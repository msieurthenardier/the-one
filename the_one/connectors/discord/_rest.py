"""Discord REST v10 client — per-bucket + global rate limiting (DD-3).

One ``httpx.AsyncClient`` per client instance. No request queuing beyond
per-bucket serialization — a personal bot's volume doesn't need it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from the_one.connectors.base import ConnectorClientError

DEFAULT_BASE_URL = "https://discord.com/api/v10"
_MAX_RETRIES = 3


class DiscordRestError(ConnectorClientError):
    """Raised on a non-2xx REST response after retries are exhausted."""


class _RateLimiter:
    """Per-bucket serialization (keyed by ``X-RateLimit-Bucket``, learned
    from the first response on a route) plus a global gate (429 with
    ``global: true`` blocks every bucket, not just the offending one)."""

    def __init__(self) -> None:
        self._route_bucket: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._remaining: dict[str, int] = {}
        self._reset_at: dict[str, float] = {}
        self._global_reset_at: float = 0.0

    def lock_for(self, route_key: str) -> asyncio.Lock:
        bucket = self._route_bucket.get(route_key, route_key)
        return self._locks.setdefault(bucket, asyncio.Lock())

    async def wait_turn(self, route_key: str) -> None:
        now = time.monotonic()
        if now < self._global_reset_at:
            await asyncio.sleep(self._global_reset_at - now)
        bucket = self._route_bucket.get(route_key, route_key)
        if self._remaining.get(bucket) == 0:
            reset_at = self._reset_at.get(bucket)
            if reset_at is not None:
                wait = reset_at - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)

    def record(self, route_key: str, headers: httpx.Headers) -> None:
        bucket = headers.get("X-RateLimit-Bucket")
        if bucket:
            self._route_bucket[route_key] = bucket
        key = bucket or route_key
        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            self._remaining[key] = int(float(remaining))
        reset_after = headers.get("X-RateLimit-Reset-After")
        if reset_after is not None:
            self._reset_at[key] = time.monotonic() + float(reset_after)

    def record_global(self, retry_after: float) -> None:
        self._global_reset_at = time.monotonic() + retry_after


class RestClient:
    """Bot-only REST client against Discord API v10 (``base_url``
    injectable for tests — a mocked ``httpx`` transport, no live REST)."""

    def __init__(
        self, token: str, *, base_url: str = DEFAULT_BASE_URL, **client_kwargs: Any
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bot {token}"},
            timeout=15.0,
            **client_kwargs,
        )
        self._limiter = _RateLimiter()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, json: Any = None, params: Any = None
    ) -> Any:
        route_key = f"{method}:{path.split('?')[0]}"
        async with self._limiter.lock_for(route_key):
            for attempt in range(_MAX_RETRIES + 1):
                await self._limiter.wait_turn(route_key)
                resp = await self._client.request(method, path, json=json, params=params)
                self._limiter.record(route_key, resp.headers)
                if resp.status_code == 429:
                    body = resp.json() if resp.content else {}
                    retry_after = float(body.get("retry_after", 1.0))
                    if body.get("global"):
                        self._limiter.record_global(retry_after)
                    if attempt >= _MAX_RETRIES:
                        raise DiscordRestError(
                            f"rate limited on {method} {path} after {attempt} retries"
                        )
                    await asyncio.sleep(retry_after)
                    continue
                if resp.status_code >= 400:
                    raise DiscordRestError(
                        f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"
                    )
                if resp.status_code == 204 or not resp.content:
                    return None
                return resp.json()
            raise DiscordRestError(f"{method} {path}: exhausted retries")  # pragma: no cover

    # ── endpoints (DD-3: ~10, a text bot needs) ─────────────────────────
    async def get_gateway_url(self) -> str:
        data = await self._request("GET", "/gateway/bot")
        return data["url"]

    async def get_current_user(self) -> dict[str, Any]:
        return await self._request("GET", "/users/@me")

    async def create_message(self, channel_id: str, content: str) -> dict[str, Any]:
        return await self._request(
            "POST", f"/channels/{channel_id}/messages", json={"content": content}
        )

    async def create_dm(self, user_id: str) -> dict[str, Any]:
        return await self._request("POST", "/users/@me/channels", json={"recipient_id": user_id})

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/channels/{channel_id}")

    async def get_channel_messages(
        self, channel_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", f"/channels/{channel_id}/messages", params={"limit": limit}
        )

    async def trigger_typing(self, channel_id: str) -> None:
        await self._request("POST", f"/channels/{channel_id}/typing")

    async def get_guild_channels(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/guilds/{guild_id}/channels")
