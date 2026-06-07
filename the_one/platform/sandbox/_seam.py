"""Internal seam helpers for sandbox-aware platform callers.

Not part of the public sandbox API; imported only by
``platform/shell.py``, ``platform/interpreter.py``, and ``platform/pty.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from the_one.platform.sandbox.base import SandboxProfile, ToolSandbox

_logger = logging.getLogger(__name__)


def warn_if_isolation_unenforced(
    profile: "SandboxProfile",
    backend: "ToolSandbox",
) -> None:
    """Emit a single WARNING when boxed isolation is requested but cannot be enforced.

    Fires when ``profile.minimal_rootfs`` is True AND the resolved backend is
    not the bubblewrap backend (``backend.name != "bubblewrap"``).  Silently
    returns on the bubblewrap path (enforcement present) or when
    ``minimal_rootfs`` is False (boxed mode not requested).

    Per DD5/DD6: the passthrough backend silently accepts and drops the field;
    only the seam (the caller of ``prepare_spawn``) warns — not the backend
    itself and not the factory.
    """
    if getattr(profile, "minimal_rootfs", False) and backend.name != "bubblewrap":
        _logger.warning(
            "boxed execution requested but isolation is not enforced on this backend "
            "(backend=%r does not support minimal_rootfs); "
            "the spawn will run unisolated",
            backend.name,
        )
