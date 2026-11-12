# Leg: widget-frame-hardening

**Status**: completed
**Flight**: [Live Visuals](../flight.md)

## Objective
Harden leg 1's frame core with the controls the leg 1 gate chose, all inside the frame's prelude and document builder:
- the gesture-recency **focus gate**;
- **layered link blocking** (preconnect), with every known bypass closed;
- the cooperative **pause gate** with a correct initial state.

Re-pin the prelude, add the exact guard allowance, and move the widget contract tests into their own lane.

## Context
- **Flight DDs:** DD6 (the prelude; the gate's preconnect decision), DD8 (pause), DD10 (focus, as amended below).
- **Operator decisions:**
  - **The leg 1 gate:** preconnect layered blocking; the frame-side focus gate.
  - **This leg's design review (2026-11-09):** the focus gate is **frame-side only**. A programmatic focus runs only while `navigator.userActivation.isActive` **and** a trusted gesture inside the frame happened within about 1 s.
  - **The page-side backstop and the `stopped-focus` state and card are dropped.** The review showed the backstop's activation report was forgeable, and that it would undo real clicks.
- **What the design-review probes found** (scratchpad `leg3rev/`):
  - **Focus, Chromium:** with no gate, a 10 ms `focus()` loop stole 20/20 characters. An `isActive`-only gate held while the operator typed, but leaked 8/40 characters in the about 5 s after a click inside the widget (transient activation). Real clicks and Tab into the frame work with the gate. No other steal route moved focus (`select`, `setSelectionRange`, `label.click`, hash, `showModal`, `dialog.show`, `window.focus`, `parent.focus`, synthetic events). Headless WebKit never shows the steal, so falsification is Chromium-only.
    - **Playwright pitfall:** `frame.evaluate` grants user activation. Measure with in-frame counters, never by reading `isActive` through `evaluate`.
  - **Links, WebKit sink TCP:** every entry point opened 1 TCP connection without a rewrite. With the rewrite, all gave 0 except two bypasses:
    1. `document.write('<li'); document.write('nk rel=preconnect …>')` (the tokenizer streams across calls);
    2. `DOMParser` `application/xml` with `<h:link xmlns:h="…xhtml">` plus `importNode`.
    
    Only links in `<head>` opened TCP. Chromium was 0 everywhere.
  - **Pause:** a pause sent after load arrives after the widget's first timers and frames, and one sent before load is lost. The initial state must be in the document.
- **Leg 1 files** (uncommitted, in the working tree):
  - `js/ui/widget-frame.js` (358 lines; prelude sections capture → neuter → `/* PAUSE-GATE */` → handlers);
  - `tests/test_widget_frame_prelude.py` (node pin tests, including `test_source_is_appended_verbatim_even_when_hostile`);
  - `tests/browser/test_ui_widget_frame_contract.py`, `tests/fixtures/widgets/escape.html`, `tests/browser/_widget_sink.py`.
- **Leg 2** moved shared internals under `App.ui.util.*`; `tests/test_ui_library_source.py` rules apply (below).

## Inputs
- Leg 1's frame core and tests, as above. The contract test still has the allow-list entry `("webkit","tcp",4,"DD6 preconnect")`.
- `tests/_ui_guard_helpers.py`: `find_ui_dir_sink_tokens` (`:181`, comments included) and `SRCDOC_SINK_ALLOWANCE` (leg 1), the pattern to mirror.
- `scripts/run-tests.sh`: `contracts_chat_pat` includes `test_ui_widget*` and `test_ui_visual_notice*`; the `contracts-chat` budget is 150 s (about 100 s measured before this flight).

## Outputs
- `widget-frame.js` gains the focus gate, link blocking and pause gate, `postPause()`/`postResume()`, and a `paused` option (the initial state). The prelude is re-pinned.
- `buildDocument` rewrites link tags in the source (AC2).
- `tests/_ui_guard_helpers.py` and `tests/test_ui_guards.py` gain `UI_DIR_SINK_ALLOWANCE = {"widget-frame.js": N}` (an exact count), with a tmp-dir probe.
- **A new lane `contracts-widget`** holds every `test_ui_widget*` file (explicit list), removed from `contracts_chat_pat`. Updates go to:
  - the `scripts/run-tests.sh` budget table;
  - the `contracts` alias (`overlay` + `chat` + `controls` + `widget`);
  - `--help`;
  - `tests/test_run_tests_lanes.py` (lane list, pairwise disjointness, union, budget table);
  - CLAUDE.md's lane section (an 18th lane, with a provisional budget re-measured at the closing gate).
- The escape battery and contract tests are extended.

## Acceptance Criteria
- [ ] **AC1 — Focus gate (frame-side only).**
  - **Prelude:**
    - Capture-phase `window` listeners record the time of the last **trusted** (`event.isTrusted`) `pointerdown`, `mousedown`, `keydown`, `click` or `touchstart` inside the frame.
    - `HTMLElement.prototype.focus`, `SVGElement.prototype.focus` and `MathMLElement.prototype.focus` (where present), `Window.prototype.focus` (where present) and `window.focus` are replaced (non-configurable, non-writable). Each calls the original only when `navigator.userActivation && navigator.userActivation.isActive` **and** the last trusted gesture was at most 1000 ms ago. Otherwise it is a silent no-op.
    - The `autofocus` property setter is neutered, and the prelude's `MutationObserver` strips `autofocus` attributes. The source rewrite does **not** touch `autofocus`; the observer and the engines' cross-origin autofocus blocking cover it.
  - **Page:** no focus listeners (no `focusout`/`blur` backstop).
  - **Contract tests:**
    - (a) **Chromium:** a page textarea is focused; a widget runs a 10 ms `focus()` loop on its input; typing 40 characters puts all 40 in the textarea.
    - (b) **Chromium:** a real click into the widget's input focuses it, typing reaches it; then a real click on the page textarea; with the widget's loop starting at once, typing 40 characters puts at least 39 in the textarea.
    - (c) **Both engines:** a real click into the widget's input focuses it, and typing reaches it.
    - (d) **Both engines:** Tab from the page into the frame focuses the widget's first focusable element.
    - (e) **Both engines:** a click on a button inside the widget whose handler calls `input.focus()` focuses that input.
    - **Falsified:** without the gate, (a) fails in Chromium. With `isActive` alone (no recency), (b) fails.
- [ ] **AC2 — Link blocking (DD6, layered, best-effort).**
  - **The source rewrite:** `buildDocument` rewrites `/<(\/?)link(?=[\s/>])/gi` to `<$1x-link` in the source before appending it. A literal `<link` inside a script string or `<pre>` is also rewritten; that is accepted and documented in `docs/widget-format.md` (leg 6).
  - **The prelude** applies the same rewrite to strings passed to:
    - the `Element.prototype` `innerHTML` and `outerHTML` setters (and `ShadowRoot.prototype.innerHTML` where it is separate);
    - `Element.prototype.insertAdjacentHTML`;
    - `Range.prototype.createContextualFragment`;
    - `Element.prototype.setHTMLUnsafe`/`ShadowRoot.prototype.setHTMLUnsafe` and `Document.parseHTMLUnsafe` where present.
  - **`document.write`/`writeln`** rewrite with **carry-over**. A trailing fragment that could be the start of a link tag (`<`, `</`, `<l`, `<li`, `<lin`, `<link` in any case, at the end of a call) is held back and prepended to the next call. On the next call's end, or at `document.close`, any held text that turned out harmless is flushed.
  - **`DOMParser.prototype.parseFromString`** rewrites with the prefix-aware pattern `/<(\/?)((?:[\w.-]+:)?)link(?=[\s/>])/gi` for **every** MIME type.
  - **`createElement`:** `Document.prototype.createElement` with a local name `link` (any case) and `createElementNS` with local name `link` (any namespace or prefix) return an inert element (`x-link`). `document.implementation.createHTMLDocument`/`createDocument` documents inherit the prototype wrappers (verify).
  - **The prelude's `MutationObserver`** removes any `HTMLLinkElement` it sees. It is **cleanup only**, not a control (the cycle-2 probe: an observer does not stop WebKit preconnect).
  - **The escape battery gains one case per route,** each with the link in `<head>` (where WebKit opens TCP):
    - parser `<link>` and `<LINK>`;
    - `createElement` (mixed case) and `createElementNS(xhtml,'link')`;
    - `innerHTML`, `outerHTML`, shadow `innerHTML`, `insertAdjacentHTML`;
    - `document.write` in one call **and split across two calls**;
    - `DOMParser` `text/html` plus `adoptNode`, and `application/xml` with a prefixed `h:link` plus `importNode`;
    - `createHTMLDocument` plus `adoptNode`, `createContextualFragment`, `<template>` content, `setHTMLUnsafe`.
  - **The WebKit allow-list entry is removed.** Every engine must read **0** TCP accepts.
  - **Falsified:** with the source rewrite removed, WebKit reads TCP > 0. With the `document.write` carry-over removed, the split-write case fails.
- [ ] **AC3 — Pause gate (DD8) with an initial state.**
  - **The `paused` option:** `App.ui.widgetFrame(opts)` takes `paused: true|false` (default false). `buildDocument` writes it into the base style as a custom property (`--frame-paused: 1|0`), as the theme mode is passed, and the gate reads it when constructed, before any model script.
  - **Starting paused:** the gate lets **exactly one** `requestAnimationFrame` round run (the callbacks queued before the first frame are called once, at the first frame), then holds. So a rAF-drawn first frame appears.
  - **While paused:**
    - `requestAnimationFrame` callbacks queue;
    - `setTimeout` callbacks that come due are deferred and run once on resume;
    - a `setInterval` that comes due one or more times runs **once** on resume (collapsed), then keeps its period;
    - `requestIdleCallback` and `scheduler.postTask` (where present) are deferred the same way;
    - `document.getAnimations()` is paused and resumed;
    - an injected `animation-play-state: paused !important` rule is toggled;
    - `AudioContext`/`webkitAudioContext` instances (wrapped constructors) are suspended and resumed.
  - **The clock:** `performance.now()` and rAF timestamps exclude paused time. `Date` is untouched.
  - **Never gated:** the prelude's own `message` listener and the heartbeat (captured timers).
  - **Page side:** `handle.postPause()` and `handle.postResume()` send `{t:'pause'}`/`{t:'resume'}`, queued until the frame has loaded, like `pendingTheme`.
  - **Contract tests, both engines,** using in-frame counters read through the frame (never `isActive`):
    - a rAF counter, a `setInterval` counter, a CSS animation and a Web Animation all stop on pause and resume with no jump in `performance.now()`;
    - a widget built with `paused:true` runs exactly one rAF round and no timers until resume;
    - the heartbeat keeps arriving while paused;
    - reassigning, redefining and deleting the wrapped functions does not lift the gate.
  - **Documented limits** (DD8, `docs/widget-format.md` in leg 6): a `MessageChannel` ping-pong loop, `requestVideoFrameCallback`, a busy loop, and `element.animate()` created after a pause keep running.
- [ ] **AC4 — Prelude pin and library rules.**
  - The prelude keeps the four-section order: capture (timers, gesture times) → neuter (RTC, History, `execCommand`, focus, link entry points, `createElement`) → pause gate (replacing `/* PAUSE-GATE */`) → handlers. `tests/test_widget_frame_prelude.py` is re-pinned with the new exact text and the section-order markers.
  - `test_source_is_appended_verbatim_even_when_hostile` is **renamed and inverted** to `test_source_is_appended_after_the_prelude_with_only_link_tags_rewritten`. It asserts that the body is the source with exactly the link rewrite applied, and nothing else changed. The "never parsed or rewritten" comment in `widget-frame.js` is updated.
  - **The prelude text is ES5** with no `=>`, backticks, `const` or `let`, no `App.` and no `//` inside the string (`test_ui_library_source.py` scans every line).
  - All of `test_ui_library_source.py`, `test_ui_guards.py`, `test_ui_control_inventory.py`, `test_ui_ownership.py`, `test_ui_emitted_classes.py`, `test_token_definitions.py` and `test_design_tokens_a11y.py` pass.
- [ ] **AC5 — Guard allowance.** `tests/_ui_guard_helpers.py` has `UI_DIR_SINK_ALLOWANCE: dict[str, int] = {"widget-frame.js": N}`, with a comment citing DD6 (frame-internal prelude, never run in the page). `test_ui_guards.py` asserts that the per-file count of `find_ui_dir_sink_tokens` hits **equals** N for that file and is 0 everywhere else. A tmp-dir probe proves that one more token or one fewer fails. **Falsified:** yes, via the probe.
- [ ] **AC6 — The `contracts-widget` lane.**
  - `scripts/run-tests.sh` gains `contracts_widget_pat=('test_ui_widget*')`, removed from `contracts_chat_pat`.
  - A budget-table entry, provisionally 300 s, re-measured at the closing gate.
  - The `contracts` alias covers four lanes, and `--help` lists the new lane.
  - `tests/test_run_tests_lanes.py` is updated: the lane list (18), pairwise disjointness, the union, the budget table, and the `contracts-chat` tuple without `widget_frame`.
  - CLAUDE.md's lane list and table gain `contracts-widget`.
  - Run `--lane contracts-widget` and `--lane contracts-chat`, and record both times.

## Verification Steps
- **Unit and static:** `.venv/bin/python -m pytest tests/test_widget_frame_prelude.py tests/test_ui_library_source.py tests/test_ui_guards.py tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_run_tests_lanes.py tests/test_app_frame_policy.py -x -q --timeout 60`, then `THE_ONE_TEST_NETNS=1 make test-unit`. One intermittent pre-existing failure is known and not this leg's: squawk 0344, `test_mcp_library_test_missing_values.py::test_cached_no_auth_posture…`.
- **Browser:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-widget -x` and `--lane contracts-chat -x`.
- **Falsifications:** AC1 (no gate; `isActive`-only), AC2 (no source rewrite; no carry-over), AC5 (the probe). Each is restored by editing.
- **Lint:** `ruff check` and `ruff format --check` over `the_one/ tests/ scripts/ evals/`.

## Implementation Guidance
1. **Read `widget-frame.js` fully first.** Keep the capture section first: capture originals (timers, rAF, `performance.now`, `postMessage`) before any wrapping, and add the gesture-time listeners there.
2. **Wrap with one helper** that `defineProperty`s with `writable:false, configurable:false` inside try/catch, so a missing API never aborts the prelude.
3. **Link rewrite:** one function used by `buildDocument` (on the page) and a copy inside the prelude string (in the frame). Keep the two regexes identical, and assert that in the node pin test by extracting both.
4. **Carry-over for `document.write`:** keep a pending string. On each call, `text = pending + arg`, find the longest suffix that is a case-insensitive prefix of `<link` or `</link` (it must start with `<`), hold it as `pending`, rewrite and write the rest. Flush `pending` (rewritten) at `document.close` and at the next call.
5. **Pause gate:**
   - one `paused` flag and a queue per kind;
   - on resume, drain rAF callbacks into the next real rAF, run deferred timeouts once, collapse intervals, resume animations and audio;
   - for the clock offset, accumulate paused milliseconds and subtract them in the wrapped `performance.now` and rAF timestamp;
   - the initial state is read from `getComputedStyle(document.documentElement).getPropertyValue('--frame-paused')` at gate construction. The base style is parsed before the prelude script, so it is available.
6. **The lane:** follow the `contracts-chat` split precedent (M31 F6 L04) in `run-tests.sh` and its tests. Keep `shared` as the complement.

## Edge Cases
- **A widget that calls `focus()` inside its own click handler:** a trusted click occurred under 1 s ago, so it is allowed (AC1(e)).
- **Keyboard-only use:** Tab into the frame, then Enter on a button that focuses an input. `keydown` is a trusted gesture, so it is allowed.
- **`document.write` after load** replaces the frame's document. The wrapped `write` still rewrites, but the new document has no prelude. Detect it: if `document.write` is called after `DOMContentLoaded`, make it a no-op. Document this in the format doc (leg 6).
- **The widget defines its own `link`-named custom element** (`x-link` collision): accepted. The inert name is reserved, which is documented.
- **The paused initial state while the theme changes:** the theme still applies.
- **A `setInterval` with a 0 ms period while paused:** it collapses to one run on resume.

## Files Affected
- `the_one/interfaces/web/static/js/ui/widget-frame.js`
- `tests/test_widget_frame_prelude.py` (re-pinned; one test renamed and inverted)
- `tests/browser/test_ui_widget_frame_contract.py` (new cases; the allow-list entry removed; split into more `test_ui_widget_frame_*` files if the file grows unwieldy)
- `tests/fixtures/widgets/escape.html` (the link route cases)
- `tests/_ui_guard_helpers.py`, `tests/test_ui_guards.py` (`UI_DIR_SINK_ALLOWANCE` and its probe)
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `CLAUDE.md` (the `contracts-widget` lane)
- `docs/ui-control-inventory.md` (the `widgetFrame` row: the new options and methods)
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md`

## Citation Audit
Verified on 2026-11-09 against the working tree (legs 1-2 landed, uncommitted):
- `js/ui/widget-frame.js` - 358 lines; `App.ui.widgetFrame = function (opts) {`; prelude sections and the `/* PAUSE-GATE */` marker; `pendingTheme` pattern - verified (design review)
- `tests/test_widget_frame_prelude.py::test_source_is_appended_verbatim_even_when_hostile` - exists and contradicts the AC2 rewrite - verified (design review)
- `tests/_ui_guard_helpers.py:181` `find_ui_dir_sink_tokens` (comments included); `SRCDOC_SINK_ALLOWANCE` (leg 1) - verified
- `tests/test_ui_library_source.py` - `_ES6` (`=>`, `class`, `let`, `const`, backtick), `_APP_GLOBAL`, `_FACTORY_LINE`; it scans every line, and `//` truncates only - verified
- `scripts/run-tests.sh` `contracts_chat_pat` (with `test_ui_widget*`, `test_ui_visual_notice*`); `contracts-chat` budget 150 s - verified
- WebKit preconnect opens TCP only for links in `<head>`; the two bypasses (split `document.write`, XML prefixed `h:link`) - verified by probe (`leg3rev/links.py`)
- Focus probes: a 5 s transient-activation leak with `isActive` alone; real click and Tab unaffected; `frame.evaluate` grants activation - verified by probe (`leg3rev/focus*.py`)
