"""
Career Agent — single-window launcher.
Starts all services sequentially, waits for each to report ready before starting next.
Ctrl+C stops everything.

Terminal shows: ERROR/CRITICAL from all services + full job-monitor output.
Full logs written per-service to logs/<name>.log.
"""

import subprocess
import sys
import threading
import signal
import time
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

_ENV = os.environ.copy()
_ENV["PYTHONIOENCODING"] = "utf-8"
# Claude Code CLI lives in %LOCALAPPDATA%\..\local\bin — not in cmd.exe PATH by default.
_claude_bin = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin"
if _claude_bin.exists():
    _ENV["PATH"] = str(_claude_bin) + os.pathsep + _ENV.get("PATH", "")

# Lines containing these tokens are always shown in terminal (all services).
_CRITICAL_TOKENS = ("ERROR", "CRITICAL", "Traceback", "Exception", "exited unexpectedly")

SERVICES = [
    {
        "name": "PDF      :8002",
        "cmd": [PY, "-m", "uvicorn", "app:app", "--port", "8002"],
        "cwd": ROOT / "services" / "pdf",
        "ready": "Application startup complete",
        "log": "pdf.log",
        "verbose": False,
    },
    {
        "name": "Parser   :8001",
        "cmd": [PY, "-m", "uvicorn", "app:app", "--port", "8001"],
        "cwd": ROOT / "services" / "parser",
        "ready": "Application startup complete",
        "log": "parser.log",
        "verbose": False,
    },
    {
        "name": "Bot",
        "cmd": [PY, str(ROOT / "agent.py")],
        "cwd": ROOT,
        "ready": "career-agent starting",
        "log": "bot.log",
        "verbose": False,
    },
    {
        "name": "Monitor",
        "cmd": [PY, str(ROOT / "services" / "job-monitor" / "monitor.py")],
        "cwd": ROOT,
        "ready": "Interval:",  # always printed regardless of first-launch vs resume
        "log": "monitor.log",
        "verbose": True,  # all monitor output → terminal
    },
]

processes: list[subprocess.Popen] = []
_lock = threading.Lock()


def _make_file_logger(log_name: str) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        LOGS_DIR / log_name, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    return handler


def _should_print(line: str, verbose: bool) -> bool:
    if verbose:
        return True
    return any(tok in line for tok in _CRITICAL_TOKENS)


def stream(
    proc: subprocess.Popen,
    label: str,
    ready_event: threading.Event | None,
    ready_signal: str | None,
    log_name: str,
    verbose: bool,
) -> None:
    handler = _make_file_logger(log_name)
    for raw in iter(proc.stdout.readline, b""):
        line = raw.decode("utf-8", errors="replace").rstrip()
        handler.stream.write(f"[{label}] {line}\n")
        handler.stream.flush()
        if _should_print(line, verbose):
            print(f"  [{label}] {line}", flush=True)
        if ready_event and not ready_event.is_set() and ready_signal and ready_signal in line:
            ready_event.set()


def start(svc: dict) -> subprocess.Popen:
    label = svc["name"]
    proc = subprocess.Popen(
        svc["cmd"],
        cwd=svc["cwd"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        env=_ENV,
    )
    with _lock:
        processes.append(proc)

    ready_event = threading.Event() if svc["ready"] else None
    t = threading.Thread(
        target=stream,
        args=(proc, label, ready_event, svc["ready"], svc["log"], svc["verbose"]),
        daemon=True,
    )
    t.start()

    if ready_event:
        ready_event.wait(timeout=30)
        print(f"  [{label}] ✓ ready", flush=True)
    else:
        time.sleep(1)

    return proc


def shutdown(*_):
    print("\nStopping all services...", flush=True)
    with _lock:
        for p in processes:
            try:
                # CTRL_BREAK_EVENT allows Python finally/atexit to run (releases locks etc.)
                p.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
    time.sleep(2)
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)

print("=" * 50)
print("  Career Agent — starting services")
print("=" * 50)

for svc in SERVICES:
    print(f"\n→ {svc['name']}", flush=True)
    start(svc)

print("\n" + "=" * 50)
print("  All services running.  Ctrl+C to stop.")
print("=" * 50 + "\n")

reported_dead: set[int] = set()

try:
    while True:
        time.sleep(2)
        for svc, proc in zip(SERVICES, processes):
            if proc.pid in reported_dead:
                continue
            rc = proc.poll()
            if rc is not None:
                print(f"[!] [{svc['name'].strip()}] exited (code {rc})", flush=True)
                reported_dead.add(proc.pid)
except KeyboardInterrupt:
    shutdown()
