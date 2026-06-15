@echo off
chcp 65001 >nul
echo Starting Career Agent services...

set "ROOT=E:\My files\0 My_Dev\my_prj\career-agent"

start "Career Agent Bot"   /D "%ROOT%"               cmd /k "call .venv\Scripts\activate && python agent.py"
start "Web Tracker :8080"  /D "%ROOT%"               cmd /k "call .venv\Scripts\activate && python -m uvicorn web.api:app --port 8080 --reload"
start "Job Monitor (RSS)"  /D "%ROOT%"               cmd /k "call .venv\Scripts\activate && python services\job-monitor\monitor.py"
start "PDF Service :8002"  /D "%ROOT%\services\pdf"  cmd /k "call ..\..\.venv\Scripts\activate && python -m uvicorn app:app --port 8002"
start "JD Parser :8001"    /D "%ROOT%\services\parser" cmd /k "call ..\..\.venv\Scripts\activate && python -m uvicorn app:app --port 8001"

echo.
echo Opened 5 windows. Web Tracker: http://localhost:8080
pause
