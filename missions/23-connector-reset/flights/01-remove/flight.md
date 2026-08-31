# Flight: Remove

**Status**: completed
**Mission**: [Connector Reset](../../mission.md)

## Contributing to Criteria
- [x] `discord.py` and `aiohttp` are absent from the runtime dependency closure, and no third-party chat-platform SDK is present in base dependencies — `uv lock` no-op, 0 hits for either package in `uv.lock` and in the `uv export --no-dev --no-emit-project --extra gui --extra all-llms` CI-consumer closure; both genuinely unimportable in the synced venv (leg 3 verification)
- [x] The `pending_approvals` table, the `agents.connector_ids` / `connector_acls` / `connector_always_listen` columns, and legacy connector rows are retired by a single new migration; an existing database upgrades cleanly — v38, `tests/test_db_migration.py` 84/84 passed in isolation incl. `TestSchemaV38`'s upgrade/idempotency tests and the v23→v38 chained-legacy-row path (leg 3 verification)
- [x] `make test-unit` and every browser lane pass; the tests for removed capabilities are deleted, not skipped; the `discord_hat` marker and its Makefile target are gone — fresh `make test-unit`: 3561 passed/0 failed/10 skipped/542 deselected (skip count unchanged from pre-flight baseline, confirming deletion not skipping); all 4 browser lanes green (leg 2's runs, no frontend changes since); `discord_hat` marker/Makefile target confirmed absent, only a retirement comment remains in `pyproject.toml:121` (leg 3 verification)
- [x] The Windows packaged build (Concourse) still builds and the packaged smoke check passes with the smaller closure — build 581708 on the temporary `windows-installer-flight01` pipeline (branch `flight/01-remove`), 2026-08-31: succeeded end-to-end incl. the "[4/6] smoke: frozen doctor" gate; installer 59 MiB (was 62 MiB)
- [x] *(foundation for)* the ≤3,000 Python / ≤1,000 JS size ceilings — this flight establishes the zero baseline the running count is tracked from — Python LOC under `the_one/connectors/` = 0, connector-tool LOC = 0, connector Studio JS LOC = 0 (all confirmed via leg 3's fresh count); note `the_one/connectors/` directory itself persists on disk (stray root-owned `__pycache__/`, zero `.py` content) — see flight log Anomalies #2

---

## Pre-Flight

### Objective

Delete the entire connector subsystem — ~8.8k Python LOC (`the_one/connectors/` + two connector tools), the 18 REST routes, ~8.4k LOC of Studio/Chat JS, the connector CSS, ~53 connector-only test files, 10 behavior specs, and the `discord_hat` live suite — while keeping the six pieces the mission preserves (connector DB table + repository + encryption enrollment, session keying columns, `Message.visibility`, factory accessor) intact and the suite green. One migration (v38) retires `pending_approvals`, the three agent connector columns, and legacy connector rows. `discord.py` and the aiohttp CVE floor leave `pyproject.toml`; the lock is regenerated and verified aiohttp-free. The flight rebuilds nothing: the tree after landing has no connector runtime, no connector UI, and a green suite.

### Open Questions
- [x] Do the masked-CRUD routes survive Flight 1? → see DD-1
- [x] Does v38 also retire `agents.connector_ids`? → see DD-2
- [x] Where does `OPERATOR_VISIBILITY` go? → see DD-3
- [x] Fate of the send tool / factory carve-out given "the agent loop is not modified"? → see DD-4
- [x] Fate of the `GET /api/_test/chat/sessions/lookup` test seam? → see DD-6

### Design Decisions

**DD-1 — All 18 connector routes are deleted**: "Kept" in the mission's six-kept-pieces constraint means the DB table, `ConnectorRepository`, and encryption-rotation enrollment — not the HTTP surface. Flight 2 rebuilds minimal CRUD + doctor routes over the kept table.
- Rationale: gives this flight a clean "no connector runtime" tree; the rotation-invariant test (`tests/test_provider_api.py::test_rotate_connector_secrets`, 2026-08-28) already seeds its row via raw SQL on the stated assumption that "Flight 1 ships no REST routes for the connectors table". Route 14 (the doctor probe) cannot work with no runtime behind it anyway.
- Trade-off: no admin surface for connector rows between Flights 1 and 2; legacy rows are dropped by v38 regardless, so the gap is inert.

**DD-2 — v38 retires all three agent connector columns**: `connector_ids`, `connector_acls`, `connector_always_listen`, plus the `pending_approvals` table and all rows in `connectors`. Single migration step, appended after the v37 block in `the_one/db/schema.py` (`CURRENT_VERSION` 37 → 38), following the ledger's idempotent presence-check pattern; if a column drop requires it (index/constraint entanglement), use the established table-rename ceremony (canonical exemplar: v23).
- Rationale: the binding direction flips in Flight 2 (connector → default agent, stored in connector config JSON — no new schema), so agent→connector attachment is dead schema; the mission constraint allows exactly one migration step, so everything retires now.
- Trade-off: none material — Flight 2's contract needs no agent-side columns.

**DD-3 — `OPERATOR_VISIBILITY` relocates to `the_one/llm/base.py`**: the constant is defined in `the_one/connectors/__init__.py:57` but consumed by the kept visibility semantic (`app.py:1653`, `app.py:1915`); `llm/base.py:162-167` already documents it as the semantic's home. `PLATFORM_SEND_OK_PREFIX` (`connectors/__init__.py:67`) is deleted with the package — it belongs to the send tool Flight 2 re-attaches.
- Rationale: `Message.visibility` is a kept piece; deleting its constant would break the Chat visibility distinction the mission explicitly preserves.
- Trade-off: import-site updates at five surviving locations — `app.py` plus four kept tests (`tests/test_db_codec.py:566`, `tests/test_ws_storage_edge_shim_visibility.py:37`, `tests/browser/test_flow_chat_peer_attribution.py:42`, `tests/browser/test_flow_chat_visibility_distinction.py:42`) that import it from `the_one.connectors`. Note: `test_ws_storage_edge_shim_visibility.py` also imports the deleted `PLATFORM_SEND_OK_PREFIX` and uses it live (`:296`) — that reference needs reworking (inline the literal or restructure the assertion), not an import-path swap.

**DD-4 — The factory carve-out is removed; the agent loop is otherwise untouched**: `agent/factory.py` carve-out blocks (`:302-320`, `:389-394`, `:417-439`) and the `connector_ids`/`connector_acls` kwargs threading through `tools/builtins.py` are removed; `agent/core.py` gets comment/prompt-composition edits only. `connector_history.py` and `connector_send.py` are deleted. The send tool's contract (name `send_to_platform_channel`, operator-visibility semantics) is preserved in git history and this spec; Flight 2 re-attaches it against the new pool rather than rewriting it.
- Rationale: the mission constraint explicitly permits "removing the `send_to_platform_channel` baseline carve-out"; a tool whose imports are deleted cannot stay compiled in.
- Trade-off: Flight 2 must consciously restore the visibility handling; recorded there.

**DD-5 — Self-configuration projection drops the `connectors` key**: `the_one/self_configuration/projection.py` (`:94-95`, `:109-176`) stops building the connector list in the `get_my_configuration` payload; `surface.py` stops constructing `ConnectorRepository`; `tests/test_self_configuration_projection.py` updated to the new shape.
- Rationale: an agent-facing payload advertising a subsystem that no longer exists is worse than a shape change; Flight 2 may re-add a minimal field.
- Trade-off: agent-visible shape change between flights — acceptable on a dev-only surface.

**DD-6 — The `GET /api/_test/chat/sessions/lookup` seam is deleted**: its only callers are connector browser tests being deleted; the session-keying columns it reads are kept, so Flight 2 or 3 can restore it verbatim if the new tests want it.
- Rationale: no live consumers after this flight; dead test seams are exactly what squawk 0020/0021's seam hygiene work polices.
- Trade-off: a small re-add later if needed.

**DD-7 — Deletions and their test/registry updates travel in the same leg**: the testid registry (`docs/ui-testid-registry.md`, ~123 connector rows), the guard infrastructure (`tests/_ui_guard_helpers.py`, `tests/browser/design_tokens.py`), and the guard tests (`test_ui_guards.py`, `test_design_tokens_a11y.py`) are pruned together with the JS they guard; the same rule pairs `index.html` script-tag removal with `test_index_asset_cache_busting.py`, and route removal with `test_seam_routes_403_sweep.py`. These are known tripwires — desyncing them is how a leg lands red.
- Rationale: each leg must land green (mission reversibility constraint) — where "green" is scoped per checkpoint: at the leg-1 boundary it means `make test-unit`; the browser lanes are **expected red between legs 1 and 2 by design** (the surviving connector JS and browser tests hit deleted routes — the studio lane via its `test_connector_*`/`test_flow_studio_*` globs, and potentially any lane via `app.js`'s pending-count poll 404ing). A red browser lane after leg 1 is not the divert trigger; browser lanes gate at leg 2's checkpoint.
- Trade-off: legs are bigger, and there is a known one-leg window where browser lanes cannot pass; that is the accepted cost of not splitting deletions from their frontends mid-file.

**DD-8 — The MCP drain in the lifespan is untouched**: the connector pool drain (`app.py:420-429`), warm-acquire (`app.py:271-322`), and stub-plugin registration (`app.py:251-270`) are deleted; the MCP evict/drain block (`app.py:396-418`) — the subject of open squawk 0025 — is not modified, not even reformatted.
- Rationale: squawk 0025 exists precisely because that ordering is unpinned; this flight must not be the reorder it warns about.
- Trade-off: none.

### Prerequisites
- [x] Suite green at start — M22 debrief records 4,571 passed / 10 skipped (Windows-only PTY) / 0 flakes, 8m29s
- [x] Migration head verified: `CURRENT_VERSION = 37` (`the_one/db/schema.py:15`); v38 slot free
- [x] Deletion/edit inventory compiled (2026-08-30 reconnaissance, recorded in flight log)
- [ ] `uv` available for lock regeneration; fresh `uv lock` runs clean before the flight starts
- [x] Concourse reachable for the Windows packaged build + smoke check (verified 2026-08-31, post-commit per re-scope)
- [x] Lock-consumer audit: `.github/workflows/windows-installer.yml` (tag-gated) and `pr-lint.yml`'s pip-audit gate consume the same `uv export` closure this flight regenerates; discord.py/aiohttp are base dependencies (not extras), so removal flows through with no double-declaration — squawks 0009/0015 both trace to drift in exactly this area, hence the explicit check in leg 3
- [ ] No uncommitted work in the target repo; work happens on a flight branch per project convention

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (design review 2026-08-30: approve with changes, applied; remaining unchecked prerequisites verify at execution start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The full deletion/edit inventory (file-by-file, with line references) is in the flight log's Reconnaissance Report. Summary of the two work fronts:

**Backend (leg 1)** — delete `the_one/connectors/` (17 files), `the_one/tools/connector_history.py` + `connector_send.py`; excise the contiguous route block `api.py:3316-4512` plus the detach route (`api.py:840-897`), `_validate_connector_config`'s Discord branch, the `_evict_all_for_account` call inside encryption rotation (`api.py:5927` — the rotation SQL itself stays), and scattered function-local imports; delete the lifespan connector blocks per DD-8 and relocate `OPERATOR_VISIBILITY` per DD-3; remove `AgentConfig` connector fields + both validators (`agent/config.py:200-577`) and the `CONNECTOR_ATTACHED_DIRECTIVE`/`compose_system_prompt(connector_attached=...)` threading; remove the factory carve-out per DD-4; delete the `Connector` model's reserved-key/idle-timeout/continuation validators and `PendingApproval` from `db/models.py` (the `Connector` model and `ChatSession` keying fields stay); delete `PendingApprovalRepository`, `list_by_connector`, and agent-row connector column handling from `db/repositories.py` (`ConnectorRepository` stays); surgery on `db/codec.py` (pending-approval replay events out, peer_name stays with session keying); `db/_connector_types.py` deleted; self-configuration per DD-5; write migration v38 per DD-2; `pyproject.toml` discord.py pin (`:23-26`) + aiohttp floor (`:36-41`, `:69`) + `discord_hat` marker/deselect (`:132-133`, `:140`) removed, lock regenerated; PyInstaller `nacl` exclusion (`packaging/windows/the-one.spec:185-189`) removed. Backend test files deleted/edited in the same leg — including the heavy mixed-purpose edits (`test_db_api.py`, `test_db_migration.py`, `test_db_repositories.py`, `conftest.py` pool-teardown hook, `test_lifespan.py`, `test_logging_config.py`, `test_ws_storage_edge_shim_visibility.py`) and rehoming `_seed_provider_and_agent` out of `tests/_connector_dispatch_helpers.py` before that helper is deleted.

**Frontend + specs + docs (leg 2)** — delete the 9 connector JS files (8,423 LOC incl. `routing-audit-panel.js`), the 8 `index.html` script tags, the pending-approval poll in `app.js:15-28`, the connector blocks in `studio.js` (123 refs), `chat.js`, `agent-editor.js`, and the connector CSS in `css/studio.css` (123 refs) + minor CSS files; prune the testid registry + guards per DD-7; delete the browser/UI test files and the remaining connector-only tests; delete 10 connector behavior specs + their `runs/` directories, edit the 5 with incidental mentions; delete `tests/live/discord_hat/` and the Makefile target (`Makefile:225-227`) + deselect strings (`:203`, `:205`) + `scripts/run-tests.sh` studio-lane globs (`:62-63`); docs — `agents.md` connector sections (~`:1187-1307`, `:1642-1696`, the M10/M11 convention entries, and exemplar-citation edits), `SECURITY-MODEL.md` four one-line edits, `CLAUDE.md` three edits, `README.md` architecture paragraph, reducing the contract description to a stub that says what Flight 2 will define. Historical artifacts (`missions/`, `maintenance/`) are left as-is.

**Verify (leg 3)** — see Verification.

### Checkpoints
- [ ] Leg 1 lands: no `the_one.connectors` imports anywhere in `the_one/` or `tests/`; `make test-unit` green (browser lanes expected red — see DD-7); fresh `uv.lock` contains neither `discord-py` nor `aiohttp`
- [x] Leg 2 lands: no `/api/connectors` or connector testids anywhere in `static/`/`docs/`/`tests/`; all browser lanes green
- [x] Leg 3 lands: full verification sweep passes; suite size/time delta and line-count baseline recorded in flight log — sweeps 1/2 clean, sweep 3 (discord) clean with enumerated exceptions, sweep 4 surfaces one real leftover (see Anomalies); metrics recorded

### Adaptation Criteria

**Divert if**:
- An unknown consumer of `the_one.connectors` or the deleted routes surfaces outside the reconnaissance inventory — stop, re-inventory, re-plan the affected leg
- A leg cannot land green without rebuilding connector functionality — the mission's pre-declared split point: stop and split a "stub-only connector row" leg rather than absorbing rebuild work
- The v38 column drops force a full `agents`-table rebuild that destabilizes unrelated columns — pause at the migration and review before landing

**Acceptable variations**:
- Additional comment-only edits discovered during the sweep (e.g. `llm/registry.py`, `api_credential.py`, `sessions/` docstrings)
- Moving a mixed-purpose test's connector cases into a deleted file's scope (or vice versa) as long as no kept behavior loses coverage
- `_acl_shape_helpers.py` / `_connector_dispatch_helpers.py` surviving into leg 2 if the rehoming ordering demands it

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `backend-removal` - Python package, tools, routes, lifespan, models/validators, repositories, codec, self-config, factory carve-out, migration v38, deps + lock, PyInstaller; backend tests deleted/edited in the same pass — **landed** 2026-08-30, `make test-unit` 3612 passed / 0 failed / 13 skipped (env-driven) / 655 deselected, 6m55s; see flight log Leg Progress + Deviations
- [x] `frontend-tests-docs-removal` - JS/CSS/index.html, testid registry + guards, browser and remaining tests, behavior specs, discord_hat suite + Makefile/scripts, docs — **landed** 2026-08-30, `make test-unit` 3561 passed / 0 failed / 10 skipped (env-driven) / 542 deselected, 5m47s; all 4 browser lanes green (studio 139p/3s 3m56s, chat 39p 1m15s, system 106p 2m30s, shared 174p/3s 1m29s); see flight log Leg Progress + Deviations
- [x] `verify-integration` - Full sweep: greps, lanes, migration upgrade test against a seeded pre-v38 DB, Windows Concourse build + packaged smoke, baseline metrics — **landed** 2026-08-30, all sweeps/dependency-closure/tests/migration/spec-parse checks recorded in flight log Verification Report; two leftover findings surfaced (orphaned `routing-audit` CSS+backend plumbing, `the_one/connectors/` dir not literally absent due to stray `__pycache__`) — see flight log Anomalies. Windows Concourse build/smoke NOT run (post-commit, Flight Director's step per the leg's re-scope)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification

- `make test-unit` green; `scripts/run-tests.sh --lane studio|chat|system|shared` all green; no new skips/xfails.
- Sweeps come up empty: `grep -rn "the_one.connectors\|the_one/connectors" the_one/ tests/ docs/ *.md`, `grep -rn "/api/connectors" the_one/ tests/`, `grep -rn "discord" the_one/ pyproject.toml Makefile scripts/ packaging/` (excluding historical `missions/`/`maintenance/` artifacts).
- Fresh `uv lock`: `discord-py` and `aiohttp` absent from the resolved closure (mission criterion 1's known-answer check from planning).
- Migration: a seeded pre-v38 database (with legacy connector rows, pending approvals, and populated agent connector columns) upgrades cleanly to v38 — rows dropped, columns gone, `test_db_migration.py`'s rewind-idempotency idiom satisfied; the rotation-invariant test still passes over the kept `connectors` table.
- Windows packaged build runs on Concourse from the regenerated lock and its smoke check passes.
- Recorded in flight log: post-deletion `make test-unit` count/time (baseline was 4,571 / 8m29s), and the connector line-count baseline (expected: 0 Python under `the_one/connectors/`, 0 connector JS) that the mission's stop-and-split ceiling tracking counts up from.
- No behavior test is authored for this flight: it removes real-environment behavior rather than adding it; the replacement live HATs belong to Flights 3–4.
