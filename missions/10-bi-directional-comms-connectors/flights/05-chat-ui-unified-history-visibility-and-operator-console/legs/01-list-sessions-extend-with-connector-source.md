# Leg: list-sessions-extend-with-connector-source

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Extend the `list_sessions` WebSocket action's per-row projection to expose the
connector-keying fields already on `ChatSession`, and extend the Chat sidebar's
`buildSessionItem` renderer to surface a source badge when a row is
connector-bound — so the operator can distinguish at a glance which sessions
originated on an external platform vs. the local Chat UI.

## Context

- **Flight slot**: F5 L1 — the read-and-render foundation. F3 already
  persists the `(platform, connector_account_id, channel_id, thread_id,
  peer_id, session_metadata, last_inbound_at)` quintuple-plus-metadata-plus-
  timestamp on every `chat_sessions` row (see `the_one/db/models.py:209` —
  `class ChatSession(BaseModel)` and `the_one/db/repositories.py:670` —
  `ChatSessionRepository.list`); F4 added `agents.connector_account_ids`.
  Nothing surfaces the connector-bound nature of a session in the operator's
  Chat sidebar today.
- **Flight design decision — "Session-list source surfacing: text-style badge
  per row"** (flight.md L52-56): badge mirrors `entity-tile-badge` precedent
  from `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js`
  (badge text = connector-type string; F5 ships `stub`; F8/F9 ship
  `discord`/`slack`).
- **Flight design decision — "`list_sessions` WS action returns the connector-
  keying fields"** (flight.md L58-62): one-line projection extension; pre-F5
  clients ignoring the new fields keep working.
- **Mission constraint**: agent loop is not modified by this flight. This
  leg's scope is the WS projection + frontend rendering; no Python beyond
  `the_one/interfaces/web/app.py` and tests, no JS beyond the chat sidebar
  + tests, no CSS beyond `chat.css`.
- **Mission Known Issue** about per-session lock unification (mission.md
  L101-102) is NOT addressed in this leg — it's leg 2.
- **F4 dispatcher tags `visibility` on messages** (`the_one/connectors/_inbound.py`)
  — irrelevant here; this leg renders only session-list metadata, not message
  bodies.

## Inputs

- `the_one/interfaces/web/app.py:1246` — current `list_sessions` action
  handler projects `{id, title, agent_name, created_at, updated_at}` per row;
  rest of the `ChatSession` fields are ignored.
- `the_one/db/models.py:209` — `class ChatSession(BaseModel)` already carries
  `platform`, `connector_account_id`, `channel_id`, `thread_id`, `peer_id`,
  `session_metadata`, `last_inbound_at` (all default `None` for non-
  connector sessions; F3 L1 landed these).
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:35` —
  `buildSessionItem(s, currentSessionId, callbacks)` builds the per-row
  DOM (an `<li class="list-item">` containing a `<button class="session-item">`
  with `.session-item-text` → `.session-item-title` + `.session-item-agent`,
  plus a delete button).
- `the_one/interfaces/web/static/js/areas/chat.js:709` — `ws.onmessage`
  handler routes `data.type === 'session_list'` to
  `App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, …)`.
- `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js:97-98` —
  `entity-tile-badge` + `entity-tile-badge admin-mcp-badge admin-mcp-badge--{type}`
  precedent for source-typed badge classes.
- `the_one/interfaces/web/static/css/components.css:560` — the
  `.entity-tile-badge` rule is `position: absolute; top: 8px; right: 8px;
  font-mono; tiny; uppercase`. The session-list row is NOT a tile, so this
  exact rule's positioning won't suit — a new `session-item-source` class is
  appropriate, styled in the same idiom (mono, tiny, uppercase) but
  positioned inline alongside `.session-item-agent`.
- `the_one/interfaces/web/static/css/chat.css:14-35` — existing session-list
  layout rules (`.session-group-list`, `.session-item-text`, `.session-item-
  title`, `.session-item-agent`). Add the source-badge rule here.

## Outputs

- `the_one/interfaces/web/app.py` — `list_sessions` handler projects ALL
  seven connector-keying fields in addition to today's five.
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` —
  `buildSessionItem` appends a `.session-item-source` element to the
  `.session-item-text` flex container when `s.platform` is non-null;
  no change for non-connector rows.
- `the_one/interfaces/web/static/css/chat.css` — new `.session-item-source`
  rule using existing M04/M06 tokens.
- New test file `tests/test_web_list_sessions_projection.py` — unit-level
  Python test of the WS handler's projection shape (using the existing
  WS-handler-isolation patterns from `tests/test_app_websocket_pause_resume.py`
  or, if simpler, by calling the projection logic directly).
- New JS browser-test or unit-test coverage that the badge renders only when
  `platform != null`. Browser tests run via the existing Playwright recipe
  (see `tests/browser/test_flow_keyboard.py` for the `app_with_agent`
  fixture pattern); local-only snapshot baselines per user-global rule.

## Acceptance Criteria

- [ ] `list_sessions` WS action returns, for each session, the connector-keying
      fields `platform`, `connector_account_id`, `channel_id`, `thread_id`,
      `peer_id`, `last_inbound_at` in addition to the existing
      `id`, `title`, `agent_name`, `created_at`, `updated_at`.
      - For non-connector sessions, all six new fields are `null`/`None`.
      - For connector-bound sessions, the values reflect the
        `chat_sessions` row.
      - `session_metadata` is NOT projected at this leg (it's a free-form
        dict; surfacing it requires UI-level handling F5 doesn't yet do).
- [ ] Python unit test asserts the projection contains the new fields for
      a connector-bound session and `null` for a non-connector session.
- [ ] `buildSessionItem` renders a `<span>` with the two-class shape
      `session-item-source session-item-source--{platform}` and
      `textContent === s.platform` when `s.platform` is a non-empty
      string; renders no such element when `s.platform` is `null`,
      `undefined`, or an empty string. The typed modifier class
      mirrors the `entity-tile-badge admin-mcp-badge admin-mcp-badge--{type}`
      precedent in `mcp-servers-grid.js:97-98` so future connector types
      (F8 discord, F9 slack) can be color-themed via additive CSS rules
      without touching JS.
- [ ] The badge element appears INSIDE the existing `.session-item-text`
      container (not in a new flex slot) so the existing
      `flex/min-width:0` ellipsis behavior of `.session-item-title`
      continues to apply unchanged.
- [ ] `.session-item-source` CSS rule lives in `chat.css`, uses existing
      tokens (`var(--font-family-mono)`, `var(--font-size-tiny)`,
      `var(--fg-tertiary)` or similar), rendered uppercase, with subtle
      spacing distinguishing it from `.session-item-agent`.
- [ ] Existing chat tests pass byte-identically (regression net): non-
      connector sessions render exactly as before; `list_sessions` payload
      for pre-F5 fields is unchanged.
- [ ] `make test-unit` clean (full Python unit suite); `make lint` clean.
- [ ] Browser-test recipe passes; if a snapshot baseline is added, it is
      generated locally and gitignored.

## Verification Steps

Verified `Makefile` targets: `test` (full default suite), `test-unit`
(unit-only), `test-browser` (Playwright), `test-pixel` (visual
snapshots — baselines local-only), `lint` (ruff check), `rebuild`
(rebuild container — REQUIRED after editing JS/CSS/Python so the
running container picks up the source change).

- **WS projection test**:
  `docker exec the-one pytest tests/test_web_list_sessions_projection.py -x --timeout 30 -v`
  — new test asserts projection shape for both connector and non-
  connector rows.
- **Regression net for the rest of the suite**:
  `make test-unit` (preferred) OR
  `docker exec the-one pytest -x --timeout 60 -q` for finer control
  during iteration — full unit suite clean.
- **Lint**: `make lint` clean (project-wide ruff check).
- **Container rebuild before browser test**: `make rebuild` (the JS/CSS
  changes ship in the container image; without rebuild the browser
  test runs against the old assets).
- **Frontend smoke**: with the container running, seed a stub-connector
  session via `tests/_connector_dispatch_helpers.py` (or the equivalent
  fixture used by existing connector tests), open the Chat sidebar,
  confirm the row shows a `stub` badge and a non-connector row does not.
- **Browser test** (if added): `make test-browser` (preferred —
  ensures the container has Playwright Chromium provisioned via
  `_ensure-playwright`) — confirms the badge appears for a connector-
  bound session.

## Implementation Guidance

1. **Extend the WS projection** (`the_one/interfaces/web/app.py`, around
   line 1246 in the `list_sessions` action handler):
   - In the list-comprehension building `sessions_list`, add the six new
     fields. Pydantic models in this project expose attribute access; the
     fields default to `None`, so plain `s.platform` works for all rows.

   ```python
   sessions_list = [
       {
           "id": s.id,
           "title": s.title,
           "agent_name": s.agent_name,
           "created_at": s.created_at,
           "updated_at": s.updated_at,
           # M10 F05 L01: connector-keying fields surface the source of
           # connector-bound sessions in the Chat sidebar. All six default
           # None for non-connector sessions (back-compat with pre-F5 client).
           "platform": s.platform,
           "connector_account_id": s.connector_account_id,
           "channel_id": s.channel_id,
           "thread_id": s.thread_id,
           "peer_id": s.peer_id,
           "last_inbound_at": s.last_inbound_at,
       }
       for s in db_sessions
   ]
   ```

   Do NOT project `session_metadata` — it's free-form dict content with
   no F5 consumer; lifting it changes payload shape for no current
   benefit and may carry sensitive routing data we shouldn't expose to
   the client unfiltered.

2. **Extend `buildSessionItem`** (`the_one/interfaces/web/static/js/areas/chat/history-buckets.js`,
   line 35):
   - Insert at line 69 — between the existing `agentSpan` append on line 68
     and the `btn.appendChild(textWrap)` on line 70 — conditionally append
     a third span carrying both the base class and the typed modifier:

   ```javascript
   // M10 F05 L01: connector-bound sessions show a source badge so the
   // operator can distinguish platform-driven conversations from web-native
   // ones at a glance. Non-connector rows (platform == null) render
   // exactly as before. The typed modifier class (session-item-source--{type})
   // mirrors mcp-servers-grid.js's admin-mcp-badge--{type} precedent so
   // future connector types can be color-themed via additive CSS only.
   if (s.platform) {
     var sourceSpan = document.createElement('span');
     // sanitize the platform value before letting it flow into a class
     // name — same defensive shape as mcp-servers-grid.js:97-98 which
     // wraps the badge-type suffix in escapeAttr. textContent is already
     // XSS-safe (DOM API, not innerHTML); the escapeAttr-equivalent only
     // matters for the className path.
     var typeSafe = String(s.platform).replace(/[^a-zA-Z0-9_-]/g, '');
     sourceSpan.className = 'session-item-source' + (typeSafe ? ' session-item-source--' + typeSafe : '');
     sourceSpan.textContent = s.platform;
     textWrap.appendChild(sourceSpan);
   }
   ```

   - Truthiness check (`if (s.platform)`) handles `null`, `undefined`, and
     empty string in one branch — the three values that should not produce
     a badge.
   - The `typeSafe` sanitization strips characters that aren't safe in a
     CSS class name; if the platform value contains nothing safe (extremely
     unlikely — connector types are short ASCII identifiers from a
     controlled vocabulary) the modifier class is omitted but the base
     `.session-item-source` class still applies.

3. **Add the CSS rule** (`the_one/interfaces/web/static/css/chat.css`).
   The entire chat-area stylesheet is wrapped in `@layer areas { ... }`
   (line 1). The new rule MUST be inside that `@layer areas` block so it
   participates in the cascade-layer ordering — add it immediately after
   the existing `.session-item-agent` rule at line 35 (before the
   `=== Chat Area: Content ===` divider at line 37):

   ```css
   .area-chat .session-item-source {
     font-family: var(--font-family-mono);
     font-size: var(--font-size-tiny);
     color: var(--fg-tertiary);
     text-transform: uppercase;
     letter-spacing: 0.05em;
     overflow: hidden;
     text-overflow: ellipsis;
     white-space: nowrap;
     margin-top: 2px;
   }
   ```

   The token choices mirror `.session-group-label` (line 15) which already
   uses uppercase + tiny + tertiary for the bucket headers — the source
   badge is the row-scoped analogue. If a different visual treatment
   reads better to the leg implementer (e.g. an inline pill instead of a
   separate line), that is acceptable provided the tokens stay within
   the M04/M06 palette and the result remains visually subordinate to
   the title.

   No per-`session-item-source--{type}` color rule is added in F5: the
   only platform value at F5 is `stub`, so coloring it would be wasted
   work. F8 (discord) and F9 (slack) add their own modifier-rule blocks
   that compose with this base rule.

4. **Write the Python projection test** (`tests/test_web_list_sessions_projection.py`).
   The projection is an inline list-comprehension in the action handler —
   there is no helper function to import. Use the FastAPI TestClient
   against the WebSocket route, mocking `ChatSessionRepository.list` to
   return a controlled pair of sessions:

   - Build two `ChatSession` instances — one with `platform=None` (web-
     native), one with `platform="stub", connector_account_id="acct-1",
     channel_id="C1", thread_id="T1", peer_id="P1",
     last_inbound_at="2026-01-01T00:00:00Z"`.
   - Open a WS connection to `/ws` via `starlette.testclient.TestClient`
     (precedent: `tests/test_origin_allowlist.py` for `TestClient` +
     `websocket_connect` shape).
   - Send `{"action": "list_sessions"}` and read the `session_list` reply.
   - Assert the connector-bound row's payload has `platform == "stub"`
     and the other five new fields match the constructed values.
   - Assert the web-native row's payload has `platform is None` (or
     `null` after JSON deserialize) and the other five fields are
     `None`.
   - Assert that `session_metadata` and `messages` are NOT projected
     (regression net against future implementers over-eagerly adding
     every field).

   If the TestClient path proves cumbersome (e.g. the WS connection
   needs significant setup the project hasn't already wired into a
   conftest fixture), accept a small refactor: extract the projection
   into a helper `_session_to_list_payload(s: ChatSession) -> dict` in
   `app.py` and import-test it directly. The refactor is cheap and
   makes the test trivial. Decide based on what produces a shorter,
   clearer test file.

5. **Optional browser-test coverage**: extend `tests/browser/test_flow_keyboard.py`
   or a new `tests/browser/test_session_list_source_badge.py` to:
   - Boot the app with a seeded stub-connector session AND a web-native
     session.
   - Open the Chat area, locate both rows in the session list.
   - Assert the connector row has a `.session-item-source` element with
     `textContent === 'stub'`; the web-native row does not.

   Use DOM-shape assertions (Playwright `locator`, `textContent`,
   `class`) — NOT visual snapshot baselines — per the user-global rule
   that snapshot baselines are local-only and never committed. The
   `test-pixel` recipe exists for snapshot regression work specifically;
   the F5 acceptance criteria do not require it.

6. **Run the verification commands** from Verification Steps. If browser
   tests are slow, run only the focused test (`pytest tests/browser/test_session_list_source_badge.py -x --timeout 60`)
   during iteration; run the full suite once at end-of-leg.

7. **Update the flight log** with this leg's outcomes:
   - Files touched.
   - Tests added (count, names).
   - Any deviation from this plan (e.g. if the projection ended up in a
     helper function, or if the CSS treatment was tightened).

## Edge Cases

- **`s.platform` is the empty string `""`** — truthy-check (`if (s.platform)`)
  treats it as falsy and renders no badge. This is the desired behavior;
  if any future migration introduces an empty-string platform value it
  would render an empty badge, which is wrong. Acceptable to rely on
  truthy-check.
- **Pre-F5 client receiving the new projection** — additional dict keys
  are silently ignored by `App.chat.renderSessionList` (the function only
  reads `s.title`, `s.agent_name`, `s.updated_at`, etc.); no break.
- **Connector session with `agent_name=null`** — already handled by the
  existing `s.agent_name || 'default'` fallback at line 67. The
  source-badge rendering is independent.
- **Many connector-bound sessions with the same `platform` value** — at
  F5 with the stub connector, the operator sees many `stub` badges. This
  is cosmetic and resolves at F8/F9 when real connector types land.
- **`s.platform` carrying an unexpected value** (defensive against rogue
  database content) — `textContent = s.platform` is XSS-safe (DOM API,
  not innerHTML) — same correctness shape as the precedent at
  `mcp-servers-grid.js:98` which wraps the badge text in
  `escapeHtml(s.type)`. For the CSS class name, the `typeSafe` regex strip
  in step 2 enforces a safe character set before the value flows into
  `className`. Connector-type strings are short ASCII identifiers from a
  controlled server-side vocabulary (`stub`, `discord`, `slack`); the
  defense is belt-and-suspenders, not a primary trust line.

- **`last_inbound_at` has no F5 consumer** — projected eagerly so F6's
  pairing-UI work (which may want to show "last activity from this
  peer") doesn't need a second projection-extension pass. Adds ~30 bytes
  per row; negligible for the single-user local-tool session count.

## Files Affected

- `the_one/interfaces/web/app.py` — projection extension at line ~1246
  (six additional dict keys).
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` —
  `buildSessionItem` adds source-span when `s.platform`.
- `the_one/interfaces/web/static/css/chat.css` — new
  `.session-item-source` rule.
- `tests/test_web_list_sessions_projection.py` — new file; Python unit
  test for the projection shape.
- Optionally `tests/browser/test_session_list_source_badge.py` (or
  extension of an existing browser test) — UI rendering check.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit`, `make lint` clean)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until end-of-flight
      review; the Reviewer evaluates all uncommitted legs together.

## Citation Audit

8 citations verified against current code at leg design time:

- `the_one/interfaces/web/app.py:1246` — `list_sessions` action handler.
  Verified `if action == "list_sessions":` at this line.
- `the_one/db/models.py:209` — `class ChatSession(BaseModel)` with all
  connector-keying fields declared at lines 237–243. Verified.
- `the_one/db/repositories.py:670` — `ChatSessionRepository.list` returns
  `list[ChatSession]`. Verified.
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:35` —
  `buildSessionItem(s, currentSessionId, callbacks)`. Verified.
- `the_one/interfaces/web/static/js/areas/chat.js:709` — `ws.onmessage`
  routes `data.type === 'session_list'` to `App.chat.renderSessionList`.
  Verified.
- `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js:97-98` —
  `entity-tile-badge admin-mcp-badge admin-mcp-badge--{type}` precedent.
  Verified at line 97.
- `the_one/interfaces/web/static/css/components.css:560` —
  `.entity-tile-badge` rule. Verified at line 560.
- `the_one/interfaces/web/static/css/chat.css:14-35` — existing session-
  list layout rules. Verified `.session-group`, `.session-item-text`,
  `.session-item-agent` at this range.
