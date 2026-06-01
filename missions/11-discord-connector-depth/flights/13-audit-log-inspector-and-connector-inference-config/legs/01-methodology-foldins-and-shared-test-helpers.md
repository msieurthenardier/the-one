# Leg: methodology-foldins-and-shared-test-helpers

**Status**: completed
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](../flight.md)

## Objective

Land the F12 carry-forward mechanical prereq: extract a shared `tests/_acl_shape_helpers.py` module consolidating the translator helpers duplicated across four test files, and codify two new M11 convention blocks in `the_one/agents.md` — all as a structural no-op that preserves the backend baseline of 2783 passing tests and the browser baseline of 443.

## Context

- **Mechanical-prereq-leg-before-semantic-changes pattern** (Pulled-Forward methodology lesson #6): L1 is the structural no-op that precedes L2's substrate semantic changes. Same shape as F11 L1 and F12 L1/L2 — extract first, mutate against the stable structure later.
- **F12 debrief Recommendations #3 + #5** (`flight-debrief.md` Recommendations §3 §5): translator helpers in 4+ test files doing the same shape-evolution work were called out as ~50 LOC of duplication; two patterns surfaced in F12 (`column-aware-index-create-for-rewind-paths`, `test-translator-helpers-for-shape-evolution`) need codification as named M11 conventions.
- **L1 is a pure structural no-op — the per-agent `dm_allowed` retirement is L2's surface, NOT L1's** (per `flight.md` Technical Approach L2 (e) — "fixture auto-updates via L1 shared helper"; this means L2 owns the helper update, with L1 providing only the consolidation point). At L1 land, the shared `_to_v24_agent_acl` MUST emit `dm_allowed: True` on per-agent peer entries, exactly matching the current behavior of the four per-file helpers. The current per-agent Pydantic validator at `the_one/agent/config.py:374-411` REQUIRES the field; any premature retirement would break the post-L1-pre-L2 build. L2 then (a) updates the shared helper to stop emitting `dm_allowed` on per-agent peers, (b) adds the validator change that REJECTS the field, (c) runs the v26 migration that strips it from stored data — in lockstep, single atomic boundary.
- **Account-scope vs per-agent `dm_allowed`**: account-scope helpers (`_to_v24_shape`, `_to_v24_allowlist`) emit `dm_allowed` on peer entries because account-scope is the path that consumes the field at the ACL layer (`the_one/connectors/_acl.py:491`). Per-agent helpers also emit it today for structural uniformity (the F12 footgun); after L2 lands, they'll stop. L1 preserves the status quo on both axes.
- **Recon-time shape drift discovered across the 4 source files** (see Edge Cases below): `test_connectors_commands.py:264`'s `_to_v24_shape` still uses the pre-L5 `guild_id: None` branch for channel/role entries (vs `DEFAULT_TEST_GUILD_ID` in the acl/routing helpers), and `tests/browser/seeders.py:91` defines its own constant `_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"` (different literal value than backend's `"g-test"`). Reconciliation strategy is documented below.
- **Existing precedent for top-level `tests/` shared helper modules**: `tests/_connector_dispatch_helpers.py` (imported as `from tests._connector_dispatch_helpers import ...`) and `tests/_pty_fixtures.py` are both at the `tests/` root, not under `tests/fixtures/`. The new `tests/_acl_shape_helpers.py` follows the same pattern.

## Inputs

What exists before this leg runs:

- Branch `flight/13-audit-log-inspector-and-connector-inference-config` checked out from main at commit `26a0ddf` (F13 planning commit; F12 already landed at `9f4df4a`).
- Backend test suite passes at **2783 passed / 4 skipped / 0 errors / 0 failures**.
- Browser test suite passes at **443 passed / 35 skipped / 12 deselected / 2 pre-existing-main failures** (unrelated to F12/F13).
- `the_one/agents.md` M11 section has the 4 existing convention blocks at lines 405-435 (`dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `two-symmetric-paths-in-acl`, `studio-event-bus`).
- Translator helpers duplicated across:
  - `tests/test_connectors_acl.py:36` — `DEFAULT_TEST_GUILD_ID = "g-test"`; `:70` `_to_v24_shape`; `:146` `_to_v24_agent_acl`
  - `tests/test_connectors_routing.py:34` — `DEFAULT_TEST_GUILD_ID = "g-test"`; `:37` `_to_v24_shape` (no `_to_v24_agent_acl`)
  - `tests/test_connectors_commands.py:264` — `_to_v24_shape` (uses `guild_id: None`, NOT `DEFAULT_TEST_GUILD_ID`; no constant; no `_to_v24_agent_acl`)
  - `tests/browser/seeders.py:91` — `_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"`; `:94` `_to_v24_allowlist`; `:160` `_to_v24_agent_acl`
- No existing `tests/_acl_shape_helpers.py` module.

## Outputs

What exists after this leg completes:

- **New file** `tests/_acl_shape_helpers.py` exporting:
  - `DEFAULT_TEST_GUILD_ID = "g-test"` (the canonical value)
  - `_to_v24_shape(allowlist: dict) -> dict` — account-scope helper; KEEPS `dm_allowed: True` default on peer-string entries; defaults channel/role string entries to `DEFAULT_TEST_GUILD_ID`; handles dict-tuple-string entries for peers and dict-tuple-string for channels/roles; renames `dm_admission` Literal `"allowlisted-peers-only"` → `"admin-approved"`
  - `_to_v24_agent_acl(agent_acl: dict | None) -> dict | None` — per-agent helper; **EMITS** `dm_allowed: True` on bare-string peer entries (status quo, matching the four per-file helpers being replaced; the v26 retirement is L2's surface, not L1's); same channel/role guild-default behavior as `_to_v24_shape`; passes through `admit_dms` unchanged; `None` short-circuits
  - `_to_v24_allowlist` — alias for `_to_v24_shape` (browser seeders' existing import name; alias keeps the import-name continuity at call sites where renaming would be noise)
- **Modified files** (each removes its local duplicate definitions and imports from the shared module):
  - `tests/test_connectors_acl.py` — drop local `DEFAULT_TEST_GUILD_ID`, `_to_v24_shape`, `_to_v24_agent_acl`; add `from tests._acl_shape_helpers import DEFAULT_TEST_GUILD_ID, _to_v24_shape, _to_v24_agent_acl`
  - `tests/test_connectors_routing.py` — drop local `DEFAULT_TEST_GUILD_ID`, `_to_v24_shape`; add `from tests._acl_shape_helpers import _to_v24_shape` (no `DEFAULT_TEST_GUILD_ID` import — the constant was referenced only inside the helper body; after deletion, no remaining references in the file); no per-agent `_to_v24_agent_acl` to import (file builds agent ACLs by hand)
  - `tests/test_connectors_commands.py` — drop local `_to_v24_shape` (with `guild_id: None`); add `from tests._acl_shape_helpers import _to_v24_shape` (no `DEFAULT_TEST_GUILD_ID` import — the file has no remaining references after helper deletion); the shape-drift change (`None` → `"g-test"`) is verified safe per Edge Case 1 below
  - `tests/browser/seeders.py` — drop local `_DEFAULT_FIXTURE_GUILD_ID` (along with the `"guild-fixture-default"` literal), `_to_v24_allowlist`, `_to_v24_agent_acl`; add `from tests._acl_shape_helpers import _to_v24_agent_acl, _to_v24_allowlist` (no `DEFAULT_TEST_GUILD_ID` import — recon confirmed seeders.py has no external references to the constant)
- **Modified file** `the_one/agents.md` M11 section: two new convention blocks added as siblings to `studio-event-bus` (i.e., between the existing 4 blocks and the `---` separator at line 437), specifically:
  - `### column-aware-index-create-for-rewind-paths`
  - `### test-translator-helpers-for-shape-evolution`
- **State**: backend test count unchanged at 2783; browser test count unchanged at 443; zero behavior change in production code.

## Acceptance Criteria

- [x] **AC-1**: `tests/_acl_shape_helpers.py` exists and exports `DEFAULT_TEST_GUILD_ID`, `_to_v24_shape`, `_to_v24_agent_acl`, `_to_v24_allowlist` (the last is an alias for `_to_v24_shape`).
- [x] **AC-2**: `_to_v24_agent_acl` emits `dm_allowed: True` on bare-string peer entries (status quo preservation; L1 is structural — L2 retires the field). Verified by `git grep -nE 'peers_new\.append.*dm_allowed' tests/_acl_shape_helpers.py` returning TWO hits — one bare-string emit (`{"id": entry, "dm_allowed": True}`) inside `_to_v24_shape`'s peers branch and one bare-string emit inside `_to_v24_agent_acl`'s peers branch. (Docstring mentions of `"dm_allowed"` in helper signatures are NOT counted by this grep — emit-site count is the contract.)
- [x] **AC-3**: `tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_commands.py`, `tests/browser/seeders.py` each contain a `from tests._acl_shape_helpers import …` line; each has its local helper duplicates DELETED (no orphaned definitions).
- [x] **AC-4** (grep-gate per Pulled-Forward methodology lessons #1 + #2): `git grep -nE "^DEFAULT_TEST_GUILD_ID = " tests/` returns EXACTLY ONE hit — the assignment in `tests/_acl_shape_helpers.py`. (The `^` anchor excludes import lines `from tests._acl_shape_helpers import DEFAULT_TEST_GUILD_ID, ...` which only appear post-import-symbol.)
- [x] **AC-5** (grep-gate): `git grep -nE "^def _to_v24_shape|^def _to_v24_agent_acl|^def _to_v24_allowlist" tests/` returns EXACTLY ONE `def _to_v24_shape`, ONE `def _to_v24_agent_acl`, and zero `def _to_v24_allowlist` (alias is an assignment, not a `def`) — all in `tests/_acl_shape_helpers.py`.
- [x] **AC-6** (grep-gate, scope-defined): `git grep -nE 'peers_new\.append.*dm_allowed' tests/_acl_shape_helpers.py` returns TWO emit sites — one inside `_to_v24_shape` (account-scope, KEEPS the field) and one inside `_to_v24_agent_acl` (per-agent, status-quo at L1; L2 retires the per-agent emit). Docstring mentions of `"dm_allowed"` (helper signature illustrations) are explicitly excluded — emit-site count is the contract.
- [x] **AC-7** (no-orphan-inline-writes): `git grep -nE '"dm_allowed":\s*(True|False|true|false)' tests/test_connectors_routing.py tests/test_connectors_commands.py tests/browser/seeders.py` post-L1 returns ZERO hits in those three files. ALL pre-L1 hits in these three files were inside the helper bodies being deleted; no separate caller-level inline writes need cleanup. (Remaining `"dm_allowed"` writes elsewhere — `test_db_migration.py`, `test_db_repositories.py`, `test_db_api.py`, `test_connector_history_tools.py`, `test_connectors_discord.py`, `tests/browser/test_flow_studio_per_peer_dm_toggle.py`, plus the per-agent `dm_allowed` writes via the extracted helper in `test_connectors_acl.py`'s callers — are out of L1 scope and stay until L2 strips the field.)
- [x] **AC-8**: `the_one/agents.md` M11 section contains two NEW convention blocks named `column-aware-index-create-for-rewind-paths` and `test-translator-helpers-for-shape-evolution`, placed as siblings to the existing 4 blocks (after `studio-event-bus`, before the `---` separator that introduces the "Subsystem contracts" section). M11 section heading is `### Mission-specific (M11)` (H3, not H2) — verified at recon.
- [x] **AC-9** (test-count preservation): the post-L1 `docker exec the-one pytest --collect-only -q tests/ 2>&1 | tail -3` collected count matches the pre-L1 baseline captured at Implementation Guidance step 1.
- [x] **AC-10** (regression-suite passing): `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py -x --timeout 30` — all green.
- [x] **AC-11** (broader regression): `docker exec the-one pytest tests/ --timeout 30 -q` ends at 2783 passed / 4 skipped / 0 errors / 0 failures.
- [x] **AC-12** (browser-suite preserved): `docker exec the-one pytest tests/browser/ --timeout 30 -q` ends at 443 passed (+ same skips/deselected; 2 pre-existing failures still present).

## Verification Steps

How to confirm each criterion is met:

- **AC-1**: `Read tests/_acl_shape_helpers.py`; visually verify the 4 exports.
- **AC-2** (consolidated with AC-6): `git grep -nE 'peers_new\.append.*dm_allowed' tests/_acl_shape_helpers.py` → exactly 2 emit-site hits (one per helper body).
- **AC-3**: `grep -n "from tests._acl_shape_helpers" tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py tests/browser/seeders.py` — each file has the import line. `grep -nE "^def _to_v24_shape|^DEFAULT_TEST_GUILD_ID = " tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py tests/browser/seeders.py` — zero hits (all extracted).
- **AC-4 / AC-5 / AC-6 / AC-7**: run the exact grep commands listed in those criteria from the project root.
- **AC-8**: `Read the_one/agents.md` around the M11 section (locate via `grep -n "^### Mission-specific (M11)" the_one/agents.md`); verify the two new blocks are present between `studio-event-bus` and the `---` separator.
- **AC-9**: `docker exec the-one pytest --collect-only -q tests/ 2>&1 | tail -3` before and after — counts equal.
- **AC-10**: `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py -x --timeout 30 -q`
- **AC-11**: `docker exec the-one pytest tests/ --timeout 30 -q | tail -5` — verify `2783 passed`.
- **AC-12**: `docker exec the-one pytest tests/browser/ --timeout 30 -q | tail -5` — verify `443 passed`.

## Implementation Guidance

1. **Capture the baseline test count snapshot before any edits.**
   - Run `docker exec the-one pytest --collect-only -q tests/ 2>&1 | tail -3` and note the collected count. Use this number to verify AC-9.
   - Run `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py -q --timeout 30 2>&1 | tail -5` to confirm the three primary consumer files pass green BEFORE the extraction begins. (If they fail, fix the unrelated flake before continuing.)

2. **Create `tests/_acl_shape_helpers.py`.**

   The module body should look like this (verbatim guidance — the docstrings record the F12/F13 reasoning):

   ```python
   """Shared ACL fixture-shape translator helpers (F13 L1 extraction).

   Consolidates the per-test-file translators that mechanical-translate
   flat-shape allowlist fixture data to the v24 structured-tuple shape.
   Imported by ``tests/test_connectors_acl.py``,
   ``tests/test_connectors_routing.py``,
   ``tests/test_connectors_commands.py``, and ``tests/browser/seeders.py``
   so the four files share a single source of truth.

   See ``the_one/agents.md`` M11 ``test-translator-helpers-for-shape-evolution``
   for the convention this module codifies.

   L1 status quo: both helpers emit ``dm_allowed: True`` on bare-string
   peer entries to match the four per-file helpers being replaced. F13
   L2 then updates ``_to_v24_agent_acl`` to stop emitting the field on
   per-agent peers (paired with the v26 Pydantic validator that REJECTS
   it at per-agent scope and the v26 migration that strips it from
   stored data). Account-scope ``_to_v24_shape`` continues emitting the
   field post-L2 — DM admission is consumed at account scope only.
   """

   from __future__ import annotations

   # M11 F12 L5 — every channel/role entry must have a non-null
   # guild_id (the v24 ``str | None`` permissive semantic was removed at
   # F12 L5). Flat-string channel/role fixture entries default to this
   # constant; tests that exercise guild_id matching pass the same value
   # in their envelope kwargs / payloads so the entry's guild_id matches.
   DEFAULT_TEST_GUILD_ID = "g-test"


   def _to_v24_shape(allowlist: dict) -> dict:
       """Translate a flat-shape allowlist to the v24 structured-tuple
       shape. Account-scope variant — KEEPS ``dm_allowed`` on peer
       entries (account-scope is the path that consumes the field).

       Tuple form for fine control:
         - ``"P1"`` → ``{"id": "P1", "dm_allowed": True}``
         - ``("P1", True)`` → ``{"id": "P1", "dm_allowed": True}``
         - ``("P1", False)`` → ``{"id": "P1", "dm_allowed": False}``
         - Already-dict shape: pass through.
       """
       result = dict(allowlist)
       if "peers" in result and isinstance(result["peers"], list):
           peers_new = []
           for entry in result["peers"]:
               if isinstance(entry, dict):
                   peers_new.append(entry)
               elif isinstance(entry, tuple):
                   peers_new.append({"id": entry[0], "dm_allowed": entry[1]})
               else:
                   peers_new.append({"id": entry, "dm_allowed": True})
           result["peers"] = peers_new
       if "channels" in result and isinstance(result["channels"], list):
           channels_new = []
           for entry in result["channels"]:
               if isinstance(entry, dict):
                   channels_new.append(entry)
               elif isinstance(entry, tuple):
                   channels_new.append(
                       {"guild_id": entry[0], "channel_id": entry[1]}
                   )
               else:
                   channels_new.append(
                       {
                           "guild_id": DEFAULT_TEST_GUILD_ID,
                           "channel_id": entry,
                       }
                   )
           result["channels"] = channels_new
       if "roles" in result and isinstance(result["roles"], list):
           roles_new = []
           for entry in result["roles"]:
               if isinstance(entry, dict):
                   roles_new.append(entry)
               elif isinstance(entry, tuple):
                   roles_new.append(
                       {"guild_id": entry[0], "role_id": entry[1]}
                   )
               else:
                   roles_new.append(
                       {"guild_id": DEFAULT_TEST_GUILD_ID, "role_id": entry}
                   )
           result["roles"] = roles_new
       if result.get("dm_admission") == "allowlisted-peers-only":
           result["dm_admission"] = "admin-approved"
       return result


   def _to_v24_agent_acl(agent_acl: dict | None) -> dict | None:
       """Per-agent ACL translator. Same channel/role guild-default
       semantics as :func:`_to_v24_shape`. L1 emits ``dm_allowed: True``
       on bare-string peer entries to match the four per-file helpers
       being replaced; F13 L2 then updates this helper to stop emitting
       the field in lockstep with the v26 Pydantic validator that
       REJECTS it at per-agent scope and the v26 migration that strips
       it from stored data.

       ``None`` short-circuits.
       """
       if agent_acl is None:
           return None
       result = dict(agent_acl)
       if isinstance(result.get("peers"), list):
           peers_new = []
           for entry in result["peers"]:
               if isinstance(entry, dict):
                   peers_new.append(entry)
               elif isinstance(entry, tuple):
                   peers_new.append({"id": entry[0], "dm_allowed": entry[1]})
               else:
                   peers_new.append({"id": entry, "dm_allowed": True})
           result["peers"] = peers_new
       if isinstance(result.get("channels"), list):
           channels_new = []
           for entry in result["channels"]:
               if isinstance(entry, dict):
                   channels_new.append(entry)
               elif isinstance(entry, tuple):
                   channels_new.append(
                       {"guild_id": entry[0], "channel_id": entry[1]}
                   )
               else:
                   channels_new.append(
                       {
                           "guild_id": DEFAULT_TEST_GUILD_ID,
                           "channel_id": entry,
                       }
                   )
           result["channels"] = channels_new
       if isinstance(result.get("roles"), list):
           roles_new = []
           for entry in result["roles"]:
               if isinstance(entry, dict):
                   roles_new.append(entry)
               elif isinstance(entry, tuple):
                   roles_new.append(
                       {"guild_id": entry[0], "role_id": entry[1]}
                   )
               else:
                   roles_new.append(
                       {"guild_id": DEFAULT_TEST_GUILD_ID, "role_id": entry}
                   )
           result["roles"] = roles_new
       return result


   # Alias preserved for browser-seeder import compatibility (the
   # account-scope translator and the account-scope-allowlist translator
   # are the same thing — the rename in seeders.py was for local
   # readability and we keep both names exported).
   _to_v24_allowlist = _to_v24_shape
   ```

   **Key invariants** the helper preserves vs the pre-extraction state:
   - Account-scope `_to_v24_shape` keeps emitting `dm_allowed` on all three peer entry forms (dict pass-through, tuple second-element, bare-string defaults to `True`).
   - Per-agent `_to_v24_agent_acl` ALSO keeps emitting `dm_allowed` at L1 (status quo — matches the four per-file helpers). L2 owns the helper-level retirement in lockstep with the validator + migration.
   - `DEFAULT_TEST_GUILD_ID = "g-test"` is the canonical value. Browser seeders' old `_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"` is migrated to `"g-test"` — safe per Edge Case 1.
   - `test_connectors_commands.py`'s former `guild_id: None` branch is reconciled to `DEFAULT_TEST_GUILD_ID` — safe per Edge Case 2.

3. **Edit `tests/test_connectors_acl.py` — remove local definitions, add the import.**

   - Delete lines around `:36` (`DEFAULT_TEST_GUILD_ID = "g-test"`).
   - Delete the entire `_to_v24_shape` definition (`:70-143`).
   - Delete the entire `_to_v24_agent_acl` definition (`:146-197`).
   - Add the import alongside the existing imports (after the `from the_one.db.models import Connector` line at `:29`):
     ```python
     from tests._acl_shape_helpers import (
         DEFAULT_TEST_GUILD_ID,
         _to_v24_agent_acl,
         _to_v24_shape,
     )
     ```
   - Preserve the comment block above `DEFAULT_TEST_GUILD_ID` if it carries reasoning useful in-file — but the shared module's docstrings now own this reasoning, so it can be deleted.
   - The `admits_inbound` and `admits_outbound` test wrappers at `:39-67` STAY (they're test-file-specific call-time helpers that wrap the real ACL functions with the v24 shape translator); they continue calling `_to_v24_agent_acl(agent_acl)` (now imported).

4. **Edit `tests/test_connectors_routing.py` — remove local def, add import.**

   - Delete the `DEFAULT_TEST_GUILD_ID = "g-test"` line (`:34`).
   - Delete the entire `_to_v24_shape` definition (`:37-72`). Line `:55` (`else {"id": entry, "dm_allowed": True}`) is INSIDE this helper body — it disappears with the helper. No separate caller-level cleanup needed; AC-7's post-edit grep verifies zero remaining `dm_allowed` literals in this file.
   - Add the import after `from the_one.db.models import Connector` at `:28` (DEFAULT_TEST_GUILD_ID is NOT imported — the constant was referenced only inside the helper body, so no remaining references in this file post-deletion):
     ```python
     from tests._acl_shape_helpers import _to_v24_shape
     ```
   - The file's existing `_account(...)` helper at `:75-93` continues calling `_to_v24_shape(...)` — now imported.

5. **Edit `tests/test_connectors_commands.py` — remove local def, add import.**

   - Delete the `_to_v24_shape` definition at `:264-288`. Line `:271` (`else {"id": entry, "dm_allowed": True}`) is INSIDE this helper body — it disappears with the helper. No separate caller-level cleanup needed.
   - Add the import (around the other imports — check the file's import block):
     ```python
     from tests._acl_shape_helpers import _to_v24_shape
     ```
   - (No `DEFAULT_TEST_GUILD_ID` to import — the file has no remaining references to the constant after helper deletion. The file's only `_to_v24_shape` caller at `:298` passes `allowlist={"peers": ["allowed-peer"], "channels": []}` per `:379`; `channels: []` means no channel-entry translation happens, so the `DEFAULT_TEST_GUILD_ID` value never gets used in this file's call paths. Confirm at recon — see Edge Case 2.)
   - **Shape drift reconciliation**: the deleted `_to_v24_shape` in this file produced `{"guild_id": None, "channel_id": entry}` for bare-string channel entries. The new shared helper produces `{"guild_id": "g-test", "channel_id": entry}`. The only caller (`:298` via `:379`) passes `channels: []` (empty list) so neither branch ever fires — the change is observably a no-op. **Verify** at implementation time by running `pytest tests/test_connectors_commands.py -x --timeout 30 -q` and confirming all tests still pass.

6. **Edit `tests/browser/seeders.py` — remove local defs, drop inline `dm_allowed` writes, add import.**

   - Delete the `_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"` line (`:91`).
   - Delete the entire `_to_v24_allowlist` definition (`:94-157`).
   - Delete the entire `_to_v24_agent_acl` definition (`:160-206`).
   - **Inline-fixture cleanup**: lines `:127` and `:178` each read `peers_new.append({"id": str(entry), "dm_allowed": True})`. Both are INSIDE the helpers being deleted, so they go away automatically — but verify post-edit grep returns zero hits in `tests/browser/seeders.py` per AC-7.
   - Add the import alongside the existing imports near the top of the file:
     ```python
     from tests._acl_shape_helpers import _to_v24_agent_acl, _to_v24_allowlist
     ```
   - The existing `seed_connector` helper at `:209+` continues calling `_to_v24_allowlist(...)` — now imported.
   - **Constant-value migration**: the deleted `_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"` is replaced by the shared `DEFAULT_TEST_GUILD_ID = "g-test"`. Per Edge Case 1, no external caller references the literal value, so the migration is observably a no-op.

7. **Add the two new convention blocks to `the_one/agents.md`.**

   - Locate the M11 section via `grep -n "^### Mission-specific (M11)" the_one/agents.md` — the heading is `### Mission-specific (M11)` (H3, NOT H2) at line 405 (confirmed at recon).
   - The existing 4 blocks end at line ~435 with `studio-event-bus`. The next line is `---` (line 437) introducing the next section. Insert the two new blocks BETWEEN `studio-event-bus`'s last line and the `---` separator.
   - Block 1 — verbatim text to insert:

     ```markdown
     ### `column-aware-index-create-for-rewind-paths`

     When a migration block must DROP+CREATE an index whose underlying columns have evolved across prior migrations, do NOT use `executescript("CREATE TABLE ...; CREATE INDEX ...")` — the `CREATE INDEX` half references the column names as they exist in the connection's current schema, and a v7-style strip-and-rewind path may execute that block against a schema where the column has since been renamed. The safe shape is: split the block into a `CREATE TABLE` half (executescript-safe) plus a Python-guarded `CREATE INDEX` step that consults `PRAGMA table_info(<table>)` at runtime to choose the correct column name branch (old-name vs new-name).

     Citation: F12 L3 introduced the pattern at `the_one/db/schema.py`'s v21 block, where v24 had dropped the old-named `idx_pending_approvals_account_peer_status` index whose v21-block CREATE referenced the post-v23-renamed column. The `test_v7_strips_removed_tool_names` rewind+rerun fixture path surfaced the failure mode (operators don't exercise the rewind path; pytest does).

     Source: F12 debrief Recommendation #5; codified at F13 L1.
     ```

   - Block 2 — verbatim text to insert:

     ```markdown
     ### `test-translator-helpers-for-shape-evolution`

     When a substrate's storage shape evolves and existing test fixtures should stay readable in the prior (flatter) author-convenience shape, add a **translator helper at test-module top** (or in a shared `tests/_*_helpers.py` module if the same translator surfaces in 3+ test files) that mechanical-translates flat fixtures to the post-evolution structured shape at fixture-build time. Existing test bodies stay readable; future shape evolutions extend the translator rather than sweeping every fixture site.

     Promote a per-file translator to a shared `tests/_*_helpers.py` module when the same helper appears in 3+ test files — F12 hit this threshold (4 sites) with `_to_v24_shape` / `_to_v24_agent_acl` / `_to_v24_allowlist` / `DEFAULT_TEST_GUILD_ID` across `tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_commands.py`, `tests/browser/seeders.py`, and F13 L1 extracted them to `tests/_acl_shape_helpers.py`.

     Citation: F12 L3 introduced the per-file pattern with `_to_v24_shape` / `_to_v24_agent_acl` at `tests/test_connectors_acl.py` (and parallel `_to_v24_allowlist` in `tests/browser/seeders.py`); F13 L1 promoted to the shared module `tests/_acl_shape_helpers.py`.

     Source: F12 debrief Recommendation #3 (extract shared module) + Recommendation #5 (codify the pattern); codified at F13 L1.
     ```

   - Verify post-edit: `grep -nE "^### \`(column-aware-index|test-translator|studio-event-bus|two-symmetric|backend-merged|dms-orthogonal)\`" the_one/agents.md` returns all 6 names in M11 section order.

8. **Run the regression gates in order.**

   - `docker exec the-one pytest tests/test_connectors_acl.py -x --timeout 30 -q`
   - `docker exec the-one pytest tests/test_connectors_routing.py -x --timeout 30 -q`
   - `docker exec the-one pytest tests/test_connectors_commands.py -x --timeout 30 -q`
   - `docker exec the-one pytest tests/browser/ --timeout 30 -q` (browser pass — quick local subset first if available, full at leg-end)
   - `docker exec the-one pytest tests/ --timeout 30 -q | tail -10` (full backend suite at leg-end)
   - Verify each AC gate (run the literal `git grep` commands in AC-4 through AC-7).

9. **Update the flight log.**

   - Append a leg-progress entry under `## Leg Progress` in `flights/13-.../flight-log.md` per the artifact's append-only convention.
   - Record: leg start/end timestamps, the recon's matching baseline-count snapshot, the exact post-L1 test counts, any inline-`dm_allowed` sites encountered beyond the spec's enumeration of 3 (and how they were resolved), confirmation that `git grep` AC gates pass.

## Edge Cases

- **Edge Case 1 — browser-seeders' `_DEFAULT_FIXTURE_GUILD_ID` value migration**: the deleted constant was `"guild-fixture-default"`; the canonical replacement is `"g-test"`. Recon confirmed (`grep -rn "guild-fixture-default" tests/`) that the literal value `"guild-fixture-default"` is referenced ONLY inside `tests/browser/seeders.py` itself — no browser test asserts the value or sends it in envelope payloads. **Treatment**: the migration is observably a no-op; existing browser tests continue passing without any test-side changes. If a regression surfaces (a browser test was relying on the old literal value indirectly through some path the recon missed), the fix is to update that test's payload to `"g-test"` to match the new fixture default.

- **Edge Case 2 — `test_connectors_commands.py`'s `_to_v24_shape` shape drift (`guild_id: None` → `guild_id: "g-test"`)**: the file's `_to_v24_shape` used the pre-F12-L5 `guild_id: None` branch for bare-string channel/role entries. Recon confirmed the helper has exactly ONE caller (`:298` via `_account(allowlist=...)`) and exactly ONE call site (`:379` passing `allowlist={"peers": ["allowed-peer"], "channels": []}`). With `channels: []` (empty list), neither the `guild_id: None` branch nor the new `guild_id: "g-test"` branch ever fires. **Treatment**: the shape drift is observably a no-op; the change is safe. If `pytest tests/test_connectors_commands.py` fails post-edit, investigate first whether a NEW call site has appeared since recon (re-run `grep -n "_to_v24_shape\|_account" tests/test_connectors_commands.py`).

- **Edge Case 3 — additional `dm_allowed` writes beyond the helper bodies**: recon confirmed ALL 4 enumerated `dm_allowed: True` sites (`test_connectors_routing.py:55`, `test_connectors_commands.py:271`, `tests/browser/seeders.py:127, 178`) are INSIDE the helper bodies being deleted — they disappear automatically. No caller-level inline writes need explicit cleanup in L1. **At implementation time**, re-run `git grep -nE '"dm_allowed":\s*(True|False)' tests/test_connectors_routing.py tests/test_connectors_commands.py tests/browser/seeders.py` AFTER the helper deletions and verify ZERO hits per AC-7. If hits remain (a caller-level inline write the spec missed at the same shape that surfaced at F11 L1 and F12 L3 recon), fold the cleanup into L1 in lockstep per the flight's "Acceptable variations" clause — but only for the three files in scope (do NOT extend L1 to scrub `dm_allowed` from per-agent peers in OTHER test files; that's L2's surface).

- **Edge Case 4 — orphan import lint after deletion**: deleting the local `_to_v24_shape` / `_to_v24_agent_acl` may leave the file with no remaining references to imports that were only used by those helpers (e.g., if a helper imported `from typing import Any` but the file's other code doesn't use it). Run `python -c "import tests.test_connectors_acl"` (and the same for the other 3 files) inside the container after each edit to catch ImportError or syntax issues before running pytest. Ruff/flake8 may also flag unused imports — the leg-execution crew's commit pre-checks (if any) will surface these; clean up unused imports as part of the edit.

- **Edge Case 5 — agents.md M11 section line-drift between flight-design and leg-execution**: the flight spec cites lines 405-431 for the M11 section; recon at leg-design time confirmed the heading `### Mission-specific (M11)` (H3, not H2) is at line 405 and the existing blocks end at line ~435. If at implementation time the line numbers have shifted (extremely unlikely — `the_one/agents.md` only changes in convention-codification flights and nothing in F13 L1 touches it apart from this leg's own edit), locate the M11 section heading via `grep -n "^### Mission-specific (M11)" the_one/agents.md` and the `studio-event-bus` block via `grep -n "studio-event-bus" the_one/agents.md`, then insert the two new blocks between `studio-event-bus`'s closing source-citation line and the next `---` separator.

- **Edge Case 6 — Divert clause (per `flight.md` Adaptation Criteria)**: if L1's extraction surfaces a fundamental shape mismatch between the 4 source helpers that the recon missed (e.g., one file's `_to_v24_shape` semantically rejects a peer-entry shape that another accepts, and the shared helper can't reconcile without breaking one consumer), invoke the flight's divert clause: split L1 into L1a (extract per-file with no consolidation — just move definitions to the shared module under file-suffixed names like `_to_v24_shape_acl`, `_to_v24_shape_routing`) + L1b (reconcile shape mismatches in a separate leg). The current recon found two reconcilable drifts (Edge Cases 1 + 2), both observably no-ops; if a third surfaces that ISN'T a no-op, divert.

## Files Affected

- `tests/_acl_shape_helpers.py` — **NEW**: the shared module per Implementation Guidance step 2.
- `tests/test_connectors_acl.py` — **MODIFIED**: remove local `DEFAULT_TEST_GUILD_ID` (`:36`), `_to_v24_shape` (`:70-143`), `_to_v24_agent_acl` (`:146-197`); add the import after `:29`.
- `tests/test_connectors_routing.py` — **MODIFIED**: remove local `DEFAULT_TEST_GUILD_ID` (`:34`), `_to_v24_shape` (`:37-72`) (line `:55` `dm_allowed: True` is inside this body, disappears with the helper); add `from tests._acl_shape_helpers import _to_v24_shape` after `:28`.
- `tests/test_connectors_commands.py` — **MODIFIED**: remove local `_to_v24_shape` (`:264-288`) (line `:271` `dm_allowed: True` is inside this body, disappears with the helper); add `from tests._acl_shape_helpers import _to_v24_shape`.
- `tests/browser/seeders.py` — **MODIFIED**: remove local `_DEFAULT_FIXTURE_GUILD_ID` (`:91`), `_to_v24_allowlist` (`:94-157`), `_to_v24_agent_acl` (`:160-206`); inline writes at `:127` and `:178` go away with their containing helpers; add the import.
- `the_one/agents.md` — **MODIFIED**: insert 2 new convention blocks at the end of the M11 section (after `studio-event-bus` block, before the `---` separator at ~line 437).

**No production source files** in `the_one/` (other than `agents.md`) are touched. L1 is a structural test-fixture extraction plus a documentation codification; zero behavior change in the connector / dispatcher / ACL substrate.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria (AC-1 through AC-12) verified
- [x] Tests passing — `2783 passed / 4 skipped / 0 errors / 0 failures` on the backend suite; `443 passed` on browser (+ same 2 pre-existing failures, no new failures)
- [x] Update `flights/13-.../flight-log.md` with the L1 progress entry under `## Leg Progress` per Implementation Guidance step 9
- [x] Set this leg's status to `landed` (in this file's header) — flips to `completed` at Phase 2d commit time per `/agentic-workflow` batching protocol
- [x] Check off this leg in `flights/13-.../flight.md` under `### Legs`
- [x] L1 is NOT the final leg of F13 — F13 has 6 legs total (L1-L6); skip the "final leg" sub-checklist
- [x] Defer commit per `flight.md` and `flight-log.md`'s `/agentic-workflow` Phase 2d note: code review + commit are DEFERRED to after L5 autonomous land (Flight Director batches L1+L2+L3+L4+L5 into a single Reviewer pass + single commit). L1 does NOT commit standalone.

---

## Citation Audit

Per `/leg` Phase 3b: every `file:line` citation in this leg artifact verified against current code at leg design time.

| Citation | Status | Notes |
|----------|--------|-------|
| `tests/test_connectors_acl.py:36` — `DEFAULT_TEST_GUILD_ID = "g-test"` | OK | Verified via `grep -n "DEFAULT_TEST_GUILD_ID = " tests/test_connectors_acl.py` |
| `tests/test_connectors_acl.py:70` — `_to_v24_shape` def | OK | Verified via Read |
| `tests/test_connectors_acl.py:146` — `_to_v24_agent_acl` def | OK | Verified via Read |
| `tests/test_connectors_acl.py:107, 164` — `peers_new.append({"id": entry, "dm_allowed": True})` | OK (inside helpers being extracted) | These lines go away with the helper deletion |
| `tests/test_connectors_routing.py:34` — `DEFAULT_TEST_GUILD_ID = "g-test"` | OK | Verified via Read |
| `tests/test_connectors_routing.py:37` — `_to_v24_shape` def | OK | Verified via Read |
| `tests/test_connectors_routing.py:55` — inline `{"id": entry, "dm_allowed": True}` | OK | Verified via Read |
| `tests/test_connectors_commands.py:264` — `_to_v24_shape` def with `guild_id: None` | OK | Verified via Read; shape drift confirmed |
| `tests/test_connectors_commands.py:271` — inline `{"id": entry, "dm_allowed": True}` | OK | Verified via Read |
| `tests/test_connectors_commands.py:298` — `_to_v24_shape` call site | OK | Verified via Read |
| `tests/test_connectors_commands.py:379` — `allowlist={"peers": ["allowed-peer"], "channels": []}` | OK | Verified via Read — `channels: []` confirms no `guild_id` branch ever fires |
| `tests/browser/seeders.py:91` — `_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"` | OK | Verified via Read; literal differs from backend's `"g-test"` |
| `tests/browser/seeders.py:94` — `_to_v24_allowlist` def | OK | Verified via Read |
| `tests/browser/seeders.py:127, 178` — inline `dm_allowed: True` writes | OK (inside helpers being extracted) | Lines go away with the helper deletion |
| `tests/browser/seeders.py:160` — `_to_v24_agent_acl` def | OK | Verified via Read |
| `tests/browser/seeders.py:243` — `config["allowlist"] = _to_v24_allowlist(...)` | OK | Verified via Read |
| `the_one/agents.md:405` — `### Mission-specific (M11)` heading (H3, NOT H2) | OK | Verified via Read at offset 380-440; heading is exactly at line 405; uses three hashes |
| `the_one/agents.md:407, 413, 419, 431` — existing 4 convention blocks (`dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `two-symmetric-paths-in-acl`, `studio-event-bus`) | OK | Verified via Read; all four `### \`{name}\`` headings present in the cited order |
| `the_one/agents.md:437` — `---` separator introducing "Subsystem contracts" | OK | Verified via Read; separator at line 437, insertion point is just before it |
| `flights/12-.../flight-debrief.md` Recommendation §3 + §5 | OK | Verified via Read of the F12 debrief Recommendations section |
| Tests/ has no `__init__.py` but `from tests._<module> import` works | OK | Verified via existing imports `from tests._connector_dispatch_helpers import ...` (6 call sites) and `from tests._pty_fixtures import ...` |

19 citations verified against current code at leg design time; no drift detected. The flight spec's line citations (`agents.md` 405-431) were also verified — the M11 section heading is at line 405 and the four existing convention block headings are at lines 407, 413, 419, 431 as cited.
