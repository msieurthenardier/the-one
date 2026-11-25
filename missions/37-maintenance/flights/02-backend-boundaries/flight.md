# Flight: Backend boundaries before connectors

**Status**: ready
**Mission**: [Post-Mission-36 Maintenance](../../mission.md)

## Contributing to Criteria

- [ ] The web API is split into feature routers (P1)
- [ ] Concurrent agent writes cannot drop credentials (squawk 0327)
- [ ] Python modules have a size ratchet (T3)

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

### Citation Audit

From the 2026-11-24 report (P1, T3, SV3):
- `the_one/interfaces/web/api.py`: 6533 lines, about 115 routes.
- `the_one/interfaces/web/app.py`: 4139 lines.
- `the_one/agent/service.py` `replace_agent` (about lines 203-255).
- The agent-credentials route (`api.py` about line 1249).

These are re-checked at leg design.

### Prerequisites

- [ ] PR #388 is merged.
- [ ] The connectors rework has not started on these files.

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

- [ ] The routes have moved, and the `/openapi.json` before-and-after diff is empty.
- [ ] The lock is in place and the race test passes.
- [ ] The size ratchet test is in place.

### Adaptation Criteria

**Divert if**: a route move needs a behaviour change, such as a shared helper whose import order matters, or a dependency that depends on the app. Stop that group, and record it.

**Acceptable variations**: only the MCP and connector group moves this flight, and the agent group is recorded for the connectors mission's leg 0.

### Legs

*(Designed by `/mission-control:agentic-workflow`.)*

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] `the_one/agents.md` module map updated for the new routers

### Verification

The unit tier and every browser lane pass. The `/openapi.json` dump is the same before and after. The race test and the size ratchet pass.
