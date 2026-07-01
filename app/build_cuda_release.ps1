#!/usr/bin/env pwsh
param(
    [string]$Version = "1.3.3",
    [switch]$ForceRuntime,
    [switch]$SkipFullZip
)

$releaseArgs = @{ Profile = "cuda"; Version = $Version }
if ($ForceRuntime) { $releaseArgs.ForceRuntime = $true }
if ($SkipFullZip) { $releaseArgs.SkipFullZip = $true }
& (Join-Path $PSScriptRoot "packaging\build_cuda_release.ps1") @releaseArgs
exit $LASTEXITCODE
