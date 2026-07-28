#!/usr/bin/env pwsh
param(
    [string]$Version = "1.3.7",
    [switch]$ForceRuntime,
    [switch]$ReuseRuntimeCache,
    [switch]$SkipFullZip
)

$releaseArgs = @{ Profile = "cuda"; Version = $Version }
if ($ForceRuntime) { $releaseArgs.ForceRuntime = $true }
if ($ReuseRuntimeCache) { $releaseArgs.ReuseRuntimeCache = $true }
if ($SkipFullZip) { $releaseArgs.SkipFullZip = $true }
Write-Host "build_cuda_release.ps1 is a compatibility alias. Prefer: .\build_release.ps1 -Profile cuda" -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "packaging\build_profile_release.ps1") @releaseArgs
exit $LASTEXITCODE
