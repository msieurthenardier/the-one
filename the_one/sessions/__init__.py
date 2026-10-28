"""Neutral session-state registries.

Hosts cross-subsystem state that ``interfaces.web.app`` (and, before
Mission 23 Flight 1 deleted the connector package, the connector
dispatcher's inbound handler) need to coordinate on. Import direction
is one-way INTO this package; nothing here imports from interfaces.
F5 L2 introduced this module to close the mission Known Issue about
per-session lock unification.
"""

from the_one.sessions._broadcast import (
    add_socket,
    add_subscriber,
    all_sockets,
    broadcast_to_all,
    broadcast_to_session,
    clear_subscribers_for_test,
    remove_socket,
    remove_subscriber,
    subscribers_for,
)
from the_one.sessions._locks import (
    clear_locks_for_test,
    is_session_busy,
    is_session_processing,
    session_locks,
    track_turn,
    turn_seq,
)

__all__ = [
    "session_locks",
    "is_session_processing",
    "is_session_busy",
    "track_turn",
    "turn_seq",
    "clear_locks_for_test",
    "add_socket",
    "remove_socket",
    "all_sockets",
    "broadcast_to_all",
    "add_subscriber",
    "remove_subscriber",
    "subscribers_for",
    "broadcast_to_session",
    "clear_subscribers_for_test",
    "clear_for_test",
]


def clear_for_test() -> None:
    """Convenience for autouse fixtures — clears both registries."""
    clear_locks_for_test()
    clear_subscribers_for_test()
