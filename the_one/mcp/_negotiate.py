"""Connect-time protocol negotiation (Mission 29 Flight 2, DD1).

``negotiate`` replaces the bare ``session.initialize()`` in ``MCPClient.connect``.
It re-implements mcp 2.3.0's private SDK function ``negotiate_auto`` on
the PUBLIC ``ClientSession`` API (``send_discover`` / ``initialize`` / ``adopt``),
so the-one depends on no private SDK module. Branch map (SDK line = the branch in
``negotiate_auto`` this mirrors; ``tests/test_mcp_negotiate.py`` names its parity
cases after these, and a drift test runs both against the same scripted sessions):

==============================  ==============================================
this module                     SDK ``negotiate_auto``
==============================  ==============================================
discover loop, ``attempt`` 0/1  ``for attempt in range(2)``
-32022 mutual modern, attempt 0 ``if mutual and attempt == 0: version = ...``
-32022 disjoint modern-only     ``if supported is not None and not any(...): raise``
-32022 unparseable / other code ``try: await session.initialize()`` (denylist)
initialize answers -32022       ``handshake_exc.code != ... or attempt != 0: raise``
                                else re-probe at ``mutual[-1]``
discover 401 in the sign-in     DEPARTURE: still try ``initialize()``; if that fails
record (any code, checked first) with an MCPError, raise ``DiscoverSignInRequired``
                                (SDK would fall back and lose the 401). If it
                                succeeds the handshake era is kept, as in the SDK.
non-MCPError from discover      propagates (no ``except`` for it)
discover result invalid         ``except ValidationError: initialize()``
no modern version in result     ``if not any(...): initialize()``
otherwise                       ``session.adopt(result)``
==============================  ==============================================

Departure from the SDK: only when the-one's sign-in record (``_signin_record``) shows
a 401 on discover. Without a record (stdio, mock sessions) the loop is the SDK's.

Additions over the SDK (DD2): when ``remembered`` is a handshake revision, call
``initialize()`` directly (no discover probe); if that fails with an ``MCPError``
and no 401 was seen since it began, run the full policy in the same call.

Catches ``MCPError`` only: OAuth flow errors and exception groups propagate to
``MCPClient.connect``'s own ``except*`` arm.
"""

from __future__ import annotations

from typing import Any

from mcp.shared.exceptions import MCPError
from mcp.types import (
    UNSUPPORTED_PROTOCOL_VERSION,
    DiscoverResult,
    UnsupportedProtocolVersionErrorData,
)
from mcp.types import version as _version
from pydantic import ValidationError

from the_one.mcp._signin_record import auth_record_for, saw_401_since


def _parse_supported(data: Any) -> list[str] | None:
    """``data.supported`` of a -32022 error, or None when it is not actionable."""
    try:
        return UnsupportedProtocolVersionErrorData.model_validate(data).supported
    except ValidationError:
        return None


def _mutual_modern(supported: list[str] | None) -> list[str]:
    return [v for v in _version.MODERN_PROTOCOL_VERSIONS if v in (supported or ())]


class DiscoverSignInRequired(Exception):  # noqa: N818  (control-flow marker)
    """Discover was answered 401 and the handshake fallback then failed too.

    Carries the ``resource_metadata`` URL captured when the 401 was seen, so
    ``MCPClient`` can raise ``MCPAuthRequired`` (the later handshake failure
    overwrote the sign-in record's last status).
    """

    def __init__(self, resource_metadata_url: str | None) -> None:
        super().__init__("server/discover was answered 401 (sign-in required)")
        self.resource_metadata_url = resource_metadata_url


async def _full_policy(session: Any) -> None:
    version = _version.LATEST_MODERN_VERSION
    for attempt in range(2):
        # Fresh baseline per attempt: a 401 from attempt 0 must not count for 1.
        record = auth_record_for(session)
        baseline = record.seq if record is not None else 0
        try:
            raw = await session.send_discover(version)
        except MCPError as e:
            deferred: DiscoverSignInRequired | None = None
            record = auth_record_for(session)
            if saw_401_since(record, baseline):
                # The record is the authority (checked before -32022, even when the
                # 401's JSON-RPC body carries that code): capture the challenge now,
                # because a failing initialize() overwrites ``last_status``.
                deferred = DiscoverSignInRequired(
                    record.last_resource_metadata if record is not None else None
                )
            elif e.code == UNSUPPORTED_PROTOCOL_VERSION:
                supported = _parse_supported(e.error.data)
                mutual = _mutual_modern(supported)
                if mutual and attempt == 0:
                    version = mutual[-1]
                    continue
                if supported is not None and not any(
                    v in _version.HANDSHAKE_PROTOCOL_VERSIONS for v in supported
                ):
                    raise  # modern-only server, no shared version
            try:
                await session.initialize()
            except MCPError as handshake_exc:
                if deferred is not None:
                    raise deferred from handshake_exc
                if handshake_exc.code != UNSUPPORTED_PROTOCOL_VERSION or attempt != 0:
                    raise
                mutual = _mutual_modern(_parse_supported(handshake_exc.error.data))
                if not mutual:
                    raise
                version = mutual[-1]
                continue
            return
        try:
            result = DiscoverResult.model_validate(raw)
        except ValidationError:
            await session.initialize()
            return
        if not any(v in result.supported_versions for v in _version.MODERN_PROTOCOL_VERSIONS):
            await session.initialize()
            return
        session.adopt(result)
        return
    raise AssertionError("unreachable")  # pragma: no cover


async def negotiate(session: Any, *, remembered: str | None) -> str:
    """Negotiate the protocol era on ``session``; return ``session.protocol_version``."""
    if remembered in _version.HANDSHAKE_PROTOCOL_VERSIONS:
        record = auth_record_for(session)
        baseline = record.seq if record is not None else 0
        try:
            await session.initialize()
        except MCPError:
            if saw_401_since(auth_record_for(session), baseline):
                raise
            await _full_policy(session)
    else:
        await _full_policy(session)
    return session.protocol_version
