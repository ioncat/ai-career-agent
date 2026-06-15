@echo off
chcp 65001 >/dev/null
title Web Tracker :8080
set "PY=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0"
echo [Web Tracker] http://localhost:8080
echo.
"%PY%" -m uvicorn web.api:app --port 8080 --reload
pause
