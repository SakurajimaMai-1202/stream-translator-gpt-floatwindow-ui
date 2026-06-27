#!/usr/bin/env pwsh
param(
    [switch]$AllowMissingRocm,
    [ValidateSet("auto", "cuda", "cpu", "rocm")]
    [string]$CpuExpectedTorchBackend = "auto"
)

$argsForScript = @{ CpuExpectedTorchBackend = $CpuExpectedTorchBackend }
if ($AllowMissingRocm) { $argsForScript.AllowMissingRocm = $true }
& (Join-Path $PSScriptRoot "packaging\validate_runtime_matrix.ps1") @argsForScript
exit $LASTEXITCODE
