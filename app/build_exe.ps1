#!/usr/bin/env pwsh

& (Join-Path $PSScriptRoot "packaging\build_legacy.ps1")
exit $LASTEXITCODE
