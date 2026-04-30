"""Platform abstraction layer.

Each helper is callable on Linux/WSL today; Windows and macOS support is a
future-mission concern but the contract is cross-platform from day one.

Public API:
    paths: canonicalize, safe_resolve, is_within
    shell: select_shell, run_shell
    interpreter: resolve_python, run_python
    tempdirs: temp_dir, user_home, user_config_dir
    pty: PtySession, UnixPtySession, create_pty_session (POSIX-only;
         importing on Windows raises NotImplementedError)
"""

from __future__ import annotations

import os

from the_one.platform.interpreter import resolve_python, run_python
from the_one.platform.paths import canonicalize, is_within, safe_resolve
from the_one.platform.shell import run_shell, select_shell
from the_one.platform.tempdirs import temp_dir, user_config_dir, user_home

__all__ = [
    "canonicalize",
    "is_within",
    "resolve_python",
    "run_python",
    "run_shell",
    "safe_resolve",
    "select_shell",
    "temp_dir",
    "user_config_dir",
    "user_home",
]

# PTY session surface — POSIX-only. Importing on Windows would raise at
# import time inside ``the_one.platform.pty``; guarding here keeps the
# package importable on Windows for non-PTY consumers (e.g. ``paths``,
# ``tempdirs``).
if os.name == "posix":
    from the_one.platform.pty import (  # noqa: E402
        PtySession,
        UnixPtySession,
        create_pty_session,
    )

    __all__ += ["PtySession", "UnixPtySession", "create_pty_session"]
