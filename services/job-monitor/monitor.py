"""
Job vacancy monitor — multi-feed, webhook push to career-agent.

Each feed entry specifies user_ids (env var labels resolving to career-agent user IDs).
New vacancies are pushed via POST {CAREER_AGENT_URL}/api/new-vacancy instead of Telegram.

Usage:
    python monitor.py                # check every 5 minutes
    python monitor.py --interval 10  # check every 10 minutes
    python monitor.py --once         # single check and exit
    python monitor.py --debug        # show feed contents, no notifications
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import aiohttp

_BASE = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent)))
_PROJECT = Path(__file__).parent
LOG_FILE = _BASE / "monitor.log"
STATE_FILE = _BASE / "seen_jobs.json"
LOCK_FILE = _BASE / "monitor.lock"
FEEDS_FILE = _PROJECT / "feeds.json"
CONFIG_FILE = _PROJECT / "config.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (vacancy-monitor/1.0)"}

# Defaults applied when config.json is missing or a field is omitted.
DEFAULT_CONFIG = {
    "interval_minutes": 5,
    "http_timeout": {"total_seconds": 30, "connect_seconds": 10},
    "check_timeout_seconds": 120,
    "retry": {"backoff_schedule_seconds": [60, 300, 1800, 7200]},
    "logging": {"level": "INFO", "max_bytes": 10 * 1024 * 1024, "backup_count": 5},
}

# Mutable module globals — set by apply_config() in main() before async_main runs.
HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=DEFAULT_CONFIG["http_timeout"]["total_seconds"],
    connect=DEFAULT_CONFIG["http_timeout"]["connect_seconds"],
    sock_connect=DEFAULT_CONFIG["http_timeout"]["connect_seconds"],
    sock_read=DEFAULT_CONFIG["http_timeout"]["total_seconds"],
)
BACKOFF_SCHEDULE = list(DEFAULT_CONFIG["retry"]["backoff_schedule_seconds"])
MAX_ATTEMPTS = len(BACKOFF_SCHEDULE) + 1
CHECK_TIMEOUT: int = DEFAULT_CONFIG["check_timeout_seconds"]

# Salary extraction from DOU titles (e.g. "$1500–2000").
SALARY_RE = re.compile(r"\$\s*\d{1,5}(?:\s*[–—\-]\s*\d{1,5})?")

# Company extraction from DOU title: "Role в Company, ..." or "Role at Company, ..."
_COMPANY_DOU_RE = re.compile(r"\s+(?:в|у|at)\s+([^,\n]+)", re.IGNORECASE)
# Strip HTML tags for Djinni description parsing
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _extract_company_from_title(title: str) -> str:
    """Extract company from DOU-style title: 'Role в Company, ...' → 'Company'."""
    m = _COMPANY_DOU_RE.search(title)
    return m.group(1).strip() if m else ""


def _extract_company_from_description(description: str) -> str:
    """Extract company from Djinni RSS description HTML.

    Djinni descriptions typically start with the company name in <b> or plain text.
    Strategy: strip HTML, take first non-empty line.
    """
    if not description:
        return ""
    text = _HTML_TAG_RE.sub(" ", description)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # First line is usually company name on Djinni
    return lines[0][:80] if lines else ""


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    # Windows fallback via ctypes
    try:
        import ctypes
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle == 0:
            return False
        exit_code = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    except Exception:
        pass
    # POSIX fallback
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True


def acquire_lock() -> None:
    """Exit if another instance is already running. Auto-cleans stale locks."""
    if LOCK_FILE.exists():
        pid_str = LOCK_FILE.read_text().strip()
        try:
            pid = int(pid_str)
            if _pid_alive(pid):
                print(f"ERROR: another instance already running (PID {pid}). Exiting.")
                sys.exit(1)
            print(f"Stale lock (PID {pid} dead) — removing and continuing.")
            LOCK_FILE.unlink()
        except ValueError:
            LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))


def release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def setup_logging(level: str = "INFO", max_bytes: int = 10 * 1024 * 1024,
                  backup_count: int = 5) -> None:
    _BASE.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[file_handler, stream_handler],
        force=True,
    )


log = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write(f"WARNING: {CONFIG_FILE.name} invalid ({e}) — using defaults\n")
        return dict(DEFAULT_CONFIG)
    if not isinstance(user, dict):
        sys.stderr.write(f"WARNING: {CONFIG_FILE.name} must be a JSON object — using defaults\n")
        return dict(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user)


def apply_config(config: dict) -> None:
    global HTTP_TIMEOUT, BACKOFF_SCHEDULE, MAX_ATTEMPTS, CHECK_TIMEOUT
    ht = config["http_timeout"]
    HTTP_TIMEOUT = aiohttp.ClientTimeout(
        total=ht["total_seconds"],
        connect=ht["connect_seconds"],
        sock_connect=ht["connect_seconds"],
        sock_read=ht["total_seconds"],
    )
    BACKOFF_SCHEDULE = list(config["retry"]["backoff_schedule_seconds"])
    MAX_ATTEMPTS = len(BACKOFF_SCHEDULE) + 1
    CHECK_TIMEOUT = int(config.get("check_timeout_seconds", 120))


def load_feeds() -> list[dict]:
    """Read feeds.json and resolve user_id labels (e.g. CAREER_AGENT_USER_1) to
    career-agent user IDs via os.environ. Exits with a helpful error on misconfiguration."""
    if not FEEDS_FILE.exists():
        log.error(
            "%s missing. Copy feeds.example.json to feeds.json and edit it "
            "with your own feed URLs and user_ids.", FEEDS_FILE.name
        )
        sys.exit(1)
    try:
        raw = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log.error("%s invalid JSON: %s", FEEDS_FILE.name, e)
        sys.exit(1)
    if not isinstance(raw, list) or not raw:
        log.error("%s must be a non-empty JSON array", FEEDS_FILE.name)
        sys.exit(1)
    feeds = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            log.error("%s entry %d must be a JSON object", FEEDS_FILE.name, i)
            sys.exit(1)
        for field in ("name", "url", "user_ids"):
            if field not in entry:
                log.error("%s entry %d missing required field '%s'",
                          FEEDS_FILE.name, i, field)
                sys.exit(1)
        if not isinstance(entry["user_ids"], list) or not entry["user_ids"]:
            log.error("%s entry %r: 'user_ids' must be a non-empty list",
                      FEEDS_FILE.name, entry["name"])
            sys.exit(1)
        resolved = []
        for label in entry["user_ids"]:
            uid = os.environ.get(label)
            if not uid:
                log.error(
                    "%s entry %r references %s but env has no such variable",
                    FEEDS_FILE.name, entry["name"], label
                )
                sys.exit(1)
            try:
                resolved.append(int(uid))
            except ValueError:
                log.error("%s entry %r: %s=%r is not a valid integer user ID",
                          FEEDS_FILE.name, entry["name"], label, uid)
                sys.exit(1)
        feeds.append({"name": entry["name"], "url": entry["url"], "user_ids": resolved})
    return feeds


def load_env() -> str:
    """Load .env and return CAREER_AGENT_URL (the webhook endpoint base)."""
    env_file = Path(__file__).parent.parent.parent / ".env"  # project root
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    return os.environ.get("CAREER_AGENT_URL", "http://web-tracker:8080")


# ── State (seen_jobs.json) ────────────────────────────────────────────────────
#
# {
#   "https://jobs.example.com/123": {
#     "title": "Senior PM",
#     "feed": "DOU.ua — Product Manager",
#     "first_seen": "2026-05-14T14:41:13",
#     "delivery": {
#       "1": {                             # career-agent user_id as string key
#         "status": "sent" | "pending" | "failed",
#         "attempts": 0,
#         "last_attempt": "..." | null,
#         "last_error": "..." | null
#       }
#     }
#   }
# }


def new_delivery_entry() -> dict:
    return {"status": "pending", "attempts": 0, "last_attempt": None, "last_error": None}


def is_due_for_retry(delivery: dict, now: datetime) -> bool:
    if delivery["status"] != "pending":
        return False
    attempts = delivery["attempts"]
    if attempts >= MAX_ATTEMPTS:
        return False
    if attempts == 0 or not delivery.get("last_attempt"):
        return True
    last = datetime.fromisoformat(delivery["last_attempt"])
    delay = BACKOFF_SCHEDULE[attempts - 1]
    return now >= last + timedelta(seconds=delay)


def _build_state_entry(j: dict, feed: dict, now_iso: str, silent: bool) -> dict:
    initial = (
        {"status": "sent", "attempts": 0, "last_attempt": now_iso, "last_error": None}
        if silent
        else new_delivery_entry()
    )
    return {
        "title": j["title"],
        "feed": feed["name"],
        "first_seen": now_iso,
        "delivery": {str(uid): dict(initial) for uid in feed["user_ids"]},
    }


def migrate_state(state: dict, feeds: list[dict]) -> int:
    """Upgrade legacy per-job 'status' schema to per-recipient 'delivery' schema.
    Also handles old 'recipients' (Telegram chat_id) entries — marks as sent."""
    feed_by_name = {f["name"]: f for f in feeds}
    migrated = 0
    for link, entry in list(state.items()):
        if "delivery" in entry:
            continue
        old_status = entry.get("status", "sent")
        feed = feed_by_name.get(entry.get("feed", ""))
        user_ids = feed["user_ids"] if feed else []
        first_seen = entry.get("first_seen") or datetime.now().isoformat(timespec="seconds")
        delivery = {}
        for uid in user_ids:
            key = str(uid)
            if old_status == "sent":
                delivery[key] = {
                    "status": "sent", "attempts": 1,
                    "last_attempt": first_seen, "last_error": None,
                }
            else:
                delivery[key] = new_delivery_entry()
        state[link] = {
            "title": entry.get("title", ""),
            "feed": entry.get("feed", ""),
            "first_seen": first_seen,
            "delivery": delivery,
        }
        migrated += 1
    if migrated:
        log.info("Migrated %d state entries to per-user delivery schema", migrated)
    return migrated


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            log.info("Migrating seen_jobs.json from list to dict format")
            return {link: {"title": "", "status": "sent", "feed": "", "first_seen": ""} for link in data}
        return data
    except Exception as e:
        log.error("seen_jobs.json is corrupted (%s) — starting with empty state", e)
        backup = STATE_FILE.with_suffix(".json.bak")
        STATE_FILE.rename(backup)
        log.info("Corrupted state saved to %s", backup)
        return {}


def save_state(state: dict) -> None:
    try:
        _BASE.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.error("Failed to save state: %s", e)


def _parse_pub_date(pub_date: str) -> str | None:
    """Parse RFC 2822 pubDate to ISO 8601 UTC string. Returns None on failure."""
    if not pub_date:
        return None
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _resolve_company(title: str, description: str, feed_url: str) -> str:
    """Extract company name from RSS data depending on source."""
    if "dou.ua" in feed_url:
        return _extract_company_from_title(title)
    if "djinni.co" in feed_url:
        return _extract_company_from_description(description)
    # Fallback: try title pattern first, then description
    return _extract_company_from_title(title) or _extract_company_from_description(description)


async def post_to_career_agent(
    session: aiohttp.ClientSession,
    career_agent_url: str,
    url: str,
    title: str,
    feed_name: str,
    user_id: int,
    pub_date: str = "",
    company: str = "",
    salary: str = "",
) -> None:
    """POST new vacancy to career-agent webhook endpoint.

    409 → already queued/processed — treat as success (stop retrying).
    4xx/5xx → raise RuntimeError so deliver_one records the failure.
    """
    endpoint = f"{career_agent_url.rstrip('/')}/api/new-vacancy"
    payload = {"url": url, "title": title, "feed_name": feed_name, "user_id": user_id}
    published_at = _parse_pub_date(pub_date)
    if published_at:
        payload["published_at"] = published_at
    if company:
        payload["company"] = company
    if salary:
        payload["salary"] = salary
    async with session.post(endpoint, json=payload) as resp:
        if resp.status == 409:
            log.info("[WEBHOOK] %s already known by career-agent — marking sent", url)
            return
        if resp.status >= 400:
            body = (await resp.text())[:300]
            raise RuntimeError(f"{resp.status} {resp.reason}: {body}")


async def fetch_jobs(session: aiohttp.ClientSession, url: str) -> list[dict]:
    async with session.get(url) as resp:
        resp.raise_for_status()
        content = await resp.read()
    root = ET.fromstring(content)
    jobs = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        if link:
            jobs.append({"title": title, "link": link, "pubDate": pub_date, "description": description})
    return jobs


async def deliver_one(
    session: aiohttp.ClientSession,
    link: str,
    j: dict,
    feed_name: str,
    user_id: int,
    career_agent_url: str,
    state: dict,
    now: datetime,
) -> bool:
    """Attempt webhook delivery to one user. Mutates state in place.
    Returns True iff delivered successfully (or was already sent)."""
    key = str(user_id)
    delivery = state[link]["delivery"].setdefault(key, new_delivery_entry())

    if delivery["status"] == "sent":
        return True
    if delivery["status"] == "failed":
        return False

    delivery["attempts"] += 1
    delivery["last_attempt"] = now.isoformat(timespec="seconds")

    try:
        await post_to_career_agent(
            session, career_agent_url, link, j["title"], feed_name, user_id,
            j.get("pubDate", ""), j.get("company", ""), j.get("salary", ""),
        )
        delivery["status"] = "sent"
        delivery["last_error"] = None
        return True
    except Exception as e:
        err = str(e)[:300]
        delivery["last_error"] = err
        if delivery["attempts"] >= MAX_ATTEMPTS:
            delivery["status"] = "failed"
            log.error("[FAILED] user=%d ← %s giving up after %d attempts: %s",
                      user_id, link, delivery["attempts"], err)
        else:
            delivery["status"] = "pending"
            log.warning("[WEBHOOK] user=%d ← %s FAIL attempt %d/%d: %s",
                        user_id, link, delivery["attempts"], MAX_ATTEMPTS, err)
        return False


async def retry_pending(
    session: aiohttp.ClientSession,
    state: dict,
    feeds: list[dict],
    career_agent_url: str,
) -> int:
    feed_by_name = {f["name"]: f for f in feeds}
    now = datetime.now()

    due: list[tuple[str, int]] = []
    for link, entry in state.items():
        if "delivery" not in entry:
            continue
        for uid_str, delivery in entry["delivery"].items():
            if is_due_for_retry(delivery, now):
                due.append((link, int(uid_str)))

    if not due:
        return 0

    log.info("Retrying %d pending delivery(s)...", len(due))
    tasks = []
    for link, user_id in due:
        entry = state[link]
        feed_name = entry.get("feed", "")
        if feed_name not in feed_by_name:
            log.warning("Feed '%s' no longer configured — skipping retry for %s", feed_name, link)
            continue
        j = {"title": entry.get("title", ""), "link": link}
        log.info("[RETRY] user=%d ← %s", user_id, j["title"][:80])
        tasks.append(deliver_one(session, link, j, feed_name, user_id, career_agent_url, state, now))

    if not tasks:
        return 0
    results = await asyncio.gather(*tasks, return_exceptions=True)
    delivered = 0
    for r in results:
        if isinstance(r, Exception):
            log.error("retry task raised: %s", r)
        elif r is True:
            delivered += 1
    return delivered


async def check_feed(
    session: aiohttp.ClientSession,
    feed: dict,
    state: dict,
    silent: bool,
    career_agent_url: str,
    debug: bool = False,
) -> int:
    try:
        jobs = await fetch_jobs(session, feed["url"])
    except Exception as e:
        log.error("[%s] fetch failed: %s", feed["name"], e)
        return 0

    # Enrich each job with company + salary extracted from RSS data
    for j in jobs:
        j["company"] = _resolve_company(j["title"], j.get("description", ""), feed["url"])
        j["salary"] = SALARY_RE.search(j["title"]).group() if SALARY_RE.search(j["title"]) else ""

    new_jobs = [j for j in jobs if j["link"] not in state]
    now = datetime.now()
    now_iso = now.isoformat(timespec="seconds")

    if debug:
        log.info("[%s] total: %d, new: %d, seen: %d",
                 feed["name"], len(jobs), len(new_jobs), len(jobs) - len(new_jobs))
        for j in new_jobs:
            log.info("  → %s | company=%s | salary=%s\n    %s",
                     j["title"], j["company"], j["salary"], j["link"])
            state[j["link"]] = _build_state_entry(j, feed, now_iso, silent=True)
        return 0

    for j in new_jobs:
        state[j["link"]] = _build_state_entry(j, feed, now_iso, silent=silent)

    if silent:
        return 0

    notified = 0
    for j in new_jobs:
        results = await asyncio.gather(
            *[deliver_one(session, j["link"], j, feed["name"], uid, career_agent_url, state, now)
              for uid in feed["user_ids"]],
            return_exceptions=True,
        )
        sent = [feed["user_ids"][i] for i, r in enumerate(results) if r is True]
        status = f"-> {sent} OK" if sent else "-> FAIL"
        log.info("[%s] NEW: %s | %s | %s", feed["name"], j["title"], j["link"], status)
        if sent:
            notified += 1
    return notified


async def check(silent: bool, career_agent_url: str, feeds: list[dict], debug: bool = False) -> int:
    state = load_state()
    migrate_state(state, feeds)

    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT, headers=HEADERS) as session:
        if not silent and not debug:
            retried = await retry_pending(session, state, feeds, career_agent_url)
            if retried:
                log.info("%d pending delivery(s) succeeded.", retried)

        results = await asyncio.gather(
            *[check_feed(session, f, state, silent, career_agent_url, debug) for f in feeds],
            return_exceptions=True,
        )

    total = 0
    for feed, result in zip(feeds, results):
        if isinstance(result, Exception):
            log.error("[%s] check_feed raised: %s", feed["name"], result)
        else:
            total += result

    save_state(state)
    return total


async def async_main(args, career_agent_url: str, feeds: list[dict]) -> None:
    if args.debug:
        log.info("[DEBUG] Current feed contents (no notifications sent):")
        await check(silent=True, career_agent_url=career_agent_url, feeds=feeds, debug=True)
        return

    if args.once:
        found = await check(silent=False, career_agent_url=career_agent_url, feeds=feeds)
        log.info("%d new listing(s)", found) if found else log.info("No new listings")
        return

    log.info("Interval: %d min | Press Ctrl+C to stop", args.interval)

    truly_first = not STATE_FILE.exists()
    if truly_first:
        log.info("First launch: indexing current listings silently...")
        await asyncio.wait_for(
            check(silent=True, career_agent_url=career_agent_url, feeds=feeds),
            timeout=CHECK_TIMEOUT,
        )
        log.info("Done. Watching for new listings...")
    else:
        log.info("Checking for listings missed while offline...")
        found = await asyncio.wait_for(
            check(silent=False, career_agent_url=career_agent_url, feeds=feeds),
            timeout=CHECK_TIMEOUT,
        )
        log.info("%d listing(s) sent.", found) if found else log.info("None missed.")

    while True:
        try:
            await asyncio.sleep(args.interval * 60)
            found = await asyncio.wait_for(
                check(silent=False, career_agent_url=career_agent_url, feeds=feeds),
                timeout=CHECK_TIMEOUT,
            )
            if not found:
                log.info("Checked — no new listings")
        except asyncio.TimeoutError:
            log.warning(
                "Check cycle timed out after %ds — skipping, will retry next interval",
                CHECK_TIMEOUT,
            )
        except asyncio.CancelledError:
            log.info("Cancelled — shutting down")
            raise
        except Exception as e:
            log.exception("Unexpected error in main loop: %s — sleeping 60s before retry", e)
            await asyncio.sleep(60)


def main():
    config = load_config()
    apply_config(config)
    setup_logging(
        level=config["logging"]["level"],
        max_bytes=config["logging"]["max_bytes"],
        backup_count=config["logging"]["backup_count"],
    )

    parser = argparse.ArgumentParser(
        description="Multi-feed vacancy monitor — pushes new vacancies to career-agent via webhook"
    )
    parser.add_argument("--interval", type=int, default=config["interval_minutes"],
                        help=f"Poll interval in minutes (default: {config['interval_minutes']})")
    parser.add_argument("--once", action="store_true", help="Single check and exit")
    parser.add_argument("--debug", action="store_true",
                        help="Show feed item counts and new listings without sending webhooks")
    args = parser.parse_args()

    if not args.once and not args.debug:
        acquire_lock()

    try:
        career_agent_url = load_env()
        feeds = load_feeds()

        log.info("Starting vacancy monitor (PID %d)", os.getpid())
        log.info("Career-agent webhook: %s/api/new-vacancy", career_agent_url)
        for f in feeds:
            log.info("  Feed: %s → user_ids: %s", f["name"], f["user_ids"])
        log.info("State: %s", STATE_FILE)
        log.info("Log:   %s", LOG_FILE)

        try:
            asyncio.run(async_main(args, career_agent_url, feeds))
        except KeyboardInterrupt:
            log.info("Stopped by user")
    finally:
        if not args.once and not args.debug:
            release_lock()


if __name__ == "__main__":
    main()
