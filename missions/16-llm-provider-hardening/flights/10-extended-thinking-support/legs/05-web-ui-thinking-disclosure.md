# Leg: web-ui-thinking-disclosure

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

## Objective

Surface captured thinking in the web chat as a **collapsed-by-default `<details>` disclosure**
per assistant turn — emitted live at turn-settle (DD2 reveal-after) and re-projected on chat
reopen from persistence — reusing the existing tool-trace disclosure idiom with **distinct
identifiers** (never the active `.msg.thinking` loading spinner).

## Context

- Legs 01–04 landed: assistant `Message` objects carry `thinking: list[ThinkingBlock]`
  (`base.py`; `ThinkingBlock{type, thinking, signature, data}`), captured on both provider paths
  and round-tripped through the codec. This leg is the **read/display** side — no provider or
  protocol change.
- **DD2 reveal-after.** The answer streams as today; the thinking disclosure appears when the
  turn settles (a `thinking` WS event fires after the answer). No live token-by-token thinking.
- **DD3 collapsible `<details>`.** Reuse the tool-trace disclosure idiom
  (`trace-shell.js` `renderTrace`; `chat.css` `.trace-shell` `:149–208`) — collapsed by default,
  native `<details>/<summary>` keyboard/focus behavior, no JS toggle. **Distinct identifiers:**
  the existing `.msg.assistant.thinking` (`chat.css:444–445`) + `createThinking`/`removeThinking`
  (`thinking-indicator.js:11/39`) are the **ACTIVE ephemeral "thinking…" loading spinner** — do
  NOT reuse those names/classes. Use e.g. `.thinking-disclosure`.
- **Display text only.** The UI shows human-readable reasoning: concatenate the `.thinking` of
  `type=="thinking"` blocks. `redacted_thinking` blocks have only opaque `.data` (no text) → show
  a `[reasoning redacted]` marker when a turn has only redacted blocks. Signatures/`data` never
  reach the client (backend-only, for replay).
- **F09-07 cache-busting invariant.** Static assets are auto-versioned: `_cache_busted_index_html`
  (`app.py:91–110`) appends `?v={__version__}` to every `/static/*.js|.css` ref, and `index()`
  serves the HTML `no-store` (`app.py:1872–1875`). **Consequence:** editing existing JS/CSS needs
  no action (auto-busted). **Adding a NEW static file requires referencing it in `index.html`** —
  so **prefer adding `renderThinking` to an existing already-loaded module** (`trace-shell.js` or
  `chat.js`) over a new file, to avoid an index.html edit + keep the cache-bust automatic.
- **DD5 provider-agnostic.** The event/projection/render key on `Message.thinking`, not on any
  provider — Ollama/OpenAI would surface identically once they populate the field.

## Inputs (current hook points — verified 2026-07-02)

- `the_one/db/codec.py` — `messages_to_ui_events` ASSISTANT branch (`:293–308`): emits the
  `assistant` event (`:295`) then `tool_call` events (`:296+`, sets
  `current_parent_id = f"replay-msg-{i}"`). **Thinking event inserts between them.**
- `the_one/interfaces/web/app.py` — `_process_and_broadcast` loop
  (`async for msg in session.agent.step(...)` at `:1533`): per assistant `msg`, emits `usage`
  (`:1548–1555`), the `assistant` content event (`:1557–1565`, `session.add_event(event)` +
  conditional broadcast), then `tool_calls` (`:1566+`); `done` at `:1709`. **`msg.thinking` is
  available here** — the thinking event inserts in this block. History replay:
  `messages_to_ui_events` call at `:979` (`_restore_session`), sent in `session_joined`
  (`history: session.history`, `:1141`); client renders via `renderHistory(data.history, …)`
  (`:1067`).
- `the_one/interfaces/web/static/js/areas/chat.js` — `ws.onmessage` event ladder (`:987+`;
  `assistant_chunk` handler `:1184–1210`; `assistant`/`done` branches call
  `finalizeStreamingBubble` at `:586`); `renderHistory` (`:358–424`, assistant branch `~:390`).
- `the_one/interfaces/web/static/js/areas/trace-shell.js` — `renderTrace` (`:21–49`) builds
  `<div class="trace-shell"><details><summary class="trace-toggle">…</summary><div
  class="trace-body">…</div></details></div>` — the disclosure idiom to mirror.
- `the_one/interfaces/web/static/css/chat.css` — `.trace-shell` + `summary.trace-toggle`
  disclosure styles (`:149–208`, reuse); `.msg.assistant.thinking` spinner (`:444–445`, AVOID).

## Outputs

- `the_one/db/codec.py` — a `thinking_display_text(blocks)` helper + a `thinking` event in the
  `messages_to_ui_events` ASSISTANT branch (from persisted `msg.thinking`).
- `the_one/interfaces/web/app.py` — a live `thinking` WS event in `_process_and_broadcast` when a
  settled assistant `msg` has displayable thinking (using the same helper).
- `the_one/interfaces/web/static/js/…` — a `thinking` handler in `ws.onmessage`, a `thinking`
  branch in `renderHistory`, and a `renderThinking(...)` builder (in `trace-shell.js` or
  `chat.js`) producing a collapsed `<details>` with a distinct class.
- `the_one/interfaces/web/static/css/chat.css` — a `.thinking-disclosure` rule block reusing the
  trace-shell disclosure styling (distinct from `.msg.thinking`).
- Tests: codec-projection unit test (hermetic); a frontend render check (Playwright or JS-unit,
  per harness); the full live disclosure+persistence acceptance is the **Leg 07 behavior test**.

## Acceptance Criteria

- [x] `thinking_display_text(blocks: list[ThinkingBlock]) -> str` returns the concatenated
      `.thinking` of `type=="thinking"` blocks (in order); returns `"[reasoning redacted]"` when a
      turn has ONLY `redacted_thinking` blocks; returns `""` when there is no thinking. Single
      source of truth, used by both emit sites.
- [x] `messages_to_ui_events` emits a `{"type": "thinking", "content": <display text>,
      "parent_message_id": "replay-msg-{i}", **vis}` event in the ASSISTANT branch — **after** the
      `assistant` content event, **before** the `tool_call` events — **only when**
      `thinking_display_text(msg.thinking)` is non-empty. Turns without thinking project
      byte-identically to today (regression-guarded).
- [x] `_process_and_broadcast` **broadcasts** a live `thinking` event (`{"type":"thinking",
      "content": <text>}`, **no** `session.add_event`) when a settled assistant `msg` has
      displayable thinking, positioned so it reveals **after** the answer (DD2). It is
      projection-only (interim-usage precedent) — reopen re-derives thinking from the persisted
      `msg.thinking` via the codec, so there is no double-render and `message_count` isn't
      inflated. The thinking event is NOT included in the REST `result_messages` payload.
- [x] The client renders the `thinking` event (live AND in `renderHistory` replay) as a
      **collapsed-by-default `<details>` disclosure** associated with the assistant turn, showing
      the reasoning text, reusing the trace-shell idiom. It is keyboard-focusable and toggles via
      Enter/Space (native `<details>`). `[a11y]`
- [x] **`renderThinking` is position-independent** — it appends to the messages container in
      stream order (mirroring `getOrCreateTrace`, which appends to `messagesEl` without requiring a
      preceding assistant bubble), NOT as a child of "the last assistant bubble." This is required
      because criterion #1's core turn (thinking + tool call, **empty `content`**) emits a thinking
      event with **no** preceding assistant content event. It must NOT route through
      `getOrCreateTrace` (that would nest the disclosure inside the tool-trace shell — it is its
      own disclosure). Placement relative to the answer (DD3 "above" vs. below) is HAT-tunable
      (flight acceptable-variation); v1 attaches with the turn per the trace-shell idiom.
- [x] **`renderThinking` tolerates both event shapes** — the live event is
      `{"type":"thinking","content":…}` (no `parent_message_id`/`vis`); the replayed event adds
      `parent_message_id` + visibility. Missing keys must not throw. (Live omission of `vis` matches
      the live `assistant` event, which also applies visibility only on replay.)
- [x] **Distinct identifiers:** the disclosure uses a new class (e.g. `.thinking-disclosure`) and
      a new `renderThinking` function — it does NOT reuse or modify `.msg.assistant.thinking`,
      `createThinking`, `removeThinking`, or the loading-spinner path.
- [x] Redacted-only turn renders the `[reasoning redacted]` marker in the disclosure (does not
      break the turn); a turn with no thinking renders no disclosure.
- [x] **F09-07 cache-busting respected:** no new un-referenced static file (or, if a new file is
      truly needed, it is referenced in `index.html` so the auto-bust covers it). Editing existing
      chat.js/trace-shell.js/chat.css is auto-versioned — confirm `?v=` still applies.
- [x] **MockProvider emits thinking** (dev-mode): extend `mock.py` so a configured
      `config["response"]["thinking"]` (list of block dicts) is parsed into
      `[ThinkingBlock(...)]` on the synthesized assistant `Message` (mirroring how it already reads
      `response.tool_calls`). This is the seam that lets a browser test drive the REAL disclosure
      end-to-end with no live Anthropic key.
- [x] Autonomous tests pass — TWO hard gates: (1) the codec-projection unit test (thinking event
      emitted/omitted/redacted-marker; includes the **`content="" thinking+tool_calls`** turn); and
      (2) a **required** Playwright/browser test that, via the MockProvider thinking seam, sends a
      turn that produces thinking, asserts the `<details>` disclosure renders **collapsed** by
      default, **expands** on toggle, coexists with a tool trace, and **survives a chat reopen**
      (history replay). Full unit + browser suites green (minus the known aiosqlite flake). The
      live (real-Anthropic) disclosure is additionally covered by the Leg 07 behavior test.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_codec.py -x --timeout 30` —
  the codec `thinking` projection test passes; the byte-identity tripwire and existing
  projection tests still pass (a no-thinking assistant message projects unchanged).
- Frontend: run the relevant browser/Playwright chat suite (`-m browser`) if a `thinking`-event
  render test is added; else a JS-unit/DOM assertion. Confirm the `<details>` is collapsed by
  default and expands.
- `grep -n "thinking-disclosure\|renderThinking\|createThinking\|removeThinking" the_one/interfaces/web/static/js/` —
  confirm the new disclosure identifiers are distinct from the spinner.
- Confirm cache-bust: load `index()` and check the new/edited asset refs carry `?v={version}`.
- `make test-unit` once at leg end — green minus the known teardown flake.
- Full live disclosure + reopen persistence: **Leg 07** `/behavior-test extended-thinking-tool-turn`.

## Implementation Guidance

1. **Shared display helper** in `the_one/db/codec.py` (imported by app.py):

   ```python
   def thinking_display_text(blocks: list[ThinkingBlock]) -> str:
       """Human-readable reasoning for the UI. Concatenates type=='thinking'
       text; a redacted-only turn yields a marker; no thinking yields ''.
       Signatures/data never reach the client."""
       texts = [tb.thinking for tb in blocks if tb.type == "thinking" and tb.thinking]
       if texts:
           return "\n\n".join(texts)
       if any(tb.type == "redacted_thinking" for tb in blocks):
           return "[reasoning redacted]"
       return ""
   ```

2. **Codec projection** — in `messages_to_ui_events` ASSISTANT branch (`codec.py:293–308`),
   insert AFTER the `if msg.content:` assistant event and BEFORE the `if msg.tool_calls:` block:

   ```python
   _thinking_text = thinking_display_text(msg.thinking)
   if _thinking_text:
       events.append({
           "type": "thinking",
           "content": _thinking_text,
           "parent_message_id": f"replay-msg-{i}",
           **vis,
       })
   ```

   (`vis` is the visibility spread already computed in the loop. Do not project signatures.)
   Add a `TestMessagesToUiEventsThinking` test class in `tests/test_db_codec.py` (mirror the
   existing `messages_to_ui_events` test style): a thinking-bearing assistant message → a
   `thinking` event with the joined text; a no-thinking message → no thinking event; a
   redacted-only message → the marker; **a `content=""` thinking+tool_calls turn → the thinking
   event is emitted (no assistant event) followed by the tool_call events** (criterion #1's shape);
   and a no-thinking full-conversation still projects byte-identically (the existing
   `test_full_conversation` exact-dict assertion stays green).

3. **Live emit** — in `app.py` `_process_and_broadcast`, inside the `if msg.role ==
   Role.ASSISTANT:` block (after the `assistant` content event at `:1557–1565`, before/around the
   tool_calls projection), emit a `thinking` event when displayable, mirroring the assistant
   event's append+broadcast:

   ```python
   _thinking_text = thinking_display_text(msg.thinking)
   if _thinking_text:
       # Broadcast-only projection (like interim usage at :1503-1520) — do NOT
       # session.add_event(): thinking is a projection DERIVED from msg.thinking,
       # not an independent persisted entity. Reopen re-derives it from the same
       # persisted msg.thinking via the codec; add_event would only inflate
       # message_count for an entry that's immediately overwritten by the
       # DB-rebuild on the next join.
       await _send_to_session(session, {"type": "thinking", "content": _thinking_text})
   ```

   (Import `thinking_display_text` from `the_one.db.codec` — `app.py:50–55` already imports from
   that module; no cycle.) Reveal-after holds because this fires as the settled assistant `msg` is
   processed — after the answer already streamed via chunks. **Design-review resolution:**
   broadcast-only (NOT `add_event`) — `session.history` is fully rebuilt from the codec on every
   join (`:996/:1015`), so neither choice double-renders; broadcast-only is the cleaner fit
   (matches the interim-usage precedent, doesn't inflate `message_count`). Keep the thinking event
   out of the REST `result_messages` payload (`~:1585–1592`).

4. **Frontend handler + render** — in `chat.js`:
   - `ws.onmessage` ladder (`:987+`): add `else if (data.type === 'thinking') { renderThinking(data); }`
     (place it so it doesn't call `hideThinking()` incorrectly — the loading spinner is already
     hidden by the assistant/chunk path by the time thinking arrives; do not disturb it).
   - `renderHistory` (`:358–424`): add `else if (ev.type === 'thinking') { renderThinking(ev); }`
     in the replay branch (after the `assistant` branch `~:390`).
   - Add `renderThinking(evt)` (in `trace-shell.js` alongside `renderTrace`, or in `chat.js`):
     build a collapsed `<details class="thinking-disclosure">` with a `<summary>` labeled
     "Thinking" and a body containing `evt.content`. **Position-independent:** append to
     `messagesEl` in stream order (mirror `getOrCreateTrace`, which appends without requiring a
     preceding bubble) — do NOT attach as a child of "the last assistant bubble" (criterion #1's
     turn has empty `content` → no preceding bubble). Do NOT route through `getOrCreateTrace` (it
     is its own disclosure, not a tool-trace child). Tolerate missing `parent_message_id`/`vis`
     (live shape). The ws handler must call only `renderThinking(data)` (+ `scrollToBottomIfPinned`
     if that's the convention) — **not** `hideThinking()` or `finalizeStreamingBubble()`. **Do
     NOT** touch `createThinking`/`removeThinking`/`showThinking`/`hideThinking`.

5. **CSS** — in `chat.css`, add a `.thinking-disclosure` rule block AFTER the trace-shell rules
   (`~:208`), reusing the `.trace-shell`/`summary.trace-toggle`/`.trace-body` visual pattern
   (border-left, muted mono summary, custom disclosure triangle). Do NOT extend
   `.msg.assistant.thinking` (`:444`). Keep the reasoning body readable (wrap long text;
   preserve newlines).

6. **Cache-bust** — reuse existing modules so no `index.html` edit is needed; the version query
   is applied automatically. If a new JS file is unavoidable, reference it in `index.html` with
   the `<script src="/static/…">` pattern the regex matches, and verify `?v=` appears.

7. **MockProvider thinking seam + browser test.** In `the_one/llm/mock.py`, where the mock builds
   its synthesized `Message.assistant(...)` from `config["response"]` (it already reads
   `response.tool_calls` at `mock.py:~87–94`/`~146–150`), also read an optional
   `response["thinking"]` (a list of block dicts) and pass `thinking=[ThinkingBlock(**b) for b in
   …]` into the assistant Message. `enable_thinking` stays accepted-and-ignored. This is dev-mode
   only, no protocol change. Then add a **required** Playwright/browser test (under
   `tests/browser/`) that: configures the mock agent to return thinking + a tool call, sends a
   message, and asserts (a) the `.thinking-disclosure` `<details>` renders collapsed, (b) it
   expands on click/Enter, (c) the tool trace also renders (coexistence), (d) after a page
   reload / chat reopen the disclosure re-renders from history. This exercises the real emit →
   codec-replay → render path end-to-end without a live Anthropic key.

## Edge Cases

- **No thinking on the turn** → helper returns `""` → no event emitted → no disclosure (the
  common case; must be byte-identical to today for both live and replay).
- **Redacted-only turn** → `[reasoning redacted]` marker; the turn must not break.
- **Thinking + tool calls same turn** → the thinking disclosure and the tool-trace shell both
  render for the turn (distinct disclosures). Confirm they don't collide in the DOM or share a
  toggle. The codec emits thinking before the tool_call events (ordering preserved).
- **Streaming vs. non-streaming** → thinking reveals after the answer either way (the event fires
  at settle). On the non-streaming path (`not chunks_seen`), the assistant event broadcasts then
  the thinking event follows — order preserved.
- **Very long reasoning** → the disclosure is collapsed by default (that is the point — keep the
  transcript clean); the body scrolls/wraps.
- **Same-session reconnect** → `session_joined` history is codec-rebuilt (`:979`), which now
  includes thinking — consistent with the live render.

## Files Affected

- `the_one/db/codec.py` — `thinking_display_text` helper + `thinking` projection in
  `messages_to_ui_events`.
- `the_one/interfaces/web/app.py` — live `thinking` event in `_process_and_broadcast`.
- `the_one/interfaces/web/static/js/areas/chat.js` — `thinking` ws handler + `renderHistory`
  branch (+ `renderThinking`, here or in trace-shell.js).
- `the_one/interfaces/web/static/js/areas/trace-shell.js` — `renderThinking` (if placed here).
- `the_one/interfaces/web/static/css/chat.css` — `.thinking-disclosure` styles.
- `the_one/llm/mock.py` — dev-mode thinking seam (parse `config["response"]["thinking"]` →
  `ThinkingBlock`s) enabling the autonomous browser test.
- `tests/test_db_codec.py` — codec `thinking` projection tests (incl. the `content=""`
  thinking+tool turn).
- `tests/browser/` — a **required** Playwright test driving the disclosure via the mock seam
  (collapsed default, expand, tool-trace coexistence, survives reopen).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (codec projection + frontend render + full unit/browser suites green minus
      known teardown flake)
- [x] Update flight-log.md with the Leg 05 progress entry
- [x] Set this leg's status to `landed` (NOT `completed` — commit deferred to Phase 2d)
- [x] Do NOT commit; do NOT check off in flight.md; do NOT touch mission.md
- [x] Signal `[HANDOFF:review-needed]`
