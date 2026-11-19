"""The secret guard for proposals (M36 F2 L3, DD9)."""

from __future__ import annotations

import pytest

from tests._schema_template import connect_template_db
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.config import AgentConfig
from the_one.db.encryption_corpora import Corpora, gather_corpora, secret_leaves
from the_one.db.models import Connector, LLMProviderConfig, MCPSource
from the_one.db.repositories import (
    AgentExternalCredentialRepository,
    ConnectorRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SecretRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import get_encryptor
from the_one.gleepglorp.proposals import guard
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository
from the_one.gleepglorp.proposals.tool import ProposeChangeTool

# Low-entropy, prefix-free, short runs: only the corpora check can recognise these.
PROVIDER_KEY = "swordfish provider key"
LIBRARY_VALUE = "plum-library-secret-value"
MCP_HEADER = "mauve-mcp-header-value"
CONNECTOR_TOKEN = "olive-connector-token"
OAUTH_ACCESS = "teal-oauth-access-token"
DCR_SECRET = "coral-dcr-client-secret"
TOOL_SECRET = "amber-web-search-key"
EXT_SECRET = "ivory-external-credential"
OVERRIDE_HEADER = "rose-override-header"
OVERRIDE_PLAIN = "lilac-plain-header-value"
OVERRIDE_ENV = "slate-override-env-value"
OVERRIDE_ENV_PLAIN = "tan-plain-env-value"
OVERRIDE_BEARER = "navy-override-bearer"
OVERRIDE_AUTH = "grey-override-authorization"
OVERRIDE_TOOL_SECRET = "gold-override-brave-key"
TOKEN_TYPE = "bearer-token-type-label"
SCOPE = "read write admin scopes"
CLIENT_ID = "public-client-id-value"


@pytest.fixture
async def world(tmp_path, monkeypatch):
    conn = await connect_template_db(tmp_path / "g.db")
    enc = get_encryptor(tmp_path)
    await LLMProviderRepository(conn, enc).create(
        LLMProviderConfig(
            id="p1",
            name="Main",
            type="openai",
            base_url="https://api.example.com",
            api_key=PROVIDER_KEY,
        )
    )
    await LLMProviderRepository(conn, enc).create(
        LLMProviderConfig(
            id="p2",
            name="Plan",
            type="anthropic-plan",
            base_url="https://api.anthropic.com",
            secrets={
                "access_token": OAUTH_ACCESS,
                "token_type": TOKEN_TYPE,
                "scope": SCOPE,
                "token_expires_at": 1_800_000_000,
            },
        )
    )
    await MCPSourceRepository(conn, enc).create(
        MCPSource(
            id="m1",
            name="Docs",
            type="streamable-http",
            config={"url": "https://docs.example.com/mcp"},
            secrets={
                "X-Api-Key": MCP_HEADER,
                "dcr_credentials": {"client_id": CLIENT_ID, "client_secret": DCR_SECRET},
            },
        )
    )
    await ConnectorRepository(conn, enc).create(
        Connector(id="c1", name="Discord", type="discord", secrets={"token": CONNECTOR_TOKEN})
    )
    await SecretRepository(conn, enc).create(
        "github", "GitHub", ["shell"], [{"key": "gh", "value": LIBRARY_VALUE}]
    )
    await ToolConfigRepository(conn, enc).upsert(
        "web_search", {}, secrets={"brave_api_key": TOOL_SECRET}, enabled=True
    )
    await AgentExternalCredentialRepository(conn, enc).create(
        source_id="m1", label="cred", identifier="ext-identifier-1", secret=EXT_SECRET
    )
    store = SQLiteAgentStore(conn, enc)
    await store.save(
        AgentConfig(
            name="target",
            mcp_overrides={
                "Docs": {
                    "headers": {
                        "X-Secret": OVERRIDE_HEADER,
                        "X-Plain": OVERRIDE_PLAIN,
                        "Authorization": OVERRIDE_AUTH,
                    },
                    "env": {"SECRET_ENV": OVERRIDE_ENV, "PLAIN_ENV": OVERRIDE_ENV_PLAIN},
                    "bearer_token": OVERRIDE_BEARER,
                    "plain_names": ["x-plain", "authorization", "PLAIN_ENV", "bearer_token"],
                    "enabled_tools": ["search-the-docs-tool-list"],
                }
            },
            tool_overrides={
                "web_search": {"brave_api_key": OVERRIDE_TOOL_SECRET, "timeout": 30},
                "shell": {"allow": "not-a-secret-field-value"},
            },
        )
    )
    await store.save(AgentConfig(name="plain"))

    async def _conn():
        return conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    class W:
        pass

    w = W()
    w.conn, w.enc = conn, enc  # type: ignore[attr-defined]
    yield w
    await conn.close()


async def refused(world, changes) -> bool:
    return await guard.check(world.conn, world.enc, changes) == guard.REFUSAL


async def passes(world, changes) -> bool:
    return await guard.check(world.conn, world.enc, changes) is None


STORED = [
    PROVIDER_KEY,
    LIBRARY_VALUE,
    MCP_HEADER,
    CONNECTOR_TOKEN,
    OAUTH_ACCESS,
    DCR_SECRET,
    TOOL_SECRET,
    EXT_SECRET,
    OVERRIDE_HEADER,
    OVERRIDE_ENV,
    OVERRIDE_BEARER,
    OVERRIDE_AUTH,
    OVERRIDE_TOOL_SECRET,
]


async def test_every_stored_secret_is_refused_inside_a_prompt_and_as_a_name(world) -> None:
    for value in STORED:
        assert await refused(world, {"system_prompt": f"Use {value} when you call the API."}), value
        assert await refused(world, {"name": value}), value
        assert await refused(world, {"rules": [{"text": f"  {value}  "}]}), value
        assert await refused(world, {"schedule": {"note": [f"x {value}"]}}), value


async def test_the_refusal_is_one_sentence_that_never_echoes(world) -> None:
    out = await guard.check(world.conn, world.enc, {"text": f"a {LIBRARY_VALUE} b"})
    assert out == (
        "That looks like a key or token. Leave it out of the proposal and tell the operator "
        "to enter it on the right page."
    )
    assert LIBRARY_VALUE not in out
    key_shaped = await guard.check(world.conn, world.enc, {"text": "ghp_" + "aB3dE5gH7jK9mN1pQ"})
    assert key_shaped == out  # the same sentence for both cases


async def test_public_and_exempt_values_are_not_refused(world) -> None:
    assert await passes(world, {"text": f"Plain header {OVERRIDE_PLAIN} is fine."})
    assert await passes(world, {"text": f"Plain env {OVERRIDE_ENV_PLAIN} is fine."})
    assert await passes(world, {"text": f"The token type is {TOKEN_TYPE}."})
    assert await passes(world, {"text": f"Scopes: {SCOPE}"})
    assert await passes(world, {"text": f"Public client {CLIENT_ID}"})
    assert await passes(world, {"text": "search-the-docs-tool-list"})  # a tool list, never a secret
    assert await passes(world, {"text": "not-a-secret-field-value"})  # a non-secret tool field
    assert await passes(world, {"text": "ext-identifier-1"})  # an identifier, never the secret
    # A disabled MCP tool and an enabled_tools entry pass.
    assert await passes(
        world,
        {"disabled_tools": ["mcp__docs__search"], "enabled_tools": ["shell", "mcp__docs__fetch"]},
    )


async def test_authorization_and_bearer_are_never_exempt_even_when_listed_plain(world) -> None:
    # Both are in plain_names above, and both are still refused.
    assert await refused(world, {"text": OVERRIDE_AUTH})
    assert await refused(world, {"text": OVERRIDE_BEARER})


async def test_prefixes_and_the_entropy_rule(world) -> None:
    tail = "aB3dE5gH7jK9mN1p"
    assert len(tail) == guard.KEY_PREFIX_MIN_TAIL
    for prefix in guard.KEY_PREFIXES:
        assert await refused(world, {"t": f"use {prefix}{tail} now"}), prefix
        if prefix != "sk-ant-":  # "sk-" already covers it: "ant-" counts toward its tail
            assert await passes(world, {"t": f"use {prefix}{tail[:-1]} now"}), prefix  # one short
    # A prefix inside a word is not a key.
    assert await passes(world, {"t": "task-management-tools-are-fine"})
    # A long run with high entropy is refused; the same run one character short passes.
    run = "Zx9Qm4Lr7Tk2Vb8Nc5Hd3Jf6Gs1Pw0Ya"
    assert len(run) == guard.KEY_MIN_LEN
    assert await refused(world, {"t": f"prompt {run} end"})
    assert await passes(world, {"t": f"prompt {run[:-1]} end"})
    # A long low-entropy run is not a key.
    assert await passes(world, {"t": "z" * 80})
    assert guard.KEY_MIN_ENTROPY == 4.0


async def test_the_hex_run_rule(world) -> None:
    assert guard.HEX_KEY_MIN_LEN == 32
    hex32 = "0123456789abcdef0123456789abcdef"
    assert len(hex32) == 32
    assert await refused(world, {"t": f"key {hex32} end"})
    assert await refused(world, {"t": hex32.upper()})
    # A 40-character git SHA in a prompt is refused (the accepted trade-off).
    assert await refused(world, {"t": "pin to commit 9fea53cd9fea53cd9fea53cd9fea53cd9fea53cd."})
    # One character short passes; a hex run glued to other letters is not a bounded hex run.
    assert await passes(world, {"t": f"key {hex32[:-1]} end"})
    # A canonical hyphenated UUID passes; the same digits without hyphens do not.
    assert await passes(world, {"t": "id 3f2b8c1e-9a47-4d6e-b5c0-7e1f2a9d8c34 ok"})
    assert await refused(world, {"t": "id 3f2b8c1e9a474d6eb5c07e1f2a9d8c34 ok"})


async def test_a_uuid_and_ordinary_prose_pass(world) -> None:
    assert await passes(
        world, {"t": "Agent id 3f2b8c1e-9a47-4d6e-b5c0-7e1f2a9d8c34 is the target."}
    )
    prose = (
        "You are a careful research assistant. Read the question, look for the most recent "
        "sources, and answer in short paragraphs. When you are unsure, say so plainly and "
        "suggest where the operator could look next. Never guess at numbers; cite the page "
        "you used. Keep a friendly, steady tone, and finish every answer with one next step."
    )
    assert await passes(world, {"system_prompt": prose, "description": "A friendly helper."})
    assert await passes(world, {})
    assert await passes(world, {"max_iterations": 20, "enabled": True, "notes": None})


async def test_corpora_are_gathered_fresh_each_call(world) -> None:
    secret = "freshly-rotated-secret"
    assert await passes(world, {"t": secret})
    await SecretRepository(world.conn, world.enc).create(
        "new", "New", ["shell"], [{"key": "k", "value": secret}]
    )
    assert await refused(world, {"t": secret})


async def test_a_value_that_will_not_decrypt_is_skipped(world) -> None:
    await world.conn.execute("UPDATE connectors SET secrets = 'not-a-valid-ciphertext'")
    await world.conn.commit()
    assert await passes(world, {"t": CONNECTOR_TOKEN})  # the unreadable value cannot be searched
    assert await refused(world, {"t": LIBRARY_VALUE})  # the rest still is
    assert await refused(world, {"t": "xoxb-" + "aB3dE5gH7jK9mN1pQ"})  # the key shape still is


# --- secret_leaves, column by column ----------------------------------------------------------


def test_secret_leaves_per_column_and_skip() -> None:
    c = Corpora(
        api_keys=[("p", "provider-api-key")],
        provider_secrets=[
            (
                "p",
                {
                    "access_token": "access-token-value",
                    "refresh_token": "refresh-token-value",
                    "token_type": "token-type-value",
                    "scope": "scope-value-here",
                    "scopes": ["scopes-value-here"],
                    "token_expires_at": 1234567890123,
                    "dcr_credentials": {
                        "client_id": "client-id-value",
                        "client_secret": "dcr-secret-val",
                    },
                },
            )
        ],
        mcps=[("m", {"Authorization": "mcp-auth-value", "X-Key": "mcp-key-value"})],
        connectors=[("c", {"token": "connector-token"})],
        tool_configs=[("web_search", {"brave_api_key": "tool-secret-key"})],
        ext_credentials=[("ident-value", "ext-secret-value")],
        secret_values=[("v", "library-secret-value")],
        agents=[
            (
                "a",
                {"web_search": {"brave_api_key": "override-tool-key", "timeout": "30000000"}},
                {
                    "Docs": {
                        "headers": {"X-A": "header-a-value", "X-Plain": "header-plain-val"},
                        "env": {"E": "env-value-here", "P": "env-plain-value"},
                        "bearer_token": "bearer-token-val",
                        "plain_names": ["x-plain", "P"],
                        "enabled_tools": ["tools-list-entry"],
                    }
                },
            )
        ],
    )
    assert secret_leaves(c) == {
        "provider-api-key",
        "access-token-value",
        "refresh-token-value",
        "dcr-secret-val",
        "mcp-auth-value",
        "mcp-key-value",
        "connector-token",
        "tool-secret-key",
        "ext-secret-value",
        "library-secret-value",
        "override-tool-key",
        "header-a-value",
        "env-value-here",
        "bearer-token-val",
    }


def test_secret_leaves_min_len_and_trimming() -> None:
    c = Corpora(
        api_keys=[("p", "short"), ("q", "  padded-secret  ")],
        secret_values=[("v", "1234567"), ("w", "12345678")],
    )
    assert secret_leaves(c) == {"padded-secret", "12345678"}
    assert secret_leaves(c, min_len=3) == {"short", "padded-secret", "1234567", "12345678"}
    assert secret_leaves(Corpora()) == set()


async def test_secret_leaves_from_a_real_gather(world) -> None:
    leaves = secret_leaves(await gather_corpora(world.conn, world.enc, strict=False))
    assert set(STORED) <= leaves
    for public in (TOKEN_TYPE, SCOPE, CLIENT_ID, OVERRIDE_PLAIN, OVERRIDE_ENV_PLAIN):
        assert public not in leaves
    assert "ext-identifier-1" not in leaves and "search-the-docs-tool-list" not in leaves


# --- through the tool ---------------------------------------------------------------------------


@pytest.fixture
def tool() -> ProposeChangeTool:
    return ProposeChangeTool(agent_name="GleepGlorp")


async def propose(tool, **kw) -> str:
    token = current_turn.set(TurnContext(session_id="s1"))
    try:
        return await tool.execute(**kw)
    finally:
        current_turn.reset(token)


async def test_a_refused_proposal_writes_no_row_and_a_clean_one_does(world, tool) -> None:
    repo = GleepGlorpProposalRepository(world.conn)
    for text in (f"Always use {LIBRARY_VALUE}.", "Use ghp_aB3dE5gH7jK9mN1pQrS here."):
        out = await propose(
            tool, kind="rule", action="create", agent="plain", changes={"text": text}
        )
        assert out == guard.REFUSAL
        assert await repo.list_for_session("s1") == []
    out = await propose(
        tool, kind="rule", action="create", agent="plain", changes={"text": "Be brief."}
    )
    assert out.startswith("Proposal 1 is waiting")
    assert len(await repo.list_for_session("s1")) == 1
    # A name carrying a secret on an agent create is refused too.
    out = await propose(tool, kind="agent", action="create", changes={"name": OVERRIDE_BEARER})
    assert out == guard.REFUSAL
