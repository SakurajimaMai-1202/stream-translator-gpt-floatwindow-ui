#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [ValidateSet("auto", "cuda", "cpu", "rocm", "none")]
    [string]$ExpectedTorchBackend = "auto",
    [switch]$RequireCpuAsrSidecar
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$scriptDir = Split-Path -Parent $packagingDir
. (Join-Path $packagingDir "runtime_profile_packaging.ps1")

$packageInfo = Get-RuntimeProfilePackageInfo -RuntimeProfile $Profile
$distDir = Join-Path $scriptDir $packageInfo.DistDirName
$packageDir = Join-Path $distDir $packageInfo.PackageName
$configPath = Join-Path $packageDir "config.yaml"
$runtimeManifestPath = Join-Path $packageDir "_runtime\runtime-version.json"
$appUpdateZip = Join-Path $distDir $packageInfo.AppUpdateZip
$nodeRuntimePath = Join-Path $packageDir "_js_runtime\node.exe"

if ($ExpectedTorchBackend -eq "auto") {
    if ($Profile -eq "rocm") {
        $ExpectedTorchBackend = "rocm"
    } elseif ($Profile -eq "cuda") {
        $ExpectedTorchBackend = "cuda"
    } elseif ($Profile -eq "cpu") {
        $ExpectedTorchBackend = "none"
    }
}

foreach ($requiredPath in @($distDir, $packageDir, $configPath, $runtimeManifestPath, $appUpdateZip, $nodeRuntimePath)) {
    if (-not (Test-Path $requiredPath)) {
        throw "Missing runtime artifact path: $requiredPath"
    }
}

$configText = Get-Content $configPath -Raw -Encoding utf8
$expectedPolicy = if ($Profile -eq "cpu") { "cpu" } else { "auto_discrete" }
if ($configText -notmatch "(?m)^runtime:\s*$") {
    throw "config.yaml missing runtime block: $configPath"
}
if ($configText -notmatch "(?m)^  profile:\s*$Profile\s*$") {
    throw "config.yaml runtime.profile is not '$Profile': $configPath"
}
if ($configText -notmatch "(?m)^  device_policy:\s*$expectedPolicy\s*$") {
    throw "config.yaml runtime.device_policy is not '$expectedPolicy': $configPath"
}

$manifest = Get-Content $runtimeManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$expectedSchema = if ($Profile -eq "cpu") { 3 } else { 2 }
if ($manifest.schema -ne $expectedSchema) {
    throw "runtime manifest schema is not $expectedSchema`: $runtimeManifestPath"
}
if ($manifest.profile -ne $Profile) {
    throw "runtime manifest profile is '$($manifest.profile)', expected '$Profile': $runtimeManifestPath"
}
if ($ExpectedTorchBackend -ne "auto" -and $manifest.torch_backend -ne $ExpectedTorchBackend) {
    throw "runtime manifest torch_backend is '$($manifest.torch_backend)', expected '$ExpectedTorchBackend': $runtimeManifestPath"
}
$expectedPolicyForcesCpu = $Profile -eq "cpu"
if ([bool]$manifest.policy_forces_cpu -ne $expectedPolicyForcesCpu) {
    throw "runtime manifest policy_forces_cpu is '$($manifest.policy_forces_cpu)', expected '$expectedPolicyForcesCpu': $runtimeManifestPath"
}
if ($Profile -eq "cuda" -and -not $manifest.cuda) {
    throw "CUDA artifact manifest missing cuda version: $runtimeManifestPath"
}
if ($Profile -eq "rocm" -and -not $manifest.hip) {
    throw "ROCm artifact manifest missing hip version: $runtimeManifestPath"
}
if ($Profile -eq "cpu" -and -not $manifest.sherpa_onnx) {
    throw "CPU artifact manifest missing sherpa-onnx version: $runtimeManifestPath"
}
if ((& $nodeRuntimePath --version) -notmatch '^v(2[2-9]|[3-9][0-9])\.') {
    throw "Packaged Node.js runtime must be version 22 or newer: $nodeRuntimePath"
}

$cpuAsrSidecar = $null
if ($Profile -ne "cpu") {
    $cpuAsrRuntimePath = Join-Path $packageDir "_runtime_cpu_asr"
    if ($RequireCpuAsrSidecar -and -not (Test-Path -LiteralPath $cpuAsrRuntimePath -PathType Container)) {
        throw "CPU ASR sidecar is required but missing: $cpuAsrRuntimePath"
    }
    if (Test-Path -LiteralPath $cpuAsrRuntimePath -PathType Container) {
        $cpuAsrPython = Join-Path $cpuAsrRuntimePath "python.exe"
        $cpuAsrManifestPath = Join-Path $cpuAsrRuntimePath "runtime-version.json"
        foreach ($requiredSidecarPath in @($cpuAsrPython, $cpuAsrManifestPath)) {
            if (-not (Test-Path -LiteralPath $requiredSidecarPath -PathType Leaf)) {
                throw "CPU ASR sidecar path is missing: $requiredSidecarPath"
            }
        }
        $cpuAsrManifest = Get-Content $cpuAsrManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($cpuAsrManifest.profile -ne "cpu" -or $cpuAsrManifest.torch_backend -ne "none" -or -not $cpuAsrManifest.sherpa_onnx) {
            throw "CPU ASR sidecar manifest is invalid: $cpuAsrManifestPath"
        }
        & $cpuAsrPython -I -c "import glob, pathlib, importlib.util, sherpa_onnx, stream_translator_gpt.main, sys; from pathlib import Path; root=Path(sys.executable).resolve().parent; paths=[Path(pathlib.__file__).resolve(), Path(glob.__file__).resolve()]; assert all(root == p.parent or root in p.parents for p in paths), paths; assert importlib.util.find_spec('torch') is None, 'CPU ASR sidecar must not include torch'; print(sherpa_onnx.__version__)"
        if ($LASTEXITCODE -ne 0) { throw "CPU ASR sidecar runtime validation failed: $cpuAsrRuntimePath" }
        $cpuAsrSidecar = $cpuAsrManifest.sherpa_onnx
    }
}

[pscustomobject]@{
    Profile = $Profile
    Package = $packageInfo.PackageName
    DistDir = $distDir
    AppUpdateZip = $packageInfo.AppUpdateZip
    TorchBackend = $manifest.torch_backend
    Torch = $manifest.torch
    SherpaOnnx = $manifest.sherpa_onnx
    CpuAsrSidecar = $cpuAsrSidecar
    Cuda = $manifest.cuda
    Hip = $manifest.hip
    PolicyForcesCpu = [bool]$manifest.policy_forces_cpu
} | Format-List

Write-Host "Runtime artifact OK for '$Profile': $packageDir" -ForegroundColor Green
