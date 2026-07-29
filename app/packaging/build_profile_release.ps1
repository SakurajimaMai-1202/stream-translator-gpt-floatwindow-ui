#!/usr/bin/env pwsh
param(
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile = "cuda",
    [string]$Version = "1.3.7",
    [switch]$ForceRuntime,
    [switch]$ReuseRuntimeCache,
    [switch]$SkipFullZip,
    [string]$SharedGuiDir = "",
    [string]$SevenZipPath = "",
    [ValidateRange(0, 9)][int]$CompressionLevel = 7,
    [ValidateRange(1, 128)][int]$CopyThreads = 16,
    [switch]$SkipRuntimeDependenciesInAppUpdate
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$scriptDir = Split-Path -Parent $packagingDir
$projectRoot = Split-Path -Parent $scriptDir
$frontendDir = Join-Path $scriptDir "frontend"
. (Join-Path $packagingDir "runtime_profile_packaging.ps1")
. (Join-Path $packagingDir "release_build_tools.ps1")

$packageInfo = Get-RuntimeProfilePackageInfo -RuntimeProfile $Profile
$profileLabel = $packageInfo.Label
$packageSuffix = $packageInfo.Suffix
$distDir = Join-Path $scriptDir $packageInfo.DistDirName
$pyInstallerDist = Join-Path $scriptDir "build-gui-dist"
$pyInstallerWork = Join-Path $scriptDir "build-gui"
$appName = "Stream Translator"
$packageName = $packageInfo.PackageName
$releaseRoot = Join-Path $distDir $packageName
$runtimeCache = Join-Path $scriptDir "build-runtime-cache\$($packageInfo.RuntimeCacheName)"
$sevenZipExe = Resolve-SevenZipPath -RequestedPath $SevenZipPath
$sharedGuiPath = if ($SharedGuiDir) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($SharedGuiDir)
} else {
    ""
}

$pythonExe = $null
if (-not $sharedGuiPath) {
    $pythonCandidates = @(
        $env:STREAM_TRANSLATOR_BUILD_PYTHON,
        (Join-Path $scriptDir "venv\Scripts\python.exe"),
        (Join-Path $scriptDir "..\.venv\Scripts\python.exe"),
        (Join-Path $scriptDir "dist-hotfix\Stream Translator\_runtime\python.exe"),
        (Join-Path $scriptDir "dist\Stream Translator\_runtime\python.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }
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
} elseif (-not (Test-Path -LiteralPath $sharedGuiPath -PathType Container)) {
    throw "Shared GUI directory not found: $sharedGuiPath"
}

function Copy-ProfileConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $sourceConfig = Join-Path $scriptDir "config.example.yaml"
    $configText = Get-Content $sourceConfig -Raw -Encoding utf8
    $configText = Set-RuntimeProfileInConfigText -ConfigText $configText -RuntimeProfile $Profile
    [System.IO.File]::WriteAllText($Destination, $configText, [System.Text.UTF8Encoding]::new($false))
}

function Set-RuntimeManifestAppVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDir
    )

    $manifestPath = Join-Path $RuntimeDir "runtime-version.json"
    if (-not (Test-Path $manifestPath)) { return }

    $manifest = Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    $manifest | Add-Member -NotePropertyName app_version -NotePropertyValue $Version -Force
    $manifest | ConvertTo-Json | ForEach-Object {
        [IO.File]::WriteAllText($manifestPath, $_ + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    }
}

if ($sharedGuiPath) {
    Write-Host "[1/6] Reuse shared frontend and GUI build" -ForegroundColor Green
    Write-Host "[2/6] Shared GUI: $sharedGuiPath" -ForegroundColor Green
    $builtApp = $sharedGuiPath
} else {
    Write-Host "[1/6] Build frontend" -ForegroundColor Yellow
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

    Write-Host "[2/6] Build GUI onedir" -ForegroundColor Yellow
    Push-Location $scriptDir
    try {
        & $pythonExe -m PyInstaller (Join-Path $packagingDir "stream-translator-llm-gui.spec") --noconfirm --distpath $pyInstallerDist --workpath $pyInstallerWork
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
    } finally { Pop-Location }

    $builtApp = Join-Path $pyInstallerDist $appName
    Get-ChildItem $builtApp -File -Filter "qtwebengine_devtools_resources.debug.pak" -Recurse -ErrorAction SilentlyContinue |
        Remove-Item -Force
}

Write-Host "[3/6] Build or reuse $profileLabel Runtime" -ForegroundColor Yellow
if ($ReuseRuntimeCache) {
    $manifestPath = Join-Path $runtimeCache "runtime-version.json"
    $runtimePython = Join-Path $runtimeCache "python.exe"
    if (-not (Test-Path $manifestPath) -or -not (Test-Path $runtimePython)) {
        throw "Reusable $profileLabel runtime cache is incomplete: $runtimeCache"
    }

    $manifest = Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($manifest.profile -ne $Profile) {
        throw "Runtime cache profile is '$($manifest.profile)', expected '$Profile'."
    }
    $expectedBackend = if ($Profile -eq "rocm") { "rocm" } else { $Profile }
    if ($manifest.torch_backend -ne $expectedBackend) {
        throw "Runtime cache torch backend is '$($manifest.torch_backend)', expected '$expectedBackend'."
    }

    $cachedPackage = Join-Path $runtimeCache "Lib\site-packages\stream_translator_gpt"
    if (Test-Path $cachedPackage) { Remove-Item $cachedPackage -Recurse -Force }
    Copy-Item (Join-Path $projectRoot "stream-translator-gpt\stream_translator_gpt") $cachedPackage -Recurse -Force

    $requiredImports = @("qwen_asr", "funasr", "torchaudio")
    if ($Profile -in @("cuda", "cpu")) {
        $requiredImports += @("faster_whisper", "whisper", "omnivad")
    }
    if ($Profile -eq "cuda") {
        $requiredImports += "nemo.collections.asr.models"
    }
    $importList = ($requiredImports | ForEach-Object { "'$_'" }) -join ","
    & $runtimePython -c "import importlib; [importlib.import_module(name) for name in [$importList]]; print('$profileLabel reusable runtime import check OK')"
    if ($LASTEXITCODE -ne 0) { throw "$profileLabel reusable runtime validation failed" }
    Write-Host "$profileLabel validated runtime cache reused: $runtimeCache" -ForegroundColor Green
} else {
    $runtimeArgs = @()
    if ($ForceRuntime) { $runtimeArgs += "-Force" }
    & (Join-Path $packagingDir "build_profile_runtime.ps1") -Profile $Profile @runtimeArgs
    if ($LASTEXITCODE -ne 0) { throw "Runtime build failed" }
}

Write-Host "[4/6] Create App Update package" -ForegroundColor Yellow
Remove-BuildDirectoryFast -Path $distDir -AllowedRoot $scriptDir
New-Item $distDir -ItemType Directory -Force | Out-Null
$updateRoot = Join-Path $distDir "App-Update"
Invoke-FastDirectoryCopy -Source $builtApp -Destination $updateRoot -Threads $CopyThreads
$updatePackageDir = Join-Path $updateRoot "_runtime\Lib\site-packages"
New-Item $updatePackageDir -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $projectRoot "stream-translator-gpt\stream_translator_gpt") $updatePackageDir -Recurse -Force
$runtimePackageDir = Join-Path $runtimeCache "Lib\site-packages"
$runtimeUpdateExcludePatterns = @(
    "stream_translator_gpt",
    "torch", "torch-*", "torchgen", "functorch",
    "torchaudio", "torchaudio-*",
    "torchvision", "torchvision-*",
    "nemo*", "megatron*", "lightning*", "pytorch_lightning*",
    "PyQt6", "PyQt6-*", "pyqt6_*.dist-info",
    "PyInstaller", "pyinstaller-*", "_pytest", "pytest", "pytest-*",
    "~orch", "~orch-*", "__editable__*", "*.egg-link"
)
if ((Test-Path $runtimePackageDir) -and -not $SkipRuntimeDependenciesInAppUpdate) {
    Invoke-FastDirectoryCopyExcluding `
        -Source $runtimePackageDir `
        -Destination $updatePackageDir `
        -Exclude $runtimeUpdateExcludePatterns `
        -Threads $CopyThreads
} elseif ($SkipRuntimeDependenciesInAppUpdate) {
    Write-Host "Quick mode: runtime dependency copy omitted from App Update" -ForegroundColor DarkYellow
}
$appUpdateBuildInfo = [ordered]@{
    schema = 1
    profile = $Profile
    version = $Version
    runtime_dependencies_included = (-not $SkipRuntimeDependenciesInAppUpdate)
}
[IO.File]::WriteAllText(
    (Join-Path $updateRoot "app-update-build.json"),
    ($appUpdateBuildInfo | ConvertTo-Json) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
Copy-Item (Join-Path $scriptDir "diagnose_runtime.ps1") $updateRoot
Copy-Item (Join-Path $scriptDir "smoke_sensevoice_asr.ps1") $updateRoot
Write-RuntimeProfileDocs -Destination $updateRoot -RuntimeProfile $Profile -Version $Version
$appUpdateZipPath = Join-Path $distDir $packageInfo.AppUpdateZip
Compress-ReleaseDirectory `
    -SevenZipPath $sevenZipExe `
    -WorkingDirectory $distDir `
    -ItemName "App-Update" `
    -Destination $appUpdateZipPath `
    -CompressionLevel $CompressionLevel `
    -ArchiveRootContents
Test-ReleaseZip -SevenZipPath $sevenZipExe -Path $appUpdateZipPath

Write-Host "[5/6] Assemble first-use full package" -ForegroundColor Yellow
Invoke-FastDirectoryCopy -Source $builtApp -Destination $releaseRoot -Threads $CopyThreads
Invoke-FastDirectoryCopy -Source $runtimeCache -Destination (Join-Path $releaseRoot "_runtime") -Threads $CopyThreads
Set-RuntimeManifestAppVersion -RuntimeDir (Join-Path $releaseRoot "_runtime")
New-Item (Join-Path $releaseRoot "models\huggingface\hub") -ItemType Directory -Force | Out-Null
Copy-ProfileConfig (Join-Path $releaseRoot "config.yaml")
Copy-Item (Join-Path $scriptDir "diagnose_runtime.ps1") $releaseRoot
Copy-Item (Join-Path $scriptDir "smoke_sensevoice_asr.ps1") $releaseRoot
Write-RuntimeProfileDocs -Destination $releaseRoot -RuntimeProfile $Profile -Version $Version

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
    $fullZipPath = Join-Path $distDir $packageInfo.FullZip
    Compress-ReleaseDirectory -SevenZipPath $sevenZipExe -WorkingDirectory $distDir -ItemName $packageName -Destination $fullZipPath -CompressionLevel $CompressionLevel
    Test-ReleaseZip -SevenZipPath $sevenZipExe -Path $fullZipPath
} else {
    Write-Host "[6/6] Full package compression skipped" -ForegroundColor DarkYellow
}

Get-ChildItem $distDir -File | ForEach-Object {
    [pscustomobject]@{ Name = $_.Name; GB = [math]::Round($_.Length / 1GB, 3) }
} | Format-Table -AutoSize
Write-Host "$profileLabel release complete: $distDir" -ForegroundColor Green
