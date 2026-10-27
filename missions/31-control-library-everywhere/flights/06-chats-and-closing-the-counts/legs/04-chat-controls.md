# Leg: chat-controls

**Status**: planning
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Build the six chat controls as `App.ui` factories with update handles, contract-tested in Chromium and WebKit, **without moving any consumer yet**:
- `App.ui.composer`, `App.ui.message` (with `App.ui.message.attribution`), `App.ui.thinking`, `App.ui.trace` (with the thinking disclosure), `App.ui.telemetry` and `App.ui.notice`;
- each emits new `ui-*` classes with owned rules in `components.css` that reproduce today's look;
- the old area renderers and `chat.css` stay live and untouched until legs 05a-05c.

## Context
- **Flight decisions:** DD4 (the library boundary, the handle shapes, the class-name policy, the notice control, keeping the streaming source), DD7 (the approved looks the controls must support: A8 "Thinking…", B2, B3, B5, B9, B13, F1), DD8 (F1, F2, B9), DD13 and DD15 (the `contracts-chat` lane).
- **The library boundary.**
  - A `js/ui` file may touch no app global except `App.ui` and `App.icons` (`tests/test_ui_library_source.py:20`, `_APP_GLOBAL`), and must be ES5 (`_ES6`).
  - The contract harness loads only `icons.js` and `js/ui/*.js` (`tests/browser/_ui_engines.py:199-201`).
  - So no control calls `App.markdown`, `App.time`, `App.config` or `App.perf`: the area passes rendered Nodes, ready labels and thresholds.
  - New factories match `_FACTORY_LINE` (`App.ui.<name> = function (opts) {`). Sub-entries such as `App.ui.message.attribution =` and `App.ui.trace.find =` have the shape of the existing `App.ui.modal.anyOpen =`.
- **Today's area renderers**, after leg 02, all in `js/areas/chat/`:
  - **`composer.js`:** `App.chat.composer.create()` returns `{el, box, input, fileInput, attachBtn, modelEl, stopBtn, sendBtn, attachmentsEl, attachmentsStatusEl, queuedRegion, telemetryRow, render(view), fit()}`. It is a DOM builder with no listeners; `chat.js` and `send.js` wire Enter, IME, `input`/`fit`, Send, Attach, file `change` and Stop. Its testids are `chat-input`, `chat-image-input`, `chat-attach-btn`, `chat-model`, `chat-stop-btn`, `chat-send-btn`, `chat-attachments`, `chat-attachments-status` and `pending-queued-region`. It has a fixed `INPUT_ID`.
  - **`message-bubble.js`:**
    - `App.chat.renderMessage(cls, text, {renderMarkdown, visibility, peerName})` returns `div.msg {cls}[data-testid=message]`. It adds `msg-operator-only` plus the label `[operator-only]` for non-user operator visibility, and `msg-from-peer` plus a visually hidden "From {peer}: " label. The body is markdown for assistant bubbles, otherwise text.
    - `App.chat.renderAttribution(side, text, ts)` returns `.msg-attribution.{side}` with `span.msg-attribution-ts[data-ts]`.
    - The streaming bubble is built empty, without markdown, and mutated through its trailing text node (`transcript.js:340-360`).
  - **`thinking-indicator.js`:** `createThinking()` builds the `thinking-indicator` testid, the "thinking" text and spinning dots on `el._dotTimer`, gated by reduced motion. `removeThinking(el)`. A second, ungated copy for "Loading model" lives in `turn-frames.js` `handleSystem` (defect DD11 4).
  - **`trace-shell.js`:**
    - `renderTrace(parentMsgId)` returns `div.trace-shell[data-parent-msg-id][data-testid=trace-shell] > details > summary.trace-toggle(.trace-summary "Tool activity", .trace-count[aria-hidden]) + .trace-body`.
    - `appendToTrace(shell, msg)` updates the count and the summary's `aria-label`.
    - `renderThinking(evt)` returns `details.thinking-disclosure[data-testid] > summary.thinking-toggle "Thinking" + .thinking-body`.
  - **`telemetry-overlay.js`:** `renderTelemetry()` returns `.telemetry-overlay[tabindex=0][role=status]`. `update`/`reset`/`setMax` take the whole content panel and `querySelector` inside it, keeping state on `root.__telemetry`. Thresholds come from `App.config`, with `App.perf` marks. `fmtTokens`.
  - **The styles** are in `css/chat.css`: telemetry `:288-304`, bubbles `:314-351`, system/operator-only/attribution `:469-498`, the markdown inside a bubble `:504-543`, trace and thinking `:354-468`, the thinking indicator `:499-501`, the composer `:574-638`, the queued chip `:651-657`. Line numbers are from planning; re-derive them.
- **The class policy (DD4).**
  - Every new class is `ui-*`: `ui-composer*`, `ui-message*`, `ui-thinking*`, `ui-trace*`, `ui-telemetry*`, `ui-notice*`.
  - Roles and states are modifiers (`ui-message--user`, `--assistant`, `--tool`, `--system`, `--error`, `--peer`, `--operator-only`; `ui-notice--muted`, `--danger`).
  - No bare role word is owned.
  - Each catalogue row lists every class and every modifier **by name** (the emitted-class guard cannot see `--` modifiers, and the ownership guard counts only names written out in the catalogue).
  - Area code will never query `ui-*` names. It reaches nodes through handles, `App.ui.trace.find` or testids.
- **The look.** The new owned rules in `components.css` reproduce today's `chat.css` rules for the same parts. The approved changes land in the consumer legs, not here: A8 "Thinking…", A15 timestamp contrast, A18 focus offset, B3's chevron, B5's chip, B13's dimmed blocked box. But each control must **support** them through its options:
  - the thinking label is a caller option;
  - the attribution's time label is set by the caller;
  - the composer's `setBlocked` dims the box;
  - the trace summary takes a chevron icon and a "Tool activity · {n}" label;
  - the message takes a `chip` for "Operator only".

  The consumer leg chooses the approved values.
- **The `contracts-chat` lane** (DD15) is created in this leg with its first file. Its files are subtracted from `contracts-controls`' complement and added to the `contracts` alias. It runs under `THE_ONE_REQUIRE_WEBKIT=1`. Its bookkeeping is the same set as leg 01's:
  - `scripts/run-tests.sh`: `LANE_LIST`, `CANON_LANES`, `BUDGET`, the pattern, `resolve_lane`, the `contracts` alias and the help text;
  - `tests/test_run_tests_lanes.py`: the `LANES` tuple, the hard-coded lane string and a by-file test;
  - CLAUDE.md: the bullets, the counts (sixteen lanes, fifteen named) and the table;
  - `the_one/agents.md`'s lane summary, and the `ci/tasks/browser.yml` comment.

  Its budget is provisional, from this leg's own solo `--lane` timing ×2 (marked provisional in both tables), and is re-measured at 09b.

## Inputs
- Batch B2 (legs 03a-03c) landed and committed: `App.ui.badge.live`, the copy confirmation (`App.ui.button.setIcon`), `App.ui.noteFlag`, the flash contract, the chip `lead` / `onRemove` and the confirm `onArmChange`.

## Outputs
- **`App.ui.composer(opts)`** (`js/ui/composer.js`, new):
  - **Options:** `label` ("Message"), `placeholder`, `onSend(text)`, `onStop()`, `onFiles(files)`, `accept`, `multiple`, `attachLabel` ("Attach images"), and per-part testids (the caller passes today's literals).
  - **Handle:** `{el, input, setPlaceholder(text), setModel(text), setBusy(bool), setBlocked(reason|null), getValue(), setValue(text), focus(), slots: {telemetry, attachments, attachmentsStatus, queued}, fit(), destroy()}`.
    - `setBusy(true)` shows Stop and disables Send.
    - `setBlocked(reason)` disables the input, Send **and** Attach, and adds a dimmed modifier on the box (B13). It is the single writer of the disabled state.
  - It owns the Enter-sends / Shift+Enter-newline / IME rule (`isComposing` or `keyCode` 229 does nothing), the auto-fit to about 8 lines on `input` and after `setValue`, and the file input's `change`.
  - Its input id comes from `App.ui.util.uid()`. `destroy` removes every listener.
- **`App.ui.message(opts)`** (`js/ui/message.js`, new):
  - **Options:** `role` ('user', 'assistant', 'tool' or 'system'), `tone` ('error' optional), `body` (a Node; the area renders markdown) or `text`, `visibility` ('operator' adds the operator-only marker for non-user roles, as a chip, with the label text from the caller), `peerName` (the peer modifier plus a visually hidden "From {peer}: " label), and `testid` ('message').
  - **Handle:** `{el, appendText(s), commit(fragment, consumed), finalize(fragment|null), tail(), destroy()}`. These are the streaming tail primitives: `commit` inserts a rendered prefix before the live tail and drops `consumed` characters from the tail; `finalize` replaces the tail with a final fragment, or leaves the text.
  - **`App.ui.message.attribution(opts)`:** options `side` ('you', 'agent' or 'peer'), `name`, `timeLabel`, `ts` (stored as `data-ts`), and `copyText` (F1; when set, an icon-only library copy button named "Copy reply", with D1's confirmation).
    - Returns `{el, setTimeLabel(text), setCopy(text|null)}`.
    - `App.ui.message.relabel(root, fn)` re-labels every attribution under `root` from its `data-ts` through the caller's `fn`. It replaces the area's global `querySelectorAll` sweep without an `App.time` dependency.
- **`App.ui.thinking(opts)`** (`js/ui/thinking.js`, or beside `message`):
  - options `label` (the caller passes "Thinking…" or "Loading model…"), `tone` ('assistant' or 'system') and `testid`;
  - returns `{el, settle(text), destroy()}`;
  - the dots animate only without `prefers-reduced-motion`. The interval stops on `destroy`, on `settle` and when `el` is disconnected (checked in the tick). There are no DOM expandos.
- **`App.ui.trace(opts)`:**
  - options `id` (stored as `data-parent-msg-id`), `label` ('Tool activity'), `testid` ('trace-shell');
  - a native `<details>` with a summary using the library chevron (B3 (b)), the label and a count in the "· {n}" form, and a body;
  - returns `{el, append(node), count(), destroy()}`; `append` updates the count and the summary's accessible name;
  - `App.ui.trace.find(root, id)` returns the handle for an existing trace, kept in a module `WeakMap` or by re-wrapping, never an expando;
  - **`App.ui.trace.thinking(opts)`:** the thinking disclosure (`label` 'Thinking', `body` text, `testid` 'thinking-disclosure'), a `<details>` in the trace's mono voice.
- **`App.ui.telemetry(opts)`:**
  - options `warn` and `crit` (thresholds from the area), `testid`;
  - returns `{el, update({input, output, context}), setMax(n), reset(), destroy()}`;
  - it keeps today's `role=status`, `tabindex=0`, the expand-on-hover-or-focus and the context bar with its warn and crit states, plus `aria-label`;
  - `fmtTokens` moves into it as a private helper (or `App.ui.telemetry.formatTokens`);
  - its state is in the closure, never `root.__telemetry`.
- **`App.ui.notice(opts)`:**
  - options `tone` ('muted' or 'danger'), `body` (a Node or text), `testid`;
  - returns `{el, set(body), destroy()}`;
  - a transcript line, not a live region: the log announces it.
- **Owned rules** in `components.css`, one section per control, reproducing today's look under the new names. `chat.css` is not edited.
- **Catalogue rows** (`docs/ui-control-inventory.md`):
  - Composer, Message bubble (with attribution) and Telemetry readout change from "not yet defined" to `library: App.ui.<name>`;
  - row 82 "Thinking indicator, trace shell" **splits into two rows**, Thinking indicator (`App.ui.thinking`) and Trace (`App.ui.trace`), since the guard requires one factory per row;
  - a new **Notice** row.

  Each lists its options, its handle, its states and every owned class and modifier by name.
- **Contract tests,** one file per control, `tests/browser/test_ui_<name>_contract.py`, parametrized over both engines through `engine_page`. Each covers:
  - roles and names;
  - tab order and keyboard;
  - every handle method;
  - degenerate inputs: empty text, a 200-character unbroken word, an empty trace, `setMax(0)`, a notice with no body;
  - the teardown: after `destroy`, no listener fires and no interval remains (count with a wrapped `setInterval`).
- **The `contracts-chat` lane** with the six files, and its bookkeeping.
- **A parity check:** a browser flow test (in `chats-transcript`) that renders each old area renderer and its new library control side by side on the real app page under `.area-chat`. It compares a fixed set of computed properties (font family, size and weight, line height, padding, margin, colours, border, radius, max-width) on the root and its main parts. It is removed in leg 05c with the old renderers.

## Acceptance Criteria
- [ ] **Six factories exist** in `js/ui`, each with a catalogue row and a contract file calling `App.ui.<name>(`. `tests/test_ui_control_inventory.py`, `tests/test_ui_library_source.py` (ES5, `_APP_GLOBAL`, `_FACTORY_LINE`), `tests/test_ui_emitted_classes.py` and `tests/test_ui_ownership.py` pass. The catalogue rows list every modifier by name. `index.html` loads the new files after `ui/core.js`, and `test_index_asset_cache_busting.py` passes.
- [ ] **Each contract file passes in Chromium and WebKit** under `THE_ONE_REQUIRE_WEBKIT=1`, covering the cases in Outputs:
  - the composer: Enter sends, Shift+Enter adds a newline, an IME Enter does nothing, `setBlocked` disables the input, Send and Attach and dims the box, `setBusy` toggles Stop and Send, auto-fit grows and then scrolls, and `destroy` removes the listeners;
  - the message: each role and modifier, `body` versus `text`, the operator-only chip and the peer label, and the streaming `appendText`, `commit` and `finalize` sequence leaving the expected DOM;
  - the attribution: `setTimeLabel`, `setCopy` (the button appears, copies the given text, is named "Copy reply", confirms, and `setCopy(null)` removes it) and `relabel`;
  - thinking: the label, reduced motion, `settle`, and no interval after disconnect;
  - the trace: `append` updates the count and the name, `find` returns the same handle, and the thinking disclosure;
  - the telemetry: `update`, `setMax`, `reset`, the thresholds, and focus expansion;
  - the notice: both tones and `set`.
- [ ] **The parity check passes** for every old/new pair, or each difference is listed in the flight log as intended (for example, the chevron for B3 belongs to 05c and must not appear here unless the caller passes it).
- [ ] **No consumer changed:** `git diff` shows no change under `js/areas/` and no change to `css/chat.css`. The chat lanes (`chats`, `chats-transcript`) pass unchanged.
- [ ] **The `contracts-chat` lane exists:** `bash scripts/run-tests.sh --lane contracts-chat --list` lists the six files and `--lane contracts-controls --list` does not. `tests/test_run_tests_lanes.py` passes. CLAUDE.md's table and `scripts/run-tests.sh` agree, with the budget marked provisional.
- [ ] `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass. Any new colour pair a control introduces is either an existing audited pair or added to the contrast audit.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. The unit guards (above), `-q -x --timeout 120`.
2. `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat -x --tb=short`.
3. `--lane chats-transcript` (the parity test) and `--lane chats`, one at a time.
4. `bash scripts/run-tests.sh --lane contracts-controls --list | grep -c test_ui_` before and after (the six files are not in it).
5. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **One control at a time, contract test first:** notice, thinking, trace, telemetry, message (with attribution), then composer (the largest). Each gets its catalogue row and its owned rules in the same step.
2. **The rules:** copy each `chat.css` rule's declarations under the new `ui-*` selector, in `@layer components`, without the `.area-chat` ancestor. Where a `chat.css` rule depends on `.area-chat` specificity to beat another rule, note it for the consumer leg's cascade check.
3. **The parity flow test** once all six exist.
4. **The lane,** once the first contract file exists (so the lane is never empty). Then the bookkeeping.
5. `make test-unit`, ruff, the flight log.

## Edge Cases
- **The composer's `fit()`** measures `scrollHeight`, which needs the box rendered. Make `fit()` a no-op while disconnected, and have the consumer call it after mounting.
- **The streaming tail:** `commit(fragment, consumed)` must not reflow the scroll position. The transcript keeps the scroll pin, and the control only mutates its own node.
- **Copy reply on a replay:** the attribution takes the stored content through `copyText`. It never reads the bubble's rendered text.
- **`App.ui.trace.find`** after a reconnect replay: an existing `.ui-trace` node built by a previous handle must still be findable. Prefer a lookup by `data-parent-msg-id` that re-wraps the node.
- **Two engines:** native `<details>` toggling, `isComposing` and `keyCode` 229 behave differently in WebKit. Test the IME rule by dispatching a composition-flagged `KeyboardEvent` in both.
- **No new colour token** unless audited. Reuse the tokens `chat.css` uses.
- **`destroy` idempotence:** calling it twice is harmless.

## Files Affected
- `the_one/interfaces/web/static/js/ui/{composer,message,thinking,trace,telemetry,notice}.js` (new; names may merge where natural, one factory per catalogue row), `index.html`, `css/components.css`.
- `tests/browser/test_ui_{composer,message,thinking,trace,telemetry,notice}_contract.py` (new), the parity flow test (new, `chats-transcript`).
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, CLAUDE.md, `the_one/agents.md` (the lane summary and "Control library"), `ci/tasks/browser.yml` (a comment).
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md` (if a testid's owner changes to a library factory), the flight log.

## Citation Audit
- `tests/test_ui_library_source.py:20` (`_APP_GLOBAL`) and `_FACTORY_LINE`; `tests/browser/_ui_engines.py:199-201` (the harness loads only `icons.js` and `js/ui`). Verified (Architect cycles 1-2 and FD).
- The area renderers' APIs and testids: FD grep of `js/areas/chat/{composer,message-bubble,thinking-indicator,trace-shell,telemetry-overlay}.js` after leg 02 (2026-10-27). `transcript.js:340-360` holds the streaming bubble.
- The `chat.css` line ranges are from the code survey §9. Re-derive them.
- Catalogue row 82 ("Thinking indicator, trace shell") and `test_inventory_rows_are_classified`'s one-factory rule: Architect cycle 2.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
