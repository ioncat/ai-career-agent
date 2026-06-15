@echo off
chcp 65001 >/dev/null
title JD Parser :8001
set "PY=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0\services\parser"
echo [JD Parser] http://localhost:8001
echo.
"%PY%" -m uvicorn app:app --port 8001
pause
