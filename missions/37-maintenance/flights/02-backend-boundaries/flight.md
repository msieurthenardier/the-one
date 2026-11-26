# Flight: Backend boundaries before connectors

**Status**: completed
**Mission**: [Post-Mission-36 Maintenance](../../mission.md)

## Contributing to Criteria

- [ ] The web API is split into feature routers (P1). *Partly: the MCP and connector groups moved in Leg 1. The agent group is deferred to the connectors mission's leg 0, because Sortie 20 was open.*
- [x] Concurrent agent writes cannot drop credentials (squawk 0327, completed)
- [x] Python modules have a size ratchet (T3)

## Pre-Flight

### Objective

Split the web API along feature lines before the connectors rework grows it further. Close the agent write race while that path is open, and stop Python modules from growing unnoticed.

### Open Questions

N/A for the fixes. The router split's exact module boundaries are settled at leg design, against the existing GleepGlorp routers (`gleepglorp_proposals_api.py`, `gleepglorp_fills_api.py`), which already show the pattern.

### Design Decisions

**Routers, not a rewrite.** Routes move as they are, with the same paths, methods, dependencies and response shapes, into router modules included by `api.py`. `tests/test_api_name_rule.py` (route classification) and the credential-gate tests are the guard.

**The MCP, connector and agent routes go first.** They are the ones the connectors rework will touch. The other groups follow only if each move stays mechanical.

**The per-agent lock is in-process.** An `asyncio.Lock` per agent name, taken by `replace_agent`, the agent-credentials route and the GleepGlorp agent `change` apply. There is one server process, so no database locking is needed. This is squawk 0327; its trigger has fired.

**The size ratchet follows `tests/test_area_module_size.py`.** Every Python module under `the_one/` is capped at 800 lines. A module already over the cap is pinned at its current size and may only shrink.

*Design decisions added 2026-11-25, at flight start (Flight Director, after the Flight 1 debrief):*

**Sequencing with Sortie 20.** Sortie 20 ("deleting an agent deletes its chats", branch `sortie/20-deleting-an-agent-deletes-its-chats`) is in flight in a parallel worktree. It changes `delete_agent` in `api.py`, `app.py`, `db/schema.py` (v57), `db/connection.py` and `db/repositories.py`.
- The MCP and connector router group moves first, because Sortie 20 does not touch it.
- The agent route group moves only if Sortie 20 has merged when that leg starts. The Flight Director checks `main` immediately before.
- Otherwise the agent group is deferred, which is this flight's existing "acceptable variation". It is recorded for the connectors mission's leg 0.
- The 0327 lock leg reads `main` again first, because Sortie 20's `delete_agent` change sits next to the agent write path.

**Closing gate: a quiet-host readiness check and a fallback** (Flight 1 debrief, recommendation 2).
- **Readiness check:** the gate starts only after the 1-minute load has been below 1.0 for 3 consecutive minutes, with no test process from any worktree. The wait is bounded at 60 minutes.
- **Fallback if no quiet window comes:** run the unit tier and each browser lane one at a time with `TEST_TIMEOUT=3600`, as a correctness check, recording the load next to each reading. Never start a full `--parallel 3` gate above load 10. Never re-budget from a loaded run.
- **T2 is carried from Flight 1.** The quiet gate re-budgets every lane, including the six with no measurement note, and restates the full-gate target and the unit tier's xdist reading at N=4. If T2 slips again, it goes to the mission debrief as unmet.

**Squawk 0428 is folded in** (`_nav.goto` has no boot-ready wait). It sits directly in the closing gate's path, because under load it fails lanes. It is fixed before the closing gate, and validated by that gate's full browser run.

### Citation Audit

From the 2026-11-24 report (P1, T3, SV3):
- `the_one/interfaces/web/api.py`: 6533 lines, about 115 routes.
- `the_one/interfaces/web/app.py`: 4139 lines.
- `the_one/agent/service.py` `replace_agent` (about lines 203-255).
- The agent-credentials route (`api.py` about line 1249).

These are re-checked at leg design.

### Prerequisites

- [x] PR #388 is merged.
- [x] The connectors rework has not started on these files.

### Pre-Flight Checklist

N/A. This is a maintenance flight with concrete fixes.

## In-Flight

### Technical Approach

1. **The router split (P1).**
   - Move the MCP-source and connector routes, then the agent routes, out of `api.py` into `the_one/interfaces/web/routes_*.py`, or the project's existing router naming.
   - Keep `api.py` as the assembly point.
   - Check that the move changed nothing: grep the tests for `patch("...api.<handler>")` and `/openapi.json` pins, and compare an `/openapi.json` dump from before and after the move.
   - `app.py` stays out of scope unless a move is mechanical. It is recorded as remaining debt.
2. **The per-agent write lock (0327).**
   - Add a lock registry keyed by agent name, taken around the load-merge-save in `replace_agent`, in the credentials route and in the GleepGlorp agent apply.
   - Add a test that races two writers, so that each one's credential survives.
3. **The Python size ratchet (T3).** Add a unit test that records the current over-cap modules, for example `repositories.py`, `app.py`, `schema.py`, `api.py`, `resolver.py` and `factory.py`, with their sizes.
4. **Write-service logging (P5, optional).**
   - Add one `logger.info` line on each create, update and delete path in the agent, provider, secret and knowledge services, and in the proposal apply.
   - Log names and ids only, never values.

### Checkpoints

- [x] The routes have moved, and the `/openapi.json` before-and-after diff is empty (the MCP and connector groups).
- [x] The lock is in place and the race test passes.
- [x] The size ratchet test is in place.

### Adaptation Criteria

**Divert if**: a route move needs a behaviour change, such as a shared helper whose import order matters, or a dependency that depends on the app. Stop that group, and record it.

**Acceptable variations**: only the MCP and connector group moves this flight, and the agent group is recorded for the connectors mission's leg 0.

### Legs

*(Designed by `/mission-control:agentic-workflow`.)*

1. [`mcp-connector-routers`](legs/01-mcp-connector-routers.md): completed.
2. [`agent-write-lock`](legs/02-agent-write-lock.md): completed.
3. [`python-size-ratchet`](legs/03-python-size-ratchet.md): completed.
4. [`closing-gate`](legs/04-closing-gate.md): completed.

The planned `agent-routers` leg was deferred (see the flight log, Leg 2 decision).

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged (PR #394)
- [x] `the_one/agents.md` module map updated for the new routers ("Web route modules (M37 F2 L1)")

### Verification

The unit tier and every browser lane pass. The `/openapi.json` dump is the same before and after. The race test and the size ratchet pass.
