"""Sandbox backend selection factory (F3 §DD2).

``get_sandbox_backend()`` selects and returns the appropriate ``ToolSandbox``
backend for the current runtime environment.  Selection order (first match wins):

1. Double-flag test bypass (``THE_ONE_SANDBOX_DISABLED=1`` AND
   ``THE_ONE_TEST_MODE=1``) — ``PassthroughSandbox`` (highest priority).
2. Non-Linux host (``sys.platform != "linux"``) — ``PassthroughSandbox``.
3. ``bwrap`` absent from PATH — ``PassthroughSandbox`` (WARNING: enforcement
   expected but not available on a Linux host).
4. ``bwrap`` present but unprivileged user namespaces unavailable
   (``_userns_available()`` → ``"unavailable"``) — ``PassthroughSandbox``
   (WARNING: user namespaces unavailable; key ``passthrough:userns-unavailable``).
5. ``bwrap`` present but userns probe errored (``_userns_available()`` →
   ``"error"``) — ``PassthroughSandbox`` (ERROR: probe broken; key
   ``passthrough:userns-probe-error``).
6. Otherwise — ``BubblewrapSandbox`` (Linux + bwrap present + userns ok + no
   bypass).

The factory logs the selection **once per process** (not per call).  Repeated
calls do NOT re-log.  Level: WARNING for the Linux-bwrap-missing and
userns-unavailable cases; ERROR for the userns-probe-error case; INFO for all
other cases (expected outcome).

DD3 locus note: the one-time unsandboxed WARNING lives here in the factory (not
inside ``PassthroughSandbox.prepare_spawn`` as DD3 literally phrases it).  The
factory is the single selection locus and knows the *reason* (non-Linux vs
bwrap-missing vs test-bypass) which determines WARNING vs INFO.  This avoids
per-instance global state on the backend class.  Observably equivalent to DD3.

The selection is re-evaluated on every call (NOT memoized) — tests monkeypatch
``sys.platform``, ``shutil.which``, and the env vars between calls and must see
fresh results.  Only the *log emission* is deduped via the module-level guard.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import ToolSandbox

_logger = logging.getLogger(__name__)

# Module-level log-once guard: set of "backend_name:reason" strings that have
# already been logged.  Persists across calls for the lifetime of the process.
# Tests reset this via ``_reset_selection_log_state()`` in a fixture.
_LOGGED: set[str] = set()

# Module-level cache for the userns probe result.  ``None`` means the probe
# has not been run yet.  The cache is reset together with _LOGGED by
# ``_reset_selection_log_state()`` so the autouse fixture in
# ``tests/test_sandbox_factory.py`` covers both automatically.
_USERNS_PROBE: Literal["ok", "unavailable", "error"] | None = None


def _reset_selection_log_state() -> None:
    """Clear the log-once guard and the userns probe cache — for tests only.

    Call in a fixture (autouse or per-test) so each test can assert that the
    selection log fires exactly once rather than inheriting state from earlier
    tests in the same process.  The probe cache is reset here so stale results
    cannot bleed across tests that stub ``_userns_available``.
    """
    global _USERNS_PROBE
    _LOGGED.clear()
    _USERNS_PROBE = None


def _userns_available() -> Literal["ok", "unavailable", "error"]:
    """Probe whether unprivileged user namespaces are usable on this host.

    Returns one of three string literals:
    * ``"ok"``          — userns work; bwrap containment is viable.
    * ``"unavailable"`` — userns definitively absent/disabled.
    * ``"error"``       — probe mechanism failed; cannot determine capability.

    Result is cached in ``_USERNS_PROBE`` after the first real evaluation so the
    ``bwrap`` probe subprocess runs at most once per process.  The cache is reset
    by ``_reset_selection_log_state()`` (for test isolation).

    Fast-path: if ``/proc/sys/kernel/unprivileged_userns_clone`` exists **and**
    reads ``"0"``, return ``"unavailable"`` immediately (definitive kernel knob).
    If the file is absent (WSL2 case) or reads any other value, fall through to
    the empirical probe — absent MUST NOT be treated as negative.

    Empirical probe: spawn ``bwrap --unshare-user --ro-bind / / /usr/bin/true``
    with a 5-second timeout.  ``returncode == 0`` → ``"ok"``; any nonzero code
    → ``"unavailable"``.  ``OSError``, ``TimeoutExpired``, or other
    ``SubprocessError`` → ``"error"``.
    """
    global _USERNS_PROBE
    if _USERNS_PROBE is not None:
        return _USERNS_PROBE

    # Fast-path: check the procfs knob only when it exists and reads "0".
    _knob = "/proc/sys/kernel/unprivileged_userns_clone"
    try:
        # Linux-only procfs knob (ASCII); explicit encoding unnecessary, left
        # as-is — revisit at F7 (M15 F5 L1 encoding audit, DD4).
        with open(_knob) as _f:
            _val = _f.read().strip()
        if _val == "0":
            _USERNS_PROBE = "unavailable"
            return _USERNS_PROBE
        # Any other value (e.g. "1"): fall through to the empirical probe.
    except OSError:
        # File absent (WSL2) or unreadable — fall through to empirical probe.
        pass

    # Empirical probe: attempt the real operation.
    _logger.debug("userns probe: running bwrap --unshare-user empirical check")
    try:
        result = subprocess.run(
            ["bwrap", "--unshare-user", "--ro-bind", "/", "/", "/usr/bin/true"],
            capture_output=True,
            timeout=5,
        )
        _logger.debug("userns probe: bwrap returncode=%d", result.returncode)
        _USERNS_PROBE = "ok" if result.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        _USERNS_PROBE = "error"

    return _USERNS_PROBE


def _sandbox_disabled_for_tests() -> bool:
    """Return True when both test double-flags are set (reads env at call time).

    The ``the_one.mcp.transports.stdio`` module keeps its own copy of this
    predicate. The duplication is intentional — both modules may need to gate
    on the double-flag independently without pulling in the other's imports.
    """
    return (
        os.environ.get("THE_ONE_SANDBOX_DISABLED") == "1"
        and os.environ.get("THE_ONE_TEST_MODE") == "1"
    )


def _select() -> tuple[str, str]:
    """Return ``(backend_name, key)`` for the current host (first match wins).

    The one selection order shared by ``get_sandbox_backend`` and
    ``describe_selection``.  ``backend_name`` is ``"passthrough"`` or
    ``"bubblewrap"``; ``key`` is the log-once key.  Logs nothing.
    """
    if _sandbox_disabled_for_tests():
        return "passthrough", "passthrough:test-bypass"
    if sys.platform != "linux":
        return "passthrough", f"passthrough:non-linux:{sys.platform}"
    if shutil.which("bwrap") is None:
        return "passthrough", "passthrough:bwrap-missing"
    probe = _userns_available()
    if probe == "unavailable":
        return "passthrough", "passthrough:userns-unavailable"
    if probe == "error":
        return "passthrough", "passthrough:userns-probe-error"
    return "bubblewrap", "bubblewrap:linux"


def describe_selection() -> tuple[str, str]:
    """Return ``(backend_name, reason)`` without logging or instantiating.

    Uses exactly ``get_sandbox_backend()``'s order (via ``_select``) and the
    cached userns probe.  ``reason`` is "" for bubblewrap.
    """
    name, key = _select()
    if key == "passthrough:test-bypass":
        return name, "test bypass"
    if key.startswith("passthrough:non-linux"):
        return name, f"non-Linux host ({sys.platform})"
    if key == "passthrough:bwrap-missing":
        return name, "bubblewrap not installed"
    if key == "passthrough:userns-unavailable":
        return name, "user namespaces unavailable"
    if key == "passthrough:userns-probe-error":
        return name, "user namespace probe failed"
    return name, ""


def get_sandbox_backend() -> "ToolSandbox":
    """Select and return the appropriate ToolSandbox backend.

    Re-evaluates on every call (not memoized) so monkeypatching in tests is
    always visible.  Only the log emission is deduped (once per process per
    unique backend+reason combination).

    Returns a ``PassthroughSandbox`` or ``BubblewrapSandbox`` instance.  Both
    structurally satisfy the ``ToolSandbox`` Protocol.
    """
    # Import here to avoid circular imports at module load time; these are
    # lightweight dataclass/class imports so the cost is negligible.
    from the_one.platform.sandbox.bubblewrap import BubblewrapSandbox
    from the_one.platform.sandbox.passthrough import PassthroughSandbox

    # --- Selection (first match wins; shared with describe_selection) ---
    name, key = _select()

    if key == "passthrough:test-bypass":
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.info(
                "sandbox backend: passthrough (test-bypass) — "
                "tool spawns are NOT sandboxed (THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1)"
            )
        return PassthroughSandbox()

    if key.startswith("passthrough:non-linux"):
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.info(
                "sandbox backend: passthrough (non-linux: %s) — tool spawns are NOT sandboxed",
                sys.platform,
            )
        return PassthroughSandbox()

    if key == "passthrough:bwrap-missing":
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.warning(
                "sandbox backend: passthrough (bwrap missing on Linux) — "
                "tool spawns are NOT sandboxed; install bubblewrap: apt-get install bubblewrap"
            )
        return PassthroughSandbox()

    if key == "passthrough:userns-unavailable":
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.warning(
                "sandbox backend: passthrough (user namespaces unavailable on Linux) — "
                "tool spawns are NOT sandboxed; enable unprivileged userns "
                "(e.g. sysctl kernel.unprivileged_userns_clone=1 on kernels that expose it)"
            )
        return PassthroughSandbox()
    if key == "passthrough:userns-probe-error":
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.error(
                "sandbox backend: passthrough (userns probe errored) — "
                "cannot determine sandbox capability; degrading to passthrough "
                "(tool spawns NOT sandboxed); investigate the probe environment"
            )
        return PassthroughSandbox()

    # Linux + bwrap present + userns ok + no test bypass → bubblewrap
    if key not in _LOGGED:
        _LOGGED.add(key)
        _logger.info("sandbox backend: bubblewrap — tool spawns are sandboxed")
    return BubblewrapSandbox()
