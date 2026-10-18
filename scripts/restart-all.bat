@echo off
rem Restart everything: stop, wait, start. Double-click entry point.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo Restarting Trae2api-cn ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1"
timeout /t 2 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1"

echo.
pause
