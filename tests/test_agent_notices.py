"""Derived tool-override notices on every agent response (sortie 07 leg 2, DD6)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import ToolConfig
from the_one.interfaces.web import api as api_module
from the_one.tools import override_validation as ov
from the_one.tools.builtins import _TOOL_CLASSES


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        app = shared_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


@pytest.fixture(autouse=True)
def _fresh_memo():
    ov._memo.clear()
    yield
    ov._memo.clear()


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    (tmp_path / "other").mkdir()
    return root


def _rows(**configs) -> dict[str, ToolConfig]:
    return {n: ToolConfig(name=n, config=c) for n, c in configs.items()}


# ── AC5/AC6: the notice itself and its scope ─────────────────────────────


class TestComputeNotices:
    def test_narrowed_path_notice_shape(self, work, tmp_path):
        outside = str(tmp_path / "other")
        cfg = AgentConfig(
            name="a", tool_overrides={"read_file": {"path_allowlist": [str(work), outside]}}
        )
        (n,) = ov.compute_notices(cfg, _rows(read_file={"path_allowlist": [str(work)]}))
        assert n == {
            "kind": "tool_override_narrowed",
            "tool": "read_file",
            "field": "path_allowlist",
            "field_title": "Allowed paths",
            "dropped": [outside],
            "effective": [str(work)],
            "message": (
                f"read_file's Allowed paths was narrowed by the app-wide setting: "
                f"`{outside}` no longer applies."
            ),
        }

    def test_stored_form_not_canonical(self, work):
        # `~` stays `~` in the notice (leg 4 stores `effective` as the field value).
        cfg = AgentConfig(
            name="a", tool_overrides={"read_file": {"path_allowlist": ["~/zz-elsewhere"]}}
        )
        (n,) = ov.compute_notices(cfg, _rows(read_file={"path_allowlist": [str(work)]}))
        assert n["dropped"] == ["~/zz-elsewhere"]

    def test_was_any_host_sentence(self):
        cfg = AgentConfig(name="a", tool_overrides={"http_request": {"host_allowlist": []}})
        rows = _rows(http_request={"host_allowlist": ["a.example.com"]})
        (n,) = ov.compute_notices(cfg, rows)
        assert n["dropped"] == []
        assert n["effective"] == ["a.example.com"]
        assert n["message"] == (
            "http_request's Allowed hosts was any host; the app-wide setting now limits it "
            "to its own list."
        )

    def test_invalid_value_notice(self):
        cfg = AgentConfig(name="a", tool_overrides={"shell": {"timeout_seconds_max": -5}})
        (n,) = ov.compute_notices(cfg, {})
        assert n["field"] == "timeout_seconds_max"
        assert n["dropped"] == [-5]
        assert n["effective"] == 1
        assert "can't be used" in n["message"]

    def test_fitting_override_has_no_notice(self):
        cfg = AgentConfig(name="a", tool_overrides={"shell": {"timeout_seconds_max": 60}})
        assert ov.compute_notices(cfg, {}) == []

    def test_coupled_change_is_never_a_notice(self):
        # The default follows a lower app-wide maximum: report-only, no notice.
        cfg = AgentConfig(name="a", tool_overrides={"shell": {"timeout_seconds_max": 10}})
        assert ov.compute_notices(cfg, {}) == []

    def test_hidden_field_raises_no_notice(self, work):
        # write_file shows only path_allowlist/path_denylist.
        cfg = AgentConfig(
            name="a", tool_overrides={"write_file": {"read_size_cap_bytes": 99_999_999}}
        )
        assert ov.compute_notices(cfg, {}) == []

    def test_disabled_for_agent_raises_none(self, work, tmp_path):
        cfg = AgentConfig(
            name="a",
            disabled_tools=["read_file"],
            tool_overrides={"read_file": {"path_allowlist": [str(tmp_path / "other")]}},
        )
        assert ov.compute_notices(cfg, _rows(read_file={"path_allowlist": [str(work)]})) == []

    def test_disabled_app_wide_raises_none(self, work, tmp_path):
        cfg = AgentConfig(
            name="a", tool_overrides={"read_file": {"path_allowlist": [str(tmp_path / "other")]}}
        )
        rows = {
            "read_file": ToolConfig(
                name="read_file", config={"path_allowlist": [str(work)]}, enabled=False
            )
        }
        assert ov.compute_notices(cfg, rows) == []

    def test_unknown_tool_is_skipped(self):
        cfg = AgentConfig(name="a", tool_overrides={"gone_tool": {"x": 1}})
        assert ov.compute_notices(cfg, {}) == []

    def test_no_overrides(self):
        assert ov.compute_notices(AgentConfig(name="a"), {}) == []


# ── The render predicate against the client's allowed() rule ─────────────


def _client_allowed(prop: dict) -> bool:
    """``tool-config-fields.js::allowed`` written out."""
    if prop.get("type") == "boolean":
        return True
    return prop.get("x_marker") in {
        "Narrow",
        "NarrowAnyWhenEmpty",
        "NarrowSuperset",
        "NarrowPrefix",
        "Substitute",
    }


def test_render_predicate_matches_the_client_rule_for_every_builtin_field():
    checked = 0
    for name, cls in sorted(_TOOL_CLASSES.items()):
        config_cls = cls.Config
        schema = api_module._enrich_schema_with_markers(config_cls.model_json_schema(), config_cls)
        schema = api_module._filter_schema_to_config_fields(schema, cls)
        props = schema.get("properties", {})
        for field in config_cls.model_fields:
            expected = field in props and _client_allowed(props[field])
            assert ov.agent_tab_renders(cls, field) is expected, f"{name}.{field}"
            checked += 1
    assert checked > 20


# ── AC5: all five routes ─────────────────────────────────────────────────


async def _seed_stale(name: str, tool_overrides: dict) -> None:
    store = await api_module._agent_store()
    await store.save(AgentConfig(name=name, tool_overrides=tool_overrides))


async def _set_tool(client, name, config):
    resp = await client.put(f"/api/tools/configs/{name}", json={"config": config})
    assert resp.status_code == 200, resp.text


class TestRoutes:
    async def test_notices_on_all_five_routes(self, client, work, tmp_path):
        outside = str(tmp_path / "other")
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        await _seed_stale("a", {"read_file": {"path_allowlist": [outside]}})

        listed = [x for x in (await client.get("/api/agents")).json() if x["name"] == "a"][0]
        got = (await client.get("/api/agents/a")).json()
        put = (await client.put("/api/agents/a", json={"description": "d"})).json()
        renamed = (await client.post("/api/agents/a/rename", json={"new_name": "b"})).json()
        for body in (listed, got, put, renamed):
            assert [n["field"] for n in body["notices"]] == ["path_allowlist"], body
            assert body["notices"][0]["dropped"] == [outside]

        created = await client.post("/api/agents", json={"name": "c"})
        assert created.json()["notices"] == []

    async def test_empty_list_when_none(self, client):
        await client.post("/api/agents", json={"name": "x"})
        assert (await client.get("/api/agents/x")).json()["notices"] == []
        assert (await client.get("/api/agents")).json()[0]["notices"] == []


# ── AC7: cost and freshness ──────────────────────────────────────────────


class TestCost:
    async def test_one_repository_read_per_request_including_the_list(self, client, work, tmp_path):
        from the_one.db.repositories import ToolConfigRepository

        for i in range(3):
            await _seed_stale(f"a{i}", {"read_file": {"path_allowlist": [str(tmp_path / "other")]}})
        calls = []
        real = ToolConfigRepository.list

        async def spy(self):
            calls.append(1)
            return await real(self)

        with patch.object(ToolConfigRepository, "list", spy):
            await client.get("/api/agents")
            assert len(calls) == 1
            calls.clear()
            await client.get("/api/agents/a0")
            assert len(calls) == 1
            calls.clear()
            await client.put("/api/agents/a1", json={"description": "d"})
            assert len(calls) == 1

    async def test_clip_runs_off_the_event_loop(self, client, work, tmp_path):
        await _seed_stale("a", {"read_file": {"path_allowlist": [str(tmp_path / "other")]}})
        hops = []
        real = asyncio.to_thread

        async def spy(fn, *a, **k):
            hops.append(fn.__name__)
            return await real(fn, *a, **k)

        with patch.object(api_module.asyncio, "to_thread", spy):
            await client.get("/api/agents/a")
        assert "compute_notices_for_many" in hops

    async def test_list_route_is_one_thread_hop(self, client, tmp_path):
        for i in range(3):
            await _seed_stale(f"a{i}", {"read_file": {"path_allowlist": [str(tmp_path / "o")]}})
        hops = []
        real = asyncio.to_thread

        async def spy(fn, *a, **k):
            hops.append(fn.__name__)
            return await real(fn, *a, **k)

        with patch.object(api_module.asyncio, "to_thread", spy):
            await client.get("/api/agents")
        assert hops.count("compute_notices_for_many") == 1


class TestMemo:
    def test_recomputes_only_when_an_input_changes(self, work, tmp_path):
        outside = str(tmp_path / "other")
        cfg = AgentConfig(name="a", tool_overrides={"read_file": {"path_allowlist": [outside]}})
        rows = _rows(read_file={"path_allowlist": [str(work)]})
        real = ov.clip_override
        calls = []

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        with patch.object(ov, "clip_override", counting):
            first = ov.compute_notices(cfg, rows)
            again = ov.compute_notices(cfg, rows)
            assert first == again
            assert len(calls) == 1
            # The override entry changes.
            cfg2 = AgentConfig(
                name="a", tool_overrides={"read_file": {"path_allowlist": [outside, "/zz"]}}
            )
            ov.compute_notices(cfg2, rows)
            assert len(calls) == 2
            # The tool-config row changes.
            ov.compute_notices(cfg, _rows(read_file={"path_allowlist": [str(work), outside]}))
            assert len(calls) == 3
            # Back to the first inputs: cached.
            ov.compute_notices(cfg, rows)
            assert len(calls) == 3

    def test_scope_filter_runs_outside_the_memo(self, work, tmp_path):
        outside = str(tmp_path / "other")
        entry = {"read_file": {"path_allowlist": [outside]}}
        rows = _rows(read_file={"path_allowlist": [str(work)]})
        on = AgentConfig(name="a", tool_overrides=entry)
        off = AgentConfig(name="a", tool_overrides=entry, disabled_tools=["read_file"])
        assert len(ov.compute_notices(on, rows)) == 1
        assert ov.compute_notices(off, rows) == []
        assert len(ov.compute_notices(on, rows)) == 1

    def test_memo_is_bounded_and_holds_no_raw_secret(self, monkeypatch):
        monkeypatch.setattr(ov, "_MEMO_SIZE", 4)
        for i in range(10):
            cfg = AgentConfig(name="a", tool_overrides={"shell": {"timeout_seconds_max": -i - 1}})
            ov.compute_notices(cfg, {})
        assert len(ov._memo) == 4
        assert all(len(k) == 64 and set(k) <= set("0123456789abcdef") for k in ov._memo)
