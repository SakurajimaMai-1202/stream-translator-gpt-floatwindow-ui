#!/usr/bin/env pwsh
param(
    [switch]$AllowMissingRocm,
    [ValidateSet("auto", "cuda", "cpu", "rocm")]
    [string]$CpuExpectedTorchBackend = "auto"
)

$ErrorActionPreference = "Stop"
$packagingDir = $PSScriptRoot

$profiles = @(
    [pscustomobject]@{ Profile = "cuda"; ExpectedTorchBackend = "cuda"; MissingAllowed = $false },
    [pscustomobject]@{ Profile = "cpu"; ExpectedTorchBackend = $CpuExpectedTorchBackend; MissingAllowed = $false },
    [pscustomobject]@{ Profile = "rocm"; ExpectedTorchBackend = "rocm"; MissingAllowed = [bool]$AllowMissingRocm }
)

$results = @()
foreach ($profileSpec in $profiles) {
    $output = $null
    try {
        $global:LASTEXITCODE = 0
        $output = & (Join-Path $packagingDir "validate_runtime_artifact.ps1") `
            -Profile $profileSpec.Profile `
            -ExpectedTorchBackend $profileSpec.ExpectedTorchBackend 2>&1
        $artifactExitCode = $LASTEXITCODE
        if ($artifactExitCode -ne 0) {
            throw ($output | Out-String)
        }
        $results += [pscustomobject]@{
            Profile = $profileSpec.Profile
            Status = "ok"
            ExpectedTorchBackend = $profileSpec.ExpectedTorchBackend
            Detail = "artifact valid"
        }
    } catch {
        $status = if ($profileSpec.MissingAllowed) { "missing-allowed" } else { "failed" }
        $results += [pscustomobject]@{
            Profile = $profileSpec.Profile
            Status = $status
            ExpectedTorchBackend = $profileSpec.ExpectedTorchBackend
            Detail = ($_.Exception.Message -replace "\s+", " ").Trim()
        }
    }
}

$results | Format-Table -AutoSize

$failed = $results | Where-Object { $_.Status -eq "failed" }
if ($failed) {
    throw "Runtime artifact matrix validation failed for: $($failed.Profile -join ', ')"
}

if ($AllowMissingRocm) {
    Write-Host "Runtime artifact matrix OK with missing ROCm allowed." -ForegroundColor Yellow
} else {
    Write-Host "Runtime artifact matrix OK." -ForegroundColor Green
}
