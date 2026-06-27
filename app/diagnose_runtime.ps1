#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [ValidateSet("auto_discrete", "auto_any", "manual", "cpu")]
    [string]$DevicePolicy = "",
    [switch]$AllowIntegratedGpu,
    [switch]$NoTorchSmoke,
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir

if (-not $DevicePolicy) {
    $DevicePolicy = if ($Profile -eq "cpu") { "cpu" } else { "auto_discrete" }
}

if (-not $Output) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Output = Join-Path (Get-Location) "runtime-diagnostics-$Profile-$timestamp.json"
}

$pythonCandidates = @(
    (Join-Path $scriptDir "_runtime\python.exe"),
    (Join-Path $scriptDir "build-runtime-cache\$Profile-runtime\python.exe"),
    $env:STREAM_TRANSLATOR_BUILD_PYTHON,
    (Join-Path $scriptDir "venv\Scripts\python.exe"),
    (Join-Path $repoRoot ".venv\Scripts\python.exe")
) | Where-Object { $_ -and (Test-Path $_) }

$pythonExe = $pythonCandidates | Select-Object -First 1
if (-not $pythonExe) {
    throw "No runtime Python found. Run from a packaged folder or set STREAM_TRANSLATOR_BUILD_PYTHON."
}

$packageSource = Join-Path $repoRoot "stream-translator-gpt"
if (Test-Path $packageSource) {
    $env:PYTHONPATH = if ($env:PYTHONPATH) { "$packageSource;$env:PYTHONPATH" } else { $packageSource }
}

$argsForPython = @(
    "-m", "stream_translator_gpt.runtime_diagnostics",
    "--profile", $Profile,
    "--device-policy", $DevicePolicy,
    "--output", $Output
)
if ($AllowIntegratedGpu) { $argsForPython += "--allow-integrated-gpu" }
if ($NoTorchSmoke) { $argsForPython += "--no-torch-smoke" }

& $pythonExe @argsForPython
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Runtime diagnostics written to: $Output" -ForegroundColor Green
