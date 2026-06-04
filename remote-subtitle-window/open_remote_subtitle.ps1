#!/usr/bin/env pwsh
param(
    [string]$Server = "http://127.0.0.1:8765"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$referenceExe = Join-Path $scriptDir "dist\RemoteSubtitleWindowReferenceStyle.exe"
$prettyExe = Join-Path $scriptDir "dist\RemoteSubtitleWindowPretty.exe"
$sharpExe = Join-Path $scriptDir "dist\RemoteSubtitleWindowTrueAlphaSharp.exe"
$trueAlphaExe = Join-Path $scriptDir "dist\RemoteSubtitleWindowTrueAlpha.exe"
$exe = Join-Path $scriptDir "dist\RemoteSubtitleWindow.exe"

if (Test-Path $referenceExe) {
    & $referenceExe --server $Server
    exit $LASTEXITCODE
}

if (Test-Path $prettyExe) {
    & $prettyExe --server $Server
    exit $LASTEXITCODE
}

if (Test-Path $sharpExe) {
    & $sharpExe --server $Server
    exit $LASTEXITCODE
}

if (Test-Path $trueAlphaExe) {
    & $trueAlphaExe --server $Server
    exit $LASTEXITCODE
}

if (Test-Path $exe) {
    & $exe --server $Server
    exit $LASTEXITCODE
}

$runner = Join-Path $scriptDir "run_remote_subtitle.ps1"
& $runner -Server $Server
