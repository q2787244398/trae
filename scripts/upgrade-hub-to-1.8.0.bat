@echo off
REM ============================================================
REM  wb-proxy 1.7.33 -> 1.8.0 升级入口（双击运行）
REM
REM  使用前提：
REM    1. 本 bat 与 upgrade-hub-to-1.8.0.py 一起放在生产 wb-proxy 目录
REM       （即含 wb_proxy.py 的那个目录），不要留在 scripts 子目录里跑。
REM    2. 新版 7 个文件已就位，位于以下任一位置：
REM         - 环境变量 HUB_STAGE_DIR 指向的目录
REM         - 生产目录旁的 _pending-1.8.0\
REM
REM  建议先干跑：
REM    upgrade-hub-to-1.8.0.bat --dry-run
REM ============================================================
setlocal

set "HERE=%~dp0"
set "PY=%HERE%python\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo [hub-upgrade] interpreter: %PY%
echo [hub-upgrade] workdir    : %HERE%
echo.

"%PY%" "%HERE%upgrade-hub-to-1.8.0.py" %*

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0"  echo [hub-upgrade] SUCCESS - service running 1.8.0
if "%RC%"=="2"  echo [hub-upgrade] PREFLIGHT FAILED - nothing changed
if "%RC%"=="3"  echo [hub-upgrade] APPLY FAILED - rolled back
if "%RC%"=="4"  echo [hub-upgrade] HEALTH TIMEOUT - rolled back
if "%RC%"=="10" echo [hub-upgrade] DRY-RUN OK - nothing changed
echo [hub-upgrade] exit code = %RC%
echo.

if "%RC%"=="10" goto :done
pause
:done
endlocal & exit /b %RC%
