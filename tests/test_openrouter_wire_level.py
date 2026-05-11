"""Wire-level pins for OpenRouterProvider.

These tests assert what *actually goes on the network* — the
construction-level tests in ``test_openrouter_provider.py`` only inspect
the in-memory client. Both layers matter; this file is the wire layer.

Pattern mirrors ``tests/test_ollama_provider_auth.py``: monkeypatch
``httpx.AsyncClient.__init__`` so every client (including the one built
internally by ``openai.AsyncOpenAI``) gets a ``MockTransport`` that
captures the outgoing ``httpx.Request``.
"""

from __future__ import annotations

import httpx
import pytest

from the_one.llm.base import Message, Role
from the_one.llm.openrouter_provider import OpenRouterProvider


def _capture_handler(captured: list[httpx.Request]):
    """Return an httpx handler that records each request and replies with
    a minimal-but-valid OpenAI chat completion payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    return handler


def _patch_async_client(monkeypatch, captured: list[httpx.Request]) -> None:
    """Wire ``MockTransport`` into every ``httpx.AsyncClient`` constructed
    after this call returns — including the one that ``openai.AsyncOpenAI``
    builds internally when no ``http_client`` kwarg is given."""

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


# ── D1: no-leak invariant on the wire ────────────────────────────────────


@pytest.mark.asyncio
class TestWireNoLeak:
    """The OpenAI SDK reads ``OPENAI_API_KEY`` ONLY when ``api_key is None``.
    OpenRouterProvider constructs the SDK client with a non-None placeholder
    so that env var cannot leak. These pin the contract at the wire layer."""

    async def test_no_leak_wire_with_OPENAI_API_KEY_env_set(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        captured: list[httpx.Request] = []
        _patch_async_client(monkeypatch, captured)

        prov = OpenRouterProvider(model="m", api_key=None)
        await prov.complete([Message(role=Role.USER, content="hi")])

        assert captured, "no request captured"
        auth = captured[0].headers.get("authorization")
        assert auth == f"Bearer {OpenRouterProvider._NO_KEY_PLACEHOLDER}", auth
        assert "sk-leaked" not in (auth or ""), "OPENAI_API_KEY leaked into the wire"

    async def test_explicit_api_key_reaches_wire(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        captured: list[httpx.Request] = []
        _patch_async_client(monkeypatch, captured)

        prov = OpenRouterProvider(model="m", api_key="real-key")
        await prov.complete([Message(role=Role.USER, content="hi")])

        assert captured[0].headers.get("authorization") == "Bearer real-key"

    async def test_OPENROUTER_API_KEY_env_used_when_no_explicit_key(
        self, monkeypatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
        captured: list[httpx.Request] = []
        _patch_async_client(monkeypatch, captured)

        prov = OpenRouterProvider(model="m", api_key=None)
        await prov.complete([Message(role=Role.USER, content="hi")])

        assert captured[0].headers.get("authorization") == "Bearer sk-or-x"


# ── D2: hardcoded ranking headers reach the wire ────────────────────────


@pytest.mark.asyncio
class TestWireRankingHeaders:
    """Ranking headers identify *this app* (the-one). Hardcoded as module
    constants in openrouter_provider, so every request carries them — no
    operator-configurable knob, no opt-in/opt-out."""

    async def test_app_identity_headers_reach_wire(self, monkeypatch) -> None:
        from the_one.llm.openrouter_provider import _APP_NAME, _APP_URL

        captured: list[httpx.Request] = []
        _patch_async_client(monkeypatch, captured)

        prov = OpenRouterProvider(model="m", api_key="k")
        await prov.complete([Message(role=Role.USER, content="hi")])

        assert captured[0].headers.get("http-referer") == _APP_URL
        assert captured[0].headers.get("x-title") == _APP_NAME
