# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Connector UX Cleanup](../flight.md)

## Objective

Operator-driven HAT walking the cumulative L1-L5 result. Operator clicks through the new-connector flow, the Discord connector editor (both tabs), the Stub connector editor (both tabs), and the agent Connectors tab. Agent guides verification steps one at a time. Small-tweak fixes during HAT land as inline commits on this branch. Final operator-confirmed pass closes the leg.

## Context

- F5 L6 is the final leg per the flight's "primitives-first → section-shape → sweep last → HAT" sequencing. L1-L5 landed at commit `e02b368` (PR #73 draft). 89/89 browser tests pass.
- Operator directive: "for the last hat, I will do the clicking around myself." Chrome MCP automation NOT used; operator drives their own browser. Agent guides steps + processes outcomes.
- Adaptation Criteria from F5 flight: HAT-discovered UX issues → fold into F5 OR escalate as Known UX Gap with near-term path — NOT defer.

## Verification Steps

Run interactively. Flight Director presents each step; operator performs in browser; reports PASS or FAIL. Failures trigger diagnose + fix + re-verify before moving on.

1. **New container start** (optional; only if operator wants a fully cold environment): `make restart` to bust pool + bust JS cache.

2. **New connector page** — `http://localhost:8484/#studio/connectors/new`:
   - L1 styled: Type dropdown looks dark-theme styled; Auto-relay row is an iOS toggle (track + ball), NOT a raw checkbox.
   - L1 Type-placeholder: open Type dropdown → "Select a connector type" placeholder visible. Pick Discord. Re-open → placeholder NOT in list (only Discord).
   - L3 styled: Auto-relay label reads "Auto-reply to platform messages" (rewritten); has an info-icon next to it; hovering shows the rewritten tooltip text. Other Lifecycle rows (Pool idle timeout, Chat-session continuation) also have info-icons.
   - L3 create-mode preservation: after picking Discord, Intents/Servers/Presence/Advanced should still render in Connection section (create-mode has no tabs).
   - PASS/FAIL.

3. **Edit Discord Constellation General tab** — `http://localhost:8484/#studio/connectors/58f1fe5a833f`:
   - L1 styled: form controls dark-theme styled throughout.
   - L2 placement: Test Connection button + LED + Invite URL block live INSIDE the Connection section (no standalone `// TEST CONNECTION` or `// INVITE` headers further down the page).
   - L3 absence: NO Intents/Servers/Presence/Advanced anywhere on General tab.
   - General-tab sections appear in order: Connection (with Test Connection + Invite folded in) → Credentials → Pairing → System Prompt Directive → Attached Agents → Danger Zone.
   - PASS/FAIL.

4. **Edit Discord Constellation Access and Routing tab**:
   - L3 placement: tab order is Lifecycle → **Runtime Config** (with Intents + Servers + Presence + Advanced) → Account-scope allowlist → Routing rules.
   - L3 styled: Intent checkboxes use `.checkbox-primary` (purple-accent borders, NOT raw browser grey).
   - L3 labels: "Servers" (not "Guilds"); info-icons on Intents/Servers/Presence with hover tooltips.
   - L4 containment: per-axis bodies (Users/Channels/Servers/Roles allowlist) have visual containment (border-left + padding + elevated surface) when expanded.
   - L4 hide-empty: empty Selected entries containers are NOT visible (no blank box below the dropdown input).
   - PASS/FAIL.

5. **Edit Stub HAT Account** — navigate to the Stub account (find via `http://localhost:8484/#studio/connectors`):
   - General tab: Connection section contains Name + Type + Test Connection + Invite (no Invite if Stub has no `renderInviteSection` — that's correct; no error). Credentials section shows the Stub-specific config-kv.
   - A&R tab: Lifecycle + Account-scope allowlist + Routing rules ONLY. **NO Runtime Config section** (Stub doesn't implement the hook — correct).
   - PASS/FAIL.

6. **Cave Man Bot Connectors tab** — `http://localhost:8484/#studio/agents/Cave%20Man%20Bot/connectors`:
   - L4 containment: expand Discord Constellation Peers axis → visual containment apparent on the expanded body. Expand Channels axis → containment + the friendly-label `#gleepglorp-text` chip (from F4) visible.
   - L4 hide-empty: expand Stub HAT Account's Peers axis → if no chips selected, the Selected entries container is hidden (no blank box).
   - PASS/FAIL.

7. **A1 + L4 fold-in still works** (regression check):
   - Restart container (if not already done in step 1).
   - Open Discord Constellation editor → Access and Routing tab. Allowlist dropdowns show pre-probe hint OR cached entities (depending on lifespan-warmup timing).
   - Click Test Connection (on General tab). After success, the A&R dropdowns auto-refresh without page reload (the F4 L4 `connector-account-pool-warmed` event listener fires).
   - PASS/FAIL.

8. **Operator-confirmed cumulative pass**: any final UX issues to surface as Known UX Gaps for F5 debrief, OR fold-in fix candidates for this commit?

## Files Affected (if any inline fixes)

- Per any fix that surfaces during HAT (TBD; expected zero).
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight.md` — L6 checked off; flight status `in-flight` → `landed`.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight-log.md` — L6 leg-progress entry with per-step outcomes.
- `missions/11-discord-connector-depth/mission.md` — F5 checked off in Flights list.
- This leg artifact's status → `completed`.

## Post-Completion Checklist

- [x] All 7 verification steps PASS (with any inline fixes committed on this branch).
- [ ] Update `flight-log.md` with L6 leg-progress entry capturing per-step outcomes.
- [ ] Set this leg's status to `completed`.
- [ ] Check off L6 in `flight.md` (Checkpoints + Legs sections).
- [ ] Update `flight.md` status `in-flight` → `landed`.
- [ ] Check off F5 in `missions/11-discord-connector-depth/mission.md`.
- [ ] Commit the artifact updates with a message describing HAT outcome.
- [ ] Push the branch; mark draft PR #73 ready for review.
- [ ] Signal `[COMPLETE:flight]`.
