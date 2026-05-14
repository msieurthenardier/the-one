# Leg: chat-trace-ui-and-thinking-reposition

**Status**: completed
**Flight**: [Chat Response Trace](../flight.md)

## Objective

Replace the inline `addMsg('tool', ...)` rendering in `chat.js` with a per-assistant-turn collapsible trace shell (Linear/Cursor-style) that groups `tool_call` + `tool_result` events under their parent assistant message — using the L02-introduced `parent_message_id` / `tool_call_id` discriminators. Move the live "thinking" indicator's insertion point so it can mount INSIDE a trace shell when one is in flight (rather than always as a sibling of `.messages`). Rehydrate the same trace structure from `session.history` on rejoin so live and replay produce visually-equivalent DOM. Streaming assistant-bubble path (chunk + pacing + markdown finalize) is untouched. Pixel-snapshot baselines WILL break (intentional — L04 regenerates them).

## Context

- **Flight + L02 pre-commits**: every `tool_call` / `tool_result` event broadcast over WS and projected from `session.history` carries `parent_message_id` (string) + `tool_call_id` (string). Frontend treats `parent_message_id` as an opaque grouping key. Live broadcast uses `f"{session.id}-msg-{i}"`; codec replay uses `f"replay-msg-{i}"` — different strings, same grouping behavior (frontend just buckets by equality).
- **L02→L03 contract**: events MAY arrive with `parent_message_id: null` (legacy DB rows from before L02 landed, OR `agent.messages` truncation edge case). L03 must NOT crash on these — render them as standalone bubbles outside any trace shell, OR under a synthetic "Legacy" trace shell. Implementation choice; the leg recommends standalone bubbles as the simpler default.
- **Current frontend state** (verified pre-leg via grep):
  - `the_one/interfaces/web/static/js/areas/chat.js:701-712 — "data.type === 'tool_call'" and "data.type === 'tool_result'"` — live event handlers calling `addMsg('tool', ...)` and `addMsg(data.is_error ? 'tool error' : 'tool', ...)`
  - `chat.js:207-208` — `renderHistory` replay path calling the same `addMsg` for `tool_call`/`tool_result` event types
  - `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js:createThinking` — creates the indicator element; CALLERS (in `chat.js`) append to `messagesEl` directly (`chat.js:335 — "messagesEl.appendChild(thinkingEl)"`)
  - `the_one/interfaces/web/static/css/chat.css:96-97 — ".msg.tool" + ".msg.tool.error"` — current tool-bubble styling (border-left accent, monospace, sm font)
  - `chat.css:91 — ".messages"` — flex column with `aria-live="polite"`, `role="log"` already on the parent
- **L02 carry-forward (working state)**: broad pytest exit code 0 in 91s; browser suite 315/35 unchanged. Test infrastructure is reliable; standard `pytest 2>&1 | tail -5` works (no summary-line-vs-exit-code workaround needed).
- **L01 carry-forward Known Issues** (do NOT touch):
  - `mission.md` KI #1: `app_with_agent` `.session-agent-badge` race blocking 2 `chat_with_messages` pixel baselines — addressed in L04, NOT here
  - `tests/test_mcp_sandbox_integration.py` F6-A5-deadlock skips — irrelevant to L03
  - `tests/browser/test_flow_provider_setup.py`, `tests/browser/test_flow_agent_crud.py` skips — irrelevant to L03
- **Pixel baselines WILL break**: changing `.msg.tool` from top-level to inside-trace-shell changes the rendered DOM. The 10 currently-passing pixel snapshots that include chat surface or tool events will need regeneration in L04. L03's job is to land the structural change; L03 is NOT expected to keep pixel baselines green.
- **Browser-suite (non-pixel) tests SHOULD remain green**: spot-checked existing tests — they query `data-testid="message"` and `.assistant` / `.user` class filters, NOT `.msg.tool`. As long as individual tool bubbles inside the trace shell preserve `data-testid="message"` and `.msg.tool` class, no browser-suite regressions expected.
- **L03 scope explicitly EXCLUDES**:
  - Any backend changes (L02 already landed those)
  - Pixel baseline regeneration (L04)
  - Operator HAT (L04)
  - The 2 known pixel-blocker tests (`test_snapshot_chat_with_messages[dark|light]`) — L04 fixes the `.session-agent-badge` race
  - Anthropic `thinking_blocks` rendering — explicitly out of mission scope

## Inputs

What exists before this leg runs:

- L01 + L01.5 + L02 changes uncommitted on `flight/05-chat-response-trace` branch (broad pytest 1622 passing in 91s; codec + WS broadcast carry paired discriminator; M07 OAuth `auth_required` event carries `parent_message_id`)
- Container `the-one` running and reachable via `docker exec`
- Frontend modules under `the_one/interfaces/web/static/js/areas/chat/`:
  - `message-bubble.js:renderMessage(cls, text, opts)` and `renderAttribution(side, text, ts)` — existing helpers (67 LOC)
  - `thinking-indicator.js:createThinking()` and `removeThinking(el)` — existing helpers (35 LOC); `createThinking` creates the indicator, CALLER appends to a parent
  - `history-buckets.js`, `welcome.js`, `telemetry-overlay.js` — sibling helpers (untouched)
- Main chat orchestrator at `the_one/interfaces/web/static/js/areas/chat.js` (814 LOC); event handlers in `connect()` at ~568-763; replay at `renderHistory` ~192-215
- CSS at `the_one/interfaces/web/static/css/chat.css` (164 LOC); `.msg.tool` styling at 96-97; `.messages` parent at 91
- F3.5 design-language tokens available (purple accent, shell-chrome surfaces, glass/bezel families) — trace shell should compose with these tokens for visual consistency
- Browser test suite baseline post-L02: 315 passed, 35 skipped, 12 deselected in ~260s

## Outputs

What exists after this leg completes:

- New module `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` exposing:
  - `App.chat.renderTrace(parentMessageId)` → returns a trace shell DOM element (with `<details>` collapsible)
  - `App.chat.appendToTrace(traceEl, msgEl)` → appends a tool message into a trace shell's body
- `the_one/interfaces/web/static/js/areas/chat.js` updated:
  - Live `tool_call` / `tool_result` handlers route through a `getOrCreateTrace(parentMessageId)` helper that finds the existing trace shell for a turn OR creates one and appends after the assistant bubble
  - `renderHistory` replay path buckets events by `parent_message_id` and renders each turn as a bubble + trace shell pair
  - `createThinking()` call sites can optionally mount the indicator inside a trace shell (default remains `.messages` for the initial-wait case)
  - Legacy events without `parent_message_id` render as standalone `addMsg('tool', ...)` bubbles (defensive)
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js` extended:
  - `createThinking()` signature unchanged (returns element)
  - The existing `removeThinking(el)` continues to work
  - A new tiny helper or convention so chat.js can target a non-`.messages` parent
- `the_one/interfaces/web/static/css/chat.css` extended:
  - `.trace-shell`, `.trace-shell .trace-toggle`, `.trace-shell .trace-body`, `.trace-shell .msg.tool`, `.trace-shell[open]` etc.
  - Composes with F3.5 design tokens
  - Keyboard-operable focus styles
- Container rebuilt via `make rebuild` so the running app serves the new JS/CSS
- Browser suite still 315 passing (no regression beyond the expected pixel-baseline diffs which are documented as L04-scope)
- Flight log updated with L03 entry and leg status `landed`
- **Pixel-snapshot baselines INTENTIONALLY BROKEN** — L04 regenerates

## Acceptance Criteria

- [ ] **New module exists**: `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` exists, exposes `App.chat.renderTrace` and `App.chat.appendToTrace` on the global `App.chat` namespace, matches the project's IIFE / `window.App` pattern (verify against `message-bubble.js` and `thinking-indicator.js` for style parity).
- [ ] **Module loaded by index.html**: the new module is added to the script-tag chain in `the_one/interfaces/web/static/index.html` after `chat/message-bubble.js` and before `chat.js`.
- [ ] **Trace shell renders for live turns with tool activity**: in a fresh chat session, when an agent step emits ≥ 1 `tool_call` event, the chat DOM contains exactly one `.trace-shell[data-parent-msg-id="..."]` element immediately after the assistant bubble for that turn. The trace shell contains `<details>` with a `<summary>` (`.trace-toggle`) and a body (`.trace-body`) housing the tool events.
- [ ] **Tool events grouped by parent_message_id**: within a single turn's trace shell, all tool_call and tool_result events with that turn's `parent_message_id` render as children. Multi-turn sessions produce multiple distinct trace shells.
- [ ] **tool_call_id pairing AND broadcast-order preservation**: each tool message element inside a trace shell has `data-tool-call-id="..."` (sourced from the event's `tool_call_id`). The rendered order within a trace shell MATCHES BROADCAST ORDER — `appendToTrace` is append-only and MUST NOT reorder events. The agent loop yields call → result sequentially (`agent/core.py:250-251` append-before-yield invariant), so today's natural order is "call followed by its result". L03's implementation must preserve this. The `data-tool-call-id` tagging provides L04-HAT verifiability and future debugging surface.
- [ ] **Replay matches live structure (structural assertion)**: after `renderHistory` for a session with multi-step tool activity, `document.querySelectorAll('.trace-shell').length` MUST EQUAL the count of distinct `parent_message_id` values in the replayed history that have at least one `tool_call` or `tool_result` event. This is a structural invariant that survives L04's pixel baseline regeneration. Verifiable via:
  ```js
  // In browser dev console after a multi-turn session loads:
  var ids = new Set();
  // Inspect each tool event's data attribute on the rendered DOM
  document.querySelectorAll('.trace-shell .msg.tool').forEach(function(el){
    ids.add(el.closest('.trace-shell').dataset.parentMsgId);
  });
  console.log('distinct parent ids:', ids.size, 'trace shells:', document.querySelectorAll('.trace-shell').length);
  // Both numbers should be equal.
  ```
  May also be locked down by a small browser test (see Suggestions). Visual screenshot comparison is secondary and not required for L03 sign-off.
- [ ] **Streaming bubble path intact**: `assistant_chunk` events still accumulate text into a single `.msg.assistant` bubble via the existing pacing queue; the L03 changes do NOT touch `currentStreamingMsg`, `pacingTimer`, `pendingChars`, `findSafeRenderBoundary`, `commitSafeBoundary`, `finalizeStreamingBubble`. Verified by `tests/browser/test_flow_streaming.py` passing unchanged.
- [ ] **Legacy `parent_message_id: null` events render gracefully**: if an event arrives with `parent_message_id === null` (e.g. from a pre-L02 DB row, or `agent.messages` truncation), it renders as a standalone `.msg.tool` bubble outside any trace shell. No crash, no console error.
- [ ] **`auth_required` event renders inside its trace shell**: the M07 OAuth consent button (per F5-L5 from M07 — the Login-required affordance at `chat.js:443 — "function renderLoginRequiredButton"`) renders INSIDE the corresponding turn's trace shell (or beneath the assistant bubble if no trace shell exists yet because the auth_required is the FIRST tool event of the turn). The button retains its existing `data-source-id` / `data-tool-call-id` / `data-resource-metadata-url` data attributes and click handler.
- [ ] **Thinking indicator default insertion preserved**: initial-wait thinking (post-`send()`, pre-first-chunk) appears in `.messages` directly, NOT inside any trace shell. This matches existing UX. The mission's "thinking indicator becomes part of the trace shell" objective is met by: (a) the helper API accepting a parent element (so future in-trace waiting states can mount inside a trace shell), AND (b) NO thinking indicator EVER appears as a sibling of `.msg.tool` elements outside a trace shell — tool events are always grouped under their trace shell.
- [ ] **Keyboard operability**: the `<details>`/`<summary>` collapse toggle is keyboard-operable via standard `Enter` / `Space` (browser-native). Focus is visible on `<summary>` per the existing focus-visible patterns in `chat.css`.
- [ ] **ARIA live-region semantics preserved**: `.messages` retains `role="log"` + `aria-live="polite"` + `aria-relevant="additions"` (verified unchanged at `chat.js:81 — "<div class=\"messages\" role=\"log\" aria-live=\"polite\""`). Tool events inside trace shells are STILL inside `.messages`, so screen-reader announcements still happen as additions land. (Note: collapsed `<details>` content's `aria-live` behavior varies by user agent; the project accepts this — screen-reader users can expand the trace to inspect.)
- [ ] **Browser suite stays green**: `timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -3` reports ≥ 315 passing, 35 skipped (unchanged from L02 baseline). NO new failures. The chat-focused tests `test_flow_chat.py`, `test_flow_markdown_chat.py`, `test_flow_streaming.py`, `test_flow_new_chat.py` MUST still pass.
- [ ] **Pixel suite delta is documented, not unexpected**: `timeout 120 docker exec the-one pytest tests/browser/ -m pixel --timeout=60 -q 2>&1 | tail -10` will show MORE failures than the F4-baseline 2 (the `chat_with_messages` pair). NEW failures from chat DOM restructure are EXPECTED. L03 documents the count delta in the flight log; L04 regenerates the baselines. Pixel tests do NOT block L03 sign-off.
- [ ] **Broad pytest stays clean**: `timeout 300 docker exec the-one pytest tests/ -m "not live and not browser and not pixel and not requires_bwrap" --timeout=30 -q 2>&1 | tail -3` reports the same 1622-passing baseline (no Python-side regressions; L03 is JS/CSS only).
- [ ] **`make rebuild` ran cleanly**: the container's served JS/CSS reflects the new code. (The Dockerfile `COPY the_one/` bakes files at build time; host edits don't surface until rebuild — verified pattern from `Makefile:rebuild`.)
- [ ] **No source-code changes outside scope**: only `the_one/interfaces/web/static/js/areas/chat.js`, `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` (new), `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js` (small edit), `the_one/interfaces/web/static/css/chat.css`, and `the_one/interfaces/web/static/index.html` (script tag) are touched. Specifically NO backend changes (`the_one/interfaces/web/app.py`, `the_one/db/codec.py` — those landed in L02).
- [ ] **WS-reconnect mid-turn does NOT duplicate shells**: if the WebSocket reconnects between `tool_call` events of one turn, exactly ONE `.trace-shell[data-parent-msg-id="..."]` exists per `parent_message_id` in the DOM after reconnect — not two. Achieved by `getOrCreateTrace`'s DOM-lookup fallback (see Implementation Guidance Step 3).
- [ ] **`auth_resolved` does not leave empty trace shells**: after the M07 OAuth flow completes successfully and `clearLoginRequiredButton` removes the inline button, if that removal leaves a `.trace-body` with ZERO children AND the trace shell's only content was the button, the empty shell is also removed. If the shell holds OTHER tool messages from the same turn, the shell stays.

## Verification Steps

How to confirm each criterion is met:

1. **Module exists + namespace** (Acceptance #1 + #2):
   ```bash
   test -f the_one/interfaces/web/static/js/areas/chat/trace-shell.js && echo "module exists"
   grep -n "App.chat.renderTrace\|App.chat.appendToTrace" the_one/interfaces/web/static/js/areas/chat/trace-shell.js
   grep -n "trace-shell.js" the_one/interfaces/web/static/index.html
   ```
   Expected: file exists; namespace methods defined; index.html includes the script tag.

2. **Live trace shell renders for tool turns** (Acceptance #3 + #4 + #5):
   - Add a temporary fixture-driven Playwright test in `tests/browser/test_flow_chat.py` (or run an ad-hoc check):
     ```python
     # Configure a mock provider with a tool_call response, send a message,
     # assert .trace-shell appears with data-parent-msg-id, contains the
     # expected .msg.tool elements with data-tool-call-id attributes.
     ```
   - Manual verification via dev container:
     1. `make rebuild`
     2. Open `http://localhost:8484` in browser, pick the mock agent
     3. Send a message that triggers a tool call (e.g. via the agent's seeded behavior)
     4. Inspect the DOM: `.trace-shell` element present after assistant bubble; contains `<details>` + tool messages with `data-tool-call-id` attributes

3. **Replay matches live structure** (Acceptance #6):
   - After step 2 above, hard-refresh the page (Cmd-Shift-R / Ctrl-Shift-R) to force a full session rejoin from `session_joined.history`
   - Verify the re-rendered DOM has the same number of `.trace-shell` elements with the same tool message counts

4. **Streaming bubble path intact** (Acceptance #7):
   ```bash
   timeout 60 docker exec the-one pytest tests/browser/test_flow_streaming.py -m browser --timeout=30 -q 2>&1 | tail -3
   ```
   Expected: all tests pass.

5. **Legacy null-parent rendering** (Acceptance #8):
   - Construct a unit-level check or manual DOM injection: dispatch a synthetic `tool_call` event with `parent_message_id: null` and verify it lands as a standalone `.msg.tool` outside any `.trace-shell`. May be done as a JS console snippet in the dev environment for L03 sign-off rather than a formal test.

6. **`auth_required` button in trace shell** (Acceptance #9):
   - This requires the M07 OAuth flow. Acceptance signoff is "the click handler still works AND the button appears inside the trace shell" — verified at L04 HAT. For L03, a code-read verification is sufficient: confirm `renderLoginRequiredButton` mounts the button inside a trace shell (or beneath the assistant if no shell exists yet) rather than directly to `.messages`.

7. **Thinking indicator placement** (Acceptance #10):
   - Manual DOM inspection during a chat send: after click, `.thinking-indicator` should appear under `.messages` directly (or inside the trace shell if a trace shell is in flight from a prior iteration — not the initial case). NEVER as a sibling of `.msg.tool` outside any shell.

8. **Keyboard operability** (Acceptance #11):
   - Click into the chat, tab to a trace shell's summary toggle, press Enter or Space — the trace expands/collapses. Focus ring is visible.

9. **ARIA semantics** (Acceptance #12):
   ```bash
   grep -n 'role="log"\|aria-live\|aria-relevant' the_one/interfaces/web/static/js/areas/chat.js
   ```
   Expected: `chat.js:81 — "<div class=\"messages\" role=\"log\" aria-live=\"polite\" aria-relevant=\"additions\" aria-atomic=\"false\""` line unchanged.

10. **Browser suite green** (Acceptance #13):
    ```bash
    timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -3
    ```
    Expected: `315 passed, 35 skipped, 12 deselected in ~260s` (matching L02 baseline).

11. **Pixel delta documented** (Acceptance #14):
    ```bash
    timeout 120 docker exec the-one pytest tests/browser/ -m pixel --timeout=60 -q 2>&1 | tail -10
    ```
    Capture the failure count + names of failing snapshots into the flight log. Expected delta: at least the 2 `chat_with_messages` pre-existing failures plus any chat-area snapshots that include tool bubbles (the new shell DOM differs from baseline). L04 regenerates.

12. **Broad pytest unchanged** (Acceptance #15):
    ```bash
    timeout 300 docker exec the-one pytest tests/ -m "not live and not browser and not pixel and not requires_bwrap" --timeout=30 -q 2>&1 | tail -3
    ```
    Expected: `1622 passed, 4 skipped, 370 deselected in ~91s` (matches L02 baseline; L03 doesn't touch Python).

13. **`make rebuild` ran cleanly** (Acceptance #16):
    ```bash
    make rebuild 2>&1 | tail -10
    docker exec the-one ls /app/the_one/interfaces/web/static/js/areas/chat/ | grep trace-shell
    ```
    Expected: rebuild succeeds; the new module file is inside the running container.

14. **Scope check** (Acceptance #17):
    ```bash
    git diff --name-only main -- \
      ':(exclude)missions/' \
      ':(exclude)tests/' \
      ':(exclude)the_one/interfaces/web/static/js/areas/chat.js' \
      ':(exclude)the_one/interfaces/web/static/js/areas/chat/' \
      ':(exclude)the_one/interfaces/web/static/css/chat.css' \
      ':(exclude)the_one/interfaces/web/static/index.html' \
      ':(exclude)the_one/interfaces/web/app.py' \
      ':(exclude)the_one/db/codec.py'
    ```
    Expected: empty (no out-of-scope changes; app.py and codec.py are excluded because L02 changes there are uncommitted carry-forward).

## Implementation Guidance

### Step 1 — Create `chat/trace-shell.js`

New file `the_one/interfaces/web/static/js/areas/chat/trace-shell.js`. Follow the IIFE pattern from `message-bubble.js` and `thinking-indicator.js`:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // Build a per-assistant-turn trace shell.
  //
  // Structure:
  //   <div class="trace-shell" data-parent-msg-id="..." data-testid="trace-shell">
  //     <details>
  //       <summary class="trace-toggle">
  //         <span class="trace-summary">Tool activity</span>
  //         <span class="trace-count" aria-hidden="true">0</span>
  //       </summary>
  //       <div class="trace-body"></div>
  //     </details>
  //   </div>
  //
  // Keyboard-operable for free via native <details>/<summary>.
  // `data-parent-msg-id` lets chat.js find an existing shell to append into.
  function renderTrace(parentMessageId) {
    var shell = document.createElement('div');
    shell.className = 'trace-shell';
    shell.dataset.parentMsgId = parentMessageId;
    shell.setAttribute('data-testid', 'trace-shell');
    var details = document.createElement('details');
    var summary = document.createElement('summary');
    summary.className = 'trace-toggle';
    var label = document.createElement('span');
    label.className = 'trace-summary';
    label.textContent = 'Tool activity';
    var count = document.createElement('span');
    count.className = 'trace-count';
    count.setAttribute('aria-hidden', 'true');
    count.textContent = '0';
    summary.appendChild(label);
    summary.appendChild(count);
    var body = document.createElement('div');
    body.className = 'trace-body';
    details.appendChild(summary);
    details.appendChild(body);
    shell.appendChild(details);
    return shell;
  }

  // Append a tool message into a trace shell's body. Updates the count
  // shown in the summary. The msgEl is expected to be a .msg.tool element
  // (or .msg.tool.error) with data-testid="message" and a data-tool-call-id
  // attribute set by the caller.
  function appendToTrace(traceEl, msgEl) {
    if (!traceEl || !msgEl) return;
    var body = traceEl.querySelector('.trace-body');
    if (!body) return;
    body.appendChild(msgEl);
    var count = traceEl.querySelector('.trace-count');
    if (count) {
      count.textContent = String(body.children.length);
    }
  }

  window.App.chat.renderTrace = renderTrace;
  window.App.chat.appendToTrace = appendToTrace;
})();
```

### Step 2 — Register the script in index.html

Edit `the_one/interfaces/web/static/index.html`: add `<script src="static/js/areas/chat/trace-shell.js"></script>` (or whatever path convention matches existing tags) in the same `<script>` block where `message-bubble.js` / `thinking-indicator.js` are listed. Verify by grepping for `message-bubble.js` to find the insertion point.

### Step 3 — Update `chat.js` live event handlers (`tool_call` / `tool_result`)

Add helpers near the top of `connect()`. **Important**: `traceShells` is per-`connect()`-closure (resets on WebSocket reconnect). The DOM-lookup fallback inside `getOrCreateTrace` makes the cache self-healing across reconnects so shells aren't duplicated when WS drops mid-turn:

```js
// L03: bucket of trace shells keyed by parent_message_id.
// On first tool event for a parent, create the shell and append to .messages
// after the assistant bubble. Subsequent events route to the same shell.
// Per-WS-connection closure scope; rebuilt on reconnect. DOM-lookup fallback
// (cycle-1 review fix) handles the reconnect-mid-turn case where the bucket
// resets but the shell from the previous connection is still in DOM.
var traceShells = Object.create(null);

function getOrCreateTrace(parentMessageId) {
  if (!parentMessageId) return null;
  if (traceShells[parentMessageId]) return traceShells[parentMessageId];
  // Self-heal across WS reconnect: if a shell for this parent already
  // exists in the DOM from a prior connection's closure, re-seed the
  // bucket from DOM rather than minting a duplicate.
  var existing = messagesEl.querySelector(
    '.trace-shell[data-parent-msg-id="' + cssEscape(parentMessageId) + '"]'
  );
  if (existing) {
    traceShells[parentMessageId] = existing;
    return existing;
  }
  var shell = App.chat.renderTrace(parentMessageId);
  messagesEl.appendChild(shell);
  traceShells[parentMessageId] = shell;
  return shell;
}

function buildToolMsg(text, isError, toolCallId) {
  var el = App.chat.renderMessage(isError ? 'tool error' : 'tool', text);
  if (toolCallId) el.dataset.toolCallId = toolCallId;
  return el;
}
```

The `cssEscape` helper already exists at `chat.js:362` (used by `clearLoginRequiredButton`'s selector escaping). Reuse it.

Replace the existing `tool_call` handler (around `chat.js:701-708`):

```js
else if (data.type === 'tool_call') {
  hideThinking();
  finalizeStreamingBubble();
  var argsText = '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
  var trace = getOrCreateTrace(data.parent_message_id);
  var msg = buildToolMsg(argsText, false, data.tool_call_id);
  if (trace) {
    App.chat.appendToTrace(trace, msg);
  } else {
    // Legacy / null parent_message_id — render standalone.
    messagesEl.appendChild(msg);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
```

Replace the existing `tool_result` handler (around `chat.js:709-713`):

```js
else if (data.type === 'tool_result') {
  finalizeStreamingBubble();
  var trace = getOrCreateTrace(data.parent_message_id);
  var msg = buildToolMsg(data.content, data.is_error, data.tool_call_id);
  if (trace) {
    App.chat.appendToTrace(trace, msg);
  } else {
    messagesEl.appendChild(msg);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
```

### Step 4 — Update `chat.js` `renderHistory` replay path

Existing replay at `chat.js:192-215` walks events linearly. Rewrite to bucket by `parent_message_id`:

```js
function renderHistory(history, agentName) {
  messagesEl.setAttribute('aria-busy', 'true');
  messagesEl.innerHTML = '';
  traceShells = Object.create(null);  // reset bucket on replay
  var agentLabel = agentName || 'agent';
  for (var i = 0; i < history.length; i++) {
    var ev = history[i];
    var histOpts = { ts: ev.ts || null };
    if (ev.type === 'user') {
      var cls = ev.source === 'api' ? 'user api' : 'user';
      addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, 'You', histOpts);
    } else if (ev.type === 'assistant') {
      addMsg('assistant', ev.content, agentLabel, histOpts);
    } else if (ev.type === 'tool_call') {
      var argsText = '> ' + ev.name + '(' + Object.entries(ev.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
      var trace = getOrCreateTrace(ev.parent_message_id);
      var msg = buildToolMsg(argsText, false, ev.tool_call_id);
      if (trace) App.chat.appendToTrace(trace, msg);
      else messagesEl.appendChild(msg);
    } else if (ev.type === 'tool_result') {
      var trace2 = getOrCreateTrace(ev.parent_message_id);
      var msg2 = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id);
      if (trace2) App.chat.appendToTrace(trace2, msg2);
      else messagesEl.appendChild(msg2);
    } else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
      addMsg('system', ev.content, null, histOpts);
    }
  }
  messagesEl.removeAttribute('aria-busy');
}
```

### Step 5 — Update `renderLoginRequiredButton` to mount in trace shell

The existing function at `chat.js:443 — "function renderLoginRequiredButton"` appends to `messagesEl`. Update to use the same trace-bucket helper:

```js
function renderLoginRequiredButton(data) {
  clearLoginRequiredButton(data);
  if (data.source_id && data.source_name) {
    sourceNames[data.source_id] = data.source_name;
  }
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-filled-primary login-required-btn';
  btn.dataset.sourceId = data.source_id || '';
  btn.dataset.toolCallId = data.tool_call_id || '';
  btn.dataset.resourceMetadataUrl = data.resource_metadata_url || '';
  if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
  var label = data.source_name
    || (data.source_id && sourceNames[data.source_id])
    || data.source_id
    || '<unknown>';
  btn.textContent = 'Login required for ' + label;
  btn.addEventListener('click', function () {
    startLoginFlow(data);
  });
  // L03: mount in the trace shell for this turn, if one exists.
  var trace = getOrCreateTrace(data.parent_message_id);
  if (trace) {
    App.chat.appendToTrace(trace, btn);
  } else {
    messagesEl.appendChild(btn);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
```

`clearLoginRequiredButton` already queries `messagesEl.querySelectorAll(...)` — the selector still works because the buttons live inside `.messages` regardless of trace nesting (`.messages` is the ancestor of all trace shells).

**Empty-trace cleanup**: after removing the button, walk up from its former parent and remove the enclosing `.trace-shell` IF its `.trace-body` is now empty. Prevents an empty shell from lingering after a successful `auth_resolved`:

```js
function clearLoginRequiredButton(data) {
  var sid = data && data.source_id ? data.source_id : null;
  var sel = sid
    ? '.login-required-btn[data-source-id="' + cssEscape(sid) + '"]'
    : '.login-required-btn';
  var existing = messagesEl.querySelectorAll(sel);
  for (var i = 0; i < existing.length; i++) {
    var btn = existing[i];
    var parent = btn.parentNode;
    if (parent) parent.removeChild(btn);
    // L03: if the button was inside a now-empty trace-body, also drop
    // the enclosing trace shell so an empty chrome doesn't linger.
    if (parent && parent.classList && parent.classList.contains('trace-body') && parent.children.length === 0) {
      var shell = parent.closest('.trace-shell');
      if (shell && shell.parentNode) {
        var key = shell.dataset.parentMsgId;
        shell.parentNode.removeChild(shell);
        if (key) delete traceShells[key];
      }
    }
  }
}
```

### Step 6 — Update `chat.css`

Add trace-shell styles near the existing `.msg.tool` block (around `chat.css:96-97`). Suggested shape (project-style; align with F3.5 design tokens):

```css
@layer areas {
  /* ... existing styles ... */

  /* L03: per-assistant-turn trace shell. <details>/<summary> for native
     keyboard support; styled to compose with F3.5 design tokens. */
  .area-chat .trace-shell {
    align-self: flex-start;
    max-width: 85%;
    margin-top: -4px;  /* visually attach to the assistant bubble above */
    font-size: var(--font-size-body-sm);
  }
  .area-chat .trace-shell details {
    border-left: 2px solid var(--border);
    padding-left: 8px;
  }
  .area-chat .trace-shell summary.trace-toggle {
    cursor: pointer;
    color: var(--fg-muted);
    font-family: var(--font-family-mono);
    letter-spacing: 0.02em;
    padding: 4px 0;
    user-select: none;
    list-style: none;  /* hide default disclosure marker */
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .area-chat .trace-shell summary.trace-toggle::-webkit-details-marker { display: none; }
  .area-chat .trace-shell summary.trace-toggle::before {
    content: '▸';
    transition: transform 0.15s ease;
    color: var(--accent);
    font-size: 0.85em;
  }
  .area-chat .trace-shell details[open] summary.trace-toggle::before {
    transform: rotate(90deg);
  }
  .area-chat .trace-shell summary.trace-toggle:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 2px;
  }
  .area-chat .trace-shell .trace-count {
    color: var(--fg-faint);
    font-variant-numeric: tabular-nums;
  }
  .area-chat .trace-shell .trace-body {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 0 4px 0;
  }
  /* Override the standalone .msg.tool's max-width inside a trace — the
     trace shell already constrains width. */
  .area-chat .trace-shell .trace-body .msg.tool {
    max-width: none;
    border-left: 2px solid var(--accent);
  }
  .area-chat .trace-shell .trace-body .msg.tool.error {
    border-left-color: var(--status-danger);
  }
  .area-chat .trace-shell .trace-body .login-required-btn {
    align-self: flex-start;
  }
}
```

Operator may iterate on aesthetics in L04 HAT.

### Step 7 — Thinking-indicator parameterization (small)

`thinking-indicator.js:createThinking()` returns an element. The caller (`chat.js:333-337 — "function showThinking()"`) currently does `messagesEl.appendChild(thinkingEl)`. For the mission's "thinking indicator becomes part of the trace shell" objective, expose flexibility by NOT hardcoding the parent at the helper level (already true today — `createThinking` doesn't append; the caller does). The `showThinking()` in chat.js stays appending to `.messages` for the initial-wait case. NO change needed in `thinking-indicator.js` itself — the API is already parent-agnostic.

The mission's objective is satisfied because: (a) the helper is parent-agnostic (any caller can mount it anywhere), (b) tool events NEVER appear as siblings of the thinking indicator outside a trace shell — they always live inside a shell. The thinking indicator therefore never visually competes with tool events.

Document this in the leg's session notes: no `thinking-indicator.js` edit was required; the parameter-by-convention pattern (helper returns element, caller mounts) was already in place.

### Step 8 — Rebuild + verify

```bash
make rebuild
# Confirm new module is in the running container:
docker exec the-one ls /app/the_one/interfaces/web/static/js/areas/chat/ | grep trace-shell
# Confirm new module is actually being served (verify-serving doesn't curl it):
docker exec the-one curl -fsS http://localhost:8484/static/js/areas/chat/trace-shell.js -o /dev/null && echo "trace-shell.js served OK"
```

Note: `make rebuild`'s `verify-serving` target curls `/api/info` and a list of admin sub-modules but does NOT curl chat submodules. The explicit curl above closes the gap.

### Step 9 — Run verification suite

In order:
1. Streaming-bubble check: `timeout 60 docker exec the-one pytest tests/browser/test_flow_streaming.py -m browser --timeout=30 -q`
2. Chat-area focused: `timeout 120 docker exec the-one pytest tests/browser/test_flow_chat.py tests/browser/test_flow_markdown_chat.py tests/browser/test_flow_new_chat.py -m browser --timeout=30 -q`
3. Full browser suite: `timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -3`
4. Broad pytest sanity: `timeout 300 docker exec the-one pytest tests/ -m "not live and not browser and not pixel and not requires_bwrap" --timeout=30 -q 2>&1 | tail -3`
5. Pixel suite (expect new failures — document only): `timeout 120 docker exec the-one pytest tests/browser/ -m pixel --timeout=60 -q 2>&1 | tail -10`

### Step 10 — Update artifacts

- Flight log: append `### L03 — chat-trace-ui-and-thinking-reposition` Leg Progress entry with file diff summary, test counts, pixel delta (which baselines newly fail), and brief session notes.
- Leg artifact: status header `in-flight` → `landed`.
- Flight artifact: check off `chat-trace-ui-and-thinking-reposition` in the Legs list.
- DO NOT COMMIT.
- Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **No `parent_message_id` on event (legacy/null)**: render as standalone `.msg.tool` outside any trace shell. `getOrCreateTrace` returns `null` for falsy parent ids; caller falls through to `messagesEl.appendChild(msg)`. No crash.
- **`parent_message_id` arrives before any assistant content** (shouldn't happen with current agent loop, but defensive): trace shell mounts after the LAST element of `.messages` — which would be the user message. Visually awkward but not broken; the next assistant_chunk will create the assistant bubble AFTER the trace shell, which is wrong order. **Mitigation**: in `getOrCreateTrace`, when creating a NEW shell, append it to `.messages` (current behavior) — this assumes assistant bubble already exists. Add a defensive comment: if the agent ever emits `tool_call` before `assistant`, fix the order in a future leg.
- **Multiple tool_call events for one turn**: `getOrCreateTrace` returns the same shell for the same `parent_message_id`. All tool events for the turn append to the same shell. Correct.
- **Multiple tool_call events with the SAME tool_call_id** (multi-broadcast / replay overlap on rejoin during in-flight turn): possible if the live broadcast and the rejoin snapshot disagree on state. The frontend MAY render duplicates. **Mitigation**: `clearLoginRequiredButton(data)` pattern (existing) — apply the same idempotency to tool message rendering. Implementation choice: optional for L03; if duplicates surface during L04 HAT, fix then.
- **WebSocket reconnect mid-turn** (RESOLVED by Step 3 DOM-lookup fallback): if WS drops between two tool events of one turn, the second event arrives on a fresh `connect()` closure with an empty `traceShells` bucket. Without mitigation, a SECOND shell would be minted for the same parent_message_id (the old shell is still in DOM but unreachable from the new bucket). The DOM-lookup fallback in `getOrCreateTrace` queries the DOM before creating, so the new bucket re-seeds from the existing shell — no duplication.
- **In-flight rejoin namespace-disjoint split** (ACCEPTED LIMITATION): L02 deliberately uses different `parent_message_id` namespace prefixes for live (`{session.id}-msg-N`) and replay (`replay-msg-N`). When `session_joined.is_processing === true`, the rejoin's `history` field carries replay-shape ids while post-rejoin live events carry live-shape ids. Same logical turn → DIFFERENT `parent_message_id` strings → DIFFERENT trace shells → visual split for the narrow window the turn is still running on the server. **Accepted** for L03 because: (a) it only occurs when joining a session WHILE a turn is in flight, (b) a refresh AFTER the turn lands (after `done` broadcasts) shows uniform replay-shape ids and the split disappears, (c) the events themselves are correctly grouped within each shell. L04 HAT may verify this is tolerable; if not, a follow-up flight can align the namespaces (would require amending L02 + new codec signature change). Do NOT attempt to reconcile in L03 — it would violate L02's intentional namespace boundary.
- **Cross-area routing**: when the user switches to Admin and back to Chat, `chat.activate()` is called. The existing flow re-uses the WebSocket and `traceShells` bucket. Bucket should be reset only on `session_joined` (new session OR rejoin) — done in `renderHistory`. If a partial state slips through, the bucket may contain stale shells; tolerable but not ideal. Document in session notes.
- **`auth_required` is the FIRST tool event of a turn**: no trace shell exists yet (no prior tool_call established one). `getOrCreateTrace(parent_message_id)` will CREATE a shell on the auth_required's parent_message_id. The Login-required button mounts inside it. Subsequent tool events join the same shell. This is correct behavior — the trace shell exists to hold ALL tool-flow elements for the turn, including auth_required.
- **Streaming bubble interleaving**: the `currentStreamingMsg` is per-iteration. It's finalized on every `tool_call` (existing behavior). The trace shell appends AFTER the just-finalized assistant bubble. Order: user → assistant content (streaming or final) → trace shell with tool events → next assistant bubble (if multi-turn) → next trace shell. Verified visually OK.
- **L01 carry-forward sandbox skips still in place**: do NOT touch `tests/test_mcp_sandbox_integration.py`. They remain quarantined for the F6-A5-deadlock issue.
- **`tests/browser/test_oauth_modal_flow.py` synthesizes `auth_required` events WITHOUT `parent_message_id`**: those tests inject events directly via WS without backend-derived ids. With L03's `getOrCreateTrace(undefined) → null` fallback, those buttons still mount on `messagesEl` directly. The existing `.login-required-btn` locator queries (6 call sites in the file) continue to match because `.messages` is the ancestor of all login buttons in either path. Non-regression case.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` — NEW file, ~50 LOC, module exposing `App.chat.renderTrace` / `App.chat.appendToTrace`
- `the_one/interfaces/web/static/index.html` — 1 new `<script>` tag for the trace-shell module
- `the_one/interfaces/web/static/js/areas/chat.js` — modify `connect()` to add `traceShells` bucket + `getOrCreateTrace` + `buildToolMsg` helpers; replace 2 event handlers (`tool_call`, `tool_result`); update `renderLoginRequiredButton`; update `renderHistory`. Expected delta: ~60-80 LOC modified
- `the_one/interfaces/web/static/css/chat.css` — add `.trace-shell` and descendant rules. Expected delta: ~50 LOC added
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js` — NO change expected (already parent-agnostic); document this in session notes
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight-log.md` — append L03 entry
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight.md` — check off `chat-trace-ui-and-thinking-reposition`
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/legs/03-chat-trace-ui-and-thinking-reposition.md` — status header update

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (run every verification step where automated; manual checks for #2, #3, #5, #7, #8 — document in flight log)
- [ ] Browser suite green (no regressions vs L02 baseline)
- [ ] Pixel delta documented in flight log (not blocking — L04 regenerates)
- [ ] Broad pytest unchanged
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`
- [ ] Check off this leg in flight.md
- [ ] DO NOT commit (per agentic-workflow: review + commit are batched at flight close)
- [ ] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

12 source-code citations verified against current code at leg design time:

| Citation | Class | Notes |
|---|---|---|
| `the_one/interfaces/web/static/js/areas/chat.js:701-708` (live `tool_call` handler) | OK | Verified — `else if (data.type === 'tool_call') { hideThinking(); finalizeStreamingBubble(); addMsg('tool', ...) }` |
| `the_one/interfaces/web/static/js/areas/chat.js:709-713` (live `tool_result` handler) | OK | Verified — `else if (data.type === 'tool_result') { finalizeStreamingBubble(); addMsg(...) }` |
| `the_one/interfaces/web/static/js/areas/chat.js:207-208` (`renderHistory` tool branches) | OK | Verified — `else if (ev.type === 'tool_call') addMsg('tool', ...)` and `else if (ev.type === 'tool_result') addMsg(...)` |
| `the_one/interfaces/web/static/js/areas/chat.js:443` (`renderLoginRequiredButton`) | OK | Verified — function definition at line 443; appends to `messagesEl` directly |
| `the_one/interfaces/web/static/js/areas/chat.js:81` (`.messages` ARIA attributes) | OK | Verified — `<div class="messages" role="log" aria-live="polite" aria-relevant="additions" aria-atomic="false">` |
| `the_one/interfaces/web/static/js/areas/chat.js:333-337` (`showThinking`) | OK | Verified — `messagesEl.appendChild(thinkingEl)` at line 335 |
| `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js:createThinking` | OK | Verified — returns element; caller appends to a parent |
| `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage` | OK | Verified — public API on `App.chat.renderMessage` |
| `the_one/interfaces/web/static/css/chat.css:91` (`.messages` flex parent) | OK | Verified — `.area-chat .messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }` |
| `the_one/interfaces/web/static/css/chat.css:96-97` (`.msg.tool` + `.msg.tool.error`) | OK | Verified — existing tool-bubble styling |
| `the_one/interfaces/web/static/css/chat.css:138` (`.login-required-btn`) | OK | Verified — `.area-chat .messages .login-required-btn { align-self: flex-start; }` |
| `Makefile:rebuild` (target name) | OK | Verified — `rebuild: ## Rebuild image + restart (REQUIRED after editing JS/CSS/Python)` |

All citations OK. No drift; no rewrites required.
