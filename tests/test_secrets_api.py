"""``/api/secrets`` and the agent grants (sortie 10, leg 1).

Security focus: no route ever returns a stored value or any fragment of it, in a success,
a 404, a 409, any 422, a malformed-body 422, or a log line.
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
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router

SHORT = "q7Zx"
MEDIUM = "medium-secret-9"
LONG = "L0ng\"secret'with\\both-quotes-and-a-backslash-xyz"
PLAINTEXTS = (SHORT, MEDIUM, LONG)
MASK = "__MASKED__"


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "t.db")
    yield c
    await c.close()


@pytest.fixture
async def client(conn):
    enc = Encryptor(Fernet.generate_key())
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            c.encryptor = enc
            yield c


def _body(**over):
    body = {
        "name": "Home address",
        "description": "where I live",
        "allowed_tools": ["write_file"],
        "values": [
            {"key": "street", "value": MEDIUM},
            {"key": "pin", "value": SHORT},
            {"key": "note", "value": LONG},
        ],
    }
    body.update(over)
    return body


async def _create(client, **over):
    resp = await client.post("/api/secrets", json=_body(**over))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assert_clean(text: str) -> None:
    for plain in PLAINTEXTS:
        assert plain not in text, "a stored value appeared in a response"
        assert plain[-4:] not in text.replace(MASK, ""), "a value tail appeared in a response"


class TestShapeAndCrud:
    async def test_routes_exist_for_the_loopback_scoping_pins(self) -> None:
        paths = {getattr(r, "path", "") for r in router.routes}
        assert {"/api/secrets", "/api/secrets/{secret_id}", "/api/tool-names"} <= paths

    async def test_create_get_list(self, client) -> None:
        created = await _create(client)
        assert set(created) == {
            "id",
            "name",
            "description",
            "allowed_tools",
            "values",
            "created_at",
            "updated_at",
        }
        assert [v["key"] for v in created["values"]] == ["street", "pin", "note"]
        assert all(v["value"] == MASK and v["id"] for v in created["values"])
        assert created["allowed_tools"] == ["write_file"]
        got = (await client.get(f"/api/secrets/{created['id']}")).json()
        assert got == created
        assert (await client.get("/api/secrets")).json() == [created]

    async def test_unknown_id_is_404_on_get_put_delete(self, client) -> None:
        assert (await client.get("/api/secrets/nope")).status_code == 404
        assert (await client.put("/api/secrets/nope", json={"description": "x"})).status_code == 404
        assert (await client.delete("/api/secrets/nope")).status_code == 404

    async def test_delete_is_204_then_gone(self, client) -> None:
        sid = (await _create(client))["id"]
        resp = await client.delete(f"/api/secrets/{sid}")
        assert resp.status_code == 204 and resp.content == b""
        assert (await client.get(f"/api/secrets/{sid}")).status_code == 404

    async def test_stored_at_rest_as_ciphertext(self, client, conn) -> None:
        await _create(client)
        async with conn.execute("SELECT value FROM secret_values") as cur:
            stored = [r[0] for r in await cur.fetchall()]
        assert stored and all(p not in v for v in stored for p in PLAINTEXTS)
        assert sorted(client.encryptor.decrypt(v) for v in stored) == sorted(PLAINTEXTS)


class TestPutSemantics:
    async def test_partial_put_keeps_omitted_fields(self, client) -> None:
        s = await _create(client)
        r = await client.put(f"/api/secrets/{s['id']}", json={"description": "new"})
        assert r.status_code == 200
        assert r.json()["description"] == "new"
        assert r.json()["name"] == s["name"]
        assert r.json()["allowed_tools"] == s["allowed_tools"]
        assert r.json()["values"] == s["values"]

    async def test_keep_replace_delete_reorder(self, client, conn) -> None:
        s = await _create(client)
        street, pin, note = s["values"]
        r = await client.put(
            f"/api/secrets/{s['id']}",
            json={
                "values": [
                    {"id": note["id"], "key": "note", "value": MASK},
                    {"id": street["id"], "key": "street", "value": "replaced-street"},
                ]
            },
        )
        assert r.status_code == 200, r.text
        assert [v["key"] for v in r.json()["values"]] == ["note", "street"]
        async with conn.execute("SELECT key, value FROM secret_values ORDER BY position") as cur:
            rows = {k: client.encryptor.decrypt(v) for k, v in await cur.fetchall()}
        assert rows == {"note": LONG, "street": "replaced-street"}

    async def test_key_rename_with_kept_value_and_two_key_swap(self, client, conn) -> None:
        s = await _create(
            client, values=[{"key": "a", "value": MEDIUM}, {"key": "b", "value": LONG}]
        )
        a, b = s["values"]
        r = await client.put(
            f"/api/secrets/{s['id']}",
            json={
                "values": [
                    {"id": a["id"], "key": "b", "value": MASK},
                    {"id": b["id"], "key": "a", "value": MASK},
                ]
            },
        )
        assert r.status_code == 200, r.text
        async with conn.execute("SELECT key, value FROM secret_values ORDER BY position") as cur:
            rows = [(k, client.encryptor.decrypt(v)) for k, v in await cur.fetchall()]
        assert rows == [("b", MEDIUM), ("a", LONG)]
        r = await client.put(
            f"/api/secrets/{s['id']}",
            json={"values": [{"id": a["id"], "key": "renamed", "value": MASK}]},
        )
        assert [v["key"] for v in r.json()["values"]] == ["renamed"]

    async def test_rename_to_own_name_in_another_case_is_allowed(self, client) -> None:
        s = await _create(client)
        r = await client.put(f"/api/secrets/{s['id']}", json={"name": "HOME ADDRESS"})
        assert r.status_code == 200 and r.json()["name"] == "HOME ADDRESS"


def _loc(resp):
    assert resp.status_code == 422, resp.text
    return [d["loc"] for d in resp.json()["detail"]]


class TestValidation:
    async def test_name_goes_through_the_name_rule(self, client) -> None:
        r = await client.post("/api/secrets", json=_body(name="a/b"))
        assert _loc(r) == [["name"]]

    async def test_duplicate_name_is_409_ignoring_case_and_never_a_500(self, client, conn) -> None:
        await _create(client)
        r = await client.post(
            "/api/secrets", json=_body(name="home ADDRESS", values=[{"key": "z", "value": "zzzz"}])
        )
        assert r.status_code == 409
        assert r.json()["detail"] == [
            {
                "type": "name_conflict",
                "loc": ["name"],
                "msg": "A secret with this name already exists.",
            }
        ]
        other = await _create(client, name="Other", values=[{"key": "o", "value": "oooo"}])
        r = await client.put(f"/api/secrets/{other['id']}", json={"name": "home address"})
        assert r.status_code == 409

    async def test_name_race_integrity_error_is_409(self, client) -> None:
        """The pre-check passes but the constraint fires (a race): still a 409."""
        await _create(client)
        with patch(
            "the_one.db.repositories.SecretRepository._name_taken",
            return_value=False,
        ):
            r = await client.post(
                "/api/secrets",
                json=_body(values=[{"key": "z", "value": "zzzz"}]),
            )
        assert r.status_code == 409

    async def test_key_race_integrity_error_is_422_not_500(self, client) -> None:
        await _create(client)
        with patch("the_one.db.repositories.SecretRepository._other_keys", return_value=set()):
            r = await client.post(
                "/api/secrets",
                json=_body(name="Two", values=[{"key": "street", "value": "zzzz"}]),
            )
        assert _loc(r) == [["values", 0, "key"]]

    async def test_description_not_a_string(self, client) -> None:
        assert _loc(await client.post("/api/secrets", json=_body(description=5))) == [
            ["description"]
        ]

    @pytest.mark.parametrize("values", [None, "x", [], {}])
    async def test_values_missing_or_malformed(self, client, values) -> None:
        body = _body()
        if values is None:
            del body["values"]
        else:
            body["values"] = values
        assert _loc(await client.post("/api/secrets", json=body)) == [["values"]]

    async def test_put_with_empty_values_is_422(self, client) -> None:
        s = await _create(client)
        assert _loc(await client.put(f"/api/secrets/{s['id']}", json={"values": []})) == [
            ["values"]
        ]

    @pytest.mark.parametrize("bad", ["", "has space", "a.b", "x" * 65, 7, None])
    async def test_key_rule(self, client, bad) -> None:
        r = await client.post("/api/secrets", json=_body(values=[{"key": bad, "value": "vvvv"}]))
        assert _loc(r) == [["values", 0, "key"]]

    async def test_key_repeat_ignoring_case_is_on_the_second(self, client) -> None:
        vals = [{"key": "Dup", "value": "aaaa"}, {"key": "dup", "value": "bbbb"}]
        assert _loc(await client.post("/api/secrets", json=_body(values=vals))) == [
            ["values", 1, "key"]
        ]

    async def test_key_owned_by_another_secret_ignoring_case(self, client) -> None:
        await _create(client)
        r = await client.post(
            "/api/secrets",
            json=_body(
                name="Two", values=[{"key": "ok", "value": "aaaa"}, {"key": "PIN", "value": "b"}]
            ),
        )
        assert _loc(r) == [["values", 1, "key"]]
        assert "another secret" in r.json()["detail"][0]["msg"].lower()

    @pytest.mark.parametrize("bad", [None, "", 5])
    async def test_value_must_be_a_non_empty_string(self, client, bad) -> None:
        r = await client.post("/api/secrets", json=_body(values=[{"key": "k", "value": bad}]))
        assert _loc(r) == [["values", 0, "value"]]

    async def test_masked_without_id_or_with_a_foreign_id(self, client) -> None:
        r = await client.post("/api/secrets", json=_body(values=[{"key": "k", "value": MASK}]))
        assert _loc(r) == [["values", 0, "value"]]
        s = await _create(client)
        other = await _create(client, name="Other", values=[{"key": "o", "value": "oooo"}])
        r = await client.put(
            f"/api/secrets/{s['id']}",
            json={"values": [{"key": "street", "value": MASK}]},
        )
        assert _loc(r) == [["values", 0, "value"]]
        r = await client.put(
            f"/api/secrets/{s['id']}",
            json={"values": [{"id": other["values"][0]["id"], "key": "street", "value": MASK}]},
        )
        assert _loc(r) == [["values", 0, "value"]]
        r = await client.put(
            f"/api/secrets/{s['id']}",
            json={"values": [{"id": "ghost", "key": "street", "value": MASK}]},
        )
        assert _loc(r) == [["values", 0, "value"]]
        # nothing was written
        assert (await client.get(f"/api/secrets/{s['id']}")).json() == s

    async def test_repeated_id_is_on_the_second_occurrence(self, client) -> None:
        s = await _create(client)
        pid = s["values"][0]["id"]
        vals = [
            {"id": pid, "key": "a", "value": MASK},
            {"id": pid, "key": "b", "value": MASK},
        ]
        r = await client.put(f"/api/secrets/{s['id']}", json={"values": vals})
        assert ["values", 1, "id"] in _loc(r)

    @pytest.mark.parametrize("tools", [None, [], "write_file"])
    async def test_allowed_tools_missing_or_empty(self, client, tools) -> None:
        body = _body()
        if tools is None:
            del body["allowed_tools"]
        else:
            body["allowed_tools"] = tools
        assert _loc(await client.post("/api/secrets", json=body)) == [["allowed_tools"]]

    @pytest.mark.parametrize("bad", [5, "", "   ", "a b", "x" * 129])
    async def test_allowed_tool_entry_rules(self, client, bad) -> None:
        r = await client.post("/api/secrets", json=_body(allowed_tools=["write_file", bad]))
        assert _loc(r) == [["allowed_tools", 1]]

    async def test_allowed_tools_are_trimmed_and_deduplicated(self, client) -> None:
        s = await _create(client, allowed_tools=[" write_file ", "write_file", "read_file"])
        assert s["allowed_tools"] == ["write_file", "read_file"]

    @pytest.mark.parametrize(
        "name",
        [
            "save_note",
            "schedule_routine",
            "send_to_platform_channel",
            "continue",
            "search_tools",
            "mcp__self-configuration__update_my_description",
        ],
    )
    async def test_refused_tools(self, client, name) -> None:
        r = await client.post("/api/secrets", json=_body(allowed_tools=["write_file", name]))
        assert _loc(r) == [["allowed_tools", 1]]
        assert r.json()["detail"][0]["msg"] == (
            f"{name} stores or publishes what it receives, so it can't receive secrets."
        )

    async def test_put_validates_a_present_allowed_tools(self, client) -> None:
        s = await _create(client)
        r = await client.put(f"/api/secrets/{s['id']}", json={"allowed_tools": ["save_note"]})
        assert _loc(r) == [["allowed_tools", 0]]
        assert (await client.get(f"/api/secrets/{s['id']}")).json()["allowed_tools"] == [
            "write_file"
        ]


class TestNoValueEverLeaves:
    """AC5: every route, every failure kind, a malformed body that contains a value."""

    async def test_no_response_body_carries_a_value_or_its_tail(self, client) -> None:
        bodies: list[str] = []

        def rec(resp):
            bodies.append(resp.text)
            return resp

        s = await _create(client)
        other = await _create(client, name="Other", values=[{"key": "o", "value": "oooo-other"}])
        sid, pid = s["id"], s["values"][0]["id"]
        rec(await client.get("/api/secrets"))
        rec(await client.get(f"/api/secrets/{sid}"))
        rec(await client.get("/api/secrets/nope"))  # 404
        rec(await client.put("/api/secrets/nope", json=_body()))  # 404 with values in body
        rec(await client.post("/api/secrets", json=_body()))  # 409 (name exists)
        # every 422 kind, each carrying real values in the request
        for body in (
            _body(name="a/b"),
            _body(description=5),
            _body(values=[]),
            _body(values=[{"key": "bad key", "value": LONG}]),
            _body(values=[{"key": "k", "value": LONG}, {"key": "K", "value": MEDIUM}]),
            _body(values=[{"key": "k", "value": ""}]),
            _body(values=[{"key": "k", "value": MASK}]),
            _body(values=[{"key": "k", "value": SHORT, "id": 5}]),
            _body(values=[{"key": "o", "value": LONG}], name="Third"),
            _body(allowed_tools=[]),
            _body(allowed_tools=["save_note"]),
            _body(allowed_tools=[LONG]),
            _body(values=[LONG]),
            _body(values=[{"key": 5, "value": LONG}]),
            _body(values="not-a-list" + LONG),
        ):
            rec(await client.post("/api/secrets", json=body))
        rec(
            await client.put(
                f"/api/secrets/{sid}",
                json={"values": [{"id": other["values"][0]["id"], "key": "street", "value": MASK}]},
            )
        )
        rec(
            await client.put(
                f"/api/secrets/{sid}",
                json={
                    "values": [
                        {"id": pid, "key": "street", "value": LONG},
                        {"id": pid, "key": "x", "value": MASK},
                    ]
                },
            )
        )
        # malformed JSON and non-object bodies containing a value
        for raw in (
            '{"values": [{"key": "k", "value": "' + MEDIUM + '"',
            '["' + LONG.replace("\\", "\\\\").replace('"', '\\"') + '"]',
            "[" + MEDIUM,
        ):
            rec(
                await client.post(
                    "/api/secrets", content=raw, headers={"content-type": "application/json"}
                )
            )
            rec(
                await client.put(
                    f"/api/secrets/{sid}", content=raw, headers={"content-type": "application/json"}
                )
            )
        # a good create, update and delete
        rec(await client.put(f"/api/secrets/{sid}", json={"description": "d"}))
        rec(await client.delete(f"/api/secrets/{other['id']}"))
        assert len(bodies) > 25
        for text in bodies:
            _assert_clean(text)

    async def test_agent_responses_carry_ids_not_values(self, client) -> None:
        s = await _create(client)
        r = await client.post("/api/agents", json={"name": "a", "secret_ids": [s["id"]]})
        assert r.status_code == 201
        for text in (
            r.text,
            (await client.get("/api/agents/a")).text,
            (await client.get("/api/agents")).text,
        ):
            _assert_clean(text)

    async def test_no_log_record_carries_a_value(self, client, caplog) -> None:
        with caplog.at_level(logging.DEBUG):
            s = await _create(client)
            await client.put(
                f"/api/secrets/{s['id']}",
                json={"values": [{"key": "new", "value": "brand-new-value-77"}]},
            )
            await client.put(
                f"/api/secrets/{s['id']}",
                json={"values": [{"key": "k", "value": LONG}, {"key": "k", "value": MEDIUM}]},
            )
            await client.post(
                "/api/secrets",
                content='{"values": ["' + MEDIUM,
                headers={"content-type": "application/json"},
            )
            await client.delete(f"/api/secrets/{s['id']}")
        assert caplog.records
        blob = "\n".join(
            r.getMessage() + " " + str(r.exc_text or "") + " " + repr(r.args)
            for r in caplog.records
        )
        for plain in (*PLAINTEXTS, "brand-new-value-77"):
            assert plain not in blob


class TestAgentGrants:
    async def test_create_default_empty_and_get_carries_secret_ids(self, client) -> None:
        r = await client.post("/api/agents", json={"name": "plain"})
        assert r.json()["secret_ids"] == []
        s = await _create(client)
        r = await client.post("/api/agents", json={"name": "granted", "secret_ids": [s["id"]]})
        assert r.status_code == 201 and r.json()["secret_ids"] == [s["id"]]
        assert (await client.get("/api/agents/granted")).json()["secret_ids"] == [s["id"]]

    async def test_put_omitted_keeps_and_empty_clears(self, client) -> None:
        s = await _create(client)
        await client.post("/api/agents", json={"name": "a", "secret_ids": [s["id"]]})
        r = await client.put("/api/agents/a", json={"description": "changed"})
        assert r.status_code == 200 and r.json()["secret_ids"] == [s["id"]]
        r = await client.put("/api/agents/a", json={"secret_ids": []})
        assert r.json()["secret_ids"] == []
        assert (await client.get("/api/agents/a")).json()["secret_ids"] == []

    async def test_unknown_id_added_on_post_or_put_is_422_on_its_index(self, client) -> None:
        s = await _create(client)
        r = await client.post("/api/agents", json={"name": "a", "secret_ids": [s["id"], "ghost"]})
        assert _loc(r) == [["secret_ids", 1]]
        assert (await client.get("/api/agents/a")).status_code == 404
        await client.post("/api/agents", json={"name": "a", "secret_ids": [s["id"]]})
        r = await client.put("/api/agents/a", json={"secret_ids": [s["id"], "ghost"]})
        assert _loc(r) == [["secret_ids", 1]]
        assert (await client.get("/api/agents/a")).json()["secret_ids"] == [s["id"]]

    async def test_only_new_ids_are_checked_on_put(self, client, conn) -> None:
        """A stored dangling id (a delete racing a grant) does not block an unrelated save."""
        s = await _create(client)
        await client.post("/api/agents", json={"name": "a", "secret_ids": [s["id"]]})
        await conn.execute("DELETE FROM secrets WHERE id = ?", (s["id"],))
        await conn.commit()
        r = await client.put("/api/agents/a", json={"description": "still editable"})
        assert r.status_code == 200 and r.json()["secret_ids"] == [s["id"]]

    async def test_non_list_and_non_string_entries_are_pydantic_422s(self, client) -> None:
        r = await client.post("/api/agents", json={"name": "a", "secret_ids": "x"})
        assert r.status_code == 422
        r = await client.post("/api/agents", json={"name": "a", "secret_ids": [5]})
        assert _loc(r) == [["secret_ids", 0]]

    async def test_delete_scrubs_grants(self, client) -> None:
        s = await _create(client)
        await client.post("/api/agents", json={"name": "a", "secret_ids": [s["id"]]})
        assert (await client.delete(f"/api/secrets/{s['id']}")).status_code == 204
        assert (await client.get("/api/agents/a")).json()["secret_ids"] == []


class TestMcpRenameCarry:
    async def test_mcp_put_rename_moves_allowed_tools(self, client) -> None:
        sid = (
            await client.post(
                "/api/mcp-sources",
                json={"type": "stdio", "config": {"command": "echo"}, "name": "Old name"},
            )
        ).json()["id"]
        s = await _create(client, allowed_tools=["mcp__Old_name__typeText", "write_file"])
        r = await client.put(f"/api/mcp-sources/{sid}", json={"name": "New"})
        assert r.status_code == 200, r.text
        assert (await client.get(f"/api/secrets/{s['id']}")).json()["allowed_tools"] == [
            "mcp__New__typeText",
            "write_file",
        ]

    async def test_secrets_carry_runs_even_when_the_agent_store_carry_fails(self, client) -> None:
        sid = (
            await client.post(
                "/api/mcp-sources",
                json={"type": "stdio", "config": {"command": "echo"}, "name": "Old"},
            )
        ).json()["id"]
        s = await _create(client, allowed_tools=["mcp__Old__t"])
        with patch(
            "the_one.interfaces.web.api._agent_store", side_effect=RuntimeError("store down")
        ):
            r = await client.put(f"/api/mcp-sources/{sid}", json={"name": "Newer"})
        assert r.status_code == 200
        assert (await client.get(f"/api/secrets/{s['id']}")).json()["allowed_tools"] == [
            "mcp__Newer__t"
        ]
