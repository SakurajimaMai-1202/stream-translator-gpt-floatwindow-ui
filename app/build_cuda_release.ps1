#!/usr/bin/env pwsh
param(
    [switch]$ForceRuntime,
    [switch]$SkipFullZip
)

& (Join-Path $PSScriptRoot "packaging\build_cuda_release.ps1") @PSBoundParameters
exit $LASTEXITCODE
