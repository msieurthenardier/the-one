"""Connection errors name the provider type, not "Ollama" (M31 F6 leg 06, DD11 2)."""

from __future__ import annotations

import socket

import pytest

from the_one.llm.base import Message
from the_one.llm.ollama_provider import OllamaProvider


def _dead_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _first_error(provider: OllamaProvider) -> Exception:
    with pytest.raises(ConnectionError) as info:
        async for _ in provider.stream([Message.user("hi")]):
            pass
    return info.value


async def test_openai_compatible_error_names_the_openai_compatible_server() -> None:
    url = f"http://127.0.0.1:{_dead_port()}/v1"
    provider = OllamaProvider(model="m", base_url=url, server_label="OpenAI-compatible")
    msg = str(await _first_error(provider))
    assert msg.startswith("Cannot connect to the OpenAI-compatible server at ")
    assert "Ollama" not in msg


async def test_ollama_error_wording_is_unchanged() -> None:
    url = f"http://127.0.0.1:{_dead_port()}/v1"
    provider = OllamaProvider(model="m", base_url=url, native_api=False)
    msg = str(await _first_error(provider))
    assert msg.startswith("Cannot connect to Ollama at ")


def test_http_status_error_wording() -> None:
    from the_one.llm import ollama_api

    assert ollama_api.server_phrase("Ollama", sentence_start=True) == "Ollama"
    assert (
        ollama_api.server_phrase("OpenAI-compatible", sentence_start=True)
        == "The OpenAI-compatible server"
    )
