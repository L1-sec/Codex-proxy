@echo off

:: 1. 新开一个CMD窗口，运行代理
start "codex_proxy.py" cmd /k "py -3.10 codex_proxy.py"

:: 2. 等待 0.3 秒（精确延迟）
ping -n 1 -w 300 127.0.0.1 >nul

codex.exe

pause
