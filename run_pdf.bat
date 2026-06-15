@echo off
chcp 65001 >/dev/null
title PDF Service :8002
set "PY=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0\services\pdf"
echo [PDF Service] http://localhost:8002
echo.
"%PY%" -m uvicorn app:app --port 8002
pause
