"""End-to-end test for M10 F5 L4 — WS write path into a connector-attached
session, exercising the full encode/decode round-trip.

Pins the leg's persistence contract: when an operator types into a
connector-attached session via the Chat UI WS path, the persisted
``chat_sessions.messages`` blob carries the F3-codec-visible
``visibility="operator"`` tag on the new USER message and the agent's
post-step messages — EXCEPT the successful platform-send tool_result,
which stays peer-visible (``visibility=None``).

Distinct from the unit tests in
``test_ws_storage_edge_shim_visibility.py``: this file drives the
storage edge AND the round-trip back through the codec/DB layer, so
the assertions hit decoded ``Message`` instances re-fetched from the
DB. The unit tests pin the in-memory contract; this pins the
persisted contract.

Fixture pattern mirrors ``tests/test_connectors_e2e_session.py`` /
``tests/test_connectors_e2e_platform_send.py`` — per-file autouse
cleanup of the pool + lock registry + connector registry, plus the
shared ``isolated_db`` fixture from ``tests/conftest.py``.
"""

from __future__ import annotations

import pytest

from tests._connector_dispatch_helpers import (
    _make_scripted_factory,
    _seed_provider_and_agent,
    _seed_stub_account,
)
from the_one.connectors import OPERATOR_VISIBILITY
from the_one.connectors import _inbound as inbound_mod
from the_one.connectors import _pool as pool_mod
from the_one.connectors._stub import StubPlugin
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    _get_or_restore_session,
    _spawn_message_processing,
)
from the_one.llm.base import Message, Role
from the_one.sessions import clear_for_test as _clear_session_registry

# ─── Autouse cleanup ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level recording buffers around each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_locks_registry():
    """Empty pool + per-session lock dict + registry between tests.

    Same shape as ``tests/test_connectors_e2e_session.py``. Also clears
    the web-app's in-memory session cache so a stale ``Session`` doesn't
    leak across tests.
    """
    yield
    await pool_mod._clear_for_test()
    await inbound_mod._clear_for_test()
    _clear_session_registry()
    _registry_clear_for_test()
    restore_to_baseline_for_test()
    web_app._sessions.clear()


# ─── E2E: WS write path into connector-attached session ─────────────────


async def test_e2e_ws_typed_message_into_connector_session_tags_visibility(
    isolated_db, monkeypatch
) -> None:
    """Operator types into a connector-attached session via the WS path;
    persisted history carries ``visibility="operator"`` on the new USER
    message and the assistant reply.

    Full round-trip:
    - Seed a connector-attached ``chat_sessions`` row (``platform="stub"``).
    - ``_get_or_restore_session`` populates ``Session.platform``.
    - ``_spawn_message_processing`` drives ``_process_and_broadcast``
      under the shared lock; the shim tags new messages.
    - Re-fetch the row and decode — the persisted blob carries the
      operator tag.

    Also stubs the broadcast sink + Ollama auto-load so the test does
    not require a live WS subscriber.
    """
    await _seed_provider_and_agent(connector_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Stub broadcast + ollama auto-load so the WS handler can run without
    # a live subscriber. Save-to-DB is the path under test — DO NOT stub
    # it.
    async def _noop(*args, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(web_app, "_send_to_session", _noop)
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop)

    # Seed a connector-attached chat_sessions row with platform="stub".
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    session_id = "cs-e2e-ws-conn"
    db_row = ChatSession(
        id=session_id,
        agent_name="agent-inbound",
        title="connector session",
        platform="stub",
        connector_id="acct-test",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        messages="[]",
    )
    await chat_repo.create(db_row)

    # Build a scripted factory that returns a single plain assistant reply.
    factory = await _make_scripted_factory(
        [Message.assistant(content="operator-visible reply")],
        monkeypatch,
    )
    # Point the web app's factory at our scripted factory so
    # ``_restore_session`` builds the connector-attached agent against it.
    web_app._state["factory"] = factory

    # Restore the session — this populates Session.platform from the DB row.
    restored = await _get_or_restore_session(session_id)
    assert restored.session is not None, "restore should succeed for seeded row"
    assert restored.session.platform == "stub", (
        f"Session.platform should mirror the DB row's platform; "
        f"got {restored.session.platform!r}"
    )

    # Drive the WS-typed input through the spawn helper — the same call
    # site the WS receive loop uses.
    await _spawn_message_processing(
        restored.session,
        "operator types here",
        source="web",
        exclude_user_echo=None,
    )

    # Re-fetch + decode the persisted blob. The shim must have tagged
    # the USER + assistant messages with OPERATOR_VISIBILITY in memory
    # AND the codec must have persisted that tag.
    refreshed = await chat_repo.get(session_id)
    decoded = decode_messages(refreshed.messages)

    user_msgs = [m for m in decoded if m.role == Role.USER]
    assert user_msgs, "expected at least one USER message in persisted history"
    # The newly-typed operator USER carries the operator tag.
    operator_user = [m for m in user_msgs if m.content == "operator types here"]
    assert operator_user, "operator USER message not found in persisted history"
    for m in operator_user:
        assert m.visibility == OPERATOR_VISIBILITY, (
            "operator-typed USER must persist with visibility=operator"
        )

    # Assistant reply ALSO carries the operator tag (default branch of
    # the leg-3 helper — it's not a successful platform-send tool_result).
    asst_msgs = [m for m in decoded if m.role == Role.ASSISTANT]
    asst_reply = [m for m in asst_msgs if m.content == "operator-visible reply"]
    assert asst_reply, "expected the scripted assistant reply in persisted history"
    for m in asst_reply:
        assert m.visibility == OPERATOR_VISIBILITY, (
            "assistant reply on a connector-attached session must persist "
            "with visibility=operator"
        )
