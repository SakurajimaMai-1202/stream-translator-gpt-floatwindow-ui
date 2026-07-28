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

$releaseArgs = @{
    Profile = $Profile
    Version = $Version
    CompressionLevel = $CompressionLevel
    CopyThreads = $CopyThreads
}
if ($ForceRuntime) { $releaseArgs.ForceRuntime = $true }
if ($ReuseRuntimeCache) { $releaseArgs.ReuseRuntimeCache = $true }
if ($SkipFullZip) { $releaseArgs.SkipFullZip = $true }
if ($SharedGuiDir) { $releaseArgs.SharedGuiDir = $SharedGuiDir }
if ($SevenZipPath) { $releaseArgs.SevenZipPath = $SevenZipPath }
if ($SkipRuntimeDependenciesInAppUpdate) { $releaseArgs.SkipRuntimeDependenciesInAppUpdate = $true }
& (Join-Path $PSScriptRoot "packaging\build_profile_release.ps1") @releaseArgs
exit $LASTEXITCODE
