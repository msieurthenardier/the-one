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
re-send of a probe with no      ADDITION (sortie 19, only with ``patient_until``): an
answer, inside the window       inner loop inside one ``attempt``; it never uses up
                                ``attempt``. See "Patient probe" below.
-32022 on initialize after a    the SDK branch above unchanged: the window leaves
no-answer window, attempt 0     ``attempt`` at 0, so the re-probe at ``mutual[-1]``
                                still runs and a late-starting dual-era server ends
                                modern (the fallback is then ``None``)
discover result invalid         ``except ValidationError: initialize()``
no modern version in result     ``if not any(...): initialize()``
otherwise                       ``session.adopt(result)``
==============================  ==============================================

Departure from the SDK: only when the-one's sign-in record (``_signin_record``) shows
a 401 on discover. Without a record (stdio, mock sessions) the loop is the SDK's.

Additions over the SDK (DD2): when ``remembered`` is a handshake revision, call
``initialize()`` directly (no discover probe); if that fails with an ``MCPError``
and no 401 was seen since it began, run the full policy in the same call.

Patient probe (sortie 19, DD1-DD4): ``negotiate`` takes three more keywords, all
optional. ``patient_until`` is a loop-clock deadline (``None``: no patience, the
policy above exactly); ``outcome`` is a ``NegotiationOutcome`` the policy fills in;
``clock`` is the time source (default: the running loop's ``time``). With a deadline
a probe "got no answer" when ``send_discover`` raised ``MCPError`` ``REQUEST_TIMEOUT``
after at least ``the_one.mcp.PROBE_NO_ANSWER_FLOOR_SECONDS`` (a server may send that
code itself, at once, and that is an ordinary error), or when a re-sent probe was cut
off by the deadline. While the deadline has not passed the probe is sent again at the
same version; each re-sent probe is bounded by the time left. ``outcome.fallback`` is
``"no_answer"`` only when the last probe got no answer and the session ends on a
handshake revision.

Catches ``MCPError`` only: OAuth flow errors and exception groups propagate to
``MCPClient.connect``'s own ``except*`` arm.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from mcp.shared.exceptions import MCPError
from mcp.types import (
    REQUEST_TIMEOUT,
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


class NegotiationOutcome:
    """What ``negotiate`` learned beyond the revision (filled in by the policy).

    ``fallback`` is ``"no_answer"`` when the connection ended on a handshake revision
    because the last ``server/discover`` probe got no answer inside a patient window,
    else ``None``.
    """

    def __init__(self) -> None:
        self.fallback: str | None = None


class _ProbeState:
    """Whether the last probe got no answer (carried across the policy's ``continue``)."""

    def __init__(self) -> None:
        self.no_answer = False


async def _probe(
    session: Any,
    version: str,
    patient_until: float | None,
    clock: Callable[[], float],
    state: _ProbeState,
) -> Any:
    """Send ``server/discover``; return its raw result or raise the last ``MCPError``.

    With no deadline this is one plain ``send_discover`` (the SDK's own timeout) and
    ``state.no_answer`` stays False. With one, see the module docstring.
    """
    state.no_answer = False
    if patient_until is None:
        return await session.send_discover(version)
    from the_one import mcp as the_one_mcp  # read at call time: tests patch the floor

    first = True
    while True:
        state.no_answer = False
        sent_at = clock()
        try:
            left = patient_until - sent_at
            if first or left <= 0:
                # No bound of the policy's own, and that is safe: the first probe has
                # the SDK's own probe timeout; a re-send with no time left is still
                # under that timeout and the connect's outer limit, and the loop
                # ends after it because the deadline has passed.
                raw = await session.send_discover(version)
            else:
                cm = asyncio.timeout(left)
                try:
                    async with cm:
                        raw = await session.send_discover(version)
                except TimeoutError:
                    if not cm.expired():
                        raise  # the connect's own timeout, not ours
                    state.no_answer = True
                    raise MCPError(
                        REQUEST_TIMEOUT, "server/discover got no answer before the deadline"
                    ) from None
            state.no_answer = False
            return raw
        except MCPError as e:
            if state.no_answer:  # the deadline cut this probe off: the window is over
                raise
            if (
                e.code == REQUEST_TIMEOUT
                and clock() - sent_at >= the_one_mcp.PROBE_NO_ANSWER_FLOOR_SECONDS
            ):
                state.no_answer = True
                if clock() < patient_until:
                    first = False
                    continue
            raise


async def _full_policy(
    session: Any,
    patient_until: float | None = None,
    clock: Callable[[], float] | None = None,
    state: _ProbeState | None = None,
) -> None:
    version = _version.LATEST_MODERN_VERSION
    if clock is None:
        clock = asyncio.get_running_loop().time
    if state is None:
        state = _ProbeState()
    for attempt in range(2):
        # Fresh baseline per attempt: a 401 from attempt 0 must not count for 1.
        record = auth_record_for(session)
        baseline = record.seq if record is not None else 0
        try:
            raw = await _probe(session, version, patient_until, clock, state)
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


async def negotiate(
    session: Any,
    *,
    remembered: str | None,
    patient_until: float | None = None,
    outcome: NegotiationOutcome | None = None,
    clock: Callable[[], float] | None = None,
) -> str:
    """Negotiate the protocol era on ``session``; return ``session.protocol_version``."""
    state = _ProbeState()
    if remembered in _version.HANDSHAKE_PROTOCOL_VERSIONS:
        record = auth_record_for(session)
        baseline = record.seq if record is not None else 0
        try:
            await session.initialize()
        except MCPError:
            if saw_401_since(auth_record_for(session), baseline):
                raise
            await _full_policy(session, patient_until, clock, state)
    else:
        await _full_policy(session, patient_until, clock, state)
    if outcome is not None:
        handshake = session.protocol_version in _version.HANDSHAKE_PROTOCOL_VERSIONS
        outcome.fallback = (
            "no_answer" if patient_until is not None and state.no_answer and handshake else None
        )
    return session.protocol_version
