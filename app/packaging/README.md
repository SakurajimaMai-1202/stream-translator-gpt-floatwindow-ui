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
.\build_all_profiles.ps1 -Version 1.4.2 -Mode Quick -ReuseRuntimeCache
.\build_all_profiles.ps1 -Version 1.4.2 -Mode Final -ReuseRuntimeCache -CompressionLevel 7 -SplitSizeMiB 1900
```

After a packaging-stage failure, keep a previously completed shared GUI and
resume without rerunning Vite/PyInstaller:

```powershell
.\build_all_profiles.ps1 -Version 1.4.2 -Mode Quick -ReuseRuntimeCache -ReuseSharedGui
```

If all three profile folders and App Update archives already passed their
individual builds, resume only validation and asset collection:

```powershell
.\build_all_profiles.ps1 -Version 1.4.2 -Mode Quick -ReuseSharedGui -ReuseProfileArtifacts
```

`Quick` builds the shared GUI once, validates and assembles all three profile
folders, and creates core-only App Update archives without compressing Full
packages or copying unchanged ASR runtime dependencies.
`Final` additionally creates standard Deflate ZIP files with multithreaded
7-Zip, splits each Full ZIP into `.partNN` files, recombines the parts, checks
the original/recombined SHA256, tests the recombined ZIP, and writes a release
manifest plus checksum file.

Starting with v1.3.10, all three Full packages intentionally exclude the
`llama` folder. The application downloads and manages the llama.cpp Runtime on
demand, so an obsolete bundled server is never shipped with a profile package.

App Update manifests use schema 2 and declare one of two modes:

- `app_only` (default) places `Stream Translator.exe`, `_internal`,
  `_js_runtime`, and the updater at the ZIP root. It must not contain
  `_runtime`, so the installed CPU/CUDA/ROCm runtime is preserved verbatim.
- `runtime_replace` also includes a complete profile-matched `_runtime` with
  `python.exe` and `runtime-version.json`. The updater swaps that directory as
  one rollback unit. Use `-UpdateMode runtime_replace` when Python, Torch,
  CUDA/ROCm, ONNX Runtime, or another ABI-sensitive dependency changes.

The CPU ASR sidecar remains independently managed. Full archives keep their
profile package directory as the ZIP root.

GUI builds always pass PyInstaller `--clean`. The fixed work directory must not
reuse an older Analysis result, otherwise a newly built Vite bundle can be
silently omitted from the packaged executable.

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

NVIDIA Parakeet is part of the CUDA profile only. Before building a CUDA
package with Parakeet enabled, the build Python must pass:

```powershell
.\check_runtime_profile_env.ps1 -Profile cuda
```

If `nemo.collections.asr.models` is missing, install:

```powershell
python -m pip install -r .\requirements_cuda_parakeet.txt
```

Official model ids are `nvidia/parakeet-tdt_ctc-0.6b-ja` and
`nvidia/parakeet-tdt_ctc-1.1b`; NVIDIA NeMo loads these through
`ASRModel.from_pretrained()`. The legacy
`grider-transwithai/parakeet-ctc-1.1b-ja` option still loads `parakeet-ja.nemo`
with `ASRModel.restore_from()`. The official model cards specify CC-BY-4.0.

Validate built artifacts from `app`:

```powershell
.\validate_runtime_artifact.ps1 -Profile cuda
.\validate_runtime_artifact.ps1 -Profile cpu -ExpectedTorchBackend none
.\validate_runtime_artifact.ps1 -Profile rocm
```

CPU release builds require a Python environment containing
`requirements_cpu_sherpa.txt`. The CPU ASR runtime uses sherpa-onnx INT8 and
removes PyTorch, NeMo, FunASR, Transformers, Whisper, CUDA, and ROCm packages.

CUDA and ROCm full packages include the isolated `_runtime_cpu_asr` sidecar by
default, so users can switch between the packaged GPU runtime and sherpa-onnx
CPU ASR without another install. Build all profiles with:

```powershell
.\build_all_profiles.ps1 -Version 1.4.2 -Mode Final
```

For a deliberately smaller GPU-only artifact, opt out explicitly with
`-IncludeCpuAsrSidecar:$false`. Artifact validation should use
`validate_runtime_artifact.ps1 -Profile <cuda|rocm> -RequireCpuAsrSidecar` for
the standard full packages.

See `app/docs/PACKAGING_zh-TW.md` for the profile matrix, package names, and build Python requirements.
