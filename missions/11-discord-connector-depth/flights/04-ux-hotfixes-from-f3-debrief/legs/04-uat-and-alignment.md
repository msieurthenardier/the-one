# Leg: uat-and-alignment

**Status**: completed
**Flight**: [UX Hotfixes from F3 Debrief](../flight.md)

## Objective

HAT smoke-verify A1 + A2 against the live gleepglorp test bot via a Chrome-MCP-driven walk. Confirm operator-visible outcomes match the L2 + L3 design contracts: Test Connection click warms the pool so the cold-restart dropdown 404 cleared without page reload (A1); the per-agent overlay's checkbox-mode resolves Discord snowflakes to friendly labels for Discord accounts and falls back to raw-ids for stub accounts (A2 + regression contract).

## Context

- F4 flight.md "L4 HAT scope — A1 + A2 only; defer F3-deferred stale-entry to F9" operator decision pins this leg's coverage: A1 + A2 walkable against gleepglorp with Chrome MCP and no operator-side Discord actions (no kicks, no role rotations). F3 L7 step 8 (stale-entry indicator) stays deferred to F9.
- This leg is the operator-driven HAT phase per the agentic-workflow interactive-leg protocol: the Flight Director guides the operator through verification steps one at a time; the operator performs each step and reports results; failures trigger inline fix-and-re-verify (spawning a Developer if code changes are needed).
- Adaptation Criteria from F4 flight.md: if NEW UX issues surface during this HAT, fold them into F4 OR escalate as Known UX Gap with a near-term path — NOT another F8/F10 deferral. This is the operator-requested discipline change to arrest UX-debt accumulation.
- The 6 verification steps below are verbatim from the L4 entry in F4 flight.md's Legs section (operator-locked at planning + cycle-1 architect review).

## Inputs

- L1 + L2 + L3 committed at `4973384` (autonomous batch) on branch `flight/04-ux-hotfixes-from-f3-debrief`.
- Draft PR #72 open at https://github.com/msieurthenardier/the-one/pull/72.
- gleepglorp Discord test bot reachable (same prereq as F3 L7).
- `chrome-devtools` MCP available for the walk.
- The operator is logged into Discord in the browser session the agent drives.
- A "Cave Man Bot" agent attached to the Discord Constellation connector account exists (F3 L7 precedent).
- A Stub HAT Account-attached agent with non-empty per-axis checkbox-mode chips exists for the regression-contract step.

## Outputs

- HAT-validated A1: Test Connection click warms the pool; dropdowns populate without page reload; `details.pool_warmed: true` visible in the response envelope.
- HAT-validated A2: per-agent overlay checkbox-mode shows friendly labels for Discord (`#gleepglorp-text` etc.); raw-id fallback for stub.
- F4 flight-log L4 leg-progress entry with per-step PASS/FAIL outcomes.
- If any step fails: a Known UX Gap section in F4 flight-debrief listing the issue with a near-term path, OR an inline fix-and-re-verify cycle commit before declaring L4 complete.
- F4 flight.md L4 checkpoint + L4 Legs entry checked off; flight status `in-flight` → `landed`; F4 mission entry checked off in `mission.md`.

## Acceptance Criteria

- [x] Step 1 (cold-pool setup): `the-one` container restarted; the pool is empty (`_pool == {}` per the L2 test idiom; no need for a separate test-only API since idle TTL is 30 min and restart is the operational cold path).
- [x] Step 2 (pre-probe hint): with cold pool, navigating to Discord Constellation editor → Access and Routing tab shows dropdowns rendering the pre-probe hint "Run Test Connection first…" (F1 L5 + F3 L4 contract).
- [x] Step 3 (A1 closure): clicking Test Connection succeeds (green LED + success message); the dropdowns repopulate from the warmed pool WITHOUT a page reload (the dropdown's GET fires from the dropdown re-mount and now returns 200 with entities).
- [x] Step 4 (envelope inspection): the Test Connection POST response (visible in browser devtools network panel) contains `details.pool_warmed: true` and `details.pool_warm_error: null` per the L2 envelope contract.
- [x] Step 5 (A2 closure for Discord): navigating to Cave Man Bot → Connectors tab → expanding the Discord Constellation Channels checkbox-mode section, the checkbox-rows display friendly labels (`#gleepglorp-text` etc.) instead of raw Discord snowflakes (`1506831630923333722` etc.). The label resolution is observable on first expand (lazy fetch fires); collapse-and-re-expand still shows the friendly labels (cache reused).
- [x] Step 6 (regression contract for stub): navigating to a Stub HAT Account-attached agent → expanding a per-axis checkbox section, the checkbox-rows display the raw account-scope strings (no label resolution; stub plugin lacks the `enumerate_discoverable_entities` hook so the L4 GET returns 503; raw-id fallback path renders correctly).
- [x] Any NEW UX issues surfaced during the walk are either folded into F4 (a follow-up commit on this branch with a Developer fix + re-verify) OR escalated as a Known UX Gap in F4 flight-debrief with a near-term path — NOT deferred to F8/F10.

## Verification Steps

Run interactively. The Flight Director presents each step one-at-a-time; operator performs the step in the browser/terminal and reports PASS or FAIL. Failures trigger diagnose+fix+re-verify before moving on.

1. **Restart the-one container** for cold-pool setup.
   - Operator: run `make restart` (or equivalent) and confirm the container is back up.
   - Expected: container restarted; pool is empty (no warm entries).
   - PASS criterion: operator reports "container restarted, app accessible at http://localhost:8000".

2. **Open Discord Constellation editor; observe pre-probe hint.**
   - Operator: navigate to `#studio/connectors/{discord-constellation-account-id}` → Access and Routing tab.
   - Expected: dropdowns on the page render with the pre-probe hint "Run Test Connection first…" (or similar).
   - PASS criterion: operator reports the dropdowns show the hint text and no entity entries are listed.
   - FAIL handling: if dropdowns show entities (pool somehow warm), restart the container again; if the hint never shows, escalate.

3. **Click Test Connection; verify dropdowns populate without page reload (A1).**
   - Operator: with browser devtools network panel open, click the Test Connection button.
   - Expected: green LED + success message; within ~1 second the dropdowns repopulate with Discord entities (channel names, usernames, etc.) WITHOUT a page reload.
   - PASS criterion: operator reports green LED + dropdowns now showing real entities + no page reload occurred.
   - FAIL handling: if dropdowns still show pre-probe hint, A1 is broken — diagnose (check api.py warmup block; check for exception in console).

4. **Inspect Test Connection response envelope (A1 confirmation).**
   - Operator: in browser devtools network panel, click the most recent POST request to `/api/connector-accounts/{id}/test/connect` and view the response body.
   - Expected: response JSON contains `details.pool_warmed: true` AND `details.pool_warm_error: null` (plus the doctor's status="ok" + message).
   - PASS criterion: operator reports both fields present with the expected values.
   - FAIL handling: if `pool_warmed: false`, the warmup attempt failed — `pool_warm_error` will contain the reason; surface to fix path.

5. **Navigate to Cave Man Bot Connectors tab; verify A2 closure for Discord.**
   - Operator: navigate to `#studio/agents/cave-man-bot` → Connectors tab → expand the Discord Constellation tile's Channels axis (the one with the chevron toggle).
   - Expected: each checkbox-row displays a friendly Discord label (e.g., `#gleepglorp-text` instead of `1506831630923333722`).
   - PASS criterion: operator reports the friendly labels are visible.
   - Optional sub-step: collapse and re-expand the axis; confirm labels are still friendly (cache reused; no flicker to raw-IDs).
   - FAIL handling: if raw IDs are still shown, check console for fetch errors; verify the L4 GET returns 200 in the network panel.

6. **Navigate to Stub HAT Account-attached agent; verify regression contract for stub (A2 fallback).**
   - Operator: navigate to `#studio/agents/{stub-attached-agent-name}` → Connectors tab → expand the stub-attached tile's checkbox-mode axis.
   - Expected: each checkbox-row displays the raw account-scope string (no label resolution — stub plugin returns 503 from the L4 GET; raw-id fallback path holds).
   - PASS criterion: operator reports raw-string display (regression held).
   - FAIL handling: if labels are somehow resolved on stub, the 503 fallback is broken — diagnose.

## Implementation Guidance

This is an interactive HAT leg — there is no code implementation. The Flight Director:

1. Presents step 1; waits for operator PASS/FAIL.
2. On PASS, presents step 2; on FAIL, diagnoses with operator and either fixes inline (spawn Developer for code change → commit fix on same branch → re-verify the failed step) or escalates as a Known UX Gap in F4 flight-debrief.
3. Repeats for steps 3 through 6.
4. On all-PASS: updates F4 flight-log L4 entry with per-step outcomes; sets leg status to `landed`; checks off L4 in F4 flight.md (Checkpoints + Legs); transitions F4 flight status to `landed`; checks off F4 entry in `mission.md`; commits the artifact updates; pushes; marks PR #72 ready for review.

## Edge Cases

- **gleepglorp unreachable**: operator-side prereq; if the bot is offline, abort the HAT and reschedule once gleepglorp is back. Not a code issue.
- **Browser session lost mid-walk**: re-open browser; restart from step 1 (cold pool may have warmed via background lifespan; verify by re-checking step 2's pre-probe hint).
- **Operator discovers an unrelated UX issue mid-walk**: capture in F4 flight-debrief Known UX Gaps subsection per the adaptation criteria; do not fold into L4 unless it blocks an L4 step.
- **A1 partial-failure** (doctor OK, warmup fails): envelope shows `pool_warmed: false` + `pool_warm_error: "<reason>"`; the operator sees the dropdowns NOT populate. This is correct behavior per L2 design (warmup is best-effort; doctor verdict preserved). The HAT records this as a HAT-step PASS (the contract held) but a UX gap may need follow-up depending on the failure reason. Surface to operator decision.

## Files Affected

- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight.md` — L4 checkpoint + L4 Legs entry checked off; flight status `in-flight` → `landed`.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight-log.md` — L4 leg-progress entry with per-step outcomes.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/04-uat-and-alignment.md` — this artifact's status header progressed through the lifecycle.
- `missions/11-discord-connector-depth/mission.md` — F4 checked off in the Flights list.
- If a step fails and triggers an inline fix, that fix's files are scoped per the fix.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All 6 verification steps PASS (with one inline fold-in fix committed in the L4 commit: cross-component pool-warmed event so dropdowns auto-refresh after Test Connection).
- [x] Update `flight-log.md` with L4 leg-progress entry capturing per-step outcomes.
- [x] Set this leg's status to `completed` (HAT is operator-judged; no separate code review gate after PASS).
- [x] Check off L4 in `flight.md` (Checkpoints + Legs sections).
- [x] Update `flight.md` status `in-flight` → `landed`.
- [x] Check off F4 in `missions/11-discord-connector-depth/mission.md`.
- [x] Commit the artifact updates with a message describing HAT outcome.
- [x] Push the branch; mark draft PR #72 ready for review.
- [x] Signal `[COMPLETE:flight]`.
