"""
core/push.py — Web Push notification utility (VAPID protocol).

Sends browser push notifications via the Web Push standard (RFC 8030 + VAPID).
Subscriptions stored in DB push_subscriptions table; expired subscriptions
(HTTP 404/410) are removed automatically on send failure.

Startup:
    from core import push
    push.configure(settings.vapid_private_key, settings.vapid_claims_email)

Send:
    result = await push.send_push(user_id=1, title="PM at Stripe", body="fit 8/10 · apply ✅")
    # result.sent / result.failed / result.expired

Key generation (one-time, store in .env):
    python -c "
    from py_vapid import Vapid; import base64, json
    v = Vapid(); v.generate_keys()
    print('VAPID_PRIVATE_KEY=' + v.private_pem().decode())
    print('VAPID_PUBLIC_KEY=' + base64.urlsafe_b64encode(
        v.public_key.public_bytes(
            __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.X962,
            __import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.UncompressedPoint
        )
    ).decode())
    "
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from db import database

log = logging.getLogger(__name__)

_vapid_private_key: str = ""
_vapid_claims_email: str = "mailto:admin@example.com"


def configure(private_key: str, claims_email: str) -> None:
    """Set VAPID credentials. Call once at startup before first send_push()."""
    global _vapid_private_key, _vapid_claims_email
    _vapid_private_key = private_key.strip()
    _vapid_claims_email = claims_email.strip() or "mailto:admin@example.com"


@dataclass
class PushResult:
    sent: int
    failed: int
    expired: int  # subscriptions deleted due to 404/410


async def send_push(
    user_id: int,
    title: str,
    body: str,
    url: str | None = None,
) -> PushResult:
    """Send Web Push notification to all active subscriptions for user_id.

    Thread-safe: pywebpush is synchronous; each send runs via asyncio.to_thread.
    Expired subscriptions (HTTP 404/410 from push service) are deleted from DB.
    No-op when VAPID not configured — returns PushResult(0, 0, 0).

    Args:
        user_id: DB user id to look up subscriptions for.
        title:   Notification title shown in browser.
        body:    Notification body text.
        url:     Optional URL to open when notification is clicked.
    """
    if not _vapid_private_key:
        log.debug("push.send_push: VAPID not configured — skipping")
        return PushResult(sent=0, failed=0, expired=0)

    subs = await database.get_push_subscriptions(user_id)
    if not subs:
        log.debug("push.send_push: no subscriptions for user_id=%d", user_id)
        return PushResult(sent=0, failed=0, expired=0)

    payload_data: dict = {"title": title, "body": body}
    if url:
        payload_data["url"] = url
    payload = json.dumps(payload_data, ensure_ascii=False)

    result = PushResult(sent=0, failed=0, expired=0)

    for sub in subs:
        endpoint = sub["endpoint"]
        try:
            await asyncio.to_thread(
                _send_one,
                endpoint=endpoint,
                p256dh=sub["p256dh"],
                auth=sub["auth"],
                payload=payload,
            )
            result.sent += 1
        except _ExpiredSubscription:
            await database.delete_push_subscription(endpoint)
            result.expired += 1
            log.info("push: removed expired subscription %.50s", endpoint)
        except Exception as exc:
            log.error("push: send failed %.50s: %s", endpoint, exc)
            result.failed += 1

    log.info(
        "push: user_id=%d sent=%d failed=%d expired=%d",
        user_id, result.sent, result.failed, result.expired,
    )
    return result


class _ExpiredSubscription(Exception):
    """Raised when push service returns 404/410 — subscription no longer valid."""


def _send_one(*, endpoint: str, p256dh: str, auth: str, payload: str) -> None:
    """Synchronous Web Push send. Called via asyncio.to_thread — not coroutine."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError as exc:
        raise RuntimeError("pywebpush not installed — run: pip install pywebpush") from exc

    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=payload,
            vapid_private_key=_vapid_private_key,
            vapid_claims={"sub": _vapid_claims_email},
        )
    except WebPushException as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) if response else None
        if status in (404, 410):
            raise _ExpiredSubscription() from exc
        raise
