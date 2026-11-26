# Squawk 0327: The targeted credentials save and a whole-agent PUT can overwrite each other

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-04
**Completed**: 2026-11-26

## Report
The agent tile's credentials Save (`PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials`) and the agent editor's main Save (`PUT /api/agents/{name}`) both load the whole agent row, merge, then save the whole row, with awaits in between. If the two interleave, whichever saves last silently drops the other's changes, in either direction: credentials, or fields like the system prompt. The window is narrow (one operator, both Saves within milliseconds). The race was accepted and documented at sortie 09 leg 5; the sortie 09 debrief turned it into this squawk.

## Evidence
- `the_one/interfaces/web/api.py::update_agent_mcp_credentials` (~1567-1627): `store.load` → source lookup and validation (awaits) → `existing.model_dump()` → `store.save(cfg)` of the whole row; its docstring notes the race.
- `api.py::update_agent` (~1470): the same load-merge-save shape.
- All coroutines share one aiosqlite connection (`the_one/db/connection.py`), so an in-process `asyncio.Lock` is sufficient.

## Corrective Action
Mission 37 Flight 2 Leg 2. `the_one/agent/service.py::agent_write_lock(name)`: a per-agent in-process `asyncio.Lock` in a refcounted registry (entry popped at zero, so it stays bounded). Held from load through save by five writers: `replace_agent`, `change_agent` (whole body, retry loop included), the targeted credentials route and the revision approve and restore routes. Ordering only: nothing merged, validated or masked changed, and no `updated_at` precondition, 409 or repository change was needed, so the scope gate did not trip. Lock order is agent lock then store write lock. The background cascades (self-configuration `manage.py`, MCP and KB rename references, override cleanup, migration) and Sortie 20's agent delete are not locked; recorded as follow-ups in the Flight 2 log. The rule is in `the_one/agents.md` (service section, "Agent write lock").

## Verification
`tests/test_agent_write_lock.py`: interleaving tests gated on `asyncio.Event` (no sleeps) for credentials save + whole-agent PUT in both orders, revision approve + PUT in both orders, and `change_agent` + PUT in both orders (regression guard), plus registry tests (bounded, released on error and cancellation). Falsified: with the lock removed from the credentials route, the credentials/PUT pair fails (the PUT's `system_prompt` change is lost); restored, it passes.

## Sign-Off
**Reviewer**: the Mission 37 Flight 2 flight-end Reviewer (Sonnet; credentials surface)
**Verdict**: confirmed (`[HANDOFF:confirmed]`). The refcounted lock is correct. The five writers hold it from load to save, and it is never taken inside a store `precheck` or `on_commit` hook.
**Commit**: `593aa5ac` (`flight/2: MCP and connector routers, per-agent write lock, size ratchet`) on `flight/02-backend-boundaries`

## Disposition
**Deferred**: low real-world exposure (single-user local app, millisecond window), logged from the sortie 09 debrief — revisit when the agent write path is next touched (for example the `api.py` agent-override extraction recommended in that debrief), or at the next squawk turnaround.
