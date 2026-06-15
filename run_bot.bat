@echo off
chcp 65001 >/dev/null
title Career Agent Bot
set "PY=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0"
echo [Career Agent Bot] Starting...
echo.
"%PY%" agent.py
pause
