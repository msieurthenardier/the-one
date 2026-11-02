# Flight: Data safety and routine observability

**Status**: ready
**Mission**: [Post-Mission-33 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] A stale connector save keeps a paired peer. *(#4, squawk 0288)*
- [ ] Routine runs are reconstructable from the log. *(#12)*
- [ ] Session pushes cost less. *(#11)*
- [ ] An agent Save made before the model list loads keeps the stored model. *(squawk 0228; added at the Flight 1 debrief)*

---

## Pre-Flight

### Objective
Close the one traced silent data-loss path left after Mission 33: a connector editor opened before a pairing drops the new peer on Save. Make unattended routine work visible in the app log. Cut the two costs that grow with Mission 33's new-chat-per-run volume:
- the hidden agent drawer rebuilding on every sessions push;
- the push frame being re-encoded once per socket.

### Open Questions
N/A. This is a maintenance flight. Capping the pushed session list is an open operator decision and is out of scope (see the [2026-10-30 report](../../../../maintenance/2026-10-30.md), "Operator decisions still open").

### Design Decisions

**Leg 1 fixes the connector path only, not optimistic concurrency for every editor**: the general `updated_at`/409 protocol belongs to the agent write-safety block that waits for sortie 07.
- Rationale: sortie 07 edits the agent routes. A protocol designed now would be designed twice.
- Trade-off: other editors stay last-writer-wins until that block flies.
- Leg design: choose between a server-side union of `config.allowlist.peers` and a 409 for a stale save. A union cannot express "remove a peer" from a stale form. A 409 needs the editor to resubmit. Settle it in the leg's design review, with the operator if it changes what the editor shows.

**Logging is INFO, one line per decision, structured with ids**: no new log handler or destination.
- Rationale: log rotation (finding #13) is a separate design call about where logs live.
- Trade-off: the log grows with routine volume until #13 lands.

### Citation Audit

Verified at `e33e8657` by the 2026-10-30 inspectors; spot-checked by the Flight Director:

| Citation | Status |
|---|---|
| `the_one/interfaces/web/api.py::update_connector` (L4366) — re-reads the stored row, then `merged = existing.model_dump(); merged.update(data)` (L4398-4399), a shallow merge: an incoming `config` replaces the stored one whole; only `secrets` is merged per key | verified |
| `the_one/connectors/inbound.py::_pair_peer` (L129) — copies `connector.config`, appends to `allowlist.peers`, `repo.update`, no version check | verified |
| `the_one/routines/scheduler.py::RoutineScheduler._handle` (L217) — logs only exceptions; decisions are written to the DB only | verified |
| `the_one/routines/runner.py` `end(outcome, reason)` (L262) — records the outcome with no log line | verified |
| `the_one/routines/proposals.py`, `the_one/routines/service.py` — no module logger | verified (scheduler and runner have `logger`; these two do not) |
| `the_one/interfaces/web/app.py::_run_purge_sweep_and_evict` (~L1462) — returns before logging when no chat ids were swept, so the run, routine and proposal counts (`retention.py:62-67`) are never logged | verified |
| `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js:737` — every store notification calls `render()` with no shown/changed check | verified |
| `the_one/sessions/_broadcast.py::broadcast_to_all` (L40, `ws.send_json` at L45) — encodes per socket | verified |

Re-audit at leg design time; line numbers drift.

### Prerequisites
- [ ] Sortie 07 has not changed `update_connector` (it touches `inbound.py:480-483` and the agent routes, not the connector PUT). Re-check at Leg 1 design.

### Pre-Flight Checklist
- [x] All open questions resolved (N/A, maintenance flight)
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified (at leg start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**1. `connector-peers-survive-stale-save` (#4, squawk 0288).**
- **Red test first**, in-process: create a connector; GET it (the editor's view); pair a peer through the real `_pair_peer` path; PUT the earlier `config` back unchanged. Assert that the peer is still stored. Today this test should fail, which proves 0288 live; record the result.
- **Then the fix** in `update_connector`, by the mechanism the leg's design review picks (see Design Decisions).
- **Also cover:** a deliberate peer removal through the editor still removes it, and secrets keep their `__MASKED__` handling.
- **Read** `connector-editor.js` `buildPayload` to confirm what the client sends.
- **Record** the outcome in the flight log and link it from squawk 0288's Disposition (0288 is escalated into this leg).

**2. `routine-logging` (#12).** Add INFO lines carrying the routine id, agent name and run id:
- `RoutineScheduler._handle`: spawn, catch-up, missed, still-running skip, advance. Include the due time and the lateness.
- runner `end()`: the outcome and the reason.
- Proposal apply, approve and dismiss: proposal id, action, flagged or not.
- The purge sweep: log the whole result dict once per sweep, including when nothing was deleted.
- **Rules:** never log the prompt text or tool output. Routine names are attacker-influenceable, so log them with `%r`.
- **Tests:** `caplog` tests per decision, with the frozen clock.
- **Behavior test:** author `routine-run-observable-from-logs` (recommended by the report). A restart across a failing routine's due time, read from the log alone.

**3. `session-push-cost` (#11).**
- **Drawer.** In `agent-drawer.js`, skip `render()` on a `sessions` notification while the drawer is hidden or not on Chats, and when its derived chat count is unchanged. Render once on show.
- **Server.** In `broadcast_to_all`, encode the payload once and `send_text` the same string to every socket, keeping the per-socket error handling.
- **Tests:**
  - A browser test counting drawer rebuilds across a push with the drawer closed.
  - A unit test that encoding happens once for N sockets.
- **Pushed-list cap:** do not add one; it is an operator decision.
- **Measurements to rerun:** the inspection's figures were 24 ms per push at 5k sessions and 106 ms / 7.3 MB at 20k.

### Checkpoints
- [ ] Leg 1 red test recorded (0288 proven or disproven)
- [ ] Routine log lines visible in a scratch instance's log
- [ ] Drawer rebuild count is 0 for a push while it is closed

### Adaptation Criteria

**Divert if**:
- The 0288 red test passes at HEAD (not reproducible). Record the evidence against 0288 and drop the leg's fix.
- The connector fix needs a client change beyond `buildPayload` (an editor reload or a conflict UI). Take that to the operator before building.

**Acceptable variations**:
- Moving a log line to the repository or service layer when that is the single place a decision is made.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `connector-peers-survive-stale-save` - Red test pairing between GET and PUT; preserve the peer in `update_connector`. Carries the work escalated from 0288.
- [ ] `routine-logging` - INFO lines for scheduler decisions, run outcomes, proposal decisions and the full purge result; behavior test `routine-run-observable-from-logs`.
- [ ] `session-push-cost` - Drawer render guard; encode the push once per broadcast.
- [ ] `agent-save-keeps-model` - Squawk 0228: a Save pressed before the first model list loads must not store an empty `llm_model` (design call at leg design: keep Save disabled until the list loads or fails, or keep the stored model as a selected option while loading); pin it with a browser test that holds the models response. Re-test flake 0229 after it lands. **Mission constraint:** "no new behaviour visible to the operator beyond the log lines and the preserved peers" — keeping the stored model selected while loading fits it; disabling Save is a visible change and needs the operator to amend the constraint at leg design. *(Added at the Flight 1 debrief, operator decision 2026-11-02.)*

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated (`agents.md` Routines and Connectors sections; SECURITY-MODEL if the log adds a field it should mention)

### Verification
- The 0288 regression test passes. A deliberate peer removal still works.
- `routine-run-observable-from-logs` passes against a scratch instance (port ≥8490, scratch data dir, never 8484).
- With a chat open and the drawer closed, a routine run causes no drawer rebuild. A push to 3 sockets encodes once.
