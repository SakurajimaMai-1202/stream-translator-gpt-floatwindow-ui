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
