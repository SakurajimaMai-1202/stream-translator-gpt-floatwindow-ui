#!/usr/bin/env pwsh
# UI2 portable packaging script (onedir mode, PyQt6-WebEngine compatible)

$ErrorActionPreference = "Stop"
$scriptDir   = $PSScriptRoot
$frontendDir = Join-Path $scriptDir "frontend"
$backendDir  = Join-Path $scriptDir "backend"
$pythonCandidates = @(
    (Join-Path $scriptDir "..\.venv\Scripts\python.exe"),
    (Join-Path $scriptDir "venv\Scripts\python.exe")
)
$venvPython = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $venvPython = (Resolve-Path $candidate).Path
        break
    }
}
$distDir     = Join-Path $scriptDir "dist"
$buildDir    = Join-Path $scriptDir "build"
$appName     = "Stream Translator"

Write-Host "=== Stream Translator - Portable Build ===" -ForegroundColor Cyan
Write-Host ""

if (-not $venvPython) {
    Write-Host "ERROR: no usable virtual environment Python found." -ForegroundColor Red
    Write-Host "Checked:" -ForegroundColor Yellow
    $pythonCandidates | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "Please create one environment and install dependencies." -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Python: $venvPython" -ForegroundColor Gray

try {
    Write-Host "[1/9] Ensure PyInstaller" -ForegroundColor Yellow
    $pyiExe = Join-Path (Split-Path -Parent $venvPython) "pyinstaller.exe"
    if (-not (Test-Path $pyiExe)) {
        Write-Host "  Installing PyInstaller..." -ForegroundColor Gray
        & $venvPython -m pip install pyinstaller --quiet
    }
    Write-Host "  OK PyInstaller ready" -ForegroundColor Green

    Write-Host "[2/9] Ensure httpx" -ForegroundColor Yellow
    & $venvPython -m pip install httpx --quiet
    Write-Host "  OK httpx ready" -ForegroundColor Green

    Write-Host "[2b/9] Validate ML packages" -ForegroundColor Yellow
    $missingPkgs = @()
    $checkPkgs = @(
        @{ name = 'torch';          import = 'torch' },
        @{ name = 'faster_whisper'; import = 'faster_whisper' },
        @{ name = 'openai_whisper'; import = 'whisper' }
    )
    foreach ($pkg in $checkPkgs) {
        & $venvPython -c "import $($pkg.import)" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $missingPkgs += $pkg.name
            Write-Host "  MISSING: $($pkg.name)" -ForegroundColor Yellow
        } else {
            Write-Host "  OK $($pkg.name)" -ForegroundColor Green
        }
    }
    if ($missingPkgs.Count -gt 0) {
        Write-Host ""
        Write-Host "ERROR: required ML packages are missing:" -ForegroundColor Red
        $missingPkgs | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
        Write-Host ""
        Write-Host "Install dependencies first:" -ForegroundColor Yellow
        Write-Host "  venv\Scripts\pip install torch --extra-index-url https://download.pytorch.org/whl/cu124" -ForegroundColor Gray
        Write-Host "  venv\Scripts\pip install -r requirements_full.txt" -ForegroundColor Gray
        exit 1
    }

    Write-Host "[3/9] Build Vue frontend" -ForegroundColor Yellow
    Set-Location $frontendDir

    if (-not (Test-Path "node_modules")) {
        Write-Host "  Installing frontend dependencies..." -ForegroundColor Gray
        npm install --silent
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed"
        }
    }
    npx vite build
    if ($LASTEXITCODE -ne 0) {
        throw "vite build failed"
    }

    $staticDir = Join-Path $backendDir "static"
    if (-not (Test-Path $staticDir)) {
        throw "Frontend build failed: static directory not found: $staticDir"
    }
    Write-Host "  OK frontend build done" -ForegroundColor Green

    Set-Location $scriptDir
    Write-Host "[4/9] Clean old artifacts" -ForegroundColor Yellow
    if (Test-Path $distDir)  { Remove-Item -Recurse -Force $distDir }
    if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
    Write-Host "  OK clean done" -ForegroundColor Green

    Write-Host "[5/9] Run PyInstaller (onedir)" -ForegroundColor Yellow
    & $venvPython -m PyInstaller --clean "stream-translator-llm-gui.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed"
    }

    $outputDir = Join-Path $distDir $appName
    $configSrc = Join-Path $scriptDir "config.example.yaml"
    $configDst = Join-Path $outputDir "config.yaml"

    if ((Test-Path $configSrc) -and (-not (Test-Path $configDst))) {
        Copy-Item $configSrc $configDst
        Write-Host "  OK copied default config.yaml" -ForegroundColor Green
    }

    Write-Host "[6/9] Create portable _runtime Python" -ForegroundColor Yellow
    $runtimeDir = Join-Path $outputDir "_runtime"

    $venvRoot = Split-Path -Parent (Split-Path -Parent $venvPython)
    $pyvenvCfg = Join-Path $venvRoot "pyvenv.cfg"
    $homeValue = (Get-Content $pyvenvCfg | Where-Object { $_ -match "^home\s*=" }) -replace "^home\s*=\s*", ""
    $basePythonDir = $homeValue.Trim()
    Write-Host "  Base Python: $basePythonDir" -ForegroundColor Gray

    if (-not (Test-Path $basePythonDir)) {
        throw "Base Python directory not found: $basePythonDir"
    }

    if (Test-Path $runtimeDir) { Remove-Item -Recurse -Force $runtimeDir }
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

    foreach ($f in @("python.exe", "pythonw.exe", "python3.dll")) {
        $src = Join-Path $basePythonDir $f
        if (Test-Path $src) { Copy-Item $src $runtimeDir }
    }
    Get-ChildItem $basePythonDir -Filter "python*.dll" -ErrorAction SilentlyContinue | Copy-Item -Destination $runtimeDir
    Get-ChildItem $basePythonDir -Filter "vcruntime*.dll" -ErrorAction SilentlyContinue | Copy-Item -Destination $runtimeDir

    $srcDLLs = Join-Path $basePythonDir "DLLs"
    if (Test-Path $srcDLLs) {
        Copy-Item $srcDLLs (Join-Path $runtimeDir "DLLs") -Recurse
    }

    $dstLib = Join-Path $runtimeDir "Lib"
    New-Item -ItemType Directory -Force -Path $dstLib | Out-Null
    Get-ChildItem (Join-Path $basePythonDir "Lib") |
        Where-Object { $_.Name -ne "site-packages" } |
        ForEach-Object { Copy-Item $_.FullName $dstLib -Recurse -Force }

    $dstSitePackages = Join-Path $dstLib "site-packages"
    New-Item -ItemType Directory -Force -Path $dstSitePackages | Out-Null
    $srcSitePackages = Join-Path $venvRoot "Lib\site-packages"
    Write-Host "  Copying site-packages (may take a while, torch is large)..." -ForegroundColor Gray
    Copy-Item "$srcSitePackages\*" $dstSitePackages -Recurse -Force

    Get-ChildItem $dstSitePackages -Filter "__editable__*" -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem $dstSitePackages -Filter "*.egg-link" -ErrorAction SilentlyContinue | Remove-Item -Force

    $dstPkg = Join-Path $dstSitePackages "stream_translator_gpt"
    if (Test-Path $dstPkg) { Remove-Item -Recurse -Force $dstPkg }
    $srcPkg = Join-Path $scriptDir "..\stream-translator-gpt\stream_translator_gpt"
    if (-not (Test-Path $srcPkg)) {
        throw "Patched stream_translator_gpt not found: $srcPkg"
    }
    Write-Host "  Copying patched stream_translator_gpt..." -ForegroundColor Gray
    Copy-Item $srcPkg $dstSitePackages -Recurse -Force

    $pyVersion = & $venvPython -c "import sys; print(f'python{sys.version_info.major}{sys.version_info.minor}._pth')" 2>&1
    $pyVersion = $pyVersion.Trim()
    Write-Host "  Writing portable path file: $pyVersion" -ForegroundColor Gray
    $pthContent = "." + [System.Environment]::NewLine +
                  "Lib" + [System.Environment]::NewLine +
                  "DLLs" + [System.Environment]::NewLine +
                  "Lib\site-packages" + [System.Environment]::NewLine +
                  "import site" + [System.Environment]::NewLine
    [System.IO.File]::WriteAllText((Join-Path $runtimeDir $pyVersion), $pthContent, [System.Text.Encoding]::ASCII)

    Write-Host "  OK _runtime created: $runtimeDir" -ForegroundColor Green

    Write-Host "[7/9] Copy ffmpeg binaries" -ForegroundColor Yellow
    $ffmpegSrc = Join-Path $scriptDir "..\ffmpeg-8.1-essentials_build\ffmpeg-8.1-essentials_build\bin"
    $ffmpegDst = Join-Path $outputDir "ffmpeg\bin"
    if (-not (Test-Path $ffmpegSrc)) {
        Write-Host "  WARN: ffmpeg source not found: $ffmpegSrc" -ForegroundColor Yellow
        Write-Host "  ffmpeg copy skipped (user must have ffmpeg in PATH)" -ForegroundColor Yellow
    } else {
        New-Item -ItemType Directory -Force -Path $ffmpegDst | Out-Null
        foreach ($exe in @('ffmpeg.exe', 'ffplay.exe', 'ffprobe.exe')) {
            $src = Join-Path $ffmpegSrc $exe
            if (Test-Path $src) {
                Copy-Item $src $ffmpegDst
                Write-Host "  Copied: $exe" -ForegroundColor Gray
            }
        }
        Write-Host "  OK ffmpeg copied: $ffmpegDst" -ForegroundColor Green
    }

    Write-Host "[8/9] Copy llama binaries" -ForegroundColor Yellow
    $llamaSrc = Join-Path $scriptDir "..\llama"
    $llamaDst = Join-Path $outputDir "llama"
    if (-not (Test-Path $llamaSrc)) {
        Write-Host "  WARN: llama source not found: $llamaSrc" -ForegroundColor Yellow
        Write-Host "  llama copy skipped (llama features unavailable)" -ForegroundColor Yellow
    } else {
        New-Item -ItemType Directory -Force -Path $llamaDst | Out-Null
        Get-ChildItem $llamaSrc -File | ForEach-Object {
            if ($_.Extension -in @('.exe', '.dll') -or $_.Name -like 'llama*') {
                Copy-Item $_.FullName $llamaDst
                Write-Host "  Copied: $($_.Name)" -ForegroundColor Gray
            }
        }
        Write-Host "  OK llama copied: $llamaDst" -ForegroundColor Green
    }

    $zipPath = Join-Path $distDir "$appName.zip"
    Write-Host "[9/9] Create zip archive" -ForegroundColor Yellow
    Compress-Archive -Path $outputDir -DestinationPath $zipPath -Force
    Write-Host "  OK zip created: $zipPath" -ForegroundColor Green

    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Green
    Write-Host "BUILD COMPLETED" -ForegroundColor Green
    Write-Host ("=" * 60) -ForegroundColor Green
    Write-Host ""
    Write-Host "Output folder: $outputDir" -ForegroundColor Cyan
    Write-Host "Portable zip : $zipPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor White
    Write-Host "  1. Extract zip to any folder"
    Write-Host "  2. Edit config.yaml (API keys, settings)"
    Write-Host "  3. Run Stream Translator.exe"
    Write-Host ""
    Write-Host "Notes:" -ForegroundColor Yellow
    Write-Host "  - Llama model files (.gguf) are not included."
    Write-Host "  - GPU acceleration needs NVIDIA driver >= 550.x."
    Write-Host "  - CPU mode works without GPU."

} catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
} finally {
    Set-Location $scriptDir
}
