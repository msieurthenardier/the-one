"""Seed every secret slot of the app with a distinct, recognisable value (M36 F1 L05).

Used by the secret-parity test in ``test_gleepglorp_views.py`` and its twin through the tool
in ``test_gleepglorp_read_tool.py``. Every seeded value is 16+ characters and ends in a
mixed-case four-character tail that appears nowhere in the views' own text, so the test can
assert both the whole value and its last four characters are absent from every output.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import (
    ChatSession,
    Connector,
    KBItem,
    KnowledgeBase,
    LLMProviderConfig,
    MCPSource,
)
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    AgentMcpToolCacheRepository,
    AgentNoteRepository,
    AgentRuleRepository,
    ConnectorRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import get_encryptor
from the_one.gleepglorp import GleepGlorpSettings, save_settings
from the_one.routines.repository import AgentRoutineRepository

_TAILS = [
    "kQ7z", "Xw3P", "mB9v", "Tj4N", "eR6y", "Lc2H", "pU8s", "Gd5F", "aZ1W", "vN7b",
    "Yh3K", "sM6q", "Dx9R", "fJ2T", "Cw8E", "uP4L", "Bn5G", "rV1A", "Hk7X", "Zt3M",
    "Qy6D", "Wf9C", "jS2U", "Ne5B", "oI8P", "iA4Y", "cL6V", "gO3Q", "bT9J", "dE2H",
    "nF7R", "lK5W", "xC1S", "hD8M", "tG4Z", "wB6N", "yU9X", "zP2L", "qV3E", "kJ5T",
    "mR8C", "eX4B", "Sd7K", "Uf2N", "Lh9V",
]  # fmt: skip

# slot label -> seeded value. Order is the creation order of this table.
SECRET_SLOTS = [
    "provider_api_key",
    "provider_config_decoy",
    "provider_baseurl_password",
    "provider_baseurl_query",
    "plan_access_token",
    "plan_refresh_token",
    "plan_token_api_key",
    "plan_token_set_at",
    "mcp_secret_authorization",
    "mcp_secret_bearer",
    "mcp_oauth_access_token",
    "mcp_oauth_refresh_token",
    "mcp_oauth_token_expires_at",
    "mcp_oauth_token_type",
    "mcp_oauth_scope",
    "mcp_oauth_dcr_client_secret",
    "mcp_config_header_sensitive",
    "mcp_config_header_plain",
    "mcp_config_env_sensitive",
    "mcp_config_env_plain",
    "mcp_stdio_secret_env",
    "mcp_address_password",
    "mcp_address_query",
    "mcp_cache_server_info",
    "mcp_cache_instructions",
    "mcp_cache_meta",
    "mcp_cache_capabilities",
    "mcp_sandbox_writable_path",
    "connector_token",
    "connector_config_decoy_peer",
    "connector_config_decoy_listen",
    "agent_tool_override",
    "agent_mcp_override_credential",
    "agent_mcp_tool_cache_description",
    "tool_config_secret",
    "tool_config_secret_decoy_in_config",
    "tool_config_url_password",
    "tool_config_url_query",
    "external_credential",
    "library_secret_value",
    "surface_row_bearer",
    "chat_message_text",
    "note_text",
]
assert len(_TAILS) >= len(SECRET_SLOTS)

SEEDS: dict[str, str] = {
    label: f"{label.replace('_', '-')}-XYZZY-0f1e2d3c-{_TAILS[i]}"
    for i, label in enumerate(SECRET_SLOTS)
}
# A value must read as a secret-looking opaque token, never as ordinary words.
assert all(len(v) >= 16 for v in SEEDS.values())

# Residuals shown on purpose (asserted): a token in a command argument and in an address path.
ARG_TOKEN = "ARGTOKEN-shown-as-written-9k2L"
PATH_TOKEN = "PATHTOKEN-shown-as-written-4m7Q"


async def seed(tmp_path) -> SimpleNamespace:
    """Build a database with every slot filled; return ``SimpleNamespace(conn, enc, ids)``."""
    conn = await connect_template_db(tmp_path / "seed.db")
    enc = get_encryptor(tmp_path)
    s = SEEDS

    # --- providers (api_key, secrets, free-form config, base URLs) --------------------
    prov = LLMProviderRepository(conn, enc)
    await prov.create(
        LLMProviderConfig(
            id="p-openai",
            name="OpenAI main",
            type="openai",
            base_url=(
                f"https://user:{s['provider_baseurl_password']}@api.example.com:8443"
                f"/v1/{PATH_TOKEN}?token={s['provider_baseurl_query']}"
            ),
            api_key=s["provider_api_key"],
            config={"decoy": s["provider_config_decoy"]},
        )
    )
    await prov.create(
        LLMProviderConfig(
            id="p-plan",
            name="Claude plan",
            type="anthropic-plan",
            base_url="https://api.anthropic.com",
            secrets={
                "access_token": s["plan_access_token"],
                "refresh_token": s["plan_refresh_token"],
            },
        )
    )
    await prov.create(
        LLMProviderConfig(
            id="p-token",
            name="Claude token",
            type="anthropic-plan-token",
            base_url="https://api.anthropic.com",
            api_key=s["plan_token_api_key"],
            secrets={"token_set_at": s["plan_token_set_at"]},
        )
    )
    await prov.create(
        LLMProviderConfig(
            id="p-local", name="Local", type="ollama", base_url="http://localhost:11434"
        )
    )

    # --- MCP servers (secrets, six OAuth keys, config env/headers, _cache, address) --------
    mcp = MCPSourceRepository(conn, enc)
    await mcp.create(
        MCPSource(
            id="m-http",
            name="Docs server",
            type="streamable-http",
            config={
                "url": (
                    f"https://user:{s['mcp_address_password']}@mcp.example.com:9443"
                    f"/mcp/{PATH_TOKEN}?token={s['mcp_address_query']}"
                ),
                "headers": {
                    "X-Api-Key": s["mcp_config_header_sensitive"],
                    "X-Plain": s["mcp_config_header_plain"],
                },
                "_cache": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search the docs. " + "long " * 80,
                            "input_schema": {"type": "object"},
                        },
                        {
                            "name": "fetch",
                            "description": "Fetch a page.",
                            "input_schema": {"type": "object"},
                        },
                    ],
                    "capabilities": {"x": s["mcp_cache_capabilities"]},
                    "server_info": {"name": s["mcp_cache_server_info"]},
                    "instructions": s["mcp_cache_instructions"],
                    "meta": {"note": s["mcp_cache_meta"]},
                    "protocol_version": "2026-07-28",
                    "last_updated": 1_800_000_000.0,
                    "last_check": {"status": "ok", "at": 1_800_000_100.0},
                    "auth_posture": "oauth",
                },
            },
            secrets={
                "Authorization": s["mcp_secret_authorization"],
                "bearer_token": s["mcp_secret_bearer"],
                "access_token": s["mcp_oauth_access_token"],
                "refresh_token": s["mcp_oauth_refresh_token"],
                "token_expires_at": s["mcp_oauth_token_expires_at"],
                "token_type": s["mcp_oauth_token_type"],
                "scope": s["mcp_oauth_scope"],
                "dcr_credentials": {
                    "client_id": "client-id-plain",
                    "client_secret": s["mcp_oauth_dcr_client_secret"],
                },
            },
        )
    )
    await mcp.create(
        MCPSource(
            id="m-stdio",
            name="Local tool",
            type="stdio",
            config={
                "command": "npx",
                "args": ["-y", "some-package", "--token", ARG_TOKEN],
                "cwd": "/home/work/project",
                "env": {
                    "SENSITIVE_ENV": s["mcp_config_env_sensitive"],
                    "PLAIN_ENV": s["mcp_config_env_plain"],
                },
                "sandbox": {"writable_paths": [s["mcp_sandbox_writable_path"]]},
            },
            secrets={"DB_PASSWORD": s["mcp_stdio_secret_env"]},
        )
    )
    # The self-configuration surface row of agent "wide": a bearer credential, a loopback URL.
    await mcp.create(
        MCPSource(
            id="m-surface",
            name="self-configuration",
            type="streamable-http",
            config={
                "url": "http://127.0.0.1:8484/self-configuration-mount/",
                "self_configuration": {"agent": "wide"},
            },
            secrets={"bearer_token": s["surface_row_bearer"]},
        )
    )

    # --- connectors (secrets + decoys in the plain config) ----------------------------
    conns = ConnectorRepository(conn, enc)
    await conns.create(
        Connector(
            id="c-discord",
            name="Team Discord",
            type="discord",
            config={
                "default_agent": "wide",
                "channel_map": {"chan-555": "plain"},
                "allowlist": {"peers": [s["connector_config_decoy_peer"]], "channels": []},
                "always_listen": [s["connector_config_decoy_listen"]],
            },
            secrets={"token": s["connector_token"]},
        )
    )

    # --- knowledge base ---------------------------------------------------------------
    await KnowledgeBaseRepository(conn).create(
        KnowledgeBase(id="kb1", name="Docs KB", description="Company docs")
    )
    items = KBItemRepository(conn)
    await items.create(
        KBItem(id="f1", kb_id="kb1", type="folder", path_or_url="/home/work/docs", status="indexed")
    )
    await items.create(
        KBItem(
            id="i1",
            kb_id="kb1",
            parent_id="f1",
            type="file",
            path_or_url="/home/work/docs/a.md",
            status="indexed",
            indexed_at="2026-11-01T10:00:00+00:00",
        )
    )

    # --- Library secret (value) -------------------------------------------------------
    lib = await SecretRepository(conn, enc).create(
        "github",
        "GitHub access",
        ["shell"],
        [{"key": "gh_token", "value": s["library_secret_value"]}],
    )

    # --- agents -----------------------------------------------------------------------
    store = SQLiteAgentStore(conn, enc)
    await store.save(
        AgentConfig(
            name="wide",
            description="The wide agent",
            provider_config_id="p-openai",
            llm_model="gpt-x",
            system_prompt="You are the wide agent.",
            enabled_tools=None,
            disabled_tools=["web_fetch"],
            kb_ids=["kb1"],
            mcp_source_ids=["m-http", "m-surface"],
            secret_ids=[lib.id],
            tool_overrides={"shell": {"allow": s["agent_tool_override"]}},
            mcp_overrides={
                "Docs server": {"headers": {"X-Key": s["agent_mcp_override_credential"]}}
            },
            notes_enabled=True,
        )
    )
    await store.save(AgentConfig(name="plain", provider_config_id="p-local", llm_model="m"))
    await AgentRuleRepository(conn).create("wide", "Always answer briefly.")
    await AgentRoutineRepository(conn).create(
        "wide",
        {
            "name": "Morning digest",
            "prompt": "Summarise the news.",
            "schedule": {
                "start": {"date": "2026-10-11", "time": "09:00"},
                "repeat": {"every": 1, "unit": "day"},
                "ends": {"kind": "never"},
            },
        },
    )
    await AgentNoteRepository(conn).create(
        "wide",
        s["note_text"],
        untrusted=False,
        sources=[],
        origin_kind="other",
        origin_session_id=None,
        origin_label=None,
        origin_platform=None,
        origin_peer_id=None,
        origin_peer_name=None,
    )
    cache = AgentMcpToolCacheRepository(conn)
    stamp = await cache.agent_updated_at("wide")
    await cache.put_if_unchanged(
        "wide",
        "m-http",
        [{"name": "t", "description": s["agent_mcp_tool_cache_description"], "input_schema": {}}],
        stamp,
    )
    await AgentExternalCredentialRepository(conn, enc).create(
        source_id="m-http", label="cred", identifier="ext-1", secret=s["external_credential"]
    )

    # --- tool config (a non-secret field beside a secret one) -------------------------
    await ToolConfigRepository(conn, enc).upsert(
        "web_search",
        {
            "search_backend": "brave",
            "google_pse_cse_id": "cse-nonsecret-visible",
            "brave_api_key": s["tool_config_secret_decoy_in_config"],
            "searxng_base_url": (
                f"https://user:{s['tool_config_url_password']}@searx.example.com:8080"
                f"/search?token={s['tool_config_url_query']}"
            ),
        },
        secrets={"brave_api_key": s["tool_config_secret"]},
        enabled=True,
    )

    # --- a chat (never readable) and GleepGlorp's own settings ----------------------------
    from the_one.db.repositories import ChatSessionRepository

    await ChatSessionRepository(conn).create(
        ChatSession(
            id="chat1",
            agent_name="wide",
            title="A chat",
            messages=json.dumps([{"role": "user", "content": s["chat_message_text"]}]),
        )
    )
    await save_settings(conn, GleepGlorpSettings(provider_config_id="p-plan", model="claude-small"))
    return SimpleNamespace(conn=conn, enc=enc, library_secret_id=lib.id)
