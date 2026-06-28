@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo Stream Translator Full Package Merger
echo =====================================
echo.
echo Put this file in the same folder as the .part files, then run it.
echo.

set "FOUND=0"
call :merge "StreamTranslator-win64-CUDA-Full.zip"
call :merge "StreamTranslator-win64-CPU-Full.zip"
call :merge "StreamTranslator-win64-ROCm-Experimental-Full.zip"

if "%FOUND%"=="0" (
  echo No supported .part files were found in:
  echo %CD%
  echo.
  echo Expected one of:
  echo   StreamTranslator-win64-CUDA-Full.zip.part01
  echo   StreamTranslator-win64-CPU-Full.zip.part01
  echo   StreamTranslator-win64-ROCm-Experimental-Full.zip.part01
  echo.
)

echo Done.
pause
exit /b 0

:merge
set "TARGET=%~1"
if not exist "%TARGET%.part01" exit /b 0

set "FOUND=1"
echo Found: %TARGET%.part*

if exist "%TARGET%" (
  set "ANSWER="
  set /p "ANSWER=%TARGET% already exists. Overwrite? [y/N] "
  if /I not "!ANSWER!"=="Y" (
    echo Skipped: %TARGET%
    echo.
    exit /b 0
  )
  del /f /q "%TARGET%" >nul 2>nul
)

set "PARTS="
for /f "delims=" %%F in ('dir /b /on "%TARGET%.part*" 2^>nul') do (
  set "PARTS=!PARTS!+"%%F""
)
set "PARTS=!PARTS:~1!"

echo Merging into %TARGET% ...
copy /b !PARTS! "%TARGET%" >nul
if errorlevel 1 (
  echo Failed to merge %TARGET%.
  echo Please check that all parts are downloaded and not blocked by antivirus.
  echo.
  exit /b 1
)

echo Created: %TARGET%
echo.
exit /b 0
