#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [ValidateSet("auto", "cuda", "cpu", "rocm")]
    [string]$ExpectedTorchBackend = "auto"
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

if ($ExpectedTorchBackend -eq "auto") {
    if ($Profile -eq "rocm") {
        $ExpectedTorchBackend = "rocm"
    } elseif ($Profile -eq "cuda") {
        $ExpectedTorchBackend = "cuda"
    }
}

foreach ($requiredPath in @($distDir, $packageDir, $configPath, $runtimeManifestPath, $appUpdateZip)) {
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
if ($manifest.schema -ne 2) {
    throw "runtime manifest schema is not 2: $runtimeManifestPath"
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

[pscustomobject]@{
    Profile = $Profile
    Package = $packageInfo.PackageName
    DistDir = $distDir
    AppUpdateZip = $packageInfo.AppUpdateZip
    TorchBackend = $manifest.torch_backend
    Torch = $manifest.torch
    Cuda = $manifest.cuda
    Hip = $manifest.hip
    PolicyForcesCpu = [bool]$manifest.policy_forces_cpu
} | Format-List

Write-Host "Runtime artifact OK for '$Profile': $packageDir" -ForegroundColor Green
