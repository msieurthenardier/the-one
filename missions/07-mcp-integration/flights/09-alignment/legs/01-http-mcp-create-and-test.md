# Leg: 01-http-mcp-create-and-test

**Status**: completed
**Flight**: [Alignment — MCPs working well end-to-end](../flight.md)

## Objective

Vibe-code-walk the operator workflow for creating and testing an HTTP (streamable-http) MCP source from scratch in the Studio MCP Servers area, against the live Cloudflare API MCP server. Surface and fix any bugs, UX gaps, or polish issues inline. Verify the F1/F6.5/F8 surfaces (create form, Test connection button, OAuth popup, capability flags one-liner, collapsible input schemas, `__MASKED__` round-trip) feel good end-to-end.

## Context

- **Flight Design Decision §1** — multi-leg vibe-coding, this leg is the first of seven workflow-focused vibing legs.
- **Flight Design Decision §2** — fix-inline default; Sizing Thresholds table governs LOC bars per anomaly type.
- **Flight Design Decision §4** — done-criteria is operator-felt + caplog gate (HAT-only, F6 baseline pattern: 0 `MCPClient.disconnect` warnings across this leg's exercises).
- **Flight Design Decision §5** — F8 carve-outs (per-agent OAuth re-auth, no-auth detection, `_pool.py` test isolation) default to defer; A6 may surface here if a no-auth probe is attempted.
- **Flight Design Decision §7** — inline fixes touching `mcp` SDK lifecycle, OAuth flows, pool worker spawn-path, `MCPToolProvider`, resolver, or `errors.py` get a ≤5-min architect pass before implementation.
- **Flight Design Decision §8** — single bundled fresh-context Sonnet review at flight close; this leg's inline-fix LOC contributes to the L8 review queue, no per-leg review.
- **Flight Design Decision §9** — all code-change work delegated to subagents (parent context = vibing + triage only). File edits, multi-file code investigation, and test additions all go to subagents. Parent sees return summaries, not full diffs or investigation traces.
- **L1 design choice — Cloudflare state at L1 start: fresh-DCR (delete + re-create source)**. Picked because:
  - Fresh-DCR exercises the highest-friction operator path (first-time consent, popup UX, post-consent retest, tools-list cold render). This is where vibing surfaces the most signal.
  - The leftover-state path (refresh-token rotation) gets exercised naturally in L5 (single HTTP MCP in chat) where the chat session lives long enough to cross the token's expiry boundary.
  - L1 leaves the Cloudflare source registered + authed at the end, ready for L3 (HTTP attach) and L5 (HTTP in chat) to inherit.

## Inputs

What exists before this leg runs:
- Dev container running on `http://localhost:8484`; web UI loads.
- F8 deliverables in production: capability flags one-liner (`mcp-server-editor.js:30-53` — `renderCapabilityFlags`); collapsible Input schema viewer (`mcp-server-editor.js:917-926`); Test connection button (visible in edit-mode for streamable-http per F6.5 L4); OAuth popup centered (`mcp-server-editor.js:932-966`).
- Test connection endpoint at `the_one/interfaces/web/api.py:821 — "@router.post(\"/mcp-sources/{source_id}/test/connect\")"` and `the_one/interfaces/web/api.py:822 — "async def test_mcp_connection(source_id: str, request: Request)"`.
- Operator has Cloudflare credentials available for OAuth consent in the popup.
- Pre-leg housekeeping per the flight's Prerequisites section: warm-pool clear via `docker compose restart the-one`; F8 baseline as the regression diff target.

## Outputs

What exists after this leg completes:
- A registered, OAuth-authed `cloudflare_api` source pointing at `https://mcp.cloudflare.com/mcp` — handed off to L3 + L5.
- Any inline fixes to `mcp-server-editor.js`, `mcp-servers-grid.js`, `the_one/interfaces/web/api.py::test_mcp_connection`, related CSS, or related browser tests — captured in the diff and logged in the flight log under "L1 → Inline Fixes Implemented".
- Flight log appended with: per-scenario operator-felt notes, anomalies + triage + resolution, caplog count.

## Acceptance Criteria

- [ ] All 10 scenarios walked; operator reports the create-and-test workflow "works well" overall.
- [ ] Caplog gate clean: 0 `MCPClient.disconnect` warnings across this leg's HAT exercises.
- [ ] Any anomaly surfaced is triaged per Flight Design Decisions §2 + §5 (inline-fix / absorb-into-{leg} / defer-to-{follow-up flight}) and recorded in the flight log.
- [ ] If `cloudflare_api` source registered + OAuth-authed at leg close (default outcome): documented in flight log; ready for L3/L5 to inherit. Exception: if the leg defers core create-or-test work to a follow-up flight, document the deferral and note that L3/L5 may need to re-walk the affected workflow.

## Verification Steps

For each scenario, the operator reports the observed outcome in plain language. The Flight Director (Claude) compares against the expected outcome and asks the operator to confirm "works well" before moving to the next scenario. Any divergence triggers triage + fix-or-defer.

Caplog gate check: at any anomaly + at leg close, run `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` — count should remain at 0.

## Implementation Guidance

### Procedure shape (Flight Design Decision §1's structured pattern)

1. **Setup** — operator confirms dev container up; warm-pool cleared; ready to drive the web UI.
2. **Walk operator scenarios** — Flight Director presents one scenario at a time; operator performs; Flight Director compares observed-vs-expected.
3. **Capture issues** — anomalies logged immediately into the flight log under "Anomalies Captured" for L1.
4. **Triage** — per §2 + §5: inline-fix (default for ≤100 LOC + leg-scope) / absorb-into-sibling / defer-to-follow-up. Architect pass per §7 if the fix touches a known-problematic-path.
5. **Fix or document** — inline fixes implemented immediately; absorbs/defers logged with target-leg or follow-up-flight reference.
6. **Re-verify** — re-walk affected scenarios to confirm fix.
7. **Close leg** — operator-felt sign-off + caplog gate verification + flight log finalization for L1.

### Operator scenarios (10 total)

**Scenario 1 — List view sanity.**
Operator: navigate to Studio → MCP Servers (URL `#studio/mcp-sources`).
Expected: list view renders; existing sources visible (likely `cloudflare_api` from F8 HAT). Note current state for cleanup in scenario 2.
Vibing prompts: Does the list look clean? Are transport-type badges scannable? Is there a clear "Create" affordance?

**Scenario 2 — Delete leftover Cloudflare source for clean slate.**
Operator: click into existing `cloudflare_api` source (or whatever the F8-leftover Cloudflare source is named). Use the delete affordance. Confirm prompt.
Expected: confirmation prompt is clear; source removed from list; no stale state.
Vibing prompts: Does the confirm prompt feel safe? Does the list update without a manual refresh?

**Scenario 3 — Create form: navigation + transport switching.**
Operator: click "Create" / navigate to `#studio/mcp-sources/new`. Toggle the transport selector between `stdio` and `streamable-http`.
Expected: form opens; transport-aware fields swap appropriately (HTTP shows URL/headers; stdio shows command/args/env).
Vibing prompts: Is the transport selector obvious? Do the fields swap cleanly without state bleed (e.g., URL field doesn't carry a stale stdio command)? Are field labels and help text readable?

**Scenario 4 — Create form: validation.**
Operator: try to save with required fields empty (no name, no URL).
Expected: validation messages are specific, actionable, surfaced near the offending field.
Vibing prompts: Are the messages clear? Do they tell the operator what to fix? Is focus moved to the first error?

**Scenario 5 — Fresh Cloudflare creation.**
Operator: fill in `name=cloudflare_api`, `transport=streamable-http`, `URL=https://mcp.cloudflare.com/mcp`. Save.
Expected: source saves; redirect to detail/edit page (or back to list with success indicator).
Vibing prompts: Is the post-save state clear? Where did I land? Is it obvious the source was created?

**Scenario 6 — First Test connection (auth_required path).**
Operator: on the Cloudflare source detail page, click "Test connection".
Expected: Phase A connect attempts → 401 from Cloudflare → backend returns `auth_required` → UI surfaces the auth-required state (button or notice indicating consent is needed).
Vibing prompts: Is it clear what just happened? Is the next step (do OAuth) discoverable? Does the loading state feel responsive (~0.5-2s per Phase A bound)?

**Scenario 7 — OAuth consent + retest with full tool render.**
Operator: trigger OAuth consent (popup opens centered). Complete Cloudflare consent in the popup. Popup closes. Click Test again (or auto-retest if F9 design surfaces that as an inline-fix candidate).
Expected: tools list renders. Capability flags one-liner appears (`Server supports: tools, …`). Each tool has a collapsible `<details>` with input schema as pretty-printed JSON.
Vibing prompts: Is the popup-then-click-Test-again rhythm acceptable, or does it want auto-retest? Are the capability flags scannable? Is the schema readable? Are tool descriptions useful? Does the post-test view feel like "this MCP works"?

**Scenario 8 — Edit cycle with `__MASKED__` round-trip.**
Operator: edit the source — change a header field (or add one), leave any persisted secrets alone. Save. Reload. Verify secret-bearing fields show `__MASKED__`. Save again WITHOUT retyping. Reload. Verify the original values are preserved.
Vibing prompts: Is `__MASKED__` self-explanatory? Is the round-trip lossless?

**Scenario 9 — Deep-link / hash routing.**
Operator: navigate away from the source-edit page (e.g., to Studio → Agents). Then in a new tab or via URL bar, navigate directly to `#studio/mcp-sources/{cloudflare-source-uuid}`.
Expected: edit page loads with source state populated; no flash of empty state; URL hash matches.
Vibing prompts: Does the deep-link feel snappy? Does state hydrate cleanly?

**Scenario 10 — Error path: bogus URL.**
Operator: create another HTTP source with a bogus URL (e.g., `https://mcp.invalid.example.com/`). Click Test.
Expected: error state renders cleanly; message is actionable; UI doesn't hang.
Vibing prompts: Is the error message useful? Could it be clearer? Does the error state visually distinguish from auth_required?

**Cleanup**: operator deletes the bogus source from scenario 10. The legitimate `cloudflare_api` source from scenarios 5-9 is left registered + OAuth-authed for L3/L5 to inherit.

### Per-anomaly procedure

When an anomaly surfaces:
1. Operator describes what happened in plain language.
2. Flight Director logs it in the flight log under "Anomalies Captured" for L1 (severity: blocking | degraded | cosmetic; what surface; what scenario).
3. **If root cause unclear** → spawn an Investigator subagent (per §9) with the operator's description, the relevant scenario number, and pointers to the likely surface(s) (e.g., `mcp-server-editor.js`'s relevant function). Subagent returns a diagnosis + recommended fix shape. Parent does NOT read the investigation trace.
4. Triage from the diagnosis: per §2's Sizing Thresholds. If touches a known-problematic-path per §7, spawn an Architect subagent for a ≤5-min review of the proposed fix shape.
5. Decision: inline-fix / absorb-into-sibling-leg / defer-to-follow-up.
6. **If inline-fix**: spawn an Implementer subagent (per §9) with the bug description, target file(s) + line ranges, fix shape, and acceptance criterion ("re-verify by re-walking Scenario N — operator should see X"). Subagent makes the edit + adds regression coverage if appropriate; returns a structured summary. Parent stages the change for operator re-verification.
7. **If absorb**: log target leg in flight log; continue L1.
8. **If defer**: log follow-up flight scaffolding in flight log; continue L1 with the affected workflow flagged.

**Subagent return summaries** are appended to the flight log under L1's "Inline Fixes Implemented" section; full diffs are visible in git, not in the leg artifact or flight log narrative.

### Caplog gate

Throughout the leg, monitor `docker compose logs -f the-one` (in a sidecar terminal or via `docker compose logs --tail 200 the-one` periodic check) for `MCPClient.disconnect` warnings. Surface immediately to Flight Director if any appear. At leg close: `docker compose logs the-one 2>&1 | grep -c "MCPClient.disconnect"` should return `0`.

## Edge Cases

- **F8 carve-out A6 surfaces during Scenario 6/7** — if the SDK anyio cross-task cancel-scope leak fires during Phase A connect or list_tools (per F6/F6.6/F8 history), the leg defaults to defer per §5 (don't attempt to fix anyio behavior in F9; that's the dedicated follow-up flight). Log the surfacing in flight log; continue with the workflow if the operator-felt experience is still acceptable, or flag the workflow as deferred-pending-follow-up.
- **Cloudflare consent times out / popup blocked** — log as anomaly; if pop-up-blocked, surface a "Popup blocked" message inline (the existing fallback per `mcp-server-editor.js:932-966`); if consent times out, the operator can retry by clicking Test again. If retry doesn't work, defer to follow-up.
- **Bogus URL DNS-resolves to a real server (e.g., a parking page)** — Scenario 10 may surface unexpected behavior. Switch to a different bogus form (e.g., `https://localhost:1` or `http://invalid./`) until the test path actually fails as intended.
- **Cloudflare source already exists from F8 HAT and operator skips Scenario 2 (deletion)** — leg becomes a leftover-state vibe instead of a fresh-DCR vibe. Acceptable variation per Flight §3 spirit. Document the divergence in flight log.
- **Deep-link in Scenario 9 surfaces a routing bug** — F8's `App.areas` array-shape lock-test should have prevented this, but if a regression surfaces, fix inline (it's a known-problematic-path per §7's principle: cross-flight invariant). Otherwise defer if > ~100 LOC.

## Files Affected

This is a vibing leg; the file set is determined by what the operator surfaces. Predicted touch points:
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (979 LOC) — the most likely site for inline UX/cosmetic fixes (Test button states, capability flags rendering, schema viewer collapse behavior, error rendering, OAuth popup messaging).
- `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js` (117 LOC) — list view; possible inline fixes to badges, empty state, delete confirmation.
- `the_one/interfaces/web/static/css/studio.css` or design-token CSS — possible polish.
- `the_one/interfaces/web/api.py:822 — "async def test_mcp_connection"` — possible inline fix to error message wording or response shape clarity (touches `errors.py` if the change crosses the exception-translation contract — §7 architect pass required).
- `tests/browser/test_flow_studio_mcp_editor.py`, `tests/browser/test_mcp_test_connection_button.py` — possible regression coverage for inline fixes.
- Flight log + this leg's status field — always.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All 10 operator scenarios walked + operator-felt sign-off
- [ ] Caplog gate clean (0 `MCPClient.disconnect` warnings across leg HAT)
- [ ] Anomalies captured in flight log with triage + resolution
- [ ] Inline fixes (if any) implemented; their unit/browser regression coverage added per inline-fix scope
- [ ] `cloudflare_api` source state at leg close documented in flight log (registered + authed; or anomaly-deferred)
- [ ] Update flight-log.md L1 section with: status `landed`, scenarios walked, anomalies + resolutions, caplog count, files touched
- [ ] Set this leg's status to `completed` in this file's header
- [ ] Check off L1 in flight.md's Legs list
- [ ] Inline-fix LOC added to L8 bundled-review queue (running tally in flight log)
- [ ] Commit all changes together (code + leg artifact + flight log)

---

## Citation Audit

5 code-location citations verified against current code at leg design time (2026-05-09):

- `the_one/interfaces/web/api.py:821 — "@router.post(\"/mcp-sources/{source_id}/test/connect\")"` — **OK** (verified at `api.py:821`).
- `the_one/interfaces/web/api.py:822 — "async def test_mcp_connection(source_id: str, request: Request)"` — **OK** (verified at `api.py:822`).
- `mcp-server-editor.js:30-53 — renderCapabilityFlags` — **OK** (function exists per F8 L2 deliverable; line range from F9 recon agent's static read).
- `mcp-server-editor.js:917-926` (collapsible Input schema viewer) — **OK** (per F8 L2 deliverable).
- `mcp-server-editor.js:932-966` (OAuth popup handler) — **OK** (per F6.5 L4 + F8 retention).
- File size citation `mcp-server-editor.js (979 LOC)` — **OK** (verified via `wc -l`).
- Studio MCP Servers area URL `#studio/mcp-sources` — **OK** (verified via grep on `the_one/interfaces/web/static/js/areas/studio/`).

No drift detected; all citations confirm current code state.
