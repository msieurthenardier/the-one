# Flight Log: Connector Plugin Contract and Lifecycle Foundation

**Flight**: [Connector Plugin Contract and Lifecycle Foundation](flight.md)

## Summary

_(populated during execution)_

---

## Reconnaissance Report

Pre-flight reconnaissance against the cited locations in the mission's Flight 1 description and the architect's first/second review of the mission spec.

| Source item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `mcp/_pool.py` worker-task-per-entry pattern | confirmed-live | `_RegistryEntry` L67-98; `_entry_worker` L148-248; `_pool` L102; `acquire` L431-517; `shutdown_drain` L387-428 | Mirror the pattern in `connectors/_pool.py`; do not share code (see flight Design Decisions) |
| `mcp/_pool.py` `_shutting_down` flag test-isolation debt | confirmed-live | Module-level `_shutting_down: bool = False` at L104; `_clear_for_test` resets at L561 but cross-test leakage observed under shared event loop | Connector pool fixes from the start; M07 debt remains deferred per Design Decisions |
| Encryption rotation single-pass transaction | confirmed-live | `interfaces/web/api.py:2770-2840` — single atomic commit covers LLM providers + MCP sources; try/except/rollback wrapper at L2819-2833 | Extend the same commit to cover `connector_accounts.secrets` in the schema-and-migration leg |
| `db/schema.py` v8/v9/v10 migration pattern | confirmed-live | Pattern at L300-430; v10 migration L363-410 shows the table-rename ceremony with `INSERT OR IGNORE INTO schema_version` last; `CURRENT_VERSION = 12` at L11 | Flight 1 introduces v13; follow v10 pattern exactly |
| Pydantic source-type config pattern | confirmed-live | `MCPSource` at `db/models.py:86-108`; `type: Literal[...]` + `config: dict[str, Any]` + `secrets: dict[str, Any]`; `merged_config()` at L97-107 | `ConnectorAccount` mirrors this shape exactly |
| Source repository pattern | confirmed-live | `MCPSourceRepository` at `db/repositories.py:291-425`; `__init__(conn, encryptor)`; encryptor is a reference (not copy) for rotation propagation; `_secrets_to_ciphertext` / `_ciphertext_to_secrets`; `_row_to_model` | `ConnectorAccountRepository` mirrors this exactly |
| MCP four-typed-exceptions contract | confirmed-live | `mcp/errors.py` defines 10 typed exceptions across a base hierarchy; held without erosion across 11 M07 flights (M07 debrief L62) | Mirror with 5 connector-type exceptions initially; grow deliberately |
| `agents.md` provider-type six-layer checklist | confirmed-live | `agents.md` L251-267 enumerates Pydantic Literal, `_PROVIDER_TYPE_MAP`, registry loaders, SQLite CHECK constraint, API gating, frontend tokens, optional `_init_provider_state` hook | Flight 1 adds the connector-type checklist parallel to this |
| `tools/builtins.py` enable/disable pattern (for Flight 4 reference) | confirmed-live | Built-in tools enable/disable surface at `tools/resolver.py` + `tools/builtins.py` | Out of Flight 1 scope; cited as the pattern Flight 4 inherits |
| M07 in-process test-stub strategy | confirmed-live | M07 tests use mock at the `ClientSession` level (no subprocess fixture); test seam is dependency injection per the `mock` LLM provider pattern | Stub plugin at `connectors/_stub.py` is in-process; no env-var test-mode seam |

**Conclusion**: All cited locations confirmed live; no drift. The mission's Flight 1 description was written against the current code shape. Design Decisions are grounded in real code paths. Proceed to leg planning.

---

## Leg Progress

_(append entries as legs complete)_

---

## Decisions

_(append runtime decisions not captured in the flight spec)_

---

## Deviations

_(append departures from the planned approach)_

---

## Anomalies

_(append unexpected issues encountered)_

---

## Session Notes

_(chronological notes during execution)_
