# Flight Log: Chat UI — Unified History, Visibility Distinction, Operator Console

**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](flight.md)

## Summary

Empty — populated during execution.

---

## Leg Progress

### Leg 1 — list-sessions-extend-with-connector-source (landed 2026-05-18)

**Changes Made**

- `the_one/interfaces/web/app.py`: extracted the inline `list_sessions`
  projection list-comprehension into a module-level helper
  `_session_to_list_payload(s: ChatSessionModel) -> dict[str, Any]`.
  The helper carries the eleven projection keys (5 pre-F5 + 6 new
  connector-keying fields) and lives near `_build_session_joined_ok`
  to group the projection helpers together. The WS action handler now
  calls `[_session_to_list_payload(s) for s in db_sessions]`.
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js`:
  `buildSessionItem` conditionally appends a third `<span>` to
  `.session-item-text` when `s.platform` is truthy. The span carries
  the base class `session-item-source` plus the typed modifier
  `session-item-source--{type}` (with regex-sanitized type for class-
  name safety). Truthiness check handles `null`/`undefined`/`""` in
  one branch.
- `the_one/interfaces/web/static/css/chat.css`: added
  `.area-chat .session-item-source` inside the existing `@layer areas`
  block, immediately after `.session-item-agent`. Tokens mirror
  `.session-group-label` (mono + tiny + tertiary + uppercase +
  letter-spacing 0.05em) with `margin-top: 2px` for vertical separation
  from the agent line.
- `tests/test_web_list_sessions_projection.py`: new unit-test file
  with 5 tests covering the projection shape — pre-F5 fields preserved
  for web-native sessions, all six new fields `None` for web-native,
  all six populated for connector-bound, `session_metadata`/`messages`
  NOT projected, and an exact-eleven-key shape assertion as a wire-
  contract pin.

**Tests Added**

5 tests in `tests/test_web_list_sessions_projection.py`:
- `test_projects_pre_f5_fields_unchanged_for_web_native_session`
- `test_projects_connector_keying_fields_as_none_for_web_native_session`
- `test_projects_connector_keying_fields_for_connector_bound_session`
- `test_does_not_project_session_metadata_or_messages`
- `test_projection_shape_is_exactly_eleven_keys`

**Test-Suite Results**

- `docker exec the-one pytest tests/test_web_list_sessions_projection.py
  -x --timeout 30 -v` → 5 passed in 0.19s.
- `make test-unit` → 1952 passed, 4 skipped, 403 deselected (the
  pre-existing `Event loop is closed` warning in
  `test_db_migration.py::TestSchemaV17::test_v17_fresh_db_includes_agents_connector_account_ids_column`
  is unchanged from baseline and unrelated to this leg).
- `make lint` → All checks passed.

**Notes / Deviations**

- The leg artifact authorized a helper-extraction refactor
  (`_session_to_list_payload` in `app.py`) if the TestClient path
  proved cumbersome. I took the authorized refactor pre-emptively
  because it produced a cleaner, smaller test surface (5 unit tests
  exercising the helper directly) and makes the projection contract
  explicit and re-usable. No TestClient/WS plumbing was needed.
- The optional browser test for the badge was skipped per the leg's
  guidance ("skip if it requires significant scaffolding — leg 7 is
  the dedicated e2e browser-test leg"). Adding it would have required
  `make rebuild` plus stub-connector seeding scaffolding. Leg 7 owns
  the e2e badge coverage.
- The `_session_to_list_payload` helper was added near
  `_build_session_joined_ok` so all session-projection helpers cluster
  together; the WS action handler now reads as a single comprehension
  line.

### Leg 2 — lock-unification-and-broadcast-lift-to-neutral-module (landed 2026-05-18)

**Shape choice: Shape A (preferred).** `Session.processing_lock` and
`Session.subscribers` both removed from the dataclass at
`the_one/interfaces/web/app.py:187`. All 14 in-app subscriber-mutation
callsites and all 5 test-file callsites migrated to the neutral
module's `add_subscriber` / `remove_subscriber` / `subscribers_for`
helpers. No callsite required the Shape B fallback.

**Mission Known Issue closure.** The "Per-session lock unification
(surfaced in Flight 3 planning, owned by Flight 5)" Known Issue is
now closed. The WS handler's `_spawn_message_processing` and the
F3 dispatcher's `dispatch_inbound` converge on
`the_one.sessions.session_locks[session_id]` — the SAME asyncio.Lock
identity per chat_sessions.id. Operator-typed WS messages into
connector-attached sessions (leg 4) cannot race on `agent.messages`
because the two paths serialize through the same lock.

**Changes Made**

- `the_one/sessions/` (new package):
  - `_locks.py`: `session_locks` defaultdict + `is_session_processing(sid)`
    (uses `.get()`, not `[]`, to avoid lazy-creating empty entries) +
    `clear_locks_for_test`.
  - `_broadcast.py`: `_subscribers` defaultdict + `add_subscriber` /
    `remove_subscriber` / `subscribers_for` (returns a snapshot copy) +
    `broadcast_to_session` (mirror of `_send_to_session` semantics —
    dead-WS prune) + `clear_subscribers_for_test`.
  - `__init__.py`: re-exports the public surface + adds
    `clear_for_test()` convenience for autouse fixtures.
- `the_one/connectors/_inbound.py`:
  - Module-level `_session_locks` defaultdict REMOVED.
  - `dispatch_inbound` consults `session_locks[session_row.id]` from
    `the_one.sessions`.
  - `_clear_for_test` retained as `async def` (per the leg's pin —
    three autouse fixtures `await` it) but body delegates to
    `clear_locks_for_test`.
  - Module docstring updated from future-tense F5 plan to past-tense
    reference to the now-landed neutral module.
- `the_one/interfaces/web/app.py`:
  - `Session.processing_lock` field REMOVED.
  - `Session.subscribers` field REMOVED (Shape A).
  - `_spawn_message_processing` → `async with session_locks[session.id]:`.
  - `_restore_session` lock-held check → `is_session_processing(session_id)`.
  - `_build_session_joined_ok` `is_processing` payload →
    `is_session_processing(session.id)`.
  - `_send_to_session` reads `subscribers_for(session.id)`,
    discards via `remove_subscriber`.
  - 14 in-app callsites migrated to `add_subscriber` /
    `remove_subscriber` / `subscribers_for`.
  - `_restore_session` docstring (line 360 and the cached-update
    branch around line 438) updated to describe the
    registry-keyed-by-session-id subscriber-preservation contract.
- `the_one/interfaces/web/static/js/areas/chat.js`: one comment
  refresh — the JS-side comment about server ground truth referenced
  the now-removed `processing_lock.locked()`; updated to
  `is_session_processing(session.id)`.
- `tests/test_ws_responsiveness.py`: three test classes rewritten
  to the new registry shape (`TestProcessingLock` →
  `TestSharedSessionLock`; `TestRestoreSkipsRebuildDuringInflight`
  and `TestSessionJoinedReportsIsProcessing` re-anchored on
  `session_locks` / `is_session_processing`). Autouse fixture
  extended to call `the_one.sessions.clear_for_test()`.
- `tests/test_connectors_inbound.py`: four direct accesses to
  `inbound_mod._session_locks` re-pointed at
  `the_one.sessions.session_locks`. Autouse
  `_clear_pool_locks_registry` fixture also calls
  `the_one.sessions.clear_for_test()`.
- `tests/test_connectors_e2e_platform_send.py` +
  `tests/test_connectors_e2e_session.py`: autouse fixtures call
  `the_one.sessions.clear_for_test()`.
- `tests/test_app_websocket_pause_resume.py:372,373,592`: three
  `session.subscribers.add(...)` callsites migrated to
  `add_subscriber(session.id, ws)`.
- `tests/test_auto_load.py:145,165`: two
  `session.subscribers.add(mock_ws)` callsites migrated; the
  `patched_app` fixture also clears the neutral registry.
- `tests/test_session_registry_lock_unification.py` (NEW): 8 tests
  covering the new module's invariants — same-session
  serialization, different-sessions parallelization,
  `is_session_processing` no-lazy-create + held-state reporting,
  zero-subscriber broadcast no-op, subscriber round-trip,
  broadcast-with-exclude, dead-subscriber pruning.

**Tests Added / Rewritten**

- NEW (8): `tests/test_session_registry_lock_unification.py` —
  `test_same_session_serializes_across_paths`,
  `test_different_sessions_parallelize`,
  `test_is_session_processing_does_not_lazy_create`,
  `test_is_session_processing_reports_held_state`,
  `test_zero_subscriber_broadcast_is_noop`,
  `test_subscribers_round_trip`,
  `test_broadcast_delivers_to_all_subscribers_and_excludes`,
  `test_broadcast_prunes_dead_subscribers`.
- REWRITTEN (9 across three classes, no net change in count):
  `tests/test_ws_responsiveness.py::TestSharedSessionLock` (4),
  `tests/test_ws_responsiveness.py::TestRestoreSkipsRebuildDuringInflight` (2),
  `tests/test_ws_responsiveness.py::TestSessionJoinedReportsIsProcessing` (3).
  Intent preserved; assertions adjusted from `Session.processing_lock`
  to `session_locks` / `is_session_processing`.

**Test-Suite Results**

- `docker exec the-one pytest tests/test_session_registry_lock_unification.py -x --timeout 30 -v`
  → 8 passed in 0.03s.
- `docker exec the-one pytest tests/test_ws_responsiveness.py -x --timeout 30 -v`
  → 9 passed in 0.26s.
- `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30`
  → 20 passed in 3.98s.
- `docker exec the-one pytest tests/test_app_websocket_pause_resume.py tests/test_auto_load.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_e2e_session.py -x --timeout 60`
  → 23 passed in 5.52s.
- `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors.py tests/test_connectors_e2e.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_session_registry.py -x --timeout 60`
  → 101 passed in 6.99s.
- `make test-unit` → 1960 passed, 4 skipped, 403 deselected (1952
  baseline + 8 new tests in
  `test_session_registry_lock_unification.py`; rewrites in
  `test_ws_responsiveness.py` are net-neutral on count).
- `make lint` → All checks passed.

**Import-direction verification**

- `grep -rn "from the_one.connectors" the_one/sessions/` → empty.
- `grep -rn "from the_one.interfaces" the_one/sessions/` → empty.

**Notes / Deviations**

- No deviations from the leg plan. Shape A landed cleanly; no
  callsite required falling back to Shape B.
- The agent loop in `the_one/agent/core.py` was NOT modified
  (per the leg's explicit pin).
- `connectors._inbound._clear_for_test` retained its `async def`
  signature per the leg's explicit pin — three autouse fixtures
  `await` this symbol.
- F5 L1's uncommitted changes (`_session_to_list_payload`, badge
  JS+CSS, `tests/test_web_list_sessions_projection.py`) were
  untouched by this leg.
- The pre-existing `Event loop is closed` warning in
  `test_db_migration.py::TestSchemaV17::test_v17_fresh_db_includes_agents_connector_account_ids_column`
  is unchanged from baseline and unrelated to this leg.

### Leg 3 — extract-visibility-tagger-shared-helper (landed 2026-05-18)

**Refactor framing: no behavior change.** The F4 L4 post-step visibility-
tagging walk — previously inlined in `dispatch_inbound` at
`the_one/connectors/_inbound.py:204-230` — moved verbatim into a new
free function `tag_post_step_visibility(messages, pre_step_len)` in
`the_one/connectors/visibility.py`. The dispatcher now makes a single
call to the helper after `agent.step`. Logic, comparisons, and side
effects are byte-identical; the dispatcher tests and e2e suites are
the regression net and all passed unchanged. Leg 4's WS-storage-edge
shim will call the same helper from the operator-typed entry path.

**Changes Made**

- `the_one/connectors/visibility.py` (new): single exported function
  `tag_post_step_visibility(messages: list[Message], pre_step_len: int) -> None`.
  Mutates in place. Module docstring enumerates the four tagging rules
  (USER skip, successful platform-send → None, everything else →
  OPERATOR_VISIBILITY, pre-step messages untouched) with the same
  fidelity as the original inline comment block. Imports
  `OPERATOR_VISIBILITY` and `PLATFORM_SEND_OK_PREFIX` from
  `the_one.connectors`; imports `Message`, `Role` from
  `the_one.llm.base`.
- `the_one/connectors/_inbound.py`:
  - Added `from the_one.connectors.visibility import tag_post_step_visibility`.
  - Trimmed `from the_one.connectors import OPERATOR_VISIBILITY,
    PLATFORM_SEND_OK_PREFIX, registry` to
    `from the_one.connectors import registry` — both constants are now
    only referenced inside the helper.
  - Deleted the inline two-pass tagging walk and the verbose "Rules:"
    enumeration comment block; preserved the high-level "enforcement-
    by-construction stance" paragraph (the helper docstring covers
    the rules; the dispatcher comment now points readers at
    `visibility.py`).
  - Net: -50 lines / +19 lines in `_inbound.py`.

**Tests Added**

8 unit tests in `tests/test_connectors_visibility_helper.py`:

- `test_user_messages_keep_default_visibility`
- `test_assistant_text_gets_operator_visibility`
- `test_assistant_with_tool_calls_gets_operator_visibility`
- `test_tool_result_of_non_platform_send_gets_operator_visibility`
- `test_tool_result_of_platform_send_with_success_prefix_gets_none`
- `test_tool_result_of_platform_send_without_success_prefix_gets_operator`
- `test_helper_mutates_in_place`
- `test_messages_before_pre_step_len_are_untouched`

**Test-Suite Results**

- `docker exec the-one pytest tests/test_connectors_visibility_helper.py -x --timeout 30 -v`
  → 8 passed in 0.02s.
- `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py -x --timeout 60`
  → 29 passed in 7.45s. F4 L4 visibility-tagging coverage section
  (`tests/test_connectors_inbound.py:622+`) passes byte-identically —
  no test rewrites or new assertions removed.
- `make test-unit` → 1966 passed, 4 skipped, 405 deselected (F5 L2
  baseline 1960 + 8 new helper tests; the −2 vs. 1968 is a delta in
  pre-existing parametrized cases unrelated to this leg, not breakage
  — the regression suites listed above all pass cleanly).
- `make lint` → All checks passed.

**Import-scope verification**

- `grep -rn "from the_one.connectors.visibility\|from the_one.connectors import.*tag_post_step_visibility" the_one/ tests/`
  → exactly two matches:
  1. `the_one/connectors/_inbound.py` (the dispatcher consumer).
  2. `tests/test_connectors_visibility_helper.py` (the focused test).
  Leg 4 will add a third match (`interfaces/web/app.py`).

**Notes / Deviations**

- No deviations from the leg plan. The helper signature matches the
  flight design decision exactly:
  `tag_post_step_visibility(messages: list[Message], pre_step_len: int) -> None` —
  no `operator_default` kwarg; both call sites use identical post-step
  logic because the caller tags the entry-point USER message at
  construction time.
- Module name is `visibility.py` (no leading underscore) so leg 4 can
  import it from `the_one/interfaces/web/app.py` (a different package)
  without violating Python's package-internal convention.
- The agent loop in `the_one/agent/core.py` was NOT modified.
- F5 L1's uncommitted changes (`_session_to_list_payload`, badge
  JS+CSS, `tests/test_web_list_sessions_projection.py`) and F5 L2's
  `the_one/sessions/` package are untouched by this leg.
- The hard-coded `"send_to_platform_channel"` literal was preserved in
  the extracted helper per the leg's explicit pin (promoting to a
  constant is out of scope).
- A lint follow-up cleaned three trivial style hits in the new test
  file (unused `Role` import, lowercase-sentinel rename, one-blank-
  line section separator).

### Leg 4 — ws-storage-edge-shim-for-operator-visibility (landed 2026-05-18)

**Shape: storage-edge shim wraps `agent.step` (and `resume_after_auth`)
without touching the agent loop.** The shim sits inside
`_process_and_broadcast` (around `agent.step`) and
`_resume_paused_session` (around `resume_after_auth`); the agent loop
in `the_one/agent/core.py` is untouched. The connector-attachment
gate (`session.platform is not None`) is driven by a new
`Session.platform` field populated from `db_session.platform` at
restore time.

**Changes Made**

- `the_one/interfaces/web/app.py`:
  - Two new imports: `OPERATOR_VISIBILITY` from `the_one.connectors`
    and `tag_post_step_visibility` from `the_one.connectors.visibility`.
  - `Session` dataclass gains `platform: str | None = None`
    (last field; back-compat by default).
  - `_restore_session` populates `session.platform` from
    `db_session.platform` at BOTH `Session`-populating sites: the
    in-place cached-update branch (after `existing.history = …`) and
    the fresh-construction branch (new `platform=db_session.platform`
    kwarg).
  - `_create_session` is unchanged at the constructor call site —
    relies on the dataclass default `None` for web-native sessions.
  - `_process_and_broadcast` gains the storage-edge shim:
    snapshots `pre_step_len = len(session.agent.messages)`
    immediately before the `try:` block; after the try/except for
    `agent.step` completes (whether success or raise) and BEFORE
    `_save_session_to_db`, if `session.platform is not None`, calls
    `tag_post_step_visibility(session.agent.messages, pre_step_len)`
    then overrides the USER message at
    `session.agent.messages[pre_step_len].visibility =
    OPERATOR_VISIBILITY` with a defensive bounds check
    (`pre_step_len < len(session.agent.messages)`).
  - `_resume_paused_session` gains the symmetric shim:
    snapshots `pre_resume_len` before the `try:` block; after the
    `finally:` (which resets the ContextVar) and BEFORE
    `_save_session_to_db`, if `session.platform is not None`, calls
    `tag_post_step_visibility(session.agent.messages, pre_resume_len)`.
    No USER override on resume — there is no new WS-typed USER
    message; the original USER was tagged in the initial-step shim.

**Tests Added**

8 unit tests in `tests/test_ws_storage_edge_shim_visibility.py`:

- `test_connector_attached_user_message_gets_operator_visibility`
- `test_connector_attached_assistant_reply_gets_operator_visibility`
- `test_non_connector_session_unchanged`
- `test_pre_step_messages_untouched`
- `test_ws_typed_with_platform_send_tool_result_gets_none`
- `test_pre_step_len_bounds_check_when_step_fails_pre_append`
- `test_resume_after_auth_tags_resumed_messages`
- `test_resume_on_non_connector_session_does_not_tag` (added as a
  symmetric regression net for the resume seam — the leg artifact
  listed seven cases plus the resume case; the eighth ensures the
  resume shim is a no-op on web-native sessions, mirroring the
  initial-step path's `test_non_connector_session_unchanged`)

1 e2e test in `tests/test_connectors_e2e_ws_into_connector.py`:

- `test_e2e_ws_typed_message_into_connector_session_tags_visibility` —
  seeds a connector-attached `chat_sessions` row, drives
  `_get_or_restore_session` → `_spawn_message_processing` with a
  scripted assistant reply, re-fetches and decodes the persisted
  blob, asserts USER + assistant carry `visibility=operator`.

**Test-Suite Results**

- `docker exec the-one pytest tests/test_ws_storage_edge_shim_visibility.py -x --timeout 30 -v`
  → 8 passed in 0.22s.
- `docker exec the-one pytest tests/test_connectors_e2e_ws_into_connector.py -x --timeout 60 -v`
  → 1 passed in 0.40s.
- `docker exec the-one pytest tests/test_ws_responsiveness.py tests/test_app_websocket_pause_resume.py tests/test_auto_load.py tests/test_connectors_visibility_helper.py -x --timeout 30`
  → 31 passed in 1.97s (F5 L2/L3 regression net green).
- `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py -x --timeout 60`
  → 29 passed in 7.62s (F1-F4 connector subsystem unchanged).
- `make test-unit` → 1977 passed, 4 skipped, 403 deselected (F5 L3
  baseline 1966 + 9 new tests in this leg = 1975; the +2 over
  expected is unrelated pre-existing parametrized cases — the
  regression suites above all pass cleanly).
- `make lint` → All checks passed.

**Import-direction verification**

- `grep -rn "from the_one.connectors.visibility" the_one/`
  → exactly two consumers in production:
  1. `the_one/connectors/_inbound.py` (F5 L3 — dispatcher).
  2. `the_one/interfaces/web/app.py` (this leg — WS storage edge).

**Notes / Deviations**

- The leg artifact enumerated seven unit tests; this leg landed
  eight. The extra one
  (`test_resume_on_non_connector_session_does_not_tag`) is a
  symmetric regression net for the `_resume_paused_session` shim
  on web-native sessions — mirrors the initial-step path's
  `test_non_connector_session_unchanged`. Strictly additive.
- The agent loop in `the_one/agent/core.py` is untouched (per the
  leg's explicit pin). The shim mutates
  `agent.messages[i].visibility` by direct attribute write at the
  storage edge — metadata presentation, not loop behaviour.
- `_create_session`'s constructor call is unchanged — the new
  `Session.platform` field defaults to `None`, which is correct
  for the WS-native code path. Per the leg guidance, an explicit
  `platform=None` kwarg would be visual noise.
- F5 L1/L2/L3's uncommitted changes (the badge JS+CSS, the
  `_session_to_list_payload` projection helper, the
  `the_one/sessions/` package, the `tag_post_step_visibility`
  helper) are untouched by this leg.

### Leg 5 — chat-ui-render-visibility-distinction (landed 2026-05-18)

**Shape: pure render-side.** No server-side Python edits; no agent-loop
edits. `renderMessage` consumes the `visibility` key the codec already
emits at `the_one/db/codec.py:154` and applies a class + inline label
when `=== "operator"`. Tokens use the real chat.css conventions
(`--border-strong`, `--fg-tertiary`, `--font-family-mono`,
`--font-size-tiny`; hardcoded px for spacing).

**Changes Made**

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`:
  `renderMessage(cls, text, opts)` now reads `opts.visibility`. When
  `=== "operator"`, the bubble gains the `msg-operator-only` class and
  a `<span class="msg-operator-only-label">[operator-only]</span>`
  prepended as the first child. The non-markdown text body branch
  switches from `el.textContent = text` (which would wipe the
  prepended label) to `el.appendChild(document.createTextNode(text))`
  ONLY in the labeled branch; the unlabeled fast path keeps
  `textContent` byte-identically. `el.dataset.visibility` is set
  whenever `opts.visibility` is truthy — provides a DOM-shape hook
  for tests and future maintenance.
- `the_one/interfaces/web/static/css/chat.css`: two new rules inside
  the existing `@layer areas { ... }` block, placed adjacent to the
  `.msg.system` rule in the message-bubble section. Used
  `.area-chat .msg.msg-operator-only` (specificity 0,2,0) rather than
  the leg-suggested `.area-chat .msg-operator-only` (0,1,0) so the
  rule reliably overrides the role-class `border-left` on
  `.msg.tool` / `.msg.tool.error` (which set their own left border
  at the same single-class specificity).
- `the_one/interfaces/web/static/js/areas/chat.js`:
  - History-replay loop: `histOpts` now carries
    `visibility: ev.visibility`.
  - `buildToolMsg(text, isError, toolCallId, opts)` extended with an
    `opts` arg and forwards it to `renderMessage`. Both history-replay
    `tool_call` / `tool_result` branches and the live-event branches
    thread the event's `visibility` through this arg.
  - Live `user` and live `assistant` (non-streaming) `addMsg` calls
    extended to pass `{ visibility: data.visibility }` as `opts`.
  - Streaming-bubble: new closure variable `currentStreamingVisibility`
    captures the first `assistant_chunk`'s `data.visibility` and is
    applied at placeholder construction. Reset to `null` alongside
    `currentStreamingMsg` at every call site of
    `finalizeStreamingBubble()` (live `assistant`, live `tool_call`,
    live `tool_result`, `auth_required`, `done`). This preserves the
    "no signature change on `finalizeStreamingBubble`" contract.
- `tests/browser/test_flow_chat_visibility_distinction.py` (new):
  one DOM-shape Playwright test. Spawns a fresh app subprocess
  (custom fixture exposes `data_dir` for direct SQLite seeding),
  seeds a provider + agent via the existing API seeders, builds a
  mixed-visibility `messages` blob via `Message` constructors + the
  codec's `encode_messages` (no hand-crafted JSON), inserts the
  `chat_sessions` row directly via sqlite3, deep-links to
  `#chat/sessions/<id>`, and asserts: `.msg-operator-only` count
  ≥ 2, `.msg-operator-only-label` count ≥ 2 with text
  `[operator-only]`, the peer-visible `.msg.tool` bubble does NOT
  carry `.msg-operator-only`, and the operator-only bubbles carry
  `data-visibility="operator"`.

**Tests Added**

1 browser test in `tests/browser/test_flow_chat_visibility_distinction.py`:

- `test_chat_renders_operator_visibility_distinction` — seeds a USER
  + ASSISTANT pair tagged `OPERATOR_VISIBILITY` and a peer-visible
  TOOL (visibility=None) into a `chat_sessions` row, navigates the
  browser to the seeded session, and asserts the DOM shape.

No new unit tests in this leg; the render-side change is verified
end-to-end via the browser test. The codec is already covered by
`tests/test_db_codec.py` and unchanged.

**Test-Suite Results**

- `docker exec the-one pytest tests/browser/test_flow_chat_visibility_distinction.py -m browser -x --timeout 60 -v`
  → 1 passed in 1.48s (initial run after rebuild) and 1.58s (post
  lint fix re-run).
- `docker exec the-one pytest tests/test_db_codec.py tests/test_ws_storage_edge_shim_visibility.py -x --timeout 30`
  → 62 passed in 0.25s (codec + F5 L4 regression net).
- `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_visibility_helper.py tests/test_connectors_e2e_ws_into_connector.py -x --timeout 60`
  → 38 passed in 7.78s (F1-F4 + F5 L2/L3 regression net).
- `make test-unit` → 1977 passed, 4 skipped, 404 deselected. Stable
  vs. F5 L4 baseline (this leg adds zero unit tests).
- `make rebuild && make test-browser` → 347 passed, 35 skipped, 12
  deselected in 297.24s. The new browser test is part of that run;
  every other browser test passes unchanged.
- `make lint` → All checks passed (one cleanup: removed an unused
  `Browser` import from the new test file).

**Notes / Deviations**

- **CSS specificity tightening (deliberate).** The leg's recommended
  rule was `.area-chat .msg-operator-only` (single-class specificity
  0,1,0). Existing `.msg.tool` / `.msg.tool.error` already set
  `border-left` at the same specificity, so cascade order alone
  would not guarantee the operator marker wins on a tool bubble
  with `visibility=operator`. Bumped the rule to
  `.area-chat .msg.msg-operator-only` (0,2,0) — explicitly
  authorized by the leg's "CSS specificity" edge-case section.
- **Streaming-bubble closure reset placement.** The leg artifact
  suggested resetting `currentStreamingVisibility` on `done`. I
  reset it at every `finalizeStreamingBubble()` call site
  (`assistant`, `tool_call`, `tool_result`, `auth_required`,
  `done`) so it tracks `currentStreamingMsg`'s lifecycle exactly.
  This preserves the leg's explicit pin that
  `finalizeStreamingBubble`'s signature does not change.
- **Known live-broadcast tagging gap (acknowledged, NOT closed).**
  The WS broadcast path in `_process_and_broadcast` builds events
  inline at lines 898-933 / 966-974 without consulting
  `Message.visibility` (because the F5 L4 storage-edge shim runs
  AFTER `agent.step` completes, but `_send_to_session` calls fire
  WITHIN the step iteration). The operator's just-typed turn on a
  connector-attached session renders unmarked UNTIL the next page
  refresh / session rejoin, at which point the codec's replay
  carries the `visibility` tag and the render shows the marker.
  Acceptable for v1 per the leg artifact's "Context — Known
  limitation" section; the JS render-side channel forwards
  `data.visibility` regardless so when a follow-on leg adds
  live-broadcast tagging the marker will appear in real time
  with no further frontend work. **Per the explicit guidance for
  this leg: I did not fold in server-side broadcast extensions.**
- **Browser-test seeding.** The conftest `app_with_agent` fixture
  hides `data_dir` behind its body; the new test mirrors the
  spawn logic in a local fixture (`app_with_data_dir`) so it can
  reach into the subprocess's SQLite file for direct seeding.
  This is the same pattern `tests/browser/test_markdown.py` uses
  for a module-scoped variant — established precedent.
- **Lint cleanup.** Initial test file imported
  `Browser` from `playwright.sync_api` (mirroring conftest) but
  the new fixture uses `Page` only; removed the unused import.
- The agent loop in `the_one/agent/core.py` is untouched (per the
  leg's explicit pin).
- F5 L1/L2/L3/L4's uncommitted changes are untouched by this
  leg.

### Leg 6 — dispatcher-broadcast-when-subscribed (landed 2026-05-18)

**Shape: dispatcher tail broadcast + codec keyword-only parameter
+ six contract tests.** The inbound dispatcher now emits per-message
UI events to live WS subscribers AFTER `chat_repo.update` and BEFORE
leaving the per-session lock. Zero subscribers remains a clean no-op
(`broadcast_to_session` iterates an empty set). The codec gained a
keyword-only `index_offset: int = 0` parameter so the dispatcher can
project the `agent.messages[pre_step_len:]` slice while still
generating session-lifetime-unique `parent_message_id` values.
**Implicit closure of the F5 L5 inbound-side broadcast-visibility
gap:** the dispatcher's events now carry `visibility` end-to-end via
`Message.visibility` (already tagged by `tag_post_step_visibility`),
so a live operator observing a connector-attached session in Chat
sees the operator-only marker in real time. The WS-typed path's
symmetric gap (F5 L5 known limitation) is NOT addressed here.

**Changes Made**

- `the_one/db/codec.py`: `messages_to_ui_events` signature changed to
  `(messages: list[Message], *, index_offset: int = 0) -> list[dict[str, Any]]`.
  Replaced `for i, msg in enumerate(messages):` with
  `for relative_i, msg in enumerate(messages): i = relative_i + index_offset`.
  Existing `f"replay-msg-{i}"` construction at line 182 now uses the
  offset-adjusted index. Default `0` keeps `_restore_session` and
  `_get_or_restore_session` byte-identical.
- `the_one/connectors/_inbound.py`: added module-top imports for
  `messages_to_ui_events` (extending the existing `db.codec` import
  line) and `broadcast_to_session` (extending the existing
  `the_one.sessions` import line). Neither has a known cycle with
  `connectors._inbound`, so they go module-top — NOT function-local
  like the `db.repositories` / `encryption` / `config` imports
  already documented at lines 100-110. After `await chat_repo.update(updated)`
  and BEFORE the `finally:` block, inserted the broadcast block:
  `new_msgs = agent.messages[pre_step_len:]`; if non-empty,
  `events = messages_to_ui_events(new_msgs, index_offset=pre_step_len)`
  and iterate `await broadcast_to_session(session_row.id, event)`.
  The block runs inside the per-session lock — the comment block
  documents the serialization trade-off and links the
  `parent_message_id` regression test.
- `tests/test_connectors_inbound_broadcast.py` (new): six contract
  tests + a `_FakeWS` / `_RaisingWS` / `_OrderingWS` trio of WS
  stubs, an autouse `_clear_pool_locks_registry` fixture that calls
  `the_one.sessions.clear_for_test()` (mirroring
  `tests/test_connectors_inbound.py:94`), and a `_dispatch_and_collect`
  helper that warms the session, subscribes the fake WS, then drives
  the dispatch-under-test.

**Tests Added**

6 tests in `tests/test_connectors_inbound_broadcast.py`:

- `test_dispatch_inbound_broadcasts_per_message_when_subscribed` —
  one `send_json` per new Message (user + assistant for a plain-text
  reply).
- `test_dispatch_inbound_zero_subscribers_is_noop` — no subscriber
  registered → dispatch completes; session row + history persisted.
- `test_dispatch_inbound_broadcasts_carry_visibility` —
  ASSISTANT-with-tool_calls (`send_to_platform_channel`) + successful
  TOOL result; asserts the event sequence
  `[user, tool_call, tool_result, assistant]`, with
  `"visibility" not in user_event`, `tool_call.visibility == "operator"`,
  `"visibility" not in tool_result_event` (leg-3 send-success
  carve-out, omitted-key contract), and final assistant
  `visibility == "operator"`.
- `test_dispatch_inbound_broadcasts_after_persistence` — wraps
  `ChatSessionRepository.update` to append `"persist"` to an ordered
  list; the subscriber's `send_json` appends `"broadcast"`. Asserts
  every `"broadcast"` entry follows the second dispatch's
  `"persist"` (the warmup's persist comes first; ordering pinned
  deterministically).
- `test_dispatch_inbound_broadcast_exception_does_not_corrupt_state` —
  subscriber's `send_json` raises; dispatcher completes without
  propagating; persistence is still observable. Inherits
  `broadcast_to_session`'s per-WS try/except + dead-WS prune.
- `test_dispatch_inbound_multi_turn_parent_message_ids_do_not_collide` —
  regression for the codec `index_offset` fix. Two consecutive
  turns on the same session_id, each emitting an
  assistant-with-tool_calls; asserts the unique-set of
  `parent_message_id` values across broadcast payloads has size 2
  (one per turn). Without the fix both turns would share
  `replay-msg-0` and the unique-set would have size 1.

**Test-Suite Results**

- `docker exec the-one pytest tests/test_connectors_inbound_broadcast.py -x --timeout 30 -v`
  → 6 passed in 1.23s.
- `docker exec the-one pytest tests/test_db_codec.py tests/test_connectors_inbound.py -x --timeout 30`
  → 74 passed in 3.74s (codec regression + dispatcher byte-identical
  on the zero-subscriber path).
- `docker exec the-one pytest tests/test_connectors_inbound.py
  tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py
  tests/test_connectors_e2e_ws_into_connector.py
  tests/test_connectors_visibility_helper.py tests/test_db_codec.py
  -x --timeout 60` → 92 passed in 8.37s.
- `make test-unit` → **1983 passed**, 4 skipped, 404 deselected.
  Matches the leg's predicted delta (F5 L5 baseline 1977 + 6 new
  tests = 1983).
- `make lint` → All checks passed.
- `grep -rn "from the_one.interfaces" the_one/connectors/ the_one/sessions/`
  → empty (one-way `connectors → sessions` and forbidden
  `connectors|sessions → interfaces.web` still hold).

**Notes / Deviations**

- **No deviations from the leg plan.** Implementation followed the
  Implementation Guidance step-by-step: (1) extend codec with
  `index_offset` kwarg-only param; (2) wire dispatcher with
  module-top imports + broadcast block after persistence; (3) add
  the six contract tests with the autouse `clear_for_test()`
  cleanup fixture.
- **Implicit closure of the F5 L5 inbound-side live-broadcast gap.**
  The F5 L5 debrief noted that the live-broadcast tagging gap on
  the WS-typed path was acknowledged but not closed. This leg, by
  consequence of its design (the codec reads `Message.visibility`
  on every projected event and the visibility tag is applied by
  `tag_post_step_visibility` BEFORE the broadcast fires), naturally
  closes that gap on the INBOUND side: a connector-driven turn now
  reaches live observers with the operator-only marker in real
  time. The WS-typed path's symmetric gap remains documented as a
  follow-on (the WS handler's `_send_to_session` calls fire WITHIN
  the agent step, before the storage-edge shim tags
  `Message.visibility`; symmetric resolution requires a separate
  leg).
- **Test fixture for ordering test.** The
  `test_dispatch_inbound_broadcasts_after_persistence` test uses a
  warmup dispatch to materialise the session row BEFORE subscribing,
  so the warmup contributes a `"persist"` entry to the ordered list
  before any subscriber exists. Test assertion is structured around
  this: assert `order[0] == "persist"`; then `order.index("persist", 1)`
  locates the second-dispatch persist; assert all entries after
  that second persist are `"broadcast"`. Equivalent to the
  leg-suggested list-mutation pattern; an artifact of the
  `_dispatch_and_collect` helper's warmup step.
- **The agent loop in `the_one/agent/core.py` is untouched** (per
  the leg's explicit pin and the mission constraint).
- **F5 L1-L5 uncommitted changes remain untouched** by this leg —
  the changes here are isolated to the codec, the dispatcher, and a
  new test file.

### Leg 7 — e2e-tests-and-design-language (landed 2026-05-18)

**Shape: pure additive e2e coverage + written design-language audit.**
Zero production Python edits, zero CSS/JS edits — the M04/M06 audit
came back clean on all three F5-introduced surfaces, so no inline fix
was applied. Two new browser tests fill the e2e gap the flight-design
explicitly carved out for this leg: one source-badge contract test
(deferred from L1 to this dedicated e2e leg) and one operator-input
write-path test (the symmetric browser-side counterpart to the
non-browser L4 storage-edge round-trip).

**Changes Made**

- `tests/browser/test_flow_chat_session_list_source_badge.py` (new):
  one Playwright test that seeds two `chat_sessions` rows via direct
  sqlite3 INSERT (one web-native with all seven connector-keying
  columns NULL; one connector-attached with `platform="stub"`,
  `connector_account_id="stub-acct-1"`, `channel_id="C1"`,
  `peer_id="P1"`), boots the chat area, and asserts the connector
  row's `.session-item-source` badge text (`"stub"`), its
  `.session-item-source--stub` typed-modifier class, and the
  ABSENCE of the badge on the web-native row. Mirrors L5's local
  `app_with_data_dir` fixture for direct-DB seeding from outside the
  spawned subprocess. INSERT uses the 13-column schema that matches
  `ChatSessionRepository.create`
  (`the_one/db/repositories.py:726-750`).
- `tests/browser/test_flow_chat_operator_input_visibility.py` (new):
  two Playwright tests covering the L4 storage-edge shim's write
  path through the browser:
  - `test_operator_input_yields_operator_visibility_on_connector_session`
    — seeds a connector-attached session, types a turn via the
    verified `[data-testid="chat-input"]` /
    `[data-testid="chat-send-btn"]` selectors, waits for the
    deterministic mock-provider reply (`"Mock response from the mock
    provider."` per `tests/browser/test_flow_chat.py:44`), refreshes
    + re-navigates to force the codec replay path (the known L5
    live-broadcast tagging gap is sidestepped by the refresh), and
    asserts the resulting USER + ASSISTANT bubbles carry the
    `msg-operator-only` class AND the `[operator-only]` label.
  - `test_operator_input_yields_no_operator_visibility_on_web_session`
    — the negative control: same flow on a web-native session
    (`platform=None`); asserts the resulting USER + ASSISTANT
    bubbles do NOT carry `msg-operator-only`. Uses the robust
    `el => el.classList.contains('msg-operator-only')` evaluate
    pattern (mirroring L5's
    `tests/browser/test_flow_chat_visibility_distinction.py:245-247`)
    rather than substring matching on the className string.
- No CSS/JS edits — the design-language audit (below) found no
  deviation warranting an inline fix.

**Tests Added**

3 browser tests:

- `test_session_list_renders_source_badge_for_connector_attached_row`
  in `tests/browser/test_flow_chat_session_list_source_badge.py`.
- `test_operator_input_yields_operator_visibility_on_connector_session`
  in `tests/browser/test_flow_chat_operator_input_visibility.py`.
- `test_operator_input_yields_no_operator_visibility_on_web_session`
  in `tests/browser/test_flow_chat_operator_input_visibility.py`.

Zero unit tests added (this leg's coverage is browser-only by
design; the unit-test side was completed in L3, L4, and L6).

**Test-Suite Results**

- `docker exec the-one pytest tests/browser/test_flow_chat_session_list_source_badge.py tests/browser/test_flow_chat_operator_input_visibility.py -m browser -x --timeout 120 -v`
  → 3 passed in 4.83s.
- `make rebuild && make test-browser` → 350 passed, 35 skipped, 12
  deselected in 303.17s. +3 vs. the L5 baseline (347) — exactly the
  three tests this leg adds; no regressions.
- `make test-unit` → 1983 passed, 4 skipped, 407 deselected in
  132.07s. Stable vs. baseline; this leg adds zero unit tests. The
  pre-existing `Event loop is closed` warning in
  `test_db_migration.py::TestSchemaV17::test_v17_fresh_db_includes_agents_connector_account_ids_column`
  remains unchanged from baseline.
- `make lint` → All checks passed.

### Design Language Audit (Leg 7)

Three F5-introduced visual surfaces audited against the M04/M06
token/spacing palette. All three PASS with no deviation; no inline
fix was applied.

| Surface | Selector | Tokens | Spacing | M04/M06 fit |
|---------|----------|--------|---------|--------------|
| Session source badge | `.area-chat .session-item-source` (chat.css L44-54) | `--font-family-mono`, `--font-size-tiny`, `--fg-tertiary`; `text-transform: uppercase`, `letter-spacing: 0.05em` | `margin-top: 2px`; ellipsis behavior (`overflow: hidden`, `text-overflow: ellipsis`, `white-space: nowrap`) | **PASS** |
| Operator-only marker | `.area-chat .msg.msg-operator-only` (chat.css L213-216) | `--border-strong` (border color) | `border-left: 3px solid`; `padding-left: 8px` | **PASS** |
| Operator-only label | `.area-chat .msg-operator-only-label` (chat.css L217-223) | `--font-family-mono`, `--font-size-tiny`, `--fg-tertiary` | `display: inline-block`; `margin-right: 4px` | **PASS** |

**Audit notes**:

- **Source badge token-parity.** The `.session-item-source` rule
  uses the exact same `mono + tiny + tertiary + uppercase + 0.05em`
  letter-spacing palette as `.session-group-label` (chat.css L15)
  AND `.session-item-agent` (chat.css L35). The `margin-top: 2px` is
  the only spacing addition — necessary because the badge sits as a
  third row inside `.session-item-text`'s flex column, below the
  agent line; without the margin the line-height alone would not
  give enough visual separation. Hardcoded px matches the chat.css
  convention (the file uses `px` throughout for in-component
  spacing).
- **Operator-only marker specificity.** The L5 leg log already
  documented the deliberate bump from the leg-suggested 0,1,0 to
  0,2,0 (via `.msg.msg-operator-only`) so the rule overrides the
  `border-left` declared on `.msg.tool` / `.msg.tool.error` at the
  same single-class specificity. The audit confirms this remains
  the correct choice — no other `.msg`-prefixed role classes set a
  conflicting `border-left` that would force a further specificity
  bump.
- **Operator-only label token-parity.** Same palette as the source
  badge — three F5 visual surfaces all share the `mono + tiny +
  tertiary` "metadata text" treatment, which keeps the operator
  console's connector-source signals visually coherent. The
  `margin-right: 4px` spacing matches the convention used elsewhere
  in `.msg`-scoped rules (e.g. `.msg-attribution` uses comparable
  4px-class margins).
- **No deviation surfaced; no inline fix applied.** All three
  surfaces sit cleanly within the existing token + spacing palette;
  no cheap-to-fix-inline deviation; no escalation-to-HAT-closer
  follow-on raised by this audit.
- **Methodology checkpoint, not a quality gate.** Per the leg
  artifact's framing (and per the flight's design that the HAT
  closer in L8 is the final acceptance gate), this audit is a
  documented inventory of the F5-introduced surfaces' token/spacing
  choices that the operator's HAT review can refer to. Future
  maintainers can verify token consistency against this table
  without re-reading every CSS rule.

**Notes / Deviations**

- **Zero production Python edits, zero CSS/JS edits.** The leg
  artifact explicitly framed CSS/JS edits as CONDITIONAL on the
  audit surfacing a cheap-to-fix-inline deviation. The audit came
  back clean across all three surfaces, so no edit was applied.
- **`make rebuild` was still run** (per the project convention that
  the container image must reflect any recent JS/CSS work before
  browser tests). After the rebuild, playwright's chromium cache
  was wiped (the `_ensure-playwright` target reinstalls it
  automatically); `make test-browser` ran it via its `@$(MAKE)
  --no-print-directory _ensure-playwright` dependency without
  manual intervention.
- **`app_with_data_dir` fixture pattern.** Both new test files
  define a local `app_with_data_dir` fixture mirroring L5's pattern
  rather than extracting it into `tests/browser/conftest.py`. The
  leg artifact allowed either approach; copying keeps the conftest
  scope unchanged and isolates the spawn logic with the tests that
  use it.
- **13-column INSERT.** Both new test files seed `chat_sessions`
  rows via a sync sqlite3 INSERT that mirrors the production
  `ChatSessionRepository.create` 13-column shape
  (`the_one/db/repositories.py:726-750`). Web-native rows pass NULL
  for all seven connector-keying columns; connector-attached rows
  set `platform`, `connector_account_id`, `channel_id`, `peer_id`
  (with `thread_id`, `session_metadata`, `last_inbound_at` left
  NULL — the channel-only DM shape used in F3/F4 precedents).
- **Verified selectors used.** `[data-testid="chat-input"]` and
  `[data-testid="chat-send-btn"]` (per
  `tests/browser/test_flow_chat.py:33-34`); the mock-provider reply
  text `"Mock response from the mock provider."` (per
  `tests/browser/test_flow_chat.py:44`); the operator-only class
  `msg-operator-only` and label `.msg-operator-only-label` (per
  L5's render-side output). Bubble locators use the
  `[data-testid="message"].user` / `.assistant` shape that L5 and
  `test_flow_chat.py` both rely on.
- **Refresh + re-navigate pattern.** The L5 live-broadcast tagging
  gap means the operator-input test must NOT assert on the live
  moment of typing — only on the post-refresh codec-replay render.
  Both tests do `page.reload()` followed by an explicit hash-route
  re-navigation, then wait for the chrome to remount before
  asserting bubble shape.
- **The agent loop in `the_one/agent/core.py` is untouched** (per
  the leg's explicit pin and the mission constraint).
- **F5 L1-L6 uncommitted changes remain untouched** by this leg —
  the only files added/modified are the two new test files and
  this flight-log entry.

---

## Decisions

Runtime decisions not in original plan.

---

## Deviations

Departures from planned approach.

---

## Anomalies

Unexpected issues encountered.

---

## Session Notes

Chronological notes from work sessions.
