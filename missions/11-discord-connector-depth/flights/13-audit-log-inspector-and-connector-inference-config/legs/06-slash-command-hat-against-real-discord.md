# Leg: slash-command-hat-against-real-discord

**Status**: completed
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](../flight.md)

## Objective

Verify all 6 platform-side slash commands (`/agents`, `/talk_to`, `/whoami`, `/new`, `/reset`, `/help`) behave correctly when invoked from a real Discord client against the operator's live the-one bot. Verify-only per operator decision at flight planning — no ephemeral-response cleanup, no Discord-native autocomplete; all commands stay channel-visible (current F8 L9 behavior). M11 criterion #10 transitions from `[ ]` → `[~]` (partial) at flight land; the "ephemeral where appropriate" sub-bullet stays open for a future flight.

## Context

- **Interactive leg** per `/agentic-workflow` HAT-leg convention. NO Developer/Reviewer agents — Flight Director guides the operator through one verification step at a time.
- **Pre-L6 behavior-test gate** is satisfied: both L4 + L5 behavior-test specs PASS on run `2026-05-31-23-56-31` (8/8 + 7/7). The L1-L5 batched commit landed at `20615fc` on the F13 branch and was pushed; draft PR at https://github.com/msieurthenardier/the-one/pull/82.
- **L6 is the final leg of F13**. After L6 lands, flight transitions to `landed` and the mission outline's Flight 13 entry gets checked off.
- **Verify-only scope** per flight planning Design Decision "Slash Verification Is Verify-Only" (operator: "All visible (current behavior)"). Ephemeral cleanup + Discord-native autocomplete polish explicitly deferred to a future flight (likely F14's HAT script flight per the flight outline).

## Inputs

- F13's L1-L5 work is committed and pushed (commit `20615fc`).
- The-one container is running with the L1-L5 code loaded.
- Operator has a real Discord client logged in.
- The-one's Discord bot (connector `58f1fe5a833f` "Discord Constellation") is invited to a Discord guild the operator can post in.
- At least one agent is attached to the Discord connector (verified: 1 agent attached per `/api/connectors/58f1fe5a833f`).
- The operator can DM the bot AND post in at least one channel where the bot has Message Content + Guild Members intents.

## Outputs

After this leg completes:
- A HAT report appended to `flight-log.md` under `## Session Notes` (one section per command — input + expected + actual + verdict).
- Any F13-caused regressions surfaced are fixed inline (commit as needed before the leg lands).
- Any pre-existing anomalies (not F13-caused) are filed as Known Issues in `mission.md` or a follow-up flight's spec.
- Leg artifact + flight.md + mission.md updated to reflect the new state.

## Acceptance Criteria

Each of the 6 commands is invoked from the operator's real Discord client and produces the documented behavior. Per command:

- [~] **AC-1 — `/agents`**: returns the list of agents currently attached to the connector (or the per-(channel, peer) eligible subset post-F7 routing-engine filtering). Visible in the channel (current F8 L9 behavior — not ephemeral). **STATUS: BLOCKED.** Bot processes the command and the dispatcher routes successfully (routing-audit panel logged `disposition: command-intercepted`, `agent: Sonos Agent`), but the command handler's `_permitted_agents` admission re-check fails because of pre-existing `_commands.py` defect (missing kwargs to `admits_inbound`); response is "No agents available for this conversation" for any peer/channel combo. Filed as Known Issue d (the 4-bug ACL/slash-sync cluster).
- [ ] **AC-2 — `/talk_to <agent_name>`**: BLOCKED on same cluster (no agents to select). Not exercised.
- [ ] **AC-3 — `/whoami`**: BLOCKED — not exercised.
- [ ] **AC-4 — `/new`**: BLOCKED — not exercised.
- [ ] **AC-5 — `/reset`**: BLOCKED — not exercised.
- [ ] **AC-6 — `/help`**: BLOCKED — not exercised.

## Verification Steps

Per `/agentic-workflow` interactive-leg protocol, the Flight Director presents one step at a time. The operator performs each in their real Discord client and reports back. For each command:

1. **Operator invokes the command** in a channel where the bot has the required intents.
2. **Operator reports** what they observed (the bot's response text, visible vs ephemeral, any errors, latency).
3. **Flight Director** records the result in the HAT report section of `flight-log.md`. Marks AC `[x]` if it matches the documented behavior; flags any deviation.
4. If a regression is surfaced, the Flight Director investigates inline + fixes (separate commit before leg land).

## Implementation Guidance

NONE — this is verify-only. No code changes are expected. If a regression surfaces during the walk, fix scope is bounded by the F13 Adaptation Criteria for L6:

> "If anomalies surface that are F13-caused (regression vs F12 baseline): fix in-leg (this is acceptance-criteria territory, not divert). If anomalies are pre-existing (carried from F8/F9/F10/F11/F12): file as Known Issue + defer to next slash-touching flight."

## Files Affected

- `missions/11-discord-connector-depth/flights/13-audit-log-inspector-and-connector-inference-config/flight-log.md` — HAT report appended under Session Notes
- `missions/11-discord-connector-depth/flights/13-audit-log-inspector-and-connector-inference-config/flight.md` — leg checked off + L6 land checkpoint ticked + flight status → `landed`
- `missions/11-discord-connector-depth/mission.md` — Flight 13 entry checked off; criterion #10 marked `[~]` (partial); criteria #12, #15 marked `[x]`
- This leg artifact — status → `completed` at commit time
- Possibly source files IF a regression surfaces (operator-confirmed before any source changes)

## Edge Cases

- **Bot offline / Discord-side rate-limited**: pause the walk; operator confirms bot is responsive (e.g. by typing a non-command message and seeing the auto-relay reply if always_listen is on, or by checking `/api/connectors/58f1fe5a833f` is healthy). Resume.
- **`/talk_to` to an unknown agent name**: bot should return a clear "agent not found" or similar denial. Per-(agent, peer) permission gating is the same — denial for an agent the peer isn't allowed to use.
- **Pre-existing F8/F9/F10/F11/F12 anomalies that resurface**: file as Known Issue in mission.md, defer to future flight. Do NOT fix in-leg.

---

## Post-Completion Checklist

- [~] All 6 ACs verified — AC-1 BLOCKED with diagnostic evidence; AC-2..AC-6 not exercised (blocked on the same defect cluster). Leg lands as a HAT report documenting findings rather than a clean PASS.
- [x] Any F13-caused regressions fixed inline — N/A (all 4 surfaced defects are pre-existing per git blame; F13 didn't touch `_commands.py`, `_discord.py`, or `_acl.py` runtime code)
- [x] Any pre-existing anomalies filed as Known Issues in mission.md — single cluster entry "F13 L6 HAT findings — ACL / slash-sync surface cluster (4 bugs, all pre-existing)" enumerates each defect with resolution-path notes
- [x] HAT report appended to flight-log.md Session Notes — narrative of the diagnostic walk (Bug A → restart → Bug B → PUT → Bug C → empty roles → Bug D → `_permitted_agents` git blame) documented
- [x] Leg status → `completed` (this file's header)
- [x] Check off this leg in flight.md `### Legs`
- [~] L6 land checkpoint in flight.md → `[~]` partial (BLOCKED on pre-existing defects, not closed clean)
- [x] Flight.md status → `landed` (F13's autonomous scope is complete; HAT-walkthrough is deferred)
- [x] Mission.md Flight 13 entry checked off (with narrative of what closed + what defers)
- [x] Mission.md criterion #12 + #15 marked `[x]`; #10 stays `[ ]` (BLOCKED on ACL/slash-sync cluster fix in follow-on flight)
- [x] L6 commit lands the HAT report + bookkeeping updates separately from the L1-L5 batch (per Phase 2d)
- [ ] Draft PR (#82) marked ready for review — operator's call; PR ships with L6 bookkeeping but the criterion #10 closure is explicitly deferred
