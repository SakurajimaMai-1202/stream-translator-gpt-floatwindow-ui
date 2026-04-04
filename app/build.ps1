#!/usr/bin/env pwsh
# 構建前端生產版本並整合至後端

Write-Host "=== UI2 生產構建腳本 ===" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"
$frontendDir = Join-Path $PSScriptRoot "frontend"
$backendDir = Join-Path $PSScriptRoot "backend"
$distDir = Join-Path $frontendDir "dist"
$staticDir = Join-Path $backendDir "static"

try {
    # 1. 構建前端
    Write-Host "[1/3] 構建 Vue 前端..." -ForegroundColor Yellow
    Set-Location $frontendDir
    
    if (-not (Test-Path "node_modules")) {
        Write-Host "安裝前端依賴..." -ForegroundColor Yellow
        npm install
    }
    
    npm run build
    
    if (-not (Test-Path $distDir)) {
        throw "前端構建失敗：dist 目錄不存在"
    }
    
    Write-Host "✅ 前端構建完成" -ForegroundColor Green
    
    # 2. 複製到後端靜態目錄
    Write-Host "[2/3] 複製靜態檔案至後端..." -ForegroundColor Yellow
    
    if (Test-Path $staticDir) {
        Remove-Item -Recurse -Force $staticDir
    }
    
    Copy-Item -Recurse $distDir $staticDir
    Write-Host "✅ 靜態檔案已複製" -ForegroundColor Green
    
    # 3. 更新後端 main.py 以服務靜態檔案
    Write-Host "[3/3] 更新後端配置..." -ForegroundColor Yellow
    
    $mainPy = Join-Path $backendDir "main.py"
    $content = Get-Content $mainPy -Raw
    
    # 取消註解靜態檔案服務
    $content = $content -replace '# (dist_path = Path.*)', '$1'
    $content = $content -replace '# (if dist_path\.exists.*)', '$1'
    $content = $content -replace '#     (app\.mount.*)', '    $1'
    
    # 更新 dist_path 指向
    $content = $content -replace 'parent\.parent / "frontend" / "dist"', 'parent / "static"'
    
    Set-Content $mainPy $content -NoNewline
    
    Write-Host "✅ 後端配置已更新" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host "✅ 生產構建完成！" -ForegroundColor Green
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host ""
    Write-Host "啟動方式：" -ForegroundColor Cyan
    Write-Host "  開發模式: python main.py" -ForegroundColor Gray
    Write-Host "  生產模式: python main.py --prod" -ForegroundColor Gray
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "❌ 構建失敗: $_" -ForegroundColor Red
    exit 1
} finally {
    Set-Location $PSScriptRoot
}
