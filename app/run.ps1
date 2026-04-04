#!/usr/bin/env pwsh
# UI2 快速啟動腳本（開發模式）

Write-Host "=== YouTube Live Translator UI2 ===" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

try {
    # 檢查依賴
    Write-Host "檢查 Python 依賴..." -ForegroundColor Yellow
    
    $requirements = Join-Path $PSScriptRoot "requirements.txt"
    if (Test-Path $requirements) {
        python -m pip install -q -r $requirements
    }
    
    # 檢查前端依賴
    $frontendDir = Join-Path $PSScriptRoot "frontend"
    $nodeModules = Join-Path $frontendDir "node_modules"
    
    if (-not (Test-Path $nodeModules)) {
        Write-Host "安裝前端依賴..." -ForegroundColor Yellow
        Set-Location $frontendDir
        npm install
        Set-Location $PSScriptRoot
    }
    
    Write-Host "✅ 依賴檢查完成" -ForegroundColor Green
    Write-Host ""
    
    # 啟動應用程式
    Write-Host "啟動 UI2 應用程式（開發模式）..." -ForegroundColor Cyan
    Write-Host ""
    
    python main.py
    
} catch {
    Write-Host ""
    Write-Host "❌ 啟動失敗: $_" -ForegroundColor Red
    exit 1
}
