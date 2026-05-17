# Flight Log: Admin Surface for Connector Accounts

**Flight**: [Admin Surface for Connector Accounts](flight.md)

## Summary

_(populated during execution)_

---

## Flight Director Notes

### 2026-05-17 — Orchestration kickoff

- Phase file `.flightops/agent-crews/leg-execution.md` loaded; structure validated (Crew/Interaction Protocol/Prompts present; all prompt fences present). Developer = Sonnet, Reviewer = Haiku per project crew config.
- Flight status transitioned `ready` → `in-flight` before leg-1 design.
- Reconnaissance report on `main` shows zero drift from plan inputs. Six planned legs to execute, in order:
  1. `pre-leg-maintenance-from-f1`
  2. `idle-ttl-field`
  3. `rest-crud-and-masked-sentinel`
  4. `rest-doctor-and-rotation-eviction`
  5. `frontend-grid-and-types`
  6. `frontend-editor-and-browser-tests`
- All legs are autonomous (no HAT/alignment leg this flight per Design Decision "HAT / alignment leg skipped").
- Working tree on the-one was on `main`, clean except for the previously-untracked Flight 2 artifact directory; feature branch `flight/02-admin-surface-for-connector-accounts` cut from `main` so the artifact files land on the flight branch alongside the code changes they describe.
- Per-leg cadence: design → developer design-review → incorporate → (optional re-review) → implement. Code review + commit are deferred to a single post-flight cycle per `/agentic-workflow` (eliminates per-leg review/commit overhead).

---

## Reconnaissance Report

Pre-flight reconnaissance verifying that Flight 1 debrief action items and the cited code locations are still live on `main` before Flight 2 plans against them.

| Source item | Classification | Evidence | Recommendation |
|---|---|---|---|
| F1 debrief: Fernet envelope duplicated between `MCPSourceRepository` and `ConnectorAccountRepository` | confirmed-live | `db/repositories.py:301-326` (MCP) and `:456-479` (Connector) are byte-identical `_secrets_to_ciphertext` / `_ciphertext_to_secrets` definitions; no shared helper exists on `main` | Leg 0 lifts to a shared `_encrypt_secrets_blob` / `_decrypt_secrets_blob` pair before any new repository code is added in Flight 2 |
| F1 debrief: `_evict_all_for_account` not wired into rotation | confirmed-live | `interfaces/web/api.py:rotate_encryption_key` (L2745-2885) contains zero references to `_evict_all_for_account`; the only callers are `tests/test_connectors_pool.py` and `tests/test_connectors_e2e.py` | Leg 3 wires the post-commit eviction loop in the rotation transaction, paired with the rotation-while-pool-warm test |
| F1 debrief: `__MASKED__` sentinel contract at `db/repositories.py:447` (cited) | already-satisfied (citation off-by-one — actual L446) | `db/repositories.py:446` carries the comment "No `__MASKED__` sentinel handling here — that runs at the API edge"; MCP REST PUT pattern at `interfaces/web/api.py:901-942` is the precedent to mirror; `_MASKED_API_KEY_SENTINEL = "__MASKED__"` at `api.py:2157` | Leg 2 mirrors the MCP per-key PUT block verbatim minus the OAuth-managed-keys preservation step (MCP-specific) |
| F1 debrief: `function-local-import-to-break-load-cycle` is now a 3-occurrence pattern | partially-satisfied | All 3 code occurrences match (`mcp/_pool.py:196`, `db/repositories.py:398`, `connectors/_pool.py:158-167+168-169`); BUT `agents.md` Project Conventions (L24-85) does NOT include the convention | Leg 0 appends the convention to `agents.md` with the three citation points |
| F1 debrief: `flight.md` leg-6 bullet patch (action item #1) | confirmed-live | F1's `flight.md:175` still reads "The lifespan integration is documented in code but **wired into `app.py` only in Flight 2**" — directly contradicts what shipped | Leg 0 patches the bullet inline so Flight 2 readers don't plan duplicate work |
| F1 debrief: `connectors/README.md` §3 missing skeleton plugin example | confirmed-live | `the_one/connectors/README.md` §3 (~L69-94) describes Protocol decomposition without a code block; the only fenced code in the file is the package-layout tree in §1 | Leg 0 inserts a ~30-line "Skeleton for a real plugin" block in §3 |
| F1 debrief: 2 pre-existing `AsyncMock-never-awaited` warnings on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (carries forward from M07) | confirmed-live (drift: count now 4, not 2) | `pytest tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` emits 4 `PytestUnraisableExceptionWarning` lines wrapping `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` | OUT OF SCOPE for Flight 2; remains a maintenance backlog item — the count drift is a small bookkeeping note, not new work |
| F1 debrief: untested edge cases (rotation-while-pool-warm, concurrent `shutdown_drain`+`acquire`, reaper-sweep-during-drain) | confirmed-live | `tests/test_connectors_pool.py` covers happy-path drain and `acquire-during-already-shutdown`; no test stages the racy cases; no rotation-with-warm-pool test | Flight 2 lands rotation-while-pool-warm (leg 3); the other two stay on Flight 10's hardening list |
| F1 debrief: `last_activity` per-inbound-acquire ratification (Flight 3 owns) | confirmed-live | Only Flight 01 directory exists; no Flight 3 spec yet; `connectors/_pool.py` has no `touch_activity` API | Out of Flight 2 scope; flight-2 known-issue list carries it forward for Flight 3 |
| Encryption rotation transaction shape at `api.py:2745-2885` | confirmed-live (no drift) | Single atomic commit covering three corpora (`llm_providers.api_key`, `mcp_sources.secrets`, `connector_accounts.secrets`); try/except/rollback wrapper present | Leg 3 extends with eviction post-commit; the atomic-commit structure is preserved verbatim |
| MCP source CRUD precedent at `api.py:840-1060` | confirmed-live | `GET /mcp-sources`, `GET /mcp-sources/types`, `GET/{id}`, `POST`, `PUT`, `DELETE` — the structural template for Flight 2's `/api/connector-accounts/*` routes | Leg 2 mirrors verbatim (minus OAuth-specific preservation steps) |
| MCP doctor probe at `api.py:1293-1619` (`POST /mcp-sources/{id}/test/connect`) | confirmed-live | Returns `{status: "ok"|"auth_required"|"error", ...}`; F8 L4 added optional in-flight override body | Leg 3 builds the parallel `/api/connector-accounts/{id}/test/connect` returning the canonical `DoctorReport`-shaped JSON; in-flight override is a deferred-decision flag |
| Studio frontend pattern at `static/js/areas/studio/mcp-server-editor.js` (1950 lines) + `mcp-servers-grid.js` (117 lines) | confirmed-live | Vanilla JS; `entity-tile-grid` + `editor-section` + `kv-value-input` + `data-original-masked` patterns; `MASKED_SENTINEL = '__MASKED__'` at L28 | Legs 4-5 mirror structurally; the `data-original-masked` round-trip is the canonical pattern for the masked-secret edit cycle |
| Browser-test framework at `tests/browser/` with snapshot baselines gitignored | confirmed-live | `tests/browser/test_flow_studio_mcp_editor.py`, `test_mcp_test_connection_button.py`, etc.; `tests/browser/__snapshots__/` gitignored at `.gitignore:14-15` | Leg 6 follows the precedent; matches the user-global "snapshots are local-only" rule |
| Studio routing pattern at `static/js/areas/studio.js` | confirmed-live | Routing handles `mcp-sources` / `mcp-sources/new` / `mcp-sources/{id}`; selection / form-mode state lives on the `App.studio` area object | Leg 4 adds a parallel `connector-accounts` section using the same shape |
| `_MASKED_API_KEY_SENTINEL` constant at `api.py:2157` | confirmed-live | Defined as `"__MASKED__"` exactly; reused across LLM provider and MCP source per-key resolution | Leg 2 imports the same constant; the cross-subsystem reuse is acknowledged in the code comment around L906-909 |

**Conclusion**: 7 of 9 F1 debrief action items are `confirmed-live` and unaddressed on `main`; 1 is `already-satisfied` (the repository comment exists; MCP edge pattern is in place — Flight 2 mirrors); 1 is `partially-satisfied` (3 code occurrences exist; only the `agents.md` documentation is missing). The F1 spec/code shape on `main` matches what this flight planned against — no drift. Flight 2 bundles 5 of the 9 items into leg 0 (Fernet helper lift, `agents.md` convention, README skeleton, F1 flight.md leg-6 patch, rotation eviction wiring — last one lives in leg 3); 1 is handled naturally (rotation-while-pool-warm test in leg 3); 2 are explicitly out of scope (Flight 10's hardening items + Flight 3's `last_activity` ratification); 1 stays on the maintenance backlog (the AsyncMock warnings).

---

## Design Adjustments

_(append adjustments to the flight spec discovered during leg planning/execution)_

### 2026-05-17 — Leg 4: doctor-probe response envelope includes `message`

- The flight Design Decision "Doctor-probe response shape" specified `{status, details}` for `POST /api/connector-accounts/{account_id}/test/connect`. Leg 4 ships `{status, message, details}` — the additional `message` field.
- **Why**: `DoctorReport.message: str` is a required field on the dataclass (`the_one/connectors/base.py:111-140`). Dropping it from the envelope would force the leg-5 UI banner to either render `status`-only (no operator-meaningful summary) or pull the summary from `details` (no contract guaranteeing a one-sentence summary key exists). Including `message` keeps the envelope a 1:1 mirror of `DoctorReport`'s public surface and lets the banner render `message` as the LED-adjacent one-sentence summary with `details` as the labeled k/v block underneath.
- **Scope**: response envelope only — flight Design Decision otherwise stands (no in-flight override body; unknown type → 200 with `{status: "error", ...}`; no catch-all `except Exception:`).
- **Forward propagation**: leg 5's frontend will read `message` for the banner text. Future connector plugins that override `doctor()` must set a meaningful `message` (the stub returns `"stub probe ok"` by default).

### 2026-05-17 — Leg 4: unknown-type envelope uses `account.type` verbatim, not `ConnectorRegistrationError` structured fields

- The unknown-connector-type branch builds its operator-facing `message` from `account.type` directly (`f"Unknown connector type: {account.type}"`) rather than from `ConnectorRegistrationError.reason` (which reads `"not registered"` per the registry's raise site).
- **Why**: `ConnectorRegistrationError.__str__` formats `"Connector type {type_name!r} registration failed: {reason}"` — "registration failed" is implementation-detail noise from the operator's perspective. They configured the `type`; surfacing it back verbatim is the clearest contract.
- The exception's `type_name` and `reason` are still on the exception object for any future logging that wants the structured shape; the route just doesn't route them into the response envelope.

### 2026-05-17 — Leg 5: minimal placeholder editor file shipped one leg early

- Per the leg-5 leg artifact's Objective + Context blocks: the full editor (Connection, Credentials, Lifecycle, Test Connection, Danger Zone) lands in leg 6, but leg 5 also ships a ~35-LoC placeholder `connector-account-editor.js` that mounts only a back-button-equivalent (a Cancel button), a title ("New Connector Account" / "Edit Connector Account"), and a `data-testid="connector-account-editor-placeholder"` anchor. Leg 6 replaces the file wholesale.
- **Why**: the routing test ("New button opens form → Cancel returns to empty state") needs SOME mountable editor to exercise the routing round-trip. Either the test waits for leg 6 (couples routing-bug detection to editor-shape detection — masks which surface a future regression came from), or leg 5 ships throwaway code (35 LoC) to decouple them. We chose the latter — pinning the routing contract immediately gives a faster MTTR for any leg-6 editor-side regression that breaks routing.
- **Forward propagation**: leg 6 deletes this file's content and rewrites it. The placeholder's `data-testid="connector-account-editor-placeholder"` anchor is consumed only by the leg-5 routing test (`test_studio_direct_load_connector_accounts_new_renders_placeholder_editor` + the round-trip test); leg 6's tests will assert the real editor's contract (form fields, save button, etc.) and can rename / drop the placeholder testid.

---

## Leg Progress

### pre-leg-maintenance-from-f1
**Status**: landed
**Started**: 2026-05-17
**Completed**: 2026-05-17

#### Changes Made

Five Flight 1 debrief carry-forward items bundled into a single behaviour-preserving + documentation leg:

1. **Fernet helper lift** (`the_one/db/repositories.py`): added two module-level free functions `_encrypt_secrets_blob(encryptor, secrets) -> str` and `_decrypt_secrets_blob(encryptor, ciphertext) -> dict[str, Any]` near the top of the module (just after `_now_iso`), with the migration-residue `InvalidToken → {}` and `JSONDecodeError propagates` semantics preserved verbatim from the prior method bodies. Both `MCPSourceRepository._secrets_to_ciphertext` / `_ciphertext_to_secrets` and `ConnectorAccountRepository._secrets_to_ciphertext` / `_ciphertext_to_secrets` reduced to one-line delegators (docstring now just says "Delegates to `_encrypt_secrets_blob`" / "Delegates to `_decrypt_secrets_blob`"). The `__MASKED__` API-edge comment on `ConnectorAccountRepository` was preserved verbatim. Net diff: -36 / +44 LoC in `repositories.py`. Comment-only references at `interfaces/web/api.py:2784` and `tests/test_provider_api.py:950` were left as-is (they reference the method names, which still exist as delegators).

2. **`function-local-import-to-break-load-cycle` convention** (`the_one/agents.md`): appended a new `### `function-local-import-to-break-load-cycle`` subsection at the end of "Project Conventions" (after `landmark-elements-over-aria-roles`, before the `---` separator). 3-sentence explanation + 2 citations (`db/repositories.py: MCPSourceRepository.find_by_runtime_package` + `connectors/_pool.py: _load_account`) + a one-line "Pattern is at the 2-occurrence threshold pending a clearer 3rd documented occurrence" note explaining why `mcp/_pool.py` is not cited (no inline comment documenting the cycle motivation; `mcp/_pool.py` already imports `repositories` at top level cleanly). Matches the design-review outcome captured in the leg's Citation Audit.

3. **Connector-type checklist items 4 + 6 patch** (`the_one/agents.md`): item 4 rewritten to reflect v14 (F1 L2 `name`) → v15 (F2 L1 `idle_timeout_seconds`) → v16 (Flight 8 CHECK migration via the table-rename ceremony). Item 6 rewritten from `interfaces/web/static/js/areas/admin.js` to `static/js/areas/studio/connector-accounts-grid.js` + `studio/connector-account-editor.js` + integration in `static/js/areas/studio.js`, with the "Admin only if a future surface needs it" note appended. The `admin.js` reference in the LLM Provider checklist (item 6 of the parallel section) is untouched — that's a different section.

4. **`connectors/README.md` §3 skeleton plugin** (`the_one/connectors/README.md`): inserted a `### Skeleton for a real plugin` subsection after the existing §3 prose and before §4 ("Test seams"). ~60 LoC fenced Python code block defining `HypotheticalPlatformPlugin` — no inheritance per `structural-Protocol-satisfaction`, implements all 4 `ConnectorPlugin` methods, returns a `DoctorReport(status='ok'|'error', details={...})` from `doctor()`, constructs `SessionKey` with the `platform` field included (verified against `connectors/base.py:104-108`), uses canonical-import paths from `the_one.connectors.base`. Imports are exactly the symbols the body uses: `ConnectorClient`, `DoctorReport`, `InboundEnvelope`, `SessionKey`, `ConnectorAccount`, `Encryptor`. `# pseudo-code — replace with real SDK call` comments at every platform-SDK touchpoint instead of `# type: ignore` pragmas (keeps lint quiet without leaking ignore-noise). The block does not mention Discord or Slack by name.

5. **F1 flight.md leg-6 bullet patch** (`missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md:175`): replaced the stale "wired into `app.py` only in Flight 2" phrase with "wired into `app.py` in this flight's leg 6 (FastAPI lifespan shutdown invokes `shutdown_drain` AFTER the MCP pool drain and BEFORE the OAuth periodic-sweep stop)." — anyone reading F1's spec now sees the as-shipped reality.

#### Test Results

- **Scoped tests** (lift regression net): `tests/test_db_repositories.py tests/test_connectors.py tests/test_connectors_pool.py tests/test_connectors_e2e.py` — 118 passed, byte-identical to the pre-lift baseline. No test code touched.
- **Full suite** (`make test`): 1774 passed, 4 skipped, 375 deselected, 2 warnings in 99.58s. Pass count matches the F1 baseline noted in the flight.md verification section ("the F1 baseline of 1774 unit tests"). 2 warnings are the carry-forward AsyncMock-never-awaited pair on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` (M07-era maintenance backlog; out of Flight 2 scope per the Reconnaissance Report).
- **`make lint`**: clean — no new findings introduced by the lift or the documentation edits.

#### Notes

- The lift's design constraint ("method-on-repository surface kept stable") meant retaining the 4 method definitions even though each is now a one-line delegator. This is belt-and-suspenders against any test that might mock `repo._secrets_to_ciphertext` directly; the design-time consumer audit confirmed no such mocks exist on this branch but the small extra LoC is cheap insurance.
- The 2-citation outcome on the `function-local-import-to-break-load-cycle` convention is the recommended path per the design review captured in the leg artifact's Citation Audit. Surfacing a 3rd documented occurrence (with an inline `# Local import to avoid circular …` comment naming the cycle) would let a future leg upgrade the citation count without restructuring the convention's prose.
- All five items were verifiable by `grep` / scoped test runs / inline diff — the documentation-only items (2, 3, 4, 5) needed no test net beyond `make lint`.
- The leg artifact's claim that the helper lift is "behaviour-preserving" was confirmed empirically: identical pass count on the same test set before and after.

---

### idle-ttl-field
**Status**: landed
**Started**: 2026-05-17
**Completed**: 2026-05-17

#### Changes Made

Per-account `idle_timeout_seconds` field landed across the persistence and pool layers, with the schema-version renumber bookkeeping carried through every site the planning audit named:

1. **v15 schema migration** (`the_one/db/schema.py`): `CURRENT_VERSION` bumped 14 → 15. New `if version < 15:` block appended after the v14 block — `ALTER TABLE connector_accounts ADD COLUMN idle_timeout_seconds INTEGER NULL` guarded by a `PRAGMA table_info` existence check, idempotency via `INSERT OR IGNORE INTO schema_version` ordered LAST before the commit. Mirrors the v11/v14 ALTER ADD COLUMN pattern.

2. **`_connector_types.py` docstring** renumbered: v14 → `name` (F1 L2); v15 → `idle_timeout_seconds` (F2 L2); v16 → Flight 8's CHECK constraint via the table-rename ceremony. The single sentence in the existing docstring carried all three references.

3. **`ConnectorAccount.idle_timeout_seconds`** (`the_one/db/models.py`): added `int | None = None` between `secrets` and `created_at`, with a Pydantic v2 `@field_validator("idle_timeout_seconds")` that returns `value` unchanged for `None`, otherwise enforces `1 <= value <= 604800` and raises `ValueError("idle_timeout_seconds must be between 1 and 604800 seconds (7 days)")`. `field_validator` was already imported alongside `BaseModel, Field` at the top of `models.py` (used by `LLMProviderConfig._normalize_api_key`); no new imports needed.

4. **Repository round-trip** (`the_one/db/repositories.py`): `ConnectorAccountRepository.create` INSERT extended with `idle_timeout_seconds` (8 columns, 8 `?` placeholders, value taken from `account.idle_timeout_seconds`). `update` SET clause extended with `idle_timeout_seconds=?` before `updated_at=?` for visual consistency. `_row_to_model` reads `row["idle_timeout_seconds"]` — SQLite's NULL maps to Python `None` which matches the Pydantic default for legacy v14 rows.

5. **`_resolve_ttl_seconds` signature change** (`the_one/connectors/_pool.py`): new signature `_resolve_ttl_seconds(override: int | None = None) -> int`. Resolution order: explicit override (if not None) → env var `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` (read at call time so test monkeypatching works) → `_DEFAULT_TTL_SECONDS` (1800). Docstring updated to document the override semantics and the precedence contract. `live-read-across-lazy-resolver-boundary` invariant preserved — env-var read still happens inside the function body.

6. **`acquire()` wiring** (`the_one/connectors/_pool.py`): the `_RegistryEntry(ttl_seconds=...)` construction now passes `_resolve_ttl_seconds(override=account.idle_timeout_seconds)`. `account` is in scope from the `_load_account` call earlier in the function.

7. **Schema-version renumber bookkeeping**:
   - `tests/test_db_migration.py` assertion (L228–231): `CURRENT_VERSION == 15` with message rewritten to reference the F2 L2 `connector_accounts.idle_timeout_seconds` v15 migration. The leading comment expanded to enumerate v11–v15 surfaces.
   - `tests/test_db_migration.py` `TestSchemaV14` class docstring (L1230–1243): "renumbers to v15" → "renumbers to v16 (v15 is claimed by flight 02 leg 02's `idle_timeout_seconds` ALTER)."
   - `tests/test_db_migration.py::TestSchemaV13::test_v13_connector_accounts_has_expected_columns_and_no_check_constraint` — the expected-columns set assertion added `idle_timeout_seconds` and the docstring was updated to enumerate the v14 (`name`) + v15 (`idle_timeout_seconds`) post-`ensure_schema` additions plus the v16 deferral for the CHECK constraint. **Not on the leg-artifact list**: caught at first scoped-test run; the test pins the post-`ensure_schema` shape of `connector_accounts`, so any new column lands here too. Out-of-band update logged in this leg's flight-log entry; see Deviations note below.

8. **New tests** (all green):
   - `tests/test_db_migration.py::TestSchemaV15` (3 tests): fresh-DB column-shape, idempotency-on-rerun, legacy-v14-row decodes with `None`. The legacy-v14 test hand-builds a v14-shape `connector_accounts` table (including the v14-added `name` column), seeds a row, runs `ensure_schema`, and asserts `idle_timeout_seconds IS NULL` on the seeded row. Modeled on `TestSchemaV14.test_v14_preserves_v13_seeded_row_with_empty_name`.
   - `tests/test_connectors_pool.py` (3 new tests): `test_resolve_ttl_seconds_override_beats_env`, `test_resolve_ttl_seconds_override_beats_default`, `test_resolve_ttl_seconds_none_override_falls_through`. Existing 4 `_resolve_ttl_seconds` tests remain green — the no-arg call resolves identically to `override=None`.
   - `tests/test_db_repositories.py::TestConnectorAccountRepository` (5 new tests): `test_idle_timeout_seconds_round_trips_real_value`, `test_idle_timeout_seconds_round_trips_none`, three validator tests pinning the bounds (rejects 0, rejects 604801, accepts {1, 604800, None}). All existing 8 connector-repo tests stay green — `idle_timeout_seconds` defaults to `None` for fixtures that don't set it.

#### Test Results

- **Scoped tests** (`tests/test_db_migration.py tests/test_connectors_pool.py tests/test_db_repositories.py`): 126 passed in 12.49s. Delta from pre-leg: +11 tests (3 TestSchemaV15 + 3 resolver-override + 5 repository round-trip / validator).
- **Full suite** (`make test`): **1785 passed**, 4 skipped, 375 deselected, 2 warnings in 100.36s. Delta from F2 L1 baseline of 1774: **+11 tests**, matches the leg artifact's "+8 to +12 expected" envelope.
- **`make lint`**: clean — no new findings.
- The 2 warnings are the carry-forward AsyncMock-never-awaited pair on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` (M07-era maintenance backlog; out of Flight 2 scope per the Reconnaissance Report).

#### Deviations

- **Out-of-band patch to `TestSchemaV13::test_v13_connector_accounts_has_expected_columns_and_no_check_constraint`**: the leg artifact's "Files Affected" list named `tests/test_db_migration.py` for the L228 assertion + the L1230 `TestSchemaV14` docstring + the new `TestSchemaV15` class, but did NOT call out the `TestSchemaV13` column-shape assertion. That test pins the post-`ensure_schema` column set, which now includes `idle_timeout_seconds` because `ensure_schema` runs all the way to v15. The fix was mechanical (add the column to the expected set, expand the docstring to enumerate the v14/v15 additions and the v16 CHECK deferral). Surfaced on the first scoped test-run; no behaviour change implied. Same pattern as the F1 L2 v14 renumber: assertions that pin the column set of `connector_accounts` need to track every column ALTER, and the v15 ALTER landed against that shape. Worth lifting into the per-leg planning audit checklist for the next leg that adds a column.

#### Notes

- The architect-refined resolver shape (`override: int | None`) paid off here: `acquire()` reads `account.idle_timeout_seconds` directly and the pool layer stays ignorant of the field name. Any future flight that wants to swap the source of the override (e.g. an agent-level override) only edits the call site at `acquire()`, not the resolver signature.
- The validator's error message format ("between 1 and 604800 seconds (7 days)") was verified by the three validator tests' `assert "between 1 and 604800" in str(exc_info.value)` — a search-for-substring check rather than an exact-string check, so future copy edits to the message don't require synchronized test updates as long as the bounds stay numerically the same.
- `tests/test_connectors_pool.py::_make_stub_account` was NOT touched — it constructs `ConnectorAccount` without `idle_timeout_seconds`, which now defaults to `None`, which the resolver short-circuits past. All existing pool tests stay byte-identically green (verified empirically by the +11 delta on a 1785 total).
- `the_one.mcp._pool._resolve_ttl_seconds` was intentionally NOT touched: it's a separate subsystem with no per-source TTL field today; touching it would be scope creep per the leg artifact's Edge Cases section.
- `model_json_schema` not asserted-against anywhere in the test suite (grep clean), so the field-ordering placement between `secrets` and `created_at` did not require a schema-pin test update.

---

### rest-crud-and-masked-sentinel
**Status**: landed
**Started**: 2026-05-17
**Completed**: 2026-05-17

#### Changes Made

Six REST routes plus two helpers and a new section header land in `the_one/interfaces/web/api.py`, matched by twelve tests in `tests/test_db_api.py::TestConnectorAccountAPI`. Six items broken out per the leg artifact's Implementation Guidance:

1. **Imports** (`api.py:24-37`): `ConnectorAccount` added to the `db.models` import block (alphabetically between `ChatSession` and `KBItem`); `ConnectorAccountRepository` added to the `db.repositories` import block (alphabetically between `ChatSessionRepository` and `KBItemRepository`). The multi-line import for `db.models` was reflowed from single-line to one-per-line to keep ruff happy with the added entry; visual mirror of the existing `db.repositories` multi-line block.

2. **`_connector_repo()` helper** (`api.py:72-75`): placed immediately after `_mcp_repo()` per the leg's "visually grouped with `_mcp_repo`" guidance. Three-line implementation — get connection, get encryptor from `settings.data_dir`, return the repository.

3. **`_connector_account_response(account)` helper** (`api.py:2087-2104`): placed at the top of the new Connector Accounts section. Two-line body (`model_dump` + overwrite `secrets` with `_mask_secrets(...)`). NO `_OAUTH_MANAGED_SECRET_KEYS` strip, NO `_cache` block, NO `oauth_active` / `has_access_token` flags. Docstring carries the leg's "INVARIANT" comment naming `test_list_returns_masked_secrets` as the regression net.

4. **Section header** (`api.py:2084`): `# ── Connector Accounts ────────────────────────────────────────────────────` placed between the MCP-related routes (terminus is the OAuth `oauth_start` route's `_drive_flow` task at api.py:2078-2081) and the existing `# ── Chat Sessions` section (now at api.py:2274). Section dividers (not line numbers) were the anchor per the leg's Edge Cases note — the cited line numbers had drifted slightly since the leg artifact was written.

5. **Six routes** (`api.py:2107-2266`), in registration order so `/types` matches before `/{account_id}`:
   - **`GET /api/connector-accounts`** → list, masked response per row.
   - **`GET /api/connector-accounts/types`** → `[{value, label}]` from `the_one.connectors.registry.types()`. Function-local import of `types as _connector_types`. Empty list in production; `[{"value": "stub", "label": "Stub"}]` once `register_for_test("stub", StubPlugin)` runs. Docstring carries the MCP-style NOTE about registration-order vs `/{account_id}`.
   - **`GET /api/connector-accounts/{account_id}`** → get-by-id; 404 on `KeyError`.
   - **`POST /api/connector-accounts`** (`status_code=201`) → mints `data["id"] = uuid.uuid4().hex[:12]` if not provided; `ConnectorAccount.model_validate(data)` (422 on `ValidationError` with `include_context=False`); `repo.create(account)`; returns masked response. Inline comment notes the deliberate deferral of per-type `config`-shape validation to Flights 8 / 9.
   - **`PUT /api/connector-accounts/{account_id}`** → load existing (404 on miss) → per-key `__MASKED__` resolution (verbatim mirror of api.py:910-926 minus the OAuth + `_cache` blocks) → `model_copy(update=data)` → `repo.update(updated)` → eviction call if `existing.secrets != resolved_secrets`. **`resolved_secrets` is initialized OUTSIDE the if-branch** to `existing.secrets` so the post-update eviction check works uniformly when the operator omits the `secrets` field entirely (intent: "I only changed the name, don't touch credentials" → no eviction). This is the documented deliberate divergence from MCP precedent; an inline block-comment names it as such for future readers. `_evict_all_for_account` imported function-local per the F2-L1-codified `function-local-import-to-break-load-cycle` convention; the comment block at the import site names the cycle.
   - **`DELETE /api/connector-accounts/{account_id}`** → load existing (404 if missing) → `_evict_all_for_account` BEFORE `repo.delete` → returns `{"status": "ok"}`. The race-handled second 404 mirrors MCP's pattern — if another caller deleted between our `get` and `delete`, the inner `KeyError` re-raises as 404 with the same detail string. Docstring notes the deferred Flight-4 per-agent-reference-check.

6. **Twelve tests** (`tests/test_db_api.py:470-786`) in a new `class TestConnectorAccountAPI` placed AFTER `TestMCPSourceAPI` and BEFORE `TestChatSessionAPI`. Order matches the leg artifact's Outputs list: `test_crud_round_trip`, `test_list_returns_masked_secrets`, `test_put_masked_sentinel_preserves_secret`, `test_no_op_put_does_not_evict`, `test_dropping_a_key_evicts`, `test_secrets_change_evicts`, `test_adding_a_new_key_evicts`, `test_delete_evicts_then_deletes`, `test_types_returns_empty_in_production`, `test_types_returns_registered_in_test`, `test_create_with_invalid_payload_returns_422`, `test_unknown_account_returns_404`.

   The class's autouse `_isolation` fixture resets the pool, restores the registry baseline, calls `StubPlugin.reset_for_test()`, and pre-registers `"stub" → StubPlugin` so the eviction tests can `acquire("test-agent", account_id)` directly. Test cleanup re-clears the pool and the registry.

   **One deviation from the leg artifact's fixture skeleton** (see Deviations below) was forced by the realisation that the production `_load_account` runs through a function-local `from the_one.db.connection import get_connection` — bypassing the `client` fixture's `patch("the_one.interfaces.web.api.get_connection")` — so a `monkeypatch.setattr(pool_mod, "_load_account", _patched)` extension was added to the `_isolation` fixture, routing through the API-side patched `get_connection` + `get_encryptor`.

#### Test Results

- **Scoped tests** (`tests/test_db_api.py::TestConnectorAccountAPI`): 12 passed in 2.24s.
- **Full file** (`tests/test_db_api.py`): 42 passed in 6.98s — no regression on existing MCP / agent / KB / chat-session API tests.
- **Full suite** (`make test`): **1797 passed**, 4 skipped, 375 deselected, 2 warnings in 102.05s. Delta from F2 L2 baseline of 1785: **+12 tests**, exactly matching the 12 added connector-account-API tests.
- **`make lint`**: clean — no new findings.
- The 2 warnings are the carry-forward AsyncMock-never-awaited pair on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` (M07-era maintenance backlog; out of Flight 2 scope per the Reconnaissance Report).

#### Deviations

- **Autouse fixture extension**: the leg artifact's Implementation Step 12 skeleton called for the fixture to reset pool state, restore the registry, reset `StubPlugin` class-state, and pre-register the stub. First scoped-test run failed with `KeyError: 'Connector account not found: ...'` inside `acquire(...)` because the pool's `_load_account` calls a function-local `from the_one.db.connection import get_connection` — which is the production singleton, NOT the `client` fixture's `patch("the_one.interfaces.web.api.get_connection", return_value=conn)`. The patch targets the api module's binding only; the pool's binding resolves independently at call time. Fix: extended `_isolation` to also `monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)`, where the patched function builds a `ConnectorAccountRepository` against the api-side patched `get_connection()` and `get_encryptor()` (re-imported live inside the closure so the `with patch(...)` overrides are honored). The `_isolation` fixture takes `client` as a dependency so the `with patch(...)` context managers inside the `client` fixture are guaranteed to be active when the closure resolves the patched symbols. Documented inline. Mirrors the same fixture extension `tests/test_connectors_pool.py::patch_plugin` ships at L139-142, just routing through the API-side patched globals instead of constructing a fresh in-memory account.
- Out-of-band fixture change is the kind of thing the leg artifact's Edge Case ("Test-isolation: pool state across tests — verified live: ... module-local and does NOT propagate") flagged at a higher level; the artifact named the state-reset shape but did not enumerate the `_load_account` binding issue. Same scope-of-discovery pattern as F2 L2's out-of-band patch to `TestSchemaV13::test_v13_connector_accounts_has_expected_columns_and_no_check_constraint` — a missing test-fixture detail surfaced on first scoped-test run.

#### Notes

- The deliberate divergence from MCP — initializing `resolved_secrets` to `existing.secrets` OUTSIDE the if-branch — is the right shape because the eviction check fires unconditionally post-update. MCP scopes `resolved_secrets` inside the if-branch because it has no post-update eviction step; if we mirrored MCP verbatim, the eviction check would crash with `NameError` whenever the operator omitted the `secrets` field entirely. The inline block-comment names this as deliberate.
- `_mask_secrets` and `_MASKED_API_KEY_SENTINEL` are both defined LATER in `api.py` than the `_connector_account_response` helper and the `update_connector_account` body that reference them. Per the leg artifact's "Key learnings" note, Python resolves module-level names at call time, not definition time — the forward references work without a hoist. Confirmed by the green test run.
- No `config`-shape validation lands this leg (the F1 stub plugin accepts arbitrary config). The POST handler carries an inline comment noting the Flight 8 / 9 deferral so future readers don't conclude it was forgotten.
- The `idle_timeout_seconds` field round-trips transparently — the F2 L2 work shipped the model field, the repository round-trip, and the pool wiring; this leg's `_connector_account_response` just does `model_dump()` which includes the field unconditionally. The `test_crud_round_trip` test pins this (`assert resp.json()["idle_timeout_seconds"] == 600` after POST and GET).
- `_validate_idle_timeout_seconds` runs at `ConnectorAccount.model_validate` time inside POST, so an out-of-range `idle_timeout_seconds` in the create payload returns 422 with the F2-L2 bounds-message — no extra leg-3 plumbing needed. Not explicitly tested at the API level here (the F2 L2 test suite already pins the validator at the model level); a future leg can add an API-level pin if useful.
- `test_create_with_invalid_payload_returns_422` exercises the Pydantic error path; the detail-list shape (`list[dict]` with `loc` tuples) is the canonical FastAPI / Pydantic v2 422 shape, so the assertion is `isinstance(detail, list)` plus a `loc`-tuple membership check.

---

### rest-doctor-and-rotation-eviction
**Status**: landed
**Started**: 2026-05-17
**Completed**: 2026-05-17

#### Changes Made

Two intertwined deliverables — the operator-facing doctor-probe REST endpoint and the rotation eviction wiring that closes the F1-debrief carry-forward — plus the `StubPlugin.doctor_should_raise` knob that the failure-injection test depends on.

1. **`POST /api/connector-accounts/{account_id}/test/connect`** (`the_one/interfaces/web/api.py:test_connector_connection`): added immediately after `delete_connector_account` (preserves the CRUD-then-action ordering MCP's `/test/connect` follows). Signature `(account_id: str)` — NO request body parameter (Flight 2 Design Decision: no in-flight override). Body:
   - Function-local import of `ConnectorClientError`, `ConnectorRegistrationError`, and `registry.resolve` (per the F2-L1-codified `function-local-import-to-break-load-cycle` convention).
   - `repo.get(account_id)` → 404 `f"Connector account not found: {account_id}"` on `KeyError`.
   - `registry.resolve(account.type)` → `{status: "error", message: f"Unknown connector type: {account.type}", details: {error: "type not registered", type: account.type}}` (HTTP 200) on `ConnectorRegistrationError`. The unknown-type envelope uses `account.type` verbatim rather than the exception's structured fields (logged as a Design Adjustment).
   - `plugin.doctor(account, get_encryptor(settings.data_dir))` inside `try/except ConnectorClientError` → wrapped 200 envelope `{status: "error", message: str(e) or type(e).__name__, details: {error: str(e), exception_type: type(e).__name__}}` on `ConnectorClientError`.
   - Success: `{status: report.status, message: report.message, details: report.details}` (HTTP 200).
   - **NO catch-all `except Exception:`** — deliberate divergence from MCP's `test_mcp_connection` (which catches `Exception` to swallow stdio-teardown `CancelledError` leaks). Connectors have no analogous transient; an escaping plain `Exception` is a plugin contract violation and SHOULD surface as 500.

2. **Rotation eviction wiring** (`the_one/interfaces/web/api.py:rotate_encryption_key`): added a new `# 4b.` block AFTER `await conn.commit()` and BEFORE the on-disk key replace at step 5. The block lives OUTSIDE the existing commit `try/except` (Flight 2 Design Decision: failing eviction must NOT abort the on-disk key write, because the DB is already in the new-key state and skipping the on-disk replace would leave the DB unreadable on next restart). Iterates `decrypted_connectors` (built at step 1 of rotation), calling `_evict_all_for_account(aid)` per account inside a narrow `try/except Exception:` that logs-and-continues. Function-local imports for `_evict_all_for_account` and `logging` per the convention.

3. **`StubPlugin.doctor_should_raise: ClassVar[BaseException | None]` knob** (`the_one/connectors/_stub.py`): added alongside the existing `connect_should_fail` scenario knob. When set, `doctor()` raises it INSTEAD of returning a `DoctorReport`. `reset_for_test()` extended to clear it. The `doctor()` method body checks `doctor_should_raise` BEFORE `doctor_response` so the raise path wins if both are set (test seam clarity). Mandatory for `test_doctor_probe_connector_client_error`.

4. **Eight new tests** (`tests/test_db_api.py`):
   - **`TestConnectorAccountDoctor`** (new class, ~140 LoC including the redeclared `_isolation` autouse fixture verbatim per the leg artifact). 7 tests: `test_doctor_probe_success`, `test_doctor_probe_configured_failure`, `test_doctor_probe_degraded_status`, `test_doctor_probe_unknown_type`, `test_doctor_probe_connector_client_error`, `test_doctor_probe_unknown_account_returns_404`, `test_doctor_probe_records_the_call`.
   - **`test_rotation_evicts_warm_pool_entries`** placed INSIDE `TestConnectorAccountAPI` (NOT a new class). The test calls `acquire("test-agent", account_id)` which depends on the existing class's `_isolation` fixture's `_load_account` monkeypatch — pinning the test inside the class reuses the fixture cleanly. A `# ── Rotation eviction (F2 L4) ──` section header inside the class delimits it.

#### Test Results

- **Scoped tests**:
  - `tests/test_db_api.py::TestConnectorAccountDoctor` — 7 passed in 1.29s.
  - `tests/test_db_api.py::TestConnectorAccountAPI` (13 tests including the new rotation test) — green.
  - `tests/test_provider_api.py` (124 tests, includes 10 existing rotation tests) — all green; the new eviction loop is a no-op when `decrypted_connectors` is empty.
- **Full suite** (`make test`): **1805 passed**, 4 skipped, 375 deselected, 2 warnings in 104.66s. Delta from F2 L3 baseline of 1797: **+8 tests**, exactly matching the leg artifact's expected delta (7 doctor + 1 rotation).
- **`make lint`**: clean — no new findings.
- The 2 warnings remain the carry-forward AsyncMock-never-awaited pair on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` (M07-era maintenance backlog).

#### Notes

- The `_isolation` fixture in `TestConnectorAccountDoctor` is a verbatim copy of the one in `TestConnectorAccountAPI`. Class-scoped autouse fixtures don't propagate across classes — the leg artifact called this out explicitly. The doctor-probe tests don't actually call `acquire(...)` (so technically only the registry + StubPlugin reset are needed), but mirroring the F2 L3 fixture keeps the class shape consistent and protects against future doctor tests that DO touch the pool.
- The rotation test asserts eviction transitively: after `POST /api/encryption/rotate`, the original `("test-agent", account_id)` pool key is gone (eviction fired), and a fresh `acquire` re-seeds it. The "decrypts under the new key" assertion is implicit — `acquire` calls `_load_account` which reads the row (encrypted under the new key, written in step 4 of rotation) via the live encryptor (whose `install_key` fired in step 7). A failure on either side would surface as `KeyError` or `InvalidToken` from `acquire`, blocking the final `assert key in pool_mod._pool`.
- The inter-commit-and-install-key race (the window between rotation's `commit()` at step 4 and `install_key` at step 7, during which a concurrent `acquire` could read a new-key row and try to decrypt with the old in-memory encryptor) is NOT addressed by this leg's eviction wiring. The eviction loop closes the post-`install_key` staleness window, not the inter-step race. Pre-F1-debrief baseline; documented in the leg artifact's Edge Cases section and the Decisions block below.
- `ConnectorRegistrationError` is a subclass of `ConnectorClientError`. The route's two-try-block ordering (catch `ConnectorRegistrationError` around `_resolve_plugin`, then catch `ConnectorClientError` around `plugin.doctor`) is deliberate — if `ConnectorRegistrationError` somehow leaked into the second block it would still be caught, but the response shape would be the generic exception envelope rather than the specific "unknown type" envelope. Leg artifact's Edge Cases notes "do not consolidate."

---

### frontend-grid-and-types
**Status**: landed
**Started**: 2026-05-17
**Completed**: 2026-05-17

#### Changes Made

Six file surfaces edited, all parallel to the existing MCP Sources studio block:

1. **New grid file** (`the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js`, 110 LoC): mirrors `mcp-servers-grid.js`. `KNOWN_CONNECTOR_BADGES = []` (empty allowlist in production — Flight 8 will register Discord). `renderConnectorAccountsGrid(container, accounts, callbacks)` exposes the same three branches: header + new-btn + grid skeleton, empty array → centered empty-canvas CTA with the production-empty copy ("No connector types registered yet — Flight 8 will add Discord."), populated array → tile markup. Tile DOM uses `entity-tile-meta` set to `—` (no transport-config equivalent yet; Flights 8/9 revisit). `data-testid` values: `new-connector-account-btn`, `new-connector-account-btn-empty`, `connector-account-card`. Empty-canvas's second copy line uses a new `empty-canvas-secondary` class (no CSS rule required — falls back to default flex spacing).

2. **New placeholder editor file** (`the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`, 35 LoC): mounts a title ("New Connector Account" / "Edit Connector Account"), a one-paragraph placeholder body ("Placeholder editor — full form lands in leg 6."), and a Cancel button that fires `callbacks.onCancel()`. Top-of-file comment explicitly names leg 6 as the wholesale-replacement landing point. `data-testid="connector-account-editor-placeholder"` on the container is the anchor the routing-round-trip test consumes.

3. **`static/index.html`**: two new `<script src>` tags placed alongside the existing `mcp-servers-grid.js` + `mcp-server-editor.js` pair, BEFORE `studio.js` (so `App.studio.renderConnectorAccountsGrid` / `renderConnectorAccountEditor` exist when `studio.js` runs).

4. **`static/js/areas/studio.js`** (~210 LoC added, structurally parallel to the MCP block):
   - `serializeState()`: new `connector-accounts` branch handling 4 URL forms (bare / `/new` / `/{id}` / pending-id race).
   - `hydrateState()`: parses `connector-accounts`, `connector-accounts/new`, `connector-accounts/{id}` into `pendingConnectorAccountId_local` / `pendingConnectorAccountFormMode_local`, mirrors the MCP block's structure exactly. Always overwrites `_pendingConnectorAccountId` / `_pendingConnectorAccountFormMode` so navigation away clears stale pending. Calls `tryConsumePendingConnectorAccount` unconditionally at the end (mirror of MCP).
   - Closure-locals + `Object.defineProperty` chain in `init()`: `CONNECTOR_TYPES`, `connectorTypesReady`, `connectorAccounts`, `connectorAccountFormMode`, `editingConnectorAccount`, `pendingConnectorAccountId`, `pendingConnectorAccountFormMode`. Four properties on `self` (`_connectorAccountFormMode`, `_editingConnectorAccount`, `_pendingConnectorAccountId`, `_pendingConnectorAccountFormMode`) mirror the MCP exposure pattern.
   - Section-nav array: appended `{ id: 'connector-accounts', label: 'Connector Accounts' }` as the fourth entry. URL slug matches `/api/connector-accounts` REST path; label matches the user-facing storage entity name (no MCP-style asymmetry).
   - `onSelect` confirm-leave block: new `connector-accounts` branch — clicking the same nav while the editor is mounted resets `connectorAccountFormMode` / `editingConnectorAccount` / `dirty`.
   - New functions (after the MCP block): `renderConnectorAccountsSection`, `fetchConnectorAccountTypes`, `fetchConnectorAccounts_`, `populateConnectorAccountsGrid`, `selectConnectorAccount`, `enterCreateConnectorAccountMode`, `findConnectorAccount`, `tryConsumePendingConnectorAccount`. All mirror their MCP equivalents. `self._tryConsumePendingConnectorAccount = tryConsumePendingConnectorAccount` exposes the consume helper for `hydrateState`.
   - `setActiveSection`'s leave-section reset: parallel `prevSection === 'connector-accounts' && section !== 'connector-accounts'` branch clears form-mode + editing state.
   - `setActiveSection`'s section dispatch: new `else if (section === 'connector-accounts') renderConnectorAccountsSection();` branch.

5. **New browser test file** (`tests/browser/test_flow_studio_connector_account_navigation.py`, 7 tests, ~115 LoC): `test_studio_section_nav_includes_connector_accounts`, `test_studio_section_nav_click_to_connector_accounts`, `test_studio_direct_load_connector_accounts`, `test_studio_direct_load_connector_accounts_new_renders_placeholder_editor`, `test_studio_refresh_preserves_connector_accounts_section`, `test_studio_connector_accounts_empty_grid_shows_cta` (asserts the "Flight 8 will add Discord" copy), `test_studio_connector_accounts_new_button_opens_form_then_cancel_returns_to_grid` (full round-trip: click empty-canvas CTA → URL `/new` + placeholder visible → click Cancel → URL bare + empty-canvas restored).

6. **Existing browser tests updated for the 4-section nav**:
   - `tests/browser/test_flow_studio_mcp_navigation.py::test_studio_section_nav_includes_mcp_servers` — count 3 → 4, labels list extended to 4 entries, docstring + module-level docstring updated.
   - `tests/browser/test_flow_studio_navigation.py::test_studio_section_nav_renders_three_buttons` — renamed to `_renders_four_buttons`, count 3 → 4, `nth(3)` "Connector Accounts" assertion added. Module-level docstring updated.
   - `tests/browser/test_flow_studio_navigation.py::test_studio_section_nav_roving_tabindex` — added `connector_btn` locator + `tabindex="-1"` assertion (this test was NOT on the leg artifact's "files to update" list but pinned the 3-button nav implicitly; surfaced on first scoped-test run).
   - `tests/browser/test_flow_studio_navigation.py::test_studio_keyboard_arrow_navigation` — every keyboard-nav assertion that landed on `mcp-sources` as the last entry updated to land on `connector-accounts`; the ArrowDown-from-mcp-sources step now lands on `connector-accounts` (no wrap) and a new ArrowDown step wraps `connector-accounts → agents`.

#### Test Results

- **Scoped tests** (`test_flow_studio_connector_account_navigation.py + test_flow_studio_mcp_navigation.py + test_flow_studio_navigation.py`): 24 passed in 24.75s (7 new + 6 MCP-nav with 1 updated + 11 studio-nav with 2 updated).
- **`make test-browser`** (canonical recipe): **323 passed, 35 skipped, 12 deselected in 267.88s**. Delta from baseline: +7 connector-account-navigation tests (the other test updates were in-place modifications, not additions). 35 skipped are pre-existing `test_studio_mcps_tab.py` skips (M07 F8 deferral); 12 deselected are the visual snapshot tests (pixel marker; gitignored baselines).
- **`make test`** (unit suite + deselected browser): **1805 passed**, 4 skipped, 382 deselected, 2 warnings in 105.75s. Pass count UNCHANGED from F2 L4's 1805 baseline — no unit-test regressions; browser tests are deselected by pyproject `addopts` and run via the `test-browser` target.
- **`make lint`**: clean after a 2-line docstring-length adjustment.
- The 2 warnings remain the carry-forward AsyncMock-never-awaited pair on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` (M07-era maintenance backlog).

#### Deviations

- **Out-of-band update to `test_studio_section_nav_roving_tabindex`**: the leg artifact named two test files for the 3-section-nav update (`test_flow_studio_mcp_navigation.py` and `test_flow_studio_navigation.py`'s `_renders_three_buttons` + the L140-170 keyboard block). The artifact's pre-implementation grep (`to_have_count(3)\|"MCP Servers"]`) did NOT catch `test_studio_section_nav_roving_tabindex` because that test doesn't use either pattern — it enumerates section buttons by `data-section` attribute. The roving-tabindex assertions for the 3 sections still pass byte-identically; the new 4th section (`connector-accounts`) just needs its own `tabindex="-1"` assertion added. Surfaced on the first scoped-test run as a passing-but-incomplete test (the test green-lit before the addition because it didn't assert exhaustively; the addition was for symmetry, not to fix a failure). Documented inline.
- **`make rebuild` required before `make test-browser`**: the Dockerfile bakes JS/CSS into the image, so the new `.js` files and the modified `studio.js` are not picked up by the running container until rebuild. Standard for any JS edit; called out so future readers know the recipe.

#### Notes

- The placeholder editor's `cancel` button is the only interactive element; click → `callbacks.onCancel()` → `studio.js` clears `connectorAccountFormMode` / `editingConnectorAccount`, calls `App.router.replaceSub('connector-accounts')`, and re-renders the section. The full editor's onBack / onSaveSuccess / onDeleteSuccess / onDirtyChange callbacks are wired in `renderConnectorAccountsSection` but unreachable from this placeholder (only Cancel is exposed). Leg 6 will exercise the rest.
- `KNOWN_CONNECTOR_BADGES = []` is the production reality: `/api/connector-accounts/types` returns `[]` (no plugins registered). The badge-class hook (`admin-connector-badge--{type}`) is present-as-future-hooks; no CSS rule needs to land in `admin.css` or `tokens.css` until Flight 8 introduces a real type that wants a distinct color (verified at design-review per the leg artifact's Edge Cases).
- The `empty-canvas-secondary` CSS class introduced in the empty-canvas copy block has no explicit CSS rule; the default flex column layout produces acceptable visual spacing. If a future flight wants a smaller / muted secondary line, a `.empty-canvas-secondary { font-size: 0.85em; color: var(--text-muted); }` rule can land in `components.css` without breaking this leg's tests (DOM-shape assertions only, no visual snapshot regression net).
- The 2 `to_have_count(3)` occurrences in `test_flow_picker.py:39` and `test_flow_admin_tools_grid.py:45` are unrelated (admin picker + tools-grid tabs); the grep also caught those but verification confirmed they pin separate UI surfaces that this leg does not modify. Not touched.

---

### frontend-editor-and-browser-tests
**Status**: landed
**Started**: 2026-05-17
**Completed**: 2026-05-17

#### Changes Made

The full Studio connector-account editor + the browser-flow tests + the
test-seam wiring that makes the stub plugin reachable from the spawned
uvicorn subprocesses.

1. **New editor file** (`the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`, **898 LoC**, wholesale replacement of leg-5's 34-LoC placeholder): IIFE + `'use strict'`; `MASKED_SENTINEL = '__MASKED__'`; module-level `_pendingProbeReport` hand-off variable for the create+test → edit-mode banner round-trip. Public entry `renderConnectorAccountEditor(container, account, types, callbacks)` renders six sections: editor-header (title + Back/Cancel/Save action cluster), Connection (name input + type select-or-readonly + config kv editor), Credentials (secrets kv with `data-original-masked` round-trip), Lifecycle (`idle_timeout_seconds` number input with placeholder "Use default (30 min)" + forward-compat note about the Flight 3 chat-session continuation field), Test Connection (edit-mode only: button + LED + status banner + labeled k/v details block at `data-testid="connector-test-details"`), Danger Zone (edit-mode only: confirm-delete via `App.confirmDelete`). Helper functions: `renderConnectionFields`, `renderConfigKvTable` / `renderSecretsKvTable` / `renderConfigRow` / `renderSecretRow`, `getFormSnapshot` for JSON-stringified dirty tracking, `handleSaveEdit` / `handleCreateAndTest` (the combined-action handler), `handleTestConnection`, `renderTestConnectionBanner` + `renderDetailsBlock` (the labeled k/v renderer that passes secret-shaped values through verbatim and JSON-stringifies non-string values in `font-mono`), `statusLedClass` mapping `ok→--success` / `degraded→--warning` / `failed/error→--danger` / default→`--idle`.

2. **`THE_ONE_REGISTER_STUB_CONNECTOR=1` test seam** (`the_one/interfaces/web/app.py` lifespan + `tests/browser/conftest.py` env injection): dev-mode-gated `register_for_test("stub", StubPlugin)` call inside the FastAPI lifespan. Production never sets the env var; browser-test conftest sets it for every `app_clean` / `_spawn_app` invocation so seeded `type="stub"` accounts can be probed via the registered plugin. Mirrors the precedent set by `THE_ONE_OPENROUTER_TEST_MODELS_JSON` (the only existing dev-mode subprocess test seam).

3. **`seed_connector_account` helper** (`tests/browser/seeders.py`): mirrors `seed_mock_provider`'s signature — `seed_connector_account(base_url, name="Test Account", type="stub", secrets=None, config=None, idle_timeout_seconds=None) -> str`. Wraps `httpx.post` to `/api/connector-accounts`, asserts 201, returns the new id.

4. **PUT validator fix** (`the_one/interfaces/web/api.py:update_connector_account`): `existing.model_copy(update=data)` does NOT re-run field validators in Pydantic v2, so `idle_timeout_seconds=0` PUTs were silently bypassing the F2 L2 bounds validator and storing 0 in the DB. Replaced with `ConnectorAccount.model_validate(existing.model_dump() | data)` so the validator fires on the merged payload and the canonical 422 surfaces to the operator. Drove this fix from the editor-test that asserts the canonical operator path; the MCP `model_copy` precedent has the same gap but is out of scope for this leg.

5. **`tests/browser/test_flow_studio_connector_account_editor.py` (12 tests, 283 LoC)**: create-mode renders all create-applicable sections + absent Test Connection / Danger Zone; edit-mode renders all six sections; type select populates from `/types`; Create & Test transitions to edit-mode + tile appears in grid; edit-with-unchanged-secret preserves via __MASKED__; edit-name-only preserves secrets; edit-change-a-secret writes new value; idle_timeout_seconds set to value; idle_timeout_seconds cleared persists null; idle_timeout_seconds=0 surfaces 422; delete via two-click confirm removes tile; Back-when-dirty surfaces `confirm-dialog-overlay`.

6. **`tests/browser/test_connector_test_connection_button.py` (7 tests, 223 LoC)**: button visible in edit-mode; absent in create-mode; default stub `ok` probe renders green LED + "(no additional details)"; `page.route()`-fulfilled `failed` renders red LED + details k/v; `degraded` renders amber LED; non-string detail values render inside `<code class="font-mono">`; secret-shaped details (starting with `***`) pass through verbatim.

7. **`tests/browser/test_flow_studio_connector_account_create_and_test.py` (3 tests, 157 LoC)**: create-ok + probe-ok lands in edit-mode with green banner (default stub doctor); create-ok + probe-failed (page.route-fulfilled) lands in edit-mode with red banner, account persisted; create-422 (via `idle_timeout_seconds=0` payload) blocks the probe — `page.on("request", ...)` capture asserts 0 calls to `/test/connect`.

8. **Leg-5 navigation-test updates** (`tests/browser/test_flow_studio_connector_account_navigation.py`): test 4 renamed `…_renders_placeholder_editor` → `…_renders_editor`; assertion swapped from `connector-account-editor-placeholder` to `connector-account-name-input` (the real-editor mount anchor). Test 7's "Cancel returns to grid" assertion replaced with the Back-button path because the new editor's Cancel button is disabled-until-dirty per the leg artifact contract (matches MCP precedent). Module docstring updated to reflect the leg-5-placeholder retirement.

#### Test Results

- **Scoped tests** (`docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_*.py tests/browser/test_connector_test_connection_button.py`): **29 passed in 33.95s** (12 editor + 7 navigation + 7 button + 3 create-and-test).
- **`make test-browser`**: **345 passed**, 35 skipped, 12 deselected in 295.21s. Delta from leg-5 baseline of 323: **+22 tests** (12 editor + 7 button + 3 create-and-test; navigation count was 7 in leg-5 and remains 7 with the in-place updates). Matches the leg artifact's "+21-23 expected" envelope.
- **`make test`**: **1805 passed**, 4 skipped, 404 deselected, 2 warnings in 106.69s. Pass count UNCHANGED from F2 L4's 1805 baseline — no unit regressions from the api.py PUT validator fix or any other backend touch.
- **`make lint`**: clean — no new findings.
- The 2 warnings remain the carry-forward AsyncMock-never-awaited pair on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` (M07-era maintenance backlog).

#### Deviations

- **Backend PUT validator gap surfaced + fixed**: the leg artifact called the `idle_timeout_seconds=0` test path "server-side 422 is canonical." The first run of that test revealed that the F2 L3 PUT handler uses `existing.model_copy(update=data)`, which in Pydantic v2 bypasses field validators — so the bound was silently storing 0. Fixed by switching to `model_validate(existing.model_dump() | data)` so the validator fires on the merged payload. Scope-appropriate: the test was the canonical operator path the leg artifact named, and the fix is a 3-line edit; not deferred. The MCP precedent at `update_mcp_source` has the same `model_copy` shape but is out of scope.
- **`THE_ONE_REGISTER_STUB_CONNECTOR=1` env var + lifespan hook**: leg artifact step 3 said "Investigate first" how the MCP precedent registers test plugins for browser tests, with explicit guidance that "this leg may need to add" a test-mode toggle. The investigation result: MCP transports are registered in production (`register_builtin_connectors` registers them at module-import time), so MCP browser tests don't need a test seam. Connectors register nothing in production, so we DO need one. Added the env-var + dev-mode-gated lifespan hook mirroring the precedent set by `THE_ONE_OPENROUTER_TEST_MODELS_JSON`.
- **Cancel button in test 7 of leg-5 navigation tests**: leg-5's placeholder editor enabled Cancel by default; the real editor disables Cancel until the form is dirty (matches MCP precedent). Switched test 7's assertion path from Cancel to the always-enabled Back button. The leg artifact's Implementation Guidance step 5 was explicit about using the real editor's selectors but didn't pre-call this specific cancel-button visibility shift; the behaviour change is intentional + matches the MCP editor.

#### Design-language screenshots

Five PNGs saved under `tests/browser/__snapshots__/connector-account-editor/` (gitignored, local-only):

- `create-form-empty.png` — fresh create form, no fields filled.
- `create-form-filled.png` — name + type + idle_timeout filled in.
- `edit-form.png` — edit-mode with masked-secret rows, idle_timeout pre-filled.
- `test-connection-success.png` — edit-mode + green LED banner + "(no additional details)".
- `test-connection-failure.png` — edit-mode + red LED banner + labeled k/v details block (`http_status=401`, `platform=discord`).

Capture script lived at `/tmp/capture_connector_screenshots*.py` inside the dev container; not committed (one-off generation per the soft-deliverable contract). Re-running requires the `THE_ONE_REGISTER_STUB_CONNECTOR=1` env-var seam. Human reviewer makes the go/no-go call on the design-language quality bar at flight-review time.

#### Notes

- The editor file lands at **898 LoC**, comfortably inside the 800-1100 target. The size discipline came from omitting MCP-specific concerns: no transport-fields visibility-toggle machinery, no sandbox section, no tools-list rendering, no OAuth popup-and-poll handler, no Reset-connection button. The Create & Test combined-action took ~80 LoC; the labeled k/v details renderer took ~30; the rest is the structural mirror of MCP's section layout.
- The `_pendingProbeReport` module-level hand-off pattern (from the leg artifact's Edge Cases) is the single cleanest path through the studio.js `onSaveSuccess(updated, true)` unmount-and-remount flow. No callback-contract change to studio.js, no DOM rescue, no closure-capture across editor identities. The variable is one-shot — set before `onSaveSuccess`, consumed + cleared by the next render-edit-mode pass.
- The Test Connection LED's `data-state` attribute is the canonical assertion handle for browser tests (`expect(led).to_have_attribute("data-state", "ok")`). The `class` attribute carries the `indicator-led--success` / `--warning` / `--danger` token but the same class set is reused across other indicator-LED sites in the codebase, so the `data-state` attribute is the connector-specific shape pin.
- No new CSS classes invented. The `.connector-test-section`, `.connector-test-actions`, `.connector-test-details-empty`, `.connector-test-details-list`, `.connector-account-editor` namespace-prefixed classes are present-as-future-hooks in case a M04/M06 follow-up wants connector-specific styling rules, but every visible style is inherited from the existing tokens (`field-input`, `field-select`, `editor-section`, `field-row`, `admin-pf-row`, `kv-value-secret`, `api-key-wrap`, `api-key-eye`, `indicator-led`, `indicator-led--success/--warning/--danger/--idle`, `btn-outlined-primary`, `btn-filled-primary`, `btn-muted-destructive`, `danger-zone`, `form-actions`, `editor-title`, `editor-subtitle`, `editor-error`, `kv-display`, `font-mono`, `form-hint`).
- The `make rebuild` step is REQUIRED after every JS edit because the Dockerfile bakes JS into the image (leg-5 implementer flagged this at L4 Deviations). Re-running browser tests without rebuild against an old image will silently exercise the prior editor file.

---

---

## Decisions

_(append runtime decisions not captured in the flight spec)_

### 2026-05-17 — Rotation inter-commit-and-install-key race acknowledged, not closed by L4 eviction

- Between the rotation transaction's `await conn.commit()` (step 4 / L3068) and the in-memory `encryptor.install_key(new_key)` (step 7 / L3089), a concurrent `acquire(...)` could read the DB row (now encrypted under the NEW key, written at step 4) and attempt to decrypt with the OLD in-memory encryptor still resident in the live `get_encryptor(...)` cache. Decryption would fail with `InvalidToken`.
- This is the pre-F1-debrief baseline. THIS leg (F2 L4) does NOT change it. The new eviction block lives at step 4b (between commit and on-disk key replace), and it closes the post-`install_key` staleness window only — warm entries that were cached BEFORE rotation must be evicted so the next acquire reloads under the new key.
- The inter-step race is a separate hardening item — it would require either holding `acquire(...)` callers behind a rotation lock (significant rework) or restructuring the rotation so the `install_key` happens before the commit (which would break the crash-safety contract that DB-and-disk-key stay in sync). Out of Flight 2 scope.
- Recorded so M10 mission debrief surfaces this alongside the other rotation invariants documented in F1 L6 + F2 L3 + F2 L4.

### 2026-05-17 — Eviction-on-TTL-change deferred to leg 3 design time

- Per the `idle-ttl-field` leg artifact's State-Machine Reachability Audit and Cache Freshness Contract: warm pool entries cache `ttl_seconds` at acquire time. An operator update of `ConnectorAccount.idle_timeout_seconds` after a warm entry exists does NOT update the warm entry's `ttl_seconds` — the new value applies on the NEXT `acquire` after eviction. Maximum staleness is bounded by the OLD TTL (worst case ~30 min on the default).
- Leg 3 (`rest-crud-and-masked-sentinel`) already calls `_evict_all_for_account` on PUT when secrets change. The open question is whether to extend that eviction trigger to also fire when `idle_timeout_seconds` changes. Resolving here would be premature — the PUT diff-detection logic lives in leg 3, and the natural place to decide "what counts as a material change" is alongside the secrets-change detection at leg-3 design time.
- Recorded so leg 3's design author picks this up explicitly rather than rediscovering it.

---

## Deviations

_(append departures from the planned approach)_

---

## Anomalies

_(append unexpected issues encountered)_

---

## Session Notes

_(chronological notes during execution)_
