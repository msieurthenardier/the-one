"""Save-time validation of agent tool overrides (sortie 07 leg 2, DD5, squawk 0257).

``POST``/``PUT /api/agents`` refuse a new or changed override that widens the
app-wide value or is invalid with a 422 on the field; an unchanged stored (stale)
field never blocks a save. Mirrors the credentialed in-process app-client pattern
of ``tests/test_api_tool_configs.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.interfaces.web import api as api_module


@pytest.fixture(autouse=True)
def _no_nss_user_lookup(monkeypatch):
    """Answer every ``~user`` lookup as "no such user" without asking NSS.

    ``Path.expanduser`` on ``~name`` calls ``pwd.getpwnam``, which goes through
    NSS (``systemd`` on this host) and can block for minutes under load (squawk
    0434). Every ``~name`` this file uses is deliberately unknown.
    """
    import pwd

    def _unknown(name):
        raise KeyError(f"getpwnam(): name not found: {name!r}")

    monkeypatch.setattr(pwd, "getpwnam", _unknown)


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


async def _set_tool(client: AsyncClient, name: str, config: dict) -> None:
    resp = await client.put(f"/api/tools/configs/{name}", json={"config": config})
    assert resp.status_code == 200, resp.text


async def _seed_agent(name: str, overrides: dict | None) -> None:
    """Store an agent directly, bypassing the save check (a stale/legacy row)."""
    from the_one.agent.config import AgentConfig

    store = await api_module._agent_store()
    await store.save(AgentConfig(name=name, tool_overrides=overrides))


def _msgs(resp) -> dict[tuple, str]:
    assert resp.status_code == 422, resp.text
    return {tuple(d["loc"]): d["msg"] for d in resp.json()["detail"]}


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "work"
    (root / "proj").mkdir(parents=True)
    (tmp_path / "other").mkdir()
    return root


# ── AC1: the 422 shape and nothing saved ─────────────────────────────────


class TestShape:
    async def test_create_widening_is_422_and_saves_nothing(self, client, work, tmp_path):
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        outside = str(tmp_path / "other")
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"read_file": {"path_allowlist": [outside]}}},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert len(detail) == 1
        assert detail[0]["type"] == "tool_override"
        assert detail[0]["loc"] == ["tool_overrides", "read_file", "path_allowlist"]
        assert isinstance(detail[0]["msg"], str)
        assert (await client.get("/api/agents/a")).status_code == 404

    async def test_update_widening_is_422_and_read_back_unchanged(self, client, work, tmp_path):
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        good = {"read_file": {"path_allowlist": [str(work / "proj")]}}
        assert (
            await client.post("/api/agents", json={"name": "a", "tool_overrides": good})
        ).status_code == 201
        bad = {"read_file": {"path_allowlist": [str(tmp_path / "other")]}}
        resp = await client.put("/api/agents/a", json={"tool_overrides": bad})
        assert resp.status_code == 422
        assert (await client.get("/api/agents/a")).json()["tool_overrides"] == good

    async def test_every_failing_field_is_reported(self, client):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "a",
                "tool_overrides": {
                    "shell": {"timeout_seconds_max": 500, "sandbox_network_allowed": True}
                },
            },
        )
        msgs = _msgs(resp)
        assert ("tool_overrides", "shell", "timeout_seconds_max") in msgs
        assert ("tool_overrides", "shell", "sandbox_network_allowed") in msgs

    async def test_unknown_tool_is_422_on_the_tool(self, client):
        resp = await client.post(
            "/api/agents", json={"name": "a", "tool_overrides": {"no_such_tool": {"x": 1}}}
        )
        assert _msgs(resp) == {
            ("tool_overrides", "no_such_tool"): "no_such_tool isn't a built-in tool."
        }

    async def test_non_dict_entry_keeps_the_agentconfig_422(self, client):
        resp = await client.post(
            "/api/agents", json={"name": "a", "tool_overrides": {"shell": "nope"}}
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail[0]["type"] != "tool_override"
        assert detail[0]["loc"][:2] == ["tool_overrides", "shell"]

    async def test_bad_override_beats_name_conflict(self, client):
        await client.post("/api/agents", json={"name": "a"})
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"shell": {"timeout_seconds_max": 500}}},
        )
        assert resp.status_code == 422


# ── AC2 + AC4: every failure family, with its exact sentence ────────────


class TestFamilies:
    async def test_path_widening(self, client, work, tmp_path):
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        outside = str(tmp_path / "other")
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"read_file": {"path_allowlist": [outside]}}},
        )
        assert _msgs(resp) == {
            ("tool_overrides", "read_file", "path_allowlist"): (
                f"`{outside}` is outside read_file's app-wide Allowed paths. "
                "Add it in Settings › Built-in tools › read_file first."
            )
        }

    async def test_number_widening(self, client):
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"shell": {"timeout_seconds_max": 500}}},
        )
        assert _msgs(resp) == {
            ("tool_overrides", "shell", "timeout_seconds_max"): (
                "Maximum timeout can be at most 120 for shell, the app-wide value."
            )
        }

    async def test_bool_widening(self, client):
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"shell": {"sandbox_network_allowed": True}}},
        )
        assert _msgs(resp) == {
            ("tool_overrides", "shell", "sandbox_network_allowed"): (
                "Allow network in the sandbox is off for shell app-wide, so it can't be "
                "turned on for one agent. Turn it on in Settings › Built-in tools "
                "› shell first."
            )
        }

    async def test_host_list_widening(self, client):
        await _set_tool(client, "http_request", {"host_allowlist": ["a.example.com"]})
        resp = await client.post(
            "/api/agents",
            json={
                "name": "a",
                "tool_overrides": {"http_request": {"host_allowlist": ["b.example.com"]}},
            },
        )
        assert _msgs(resp) == {
            ("tool_overrides", "http_request", "host_allowlist"): (
                "`b.example.com` isn't in http_request's app-wide Allowed hosts. "
                "Add it in Settings › Built-in tools › http_request first."
            )
        }

    async def test_bounds_negative_timeout(self, client):
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"shell": {"timeout_seconds_max": -5}}},
        )
        msgs = _msgs(resp)
        assert msgs == {
            ("tool_overrides", "shell", "timeout_seconds_max"): (
                "Maximum timeout for shell isn't valid: Input should be greater than or equal to 1."
            )
        }

    async def test_type_mismatch(self, client):
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"read_file": {"path_allowlist": "/tmp"}}},
        )
        assert _msgs(resp) == {
            ("tool_overrides", "read_file", "path_allowlist"): (
                "Allowed paths for read_file has the wrong kind of value."
            )
        }

    async def test_unmarked_key(self, client):
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"http_request": {"redirect_cap": 3}}},
        )
        assert _msgs(resp) == {
            ("tool_overrides", "http_request", "redirect_cap"): (
                "Redirect limit can't be changed for one agent; it is set in "
                "Settings › Built-in tools › http_request."
            )
        }

    @pytest.mark.parametrize("bad", ["~nosuchuser_zz9/x", "/tmp/a\x00b"])
    async def test_path_that_cannot_be_read(self, client, bad):
        resp = await client.post(
            "/api/agents",
            json={"name": "a", "tool_overrides": {"read_file": {"path_allowlist": [bad]}}},
        )
        assert _msgs(resp) == {
            ("tool_overrides", "read_file", "path_allowlist"): (
                "A path in Allowed paths for read_file can't be read. Check each path."
            )
        }

    async def test_cross_field_attributed_to_default_when_both_changed(self, client):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "a",
                "tool_overrides": {
                    "shell": {"timeout_seconds_default": 25, "timeout_seconds_max": 20}
                },
            },
        )
        assert _msgs(resp) == {
            ("tool_overrides", "shell", "timeout_seconds_default"): (
                "Default timeout can't be higher than Maximum timeout for shell."
            )
        }

    async def test_cross_field_attributed_to_the_one_that_changed(self, client):
        await _seed_agent("a", {"shell": {"timeout_seconds_default": 25}})
        resp = await client.put(
            "/api/agents/a",
            json={
                "tool_overrides": {
                    "shell": {"timeout_seconds_default": 25, "timeout_seconds_max": 20}
                }
            },
        )
        assert list(_msgs(resp)) == [("tool_overrides", "shell", "timeout_seconds_max")]
        await _seed_agent("b", {"shell": {"timeout_seconds_max": 20}})
        resp = await client.put(
            "/api/agents/b",
            json={
                "tool_overrides": {
                    "shell": {"timeout_seconds_default": 25, "timeout_seconds_max": 20}
                }
            },
        )
        assert list(_msgs(resp)) == [("tool_overrides", "shell", "timeout_seconds_default")]

    async def test_valid_override_saves_and_unknown_field_keys_are_ignored(self, client):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "a",
                "tool_overrides": {"shell": {"timeout_seconds_max": 60, "no_such_field": 1}},
            },
        )
        assert resp.status_code == 201, resp.text


# ── AC3: changed fields only ─────────────────────────────────────────────


class TestChangedOnly:
    async def test_stale_path_in_same_entry_still_saves(self, client, work, tmp_path):
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        outside = str(tmp_path / "other")
        await _seed_agent("a", {"read_file": {"path_allowlist": [outside]}})
        resp = await client.put(
            "/api/agents/a",
            json={
                "tool_overrides": {
                    "read_file": {"path_allowlist": [outside], "read_size_cap_bytes": 51200}
                }
            },
        )
        assert resp.status_code == 200, resp.text

    async def test_stale_negative_timeout_in_same_entry_still_saves(self, client):
        await _seed_agent("a", {"shell": {"timeout_seconds_max": -5}})
        resp = await client.put(
            "/api/agents/a",
            json={
                "tool_overrides": {
                    "shell": {"timeout_seconds_max": -5, "sandbox_network_allowed": False}
                }
            },
        )
        assert resp.status_code == 200, resp.text

    async def test_stale_unreadable_path_in_same_entry_still_saves(self, client, work):
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        await _seed_agent("a", {"read_file": {"path_allowlist": ["~nosuchuser_zz9/x"]}})
        resp = await client.put(
            "/api/agents/a",
            json={
                "tool_overrides": {
                    "read_file": {
                        "path_allowlist": ["~nosuchuser_zz9/x"],
                        "allow_binary_files": False,
                    }
                }
            },
        )
        assert resp.status_code == 200, resp.text

    async def test_a_list_edited_while_stale_is_checked_as_a_whole(self, client, work, tmp_path):
        await _set_tool(client, "read_file", {"path_allowlist": [str(work)]})
        stale = str(tmp_path / "other")
        await _seed_agent("a", {"read_file": {"path_allowlist": [stale]}})
        resp = await client.put(
            "/api/agents/a",
            json={"tool_overrides": {"read_file": {"path_allowlist": [stale, str(work / "proj")]}}},
        )
        assert list(_msgs(resp)) == [("tool_overrides", "read_file", "path_allowlist")]

    async def test_omitted_and_null_overrides_check_nothing(self, client):
        await _seed_agent("a", {"shell": {"timeout_seconds_max": -5}})
        resp = await client.put("/api/agents/a", json={"description": "x"})
        assert resp.status_code == 200, resp.text
        assert (await client.get("/api/agents/a")).json()["tool_overrides"] == {
            "shell": {"timeout_seconds_max": -5}
        }
        resp = await client.put("/api/agents/a", json={"tool_overrides": None})
        assert resp.status_code == 200, resp.text

    async def test_removing_a_field_is_not_checked(self, client):
        await _seed_agent(
            "a", {"shell": {"timeout_seconds_max": 500, "timeout_seconds_default": 30}}
        )
        resp = await client.put(
            "/api/agents/a", json={"tool_overrides": {"shell": {"timeout_seconds_default": 30}}}
        )
        assert resp.status_code == 200, resp.text

    async def test_unknown_tool_unchanged_is_carried(self, client):
        await _seed_agent("a", {"removed_tool": {"x": 1}})
        resp = await client.put(
            "/api/agents/a", json={"tool_overrides": {"removed_tool": {"x": 1}}, "description": "d"}
        )
        assert resp.status_code == 200, resp.text

    async def test_json_canonical_comparison_five_vs_five_point_zero(self, client):
        await _seed_agent("a", {"shell": {"timeout_seconds_max": 500}})
        same = await client.put(
            "/api/agents/a", json={"tool_overrides": {"shell": {"timeout_seconds_max": 500}}}
        )
        assert same.status_code == 200, same.text
        # 500.0 is a different JSON value from 500: it counts as changed and is checked.
        changed = await client.put(
            "/api/agents/a", json={"tool_overrides": {"shell": {"timeout_seconds_max": 500.0}}}
        )
        assert list(_msgs(changed)) == [("tool_overrides", "shell", "timeout_seconds_max")]

    async def test_json_canonical_comparison_true_vs_one(self, client):
        await _seed_agent("a", {"shell": {"sandbox_network_allowed": True}})
        same = await client.put(
            "/api/agents/a", json={"tool_overrides": {"shell": {"sandbox_network_allowed": True}}}
        )
        assert same.status_code == 200, same.text
        changed = await client.put(
            "/api/agents/a", json={"tool_overrides": {"shell": {"sandbox_network_allowed": 1}}}
        )
        assert list(_msgs(changed)) == [("tool_overrides", "shell", "sandbox_network_allowed")]

    async def test_disabled_tool_entry_is_still_checked(self, client):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "a",
                "disabled_tools": ["shell"],
                "tool_overrides": {"shell": {"timeout_seconds_max": 500}},
            },
        )
        assert resp.status_code == 422
