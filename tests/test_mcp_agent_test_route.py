"""Sortie 09 leg 2: ``POST /api/mcp-sources/{source_id}/test/agent`` (DD6).

Drives the real route against the in-process key-checking server. The persistence
modes are also checked at the helper boundary (the ``cache_write`` each helper is
given), and the end-to-end test proves two agents on one source each see their own tools.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from tests._agent_mcp_world import KEY1, KEY2, SID, world
from the_one.db.models import MCPSource
from the_one.mcp import _tool_provider as provider_mod
from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError

URL = f"/api/mcp-sources/{SID}/test/agent"
SECRET_KEY = "distinctive-key-zq93"


@pytest.fixture
def world_(tmp_path, monkeypatch):
    return world(tmp_path, monkeypatch)


def _cache_of(src) -> dict:
    return dict((src.config or {}).get("_cache") or {})


async def _post(w, agent, overrides=None):
    return await w.api.post(URL, json={"agent": agent, "overrides": overrides})


def _spy(name):
    """Wrap an api.py helper so the kwargs it is given can be read back."""
    from the_one.interfaces.web import api

    calls: list[dict] = []
    real = getattr(api, name)

    async def wrapper(*a, **k):
        calls.append(dict(k))
        return await real(*a, **k)

    return calls, patch.object(api, name, wrapper)


# --- AC7: the contract of the route ---------------------------------------------------


async def test_unknown_source_agent_and_malformed_bodies(world_):
    async with world_ as w:
        assert (await w.api.post("/api/mcp-sources/nope/test/agent", json={})).status_code == 404
        resp = await _post(w, "ghost")
        assert resp.status_code == 404
        for bad in (
            {"agent": 5},
            {"agent": ""},
            {"agent": None, "overrides": []},
            {"agent": None, "overrides": "x"},
        ):
            resp = await w.api.post(URL, json=bad)
            assert resp.status_code == 422, bad
            assert resp.json()["detail"][0]["loc"][0] == "body"
        assert (await w.api.post(URL, json=[1])).status_code == 422
        assert (await w.api.post(URL, content=b"{nope")).status_code == 422
        assert w.requests() == []


async def test_a_self_configuration_row_is_refused(world_):
    async with world_ as w:
        await w.repo.create(
            MCPSource(
                id="surf",
                name="self-configuration (x)",
                type="streamable-http",
                config={"url": "http://localhost/mcp", "self_configuration": {"agent": "x"}},
            )
        )
        from the_one.self_configuration import manage

        row = await w.repo.get("surf")
        if not manage.is_surface_row(row):
            pytest.skip("surface marker shape changed")
        resp = await w.api.post("/api/mcp-sources/surf/test/agent", json={"agent": None})
        assert resp.status_code == 422


async def test_a_refused_value_is_a_422_in_the_save_shape(world_):
    async with world_ as w:
        resp = await _post(w, None, {"headers": {"Host": "evil"}})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail[0]["loc"] == ["mcp_overrides", "srv", "headers", "Host"]
        assert detail[0]["type"] == "mcp_override"
        assert w.requests() == []


# --- AC8: needs_values ---------------------------------------------------------------


async def test_a_keyless_agent_on_a_blank_library_header_needs_values_without_connecting(world_):
    async with world_ as w:
        await w.save_agent("plain")
        for agent in ("plain", None):
            resp = await _post(w, agent)
            assert resp.status_code == 200
            assert resp.json() == {"status": "needs_values", "missing": ["X-Api-Key"]}
        assert w.requests() == []  # the key server saw no request


async def test_a_blank_or_null_unsaved_value_is_refused_without_connecting(world_):
    async with world_ as w:
        await w.save_agent("a", KEY1)
        for value in ("  ", None):
            resp = await _post(w, "a", {"headers": {"X-Api-Key": value}})
            assert resp.status_code == 422, value
        assert w.requests() == []


# --- AC10 / AC11: modes, persistence, no posture ---------------------------------------


async def test_stored_credentials_write_the_per_agent_row_and_never_the_shared_cache(world_):
    async with world_ as w:
        await w.save_agent("a", KEY2)
        before = _cache_of(await w.repo.get(SID))
        calls, patched = _spy("_build_and_test_no_auth_mcp")
        with patched:
            resp = await _post(w, "a")
        body = resp.json()
        assert body["status"] == "ok"
        assert {t["name"] for t in body["tools"]} == {"echo", "add"}
        assert calls[0]["cache_write"] == "none" and calls[0]["record_era"] is False
        assert calls[0]["classify"] is True and calls[0]["from_fallthrough"] is True
        row = await w.cache.get("a", SID)
        assert {t["name"] for t in row["tools"]} == {"echo", "add"}
        after = _cache_of(await w.repo.get(SID))
        assert after == before  # no tools, no auth_posture, no last_check
        assert "auth_posture" not in after and "last_check" not in after


async def test_no_override_or_no_agent_writes_the_shared_cache_without_posture(
    tmp_path, monkeypatch
):
    async with world(tmp_path, monkeypatch, library_headers={"X-Api-Key": KEY1}) as w:
        await w.save_agent("plain")
        for agent, overrides in (("plain", None), (None, None), (None, {"enabled_tools": ["x"]})):
            await w.repo.merge_cache(SID, {}, delete=("tools", "capabilities", "last_updated"))
            calls, patched = _spy("_build_and_test_no_auth_mcp")
            with patched:
                resp = await _post(w, agent, overrides)
            assert resp.json()["status"] == "ok", (agent, overrides)
            assert calls[0]["cache_write"] == "shared_no_posture"
            cache = _cache_of(await w.repo.get(SID))
            assert {t["name"] for t in cache["tools"]} == {"echo"}
            for field in ("capabilities", "server_info", "protocol_version", "last_updated"):
                assert field in cache
            assert "auth_posture" not in cache and "last_check" not in cache
        assert await w.cache.get_for_agent("plain") == {}  # no per-agent row for a plain agent


async def test_an_unsaved_value_or_removal_writes_nothing(world_):
    async with world_ as w:
        await w.save_agent(
            "a",
            None,
            extra={
                "mcp_overrides": {"srv": {"headers": {"X-Api-Key": KEY1, "X-Other": "keep-me-1"}}}
            },
        )
        await w.build_tools("a")  # fills the row with KEY1's tools
        row_before = await w.cache.get("a", SID)
        shared_before = _cache_of(await w.repo.get(SID))

        # an unsaved NEW value
        calls, patched = _spy("_build_and_test_no_auth_mcp")
        with patched:
            resp = await _post(w, "a", {"headers": {"X-Api-Key": KEY2}})
        assert {t["name"] for t in resp.json()["tools"]} == {"echo", "add"}
        assert calls[0]["cache_write"] == "none"
        assert await w.cache.get("a", SID) == row_before

        # an unsaved removal: masks for the stored name only, one name left out
        calls, patched = _spy("_build_and_test_no_auth_mcp")
        with patched:
            resp = await _post(w, "a", {"headers": {"X-Api-Key": "__MASKED__"}})
        assert resp.json()["status"] == "ok"
        assert calls[0]["cache_write"] == "none"
        assert await w.cache.get("a", SID) == row_before
        assert _cache_of(await w.repo.get(SID)) == shared_before


async def test_create_mode_with_overrides_persists_nothing(world_):
    async with world_ as w:
        calls, patched = _spy("_build_and_test_no_auth_mcp")
        with patched:
            resp = await _post(w, None, {"headers": {"X-Api-Key": KEY2}})
        assert {t["name"] for t in resp.json()["tools"]} == {"echo", "add"}
        assert calls[0]["cache_write"] == "none"
        assert _cache_of(await w.repo.get(SID)).get("tools") is None
        assert await w.cache.get_for_agent("anyone") == {}


async def test_a_rejected_key_is_an_error_without_consent_and_writes_nothing(world_):
    async with world_ as w:
        await w.save_agent("a", "wrong-key-0000")
        resp = await _post(w, "a")
        body = resp.json()
        assert body["status"] == "error" and "consent_url" not in body
        assert "MCPCredentialsRejected" in body["error"]
        assert "wrong-key-0000" not in resp.text
        assert await w.cache.get("a", SID) is None
        assert "last_check" not in _cache_of(await w.repo.get(SID))


async def test_stdio_sources_use_the_stdio_helper_in_each_mode(world_):
    async with world_ as w:
        await w.repo.create(
            MCPSource(
                id="std",
                name="std",
                type="stdio",
                config={"command": "echo", "args": [], "env": {"API_KEY": ""}},
            )
        )
        await w.save_agent(
            "s", None, extra={"mcp_overrides": {"std": {"env": {"API_KEY": "stdio-secret-1"}}}}
        )
        cfg = (await w.api.get("/api/agents/s")).json()
        cfg["mcp_source_ids"] = ["std"]
        assert (await w.api.put("/api/agents/s", json=cfg)).status_code == 200
        seen = []

        async def fake(source, source_id, repo, **kw):
            seen.append((dict(source.secrets), kw))
            return {"status": "ok", "tools": [{"name": "t"}], "capabilities": {}}

        from the_one.interfaces.web import api

        with patch.object(api, "_build_and_test_stdio_mcp", fake):
            resp = await w.api.post(
                "/api/mcp-sources/std/test/agent", json={"agent": "s", "overrides": None}
            )
        assert resp.json()["status"] == "ok"
        assert seen[0][0] == {"API_KEY": "stdio-secret-1"}
        assert seen[0][1] == {"cache_write": "none", "record_era": False}
        assert (await w.cache.get("s", "std"))["tools"] == [{"name": "t"}]

        missing = await w.api.post(
            "/api/mcp-sources/std/test/agent", json={"agent": None, "overrides": None}
        )
        assert missing.json() == {"status": "needs_values", "missing": ["API_KEY"]}


async def test_live_tokens_run_phase_a_against_the_effective_source(world_, monkeypatch):
    async with world_ as w:
        src = await w.repo.get(SID)
        await w.repo.update(
            src.model_copy(
                update={
                    "secrets": {
                        "dcr_credentials": {"client_id": "c"},
                        "access_token": "tok-aaaa-bbbb",
                    },
                    "config": {"url": "http://localhost/mcp"},
                }
            )
        )
        await w.save_agent(
            "a", None, extra={"mcp_overrides": {"srv": {"headers": {"X-Extra": "extra-val-1"}}}}
        )
        seen = []

        async def fake(source, source_id, repo, **kw):
            seen.append((dict(source.secrets), kw))
            return {"status": "ok", "tools": [{"name": "t"}], "capabilities": {}}

        from the_one.interfaces.web import api

        monkeypatch.setattr(api, "_connect_with_tokens", fake)
        resp = await _post(w, "a")
        assert resp.json()["status"] == "ok"
        secrets, kw = seen[0]
        assert secrets["access_token"] == "tok-aaaa-bbbb" and secrets["X-Extra"] == "extra-val-1"
        assert kw == {"record_era": False, "cache_write": "none"}
        assert (await w.cache.get("a", SID))["tools"] == [{"name": "t"}]

        # sign-in required: no consent URL, no token clearing, no eviction
        async def needs_auth(*a, **k):
            raise MCPAuthRequired(SID)

        evicted = []

        async def spy_evict(*a, **k):
            evicted.append(a)

        monkeypatch.setattr(api, "_connect_with_tokens", needs_auth)
        with patch("the_one.mcp._pool._evict_all_for_source", spy_evict):
            resp = await _post(w, "a")
        assert resp.json() == {"status": "auth_required"}
        assert evicted == []
        stored = await w.repo.get(SID)
        assert stored.secrets.get("access_token") == "tok-aaaa-bbbb"  # tokens untouched

        async def conn_error(*a, **k):
            raise MCPConnectionError("initialize timed out")

        monkeypatch.setattr(api, "_connect_with_tokens", conn_error)
        resp = await _post(w, "a")
        assert resp.json()["status"] == "error"
        assert (await w.repo.get(SID)).secrets.get("access_token") == "tok-aaaa-bbbb"


# --- AC12: no value in any response or log -------------------------------------------------


async def test_no_value_appears_in_a_response_or_a_log_record(tmp_path, monkeypatch, caplog):
    async with world(tmp_path, monkeypatch, keys={SECRET_KEY: ["echo"]}) as w:
        caplog.set_level(logging.DEBUG)
        await w.save_agent("a", SECRET_KEY)
        ok = await _post(w, "a")
        assert ok.json()["status"] == "ok"
        # unsaved wrong value (rejection) and a refused value (422)
        rejected = await _post(w, "a", {"headers": {"X-Api-Key": "leaky-wrong-key1"}})
        assert rejected.json()["status"] == "error"
        refused = await _post(w, "a", {"headers": {"X-Api-Key": "bad\nvalue-leak-9"}})
        assert refused.status_code == 422
        needs = await _post(w, None)
        assert needs.json()["status"] == "needs_values"
        for resp in (ok, rejected, refused, needs):
            for secret in (SECRET_KEY, "leaky-wrong-key1", "value-leak-9"):
                assert secret not in resp.text
        for secret in (SECRET_KEY, "leaky-wrong-key1", "value-leak-9"):
            assert secret not in caplog.text


# --- AC14: two agents, one source, end to end -----------------------------------------------


async def test_two_agents_on_one_source_each_get_their_own_tools_end_to_end(world_, monkeypatch):
    async with world_ as w:
        await w.save_agent("a", KEY1)
        await w.save_agent("b", KEY2)
        await w.save_agent("plain")
        ra, rb = await _post(w, "a"), await _post(w, "b")
        assert {t["name"] for t in ra.json()["tools"]} == {"echo"}
        assert {t["name"] for t in rb.json()["tools"]} == {"echo", "add"}
        assert (await _post(w, "plain")).json()["status"] == "needs_values"

        # the route filled each agent's row; a build reads it with no connection
        async def boom(*a, **k):
            raise AssertionError("acquire must not be called")

        monkeypatch.setattr(provider_mod, "acquire", boom)
        assert set(await w.build_tools("a")) == {"mcp__srv__echo"}
        assert set(await w.build_tools("b")) == {"mcp__srv__echo", "mcp__srv__add"}
        assert w.tools_list_tails() == [KEY1[-4:], KEY2[-4:]]  # one listing each, from the route
