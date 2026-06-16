"""
Career Agent — single-window launcher.
Starts all services sequentially, waits for each to report ready before starting next.
Ctrl+C stops everything.
"""

import subprocess
import sys
import threading
import signal
import time
import os
from pathlib import Path

ROOT = Path(__file__).parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

SERVICES = [
    {
        "name": "Tracker  :8080",
        "cmd": [PY, "-m", "uvicorn", "web.api:app", "--port", "8080", "--reload"],
        "cwd": ROOT,
        "ready": "Application startup complete",
    },
    {
        "name": "PDF      :8002",
        "cmd": [PY, "-m", "uvicorn", "app:app", "--port", "8002"],
        "cwd": ROOT / "services" / "pdf",
        "ready": "Application startup complete",
    },
    {
        "name": "Parser   :8001",
        "cmd": [PY, "-m", "uvicorn", "app:app", "--port", "8001"],
        "cwd": ROOT / "services" / "parser",
        "ready": "Application startup complete",
    },
    {
        "name": "Monitor",
        "cmd": [PY, str(ROOT / "services" / "job-monitor" / "monitor.py")],
        "cwd": ROOT,
        "ready": "Watching for new listings",
    },
    {
        "name": "Bot",
        "cmd": [PY, str(ROOT / "agent.py")],
        "cwd": ROOT,
        "ready": "career-agent starting",
    },
]

processes: list[subprocess.Popen] = []
_lock = threading.Lock()


def stream(proc: subprocess.Popen, label: str, ready_event: threading.Event | None, ready_signal: str | None) -> None:
    for raw in iter(proc.stdout.readline, b""):
        line = raw.decode("utf-8", errors="replace").rstrip()
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
    )
    with _lock:
        processes.append(proc)

    ready_event = threading.Event() if svc["ready"] else None
    t = threading.Thread(target=stream, args=(proc, label, ready_event, svc["ready"]), daemon=True)
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
                p.terminate()
            except Exception:
                pass
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

try:
    while True:
        time.sleep(2)
        dead = [p for p in processes if p.poll() is not None]
        if dead:
            print(f"[!] {len(dead)} service(s) exited unexpectedly", flush=True)
except KeyboardInterrupt:
    shutdown()
