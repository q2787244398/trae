@echo off
rem Double-click entry point for the update check.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-update.ps1"
echo.
pause
