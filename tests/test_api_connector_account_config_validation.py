"""Tests for the API-layer per-type ConnectorAccount.config validator.

M11 F1 L2 — :func:`_validate_connector_account_config` in
:mod:`the_one.interfaces.web.api` gates the shape of
``account.config`` at the API write boundary (POST and PUT on
``/api/connector-accounts``). Discord branch validates
``intents``, ``guilds``, and ``presence``; stub branch passes any
shape; the trailing ``else`` defensive-exhaustiveness raise is
unreachable for properly-validated input.

The rejection-test assertions pin the 422 detail strings
byte-for-byte per the ``verbatim-message-equality`` convention
codified in agents.md from M11 F1 L1.
"""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    """Create a test client with an isolated DB and test encryptor.

    Mirrors the fixture shape established in ``tests/test_db_api.py``
    so the connector-account routes resolve against an in-memory
    schema and the encryptor patch keeps secrets round-tripping.
    """
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    test_encryptor = Encryptor(test_key, key_path=key_path)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


def _discord_payload(config: dict) -> dict:
    """Standard Discord-type connector-account POST payload with the
    given config. BOT_TOKEN secret is required at the model level."""
    return {
        "name": "Discord Bot",
        "type": "discord",
        "config": config,
        "secrets": {"BOT_TOKEN": "discord-bot-token-secret"},
    }


class TestConnectorAccountConfigValidation:
    # ── intents rejection cases ───────────────────────────────────

    async def test_intents_missing_required_key_rejected(
        self, client: AsyncClient
    ) -> None:
        """intents missing one of {message_content, members, guilds} → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload(
                {"intents": {"message_content": True, "members": True}}
            ),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.intents must have exactly these keys: "
            "['guilds', 'members', 'message_content']; got: "
            "['members', 'message_content']."
        )

    async def test_intents_extra_keys_rejected(self, client: AsyncClient) -> None:
        """intents with an extra key beyond the canonical three → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload(
                {
                    "intents": {
                        "message_content": True,
                        "members": True,
                        "guilds": True,
                        "presences": True,
                    }
                }
            ),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.intents must have exactly these keys: "
            "['guilds', 'members', 'message_content']; got: "
            "['guilds', 'members', 'message_content', 'presences']."
        )

    async def test_intents_non_bool_value_rejected(self, client: AsyncClient) -> None:
        """intents with a JSON ``1`` (int, not bool) → 422 (bool-is-int trap)."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload(
                {
                    "intents": {
                        "message_content": 1,
                        "members": True,
                        "guilds": True,
                    }
                }
            ),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.intents.message_content must be a "
            "boolean; got int."
        )

    async def test_intents_empty_dict_rejected(self, client: AsyncClient) -> None:
        """intents = {} violates the 'exactly these three keys' rule → 422.

        Per Design Decisions §1: the absence of the ``intents`` key is the
        canonical 'use defaults' signal; the explicit empty-dict form is
        rejected as deliberate operator intent that the validator must
        treat as a malformed shape.
        """
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"intents": {}}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.intents must have exactly these keys: "
            "['guilds', 'members', 'message_content']; got: []."
        )

    async def test_intents_not_a_dict_rejected(self, client: AsyncClient) -> None:
        """intents as a list (non-dict) → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"intents": ["message_content", "members"]}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.intents must be a dict."
        )

    # ── guilds rejection cases ────────────────────────────────────

    async def test_guilds_non_digit_entry_rejected(self, client: AsyncClient) -> None:
        """guilds with a non-digit string entry → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"guilds": ["123456", "abc123"]}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.guilds entries must be non-empty "
            "decimal-digit strings; got 'abc123'."
        )

    async def test_guilds_non_string_entry_rejected(self, client: AsyncClient) -> None:
        """guilds with an integer entry (not a string) → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"guilds": ["123456", 789]}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.guilds entries must be strings; got int."
        )

    async def test_guilds_not_a_list_rejected(self, client: AsyncClient) -> None:
        """guilds as a string (non-list) → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"guilds": "123456"}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.guilds must be a list of digit-only "
            "strings if present."
        )

    # ── presence rejection cases ──────────────────────────────────

    async def test_presence_non_dict_rejected(self, client: AsyncClient) -> None:
        """presence as a string (non-dict) → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"presence": "watching agents"}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.presence must be a dict if present."
        )

    async def test_presence_empty_name_rejected(self, client: AsyncClient) -> None:
        """presence with name='' (empty string) → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"presence": {"name": "", "type": "watching"}}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.presence.name must be a non-empty string."
        )

    async def test_presence_unknown_type_rejected(self, client: AsyncClient) -> None:
        """presence with type='dancing' (outside the pinned set) → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload(
                {"presence": {"name": "agents", "type": "dancing"}}
            ),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.presence.type must be one of: "
            "['competing', 'listening', 'playing', 'streaming', 'watching']; "
            "got: 'dancing'."
        )

    # ── happy-path cases ──────────────────────────────────────────

    async def test_happy_path_all_three_keys_well_formed(
        self, client: AsyncClient
    ) -> None:
        """All three optional config keys present and well-formed → 201."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload(
                {
                    "intents": {
                        "message_content": True,
                        "members": False,
                        "guilds": True,
                    },
                    "guilds": ["123456789012345678", "987654321098765432"],
                    "presence": {"name": "agent traffic", "type": "watching"},
                }
            ),
        )
        assert resp.status_code == 201

    async def test_happy_path_all_three_keys_absent(self, client: AsyncClient) -> None:
        """Empty config → 201 (M10 F8 backward-compat: no intents key)."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({}),
        )
        assert resp.status_code == 201

    async def test_happy_path_empty_guilds_list(self, client: AsyncClient) -> None:
        """guilds=[] (empty list) → 201; the plugin's sync handles empty/absent."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"guilds": []}),
        )
        assert resp.status_code == 201

    # ── stub-type carve-out ───────────────────────────────────────

    async def test_stub_type_with_discord_shaped_config_passes(
        self, client: AsyncClient
    ) -> None:
        """Stub-type account with arbitrary config bypasses Discord validation."""
        resp = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Stub Bot",
                "type": "stub",
                "config": {
                    "foo": "bar",
                    "intents": "this would fail discord validation",
                },
                "secrets": {"BOT_TOKEN": "stub-token"},
            },
        )
        assert resp.status_code == 201

    # ── system_prompt_directive rejection cases ───────────────────
    # M11 F2 L3: per-account operator-authored system-prompt directive.
    # Optional key on Discord-type config; APPEND-mode at the composer
    # (L3 substrate; L4 ships the UI). Absent → no override. Present →
    # must be a non-empty string.

    async def test_discord_system_prompt_directive_non_string_rejected(
        self, client: AsyncClient
    ) -> None:
        """system_prompt_directive as an int → 422."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"system_prompt_directive": 42}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.system_prompt_directive must be a string "
            "if present; got int."
        )

    async def test_discord_system_prompt_directive_empty_string_rejected(
        self, client: AsyncClient
    ) -> None:
        """system_prompt_directive='' → 422 (absence is the canonical
        'no override' signal; empty string is operator-confusing noise)."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"system_prompt_directive": ""}),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.system_prompt_directive must be a "
            "non-empty string if present (use absence to mean 'no override')."
        )

    # ── system_prompt_directive happy-path cases ──────────────────

    async def test_discord_system_prompt_directive_absent_passes(
        self, client: AsyncClient
    ) -> None:
        """Absent system_prompt_directive → 201 (M10 F8 back-compat: the
        key is optional; absence is the canonical 'no override' signal)."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({}),
        )
        assert resp.status_code == 201

    async def test_discord_system_prompt_directive_short_string_passes(
        self, client: AsyncClient
    ) -> None:
        """A short, well-formed directive → 201."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload(
                {"system_prompt_directive": "Sign replies with a coffee emoji."}
            ),
        )
        assert resp.status_code == 201

    async def test_discord_system_prompt_directive_long_string_passes(
        self, client: AsyncClient
    ) -> None:
        """A 5000-char directive → 201 (no length cap)."""
        resp = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({"system_prompt_directive": "x" * 5000}),
        )
        assert resp.status_code == 201

    async def test_stub_system_prompt_directive_pass_through(
        self, client: AsyncClient
    ) -> None:
        """Stub-type with system_prompt_directive in arbitrary shape → 201
        (stubs don't validate per-type config; this pins the carve-out
        behavior for the new key alongside the existing keys)."""
        resp = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Stub Bot",
                "type": "stub",
                "config": {"system_prompt_directive": 42},
                "secrets": {"BOT_TOKEN": "stub-token"},
            },
        )
        assert resp.status_code == 201

    # ── update path coverage ──────────────────────────────────────

    async def test_update_path_with_malformed_config_rejected(
        self, client: AsyncClient
    ) -> None:
        """PUT with malformed intents config → 422 (covers the second call site)."""
        create = await client.post(
            "/api/connector-accounts",
            json=_discord_payload({}),
        )
        assert create.status_code == 201
        account_id = create.json()["id"]

        resp = await client.put(
            f"/api/connector-accounts/{account_id}",
            json={
                "config": {
                    "intents": {
                        "message_content": 1,
                        "members": True,
                        "guilds": True,
                    }
                }
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "Discord connector config.intents.message_content must be a "
            "boolean; got int."
        )
