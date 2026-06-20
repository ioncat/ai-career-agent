"""
tests/test_push.py — tests for core/push.py + /api/push/* endpoints.

Mocks: database helpers, _send_one (no real Web Push calls).
No VAPID keys or push service needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.push import PushResult, _ExpiredSubscription, configure, send_push
from db import database


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sub(endpoint: str = "https://push.example.com/sub/1", p256dh: str = "keyA", auth: str = "authA") -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}[k]
    return row


def _configure_vapid():
    configure("fake-private-key", "mailto:test@example.com")


def _clear_vapid():
    configure("", "")


# ── configure() ──────────────────────────────────────────────────────────────

def test_configure_sets_credentials():
    configure("my-key", "mailto:foo@bar.com")
    from core import push as _push
    assert _push._vapid_private_key == "my-key"
    assert _push._vapid_claims_email == "mailto:foo@bar.com"
    _clear_vapid()


def test_configure_strips_whitespace():
    configure("  key  ", "  mailto:x@y.com  ")
    from core import push as _push
    assert _push._vapid_private_key == "key"
    assert _push._vapid_claims_email == "mailto:x@y.com"
    _clear_vapid()


def test_configure_empty_email_falls_back_to_default():
    configure("key", "")
    from core import push as _push
    assert _push._vapid_claims_email == "mailto:admin@example.com"
    _clear_vapid()


# ── send_push — VAPID not configured ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_push_no_op_when_vapid_not_configured():
    _clear_vapid()
    result = await send_push(user_id=1, title="Test", body="Hello")
    assert result == PushResult(sent=0, failed=0, expired=0)


# ── send_push — no subscriptions ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_push_no_op_when_no_subscriptions():
    _configure_vapid()
    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=[])
        result = await send_push(user_id=1, title="Test", body="Hello")
    assert result == PushResult(sent=0, failed=0, expired=0)
    _clear_vapid()


# ── send_push — happy path ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_push_one_subscription_success():
    _configure_vapid()
    sub = _sub()
    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=[sub])
        with patch("core.push._send_one") as mock_send:
            result = await send_push(user_id=1, title="New vacancy", body="PM at Stripe")
    assert result == PushResult(sent=1, failed=0, expired=0)
    mock_send.assert_called_once()
    _clear_vapid()


@pytest.mark.asyncio
async def test_send_push_multiple_subscriptions():
    _configure_vapid()
    subs = [_sub(f"https://push.example.com/sub/{i}") for i in range(3)]
    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=subs)
        with patch("core.push._send_one"):
            result = await send_push(user_id=1, title="T", body="B")
    assert result == PushResult(sent=3, failed=0, expired=0)
    _clear_vapid()


@pytest.mark.asyncio
async def test_send_push_passes_correct_payload():
    _configure_vapid()
    import json
    sub = _sub()
    captured = {}

    def fake_send_one(*, endpoint, p256dh, auth, payload):
        captured["payload"] = json.loads(payload)

    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=[sub])
        with patch("core.push._send_one", side_effect=fake_send_one):
            await send_push(user_id=1, title="Vacancy", body="fit 8/10", url="http://localhost/v/42")

    assert captured["payload"]["title"] == "Vacancy"
    assert captured["payload"]["body"] == "fit 8/10"
    assert captured["payload"]["url"] == "http://localhost/v/42"
    _clear_vapid()


@pytest.mark.asyncio
async def test_send_push_no_url_in_payload_when_not_given():
    _configure_vapid()
    import json
    sub = _sub()
    captured = {}

    def fake_send_one(*, endpoint, p256dh, auth, payload):
        captured["payload"] = json.loads(payload)

    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=[sub])
        with patch("core.push._send_one", side_effect=fake_send_one):
            await send_push(user_id=1, title="T", body="B")

    assert "url" not in captured["payload"]
    _clear_vapid()


# ── send_push — expired subscription (404/410) ───────────────────────────────

@pytest.mark.asyncio
async def test_send_push_expired_subscription_deleted():
    _configure_vapid()
    sub = _sub(endpoint="https://push.example.com/expired")
    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=[sub])
        mock_db.delete_push_subscription = AsyncMock()
        with patch("core.push._send_one", side_effect=_ExpiredSubscription()):
            result = await send_push(user_id=1, title="T", body="B")
    assert result == PushResult(sent=0, failed=0, expired=1)
    mock_db.delete_push_subscription.assert_awaited_once_with("https://push.example.com/expired")
    _clear_vapid()


@pytest.mark.asyncio
async def test_send_push_mixed_results():
    _configure_vapid()
    subs = [
        _sub("https://push.example.com/ok"),
        _sub("https://push.example.com/expired"),
        _sub("https://push.example.com/fail"),
    ]
    call_count = 0

    def side_effect(*, endpoint, p256dh, auth, payload):
        nonlocal call_count
        call_count += 1
        if "expired" in endpoint:
            raise _ExpiredSubscription()
        if "fail" in endpoint:
            raise RuntimeError("network error")

    with patch("core.push.database") as mock_db:
        mock_db.get_push_subscriptions = AsyncMock(return_value=subs)
        mock_db.delete_push_subscription = AsyncMock()
        with patch("core.push._send_one", side_effect=side_effect):
            result = await send_push(user_id=1, title="T", body="B")

    assert result == PushResult(sent=1, failed=1, expired=1)
    _clear_vapid()


# ── DB helpers ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_and_get_push_subscription(tmp_path):
    database.configure(tmp_path / "test.db")
    await database.init_db()
    await database.insert_user(name="Alice", telegram_chat_id=999)

    await database.upsert_push_subscription(
        user_id=1, endpoint="https://push.example.com/1",
        p256dh="keyA", auth="authA",
    )
    subs = await database.get_push_subscriptions(user_id=1)
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://push.example.com/1"
    assert subs[0]["p256dh"] == "keyA"


@pytest.mark.asyncio
async def test_upsert_updates_keys_on_conflict(tmp_path):
    database.configure(tmp_path / "test.db")
    await database.init_db()
    await database.insert_user(name="Alice", telegram_chat_id=999)

    await database.upsert_push_subscription(
        user_id=1, endpoint="https://push.example.com/1",
        p256dh="oldKey", auth="oldAuth",
    )
    await database.upsert_push_subscription(
        user_id=1, endpoint="https://push.example.com/1",
        p256dh="newKey", auth="newAuth",
    )
    subs = await database.get_push_subscriptions(user_id=1)
    assert len(subs) == 1
    assert subs[0]["p256dh"] == "newKey"


@pytest.mark.asyncio
async def test_delete_push_subscription(tmp_path):
    database.configure(tmp_path / "test.db")
    await database.init_db()
    await database.insert_user(name="Alice", telegram_chat_id=999)

    await database.upsert_push_subscription(
        user_id=1, endpoint="https://push.example.com/del",
        p256dh="k", auth="a",
    )
    await database.delete_push_subscription("https://push.example.com/del")
    subs = await database.get_push_subscriptions(user_id=1)
    assert subs == []


@pytest.mark.asyncio
async def test_get_push_subscriptions_empty(tmp_path):
    database.configure(tmp_path / "test.db")
    await database.init_db()
    subs = await database.get_push_subscriptions(user_id=99)
    assert subs == []


# ── API endpoints ─────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BFakePublicKey123==")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "")
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def client_no_vapid(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    import importlib, web.api
    importlib.reload(web.api)
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_api_push_subscribe_creates_subscription(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    database.configure(tmp_path / "test.db")
    await database.init_db()
    await database.insert_user(name="Alice", telegram_chat_id=111)

    resp = client.post("/api/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/sub/1",
        "p256dh": "keyABC",
        "auth": "authXYZ",
        "user_id": 1,
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "subscribed"

    subs = await database.get_push_subscriptions(1)
    assert len(subs) == 1
    assert subs[0]["p256dh"] == "keyABC"


def test_api_push_unsubscribe(client):
    resp = client.delete("/api/push/subscribe?endpoint=https://fcm.googleapis.com/sub/gone")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unsubscribed"


def test_api_vapid_public_key_returns_key(client):
    resp = client.get("/api/push/vapid-public-key")
    assert resp.status_code == 200
    assert resp.json()["publicKey"] == "BFakePublicKey123=="


def test_api_vapid_public_key_503_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "")
    import importlib, web.api
    importlib.reload(web.api)
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        resp = c.get("/api/push/vapid-public-key")
    assert resp.status_code == 503
