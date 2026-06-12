"""Tests for ``the_one.platform.pty`` (F4 L5a).

Pin the ``PtySession`` ABC contract and the ``UnixPtySession``
concrete implementation. The Windows-guard test is symmetric:
on Posix it asserts the import succeeds; on Windows (skipped on
this Linux dev container) it would assert the import-time raise.

All tests use ``try/finally: await s.close()`` to avoid leaking
child processes between tests — a leaked PTY child can lock the
master fd and cause the next test to hang.

``pytest-asyncio`` is installed with ``asyncio_mode = "auto"`` in
``pyproject.toml`` — ``async def test_*`` is auto-detected. Do
NOT add ``@pytest.mark.asyncio`` decorators.
"""

from __future__ import annotations

import asyncio
import os

import pytest

# Skip the entire module on non-Posix platforms — ``UnixPtySession``
# requires ``pty.fork()`` and the module-level Windows guard would
# raise ``NotImplementedError`` on import.
pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="UnixPtySession requires POSIX (pty.fork)",
)

from the_one.platform.pty import (  # noqa: E402  (after pytestmark skip)
    PtySession,
    UnixPtySession,
    create_pty_session,
)

# ---------------------------------------------------------------------------
# Passthrough pin — DD7
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _pin_to_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin every test in this file to the PassthroughSandbox backend.

    Sets ``THE_ONE_SANDBOX_DISABLED=1`` so ``get_sandbox_backend()``
    returns passthrough regardless of whether bwrap is present on the
    host.  Function-scoped (pytest's ``monkeypatch`` is function-scoped)
    so the env var is restored after each test.

    Must be function-scoped — a module-scoped autouse fixture cannot
    consume the function-scoped ``monkeypatch`` fixture (pytest raises).
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")


# ---------------------------------------------------------------------------
# ABC contract pins
# ---------------------------------------------------------------------------


class TestPtySessionAbc:
    """Pin the abstract surface so accidental rename/removal trips a
    fast test rather than a runtime AttributeError in the registry."""

    def test_abc_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            PtySession()  # type: ignore[abstract]

    def test_unix_session_is_pty_session(self) -> None:
        assert issubclass(UnixPtySession, PtySession)

    def test_factory_returns_pty_session(self) -> None:
        s = create_pty_session()
        assert isinstance(s, PtySession)
        assert isinstance(s, UnixPtySession)


# ---------------------------------------------------------------------------
# UnixPtySession lifecycle
# ---------------------------------------------------------------------------


class TestUnixPtySession:
    async def test_start_creates_alive_session(self) -> None:
        s = UnixPtySession()
        try:
            await s.start()
            assert s.is_alive
        finally:
            await s.close()

    async def test_send_echoes_input(self) -> None:
        s = UnixPtySession()
        try:
            await s.start()
            out = await s.send("echo hello-pty")
            assert b"hello-pty" in out, out
        finally:
            await s.close()

    async def test_send_round_trip_pwd(self, tmp_path) -> None:
        s = UnixPtySession(cwd=tmp_path)
        try:
            await s.start()
            out = await s.send("pwd")
            # ``tmp_path`` may resolve to a symlink target via shell's PWD
            # tracking on some systems; substring check is sufficient and
            # tolerates trailing newlines/escapes.
            assert str(tmp_path).encode() in out, out
        finally:
            await s.close()

    async def test_send_after_close_raises(self) -> None:
        s = UnixPtySession()
        await s.start()
        await s.close()
        with pytest.raises(RuntimeError):
            await s.send("echo nope")

    async def test_close_is_idempotent(self) -> None:
        s = UnixPtySession()
        await s.start()
        await s.close()
        # Second close must not raise.
        await s.close()

    async def test_close_kills_subprocess(self) -> None:
        s = UnixPtySession()
        await s.start()
        pid = s._pid  # capture before close zeroes it
        assert pid is not None
        await s.close()
        # Give the kernel a moment to fully reap the zombie.
        await asyncio.sleep(0.05)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    async def test_send_timeout_raises_when_no_output(self) -> None:
        """A blocking command (``read x`` waits for stdin) with terminal
        echo disabled produces NO output. The idle-mark check never
        succeeds (buffer is empty), so the timeout window elapses and
        ``send`` raises ``asyncio.TimeoutError``.

        Why disable echo first: by default, the PTY echoes input bytes
        back on the master fd. With echo on, sending ``read x\\n`` fills
        the buffer with the echoed bytes and returns successfully on
        idle-mark — masking the timeout-on-empty-buffer code path. We
        send ``stty -echo`` first to force the empty-buffer case.

        Why ``/bin/sh`` (dash) instead of ``/bin/bash``: on WSL2, bash emits
        bracketed-paste-mode control sequences (``\\x1b[?2004l``) when a
        command is submitted, even with echo disabled. These sequences fill
        the buffer and prevent TimeoutError.  ``/bin/sh`` (dash) has no
        readline/bracketed-paste integration and produces zero output for a
        blocked ``read x`` with echo off — making the test deterministic
        across host environments.
        """
        s = UnixPtySession(shell="/bin/sh")
        try:
            await s.start()
            # Drain echoed bytes from the stty command itself; we don't
            # care about its output, only that echo is off afterwards.
            await s.send("stty -echo")
            with pytest.raises(asyncio.TimeoutError):
                # ``read x`` blocks for input; with echo off, no bytes
                # appear on the master fd. Tight timeout exhausts the
                # budget before any byte arrives.
                await s.send("read x", timeout=0.5)
        finally:
            await s.close()

    async def test_env_allowlist_invariant(self, monkeypatch) -> None:
        """``THE_ONE_TEST_LEAK`` set in parent must NOT be visible to the
        spawned shell. ``monkeypatch.setenv`` MUST run before
        ``session.start()`` is called — ``_build_subprocess_env`` is now
        captured in the parent inside ``start()`` (before ``pty.fork()``,
        for fork-safety — DD1), so the monkeypatched env must be in place
        before ``start()`` is called, not merely before ``__init__``."""
        monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret-pty-allowlist")
        # Use ``/bin/bash`` explicitly for deterministic ``env`` output
        # regardless of the dev container's ``$SHELL``.
        s = UnixPtySession(shell="/bin/bash")
        try:
            await s.start()
            out = await s.send("env | grep THE_ONE_TEST_LEAK || echo NOT_FOUND_OK")
            assert b"NOT_FOUND_OK" in out, out
            assert b"secret-pty-allowlist" not in out, out
        finally:
            await s.close()

    async def test_last_activity_updated(self) -> None:
        s = UnixPtySession()
        try:
            await s.start()
            t0 = s.last_activity
            # Sleep a hair so the monotonic delta is observable across
            # platforms with coarser clocks.
            await asyncio.sleep(0.01)
            await s.send("echo tick")
            assert s.last_activity > t0
        finally:
            await s.close()

    async def test_is_alive_false_after_subprocess_exits(self) -> None:
        s = UnixPtySession()
        try:
            await s.start()
            assert s.is_alive
            # Tell the shell to exit; idle-mark returns its goodbye bytes
            # (or none). Then poll ``is_alive`` briefly until kernel
            # reports the child gone.
            try:
                await s.send("exit", timeout=1.0)
            except asyncio.TimeoutError:
                # Some shells exit without echoing anything — accepted.
                pass
            # Give the kernel a moment.
            for _ in range(40):
                if not s.is_alive:
                    break
                await asyncio.sleep(0.05)
            assert not s.is_alive
        finally:
            await s.close()

    async def test_cannot_start_twice(self) -> None:
        s = UnixPtySession()
        try:
            await s.start()
            with pytest.raises(RuntimeError):
                await s.start()
        finally:
            await s.close()


# ---------------------------------------------------------------------------
# Windows guard — pin the import-time raise on Windows.
# ---------------------------------------------------------------------------


class TestWindowsGuard:
    """On Windows, importing ``the_one.platform.pty`` must raise
    ``NotImplementedError`` at IMPORT time. On Posix (this dev container)
    the test is skipped; the module-level ``pytestmark`` already filters
    out the rest of this file's Posix-specific tests on Windows."""

    @pytest.mark.skipif(
        os.name != "nt",
        reason="Windows-only guard test",
    )
    def test_import_raises_on_windows(self) -> None:  # pragma: no cover
        # Force re-import to trigger the guard. Importing the module
        # under ``importlib`` catches the raise without polluting the
        # parent test module's import state.
        import importlib

        with pytest.raises(NotImplementedError):
            importlib.import_module("the_one.platform.pty")


# ---------------------------------------------------------------------------
# Sanity guards on the helper internals — narrow tests to catch regressions
# in the subtle bits (clamped select timeout, idle-mark vs. timeout).
# ---------------------------------------------------------------------------


class TestReadUntilIdleEdgeCases:
    """Pin the trickier internals via direct call. These avoid the
    full fork+exec round-trip when possible."""

    async def test_select_timeout_clamped_when_budget_exhausted(self) -> None:
        """Once the timeout budget runs out, the inner ``select`` timeout
        must clamp to ``0.0`` (not negative). Verified indirectly by
        running a session that times out cleanly with raise rather than
        a ``ValueError``. Echo is disabled first so the buffer stays
        empty (otherwise idle-mark on echoed input bytes returns early).

        Why ``/bin/sh`` (dash) instead of ``/bin/bash``: see
        ``test_send_timeout_raises_when_no_output`` for the rationale —
        bash on WSL2 emits bracketed-paste control sequences that fill
        the buffer and prevent TimeoutError. Dash is deterministic.
        """
        s = UnixPtySession(shell="/bin/sh")
        try:
            await s.start()
            await s.send("stty -echo")
            # ``read x`` blocks; very tight timeout ensures the budget
            # exhausts mid-loop. If clamping is broken, ``select`` raises
            # ``ValueError`` instead of yielding TimeoutError.
            with pytest.raises(asyncio.TimeoutError):
                await s.send("read x", timeout=0.2)
        finally:
            await s.close()

    async def test_is_alive_handles_child_process_error(self) -> None:
        """If the kernel removes the entry between ``waitpid`` calls,
        ``is_alive`` must catch ``ChildProcessError`` and return False
        rather than propagating."""
        s = UnixPtySession()
        await s.start()
        pid = s._pid
        assert pid is not None
        # Manually reap the child so a subsequent ``waitpid`` raises
        # ``ChildProcessError``.
        os.kill(pid, 9)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        # ``is_alive`` must not raise.
        assert s.is_alive is False
        # And ``close`` must remain idempotent / not raise.
        await s.close()
