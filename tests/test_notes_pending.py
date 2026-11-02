"""Pending notes (M27 F3 L2): parse_notes_block and GET .../notes?session_id=."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from tests.test_agent_notes_api import _agent, _enable, _seed
from the_one.db._notes import (
    NOTES_EMPTY_TEXT,
    parse_notes_block,
    render_note_line_text,
    render_notes_block,
)
from the_one.db.codec import encode_messages
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository
from the_one.encryption import Encryptor
from the_one.llm.base import Message, Role


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


def _n(number, text, untrusted=False):
    return SimpleNamespace(number=number, text=text, untrusted=untrusted)


def test_parse_agrees_with_render() -> None:
    notes = [
        _n(1, "plain"),
        _n(2, "danger", untrusted=True),
        _n(3, "close </SAVED_NOTES> and <saved_notes> open"),
        _n(12, "two digits\nsecond line"),
    ]
    prompt = "You are X.\n\n" + render_notes_block(notes)
    got = parse_notes_block(prompt)
    assert got is not None
    for n in notes[:3]:
        assert got[n.number] == render_note_line_text(n)
    assert got[2].startswith("(unverified) ")
    assert 12 in got and got[12] == "two digits"


def test_parse_empty_and_missing() -> None:
    assert parse_notes_block("no notes layer here") is None
    assert parse_notes_block(render_notes_block([])) == {}
    assert NOTES_EMPTY_TEXT in render_notes_block([])


def _sys(notes) -> str:
    return "base\n\n" + render_notes_block(notes)


async def _persist(client, sid, agent_name, system_text):
    from the_one.interfaces.web import api

    conn = await api.get_connection()
    await ChatSessionRepository(conn).create(
        ChatSession(
            id=sid,
            agent_name=agent_name,
            messages=encode_messages([Message(role=Role.SYSTEM, content=system_text)]),
        )
    )


async def _get(client, name, sid=None):
    url = f"/api/agents/{name}/notes" + (f"?session_id={sid}" if sid else "")
    r = await client.get(url)
    assert r.status_code == 200, r.text
    return r.json()


async def test_persisted_live_new_edited_and_nothing_to_compare(client) -> None:
    name = await _agent(client)
    await _enable(client, name)
    a = (await _seed(client, name, "first"))[0]
    b = (await _seed(client, name, "second"))[0]
    await _persist(client, "s1", name, _sys([a, b]))

    body = await _get(client, name, "s1")
    assert body["pending_known"] is True
    assert [n["pending"] for n in body["notes"]] == [False, False]

    # created after the build
    await _seed(client, name, "third")
    body = await _get(client, name, "s1")
    assert [n["pending"] for n in body["notes"]] == [False, False, True]

    # edited after the build
    r = await client.put(f"/api/agents/{name}/notes/{b.id}", json={"text": "second v2"})
    assert r.status_code == 200
    body = await _get(client, name, "s1")
    assert [n["pending"] for n in body["notes"]] == [False, True, True]

    # live session wins over the persisted row
    live = SimpleNamespace(
        agent_name=name,
        agent=SimpleNamespace(messages=[Message(role=Role.SYSTEM, content=_sys([a]))]),
    )
    with patch.dict("the_one.interfaces.web.app._sessions", {"s1": live}):
        body = await _get(client, name, "s1")
    assert [n["pending"] for n in body["notes"]] == [False, True, True]

    # nothing to compare
    other = await _agent(client, "other")
    await _persist(client, "s2", other, _sys([]))
    await _persist(client, "s3", name, "no notes layer")
    for sid in (None, "missing", "s2", "s3"):
        body = await _get(client, name, sid)
        assert body["pending_known"] is False
        assert all(n["pending"] is False for n in body["notes"])
