"""Mission 29 Flight 2 leg 1: the DD5 failure matrix, the DD6 owner-task rule and
the DD8 input-required error, driven through mock sessions (leg 2 adds real
modern-era fixtures)."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import anyio
import httpx2
import pytest
from mcp import types as mcp_types
from mcp.shared.exceptions import MCPError, UrlElicitationRequiredError

from tests.test_mcp_client import (
    _make_call_tool_result,
    _make_init_result,
    _make_list_tools_result,
    _make_text_content,
    _make_tool,
    _set_init,
    _stdio_source,
)
from the_one.mcp import _era
from the_one.mcp import _signin_record as sh
from the_one.mcp import client as client_mod
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import (
    TOKEN_FAILURE_MARKERS,
    MCPAuthRequired,
    MCPCallError,
    MCPConnectionError,
    MCPVersionMismatch,
)

SRC = "src-1"
NO_SHARED = {"supported": ["2099-01-01"], "requested": "2025-11-25"}
SHARED = {"supported": ["2025-11-25"], "requested": "2026-07-28"}
SSE_CAP = MCPError(-32000, "SSE stream failed: event exceeded the byte limit")
TERMINATED = MCPError(-32600, "Session terminated")


def _session() -> MagicMock:
    s = MagicMock()
    _set_init(s, _make_init_result())
    s.list_tools = AsyncMock(return_value=_make_list_tools_result([_make_tool("t")]))
    s.call_tool = AsyncMock(return_value=_make_call_tool_result(content=[_make_text_content("ok")]))
    return s


@pytest.fixture
def sess(monkeypatch) -> MagicMock:
    s = _session()

    @asynccontextmanager
    async def _cm(source):
        yield s

    monkeypatch.setattr(client_mod, "_transport_connect", _cm)
    return s


def _record_401(session) -> sh.AuthRecord:
    rec = sh.AuthRecord(seq=1, last_status=401, last_resource_metadata="https://rm/x")
    sh._AUTH_RECORDS[session] = rec
    return rec


def _raising_with_401(session, exc):
    """A session method that records a new 401 response, then fails with ``exc``."""
    rec = sh.auth_record_for(session) or sh.AuthRecord()
    sh._AUTH_RECORDS[session] = rec

    async def _fn(*a, **k):
        rec.seq += 1
        rec.last_status = 401
        raise exc

    return _fn


async def _connected(sess) -> MCPClient:
    c = MCPClient(_stdio_source(source_id=SRC))
    await c.connect()
    return c


# --- row 1: UrlElicitationRequiredError -------------------------------------


async def test_row1_connect_wraps_url_elicitation(sess) -> None:
    sess.initialize = AsyncMock(side_effect=UrlElicitationRequiredError([]))
    with pytest.raises(MCPConnectionError, match="MCP connect failed"):
        await MCPClient(_stdio_source(source_id=SRC)).connect()


async def test_row1_list_tools_passes_through(sess) -> None:
    c = await _connected(sess)
    sess.list_tools = AsyncMock(side_effect=UrlElicitationRequiredError([]))
    with pytest.raises(UrlElicitationRequiredError):
        await c.list_tools()


async def test_row1_call_tool_passes_through(sess) -> None:
    c = await _connected(sess)
    await c.list_tools()
    sess.call_tool = AsyncMock(side_effect=UrlElicitationRequiredError([]))
    with pytest.raises(UrlElicitationRequiredError):
        await c.call_tool("t", {})


# --- row 2: a 401 as the last response -------------------------------------

_ROW2_EXC = [
    pytest.param(MCPError(-32603, "boom"), id="mcp-error"),
    pytest.param(httpx2.ConnectError("x"), id="httpx"),
    pytest.param(anyio.ClosedResourceError(), id="closed-resource"),
    pytest.param(ValueError("generic"), id="generic"),
    pytest.param(ExceptionGroup("g", [ValueError("v")]), id="group"),
]


async def test_row2_connect(sess) -> None:
    _record_401(sess)
    sess.initialize = AsyncMock(side_effect=MCPError(-32603, "boom"))
    with pytest.raises(MCPAuthRequired):
        await MCPClient(_stdio_source(source_id=SRC)).connect()


async def test_row2_connect_generic_exception(sess) -> None:
    _record_401(sess)
    sess.initialize = AsyncMock(side_effect=ValueError("generic"))
    with pytest.raises(MCPAuthRequired):
        await MCPClient(_stdio_source(source_id=SRC)).connect()


@pytest.mark.parametrize("exc", _ROW2_EXC)
async def test_row2_list_tools(sess, exc) -> None:
    c = await _connected(sess)
    sess.list_tools = _raising_with_401(sess, exc)
    with pytest.raises(MCPAuthRequired):
        await c.list_tools()


@pytest.mark.parametrize("exc", _ROW2_EXC)
async def test_row2_call_tool(sess, exc) -> None:
    c = await _connected(sess)
    await c.list_tools()
    sess.call_tool = _raising_with_401(sess, exc)
    with pytest.raises(MCPAuthRequired):
        await c.call_tool("t", {})


async def test_row2_timeout(sess) -> None:
    c = await _connected(sess)
    c.call_timeout_seconds = 0.05
    await c.list_tools()
    rec = sh.AuthRecord()
    sh._AUTH_RECORDS[sess] = rec

    async def _hang(*a, **k):
        rec.seq += 1
        rec.last_status = 401
        await asyncio.sleep(5)

    sess.call_tool = _hang
    with pytest.raises(MCPAuthRequired):
        await c.call_tool("t", {})


# --- row 3: -32022 ----------------------------------------------------------


async def test_row3_connect_no_shared_version(sess) -> None:
    sess.initialize = AsyncMock(side_effect=MCPError(-32022, "unsupported", NO_SHARED))
    with pytest.raises(MCPVersionMismatch) as ei:
        await MCPClient(_stdio_source(source_id=SRC)).connect()
    assert ei.value.observed == "2099-01-01"


@pytest.mark.parametrize("data", [SHARED, None, {"junk": 1}])
async def test_row3_connect_shared_or_unparsed_is_plain_connection_error(sess, data) -> None:
    sess.initialize = AsyncMock(side_effect=MCPError(-32022, "unsupported", data))
    with pytest.raises(MCPConnectionError, match="MCP connect failed"):
        await MCPClient(_stdio_source(source_id=SRC)).connect()


async def test_row3_connect_initialize_runtime_error_still_mismatch(sess) -> None:
    sess.initialize = AsyncMock(
        side_effect=RuntimeError("Unsupported protocol version from the server: 1999-01-01")
    )
    with pytest.raises(MCPVersionMismatch) as ei:
        await MCPClient(_stdio_source(source_id=SRC)).connect()
    assert ei.value.observed == "1999-01-01"


@pytest.mark.parametrize("op", ["list_tools", "call_tool"])
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (NO_SHARED, MCPVersionMismatch),
        (SHARED, MCPConnectionError),
        (None, MCPConnectionError),
        ({"junk": 1}, MCPConnectionError),
    ],
)
async def test_row3_mid_session_marks_dead_and_forgets_era(sess, op, data, expected) -> None:
    c = await _connected(sess)
    await c.list_tools()
    _era.remember_era(SRC, "2026-07-28")
    err = MCPError(-32022, "unsupported", data)
    if op == "list_tools":
        sess.list_tools = AsyncMock(side_effect=err)
        coro = c.list_tools()
    else:
        sess.call_tool = AsyncMock(side_effect=err)
        coro = c.call_tool("t", {})
    with pytest.raises(expected) as ei:
        await coro
    assert type(ei.value) is expected
    assert c.is_alive is False
    assert _era.era_for(SRC) is None
    if expected is MCPConnectionError:
        assert "changed protocol revision" in str(ei.value)


# --- row 4: SSE cap ---------------------------------------------------------


async def test_row4_connect(sess) -> None:
    sess.initialize = AsyncMock(side_effect=SSE_CAP)
    with pytest.raises(MCPConnectionError, match="larger than"):
        await MCPClient(_stdio_source(source_id=SRC)).connect()


async def test_row4_list_tools_not_marked_dead(sess) -> None:
    c = await _connected(sess)
    sess.list_tools = AsyncMock(side_effect=SSE_CAP)
    with pytest.raises(MCPConnectionError, match="larger than"):
        await c.list_tools()
    assert c.is_alive


async def test_row4_call_tool_not_marked_dead(sess) -> None:
    c = await _connected(sess)
    await c.list_tools()
    sess.call_tool = AsyncMock(side_effect=SSE_CAP)
    with pytest.raises(MCPCallError, match="larger than"):
        await c.call_tool("t", {})
    assert c.is_alive


# --- row 5 (unchanged behaviour, order swapped with row 4) ------------------


async def test_row5_session_terminated(sess) -> None:
    c = await _connected(sess)
    sess.list_tools = AsyncMock(side_effect=TERMINATED)
    with pytest.raises(MCPConnectionError):
        await c.list_tools()
    assert c.is_alive is False
    c2 = await _connected(sess)
    sess.list_tools = AsyncMock(return_value=_make_list_tools_result([_make_tool("t")]))
    await c2.list_tools()
    sess.call_tool = AsyncMock(side_effect=TERMINATED)
    with pytest.raises(MCPConnectionError, match="session terminated"):
        await c2.call_tool("t", {})
    assert c2.is_alive is False


# --- AC4: the contract strings Test connection matches on -------------------


def test_token_failure_markers_are_pinned() -> None:
    assert TOKEN_FAILURE_MARKERS == ("did not respond", "cancelled during initialize")


async def test_contract_strings_come_from_the_real_code_paths(sess) -> None:
    """The same case-insensitive ``in`` test ``api.py`` uses matches both messages."""

    def looks_like_token_failure(e: Exception) -> bool:
        msg = str(e).lower()
        return any(m in msg for m in TOKEN_FAILURE_MARKERS)

    async def _hang(*a, **k):
        await asyncio.sleep(5)

    sess.initialize = _hang
    with pytest.raises(MCPConnectionError) as ei:
        await MCPClient(_stdio_source(source_id=SRC), timeout_seconds=0.05).connect()
    assert "did not respond" in str(ei.value)
    assert looks_like_token_failure(ei.value)

    sess.initialize = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(MCPConnectionError) as ei:
        await MCPClient(_stdio_source(source_id=SRC)).connect()
    assert "cancelled during initialize" in str(ei.value)
    assert looks_like_token_failure(ei.value)


# --- AC5: owner-task cancellation rule --------------------------------------


async def test_cancel_on_other_task_propagates_despite_401(sess) -> None:
    c = MCPClient(_stdio_source(source_id=SRC))
    await asyncio.create_task(c.connect())  # the owner task, now finished
    await c.list_tools()
    sess.call_tool = _raising_with_401(sess, asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await c.call_tool("t", {})


async def test_cancel_on_other_task_propagates_in_list_tools(sess) -> None:
    c = MCPClient(_stdio_source(source_id=SRC))
    await asyncio.create_task(c.connect())
    sess.list_tools = _raising_with_401(sess, asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await c.list_tools()


async def test_cancel_on_owner_task_still_translates_401(sess) -> None:
    c = await _connected(sess)
    await c.list_tools()
    sess.call_tool = _raising_with_401(sess, asyncio.CancelledError())
    with pytest.raises(MCPAuthRequired):
        await c.call_tool("t", {})


async def test_owner_task_reset_on_connect_and_cleared_on_disconnect(sess) -> None:
    c = MCPClient(_stdio_source(source_id=SRC))
    assert c._owner_task is None
    await c.connect()
    assert c._owner_task is asyncio.current_task()
    await c.disconnect()
    assert c._owner_task is None


# --- AC7: input required ----------------------------------------------------


async def test_input_required_result_is_a_plain_call_error(sess) -> None:
    c = await _connected(sess)
    await c.list_tools()
    sess.call_tool = AsyncMock(return_value=mcp_types.InputRequiredResult(request_state="x"))
    with pytest.raises(MCPCallError) as ei:
        await c.call_tool("t", {})
    assert (
        ei.value.server_message
        == "the server asked for extra input, which the-one can't provide yet"
    )
    sess.call_tool.assert_awaited_once_with("t", {}, allow_input_required=True)


# --- AC3: the mismatch message ----------------------------------------------


def test_mismatch_message_names_the_supported_range() -> None:
    e = MCPVersionMismatch(pinned="2025-11-25", observed="1999-01-01")
    assert "the-one supports 2024-11-05 through 2026-07-28" in str(e)
    assert e.pinned == "2025-11-25" and e.observed == "1999-01-01"
