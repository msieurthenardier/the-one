# Leg: hat-alignment

**Status**: completed
**Flight**: [Discord Client](../flight.md)

## Objective

Guided human acceptance test of the paths only a human Discord account can exercise — DM admission silence, pairing-code enrollment, the DM round-trip (DD-10's PeerTarget branch live), the private operator console against live DM traffic, and daily-driver alignment — with inline fixes per the HAT fix-vs-feature gate.

## Context

- Interactive leg: the operator performs each step from their own Discord account against the dev instance (port 8485, scratch data dir; GleepGlorp connected to the `the-one HAT` guild). The Flight Director drives the app side, mints codes/handoffs, and verifies state.
- Covers the mission criterion half the behavior test could not (bots cannot DM bots): DM + pairing observed live from a human account.
- Cross-state rule (flight-skill HAT guidance): at least one step verifies a surface the operator is NOT looking at (their Discord DM while acting in the browser, and vice versa).
- Fix-vs-feature gate: look-and-feel FIXES ride the inline protocol; anything adding behavior gets a scoped design review first. Contract-pinned surfaces (behavior specs, ids/routes/shapes) change only by deliberate re-author.

## Verification Steps (operator-performed, one at a time)

1. **Unadmitted-DM silence**: operator DMs GleepGlorp a plain message from their human account (not on the allowlist) → total silence: no reply in Discord, no new session, nothing persisted.
2. **Pairing enrollment**: FD mints a pairing code (`POST /api/connectors/{id}/pairing-code`, 10-min TTL); operator DMs the code → allowlist gains the operator's user id; no reply content beyond the enrollment (per DD-3: code consumption persists the append and nothing else).
3. **DM round-trip**: operator DMs a question → agent's reply arrives IN THE DM (DD-10 auto-reply via PeerTarget); app shows a DM-keyed session with peer attribution.
4. **Private console (cross-state)**: FD/operator types an operator note into that DM session in the Chat UI → operator confirms NOTHING arrives in their Discord DM; the note renders operator-side only.
5. **Operator-instructed DM send**: in the DM session via Chat UI: "send me the word 'lighthouse' using your send tool" → arrives in the operator's Discord DM (DD-11 PeerTarget default).
6. **Daily-driver alignment (open)**: operator exercises whatever daily-driver concerns they have (channel behavior from their human account, `/new`, Studio ergonomics, doctor states); findings triaged via the fix-vs-feature gate.

## Acceptance

- [x] Steps 1–5 verified live by the operator
- [x] Step 6 concluded with the operator satisfied (fixes applied inline or triaged)
- [x] Any inline fixes reviewed per the HAT protocol and committed
- [x] Flight log records each step's outcome

---

## Post-Completion

FD updates this leg to `completed`, flight status to `landed`, checks off the flight in mission.md, marks PR #187 ready for review, and signals `[COMPLETE:flight]`.
