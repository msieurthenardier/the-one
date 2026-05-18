# Leg: e2e-tests-and-design-language

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Land the end-to-end browser-flow coverage that the flight's stated
e2e scope requires (flight.md L172-175): a session-list source-badge
test on the e2e tier; an operator-input → connector-attached session
test that exercises the F5 L4 WS storage-edge shim through the
browser; and a written design-language audit confirming the F5-
introduced visual surfaces meet the M04/M06 token/spacing bar
without an alignment-flight rework. The unit tests for legs 3/4/6
already landed inside those legs; this leg fills the e2e gap and
provides the methodology checkpoint before the HAT closer.

## Context

- **Flight slot**: F5 L7 — the e2e-coverage + design-language audit
  leg. The unit tests are already in place (L3: `test_connectors_visibility_helper.py`;
  L4: `test_ws_storage_edge_shim_visibility.py` +
  `test_connectors_e2e_ws_into_connector.py`; L6:
  `test_connectors_inbound_broadcast.py`). The render-side browser
  test landed in L5 (`test_flow_chat_visibility_distinction.py`).
  This leg adds two more browser tests and a written design-
  language audit.
- **Flight In-Flight § Leg 7** (flight.md L172-175): browser-flow
  tests covering — session list shows connector-source badge;
  opening a connector-attached session renders both peer-visible
  and operator-only messages with the right distinction (covered
  by L5's existing browser test); typing into a connector-attached
  session shows operator-visibility on the resulting messages;
  M04/M06 design-language passes. Visual snapshot baselines are
  local-only per user-global rule.
- **L1 deferred a browser-test for the source badge** (its leg
  artifact's step 5 marked it optional, since L7 is the dedicated
  e2e leg). This leg implements that test now.
- **The L4-shim E2E DB round-trip** (`test_connectors_e2e_ws_into_connector.py`)
  exercises the storage path WITHOUT a browser. This leg adds the
  symmetric BROWSER E2E: operator opens a connector-attached
  session in the Chat UI, types into it, observes (after refresh)
  that the resulting persisted messages render with the operator-
  only marker.
- **Live-broadcast visibility gap from L5** means the browser test
  for the operator-input path MUST verify after a session refresh
  (not in the live moment of typing). The L5 leg documented this
  limitation; this leg's test respects it.
- **Design-language audit**: M04 and M06 set the design-language
  bar (`--accent`, `--border-strong`, `--fg-tertiary`,
  `--font-family-mono`, `--font-size-tiny`, hardcoded px spacing
  matching `chat.css` convention). The F5-introduced surfaces are:
  the session-list source badge (L1: `.session-item-source` +
  optional `.session-item-source--{type}`); the operator-only
  marker on message bubbles (L5: `.msg-operator-only` +
  `.msg-operator-only-label`). The audit is a written checklist
  in the flight log enumerating these surfaces against the M04/M06
  token/spacing palette; no separate Python test asserts design-
  language conformance — it's a methodology checkpoint, captured
  in the flight log as a prose audit.
- **Mission constraint**: agent loop is not modified by this leg.
  Browser tests drive the UI through the existing WS + API
  surfaces.
- **Test conventions**: `make rebuild` is REQUIRED before browser
  tests (JS/CSS changes ship in the container image). The browser
  tests use Playwright via `make test-browser`. DOM-shape
  assertions only (no visual snapshot baselines).
- **No schema change. No production code change in this leg.**
  Tests + design-language audit + flight-log update only.

## Inputs

- `tests/browser/test_flow_chat_visibility_distinction.py` — L5's
  browser test. Strategy precedent: spawn fresh app subprocess via
  `app_clean`-like fixture exposing `data_dir`; seed via API
  seeders; INSERT seeded connector-keyed `chat_sessions` row
  directly with `encode_messages`-built blob; navigate via WS
  join; assert DOM shape via Playwright `locator` / `evaluate`.
- `tests/browser/conftest.py:112-188` — `app_clean` fixture; spawns
  a subprocess with empty DB; M10 F2 L6 already wires the
  StubPlugin into the spawned subprocess (lines 129 + 311 per the
  earlier grep). Suitable for the new tests' seeding.
- `tests/browser/conftest.py:228-244` — `app_with_provider`,
  `app_with_agent` layered fixtures. The new tests inherit from
  these to get a provider + agent seeded without re-doing the
  setup.
- `tests/browser/seeders.py` — `seed_mock_provider`,
  `seed_mock_agent` precedents for API-driven seeding.
- `the_one/db/repositories.py:726-744` — `ChatSessionRepository.create`
  signature for the direct-DB INSERT precedent.
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js`
  — `buildSessionItem` (L1's output): renders the
  `.session-item-source` element when `s.platform` is truthy.
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`
  — `renderMessage` (L5's output): adds `msg-operator-only` class
  + `[operator-only]` label when `opts.visibility === "operator"`.
- `the_one/interfaces/web/static/css/chat.css` — source-badge
  rule from L1 (`.session-item-source`); operator-only marker
  rules from L5 (`.area-chat .msg.msg-operator-only`,
  `.area-chat .msg-operator-only-label`). Token palette to audit:
  `--border-strong`, `--fg-tertiary`, `--font-family-mono`,
  `--font-size-tiny`.

## Outputs

- New browser test
  `tests/browser/test_flow_chat_session_list_source_badge.py` —
  source-badge e2e:
  - Spawn fresh app via the `app_with_agent`-style fixture.
  - Seed two `chat_sessions` rows via direct DB insert:
    - Row A: web-native (no connector-keying fields set).
    - Row B: connector-attached (`platform="stub"`,
      `connector_account_id="acct-1"`, `channel_id="C1"`,
      `thread_id=None`, `peer_id="P1"`).
  - Boot the page; navigate to the chat area; wait for the
    session list to render.
  - Assertions:
    - The connector-bound row has a child element with class
      `session-item-source` AND
      `session-item-source--stub`. The text content is `"stub"`.
    - The web-native row has NO `.session-item-source` element.
    - The connector-bound row's badge text matches the
      `platform` value (defensive — pin the JS branch).
- New browser test
  `tests/browser/test_flow_chat_operator_input_visibility.py` —
  operator-input write path e2e:
  - Spawn fresh app via `app_with_agent`.
  - Seed ONE connector-attached session row (similar to the
    source-badge test).
  - Boot the page; navigate to chat; open the seeded session via
    WS join action.
  - Type a message into the chat composer; submit.
  - **Wait for the turn to complete** (e.g. `expect(page.locator(
    '.msg.assistant').last).to_be_visible()` or wait for the
    `done` event by polling for `is_processing=false` via WS
    state).
  - **Refresh the page** (or rejoin the session) to force the
    codec replay path — this is the known limitation from L5;
    live-broadcast visibility tagging is a separate follow-on.
  - After refresh, navigate to the session again; assert the
    just-typed user bubble AND the assistant reply both have
    the `msg-operator-only` class. Assert the `[operator-only]`
    labels are present on both.
  - **Negative control**: also boot a web-native session in the
    same test (or a sibling test) and verify the typed turn has
    NO `msg-operator-only` class on the resulting bubbles (back-
    compat regression net).
- **Written design-language audit** in the flight log: a
  **methodology checkpoint** (not a quality gate — the HAT closer
  in L8 is the final acceptance gate). The audit's purpose is to
  document the F5-introduced visual surfaces' token/spacing
  choices so the operator's HAT review has a concrete inventory
  to refer to, and so future maintainers can verify token
  consistency against the existing M04/M06 palette without
  reading every CSS rule. If the audit surfaces a deviation that
  is cheap to fix inline (CSS-only, <10 lines), apply it; if
  not, document the deviation for the HAT closer. Format:
  ```
  | Surface | Selector | Tokens | Spacing | M04/M06 fit |
  |---------|----------|--------|---------|--------------|
  | Session source badge | `.session-item-source` | `--font-family-mono`, `--font-size-tiny`, `--fg-tertiary` | `padding: 2px 4px` (or per chat.css) | PASS / NOTES |
  | Operator-only marker | `.msg.msg-operator-only` | `--border-strong` | `border-left: 3px; padding-left: 8px` | PASS / NOTES |
  | Operator-only label | `.msg-operator-only-label` | `--font-family-mono`, `--font-size-tiny`, `--fg-tertiary` | `margin-right: 4px` | PASS / NOTES |
  ```
  The audit lives in the flight log as a prose block. If any
  surface fails the bar, the leg notes the deviation and either
  fixes it inline OR escalates to a follow-on alignment-flight
  decision.
- The flight log gains a Leg 7 progress entry recording the two
  new browser tests, the design-language audit summary, and any
  inline fixes applied.

## Acceptance Criteria

- [ ] `tests/browser/test_flow_chat_session_list_source_badge.py`
      exists and exercises the L1 source-badge contract through
      the browser:
      - Connector-attached row shows `.session-item-source` AND
        `.session-item-source--stub` with text `"stub"`.
      - Web-native row shows NO `.session-item-source` element.
- [ ] `tests/browser/test_flow_chat_operator_input_visibility.py`
      exists and exercises the L4-shim write path through the
      browser:
      - After operator types into a connector-attached session
        AND refreshes/rejoins, the resulting USER + ASSISTANT
        bubbles have `msg-operator-only` class + `[operator-only]`
        label.
      - In a parallel web-native session, the typed turn has NO
        `msg-operator-only` markers (negative control).
- [ ] A written design-language audit lives in the flight log
      under a Leg 7 section: tables one row per F5-introduced
      visual surface; columns capture selector, tokens, spacing,
      and PASS/NOTES vs. M04/M06.
- [ ] Any inline design-language fix is documented in the flight
      log AND the relevant CSS/JS is updated in this leg. If a
      surface fails the bar and is NOT cheaply fixable inline,
      the leg notes the deviation and escalates to a follow-on
      decision (NOT a flight-blocking issue per the flight design,
      since the HAT closer is the final acceptance gate).
- [ ] `make rebuild && make test-browser` clean — the two new
      browser tests pass; no other browser tests regress.
- [ ] `make test-unit` clean — no Python-side regression
      (this leg should not edit Python).
- [ ] `make lint` clean.
- [ ] The agent loop in `the_one/agent/core.py` is untouched.
- [ ] No production server-side code changes in this leg.
      (Inline design-language fixes are CSS/JS only.)

## Verification Steps

- **New browser tests**:
  `docker exec the-one pytest tests/browser/test_flow_chat_session_list_source_badge.py tests/browser/test_flow_chat_operator_input_visibility.py -x --timeout 120 -v`
  — pass after `make rebuild`.
- **Full browser-test suite regression**:
  `make rebuild && make test-browser`
  — all existing browser tests + the two new ones pass.
- **Full unit-suite regression**: `make test-unit` clean (this
  leg should add zero unit tests; the baseline 1983 stays put
  unless inline design fixes touch Python — which they shouldn't).
- **Lint**: `make lint` clean.

## Implementation Guidance

1. **Source-badge browser test**
   (`tests/browser/test_flow_chat_session_list_source_badge.py`):
   - Mirror the structure of L5's
     `test_flow_chat_visibility_distinction.py`. **Note**: L5
     defines a LOCAL `app_with_data_dir` fixture in its own file
     (because the shared `app_with_agent` fixture exposes only
     `base_url`/`provider_id`/`agent_name`, not `data_dir`).
     The new tests need similar `data_dir`-exposing fixtures.
     Recommended approach: extract L5's local fixture into
     `tests/browser/conftest.py` as a reusable
     `app_with_data_dir` fixture, OR copy the local fixture
     into each new test file (matching L5's pattern). Either is
     acceptable; the conftest extraction is cleaner but expands
     conftest scope.
   - Seed two rows via a sync sqlite3 INSERT that **includes the
     connector-keying columns**. L5's `_seed_session_with_messages`
     INSERT (test file lines 160-168) only covers
     `(id, agent_name, title, messages, created_at, updated_at)`
     — extend the column list to include
     `platform, connector_account_id, channel_id, thread_id, peer_id,
     session_metadata, last_inbound_at`:
     ```sql
     INSERT INTO chat_sessions (
       id, agent_name, title, messages, created_at, updated_at,
       platform, connector_account_id, channel_id, thread_id, peer_id,
       session_metadata, last_inbound_at
     ) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'),
       ?, ?, ?, ?, ?, ?, ?)
     ```
     For the web-native row, pass `NULL` for all seven connector
     columns; for the connector-attached row, pass
     `("stub", "stub-acct-1", "C1", NULL, "P1", NULL, NULL)`.
   - `ChatSessionRepository.create` (the async aiosqlite path)
     is the *signature* reference for which columns to populate
     — the test uses sync sqlite3 because it executes against
     the spawned subprocess's DB file from outside the process.
   - Navigate to chat: `page.goto(f"{base_url}/#chat")` (verify
     the hash route at impl start).
   - Wait for the session list to render: `page.wait_for_selector('.session-list .list-item')`
     or similar.
   - Locate the connector-attached row by its session id:
     `connector_row = page.locator(f'.list-item:has(button[data-id="{connector_sid}"])')`.
   - Assert the badge:
     ```python
     badge = connector_row.locator('.session-item-source')
     expect(badge).to_have_count(1)
     expect(badge).to_have_text("stub")
     expect(badge).to_have_class(/session-item-source--stub/)
     ```
   - Locate the web-native row and assert NO `.session-item-source`
     element exists inside it.

2. **Operator-input visibility browser tests** — split into TWO
   parallel test files (or two test functions in the same file)
   for cleaner failure isolation:
   - `tests/browser/test_flow_chat_operator_input_visibility.py`
     (the connector-attached happy path)
   - The negative-control test (web-native session unchanged)
     can live in the same file as a second test function
     `test_operator_input_yields_no_operator_visibility_on_web_session`.

   **Test 1: connector-attached session**:
   - Same fixture shape as the source-badge test (the local
     `app_with_data_dir` pattern from L5, or the extracted
     conftest fixture).
   - Seed ONE connector-attached session row (same column-
     extension pattern as test 1 above; empty `messages`
     array — the test drives the first turn).
   - Boot the app; click the seeded session in the sidebar to
     join it (or navigate via hash route — see L5's pattern
     at line 215 for `page.goto(f"{base_url}#chat/sessions/{session_id}")`).
   - Wait for the session to be active.
   - Type a message and submit using the VERIFIED selectors
     from `tests/browser/test_flow_chat.py:33-34`:
     ```python
     page.locator('[data-testid="chat-input"]').fill("hello")
     page.locator('[data-testid="chat-send-btn"]').click()
     ```
   - Wait for the deterministic mock-provider reply — the
     existing mock provider returns the literal string
     `"Mock response from the mock provider."` per
     `test_flow_chat.py:44`. Assert on that exact text:
     ```python
     expect(page.locator('.msg.assistant', has_text="Mock response from the mock provider.")).to_be_visible(timeout=30_000)
     ```
   - **Refresh the page** to trigger the codec replay path
     (known L5 limitation: live broadcasts don't carry
     visibility; the storage-edge shim has tagged the persisted
     messages by this point). After reload, explicitly
     re-navigate to the session via hash route:
     `page.goto(f"{base_url}#chat/sessions/{session_id}")`.
   - Wait for the session's messages to render again.
   - Assertions (exactly one user + one assistant bubble after
     refresh):
     ```python
     user_bubble = page.locator('.msg.user').last
     expect(user_bubble).to_have_class(re.compile(r"\bmsg-operator-only\b"))
     expect(user_bubble.locator('.msg-operator-only-label')).to_have_text("[operator-only]")
     assistant_bubble = page.locator('.msg.assistant').last
     expect(assistant_bubble).to_have_class(re.compile(r"\bmsg-operator-only\b"))
     ```

   **Test 2: web-native session (negative control)**:
   - Same fixture; seed ONE web-native session row (all seven
     connector-keying columns `NULL`).
   - Drive the same typing flow + refresh + re-navigation.
   - Assertions:
     ```python
     user_bubble = page.locator('.msg.user').last
     # NOT(.) — assert the class is NOT present
     assert "msg-operator-only" not in (user_bubble.get_attribute("class") or "")
     ```
   - Mirror for the assistant bubble.

3. **Design-language audit** (written, in the flight log):
   - Open `flight-log.md` for F5.
   - Add a section `### Design Language Audit (Leg 7)`.
   - For each of the three surfaces (source badge, operator-
     only marker, operator-only label), record:
     - Selector
     - CSS rule contents (border, padding, font, color tokens)
     - M04/M06 fit assessment (PASS / NOTES with reasoning)
   - If any surface needs a small inline fix (e.g. a missing
     hover state, an incorrect token, an off-by-1 px), apply
     the fix in this leg AND note it in the audit. If the fix
     is too large (>~10 lines, or touches another module's
     conventions), document the deviation and escalate the
     decision to the HAT closer.
   - The audit is a methodology checkpoint, not a separate test.

4. **Full-suite + lint**:
   - `make rebuild` (mandatory: any CSS/JS fix during the audit
     must ship into the container).
   - `make test-browser` clean.
   - `make test-unit` clean (sanity check; should be unchanged).
   - `make lint` clean.

5. **Update flight log** with leg 7's outcomes:
   - The two new browser tests (names + count).
   - The design-language audit table.
   - Any inline fixes applied.
   - Any deviations or follow-on items raised for the HAT closer.

## Edge Cases

- **Flaky mock-agent reply timing**: the operator-input test
  depends on the mock agent producing a deterministic reply in
  bounded time. If the existing mock-agent setup is non-
  deterministic (e.g. random-delay simulation), the test should
  use a 30-second timeout AND assert specific deterministic
  reply text if available. Worst case: skip the assistant-reply
  assertion and only verify the user bubble's visibility after
  refresh.

- **Page refresh + WS reconnect race**: after `page.reload()`,
  the WS reconnects and re-fetches the session list. The test
  must wait for the new connection's `session_list` event
  before navigating into the seeded session. Pattern: poll for
  the session row to appear in the sidebar before clicking.

- **Mock agent's tool-using path**: the existing mock provider's
  reply (`"Mock response from the mock provider."` per
  `test_flow_chat.py:44`) is plain-text, no tool_calls — so the
  primary acceptance path is "exactly one user bubble + one
  assistant bubble after refresh, both carrying
  msg-operator-only." Tool-bubble interaction is not exercised
  by this test (the F4 e2e ws-into-connector test already
  covers tool-call visibility via the dispatcher path).

- **Source-badge negative-control (web-native row)**: ensure the
  seeded web-native row genuinely has `platform=None`. The
  default `ChatSession` constructor's defaults are `None`; no
  explicit kwarg needed. Verify via direct SQL query after seed
  if the test is suspicious of data-injection drift.

- **Design-language audit finds a deviation**: the leg's
  acceptance criterion allows escalation to a follow-on if the
  fix is too large. The HAT closer is the final gate; design-
  language deviations surfaced here should be either fixed
  inline OR explicitly noted for the operator's HAT review.

- **CSS specificity drift**: if a future flight touches
  `.msg.tool` or other bubble-level rules, the
  `.msg.msg-operator-only` rule's specificity may need
  revisiting. The audit notes the current specificity choice
  (`(0, 2, 0)` — two class selectors) and the rationale.

- **Pre-existing snapshot baselines**: per user-global rule,
  visual snapshot baselines are NOT committed. If `make test-pixel`
  is run during implementation, the regenerated baselines stay
  local. The new browser tests in this leg use DOM-shape
  assertions only — no snapshots.

## Files Affected

- `tests/browser/test_flow_chat_session_list_source_badge.py`
  (new) — source-badge browser E2E.
- `tests/browser/test_flow_chat_operator_input_visibility.py`
  (new) — operator-input write path browser E2E.
- `missions/10-bi-directional-comms-connectors/flights/05-.../flight-log.md`
  — appended Leg 7 entry + design-language audit table.
- (Conditional) `the_one/interfaces/web/static/css/chat.css` —
  ONLY if the design-language audit surfaces an inline fix.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make rebuild && make test-browser`, `make test-unit`, `make lint` clean)
- [ ] Update flight-log.md with Leg 7 progress entry AND the
      design-language audit table (with PASS/NOTES per surface).
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until
      end-of-flight review.

## Citation Audit

8 citations verified against current code at leg design time:

- `tests/browser/test_flow_chat_visibility_distinction.py` —
  L5's browser test (verified — exists).
- `tests/browser/conftest.py:112-188` — `app_clean` fixture
  (verified).
- `tests/browser/conftest.py:228-244` — `app_with_provider`,
  `app_with_agent` (verified at lines 228-244).
- `tests/browser/seeders.py` — `seed_mock_provider` /
  `seed_mock_agent` (verified — referenced from L5's browser test
  imports).
- `the_one/db/repositories.py:726-744` — `ChatSessionRepository.create`
  signature (verified — F3 L1 output).
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js`
  — L1 output: `.session-item-source` element conditionally
  rendered when `s.platform` is truthy (verified).
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`
  — L5 output: `msg-operator-only` class + label injection
  (verified).
- `the_one/interfaces/web/static/css/chat.css` — L1
  `.session-item-source` rule + L5
  `.area-chat .msg.msg-operator-only` + `.area-chat .msg-operator-only-label`
  rules (verified).
