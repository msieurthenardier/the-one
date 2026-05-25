# Leg: chat-ui-attribution

**Status**: completed
**Flight**: [Peer-name Attribution End-to-End (Bug C)](../flight.md)

## Objective

Render peer-attributed user bubbles in the Chat UI: branch `addMsg` + `renderMessage` + `renderAttribution` on `opts.peerName` truthiness to pick (a) the new `'from-peer'` attribution side, (b) the new `msg-from-peer` bubble class that overrides `.msg.user`'s right-alignment via a same-specificity CSS rule declared after `chat.css:129`, and (c) the peer's display name as the attribution text — so the operator sees `discord-username` (left-aligned) on peer-originated messages while operator-typed messages keep their existing `'You'` right-aligned rendering.

## Context

L1-L3 closed the server-side half of Bug C: `Message.peer_name` round-trips through the codec, `messages_to_ui_events` projects it onto user events, the dispatcher binds it from the envelope, and the live broadcast carries it on connector-inbound `user` events. L4 closes the client-side half: the Chat UI must consume `peer_name` from both replay (`renderHistory` reading `ev.peer_name`) and live broadcast (`onmessage` reading `data.peer_name`) and produce a visually distinct rendering.

Per flight Design Decision §1: peer bubbles render **left-aligned** with peer_name attribution (new `'from-peer'` side). Operator-typed user bubbles stay right-aligned with `'You'`. The architectural shape is `addMsg(cls, text, attribution, opts)` where `opts.peerName` truthiness is the single signal that flips both the attribution side AND the bubble alignment.

Per architect cycle-1 review (recorded in flight-log.md): side selection inside `addMsg` is **inferred from `opts.peerName` truthiness**, not a separate `opts.side` knob. This avoids a brittle caller-side contract.

Per architect cycle-1 high-severity finding: the CSS override **must** target `.area-chat .msg.user.msg-from-peer` (same specificity as the existing `.area-chat .msg.user` at `chat.css:129`) AND must be declared **after** it in source order. The L4 AC explicitly pins both the selector AND the source-order requirement.

Visibility composition (already structurally correct): `tag_post_step_visibility` in `connectors/visibility.py:60` `continue`s on `Role.USER`, so peer-inbound user messages keep `visibility=None`. The codec omits the `visibility` key; the Chat UI's `renderMessage` does not add `msg-operator-only` (the gate is `firstToken === 'user' → isUserBubble → skip marker on user bubbles` at `message-bubble.js:43-44`). Peer bubbles render unmarked; operator-typed user bubbles also unmarked. Both correct.

## Inputs

What exists before this leg runs (post-L1+L2+L3 state):

- `Message.peer_name: str | None = None` field; codec round-trip; `messages_to_ui_events` projects `peer_name` onto Role.USER events when set (L1+L2).
- `_inbound.py` binds `working_envelope.peer_name` post-step (L3); broadcast tests pin `user` event carries `peer_name`, non-USER events do not (L3).
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`:
  - `renderMessage(cls, text, opts)` at line 31 — builds `<div class="msg {cls}">`, handles `opts.visibility === 'operator'` (adds `msg-operator-only` class + `[operator-only]` label, suppressed on user-role bubbles per `message-bubble.js:43-44`); stashes `el.dataset.visibility` when truthy; renders markdown for assistant or textContent for others.
  - `renderAttribution(side, text, ts)` at line 90 — builds `<div class="msg-attribution {side}">{text}<span class="msg-attribution-ts">{fmtTs(ts)}</span></div>`. The `side` argument is appended to the class string; the function accepts any string but the existing CSS only styles `from-you` (line 225) and `from-agent` (line 226).
- `the_one/interfaces/web/static/js/areas/chat.js`:
  - `addMsg(cls, text, attribution, opts)` at line 116 — appends rendered message, then conditionally appends attribution; side selection: `cls.indexOf('user') === 0 ? 'from-you' : 'from-agent'` at line 120.
  - `renderHistory(history, agentName)` at line 220 — replay loop; user-event branch at line 238-241 calls `addMsg(cls, '[' + source + '] ' + ev.content, 'You', histOpts)` with `histOpts = { ts: ev.ts || null, visibility: ev.visibility }` at line 237.
  - Live `data.type === 'user'` handler at line 846-854 — calls `addMsg(cls, ..., 'You', { visibility: data.visibility })`.
  - Send-echo at line 616 — `addMsg('user', text, 'You')`; operator-typed by construction; will stay unchanged.
- `the_one/interfaces/web/static/css/chat.css`:
  - `.area-chat .msg.user { align-self: flex-end; background: var(--accent); color: var(--fg-on-accent); box-shadow: 0 0 8px var(--accent-glow); }` at line 129.
  - `.area-chat .msg.user.api { background: var(--accent-api); box-shadow: none; }` at line 130.
  - `.area-chat .msg-attribution.from-you { align-self: flex-end; }` at line 225.
  - `.area-chat .msg-attribution.from-agent { align-self: flex-start; }` at line 226.
- `tests/browser/test_flow_chat_visibility_distinction.py` — established browser-test pattern: spin app subprocess against a temp data_dir, seed provider+agent via `seeders.py`, seed `chat_sessions` row directly via `sqlite3.connect` with codec-encoded messages, navigate to `#chat/sessions/{id}` deep link, assert DOM-shape via Playwright locators + `evaluate` for class/dataset/computedStyle checks.

## Outputs

After this leg completes:

- `renderMessage(cls, text, opts)` adds `msg-from-peer` class to the bubble when `opts.peerName` is truthy. No other behavior change.
- `addMsg(cls, text, attribution, opts)` side selection becomes: `opts.peerName ? 'from-peer' : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent')`. Defensive `opts = opts || {}` at the top of `addMsg`.
- `renderAttribution` keeps its signature — it already accepts any side string. No JS change needed beyond the CSS rule for `from-peer`.
- `renderHistory` user-event branch reads `ev.peer_name`, sets `attribution = ev.peer_name || 'You'` and `histOpts.peerName = ev.peer_name`. Other event branches unchanged.
- Live `data.type === 'user'` handler reads `data.peer_name`, sets `attribution = data.peer_name || 'You'` and adds `peerName: data.peer_name` to the opts object.
- Send-echo path (`chat.js:616`) unchanged (operator-typed; no peer_name by construction).
- `chat.css` gains TWO new rules declared AFTER the existing `.area-chat .msg.user` rule at line 129 AND after the existing `.area-chat .msg-attribution.from-agent` rule at line 226:
  - `.area-chat .msg.user.msg-from-peer` — overrides `align-self` to `flex-start`, neutralizes the accent background (uses surface/elevated colors instead so peer bubbles read as left-side platform-source). Source-order placement after line 129 is load-bearing — same specificity as the base `.msg.user` rule, last-rule-wins via CSS cascade source order.
  - `.area-chat .msg-attribution.from-peer` — `align-self: flex-start` for the attribution label. Mirrors `.from-agent`.
- `tests/browser/test_flow_chat_peer_attribution.py` — new browser test mirrors `test_flow_chat_visibility_distinction.py`'s seed-then-render pattern; pins DOM-shape and computed-style assertions for peer-attributed rendering across replay (operator-typed + peer-attributed user bubbles coexisting in one session).

## Acceptance Criteria

- [x] `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage` adds `msg-from-peer` to the bubble's class string when `opts.peerName` is truthy. The class is added in the same composition block as the operator-only class, BEFORE `el.className = fullCls` is assigned. Class-set composes correctly (`msg user msg-from-peer` for peer-inbound; peer + operator-only co-occurrence is structurally prevented because peer-inbound users have visibility=None per L3 server-side gating, and the `isUserBubble` gate at `message-bubble.js:44` suppresses the operator-only class+label on user bubbles regardless).
- [x] `the_one/interfaces/web/static/js/areas/chat.js:addMsg` infers `side` via `opts.peerName ? 'from-peer' : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent')`. Defensive `opts = opts || {}` is added at the top of `addMsg` (current callers sometimes omit `opts` entirely — e.g. `addMsg('system', detail)`).
- [x] `chat.js:renderHistory` user-event branch (line 238-241) reads `ev.peer_name`:
  - `attribution = ev.peer_name || 'You'`
  - `histOpts.peerName = ev.peer_name` (added to the existing `histOpts` object at line 237)
- [x] `chat.js` live user-event handler (line 846-854) reads `data.peer_name`:
  - `attribution = data.peer_name || 'You'`
  - opts: `{ visibility: data.visibility, peerName: data.peer_name }`
- [x] `chat.js` send-echo at line 616 is UNCHANGED. Operator-typed by construction — no `peerName` source, attribution stays `'You'`.
- [x] `the_one/interfaces/web/static/css/chat.css` gains a new rule `.area-chat .msg.user.msg-from-peer { align-self: flex-start; background: var(--surface-elevated); color: var(--fg); box-shadow: none; }` declared AFTER the existing `.area-chat .msg.user` rule at line 129. **The source-order requirement is load-bearing** — same specificity as `.msg.user`, last-rule-wins via CSS cascade. The exact background/color tokens may be tuned by the implementer if `--surface-elevated`/`--fg` don't read well visually; the AC pins (a) same-specificity selector, (b) source-order after line 129, (c) `align-self: flex-start`.
- [x] `chat.css` gains a new rule `.area-chat .msg-attribution.from-peer { align-self: flex-start; }` declared after `.area-chat .msg-attribution.from-agent` at line 226. Mirrors the `from-agent` pattern.
- [x] `tests/browser/test_flow_chat_peer_attribution.py` (new) — mirrors `test_flow_chat_visibility_distinction.py`'s pattern. Seeds a session with three USER messages and one assistant message:
  - USER #1: operator-typed (no peer_name, visibility=OPERATOR_VISIBILITY) — should render `.msg.user` right-aligned, attribution `.from-you` text `'You'`.
  - USER #2: peer-attributed (`peer_name="alice"`, visibility=None) — should render `.msg.user.msg-from-peer` left-aligned, attribution `.from-peer` text `'alice'`.
  - ASSISTANT: visibility=OPERATOR_VISIBILITY — should render with `.msg-operator-only` class (existing behavior unchanged).
  - USER #3: peer-attributed (`peer_name="bob"`, visibility=None) — verifies two distinct peer names render correctly in one session.

  Assertions:
  - [x] `.msg.user.msg-from-peer` count == 2 (USER #2 and #3).
  - [x] `.msg.user:not(.msg-from-peer)` count == 1 (USER #1).
  - [x] First `.msg-from-peer`'s immediately-following attribution element has class `msg-attribution from-peer` and text starting with `'alice'` (the `· {ts}` suffix may follow when the codec emits no `ts`, which it doesn't on replay — `histOpts.ts = ev.ts || null` and absence-of-ts means the suffix is suppressed; this means the text is just `'alice'`).
  - [x] Second `.msg-from-peer`'s attribution is `'bob'`.
  - [x] The operator-typed user bubble's attribution is `'You'` and side class is `from-you`.
  - [x] Computed style on `.msg.user.msg-from-peer`: `getComputedStyle(el).alignSelf === 'flex-start'` (verifies the source-order CSS override actually wins).
  - [x] Computed style on `.msg.user:not(.msg-from-peer)`: `getComputedStyle(el).alignSelf === 'flex-end'` (verifies the operator-typed user bubble still right-aligns).
  - [x] Visibility composition: assistant bubble has `.msg-operator-only` class; peer bubbles do NOT have it; operator-typed user bubble does NOT have it (existing F5 L8 HAT decision preserved).
- [x] All existing browser tests pass without modification: `tests/browser/test_flow_chat.py`, `tests/browser/test_flow_chat_visibility_distinction.py`, `tests/browser/test_flow_chat_operator_input_visibility.py`, `tests/browser/test_flow_new_chat.py`, `tests/browser/test_flow_markdown_chat.py`, `tests/browser/test_flow_chat_session_list_source_badge.py`. Specifically: `test_chat_renders_operator_visibility_distinction` still passes because its seeded messages have no peer_name, so the new code branches default to the pre-L4 behavior.

## Verification Steps

Run from the project root inside the dev container.

1. **Targeted browser test passes**:
   ```
   docker exec the-one pytest -x --timeout 60 tests/browser/test_flow_chat_peer_attribution.py
   ```
   Expected: all assertions pass.

2. **Adjacent browser tests pass** (no regressions on the visibility distinction test, which exercises the operator-only marker that L4 must compose with cleanly):
   ```
   docker exec the-one pytest -x --timeout 60 tests/browser/test_flow_chat_visibility_distinction.py tests/browser/test_flow_chat_operator_input_visibility.py tests/browser/test_flow_chat.py
   ```
   Expected: all pass.

3. **Full chat-flow browser suite**:
   ```
   docker exec the-one pytest -x --timeout 60 -k "test_flow_chat" tests/browser/
   ```
   Expected: all pass.

4. **Server-side suite unaffected** (L4 is pure frontend + CSS + browser test — no Python server changes):
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py
   ```
   Expected: all pass (covers L1-L3 regression net).

5. **Smoke-check the CSS specificity** via a manual `evaluate_script` snippet during the browser test development:
   ```
   page.evaluate("() => getComputedStyle(document.querySelector('.msg.user.msg-from-peer')).alignSelf")
   ```
   Expected: `'flex-start'`.

## Implementation Guidance

1. **Edit `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage`** — add the `msg-from-peer` class branch. Insert immediately after the operator-only class composition block (around current lines 43-47), before `el.className = fullCls;`:

   ```js
   var isOperatorOnly = opts.visibility === 'operator' && !isUserBubble;
   if (isOperatorOnly) {
     fullCls += ' msg-operator-only';
   }
   // M11 F06 L04: peer-attributed user bubble gets msg-from-peer for the
   // CSS left-align override (.area-chat .msg.user.msg-from-peer in chat.css,
   // declared after .area-chat .msg.user — same specificity, last-rule-wins).
   // Composes cleanly with visibility: peer-inbound users have visibility=None
   // by construction (connectors/visibility.py:60 skips Role.USER), so
   // isOperatorOnly above is false for peer bubbles.
   if (opts.peerName) {
     fullCls += ' msg-from-peer';
   }
   el.className = fullCls;
   ```

2. **Edit `the_one/interfaces/web/static/js/areas/chat.js:addMsg`** — add defensive `opts = opts || {}` and change side selection. Current code at lines 116-127:

   ```js
   function addMsg(cls, text, attribution, opts) {
     App.perf.mark('addMsg:start');
     opts = opts || {};
     messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));
     if (attribution) {
       // M11 F06 L04: side inferred from opts.peerName truthiness.
       // peer-attributed user bubbles align left ('from-peer'); operator-typed
       // user bubbles stay right ('from-you'); non-user bubbles ('assistant',
       // 'tool', 'system') align left ('from-agent') as before.
       var side = opts.peerName
         ? 'from-peer'
         : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent');
       var ts = Object.prototype.hasOwnProperty.call(opts, 'ts') ? opts.ts : new Date().toISOString();
       messagesEl.appendChild(App.chat.renderAttribution(side, attribution, ts));
     }
     scrollToBottomIfPinned();
     App.perf.mark('addMsg:end');
     App.perf.measure('addMsg', 'addMsg:start', 'addMsg:end');
   }
   ```

3. **Edit `chat.js:renderHistory` user-event branch** (current line 237-241):

   ```js
   var histOpts = { ts: ev.ts || null, visibility: ev.visibility, peerName: ev.peer_name };
   if (ev.type === 'user') {
     var cls = ev.source === 'api' ? 'user api' : 'user';
     var attribution = ev.peer_name || 'You';
     addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, attribution, histOpts);
   }
   ```

4. **Edit `chat.js` live `data.type === 'user'` handler** (current line 846-854):

   ```js
   if (data.type === 'user') {
     var cls = data.source === 'api' ? 'user api' : 'user';
     // M11 F06 L04: forward peer_name from the live broadcast onto the
     // attribution + bubble side. Connector-inbound user events carry
     // data.peer_name (per F6 L3 dispatcher binding + F6 L2 codec
     // projection). Operator-typed user events have no peer_name.
     var liveAttribution = data.peer_name || 'You';
     addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content, liveAttribution, { visibility: data.visibility, peerName: data.peer_name });
   }
   ```

5. **DO NOT edit `chat.js:616`** (send-echo path) — operator-typed turns have no peer_name source by construction.

6. **Edit `the_one/interfaces/web/static/css/chat.css`** — insert new rule for the bubble side override IMMEDIATELY AFTER line 130 (`.area-chat .msg.user.api ...`), so the cascade walks `.msg.user` → `.msg.user.api` → `.msg.user.msg-from-peer`. Source-order placement is load-bearing:

   ```css
   .area-chat .msg.user { align-self: flex-end; background: var(--accent); color: var(--fg-on-accent); box-shadow: 0 0 8px var(--accent-glow); }
   .area-chat .msg.user.api { background: var(--accent-api); box-shadow: none; }
   /* M11 F06 L04: peer-attributed user bubble. Same specificity as
      .msg.user above; declared AFTER it so last-rule-wins flips alignment
      and neutralizes the accent background so peer messages read as
      left-side platform-source (not me/operator). */
   .area-chat .msg.user.msg-from-peer { align-self: flex-start; background: var(--surface-elevated); color: var(--fg); box-shadow: none; }
   ```

   And insert the attribution-side rule immediately after line 226 (`.area-chat .msg-attribution.from-agent ...`):

   ```css
   .area-chat .msg-attribution.from-you { align-self: flex-end; }
   .area-chat .msg-attribution.from-agent { align-self: flex-start; }
   /* M11 F06 L04: peer-attributed attribution label. Mirrors .from-agent
      (left-aligned) but kept as a distinct class so a future themed peer
      color (avatar dot, role color) can target it without touching agent
      attribution rendering. */
   .area-chat .msg-attribution.from-peer { align-self: flex-start; }
   ```

   The tokens `--surface-elevated` and `--fg` are project-defined design-language variables (the operator's L5/F5 work codified these). If those names don't exist in `chat.css`'s context, the implementer should grep `the_one/interfaces/web/static/css/design-language*.css` (or equivalent) for the canonical token names and substitute accordingly.

7. **Create `tests/browser/test_flow_chat_peer_attribution.py`** — copy the structure of `tests/browser/test_flow_chat_visibility_distinction.py` (281 lines) verbatim for the fixtures (`app_with_data_dir`, `_seed_session_with_messages`, port helpers, etc.) — or import them from there if the existing test exposes them. If they're not exposed, duplicating the fixtures is acceptable for this single test (the test is browser-tier and isolated; a future refactor can de-duplicate). Build the seeded messages list:

   ```python
   msgs = [
       Message.system("you are a test agent"),
       Message.user("operator typing", visibility=OPERATOR_VISIBILITY),  # USER #1: operator-typed
       Message.user("hey @bot ping?", peer_name="alice"),                # USER #2: peer-attributed (visibility=None)
       Message.assistant("pong", visibility=OPERATOR_VISIBILITY),        # ASSISTANT
       Message.user("another one", peer_name="bob"),                     # USER #3: peer-attributed
   ]
   ```

   Then drive the assertions per the AC list. Use `page.locator()` + `.evaluate()` for class checks and computed-style probes. Pattern follows the visibility-distinction test's structure.

8. **Update leg status to `in-flight`** at the start of implementation; update to `landed` when implementation + tests pass.

9. **Update flight-log.md** with a Leg Progress entry. Check off `chat-ui-attribution` in `flight.md`'s Legs list. Do NOT commit (deferred to flight-end; this is the LAST autonomous leg before Phase 2d full-flight review).

## Edge Cases

- **Peer bubble with `peer_name=""` (empty string)**: per L1+L2 edge-case analysis, this cannot happen in practice (Discord plugin's `display_name or str(user.id)` at `_discord.py:218` guarantees non-empty). If it did appear, `data.peer_name || 'You'` falls back to `'You'` and `opts.peerName` is falsy → side defaults to `'from-you'` and `msg-from-peer` class is NOT added. Net result: empty-string peer_name renders identically to operator-typed. Acceptable graceful degradation.
- **`renderHistory` with mixed peer-attributed + operator-typed user messages in one session**: each event independently carries (or doesn't carry) `ev.peer_name`. The per-event `addMsg` call branches independently — no cross-event state. AC's seeded session exercises this exact mixed-history case.
- **Live broadcast `assistant_chunk` events**: the streaming-bubble code at chat.js:855-881 does NOT use `addMsg` for chunks; it appends directly to `messagesEl`. peer_name is not relevant for assistant chunks (different role; no peer_name on assistant messages by construction). No change needed.
- **Replay path with `ev.peer_name === null` vs `undefined`**: the codec emits `peer_name` only when non-None (L1 + L2 contract). On the frontend, `ev.peer_name` is `undefined` when absent. `ev.peer_name || 'You'` falls back correctly. `opts.peerName = ev.peer_name` sets `peerName: undefined` when absent, which is falsy → side defaults correctly. No special handling needed.
- **Tool/system bubbles**: `addMsg` is called with `cls='tool'` or `cls='system'`; `opts.peerName` is never set on those calls (tool/system have no `peer_name` source). The side defaults to `'from-agent'` (cls.indexOf('user') !== 0). Unchanged behavior.
- **`api`-source user (HTTP `/api/chat/send` path)**: per the `cls === 'user api'` branch in `renderHistory:239` and the live handler, this is an operator-typed turn (HTTP path doesn't carry peer_name). `peer_name` is absent → defaults to `'You'` and `from-you` side. Unchanged behavior.
- **CSS specificity edge case: `.msg.user.api.msg-from-peer` (operator-typed via API + peer_name somehow)**: structurally impossible — the API path has no peer_name source. If it did somehow happen, `.msg.user.msg-from-peer` (specificity 0,0,3,0) and `.msg.user.api` (specificity 0,0,3,0) are equal-specificity; the rule declared LAST in source order wins. Since `msg-from-peer` is declared after `msg.user.api`, the peer rule wins on `align-self` and `background`. Acceptable — this case can't occur in practice but the cascade behavior is well-defined.
- **Markdown rendering on peer bubbles**: `renderMessage` calls `App.markdown.render(text)` only when `firstToken === 'assistant'` (line 11-13 of `shouldRenderAsMarkdown`). Peer user bubbles do NOT get markdown rendering (they render via `el.textContent = text`). Acceptable — peer messages on Discord are typically chat-snippet shape; markdown would expand unintended formatting. Matches operator-typed user bubbles which also don't get markdown.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js` — `renderMessage` adds `msg-from-peer` class
- `the_one/interfaces/web/static/js/areas/chat.js` — `addMsg` side inference; `renderHistory` user branch; live user handler
- `the_one/interfaces/web/static/css/chat.css` — two new rules (`.msg.user.msg-from-peer` + `.msg-attribution.from-peer`), source-order-after-existing
- `tests/browser/test_flow_chat_peer_attribution.py` — new browser test
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/legs/04-chat-ui-attribution.md` — status transitions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (per agentic-workflow protocol; do NOT commit):**

- [x] All acceptance criteria verified
- [x] Targeted browser test passes
- [x] Adjacent browser tests pass (no regressions on visibility-distinction)
- [x] Server-side regression net passes (`tests/test_db_codec.py`, `tests/test_connectors_inbound.py`, `tests/test_connectors_inbound_broadcast.py`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off `chat-ui-attribution` in flight.md
- [x] Do NOT commit — full-flight Reviewer + commit happens in Phase 2d after this leg
- [x] Do NOT update flight.md status to `landed` (L5 HAT runs next)
- [x] Constraint check: `the_one/agent/core.py` and `the_one/agent/factory.py` are NOT in the diff

---

## Citation Audit

Citations verified against current code (post-L1+L2+L3 state) at leg design time:

- `the_one/interfaces/web/static/js/areas/chat.js:116` (`addMsg`) — verified at design time.
- `the_one/interfaces/web/static/js/areas/chat.js:220` (`renderHistory`) — verified.
- `the_one/interfaces/web/static/js/areas/chat.js:237-241` (user-event histOpts + addMsg call) — verified.
- `the_one/interfaces/web/static/js/areas/chat.js:616` (send-echo) — verified.
- `the_one/interfaces/web/static/js/areas/chat.js:846-854` (live user handler) — verified.
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:31` (`renderMessage`) — verified.
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:43-44` (isUserBubble gate) — verified.
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:90` (`renderAttribution`) — verified.
- `the_one/interfaces/web/static/css/chat.css:129` (`.area-chat .msg.user`) — verified via grep.
- `the_one/interfaces/web/static/css/chat.css:130` (`.area-chat .msg.user.api`) — verified.
- `the_one/interfaces/web/static/css/chat.css:225` (`.from-you`) — verified.
- `the_one/interfaces/web/static/css/chat.css:226` (`.from-agent`) — verified.
- `tests/browser/test_flow_chat_visibility_distinction.py:172` (test pattern template) — verified at flight-design time.
- `the_one/connectors/visibility.py:60` (`continue` on Role.USER) — verified at flight-design time.
- `the_one/connectors/_discord.py:218` (peer_name fallback) — verified.

15 citations verified. The CSS line numbers in particular are stable (L1-L3 did not touch frontend assets); the JS line numbers may shift by ≤2 lines if L1-L3 added any frontend code (they did not — server-side only).
