"""Temp-dir and user-dir helpers — cross-platform contract.

Forward-looking module: no current ``the_one/tools/*.py`` calls
``tempfile.gettempdir()`` or ``Path.home()``. F3-F5 will consume these helpers
(e.g., default path-scope allowlist may resolve via ``user_home()``). Building
this now keeps the platform package complete and avoids a follow-up scaffold.

Helpers:
    temp_dir() — wraps ``tempfile.gettempdir()`` as a ``Path``.
    user_home() — wraps ``Path.home()``.
    user_config_dir(app) — cross-platform user-config path:
        POSIX:   ``~/.{app}``
        Windows: ``%APPDATA%\\{app}`` (falls back to ``~/{app}`` when
                 ``APPDATA`` is unset or empty).

All helpers return paths *without* creating them — matching the non-creating
semantics of ``tempfile.gettempdir`` and ``Path.home``. Caller creates the
directory if needed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def temp_dir() -> Path:
    """Return the system temp directory as a ``Path``."""
    return Path(tempfile.gettempdir())


def user_home() -> Path:
    """Return the current user's home directory as a ``Path``."""
    return Path.home()


def user_config_dir(app: str) -> Path:
    """Return the user-config directory for ``app`` (path NOT created).

    POSIX: ``~/.{app}``.
    Windows: ``%APPDATA%/{app}`` if ``APPDATA`` is set and non-empty,
    otherwise ``~/{app}`` as a fallback.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / app
    return Path.home() / f".{app}"
