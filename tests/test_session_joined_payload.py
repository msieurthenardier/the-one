"""Builder-level assertions: session_joined payloads carry session_metadata.last_usage.

M16 F06 L02 — verifies that both _build_session_joined_ok and
_build_session_joined_degraded surface session_metadata["last_usage"] when the
source carries it.

The full restart round-trip (drop in-memory session → DB reload →
_restore_session) is L03's scope. These tests are cheap builder-level checks
that confirm the carry — no DB setup required for the ok path; the degraded
path uses an in-memory ChatSessionModel instance directly (the builder reads
db.session_metadata without hitting the DB).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from the_one.db.models import ChatSession as ChatSessionModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeAgent:
    """Minimal stand-in for the_one.agent.Agent — only the bits Session uses."""

    def __init__(self) -> None:
        self.messages = []


def _make_session(session_id: str = "s-payload-test", session_metadata=None):
    from the_one.interfaces.web.app import Session

    return Session(
        id=session_id,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        created=datetime.now(timezone.utc).isoformat(),
        session_metadata=session_metadata,
    )


_LAST_USAGE = {
    "input_tokens": 120,
    "output_tokens": 45,
    "context_tokens": 980,
}


# ---------------------------------------------------------------------------
# _build_session_joined_ok
# ---------------------------------------------------------------------------


class TestSessionJoinedOkCarriesLastUsage:
    """`_build_session_joined_ok` surfaces session_metadata.last_usage."""

    def test_last_usage_present(self) -> None:
        from the_one.interfaces.web.app import _build_session_joined_ok

        metadata = {"last_usage": _LAST_USAGE, "routing": []}
        s = _make_session(session_metadata=metadata)
        payload = _build_session_joined_ok(s)

        assert payload["session_metadata"] is not None
        assert payload["session_metadata"]["last_usage"] == _LAST_USAGE

    def test_last_usage_absent_when_metadata_none(self) -> None:
        """Fresh sessions with no metadata produce None session_metadata
        in the payload — no last_usage key at all (not just missing value)."""
        from the_one.interfaces.web.app import _build_session_joined_ok

        s = _make_session(session_metadata=None)
        payload = _build_session_joined_ok(s)

        assert payload["session_metadata"] is None

    def test_last_usage_absent_when_key_missing(self) -> None:
        """session_metadata present but without last_usage (e.g. routing-only)
        — payload carries the metadata dict but no last_usage key."""
        from the_one.interfaces.web.app import _build_session_joined_ok

        metadata = {"routing": []}
        s = _make_session(session_metadata=metadata)
        payload = _build_session_joined_ok(s)

        assert payload["session_metadata"] is not None
        assert "last_usage" not in payload["session_metadata"]


# ---------------------------------------------------------------------------
# _build_session_joined_degraded
# ---------------------------------------------------------------------------


class TestSessionJoinedDegradedCarriesLastUsage:
    """`_build_session_joined_degraded` surfaces db.session_metadata.last_usage."""

    async def test_last_usage_present(self) -> None:
        from the_one.interfaces.web.app import (
            SESSION_STATUS_AGENT_DELETED,
            RestoredSession,
            _build_session_joined_degraded,
        )

        metadata = {"last_usage": _LAST_USAGE}
        db_row = ChatSessionModel(
            id="s-degraded-payload",
            agent_name="test-agent",
            session_metadata=metadata,
        )
        restored = RestoredSession(None, SESSION_STATUS_AGENT_DELETED, db_row)

        # _build_session_joined_degraded calls _merge_pending_approvals_into_history
        # which does a DB query. Patch it to return the empty history directly.
        with patch(
            "the_one.interfaces.web.app._merge_pending_approvals_into_history",
            return_value=[],
        ):
            payload = await _build_session_joined_degraded(restored)

        assert payload["session_metadata"] is not None
        assert payload["session_metadata"]["last_usage"] == _LAST_USAGE

    async def test_last_usage_absent_when_metadata_none(self) -> None:
        """Degraded session with no metadata — payload carries None session_metadata."""
        from the_one.interfaces.web.app import (
            SESSION_STATUS_AGENT_DELETED,
            RestoredSession,
            _build_session_joined_degraded,
        )

        db_row = ChatSessionModel(
            id="s-degraded-no-meta",
            agent_name="test-agent",
            session_metadata=None,
        )
        restored = RestoredSession(None, SESSION_STATUS_AGENT_DELETED, db_row)

        with patch(
            "the_one.interfaces.web.app._merge_pending_approvals_into_history",
            return_value=[],
        ):
            payload = await _build_session_joined_degraded(restored)

        assert payload["session_metadata"] is None
