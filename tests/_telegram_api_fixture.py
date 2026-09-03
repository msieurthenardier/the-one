"""Fake Telegram Bot API double (DD-8-of-Flight-3 pattern) -- an
``httpx.MockTransport``-backed scriptable fake for the Telegram client's
unit tests. No real network: a test builds a ``FakeTelegramApi`` and
passes its ``.transport`` as ``TelegramPlugin(api_transport=...)``.

``getUpdates`` models Telegram's REAL offset semantics rather than a
scripted batch queue: every scheduled update stays in ``self.updates``
forever (nothing is server-side deleted), and each call filters by the
caller's ``offset`` param (``update_id >= offset``, or everything when
``offset`` is omitted). This is what makes AC-2's redelivery assertion
meaningful without special-casing it in the fixture: a fresh
``_AccountState`` (offset=None) naturally re-receives every update the
fixture has ever scheduled, exactly like the real Bot API does after an
unclean restart.
"""

from __future__ import annotations

from typing import Any

import httpx


class FakeTelegramApi:
    """``me``: the ``getMe`` result. ``updates``: every update the fake
    server "knows about" (list of raw update dicts, each with an
    ``update_id``) -- append via :meth:`schedule` mid-test to simulate a
    message arriving after ``connect()``. ``error_status``: method name ->
    HTTP status code, applied to EVERY call of that method (permanent:
    401/404/409; ordinary: 500 etc.); ``429`` triggers Telegram's
    ``retry_after`` shape once, then reverts to normal on the retry.
    ``calls`` logs every ``(method, payload)`` for offset/shape assertions.

    ``reject_parse_mode_once`` (Mission 23 Flight 4, HAT step 8 -- Telegram
    formatted rendering): a one-shot-400 capability for ``sendMessage``,
    analogous to the existing ``429`` one-shot handling above but keyed on
    ``"parse_mode" in payload`` rather than on method name alone, so a
    test can script the plugin's own mechanical fallback (a formatted
    attempt gets rejected once, the plain-text retry that follows must
    NOT carry ``parse_mode`` and so sails through). This check runs
    BEFORE the generic ``error_status``/429 handling below, which is what
    lets a test compose the two: e.g. ``reject_parse_mode_once=True`` +
    ``error_status={"sendMessage": 429}`` scripts "400 first (on the
    parse_mode attempt), then 429 on the plain-text fallback retry" in
    one fixture -- the fallback retry's own 429 is absorbed by ``_api``'s
    already-existing one-shot-429 retry, so the plugin still only sees a
    plain success. Fires at most once, on the first ``sendMessage`` call
    whose payload contains ``parse_mode``; every other call (with or
    without ``parse_mode``) is unaffected.
    """

    def __init__(
        self,
        *,
        me: dict[str, Any] | None = None,
        updates: list[dict[str, Any]] | None = None,
        send_message_result: dict[str, Any] | None = None,
        error_status: dict[str, int] | None = None,
        empty_poll_delay: float = 0.02,
        reject_parse_mode_once: bool = False,
        retry_after: Any = 0,
    ) -> None:
        self.me = me or {"id": 111, "is_bot": True, "username": "TestBot"}
        self.updates: list[dict[str, Any]] = list(updates or [])
        self.send_message_result = send_message_result or {"message_id": 999}
        self.error_status = dict(error_status or {})
        self.empty_poll_delay = empty_poll_delay
        self.reject_parse_mode_once = reject_parse_mode_once
        # Squawk 0038: the scripted 429's retry_after value, e.g. an absurd
        # (99999) or malformed ("soon") value to exercise _api.py's clamp.
        self.retry_after = retry_after
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sent_messages: list[dict[str, Any]] = []
        self._sent_429_once: set[str] = set()
        self._rejected_parse_mode_once = False

    def schedule(self, update: dict[str, Any]) -> None:
        """Append one update -- visible to the NEXT ``getUpdates`` call
        whose ``offset`` doesn't exceed its ``update_id``."""
        self.updates.append(update)

    async def handler(self, request: httpx.Request) -> httpx.Response:
        import asyncio
        import json

        method = request.url.path.rsplit("/", 1)[-1]
        payload = json.loads(request.content or b"{}")
        self.calls.append((method, payload))

        if (
            method == "sendMessage"
            and self.reject_parse_mode_once
            and not self._rejected_parse_mode_once
            and "parse_mode" in payload
        ):
            self._rejected_parse_mode_once = True
            return httpx.Response(
                400,
                json={
                    "ok": False,
                    "error_code": 400,
                    "description": "fake 400: can't parse entities",
                },
            )

        status = self.error_status.get(method)
        if status == 429 and method not in self._sent_429_once:
            self._sent_429_once.add(method)
            return httpx.Response(
                429,
                json={
                    "ok": False,
                    "error_code": 429,
                    "parameters": {"retry_after": self.retry_after},
                },
            )
        if status is not None and status != 429:
            return httpx.Response(
                status, json={"ok": False, "error_code": status, "description": f"fake {status}"}
            )

        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": self.me})
        if method == "getUpdates":
            offset = payload.get("offset")
            batch = (
                self.updates
                if offset is None
                else [u for u in self.updates if u["update_id"] >= offset]
            )
            if not batch:
                await asyncio.sleep(self.empty_poll_delay)
            return httpx.Response(200, json={"ok": True, "result": batch})
        if method == "sendMessage":
            self.sent_messages.append(payload)
            return httpx.Response(200, json={"ok": True, "result": self.send_message_result})
        return httpx.Response(404, json={"ok": False, "error_code": 404, "description": "?"})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
