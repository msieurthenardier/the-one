"""Sortie 08: the self-configuration server is owned by the server, not by the
agent form or an agent write.

Covers the attachment carry (DD2), the 422 on any per-agent override (DD3),
the `disabled_tools` strip (DD7), `override_for` at the build sites (DD4), the
`is_platform_surface` marker and the startup strip `strip_surface_overrides`
(DD4). The factory's registration exemption is in `tests/test_factory.py`.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import Encryptor
from the_one.mcp._tool import MCPClientTool, _normalize_source_name
from the_one.mcp.types import MCPTool
from the_one.self_configuration import credentials as sc_credentials
from the_one.self_configuration import manage
from the_one.self_configuration.constants import (
    SURFACE_ROW_NAME,
    SURFACE_TOOL_PREFIX,
    override_for,
)
from the_one.self_configuration.projection import build_describe_my_capabilities

REFUSAL = "Self-configuration tab"
PREFIXED = f"{SURFACE_TOOL_PREFIX}update_my_description"


@pytest.fixture(autouse=True)
def _isolated_registry():
    sc_credentials.clear_for_test()
    sc_credentials.register_credential_source_once()
    yield
    sc_credentials.clear_for_test()


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as client:
            yield SimpleNamespace(
                client=client,
                conn=conn,
                store=SQLiteAgentStore(conn, enc),
                mcp=MCPSourceRepository(conn, enc),
                enc=enc,
            )
    await conn.close()


async def _agent(env, name: str) -> None:
    resp = await env.client.post("/api/agents", json={"name": name, "description": "t"})
    assert resp.status_code == 201, resp.text


async def _enable(env, name: str) -> str:
    resp = await env.client.post(f"/api/agents/{name}/self-configuration")
    assert resp.status_code == 200, resp.text
    return resp.json()["source_id"]


async def _ordinary(env, source_id: str) -> str:
    await env.mcp.create(
        MCPSource(
            id=source_id,
            name=f"srv-{source_id}",
            type="streamable-http",
            config={"url": "https://example.com/mcp"},
        )
    )
    return source_id


async def _set_ids(env, name: str, ids: list[str]) -> None:
    cfg = await env.store.load(name)
    await env.store.save(cfg.model_copy(update={"mcp_source_ids": ids}))


async def _get(env, name: str) -> dict[str, Any]:
    resp = await env.client.get(f"/api/agents/{name}")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── DD2: the attachment carry (AC3, AC3b, AC4) ────────────────────────────


class TestAttachmentCarry:
    async def test_put_without_the_surface_id_keeps_it_at_its_stored_position(self, env) -> None:
        await _agent(env, "a")
        s = await _enable(env, "a")
        m1 = await _ordinary(env, "m1")
        m2 = await _ordinary(env, "m2")

        # stored [s, m1] -> a PUT of [m1] puts the surface back at index 0
        await _set_ids(env, "a", [s, m1])
        resp = await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": [m1]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["mcp_source_ids"] == [s, m1]
        assert (await _get(env, "a"))["mcp_source_ids"] == [s, m1]
        status = (await env.client.get("/api/agents/a/self-configuration")).json()
        assert status["enabled"] is True

        # stored [m1, m2, s] -> a PUT of [m2] clamps to len(incoming)
        await _set_ids(env, "a", [m1, m2, s])
        resp = await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": [m2]})
        assert resp.json()["mcp_source_ids"] == [m2, s]

        # adding ids while attached keeps the stored index
        await _set_ids(env, "a", [m1, s])
        resp = await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": [m1, m2]})
        assert resp.json()["mcp_source_ids"] == [m1, s, m2]

    async def test_put_listing_the_surface_id_does_not_duplicate_it(self, env) -> None:
        await _agent(env, "a")
        s = await _enable(env, "a")
        resp = await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": [s]})
        assert resp.json()["mcp_source_ids"] == [s]

    async def test_put_omitting_mcp_source_ids_keeps_only_the_surface(self, env) -> None:
        await _agent(env, "a")
        s = await _enable(env, "a")
        m1 = await _ordinary(env, "m1")
        await _set_ids(env, "a", [m1, s])
        resp = await env.client.put("/api/agents/a", json={"name": "a", "description": "x"})
        assert resp.status_code == 200, resp.text
        # the other attached ids still reset (an omitted field is not "preserve all")
        assert resp.json()["mcp_source_ids"] == [s]
        status = (await env.client.get("/api/agents/a/self-configuration")).json()
        assert status["enabled"] is True

    async def test_put_cannot_attach_an_orphaned_own_row(self, env) -> None:
        await _agent(env, "a")
        s = await _enable(env, "a")
        await _set_ids(env, "a", [])  # orphan: legacy data or a crash
        resp = await env.client.put("/api/agents/a", json={"name": "a", "mcp_source_ids": [s]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["mcp_source_ids"] == []
        status = (await env.client.get("/api/agents/a/self-configuration")).json()
        assert status["enabled"] is False
        assert status["orphaned_row"] is True
        assert status["source_id"] == s

    async def test_create_cannot_attach_an_own_surface_row(self, env) -> None:
        await _agent(env, "a")
        s = await _enable(env, "a")
        await env.store.delete("a")  # no cascade: the row is left behind
        resp = await env.client.post("/api/agents", json={"name": "a", "mcp_source_ids": [s]})
        assert resp.status_code == 201, resp.text
        assert resp.json()["mcp_source_ids"] == []

    async def test_a_foreign_surface_id_is_still_a_422(self, env) -> None:
        await _agent(env, "a")
        await _agent(env, "b")
        s = await _enable(env, "a")
        resp = await env.client.put("/api/agents/b", json={"name": "b", "mcp_source_ids": [s]})
        assert resp.status_code == 422
        resp = await env.client.post("/api/agents", json={"name": "c", "mcp_source_ids": [s]})
        assert resp.status_code == 422


# ── DD3: any per-agent entry for the surface is a 422 (AC6, AC7) ──────────


class TestOverrideRefusal:
    @pytest.mark.parametrize(
        "entry",
        [
            {"disabled_tools": []},
            {"disabled_tools": ["describe_my_capabilities"]},
            {"enabled_tools": ["get_my_configuration"]},
            {"bearer_token": "attacker-supplied"},
            {"headers": {"X-A": "b"}},
            ["not", "a", "dict"],
            "text",
        ],
    )
    async def test_non_empty_entry_is_refused_and_nothing_is_stored(self, env, entry) -> None:
        await _agent(env, "a")
        body = {"name": "a", "mcp_overrides": {SURFACE_ROW_NAME: entry}}
        resp = await env.client.put("/api/agents/a", json=body)
        assert resp.status_code == 422, resp.text
        assert REFUSAL in resp.json()["detail"]
        assert (await _get(env, "a"))["mcp_overrides"] in (None, {})

        resp = await env.client.post("/api/agents", json={**body, "name": "n"})
        assert resp.status_code == 422, resp.text
        assert REFUSAL in resp.json()["detail"]
        assert (await env.client.get("/api/agents/n")).status_code == 404

    @pytest.mark.parametrize("entry", [{}, None])
    async def test_empty_entry_is_accepted_and_dropped(self, env, entry) -> None:
        await _agent(env, "a")
        body = {"name": "a", "mcp_overrides": {SURFACE_ROW_NAME: entry}}
        resp = await env.client.put("/api/agents/a", json=body)
        assert resp.status_code == 200, resp.text
        assert SURFACE_ROW_NAME not in (resp.json()["mcp_overrides"] or {})
        resp = await env.client.post("/api/agents", json={**body, "name": "n"})
        assert resp.status_code == 201, resp.text
        assert SURFACE_ROW_NAME not in ((await _get(env, "n"))["mcp_overrides"] or {})

    async def test_save_omitting_the_key_is_accepted_and_removes_a_stored_entry(self, env) -> None:
        await _agent(env, "a")
        cfg = await env.store.load("a")
        await env.store.save(
            cfg.model_copy(
                update={
                    "mcp_overrides": {
                        SURFACE_ROW_NAME: {"disabled_tools": ["update_my_description"]}
                    }
                }
            )
        )
        assert (await env.store.load("a")).mcp_overrides  # seeded

        resp = await env.client.put("/api/agents/a", json={"name": "a", "description": "x"})
        assert resp.status_code == 200, resp.text
        assert (await env.store.load("a")).mcp_overrides is None
        assert "self-configuration" not in ((await _get(env, "a"))["mcp_overrides"] or {})

    async def test_removing_the_key_keeps_other_servers_overrides(self, env) -> None:
        await _agent(env, "a")
        cfg = await env.store.load("a")
        await env.store.save(
            cfg.model_copy(
                update={
                    "mcp_overrides": {
                        SURFACE_ROW_NAME: {"disabled_tools": ["x"]},
                        "other": {"disabled_tools": ["y"]},
                    }
                }
            )
        )
        resp = await env.client.put("/api/agents/a", json={"name": "a"})
        assert resp.status_code == 200, resp.text
        assert (await env.store.load("a")).mcp_overrides == {"other": {"disabled_tools": ["y"]}}


# ── DD7: disabled_tools cannot withhold a surface tool (AC9) ──────────────


class TestDisabledToolsStrip:
    async def test_surface_names_are_stripped_and_others_kept(self, env) -> None:
        await _agent(env, "a")
        keep = ["mcp__github__delete_repo", "shell"]
        resp = await env.client.put(
            "/api/agents/a", json={"name": "a", "disabled_tools": [PREFIXED, *keep]}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["disabled_tools"] == keep
        resp = await env.client.post(
            "/api/agents", json={"name": "n", "disabled_tools": [*keep, PREFIXED]}
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["disabled_tools"] == keep

    async def test_a_mixed_list_and_a_non_list_are_left_for_validation(self, env) -> None:
        await _agent(env, "a")
        resp = await env.client.put(
            "/api/agents/a", json={"name": "a", "disabled_tools": [PREFIXED, 5]}
        )
        assert resp.status_code == 422, resp.text
        resp = await env.client.put("/api/agents/a", json={"name": "a", "disabled_tools": PREFIXED})
        assert resp.status_code == 422, resp.text


# ── DD4: override_for, the marker, the prefix ─────────────────────────────


def _src(name: str, config: dict | None = None, sid: str = "s1") -> MCPSource:
    return MCPSource(
        id=sid, name=name, type="streamable-http", config=config or {"url": "http://x"}
    )


class TestOverrideFor:
    def test_surface_row_gets_none_and_others_get_their_entry(self) -> None:
        surface = _src(SURFACE_ROW_NAME, {"self_configuration": {"agent": "a"}})
        ordinary = _src("github")
        overrides = {
            SURFACE_ROW_NAME: {"disabled_tools": ["x"]},
            "github": {"disabled_tools": ["y"]},
        }
        assert override_for(overrides, surface) is None
        assert override_for(overrides, ordinary) == {"disabled_tools": ["y"]}
        assert override_for(None, ordinary) is None
        assert override_for(None, surface) is None

    def test_the_marker_decides_not_the_name(self) -> None:
        markerless = _src(SURFACE_ROW_NAME)
        assert override_for({SURFACE_ROW_NAME: {"disabled_tools": ["x"]}}, markerless) == {
            "disabled_tools": ["x"]
        }
        legacy_named_surface = _src(
            "self-configuration (a)", {"self_configuration": {"agent": "a"}}
        )
        assert (
            override_for(
                {"self-configuration (a)": {"disabled_tools": ["x"]}}, legacy_named_surface
            )
            is None
        )

    def test_tool_prefix_matches_the_tool_name_normalization(self) -> None:
        assert SURFACE_TOOL_PREFIX == f"mcp__{_normalize_source_name(SURFACE_ROW_NAME)}__"

    def test_manage_re_exports_the_constant(self) -> None:
        assert manage.SURFACE_ROW_NAME == SURFACE_ROW_NAME


class TestIsPlatformSurface:
    def _tool(self, source: MCPSource) -> MCPClientTool:
        mt = MCPTool(
            name="get_my_configuration",
            description="d",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            annotations=None,
        )
        return MCPClientTool(mt, source.id, source.name, "a", source)

    def test_true_for_a_marked_row_even_after_an_override_is_applied(self) -> None:
        from the_one.mcp._tool_provider import _apply_override

        src = _src(SURFACE_ROW_NAME, {"url": "http://x", "self_configuration": {"agent": "a"}})
        assert self._tool(src).is_platform_surface is True
        applied = _apply_override(src, {"disabled_tools": ["x"]})
        assert self._tool(applied).is_platform_surface is True

    def test_false_for_an_ordinary_row_even_one_named_like_the_surface(self) -> None:
        assert self._tool(_src("github")).is_platform_surface is False
        assert self._tool(_src(SURFACE_ROW_NAME)).is_platform_surface is False


def _cache(*names: str) -> dict[str, Any]:
    return {
        "url": "http://127.0.0.1:1/mcp/self-configuration/",
        "self_configuration": {"agent": "a"},
        "_cache": {"tools": [{"name": n, "description": "", "input_schema": {}} for n in names]},
    }


_FOUR = (
    "get_my_configuration",
    "describe_my_capabilities",
    "update_my_description",
    "update_my_system_prompt",
)


class TestBuildSitesIgnoreAStoredEntry:
    @pytest.mark.parametrize(
        "override", [{"disabled_tools": ["update_my_description"]}, {"enabled_tools": []}]
    )
    async def test_projection_lists_all_four_tools(self, env, override) -> None:
        await env.mcp.create(_src(SURFACE_ROW_NAME, _cache(*_FOUR), sid="sc"))
        await env.mcp.create(
            _src("github", _cache("a_tool", "b_tool") | {"self_configuration": None}, sid="gh")
        )
        config = AgentConfig(
            name="a",
            mcp_source_ids=["sc", "gh"],
            mcp_overrides={
                SURFACE_ROW_NAME: override,
                "github": {"disabled_tools": ["b_tool"]},
            },
        )
        result = await build_describe_my_capabilities(
            config,
            tool_config_repo=ToolConfigRepository(env.conn, env.enc),
            mcp_repo=env.mcp,
        )
        by_name = {s["name"]: s for s in result["mcp_sources"]}
        assert set(by_name[SURFACE_ROW_NAME]["tools"]) == set(_FOUR)
        # an ordinary source's override still filters
        assert by_name["github"]["tools"] == ["a_tool"]

    @pytest.mark.parametrize(
        "override", [{"disabled_tools": ["update_my_description"]}, {"enabled_tools": []}]
    )
    async def test_search_tools_index_lists_all_four_tools(self, override) -> None:
        from the_one.agent.factory import _build_source_index

        surface = _src(SURFACE_ROW_NAME, _cache(*_FOUR), sid="sc")
        ordinary = _src(
            "github",
            {"url": "http://x", **_cache("a_tool", "b_tool")} | {"self_configuration": None},
            sid="gh",
        )
        rows = {"sc": surface, "gh": ordinary}
        repo = MagicMock()
        repo.get = AsyncMock(side_effect=lambda sid: rows[sid])
        config = AgentConfig(
            name="a",
            mcp_source_ids=["sc", "gh"],
            mcp_overrides={
                SURFACE_ROW_NAME: override,
                "github": {"disabled_tools": ["b_tool"]},
            },
        )
        index: dict[str, Any] = {}
        with (
            patch("the_one.agent.factory.settings") as mock_settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=MagicMock()),
            patch("the_one.db.repositories.MCPSourceRepository", return_value=repo),
        ):
            mock_settings.data_dir = "/tmp/unused"
            await _build_source_index(config=config, agent_name="a", source_index=index)
        assert set(index[SURFACE_ROW_NAME]["tool_names_prefixed"]) == {
            f"{SURFACE_TOOL_PREFIX}{t}" for t in _FOUR
        }
        assert index["github"]["tool_names_prefixed"] == ["mcp__github__a_tool"]


# ── DD4: the startup strip (AC13, AC16) ───────────────────────────────────


@pytest.fixture
async def strip_env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    yield SimpleNamespace(store=SQLiteAgentStore(conn, enc))
    await conn.close()


async def _save(env, name: str, **fields: Any) -> None:
    await env.store.save(AgentConfig(name=name, **fields))


class TestStripSurfaceOverrides:
    async def test_owner_of_an_enabled_surface_is_cleaned(self, strip_env, caplog) -> None:
        await _save(
            strip_env,
            "owner",
            mcp_source_ids=["sc"],
            mcp_overrides={
                SURFACE_ROW_NAME: {"disabled_tools": ["update_my_description"]},
                "github": {"disabled_tools": ["z"]},
            },
            disabled_tools=[PREFIXED, "shell", "mcp__github__z"],
        )
        with caplog.at_level(logging.INFO, logger="the_one.self_configuration.manage"):
            await manage.strip_surface_overrides(strip_env.store)
        got = await strip_env.store.load("owner")
        assert got.mcp_overrides == {"github": {"disabled_tools": ["z"]}}
        assert got.disabled_tools == ["shell", "mcp__github__z"]
        assert got.mcp_source_ids == ["sc"]
        assert any("'owner'" in r.getMessage() for r in caplog.records if r.levelno == logging.INFO)

    async def test_a_disabled_agent_with_a_leftover_entry_is_cleaned_to_none(
        self, strip_env
    ) -> None:
        await _save(strip_env, "off", mcp_overrides={SURFACE_ROW_NAME: {"enabled_tools": []}})
        await manage.strip_surface_overrides(strip_env.store)
        assert (await strip_env.store.load("off")).mcp_overrides is None

    async def test_a_disabled_tools_only_withhold_is_cleaned(self, strip_env) -> None:
        await _save(strip_env, "dt", disabled_tools=[PREFIXED])
        await manage.strip_surface_overrides(strip_env.store)
        assert (await strip_env.store.load("dt")).disabled_tools == []

    async def test_a_legacy_named_key_is_left_alone(self, strip_env) -> None:
        legacy = {"self-configuration (x)": {"disabled_tools": ["a"]}}
        await _save(strip_env, "x", mcp_overrides=legacy)
        await manage.strip_surface_overrides(strip_env.store)
        assert (await strip_env.store.load("x")).mcp_overrides == legacy

    async def test_an_agent_with_nothing_to_change_is_not_saved(
        self, strip_env, monkeypatch
    ) -> None:
        await _save(
            strip_env,
            "clean",
            disabled_tools=["shell"],
            mcp_overrides={"g": {"disabled_tools": ["a"]}},
        )
        await _save(strip_env, "dirty", disabled_tools=[PREFIXED])
        saved: list[str] = []
        real_save = strip_env.store.save

        async def spy(cfg):
            saved.append(cfg.name)
            await real_save(cfg)

        monkeypatch.setattr(strip_env.store, "save", spy)
        await manage.strip_surface_overrides(strip_env.store)
        assert saved == ["dirty"]

    async def test_one_failing_agent_is_skipped_with_a_warning_and_the_rest_are_cleaned(
        self, strip_env, monkeypatch, caplog
    ) -> None:
        await _save(strip_env, "bad", disabled_tools=[PREFIXED])
        await _save(strip_env, "good", disabled_tools=[PREFIXED])
        real_load = strip_env.store.load

        async def load(name):
            if name == "bad":
                raise RuntimeError("cannot decrypt")
            return await real_load(name)

        monkeypatch.setattr(strip_env.store, "load", load)
        with caplog.at_level(logging.WARNING, logger="the_one.self_configuration.manage"):
            await manage.strip_surface_overrides(strip_env.store)
        assert any(
            "'bad'" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records
        )
        monkeypatch.undo()
        assert (await strip_env.store.load("good")).disabled_tools == []
        assert (await strip_env.store.load("bad")).disabled_tools == [PREFIXED]

    async def test_a_failing_listing_never_raises(self, strip_env, monkeypatch, caplog) -> None:
        async def broken():
            raise RuntimeError("db gone")

        monkeypatch.setattr(strip_env.store, "list_agents", broken)
        with caplog.at_level(logging.WARNING, logger="the_one.self_configuration.manage"):
            await manage.strip_surface_overrides(strip_env.store)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
