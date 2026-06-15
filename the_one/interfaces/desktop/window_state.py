"""Window geometry persistence — save/restore size and position across launches.

Saves to ``data_dir / "window-state.json"`` (platformdirs per-user store).
No GUI imports at module top level — importable headless (for tests, etc.).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _state_path() -> Path:
    """Compute the window-state file path at call time (not at import time).

    Using a helper function rather than a module-level constant means that
    ``monkeypatch.setattr(settings, "data_dir", tmp_path)`` in tests is
    honoured — a module-level assignment would freeze the path at import.
    """
    from the_one.config import settings

    return settings.data_dir / "window-state.json"


def load_state() -> dict[str, Any] | None:
    """Read the saved window geometry from disk.

    Returns a dict with at least ``width`` and ``height`` keys (and optionally
    ``x`` and ``y``) on success, or ``None`` when:
    - the file does not exist (first run), or
    - the file is unreadable / malformed JSON (logged at WARNING).
    Never raises.
    """
    path = _state_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("window_state: could not read %s: %s", path, exc)
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("window_state: corrupt JSON in %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        log.warning("window_state: unexpected format in %s (not a dict)", path)
        return None

    return data


def save_state(width: int, height: int, x: int | None = None, y: int | None = None) -> None:
    """Persist window geometry to disk.

    Creates ``data_dir`` (and parents) if needed.  Best-effort: exceptions
    are logged at WARNING and never propagated (so a failed save never blocks
    the window close).
    """
    from the_one.config import settings

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {"width": width, "height": height}
        if x is not None:
            state["x"] = x
        if y is not None:
            state["y"] = y
        _state_path().write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:
        log.warning("window_state: could not save state: %s", exc)


def clamp_to_bounds(state: dict[str, Any], screens: list[Any]) -> dict[str, Any]:
    """Clamp a saved geometry dict so the window is fully on-screen.

    ``screens`` is a list of pywebview ``Screen`` objects, each with integer
    attributes ``x``, ``y``, ``width``, ``height``.  If the list is empty or
    any screen attribute is unavailable, return ``state`` unchanged.

    Clamping order (critical):
    1. Clamp *width/height* to the union dimensions first — a window wider
       than the combined screen area would push the right-clamp bound negative,
       making the subsequent top-left clamp nonsensical.
    2. Clamp the *top-left* origin into
       ``[union_x_min, union_x_max - width] × [union_y_min, union_y_max - height]``
       (negative-origin-safe — does NOT assume (0, 0) is the minimum).
    """
    if not screens:
        return state

    try:
        # Build the union of all screen rectangles.
        union_x_min = min(s.x for s in screens)
        union_y_min = min(s.y for s in screens)
        union_x_max = max(s.x + s.width for s in screens)
        union_y_max = max(s.y + s.height for s in screens)
        union_w = union_x_max - union_x_min
        union_h = union_y_max - union_y_min
    except Exception as exc:
        log.warning("window_state: could not compute screen union: %s", exc)
        return state

    result = dict(state)

    # Step 1: clamp width/height to the union dimensions.
    w = min(int(result.get("width", union_w)), union_w)
    h = min(int(result.get("height", union_h)), union_h)
    result["width"] = w
    result["height"] = h

    # Step 2: clamp top-left so the window stays within the union.
    if "x" in result:
        x_lo = union_x_min
        x_hi = union_x_max - w
        result["x"] = max(x_lo, min(int(result["x"]), x_hi))

    if "y" in result:
        y_lo = union_y_min
        y_hi = union_y_max - h
        result["y"] = max(y_lo, min(int(result["y"]), y_hi))

    return result
