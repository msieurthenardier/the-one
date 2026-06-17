# Leg: window-chrome

**Status**: completed *(superseded by Leg 8 — DD3 divert to a native frame; the frameless
custom chrome this leg added was removed. Retained as the executed record of the attempt.)*
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Give the native window custom chrome: open the window `frameless=True` and render a themed
HTML titlebar (minimize / maximize-restore / close) plus a drag region into the web UI's
existing `#app-topbar`, shown **only inside the native window**, with the buttons wired
through a pywebview `js_api` (close → F6 close-to-tray).

## Context

- **DD2** (flight): frameless window + themed titlebar in `#app-topbar`, vanilla JS,
  desktop-only; buttons call a `js_api`; close → close-to-tray; nav buttons AND window
  controls get explicit `no-drag`; render gated on the `pywebviewready` event.
- **DD3** (flight, the lead risk): does `frameless=True, resizable=True` keep Windows
  edge-resize on the installed pywebview? Resolved empirically at the HAT (see "Spike" below).
- **DD7** (flight): verify every new pywebview API against the real install; mock the **real
  runtime form**, not the assumed signature.
- Builds on **Leg 1**'s `DesktopSession` class. The titlebar host (`#app-topbar`) and the
  `renderTopBar()` that rebuilds it live in `the_one/interfaces/web/static/js/app.js:41`.

### Spike — runtime-form questions (cannot run on this Linux dev host)

pywebview is **not installed** on the dev host (the F6/Leg-1 suites mock it). The frameless
**resize**, **drag-region mechanism**, and **`js_api` injection timing** can only be observed
on the **real installed pywebview on Windows** (operator's box / Concourse `windows-2022`).
This leg therefore:
1. Implements to the DD3 **"if yes" default** — `frameless=True, resizable=True` — which is
   the expected-correct path; if the HAT shows edge-resize is lost, the conditional
   **Leg 3 `window-resize`** is opened to re-implement it.
2. Mocks the **real runtime forms** in unit tests (per DD7). Confirmed against the pinned
   **pywebview 5.4** source during design review:
   - `js_api` is an object stored as `Window._js_api`; pywebview's `get_functions()` strips
     `args[0]` (`self`), so `def minimize(self)` → JS `window.pywebview.api.minimize()`.
   - The drag-region selector is the module constant `DRAG_REGION_SELECTOR =
     '.pywebview-drag-region'` (confirmed — **not** a guess).
   - **`easy_drag` defaults to `True`** and pywebview has **no `no-drag` exemption** (that is
     an Electron concept, absent from pywebview's `customize.js`). We pass **`easy_drag=False`**
     and rely solely on a **dedicated `.pywebview-drag-region`** element that does NOT contain
     the interactive controls (see DD-correction below). NB: pywebview's whole-window drag
     listener only activates when `platform == 'chromium'`, and Windows reports
     `'edgechromium'` — so `easy_drag` is likely **inoperative on Windows** either way (the
     drag-region element is the sole JS drag surface regardless). `easy_drag=False` is the
     correct defensive value (documented frameless-drag control, matters on other
     platforms/versions); whether Windows WebView2 handles frameless drag at the native layer
     is a **HAT observation**.
   - `pywebviewready` is a DOM event; the Window has `maximize()`/`minimize()`/`restore()` but
     **no `toggle_maximize()`/`is_maximized`** — toggle state is tracked app-side.
   Tests assert the wiring, not the native effect.
3. Records the three spike runtime-forms (resize / js_api / drag) back into the flight DDs at
   the **docs leg (Leg 6)** once the HAT confirms them, so the mac/Linux port doesn't re-spike.

## Inputs

- `the_one/interfaces/desktop/shell.py` with `DesktopSession` (Leg 1). The window is created
  via `webview.create_window("GleepGlorp AI", url, **_create_kwargs)` with
  `_create_kwargs = {"frameless": False, ...}` today.
- `the_one/interfaces/web/static/index.html` — `<header id="app-topbar"></header>` (line 25).
- `the_one/interfaces/web/static/js/app.js` — `renderTopBar()` (line 41) builds the banner +
  area buttons into `#app-topbar` and wires `.app-picker-button` click handlers.
- `the_one/interfaces/web/static/css/components.css` (and `tokens.css`) — topbar styling.
- **Four** existing assertions pin `create_window` kwargs `frameless is False` and must all
  flip to `True` (intended behavior change): `tests/test_desktop_shell.py:297` and
  `tests/test_window_state.py:309`, `:345`, `:430` (the screens-as-list, screens-as-callable,
  and no-saved-state geometry-restore paths). Missing any of the three in `test_window_state.py`
  silently breaks that suite.

## Outputs

- `DesktopSession` creates the window `frameless=True, resizable=True` and passes a `js_api`
  object exposing `minimize`, `toggle_maximize`, `close` (close routes to the F6
  close-to-tray path — same as the old window X).
- `#app-topbar` renders window-control buttons + a drag region **only when
  `window.pywebview` is present**, with `no-drag` on both the controls and the existing nav
  buttons; rendered/re-checked on the `pywebviewready` event.
- Unit tests covering: create_window now passes `frameless=True` + a `js_api`; the `js_api`
  methods call the right window methods (minimize → window.minimize; toggle_maximize toggles;
  close → close-to-tray path); the titlebar conditional-render logic (controls only when
  `window.pywebview` present); the `no-drag` exemptions present on controls + nav buttons.
- Browser mode (no `window.pywebview`) renders **unchanged** — no fake controls.

## Acceptance Criteria

- [ ] `create_window` is called with `frameless=True`, `resizable=True`, **`easy_drag=False`**,
      and a `js_api=` object (the `DesktopSession`-owned API instance), replacing today's
      `frameless=False`. (`easy_drag=False` disables pywebview's whole-window drag so only the
      explicit `.pywebview-drag-region` element is draggable.)
- [ ] The `js_api` object exposes `minimize()`, `toggle_maximize()`, and `close()`:
      - `minimize()` → `window.minimize()`.
      - `toggle_maximize()` tracks an app-side `_is_maximized` flag (pywebview 5.4 has no
        `toggle_maximize`/`is_maximized`): toggles between `window.maximize()` and
        `window.restore()`, flipping the flag.
      - `close()` invokes the **same close-to-tray path** as the F6 window-X (hide to tray +
        first-run notice, not destroy) **when the tray is active**, so closing via the custom
        button keeps the app running in the tray exactly as F6.
- [ ] `close()` mirrors the F6 tray-fallback: when the tray failed to start (`self._icon is
      None`, so `_on_closing` was never registered), `close()` must `destroy()` (real exit) —
      NOT hide into a non-existent tray, which would make the app unrecoverable.
- [ ] The `js_api` reaches the live window without a chicken-and-egg break: create the API
      instance, pass `js_api=api` into `create_window`, then store the returned window on the
      session (`self._window = _desktop_window`) and give the API its window reference
      (`api._window = _desktop_window`) — pywebview returns from `create_window` before the
      GUI loop starts and the methods only fire after `pywebviewready`. Verified by a unit
      test that the methods act on the window object.
- [ ] The window controls + a **dedicated `.pywebview-drag-region` element** are injected into
      `#app-topbar` **only when `window.pywebview` is present**; in a plain browser (no
      `window.pywebview`) the topbar is byte-identical to today.
- [ ] The drag region is a **dedicated element** (e.g. a flex-spacer in the titlebar) that
      does **NOT contain** the window controls or the `.app-picker-button` nav buttons — they
      are siblings, not descendants. (pywebview has no `no-drag` exemption; keeping the
      interactive controls outside the drag-region element is the only reliable way to stop
      drag from swallowing their clicks.) The nav buttons still fire (hash navigation).
      *(native drag-move effect is HAT-verified; the host-native test asserts the drag-region
      element exists, carries the class, and contains no interactive controls, and that nav
      click handlers still fire.)*
- [ ] The controls are injected **inside `renderTopBar()`** (guarded by `window.pywebview`),
      and `renderTopBar()` is **re-run on the `pywebviewready` event** — because the initial
      `renderTopBar()` fires at `DOMContentLoaded`, before the bridge exists, a one-shot inject
      would draw nothing.
- [ ] The frameless/`js_api`/easy_drag assertions flip across all four pinned tests
      (`test_desktop_shell.py`, `test_window_state.py` ×3) plus a new assertion that `js_api`
      and `easy_drag=False` were passed. All desktop suites green host-native.
- [ ] No regression in the F6 close-to-tray / Quit / focus / window-state paths (Leg 1
      suites still green).
- [ ] `the-one` browser-mode UI (the 513-test browser suite scope) is unaffected — the
      controls are desktop-only and additive.

## Verification Steps

- `.venv/bin/python -m pytest tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py tests/test_window_state.py -x --timeout=30`
- A new/updated unit test for the `js_api` methods (minimize/toggle_maximize/close routing).
- A DOM-shape check that the controls + `.pywebview-drag-region` render only under
  `window.pywebview`, that the drag-region element contains no interactive controls, and that
  nav buttons still fire. **No JS unit harness exists in this repo** — use a Playwright test
  with `window.pywebview` stubbed via `page.add_init_script` (browser-marked, excluded from
  the default CI path), or a documented manual check; the HAT covers the native effect.
- **HAT-deferred** (Leg 7, real Windows install): frameless window shows the themed titlebar;
  minimize/maximize-restore/close-to-tray buttons work; titlebar drags the window; window
  resizes (DD3 resolution); nav buttons still fire under the drag region.

## Implementation Guidance

1. **Spike-equivalent reading first (DD7).** Read the installed pywebview's `create_window`
   signature and `js_api`/`frameless`/`resizable`/drag docs in the project's pinned pywebview
   version (check `pyproject.toml` / the lockfile for the version; read the package source if
   vendored). Mock the **real form** in tests. Flag any API whose runtime form can't be
   confirmed without Windows as a HAT check.
2. **Shared close-to-tray session method.** Extract the F6 close-to-tray body (first-run
   notice + `_desktop_window.hide()` → cancel destroy) into a session method, with the
   tray-fallback guard: if `self._icon is None`, set `_really_quit = True` and `destroy()`
   instead of hiding. Both `_on_closing` (the events.closing handler) and `js_api.close()`
   call this one method, so there is a single close-to-tray implementation and the
   tray-absent case can never hide into a non-existent tray.
3. **`js_api` class** — add a small API class (e.g. `_WindowApi`) the `DesktopSession` owns.
   `minimize(self)` → `self._window.minimize()`; `toggle_maximize(self)` keeps an
   `_is_maximized` bool (init `False`), calling `self._window.maximize()` / `.restore()` and
   flipping it; `close(self)` → the shared close-to-tray method. Add a comment that pywebview
   strips `self` so these are zero-arg JS calls. Wiring order: build `api`, pass `js_api=api`
   to `create_window`, then `self._window = _desktop_window` and `api._window = _desktop_window`
   after the call returns. (Optional, HAT-only: subscribe `events.maximized`/`events.restored`
   to keep `_is_maximized` accurate if the user maximizes via the OS — defer unless cheap.)
4. **`create_window` kwargs** — set `frameless=True, resizable=True, easy_drag=False,
   js_api=api`. Keep the window-state-restore width/height/x/y kwargs from F6.
5. **Titlebar render in `app.js`** — inject the window controls + a **dedicated drag-region
   element** (`<div class="pywebview-drag-region">`, a flex spacer) into `#app-topbar`
   **inside `renderTopBar()`**, guarded by `if (window.pywebview)`, so they re-appear on every
   nav render. Also trigger a `renderTopBar()` (or re-check) on the `pywebviewready` event so a
   render that ran before the bridge existed draws them. The drag-region element must NOT wrap
   the controls or the `.app-picker-button` nav buttons — make them siblings of the spacer.
   Buttons call `window.pywebview.api.minimize()` / `.toggle_maximize()` / `.close()`.
6. **CSS** — style the controls to match the themed topbar (existing tokens in `tokens.css`);
   the `.pywebview-drag-region` spacer fills the titlebar's empty space (e.g. `flex: 1`) and
   carries no interactive children.
7. **Tests** — flip the four `frameless` assertions to `True` (`test_desktop_shell.py:297`,
   `test_window_state.py:309/345/430`); assert `js_api` and `easy_drag=False` passed; add
   `js_api`-method tests (minimize/toggle_maximize toggle/close→close-to-tray + close→destroy
   when `_icon is None`); add the conditional-render + drag-region-has-no-interactive-children
   assertions by the cleanest available means (no JS unit harness exists — a Playwright test
   with `window.pywebview` stubbed via `page.add_init_script`, or a documented manual check).

## Edge Cases

- **`window.pywebview` injected late** — covered by rendering on `pywebviewready`; also
  re-check inside the render path so an early `renderTopBar()` that ran before the bridge
  re-draws controls once ready.
- **`renderTopBar()` builds `innerHTML`** — inject the window controls + drag region **inside**
  `renderTopBar()` (guarded by `window.pywebview`), and **re-run `renderTopBar()` on the
  `pywebviewready` event**. Rationale (corrected at re-review): `renderTopBar()` runs once at
  `DOMContentLoaded` — which fires *before* the pywebview bridge is injected — so a one-shot
  inject at load would draw nothing; re-running on `pywebviewready` is what makes the controls
  appear. (`switchTo()` only toggles `aria-current`, it does not rebuild the topbar, so nav
  itself won't drop the controls — but injecting inside `renderTopBar()` keeps a single render
  path and is robust if that changes.)
- **close → close-to-tray when the tray failed to start** — F6 falls back to default destroy
  when `build_tray` raised (no `_on_closing` registered). `js_api.close()` routes through the
  shared close-to-tray method (step 2), which checks `self._icon is None` and `destroy()`s
  (real exit) in that case rather than hiding into a non-existent tray.
- **`easy_drag` must be `False`** — leaving the pywebview default (`True`) on a frameless
  window makes the whole body a drag surface and every non-`stopPropagation` click starts a
  drag; pywebview has no `no-drag` class to exempt children. `easy_drag=False` + a dedicated
  `.pywebview-drag-region` element is the only reliable design.
- **Maximize on a frameless window** — DD's "acceptable variation": true OS-maximize vs a
  manual fill-work-area, whichever is reliable frameless (HAT-confirmed). Implement the
  pywebview-native call; flag for HAT.
- **Browser mode** — `window.pywebview` undefined → zero controls, zero drag region, no
  behavior change. Assert this.

## Files Affected

- `the_one/interfaces/desktop/shell.py` — `frameless=True, resizable=True`, `js_api`; a
  shared close-to-tray session method that both `_on_closing` and `js_api.close()` call.
- `the_one/interfaces/web/static/js/app.js` — titlebar controls + drag region, `no-drag`,
  `pywebviewready` gating.
- `the_one/interfaces/web/static/css/components.css` (or a new desktop-chrome CSS block) —
  titlebar control styling + drag-region rules.
- `tests/test_desktop_shell.py` — frameless→True (:297), `js_api` + `easy_drag=False`
  assertions.
- `tests/test_window_state.py` — frameless→True at :309, :345, :430.
- New test(s) for `js_api` methods (minimize / toggle_maximize / close→close-to-tray /
  close→destroy-when-no-tray) + conditional-render logic.

---

## Post-Completion Checklist

**Per this flight's batched model — set status to `landed` (NOT `completed`); do NOT commit
or signal `[COMPLETE:leg]`. Code review + commit are deferred to the end of the last
autonomous leg.**

- [ ] All non-HAT acceptance criteria verified host-native
- [ ] HAT-deferred criteria explicitly listed in the flight-log entry for the operator HAT (Leg 7)
- [ ] Update flight-log.md with leg progress entry (incl. spike runtime-forms still pending HAT)
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
