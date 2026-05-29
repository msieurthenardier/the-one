# Flight: Hierarchical Allowlist Axes + Snake_Case Identifier Rename (F11 prereq)

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

This flight does not close a mission criterion directly. It is a substrate-stabilization + UX-correctness flight that supports criterion #19 (daily-driver robustness) indirectly: hierarchical allowlist axes close the operator-mental-model gap filed at F10 L5 HAT (operators reviewing the allowlist can't tell which server a `#general` belongs to under the current flat storage), and the snake_case identifier rename closes the F11-debrief carry-forward debt before the substrate gains further surface area. The F10-filed "Hierarchical allowlist axes" Known Issue and the F11-filed "snake_case identifier rename residue" Known Issue both close at this flight's land.

---

## Pre-Flight

### Objective

Reshape the connector allowlist substrate from 5 flat axes (`peers, channels, guilds, roles, dm_admission`) into a hierarchical-where-it-matters / global-where-it-makes-sense shape with a refined DM model: **peers** stay global as a flat allowlist AND gain a per-peer `dm_allowed` boolean that gates DM admission specifically under the `dm_admission="admin-approved"` policy mode; **`dm_admission`** STAYS as the account-scope 3-state policy (`all|none|admin-approved`) — under `all` and `none` modes, per-peer `dm_allowed` is ignored; under `admin-approved`, per-peer `dm_allowed` is the discriminator (operator-confirmed at planning); **guilds** stay flat as the top of the server hierarchy; **channels** and **roles** become structured tuples (`{guild_id, channel_id}` / `{guild_id, role_id}`) so the substrate prevents the name-collision admission bugs the operator surfaced at F10 L5 HAT. Extract `_acl.py:admits_inbound`'s DM-vs-guild decision tree into `_admits_inbound_dm` + `_admits_inbound_guild` (the 5-axes-tipping-point concern). Drop the `\bConnectorAccount\b`-grep-gate residue from F11 (~35 live def + ~292 hit sites of snake_case identifiers + the `idx_pending_approvals_account_peer_status` index name). Codify the methodology lesson from F11's debrief: rename-flight gate-greps must enumerate excluded surfaces explicitly; the `_acl.py` two-symmetric-paths substrate shape becomes a named convention in agents.md.

### Open Questions

All resolved during planning + architect cycle-1 — see Design Decisions below.

- [x] dm_admission disposition → see DD: DM Admission Model
- [x] Storage shape for channels + roles → see DD: Storage Shape
- [x] Leg sequencing and bundling → see DD: Leg Split Shape (post-architect-cycle-1: 4 legs, L3+L5 merged)
- [x] Migration strategy for existing channel/role IDs without guild_id → see DD: Backfill Strategy for Guild-less Legacy Entries
- [x] Per-agent `connector_acls` shape parallels → see DD: Per-Agent Overlay Mirrors Account Scope
- [x] DM composition truth table (architect cycle-1 finding) → see DD: DM Composition Truth Table
- [x] Index rename placement (architect cycle-1 finding) → folded into v24 (L3)
- [x] L1 grep gate excluded surfaces (architect cycle-1 finding) → see DD: Snake_Case Identifier Rename (updated)
- [x] L3 storage-change peer-consumer site catalog (architect cycle-1 finding) → see L3 Technical Approach (updated)

### Design Decisions

**Snake_Case Identifier Rename (F11 prereq)**: F11's L1 grep gate `\bConnectorAccount\b` (PascalCase, word-boundary) excluded snake_case identifiers; ~35 live def + ~292 hit sites (architect-cycle-1 corrected count) carry the old vocabulary. F12 L1 closes the gap as a mechanical prereq leg before any ACL substrate work. The leg's grep gate explicitly enumerates the **search corpus**: `the_one/`, `tests/` (including `tests/browser/`), `the_one/connectors/README.md`, `the_one/agents.md`. The **search patterns**: `\bConnectorAccount\b`, `\bconnector_account_id\b`, `\bconnector_account_ids\b`, `\bconnector_account\b` (snake-case word-boundary), AND `connector_account` (substring, capturing function/method/class names like `list_by_connector_account` + filenames like `test_api_connector_account_config_validation.py`). Test filenames carrying the term ARE in L1 scope. Per F11 debrief methodology lesson #1 ("grep-gate-scope-is-a-design-decision"): excluded surfaces are listed explicitly:
- ALLOWED RESIDUE post-L1: schema v23 migration body in `the_one/db/schema.py` (retains historical `connector_account` strings as the FROM side of the v23 row-rewrite + as the original ALTER ADD COLUMN statements); historical citations in `the_one/agents.md` M11 sub-section change-log entries; historical citations in `the_one/connectors/README.md:312,418` (F1 references, Category A "preserve historical-artifact names"); the SQLite index `idx_pending_approvals_account_peer_status` (renamed inside L3 v24 migration, NOT L1 — operator-confirmed at planning).
- Rationale: F11 left hybrid vocabulary in the Python identifier-name surface. F12 touches `_acl.py` and the storage substrate; doing the rename FIRST avoids re-touching the same files across legs. Mechanical; no behavior change.
- Trade-off: ~30 def renames + ~292 hit site updates (Python + Markdown + browser tests) means a substantial leg-1 diff. Mitigated by being purely mechanical and well-bounded by the explicitly-enumerated grep gate.

**DM Admission Model — `dm_admission` STAYS as account-scope policy; per-peer `dm_allowed` ADDS finer-grained gating under `admin-approved` mode** (operator-clarified post-cycle-2):
- `dm_admission` STAYS in storage and semantics. Account-scope 3-state Literal. **Literal value RENAMED in v24** (operator-confirmed at Phase 6): `none | allowlisted-peers-only | all` → `none | admin-approved | all`. The Literal value `admin-approved` is more honest about what it means now that per-peer `dm_allowed` discriminates within the policy. Schema v24 row-rewrite substitutes the value in each row's JSON `allowlist` payload as part of the migration body.
- Per-peer `dm_allowed: bool` is a new field on each peer entry: `peers: list[{id: str, dm_allowed: bool}, ...]`. **Only meaningful under `dm_admission="admin-approved"` (or `"allowlisted-peers-only"` pre-rename)**. Under `dm_admission="all"` or `"none"`, per-peer `dm_allowed` is stored but the ACL does not consult it.
- Schema migration v24 collapse rule for the NEW per-peer field on existing peer entries:
  - `dm_admission == "all"` → existing peers get `dm_allowed=true` (innocuous; preserves "everyone DMs" semantic if operator later flips mode to `admin-approved`)
  - `dm_admission == "none"` → existing peers get `dm_allowed=false` (innocuous; preserves "nobody DMs" semantic; operator can flip to true per-peer after switching mode)
  - `dm_admission == "allowlisted-peers-only"` (or absent-but-allowlist-present per F10 default) → existing peers get `dm_allowed=true` (preserves F10's "allowlisted-peers-can-DM" semantic exactly — no operator-visible regression for the most common mode)
  - `allowlist` itself absent → no peers to migrate
- Per-agent `connector_acls[acct].admit_dms` per-axis-tri-state-override STAYS (per F10 + operator confirmation; not retired)
- Rationale: Operator's clarified intent — keep the 3-state account-scope policy as the operator's primary knob (matches existing mental model + UI familiarity); ADD per-peer fine-grained control INSIDE the `admin-approved` mode for cases where operator wants to allowlist a peer for channel interactions but NOT DMs. Per-peer is the "admin-approval-per-peer" mechanism, not a replacement axis.
- Trade-off: Schema v24 adds a field to existing entries (no axis retirement; smaller blast radius than the original "replace" plan). UI complexity: per-peer DM toggle is conditional on account-scope mode (rendered only under `admin-approved`); avoids confusing operators who flipped to `all`/`none` from seeing irrelevant toggles.

**DM Composition Truth Table** (operator-confirmed at planning; revised post-clarification to include `dm_admission` as primary gate):

Final admit rule:
```
admit_dm = (admit_dms is not False) AND
           (peer in allowlist) AND
           (
             dm_admission == "all" OR
             (dm_admission == "admin-approved" AND peer.dm_allowed == true)
           )
```

Composition chain:
- **Per-agent `admit_dms` (per F10, unchanged)**:
  - `False` → deny (force; overrides everything below)
  - `True` or `None` → defer to account-scope policy
- **Account-scope `dm_admission` (3-state, unchanged from F10 semantically; possible Literal-value rename to `admin-approved`)**:
  - `none` → deny (regardless of allowlist + per-peer toggle)
  - `all` → admit if peer in allowlist (per-peer toggle ignored)
  - `admin-approved` → admit IFF peer in allowlist AND `peer.dm_allowed == true`
- **Per-peer `dm_allowed` (NEW)**:
  - Only consulted under `dm_admission="admin-approved"` mode
  - True → this peer can DM (when account-scope is admin-approved)
  - False → this peer cannot DM (when account-scope is admin-approved)

Rationale: Preserves F10's existing semantics for `dm_admission="none"` and `="all"` exactly — operators using those modes see zero behavioral change. The `admin-approved` mode gains finer granularity via per-peer toggle, matching operator's stated request for "per-user dm allow in addition to the connector scoped permission."

Trade-off: Three axes contribute to a single decision (per-agent override + account-scope policy + per-peer toggle). Composition is single-rule and short-circuiting, so reasoning load is bounded. Cross-product matrix tests in L3 cover all 12 combinations (`admit_dms × dm_admission × dm_allowed × in_allowlist`).

**Storage Shape — structured tuples for channels + roles**: `account.config.allowlist.channels` becomes `list[{"guild_id": str, "channel_id": str}]`; `roles` becomes `list[{"guild_id": str, "role_id": str}]`. Per-agent `connector_acls[acct].channels` and `.roles` mirror. `peers` and `guilds` stay flat.
- Rationale: Channel and role IDs are server-scoped on Discord's side, but the substrate currently stores them as flat lists of strings — the discoverable-dropdown UI shows them grouped by server but the storage doesn't preserve the hierarchy. Storing the guild_id explicitly: (a) prevents name-collision bugs (channel `#general` in Server A vs Server B if any code path ever switched from id-based to name-based admission); (b) lets the ACL check be one lookup instead of a join against Discord's runtime cache; (c) makes the discoverable-dropdown UI's grouping a property of the storage rather than a presentation-layer invention.
- Trade-off: Schema migration v24 row-rewrites 2 axes (channels + roles) in `account.config.allowlist` AND in `agents.connector_acls`. Existing channel/role IDs lack guild_id; the migration backfills with `null` (see DD: Backfill Strategy) and the ACL check treats `null` guild_id as "any guild" (legacy-permissive behavior). Operator can re-allowlist via UI to gain guild scoping.

**Backfill Strategy for Guild-less Legacy Entries**: Migration v24 backfills `guild_id=null` for each existing channel + role entry in the row-rewrite (instead of attempting Discord-runtime resolution at migration time, which would introduce a network dependency the migration cannot honor on a fresh local DB).
- ACL semantics: `{guild_id: null, channel_id: "C123"}` admits the channel regardless of which guild it appears under — preserves legacy permissive behavior. New entries created post-v24 via the UI always carry a real guild_id (the discoverable-dropdown collects both).
- Reconciliation: operator can click a "Re-scope to current guild" affordance in the per-entry UI to backfill guild_id from the current Discord live cache. Not enforced.
- Rationale: Migration must be deterministic and offline-safe (no network at migration time). Legacy permissive behavior matches operator's existing mental model of "these were allowed before; they're still allowed."
- Trade-off: Creates a soft data-quality gradient (legacy entries with null guild_id are looser than new entries). Surfaced in the UI as a "legacy entry" indicator so operators see what's null-scoped.

**Per-Agent Overlay Mirrors Account Scope**: Per-agent `connector_acls[acct]` shape changes mirror the account-scope changes exactly:
- `peers: list[str]` → `peers: list[{id: str, dm_allowed: bool}]` (per-peer `dm_allowed` is a plain bool — false is the safe default; per-peer is only consulted under `dm_admission="admin-approved"` per DD: DM Composition Truth Table)
- `channels: list[str]` → `channels: list[{guild_id: str | None, channel_id: str}]`
- `roles: list[str]` → `roles: list[{guild_id: str | None, role_id: str}]`
- `guilds` stays flat (no shape change)
- `admit_dms: bool | None` STAYS as a per-agent tri-state override on the account-scope-aggregated DM admission (None = inherit, True = always-allow regardless of per-peer toggle, False = never-allow regardless)
- Rationale: Substrate must be consistent across scopes; the per-agent overlay's purpose is to narrow, never to introduce a different storage shape than the account scope. The F10 L1 `admit_dms` per-axis-tri-state-override stays per operator's planning choice (option A vs C).
- Trade-off: Migration touches 2 surfaces (account.config + agents.connector_acls) but the shape evolves in lockstep.

**`_acl.py:admits_inbound` Extraction**: split into `_admits_inbound_dm` and `_admits_inbound_guild` (private helpers); `admits_inbound` becomes the thin dispatcher that consults `is_dm` and delegates to one or the other. Done in F12 L2, BEFORE the storage-shape changes land in L3 — extracting against the current 5-flat-axis shape is the smaller refactor; F12 L3 then updates the extracted helpers to handle structured-tuple lookups in-place.
- Rationale: F10 debrief flagged the function as "edge of readable" at 5 axes; F12's structured-tuple ACL semantics will add complexity. Extracting first means F12 L3 lands the ACL semantic changes against a clean structure rather than mutating an already-too-large function.
- Trade-off: Two-phase refactor (extract in L2, modify in L3) — slightly more LOC churn than doing both in one leg, but each leg's diff is smaller and reviewable.

**Two-Symmetric-Paths Convention Codified**: F12 L2 also codifies a new project convention in `the_one/agents.md` Mission-specific (M11) section: `two-symmetric-paths-in-acl`. Every change to `admits_inbound` requires the symmetric change to `admits_outbound` (and vice versa). F8 L8 (per-agent guilds/roles), F10 L1 (dm_admission), F11 L3 (deny-message retirement) all paid this cost; codifying makes the recon discipline part of the substrate's documented shape per F11 debrief recommendation #5.
- Rationale: Three flights independently surfaced the same pattern; promotion is overdue.
- Trade-off: None — it's documentation that prevents future recon misses.

**Verification Approach — Regression Tests + Targeted HAT Sub-Step Optional**: Backend test suite + browser test suite + a new `TestSchemaV24` class in `test_db_migration.py` cover the storage and ACL semantics. UI changes (discoverable-dropdown grouping + per-peer DM toggle) are covered by extended browser tests. No standalone behavior-test spec authored unless operator-requested at L4 design time (the visible UI is small enough that browser tests suffice).
- Rationale: F11 used regression-tests-only successfully; the F12 UI changes are bounded extensions of existing dropdown + checkbox patterns rather than novel UX. HAT would add observation cost without surfacing what regression tests miss.
- Trade-off: If the operator wants live confidence that the per-peer DM toggle behaves correctly under real Discord traffic, a small targeted HAT can be authored at L4 design time (UI is the visible surface). Default: skip.

**Leg Split Shape**: 4 legs (architect cycle-1 collapsed L3+L5 into single leg to avoid transient ACL-helper-vs-storage-shape mismatch state; operator-confirmed).
- L1: snake_case rename (F11 prereq, atomic mechanical rename + explicit grep-gate enumeration per F11 methodology lesson)
- L2: `_acl.py:admits_inbound` extraction into `_admits_inbound_dm` + `_admits_inbound_guild` + agents.md `two-symmetric-paths-in-acl` M11 convention (semantically a no-op)
- L3: storage shape + schema migration v24 (including index rename `idx_pending_approvals_account_peer_status` → `idx_pending_approvals_connector_peer_status` + optional dm_admission Literal-value rename `"allowlisted-peers-only"` → `"admin-approved"`) + ACL semantics update in lockstep (peers gain dm_allowed + channels/roles gain guild_id tuple + `dm_admission` STAYS as account-scope 3-state policy + `_admits_inbound_dm` / `_admits_inbound_guild` / `admits_outbound` updated for structured tuples + new composition chain (`admit_dms × dm_admission × dm_allowed × in_allowlist`) + per-agent overlay mirrors + cross-product matrix tests). One big atomic leg — substantial but coherent.
- L4: UI — discoverable-dropdown grouping by server for channels + roles; per-peer DM toggle UI in allowlist editor (rendered conditionally on account-scope `dm_admission` mode — visible under `admin-approved`, hidden/disabled under `all`/`none`); legacy-entry indicator for null-guild_id entries; allowlist editor refresh; dm_admission row STAYS with revised label (`Admit all DMs` / `Deny all DMs` / `Admin-approved (per-peer)`); browser test fixture + assertion updates across ~10-15 files (architect cycle-1 corrected estimate) including conditional-render verification.
- Rationale: L1 is independent. L2 prepares the structural surface for L3's modifications. L3 must merge storage-change + ACL-semantic update because adding the per-peer `dm_allowed` field to the storage shape requires the ACL helpers to consume it in lockstep — splitting into L3 (storage) + L5 (semantics) would leave tests against the new shape (with per-peer `dm_allowed` populated by migration v24) without the ACL semantic that respects it. L4 then makes the UI atomic.
- Trade-off: L3 is large (Pydantic shape change + migration v24 + 4 ACL helper updates + cross-product matrix tests + peer-list consumer site updates in `_inbound.py` / `api.py` / `_discord.py`). Single-leg atomicity is the price of avoiding the bridge-code intermediate state. If L3's design review surfaces unexpected scope (architect cycle-1 estimated `peers` has 7 production read sites alone), split into F12a/F12b is the divert (see Adaptation Criteria).

### Prerequisites

- [ ] F11 has landed (commit `e0a8491` on main, verified)
- [ ] Backend test suite baseline: 2749 passed / 4 skipped / 0 errors / ~254s wall (per F11 debrief test-metrics)
- [ ] Browser test suite baseline: 431 passed / 35 skipped / 14 deselected / 2 pre-existing-main failures (NOT F11-or-F12-caused)
- [ ] M11 agents.md M11 section exists (lines 405+; `studio-event-bus`, `dms-orthogonal-to-guild-restriction`, `backend-merged-replay` already in it after F11 L3)
- [ ] No outstanding F11 carry-forward that blocks F12: snake_case rename is THIS flight's L1; aiosqlite teardown warning investigation deferred to routine-maintenance (F11 debrief's "apply L3 pattern" recommendation does not apply; needs separate investigation — flagged as Known Issue, not F12 scope)
- [ ] Operator's local `docker-compose.yml` HAT env vars unchanged (continues out of F12 commits)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites listed
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**L1 — Snake_case identifier rename (F11 prereq).** Single atomic mechanical rename covering all snake_case identifier surfaces F11's `\bConnectorAccount\b` gate excluded. Surfaces:
- `SQLiteAgentStore.list_by_connector_account` → `list_by_connector` at `the_one/db/repositories.py:89` + 3 production call sites (`connectors/_inbound.py:364`, `interfaces/web/app.py:149`, +1 more discovered via grep) + 6 docstring citations
- `_resolve_connector_account_context` → `_resolve_connector_context` at `the_one/tools/connector_history.py:526` + 4 same-file call sites
- 11 `_connector_account*` FastAPI handler function names in `the_one/interfaces/web/api.py` (`detach_agent_from_connector_account` → `detach_agent_from_connector`, etc. — full list in L1 spec)
- 9 test classes (`TestConnectorAccountAPI` → `TestConnectorAPI`, etc.)
- Fixture `_seed_connector_account` → `_seed_connector` + ~6 test methods carrying the old vocab in their names
- 4 test filenames carrying the term: `tests/test_api_connector_account_config_validation.py` → `test_api_connector_config_validation.py`, plus any others discovered via the L1 architect-cycle-1 grep
- SQLite index `idx_pending_approvals_account_peer_status` — RENAMED IN L3 v24 migration (not L1; operator-confirmed at planning to keep the index rename bundled with the storage-change migration)

L1 explicitly applies F11 debrief methodology lesson #1: the grep gate enumerates ALL surface forms AND the search corpus. Per F11 debrief recommendation #2, a **Phase 5c architect cycle runs the literal grep against the codebase pre-implementation** to confirm the hit count matches the spec's enumerated list of ~292 hits. Per F11 debrief recommendation #3, test-surface recon is separate: `grep -rln 'connector_account' tests/` AND `grep -rln 'connector_account' tests/browser/` separately to catch browser-test surfaces.

**L2 — `_acl.py:admits_inbound` extraction + two-symmetric-paths-in-acl convention.** Extract the DM-vs-guild decision tree at `admits_inbound` (currently lines 248+ in the 484-LOC file) into two private helpers:
- `_admits_inbound_dm(account, account_acl, agent_acl, envelope, ...) -> tuple[bool, str]` — handles the `is_dm=True` branches (DM admission against `dm_admission` axis, per-peer DM-allow check after L3 lands)
- `_admits_inbound_guild(account, account_acl, agent_acl, envelope, ...) -> tuple[bool, str]` — handles the `is_dm=False` branches (guild + channel + role admission)
- `admits_inbound` becomes the thin dispatcher: consults `is_dm`, delegates to one helper or the other, returns its result

L2 does NOT change ACL semantics — same inputs, same outputs, same flat-axis shape. The extraction is structurally a no-op at the test level (all 58+ existing ACL tests pass unchanged). The new file size estimate is ~520 LOC (current 484 + ~36 for the dispatcher + helper signatures).

Also in L2: add `### two-symmetric-paths-in-acl` to `the_one/agents.md` Mission-specific (M11) section. Pattern: "Every change to `admits_inbound` requires the symmetric change to `admits_outbound` (and vice versa). The two ACL paths are mirror images at the per-agent block — F8 L8 (per-agent guilds/roles axes), F10 L1 (dm_admission axis), F11 L3 (deny-message retirement) all paid this cost. Recon for any ACL-touching leg defaults to enumerating both directions."

**L3 — Storage shape + schema migration v24 + ACL semantics update (merged per architect cycle-1 + operator decision).** Pydantic + SQLite schema changes for the structured-tuple storage AND the ACL helpers updated in lockstep so tests pass through the leg. One large atomic leg.

**(a) Schema migration v24** row-rewrites both `connectors.config.allowlist` AND `agents.connector_acls` JSON column contents. Migration shape (offline-safe, no network):
- For each row in `connectors`: parse `config.allowlist`, transform:
  - `peers: list[str]` → `peers: list[{id: str, dm_allowed: bool}]` where `dm_allowed` derives from `dm_admission` per the collapse rule in DD: DM Admission Model (preserves F10 semantics exactly for each existing mode).
  - `channels: list[str]` → `channels: list[{guild_id: null, channel_id: str}]` (null-guild_id backfill)
  - `roles: list[str]` → `roles: list[{guild_id: null, role_id: str}]`
  - `dm_admission` key STAYS but **its Literal VALUE is renamed** in-place: every occurrence of `"allowlisted-peers-only"` in `config.allowlist["dm_admission"]` is rewritten to `"admin-approved"` (operator-confirmed at Phase 6). Migration is offline-safe and idempotent (re-running on already-v24 data is a no-op).
- For each row in `agents`: parse `connector_acls` JSON dict, transform each `connector_acls[account_id]` payload similarly (skipping `admit_dms` which stays as-is per DD: Per-Agent Overlay; per-peer `dm_allowed` added the same way)
- ALSO in this migration: DROP + CREATE `idx_pending_approvals_account_peer_status` → `idx_pending_approvals_connector_peer_status` (bundled per operator decision; L1 explicitly defers index rename to here).

**(b) Pydantic validator** in `the_one/db/models.py:308-356` extended to the new shape:
- `peers` list-entries validate as `{id: str, dm_allowed: bool}` dicts
- `channels` / `roles` list-entries validate as `{guild_id: str | None, channel_id|role_id: str}` dicts
- `dm_admission` Literal updated to `Literal["none", "admin-approved", "all"]` post-v24 (per operator-confirmed rename). Default rule for absent-`dm_admission` key when allowlist is present is `"admin-approved"` (preserving F10's permissive-when-allowlisted default semantic).

**(c) ACL helper updates** in `the_one/connectors/_acl.py` (post-L2 extraction):
- `_admits_inbound_dm` updated per DM Composition Truth Table — composition rule: `admit_dm = (admit_dms is not False) AND (peer in allowlist) AND (dm_admission == "all" OR (dm_admission == "admin-approved" AND peer.dm_allowed == true))`. Preserves F10's `dm_admission` branching exactly for `"all"` and `"none"` modes; refines `"admin-approved"` (aka `"allowlisted-peers-only"` pre-rename) mode via per-peer consultation.
- `_admits_inbound_guild` updated for structured-tuple channel + role lookups: `any(c["channel_id"] == channel_id AND (c["guild_id"] is None OR c["guild_id"] == envelope.guild_id) for c in channels)`. Null guild_id is permissive (legacy entries).
- `admits_outbound` mirror update per `two-symmetric-paths-in-acl` convention: same channel-tuple lookup; no DM admission semantic at outbound (no envelope context per F10 design).
- `admits_dm_peer` updated for the composition chain consumption.

**(d) Peer-list consumer site updates** (architect cycle-1 catalog — 7 production sites + tests):
- `the_one/connectors/_inbound.py:471,474` — "add peer to allowlist on first contact" path. Peer entries now structured dicts; update construction + read sites.
- `the_one/interfaces/web/api.py:2731,2734` — peer-management endpoint. Update request/response shape; preserve operator's per-peer DM toggle choice on edit.
- `the_one/connectors/_discord.py:1651` — peer enumeration consumer. Update structured-dict reads.
- `the_one/connectors/_acl.py:220,321` — internal peer-list iteration (covered by L2 extraction + L3 helper updates).
- All test fixtures across `tests/test_connectors_*.py`, `tests/test_db_repositories.py`, `tests/test_api_*.py` that construct allowlist data — update to new shape. Per F11 debrief methodology lesson #3: separate test-surface grep at L3 design time: `grep -rln 'allowlist.*peers\|allowlist.*channels\|allowlist.*roles\|allowlist.*dm_admission' tests/`.

**(e) Tests added**:
- `TestSchemaV24` class in `tests/test_db_migration.py` with 4+ tests: (i) fresh-DB shape; (ii) idempotency on rerun; (iii) legacy-v23-row migration with peers + channels + roles + dm_admission preserved per the collapse rules; (iv) the agents.connector_acls JSON column row-rewrite works in lockstep; (v) the index rename applies cleanly.
- Cross-product matrix tests in `tests/test_connectors_acl.py` covering: (peer in/not in allowlist) × (dm_allowed True/False) × (admit_dms None/True/False) × (is_dm True/False) for DM admission; (channel guild_id null/specific/mismatched) × (envelope guild_id) for guild admission. Per F11 debrief recommendation about codifying cross-axis HAT-discovered bugs as substrate-test-matrix-by-default.
- Existing ACL tests that pin flat-axis behavior: reclassified as Category A (pin pre-v24 historical shape — `TestPreV24AllowlistShape` class or similar) or rewritten for the structured shape per case-by-case judgment at L3 design time.

**L4 — UI — discoverable-dropdown grouping + per-peer DM toggle + allowlist editor refresh.** Frontend updates atomic to the L3 storage:
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` already groups by server in its display; extend to emit `{guild_id, channel_id}` / `{guild_id, role_id}` tuples on selection (not just the bare ID)
- Allowlist editor in `connector-editor.js` (post-F11 rename) updates:
  - dm_admission row STAYS as account-scope 3-state radio (`Admit all DMs` / `Deny all DMs` / `Admin-approved (per-peer)`); label revised for clarity. Optional Literal-value rename `"allowlisted-peers-only"` → `"admin-approved"` per DD: DM Admission Model is reflected in the radio's `value` attribute (post-v24 migration).
  - Peers section: each peer row gains a slider/toggle for "DM allowed" (bool). The toggle is rendered conditionally on the account-scope `dm_admission` value — visible + interactive ONLY when `dm_admission="admin-approved"`; hidden (or shown disabled with explanatory tooltip) under `"all"` (per-peer ignored; everyone admitted) and `"none"` (per-peer ignored; nobody admitted). UI test must verify this conditional rendering.
  - Channels section: dropdown selection now stores `{guild_id, channel_id}`; existing flat entries (post-v24 with null guild_id) render with a "legacy entry" indicator + a "Re-scope to current guild" affordance
  - Roles section: same shape as channels
- Per-agent overlay in `agent-editor.js` Connectors tab follows the same UI patterns (with the per-axis-tri-state-override "inherit / explicit-list / empty" semantics preserved)
- Browser tests: ~10-15 connector-touching browser tests need fixture + assertion updates (test data now includes per-peer DM toggle state + channel/role tuples); 4-8 new browser tests added for the legacy-entry indicator + per-peer toggle behavior. **Per F11 debrief recommendation #2, a Phase 5c architect cycle for L4 enumerates the exact browser-test file set + estimated per-file diff size before implementation** (F11's L2 had a 10→112 URL undercount in `test_db_api.py`; same recon discipline applies).
- `tests/browser/test_flow_studio_connector_dm_admission_row.py` — STAYS, but is **extended** (not deleted) to additionally verify per-peer DM toggle conditional rendering (visible under `admin-approved`, hidden under `all`/`none`). The dm_admission row itself stays in the editor.

### Checkpoints

- [x] **L1 land**: backend test suite green at 2749+ (no test additions in L1); `git grep -E "connector_account|ConnectorAccount" the_one/ tests/` returns zero hits in source files (allowed residue documented at gate); test filenames renamed in lockstep; 0 new errors / 0 new failures vs F11 baseline (2749/4/0/254s)
- [x] **L2 land**: backend test suite green at 2749+ (no new tests in L2; structural-no-op extraction); `the_one/agents.md` M11 section has the new `two-symmetric-paths-in-acl` convention block
- [x] **L3 land**: migration test suite green including new `TestSchemaV24`; backend test suite green at 2754+ (L3 adds ~5 new schema tests + 12-cell cross-product matrix); `account.config.allowlist` validator accepts new shape (per-peer dm_allowed field; dm_admission Literal unchanged); ACL helpers consume structured-tuple shape AND composition chain; in-memory fixtures across all connector + ACL + db tests updated to use new shape; index rename `idx_pending_approvals_account_peer_status` → `idx_pending_approvals_connector_peer_status` applied
- [x] **L4 land**: browser test suite green; per-peer DM toggle UI renders conditionally on account-scope `dm_admission` mode (visible under `admin-approved`, hidden/disabled under `all`/`none`); legacy-entry indicator renders for null-guild_id channels/roles; dm_admission row stays + label revised for clarity; agent-editor Connectors tab mirrors the new shape; ~10-15 browser test fixture updates + 4-8 new tests including the conditional-render verification
- [x] **Flight land**: combined diff reviewable; PR opened as draft; no new flakes; pre-existing browser failures (2) still present (not F12-caused)

### Adaptation Criteria

**Divert if**:
- L1's grep gate surfaces a 3rd-party-library or generated-file reference that requires unbounded sweeping — operator decision on allowlist addition vs deferral
- L2's extraction surfaces unexpected cross-function state (e.g. a helper that admits_inbound shares with another path the recon missed) — re-scope L2 OR split into L2a (extract) + L2b (untangle helper sharing)
- L3 migration v24 surfaces a row that fails the validator after row-rewrite (e.g. operator's seeded data has a malformed allowlist that wasn't caught by the v23 validator) — split into v24-row-rewrite + v25-validator-tightening, OR pre-clean during v24
- L4 browser test updates touch >30% of the connector-touching browser tests — operator decision on whether to split L4 into L4a (storage-aware fixture updates) + L4b (UI behavioral verification)
- L3 cross-product matrix tests surface ACL semantic differences vs pre-F12 baseline beyond the documented null-guild_id-is-permissive rule — re-scope L3 to address the unintended semantic change OR split into F12a/F12b

**Acceptable variations**:
- L1 may discover additional snake_case identifier sites the architect cycle-1 grep undercounted (similar to F11's `test_db_api.py` 10→112 surprise); rename in lockstep within L1
- L3 may discover additional fixture-data sites that need updating beyond the test_db_migration.py focus; update in lockstep
- L4 may discover that the discoverable-dropdown already does some of the grouping work; reduce scope correspondingly
- L3 may discover that one of the cross-product matrix cases doesn't fit the per-axis-tri-state-override convention (e.g. null-guild_id with non-empty channels needs a 4th state); add the case + explicit decision in L3 design

### Legs

- [x] `snake-case-identifier-rename` — F11 prereq carry-forward; ~35 def + ~292 sites (Python + Markdown + browser tests); mechanical rename with explicit grep-gate enumeration; Phase 5c architect cycle runs literal grep pre-implementation
- [x] `acl-extraction-and-symmetric-paths-convention` — extract `admits_inbound` into `_admits_inbound_dm` + `_admits_inbound_guild` dispatcher; codify `two-symmetric-paths-in-acl` M11 convention in agents.md; semantically a no-op
- [x] `storage-shape-v24-migration-and-acl-semantics` — Pydantic shape change + schema v24 row-rewrite for 3 axes in `account.config.allowlist` + parallel updates to `agents.connector_acls` + index rename + ACL helper updates (`_admits_inbound_dm` / `_admits_inbound_guild` / `admits_outbound` / `admits_dm_peer` for structured tuples + per-peer DM check) + peer-list consumer site updates in `_inbound.py` / `api.py` / `_discord.py` + `TestSchemaV24` with 5+ tests + cross-product matrix tests. **One large atomic leg** — operator-confirmed merge of original L3+L5 to avoid transient ACL-vs-storage-shape state.
- [x] `ui-discoverable-dropdown-and-per-peer-dm-toggle` — frontend updates atomic to L3 storage; allowlist editor + agent-editor Connectors tab; legacy-entry indicator; per-peer DM toggle UI (conditional on `dm_admission=admin-approved` mode); dm_admission row STAYS with revised label; ~10-15 browser test fixture updates + 4-8 new tests including conditional-render verification; Phase 5c architect cycle enumerates exact test surface pre-implementation

---

## Post-Flight

### Completion Checklist

- [x] All 4 legs completed
- [ ] Code merged
- [x] Backend test suite: 2754+ passed / 4 skipped / 0 errors / 0 failures (allowing for `TestSchemaV24` + cross-product matrix tests in L3) — final: 2767 passed / 4 skipped / 0 errors
- [x] Browser test suite: green except 2 pre-existing-main failures (not F12-caused) — final: 438 passed / 2 pre-existing-main failures
- [x] Migration test suite green including `TestSchemaV24`
- [x] Repo-wide grep for snake_case identifier rename returns 0 hits in source files (per L1's explicitly-enumerated gate)
- [x] `the_one/agents.md` M11 section has `two-symmetric-paths-in-acl` convention block; F10 Known Issues "Hierarchical allowlist axes (F10 L5 HAT finding)" marked `[x]`; F11 Known Issues "snake_case identifier rename residue" marked `[x]`
- [x] Mission outline `mission.md` Flight 12 entry marked `[x]` with one-line summary

### Verification

Four independent signals confirm the flight achieved its objective:

1. **Mechanical (grep)**: `git grep -nE "connector_account|ConnectorAccount" the_one/ tests/` returns zero hits in source files post-L1; `git grep -nE "dm_admission" the_one/ tests/` returns zero hits in production code (migration v24 body retains as the FROM side; tests retain in TestSchemaV23-and-earlier per Category A discipline).

2. **Regression (test suites)**: backend suite at 2753+ passing / 0 errors / 4 skipped; migration test suite green (v24 + all priors); browser suite green except 2 pre-existing-main failures (not F12-caused).

3. **Semantic (cross-product matrix)**: L3's cross-product matrix tests pass — admission decisions for representative (peer, channel, role, guild, is_dm) combinations match documented behavior including the legacy null-guild_id-is-permissive backwards-compat rule.

4. **Operator (smoke test)**: operator opens a fresh dev environment, creates a connector, allowlists a peer (with DM toggle), selects 2 channels from different servers via the dropdown, sends test messages from Discord — admission decisions match the operator's allowlist intent in both directions, the legacy-entry indicator does not surface for new entries, the per-peer DM toggle reflects in the UI consistently across the connector editor and the agent-editor Connectors tab.
