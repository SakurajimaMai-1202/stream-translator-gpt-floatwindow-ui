#!/usr/bin/env pwsh
param(
    [string]$Version = "1.3.4",
    [switch]$ForceRuntime,
    [switch]$SkipFullZip
)

$releaseArgs = @{ Profile = "cuda"; Version = $Version }
if ($ForceRuntime) { $releaseArgs.ForceRuntime = $true }
if ($SkipFullZip) { $releaseArgs.SkipFullZip = $true }
Write-Host "build_cuda_release.ps1 is a compatibility alias. Prefer: .\build_release.ps1 -Profile cuda" -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "packaging\build_profile_release.ps1") @releaseArgs
exit $LASTEXITCODE
