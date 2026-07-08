"""
core/telegram.py — Telegram bot: push notifications only.

Responsibilities:
- send_message / send_document helpers (outbound notifications to allowed_chat_id)
- No incoming message handling — bot is send-only; Flutter is the primary UI

Usage (wired in agent.py):
    bot = TelegramBot(token=settings.telegram_token, chat_id=settings.telegram_chat_id)
    await bot.send_message("Analysis complete!")
    await bot.stop()  # on shutdown
"""

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile

log = logging.getLogger(__name__)

_MAX_MSG_LEN = 4096


class TelegramBot:
    """Telegram push-notification sender.

    Args:
        token:    Bot API token from @BotFather.
        chat_id:  Recipient chat_id for all outbound messages.
    """

    def __init__(self, token: str, chat_id: int) -> None:
        self._bot = Bot(token=token)
        self._chat_id = chat_id

    async def stop(self) -> None:
        """Close bot session."""
        log.info("TelegramBot: closing session")
        await self._bot.session.close()

    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> None:
        """Send text to chat_id. Splits at 4096 chars."""
        for chunk in _split_message(text):
            await self._bot.send_message(self._chat_id, chunk, parse_mode=parse_mode)

    async def send_document(self, file_path: Path, caption: str | None = None) -> None:
        """Send a file to chat_id."""
        await self._bot.send_document(
            self._chat_id,
            FSInputFile(file_path),
            caption=caption,
        )


def _split_message(text: str, max_len: int = _MAX_MSG_LEN) -> list[str]:
    """Split text into chunks ≤ max_len chars, breaking on newlines when possible."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
