"""F5 L4 — WS storage-edge shim for operator-visibility tagging.

Pins the call-site contract of the shim in ``_process_and_broadcast`` and
its symmetric counterpart in ``_resume_paused_session``. The shim's job:

- On a connector-attached session (``Session.platform is not None``),
  every WS-typed message arrives as ``visibility=OPERATOR_VISIBILITY``
  and the agent's responses stay operator-only by default — EXCEPT the
  successful ``send_to_platform_channel`` tool_result, which the leg-3
  helper sets to ``visibility=None`` (peer-visible).
- On a web-native session (``Session.platform is None``), the shim is a
  no-op — messages persist with ``visibility=None``, byte-identical to
  the pre-F5 contract.

These tests stub out ``_send_to_session`` + ``_save_session_to_db`` +
``_ensure_ollama_model_loaded`` and drive ``_process_and_broadcast`` /
``_resume_paused_session`` directly with a fake agent. They do NOT
duplicate the leg-3 helper's per-rule coverage (see
``tests/test_connectors_visibility_helper.py`` for that). The focus
here is the SHIM's call-site contract:

  1. USER-override at ``pre_step_len`` for connector-attached sessions.
  2. Helper invocation gate on ``session.platform is not None``.
  3. Byte-identical no-op for web-native sessions.
  4. Defensive bounds check when ``agent.step`` raises pre-append.
  5. Platform-send carve-out lands on the WS path (helper invocation
     proof from this entry point).
  6. Symmetric tagging on ``_resume_paused_session`` after auth.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    Session,
    _process_and_broadcast,
    _resume_paused_session,
)
from the_one.llm.base import Message, ToolCall, ToolResult


class _ShimStubAgent:
    """Stub agent that mirrors the REAL Agent's append invariants.

    Distinct from ``test_app_websocket_pause_resume.py``'s ``StubAgent``
    because the shim's contract depends on the real agent's
    "Message.user(...) append BEFORE first yield + each yielded message
    appended to ``self.messages`` in order" behavior. This stub:

      - Appends ``Message.user(user_input)`` on entry to ``step``.
      - Appends each scripted yielded ``Message`` to ``self.messages``.
      - Optionally raises before the user-append (to simulate the
        bounds-check edge case in the shim) when
        ``raise_before_append`` is set.
      - Mirrors the same behaviour for ``resume_after_auth`` (no
        user-append on the resume seam).
    """

    def __init__(
        self,
        step_messages: list[Message] | None = None,
        resume_messages: list[Message] | None = None,
        deferred_tool_calls: list[ToolCall] | None = None,
        agent_messages: list[Message] | None = None,
        raise_before_append: bool = False,
    ) -> None:
        self._step_messages = step_messages or []
        self._resume_messages = resume_messages or []
        self._deferred_tool_calls = deferred_tool_calls
        self.messages: list[Message] = agent_messages or []
        self._raise_before_append = raise_before_append

        class _LLMShim:
            max_context_tokens = 128_000

        self.llm = _LLMShim()

    async def step(
        self,
        user_input: str,
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        if self._raise_before_append:
            raise RuntimeError("step failed before user-append")
        # Mirror the real Agent invariant — append the USER message
        # BEFORE first yield. The shim's USER override at pre_step_len
        # relies on this.
        self.messages.append(Message.user(user_input))
        for m in self._step_messages:
            self.messages.append(m)
            yield m

    async def resume_after_auth(self) -> AsyncIterator[Message]:
        if self._deferred_tool_calls is None:
            return
        self._deferred_tool_calls = None
        for m in self._resume_messages:
            self.messages.append(m)
            yield m


def _patch_broadcast_and_save(monkeypatch) -> list[dict[str, Any]]:
    """Stub IO sinks and return the captured broadcast list."""
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))

    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)
    return captured


# ---------------------------------------------------------------------------
# 1. USER override at pre_step_len on connector-attached sessions
# ---------------------------------------------------------------------------


async def test_connector_attached_user_message_gets_operator_visibility(
    monkeypatch,
) -> None:
    """Connector-attached session: WS-typed USER ends with
    ``visibility=OPERATOR_VISIBILITY`` at ``pre_step_len``.
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("you are an agent")
    assistant_reply = Message.assistant("hello back")
    agent = _ShimStubAgent(
        step_messages=[assistant_reply],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-L4-1",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    pre_step_len = len(session.agent.messages)
    await _process_and_broadcast(session, "operator hello")

    # USER message at pre_step_len carries operator visibility.
    user_msg = session.agent.messages[pre_step_len]
    assert user_msg.role.value == "user"
    assert user_msg.content == "operator hello"
    assert user_msg.visibility == OPERATOR_VISIBILITY


# ---------------------------------------------------------------------------
# 2. Assistant reply at pre_step_len + 1 gets operator visibility
# ---------------------------------------------------------------------------


async def test_connector_attached_assistant_reply_gets_operator_visibility(
    monkeypatch,
) -> None:
    """Connector-attached session: the assistant reply appended by
    ``agent.step`` carries ``visibility=OPERATOR_VISIBILITY``.
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    assistant_reply = Message.assistant("hi operator")
    agent = _ShimStubAgent(
        step_messages=[assistant_reply],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-L4-2",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    pre_step_len = len(session.agent.messages)
    await _process_and_broadcast(session, "ping")

    asst = session.agent.messages[pre_step_len + 1]
    assert asst.role.value == "assistant"
    assert asst.visibility == OPERATOR_VISIBILITY


# ---------------------------------------------------------------------------
# 3. Non-connector (web-native) session: byte-identical no-op
# ---------------------------------------------------------------------------


async def test_non_connector_session_unchanged(monkeypatch) -> None:
    """Web-native (``session.platform is None``) session: USER + assistant
    messages carry ``visibility=None`` (back-compat — F3 codec contract:
    absent-tag == peer-visible / no-tag).
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    assistant_reply = Message.assistant("web reply")
    agent = _ShimStubAgent(
        step_messages=[assistant_reply],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-L4-3",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        # platform defaults to None — explicit here for clarity.
        platform=None,
    )

    pre_step_len = len(session.agent.messages)
    await _process_and_broadcast(session, "web hello")

    assert session.agent.messages[pre_step_len].visibility is None
    assert session.agent.messages[pre_step_len + 1].visibility is None


# ---------------------------------------------------------------------------
# 4. Pre-step messages with sentinel visibility are not touched
# ---------------------------------------------------------------------------


async def test_pre_step_messages_untouched(monkeypatch) -> None:
    """Pre-existing history (indices < ``pre_step_len``) keeps its
    sentinel visibility after the shim runs. The helper's window-only
    contract holds at the call site.
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    system_msg.visibility = "sentinel"
    prior_user = Message.user("earlier", visibility="sentinel")
    prior_assistant = Message.assistant("earlier reply", visibility="sentinel")
    assistant_reply = Message.assistant("new reply")
    agent = _ShimStubAgent(
        step_messages=[assistant_reply],
        agent_messages=[system_msg, prior_user, prior_assistant],
    )
    session = Session(
        id="cs-L4-4",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    pre_step_len = len(session.agent.messages)
    await _process_and_broadcast(session, "new operator turn")

    # All pre-step indices keep the sentinel.
    for i in range(pre_step_len):
        assert session.agent.messages[i].visibility == "sentinel", (
            f"pre-step index {i} changed visibility"
        )

    # New USER + assistant carry OPERATOR_VISIBILITY.
    assert session.agent.messages[pre_step_len].visibility == OPERATOR_VISIBILITY
    assert session.agent.messages[pre_step_len + 1].visibility == OPERATOR_VISIBILITY


# ---------------------------------------------------------------------------
# 5. Architect-surfaced carve-out: successful platform-send tool_result
#    gets visibility=None even on the WS path.
# ---------------------------------------------------------------------------


async def test_ws_typed_with_platform_send_tool_result_gets_none(monkeypatch) -> None:
    """Operator types something; agent calls ``send_to_platform_channel``;
    the successful tool_result carries ``visibility=None`` (peer-visible)
    while the surrounding assistant text + USER stay
    ``OPERATOR_VISIBILITY``. Exercises the shared helper's
    ``is_successful_platform_send`` branch from the WS entry point.
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    assistant_with_tc = Message.assistant(
        "calling platform send",
        tool_calls=[
            ToolCall(
                id="tc-send",
                name="send_to_platform_channel",
                arguments={"content": "hello peers"},
            )
        ],
    )
    success_tool_result = Message.tool(
        ToolResult(
            tool_call_id="tc-send",
            content=f"{PLATFORM_SEND_OK_PREFIX} delivered",
            metadata=None,
        )
    )
    final_assistant = Message.assistant("sent")
    agent = _ShimStubAgent(
        step_messages=[assistant_with_tc, success_tool_result, final_assistant],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-L4-5",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    pre_step_len = len(session.agent.messages)
    await _process_and_broadcast(session, "say hello to peers")

    user_msg = session.agent.messages[pre_step_len]
    assistant_with_call = session.agent.messages[pre_step_len + 1]
    tool_result_msg = session.agent.messages[pre_step_len + 2]
    final_msg = session.agent.messages[pre_step_len + 3]

    # USER override — operator-visible.
    assert user_msg.visibility == OPERATOR_VISIBILITY
    # Surrounding assistant text stays operator-only.
    assert assistant_with_call.visibility == OPERATOR_VISIBILITY
    assert final_msg.visibility == OPERATOR_VISIBILITY
    # Successful platform-send tool_result → peer-visible (None).
    assert tool_result_msg.visibility is None


# ---------------------------------------------------------------------------
# 6. Bounds check: agent.step raises BEFORE the user-append lands
# ---------------------------------------------------------------------------


async def test_pre_step_len_bounds_check_when_step_fails_pre_append(monkeypatch) -> None:
    """If ``agent.step`` raises before its internal
    ``Message.user(...)`` append lands, the shim's bounds check
    prevents an ``IndexError`` and the visibility state is unchanged
    from the pre-step snapshot.
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    system_msg.visibility = "sentinel"
    agent = _ShimStubAgent(
        step_messages=[],
        agent_messages=[system_msg],
        raise_before_append=True,
    )
    session = Session(
        id="cs-L4-6",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    pre_step_len = len(session.agent.messages)
    # Should not raise IndexError.
    await _process_and_broadcast(session, "doomed")

    # No new messages appended; pre-step state untouched.
    assert len(session.agent.messages) == pre_step_len
    assert session.agent.messages[0].visibility == "sentinel"


# ---------------------------------------------------------------------------
# 7. Symmetric shim on _resume_paused_session
# ---------------------------------------------------------------------------


async def test_resume_after_auth_tags_resumed_messages(monkeypatch) -> None:
    """Connector-attached session whose agent has
    ``_deferred_tool_calls`` set; ``resume_after_auth`` yields one
    assistant reply; calling ``_resume_paused_session`` tags the
    appended messages with ``OPERATOR_VISIBILITY``. No USER override
    on the resume path — there is no new WS-typed USER message.
    """
    _patch_broadcast_and_save(monkeypatch)

    # Pre-pause history: system + assistant-with-tool-call + auth_required
    # tool_msg + the original USER (already operator-tagged by the
    # initial-step shim).
    system_msg = Message.system("system")
    user_msg = Message.user("operator triggered auth", visibility=OPERATOR_VISIBILITY)
    pre_assistant = Message.assistant(
        "",
        tool_calls=[ToolCall(id="tc-X", name="auth_tool", arguments={})],
        visibility=OPERATOR_VISIBILITY,
    )
    auth_tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc-X",
            content="auth required",
            metadata={
                "is_auth_required": True,
                "source_id": "src-X",
                "tool_call_id": "tc-X",
            },
        ),
        visibility=OPERATOR_VISIBILITY,
    )

    # Resume yields a successful tool_result (no platform-send) +
    # a final assistant reply — both should end OPERATOR_VISIBILITY.
    resumed_tool_result = Message.tool(
        ToolResult(tool_call_id="tc-X", content="auth ok", metadata=None)
    )
    final_assistant = Message.assistant("auth resolved, proceeding")

    agent = _ShimStubAgent(
        resume_messages=[resumed_tool_result, final_assistant],
        deferred_tool_calls=[ToolCall(id="tc-X", name="auth_tool", arguments={})],
        agent_messages=[system_msg, user_msg, pre_assistant, auth_tool_msg],
    )
    session = Session(
        id="cs-L4-7",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    pre_resume_len = len(session.agent.messages)
    await _resume_paused_session(session)

    # The resumed tool_result + final assistant carry OPERATOR_VISIBILITY.
    assert session.agent.messages[pre_resume_len].visibility == OPERATOR_VISIBILITY
    assert session.agent.messages[pre_resume_len + 1].visibility == OPERATOR_VISIBILITY

    # Pre-resume messages untouched.
    assert session.agent.messages[0].visibility is None  # system
    assert session.agent.messages[1].visibility == OPERATOR_VISIBILITY  # user
    assert session.agent.messages[2].visibility == OPERATOR_VISIBILITY  # asst
    assert session.agent.messages[3].visibility == OPERATOR_VISIBILITY  # tool


# ---------------------------------------------------------------------------
# 8. Resume on web-native session is a no-op (regression net)
# ---------------------------------------------------------------------------


async def test_resume_on_non_connector_session_does_not_tag(monkeypatch) -> None:
    """Resume on a web-native session: appended messages keep
    ``visibility=None``. Byte-identical to pre-F5 behaviour.
    """
    _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    resumed_assistant = Message.assistant("resumed reply")
    agent = _ShimStubAgent(
        resume_messages=[resumed_assistant],
        deferred_tool_calls=[ToolCall(id="tc-X", name="auth_tool", arguments={})],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-L4-8",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform=None,
    )

    pre_resume_len = len(session.agent.messages)
    await _resume_paused_session(session)

    assert session.agent.messages[pre_resume_len].visibility is None


# ---------------------------------------------------------------------------
# 9. F6 L6 — live-broadcast carries visibility on connector-attached session
# ---------------------------------------------------------------------------


async def test_live_broadcast_carries_operator_visibility_on_connector_attached_session(
    monkeypatch,
) -> None:
    """F6 L6: closes the F5 live-broadcast carry-forward.

    The user-echo event broadcast by ``_process_and_broadcast`` BEFORE
    ``agent.step`` runs must carry ``visibility=OPERATOR_VISIBILITY``
    on a connector-attached session (``session.platform is not None``).
    The first captured broadcast event is the user echo.
    """
    captured = _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    assistant_reply = Message.assistant("ack")
    agent = _ShimStubAgent(
        step_messages=[assistant_reply],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-F6L6-1",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform="stub",
    )

    await _process_and_broadcast(session, "operator hello")

    # The first broadcast event is the user echo.
    assert captured, "expected at least one broadcast event"
    user_event = captured[0]
    assert user_event["type"] == "user"
    assert user_event["content"] == "operator hello"
    assert user_event.get("visibility") == OPERATOR_VISIBILITY


# ---------------------------------------------------------------------------
# 10. F6 L6 — live-broadcast omits visibility on web-native session
# ---------------------------------------------------------------------------


async def test_live_broadcast_omits_visibility_on_web_native_session(
    monkeypatch,
) -> None:
    """F6 L6 sister test: on a web-native session (``platform is None``),
    the user-echo event MUST NOT carry the ``visibility`` key. Mirrors
    the codec's projection rule at ``db/codec.py:173-176`` — only emit
    the key when the value is meaningful.
    """
    captured = _patch_broadcast_and_save(monkeypatch)

    system_msg = Message.system("system")
    assistant_reply = Message.assistant("web ack")
    agent = _ShimStubAgent(
        step_messages=[assistant_reply],
        agent_messages=[system_msg],
    )
    session = Session(
        id="cs-F6L6-2",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-18T00:00:00+00:00",
        platform=None,
    )

    await _process_and_broadcast(session, "web hello")

    assert captured, "expected at least one broadcast event"
    user_event = captured[0]
    assert user_event["type"] == "user"
    assert user_event["content"] == "web hello"
    assert "visibility" not in user_event
