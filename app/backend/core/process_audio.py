"""GUI target discovery uses only ctypes; capture itself runs in the ASR runtime."""
from stream_translator_gpt.process_audio_targets import (
    list_process_audio_targets,
    validate_process_target,
)

__all__ = ["list_process_audio_targets", "validate_process_target"]
