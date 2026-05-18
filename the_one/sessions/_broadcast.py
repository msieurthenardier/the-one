"""Shared per-session WebSocket subscriber registry + broadcast helper.

Pre-F5-L2 the Session dataclass in ``interfaces/web/app`` owned a
``subscribers: set[WebSocket]`` field and the broadcast helpers
iterated it directly. F5 L2 lifted the registry here so the F5 L6
dispatcher can broadcast inbound-driven UI events without an
``interfaces.web.app`` import. The Session dataclass no longer
carries the field; this module is the source of truth.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

# set[WebSocket] keyed by chat_sessions.id. defaultdict factory is
# set() — every read returns at minimum an empty set so the
# zero-subscriber broadcast path is a clean iteration over nothing.
_subscribers: defaultdict[str, set] = defaultdict(set)


def add_subscriber(session_id: str, ws: Any) -> None:
    _subscribers[session_id].add(ws)


def remove_subscriber(session_id: str, ws: Any) -> None:
    # discard, not remove — safe to call when the subscriber is
    # absent (lifecycle teardown calls this defensively).
    _subscribers[session_id].discard(ws)


def subscribers_for(session_id: str) -> set:
    """Return a SNAPSHOT copy of the subscriber set.

    Callers iterate the snapshot; mutating the live set during
    iteration (e.g. discarding a dead WS mid-broadcast) is the
    pre-F5 bug shape that lives in interfaces.web.app:562-570
    today. Snapshot semantics avoid it.
    """
    return set(_subscribers.get(session_id, ()))


async def broadcast_to_session(
    session_id: str,
    payload: dict[str, Any],
    *,
    exclude: Any = None,
) -> None:
    """Send a JSON payload to every WS subscriber of this session_id.

    Mirrors interfaces.web.app._send_to_session's semantics:
    dead-WS detection + discard. Zero subscribers → clean no-op.
    """
    dead: list = []
    for ws in subscribers_for(session_id):
        if ws is exclude:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        remove_subscriber(session_id, ws)


def clear_subscribers_for_test() -> None:
    _subscribers.clear()
