#!/usr/bin/env pwsh
param(
    [string]$Version = "1.3.7",
    [string]$Destination = "",
    [ValidateRange(1, 128)][int]$CopyThreads = 16
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$scriptDir = Split-Path -Parent $packagingDir
$frontendDir = Join-Path $scriptDir "frontend"
$pyInstallerDist = Join-Path $scriptDir "build-gui-dist"
$pyInstallerWork = Join-Path $scriptDir "build-gui"
$destinationPath = if ($Destination) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
} else {
    Join-Path $scriptDir "build-shared-gui\Stream Translator"
}
. (Join-Path $packagingDir "release_build_tools.ps1")

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

$stopwatch = [Diagnostics.Stopwatch]::StartNew()
Write-Host "[Shared GUI 1/2] Build frontend" -ForegroundColor Yellow
Push-Location $frontendDir
try {
    if (-not (Test-Path "node_modules")) { npm install }
    $previousViteVersion = $env:VITE_APP_VERSION
    $env:VITE_APP_VERSION = $Version
    & (Join-Path $frontendDir "node_modules\.bin\vite.cmd") build
    if ($LASTEXITCODE -ne 0) { throw "Vite build failed" }
} finally {
    $env:VITE_APP_VERSION = $previousViteVersion
    Pop-Location
}

Write-Host "[Shared GUI 2/2] Build PyInstaller onedir" -ForegroundColor Yellow
Push-Location $scriptDir
try {
    & $pythonExe -m PyInstaller (Join-Path $packagingDir "stream-translator-llm-gui.spec") --noconfirm --distpath $pyInstallerDist --workpath $pyInstallerWork
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
} finally {
    Pop-Location
}

$builtApp = Join-Path $pyInstallerDist "Stream Translator"
Get-ChildItem $builtApp -File -Filter "qtwebengine_devtools_resources.debug.pak" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force

if (Test-Path -LiteralPath $destinationPath) {
    Remove-BuildDirectoryFast -Path $destinationPath -AllowedRoot $scriptDir
}
Invoke-FastDirectoryCopy -Source $builtApp -Destination $destinationPath -Threads $CopyThreads
$stopwatch.Stop()

$exePath = Join-Path $destinationPath "StreamTranslator.exe"
if (-not (Test-Path $exePath)) {
    $exePath = Get-ChildItem $destinationPath -Filter "*.exe" -File | Select-Object -First 1 -ExpandProperty FullName
}
$result = [pscustomobject]@{
    path = $destinationPath
    version = $Version
    exe_sha256 = if ($exePath) { (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash } else { "" }
    elapsed_seconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)
}
$result | ConvertTo-Json -Compress
$global:LASTEXITCODE = 0
