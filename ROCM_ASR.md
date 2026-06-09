# ROCm ASR Experimental Branch

This branch is for testing AMD ROCm support for local ASR only.

## Scope

Supported in this branch:

- Qwen3-ASR local transcription
- Silero / FireRed VAD
- URL, microphone, system audio, and local file input

Not supported in this branch:

- Faster-Whisper GPU acceleration
- SimulStreaming
- OpenAI Whisper API as an ASR backend
- Local LLM acceleration on AMD GPU
- bitsandbytes 4-bit / 8-bit quantization for Qwen3-ASR

## Expected Runtime

ROCm PyTorch exposes AMD GPUs through the `torch.cuda` namespace. The app checks
`torch.version.hip` to identify ROCm builds and skips NVIDIA CUDA capability
checks when ROCm is detected.

Recommended first test:

1. Install an AMD ROCm PyTorch build that supports your GPU.
2. Select `Qwen/Qwen3-ASR-1.7B` or `Qwen/Qwen3-ASR-0.6B`.
3. Keep Qwen3 dtype at `bfloat16` or `float16`.
4. Keep 4-bit quantization disabled.
5. Run a short local audio file before testing long streams.

## Validation Status

Maintainer does not currently have an AMD GPU available. Treat this branch as
experimental until users with AMD hardware report successful Qwen3-ASR + VAD
runs.

Useful report details:

- GPU model
- OS version
- PyTorch version
- `torch.version.hip`
- `torch.cuda.is_available()`
- Qwen3-ASR model used
- Audio length and transcription time
