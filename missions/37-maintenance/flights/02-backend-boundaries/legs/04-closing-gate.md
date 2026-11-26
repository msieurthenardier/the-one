# Leg: closing-gate

**Status**: completed
**Flight**: [Backend boundaries before connectors](../flight.md)

## Objective
Fix squawk 0428 (`_nav.goto` has no boot-ready wait). Then run the flight's closing gate over every lane. Use the quiet-host readiness check and its fallback, and re-budget all lanes if a quiet window comes (T2, carried from Flight 1).

## Context
- **Flight design decisions:**
  - "Closing gate: a quiet-host readiness check and a fallback";
  - "Squawk 0428 is folded in".
- **Squawk 0428.** `tests/browser/_nav.py::goto` is a plain `page.goto`. Under heavy load the app's first `/api/config` is slow (the bwrap probe), so the router starts late, and a test's first `expect(...)` fails at the default 5 s.
  - Squawk 0424 (merged) already added `wait_router_started(page)` to `open_destination`. `wait_router_started` returns on its first poll when `App.router.current()` is set.
- **Why every lane must run.** Flight 2 moved 17 routes out of `api.py` (Leg 1), wrapped five writers in a lock (Leg 2) and added logging (Leg 3). The closing gate is the first full browser verification of Flight 1 and Flight 2 together.
- **The re-budget rule** (`the_one/agents.md` "Budget history"):
  - Compare each lane's wall time against its last quiet reading, or against its budget if there is no reading.
  - A change of more than 15%, or a lane over budget, sets a new budget of wall × 1.25, rounded up to 30 s.
  - **Six lanes have no measurement note:** `knowledge`, `mcp-connection`, `settings-tools`, `providers`, `contracts-widget` and `chats-widgets`.
- **The host.** It has been loaded by other projects for most of two days (load 7-28). Sortie 20's worktree runs lanes too. Never run concurrently with another test process (CLAUDE.md host policy).

## Inputs
- Legs 1-3 committed at `593aa5ac`.

## Outputs
- The 0428 fix in `tests/browser/_nav.py`, plus any caller adjustments.
- A gate reading in the flight log.
- If the host was quiet: updated budgets in `scripts/run-tests.sh`, a "Budget history" entry and restated targets in `the_one/agents.md`.
- Squawk 0428 completed in its file.

## Acceptance Criteria
- [ ] **AC1, the 0428 fix.**
  - `_nav.goto` calls `wait_router_started(page)` after `page.goto`.
  - Before changing it, grep every `_nav.goto` caller (`tests/browser/`). Any caller that loads a page where `window.App` never boots must not wait on the router: an error page, a deliberately failing `/api/config`, a non-app URL. For those, add a parameter such as `goto(..., boot=False)`, or use `page.goto` directly with a comment. Record each one.
  - `tests/test_nav_helper.py` passes.
  - Re-run the squawk's failing test, `tests/browser/test_flow_chat_composer_library.py::test_the_empty_states_text_column_is_centred`, 3 times in isolation. If the host is quiet, reproduce the race with a throwaway slow-`/api/config` route stub, as squawk 0424 did. Remove the stub afterwards.
  - Squawk 0428's Corrective Action and Verification are recorded, with Status `in-progress`.
- [ ] **AC2, the readiness check.**
  - Before the gate, wait up to 60 minutes for this condition: the 1-minute load below 1.0 for 3 consecutive minutes, and no test process from any worktree running.
  - Record the start time, how long the wait took, and the outcome.
- [ ] **AC3, the gate.**
  - **If quiet:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python make gate`. Record the unit summary and time, `PARALLEL_RESULT`, every lane's wall time and budget, the total, and the load at the start and the end.
  - **Fallback, if not quiet:** run the unit tier first. Then run each canonical browser lane (`scripts/run-tests.sh --help` lists them) with `--lane <lane>`, one at a time, with `TEST_TIMEOUT=3600`. Contracts lanes also need `THE_ONE_REQUIRE_WEBKIT=1`.
    - Before each lane, check that no other test process is running. If one is, wait for it.
    - Record each lane's result, wall time and load.
    - Never start a `--parallel` gate above load 10.
- [ ] **AC4, triage.**
  - A failure is re-run in isolation.
  - Squawk 0424 and 0428 races should be gone after AC1.
  - A failure that reproduces in isolation and was not on `main` is a regression from this flight. Stop and report it; do not land.
  - A failure that predates this flight (verify against `main` cheaply, if you can) is logged as a squawk with evidence.
- [ ] **AC5, re-budget (T2), only from a quiet `--parallel 3` gate.** Apply the rule to every lane, including the six with no note. Update `scripts/run-tests.sh` (budgets and "measured" comments) and `the_one/agents.md` (a "Budget history" entry, the full-gate target, and the unit tier's xdist reading at N=4). `tests/test_run_tests_lanes.py` passes.
  - **On the fallback path:** do not re-budget. Record "T2 not met: no quiet host" for the mission debrief. Still add one sentence to "Budget history" recording the fallback run.
- [ ] **AC6, lint.** `ruff check` and `ruff format --check` are clean.

## Verification Steps
- **AC1:** the `_nav.py` diff, the caller audit and the three isolation runs.
- **AC2, AC3:** the flight log's readiness and gate records.
- **AC4:** the triage notes.
- **AC5:** the diffs to `scripts/run-tests.sh` and `agents.md`, and the lane test.
- **AC6:** the ruff output.

## Implementation Guidance
1. Make the 0428 fix and audit its callers (AC1). Run `tests/test_nav_helper.py` and the failing test.
2. Start the readiness wait (AC2). Use a bounded background loop that checks `/proc/loadavg` and `ps` every 60 s. Do not use `pgrep -f` loops, and add no load.
3. Run the gate, or its fallback (AC3), in the background. Wait for its completion notifications.
4. Triage (AC4). Re-budget only if quiet (AC5).
5. Write the flight log's "Leg 4" entry, then `[LAND:leg]`.

## Edge Cases
- **Sortie 20 lanes start during the fallback:** pause between lanes. Never overlap.
- **A lane is killed by `TEST_TIMEOUT` under load:** re-run that lane alone once. If it is killed again, record it with the load, as a load limit, not a failure.
- **`_nav.goto` before an authenticated session exists** (the handoff exchange in `tests/browser/conftest.py`): make sure the boot wait comes after the handoff, or is skipped for that call.

## Files Affected
- `tests/browser/_nav.py`, and any `goto` callers that need `boot=False`
- `scripts/run-tests.sh` and `the_one/agents.md` (only if re-budgeting)
- `squawks/0428-nav-goto-has-no-boot-ready-wait.md`
- the flight log

## Citation Audit
- `tests/browser/_nav.py::goto` is a plain `page.goto`. `open_destination` calls `wait_router_started` (squawk 0424, merged in #391). Verified.
- Squawk 0428 names the failing test at `test_flow_chat_composer_library.py:134-136`. Verified.
- The re-budget rule and the six unnoted lanes are from the Flight 1 Leg 3 entry and `agents.md`. Verified.
