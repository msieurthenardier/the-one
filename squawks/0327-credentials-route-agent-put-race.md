# Squawk 0327: The targeted credentials save and a whole-agent PUT can overwrite each other

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-04
**Completed**: —

## Report
The agent tile's credentials Save (`PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials`) and the agent editor's main Save (`PUT /api/agents/{name}`) both load the whole agent row, merge, then save the whole row, with awaits in between. If the two interleave, whichever saves last silently drops the other's changes, in either direction: credentials, or fields like the system prompt. The window is narrow (one operator, both Saves within milliseconds). The race was accepted and documented at sortie 09 leg 5; the sortie 09 debrief turned it into this squawk.

## Evidence
- `the_one/interfaces/web/api.py::update_agent_mcp_credentials` (~1567-1627): `store.load` → source lookup and validation (awaits) → `existing.model_dump()` → `store.save(cfg)` of the whole row; its docstring notes the race.
- `api.py::update_agent` (~1470): the same load-merge-save shape.
- All coroutines share one aiosqlite connection (`the_one/db/connection.py`), so an in-process `asyncio.Lock` is sufficient.

## Corrective Action
*(written at completion)* Planned approach: a per-agent `asyncio.Lock` (keyed by agent name, e.g. a small lock registry) held around load-merge-save in both write paths. Ordering only: no change to what is merged, validated or masked. **Scope gate:** if the fix needs semantic changes (an `updated_at` precondition, 409s, a repository API change), stop and escalate to a sortie.

## Verification
An interleaving unit test: start a credentials save and a whole-agent PUT concurrently (patch an await point to yield), then assert both changes survive. Falsify it by removing the lock.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: low real-world exposure (single-user local app, millisecond window), logged from the sortie 09 debrief — revisit when the agent write path is next touched (for example the `api.py` agent-override extraction recommended in that debrief), or at the next squawk turnaround.
