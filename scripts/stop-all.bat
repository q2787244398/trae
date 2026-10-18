@echo off
rem Double-click entry point for stopping everything.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1"
echo.
pause
