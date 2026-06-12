import os
import io
import sys
import queue
import re
import time
import logging
import contextlib
from abc import abstractmethod
from scipy.io.wavfile import write as write_audio

import numpy as np

from . import filters
from .common import TranslationTask, SAMPLE_RATE, LoopWorkerBase, sec2str, ApiKeyPool, ERROR, INFO, WARNING
from .simul_streaming.simul_whisper.whisper.utils import compression_ratio
from .torch_setup import disable_nnpack

try:
    import torch
    disable_nnpack(torch)
except ImportError:
    pass


def _filter_text(text: str, whisper_filters: str):
    filter_name_list = whisper_filters.split(',')
    for filter_name in filter_name_list:
        filter = getattr(filters, filter_name)
        if not filter:
            raise Exception('Unknown filter: %s' % filter_name)
        text = filter(text)
    return text


def _apply_hf_proxy(proxy: str):
    try:
        import huggingface_hub
        session = huggingface_hub.utils.get_session()
        session.proxies = {'http': proxy, 'https': proxy}
        session.verify = False
    except Exception:
        pass


class AudioTranscriber(LoopWorkerBase):

    def __init__(self, whisper_filters: str = None, print_result: bool = False, output_timestamps: bool = False,
                 disable_transcription_context: bool = False, transcription_initial_prompt: str = None,
                 transcription_filters: str = None):
        self.whisper_filters = whisper_filters or transcription_filters or ""
        self.print_result = print_result
        self.output_timestamps = output_timestamps
        self.disable_transcription_context = disable_transcription_context
        self.transcription_initial_prompt = transcription_initial_prompt

        self.constant_prompt = re.sub(r',\s*', ', ',
                                      transcription_initial_prompt) if transcription_initial_prompt else ""
        if self.constant_prompt and not self.constant_prompt.strip().endswith(','):
            self.constant_prompt += ','

    @abstractmethod
    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        """Returns (text, tokens). tokens can be None if not available."""
        pass

    def reset_context(self):
        """Override in subclass to reset model context when repetition is detected."""
        pass

    def prepare_for_reuse(self):
        """Reset per-run state before reusing a preloaded transcriber."""
        self.reset_context()

    def loop(self, input_queue: queue.SimpleQueue[TranslationTask], output_queue: queue.SimpleQueue[TranslationTask]):
        previous_text = ""

        while True:
            task = input_queue.get()
            if task is None:
                output_queue.put(None)
                break

            dynamic_context = previous_text if not self.disable_transcription_context else ""

            if self.constant_prompt:
                limit = 500 - len(self.constant_prompt) - 1
                if len(dynamic_context) > limit:
                    if limit > 0:
                        dynamic_context = dynamic_context[-limit:]
                    else:
                        dynamic_context = ""

            initial_prompt = f"{self.constant_prompt} {dynamic_context}".strip()
            if not initial_prompt:
                initial_prompt = None

            asr_started_at = time.perf_counter()
            try:
                text, tokens = self.transcribe(task.audio, initial_prompt=initial_prompt)
            except Exception as exc:
                print(f'{ERROR}ASR transcription failed: {type(exc).__name__}: {exc}', flush=True)
                output_queue.put(None)
                break
            task.asr_latency_ms = (time.perf_counter() - asr_started_at) * 1000

            if self.constant_prompt and text.strip().rstrip(',') == self.constant_prompt.strip().rstrip(','):
                text = ""

            # Repetition detection: reset context if compression ratio too high OR token diversity too low
            is_repetitive = False
            if len(text) > 10:
                zlib_ratio = compression_ratio(text)
                if tokens:
                    unique_ratio = len(set(tokens)) / len(tokens)
                else:
                    # Fallback to character-level unique ratio for models like Qwen3-ASR that don't return tokens
                    # We extract alphanumeric characters to avoid punctuation/space bias
                    clean_text = "".join(c for c in text if c.isalnum())
                    unique_ratio = len(set(clean_text)) / len(clean_text) if clean_text else 1.0

                if zlib_ratio > 2.0 or unique_ratio < 0.4:
                    self.reset_context()
                    is_repetitive = True

            task.transcript = _filter_text(text, self.whisper_filters).strip()
            if not task.transcript:
                continue
            previous_text = "" if is_repetitive else task.transcript
            if self.print_result:
                if self.output_timestamps:
                    timestamp_text = f'{sec2str(task.time_range[0])} --> {sec2str(task.time_range[1])}'
                    print(timestamp_text + ' ' + task.transcript, flush=True)
                else:
                    print(task.transcript, flush=True)
            output_queue.put(task)


class OpenaiWhisper(AudioTranscriber):

    def __init__(self, model: str, language: str, **kwargs) -> None:
        super().__init__(**kwargs)
        import whisper

        print(f'{INFO}Loading Whisper model: {model}')
        self.model = whisper.load_model(model)
        self.language = language

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        result = self.model.transcribe(audio,
                                       without_timestamps=True,
                                       language=self.language,
                                       initial_prompt=initial_prompt)
        text = result.get('text', '')
        tokens = []
        for segment in result.get('segments', []):
            tokens.extend(segment.get('tokens', []))
        return text, tokens if tokens else None


class FasterWhisper(AudioTranscriber):

    def __init__(self, model: str, language: str, proxy: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        from faster_whisper import WhisperModel

        if proxy:
            _apply_hf_proxy(proxy)
        print(f'{INFO}Loading Faster-Whisper model: {model}')
        self._whisper_model_class = WhisperModel
        self._model_name = model
        self._cpu_fallback_applied = False
        try:
            self.model = WhisperModel(model, device='auto', compute_type='auto')
        except RuntimeError as e:
            err = str(e).lower()
            if 'cublas64_12.dll' in err or 'cublas' in err:
                self.model = WhisperModel(model, device='cpu', compute_type='int8')
                self._cpu_fallback_applied = True
            else:
                raise
        self.language = language

    def _fallback_to_cpu(self):
        if self._cpu_fallback_applied:
            return
        print(f'{WARNING}CUDA 執行環境不可用，Faster-Whisper 自動回退 CPU（int8）。')
        self.model = self._whisper_model_class(self._model_name, device='cpu', compute_type='int8')
        self._cpu_fallback_applied = True

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        try:
            segments, info = self.model.transcribe(audio, language=self.language, initial_prompt=initial_prompt)
        except RuntimeError as e:
            err = str(e).lower()
            if ('cublas64_12.dll' in err or 'cublas' in err) and not self._cpu_fallback_applied:
                self._fallback_to_cpu()
                segments, info = self.model.transcribe(audio, language=self.language, initial_prompt=initial_prompt)
            else:
                raise
        text = ''
        tokens = []
        for segment in segments:
            text += segment.text
            tokens.extend(getattr(segment, 'tokens', None) or [])
        return text, tokens if tokens else None


class SimulStreaming(AudioTranscriber):

    def __init__(self, model: str, language: str, use_faster_whisper: bool, proxy: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        from .simul_streaming.simulstreaming_whisper import SimulWhisperASR, SimulWhisperOnline

        fw_encoder = None
        if use_faster_whisper:
            print(f'{INFO}Loading Faster-Whisper as encoder for SimulStreaming: {model}')
            from faster_whisper import WhisperModel
            if proxy:
                _apply_hf_proxy(proxy)
            try:
                fw_encoder = WhisperModel(model, device='auto', compute_type='auto')
            except RuntimeError as e:
                err = str(e).lower()
                if 'cublas64_12.dll' in err or 'cublas' in err:
                    print(f'{WARNING}SimulStreaming 的 Faster-Whisper 編碼器 CUDA 不可用，改用 CPU（int8）。')
                    fw_encoder = WhisperModel(model, device='cpu', compute_type='int8')
                else:
                    raise

        print(f'{INFO}Loading SimulStreaming model: {model}')
        simulstreaming_params = {
            "language": language,
            "model": model,
            "cif_ckpt_path": None,
            "frame_threshold": 25,
            "audio_max_len": 10.0,
            "audio_min_len": 0.0,
            "segment_length": 0.5,
            "task": "transcribe",
            "beams": 1,
            "decoder_type": "greedy",
            "never_fire": False,
            "init_prompt": self.constant_prompt,
            "static_init_prompt": None,
            "max_context_tokens": 50,
            "logdir": None,
            "fw_encoder": fw_encoder,
        }
        asr = SimulWhisperASR(**simulstreaming_params)
        self.asr_online = SimulWhisperOnline(asr)
        self.asr_online.init()

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        self.asr_online.insert_audio_chunk(audio)
        result = self.asr_online.process_iter(is_last=True)
        return result.get('text', ''), result.get('tokens', None)

    def reset_context(self):
        self.asr_online.model.refresh_segment(complete=True)
        self.asr_online.unicode_buffer = []

    def prepare_for_reuse(self):
        self.asr_online.init()


class RemoteOpenaiTranscriber(AudioTranscriber):

    def __init__(self, model: str, language: str, proxy: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        print(f'{INFO}Using {model} API as transcription engine.')
        self.model = model
        self.language = language
        self.proxy = proxy

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        from openai import OpenAI
        import httpx

        # Create an in-memory buffer
        audio_buffer = io.BytesIO()
        audio_buffer.name = 'audio.wav'
        write_audio(audio_buffer, SAMPLE_RATE, audio)
        audio_buffer.seek(0)

        call_args = {
            'model': self.model,
            'file': audio_buffer,
            'language': self.language,
        }
        if initial_prompt:
            call_args['prompt'] = initial_prompt

        ApiKeyPool.use_openai_api()
        client = OpenAI(http_client=httpx.Client(proxy=self.proxy))
        result = client.audio.transcriptions.create(**call_args).text
        return result, None


class HFTranscriber(AudioTranscriber):

    def __init__(self, model: str, language: str, proxy: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        from transformers import pipeline

        if proxy:
            _apply_hf_proxy(proxy)

        if not os.path.exists(model):
            try:
                from huggingface_hub import model_info
                info = model_info(model)
                tag = info.pipeline_tag
                if tag and tag != 'automatic-speech-recognition':
                    raise ValueError(
                        f'Model "{model}" has pipeline_tag="{tag}", not "automatic-speech-recognition". '
                        f'It is not compatible with --use_hf_asr. '
                        f'Please choose a model with pipeline_tag="automatic-speech-recognition" on HuggingFace Hub.')
            except ImportError:
                pass

        print(f'{INFO}Loading HuggingFace ASR model: {model}')
        self.language = language
        self.pipe = pipeline('automatic-speech-recognition', model=model, device_map='auto')

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        generate_kwargs = {}
        if self.language:
            generate_kwargs['language'] = self.language
        result = self.pipe(
            {
                'array': audio,
                'sampling_rate': SAMPLE_RATE
            },
            generate_kwargs=generate_kwargs,
        )
        return result['text'], None


class NemoASRTranscriber(AudioTranscriber):

    def __init__(self, *args, **kwargs) -> None:
        raise ImportError(
            "Nvidia NeMo Parakeet ASR is not supported in this build to prevent heavy and unstable Python dependencies on Windows."
        )

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        return "", None


def _load_qwen3_asr_model_class():
    # qwen_asr imports the forced aligner eagerly, but plain ASR does not need it.
    # Avoid importing nagisa/dynet here because some older CPUs hit SIGILL in dynet wheels.
    module_name = 'qwen_asr.inference.qwen3_forced_aligner'
    if module_name not in sys.modules:
        import types
        forced_aligner_stub = types.ModuleType(module_name)

        class Qwen3ForcedAligner:

            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                raise RuntimeError('Qwen3 forced alignment is not available in this transcription backend.')

        forced_aligner_stub.Qwen3ForcedAligner = Qwen3ForcedAligner
        sys.modules[module_name] = forced_aligner_stub

    from qwen_asr import Qwen3ASRModel
    return Qwen3ASRModel


class _TransformersPadTokenLogFilter(logging.Filter):

    def filter(self, record):
        return 'Setting `pad_token_id` to `eos_token_id`' not in record.getMessage()


def _install_transformers_pad_token_log_filter():
    logger = logging.getLogger('transformers.generation.utils')
    if any(isinstance(filter_, _TransformersPadTokenLogFilter) for filter_ in logger.filters):
        return
    logger.addFilter(_TransformersPadTokenLogFilter())


def _parse_torch_cuda_arch(arch: str) -> tuple[int, int] | None:
    match = re.fullmatch(r'sm_(\d+)(\d)', arch)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


class Qwen3ASRTranscriber(AudioTranscriber):
    LANGUAGE_NAMES = {
        'ar': 'Arabic',
        'cs': 'Czech',
        'da': 'Danish',
        'de': 'German',
        'el': 'Greek',
        'en': 'English',
        'es': 'Spanish',
        'fa': 'Persian',
        'fi': 'Finnish',
        'fil': 'Filipino',
        'fr': 'French',
        'hi': 'Hindi',
        'hu': 'Hungarian',
        'id': 'Indonesian',
        'it': 'Italian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'mk': 'Macedonian',
        'ms': 'Malay',
        'nl': 'Dutch',
        'pl': 'Polish',
        'pt': 'Portuguese',
        'ro': 'Romanian',
        'ru': 'Russian',
        'sv': 'Swedish',
        'th': 'Thai',
        'tl': 'Filipino',
        'tr': 'Turkish',
        'vi': 'Vietnamese',
        'yue': 'Cantonese',
        'zh': 'Chinese',
        'zh-cn': 'Chinese',
        'zh-hans': 'Chinese',
        'zh-hant': 'Chinese',
        'zh-tw': 'Chinese',
    }
    SUPPORTED_LANGUAGE_NAMES = set(LANGUAGE_NAMES.values())

    def __init__(self, model: str, language: str, proxy: str = None, dtype: str = 'bfloat16',
                 device_map: str = 'auto', max_new_tokens: int = 128, quantization: str = 'none',
                 bnb_4bit_quant_type: str = 'nf4', bnb_4bit_use_double_quant: bool = False,
                 rms_threshold: float = 0.005, **kwargs) -> None:
        super().__init__(**kwargs)

        try:
            import torch
            Qwen3ASRModel = _load_qwen3_asr_model_class()
        except ImportError as e:
            raise ImportError(
                'Qwen3-ASR support requires the qwen_asr extra. Install it with: '
                'pip install "stream-translator-gpt[qwen_asr]"'
            ) from e

        if proxy:
            _apply_hf_proxy(proxy)

        self._validate_device_map(torch, device_map)
        device_map = self._resolve_device_map(torch, device_map)

        dtype_obj = torch.bfloat16
        if dtype:
            dtype_obj = getattr(torch, dtype, None)
            if not isinstance(dtype_obj, torch.dtype):
                raise ValueError(f'Unsupported Qwen3-ASR dtype: {dtype}')

        # Fallback to float16 if bfloat16 is requested but unsupported by the current GPU
        if dtype_obj == torch.bfloat16 and torch.cuda.is_available() and device_map != 'cpu':
            is_bf16_supported = False
            try:
                is_bf16_supported = torch.cuda.is_bf16_supported()
            except AttributeError:
                pass
            if not is_bf16_supported:
                print(f'{WARNING}bfloat16 is not supported on the current GPU. Falling back to float16 for Qwen3-ASR.')
                dtype_obj = torch.float16

        if device_map == 'cpu' and dtype_obj != torch.float32:
            print(f'{WARNING}Using float32 for Qwen3-ASR CPU fallback.')
            dtype_obj = torch.float32


        # 檢測並啟用 SDPA / FlashAttention-2 加速
        attn_implementation = "sdpa"
        try:
            import flash_attn
            attn_implementation = "flash_attention_2"
            print(f'{INFO}FlashAttention-2 detected, using it for Qwen3-ASR')
        except ImportError:
            print(f'{INFO}Using PyTorch SDPA (Scaled Dot-Product Attention) for Qwen3-ASR')

        model_kwargs = {
            'dtype': dtype_obj,
            'device_map': device_map or 'auto',
            'max_new_tokens': max_new_tokens or 128,
            'max_inference_batch_size': 1,
            'num_beams': 1,
            'attn_implementation': attn_implementation,
        }

        # 處理 4-bit/8-bit 量化
        quantization = (quantization or 'none').strip().lower()
        if self._is_rocm_torch(torch) and (quantization not in {'none', ''} or kwargs.get('load_in_4bit', False)):
            raise RuntimeError(
                'Qwen3-ASR bitsandbytes quantization is not enabled on the ROCm branch. '
                'Use full precision / bf16 first when testing AMD GPUs.'
            )
        if quantization in {'bnb_4bit', '4bit'} or kwargs.get('load_in_4bit', False):
            from transformers import BitsAndBytesConfig
            print(f'{INFO}Enabling 4-bit quantization (NF4) for Qwen3-ASR')
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type=bnb_4bit_quant_type or 'nf4',
                bnb_4bit_compute_dtype=dtype_obj,
                bnb_4bit_use_double_quant=bool(bnb_4bit_use_double_quant),
            )
            model_kwargs['quantization_config'] = bnb_config
            model_kwargs.pop('dtype', None)
        elif quantization in {'bnb_8bit', '8bit'}:
            from transformers import BitsAndBytesConfig
            print(f'{INFO}Enabling 8-bit quantization for Qwen3-ASR')
            model_kwargs['quantization_config'] = BitsAndBytesConfig(load_in_8bit=True)
            model_kwargs.pop('dtype', None)

        print(f'{INFO}Loading Qwen3-ASR model: {model}')
        self.model = Qwen3ASRModel.from_pretrained(model, **model_kwargs)
        self._set_generation_pad_token_id()
        _install_transformers_pad_token_log_filter()

        self.language = self._normalize_language(language)
        self.rms_threshold = rms_threshold

    @classmethod
    def _normalize_language(cls, language: str | None) -> str | None:
        if language is None:
            return None
        language = str(language).strip()
        if not language or language.lower() == 'auto':
            return None

        language_key = language.lower().replace('_', '-')
        if language_key in cls.LANGUAGE_NAMES:
            return cls.LANGUAGE_NAMES[language_key]

        language_name = language[:1].upper() + language[1:].lower()
        if language_name in cls.SUPPORTED_LANGUAGE_NAMES:
            return language_name

        supported = ', '.join(sorted(cls.LANGUAGE_NAMES.keys()))
        raise ValueError(
            f'Qwen3-ASR does not support language "{language}". '
            f'Use "auto" or one of these language codes: {supported}.')

    @classmethod
    def _validate_device_map(cls, torch, device_map: str | None) -> None:
        device_map = str(device_map or 'auto').strip() or 'auto'
        if device_map == 'cpu':
            return
        if cls._is_rocm_torch(torch):
            if torch.cuda.is_available():
                return
            raise RuntimeError(
                'ROCm PyTorch was detected, but no AMD GPU is available through torch.cuda. '
                'Check the ROCm driver/runtime and PyTorch ROCm installation.')
        if device_map == 'auto':
            if not torch.cuda.is_available() or cls._cuda_has_supported_device(torch):
                return
            raise RuntimeError(
                'Current PyTorch CUDA build does not support the available GPU(s) for Qwen3-ASR. '
                'Install a PyTorch build that supports your GPU compute capability, or explicitly use '
                '--qwen3_asr_device_map cpu.')
        if device_map.startswith('cuda'):
            if cls._cuda_has_supported_device(torch):
                return
            raise RuntimeError(
                'Current PyTorch CUDA build does not support the available GPU(s) for Qwen3-ASR. '
                'Install a PyTorch build that supports your GPU compute capability, or explicitly use '
                '--qwen3_asr_device_map cpu.')

    @classmethod
    def _resolve_device_map(cls, torch, device_map: str | None) -> str:
        requested = str(device_map or 'auto').strip() or 'auto'
        if requested == 'cpu' or not cls._is_rocm_torch(torch) or not torch.cuda.is_available():
            return requested

        supported_arches = set(torch.cuda.get_arch_list())
        requested_index = cls._requested_cuda_index(requested)
        candidate_indexes = (
            [requested_index]
            if requested_index is not None
            else list(range(torch.cuda.device_count()))
        )

        detected_devices = []
        for index in candidate_indexes:
            try:
                properties = torch.cuda.get_device_properties(index)
                name = str(getattr(properties, 'name', '') or torch.cuda.get_device_name(index))
                arch = str(getattr(properties, 'gcnArchName', '') or '').split(':', 1)[0]
            except Exception as error:
                detected_devices.append(f'cuda:{index} (unavailable: {error})')
                continue

            label = f'cuda:{index} {name}'.strip()
            detected_devices.append(f'{label} [{arch or "unknown arch"}]')
            if not supported_arches or not arch or arch in supported_arches:
                selected = f'cuda:{index}'
                print(f'{INFO}Selected ROCm GPU: {label} [{arch or "unknown arch"}]', flush=True)
                return selected

        supported = ', '.join(sorted(supported_arches)) or 'not reported'
        detected = ', '.join(detected_devices) or 'none'
        print(
            f'{WARNING}No compatible ROCm GPU was found. Detected: {detected}; '
            f'PyTorch kernels: {supported}. Falling back to CPU to avoid HIP invalid device function.',
            flush=True,
        )
        return 'cpu'

    @staticmethod
    def _requested_cuda_index(device_map: str) -> int | None:
        match = re.fullmatch(r'(?:cuda|hip):(\d+)', device_map.lower())
        return int(match.group(1)) if match else None

    @staticmethod
    def _cuda_has_supported_device(torch) -> bool:
        if not torch.cuda.is_available():
            return False
        if Qwen3ASRTranscriber._is_rocm_torch(torch):
            return True
        supported_caps = []
        for arch in torch.cuda.get_arch_list():
            capability = _parse_torch_cuda_arch(arch)
            if capability is not None:
                supported_caps.append(capability)
        if not supported_caps:
            return True
        min_cap = min(supported_caps)
        for index in range(torch.cuda.device_count()):
            if torch.cuda.get_device_capability(index) >= min_cap:
                return True
        return False

    @staticmethod
    def _is_rocm_torch(torch) -> bool:
        return bool(getattr(getattr(torch, 'version', None), 'hip', None))

    def _set_generation_pad_token_id(self) -> None:
        hf_model = getattr(self.model, 'model', None)
        generation_config = getattr(hf_model, 'generation_config', None)
        model_config = getattr(hf_model, 'config', None)
        pad_token_id = getattr(generation_config, 'pad_token_id', None)
        if pad_token_id is None:
            pad_token_id = getattr(model_config, 'pad_token_id', None)
        if pad_token_id is None:
            pad_token_id = getattr(generation_config, 'eos_token_id', None)
            if pad_token_id is None:
                pad_token_id = getattr(model_config, 'eos_token_id', None)
            if isinstance(pad_token_id, (list, tuple)):
                pad_token_id = pad_token_id[0] if pad_token_id else None
            if pad_token_id is None:
                return

        if generation_config is not None:
            generation_config.pad_token_id = pad_token_id
        if model_config is not None:
            model_config.pad_token_id = pad_token_id
        self._wrap_generate_with_pad_token_id(hf_model, pad_token_id)

    @staticmethod
    def _wrap_generate_with_pad_token_id(hf_model, pad_token_id) -> None:
        if hf_model is None or getattr(hf_model, '_stream_translator_pad_token_wrapped', False):
            return
        original_generate = getattr(hf_model, 'generate', None)
        if original_generate is None:
            return

        def generate_with_pad_token_id(*args, **kwargs):
            kwargs.setdefault('pad_token_id', pad_token_id)
            return original_generate(*args, **kwargs)

        hf_model.generate = generate_with_pad_token_id
        hf_model._stream_translator_pad_token_wrapped = True

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        if rms < self.rms_threshold:
            return "", None

        results = self.model.transcribe(audio=(audio, SAMPLE_RATE), context=initial_prompt or '', language=self.language)
        result = results[0] if results else None
        if result is None:
            return '', None
        if isinstance(result, dict):
            return result.get('text', ''), None
        return getattr(result, 'text', ''), None
