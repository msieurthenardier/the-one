"""Telegram Bot API client -- ``getMe``/``getUpdates``/``sendMessage`` on
``httpx`` (DD-2, DD-11). Token lives in the URL path, not a header."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from the_one.connectors import base

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.telegram.org"
_ORDINARY_HTTP_TIMEOUT = 15.0
_LONG_POLL_SLACK_SECONDS = 15.0  # on top of getUpdates's own <=50s timeout (DD-2)
# DD-2: config errors retrying cannot fix. PermanentConnectorFailure REUSED.
_PERMANENT_STATUSES = frozenset({401, 404, 409})
# Squawk 0038: unbounded retry_after could park the caller arbitrarily
# long. Discord's REST client (DD-3) has no such clamp to mirror; capped
# here instead. Non-numeric/negative values are treated as the ceiling.
_MAX_RETRY_AFTER_SECONDS = 60.0


_PHOTO_RETRY_AFTER_SECONDS = 10.0  # M35 F3 DD10: the visual path's 429 clamp
_PHOTO_HTTP_TIMEOUT = 15.0


def monotonic() -> float:
    """The clock the photo budget runs on (a seam: tests patch this module attribute)."""
    return time.monotonic()


class TelegramApiError(base.ConnectorClientError):
    """Non-permanent failure -- ordinary manager backoff applies.

    ``status`` is the HTTP status of the response it was built from.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class TelegramTransportError(base.ConnectorClientError):
    """A request failed below HTTP (connect error, timeout, ...). The request may have
    reached Telegram, so a send is never repeated. Deliberately NOT a ``TelegramApiError``:
    ``TelegramClient.send`` retries any ``TelegramApiError`` as plain text, which would
    post a reply that may already be posted twice."""


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
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float,
        data: dict[str, Any] | None = None,
        files: Any = None,
    ) -> httpx.Response:
        """JSON by default; ``data`` + ``files`` send multipart instead."""
        path = f"/bot{self._token}/{method}"
        try:
            if files is not None:
                return await self._client.post(path, data=data, files=files, timeout=timeout)
            return await self._client.post(path, json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            # The token is in the URL path: never chain the cause, whose traceback or
            # message could print it, and say only the exception's type.
            raise TelegramTransportError(
                f"telegram {method} failed: {type(exc).__name__}"
            ) from None

    def _handle_response(self, method: str, resp: httpx.Response) -> Any:
        if resp.status_code in _PERMANENT_STATUSES:
            perm = base.PermanentConnectorFailure(
                f"telegram {method} -> {resp.status_code}: {resp.text[:200]}"
            )
            perm.status = resp.status_code  # type: ignore[attr-defined]
            raise perm
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not data.get("ok", True):
            desc = data.get("description", resp.text[:200])
            raise TelegramApiError(
                f"telegram {method} -> {resp.status_code}: {desc}", status=resp.status_code
            )
        return data.get("result")

    async def _post_with_429_retry(
        self,
        method: str,
        *,
        payload: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        timeout: float,
        max_retry_after: float,
        deadline: float | None = None,
    ) -> Any:
        """Post, retrying once on a 429 after ``min(retry_after, max_retry_after)``.

        With ``deadline`` (a ``monotonic()`` value) every attempt runs under
        ``asyncio.wait_for`` on the time left (``TimeoutError`` escapes: the request may have
        been posted), each request's own timeout is capped to it, and a 429 whose wait is not
        under the time left is not slept on: it is raised at once as a 429 ``TelegramApiError``.
        """

        async def attempt() -> httpx.Response:
            if deadline is None:
                return await self._post(method, payload, timeout=timeout, data=data, files=files)
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            return await asyncio.wait_for(
                self._post(
                    method, payload, timeout=min(timeout, remaining), data=data, files=files
                ),
                remaining,
            )

        resp = await attempt()
        if resp.status_code == 429:
            body = resp.json() if resp.content else {}
            raw = (body.get("parameters") or {}).get("retry_after", 1.0)
            try:
                retry_after = float(raw)
            except (TypeError, ValueError):
                retry_after = -1.0
            if not 0 <= retry_after <= max_retry_after:
                logger.warning("telegram %s: retry_after %r clamped", method, raw)
                retry_after = max_retry_after
            if deadline is not None and retry_after >= deadline - monotonic():
                return self._handle_response(method, resp)
            await asyncio.sleep(retry_after)
            resp = await attempt()
        return self._handle_response(method, resp)

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
        self,
        *,
        chat_id: str,
        text: str,
        message_thread_id: str | None = None,
        parse_mode: str | None = None,
        max_retry_after: float = _MAX_RETRY_AFTER_SECONDS,
    ) -> dict[str, Any]:
        # One bounded retry on 429 (else raises). `parse_mode` is OPTIONAL
        # and omitted from the payload when None -- mirrors the
        # `message_thread_id` pattern immediately below (Mission 23
        # Flight 4, HAT step 8: Telegram formatted rendering).
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        return await self._post_with_429_retry(
            "sendMessage",
            payload=payload,
            timeout=_ORDINARY_HTTP_TIMEOUT,
            max_retry_after=max_retry_after,
        )

    async def send_photo(
        self,
        *,
        chat_id: str,
        photo: bytes,
        filename: str,
        caption: str,
        message_thread_id: str | None = None,
        timeout: float = _PHOTO_HTTP_TIMEOUT,
        max_retry_after: float = _PHOTO_RETRY_AFTER_SECONDS,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        """``sendPhoto`` as multipart: ``photo`` is the PNG, ``caption`` plain text (no
        ``parse_mode``). One 429 retry, clamped to ``max_retry_after`` (10 s)."""
        form: dict[str, Any] = {"chat_id": chat_id, "caption": caption}
        if message_thread_id is not None:
            form["message_thread_id"] = message_thread_id
        return await self._post_with_429_retry(
            "sendPhoto",
            data=form,
            files={"photo": (filename, photo, "image/png")},
            timeout=timeout,
            max_retry_after=max_retry_after,
            deadline=deadline,
        )
