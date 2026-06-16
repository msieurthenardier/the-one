"""First-run close-to-tray notice helpers.

Persists a marker under ``settings.data_dir`` so the "app is still running in
the tray" notification is only shown on the *first* close-to-tray, not every
subsequent one.

The helpers are independent of ``shell.py`` so they can be unit-tested without
importing the GUI stack.
"""

from __future__ import annotations

from pathlib import Path

_MARKER_NAME = ".close_to_tray_notice_shown"


def _marker_path() -> Path:
    """Compute the marker path at call time (not at import time).

    Resolving ``settings.data_dir`` inside the function (same pattern as
    ``window_state._state_path()``) means that a test monkeypatching
    ``settings.data_dir`` is honoured without also patching this helper —
    a module-level attribute access would freeze the path at import.
    """
    from the_one.config import settings

    return settings.data_dir / _MARKER_NAME


def notice_shown() -> bool:
    """Return True if the close-to-tray notice has already been shown."""
    return _marker_path().exists()


def mark_notice_shown() -> None:
    """Persist the notice marker so future closes are silent.

    Creates ``settings.data_dir`` (and parents) if it does not yet exist —
    ``ensure_dirs()`` is called on the DB/agent path, not from ``run_desktop()``,
    so ``data_dir`` may not exist yet on a fresh install when the close button
    is first pressed.
    """
    path = _marker_path()
    # Must mkdir ourselves; do NOT assume data_dir already exists.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
