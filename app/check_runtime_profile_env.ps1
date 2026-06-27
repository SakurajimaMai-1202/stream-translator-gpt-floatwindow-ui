#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [string]$Python
)

$argsForScript = @{ Profile = $Profile }
if ($Python) { $argsForScript.Python = $Python }
& (Join-Path $PSScriptRoot "packaging\check_runtime_profile_env.ps1") @argsForScript
exit $LASTEXITCODE
