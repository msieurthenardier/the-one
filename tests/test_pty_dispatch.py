"""Platform-neutral PTY dispatch tests (M15 F3 Legs 1-2).

This file is NOT skipped on Windows — it is the authoritative
import-success assertion on the ``windows-2022`` CI lane (DD7).

Tests:

* ``test_module_imports_on_current_platform`` — ``the_one.platform.pty``
  and ``the_one.platform`` import without error on every OS (the Leg 1
  contract: module imports on Windows; PTY working on Windows is Leg 2).

* ``test_dispatch_posix`` (POSIX-only) — ``create_pty_session()`` returns
  a ``UnixPtySession`` instance.

* ``test_dispatch_windows`` (Windows-only) —
  ``create_pty_session()`` returns a ``WindowsPtySession`` instance.
  (Leg 2: inverted from Leg 1's ``raises NotImplementedError`` stub.)
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
def test_dispatch_windows() -> None:
    """On Windows, ``create_pty_session()`` returns a ``WindowsPtySession``.

    Leg 2 inverted this from the Leg 1 stub (which asserted
    ``NotImplementedError``).  The authoritative backend verification is
    ``tests/test_pty_windows.py`` (cmd.exe round-trip on the windows-2022
    CI lane).
    """
    from the_one.platform.pty import create_pty_session
    from the_one.platform.pty_windows import WindowsPtySession

    session = create_pty_session()
    assert isinstance(session, WindowsPtySession)
