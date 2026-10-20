@echo off
rem ============================================================
rem 网络一键修复脚本（断网时使用，无需重启电脑）
rem 用法：右键 -> 以管理员身份运行
rem ============================================================
echo [1/4] 禁用以太网适配器...
netsh interface set interface name="以太网" admin=disabled
timeout /t 3 >nul

echo [2/4] 重新启用以太网适配器...
netsh interface set interface name="以太网" admin=enabled
timeout /t 5 >nul

echo [3/4] 清理 DNS 缓存...
ipconfig /flushdns

echo [4/4] 重新获取 IP 地址...
ipconfig /release >nul 2>nul
ipconfig /renew >nul 2>nul

echo.
echo [完成] 网络已重置，请检查网络连接。
timeout /t 5 >nul
