"""F6.5 L04 HAT-cycle fix regression test — carried into F7 L05 per
F6.5 debrief AI #3.

``_process_and_broadcast`` MUST read ``session.agent.llm.max_context_tokens``
LIVE at usage-event emission, NOT pre-capture it at function entry. The
pre-capture pattern caused the F6.5 HAT-observed "first message shows the
class-default context window, then jumps to the resolved value on the
second message" bug — because the L01 lazy resolver runs INSIDE the first
``agent.step()`` call, so any value captured *before* the step would be
the pre-resolution default.

This test pins the live-read contract: we mutate
``agent.llm.max_context_tokens`` between function entry and the first
usage emission, then assert the broadcast event reflects the *post-mutation*
value. If a future maintainer resurrects the eager-capture pattern (e.g.,
``max_context = session.agent.llm.max_context_tokens`` at the top of
``_process_and_broadcast``), this test fails — the captured value is
the entry-time value, NOT the post-mutation value.

Sanity-checked at L05 implementation time by temporarily reintroducing
the eager capture in app.py; the test failed as expected, then the fix
was restored and the test passes again.

Test scaffolding mirrors ``tests/test_app_websocket_pause_resume.py``
(StubAgent + monkeypatched ``_send_to_session`` capture).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest

from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import Session, _process_and_broadcast
from the_one.llm.base import Message, TokenUsage


class _LiveReadStubAgent:
    """Stub Agent whose ``llm.max_context_tokens`` is mutated mid-step.

    The ``step()`` async generator yields a single assistant Message with
    a non-None ``usage`` payload. CRITICALLY, ``step()`` mutates
    ``self.llm.max_context_tokens`` BEFORE yielding — this models the L01
    lazy resolver flipping the attribute from class-default to the
    resolved value during the first ``agent.step()`` call.

    If ``_process_and_broadcast`` captured ``max_context_tokens`` BEFORE
    entering the ``async for`` loop, it would see the pre-mutation value
    and emit the wrong number in the usage event. The live-read pattern
    sees the post-mutation value.
    """

    def __init__(
        self,
        initial_max_context_tokens: int,
        resolved_max_context_tokens: int,
    ) -> None:
        # Provide a minimal ``llm`` shim with a MUTABLE
        # ``max_context_tokens`` attribute.
        class _LLMShim:
            pass

        self.llm = _LLMShim()
        self.llm.max_context_tokens = initial_max_context_tokens
        self._resolved_max_context_tokens = resolved_max_context_tokens
        self.messages: list[Message] = []
        self._deferred_tool_calls = None

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002 — F7 L04: widened signature
    ) -> AsyncIterator[Message]:
        # Model the L01 lazy resolver: the FIRST `agent.step()` call
        # triggers `_resolve_max_context_tokens_if_needed`, which can
        # flip `max_context_tokens` from the class default to the
        # resolved-per-model value. We mutate just before yielding the
        # assistant message with usage — any usage event broadcast AFTER
        # this yield should reflect the new value.
        self.llm.max_context_tokens = self._resolved_max_context_tokens
        yield Message.assistant(
            "ok",
            usage=TokenUsage(input_tokens=42, output_tokens=7),
        )

    async def resume_after_auth(self) -> AsyncIterator[Message]:  # pragma: no cover
        if False:
            yield  # type: ignore[unreachable]

    def reset(self) -> None:  # pragma: no cover
        self.messages = []


async def test_usage_event_reflects_live_max_context_tokens_at_emission(
    monkeypatch,
) -> None:
    """Pin F6.5 L04 HAT-cycle fix: usage event reads max_context_tokens LIVE.

    The L01 lazy resolver runs inside the first ``agent.step()`` call.
    ``_process_and_broadcast`` must NOT cache ``max_context_tokens`` at
    function entry — it must read the attribute live at usage emission
    so the resolved value appears on the FIRST message, not the second.
    """
    # Stub out the Ollama auto-load (external state, not under test).
    monkeypatch.setattr(
        web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        web_app, "_save_session_to_db", AsyncMock(return_value=None)
    )

    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    # Initial = the LLMProvider class default (128k from base.py).
    # Resolved = a deliberately-distinct value (32_000) so a wrong
    # broadcast is unambiguous. A real-world example: OpenRouter resolves
    # a small open-weight model from 128k default down to (e.g.) 32k.
    INITIAL = 128_000
    RESOLVED = 32_000
    agent = _LiveReadStubAgent(
        initial_max_context_tokens=INITIAL,
        resolved_max_context_tokens=RESOLVED,
    )
    session = Session(
        id="cs-live-read",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-15T00:00:00+00:00",
    )

    await _process_and_broadcast(session, "trigger usage")

    # Find the usage event (non-interim — the final one emitted by the
    # ASSISTANT branch in _process_and_broadcast).
    usage_events = [
        p
        for p in captured
        if p.get("type") == "usage" and not p.get("is_interim")
    ]
    assert len(usage_events) == 1, (
        f"expected exactly one final usage event, got {len(usage_events)}: "
        f"{usage_events!r}"
    )
    usage_event = usage_events[0]

    # The contract: max_context_tokens in the broadcast event reflects
    # the LIVE attribute value at emission time (RESOLVED), NOT the
    # value at function entry (INITIAL). If _process_and_broadcast
    # captured the value at the top, this assertion would fail with
    # max_context_tokens == 128_000.
    assert usage_event["max_context_tokens"] == RESOLVED, (
        "_process_and_broadcast must read max_context_tokens LIVE at usage "
        "emission; eager-capture at function entry would emit "
        f"{INITIAL} instead of {RESOLVED}. Got: {usage_event!r}"
    )
    # Sanity: agent.llm.max_context_tokens is indeed the resolved value
    # (confirms the mutation in step() ran).
    assert agent.llm.max_context_tokens == RESOLVED


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
