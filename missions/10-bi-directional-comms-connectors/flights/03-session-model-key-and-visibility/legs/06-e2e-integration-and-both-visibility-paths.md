# Leg: e2e-integration-and-both-visibility-paths

**Status**: completed
**Flight**: [Session Model — Schema, Key Normalization, Visibility](../flight.md)

## Objective

Land the end-to-end integration test that proves F3's contract as a single trace: schema → model → codec → resolver → dispatcher → persistence. The leg's main NEW coverage is the **both-visibility coexistence** scenario — a connector-attached session with both peer-visible messages (from `dispatch_inbound`) AND operator-visibility messages (constructed directly to simulate F5's future operator-input path) in its history, with `messages_to_ui_events` projecting both correctly. This is the regression baseline F4, F5, and downstream flights inherit when building on the F3 surface.

## Context

- **Most of the flight's planned e2e scenarios are already covered** by tests in legs 3+4:
  - First-contact session creation, within-window continuation, after-window fresh, per-thread isolation, DM session-keying — `tests/test_connectors_session.py` (leg 3) covers resolver-level.
  - Concurrent same-session serialization, concurrent different-session parallelism, pool `last_activity` touch — `tests/test_connectors_inbound.py` (leg 4) covers dispatcher-level.
  - Schema migration verification — `TestSchemaV16` (leg 1).
  - Visibility round-trip + projection — `tests/test_db_codec.py::TestMessagesToUiEventsVisibility` (leg 2).
- **What leg 6 adds**:
  1. **Both-visibility coexistence**: a single connector-attached session holds both peer and operator messages, persisted correctly via codec, projected correctly via `messages_to_ui_events`. NOT covered by any existing test — leg 4 tests visibility=None defaults; leg 2 tests projection in isolation; leg 6 stitches them together.
  2. **Full-stack smoke test**: one test that exercises ALL F3 components in a single trace — schema applied to a fresh in-memory DB, stub plugin registered, connector account seeded, agent factory built, `dispatch_inbound` driven, history persisted, decoded, projected to UI events. If a future flight breaks any F3 surface, this test surfaces the regression at the highest level.
  3. **Optional regression aggregators**: documentation-style assertions that aggregate "F3 contract holds" — i.e. that the seven schema columns are populated as expected, that the resolver's continuation window is consulted, that the dispatcher's per-session lock fires for the same external key. These cross-cut what individual tests verify in isolation.
- **NOT in leg 6 scope**:
  - Outbound (F4 owns the platform-send tool + outbound path).
  - Chat UI rendering (F5 owns; leg 6 verifies the codec's projection output but does NOT render it).
  - Real Discord / Slack integration (F8 / F9 own).

## Inputs

State that must exist before this leg runs:

- Legs 1+2+3+4+5 of this flight are `landed` (1878 unit tests + 13 browser tests passing on `flight/03-session-model-key-and-visibility`; uncommitted per batched-review model).
- `the_one/db/schema.py:CURRENT_VERSION == 16` (leg 1).
- `the_one/db/models.py:ChatSession` with the 7 external-key fields (leg 1); `ConnectorAccount.session_continuation_seconds` (leg 1).
- `the_one/llm/base.py:Message.visibility` (leg 2).
- `the_one/connectors.OPERATOR_VISIBILITY` constant (leg 2).
- `the_one/db/codec.py:message_to_dict / message_from_dict / messages_to_ui_events` with visibility round-trip + projection (leg 2).
- `the_one/connectors/_session.py:resolve_session` (leg 3).
- `the_one/db/repositories.py:ChatSessionRepository.find_most_recent_by_external_key` + `update_last_inbound` (legs 3+4).
- `the_one/connectors/_inbound.py:dispatch_inbound` + `_clear_for_test` (leg 4).
- `the_one/connectors/_stub.py:StubPlugin` with `display_channel` (leg 3).
- `the_one/connectors/registry.py:register_for_test` (F1 — the test-fixture registration hook).
- Mock LLM provider at `the_one/llm/mock.py` (extant — produces predictable single-shot replies; suffices for leg 6's non-concurrency tests).

## Outputs

State that must exist after this leg completes:

- New test file `tests/test_connectors_e2e_session.py` (parallel to F1's `tests/test_connectors_e2e.py`) covering **3 tests** (NOT 4 — first-contact smoke dropped per design review: it's covered by leg-4's `test_dispatch_inbound_creates_session_on_first_contact` and visibility=None pinning by leg-4's `test_dispatch_inbound_persists_inbound_with_visibility_none` and `_agent_reply_*` siblings):
  - `test_e2e_both_visibility_paths_coexist_in_session` — connector inbound creates a session, then a direct repo write adds an `OPERATOR_VISIBILITY`-tagged Message to the same session's history (simulating F5's future operator-input path). Assert:
    - Decoded `agent.messages` contains BOTH messages.
    - Encoded JSON shows the operator-tagged message WITH `"visibility": "operator"` AND the peer-originated messages WITHOUT a `visibility` key (omitted, NOT explicit None — design-review verified this matches the codec contract at `the_one/db/codec.py:63-67`).
    - `messages_to_ui_events(decoded)` produces events where the operator message has `event["visibility"] == "operator"` and the peer events have NO `visibility` key.
    - This is the F3 contract proof that F5 inherits: operator and peer messages coexist; the projection layer faithfully tags each kind.
  - `test_e2e_session_metadata_column_round_trips_at_create_time` — write a non-trivial dict (e.g. `{"routing": {"rule": "default"}, "audit": ["v1"]}`) into `session_metadata` at `ChatSessionRepository.create` time, read it back, assert byte-identical. Plus a `session_metadata=None` round-trip. Forward-compat for F7's routing-decision logs; verified leg-1's `create` writes this column.
  - `test_e2e_continuation_window_real_time_supersede` — push two inbounds for the same external key with a real `asyncio.sleep(2)` between them; use the per-account `ConnectorAccount.session_continuation_seconds=1` override (NOT the env var — exercises the column path leg-5 just surfaced in the admin editor). Assert exactly 2 `chat_sessions` rows exist. **Distinct from leg-4's `test_dispatch_inbound_creates_new_session_after_window`** which fakes elapsed time via stale `last_inbound_at` — leg-6's variant exercises real `datetime.now()` comparison and catches `datetime.now`-vs-`utcnow` regressions the faked test would miss. Include a comment in the test body explaining the intentional wall-clock trade-off.
- Flight log gains "Leg Progress: e2e-integration-and-both-visibility-paths" entry.
- Leg status flipped to `landed`. This leg ticked off in `flight.md`. Flight ready for the post-flight Reviewer pass (Phase 2d of agentic-workflow).

## Acceptance Criteria

- [ ] New test file `tests/test_connectors_e2e_session.py` exists with at least the four tests in Outputs.
- [ ] **Both-visibility coexistence test** (`test_e2e_both_visibility_paths_coexist_in_session`) explicitly asserts:
  - The persisted `chat_sessions.messages` JSON contains exactly one message with `"visibility": "operator"` and N-1 messages without the visibility key (where N is the total Messages persisted).
  - `messages_to_ui_events` projects accordingly: events derived from the operator-tagged Message carry `event["visibility"] = "operator"`; events from untagged Messages have NO visibility key (key absent, not `None`).
  - This is the canonical example F5 will consult when implementing the Chat UI's visual distinction.
- [ ] The full-pipeline test (`test_e2e_first_contact_...`) drives `dispatch_inbound` to completion against the StubPlugin + a MockProvider-backed agent. Asserts the agent-step output is persisted (the mock provider's reply text appears in the decoded history).
- [ ] The session-metadata forward-compat test (`test_e2e_session_metadata_column_writable_for_future_flights`) writes a dict like `{"routing": {"rule": "default", "agent": "test"}}`, reads it back, asserts byte-identical. Includes a None-round-trip case.
- [ ] The continuation-window-reuse test monkeypatches `THE_ONE_SESSION_CONTINUATION_SECONDS=1` (or whatever scoping mechanism leg 3's `_resolve_continuation_seconds` honors); sleeps 2 seconds between the second and third inbound; asserts row count.
- [ ] All tests use the same test-fixture pattern as `tests/test_connectors_inbound.py` (leg 4) and `tests/test_connectors_session.py` (leg 3) — leg-6 author reads those files first to understand the existing fixture / autouse-cleanup conventions and mirrors them.
- [ ] No new code outside the test file. F3 is functionally complete after leg 5; leg 6 is verification + regression-baseline addition.
- [ ] `make test` clean (1878 → ~1878 + 4 = ~1882 tests).
- [ ] `make lint` clean.
- [ ] Flight log updated with leg-completion entry.
- [ ] Leg status flipped to `landed`. This leg ticked off in `flight.md`.

## Verification Steps

- **Scoped tests** — `docker exec the-one pytest tests/test_connectors_e2e_session.py -x --timeout 30 -v` passes.
- **Both-visibility test passes** — verifies the F3 visibility-layer contract end-to-end.
- **Full suite** — `docker exec the-one pytest -x --timeout 30` green at ~1882 tests.
- **Lint** — `docker exec the-one ruff check the_one/ tests/` clean.
- **Final leg verification (post-flight readiness)**: After leg 6 lands, verify the flight is ready for Phase 2d (flight-level Reviewer pass + commit):
  - All 6 leg statuses are `landed`.
  - `flight.md` Legs list has all 6 entries ticked.
  - Flight log has Leg Progress entries for all 6 legs.
  - Working tree is dirty (uncommitted changes from all 6 legs), branch is `flight/03-session-model-key-and-visibility`.

## Implementation Guidance

1. **Read leg 3 + leg 4 test files first**: `tests/test_connectors_session.py` (leg 3) and `tests/test_connectors_inbound.py` (leg 4) carry the canonical fixture patterns for F3 tests. Mirror their autouse-cleanup, StubPlugin registration, in-memory DB seeding. Leg 6's test file should look stylistically identical to those.

2. **Test fixture sketch — leg-4's pattern is the template** (design-review confirmed there is no shared `conftest.py` fixture for `in_memory_db` / `connector_account` / `agent_factory`; leg 4 uses inline helpers + an `isolated_db` per-file fixture). Mirror leg-4 line-for-line. The autouse cleanup MUST include `restore_to_baseline_for_test()` per leg-4's pattern at `tests/test_connectors_inbound.py:81-90` — otherwise registry state leaks between tests in the file.

   ```python
   import asyncio
   import json
   import pytest
   import pytest_asyncio

   from the_one.connectors import OPERATOR_VISIBILITY, registry
   from the_one.connectors._inbound import dispatch_inbound, _clear_for_test as clear_inbound_locks
   from the_one.connectors._pool import _clear_for_test as clear_pool
   from the_one.connectors._stub import StubPlugin
   from the_one.connectors.base import InboundEnvelope
   from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events
   from the_one.db.models import ChatSession
   from the_one.db.repositories import ChatSessionRepository
   from the_one.llm.base import Message

   # Leg 6 uses leg-4's per-file helpers verbatim — copy them or import from
   # tests.test_connectors_inbound (whichever is cleaner; the existing leg-4
   # author's call). The helpers to mirror:
   #   - `isolated_db` (pytest_asyncio.fixture — in-memory aiosqlite with ensure_schema applied)
   #   - `_seed_stub_account(conn, ...)` (creates a connector_accounts row with type="stub")
   #   - `_seed_provider_and_agent(conn, ...)` (seeds an agent + LLM provider config so factory.create works)
   #   - `_make_factory(conn)` (builds an AgentFactory bound to the in-memory DB)
   #   - `_envelope(...)` (constructs an InboundEnvelope with sensible defaults)
   # AND the autouse cleanup at `tests/test_connectors_inbound.py:81-90`:
   #   - StubPlugin.reset_for_test()
   #   - registry.register_for_test("stub", StubPlugin)
   #   - registry.restore_to_baseline_for_test()  ← the critical missing piece if not included
   #   - clear_pool() + clear_inbound_locks()
   ```

   Decide between (a) copying the leg-4 helpers into the new file (small duplication; ~80 LoC), (b) importing them from `tests.test_connectors_inbound` (cross-test-file import is unusual but works), or (c) extracting them into a shared `tests/_connectors_test_helpers.py` (the cleanest long-term home, but a refactor beyond leg-6 scope). **Recommend (a)** — keep leg-6 self-contained; the refactor to (c) is a clear F10-hardening-or-mission-end maintenance candidate, not a leg-6 concern.

3. **Test 1 — both-visibility coexistence (the leg's headline test)**. Uses leg-4 helpers inline (the design-review-confirmed pattern; do NOT take `in_memory_db`, `connector_account`, `agent_factory` as fixtures — those don't exist):

   ```python
   async def test_e2e_both_visibility_paths_coexist_in_session(isolated_db):
       """Connector inbound creates peer-visible turn; direct repo write adds an
       operator-tagged Message to the same session. Both visibility layers
       coexist in the persisted history; codec + projection faithfully tag
       each kind. F3 contract proof that F5's Chat UI inherits.
       """
       conn = isolated_db
       account = await _seed_stub_account(conn)
       await _seed_provider_and_agent(conn, agent_name="test-agent")
       factory = _make_factory(conn)
       registry.register_for_test("stub", StubPlugin)

       envelope = _envelope(
           platform="stub", account_id=account.id,
           channel_id="ch-eng", text="from peer",
       )

       # First inbound — creates session + peer turn (peer user + agent reply)
       await dispatch_inbound(
           agent_name="test-agent",
           account_id=account.id,
           envelope=envelope,
           factory=factory,
       )

       chat_repo = ChatSessionRepository(conn)
       sess = (await chat_repo.list())[0]

       # Simulate F5's operator-input path by directly appending an
       # operator-tagged Message to the session's persisted history.
       # (F3 has no operator-input UI yet; F5 will own the path. The codec
       # round-trip is the contract — leg 6 verifies it works.)
       existing = decode_messages(sess.messages)
       operator_user = Message.user(
           "what's the context here?",
           visibility=OPERATOR_VISIBILITY,
       )
       operator_assistant = Message.assistant(
           "the peer asked about X",
           visibility=OPERATOR_VISIBILITY,
       )
       updated_history = existing + [operator_user, operator_assistant]
       sess_updated = sess.model_copy(update={"messages": encode_messages(updated_history)})
       await chat_repo.update(sess_updated)

       # Re-fetch + decode
       sess_after = await chat_repo.get(sess.id)
       msgs = decode_messages(sess_after.messages)

       # Both visibility layers present (exact counts — operator user + operator assistant)
       operator_msgs = [m for m in msgs if m.visibility == OPERATOR_VISIBILITY]
       peer_msgs = [m for m in msgs if m.visibility is None]
       assert len(operator_msgs) == 2
       assert len(peer_msgs) >= 2  # peer user + at least one agent reply (mock provider)

       # Encoded JSON: operator-tagged Messages carry "visibility": "operator";
       # peer-originated Messages do NOT carry the key (omitted, NOT explicit
       # None — design-review verified at the_one/db/codec.py:63-67)
       parsed = json.loads(sess_after.messages)
       operator_count = sum(1 for d in parsed if d.get("visibility") == "operator")
       absent_count = sum(1 for d in parsed if "visibility" not in d)
       assert operator_count == 2
       assert absent_count >= 2

       # messages_to_ui_events projects accordingly.
       # Operator user message → 1 event. Operator assistant message with
       # content → 1 event. So at least 2 operator-tagged events; more only if
       # an assistant has tool_calls (mock provider does not). Lower bound is
       # tight but the upper bound is variance-bound to tool-call expansion.
       events = messages_to_ui_events(msgs)
       operator_events = [e for e in events if e.get("visibility") == "operator"]
       absent_events = [e for e in events if "visibility" not in e]
       assert len(operator_events) >= 2
       assert len(absent_events) >= 2
   ```

4. **Test 2 — `session_metadata` forward-compat (simplified per design review)**. Verified that `ChatSessionRepository.create` writes `session_metadata` (`the_one/db/repositories.py:723-748` — design-review confirmed). The recommend-(a) pivot is the right call; F7 owns its update primitive:

   ```python
   async def test_e2e_session_metadata_column_round_trips_at_create_time(isolated_db):
       """Verify session_metadata column holds non-trivial JSON at row creation.

       Forward-compat for F7's future routing-decision logs. F3 L1 added
       the column; this test pins the round-trip BEFORE F7 needs it.
       """
       chat_repo = ChatSessionRepository(isolated_db)

       # Non-trivial dict
       metadata = {"routing": {"rule": "default"}, "audit": ["v1"]}
       new_session = ChatSession(
           id="test-meta-session-1",
           agent_name="test-agent",
           platform="stub",
           connector_account_id="acc-1",
           channel_id="ch-1",
           thread_id=None,
           peer_id="peer-1",
           session_metadata=metadata,
           last_inbound_at="2026-05-17T12:00:00+00:00",
       )
       await chat_repo.create(new_session)
       fetched = await chat_repo.get("test-meta-session-1")
       assert fetched.session_metadata == metadata

       # None round-trip — default state
       new_session_none = ChatSession(
           id="test-meta-session-2",
           agent_name="test-agent",
           session_metadata=None,
       )
       await chat_repo.create(new_session_none)
       fetched_none = await chat_repo.get("test-meta-session-2")
       assert fetched_none.session_metadata is None
   ```

5. **Test 3 — continuation-window real-time supersede**. Uses the per-account `session_continuation_seconds=1` override (NOT the env var — exercises the column-driven path the leg-5 admin editor surfaces; design-review-recommended):

   ```python
   async def test_e2e_continuation_window_real_time_supersede(isolated_db):
       """Two inbounds with real asyncio.sleep(2) between them and a 1-second
       per-account continuation window produce two distinct session rows.

       Distinct from leg-4's ``test_dispatch_inbound_creates_new_session_after_window``
       which fakes elapsed time via a stale ``last_inbound_at`` write. Leg-6's
       variant exercises real ``datetime.now()`` comparison and catches a
       ``datetime.now`` vs. ``utcnow`` regression that the faked test would
       miss. The 2-second sleep is intentional — it is the lightest possible
       exercise of the time-source code path.

       Uses per-account override (NOT env var) to exercise the column path
       the leg-5 admin editor surfaces (the env var is covered by leg-3's
       resolver tests).
       """
       conn = isolated_db
       account = await _seed_stub_account(conn, session_continuation_seconds=1)
       await _seed_provider_and_agent(conn, agent_name="test-agent")
       factory = _make_factory(conn)
       registry.register_for_test("stub", StubPlugin)

       envelope = _envelope(
           platform="stub", account_id=account.id,
           channel_id="ch-eng", text="ping",
       )

       # 1st inbound — creates session
       await dispatch_inbound(agent_name="test-agent",
                              account_id=account.id,
                              envelope=envelope, factory=factory)

       # Sleep past the 1-second window (real wall-clock; intentional)
       await asyncio.sleep(2)

       # 2nd inbound — should create a NEW session (window elapsed)
       await dispatch_inbound(agent_name="test-agent",
                              account_id=account.id,
                              envelope=envelope, factory=factory)

       chat_repo = ChatSessionRepository(conn)
       sessions = await chat_repo.list()
       assert len(sessions) == 2  # one for each inbound after window elapsed
   ```

6. **Run tests**:
   ```
   docker exec the-one pytest tests/test_connectors_e2e_session.py -x --timeout 30 -v
   docker exec the-one pytest -x --timeout 30                    # full suite
   docker exec the-one ruff check the_one/ tests/
   ```

8. **Update flight log** with "Leg Progress: e2e-integration-and-both-visibility-paths" entry. Capture: timestamps, summary, test-count delta from leg 5's 1878.

9. **Flip leg status to `landed`**, tick leg 6 in `flight.md`. Signal `[HANDOFF:review-needed]`. Do NOT commit — Phase 2d (the flight-level Reviewer pass + commit) follows.

## Edge Cases

- **Agent build for the test fixture**: the leg-4 dispatcher test fixture pattern (build `AgentFactory` with a MockProvider) is the template. Read leg 4's test file for the exact construction pattern — re-use, don't re-invent.

- **In-memory DB fixture sharing**: each test should get a fresh in-memory DB with schema applied. Leg-3 + leg-4 test files have this pattern; mirror them.

- **`asyncio.sleep(2)` in the continuation test**: real wall-clock sleep. If this slows the test suite materially, leg-6 author may switch to monkeypatching `datetime.now` inside the resolver — but that's a more invasive test technique. Start with sleep; tune if needed.

- **The both-visibility test's "simulate F5" path** uses `chat_repo.update(sess.model_copy(update={"messages": encoded}))` — the exact `_save_session_to_db` shape. The leg-1 docstring confirms this preserves connector identity columns. If for some reason the test discovers otherwise, that's a leg-1 contract regression — flag for fix, not for leg-6 workaround.

- **Test naming convention**: leg 4's tests use `test_dispatch_inbound_*` prefixes; leg 3 uses `test_resolve_session_*`. Leg 6 uses `test_e2e_*` as a distinct prefix so the e2e tests are easy to grep for in regression triage.

## Files Affected

- `tests/test_connectors_e2e_session.py` — new test file with 4 tests
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight-log.md` — leg-completion entry
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight.md` — tick leg 6 (all 6 boxes filled)
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/legs/06-e2e-integration-and-both-visibility-paths.md` — this file's status → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (scoped + full suite)
- [ ] Lint clean
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md's Legs list
- [ ] Do NOT commit — agentic-workflow batched-review model defers commit to flight end
- [ ] Signal `[HANDOFF:review-needed]`. The Flight Director's next action is Phase 2d (spawn flight-level Reviewer; commit).

---

## Citation Audit

5 citations verified against current code at leg design time:

- `tests/test_connectors_session.py` (leg 3) — verified exists.
- `tests/test_connectors_inbound.py` (leg 4) — verified exists.
- `tests/test_db_codec.py::TestMessagesToUiEventsVisibility` (leg 2) — verified exists.
- `tests/test_connectors_e2e.py` (F1) — verified exists; leg 6's file name `test_connectors_e2e_session.py` parallels it.
- `the_one/connectors.OPERATOR_VISIBILITY` (leg 2) — verified exports.
