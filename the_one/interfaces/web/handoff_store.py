"""The one-time browser-handoff credential store.

Mission 20 / Flight 1 / Leg 2 (`gate-middleware`) — DD7, DD12, LD2.

**Do not confuse this with the long-lived credential** in
`the_one/api_credential.py`. That one is a file, persists across restarts,
and authenticates every non-browser caller. This one is a small in-memory,
per-process object: a handoff value is minted, presented exactly once on a
document request, and burned — see DD12 in the flight spec for the full
policy this module implements (single-use, TTL, per-process, no
persistence).

Two mint call sites land in the same store (LD2):
  - `mint_handoff_credential()` below — called directly, in-process, by the
    desktop launcher (which shares a process with the server; see the leg
    artifact's Reconnaissance Findings #1). **This is the pinned name and
    module `operational-callers` wires the launcher to** — do not rename
    without updating that leg's design.
  - `POST /api/session/handoff` in `the_one/interfaces/web/app.py`, for
    callers that hold the long-lived credential but run outside this
    process (the browser-test harness, the behavior-test runner).

Consumption happens inside `CredentialGateMiddleware`
(`the_one/interfaces/web/middleware.py`), which is the only reader.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

# The query parameter name the gate middleware looks for on a document
# request (LD1's third channel). An "acceptable variation" per the flight
# spec — no other code depends on this exact string except the gate and the
# mint endpoint, both of which import it from here.
HANDOFF_QUERY_PARAM = "handoff"

# Generous on purpose (DD12: "choose the TTL generously; failure mode is a
# relaunch, not a lockout") — minutes, not seconds, so a launcher that is
# slow to open the URL (cold start, slow disk) does not race it.
DEFAULT_TTL_SECONDS = 300.0

_TOKEN_NBYTES = 32  # 64 hex chars — independent of the long-lived credential's shape


@dataclass
class _HandoffEntry:
    issued_at: float
    consumed: bool = False


class HandoffStore:
    """A small explicit object with an injected clock (leg Implementation
    Guidance #5) — deliberately not module-level globals with `time.time()`
    inline, so the TTL and single-use tests can control time without
    `time.sleep`.

    Per-process only: nothing here is written to disk. A fresh instance
    (standing in for a restarted process, per the leg's acceptance
    criteria) starts with an empty store — it neither recognises an
    outstanding value minted by another instance nor can it resurrect one
    that instance had already consumed.

    Thread-safe: the desktop launcher runs uvicorn on a daemon thread in
    its own process (leg Reconnaissance Findings #1), so `consume()` must
    be atomic under concurrent requests racing the same token (leg Edge
    Cases: "Concurrent consumption of one handoff credential").
    """

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, _HandoffEntry] = {}

    def mint(self) -> str:
        """Issue a fresh one-time handoff token, outstanding and unconsumed."""
        token = secrets.token_hex(_TOKEN_NBYTES)
        with self._lock:
            self._entries[token] = _HandoffEntry(issued_at=self._clock())
        return token

    def consume(self, token: str) -> bool:
        """Attempt to spend *token*. Returns ``True`` at most once per token
        — the single call that finds it outstanding, unexpired, and unspent.
        Every other call (unknown token, already-consumed, expired) returns
        ``False`` and has no side effect.

        The check-and-mark happens under the lock in one critical section,
        so two requests racing the same token cannot both observe ``True``.
        """
        with self._lock:
            entry = self._entries.get(token)
            if entry is None or entry.consumed:
                return False
            if self._clock() - entry.issued_at > self._ttl_seconds:
                return False
            entry.consumed = True
            return True


# Process-local default store, shared by the in-process mint function, the
# `/api/session/handoff` mint endpoint, and (once `enforce-and-migrate-
# harness` registers it) the gate middleware's default construction. Tests
# that need TTL/clock control or store-isolation construct their own
# `HandoffStore` instance directly rather than using this singleton.
_default_store = HandoffStore()


def get_default_handoff_store() -> HandoffStore:
    """Return the process-wide default `HandoffStore` instance."""
    return _default_store


def mint_handoff_credential() -> str:
    """Mint a fresh one-time handoff token in the default per-process store
    and return the raw token string.

    **Pinned name and module** (leg Implementation Guidance #7): this is
    the in-process function the desktop launcher calls directly, with no
    IPC and no HTTP hop — `operational-callers` wires `shell.py`'s
    server-start block to this exact call. Callers that need a full URL
    build it themselves: ``f"{base_url}?{HANDOFF_QUERY_PARAM}={token}"``.
    """
    return _default_store.mint()
