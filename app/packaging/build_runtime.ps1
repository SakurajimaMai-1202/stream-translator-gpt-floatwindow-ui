#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [switch]$Force
)

$runtimeArgs = @{ Profile = $Profile }
if ($Force) { $runtimeArgs.Force = $true }
& (Join-Path $PSScriptRoot "build_cuda_runtime.ps1") @runtimeArgs
exit $LASTEXITCODE
