"""Hermetic adapter suite for text-form tool-call recovery in OllamaProvider.

M16 F03 L02 (#105): wires the leg-01 recovery kernel into
``OllamaProvider.complete()`` and ``.stream()``. When a response carries NO
structured ``tool_calls`` but its content holds a recognizable text-form call,
the provider recovers it into ``ToolCall``s with synthesized stable ids
(``f"{name}_{index}"``) and strips the recognized block from the returned
content (DD2/DD4). The agent loop and ``_to_api_message`` are NOT touched here.

All hermetic: ``complete`` uses an ``httpx.MockTransport`` (the ``/api/show``-
fires-first idiom from ``test_ollama_provider_auth.py``); ``stream`` monkeypatches
``ollama_provider.ollama_api.chat_stream``. No live model, no markers.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from the_one.llm.base import Message, Role
from the_one.llm.ollama_provider import OllamaProvider

# Verbatim captured primary fixture (Flight 1 spike, live gemma3:4b):
# a ```tool fenced block containing a Python-call, returned with tool_calls null.
GEMMA_FIXTURE = "```tool\nget_weather(city='Paris')\n```"


# ---------------------------------------------------------------------------
# complete() helpers — MockTransport with /api/show firing first
# ---------------------------------------------------------------------------


def _complete_handler(content, tool_calls=None):
    """Build a MockTransport handler: ``/api/show`` first, then a chat reply.

    ``content`` is the assistant message content; ``tool_calls`` (when given)
    is placed on the message as a structured array.
    """
    message: dict = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/show"):
            return httpx.Response(200, json={"model_info": {}})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return handler


def _patch_transport(monkeypatch, handler) -> None:
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


async def _run_complete(monkeypatch, content, tool_calls=None) -> Message:
    _patch_transport(monkeypatch, _complete_handler(content, tool_calls))
    prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1")
    return await prov.complete([Message(role=Role.USER, content="hi")])


# ---------------------------------------------------------------------------
# stream() helpers — monkeypatch ollama_api.chat_stream
# ---------------------------------------------------------------------------


def _stream_chunks(content_pieces, tool_call_deltas=None):
    """Build the chunk-dict sequence a monkeypatched chat_stream yields.

    Each piece in ``content_pieces`` becomes a ``delta.content`` chunk; an
    optional ``tool_call_deltas`` list is emitted as a single tool_calls delta
    chunk. A choices-empty usage trailer closes the sequence so the provider's
    final chunk carries ``usage`` (the branch at ollama_provider.py:182).
    """
    chunks: list[dict] = []
    for piece in content_pieces:
        chunks.append({"choices": [{"delta": {"content": piece}}]})
    if tool_call_deltas is not None:
        chunks.append({"choices": [{"delta": {"tool_calls": tool_call_deltas}}]})
    chunks.append({"usage": {"prompt_tokens": 3, "completion_tokens": 4}})
    return chunks


def _patch_chat_stream(monkeypatch, chunks) -> None:
    async def fake_chat_stream(base_url, body, headers=None):
        for c in chunks:
            yield c

    from the_one.llm import ollama_api

    monkeypatch.setattr(ollama_api, "chat_stream", fake_chat_stream)


async def _run_stream(monkeypatch, content_pieces, tool_call_deltas=None):
    _patch_chat_stream(
        monkeypatch, _stream_chunks(content_pieces, tool_call_deltas)
    )
    prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1")
    chunks = []
    async for ch in prov.stream([Message(role=Role.USER, content="hi")]):
        chunks.append(ch)
    final = [c for c in chunks if c.is_final]
    assert len(final) == 1, "expected exactly one final chunk"
    return final[0], chunks


# ===========================================================================
# complete() path
# ===========================================================================


@pytest.mark.asyncio
async def test_complete_recovers_on_empty_structured_tool_calls(monkeypatch):
    msg = await _run_complete(monkeypatch, GEMMA_FIXTURE)
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.name == "get_weather"
    assert tc.arguments == {"city": "Paris"}


@pytest.mark.asyncio
async def test_complete_strips_recognized_block(monkeypatch):
    # Whole-content fence → stripped to "".
    msg = await _run_complete(monkeypatch, GEMMA_FIXTURE)
    assert "```tool" not in msg.content
    assert msg.content == ""


@pytest.mark.asyncio
async def test_complete_strip_preserves_prose_before_and_after_fence(monkeypatch):
    content = "Let me check.\n" + GEMMA_FIXTURE + "\nOne moment."
    msg = await _run_complete(monkeypatch, content)
    assert len(msg.tool_calls) == 1
    assert "```tool" not in msg.content
    assert "get_weather(city='Paris')" not in msg.content
    assert "Let me check." in msg.content
    assert "One moment." in msg.content


@pytest.mark.asyncio
async def test_complete_synthesized_ids_stable_and_roundtrip(monkeypatch):
    # f"{name}_{index}" — deterministic, and what a ToolResult.tool_call_id
    # would match (the agent loop preserves the id the provider sets).
    from the_one.llm.base import ToolResult

    msg = await _run_complete(monkeypatch, GEMMA_FIXTURE)
    tc = msg.tool_calls[0]
    assert tc.id == "get_weather_0"
    result = ToolResult(tool_call_id=tc.id, content="sunny")
    assert result.tool_call_id == "get_weather_0"


@pytest.mark.asyncio
async def test_complete_no_double_recovery_when_structured_present(monkeypatch):
    # Structured tool_calls present + a marker in content: structured wins,
    # recovery does not run, content is NOT stripped.
    structured = [
        {
            "id": "call_abc",
            "type": "function",
            "function": {"name": "get_time", "arguments": {"zone": "UTC"}},
        }
    ]
    msg = await _run_complete(monkeypatch, GEMMA_FIXTURE, tool_calls=structured)
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.name == "get_time"
    assert tc.id == "call_abc"
    assert tc.arguments == {"zone": "UTC"}
    # Content untouched — the marker block is still present.
    assert "```tool" in msg.content


@pytest.mark.asyncio
async def test_complete_no_false_positive_on_prose(monkeypatch):
    content = "The weather in Paris looks pleasant today."
    msg = await _run_complete(monkeypatch, content)
    assert msg.tool_calls == []
    assert msg.content == content


@pytest.mark.asyncio
async def test_complete_multi_call_recovered_in_order(monkeypatch):
    content = (
        "```tool\nget_weather(city='Paris')\n```\n"
        "```tool\nget_time(zone='UTC')\n```"
    )
    msg = await _run_complete(monkeypatch, content)
    assert [tc.name for tc in msg.tool_calls] == ["get_weather", "get_time"]
    assert [tc.id for tc in msg.tool_calls] == ["get_weather_0", "get_time_1"]
    assert msg.tool_calls[0].arguments == {"city": "Paris"}
    assert msg.tool_calls[1].arguments == {"zone": "UTC"}


@pytest.mark.asyncio
async def test_complete_positional_args_key_passthrough(monkeypatch, caplog):
    from the_one.llm._toolcall_recovery import POSITIONAL_ARGS_KEY

    content = "```tool\nget_weather('Paris')\n```"
    with caplog.at_level(logging.WARNING):
        msg = await _run_complete(monkeypatch, content)
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    # Sentinel survives verbatim into ToolCall.arguments (the provider does not
    # strip it; the dispatcher handles it).
    assert tc.arguments[POSITIONAL_ARGS_KEY] == ["Paris"]
    # The kernel logs a warning when it carries positional args.
    assert any("positional args" in r.message for r in caplog.records)


# ===========================================================================
# stream() path
# ===========================================================================


@pytest.mark.asyncio
async def test_stream_recovers_on_empty_structured_tool_calls(monkeypatch):
    # Split the marker across two deltas to also exercise the marker-split edge.
    final, _ = await _run_stream(monkeypatch, ["```tool\nget_weath", "er(city='Paris')\n```"])
    assert len(final.message.tool_calls) == 1
    tc = final.message.tool_calls[0]
    assert tc.name == "get_weather"
    assert tc.arguments == {"city": "Paris"}
    assert tc.id == "get_weather_0"
    # The chunk's tool_calls matches the message's.
    assert final.tool_calls == final.message.tool_calls


@pytest.mark.asyncio
async def test_stream_strips_recognized_block(monkeypatch):
    final, _ = await _run_stream(monkeypatch, [GEMMA_FIXTURE])
    assert "```tool" not in final.message.content
    assert final.message.content == ""


@pytest.mark.asyncio
async def test_stream_strip_preserves_surrounding_prose(monkeypatch):
    final, _ = await _run_stream(
        monkeypatch, ["Checking.\n", GEMMA_FIXTURE, "\nDone."]
    )
    assert len(final.message.tool_calls) == 1
    assert "```tool" not in final.message.content
    assert "Checking." in final.message.content
    assert "Done." in final.message.content


@pytest.mark.asyncio
async def test_stream_no_double_recovery_when_structured_present(monkeypatch):
    # A structured tool_calls delta arrives → recovery must NOT run on content.
    deltas = [
        {
            "index": 0,
            "id": "call_xyz",
            "function": {"name": "get_time", "arguments": '{"zone": "UTC"}'},
        }
    ]
    final, _ = await _run_stream(monkeypatch, [GEMMA_FIXTURE], tool_call_deltas=deltas)
    assert len(final.message.tool_calls) == 1
    tc = final.message.tool_calls[0]
    assert tc.name == "get_time"
    assert tc.id == "call_xyz"
    # Content not stripped — the marker is still present.
    assert "```tool" in final.message.content


@pytest.mark.asyncio
async def test_stream_no_false_positive_on_prose(monkeypatch):
    final, _ = await _run_stream(monkeypatch, ["Just ", "some ", "prose."])
    assert final.message.tool_calls == []
    assert final.message.content == "Just some prose."


@pytest.mark.asyncio
async def test_stream_multi_call_recovered_in_order(monkeypatch):
    content = (
        "```tool\nget_weather(city='Paris')\n```\n"
        "```tool\nget_time(zone='UTC')\n```"
    )
    final, _ = await _run_stream(monkeypatch, [content])
    tcs = final.message.tool_calls
    assert [tc.name for tc in tcs] == ["get_weather", "get_time"]
    assert [tc.id for tc in tcs] == ["get_weather_0", "get_time_1"]


@pytest.mark.asyncio
async def test_stream_interim_deltas_carry_unstripped_content(monkeypatch):
    # Documented limitation: interim StreamChunks carry the raw, un-stripped
    # content; only the FINAL message is stripped.
    _, chunks = await _run_stream(monkeypatch, [GEMMA_FIXTURE])
    interim_text = "".join(c.content for c in chunks if not c.is_final)
    assert "```tool" in interim_text
    final = [c for c in chunks if c.is_final][0]
    assert final.message.content == ""
