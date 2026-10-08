#!/usr/bin/env python3
"""
scripts/health_check.py — Lightweight service health monitor.

PURPOSE
-------
Fast no-cost check that all career-agent services are alive.
Does NOT call Claude API — DB and HTTP only.

CHECKS
------
    :PARSER_URL/health   — jd-parser (fetches JDs from web)
    :8002/health         — pdf-service (renders PDFs)
    db/agent.db          — SQLite reachable (SELECT 1)
    Telegram ping        — optional, only if --telegram flag
    job-monitor feeds    — optional, only if --monitor flag: reads the monitor's
                           feed_health.json; fails if a feed has an unrecovered
                           failure alert or its last check is older than
                           --monitor-max-age minutes (monitor stopped)

OUTPUT
------
    Console: one line per check, ✅/❌ prefix
    Exit 0  — all checks passed
    Exit 1  — one or more checks failed

TELEGRAM ALERT
--------------
    Sent if --telegram and any check failed.
    Uses TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env.

USAGE
-----
    python scripts/health_check.py
    python scripts/health_check.py --telegram
    python scripts/health_check.py --pdf-url http://localhost:9002

SCHEDULE (Windows Task Scheduler)
----------------------------------
    Program:  python
    Args:     scripts/health_check.py --telegram
    Start in: E:\\path\\to\\career-agent
"""

import argparse
import asyncio
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass


# ── Config ────────────────────────────────────────────────────────────────────

PARSER_URL  = os.getenv("PARSER_URL", "http://localhost:8001")
PDF_URL     = os.getenv("PDF_SERVICE_URL", "http://localhost:8002")
DB_PATH     = Path(os.getenv("DB_PATH", str(_ROOT / "db" / "agent.db")))
BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "")

HTTP_TIMEOUT = 5  # seconds per request

# job-monitor writes feed_health.json into its DATA_DIR (default: its own folder).
MONITOR_DIR = Path(os.getenv("JOB_MONITOR_DATA_DIR", str(_ROOT / "services" / "job-monitor")))
MONITOR_MAX_AGE_MIN = 30  # monitor polls every 5 minutes by default


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


# ── Checks ────────────────────────────────────────────────────────────────────

async def check_http(name: str, url: str) -> CheckResult:
    """GET {url}/health → expect 200 + {"status":"ok"}."""
    import urllib.request
    import urllib.error
    import json

    health_url = url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(health_url, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            if data.get("status") == "ok":
                return CheckResult(name, ok=True, detail=health_url)
            return CheckResult(name, ok=False, detail=f"unexpected body: {body[:80]}")
    except urllib.error.URLError as exc:
        return CheckResult(name, ok=False, detail=str(exc.reason))
    except Exception as exc:
        return CheckResult(name, ok=False, detail=str(exc)[:120])


def check_db() -> CheckResult:
    """SQLite reachable: SELECT 1 from agent.db."""
    if not DB_PATH.exists():
        return CheckResult("sqlite", ok=False, detail=f"file not found: {DB_PATH}")
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        # Also count vacancies as a sanity check
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        count = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        conn.close()
        return CheckResult("sqlite", ok=True, detail=f"{DB_PATH.name} ({count} vacancies)")
    except Exception as exc:
        return CheckResult("sqlite", ok=False, detail=str(exc)[:120])


async def check_telegram_bot() -> CheckResult:
    """Telegram getMe — confirms bot token is valid."""
    if not BOT_TOKEN:
        return CheckResult("telegram", ok=False, detail="TELEGRAM_BOT_TOKEN not set")
    import urllib.request
    import json

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                bot_name = data["result"].get("username", "?")
                return CheckResult("telegram", ok=True, detail=f"@{bot_name}")
            return CheckResult("telegram", ok=False, detail=str(data))
    except Exception as exc:
        return CheckResult("telegram", ok=False, detail=str(exc)[:120])


def check_monitor(
    monitor_dir: Path | None = None,
    max_age_minutes: int = MONITOR_MAX_AGE_MIN,
    now: datetime | None = None,
) -> CheckResult:
    """job-monitor feeds: read feed_health.json (written by services/job-monitor/monitor.py).

    Fails when the file is missing or unreadable, when a feed carries an unrecovered
    failure alert (`alerted`), or when a feed's last check is older than
    max_age_minutes (the monitor is not running).
    """
    import json

    path = Path(monitor_dir or MONITOR_DIR) / "feed_health.json"
    if not path.exists():
        return CheckResult("job-monitor", ok=False, detail=f"no state file: {path}")
    try:
        health = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(health, dict):
            raise ValueError("not a JSON object")
    except Exception as exc:
        return CheckResult("job-monitor", ok=False, detail=f"unreadable {path.name}: {str(exc)[:80]}")
    if not health:
        return CheckResult("job-monitor", ok=False, detail="no feeds recorded yet")

    now = now or datetime.now()
    problems: list[str] = []
    for name, h in sorted(health.items()):
        failures = int(h.get("consecutive_failures", 0) or 0)
        if h.get("alerted"):
            problems.append(f"{name}: failing ({failures} checks in a row)")
            continue
        last = h.get("last_check")
        try:
            age_ok = now - datetime.fromisoformat(last) <= timedelta(minutes=max_age_minutes)
        except (TypeError, ValueError):
            age_ok = False
        if not age_ok:
            problems.append(f"{name}: stale (last check {last or 'never'})")
    if problems:
        return CheckResult("job-monitor", ok=False, detail="; ".join(problems))
    return CheckResult("job-monitor", ok=True, detail=f"{len(health)} feed(s) healthy")


# ── Alert ─────────────────────────────────────────────────────────────────────

async def send_telegram_alert(failures: list[CheckResult]) -> None:
    """Send Telegram message listing failed checks."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️  Telegram alert skipped: BOT_TOKEN or CHAT_ID not set")
        return

    import urllib.request
    import urllib.parse
    import json

    lines = ["🔴 career-agent health check FAILED\n"]
    for f in failures:
        lines.append(f"❌ {f.name}: {f.detail}")

    text = "\n".join(lines)
    payload = json.dumps({"chat_id": CHAT_ID, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}),
            timeout=HTTP_TIMEOUT,
        ) as resp:
            resp.read()
        print("📨  Telegram alert sent")
    except Exception as exc:
        print(f"⚠️  Telegram alert failed: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> int:
    pdf_url = args.pdf_url or PDF_URL
    parser_url = args.parser_url or PARSER_URL

    results: list[CheckResult] = []

    # HTTP checks (run in parallel)
    http_tasks = [
        check_http("parser", parser_url),
        check_http("pdf-service", pdf_url),
    ]
    if args.telegram:
        http_tasks.append(check_telegram_bot())

    http_results = await asyncio.gather(*http_tasks)
    results.extend(http_results)

    # DB check (sync — fast)
    results.append(check_db())

    if args.monitor:
        results.append(check_monitor(
            Path(args.monitor_dir) if args.monitor_dir else None,
            args.monitor_max_age,
        ))

    # Print results
    all_ok = True
    for r in results:
        icon = "✅" if r.ok else "❌"
        detail = f"  ({r.detail})" if r.detail else ""
        print(f"{icon}  {r.name}{detail}")
        if not r.ok:
            all_ok = False

    # Alert
    if not all_ok and args.telegram:
        failures = [r for r in results if not r.ok]
        await send_telegram_alert(failures)

    return 0 if all_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lightweight health check for career-agent services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--telegram", action="store_true",
        help="Also check Telegram bot token + send alert on failure",
    )
    parser.add_argument(
        "--monitor", action="store_true",
        help="Also check the job-monitor feeds (feed_health.json): failing or stale feeds fail the run",
    )
    parser.add_argument(
        "--monitor-dir", default=None,
        help=f"Folder holding the monitor's feed_health.json (default: {MONITOR_DIR})",
    )
    parser.add_argument(
        "--monitor-max-age", type=int, default=MONITOR_MAX_AGE_MIN,
        help=f"Minutes without a monitor check before a feed counts as stale (default: {MONITOR_MAX_AGE_MIN})",
    )
    parser.add_argument(
        "--pdf-url", default=None,
        help=f"PDF service URL (default: {PDF_URL})",
    )
    parser.add_argument(
        "--parser-url", default=None,
        help=f"Parser service URL (default: {PARSER_URL})",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
