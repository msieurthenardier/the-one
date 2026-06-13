"""Platform-neutral PTY dispatch tests (M15 F3 Leg 1).

This file is NOT skipped on Windows — it is the authoritative
import-success assertion on the ``windows-2022`` CI lane (DD7).

Tests:

* ``test_module_imports_on_current_platform`` — ``the_one.platform.pty``
  and ``the_one.platform`` import without error on every OS (the Leg 1
  contract: module imports on Windows; PTY working on Windows is Leg 2).

* ``test_dispatch_posix`` (POSIX-only) — ``create_pty_session()`` returns
  a ``UnixPtySession`` instance.

* ``test_dispatch_windows_pending_leg2`` (Windows-only) —
  ``create_pty_session()`` raises ``NotImplementedError`` mentioning Leg 2.
  NOTE: Leg 2 INVERTS this assertion — it will flip from ``raises`` to
  ``returns WindowsPtySession``.  Do not mistake this for a broken test on
  the Windows CI inventory; it is the intentional Leg 1 stub.
"""

from __future__ import annotations

import os

import pytest


def test_module_imports_on_current_platform() -> None:
    """``the_one.platform.pty`` and ``the_one.platform`` import without error.

    Runs on every OS — this is the Leg 1 cascade-unblock contract (DD6).
    On the ``windows-2022`` CI lane this is the real Windows import-success
    assertion (DD7).
    """
    import importlib

    # Fresh import (module may already be in sys.modules from other tests;
    # use importlib.import_module which returns the cached copy — that is
    # sufficient: the goal is that collection-time import never raised).
    mod = importlib.import_module("the_one.platform.pty")
    assert mod is not None

    platform_mod = importlib.import_module("the_one.platform")
    assert platform_mod is not None


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only dispatch path")
def test_dispatch_posix() -> None:
    """On POSIX, ``create_pty_session()`` returns a ``UnixPtySession``."""
    from the_one.platform.pty import create_pty_session
    from the_one.platform.pty_unix import UnixPtySession

    session = create_pty_session()
    assert isinstance(session, UnixPtySession)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only dispatch path")
def test_dispatch_windows_pending_leg2() -> None:
    """On Windows, ``create_pty_session()`` raises ``NotImplementedError``
    mentioning Leg 2.

    NOTE: Leg 2 INVERTS this assertion — it will flip from ``raises`` to
    ``returns WindowsPtySession``.  This test will be replaced/removed in
    Leg 2.  Do not mistake this expected failure for a broken test when
    reading the Leg 1 Windows CI failure inventory (DD10).
    """
    from the_one.platform.pty import create_pty_session

    with pytest.raises(NotImplementedError, match="Leg 2"):
        create_pty_session()
