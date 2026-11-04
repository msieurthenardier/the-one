"""Sortie 09 leg 5: per-agent ``plain_names`` (the sensitive flag) and the targeted
credentials route ``PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials``.

Covers AC1-AC6: the schema field, its validation, the merge and prune, the masking in
agent responses, the route's refusals, scope and eviction, and that no value leaks.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import _agent_response, _looks_masked
from the_one.mcp._overrides import (
    MCP_OVERRIDE_CREDENTIAL_KEYS,
    StdioMCPOverride,
    StreamableHttpMCPOverride,
    has_credential_override,
)
from the_one.mcp._tool_provider import _apply_override
from the_one.mcp.override_validation import validate_mcp_overrides

SECRET = "distinctive-secret-value-12345"
PLAIN = "plain-visible-value-777"


def _http(name="gh", sid="gh-id") -> MCPSource:
    return MCPSource(
        id=sid,
        name=name,
        type="streamable-http",
        config={"url": "http://localhost/mcp", "headers": {}},
        secrets={},
    )


def _stdio(name="local", sid="local-id") -> MCPSource:
    return MCPSource(
        id=sid,
        name=name,
        type="stdio",
        config={"command": "echo", "args": [], "env": {}},
        secrets={},
    )


# --- AC1: schema ----------------------------------------------------------------


def test_plain_names_is_a_plain_field_not_a_credential_key():
    assert MCP_OVERRIDE_CREDENTIAL_KEYS == {"env", "headers", "bearer_token"}
    for cls in (StdioMCPOverride, StreamableHttpMCPOverride):
        assert "plain_names" in cls.model_fields
        assert cls.model_fields["plain_names"].metadata == []


def test_a_payload_with_only_plain_names_returns_the_source_unchanged():
    src = _http()
    assert _apply_override(src, {"plain_names": ["X-Key"]}) is src
    assert _apply_override(_stdio(), {"plain_names": ["K"]}).secrets == {}


def test_plain_names_alone_is_not_a_credential_override():
    assert not has_credential_override({"plain_names": ["X-Key"]}, _http())
    assert not has_credential_override({"plain_names": ["K"]}, _stdio())


# --- AC2: validation ------------------------------------------------------------


def _validate(overrides, *sources):
    return validate_mcp_overrides(overrides, {s.name: s for s in sources}, _looks_masked)


@pytest.mark.parametrize("bad", ["X-Key", {"a": 1}, [1, 2], ["ok", 3], 5])
def test_plain_names_must_be_a_list_of_strings(bad):
    details = _validate({"gh": {"plain_names": bad}}, _http())
    assert [tuple(d["loc"]) for d in details] == [("mcp_overrides", "gh", "plain_names")]
    assert details[0]["type"] == "mcp_override"


@pytest.mark.parametrize("name", ["Authorization", "authorization", "AUTHORIZATION"])
def test_authorization_cannot_be_marked_plain(name):
    details = _validate({"gh": {"plain_names": ["X-Key", name]}}, _http())
    assert [tuple(d["loc"]) for d in details] == [("mcp_overrides", "gh", "plain_names", name)]
    assert details[0]["msg"] == "An Authorization value is always sensitive."


def test_valid_and_null_plain_names_pass():
    assert _validate({"gh": {"plain_names": ["X-Key"]}}, _http()) == []
    assert _validate({"gh": {"plain_names": None}}, _http()) == []
    assert _validate({"local": {"plain_names": ["Authorization"]}}, _stdio()) == []


# --- API fixtures -----------------------------------------------------------------


@pytest.fixture
async def api(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "t.key")
    repo = MCPSourceRepository(conn, encryptor)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            yield c, repo, conn, encryptor
    await conn.close()


async def _stored(api, name):
    _, _, conn, encryptor = api
    return await SQLiteAgentStore(conn, encryptor).load(name)


@pytest.fixture
def evictions():
    log = []

    async def ev(key):
        log.append(key)

    with patch("the_one.mcp._pool._evict", ev):
        yield log


async def _agent(api, name="a", overrides=None, **extra):
    c = api[0]
    resp = await c.post("/api/agents", json={"name": name, "mcp_overrides": overrides, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


ENTRY = {
    "headers": {"X-Region": PLAIN, "X-Key": SECRET},
    "plain_names": ["X-Region"],
    "disabled_tools": ["t1"],
}


# --- AC3: merge and prune ---------------------------------------------------------


async def test_create_stores_plain_names_pruned_to_present_values(api):
    await api[1].create(_http())
    body = {"gh": {"headers": {"X-Region": PLAIN}, "plain_names": ["x-region", "X-Gone"]}}
    await _agent(api, overrides=body)
    stored = (await _stored(api, "a")).mcp_overrides["gh"]
    # names present in the merged headers (case-insensitive), spelled as the header is
    assert stored["plain_names"] == ["X-Region"]


async def test_a_main_save_with_only_tool_filters_keeps_plain_names(api):
    await api[1].create(_http())
    await _agent(api, overrides={"gh": ENTRY})
    c = api[0]
    resp = await c.put(
        "/api/agents/a",
        json={"name": "a", "mcp_overrides": {"gh": {"disabled_tools": ["t2"]}}},
    )
    assert resp.status_code == 200, resp.text
    stored = (await _stored(api, "a")).mcp_overrides["gh"]
    assert stored["plain_names"] == ["X-Region"]
    assert stored["headers"] == {"X-Region": PLAIN, "X-Key": SECRET}
    assert stored["disabled_tools"] == ["t2"]


async def test_a_removed_value_drops_out_of_plain_names(api):
    await api[1].create(_http())
    await _agent(api, overrides={"gh": ENTRY})
    c = api[0]
    # A headers dict replaces the stored one inner-key-wise: a name left out is removed.
    resp = await c.put(
        "/api/agents/a/mcp-overrides/gh-id/credentials",
        json={"headers": {"X-Key": "__MASKED__"}},
    )
    assert resp.status_code == 200, resp.text
    stored = (await _stored(api, "a")).mcp_overrides["gh"]
    assert stored["headers"] == {"X-Key": SECRET}
    assert "plain_names" not in stored


async def test_a_header_cleared_by_a_main_save_is_pruned(api):
    await api[1].create(_http())
    await _agent(api, overrides={"gh": ENTRY})
    c = api[0]
    resp = await c.put(
        "/api/agents/a",
        json={
            "name": "a",
            "mcp_overrides": {"gh": {"headers": None, "disabled_tools": ["t1"]}},
        },
    )
    assert resp.status_code == 200
    stored = (await _stored(api, "a")).mcp_overrides["gh"]
    assert "headers" not in stored and "plain_names" not in stored
    assert stored["disabled_tools"] == ["t1"]


async def test_null_plain_names_clears_and_a_list_replaces(api):
    await api[1].create(_http())
    await _agent(api, overrides={"gh": ENTRY})
    c = api[0]
    resp = await c.put("/api/agents/a/mcp-overrides/gh-id/credentials", json={"plain_names": None})
    assert resp.status_code == 200
    assert "plain_names" not in (await _stored(api, "a")).mcp_overrides["gh"]
    resp = await c.put(
        "/api/agents/a/mcp-overrides/gh-id/credentials", json={"plain_names": ["X-Key"]}
    )
    assert resp.status_code == 200
    assert (await _stored(api, "a")).mcp_overrides["gh"]["plain_names"] == ["X-Key"]


async def test_a_leftover_plain_names_alone_keeps_no_entry_alive(api):
    await api[1].create(_http())
    await _agent(api, overrides={"gh": {"headers": {"X-Key": SECRET}, "plain_names": ["X-Key"]}})
    c = api[0]
    resp = await c.put("/api/agents/a/mcp-overrides/gh-id/credentials", json={"headers": None})
    assert resp.status_code == 200
    assert (await _stored(api, "a")).mcp_overrides is None


async def test_a_malformed_plain_names_on_the_agent_put_is_a_422(api):
    await api[1].create(_http())
    c = api[0]
    resp = await c.post(
        "/api/agents", json={"name": "bad", "mcp_overrides": {"gh": {"plain_names": "X"}}}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["mcp_overrides", "gh", "plain_names"]


# --- AC4: masking -----------------------------------------------------------------


async def test_plain_values_are_clear_and_sensitive_values_masked(api):
    await api[1].create(_http())
    await api[1].create(_stdio())
    await _agent(
        api,
        overrides={
            "gh": ENTRY,
            "local": {"env": {"REGION": PLAIN, "TOKEN": SECRET}, "plain_names": ["REGION"]},
        },
    )
    c = api[0]
    for body in ((await c.get("/api/agents/a")).json(), (await c.get("/api/agents")).json()[0]):
        gh = body["mcp_overrides"]["gh"]
        assert gh["headers"]["X-Region"] == PLAIN
        assert gh["headers"]["X-Key"] != SECRET
        assert gh["plain_names"] == ["X-Region"]
        local = body["mcp_overrides"]["local"]
        assert local["env"]["REGION"] == PLAIN
        assert local["env"]["TOKEN"] != SECRET


async def test_env_names_are_matched_exactly(api):
    await api[1].create(_stdio())
    await _agent(api, overrides={"local": {"env": {"Region": PLAIN}, "plain_names": ["Region"]}})
    c = api[0]
    resp = await c.put(
        "/api/agents/a/mcp-overrides/local-id/credentials",
        json={"env": {"Region": PLAIN}, "plain_names": ["REGION"]},
    )
    assert resp.status_code == 200
    # "REGION" does not match "Region" for env: pruned away and the value is masked again
    body = resp.json()["mcp_overrides"]["local"]
    assert "plain_names" not in body
    assert body["env"]["Region"] != PLAIN


def test_bearer_token_and_authorization_stay_masked_even_if_listed_by_hand():
    cfg_data = {
        "name": "a",
        "provider_config_id": "p",
        "mcp_overrides": {
            "gh": {
                "headers": {"Authorization": SECRET, "X-Key": PLAIN},
                "bearer_token": SECRET,
                "plain_names": ["Authorization", "bearer_token", "X-Key"],
            }
        },
    }
    from the_one.agent.config import AgentConfig

    out = _agent_response(AgentConfig.model_validate(cfg_data))["mcp_overrides"]["gh"]
    assert out["bearer_token"] != SECRET
    assert out["headers"]["Authorization"] != SECRET
    assert out["headers"]["X-Key"] == PLAIN


async def test_a_mask_shaped_plain_value_is_dropped_by_the_merge(api):
    # Documented limitation, shared with the Library: a value shaped like a mask is the
    # client keeping a stored value, so with nothing stored it is dropped.
    await api[1].create(_http())
    await _agent(api, overrides={"gh": {"headers": {"X-Key": SECRET}}})
    c = api[0]
    resp = await c.put(
        "/api/agents/a/mcp-overrides/gh-id/credentials",
        json={"headers": {"X-New": "***"}, "plain_names": ["X-New"]},
    )
    assert resp.status_code == 200
    stored = (await _stored(api, "a")).mcp_overrides["gh"]
    assert "X-New" not in stored["headers"] and "plain_names" not in stored


# --- AC5: the targeted route ------------------------------------------------------


async def test_the_route_changes_only_that_sources_credentials(api):
    await api[1].create(_http())
    await api[1].create(_http("other", "other-id"))
    await _agent(
        api,
        overrides={"gh": ENTRY, "other": {"headers": {"X-O": "other-secret-1"}}},
        description="keep me",
    )
    c = api[0]
    resp = await c.put(
        "/api/agents/a/mcp-overrides/gh-id/credentials",
        json={"headers": {"X-Region": "eu-west", "X-Key": "__MASKED__"}},
    )
    assert resp.status_code == 200, resp.text
    stored = await _stored(api, "a")
    gh = stored.mcp_overrides["gh"]
    assert gh["headers"] == {"X-Region": "eu-west", "X-Key": SECRET}
    assert gh["plain_names"] == ["X-Region"]  # omitted keeps
    assert gh["disabled_tools"] == ["t1"]  # tool filter untouched
    assert stored.mcp_overrides["other"]["headers"] == {"X-O": "other-secret-1"}
    assert stored.description == "keep me"
    body = resp.json()
    assert "mcp_tool_cache" in body and "notices" in body
    assert body["mcp_overrides"]["gh"]["headers"]["X-Region"] == "eu-west"


async def test_the_route_can_set_credentials_for_an_unattached_source(api):
    await api[1].create(_http())
    await _agent(api)
    resp = await api[0].put(
        "/api/agents/a/mcp-overrides/gh-id/credentials", json={"headers": {"X-Key": SECRET}}
    )
    assert resp.status_code == 200
    assert (await _stored(api, "a")).mcp_overrides["gh"]["headers"] == {"X-Key": SECRET}


async def test_the_route_refusals(api):
    await api[1].create(_http())
    await _agent(api)
    c = api[0]
    url = "/api/agents/{}/mcp-overrides/{}/credentials"
    assert (await c.put(url.format("nobody", "gh-id"), json={})).status_code == 404
    assert (await c.put(url.format("a", "nope"), json={})).status_code == 404
    # malformed bodies
    assert (await c.put(url.format("a", "gh-id"), content="[1]")).status_code == 422
    assert (await c.put(url.format("a", "gh-id"), json={"extra": 1})).status_code == 422
    resp = await c.put(url.format("a", "gh-id"), json={"headers": "x"})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["mcp_overrides", "gh", "headers"]
    # DD2 and AC2 refusals use the mcp_override shape
    resp = await c.put(url.format("a", "gh-id"), json={"headers": {"Host": "x1"}})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"][:2] == ["mcp_overrides", "gh"]
    resp = await c.put(
        url.format("a", "gh-id"),
        json={"headers": {"Authorization": "Bearer x1"}, "plain_names": ["Authorization"]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "An Authorization value is always sensitive."
    assert (await _stored(api, "a")).mcp_overrides is None


async def test_the_route_refuses_a_self_configuration_row(api):
    surface = MCPSource(
        id="sc-id",
        name="self-configuration",
        type="streamable-http",
        config={"url": "http://localhost/mcp", "headers": {}, "x_the_one_surface_owner": "a"},
        secrets={},
    )
    await api[1].create(surface)
    await _agent(api)
    with patch(
        "the_one.interfaces.web.api.self_configuration_manage.is_surface_row",
        return_value=True,
    ):
        resp = await api[0].put(
            "/api/agents/a/mcp-overrides/sc-id/credentials", json={"headers": {"X": "v1"}}
        )
    assert resp.status_code == 422


async def test_the_route_evicts_on_a_changed_credential_but_not_on_sensitivity(api, evictions):
    await api[1].create(_http())
    await _agent(api, overrides={"gh": ENTRY})
    evictions.clear()
    c = api[0]
    # sensitivity only: same values (masked / as stored), different plain_names
    resp = await c.put(
        "/api/agents/a/mcp-overrides/gh-id/credentials",
        json={"headers": {"X-Region": PLAIN, "X-Key": "__MASKED__"}, "plain_names": ["X-Key"]},
    )
    assert resp.status_code == 200
    assert evictions == []
    # a changed value evicts that (agent, source) key
    resp = await c.put(
        "/api/agents/a/mcp-overrides/gh-id/credentials",
        json={"headers": {"X-Region": "other-value"}},
    )
    assert resp.status_code == 200
    assert evictions == [("a", "gh-id")]


# --- AC6: no leaks ----------------------------------------------------------------


async def test_no_value_leaks_through_the_new_paths(api, caplog):
    await api[1].create(_http())
    await _agent(api)
    c = api[0]
    url = "/api/agents/a/mcp-overrides/gh-id/credentials"
    caplog.set_level(logging.DEBUG)
    refused = await c.put(url, json={"headers": {"Host": SECRET}, "plain_names": ["Host"]})
    assert refused.status_code == 422
    ok = await c.put(url, json={"headers": {"X-Key": SECRET, "X-R": PLAIN}, "plain_names": ["X-R"]})
    assert ok.status_code == 200
    sens_only = await c.put(
        url, json={"headers": {"X-Key": "__MASKED__", "X-R": PLAIN}, "plain_names": None}
    )
    assert sens_only.status_code == 200
    for resp in (refused, ok, sens_only):
        assert SECRET not in resp.text
    assert PLAIN not in refused.text
    assert PLAIN in ok.text  # by design: a plain value is returned on agent responses
    assert PLAIN not in sens_only.text  # no longer plain
    assert SECRET not in caplog.text and PLAIN not in caplog.text
