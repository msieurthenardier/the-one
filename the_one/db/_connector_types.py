"""Single source of truth for the connector type enum.

Mirrors the_one/db/_provider_types.py exactly in role: three layers must
agree on the valid values, and the tuple below is the canonical list each
re-derives its representation from.

- The Pydantic ``Literal`` annotation on ``ConnectorAccount.type`` (compile-time
  type checking, JSON-schema generation, request validation at the API edge)
  — landed in the models-and-repository leg of flight 1.
- The SQLite CHECK constraint string baked into the ``connector_accounts``
  table (runtime DB-level rejection of bogus rows) — **deferred to flight 8**
  which adds the CHECK via a v19 table-rename ceremony when there is a real
  type to constrain (v14 → ``name`` column on ``connector_accounts`` (F1 L2);
  v15 → ``idle_timeout_seconds`` (F2 L2); v16 → chat_sessions external-key
  columns + ``session_continuation_seconds`` on ``connector_accounts`` (F3 L1);
  v17 → ``agents.connector_account_ids`` persistence (F4 L5);
  v18 → ``agents.connector_acls`` persistence (F6 L1c);
  v19 is Flight 8's CHECK constraint via the table-rename ceremony established
  by v6/v12).
  Until then ``connector_accounts.type`` is unconstrained at the DB level;
  the Pydantic ``Literal`` is the sole guard at the API edge.
- The connector-type → registry-class map in ``the_one/connectors/registry.py``
  (runtime dispatch from a stored account config to a ConnectorPlugin) —
  landed in the registry leg of flight 1.

The consistency tests pin the three layers to this tuple — currently a no-op
because the tuple is empty.
"""

from __future__ import annotations

CONNECTOR_TYPES: tuple[str, ...] = ()
