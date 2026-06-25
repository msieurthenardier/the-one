# Leg: search-config-persistence

**Status**: completed
**Flight**: [Agent-loop Resource Governance & Context-budget Management](../flight.md)

## Objective
Give built-in tool configs **encrypted secret storage at rest** — a generic
`config`(plaintext) + `secrets`(encrypted) split on `ToolConfigRepository`, mirroring the
`MCPSource`/`Connector` pattern and driven by the `secret:true` schema markers leg 2 added
— so `web_search`'s keyed-engine API keys (Brave/Google/Tavily) encrypt on disk, are
masked over the API, are preserved on masked re-save, and are decrypted back into the
resolved config so the backends still receive the real keys. No new UI (keys settable via
API/config here; the admin form is leg `search-config-admin-ui`).

## Context
- **Flight pivot / DD3 refinement**: keyed search engines need API keys; leg 2 put them on
  `WebSearchConfig` as plain `str` fields MARKED `secret:true` but stored PLAINTEXT in the
  tool-config `config` JSON. This leg makes them encrypted at rest. The flight batch-commits
  at the end, so no plaintext-key release ever ships.
- **Generic, not web_search-specific**: the split is driven by each Config's `secret:true`
  field markers, so ANY future built-in tool with a secret field gets encrypted storage +
  masking for free. `web_search` is just the first consumer.
- **Codebase facts (verified — Explore):**
  - `ToolConfigRepository` (`db/repositories.py:830-912`): table `tool_configs`
    (`name` PK, `config TEXT DEFAULT '{}'`, `enabled`, timestamps). **No encryptor, no
    secrets column.** `upsert(name, config, enabled)` (`:866`), `get` (`:859`), `list`
    (`:843`), `list_all()` resolver-facing `{name: config_dict}` (`:849`), `_row_to_model`
    (`:904`).
  - **Pattern to copy**: shared helpers `_encrypt_secrets_blob`/`_decrypt_secrets_blob`
    (`repositories.py:35-65`) — Fernet JSON blob; `_decrypt_secrets_blob` tolerates
    `InvalidToken` (plaintext `'{}'` migration-residue) → `{}`. `MCPSourceRepository`
    (`:402-517`) and `ConnectorRepository` (`:541-625`): encryptor by reference in
    `__init__`; `_secrets_to_ciphertext`/`_ciphertext_to_secrets` delegators; encrypt on
    write, decrypt on read.
  - **Schema/migrations**: versioned, `CURRENT_VERSION = 31` (`db/schema.py:15`);
    `ensure_schema()` applies up to current; idempotent ADD COLUMN guarded by
    `PRAGMA table_info`. `tool_configs` created in v8 (`schema.py:331-337`); the
    **mcp_sources `secrets` column (v10, `schema.py:374-421`)** is the exact precedent
    (`ADD COLUMN secrets TEXT DEFAULT '{}'`).
  - **Encryptor wiring**: `get_encryptor(settings.data_dir)` (`encryption.py:86-108`).
    Repo factories thread it (MCP `api.py:81`, Connector `:87`, Provider `:3785`). **The
    tool-config factory `_tool_config_repo()` (`api.py:114-116`) does NOT** — it constructs
    `ToolConfigRepository(conn)` with no encryptor.
  - **Masking primitives** (`api.py:722-823`): `_mask_secret_value` (`:746`), the
    `__MASKED__` sentinel (`:785`), `_looks_masked` (`:800`, matches the sentinel + the
    `***`/`***...tail4` visual masks). Provider PUT preserves on masked (`:3956-3972`); MCP
    `_mask_secrets`/`_mcp_source_response` (`:840-864`). Reuse all of these.
  - **Tool-config API handlers**: GET `/tools/configs/{name}` (`api.py:212-236`) returns
    `config` plaintext; PUT (`:240-300`) validates against `cls.Config`, `model_dump()`s,
    `repo.upsert(name, new_config, enabled=…)`. Neither masks nor preserves secrets today.
  - **Resolver path (CORRECTED — design review)**: `builtins.get_tools` resolves each tool
    via `resolve(cls.Config, tool_configs.get(name), …)` (`builtins.py:191`), but the
    `tool_configs` feed is built in **`factory.py:292-294`** from `repo.list()` →
    `{c.name: c.config}` — NOT `list_all()` (which has NO production caller). So the real
    fix is `ToolConfig.merged_config()` consumed at `factory.py:294`, plus threading the
    encryptor into the factory's repo construction.

## Inputs
- `db/schema.py` (`CURRENT_VERSION=31`, v8 tool_configs, v10 mcp_sources-secrets precedent).
- `db/repositories.py` (`ToolConfigRepository`, shared secret helpers, MCP/Connector
  patterns).
- `db/models.py` `ToolConfig` row model (add a `secrets` field — check MCPSource model for
  the shape).
- `interfaces/web/api.py` (`_tool_config_repo`, tool GET/PUT, masking primitives).
- `tools/_web_search_config.py` `WebSearchConfig` + `WEB_SEARCH_SECRET_FIELDS` (leg 2) — the
  first config carrying `secret:true` fields.

## Outputs
- Migration **v32**: `tool_configs.secrets TEXT DEFAULT '{}'`; `CURRENT_VERSION=32`.
- `ToolConfigRepository` gains an `encryptor`; secrets read/write via the shared helpers;
  `upsert(name, config, secrets=None, enabled=True)` (secrets a DEFAULTED kwarg so existing
  callers are unaffected); `get`/`list`/`_row_to_model` return decrypted secrets.
- `ToolConfig` model gains `secrets: dict[str, Any]` (default `{}`) **and a
  `merged_config()` method** (`{**config, **secrets}`) mirroring `MCPSource.merged_config()`
  (`models.py:98-108`).
- **`factory.py` rewired** (HIGH — the real resolver feed): the tool-config feed at
  `factory.py:292-294` is built from `repo.list()` → `{c.name: c.config}` and passed to
  `get_tools`; `list_all()` has NO production caller. Change it to
  `{c.name: c.merged_config()}` so `build_search_backend` (via `builtins.py:191` `resolve`)
  receives the REAL keys. The factory's `ToolConfigRepository(conn)` construction
  (`factory.py:292`) must also thread the encryptor (it now decrypts on read).
- `_tool_config_repo()` threads `get_encryptor(settings.data_dir)`.
- A generic `_secret_field_names(config_cls) -> set[str]` reading `secret:true` from the
  model's `json_schema_extra`.
- Tool GET masks secret-marked values (`_mask_secret_value`); PUT splits secrets out of the
  validated config, preserves existing on `_looks_masked`, persists config + encrypted
  secrets.
- Round-trip / migration / masking / resolver-merge tests; updated repo-construction
  fixtures.

## Acceptance Criteria
- [x] Migration **v32** adds `secrets TEXT DEFAULT '{}'` to `tool_configs`, idempotent
      (`PRAGMA table_info` guard, mirroring v10 mcp_sources); `CURRENT_VERSION` → 32;
      `ensure_schema()` applies it; a pre-existing row with the plaintext `'{}'` default
      decrypts to `{}` (InvalidToken tolerance), and the next write re-encrypts.
- [x] `ToolConfigRepository.__init__(conn, encryptor)` holds the encryptor BY REFERENCE;
      `_secrets_to_ciphertext`/`_ciphertext_to_secrets` delegate to the shared helpers;
      `upsert(name, config, secrets=None, enabled=True)` (secrets DEFAULTED — all current
      `upsert(name, config[, enabled=…])` callers keep working) encrypts `secrets` on
      write; `get`/`list`/`_row_to_model` decrypt on read.
- [x] **`ToolConfig.merged_config()` returns `{**config, **secrets}`** and the FACTORY feed
      (`factory.py:294`) uses it (`{c.name: c.merged_config()}`) so the resolver/
      `build_search_backend` receives the real api_key/base_url (NOT the mask). A test
      asserts a saved `web_search` `brave_api_key` reaches the backend THROUGH THE FACTORY
      path (`test_factory_feeds_real_secret_to_search_backend` — drives `AgentFactory.create()`
      with the real `BuiltinToolProvider`, NOT a direct `list_all()` call).
- [x] `ToolConfig` row model carries `secrets: dict[str, Any] = {}`.
- [x] BOTH production constructions thread the encryptor: `_tool_config_repo()`
      (`api.py:114`) AND `factory.py:292` use `get_encryptor(settings.data_dir)`; every
      test/fixture construction (`tests/test_db_repositories.py`, `test_factory*`,
      `test_connectors_e2e_platform_send.py`, `test_factory_disable_enforcement.py`)
      updated to pass an `Encryptor` (the `mcp_repo_encryptor` fixture shape).
- [x] `_secret_field_names(config_cls)` returns the set of field names whose
      `json_schema_extra` has `secret: true` (generic; works for any tool Config). Parity
      asserted against `WEB_SEARCH_SECRET_FIELDS`.
- [x] GET `/tools/configs/{name}` returns `config` with each secret-marked value MASKED via
      `_mask_secret_value` (decrypted then masked — never raw); non-secret fields unchanged;
      schema unchanged.
- [x] PUT `/tools/configs/{name}` validates the full body against `cls.Config`, then SPLITS
      secret-marked fields into the `secrets` dict and the rest into `config` — **secret-
      marked keys are ABSENT from the persisted `config` column** (asserted), so no
      plaintext key ever lands in `config`. For any incoming secret value that
      `_looks_masked`, PRESERVE the existing decrypted secret; a masked value with no
      existing secret is dropped (cleared), not stored as the mask string. A real new value
      replaces it.
- [x] Tools with NO secret fields behave exactly as before (`secrets={}` blob;
      backward-compatible). Other built-in tools' configs are unaffected.
- [x] No secret appears in any API response except masked; no secret is logged.
- [x] FULL unit suite (`make test-unit`) green: **3565 passed, 10 skipped, 0 failed**
      (above the leg-2 baseline of 3550); the migration runs cleanly on a fresh DB AND an
      existing one (`TestSchemaV32`).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_repositories.py -x --timeout 30`
  (or the repo-test file) — round-trip encrypt/decrypt, InvalidToken tolerance, list_all merge.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_schema*.py -x --timeout 30`
  — v32 migration idempotency + version, fresh + existing DB.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_api_tool_configs.py -x --timeout 30`
  — GET masks secrets, PUT preserves-on-masked / replaces-on-real, split correctness.
- A resolver/builtins test: a saved `web_search` config with `brave_api_key` set →
  `build_search_backend` (or the resolved `WebSearchConfig`) sees the REAL key, not the mask.
- `make test-unit` once at leg-end.

## Implementation Guidance
1. **Migration v32** (`db/schema.py`). Add an `if version < 32:` block: `PRAGMA
   table_info(tool_configs)` → add `secrets TEXT DEFAULT '{}'` if absent; insert the
   version marker; commit. Bump `CURRENT_VERSION = 32`. Copy the v10 mcp_sources block shape.
2. **`ToolConfig` model** (`db/models.py:684`). Add `secrets: dict[str, Any] = Field(
   default_factory=dict)` AND a `merged_config()` method returning `{**self.config,
   **self.secrets}` — copy `MCPSource.merged_config()` (`models.py:98-108`); secrets shadow
   same-named config keys (web_search keys don't collide, but document the order).
3. **`ToolConfigRepository`** (`db/repositories.py:830`). Add `encryptor: Encryptor` to
   `__init__`; add the two delegators (copy MCP's `:405-417`). `upsert(name, config,
   secrets=None, enabled=True)` with `secrets = secrets or {}` — DEFAULTED kwarg so the
   existing `api.py:294` / test callers (`upsert("shell", {}, enabled=False)` etc.) keep
   working; write `self._secrets_to_ciphertext(secrets)` into the `secrets` column (extend
   the INSERT OR REPLACE column list). `get`/`list`/`_row_to_model` — decrypt the `secrets`
   column into `ToolConfig.secrets`. Leave `list_all()` as-is (no production caller); the
   resolver merge happens via `merged_config()` in the factory (step 4b).
4. **Encryptor wiring — TWO production sites.**
   (a) `_tool_config_repo()` (`api.py:114`) → `ToolConfigRepository(conn,
   get_encryptor(settings.data_dir))`.
   (b) `factory.py:292` also constructs `ToolConfigRepository(conn)` — thread the encryptor
   there too (it now decrypts on read), AND change the feed at `factory.py:294` from
   `{c.name: c.config}` to `{c.name: c.merged_config()}` so the resolver gets real keys.
   Then grep every remaining `ToolConfigRepository(` (test fixtures) and pass an
   `Encryptor` (use the `mcp_repo_encryptor` fixture shape, `tests/test_db_repositories.py:60`).
5. **`_secret_field_names(config_cls)` helper** (`api.py` near the masking primitives).
   `{n for n, fi in config_cls.model_fields.items() if (fi.json_schema_extra or {}).get(
   "secret") is True}` — NULL-GUARD `json_schema_extra` (it's `None` on unmarked fields).
   Add a parity assert against `WEB_SEARCH_SECRET_FIELDS` (`_web_search_config.py:130`).
6. **GET handler** (`api.py:212`). After loading `config` (now config+secrets merged from
   the repo, or fetch both), build the response `config` = non-secret fields verbatim +
   secret fields run through `_mask_secret_value`. Use `_secret_field_names(cls.Config)`.
7. **PUT handler** (`api.py:240`). Validate the full incoming `config` against `cls.Config`
   (unchanged). Then split `validated.model_dump()` by `_secret_field_names`: secret keys
   move INTO `new_secrets` and are **removed from `new_config`** (so the `config` column
   never holds a plaintext key); the rest stay in `new_config`. For each secret field whose
   incoming value `_looks_masked`, replace it in `new_secrets` with the existing decrypted
   value from `repo.get(name)` (reuse the MCP/connector per-key resolution at
   `api.py:1229`/`:2605`); a masked value with no existing secret is dropped. `repo.upsert(
   name, new_config, secrets=new_secrets, enabled=…)`. Return the masked response (reuse the
   GET masking).
8. **No-secret tools**: `_secret_field_names` returns ∅ → `new_secrets={}` → identical
   behavior to today. Verify an existing tool config test still passes unchanged.

## Edge Cases
- **Masked value on PUT with no existing secret** (operator pastes the mask shape into a
  blank field): `_looks_masked` true but no stored secret → store empty (treat as cleared);
  do not persist the mask string. Document.
- **Key rotation**: encryptor held by reference, so `install_key()` propagates — same
  guarantee as MCP/Connector. No extra work; note it.
- **`list_all()` precedence**: a secret field name colliding with a config field name —
  secrets win (they're the authoritative store for that field). Web search fields don't
  collide, but document the merge order.
- **Resolver sees real key, GET shows mask**: two different reads — the resolver uses the
  factory feed `merged_config()` (real key), the admin GET uses the masking path. Keep them
  distinct; a test asserts the FACTORY/backend path is NOT masked.
- **Fresh DB**: v32 runs in-sequence on a brand-new DB (column present from the ADD COLUMN);
  the `'{}'` default decrypts to `{}` via InvalidToken tolerance on first read.

## Files Affected
- `the_one/db/schema.py` — migration v32; `CURRENT_VERSION` 31→32.
- `the_one/db/repositories.py` — `ToolConfigRepository` encryptor + secrets column +
  defaulted-`secrets` upsert.
- `the_one/db/models.py` — `ToolConfig.secrets` + `merged_config()`.
- `the_one/agent/factory.py` (`:292-294`) — encryptor on the repo + feed via
  `merged_config()` (the real resolver wiring).
- `the_one/interfaces/web/api.py` — `_tool_config_repo` encryptor; `_secret_field_names`;
  GET mask; PUT split (secret keys removed from `config`) + preserve-on-masked.
- `tests/test_db_repositories.py` — round-trip, InvalidToken, `tool_config_repo` fixture
  gains an encryptor; update `upsert` call sites if needed.
- `tests/test_schema.py` / `tests/test_db_migration.py` — v32 column-presence (no hardcoded
  31 to change; version asserts are symbolic).
- `tests/test_api_tool_configs.py` — GET mask, PUT preserve/replace, secret-keys-absent-
  from-config split.
- `tests/test_factory*.py`, `tests/test_connectors_e2e_platform_send.py` — `ToolConfigRepository`
  construction sites gain an encryptor; add a factory→backend real-key test.
- Docs: note tool-config secrets are encrypted at rest (parity with MCP/provider keys).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (full unit suite, 3565 passed); migration verified on fresh + existing DB
- [x] Update flight-log.md (migration version, the split mechanism, resolver-merge, that the
      UI half remains in leg `search-config-admin-ui`)
- [x] Set this leg's status to `landed` (commit deferred to flight end)
- [x] Check off this leg in flight.md
- [x] (Not the final leg — do not land the flight here)
