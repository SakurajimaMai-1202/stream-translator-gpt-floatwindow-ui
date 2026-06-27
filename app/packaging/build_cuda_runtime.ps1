#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$scriptDir = Split-Path -Parent $packagingDir
$profileLabel = $Profile.ToUpperInvariant()
$runtimeCache = Join-Path $scriptDir "build-runtime-cache\$Profile-runtime"
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

$sourceRuntimeJson = & $pythonExe -c "import json, sys, torch; cuda = torch.version.cuda; hip = getattr(torch.version, 'hip', None); backend = 'rocm' if hip else ('cuda' if cuda else 'cpu'); print(json.dumps({'python': sys.version.split()[0], 'torch': torch.__version__, 'torch_backend': backend, 'cuda': cuda, 'hip': hip, 'cuda_available': torch.cuda.is_available(), 'device_count': torch.cuda.device_count()}))"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect torch in build Python: $pythonExe"
}
$sourceRuntime = $sourceRuntimeJson | ConvertFrom-Json

if ($Profile -eq "cuda" -and -not $sourceRuntime.cuda) {
    throw "CUDA profile requires a build Python with torch.version.cuda. Current torch backend: $($sourceRuntime.torch_backend)."
}
if ($Profile -eq "rocm" -and -not $sourceRuntime.hip) {
    throw "ROCm profile requires a build Python with torch.version.hip. Pass -Python to check_runtime_profile_env.ps1 or set STREAM_TRANSLATOR_BUILD_PYTHON to a ROCm/HIP torch runtime."
}
if ($Profile -eq "cpu" -and ($sourceRuntime.cuda -or $sourceRuntime.hip)) {
    Write-Warning "CPU profile is using a GPU-capable torch build. It is allowed, but a CPU torch build is smaller."
}

$requirementsHash = (Get-FileHash -Path (Join-Path $scriptDir "requirements.txt") -Algorithm SHA256).Hash
$fullRequirementsHash = (Get-FileHash -Path (Join-Path $scriptDir "requirements_full.txt") -Algorithm SHA256).Hash
$fingerprintSource = "runtime-schema=2`n" + $Profile + "`n" + $requirementsHash + "`n" + $fullRequirementsHash + "`n" + ($sourceRuntimeJson | Out-String)
$fingerprintBytes = [Text.Encoding]::UTF8.GetBytes($fingerprintSource)
$fingerprintStream = [IO.MemoryStream]::new($fingerprintBytes)
$fingerprint = (Get-FileHash -InputStream $fingerprintStream -Algorithm SHA256).Hash
$fingerprintStream.Dispose()

if (-not $Force -and (Test-Path $manifestPath)) {
    $existing = Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($existing.schema -eq 2 -and $existing.profile -eq $Profile -and $existing.fingerprint -eq $fingerprint) {
        $cachedPackage = Join-Path $runtimeCache "Lib\site-packages\stream_translator_gpt"
        if (Test-Path $cachedPackage) { Remove-Item $cachedPackage -Recurse -Force }
        Copy-Item $patchedPackage $cachedPackage -Recurse -Force
        Write-Host "$profileLabel Runtime unchanged; using cache: $runtimeCache" -ForegroundColor Green
        exit 0
    }
}

Write-Host "Rebuilding clean $profileLabel Runtime..." -ForegroundColor Cyan
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

$versionInfo = & $pythonExe -c "import json, sys, torch; cuda = torch.version.cuda; hip = getattr(torch.version, 'hip', None); backend = 'rocm' if hip else ('cuda' if cuda else 'cpu'); print(json.dumps({'python': sys.version.split()[0], 'torch': torch.__version__, 'torch_backend': backend, 'cuda': cuda, 'hip': hip, 'cuda_available': torch.cuda.is_available(), 'device_count': torch.cuda.device_count()}))"
$versions = $versionInfo | ConvertFrom-Json

$validationScript = @"
import importlib
import sys
import torch

profile = '$Profile'
required = ['qwen_asr']
if profile in ('cuda', 'cpu'):
    required.extend(['faster_whisper', 'whisper', 'omnivad'])

for name in required:
    importlib.import_module(name)

if profile == 'cuda' and not torch.version.cuda:
    raise SystemExit('CUDA profile requires a CUDA PyTorch runtime')
if profile == 'rocm' and not getattr(torch.version, 'hip', None):
    raise SystemExit('ROCm profile requires a ROCm/HIP PyTorch runtime')
if profile == 'cpu' and (torch.version.cuda or getattr(torch.version, 'hip', None)):
    print('Warning: CPU profile is using a GPU-capable torch build; package policy will still force CPU.', file=sys.stderr)

print(f'{profile.upper()} Runtime import check OK {torch.__version__}')
"@
& (Join-Path $runtimeCache "python.exe") -c $validationScript
if ($LASTEXITCODE -ne 0) { throw "$profileLabel Runtime validation failed" }

[ordered]@{
    schema = 2
    profile = $Profile
    fingerprint = $fingerprint
    python = $versions.python
    torch = $versions.torch
    torch_backend = $versions.torch_backend
    cuda = $versions.cuda
    hip = $versions.hip
    cuda_available = $versions.cuda_available
    device_count = $versions.device_count
    policy_forces_cpu = ($Profile -eq "cpu")
    created_at = (Get-Date).ToString("o")
} | ConvertTo-Json | ForEach-Object {
    [IO.File]::WriteAllText($manifestPath, $_ + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

$runtimeSize = (Get-ChildItem $runtimeCache -File -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("{0} Runtime complete: {1:N2} GB" -f $profileLabel, ($runtimeSize / 1GB)) -ForegroundColor Green
