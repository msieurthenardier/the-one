# Leg: ws-storage-edge-shim-for-operator-visibility

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Wire the WS-typed message path so that, on a connector-attached session,
the operator's `user_input` and all new non-USER messages appended by
`agent.step` are tagged `visibility=OPERATOR_VISIBILITY` before they
land in the database. Reuse the leg-3 helper for the post-step walk;
the USER message itself is overridden at the call site. Non-connector
(web-native) sessions remain byte-identical to today.

The agent loop is not modified — the shim sits in the WS handler's
`_process_and_broadcast`, around `agent.step` rather than inside it.

## Context

- **Flight slot**: F5 L4 — the operator-input write path. After this
  leg, an operator typing into a connector-attached session sees their
  message persisted with `visibility="operator"`, and the agent's
  responses stay operator-only by default. Successful
  `send_to_platform_channel` tool-call results inherit
  `visibility=None` (peer-visible) via the leg-3 helper's existing
  carve-out — no extra branch needed here.
- **Flight design decision — "Storage-edge shim for operator-visibility
  tagging"** (flight.md L64-68): the shim activates when
  `chat_session_row.platform IS NOT NULL`; captures `pre_step_len`
  before `agent.step`; after the step completes, calls
  `tag_post_step_visibility(agent.messages, pre_step_len)` then
  overrides the USER message at `agent.messages[pre_step_len]` to
  `OPERATOR_VISIBILITY`. The mission constraint "agent loop is not
  modified" is preserved by the two-line call-site override at the
  storage edge.
- **Flight design decision — "Per-session-lock unification..."**
  (flight.md L37-44): F5 L2 has landed the shared `session_locks`
  registry. The shim runs INSIDE `_spawn_message_processing`'s
  `async with session_locks[session.id]:` block — same lock identity
  as the dispatcher's path, so concurrent operator-typed +
  dispatcher-inbound on the same session can't race on
  `agent.messages`.
- **Architect-surfaced carve-out** (flight.md L155-158): a WS-typed
  operator message that triggers a platform-send tool call must
  produce a tool_result message with `visibility=None` (peers saw it);
  the surrounding assistant text + USER stay OPERATOR_VISIBILITY.
  This is the leg-3 helper's `is_successful_platform_send` branch
  applied to the WS path. The dedicated test for this case lands
  here.
- **Mission constraint**: agent loop in `the_one/agent/core.py` MUST
  NOT be modified. The shim mutates `agent.messages[i].visibility`
  by direct attribute write on a dataclass — that's metadata
  presentation, not a loop change.
- **F5 L1/L2/L3 carry-forward state**: list-sessions projection
  exposes `platform` to the client; lock + subscribers registry
  lives at `the_one.sessions`; `tag_post_step_visibility` helper
  lives at `the_one/connectors/visibility.py`.
- **Pause/resume on connector-attached sessions**: the flight's
  open question 7 (mission.md L88-89) settled the default: connector-
  driven sessions don't yet support pause/resume from the connector
  side; auth-required pauses are operator-resolved in the Chat UI.
  Resume-path tagging IS INCLUDED in this leg's scope: the same
  shim shape (snapshot `pre_resume_len`; call
  `tag_post_step_visibility` at the end) sits in
  `_resume_paused_session` at `the_one/interfaces/web/app.py:981`.
  Without it, the resumed assistant messages would persist with
  `visibility=None` and render as peer-visible in the Chat UI even
  though they never reached peers — a real UX defect. The resume
  path has no WS-typed USER message to override (the original USER
  was tagged in the initial-step shim); only the post-step rules
  apply on resume.
- **No schema change.** `Message.visibility` is on the dataclass
  (F3 L2); the codec persists it (F3 L2); `ChatSession.platform`
  exists on the model (F3 L1). Leg 4 sets the visibility at a new
  call site; no migrations.

## Inputs

- `the_one/interfaces/web/app.py:187-217` — `class Session`
  dataclass. After F5 L2, `processing_lock` and `subscribers` fields
  are gone; the dataclass carries `id, agent, created, source,
  title, agent_name, history`. **Missing**: the in-memory `Session`
  has no `platform` field today; the shim's connector-attached check
  needs that information at call time. THIS LEG ADDS `platform: str | None = None`
  to the `Session` dataclass.
- `the_one/interfaces/web/app.py:235` —
  `_spawn_message_processing(session, user_input, source, exclude_user_echo)`.
  Acquires `session_locks[session.id]`, sets the
  `current_chat_session_id` ContextVar, calls `_process_and_broadcast`.
  The shim mutates state BEFORE / AFTER the inner call, inside the
  lock, on the way to `_save_session_to_db`.
- `the_one/interfaces/web/app.py:790-978` —
  `_process_and_broadcast(session, user_input, source, exclude_user_echo)`.
  Runs the agent step, fans out events to WS subscribers, persists
  via `_save_session_to_db` at line 969. The shim sits HERE: capture
  `pre_step_len` BEFORE line 857 (`async for msg in session.agent.step(...)`);
  apply tagging AFTER the try/except for `agent.step` (between
  line 956's `except` block end and the `_save_session_to_db` call
  at line 968).
- `the_one/interfaces/web/app.py:315-351` — `_create_session`
  constructs a fresh `Session` for the WS-native path. The shim
  populates `Session.platform = None` here (the only path that
  creates a session WITHOUT a connector-attached row; dispatcher-
  driven sessions are persisted to the DB but DON'T flow through
  this function — they're created via `chat_repo.create(...)` in
  `connectors/_session.py`).
- `the_one/interfaces/web/app.py:354-455` — `_restore_session`
  rebuilds an in-memory `Session` from the DB row. `db_session` is
  the `ChatSessionModel` instance fetched by the repo at line 373;
  `db_session.platform` is the field we need to populate
  `Session.platform`. The shim wires this at the two `Session`-
  populating sites: lines 440-443 (in-place update of existing
  cached Session) and lines 446-453 (fresh `Session(...)`
  construction).
- `the_one/connectors/visibility.py` — `tag_post_step_visibility`
  helper (lands in F5 L3). The shim's only new external dependency.
- `the_one/connectors/__init__.py:52` — `OPERATOR_VISIBILITY`
  constant. The shim imports this from `the_one.connectors`.
- `tests/test_app_websocket_pause_resume.py` — F5 L2 already
  migrated three subscriber callsites; these tests stand intact.
  Test patterns here (`Session(...)` construction, stub agents)
  are the natural template for new WS-shim coverage.
- `tests/test_ws_responsiveness.py` — likewise, the `_make_session`
  helper at line 40 builds a `Session` instance; the new
  `Session.platform` field defaults `None` so existing tests are
  byte-identical without edits.
- `tests/test_connectors_visibility_helper.py` — leg-3's
  helper-isolation tests. The WS-shim regression net at leg 4 does
  NOT duplicate the helper's rules; the new tests pin the SHIM'S
  call-site contract (USER override, platform-attached gate, byte-
  identical non-connector path).
- `the_one/connectors/_inbound.py:193-218` — the dispatcher's shim
  precedent. Same shape (`pre_step_len` snapshot; post-step helper
  call) but no USER override (peer inbound is peer-visible by
  default). Leg-4's WS shim is the symmetric counterpart with the
  USER override flipped to OPERATOR_VISIBILITY.

## Outputs

- `the_one/interfaces/web/app.py` — modified:
  - `Session` dataclass gains `platform: str | None = None`.
  - `_create_session` is unchanged at the constructor call site —
    the dataclass default `None` is correct for web-native sessions;
    explicit kwarg would be visual noise.
  - `_restore_session` populates `session.platform` from
    `db_session.platform` at the two `Session`-populating sites
    (cached-update + fresh-construction branches).
  - `_process_and_broadcast` gains the storage-edge shim:
    1. Capture `pre_step_len = len(session.agent.messages)` BEFORE
       the `async for msg in session.agent.step(...)` loop at
       line 857.
    2. AFTER the try/except for `agent.step` completes — whether
       it succeeded or raised — and BEFORE `_save_session_to_db`
       at line 969: if `session.platform is not None`, call
       `tag_post_step_visibility(session.agent.messages, pre_step_len)`
       and then override the USER message:
       ```python
       if pre_step_len < len(session.agent.messages):
           session.agent.messages[pre_step_len].visibility = OPERATOR_VISIBILITY
       ```
       The bounds check guards the degenerate case where
       `agent.step` raised before its internal
       `Message.user(...)` append landed in `agent.messages` —
       defensive, expected to be unreachable in practice.
    3. The two new imports: `tag_post_step_visibility` from
       `the_one.connectors.visibility`; `OPERATOR_VISIBILITY` from
       `the_one.connectors`.
- New test file `tests/test_ws_storage_edge_shim_visibility.py`
  covering:
  - **`test_connector_attached_user_message_gets_operator_visibility`**:
    WS-typed message into a connector-attached session ends with
    `session.agent.messages[pre_step_len].visibility == OPERATOR_VISIBILITY`.
  - **`test_connector_attached_assistant_reply_gets_operator_visibility`**:
    same setup; the assistant reply at `pre_step_len + 1` has
    `visibility == OPERATOR_VISIBILITY`.
  - **`test_non_connector_session_unchanged`**: WS-typed message
    into a web-native (`session.platform is None`) session ends
    with the USER + assistant messages carrying `visibility=None`
    (the F3 codec contract: absent === platform-visible / no-tag).
    Regression net for the byte-identical claim.
  - **`test_pre_step_messages_untouched`**: seed
    `session.agent.messages` with prior history that has a sentinel
    visibility (e.g. `"sentinel"`); confirm after the turn the
    pre-step messages still have `visibility == "sentinel"`.
  - **`test_ws_typed_with_platform_send_tool_result_gets_none`**
    (the architect-surfaced carve-out): the operator types
    something; the agent calls `send_to_platform_channel` and the
    tool returns the success prefix; the tool_result message ends
    with `visibility=None` (peer-visible) while the surrounding
    assistant text + USER stay `OPERATOR_VISIBILITY`. Exercises the
    shared helper's `is_successful_platform_send` branch from the
    WS entry point.
  - **`test_pre_step_len_bounds_check_when_step_fails_pre_append`**:
    stub an `agent.step` that raises before yielding any messages;
    confirm the shim does not raise `IndexError` and the visibility
    state is unchanged.
  - **`test_resume_after_auth_tags_resumed_messages`**: build a
    connector-attached session whose agent has
    `_deferred_tool_calls` set; stub `resume_after_auth` to yield
    one assistant reply; call `_resume_paused_session(session)`;
    assert the appended messages have
    `visibility=OPERATOR_VISIBILITY`. Mirror of the initial-step
    test, on the resume seam.
- New test file (or extension of an existing connector e2e file)
  `tests/test_connectors_e2e_ws_into_connector.py` — end-to-end
  coverage: seed a connector-attached session in the DB via the
  existing dispatcher-helpers fixture, drive
  `_spawn_message_processing` with operator text, assert the
  persisted `chat_sessions.messages` blob carries the expected
  visibility tagging when decoded.
- `Session.platform` field default `None` means existing tests
  that construct `Session(...)` without it continue to pass byte-
  identically (verified at leg end).

## Acceptance Criteria

- [ ] `Session` dataclass at `the_one/interfaces/web/app.py:187`
      gains a single new field: `platform: str | None = None`. No
      other field changes.
- [ ] `_create_session` (line 315) is unchanged at the constructor
      call site — relies on the dataclass default `None`.
- [ ] `_restore_session` (line 354) populates `session.platform`
      from `db_session.platform` at BOTH `Session`-populating sites:
      the in-place update at lines 440-443 (after F5 L2) AND the
      fresh-construction at lines 446-453.
- [ ] `_process_and_broadcast` snapshots
      `pre_step_len = len(session.agent.messages)` BEFORE the
      `async for msg in session.agent.step(...)` loop.
- [ ] AFTER the try/except for `agent.step` completes and BEFORE
      `_save_session_to_db`, the shim runs (only when
      `session.platform is not None`):
      - Calls `tag_post_step_visibility(session.agent.messages, pre_step_len)`.
      - Overrides the USER message at `session.agent.messages[pre_step_len]`
        to `visibility = OPERATOR_VISIBILITY` (bounds-checked).
- [ ] WS-typed message into a connector-attached session: persisted
      `agent.messages[pre_step_len]` (USER) and all post-step
      non-USER messages carry `visibility=OPERATOR_VISIBILITY`,
      EXCEPT successful platform-send tool_result messages which
      carry `visibility=None` (the leg-3 helper's carve-out).
- [ ] WS-typed message into a web-native (non-connector) session
      produces messages with `visibility=None` (back-compat: F3
      codec absent-tag == peer-visible / no-tag). All existing
      non-connector tests pass byte-identically.
- [ ] All seven new unit-test cases enumerated under Outputs land in
      `tests/test_ws_storage_edge_shim_visibility.py` (or an
      equivalent file name — implementer's call as long as it's
      discoverable).
- [ ] An e2e test in
      `tests/test_connectors_e2e_ws_into_connector.py` (or
      extension of an existing connector-e2e file) covers the
      full DB round-trip: in-memory tagging → encode → DB row →
      decode → assertions.
- [ ] `make test-unit` clean. F5 L3 baseline was 1966 passed;
      expected ~+8 from this leg's seven unit tests + one e2e.
      Confirm the delta is the new tests, not unrelated breakage.
- [ ] `make lint` clean.
- [ ] No regression on F1/F2/F3/F4 or earlier F5 leg tests; the
      F5 L2 lock/subscribers tests at `test_ws_responsiveness.py`,
      `test_app_websocket_pause_resume.py`, `test_auto_load.py`
      remain byte-identical.
- [ ] The agent loop in `the_one/agent/core.py` is untouched.
- [ ] `_resume_paused_session` gains the symmetric shim:
      snapshot `pre_resume_len = len(session.agent.messages)` before
      the `async for msg in session.agent.resume_after_auth():` loop
      at line 1010; AFTER the try/except/finally completes and
      BEFORE `_save_session_to_db` at line 1033, if
      `session.platform is not None`, call
      `tag_post_step_visibility(session.agent.messages, pre_resume_len)`.
      No USER override on the resume path — there is no new WS-
      typed USER message.

## Verification Steps

- **WS-shim unit tests**:
  `docker exec the-one pytest tests/test_ws_storage_edge_shim_visibility.py -x --timeout 30 -v`
  — six new test cases pass.
- **E2E DB round-trip**:
  `docker exec the-one pytest tests/test_connectors_e2e_ws_into_connector.py -x --timeout 60 -v`
  — full encode/decode round-trip pins visibility.
- **F5 L2/L3 regression net**:
  `docker exec the-one pytest tests/test_ws_responsiveness.py tests/test_app_websocket_pause_resume.py tests/test_auto_load.py tests/test_connectors_visibility_helper.py -x --timeout 30 -v`
  — F5 L2 lock + subscribers tests + F5 L3 helper tests stay green.
- **Dispatcher / e2e session / platform-send regression**:
  `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py -x --timeout 60 -v`
  — F1-F4 connector subsystem unchanged.
- **Full unit-suite regression**: `make test-unit` clean.
- **Lint**: `make lint` clean.
- **Import-direction grep**: `grep -rn "from the_one.connectors.visibility"
  the_one/` (production code only) — after this leg, exactly TWO
  consumers in production: `the_one/connectors/_inbound.py` (F5 L3)
  and `the_one/interfaces/web/app.py` (this leg). Test files may
  add additional matches; that's fine.

## Implementation Guidance

The shim is small and additive. Recommended order:

1. **Add the `platform` field to `Session`** (`the_one/interfaces/web/app.py`):
   - In the `@dataclass` block at line 187, add at the end of the
     field declarations (after `processing_lock` was removed in F5
     L2; the current dataclass ends with `agent_name`, `history`):
     ```python
     # M10 F05 L04: connector-attached sessions carry the platform
     # string ("stub", "discord", "slack", …) populated from
     # ChatSession.platform at restore time. Web-native sessions
     # carry None. The storage-edge shim in _process_and_broadcast
     # reads this field to gate operator-visibility tagging.
     platform: str | None = None
     ```
   - Run `make lint`; green. Run `make test-unit`; green
     (default `None` keeps all existing constructors byte-
     identical).

2. **Populate `Session.platform` at restore time**
   (`_restore_session`, lines 354-455):
   - In the cached-update branch at lines 440-443, after
     `existing.agent_name = db_session.agent_name`, add:
     ```python
     existing.platform = db_session.platform
     ```
   - In the fresh-construction branch at lines 446-453, add the
     `platform=db_session.platform` kwarg to the `Session(...)`
     constructor call.

3. **`_create_session` requires no kwarg change**:
   - The `Session(...)` constructor call at line 327 currently
     omits `title`, `processing_lock`, etc. — relying on field
     defaults. Adding an explicit `platform=None` would be visual
     noise: the field's docstring comment (added in step 1) already
     documents the intent. The implementer should leave
     `_create_session`'s constructor call untouched; the new
     `platform` field defaults to `None` for the WS-native code
     path, which is correct.

4. **Add the shim to `_process_and_broadcast`**
   (`the_one/interfaces/web/app.py:790-978`):
   - Add the imports at the top of the file (find the existing
     `from the_one.connectors import …` block):
     ```python
     from the_one.connectors import OPERATOR_VISIBILITY
     from the_one.connectors.visibility import tag_post_step_visibility
     ```
   - Inside `_process_and_broadcast`, immediately BEFORE the
     `try:` at line 856 (which wraps the `async for msg in
     session.agent.step(...)` loop), capture the snapshot:
     ```python
     # F5 L4: storage-edge shim for operator-visibility tagging.
     # On a connector-attached session, every WS-typed message is
     # operator-only by default. The agent's responses to that
     # message (and any intermediate tool calls/results) stay in
     # operator-console-only mode UNLESS the agent explicitly
     # invokes send_to_platform_channel — that tool's successful
     # tool_result is the only path to visibility=None / peer-
     # visible from this WS write path.
     pre_step_len = len(session.agent.messages)
     ```
   - AFTER the try/except for `agent.step` (line 956), and BEFORE
     `_save_session_to_db` at line 968, add:
     ```python
     # F5 L4: apply visibility tagging if this is a connector-
     # attached session. Runs whether agent.step succeeded or
     # raised — partial messages still need tagging because
     # _save_session_to_db persists whatever is in agent.messages.
     if session.platform is not None:
         tag_post_step_visibility(session.agent.messages, pre_step_len)
         # The helper SKIPS USER messages; override the WS-typed
         # operator input at pre_step_len explicitly. Bounds-checked
         # in case agent.step raised before its internal
         # Message.user(...) append landed.
         if pre_step_len < len(session.agent.messages):
             session.agent.messages[pre_step_len].visibility = OPERATOR_VISIBILITY
     ```
   - Run a focused regression: `pytest tests/test_ws_responsiveness.py
     tests/test_app_websocket_pause_resume.py -x --timeout 30 -v`;
     green (no behavior change for non-connector sessions).

4b. **Add the symmetric shim to `_resume_paused_session`**
    (`the_one/interfaces/web/app.py:981`):
    - Immediately before the `try:` at line 1008, snapshot:
      ```python
      # F5 L4: capture pre-resume length so we can tag any
      # messages appended during resume_after_auth on a connector-
      # attached session. Mirrors the shim in
      # _process_and_broadcast — same helper, no USER override
      # (resume has no new WS-typed USER message).
      pre_resume_len = len(session.agent.messages)
      ```
    - AFTER the `finally:` block at line 1029 (which resets the
      ContextVar) and BEFORE `_save_session_to_db` at line 1033,
      add:
      ```python
      if session.platform is not None:
          tag_post_step_visibility(session.agent.messages, pre_resume_len)
      ```
    - Imports added in step 4 are already in scope.

5. **Add the WS-shim unit tests**
   (`tests/test_ws_storage_edge_shim_visibility.py`):
   - Pattern: use the stub-agent approach from
     `tests/test_app_websocket_pause_resume.py` to drive
     `_process_and_broadcast` without spinning up the full app.
     The fake agent's `step` yields scripted `Message` instances.
   - Each test:
     1. Build a `Session` with `platform="stub"` (or `None` for
        the byte-identical case).
     2. Pre-seed `session.agent.messages` with a system message
        + any pre-step history.
     3. Capture `pre_step_len` at test fixture level.
     4. Drive `_process_and_broadcast(session, user_input, source="web", exclude_user_echo=None)`.
     5. Assert the post-call `session.agent.messages[…].visibility`
        for the relevant indices.
   - For `test_ws_typed_with_platform_send_tool_result_gets_none`:
     the stub agent yields an ASSISTANT message with a `tool_call`
     whose name is `"send_to_platform_channel"`, then a TOOL
     message whose content starts with `PLATFORM_SEND_OK_PREFIX`
     (importable from `the_one.connectors`). Mirrors the F4 L4
     ground-truth tests at
     `tests/test_connectors_inbound.py:625-700` for the dispatcher
     side; same shape on the WS side.
   - For `test_pre_step_len_bounds_check_when_step_fails_pre_append`:
     the stub agent's `step` raises immediately without yielding
     and without appending any message (matches the
     `agent/core.py` invariant — verify against actual code that
     the first `Message.user(...)` append happens INSIDE a try and
     could be skipped if an early exception fires). The shim's
     bounds check `pre_step_len < len(session.agent.messages)`
     prevents `IndexError`. (NOTE: if `agent.step` ALWAYS appends
     before raising, this test simply pins the bounds check as
     defensive code. Either way, no failure.)

6. **Add the e2e DB round-trip test**
   (`tests/test_connectors_e2e_ws_into_connector.py`):
   - Pattern: borrow from `tests/test_connectors_e2e_session.py`
     for fixture shape; that file already exercises the
     dispatcher's full round-trip. The WS variant uses the same
     DB fixture but drives `_spawn_message_processing` instead of
     `dispatch_inbound`.
   - Seed a connector-attached `chat_sessions` row via
     `chat_repo.create(...)` with `platform="stub"` and the
     other connector-keying fields.
   - Drive `_get_or_restore_session(session_id)` → assert
     `session.platform == "stub"`.
   - Drive `_spawn_message_processing(session, "hello", "web", None)`
     with a stub agent that yields a simple assistant reply.
   - After the call, re-fetch the session from the DB; decode the
     messages; assert the USER message has `visibility="operator"`
     and the assistant reply has `visibility="operator"`.
   - Confirm the registry-level cleanup fixtures (the F5 L2
     autouse `_clear_pool_locks_registry` mechanism — extended
     to call `the_one.sessions.clear_for_test()`) handle this
     test correctly. Mirror the autouse pattern from the other
     connector-e2e files.

7. **Full-suite + lint**:
   - `make test-unit` clean.
   - `make lint` clean.
   - Import-direction grep: three consumers of
     `the_one.connectors.visibility`.

8. **Update flight log** with leg 4's outcomes — files touched,
   tests added, any deviations.

## Edge Cases

- **`session.platform is None` (web-native session)**: shim is a
  no-op. All existing non-connector test paths (the bulk of
  `test_ws_responsiveness.py`, `test_app_websocket_pause_resume.py`,
  `test_auto_load.py`) remain byte-identical. THE REGRESSION NET.

- **`agent.step` raises mid-turn**: the try/except at lines 856-965
  catches and broadcasts a system error. The partial
  `agent.messages` state is still persisted by `_save_session_to_db`
  at line 969. The shim sits between the except block end and the
  save — it should tag whatever made it into `agent.messages`. For
  the bounds check at the USER override, if no USER got appended,
  `pre_step_len == len(agent.messages)` and the override is
  skipped.

- **`agent.step` pauses on `MCPAuthRequired`**: the pause path
  appends messages (assistant + tool-call-with-deferred-result)
  before yielding `auth_required`. The initial shim tags those
  messages when the step exits normally (the iterator exhausts on
  pause). When `_resume_paused_session` later runs and appends
  MORE messages, the symmetric resume-shim (step 4b in
  Implementation Guidance) tags them. Combined, both seams keep
  the operator-only invariant continuous across the auth round-
  trip on a connector-attached session.

- **`Session.platform` ≠ DB row's `platform`**: theoretically the
  in-memory cached field could drift from the DB if a row's
  `platform` is mutated outside the WS flow (e.g. a future flight
  edits connector-keying fields in place). Today no such mutation
  exists. Mitigation: `_restore_session` re-reads `db_session`
  from the repo on every join, so a drifted cached `Session` is
  refreshed at the next join. Acceptable for F5.

- **Concurrent WS-typed + dispatcher-inbound on the same session**:
  F5 L2's shared lock registry serializes them; only one is inside
  `agent.step` at a time. The shim tags whatever happened in
  THIS turn (its `pre_step_len` window). The other path's tagging
  is independent.

- **`_create_session` from a dispatcher-driven row**: doesn't
  happen — `_create_session` is the WS-native code path only.
  Dispatcher-created `chat_sessions` rows are first surfaced to
  the WS via `_restore_session` (an operator's join action), at
  which point `Session.platform` is populated from `db_session.platform`.

- **The first turn after restore on a connector-attached session
  where the dispatcher recently appended messages**: the
  dispatcher already tagged its appended messages; the new WS
  shim only touches the post-step window from this turn forward.
  No double-tagging.

- **`agent.step` consumes an empty `user_input`**: not a runtime
  concern (the WS handler filters empty input at line 1327 before
  calling `_spawn_message_processing`); defensive bounds check
  still safe.

## Files Affected

- `the_one/interfaces/web/app.py` — three modifications: `Session`
  dataclass gains `platform` field; `_restore_session` populates
  `session.platform` from `db_session.platform` at two sites;
  `_process_and_broadcast` gains the storage-edge shim (snapshot +
  post-step tagging); two new imports.
- `tests/test_ws_storage_edge_shim_visibility.py` (new) — six new
  unit tests for the shim.
- `tests/test_connectors_e2e_ws_into_connector.py` (new) — one
  e2e DB round-trip test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit`, `make lint` clean)
- [ ] Import-direction grep confirms three consumers of
      `the_one.connectors.visibility`.
- [ ] Update flight-log.md with Leg 4 progress entry.
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until
      end-of-flight review.

## Citation Audit

12 citations verified against current code at leg design time:

- `the_one/interfaces/web/app.py:187-217` — `class Session`
  dataclass (verified post-F5 L2; `processing_lock` /
  `subscribers` fields are gone).
- `the_one/interfaces/web/app.py:235` —
  `_spawn_message_processing` (verified).
- `the_one/interfaces/web/app.py:315` — `_create_session`
  (verified).
- `the_one/interfaces/web/app.py:354` — `_restore_session`
  (verified).
- `the_one/interfaces/web/app.py:440-443` — cached-update branch
  of `_restore_session` (verified — `existing.title`,
  `existing.agent_name`, `existing.history` assignments).
- `the_one/interfaces/web/app.py:446-453` — fresh-construction
  branch of `_restore_session` (verified).
- `the_one/interfaces/web/app.py:790` — `_process_and_broadcast`
  (verified).
- `the_one/interfaces/web/app.py:856` — `try:` wrapping the
  agent.step loop (verified).
- `the_one/interfaces/web/app.py:857` —
  `async for msg in session.agent.step(...)` (verified).
- `the_one/interfaces/web/app.py:956` — `except Exception as exc:`
  (verified).
- `the_one/interfaces/web/app.py:968-969` — `_save_session_to_db`
  call (verified).
- `the_one/connectors/__init__.py:52` — `OPERATOR_VISIBILITY`
  (verified).
- `the_one/connectors/visibility.py` — `tag_post_step_visibility`
  (verified — leg-3 output).
- `the_one/connectors/_inbound.py:193-218` — dispatcher precedent
  for `pre_step_len` shape (verified — F5 L3 reduced the post-step
  block to a single helper call).
