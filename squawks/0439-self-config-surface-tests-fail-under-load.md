# Squawk 0439: five self-configuration surface tests fail in the unit tier under load

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: —

## Report

During squawk 0438's verification, `THE_ONE_TEST_NETNS=1 make test-unit` at load 20 to 23 failed six tests:
- the known 0431 `test_mcp_pool` flake;
- five tests in `tests/test_self_configuration_surface.py`.

Re-run alone at load 23, both files passed (45 passed). The five were not failing in the 0434 and 0428 unit runs at load 7 to 19. The failure messages were not kept, so the first step is to capture them.

## Evidence
- `squawks/0438-browser-app-spawn-ready-timeout-under-load.md`, Verification (the unit-run line).
- `tests/test_self_configuration_surface.py::_wait_ready` polls `/api/live` with a fixed `timeout: float = 10.0` for an in-process uvicorn task on the test's own event loop. That is a suspect, not a confirmed cause.

## Corrective Action
**Capture.** The original failure did not reproduce. `THE_ONE_TEST_NETNS=1 make test-unit` at load 29 falling to 8 passed (12401 passed, 15 skipped), and the file alone passed 3 times at load about 5. No failure messages exist, so the observed cause is unconfirmed.

**Deterministic evidence (not load).** The fixture `running_surface` starts uvicorn in-process and gates on `_wait_ready`, a fixed 10 s `/api/live` poll. Injecting an 11 s `asyncio.sleep` at the start of the test lifespan (scratch edit, since removed) made the first test fail with `RuntimeError: server on http://127.0.0.1:56203 did not become ready within 10.0s` (`tests/test_self_configuration_surface.py:72`). Any start slower than 10 s fails every test using the fixture, which is the same failure shape as 0438 for the browser spawn. Only the injected delay was demonstrated. Real causes of a slow start, such as cold imports or a slow DB open on a busy host, are plausible but were not measured. The file takes about 5 s for 13 tests unloaded. The inference, not measured under load, is that a 10 s ceiling per start has little headroom at load 20 and above.

**Fix.** `_wait_ready` now defaults to `tests/browser/_app_ready.py::app_ready_timeout()` (45 s, env `THE_ONE_TEST_APP_READY_TIMEOUT`), the 0438 knob. The poll returns at the first 200, so the longer ceiling costs time only on a genuinely slow start.

**Deliberately unchanged.** The teardown `wait_for(task, 10.0)`, the shutdown-sequence 15 s and the in-flight 5 s bounds. They guard hangs (the 15 s one is documented as sitting under the drain's own worst case) and nothing shows them firing. If the five failures recur with a message from one of these, raise that one with the evidence.

**Caveat.** This is hardening against the one fragile timing that was demonstrated, not a confirmed match for the original five failures. If they recur, the captured message decides the next step.

## Verification
- Ruff check and format check on `tests/`: clean.
- Run before the fix, `make test-unit` (NETNS=1), load 29 to 8: 12401 passed, 15 skipped.
- File alone, 3 sequential runs after the fix (no other test process; load 3.5, 3.3, 3.1): 13 passed each, about 5.3 s.
- After the fix, `THE_ONE_TEST_NETNS=1 make test-unit`, load 3 to 5: 12401 passed, 15 skipped, 149 s.
- The scratch delay showed the pre-fix failure; it was not re-run against the fix (an 11 s delay is under 45 s by construction).

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; test-only, no security-sensitive surface)
**Verdict**: confirmed.
- The import of `tests.browser._app_ready` resolves through `pyproject.toml` `pythonpath = ["tests", "."]`, the same way the file already imports `tests._credential_helpers`. It loads neither Playwright nor the browser conftest.
- The `None` default resolves at call time. A bad env value raises inside the fixture's `try`, so the server is still torn down.
- Leaving the hang-guard waits unchanged is reasonable.
- The record is honest about the unreproduced failure. Two sentences that went past the evidence have been reworded.
- Non-blocking, accepted: no test pins `_wait_ready`'s default to `app_ready_timeout()`. A small follow-up if wanted.

**Commit**: `squawk/0439: ...` on squawk/0439-self-config-surface-under-load

## Disposition
**Deferred**: the hardening for the one demonstrated fragile timing (the 10 s in-process ready wait) has landed. The original five failures were not reproduced and their cause is unconfirmed, so this squawk is not marked completed. Revisit when any `tests/test_self_configuration_surface.py` test fails again in a unit run. The 0435 per-test timeout means the run now keeps a failure message and stack. Capture them here, and let that message pick the next fix.
