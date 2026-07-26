param(
    [string]$Version = "1.3.6",
    [string]$SourcePath = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $OutputDir) {
    $OutputDir = Join-Path $appRoot "release-v$Version"
}

$defaultCandidates = @(
    (Join-Path $appRoot "models\huggingface\modelscope\models\iic\SenseVoiceSmall"),
    (Join-Path $appRoot "models\huggingface\modelscope\iic\SenseVoiceSmall"),
    (Join-Path $appRoot "models\SenseVoiceSmall")
)

if (-not $SourcePath) {
    foreach ($candidate in $defaultCandidates) {
        if (Test-Path $candidate -PathType Container) {
            $SourcePath = $candidate
            break
        }
    }
}

if (-not $SourcePath -or -not (Test-Path $SourcePath -PathType Container)) {
    throw "SenseVoiceSmall model folder was not found. Provide -SourcePath or place it under app\models\huggingface\modelscope\models\iic\SenseVoiceSmall."
}

$source = (Resolve-Path $SourcePath).Path
$output = New-Item -ItemType Directory -Force -Path $OutputDir
$assetName = "StreamTranslator-SenseVoiceSmall-Model-v$Version.zip"
$assetPath = Join-Path $output.FullName $assetName
$stageRoot = Join-Path $output.FullName "_sensevoice_model_package"
$packagedModelDir = Join-Path $stageRoot "models\huggingface\modelscope\models\iic\SenseVoiceSmall"

if (Test-Path $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
if (Test-Path $assetPath) {
    Remove-Item -LiteralPath $assetPath -Force
}

New-Item -ItemType Directory -Force -Path $packagedModelDir | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $packagedModelDir -Recurse -Force

$readmePath = Join-Path $stageRoot "README-SenseVoiceSmall.txt"
@"
Stream Translator SenseVoiceSmall model package

How to install:
1. Extract this zip into the Stream Translator application folder.
2. The model should end up at:
   models\huggingface\modelscope\models\iic\SenseVoiceSmall
3. CUDA, CPU, and ROCm packages can share the same extracted model folder.

This package avoids slow first-run downloads from ModelScope or Hugging Face.
"@ | Set-Content -Path $readmePath -Encoding UTF8

Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $assetPath -CompressionLevel Optimal
Remove-Item -LiteralPath $stageRoot -Recurse -Force

$hash = Get-FileHash -Algorithm SHA256 -Path $assetPath
Write-Host "Created: $assetPath"
Write-Host "SHA256: $($hash.Hash)  $assetName"
