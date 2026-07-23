#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [string]$Version = "1.3.5",
    [switch]$ForceRuntime,
    [switch]$ReuseRuntimeCache,
    [switch]$SkipFullZip
)

$releaseArgs = @{ Profile = $Profile; Version = $Version }
if ($ForceRuntime) { $releaseArgs.ForceRuntime = $true }
if ($ReuseRuntimeCache) { $releaseArgs.ReuseRuntimeCache = $true }
if ($SkipFullZip) { $releaseArgs.SkipFullZip = $true }
& (Join-Path $PSScriptRoot "packaging\build_profile_release.ps1") @releaseArgs
exit $LASTEXITCODE
