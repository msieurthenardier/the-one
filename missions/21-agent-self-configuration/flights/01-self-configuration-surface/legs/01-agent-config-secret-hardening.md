# Leg: agent-config-secret-hardening

**Status**: completed
**Flight**: [Self-Configuration Surface](../flight.md)

## Objective

Bring `AgentConfig.tool_overrides` and `mcp_overrides` into line with every
other secrets-bearing record in the platform: Fernet-encrypted at rest, their
credential keys masked on every agent read path, preserved server-side across
PUT, and included in key rotation — closing Mission Known Issue 1 and mission
criterion 2 before any read projection is built over the store.

## Context

- **DD5** (flight): encrypt the override columns at rest *and* mask on read,
  with preserve-on-PUT resolved server-side against the stored row, because
  Studio rebuilds `mcp_overrides` from the DOM and renders no credential fields
  (`the_one/interfaces/web/static/js/areas/studio.js:collectFormData`, ~2064–2132;
  `mcps-tab.js` header comment: "Per-agent credential overrides … are NOT
  rendered in this UI"). A credential set via the API is already wiped by the
  next Studio save today.
- **Three corrections to DD5, found during leg design** (recorded in the flight
  log under Decisions):
  - **C1 — a production rotation path exists.** DD5 says `Encryptor.rotate_key`
    has no production caller. True, but misleading: `POST /api/encryption/rotate`
    (`the_one/interfaces/web/api.py:rotate_encryption_key`) re-encrypts four
    corpora inline — `llm_providers.api_key`, `llm_providers.secrets`,
    `mcp_sources.secrets`, `connectors.secrets` — in one transaction, then
    replaces the key file. An encrypted agent column that is *not* in that
    transaction is orphaned the first time the operator rotates. The agents
    columns join the rotation in this leg, non-negotiably.
  - **C2 — `_decrypt_secrets_blob` would erase legacy rows.** DD5 says the
    helper "falls back to treating undecryptable input as plaintext". It does
    not: on `InvalidToken` it returns `{}` (`the_one/db/repositories.py:_decrypt_secrets_blob`
    — "Treat as empty secrets"). That is correct for a column whose default is
    `'{}'`, and destructive for the agents columns, whose legacy plaintext is
    real operator data like `{"shell": {"timeout": 30}}`. This leg adds its own
    decode that parses legacy plaintext on `InvalidToken` instead of discarding
    it.
  - **C3 — the concrete list of unsafe-to-serialize keys is three, all in
    `mcp_overrides`.** The mission asked for an enumerated list rather than a
    policy. The credential-bearing keys are the `Substitute`-marked fields of the
    two override schemas in `the_one/mcp/_overrides.py`: `env`
    (`StdioMCPOverride`), `headers` and `bearer_token`
    (`StreamableHttpMCPOverride`). `enabled_tools` / `disabled_tools` in the same
    dicts are not secrets and **are** round-tripped by Studio's MCPs tab — they
    must stay in the clear. `tool_overrides` holds **no** credential today: the
    only `Substitute`-marked built-in tool field is `WebConfig.default_user_agent`
    (`the_one/tools/_web_config.py`), which is not secret, and Studio's Tools tab
    reads `agent.tool_overrides` values back into its form
    (`tools-tab.js:376 — "var agentOverride = ((agent && agent.tool_overrides) || {})[name] || {}"`).
    So: **both columns are encrypted at rest** (parity, and so a future
    `Substitute` credential on a tool Config is covered without a second
    migration of habit), but **only the three `mcp_overrides` keys are masked**.
- Precedent to copy, not reinvent: `MCPSourceRepository` holds the encryptor
  **by reference** so `install_key()` after rotation propagates
  (`repositories.py:405-407`); `_mcp_source_response` overwrites `secrets` with
  `_mask_secrets(...)` after `model_dump()` and the regression net is an
  assertion on response *text* (`api.py:_mcp_source_response` docstring;
  `tests/test_db_api.py::test_list_returns_masked_secrets`); the PUT handler
  resolves `_looks_masked` values per key from the stored row
  (`api.py:update_mcp_source`, ~1290–1322).
- Prior-leg learnings: none — first leg of the flight. Working tree is clean on
  branch `flight/01-self-configuration-surface`.

## Inputs

- `the_one/db/repositories.py:SQLiteAgentStore` — `__init__(self, conn)` takes no
  encryptor; `save()` writes `json.dumps(config.tool_overrides)` /
  `json.dumps(config.mcp_overrides)` (or `None`) straight into the columns;
  `_row_to_config` is a `@staticmethod` that `json.loads` them back.
  Constructed at 7 production sites (`connectors/_pool.py:578`,
  `connectors/_inbound.py:328`, `interfaces/cli.py:31`, `interfaces/web/app.py:140`
  and `:1283`, `retention.py:58`, `interfaces/web/api.py:_agent_store`) and ~30
  test sites, all as `SQLiteAgentStore(conn)`.
- `the_one/db/schema.py` — `agents.tool_overrides` (v8) and `agents.mcp_overrides`
  (v11) are nullable `TEXT` columns added by `ALTER TABLE`. No DDL change is
  needed: Fernet ciphertext is text, and NULL semantics are unchanged.
- `the_one/interfaces/web/api.py` — every agent-config response is a bare
  `cfg.model_dump()` (`list_agents`, `get_agent`, `create_agent`,
  `update_agent`, `detach_agent_from_connector` (~627), and `rename_agent`
  (~678) — six sites in total under `# ── Agents` (:436–680); the implementer
  must grep `model_dump()` in that section and route **every** agent-config
  return through the new helper. Line ~723 is `update_knowledge_base` and is
  **not** an agent endpoint).
  `_mask_secret_value`, `_mask_secrets`, `_looks_masked`, `_MASKED_API_KEY_SENTINEL`
  exist and are reused unchanged.
- `the_one/interfaces/web/api.py:rotate_encryption_key` — four SELECT/decrypt
  passes, one `try:` block of UPDATE loops, one `commit()`, then key-file
  replace and `encryptor.install_key(new_key)`.
- `the_one/mcp/_overrides.py` — `StdioMCPOverride`, `StreamableHttpMCPOverride`,
  both with `Annotated[T | None, Substitute]` credential fields.
- Test fixtures: `tests/test_db_api.py::client` patches
  `the_one.interfaces.web.api.get_encryptor` with a function-scoped test
  `Encryptor` and yields the raw key for direct-DB decrypt assertions;
  `tests/test_db_repositories.py::agent_store` is `SQLiteAgentStore(conn)`;
  `tests/conftest.py` isolates `THE_ONE_DATA_DIR` to a temp dir for the whole
  run, so a default-resolved `get_encryptor(settings.data_dir)` never touches the
  operator's key file under test.

## Outputs

- `SQLiteAgentStore` accepts an optional `Encryptor` (defaulted), holds it by
  reference, encrypts both override columns on `save()`, and decodes
  ciphertext **or** legacy plaintext on load. `_row_to_config` becomes an
  instance method.
- A single source of truth for the masked key set, derived from the
  `Substitute` markers on the override schemas — not a hand-typed list in
  `api.py`.
- One `_agent_response(cfg)` helper in `api.py` that every agent-config return
  goes through, masking the three credential keys per source.
- Server-side credential preserve in `update_agent`.
- Agents columns included in `rotate_encryption_key`'s single transaction.
- Tests pinning each of the above, including a response-text regression net.
- Docs: `the_one/agents.md` (rotation invariant ×2, new "Agent override secrets
  storage" section), `SECURITY-MODEL.md` Secrets, the `rotate_encryption_key`
  docstring, and a one-line `CLAUDE.md` watch-out beside the existing
  `__MASKED__` note.

## Acceptance Criteria

- [x] **AC1 — ciphertext at rest.** After `SQLiteAgentStore.save()` of a config
      with non-`None` `tool_overrides` and `mcp_overrides`, a raw
      `SELECT tool_overrides, mcp_overrides FROM agents` returns values that are
      not valid JSON and that decrypt under the store's encryptor to the
      original dicts. `None` is stored as SQL NULL and loads as `None`; `{}` is
      stored encrypted and loads as `{}` (the None/`{}` distinction the existing
      round-trip tests pin is preserved).
- [x] **AC2 — legacy plaintext survives.** A row whose column holds plaintext
      JSON (inserted directly, as pre-leg databases have it) loads with its
      values intact, and the next `save()` rewrites that column as ciphertext.
      A column holding plaintext that is not valid JSON raises (corruption is
      not masked), matching `_decrypt_secrets_blob`'s stance.
- [x] **AC3 — masked on every read path.** With an agent whose `mcp_overrides`
      carry `bearer_token`, `headers`, and `env` values, the response bodies of
      `GET /api/agents`, `GET /api/agents/{name}`, `POST /api/agents`,
      `PUT /api/agents/{name}`, `POST /api/agents/{name}/rename`, and
      `DELETE /api/agents/{agent_name}/connectors/{account_id}` (and any other
      endpoint returning an agent config) contain none of the plaintext values
      — asserted as `secret not in resp.text` per endpoint, the
      `test_list_returns_masked_secrets` pattern. `bearer_token` renders in
      `_mask_secret_value` shape; `headers` and `env` render as dicts whose
      *values* are masked and whose keys are intact.
- [x] **AC4 — non-secrets stay clear.** In the same responses,
      `mcp_overrides[<source>].enabled_tools` / `.disabled_tools` and every
      `tool_overrides` value are returned unmasked and byte-identical to what
      was stored.
- [x] **AC5 — preserve-on-PUT, per credential key.** For each `(source_name,
      credential_key)` in the stored row: an incoming payload that **omits** the
      key (or the whole source entry, or sends `mcp_overrides: null`) preserves
      the stored value; an incoming value for which `_looks_masked` is true
      preserves it (for `headers`/`env`, resolved per inner key against the
      stored inner dict); an incoming explicit `null` clears it; any other value
      overwrites it. A masked value for a key with nothing stored is dropped,
      never persisted as the mask string. Verified by loading through the store
      (plaintext) after the PUT, not by re-GETting a masked view.
- [x] **AC6 — rotation covers the agents columns.** After
      `POST /api/encryption/rotate`, `store.load()` returns the same overrides,
      the raw columns decrypt under the new key and not the old, legacy
      plaintext rows are normalised to ciphertext, NULL columns stay NULL, and a
      failure injected into the agents UPDATE loop rolls back every other
      surface (the existing atomicity contract now spans five corpora).
- [x] **AC7 — no constructor ripple.** `SQLiteAgentStore(conn)` with no
      encryptor still works at every existing site; `api.py:_agent_store()`
      passes `get_encryptor(settings.data_dir)` explicitly so the api-module
      patch in tests governs it.
- [x] **AC8 — suites green.** `make test-unit` passes; `ruff check` and
      `ruff format --check` on `the_one/ tests/` are clean.
- [x] **AC9 — documentation.** `the_one/agents.md` "Encryption rotation
      invariant" and "Encryption-rotation invariant (three corpora)" name the
      agents columns as a rotated corpus; a new "Agent override secrets storage"
      section sits beside "Tool config secrets storage"; `SECURITY-MODEL.md`
      Secrets lists per-agent MCP override credentials; the
      `rotate_encryption_key` docstring counts five surfaces; `CLAUDE.md` gains
      a one-line watch-out that agent PUTs preserve stored MCP credential
      overrides server-side.

## Verification Steps

- AC1, AC2: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_repositories.py -x --timeout 30`
  — new tests read the raw column via the fixture's `conn`, assert
  `json.loads` fails on it and `encryptor.decrypt` succeeds; a legacy test
  inserts plaintext with `INSERT INTO agents (name, tool_overrides, mcp_overrides)`
  and loads.
- AC3, AC4, AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_api.py tests/test_agent_tool_overrides_round_trip.py -x --timeout 30`
  — one test per endpoint for the text regression net; a preserve matrix test
  parametrised over {omitted, masked, null, new value} × {bearer_token, headers,
  env}; a Studio-shaped PUT test (payload carries only `enabled_tools`) and a
  `mcp_overrides: null` PUT test, both loading via a `SQLiteAgentStore` built on
  the fixture `conn` with the fixture encryptor.
- AC6: extend `tests/test_provider_api.py::TestEncryptionRotation` (the
  established rotation suite — `test_rotate_key`,
  `test_rotate_dual_surface_atomicity_on_db_failure`,
  `test_rotate_with_migration_residue_mcp_row` are the patterns to mirror) with
  an agent carrying overrides; assert old-key decrypt raises `InvalidToken` and
  new-key decrypt matches. Two rollback tests: (a) the existing
  commit-failure shape (`patch("aiosqlite.Connection.commit", side_effect=...)`)
  extended to assert the agents columns are unchanged alongside the other
  surfaces; (b) a placement test that wraps `conn.execute` to raise when the
  SQL starts with `UPDATE agents`, then asserts an MCP source's ciphertext and
  the on-disk key file are unchanged — this is the one that proves the agents
  loop sits *inside* the `try:`, which the commit-patch test cannot. Note
  `tests/test_db_api.py` holds only the pool-eviction rotation test.
- AC7: `grep -rn "SQLiteAgentStore(" the_one/ tests/` shows no signature
  change was needed; `make test-unit` covers the production sites.
- AC8: `make test-unit && make lint && .venv/bin/ruff format --check the_one/ tests/`.
- AC9: `grep -n "agents.tool_overrides\|Agent override secrets" the_one/agents.md SECURITY-MODEL.md CLAUDE.md`.

## Implementation Guidance

1. **Masked-key set, marker-driven** — `the_one/mcp/_overrides.py`
   - Add `MCP_OVERRIDE_CREDENTIAL_KEYS: frozenset[str]` computed from the
     `Substitute`-marked fields of `StdioMCPOverride` and
     `StreamableHttpMCPOverride` (`field.metadata` contains the `Substitute`
     class object — the same `m is Substitute` identity check
     `the_one/tools/resolver.py` uses). Add a small test that the set equals
     `{"env", "headers", "bearer_token"}` so a future schema addition changes
     the test, not silently the masking.
   - Do **not** include `enabled_tools` / `disabled_tools` — they carry no
     marker, which is the point.

2. **Store: encrypt/decrypt the two columns** — `the_one/db/repositories.py`
   - `SQLiteAgentStore.__init__(self, conn, encryptor: Encryptor | None = None)`.
     When `None`, resolve `get_encryptor(settings.data_dir)` (import
     `from the_one.config import settings` and `from the_one.encryption import
     get_encryptor` at module top — `config.py` and `encryption.py` import
     nothing from `the_one`, so no cycle). Store as `self.encryptor` **by
     reference** with the same comment the MCP repository carries.
   - Add two module-level helpers beside `_encrypt_secrets_blob`:
     `_encrypt_overrides_column(encryptor, value: dict | None) -> str | None`
     (`None → None`, else `encryptor.encrypt(json.dumps(value))`) and
     `_decrypt_overrides_column(encryptor, raw: str | None) -> dict | None`
     (`None`/`""` → `None`; try `json.loads(encryptor.decrypt(raw))`; on
     `InvalidToken` → `json.loads(raw)` — **legacy plaintext, not `{}`**;
     `JSONDecodeError` propagates). Docstring must say why this differs from
     `_decrypt_secrets_blob` (C2 above).
   - `save()`: replace the two `json.dumps(...) if ... is not None else None`
     expressions with `_encrypt_overrides_column(self.encryptor, ...)`.
   - `_row_to_config`: drop `@staticmethod`, take `self`, use
     `_decrypt_overrides_column(self.encryptor, row["tool_overrides"])` and the
     same for `mcp_overrides`. Both callers (`load`, `list_by_connector`)
     already call `self._row_to_config(row)`.
   - `rename()` touches neither column — no change.

3. **API: one response helper, every agent return** — `the_one/interfaces/web/api.py`
   - `_agent_response(cfg: AgentConfig) -> dict[str, Any]`: `data =
     cfg.model_dump()`; if `data["mcp_overrides"]`, for each source entry that
     is a dict, for each key in `MCP_OVERRIDE_CREDENTIAL_KEYS` present with a
     truthy value: a `str` → `_mask_secret_value(v)`; a `dict` → `{k:
     _mask_secret_value(v) for k, v in ...}`; anything else → `_MASK_PREFIX`
     wholesale. Leave every other key untouched. Copy the INVARIANT comment
     style from `_mcp_source_response`.
   - `_agent_store()`: `SQLiteAgentStore(conn, get_encryptor(settings.data_dir))`.
   - Replace every agent-config `model_dump()` return in the Agents section
     with `_agent_response(...)`. Grep, don't count: the known sites are
     `list_agents`, `get_agent`, `create_agent`, `update_agent`,
     `detach_agent_from_connector`, `rename_agent`.

4. **API: server-side preserve in `update_agent`**
   - Before `AgentConfig.model_validate(data)`, load `existing` (already loaded
     for the 404 check — keep the object) and run
     `data["mcp_overrides"] = _merge_preserved_mcp_credentials(data.get("mcp_overrides"), existing.mcp_overrides)`.
   - Semantics per AC5. Treat incoming `None` as `{}` for the merge; return
     `None` if the merged result is empty so the None/`{}` fidelity the
     round-trip tests pin is preserved when nothing was stored. For an incoming
     entry that is not a dict, leave it alone — `AgentConfig` validation will
     422 it as today.
   - `create_agent` has no stored row: no preserve, but masked values in a POST
     are dropped rather than persisted (reuse `_looks_masked`).

5. **Rotation: fifth surface** — `rotate_encryption_key`
   - After the connectors SELECT, `SELECT name, tool_overrides, mcp_overrides
     FROM agents`; decode each column with `_decrypt_overrides_column` (import
     from `the_one.db.repositories`) — this is the tolerant path that also
     normalises legacy plaintext; keep `None` as `None`.
   - Re-encrypt with `new_encryptor` via `_encrypt_overrides_column`; add the
     `UPDATE agents SET tool_overrides = ?, mcp_overrides = ? WHERE name = ?`
     loop **inside the same `try:`** as the other four so rollback covers it.
   - Only DML between the first SELECT and `commit()` — the docstring's
     aiosqlite auto-commit warning applies.
   - No pool eviction is needed for agents: `AgentFactory.create()` re-reads
     the row on every build.
   - Update the docstring: "ALL FIVE surfaces … `agents.tool_overrides` /
     `agents.mcp_overrides`".

6. **Tests** — per Verification Steps. Prefer extending the existing classes
   (`TestAgentAPI`, the rotation test class, the repository round-trip tests)
   over new files. Build the legacy-row fixture with a raw `INSERT`, the
   pattern `tests/test_db_migration.py:875` already uses.

7. **Docs** — per AC9. Keep the `agents.md` additions in the same voice as the
   "Tool config secrets storage" section: what is stored where, that the
   encryptor is held by reference, the decode's legacy-plaintext fallback and
   why it differs from `_decrypt_secrets_blob`, the marker-derived masked-key
   set, and the preserve semantics (omit/masked → keep, `null` → clear).

## Edge Cases

- **Legacy row holding exactly `"{}"`** → loads as `{}`, not `None` (the
  existing `{}`-vs-`None` fidelity tests remain the oracle).
- **Empty-string column** → `None` (matches the current truthiness decode).
- **Ciphertext that decrypts to non-JSON** → `JSONDecodeError` propagates; do
  not swallow.
- **Incoming `headers` is a partially masked dict** (operator changed one
  header) → per-inner-key resolution: masked inner values come from the stored
  inner dict, new ones overwrite, inner keys absent from the payload are
  dropped (the payload is authoritative for the *shape* of a dict the client
  chose to send; only mask-shaped values are resolved).
- **Incoming `bearer_token` ≤ 4 chars** → masked as `***`; `_looks_masked`
  recognises it on the way back.
- **Masked value, nothing stored** → drop the key (mirrors
  `update_mcp_source`).
- **Stored credentials for a source the agent has since detached** → still
  preserved (they are orphan overrides; `_warn_orphan_overrides` in
  `_tool_provider.py` already logs them). Clearing is an explicit `null`, not
  a side-effect of detaching.
- **`POST /api/agents` echoing the payload** → the response is masked like any
  other; the *stored* value is the plaintext the client sent.
- **Rotation with an agent whose columns are both NULL** → skip the row or
  write NULLs; never write an encrypted `null`.
- **Two encryptor instances in tests** — the api-module patch returns the test
  encryptor; a `SQLiteAgentStore(conn)` built in the same test without passing
  it would resolve a *different* key from the isolated data dir. Tests that
  read through the store after an API write must construct the store with the
  fixture encryptor.

## Files Affected

- `the_one/mcp/_overrides.py` — add `MCP_OVERRIDE_CREDENTIAL_KEYS`.
- `the_one/db/repositories.py` — `SQLiteAgentStore` encryptor param,
  `_encrypt_overrides_column` / `_decrypt_overrides_column`, `save()` and
  `_row_to_config` changes.
- `the_one/interfaces/web/api.py` — `_agent_response`,
  `_merge_preserved_mcp_credentials`, `_agent_store`, `update_agent`,
  `create_agent`, every agent-config return, `rotate_encryption_key`.
- `tests/test_db_repositories.py`, `tests/test_db_api.py`,
  `tests/test_mcp_overrides.py` (marker-set test) — new/extended tests.
- `the_one/agents.md`, `SECURITY-MODEL.md`, `CLAUDE.md` — docs.

## Risk Checks

- **Schema**: no DDL. Column type is already `TEXT`; ciphertext is text; NULL
  semantics unchanged. No migration to create, so none to forget to run.
  Legacy data migrates lazily on next `save()` (DD5), with C2 ensuring it
  migrates rather than vanishes.
- **State-machine / lifecycle**: none introduced.
- **Cache freshness**: `get_encryptor` caches by data dir; the store holds the
  instance by reference; `install_key()` after rotation propagates to every
  live store. Source of truth is the key file; the single rebuild trigger is
  rotation; the acceptable staleness is zero and is met by reference-holding.
- **Interface changes**: `SQLiteAgentStore.__init__` widened with a defaulted
  parameter (39 construction sites unaffected); `_row_to_config` staticmethod →
  instance method (no external caller — `tests/_connector_dispatch_helpers.py`
  mentions a monkeypatch of it that was *removed*; the implementer confirms
  with `grep -rn "_row_to_config" tests/` that only docstrings/comments remain).

## Citation Audit

All citations checked against the working tree at leg design time (branch
`flight/01-self-configuration-surface`, base `0e8278d`):

- `repositories.py` — `SQLiteAgentStore.__init__` at :74 (`def __init__(self,
  conn: aiosqlite.Connection)`), `save()` override writes at :171-172,
  `_row_to_config` at :238 (`@staticmethod` at :237), callers at :118 and :128,
  `_decrypt_secrets_blob` at :40-66 with the "Treat as empty secrets" fallback
  at :61-64, `MCPSourceRepository.__init__` reference-holding at :405-407 — all
  live.
- `api.py` — `_agent_store` at :66-68, agent `model_dump()` returns at :446,
  :457, :539, :558, :627, :678 (six; the design review corrected an earlier
  citation of :723, which is `update_knowledge_base`), `_looks_masked` at :852,
  `_mask_secrets` at :910, `rotate_encryption_key` decorator at :4711 / `def`
  at :4712 with the UPDATE `try:` block at :4839-4863 — all live. The
  `m is Substitute` metadata scan is precedented in
  `api.py:_enrich_schema_with_markers` (:119-157).
- `_overrides.py` — `env` (:60), `headers` (:89), `bearer_token` (:90) — live.
- `_web_config.py:default_user_agent` `Substitute` at ~:250 — live; it is the
  only `Substitute` marker outside `_overrides.py`.
- `studio.js:collectFormData` ~:2037-2132, `mcps-tab.js` header comment,
  `tools-tab.js:376` — live.
- `tests/test_db_api.py::client` patches `api.get_encryptor` (:33-36);
  `tests/test_db_repositories.py::agent_store` at :40-42;
  `tests/test_provider_api.py::TestEncryptionRotation` from :557;
  `tests/conftest.py` `THE_ONE_DATA_DIR` isolation at :36 — live.

Design review (2026-08-24, Developer/Sonnet): approve with changes — the two
citation corrections above applied; no substantive change to criteria or
guidance.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
