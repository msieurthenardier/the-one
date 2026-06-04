"""Tests for the `list_sessions` WS action's per-row projection (M10 F05 L01).

Covers `_session_to_list_payload` — the helper extracted from the WS action's
inline list-comprehension. The helper is the contract surface for what
`session_list` payloads carry to the chat sidebar; this test pins:

  - The pre-F5 five-field shape (id, title, agent_name, created_at,
    updated_at) is preserved byte-identically for non-connector sessions.
  - The six new connector-keying fields (platform, connector_id,
    channel_id, thread_id, peer_id, last_inbound_at) are projected for
    connector-bound sessions.
  - All six new fields are ``None`` for non-connector (web-native) sessions
    — back-compat with pre-F5 clients that ignore unknown keys.
  - ``session_metadata`` and ``messages`` are NOT projected — regression net
    against future implementers over-eagerly adding every field
    (``messages`` would balloon the payload; ``session_metadata`` may carry
    sensitive routing data the client shouldn't see unfiltered).
"""

from __future__ import annotations

from the_one.db.models import ChatSession
from the_one.interfaces.web.app import _session_to_list_payload

# Connector-keying fields surfaced by the F5 projection extension. Pinned as
# a constant so future-leg additions (e.g. F6 surfacing
# ``session_metadata``) are forced through a deliberate test edit rather
# than silently passing.
F5_NEW_FIELDS = (
    "platform",
    "connector_id",
    "channel_id",
    "thread_id",
    "peer_id",
    "last_inbound_at",
)

# Pre-F5 fields — the byte-identical projection for non-connector rows.
PRE_F5_FIELDS = (
    "id",
    "title",
    "agent_name",
    "created_at",
    "updated_at",
)


def test_projects_pre_f5_fields_unchanged_for_web_native_session() -> None:
    """A web-native session's projection carries the pre-F5 five fields
    with the exact values from the DB row.
    """
    s = ChatSession(
        id="sess-web-1",
        agent_name="default",
        title="Hello world",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-02T00:00:00Z",
    )
    payload = _session_to_list_payload(s)

    assert payload["id"] == "sess-web-1"
    assert payload["title"] == "Hello world"
    assert payload["agent_name"] == "default"
    assert payload["created_at"] == "2026-05-01T00:00:00Z"
    assert payload["updated_at"] == "2026-05-02T00:00:00Z"


def test_projects_connector_keying_fields_as_none_for_web_native_session() -> None:
    """A web-native session has all six new fields defaulting to ``None``.

    Back-compat with pre-F5 clients: the keys are present (so the wire
    contract is stable) but carry no value to render.
    """
    s = ChatSession(id="sess-web-2", agent_name="default", title="No connector")
    payload = _session_to_list_payload(s)

    for field in F5_NEW_FIELDS:
        assert field in payload, f"missing connector-keying field: {field}"
        assert payload[field] is None, (
            f"web-native session must project {field}=None; got {payload[field]!r}"
        )


def test_projects_connector_keying_fields_for_connector_bound_session() -> None:
    """A connector-bound session projects all six new fields with the row's
    values.
    """
    s = ChatSession(
        id="sess-conn-1",
        agent_name="connector-agent",
        title="From stub",
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
        platform="stub",
        connector_id="acct-1",
        channel_id="C1",
        thread_id="T1",
        peer_id="P1",
        last_inbound_at="2026-01-01T00:00:00Z",
    )
    payload = _session_to_list_payload(s)

    assert payload["platform"] == "stub"
    assert payload["connector_id"] == "acct-1"
    assert payload["channel_id"] == "C1"
    assert payload["thread_id"] == "T1"
    assert payload["peer_id"] == "P1"
    assert payload["last_inbound_at"] == "2026-01-01T00:00:00Z"


def test_does_not_project_session_metadata_or_messages() -> None:
    """``session_metadata`` and ``messages`` MUST NOT appear in the payload.

    ``session_metadata`` is free-form dict content with no F5 consumer and
    may carry sensitive routing data we shouldn't expose unfiltered.
    ``messages`` would balloon the per-row payload — the WS contract is a
    list of *headers*, not bodies.
    """
    s = ChatSession(
        id="sess-conn-2",
        agent_name="connector-agent",
        title="Has metadata",
        platform="stub",
        connector_id="acct-1",
        channel_id="C1",
        session_metadata={"secret_routing_key": "do-not-leak"},
        messages='[{"role":"user","content":"hi"}]',
    )
    payload = _session_to_list_payload(s)

    assert "session_metadata" not in payload, (
        "session_metadata leaks free-form routing/auth content; do NOT project"
    )
    assert "messages" not in payload, (
        "messages is the session body, not a sidebar row header — do NOT project"
    )


def test_projection_shape_is_exactly_eleven_keys() -> None:
    """Pin the wire contract to the eleven documented keys. A new key
    appearing here forces a deliberate edit to this test (and a
    corresponding leg/flight design decision) rather than landing
    silently.
    """
    s = ChatSession(
        id="sess-pin",
        agent_name="default",
        title="Pin",
        platform="stub",
        connector_id="acct-1",
        channel_id="C1",
        thread_id="T1",
        peer_id="P1",
        last_inbound_at="2026-01-01T00:00:00Z",
        session_metadata={"k": "v"},
    )
    payload = _session_to_list_payload(s)

    expected_keys = set(PRE_F5_FIELDS) | set(F5_NEW_FIELDS)
    assert set(payload.keys()) == expected_keys, (
        f"projection shape drift — got {sorted(payload.keys())}, expected {sorted(expected_keys)}"
    )
