#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$appDir = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    $env:STREAM_TRANSLATOR_BUILD_PYTHON,
    (Join-Path $appDir "venv\Scripts\python.exe"),
    (Join-Path $appDir "..\.venv\Scripts\python.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
    & $candidate -c "import PyInstaller; from PyQt6 import QtCore, QtGui, QtWidgets, QtNetwork" *> $null
    if ($LASTEXITCODE -eq 0) {
        $pythonExe = (Resolve-Path -LiteralPath $candidate).Path
        break
    }
}
if (-not $pythonExe) { throw "No usable Python with PyInstaller and PyQt6 found" }
Push-Location $appDir
try {
    & $pythonExe -m PyInstaller (Join-Path $PSScriptRoot "stream-translator-remote-subtitle.spec") `
        --noconfirm --clean --distpath (Join-Path $appDir "dist-remote-subtitle") `
        --workpath (Join-Path $appDir "build-remote-subtitle")
    if ($LASTEXITCODE -ne 0) { throw "Remote subtitle build failed" }
    # Analysis-00.toc also lists the spec's excludes, so only the bundled module list (PYZ) is checked.
    $tocFiles = @(Get-ChildItem -LiteralPath (Join-Path $appDir "build-remote-subtitle") -Recurse -File |
        Where-Object { $_.Name -eq "PYZ-00.toc" })
    if (-not $tocFiles) { throw "No bundled module TOC found" }
    if ($tocFiles | Select-String -Pattern "\('backend(?:\.|')" -Quiet) {
        throw "Remote subtitle build unexpectedly contains backend modules"
    }
} finally {
    Pop-Location
}
Write-Host (Join-Path $appDir "dist-remote-subtitle\StreamTranslatorRemoteSubtitle.exe")
