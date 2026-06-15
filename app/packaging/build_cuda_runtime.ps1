#!/usr/bin/env pwsh
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$scriptDir = Split-Path -Parent $packagingDir
$runtimeCache = Join-Path $scriptDir "build-runtime-cache\cuda-runtime"
$manifestPath = Join-Path $runtimeCache "runtime-version.json"
$patchedPackage = Join-Path $scriptDir "..\stream-translator-gpt\stream_translator_gpt"
$pythonCandidates = @(
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
    throw "No usable build Python found. Set STREAM_TRANSLATOR_BUILD_PYTHON."
}

$requirementsHash = (Get-FileHash -Path (Join-Path $scriptDir "requirements.txt") -Algorithm SHA256).Hash
$fullRequirementsHash = (Get-FileHash -Path (Join-Path $scriptDir "requirements_full.txt") -Algorithm SHA256).Hash
$pythonRuntimeInfo = & $pythonExe -c "import sys, torch; print(sys.version); print(torch.__version__)"
$fingerprintSource = $requirementsHash + "`n" + $fullRequirementsHash + "`n" + ($pythonRuntimeInfo | Out-String)
$fingerprintBytes = [Text.Encoding]::UTF8.GetBytes($fingerprintSource)
$fingerprintStream = [IO.MemoryStream]::new($fingerprintBytes)
$fingerprint = (Get-FileHash -InputStream $fingerprintStream -Algorithm SHA256).Hash
$fingerprintStream.Dispose()

if (-not $Force -and (Test-Path $manifestPath)) {
    $existing = Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($existing.fingerprint -eq $fingerprint) {
        $cachedPackage = Join-Path $runtimeCache "Lib\site-packages\stream_translator_gpt"
        if (Test-Path $cachedPackage) { Remove-Item $cachedPackage -Recurse -Force }
        Copy-Item $patchedPackage $cachedPackage -Recurse -Force
        Write-Host "CUDA Runtime unchanged; using cache: $runtimeCache" -ForegroundColor Green
        exit 0
    }
}

Write-Host "Rebuilding clean CUDA Runtime..." -ForegroundColor Cyan
if (Test-Path $runtimeCache) { Remove-Item $runtimeCache -Recurse -Force }
New-Item $runtimeCache -ItemType Directory -Force | Out-Null

$pythonDir = Split-Path -Parent $pythonExe
$venvRoot = Split-Path -Parent $pythonDir
$pyvenvCfg = Join-Path $venvRoot "pyvenv.cfg"
if (Test-Path $pyvenvCfg) {
    $basePythonDir = ((Get-Content $pyvenvCfg | Where-Object { $_ -match '^home\s*=' }) -replace '^home\s*=\s*', '').Trim()
    $sourceSitePackages = Join-Path $venvRoot "Lib\site-packages"
} elseif (Test-Path (Join-Path $pythonDir "Lib\site-packages")) {
    $basePythonDir = $pythonDir
    $sourceSitePackages = Join-Path $pythonDir "Lib\site-packages"
} else {
    throw "Unsupported Python layout: $pythonExe"
}

foreach ($name in @("python.exe", "pythonw.exe", "python3.dll")) {
    $source = Join-Path $basePythonDir $name
    if (Test-Path $source) { Copy-Item $source $runtimeCache }
}
Get-ChildItem $basePythonDir -Filter "python*.dll" | Copy-Item -Destination $runtimeCache
Get-ChildItem $basePythonDir -Filter "vcruntime*.dll" -ErrorAction SilentlyContinue | Copy-Item -Destination $runtimeCache
Copy-Item (Join-Path $basePythonDir "DLLs") (Join-Path $runtimeCache "DLLs") -Recurse

$runtimeLib = Join-Path $runtimeCache "Lib"
New-Item $runtimeLib -ItemType Directory -Force | Out-Null
Get-ChildItem (Join-Path $basePythonDir "Lib") |
    Where-Object { $_.Name -ne "site-packages" } |
    ForEach-Object { Copy-Item $_.FullName $runtimeLib -Recurse -Force }

$runtimeSitePackages = Join-Path $runtimeLib "site-packages"
New-Item $runtimeSitePackages -ItemType Directory -Force | Out-Null
Copy-Item "$sourceSitePackages\*" $runtimeSitePackages -Recurse -Force

# The GUI ships Qt in _internal. The ASR subprocess does not need Qt, Gradio, or build tools.
$removePatterns = @(
    "PyQt6", "PyQt6-*.dist-info", "pyqt6_*.dist-info",
    "gradio", "gradio-*.dist-info", "gradio_client", "gradio_client-*.dist-info",
    "PyInstaller", "pyinstaller-*.dist-info", "_pytest", "pytest", "pytest-*.dist-info",
    "~orch", "~orch-*.dist-info", "__editable__*", "*.egg-link"
)
foreach ($pattern in $removePatterns) {
    Get-ChildItem $runtimeSitePackages -Filter $pattern -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
}

Get-ChildItem $runtimeCache -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem $runtimeCache -File -Include "*.pyc", "*.pyo", "*.lib" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force

$runtimePackage = Join-Path $runtimeSitePackages "stream_translator_gpt"
if (Test-Path $runtimePackage) { Remove-Item $runtimePackage -Recurse -Force }
Copy-Item $patchedPackage $runtimePackage -Recurse -Force

$pthName = (& $pythonExe -c "import sys; print(f'python{sys.version_info.major}{sys.version_info.minor}._pth')").Trim()
$pthContent = ".`r`nLib`r`nDLLs`r`nLib\site-packages`r`nimport site`r`n"
[IO.File]::WriteAllText((Join-Path $runtimeCache $pthName), $pthContent, [Text.Encoding]::ASCII)

$versionInfo = & $pythonExe -c "import json, sys, torch; print(json.dumps({'python': sys.version.split()[0], 'torch': torch.__version__}))"
$versions = $versionInfo | ConvertFrom-Json
[ordered]@{
    schema = 1
    fingerprint = $fingerprint
    python = $versions.python
    torch = $versions.torch
    created_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content $manifestPath -Encoding utf8

& (Join-Path $runtimeCache "python.exe") -c "import torch, qwen_asr, faster_whisper, whisper, omnivad; print('Runtime import check OK', torch.__version__)"
if ($LASTEXITCODE -ne 0) { throw "CUDA Runtime validation failed" }

$runtimeSize = (Get-ChildItem $runtimeCache -File -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("CUDA Runtime complete: {0:N2} GB" -f ($runtimeSize / 1GB)) -ForegroundColor Green
