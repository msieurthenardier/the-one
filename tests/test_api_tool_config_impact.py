"""``POST /api/tools/configs/{name}/impact`` (sortie 07 leg 5, DD8).

The Settings editor asks which agents a proposed tool config would newly narrow before it
saves. The route runs the PUT's own computation (``_compute_tool_config_update``), so the
preview equals what a following PUT stores.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.repositories import ToolConfigRepository
from the_one.tools import override_validation as ov


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


async def _agent(client: AsyncClient, name: str, hosts: list[str], **extra) -> None:
    resp = await client.post(
        "/api/agents",
        json={"name": name, "tool_overrides": {"http_request": {"host_allowlist": hosts}}, **extra},
    )
    assert resp.status_code in (200, 201), resp.text


async def _impact(client: AsyncClient, name: str, body: dict):
    return await client.post(f"/api/tools/configs/{name}/impact", json=body)


async def _two_agents(client: AsyncClient) -> None:
    await _agent(client, "wide", ["a.example.com", "b.example.com"])
    await _agent(client, "narrow", ["a.example.com"])


class TestImpact:
    async def test_tightening_lists_exactly_the_narrowed_agent_and_field(self, client):
        await _two_agents(client)
        resp = await _impact(
            client, "http_request", {"config": {"host_allowlist": ["a.example.com"]}}
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "agents": [
                {
                    "agent": "wide",
                    "fields": [
                        {
                            "field": "host_allowlist",
                            "field_title": "Allowed hosts",
                            "dropped": ["b.example.com"],
                        }
                    ],
                }
            ]
        }

    async def test_any_host_agent_is_listed_with_no_dropped_values(self, client):
        await _agent(client, "anyhost", [])
        resp = await _impact(
            client, "http_request", {"config": {"host_allowlist": ["a.example.com"]}}
        )
        (entry,) = resp.json()["agents"]
        assert entry["agent"] == "anyhost"
        assert entry["fields"][0]["dropped"] == []

    async def test_a_widening_and_an_unrelated_change_list_nothing(self, client):
        await _two_agents(client)
        # Widening: nothing is narrowed (and the stored row is the default).
        wide = await _impact(
            client,
            "http_request",
            {"config": {"host_allowlist": ["a.example.com", "b.example.com", "c.example.com"]}},
        )
        assert wide.json() == {"agents": []}
        # An unrelated field changes no notice.
        other = await _impact(client, "http_request", {"config": {"timeout_seconds_max": 60}})
        assert other.json() == {"agents": []}

    async def test_a_no_op_after_the_tightening_lists_nothing(self, client):
        await _two_agents(client)
        body = {"config": {"host_allowlist": ["a.example.com"]}}
        assert (await client.put("/api/tools/configs/http_request", json=body)).status_code == 200
        # "wide" now carries the notice; proposing the same value is not a new narrowing.
        assert (await _impact(client, "http_request", body)).json() == {"agents": []}
        # A further tightening that drops nothing more also lists nothing; one that drops
        # a value the agent still holds would, but "wide" was already clipped to a.example.com.
        assert (
            await _impact(client, "http_request", {"config": {"host_allowlist": ["z.example.com"]}})
        ).json()["agents"][0]["agent"] == "narrow"

    async def test_tool_off_for_the_agent_or_app_wide_lists_nothing(self, client):
        await _agent(
            client, "off", ["a.example.com", "b.example.com"], disabled_tools=["http_request"]
        )
        body = {"config": {"host_allowlist": ["a.example.com"]}}
        assert (await _impact(client, "http_request", body)).json() == {"agents": []}
        await _agent(client, "on", ["a.example.com", "b.example.com"])
        assert [
            a["agent"] for a in (await _impact(client, "http_request", body)).json()["agents"]
        ] == ["on"]
        # Disabling the tool app-wide in the same proposal narrows nothing.
        off = await _impact(
            client,
            "http_request",
            {"enabled": False, "config": {"host_allowlist": ["a.example.com"]}},
        )
        assert off.json() == {"agents": []}

    async def test_the_preview_equals_what_the_put_stores(self, client):
        await _two_agents(client)
        body = {"config": {"host_allowlist": ["a.example.com"], "timeout_seconds_max": 45}}
        preview = (await _impact(client, "http_request", body)).json()
        # The route stored nothing.
        before = (await client.get("/api/tools/configs/http_request")).json()
        assert before["config"].get("host_allowlist", []) == []
        assert (await client.put("/api/tools/configs/http_request", json=body)).status_code == 200
        stored = (await client.get("/api/tools/configs/http_request")).json()["config"]
        assert stored["host_allowlist"] == ["a.example.com"] and stored["timeout_seconds_max"] == 45
        listed = {a["name"]: a for a in (await client.get("/api/agents")).json()}
        with_notice = sorted(
            n for n, a in listed.items() if any(x["tool"] == "http_request" for x in a["notices"])
        )
        assert with_notice == [a["agent"] for a in preview["agents"]] == ["wide"]
        (notice,) = listed["wide"]["notices"]
        (field,) = preview["agents"][0]["fields"]
        assert (notice["field"], notice["dropped"]) == (field["field"], field["dropped"])

    async def test_hidden_values_and_omitted_config_follow_the_puts_computation(self, client):
        await _two_agents(client)
        # `config` omitted: the stored config stands, so nothing changes.
        assert (await _impact(client, "http_request", {})).json() == {"agents": []}
        assert (await _impact(client, "http_request", {"enabled": True})).json() == {"agents": []}

    async def test_invalid_body_gets_the_puts_422(self, client):
        await _two_agents(client)
        body = {"config": {"timeout_seconds_default": "soon"}}
        put = await client.put("/api/tools/configs/http_request", json=body)
        imp = await _impact(client, "http_request", body)
        assert put.status_code == imp.status_code == 422
        assert imp.json() == put.json()

    async def test_unknown_tool_is_404(self, client):
        resp = await _impact(client, "no_such_tool", {"config": {}})
        assert resp.status_code == 404

    async def test_a_tool_with_an_empty_config_lists_nothing(self, client):
        await _two_agents(client)
        resp = await _impact(client, "current_time", {"config": {}})
        assert resp.status_code == 200 and resp.json() == {"agents": []}

    async def test_one_rows_list_per_request(self, client):
        await _two_agents(client)
        calls = []
        real = ToolConfigRepository.list

        async def counting(self, *a, **k):
            calls.append(1)
            return await real(self, *a, **k)

        with patch.object(ToolConfigRepository, "list", counting):
            resp = await _impact(
                client, "http_request", {"config": {"host_allowlist": ["a.example.com"]}}
            )
        assert resp.status_code == 200 and len(calls) == 1
