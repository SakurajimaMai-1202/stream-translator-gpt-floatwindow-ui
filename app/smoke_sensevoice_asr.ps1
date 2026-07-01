#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory = $true)]
    [string]$Audio,
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cpu",
    [ValidateSet("auto_discrete", "auto_any", "manual", "cpu")]
    [string]$DevicePolicy = "",
    [string]$Model = "iic/SenseVoiceSmall",
    [string]$Language = "auto",
    [switch]$AllowIntegratedGpu
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir

if (-not (Test-Path $Audio)) {
    throw "Audio file not found: $Audio"
}

if (-not $DevicePolicy) {
    $DevicePolicy = if ($Profile -eq "cpu") { "cpu" } else { "auto_discrete" }
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

$modelRoot = Join-Path $scriptDir "models\huggingface"
$hfHub = Join-Path $modelRoot "hub"
$modelScope = Join-Path $modelRoot "modelscope"
New-Item -ItemType Directory -Force -Path $hfHub, $modelScope | Out-Null
$env:HF_HOME = $modelRoot
$env:HUGGINGFACE_HUB_CACHE = $hfHub
$env:TRANSFORMERS_CACHE = $hfHub
$env:MODELSCOPE_CACHE = $modelScope

$allowIntegrated = if ($AllowIntegratedGpu) { "1" } else { "0" }
$smokeScript = @"
import json
import sys

package_source = r'''$packageSource'''
if package_source and package_source not in sys.path:
    sys.path.insert(0, package_source)

import numpy as np
from scipy.io import wavfile

from stream_translator_gpt.audio_transcriber import SenseVoiceTranscriber
from stream_translator_gpt.runtime_accelerator import resolve_qwen3_device_map

audio_path = r'''$Audio'''
profile = '''$Profile'''
policy = '''$DevicePolicy'''
allow_integrated = '''$allowIntegrated''' == '1'
model = r'''$Model'''
language = '''$Language'''

try:
    import torch
    device = resolve_qwen3_device_map(
        torch,
        'auto',
        runtime_profile=profile,
        device_policy=policy,
        allow_integrated_gpu=allow_integrated,
    )
except Exception as exc:
    print(json.dumps({'ok': False, 'stage': 'device', 'error': repr(exc)}, ensure_ascii=False))
    raise

sample_rate, audio = wavfile.read(audio_path)
if sample_rate != 16000:
    raise SystemExit(f'SenseVoice smoke test expects a 16 kHz WAV file, got {sample_rate} Hz: {audio_path}')
if audio.ndim > 1:
    audio = audio.mean(axis=1)
audio = audio.astype(np.float32)
peak = float(np.max(np.abs(audio))) if audio.size else 0.0
if peak > 1.0:
    audio = audio / max(peak, 1.0)

transcriber = SenseVoiceTranscriber(model=model, language=language, device=device, print_result=False)
text, _ = transcriber.transcribe(audio)
print(json.dumps({'ok': True, 'profile': profile, 'device': device, 'model': model, 'text': text}, ensure_ascii=False))
"@

& $pythonExe -c $smokeScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
