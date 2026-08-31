# Flight Log: Remove

**Flight**: [Remove](flight.md)

## Summary
All three legs completed 2026-08-30 (backend-removal, frontend-tests-docs-removal, verify-integration) plus a post-leg-3 fix pass. Connector subsystem fully removed: 208 files changed, +1,608 / −67,382. Suite 3,561 passed / 0 failed (from 4,571 baseline, −1.5 min); all four browser lanes green; `discord-py` and `aiohttp` out of the closure; migration v38 in with upgrade/rewind coverage. Flight-end review (Sonnet, independent): [HANDOFF:confirmed], zero issues. Remaining before `landed`: post-commit Concourse Windows build + packaged smoke.

---

## Reconnaissance Report (2026-08-30, planning phase)

Deletion/edit inventory compiled against the live tree before spec creation. Line numbers are as-of this date; re-grep symbols if they drift before execution.

### Delete outright — Python
- `the_one/connectors/` — 17 source files + README, ~8,027 LOC (largest: `_discord.py` 2160, `_pool.py` 1231, `_inbound.py` 1189, `_acl.py` 776)
- `the_one/tools/connector_history.py` (546), `the_one/tools/connector_send.py` (198)
- `the_one/db/_connector_types.py` (56)

### Routes — `the_one/interfaces/web/api.py` (all deleted, DD-1)
- Contiguous block `api.py:3316-4512` (~1,197 lines): 17 routes + 11 helper functions/models
- Detach route `DELETE /api/agents/{agent_name}/connectors/{account_id}` at `api.py:840-897`
- Test seams: `GET /api/_test/chat/sessions/lookup` (`:4642-4681`, DD-6), `POST /api/_test/chat/sessions/{id}/routing-audit` (`:4603`)
- Also delete (leg design review 2026-08-30 additions): `PendingApprovalRepository` import `:46`; `_pending_approval_repo()` factory `:268-270`
- Edits, not deletes: `_validate_connector_config` (`:1853-1970`) Discord branch; encryption rotation block (`:5632-5947`) loses only the `_evict_all_for_account` call (`:5927`) and pool-eviction lines (`:5916-5934`) — the connectors-table SQL stays; module import at `:3363-3364`; comment sites `:1468, :2148, :4565, :5003`

### Lifespan — `the_one/interfaces/web/app.py`
- Delete: stub registration `:251-270`; warm-acquire `:271-322`; legacy inference deprecation warning `:324-345`; connector pool drain `:420-429`; `_inflight_save_warm_tasks` drain `:431-440`; imports `:47-49` plus `:55` (`pending_approvals_to_ui_events`) and `:68` (`PendingApprovalRepository`); the pending-approval surface — `_pending_approval_repo()` `:990-1001`, `_merge_pending_approvals_into_history()` `:1004-1032`, and both call sites: `_restore_session` `:1163-1200` and `_build_session_joined_degraded` ~`:1345` (leg design review 2026-08-30 additions)
- **Untouched (DD-8 / squawk 0025)**: MCP evict/drain block `:396-418`
- Kept with edits: `OPERATOR_VISIBILITY` consumers `:1653`, `:1915` (constant relocates to `the_one/llm/base.py`, DD-3); session projection connector-keying fields `:1285-1299` (KEPT); visibility timing `:1638-1653`, `:1716-1788`

### Models / DB
- `agent/config.py`: fields `:200` (`connector_ids`), `:254` (`connector_acls`), `:281` (`connector_always_listen`); validators `:297-577`; `CONNECTOR_ATTACHED_DIRECTIVE` `:76-128`; `compose_system_prompt(connector_attached=...)` `:131-172`, `:619`
- `db/models.py`: `Connector` validators — idle-timeout `:160-177`, continuation `:178-204`, reserved-key `:205-~635` (~430 lines); `PendingApproval` `:646-684`. **KEPT**: `Connector` model core, `ChatSession` keying fields `:753-790`
- `db/repositories.py`: delete `PendingApprovalRepository` `:767-~900`, `list_by_connector` `:165-190`, agent-row connector column handling `:205-206, 222-224, 242-246, 392-406`. **KEPT**: `ConnectorRepository` `:659-766`
- `db/codec.py`: delete the entire `pending_approvals_to_ui_events` function `:435-469` (def line through closing bracket — original `:442-465` citation was body-only); peer_name `:345-357` KEPT
- `db/_connector_types.py` has two KEPT importers — `db/schema.py:10` (builds `_CONNECTOR_TYPES_SQL`, used in frozen v19/v23 DDL at `:799`, `:1083`) and `db/models.py:10` (Literal assert `:641-642`) — decouple both (schema.py: frozen inline literal; models.py: own constant) BEFORE deleting the module (leg design review 2026-08-30)
- `db/key_reconcile.py:24` `("connectors","secrets")` corpus — KEPT
- `db/schema.py`: `CURRENT_VERSION = 37` at `:15`; v38 appends after `:~2142`; idempotent pattern = presence-checked DDL then `INSERT OR IGNORE INTO schema_version`; table-rename ceremony exemplars v10 `:380-418`, v19 `:744-822`, v23 `:961-1163` (most complete), v37 `:2090-2142`

### Agent loop (DD-4 scope only)
- `agent/factory.py`: carve-out `:302-320`, kwargs `:389-394`, baseline carve-out `:417-439`, comment `:120`. **KEPT**: `set_factory()` `:155` / `get_factory()` `:166`
- `agent/core.py`: comment/prompt edits `:121-124`, `:441`, `:451`
- `tools/builtins.py`: imports `:9-15`, `_TOOL_CLASSES` entry `:69`, comment `:92-95`, kwargs `:147-148`, injection block `:212-226`
- `tools/execution.py:558, :585` — comments only

### Self-configuration (DD-5)
- `projection.py:40-42, :94-95, :109-176`; `surface.py:153, 168, 180, 185`; `manage.py:88`, `credentials.py:136` comments only

### Frontend — delete 9 files, 8,423 LOC
`connector-editor.js` 4982, `connectors-tab.js` 1020, `discoverable-dropdown.js` 846, `connector-form-discord.js` 720, `routing-audit-panel.js` 337, `connector-form-registry.js` 211, `connectors-grid.js` 125, `pending-approval-banner.js` 113, `connector-vocabulary.js` 69

### Frontend — edits
- `index.html`: **9** script tags (`:43, :47, :54, :61-66` — design review caught `:65` `discoverable-dropdown.js` missing from the original count). Leg 2 must re-grep `index.html` for all connector/discoverable script tags rather than trusting cited line numbers, and update `test_index_asset_cache_busting.py`'s exact-count assertion to match
- `js/areas/studio.js` (123 refs — heaviest: editor registration + overlay dropdown `:2401-2497`, event-bus `:353-360`, 6 fetches); `js/areas/chat.js` (23 refs: `:334`, `:495-614`, `:812-814`, `:1193`, `:1449-1451`); `js/app.js:15-28` (pending-count poll); `agent-editor.js` (9), `status-section.js` (3), `studio-event-bus.js` (2), comment-only in `mcp-server-editor.js`, `provider-editor.js`, `message-bubble.js`
- `history-buckets.js` — keys on kept `chat_sessions.platform`; likely **no change**
- CSS: `css/studio.css` (123 refs, large excision), `components.css` (3), `chat.css` (2), `admin.css` (1)

### Tests
- **Delete: 41 connector-named files** (26 `tests/`, 15 `tests/browser/`) **+ 12 connector-only unnamed**: `test_app_pending_approval_merge.py`, `test_discord_hat_helpers.py`, and browser flow files for pending-approval (×2), routing-audit, always-listen, per-agent overlays (×3), hierarchical rows, source badge, operator-input visibility
- **Edit (mixed-purpose, imports the package)**: `conftest.py` (`:362, :382-389` pool teardown), `test_db_api.py` (256 refs), `test_db_codec.py` (`:566` imports `OPERATOR_VISIBILITY` — swap to new `llm/base.py` home per DD-3), `test_lifespan.py` (30), `test_pairing_prefix.py`, `test_logging_config.py`, `test_ws_storage_edge_shim_visibility.py` (18; `:37` imports both `OPERATOR_VISIBILITY` — swap — and the deleted `PLATFORM_SEND_OK_PREFIX`, used live at `:296` — rework the assertion, don't just re-import), `browser/test_flow_chat_visibility_distinction.py` (`:42` `OPERATOR_VISIBILITY` swap), `browser/test_flow_chat_peer_attribution.py` (`:42` `OPERATOR_VISIBILITY` swap)
- **Edit (references without import)**: `test_db_migration.py` (440 refs), `test_db_repositories.py` (333 — imports `_connector_dispatch_helpers._seed_provider_and_agent` at `:1109`, rehome first), `test_factory.py` (41), `test_config.py`, `test_self_configuration_projection.py`, `test_provider_api.py`, `test_api_secret_mask_roundtrip.py` (delete the three connector-only test methods calling `/api/connectors` — `test_connector_sentinel_preserves`, `test_connector_starlit_prefix_is_real_value`, and the third near `:178` — keep the MCP-source and LLM-provider sentinel tests), `test_ui_guards.py`, `test_mcp_pool.py`, `test_design_tokens_a11y.py`, `browser/seeders.py` (imports `_acl_shape_helpers` at `:27`, edit first), ~18 more single-ref files
- **Tripwires (DD-7)**: `test_index_asset_cache_busting.py` ↔ `index.html`; `test_seam_routes_403_sweep.py` ↔ route removal; `test_ui_guards.py`/`test_design_tokens_a11y.py` ↔ testid registry + JS
- **Shared helpers**: `_acl_shape_helpers.py` (159), `_connector_dispatch_helpers.py` (341) — delete after consumer edits; `_credential_helpers.py:8-9` comment
- **Behavior specs**: delete 10 (+ `runs/` dirs): connector-editor-keyboard-a11y, connector-editor-ux, connector-inference-provider-config-roundtrip, discord-approval-flow, discord-engagement, discord-multi-agent-routing, discord-multi-channel-routing, discord-multi-user-routing, discord-slash-end-to-end, audit-log-inspector-renders-routing-entries. Edit 5 incidental: agent-history-auto-purge, agent-purge-now-clears-history, shell-navigation-smoke, studio-agent-crud, studio-smoke
- **Live suite**: delete `tests/live/discord_hat/` (9 files); marker at `pyproject.toml:140`, deselect `:132-133`; `Makefile:225-227` target, `:203, :205` deselect strings; `scripts/run-tests.sh:62-63` studio-lane globs; `ci/tasks/test.yml:7` comment

### Packaging / deps
- `pyproject.toml`: discord.py pin + comment `:23-26`; aiohttp floor comment `:36-41` + `"aiohttp>=3.14.3"` at `:69` (all other CVE floors **stay**); regenerate `uv.lock`
- `packaging/windows/the-one.spec:185-189`: `excludes = ["nacl"]` + rationale comment

### Docs
- `agents.md` (1696 LOC, 113 hit lines): connector-type checklist `:1187-1203`; connector subsystem `:1204-1307`; live-status `:1642-1671`; save-reconnects `:1672-1696`; M10/M11 convention entries `:544-707`, `:714-744`; exemplar citations `:152-179, :186, :243, :261-263, :274-301, :314-336, :385-408` (restate exemplars, don't delete the conventions)
- `SECURITY-MODEL.md`: one-line edits `:208, :278, :625, :634` (last two: kept concepts, wording only)
- `CLAUDE.md`: `:65` kept, `:229` delete caveat, `:232` lane globs
- `README.md`: `:123` delete connectors paragraph, `:125` edit persistence mention
- `docs/ui-testid-registry.md`: ~123 rows to prune (+ prefix note `:19`)
- `docs/kb-architecture.md:35` — false positive ("LlamaHub connectors"), no change
- Historical `missions/`, `maintenance/`, `BACKLOG.md` — no changes (BACKLOG has no live connector items)

### Comment-only sweep sites
`the_one/sessions/__init__.py:4-6`, `_locks.py:37` (module raison d'être restated); `api_credential.py:162-163`; `llm/registry.py:16`, `llm/plan_credentials.py:118, :222` (caller enumerations)

---

## Flight Director Notes

- **2026-08-30 — flight start**: status `ready` → `in-flight`; branch `flight/01-remove` created from `main` (planning artifacts ride on it). Crew phase file `leg-execution.md` validated (Crew / Interaction Protocol / Prompts present). Reviewer model tier for flight-end review: **Sonnet** — the diff touches encryption rotation, credential-bearing tables, and middleware-adjacent lifespan code (security-sensitive per crew file).
- **2026-08-30 — leg 1 designed (`01-backend-removal`)**. Risk tier: **HIGH** — schema migration (v38), shared-interface removals with surviving consumers (`OPERATOR_VISIBILITY`, factory kwargs, self-config payload shape), and lifespan edits adjacent to squawk 0025's pinned concern → per-leg design review runs. Citation audit: inventory line refs verified by the flight design review earlier today; leg instructs re-grep before reliance.
- **2026-08-30 — leg 1 design review, 2 cycles (cap reached)**: Round 1 (Developer, Sonnet): needs rework — two high issues (`_connector_types.py` kept importers; pending-approval surface under-cited), both fixed with reviewer-supplied citations. Round 2 (focused pass): needs rework — two more high issues of the same mechanical class (`schema.py:28`/`:10` dead derivation+import; `codec.py:8` dead import), with exact fixes supplied and every other amended citation verified exact. Flight Director call: applied the reviewer-specified mechanical fixes and proceeded to `ready` WITHOUT a third review cycle — no unresolved design issue remains (both rounds' issues were citation completeness, not design), so the escalate-on-persisting-issues trigger does not apply. The implementing Developer's step-4 grep check and the flight-end Reviewer both re-cover this exact surface.
- **2026-08-30 — leg 2 designed (`02-frontend-tests-docs-removal`)**. Risk tier: **HIGH** — not for schema (none) but for the DD-7 tripwire class that produced four collection/dangling-reference issues in leg 1's reviews: shared-file excisions (`studio.js` event-bus, `chat.js` kept-vs-deleted rendering split, CSS shared selectors) plus the testid-guard sync. Per-leg design review runs (Developer, Sonnet). Leg 1's `uv sync --extra dev` deviation carried into the leg text.
- **2026-08-30 — leg 2 design review, 1 cycle**: approve with changes. Substantive catches, all folded in: `history-buckets.js` was mischaracterized as no-change (it renders pending-approval testids — deletion required plus the `chat.js:1193` call-site arg); orphaned `--badge-discord` tokens in `tokens.css` + their `design_tokens.py` mirrors were cited nowhere and caught by no gate (grep criterion broadened to include `discord`); `test_flow_agent_tabs.py` and `test_flow_studio_navigation.py` flagged as structural rewrites paired with `agent-editor.js` tab markup; `app.js` badge surface extended to its true four-site extent; false positives pre-cleared. Fixes were reviewer-specified and mechanical → no second cycle; leg `ready`, implementer spawned (Developer, Sonnet).
- **2026-08-30 — leg 3 designed (`03-verify-integration`)**. Risk tier: **LOW** — no source changes; pure verification + artifact/log updates within established tooling. Per-leg design review SKIPPED per the risk-tier rule (additive, single-surface); the flight-end Reviewer covers the whole tree regardless. **Re-scope**: the Windows Concourse build + packaged smoke check moves out of leg 3 to post-commit — Concourse builds the pushed branch, and this flight commits once at flight end; leg 3 instead validates the closure locally with the exact `uv export` invocation the CI consumers use. The Flight Director runs the Concourse check after Phase 2d's commit + draft PR, before marking the flight `landed`.
- **2026-08-30 — post-leg-3 fix pass ordered**: leg 3's sweep 4 surfaced routing-audit leftovers inside this flight's charter (orphaned `chat.css:287-462` block, dead `session_metadata` routing read/ship plumbing in `app.py`/`api.py`, dead branch `api.py:1788`, stale `packaging/windows/README.md:235`). Flight Director decision: this is completion of the flight's own deletion scope, not a squawk — a targeted Developer fix pass runs BEFORE the flight-end review, its changes covered by that review. The landed legs are immutable; this pass is logged here as the record. The stray root-owned `the_one/connectors/__pycache__/` (untracked, local-only, makes the package resolve as an empty namespace) is removed in the same pass if permissions allow; otherwise flagged to the operator.
- **2026-08-30 — flight commit + PR; Concourse check BLOCKED on environment**: flight-end review [HANDOFF:confirmed] (zero issues); committed `fea6d3e` (213 files, +2,251/−67,382), pushed, draft PR #184 opened with all legs checked. The final gate — Windows Concourse build + packaged smoke — is blocked: both pipelines track `main` (a temporary `windows-installer-flight01` variant pointed at the flight branch was prepared), but Concourse at localhost:8080 is unreachable and Docker is not available in this WSL distro (Docker Desktop off or WSL integration disabled). Operator action required: start Docker Desktop / the Concourse stack, then re-run the set-pipeline + trigger. Flight stays `in-flight` (not `landed`) until the packaged build criterion is checked. Also outstanding for the operator: `sudo rm -rf ~/projects/the-one/the_one/connectors` (root-owned stray `__pycache__`, untracked, local-only).
- **Leg re-scope vs flight spec**: `tests/live/discord_hat/`, the `discord_hat` marker/deselect (pyproject + Makefile), and the two surviving browser files' `OPERATOR_VISIBILITY` import swaps move from leg 2 into leg 1. Rationale: unit-lane pytest collection imports all collected modules (M22 debrief's "701 deselected" confirms browser/live files are collected), so once `uv sync` removes the `discord` package, leaving those files would break `make test-unit` at collection — violating leg 1's green gate. `scripts/run-tests.sh` glob edits stay in leg 2 (harmless while browser files exist).

---

## Leg Progress

### 2026-08-30 — `backend-removal` landed

**Files deleted (63):** the `the_one/connectors/` package (17 source files + README), `the_one/tools/connector_history.py` + `connector_send.py`, `the_one/db/_connector_types.py`; `tests/live/discord_hat/` (12 files incl. `.env.hat.example`); `tests/_connector_dispatch_helpers.py` (after rehoming `_seed_provider_and_agent`'s test into `test_db_repositories.py`); 28 connector-named unit test files under `tests/` (the 26 the recon report named, plus `test_pairing_prefix.py` and `test_api_connector_config_validation.py` + `test_connectors_routing_schema.py` found via re-grep — citation drift the leg artifact flagged as expected).

**Files edited (46):** `the_one/interfaces/web/api.py` (route block, detach route, both `/api/_test` seams, `_validate_connector_config`, rotation pool-eviction, `_pending_approval_repo`, `_connector_repo` — orphaned by the route deletion, not explicitly cited but same class of cleanup), `app.py` (stub registration, warm-acquire, legacy-inference warning, connector pool drain, pending-approval merge surface — MCP evict/drain block `:396-418` verified byte-identical against `git show HEAD`), `agent/config.py`, `agent/factory.py`, `agent/core.py`, `db/models.py`, `db/repositories.py`, `db/codec.py`, `db/schema.py` (migration v38 + the v23 re-entry-guard fix, see Deviations), `tools/builtins.py`, `tools/execution.py`, `llm/base.py`, `llm/registry.py`, `llm/plan_credentials.py`, `self_configuration/{projection,surface,manage,credentials}.py`, `sessions/{__init__,_locks}.py`; `pyproject.toml`, `Makefile`, `packaging/windows/the-one.spec`, `uv.lock`; 24 test files (mixed-purpose edits: `test_db_api.py`, `test_db_migration.py`, `test_db_repositories.py`, `conftest.py`, `test_lifespan.py`, `test_factory.py`, `test_config.py`, `test_api_secret_mask_roundtrip.py`, `test_logging_config.py`, `test_mcp_pool.py`, `test_builtins.py`, `test_last_usage_round_trip.py`, `test_session_joined_payload.py`, `test_seam_routes_403_sweep.py`, `test_llm_provider_tool_result_serialization.py`, `test_db_codec.py`, `test_ws_storage_edge_shim_visibility.py`, 2 browser files' `OPERATOR_VISIBILITY` import swap, `_credential_helpers.py`).

**Kept, verified untouched:** `Connector` model core, `ConnectorRepository`, `ChatSession` keying fields, `Message.visibility`, `set_factory`/`get_factory`, `tests/_acl_shape_helpers.py`, `tests/browser/seeders.py`, `db/key_reconcile.py`, `the_one/interfaces/web/static/`, `docs/ui-testid-registry.md`, `scripts/run-tests.sh`.

**Migration v38:** `CURRENT_VERSION` 37 → 38. Drops `pending_approvals` (index + table) and the three `agents` connector columns (presence-guarded), `DELETE FROM connectors`. New `TestSchemaV38` class in `test_db_migration.py` (upgrade-from-seeded-pre-v38, stamp-rewind idempotency, double-ensure idempotency) — all pass. `db/schema.py:_CONNECTOR_TYPES_SQL` derivation replaced with frozen inline literals in the historical v19/v23 DDL; `db/models.py` carries its own `_CONNECTOR_TYPES` constant.

**Suite:** `make test-unit` — **3612 passed, 0 failed, 0 errors, 13 skipped, 655 deselected, 6m55s** (baseline M22: 4,571 passed / 10 skipped / 8m29s). Skip-count delta (+3) is environment-driven (Ollama-reachability / bwrap-setuid / frozen-detection conditional skips in `test_llm_provider_cross_provider_history.py`, `test_pty_sandbox.py`, `test_doctor.py` — none touched this leg; confirmed via `git status` showing zero diff on those files), not a skip this leg introduced. Final run executed against the fully-synced venv with `discord`/`aiohttp` genuinely absent (`.venv/bin/python -c "import discord"` / `import aiohttp` both raise `ModuleNotFoundError`).

**Dependency closure:** `uv lock` — `discord-py` and `aiohttp` both 0 hits in `uv.lock`. `uv sync --extra gui --extra all-llms --extra dev` — clean.

**Lint:** `ruff check` and `ruff format --check` both clean after this leg's edits (ran `ruff check --fix` for import-sort + one dead `logging` import in `test_db_migration.py`; `ruff format` on 3 files) — not part of the leg's explicit gate but consistent with project convention.

---

### 2026-08-30 — `frontend-tests-docs-removal` landed

**Files deleted (58):** the 9 connector JS files (`connector-editor.js`, `connectors-tab.js`, `discoverable-dropdown.js`, `connector-form-discord.js`, `routing-audit-panel.js`, `connector-form-registry.js`, `connectors-grid.js`, `pending-approval-banner.js`, `connector-vocabulary.js` — 8,423 LOC per recon); 25 connector-only browser test files under `tests/browser/` (the connector-named set plus the unnamed connector-exclusive flow files: `test_flow_chat_pending_approval.py`, `test_flow_chat_pending_badge.py`, `test_flow_chat_routing_audit_panel.py`, `test_flow_chat_session_list_source_badge.py`, `test_flow_connector_detach.py`, `test_flow_studio_always_listen_toggles.py`, `test_flow_studio_hierarchical_server_rows.py`, `test_flow_studio_per_agent_overlay_dropdown.py`, `test_flow_studio_per_agent_overlay_label_resolver.py`, `test_flow_chat_operator_input_visibility.py`, `test_flow_studio_per_agent_admit_dms.py` — the last two found via re-grep, not named in the recon list; see Deviations); the 10 connector behavior specs + their `runs/` directories (12 run-log files); `tests/_acl_shape_helpers.py`.

**Files edited (41):** shared JS — `studio.js` (serializeState/hydrateState connector branches, Connector Accounts state block, event-bus listener, section-nav entry, `commit()` reset branches, the whole `renderConnectorsSection`/`fetchConnectors_`/etc. function family, `collectFormData`'s `connector_ids`/`connector_acls`/`connector_always_listen` block — ~470 lines removed total), `chat.js` (routing-audit trigger, pending-approval dedup/fetch/render/click-handler machinery, live WS `pending-approval` branch; platform-session badge rendering and `renderHistory`/`onmessage` structure otherwise untouched), `history-buckets.js` (deleted `buildPendingApprovalsSection` + the `pendingApprovals` param per the design-review correction — this one was NOT a no-op as originally scoped), `app.js` (pending-badge poll, `_startPendingBadgePoll`, the nav badge markup — full 3c extent), `agent-editor.js` (Connectors tab button/panel/wiring removed, 6→5 tabs), `studio-event-bus.js`, `mcp-server-editor.js`, `provider-editor.js`, `message-bubble.js`, `tools-editor.js`, `status-section.js` (design-language gallery's discord-badge swatch) — comment/citation-only; CSS — `studio.css` (897-line contiguous excision: connector test/kv-table buttons, Connector Type Badges, empty-types banner, Connector account editor polish, per-axis ACL chevron rows, Discoverable Dropdown, Discord Runtime Config rows), `components.css` (`.nav-pending-badge` + `.pending-approvals-section` blocks, 2 exemplar-citation rewords), `tokens.css` (`--badge-discord`/`--badge-ink-discord` light+dark), `chat.css`, `admin.css` (comment-only, per instruction — the shared `.mcp-test-row`/`.connector-test-row` selector kept `.mcp-test-row` and dropped only the connector half); testid/guard surface — `docs/ui-testid-registry.md` (~130 rows pruned across all three tables; manual-exceptions table is now legitimately empty), `tests/_ui_guard_helpers.py`, `tests/browser/design_tokens.py` (`badge_discord`/`badge_ink_discord` mirrors), `tests/test_ui_guards.py` (baseline dynamic-sink entries for 5 deleted files + 1 changed snippet; manual-exceptions assertion relaxed, see Deviations), `tests/test_design_tokens_a11y.py` (two whole tests deleted along with the CSS they pinned, see Deviations); `index.html` (9 script tags) + `tests/test_index_asset_cache_busting.py` (62→53); browser test edits — `conftest.py`, `seeders.py` (`seed_connector` + `_acl_shape_helpers` import removed), `test_flow_agent_tabs.py` (structural: 6→5 tab count + docstring), `test_flow_chat_peer_attribution.py` (stale module-path comment), `test_flow_provider_plan_signin.py`, `test_flow_studio_loadall_error.py` (six→five fetches), `test_flow_studio_mcp_navigation.py` (4→3 nav buttons — found via re-grep, not named in the recon list), `test_flow_studio_navigation.py` (structural: 4→3 buttons, tabindex, arrow/Home/End wrap points); `tests/test_api_secret_mask_roundtrip.py`, `tests/_credential_helpers.py`; 5 incidental behavior specs (`agent-history-auto-purge`, `agent-purge-now-clears-history`, `shell-navigation-smoke`, `studio-agent-crud`, `studio-smoke`); lane plumbing — `scripts/run-tests.sh` (studio-lane globs), `CLAUDE.md` (lane-glob description + discord-package caveat), `ci/tasks/test.yml` (stale `discord_hat` deselect comment); docs — `the_one/agents.md`, `SECURITY-MODEL.md`, `README.md`.

**Suite:** `make test-unit` — **3561 passed, 0 failed, 0 errors, 10 skipped, 542 deselected, 347.40s (5m47s)**. Skip count is 10 vs leg 1's 13 — fewer, environment-driven (same conditional-skip tests leg 1 flagged), not a new skip introduced by this leg. Deselected dropped 655→542, consistent with deleting 25 browser test files from collection.

**Browser lanes — all 4 green:**
| Lane | Result | Time |
|------|--------|------|
| studio | 139 passed, 3 skipped | 235.57s (3m56s) |
| chat | 39 passed, 0 skipped (incl. both protected kept-behavior tests) | 75.35s (1m15s) |
| system | 106 passed, 0 skipped | 149.69s (2m30s) |
| shared | 174 passed, 3 skipped | 88.79s (1m29s) |

Total across the 4 lanes: 458 passed / 6 skipped. `test_flow_chat_visibility_distinction.py::test_chat_renders_operator_visibility_distinction` and `test_flow_chat_peer_attribution.py::test_chat_renders_peer_attribution` both pass, confirming the platform-session/visibility kept behavior survived the sweep.

**Testid registry:** pruned connector/approval/routing-audit rows across all three tables (literal, parametric-prefix, manual-exceptions) — the manual-exceptions table is now empty (its 4 entries were all `connector-editor.js` variable-carried ids); see Deviations for the guard-test adjustment this required.

---

### 2026-08-30 — `verify-integration` landed

Full local verification sweep over the combined legs 1+2 tree. No source changes made. Suite/lane results match leg 2 exactly (no drift). Dependency closure clean. Migration + rotation tests green. Packaging spec parses. Two findings surfaced beyond the leg's own literal grep terms — see Anomalies and the Verification Report below.

---

### 2026-08-30 — Post-leg-3 fix pass

Targeted Developer pass addressing the five items leg 3's sweep surfaced (Anomaly 1, Verification Report §3-4), completing this flight's own deletion scope before the flight-end review. No source changes outside this scope.

**1. Orphaned `routing-audit` CSS — removed.** `the_one/interfaces/web/static/css/chat.css:287-462` (176 lines: the `M11 F13 L5 / M16 F09 L04` comment through `.routing-audit-policy`'s closing brace) deleted outright — re-grepped confirmed 0 JS/HTML consumers of any `routing-audit` class/id anywhere under `static/`. Also updated one collateral stale comment on the surviving `.new-chat-header` rule (`:73-74`) that referenced "the routing-audit trigger after it," which no longer exists.

**2. `session_metadata` "routing" plumbing in `app.py`/`api.py` — investigated, left in place (alive).** Leg 3's report characterized the read/ship sites (`app.py:404-409` field def, `:1019-1022` refresh-on-restore, `:1036-1039` construction, `:1160-1162`/`:1184-1186` WS `session_joined` shipping; `api.py:3157-3174` REST detail-endpoint shipping) as a fully dead pipeline. Re-verification found this is **not correct**: the generic `session_metadata` dict field is the live carrier for the unrelated `last_usage` feature (M16 F06) — `_persist_last_usage` (`app.py:1078-1113`) writes `session.session_metadata["last_usage"]` on every turn-settle and is called live from two sites (`:1764`, `:1888`); `chat.js:1158` reads `data.session_metadata.last_usage` out of the exact `session_joined` WS payload the report flagged as dead. Only the "routing" *key* itself is dead (its sole production writer, the connector dispatcher, is gone — confirmed via `grep '"routing"' the_one/ tests/`: zero production writers, only test fixtures using "routing" as a generic sibling-key stand-in to test that `last_usage` writes preserve unrelated keys). The REST detail endpoint (`api.py:3157-3174`) has no current JS caller either, but `agents.md:522` already documents it as intentionally generic post-reset ("audit/telemetry data such as per-turn usage snapshots"), not routing-specific. **Left all sites unchanged** — removing them would break the live `last_usage` restore-on-rejoin behavior (confirmed still passing: `test_flow_usage_restore.py::test_overlay_restores_after_session_reopen`). The in-code comments at these sites still frame their *original* motivation (M11 F13 L5 routing-audit) rather than their current one (also serving `last_usage`) — flagging as pre-existing staleness, not touched, since the underlying code is correct and live.

**3. `api.py:1788` dead `discord` branch — removed (whole function, not just the branch).** `_validate_connector_config` (`api.py:1765-1804`) had zero callers anywhere in `the_one/`/`tests/` (confirmed by grep — its own docstring self-admitted "this helper currently has no caller," per DD-1). Deleted the entire function rather than just the flagged `if account.type in ("discord", "stub"):` branch, since the enclosing function was wholly dead, not only that one branch. Also removed the now-unused `Connector` import from `api.py`'s `db.models` import block (was used only by this function's type annotation). `ruff check`/`ruff format --check` both clean on the touched files. `grep discord the_one/interfaces/web/api.py` now returns 0 hits.

**4. `packaging/windows/README.md:235` — updated.** Stale `excludes=["nacl"]` line rewritten to describe the spec's current `excludes = []` state, matching the rationale comment already in `the-one.spec:185-187`.

**5. `the_one/connectors/__pycache__/` — could not remove (permission denied, as anticipated).** `rm -rf the_one/connectors/` failed on every file inside the root-owned `__pycache__/` subdirectory (`Permission denied`). Left in place per the leg's own note (untracked, gitignored, local-only, predates this flight) — the directory still resolves as an empty PEP 420 namespace package. Flagging to the operator: manual `sudo rm -rf the_one/connectors/__pycache__` (or equivalent) would fully clear it; not blocking.

**Gate results (all green):**
- Affected-area tests (`test_db_api.py`, `test_seam_routes_403_sweep.py`, `test_lifespan.py`, `test_session_joined_payload.py`, `test_last_usage_persistence.py`, `test_last_usage_round_trip.py`, `test_db_repositories.py`): **213 passed**, 69.94s.
- `make test-unit`: **3561 passed, 0 failed, 0 errors, 10 skipped, 542 deselected, 353.97s (5m53s)** — exact match to leg 2/3's landed baseline (no drift; item 2 made no code changes, items 1/3/4 don't touch anything unit-covered beyond what's above).
- Browser `chat` lane (`THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chat`): **39 passed, 0 skipped**, 78.54s — includes `test_overlay_restores_after_session_reopen`, direct confirmation the `last_usage` session_metadata path (left alive per item 2) still works end-to-end.
- `system` lane: **not run** — this pass made zero changes to `app.py`, so the "if app.py's changes touch anything it covers" trigger doesn't apply.
- Leg 3 sweep 4 grep re-run (`pending_approval|connector_acls|connector_always_listen|discoverable|routing-audit|engagement gate` over `static/`, `docs/`, `tests/`, the four top-level docs): **clean** — `chat.css` no longer appears in the hit list; all remaining hits are the same frozen-migration-history/historical-prose categories leg 3 already accepted as expected.

---

## Verification Report (2026-08-30, leg 3 — `verify-integration`)

### 1. Sweep — `the_one.connectors|the_one/connectors` (repo-wide, excl. `.git/`, `missions/`, `maintenance/`, `squawks/`)
**PASS — 0 hits.**

### 2. Sweep — `/api/connectors` (repo-wide, excl. `.git/`, `missions/`, `maintenance/`, `squawks/`)
**PASS — 0 hits.**

### 3. Sweep — `discord` (repo-wide, excl. `.git/`, `missions/`, `maintenance/`, `squawks/`)
**PASS with enumerated exceptions.** Accepted hits (the three named categories):
- **Frozen migration DDL / comments in `the_one/db/schema.py`** (13 lines): `:25, 494, 513, 587, 633, 695, 728, 747, 766, 802, 845, 989, 1143` — the two literal `CHECK (type IN ('discord', 'stub'))` DDL strings (`:802`, `:1143`) plus their explanatory comments.
- **`Connector.type` Literal in `the_one/db/models.py`** (4 lines): `:135, 140, 152, 169`.
- **Illustrative backend comments** (11 lines): `the_one/agent/factory.py:129, 170`; `the_one/interfaces/web/app.py:232, 399`; `the_one/llm/base.py:182, 187, 188, 191, 205`; `the_one/interfaces/web/api.py:1778, 1781` (docstring on `_validate_connector_config`).

Additional hits found outside the three named categories (not fixed — reporting per the leg's "report, don't fix" rule):
- **`the_one/interfaces/web/api.py:1788`** — `if account.type in ("discord", "stub"):` is live code, not a comment (the docstring above it: "this helper currently has no caller" — Flight 1 DD-1 removed all routes that called it). Consistent in spirit with the kept `Literal["discord", "stub"]`, but it's a code branch, not a comment.
- **`packaging/windows/README.md:235`** — stale: still reads `"excluded (\`excludes=["nacl"]\`)"`, but `packaging/windows/the-one.spec:189` now sets `excludes = []` (nacl exclusion removed this flight, criterion 5 below). This line is now factually wrong.
- **`packaging/windows/the-one.spec:186-187`** — comment explaining the nacl-exclusion removal, mentions "discord.py's optional voice support" (informational, matches the code's actual `excludes = []`, not stale).
- **`README.md:123`** — top-level doc prose, past tense ("Discord plugin) ... was reset"), describing the flight's own edit — intentional narrative, not a leftover.
- **`the_one/agents.md:255`** — top-level doc citation, past tense, describing a removed worked example.
- **`pyproject.toml:121`** — retirement comment, harmless.
- **Test files** (`tests/test_db_repositories.py`, `tests/test_retention.py`, `tests/test_db_migration.py`, `tests/test_api_secret_mask_roundtrip.py:8`, `tests/test_factory.py:571`) — `"discord"` used as example `platform`/`type` string value for **kept** functionality (`ChatSession.platform`, `Connector.type` Literal) or as frozen-history migration-test scaffolding (hand-built old-schema SQL, comments citing historical version numbers). Largely inherent to testing what the migration/kept-fields actually do.
- **Behavior specs/run logs** (`tests/behavior/studio-smoke.md` + its `runs/`, `tests/behavior/agent-history-auto-purge/runs/…`, `tests/behavior/agent-purge-now-clears-history/runs/…`) — historical narrative, not live specs (10 discord-only specs were already deleted in leg 2; these are incidental-mention survivors).
- `.gitignore:12, 43` — non-source path references.

Full raw grep output available by re-running; not pasted in full here given volume (see enumeration above for every file touched).

### 4. Sweep — `pending_approval|connector_acls|connector_always_listen|discoverable|routing-audit|engagement gate` (`the_one/interfaces/web/static/`, `docs/`, `tests/`, and the four top-level docs: `README.md`, `CLAUDE.md`, `SECURITY-MODEL.md`, `the_one/agents.md`)
**FAIL — one substantive leftover found, reported (not fixed) per the leg's scope.**

- **`the_one/interfaces/web/static/css/chat.css:287-462`** (~176 lines) is a live, fully-intact `.routing-audit-*` CSS block (trigger, overlay, modal, badges, rows, expansion) styling the deleted `routing-audit-panel.js` (confirmed deleted in leg 2). No JS or HTML anywhere references any `routing-audit` class or id anymore (`grep -rniE "routing-audit" the_one/interfaces/web/static/js/ .../index.html` — 0 hits) — this CSS is orphaned.
- **Backend companion dead code**: `the_one/interfaces/web/app.py` (`Session.session_metadata` field + its doc comments `:404-409`; refresh-on-restore `:1019-1022`; construction `:1036-1039`) and `the_one/interfaces/web/api.py:3157-3174` (`GET /api/chat/sessions/{id}` still ships `"session_metadata"` in its response, with an M11 F13 L5 "routing-audit inspector" comment) still carry the plumbing that fed the deleted panel. The **writer side is gone**: no live code calls `ChatSessionRepository.append_to_session_metadata(..., "routing", ...)` anymore (`grep -rn 'append_to_session_metadata\|"routing"' the_one/ tests/` shows only the repository's generic primitive definition and these read-side comments — the connector dispatcher that used to write the `"routing"` key was deleted with the connector package in leg 1). So `session_metadata` will always be `None`/empty going forward; the entire read → ship → render pipeline (170+ CSS lines, several backend comment blocks, one response field) is dead weight with no writer and no renderer.
- Not itself a functional regression (nothing renders it, nothing calls the dead branch), but it is exactly the class of leftover DD-7 exists to prevent, and it slipped past leg 2's own sweep because leg 2's grep terms didn't include "routing-audit" as a standalone term. **Flight Director attention needed**: either fold into a leg-4-equivalent cleanup or accept as known debt before flight-end commit.
- All other terms (`pending_approval`, `connector_acls`, `connector_always_listen`, `discoverable`, `engagement gate`) — 0 live hits in the swept scope; remaining matches are `tests/test_db_migration.py` frozen-history migration-test scaffolding (asserting/simulating the *absence* of these post-v38, or hand-building pre-migration schema shapes to test the drop) and `the_one/agents.md` historical citation prose — both inherent/expected, not leftovers.

### 5. Dependency closure
**PASS.**
- `uv lock` re-run: **no-op** (`diff` against pre-run lock: identical).
- `discord-py` / `aiohttp`: 0 hits in `uv.lock`.
- `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` (verified against `.github/workflows/windows-installer.yml`, `.github/workflows/pr-lint.yml`, and `ci/tasks/windows-installer-build.yml` — all three use this exact invocation): **succeeds**, output contains 0 hits for `discord`/`aiohttp`.
- `uv sync --extra gui --extra all-llms --extra dev`: already in sync (Resolved 126 packages, audited 115, no changes needed).
- Confirmed genuinely unimportable in the synced venv: `import discord` and `import aiohttp` both raise `ModuleNotFoundError`.

### 6. `make test-unit` (fresh run)
**PASS.** `3561 passed, 0 failed, 0 errors, 10 skipped, 542 deselected` — **351.91s (5m51s)**, wall time 6m04s including make overhead. Exactly matches leg 2's landed count (no drift, as expected with zero source changes this leg).

### 7. Browser lanes
**Basis: leg 2's recorded runs stand — not re-run.** This leg made zero source changes and no other work has landed on the branch since leg 2's landing earlier the same day (2026-08-30); nothing under `the_one/interfaces/web/static/` or `tests/browser/` changed. Leg 2's recorded results: studio 139p/3s (3m56s), chat 39p/0s (1m15s), system 106p/0s (2m30s), shared 174p/3s (1m29s) — all 4 green, 458 passed / 6 skipped total.

### 8. Migration + rotation tests (targeted, in isolation)
**PASS.**
- `tests/test_db_migration.py` full file in isolation: **84 passed**, 25.75s — includes `TestSchemaV38::test_v38_upgrade_drops_columns_and_table_and_rows`, `test_v38_idempotent_on_stamp_rewind`, `test_v38_idempotent_on_double_ensure`, and `TestSchemaV23::test_v23_legacy_v22_rows_chain_to_v38` (the v23→v38 chained-legacy-row upgrade path) — all pass.
- `tests/test_provider_api.py::TestEncryptionRotation::test_rotate_connector_secrets`: **PASS** (1 passed, 175 deselected) — the kept `connectors` table rotation invariant holds.

### 9. Metrics baseline
- **Suite**: 3,561 passed / 10 skipped / 542 deselected / 351.91s (5m51s) vs. the pre-flight M22 baseline of **4,571 passed / 10 skipped / 0 flakes / 8m29s** — net **-1,010 tests** (deleted, not skipped — skip count is flat at 10 both before and after), **-2m38s** wall time.
- **Python LOC under `the_one/connectors/`**: **0** (`find ... -name "*.py" | xargs wc -l` → no files). **Directory itself is not literally absent** — `the_one/connectors/` still exists on disk containing only a stray, root-owned, pre-existing `__pycache__/` subdirectory (mtime 2026-06-05, predates this flight, gitignored, untracked). All 18 tracked source files (17 `.py` + `README.md`) are correctly `git`-deleted (working-tree `D`, uncommitted per the flight's commit model). Because there is no `__init__.py`, `the_one.connectors` still resolves as an **empty PEP 420 implicit namespace package** (`import the_one.connectors` succeeds, `__file__` is `None`, `dir()` shows only dunders, zero attributes/submodules) — no functional code, zero LOC, but the "directory absent" wording in the leg's own criterion is not literally satisfied. Could not remove the stray `__pycache__` (root-owned; out of scope for a no-source-changes leg regardless).
- **Connector-tool LOC**: **0** (`connector_history.py`, `connector_send.py` both absent from `the_one/tools/`).
- **Connector Studio JS LOC**: **0** (all 9 named files absent from `the_one/interfaces/web/static/`).
- **Repo-wide diff stat vs `main`**: `207 files changed, 1614 insertions(+), 67171 deletions(-)`.

### 10. Packaging spec parse
**PASS.** `python3 -c "compile(open('packaging/windows/the-one.spec').read(), 'spec', 'exec')"` succeeds. Confirmed the `nacl` exclusion is removed: `excludes = []` at `the_one-spec:189` (was `excludes=["nacl"]`).

---

## Decisions
- **2026-08-30**: `_connector_repo()` in `api.py` (constructs `ConnectorRepository`) was orphaned by the route-block deletion (its only callers were the 18 deleted routes) but wasn't explicitly named in the leg's citation list. Deleted it as the same class of cleanup already authorized for the route block, along with the now-unused `ConnectorRepository` import — flagged here rather than silently left as dead code.
- **2026-08-30**: `tag_post_step_visibility` (the WS-storage-edge-shim visibility mutator, consumed by `app.py`'s `_process_and_broadcast` / `_resume_paused_session` and pinned by `tests/test_ws_storage_edge_shim_visibility.py`) lived in the deleted `the_one/connectors/post_step_metadata.py`, not just the `OPERATOR_VISIBILITY` constant DD-3 named. Relocated the function itself to `llm/base.py` alongside the constant, inlining the `PLATFORM_SEND_OK_PREFIX` literal it referenced internally (matching DD-3's treatment of that constant at the test call site). See Deviations.

---

## Deviations
1. **Unnamed surviving consumer found via re-grep**: `tag_post_step_visibility` — a real function, not just `OPERATOR_VISIBILITY` — had a surviving caller in `app.py` outside the connectors package. DD-3 and the leg's step 1 only named the constant. Resolved by the same relocation treatment (moved to `llm/base.py`), consistent with DD-3's rationale ("`Message.visibility` is a kept piece"). **Flight-end Reviewer: please double-check this relocation** — it's the one place this leg made a judgment call beyond the leg artifact's literal citations, even though it's the same class of fix as the explicitly-authorized `OPERATOR_VISIBILITY` move.
2. **Migration-chain interaction bug found and fixed**: adding v38 broke `TestSchemaV7::test_v7_strips_removed_tool_names` and similar rewind-replay tests — v23's re-entry guard (`if post_v23_target_exists: ... elif pre_v23_source_exists: <segments 1-4>`) assumed "`connectors` table exists" implies "`pending_approvals`/`agents` are also already in post-v23 shape," which v38 breaks by treating `connectors` (rows-only clear) and `pending_approvals`/`agents.connector_ids` (drop) asymmetrically. Fixed by adding independent re-checks for segment 2 (`pending_approvals` rename) and segment 4 (`agents` rename) inside the `if post_v23_target_exists:` branch, scoped narrowly to that branch — the historical `elif` branch (segments 1-4 as originally written) is untouched. **Flight-end Reviewer: please scrutinize this fix** — it's the one place this leg edited pre-existing frozen-history migration logic rather than purely adding new code; `the_one/db/schema.py` lines around the `post_v23_target_exists` branch in the `if version < 23:` block.
3. **`uv sync --extra gui --extra all-llms`** (the exact command the leg's Verification Steps specifies) uninstalled the dev/test toolchain (pytest, ruff, playwright, pre-commit, pip-audit, and 46 others) from `.venv` because it omitted `--extra dev`. Re-ran as `uv sync --extra gui --extra all-llms --extra dev` to restore it, then re-verified `discord`/`aiohttp` are genuinely absent and re-ran the full suite. Flagging so the Verification Steps text can be corrected (add `--extra dev`) before Leg 3 or future runs rely on it.
4. **Citation drift beyond the leg's own "known drift" list**: `test_pairing_prefix.py`, `test_api_connector_config_validation.py`, and `test_connectors_routing_schema.py` were connector-only test files not named in the recon report's "26 connector-named files" but caught by re-grep and deleted (all three tested functionality — `_pairing.py`'s helper, `_validate_connector_config`'s Discord branch, the reserved-keys config validator — deleted by this leg). `test_factory.py`'s `TestNativeApiWiring` and the main `factory` fixture also carried dead `ConnectorRepository`-mock scaffolding not tied to any specific cited line range; removed as the same class of cleanup.
5. **`agents.md` still contains ~27 hits** for `the_one.connectors`/`the_one/connectors` (all in prose/citations) — this is docs, explicitly leg 2's scope per the leg's own Files Affected section, so left untouched. Flagging because the leg's own acceptance-criteria grep (`the_one/ tests/`) is literally broad enough to walk `the_one/agents.md` and would show these as "failures" if run without this context.

---

### `frontend-tests-docs-removal` (leg 2)

6. **Two browser test files found via content re-grep, not named in the recon list**: `test_flow_studio_mcp_navigation.py` (`test_studio_section_nav_includes_mcp_servers` asserted 4 nav buttons incl. "Connectors" — edited to 3, not deleted, since the file is otherwise a legitimate MCP-navigation test) and `test_flow_studio_per_agent_admit_dms.py` (entirely `connector_acls[account_id].admit_dms` / agent-editor Connectors-tab exclusive — deleted wholesale). Neither filename contains "connector", so the recon's filename-based inventory missed them; caught by `grep -l "connector" tests/browser/*.py -i` before running the lanes.
7. **`docs/agents.md`'s "Citation (n=1 from...)" historical-incident paragraphs contained the literal banned strings** (`the_one/connectors/_pool.py`, `the_one/connectors/_inbound.py`, `the_one/connectors/base.py`) even though clearly framed as past-tense incident narratives, not live pointers — the leg's acceptance-criteria grep (`the_one.connectors|the_one/connectors`) is a literal string match with no carve-out for tense. Reworded 3 citations (the `protocol-widening-for-required-capability`, `llm-controlled-behavior-is-not-a-production-contract`, and `pool-warming-entrypoints-are-finite-and-named` convention citations, plus the top-of-file "Connector subsystem removed" placeholder note) to describe the same incidents without the literal module path, so the grep passes without falsifying the history. The docs-sweep sub-agent's own pass had left these four as deliberate historical-narrative exceptions (a reasonable call in isolation); this leg's literal grep is stricter than that judgment allows, so the follow-up rewording was needed to actually satisfy the acceptance criterion.
8. **`test_manual_exception_testids_still_in_source` (`test_ui_guards.py`) hard-asserted the manual-exceptions table is non-empty** (`assert reg_manual, "...empty or unparseable"`) — a safety net against silent parser breakage. All 4 entries in that table (`connector-continuation-input`, `connector-idle-timeout-input`, `create-and-test-connector-btn`, `save-connector-btn`) were `connector-editor.js`-only, so the table legitimately empties out this leg. Relaxed the assertion to tolerate a genuinely-empty table (documented in the test's own docstring) rather than removing the safety net outright — a future feature reintroducing a variable-carried testid re-populates the table and the missing-literal check still fires.
9. **Two `test_design_tokens_a11y.py` tests deleted, not just their token citations**: `test_connector_empty_types_banner_prose_passes_body_aa` and `test_discoverable_dropdown_hover_item_text_passes_body_aa` pinned contrast ratios for `.connector-empty-types-banner` and `.discoverable-dropdown-item:hover`, both deleted wholesale from `studio.css` this leg. The leg's own acceptance criterion only said "`test_design_tokens_a11y.py` pass," not "delete tests whose CSS subject is gone" — flagging since these are the one place this leg removed test *functions* (not just rows/tokens) beyond the leg's literal step list, discovered by running the file and reading the failures rather than by citation.
10. **`js/areas/studio/agent-editor.js`'s Connectors tab removal and `tests/browser/test_flow_agent_tabs.py`'s structural rewrite were paired in the same pass** per the leg's step 6 instruction — `test_tablist_renders_with_six_tabs` renamed to `test_tablist_renders_with_five_tabs`, count assertion 6→5, `tab-connectors` assertions dropped. No `[data-testid="tab-connectors"]` or `agent-tab-connectors` references remain anywhere in `static/`/`tests/`/`docs/` (re-grepped after the edit).

---

## Anomalies

1. **Orphaned `routing-audit` UI remnant (leg 3 finding, 2026-08-30)**: `the_one/interfaces/web/static/css/chat.css:287-462` (~176 lines) still styles the deleted `routing-audit-panel.js`'s DOM, with no surviving JS/HTML consumer; `app.py`'s `Session.session_metadata` plumbing and `api.py:3157-3174`'s `GET /api/chat/sessions/{id}` response field are the dead read/ship side of the same feature (the connector-dispatcher write side was already deleted in leg 1). Not a functional regression (unreachable), but exactly the DD-7 tripwire class — leg 2's own sweep terms didn't include "routing-audit" as a standalone grep and missed it. See Verification Report §4 for full detail. Flight Director: needs a decision (cleanup pass vs. accepted debt) before flight-end commit.
2. **`the_one/connectors/` directory not literally absent (leg 3 finding, 2026-08-30)**: all 18 tracked files are correctly deleted, but the directory persists on disk because of a stray, root-owned, pre-existing `__pycache__/` subdirectory (untracked, gitignored, predates this flight). `the_one.connectors` therefore still imports as an empty PEP 420 namespace package (zero LOC, zero attributes) rather than raising `ModuleNotFoundError`. See Verification Report §9. Cosmetic/filesystem-only; flagged since the leg's own criterion text says "directory absent."
