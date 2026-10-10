# Windows process audio capture

Build the x64 DLL with `./build.ps1` using Visual Studio Desktop C++ Build Tools and a Windows SDK containing `audioclientactivationparams.h` (20348 or newer). The DLL uses the static C++ runtime and is output to `stream_translator_gpt/native/process_audio_capture.dll`. Generated binaries are build artifacts.

The implementation uses Microsoft's process-loopback activation API with INCLUDE_TARGET_PROCESS_TREE. A window is a selection aid; browser tabs/windows may share audio processes. Windows build 20348 or later is required. No fallback to endpoint capture occurs.

## C ABI

All functions use the C calling convention; Python should use `ctypes.CDLL`. HRESULTs are signed 32-bit integers, and negative values indicate errors.

- `void* pa_create(uint32_t pid, uint64_t expected_creation_time, int* error)`: validates a live process. Creation time is Windows FILETIME ticks; zero skips that check for native diagnostics only.
- `int pa_start(void*)`: starts once; waits up to 12 seconds for initialization.
- `int pa_read(void*, float* out, int capacity, int timeout_ms)`: returns float sample count, **48 kHz stereo interleaved float32**. Capacity is in samples; odd capacity rounds down. Zero means no data or stopped. Negative means error.
- `int pa_status(void*)`: current HRESULT.
- `uint64_t pa_dropped_frames(void*)`: lost stereo frames; a discontinuity increments at least one frame and clears queued samples. Consumers should reset downstream continuity whenever this counter changes.
- `void pa_stop(void*)`: wakes readers and waits up to five seconds for worker cleanup; repeatable.
- `void pa_destroy(void*)`: stops and releases handle; no concurrent API calls may continue using that handle.

An MTA worker owns all capture COM objects. The agile activation callback has independent reference-counted lifetime, so a late callback never references a destroyed capture. The queue holds at most five seconds and drops oldest frames. Silent packets become zeros. The process handle detects exit and prevents PID reuse. Each handle is single-use. Keep the DLL loaded until process exit: if an OS COM call stalls past stop's bounded wait, the worker retains shared state until it finishes.

Reference: [Microsoft ApplicationLoopback sample](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback).

## Reproducible local validation

Run from the repository root:

```powershell
python tools/process_audio_capture_smoke.py
python tools/process_audio_targets_smoke.py
& app/build-runtime-cache/cpu-runtime/python.exe tools/process_audio_pipeline_smoke.py
& app/build-runtime-cache/cpu-runtime/python.exe tools/process_audio_pipeline_smoke.py --route main --report benchmark-results/process-audio-capture-20261009/main-pipeline-report.json
```

The capture smoke plays two simultaneous test tones using sibling processes and checks isolation, ten silent lifecycle cycles, OS handle/thread counts, stale creation time rejection, and target exit. The targets smoke creates a minimized temporary Win32 window and checks actual window enumeration and stale target rejection. The pipeline smoke uses the existing six-second Japanese audio fixture, actual FireRed OmniVAD and cached CPU SenseVoice ONNX model, then asserts nonempty exported subtitles through both entry paths. It disables translation and sets Hugging Face offline flags. These checks validate local source/runtime inference, not browser-tab isolation, full packaged GUI deployment, or translation-provider behavior. Reports live in `benchmark-results/process-audio-capture-20261009/`.
