# Squawk 0134: Two self-configuration surface tests fail intermittently under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-09

## Report

Two unit-tier tests in `tests/test_self_configuration_surface.py` sometimes fail in a full `make test-unit` run. Both pass when re-run on their own.

On 2026-10-07 the `squawk/turnaround-2026-10-07` branch had nine full runs, and only one hit them: the squawk 0129 Developer's run, with 5453 passed, 10 skipped and 2 failed. The other eight runs had no failures, and none of that batch's changes touch the self-configuration surface.

The tests' names suggest timing assertions under concurrency. The one failing run was the busiest, with other test processes on the host. A gate that sometimes goes red for no reason trains people to dismiss red, so a real failure here could be waved off as "the known flake". Find the timing or ordering assumption and make each test deterministic. Do not add retries, `xfail` or skips.

Distinct from squawk 0132. That one is about skips (the native-watch self-probe); these are failures.

## Evidence

- `tests/test_self_configuration_surface.py:467` `TestSquawk0006TwoAgentSimultaneousIsolation` → `test_two_live_agt_credentials_never_cross` (line 483)
- `tests/test_self_configuration_surface.py:570` `TestSquawk0005ShutdownDrainUnderLoad` → `test_live_surface_connection_evicted_before_general_drain` (line 604)
- Both use the `running_surface` fixture, so they run against a live loopback surface.
- Rate: 1 hit in 9 full `make test-unit` runs on 2026-10-07 (the turnaround's Developer and Reviewer gate runs). A re-run of the two tests alone gave 2 passed.
- The failure output from that run was not kept. Reproducing it under forced load, for example with busy-loop processes alongside a repeat of the two tests as squawk 0132's Developer did, is the first step.

## Corrective Action
Reproduced first, then fixed in the test fixture only; no production code touched.

Reproduction: 40 busy-loop processes (`while :; do :; done`, PIDs recorded and killed by a `trap`, verified gone afterwards) on a 20-core host, running the two tests together in one pytest process. 4 of 10 runs failed, always `test_live_surface_connection_evicted_before_general_drain` and always after `test_two_live_agt_credentials_never_cross` had passed; each failure took ~33 s. The drain test alone and the pair without load passed every time (6/6 and 6/6). Failure excerpt:

```
the_one/mcp/_pool.py:229: in _entry_worker  await client.connect()
E  the_one.mcp.errors.MCPConnectionError: MCP server did not respond within 30 seconds during initialize.
Captured stderr: ERROR:    ASGI callable returned without completing response.
```

Debug log of a failing run: the server logged "Closing SSE writer" and then "Request stream 0 not found for message" *before* the initialize response was produced, and the client logged "peer closed connection without sending complete message body". So the SSE response was cancelled before it sent anything, and the client (which does not treat an empty SSE body as an error) waited out its 30 s budget. An `sse_starlette` probe patched into the run showed why: `EventSourceResponse._listen_for_exit_signal_with_grace` returned with `AppStatus.should_exit == True`.

Root cause: `sse_starlette.sse.AppStatus.should_exit` is a class-level latch that nothing ever clears. A per-loop watcher task latches it whenever the uvicorn server found through the SIGTERM handler has `should_exit` set (it polls every 0.5 s). The `running_surface` fixture stops its server with `server.should_exit = True`, so if the previous test's watcher polls inside that teardown window (a loaded host stretches the window), the latch survives into the next test's fresh server and every SSE response there is cancelled on arrival. The first `initialize` POST of the next test that uses SSE (the pool-driven drain test; the pair's first test is not hit because nothing precedes it) then gets an empty body. Not a template-DB effect (0134 predates it) and not a timing budget that was too small: the 30 s wait was a symptom of a response that never came. In production there is one uvicorn server per process, so the latch only matters for shutdown there. Test isolation only; the drain itself is not at fault.

Fix (`tests/test_self_configuration_surface.py`): new `_reset_sse_shutdown_flag()` helper clears `AppStatus.should_exit`; `running_surface` calls it at setup (the previous test's loop is closed by then, so its watcher cannot re-latch) and again at teardown after the server task has finished. No retries, skips or timeout changes.

Squawk 0157 is the same defect (same test, same 30 s initialize timeout, seen in CI); see its artifact.

## Verification
- Under the same 40-busy-loop load: 50 of 50 consecutive runs of the two tests together passed (pre-fix: 4 failures in 10). Load PIDs confirmed gone afterwards.
- The fix addresses the reproduced cause (the sticky `AppStatus.should_exit` latch), not a timeout.
- `make test-unit`: 5627 passed, 10 skipped (the expected count), run without the forced load.
- `ruff check tests/` clean; `ruff format --check tests/` clean (370 files).

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the self-configuration credential-isolation tests and a CI install script). Confirmed the `sse_starlette` `AppStatus.should_exit` class-level latch against the library source (`sse.py`: class attribute, set by the per-loop watcher, never cleared). The fix is test-only, with no retries, skips or timeout widening. `tests/test_self_configuration_surface.py`: 11 passed.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-09` on branch `squawk/turnaround-2026-10-09`
