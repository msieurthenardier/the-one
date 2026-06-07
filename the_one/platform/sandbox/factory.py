"""Sandbox backend selection factory (F3 §DD2).

``get_sandbox_backend()`` selects and returns the appropriate ``ToolSandbox``
backend for the current runtime environment.  Selection order (first match wins):

1. Double-flag test bypass (``THE_ONE_SANDBOX_DISABLED=1`` AND
   ``THE_ONE_TEST_MODE=1``) — ``PassthroughSandbox`` (highest priority).
2. Non-Linux host (``sys.platform != "linux"``) — ``PassthroughSandbox``.
3. ``bwrap`` absent from PATH — ``PassthroughSandbox`` (WARNING: enforcement
   expected but not available on a Linux host).
4. Otherwise — ``BubblewrapSandbox`` (Linux + bwrap present + no bypass).

The factory logs the selection **once per process** (not per call).  Repeated
calls do NOT re-log.  Level: WARNING for the Linux-bwrap-missing case
(enforcement expected but absent); INFO for all other cases (expected outcome).

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
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import ToolSandbox

_logger = logging.getLogger(__name__)

# Module-level log-once guard: set of "backend_name:reason" strings that have
# already been logged.  Persists across calls for the lifetime of the process.
# Tests reset this via ``_reset_selection_log_state()`` in a fixture.
_LOGGED: set[str] = set()


def _reset_selection_log_state() -> None:
    """Clear the log-once guard — for tests only.

    Call in a fixture (autouse or per-test) so each test can assert that the
    selection log fires exactly once rather than inheriting state from earlier
    tests in the same process.
    """
    _LOGGED.clear()


def _sandbox_disabled_for_tests() -> bool:
    """Return True when both test double-flags are set (reads env at call time).

    The ``the_one.mcp.transports.stdio`` module keeps its own copy of this
    predicate intentionally — relocating it would require inverting the
    ``SandboxError`` / ``MCPClientError`` import-cycle (DD1, deferred to
    end-of-mission maintenance).  The duplication is a deliberate workaround,
    not pending reconciliation.
    """
    return (
        os.environ.get("THE_ONE_SANDBOX_DISABLED") == "1"
        and os.environ.get("THE_ONE_TEST_MODE") == "1"
    )


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

    # --- Selection (first match wins) ---

    if _sandbox_disabled_for_tests():
        key = "passthrough:test-bypass"
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.info(
                "sandbox backend: passthrough (test-bypass) — "
                "tool spawns are NOT sandboxed (THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1)"
            )
        return PassthroughSandbox()

    if sys.platform != "linux":
        key = f"passthrough:non-linux:{sys.platform}"
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.info(
                "sandbox backend: passthrough (non-linux: %s) — tool spawns are NOT sandboxed",
                sys.platform,
            )
        return PassthroughSandbox()

    if shutil.which("bwrap") is None:
        key = "passthrough:bwrap-missing"
        if key not in _LOGGED:
            _LOGGED.add(key)
            _logger.warning(
                "sandbox backend: passthrough (bwrap missing on Linux) — "
                "tool spawns are NOT sandboxed; install bubblewrap: apt-get install bubblewrap"
            )
        return PassthroughSandbox()

    # Linux + bwrap present + no test bypass → bubblewrap
    key = "bubblewrap:linux"
    if key not in _LOGGED:
        _LOGGED.add(key)
        _logger.info("sandbox backend: bubblewrap — tool spawns are sandboxed")
    return BubblewrapSandbox()
