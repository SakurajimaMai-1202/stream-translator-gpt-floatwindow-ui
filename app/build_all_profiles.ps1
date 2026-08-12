#!/usr/bin/env pwsh
param(
    [string]$Version = "1.4.0",
    [ValidateSet("Quick", "Final")][string]$Mode = "Quick",
    [switch]$ReuseRuntimeCache,
    [switch]$ReuseSharedGui,
    [switch]$ReuseProfileArtifacts,
    [string]$SevenZipPath = "",
    [ValidateRange(0, 9)][int]$CompressionLevel = 7,
    [ValidateRange(64, 2047)][int]$SplitSizeMiB = 1900,
    [ValidateRange(1, 128)][int]$CopyThreads = 16,
    [switch]$IncludeCpuAsrSidecar = $true
)

$ErrorActionPreference = "Stop"
$appDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $appDir
$packagingDir = Join-Path $appDir "packaging"
$sharedGuiDir = Join-Path $appDir "build-shared-gui\Stream Translator"
$assetDir = Join-Path $appDir "release-v$Version-assets"
$profiles = @("cuda", "cpu", "rocm")

. (Join-Path $packagingDir "runtime_profile_packaging.ps1")
. (Join-Path $packagingDir "release_build_tools.ps1")

$sevenZipExe = Resolve-SevenZipPath -RequestedPath $SevenZipPath
$reuseValidatedRuntimeCaches = $true
$effectiveCompressionLevel = if ($Mode -eq "Quick") { 1 } else { $CompressionLevel }
if (-not $ReuseRuntimeCache) {
    Write-Host "Validated profile runtime caches are reused by default in the three-profile build." -ForegroundColor DarkYellow
}
$overallTimer = [Diagnostics.Stopwatch]::StartNew()
$stepTimings = [ordered]@{}

& (Join-Path $packagingDir "build_profile_runtime.ps1") -Profile cpu
if (-not $?) { throw "CPU ASR runtime cache build failed" }

& (Join-Path $packagingDir "build_cpu_asr_sidecar.ps1") `
    -Version $Version `
    -SevenZipPath $sevenZipExe `
    -CompressionLevel $effectiveCompressionLevel `
    -CopyThreads $CopyThreads
if (-not $?) { throw "CPU ASR sidecar build failed" }
$sidecarAsset = Get-Item -LiteralPath (Join-Path $appDir "dist-cpu-asr-sidecar\StreamTranslator-CPU-ASR-Sidecar-v$Version.zip")
$sidecarChecksum = Get-Item -LiteralPath "$($sidecarAsset.FullName).sha256"

Write-Host "Stream Translator three-profile build" -ForegroundColor Cyan
Write-Host "Version=$Version Mode=$Mode Compression=$effectiveCompressionLevel Split=${SplitSizeMiB}MiB Threads=$CopyThreads"

$timer = [Diagnostics.Stopwatch]::StartNew()
if ($ReuseSharedGui) {
    if (-not (Test-Path -LiteralPath $sharedGuiDir -PathType Container)) {
        throw "Reusable shared GUI was not found: $sharedGuiDir"
    }
    Write-Host "Reusing shared GUI: $sharedGuiDir" -ForegroundColor Green
} else {
    & (Join-Path $packagingDir "build_shared_gui.ps1") `
        -Version $Version `
        -Destination $sharedGuiDir `
        -CopyThreads $CopyThreads
    if (-not $?) { throw "Shared GUI build failed" }
}
$timer.Stop()
$stepTimings.shared_gui_seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 2)

$sharedExe = Get-ChildItem -LiteralPath $sharedGuiDir -Filter "*.exe" -File | Select-Object -First 1
if (-not $sharedExe) { throw "Shared GUI executable was not found: $sharedGuiDir" }
$sharedGuiHash = (Get-FileHash -LiteralPath $sharedExe.FullName -Algorithm SHA256).Hash

$profileResults = @()
foreach ($profile in $profiles) {
    $packageInfo = Get-RuntimeProfilePackageInfo -RuntimeProfile $profile
    $timer.Restart()
    $releaseArgs = @{
        Profile = $profile
        Version = $Version
        SharedGuiDir = $sharedGuiDir
        SevenZipPath = $sevenZipExe
        CompressionLevel = $effectiveCompressionLevel
        CopyThreads = $CopyThreads
    }
    if ($reuseValidatedRuntimeCaches) { $releaseArgs.ReuseRuntimeCache = $true }
    if ($Mode -eq "Quick") { $releaseArgs.SkipFullZip = $true }
    if ($Mode -eq "Quick") { $releaseArgs.SkipRuntimeDependenciesInAppUpdate = $true }
    if ($profile -ne "cpu") { $releaseArgs.IncludeCpuAsrSidecar = [bool]$IncludeCpuAsrSidecar }

    if ($ReuseProfileArtifacts) {
        Write-Host "Reusing assembled $profile artifact" -ForegroundColor Green
    } else {
        & (Join-Path $packagingDir "build_profile_release.ps1") @releaseArgs
        if (-not $?) { throw "$profile package build failed" }
    }
    $validationArgs = @{ Profile = $profile }
    if ($IncludeCpuAsrSidecar -and $profile -ne "cpu") {
        $validationArgs.RequireCpuAsrSidecar = $true
    }
    & (Join-Path $packagingDir "validate_runtime_artifact.ps1") @validationArgs
    if (-not $?) { throw "$profile artifact validation failed" }
    $timer.Stop()
    $stepTimings["$profile`_package_seconds"] = [Math]::Round($timer.Elapsed.TotalSeconds, 2)

    $distDir = Join-Path $appDir $packageInfo.DistDirName
    $packageRoot = Join-Path $distDir $packageInfo.PackageName
    $runtimeManifestPath = Join-Path $packageRoot "_runtime\runtime-version.json"
    if (-not (Test-Path -LiteralPath $runtimeManifestPath)) {
        throw "Runtime manifest missing from assembled package: $runtimeManifestPath"
    }
    $runtimeManifest = Get-Content -LiteralPath $runtimeManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($runtimeManifest.profile -ne $profile) {
        throw "Assembled package profile mismatch: expected $profile, got $($runtimeManifest.profile)"
    }

    $packagedExe = Get-ChildItem -LiteralPath $packageRoot -Filter "*.exe" -File | Select-Object -First 1
    if (-not $packagedExe) { throw "Packaged GUI executable missing: $packageRoot" }
    $packagedGuiHash = (Get-FileHash -LiteralPath $packagedExe.FullName -Algorithm SHA256).Hash
    if ($packagedGuiHash -ne $sharedGuiHash) {
        throw "$profile GUI hash differs from the shared GUI build"
    }
    if ($Mode -eq "Final" -and -not (Test-Path -LiteralPath (Join-Path $distDir $packageInfo.FullZip))) {
        throw "Reusable Final artifact is missing its Full ZIP: $(Join-Path $distDir $packageInfo.FullZip)"
    }

    $appUpdateBuildInfoPath = Join-Path $distDir "App-Update\app-update-build.json"
    $appUpdateDependencyMode = if (Test-Path -LiteralPath $appUpdateBuildInfoPath) {
        $appUpdateBuildInfo = Get-Content -LiteralPath $appUpdateBuildInfoPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ([bool]$appUpdateBuildInfo.runtime_dependencies_included) { "included" } else { "omitted" }
    } else {
        "unknown-reused-artifact"
    }

    $profileResults += [pscustomobject]@{
        profile = $profile
        package_name = $packageInfo.PackageName
        runtime_backend = $runtimeManifest.torch_backend
        app_update = $packageInfo.AppUpdateZip
        app_update_runtime_dependencies = $appUpdateDependencyMode
        full_zip = if ($Mode -eq "Final") { $packageInfo.FullZip } else { $null }
        full_zip_sha256 = $null
        parts = @()
    }
}

if (Test-Path -LiteralPath $assetDir) {
    Remove-Item -LiteralPath $assetDir -Recurse -Force
}
New-Item -ItemType Directory -Path $assetDir -Force | Out-Null

Copy-Item -LiteralPath $sidecarAsset.FullName -Destination $assetDir -Force
Copy-Item -LiteralPath $sidecarChecksum.FullName -Destination $assetDir -Force

$checksumEntries = @()
$checksumEntries += [pscustomobject]@{
    hash = (Get-FileHash -LiteralPath $sidecarAsset.FullName -Algorithm SHA256).Hash
    name = $sidecarAsset.Name
}
$checksumEntries += [pscustomobject]@{
    hash = (Get-FileHash -LiteralPath $sidecarChecksum.FullName -Algorithm SHA256).Hash
    name = $sidecarChecksum.Name
}
foreach ($result in $profileResults) {
    $packageInfo = Get-RuntimeProfilePackageInfo -RuntimeProfile $result.profile
    $distDir = Join-Path $appDir $packageInfo.DistDirName
    $appUpdatePath = Join-Path $distDir $packageInfo.AppUpdateZip
    Copy-Item -LiteralPath $appUpdatePath -Destination $assetDir -Force
    $appUpdateHash = (Get-FileHash -LiteralPath $appUpdatePath -Algorithm SHA256).Hash
    $checksumEntries += [pscustomobject]@{ hash = $appUpdateHash; name = $packageInfo.AppUpdateZip }

    if ($Mode -eq "Final") {
        $timer.Restart()
        $fullZipPath = Join-Path $distDir $packageInfo.FullZip
        Test-ReleaseZip -SevenZipPath $sevenZipExe -Path $fullZipPath
        $parts = @(Split-ReleaseFile -Path $fullZipPath -PartSizeMiB $SplitSizeMiB)
        $fullZipHash = Test-SplitReleaseFile -OriginalPath $fullZipPath -Parts $parts -SevenZipPath $sevenZipExe
        $timer.Stop()
        $stepTimings["$($result.profile)_split_verify_seconds"] = [Math]::Round($timer.Elapsed.TotalSeconds, 2)

        $result.full_zip_sha256 = $fullZipHash
        $result.parts = @($parts | Sort-Object Name | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $assetDir -Force
            $partHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            $checksumEntries += [pscustomobject]@{ hash = $partHash; name = $_.Name }
            [pscustomobject]@{
                name = $_.Name
                size_bytes = $_.Length
                sha256 = $partHash
            }
        })
        $checksumEntries += [pscustomobject]@{ hash = $fullZipHash; name = $packageInfo.FullZip }
    }
}

$mergeScriptSource = Join-Path $projectRoot "merge-full-package.bat"
if (Test-Path -LiteralPath $mergeScriptSource) {
    Copy-Item -LiteralPath $mergeScriptSource -Destination $assetDir -Force
    $checksumEntries += [pscustomobject]@{
        hash = (Get-FileHash -LiteralPath $mergeScriptSource -Algorithm SHA256).Hash
        name = "merge-full-package.bat"
    }
}

$releaseNotesSource = Join-Path $appDir "docs\RELEASE_NOTES_v$Version`_zh-TW.md"
if (Test-Path -LiteralPath $releaseNotesSource) {
    Copy-Item -LiteralPath $releaseNotesSource -Destination $assetDir -Force
    $checksumEntries += [pscustomobject]@{
        hash = (Get-FileHash -LiteralPath $releaseNotesSource -Algorithm SHA256).Hash
        name = (Split-Path -Leaf $releaseNotesSource)
    }
}

$overallTimer.Stop()
$manifest = [ordered]@{
    schema = 1
    version = $Version
    mode = $Mode.ToLowerInvariant()
    created_at = (Get-Date).ToString("o")
    compression = [ordered]@{
        format = "zip"
        method = "Deflate"
        level = $effectiveCompressionLevel
        multithreaded = $true
        tool = $sevenZipExe
    }
    split_size_mib = if ($Mode -eq "Final") { $SplitSizeMiB } else { $null }
    shared_gui_sha256 = $sharedGuiHash
    cpu_asr_sidecar = [ordered]@{
        name = $sidecarAsset.Name
        size_bytes = $sidecarAsset.Length
        sha256 = (Get-FileHash -LiteralPath $sidecarAsset.FullName -Algorithm SHA256).Hash
    }
    profiles = $profileResults
    timings = $stepTimings
    total_seconds = [Math]::Round($overallTimer.Elapsed.TotalSeconds, 2)
}
$manifestPath = Join-Path $assetDir "release-manifest-v$Version.json"
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$checksumEntries += [pscustomobject]@{
    hash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash
    name = (Split-Path -Leaf $manifestPath)
}

$checksumPath = Join-Path $assetDir "SHA256SUMS-v$Version.txt"
$checksumText = ($checksumEntries | Sort-Object name | ForEach-Object {
    "$($_.hash)  $($_.name)"
}) -join "`r`n"
[IO.File]::WriteAllText($checksumPath, $checksumText + "`r`n", [Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Three-profile $Mode build complete: $assetDir" -ForegroundColor Green
Write-Host "Shared GUI SHA256: $sharedGuiHash"
Write-Host "Elapsed: $([Math]::Round($overallTimer.Elapsed.TotalMinutes, 2)) minutes"
