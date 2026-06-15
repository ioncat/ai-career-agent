@echo off
chcp 65001 >/dev/null
title Job Monitor (RSS)
set "PY=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0"
echo [Job Monitor] RSS poll every 5 min...
echo.
"%PY%" services\job-monitor\monitor.py
pause
