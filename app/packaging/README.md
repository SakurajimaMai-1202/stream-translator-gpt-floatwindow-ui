# Packaging

Use `app/build_release.ps1` for normal release builds:

```powershell
.\build_release.ps1 -Profile cuda
.\build_release.ps1 -Profile cpu
.\build_release.ps1 -Profile rocm
```

The legacy CUDA wrappers are still available:

```powershell
.\build_cuda_release.ps1
.\build_cuda_runtime.ps1
```

They are compatibility aliases for `-Profile cuda`.

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
.\validate_runtime_artifact.ps1 -Profile cpu -ExpectedTorchBackend cuda
.\validate_runtime_artifact.ps1 -Profile rocm
```

For the current CUDA+CPU-only development state:

```powershell
.\validate_runtime_matrix.ps1 -CpuExpectedTorchBackend cuda -AllowMissingRocm
```

See `app/docs/PACKAGING_zh-TW.md` for the profile matrix, package names, and build Python requirements.
