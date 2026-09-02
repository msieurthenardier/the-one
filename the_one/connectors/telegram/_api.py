"""Telegram Bot API client -- ``getMe``/``getUpdates``/``sendMessage`` on
``httpx`` (DD-2, DD-11). Token lives in the URL path, not a header."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from the_one.connectors import base

DEFAULT_BASE_URL = "https://api.telegram.org"
_ORDINARY_HTTP_TIMEOUT = 15.0
_LONG_POLL_SLACK_SECONDS = 15.0  # on top of getUpdates's own <=50s timeout (DD-2)
# DD-2: config errors retrying cannot fix. PermanentConnectorFailure REUSED.
_PERMANENT_STATUSES = frozenset({401, 404, 409})


class TelegramApiError(base.ConnectorClientError):
    """Non-permanent failure -- ordinary manager backoff applies."""


class TelegramApiClient:
    """``base_url``/transport injectable for tests -- no live network."""

    def __init__(
        self, token: str, *, base_url: str = DEFAULT_BASE_URL, **client_kwargs: Any
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=_ORDINARY_HTTP_TIMEOUT, **client_kwargs
        )
        self._token = token

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(
        self, method: str, payload: dict[str, Any], *, timeout: float
    ) -> httpx.Response:
        path = f"/bot{self._token}/{method}"
        return await self._client.post(path, json=payload, timeout=timeout)

    def _handle_response(self, method: str, resp: httpx.Response) -> Any:
        if resp.status_code in _PERMANENT_STATUSES:
            raise base.PermanentConnectorFailure(
                f"telegram {method} -> {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not data.get("ok", True):
            desc = data.get("description", resp.text[:200])
            raise TelegramApiError(f"telegram {method} -> {resp.status_code}: {desc}")
        return data.get("result")

    async def get_me(self) -> dict[str, Any]:
        resp = await self._post("getMe", {}, timeout=_ORDINARY_HTTP_TIMEOUT)
        return self._handle_response("getMe", resp)

    async def get_updates(
        self, *, offset: int | None, timeout: int, allowed_updates: tuple[str, ...] = ("message",)
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": list(allowed_updates)}
        if offset is not None:
            payload["offset"] = offset
        resp = await self._post("getUpdates", payload, timeout=timeout + _LONG_POLL_SLACK_SECONDS)
        return self._handle_response("getUpdates", resp) or []

    async def send_message(
        self, *, chat_id: str, text: str, message_thread_id: str | None = None
    ) -> dict[str, Any]:
        # Plain text, no parse_mode; one bounded retry on 429 (else raises).
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        resp = await self._post("sendMessage", payload, timeout=_ORDINARY_HTTP_TIMEOUT)
        if resp.status_code == 429:
            data = resp.json() if resp.content else {}
            retry_after = float((data.get("parameters") or {}).get("retry_after", 1.0))
            await asyncio.sleep(retry_after)
            resp = await self._post("sendMessage", payload, timeout=_ORDINARY_HTTP_TIMEOUT)
        return self._handle_response("sendMessage", resp)
