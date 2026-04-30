"""Shared PTY-session test helpers (F4 L6 promotion).

Promoted from ``tests/test_session_registry.py`` so multiple test modules
(``test_session_registry``, ``test_session_tools``) can import the mock
without cross-test-module imports — pytest's collection ordering makes
``from tests.test_session_registry import ...`` fragile (the importing
module's collection can run before the source module is itself imported,
masking the symbol).

Underscore prefix (``_pty_fixtures``) keeps pytest from picking this file
up as a test module — it has no ``test_*`` functions.
"""

from __future__ import annotations

import time

from the_one.platform.pty import PtySession


class MockPtySession(PtySession):
    """In-memory ``PtySession`` for unit tests.

    NOTE: ``is_alive`` and ``last_activity`` MUST be ``@property``
    accessors. ``PtySession`` declares them as ``@property
    @abstractmethod`` — class-level attributes do NOT satisfy abstract
    property descriptors, and ``MockPtySession()`` would raise
    ``TypeError`` at instantiation.
    """

    def __init__(self, last_activity: float | None = None) -> None:
        self._alive = True
        self._last_activity = (
            last_activity if last_activity is not None else time.monotonic()
        )
        self.close_count = 0
        # Test purchase: record what the tool layer wrote into ``send``.
        self.sent: list[tuple[str, float]] = []
        # Optional canned output; tests can override to drive specific
        # ``shell_session_send`` flows without spawning a real PTY.
        self.send_response: bytes = b""

    async def start(self) -> None:  # pragma: no cover — unused in unit tests
        pass

    async def send(
        self, input: str, timeout: float = 30.0  # noqa: A002
    ) -> bytes:
        self.sent.append((input, timeout))
        return self.send_response

    async def close(self) -> None:
        self.close_count += 1
        self._alive = False

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def last_activity(self) -> float:
        return self._last_activity
