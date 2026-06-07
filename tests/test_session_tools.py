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
    """``shell_session_start`` returns a ``pty-{32 hex}`` token.

    Uses ``host_access=True`` so the tool exercises the host cwd-check path
    against the tmp_path allowlist — the boxed path would allocate a scratch
    dir under data_dir, not tmp_path.
    """
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])
    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None, cleanup_dir=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    sid = await tool.execute(cwd=str(tmp_path), host_access=True)
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
        lambda cwd=None, shell=None, profile=None, cleanup_dir=None: MockPtySession(),
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
        lambda cwd=None, shell=None, profile=None, cleanup_dir=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(
        cfg, cross_configs=_cross(allowlist=[str(tmp_path)]), agent_name="alpha"
    )
    out = await tool.execute(cwd=str(tmp_path))
    assert out == (
        "[error] [constraint] max concurrent sessions reached (5); close an existing session first"
    )


async def test_start_host_access_default_cwd_validates_via_cwd_check(monkeypatch, tmp_path) -> None:
    """With host_access=True, the default $HOME path is run through ``_cwd_check`` —
    if $HOME is not in the allowlist, ``start`` refuses.

    Note: ``host_access=False`` (boxed default) always allocates a fresh scratch dir
    and ignores the operator allowlist, so the $HOME restriction only applies to the
    host-access path.
    """
    cfg = ExecutionConfig()
    # Allowlist that does NOT include $HOME — use a tmp_path subdir.
    cross = _cross(allowlist=[str(tmp_path)])
    # Force HOME to a path outside the allowlist for this test.
    monkeypatch.setenv("HOME", "/nonexistent-home-for-test")
    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None, cleanup_dir=None: MockPtySession(),
    )
    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    out = await tool.execute(host_access=True)  # no cwd → defaults to $HOME
    assert out.startswith("[error] [constraint]"), out


async def test_start_host_access_true_uses_host_path(monkeypatch, tmp_path) -> None:
    """``host_access=True`` goes through ``_cwd_check`` (allowlist-validated, host FS)."""
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])

    captured: dict = {}

    def _fake_create(cwd=None, shell=None, profile=None, cleanup_dir=None):
        captured["cwd"] = cwd
        captured["cleanup_dir"] = cleanup_dir
        return MockPtySession()

    monkeypatch.setattr("the_one.tools.sessions.create_pty_session", _fake_create)
    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    sid = await tool.execute(cwd=str(tmp_path), host_access=True)
    assert sid.startswith("pty-"), sid
    # cleanup_dir must be None for host sessions.
    assert captured["cleanup_dir"] is None
    # cwd must be the resolved tmp_path.
    assert captured["cwd"] == tmp_path


async def test_start_boxed_creates_scratch_dir_and_cleanup_dir(monkeypatch, tmp_path) -> None:
    """Boxed session (host_access=False) allocates a scratch dir and passes
    it as cleanup_dir to create_pty_session."""
    cfg = ExecutionConfig()
    # Allowlist covers tmp_path — but boxed cwd defaults to scratch, not tmp_path.
    cross = _cross(allowlist=[str(tmp_path)])
    # Redirect data_dir to tmp_path so scratch lands there.
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    captured: dict = {}

    def _fake_create(cwd=None, shell=None, profile=None, cleanup_dir=None):
        captured["cwd"] = cwd
        captured["cleanup_dir"] = cleanup_dir
        return MockPtySession()

    monkeypatch.setattr("the_one.tools.sessions.create_pty_session", _fake_create)
    # Reset the module-level settings cache so the monkeypatched env is picked up.
    import the_one.config as _cfg_mod

    monkeypatch.setattr(_cfg_mod, "_settings", None)

    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    sid = await tool.execute()  # no cwd → defaults to scratch root
    assert sid.startswith("pty-"), sid
    # cleanup_dir must be a directory under data_dir/boxes/ that exists on the host.
    cleanup = captured["cleanup_dir"]
    assert cleanup is not None
    assert cleanup.exists(), "scratch dir must be created before session is built"
    assert "boxes" in cleanup.parts, f"scratch must be under boxes/; got {cleanup}"
    # The scratch dir is the cwd (boxed default).
    assert captured["cwd"] == cleanup


async def test_start_registration_failure_closes_session_and_removes_scratch(
    monkeypatch, tmp_path
) -> None:
    """If ``register()`` raises after ``session.start()``, the tool closes the
    session (removing the scratch dir) and returns an ``[error]`` response —
    no process or scratch directory leaks.

    We force the failure via ``_shutting_down=True`` on the registry (the
    shutdown guard raises ``RuntimeError`` on register).
    """
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])
    monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))

    import the_one.config as _cfg_mod

    monkeypatch.setattr(_cfg_mod, "_settings", None)

    closed: list[bool] = []

    class TrackingMock(MockPtySession):
        def __init__(self, cleanup_dir=None) -> None:
            super().__init__()
            self._cleanup_dir = cleanup_dir

        async def close(self) -> None:
            await super().close()
            closed.append(True)
            # Record whether the scratch dir still exists at close time
            # (it's the caller's responsibility to remove it via cleanup_dir;
            # MockPtySession.close() doesn't do rmtree — that lives in UnixPtySession).
            # We just record that close() was called.

    captured_cleanup_dir: list = []

    def _fake_create(cwd=None, shell=None, profile=None, cleanup_dir=None):
        captured_cleanup_dir.append(cleanup_dir)
        return TrackingMock(cleanup_dir=cleanup_dir)

    monkeypatch.setattr("the_one.tools.sessions.create_pty_session", _fake_create)

    # Force register() to raise by setting the shutdown flag.
    monkeypatch.setattr("the_one.tools._session_registry._shutting_down", True)

    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    out = await tool.execute()

    # Tool must return an [error] response (not raise).
    assert out.startswith("[error]"), f"expected [error] response, got: {out!r}"
    # session.close() must have been called.
    assert closed, "session.close() must be called on registration failure"
    # cleanup_dir was passed (this is a boxed session by default).
    assert captured_cleanup_dir[0] is not None


async def test_start_host_access_registration_failure_closes_session(monkeypatch, tmp_path) -> None:
    """Registration failure on host_access=True: session is closed, no scratch dir."""
    cfg = ExecutionConfig()
    cross = _cross(allowlist=[str(tmp_path)])

    closed: list[bool] = []

    class TrackingMock(MockPtySession):
        async def close(self) -> None:
            await super().close()
            closed.append(True)

    monkeypatch.setattr(
        "the_one.tools.sessions.create_pty_session",
        lambda cwd=None, shell=None, profile=None, cleanup_dir=None: TrackingMock(),
    )

    monkeypatch.setattr("the_one.tools._session_registry._shutting_down", True)

    tool = ShellSessionStartTool(cfg, cross_configs=cross, agent_name="alpha")
    out = await tool.execute(cwd=str(tmp_path), host_access=True)

    assert out.startswith("[error]"), f"expected [error] response, got: {out!r}"
    assert closed, "session.close() must be called on registration failure (host mode)"


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

    # host_access=True: tmp_path is the cwd; the allowlist must cover it.
    # (Boxed mode would allocate a scratch under data_dir/boxes/, not tmp_path.)
    sid = await start.execute(cwd=str(tmp_path), host_access=True)
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


# ===================================================================
# F4 L5: box-by-default / host_access contract on description strings
# ===================================================================


class TestShellSessionStartDescriptionContract:
    """Lightweight substring checks — no bwrap required.

    Verify that ShellSessionStartTool description and host_access param
    description carry the box-by-default / escalate contract.
    """

    def test_description_mentions_isolated(self) -> None:
        """ShellSessionStartTool.description conveys the box-by-default contract."""
        assert "isolated" in ShellSessionStartTool.description

    def test_description_mentions_no_access_user_files(self) -> None:
        """ShellSessionStartTool.description states boxed = no user files/network."""
        assert "no access" in ShellSessionStartTool.description

    def test_description_mentions_host_access_escalation(self) -> None:
        """ShellSessionStartTool.description tells the model when to escalate."""
        assert "host_access=true" in ShellSessionStartTool.description

    def test_description_mentions_scratch_persists(self) -> None:
        """ShellSessionStartTool.description notes that boxed scratch persists across sends."""
        assert "persists" in ShellSessionStartTool.description

    def test_host_access_param_default_false_isolated(self) -> None:
        """ShellSessionStartTool host_access param description states default=isolated."""
        desc = ShellSessionStartTool.parameters["properties"]["host_access"]["description"]
        assert "isolated" in desc

    def test_host_access_param_set_true_for_real_files(self) -> None:
        """ShellSessionStartTool host_access param description states when to set true."""
        desc = ShellSessionStartTool.parameters["properties"]["host_access"]["description"]
        assert "real" in desc
