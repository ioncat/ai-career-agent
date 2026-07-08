"""
tests/test_telegram.py — tests for core/telegram.py (push-only bot).

No real Telegram token needed — Bot internals are mocked.
Tests cover: message splitting, send_message, send_document.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.telegram import TelegramBot, _split_message


# ── _split_message ────────────────────────────────────────────────────────────

def test_split_message_short():
    assert _split_message("hello") == ["hello"]


def test_split_message_exact_limit():
    text = "x" * 4096
    assert _split_message(text) == [text]


def test_split_message_long_splits():
    text = "a" * 4097
    chunks = _split_message(text)
    assert len(chunks) == 2
    assert all(len(c) <= 4096 for c in chunks)
    assert "".join(chunks) == text


def test_split_message_breaks_on_newline():
    text = "line1\n" + "x" * 4094
    chunks = _split_message(text)
    assert chunks[0] == "line1"
    assert chunks[1] == "x" * 4094


def test_split_message_three_chunks():
    text = "x" * 4096 + "y" * 4096 + "z" * 100
    chunks = _split_message(text)
    assert len(chunks) == 3
    assert all(len(c) <= 4096 for c in chunks)


# ── TelegramBot construction ──────────────────────────────────────────────────

def _make_bot() -> TelegramBot:
    with patch("core.telegram.Bot"):
        bot = TelegramBot(token="fake:token", chat_id=12345)
    return bot


def test_construction_does_not_raise():
    bot = _make_bot()
    assert bot._chat_id == 12345


# ── send_message ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_single_chunk():
    bot = _make_bot()
    bot._bot.send_message = AsyncMock()

    await bot.send_message("Hello!")
    bot._bot.send_message.assert_awaited_once()
    assert bot._bot.send_message.call_args.args[1] == "Hello!"


@pytest.mark.asyncio
async def test_send_message_long_sends_multiple_chunks():
    bot = _make_bot()
    bot._bot.send_message = AsyncMock()

    await bot.send_message("x" * 5000)
    assert bot._bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_send_message_uses_correct_chat_id():
    bot = _make_bot()
    bot._bot.send_message = AsyncMock()

    await bot.send_message("hi")
    assert bot._bot.send_message.call_args.args[0] == 12345


# ── send_document ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_document_calls_bot():
    bot = _make_bot()
    bot._bot.send_document = AsyncMock()

    with patch("core.telegram.FSInputFile"):
        await bot.send_document(Path("/tmp/cv.pdf"), caption="Your CV")

    bot._bot.send_document.assert_awaited_once()
    call_args = bot._bot.send_document.call_args
    assert call_args.args[0] == 12345
    assert call_args.kwargs.get("caption") == "Your CV"
