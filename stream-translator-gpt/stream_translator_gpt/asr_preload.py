import gc
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .common import INFO
from .audio_transcriber import (OpenaiWhisper, FasterWhisper, SimulStreaming, RemoteOpenaiTranscriber, HFTranscriber,
                                Qwen3ASRTranscriber, NemoASRTranscriber)


@dataclass(frozen=True)
class ASRConfig:
    backend: str
    model: str | None
    language: str | None
    processing_proxy: str | None
    transcription_filters: str
    print_result: bool
    output_timestamps: bool
    disable_transcription_context: bool
    transcription_initial_prompt: str | None
    use_faster_whisper: bool = False
    openai_transcription_model: str | None = None
    qwen3_asr_model: str | None = None
    qwen3_asr_dtype: str | None = None
    qwen3_asr_device_map: str | None = None
    qwen3_asr_max_new_tokens: int | None = None
    qwen3_asr_quantization: str | None = None
    qwen3_asr_bnb_4bit_quant_type: str | None = None
    qwen3_asr_bnb_4bit_use_double_quant: bool = False
    nemo_asr_model: str | None = None
    nemo_asr_device: str | None = None
    nemo_asr_decoding: str | None = None

    def fingerprint(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((key, str(value)) for key, value in self.__dict__.items()))

    def label(self) -> str:
        model = self.qwen3_asr_model or self.nemo_asr_model or self.openai_transcription_model or self.model or ""
        extra = []
        if self.backend == "qwen3":
            extra.append(str(self.qwen3_asr_device_map or "auto"))
            extra.append(str(self.qwen3_asr_quantization or "none"))
        elif self.backend == "nemo":
            extra.append(str(self.nemo_asr_device or "auto"))
            extra.append(str(self.nemo_asr_decoding or "tdt"))
        suffix = f" ({', '.join(extra)})" if extra else ""
        return f"{self.backend}: {model}{suffix}"


def normalize_language(language: str | None) -> str | None:
    if language is None:
        return None
    language = str(language).strip()
    return None if not language or language == "auto" else language


def build_asr_config(options: dict[str, Any]) -> ASRConfig:
    backend = "whisper"
    if options.get("use_openai_transcription_api"):
        backend = "openai_api"
    elif options.get("use_hf_asr"):
        backend = "hf"
    elif options.get("use_qwen3_asr"):
        backend = "qwen3"
    elif options.get("use_nemo_asr"):
        backend = "nemo"
    elif options.get("use_simul_streaming") and options.get("use_faster_whisper"):
        backend = "faster_simul"
    elif options.get("use_simul_streaming"):
        backend = "simul"
    elif options.get("use_faster_whisper"):
        backend = "faster"

    model = options.get("model")
    if backend in {"openai_api", "qwen3", "nemo"}:
        model = None
    openai_transcription_model = options.get("openai_transcription_model") if backend == "openai_api" else None
    qwen3_asr_model = options.get("qwen3_asr_model") if backend == "qwen3" else None
    qwen3_asr_dtype = options.get("qwen3_asr_dtype") if backend == "qwen3" else None
    qwen3_asr_device_map = options.get("qwen3_asr_device_map") if backend == "qwen3" else None
    qwen3_asr_max_new_tokens = options.get("qwen3_asr_max_new_tokens") if backend == "qwen3" else None
    qwen3_asr_quantization = options.get("qwen3_asr_quantization") if backend == "qwen3" else None
    qwen3_asr_bnb_4bit_quant_type = options.get("qwen3_asr_bnb_4bit_quant_type") if backend == "qwen3" else None
    qwen3_asr_bnb_4bit_use_double_quant = (
        bool(options.get("qwen3_asr_bnb_4bit_use_double_quant")) if backend == "qwen3" else False)
    nemo_asr_model = options.get("nemo_asr_model") if backend == "nemo" else None
    nemo_asr_device = options.get("nemo_asr_device") if backend == "nemo" else None
    nemo_asr_decoding = options.get("nemo_asr_decoding") if backend == "nemo" else None

    return ASRConfig(
        backend=backend,
        model=model,
        language=normalize_language(options.get("language")),
        processing_proxy=options.get("processing_proxy"),
        transcription_filters=options.get("transcription_filters") or "emoji_filter,repetition_filter",
        print_result=not bool(options.get("hide_transcribe_result")),
        output_timestamps=bool(options.get("output_timestamps")),
        disable_transcription_context=bool(options.get("disable_transcription_context")),
        transcription_initial_prompt=options.get("transcription_initial_prompt"),
        use_faster_whisper=backend in {"faster", "faster_simul"},
        openai_transcription_model=openai_transcription_model,
        qwen3_asr_model=qwen3_asr_model,
        qwen3_asr_dtype=qwen3_asr_dtype,
        qwen3_asr_device_map=qwen3_asr_device_map,
        qwen3_asr_max_new_tokens=qwen3_asr_max_new_tokens,
        qwen3_asr_quantization=qwen3_asr_quantization,
        qwen3_asr_bnb_4bit_quant_type=qwen3_asr_bnb_4bit_quant_type,
        qwen3_asr_bnb_4bit_use_double_quant=qwen3_asr_bnb_4bit_use_double_quant,
        nemo_asr_model=nemo_asr_model,
        nemo_asr_device=nemo_asr_device,
        nemo_asr_decoding=nemo_asr_decoding,
    )


def create_transcriber(config: ASRConfig):
    common_args = {
        "transcription_filters": config.transcription_filters,
        "print_result": config.print_result,
        "output_timestamps": config.output_timestamps,
        "disable_transcription_context": config.disable_transcription_context,
        "transcription_initial_prompt": config.transcription_initial_prompt,
    }

    if config.backend == "faster_simul":
        return SimulStreaming(model=config.model,
                              language=config.language,
                              use_faster_whisper=True,
                              proxy=config.processing_proxy,
                              **common_args)
    if config.backend == "simul":
        return SimulStreaming(model=config.model,
                              language=config.language,
                              use_faster_whisper=False,
                              proxy=config.processing_proxy,
                              **common_args)
    if config.backend == "faster":
        return FasterWhisper(model=config.model, language=config.language, proxy=config.processing_proxy, **common_args)
    if config.backend == "openai_api":
        return RemoteOpenaiTranscriber(model=config.openai_transcription_model,
                                       language=config.language,
                                       proxy=config.processing_proxy,
                                       **common_args)
    if config.backend == "hf":
        return HFTranscriber(model=config.model, language=config.language, proxy=config.processing_proxy, **common_args)
    if config.backend == "qwen3":
        return Qwen3ASRTranscriber(model=config.qwen3_asr_model,
                                   language=config.language,
                                   proxy=config.processing_proxy,
                                   dtype=config.qwen3_asr_dtype,
                                   device_map=config.qwen3_asr_device_map,
                                   max_new_tokens=config.qwen3_asr_max_new_tokens,
                                   quantization=config.qwen3_asr_quantization,
                                   bnb_4bit_quant_type=config.qwen3_asr_bnb_4bit_quant_type,
                                   bnb_4bit_use_double_quant=config.qwen3_asr_bnb_4bit_use_double_quant,
                                   **common_args)
    if config.backend == "nemo":
        return NemoASRTranscriber(model=config.nemo_asr_model,
                                  proxy=config.processing_proxy,
                                  device=config.nemo_asr_device,
                                  decoding=config.nemo_asr_decoding,
                                  **common_args)
    return OpenaiWhisper(model=config.model, language=config.language, **common_args)


class PreloadedTranscriberManager:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.transcriber = None
        self.config: ASRConfig | None = None
        self.loaded_at: datetime | None = None
        self.in_use = False
        self.status = "empty"
        self.error: str | None = None

    def preload(self, config: ASRConfig) -> str:
        if config.backend == "openai_api":
            raise ValueError("OpenAI Transcription API is remote and does not need ASR preloading.")

        with self._lock:
            if self.in_use:
                raise RuntimeError("ASR model is currently in use. Stop the running task before preloading.")
            if self.transcriber is not None and self.matches(config):
                return f"ASR model already preloaded: {config.label()}"
            self._unload_locked()
            self.error = None
            self.status = "loading"

        print(f"{INFO}Preloading ASR model: {config.label()}")
        try:
            transcriber = create_transcriber(config)
        except Exception as e:
            with self._lock:
                self.error = str(e)
                self.status = "error"
            raise

        with self._lock:
            self.transcriber = transcriber
            self.config = config
            self.loaded_at = datetime.now(timezone.utc)
            self.status = "loaded"
        return f"ASR model preloaded: {config.label()}"

    def unload(self) -> str:
        with self._lock:
            if self.in_use:
                raise RuntimeError("ASR model is currently in use. Stop the running task before unloading.")
            if self.transcriber is None:
                self._unload_locked()
                return "No ASR model is preloaded."
            label = self.config.label() if self.config else "unknown"
            self._unload_locked()
        self._cleanup()
        return f"ASR model unloaded: {label}"

    def matches(self, config: ASRConfig) -> bool:
        with self._lock:
            return self.config is not None and self.config.fingerprint() == config.fingerprint()

    def get_for_run(self, config: ASRConfig):
        with self._lock:
            if self.transcriber is None:
                return None
            if not self.matches(config):
                loaded = self.config.label() if self.config else "unknown"
                raise RuntimeError(
                    f"Preloaded ASR model does not match current settings. Loaded: {loaded}. Current: {config.label()}. "
                    "Preload again or unload the model before running.")
            if self.in_use:
                raise RuntimeError("Preloaded ASR model is already in use.")
            self.in_use = True
            self.status = "running"
            transcriber = self.transcriber
        if hasattr(transcriber, "prepare_for_reuse"):
            transcriber.prepare_for_reuse()
        return transcriber

    def release(self) -> None:
        with self._lock:
            self.in_use = False
            if self.transcriber is not None:
                self.status = "loaded"

    def status_text(self) -> str:
        with self._lock:
            if self.status == "error":
                return f"ASR preload error: {self.error or 'unknown error'}"
            if self.transcriber is None:
                return "No ASR model preloaded."
            state = "running" if self.in_use else self.status
            return f"ASR model {state}: {self.config.label() if self.config else 'unknown'}"

    def _unload_locked(self) -> None:
        self.transcriber = None
        self.config = None
        self.loaded_at = None
        self.status = "empty"
        self.error = None

    @staticmethod
    def _cleanup() -> None:
        gc.collect()
        try:
            import torch
            if getattr(torch, "cuda", None) and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
