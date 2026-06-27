#!/usr/bin/env pwsh
param(
    [switch]$Force
)

& (Join-Path $PSScriptRoot "packaging\build_cuda_runtime.ps1") -Profile cuda @PSBoundParameters
exit $LASTEXITCODE
