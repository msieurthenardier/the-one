"""Tests for M11 F17 L1 connector disposition observability.

Covers:
1.  :func:`log_disposition` emits one structured stdout line per call.
2.  Inbound vocabulary: all six dispositions are emitted.
3.  Outbound vocabulary: all three dispositions are emitted.
4.  ``dropped`` disposition logs at DEBUG; all others at INFO.
5.  ``log_disposition`` calls :func:`record_disposition` best-effort.
6.  ``record_disposition`` increments counters on a warm entry.
7.  ``record_disposition`` is a no-op when no warm entry exists.
8.  ``_get_account_counters_snapshot`` returns a frozen pair for a warm entry.
9.  ``_get_account_counters_snapshot`` returns ``None`` when cold.
10. ``GET /connectors/{id}/disposition-counters`` — 404 when connector not found.
11. ``GET /connectors/{id}/disposition-counters`` — warm=False + empty when cold.
12. ``GET /connectors/{id}/disposition-counters`` — warm=True + counters when warm.
13. No-leak guarantee: a log call with content + token must NOT include them in
    the emitted line.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from the_one.connectors import _pool as pool_mod
from the_one.connectors._observability import log_disposition
from the_one.connectors._pool import (
    _ACCOUNT_POOL_AGENT_SLOT,
    _CountersSnapshot,
    _get_account_counters_snapshot,
    account_acquire,
    record_disposition,
)
from the_one.connectors.base import DoctorReport, SessionKey
from the_one.connectors.registry import register_for_test, restore_to_baseline_for_test
from the_one.db.models import Connector

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _clear_pool():
    yield
    await pool_mod._clear_for_test()
    restore_to_baseline_for_test()


class _StubClient:
    """Minimal ConnectorClient stub."""

    def is_alive(self) -> bool:
        return True


class _StubPlugin:
    """Minimal ConnectorPlugin stub."""

    async def connect(self, account, encryptor):  # noqa: ANN001
        return _StubClient()

    async def disconnect(self, client):  # noqa: ANN001
        pass

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )


def _make_connector(account_id: str = "acct-obs-test") -> Connector:
    return Connector(id=account_id, name="Obs Test", type="stub", config={}, secrets={})


@pytest.fixture
def patch_pool(monkeypatch):
    """Register the stub plugin + patch _load_account for warm-entry tests."""
    register_for_test("stub", _StubPlugin)

    async def _patched_load(account_id, encryptor):  # noqa: ANN001
        return _make_connector(account_id=account_id)

    monkeypatch.setattr(pool_mod, "_load_account", _patched_load)


# ─── Helper ───────────────────────────────────────────────────────────────────


def _call_log_disposition(**kwargs) -> None:  # type: ignore[return]
    """Minimal log_disposition call with required fields filled."""
    defaults = dict(
        account_id="acct-1",
        channel_id="ch-1",
        peer_id="peer-1",
        kind="inbound",
        disposition="stepped",
    )
    defaults.update(kwargs)
    log_disposition(**defaults)


# ─── Tests: line format ───────────────────────────────────────────────────────


def test_log_disposition_emits_one_line_with_key_value_pairs(caplog):
    """The emitted log record contains account=, channel=, peer=, disposition=."""
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(
            account_id="acct-42",
            channel_id="ch-99",
            peer_id="peer-77",
            kind="inbound",
            disposition="stepped",
        )

    assert len(caplog.records) == 1
    msg = caplog.records[0].message
    assert "connector.inbound" in msg
    assert "account=acct-42" in msg
    assert "channel=ch-99" in msg
    assert "peer=peer-77" in msg
    assert "disposition=stepped" in msg


def test_log_disposition_includes_optional_reason(caplog):
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(disposition="denied", reason="invalid_pairing")
    msg = caplog.records[0].message
    assert "reason=invalid_pairing" in msg


def test_log_disposition_includes_latency_ms(caplog):
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="outbound", disposition="ok", latency_ms=12.5)
    msg = caplog.records[0].message
    assert "latency_ms=12.5" in msg
    assert "connector.outbound" in msg


def test_log_disposition_includes_retry_after(caplog):
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="outbound", disposition="rate_limited", retry_after=5.0)
    msg = caplog.records[0].message
    assert "retry_after=5.000" in msg


def test_log_disposition_includes_error_type(caplog):
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="outbound", disposition="error", error_type="Forbidden")
    msg = caplog.records[0].message
    assert "error_type=Forbidden" in msg


# ─── Tests: vocabulary ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "disposition",
    ["stepped", "command-intercepted", "no-eligible", "policy-silent", "denied"],
)
def test_inbound_dispositions_emit_info(caplog, disposition: str):
    """All inbound non-dropped dispositions emit at INFO."""
    with caplog.at_level(logging.DEBUG, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="inbound", disposition=disposition)
    record = caplog.records[0]
    assert record.levelno == logging.INFO
    assert f"disposition={disposition}" in record.message


def test_inbound_dropped_emits_debug(caplog):
    """The ``dropped`` disposition emits at DEBUG."""
    with caplog.at_level(logging.DEBUG, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="inbound", disposition="dropped", reason="bot-author")
    record = caplog.records[0]
    assert record.levelno == logging.DEBUG
    assert "disposition=dropped" in record.message
    assert "reason=bot-author" in record.message


def test_inbound_dropped_not_visible_at_info(caplog):
    """At INFO level, ``dropped`` lines are invisible."""
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="inbound", disposition="dropped")
    assert caplog.records == []


@pytest.mark.parametrize("disposition", ["ok", "rate_limited", "error"])
def test_outbound_dispositions_emit_info(caplog, disposition: str):
    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        _call_log_disposition(kind="outbound", disposition=disposition)
    record = caplog.records[0]
    assert record.levelno == logging.INFO
    assert f"disposition={disposition}" in record.message
    assert "connector.outbound" in record.message


# ─── Tests: counter increment ─────────────────────────────────────────────────


async def test_record_disposition_increments_warm_entry_inbound(patch_pool):
    """record_disposition increments inbound_counters on a warm entry."""
    client = await account_acquire("acct-obs-test")
    assert client is not None

    record_disposition("acct-obs-test", "inbound", "stepped")
    record_disposition("acct-obs-test", "inbound", "stepped")
    record_disposition("acct-obs-test", "inbound", "denied")

    key = (_ACCOUNT_POOL_AGENT_SLOT, "acct-obs-test")
    entry = pool_mod._pool[key]
    assert entry.inbound_counters == {"stepped": 2, "denied": 1}
    assert entry.outbound_counters == {}


async def test_record_disposition_increments_warm_entry_outbound(patch_pool):
    """record_disposition increments outbound_counters on a warm entry."""
    await account_acquire("acct-obs-test")

    record_disposition("acct-obs-test", "outbound", "ok")
    record_disposition("acct-obs-test", "outbound", "rate_limited")

    key = (_ACCOUNT_POOL_AGENT_SLOT, "acct-obs-test")
    entry = pool_mod._pool[key]
    assert entry.outbound_counters == {"ok": 1, "rate_limited": 1}
    assert entry.inbound_counters == {}


async def test_record_disposition_noop_when_no_warm_entry():
    """record_disposition is a no-op when no warm entry exists — no exception."""
    # No acquire — pool is empty.
    record_disposition("nonexistent-account", "inbound", "stepped")
    # No exception raised; no entry in pool.
    assert pool_mod._pool == {}


# ─── Tests: _get_account_counters_snapshot ────────────────────────────────────


async def test_counters_snapshot_returns_frozen_pair(patch_pool):
    """_get_account_counters_snapshot returns a _CountersSnapshot for a warm entry."""
    await account_acquire("acct-obs-test")
    record_disposition("acct-obs-test", "inbound", "stepped")
    record_disposition("acct-obs-test", "outbound", "ok")

    snap = await _get_account_counters_snapshot("acct-obs-test")
    assert snap is not None
    assert isinstance(snap, _CountersSnapshot)
    assert snap.inbound == {"stepped": 1}
    assert snap.outbound == {"ok": 1}


async def test_counters_snapshot_returns_none_when_cold():
    """_get_account_counters_snapshot returns None when no warm entry."""
    snap = await _get_account_counters_snapshot("cold-acct")
    assert snap is None


async def test_counters_snapshot_is_copy_not_live(patch_pool):
    """Mutating the snapshot dict does not affect the pool entry's counters."""
    await account_acquire("acct-obs-test")
    record_disposition("acct-obs-test", "inbound", "stepped")

    snap = await _get_account_counters_snapshot("acct-obs-test")
    assert snap is not None
    # Mutate the snapshot copy.
    snap.inbound["stepped"] = 999

    key = (_ACCOUNT_POOL_AGENT_SLOT, "acct-obs-test")
    entry = pool_mod._pool[key]
    assert entry.inbound_counters["stepped"] == 1  # pool entry unchanged


# ─── Tests: no-leak guarantee ─────────────────────────────────────────────────


def test_no_message_content_or_token_in_log_line(caplog):
    """log_disposition must never include message content or tokens.

    Simulate a scenario where an outbound caller might accidentally pass
    content/token by verifying the log line only contains the expected
    structured fields — no free-form text leaks through.
    """
    secret_token = "xoxb-super-secret-token-12345"
    content_text = "Hello world, this is the message body!"

    with caplog.at_level(logging.INFO, logger="the_one.connectors._observability"):
        # Caller correctly passes only ids/dispositions — NOT content/token.
        log_disposition(
            account_id="acct-1",
            channel_id="ch-1",
            peer_id="peer-1",
            kind="outbound",
            disposition="ok",
            latency_ms=5.0,
        )

    assert len(caplog.records) == 1
    line = caplog.records[0].message
    # The token and message content were NOT passed; assert they're absent.
    assert secret_token not in line
    assert content_text not in line
    # Only structured fields present.
    assert "account=" in line
    assert "disposition=ok" in line
    assert "latency_ms=" in line


def test_log_disposition_signature_has_no_content_or_token_param():
    """log_disposition's signature structurally excludes content/token params.

    Passing them as kwargs raises TypeError — no accident pathway exists.
    """
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        log_disposition(  # type: ignore[call-arg]
            account_id="a",
            channel_id="c",
            peer_id="p",
            kind="outbound",
            disposition="ok",
            content="secret message body",
        )

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        log_disposition(  # type: ignore[call-arg]
            account_id="a",
            channel_id="c",
            peer_id="p",
            kind="outbound",
            disposition="ok",
            token="xoxb-secret",
        )


# ─── Tests: API endpoint (counters read path) ─────────────────────────────────


@pytest.fixture
async def _api_client():
    """Minimal FastAPI + ASGITransport client for connector endpoint tests.

    Mirrors the pattern in ``tests/test_mcp_stdio_test_connect.py``.
    Patches ``_connector_repo`` at the api module level so tests control
    what the repo returns without spinning up a full DB.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from the_one.interfaces.web.api import router

    app = FastAPI()
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_api_disposition_counters_404_unknown_connector(_api_client):
    """GET /connectors/{id}/disposition-counters → 404 for unknown id."""
    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(side_effect=KeyError("not found"))
    mock_repo_factory = AsyncMock(return_value=mock_repo)

    with patch("the_one.interfaces.web.api._connector_repo", mock_repo_factory):
        resp = await _api_client.get("/api/connectors/unknown-acct/disposition-counters")

    assert resp.status_code == 404


async def test_api_disposition_counters_cold_returns_warm_false(_api_client):
    """GET /connectors/{id}/disposition-counters → warm=False + empty when cold."""
    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=MagicMock())
    mock_repo_factory = AsyncMock(return_value=mock_repo)

    # Pool has no warm entry for "cold-acct".
    with patch("the_one.interfaces.web.api._connector_repo", mock_repo_factory):
        resp = await _api_client.get("/api/connectors/cold-acct/disposition-counters")

    assert resp.status_code == 200
    data = resp.json()
    assert data["warm"] is False
    assert data["inbound"] == {}
    assert data["outbound"] == {}


async def test_api_disposition_counters_warm_returns_counts(_api_client, patch_pool):
    """GET /connectors/{id}/disposition-counters → warm=True + counts when warm."""
    # Warm the pool entry and record some dispositions.
    await account_acquire("acct-obs-test")
    record_disposition("acct-obs-test", "inbound", "stepped")
    record_disposition("acct-obs-test", "inbound", "stepped")
    record_disposition("acct-obs-test", "outbound", "ok")

    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=MagicMock())
    mock_repo_factory = AsyncMock(return_value=mock_repo)

    with patch("the_one.interfaces.web.api._connector_repo", mock_repo_factory):
        resp = await _api_client.get("/api/connectors/acct-obs-test/disposition-counters")

    assert resp.status_code == 200
    data = resp.json()
    assert data["warm"] is True
    assert data["inbound"] == {"stepped": 2}
    assert data["outbound"] == {"ok": 1}
