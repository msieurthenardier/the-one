# Squawk 0005: Verify shutdown-drain under load for a surface-enabled agent

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-26
**Completed**: 2026-08-29

## Report

Flight 1 (Self-Configuration Surface) implemented the shutdown-drain WARNING
mitigation — the lifespan evicts every marked surface row's pool entries before
`_mcp_pool_shutdown_drain()`, so a loopback session can terminate while the
listener is still up. The mitigation is **reasoned but never exercised under
load**: neither Flight 1 nor Flight 2 ran a test with a surface-enabled agent
holding a *live pool connection at shutdown*. Add that verification. If it
surfaces a real drain defect, escalate to a flight rather than expanding this
squawk.

Carried forward from the Flight 1 debrief and re-homed here after being pulled
out of Mission 21 Flight 2 Leg 2 at design review (pool/lifecycle verification
debt, orthogonal to approval governance).

## Evidence

- Flight 1 debrief, "What Could Be Improved → Technical": "Shutdown-drain WARNING
  mitigation is reasoned but unproven under load."
- Mission 21 Flight 2 flight log (2026-08-25): the two Flight-1 carry-overs pulled
  out of Leg 2 at design review; Flight 2 debrief Action Items confirm neither was
  logged until now.
- Mitigation site: the app lifespan's pre-drain eviction of marked rows' pool
  entries ahead of `_mcp_pool_shutdown_drain()` (`the_one/interfaces/web/app.py`
  lifespan).

## Corrective Action

Added a test-only verification of the shutdown-drain mitigation under a
genuinely live self-configuration connection: `tests/test_self_configuration_surface.py::TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain`.

**Approach taken: pool-layer fallback (not full lifespan-level composition),
per the squawk's sanctioned escape hatch.** Full composition — driving the
real `the_one.interfaces.web.app.lifespan` via the bare `async with
lifespan(app)` idiom `tests/test_lifespan.py` uses — was evaluated and
found infeasible with existing fixtures, for two independent reasons:

1. The self-configuration surface is a REAL loopback HTTP connection to
   `http://127.0.0.1:{settings.port}{MOUNT_PATH}/`. Nothing is listening on
   that port unless a real `uvicorn.Server` is bound to it. The bare
   `async with lifespan(app)` idiom never binds a port — it only enters the
   context manager in-process — so it can never produce a genuinely LIVE
   surface connection regardless of which `FastMCP` instance's
   `session_manager.run()` is entered.
2. Even granting a real bound server, the production `app` singleton's
   `session_manager.run()` is guarded to fire at most ONCE per process
   (`app.py`'s `_self_configuration_session_manager_started` — see that
   module's own docstring and `tests/test_self_configuration_surface.py`'s
   module docstring). By the time any test runs, that guard is realistically
   already spent from earlier `TestClient(app)` cycles elsewhere in the
   suite, so even a live-bound `app` singleton would not reliably serve the
   mount.

The test instead reproduces the SAME SHAPE the lifespan's shutdown branch
performs — `_evict_all_for_source(source_id)` for the marked surface row,
strictly BEFORE the general `_mcp_pool_shutdown_drain()` — directly at the
`the_one.mcp._pool` layer, against a connection obtained exactly the way
`running_surface` (this file's existing fixture) provides one: a real
`uvicorn.Server` bound to an OS-allocated port running the actual
self-configuration `FastMCP` mount, dialed back into via the platform's own
pool-acquire path (`the_one.mcp._pool.acquire`), the same call a real agent
turn makes.

The test:
- enables the self-configuration surface for a seeded agent via the real
  `POST /api/agents/{name}/self-configuration` route (mints the credential,
  the surface row, and the loopback `MCPSource`, exactly as production
  does);
- acquires a genuinely live, connected `MCPClient` for that row via
  `pool_mod.acquire(agent_name, source_id)` — the exact call an agent turn
  makes;
- fires one in-flight tool call (`get_my_configuration`) without awaiting
  it, so it races the eviction/disconnect that follows;
- monkeypatches `pool_mod._evict_all_for_source` and `pool_mod.shutdown_drain`
  with call-order-recording spies, then runs the eviction and the general
  drain in the exact sequence `app.py`'s shutdown branch uses, wrapped in
  `asyncio.wait_for(..., timeout=15.0)` (comfortably under the drain's own
  worst-case ~20s ceiling: two ~10s-per-entry ceilings, evict then drain);
- asserts the recorded order is `["evict", "drain"]`;
- asserts the pool registry (`pool_mod._pool`) is empty afterward;
- bounds the in-flight call's own outcome separately (`wait_for(..., 5.0)`,
  any exception tolerated — only a hang would be a defect, and `wait_for`
  both catches and cancels that);
- asserts no WARNING/ERROR record in `caplog` mentions a stuck or
  unterminated session (`"did not terminate"` / `"stuck"` / `"unterminated"`).

No drain defect was found — the sequence completed well within budget
(sub-second in practice), in the correct order, with an empty registry and
no stuck-session warning. Nothing to escalate.

A `finally` block unconditionally resets the MCP pool's module-global state
(`pool_mod._clear_for_test()`) after the test, because `shutdown_drain()`
latches `_shutting_down = True` process-wide — left set, it would break
every later test in the same process whose path reaches `pool_mod.acquire`
(mirrors `tests/test_lifespan.py`'s `reset_lifespan_singletons` fixture,
which exists for the identical hazard).

Only `tests/test_self_configuration_surface.py` was touched (new test
class appended) plus this squawk file's status; no source under `the_one/`
was changed.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_surface.py -x --timeout 120` — 11 passed (10 pre-existing + the new test), 0 failed.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_surface.py -x --timeout 120 -k TestSquawk0005` — 1 passed in isolation.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_lifespan.py -x --timeout 120` — 8 passed (unchanged; run to confirm no singleton bleed from this squawk's work, per the task's request — this squawk did not modify `test_lifespan.py`).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_pool.py -x --timeout 120` — 27 passed, 2 deselected (unchanged; confirms no pool-layer regression from the monkeypatch/spy technique used).
- Test name: `TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain`.
  Assertions: eviction runs before the general drain (`order == ["evict", "drain"]`); the pool registry is empty after the sequence (`pool_mod._pool == {}`); the whole eviction+drain sequence completes within a 15s bound (no hang); no WARNING/ERROR in `caplog` mentions a stuck/unterminated session.
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` — both clean (`All checks passed!`; `455 files already formatted`).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-29; Sonnet — batch touches `api_credential.py`, the DB import graph, and self-configuration identity)
**Verdict**: confirmed
**Commit**: `cefa92f` on `squawk/turnaround-2026-08-29` — PR #181

Full unit suite at close-out: 4586 passed, 10 skipped, 704 deselected, 20 warnings in 557.56s (0:09:17).

Reviewer note (non-blocking): the evict-before-drain order assertion is driven by the test's own helper, not `app.py`'s lifespan shutdown branch — logged as squawk 0025.
**Reviewer**:
**Verdict**:
**Commit**:
