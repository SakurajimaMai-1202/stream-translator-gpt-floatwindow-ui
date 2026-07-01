#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [string]$Version = "1.3.2",
    [switch]$ForceRuntime,
    [switch]$SkipFullZip
)

$releaseArgs = @{ Profile = $Profile; Version = $Version }
if ($ForceRuntime) { $releaseArgs.ForceRuntime = $true }
if ($SkipFullZip) { $releaseArgs.SkipFullZip = $true }
& (Join-Path $PSScriptRoot "build_cuda_release.ps1") @releaseArgs
exit $LASTEXITCODE
