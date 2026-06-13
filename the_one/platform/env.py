"""Subprocess env-allowlist machinery — platform layer (F4 Decision 10).

Hosts the hardcoded eight-key allowlist and the ``_build_subprocess_env()``
helper that materializes only those keys from the current process environment
into a fresh dict. This is the env handed to every subprocess spawned by an
execution tool — strict allowlist, no inheritance of arbitrary parent env
(which could leak credentials, build secrets, or session tokens to the
agent's tool output).

Originally lived in ``the_one/tools/execution.py`` (F4 L2). Moved here in
F4 L5a so ``the_one/platform/pty.py`` can import it without creating a
``platform → tools`` reverse dependency. ``tools.execution`` now re-exports
both names for backward compatibility (existing tests reference
``from the_one.tools.execution import _ENV_ALLOWLIST, _build_subprocess_env``).

The eight allowlisted keys cover every legitimate need a build/test/REPL has:
PATH for binaries; HOME/USER/LOGNAME for tools that key on identity;
LANG/LC_ALL for locale-sensitive output; TERM for shell prompts; TZ for
timestamp-aware tools. Adding to this list is a code change, not a config
knob — keeps the trust surface small.

On Windows (``os.name == "nt"``) the ``_WINDOWS_ENV_ALLOWLIST`` is unioned in
by ``_build_subprocess_env`` in addition to the POSIX eight. These keys are
non-secret OS essentials that cmd.exe requires to function correctly:
- ``SystemRoot``: cmd.exe reads it to locate system32 (without it cmd.exe
  fails to start or misbehaves on basic internal commands).
- ``PATHEXT``: file-extension ordering for executable lookup (cmd.exe uses it
  to resolve plain ``python`` → ``python.exe``).
- ``COMSPEC``: path to cmd.exe itself (used by subprocesses that launch a
  shell).
- ``TEMP`` / ``TMP``: temporary directory (many tools write temp files).
- ``USERPROFILE``: user home directory (Windows equivalent of HOME).
- ``USERNAME``: the logged-in user name (Windows equivalent of USER).

``_ENV_ALLOWLIST`` is NOT modified — ``test_execution_helpers.py:273``
(``test_eight_allowlist_keys_canonical_set``) pins it to the exact 8-key POSIX
tuple. The Windows additions are separate and unioned only on Windows.
"""

from __future__ import annotations

import os

# F4 Decision 10: hardcoded subprocess env allowlist. Eight keys; not
# operator-configurable. See module docstring.
# IMPORTANT: do NOT add Windows keys here — test_execution_helpers.py:273
# pins this to exactly the 8-key POSIX tuple. Windows additions live in
# _WINDOWS_ENV_ALLOWLIST below.
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "TERM",
    "TZ",
)

# Windows-only additions — unioned into _build_subprocess_env only on nt.
# cmd.exe requires these non-secret OS essentials to function correctly.
# See module docstring for why each key is needed.
_WINDOWS_ENV_ALLOWLIST: tuple[str, ...] = (
    "SystemRoot",
    "PATHEXT",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "USERNAME",
)


def _build_subprocess_env() -> dict[str, str]:
    """Return a dict containing only the ``_ENV_ALLOWLIST`` keys present
    in the current process environment. On Windows, also includes the
    ``_WINDOWS_ENV_ALLOWLIST`` keys. Missing keys are silently dropped —
    never raises ``KeyError``.

    F4 Decision 10: the allowlisted keys are hardcoded; not
    operator-configurable. This is the env handed to every subprocess
    spawned by an execution tool — strict allowlist, no inheritance of
    arbitrary parent env (which could leak credentials, build secrets,
    or session tokens to the agent's tool output).

    On Windows (``os.name == "nt"``), the union of ``_ENV_ALLOWLIST`` and
    ``_WINDOWS_ENV_ALLOWLIST`` is used so that cmd.exe receives the OS
    essentials it needs (``SystemRoot``, ``PATHEXT``, etc.). The POSIX path
    returns exactly today's result — ``_ENV_ALLOWLIST`` unchanged.
    """
    allowlist = _ENV_ALLOWLIST
    if os.name == "nt":
        allowlist = _ENV_ALLOWLIST + _WINDOWS_ENV_ALLOWLIST
    return {k: os.environ[k] for k in allowlist if k in os.environ}
