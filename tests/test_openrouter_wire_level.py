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


# ── D2: ranking-header presence & injection rejection ───────────────────


@pytest.mark.asyncio
class TestWireRankingHeaders:
    async def test_referer_and_title_reach_wire_unchanged(self, monkeypatch) -> None:
        captured: list[httpx.Request] = []
        _patch_async_client(monkeypatch, captured)

        prov = OpenRouterProvider(
            model="m",
            api_key="k",
            config={"referer": "https://valid.example", "title": "Valid Title"},
        )
        await prov.complete([Message(role=Role.USER, content="hi")])

        assert captured[0].headers.get("http-referer") == "https://valid.example"
        assert captured[0].headers.get("x-title") == "Valid Title"

    async def test_no_referer_no_title_no_headers(self, monkeypatch) -> None:
        captured: list[httpx.Request] = []
        _patch_async_client(monkeypatch, captured)

        prov = OpenRouterProvider(model="m", api_key="k", config={})
        await prov.complete([Message(role=Role.USER, content="hi")])

        header_keys = {k.lower() for k in captured[0].headers.keys()}
        assert "http-referer" not in header_keys
        assert "x-title" not in header_keys


class TestConstructorRejectsHeaderInjection:
    """Defensive header check at the provider constructor.

    If Agent A has landed a CR/LF rejection in OpenRouterProvider.__init__,
    this test will run and pin the rejection contract. Otherwise it skips
    with a clear reason — the API-layer rejection is already covered by
    ``test_provider_api.py::TestOpenRouterValidation``; the constructor
    layer is a defense-in-depth check.
    """

    def test_constructor_rejects_referer_with_crlf(self) -> None:
        with pytest.raises(ValueError):
            OpenRouterProvider(
                model="m",
                api_key="x",
                config={"referer": "https://x.com\r\nX-Injected: y"},
            )

    def test_constructor_rejects_title_with_nul(self) -> None:
        with pytest.raises(ValueError):
            OpenRouterProvider(
                model="m",
                api_key="x",
                config={"title": "evil\x00injected"},
            )


# ── D6: empty referer/title dropped at API layer (round-trip pin) ───────
# (Lives here because it complements D1/D2 — the wire layer cannot send a
# header that the API layer correctly dropped at save time.)


import sys
from pathlib import Path
from unittest.mock import patch

import aiosqlite
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture
async def api_client(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(test_key)
    test_encryptor = Encryptor(test_key, key_path=key_path)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    await conn.close()


@pytest.mark.asyncio
async def test_empty_string_referer_dropped_at_api_layer_round_trip(
    api_client: AsyncClient,
) -> None:
    """``""`` referer / title round-trip as ABSENT keys (not empty strings).
    Pinned at the API surface — the wire layer tests above assume that no
    empty-string headers ever enter the constructor."""
    body = {
        "name": "ORempty",
        "type": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "k",
        "config": {"referer": "", "title": ""},
    }
    resp = await api_client.post("/api/providers", json=body)
    assert resp.status_code in (200, 201), resp.text
    prov_id = resp.json()["id"]

    get_resp = await api_client.get(f"/api/providers/{prov_id}")
    cfg = get_resp.json()["config"]
    assert "referer" not in cfg
    assert "title" not in cfg
