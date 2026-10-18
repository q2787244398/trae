@echo off
rem Double-click entry point. All logic lives in start-all.ps1.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"
echo.
pause
