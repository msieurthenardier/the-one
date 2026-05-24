"""Single source of truth for the connector type enum.

Mirrors the_one/db/_provider_types.py exactly in role: three layers must
agree on the valid values, and the tuple below is the canonical list each
re-derives its representation from.

- The Pydantic ``Literal`` annotation on ``ConnectorAccount.type`` (compile-time
  type checking, JSON-schema generation, request validation at the API edge)
  — landed in the models-and-repository leg of flight 1; narrowed to
  ``Literal["discord", "stub"]`` by M10 F8 L2 once ``CONNECTOR_TYPES`` was
  populated.
- The SQLite CHECK constraint string baked into the ``connector_accounts``
  table (runtime DB-level rejection of bogus rows) — added in **v19 → F8 L2
  (Discord)** via the table-rename ceremony established by v6/v12. The
  ``_CONNECTOR_TYPES_SQL`` projection at ``db/schema.py`` (immediately below
  ``_PROVIDER_TYPES_SQL``) re-derives the SQL literal list from the tuple
  below so a future connector type added here flows automatically into the
  next CHECK-changing migration. v14 → ``name`` column on
  ``connector_accounts`` (F1 L2); v15 → ``idle_timeout_seconds`` (F2 L2);
  v16 → chat_sessions external-key columns + ``session_continuation_seconds``
  on ``connector_accounts`` (F3 L1); v17 → ``agents.connector_account_ids``
  persistence (F4 L5); v18 → ``agents.connector_acls`` persistence (F6 L1c);
  v19 → ``CHECK (type IN ('discord', 'stub'))`` on ``connector_accounts.type``
  (F8 L2).
- The connector-type → registry-class map in ``the_one/connectors/registry.py``
  (runtime dispatch from a stored account config to a ConnectorPlugin) —
  landed in the registry leg of flight 1. The production registry registers
  ``"discord"`` only (F8 L2 extended ``register_builtin_connectors``); the
  ``"stub"`` entry is test-only — see the note below.

``'stub'`` belongs in ``CONNECTOR_TYPES`` per the M07 ``'mock'``-in-
``PROVIDER_TYPES`` precedent. 69+ test sites construct
``ConnectorAccount(type="stub")`` and persist it; the v19 CHECK accepting
``'stub'`` keeps those round-trips green at the DB layer. The production-
purity invariant — "no production code path ever inserts a stub-typed
row" — is enforced by two separate guards:

1. ``the_one/connectors/_stub.py:18-19`` declares "Production code MUST NOT
   import this module"; the import-time invariant trips loudly if a
   production module ever reaches for the stub.
2. ``register_builtin_connectors`` registers ``"discord"`` only; tests that
   need the stub call ``register_for_test("stub", StubPlugin)`` explicitly.

The CHECK accepting ``'stub'`` is therefore harmless: nothing in production
paths inserts a stub-typed row, so the constraint never sees one in a
production DB.

The consistency tests at ``tests/test_connector_types_consistency.py`` pin
the three layers to this tuple — Literal-vs-tuple, registry-vs-tuple (with
the literal ``'stub'`` carve-out for the test-only type), and CHECK-vs-tuple.
"""

from __future__ import annotations

CONNECTOR_TYPES: tuple[str, ...] = ("discord", "stub")
