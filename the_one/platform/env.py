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
"""

from __future__ import annotations

import os

# F4 Decision 10: hardcoded subprocess env allowlist. Eight keys; not
# operator-configurable. See module docstring.
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


def _build_subprocess_env() -> dict[str, str]:
    """Return a dict containing only the ``_ENV_ALLOWLIST`` keys present
    in the current process environment. Missing keys are silently
    dropped — never raises ``KeyError``.

    F4 Decision 10: the eight allowlisted keys are hardcoded; not
    operator-configurable. This is the env handed to every subprocess
    spawned by an execution tool — strict allowlist, no inheritance of
    arbitrary parent env (which could leak credentials, build secrets,
    or session tokens to the agent's tool output).
    """
    return {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
