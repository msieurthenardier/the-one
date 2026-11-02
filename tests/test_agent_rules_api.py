"""REST tests for per-agent rules (M27 F1, DD4/DD8).

Same throwaway-app shape as ``tests/test_self_configuration_api.py``: only the
API router, with ``get_connection`` / ``get_encryptor`` patched to an isolated
template database.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.encryption import Encryptor


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = shared_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


async def _agent(client: AsyncClient, name: str = "ruled") -> str:
    resp = await client.post("/api/agents", json={"name": name, "description": "d"})
    assert resp.status_code == 201, resp.text
    return name


async def _rule(client, name, text, **extra) -> dict:
    resp = await client.post(f"/api/agents/{name}/rules", json={"text": text, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_get_empty_returns_rules_and_limits(client) -> None:
    name = await _agent(client)
    resp = await client.get(f"/api/agents/{name}/rules")
    assert resp.status_code == 200
    assert resp.json() == {"rules": [], "limits": {"rule_chars": 500, "total_chars": 4000}}


async def test_unknown_agent_is_404_on_every_route(client) -> None:
    for method, path, body in [
        ("GET", "/api/agents/nope/rules", None),
        ("POST", "/api/agents/nope/rules", {"text": "x"}),
        ("PUT", "/api/agents/nope/rules/order", {"ids": []}),
        ("PUT", "/api/agents/nope/rules/abc", {"text": "x"}),
        ("DELETE", "/api/agents/nope/rules/abc", None),
    ]:
        resp = await client.request(method, path, json=body)
        assert resp.status_code == 404, (method, path, resp.text)


async def test_create_returns_201_and_appends(client) -> None:
    name = await _agent(client)
    first = await _rule(client, name, "  one  ")
    second = await _rule(client, name, "two", enabled=False)
    assert first["text"] == "one" and first["enabled"] is True and first["position"] == 0
    assert second["enabled"] is False and second["position"] == 1
    assert set(first) == {
        "id",
        "agent_name",
        "text",
        "enabled",
        "position",
        "created_at",
        "updated_at",
    }
    listed = (await client.get(f"/api/agents/{name}/rules")).json()["rules"]
    assert [r["text"] for r in listed] == ["one", "two"]


async def test_limits_are_422_with_plain_detail(client) -> None:
    name = await _agent(client)
    for text in ("", "   "):
        resp = await client.post(f"/api/agents/{name}/rules", json={"text": text})
        assert resp.status_code == 422 and "empty" in resp.json()["detail"]
    resp = await client.post(f"/api/agents/{name}/rules", json={"text": "x" * 501})
    assert resp.status_code == 422
    assert "500" in resp.json()["detail"] and "501" in resp.json()["detail"]

    for _ in range(8):
        await _rule(client, name, "x" * 500)
    resp = await client.post(f"/api/agents/{name}/rules", json={"text": "y"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "Rules are limited to 4,000 characters in total; this would make 4,001."
    )


async def test_total_counts_disabled_rules_and_toggle_never_fails(client) -> None:
    name = await _agent(client)
    ids = [(await _rule(client, name, "x" * 500, enabled=False))["id"] for _ in range(8)]
    resp = await client.post(f"/api/agents/{name}/rules", json={"text": "y", "enabled": False})
    assert resp.status_code == 422
    resp = await client.put(f"/api/agents/{name}/rules/{ids[0]}", json={"enabled": True})
    assert resp.status_code == 200 and resp.json()["enabled"] is True
    # An edit past the total is 422 too.
    resp = await client.put(f"/api/agents/{name}/rules/{ids[0]}", json={"text": "x" * 501})
    assert resp.status_code == 422


async def test_update_edits_text_and_enabled(client) -> None:
    name = await _agent(client)
    rule = await _rule(client, name, "old")
    resp = await client.put(f"/api/agents/{name}/rules/{rule['id']}", json={"text": "new"})
    assert resp.status_code == 200
    assert (resp.json()["text"], resp.json()["enabled"]) == ("new", True)
    resp = await client.put(f"/api/agents/{name}/rules/{rule['id']}", json={"enabled": False})
    assert (resp.json()["text"], resp.json()["enabled"]) == ("new", False)


async def test_delete_densifies_positions(client) -> None:
    name = await _agent(client)
    a, b, c = [await _rule(client, name, t) for t in "abc"]
    resp = await client.delete(f"/api/agents/{name}/rules/{b['id']}")
    assert resp.status_code == 200
    listed = (await client.get(f"/api/agents/{name}/rules")).json()["rules"]
    assert [(r["text"], r["position"]) for r in listed] == [("a", 0), ("c", 1)]
    assert (await client.delete(f"/api/agents/{name}/rules/{b['id']}")).status_code == 404
    assert a["id"] and c["id"]


async def test_reorder_takes_an_exact_permutation(client) -> None:
    name = await _agent(client)
    ids = [(await _rule(client, name, t))["id"] for t in "abc"]
    for bad in (ids[:2], ids + [ids[0]], ids[:2] + ["nope"]):
        resp = await client.put(f"/api/agents/{name}/rules/order", json={"ids": bad})
        assert resp.status_code == 422, bad
    resp = await client.put(f"/api/agents/{name}/rules/order", json={"ids": ids[::-1]})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["text"] for r in body["rules"]] == ["c", "b", "a"]
    assert [r["position"] for r in body["rules"]] == [0, 1, 2]
    assert body["limits"] == {"rule_chars": 500, "total_chars": 4000}


async def test_another_agents_rule_is_404(client) -> None:
    one, two = await _agent(client, "one"), await _agent(client, "two")
    rule = await _rule(client, one, "mine")
    resp = await client.put(f"/api/agents/{two}/rules/{rule['id']}", json={"text": "x"})
    assert resp.status_code == 404
    assert (await client.delete(f"/api/agents/{two}/rules/{rule['id']}")).status_code == 404
    resp = await client.put(f"/api/agents/{two}/rules/order", json={"ids": [rule["id"]]})
    assert resp.status_code == 422
    assert (await client.get(f"/api/agents/{one}/rules")).json()["rules"][0]["text"] == "mine"


async def test_general_form_put_leaves_rules_untouched(client) -> None:
    name = await _agent(client)
    await _rule(client, name, "stays")
    resp = await client.put(f"/api/agents/{name}", json={"name": name, "description": "changed"})
    assert resp.status_code == 200, resp.text
    listed = (await client.get(f"/api/agents/{name}/rules")).json()["rules"]
    assert [r["text"] for r in listed] == ["stays"]


async def test_rename_carries_rules_and_revisions(client) -> None:
    from the_one.interfaces.web import api

    name = await _agent(client, "before")
    await _rule(client, name, "carried")
    repo = await api._agent_revisions_repo()
    await repo.append(
        agent_name=name,
        field="description",
        proposed_value="p",
        base_value="b",
        source="self",
        status="applied",
        created_at="t",
        resolved_at="t",
    )
    resp = await client.post(f"/api/agents/{name}/rename", json={"new_name": "after"})
    assert resp.status_code == 200, resp.text
    assert (await client.get("/api/agents/before/rules")).status_code == 404
    listed = (await client.get("/api/agents/after/rules")).json()["rules"]
    assert [r["text"] for r in listed] == ["carried"]
    assert [r.agent_name for r in await repo.list_for_agent("after")] == ["after"]


async def test_delete_agent_removes_rules_and_revisions(client) -> None:
    from the_one.interfaces.web import api

    name = await _agent(client, "doomed")
    await _rule(client, name, "gone")
    repo = await api._agent_revisions_repo()
    await repo.append(
        agent_name=name,
        field="description",
        proposed_value="p",
        base_value="b",
        source="self",
        status="applied",
        created_at="t",
        resolved_at="t",
    )
    assert (await client.delete(f"/api/agents/{name}")).status_code == 200
    conn = repo.conn
    for table in ("agent_rules", "agent_revisions"):
        async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:
            assert (await cur.fetchone())[0] == 0


async def test_type_validation_errors_never_echo_submitted_text(client) -> None:
    name = await _agent(client)
    secret = ["sentinel-rule-text-9137"]
    resp = await client.post(f"/api/agents/{name}/rules", json={"text": secret})
    assert resp.status_code == 422
    assert "sentinel-rule-text-9137" not in resp.text
    rule = await _rule(client, name, "ok")
    resp = await client.put(f"/api/agents/{name}/rules/{rule['id']}", json={"text": secret})
    assert resp.status_code == 422
    assert "sentinel-rule-text-9137" not in resp.text
    resp = await client.put(
        f"/api/agents/{name}/rules/order", json={"ids": "sentinel-rule-text-9137"}
    )
    assert resp.status_code == 422
    assert "sentinel-rule-text-9137" not in resp.text
