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

Build all three profiles from one shared frontend/PyInstaller GUI artifact:

```powershell
.\build_all_profiles.ps1 -Version 1.3.6 -Mode Quick -ReuseRuntimeCache
.\build_all_profiles.ps1 -Version 1.3.6 -Mode Final -ReuseRuntimeCache -CompressionLevel 7 -SplitSizeMiB 1900
```

After a packaging-stage failure, keep a previously completed shared GUI and
resume without rerunning Vite/PyInstaller:

```powershell
.\build_all_profiles.ps1 -Version 1.3.6 -Mode Quick -ReuseRuntimeCache -ReuseSharedGui
```

If all three profile folders and App Update archives already passed their
individual builds, resume only validation and asset collection:

```powershell
.\build_all_profiles.ps1 -Version 1.3.6 -Mode Quick -ReuseSharedGui -ReuseProfileArtifacts
```

`Quick` builds the shared GUI once, validates and assembles all three profile
folders, and creates core-only App Update archives without compressing Full
packages or copying unchanged ASR runtime dependencies.
`Final` additionally creates standard Deflate ZIP files with multithreaded
7-Zip, splits each Full ZIP into `.partNN` files, recombines the parts, checks
the original/recombined SHA256, tests the recombined ZIP, and writes a release
manifest plus checksum file.

The three-profile command always reuses and validates the existing
`cuda-runtime`, `cpu-runtime`, and `rocm-runtime` caches. Rebuild a changed
runtime separately with the correct profile-specific Build Python before
running the unified release command.

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
| `../build_all_profiles.ps1` | Build one shared GUI and assemble/verify all three release profiles |
| `build_shared_gui.ps1` | Build the shared Vite and PyInstaller GUI artifact once |
| `build_profile_release.ps1` | Shared release implementation for CUDA / CPU / ROCm packages |
| `build_profile_runtime.ps1` | Shared runtime-cache builder for CUDA / CPU / ROCm packages |
| `release_build_tools.ps1` | Robocopy, 7-Zip, split/recombine, archive validation, and hash helpers |
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
