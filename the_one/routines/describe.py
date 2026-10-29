"""Plain-words descriptions of a routine's schedule, next run and target
(Mission 33 F2 L3, DD2/DD7).

The server-side twin of the browser's schedule wording, for ``list_my_routines`` and the
routine tools' results. Times are 12-hour wall-clock in the operator's zone, through the
``the_one.time_zones`` formatters. These strings go into tool results the model reads, so
they NEVER include a chat title or channel name (titles derive from conversation content):
a target reads "this chat", "chat {id}", "a new chat each run" or "its own chat".
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from typing import Any

from the_one import time_zones
from the_one.routines import recurrence_text
from the_one.routines import schedule as routine_schedule


def _clock(local: datetime) -> str:
    return time_zones._clock(local)


def _short_date(local: datetime) -> str:
    return (
        f"{time_zones._WEEKDAYS[local.weekday()]}, "
        f"{time_zones._MONTHS[local.month - 1]} {local.day}, {local.year}"
    )


def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return routine_schedule.parse_utc(raw)
    except Exception:  # noqa: BLE001
        return None


def schedule_sentence(schedule: Any, anchor_at: str | None, zone: tzinfo) -> str | None:
    """The schedule as one sentence, or None when it cannot be read (a schedule v48 could
    not upgrade, or a hand-edited row): the views and tools never fail over it."""
    try:
        return recurrence_text.describe(schedule, _parse(anchor_at), zone)
    except Exception:  # noqa: BLE001
        return None


def describe_next(next_run_at: str | None, zone: tzinfo, *, now: datetime | None = None) -> str:
    """The next run as ``today 3:40 PM`` / ``tomorrow 9:00 AM`` / a dated form."""
    at = _parse(next_run_at)
    if at is None:
        return "no run scheduled"
    now = now or time_zones.utcnow()
    local = at.astimezone(zone)
    today = now.astimezone(zone).date()
    if local.date() == today:
        return f"today {_clock(local)}"
    if local.date() == today + timedelta(days=1):
        return f"tomorrow {_clock(local)}"
    return f"{_short_date(local)} at {_clock(local)}"


def describe_target(routine_or_payload: Any, current_session_id: str | None) -> str:
    """``this chat`` / ``chat {id}`` / ``a new chat each run`` / ``its own chat``."""
    if isinstance(routine_or_payload, dict):
        target = routine_or_payload.get("target", routine_or_payload)
        kind = target.get("kind") or target.get("target_kind")
        sid = target.get("session_id") or target.get("target_session_id")
    else:
        kind = getattr(routine_or_payload, "target_kind", None)
        sid = getattr(routine_or_payload, "target_session_id", None)
    if kind == "new":
        return "a new chat each run"
    if kind == "own":
        return "its own chat"
    if kind == "chat" and sid:
        return "this chat" if sid == current_session_id else f"chat {sid}"
    # An own-chat routine that has run already points at its chat; the kind still wins above.
    return "a chat"
