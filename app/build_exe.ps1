#!/usr/bin/env pwsh

Write-Host "build_exe.ps1 is legacy. Prefer: .\build_release.ps1 -Profile cuda" -ForegroundColor Yellow
& (Join-Path $PSScriptRoot "packaging\legacy\build_legacy.ps1")
exit $LASTEXITCODE
