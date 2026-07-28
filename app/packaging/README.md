# Packaging

Run release commands from the `app` directory. The root-level scripts are the
developer-facing entry points; scripts in this `packaging` directory are
implementation details.

## Developer entry points

Use `app/build_release.ps1` for normal release builds:

```powershell
.\build_release.ps1 -Profile cuda
.\build_release.ps1 -Profile cpu
.\build_release.ps1 -Profile rocm
```

When dependencies have not changed and the three validated runtime caches
already exist, refresh only the application code and reuse each cache:

```powershell
.\build_release.ps1 -Profile cuda -ReuseRuntimeCache
.\build_release.ps1 -Profile cpu -ReuseRuntimeCache
.\build_release.ps1 -Profile rocm -ReuseRuntimeCache
```

This mode validates the runtime manifest, torch backend, and required imports
before assembling a new package. It is useful on a build machine without an AMD
GPU because it does not attempt to reconstruct the ROCm PyTorch environment.

The legacy CUDA wrappers are still available:

```powershell
.\build_cuda_release.ps1
.\build_cuda_runtime.ps1
```

They are compatibility aliases for `-Profile cuda` and are kept only so older
automation does not break.

## Internal scripts

| Script | Purpose |
| --- | --- |
| `build_profile_release.ps1` | Shared release implementation for CUDA / CPU / ROCm packages |
| `build_profile_runtime.ps1` | Shared runtime-cache builder for CUDA / CPU / ROCm packages |
| `runtime_profile_packaging.ps1` | Helper functions for package naming, config injection, checksums, and release notes |
| `check_runtime_profile_env.ps1` | Build-Python profile validation implementation |
| `validate_runtime_artifact.ps1` | Single artifact validator implementation |
| `validate_runtime_matrix.ps1` | Three-profile artifact matrix validator implementation |
| `build_sensevoice_model_package.ps1` | Optional SenseVoice model-cache package builder |
| `legacy/build_legacy.ps1` | Old one-profile build path; use only for historical troubleshooting |

CUDA Parakeet CTC JA is part of the CUDA profile only. Before building a CUDA
package with Parakeet enabled, the build Python must pass:

```powershell
.\check_runtime_profile_env.ps1 -Profile cuda
```

If `nemo.collections.asr.models` is missing, install:

```powershell
python -m pip install -r .\requirements_cuda_parakeet.txt
```

The model id is `grider-transwithai/parakeet-ctc-1.1b-ja`; the runtime loads
`parakeet-ja.nemo` from that HuggingFace repo with NVIDIA NeMo
`ASRModel.restore_from()`.

Validate built artifacts from `app`:

```powershell
.\validate_runtime_artifact.ps1 -Profile cuda
.\validate_runtime_artifact.ps1 -Profile cpu -ExpectedTorchBackend cpu
.\validate_runtime_artifact.ps1 -Profile rocm
```

CPU release builds require a CPU-only PyTorch build environment. CUDA or ROCm
torch must not be used to create the CPU runtime.

See `app/docs/PACKAGING_zh-TW.md` for the profile matrix, package names, and build Python requirements.
