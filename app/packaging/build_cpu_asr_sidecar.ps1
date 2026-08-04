#!/usr/bin/env pwsh
param(
    [string]$Version = "1.3.9",
    [string]$SevenZipPath = "",
    [ValidateRange(0, 9)][int]$CompressionLevel = 7,
    [ValidateRange(1, 128)][int]$CopyThreads = 16
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot
$appDir = Split-Path -Parent $packagingDir
$projectRoot = Split-Path -Parent $appDir
$runtimeCache = Join-Path $appDir "build-runtime-cache\cpu-runtime"
$outputDir = Join-Path $appDir "dist-cpu-asr-sidecar"
$stagingRoot = Join-Path $outputDir "staging"
$stagingRuntime = Join-Path $stagingRoot "_runtime_cpu_asr"
$assetName = "StreamTranslator-CPU-ASR-Sidecar-v$Version.zip"
$assetPath = Join-Path $outputDir $assetName

. (Join-Path $packagingDir "release_build_tools.ps1")
$sevenZipExe = Resolve-SevenZipPath -RequestedPath $SevenZipPath

if (-not (Test-Path -LiteralPath (Join-Path $runtimeCache "python.exe"))) {
    throw "CPU runtime cache is missing: $runtimeCache"
}

Remove-BuildDirectoryFast -Path $outputDir -AllowedRoot $appDir
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
Invoke-FastDirectoryCopy -Source $runtimeCache -Destination $stagingRuntime -Threads $CopyThreads

$packageTarget = Join-Path $stagingRuntime "Lib\site-packages\stream_translator_gpt"
if (Test-Path -LiteralPath $packageTarget) { Remove-Item -LiteralPath $packageTarget -Recurse -Force }
Copy-Item -LiteralPath (Join-Path $projectRoot "stream-translator-gpt\stream_translator_gpt") -Destination $packageTarget -Recurse -Force

$manifestPath = Join-Path $stagingRuntime "runtime-version.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifest.profile -ne "cpu" -or $manifest.torch_backend -ne "none" -or -not $manifest.sherpa_onnx) {
    throw "CPU ASR sidecar runtime manifest is invalid"
}
$manifest | Add-Member -NotePropertyName app_version -NotePropertyValue $Version -Force
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

$runtimePython = Join-Path $stagingRuntime "python.exe"
& $runtimePython -c "import sherpa_onnx, stream_translator_gpt.main; print('CPU ASR sidecar import check OK', sherpa_onnx.__version__)"
if ($LASTEXITCODE -ne 0) { throw "CPU ASR sidecar import validation failed" }

Compress-ReleaseDirectory `
    -SevenZipPath $sevenZipExe `
    -WorkingDirectory $stagingRoot `
    -ItemName "_runtime_cpu_asr" `
    -Destination $assetPath `
    -CompressionLevel $CompressionLevel
Test-ReleaseZip -SevenZipPath $sevenZipExe -Path $assetPath

$hash = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$assetPath.sha256", "$hash  $assetName`r`n", [Text.UTF8Encoding]::new($false))
Write-Output $assetPath
