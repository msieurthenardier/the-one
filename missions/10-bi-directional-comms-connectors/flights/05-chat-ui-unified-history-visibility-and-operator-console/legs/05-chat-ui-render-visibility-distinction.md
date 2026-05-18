# Leg: chat-ui-render-visibility-distinction

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Make `App.chat.renderMessage` accept a `visibility` parameter sourced
from the event dict's `visibility` key (already emitted by the codec
at `the_one/db/codec.py:114-187`). When `visibility === "operator"`,
the rendered bubble carries a `msg-operator-only` class and an inline
`[operator-only]` label. The CSS rule lives in `chat.css` using real
M04/M06 tokens. Non-connector and platform-visible messages render
byte-identically to today.

Pure render-side leg. No server-side broadcast changes; no agent-loop
changes. Live-broadcast visibility tagging (so the operator sees the
marker on their own typing in real time, before refresh) is a deliberate
follow-on described in Edge Cases.

## Context

- **Flight slot**: F5 L5 — the visual distinction. After this leg, when
  the operator opens a connector-attached session in the Chat UI, the
  bubbles tagged operator-only via the persisted `Message.visibility`
  field render with a subtle left-border marker + tiny inline label,
  visually subordinate to peer-visible bubbles. The codec at
  `the_one/db/codec.py:114-187` already projects `visibility` into
  every event derived from a tagged Message; this leg is the receiver.
- **Flight design decision — "Visibility-distinction visual treatment
  in the Chat UI"** (flight.md L46-50): inline marker at the message-
  bubble level; subtle left-border + small `[operator-only]` label.
  Single timeline (no split panels).
- **Flight In-Flight § Leg 5** (flight.md L160-166): scope is
  `renderMessage` + CSS + label + consumers + browser test.
- **Known limitation — live-broadcast visibility gap**: the WS
  broadcast path in `_process_and_broadcast` builds events INLINE at
  lines 898-933 / 966-974 without consulting `Message.visibility`
  (because the F5 L4 storage-edge shim runs AFTER `agent.step`
  completes, but `_send_to_session` calls fire WITHIN the step
  iteration). The operator's just-typed turn on a connector-attached
  session therefore renders without the operator-only marker UNTIL
  the next page refresh / session rejoin, at which point the codec's
  replay carries the `visibility` tag and the render shows the
  marker. Acceptable for v1 because: (1) the storage-edge shim
  ensures persistence is correct; (2) refresh restores correct
  rendering; (3) single-user local-tool means the only consumer is
  the operator themselves. Live-broadcast tagging is a follow-on
  leg's territory.
- **Mission constraint**: agent loop in `the_one/agent/core.py` is
  not modified. This leg touches the chat-area CSS and JS — no
  server-side Python changes.
- **F5 L1/L2/L3/L4 carry-forward state**: source-badge on session
  list (L1); shared lock + subscribers registry (L2);
  `tag_post_step_visibility` helper (L3); WS storage-edge shim +
  `Session.platform` field (L4). All landed and uncommitted on
  this branch.
- **No schema change.** Render-side only.
- **Test-pixel snapshots are local-only** (per the user-global rule):
  the browser test uses DOM-shape assertions (Playwright
  `locator`, `evaluate`, `class`), NOT visual snapshot baselines.

## Inputs

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:22`
  — `renderMessage(cls, text, opts)` builds `<div class="msg {cls}">`
  and renders the text via markdown (for `assistant`) or
  `textContent` (everything else). Signature already takes `opts`
  (`renderMarkdown` flag); the leg extends `opts.visibility`.
- `the_one/interfaces/web/static/js/areas/chat.js:116` —
  `addMsg(cls, text, attribution, opts)` forwards `opts` to
  `App.chat.renderMessage`. Today's call sites: history-replay
  loop (lines 220-260) passes `histOpts = { ts: ev.ts || null }`;
  live event handlers pass no `opts`. The leg extends call sites
  that have an event dict in scope to forward `visibility: ev.visibility`.
- `the_one/interfaces/web/static/js/areas/chat.js:461` — tool-
  bubble construction: `App.chat.renderMessage(isError ? 'tool error'
  : 'tool', text)` — no `opts` arg today. The leg extends to pass
  the event's `visibility`.
- `the_one/interfaces/web/static/js/areas/chat.js:839` — streaming-
  bubble shell construction:
  `App.chat.renderMessage('assistant', '', { renderMarkdown: false })`
  — the placeholder element built up by `assistant_chunk` events.
  Decision (resolved in this leg's design): stash `visibility` from
  the first `assistant_chunk` event on a JS closure variable
  (`currentStreamingVisibility`) and apply it as a class on the
  placeholder at construction. If the LIVE `assistant_chunk` event
  doesn't carry `visibility` today (it doesn't — the known
  limitation above), the streaming bubble renders without the
  marker; refresh fixes it. The streaming-bubble class is set
  inline at placeholder construction by reading
  `currentStreamingVisibility`, defaulting to `null`. NO change to
  `finalizeStreamingBubble`'s signature.
- `the_one/interfaces/web/static/css/chat.css` — chat-area CSS
  inside `@layer areas`. Existing rules at lines 14-46 cover the
  session-list (including F5 L1's `.session-item-source`); lines
  47+ cover message-bubble styles. The new `.msg-operator-only`
  rules belong in the message-bubble section.
- `the_one/interfaces/web/static/css/tokens.css` — design tokens.
  **Verified at design time** (the prior token-name draft was wrong):
  `--accent-muted` and `--space-2`/`--space-1` DO NOT EXIST. Real
  tokens to use: `--border-strong` (`#666666`),
  `--accent-translucent` (`rgba(167, 139, 250, 0.08)`),
  `--fg-tertiary`, `--font-family-mono`, `--font-size-tiny`.
  Spacing values are hardcoded px throughout `chat.css` (e.g.
  `padding: 12px 16px 0 16px`); the leg follows that convention.
- `the_one/db/codec.py:114-187` — `messages_to_ui_events`. Already
  emits `visibility` on every event derived from a tagged message
  (F3 L2). The leg's frontend changes consume what the codec
  already produces.
- `tests/browser/test_flow_keyboard.py` — Playwright fixture
  precedent for the new browser test.

## Outputs

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js` —
  modified:
  - `renderMessage(cls, text, opts)` reads `opts.visibility`. When
    `=== "operator"`:
    1. The `<div>` gains the `msg-operator-only` class.
    2. A `<span class="msg-operator-only-label">[operator-only]</span>`
       is appended INSIDE the bubble as the FIRST child (prepended
       before markdown/text body). Uses `textContent` (XSS-safe).
  - The non-markdown branch (today: `el.textContent = text`)
    becomes `el.appendChild(document.createTextNode(text))` —
    XSS-equivalent (DOM API, not innerHTML) but preserves the
    label when present. The conditional swap only happens when
    the label was prepended; otherwise keep the existing
    `textContent` path for byte-identical behavior on non-
    visibility-tagged bubbles.
  - Optional: stash `el.dataset.visibility = opts.visibility`
    when present — makes the browser test's DOM-shape
    assertions trivial and gives future maintenance a clean
    handle.
- `the_one/interfaces/web/static/css/chat.css` — new rules inside
  `@layer areas`, placed alongside the message-bubble styles:
  ```css
  .area-chat .msg-operator-only {
    border-left: 3px solid var(--border-strong);
    padding-left: 8px;
  }
  .area-chat .msg-operator-only-label {
    display: inline-block;
    margin-right: 4px;
    font-family: var(--font-family-mono);
    font-size: var(--font-size-tiny);
    color: var(--fg-tertiary);
  }
  ```
  Tokens verified against `tokens.css`. Spacing uses hardcoded px,
  matching the chat.css convention.
- `the_one/interfaces/web/static/js/areas/chat.js` — modified at
  call sites:
  - **History-replay loop** (line 233): extend `histOpts` to carry
    visibility: `var histOpts = { ts: ev.ts || null, visibility: ev.visibility };`.
    Single change covers all `addMsg(...)` calls inside the loop.
  - **Tool-bubble builder at line 461**: inspect the function
    containing this call; thread `visibility` from the event being
    rendered into the `opts` arg.
  - **Streaming-bubble at line 839**: add a closure variable
    `currentStreamingVisibility` (defaults `null`); set it from
    the first `assistant_chunk` event's `data.visibility` (which
    is `undefined` today — see the live-broadcast known
    limitation); apply it when constructing the placeholder.
  - **Live-event handlers** that render bubbles directly from a
    `data` dict (e.g. the `assistant` event handler at the
    non-streaming path ~line 857; the `user` event echo at
    ~line 829): extend each to pass
    `{ visibility: data.visibility }` as `opts`. Today
    `data.visibility` is `undefined` on live events (known
    limitation), so this is a no-op at runtime — but the wiring
    is in place for when live-broadcast tagging lands.
- New browser test
  `tests/browser/test_flow_chat_visibility_distinction.py` — DOM-
  shape assertions:
  - Seed a session via `chat_repo.create(...)` with an encoded
    `messages` blob carrying mixed visibility tags (USER + ASSISTANT
    with `visibility="operator"`; a TOOL with `visibility=None`).
    Build the messages via `Message(...).model_dump()` + the codec's
    `encode_messages` — DON'T hand-craft the JSON.
  - Boot the app via the `app_with_agent` (or equivalent) fixture
    that already exists in `tests/browser/`.
  - Navigate to the seeded session; wait for messages to render.
  - Assertions:
    - `page.locator('.msg-operator-only').count()` ≥ 2 (USER +
      ASSISTANT operator-only bubbles).
    - `page.locator('.msg-operator-only-label').count()` ≥ 2
      with `textContent === '[operator-only]'`.
    - The TOOL bubble does NOT have the `msg-operator-only`
      class (peer-visible).
  - No snapshot baseline.

## Acceptance Criteria

- [ ] `App.chat.renderMessage(cls, text, opts)` reads
      `opts.visibility`. When `=== "operator"`:
      - The returned `<div>` has the `msg-operator-only` class
        appended.
      - A `<span class="msg-operator-only-label">[operator-only]</span>`
        is the first child of the bubble.
- [ ] When `opts.visibility` is `null`, `undefined`, or any other
      value, rendering is byte-identical to today — no extra
      class, no label, no `dataset` mutation, no DOM change.
- [ ] The non-markdown branch's `el.textContent = text` is
      adjusted to `el.appendChild(document.createTextNode(text))`
      ONLY when a label was prepended (the
      `opts.visibility === "operator"` branch); otherwise the
      existing `textContent` path is preserved byte-identically.
- [ ] `.msg-operator-only` and `.msg-operator-only-label` CSS
      rules live inside `@layer areas { ... }` in
      `the_one/interfaces/web/static/css/chat.css`, alongside the
      message-bubble styles. Tokens used: `--border-strong`,
      `--fg-tertiary`, `--font-family-mono`, `--font-size-tiny`.
      Spacing: hardcoded px (`3px` border, `8px`/`4px` padding/
      margin) matching the chat.css convention.
- [ ] Every history-replay call site in `chat.js` that has an
      event dict in scope forwards `visibility: ev.visibility`
      via `opts` (history-replay loop at line 233 extension;
      live-event handlers ~line 829, ~line 857 extension; tool-
      bubble at line 461 extension; streaming-bubble at line 839
      via the `currentStreamingVisibility` closure).
- [ ] `tests/browser/test_flow_chat_visibility_distinction.py`
      exists with DOM-shape assertions on a seeded mixed-
      visibility session. No snapshot baseline.
- [ ] `make rebuild && make test-browser` clean (rebuild
      mandatory before browser test — JS/CSS changes must ship
      into the container image).
- [ ] `make test-unit` clean — no regression on F1-F4 or earlier
      F5 leg tests. (No new unit tests in this leg; the render-
      side change is verified end-to-end via the browser test.)
- [ ] `make lint` clean.
- [ ] The agent loop in `the_one/agent/core.py` is untouched.
- [ ] No server-side Python changes. `_broadcast_one`,
      `_process_and_broadcast`, the codec, the helpers in
      `the_one/connectors/`, the registry modules in
      `the_one/sessions/` — all unchanged.

## Verification Steps

- **Codec regression net** (pin-down that codec is unchanged and
  still emits visibility correctly):
  - `docker exec the-one pytest tests/test_db_codec.py -x --timeout 30 -v`
    (the file containing codec tests — verify the exact name at
    impl start with `find tests -name "test_*codec*"`).
- **F5 L4 regression**:
  `docker exec the-one pytest tests/test_ws_storage_edge_shim_visibility.py tests/test_connectors_e2e_ws_into_connector.py -x --timeout 60 -v`
- **F1-F4 regression**:
  `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_visibility_helper.py -x --timeout 60 -v`
- **Full unit-suite**: `make test-unit` clean.
- **Rebuild + browser**: `make rebuild && make test-browser` —
  the new browser test passes; no other browser-test regressions.
- **Lint**: `make lint` clean.

## Implementation Guidance

The leg has three parts: JS render extension (the leaf — most
independently testable), CSS rule, and the call-site wiring.
Recommended order: JS render first; CSS second; call-site wiring
third; browser test last.

1. **JS render extension**
   (`the_one/interfaces/web/static/js/areas/chat/message-bubble.js`):
   - Modify `renderMessage` at line 22:
     ```javascript
     function renderMessage(cls, text, opts) {
       opts = opts || {};
       var el = document.createElement('div');
       var fullCls = 'msg ' + cls;
       var isOperatorOnly = opts.visibility === 'operator';
       if (isOperatorOnly) {
         fullCls += ' msg-operator-only';
       }
       el.className = fullCls;
       el.setAttribute('data-testid', 'message');
       // Stash for DOM-shape assertions and future maintenance.
       if (opts.visibility) {
         el.dataset.visibility = opts.visibility;
       }
       if (isOperatorOnly) {
         var label = document.createElement('span');
         label.className = 'msg-operator-only-label';
         label.textContent = '[operator-only]';
         el.appendChild(label);
       }
       if (shouldRenderAsMarkdown(cls, opts)) {
         el.appendChild(App.markdown.render(text));
       } else if (isOperatorOnly) {
         // Label was prepended — textContent assignment would wipe
         // it. Use appendChild(createTextNode(...)) which is
         // XSS-equivalent (DOM API, not innerHTML).
         el.appendChild(document.createTextNode(text));
       } else {
         el.textContent = text;
       }
       return el;
     }
     ```
   - Verify the byte-identical claim with the existing test
     (`tests/browser/test_flow_markdown_chat.py:144+`) — it
     should still pass without edits.

2. **CSS rule** (`the_one/interfaces/web/static/css/chat.css`):
   - Locate the message-bubble section (search for `.msg.assistant`
     or `.msg.user` in chat.css to find the right neighborhood).
   - Add the two rules inside `@layer areas`, in the message-bubble
     section:
     ```css
     .area-chat .msg-operator-only {
       border-left: 3px solid var(--border-strong);
       padding-left: 8px;
     }
     .area-chat .msg-operator-only-label {
       display: inline-block;
       margin-right: 4px;
       font-family: var(--font-family-mono);
       font-size: var(--font-size-tiny);
       color: var(--fg-tertiary);
     }
     ```

3. **Call-site wiring** (`the_one/interfaces/web/static/js/areas/chat.js`):
   - **Line 233 — history-replay loop**: change to:
     ```javascript
     var histOpts = { ts: ev.ts || null, visibility: ev.visibility };
     ```
   - **Line 461 — tool-bubble builder**: inspect the function (a
     `buildToolMsg(...)` or similar; read 5-10 lines of context).
     The function likely receives the event dict; thread
     `visibility` through to the renderMessage call as an `opts`
     arg.
   - **Live-event handlers** (search for `addMsg(...)` and
     `App.chat.renderMessage(...)` between lines 500-900): for
     each call that has a `data` event dict in scope, add an
     `opts` arg or extend the existing one with
     `visibility: data.visibility`. Today `data.visibility` is
     `undefined` for live events (known limitation), so this is
     a no-op at runtime but wires the channel for the future
     live-broadcast tagging leg.
   - **Streaming-bubble at line 839** (the `assistant_chunk`
     stream path): add a closure variable
     `currentStreamingVisibility = null;` near the top of the
     `ws.onmessage` handler scope. On the first
     `assistant_chunk` event of a streaming turn, set
     `currentStreamingVisibility = data.visibility || null;`.
     When constructing the placeholder bubble at line 839, pass
     `{ renderMarkdown: false, visibility: currentStreamingVisibility }`.
     On `done` or the final `assistant` event, reset
     `currentStreamingVisibility = null;`. (Today
     `data.visibility` is `undefined` — the streaming bubble
     renders without the marker; refresh fixes it. Wiring lands
     for the future live-broadcast tagging leg.)

4. **Browser test**
   (`tests/browser/test_flow_chat_visibility_distinction.py`):
   - Mirror `tests/browser/test_flow_keyboard.py` shape for
     fixture + Playwright setup.
   - Build seeded messages programmatically:
     ```python
     from the_one.llm.base import Message, Role
     from the_one.db.codec import encode_messages
     from the_one.connectors import OPERATOR_VISIBILITY

     msgs = [
         Message.system("you are a test agent"),
         Message.user("hello bot", visibility=OPERATOR_VISIBILITY),
         Message.assistant("hi operator", visibility=OPERATOR_VISIBILITY),
         # Add a peer-visible TOOL for the assertion contrast:
         Message.tool(
             ToolResult(tool_call_id="tc1", content="...", is_error=False),
             visibility=None,
         ),
     ]
     encoded = encode_messages(msgs)
     ```
     If `Message.tool` / `ToolResult` shape requires more setup,
     fall back to a simpler two-message seed (USER + ASSISTANT
     with operator visibility); the contrast can be a third
     message with `visibility=None` of any role.
   - Insert the seeded row via `chat_repo.create(ChatSession(...))`
     with `platform="stub"` and the encoded `messages` blob.
   - Boot the app; navigate to the seeded session
     (likely via WS `join` action or by querying the session-list
     and clicking the row).
   - Assertions:
     ```python
     operator_only = page.locator('.msg-operator-only')
     assert operator_only.count() >= 2
     labels = page.locator('.msg-operator-only-label')
     assert labels.count() >= 2
     # Pin label text
     assert labels.first.text_content() == '[operator-only]'
     # Peer-visible bubble (TOOL) lacks the class
     tool_bubble = page.locator('.msg.tool')
     assert tool_bubble.evaluate(
         "el => el.classList.contains('msg-operator-only')"
     ) is False
     ```

5. **Full-suite + lint**:
   - `make test-unit` clean.
   - `make rebuild` — required so the JS/CSS changes ship into
     the container.
   - `make test-browser` clean.
   - `make lint` clean.

6. **Update flight log** with leg 5's outcomes — files touched,
   browser test added, any token-name or spacing-value
   adjustments, the known live-broadcast tagging gap noted as
   a follow-on.

## Edge Cases

- **`opts.visibility` is `null` / `undefined` / `"peer"` / etc.**:
  the strict equality check `=== 'operator'` makes all of these
  fall through to the byte-identical path. Safe.

- **Live-broadcast events lack `visibility`** (today's reality —
  the known limitation): the call-site forwarding still passes
  `visibility: data.visibility`, which is `undefined`. Render is
  byte-identical to today. After the future live-broadcast
  tagging leg lands, the same wire carries the tagged value and
  the marker shows in real time.

- **A peer-visible bubble follows an operator-only bubble** in the
  timeline: distinct messages get distinct DOM elements; each
  renders independently. Single timeline preserved.

- **The label appears with a markdown-rendered assistant body**:
  the markdown render returns a DocumentFragment whose root is
  typically `<p>`; the label is a `<span>` sibling. Visually:
  small mono-tiny-muted `[operator-only]` tag, then the
  markdown body. Inline-block on the label vs block on the
  markdown content puts the label on its own visual line in
  practice (the `<p>` starts a new block). Acceptable; the
  flight design called for "small … label" without specifying
  inline-vs-block. If implementer or HAT operator dislikes the
  placement, `display: inline` on the label + tightening the
  surrounding margins would tuck it inline with the first line
  of body text.

- **The `textContent` swap to `createTextNode`** ONLY happens in
  the `isOperatorOnly` branch — the no-label fast path keeps
  `el.textContent = text` byte-identically. Defends against any
  regression on user/system/tool bubble rendering for non-
  visibility-tagged messages.

- **Streaming-bubble visibility "flip" on finalize** — does NOT
  happen with the proposed design: the placeholder gets its
  visibility class at construction (from
  `currentStreamingVisibility`), not at finalize. The streaming
  text accumulates inside an already-styled bubble. If
  `data.visibility` is `undefined` on `assistant_chunk` (today's
  state), the placeholder is unmarked — same as today; refresh
  fixes the persisted view.

- **Browser-test seed shape**: `Message.tool` requires a
  `ToolResult` instance; if that's heavier than the test
  warrants, the contrast can use a system message with
  `visibility=None` instead. Implementer chooses the simplest
  seed that satisfies the assertion shape.

- **CSS specificity**: existing `.msg.assistant`, `.msg.user`, etc.
  rules set the bubble's left padding/border. `.msg-operator-only`
  adds `border-left` + `padding-left`. If the existing rules
  ALSO set `padding-left`, specificity conflicts may arise. At
  impl start, check `chat.css` for any `.area-chat .msg` rule
  that sets these properties; if found, either increase
  `.msg-operator-only` specificity (`.area-chat .msg.msg-operator-only`)
  or use `!important` (last resort).

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`
  — `renderMessage` reads `opts.visibility`; class + label
  injection; non-markdown `textContent`-vs-`createTextNode` swap
  in the labeled branch.
- `the_one/interfaces/web/static/js/areas/chat.js` — call-site
  forwards `visibility` (history replay, tool bubble, streaming
  bubble, live event handlers).
- `the_one/interfaces/web/static/css/chat.css` — new
  `.msg-operator-only` + `.msg-operator-only-label` rules inside
  `@layer areas`.
- `tests/browser/test_flow_chat_visibility_distinction.py` (new)
  — DOM-shape browser test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit`, `make rebuild && make test-browser`, `make lint` clean)
- [ ] Update flight-log.md with Leg 5 progress entry, including
      the known live-broadcast tagging gap and any token /
      specificity adjustments.
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until
      end-of-flight review.

## Citation Audit

11 citations verified against current code at leg design time:

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:22`
  — `renderMessage(cls, text, opts)` (verified).
- `the_one/interfaces/web/static/js/areas/chat.js:116` — `addMsg`
  (verified).
- `the_one/interfaces/web/static/js/areas/chat.js:233` — history-
  replay `histOpts` construction (verified).
- `the_one/interfaces/web/static/js/areas/chat.js:461` — tool-
  bubble `App.chat.renderMessage` (verified).
- `the_one/interfaces/web/static/js/areas/chat.js:839` — streaming-
  bubble placeholder construction (verified).
- `the_one/db/codec.py:114-187` — `messages_to_ui_events`
  (verified; emits `visibility` when non-None at line 154).
- `the_one/connectors/__init__.py:52` — `OPERATOR_VISIBILITY`
  (verified).
- `the_one/interfaces/web/static/css/chat.css:1` — `@layer areas {`
  wrapping (verified).
- `the_one/interfaces/web/static/css/tokens.css` — `--border-strong`
  at lines 4-5; `--fg-tertiary` at lines 8-9; `--font-family-mono`
  + `--font-size-tiny` exist (verified; the prior draft's
  `--accent-muted` / `--space-2` / `--space-1` do NOT exist —
  fixed).
- `tests/browser/test_flow_keyboard.py` — Playwright fixture
  precedent (verified).
- `the_one/interfaces/web/app.py:817` — `user_event = {"type":
  "user", "content": user_input, "source": source}` (verified;
  the prior draft cited 801 — fixed). This leg does NOT modify
  this line; reference for the known live-broadcast gap.
