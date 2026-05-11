# Leg: 04-tier2-hat-cloudflare (HAT)

**Status**: landed
**Flight**: [OAuth simplification + Test connection button](../flight.md)

## Objective

Replace `tests/HAT.md` Tier-2 procedure (currently GitHub manual-entry path, deleted by L0+L1) with an end-to-end Cloudflare API MCP procedure that exercises F6.5's full happy path — Test connection button → DCR-supporting AS consent → tools list → agent build → chat tool call. **Binding go/no-go** for flight close per Design Decision §4: flight cannot transition to `landed` without a PASS.

## Context

L0 + L1 + L2 + L3 landed (commit `b12bfed4`). The Test button works against in-repo OAuth fixtures (verified by unit + browser tests in L3) but the binding contract per Design Decision §4 is live verification against a real DCR-supporting OAuth-protected MCP server. The mission entry's "real-target HAT is binding go/no-go for spec-compliance claims" rationale (F6 debrief recommendation #5) carries forward.

This leg is INTERACTIVE — the Flight Director guides the operator through verification steps one at a time. No autonomous Developer for verification, but a Developer may be spawned inline if a step surfaces a code-fix-needed issue.

## Inputs

What exists before this leg runs:

- Branch `flight/6_5-oauth-simplification` with L0-L3 committed at `b12bfed4`; PR #36 open as draft
- Dev container running at `http://localhost:8484` (verified `docker compose ps`)
- `tests/HAT.md` Tier-2 section at lines 231-260 (GitHub manual-entry procedure — to be REPLACED, not appended)
- Operator-side prerequisite: a Cloudflare account (free-tier acceptable). The HAT doc must call this out as a gate.

## Outputs

What exists after this leg completes:

- `tests/HAT.md` Tier-2 section replaced with the Cloudflare API MCP procedure (7 verification steps + automated cleanup)
- Flight log L4 entry recording date + caplog count + any anomalies
- Flight status updated to `landed`; mission.md flight 6.5 checkbox ticked
- PR #36 marked ready-for-review
- Optionally a fixup commit on the same branch if any code changes were needed during HAT (e.g. fixing a bug surfaced by live testing)

## Acceptance Criteria

- [ ] `tests/HAT.md` Tier-2 references Cloudflare API MCP procedure (no remaining references to `https://api.githubcopilot.com/mcp/`, GitHub OAuth manual-entry, `auth_endpoint`/`token_endpoint` paste fields)
- [ ] All 7 verification steps below executed by the operator with PASS results
- [ ] Cleanup step deletes the test source and agent
- [ ] Caplog `MCPClient.disconnect` warning count remains 0 (carry-forward from F6 Tier-1 HAT)
- [ ] Flight log L4 entry records: date, operator's Cloudflare account status, caplog count, any anomalies
- [ ] Mission.md flight 6.5 checkbox ticked

## Verification Steps (interactive)

The Flight Director presents these one at a time. The operator performs each and reports back. The Flight Director records outcomes in the flight log and proceeds to the next step on PASS.

### Pre-flight

- [ ] Operator has a Cloudflare account (free-tier acceptable). If not available, abort the leg per flight Design Decision §4 (HAT is binding; cannot ship without it).
- [ ] Dev container is up at `http://localhost:8484` (Flight Director verifies via `docker compose ps`).
- [ ] Operator's browser allows popups for `localhost:8484`.

### Step 1 — Register source

In Studio, navigate to `#studio/mcp-sources/new`. Fill:
- name: `cloudflare_api`
- type: `streamable-http`
- url: `https://mcp.cloudflare.com/mcp`

Click Save. Verify: editor transitions to edit-mode (Test connection section appears below the form).

### Step 2 — First Test connection click

Click the Test connection button. Verify within 15 seconds:
- Result panel shows "Opening consent popup..."
- A popup window opens at the Cloudflare consent URL
- Test button is disabled while the popup is open

Report the consent URL (the popup's location bar) so the Flight Director can confirm it's a Cloudflare AS URL (not localhost, not the source URL itself).

### Step 3 — Cloudflare consent

Complete Cloudflare consent in the popup (login + authorize the-one's OAuth app registration). Verify:
- Popup redirects to `http://127.0.0.1:8484/api/oauth/callback?code=...&state=...`
- Popup body renders "Login successful"
- Operator closes the popup tab

### Step 4 — Auto re-test

Within ~500ms of popup close, the UI auto-runs the Test connection re-POST. Verify:
- Result panel updates to "Connected. Tools (N): ..." with N > 0
- The tool list includes Cloudflare-API tools (e.g. `accounts_list`, `zones_list`, or similar — exact list depends on Cloudflare's MCP server scope at HAT time)
- Test button re-enabled

### Step 5 — Agent build

Navigate to `#studio/agents/new`. Create agent `hat_cloudflare_api`:
- Pick any LLM provider already configured in the dev environment
- In MCPs tab, attach `cloudflare_api`
- Save

Verify the agent build succeeds (no error toast, agent appears in agent grid).

### Step 6 — Chat tool call

Open chat with `hat_cloudflare_api`. Send: *"List my Cloudflare accounts using your MCP tool."*

Verify:
- Agent dispatches a `mcp__cloudflare_api__*` tool (exact name varies — `accounts_list` is most likely)
- Tool result lands in chat as a non-empty list of accounts
- No "Login required" button appears (tokens already valid from Step 3-4)

### Step 7 — Cleanup

Delete the test source and agent:
```bash
# From host:
curl -X DELETE http://localhost:8484/api/agents/hat_cloudflare_api
curl -X DELETE http://localhost:8484/api/mcp-sources/<source_id>
```

(`<source_id>` is the id from Step 1; the operator can read it from the Studio MCP Servers list URL.)

Verify both DELETEs return 204 No Content; the agent grid and MCP sources list both refresh empty (or back to pre-HAT state).

### Caplog gate

After Step 7, check the dev container logs for `MCPClient.disconnect` warnings:
```bash
docker compose logs the-one --since 30m | grep -i "transport close failed\|disconnect" | wc -l
```

Expected: 0 occurrences (mirrors F6 Tier-1 HAT contract).

## Pass Criteria

ALL of the following must hold:
- All 7 steps complete successfully
- Cleanup succeeds
- Caplog warning count = 0
- No new bugs surfaced that needed code fixes (if a fix was needed inline, document in flight log Anomalies)

## Files Affected

- `tests/HAT.md` — REPLACE Tier-2 section (lines ~231-260) with Cloudflare API MCP procedure
- `missions/07-mcp-integration/flights/06_5-oauth-simplification/flight-log.md` — append L4 entry under Leg Progress
- `missions/07-mcp-integration/flights/06_5-oauth-simplification/flight.md` — set status to `landed`, check off L4 leg checkbox
- `missions/07-mcp-integration/mission.md` — check off flight 6.5 checkbox

---

## Post-Completion Checklist

- [ ] All 7 verification steps + cleanup PASS
- [ ] Caplog count = 0
- [ ] HAT.md Tier-2 updated with Cloudflare procedure
- [ ] Flight log L4 entry recorded
- [ ] Leg status: `landed`
- [ ] Flight status: `landed`
- [ ] Mission.md flight 6.5 checkbox ticked
- [ ] Commit the HAT.md update + flight artifacts as a fixup on the same branch
- [ ] PR #36 marked ready-for-review

## Citation Audit

5 citations verified at leg design time (2026-05-08):
- `tests/HAT.md:231-260` (Tier-2 section to replace) — OK
- Existing `/api/mcp-sources/{id}/test/connect` endpoint (per L3 commit b12bfed4) — OK
- `https://mcp.cloudflare.com/mcp` (per F6 close verification: 0.4s response time, DCR-supporting per flight Design Decision §2) — assumed live; operator verifies at HAT time
- F6 Tier-1 HAT caplog gate at `tests/HAT.md:184` (carry-forward) — OK
- Mission known-issue at `mission.md:104` (already retired at F6 Tier-1 HAT close) — informational
