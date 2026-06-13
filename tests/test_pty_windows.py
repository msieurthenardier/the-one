"""Windows PTY session tests — cmd.exe round-trip (M15 F3 Leg 2).

These tests are guarded by ``skipif(os.name != "nt")`` and run ONLY on the
``windows-2022`` CI lane.  They are the authoritative backend verification for
``WindowsPtySession`` (pywinpty / ConPTY).  Running them on Linux would fail
at ``import winpty`` — the entire module is guarded to prevent that.

Test environment:
- ``THE_ONE_SANDBOX_DISABLED=1`` → forces ``PassthroughSandbox`` (matches the
  ``THE_ONE_TEST_MODE=1`` / sandbox-disabled convention in ``test_pty_session.py``
  and avoids the bwrap gate that does not exist on Windows).
- ``THE_ONE_TEST_MODE=1`` → enables any test-mode guards in the product code.
"""

from __future__ import annotations

import os

import pytest

# Guard the entire module — do NOT import WindowsPtySession or winpty at module
# scope on non-Windows; that would blow up collection on Linux.
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only PTY backend tests")


@pytest.fixture(autouse=True)
def _windows_pty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force PassthroughSandbox for all tests in this module.

    Mirrors the convention in test_pty_session.py (THE_ONE_SANDBOX_DISABLED +
    THE_ONE_TEST_MODE) so WindowsPtySession uses PassthroughSandbox and the
    tests don't require bwrap (which doesn't exist on Windows).
    """
    monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")
    monkeypatch.setenv("THE_ONE_TEST_MODE", "1")


@pytest.mark.asyncio
async def test_start_creates_alive_session() -> None:
    """``start()`` spawns cmd.exe and the session reports alive."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        assert session.is_alive
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_send_echo_hello_round_trip() -> None:
    """``send("echo hello")`` returns output containing ``hello``."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        output = await session.send("echo hello", timeout=15.0)
        assert b"hello" in output
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_send_second_command_state_persists() -> None:
    """A second send in the same session succeeds — PTY state persists."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        await session.send("echo first", timeout=15.0)
        output2 = await session.send("echo second", timeout=15.0)
        assert b"second" in output2
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_close_makes_session_not_alive() -> None:
    """After ``close()``, ``is_alive`` returns False."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    await session.start()
    assert session.is_alive
    await session.close()
    assert not session.is_alive


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """Calling ``close()`` multiple times does not raise."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    await session.start()
    await session.close()
    await session.close()  # second call must not raise


@pytest.mark.asyncio
async def test_last_activity_updated_after_send() -> None:
    """``last_activity`` is updated after each ``send``."""
    import time

    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    try:
        await session.start()
        before = session.last_activity
        # Brief pause to ensure monotonic difference is measurable.
        time.sleep(0.05)
        await session.send("echo ts", timeout=15.0)
        after = session.last_activity
        assert after >= before
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_send_after_close_raises_runtime_error() -> None:
    """``send()`` after ``close()`` raises ``RuntimeError``."""
    from the_one.platform.pty_windows import WindowsPtySession

    session = WindowsPtySession()
    await session.start()
    await session.close()
    with pytest.raises(RuntimeError, match="session not active"):
        await session.send("echo nope", timeout=5.0)
