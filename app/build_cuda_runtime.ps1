#!/usr/bin/env pwsh
param(
    [switch]$Force
)

Write-Host "build_cuda_runtime.ps1 is a compatibility alias. Prefer: .\build_runtime.ps1 -Profile cuda" -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "packaging\build_profile_runtime.ps1") -Profile cuda @PSBoundParameters
exit $LASTEXITCODE
