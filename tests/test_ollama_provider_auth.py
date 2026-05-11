"""Authorization header behavior for OllamaProvider (openai-compatible target)."""

from __future__ import annotations

import httpx
import pytest

from the_one.llm.base import Message, Role
from the_one.llm.ollama_provider import OllamaProvider


def _capture_handler(captured: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return handler


@pytest.mark.asyncio
class TestOllamaAuthHeader:
    async def test_complete_sends_authorization_with_api_key(self, monkeypatch) -> None:
        """With api_key set, OllamaProvider.complete must send Authorization."""
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(
            model="m",
            base_url="http://localhost:11434/v1",
            api_key="sk-test-key",
        )
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert captured, "no request captured"
        assert captured[0].headers.get("authorization") == "Bearer sk-test-key"

    async def test_complete_no_authorization_when_api_key_none(self, monkeypatch) -> None:
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1")
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}

    async def test_complete_empty_string_api_key_sends_no_auth(self, monkeypatch) -> None:
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1", api_key="")
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}

    async def test_complete_whitespace_api_key_sends_no_auth(self, monkeypatch) -> None:
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1", api_key="   ")
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}


@pytest.mark.asyncio
class TestOllamaApiHeadersParam:
    async def test_show_model_passes_headers(self, monkeypatch) -> None:
        from the_one.llm import ollama_api

        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"capabilities": ["completion"]})

        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        await ollama_api.show_model(
            "http://localhost:11434", "model-x", headers={"Authorization": "Bearer x"}
        )
        assert captured[0].headers.get("authorization") == "Bearer x"

    async def test_chat_stream_passes_headers(self, monkeypatch) -> None:
        from the_one.llm import ollama_api

        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="data: [DONE]\n\n")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        async for _ in ollama_api.chat_stream(
            "http://localhost:11434/v1",
            {"model": "m", "messages": []},
            headers={"Authorization": "Bearer y"},
        ):
            pass
        assert captured[0].headers.get("authorization") == "Bearer y"
