"""Mission 29 Flight 2 leg 2 (pass 2a): ``negotiate`` (DD1/DD2), era memory wiring
in ``MCPClient.connect`` (DD2), era-agnostic ``_meta`` (DD3) and the version gate
(DD4), driven through scripted/mock sessions. Real-server fixtures are pass 2b."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from asgi_lifespan import LifespanManager
from mcp import types as mcp_types
from mcp.shared.exceptions import MCPError, UrlElicitationRequiredError
from mcp.types.version import LATEST_MODERN_VERSION

from tests.fixtures.mcp.asgi_401 import Auth401Wrapper
from tests.fixtures.mcp.hello_server import make_http_app
from tests.test_mcp_client import _make_init_result, _set_init, _stdio_source
from the_one.db.models import MCPSource
from the_one.mcp import _era, _negotiate
from the_one.mcp import _signin_record as sr
from the_one.mcp import client as client_mod
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPConnectionError, MCPVersionMismatch
from the_one.mcp.transports import streamable_http as sh

METHOD_NOT_FOUND = MCPError(mcp_types.METHOD_NOT_FOUND, "Method not found")
INVALID_PARAMS = MCPError(-32602, "Invalid params")
MODERN = "2026-07-28"
HS = "2025-11-25"


def _unsupported(supported, requested=MODERN) -> MCPError:
    return MCPError(-32022, "unsupported", {"supported": supported, "requested": requested})


def _discover_result(versions=(MODERN,), meta=None) -> mcp_types.DiscoverResult:
    return mcp_types.DiscoverResult(
        supported_versions=list(versions),
        capabilities=mcp_types.ServerCapabilities(tools=mcp_types.ToolsCapability()),
        _meta=meta,
    )


class FakeSession:
    """A scripted session: ``discover``/``initialize`` are lists consumed in order;
    an exception instance is raised, anything else returned."""

    def __init__(self, discover=(), initialize=()):
        self._discover = list(discover)
        self._initialize = list(initialize)
        self.calls: list[tuple] = []
        self.protocol_version = None

    async def send_discover(self, version):
        self.calls.append(("discover", version))
        item = self._discover.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def initialize(self):
        self.calls.append(("initialize",))
        item = self._initialize.pop(0) if self._initialize else None
        if isinstance(item, BaseException):
            raise item
        self.protocol_version = HS
        return item

    def adopt(self, result):
        self.calls.append(("adopt",))
        self.protocol_version = MODERN


# --- negotiate: the policy, one test per SDK branch -------------------------


async def test_discover_success_adopts() -> None:
    s = FakeSession(discover=[_discover_result()])
    assert await _negotiate.negotiate(s, remembered=None) == MODERN
    assert s.calls == [("discover", LATEST_MODERN_VERSION), ("adopt",)]


async def test_modern_offer_is_read_at_call_time(monkeypatch) -> None:
    monkeypatch.setattr("mcp.types.version.LATEST_MODERN_VERSION", "2099-01-01")
    s = FakeSession(discover=[METHOD_NOT_FOUND])
    await _negotiate.negotiate(s, remembered=None)
    assert s.calls[0] == ("discover", "2099-01-01")


@pytest.mark.parametrize("err", [METHOD_NOT_FOUND, INVALID_PARAMS, MCPError(-32001, "timeout")])
async def test_other_mcp_error_falls_back_to_initialize(err) -> None:
    s = FakeSession(discover=[err])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert s.calls == [("discover", LATEST_MODERN_VERSION), ("initialize",)]


async def test_32022_mutual_modern_reprobes_once_at_that_version() -> None:
    s = FakeSession(discover=[_unsupported([MODERN, "2099-01-01"]), _discover_result()])
    assert await _negotiate.negotiate(s, remembered=None) == MODERN
    assert s.calls == [("discover", LATEST_MODERN_VERSION), ("discover", MODERN), ("adopt",)]


async def test_32022_disjoint_modern_only_raises() -> None:
    s = FakeSession(discover=[_unsupported(["2099-01-01"])])
    with pytest.raises(MCPError) as ei:
        await _negotiate.negotiate(s, remembered=None)
    assert ei.value.code == -32022
    assert s.calls == [("discover", LATEST_MODERN_VERSION)]


async def test_32022_listing_a_handshake_version_falls_back() -> None:
    s = FakeSession(discover=[_unsupported([HS])])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert s.calls[-1] == ("initialize",)


@pytest.mark.parametrize("data", [None, {"junk": 1}, "text"])
async def test_32022_unparseable_data_falls_back(data) -> None:
    s = FakeSession(discover=[MCPError(-32022, "unsupported", data)])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert s.calls == [("discover", LATEST_MODERN_VERSION), ("initialize",)]


async def test_initialize_32022_reprobes_discover_once_at_mutual_version() -> None:
    s = FakeSession(
        discover=[METHOD_NOT_FOUND, _discover_result()],
        initialize=[_unsupported([MODERN])],
    )
    assert await _negotiate.negotiate(s, remembered=None) == MODERN
    assert s.calls == [
        ("discover", LATEST_MODERN_VERSION),
        ("initialize",),
        ("discover", MODERN),
        ("adopt",),
    ]


async def test_initialize_32022_without_mutual_version_raises() -> None:
    s = FakeSession(discover=[METHOD_NOT_FOUND], initialize=[_unsupported(["2099-01-01"])])
    with pytest.raises(MCPError):
        await _negotiate.negotiate(s, remembered=None)


async def test_initialize_32022_on_the_second_attempt_raises() -> None:
    s = FakeSession(
        discover=[METHOD_NOT_FOUND, METHOD_NOT_FOUND],
        initialize=[_unsupported([MODERN]), _unsupported([MODERN])],
    )
    with pytest.raises(MCPError):
        await _negotiate.negotiate(s, remembered=None)
    assert [c[0] for c in s.calls] == ["discover", "initialize", "discover", "initialize"]


@pytest.mark.parametrize("exc", [ConnectionError("x"), httpx2.ConnectError("x"), ValueError("v")])
async def test_non_mcp_error_from_discover_propagates(exc) -> None:
    s = FakeSession(discover=[exc])
    with pytest.raises(type(exc)):
        await _negotiate.negotiate(s, remembered=None)
    assert s.calls == [("discover", LATEST_MODERN_VERSION)]


async def test_invalid_discover_result_falls_back() -> None:
    s = FakeSession(discover=[{"nonsense": True}])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert s.calls[-1] == ("initialize",)


async def test_discover_result_with_no_modern_version_falls_back() -> None:
    s = FakeSession(discover=[_discover_result(versions=[HS])])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert ("adopt",) not in s.calls


async def test_url_elicitation_from_discover_falls_back_like_any_mcp_error() -> None:
    """Pin (SDK parity): UrlElicitationRequiredError is an MCPError subclass."""
    s = FakeSession(discover=[UrlElicitationRequiredError([])])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert s.calls[-1] == ("initialize",)


# --- negotiate: the DD2 shortcut --------------------------------------------


@pytest.mark.parametrize("rev", ["2024-11-05", "2025-06-18", HS])
async def test_remembered_handshake_revision_skips_discover(rev) -> None:
    s = FakeSession()
    assert await _negotiate.negotiate(s, remembered=rev) == HS
    assert s.calls == [("initialize",)]


@pytest.mark.parametrize("remembered", [None, MODERN, "1999-01-01"])
async def test_remembered_other_than_handshake_runs_the_full_policy(remembered) -> None:
    s = FakeSession(discover=[_discover_result()])
    assert await _negotiate.negotiate(s, remembered=remembered) == MODERN
    assert s.calls[0][0] == "discover"


async def test_shortcut_failure_runs_the_full_policy_in_the_same_call() -> None:
    s = FakeSession(discover=[_discover_result()], initialize=[METHOD_NOT_FOUND])
    assert await _negotiate.negotiate(s, remembered=HS) == MODERN
    assert s.calls == [("initialize",), ("discover", LATEST_MODERN_VERSION), ("adopt",)]


async def test_shortcut_non_mcp_error_propagates() -> None:
    s = FakeSession(initialize=[ConnectionError("down")])
    with pytest.raises(ConnectionError):
        await _negotiate.negotiate(s, remembered=HS)
    assert s.calls == [("initialize",)]


async def test_shortcut_401_propagates_without_the_full_policy(monkeypatch) -> None:
    s = FakeSession(initialize=[MCPError(-32603, "boom")])
    rec = sr.AuthRecord()
    monkeypatch.setattr(_negotiate, "auth_record_for", lambda session: rec)

    async def init_401():
        s.calls.append(("initialize",))
        rec.seq += 1
        rec.last_status = 401
        raise MCPError(-32603, "boom")

    s.initialize = init_401
    with pytest.raises(MCPError):
        await _negotiate.negotiate(s, remembered=HS)
    assert s.calls == [("initialize",)]


async def test_shortcut_non_401_status_still_runs_the_full_policy(monkeypatch) -> None:
    s = FakeSession(discover=[_discover_result()])
    rec = sr.AuthRecord()
    monkeypatch.setattr(_negotiate, "auth_record_for", lambda session: rec)

    async def init_500():
        s.calls.append(("initialize",))
        rec.seq += 1
        rec.last_status = 500
        raise MCPError(-32603, "boom")

    s.initialize = init_500
    assert await _negotiate.negotiate(s, remembered=HS) == MODERN


def _moving_record(monkeypatch, session, statuses):
    """Register an AuthRecord for ``session`` whose ``send_discover`` bumps seq and
    sets ``last_status`` per call (``None`` = no response seen)."""
    rec = sr.AuthRecord()
    monkeypatch.setattr(_negotiate, "auth_record_for", lambda sess: rec)
    orig = session.send_discover
    it = iter(statuses)

    async def moving(version):
        st = next(it)
        if st is not None:
            rec.seq += 1
            rec.last_status = st
            rec.last_resource_metadata = "https://rm.test/x" if st == 401 else None
        return await orig(version)

    session.send_discover = moving
    return rec


async def test_discover_401_in_record_defers_then_initialize_ok_keeps_handshake(monkeypatch):
    s = FakeSession(discover=[MCPError(-32603, "x")])
    _moving_record(monkeypatch, s, [401])
    assert await _negotiate.negotiate(s, remembered=None) == HS
    assert s.calls == [("discover", LATEST_MODERN_VERSION), ("initialize",)]


async def test_discover_401_in_record_then_initialize_error_raises_marker(monkeypatch):
    s = FakeSession(discover=[MCPError(-32603, "x")], initialize=[MCPError(-32600, "bad")])
    _moving_record(monkeypatch, s, [401])
    with pytest.raises(_negotiate.DiscoverSignInRequired) as ei:
        await _negotiate.negotiate(s, remembered=None)
    assert ei.value.resource_metadata_url == "https://rm.test/x"


async def test_discover_401_wins_over_a_32022_body(monkeypatch):
    """The record is the authority, checked before the -32022 branch: no re-probe."""
    s = FakeSession(
        discover=[_unsupported([MODERN]), _discover_result()],
        initialize=[MCPError(-32600, "bad")],
    )
    _moving_record(monkeypatch, s, [401, 200])
    with pytest.raises(_negotiate.DiscoverSignInRequired):
        await _negotiate.negotiate(s, remembered=None)
    assert [c[0] for c in s.calls] == ["discover", "initialize"]


async def test_preseeded_401_with_unchanged_seq_does_not_defer(monkeypatch):
    s = FakeSession(discover=[METHOD_NOT_FOUND], initialize=[MCPError(-32600, "bad")])
    rec = _moving_record(monkeypatch, s, [None])
    rec.seq, rec.last_status = 3, 401
    with pytest.raises(MCPError) as ei:
        await _negotiate.negotiate(s, remembered=None)
    assert not isinstance(ei.value, _negotiate.DiscoverSignInRequired)


async def test_a_401_from_attempt_zero_does_not_count_for_attempt_one(monkeypatch):
    """Fresh baseline per attempt. Attempt 0: 401 body carrying -32022 is deferred (no
    re-probe), so to reach attempt 1 attempt 0 must be a non-401 -32022; attempt 1 is
    then a plain error with no new response, and the earlier record state is ignored."""
    s = FakeSession(
        discover=[_unsupported([MODERN]), METHOD_NOT_FOUND],
        initialize=[MCPError(-32600, "bad")],
    )
    rec = _moving_record(monkeypatch, s, [500, None])
    rec.last_status = 401  # stale 401 from before; seq moves only on attempt 0
    with pytest.raises(MCPError) as ei:
        await _negotiate.negotiate(s, remembered=None)
    assert not isinstance(ei.value, _negotiate.DiscoverSignInRequired)


async def test_record_none_keeps_sdk_parity_fallback(monkeypatch):
    s = FakeSession(discover=[MCPError(-32603, "x")], initialize=[MCPError(-32600, "bad")])
    monkeypatch.setattr(_negotiate, "auth_record_for", lambda sess: None)
    with pytest.raises(MCPError) as ei:
        await _negotiate.negotiate(s, remembered=None)
    assert not isinstance(ei.value, _negotiate.DiscoverSignInRequired)
    assert [c[0] for c in s.calls] == ["discover", "initialize"]


def test_saw_401_since_predicate() -> None:
    assert sr.saw_401_since(None, 0) is False
    assert sr.saw_401_since(sr.AuthRecord(seq=1, last_status=401), 0) is True
    assert sr.saw_401_since(sr.AuthRecord(seq=1, last_status=401), 1) is False
    assert sr.saw_401_since(sr.AuthRecord(seq=2, last_status=200), 0) is False


def test_negotiate_uses_only_public_sdk_names() -> None:
    import inspect

    src = inspect.getsource(_negotiate)
    assert "mcp.client._probe" not in src
    assert "from mcp.client" not in src and "import negotiate_auto" not in src


# --- parity with the SDK's negotiate_auto (SDK imported in the test only) ----


def _scenarios():
    return {
        "success": dict(discover=[_discover_result()]),
        "method_not_found": dict(discover=[METHOD_NOT_FOUND]),
        "mutual_reprobe": dict(discover=[_unsupported([MODERN]), _discover_result()]),
        "disjoint_raises": dict(discover=[_unsupported(["2099-01-01"])]),
        "handshake_listed": dict(discover=[_unsupported([HS])]),
        "unparseable_32022": dict(discover=[MCPError(-32022, "u", {"junk": 1})]),
        "initialize_32022_reprobe": dict(
            discover=[METHOD_NOT_FOUND, _discover_result()], initialize=[_unsupported([MODERN])]
        ),
        "initialize_32022_disjoint": dict(
            discover=[METHOD_NOT_FOUND], initialize=[_unsupported(["2099-01-01"])]
        ),
        "initialize_32022_twice": dict(
            discover=[METHOD_NOT_FOUND, METHOD_NOT_FOUND],
            initialize=[_unsupported([MODERN]), _unsupported([MODERN])],
        ),
        "transport_error": dict(discover=[ConnectionError("x")]),
        "invalid_result": dict(discover=[{"nonsense": True}]),
        "no_modern_version": dict(discover=[_discover_result(versions=[HS])]),
        "url_elicitation": dict(discover=[UrlElicitationRequiredError([])]),
        "initialize_other_error": dict(
            discover=[METHOD_NOT_FOUND], initialize=[MCPError(-32603, "boom")]
        ),
    }


async def _outcome(fn, **script):
    s = FakeSession(**script)
    try:
        await fn(s)
        verdict = "ok"
    except BaseException as e:  # noqa: BLE001 - comparing outcomes, whatever they are
        verdict = (type(e).__name__, getattr(e, "code", None))
    return verdict, s.calls, s.protocol_version


@pytest.mark.parametrize("name", list(_scenarios()))
async def test_parity_with_sdk_negotiate_auto(name) -> None:
    """Drift tripwire: the-one's policy and the SDK's private ``negotiate_auto``
    must agree on outcome, call sequence and negotiated version for every scripted
    scenario. A failure after an SDK upgrade means the policy moved."""
    from mcp.client._probe import negotiate_auto

    async def ours(s):
        await _negotiate.negotiate(s, remembered=None)

    ref = await _outcome(negotiate_auto, **_scenarios()[name])
    got = await _outcome(ours, **_scenarios()[name])
    assert got == ref


# --- connect: era memory, fresh_negotiation, record_era -----------------------


def _modern_session(meta=None, versions=(MODERN,)):
    s = MagicMock()
    result = _discover_result(versions, meta=meta)
    s.send_discover = AsyncMock(return_value=result)
    s.initialize = AsyncMock(side_effect=AssertionError("handshake not expected"))
    s.initialize_result = None
    s.discover_result = result
    s.protocol_version = MODERN
    s.server_capabilities = result.capabilities
    s.server_info = mcp_types.Implementation(name="srv", version="")
    s.instructions = None
    return s


@pytest.fixture
def patch(monkeypatch):
    def _install(sess):
        @asynccontextmanager
        async def _cm(source):
            yield sess

        monkeypatch.setattr(client_mod, "_transport_connect", _cm)
        return sess

    return _install


def _handshake_session(version=HS, **kw):
    s = MagicMock()
    _set_init(s, _make_init_result(protocol_version=version, **kw))
    return s


async def test_connect_remembers_the_negotiated_era(patch) -> None:
    patch(_modern_session())
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    assert c.negotiated_protocol_version == MODERN
    assert _era.era_for("a") == MODERN
    await c.disconnect()


async def test_connect_on_remembered_handshake_sends_no_discover(patch) -> None:
    sess = patch(_handshake_session())
    _era.remember_era("a", HS)
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    sess.send_discover.assert_not_awaited()
    assert _era.era_for("a") == HS
    await c.disconnect()


async def test_fresh_negotiation_ignores_the_remembered_era(patch) -> None:
    sess = patch(_handshake_session())
    _era.remember_era("a", HS)
    c = MCPClient(_stdio_source(source_id="a"), fresh_negotiation=True)
    await c.connect()
    sess.send_discover.assert_awaited_once()
    await c.disconnect()


async def test_failed_connect_forgets_the_era(patch) -> None:
    sess = patch(_handshake_session())
    sess.initialize = AsyncMock(side_effect=ValueError("boom"))
    _era.remember_era("a", HS)
    with pytest.raises(MCPConnectionError):
        await MCPClient(_stdio_source(source_id="a")).connect()
    assert _era.era_for("a") is None


async def test_record_era_false_suppresses_remember_and_forget(patch) -> None:
    patch(_modern_session())
    c = MCPClient(_stdio_source(source_id="a"), record_era=False)
    await c.connect()
    assert _era.era_for("a") is None
    await c.disconnect()
    sess = patch(_handshake_session())
    sess.initialize = AsyncMock(side_effect=ValueError("boom"))
    _era.remember_era("b", HS)
    with pytest.raises(MCPConnectionError):
        await MCPClient(_stdio_source(source_id="b"), record_era=False).connect()
    assert _era.era_for("b") == HS


async def test_already_connected_guard_leaves_the_memory_intact(patch) -> None:
    patch(_modern_session())
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    with pytest.raises(MCPConnectionError, match="already connected"):
        await c.connect()
    assert _era.era_for("a") == MODERN
    await c.disconnect()


async def test_cancellation_is_not_an_era_verdict(monkeypatch) -> None:
    """A CancelledError escaping ``_connect_once`` re-raises without forgetting."""

    async def cancelled(self):
        raise asyncio.CancelledError()

    monkeypatch.setattr(MCPClient, "_connect_once", cancelled)
    _era.remember_era("a", HS)
    with pytest.raises(asyncio.CancelledError):
        await MCPClient(_stdio_source(source_id="a")).connect()
    assert _era.era_for("a") == HS


async def test_unsupported_revision_after_negotiation_is_a_mismatch(patch) -> None:
    sess = patch(_handshake_session())
    sess.protocol_version = "1999-01-01"
    with pytest.raises(MCPVersionMismatch) as ei:
        await MCPClient(_stdio_source(source_id="a")).connect()
    assert ei.value.observed == "1999-01-01"


# --- connect: -32022 end to end ----------------------------------------------


async def test_no_shared_version_through_connect_is_a_version_mismatch(patch) -> None:
    sess = patch(_modern_session())
    sess.send_discover = AsyncMock(side_effect=_unsupported(["2099-01-01"]))
    with pytest.raises(MCPVersionMismatch) as ei:
        await MCPClient(_stdio_source(source_id="a")).connect()
    assert ei.value.observed == "2099-01-01"
    assert _era.era_for("a") is None


async def test_accepted_gap_reprobe_listing_only_modern_is_a_generic_failure(patch) -> None:
    """Pin (accepted gap): negotiate raises when ``supported`` lists no handshake
    version (the SDK's criterion) but ``_shares_no_version`` counts modern too, so
    a -32022 on the re-probe that lists a mutual modern version reads as the
    generic connect failure, not MCPVersionMismatch."""
    sess = patch(_modern_session())
    sess.send_discover = AsyncMock(side_effect=_unsupported([MODERN]))
    with pytest.raises(MCPConnectionError, match="MCP connect failed") as ei:
        await MCPClient(_stdio_source(source_id="a")).connect()
    assert not isinstance(ei.value, MCPVersionMismatch)
    assert sess.send_discover.await_count == 2


# --- connect: _meta in both eras (DD3) ----------------------------------------


async def test_modern_meta_drops_the_server_info_stamp(patch) -> None:
    stamp = {mcp_types.SERVER_INFO_META_KEY: {"name": "srv", "version": ""}, "other": 1}
    patch(_modern_session(meta=stamp))
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    assert c._meta == {"other": 1}
    await c.disconnect()


async def test_modern_meta_with_only_the_stamp_is_none(patch) -> None:
    patch(_modern_session(meta={mcp_types.SERVER_INFO_META_KEY: {"name": "srv", "version": ""}}))
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    assert c._meta is None
    await c.disconnect()


async def test_modern_without_meta_is_none(patch) -> None:
    patch(_modern_session())
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    assert c._meta is None
    await c.disconnect()


async def test_handshake_meta_is_kept(patch) -> None:
    patch(_handshake_session(meta={"vendor": "x"}))
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    assert c._meta == {"vendor": "x"}
    assert c.negotiated_protocol_version == HS
    await c.disconnect()


async def test_handshake_stamp_key_is_dropped_too(patch) -> None:
    patch(_handshake_session(meta={mcp_types.SERVER_INFO_META_KEY: {"name": "s"}, "k": 2}))
    c = MCPClient(_stdio_source(source_id="a"))
    await c.connect()
    assert c._meta == {"k": 2}
    await c.disconnect()


# --- connect: a discover answered 401 with a real wrapper ---------------------


async def test_discover_401_and_initialize_200_connects_on_the_handshake(monkeypatch) -> None:
    wrapper = Auth401Wrapper(make_http_app(), fail_methods={"server/discover"})
    async with LifespanManager(wrapper):
        client = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=wrapper), base_url="http://localhost"
        )
        monkeypatch.setattr(sh, "_test_http_client_override", client)
        try:
            src = MCPSource(
                id="s401",
                name="n",
                type="streamable-http",
                config={"url": "http://localhost/mcp", "headers": {}},
                secrets={},
            )
            c = MCPClient(src)
            await c.connect()
            try:
                assert c.negotiated_protocol_version == HS
                assert _era.era_for("s401") == HS
                assert ("server/discover", 401) in wrapper.seen
            finally:
                await c.disconnect()
        finally:
            await client.aclose()


async def test_every_mock_session_fixture_answers_discover() -> None:
    """AC6 tripwire: the centralised hook makes a bare mock session fall back."""
    s = MagicMock()
    _set_init(s, _make_init_result())
    with pytest.raises(MCPError) as ei:
        await s.send_discover(MODERN)
    assert ei.value.code == mcp_types.METHOD_NOT_FOUND
