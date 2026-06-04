#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$appName = "RemoteSubtitleWindow"
$entry = Join-Path $scriptDir "remote_subtitle_window.py"
$distDir = Join-Path $scriptDir "dist"
$buildDir = Join-Path $scriptDir "build"
$venvDir = Join-Path $scriptDir ".build-venv"
$python = Join-Path $venvDir "Scripts\python.exe"

Write-Host "=== Remote Subtitle Window build ===" -ForegroundColor Cyan

if (-not (Test-Path $entry)) {
    throw "Entry file not found: $entry"
}

if (-not (Test-Path $python)) {
    Write-Host "[1/4] Create build virtualenv" -ForegroundColor Yellow
    python -m venv $venvDir
}

Write-Host "[2/4] Ensure PyInstaller" -ForegroundColor Yellow
& $python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install pyinstaller --quiet
}

Write-Host "[3/4] Clean previous build" -ForegroundColor Yellow
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir -ErrorAction SilentlyContinue }
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue }

Write-Host "[4/4] Build one-file exe" -ForegroundColor Yellow
& $python -m PyInstaller `
    --onefile `
    --windowed `
    --clean `
    --icon "app_icon.ico" `
    --name $appName `
    --distpath $distDir `
    --workpath $buildDir `
    $entry

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed"
}

$exe = Join-Path $distDir "$appName.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished but exe was not found: $exe"
}

Write-Host ""
Write-Host "Build completed:" -ForegroundColor Green
Write-Host "  $exe" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run example:" -ForegroundColor White
Write-Host "  .\dist\RemoteSubtitleWindow.exe --server http://192.168.1.10:8765"
