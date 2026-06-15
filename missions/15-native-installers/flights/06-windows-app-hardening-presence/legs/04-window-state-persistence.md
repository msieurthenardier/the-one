# Leg: window-state-persistence

**Status**: completed
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](../flight.md)

## Objective

Persist the window's size and position to `window-state.json` under `data_dir` and
restore it on the next launch — clamped to visible monitor bounds — so the app reopens
where the user left it.

## Context

- Flight DD5: **close-only geometry capture is the baseline** (pywebview 5's `moved`
  event is unreliable across backends; live save-on-move/resize is a stretch goal, NOT
  this leg). Restore clamps to visible bounds so a window saved on a now-absent monitor
  doesn't open off-screen.
- `data_dir` (platformdirs) is the per-user store that survives restart + reinstall
  (same store as the F5 webview profile and the Leg-2 notice marker).
- Leg 2 added `_on_closing` (every X press routes through it) and `_on_quit`
  (Quit-from-tray → `window.destroy()`). **Capture geometry at BOTH** — `_on_closing`
  covers the user-X path; `_on_quit` covers Quit-from-tray (a programmatic `destroy()`
  may not re-fire `closing`). Dedupe into one `_save_current_geometry(window)` helper.

## Inputs

- `the_one/interfaces/desktop/shell.py` — `run_desktop()` (creates the window via
  `webview.create_window`), `_on_closing`, `_on_quit` (Leg 2); `settings.data_dir`.
- pywebview `Window`: `create_window(..., width, height, x, y)` accepts initial
  geometry; the live window exposes `width`/`height` (and `x`/`y` if available) for
  capture; `webview.screens` lists monitors (for the clamp). **Verify these against the
  installed pywebview during implementation** (attribute availability is the risk).

## Outputs

- `the_one/interfaces/desktop/window_state.py` — new; `load_state()`, `save_state(...)`,
  `clamp_to_bounds(state, screens)`.
- `the_one/interfaces/desktop/shell.py` — read+clamp state before `create_window`
  (apply width/height/x/y); a `_save_current_geometry(window)` helper called from
  `_on_closing` and `_on_quit`.
- `tests/test_window_state.py` — new; load/save/clamp/corrupt-file unit tests + the
  capture-on-close wiring.

## Acceptance Criteria

- [ ] `window_state.py` round-trips geometry to `data_dir / "window-state.json"`:
      `save_state(width,height,x,y)` writes JSON; `load_state()` reads it back as a dict
      (or `None` if absent). (Tested with a temp `data_dir`.)
- [ ] **Restore on launch:** when a saved state exists, `run_desktop()` passes
      `width`/`height`/`x`/`y` (post-clamp) to `webview.create_window`. (Tested:
      `load_state` returning a rect → `create_window` called with those kwargs, mocked.)
- [ ] **First run / no state:** with no `window-state.json`, `create_window` is called
      with the F4 defaults (no geometry kwargs forced). (Tested: `load_state()` → None →
      default create.)
- [ ] **Visible-bounds clamp:** an off-screen saved rect (e.g. x/y beyond the union of
      `webview.screens` bounds) is clamped so the window is on-screen; an on-screen rect
      is unchanged. (Unit-tested with synthetic screen rects.)
- [ ] **Capture on close:** geometry is saved via `_save_current_geometry(window)` from
      BOTH `_on_closing` (user X) and `_on_quit` (Quit-from-tray), before hide/destroy.
      (Tested: a mock window with geometry attrs → both paths write the file.)
- [ ] **Corrupt/missing file → defaults, no crash:** a malformed `window-state.json`
      makes `load_state()` return `None` (logged), not raise. (Tested with garbage file.)
- [ ] If pywebview doesn't expose `x`/`y` for capture on the installed version, capture
      `width`/`height` only and log the partial-capture once (documented degrade) —
      restore still applies whatever was saved. (Verified during impl; tested for the
      width/height-only path.)
- [ ] `tests/test_window_state.py` passes host-native; Leg 1/2/3 suites still pass.

## Verification Steps

- `python -m pytest tests/test_window_state.py tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py -x --timeout=30 -q`
  (host-native — NOT docker) — all green.
- `python -c "from the_one.interfaces.desktop import window_state; print('ws import ok')"`
  — imports without a GUI stack (no top-level pywebview).
- `git diff --stat` — scoped to `the_one/interfaces/desktop/` + `tests/`.

## Implementation Guidance

1. **`window_state.py`** (no GUI imports at module top — keep it importable headless):
   - **Do NOT bind a module-level `STATE_PATH`** — compute the path **at call time** via
     a helper `def _state_path() -> Path: return settings.data_dir / "window-state.json"`
     so a test's `monkeypatch.setattr(settings, "data_dir", tmp_path)` is honored (a
     module-level assignment would freeze the path at import).
   - `load_state() -> dict | None`: read+`json.loads`; on `FileNotFoundError` →
     `None`; on `json.JSONDecodeError`/`OSError` → log warning, `None`.
   - `save_state(width, height, x=None, y=None) -> None`: `settings.data_dir.mkdir(
     parents=True, exist_ok=True)`; write `{"width":…, "height":…, "x":…, "y":…}` (omit
     `x`/`y` if `None`).
   - `clamp_to_bounds(state, screens) -> dict`: compute the union of screen rects
     (`Screen` has `x/y/width/height`). First **bound width/height** to the union's
     dimensions (a saved 8K window on a 1080p screen must shrink, else the right/bottom
     clamp bound goes negative). Then clamp the top-left into
     `[union_x_min, union_x_max - width] × [union_y_min, union_y_max - height]` (handles
     negative-origin secondary monitors — use the union mins, not `(0,0)`). If `screens`
     is empty/unavailable, return `state` unchanged.

2. **`shell.py` restore (before `create_window`)** — `state = load_state()`; if present,
   `clamp_to_bounds(state, webview.screens())` (**`screens()` is a function — call it
   with parens**) and spread its keys into the `create_window(...)` call
   (`width=…, height=…, x=…, y=…`). If absent, call `create_window` exactly as today
   (F4 defaults).

3. **`shell.py` capture** — `_save_current_geometry(window)`:
   - **Pre-check `if not window.events.shown.is_set(): return`** — `window.width/x/y`
     internally call `shown.wait(15)`; reading them before the window has shown would
     **block the GUI thread up to 15 s** (these run inline on the GUI thread in the
     winforms backend), freezing the close. Skip the capture in that race.
   - Read geometry defensively: `try: w, h, x, y = window.width, window.height,
     window.x, window.y` `except Exception: return` (these are *properties* backed by
     GUI calls in pywebview 5 — `getattr(..., None)` would NOT catch a GUI-not-ready
     error; a try/except does, and also covers an older pywebview lacking x/y).
   - `save_state(w, h, x, y)`.
   - Call it at the top of `_on_closing` (before hide/destroy) and in `_on_quit` (before
     `window.destroy()`). The whole thing is best-effort — log, never block the close.

4. **Tests** (`tests/test_window_state.py`) — monkeypatch `settings.data_dir` →
   `tmp_path`. Cover round-trip, None-on-missing, None-on-corrupt, clamp on/off-screen
   (incl. the saved-wider-than-screen shrink and a negative-origin monitor),
   the create_window-with-geometry wiring (mock webview; `webview.screens` mock returns
   a list — `screens.return_value=[...]`), and the dual capture paths. **Configure the
   mock window's geometry with integers** (`mock_window.configure_mock(width=1280,
   height=800, x=100, y=50)` and set `events.shown.is_set.return_value=True`) — a bare
   `MagicMock` returns truthy mocks, not ints, so the saved JSON would be non-numeric.
   Reuse the `sys.modules` webview-mock fixture pattern from `test_desktop_shell.py`.

## Edge Cases

- **`closing` fires on `destroy()` in all pywebview-5.4 backends** (winforms/gtk/cocoa,
  verified in source) — so capturing in `_on_closing` alone already covers the Quit
  path (Quit sets `_really_quit` then destroys → `closing` fires → capture runs). The
  `_on_quit` capture is therefore **redundant but kept for forward-safety** against a
  future backend that stops firing `closing` on destroy; the double write is idempotent
  (same geometry). (Corrected from the design-review — the original "destroy may not
  fire closing" rationale was wrong for the pinned version.)
- **Capture-skip on the startup race:** if the window closes before `shown` fires,
  `_save_current_geometry` returns early (the `shown.is_set()` pre-check) rather than
  blocking on `shown.wait(15)` — that launch just doesn't update the saved geometry.
- **Hidden window geometry:** when close-to-tray has hidden the window, its last
  geometry attributes persist; capturing on a later Quit saves the last-known position.
  Acceptable.
- **Multi-monitor removal:** the clamp handles a saved rect on a monitor that's gone.
- **Negative coordinates are valid** on multi-monitor (a left/upper secondary monitor) —
  the clamp must treat the *union* of screen rects as valid, not assume `(0,0)` origin.
- **State freshness contract:** source of truth = the live window geometry; write
  trigger = on close (both paths); max staleness = "last close" (acceptable for
  window position); single writer (one window) → no invalidation map needed. No DB/FK.

## Files Affected

- `the_one/interfaces/desktop/window_state.py` — new.
- `the_one/interfaces/desktop/shell.py` — restore-on-create + `_save_current_geometry` from both close paths.
- `tests/test_window_state.py` — new.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (`test_window_state.py` + Leg 1/2/3 suites, host-native)
- [ ] Update flight-log.md with the leg progress entry
- [ ] Set this leg's status to `landed` (completion/commit deferred to flight-end review)

## Citation Audit

2 citations verified at leg-design time (2026-06-15): `the_one/interfaces/desktop/
shell.py` (`run_desktop` create_window, `_on_closing`, `_on_quit`) — OK (Leg 2/3
outputs); `settings.data_dir` — OK (platformdirs, `config.py`). pywebview geometry
attributes (`window.x/y/width/height`, `create_window(x,y,width,height)`,
`webview.screens`) are library API to confirm against the installed pywebview during
implementation (flagged as the leg's risk + a documented width/height-only degrade).
