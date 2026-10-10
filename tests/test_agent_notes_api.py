"""REST tests for per-agent notes (M27 F2 L1, DD2/DD11).

Same throwaway-app shape as ``tests/test_self_configuration_api.py``: only the
API router, with ``get_connection`` / ``get_encryptor`` patched to an isolated
template database.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.repositories import AgentNoteRepository
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


_ORIGIN = {
    "origin_kind": "web",
    "origin_session_id": None,
    "origin_label": None,
    "origin_platform": None,
    "origin_peer_id": None,
    "origin_peer_name": None,
}


async def _agent(client, name="noted") -> str:
    resp = await client.post("/api/agents", json={"name": name, "description": "d"})
    assert resp.status_code == 201, resp.text
    return name


async def _enable(client, name, value=True):
    resp = await client.put(f"/api/agents/{name}/notes/settings", json={"enabled": value})
    assert resp.status_code == 200, resp.text


async def _seed(client, name, text, **kw):
    """Create a note through the repository on the patched connection."""
    from the_one.interfaces.web import api

    conn = await api.get_connection()
    return await AgentNoteRepository(conn).create(
        name,
        text,
        untrusted=kw.pop("untrusted", False),
        sources=kw.pop("sources", []),
        **{**_ORIGIN, **kw},
    )


async def test_get_defaults_off_with_limits_and_usage(client) -> None:
    name = await _agent(client)
    resp = await client.get(f"/api/agents/{name}/notes")
    assert resp.status_code == 200
    assert resp.json() == {
        "enabled": False,
        "notes": [],
        "limits": {"note_chars": 400, "total_chars": 4000, "writes_per_turn": 5},
        "usage": {"total_chars": 0},
    }


async def test_unknown_agent_and_unknown_note_are_404(client) -> None:
    for method, path, body in [
        ("GET", "/api/agents/nope/notes", None),
        ("PUT", "/api/agents/nope/notes/settings", {"enabled": True}),
        ("PUT", "/api/agents/nope/notes/abc", {"text": "x"}),
        ("DELETE", "/api/agents/nope/notes/abc", None),
        ("DELETE", "/api/agents/nope/notes", None),
    ]:
        resp = await client.request(method, path, json=body)
        assert resp.status_code == 404, (method, path, resp.text)
    name = await _agent(client)
    assert (
        await client.put(f"/api/agents/{name}/notes/zzz", json={"text": "x"})
    ).status_code == 404
    assert (await client.delete(f"/api/agents/{name}/notes/zzz")).status_code == 404


async def test_settings_route_wins_over_note_id_and_validates(client) -> None:
    name = await _agent(client)
    resp = await client.put(f"/api/agents/{name}/notes/settings", json={"enabled": True})
    assert resp.status_code == 200 and resp.json() == {"enabled": True}
    assert (await client.get(f"/api/agents/{name}/notes")).json()["enabled"] is True
    for bad in ({"enabled": "no"}, {"enabled": 1}, {}, []):
        r = await client.put(f"/api/agents/{name}/notes/settings", json=bad)
        assert r.status_code == 422, bad


async def test_list_edit_delete_clear_flow(client) -> None:
    name = await _agent(client)
    await _enable(client, name)
    a = await _seed(client, name, "first", untrusted=True, sources=["fetch_url"])
    b = (await _seed(client, name, "second"))[0]
    a = a[0]
    body = (await client.get(f"/api/agents/{name}/notes")).json()
    assert [n["number"] for n in body["notes"]] == [1, 2]
    assert body["usage"] == {"total_chars": len("first") + len("second")}
    n0 = body["notes"][0]
    assert n0["untrusted"] is True and n0["untrusted_sources"] == ["fetch_url"]
    assert set(n0) >= {
        "id", "number", "text", "untrusted", "untrusted_sources", "origin_kind",
        "origin_session_id", "origin_label", "origin_exists", "origin_platform",
        "origin_peer_id", "origin_peer_name", "created_at", "updated_at", "updated_by",
    }  # fmt: skip

    r = await client.put(f"/api/agents/{name}/notes/{a.id}", json={"text": "edited\nline"})
    assert r.status_code == 200
    assert r.json()["text"] == "edited line" and r.json()["updated_by"] == "operator"
    assert r.json()["untrusted"] is True

    assert (await client.delete(f"/api/agents/{name}/notes/{b.id}")).json() == {"status": "ok"}
    assert (await client.delete(f"/api/agents/{name}/notes")).json() == {"deleted": 1}
    assert (await client.get(f"/api/agents/{name}/notes")).json()["notes"] == []


async def test_edit_errors_are_422_without_echoing_text(client) -> None:
    name = await _agent(client)
    await _enable(client, name)
    a = (await _seed(client, name, "alpha-text"))[0]
    b = (await _seed(client, name, "beta-text"))[0]
    secret = "SECRET" * 100
    r = await client.put(f"/api/agents/{name}/notes/{a.id}", json={"text": secret})
    assert r.status_code == 422 and "SECRET" not in r.text
    r = await client.put(f"/api/agents/{name}/notes/{a.id}", json={"text": "  "})
    assert r.status_code == 422
    r = await client.put(f"/api/agents/{name}/notes/{b.id}", json={"text": "ALPHA-text!"})
    assert r.status_code == 422 and "alpha" not in r.json()["detail"].lower()
    r = await client.put(f"/api/agents/{name}/notes/{a.id}", json={"text": 5})
    assert r.status_code == 422


async def test_operator_can_edit_and_delete_while_off(client) -> None:
    name = await _agent(client)
    await _enable(client, name)
    a = (await _seed(client, name, "x"))[0]
    await _enable(client, name, False)
    assert (
        await client.put(f"/api/agents/{name}/notes/{a.id}", json={"text": "y"})
    ).status_code == 200
    assert (await client.delete(f"/api/agents/{name}/notes/{a.id}")).status_code == 200


async def test_another_agents_note_is_404(client) -> None:
    one, two = await _agent(client, "one"), await _agent(client, "two")
    await _enable(client, one)
    n = (await _seed(client, one, "mine"))[0]
    assert (
        await client.put(f"/api/agents/{two}/notes/{n.id}", json={"text": "x"})
    ).status_code == 404
    assert (await client.delete(f"/api/agents/{two}/notes/{n.id}")).status_code == 404


async def test_update_agent_preserves_notes_enabled_on_omit(client) -> None:
    name = await _agent(client)
    assert (await client.get(f"/api/agents/{name}/notes")).json()["enabled"] is False
    await _enable(client, name)
    r = await client.put(f"/api/agents/{name}", json={"name": name, "description": "changed"})
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/agents/{name}/notes")).json()["enabled"] is True
    r = await client.put(
        f"/api/agents/{name}", json={"name": name, "description": "c", "notes_enabled": False}
    )
    assert r.status_code == 200
    assert (await client.get(f"/api/agents/{name}/notes")).json()["enabled"] is False


async def test_notes_survive_off_and_back_on(client) -> None:
    name = await _agent(client)
    await _enable(client, name)
    await _seed(client, name, "kept")
    await _enable(client, name, False)
    body = (await client.get(f"/api/agents/{name}/notes")).json()
    assert body["enabled"] is False and [n["text"] for n in body["notes"]] == ["kept"]
