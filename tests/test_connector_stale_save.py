"""A connector editor Save must not drop a peer paired after the editor loaded
(squawk 0288). The editor sends ``allowlist_peers_base`` (the peers it last
loaded or saved); ``update_connector`` three-way merges ``allowlist.peers``.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from the_one.config import settings
from the_one.connectors.inbound import _pair_peer
from the_one.interfaces.web.api import _connector_repo, _merge_paired_peers

pytestmark = pytest.mark.usefixtures("isolated_db")


@pytest.fixture
async def client():
    transport = ASGITransport(app=shared_app())
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers()
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _stub_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")


async def _create(client: AsyncClient, peers: list[str] | None, **extra) -> str:
    config: dict = {"enabled": False, "default_agent": "bot-1", **extra}
    if peers is not None:
        config["allowlist"] = {"peers": peers}
    r = await client.post(
        "/api/connectors",
        json={"name": "C", "type": "stub", "config": config, "secrets": {"token": "tok-1"}},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _stored_config(cid: str) -> dict:
    repo = await _connector_repo()
    return (await repo.get(cid)).config


async def _pair(cid: str, peer: str) -> None:
    repo = await _connector_repo()
    await _pair_peer(await repo.get(cid), peer, repo)


async def test_ac1_peer_paired_after_editor_load_survives_save(client: AsyncClient) -> None:
    cid = await _create(client, ["a"])
    editor_view = (await client.get(f"/api/connectors/{cid}")).json()
    await _pair(cid, "b")
    config = dict(editor_view["config"], default_agent="bot-2")
    r = await client.put(
        f"/api/connectors/{cid}",
        json={
            "name": "C",
            "type": "stub",
            "config": config,
            "secrets": {"token": "__MASKED__"},
            "allowlist_peers_base": ["a"],
        },
    )
    assert r.status_code == 200, r.text
    stored = await _stored_config(cid)
    assert stored["allowlist"]["peers"] == ["a", "b"]
    assert stored["default_agent"] == "bot-2"
    assert "allowlist_peers_base" not in stored
    assert "allowlist_peers_base" not in r.json()
    repo = await _connector_repo()
    assert (await repo.get(cid)).secrets["token"] == "tok-1"  # AC5


async def _put(client, cid, config, base=...):
    body = {"name": "C", "type": "stub", "config": config, "secrets": {"token": "__MASKED__"}}
    if base is not ...:
        body["allowlist_peers_base"] = base
    return await client.put(f"/api/connectors/{cid}", json=body)


async def test_ac2_deliberate_removal_kept_and_pairing_preserved(client: AsyncClient) -> None:
    cid = await _create(client, ["a", "b"])
    await _pair(cid, "c")
    r = await _put(client, cid, {"enabled": False, "allowlist": {"peers": ["a"]}}, ["a", "b"])
    assert r.status_code == 200
    assert (await _stored_config(cid))["allowlist"]["peers"] == ["a", "c"]


async def test_ac2_peer_removed_elsewhere_not_readded_but_named_peer_wins(
    client: AsyncClient,
) -> None:
    cid = await _create(client, ["a"])
    r = await _put(client, cid, {"enabled": False, "allowlist": {"peers": ["a", "b"]}}, ["a", "b"])
    assert r.status_code == 200
    assert (await _stored_config(cid))["allowlist"]["peers"] == ["a", "b"]


async def test_ac3_no_base_replaces_as_before(client: AsyncClient) -> None:
    cid = await _create(client, ["a", "b"])
    r = await _put(client, cid, {"enabled": False, "allowlist": {"peers": ["a"]}})
    assert r.status_code == 200
    assert (await _stored_config(cid))["allowlist"]["peers"] == ["a"]


@pytest.mark.parametrize("bad", ["x", 5, {"a": 1}, [1, 2], ["a", None]])
async def test_ac3_bad_base_is_422_and_writes_nothing(client: AsyncClient, bad) -> None:
    cid = await _create(client, ["a", "b"])
    before = await _stored_config(cid)
    r = await _put(client, cid, {"enabled": False, "allowlist": {"peers": ["a"]}}, bad)
    assert r.status_code == 422
    assert "allowlist_peers_base" in r.text
    assert await _stored_config(cid) == before


async def test_ac3_null_base_is_absent(client: AsyncClient) -> None:
    cid = await _create(client, ["a", "b"])
    r = await _put(client, cid, {"enabled": False, "allowlist": {"peers": ["a"]}}, None)
    assert r.status_code == 200
    assert (await _stored_config(cid))["allowlist"]["peers"] == ["a"]


@pytest.mark.parametrize(
    "config",
    [
        {"allowlist": "x"},
        {"allowlist": {"peers": "p"}},
        {"allowlist": {"peers": [1, 2]}},
    ],
)
async def test_ac3b_malformed_shapes_keep_422_row_unchanged(client: AsyncClient, config) -> None:
    cid = await _create(client, ["a"])
    before = await _stored_config(cid)
    await _pair(cid, "b")
    before = await _stored_config(cid)
    r = await _put(client, cid, {"enabled": False, **config}, ["a"])
    assert r.status_code == 422
    assert await _stored_config(cid) == before


async def test_ac4_sparse_incoming_config_keeps_paired_peer(client: AsyncClient) -> None:
    cid = await _create(client, [])
    await _pair(cid, "p")
    r = await _put(client, cid, {"enabled": False}, [])
    assert r.status_code == 200
    stored = await _stored_config(cid)
    assert stored["allowlist"] == {"peers": ["p"]}


def test_helper_pure_and_dedupes() -> None:
    stored = {"allowlist": {"peers": ["a", "b", "c"], "channels": ["x"]}}
    incoming = {"allowlist": {"peers": ["a", "a"]}, "default_agent": "d"}
    snap_in = {"allowlist": {"peers": ["a", "a"]}, "default_agent": "d"}
    out = _merge_paired_peers(stored, incoming, ["a"])
    assert out["allowlist"] == {"peers": ["a", "b", "c"]}
    assert incoming == snap_in
    assert stored["allowlist"]["peers"] == ["a", "b", "c"]
    # no allowlist stored: nothing added, no empty key written
    out2 = _merge_paired_peers({}, {"default_agent": "d"}, [])
    assert out2 == {"default_agent": "d"}


def test_helper_returns_same_object_for_malformed() -> None:
    stored = {"allowlist": {"peers": ["a"]}}
    for bad in (
        "x",
        {"allowlist": "x"},
        {"allowlist": {"peers": "p"}},
        {"allowlist": {"peers": [1]}},
    ):
        assert _merge_paired_peers(stored, bad, []) is bad
