# Flight: Chats, and closing every count to zero

**Status**: landed
**Mission**: [Every control comes from one library](../../mission.md)

## Contributing to Criteria
- [x] **Every kind of control is defined once in the library.** This flight adds the chat controls (`App.ui.composer`, `message`, `thinking`, `trace`, `telemetry`, `notice`), the badge live form (`App.ui.badge.live`), the model list (`App.ui.modelList`) and the note flag (`App.ui.noteFlag`). It closes the catalogue's last "not yet defined" rows: composer, message bubble, thinking indicator and trace shell, telemetry readout, and provider model picker. The retired "Data table" row moves to a new Retired table (D5). A unit assertion then fails on any control row that reads "not yet defined" (DD14).
- [x] **A change to one control reaches every place it appears.** `OWNERSHIP_ALLOWANCE` goes from 25 rows / 36 uses to **empty**, and so do `TOTAL_USES` and `MOVES`. Library options replace the 12 area-CSS rows in `chat.css` and `studio.css` (DD6). The chat JS rows go with the migration (legs 05a and 05b). The `icons.js` and `markdown.js` rows go in legs 03a and 07, and the aliases in leg 09a.
- [x] **No UI markup is built from HTML strings outside the markdown renderer.** `HTML_SINK_ALLOWANCE` goes from 5 (all in `chat.js`, all `innerHTML = ''` clears) to **empty** in leg 01. `markdown.js` loses its trusted icon seam (`injectIcon`'s SVG-string parse) with the copy-button migration (leg 07). Icons are placed only as nodes (`App.ui.icon`), and `App.icon` / `App.iconNode` are deleted.
- [x] **Each control's styles are owned by that control.** The chat rules for the new controls move from `chat.css` into owned sections of `components.css`. Dead families are deleted (`.test-result*`, `.msg-pending-approval*`, `.stub-*`, `.u-flex`, `.u-block`, the orphaned badge kinds per D6). The unlayered tail of `components.css` goes inside `@layer components`, with a unit check that keeps it there. The unused-selector report is reviewed at leg 09a and is empty apart from documented dynamic users.
- [x] **Every migrated surface looks as it did before, apart from approved differences.** Before and after captures cover the chat surfaces in every state, the model picker and the agent and provider editors (D7), in both themes, on one seed (DD12). The approved visible changes are the planning survey's items and the operator's two added features (DD7, DD8). None of them are found at the HAT.
- [x] **Every library control works by keyboard and by role in both engines.** Each new control and each new option gets contract tests in Chromium and WebKit. That includes the composer's Enter/Shift+Enter/IME rule, the reply Copy and its confirmation, and the model list's row actions and focus retention.
- [x] **The area code is organised by surface.** `chat.js` (2,399 lines) splits into seven modules and lands at about 600 lines (DD3). `provider-models.js` (996 lines; its allowance ceiling is 1,014) drops under 800 on the model list (D2, D8). Both line-guard allowance entries are removed. Every area entry module (`studio.js`, `chat.js`, `admin.js`) is then 800 lines or fewer.
- [x] **The catalogue documents every control** in its final state, with the Retired table.
- [x] **Existing behaviour holds.** The planning defects are fixed, each with a test that fails first (DD11). The unit, browser (every lane, both engines for the contracts) and lint gates pass. The mission-close UI behavior specs pass on a dedicated dev instance (DD15). Every testid survives or is recorded as retired.

---

## Pre-Flight

### Objective
Move the chat surfaces onto the control library and close every mission count to zero, so the mission's library criteria are met when this flight lands.
- **Chat:** split `chat.js` by surface, behaviour-free. Then build the composer, the message bubble, the thinking indicator, the trace and the telemetry readout as `App.ui` factories with update handles, and move the chat area onto them.
- **The library:** fix `App.ui.flash`'s container contract (the Flight 5 debrief's Recommendation 1). Add the options that retire the last area-CSS rows. Build the model list for the provider model picker, and the note flag.
- **Markdown:** negative security tests first, then close the link and code-fence holes, style headings and wide tables, and add strikethrough, task lists and bare-URL links. Move the code-block Copy onto the library.
- **Close the counts:** zero for the ownership allowance, the sink allowance, the retired-API aliases, the catalogue's "not yet defined" rows and the line-guard allowance; dead CSS deleted; docs and the catalogue in their final state.
- **Two features the operator added at planning (DD8):** a Copy button on every finished agent reply, and a notice when an agent stops at its step limit (today the chat goes silent).

Four changes reach beyond the chat area, and are named here so no lane is surprised:
- **The flash contract (DD5)** changes every `App.ui.flash` caller, about 30 sites across Library, Settings and Agents.
- **The searchList options (A9, squawk 0185)** change Jump to as well as the agent picker.
- **Sentence case (D7)** changes the agent and provider editors' labels.
- **The step-limit notice (F2)** changes the agent loop (`the_one/agent/core.py`), the WebSocket protocol, the connector inbound path and the CLI.

### Open Questions
- [x] Which presentation items are approved? → DD7 (operator, 2026-10-26, review page https://claude.ai/artifact/2TBSM1R3Aa3pGaU8uLPkUM): all of A1-A18; B1 (a), B2 (a), B3 (b), B5 (a), B6 (a), B9 (a), B13 (a); left as they are: B4, B7, B8, B10, B11, B12, B14.
- [x] Which functional defects ride in the flight? → all four (0.1-0.4; operator changed 0.2 and 0.4 from the recommendation): DD11, DD8.
- [x] Where do the chat controls live? → `js/ui/` as `App.ui.*` factories (operator, 2026-10-26).
- [x] How do library chat controls show markdown and clock times when `js/ui` may not call `App.markdown` or `App.time`? → DD4 (the area passes Nodes and labels).
- [x] Code-copy feedback? → D1 (a): the icon-only library Copy button gains a visible confirmation (the icon swaps to a check, tooltip "Copied", for 2 s). DD6.
- [x] What does "provider model picker" mean? → D2 (a): a presentational library model list; fetch, Pull and VRAM stay in the area. DD10.
- [x] Link policy for model replies? → D3 (a): reject backslashes and control characters; keep `/` and `#` links but require the same origin. DD9.
- [x] Squawk 0185? → D4 (a): keep the highlighted row by identity across refreshes. DD6.
- [x] The "Data table" catalogue row? → D5 (b): a new Retired table. DD14.
- [x] The seven badge kinds nothing produces? → D6 (a): delete them with their tokens and contrast rows. DD14.
- [x] Title-case labels on the agent and provider editors? → D7 (a): sentence case in this flight. DD7.
- [x] The line-guard allowance? → D8 (a): `provider-editor.js` (896) stays; the criterion names only the entry modules. `provider-models.js` drops under 800 under D2.
- [x] Reply Copy: what and where? → the markdown source of a finished agent reply, from an icon-only Copy in its attribution row (operator, 2026-10-26). DD8.
- [x] Step-limit notice: how far? → the web chat and connector chats, not stored in history (operator, 2026-10-26). DD8.
- [x] Squawk 0271 (the MCP editor test-file split)? → in groundwork (operator, 2026-10-26).
- [x] The OAuth fixture? → out of the flight, a separate sortie (operator, 2026-10-26).
- [x] A HAT and the behavior-spec sweep? → a HAT leg closes the flight. The closing leg runs the mission-close UI specs (operator, 2026-10-26). DD15.

### Design Decisions

**DD1: One flight, chat plus the closing counts** (mission plan; the Flight 5 debrief, Recommendation 4).
- **In scope:**
  - the chat surfaces and `markdown.js`;
  - the provider model picker;
  - the library options the last allowance rows need;
  - the flash contract;
  - the library squawks 0269, 0270 and 0185, chat's 0215 and 0249, lane squawks 0259 and 0271, and docs squawk 0272;
  - the planning defects (DD11), D7's sentence case and the two added features (DD8).
- **Out:**
  - the OAuth fixture (a sortie);
  - the knowledge search score floor and "Add file" (mission Known Issues);
  - squawk 0260 (the stdio cause text);
  - the remaining title-case and look-and-feel items on surfaces outside this flight (Flight 7, optional).
- **Size:** fourteen autonomous legs plus the HAT, after Architect cycle 1 split 03b, 05a and 09. That is under the 15-leg divert line. Design review may split a leg further, but never merges legs, and a split past 15 is raised with the operator.

**DD2: Groundwork first (leg 01).** No product behaviour change.
- **The capture tool** (`scripts/ui_capture.py`) gains the chat and model-picker surfaces on one seed:
  - mock providers for rich markdown, thinking, tool calls, streaming and a slow reply;
  - an unreachable `openai-compatible` provider;
  - an agent with a long name; sessions in every date group, a connector session with peers and an operator-only reply, a deleted-agent session and an empty one;
  - injected WebSocket frames for sign-in, and a stubbed Pull stream.

  The presentation survey's driver is the starting point. The FD copied it and both surveys out of the session scratchpad to `$HOME/.cache/the-one-ui-capture/m31-f6-planning/` (local, never committed). The before set is taken before any chat file changes.
- **The seed is pinned against the environment** (Architect cycle 1). The before set (leg 01) and the after set (leg 09b) are days apart. So the seed pins:
  - the page clock, with `page.clock.set_fixed_time` (not `install`, which would freeze the 16 ms streaming interval and the toast timers);
  - the time zone, in zone mode through `PUT /api/time-settings`;
  - every session's `updated_at` relative to that clock, so the Today and Yesterday groups and the clock times match;
  - the plan-token stamp.

  Both sets are taken on the same Playwright Chromium build.
- **The five sinks.** The `innerHTML = ''` clears (`chat.js:215`, `:685`, `:743`, `:924`, `:1647`) become `replaceChildren()`. At `:1647` the line is deleted, since the next line sets `textContent`. `HTML_SINK_ALLOWANCE` and `SINK_TOTAL` go to empty and 0, so the split moves no sinks.
- **Allowance bookkeeping.** `START_ROWS` in `tests/_ui_ownership_allowance.py` is rewritten to the Flight 6 start set (25 rows), and `SINK_START_FILES` to empty.
- **Lanes:**
  - a quiet-host `--parallel 3` re-measure (squawk 0259's rule);
  - `chats` splits into `chats` (state, list, picker, start, reconnect, drawer) and `chats-transcript` (composer, streaming, markdown chat, telemetry, attachments, queued, visibility, peer, thinking, time zone);
  - squawk 0271: `test_flow_studio_mcp_editor.py` splits by concern into files with a shared helper module, and `mcp` into two lanes.

  The new lanes' starting budgets come from the per-test junit times of the re-measure, by the measured-plus-25% rule. `scripts/run-tests.sh` (`LANE_LIST`, `CANON_LANES`, `BUDGET`, the patterns, the `chat` alias), `tests/test_run_tests_lanes.py` and CLAUDE.md's lane bullets and table move together. Squawk 0259 closes with this leg.
- **Squawk 0249** (test-only): stub `POST /api/oauth/start` in `test_second_auth_required_event_navigates_popup_to_consent_url`, in the falsely passing `test_popup_closes_on_auth_resolved_event`, and in `test_button_click_opens_popup_with_window_open_features`. A falsification check proves the sibling now fails when `auth_resolved` closes nothing.

**DD3: A behaviour-free split before any migration (leg 02).** `chat.js` follows the house pattern of studio (M31 F2) and the MCP editor (M31 F5):
- `App.chat.<name>.create(ctx)` factories sharing one `state` object, with call-time getters for modules created later;
- `ws` stays a closure variable exposed as `ctx.ws()`, because `connect()` reassigns it and tests call `area._ws()`.

The modules (code survey §1.3):

| Module | Owns | Est. lines |
|---|---|---|
| `chat/transcript.js` | the log: `addMsg`, the scroll pin, clear, `renderHistory`, streaming (pacing, the safe boundary, finalize), the thinking show/hide and model-loading row, trace shells, tool bubbles, delivered results | ~420 |
| `chat/sign-in.js` | popups, `loginFlows`, `sourceNames`, the login group render/reset, the `auth_*` handlers and the settle-close above the gate | ~330 |
| `chat/attachments.js` | staging, chips, caps, the file input | ~210 |
| `chat/hold-queue.js` | the one-slot client hold | ~90 |
| `chat/session-flow.js` | pick, open, reset, clear, the idle rules, hydrate, validate, heal, `startSend`, `applyStartFailed`, live refresh | ~380 |
| `chat/socket.js` | `connect`, `onopen`, `onclose`, the one `sock.onmessage` entry, the session frames | ~330 |
| `chat/turn-frames.js` | the gated frames (`user`, `assistant_chunk`, `assistant`, `thinking`, `tool_*`, `system`, `usage`, `done`, `cancelled`), delegating `auth_*` to sign-in | ~230 |
| `chat.js` (remains) | descriptor, `state`, construction, `renderPane`, `renderChatsList`, subscriptions, welcome, `send()`, composer and Stop wiring, the `_*` seams; `registerPickerHost` stays the last statement of `init` | ~600 |

- **The WebSocket three-phase order is kept exactly:**
  1. the session lifecycle frames, each returning;
  2. the global popup close for `auth_resolved` / `auth_failed`;
  3. the frame gate `if (!chatState.onFrame(data).accept) return;`, then the gated frames.

  There is one `sock.onmessage` entry (`test_oauth_modal_flow.py:51-70` calls it directly), and `boundOn = sock` runs first.
- **Code-text anchors are re-anchored to the new files, never relaxed:**
  - `tests/test_store_static.py:105-213`;
  - `tests/test_consent_link_static.py:20-23, 47-49`.
- **Bookkeeping:**
  - each moved ownership use gets a `MOVES` entry;
  - new script tags go between the chat modules and `areas/chat.js` (`test_index_asset_cache_busting.py:91-98`; there is no count pin and no Makefile change);
  - the `chat.js` line-guard entry is removed in this leg (the guard fails on a listed module at 800 or fewer).

**DD4: The library boundary and the update handles.** A `js/ui` file may touch no app global but `App.ui` and `App.icons` (`tests/test_ui_library_source.py:20`), and the contract harness loads only `icons.js` and `js/ui/*.js` (`tests/browser/_ui_engines.py:201-203`). So:
- **The area renders and the library places.**
  - The message bubble takes a `body` Node, and the streaming handle takes rendered fragments (`commit(fragment, consumed)`, `finalize(fragment)`).
  - The attribution takes a ready time label, with `setTimeLabel(text)`; the zone relabel stays an area sweep over the handles.
  - The telemetry readout takes its thresholds from the area, and the perf marks stay in the area.
- **Streaming pacing stays in the area transcript** (one transcript-wide 16 ms interval and chat-specific boundary logic). The handle exposes tail primitives only.
- **Every handle owns its effects:**
  - intervals stop on `destroy` and on disconnect (checking `isConnected` in the tick);
  - listeners are removed by `destroy`;
  - state is retained in the closure, never in DOM expandos (`root.__telemetry` and `el._dotTimer` go).
- **The factory shapes** (names may change at design review, behaviour may not):
  - `App.ui.composer(opts) → {el, input, setPlaceholder, setModel, setBusy, setBlocked, getValue, setValue, focus, slots: {telemetry, attachments, queued}, destroy}`. It owns Enter-sends, Shift+Enter newline and the IME rule (`isComposing` / keyCode 229), and the auto-fit. Its input id comes from `App.ui.util.uid()`, not the fixed `chat-composer-input`. `setBlocked` disables the input, Send **and Attach** (0.3), dims the box (B13) and is the single writer of the disabled state (today there are 11).
  - `App.ui.message(opts) → {el, appendText, commit, finalize, tail, destroy}`, plus `App.ui.message.attribution(opts) → {el, setTimeLabel, setCopy(text|null)}` (the F1 reply Copy, DD8).
  - `App.ui.thinking(opts) → {el, settle(text), destroy}`, which serves both "Thinking…" and "Loading model".
  - `App.ui.trace(opts) → {el, append(node), count(), destroy}` with `App.ui.trace.find(root, id)`, plus the thinking disclosure as a trace sibling or a `disclosure` variant.
  - `App.ui.telemetry(opts) → {el, update, setMax, reset, destroy}`.
  - `App.ui.notice(opts) → {el, set(body), destroy}` (added at Architect cycle 1). A transcript line in a `muted` or `danger` tone that takes a body **Node**. It serves B9's "Stopped." line, A4's agent error (the headline plus "Technical details") and F2's step-limit line with its settings link.
- **The streaming source is kept.** F1 copies the reply's markdown source, but `commitSafeBoundary` throws away committed text today (`chat.js:1043-1055`). The transcript keeps the full received source per reply and hands it to `setCopy` at finalize. On replay it hands over the stored content.
- **Class names: new `ui-*` classes, then a handover** (Architect cycle 1; the Flight 4 `toolTile` precedent, catalogue row 104). The ownership guard counts an owned class in any string literal outside `js/ui/` and in the area stylesheets (`tests/test_ui_ownership.py:178-189`, `:50`). So a control that owned today's names (`msg`, `composer-box`, `trace-shell`, …) would create allowance rows in every chat module until its consumer moves, and those rows would have no `MOVES` cover.
  - **Leg 04:** each control emits **new** `ui-composer*`, `ui-message*`, `ui-thinking*`, `ui-trace*`, `ui-telemetry*` and `ui-notice*` classes, with new owned rules in `components.css`. The `chat.css` rules stay untouched, because the old DOM is still live.
  - **Roles and states are modifiers:** `ui-message--user`, `ui-message--assistant`, `ui-notice--danger`, and so on. No control owns a bare role word (`thinking`, `user`, `assistant`, `tool`, `error`, `label`, `value`). Those words collide with WebSocket frame literals such as `data.type === 'thinking'` (`chat.js:2030`), and would make DD14's empty allowance unreachable.
  - **Area code never queries the new `ui-*` names.** It reaches nodes through the handles, `App.ui.trace.find` or testids.
  - **The consumer leg (05a, 05b or 05c):** the area moves onto the control, and the legacy `chat.css` rules and class names are **deleted**, not kept as hooks.
  - **Test locators are retargeted** to testids or the new `ui-*` classes in the same leg: about 32 `.msg`, 9 `.trace-shell`, 8 `.composer-box` and 7 `.telemetry-overlay` in `tests/browser`. Behavior specs that name a class are re-read in that leg.
  - **The contrast audits move with their rules:** `_TELEMETRY_RESTING_OPACITY` and the `.chip-remove` gate in `tests/test_design_tokens_a11y.py`.
- **The badge live form** is a separate entry point, `App.ui.badge.live(opts) → {el, set({kind, text})}`. Empty text hides the badge. `App.ui.badge`'s return type stays a node, because `list-pane.js:264` and `tile.js:348` expect one.
- **Testids stay caller-supplied literals,** so the registry extractor (`tests/_ui_guard_helpers.py:73-84`) still sees them. `test_flow_context_overlay_thresholds.py` moves from `App.chat.updateTelemetry` to the handle.

**DD5: The flash contract** (the Flight 5 debrief, Recommendation 1; reworked at Architect cycle 1). `App.ui.flash` always appends to one lazily created page region, `div.app-flash-region`, re-appended if detached (the pattern of `ui/confirm.js:86-96`).
- **The modal exception.** When an `App.ui.modal` is open, the toast goes into the topmost one, so a toast flashed from a modal is not drawn under the top layer.
  - The top dialog comes from modal's own stack, through a new `App.ui.modal.top()`, not from DOM order.
  - `App.ui.modal` removes its `<dialog>` on close (`ui/modal.js:67`, `:136-141`). So close re-homes any `.app-flash` child to the next dialog down, or to the page region. Without that, a toast flashed while the leave-guard `confirmDialog` or the Pull size confirm is open would die with it, which is the defect this fixes.
- **The newest toast replaces the one showing** (operator, 2026-10-26). Today two toasts overlap exactly at the fixed top centre; afterwards only the newest shows. The replaced toast's timers are cancelled.
- **The `container` option is deleted** from every caller (code survey §3.7: about 30 sites), **including the `App.showFlash` delegate** (`app.js:287-289`).
  - Removing the delegate's container is what moves markdown's copy toast out of the message log. So DD11 7 is fixed in this leg, and DD9's negative test 6 is written here as its failing-first test: "no `.app-flash` inside `.messages`".
  - The library copyButton's own visually hidden `role=status` span legitimately sits inside the bubble, so the test names `.app-flash` only.
- **A14's wording rides along,** since this leg touches every caller: "Agent saved", no "Error:" prefix, no exclamation mark.
- **No other visible change.** `.app-flash` is already fixed-position (`components.css:11`); B8 keeps it at the top centre.
- **Contract tests, both engines:**
  - a toast flashed and then the old container removed is still connected and visible;
  - a toast while a modal is open sits inside the dialog;
  - **a toast flashed in a modal survives that modal closing**;
  - a second toast replaces the first.

  `test_ui_feedback_contract.py:186-198` (`inHolder: True`) is retargeted.
- **Consumer tests:** "MCP server created" and "Connector created" survive their editor's remount, and the Flight 5 page-flash comments in the provider and MCP editors are simplified.
- **The leg is tier high** (a shared interface with existing consumers), and runs every editor lane.

**DD6: The library options that retire the remaining rows** (legs 03a and 03b). Each is a library option, never consumer CSS on library internals:

| Option | Retires | Leg |
|---|---|---|
| `App.ui.badge.live(opts) → {el, set({kind, text})}`, empty text hides (DD4) | `chat-pane.js` badge ×2, `agent-drawer.js` badge ×2 | 03a |
| `App.ui.copyButton` icon-only visible confirmation: the icon swaps to a check, tooltip "Copied" / "Copy failed", for 2 s. It is announced once, and a contract test proves this under a `role=log` ancestor (or the button takes a `liveEl` outside the log) | D1; used by the reply Copy (leg 05c) and markdown (leg 07) | 03a |
| `App.ui.noteFlag` (moved from `icons.js`, with a row and a contract test) | `icons.js` `App.iconNode(` | 03a |
| The unlayered `components.css` tail (`.note-flag*`, `.consent-link*`) moved inside `@layer components`, plus a unit check that nothing sits outside a layer | code survey D10 | 03a |
| `App.ui.searchList` `variant: 'chooser'` (the 40 px field, band padding, list hairline, empty hairline, zero gap); the meta truncates before the label (A9); the active row is kept by id across refresh (D4, squawk 0185) | `chat.css` `field-input`, `ui-search-list` ×1, `-field` ×2, `-listbox`, `-empty`; Jump to's copy of the gap rule | 03b |
| `App.ui.drawer` `reserveHeaderEnd: true` (overlay-mode padding) | `chat.css` `ui-drawer-header` | 03b |
| `App.ui.modal` `footerEnd: Node|string` | `agent-picker.js` `modal-dialog-footer-end` | 03b |
| `.ui-list-pane` base rule `flex: 1 1 auto`; `.badge` base `flex-shrink: 0` | `chat.css` `ui-list-pane`, `badge`; `studio.css` `ui-list-pane` ×2 | 03b |
| `.tabpanel` padding moved into the library rule (the only non-flush panels are the agent editor's) | `studio.css` `tabpanel` | 03b |
| a `section` / `editorShell` inset option set by the studio editors (an audit of the sections under `.area-studio` first; the `components.css:1457` `!important` goes). *Leg 03b design:* a default flip (the base takes 20px; `inset: 'none'` already exists) | `studio.css` `editor-section` | 03b |
| `textInput` / `select` `width: 'fill'`. *Leg 03b design:* no `fill`; `:45` is a no-op and is deleted; a `minWidth` option for `:472` | `studio.css` `field-input` ×2 | 03b |
| `App.ui.chip` `lead: Node` and `onRemove` / `removeLabel` (a library icon-only remove button) | `chat.js` `chip`; A6, A7 | 03c (consumers in 05a) |
| `App.ui.confirm` `onArmChange(armed)` (or a `listPane` row-action `confirm: {label}`) | `chat.js` `confirm-delete` ×2, the per-row MutationObserver | 03c (consumer in 05b) |
| `keyValueTable`: the remove button's name follows an unsaved key rename (squawk 0269); a re-baselining `setRow` clears the rename hint (squawk 0270) | squawks | 03c |

The remaining chat JS rows go with the migration:
- `chip` in 05a;
- `App.confirmDelete(` and `confirm-delete` in 05b (the Chats list delete);
- `App.consentLink.` ×4, `consent-link` and `btn-filled-primary` in 05b (sign-in).

Both `icons.js` rows go in 03a. `App.noteFlag` moves to `App.ui.noteFlag`, which removes `App.iconNode`'s last caller, and `App.iconNode` (the home of the `App.icon(` use) is then deleted. `markdown.js`'s rows go in leg 07. The `App.icon` definition itself is deleted with the other aliases in 09a.

**DD7: Visible changes, and the ledger.**
- **The presentation survey** ran at planning: 242 screenshots of the chat surfaces, the model pickers and the toasts, at 1280 and 1024 in both themes. It found 4 functional defects, 18 obvious items (A1-A18) and 14 taste items (B1-B14). Evidence: the review page and `f6-presentation-debt.md` (FD scratchpad). The summary is in the flight log.
- **Approved by the operator** (2026-10-26):
  - **all of A1-A18**:
    - A1: markdown headings on the type tokens.
    - A2: the code-block Copy on the library (D1).
    - A3: "Sign-in needed" and "Sign in to {server}" on a library button.
    - A4: an agent error as a danger-tone headline with "Technical details".
    - A5: the deleted-agent banner on `App.ui.banner`.
    - A6 and A7: the library remove buttons; "Queued" without the colon.
    - A8: "Thinking…" in sentence case.
    - A9: the search-list meta truncates first.
    - A10: model ids in mono.
    - A11: the VRAM value in plain secondary text.
    - A12: "Use Pull to download one."
    - A13: the app's own Pull wording plus the percentage.
    - A14: "Agent saved", no "Error:" prefix, no exclamation mark.
    - A15: timestamps at AA contrast.
    - A16: the platform's display name.
    - A17: "Agents" linked inside the sentence.
    - A18: the 2 px telemetry focus offset.
  - **B1 (a):** wide markdown tables scroll sideways in their own wrapper.
  - **B2 (a):** the thinking disclosure always sits above the reply it belongs to. This is a real reorder: the `thinking` frame arrives after the answer (`chat.js:2030-2038`). So the transcript inserts the disclosure before the bubble of the reply it belongs to, anchored on that reply's node, live and on replay.
  - **B3 (b):** the trace keeps its mono voice, with the library chevron and "Tool activity · 4".
  - **B5 (a):** "Operator only" as a small chip.
  - **B6 (a):** the Chats empty state's text column is centred.
  - **B9 (a):** a muted "Stopped." line after Stop, plus "Queued message discarded." when one was held.
  - **B13 (a):** the blocked composer is dimmed with the disabled tokens, and Attach is disabled too.
  - **D7 (a):** sentence case for the agent editor's labels ("LLM configuration", "System prompt", "Chat history retention (days)", "Max iterations", …) and the provider editor's ("Context window", "Reasoning effort", the "OpenAI-compatible" type option). The full list is fixed at leg 03c's design review from a grep.
  - **Left as they are:** B4, B7, B8, B10, B11, B12 (the "no tools" chip keeps its danger outline), B14.
- **Every leg appends its visible differences to the ledger** (flight log, numbered rows). The HAT walks the ledger.
- **A ledger criterion that describes a look carries a derived-relationship or degenerate-input test.** For example:
  - the reply Copy copies exactly the stored markdown;
  - the Chats row's platform badge reads the platform's display name from one table ("Discord" for `discord`), not the raw slug;
  - a 200-character model id truncates in the meta, not the label;
  - an empty reply has no Copy.

**DD8: New behaviour approved at planning.** These are features and not fixes, each decided by the operator on 2026-10-26, so none of them is a HAT surprise.
- **F1: Copy on every finished agent reply.**
  - An icon-only library Copy sits in the reply's attribution row, beside the time, using D1's confirmation.
  - It copies the reply's **markdown source**: the text the model wrote and the server stores, not the rendered text.
  - It appears once the reply has finished streaming, and never on user, tool, system or thinking content.
  - It reads the text the area hands the handle (`setCopy(text)`); a reply with empty text has no button.
  - On a history replay it reads the stored content.
  - Tests:
    - the clipboard text equals the stored message content, for a reply with a code fence and a table;
    - no Copy while streaming;
    - one Copy per reply after finalize;
    - its name is "Copy reply".
- **F2: A notice when an agent stops at its step limit.**
  - **Today:** `Agent._run_iterations` (`the_one/agent/core.py:286`) simply leaves its `while self._remaining_iterations > 0` loop. Nothing is yielded and the turn ends as if complete.
  - **The flag's lifecycle** (pinned at Architect cycle 1):
    - The agent keeps a `stopped_at_step_limit` attribute. It is **cleared** at the entry of `step()`, of `resume_after_auth()` (including its re-pause return) and of `reset()`.
    - It is **set** only when the `while` in `_run_iterations` ends because the budget ran out. It is never set on a `return`: a text answer, the degraded backstops (DD-C, DD-C2) or an auth pause. It is set as state before the generator returns (squawk 0219's rule).
    - A last iteration that produced text **and** tool calls counts as exhausted, since the model asked for more work.
    - `resume_after_auth` with a zero remaining budget (`core.py:563-569`) reports exhaustion the same way.
    - Each interface reads the flag after its `async for … agent.step(…)` (or `resume_after_auth`) loop.
  - **The web frame is a contract**, since a behavior spec depends on it:
    - The frame is `{"type": "step_limit", "steps": n}`. It is session-scoped and frame-gated like the other turn frames.
    - It is sent **immediately before `done` in each non-paused branch**. On the step path (`app.py:2299`) that is after `_save_session_to_db` (save `:2534`, `done` `:2568`). On the resume path (`:2621`) it goes inside `if not re_paused:`, before that path's `done` (`:2643`) and before its later save (`:2666`). The resume path's save is not reordered.
    - It is **broadcast-only through `_send_to_session`, never `add_event`**. So it is not in the in-memory `Session.history` (`app.py:743`, `add_event` `:766`) that every `session_joined` replays (`:1865`), and not in the DB. The model never sees it, and a reload or a second socket shows nothing.
    - `the_one/agents.md`'s session-scoped frame list and WebSocket event table gain it (DD14).
  - **The web chat** renders the frame as an `App.ui.notice` line (DD4) after the reply: "Stopped: this agent used its {n} steps for this message. Send another message to continue, or raise Max iterations in its settings."
    - "Max iterations" links to `#agents/{name}` when the agent has a stored record.
    - For the default agent with no record (`app.py:1940-1943`), or a deleted agent, it is plain text.
    - A connector turn shown in an open web chat gets only `session_updated` and a re-join, so the web view shows no notice for it. That follows from "not stored" and is expected at the HAT.
    - When `n` is below 1 (`max_iterations` has no lower bound, `config.py:132`), the count is left out: "Stopped: this agent reached its step limit for this message. …".
  - **Connectors** (`connectors/inbound.py:472`): the neutral line "(Stopped: reached its step limit for this message.)", with no mention of settings, because peers may read it in a public channel (operator, 2026-10-26).
    - It is sent **always**, even when the agent already posted through `send_to_platform_channel` (the auto-delivery skip rule, `inbound.py:293-302`).
    - It goes after `_auto_deliver_reply`, through the same outbound client. When `client_for()` is `None`, it is logged and dropped, as auto-delivery is.
  - **The REST `/api/chat` result** (`app.py:3046`) gains an additive `step_limit: true` key when the limit was hit. **The CLI** (`interfaces/cli.py`) prints the web wording without the link.
  - **The leg is tier high:** the agent loop, the WebSocket protocol, connectors.
  - **Tests:**
    - unit: the flag's lifecycle on a `FakeLLM`. A tool call on every iteration exhausts `max_iterations=2` and sets the flag; a normal finish, a pause and a resume that finishes do not; the next `step()` clears it; a resume with a zero remaining budget sets it;
    - the WebSocket frame order (`step_limit` before `done`) on both the step and the resume path;
    - a second socket joining after `done` gets no `step_limit` in `session_joined.history`;
    - the stub connector's outbound gets the line once, including after a `send_to_platform_channel` turn;
    - the REST key, and the CLI line;
    - a browser test with the mock provider's `tool_calls` on a harmless real tool (`current_time`, not `continue` or an unknown tool) shows the notice and its link.
- **0.4: Strikethrough, task lists and bare URLs in markdown** (operator: fix in this flight).
  - `~~text~~` becomes `<del>`.
  - `- [ ]` and `- [x]` items become list items with a disabled checkbox carrying the checked state and an accessible name from the item text.
  - Bare `http(s)://` URLs become links. Trailing punctuation (`.,;:!?)` and an unbalanced `)`) stays outside the link, and every autolink goes through `safeHref`.
  - Negative cases: a bare URL inside link text, inline code or a fence is never autolinked, and `~~` inside a code span never strikes.
  - Each comes with the negative tests of DD9. The markdown invariant guard (`test_markdown_no_html_string_invariant`, literal `createElement` args) stays green; `del` and `input` are literal tags.
- **B9: the "Stopped." line** (above) uses the same notice control as F2.

**DD9: Markdown security, tests first** (leg 07; code survey §4).
- **Before any change, add the negative tests**, each failing today where marked:
  1. backslash and whitespace paths (`/\evil.example`, `/<TAB>/evil.example`, `/<LF>/evil.example`, `\/evil.example`) must not resolve off-site — **fails today**;
  2. ```` ```js is-hidden ```` must give `<code>` at most one class — **fails today**, and retargets `test_markdown.py:948`;
  3. nested links (`[a [b](https://x)](https://y)`) must give no `a a`;
  4. attribute injection in an href stays one attribute;
  5. `javascript:` with entities or percent-encoding renders `#`;
  6. no `.app-flash` inside `.messages`. This one is written and fixed in leg 03a, where dropping the delegate's container fixes it (DD5); leg 07 keeps it green with the library button;
  7. autolinks (0.4): `javascript:`-looking bare text is never linked, and a bare URL followed by `).` links only the URL.
- **`safeHref` (D3 (a)):**
  - reject any `\` and any C0 control, tab or newline anywhere in the href;
  - keep `http:`, `https:`, `mailto:` and `tel:`;
  - keep root-relative and `#` links only when `new URL(href, location.href)` has the page's origin;
  - everything else becomes `#`.
- **Code-fence language:** the first token only, `[A-Za-z0-9_+#.-]{1,32}`, else no class.
- **The code-block Copy** becomes `App.ui.copyButton` icon-only (A2, D1). `injectIcon` and its SVG-string parse go. `test_markdown.py:654-680` (the exact copy-button markup) and `:809-829` (the "Copied!" toast) are retargeted to the library button's contract.
- **A1:** h1-h6 inside a reply map to the type tokens, capped so a reply heading is never larger than the app's page heading.
- **B1:** a table renders inside an `overflow-x: auto` wrapper.
- **The behavior spec `discord-markdown-links`** (draft) is re-read for the root-relative change.

**DD10: The model list** (D2 (a); leg 08).
- **`App.ui.modelList(opts) → {el, reconcile(sections), setRowBusy(name, busy), setRowError(name, msg), focusRow(name), destroy}`.** Keyed rows with a status dot (`App.ui.status`), name (mono, A10), capability chips, size and row actions (Load, Unload, Delete armed through `App.ui.confirm`). It retains focus across reconcile.
- **Fetch, Pull, the pull select, VRAM and the size confirm stay in the area.**
- **`provider-models.js`** (996 lines) splits into the basic list and the Ollama panel on the control, each under 800. The line-guard entry is removed. `App.studio.renderCapabilityChips` (also used by `agent-model-picker.js:58`) moves to a shared spot or onto the control.
- **The `.admin-pf-model-*` classes** become owned `ui-model-*` classes. The `.admin-pf-*` layout classes of the panel itself stay area layout.
- **Ledger:** A10, A11, A12, A13, A17. B12 is kept unchanged.
- **The catalogue row "Provider model picker"** becomes `library: App.ui.modelList`.

**DD11: The defects found in planning are fixed, test first.** Each gets a test that fails on today's code, then the fix:
1. **Focus is lost after an agent pick** (0.1): after a pick, focus goes to `chat-input` (leg 05a). The picker returns focus to its opener in `onClose` (`agent-picker.js:190-199`); the pick then moves it on.
2. **An OpenAI-compatible provider's errors name Ollama** (0.2). `openai-compatible` maps to `OllamaProvider` (`the_one/llm/registry.py:22`), and the `ollama_api.py` errors hard-code "Ollama" (from `:101`). Errors name the configured provider type's label instead, passed through the factory to the provider, and a test drives an `openai-compatible` provider at a dead port (leg 06).
   - Two probes are already known to call the Ollama-only `/api/show` on an `openai-compatible` provider, and both fail softly: `supports_tools` → `get_model_capabilities` (`ollama_provider.py:294-302`; the failure is swallowed in `ollama_api.py:215-218`) and `_resolve_max_context_tokens` (`ollama_provider.py:264-279`). They stay as they are; 0.2 is a wording fix.
   - Anything beyond those two probes is raised as its own question.
3. **A deleted agent's chat keeps Attach enabled** (0.3), and logs a 404 for its context window (leg 05a; the 404 is skipped or handled quietly, without a console error).
4. **The "Loading model" interval leaks** on any log wipe, and ignores reduced motion (code survey D1; leg 05c, `App.ui.thinking`).
5. **A late context-window response sets the wrong chat's maximum** (D5; leg 05c, keyed on the session with `App.ui.util.latest()`).
6. **Deleting a chat while the socket is down leaves the row armed** and silent (D6; leg 05b: revert the arm and say why).
7. **The code-copy toast lands in the message log** (D4; leg 03a, DD5).
8. **The markdown link escape and the fence class injection** (D2, D3; leg 07).
9. **Squawk 0215:** a failed `/api/oauth/start` leaves a stale sign-in block (leg 05b, `abandon()` resets the group).
10. **The flash container defect** (DD5; leg 03a).
11. **The unlayered CSS** (D10; leg 03a).

**DD12: Captures.**
- **The before set** is taken in leg 01, the after set in leg 09b, on the DD2 seed with its pinned clock, zone and Chromium build.
- **Each set** covers every chat state, the model pickers, the agent and provider editors (D7) and a toast from each editor, at 1280 and 1024 in both themes.
- **Each pair is compared** with PIL `ImageChops`, and each difference is mapped to a ledger row. Separately, each mapped difference is judged against what its row promised (Flight 4 debrief, Key Learning 3).
- **Captures are local evidence** and never committed.

**DD13: Standing leg rules** (Flight 5 DD10, plus the Flight 5 debrief). Every leg spec carries these:
- **No consumer CSS on library internals and no `[data-testid]` style hooks.** A needed look becomes a library option.
- **Mind the cascade layers.** A rule moved from `chat.css` (`@layer areas`, `.area-chat`-scoped) into `components.css` (`@layer components`) loses a layer and a class of specificity. Each move gets a computed-style check under an `area-chat` ancestor, and the leg's capture diff.
- **What the old control gave for free:** list it and keep each item or record a ledger row. Examples:
  - the textarea's IME guard;
  - the native `<details>` find-in-page open;
  - `aria-keyshortcuts`;
  - the queued chip's keyboard cancel;
  - the scroll pin;
  - the log's `role=log` additions.
- **Derived-relationship or degenerate-input criteria** on every relabel or restyle (DD7).
- **Append to the ledger,** with an in-progress log line at each internal checkpoint.
- **Retarget pins, never relax them.**
- **The side-effect inventory** (code survey §5) is checked in every leg that moves an effect.
- **Grep after every move.** Re-run the line guard, and `git grep` the moved paths and deleted classes across `tests/`, `scripts/`, `Makefile`, `docs/` and `tests/behavior/`. Run the owning lane for each deleted class, and paste the hits into the leg.
- **A new browser test file gets its lane** in `scripts/run-tests.sh`. Otherwise it lands in `shared`.
- **`provider-editor.js` has zero line headroom** (896 lines against an 896 ceiling): any leg that touches it (03a, 03b, 03c, 08) must not add net lines.
- **Every fix pass runs `make test-unit` and its owning lanes before signalling,** whether a review fix, a HAT fix or a post-gate change (Flight 5 debrief, Recommendation 3; a repeat finding).
- **A HAT-fix Developer brief** states "a library option, never consumer CSS on library internals" up front.

**DD14: Closing the counts** (leg 09a). The allowances only shrink, and here they reach zero.
- **`OWNERSHIP_ALLOWANCE`, `TOTAL_USES` and `MOVES` are empty.** The guard machinery stays, so any new use fails.
- **`HTML_SINK_ALLOWANCE` is empty** (since leg 01), and `test_chat_area_has_no_baselined_sink`'s docstring is updated.
- **The aliases are deleted** with `_ALIAS_LINES` (`tests/test_ui_library_source.py:29-34`) and their test call sites:
  - `App.confirmDelete`;
  - the `App.consentLink` alias;
  - `App.showFlash`;
  - `App.icon` (`App.iconNode` is already gone in 03a);
  - `App.escapeHtml`, `App.escapeAttr`;
  - the dead `icon:` fields of the three `registerArea` descriptors.

  `App.icons` (the table) stays.
- **The catalogue:**
  - no row reads "not yet defined";
  - `tests/test_ui_control_inventory.py` gains that as an assertion;
  - the "Data table" row moves to a new Retired table (D5);
  - the "Owned by controls built later" table loses `test-result`.
- **Badge kinds (D6).** `connectors`, `execution`, `time`, `web`, `filesystem`, `approved` and `dismissed` are deleted, after a grep confirms no producer, with:
  - their tokens and contrast rows;
  - `BADGE_KINDS`;
  - the `test_ui_badge_kinds.py` pin, re-counted.
- **Dead CSS:**
  - `.test-result*`;
  - `.msg-pending-approval*`, with its a11y row `test_design_tokens_a11y.py:624-628`;
  - `.stub-*`;
  - `.u-flex`, `.u-block`.

  `scripts/unused_selectors.py` learns the `ui-disclosure--` dynamic prefix. The report is reviewed and recorded in the flight log.
- **Docs to their final state:**
  - `the_one/agents.md` "Control library (`App.ui`)", the chat sections, `rescueFlashes` and the other drift (code survey D14);
  - `the_one/agents.md`'s WebSocket event table and session-scoped frame list, with `step_limit` (DD8; written in leg 06, checked here);
  - CLAUDE.md's control-library totals, chat sections and lane table;
  - the catalogue, including its header prose on statuses (`docs/ui-control-inventory.md:23-36`);
  - squawk 0272 (the lane-time sentence and four patterns).

**DD15: Tests, lanes and specs.**
- **Lanes** (budgets at planning; F5 L12 measurements):
  - `chats` (388/450 s) is split in leg 01 before any chat test is added;
  - a `contracts-chat` lane is created in leg 04 with the first chat-control contract file (a lane must have files), so `contracts-controls` (365/480) does not grow past budget. Its files are subtracted from `contracts-controls`' complement set and added to the `contracts` alias, and it runs under `THE_ONE_REQUIRE_WEBKIT=1`;
  - `contracts-controls` and `contracts-overlay` carry the option tests of legs 03a-03c;
  - `providers` carries the model list and D7;
  - `agents` carries D7 and the flash consumers;
  - `shared` carries `test_markdown.py`, `test_oauth_modal_flow.py` and `test_flow_jump_to.py`;
  - every editor lane runs for DD5.

  Re-budget at leg 09b by the 15% and 1.3x rules, from quiet-host readings only.
- **Batch mode, with the HAT at the end** (the operator's standing preference). Batches:
  - B1 = 01-02;
  - B2 = 03a-03c;
  - B3 = 04, 05a, 05b, 05c;
  - B4 = 06, 07, 08;
  - B5 = 09a-09b.

  Each leg runs its own lanes plus the unit guards. Each batch end greps for deleted selectors and classes and runs their lanes. The full gate runs at leg 02 (after the split), at leg 09b and after any HAT code change.
- **Fixed waits:** no new test uses a fixed `wait_for_timeout` to prove that nothing changed. It holds the request with `page.route`, releases it, waits for it, then asserts.
- **Behavior specs:**
  - **a new spec, `agent-step-limit-notice`,** is drafted in leg 06 and run in leg 09b. On a dedicated dev instance, a mock provider calls `current_time` on every reply, with `max_iterations` 2. The spec checks:
    - the web notice and its link;
    - the stub connector's outbound line (`THE_ONE_STUB_TEST_ENDPOINT=1`);
    - that a reload, and a second browser context, show no notice;
    - that the stored history carries no notice, read through `GET /api/chat/sessions/{id}` (`api.py:5088-5105` returns `messages`);
  - **the mission-close sweep in leg 09b:** `chat-roundtrip`, `start-a-chat`, `list-and-detail`, `workbench-navigation`, `shell-navigation-smoke`, `jump-to-palette` and `studio-agent-crud`. Steps that quote changed text are re-authored deliberately in the leg that changes it, never at the run;
  - **re-authored in the leg that changes their surface:**
    - `jump-to-palette` (03b, D4);
    - `studio-agent-crud` and `agent-retention-setting-roundtrip` for A14's "Agent saved" in 03a (leg 03a design review); then `studio-agent-crud`, `agent-retention-setting-roundtrip` (it names "Max Iterations" in its intro and step 1) and `save-preserves-config` (steps 5-6, "Reasoning Effort") in 03c, for D7;
    - `vision-round-trip` (05a, the attachment chip);
    - `start-a-chat` (05b, the delete arm, step 14);
    - `chat-loop-hang-and-cancel` (05c, B9);
    - `extended-thinking-tool-turn` (05c, B2/B3);
    - `stub-connector-round-trip` step 7 (`.msg-operator-only`, `.msg-attribution.from-agent`) and `agent-governance-and-search` step 8 (`.telemetry-overlay`, `.context-bar.warn`, `.t-ctx-pct.warn`) in 05c, for the deleted classes;
    - `discord-markdown-links` (07).

### Citation Audit

Verified against the working tree at `2e82aaa` (FD read and grep, 2026-10-26, plus the code survey's citations, spot-checked):

| Citation | Status |
|---|---|
| `tests/test_ui_library_source.py:20` — `_APP_GLOBAL = re.compile(r"\bApp\.(?!ui\b\|icons\b)\w+")` (DD4) | verified |
| `tests/test_area_module_size.py:24-28` — `ALLOWANCE = {"chat.js": 2399, "studio/provider-models.js": 1014, "studio/provider-editor.js": 896}` (DD3, DD10, D8) | verified |
| `js/areas/chat.js` — the five clears at `:215`, `:685`, `:743`, `:924`, `:1647` are the only sinks in the chat area (DD2) | verified (grep) |
| `tests/test_ui_guards.py` — `SINK_TOTAL = 5`, `SINK_START_FILES = {"areas/chat.js", "areas/studio/mcp-server-editor.js"}` (DD2) | verified |
| `tests/_ui_ownership_allowance.py` — 25 rows; `START_ROWS` still "as of M31 F5 L01" (DD2, DD6) | verified |
| `js/ui/feedback.js:128` — `App.ui.flash = function (message, opts)`; the container defaults to `document.body` and the toast is appended to it (DD5) | verified |
| `js/app.js:288` — `App.ui.flash(msg, { error: !!isError, container: container \|\| document.body })` (the `App.showFlash` delegate) | verified |
| `js/markdown.js:104-122` — `safeHref` rejects `^\s*\/\/`, then accepts `^(https?:\|mailto:\|tel:\|\/\|#)` (DD9) | verified |
| `js/markdown.js:621-632` — `injectIcon` reads `window.App.icon(name)`; `:793-804` — three `App.showFlash(wrap, …)` calls (DD9) | verified |
| `the_one/agent/core.py:286-287` — `while self._remaining_iterations > 0: self._remaining_iterations -= 1`; the loop exits with nothing yielded when the budget runs out (DD8 F2) | verified |
| `the_one/interfaces/web/app.py:2299` (`async for msg in session.agent.step(`), `:2621` (`resume_after_auth`), `:2568` and `:2643` (`{"type": "done"}`) — the web turn paths (DD8 F2) | verified |
| `the_one/connectors/inbound.py:472` — `async for _ in agent.step(envelope.text):` (DD8 F2) | verified |
| `the_one/llm/registry.py:22` — `"openai-compatible": "ollama"`; `the_one/llm/ollama_api.py:101` — `ConnectionError(f"Cannot connect to Ollama at {url}: {exc}")` (DD11 2) | verified |
| `js/ui/consent-link.js:118` — the `App.consentLink` alias; `chat.js:1288, 1401, 1424, 2110` call it (DD14) | verified (code survey; grep count 4 matches the allowance) |
| `tests/browser/test_oauth_modal_flow.py:188-230` — the flaky test clicks "Log in" with no `/api/oauth/start` stub (squawk 0249) | verified (code survey); the root cause is confirmed by one run in leg 01 |
| `the_one/interfaces/web/app.py:743` — `history: list[dict[str, Any]]` on `Session`; `:766` `def add_event`; `:1865` `"history": session.history` in `session_joined` (DD8 F2: broadcast-only) | verified (Architect cycle 1, FD re-read) |
| `js/ui/modal.js:67` — "The `<dialog>` is created on open() and removed from the DOM on close"; `:136-141` splices the stack and removes the dialog (DD5's re-home) | verified |
| `the_one/connectors/inbound.py:293-302` — auto-delivery returns early when the agent already sent through `send_to_platform_channel` (DD8 F2's "always") | verified |
| `the_one/llm/ollama_provider.py:264` `_resolve_max_context_tokens`, `:294` `supports_tools`, `:301` `ollama_api.get_model_capabilities` — the two known Ollama-only probes (DD11 2) | verified |
| `tests/test_ui_ownership.py:178-189` (a token in any JS string literal outside `js/ui/` counts), `:50` (`CSS_FILES`) — the reason for DD4's `ui-*` names | verified (Architect cycle 1) |

### Prerequisites
- [x] The operator's decisions on the review page and the three feature questions (2026-10-26).
- [x] The branch `flight/06-chats-and-closing-the-counts` is created from `main` (`3b3d42a` or later) at flight start. Sortie 06 (#329, `3b3d42a`) landed after planning. The FD checked it against the plan: the counts are unchanged (25 rows / 36 uses, 5 sinks); it does not touch `chat.js` or the chat area; `provider-editor.js` is still 896 lines; and the `studio.css` rows of DD6 are unchanged (it deleted only `.agent-load-error`).
- [x] WebKit userland and `THE_ONE_TEST_NETNS=1` work. Re-verify at the start of every leg that runs browser tests.
- [x] The before captures are taken in leg 01, before any chat file changes.
- [x] A quiet host for leg 01's re-measure (no other test process; 1-minute load below about 1.0).
- [x] The stub connector seam (`THE_ONE_STUB_TEST_ENDPOINT=1` with `THE_ONE_DEV_MODE=true`) works on a scratch instance, for the F2 spec (checked in leg 06).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified (the branch, WebKit and the quiet host are verified at flight start and per leg)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Groundwork and the split first,** with no behaviour change. The sinks reach zero before the split.
2. **The library pieces next:**
   - the flash contract and the feedback options (03a);
   - the layout options (03b);
   - the chip and confirm options, the key-value squawks and D7 (03c).

   Each is contract-tested in both engines before its consumer moves.
3. **The chat controls** are built and contract-tested on their own, under new `ui-*` class names (04).
4. **Then the chat area moves onto them** in three slices, each deleting the legacy classes it hands over:
   - the composer side (05a);
   - sign-in and the Chats list delete (05b);
   - the transcript (05c).
5. **The server-side turn-end messages** (06): the step-limit notice and the provider error wording.
6. **Markdown**, negative tests first (07).
7. **The model list** (08).
8. **The close:**
   - the code (09a): aliases, allowances, catalogue, badge kinds, dead CSS, docs;
   - the verification (09b): the after set, budgets, the full gate and the spec sweep.
9. **The HAT.**

### Checkpoints
- [x] The chat surfaces are in the capture tool, the before set is taken, the sinks are at zero, the lanes are split and re-measured, and squawk 0249 is fixed.
- [x] `chat.js` is split into modules, behaviour-free, at 800 lines or fewer; full gate green.
- [x] The flash contract is in, every caller has dropped `container`, and toasts survive modals and remounts. The options that retire the area-CSS rows are in, and the library squawks 0269, 0270 and 0185 and D7 are done. Every editor lane is green.
- [x] The six chat controls (the five plus the notice) exist in `js/ui` with contract tests in both engines, in the `contracts-chat` lane.
- [x] The chat area is on the controls. The area renderers and legacy chat classes are deleted, the chat JS allowance rows are gone and defects 1, 3-6 and 9 are fixed. F1 and B9 are in.
- [x] The step-limit notice reaches the web chat, connectors and the CLI. The provider error names the right provider. The new spec is drafted.
- [x] Markdown: the negative tests are in, the holes are closed, A1, B1 and 0.4 are done and the Copy is on the library.
- [x] The model list is in the library, and `provider-models.js` is under 800.
- [x] Every count is at zero. Docs and the catalogue are final, the after set is reviewed, budgets are re-measured and the full gate is green. The mission-close specs and the new spec pass.
- [x] HAT passed, and the close checks re-run after any HAT code change.

### Adaptation Criteria

**Divert if**:
- The split cannot stay behaviour-free (a test changes behaviour, not just a path pin): stop and re-plan the boundary.
- A chat control cannot meet DD4's boundary without widening `_APP_GLOBAL`: raise it rather than widen the guard.
- F2 needs a schema or history change, or `openai-compatible` calls an Ollama-only endpoint beyond the two known probes (DD11 2): raise it as its own question.
- A markdown fix changes how any link that is safe today renders, beyond D3's same-origin rule: raise it.
- Design review pushes the flight past 15 autonomous legs: raise a split with the operator.

**Acceptable variations**:
- Module boundaries and names inside DD3; factory and option names inside DD4 and DD6.
- Splitting a leg further at its design review (never merging legs).
- Further lane splits by the re-budget rules.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `groundwork-and-before-set` (01):
  - the chat and model-picker surfaces in `scripts/ui_capture.py`, with the seed pinned against the clock and zone (DD2), and the before set;
  - the five clears replaced (sinks 5 → 0) and `START_ROWS` rewritten;
  - the quiet-host re-measure; `chats` split; squawk 0271's MCP test-file split and the `mcp` lane split, with budgets from junit;
  - squawk 0249's stubs and falsification check; squawk 0259 closed.
- [x] `chat-split` (02), **tier high (a behaviour-free restructure of the largest area file)**: `chat.js` into the DD3 modules; anchors re-anchored; `MOVES` entries; the line-guard entry removed; full gate.
- [x] `flash-and-feedback-options` (03a), **tier high (a shared interface, every editor)**:
  - DD5's flash region: the modal stack rule, the re-home on close, the newest-replaces rule, and `container` removed from every caller including `App.showFlash`;
  - A14's wording; DD9 test 6 and DD11 7;
  - `App.ui.badge.live`; the copyButton confirmation (D1, announced once under `role=log`);
  - `App.ui.noteFlag`, with `App.iconNode` deleted;
  - the unlayered CSS moved inside the layer, with its unit check;
  - every editor lane, plus `chats` and `agent-tabs` (the badge and note-flag consumers in `chat-pane.js`, `agent-drawer.js` and `studio/notes-section.js`).
- [x] `layout-options` (03b), **tier high (searchList contract changes)**:
  - the searchList chooser variant, A9 and D4 (squawk 0185);
  - the drawer and modal options;
  - the list-pane, badge, tabpanel, section-inset and field-width rules.
  - Retires the 12 area-CSS rows and `agent-picker.js`'s row; re-authors `jump-to-palette`.
- [x] `chip-confirm-kv-and-labels` (03c):
  - the chip `lead` / `onRemove` and the confirm `onArmChange` options;
  - squawks 0269 and 0270;
  - D7's sentence case, re-authoring `studio-agent-crud`, `agent-retention-setting-roundtrip` and `save-preserves-config`.
- [x] `chat-controls` (04), **tier high (six new library controls with update handles)**: under DD4's boundary and class policy (new `ui-*` names, owned rules in `components.css`, `chat.css` untouched):
  - `App.ui.composer`;
  - `message` (with the attribution and F1's `setCopy`);
  - `thinking`;
  - `trace` (with the thinking disclosure);
  - `telemetry`;
  - `notice`.

  Catalogue rows: one factory per row, so row 82 "Thinking indicator, trace shell" splits in two and `notice` gets a new row, and every `--` modifier is listed by name in Owned classes (the emitted-class guard cannot see `--` modifiers). Contract tests in both engines. The `contracts-chat` lane, with DD2's bookkeeping (`run-tests.sh`, `tests/test_run_tests_lanes.py`, CLAUDE.md) and a provisional budget from this leg's own `--lane` timing, re-measured at 09b.
- [x] `composer-and-attachments` (05a), **tier high (the send path)**:
  - the composer, attachments, hold queue and health banner moved onto the library: A5, A6, A7, B6, B13, DD11 1 and 3;
  - `composer.js` and the legacy composer classes deleted, with locators retargeted;
  - re-authors `vision-round-trip`.
- [x] `sign-in-and-list-delete` (05b), **tier high (sign-in)**:
  - chat sign-in on `App.ui.button` and `App.ui.consentLink`: A3 and squawk 0215 (DD11 9);
  - the Chats list delete on `App.ui.confirm`'s `onArmChange`: DD11 6; the platform badge's display name (A16, `chat/chats-list.js:120`);
  - `App.confirmDelete` and `App.consentLink` call sites removed;
  - re-authors `start-a-chat` step 14.
- [x] `transcript` (05c), **tier high (streaming, replay)**:
  - the message, thinking, trace, telemetry and notice moved onto the library: A4, A8, A15, A18, B2 (anchored reorder), B3, B5, B9, F1 (the full received source kept), DD11 4 and 5;
  - the area renderers and legacy classes deleted (`message-bubble.js`, `thinking-indicator.js`, `trace-shell.js`, `telemetry-overlay.js`), with locators retargeted and the contrast audits moved;
  - re-authors `chat-loop-hang-and-cancel`, `extended-thinking-tool-turn`, `stub-connector-round-trip` (step 7) and `agent-governance-and-search` (step 8).
- [x] `turn-end-messages` (06), **tier high (the agent loop, the WebSocket protocol, connectors)**:
  - F2 across core, web, connectors, REST and the CLI, with DD8's flag lifecycle and the `step_limit` frame contract;
  - DD11 2's provider error wording;
  - the `agent-step-limit-notice` spec drafted; `agents.md`'s frame table.
- [x] `markdown` (07), **tier high (security)**:
  - DD9's negative tests first; then `safeHref` (D3) and the fence token;
  - A1, B1 and 0.4 with its negative cases;
  - the code-block Copy on the library (A2, D1), with `injectIcon` and the `App.icon` / `App.showFlash` calls gone;
  - re-authors `discord-markdown-links`.
- [x] `model-list` (08): `App.ui.modelList` with contract tests; `provider-models.js` on it and under 800; A10-A13 and A17; the line-guard entry removed.
- [x] `close-the-counts` (09a):
  - the aliases deleted; the allowances empty; the catalogue's Retired table and the "no not-yet-defined" assertion;
  - D6's badge kinds; dead CSS; the unused-selector review;
  - docs final, including squawk 0272.
- [x] `close-verification` (09b): the after set and its ledger mapping; the quiet-host re-budget; the full gate; the behavior-spec sweep and `agent-step-limit-notice`.
- [x] `flight-hat` (10) *(interactive)*: the operator walks the ledger in both themes at 1280 and 1024, on a seeded dev instance.
  - The walk includes a state the operator isn't looking at: a connector chat updated while another chat is open, and the step-limit line on the stub connector.
  - The operator approves the before and after set.
- [x] `multi-message-queue` (10a), HAT feature (fix-vs-feature gate): the hold queue holds up to 10 messages, one chip each.
- [x] `chat-row-status` (10b), HAT feature: the Chats rows show working and new-reply activity (`busy`, `turn_seq`, `track_turn`).
- [x] `per-chat-drafts` (10c), HAT feature: each conversation keeps its own unsent text and staged images.
- [x] `step-limit-continue` (10d), HAT feature: the web step-limit notice carries a Continue button.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- **Counts:** `OWNERSHIP_ALLOWANCE`, `TOTAL_USES`, `MOVES` and `HTML_SINK_ALLOWANCE` are empty. `tests/test_area_module_size.py` `ALLOWANCE` holds only `studio/provider-editor.js` (D8). `git grep` finds no code call to `App.confirmDelete(`, `App.showFlash(`, `App.icon(`, `App.iconNode(`, `App.consentLink.`, `App.escapeHtml` or `App.escapeAttr`.
- **The catalogue** has no "not yet defined" row, enforced by `tests/test_ui_control_inventory.py`. The unused-selector report is empty apart from documented dynamic users.
- **Behaviour:** `make gate` (unit, then every browser lane, `THE_ONE_REQUIRE_WEBKIT=1`, `THE_ONE_TEST_NETNS=1`) and `make lint` pass. The mission-close behavior specs and `agent-step-limit-notice` pass on a dedicated dev instance.
- **Looks:** every visible difference in the before and after set maps to a ledger row, and the operator approves the set at the HAT.
