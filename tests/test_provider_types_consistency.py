"""Pin the three provider-type representations to one source of truth.

The 7 valid ``LLMProviderConfig.type`` values live in three places that
must agree. This file is the cross-layer contract test. If any of these
asserts fail, fix the drift in ``the_one/db/_provider_types.py`` and the
re-derivation in the offending site (do NOT edit a single site to make
the test pass — re-derive from ``PROVIDER_TYPES``).
"""

from __future__ import annotations

from typing import get_args

import aiosqlite
import pytest

from the_one.db._provider_types import PROVIDER_TYPES
from the_one.db.models import LLMProviderConfig
from the_one.db.schema import ensure_schema
from the_one.llm.registry import PROVIDER_TYPE_MAP


def test_provider_types_tuple_has_expected_members() -> None:
    """Pin the canonical set so a typo in ``_provider_types.py`` is caught here
    rather than as a confusing downstream failure."""
    assert set(PROVIDER_TYPES) == {
        "ollama",
        "openai-compatible",
        "openai",
        "anthropic",
        "mock",
        "openrouter",
        "anthropic-plan",
    }


def test_pydantic_literal_matches_provider_types() -> None:
    """The ``Literal[...]`` arg-set on ``LLMProviderConfig.type`` must equal
    ``PROVIDER_TYPES``. (The model's import-time assertion already enforces
    this; the explicit test is for visibility in the suite output.)"""
    annotation = LLMProviderConfig.model_fields["type"].annotation
    assert set(get_args(annotation)) == set(PROVIDER_TYPES)


def test_provider_type_map_keys_match_provider_types() -> None:
    """The dispatch map (lifted to ``the_one.llm.registry`` in M19 F01 L02;
    consumed by the agent factory, connector inference, and the provider API
    branches) must dispatch every declared provider type to a registry name."""
    assert set(PROVIDER_TYPE_MAP.keys()) == set(PROVIDER_TYPES)


@pytest.mark.asyncio
async def test_sqlite_check_constraint_matches_provider_types(tmp_path) -> None:
    """Open a fresh DB, introspect the live ``llm_providers`` CHECK constraint,
    and assert the literal values in it match ``PROVIDER_TYPES``."""
    db_path = tmp_path / "schema-check.db"
    conn = await aiosqlite.connect(str(db_path))
    try:
        conn.row_factory = aiosqlite.Row
        await ensure_schema(conn)
        async with conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='llm_providers'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None, "llm_providers table missing after ensure_schema()"
        sql = row["sql"]
        assert "CHECK" in sql, f"CHECK constraint missing from llm_providers DDL: {sql}"

        # Strip everything outside the ``type IN (...)`` clause and pull the
        # quoted-literal members back out as a set.
        import re

        match = re.search(r"type\s+IN\s*\(([^)]*)\)", sql, re.IGNORECASE)
        assert match is not None, f"Could not locate 'type IN (...)' in DDL: {sql}"
        literals = re.findall(r"'([^']*)'", match.group(1))
        assert set(literals) == set(PROVIDER_TYPES), (
            f"SQLite CHECK constraint drifted from PROVIDER_TYPES: "
            f"{set(literals)} vs {set(PROVIDER_TYPES)}"
        )
    finally:
        await conn.close()
