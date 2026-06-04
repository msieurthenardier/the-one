"""Pin the three connector-type representations to one source of truth.

Mirrors :mod:`tests.test_provider_types_consistency` exactly in role. The
valid ``Connector.type`` values live in three layers that must
agree (per the connector-type 6-layer extension checklist in
``agents.md``):

1. The Pydantic ``Literal`` annotation on
   :attr:`the_one.db.models.Connector.type` (layer 1).
2. The :data:`the_one.db._connector_types.CONNECTOR_TYPES` tuple (layer 2).
3. The runtime registry (layer 3) — production registers ``"discord"``
   only; ``"stub"`` is the test-only carve-out per the M07 ``'mock'``-in-
   ``PROVIDER_TYPES`` precedent.
4. The SQLite CHECK constraint on ``connectors.type`` baked by
   the v19 table-rename ceremony (layer 4).

If any of these asserts fail, fix the drift in
``the_one/db/_connector_types.py`` and the re-derivation in the offending
site — do NOT edit a single site to make the test pass; re-derive from
``CONNECTOR_TYPES``.

Lands in M10 F8 L2 alongside the v19 migration. Adding a new connector
type in a future flight requires touching all four layers in the same
leg — these tests catch the most likely drift (e.g. adding ``"slack"`` to
``CONNECTOR_TYPES`` without registering it).
"""

from __future__ import annotations

import re
from typing import get_args

import aiosqlite
import pytest

from the_one.connectors.registry import (
    clear_for_test,
    restore_to_baseline_for_test,
)
from the_one.connectors.registry import (
    types as _registry_types,
)
from the_one.db._connector_types import CONNECTOR_TYPES
from the_one.db.models import Connector
from the_one.db.schema import ensure_schema


def test_connector_types_tuple_has_expected_members() -> None:
    """Pin the canonical set so a typo in ``_connector_types.py`` is caught
    here rather than as a confusing downstream failure.

    Layer 2 of the connector-type 6-layer checklist (``agents.md``). M10
    F8 L2 populated the tuple to ``("discord", "stub")``.
    """
    assert set(CONNECTOR_TYPES) == {"discord", "stub"}


def test_pydantic_literal_matches_connector_types() -> None:
    """The ``Literal[...]`` arg-set on ``Connector.type`` must equal
    ``CONNECTOR_TYPES``. (The model's import-time assertion already enforces
    this; the explicit test is for visibility in the suite output.)

    Layer 1 of the connector-type 6-layer checklist (``agents.md``). M10
    F8 L2 narrowed the annotation from ``str`` to ``Literal["discord",
    "stub"]``.
    """
    annotation = Connector.model_fields["type"].annotation
    assert set(get_args(annotation)) == set(CONNECTOR_TYPES)


def test_registry_baseline_matches_connector_types_minus_stub() -> None:
    """The production registry must register exactly
    ``CONNECTOR_TYPES - {"stub"}``.

    The ``'stub'`` carve-out is by literal name — it's the one test-only
    connector type per the M07 ``'mock'``-in-``PROVIDER_TYPES`` precedent.
    Tests register it explicitly via :func:`register_for_test`. Future
    test-only types would need to extend this exception list explicitly;
    the tight equality (rather than a subset check) catches the most
    likely drift — adding ``"slack"`` to ``CONNECTOR_TYPES`` without
    registering it.

    Layer 3 of the connector-type 6-layer checklist (``agents.md``). M10
    F8 L2 added the ``register("discord", DiscordPlugin)`` call in
    :func:`register_builtin_connectors`.
    """
    # Restore the singleton to its post-:func:`register_builtin_connectors`
    # baseline in case prior tests in the session left ``"stub"`` (or any
    # other test-registered type) lingering. ``clear_for_test`` + replay
    # rather than rely on whatever order pytest happened to pick.
    clear_for_test()
    restore_to_baseline_for_test()
    assert set(_registry_types()) == set(CONNECTOR_TYPES) - {"stub"}


@pytest.mark.asyncio
async def test_sqlite_check_constraint_matches_connector_types(tmp_path) -> None:
    """Open a fresh DB, introspect the live ``connectors`` CHECK
    constraint, and assert the literal values in it match
    ``CONNECTOR_TYPES``.

    Layer 4 of the connector-type 6-layer checklist (``agents.md``). M10
    F8 L2's v19 migration added the CHECK via the v6/v12 table-rename
    ceremony; M11 F11 L1's v23 migration renamed the table to
    ``connectors`` and carried the CHECK forward verbatim. Mirrors
    :func:`tests.test_provider_types_consistency.test_sqlite_check_constraint_matches_provider_types`.
    """
    db_path = tmp_path / "schema-check.db"
    conn = await aiosqlite.connect(str(db_path))
    try:
        conn.row_factory = aiosqlite.Row
        await ensure_schema(conn)
        async with conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='connectors'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None, "connectors table missing after ensure_schema()"
        sql = row["sql"]
        assert "CHECK" in sql, f"CHECK constraint missing from connectors DDL: {sql}"

        # Strip everything outside the ``type IN (...)`` clause and pull the
        # quoted-literal members back out as a set.
        match = re.search(r"type\s+IN\s*\(([^)]*)\)", sql, re.IGNORECASE)
        assert match is not None, f"Could not locate 'type IN (...)' in DDL: {sql}"
        literals = re.findall(r"'([^']*)'", match.group(1))
        assert set(literals) == set(CONNECTOR_TYPES), (
            f"SQLite CHECK constraint drifted from CONNECTOR_TYPES: "
            f"{set(literals)} vs {set(CONNECTOR_TYPES)}"
        )
    finally:
        await conn.close()
