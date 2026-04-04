#!/usr/bin/env pwsh
# UI2 開發伺服器啟動腳本

Write-Host "=== YouTube Live Translator UI2 開發環境 ===" -ForegroundColor Cyan
Write-Host ""

# 啟動後端
Write-Host "[1/2] 啟動 FastAPI 後端 (Port 8000)..." -ForegroundColor Yellow
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\backend'; python main.py"

# 等待後端啟動
Start-Sleep -Seconds 3

# 啟動前端
Write-Host "[2/2] 啟動 Vite 前端 (Port 5173)..." -ForegroundColor Yellow
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; npm run dev"

Write-Host ""
Write-Host "✅ 開發環境已啟動！" -ForegroundColor Green
Write-Host "   - 後端 API: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "   - API 文件: http://127.0.0.1:8000/api/docs" -ForegroundColor Cyan
Write-Host "   - 前端應用: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "按 Ctrl+C 關閉此視窗 (後端/前端會在獨立視窗繼續執行)" -ForegroundColor Gray
