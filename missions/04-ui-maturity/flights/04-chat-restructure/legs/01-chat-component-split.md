# Leg: 01-chat-component-split

**Status**: completed
**Flight**: [Chat Restructure — Components, Streaming & Markdown](../flight.md)

## Objective

Split `static/js/areas/chat.js` (782 LOC) into a closure-state orchestrator (~400 LOC) plus five pure-helper IIFE sub-modules under `static/js/areas/chat/` that attach to a new `App.chat.{name}` namespace, with no observable behaviour change.

## Context

- F4 design decision (flight.md "Design Decisions"): the chat split is a pure refactor; pure helpers extract DOM-construction logic, and callback-injected helpers receive what would otherwise be closure references.
- F4 design decision: load order is established by `<script>` tag concatenation (no bundler). `index.html` must load helpers BEFORE `chat.js`.
- F4 design decision: a 3-line `App.markdown` stub lands in this leg at `static/js/markdown.js` so any leg-01/leg-02 test that touches `App.markdown` does not trip. Leg 03 replaces the stub with the real implementation.
- F4 design decision: behavior preservation contract — 100% of existing browser tests pass without modification; all `data-testid` attributes preserved on their original elements.
- F3 keyboard-operability work (closed in flight 03) lives at sites this leg moves: welcome listbox arrow-key navigation, session-item Enter/Space + delete-button focus-within reveal. The split must preserve the keydown handlers and class hooks (`.session-item`, `.delete`, `.chat-welcome-item`, etc.) verbatim — leg 02 renames classes; leg 01 does not.

## Inputs

- `static/js/areas/chat.js` exists at 782 LOC with the structure documented in the flight spec (closure state in `init`, plus `serializeState`, `hydrateState`, `activate`, `deactivate` lifecycle hooks).
- `static/js/areas/` contains only `chat.js`, `studio.js`, `admin.js` (no `chat/` subdirectory yet).
- `static/index.html` loads scripts in this order: `theme.js` (head) → `app.js` → `icons.js` → `areas/chat.js` → `areas/studio.js` → `areas/admin.js`.
- `App.icons`, `App.icon`, `App.router`, `App.registerArea` are available at runtime (set up by `app.js` + `icons.js`).
- All F1-F3 browser tests (≥ 32) and unit tests (≥ 393) pass on the current branch tip.

## Outputs

- `static/js/markdown.js` exists with a 3-line stub: `(function(){window.App=window.App||{};window.App.markdown={};})();`.
- `static/js/areas/chat/` directory contains 5 helper files, each its own IIFE that attaches to `window.App.chat`:
  - `welcome.js` — `App.chat.welcomeLink`, `App.chat.renderWelcomeList`
  - `history-buckets.js` — `App.chat.BUCKET_ORDER`, `App.chat.BUCKET_LABELS`, `App.chat.startOfDay`, `App.chat.bucketForSession`, `App.chat.buildSessionItem`, `App.chat.renderSessionList`
  - `message-bubble.js` — `App.chat.renderMessage`, `App.chat.renderAttribution`
  - `telemetry-overlay.js` — `App.chat.renderTelemetry`, `App.chat.updateTelemetry`, `App.chat.fmtTokens`
  - `thinking-indicator.js` — `App.chat.createThinking`, `App.chat.removeThinking` (`THINKING_FRAMES` stays module-private inside the IIFE)
- `static/js/areas/chat.js` retains closure state + lifecycle + WS wiring; LOC drops from 782 to ≤ 450 (target ~400). Helpers are called via `App.chat.{name}(...)`.
- `static/index.html` script order updated: `app.js` → `icons.js` → `markdown.js` → `areas/chat/welcome.js` → `areas/chat/history-buckets.js` → `areas/chat/message-bubble.js` → `areas/chat/telemetry-overlay.js` → `areas/chat/thinking-indicator.js` → `areas/chat.js` → `areas/studio.js` → `areas/admin.js`.
- All `data-testid` attributes preserved on the same DOM elements they were on before.
- `the_one/agents.md` gains a brief subsection documenting the `App.chat` namespace contract (signature + ownership of closure state).

## Acceptance Criteria

- [x] `static/js/markdown.js` exists with the 3-line `App.markdown = {}` stub.
- [x] `static/js/areas/chat/` exists and contains exactly 5 files: `welcome.js`, `history-buckets.js`, `message-bubble.js`, `telemetry-overlay.js`, `thinking-indicator.js`.
- [x] Each helper file is ≤ 150 LOC. (welcome 91; history-buckets 135; message-bubble 27; telemetry-overlay 83; thinking-indicator 35)
- [x] Each helper file is an IIFE that does `window.App = window.App || {}; window.App.chat = window.App.chat || {};` before attaching its functions to `window.App.chat`.
- [x] `static/js/areas/chat.js` LOC ≤ 450 (target ~400) measured by `wc -l`. (441 LOC)
- [x] `static/index.html` `<script>` tag order matches the Outputs section above.
- [x] All 7 `data-testid` attributes from the pre-leg chat.js (`agent-select`, `chat-welcome`, `new-chat-btn`, `chat-input`, `chat-send-btn`, `message`, `thinking-indicator`) are present on their original DOM elements at runtime.
- [x] `pytest tests/` collects + passes the same exact count as on `bef9ba0` (393 selected; the default marker filter excludes `tests/browser/`). Pure refactor — no count change permitted.
- [x] `pytest -m browser tests/browser/` collects + passes the same exact count as on `bef9ba0` (32 selected). Disjoint from the run above. Pure refactor — no count change permitted.
- [x] `the_one/agents.md` contains a new subsection under `## Architecture Overview` or `## Module Map` (designer's choice) titled "App.chat helpers" or similar, listing each helper signature and its closure-coupling category (PURE vs CALLBACK-INJECTED).
- [x] No new external dependencies introduced (`pyproject.toml` unchanged; no new `<link>` or `<script>` tags pointing to remote URLs).
- [ ] Manual smoke check (run the app, open `#chat`): welcome canvas renders in all four states (no-providers, no-agents, both, ready); session list renders with bucket headings; thinking indicator appears on send and clears on response; telemetry overlay updates on `usage` event; new-chat button starts a new conversation. _(Deferred: orchestrator-driven leg; functional coverage delivered by the 32-case browser suite. Flight Director or human can run interactively post-handoff.)_

## Verification Steps

- File presence: `ls static/js/areas/chat/` shows 5 files; `ls static/js/markdown.js` exists.
- Per-file LOC check: `wc -l static/js/areas/chat/*.js` shows each ≤ 150; `wc -l static/js/areas/chat.js` shows ≤ 450.
- IIFE pattern check: `grep -L "(function" static/js/areas/chat/*.js` returns no output (every file matches the IIFE pattern).
- Namespace check: `grep -L "window.App.chat" static/js/areas/chat/*.js` returns no output (every helper attaches to the namespace).
- Stub check: `cat static/js/markdown.js` shows the 3-line stub literally (or visually equivalent — a one-line variant is acceptable).
- Script-order check: `grep "<script\|src=\".*\.js\"" static/index.html` enumerates script tags in the documented order; `markdown.js` appears before any `areas/chat/*.js`; all `areas/chat/*.js` appear before `areas/chat.js`.
- testid check: `grep -h "data-testid" static/js/areas/chat.js static/js/areas/chat/*.js` shows all 7 ids on their original element constructions.
- Tests: `pytest --timeout=60 tests/` passes with no new failures. `pytest --timeout=120 -m browser tests/browser/` passes with no new failures. (Use `--timeout` to fail fast on hangs per the implementation prompt.)
- Manual smoke (Flight Director or human): start `the-one` web server, open `http://localhost:8080/#chat`, verify the four welcome canvas states + session list bucketing + thinking indicator + telemetry overlay + new-chat header button.

## Implementation Guidance

### 1. Create the `App.markdown` stub

Create `static/js/markdown.js`:

```js
(function () { window.App = window.App || {}; window.App.markdown = {}; })();
```

This is intentionally minimal — leg 03 replaces it with the real implementation. The stub guards any leg-01/leg-02 test that references `App.markdown` from tripping on `undefined`.

### 2. Create `static/js/areas/chat/` and the 5 helper files

Each helper file follows this template:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // ... helper functions assigned to App.chat.{name}
})();
```

#### `welcome.js`

Move from chat.js:
- `welcomeLink(text, areaId)` — verbatim move (lines 284-290). Becomes `App.chat.welcomeLink`. **PURE**.
- `renderWelcomeList()` — refactored to take parameters explicitly (was a closure over `welcomeEl`, `welcomeListEl`, `setupState`, `availableAgents`, `startSessionWith`). New signature: `App.chat.renderWelcomeList(welcomeEl, welcomeListEl, agents, setupState, callbacks)` where `callbacks = { onStart: function(agentName) }`. **CALLBACK-INJECTED**. Replace the inline `startSessionWith(agent.name)` calls with `callbacks.onStart(agent.name)`. The roving-tabindex keydown listener (lines 293-312 in current chat.js) STAYS in chat.js — it's bound once at init and references `welcomeListEl` via the local closure, so leaving it in chat.js avoids needing to pass an event-handler reference back out. (Acceptable because the keydown handler is a one-shot binding, not per-render work.)

The `welcomeEl.querySelector('.chat-welcome-prompt')` call inside the function is fine to keep — `welcomeEl` is now a parameter.

**Convention for all helper files**: inside an IIFE, when one helper calls another in the same file, call it directly by its local name (not via `App.chat.{name}`). Declare callees before callers, or use `function` declarations so hoisting handles it. Apply this uniformly — `welcome.js`, `history-buckets.js`, and `telemetry-overlay.js` all have intra-file calls.

#### `history-buckets.js`

Move from chat.js:
- `BUCKET_ORDER`, `BUCKET_LABELS` — verbatim move (lines 344-351). Become `App.chat.BUCKET_ORDER`, `App.chat.BUCKET_LABELS`.
- `startOfDay(d)` — verbatim move (lines 324-326). Becomes `App.chat.startOfDay`. **PURE**.
- `bucketForSession(s, nowDay)` — verbatim move (lines 328-342). Becomes `App.chat.bucketForSession`. **PURE**.
- `buildSessionItem(session, currentSessionId, callbacks)` — refactored. New signature receives `callbacks = { onJoin: function(id), onDelete: function(id, btn) }`. Replace the current `joinSession(s.id)` call (line 387, 391) with `callbacks.onJoin(s.id)`; replace the current `ws.send(...)` delete call (lines 381-384) with `callbacks.onDelete(s.id, delBtn)` where the orchestrator's onDelete handler does the WS send. **CALLBACK-INJECTED**.
- `renderSessionList(sessionListEl, sessions, currentSessionId, callbacks)` — refactored from `renderSessionList(sessions)` (lines 397-445). The `currentSessionId` and `callbacks` flow through to `buildSessionItem`. **CALLBACK-INJECTED**.

#### `message-bubble.js`

Note on signature: the flight spec's `App.chat.renderMessage(cls, text, attribution, opts)` is interpreted concretely as **two separate functions** to keep "returns one HTMLElement" honest and to give leg 05 a clean handle on the bubble for streaming mutation:

- `App.chat.renderMessage(cls, text, opts) → HTMLElement` — builds the message bubble: `<div class="msg {cls}" data-testid="message">{text}</div>`. `opts.renderMarkdown` defaults `false` and is unused in leg 01 (read by leg 05). Returns the bubble. **PURE**.
- `App.chat.renderAttribution(side, text) → HTMLElement` — builds the attribution label: `<div class="msg-attribution {side}">{text}</div>`. `side` is `'from-you'` or `'from-agent'` (caller-determined). Returns the label. **PURE**.

The orchestrator's local `addMsg(cls, text, attribution, opts)` (lines 127-142 in current chat.js) becomes:

```js
function addMsg(cls, text, attribution, opts) {
  messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));
  if (attribution) {
    var side = cls.indexOf('user') === 0 ? 'from-you' : 'from-agent';
    messagesEl.appendChild(App.chat.renderAttribution(side, attribution));
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
```

This keeps `addMsg` in chat.js (4-5 lines) — append + scroll are orchestrator concerns; bubble construction is a helper concern. The `opts` parameter is forwarded for leg 05's streaming integration; in leg 01 all callers pass it as `undefined` and `renderMessage` defaults `opts.renderMarkdown` to `false`.

**Note for leg 05**: this leg replaces the flight spec's `renderMessage(cls, text, attribution, opts)` signature with the **canonical contract** `renderMessage(cls, text, opts) → bubble` plus separate `renderAttribution(side, text) → label`. Leg 05's wire-up should call them as a pair (not a single `renderMessage` invocation that handles both). The streaming bubble handle is the bubble element (with `firstChild` as a text node), the attribution is appended separately. This contract is documented in `agents.md`.

#### `telemetry-overlay.js`

This file ships the full telemetry overlay surface to match the flight spec's checkpoint ("5 helper sub-modules" with `App.chat.renderTelemetry` as the construction call):

- `App.chat.renderTelemetry() → HTMLElement` — builds the full overlay DOM via `document.createElement` calls (NOT innerHTML). Returns the `.telemetry-overlay` element with the inner `.telemetry-summary`, `.context-bar-wrap`/`.context-bar`, `.t-ctx-pct` value span, `.telemetry-details` div, and the three `.telemetry` `in:`/`out:`/`ctx:` rows. Sets `tabindex="0"`, `role="status"`, `aria-label="Token usage"` on the overlay container. **PURE**. Mirrors lines 78-88 of current chat.js verbatim in DOM shape — exact class names + tabindex/role/aria preserved so the F2/F3 CSS rules and a11y stay valid.
- `App.chat.updateTelemetry(chromeContent, data)` — refactored from `updateTelemetry(data)` (lines 110-121). Takes the chrome content element as a parameter named `chromeContent` so the `.querySelector('.t-in')` etc. lookups have an explicit scope. **PURE**.
- `App.chat.fmtTokens(n)` — verbatim move (lines 104-108). Used by `updateTelemetry`. **PURE**.

**Chat.js chrome construction change**: split the existing single innerHTML string (lines 59-93) into (a) an innerHTML for the welcome canvas + chrome wrapper / header / messages / input-area + a placeholder for the overlay, and (b) a follow-up `chromeEl.insertBefore(App.chat.renderTelemetry(), chromeEl.querySelector('.input-area'))` to inject the overlay between `.messages` and `.input-area` (matching original DOM order). Alternative: keep the chrome innerHTML minus the overlay block, then call `renderTelemetry()` and append at the right position. Either implementation is acceptable; the contract is "overlay sits between `.messages` and `.input-area` in the chrome".

#### `thinking-indicator.js`

- `App.chat.createThinking() → HTMLElement` — refactored from `showThinking()` (lines 480-494). Builds the thinking element (with `data-testid="thinking-indicator"`), starts the dot-animation interval, returns the element. The interval-id is stored on the element as `el._dotTimer` (matches current pattern). **PURE** (creates DOM with side-effect of starting an interval — the interval is owned by the returned element).
- `App.chat.removeThinking(el)` — refactored from `hideThinking()` (lines 496-501). Idempotent: if `el` is null/undefined, no-op. Otherwise clears `el._dotTimer` and removes `el` from its parent. **PURE**.
- `App.chat.THINKING_FRAMES` — verbatim move (line 478). Used by `createThinking`.

The orchestrator wraps these:

```js
var thinkingEl = null;
function showThinking() {
  if (thinkingEl) return;
  thinkingEl = App.chat.createThinking();
  messagesEl.appendChild(thinkingEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
function hideThinking() {
  App.chat.removeThinking(thinkingEl);
  thinkingEl = null;
}
```

### 3. Refactor `chat.js`

In place. The file shrinks from 782 → ~400 LOC by:

- Deleting the function bodies for the moved helpers (`welcomeLink`, `renderWelcomeList`, `startOfDay`, `bucketForSession`, `BUCKET_ORDER`, `BUCKET_LABELS`, `buildSessionItem`, `renderSessionList`, `updateTelemetry`, `fmtTokens`, `showThinking`'s body, `hideThinking`'s body — replaced with thin wrappers).
- Replacing the `addMsg` body with the 4-5 line wrapper described above.
- Replacing `renderWelcomeList()` call sites (lines 180, 526, 201) with `App.chat.renderWelcomeList(welcomeEl, welcomeListEl, availableAgents, setupState, callbacks)` where `callbacks = { onStart: startSessionWith, onLink: function (areaId) { /* no-op; href handles navigation */ } }` — actually `onLink` is unused since `welcomeLink` returns an `<a href>`, so the callback can be omitted from the contract. Keep the callback shape consistent: pass `{ onStart: startSessionWith }`.
- Replacing `renderSessionList(sessions)` call sites (line 595) with `App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, callbacks)` where `callbacks = { onJoin: joinSession, onDelete: function (id, btn) { ws.send(JSON.stringify({ action: 'delete_session', session_id: id })); } }`.
- Keeping these closure-bound functions IN chat.js (not extractable without architectural change): `joinSession`, `connect`, `send`, `refreshSessionList`, `checkSetupState`, `setSessionHealth`, `syncDropdownToCurrent`, `highlightActiveSession`, `showWelcome` / `showChrome`, `fetchAgents`, `updateAgentBadge`, `startSessionWith`, `addMsg` (thin wrapper), `showThinking` / `hideThinking` (thin wrappers), the welcome listbox keydown handler (roving tabindex), the input/sendBtn/agentSelect/headerNewBtn event listeners (including `headerNewBtn`'s click handler at chat.js:747-749).

### 4. Update `index.html` script order

Edit `static/index.html`. Replace the existing `<script>` block at the bottom of `<body>` with the documented order. Verify by reloading the app — open browser console, confirm no `App.chat is undefined` or similar errors.

### 5. Update `agents.md`

Add a subsection (suggested location: after the existing `## Module Map` section, or under `## Key Patterns`) documenting the `App.chat` namespace. Suggested text:

```markdown
### App.chat helpers

The chat area's pure-helper layer lives at `static/js/areas/chat/`. Files attach functions to `App.chat.{name}` from their own IIFE; `chat.js` consumes them via the namespace.

**Pure** (take inputs, return DOM):
- `App.chat.welcomeLink(text, areaId) → <a>`
- `App.chat.startOfDay(d) → number`
- `App.chat.bucketForSession(s, nowDay) → BucketLabel`
- `App.chat.fmtTokens(n) → string`
- `App.chat.renderMessage(cls, text, opts) → <div.msg>` (`opts.renderMarkdown: bool` reserved for the markdown integration; flight spec's `(cls, text, attribution, opts)` is split into two functions with `renderAttribution` below)
- `App.chat.renderAttribution(side, text) → <div.msg-attribution>`
- `App.chat.renderTelemetry() → <div.telemetry-overlay>` (returns the full overlay DOM with all inner spans/divs)
- `App.chat.updateTelemetry(chromeContent, data)` (mutates DOM under the chrome content element)
- `App.chat.createThinking() → <div.msg.thinking>` (returns an element with a self-managed dot-animation interval; the THINKING_FRAMES constant is module-private)
- `App.chat.removeThinking(el)` (idempotent — no-op if `el` is null/already removed)

**Callback-injected** (closure references replaced with explicit callbacks):
- `App.chat.renderWelcomeList(welcomeEl, welcomeListEl, agents, setupState, callbacks)` — `callbacks = { onStart: function(agentName) }` (no `onLink` — `welcomeLink` returns `<a href>` and the browser handles navigation)
- `App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, callbacks)` — `callbacks = { onJoin: function(id), onDelete: function(id, btn) }`
- `App.chat.buildSessionItem(session, currentSessionId, callbacks)` — same callbacks shape

The orchestrator (chat.js) owns closure state — `ws`, `currentSessionId`, `currentAgentName`, `pendingJoinId`, `availableAgents`, `setupState`, the WS lifecycle, and the welcome-listbox roving-tabindex keydown handler — and wires WS events to helpers via the callbacks above.

Load order (set in `index.html`): `app.js` → `icons.js` → `markdown.js` → `areas/chat/welcome.js` → `areas/chat/history-buckets.js` → `areas/chat/message-bubble.js` → `areas/chat/telemetry-overlay.js` → `areas/chat/thinking-indicator.js` → `areas/chat.js` → `areas/studio.js` → `areas/admin.js`.
```

### 6. Run tests

```bash
pytest --timeout=60 tests/                          # unit + non-browser
pytest --timeout=120 -m browser tests/browser/      # browser tests
```

Both must pass with no new failures. If a browser test fails, the most likely culprits are: (a) script load order broken (helpers loaded after chat.js), (b) a closure-bound function inadvertently referenced from a helper, (c) a `data-testid` attribute moved to the wrong DOM element.

### 7. Update flight log

Append a `### chat-component-split` block under `## Leg Progress` summarizing what moved, the LOC delta, the test counts before/after, and the deviation note about telemetry-overlay DOM construction staying inline.

## Edge Cases

- **A helper is loaded but `App.chat` was never created**: The IIFE template defensively creates `window.App.chat = window.App.chat || {}` before attaching, so any helper file is safe to load standalone. No coupling to load order beyond the script-tag concatenation.
- **`removeThinking(el)` called with null**: idempotent — early-return on null/undefined.
- **`renderSessionList` called with empty sessions**: matches current behaviour (lines 398-399) — clears the list, returns without rendering buckets.
- **`renderWelcomeList` called when setup is incomplete**: matches current behaviour (lines 218-242) — shows guidance, drops the listbox role, returns.
- **A test references `App.markdown.parse` before leg 03 lands**: stub provides `App.markdown = {}`; `App.markdown.parse` will be `undefined`. If a leg-01 test asserts on this, fix the test to defer to leg 03 instead of stubbing further. (No such test is expected; the stub guards against accidental ReferenceError.)
- **Welcome listbox keydown handler runs before any items render**: matches current behaviour (lines 293-312) — handler queries `.chat-welcome-item`, returns early if empty.
- **`buildSessionItem` callback `onDelete` invoked while WS is closed**: matches current behaviour — the `ws.send` inside the callback would throw; current code at line 383 has the same risk. Out of scope for leg 01 (refactor preserves behaviour).

## Files Affected

- `the_one/interfaces/web/static/js/markdown.js` — NEW (3-line stub)
- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — NEW
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — NEW
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js` — NEW
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — NEW
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js` — NEW
- `the_one/interfaces/web/static/js/areas/chat.js` — SHRINKS to ~400 LOC; closure state + WS lifecycle + thin wrappers around helpers
- `the_one/interfaces/web/static/index.html` — UPDATED script tag order
- `the_one/agents.md` — UPDATED with `App.chat` helpers subsection
- `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md` — UPDATED with leg progress entry

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (manual smoke deferred — see note above)
- [x] `pytest --timeout=60 tests/` passes (393 / 393)
- [x] `pytest --timeout=120 -m browser tests/browser/` passes (32 / 32)
- [x] Update flight-log.md with leg progress entry under `## Leg Progress` (`### chat-component-split` heading)
- [x] Set this leg's status to `landed` (in this file's header) — DO NOT set to `completed` and DO NOT commit; the flight-level review and commit run after the last autonomous leg per `/agentic-workflow`.
- [x] Signal `[HANDOFF:review-needed]`
