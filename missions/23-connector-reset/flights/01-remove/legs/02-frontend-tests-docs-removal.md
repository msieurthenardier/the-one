# Leg: frontend-tests-docs-removal

**Status**: completed
**Flight**: [Remove](../flight.md)

## Objective
Delete the connector frontend (9 JS files + shared-file excisions + CSS), the remaining browser connector tests, the 10 connector behavior specs, and the connector testid-registry/guard surface; sweep the docs; and restore ALL test lanes to green — closing the browser-lane redness window leg 1 opened.

## Context
- Leg 1 landed the backend deletion: no connector runtime, no routes, `make test-unit` green (3,612 passed / 6m55s), venv has no `discord`/`aiohttp`. Frontend, docs, testid registry, `scripts/run-tests.sh`, `tests/_acl_shape_helpers.py`, and `tests/browser/seeders.py` were left untouched for this leg.
- Flight DD-7: deletions travel with their test/registry updates — the tripwires are `test_index_asset_cache_busting.py` ↔ `index.html`, `test_ui_guards.py`/`test_design_tokens_a11y.py` ↔ testid registry + JS, and the guard helpers (`tests/_ui_guard_helpers.py`, `tests/browser/design_tokens.py`) that enumerate connector testid prefixes.
- This leg's green gate is FULL: `make test-unit` AND all four browser lanes (`scripts/run-tests.sh --lane studio|chat|system|shared`). The DD-7 redness window ends here.
- **Kept concepts to protect**: the Chat session platform badge and unified-history rendering key on the kept `chat_sessions.platform` columns and `Message.visibility` — `history-buckets.js` likely needs NO code change; `chat.js` keeps platform-session rendering while losing approval/routing UI. Two browser tests exercising kept behavior (`test_flow_chat_visibility_distinction.py`, `test_flow_chat_peer_attribution.py`, already import-fixed in leg 1) must still pass.
- The authoritative inventory is the flight log's Reconnaissance Report (Frontend, Tests, Docs sections) plus leg 1's Leg Progress entry for what already happened. Re-grep every citation.
- Leg 1 deviation to honor: any `uv sync` here must include `--extra dev` or it strips the test toolchain.

## Inputs
- Branch `flight/01-remove` with leg 1 landed (uncommitted, by design — flight-end commit model).
- `make test-unit` green; browser lanes red (expected, DD-7).

## Outputs
- No connector JS/CSS/testids/behavior-specs anywhere under `the_one/interfaces/web/static/`, `docs/ui-testid-registry.md`, or `tests/behavior/`.
- `index.html` without the 9 connector script tags; asset-count test updated.
- `scripts/run-tests.sh` without `test_connector_*`/`test_flow_connector_*` globs; `CLAUDE.md:232`'s lane-glob description matches.
- `tests/_acl_shape_helpers.py` deleted; `tests/browser/seeders.py` edited first.
- Docs (`the_one/agents.md`, `SECURITY-MODEL.md`, `CLAUDE.md`, `README.md`) free of routing/ACL/approval/slash-command/engagement-gate references; a short "connector subsystem reset — contract defined in Flight 2" placeholder where the architecture docs described the subsystem.
- All lanes green.

## Acceptance Criteria
- [x] The 9 connector JS files are deleted; `grep -rin "connector\|discoverable\|discord" the_one/interfaces/web/static/` returns zero hits (the `discord` term catches the orphaned badge tokens the narrower grep missed; remaining platform-session code/comments reworded to platform terms — connector wording returns with Flight 2's actual contract)
- [x] `index.html` has no script tag referencing a deleted file, and `test_index_asset_cache_busting.py` passes with its updated expected count
- [x] `grep -rn "/api/connectors" .` (excluding `.git/`, `missions/`, `maintenance/`, `squawks/`) returns zero hits repo-wide
- [x] `docs/ui-testid-registry.md` has no connector/approval/routing-audit rows; `tests/_ui_guard_helpers.py` and `tests/browser/design_tokens.py` enumerate no connector prefixes; `test_ui_guards.py` and `test_design_tokens_a11y.py` pass
- [x] The 10 connector behavior specs and their `runs/` directories are deleted; the 5 incidental-mention specs are edited; `ls tests/behavior/ | grep -i "connector\|discord\|routing"` is empty
- [x] `tests/_acl_shape_helpers.py` is deleted and `tests/browser/seeders.py` no longer imports it
- [x] The remaining browser connector test files (the ~15 connector-named + the connector-only flow files from the recon list not already deleted in leg 1) are deleted; `test_flow_chat_visibility_distinction.py` and `test_flow_chat_peer_attribution.py` still pass (kept behavior)
- [x] `the_one/agents.md`, `SECURITY-MODEL.md`, `CLAUDE.md`, `README.md`: zero references to the removed capabilities (routing engine, ACL axes, peer approvals, slash commands, engagement gate, discoverable dropdowns, discord.py); kept concepts (`Connector` row, rotation corpus, `Message.visibility`, session keying) still accurately described; `grep -rn "the_one.connectors\|the_one/connectors" the_one/ tests/ docs/ *.md` (excluding historical artifacts) returns zero
- [x] `make test-unit` green with no new skips/xfails
- [x] `scripts/run-tests.sh --lane studio`, `--lane chat`, `--lane system`, `--lane shared` all pass
- [x] Flight log updated with a leg progress entry (files deleted/edited, lane results, deviations)

## Verification Steps
- Run the greps in the criteria; each must return as specified.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_index_asset_cache_busting.py tests/test_ui_guards.py tests/test_design_tokens_a11y.py -x --timeout 30` — targeted tripwire check before the full runs.
- `make test-unit` (full), then each of the four browser lanes.
- Visual spot: `grep -n "script src" the_one/interfaces/web/static/index.html` — every referenced file exists.

## Implementation Guidance

1. **Delete the 9 JS files**: `connector-editor.js`, `connectors-tab.js`, `discoverable-dropdown.js`, `connector-form-discord.js`, `routing-audit-panel.js`, `connector-form-registry.js`, `connectors-grid.js`, `pending-approval-banner.js`, `connector-vocabulary.js`.
2. **`index.html`**: re-grep for ALL script tags referencing deleted files (recon says 9 tags at `:43, :47, :54, :61-66` — verify, don't trust). Update `test_index_asset_cache_busting.py`'s exact count in the same pass.
3. **Shared JS edits** (re-grep `connector`, `approval`, `routing`, `discoverable`, `discord` per file): `js/areas/studio.js` (~123 refs — editor registration, overlay dropdown `:2401-2497`, event-bus wiring `:353-360`, 6 fetches), `js/areas/chat.js` (~23 refs — approval handlers `:495-614`, `:812-814`, routing-audit `:334`; the WS `pending-approval` handler runs `:1449-~1465`, longer than first cited; KEEP platform-session badge/unified-history rendering), `agent-editor.js` (14 hit lines, not 9 — includes the `tab-connectors` tab-button/panel markup `:105-131` that `test_flow_agent_tabs.py` asserts against; fix the pair together, see step 6), `status-section.js`, `studio-event-bus.js`, comment-only edits in `mcp-server-editor.js`, `provider-editor.js`, `message-bubble.js`, and `tools-editor.js:170` (an unrelated hover-affordance comment containing "discoverable" — reword it so the zero-hits grep passes; expected hit, not breakage).
3b. **`history-buckets.js` DOES change** (design review correction — not "no functional change"): delete `buildPendingApprovalsSection()` and the `pendingApprovals` parameter/branch in `renderSessionList()` (`:116-160`, rendering the `pending-approvals-section`/`pending-approval-item` testids), and drop the trailing `pendingApprovals` argument at the `chat.js:1193` call site. The platform-badge/bucket rendering stays.
3c. **`js/app.js` badge surface, full extent**: the poll `:15-28` AND `_startPendingBadgePoll()` `:229`, the `badgeHtml`/`data-testid="nav-pending-badge"` markup in `renderTopBar()` `:48-61`, the `.nav-pending-badge` rule in `components.css` ~`:106-120`, and the `shell`-area registry row `docs/ui-testid-registry.md:171`.
4. **CSS**: excise connector blocks from `css/studio.css` (~123 refs), `components.css` (4 hits incl. the badge rule above), `chat.css` (2), `admin.css` (2 — one is a COMMENT at `:316` listing `.connector-always-listen-row` alongside three unrelated KEPT classes: edit the comment, don't delete the rule). **`css/tokens.css`**: remove the connector-exclusive `--badge-discord`/`--badge-ink-discord` pairs (light `:136-137`/`:157-158`, dark `:271-272`/`:292-293`) AND their `badge_discord`/`badge_ink_discord` mirrors in `tests/browser/design_tokens.py` — the mirror-sync test checks values match, not that tokens have live consumers, so orphans survive it silently. `--badge-unknown`/`--badge-ink-unknown` are SHARED with provider/tool badges — keep them. Remove shared-selector rules only when every selector targets deleted markup.
5. **Testid surface (one pass, DD-7)**: prune `docs/ui-testid-registry.md` connector/approval/routing rows (+ the `connector-row-` prefix note at `:19`), the prefix enumerations in `tests/_ui_guard_helpers.py` and `tests/browser/design_tokens.py`, and fix `test_ui_guards.py` / `test_design_tokens_a11y.py` expectations together.
6. **Browser tests**: delete the remaining connector-named files under `tests/browser/` and the connector-only flow files from the recon list (pending-approval ×2, routing-audit, always-listen, per-agent overlays ×3, hierarchical rows, source badge, operator-input visibility — re-check which leg 1 already took). Edit `tests/browser/seeders.py` (drop the `_acl_shape_helpers` import `:27` and its uses), then delete `tests/_acl_shape_helpers.py`. Sweep remaining single-ref browser files — two need STRUCTURAL rewrites, not line strips: `test_flow_agent_tabs.py:64-92` (`to_have_count(6)` → 5, drop the `tab-connectors` `aria-selected` assertion block, rewrite the six-tab docstring — paired with `agent-editor.js:105-131`) and `test_flow_studio_navigation.py:85-173` (the `connectors` section-nav `tabindex`/focus assertions); plus `test_flow_studio_loadall_error.py`, `test_flow_provider_plan_signin.py`, `browser/conftest.py`, `browser/design_tokens.py` (the badge_discord mirrors, per step 4). Known false positives — confirmed clean, no action: `test_flow_hash_routing.py` ("approval"/"pending" hits are hash-routing), `self-configuration-tab.js` (M21 self-revision approval, unrelated).
7. **Behavior specs**: delete the 10 connector-exclusive specs + `runs/` dirs; edit the 5 incidental (`agent-history-auto-purge`, `agent-purge-now-clears-history`, `shell-navigation-smoke`, `studio-agent-crud`, `studio-smoke`).
8. **Lane plumbing**: `scripts/run-tests.sh:62-63` — remove `test_connector_*`/`test_flow_connector_*` globs from the studio lane; update `CLAUDE.md:232`'s glob description and delete the `:229` discord-package caveat.
9. **Docs sweep**: `the_one/agents.md` — remove the connector-subsystem sections (`:1187-1307`, `:1642-1696`), the M10/M11 mission-specific entries that describe removed machinery (`:544-707` selectively — entries about kept concepts like session keying or visibility stay), the F9 contract section (`:728-744`); rewrite exemplar citations that point at deleted files (`:152-179`, `:243`, `:261-263`, `:274-301`, `:314-336`, `:385-408`) to cite surviving exemplars — do not delete the conventions themselves. `SECURITY-MODEL.md` `:208, :278, :625, :634` one-line edits (last two keep the concept, fix wording). `README.md` `:123` paragraph → one-line "connector subsystem reset; new minimal contract lands in Mission 23 Flight 2" placeholder; `:125` persistence wording. Preserve operator anonymity in everything written (no usernames/home paths).
10. **Close out**: targeted tripwire tests, `make test-unit`, all four browser lanes. Record lane timings in the flight log entry.

## Edge Cases
- **Kept chat behavior**: the two surviving visibility/attribution browser tests define "kept" — if an edit to `chat.js` breaks them, the edit went too far.
- **`studio.js` event-bus**: other Studio editors share the bus (`studio-event-bus.js`) — remove connector subscriptions only, not the bus.
- **Behavior-spec runs/ dirs**: delete with their specs; do not leave orphaned run logs.
- **agents.md conventions**: the convention entries are methodology the project keeps — only their connector *exemplars* change. When a convention's only exemplar was connector code, cite the nearest surviving analogue (MCP pool, provider editor).
- **Grep hygiene**: the repo-wide `/api/connectors` grep will hit historical `missions/`/`maintenance/`/`squawks/` artifacts — those are excluded by design; never edit inspection records.

## Files Affected
See flight log Reconnaissance Report sections: Frontend (deletes + edits), Tests (browser remainder + helpers + tripwires), Docs; minus everything leg 1's Leg Progress entry already reports done.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` + all four browser lanes)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header) — commit happens at flight end
- [x] Check off this leg in flight.md
