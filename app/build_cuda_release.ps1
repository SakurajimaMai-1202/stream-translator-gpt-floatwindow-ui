#!/usr/bin/env pwsh
param(
    [switch]$ForceRuntime,
    [switch]$SkipFullZip
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$frontendDir = Join-Path $scriptDir "frontend"
$distDir = Join-Path $scriptDir "dist-cuda"
$pyInstallerDist = Join-Path $scriptDir "build-gui-dist"
$pyInstallerWork = Join-Path $scriptDir "build-gui"
$appName = "Stream Translator"
$releaseRoot = Join-Path $distDir $appName
$runtimeCache = Join-Path $scriptDir "build-runtime-cache\cuda-runtime"
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
    & $candidate -c "import PyInstaller, sys; print(sys.executable)" *> $null
    $candidateExitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($candidateExitCode -eq 0) {
        $pythonExe = (Resolve-Path $candidate).Path
        break
    }
}
if (-not $pythonExe) { throw "No usable build Python with PyInstaller found" }

Write-Host "[1/6] Build frontend" -ForegroundColor Yellow
Push-Location $frontendDir
try {
    if (-not (Test-Path "node_modules")) { npm install }
    npx vite build
    if ($LASTEXITCODE -ne 0) { throw "Vite build failed" }
} finally { Pop-Location }

Write-Host "[2/6] Build GUI onedir" -ForegroundColor Yellow
Push-Location $scriptDir
try {
    & $pythonExe -m PyInstaller "stream-translator-llm-gui.spec" --noconfirm --distpath $pyInstallerDist --workpath $pyInstallerWork
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
} finally { Pop-Location }

$builtApp = Join-Path $pyInstallerDist $appName
Get-ChildItem $builtApp -File -Filter "qtwebengine_devtools_resources.debug.pak" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force

Write-Host "[3/6] Build or reuse CUDA Runtime" -ForegroundColor Yellow
$runtimeArgs = @()
if ($ForceRuntime) { $runtimeArgs += "-Force" }
& (Join-Path $scriptDir "build_cuda_runtime.ps1") @runtimeArgs
if ($LASTEXITCODE -ne 0) { throw "Runtime build failed" }

Write-Host "[4/6] Create App Update package" -ForegroundColor Yellow
if (Test-Path $distDir) { Remove-Item $distDir -Recurse -Force }
New-Item $distDir -ItemType Directory -Force | Out-Null
$updateRoot = Join-Path $distDir "App-Update"
Copy-Item $builtApp $updateRoot -Recurse
$updatePackageDir = Join-Path $updateRoot "_runtime\Lib\site-packages"
New-Item $updatePackageDir -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $projectRoot "stream-translator-gpt\stream_translator_gpt") $updatePackageDir -Recurse -Force
Copy-Item (Join-Path $scriptDir "PORTABLE_GUIDE_zh-TW.txt") $updateRoot
Copy-Item (Join-Path $scriptDir "UPDATE_NOTES_zh-TW.txt") $updateRoot -ErrorAction SilentlyContinue
Push-Location $distDir
try { & tar.exe -a -c -f "StreamTranslator-CUDA-App-Update.zip" "App-Update" } finally { Pop-Location }

Write-Host "[5/6] Assemble first-use full package" -ForegroundColor Yellow
Copy-Item $builtApp $releaseRoot -Recurse
Copy-Item $runtimeCache (Join-Path $releaseRoot "_runtime") -Recurse
New-Item (Join-Path $releaseRoot "models\huggingface\hub") -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $scriptDir "config.example.yaml") (Join-Path $releaseRoot "config.yaml")
Copy-Item (Join-Path $scriptDir "PORTABLE_GUIDE_zh-TW.txt") $releaseRoot
Copy-Item (Join-Path $scriptDir "UPDATE_NOTES_zh-TW.txt") $releaseRoot -ErrorAction SilentlyContinue

$ffmpegSource = Join-Path $projectRoot "ffmpeg-8.1-essentials_build\ffmpeg-8.1-essentials_build\bin"
$ffmpegTarget = Join-Path $releaseRoot "ffmpeg\bin"
New-Item $ffmpegTarget -ItemType Directory -Force | Out-Null
foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
    $source = Join-Path $ffmpegSource $name
    if (Test-Path $source) { Copy-Item $source $ffmpegTarget }
}

$llamaSource = Join-Path $projectRoot "llama"
if (Test-Path $llamaSource) {
    $llamaTarget = Join-Path $releaseRoot "llama"
    New-Item $llamaTarget -ItemType Directory -Force | Out-Null
    Get-ChildItem $llamaSource -File | Where-Object { $_.Extension -in @('.exe', '.dll') } |
        Copy-Item -Destination $llamaTarget
}

if (-not $SkipFullZip) {
    Write-Host "[6/6] Compress full package" -ForegroundColor Yellow
    Push-Location $distDir
    try { & tar.exe -a -c -f "StreamTranslator-CUDA-Full.zip" $appName } finally { Pop-Location }
} else {
    Write-Host "[6/6] Full package compression skipped" -ForegroundColor DarkYellow
}

Get-ChildItem $distDir -File | ForEach-Object {
    [pscustomobject]@{ Name = $_.Name; GB = [math]::Round($_.Length / 1GB, 3) }
} | Format-Table -AutoSize
Write-Host "CUDA release complete: $distDir" -ForegroundColor Green
