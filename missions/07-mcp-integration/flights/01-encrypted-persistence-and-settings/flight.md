# Flight: Encrypted MCP Source Persistence + Settings Page

**Status**: completed
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] The operator can register, edit, and remove MCP server definitions through a Settings surface that follows the existing design language and admin patterns, with sensitive configuration fields persisted in encrypted form using the same key + rotation pipeline that already protects LLM-provider credentials
- [ ] Credentials never appear in plaintext outside the encryption boundary — not in API responses, not in logs, not in the inspector trace pane — and the existing edit-form sentinel pattern is preserved so an operator can re-save an MCP source without retyping its secrets
- [ ] The Settings MCP section, the simplified inspector, and the Studio MCPs tab all meet the M04/M06 design-language quality bar without alignment-flight rework *(F1 contributes the Settings MCP section)*

---

## Pre-Flight

### Objective

Land the storage layer and operator-facing Settings page for MCP server definitions. The mission's `mcp_sources` table is reshaped to support field-segregated encryption: the existing `config` JSON column stays plaintext (transport, command, args, URL, non-sensitive headers), and a new `secrets` column holds Fernet-encrypted JSON of operator-marked sensitive fields (env-var values, OAuth client_secret, bearer headers). The deprecated `'sse'` transport literal is renamed to `'streamable-http'` to align with the current MCP specification. The encryption key + rotation pipeline that already protects LLM provider credentials is extended in one pass to cover MCP source secrets, with a crash-safe rotation transaction that re-encrypts both surfaces atomically. The existing `/api/mcp-sources` CRUD endpoints are extended with transport-aware validation, per-sensitive-field `__MASKED__` sentinel handling on update, and consistent secret-masking on response. A new "MCP Servers" Settings sidebar entry lands as a peer of LLM Providers and Built-in Tools, with grid + editor sub-modules mirroring the M06 provider-editor pattern. No live MCP connection logic and no OAuth flow in this flight — those land in F2 and F5 respectively. The OAuth-static-config fields (issuer URL, client_id, optional pre-registered client_secret, scopes) ARE persisted now so F5 only adds the live flow without a schema migration.

### Open Questions

- [x] **Encryption granularity** → field-segregated with two-column storage. The `config` JSON column stays plaintext for non-sensitive fields (`command`, `args`, `url`, plain `headers`); a new `secrets` JSON column holds the Fernet-encrypted JSON of operator-marked sensitive fields. The operator's "mark as sensitive" UI checkbox routes a field into one or the other at save time. In-memory the model exposes a single merged dict; the storage layer keeps them split. Resolution: see Design Decisions.
- [x] **OAuth field persistence in F1** → F1 persists the full static OAuth client config shape (issuer URL, client_id, optional client_secret marked sensitive, scopes list, redirect URI). F5 adds the live token-acquisition flow on top without a schema migration. Resolution: see Design Decisions.
- [x] **URL slug for the new section** → `#admin/mcp-sources`, matching the existing `/api/mcp-sources` REST path. Avoids renaming the API path and keeps the studio.js `fetchMcpSources()` call site stable.
- [x] **Settings sidebar label** → "MCP Servers" — disambiguates from the Studio agent-editor "MCPs" tab (which attaches them, not the inventory) and matches the MCP spec's own "server" terminology.
- [x] **Type literal rename target** → `'streamable-http'` (kebab-case, matches the `'openai-compatible'` precedent in `llm_providers.type`).
- [x] **Resolver-keying decision (mission Open Q "MCP source identity for the resolver")** → Deferred to F4 (per-agent attach) design. F1's storage shape doesn't constrain F4's choice between extending `tool_overrides` keys vs. a parallel `mcp_overrides` field. Carries forward as a mission-level Open Q.
- [x] **Migration pattern** → Hybrid: v3/v5/v6's whole-table-rebuild structure (PRAGMA foreign_keys=OFF/ON brackets, table-rename ceremony for the CHECK constraint change) using v8/v9's individual `await conn.execute(...)` calls + `INSERT OR IGNORE INTO schema_version` LAST for idempotency. The `executescript` form is avoided — its implicit-COMMIT defeats the LAST-INSERT idempotency. The `'sse'` → `'streamable-http'` rename happens via `CASE WHEN type='sse' THEN 'streamable-http' ELSE type END` inside the `INSERT INTO mcp_sources_new SELECT ...` step (standard SQLite CASE-WHEN value transformation applied within v3/v6's whole-table-rebuild ceremony — note: v3 and v6 themselves used identity-SELECTs without column transformation, so this is the rebuild ceremony from those migrations plus a CASE expression in the SELECT clause; it is NOT an in-codebase precedent for the CASE pattern itself). A pre-rebuild UPDATE against the old table would FAIL the still-active `CHECK (type IN ('stdio','sse'))` constraint. Documented in L1.
- [x] **Per-sensitive-field UI shape**: chip-list with per-row sensitive checkbox? Two-column form with sensitive fields in a `secrets` section and non-sensitive in `config`? A unified key/value table with a sensitive toggle per row? Resolved in L6: option (c) unified kv table.
- [x] **Pre-existing `'sse'` rows in the wild**: any local dev/test DBs likely have empty `mcp_sources`, but the migration must still upgrade `'sse'` → `'streamable-http'` cleanly with no data loss in case rows exist. Resolved in L1: migration test seeds BOTH an `'sse'` row AND a `'stdio'` row with non-empty `config` before applying v10, then asserts the `'sse'` row was renamed, the `'stdio'` row is untouched, both rows have `secrets='{}'`, and re-running the migration is a no-op.

### Design Decisions

**Field-segregated encryption with two-column storage**: `mcp_sources.config TEXT DEFAULT '{}'` (plaintext JSON, unchanged at the column level) holds non-sensitive fields. A new `mcp_sources.secrets TEXT DEFAULT '{}'` column holds Fernet-encrypted JSON of operator-marked sensitive fields. The encryption shape is "encrypt the `secrets` JSON blob as a single ciphertext string," NOT per-field encryption inside the JSON — one `Fernet.encrypt` call per row at save time, one `Fernet.decrypt` per row at read time, mirroring the `llm_providers.api_key` pattern at the structural level even though MCP secrets are a JSON blob rather than a single string.
- Rationale: clean separation at storage layer (auditable "what's encrypted" by looking at column), simple at code layer (one decrypt per row), gives admin grid free non-decrypt rendering of plaintext fields like command/URL.
- Trade-off: fields cannot move between sensitive and non-sensitive without a save round-trip; an operator who realizes mid-edit that a field should be sensitive triggers re-saves of both blobs. Acceptable — the alternative (per-field tagged encryption inside one blob) doubles the marker noise in serialization for negligible gain.

**Pydantic model exposes a merged in-memory shape**: `MCPSource.config: dict[str, Any] = Field(default_factory=dict)` (non-sensitive) and `MCPSource.secrets: dict[str, Any] = Field(default_factory=dict)` (sensitive) are separate fields on the model; serialized that way to/from the storage layer. Consumers that need a flat-merged view — specifically F2's bearer-token-from-config / env-var resolution path at MCP-process spawn time — call a `MCPSource.merged_config()` helper that returns a single dict. Consumers that need the split (UI rendering in L6, masking in L3, rotation in L4, F4's resolver-keying) keep the split explicit.
- Rationale: callers that DO care about the split (UI rendering, encryption rotation, masking on response, F4 resolver) get explicit access; callers that don't (F2 connect path) get the convenience method. The split is the storage shape; merging is opt-in.
- Trade-off: two surface areas to keep consistent on save/load. Acceptable — repository tests lock the round-trip invariants. F4 design will explicitly NOT use `merged_config()`; F4 keeps the split visible because per-key Substitute/Narrow markers may need to know whether a field is sensitive.

**MCPSource.type literal becomes `Literal["stdio", "streamable-http"]`**: replaces `Literal["stdio", "sse"]`. Schema migration v10 rebuilds the table with the new CHECK constraint (`type IN ('stdio', 'streamable-http')`) and `UPDATE`s any pre-existing `'sse'` rows to `'streamable-http'` before the constraint takes effect. Pydantic literal change ships in the same flight.
- Rationale: HTTP+SSE was deprecated by the MCP spec in revision 2025-03-26 and replaced by Streamable HTTP; carrying a stale literal is technical debt that gets harder to remove the longer F2's connect logic depends on the model's type field.
- Trade-off: any external tooling pinning the legacy `'sse'` value via direct `/api/mcp-sources` writes breaks. Acceptable — there is no such tooling today and the API has shipped only as a CRUD passthrough with no live consumers.

**OAuth static config persists in F1 even though the live flow lands in F5**: the editor surfaces OAuth fields (`issuer_url`, `client_id`, `client_secret` (marked sensitive by default), `scopes` (list), `redirect_uri`) for `streamable-http` transport. Persisted via the same plaintext+secrets split. F5 only adds the live token-acquisition handler and the runtime token-storage shape (access_token + refresh_token, both sensitive) on top.
- Rationale: keeps F5 free of schema-migration churn, surfaces the operator-facing form shape one flight earlier so F2's bearer-token-from-config tests have a real config to read from, no F5 rework when DCR / Client ID Metadata Documents are decided.
- Trade-off: form has fields that don't yet do anything live in F1. Mitigated with inline help text marking "configure now; consent flow ships in a later mission flight."
- **F1↔F5 column-shape contract**: F1 commits the column shape `{issuer_url, client_id, client_secret, scopes, redirect_uri}` plus the runtime token slots `{access_token, refresh_token, token_expires_at}` (the runtime tokens added to `secrets` in F1 even though F5 is the first writer — same rationale as the OAuth fields). DCR and Client ID Metadata Documents (mission Open Q for F5) MUST fit within these columns or surface as an F1-blocker before F5 design — no quiet schema migration in F5. CIMD-style URL-as-client_id fits in the existing `client_id` column natively.

**Encryption rotation extended in one pass, not per-surface**: `/api/encryption/rotate` is updated in this flight to re-encrypt every MCP source's `secrets` blob in the same crash-safe transaction that already re-encrypts every `llm_providers.api_key`. Both surfaces commit atomically before the new key file replaces the old one via `os.replace`.
- Rationale: a partial rotation that handles only one of the two surfaces leaves the other surface encrypted with a key that no longer exists on disk — silent corruption for either MCP secrets or LLM provider keys depending on which surface was missed. Single-transaction rotation matches the mission constraint ("Single-key encryption reuse, not a parallel key").
- Trade-off: the rotation endpoint grows by ~30 lines and the test surface grows by ~3 cases (rotate-mcp-only, rotate-mixed, mcp-rotation-preserves-on-failure). Acceptable.

**Migration shape: hybrid v3/v5/v6 + v8/v9 idempotency**: schema v10 uses the v3/v5/v6 whole-table-rebuild ceremony (CREATE new + INSERT-SELECT old + DROP old + RENAME new) but with v8/v9's individual-execute pattern (NOT `executescript`) and `INSERT OR IGNORE INTO schema_version` LAST for retry-on-partial-apply safety. The `'sse'` → `'streamable-http'` rename is applied inline via `CASE WHEN type='sse' THEN 'streamable-http' ELSE type END` in the `INSERT INTO mcp_sources_new SELECT ...` step. **Crucially, this is NOT a pre-rebuild `UPDATE` on the old table** — the still-active CHECK constraint on `mcp_sources` is `type IN ('stdio', 'sse')`, so writing the literal `'streamable-http'` against the old table would fail constraint validation. The CASE-in-SELECT lands the renamed value directly into the new table whose CHECK constraint already permits it.
- Rationale: documented in `schema.py` v8 docstring — `executescript` silently COMMITs before each non-DML statement; using individual `await conn.execute` calls keeps idempotency semantics correct across retries. Whole-table-rebuild is unavoidable because SQLite has no `ALTER TABLE DROP CONSTRAINT`. The CASE-WHEN value-transformation form is standard SQLite (not an in-codebase precedent — v3 and v6 used identity-SELECTs without column rewriting).
- Trade-off: more verbose than `executescript`. Acceptable — the verbosity is the idempotency.

**Sidebar nav extension preserves M06's section-nav primitive**: the new `mcp-sources` category slots into the existing `categories` array in `admin.js` alongside `system`, `providers`, `tools`. `validIds`, `serializeState`, `hydrateState`, `_setCategory` all gain parallel branches. The grid + editor sub-modules live at `static/js/areas/admin/mcp-servers-grid.js` and `mcp-server-editor.js`, mirroring `providers-grid.js` + `provider-editor.js`. Hash routing follows the provider precedent: `#admin/mcp-sources`, `#admin/mcp-sources/new`, `#admin/mcp-sources/{id}`.
- Rationale: M06 established the section-nav pattern for exactly this kind of expansion; the codebase already has all the helpers (`App.layout.renderSectionNav`, `App.confirmDelete`, `App.confirmDialog`, `entity-tile-grid`, dirty-flag mirror).
- Trade-off: copy-mostly-paste of provider-editor scaffold. Acceptable — the editor logic differs in transport-aware fields and the sensitive checkbox; everything else is mechanical.

### Prerequisites

- [x] M05 F2 resolver shipped — `Encryptor`, `__MASKED__` sentinel, `Substitute`/`Narrow` markers all available
- [x] M06 admin section-nav primitive (`App.layout.renderSectionNav`, `categories` array pattern, hash routing) shipped
- [x] LLM provider editor pattern (`provider-editor.js`, `providers-grid.js`, `_provider_response` masking) is the canonical reference
- [x] `/api/encryption/rotate` endpoint exists with crash-safe pattern + 4 test cases including failure-path invariants
- [x] `MCPSource` Pydantic model + `MCPSourceRepository` + `/api/mcp-sources` CRUD all exist as plain (unencrypted) CRUD — F1 extends them, doesn't create them from scratch
- [x] Mission encryption-granularity Open Question is closed (decision: field-segregated)
- [x] Mission OAuth-field-persistence-in-F1 question is closed (decision: full static OAuth config persists in F1)

### Pre-Flight Checklist

- [x] All open questions resolved (8 closed; 2 deferred to L6 + L1 design respectively, both flagged in Open Questions)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (see In-Flight § Verification)
- [x] Legs defined (see In-Flight § Legs)

---

## In-Flight

### Technical Approach

The flight lands in seven legs that compose bottom-up: (1) schema migration → (2) model + encrypted repository → (3) REST endpoint extension → (4) encryption rotation extension → (5) sidebar nav + grid → (6) editor sub-module → (7) optional HAT.

The structural pattern at each layer mirrors LLM Providers, with the field-segregated encryption being the only fundamental departure from the provider precedent. The provider repository encrypts a single `api_key` column; this flight's repository encrypts a `secrets` JSON blob — same Fernet-per-column shape, different content.

The schema migration is the only irreversible step in the flight; its design (rebuild ceremony + idempotent INSERT-OR-IGNORE) is deliberately conservative. Every other leg is additive on top of an unchanged storage layer once L1 lands.

The Settings UI legs (L5, L6) follow the existing admin orchestrator delegation pattern: `admin.js` routes to grid or editor based on URL state; sub-modules own their own DOM and fetch lifecycle; orchestrator owns the dirty-flag mirror, beforeunload registration, and confirmDialog gates. No new top-level UI patterns are introduced.

**Encryption rotation (L4)** is the highest-coupling leg: it extends a shipped endpoint that has dedicated failure-path test coverage. The leg's primary risk is regressing the LLM provider rotation behavior; mitigated by leaving the existing logic structurally intact and adding the MCP loop as a parallel pass within the same transaction. The single failing test from `test_provider_api.py::TestEncryptionRotation::test_rotate_preserves_key_on_db_failure` is the regression net.

**Field-sensitive UI shape (L6)** carries the only deferred design question — see Open Questions. L6 design will pick between three candidate shapes and document the choice with rationale.

### Checkpoints

- [x] L1 lands: schema v10 migration test passes; pre-existing `'sse'` row migrated to `'streamable-http'`; idempotent re-run is a no-op
- [x] L2 lands: `MCPSource` model has `secrets` field; `MCPSourceRepository` round-trips encrypted secrets; masked-tail behavior matches provider precedent
- [x] L3 lands: `/api/mcp-sources` POST/PUT validate transport-aware fields; `__MASKED__` per-field sentinel preserves stored secrets across edit; GET response masks every secret with `***...{tail4}` (or `***` for short values); new `/api/mcp-sources/types` endpoint returns the two transport types
- [x] L4 lands: `/api/encryption/rotate` re-encrypts both LLM provider keys AND MCP source secrets in one crash-safe transaction; failure-path test mirrors `test_rotate_preserves_key_on_db_failure` for the MCP surface; test coverage includes rotation with mixed providers + MCP sources
- [x] L5 lands: "MCP Servers" appears as a peer entry in the Settings sidebar nav; grid renders empty state when no sources exist; "New MCP Server" CTA opens the create editor; hash routing for `#admin/mcp-sources` and `#admin/mcp-sources/new` works on direct-load
- [x] L6 lands: editor renders transport-aware form fields; per-field sensitive checkbox routes the field between `config` and `secrets` blobs at save; OAuth client config section persists statically; `__MASKED__` round-trip preserves unchanged secrets; Danger Zone delete with `confirmDelete` works; dirty flag + beforeunload integrated
- [ ] L7 *(optional)* lands: operator HAT walkthrough covering both transports, sensitive-field round-trip across save/reload AND key rotation, dirty-flag confirm-dialog edges, and a final regression sweep on `test_provider_api.py::TestEncryptionRotation` passes green

### Adaptation Criteria

**Divert if**:
- L1 migration cannot be made idempotent under the chosen pattern — would force a different migration shape and re-design L2's read path. Likely never; the pattern is well-precedented.
- Per-field encryption (decision-b2 in mission Open Q) becomes necessary mid-flight — would force schema rework. Decision is locked at flight start; only re-open if a concrete L3 use case forces it (none anticipated).
- `/api/encryption/rotate` extension breaks one of the four existing rotation tests in a way that can't be fixed by adding the MCP loop without restructuring — would force a rotation refactor flight before continuing.

**Acceptable variations**:
- L6's per-field sensitive UI shape: which of the three candidate shapes (chip-list with checkbox, two-section split, unified table with toggle) ships is decided at L6 design and may differ from any pre-flight prediction.
- L1 migration may add additional columns beyond `secrets` if L2's repository design surfaces a need (e.g., a `transport_version` column for future compatibility), without re-opening the flight design.
- L7 may be skipped if L1-L6 land cleanly and HAT-class issues are not surfaced during integration.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-schema-v10-migration` - Schema v10 migration: rebuild `mcp_sources` table with new CHECK constraint (`type IN ('stdio', 'streamable-http')`) + add `secrets TEXT DEFAULT '{}'` column. The `'sse'` → `'streamable-http'` rename is applied via `CASE WHEN type='sse' THEN 'streamable-http' ELSE type END` inside the `INSERT INTO mcp_sources_new SELECT ...` step (NOT a pre-rebuild UPDATE — the still-active old CHECK constraint would reject `'streamable-http'`). Idempotent under partial-apply via `INSERT OR IGNORE INTO schema_version`. New `tests/test_db_migration.py::TestSchemaV10` walk test: seed a v9 DB containing BOTH a row with `type='sse'` (non-empty `config`) AND a row with `type='stdio'` (non-empty `config`); assert post-migration the `'sse'` row has `type='streamable-http'`, the `'stdio'` row is unchanged, both rows have `secrets='{}'`, and the schema_version row is at v10. Idempotent re-run (call `ensure_schema` twice on the same connection) is a no-op.
- [x] `02-encrypted-repository` - `MCPSource` Pydantic model gains `secrets: dict[str, Any] = Field(default_factory=dict)` field (separate from `config`; both fields use `default_factory=dict` for round-trip stability between freshly-created and migrated rows). The model's `type` `Literal` becomes `Literal["stdio", "streamable-http"]` (drops `'sse'`). `merged_config()` helper returns a single dict for F2's bearer-token resolution path; F4's resolver path keeps the split. `MCPSourceRepository.__init__(self, conn, encryptor)` stores `self.encryptor = encryptor` **as a reference, NOT a copy** — `Encryptor.install_key()` post-rotation must propagate to live repository instances (mirrors `LLMProviderRepository:489`). `_to_row` encrypts the `secrets` JSON blob via `Fernet.encrypt(json.dumps(secrets).encode())`; `_row_to_model` decrypts. **Update sites** (the constructor signature change and the `'sse'` literal removal ripple to several call sites): (a) `the_one/interfaces/web/api.py:56-58` — `_mcp_repo()` factory now constructs with `get_encryptor(settings.data_dir)` per the `_provider_repo()` precedent at `api.py:617-620`; (b) `tests/test_db_repositories.py:51-52` — `mcp_repo` fixture passes an Encryptor; (c) `tests/test_db_repositories.py:230,244` — existing test cases using `type="sse"` rewritten to `type="streamable-http"`; (d) `tests/test_db_api.py:188-209` — `TestMCPSourceAPI::test_crud` augmented with the new shape, and any `'sse'` literals replaced. Tests in `test_db_repositories.py::TestMCPSourceRepository` extended: encryption round-trip with mixed plaintext + secrets, empty-secrets default round-trip, post-`install_key` decryption with a new key still works on the same repo instance.
- [x] `03-api-endpoint-extension` - `/api/mcp-sources` POST/PUT validate transport-aware fields per `MCPSource.type` (stdio: command, args, env; streamable-http: url, headers, OAuth client config). **GET response shape is `{id, name, type, config: {...plaintext...}, secrets: {key: "***...{tail4}", ...}, created_at, updated_at}`** — split visible to the client, with masking applied to each decoded sensitive field's VALUE individually (NOT to the encrypted blob or the JSON serialization). Short values (`<=4` chars) mask as `***`; longer values mask as `***...{tail4}` mirroring `_mask_api_key` at `api.py:667`. `__MASKED__` sentinel handling on PUT operates per-key inside the `secrets` blob: an incoming `secrets[key] == "__MASKED__"` preserves the existing stored value for that key; other keys overwrite. New `/api/mcp-sources/types` endpoint returns `[{value:'stdio',label:'Stdio'},{value:'streamable-http',label:'Streamable HTTP'}]`. Tests in `test_db_api.py::TestMCPSourceAPI` extended: per-field masking shape, per-key `__MASKED__` round-trip, transport-aware validation rejection, types endpoint shape.
- [x] `04-rotation-extension` - `/api/encryption/rotate` extended to re-encrypt every MCP source's `secrets` blob in the same crash-safe transaction that already re-encrypts `llm_providers.api_key`. **All-in-memory invariant pinned**: SELECT all LLM provider rows → SELECT all MCP source rows → re-encrypt all rows in memory → single UPDATE loop for both tables → single `commit()` → file replace. **No non-DML statements between the two table loops** (no `PRAGMA`, no `CREATE TEMP TABLE`, no DDL) — the auto-begin transaction must remain unbroken; aiosqlite's default mode would silently COMMIT before any non-DML statement (per `schema.py` v8 docstring). New rotation tests in `test_provider_api.py::TestEncryptionRotation` (or a sibling `test_mcp_rotation.py` if the file grows too large): `test_rotate_mcp_source_secrets`, `test_rotate_mixed_providers_and_mcps`, `test_rotate_preserves_mcp_secrets_on_db_failure` (mirroring the existing `test_rotate_preserves_key_on_db_failure` invariants — pre-rotation key bytes preserved on disk, MCP secret still decrypts via cached encryptor, direct decrypt with old key still works on disk ciphertext).
- [x] `05-settings-nav-and-grid` - `admin.js` `categories` array gains `{ id: 'mcp-sources', label: 'MCP Servers' }`; `validIds` array gains `'mcp-sources'`. **Closure-mirror enumeration** (the providers pattern is not just instance properties — the `pendingProviderId`/`pendingFormMode`/`mcpSourceFormMode`/`editingMcpSource` are `var`s declared in `init`, exposed via `Object.defineProperty` getter/setters, and mutated in EVERY closure that touches admin state): L5 must extend in parallel (a) `var` declarations at `admin.js:120-138`, (b) `Object.defineProperty` exposures at `:600-639`, (c) reset blocks in `doSetCategory` at `:199-213` and `_setCategory` at `:640-654`, (d) `_tryConsumePendingMcpSource` companion to `_tryConsumePendingProvider`, (e) `hydrateState` parsing branch at `:55-67` for `mcp-sources/new` + `mcp-sources/{id}` patterns, (f) `serializeState` branch at `:8-33`. New `admin/mcp-servers-grid.js` sub-module mirroring `providers-grid.js` shape (100 lines, structural copy). Transport-badge: `KNOWN_TRANSPORT_BADGES = ['stdio', 'streamable-http']` mirrors `KNOWN_BADGE_TYPES` at `admin.js:165` for dev-mode/extensibility precedent. Browser test `test_flow_admin_mcp_navigation.py` covers section-nav presence, hash-routing direct-load for `#admin/mcp-sources` and `#admin/mcp-sources/new`, and grid-empty-state CTA.
- [x] `06-editor-sub-module` - New `admin/mcp-server-editor.js` mirrors `provider-editor.js` scaffold: editor-header + Connection section (transport-aware fields) + per-field sensitive checkbox + OAuth client config section (for streamable-http) + Danger Zone delete. Per-sensitive-field UI shape decided in this leg's design (see Open Questions). `__MASKED__` round-trip preserves unchanged secrets; dirty-flag mirror via `onDirtyChange`; `confirmDelete` for destructive action. Browser test covering create + edit + delete cycle for both transports added under `tests/browser/`.
- [ ] `07-hat-and-alignment` *(optional)* - Operator-driven HAT walkthrough: empty-state empty-canvas CTA → create stdio source with mixed sensitive/non-sensitive fields → edit one sensitive + one non-sensitive without retyping the secret → trigger key rotation while MCP source exists → verify secret still decrypts correctly post-rotation → delete with confirm dialog. Final regression sweep on `test_provider_api.py::TestEncryptionRotation` and the new MCP rotation tests.

---

## Post-Flight

### Completion Checklist

- [ ] All legs L1-L6 completed (L7 optional)
- [ ] Schema migrated to v10 cleanly on a pre-existing v9 dev DB
- [ ] All new + existing tests pass (`make test`)
- [ ] Browser tests pass (`make test-browser`)
- [ ] `make lint` and `make format` clean
- [ ] `make rebuild` + manual smoke check: create stdio MCP source, edit it, rotate key, verify masked tail still works, delete with confirm
- [ ] `agents.md` updated with the new MCP source storage shape (encryption-via-secrets-column pattern, `__MASKED__` per-field semantic, transport-rename note)
- [ ] `CLAUDE.md` updated with the v10 migration entry and the field-segregated encryption pattern as the authoritative MCP storage contract for F2-F8

### Verification

- **Unit-level**: `pytest tests/test_db_migration.py::TestSchemaV10 tests/test_db_repositories.py::TestMCPSourceRepository tests/test_db_api.py::TestMCPSourceAPI tests/test_provider_api.py::TestEncryptionRotation -v` — all green
- **Integration-level**: `make test` — full suite including the new tests, no regressions
- **Browser-level**: `make test-browser` — new MCP-server-editor browser test passes alongside existing admin/studio coverage
- **Manual rotation invariant**: with a `'streamable-http'` MCP source containing an encrypted `client_secret` and a `'stdio'` source containing encrypted `env`, trigger `/api/encryption/rotate`; both sources still decrypt correctly afterward; both LLM provider api_keys still decrypt correctly afterward
- **Manual masking invariant**: GET `/api/mcp-sources/{id}` for any source with secrets — the response shows `***...{tail4}` for each sensitive field; no plaintext leak
- **Manual sentinel invariant**: edit an MCP source, change one non-sensitive field, save without retyping any secret — secrets persist intact across the save (via per-field `__MASKED__` handling)
