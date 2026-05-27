# Flight: ACL DM-admission + channels-axis UI split

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] **#8** — Pairing question resolution: F9 substrate landed (resolver hook, storage, endpoints, banner, allowlist mutation) but L8 HAT step-4 surfaced an ACL semantics + UI axis-conflation gap that prevents end-to-end usability when `account.config.allowlist.channels` is non-empty. F10 closes both gaps and re-runs the HAT to fully close criterion #8.

Indirect support:
- **#18** (15-minute onboarding) — fixing the UI conflation lets a new operator express "guild channel + DM admission" without hitting the trap.
- **#19** (full-day daily-driver) — F9's dual-flow becomes a reliable daily-driver primitive once the gap is closed.

---

## Pre-Flight

### Objective

Close the two F9 L8 findings together: (a) substrate — add an account-scope `dm_admission` axis to `allowlist` so DM admission is independent of the `channels` guild-restriction axis, with the dispatcher consulting it correctly; (b) UI — surface the new axis in the connector account allowlist editor as a 3-value selector + per-agent overlay as an opt-out checkbox; (c) re-run L8 HAT against a channels-restricted account to verify dual-flow now works end-to-end.

### Open Questions

All resolved at flight-design time:

- [x] **Substrate shape** (a/b/c from F9 L8 record) — **(b) new `dm_admission` axis**. Pure addition; preserves F8 L8 guilds-axis posture; supports legacy-preservation migration cleanly. Operator-confirmed.
- [x] **`dm_admission` values** — `Literal["none", "allowlisted-peers-only", "all"]`. Three explicit values map to operator-meaningful posture: block, peer-gated (the F9 dual-flow's intended target), open. NOT a boolean — the three-way distinction matters for the migration default and for the F9 flow's "approved peers can DM" semantic.
- [x] **Fresh-account default** — `allowlisted-peers-only`. Matches the F9 mental model: peer approval is the gate; no pre-shared code needed. (PAIR-prefix fallback still works via L1 resolver's existing path.)
- [x] **Legacy-account migration default** — preserve existing behavior. The migration walks v21 `connector_accounts` rows: if `config.allowlist.channels` is empty/absent → `dm_admission = "all"` (existing behavior admitted all DMs); if `config.allowlist.channels` is non-empty → `dm_admission = "none"` (existing behavior denied all DMs against channels mismatch). No legacy operator sees a behavior change unless they explicitly switch.
- [x] **Per-agent overlay shape** — single boolean field `admit_dms` in `agent.connector_acls[account_id]`, semantic: `null|absent` = inherit account-scope; `false` = opt-out (this agent denies DMs regardless of account-scope `dm_admission`). NO `true` value (no need to "force-admit" — that would just be account-scope `all`). Operator-confirmed: "uncheck in agent override (not add new)".
- [x] **Per-agent UI affordance** — one checkbox in the per-agent ACL editor (in `connectors-tab.js`'s expanded details panel) labeled "Admit DMs (inherit from account)". Checked = inherit (default); unchecked = opt out. Disabled-and-checked-visually when account-scope is `none` (no DMs reach the dispatcher anyway). Disabled-and-checked-visually when account-scope is `all` AND the operator could uncheck to narrow — wait, that's the normal interactive state. Re-do: the checkbox is always interactive when account-scope is `allowlisted-peers-only` or `all`; greyed-out-and-checked when account-scope is `none` (no DMs to opt out from).
- [x] **HAT inclusion** — yes, optional final leg re-running F9 L8's 8 steps against a channels-restricted account.

### Design Decisions

**§1. Substrate shape: new `dm_admission` axis on account-scope allowlist** (operator-confirmed shape b):
- New key `dm_admission: Literal["none", "allowlisted-peers-only", "all"]` in `account.config.allowlist`.
- **Validator extension at `the_one/db/models.py:305-341`** — the existing `ConnectorAccount.config` `@field_validator` enforces:
  - Allowed keys: `{"peers", "channels", "guilds", "roles"}` (line 318) — **extend to add `"dm_admission"`**.
  - Required keys: `{"peers", "channels"}` (line 323) — leave unchanged; `dm_admission` is optional.
  - Per-key value type: `list` of `str` (line 333) — **extend to special-case `dm_admission` as a `Literal` string (one of `"none"` / `"allowlisted-peers-only"` / `"all"`), branching by key name in the validation loop**.
  - Default for fresh `model_validate` of legacy JSON without the key: `"allowlisted-peers-only"`. Apply this at the validator (set if absent) so the model always carries the key after a `model_validate` round-trip.
- Dispatcher consults the new axis in `the_one/connectors/_acl.py:admits_inbound`. Insertion point: **between** the existing channels-axis check at line 323-329 and the guilds-axis check at line 334-340. Semantic:
  - If `is_dm=False` (guild message), `dm_admission` is irrelevant — channels-axis already handled the check at line 323-329. Skip the dm_admission gate.
  - If `is_dm=True`:
    - account-scope channels-axis check at line 323-329 must NOT fire for DMs. Wrap the existing channels-axis check in `if not is_dm:` so it's only consulted for guild messages.
    - Consult `allowlist.dm_admission`:
      - `"all"` → admit.
      - `"none"` → deny.
      - `"allowlisted-peers-only"` → admit IFF peer_id is in `allowlist.peers`. (The peers-axis check at line 316-322 already enforces this — when `allowed_peers` is non-empty AND peer_id is not in it, that path denies. When `allowed_peers` is empty, the F9 flow doesn't apply: the operator hasn't approved anyone; deny.)
- Trade-off: this changes the contract of `allowlist.channels` from "applies to all inbound" to "applies to guild messages only." That's the operator-intuitive interpretation but does shift from the pre-F10 semantic. Documented in the migration block + Pydantic field docstring.

**§2. F8 L8 guilds-axis posture preserved** (locked at planning):
- F8 L8 documented "guild_id is None (DM context) against a non-empty guilds list denies" as the deliberate "DMs out-of-scope under guild restriction" semantic. F10 does NOT change this — `dm_admission` operates independently of `guilds`. An operator who sets `guilds=[guild-A]` + `dm_admission=all` says "this account is scoped to guild-A AND admits all DMs." Two independent restrictions composing.
- BUT — wait. If `dm_admission=all` and `guilds=[guild-A]`, a DM (guild_id=None) hits the guilds-axis check at line 334 and denies (None not in [guild-A]). The dm_admission gate never gets consulted because guilds-axis denied first. Same for non-empty roles.
- Resolution: re-order the axis checks so DMs short-circuit the guilds/roles checks. When `is_dm=True`, skip BOTH channels AND guilds AND roles axes; only consult peers + dm_admission. When `is_dm=False`, consult all four as today.
- This is a deeper semantic shift than just "channels-axis gets is_dm short-circuit." It says: **all guild-context restrictions (channels, guilds, roles) become guild-only when the inbound is a DM**. The operator's intent of "restrict to specific guilds/channels/roles" is preserved for guild messages; DMs go through the orthogonal `dm_admission` + `peers` gates.
- The F8 L8 documented posture is INVERTED here: previously "DMs out-of-scope under guild restriction" (deny); now "DMs orthogonal to guild restriction" (consult dm_admission). Document the inversion in `_acl.py:admits_inbound` docstring + a comment block in the L1 leg.

**§3. Per-agent overlay shape: `admit_dms` boolean field, opt-out only** (operator-confirmed):
- New key `admit_dms: bool | None` in `agent.connector_acls[account_id]`. Tri-state inheritance pattern matches the existing 4 axes (`peers`, `channels`, `guilds`, `roles`):
  - `None` / absent: inherit account-scope.
  - `False`: explicit opt-out (this agent denies DMs).
  - `True`: redundant (= explicit affirm-inherit). Allowed but UI does not produce it.
- **Validator extension at `the_one/agent/config.py:262-322`** — the existing `connector_acls` `@field_validator` enforces:
  - Outer type annotation `dict[str, dict[str, list[str] | None]]` (line 230) — **widen to `dict[str, dict[str, list[str] | bool | None]]`** to accept boolean values for the new key.
  - Allowed inner-keys: `{"peers", "channels", "guilds", "roles"}` (line 310) — **extend to add `"admit_dms"`**.
  - Per-key value type validator: enforces `list[str] | None` (line 313-318 region) — **branch by key name so `admit_dms` validates as `bool | None` and the existing 4 axes keep their `list[str] | None` validation**.
- Dispatcher consults this in `_acl.py:admits_inbound` after the account-scope `dm_admission` gate passes: if `agent_acl["admit_dms"] is False` AND `is_dm`, deny.

**§4. Schema migration v22** (row-rewrite, JSON columns):
- No SQL DDL change needed. Both `connector_accounts.config` and `agents.connector_acls` are TEXT (JSON) columns.
- **Precedent**: `schema.py:286-303` (v7 row-rewrite) — NOT v17/v18/v20/v21 (those are ALTER ADD COLUMN, wrong precedent for the row walk this leg needs).
- Migration block at the tail of `ensure_schema` bumps CURRENT_VERSION 21 → 22 and walks existing `connector_accounts` rows:
  - For each row, decode `config` JSON, mutate `allowlist.dm_admission` per the legacy-preservation rule (`"all"` if `allowlist.channels` is absent/empty/None; `"none"` otherwise), re-encode, UPDATE row.
  - `agents` table: no in-place rewrite — absent `admit_dms` key is the inherit-from-account default.
- Validator-default coupling (per §1 / §3): when a legacy JSON without `dm_admission` flows through `model_validate` AFTER the migration, the migration has already written `dm_admission` into the JSON, so the validator's default (`"allowlisted-peers-only"`) is reached ONLY for rows that bypass the migration (which shouldn't happen for live operator data, but defensively the validator-default still produces a sane result).

**§5. UI: account-scope allowlist editor** (new row in `connector-account-editor.js:renderAllowlistSection`):
- Insert a new "DM admission" row between the existing peers axis (line 2030+) and channels axis (line 2045+). The placement is intentional: peers axis defines WHO can DM; dm_admission defines WHETHER DMs are admitted at all.
- Render as a 3-value selector (radio group OR `<select>`):
  - "Deny all DMs" (`none`)
  - "Admit DMs from approved peers" (`allowlisted-peers-only`)
  - "Admit all DMs" (`all`)
- Tooltip / help text: "DMs (direct messages to the bot) are admitted independently of channel restrictions. Approved peers are those on the Peers allowlist above."
- Dirty-tracker integration via the existing `data-allowlist-*` slot pattern; save flow via the existing `collectFormData` path.

**§6. UI: per-agent overlay** (`connectors-tab.js`):
- Add a single checkbox row at the top of the per-agent ACL editor (in the expanded details panel) labeled "Admit DMs from this account" with the inherit-from-account caveat in the hint text.
- Checked = inherit (no per-agent override; `admit_dms` absent from the agent's per-account ACL).
- Unchecked = explicit opt-out (`admit_dms: false`).
- Disabled-and-checked when account-scope is `none` (with hint "Account denies all DMs; per-agent override not applicable").
- Save flow: `collectFormData` + the existing `connector_acls` write path.

**§7. Carry-forwards**: NONE — F10 is tightly scoped. Any items found during recon get classified into routine-maintenance per the project's convention.

### Prerequisites

- [x] F9 merged or merge-pending (PR #78). F10 branches from `flight/09-pairing-resolution-and-detach` HEAD if F9 hasn't merged yet; otherwise from `main`. **Decision**: F10 branches from F9 HEAD to avoid blocking on PR merge; rebase onto main once F9 lands.
- [ ] **Create F10 branch**: `git checkout -b flight/10-acl-dm-admission-axis-split` from `flight/09-pairing-resolution-and-detach` HEAD (commit `07d3093`) at L1 start.
- [ ] Discord test guild + ≥2 burner accounts available (operator-already-paired + 1 unpaired) for L5 HAT.
- [ ] Inherited stray `docker-compose.yml` modification still present (4th flight inheriting now); operator action to commit or stash recommended before F10 commit.

### Pre-Flight Checklist

- [x] All open questions resolved (8 of 8 at flight-design time)
- [x] Design decisions documented above (§1-§7)
- [ ] Prerequisites verified
- [x] Validation approach defined (unit tests + browser tests + operator HAT re-run)
- [x] Legs defined (see In-Flight § Legs)

---

## In-Flight

### Technical Approach

F10 ships in **4 mandatory legs + 1 optional HAT leg**:

**L1 — Substrate: dm_admission axis + admit_dms per-agent + migration v22** (`acl-dm-admission-substrate`). Extend Pydantic validators per §1 (account-scope at `db/models.py:305-341`) and §3 (per-agent at `agent/config.py:230,262-322`) — both have strict per-key validators that reject unknown keys; both need extension PLUS branch-by-key value-type validation (the new keys are Literal-string and bool respectively, NOT list[str]). Add migration v22 to `the_one/db/schema.py` mirroring the v7 row-rewrite precedent at `schema.py:286-303` (NOT the ALTER-ADD-COLUMN v17/v18/v20/v21). Modify `the_one/connectors/_acl.py:admits_inbound` per §1-§2: re-order axis checks so DMs skip channels/guilds/roles and consult dm_admission + peers; add the per-agent `admit_dms` consultation per §3. Update the dispatcher docstring at `_acl.py` to document the new posture (inverting F8 L8's "DMs out-of-scope under guild restriction").

**L1 tests** in `tests/test_connectors_acl.py` (730 LOC, 58 tests today — NOT a new file):
- New tests: 9 combinations covering account-scope `dm_admission` ∈ {`none`,`allowlisted-peers-only`,`all`} × is_dm ∈ {True} × peer-on-allowlist ∈ {True, False, peers-empty}. Plus 3 per-agent `admit_dms=False` opt-out tests.
- **Three existing tests must be inverted** to match the new posture (per cycle-1 Architect):
  - `test_account_guilds_restrictive_denies_dm_envelope` (`:486`) — F8 L8 posture pins; now needs to assert the new outcome (DM with guild-restricted account → admit if dm_admission permits + peer allowlisted).
  - `test_account_roles_empty_member_roles_denies_when_restricted` (`:592`) — same inversion.
  - `test_account_roles_member_roles_none_denies_when_restricted` (`:605`) — same inversion.
- Migration tests: `tests/test_db_migration.py::TestSchemaV22` for fresh-DB + idempotent + legacy-preservation (3 sub-cases: empty-channels row → `dm_admission="all"`; non-empty-channels row → `dm_admission="none"`; absent-allowlist row → no change).
- Repository tests: round-trip of the new `allowlist.dm_admission` field + per-agent `connector_acls[account_id].admit_dms` field in `tests/test_db_repositories.py`.

**L2 — UI: account-scope DM admission row** (`account-scope-dm-admission-row`). Extend `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderAllowlistSection` (line 2030-2088) with a new "DM admission" row per §5 between peers and channels. Wire into `getFormSnapshot` (dirty-tracker) and `collectFormData` (save flow). The selector value persists to `account.config.allowlist.dm_admission`. CSS for the row matches the existing `.field-row.admin-pf-row.connector-account-acl-fieldrow` pattern. Tests: extend existing connector-account-editor browser tests; add a new test for the DM-admission selector save/load round-trip.

**L3 — UI: per-agent overlay opt-out checkbox** (`per-agent-dm-admission-opt-out`). Extend `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`'s per-agent ACL editor (the expanded details panel for each account, where the existing peers + channels axes render at line 522-523) with the "Admit DMs from this account" checkbox per §6. **Implementation note (per cycle-1 Architect)**: `_buildAxisRow` (line 293) is a chip-list/checkbox-list primitive for axis-shaped values (`list[str] | None`); `admit_dms` is boolean. Add a **NEW sibling helper** (e.g. `_buildAdmitDmsRow(accountAcl, accountScopeDmAdmission)`) — do NOT parameter-extend `_buildAxisRow`. Wire into the agent's `collectFormData` write path (the `connector_acls` write site in `studio.js`). Tests: extend `test_flow_studio_always_listen_toggles.py`-style browser tests; verify the checkbox state round-trips to `agent.connector_acls[account_id].admit_dms`.

**L4 — Tests + HAT re-design** (`hat-redesign-and-test-rerun`). Update `tests/browser/test_flow_studio_connector_discord_vocabulary.py` and `tests/browser/test_flow_studio_connector_allowlist_dropdown.py` (per cycle-1 Architect) and any other browser tests that assert allowlist axis count (now 5 fields: peers, dm_admission, channels, guilds, roles) — there will be drift in any test counting `[data-allowlist-chiplist-slot]` slots or expecting a specific axis count in the editor. Re-design the L8 HAT spec inline in this flight's L5 leg to incorporate the new DM-admission setup steps (operator sets `dm_admission = allowlisted-peers-only` before step 1; verifies the per-agent checkbox in step 5b; etc.).

**L5 (optional, recommended) — HAT for F9 closure** (`hat-acl-split-verify`). Operator-driven walkthrough re-running the F9 L8 8 steps against an account configured with `channels=[guild-channel-id]` + `dm_admission=allowlisted-peers-only`. The expected outcome differs from L8: step 4 (B1's follow-up DM) now succeeds because dm_admission + peer-allowlist combination admits B1's DM independent of the channels axis. Additional step 5b: navigate to the agent editor's Connectors tab; uncheck "Admit DMs from this account" on one of the attached agents; verify subsequent DMs to that agent don't engage but other attached agents still do.

Inline-hotfix-during-HAT discipline (F7 L12 / F9 L8 precedent). Operator-judged satisfaction gates flight-land. Mission criterion #8 marked fully closed when L5 passes.

### Checkpoints

- [x] **L1**: schema v22 + Pydantic models extended + `_acl.py` re-ordered; unit tests + migration tests + repo tests pass; legacy-row preservation verified.
- [x] **L2**: account-scope DM admission row renders; save/load round-trips; existing allowlist tests pass.
- [x] **L3**: per-agent opt-out checkbox renders + round-trips; the existing per-agent ACL save flow unchanged.
- [x] **L4**: test drift cleaned; full suite green; pre-L4 baseline matched-or-improved.
- [ ] **(optional) L5**: HAT 8-step + 1-substep walkthrough; mission criterion #8 fully closed.

### Adaptation Criteria

**Divert if**:
- L1's `admits_inbound` re-ordering breaks existing dispatcher tests beyond surface drift. The F8 L8 guilds-axis posture inversion is the riskiest call; if reviewer or testing surfaces that a real operator depends on the "DMs out-of-scope under guild restriction" semantic (e.g. their setup uses an empty channels axis + non-empty guilds list to admit guild messages but block DMs), pause and reconsider §2 — possibly add an `is_dm` short-circuit ONLY for channels (the actual F9 L8 finding) and keep guilds/roles per the F8 L8 posture.
- Migration v22 surfaces a Pydantic v2 default-vs-migration-write conflict (e.g. legacy rows being re-defaulted to `"allowlisted-peers-only"` on read instead of preserving the migration-inserted `"all"`/`"none"`). Re-validate the model_validate vs model_dump round-trip discipline.

**Acceptable variations**:
- L2 and L3 can land in either order; both are UI-only and don't depend on each other.
- The HAT (L5) can be deferred to a separate post-merge session if L4 lands clean and the operator wants to merge sooner.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `acl-dm-admission-substrate` — schema v22 migration + Pydantic field additions + `_acl.py:admits_inbound` re-order + unit/migration/repo tests.
- [x] `account-scope-dm-admission-row` — connector-account-editor.js allowlist row + dirty-tracker + save flow + tests.
- [x] `per-agent-dm-admission-opt-out` — connectors-tab.js per-agent checkbox + save flow + tests.
- [x] `hat-redesign-and-test-rerun` — browser-test count drift cleanup + L8-spec re-design for new flow.
- [ ] `hat-acl-split-verify` *(optional)* — operator-driven HAT against channels-restricted account.

---

## Post-Flight

### Completion Checklist

- [ ] All mandatory legs (L1-L4) completed; optional L5 HAT completed or explicitly skipped
- [ ] Mission criterion #8 (pairing) checked off fully in `mission.md` (F9's `[~]` becomes `[x]`)
- [ ] Test suite baseline recorded vs F9's 2721 / +6 browser
- [ ] `agents.md` — if any new convention emerges from the re-order (e.g. "is-dm-orthogonal-to-guild-restriction"), codify. NONE pre-committed.
- [ ] Flight-debrief written. **Note**: per operator decision, F9 + F10 debriefed together AFTER F10 lands (single combined debrief). Skip F9-only debrief; one combined retrospective covers the dual-flow + axis-split arc end-to-end.

### Verification

- **Tests**: `make test-unit` passes; new migration tests pass; ACL unit tests pass; browser tests for connector-account-editor + connectors-tab pass; F9 baseline matched or improved.
- **End-to-end**: HAT (if L5 ran) passes 8-step + 1-substep scenario; operator judges shippable.
- **Behavior preservation**: legacy `connector_accounts` rows preserve their pre-F10 dispatcher behavior (empty-channels rows admit DMs; non-empty-channels rows deny DMs) UNLESS the operator explicitly switches `dm_admission`.

---

## Design-Review Cycle Log

**Cycle 1 (2026-05-27, Architect)**: needs-rework. Two HIGH: Pydantic validator strictness at `db/models.py:305-341` and `agent/config.py:262-322` — both reject unknown keys AND enforce per-key value types as `list[str]`; the new `dm_admission` (Literal-string) and `admit_dms` (bool) both need explicit validator extension + branch-by-key value-type validation. Two MEDIUM: test file path wrong (`tests/test_connectors_acl.py` not `test_acl_admits_inbound.py`) + 3 existing tests at `:486`, `:592`, `:605` need inversion. One LOW: §4 migration cited v17/v18/v20/v21 ALTER-ADD-COLUMN as precedents; v7 row-rewrite at `schema.py:286-303` is correct.

All addressed in §1, §3, §4, L1 description, L3 description, L4 description.

**Cycle 2 (2026-05-27, Architect)**: approve. All six cycle-1 issues verified resolved. Two non-blocking cosmetic suggestions accepted as-is.

**Flight design ready for execution.** No further cycles needed.
