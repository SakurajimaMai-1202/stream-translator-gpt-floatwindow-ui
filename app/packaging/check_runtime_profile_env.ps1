#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [string]$Python
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$scriptDir = Split-Path -Parent $packagingDir

$pythonCandidates = @(
    $Python,
    $env:STREAM_TRANSLATOR_BUILD_PYTHON,
    (Join-Path $scriptDir "venv\Scripts\python.exe"),
    (Join-Path $scriptDir "..\.venv\Scripts\python.exe"),
    (Join-Path $scriptDir "dist-hotfix\Stream Translator\_runtime\python.exe"),
    (Join-Path $scriptDir "dist\Stream Translator\_runtime\python.exe")
) | Where-Object { $_ -and (Test-Path $_) }

$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $candidate -c "import sys; print(sys.executable)" *> $null
    $candidateExitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($candidateExitCode -eq 0) {
        $pythonExe = (Resolve-Path $candidate).Path
        break
    }
}

if (-not $pythonExe) {
    throw "No usable Python found. Pass -Python or set STREAM_TRANSLATOR_BUILD_PYTHON."
}

$probeScript = @"
import importlib.util
import json
import sys

info = {
    'executable': sys.executable,
    'python': sys.version.split()[0],
    'profile': '$Profile',
}

try:
    import torch
    info.update({
        'torch': torch.__version__,
        'cuda': torch.version.cuda,
        'hip': getattr(torch.version, 'hip', None),
        'cuda_available': torch.cuda.is_available(),
        'device_count': torch.cuda.device_count(),
    })
except Exception as exc:
    info['torch_error'] = repr(exc)

info['pyinstaller'] = importlib.util.find_spec('PyInstaller') is not None
info['qwen_asr'] = importlib.util.find_spec('qwen_asr') is not None
info['faster_whisper'] = importlib.util.find_spec('faster_whisper') is not None
print(json.dumps(info, ensure_ascii=False))
"@

$json = & $pythonExe -c $probeScript
if ($LASTEXITCODE -ne 0) {
    throw "Python runtime probe failed: $pythonExe"
}

$info = $json | ConvertFrom-Json
$errors = @()

if (-not $info.torch) {
    $errors += "torch is not importable"
}
if (-not $info.pyinstaller) {
    $errors += "PyInstaller is not importable"
}
if (-not $info.qwen_asr) {
    $errors += "qwen_asr is not importable"
}
if ($Profile -in @("cuda", "cpu") -and -not $info.faster_whisper) {
    $errors += "faster_whisper is required for $Profile profile"
}
if ($Profile -eq "cuda" -and -not $info.cuda) {
    $errors += "CUDA profile requires torch.version.cuda. Use a CUDA torch build Python."
}
if ($Profile -eq "rocm" -and -not $info.hip) {
    $errors += "ROCm profile requires torch.version.hip. Use -Python or STREAM_TRANSLATOR_BUILD_PYTHON to point at a ROCm/HIP torch runtime."
}
if ($Profile -eq "cpu" -and ($info.cuda -or $info.hip)) {
    Write-Warning "CPU profile is using a GPU-capable torch build. It is allowed, but a CPU torch build is smaller."
}

$info | Format-List

if ($errors.Count -gt 0) {
    throw "Runtime profile environment is not ready for '$Profile': $($errors -join '; ')"
}

Write-Host "Runtime profile environment OK for '$Profile': $pythonExe" -ForegroundColor Green
