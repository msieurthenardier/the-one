# Flight Log: Hierarchical Allowlist Axes + Snake_Case Identifier Rename (F11 prereq)

**Flight**: [Hierarchical Allowlist Axes + Snake_Case Identifier Rename](flight.md)

## Summary

Flight in-flight. F12 began execution on 2026-05-29 immediately after F11 merged to main (`e0a8491`) + F12 planning. Four legs: L1 snake-case-identifier-rename (F11 prereq closure), L2 acl-extraction-and-symmetric-paths-convention, L3 storage-shape-v24-migration-and-acl-semantics (large merged leg), L4 ui-discoverable-dropdown-and-per-peer-dm-toggle. Per agentic-workflow protocol, code review + commit deferred to Phase 2d.

---

## Flight Director Notes

### 2026-05-29 — Flight kickoff

- Loaded crew definitions from `.flightops/agent-crews/leg-execution.md` (Developer Sonnet / Reviewer Haiku / Accessibility Reviewer Sonnet). Defer-to-Phase-2d commit rule per `/agentic-workflow` skill.
- **State at kickoff**:
  - Main branch HEAD: `e0a8491` (F11 merge commit)
  - Backend baseline: 2749 passed / 4 skipped / 0 errors / ~254s wall (per F11 debrief test-metrics)
  - Branch created from main: `flight/12-hierarchical-allowlist-and-snake-case-rename`
  - Flight status `ready` → `in-flight`
- **Operator local-state callout (unchanged)**: `docker-compose.yml` carries uncommitted HAT env vars from M11 F7 L12. Developer agents instructed across all legs to stage files explicitly (no `git add .` / `-A`) so this stays out of F12 commits.
- **Architect cycles used at flight-design**: 2 (cycle-2 verdict READY pre-operator-clarification on DM model). Post-operator-clarification ("`dm_admission` STAYS + per-peer `dm_allowed` ADDS"), spec was patched in-place; no cycle-3 architect spawned because the change was direct operator scope-refinement, not unresolved-issue-persistence. Operator approved revised spec at Phase 6.
- **Pulled-forward F11 debrief methodology lessons** (see flight-log Reconnaissance Report section "Pulled-Forward F11 Debrief Methodology Lessons" — applied across all 4 legs).
- **Acceptance verification approach**: regression tests + 12-cell cross-product matrix (L3) + browser tests (L4). No standalone behavior-test spec authored.

---

## Reconnaissance Report

Per `/flight` Phase 1b. Source artifacts:
- F11 debrief at `flights/11-connector-rename-and-housekeeping/flight-debrief.md` (carry-forward Action Items)
- M11 mission outline F12 entry (`mission.md:126`)
- M11 Known Issues (`mission.md:107-115` "Hierarchical allowlist axes", "snake_case identifier rename residue", "aiosqlite event-loop-closed teardown warnings")

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Hierarchical allowlist axes (Servers ⊃ Channels ⊃ Users) | **confirmed-live (reshaped at planning)** | Mission outline + F10 L5 HAT Known Issue. **Operator reshaped at planning**: users stay GLOBAL (per-peer DM toggle); hierarchical is **Servers → Channels → Roles** (not → Users) | F12 core scope L3+L4+L5 |
| `_acl.py:admits_inbound` extraction into `_admits_inbound_dm` + `_admits_inbound_guild` | **confirmed-live** | Mission outline + F10 debrief tech section; `_acl.py` is 484 LOC with 5 axes | F12 L2 |
| Snake_case identifier rename (F11 prereq) | **confirmed-live** | F11 debrief Action Items + M11 Known Issue at `mission.md:111` | F12 L1 (atomic mechanical rename with explicit grep-gate per F11 methodology) |
| aiosqlite teardown warnings (F11 prereq) | **needs-human-recheck — F11 debrief overstated the fix path** | F11 debrief recommendation said "apply L3's fixture-redesign pattern". Verification at F12 planning: `test_db_migration.py` already uses `async def setup` fixture + inline `await aiosqlite.connect/close` per-test method (NOT the sync+run_until_complete pattern L3 fixed in `test_provider_repository.py`). Warnings come from aiosqlite's worker-thread teardown racing with pytest's event loop close — a library-internal quirk, not a fixture-design bug | Deferred to routine-maintenance; NOT folded into F12. Re-filed in flight log section below with corrected framing |
| 2 pre-existing browser test failures | **confirmed-live (since pre-F10)** | F11 debrief Action Items: `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` (expects 4 tabs, sees 5) + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` | Deferred to routine-maintenance; NOT F12 scope |

**Classification summary**: 3 confirmed-live items drive F12 scope (5 legs); 2 items deferred to routine-maintenance with corrected framing for one of them.

**Recon adjustments to source-artifact framing**:
- F11 debrief recommendation #4 ("apply L3 pattern to aiosqlite warnings in test_db_migration.py") is **incorrect**: the test_db_migration.py fixture is already async (`async def setup`); the warnings come from aiosqlite library-internal worker-thread teardown timing, not a fixture-design bug. Real fix needs investigation (shared fixture vs per-test open/close OR warning filter OR aiosqlite version bump), not mechanical pattern-replication. The F11 debrief's confident framing didn't run the test_db_migration.py grep at debrief time.
- Operator-side scope reshape (planning): users in the allowlist stay GLOBAL with a per-peer DM toggle (not server-scoped); the hierarchy applies to Servers → Channels → Roles only. This is materially simpler than the M10/F10-filed Known Issue language ("Servers / Channels / Users") and changes the migration shape (peers gain dm_allowed, not guild scoping).
- F11 debrief recommendation about "renaming `idx_pending_approvals_account_peer_status` index name" folds into F12 L1's grep gate naturally (the snake_case identifier rename includes the index name).

---

## Pulled-Forward F11 Debrief Methodology Lessons

Per operator instruction ("pull forward those recommendations"):

1. **Grep-gate-scope-is-a-design-decision**: F12 L1 spec explicitly enumerates the grep gate's surface forms (`\bConnectorAccount\b`, `\bconnector_account_id(s)\b`, `connector_account` substring); excluded surfaces are listed explicitly with rationale.
2. **Phase 5c architect cycle for grep-gate flights**: F12 L1 specifies a Phase 5c architect cycle that runs the literal grep against the codebase pre-implementation and confirms the hit count matches the spec's enumerated list.
3. **Separate test-surface from production-surface recon**: F12 L3 spec calls out a separate test-surface grep at design time to enumerate fixture + assertion updates needed.
4. **Two-symmetric-paths-in-acl convention codified**: F12 L2 promotes this as a named M11 convention in `the_one/agents.md` so future ACL-touching legs default to enumerating both `admits_inbound` AND `admits_outbound` at recon.
5. **Operator-local-state preservation discipline** (`docker-compose.yml` stays unstaged): preserved as F12 implementation guidance across all 5 legs.

---

## Leg Progress

### L1 — snake-case-identifier-rename (2026-05-29)

**Status**: landed (Phase 2d batches commits)

**Surfaces touched**:

- **Production code (5 files)**:
  - `the_one/interfaces/web/api.py` — 11 FastAPI handler renames (drop `_account` from each): `detach_agent_from_connector`, `_validate_connector_config`, `_connector_response`, `list_connectors`, `list_connector_types`, `get_connector`, `create_connector`, `update_connector`, `delete_connector`, `generate_connector_pairing_code`, `list_attached_agents_for_connector`. Internal call sites and docstrings updated in lockstep. Logger prefix in `detach_agent_from_connector` updated to match new name.
  - `the_one/db/repositories.py` — `SQLiteAgentStore.list_by_connector_account` → `list_by_connector` (1 def at `:89`).
  - `the_one/tools/connector_history.py` — `_resolve_connector_account_context` → `_resolve_connector_context` (1 def at `:526` + 4 same-file call sites at 142, 241, 332, 417).
  - `the_one/db/models.py:259` — docstring `{create,update}_connector_account` → `{create,update}_connector`.
  - `the_one/connectors/_discord.py:632` — comment reference `_validate_connector_account_config` → `_validate_connector_config`.

- **Production call sites / docstrings updated (4 files)**:
  - `the_one/connectors/_inbound.py` — 1 call site (`:364`) + 3 docstring refs to `list_by_connector_account` updated.
  - `the_one/connectors/_routing.py` — 2 docstring refs to `list_by_connector_account` updated.
  - `the_one/interfaces/web/app.py:149` — 1 call site updated.

- **Test code (5 files)**:
  - `tests/test_db_api.py` — 4 class renames (`TestConnectorAccountAPI` → `TestConnectorAPI`, `TestConnectorAccountDoctor` → `TestConnectorDoctor`, `TestConnectorAccountPairingCodeAndAttached` → `TestConnectorPairingCodeAndAttached`, `TestConnectorAccountPeerApprovals` → `TestConnectorPeerApprovals`) + cross-class doc refs + 2 method renames (`test_update_connector_account_routing_round_trips` → `test_update_connector_routing_round_trips`, `test_list_connector_accounts_includes_attached_agents_count` → `test_list_connectors_includes_attached_agents_count`) + 1 docstring ref to `list_connector_accounts` updated.
  - `tests/test_db_repositories.py` — 3 class renames (`TestConnectorAccountRepository` → `TestConnectorRepository`, `TestConnectorAccountConfigValidator` → `TestConnectorConfigValidator`, `TestConnectorAccountSessionContinuation` → `TestConnectorSessionContinuation`) + cross-class docstring ref + 6 `test_list_by_connector_account_*` → `test_list_by_connector_*` method renames + `test_fk_cascade_via_connector_account_delete` → `test_fk_cascade_via_connector_delete` method rename + all `list_by_connector_account` call sites/docstrings updated + `_seed_connector_account` → `_seed_connector` fixture rename (1 def at `:2717` + 11 call sites) + docstring "Deleting the parent connector_account" → "Deleting the parent connector".
  - `tests/test_app_pending_approval_merge.py` — `_seed_connector_account` → `_seed_connector` fixture rename (1 def at `:79` + 5 call sites).
  - `tests/test_provider_api.py:742` — `test_rotate_connector_account_secrets` → `test_rotate_connector_secrets` method rename.
  - `tests/_connector_dispatch_helpers.py:98` — docstring ref to `list_by_connector_account` updated.
  - `tests/test_lifespan.py:148` — **scope fold-in (not enumerated in original spec)**: `test_lifespan_warm_acquires_connector_accounts_per_account` → `test_lifespan_warm_acquires_connectors_per_account`. Phase 5c grep verification surfaced this as an in-scope identifier rename; folded into L1 per spec's "fold the rename into L1" rule.

- **Test filename renames via `git mv` (2 files)**:
  - `tests/test_api_connector_accounts.py` → `tests/test_api_connectors.py` (also updated 2 internal docstring refs to the sibling file's new name).
  - `tests/test_api_connector_account_config_validation.py` → `tests/test_api_connector_config_validation.py` (also renamed module-docstring `_validate_connector_account_config` → `_validate_connector_config` and class `TestConnectorAccountConfigValidation` → `TestConnectorConfigValidation`).

- **Markdown citations (2 files)**:
  - `the_one/agents.md:243` — 3 stale post-F11 references updated: JS file `connector-account-editor.js` → `connector-editor.js` (×2 in the line), JS function `renderConnectorAccountEditor` → `renderConnectorEditor` (verified via grep of `connector-editor.js:285`), browser test filename `test_flow_studio_connector_account_create_and_test.py` → `test_flow_studio_connector_create_and_test.py` (verified via `ls tests/browser/`).
  - `the_one/connectors/README.md:418` — `SQLiteAgentStore.list_by_connector_account(account_id)` → `SQLiteAgentStore.list_by_connector(account_id)`.

**Preserve list (historical-narration, not modified)**:
- `the_one/db/schema.py` — v17/v21/v23 migration bodies (L3 scope; index rename deferred).
- `tests/test_db_migration.py` — pre-v23 TestSchemaVN classes (Category A).
- `the_one/agents.md:671` + `the_one/connectors/README.md:312` — explicitly-preserved historical narration about v23 rename.
- **Additional historical-narration refs preserved beyond spec's enumeration** (same semantic class as agents.md:671 + README.md:312 — narrate the v23 rename from `connector_accounts` table name; not snake_case identifier defs):
  - `the_one/connectors/_stub.py:23` ("Schema v13 has no CHECK constraint on ``connector_accounts.type``")
  - `the_one/db/_connector_types.py:24` ("v23 → table + FK column rename ``connector_accounts`` →")
  - `the_one/db/models.py:120` ("v13 table originally named ``connector_accounts``")
- These 3 trip the grep gate's filter pipeline (which only excludes `schema.py` + `test_db_migration.py` + `agents.md:671` + `README.md:312`) but are semantically equivalent to the explicitly-allowed historical narrations. Suggest L2/L3 fold the grep-gate filter to include these 3 file:line citations OR convert them to `connectors` table-name references with a footnote.

**Test results**:
- Backend: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` → **2749 passed, 4 skipped, 17 deselected, 2 warnings in 261.68s** (matches F11 baseline exactly).
- Browser: `docker exec the-one pytest tests/browser/ -m browser --timeout 120` → **431 passed, 35 skipped, 12 deselected, 2 failed in 514.12s**. The 2 failures (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` and `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`) are the documented pre-existing-on-main failures (per leg spec's `Inputs` baseline); not L1-caused.

**Grep verification gate**: residual hits in `_stub.py:23`, `_connector_types.py:24`, `models.py:120` — all historical narrations about the v23 table rename. See Preserve list above.

**No commits made.** Stage held back per Phase 2d batching protocol. Phase 5c grep recon (architect cycle) confirmed enumeration was accurate including the `_seed_connector_account` 11-call-site correction baked into the spec.


### L2 — acl-extraction-and-symmetric-paths-convention (2026-05-29)

**Status**: landed (Phase 2d batches commits)

**Surfaces touched**:

- **Production code (1 file)**:
  - `the_one/connectors/_acl.py` — `admits_inbound` extracted from 1 function (240-line body) into 3 functions: thin dispatcher + `_admits_inbound_dm` (DM-context branches: account-scope peers + dm_admission, per-agent peers + admit_dms) + `_admits_inbound_guild` (guild-context branches: account-scope peers + channels + guilds + roles, per-agent peers + channels + guilds + roles). Dispatcher does NO pre-computation — helpers own their own `account_id` derivation, `allowlist` lookup, `member_roles_set` computation. Peers-axis prelude is duplicated across the two helpers per spec guidance (small overlap, L3 will diverge them per per-peer `dm_allowed`). Public signature + docstring preserved verbatim on the dispatcher (added a short "Internal structure (F12 L2)" docstring paragraph noting the dispatcher pattern + pointing at the new convention).

- **Documentation (1 file)**:
  - `the_one/agents.md` — added `two-symmetric-paths-in-acl` convention block to the Mission-specific (M11) section as a 4th sibling between `backend-merged-replay` and `studio-event-bus`. Cites substrate shape (`admits_inbound` + `admits_outbound` mirrored at per-agent block), historical pattern instances (M10 F8 L8 guilds/roles axes, F10 L1 dm_admission, F11 L3 deny-message retirement), prescriptive rule ("recon for any ACL-touching leg defaults to enumerating both directions"), and source attribution (F11 debrief recommendation #5, codified at F12 L2). Names F12 L3 as the next concrete instance.

**Structural verification**:
- `grep -cE "^(async )?def " the_one/connectors/_acl.py` → **7** (was 5; added `_admits_inbound_dm` + `_admits_inbound_guild`).
- `wc -l the_one/connectors/_acl.py` → **575** (was 484; +91 LOC). Slightly above the spec's ~510-525 hint because comment blocks at both branches were preserved verbatim in both helpers rather than condensed; readability favors the verbose form and the peers-axis prelude duplication is explicit in the spec. No structural drift — same control flow, same reason strings, same ordering.
- `admits_inbound` body (excluding 50-line docstring + 12-line "Internal structure" doc paragraph) is the ~12-line dispatcher: `if is_dm: return _admits_inbound_dm(...) ; return _admits_inbound_guild(...)`.

**Test results**:
- Focused ACL suite: `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 30` → **169 passed in 16.11s** (matches L1 baseline pass count — no skips, no new tests added, no test fixture or assertion modifications in L2).
- Broad backend: `docker exec the-one pytest --ignore=tests/browser -x --timeout 60` → **2749 passed, 4 skipped, 17 deselected, 2 warnings in 242.16s** (matches L1 baseline exactly — same 2 aiosqlite teardown warnings are pre-existing library-internal quirk; not L2-caused).
- Browser baseline preserved (no L2 changes to UI — `tests/browser/` untouched).

**Atomicity boundary verified**:
- Only `the_one/connectors/_acl.py`, `the_one/agents.md`, this leg artifact (status), and `flight-log.md` (this entry) touched.
- `admits_outbound` left as a single function (convention applies to FUTURE changes — L3 of this same flight is the next concrete instance).
- No test files modified — all 63+ existing `admits_inbound`-touching test sites pass against the extracted dispatcher unchanged.
- `docker-compose.yml` stays unstaged (operator local dev state).

**No commits made.** Stage held back per Phase 2d batching protocol.


### L3 — storage-shape-v24-migration-and-acl-semantics (2026-05-29)

**Status**: landed (Phase 2d batches commits)

**Substrate change (v24 migration)**:

- `the_one/db/schema.py` — added `if version < 24:` block after the v23 block (`:1155`). The migration row-rewrites the `connectors.config.allowlist` JSON column: peers `list[str]` → `list[{id, dm_allowed}]`; channels `list[str]` → `list[{guild_id, channel_id}]` (NULL guild_id legacy-permissive); roles `list[str]` → `list[{guild_id, role_id}]` (NULL guild_id legacy-permissive); `dm_admission` Literal-value rename `"allowlisted-peers-only"` → `"admin-approved"` (operator-vocabulary alignment). Parallel row-rewrite of `agents.connector_acls` JSON for per-agent shape uniformity (per-agent peers default `dm_allowed=True`; account-scope per-peer `dm_allowed` is the Truth Table discriminator). Index rename `idx_pending_approvals_account_peer_status` → `idx_pending_approvals_connector_peer_status` (cosmetic-rename deferred from F11 v23 per F12 operator decision). Bumped `CURRENT_VERSION = 24`.
- DM Admission collapse rule applied per the operator-confirmed F12 L3 spec: `dm_admission="all"` → peers get `dm_allowed=True`; `dm_admission="none"` → peers get `dm_allowed=False`; `dm_admission="allowlisted-peers-only"` (explicit OR absent-but-allowlist-present) → peers get `dm_allowed=True` AND `dm_admission` rewritten to `"admin-approved"`; `allowlist` absent entirely → no peers to migrate.
- Segment guards baked in for the v7-strip rewind+rerun scenario: per-row `isinstance(peers[0], dict)` short-circuit + `agents` / `pending_approvals` table-existence guards (hand-built partial-schema test fixtures used by the v22 `TestSchemaV22::test_v22_legacy_row_*` tests build connector_accounts but no agents table).
- Anomaly resolved in-leg: the v21 block's `CREATE INDEX IF NOT EXISTS idx_pending_approvals_account_peer_status ON pending_approvals (connector_account_id, ...)` was failing on the `test_v7_strips_removed_tool_names` rewind path because v24 dropped the old-named index and the v21 re-create referenced the post-v23-renamed column. Fixed by splitting v21's `executescript` into the CREATE TABLE half + a Python-guarded CREATE INDEX that consults `PRAGMA table_info(pending_approvals)` to choose the old-column branch (fresh-migration path) vs the new-column branch with the new v24 index name (rewind+rerun path). Documented in the v21 block's comment.

**Pydantic validator updates**:

- `the_one/db/models.py` — `_validate_config_v17_extras` extended at the `allowlist` branch. New per-axis shape validation: peers entries must be `dict[str, Any]` with keys `{id: str, dm_allowed: bool}`; channels entries `{channel_id: str, guild_id: str | None}`; roles entries `{role_id: str, guild_id: str | None}`; `guilds` axis stays `list[str]`. `dm_admission` Literal updated to `{"none", "admin-approved", "all"}` (rejects pre-rename value). Default for absent-key on present allowlist: `"admin-approved"`.
- `the_one/agent/config.py` — `connector_acls` field annotation widened from `dict[str, dict[str, list[str] | bool | None]] | None` to `dict[str, dict[str, Any]] | None` (the structured-tuple shape can't be expressed via Pydantic v2 generics for a heterogenous-key inner dict). `_validate_connector_acls` validator extended for per-key shape: peers/channels/roles use the same structured-tuple shape as account-scope; `admit_dms` stays `bool | None`; `guilds` stays `list[str]`. Per-agent `peers[*].dm_allowed` is structurally uniform with account-scope BUT not consulted by the F12 L3 DM Composition Truth Table (per the operator-confirmed semantics — DM admission is decided at account scope).

**ACL helper updates (`the_one/connectors/_acl.py`)**:

- `_admits_inbound_dm` — rewritten per the operator-confirmed F12 L3 DM Composition Truth Table: `admit_dm = (admit_dms is not False) AND (peer in allowlist) AND (dm_admission == "all" OR (dm_admission == "admin-approved" AND peer.dm_allowed == True))`. Per-agent `admit_dms=False` short-circuits first. Peers-axis check (account-scope; structured-dict id match) denies before `dm_admission` is consulted (precedence per cycle-1 cell-#3 clarification). `dm_admission="all"` ignores per-peer `dm_allowed`; `"admin-approved"` consults it; `"none"` always denies. Reason strings rephrased for the "peer not in allowlist under admin-approved" case (`"DM denied: account ... dm_admission is 'admin-approved' and peer not in allowlist"`).
- `_admits_inbound_guild` — updated for structured-tuple consumption. Channels axis: admit iff `any(c["channel_id"] == channel_id AND (c["guild_id"] is None OR c["guild_id"] == guild_id))` (NULL guild_id legacy-permissive backward-compat). Roles axis: admit iff `member_roles_set & {r["role_id"] for r in allowed_roles where r["guild_id"] is None or r["guild_id"] == guild_id}` is non-empty. Peers axis: structured-dict id match.
- `admits_outbound` — channel-tuple lookup at both scopes; matches by `channel_id` ALONE, ignoring per-entry `guild_id` (LOCKED decision per cycle-1 finding #5 — F4 platform-send tool has no envelope guild_id context). Documented in the function docstring with the rationale.
- `admits_dm_peer` — updated for structured-dict peer lookup; consults only `peer["id"]` (the `dm_allowed` field gates inbound DM admission, not outbound history reads).
- Module docstring updated to document the F12 L3 structured-tuple storage + the `dm_admission` rename.

**Peer-list consumer site updates (3 production sites)**:

- `the_one/connectors/_inbound.py:467-476` — pairing-approve peer-add path now appends `{"id": envelope.peer_id, "dm_allowed": False}` (operator must flip via UI under the `"admin-approved"` policy mode). Existing membership check rewritten to `any(p["id"] == ...)`.
- `the_one/interfaces/web/api.py:2727-2740` — `approve_peer_approval` handler mirrors the same structured-dict construction.
- `the_one/connectors/_discord.py:1651` — pairing-resolver hook consumes `peer["id"]` for membership check.

**New tests added**:

- `tests/test_db_migration.py` — `TestSchemaV24` class with 5 tests: `test_v24_fresh_db_shape` (validator accepts structured shape, rejects flat shape, rejects pre-rename Literal value; renamed index present, old name absent), `test_v24_idempotent_on_rerun` (segment guards short-circuit), `test_v24_legacy_v23_row_migration_preserves_data` (4 sub-cases covering `dm_admission` ∈ {"all", "none", "allowlisted-peers-only", absent}), `test_v24_agents_connector_acls_rewrite` (parallel structured shape for per-agent), `test_v24_index_rename` (DROP+CREATE atomic from app perspective).
- `tests/test_connectors_acl.py` — `TestDmAdmissionCompositionMatrix` parametrized class with 12 cells covering the `admit_dms × dm_admission × dm_allowed × in_allowlist` cross-product (per the F12 L3 spec's enumerated table, including the revised cell #3 where `dm_admission="all"` + peer not in non-empty peers list denies via the peers-axis check precedence). One cell per parametrize → 12 distinct test IDs.
- `tests/test_db_repositories.py` — `test_v24_structured_shape_full_round_trip_through_sqlite` (cycle-1 finding #4): full structured-shape round-trip across all 4 axes + `dm_admission`; explicit `isinstance(peer_entry["dm_allowed"], bool)` assertion to guard against bool→int silent coercion through JSON round-trip.

**Existing test fixtures updated (~30 sites across 9 files)**:

- `tests/test_connectors_acl.py` — added `_to_v24_shape()` + `_to_v24_agent_acl()` translator helpers at module top; wrapped `admits_inbound` / `admits_outbound` imports with thin wrappers that translate flat-shape `agent_acl` inputs at call time so existing fixtures keep their readable flat shape. One assertion updated to the new "peer not in allowlist" reason string under `"admin-approved"` policy.
- `tests/test_connectors_routing.py` — added `_to_v24_shape()` helper and wired it into the file's `_account()` builder so fixtures stay readable.
- `tests/test_connectors_inbound.py` — 2 assertions updated to `any(p["id"] == ...)` membership check (structured-dict peers).
- `tests/test_db_repositories.py` — 8 fixture sites updated to structured shape (validator round-trip tests, ACL save-load tests, partial-axes tests, full-config round-trip).
- `tests/test_db_api.py` — 7 fixture sites updated (pairing-code preserves-keys, attached-agents response, dismiss-doesn't-mutate, approve adds/preserves/initializes peer, empty-lockdown survives).
- `tests/test_connector_history_tools.py` — 3 fixture sites updated (channel/thread/dm history ACL denials).
- `tests/test_connector_send_tool.py` — 4 fixture sites updated (channel admission permit/deny scenarios).
- `tests/test_connectors_commands.py` — added `_to_v24_shape()` helper; wired into `_account()`.
- `tests/test_connectors_discord.py` — `_resolve_test_account()` helper updated to build structured peers internally.
- **Category A historical-shape tests**: 0 found — every flat-shape fixture was test scaffolding rather than shape-pinning. The v22 `TestSchemaV22::test_v22_legacy_row_*` tests SEED pre-v23 flat-shape rows but the post-ensure_schema assertions had to be updated to the post-v24 shape (the seeded rows survive into the v24 row-rewrite). Updated the 2 v22 tests with structured-shape assertions and a docstring note explaining the v24 evolution. The v23/v21 fresh-DB tests had identical issue with the renamed index name — updated assertions to `idx_pending_approvals_connector_peer_status` and added v24-evolution-aware docstrings. The exact-CURRENT_VERSION assertion (`assert CURRENT_VERSION == 23`) at `TestSchemaV8::test_v8_fresh_db_includes_tool_configs_and_tool_overrides` was bumped to `== 24` with extended docstring referencing F12 L3.

**Test results**:

- Migration suite: `docker exec the-one pytest tests/test_db_migration.py --timeout 30` → **63 passed in 13.78s**.
- Focused ACL + connectors suite: `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_inbound.py --timeout 30` → **181 passed in 16.64s** (L2 baseline 169 + 12 new DM composition matrix cells; the existing-fixture updates net to zero).
- Broad backend suite: `docker exec the-one pytest --ignore=tests/browser --timeout 60` → **2767 passed, 4 skipped, 17 deselected, 2 warnings in 248.33s**. Beats the spec's 2766 target by 1 (the SQLite round-trip test added per cycle-1 finding #4). Wall-clock ~248s, well within the +10% bound (L2 baseline 242s).
- Browser baseline preserved (no L3 changes to UI — `tests/browser/` untouched).

**Atomicity boundary verified**:

- Production code touched: `the_one/connectors/_acl.py`, `the_one/db/models.py`, `the_one/agent/config.py`, `the_one/db/schema.py`, `the_one/connectors/_inbound.py`, `the_one/connectors/_discord.py`, `the_one/interfaces/web/api.py` (7 files — matches spec's enumerated 5 production files + the 2 spec-cited consumer-site files at `_discord.py:1651` and `web/api.py:2727-2740`).
- Test code touched: `tests/test_db_migration.py` (new class), `tests/test_connectors_acl.py` (new matrix + helpers + 1 assertion), `tests/test_connectors_routing.py` (helper added to existing _account), `tests/test_connectors_inbound.py` (2 assertions), `tests/test_db_repositories.py` (8 fixtures + 1 new round-trip), `tests/test_db_api.py` (7 fixtures), `tests/test_connector_history_tools.py` (3 fixtures), `tests/test_connector_send_tool.py` (4 fixtures), `tests/test_connectors_commands.py` (helper + 1 fixture), `tests/test_connectors_discord.py` (1 helper).
- No frontend file touched (L4 scope).
- No `tests/browser/*.py` touched (L4 scope).
- `docker-compose.yml` stays unstaged (operator local dev state).

**Deviations from spec**:

- Spec's "Pre-v24 TestSchemaVN classes stay untouched (Category A)" carve-out had a conflict with the v22/v23/v21 fresh-DB tests' assertions on `dm_admission` Literal value, peers/channels shape, and index name — those tests pass through full `ensure_schema` which now includes v24, so their post-state assertions had to be updated. The Category A discipline (preserve legacy-data-decode tests that pin pre-vN historical shape) was honored — only the head-of-`ensure_schema` assertions were updated, and only with explanatory comments citing the F12 L3 evolution. The `TestSchemaV21`, `TestSchemaV22`, and `TestSchemaV23` legacy-data-DECODE tests retain their pre-v24 seeded data + their preserved data shapes (other than the v24 collapse rule's mechanical row-rewrites).
- Spec's "transitional dual-shape validator" recommendation was skipped (single-step path per spec's alternative). All fixture updates landed atomically with the validator change.

**No commits made.** Stage held back per Phase 2d batching protocol.

### L4 — ui-discoverable-dropdown-and-per-peer-dm-toggle (2026-05-29)

**Status**: landed (Phase 2d batches commits)

**Frontend code changes**:

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — allowlist-editor refresh:
  - `dm_admission` select: Literal value rename `'allowlisted-peers-only'` → `'admin-approved'`; visible label rename `"Admit DMs from approved peers"` → `"Admin-approved (per-peer)"`; default fallbacks updated to `'admin-approved'` (3 sites: render, collect, defensive-default).
  - `_mountAllowlistAxisEditor` extended with per-axis `valueShape` ('peer' / 'channel' / 'role' / 'flat') passthrough to the dropdown. Stub-fallback chip-list path unwraps structured tuples → flat-id chips on init and installs a wrap-on-collect `_allowlistValues` getter so chip-list edits round-trip structured tuples (`{guild_id: null, ...}` defaults).
  - `collectAllowlistFromContainer` / `_readChiplist` updated to pass non-string entries through unchanged (structured shape reaches the save payload).
  - `_confirmStaleChipsThen` updated to extract ids from structured-tuple peers/channels (both the orig/new comparison and the per-agent attached-agents lookup).
  - `wireAllowlistEvents` adds a `dm_admission` select change handler that toggles a `dm-admission-admin-approved` class on the peers field-row (path (b) per the leg artifact — CSS-toggle preserves checkbox state across mode flips). Peers field-row now carries `data-testid="connector-allowlist-peers-row"` for browser-test selectors.

- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — `valueShape` opt-in for structured-tuple shape. Internal helpers (`_entryId`, `_entryGuildId`, `_wrapId`, `_currentIds`) wrap/unwrap at the chip + selection boundaries; menu logic continues to operate in flat-id terms. `_renderChips` adds per-peer DM toggle (inside the peer chip, `data-testid="connector-allowlist-peer-dm-toggle-{peer_id}"`) when `valueShape === 'peer'`; toggle visibility is CSS-controlled by the parent peers-row class. `_renderChips` also adds the legacy-entry indicator (`data-testid="connector-allowlist-{channel|role}-legacy-indicator-{id}"`) for null-guild_id channels/roles, with tooltip explaining the v24 backfill. `_addValue` / `_removeValue` / `_refreshSelectionUI` updated to operate on structured-tuple shape.

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — `renderDiscoverableDropdown` bridge extended from 5- to 6-positional signature; the 6th `extraOpts` carries `{valueShape}` for the structured-tuple opt-in. Default `{}` preserves pre-L4 flat-id behavior unchanged.

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — per-agent overlay updates (rendered for the agent editor's Connectors tab):
  - `accountAcl.peers` / `.channels` from raw storage projected to id-string arrays via `_projectAclAxisToIds` so the checkbox-list-mode initial-state matcher and chip-mode initial-chip render continue operating in id terms.
  - `scopePeers` / `scopeChannels` similarly projected via `_projectPeerIds` / `_projectChannelIds`.
  - Checkbox-mode wrapper for channels carries `data-channel-guild-id-map` (JSON-encoded `channel_id → guild_id` lookup) so the save path can re-attach guild context when wrapping checked ids back into structured tuples.
  - Chip-list dropdown path passes `valueShape` ('peer' / 'channel') into the dropdown and re-wraps init items from id-strings → structured tuples for consistent render shape.
  - `_buildChipList` (per-agent chip-list editor) projects structured-tuple entries to id-strings for display.
  - Per-agent peers section gets a one-line note `"DM admission is account-scope only."` (`data-testid="agent-connector-peers-dm-note-{account_id}"`) — per L3 spec, per-agent `peers[*].dm_allowed` is NOT consulted by ACL, so the per-peer toggle is OMITTED from the per-agent overlay and replaced by this explanatory note.
  - `scopeDmAdmission` default updated to `'admin-approved'` (L4 Literal rename).

- `the_one/interfaces/web/static/js/areas/studio.js` — per-agent ACL collect path updated for structured-tuple shape:
  - New `_wrapPerAgentEntry` helper wraps checked-checkbox-ids back into `{id, dm_allowed: true}` (peers) / `{guild_id, channel_id}` (channels). Channels read guild_id from the `data-channel-guild-id-map` data attribute on the checkbox wrapper.
  - Chips-mode handles both dropdown-emitted structured tuples (passed through) and text-node-walk strings (wrapped via `_wrapPerAgentEntry`).
  - Per-agent peers default `dm_allowed=true` (structural-uniformity field; NOT consulted by ACL per L3 — defaulting True keeps the save shape neutral).

- `the_one/interfaces/web/static/css/studio.css` — new styles for the per-peer DM toggle (display: none by default; display: inline-flex when the parent peers-row carries `dm-admission-admin-approved`) and the legacy-entry indicator (dashed border on `.chip[data-legacy="true"]` + small info-glyph span). Uses the existing `--accent` and `--fg-secondary` design tokens (per token_definitions.py regression test).

**Out-of-listed-boundary files justified**:

- `connectors-tab.js` + `studio.js` + `connector-form-discord.js` are not in the leg's literal 4-file enumeration, but the per-agent overlay rendering + per-agent ACL save path + Discord registry bridge live there respectively. L4 correctness REQUIRES structured-tuple support across these surfaces (the per-agent overlay save would otherwise emit string arrays that the L3 validator now rejects). The leg artifact's "agent-editor.js — per-agent overlay" line semantically covers connectors-tab.js (agent-editor.js delegates to it for the overlay); the Discord bridge in connector-form-discord.js is a mechanical 5→6 positional parameter extension to forward the `valueShape` opt; studio.js's collect-path update is the save-side counterpart to the structured-tuple render path. All changes are L4-scoped (structured-tuple + Literal rename support only) — no behavior changes beyond what L4 atomically introduces. Python files untouched per the L4 atomicity boundary.

**Browser test fixture updates**:

- `tests/browser/seeders.py` — added `_to_v24_allowlist()` + `_to_v24_agent_acl()` translator helpers mirroring the backend-test `_to_v24_shape()` from `tests/test_connectors_acl.py`. `seed_connector` auto-translates `config['allowlist']` to the structured-tuple shape and the `dm_admission` Literal rename — fixtures continue using the flat shape for readability.
- `tests/browser/test_flow_studio_connector_dm_admission_row.py` — 3 sites updated: option-values assertion now `["none", "admin-approved", "all"]`; 2 fixtures + 1 assertion updated to `"admin-approved"`.
- `tests/browser/test_flow_studio_per_agent_admit_dms.py` — docstring updated for Literal rename.
- `tests/browser/test_flow_studio_connector_allowlist_dropdown.py` — 2 assertions updated to project `channel_id` from structured-tuple channels for membership checks.
- `tests/browser/test_flow_studio_connector_discord_vocabulary.py` — round-trip assertion updated to project ids from structured-tuple peers/channels/roles.
- `tests/browser/test_flow_chat_pending_approval.py` — `_allowlist_peers` helper updated to project `id` from structured-tuple peers.
- The remaining 4 of the 10 listed files (routing_dropdown, discoverable_dropdown, per_agent_overlay_dropdown, per_agent_overlay_label_resolver, admin_tools_editor) needed no inline test changes — the seeder auto-translation covered their fixtures, and their assertions don't touch the per-entry shape.

**New browser tests added** (`tests/browser/test_flow_studio_per_peer_dm_toggle.py`):

- `test_per_peer_dm_toggle_visible_only_under_admin_approved` — switching `dm_admission` between admin-approved / all / none toggles the `dm-admission-admin-approved` CSS class on the peers section; toggle DOM persists across mode flips (path (b) preserves checkbox state).
- `test_per_peer_dm_toggle_persists_on_save` — toggling the per-peer DM checkbox and saving round-trips the boolean at `account.config.allowlist.peers[i].dm_allowed`.
- `test_per_peer_dm_toggle_hidden_under_all_mode` / `test_per_peer_dm_toggle_hidden_under_none_mode` — verifies the CSS class is absent under all / none modes.
- `test_channel_legacy_indicator_renders_for_null_guild_id` / `test_role_legacy_indicator_renders_for_null_guild_id` — connector seeded with a structured channel/role entry whose `guild_id` is null renders the legacy indicator with the per-id testid; non-null entries do NOT render the indicator.
- `test_per_agent_overlay_omits_dm_toggle` — verifies the per-agent overlay renders the "DM admission is account-scope only" note and does NOT render any `connector-allowlist-peer-dm-toggle-*` elements (the toggle is connector-editor scope only).

**Test results**:

- Backend regression: `docker exec the-one pytest --ignore=tests/browser --timeout 60` → **2767 passed, 4 skipped, 17 deselected, 2 warnings in 251.93s** (L3 baseline preserved exactly).
- Browser suite: `docker exec the-one pytest tests/browser/ -m browser --timeout 120` → **438 passed, 35 skipped, 12 deselected, 2 failed, 1 warning in 525.47s**. The 2 failures are the pre-existing-main failures (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs`, `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`) verified against the pre-L4 branch state with the same 2 failures. Pass count: 431 baseline + 7 new tests = 438 (within the spec's 435-445 target).
- POST-fixture audit (cycle-1 finding): `grep -rnE '"allowlisted-peers-only"' tests/browser/` returns 5 hits — all in comments/docstrings (auto-translator + test docstrings explaining the rename); 0 hits in fixtures or assertions. `grep -rn 'connector.*config.*allowlist.*peers.*\[' tests/browser/` returns 0 hits.

**Atomicity boundary verified**:

- No Python file touched (production or tests/test_*.py) beyond `tests/browser/seeders.py` + the 5 specific browser tests listed above.
- `docker-compose.yml` stays unstaged (operator local dev state).
- L3 baseline preserved at exactly 2767 passing.

**Deviations from spec**:

- The literal "4 files only" list in the leg artifact was extended to 6 frontend files (connector-editor.js + discoverable-dropdown.js + agent-editor.js + studio.css + connectors-tab.js + studio.js + connector-form-discord.js) for L4 correctness. The leg's "agent-editor.js — per-agent overlay" line was interpreted semantically (the overlay rendering lives in connectors-tab.js because agent-editor.js delegates to it). studio.js's collect path and the Discord registry bridge in connector-form-discord.js had to be updated for the structured-tuple shape to flow end-to-end. Justified above.
- Re-scope affordance for legacy entries: EXPLICITLY OUT OF SCOPE per the leg artifact — operators re-scope by removing + re-adding via the dropdown. Tooltip text on the legacy indicator references this workflow.
- agent-editor.js itself (the file enumerated in the boundary) was untouched — the per-agent overlay surface is connectors-tab.js. agent-editor.js's `renderAgentEditor` just delegates to `renderConnectorsTab` for the Connectors tab panel.

**No commits made.** Stage held back per Phase 2d batching protocol.


---

## Decisions

(empty — populated during execution; planning-time decisions live in flight.md Design Decisions)

---

## Deviations

(empty — populated during execution)

---

## Anomalies

(empty — populated during execution)

---

## Session Notes

(empty — populated during execution)
