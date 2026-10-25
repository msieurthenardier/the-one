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
import os
import sys
from pathlib import Path

from the_one.platform.env import ensure_stdio_streams

ensure_stdio_streams()

from the_one.main import cli_entry  # noqa: E402 (must come after the stdio fix)

# A Finder or Dock launch has nowhere for stdout/stderr to go, so the `app` command logs to
# ~/Library/Logs/<bundle name>/app.log (Mission 32 Flight 3 leg 6). The folder name is the
# bundle name in packaging/product.toml (a test pins it).
LOG_DIR_NAME = "GleepGlorp AI"
LOG_FILE_NAME = "app.log"
LOG_MAX_BYTES = 10 * 1024 * 1024


def app_log_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "Logs" / LOG_DIR_NAME / LOG_FILE_NAME


def redirect_app_log(args, stderr=None, home=None, max_bytes=LOG_MAX_BYTES):
    """Open the app log for an ``app`` launch that has no terminal; else return None.

    Append mode, line-buffered; a log already over ``max_bytes`` is truncated at start. Any
    failure returns None and the caller keeps its current streams. This only opens the file;
    ``_install_log`` points the process at it.
    """
    if not args or args[0] != "app":
        return None
    stream = sys.stderr if stderr is None else stderr
    try:
        if stream is not None and stream.isatty():
            return None
    except (OSError, ValueError, AttributeError):
        pass  # a closed or odd stream is not a terminal
    try:
        path = app_log_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if path.exists() and path.stat().st_size > max_bytes else "a"
        return open(path, mode, buffering=1, encoding="utf-8")  # noqa: SIM115
    except OSError:
        return None


def _install_log(log) -> None:
    """Send fds 1 and 2 (native and child output) and sys.stdout/stderr to ``log``."""
    try:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    except OSError:
        pass
    sys.stdout = sys.stderr = log


def launch_args(argv: list[str]) -> list[str]:
    """The CLI arguments for a launch: Finder's ``-psn_*`` dropped, bare launch means ``app``."""
    # Finder adds -psn_* on older macOS; it is not a subcommand.
    args = [a for a in argv if not a.startswith("-psn_")]
    return args or ["app"]  # a bare double-click opens the window


if __name__ == "__main__":
    # Spawned multiprocessing children re-execute the bundle executable; this runs first so
    # they take the child bootstrap instead of re-running cli_entry (the fork-bomb guard).
    multiprocessing.freeze_support()
    _args = launch_args(sys.argv[1:])
    _log = redirect_app_log(_args)
    if _log is not None:
        _install_log(_log)
    sys.argv = [sys.argv[0], *_args]
    cli_entry()
