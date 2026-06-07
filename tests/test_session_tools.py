"""Unit + integration tests for the four ``shell_session_*`` tools.

Most tests use ``MockPtySession`` (from ``tests._pty_fixtures``) injected
via monkeypatching ``the_one.tools.sessions.create_pty_session`` so unit
runs stay fast and deterministic. ONE end-to-end test
(``test_end_to_end_real_pty_round_trip``) drives a real
``UnixPtySession`` through the full tool chain to pin the integration
contract.

``pytest-asyncio`` runs in auto mode (``asyncio_mode = "auto"``); test
functions are plain ``async def`` — no ``@pytest.mark.asyncio`` needed.

Every test goes through the autouse ``_registry_cleanup`` fixture which
calls ``await _clear_for_test()`` afterwards so the next test starts
with an empty registry and a fresh reaper task slot.
"""

from __future__ import annotations

import os

import pytest

from tests._pty_fixtures import MockPtySession
from the_one.tools import _session_registry
from the_one.tools._session_registry import _clear_for_test
from the_one.tools.execution import ExecutionConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.sessions import (
    ShellSessionCloseTool,
    ShellSessionListTool,
    ShellSessionSendTool,
    ShellSessionStartTool,
)


@pytest.fixture(autouse=True)
async def _registry_cleanup():
    """Reset module-level registry state after every test."""
    yield
    await _clear_for_test()


def _cross(allowlist: list[str] | None = None) -> dict:
    """Build the per-call ``cross_configs`` view a session tool expects.

    Defaults to ``path_allowlist=["~"]`` (Pydantic field default) which
    permits ``$HOME``-rooted paths. Tests passing an explicit allowlist
    override it.
    """
    if allowlist is None:
        return {FilesystemConfig: FilesystemConfig()}
    return {FilesystemConfig: FilesystemConfig(path_allowlist=allowlist)}


# ────────────────────────────────────────────────────────────────────────────
# ShellSessionStartTool
# ────────────────────────────────────────────────────────────────────────────


async def test_start_returns_pty_session_id(monkeypatch, tmp_path) -> None:
    """``shell_session_start`` returns a ``pty-{32 hex}`` token."""
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])
    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    sid = await tool.execute(cwd=str(tmp_path))
    assert sid.startswith("pty-")
    # ``pty-`` (4) + 32-char uuid4 hex = 36 total.
    assert len(sid) == 36


async def test_start_rejects_none_agent_name(tmp_path) -> None:
    """``agent_name=None`` (introspection path) → constraint refusal."""
    tool = ShellSessionStartTool(
        ExecutionConfig(),
        cross_configs=_cross(allowlist=[str(tmp_path)]),
        agent_name=None,
    )
    out = await tool.execute(cwd=str(tmp_path))
    assert out == "[error] [constraint] session tools require an agent context"


async def test_start_rejects_cwd_outside_allowlist(monkeypatch, tmp_path) -> None:
    """``cwd`` that fails ``_cwd_check`` → constraint refusal."""
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])
    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    out = await tool.execute(cwd="/etc")
    assert out.startswith("[error] [constraint]"), out


async def test_start_max_concurrent_sessions(monkeypatch, tmp_path) -> None:
    """6th ``start`` past a 5-cap returns the documented constraint error."""
    cfg = ExecutionConfig()  # default max_concurrent_sessions = 5
    # Pre-register 5 mock sessions for the agent so the cap is reached.
    for _ in range(5):
        await _session_registry.register(
            "alpha",
            _session_registry.new_session_id(),
            MockPtySession(),
            ttl_seconds=300,
        )
    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(
        cfg, cross_configs=_cross(allowlist=[str(tmp_path)]), agent_name="alpha"
    )
    out = await tool.execute(cwd=str(tmp_path))
    assert out == (
        "[error] [constraint] max concurrent sessions reached (5); close an existing session first"
    )


async def test_start_default_cwd_validates_via_cwd_check(monkeypatch, tmp_path) -> None:
    """Even the $HOME default path is run through ``_cwd_check`` — if
    $HOME is not in the allowlist, ``start`` refuses."""
    cfg = ExecutionConfig()
    # Allowlist that does NOT include $HOME — use a tmp_path subdir.
    cross = _cross(allowlist=[str(tmp_path)])
    # Force HOME to a path outside the allowlist for this test.
    monkeypatch.setenv("HOME", "/nonexistent-home-for-test")
    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    out = await tool.execute()  # no cwd → defaults to $HOME
    assert out.startswith("[error] [constraint]"), out


# ────────────────────────────────────────────────────────────────────────────
# ShellSessionSendTool
# ────────────────────────────────────────────────────────────────────────────


async def test_send_rejects_none_agent_name() -> None:
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name=None)
    out = await tool.execute(session_id="pty-anything", input="echo hi")
    assert out == "[error] [constraint] session tools require an agent context"


async def test_send_denylist_trip() -> None:
    """``shell_session_send`` re-applies ``_command_check`` per call
    (Decision 11). ``sudo whoami`` trips the ``"sudo "`` token."""
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id="pty-anything", input="sudo whoami")
    assert out == "[error] [constraint] command contains denylisted token 'sudo '"


async def test_send_unknown_session_id() -> None:
    """Unknown session_id → constraint refusal naming the id."""
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id="pty-does-not-exist", input="echo hi")
    assert out.startswith("[error] [constraint] session 'pty-does-not-exist'")
    assert "not owned" in out or "does not exist" in out


async def test_send_cross_agent_isolation() -> None:
    """Agent B cannot ``send`` against agent A's session id."""
    sid = _session_registry.new_session_id()
    await _session_registry.register("alpha", sid, MockPtySession(), ttl_seconds=300)
    tool_b = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="beta")
    out = await tool_b.execute(session_id=sid, input="echo hi")
    assert out.startswith(f"[error] [constraint] session '{sid}'")
    assert "not owned" in out or "does not exist" in out


async def test_send_happy_path_returns_truncated_text() -> None:
    """Mock session returns canned bytes; tool runs through
    ``_truncate_output`` and returns the decoded text."""
    sid = _session_registry.new_session_id()
    mock = MockPtySession()
    mock.send_response = b"hello world\n"
    await _session_registry.register("alpha", sid, mock, ttl_seconds=300)
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id=sid, input="echo hello world")
    assert "hello world" in out
    # No ``[stderr]`` marker — PTY merges streams; we pass b"" for stderr.
    assert "[stderr]" not in out
    assert mock.sent == [("echo hello world", ExecutionConfig().timeout_seconds_default)]


async def test_send_clips_timeout_above_max() -> None:
    """Agent passing ``timeout=999`` is clipped to the operator-set max
    (default 120) and that clipped value is what the session sees."""
    sid = _session_registry.new_session_id()
    mock = MockPtySession()
    await _session_registry.register("alpha", sid, mock, ttl_seconds=300)
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    await tool.execute(session_id=sid, input="echo hi", timeout=999)
    assert mock.sent == [("echo hi", 120.0)]


async def test_send_timeout_emits_send_timed_out_message() -> None:
    """``asyncio.TimeoutError`` from ``session.send`` → ``[error] Send
    timed out after Ns`` (distinct wording from one-shot Shell)."""
    import asyncio

    class TimeoutMock(MockPtySession):
        async def send(
            self,
            input: str,
            timeout: float = 30.0,  # noqa: A002
        ) -> bytes:
            raise asyncio.TimeoutError()

    sid = _session_registry.new_session_id()
    await _session_registry.register("alpha", sid, TimeoutMock(), ttl_seconds=300)
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id=sid, input="sleep 60", timeout=5)
    assert out == "[error] Send timed out after 5s"


async def test_send_generic_exception_envelope() -> None:
    """Non-constraint, non-timeout exceptions surface via the generic
    ``[error] {e}`` clause."""

    class BoomMock(MockPtySession):
        async def send(
            self,
            input: str,
            timeout: float = 30.0,  # noqa: A002
        ) -> bytes:
            raise OSError("EIO from closed master_fd")

    sid = _session_registry.new_session_id()
    await _session_registry.register("alpha", sid, BoomMock(), ttl_seconds=300)
    tool = ShellSessionSendTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id=sid, input="ls")
    assert out == "[error] EIO from closed master_fd"


# ────────────────────────────────────────────────────────────────────────────
# ShellSessionCloseTool
# ────────────────────────────────────────────────────────────────────────────


async def test_close_rejects_none_agent_name() -> None:
    tool = ShellSessionCloseTool(ExecutionConfig(), cross_configs=_cross(), agent_name=None)
    out = await tool.execute(session_id="pty-anything")
    assert out == "[error] [constraint] session tools require an agent context"


async def test_close_removes_session_and_reports_success() -> None:
    sid = _session_registry.new_session_id()
    mock = MockPtySession()
    await _session_registry.register("alpha", sid, mock, ttl_seconds=300)
    tool = ShellSessionCloseTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id=sid)
    assert out == f"closed {sid}"
    assert mock.close_count == 1
    assert await _session_registry.get("alpha", sid) is None


async def test_close_unknown_session() -> None:
    tool = ShellSessionCloseTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute(session_id="pty-nope")
    assert out.startswith("[error] [constraint] session 'pty-nope'")
    assert "not owned" in out or "does not exist" in out


# ────────────────────────────────────────────────────────────────────────────
# ShellSessionListTool
# ────────────────────────────────────────────────────────────────────────────


async def test_list_rejects_none_agent_name() -> None:
    tool = ShellSessionListTool(ExecutionConfig(), cross_configs=_cross(), agent_name=None)
    out = await tool.execute()
    assert out == "[error] [constraint] session tools require an agent context"


async def test_list_empty_returns_no_open_sessions() -> None:
    tool = ShellSessionListTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute()
    assert out == "(no open sessions)"


async def test_list_returns_newline_joined_sids() -> None:
    sid_a = _session_registry.new_session_id()
    sid_b = _session_registry.new_session_id()
    await _session_registry.register("alpha", sid_a, MockPtySession(), ttl_seconds=300)
    await _session_registry.register("alpha", sid_b, MockPtySession(), ttl_seconds=300)
    # Cross-agent session is NOT included.
    await _session_registry.register(
        "beta", _session_registry.new_session_id(), MockPtySession(), ttl_seconds=300
    )
    tool = ShellSessionListTool(ExecutionConfig(), cross_configs=_cross(), agent_name="alpha")
    out = await tool.execute()
    lines = out.split("\n")
    assert set(lines) == {sid_a, sid_b}


# ────────────────────────────────────────────────────────────────────────────
# End-to-end (real UnixPtySession) — pins the integration contract.
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(os.name != "posix", reason="UnixPtySession requires posix")
async def test_end_to_end_real_pty_round_trip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spawn a real shell, send ``echo`` through the tool layer, list,
    close — verify the full chain works without mocks.

    Pinned to passthrough (THE_ONE_SANDBOX_DISABLED=1) by design: under real
    bwrap, the kernel mounts a fresh tmpfs at ``/tmp``, which shadows any
    ``tmp_path`` workspace created there — making the session's cwd invisible
    inside the sandbox regardless of what writable paths the profile carries.
    This is a tool-layer round-trip test, not a containment test.  Real-bwrap
    containment is covered by ``tests/test_pty_sandbox.py`` and the
    ``/behavior-test pty-session-containment`` spec.
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])
    start = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    send = ShellSessionSendTool(cfg, cross_configs=cross, agent_name="alpha")
    listt = ShellSessionListTool(cfg, cross_configs=cross, agent_name="alpha")
    close = ShellSessionCloseTool(cfg, cross_configs=cross, agent_name="alpha")

    sid = await start.execute(cwd=str(tmp_path))
    assert sid.startswith("pty-"), sid
    try:
        out = await send.execute(session_id=sid, input="echo hello-pty-roundtrip")
        # The shell's echo of the command + its output may both appear;
        # the substring is what matters.
        assert "hello-pty-roundtrip" in out, out
        sids_text = await listt.execute()
        assert sid in sids_text.split("\n"), sids_text
    finally:
        closed_msg = await close.execute(session_id=sid)
    assert sid in closed_msg, closed_msg
    # And the registry no longer holds it.
    assert await _session_registry.get("alpha", sid) is None
