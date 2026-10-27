# Leg: chat-controls

**Status**: completed
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

  The consumer leg chooses the approved values. **Every option that changes the look defaults to today's look** (design review), so the parity check compares like with like.
- **The `contracts-chat` lane** (DD15) is created in this leg with its first file. Its files are subtracted from `contracts-controls`' complement and added to the `contracts` alias. It runs under `THE_ONE_REQUIRE_WEBKIT=1`. Its bookkeeping is the same set as leg 01's:
  - `scripts/run-tests.sh`: `LANE_LIST`, `CANON_LANES`, `BUDGET`, the pattern, `resolve_lane`, the `contracts` alias and the help text;
  - `tests/test_run_tests_lanes.py`: the `LANES` tuple, the hard-coded lane string and a by-file test;
  - CLAUDE.md: the bullets, the counts (sixteen lanes, fifteen named) and the table;
  - `the_one/agents.md`'s lane summary, and the `ci/tasks/browser.yml` comment.

  Its budget is a **provisional 300 s** in both tables. A solo `--lane` run cannot set a budget (the quiet-host rule, squawk 0259), so the provisional figure stands until the quiet-host run at 09b replaces it by the measured-plus-25% rule.

## Inputs
- Batch B2 (legs 03a-03c) landed and committed: `App.ui.badge.live`, the copy confirmation (`App.ui.button.setIcon`), `App.ui.noteFlag`, the flash contract, the chip `lead` / `onRemove` and the confirm `onArmChange`.

## Outputs
*(Rewritten after design review cycle 2 to fold in the cycle-1 amendments. Where the amendments section below still adds detail, it applies. Nothing here contradicts it.)*
- **`App.ui.composer(opts)`** (`js/ui/composer.js`, new):
  - **Options:** `label` ("Message"), `placeholder`, `onSend(text)`, `onStop()`, `onAttach()`, `onFiles(files)`, `accept`, `multiple`, `attachLabel` ("Attach images"), and per-part testids (the caller passes today's literals).
  - **Handle:** `{el, input, setPlaceholder(text), setModel(text), setBusy(bool), setBlocked(reason|null), openFilePicker(), getValue(), setValue(text), focus(), slots: {telemetry, attachments, attachmentsStatus, queued}, fit(), destroy()}`.
    - `setBusy(true)` shows Stop and disables Send (not the input).
    - `setBlocked(reason)` disables the input and Attach and dims the box (B13).
    - **Send's disabled state is `blocked || busy`**, so clearing `blocked` while busy keeps Send disabled. Today the banner-clear path re-enables Send even while busy; the new behaviour is an intended fix.
  - It owns:
    - the Enter-sends / Shift+Enter-newline / IME rule (`isComposing` or `keyCode` 229 does nothing). Enter calls `onSend(rawValue)` whenever the input is enabled, busy or not, and with empty text too;
    - the auto-fit, with today's `minHeight` hold;
    - the file input's `change`.
  - It never clears the input.
  - Its input id comes from `App.ui.util.uid()`. No test selects the old `chat-composer-input` id. `destroy` removes every listener.
- **`App.ui.message(opts)`** (`js/ui/message.js`, new):
  - **Options:**
    - `role` ('user', 'assistant', 'tool' or 'system') and `source` ('api' for today's `.msg.user.api`);
    - `tone` ('error');
    - `body` (a Node; wins over `text`) or `text`;
    - `streaming` (true creates the empty tail text node);
    - `visibility` ('operator' for non-user roles), with `visibilityStyle` ('label', the default `[operator-only]` span, or 'chip', B5) and `visibilityLabel`;
    - `peerName`;
    - `testid` (caller-supplied).
  - **Handle:** `{el, appendText(s), commit(fragment, consumed), finalize(fragment|null), tail(), destroy()}`. `tail()` returns the tail **string**; the semantics are as in the amendments.
  - **`App.ui.message.attribution(opts)`:**
    - options `side` ('you', 'agent' or 'peer'), `name`, `timeLabel`, `ts`, `copyText` and `liveEl`;
    - with `copyText` it builds `App.ui.copyButton({iconOnly: true, label: 'Copy reply', text: function () {…}, liveEl: opts.liveEl, testid})`, D1's confirmation. The transcript passes **one shared live node** as `liveEl`, so replies do not each carry a `role=status` span; with `liveEl` the root is the bare button;
    - returns `{el, setTimeLabel(text), setCopy(text|null)}`. `setCopy(null)` removes the node it owns;
    - while confirming, the button's name is "Copied" (or "Copy failed") for 2 s, then reverts to "Copy reply". Tests assert the revert and never assume a constant name;
    - `App.ui.message.relabel(root, fn)` as in the amendments.
- **`App.ui.thinking(opts)`** (`js/ui/thinking.js`, or beside `message`):
  - options `label` ("Thinking…" or "Loading model…", from the caller), `tone` ('assistant' or 'system') and `testid`;
  - its root composes the message classes (`ui-message ui-message--assistant ui-thinking`, or `--system`);
  - returns `{el, settle(text), destroy()}`;
  - the dots animate only without reduced motion (read once). The interval stops on `destroy`, on `settle`, and once the node has been connected and **then** disconnected; a node not yet attached keeps ticking. There are no DOM expandos.
- **`App.ui.trace(opts)`:**
  - options `id` (`data-parent-msg-id`), `label` ('Tool activity'), `chevron` ('css', the default, today's look; or 'icon'), `countStyle` ('span', the default, today's separate count; or 'dot', "Tool activity · 4", B3), `testid`;
  - a native `<details>`;
  - returns `{el, append(node), count(), destroy()}`. `count()` derives from the body's children. `append` updates the count and the summary's accessible name ("Tool activity, N items"). `destroy` detaches listeners only;
  - `App.ui.trace.find(root, id)` looks up `.ui-trace[data-parent-msg-id="…"]` (scoped to `.ui-trace`, since the thinking disclosure also carries the attribute) and re-wraps it;
  - **`App.ui.trace.thinking(opts)`** (`label` 'Thinking', `body`, `parentId`, `testid`);
  - `App.ui.disclosure` is not expected to be reused: its `aria-labelledby` labelling conflicts with the trace's exact summary name and mono voice. The reason is recorded.
- **`App.ui.telemetry(opts)`:**
  - options `thresholds` (`{warn, crit}` or a function returning it, read on every update) and `testid`;
  - returns `{el, update(data), setMax(n), reset(), destroy()}`. `update` takes today's usage-frame shape (`input_tokens`, `output_tokens`, `context_tokens`, `max_context_tokens`). `setMax` touches only the maximum and the percentage;
  - it keeps today's `role=status`, `tabindex=0`, the expand-on-hover-or-focus, the context bar's warn and crit states, `aria-label` and the 0.7 resting opacity;
  - `fmtTokens` moves in as a private helper (or `App.ui.telemetry.formatTokens`), and its state is in the closure.
- **`App.ui.notice(opts)`:**
  - options `tone` ('muted' or 'danger'), `body` (a Node or text) and `testid`;
  - returns `{el, set(body), destroy()}`;
  - a transcript line, not a live region: the log announces it.
- **Script order:** the six new files go in `index.html`'s `js/ui` block **after `drawer.js`** (so after `feedback.js`, `copy.js` and `button.js`). The harness derives its script list from `index.html`.
- **Owned rules** in `components.css`, one section per control, reproducing today's look under the new names. `chat.css` is not edited.
- **Catalogue rows** (`docs/ui-control-inventory.md`):
  - Composer, Message bubble (with attribution) and Telemetry readout change from "not yet defined" to `library: App.ui.<name>`;
  - the "Thinking indicator, trace shell" row (row 83 at B2's close) **splits into two rows**, Thinking indicator (`App.ui.thinking`) and Trace (`App.ui.trace`), since the guard requires one factory per row;
  - a new **Notice** row.

  Each lists its options, its handle, its states and every owned class and modifier by name.
- **Testids are caller-supplied only.** `find_testid_value_violations` (`tests/_ui_guard_helpers.py:151`) requires a `testid:` value in `js/ui` to be a forwarded identifier, so no factory has a literal default such as `'message'`. The contract tests pass the literals from Python, and leg 05 passes today's literals.
- **Contract tests,** one file per control, `tests/browser/test_ui_<name>_contract.py`, parametrized over both engines through `engine_page`. Each covers:
  - roles and names;
  - tab order and keyboard;
  - every handle method;
  - degenerate inputs: empty text, a 200-character unbroken word, an empty trace, `setMax(0)`, a notice with no body;
  - the teardown: after `destroy`, no listener fires and no interval remains (count with a wrapped `setInterval`).
- **The `contracts-chat` lane** with the six files, and its bookkeeping.
- **A parity check:** a browser flow test (in `chats-transcript`) that renders each old area renderer and its new library control side by side on the real app page under `.area-chat`. It compares a fixed set of computed properties (font family, size and weight, line height, padding, margin, colours, border, radius, max-width) on the root and its main parts. It is removed in leg 05c with the old renderers.

## Acceptance Criteria
- [ ] **Six factories exist** in `js/ui`, each with a catalogue row and a contract file calling `App.ui.<name>(`. `tests/test_ui_control_inventory.py`, `tests/test_ui_library_source.py` (ES5, `_APP_GLOBAL`, `_FACTORY_LINE`), `tests/test_ui_emitted_classes.py` and `tests/test_ui_ownership.py` pass. The catalogue rows list every modifier by name. `index.html` loads the new files after `drawer.js`, and `test_index_asset_cache_busting.py` passes.
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
- The catalogue's "Thinking indicator, trace shell" row (row 83 after B2) and `test_inventory_rows_are_classified`'s one-factory rule: Architect cycle 2.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27; these take precedence over the Outputs above)
- **The composer's send semantics:**
  - Enter (without Shift, outside an IME composition) calls `onSend(rawValue)` whenever the input is enabled, **whether or not the composer is busy**. A busy Enter is how a message is held in the one-slot queue; only the Send button is disabled while busy.
  - `onSend` fires for empty or whitespace text too (an image-only send); the area decides.
  - **The control never clears the input.** The area clears it with `setValue('')` only on success, so a guarded return (idle, joining, a closed socket) keeps the text.
  - The Send button's click calls the same `onSend(getValue())`.
  - **Busy and blocked compose:** Send's disabled state is `blocked || busy` (today's `chat.js:373`), so clearing `blocked` while busy leaves Send disabled.
  - `setBlocked` also disables Attach (B13, approved), a deliberate change from today's `applyComposerState`.
  - **Attach:** the button's click calls `onAttach()`; the area owns the busy and blocked guard and calls `composer.openFilePicker()`. The hidden file input keeps `aria-label` "Attach images" (`attachLabel`, squawk 0110), and its `change` calls `onFiles(files)`.
  - **Slots:** the attachments slot keeps today's inline `style.display` pattern and its visually hidden `aria-live` status node. The queued and telemetry slots toggle `hidden`, so no `ui-composer-*` rule sets a `display` that would defeat the global `[hidden]` reset.
  - `fit()` keeps today's `box.style.minHeight` hold, which stops a pinned log drifting per keystroke, and is a no-op while disconnected. `setValue` calls `fit()`. No width cap is invented (DD16).
  - **Contract cases:** Enter while busy, Enter with empty text, blocked then unblocked while busy, and an attach click calling `onAttach` and never the picker directly.
- **The message's streaming contract:**
  - `App.ui.message({…, streaming: true})` creates an explicit empty tail text node as the bubble's `lastChild`, after any operator marker or peer label.
  - `appendText(s)` is `tail.nodeValue += s`; `tail()` returns the tail **string**.
  - `commit(fragment, consumed)`: if the fragment is null or has no `firstChild`, do nothing and consume nothing; otherwise insert it before the tail and cut `consumed` characters from the tail's start.
  - `finalize(fragment|null)` removes the tail even when empty, appends the fragment, and makes every later `appendText`, `commit` and `finalize` a no-op.
  - `renderHistory` builds finished bubbles through `body` and does not use these. `body` wins over `text` when both are given.
  - **Contract cases:** streaming with operator visibility and with a peer label (the tail stays last), an empty finalize, a double finalize, and a `commit` with an empty fragment.
- **Today's look is the default:**
  - **The trace:** a CSS chevron plus a separate count span by default; `chevron: 'icon'` and `countStyle: 'dot'` ("Tool activity · 4") are options for 05c's B3. The summary's accessible name ("Tool activity, 3 items") is the same either way.
  - **Operator-only:** the `[operator-only]` label span by default; `visibilityStyle: 'chip'` is the B5 option, with label text from the caller.
- **Message variants:**
  - `ui-message--api` (today's `.msg.user.api`, `--accent-api`), plus `--user`, `--assistant`, `--tool`, `--system`, `--error`, `--peer` and `--operator-only`;
  - the tool-in-trace overrides become a descendant rule (`.ui-trace-body .ui-message--tool`, and its error form);
  - the markdown descendant rules (`chat.css` `.msg.assistant p, ul, pre, code, table, th, td…`) are re-scoped under `.ui-message--assistant`;
  - wrapping (`pre-wrap`, word-wrap) is covered by the 200-character word case;
  - modifiers come from a table (for example `ROLE_CLASS`) so the emitted-class guard finds each one, and each is listed by name in the catalogue.
  - `.msg-pending-approval*` is dead CSS (no builder) and is **not** part of the control; leg 09a deletes it (DD14).
- **Thinking composes the message:**
  - its root is `div.ui-message.ui-message--assistant.ui-thinking` (or `--system` for `tone: 'system'`, today's centred "Loading model" look), so the bubble look comes from the message rules;
  - `settle(text)` stops the timer, drops the thinking and loading modifiers, and replaces the contents with plain text, keeping the same node (today's `turn-frames.js` "Model loaded." behaviour);
  - **the interval stops** on `destroy`, on `settle`, and once the node **has been connected and then disconnected**. A node that is built but not yet appended keeps ticking until attached;
  - reduced motion is read once at creation, as today. A contract case covers both engines.
- **Telemetry:**
  - `thresholds` is a number pair **or a function** returning `{warn, crit}`, read on every update (today's `ctxThresholds()` reads `App.config` each time, which may load after init);
  - `update(data)` takes **today's `updateTelemetry` data shape** (the server's usage-frame field names, including `max_context_tokens`), so 05c maps its callers one to one (`socket.js:203`, `:217`, `:273`, `session-flow.js:110`, `turn-frames.js:162`);
  - `setMax(n)` touches only the maximum and the percentage, keeping the replay-restore behaviour (`socket.js:213`);
  - the perf marks stay in the area, and the 0.7 resting opacity (`_TELEMETRY_RESTING_OPACITY`) is copied.
- **The trace handle:**
  - `App.ui.trace.find(root, id)` locates `.ui-trace[data-parent-msg-id="…"]` and re-wraps it;
  - `count()` derives from the body's children, never a stored counter, so a re-wrapped handle cannot drift;
  - `destroy()` on a trace detaches listeners only and never removes content;
  - `App.ui.trace.thinking` takes `parentId` (sets `data-parent-msg-id` when given) and tolerates an empty or missing body;
  - reusing `App.ui.disclosure`'s native-details mechanics is preferred; if the mono voice or count wiring rules that out, the reason is recorded in the flight log.
- **Attribution:**
  - the separator is the text node `' · '`;
  - an empty or invalid `timeLabel` renders no separator, no time span and no `data-ts`;
  - `relabel(root, fn)` calls `fn(ts)` and skips a node when `fn` returns null or undefined.
- **The parity check:**
  - mount the old renderer's node and the new control's node under the real `.area-chat .messages` on the Chats destination (a `display: none` host gives zero layout values), giving the new nodes **distinct testids**;
  - don't mount a second old composer: its fixed `chat-composer-input` id would duplicate. Compare the live composer instead;
  - compare pseudo-elements as well (the trace chevron's `::before`, `::-webkit-details-marker`);
  - re-check that no `@layer areas` element rule inside `.area-chat` beats the new component rules.
- **The copy fallback:** the harness page has no clipboard permission, so WebKit takes `copyButton`'s `execCommand` fallback. Follow `tests/browser/test_ui_copy_contract.py`'s approach.
- **Extra contract cases** (cycle 2): thinking built but never attached keeps ticking; telemetry `thresholds` as a function that changes between updates; the parity test asserts Attach reaches the disabled state (the intended B13 change).
- **WebKit caveats** for the contract tests:
  - IME through `new KeyboardEvent('keydown', {key: 'Enter', isComposing: true})` in both engines; `keyCode` 229 through `Object.defineProperty` on the event;
  - `<details>` toggling awaited on `el.open` or the `toggle` event, never a fixed sleep; `summary` gets `list-style: none` plus the `::-webkit-details-marker` hide;
  - auto-fit asserted as "grows, then caps and scrolls", not pixel values;
  - telemetry expansion through `.focus()` and `:focus-within`, not hover.
- **Lane bookkeeping detail** (concrete after cycle 2):
  - `scripts/run-tests.sh`: `contracts_controls_files()` (about `:263`) subtracts a new `contracts_chat_pat`; `LANE_LIST`, `CANON_LANES`, `BUDGET` (300, provisional), the `resolve_lane` case, the header comments (`:23`, `:27`) and the error text (`:509`). The `contracts` alias and the `shared` complement use `contracts_all_pat`, so they need no change.
  - `tests/test_run_tests_lanes.py`: `LANES`, the hard-coded lane string (`:149-150`), and `test_contracts_lanes_are_exactly_the_ui_contract_files` (`:86-88`), which becomes a three-way union.
  - CLAUDE.md `:431`/`:433` (fifteen lanes become sixteen, fourteen named become fifteen) plus its bullets and table; `the_one/agents.md:179`; `ci/tasks/browser.yml:11`.
  - (The original text follows.) `contracts_controls_files()` gains a third subtraction (explicit globs `test_ui_composer*`, `test_ui_message*`, `test_ui_thinking*`, `test_ui_trace*`, `test_ui_telemetry*`, `test_ui_notice*`). `resolve_lane`, the `shared` complement and the `run-tests.sh` header comments are updated. `ci/tasks/browser.yml` says sixteen lanes.
- **Record for the consumer legs:** the `components.css` rules that relied on `.area-chat` specificity (`.msg.user.msg-from-peer` after `.msg.user`, the tool-in-trace override), listed in the flight log for 05a-05c's cascade checks.
- **Not separate rows:** attribution, `relabel`, `find` and `thinking` are sub-entries of their factory's row, with no own contract file. Each catalogue row's text says so. Every row keeps six cells.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only): approve with changes.** Applied as the amendments above. FD answers to the reviewer's questions:
  - thinking composes the message classes;
  - the area owns the send guards, and the control forwards the raw text;
  - telemetry keeps the server field names, including `max`;
  - old-look defaults, with options for the approved looks;
  - `.msg-pending-approval*` is dead CSS for 09a;
  - the `contracts-chat` budget is a provisional 300 s, never from a solo run.
- **A second cycle runs when batch B2 lands**, before the leg's Developer starts. The amendments are substantive (the handle semantics), and B2 changes the library this leg builds on (the copy confirmation, `badge.live`, the chip options). The leg stays `ready`, pending that pass.
- **Design review cycle 2** (Sonnet, 2026-10-27, against the landed B2 library, read-only): approve with changes. Applied:
  - **[medium]** the Outputs rewritten so no bullet contradicts the amendments;
  - **[medium]** the Copy reply through `copyButton` with one shared `liveEl` (FD answer to the reviewer's question) and its 2 s name revert;
  - **[medium]** Send's `blocked || busy` noted as an intended fix;
  - **[low]** the script order after `drawer.js`;
  - **[low]** the trace not reusing `disclosure` (expected);
  - **[low]** the row-number drift.

  The lane bookkeeping detail below is now concrete. This was the second and final cycle.
