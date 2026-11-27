"""The browser fixtures' app-spawn ready timeout (squawk 0438).

Kept apart from ``conftest.py`` so the unit tier can pin the default and the
parse without importing Playwright or spawning anything.

Under a loaded host (full gate, ``--parallel 3``) the per-test uvicorn
subprocess can take longer than 15 s to answer ``/api/live``. The wait already
raises at once when the subprocess exits, so a longer timeout costs time only
when the app is genuinely slow to start.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

APP_READY_TIMEOUT_ENV = "THE_ONE_TEST_APP_READY_TIMEOUT"
DEFAULT_APP_READY_TIMEOUT = 45.0


def app_ready_timeout(env: Mapping[str, str] | None = None) -> float:
    """Return the spawn-ready timeout in seconds.

    ``THE_ONE_TEST_APP_READY_TIMEOUT`` overrides the default. An empty value
    means unset. A value that is not a finite number above zero raises
    ``ValueError`` naming the variable; it never falls back silently.
    """
    source = os.environ if env is None else env
    raw = source.get(APP_READY_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_APP_READY_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not (0 < value < float("inf")):
        raise ValueError(
            f"{APP_READY_TIMEOUT_ENV}={raw!r} is not a positive number of seconds "
            f"(default {DEFAULT_APP_READY_TIMEOUT:g})"
        )
    return value
