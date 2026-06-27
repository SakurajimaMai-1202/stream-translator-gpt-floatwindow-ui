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
