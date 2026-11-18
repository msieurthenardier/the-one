# Flight Log: Local-command MCP servers: newest protocol and Forget

**Flight**: [Local-command MCP servers: newest protocol and Forget](flight.md)

## Summary
Ready. Charter agreed, the flight designed, the Architect's design review folded in and the design approved by the operator on 2026-11-18. Execution is next.

---

## Leg Progress

---

## Decisions
Runtime decisions not in original plan.

---

## Deviations
Departures from planned approach.

---

## Anomalies
Unexpected issues encountered.

---

## Session Notes

### 2026-11-18 — planning
- Escalated from squawks 0372 (the Protocol row stays at 2025-11-25) and 0373 (no "Forget tools list" on the operator's server). Both came from the operator's report of 2026-11-17.
- Squawk 0372 was reproduced on a scratch instance with the published `@modelcontextprotocol/server-everything` 2.3.0 run as a local command: started 12 s late it connects on 2025-11-25 with 16 tools, where a prompt start gives 2026-07-28 and 22. The cause is the 10 s deadline of the `server/discover` probe, counted from the spawn.
- Squawk 0373 turned out not to be a defect: the operator's server is a local command, and local-command servers have never had the button (Mission 31 Flight 5, DD6). The operator asked for it.
- Qualified as a sortie: one outcome (local-command servers do not get stuck on an older protocol, by waiting for a slow start and by letting the operator clear what is remembered), one cluster of decisions (how the connect treats a local server that is slow to answer the probe), two build legs and a HAT, no new subsystem. It changes the connect path shared with chats, which is why it is not squawk work.
- Operator decisions, 2026-11-18: the charter as drafted; the editor shows a note when a connection fell back for lack of an answer; the note sits under the facts in the Server section (mockup in the flight artifact); the npx cache behaviour is left out; a short closing HAT.
- Architect design review, one cycle (Opus): approve with changes; one high, six medium and several low issues. Folded into the flight artifact:
  - High: a timeout cannot be told from a server-sent -32001 by its code, and a code-only rule would re-send in a tight loop. "No answer" now also needs the probe to have been outstanding for a floor, or to have been cut off by the deadline (DD1).
  - The re-send is an inner loop that leaves the policy's `attempt` counter alone, so the existing recovery (a dual-era server that committed to the modern era refuses `initialize`, and the policy probes once more) still works; the fallback fact follows the final revision (DD1, DD4).
  - Each re-sent probe is cut at the deadline, so the handshake really keeps the reserve (DD2).
  - `negotiate` keeps its return type; the fallback is reported through an outcome object (DD1, DD4). The Test route reads the client's new property through a helper that tolerates the unit tests' fake clients (DD4).
  - The two HTTP cache writers and the source-update rule delete the fallback key, so it cannot outlive the server it describes (DD4).
  - The Forget rule for a local-command server is "has a stored tools list" (DD5). The note is an `App.ui.banner`, built once and toggled (DD4).
  - The test plan was wrong in two places: patching the SDK's probe timeout does not shorten the window (the connect limit must be small too), and the Python fixture recovers to the modern era, so a real fallback needs the start delay with `--legacy-only`. One existing test changes meaning and is rewritten (DD6).
  - Added: the `agents` lane, more documents, the capture surface, the HAT's timing.
- The Architect recommended not remembering a no-answer fallback. The Flight Director chose a middle rule, remembered only the second time in a row (DD3): never remembering it would cost a local server that ignores the probe the full window on every connect, which the Mission 29 design had bounded to once per run. Plain "never remembered" is listed as an acceptable variation.
- The Architect's two questions, settled by the Flight Director: a fallback that happens only in a chat shows no note until a Test (nothing but Test writes the stored cache); a local-command server with a remembered revision and no stored tools list has no Forget button until it is tested. Both are recorded as accepted gaps.
- The Architect confirmed the sortie gate: one cluster of decisions plus a small independent editor rule, two build legs and a HAT. No second review cycle was run: every change is the Architect's own fix or a narrowing of it, and leg 1 (the shared connect path) gets a Developer design review against the code before it is built.
- A side finding recorded in squawk 0372 and left out of scope: a bare `npx -y <package>` reuses a version already in npx's cache.
- The artifacts were written while `sortie/18-debrief` (PR #378) was checked out; they are committed on the sortie's own branch.
- The operator approved the design and merged PR #378 (`032f27cc`). The merge was made before the last commit of that branch was pushed (`c317c878`, squawk 0373's operator answers), so `main` lacks it; the sortie branch carries it, rebased onto `main` with the design commit. Flight status `planning` → `ready`.
