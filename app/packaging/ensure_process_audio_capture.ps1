# Build the shared native capture DLL before copying the Python package.
$ErrorActionPreference = 'Stop'
$processAudioRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$processAudioNative = Join-Path $processAudioRoot 'stream-translator-gpt\native'
$processAudioDll = Join-Path $processAudioRoot 'stream-translator-gpt\stream_translator_gpt\native\process_audio_capture.dll'
$processAudioInputs = @(
    (Join-Path $processAudioNative 'process_audio_capture.cpp'),
    (Join-Path $processAudioNative 'build.ps1')
)
$processAudioNeedsBuild = -not (Test-Path -LiteralPath $processAudioDll)
if (-not $processAudioNeedsBuild) {
    $processAudioBuiltAt = (Get-Item -LiteralPath $processAudioDll).LastWriteTimeUtc
    $processAudioNeedsBuild = @($processAudioInputs | Where-Object {
        (Get-Item -LiteralPath $_).LastWriteTimeUtc -gt $processAudioBuiltAt
    }).Count -gt 0
}
if ($processAudioNeedsBuild) {
    & (Join-Path $processAudioNative 'build.ps1')
    if (-not (Test-Path -LiteralPath $processAudioDll)) { throw 'Process audio capture DLL build failed.' }
}
