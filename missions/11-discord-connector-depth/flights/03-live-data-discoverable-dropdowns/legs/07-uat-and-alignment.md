# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Chrome-MCP-driven HAT walk against the gleepglorp test bot validating that the F3 dropdown UX works end-to-end against real Discord traffic. Required per F1 debrief — registry-mediated UI dispatch touched. Interactive leg: the operator drives Discord-side actions; the Flight Director (and a spawned browser-driving agent if the chrome-devtools MCP is available) drives the editor and observes results.

## Context

- L1-L6b are landed and committed (commit `e53f9e1`); F3 batched code-review and accessibility-review both signaled `[HANDOFF:confirmed]`.
- The 10 verification steps are documented in `flight.md`'s L7 Checkpoint and the L7 Legs entry. This artifact is the leg-level scaffold; the actual HAT walk happens interactively at run-time.
- **Driver choice**: Chrome MCP (`chrome-devtools` MCP server) is the preferred driver; per the mission constraints, if Discord's web-client bot-detection makes browser automation unreliable, the HAT may use `discord.py` as a second-bot driver — resolved during the HAT walk if needed.
- **Substrate-contract reversal** per flight Adaptation Criteria: if HAT surfaces a substrate-contract reversal (per `prompt-discipline-needs-mechanical-fallback` codified in F1), pause the flight and trigger fresh design review.

## Prerequisites for the HAT walk

- [ ] gleepglorp test bot reachable from the host (verify with a simple ping or Test Connection from the Studio).
- [ ] Operator is logged into Discord in the browser session the agent will drive (or the operator stands by to log in when prompted).
- [ ] The `the-one` server is running and reachable.
- [ ] The chrome-devtools MCP server is registered and the agent can drive it.
- [ ] If the operator wants screenshot evidence, it must remain gitignored per the user-global "test snapshots not committed" rule.

## Verification Steps

The 10 steps from flight.md's Checkpoint L7, walked one at a time. Each step ends with the operator confirming pass or reporting an anomaly; anomalies trigger inline fix (Developer agent spawn if code changes needed) and re-verification.

1. **Discord Constellation allowlist section renders dropdown components on all 4 axes** — open the gleepglorp connector account editor; navigate to the Allowlist section; verify each axis (peers/channels/guilds/roles) shows a `discoverable-dropdown` component (NOT a chip-list).

2. **Dropdowns populate from the live bot view** — open each axis's dropdown; verify the channel count matches what gleepglorp can see; same for users / guilds / roles.

3. **Typeahead filters work** — type `"test"` (or another known substring) into the channels dropdown input; verify the menu narrows to matching names.

4. **Selecting an entry creates a chip** — click an item in the dropdown menu; verify a chip appears in the selected-values strip; verify the dropdown's `onChange` fired (chip is rendered with the expected label).

5. **Save round-trip persists the selected IDs in `account.config.allowlist`** — click Save; reload the editor; verify the chips still appear AND `account.config.allowlist.{axis}` contains the expected IDs (via direct API GET or the connector account JSON view).

6. **Routing-rules editor's match-value input is now a dropdown of the same data** — navigate to the Routing Rules section; add a new row with scope=`channel`; verify the match-value cell is a dropdown of channels (not free-form text); scope=`peer` → dropdown of peers; scope=`thread` → dropdown of channels (per the L6b thread→channels mapping).

7. **Refresh button forces immediate refresh + repopulates** — modify gleepglorp's discoverable state (e.g., create a new channel via Discord); click the dropdown's Refresh button; verify the new entry appears.

8. **Stale-entry indicator displays after the operator removes a member from the test guild and refreshes** — remove a member (kick or member-leaves) from the test guild via Discord; click Refresh in the peers dropdown; verify the removed member's chip (if currently selected) renders with `data-stale="true"` and strikethrough styling.

9. **Per-agent overlay editor on an attached agent renders dropdowns too** — navigate to Studio → an agent attached to gleepglorp (e.g., Cave Man Bot) → Connectors tab → the gleepglorp tile's expanded body; verify the per-axis overrides render dropdowns (Discord chip-mode path) when account-scope is permissive.

10. **Stub-type account renders the existing chip-lists / free-form text — fallback path intact** — open a stub-type connector account; verify the Allowlist section renders chip-lists (not dropdowns); verify the Routing Rules match-value cells render chip-lists (not dropdowns).

## Acceptance Criteria

- [ ] All 10 verification steps pass with operator confirmation.
- [ ] Any HAT-discovered fixes land in `flight-log.md` under a new `### Anomalies` section + are addressed via Developer agent spawn → re-verify → continue.
- [ ] No substrate-contract reversal surfaces — if one does, pause the flight per Adaptation Criteria.
- [ ] Update `flight.md`'s L7 Checkpoint + L7 Legs entry to checked.
- [ ] Update this leg artifact's status to `completed`.

## Files Affected

- `missions/.../flight.md` — L7 Checkpoint + Legs checked off.
- `missions/.../flight-log.md` — L7 entry + any HAT anomalies + fixes.
- `missions/.../legs/07-uat-and-alignment.md` — this artifact's status.
- If HAT discovers issues requiring code changes: relevant source files + tests. New commits per inline-fix-then-re-verify cycle.

---

## Post-Completion Checklist

- [ ] All 10 verification steps confirmed pass.
- [ ] HAT anomalies (if any) addressed inline, with each fix re-verifying the failing step.
- [ ] Flight log updated with HAT outcomes + any anomalies/fixes.
- [ ] Leg status → `completed`.
- [ ] Flight.md L7 entries checked.
- [ ] Final commit lands all L7-discovered changes + artifact updates.
- [ ] Draft PR opened (or marked ready) post-HAT per Phase 3 of the agentic-workflow.
