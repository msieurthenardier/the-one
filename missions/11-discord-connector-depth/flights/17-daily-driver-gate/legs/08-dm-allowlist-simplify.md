# Leg: dm-allowlist-simplify

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (substrate migration + ACL + approve-flow + UI) — L3 once-over Leg D. **Closes the F16-parked mission Known Issue (F3a).** Visual acceptance: `discord-approval-flow` (with E/F).

## Objective

Post-F16 the account-scope `peers` axis gates **DMs only**, so a user being in the list already means "this person may DM." Collapse the redundant two-step: **relabel the users/peers allowlist section "Direct Messages"**, **drop the per-peer `dm_allowed` flag** (in-list = can-DM), **keep the `dm_admission` 3-mode policy but relabel it** (Anyone / Only these people / No one), and **fix the approve flow** to add an approved peer as allowed. This removes the limbo state that gave Chuck R "no agents available" and closes the F16-parked Known Issue.

## Context

- **F3a (this flight, confirmed live):** `allowlist.dm_admission="admin-approved"` + a peer with `dm_allowed:false` → DM gated at admission → `no-eligible` → "no agents available." The two-step (approve adds `{id, dm_allowed:False}`, operator must flip a toggle) is confusing in real use. F16's disposition was "park until F17 evidence; scope a follow-on only if confusing" — it is.
- **Current shape (recon, F16 context):** peers stored `{id, dm_allowed}`; `dm_admission` Literal `"none" | "admin-approved" | "all"` (`_acl.py:402`); DM admit rule `_admits_inbound_dm` ≈ peer-in-list AND (`dm_admission=="all"` OR (`admin-approved` AND `dm_allowed`)) with a list-membership precedence deny at `_acl.py:559` BEFORE dm_admission. Approve handler appends `{id, dm_allowed:False}` (`api.py:2716`).
- **New model (operator-confirmed):** the "Direct Messages" section = who may DM. A peer in the list can DM (no per-peer flag). `dm_admission` becomes the section's top policy:
  - **Anyone** (`all`) → any DM admitted; the list is irrelevant.
  - **Only these people** (`admin-approved`) → admit iff the peer is in the Direct Messages list.
  - **No one** (`none`) → no DMs.
- **Per-agent `connector_acls.peers` (F15 L4 guild-routing) is a SEPARATE axis — untouched.** This leg is account-scope DM only.
- **Mission constraints:** no agent-loop change; substrate migration is in scope; no env-var seam.

## Resolved at design review (implement to these — cite file:line)

- **Schema = v28** (`CURRENT_VERSION=27` at `the_one/db/schema.py:15` → bump to 28). **JSON-column row-rewrite** (the unanimous v24–v27 pattern, NOT ALTER): `SELECT id, config FROM connectors`; for each row, if `allowlist.peers` entries are dicts carrying `dm_allowed`, pop `dm_allowed` → bare `{id: str}`; UPDATE-when-changed; `INSERT OR IGNORE INTO schema_version VALUES (28)`. **Idempotency guard:** skip a row if `peers` is empty OR `peers[0]` has no `"dm_allowed"` key (mirror v24's guard at `schema.py:1252`). Defensive `connectors`-table-existence check like v25/v26/v27. **Do NOT modify the v24 block** (it writes `{id, dm_allowed}` during backfill; v28 strips it later in the same pipeline — intentional, per the v26 comment). Only `connectors.config` needs touching (per-agent `connector_acls.peers` was already stripped by v26).
- **Target shape = `{id: str}` bare dicts** (parallel to the post-v26 per-agent shape; NOT plain strings — avoids a future migration + matches precedent).
- **[HIGH] `models.py` validator (`:354-391`) MUST be updated in the SAME commit as the migration.** It currently requires exactly `{id, dm_allowed}` (rejects missing/extra keys) → a post-migration `{id}` row fails `Connector.model_validate()` on the read path (`repositories._row_to_model`) → every connector read crashes. Change the required-key set `{"id","dm_allowed"}` → `{"id"}`, drop the `dm_allowed` bool-check, update the `:354` docstring. (`_acl.py` reads via `.get("dm_allowed", False)` so it's safe pre/post — only the strict Pydantic validator is the hazard.)
- **`_admits_inbound_dm` rewrite (`_acl.py` ~`:539-629`):** keep step 1 (`admit_dms=False`→deny). Then gate on `dm_admission` FIRST: `none`→deny; `all`→**skip the peers-axis membership check entirely** (admit regardless of the list — this REMOVES the current `:559-565` pre-precedence deny that denies a non-listed peer even under `all`); `admin-approved`→admit iff peer is in `allowlist.peers` (drop the `:592` `dm_allowed` check). Empty list: `all`→admit, `admin-approved`→deny ("not in allowlist"), `none`→deny. **`_admits_inbound_guild` + the F16 DM-only carve-out (`_acl.py:683`) stay untouched.** Default `dm_admission` stays `"admin-approved"` (safe default).
- **Approve-flow writers → `{id}` (no `dm_allowed`):** `approve_peer_approval` (`api.py:2826`) AND the PAIR-prefix success path (`_inbound.py:502`). (`_discord.py:1908` is read-only — safe.) **This is the F16-parked Known Issue fix.**
- **UI (4 files, contained):** `connector-editor.js:2228` "Users"→**"Direct Messages"** + `:2229` description; `:2274-2281` dm_admission options → **"No one" / "Only these people" / "Anyone"** + `:2254` tooltip; **remove the per-peer `dm_allowed` toggle** (`discoverable-dropdown.js:277-298`, the `valueShape==='peer'` block); `_wrapId` `discoverable-dropdown.js:110-111` → `{id}`; `connector-editor.js:3627` → `{id}`; `connectors-tab.js:727` → `{id}`.
- **Latent-bug fix (fold in):** `studio.js:2133` writes per-agent peers as `{id, dm_allowed:true}`, but the per-agent validator (`agent/config.py:396`) ALREADY rejects `dm_allowed` (post-v26) → the per-agent ACL editor's peer-add is currently broken. Change `studio.js:2133` → `{id}`.
- **Test blast radius (~10 files + 1 deletion):** rewrite the 12-cell matrix `TestDmCompositionMatrix` (`test_connectors_acl.py:1183`, collapses to 3 axes ≈6 cells) + `_acl_shape_helpers.py:35-53` (`_account_peers`→`{id}`); **DELETE `tests/browser/test_flow_studio_per_peer_dm_toggle.py`** (tests the removed toggle); fix shape assertions in `test_db_api.py` (`:2043/:2209/:2229/:2354`), `test_connectors_inbound.py` (`~:1797/:2149`), `test_connectors_discord.py:1392`, `test_connector_history_tools.py:569`, `test_db_repositories.py` (`:1700-2050`), `test_pairing_peers_decoupling.py:142`; ADD a v28 migration test (`test_db_migration.py`) + an **F3a-reproduction test** (admin-approved + approve peer + immediate DM → admitted — permanent regression net). v24 migration tests stay (v24 immutable).

## Acceptance Criteria

- [x] **Storage migration (vN):** account-scope `allowlist.peers` rewritten from `[{id, dm_allowed}]` → `[{id}]` (drop `dm_allowed`); migration is idempotent + backward-readable (legacy `{id, dm_allowed}` entries read as `{id}`). The exact target shape (`{id}` dict vs plain id string) matches the cleanest fit with the per-agent peers shape — resolved at design.
- [x] **ACL composition rewrite (`_acl.py` `_admits_inbound_dm`, ~`:504`/`:559`/`:571`):** drop the `dm_allowed` term. New DM admit: `none`→deny; `all`→admit (list ignored); `admin-approved`→admit iff peer in the Direct Messages list. The F16 "account peers is DM-only / inert in guild" carve-out (`_admits_inbound_guild`) stays. Update the 12-cell `dm_admission` composition matrix tests + the F12/F16 ACL tests to the new (no-`dm_allowed`) semantics.
- [x] **Approve flow (`api.py:2716` `approve_peer_approval` + the PAIR-prefix path):** an approved peer is added to the Direct Messages list **as allowed** (just `{id}`) — no `dm_allowed:false`. Approving a peer lets them DM immediately (under `admin-approved`). **This is the F16-parked Known Issue fix.**
- [x] **UI — Direct Messages section:** the connector allowlist editor's users/peers section is **relabeled "Direct Messages"**; the **per-peer `dm_allowed` toggle is removed** (in-list = allowed); the `dm_admission` control is a **relabeled 3-mode policy** ("Who can DM the bot?" → Anyone / Only these people / No one — or similar clear copy). Adding/removing a user in the list is the only DM-grant control. (Per-agent ACL overlay UI unchanged.)
- [x] **Mission Known Issue marked resolved** in `mission.md` (the F16-parked "pairing-approval two-step DM-grant" entry) with fix evidence.
- [x] Full backend + browser suites green; the `dm_admission` matrix + approve-flow tests updated to the new model. No regression to guild admission (F16) or the per-agent overlay (F15 L4).

## Verification Steps

- Migration: a connector with legacy `peers=[{id, dm_allowed:false}]` → after migration reads `peers=[{id}]`; the peer can DM under `admin-approved`.
- ACL: `_admits_inbound_dm` unit matrix — `none`/`all`/`admin-approved` × in-list/not-in-list, no `dm_allowed` term. `all` admits a non-listed peer; `admin-approved` admits only listed; `none` denies all.
- Approve: `approve_peer_approval` adds `{id}` (no `dm_allowed`); a subsequent DM from that peer is admitted (the F3a reproduction now passes).
- UI: the section reads "Direct Messages"; no per-peer DM checkbox; the policy radio has the 3 relabeled modes.
- Guild unaffected: F16 guild-admission tests still green (account peers inert in guild).
- Behavior: `discord-approval-flow` (D/E/F) end-to-end.

## Implementation Guidance

1. **Confirm current schema version + the exact peers/dm_admission storage** (design review). Write the vN migration rewriting `allowlist.peers` entries to drop `dm_allowed` (idempotent; legacy-tolerant read path).
2. **Rewrite `_admits_inbound_dm`'s composition** per the new model; drop the `dm_allowed` consult + the pre-dm_admission list-precedence-deny under `all`. Keep `_admits_inbound_guild` (F16) untouched.
3. **Fix `approve_peer_approval`** (+ the PAIR-prefix success path in `_inbound.py`) to append `{id}` (allowed), not `{id, dm_allowed:False}`.
4. **UI:** relabel the section "Direct Messages"; remove the per-peer DM toggle; relabel the `dm_admission` control to the 3-mode policy. (Find the allowlist editor's peers/users section + the per-peer toggle + the dm_admission control in the connector-editor JS.)
5. **Tests:** rewrite the `dm_admission` matrix + F12/F16 ACL tests to the no-`dm_allowed` model; add the F3a-reproduction-now-passes test; migration test; approve-flow test.
6. **mission.md:** mark the F16-parked Known Issue resolved with evidence.

## Edge Cases

- **Legacy data:** a connector still on `{id, dm_allowed}` must read correctly post-migration (dm_allowed dropped; peer treated as allowed). A peer that was `dm_allowed:false` becomes allowed-to-DM after migration — that's the intended fix (they were approved; now they can actually DM). Note this in the migration (it's a deliberate semantic grant for already-approved peers).
- **`all` mode + non-empty list:** under the new model, "Anyone" ignores the list (don't deny a non-listed peer under `all`). This is a change from the current pre-dm_admission precedence.
- **Per-agent peers axis:** do NOT touch `connector_acls.peers` (guild-routing) or `_admits_inbound_guild`.
- **dm_admission default:** confirm the default mode for a connector with no explicit dm_admission (currently `"admin-approved"` per `_acl.py:571`) — keep the default sensible.

## Files Affected

- `the_one/db/` — vN migration (peers drop `dm_allowed`); the schema/migration module.
- `the_one/connectors/_acl.py` (`_admits_inbound_dm`, ~`:504`/`:559`/`:571`) — composition rewrite.
- `the_one/interfaces/web/api.py` (`approve_peer_approval` ~`:2716`) + `the_one/connectors/_inbound.py` (PAIR-prefix path) — approve adds `{id}` allowed.
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (+ form helpers) — Direct Messages relabel, remove per-peer toggle, relabel dm_admission policy.
- `the_one/db/models.py` — peers shape doc (+ any Pydantic shape).
- `tests/…` — ACL matrix rewrite, migration test, approve-flow test, F3a-reproduction test, browser tests.
- `missions/11-discord-connector-depth/mission.md` — F16-parked Known Issue → resolved.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (ACL matrix + migration + approve + full backend green; 2919 passed / 4 skipped)
- [x] Flight log updated; leg status `landed` (→ `completed` at DM-cluster commit)
- [x] mission.md F16 Known Issue marked resolved (DM-grant half + full closure note added)
- [ ] Commit deferred to DM-cluster batch (after the `discord-approval-flow` behavior test)
