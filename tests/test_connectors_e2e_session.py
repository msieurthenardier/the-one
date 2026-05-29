"""End-to-end integration tests for M10 F03 — connector-attached chat sessions.

Covers the F3 contract as a single trace (schema → model → codec →
resolver → dispatcher → persistence → projection). The headline test is
the both-visibility coexistence scenario: a single connector-attached
session holds BOTH peer-visible messages (from ``dispatch_inbound``) AND
operator-visibility messages (constructed directly to simulate F5's
future operator-input path) in its history, with ``messages_to_ui_events``
faithfully projecting both kinds. This is the regression baseline F4,
F5, and downstream flights inherit when building on the F3 surface.

Scope distinctions (NOT duplicating leg 3 / leg 4 coverage):

- First-contact session creation, within-window continuation, after-window
  fresh, per-thread isolation, DM session-keying — leg 3 covers
  resolver-level in ``tests/test_connectors_session.py``.
- Concurrent same-session serialization, concurrent different-session
  parallelism, pool ``last_activity`` touch — leg 4 covers
  dispatcher-level in ``tests/test_connectors_inbound.py``.
- Schema migration verification — ``TestSchemaV16`` in
  ``tests/test_db_migration.py`` (leg 1).
- Visibility round-trip + projection in isolation — leg 2 in
  ``tests/test_db_codec.py::TestMessagesToUiEventsVisibility``.

What this file adds:

1. ``test_e2e_both_visibility_paths_coexist_in_session`` — the headline.
   Operator-tagged and peer-originated Messages coexist in the same
   ``chat_sessions`` row; codec + projection both tag each kind
   faithfully. F3 contract proof F5 inherits.
2. ``test_e2e_session_metadata_column_round_trips_at_create_time`` —
   forward-compat for F7's routing-decision logs. F3 L1 added the
   column; this pins the round-trip BEFORE F7 needs it.
3. ``test_e2e_continuation_window_real_time_supersede`` — exercises the
   real ``datetime.now()`` code path with a wall-clock ``asyncio.sleep(2)``
   between two inbounds under a per-account ``session_continuation_seconds=1``
   override. Distinct from leg 4's
   ``test_dispatch_inbound_creates_new_session_after_window`` which fakes
   elapsed time via a stale ``last_inbound_at`` write — the wall-clock
   variant catches ``datetime.now`` vs. ``utcnow`` regressions the faked
   test would miss.

Fixture pattern mirrors ``tests/test_connectors_inbound.py`` (leg 4)
verbatim — the per-file ``isolated_db`` fixture + module-local
``_seed_*`` / ``_make_factory`` / ``_envelope`` helpers. There is no
shared ``conftest.py`` fixture for these; leg 4 set the convention and
leg 6 follows it self-contained.
"""

from __future__ import annotations

import asyncio
import json

import pytest

# F4 L5 (M10 F3 debrief carry-forward): the in-file helpers moved to
# ``tests/_connector_dispatch_helpers`` when this file became the SECOND
# consumer (F4 L5's new e2e test file is the THIRD; the explicit-import
# trigger was met at the second consumer per the F3 debrief). The
# ``isolated_db`` fixture itself lives in ``tests/conftest.py`` for
# pytest auto-discovery; only the helper FUNCTIONS are imported here.
from tests._connector_dispatch_helpers import (
    _envelope,
    _make_factory,
    _seed_provider_and_agent,
    _seed_stub_account,
)
from the_one.connectors import OPERATOR_VISIBILITY
from the_one.connectors import _inbound as inbound_mod
from the_one.connectors import _pool as pool_mod
from the_one.connectors._inbound import dispatch_inbound
from the_one.connectors._stub import StubPlugin
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.codec import (
    decode_messages,
    encode_messages,
    messages_to_ui_events,
)
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.base import Message, Role
from the_one.sessions import clear_for_test as _clear_session_registry

# ─── Fixtures (mirror leg 4's pattern verbatim) ──────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level recording buffers around each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_locks_registry():
    """Empty pool + per-session lock dict + registry between tests.

    The ``restore_to_baseline_for_test()`` call is critical — without it,
    registry state leaks between tests in this file (and into downstream
    test files in the full suite). Mirrors leg 4's autouse cleanup at
    ``tests/test_connectors_inbound.py:81-90``.
    """
    yield
    await pool_mod._clear_for_test()
    await inbound_mod._clear_for_test()
    # F5 L2: also clear the neutral session registries (shared lock +
    # subscribers).
    _clear_session_registry()
    _registry_clear_for_test()
    restore_to_baseline_for_test()


# ─── Test 1 — headline: both-visibility coexistence ──────────────────────


async def test_e2e_both_visibility_paths_coexist_in_session(
    isolated_db, monkeypatch
) -> None:
    """Connector inbound creates a peer-visible USER message + an
    operator-tagged assistant reply (F4 L4 dispatcher tagging); a
    direct repo write appends two more operator-tagged Messages to
    the same session's history (simulating F5's future operator-input
    path).

    Cross-flight contract proof that F5 inherits:

    - Decoded ``agent.messages`` contains BOTH peer and operator messages.
    - Encoded JSON: operator-tagged dicts carry ``"visibility": "operator"``;
      peer-originated dicts have NO ``visibility`` key (omitted, NOT
      explicit None — codec contract at ``the_one/db/codec.py:63-67``).
    - ``messages_to_ui_events`` produces events where operator-derived
      events carry ``event["visibility"] == "operator"`` and peer-derived
      events have NO ``visibility`` key.

    This is the canonical example F5 will consult when implementing the
    Chat UI's visual distinction.

    F4 L4 update: the dispatcher's post-step visibility-tagging pass
    now tags the assistant reply with ``OPERATOR_VISIBILITY`` (default
    branch — plain-text assistant message is not a successful platform-
    send tool_result and not USER). Peer-visible (``visibility=None``)
    is preserved only for the inbound USER message (the USER-skip rule).

    M11 F7 L5: auto-relay is now invariant on engaged turns. To keep
    the F4 L4 operator-tagging branch fires unflipped here, we
    monkeypatch ``StubClient.send`` to a no-op that raises so the
    dispatcher's relay try/except swallows the failure and leaves the
    assistant message at ``OPERATOR_VISIBILITY``. The auto-relay-fires
    path (which DOES flip the assistant reply back to platform-visible)
    is covered by dedicated tests in
    ``tests/test_connectors_inbound.py``.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account()

    # Test isolation: suppress the platform-send side effect so the F4
    # L4 operator-tagging assertion survives. Raising forces the
    # dispatcher's swallow-and-keep-as-operator-only branch.
    from the_one.connectors._stub import StubClient as _StubClient

    async def _send_noop(self, target, content):
        raise RuntimeError("test isolation: relay suppressed")

    monkeypatch.setattr(_StubClient, "send", _send_noop)

    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope(text="from peer")

    # First inbound — creates the session + persists a peer USER message
    # (visibility=None) and an operator-tagged assistant reply (F4 L4).
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    sess = sessions[0]

    # Simulate F5's operator-input path by directly appending two
    # operator-tagged Messages (operator user prompt + operator-only
    # assistant reply) to the session's persisted history. F3 has no
    # operator-input UI yet; F5 will own the path. The codec round-trip
    # is the contract — leg 6 verifies it works.
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
    sess_updated = sess.model_copy(
        update={"messages": encode_messages(updated_history)}
    )
    await chat_repo.update(sess_updated)

    # Re-fetch + decode — the round-trip through the column is the test.
    sess_after = await chat_repo.get(sess.id)
    msgs = decode_messages(sess_after.messages)

    # Both visibility layers present.
    # - Operator: 1 from the F4 L4 dispatcher-tagged assistant reply
    #   + 2 we appended directly = 3 total.
    # - Peer (visibility=None): exactly the peer USER message (the only
    #   non-operator-tagged dispatcher output post-F4-L4).
    operator_msgs = [m for m in msgs if m.visibility == OPERATOR_VISIBILITY]
    peer_msgs = [m for m in msgs if m.visibility is None]
    assert len(operator_msgs) == 3
    assert len(peer_msgs) >= 1

    # Encoded JSON: operator-tagged dicts carry the key with value
    # ``"operator"``; peer-originated dicts do NOT carry the key
    # (omitted, NOT explicit None — codec contract verified at
    # ``the_one/db/codec.py:63-67``).
    parsed = json.loads(sess_after.messages)
    operator_count = sum(1 for d in parsed if d.get("visibility") == "operator")
    absent_count = sum(1 for d in parsed if "visibility" not in d)
    assert operator_count == 3
    assert absent_count >= 1
    # No peer-originated dict should carry the key with explicit None
    # or any other value — the codec MUST omit the key entirely when
    # source visibility is None. This guards against a regression where
    # a future change emits ``"visibility": null``.
    for d in parsed:
        if "visibility" in d:
            assert d["visibility"] == "operator"

    # messages_to_ui_events projects accordingly. Each operator-tagged
    # Message produces at least one event carrying
    # ``event["visibility"] == "operator"``; each peer-originated Message
    # produces events with NO ``visibility`` key. Lower bounds only —
    # tool_calls (if present) expand to additional events, and the mock
    # provider's reply may produce 1+ events per Message.
    events = messages_to_ui_events(msgs)
    operator_events = [e for e in events if e.get("visibility") == "operator"]
    absent_events = [e for e in events if "visibility" not in e]
    assert len(operator_events) >= 3
    assert len(absent_events) >= 1
    # Same null-key regression guard at the projection layer: no event
    # should carry ``"visibility": None`` (key absent is the contract).
    for e in events:
        if "visibility" in e:
            assert e["visibility"] == "operator"


# ─── Test 2 — session_metadata forward-compat for F7 ─────────────────────


async def test_e2e_session_metadata_column_round_trips_at_create_time(
    isolated_db,
) -> None:
    """Verify ``session_metadata`` holds non-trivial JSON at row creation.

    Forward-compat for F7's future routing-decision logs. F3 L1 added
    the column; this test pins the round-trip BEFORE F7 needs it. F7
    will own its update primitive (this leg only exercises create-time
    write + read).
    """
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)

    # Non-trivial dict: nested object + list, the two JSON shapes F7's
    # routing log is most likely to use.
    metadata = {"routing": {"rule": "default", "agent": "test"}, "audit": ["v1"]}
    new_session = ChatSession(
        id="test-meta-session-1",
        agent_name="agent-meta",
        title="meta-test",
        platform="stub",
        connector_id="acc-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        session_metadata=metadata,
        last_inbound_at="2026-05-17T12:00:00+00:00",
    )
    await chat_repo.create(new_session)
    fetched = await chat_repo.get("test-meta-session-1")
    assert fetched.session_metadata == metadata

    # None round-trip — the default state. Most non-connector sessions
    # (Chat UI direct, prior to F7) will store None here.
    new_session_none = ChatSession(
        id="test-meta-session-2",
        agent_name="agent-meta",
        title="meta-test-none",
        session_metadata=None,
    )
    await chat_repo.create(new_session_none)
    fetched_none = await chat_repo.get("test-meta-session-2")
    assert fetched_none.session_metadata is None


# ─── Test 3 — continuation window: real-time supersede ───────────────────


async def test_e2e_continuation_window_real_time_supersede(isolated_db) -> None:
    """Two inbounds with a real ``asyncio.sleep(2)`` between them, under
    a 1-second per-account continuation window, produce two distinct
    session rows.

    Distinct from leg 4's ``test_dispatch_inbound_creates_new_session_after_window``
    which fakes elapsed time via a stale ``last_inbound_at`` write. The
    wall-clock variant exercises real ``datetime.now()`` comparison and
    catches a ``datetime.now`` vs. ``utcnow`` regression that the faked
    test would miss. The 2-second sleep is intentional — the lightest
    possible exercise of the time-source code path.

    Uses the per-account ``session_continuation_seconds=1`` override
    (NOT the env var) to exercise the column path the leg 5 admin editor
    surfaces. Env-var path is covered by leg 3's resolver tests.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account(session_continuation_seconds=1)
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope(text="ping")

    # 1st inbound — creates session.
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1

    # Wall-clock sleep past the 1-second window — intentional. The
    # equivalent fake-elapsed-time test in leg 4 cannot exercise the
    # resolver's actual ``datetime.now()`` call.
    await asyncio.sleep(2)

    # 2nd inbound — should create a NEW session (window elapsed).
    await dispatch_inbound("acct-test", envelope, factory=factory)

    sessions = await chat_repo.list()
    assert len(sessions) == 2

    # Old row preserved (not deleted), distinct ids.
    ids = {s.id for s in sessions}
    assert len(ids) == 2

    # Both rows share the same external key (platform + account + channel
    # + thread) — the most-recent-within-window query is what
    # distinguishes them, not a key change.
    external_keys = {
        (s.platform, s.connector_id, s.channel_id, s.thread_id)
        for s in sessions
    }
    assert len(external_keys) == 1

    # Each row should have exactly one user turn (the inbound that
    # created it). Confirms the second inbound did NOT land in the
    # first session's history.
    for s in sessions:
        history = decode_messages(s.messages)
        user_msgs = [m for m in history if m.role == Role.USER]
        assert len(user_msgs) == 1
