@echo off
chcp 65001 >nul
echo Starting Career Agent services...

set "ROOT=E:\My files\0 My_Dev\my_prj\career-agent"

:: ── Telegram bot + RSS watcher (agent.py includes rss_watcher) ──────────────
start /D "%ROOT%" "Career Agent Bot" cmd /k ".venv\Scripts\activate && python agent.py"

:: ── Web Tracker dashboard ────────────────────────────────────────────────────
start /D "%ROOT%" "Web Tracker :8080" cmd /k ".venv\Scripts\activate && uvicorn web.api:app --port 8080 --reload"

:: ── RSS monitor → POST /api/new-vacancy (polls feeds every 5 min) ────────────
start /D "%ROOT%" "Job Monitor (RSS)" cmd /k ".venv\Scripts\activate && python services\job-monitor\monitor.py"

:: ── PDF render service (needed for CV → PDF) ─────────────────────────────────
start /D "%ROOT%\services\pdf" "PDF Service :8002" cmd /k "..\..\.venv\Scripts\activate && uvicorn app:app --port 8002"

:: ── JD parser (needed for URL → Markdown) ────────────────────────────────────
start /D "%ROOT%\services\parser" "JD Parser :8001" cmd /k "..\..\.venv\Scripts\activate && uvicorn app:app --port 8001"

echo.
echo Opened 5 windows: Bot, Web Tracker, Job Monitor, PDF Service, JD Parser
echo Web Tracker: http://localhost:8080
pause
