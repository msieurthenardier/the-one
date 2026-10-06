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


# ── First-launch size and floor (M25 F5 L3, flight DD6) ───────────────────
# Units are logical pixels (pywebview multiplies by the DPI scale on WinForms);
# the size is the OUTER window size (the client area is 16px narrower and 39px
# shorter at 96 DPI).
DEFAULT_SIZE: tuple[int, int] = (1440, 900)
MIN_SIZE: tuple[int, int] = (640, 360)
SCREEN_MARGIN: int = 64


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def work_area(screens: list[Any] | None, platform: str) -> tuple[int, int, int, int] | None:
    """Return the first screen's usable ``(x, y, width, height)``, or None.

    On ``win32`` pywebview's ``frame`` is the WorkingArea (a .NET ``Rectangle``)
    and is used when all four of its fields are real numbers.  Otherwise (GTK's
    ``frame`` is the monitor geometry, and a mock's ``frame`` is not numeric) the
    screen's bounds are reduced by ``SCREEN_MARGIN`` on each side.
    """
    if not screens:
        return None
    try:
        screen = screens[0]
        if platform == "win32":
            frame = getattr(screen, "frame", None)
            vals = tuple(getattr(frame, n, None) for n in ("X", "Y", "Width", "Height"))
            if frame is not None and all(_is_num(v) for v in vals):
                return (int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]))
        sx, sy, sw, sh = screen.x, screen.y, screen.width, screen.height
        if not all(_is_num(v) for v in (sx, sy, sw, sh)):
            return None
        return (
            int(sx) + SCREEN_MARGIN,
            int(sy) + SCREEN_MARGIN,
            int(sw) - 2 * SCREEN_MARGIN,
            int(sh) - 2 * SCREEN_MARGIN,
        )
    except Exception:
        return None


def first_launch_size(screens: list[Any] | None, platform: str) -> tuple[int, int]:
    """``DEFAULT_SIZE`` fitted into the work area (never below ``MIN_SIZE``
    unless the work area itself is smaller, which then wins)."""
    area = work_area(screens, platform)
    if area is None:
        return DEFAULT_SIZE
    _, _, aw, ah = area
    w = max(min(DEFAULT_SIZE[0], aw), min(MIN_SIZE[0], aw))
    h = max(min(DEFAULT_SIZE[1], ah), min(MIN_SIZE[1], ah))
    return (w, h)


def apply_floor(state: dict[str, Any]) -> dict[str, Any]:
    """Lift a saved width or height below ``MIN_SIZE``; leave all else unchanged."""
    result = dict(state)
    for key, floor in (("width", MIN_SIZE[0]), ("height", MIN_SIZE[1])):
        try:
            if key in result and int(result[key]) < floor:
                result[key] = floor
        except (TypeError, ValueError):
            pass
    return result
