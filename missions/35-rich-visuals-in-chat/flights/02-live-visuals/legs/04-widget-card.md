# Leg: widget-card

**Status**: completed
**Flight**: [Live Visuals](../flight.md)

## Objective
Build `App.ui.widget`, the card that wraps the hardened frame. It covers:
- the agent-made marking;
- the header controls (Pause/Resume, Restart, Start anyway);
- the limits and notices (too large, cut off, empty, escape);
- theme following, View source, and `sweep()` teardown;
- the CSS for the boards, including the narrow layout;
- the `pause` and widget icons, and the catalogue and testid rows.

It exposes a small instance API that leg 5's lifecycle manager will drive. In this leg a card loads its frame as soon as it is created, which is the simplest policy; leg 5 replaces the policy, not the API.

## Context
- **Flight DDs:** DD10 (marking; focus is now frame-side only, so the card adds no focus listeners), DD11 (limits), DD12 (cut-off), DD3 (the escape notice), DD5 (theme), DD7 (the states this card renders; leg 5 owns the transitions).
- **Mockups:** boards 1, 2, 3, 5 and 6 (https://claude.ai/artifact/RarECj12aPxfKNH81o4UAX). Board 6's "kept taking focus" card is dropped (operator, 2026-11-09).
- **Leg 1 + 3a:** `App.ui.widgetFrame(opts)` returns `{iframe, destroy(), postTheme(theme), postPause(), postResume(), loads(), paused}`.
  - **Options:** `slot`, `source`, `title`, `theme`, `paused`, and the callbacks `onSize(h)`, `onHeartbeat()` and `onEscape()`.
  - **Statics:** `buildDocument`, `readTheme`, `PRELUDE`, `POLICY`, `LINK_RE` and `limits` (`js/ui/widget-frame.js:500`, `:609`, `:631-643`).
  - **Theme:** the module-level theme `MutationObserver` already pushes theme changes to live frames (leg 1).
- **Leg 2:** `App.ui.visualNotice({tone, headline, reason, source, sourceLabel, testid, detailsTestid})`.
- **Library rules learned this flight** (each one failed a guard once):
  - Every `js/ui` file is an ES5 strict IIFE, touches only `App.ui`/`App.icons`, and exports its factory exactly as `  App.ui.widget = function (opts) {` (`tests/test_ui_library_source.py`).
  - Shared internals live under `App.ui.util.*`.
  - Every emitted class is owned by a catalogue row and written in a form the emitted-class scanner sees (`className:`/`cls`/`*Class`).
  - A catalogue row may cite only real factories.
  - A `document` listener must be removed in the same file (the paired-listener guard).
  - No `innerHTML`/`outerHTML`/`insertAdjacentHTML` tokens anywhere in a `js/ui` file, comments included (only `widget-frame.js` has an exact allowance).
- **Lane:** tests go in `tests/browser/test_ui_widget_card*.py`, which match `contracts-widget`'s `test_ui_widget*` (leg 3a). The inventory test needs a `test_ui_*.py` file that literally calls `App.ui.widget(`.

## Inputs
- `widget-frame.js` (648 lines), `visual-notice.js`, `ui/button.js` (`App.ui.button`, `icon` option), `ui/core.js:238` (`App.ui.icon`), `ui/feedback.js:277` (`App.ui.chip`), `ui/disclosure.js:25`, `ui/page.js:166` (`App.ui.codeBlock`).
- `js/icons.js` has `play`, `refresh-cw` and `stop`; no `pause` and no widget icon.
- `css/components.css:2949-2950` is the chart width rule inside the assistant bubble (`width: 46rem`); mirror it for `.ui-widget`.
- There are no container queries in the CSS yet.

## Outputs
- **`js/ui/widget.js`:** `App.ui.widget = function (opts)`.
  - **Options:** `source` (string), `closed` (boolean, default true), `agentName` (string or null), `testid` (string prefix), `key` (string; leg 6 supplies session parts), `paused` (initial; default false).
  - **Returns:**
    - `null` for an empty or whitespace-only source;
    - the **notice node's handle** `{el, destroy()}` for too-large and cut-off sources (no card, no frame);
    - otherwise a card handle `{el, destroy(), state(), start(), pause(), resume(), restart(), unload(), stop(kind)}`. `kind` is `hung` or `hung-last` (leg 5).
  - **Statics:** `App.ui.widget.sweep()`, plus underscore test seams documented as test-only (`_instances()`).
- **CSS:**
  - `.ui-widget*` rules per the boards, using tokens only;
  - `.ui-message--assistant .ui-widget { width: 46rem; }` beside the chart rule;
  - a narrow layout through a container query (`container-type: inline-size` on the card; below about 420 px the button labels hide, the buttons stay named, and the title ellipsizes), verified in WebKit.
- **Icons:** `pause`, and a widget icon (`app-window`-like: a rounded square with a play triangle, per the boards), added to `js/icons.js` in the existing format. Check the icon guard and contract tests (`test_ui_icon_contract.py`) for any pinned icon count.
- **Catalogue:** an `App.ui.widget` row (owned classes, sub-entries, the instance API, test seams). The `widgetFrame` row notes that it is wrapped by `widget`.
- **Testid registry:** a parametric family under `{t}`: `{t}`, `{t}-frame`, `{t}-pause`, `{t}-restart`, `{t}-start`, `{t}-source`, `{t}-notice`. Chat uses the prefix `chat-widget` (leg 6).
- **Contract tests:** `tests/browser/test_ui_widget_card_contract.py` (Chromium + WebKit).

## Acceptance Criteria
- [ ] **AC1 — Structure and marking** (boards 1, 2, 6).
  - `figure.ui-widget[data-testid={t}]` > a header > a body > a "View source" disclosure.
  - **The header**, in this order:
    - the widget icon (`aria-hidden`);
    - "Widget by {agentName}" ("Widget by the agent" when absent);
    - `· {title}` when the source's first `<title>` element has text. Use a bounded case-insensitive regex over the first 8 KiB; strip any tags inside, collapse whitespace, trim, cap at 60 code points. Shown in its own span; omitted when empty;
    - a "Paused" chip (`App.ui.chip`) when paused by the operator;
    - a flexible spacer;
    - Pause/Resume, one `App.ui.button` with `aria-pressed`. Its visible label is "Pause"/"Resume" and its accessible name "Pause widget"/"Resume widget". Testid `{t}-pause`;
    - Restart (`{t}-restart`, "Restart widget").
  - **The body** holds the frame (`{t}-frame` on the iframe), or a stopped message plus a Start anyway button (`{t}-start`).
  - **"View source"** is an `App.ui.disclosure` (closed) holding `App.ui.codeBlock` with the exact source (`{t}-source`).
  - All text goes through `textContent`. The iframe's `title` is "Widget by {agentName}" ("Widget by the agent").
  - **Contract tests, both engines,** cover each part, plus a title with markup inside (`<title>A <b>B</b></title>` reads "A B"), a 200-character title capped at 60, no title, and a null agent name.
- [ ] **AC2 — Controls.**
  - **Pause** posts `postPause()`. The button flips to Resume (`aria-pressed=true`) and the Paused chip appears. **Resume** reverses both.
  - **Restart** destroys the frame and mounts a fresh one: `loads()` restarts at 1, and the frame's own counter starts from 0. A paused widget is no longer paused after Restart.
  - **Start anyway** (in stopped states) mounts a fresh frame, unpaused.
  - `opts.paused:true` mounts with `widgetFrame({paused:true})` and shows the paused header.
  - Contract tests, both engines, using in-frame counters (never `isActive` through `evaluate`).
- [ ] **AC3 — Notices and limits** (DD11, DD12, DD3; boards 3, 5, 6):
  - **Too large:** a source over 64 KiB in UTF-8 bytes returns `App.ui.visualNotice({tone:'danger', headline:"Couldn't run this widget.", reason:'This widget is too large to run (N KB; the limit is 64 KB).', source, sourceLabel:'Widget source', testid:'{t}-notice'})`. N is `ceil(bytes/1024)`. Count UTF-8 bytes correctly for astral characters.
  - **Cut off:** `closed === false` returns the muted `visualNotice` with headline "This widget was cut off before it finished." and the source. The source never runs.
  - **Empty or whitespace-only:** returns `null`.
  - **Escape:** `onEscape` puts the card in the stopped state "This widget tried to leave its frame and was stopped." with Start anyway. The header (marking) stays.
  - **Hang:** `stop('hung')` shows "This widget stopped responding." and `stop('hung-last')` shows "This widget stopped responding last time.", each with Start anyway. These are called by leg 5; this leg tests them through the handle.
  - **Size:** the frame height follows `onSize`, within 48-720, 240 before the first message (leg 1). The card keeps the last height when it unloads, so the log does not jump.
  - Contract tests for each, both engines. A source of exactly 65,536 bytes runs, and one byte more does not.
- [ ] **AC4 — States and API for leg 5.** `state()` returns one of `running`, `paused-user`, `paused-auto`, `waiting`, `stopped-hung`, `stopped-escape`.
  - `pause()`/`resume()` are the operator's pause, `paused-user`, which drives the header and chip.
  - `unload()` destroys the frame, keeps the slot height, and shows the waiting body (the header over an empty body).
  - `start()` mounts from `waiting`.
  
  A test covers each transition through the handle. **The auto-pause (`paused-auto`) is an internal state that leg 5 sets through a documented handle method (`autoPause()`/`autoResume()`), which does not show the chip.** It is added now, so leg 5 does not reshape the API.
- [ ] **AC5 — Theme.** With two cards loaded, switching `data-theme` on `documentElement` updates both frames' `--bg`, read through the frame. A card created after the switch mounts in the new theme. (The observer is leg 1's; this is a regression test at the card level.)
- [ ] **AC6 — `sweep()` and destroy.**
  - `destroy()` is idempotent: it removes the frame and releases the instance.
  - `App.ui.widget.sweep()` destroys every instance that was connected once and is no longer connected; one never attached is kept.
  - Test: create 3 cards, attach them, detach 2, `sweep()`. Exactly 2 are destroyed (`_instances()`), and their frames' `contentWindow`s are gone from the frame core's `Map` (a seam on `widgetFrame`, for example `_live()`, if one is needed).
- [ ] **AC7 — Layout.**
  - Inside an assistant bubble the card's preferred width is 46rem, capped at the bubble.
  - At a card width under about 420 px, Pause and Restart are icon-only with unchanged accessible names, and the title ellipsizes.
  - Contract test in both engines: set the container width to 340 px, then assert the labels are visually hidden (or have no rendered width) and the accessible names are intact.
- [ ] **AC8 — Library rules.**
  - Catalogue row and registry.
  - Guards: `test_ui_library_source`, `test_ui_guards` (HTML sinks, paired listeners, srcdoc, `UI_DIR_SINK_ALLOWANCE` unchanged), `test_ui_control_inventory`, `test_ui_ownership`, `test_ui_emitted_classes`, `test_token_definitions`, `test_design_tokens_a11y`, `test_run_tests_lanes`.
  - `ruff` clean.
  - `index.html` loads `widget.js` after `widget-frame.js` and `visual-notice.js`.

## Verification Steps
- **Static and unit:** the guard set above, then `THE_ONE_TEST_NETNS=1 make test-unit` (squawk 0344 is a known intermittent, not this leg's).
- **Browser:**
  - `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-widget -x`;
  - `--lane contracts-controls -x`, because icons are shared and `test_ui_icon_contract.py` lives there;
  - `--lane contracts-chat -x`, because of the `visualNotice` reuse.
  
  Record the `contracts-widget` time against its provisional 300 s budget.
- **Falsification:** one assertion of the Developer's choice per AC1 (title extraction), AC3 (the byte limit) and AC6 (sweep), each restored by editing.

## Implementation Guidance
1. **Build with DOM APIs and library pieces only:**
   - header buttons via `App.ui.button({icon, label, testid})`, then set `aria-pressed` and the accessible name;
   - the chip via `App.ui.chip`;
   - View source via `App.ui.disclosure` plus `App.ui.codeBlock`.
   
   Emit classes as `className:`/`cls` literals.
2. **Keep the instance state in one object,** with one `render()` that patches the header and body from `state`, and no re-creation of the header.
3. **The UTF-8 byte count:** use `new Blob([source]).size` where available, or a manual count over code points. Do not use `TextEncoder` unless it is guaranteed in WebKitGTK 2.52 (it is; either is fine).
4. **The narrow layout:** `container-type: inline-size` on `figure.ui-widget`, with `@container (max-width: 420px)` hiding `.ui-widget-btn-label`. Labels stay in the DOM for the accessible name (or use `aria-label`).
5. **Do not add an `IntersectionObserver`, the cap, the ceiling, the hang guard or `visibilitychange`.** Those are leg 5. In this leg the frame mounts at construction, unless `paused` is set (then it mounts paused).

## Edge Cases
- **`<title>` inside a script string:** the regex still reads it. Accepted, since the title is only a label.
- **A source with a BOM or CRLF:** counted as bytes, and shown verbatim in View source.
- **A Restart while the frame is mid-load:** destroy and remount; no leak (`loads()` resets).
- **An escape fired after `destroy`:** ignored.
- **Two cards with the same `key`:** allowed. Keys matter in leg 5.

## Files Affected
- `the_one/interfaces/web/static/js/ui/widget.js` - new
- `the_one/interfaces/web/static/js/ui/widget-frame.js` - a test seam only, if needed (`_live()`)
- `the_one/interfaces/web/static/js/icons.js` - `pause` and a widget icon
- `the_one/interfaces/web/static/css/components.css` - the card styles and the width rule
- `the_one/interfaces/web/static/index.html` - the script tag
- `tests/browser/test_ui_widget_card_contract.py` - new
- `tests/browser/_widget_harness.py` - extended if useful (leg 3a's helper)
- icon pin tests, if they count icons
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md`

## Citation Audit
Verified on 2026-11-09 against the working tree (legs 1, 2 and 3a landed, uncommitted):
- `js/ui/widget-frame.js:500` `App.ui.widgetFrame = function (opts) {`; header comment `:6-21` (the handle and callbacks); `:415` `--frame-paused`; `:609` `postResume`; `:631` `paused`; `:638-643` statics - verified
- `css/components.css:2949-2950` - `.ui-message--assistant .ui-chart:not(.ui-chart--spark), .ui-message--assistant .ui-chart-placeholder { width: 46rem; }` - verified
- `js/ui/core.js:238` `App.ui.icon = function (name, opts)`; `ui/button.js:18-25` (`icon` option, an `App.icons` name) - verified
- `tests/test_ui_library_source.py` rules; `UI_DIR_SINK_ALLOWANCE` (leg 3a) - verified
- `scripts/run-tests.sh` `contracts_widget_pat=('test_ui_widget*')` (leg 3a) - verified from the leg 3a report
