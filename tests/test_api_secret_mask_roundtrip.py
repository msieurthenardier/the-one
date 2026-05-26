"""Round-trip safety tests for the GET-mask / PUT-preserve secret contract.

F7 L12 hotfix: secret-bearing PUT handlers historically only recognized the
``__MASKED__`` sentinel (which the Studio UI emits) for "preserve existing"
semantics. They did NOT recognize the mask SHAPES (``***`` / ``***...tail4``)
produced by GET responses. Any external caller that fetched a GET payload and
PUT it back unchanged silently corrupted the stored secret to the literal
mask string — discovered via a Discord connector account whose ``BOT_TOKEN``
persisted to disk as ``***...SD7U`` after such a round-trip.

These tests pin the round-trip safety for all three affected entities
(MCP source, connector account, LLM provider), the canonical sentinel path,
and the negative case where a user-supplied value merely starts with ``***``
but is NOT a mask shape.
"""

from __future__ import annotations

import json
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
async def client_and_key(tmp_path):
    """AsyncClient + raw Fernet key bytes for direct DB ciphertext decrypt.

    The standard ``test_db_api.py`` / ``test_provider_api.py`` ``client``
    fixture does not expose the encryption key for direct-DB assertions.
    This fixture is the same shape but also yields the key bytes so tests
    can verify the *stored* secret matches the original plaintext — not
    just the mask shape of a re-fetched GET response (the mask shape is
    identical whether the stored value is the real secret or the literal
    mask string, which is exactly why the bug was silent).
    """
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(test_key)
    test_encryptor = Encryptor(test_key, key_path=key_path)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, test_key, db_path

    await conn.close()


# ── MCP source round-trip ────────────────────────────────────────────────


class TestMCPSourceRoundTrip:
    async def test_get_put_get_does_not_corrupt_secret(self, client_and_key) -> None:
        """GET → PUT (verbatim) → GET round-trip must preserve stored secret.

        Pre-fix: PUT-ing the GET response back would write the literal mask
        string ``***...c123`` into the DB. Post-fix: ``_looks_masked``
        recognizes the mask shape as "preserve existing" — the stored
        ciphertext still decrypts to the original ``real-bot-token-abc123``.
        """
        client, key, db_path = client_and_key
        real_value = "real-bot-token-abc123"

        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "RT",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"BOT_TOKEN": real_value},
            },
        )
        sid = create.json()["id"]

        # GET — capture the masked response.
        got = await client.get(f"/api/mcp-sources/{sid}")
        assert got.status_code == 200
        masked_payload = got.json()
        assert masked_payload["secrets"]["BOT_TOKEN"] == "***...c123"

        # PUT the GET response back verbatim. Pre-fix: this corrupted the
        # store. Post-fix: ``_looks_masked`` preserves the existing value.
        put = await client.put(f"/api/mcp-sources/{sid}", json=masked_payload)
        assert put.status_code == 200

        # GET again — mask shape unchanged. (Not sufficient on its own;
        # see the direct-decrypt assertion below.)
        got_again = await client.get(f"/api/mcp-sources/{sid}")
        assert got_again.json()["secrets"]["BOT_TOKEN"] == "***...c123"

        # The load-bearing assertion: direct DB inspect must show the
        # ORIGINAL plaintext, not the literal mask string.
        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        decrypted = Fernet(key).decrypt(row["secrets"].encode()).decode()
        stored = json.loads(decrypted)
        assert stored == {"BOT_TOKEN": real_value}, (
            f"Round-trip corrupted the stored secret: got {stored!r}"
        )

    async def test_short_value_mask_roundtrip(self, client_and_key) -> None:
        """Short (≤4 char) secret masks as bare ``***`` — must also round-trip.

        Exercises the other branch of ``_MASK_SHAPE_RE`` (no ``...tail``
        suffix). Pre-fix this would have written ``"***"`` as the stored
        value.
        """
        client, key, db_path = client_and_key
        real_value = "abcd"  # exactly 4 — masks as ``***`` (no suffix)

        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "RT-short",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": real_value},
            },
        )
        sid = create.json()["id"]
        got = await client.get(f"/api/mcp-sources/{sid}")
        assert got.json()["secrets"]["K"] == "***"

        put = await client.put(f"/api/mcp-sources/{sid}", json=got.json())
        assert put.status_code == 200

        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        decrypted = Fernet(key).decrypt(row["secrets"].encode()).decode()
        assert json.loads(decrypted) == {"K": real_value}


# ── Connector account round-trip ─────────────────────────────────────────


class TestConnectorAccountRoundTrip:
    async def test_get_put_get_does_not_corrupt_secret(self, client_and_key) -> None:
        """Mirror of the MCP test for connector_accounts.

        Reproduces the exact failure mode discovered in production for the
        Discord ``BOT_TOKEN`` that persisted as ``***...SD7U`` after the
        operator's GET → PUT round-trip.
        """
        client, key, db_path = client_and_key
        real_value = "real-bot-token-abc123"

        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Discord Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": real_value},
            },
        )
        account_id = create.json()["id"]

        got = await client.get(f"/api/connector-accounts/{account_id}")
        assert got.status_code == 200
        masked_payload = got.json()
        assert masked_payload["secrets"]["BOT_TOKEN"] == "***...c123"

        put = await client.put(f"/api/connector-accounts/{account_id}", json=masked_payload)
        assert put.status_code == 200

        got_again = await client.get(f"/api/connector-accounts/{account_id}")
        assert got_again.json()["secrets"]["BOT_TOKEN"] == "***...c123"

        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM connector_accounts WHERE id = ?",
                (account_id,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        decrypted = Fernet(key).decrypt(row["secrets"].encode()).decode()
        stored = json.loads(decrypted)
        assert stored == {"BOT_TOKEN": real_value}, (
            f"Round-trip corrupted the stored secret: got {stored!r}"
        )


# ── LLM provider round-trip ──────────────────────────────────────────────


class TestProviderRoundTrip:
    async def test_get_put_get_does_not_corrupt_api_key(self, client_and_key) -> None:
        """Provider ``api_key`` is the single-key analogue of the per-key
        secrets dict; same round-trip bug shape, same fix."""
        client, key, db_path = client_and_key
        real_value = "sk-realopenaikeyabcd1234"

        create = await client.post(
            "/api/providers",
            json={
                "name": "OAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": real_value,
            },
        )
        provider_id = create.json()["id"]

        got = await client.get(f"/api/providers/{provider_id}")
        assert got.status_code == 200
        masked_payload = got.json()
        assert masked_payload["api_key"] == "***...1234"

        put = await client.put(f"/api/providers/{provider_id}", json=masked_payload)
        assert put.status_code == 200

        got_again = await client.get(f"/api/providers/{provider_id}")
        assert got_again.json()["api_key"] == "***...1234"

        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?",
                (provider_id,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        decrypted = Fernet(key).decrypt(row["api_key"].encode()).decode()
        assert decrypted == real_value, (
            f"Round-trip corrupted the stored api_key: got {decrypted!r}"
        )


# ── Canonical __MASKED__ sentinel path (regression net) ──────────────────


class TestSentinelPathStillWorks:
    """Pin the original ``__MASKED__`` preserve-existing behavior. The fix
    widens the predicate from ``== _MASKED_API_KEY_SENTINEL`` to
    ``_looks_masked``; the sentinel branch MUST remain functional."""

    async def test_mcp_sentinel_preserves(self, client_and_key) -> None:
        client, key, db_path = client_and_key
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "S",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "ghp_realsecretvalue"},
            },
        )
        sid = create.json()["id"]
        await client.put(
            f"/api/mcp-sources/{sid}",
            json={
                "name": "S",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "__MASKED__"},
            },
        )
        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        decrypted = Fernet(key).decrypt(row["secrets"].encode()).decode()
        assert json.loads(decrypted) == {"K": "ghp_realsecretvalue"}

    async def test_connector_sentinel_preserves(self, client_and_key) -> None:
        client, key, db_path = client_and_key
        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "tok_realvalue"},
            },
        )
        account_id = create.json()["id"]
        await client.put(
            f"/api/connector-accounts/{account_id}",
            json={"secrets": {"BOT_TOKEN": "__MASKED__"}},
        )
        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM connector_accounts WHERE id = ?",
                (account_id,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        decrypted = Fernet(key).decrypt(row["secrets"].encode()).decode()
        assert json.loads(decrypted) == {"BOT_TOKEN": "tok_realvalue"}

    async def test_provider_sentinel_preserves(self, client_and_key) -> None:
        client, key, db_path = client_and_key
        create = await client.post(
            "/api/providers",
            json={
                "name": "OAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-realopenaikey9999",
            },
        )
        provider_id = create.json()["id"]
        await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "OAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "__MASKED__",
            },
        )
        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?",
                (provider_id,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        decrypted = Fernet(key).decrypt(row["api_key"].encode()).decode()
        assert decrypted == "sk-realopenaikey9999"


# ── Negative cases: not all leading-``***`` values are masks ─────────────


class TestNonMaskValuesPassThrough:
    """``_MASK_SHAPE_RE`` anchors and bounds the match. A legitimate
    user-supplied secret that merely starts with ``***`` (but isn't the
    exact mask shape) MUST overwrite the stored value normally — not be
    preserved as if it were the sentinel."""

    async def test_provider_starlit_prefix_is_real_value(self, client_and_key) -> None:
        client, key, db_path = client_and_key
        create = await client.post(
            "/api/providers",
            json={
                "name": "OAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-originalkey9999",
            },
        )
        provider_id = create.json()["id"]

        # ``***hello`` starts with ``***`` but is NOT a mask shape (no
        # ``...tail`` suffix AND has extra trailing chars). It must be
        # treated as a real, overwriting value.
        await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "OAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "***hello",
            },
        )
        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?",
                (provider_id,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        decrypted = Fernet(key).decrypt(row["api_key"].encode()).decode()
        assert decrypted == "***hello", (
            "Non-mask values starting with '***' must overwrite, not preserve."
        )

    async def test_connector_starlit_prefix_is_real_value(self, client_and_key) -> None:
        client, key, db_path = client_and_key
        create = await client.post(
            "/api/connector-accounts",
            json={
                "name": "Bot",
                "type": "stub",
                "secrets": {"BOT_TOKEN": "original-token"},
            },
        )
        account_id = create.json()["id"]

        # ``***...toolong`` — 7 chars after the dots, beyond the
        # ``{1,4}`` bound — must NOT match the mask shape and must
        # overwrite as a real value.
        await client.put(
            f"/api/connector-accounts/{account_id}",
            json={"secrets": {"BOT_TOKEN": "***...toolong"}},
        )
        direct_conn = await aiosqlite.connect(str(db_path))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM connector_accounts WHERE id = ?",
                (account_id,),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        decrypted = Fernet(key).decrypt(row["secrets"].encode()).decode()
        assert json.loads(decrypted) == {"BOT_TOKEN": "***...toolong"}


# ── Unit-level pin on the helper itself ──────────────────────────────────


class TestLooksMaskedHelper:
    """Pin the regex and the non-string short-circuit independently of the
    HTTP plumbing. Tests the exported helper directly so future refactors
    of the regex are caught at unit-test time, not via integration tests."""

    def test_sentinel(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked("__MASKED__") is True

    def test_bare_mask(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked("***") is True

    def test_mask_with_tail(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked("***...abcd") is True
        assert _looks_masked("***...a") is True  # 1-char tail still matches

    def test_mask_tail_too_long(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked("***...toolong") is False

    def test_starts_with_stars_but_not_mask(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked("***hello") is False
        assert _looks_masked("***-real-key") is False
        assert _looks_masked("****") is False  # 4 stars, no tail

    def test_non_string_values(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked(None) is False
        assert _looks_masked(42) is False
        assert _looks_masked({}) is False
        assert _looks_masked(True) is False

    def test_empty_string(self) -> None:
        from the_one.interfaces.web.api import _looks_masked

        assert _looks_masked("") is False


class TestMaskShapeSingleSourceOfTruth:
    """M11 F8 L3: pin the regex-emit pairing. If a maintainer drifts the
    emit shape from the recognize shape (e.g., by changing the prefix in
    one but not the other), these tests fail loud.

    See ``the_one/agents.md`` → ``single-source-of-truth-for-paired-helpers``.
    """

    def test_mask_shape_re_matches_emit_mask_output_for_short_string(self) -> None:
        from the_one.interfaces.web.api import _MASK_SHAPE_RE, _emit_mask

        masked = _emit_mask("ab")
        assert _MASK_SHAPE_RE.match(masked), f"Regex must match emit output {masked!r}"

    def test_mask_shape_re_matches_emit_mask_output_for_long_string(self) -> None:
        from the_one.interfaces.web.api import _MASK_SHAPE_RE, _emit_mask

        masked = _emit_mask("longersecret-token-123")
        assert _MASK_SHAPE_RE.match(masked), f"Regex must match emit output {masked!r}"
        # Tail of _MASK_TAIL_LEN (=4) chars: last 4 chars of the input string.
        assert masked.endswith("-123")

    def test_mask_shape_re_rejects_unrelated_user_input(self) -> None:
        from the_one.interfaces.web.api import _MASK_SHAPE_RE

        # Values that merely START with the prefix but aren't masks:
        assert not _MASK_SHAPE_RE.match("***hello")
        assert not _MASK_SHAPE_RE.match("abc")
        assert not _MASK_SHAPE_RE.match("")
        # Trailing content past the tail length:
        assert not _MASK_SHAPE_RE.match("***...too_long_tail")

    def test_mask_emitters_route_through_emit_mask(self) -> None:
        """Spot-check both wrapper functions produce identical output to
        _emit_mask for str inputs. Tightens the routing invariant — if a
        future refactor accidentally re-introduces a literal in one of
        the wrappers, this test catches it.
        """
        from the_one.interfaces.web.api import (
            _emit_mask,
            _mask_api_key,
            _mask_secret_value,
        )

        value = "supersecret-token-xyz789"
        assert _mask_secret_value(value) == _emit_mask(value)
        assert _mask_api_key(value) == _emit_mask(value)

    def test_rendered_regex_matches_pre_l3_literal(self) -> None:
        """Regression net: pin the rendered regex pattern byte-for-byte
        against the pre-L3 literal. Catches a future Python ``re.escape``
        semantic change for ASCII (very unlikely, but exactly the
        scenario this leg's "single source-of-truth" defends against).
        Also catches an accidental edit to ``_MASK_PREFIX`` /
        ``_MASK_TAIL_SEPARATOR`` / ``_MASK_TAIL_LEN`` that drifts the
        rendered pattern away from the established round-trip contract.
        """
        from the_one.interfaces.web.api import _MASK_SHAPE_RE

        assert _MASK_SHAPE_RE.pattern == r"^\*\*\*(\.\.\..{1,4})?$"
