from __future__ import annotations

# Back-compat shim. The desktop launcher moved to the_one.interfaces.desktop.shell
# (M15 F6 DD1 — single composable desktop module); M32 F3 DD1 split it again,
# so `_select_port` now comes from `desktop.takeover`. These re-exports keep existing
# imports working: main.py's `app` dispatch and the CI packaged-smoke's
# `from the_one.interfaces.app import _select_port`.
from the_one.interfaces.desktop.shell import (  # noqa: F401
    _graceful_shutdown,
    _wait_until_serving,
    _webview_available,
)
from the_one.interfaces.desktop.shell import (
    run_desktop as run,
)
from the_one.interfaces.desktop.takeover import _select_port  # noqa: F401

__all__ = [
    "run",
    "_select_port",
    "_webview_available",
    "_wait_until_serving",
    "_graceful_shutdown",
]
