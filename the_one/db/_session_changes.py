"""In-process signal: "what the Chats list shows has changed".

A leaf module (stdlib only). The chat-session repositories call
:func:`notify_sessions_changed` after a committed write that changes a
row the Chats list shows; the web app's lifespan registers one listener
that coalesces the signals and pushes the list to connected sockets.
With no listener registered (unit tests, the CLI) a notify is a no-op.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_listeners: list[Callable[[], None]] = []


def add_listener(fn: Callable[[], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def remove_listener(fn: Callable[[], None]) -> None:
    try:
        _listeners.remove(fn)
    except ValueError:
        pass


def notify_sessions_changed() -> None:
    """Call every listener; never raises."""
    for fn in list(_listeners):
        try:
            fn()
        except Exception:
            logger.exception("sessions-changed listener failed")


def clear_for_test() -> None:
    _listeners.clear()
