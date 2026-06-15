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
import sys
from pathlib import Path

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


# ---------------------------------------------------------------------------
# M15 F5 L1 — frozen-runtime seam (DD2/DD3).
#
# When the app is frozen (PyInstaller), the GUI launch has a stripped PATH and
# PyInstaller prepends the bundle dir (``_MEIPASS`` / the exe's directory) to the
# child's PATH. That bundle dir contains the app's own bundled libs, not the
# real ``node``/``uv``/``python`` runtimes the agent needs to spawn. The seam
# below (a) strips the bundle dir from the front of the child PATH and (b)
# augments PATH with common runtime install locations plus an operator override.
#
# Crucially, the env handed to children is built from a hardcoded allowlist (see
# ``_build_subprocess_env``), so PyInstaller's loader-path leakage
# (``LD_LIBRARY_PATH`` / ``DYLD_*`` / their ``*_ORIG`` stashes) never reaches a
# child — those keys are not in the allowlist. The only allowlisted key
# PyInstaller mutates is ``PATH``, so the fix is narrow. No restore-``*_ORIG``
# machinery is added (it would be dead code); the allowlist invariant is asserted
# by a unit test instead.
# ---------------------------------------------------------------------------

# Operator override env vars (DECIDED: read from raw ``os.environ``, not
# ``Settings`` — keeps ``platform`` free of a ``platform → config`` import cycle).
# Intentionally plumbing-level, sharing only the ``THE_ONE_`` prefix convention.
_EXTRA_PATH_ENV = "THE_ONE_EXTRA_PATH"


def is_frozen() -> bool:
    """True when running inside a PyInstaller (or similar) frozen bundle.

    Import-cheap — called on every subprocess spawn. ``sys.frozen`` is set by
    PyInstaller (and most freezers); ``sys._MEIPASS`` is the bundle directory it
    injects. Either being present means we're frozen.
    """
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def _bundle_dir() -> str | None:
    """Return the frozen bundle directory, or ``None`` when not frozen.

    Handles both PyInstaller layouts: ``sys._MEIPASS`` is set in one-file
    (a temp extraction dir) and one-dir (the install dir) modes. When ``_MEIPASS``
    is absent but the app is otherwise frozen, fall back to the executable's
    parent directory (the one-dir bundle root). DD1 commits to one-dir.
    """
    if not is_frozen():
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return str(meipass)
    return str(Path(sys.executable).resolve().parent)


def _common_runtime_dirs() -> list[str]:
    """Platform-appropriate directories where node/uv/python commonly install.

    Returned in the order they should be appended to PATH. Existence is not
    checked here (cheap, and a non-existent dir on PATH is harmless); de-dup and
    ordering are handled by the caller.
    """
    home = Path.home()
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        localappdata = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        return [
            str(Path(program_files) / "nodejs"),
            str(Path(appdata) / "npm"),
            # uv installs to %LOCALAPPDATA%\Programs\uv or ~/.local/bin.
            str(Path(localappdata) / "Programs" / "uv"),
            str(home / ".local" / "bin"),
            str(home / ".cargo" / "bin"),
        ]
    # POSIX (Linux, macOS, WSL).
    return [
        "/usr/local/bin",
        "/opt/homebrew/bin",  # Apple Silicon Homebrew
        str(home / ".local" / "bin"),
        str(home / ".cargo" / "bin"),  # uv default install location
        str(home / ".npm-global" / "bin"),
    ]


def strip_bundle_dir_from_path(env: dict[str, str]) -> dict[str, str]:
    """Remove the frozen bundle directory from the front of ``env["PATH"]``.

    Returns a fresh dict (input is not mutated). When not frozen, or when there
    is no ``PATH``, the input is returned unchanged (as a copy). This is the
    *strip-always-wins* half of the seam: it is re-applied at the MCP caller
    after ``build_stdio_environ`` so an operator-supplied ``PATH`` can never
    re-introduce the bundle dir. Augmentation (the runtime-dir append) is NOT
    applied here — that yields to an explicit operator ``PATH``.
    """
    bundle = _bundle_dir()
    path = env.get("PATH", "")
    if bundle is None or not path:
        return dict(env)

    bundle_norm = os.path.normcase(os.path.normpath(bundle))
    entries = path.split(os.pathsep)
    kept: list[str] = []
    for entry in entries:
        if not entry:
            continue
        if os.path.normcase(os.path.normpath(entry)) == bundle_norm:
            continue  # drop the bundle dir wherever it appears
        kept.append(entry)

    result = dict(env)
    result["PATH"] = os.pathsep.join(kept)
    return result


def clean_subprocess_env(env: dict[str, str]) -> dict[str, str]:
    """Sanitize the PATH of an already-allowlisted child env for the frozen seam.

    Operates on the dict produced by the allowlist filter. When **not** frozen,
    returns the input unchanged (cheap fast-path) — PATH is effectively
    untouched. When **frozen**:

    1. Strip the bundle directory from the front of PATH (``strip_bundle_dir_from_path``).
    2. Augment PATH with common runtime install locations plus an operator
       override (``THE_ONE_EXTRA_PATH``, read from raw ``os.environ``).

    The operator override is appended last among the augmentation entries so an
    operator can extend — but the existing (stripped) PATH entries keep priority
    over the appended defaults. De-dups while preserving order.
    """
    if not is_frozen():
        return env

    stripped = strip_bundle_dir_from_path(env)
    existing = [p for p in stripped.get("PATH", "").split(os.pathsep) if p]

    augment = list(_common_runtime_dirs())
    extra = os.environ.get(_EXTRA_PATH_ENV, "")
    if extra:
        augment.extend(p for p in extra.split(os.pathsep) if p)

    seen: set[str] = set()
    ordered: list[str] = []
    for entry in [*existing, *augment]:
        key = os.path.normcase(os.path.normpath(entry))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(entry)

    result = dict(stripped)
    result["PATH"] = os.pathsep.join(ordered)
    return result


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

    M15 F5 L1: the result is passed through ``clean_subprocess_env`` so every
    spawn path (MCP stdio, shell, python-exec, PTY) inherits the frozen-runtime
    PATH sanitization without per-call-site changes. When not frozen this is a
    no-op (PATH unchanged), preserving today's behavior exactly.
    """
    allowlist = _ENV_ALLOWLIST
    if os.name == "nt":
        allowlist = _ENV_ALLOWLIST + _WINDOWS_ENV_ALLOWLIST
    return clean_subprocess_env({k: os.environ[k] for k in allowlist if k in os.environ})
