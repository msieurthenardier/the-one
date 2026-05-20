# Leg: discord-plugin-foundation-and-type-registration

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Land the 8-layer connector-type extension checklist's layers 1-6 for `'discord'` plus the `DiscordPlugin` class skeleton + the `discord.py` SDK pin in a single atomic leg: narrow `ConnectorAccount.type` to `Literal["discord", "stub"]`, populate `CONNECTOR_TYPES = ("discord", "stub")`, register `'discord'` in `register_builtin_connectors()`, ship the v19 schema migration with `CHECK (type IN (...))` via the v6/v12 table-rename ceremony (CHECK set derived from `CONNECTOR_TYPES` via a new `_CONNECTOR_TYPES_SQL` projection mirroring `_PROVIDER_TYPES_SQL`), verify API gating is type-agnostic, add the Studio Discord badge token + CSS rule, and ship the `DiscordPlugin` skeleton that raises `NotImplementedError` from `connect` (L3 fills in). The leg is the foundation Discord-specific work depends on — nothing else in F8 can land before the type is registered.

## Context

This is L2 of F8. Per Design Decisions in `flight.md`:

- **"Layers 1-6 of the 8-layer connector-type extension checklist all land in F8 — primarily in L2"** — bundling layers 1, 2, 3, 4, 5, 6 into L2 keeps type registration atomic. A partial landing (e.g. Literal narrowed but registry empty) would break the system at first dispatch.
- **"Stub plugin stays test-only — NOT registered in any production code path"** — `register_builtin_connectors()` registers `'discord'` ONLY. Tests continue to use `register_for_test` for `'stub'`.
- **"v19 schema migration lands in L2 — `CHECK (type IN ('discord', 'stub'))` on `connector_accounts.type` via table-rename ceremony"** — CHECK set is derived from `CONNECTOR_TYPES` via a `_CONNECTOR_TYPES_SQL` projection mirroring `_PROVIDER_TYPES_SQL` at `db/schema.py:17`. `'stub'` is included per the M07 `'mock'`-in-`PROVIDER_TYPES` precedent (69 test sites construct `ConnectorAccount(type="stub")`; the `_stub.py:18-19` import-time invariant is the production-purity enforcer, not the CHECK).
- **"Discord SDK: `discord.py 2.4+`, pinned at flight start"** — M10 mission constraint "maintained SDKs with pinned versions"; the F1 `mcp==1.27.0` precedent at `pyproject.toml:24`.

Key learnings from prior flights / L1 (from the flight log):

- L1 codified `per-axis-tri-state-override` as a named project convention in `agents.md`; L8 will extend it with `guilds` + `roles` axes.
- L1 codified `hat-driven-contract-flip-migration-discipline` — L2's Literal-narrowing-with-`'stub'` semi-flip is a candidate application (the prior contract was "type: str unconstrained"; the new contract is "type: Literal[...]"). Both contracts are honored simultaneously here — existing `type="stub"` rows continue to validate.
- L1's `_routing.py` module docstring now carries the single-winner audit-log clarification; the v19 table-rename leaves session_metadata untouched so the routing-audit format is unaffected.

## Inputs

What exists before this leg runs:

- `the_one/db/_connector_types.py` exports `CONNECTOR_TYPES: tuple[str, ...] = ()` (empty tuple). Module docstring documents the three-layer agreement requirement and explicitly defers the v19 CHECK to Flight 8.
- `the_one/db/models.py:139` declares `ConnectorAccount.type: str` with a comment "narrows to Literal in flight 08 when CONNECTOR_TYPES is non-empty". Lines 110-117 carry the "intentionally NOT imported here yet" rationale.
- `the_one/db/schema.py:17` declares `_PROVIDER_TYPES_SQL = ", ".join(f"'{t}'" for t in PROVIDER_TYPES)`. No `_CONNECTOR_TYPES_SQL` equivalent yet.
- `the_one/db/schema.py:505-512` v13 migration creates `connector_accounts` with NO CHECK constraint on `type`. v14 (line 518+) added `name TEXT NOT NULL DEFAULT ''`; v15 added `idle_timeout_seconds INTEGER NULL`; v16 added `session_continuation_seconds INTEGER NULL`. By v18 the table has 9 columns: `id, type, config, secrets, created_at, updated_at, name, idle_timeout_seconds, session_continuation_seconds`. v18 (line 666+) added `agents.connector_acls` (a different table).
- `the_one/connectors/registry.py:147` declares `register_builtin_connectors()` with an empty body and a docstring naming `register("discord", DiscordPlugin)` as Flight 8's job (line 156).
- `the_one/connectors/base.py` exports `ConnectorPlugin` Protocol with 4 methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`). Structural satisfaction is the convention.
- `the_one/connectors/_stub.py:18-19` carries the invariant "Production code MUST NOT import this module." Tests register the stub via `register_for_test("stub", StubPlugin)`.
- `the_one/interfaces/web/api.py:2132-2134` exposes `GET /api/connector-accounts/types` returning `[{"value": t, "label": t.capitalize()} for t in registry.types()]`. The endpoint's existing docstring already anticipates F8 ("Returns an empty list in production until Flight 8 (Discord) lands the first real connector type").
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js:92` writes the class `admin-connector-badge--{type}` per-account row. No CSS rule for any specific type exists in `studio.css` or any other CSS file (verified — zero hits for `admin-connector-badge--`).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:461` carries a comment referencing `CONNECTOR_TYPES = ()` as the production state; it'll need a one-word update once Discord ships.
- `the_one/interfaces/web/static/css/tokens.css:147-157` defines provider-color tokens (`--badge-ollama`, `--badge-openai`, etc.). No `--badge-discord` yet.
- `the_one/interfaces/web/static/css/studio.css:911` contains a comment about `CONNECTOR_TYPES = ()` (the L1-codified `per-axis-tri-state-override` convention area).
- `pyproject.toml:6-25` lists base dependencies. `mcp==1.27.0` at line 24 is the precedent for SDK pinning. No `discord.py` entry.
- `tests/test_db_repositories.py:1015-1029` exercises `type="stub"` with Discord-themed values (`name="Discord Bot"`, `BOT_TOKEN`). This test passes today and continues to pass after L2 because `'stub'` is in `CONNECTOR_TYPES` and the v19 CHECK.
- F1-F7 + L1 test suite green on branch `flight/08-planning-discord` (2268 passed).

## Outputs

After this leg completes:

- `pyproject.toml` includes `discord.py>=2.4,<2.5` in `dependencies`.
- `the_one/db/_connector_types.py` exports `CONNECTOR_TYPES = ("discord", "stub")` with an updated docstring reflecting v19's landing.
- `the_one/db/models.py:139` declares `ConnectorAccount.type: Literal["discord", "stub"]`; lines 110-117 narrative replaced with the `assert set(get_args(...)) == set(CONNECTOR_TYPES)` pinning invariant alongside `LLMProviderConfig`'s assert at the top of the module.
- `the_one/db/schema.py:17` (in the existing TYPES_SQL block) adds `_CONNECTOR_TYPES_SQL = ", ".join(f"'{t}'" for t in CONNECTOR_TYPES)` immediately below `_PROVIDER_TYPES_SQL`.
- `the_one/db/schema.py` gains a `if version < 19:` block landing the table-rename ceremony with `CHECK (type IN ({_CONNECTOR_TYPES_SQL}))` on `connector_accounts.type`.
- `the_one/connectors/registry.py:147-167` `register_builtin_connectors()` body calls `register("discord", DiscordPlugin)` (imported from `the_one.connectors._discord`).
- `the_one/connectors/_discord.py` (NEW) ships `DiscordPlugin` class with the 4-method skeleton: `connect` raises `NotImplementedError("M10 F8 L3 lands the gateway client")`; `disconnect`, `doctor`, `normalize_session_key` are minimal stubs that either return safe defaults or raise `NotImplementedError` with the same M10-F8-L3-fills-in language. The class is structurally importable but unusable until L3.
- `the_one/interfaces/web/static/css/tokens.css` adds `--badge-discord: #5865F2;` (Discord brand "Blurple" — RGB 88, 101, 242) alongside the existing provider badge tokens.
- `the_one/interfaces/web/static/css/studio.css` adds `.area-studio .admin-connector-badge--discord { background: var(--badge-discord); }` (parallel to the existing `.area-admin .admin-provider-badge--*` rules in `admin.css:159-165`).
- `the_one/interfaces/web/api.py:2126-2130` docstring updated to reflect `'discord'` now ships in the production list.
- `the_one/agents.md:299-306` "Connector type extension checklist" entries 1, 2, 3, 4, 6 transition from forward-references to landed-feature citations.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:461` and `studio.css:911` comments updated from "until Flight 8" to "as of Flight 8 L2".
- `tests/test_db_repositories.py:1015-1029` passes unchanged (verification only — `'stub'` is valid post-L2).
- `tests/test_connector_types_consistency.py` (NEW) mirrors `tests/test_provider_types_consistency.py` shape: pins the three layers (Literal annotation, `CONNECTOR_TYPES` tuple, SQL CHECK set) against each other so a future contributor adding a new connector type can't drift one layer relative to another.
- F1-F7 + L1 test suite continues to pass; the v19 migration runs idempotently against an existing DB.

## Acceptance Criteria

- [ ] **`discord.py` SDK pin lands in `pyproject.toml`.** Add `"discord.py>=2.4,<2.5"` to the `dependencies` list at `pyproject.toml:6-25`. Place it alphabetically (between `cryptography` at line 23 and `mcp` at line 24 — or after `mcp` if alphabetical-by-import-name vs. alphabetical-by-package-name is in tension). Add a brief one-line comment above it citing the M10 mission constraint ("Wire-protocol clients use maintained SDKs with pinned versions") OR rely on the precedent comments below — implementer's call. **Post-add verification**: `docker exec the-one python -c 'import discord; print(discord.__version__)'` prints a 2.4.x version string. If the SDK is not yet installed in the existing dev container image, run `make rebuild` (or document the rebuild step in the leg log) before running tests.

- [ ] **Layer 2 — `CONNECTOR_TYPES` populated.** In `the_one/db/_connector_types.py:32`, change `CONNECTOR_TYPES: tuple[str, ...] = ()` to `CONNECTOR_TYPES: tuple[str, ...] = ("discord", "stub")`. Update the module docstring (lines 1-30):
  - Remove the "currently a no-op because the tuple is empty" paragraph at the end.
  - Add an explanation that `'stub'` belongs in `CONNECTOR_TYPES` per the M07 `'mock'`-in-`PROVIDER_TYPES` precedent: the production-purity invariant is enforced by `_stub.py:18-19`'s "Production code MUST NOT import" + `register_builtin_connectors` registering only `'discord'`. The CHECK accepting `'stub'` is harmless because nothing in production paths inserts a stub-typed row.
  - Cite the v19 landing as "v19 → F8 L2 (Discord). `CONNECTOR_TYPES` populated; CHECK constraint added via table-rename ceremony."

- [ ] **Layer 1 — `ConnectorAccount.type` narrowed to `Literal["discord", "stub"]`** at `the_one/db/models.py:139`. Replace the `type: str` declaration with `type: Literal["discord", "stub"]`. **Importantly**: spell the Literal explicitly (do NOT use `Literal[*CONNECTOR_TYPES]` — `LLMProviderConfig.type` at line 25 has the same constraint and is the precedent). The comment above the declaration at lines 110-117 is replaced with the canonical pattern from `LLMProviderConfig`:
  ```python
  from the_one.db._connector_types import CONNECTOR_TYPES  # (added near line 11)

  # ... (other module-level code, including the VALID_ROUTING_SCOPES constant) ...

  # Pin the explicit ``Literal`` arg-set to ``CONNECTOR_TYPES`` at import time so
  # the two cannot drift. See _connector_types.py for the canonical source.
  assert set(get_args(ConnectorAccount.model_fields["type"].annotation)) == set(CONNECTOR_TYPES), (
      "ConnectorAccount.type Literal drifted from CONNECTOR_TYPES — update both in lockstep."
  )
  ```
  The assert goes immediately after the `ConnectorAccount` class definition (mirroring the `LLMProviderConfig` assert at `models.py:56-61`).

- [ ] **`_CONNECTOR_TYPES_SQL` projection added immediately below `_PROVIDER_TYPES_SQL`** (next non-blank line after `schema.py:17`, with a one-line gap if the implementer prefers visual separation). Mirrors the provider precedent:
  ```python
  from the_one.db._connector_types import CONNECTOR_TYPES  # alongside line 9's PROVIDER_TYPES import

  # Build comma-separated quoted SQL literal list, sourced from
  # CONNECTOR_TYPES. The v19 CHECK constraint (added by F8 L2's
  # table-rename ceremony) references this; future connector types
  # added to the tuple flow automatically into the constraint via
  # the next CHECK-changing migration.
  _CONNECTOR_TYPES_SQL = ", ".join(f"'{t}'" for t in CONNECTOR_TYPES)
  ```

- [ ] **v13 forward-reference comment update** at `the_one/db/schema.py:485-490`. The existing v13 block comment says "flight 8 (Discord) will land v19 with the table-rename ceremony to add the CHECK once 'discord' is a real type." Update the comment to read as historical context after the fact: "v19 (F8 L2 — landed) added the CHECK via table-rename ceremony per the table-rebuild precedent used in v3/v6 for `llm_providers`. v13 deliberately deferred the CHECK because `CONNECTOR_TYPES` was empty at v13 landing; the v3/v6 precedent (CHECK in CREATE TABLE from day one + later extension via rebuild) doesn't apply because there was nothing to constrain initially."

- [ ] **Layer 4 — v19 schema migration with CHECK constraint** added to `the_one/db/schema.py` after the existing v18 block at line ~695. Pattern follows v6 (line 230+) and v12 / v13 table rebuilds. The migration:
  1. `PRAGMA foreign_keys=OFF;`
  2. `CREATE TABLE connector_accounts_new` with all 9 existing columns AND the new CHECK: `type TEXT NOT NULL CHECK (type IN ({_CONNECTOR_TYPES_SQL}))`. Preserve every column type and DEFAULT verbatim from the v13/v14/v15/v16 incrementally-evolved shape:
     - `id TEXT PRIMARY KEY`
     - `type TEXT NOT NULL CHECK (type IN ({_CONNECTOR_TYPES_SQL}))`
     - `config TEXT DEFAULT '{}'`
     - `secrets TEXT DEFAULT '{}'`
     - `created_at TEXT NOT NULL DEFAULT (datetime('now'))`
     - `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`
     - `name TEXT NOT NULL DEFAULT ''`
     - `idle_timeout_seconds INTEGER NULL`
     - `session_continuation_seconds INTEGER NULL`
  3. `INSERT INTO connector_accounts_new SELECT id, type, config, secrets, created_at, updated_at, name, idle_timeout_seconds, session_continuation_seconds FROM connector_accounts;`
  4. `DROP TABLE connector_accounts;`
  5. `ALTER TABLE connector_accounts_new RENAME TO connector_accounts;`
  6. `PRAGMA foreign_keys=ON;`
  7. `INSERT OR IGNORE INTO schema_version (version) VALUES (19);`
  
  Migration block carries a comment citing: the v6/v12 table-rename precedent; `agents.md:302` layer-4 commitment; the M07 `'mock'`-in-CHECK precedent; the `_stub.py:18-19` production-purity invariant the CHECK does NOT enforce. **Idempotency**: the block guards with `if version < 19:`; partial-apply tolerance follows the v3/v6 pattern (`PRAGMA foreign_keys=OFF` outside the transaction is automatic since SQLite executescript opens its own).

- [ ] **Layer 3 — `register_builtin_connectors()` body** at `the_one/connectors/registry.py:147-167`. Replace the empty body with:
  ```python
  from the_one.connectors._discord import DiscordPlugin  # function-local import to avoid module-level cycle at registry import time

  register("discord", DiscordPlugin)
  ```
  Use a **function-local import** to avoid a load-cycle if `_discord` ever needs to import from `registry` (the precedent is `agents.md`'s `function-local-import-to-break-load-cycle` convention; the F1-shipped registry.py module-level docstring already anticipates this). Update the docstring at lines 156+ to drop the "Flight 8" forward-reference language and reflect the landed registration.

- [ ] **`DiscordPlugin` skeleton ships at `the_one/connectors/_discord.py`** (NEW). Module structure:
  - Module docstring cites M10 F8 L2 as the source; cross-references the SDK pin in `pyproject.toml` and the v19 CHECK constraint.
  - Imports: `from the_one.connectors.base import ConnectorPlugin, ConnectorClient, InboundEnvelope, OutboundTarget, SessionKey, DoctorReport, SendResult` + `from the_one.db.models import ConnectorAccount` + `from the_one.security import Encryptor` (NOT inheriting from any Protocols — structural satisfaction).
  - `class DiscordPlugin:` — **stateless, no `__init__`**, mirroring `StubPlugin` at `_stub.py:72+`. The F1 construction contract is `cls()` (zero-arg) at `registry.py:76`; account + encryptor are passed to `connect(account, encryptor)` by `_pool.py:440-`. L3 must place per-connection state on the returned `ConnectorClient`, NOT on the plugin instance.
  - Method stubs matching the F1 Protocol surface verbatim (signatures verified against `StubPlugin.connect/disconnect/doctor/normalize_session_key` at `_stub.py:165-`):
    - `async def connect(self, account: ConnectorAccount, encryptor: Encryptor) -> ConnectorClient:` raises `NotImplementedError("M10 F8 L3 lands the Discord gateway client and reconnect schedule")`.
    - `async def disconnect(self, client: ConnectorClient) -> None:` raises `NotImplementedError("M10 F8 L3 lands the disconnect path")`.
    - `async def doctor(self, account: ConnectorAccount, encryptor: Encryptor) -> DoctorReport:` raises `NotImplementedError("M10 F8 L7 lands the Discord doctor probe")`. (Confirm the exact signature against `StubPlugin.doctor` at design time — match it verbatim including async-vs-sync.)
    - `def normalize_session_key(self, envelope: InboundEnvelope) -> SessionKey:` raises `NotImplementedError("M10 F8 L4 lands the Discord inbound envelope normalization")`. (Confirm sync-vs-async against `StubPlugin.normalize_session_key` at design time.)
  - **Structural Protocol satisfaction**: `isinstance(DiscordPlugin(), ConnectorPlugin)` must return `True` — the 4 method names are present on a zero-arg instance.
  - Module convention: `__all__ = ("DiscordPlugin",)`.
  - No SDK imports yet — the file imports `discord` only inside method bodies that will be filled in by L3-L7. This keeps the module loadable at `register_builtin_connectors()` time even if `discord.py` were missing (defensive — though the pin guarantees it's present).

- [ ] **Layer 5 — API gating verification.** Confirm `/api/connector-accounts/*` routes in `the_one/interfaces/web/api.py` need NO Discord-specific gating:
  - `create_connector_account`, `update_connector_account`, `delete_connector_account`, `get_connector_account`, `list_connector_accounts` — all should be type-agnostic (the Pydantic Literal narrowing at the model edge handles type validation; the v19 CHECK handles DB-edge validation; no `if type == "discord":` branches needed).
  - `list_connector_account_types` (at `api.py:2120-2134`) docstring update: drop "Returns an empty list in production until Flight 8 (Discord) lands the first real connector type" and replace with "Returns the registered types from `register_builtin_connectors`; F8 L2 added `'discord'`."
  - `test_connector_account` (if it exists, mirroring `test_provider`): verify type-agnostic OR introduce Discord-specific test-probe gating per implementer's design call.
  - **Documentation deliverable**: leg-log entry confirms the routes are type-agnostic; if any aren't, the leg's diff updates them and the implementer documents the deviation in the flight log.

- [ ] **Layer 6 — Studio frontend Discord badge token + CSS rule.**
  - `the_one/interfaces/web/static/css/tokens.css` adds `--badge-discord: #5865F2;` immediately after the existing `--badge-unknown` (line 157) within the same `--badge-*` token block. The hex value is Discord's documented brand color "Blurple."
  - `the_one/interfaces/web/static/css/studio.css` adds a Connector Type Badges section (mirroring `admin.css:158-165`):
    ```css
    /* === Connector Type Badges === */
    .area-studio .admin-connector-badge--discord { background: var(--badge-discord); }
    .area-studio .admin-connector-badge--unknown { background: var(--badge-unknown); }
    ```
    Place the new section near studio.css line 911 (where the F8-`CONNECTOR_TYPES = ()` comment lives) — or wherever the existing studio.css badge-related rules cluster.
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:461` comment updated: drop "until Flight 8 lands Discord" language.
  - `the_one/interfaces/web/static/css/studio.css:911` comment updated similarly: drop the "until F8 ships Discord" forward-reference.

- [ ] **`agents.md:299-306` connector-type extension checklist transitions from forward-references to citations.** Per-layer:
  - Layer 1: "Flight 8 narrows to `Literal["discord"]`" → "F8 L2 narrowed to `Literal["discord", "stub"]` (`'stub'` included per M07 precedent)."
  - Layer 2: "Empty tuple in Flight 1" → "F8 L2 populated to `("discord", "stub")`."
  - Layer 3: "Empty body in Flight 1" → "F8 L2 registers `register("discord", DiscordPlugin)`."
  - Layer 4: "Flight 8's v19 migration" → "v19 (F8 L2) added `CHECK (type IN ('discord', 'stub'))` via table-rename ceremony."
  - Layer 6: "Flight 8 supplies the Discord-specific assets" → "F8 L2 shipped the `--badge-discord` token + `.admin-connector-badge--discord` rule."

- [ ] **`tests/test_connector_types_consistency.py` ships (NEW).** Mirror `tests/test_provider_types_consistency.py` structurally. Three pinning tests:
  1. **Literal-vs-tuple agreement**: `set(get_args(ConnectorAccount.model_fields["type"].annotation)) == set(CONNECTOR_TYPES)`. Mirrors the `LLMProviderConfig.type` test.
  2. **Registry-vs-tuple agreement** (tight, drift-catching): `set(_connector_types_in_registry()) == set(CONNECTOR_TYPES) - {"stub"}`. Exact equality minus the one literal stub exception. This catches the most likely drift — adding `"slack"` to `CONNECTOR_TYPES` without registering it — which a subset check would silently pass. The `"stub"` carve-out is by literal name, documented inline as "the one test-only type per the M07 `'mock'` precedent." Future test-only types would need to extend this exception list explicitly.
  3. **CHECK-vs-tuple agreement**: read `connector_accounts` table SQL from `PRAGMA table_info` or the migration source; parse the CHECK literal list; assert it matches `CONNECTOR_TYPES`. Mirrors the provider precedent.
  Each test docstring cites M10 F8 L2 + the layer it pins.

- [ ] **F1-F7 + L1 regression**: `docker exec the-one pytest tests/ -x --timeout 30` passes — count goes from 2268 to ~2271 (adds 3 consistency tests in the new file). No regression in pre-L2 paths. Specifically run the migration-relevant test files alone first: `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py -x --timeout 30`.

- [ ] **Migration idempotency**: Re-running `ensure_schema` against an already-v19 DB is a no-op (`if version < 19:` short-circuits). Test: spin up a fresh DB, run migrations, check `_get_version` returns 19; re-run `ensure_schema`, assert version still 19 and `connector_accounts` schema unchanged.

## Verification Steps

- `grep -n 'CHECK (type IN' the_one/db/schema.py` — at least one new hit for the v19 `connector_accounts` block.
- `grep -c "DiscordPlugin" the_one/connectors/_discord.py` — at least 1 (the class declaration).
- `grep -c "register(\"discord\", DiscordPlugin)" the_one/connectors/registry.py` — exactly 1.
- `docker exec the-one python -c "from the_one.db._connector_types import CONNECTOR_TYPES; assert CONNECTOR_TYPES == ('discord', 'stub'), CONNECTOR_TYPES; print('OK')"` — prints OK.
- `docker exec the-one python -c "from the_one.db.models import ConnectorAccount; from typing import get_args; print(set(get_args(ConnectorAccount.model_fields['type'].annotation)))"` — prints `{'discord', 'stub'}`.
- `docker exec the-one python -c "from the_one.connectors.registry import types as t; print(sorted(t()))"` — prints `['discord']` (production registry; stub not registered).
- `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_connector_types_consistency.py -x --timeout 30` — all pass; the consistency file has at least 3 new tests.
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes.
- Fresh-DB migration test: drop the SQLite file (or use an in-memory DB), run `ensure_schema`, query `PRAGMA table_info(connector_accounts)`, confirm the CHECK constraint is present via reading SQL from `sqlite_master`.

## Implementation Guidance

Order surfaces by dependency — `pyproject.toml` first (rebuild may be needed), then the Python contract (tuple → Literal → registry → migration → plugin skeleton → consistency tests), then the frontend assets, then docs.

1. **`pyproject.toml` SDK pin**. Add `discord.py>=2.4,<2.5` to `dependencies`. Run `make rebuild` if the SDK isn't in the dev image yet. Verify with `docker exec the-one python -c 'import discord; print(discord.__version__)'`.

2. **Layer 2 — `_connector_types.py`**. Populate the tuple + update the docstring. This is the canonical source of truth; subsequent layers reference it.

3. **`_CONNECTOR_TYPES_SQL` projection in `schema.py`**. Add the projection immediately below `_PROVIDER_TYPES_SQL`. This is consumed by the v19 migration block in step 5.

4. **Layer 1 — `ConnectorAccount.type` Literal narrowing**. Replace `type: str` with `type: Literal["discord", "stub"]`; add the pinning assert. Run `docker exec the-one pytest tests/test_db_repositories.py -x --timeout 30` to confirm 69 stub-typed test sites still pass.

5. **Layer 4 — v19 migration block in `schema.py`**. Add the `if version < 19:` block. Test by running migrations against a fresh DB AND an existing v18 DB; confirm both end at version 19 with the CHECK constraint live. Use `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30`.

6. **Layer 3 — `register_builtin_connectors()`** in `registry.py`. Use function-local import for `DiscordPlugin` to avoid load cycles. Run `docker exec the-one python -c "from the_one.connectors.registry import types; print(list(types()))"` — should print `['discord']`.

7. **`DiscordPlugin` skeleton in `_discord.py`**. Build the 4-method class. Verify `isinstance(plugin, ConnectorPlugin)` returns `True` against an instance.

8. **Consistency tests in `tests/test_connector_types_consistency.py`**. Mirror the provider file. Pin the three layers against each other.

9. **Layer 6 — frontend assets**. Add the badge token + CSS rule + comment updates in JS/CSS. No browser test in this leg (L10 covers the routing-rules editor; future legs may add Studio Connector Account tests).

10. **Layer 5 — API gating verification + docstring update**. Read all `/api/connector-accounts/*` route handlers in `api.py`; confirm none branch on type; update the `list_connector_account_types` docstring.

11. **`agents.md` connector-type extension checklist update**. Transition the 6 entries from forward-references to citations.

12. **Full-suite green** (validation). Run `docker exec the-one pytest tests/ -x --timeout 30`. Update `flight-log.md` with the leg progress entry.

### Code patterns to follow

- **`LLMProviderConfig.type` precedent at `db/models.py:25`** — pattern for the Literal narrowing + pinning assert. Mirror exactly.
- **`_PROVIDER_TYPES_SQL` projection at `db/schema.py:17`** — pattern for the new `_CONNECTOR_TYPES_SQL`. Mirror exactly.
- **v6/v12 table-rename ceremony** — pattern for the v19 migration. `PRAGMA foreign_keys=OFF` → `CREATE TABLE _new` → `INSERT ... SELECT` → `DROP` → `ALTER ... RENAME` → `PRAGMA foreign_keys=ON`. Wrap in `executescript` to keep transactional.
- **`function-local-import-to-break-load-cycle` convention** — `register_builtin_connectors` should `from the_one.connectors._discord import DiscordPlugin` inside the function body, not at module top, to defer the dependency on `_discord` until after `registry` itself has fully loaded.
- **`structural-Protocol-satisfaction` convention** — `DiscordPlugin` does NOT inherit from `ConnectorPlugin`; it satisfies the Protocol structurally via method names.
- **`tests/test_provider_types_consistency.py`** — pattern for the new connector-types consistency test file. Mirror the test class structure.

## Edge Cases

- **Existing v13-v18 DBs with rows that have invalid types** (e.g. seeded data from a hand-edited DB): the v19 migration's `INSERT INTO _new SELECT *` would fail the CHECK if any existing row has `type NOT IN ('discord', 'stub')`. Mitigation: this is the desired behavior — bad data should fail loudly at migration time. Document in the leg log; F8 has no existing prod data (the operator's the-one instances are dev only, all rows are stub-typed).
- **Fresh-DB path**: the v13 CREATE TABLE at `schema.py:505-512` STILL has no CHECK constraint. A fresh DB runs through all migrations, so v19 will table-rename the v13-created table with the CHECK applied. This is correct but means the v13 → v19 path involves creating-then-rebuilding the table on first init. Acceptable (matches the v3 llm_providers → v6 CHECK-extension precedent).
- **`DiscordPlugin.__init__` — DON'T add one** (cycle-1 review correction): F1's `registry.py:76` calls `plugin = cls()` (zero-arg). `StubPlugin` at `_stub.py:72+` has NO `__init__` — stateless. The original L2 design proposed `__init__(self, account, encryptor)`; that would fail at first dispatch with `TypeError: missing 2 required positional arguments`. The corrected design above mirrors the StubPlugin shape: stateless plugin; `connect(self, account, encryptor)` receives the inputs at call time; L3 stashes per-connection state on the returned `ConnectorClient` instance, NOT on the plugin instance.
- **Backward compatibility for old test fixtures using positional construction**: `ConnectorAccount(id, name, type, config, secrets, ...)` positional construction still works under the Literal narrowing — Pydantic accepts `"stub"` and `"discord"` as valid values; rejects anything else (which is the desired tightening).
- **Migration partial-apply**: if the system crashes mid-v19 migration (between `INSERT ... SELECT` and `DROP TABLE`), the next run sees version still at 18 and `connector_accounts_new` left over. The `IF NOT EXISTS` on the migration block protects against this — actually NO, the v19 block uses `executescript` which doesn't carry `IF NOT EXISTS` for CREATE TABLE. Mitigation: the SQLite executescript transactional semantics roll back on failure; either the whole v19 lands or none of it does. Test by deliberately injecting a constraint violation mid-migration (e.g. a row with `type='invalid'`) and confirming version stays at 18.
- **`is_dm` hook hot-path**: not yet wired in L2; L6 implements. `DiscordPlugin` does NOT declare `is_dm` in L2 — that's L6's surface (`getattr` sentinel; the consult site at `_acl.py:95, 171` already exists from F7).

- **JS connector-types cache freshness**: `studio.js:290, 725, 792-797` carries a module-scope `CONNECTOR_TYPES` variable populated by the `/api/connector-accounts/types` fetch on Studio-area mount. Operators with Studio already mounted at the time the migration runs will continue to see the empty list until they refresh / re-navigate. Acceptable for L2 (a registry change is dev-time, not hot-reloadable). Documented here so reviewers don't read the staleness as a bug.

## Files Affected

- `pyproject.toml` — add `discord.py>=2.4,<2.5` to dependencies
- `the_one/db/_connector_types.py` — populate tuple + docstring update
- `the_one/db/models.py` — `ConnectorAccount.type` Literal narrowing + pinning assert + imports
- `the_one/db/schema.py` — `_CONNECTOR_TYPES_SQL` projection + v19 migration block
- `the_one/connectors/registry.py` — `register_builtin_connectors()` body + docstring
- `the_one/connectors/_discord.py` (NEW) — `DiscordPlugin` skeleton with 4-method shape
- `the_one/interfaces/web/api.py` — `list_connector_account_types` docstring + verification of type-agnostic routes
- `the_one/interfaces/web/static/css/tokens.css` — `--badge-discord` token
- `the_one/interfaces/web/static/css/studio.css` — `.admin-connector-badge--discord` rule + comment update
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — comment update
- `the_one/agents.md` — connector-type extension checklist transition to citations
- `tests/test_connector_types_consistency.py` (NEW) — three consistency tests

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`docker exec the-one pytest tests/ -x --timeout 30`)
- [ ] Migration tested against a fresh DB (verify CHECK is live) AND an existing v18 DB (verify upgrade)
- [ ] Update flight-log.md with leg progress entry (Changes Made + Test Results)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit — wait for flight-level review per `/agentic-workflow`

## Citation Audit

Citations verified against current code at leg-design time:

- `db/models.py:139` — `ConnectorAccount.type: str` declaration — **OK** (verified line 139)
- `db/models.py:110-117` — "intentionally NOT imported here yet" comment — **OK** (verified lines 110-117)
- `db/models.py:25` — `LLMProviderConfig.type` Literal precedent — **OK** (verified line 25)
- `db/models.py:56-61` — `LLMProviderConfig` pinning assert precedent — **OK** (verified lines 56-61)
- `db/_connector_types.py:32` — `CONNECTOR_TYPES = ()` — **OK** (verified)
- `db/schema.py:17` — `_PROVIDER_TYPES_SQL` projection — **OK** (verified)
- `db/schema.py:505-512` — v13 connector_accounts CREATE TABLE — **OK** (verified, no CHECK)
- `db/schema.py:518-542` — v14 `name` ALTER — **OK** (verified shape)
- `db/schema.py:544+` — v15 `idle_timeout_seconds` ALTER — **OK** (verified pattern)
- `db/schema.py:618-624` — v16 `session_continuation_seconds` ALTER on connector_accounts — **OK** (verified)
- `db/schema.py:666-695` — v18 ALTER on agents (NOT connector_accounts) — **OK** (verified — last existing block)
- `db/schema.py:230+` — v6 table-rename precedent — **OK** (verified pattern)
- `connectors/registry.py:147-167` — `register_builtin_connectors` empty body — **OK** (verified)
- `connectors/_stub.py:18-19` — "MUST NOT import" invariant — **OK** (verified)
- `interfaces/web/api.py:2120-2134` — `list_connector_account_types` endpoint — **OK** (verified)
- `interfaces/web/static/css/tokens.css:147-157` — provider badge tokens — **OK** (verified)
- `interfaces/web/static/css/admin.css:158-165` — provider badge CSS rule precedent — **OK** (verified)
- `interfaces/web/static/css/studio.css:911` — F8 forward-reference comment — **OK** (verified)
- `interfaces/web/static/js/areas/studio/connector-account-editor.js:461` — F8 forward-reference comment — **OK** (verified)
- `interfaces/web/static/js/areas/studio/connector-accounts-grid.js:92` — badge class write site — **OK** (verified)
- `pyproject.toml:6-25` — dependencies list with `mcp==1.27.0` precedent — **OK** (verified)
- `tests/test_db_repositories.py:1015-1029` — existing stub-typed round-trip test — **OK** (verified — uses type="stub", will continue passing)
- `agents.md:299-306` — 8-layer extension checklist — **OK** (verified)

23 citations verified against current code at leg design time.
