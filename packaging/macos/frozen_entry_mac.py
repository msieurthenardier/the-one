"""Frozen entry point for the macOS PyInstaller bundle (Mission 32 Flight 1, candidate A).

Spike prototype, build artifact: PyInstaller's ``Analysis`` ingests it; the running app
never imports it. Recipe upkeep, not an app patch (DD4).

One executable has to serve two callers:

* a shell: ``GleepGlorp AI.app/Contents/MacOS/the-one doctor|serve|version|...`` must run the
  CLI exactly as the Linux and Windows console builds do;
* Finder / Dock / ``open``: they launch the bundle's main executable with NO arguments
  (or only a ``-psn_<n>_<n>`` process-serial-number argument on older macOS), and the
  bare ``the-one`` command would start the terminal ``chat``. For that launch ``app``
  (the native window) is appended, as ``../windows/frozen_entry_gui.py`` forces it on Windows.

``ensure_stdio_streams()`` first: a windowed (``console=False``) bundle can have
``sys.stdout``/``sys.stderr`` set to None, and uvicorn calls ``sys.stdout.isatty()`` at config time.
"""

from __future__ import annotations

import multiprocessing
import sys

from the_one.platform.env import ensure_stdio_streams

ensure_stdio_streams()

from the_one.main import cli_entry  # noqa: E402 (must come after the stdio fix)

if __name__ == "__main__":
    # Spawned multiprocessing children re-execute the bundle executable; this runs first so
    # they take the child bootstrap instead of re-running cli_entry (the fork-bomb guard).
    multiprocessing.freeze_support()
    # Finder adds -psn_* on older macOS; it is not a subcommand.
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]
    if not args:
        args = ["app"]  # a bare double-click opens the window
    sys.argv = [sys.argv[0], *args]
    cli_entry()
