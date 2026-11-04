"""Smoke tests for ``tests/fixtures/mcp/key_server.py`` (sortie 09 DD11)."""

from __future__ import annotations

import subprocess
import sys
import time

import httpx
import httpx2
import pytest
from asgi_lifespan import LifespanManager

from tests.fixtures.mcp.key_server import KeyServerApp, make_key_app, parse_keys
from the_one.db.models import MCPSource
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPCredentialsRejected
from the_one.mcp.transports import streamable_http as sh

KEYS = {"alpha-key-1": ["echo"], "beta-key-22": ["echo", "add"]}


def test_keys_must_be_at_least_eight_characters():
    with pytest.raises(ValueError, match="at least 8"):
        make_key_app("X-Api-Key", {"short": ["echo"]})


def test_parse_keys_grammar():
    assert parse_keys("alpha-key-1:echo;beta-key-22:echo,add") == KEYS


def _source(headers: dict[str, str]) -> MCPSource:
    return MCPSource(
        id="src-key",
        name="keyed",
        type="streamable-http",
        config={"url": "http://localhost/mcp", "headers": dict(headers)},
    )


def _serve(monkeypatch, app: KeyServerApp) -> None:
    def factory(headers):
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://localhost",
            headers=headers,
        )

    monkeypatch.setattr(sh, "_test_http_client_override", factory)


async def test_each_key_sees_only_its_own_tools_and_the_log_keeps_only_a_tail(monkeypatch):
    app = make_key_app("X-Api-Key", KEYS)
    async with LifespanManager(app):
        _serve(monkeypatch, app)
        for key, expected in (("alpha-key-1", {"echo"}), ("beta-key-22", {"echo", "add"})):
            async with MCPClient(_source({"X-Api-Key": key}), fresh_negotiation=True) as client:
                assert {t.name for t in await client.list_tools()} == expected
                if "add" in expected:
                    assert (await client.call_tool("add", {"a": 2, "b": 3})).text
        methods = {e["method"] for e in app.log}
        assert {"tools/list", "tools/call"} <= methods
        tails = {e["key_tail"] for e in app.log}
        assert tails == {"ey-1", "y-22"}
        assert "alpha-key-1" not in str(app.log) and "beta-key-22" not in str(app.log)
        assert [e["seq"] for e in app.log] == list(range(1, len(app.log) + 1))


async def test_a_missing_or_wrong_key_gets_a_bare_401_that_is_credentials_rejected(monkeypatch):
    app = make_key_app("X-Api-Key", KEYS)
    async with LifespanManager(app):
        _serve(monkeypatch, app)
        for headers in ({}, {"X-Api-Key": "not-a-real-key"}):
            with pytest.raises(MCPCredentialsRejected if headers else Exception) as exc:
                async with MCPClient(_source(headers), fresh_negotiation=True) as client:
                    await client.list_tools()
            if not headers:
                # no configured header at all: not "credentials rejected", a sign-in prompt
                assert not isinstance(exc.value, MCPCredentialsRejected)
        assert any(e["status"] == 401 for e in app.log)
        # the raw response has no WWW-Authenticate (no resource_metadata to discover)
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://localhost"
        ) as raw:
            resp = await raw.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
            assert resp.status_code == 401
            assert "www-authenticate" not in resp.headers
            log = (await raw.get("/_log")).json()
            assert log[-1]["method"] == "ping" and log[-1]["key_tail"] is None


def test_subprocess_prints_port_serves_and_shuts_down_fast():
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.fixtures.mcp.key_server",
            "--header",
            "X-Api-Key",
            "--keys",
            "alpha-key-1:echo;beta-key-22:echo,add",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        line = proc.stdout.readline().strip()
        assert line.startswith("PORT ")
        base = f"http://127.0.0.1:{line.split()[1]}"
        body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        assert httpx.post(f"{base}/mcp", json=body, timeout=5).status_code == 401
        log = httpx.get(f"{base}/_log", timeout=5).json()
        assert log[0]["status"] == 401
    finally:
        started = time.monotonic()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    assert time.monotonic() - started < 3.0
