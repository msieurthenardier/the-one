"""Neutral session-state registries.

Hosts cross-subsystem state that BOTH interfaces.web.app and
connectors._inbound need to coordinate on. Import direction is
one-way INTO this package; nothing here imports from interfaces
or connectors. F5 L2 introduced this module to close the
mission Known Issue about per-session lock unification.
"""
from the_one.sessions._broadcast import (
    add_subscriber,
    broadcast_to_session,
    clear_subscribers_for_test,
    remove_subscriber,
    subscribers_for,
)
from the_one.sessions._locks import (
    clear_locks_for_test,
    is_session_processing,
    session_locks,
)

__all__ = [
    "session_locks",
    "is_session_processing",
    "clear_locks_for_test",
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
