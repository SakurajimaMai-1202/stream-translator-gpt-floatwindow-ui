@echo off
REM Windows 批次檔啟動腳本

echo ========================================
echo YouTube Live Translator UI2
echo ========================================
echo.

REM 啟動虛擬環境
call venv\Scripts\activate.bat

REM 啟動應用程式
python main.py

pause
