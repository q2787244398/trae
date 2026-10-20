@echo off
rem ============================================================
rem relay 常驻启动脚本（Windows 本机部署通用版）
rem
rem 用法：
rem   1) 安装依赖：pip install -r requirements.txt
rem   2) 修改下方 RELAY_DIR / DEPS 指向你的部署目录
rem   3) 双击运行，或注册为开机自启计划任务
rem
rem 关键点：解释器默认找不到 uvicorn，必须把依赖目录加入
rem PYTHONPATH（relay-deps 或 venv 的 site-packages）
rem ============================================================
setlocal enabledelayedexpansion

rem ---------- 按需修改的配置 ----------
set "RELAY_DIR=%~dp0..\relay"
set "HOST=127.0.0.1"
set "PORT=8000"
set "PYTHON=python"
rem 依赖目录，留空则使用解释器自身环境
set "DEPS=%~dp0..\relay-deps"
rem -----------------------------------

if not exist "%RELAY_DIR%\src\main.py" (
    echo [错误] 未找到 relay 源码：%RELAY_DIR%\src\main.py
    echo请修改本脚本顶部的 RELAY_DIR 指向实际部署目录。
    pause
    exit /b 1
)

rem 端口已监听则退出，避免重复启动
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [跳过] relay 已在运行，端口 %PORT% 正常监听。
    exit /b 0
)

echo [启动] Trae CN Relay ...
cd /d "%RELAY_DIR%"

if exist "%DEPS%" (
    if "!PYTHONPATH!" == "" (
        set "PYTHONPATH=%DEPS%"
    ) else (
        set "PYTHONPATH=%DEPS%;!PYTHONPATH!"
    )
    echo [环境] PYTHONPATH=%DEPS%
)

rem 用 start 彻底脱离当前会话，避免父进程退出时连带终止
start "trae-relay" /min "%PYTHON%" -m uvicorn src.main:app --host %HOST% --port %PORT% --log-level warning

set /a COUNT=0
:WAIT
timeout /t 2 /nobreak >nul
set /a COUNT+=1
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 goto DONE
if !COUNT! lss 15 goto WAIT

echo [失败] relay 未能在 30 秒内就绪。
echo请检查依赖：pip install -r requirements.txt
pause
exit /b 1

:DONE
echo [完成] relay 已启动，监听 %HOST%:%PORT%
timeout /t 3 >nul
exit /b 0
