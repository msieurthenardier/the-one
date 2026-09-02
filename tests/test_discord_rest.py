"""Tests for ``the_one.connectors.discord._rest`` — endpoint helpers +
per-bucket/global rate limiting (DD-3). Mission 23 Flight 3 Leg 1. All
against a mocked ``httpx`` transport — no live REST calls.
"""

from __future__ import annotations

import time

import httpx
import pytest

from the_one.connectors.discord._rest import DiscordRestError, RestClient, _RateLimiter

_BASE = "https://discord.test/api/v10"


def _rest(handler) -> RestClient:
    return RestClient("tok", base_url=_BASE, transport=httpx.MockTransport(handler))


# ── endpoint helpers (AC-6: ~10, a text bot needs) ──────────────────────


async def test_get_gateway_url():
    async def handler(request):
        assert request.url.path == "/api/v10/gateway/bot"
        assert request.headers["authorization"] == "Bot tok"
        return httpx.Response(200, json={"url": "wss://gateway.discord.gg"})

    rest = _rest(handler)
    try:
        assert await rest.get_gateway_url() == "wss://gateway.discord.gg"
    finally:
        await rest.aclose()


async def test_get_current_user():
    async def handler(request):
        assert request.url.path == "/api/v10/users/@me"
        return httpx.Response(200, json={"id": "bot-1", "username": "TestBot"})

    rest = _rest(handler)
    try:
        assert (await rest.get_current_user())["username"] == "TestBot"
    finally:
        await rest.aclose()


async def test_create_message():
    async def handler(request):
        assert request.url.path == "/api/v10/channels/c1/messages"
        assert request.method == "POST"
        import json as _json

        assert _json.loads(request.content) == {"content": "hi"}
        return httpx.Response(200, json={"id": "msg-1"})

    rest = _rest(handler)
    try:
        assert (await rest.create_message("c1", "hi"))["id"] == "msg-1"
    finally:
        await rest.aclose()


async def test_create_dm():
    async def handler(request):
        assert request.url.path == "/api/v10/users/@me/channels"
        return httpx.Response(200, json={"id": "dm-channel-1"})

    rest = _rest(handler)
    try:
        assert (await rest.create_dm("peer-1"))["id"] == "dm-channel-1"
    finally:
        await rest.aclose()


async def test_get_channel():
    async def handler(request):
        assert request.url.path == "/api/v10/channels/c1"
        return httpx.Response(200, json={"id": "c1", "type": 0})

    rest = _rest(handler)
    try:
        assert (await rest.get_channel("c1"))["type"] == 0
    finally:
        await rest.aclose()


async def test_get_channel_messages_with_limit():
    async def handler(request):
        assert request.url.path == "/api/v10/channels/c1/messages"
        assert request.url.params["limit"] == "25"
        return httpx.Response(200, json=[{"id": "m1"}])

    rest = _rest(handler)
    try:
        result = await rest.get_channel_messages("c1", limit=25)
        assert result == [{"id": "m1"}]
    finally:
        await rest.aclose()


async def test_trigger_typing_no_content_response():
    async def handler(request):
        assert request.url.path == "/api/v10/channels/c1/typing"
        return httpx.Response(204)

    rest = _rest(handler)
    try:
        assert await rest.trigger_typing("c1") is None
    finally:
        await rest.aclose()


async def test_get_guild_channels():
    async def handler(request):
        assert request.url.path == "/api/v10/guilds/g1/channels"
        return httpx.Response(200, json=[{"id": "c1"}, {"id": "c2"}])

    rest = _rest(handler)
    try:
        assert len(await rest.get_guild_channels("g1")) == 2
    finally:
        await rest.aclose()


async def test_non_2xx_raises_discord_rest_error():
    async def handler(request):
        return httpx.Response(403, text="forbidden")

    rest = _rest(handler)
    try:
        with pytest.raises(DiscordRestError):
            await rest.get_current_user()
    finally:
        await rest.aclose()


# ── rate limiting (AC-6) ─────────────────────────────────────────────────


async def test_429_retries_with_retry_after_then_succeeds():
    attempts = []

    async def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, json={"retry_after": 0.02, "global": False})
        return httpx.Response(200, json={"id": "msg-1"})

    rest = _rest(handler)
    try:
        result = await rest.create_message("c1", "hello")
        assert result == {"id": "msg-1"}
        assert len(attempts) == 2
    finally:
        await rest.aclose()


async def test_429_bounded_retries_raises_after_max():
    attempts = []

    async def handler(request):
        attempts.append(request)
        return httpx.Response(429, json={"retry_after": 0.001, "global": False})

    rest = _rest(handler)
    try:
        with pytest.raises(DiscordRestError):
            await rest.get_current_user()
        assert len(attempts) == 4  # _MAX_RETRIES(3) + the initial attempt
    finally:
        await rest.aclose()


async def test_429_with_global_flag_sets_the_global_gate():
    async def handler(request):
        return httpx.Response(429, json={"retry_after": 0.01, "global": True})

    rest = _rest(handler)
    try:
        with pytest.raises(DiscordRestError):
            await rest.get_current_user()
        assert rest._limiter._global_reset_at > time.monotonic() - 1
    finally:
        await rest.aclose()


async def test_rate_limiter_learns_bucket_and_shares_lock_across_routes():
    limiter = _RateLimiter()
    lock_a_before_learning = limiter.lock_for("GET:/a")
    assert lock_a_before_learning is limiter.lock_for("GET:/a")

    limiter._route_bucket["GET:/a"] = "bucket-x"
    limiter._route_bucket["GET:/b"] = "bucket-x"
    assert limiter.lock_for("GET:/a") is limiter.lock_for("GET:/b")


async def test_rate_limiter_waits_when_bucket_remaining_is_zero():
    limiter = _RateLimiter()
    limiter.record(
        "GET:/a",
        httpx.Headers(
            {
                "X-RateLimit-Bucket": "bucket-a",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset-After": "0.05",
            }
        ),
    )
    start = time.monotonic()
    await limiter.wait_turn("GET:/a")
    assert time.monotonic() - start >= 0.04


async def test_rate_limiter_global_gate_blocks_every_bucket_not_just_the_offender():
    import asyncio

    limiter = _RateLimiter()
    limiter.record_global(0.05)
    start = time.monotonic()
    await asyncio.gather(limiter.wait_turn("GET:/a"), limiter.wait_turn("GET:/b"))
    assert time.monotonic() - start >= 0.04
