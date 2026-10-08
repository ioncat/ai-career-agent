"""
tests/test_job_monitor_health.py - feed-failure alerting in services/job-monitor/monitor.py
and the `--monitor` flag of scripts/health_check.py.

Everything is mocked: no live feed, no Telegram call, no running service.
Contract under test:
- a per-feed failure streak lives in feed_health.json (not in seen_jobs.json);
- ONE alert when the streak reaches 3, ONE recovery alert on the first success after it;
- a failed Telegram send is retried on the next cycle instead of being lost;
- a restart does not repeat an alert that was already sent;
- `health_check.py --monitor` fails on an alerted or stale feed.
"""

import asyncio
import importlib.util
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


monitor = _load("job_monitor_monitor", "services/job-monitor/monitor.py")
health_check = _load("health_check_script", "scripts/health_check.py")

FEED = {"name": "Feed A", "url": "https://example.org/rss", "user_ids": [1]}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "_BASE", tmp_path)
    monkeypatch.setattr(monitor, "STATE_FILE", tmp_path / "seen_jobs.json")
    monkeypatch.setattr(monitor, "HEALTH_FILE", tmp_path / "feed_health.json")
    sent: list[str] = []
    answers: list[bool] = []

    async def fake_send(session, text):
        sent.append(text)
        return answers.pop(0) if answers else True

    monkeypatch.setattr(monitor, "send_telegram_message", fake_send)
    return {"dir": tmp_path, "sent": sent, "answers": answers, "monkeypatch": monkeypatch}


def _cycle(env, *, fails: bool, feeds=None, debug=False):
    async def fake_fetch(session, url):
        if fails:
            raise RuntimeError("503 Service Unavailable for url: https://example.org/rss?key=SECRET")
        return []

    env["monkeypatch"].setattr(monitor, "fetch_jobs", fake_fetch)
    return asyncio.run(monitor.check(silent=False, career_agent_url="http://x", feeds=feeds or [FEED], debug=debug))


def _health(env):
    return json.loads((env["dir"] / "feed_health.json").read_text(encoding="utf-8"))


# ── record_fetch_result: the pure streak logic ────────────────────────────────

def test_alert_comes_once_at_the_third_failure_in_a_row():
    health = {}
    assert monitor.record_fetch_result(health, "f", False, "e") == (None, 0)
    assert monitor.record_fetch_result(health, "f", False, "e") == (None, 0)
    assert monitor.record_fetch_result(health, "f", False, "e") == ("failing", 3)
    assert monitor.record_fetch_result(health, "f", False, "e") == (None, 0)   # not repeated
    assert health["f"]["consecutive_failures"] == 4


def test_recovery_alert_comes_once_and_only_after_an_alert():
    health = {}
    for _ in range(3):
        monitor.record_fetch_result(health, "f", False, "e")
    assert monitor.record_fetch_result(health, "f", True) == ("recovered", 3)
    assert monitor.record_fetch_result(health, "f", True) == (None, 0)
    assert health["f"]["consecutive_failures"] == 0 and health["f"]["alerted"] is False


def test_failures_that_are_not_in_a_row_never_alert():
    health = {}
    for _ in range(5):
        assert monitor.record_fetch_result(health, "f", False, "e")[0] is None
        assert monitor.record_fetch_result(health, "f", False, "e")[0] is None
        assert monitor.record_fetch_result(health, "f", True) == (None, 0)


def test_feeds_are_counted_separately():
    health = {}
    for _ in range(2):
        monitor.record_fetch_result(health, "a", False, "e")
        monitor.record_fetch_result(health, "b", False, "e")
    assert monitor.record_fetch_result(health, "a", False, "e")[0] == "failing"
    assert health["b"]["alerted"] is False


def test_error_text_loses_urls_and_is_cut():
    health = {}
    monitor.record_fetch_result(health, "f", False, "404 at https://x.org/feed?key=SECRET and more " + "z" * 400)
    assert "SECRET" not in health["f"]["last_error"] and "<url>" in health["f"]["last_error"]
    assert len(health["f"]["last_error"]) <= 300


def test_alert_texts_name_the_feed_and_the_streak():
    failing = monitor.format_feed_alert("failing", "Feed A", 3, "503")
    assert "Feed A" in failing and "3 checks in a row" in failing and "503" in failing
    recovered = monitor.format_feed_alert("recovered", "Feed A", 3, None)
    assert "Feed A" in recovered and "working again" in recovered


# ── Telegram sender ───────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, status=200, raises=None):
        self.status, self.raises, self.calls = status, raises, []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if self.raises:
            raise self.raises
        return _Resp(self.status)


def test_send_without_credentials_logs_and_does_not_retry(monkeypatch, caplog):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    session = _Session()
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(monitor.send_telegram_message(session, "hello")) is True
    assert session.calls == [] and "not configured" in caplog.text


def test_send_posts_to_the_bot_api(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    session = _Session()
    assert asyncio.run(monitor.send_telegram_message(session, "hello")) is True
    url, payload = session.calls[0]
    assert url == "https://api.telegram.org/bot123:TOKEN/sendMessage"
    assert payload == {"chat_id": "42", "text": "hello"}


@pytest.mark.parametrize("session", [_Session(status=500), _Session(raises=OSError("boom"))])
def test_send_failure_returns_false_and_never_logs_the_token(monkeypatch, caplog, session):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(monitor.send_telegram_message(session, "hello")) is False
    assert "TOKEN" not in caplog.text


# ── check(): the whole cycle ──────────────────────────────────────────────────

def test_cycle_sends_one_failing_and_one_recovery_alert(env):
    for _ in range(2):
        _cycle(env, fails=True)
    assert env["sent"] == []
    _cycle(env, fails=True)
    assert len(env["sent"]) == 1 and "failed 3 checks in a row" in env["sent"][0]
    assert "SECRET" not in env["sent"][0]
    _cycle(env, fails=True)
    assert len(env["sent"]) == 1                       # no repeat while it stays down
    _cycle(env, fails=False)
    assert len(env["sent"]) == 2 and "working again" in env["sent"][1]
    _cycle(env, fails=False)
    assert len(env["sent"]) == 2
    assert _health(env)["Feed A"]["consecutive_failures"] == 0


def test_state_lives_in_its_own_file_and_survives_a_restart(env):
    for _ in range(3):
        _cycle(env, fails=True)
    assert (env["dir"] / "feed_health.json").exists()
    assert "Feed A" not in json.loads((env["dir"] / "seen_jobs.json").read_text(encoding="utf-8"))
    _cycle(env, fails=True)                            # a fresh check() = a restarted process
    assert len(env["sent"]) == 1


def test_a_failed_send_is_retried_on_the_next_cycle(env):
    env["answers"].append(False)                       # the first alert cannot be delivered
    for _ in range(3):
        _cycle(env, fails=True)
    assert len(env["sent"]) == 1 and _health(env)["Feed A"]["alerted"] is False
    _cycle(env, fails=True)
    assert len(env["sent"]) == 2 and _health(env)["Feed A"]["alerted"] is True


def test_a_failed_recovery_send_is_retried_too(env):
    for _ in range(3):
        _cycle(env, fails=True)
    env["answers"].append(False)
    _cycle(env, fails=False)
    assert len(env["sent"]) == 2 and _health(env)["Feed A"]["alerted"] is True
    _cycle(env, fails=False)
    assert len(env["sent"]) == 3 and _health(env)["Feed A"]["alerted"] is False


def test_debug_mode_does_not_touch_the_health_file(env):
    _cycle(env, fails=True, debug=True)
    assert not (env["dir"] / "feed_health.json").exists() and env["sent"] == []


def test_a_feed_removed_from_the_config_is_forgotten(env):
    other = {"name": "Feed B", "url": "https://example.org/b", "user_ids": [1]}
    _cycle(env, fails=False, feeds=[FEED, other])
    assert set(_health(env)) == {"Feed A", "Feed B"}
    _cycle(env, fails=False, feeds=[FEED])
    assert set(_health(env)) == {"Feed A"}


# ── health_check.py --monitor ─────────────────────────────────────────────────

NOW = datetime(2026, 10, 8, 18, 0, 0)


def _write_health(folder, **feeds):
    (folder / "feed_health.json").write_text(json.dumps(feeds), encoding="utf-8")


def _feed(minutes_ago=2, failures=0, alerted=False):
    return {"consecutive_failures": failures, "alerted": alerted,
            "last_check": (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")}


def test_monitor_check_passes_for_fresh_healthy_feeds(tmp_path):
    _write_health(tmp_path, a=_feed(), b=_feed(minutes_ago=10, failures=1))
    result = health_check.check_monitor(tmp_path, now=NOW)
    assert result.ok and "2 feed(s)" in result.detail


def test_monitor_check_fails_on_an_alerted_feed(tmp_path):
    _write_health(tmp_path, a=_feed(), b=_feed(failures=4, alerted=True))
    result = health_check.check_monitor(tmp_path, now=NOW)
    assert not result.ok and "b: failing (4 checks in a row)" in result.detail


def test_monitor_check_fails_on_a_stale_feed(tmp_path):
    _write_health(tmp_path, a=_feed(minutes_ago=90))
    result = health_check.check_monitor(tmp_path, max_age_minutes=30, now=NOW)
    assert not result.ok and "stale" in result.detail


@pytest.mark.parametrize("content", [None, "{not json", "[]", "{}"])
def test_monitor_check_fails_on_a_missing_or_empty_state_file(tmp_path, content):
    if content is not None:
        (tmp_path / "feed_health.json").write_text(content, encoding="utf-8")
    assert not health_check.check_monitor(tmp_path, now=NOW).ok


def test_run_includes_the_monitor_result_only_with_the_flag(tmp_path, monkeypatch, capsys):
    import argparse

    async def ok_http(name, url):
        return health_check.CheckResult(name, ok=True)

    monkeypatch.setattr(health_check, "check_http", ok_http)
    monkeypatch.setattr(health_check, "check_db", lambda: health_check.CheckResult("sqlite", ok=True))
    base = dict(pdf_url=None, parser_url=None, telegram=False, monitor_dir=str(tmp_path),
                monitor_max_age=30)

    assert asyncio.run(health_check.run(argparse.Namespace(monitor=False, **base))) == 0
    assert "job-monitor" not in capsys.readouterr().out

    assert asyncio.run(health_check.run(argparse.Namespace(monitor=True, **base))) == 1   # no state file
    assert "job-monitor" in capsys.readouterr().out
