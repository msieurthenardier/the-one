# Leg: agent-write-lock

**Status**: completed
**Flight**: [Backend boundaries before connectors](../flight.md)

## Objective
Serialize every load-merge-save of an agent row, per agent, so that two concurrent writers cannot silently drop each other's changes. This closes squawk 0327.

## Context
- The flight's design decision "The per-agent lock is in-process", and squawk 0327 (deferred; its trigger has fired).
- Three writers do a load, a merge across awaits, then a save of the whole row:
  - `the_one/agent/service.py::replace_agent` (line 203), behind `PUT /api/agents/{name}`. It does `deps.store.load(name)`, then validation and merge, then `deps.store.save(cfg)` (about +13 to +53).
  - `the_one/agent/service.py::change_agent` (line 294), used by the GleepGlorp agent kind (`kinds/agent.py:261`) and the proposal apply. It does `deps.store.load(name)` (about +32), validation outside the store write lock against a snapshot, then `deps.store.save(cfg, precheck=..., on_commit=...)` (about +78). Its `precheck` already re-checks staleness under the store's write lock, so a stale GleepGlorp proposal is refused, not overwritten.
  - `the_one/interfaces/web/api.py::update_agent_mcp_credentials` (line 1185, `PUT /agents/{name}/mcp-overrides/{source_id}/credentials`). It does `store.load`, then source lookup and validation (awaits), then `existing.model_dump()` and `store.save(cfg)` of the whole row. Its docstring records the race as known.
- All coroutines share one aiosqlite connection (`the_one/db/connection.py`), and there is one server process. An in-process `asyncio.Lock` per agent name is therefore enough (squawk 0327, "Evidence").
- **Ordering only.** Nothing about what is merged, validated, masked or refused changes. The squawk's scope gate applies: semantic changes such as `updated_at` preconditions, 409s or repository API changes are out of scope.
- **Sortie 20 (PR #392, open)** changes `api.py::delete_agent` (about line 1253) and the store's `delete`. It is next to, but not inside, the credentials route. Keep this leg's edit to the credentials route minimal: wrap its body, and touch no lines outside it. Deletion is not in scope for this lock.

## Inputs
- Leg 1 landed (uncommitted on this branch). `api.py` is now 5083 lines, and the credentials route stays in `api.py`.

## Outputs
- A small lock registry in `the_one/agent/service.py`, for example `agent_write_lock(name) -> AsyncContextManager`, backed by a dict of `asyncio.Lock`.
  - Lock entries are bounded: either drop a lock when no one is waiting for it, or keep a dict whose size is bounded by the number of agents. Document which.
- Each of the three writers holds the lock for its agent from its `load` through its `save`.
- Tests: an interleaving test per pair, and a falsification.

## Acceptance Criteria
- [ ] **AC1, the lock.**
  - `agent_write_lock(name)` exists in `the_one/agent/service.py`, keyed by the stored agent name exactly as the store keys rows (`AgentStore.save` upserts by `config.name`).
  - It is a refcounted registry, `{name: [Lock, refcount]}`. Entering increments the count. Exiting decrements it and pops the entry at zero, with no await between the check and the pop. The dict therefore stays bounded.
  - It is used by five writers, around load through save:
    1. `replace_agent`;
    2. `change_agent`, wrapping its whole body including the retry loop, not per attempt;
    3. the credentials route;
    4. the revision approve route (`api.py` about line 1927);
    5. the revision restore route (`api.py` about line 1990).
  - `api.py` imports it the way it imports the other `agent_service` symbols.
- [ ] **AC2, no reentrancy deadlock.**
  - No writer renames: `replace_agent` forces `data["name"] = name`, and `save` upserts by name.
  - No writer calls another under the lock.
  - No writer takes `agent_write_lock` from inside a store `precheck` or `on_commit` hook. The store's `write_transaction` cannot be re-entered, and the order is always agent lock first, then the store write lock.
  - The proposal apply and `kinds/agent.py` call `change_agent` outside any store transaction. The design review checked this. Record it.
- [ ] **AC2b, the writers considered.** The flight log gets a table of every whole-row agent writer that `grep store.save(` finds, each marked locked or out of scope with a reason. The five above are locked. These are out of scope as background cascades, each recorded as a follow-up:
  - `self_configuration/manage.py:212, 253, 380`;
  - `mcp/rename_references.py:162`;
  - `knowledge/kb_rename.py:126`;
  - `db/override_cleanup.py:130`;
  - `db/migration.py:42`;
  - Sortie 20's `delete_agent`.

  Also confirm that the routines and notes toggles are column-level UPDATEs, not whole-row saves, and record it.
- [ ] **AC3, interleaving tests.**
  - New unit tests run two writers concurrently against the real store. Patch an await point between load and save so it yields, for example the source lookup or a validation coroutine. Then assert both changes survive.
  - Gate with an `asyncio.Event`, not with sleeps, so the test is deterministic.
  - Patch targets:
    - the credentials route's `_validate_mcp_override_credentials` and `mcp_repo.get`, patched on `api`, where the route binds them;
    - for `replace_agent`, `_post_validation_checks` or `validate_mcp_override_credentials`;
    - for `change_agent`, `_post_validation_checks` or `mcp_repo.list`.
  - Pairs to cover:
    - credentials save + whole-agent PUT, in both orders. This pair is the falsification target, because its whole-row `save` has no precheck.
    - revision approve + whole-agent PUT.
    - `change_agent` + whole-agent PUT. This pair is a regression guard only, because `change_agent`'s precheck retry may already keep both changes without the lock.
  - Falsify the credentials pair: remove the lock from one writer by editing, show the test fails because one change is lost, then put the lock back.
- [ ] **AC4, behaviour unchanged.**
  - The agent API tests pass unchanged.
  - `change_agent` and proposal-apply tests pass, including stale-refusal and `on_commit`.
  - The credentials route tests pass, as do the GleepGlorp agent kind tests.
  - `tests/test_api_name_rule.py` passes.
- [ ] **AC5, the tier.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with `main`'s counts plus the new tests.
  - Run it only when no other test process is on the host.
- [ ] **AC6, docs.**
  - The credentials route's docstring no longer says "known narrow race". It says writes to one agent are serialized.
  - `the_one/agents.md` "Agent PUT preserves credentials" (or the nearest agent-write section) states the lock rule: every new agent writer takes `agent_write_lock`.
  - The squawk 0327 file records the corrective action and verification, with status `in-progress`. The Flight Director completes it at flight review.
- [ ] **AC7, lint.** `ruff check` and `ruff format --check` are clean.

## Verification Steps
- **AC1 and AC2:** read the code and the call-graph note in the flight log.
- **AC3:** the test output, plus the falsification run.
- **AC4 and AC5:** the test outputs.
- **AC6:** the doc and squawk diffs.
- **AC7:** the ruff output.

## Implementation Guidance
1. **Read the three writers fully.** List every await between `load` and `save`. Check whether any writer calls another, or renames an agent. Look in `replace_agent` for a name change in the body, and grep for agent rename routes.
2. **Add the lock registry** to `the_one/agent/service.py`, next to the other module-level state, with a short docstring:
   - why the lock exists (squawk 0327);
   - that it is ordering-only;
   - that the process is single, so an in-process lock is enough.
3. **Wrap each writer's load-to-save span.** In `change_agent`, the store's own write lock is taken inside `save`. Take the agent lock outside it, never the reverse. The order is always agent lock, then store write lock, which avoids lock-order inversion.
4. **Credentials route:** wrap only its body's load-to-save span. Add one import line. Leave the rest of `api.py` alone (Sortie 20).
5. **Tests:** put them in a new file, for example `tests/test_agent_write_lock.py`, using the session schema template (`tests/_schema_template.py`) and the existing agent-store fixtures. Find them in the agent service tests.
6. **Falsify** (AC3), then run the related test files, then the unit tier.
7. **Update the docs and squawk 0327.** Write the flight log "Leg 2" entry, then signal `[LAND:leg]`.

## Edge Cases
- **The lock dict growing without bound:** keep it bounded (see Outputs).
- **Cancellation:** a writer cancelled while holding the lock must release it. `async with` does this.
- **`change_agent` called from the proposal apply inside another transaction:** check that no caller already holds the store write lock when it calls `change_agent`. That would invert the lock order. Record the check.
- **The agent delete route (Sortie 20):** not locked in this leg. A delete racing a save is out of scope. Record it as a possible follow-up, not a change here.

## Files Affected
- `the_one/agent/service.py`
- `the_one/interfaces/web/api.py`: the credentials route body only, plus one import.
- new `tests/test_agent_write_lock.py`
- `the_one/agents.md`
- `squawks/0327-credentials-route-agent-put-race.md`

## Citation Audit
- `the_one/agent/service.py:203` `replace_agent` (load at about +13, save at about +53) and `:294` `change_agent` (load at about +32, save with precheck and on_commit at about +78). Verified 2026-11-25 on the branch after Leg 1.
- `the_one/interfaces/web/api.py:1184-1185`: the credentials route. Its docstring records the known race. Verified after Leg 1.
- `the_one/gleepglorp/kinds/agent.py:261`: calls `agent_service.change_agent`. Verified.
- The squawk 0327 report and planned approach. Verified.

**Design review 1 (Sonnet): approve with changes.** It raised three medium issues and three low ones, all folded in above:
- the other whole-row writers are now listed;
- the two revision routes are locked;
- the background cascades are recorded as out of scope;
- the lock order and the no-lock-in-hooks rule are stated;
- the rename question is settled: no writer renames;
- `change_agent` takes the lock around its whole body;
- the falsification target is the credentials pair, and the `change_agent` pair is a regression guard;
- the tests gate with an Event, with named patch targets;
- the registry is refcounted.

The changes add scope but no new design, so there is no second review cycle. Leg 2 is `ready`.
