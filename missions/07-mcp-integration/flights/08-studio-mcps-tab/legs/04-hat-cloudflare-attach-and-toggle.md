# Leg: 04-hat-cloudflare-attach-and-toggle

**Status**: completed
**Flight**: [Studio MCPs tab + inspector polish](../flight.md)

## Objective

Binding Tier-2 HAT against the live Cloudflare API MCP server. Operator drives the procedure through the dev container's web UI; Flight Director (Claude) guides one step at a time and inline-fixes any defects discovered along the way.

## Context

- Per Flight Design Decision §6, F8 introduces material new operator-facing surfaces (the agent-editor MCPs tab, per-tool toggling, credential override save flow) — without HAT, "agent registry contains exactly the enabled tools" has no live verification. The empirical pattern from F4/F5/F6/F6.5/F6.6 (4+ invisible-to-unit-tests bugs caught by HAT in F6.5 alone) makes this binding for OAuth-touching flights.
- L0-L3 are committed as `74840fa` on branch `flight/08-studio-mcps-tab` with PR #38 open. The dev container is running per `make rebuild` / `docker compose up -d`. Operator's existing `cloudflare_api` MCP source from F6.5 HAT should still work (config: `https://mcp.cloudflare.com/mcp` with persisted DCR credentials).

## Procedure (11 steps)

The Flight Director presents one step at a time; the operator performs the action and reports outcome.

### Pre-flight

- [ ] Dev container running on `http://localhost:8484`; web UI loads.
- [ ] An existing `cloudflare_api` MCP source (or one is freshly registered) — URL `https://mcp.cloudflare.com/mcp`.
- [ ] An existing test agent (e.g. `hat_cloudflare_api`) or one created during the procedure.

### Steps

1. **Test connection on the source-edit page.** Operator: navigate to Studio → MCP Sources → `cloudflare_api` → Edit. Click "Test connection". If OAuth consent flow fires, complete it in the popup; click Test connection again. Verify the Tools section renders: capability flags one-liner ("Server supports: tools, …") AND each tool has a collapsible "Input schema" nested `<details>`.

2. **Open the agent editor.** Operator: navigate to Studio → Agents → `hat_cloudflare_api` (or create a new agent if needed). Switch to the MCPs tab.

3. **Verify empty-state semantics.** If the agent has no MCP sources attached, verify the chip-list renders all available sources (Cloudflare API source's chip should be present, transport badge `streamable-http`).

4. **Attach the Cloudflare source.** Operator: click the `cloudflare_api` chip. Verify the chip becomes visually `attached` AND the per-attachment editor opens. The URL hash updates to `#studio/agents/hat_cloudflare_api/mcps/{cloudflare-source-uuid}`.

5. **Inspect the per-attachment editor.** Verify the Tools section populates with checkboxes (one per Cloudflare tool). Each checkbox is checked by default (denylist mode). The Override credentials section renders streamable-http fields (`bearer_token`, `headers`).

6. **Toggle 2-3 tools off.** Operator: pick 2-3 tools to disable (uncheck their boxes). Click Save.

7. **Reload preserves the toggles.** Operator: reload the agent editor (refresh page or navigate away + back). Verify the same boxes are unchecked.

8. **Cycle credential override with `__MASKED__` round-trip.** Operator: in the Override credentials section, type a `bearer_token` value (any string — won't be used since OAuth tokens cover the Cloudflare flow). Click Save. Reload. Verify the `bearer_token` field shows `__MASKED__`. Click Save again WITHOUT retyping. Reload. Verify the value is preserved.

9. **Trigger an agent build (start a chat session).** Operator: navigate to Chat → start a new session with `hat_cloudflare_api` as the agent. Open browser DevTools → Network → WebSocket. Watch the `tool_call` event payload's `available_tools` field. Verify it contains ONLY the enabled tools' prefixed names (e.g. `mcp__cloudflare_api__list_zones`); the disabled tools are absent.

10. **Run a chat tool call against an enabled tool.** Operator: send a chat message that triggers one of the enabled tools (e.g. "list my Cloudflare zones"). Verify the tool call succeeds and the result renders in chat.

11. **Confirm disabled tool absence.** Operator: from the same `available_tools` payload in step 9, verify the disabled tools' prefixed names are NOT in the list. (No separate chat call needed.)

### Caplog gate

Throughout the HAT, monitor `docker compose logs -f the-one` for `MCPClient.disconnect` warnings — count must remain at 0 (matches the F6.6 baseline). Surface any to the Flight Director for diagnosis.

## Acceptance Criteria

- [ ] All 11 steps pass.
- [ ] Caplog `MCPClient.disconnect` warnings = 0.
- [ ] Any inline fixes during HAT are captured in the flight log under "Anomalies" with severity classification (blocking / degraded / cosmetic) and resolution.

## Files Affected

- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight-log.md` — append L4 progress entry + any anomalies.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight.md` — check off L4; flight status `in-flight` → `landed`.
- `missions/07-mcp-integration/mission.md` — check off Flight 8 in the Flights list.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/legs/04-hat-cloudflare-attach-and-toggle.md` — leg status `ready` → `completed`.

## Citation Audit

- Flight Design Decision §6 (binding HAT) — verified by reading the parent flight artifact.
- F6.5 HAT precedent (4 bugs caught) — confirmed in flight history.
- F6.6 caplog baseline (0 disconnect warnings) — confirmed via flight log carry-forward.
