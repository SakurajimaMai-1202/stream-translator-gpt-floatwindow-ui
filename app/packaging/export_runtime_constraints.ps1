#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("cuda", "cpu", "rocm")]
    [string]$Profile,
    [string]$RuntimeDir
)

$ErrorActionPreference = "Stop"
$appDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "runtime_profile_packaging.ps1")
$packageInfo = Get-RuntimeProfilePackageInfo -RuntimeProfile $Profile
if (-not $RuntimeDir) {
    $RuntimeDir = Join-Path (Join-Path (Join-Path $appDir $packageInfo.DistDirName) $packageInfo.PackageName) "_runtime"
}
$RuntimeDir = (Resolve-Path -LiteralPath $RuntimeDir).Path
$pythonExe = Join-Path $RuntimeDir "python.exe"
$manifestPath = Join-Path $RuntimeDir "runtime-version.json"
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "Runtime Python not found: $pythonExe"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
if (-not $manifest.python -or -not $manifest.app_version) {
    throw "Runtime manifest must contain python and app_version: $manifestPath"
}
if ($manifest.profile -and $manifest.profile -ne $Profile) {
    throw "Runtime profile mismatch: expected '$Profile', got '$($manifest.profile)'."
}

$exportScript = @'
import importlib.metadata as metadata
import json
import re

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()

packages = {}
for distribution in metadata.distributions():
    name = distribution.metadata.get("Name")
    if not name or normalize(name) in {"pip", "setuptools", "wheel", "stream-translator-gpt"}:
        continue
    key = normalize(name)
    if key in packages and packages[key][1] != distribution.version:
        raise RuntimeError(f"Conflicting installed versions for {name}")
    packages[key] = (name, distribution.version)
print(json.dumps([{"name": name, "version": version} for name, version in sorted(packages.values())], ensure_ascii=True))
'@
$json = & $pythonExe -I -c $exportScript
if ($LASTEXITCODE -ne 0) {
    throw "Runtime metadata export failed: $pythonExe"
}
$packages = $json | ConvertFrom-Json
$torch = $packages | Where-Object { $_.name -ieq "torch" } | Select-Object -First 1
$pythonNote = if ($Profile -eq "cpu") {
    "；無 torch，sherpa-onnx"
} elseif ($Profile -eq "rocm" -and $torch) {
    "；torch $($torch.version.Split('+')[0]) 自建 ROCm wheel，無法從公開索引安裝"
} elseif ($torch) {
    "；torch $($torch.version)"
} else {
    ""
}
$lines = @(
    "# $Profile profile runtime 實際發布版本（由 v$($manifest.app_version) 發布包 _runtime 匯出）",
    "# Python $($manifest.python)$pythonNote",
    "# 用法：pip install -r requirements.txt -c constraints/runtime-$Profile.txt",
    "# 重新產生：packaging/export_runtime_constraints.ps1"
)
foreach ($package in $packages) {
    $name = [string]$package.name
    $version = [string]$package.version
    $line = "$name==$version"
    if ($name -ieq "yt-dlp") {
        $line = "# $line  （打包時刻意更新為最新版，不鎖定）"
    } elseif ($Profile -eq "rocm" -and $name -in @("torch", "torchaudio") -and $version.Contains('+')) {
        $line = "# $line  （自建 ROCm wheel，需手動安裝）"
    }
    $lines += $line
}
$outputPath = Join-Path $appDir "constraints\runtime-$Profile.txt"
Write-Utf8NoBomTextFile -Path $outputPath -Text ($lines -join "`n")
Write-Host "已匯出 / Exported runtime constraints: $outputPath" -ForegroundColor Green
