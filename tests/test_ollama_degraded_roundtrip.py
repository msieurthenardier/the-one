"""Hermetic pin for the degraded (non-tool-capable) follow-up round-trip.

M16 F03 L03 (#105): after leg 02, a recovered text-form call is dispatched by
the agent loop (DD6), producing an assistant message with synthesized-id
``tool_calls`` followed by a ``ToolResult``. On the *next* turn the provider
serializes that history via ``_to_api_message``. For a non-tool-capable model
(e.g. gemma3:4b — capabilities ['completion','vision'], ``supports_tools()`` is
False) the follow-up request goes out with ``tools`` omitted.

This test pins the *current structured* serialization of that degraded
follow-up history — the ``role:"tool"`` result branch and the
assistant-``tool_calls`` branch — so a future refactor cannot silently break
the round-trip we just validated live.

Structured degraded round-trip VALIDATED LIVE against gemma3:4b on 2026-06-18
(flight 3 leg 03): with the wire shape asserted below and NO ``tools`` key,
live Ollama returned 2xx and the model replied coherently. This pins that
contract. No production code change accompanies this test (the live finding was
ACCEPTED, not REJECTED).

Scope note: this pins the *recovered-call follow-up history* serialization
specifically — NOT the structured shape globally. A future tool-capable
refactor that changes how non-degraded histories serialize should not be
tripped by this test; it asserts only the three messages of a degraded
round-trip.

Pure/hermetic: ``_to_api_message`` is a synchronous per-message serializer with
no I/O — no live model, no transport, no mocks needed.
"""

from __future__ import annotations

import json

from the_one.llm.base import Message, ToolCall, ToolResult
from the_one.llm.ollama_provider import OllamaProvider


def _degraded_followup_history() -> list[Message]:
    """The realistic degraded follow-up history (DD5/DD6):

    USER question -> ASSISTANT carrying a recovered-style ToolCall (synthesized
    id ``get_weather_0``) -> TOOL ToolResult for that id. Mirrors exactly the
    history the live probe sent to gemma3:4b.
    """
    return [
        Message.user("What's the weather in Paris?"),
        Message.assistant(
            content="",
            tool_calls=[
                ToolCall(id="get_weather_0", name="get_weather", arguments={"city": "Paris"})
            ],
        ),
        Message.tool(ToolResult(tool_call_id="get_weather_0", content="Sunny, 24°C")),
    ]


def test_degraded_followup_history_serializes_structured() -> None:
    """Pin the structured degraded follow-up serialization validated live.

    Asserts the assistant-``tool_calls`` branch and the ``role:"tool"`` result
    branch produce exactly the wire shape that live gemma3:4b accepted on
    2026-06-18 (flight 3 leg 03), with ``tools`` omitted from the request.
    """
    prov = OllamaProvider(model="gemma3:4b", base_url="http://localhost:11434/v1")
    user_msg, assistant_msg, tool_msg = _degraded_followup_history()

    user_api = prov._to_api_message(user_msg)
    assert user_api == {"role": "user", "content": "What's the weather in Paris?"}

    # Assistant-tool_calls branch: structured tool_calls with synthesized id,
    # content collapsed to None (Message.assistant content="").
    assistant_api = prov._to_api_message(assistant_msg)
    assert assistant_api == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "get_weather_0",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"city": "Paris"}),
                },
            }
        ],
    }

    # role:"tool" result branch: tool_call_id threaded back, content verbatim.
    tool_api = prov._to_api_message(tool_msg)
    assert tool_api == {
        "role": "tool",
        "tool_call_id": "get_weather_0",
        "content": "Sunny, 24°C",
    }
