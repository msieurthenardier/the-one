"""Tests for the F6 L1 tool-config admin endpoints.

Mirrors the established API-test pattern at `tests/test_db_api.py:16-35`
(ASGITransport + AsyncClient + isolated DB + patched `get_connection`).
Do NOT use `from fastapi.testclient import TestClient` — that path
triggers the real app's `lifespan`, which is not what existing API
tests use.
"""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.interfaces.web.api import router
from the_one.tools._search_backends import SearchResult


@pytest.fixture
async def client(tmp_path):
    """Create a test client with an isolated DB. Mirrors the fixture at
    `tests/test_db_api.py:16-35` exactly."""
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        test_app = FastAPI()
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


# ── GET /api/tools/configs ────────────────────────────────────────────────


class TestListToolConfigs:
    async def test_list_configs_returns_all_20_tools(self, client: AsyncClient) -> None:
        """Fresh DB, no rows → GET returns 20 entries each with
        `enabled=True`, `config={}`, plus the tool's description."""
        from the_one.tools.builtins import _TOOL_CLASSES

        resp = await client.get("/api/tools/configs")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == len(_TOOL_CLASSES) == 20
        # Sorted by name.
        names = [r["name"] for r in rows]
        assert names == sorted(_TOOL_CLASSES)
        for r in rows:
            assert r["enabled"] is True
            assert r["config"] == {}
            assert isinstance(r["description"], str) and r["description"]

    async def test_list_configs_reflects_saved_state(self, client: AsyncClient) -> None:
        """Upsert one row with `enabled=False`; GET shows that row's
        `enabled=False` and the others' `enabled=True`."""
        await client.put(
            "/api/tools/configs/web_search",
            json={"enabled": False},
        )
        resp = await client.get("/api/tools/configs")
        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()}
        assert rows["web_search"]["enabled"] is False
        assert rows["fetch_url"]["enabled"] is True
        assert rows["shell"]["enabled"] is True


# ── GET /api/tools/configs/{name} ─────────────────────────────────────────


class TestGetToolConfig:
    async def test_get_one_returns_enriched_schema(self, client: AsyncClient) -> None:
        """Returns `{name, enabled, config, description, schema}` with
        `schema["properties"][field]["x_marker"]` populated for marker-
        bearing fields. Confirms the helper covers all marker types
        via WebConfig (Narrow + NarrowSuperset + Substitute)."""
        resp = await client.get("/api/tools/configs/web_search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "web_search"
        assert data["enabled"] is True
        assert data["config"] == {}
        assert isinstance(data["description"], str) and data["description"]

        props = data["schema"]["properties"]
        assert props["host_allowlist"]["x_marker"] == "Narrow"
        assert props["host_denylist"]["x_marker"] == "NarrowSuperset"
        assert props["default_user_agent"]["x_marker"] == "Substitute"

    async def test_get_one_returns_404_for_unknown_tool(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tools/configs/nonexistent")
        assert resp.status_code == 404
        assert "Tool not found" in resp.json()["detail"]

    async def test_get_one_for_empty_config_tool(self, client: AsyncClient) -> None:
        """Originally this leg expected `shell_session_close` to use
        `_EmptyConfig` (per the leg's Edge Cases note), but F2-F5 wired
        every builtin tool to a category Config — `_TOOL_CLASSES` now
        has zero tools using `_EmptyConfig`. Logged in flight log.

        The endpoint behaviour we still want to lock in: GET on a tool
        whose Config has no marker-bearing fields returns a schema with
        no `x_marker` keys injected. `shell_session_close` uses
        `ExecutionConfig`, which carries Narrow markers, so we instead
        verify the helper-no-op contract via a probe: a tool whose
        schema fields are all unmarked yields no `x_marker` keys.

        We pick the simplest probe: confirm the endpoint returns 200
        and a valid `properties` dict, and that NO property has an
        empty/unknown `x_marker` value (only "Narrow" / "NarrowPrefix"
        / "NarrowSuperset" / "Substitute" / absent are valid)."""
        resp = await client.get("/api/tools/configs/shell_session_close")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "shell_session_close"
        valid_markers = {
            "Narrow",
            "NarrowPrefix",
            "NarrowSuperset",
            "Substitute",
        }
        props = data["schema"].get("properties", {})
        # Either properties is empty (helper no-op) OR every x_marker
        # value present is from the valid set.
        for prop in props.values():
            if "x_marker" in prop:
                assert prop["x_marker"] in valid_markers


# ── PUT /api/tools/configs/{name} ─────────────────────────────────────────


class TestUpsertToolConfig:
    async def test_put_validates_config_against_schema(self, client: AsyncClient) -> None:
        """Negative bound on a `>= 0` field → 422."""
        # `timeout_seconds_max` has `ge=1` per WebConfig — -1 violates.
        resp = await client.put(
            "/api/tools/configs/web_search",
            json={"config": {"timeout_seconds_max": -1}},
        )
        assert resp.status_code == 422

    async def test_put_422_response_is_json_serializable_for_model_validator(
        self, client: AsyncClient
    ) -> None:
        """Model-validator errors carry a raw exception in `ctx['error']`
        which is NOT JSON-serializable. Without `include_context=False`
        on `e.errors()`, FastAPI's JSONResponse crashes and the operator
        sees a 500 instead of a 422. Discovered during F6 L6 HAT scenario 3
        (operator narrowed timeout_seconds_max < timeout_seconds_default).

        WebConfig has a model-validator requiring
        `timeout_seconds_default <= timeout_seconds_max`. Submit a config
        that violates that without violating any field-level bound."""
        resp = await client.put(
            "/api/tools/configs/web_search",
            json={"config": {"timeout_seconds_max": 10}},
        )
        assert resp.status_code == 422, resp.text
        # Body must round-trip cleanly through JSON.
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) >= 1
        err = body["detail"][0]
        assert err["type"] == "value_error"
        assert "timeout_seconds" in err["msg"]
        # `ctx` must be absent or stringified — never carry a raw exception.
        if "ctx" in err:
            for v in err["ctx"].values():
                assert isinstance(v, (str, int, float, bool, list, dict, type(None))), v

    async def test_put_persists_enabled_and_config(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/tools/configs/web_search",
            json={"enabled": False, "config": {"timeout_seconds_max": 100}},
        )
        assert resp.status_code == 200
        # Subsequent GET shows the values.
        resp = await client.get("/api/tools/configs/web_search")
        data = resp.json()
        assert data["enabled"] is False
        assert data["config"]["timeout_seconds_max"] == 100

    async def test_put_replaces_config_wholesale(self, client: AsyncClient) -> None:
        """REPLACE-not-merge: existing override `host_allowlist=["a.com"]`
        + `timeout_seconds_max=99`; PUT `{"config": {"timeout_seconds_max":
        100}}` → `host_allowlist` is gone (replaced by Config's default),
        `timeout_seconds_max == 100`."""
        await client.put(
            "/api/tools/configs/web_search",
            json={
                "config": {
                    "timeout_seconds_max": 99,
                    "host_allowlist": ["a.com"],
                }
            },
        )
        # Replace with a new, different config dict.
        await client.put(
            "/api/tools/configs/web_search",
            json={"config": {"timeout_seconds_max": 100}},
        )
        resp = await client.get("/api/tools/configs/web_search")
        cfg = resp.json()["config"]
        assert cfg["timeout_seconds_max"] == 100
        # `host_allowlist` is back to the WebConfig default (empty list).
        assert cfg["host_allowlist"] == []

    async def test_put_preserves_omitted_top_level_keys(self, client: AsyncClient) -> None:
        """Existing row `enabled=False, config={"timeout_seconds_max": 100}`;
        PUT `{"enabled": true}` (no `config`) → row becomes
        `enabled=True` AND `config={"timeout_seconds_max": 100}` (unchanged
        — well, validated against the WebConfig defaults)."""
        # Seed
        await client.put(
            "/api/tools/configs/web_search",
            json={"enabled": False, "config": {"timeout_seconds_max": 100}},
        )
        # PUT only `enabled`
        await client.put(
            "/api/tools/configs/web_search",
            json={"enabled": True},
        )
        resp = await client.get("/api/tools/configs/web_search")
        data = resp.json()
        assert data["enabled"] is True
        # `config` preserved verbatim from the prior write — including
        # the `timeout_seconds_max=100` field plus the WebConfig defaults
        # for the other fields (saved by the prior validate-then-dump).
        assert data["config"]["timeout_seconds_max"] == 100

        # Symmetric: PUT `{"config": ...}` with no `enabled` preserves enabled.
        # First flip enabled back to False, then PUT a config-only update.
        await client.put(
            "/api/tools/configs/web_search",
            json={"enabled": False},
        )
        await client.put(
            "/api/tools/configs/web_search",
            json={"config": {"timeout_seconds_max": 60}},
        )
        resp = await client.get("/api/tools/configs/web_search")
        data = resp.json()
        # `enabled` preserved at False (was not in the second body).
        assert data["enabled"] is False
        assert data["config"]["timeout_seconds_max"] == 60

    async def test_put_with_empty_config_wipes_to_defaults(self, client: AsyncClient) -> None:
        """PUT `{"config": {}}` with an existing row carrying overrides
        → `model_validate({})` succeeds; saved `config` becomes the
        Config's default-dump (every field at its default value)."""
        # Seed with overrides
        await client.put(
            "/api/tools/configs/web_search",
            json={
                "config": {
                    "timeout_seconds_max": 99,
                    "host_allowlist": ["a.com"],
                }
            },
        )
        # Wipe to defaults
        await client.put(
            "/api/tools/configs/web_search",
            json={"config": {}},
        )
        resp = await client.get("/api/tools/configs/web_search")
        cfg = resp.json()["config"]
        # Defaults match WebConfig declared defaults.
        assert cfg["timeout_seconds_max"] == 120  # WebConfig default
        assert cfg["host_allowlist"] == []
        assert cfg["host_denylist"] == []
        assert cfg["redirect_cap"] == 5

    async def test_put_for_unknown_tool(self, client: AsyncClient) -> None:
        resp = await client.put("/api/tools/configs/nonexistent", json={"enabled": False})
        assert resp.status_code == 404


# ── POST /api/tools/configs/{name}/test ───────────────────────────────────


class TestTestEndpoint:
    async def test_test_endpoint_runs_web_search_with_fixture_query(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """POST /configs/web_search/test with a monkeypatched DDG backend.
        The endpoint runs `DDGSearchBackend.search` with the fixture
        query; output contains the fixture results."""
        captured = {}

        async def fake_search(self, query, max_results):
            captured["query"] = query
            captured["max_results"] = max_results
            return [
                SearchResult(
                    title="Fixture Result",
                    url="https://example.org/x",
                    snippet="A fixture snippet",
                ),
            ]

        monkeypatch.setattr(
            "the_one.tools._search_backends.DDGSearchBackend.search",
            fake_search,
        )
        resp = await client.post("/api/tools/configs/web_search/test")
        assert resp.status_code == 200
        data = resp.json()
        assert "Fixture Result" in data["output"]
        assert "https://example.org/x" in data["output"]
        assert isinstance(data["elapsed_ms"], float)
        assert captured["query"] == "the one cli agent"
        assert captured["max_results"] == 5

    async def test_test_endpoint_runs_fetch_url_with_fixture_url(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """POST /configs/fetch_url/test with a monkeypatched
        `_build_transport`. Output contains the readability-extracted
        markdown for the fixture HTML."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=(
                    b"<html><head><title>Fixture</title></head>"
                    b"<body><article><h1>Heading</h1>"
                    b"<p>Paragraph body content for the fixture page.</p>"
                    b"</article></body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            )

        def fake_build_transport(self, cfg):
            return httpx.MockTransport(handler)

        monkeypatch.setattr(
            "the_one.tools.web.FetchUrlTool._build_transport",
            fake_build_transport,
        )
        resp = await client.post("/api/tools/configs/fetch_url/test")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["output"], str)
        assert "[200]" in data["output"]
        # readability + markdownify yields markdown — the body content is
        # carried through in some form.
        assert "Paragraph" in data["output"] or "Heading" in data["output"]
        assert isinstance(data["elapsed_ms"], float)

    async def test_test_endpoint_rejects_non_testable_tool(self, client: AsyncClient) -> None:
        resp = await client.post("/api/tools/configs/shell/test")
        assert resp.status_code == 400
        assert resp.json()["detail"] == ("Tool shell does not support connection testing")

    async def test_test_endpoint_rejects_unknown_tool(self, client: AsyncClient) -> None:
        """404 must take precedence over 400."""
        resp = await client.post("/api/tools/configs/nonexistent/test")
        assert resp.status_code == 404

    async def test_test_endpoint_uses_operator_resolved_config_for_fetch_url(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Operator saves `fetch_url` with `host_denylist=["example.com"]`.
        POST /configs/fetch_url/test (fixture URL = https://example.com/).
        The endpoint MUST surface the constraint refusal as
        `[error] [constraint] host 'example.com' is in host_denylist`
        in the `output` field; HTTP 200; the diagnostic IS the value."""
        # Save the operator config with a denylist that blocks the fixture URL.
        await client.put(
            "/api/tools/configs/fetch_url",
            json={"config": {"host_denylist": ["example.com"]}},
        )

        # Monkeypatch the transport so we don't hit network even by accident
        # (the constraint check fires before transport is exercised).
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"should not be reached")

        def fake_build_transport(self, cfg):
            return httpx.MockTransport(handler)

        monkeypatch.setattr(
            "the_one.tools.web.FetchUrlTool._build_transport",
            fake_build_transport,
        )

        resp = await client.post("/api/tools/configs/fetch_url/test")
        assert resp.status_code == 200
        data = resp.json()
        # The denylist check refuses with the constraint formatter.
        assert "[error] [constraint]" in data["output"]
        assert "example.com" in data["output"]
        assert "host_denylist" in data["output"]

    async def test_test_endpoint_named_tool_isolation(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Operator saves `web_search` with `host_denylist=["example.com"]`
        AND `http_request` (also WebConfig) with NO denylist additions.
        POST /configs/fetch_url/test (which uses WebConfig). The endpoint
        must use `fetch_url`'s saved row (empty in this case → defaults)
        — NOT `http_request`'s and NOT `web_search`'s. Codifies the
        named-tool re-keying behaviour."""
        # Save `web_search` with a denylist.
        await client.put(
            "/api/tools/configs/web_search",
            json={"config": {"host_denylist": ["example.com"]}},
        )
        # Save `http_request` empty (defaults).
        await client.put(
            "/api/tools/configs/http_request",
            json={"config": {}},
        )
        # `fetch_url` has no saved row → operator default (no denylist).

        # Capture what `BuiltinToolProvider.get_tools` is called with.
        captured: dict = {}
        from the_one.tools.builtins import BuiltinToolProvider

        original = BuiltinToolProvider.get_tools

        def spy_get_tools(self, tool_configs=None, agent_overrides=None, agent_name=None):
            captured["tool_configs"] = tool_configs
            return original(self, tool_configs, agent_overrides, agent_name)

        monkeypatch.setattr(BuiltinToolProvider, "get_tools", spy_get_tools)

        # Avoid hitting network: route the transport to a MockTransport.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"OK")

        def fake_build_transport(self, cfg):
            return httpx.MockTransport(handler)

        monkeypatch.setattr(
            "the_one.tools.web.FetchUrlTool._build_transport",
            fake_build_transport,
        )

        resp = await client.post("/api/tools/configs/fetch_url/test")
        assert resp.status_code == 200

        # Re-keying assertion: every tool sharing WebConfig (web_search,
        # fetch_url, http_request, download_file) should carry
        # fetch_url's saved row (empty dict) in `tool_configs`.
        tcs = captured["tool_configs"]
        assert tcs["fetch_url"] == {}, "fetch_url should keep its own saved row (empty)"
        # Re-keyed siblings: the named tool's row replaces theirs.
        assert tcs["web_search"] == {}, "web_search must be re-keyed to fetch_url's empty row"
        assert tcs["http_request"] == {}, "http_request must be re-keyed to fetch_url's empty row"
        # And the resulting fetch_url request is NOT denied — the
        # endpoint succeeded with [200] from the fixture transport.
        # (If the re-keying were broken, web_search's denylist would
        # have been propagated through cross_configs[WebConfig] and
        # the request would have been refused.)
        assert "[200]" in resp.json()["output"]

    # ── F6 HAT addition — custom test inputs ──────────────────────────

    async def test_test_endpoint_accepts_custom_query_for_web_search(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """POST /configs/web_search/test with `{query: "custom"}` — the
        DDG backend MUST be invoked with the operator-supplied query, not
        the default fixture."""
        captured = {}

        async def fake_search(self, query, max_results):
            captured["query"] = query
            captured["max_results"] = max_results
            return [
                SearchResult(
                    title="R",
                    url="https://example.org/r",
                    snippet="s",
                ),
            ]

        monkeypatch.setattr(
            "the_one.tools._search_backends.DDGSearchBackend.search",
            fake_search,
        )
        resp = await client.post(
            "/api/tools/configs/web_search/test",
            json={"query": "custom"},
        )
        assert resp.status_code == 200
        assert captured["query"] == "custom"
        # max_results untouched → default
        assert captured["max_results"] == 5

    async def test_test_endpoint_accepts_custom_url_for_fetch_url(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """POST /configs/fetch_url/test with `{url: "https://other.example/"}`
        — FetchUrlTool MUST be invoked with that URL, not the default
        fixture."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(
                200,
                content=(
                    b"<html><head><title>X</title></head>"
                    b"<body><article><p>Body</p></article></body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            )

        def fake_build_transport(self, cfg):
            return httpx.MockTransport(handler)

        monkeypatch.setattr(
            "the_one.tools.web.FetchUrlTool._build_transport",
            fake_build_transport,
        )
        resp = await client.post(
            "/api/tools/configs/fetch_url/test",
            json={"url": "https://other.example/"},
        )
        assert resp.status_code == 200
        assert captured["url"] == "https://other.example/"

    async def test_test_endpoint_falls_back_to_default_on_empty_string(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """POST /configs/web_search/test with `{query: "  "}` — whitespace
        only should be treated as no override; default fixture query is
        used."""
        captured = {}

        async def fake_search(self, query, max_results):
            captured["query"] = query
            captured["max_results"] = max_results
            return []

        monkeypatch.setattr(
            "the_one.tools._search_backends.DDGSearchBackend.search",
            fake_search,
        )
        resp = await client.post(
            "/api/tools/configs/web_search/test",
            json={"query": "  "},
        )
        assert resp.status_code == 200
        assert captured["query"] == "the one cli agent"

    async def test_test_endpoint_ignores_unknown_keys(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """POST /configs/web_search/test with `{garbage: "x"}` — unknown
        keys are silently ignored; defaults used; no crash."""
        captured = {}

        async def fake_search(self, query, max_results):
            captured["query"] = query
            captured["max_results"] = max_results
            return []

        monkeypatch.setattr(
            "the_one.tools._search_backends.DDGSearchBackend.search",
            fake_search,
        )
        resp = await client.post(
            "/api/tools/configs/web_search/test",
            json={"garbage": "x"},
        )
        assert resp.status_code == 200
        assert captured["query"] == "the one cli agent"
        assert captured["max_results"] == 5
