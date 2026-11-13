"""Telegram Bot API long-poll connector (Mission 23 Flight 4, DD-1/DD-2)."""

from __future__ import annotations

from the_one.connectors import registry
from the_one.connectors.telegram._api import DEFAULT_BASE_URL
from the_one.connectors.telegram.plugin import TelegramClient, TelegramPlugin

__all__ = ["TelegramClient", "TelegramPlugin", "register"]


def register(*, base_url: str = DEFAULT_BASE_URL) -> None:
    """Unconditional at lifespan startup, mirroring Discord's block."""
    registry.register("telegram", TelegramPlugin(base_url=base_url))
