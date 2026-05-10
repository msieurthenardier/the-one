# Leg: 03-http-mcp-attach-to-agent

**Status**: completed
**Flight**: [Alignment — MCPs working well end-to-end](../flight.md)

## Objective

Vibe-code-walk the operator workflow for attaching an HTTP MCP source (the L1-registered `cloudflare_api` OAuth source and/or `cloudflare_docs` no-auth source) to an agent via the Studio agent-editor **MCPs tab** — exercising attach toggle, per-tool enable/disable, save/reload preservation, hash-routing, and the **cross-cut consistency check** between the source-edit Test/Refresh view (L1's surface) and the agent-editor tool list (L3's surface). Surface and fix bugs / UX gaps / polish issues inline. By leg close, the operator should feel that "I can attach an HTTP MCP to an agent and pick which tools the agent can see" works well end-to-end on the streamable-http transport.

## Context

- **F9 §1** — multi-leg vibe-coding shape; this leg is L3 (HTTP attach analog of L4's stdio attach).
- **F9 §2 + Sizing Thresholds** — fix-inline default; per-anomaly LOC bars. **Cumulative production LOC outside vibing surfaces is already at ~1193 (above §2's ~600 ceiling) after L1+L2; L3 should aim for ~0 production LOC outside the seven vibing-surface UI files** (which include `mcps-tab.js`, `studio.js`, `agent-editor.js`, `studio.css` for this leg). Backend changes that aren't in those files trigger immediate operator audit before dispatch.
- **F9 §4** — operator-felt + caplog gate (0 `MCPClient.disconnect` warnings across this leg's HAT exercises).
- **F9 §5** — F8 carve-outs default defer. The per-agent OAuth re-auth gap (F8 A4 + A5) is the most likely L3 carve-out collision: agent-editor's probe path can surface auth-required mid-attach. If it does, the existing inline notice (`mcps-tab.js:317 — "_renderAuthRequiredNotice"`) is the carve-out-conformant landing — operator re-Tests on source-edit page, returns to agent-editor. Per-agent re-auth still deferred.
- **F9 §7** — architect pass before any inline fix touching `mcp_overrides` resolution, `MCPToolProvider.get_tools_for_agent` filter/namespace prefixing, OAuth flows in the attach path, hash-routing logic, or pool worker spawn-path. UI/CSS/copy edits inline-only.
- **F9 §9** — all code-change work delegated to subagents; parent context = vibing + triage only.
- **L1 outcome carry-forward**: cloudflare_api (OAuth) + cloudflare_docs (no-auth) sources registered with `_cache.tools` populated and `_cache.auth_posture` set. F8's A6 (no-auth detection) was absorbed via Shape C, so the no-auth attach path should fast-path through the probe.
- **L2 outcome carry-forward**: stdio sources DELETED at leg close. L3 is HTTP-only; no stdio carry-forward needed (L4 will set up its own stdio source).
- **Methodology insight from L1's flight log** (logged for L8 mission-close): exploratory vibing surfaces operator-felt polish issues more effectively than scripted scenarios. L3 follows the same pattern: scenarios below are coverage check, NOT a strict script.
- **Cross-cut verification per F9 leg sketch** — explicit goal: catch any L1 inline fix that didn't propagate to the attach path (e.g., tool-name rendering polish on source-edit page that the agent-editor still shows raw).

## L3 Carry-Forward Setup

For L3 to start cleanly, the operator confirms (at leg setup time):

- [ ] Dev container running on `http://localhost:8484`; web UI loads.
- [ ] cloudflare_api source still registered + tokens valid (check via source-edit page Refresh — should NOT trigger OAuth popup; `_cache.tools` should populate fast-path).
- [ ] cloudflare_docs source still registered + `_cache.auth_posture: "no_auth"` (check via source-edit page Refresh — fast probe; tools list visible).
- [ ] At least one agent exists OR operator creates one at L3 setup time. The agent's initial state should have NO MCPs attached (so L3's attach toggle is the first attach).
- [ ] (Optional) `docker compose restart the-one` to clear warm pool — only if operator wants to verify cold-start UX. NOT required.

If cloudflare_api's refresh-token has expired since L1, that's an expected lifecycle event — operator re-Tests on source-edit page (re-OAuth flow already polished by L1), then proceeds with L3.

## Inputs

What exists before this leg runs:

- F1-F8 + F9-L1+L2 production state (HTTP create+test polished; stdio create+test polished; agent-editor MCPs tab from F8 in production).
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js:34 — "function renderMcpsTab"` — the L3 primary vibing surface.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:153 — "App.studio.renderMcpsTab"` — integration call site.
- `the_one/interfaces/web/static/js/areas/studio.js:668 — "function fetchMcpSourceTools"` — the probe-on-open backing call (POSTs to `/api/mcp-sources/{id}/test/connect`).
- `the_one/interfaces/web/static/js/areas/studio.js:118 — "if (tab.indexOf('mcps/')"` — hash-routing deep-link parser (F8 L3 Patch A).
- `the_one/interfaces/web/api.py:1144 — "@router.post(\"/mcp-sources/{source_id}/test/connect\")"` + `:1145 — "async def test_mcp_connection"` — backend probe endpoint (already shared between source-edit Refresh and agent-editor probe paths).
- `the_one/mcp/_tool_provider.py:175 — "class MCPToolProvider"` + `:183 — "async def get_tools_for_agent"` — the runtime resolver for `mcp_source_ids` × `mcp_overrides`.
- `tests/browser/test_studio_mcps_tab.py` (393 LOC, 7 tests covering attach, detach, per-tool toggle, empty state, hash routing, auth-required notice, areas array shape lock) — regression baseline.

## Outputs

What exists after this leg completes:

- An agent with cloudflare_api attached (default outcome) — handed off to L5 (HTTP in chat).
- (Optionally) an agent with cloudflare_docs attached or both attached — extra coverage for L5 / L7.
- Per-agent tool overrides exercised (denylist, allowlist, both flavors) on at least one agent + source pairing — exercises the F6 namespacing scheme + `mcp_overrides` resolution.
- Any L3 inline fixes captured in diff and logged in flight log under "L3 → Inline Fixes Implemented".
- Flight log appended: per-scenario operator-felt notes, anomalies + triage + resolution, caplog count, cross-cut verification result.

## Acceptance Criteria

- [ ] Operator attaches at least one HTTP MCP source (cloudflare_api OR cloudflare_docs) to an agent via the agent-editor MCPs tab; reload preserves attachment + per-tool overrides.
- [ ] Operator-felt sign-off on the attach + per-tool override UX: "this works well."
- [ ] **Cross-cut verified**: tool-list shown in source-edit Refresh view (L1's surface) matches agent-editor MCPs tab tool-list for the same source — same tool names, same count, same ordering. No drift between the two surfaces.
- [ ] Hash-routing works: `#studio/agents/{name}/mcps/{source-id}` deep-link auto-opens the source's details panel; closing the panel clears the source-id from the hash; browser back/forward navigates predictably.
- [ ] Auth-required notice path works: if cloudflare_api has been Reset (token cleared on source-edit page), agent-editor MCPs tab for that source shows the inline auth-required notice with link to source settings (`mcps-tab.js:317-329`); does NOT auto-trigger an OAuth popup.
- [ ] Caplog gate clean: `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` = 0 across L3's HAT exercises.
- [ ] All 7 prior `test_studio_mcps_tab.py` tests still pass UNMODIFIED unless an inline fix structurally changes the surface (in which case the test is updated as part of the same batch and flagged for L8 review).
- [ ] Any anomaly surfaced is triaged per F9 §2 + §5 and recorded in the flight log under "L3 → Anomalies Captured".
- [ ] Cumulative production LOC for L3 outside the seven vibing-surface UI files is logged at leg close — target ~0 LOC; actual count flagged for L8 review queue if non-zero.

## Verification Steps

For each scenario, the operator reports the observed outcome in plain language. The Flight Director compares against the expected outcome and asks the operator to confirm "works well" before moving to the next scenario. Any divergence triggers triage + fix-or-defer.

Caplog gate check at any anomaly + at leg close: `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` — count should remain at 0.

Cross-cut tool-list check (criterion #3 above): operator opens cloudflare_api on source-edit page (clicks Refresh), notes tool names + count + ordering. Then navigates to agent-editor MCPs tab, opens cloudflare_api's details panel, notes tool names + count + ordering. Reports any drift.

## Implementation Guidance

### Procedure shape (F9 §1's structured pattern, exploratory mode per L1 + L2 methodology insight)

1. **Setup** — operator confirms L3 Carry-Forward Setup checklist; L3 begins.
2. **Walk operator scenarios** — exploratory primary, scenario list below as coverage check / fallback.
3. **Capture issues** — anomalies logged immediately into flight log under "L3 → Anomalies Captured".
4. **Triage** — per §2 + §5: inline-fix (default for ≤100 LOC + leg-scope) / absorb-into-sibling (typically L4 for stdio-equivalents) / defer-to-follow-up. Architect pass per §7 if the fix touches a known-problematic-path.
5. **Fix or document** — inline fixes implemented immediately via Implementer subagent (per §9); absorbs/defers logged with target-leg or follow-up-flight reference.
6. **Re-verify** — re-walk affected scenarios to confirm fix.
7. **Close leg** — operator-felt sign-off + caplog gate verification + flight log finalization.

### Operator scenarios (6 total, coverage check for exploratory mode)

**Scenario 1 — Tab navigation + empty/list-state branch.**
Operator: navigate to Studio → Agents → pick or create an agent → click the MCPs tab (`agent-editor.js:98 — "id=\"agent-tab-mcps\""`).
Expected: tab activates; panel renders. Sources list visible (cloudflare_api + cloudflare_docs as rows); transport-type badges show "streamable-http" (`mcps-tab.js:127 — "source.type === 'stdio' ? 'stdio' : 'streamable-http'"`).
Vibing prompts: Is the MCPs tab discoverable from the tablist? Are streamable-http vs stdio badges visually distinct enough? List ordering predictable (creation order? alpha?)?

**Scenario 2 — Attach toggle + Save + reload preservation.**
Operator: toggle attach for cloudflare_api ON (the row's switch — `mcps-tab.js:107-118`); click Save; reload page; navigate back to the agent → MCPs tab.
Expected: attach toggle persists ON across reload. The agent's stored `mcp_source_ids` includes cloudflare_api's UUID. Save selector contract per `mcps-tab.js:18 — "[data-mcp-source-toggle]:checked"` collected by `studio.js::collectFormData`.
Vibing prompts: Save indicator clear (dirty tracking working)? Reload preservation feels right? Does the page state recover smoothly?

**Scenario 3 — Open details panel + tool list rendering + cross-cut consistency.**
Operator: open cloudflare_api's `<details>` row (`mcps-tab.js:163 — "details.addEventListener('toggle')"`).
Expected: lazy-loads body via `_populateDetailsBody` (`mcps-tab.js:196`); calls `fetchMcpSourceTools(sourceId)` (`studio.js:668`); tool list renders as checkbox group with namespaced hint `mcp__cloudflare_api__{tool}` (`mcps-tab.js:283`). **Cross-cut**: operator compares the rendered tool list against what L1's source-edit Refresh shows for the same source — same names, same count, same ordering. Any drift is L3 anomaly.
Vibing prompts: Loading indicator clear? Latency from open-to-tool-render acceptable? Tool-name formatting readable? Hint span helpful or noisy at scale (Cloudflare API has many tools)? Cross-cut check: identical to source-edit Refresh view?

**Scenario 4 — Per-tool enable/disable + Save + reload preservation.**
Operator: in cloudflare_api's open details panel, uncheck a tool (creates a denylist entry per `mcps-tab.js:271 — "isAllowlist"` mode detection) → Save → reload → reopen. Then re-check the tool → Save → reload → reopen. Then mark a single tool as the ONLY enabled one (allowlist mode) → Save → reload.
Expected: denylist persists; re-enable persists; allowlist mode (single tool checked) persists. Selector contract per `mcps-tab.js:19 — "[data-mcp-tool-toggle][data-mcp-source]"`. Backend resolution in `MCPToolProvider.get_tools_for_agent` (`_tool_provider.py:183`) applies the override.
Vibing prompts: Mode-switch (denylist ↔ allowlist) discoverable? Is "1 tool enabled" obvious as opposed to "0 tools enabled" (which would be empty allowlist)? Does the UI surface the agent's current mode? Is there bulk-select (select-all / select-none) and is it missed?

**Scenario 5 — Hash-routing deep-link + back-navigation.**
Operator: paste `#studio/agents/{agent-name}/mcps/{cloudflare_api-source-id}` directly into the URL.
Expected: agent-editor opens with MCPs tab pre-selected (`studio.js:118-120 — "tab = 'mcps'"`); cloudflare_api's details panel auto-opens (`mcps-tab.js:138-140 — "if (pendingSourceId === source.id)"`); closing the panel clears the source-id from hash (`mcps-tab.js:172-176 — "if (currentSourceId === source.id) onSelectedSourceChange(null)"`); browser back/forward navigates between deep-link states predictably.
Vibing prompts: Deep-link feels predictable? Closing a panel updates hash visibly? Browser back/forward usable? Does the URL look "shareable" (operator could send to teammate)?

**Scenario 6 — Refresh tools button + Auth-required notice path.**
Operator: click Refresh tools (`mcps-tab.js:206-211 — "Refresh tools"`) on the open cloudflare_api panel — should re-fetch tools list with `forceRefresh: true` (drops `_mcpSourceToolsCache` entry). Then navigate to source-edit page (`#studio/mcp-sources/{cloudflare_api-id}`) and click Reset connection on cloudflare_api → tokens cleared. Navigate back to agent-editor → MCPs tab → reopen cloudflare_api's details panel.
Expected: Refresh tools re-renders without auto-popup. Reset clears tokens server-side. Reopening agent-editor panel shows the inline auth-required notice with link to source settings (`mcps-tab.js:317-329 — "_renderAuthRequiredNotice"`); the notice does NOT auto-trigger an OAuth popup (`mcps-tab.js:22-26` comment confirms agent-editor's no-popup contract).
Vibing prompts: Refresh visual feedback (loading state) clear? Reset effect on agent-editor visible? Inline notice copy operator-readable? Link target navigates correctly to source settings?

### Predicted anomalies (Flight Director's setup hypotheses; not commitments)

Surfaced upfront so the operator's vibing time is spent on *surfacing* rather than *anticipating*. If actually surfaces, triage per §2:

1. **Stale tool cache**: `fetchMcpSourceTools` (`studio.js:668-699`) does NOT consult `source.config["_cache"].tools` populated by L1's source-edit Refresh — it always re-runs `/test/connect`. Every details-open triggers a fresh probe. For OAuth sources Phase 0 fast-paths (cheap), but UX may still feel unnecessarily slow. Triage TBD if surfaces (likely cosmetic).

2. **No "Last updated" indicator** in agent-editor — L1 added a "Last updated" line on the source-edit page next to Refresh/Reset (per A-L1-6). Agent-editor MCPs tab has no equivalent. Operator may want consistency. Triage cosmetic.

3. **No bulk-select** on per-tool toggles — operator may want "select all / select none" for sources with many tools. Cloudflare API has 30+ tools; this is more likely to surface here than on a small fixture. Triage TBD per appetite.

4. **Tool-list drift cross-cut failure** (the cross-cut criterion's reason for existing): if any L1 inline fix mutated source-edit tool-list rendering but agent-editor still uses raw probe response, the two views could diverge. F9's L3 description explicitly calls this out as cross-cut purpose — high-signal if observed.

5. **Hash routing edge cases post-L1 polish**: L1 added new hash-routing behavior in source-edit (e.g., for OAuth callback close). Confirm `studio.js:118 — "tab.indexOf('mcps/')"` deep-link parsing still parses correctly with all the new hash patterns. Likely fine; verify.

6. **F8 A4/A5 carve-out collision (per-agent OAuth re-auth gap)**: cloudflare_api was attached at L3, but if the OAuth refresh-token has expired and Phase B kicks → consent_url popup. Agent-editor surface mustn't auto-open the popup (per `mcps-tab.js:22-26` contract). The existing inline notice IS the carve-out-conformant landing. Per-agent re-auth still deferred per F9 §5.

### Subagent dispatch pattern (F9 §9)

Same as L1 + L2: parent context = vibing + triage; all code-change work via subagent. Each spawn carries:

- bug description + acceptance criterion (re-verify by re-walking Scenario N — operator should see X)
- target file(s) + line ranges using cite-by-symbol + snippet form (e.g., `mcps-tab.js:_renderAuthRequiredNotice — "This source needs Test/auth"`)
- §7 architect-pass output if it preceded the fix
- noted §2 LOC budget — L3 should stay ~0 LOC outside the seven vibing-surface UI files

Returns structured summary: file paths + brief description + LOC count + any flagged questions or follow-ups.

## Edge Cases

- **Token expiry mid-leg**: cloudflare_api's refresh-token may expire during L3. Agent-editor probe surfaces AuthRequired inline notice. Operator re-Tests on source-edit page (already polished by L1) → returns to agent-editor → re-opens panel. Not a defect; expected lifecycle. Caplog should remain clean across the recovery.
- **Cloudflare service hiccup**: if cloudflare_api server is unreachable during L3, probe fails → structured error in details panel (`mcps-tab.js:233-238 — "mcp-tools-error"`). Triage as external noise, not L3 defect.
- **No-auth source path (cloudflare_docs)**: optional secondary coverage. If operator chooses to attach cloudflare_docs alongside or instead of cloudflare_api, the probe path should fast-path on `_cache.auth_posture: "no_auth"` (set by L1 Shape C). No OAuth flow; tools render directly. Useful for confirming Shape C's hint propagation reaches the attach path.
- **Multi-source attach in single agent**: optional — L3 can attach BOTH cloudflare_api + cloudflare_docs to the same agent. Exercises multi-source on HTTP only (mixed-transport multi-source is L7's job). Per operator appetite.
- **Empty allowlist (0 tools enabled)**: if operator unchecks ALL tools in allowlist mode, the resolver should return zero tools for that source → agent has no MCP tools attached for that source. Verify `_tool_provider.py:183 — "get_tools_for_agent"` handles this without erroring. Edge but possible if operator vibes "what if I disable them all?"
- **`mcp_overrides` schema with stale source name**: if operator renames a source after attaching it (unlikely in L3 since sources are L1-pinned), the per-source overrides keyed by name would orphan. `_tool_provider.py:153 — "_warn_orphan_overrides"` already logs WARNING for this case. Document if surfaces; F8 carve-out.

## Files Affected (likely)

Read-only on most files; vibing surfaces are bolded. Actual files depend on what surfaces.

**Vibing-surface UI files (excluded from F9 §2 cumulative LOC ceiling):**
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` — primary L3 vibing surface
- `the_one/interfaces/web/static/js/areas/studio.js` — `fetchMcpSourceTools` + hash-routing
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — MCPs tab integration
- `the_one/interfaces/web/static/css/` (any studio CSS) — polish

**Backend / non-vibing files (changes here count toward §2 ceiling):**
- `the_one/interfaces/web/api.py:1144 — "test_mcp_connection"` — only if cross-cut anomaly forces a backend change (rare; L3 should be UI-only)
- `the_one/mcp/_tool_provider.py:183 — "get_tools_for_agent"` — only if `mcp_overrides` resolution surfaces an anomaly (architect pass per §7 required)

**Test baseline:**
- `tests/browser/test_studio_mcps_tab.py` (393 LOC, 7 tests) — must remain UNMODIFIED unless inline fix structurally changes the surface

## Citation Audit

26 citations verified against current code at leg design time:

- `mcps-tab.js:18-19 — selector contracts comment`  ✓ verified
- `mcps-tab.js:22-26 — agent-editor no-popup / credential-override carve-out comment` ✓ verified

- `mcps-tab.js:34 — "function renderMcpsTab"` ✓ verified
- `mcps-tab.js:71-78 — empty-state` ✓ verified
- `mcps-tab.js:107-118 — attach toggle render block` ✓ verified
- `mcps-tab.js:127 — transport badge text` ✓ verified
- `mcps-tab.js:138-140 — pendingSourceId auto-open` ✓ verified
- `mcps-tab.js:163 — toggle event listener` ✓ verified
- `mcps-tab.js:172-176 — close clears hash` ✓ verified
- `mcps-tab.js:196 — _populateDetailsBody` ✓ verified
- `mcps-tab.js:206-211 — Refresh tools button` ✓ verified
- `mcps-tab.js:233-238 — mcp-tools-error render` ✓ verified
- `mcps-tab.js:271-272 — isAllowlist mode detection` ✓ verified
- `mcps-tab.js:283 — namespaced hint prefix` ✓ verified
- `mcps-tab.js:317-329 — _renderAuthRequiredNotice` ✓ verified
- `agent-editor.js:98 — agent-tab-mcps` ✓ verified
- `agent-editor.js:153 — App.studio.renderMcpsTab` ✓ verified
- `studio.js:118 — tab.indexOf('mcps/')` ✓ verified
- `studio.js:668 — fetchMcpSourceTools` ✓ verified
- `api.py:1144 — @router.post("/mcp-sources/{source_id}/test/connect")` ✓ verified
- `api.py:1145 — async def test_mcp_connection` ✓ verified
- `_tool_provider.py:175 — class MCPToolProvider` ✓ verified
- `_tool_provider.py:183 — async def get_tools_for_agent` ✓ verified
- `_tool_provider.py:153 — _warn_orphan_overrides` ✓ verified
- `tests/browser/test_studio_mcps_tab.py` 393 LOC, 7 tests ✓ verified
