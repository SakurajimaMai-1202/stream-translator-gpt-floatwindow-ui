#!/usr/bin/env pwsh
param(
    [string]$Server = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$candidate = Join-Path $scriptDir "..\.venv\Scripts\python.exe"
$python = "python"

if (Test-Path $candidate) {
    & $candidate --version *> $null
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
    }
}

$entry = Join-Path $scriptDir "remote_subtitle_window.py"

if ($Server) {
    & $python $entry --server $Server
} else {
    & $python $entry
}
