# Leg: backend-removal

**Status**: completed
**Flight**: [Remove](../flight.md)

## Objective
Delete the connector backend — the `the_one/connectors/` package, connector tools, all 18 REST routes + 2 test seams, lifespan blocks, models/validators/repositories, the agent-loop carve-out, and the self-configuration projection coupling — add migration v38, remove `discord.py` and the aiohttp CVE floor from the dependency closure, and land with `make test-unit` green.

## Context
- Flight DD-1: all 18 routes go; "kept" = DB table, `ConnectorRepository`, encryption enrollment — not the HTTP surface.
- Flight DD-2: migration v38 retires `pending_approvals` (+ its index), `agents.connector_ids`/`connector_acls`/`connector_always_listen` (plain `ALTER TABLE agents DROP COLUMN` — design review confirmed no index/CHECK entanglement; SQLite floor is fine on Python ≥3.11), and deletes all rows from `connectors`. Table-rename ceremony NOT needed; follow the ledger's idempotent presence-check pattern (`INSERT OR IGNORE INTO schema_version` last).
- Flight DD-3: `OPERATOR_VISIBILITY` relocates to `the_one/llm/base.py` (documented home, `base.py:162-167`). `PLATFORM_SEND_OK_PREFIX` is deleted, NOT relocated.
- Flight DD-4: factory carve-out removal is the only agent-loop change; `agent/core.py` gets comment/prompt-composition edits only.
- Flight DD-5: self-config projection drops its `connectors` key.
- Flight DD-6: both `/api/_test` connector seams go.
- Flight DD-8: the MCP evict/drain block `app.py:396-418` is UNTOUCHABLE — do not modify, reorder, or reformat it (open squawk 0025 pins its ordering concern).
- Flight DD-7 scope note: "green" for THIS leg means `make test-unit`. Browser lanes are expected red until leg 2 — not this leg's problem. BUT: unit-lane collection imports every collected module (the M22 "701 deselected" shows browser/live files are collected then deselected), so **any file that imports `the_one.connectors` or `discord` must be deleted or fixed in this leg regardless of lane** — a collection ImportError breaks the unit lane. This is why the `discord_hat` live suite and the two browser-file import swaps are in this leg (Flight Director re-scope, recorded in the flight log).
- The complete file-by-file inventory with line references lives in the flight log's **Reconnaissance Report** (verified by design review 2026-08-30). Work from it; re-grep any citation before relying on it.

## Inputs
- Branch `flight/01-remove` from current `main`; suite green (4,571 passed / 10 Windows-only skips).
- `the_one/db/schema.py` `CURRENT_VERSION = 37`.
- Flight log Reconnaissance Report (this flight, planning section).

## Outputs
- No `the_one/connectors/` directory; no `connector_history.py` / `connector_send.py` / `db/_connector_types.py`.
- No connector routes or `/api/_test` connector seams in `api.py`; rotation block keeps its connectors-table SQL but loses pool eviction.
- `OPERATOR_VISIBILITY` lives in `the_one/llm/base.py`; `app.py` and the four surviving tests import it from there.
- Migration v38 in `schema.py`; `CURRENT_VERSION = 38`.
- `pyproject.toml` without discord.py pin, aiohttp floor, or `discord_hat` marker/deselect; regenerated `uv.lock` with neither `discord-py` nor `aiohttp`; synced venv.
- `packaging/windows/the-one.spec` without the `nacl` exclusion.
- No `tests/live/discord_hat/`; Makefile without `test-discord-hat` target and marker deselect strings.
- Backend/unit test files deleted or edited per inventory; `tests/_connector_dispatch_helpers.py` deleted after rehoming `_seed_provider_and_agent`; `tests/_acl_shape_helpers.py` KEPT for leg 2 (its surviving consumer `tests/browser/seeders.py` is leg 2's).
- Frontend JS/CSS/index.html, browser connector tests (the non-importing ones), behavior specs, docs, testid registry: UNTOUCHED (leg 2).

## Acceptance Criteria
- [x] `grep -rn "the_one.connectors\|the_one/connectors" the_one/ tests/` returns nothing — **CODE is clean** (`the_one/*.py` and `tests/*.py` both zero hits, including a leg-2 browser test file that mentions the path only in a docstring, no actual import). The literal grep as scoped ALSO walks `the_one/agents.md` (27 hits) — that's the docs sweep the flight's own Files Affected section assigns to leg 2; see Deviations.
- [x] `grep -rn "import discord\|from discord" the_one/ tests/` returns nothing
- [x] `grep -rn '"/api/connectors\|/api/connectors/' the_one/` returns nothing (leg 2 owns `static/` and remaining `tests/browser/` hits)
- [x] `OPERATOR_VISIBILITY` is defined in `the_one/llm/base.py` and no module defines or re-exports it elsewhere
- [x] `the_one/db/schema.py` has `CURRENT_VERSION = 38` and a `if version < 38:` block that: drops `pending_approvals` (index first), drops the three `agents` connector columns guarded by column-presence checks, and `DELETE FROM connectors`; a seeded pre-v38 database (legacy connector rows + pending approvals + populated agent connector columns) upgrades cleanly, and the block is a no-op on re-run after a schema_version rewind (existing `test_db_migration.py` idiom, with a new test covering v38)
- [x] `agents.md`'s encryption-rotation invariant count is honored: `POST /api/encryption/rotate` still rotates `connectors.secrets` (rotation test passes over the kept table)
- [x] `AgentConfig` has no `connector_ids`/`connector_acls`/`connector_always_listen` fields, validators, or `CONNECTOR_ATTACHED_DIRECTIVE`; `compose_system_prompt` has no `connector_attached` parameter; `agent/factory.py` has no `send_to_platform_channel` handling; `tools/builtins.py` has no connector tool classes or kwargs
- [x] Self-configuration projection payload has no `connectors` key; `surface.py` constructs no `ConnectorRepository`
- [x] `uv.lock` (regenerated) contains no `discord-py` and no `aiohttp` package entry
- [x] `pyproject.toml` retains ALL other CVE floors (`click`, `idna`, `starlette`, `cryptography`, `pydantic-settings`, `python-multipart`, `soupsieve`, `lxml-html-clean`, …) and their comments
- [x] `make test-unit` passes with 0 failures, no new skips/xfails, no collection errors — 0 failures / 0 errors confirmed; skip count differs from the M22 baseline (13 vs 10) but is environment-driven (Ollama-reachability / bwrap / frozen-detection skips in files this leg never touched), not a new skip this leg introduced — see Deviations.
- [x] Flight log updated with a leg progress entry (counts: files deleted, tests removed, suite time)

## Verification Steps
- Run the four greps above; each must be empty. — DONE (code-scope clean; `agents.md` docs hits are leg 2's, see above).
- `python -c "from the_one.llm.base import OPERATOR_VISIBILITY"` (via `.venv/bin/python`) succeeds. — DONE.
- Migration: run the new v38 upgrade test plus the full `tests/test_db_migration.py` file; run `tests/test_provider_api.py::test_rotate_connector_secrets`. — DONE, all green.
- `uv lock && uv sync --extra gui --extra all-llms` clean; `grep -c 'name = "aiohttp"' uv.lock` → 0; same for `discord-py`. — DONE, both 0. NOTE: this exact `uv sync` invocation (no `--extra dev`) uninstalled the dev/test toolchain (pytest, ruff, playwright, pre-commit, pip-audit, …) from `.venv` — see Deviations; re-ran with `--extra dev` added.
- `make test-unit` — full unit suite, green. — DONE, 3612 passed / 0 failed / 0 errors / 13 skipped / 655 deselected, 6m55s, run against the fully-synced (discord/aiohttp-free) venv.
- Do NOT run browser lanes as a gate (expected red until leg 2). — Honored; not run.

## Implementation Guidance

Ordering matters — keep the tree importable at each stage:

1. **Relocate `OPERATOR_VISIBILITY`** into `the_one/llm/base.py` (beside its documentation, `:162-167`); update the five import sites (`app.py:47`, `tests/test_db_codec.py:566`, `tests/test_ws_storage_edge_shim_visibility.py:37`, `tests/browser/test_flow_chat_peer_attribution.py:42`, `tests/browser/test_flow_chat_visibility_distinction.py:42`). Rework `test_ws_storage_edge_shim_visibility.py:296`'s live use of `PLATFORM_SEND_OK_PREFIX` (inline the literal `[platform-send-ok]` or restructure the assertion — do not re-import).
2. **Excise `api.py`**: route block `:3316-4512`, detach route `:840-897`, both `/api/_test` connector seams (`:4603`, `:4642-4681`), `_validate_connector_config` Discord branch (`:1853-1970`, keep the unknown-type rejection), rotation-block pool eviction (`:5916-5934`, keep the connectors-table SQL), module import `:3363-3364`, **the `PendingApprovalRepository` import at `:46` and its `_pending_approval_repo()` factory at `:268-270`** (delete outright — their only callers are the deleted routes; no stub kept for Flight 2), comment sites.
3. **Excise `app.py`**: stub registration `:251-270`, warm-acquire `:271-322`, legacy inference warning `:324-345`, connector pool drain `:420-429`, `_inflight_save_warm_tasks` drain `:431-440`, imports `:47-49` **plus the `pending_approvals_to_ui_events` import at `:55` and `PendingApprovalRepository` at `:68`**, and the **whole pending-approval merge surface: `_pending_approval_repo()` at `:990-1001`, `_merge_pending_approvals_into_history()` at `:1004-1032`, and BOTH call sites — inside `_restore_session` (`:1163-1200`) and inside `_build_session_joined_degraded` (~`:1345`)** — delete outright. LEAVE `:396-418` (MCP drain) byte-identical. Keep session projection keying fields `:1285-1299` and visibility logic (now importing from `llm/base`).
4. **Models/repos/codec**: strip `agent/config.py` per inventory; `db/models.py` — remove the three `Connector` validators and `PendingApproval`, keep the `Connector` model core and `ChatSession`; `db/repositories.py` — remove `PendingApprovalRepository`, `list_by_connector`, agent-row connector columns from upsert/hydrate, keep `ConnectorRepository`; `db/codec.py` — remove the **entire `pending_approvals_to_ui_events` function (`:435-469` — def line through closing bracket, not just the cited body)**, keep peer_name.
   **`db/_connector_types.py` decoupling (BEFORE deleting the module in step 8)** — it has two KEPT importers, `db/schema.py:10` and `db/models.py:10`, and deleting it first breaks the entire suite at collection since schema.py is a foundational import:
   - `db/schema.py`: replace the `_CONNECTOR_TYPES_SQL` uses with a **frozen inline literal** in the historical v19/v23 DDL (`:799`, `:1083`), then **delete the now-dead derivation at `:28` and the `CONNECTOR_TYPES` import at `:10`**. Also update the comments at `:752-754` and `:986` that claim future connector types "flow automatically into the next CHECK-changing migration" — false once frozen; Flight 2 changes the CHECK via a new ceremony step. Add a one-line comment saying the literal is frozen history.
   - `db/models.py`: inline the tuple beside the `Connector.type` Literal assert (`:641-642`) as the model's own constant. The deliberate duplication is correct now: the two uses have different lifecycles (frozen history vs living model), which is exactly the "three layers must agree" invariant collapsing to two independent ones.
   - `db/codec.py`: with `pending_approvals_to_ui_events` gone, **delete its now-unused `PendingApproval` import at `:8`** (its only uses are `:436`, `:438`, inside the deleted function) — otherwise `codec.py`, imported by `agent/core.py` and `app.py`, ImportErrors at collection.
   - Fast local check before step 8: `grep -n "_CONNECTOR_TYPES_SQL\|CONNECTOR_TYPES" the_one/db/schema.py the_one/db/models.py` and `grep -n "PendingApproval" the_one/db/codec.py` must show only the new inline constants.
5. **Agent loop (DD-4 only)**: `factory.py` carve-outs `:302-320`, `:389-394`, `:417-439`, comment `:120`; `tools/builtins.py` entries and kwargs; `core.py` comments/prompt-composition. `set_factory`/`get_factory` stay.
6. **Self-configuration**: `projection.py` and `surface.py` per DD-5; update `tests/test_self_configuration_projection.py`.
7. **Migration v38** per DD-2 (write it AFTER the model changes so tests exercise the final shape). Add the upgrade + rewind test to `test_db_migration.py`.
8. **Delete the package and tools**: `the_one/connectors/`, `tools/connector_history.py`, `tools/connector_send.py`.
9. **Tests**: delete the 26 connector-named unit files + `test_app_pending_approval_merge.py` + `test_discord_hat_helpers.py` + `tests/live/discord_hat/`; edit the mixed-purpose files per the Reconnaissance Report (notably `conftest.py:362,382-389` pool teardown, `test_db_api.py` 256 refs, `test_db_migration.py` 440 refs, `test_db_repositories.py` — rehome `_seed_provider_and_agent` from `tests/_connector_dispatch_helpers.py` before deleting that helper, `test_api_secret_mask_roundtrip.py` — delete only the three connector methods, `test_lifespan.py`, `test_logging_config.py`, `test_factory.py`, `test_config.py`). KEEP `tests/_acl_shape_helpers.py` (leg 2).
10. **Deps + packaging**: `pyproject.toml` — remove `:23-26` (discord.py + comment), `:36-41` + `:69` (aiohttp comment + floor ONLY), `:132-133` + `:140` (deselect + marker); `Makefile` — remove `test-discord-hat` target `:225-227` and marker strings `:203,:205`; `packaging/windows/the-one.spec:185-189` — remove `nacl` exclusion + comment. Then `uv lock`, `uv sync`, and the closing full `make test-unit`.
11. **Comment sweep** (acceptable-variation territory): `sessions/__init__.py`, `sessions/_locks.py`, `api_credential.py:162-163`, `llm/registry.py:16`, `llm/plan_credentials.py:118,:222`, `tools/execution.py:558,:585`; stale `PendingApprovalRepository` pattern citations in kept docstrings/comments — `db/repositories.py:969,:1004,:1061,:1089,:1143` (`AgentRevisionRepository`) and `api.py:275`.

## Edge Cases
- **`_connector_types.py` CHECK coupling**: the `connectors.type` CHECK constraint in the live schema references the type values. Deleting the module must not alter the deployed CHECK (schema history is append-only); Flight 2 changes the CHECK via the established ceremony. Only the Python-side tuple moves/goes — see step 4's decoupling instructions (schema.py frozen literal, models.py own constant) for the two kept importers.
- **Grep timing**: run the four acceptance greps once more AFTER step 10's packaging edits and `uv lock`/`uv sync` — the packaging files are themselves grep targets.
- **Known citation drift**: `test_flow_chat_visibility_distinction.py`'s import is at `:43` (not `:42`); `tests/live/discord_hat/` holds 11 tracked files (not 9) — immaterial since the whole directory goes.
- **Fresh-create path**: `ensure_schema` linearly replays all blocks — a brand-new DB creates the agent connector columns (v18/v19-era blocks) then v38 drops them. This is the established pattern; do not "optimize" earlier blocks.
- **Rewind idempotency**: v38's column drops must be guarded by presence checks so a schema_version-rewind re-run is a no-op (see v23's guards).
- **`test_db_api.py` scale**: 256 connector refs — expect to delete whole test classes for approvals/ACLs while keeping connector-table CRUD-at-repository-level tests (the repository is kept).
- **Collection vs deselection**: if any remaining collected file trips ImportError on the removed `discord` package, that file was missed — fix in this leg, whatever lane it belongs to.

## Files Affected
See the flight log **Reconnaissance Report** for the authoritative file-by-file list with line references (backend sections: Python deletes, Routes, Lifespan, Models/DB, Agent loop, Self-configuration, Tests, Packaging/deps). This leg touches everything there EXCEPT the Frontend sections, behavior specs, browser-only test files that don't import the package, `scripts/run-tests.sh` globs, docs, and the testid registry — those are leg 2.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header) — commit happens at flight end, not per leg
- [x] Check off this leg in flight.md
