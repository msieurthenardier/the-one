"""``inbound.is_continuable`` (M33 F1 L4, AC12)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from the_one.connectors.inbound import is_continuable
from the_one.db.models import ChatSession

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)


def row(last: str | None, meta: dict | None = None) -> ChatSession:
    return ChatSession(id="s", last_inbound_at=last, session_metadata=meta)


def test_fresh_is_continuable():
    assert is_continuable(row((NOW - timedelta(seconds=10)).isoformat()), 60, NOW)


def test_stale():
    assert not is_continuable(row((NOW - timedelta(seconds=60)).isoformat()), 60, NOW)


def test_ended():
    assert not is_continuable(row(NOW.isoformat(), {"ended_at": "x"}), 60, NOW)


def test_missing_and_unparsable():
    assert not is_continuable(row(None), 60, NOW)
    assert not is_continuable(row("not a date"), 60, NOW)


def test_naive_reads_as_utc():
    naive = (NOW - timedelta(seconds=5)).replace(tzinfo=None).isoformat()
    assert is_continuable(row(naive), 60, NOW)
