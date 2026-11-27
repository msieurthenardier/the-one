# Leg: height-clamps-and-proof

**Status**: completed
**Flight**: [Usable at the smallest window](../flight.md)

## Objective
Make every page fully usable at 624×321 (short-window compaction and a scrolling rail, every scroll container clear of the GleepGlorp corner button, fixed widths clamped so nothing scrolls sideways down to 360px wide), prove the charter's criteria with tests in both engines and with the real WebKitGTK engine at the desktop minimum, and run the closing gate.

## Context
- Flight DD5 (short-window compaction under `(max-height: 479.98px)`, rules only where a measurement needs them; accepted exception: also applies to wide-but-short windows), DD6 (corner-button clearance on the element that actually scrolls, at every width; accepted exception), DD7 (width clamps that resolve to today's values at 768px and wider), DD9 (the probe at 640×360 and 624×321), DD10 (tests and lanes).
- Media queries use the classic `max-width` / `max-height` forms with `.98px` (leg 1 design review; flight DD2 annotated), not range syntax.
- Legs 1 and 2 are landed, uncommitted, in the working tree: one pane by intent below 768px (`js/shell-pane.js`, `data-pane`), panels in `fill` mode with `App.shellPane.setCovered`, `tests/browser/test_flow_narrow_layout.py` and `test_flow_narrow_panels.py` in the `layout` lane (71 passed at leg 2 end). Read the flight log's leg 1 and leg 2 entries.
- The operator approved the A2 board's compact chat (a 40px header, Send beside the input) as the target look at 624×321.
- This leg ends the autonomous legs; the HAT follows. Charter criteria 1–4 must be provable at the end of this leg.

## Inputs
- `css/chat.css` `.chat-instance .chat-header { height: 48px; ... }` (~:35); `css/components.css` `.ui-composer { flex-shrink: 0; padding: 12px 24px 20px; }` (~:3213), its telemetry (~:3214), attachments (~:3215), the message list padding (`chat.css` ~:299) and `.ui-message` padding.
- `css/components.css` `.ui-rail` (~:53-64; width now `var(--rail-w)`), rail items (~:72-91), footer (~:113-120); no `overflow` on the rail.
- `css/gleepglorp-drawer.css` ~:138-140: `gg-corner-on` reserves `padding-bottom: 72px` on `.studio-editor`, `.studio-section-content`, `.admin-content` only; `.tabpanel` has `padding: 16px 20px 80px` (`components.css` ~:1305) but a tabbed agent editor's scroller may be a different element.
- Fixed widths: `.modal-dialog` `min-width: 320px` (`components.css` ~:1756); the tool tile grid `repeat(auto-fill, minmax(280px, 1fr))` (~:2429); `admin.css` `.admin-form` `padding: 0 32px 40px` (~:26), `.settings-list` `padding: 0 32px` (~:83), `.settings-item` `margin: 24px 32px 0` (~:92); `studio.css` grid templates (`7rem 4.5rem minmax(0,1fr) auto` ~:400, `9rem 5.5rem ...` ~:1226) and `min-width: 160px` (~:517, :548); `.page-header` `padding: 16px 32px` (~:1209-1214); `.ui-facts` `fit-content(16rem)` (~:1655); `.app-flash` (~:11) has no max-width.
- `scripts/webkitgtk_probe.py`: `pin_environment()` (~:129; does not pin `GDK_SCALE`), `--setup-script` (must complete with exactly `true`), `window.__probeReport` echoed as `"report"` (~:367-368, :459), `--root-selector` polling (~:377), `window.set_default_size(1280, 900)` (~:344); refuses ports 8484/8485 and the default data dir. Its safety tests: find them with `grep -rn webkitgtk_probe tests/`.
- `scripts/ui_capture.py` `SIZES` (~:76-78: 1280×900, 1024×768); `tests/test_ui_capture_safety.py`.
- `Makefile` `gate` = `test-unit` then `test-browser` (`run-tests.sh --parallel 3`).

## Outputs
- Short-height and width-clamp CSS; the rail scrolls when it does not fit.
- Corner-button clearance on every real scroller.
- `scripts/webkitgtk_probe.py --window-size WxH`, `scripts/ui_capture.py` 640×360 and 624×321 sizes, with their safety tests.
- `tests/browser/test_flow_narrow_criteria.py` (new; `layout` lane glob) proving charter criteria 1, 3 and 4 across every destination and tab.
- Probe runs at 640×360 and 624×321 recorded in the flight log.
- A green closing gate.

## Acceptance Criteria
- [ ] **AC1 Measurement first.** Before writing height rules, measure at 624×321 (Chromium) an open chat with the composer's toolbar, telemetry and one attachment row shown: header height, composer height, transcript height, and how many 14px-body lines fit. Record the numbers in the flight log. Add only the compaction rules the measurement shows are needed for three full transcript lines; if none are needed for the chat, say so.
- [ ] **AC2 Short windows.** Under `@media (max-height: 479.98px)`: the chat header, message spacing and composer padding compact as AC1 requires (target: the A2 board, a 40px header, Send beside the input); the rail's items and footer tighten and the rail scrolls vertically (`overflow-y: auto`) when its content is taller than the window, so every rail item and Jump to stays reachable. At 1024×768 and 1280×800 nothing changes.
- [ ] **AC3 Corner-button clearance.** For every scroll container that can sit under `#gleepglorp-corner-button` (studio editors and section content, every agent editor tab panel, Library editors, admin content, Settings pages, list columns where the button overlaps them at narrow widths), the reservation sits on the element that actually scrolls. Test: at 624×321 and at 1280×800, the last interactive control in each, scrolled into view, is the element at its own centre point (`document.elementFromPoint`), with the corner button shown.
- [ ] **AC4 Width clamps.** The modal `min-width` becomes `min(320px, 100% - 24px)`; the tile grid `minmax(min(280px, 100%), 1fr)`; below 768px the 32px form, list, item and page-header paddings step down to 16px; the studio grids and `min-width: 160px` controls, `.ui-facts`, `.app-flash` and any other fixed width the AC5 test finds are clamped so they fit. At 768px and wider every clamp resolves to today's value (computed styles unchanged at 1024 and 1280 for the elements touched).
- [ ] **AC5 Charter criterion 1 at 624×321.** In Chromium and WebKit, for Chats with an open chat, Agents and every agent tab (General, Tools, Rules and notes, Routines, Self-configuration, and any other tab the editor shows), Library and every editor kind (providers, knowledge, MCP, connectors, secrets; a create form and an existing item), Settings and every page (GleepGlorp, Appearance, Date and time, Prompts, Encryption, Built-in tools and a tool's editor, Knowledge indexing): the visible pane is at least 360px wide, `document.scrollingElement.scrollWidth <= clientWidth`, no element inside the visible pane extends past the viewport's right edge, an open chat shows at least three transcript lines above the composer, and AC3's last-control check passes. Modals opened from these pages (the agent delete dialog, Jump to) fit the viewport.
- [ ] **AC6 Charter criterion 3.** At 480×321 and 360×640, every destination root and one item per destination: no sideways page scroll and no element past the right edge.
- [ ] **AC7 Charter criterion 4.** At 1024×768 and 1280×800 every existing lane passes (only the edits legs 1–3 recorded on purpose), and the new file's wide cases pass; the only visible differences are DD5's and DD6's accepted exceptions.
- [ ] **AC8 Probe.** `scripts/webkitgtk_probe.py` gains `--window-size WxH` (default `1280x900`, validated, covered by the probe's safety tests). Run against a dev instance (port 8490 or higher, scratch data dir under `$HOME`, started from a scratch cwd per CLAUDE.md, with the dev-mode `mock` provider seeded with an agent and a chat) at 640×360 and at 624×321, on an open chat and on the Settings nav: a setup script defines `window.__probeReport` as a getter returning `innerWidth`, `innerHeight`, `devicePixelRatio`, the visible pane and its width, transcript line count and `scrollWidth <= clientWidth`; `--root-selector` waits for a settled state (for example `.app-shell-row[data-pane="detail"]`). The report shows a viewport no larger than the window, a visible pane at least 360px wide and no horizontal overflow. The commands and JSON are recorded in the flight log; the dev instance is stopped by its recorded PID afterwards.
- [ ] **AC9 Captures.** `scripts/ui_capture.py` `SIZES` gains `640: 640×360` and `624: 624×321` (default `--widths` stays `1280,1024`); `tests/test_ui_capture_safety.py` covers them; one capture run at `--widths 624,640` across the four destinations in both themes succeeds into the scratchpad (for the HAT).
- [ ] **AC10 Closing gate.** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes (unit tier, then every browser lane three at a time), with any failure triaged per the flake rule and recorded. The `layout` lane's provisional budget is left provisional unless the run is a quiet-host `--parallel 3` reading (squawk 0259).
- [ ] **AC11 Records.** `the_one/agents.md` (the short-window rules, the clearance rule, the clamps, the probe option and capture sizes), the app guide if any visible behaviour it describes changed, and the flight log.

## Verification Steps
- AC1: the measurement script or test output, recorded in the flight log.
- AC2–AC6: `tests/browser/test_flow_narrow_criteria.py` via `PYTHON=.venv/bin/python THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 bash scripts/run-tests.sh --lane layout`.
- AC7, AC10: `make gate` as in AC10.
- AC8: the probe commands and JSON in the flight log.
- AC9: `tests/test_ui_capture_safety.py`; the capture run's summary line.
- Static guards: `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_css_layers`, `test_ui_ownership`, `test_ui_control_inventory`, `test_gleepglorp_guide`, `test_run_tests_lanes`.
- Squawk 0334: grep `tests/` for pinned composer, chat-header, rail, modal, tile-grid and padding values (including `tests/browser/design_tokens.py`) and run their lanes before the gate (at least `contracts-chat`, `contracts-overlay`, `contracts-controls`, `chats`, `chats-transcript`, `settings`, `settings-tools`, `agents`, `agent-tabs`, `library`).

## Implementation Guidance

1. **Measure (AC1).** Write the 624×321 measurement as the first test in the new file (it can stay as a regression assertion: ≥ 3 lines) and record the numbers.
2. **Short-height CSS (AC2).** In the layer that owns each rule (components for `.ui-composer`, `.ui-rail`; areas for `.chat-instance .chat-header` in `chat.css`), add `@media (max-height: 479.98px)` blocks. The A2 target puts Send beside the input: check whether the composer's toolbar row can move inline under the media query without JS (flex-wrap / order) before considering any JS change; if it needs JS, stop and report it (that would be a control change needing an inventory note). Rail: `overflow-y: auto` and tighter item padding/gap under the media query; keep focus rings visible (inset rings per the design system).
3. **Clearance (AC3).** Find each real scroller (computed `overflow-y: auto|scroll` with `scrollHeight > clientHeight`) on each page; move or add the reservation (`padding-bottom` or `scroll-padding-bottom` + a spacer) onto it under `.app-shell-row.gg-corner-on` in `css/gleepglorp-drawer.css`. Do not leave both the old and the new reservation on a nested pair (double space).
4. **Clamps (AC4).** Apply DD7's clamps; write the narrow padding step-downs under `@media (max-width: 767.98px)`; for each clamp, check the computed value at 1024 and 1280 is unchanged.
5. **Tests (AC5–AC7).** New `tests/browser/test_flow_narrow_criteria.py`: parametrise over destinations, tabs, editor kinds and Settings pages; seed with the existing seeders (an agent with routines and rules, a provider, a knowledge base, an MCP source, a connector, a secret, a chat with history); navigate through `_nav`, lists through `_lists`, chats through `_chats`; `engine_browser` + `credentialed_context` for both engines. Keep each test focused so a failure names the page.
6. **Probe (AC8).** Replace the hard-coded `set_default_size(1280, 900)` with `--window-size`; add its validation and safety-test cases; write the setup script under `scripts/probe/` (follow the existing `scripts/probe/gg-drawer/*.js` pattern); run it; record.
7. **Captures (AC9).** Add the sizes; extend the safety test; run once into the scratchpad.
8. **Gate (AC10).** Check `uptime` and `ps` first; run the gate in the background (`run_in_background`), wait for its completion notification, and append a progress line to the flight log at least once per hour of gate time (Mission 37 lesson: report at milestones during long gates).
9. **Docs (AC11).**

## Edge Cases
- **A composer with several attachment rows or a queued-message row at 321px:** the transcript may drop below three lines; the criterion is measured with one attachment row (AC1); more is accepted as the operator's choice to fill the composer.
- **A modal taller than 321px** (the agent delete dialog, Jump to): it must scroll inside itself or fit; it must not be cut off with its buttons unreachable.
- **Wide-but-short windows (e.g. 1280×450):** DD5's compaction applies (accepted); both panes visible.
- **Forced colours / reduced motion:** no new transitions; any new border or focus style keeps working under `forced-colors: active`.
- **The rail scrolling with keyboard focus:** a focused rail item is scrolled into view (browser default for focusable elements in an overflow container).

## Files Affected
- `the_one/interfaces/web/static/css/components.css`, `chat.css`, `admin.css`, `studio.css`, `gleepglorp-drawer.css` (and any other area stylesheet a clamp needs)
- `scripts/webkitgtk_probe.py`, `scripts/probe/<new>/*.js`, the probe's safety tests
- `scripts/ui_capture.py`, `tests/test_ui_capture_safety.py`
- `tests/browser/test_flow_narrow_criteria.py` (new)
- `the_one/agents.md`, the app guide if needed

## Citation Audit
Checked against the working tree on 2026-11-27 (legs 1–2 landed, uncommitted):
- `css/components.css` `.modal-dialog` `min-width: 320px` (~:1756), tile grid `minmax(280px, 1fr)` (~:2429), `.ui-composer` padding (~:3213) - verified
- `css/admin.css` `.admin-form` (~:26), `.settings-list` (~:83), `.settings-item` (~:92) 32px paddings - verified
- `css/chat.css` `.chat-instance .chat-header` `height: 48px` (~:35) - verified
- `css/gleepglorp-drawer.css` `gg-corner-on` reservation on three containers (~:138-140) - verified
- `scripts/webkitgtk_probe.py` `pin_environment` (~:129), `--setup-script` (~:150, validated ~:255-261), `__probeReport` (~:367-368, :459), `--root-selector` (~:377), `set_default_size(1280, 900)` (~:344) - verified
- `scripts/ui_capture.py` `SIZES` (~:76-78); `tests/test_ui_capture_safety.py` tests - verified
- `Makefile` `gate` / `test-browser` - verified
- `css/studio.css` grid templates (~:400, :1226), `min-width: 160px` (~:517, :548); `.page-header` (~:1209-1214); `.ui-facts` (~:1655); `.app-flash` (~:11) - from the code-study report, unverified line numbers (re-locate by grep)
- The real scroller of each agent editor tab panel - unverified (AC3 step 3 finds it)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
