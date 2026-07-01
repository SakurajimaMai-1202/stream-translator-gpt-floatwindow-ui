import os
import io
import sys
import queue
import re
import time
import logging
import contextlib
import tempfile
import gc
from abc import abstractmethod
from pathlib import Path
from typing import Any
from scipy.io.wavfile import write as write_audio

import numpy as np

from . import filters
from .common import TranslationTask, SAMPLE_RATE, LoopWorkerBase, sec2str, ApiKeyPool, INFO, WARNING
from .simul_streaming.simul_whisper.whisper.utils import compression_ratio
from .torch_setup import disable_nnpack
from .asr_postprocessor import ASRTermCorrector

try:
    import torch
    disable_nnpack(torch)
except ImportError:
    pass


def _filter_text(text: str, whisper_filters: str):
    filter_name_list = [name.strip() for name in (whisper_filters or '').split(',') if name.strip()]
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


def _normalize_duplicate_text(text: str) -> str:
    return re.sub(r'[\W_]+', '', text or '', flags=re.UNICODE).casefold()


def _is_consecutive_duplicate(previous_text: str, current_text: str) -> bool:
    previous = _normalize_duplicate_text(previous_text)
    current = _normalize_duplicate_text(current_text)
    return len(current) >= 6 and current == previous


class AudioTranscriber(LoopWorkerBase):

    suppress_consecutive_duplicates = False

    def __init__(self, whisper_filters: str = None, print_result: bool = False, output_timestamps: bool = False,
                 disable_transcription_context: bool = False, transcription_initial_prompt: str = None,
                 transcription_filters: str = None, asr_corrections_enabled: bool = False,
                 asr_correction_rules: str = None, asr_corrections_case_sensitive: bool = False):
        self.whisper_filters = whisper_filters or transcription_filters or ""
        self.print_result = print_result
        self.output_timestamps = output_timestamps
        self.disable_transcription_context = disable_transcription_context
        self.transcription_initial_prompt = transcription_initial_prompt
        self.term_corrector = ASRTermCorrector(
            asr_correction_rules if asr_corrections_enabled else None,
            case_sensitive=asr_corrections_case_sensitive,
        )

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
        previous_transcript = ""

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
            text, tokens = self.transcribe(task.audio, initial_prompt=initial_prompt)
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

            task.raw_transcript = _filter_text(text, self.whisper_filters).strip()
            if (self.suppress_consecutive_duplicates and
                    _is_consecutive_duplicate(previous_transcript, task.raw_transcript)):
                self.reset_context()
                previous_text = ""
                continue
            task.transcript = self.term_corrector.apply(task.raw_transcript).strip()
            if not task.transcript:
                continue
            previous_transcript = task.raw_transcript
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

    DEFAULT_MODEL = "grider-transwithai/parakeet-ctc-1.1b-ja"
    DEFAULT_HF_FILENAME = "parakeet-ja.nemo"

    def __init__(self, model: str = DEFAULT_MODEL, language: str = 'ja',
                 device: str = 'auto', decoding: str = 'ctc', dtype: str = 'bfloat16',
                 runtime_profile: str = 'cuda', proxy: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if str(runtime_profile or 'cuda').lower() != 'cuda':
            raise RuntimeError('Parakeet CTC JA is only enabled for the CUDA runtime profile.')
        if decoding and str(decoding).lower() != 'ctc':
            raise ValueError('Parakeet CTC JA supports only CTC decoding in this build.')
        self.language = self._normalize_language(language)
        self.model_id = model or self.DEFAULT_MODEL
        if proxy:
            _apply_hf_proxy(proxy)

        os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'stream-translator-matplotlib'))
        try:
            import torch
            from nemo.collections.asr.models import ASRModel
        except ImportError as exc:
            raise ImportError(
                'Parakeet CTC JA support requires NVIDIA NeMo. Install the CUDA Parakeet extra before using '
                '--use_nemo_asr, for example: pip install -r app/requirements_cuda_parakeet.txt'
            ) from exc

        self.device = self._resolve_device(torch, device)
        self.dtype_name, self.torch_dtype = self._resolve_dtype(torch, dtype, self.device)
        model_path = self._resolve_nemo_model_path(self.model_id)
        if model_path:
            self.model = self._quiet_call(ASRModel.restore_from, restore_path=str(model_path), map_location=self.device)
        else:
            self.model = self._quiet_call(ASRModel.from_pretrained, model_name=self.model_id, map_location=self.device)
        if self.torch_dtype is not None:
            self.model = self.model.to(device=self.device, dtype=self.torch_dtype)
        else:
            self.model = self.model.to(self.device)
        self.model.eval()
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        print(f'{INFO}Parakeet CTC JA model loaded: {self.model_id} on {self.device} dtype={self.dtype_name}')
        self._print_memory_diagnostics(torch)

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        wav_path = self._write_temp_wav(audio)
        try:
            result = self._transcribe_file(wav_path)
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass
        return self._extract_text(result), None

    def _transcribe_file(self, wav_path: Path):
        if self.torch_dtype is None:
            return self._quiet_call(
                self.model.transcribe,
                [str(wav_path)],
                batch_size=1,
                return_hypotheses=False,
            )

        import torch

        with torch.inference_mode(), torch.autocast(device_type='cuda', dtype=self.torch_dtype):
            return self._quiet_call(
                self.model.transcribe,
                [str(wav_path)],
                batch_size=1,
                return_hypotheses=False,
            )

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or 'ja').strip().lower()
        if normalized in {'', 'auto', 'ja', 'japanese'}:
            return 'ja'
        raise ValueError('Parakeet CTC JA is a Japanese-only ASR model. Set input language to Japanese or auto.')

    @staticmethod
    def _resolve_device(torch_module: Any, device: str | None) -> str:
        requested = str(device or 'auto').strip().lower()
        if requested in {'auto', ''}:
            if torch_module.cuda.is_available():
                return 'cuda:0'
            raise RuntimeError('Parakeet CTC JA requires an available CUDA GPU.')
        if requested == 'cuda':
            requested = 'cuda:0'
        if not requested.startswith('cuda'):
            raise RuntimeError('Parakeet CTC JA requires a CUDA device.')
        if not torch_module.cuda.is_available():
            raise RuntimeError('Parakeet CTC JA requires an available CUDA GPU.')
        return requested

    @staticmethod
    def _resolve_dtype(torch_module: Any, dtype: str | None, device: str) -> tuple[str, Any | None]:
        requested = str(dtype or 'bfloat16').strip().lower()
        aliases = {
            'auto': 'bfloat16',
            'bf16': 'bfloat16',
            'fp16': 'float16',
            'half': 'float16',
            'fp32': 'float32',
            'full': 'float32',
            'none': 'float32',
        }
        requested = aliases.get(requested, requested)
        if requested in {'float32', '32'}:
            return 'float32', None
        if requested == 'bfloat16':
            is_supported = getattr(torch_module.cuda, 'is_bf16_supported', lambda: False)
            if callable(is_supported) and is_supported():
                return 'bfloat16', torch_module.bfloat16
            print(f'{WARNING}Parakeet CTC JA requested bfloat16, but this CUDA device does not report BF16 support; falling back to float16.')
            return 'float16', torch_module.float16
        if requested in {'float16', '16'}:
            return 'float16', torch_module.float16
        raise ValueError('Parakeet CTC JA dtype must be auto, bfloat16, float16, or float32.')

    @classmethod
    def _resolve_nemo_model_path(cls, model_id: str) -> Path | None:
        path = Path(str(model_id)).expanduser()
        if path.suffix.lower() == '.nemo':
            if not path.exists():
                raise FileNotFoundError(f'Parakeet CTC JA .nemo file not found: {path}')
            return path
        if model_id == cls.DEFAULT_MODEL:
            try:
                from huggingface_hub import hf_hub_download
            except ImportError as exc:
                raise ImportError('Parakeet CTC JA HuggingFace download requires huggingface_hub.') from exc
            return Path(hf_hub_download(repo_id=model_id, filename=cls.DEFAULT_HF_FILENAME))
        return None

    def _print_memory_diagnostics(self, torch_module: Any) -> None:
        try:
            dtype_counts: dict[str, int] = {}
            dtype_bytes: dict[str, int] = {}
            buffer_counts: dict[str, int] = {}
            buffer_bytes: dict[str, int] = {}
            total_params = 0
            for param in self.model.parameters():
                count = int(param.numel())
                dtype = str(param.dtype).replace('torch.', '')
                dtype_counts[dtype] = dtype_counts.get(dtype, 0) + count
                dtype_bytes[dtype] = dtype_bytes.get(dtype, 0) + count * int(param.element_size())
                total_params += count
            total_buffers = 0
            for buffer in self.model.buffers():
                count = int(buffer.numel())
                dtype = str(buffer.dtype).replace('torch.', '')
                buffer_counts[dtype] = buffer_counts.get(dtype, 0) + count
                buffer_bytes[dtype] = buffer_bytes.get(dtype, 0) + count * int(buffer.element_size())
                total_buffers += count
            dtype_summary = ', '.join(
                f'{dtype}:{count / 1_000_000_000:.3f}B/{dtype_bytes[dtype] / (1024 ** 3):.2f}GiB'
                for dtype, count in sorted(dtype_counts.items())
            )
            buffer_summary = ', '.join(
                f'{dtype}:{count / 1_000_000_000:.3f}B/{buffer_bytes[dtype] / (1024 ** 3):.2f}GiB'
                for dtype, count in sorted(buffer_counts.items())
            ) or 'none'
            allocated = torch_module.cuda.memory_allocated() / (1024 ** 3)
            reserved = torch_module.cuda.memory_reserved() / (1024 ** 3)
            max_allocated = torch_module.cuda.max_memory_allocated() / (1024 ** 3)
            print(
                f'{INFO}Parakeet CTC JA memory: params={total_params / 1_000_000_000:.3f}B '
                f'[{dtype_summary}], buffers={total_buffers / 1_000_000_000:.3f}B [{buffer_summary}], cuda_allocated={allocated:.2f}GiB, '
                f'cuda_reserved={reserved:.2f}GiB, cuda_max_allocated={max_allocated:.2f}GiB'
            )
        except Exception as exc:
            print(f'{WARNING}Parakeet CTC JA memory diagnostics failed: {exc}')

    @staticmethod
    def _write_temp_wav(audio: np.array) -> Path:
        samples = np.asarray(audio, dtype=np.float32)
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
        samples = np.clip(samples, -1.0, 1.0)
        pcm = (samples * 32767.0).astype(np.int16)
        tmp = tempfile.NamedTemporaryFile(prefix='parakeet-ctc-ja-', suffix='.wav', delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        write_audio(str(tmp_path), SAMPLE_RATE, pcm)
        return tmp_path

    @classmethod
    def _extract_text(cls, result: Any) -> str:
        if isinstance(result, list):
            if not result:
                return ''
            return cls._extract_text(result[0])
        if isinstance(result, tuple):
            return cls._extract_text(result[0] if result else '')
        if hasattr(result, 'text'):
            return str(result.text or '').strip()
        return str(result or '').strip()

    @staticmethod
    def _quiet_call(func, *args, **kwargs):
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        previous_disable_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                return func(*args, **kwargs)
        finally:
            logging.disable(previous_disable_level)


class SenseVoiceTranscriber(AudioTranscriber):

    TAG_RE = re.compile(r"<\|[^|>]+?\|>")

    def __init__(self, model: str = 'iic/SenseVoiceSmall', language: str = 'auto',
                 device: str = 'cpu', proxy: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if proxy:
            _apply_hf_proxy(proxy)
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise ImportError(
                'SenseVoice support requires FunASR. Install the SenseVoice runtime extra before using --use_sensevoice_asr.'
            ) from exc

        self.language = self._normalize_language(language)
        self.device = device or 'cpu'
        self.model_id = model or 'iic/SenseVoiceSmall'
        self.model = self._quiet_call(
            AutoModel,
            model=self.model_id,
            trust_remote_code=True,
            device=self.device,
            disable_update=True,
        )

    def transcribe(self, audio: np.array, initial_prompt: str = None) -> tuple[str, list | None]:
        wav_path = self._write_temp_wav(audio)
        try:
            result = self._quiet_call(
                self.model.generate,
                input=str(wav_path),
                cache={},
                language=self.language,
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
            )
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass

        return self._extract_text(result), None

    @classmethod
    def _write_temp_wav(cls, audio: np.array) -> Path:
        samples = np.asarray(audio, dtype=np.float32)
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
        samples = np.clip(samples, -1.0, 1.0)
        pcm = (samples * 32767.0).astype(np.int16)
        tmp = tempfile.NamedTemporaryFile(prefix='sensevoice-', suffix='.wav', delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        write_audio(str(tmp_path), SAMPLE_RATE, pcm)
        return tmp_path

    @classmethod
    def _extract_text(cls, result: Any) -> str:
        if isinstance(result, list):
            return cls._clean_text(' '.join(cls._extract_text(item) for item in result))
        if isinstance(result, dict):
            return cls._clean_text(str(result.get('text') or result.get('sentence') or ''))
        return cls._clean_text(str(result or ''))

    @classmethod
    def _clean_text(cls, text: str) -> str:
        return cls.TAG_RE.sub('', text).strip()

    @staticmethod
    def _quiet_call(func, *args, **kwargs):
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        previous_disable_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                return func(*args, **kwargs)
        finally:
            logging.disable(previous_disable_level)

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or 'auto').strip().lower()
        if normalized in {'', 'auto'}:
            return 'auto'
        if normalized in {'zh', 'zh-tw', 'zh-hant', 'zh-cn', 'zh-hans', 'chinese'}:
            return 'zh'
        if normalized in {'ja', 'japanese'}:
            return 'ja'
        if normalized in {'en', 'english'}:
            return 'en'
        if normalized in {'ko', 'korean'}:
            return 'ko'
        return normalized


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
    suppress_consecutive_duplicates = True

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

        dtype_obj = torch.bfloat16
        if dtype:
            dtype_obj = getattr(torch, dtype, None)
            if not isinstance(dtype_obj, torch.dtype):
                raise ValueError(f'Unsupported Qwen3-ASR dtype: {dtype}')

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

    @staticmethod
    def _cuda_has_supported_device(torch) -> bool:
        if not torch.cuda.is_available():
            return False
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
