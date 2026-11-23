"""GleepGlorp's whitelist views (M36 F1 L05, DD5 as amended): the leg's acceptance gate.

Secret parity across every encrypted store, the structural allowlist and classification,
the read-only proof, the undecryptable-row degrade and the notes/chat exclusion.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from cryptography.fernet import Fernet

from tests._gleepglorp_seed import ARG_TOKEN, PATH_TOKEN, SEEDS, seed
from the_one.gleepglorp import views
from the_one.gleepglorp.views import ALLOWED, KINDS, LIST_KINDS, UNREADABLE, PlainMessage


@pytest.fixture
async def world(tmp_path):
    ns = await seed(tmp_path)
    yield ns
    await ns.conn.close()


# --- the parity driver: how each kind enumerates its valid names -----------------------


async def _names_of_list_kind(ns, kind: str) -> list[str]:
    return [e["name"] for e in await views.read(ns.conn, ns.enc, kind) if e["name"] != "…"]


async def _agent_names(ns, kind: str) -> list[str]:
    return [e["name"] for e in await views.read(ns.conn, ns.enc, "agents")]


async def _no_names(ns, kind: str) -> list[str | None]:
    return [None]


# One entry per kind. A kind without an entry here fails ``test_every_kind_is_classified``.
PARITY_DRIVER = {
    "overview": _no_names,
    "agents": _names_of_list_kind,
    "mcp_servers": _names_of_list_kind,
    "providers": _names_of_list_kind,
    "knowledge_bases": _names_of_list_kind,
    "connectors": _names_of_list_kind,
    "routines": _agent_names,
    "secrets": _names_of_list_kind,
    "built_in_tools": _names_of_list_kind,
    "settings": _no_names,
    "fields": _names_of_list_kind,
}


async def _call(ns, kind: str, name: str | None) -> tuple[Any, str]:
    """One read as ``(data or None, serialized text)``; a plain reply is its own text."""
    try:
        data = await views.read(ns.conn, ns.enc, kind, name)
    except PlainMessage as msg:
        return None, str(msg)
    return data, json.dumps(data, separators=(",", ":"), ensure_ascii=False)


async def _everything(ns) -> list[tuple[str, str | None, Any, str]]:
    """Every kind, with no name, with every valid name, and the unknown-name path."""
    out = []
    for kind in KINDS:
        data, text = await _call(ns, kind, None)
        out.append((kind, None, data, text))
        for name in await PARITY_DRIVER[kind](ns, kind):
            if name is None:
                continue
            data, text = await _call(ns, kind, name)
            out.append((kind, name, data, text))
        for odd in ("does-not-exist", "../etc/passwd", "ünï'\"cødé", "x" * 500):
            data, text = await _call(ns, kind, odd)
            out.append((kind, odd, data, text))
    return out


# --- secret parity ----------------------------------------------------------------------


async def test_secret_parity_no_seeded_value_in_any_output(world) -> None:
    results = await _everything(world)
    assert len(results) > 40  # the driver really walked every kind and name
    blob = "\n".join(text for *_, text in results)
    leaks = []
    for label, value in SEEDS.items():
        if value in blob:
            leaks.append(f"{label}: whole value")
        if value[-4:] in blob:
            leaks.append(f"{label}: last four characters")
    # external_credential is vacuous by design: no kind reads agent_external_credentials, so
    # it can only pass; it is seeded so a future kind that does read the table fails here.
    assert not leaks, leaks


async def test_every_secret_slot_is_actually_seeded(world) -> None:
    """The parity test is only as strong as its seeds: each slot is stored in the database."""
    conn = world.conn
    async with conn.execute("SELECT api_key, secrets FROM llm_providers") as cur:
        assert any(r[0] for r in await cur.fetchall())
    # Decrypted corpora hold the values (so a leak would be real, not an empty fixture).
    from the_one.db.encryption_corpora import gather_corpora

    c = await gather_corpora(conn, world.enc, strict=False)
    plain = json.dumps(
        [getattr(c, f.name) for f in dataclasses.fields(c)],
        default=str,
    )
    must_be_stored = [
        label
        for label in SEEDS
        if label
        not in {
            # plain-column or non-encrypted seeds, covered by their own columns:
            "provider_config_decoy",
            "provider_baseurl_password",
            "provider_baseurl_query",
            "mcp_config_header_sensitive",
            "mcp_config_header_plain",
            "mcp_config_env_sensitive",
            "mcp_config_env_plain",
            "mcp_address_password",
            "mcp_address_query",
            "mcp_cache_server_info",
            "mcp_cache_instructions",
            "mcp_cache_meta",
            "mcp_cache_capabilities",
            "mcp_sandbox_writable_path",
            "connector_config_decoy_peer",
            "connector_config_decoy_listen",
            "agent_mcp_tool_cache_description",
            "tool_config_secret_decoy_in_config",
            "tool_config_url_password",
            "tool_config_url_query",
            "chat_message_text",
            "note_text",
        }
    ]
    missing = [label for label in must_be_stored if SEEDS[label] not in plain]
    assert not missing, missing
    # And the plain-column seeds are in their plain columns.
    async with conn.execute("SELECT config FROM mcp_sources") as cur:
        cfgs = "".join(r[0] for r in await cur.fetchall())
    for label in ("mcp_config_header_sensitive", "mcp_config_env_sensitive",
                  "mcp_cache_server_info", "mcp_cache_instructions", "mcp_cache_meta",
                  "mcp_cache_capabilities", "mcp_sandbox_writable_path",
                  "mcp_address_password"):  # fmt: skip
        assert SEEDS[label] in cfgs, label
    for sql, labels in (
        ("SELECT tools FROM agent_mcp_tool_cache", ("agent_mcp_tool_cache_description",)),
        ("SELECT config FROM tool_configs",
         ("tool_config_secret_decoy_in_config", "tool_config_url_password",
          "tool_config_url_query")),
        ("SELECT config FROM connectors",
         ("connector_config_decoy_peer", "connector_config_decoy_listen")),
        ("SELECT config FROM llm_providers", ("provider_config_decoy",)),
        ("SELECT base_url FROM llm_providers",
         ("provider_baseurl_password", "provider_baseurl_query")),
    ):  # fmt: skip
        async with conn.execute(sql) as cur:
            stored = "".join(str(r[0]) for r in await cur.fetchall())
        for label in labels:
            assert SEEDS[label] in stored, label
    async with conn.execute("SELECT messages FROM chat_sessions") as cur:
        assert SEEDS["chat_message_text"] in (await cur.fetchone())[0]
    async with conn.execute("SELECT text FROM agent_notes") as cur:
        assert SEEDS["note_text"] in (await cur.fetchone())[0]


async def test_every_encryption_corpus_field_has_a_seed_slot(world) -> None:
    """A field added to ``Corpora`` without a seeded row fails here (it gathers empty), so
    the parity test cannot silently miss a new encrypted corpus."""
    from the_one.db.encryption_corpora import Corpora, gather_corpora

    c = await gather_corpora(world.conn, world.enc, strict=False)
    empty = [f.name for f in dataclasses.fields(Corpora) if not getattr(c, f.name)]
    assert not empty, f"Corpora fields with no seed in tests/_gleepglorp_seed.py: {empty}"


async def test_oauth_managed_key_names_do_not_surface(world) -> None:
    data, text = await _call(world, "mcp_servers", "Docs server")
    for key in (
        "access_token",
        "refresh_token",
        "token_expires_at",
        "token_type",
        "dcr_credentials",
    ):
        assert key not in text, key
    assert data["signed_in"] is True


async def test_residuals_are_shown_as_written(world) -> None:
    """A token in a command argument or an address path is shown: a documented residual."""
    stdio, stdio_text = await _call(world, "mcp_servers", "Local tool")
    assert ARG_TOKEN in stdio["args"]
    http, _ = await _call(world, "mcp_servers", "Docs server")
    assert http["address"] == f"https://mcp.example.com:9443/mcp/{PATH_TOKEN}"
    # ...but the user info and the query string are gone.
    assert "user" not in http["address"].split("//")[1].split("/")[0]
    assert "token=" not in http["address"]


async def test_provider_address_drops_userinfo_query_and_path(world) -> None:
    prov, text = await _call(world, "providers", "OpenAI main")
    assert prov["address"] == "https://api.example.com:8443"
    assert PATH_TOKEN not in text


# --- what each view holds ---------------------------------------------------------------


async def test_agent_detail(world) -> None:
    d, _ = await _call(world, "agents", "wide")
    assert d["name"] == "wide"
    assert d["system_prompt"] == "You are the wide agent."
    assert d["model"] == "gpt-x" and d["provider"] == "OpenAI main"
    assert d["enabled_tools"] == "all" and d["disabled_tools"] == ["web_fetch"]
    assert d["tools_with_overrides"] == ["shell"]  # the name, never the override value
    assert d["rules"] == [{"number": 1, "text": "Always answer briefly.", "enabled": True}]
    assert sorted(d["mcp_servers"]) == ["Docs server", "self-configuration"]
    assert d["knowledge_bases"] == ["Docs KB"]
    assert d["routines_count"] == 1 and d["notes_count"] == 1
    assert d["rich_visuals"] is True and d["self_configuration"] is True
    plain, _ = await _call(world, "agents", "plain")
    assert plain["self_configuration"] is False and plain["enabled_tools"] == "all"


async def test_mcp_detail_and_status(world) -> None:
    d, _ = await _call(world, "mcp_servers", "Docs server")
    assert d["type"] == "streamable-http"
    assert d["header_names"] == ["Authorization", "X-Api-Key", "X-Plain", "bearer_token"]
    assert d["connection"] == {
        "status": "ok",
        "checked_at": "2027-01-15T08:01:40+00:00",
        "protocol_version": "2026-07-28",
        "auth_posture": "oauth",
        "protocol_fallback": None,
    }
    assert d["tool_count"] == 2
    assert [t["name"] for t in d["tools"]] == ["search", "fetch"]
    assert len(d["tools"][0]["description"]) <= 200  # server-written text is capped
    assert d["agents"] == ["wide"]
    stdio, _ = await _call(world, "mcp_servers", "Local tool")
    assert stdio["command"] == "npx" and stdio["working_directory"] == "/home/work/project"
    assert stdio["env_names"] == ["DB_PASSWORD", "PLAIN_ENV", "SENSITIVE_ENV"]
    assert "sandbox" not in json.dumps(stdio) and SEEDS[
        "mcp_sandbox_writable_path"
    ] not in json.dumps(stdio)
    assert stdio["connection"]["status"] == "not checked yet"


async def test_surface_row_is_one_built_in_entry_without_credential_or_address(world) -> None:
    listing, _ = await _call(world, "mcp_servers", None)
    rows = [e for e in listing if e["name"] == "self-configuration"]
    assert len(rows) == 1 and rows[0]["summary"].startswith("Self-configuration (built in")
    d, text = await _call(world, "mcp_servers", "self-configuration")
    assert d["agents"] == ["wide"]
    assert "127.0.0.1" not in text and "self-configuration-mount" not in text
    assert SEEDS["surface_row_bearer"] not in text


async def test_provider_detail(world) -> None:
    plan, _ = await _call(world, "providers", "Claude plan")
    assert plan["oauth_active"] is True and plan["used_by_gleepglorp"] is True
    token, _ = await _call(world, "providers", "Claude token")
    assert token["oauth_active"] is False and token["type"] == "anthropic-plan-token"
    main, _ = await _call(world, "providers", "OpenAI main")
    assert main["agents"] == ["wide"] and main["used_by_gleepglorp"] is False


async def test_knowledge_base_detail(world) -> None:
    d, _ = await _call(world, "knowledge_bases", "Docs KB")
    assert d["folders"] == ["/home/work/docs"]
    assert d["items"]["indexed"] == 1 and d["latest_indexed"] == "2026-11-01T10:00:00+00:00"
    assert d["indexer"] == "idle" and d["agents"] == ["wide"]


async def test_connector_detail_has_bindings_but_no_token_or_allowlist(world) -> None:
    d, text = await _call(world, "connectors", "Team Discord")
    assert d == {
        "name": "Team Discord",
        "type": "discord",
        "enabled": True,
        "default_agent": "wide",
        "channel_bindings": [{"channel": "chan-555", "agent": "plain"}],
    }
    assert SEEDS["connector_config_decoy_peer"] not in text


async def test_routines_detail(world) -> None:
    d, _ = await _call(world, "routines", "wide")
    assert d["agent"] == "wide" and len(d["routines"]) == 1
    r = d["routines"][0]
    assert r["name"] == "Morning digest" and r["prompt"] == "Summarise the news."
    assert r["enabled"] is True and "9:00" in r["schedule"] and r["next_run"]
    assert set(r) == {
        "name",
        "schedule",
        "next_run",
        "prompt",
        "enabled",
    }  # no last_run, no session
    none, text = await _call(world, "routines", None)
    assert none is None and "agent name" in text and "wide" in text and "plain" in text


async def test_secret_detail_shows_key_names_never_values(world) -> None:
    d, text = await _call(world, "secrets", "github")
    assert d == {
        "id": world.library_secret_id,
        "name": "github",
        "description": "GitHub access",
        "keys": ["gh_token"],
        "allowed_tools": ["shell"],
        "agents": ["wide"],
    }
    assert SEEDS["library_secret_value"] not in text


async def test_built_in_tool_settings_exclude_secret_fields(world) -> None:
    d, text = await _call(world, "built_in_tools", "web_search")
    assert d["settings"] == {
        "search_backend": "brave",
        "google_pse_cse_id": "cse-nonsecret-visible",
        "searxng_base_url": "https://searx.example.com:8080/search",
    }
    assert "brave_api_key" not in text
    listing, _ = await _call(world, "built_in_tools", None)
    assert any(e["name"] == "current_time" for e in listing)


async def test_settings_and_overview(world) -> None:
    s, _ = await _call(world, "settings", None)
    assert set(s) == {"time_zone", "knowledge_indexing"}
    assert s["knowledge_indexing"]["chunking"]["size_chars"] == 1000
    o, _ = await _call(world, "overview", None)
    assert o["gleepglorp"] == {
        "state": "ready",
        "model": "claude-small",
        "provider": "Claude plan",
        "web_access": True,
        "memory": True,
    }
    assert o["counts"]["agents"] == 2 and o["counts"]["providers"] == 4
    assert "self-configuration" not in o["names"]["mcp_servers"]  # the surface row is not a server
    assert o["names"]["agents"] == ["plain", "wide"]


async def test_unknown_name_lists_only_that_kinds_valid_names(world) -> None:
    for kind in sorted(LIST_KINDS):
        data, text = await _call(world, kind, "nope")
        assert data is None and "nope" in text and "Valid names:" in text
    _, text = await _call(world, "agents", "nope")
    assert "wide" in text and "Docs KB" not in text and "Docs server" not in text
    _, text = await _call(world, "routines", "nope")
    assert "wide" in text and "plain" in text
    _, text = await _call(world, "bogus-kind", None)
    assert "Valid kinds" in text


# --- structural allowlist and classification ---------------------------------------------


def _check_nested(kind: str, value: Any, path: str) -> None:
    allowed = ALLOWED[kind]["nested"]
    if isinstance(value, dict):
        assert set(value) <= allowed, f"{kind}{path}: undeclared keys {set(value) - allowed}"
        for k, v in value.items():
            _check_nested(kind, v, f"{path}.{k}")
    elif isinstance(value, list):
        for v in value:
            _check_nested(kind, v, f"{path}[]")


def check_output_keys(kind: str, data: Any) -> None:
    """Every dict an output holds is declared by the kind's constants."""
    if isinstance(data, list):
        for item in data:
            assert set(item) <= ALLOWED[kind]["list"], f"{kind}: undeclared list keys in {item}"
        return
    assert set(data) <= ALLOWED[kind]["detail"], (
        f"{kind}: undeclared keys {set(data) - ALLOWED[kind]['detail']}"
    )
    for k, v in data.items():
        if kind == "built_in_tools" and k == "settings":
            continue  # a tool's own non-secret Config field names, checked by its own test
        _check_nested(kind, v, f".{k}")


async def test_every_output_key_is_declared(world) -> None:
    for kind, name, data, _ in await _everything(world):
        if data is not None:
            check_output_keys(kind, data)


async def test_a_view_refuses_an_undeclared_key(world, monkeypatch) -> None:
    """``_emit`` is the runtime guard: a key outside the constant is refused, not shown."""
    monkeypatch.setitem(
        ALLOWED, "providers", {**ALLOWED["providers"], "detail": frozenset({"name", "type"})}
    )
    with pytest.raises(views.UndeclaredKeyError):
        await views.read(world.conn, world.enc, "providers", "OpenAI main")


def test_every_kind_is_classified() -> None:
    from the_one.gleepglorp.read_tool import ReadAppConfigTool

    enum = set(ReadAppConfigTool.parameters["properties"]["kind"]["enum"])
    assert enum == set(KINDS) == set(views.VIEWS) == set(ALLOWED) == set(PARITY_DRIVER)
    assert len(KINDS) == 11
    for kind in KINDS:
        assert set(ALLOWED[kind]) == {"list", "detail", "nested"}
    # List kinds declare {name, summary} entries; the others have no list entry.
    assert {k for k in KINDS if ALLOWED[k]["list"]} == set(LIST_KINDS)


# --- read-only by construction ----------------------------------------------------------


async def _snapshot(conn) -> tuple[Any, ...]:
    async with conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name"
    ) as c:
        master = [tuple(r) for r in await c.fetchall()]
    async with conn.execute("PRAGMA schema_version") as c:
        version = (await c.fetchone())[0]
    async with conn.execute("PRAGMA user_version") as c:
        user_version = (await c.fetchone())[0]
    return conn.total_changes, master, version, user_version


async def test_reads_change_nothing(world) -> None:
    before = await _snapshot(world.conn)
    await _everything(world)
    assert await _snapshot(world.conn) == before


async def test_first_read_of_gleepglorp_settings_writes_nothing(tmp_path) -> None:
    from tests._schema_template import connect_template_db
    from the_one.encryption import get_encryptor

    conn = await connect_template_db(tmp_path / "empty.db")
    try:
        enc = get_encryptor(tmp_path)
        before = await _snapshot(conn)
        async with conn.execute("SELECT COUNT(*) FROM app_metadata WHERE key = 'gleepglorp'") as c:
            assert (await c.fetchone())[0] == 0
        for kind in KINDS:
            try:
                await views.read(conn, enc, kind, None)
            except PlainMessage:
                pass
        assert await _snapshot(conn) == before
        async with conn.execute("SELECT COUNT(*) FROM app_metadata WHERE key = 'gleepglorp'") as c:
            assert (await c.fetchone())[0] == 0
    finally:
        await conn.close()


# --- a row that cannot be decrypted degrades; nothing raises ---------------------------------


async def test_an_undecryptable_row_reads_unreadable_in_the_list(world) -> None:
    stale = Fernet(Fernet.generate_key()).encrypt(b"old-key-value").decode()
    await world.conn.execute("UPDATE llm_providers SET api_key = ? WHERE id = 'p-openai'", (stale,))
    await world.conn.execute("UPDATE agents SET tool_overrides = ? WHERE name = 'wide'", (stale,))
    await world.conn.commit()

    providers = await views.read(world.conn, world.enc, "providers")
    by = {e["name"]: e["summary"] for e in providers}
    assert by["OpenAI main"] == UNREADABLE
    assert by["Claude plan"] == "anthropic-plan"  # the rest of the list is still there
    agents = {e["name"]: e["summary"] for e in await views.read(world.conn, world.enc, "agents")}
    assert agents["wide"] == UNREADABLE and agents["plain"] != UNREADABLE

    for kind, name in (("providers", "OpenAI main"), ("agents", "wide")):
        with pytest.raises(PlainMessage, match="encryption key changed"):
            await views.read(world.conn, world.enc, kind, name)
    # Everything else still reads, and nothing leaked through the failure.
    _, text = await _call(world, "overview", None)
    assert "wide" in text


# --- never notes or chats ---------------------------------------------------------------------


async def test_never_notes_or_chat_content(world) -> None:
    blob = "\n".join(text for *_, text in await _everything(world))
    assert SEEDS["note_text"] not in blob and SEEDS["chat_message_text"] not in blob
    assert "A chat" not in blob  # not even a chat title


# --- helpers ----------------------------------------------------------------------------------


def test_scrub_url() -> None:
    s = views.scrub_url
    assert s("https://u:p@h.example:81/a/b?q=1#f", keep_path=True) == "https://h.example:81/a/b"
    assert s("https://u:p@h.example:81/a/b?q=1", keep_path=False) == "https://h.example:81"
    assert s("http://[::1]:8080/x", keep_path=False) == "http://[::1]:8080"
    assert s("localhost:11434/v1", keep_path=True) is None  # no scheme: never echoed
    assert s("", keep_path=True) is None and s(None, keep_path=True) is None
    assert s("http://", keep_path=True) is None
    assert s("http://h:notaport/x", keep_path=True) is None
    assert views.cut("x" * 300, 200).endswith("…") and len(views.cut("x" * 300, 200)) == 200
