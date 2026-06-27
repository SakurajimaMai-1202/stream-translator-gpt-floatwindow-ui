#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [ValidateSet("auto", "cuda", "cpu", "rocm")]
    [string]$ExpectedTorchBackend = "auto"
)

$argsForScript = @{
    Profile = $Profile
    ExpectedTorchBackend = $ExpectedTorchBackend
}
& (Join-Path $PSScriptRoot "packaging\validate_runtime_artifact.ps1") @argsForScript
exit $LASTEXITCODE
