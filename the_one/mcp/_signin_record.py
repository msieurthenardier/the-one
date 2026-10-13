"""Leaf module: the DD1 sign-in record and the DD8 SSE cap constant.

Kept free of ``the_one.mcp.oauth`` / transport imports so ``MCPClient`` can read
the record without importing the transport (and, through it, the OAuth storage
chain - ``tests/test_imports.py`` pins that ``the_one.agent.core`` does not load
``the_one.mcp.oauth``). The transport re-exports these names.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Any

MAX_SSE_EVENT_BYTES = 1024 * 1024
"""The 1 MiB cap on one server-sent event (Mission 29, DD8).

Equal to the mcp 2.3.0 SDK default (``DEFAULT_MAX_SSE_EVENT_SIZE``) but passed
explicitly to ``streamable_http_client``, so a future SDK default change shows
up as a diff here (and in ``tests/test_mcp_transport_timeouts.py``) rather than
silently. An oversized event fails the request that was waiting on it with a
plain error (``MCPClient`` translates it).
"""


@dataclass
class AuthRecord:
    """Per-connection record of the MCP POST responses seen (DD1).

    ``seq`` counts MCP-POST responses; ``last_status`` is the status of the most
    recent one and ``last_resource_metadata`` the ``resource_metadata`` field of
    its ``WWW-Authenticate`` header when it was a 401. ``MCPClient`` captures
    ``seq`` when an operation starts and treats a failure as sign-in-required
    only if the most recent MCP-POST response after that baseline was a 401.
    """

    seq: int = 0
    last_status: int | None = None
    last_resource_metadata: str | None = None


# ClientSession -> its AuthRecord. 2.3.0's ClientSession defines no __eq__ or
# __slots__, so it is hashable and weakly referenceable; MCPClient._session
# keeps it alive for the connection's life.
_AUTH_RECORDS: "weakref.WeakKeyDictionary[Any, AuthRecord]" = weakref.WeakKeyDictionary()


def auth_record_for(session: Any | None) -> AuthRecord | None:
    """The :class:`AuthRecord` for ``session`` (None for a session this module
    did not open, e.g. a patched transport)."""
    if session is None:
        return None
    return _AUTH_RECORDS.get(session)


def saw_401_since(record: AuthRecord | None, baseline: int) -> bool:
    """True iff the most recent MCP-POST response after ``baseline`` was a 401.

    The one predicate behind ``MCPClient._auth_required_since`` and the
    negotiation shortcut (Mission 29 Flight 2). ``record`` None (stdio, a
    patched transport, a mock session) means "no 401".
    """
    return record is not None and record.seq > baseline and record.last_status == 401
