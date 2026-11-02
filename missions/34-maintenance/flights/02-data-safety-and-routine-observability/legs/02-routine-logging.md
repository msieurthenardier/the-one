# Leg: routine-logging

**Status**: completed
**Flight**: [Data safety and routine observability](../flight.md)

## Objective
Every unattended routine decision, run outcome, proposal decision and purge sweep writes one INFO line to the app log, so a routine's history can be reconstructed from the log alone after the 30-day purge.

## Context
- Flight Technical Approach step 2; mission criterion "Routine runs are reconstructable from the log" (#12). Flight Design Decision: INFO, one line per decision, structured with ids; no new handler or destination (log rotation, #13, is out of scope).
- The app logs at INFO by default (`the_one/config.py` `log_level: str = "INFO"`, applied in `the_one/logging_config.py`), so INFO lines reach the `make up` / `the-one serve` log with no configuration.
- **Today.** `the_one/routines/scheduler.py::RoutineScheduler._handle` logs only exceptions (the pass wrapper); its decisions go to the DB only. `the_one/routines/runner.py::run_routine`'s `end(outcome, reason)` and `_fail_early` record the outcome with no log line. `the_one/routines/service.py` (`agent_change`, `approve_proposal`, `dismiss_proposal`) and `the_one/routines/proposals.py` have no module logger. `the_one/interfaces/web/app.py::_run_purge_sweep_and_evict` returns before logging when no chat ids were swept, and its one line logs only the chat and eviction counts, never `runs_deleted`/`routines_deleted`/`proposals_deleted` (`the_one/retention.py::run_purge_sweep`'s result keys).
- **Line format.** One line per event: a fixed event name first, then `key=value` pairs, ids bare, operator- or agent-supplied text with `%r`. Example shapes (the Developer fixes the exact wording and keeps it consistent):
  - `routine decision=spawn routine=<id> agent=<name!r> trigger=schedule|catch_up due=<iso> late_s=<n>`
  - `routine decision=missed routine=<id> agent=<name!r> due=<iso> late_s=<n> reason=<r!r>`
  - `routine decision=still_running_skip …`, `routine decision=skip_changed …` (lost `advance_if_due`: the operator's edit won), and the advance itself: `next=<iso>|none finished=<bool>` on the spawn/missed line (one line per decision, not a separate advance line).
  - `routine run=<run id> routine=<id> agent=<name!r> session=<sid> started trigger=<kind>` and `routine run=<run id> … outcome=<o> reason=<r!r>` (the `end()` path and `_fail_early`, which has no run id before insert: log `run=none`).
  - `routine proposal=<id> agent=<name!r> action=create|update|delete decision=applied|pending|approved|superseded|dismissed flagged=<bool> routine=<id or none>`.
  - `purge sweep deleted=<n> runs_deleted=<n> routines_deleted=<n> proposals_deleted=<n> evicted=<n> last_purge_at=<iso>` once per sweep, including when every count is 0. Do not log the `ids` list (it can be thousands of session ids); its length is `deleted`.
- **Never log** the prompt text, tool output, message content, payload values, or a schedule's full JSON. Routine and agent names are attacker-influenceable (an agent writes routine names), so they go through `%r`, never `%s`. The run `reason` strings are app-authored, but log them with `%r` too.
- **Where decisions are made.** The flight's acceptable variation applies: put a line at the single place the decision is made (e.g. a pending proposal is decided in `agent_change`, not in `insert_pending`). Operator-direct routine CRUD (REST create/update/delete) is not in scope; agent-made changes are, through `agent_change`.
- **Run now.** `POST …/routines/{id}/run` goes through `run_routine` with `trigger_kind="manual"` (check), so its run lines come for free; no scheduler line.
- **Behavior test.** Author `tests/behavior/routine-run-observable-from-logs.md` per the behavior-test format in `.flightops/ARTIFACTS.md` and the conventions of an existing routine spec (`tests/behavior/agent-schedules-follow-up.md`): scratch instance (port ≥8490, scratch data dir under `$HOME`, scratch cwd, `THE_ONE_DEV_MODE=true`, never 8484 or the default data dir; CLAUDE.md "Behavior-test credential convention"); a routine whose run fails deterministically (e.g. an agent on a mock provider that is then deleted, giving "The agent's model provider is missing.", or whatever the Developer finds simplest and deterministic); stop the instance across its due time; restart; read the outcome, the catch-up or missed decision and the reason from `serve.log` alone, then confirm them against `GET …/routines/{id}/runs`. The Developer authors the spec only; the Flight Director runs it with `/mission-control:behavior-test` after the leg lands.

## Inputs
- Leg 1 landed (independent files; no dependency beyond the shared tree).

## Outputs
- INFO lines in `scheduler.py`, `runner.py`, `service.py` (a module logger), `app.py::_run_purge_sweep_and_evict`.
- `caplog` unit tests beside the existing ones (`tests/test_routines_scheduler.py`, `tests/test_routines_runner.py`, `tests/test_routines_proposals.py` or `tests/test_routines_service.py`, `tests/test_chat_history_purge.py`).
- `tests/behavior/routine-run-observable-from-logs.md` (status `active`, no run yet).
- `the_one/agents.md` "Routines (M33)": a short "Routine log lines" paragraph listing the events and the `%r` rule. `SECURITY-MODEL.md` "Routines": one sentence that the log carries routine and agent names (repr-quoted) and ids, never prompts or output.

## Acceptance Criteria
- [ ] **AC1 — scheduler decisions.** For each of spawn (`schedule`), spawn (`catch_up`), missed (one-off and repeating), still-running skip and skip-because-changed, a `caplog` test with the frozen/injected clock asserts exactly one INFO record from `the_one.routines.scheduler` naming the decision, the routine id, the repr-quoted agent name, the due time and the lateness, plus the next run (or none/finished) where the routine advanced.
- [ ] **AC2 — run outcome.** For a run that ends `succeeded` (or the success outcome name the runner uses), one that ends `failed` through the restore path, and one through `_fail_early`, a test asserts an INFO record with the outcome and the reason; a started line carries the run id and session id.
- [ ] **AC3 — proposals.** `agent_change` logs applied or pending (with the proposal id, action and `flagged`); `approve_proposal` logs approved or superseded; `dismiss_proposal` logs dismissed. One test per decision.
- [ ] **AC4 — purge.** `_run_purge_sweep_and_evict` logs one INFO record per sweep with every count, including a sweep that deleted nothing (a test asserts the zero line), and the old conditional line is replaced, not duplicated.
- [ ] **AC5 — nothing sensitive.** A test gives a routine a prompt containing a unique marker string and a name containing a newline and a quote, runs it through the scheduler and runner with the test fakes, and asserts the marker appears in no log record and the name appears only in its repr form (no raw newline in any message).
- [ ] **AC6 — behavior spec.** `tests/behavior/routine-run-observable-from-logs.md` exists in the project's behavior-test format with a step table whose expected results name the exact log lines the code now writes.
- [ ] **AC7 — docs.** agents.md and SECURITY-MODEL.md updated as in Outputs.
- [ ] **AC8 — suites green.** `make test-unit` passes; ruff check and format clean.

## Verification Steps
- AC1–AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_routines_scheduler.py tests/test_routines_runner.py tests/test_routines_service.py tests/test_routines_proposals.py tests/test_chat_history_purge.py -x --timeout 30` (adjust to the files used).
- AC6/AC7: read the spec and docs.
- AC8: `THE_ONE_TEST_NETNS=1 make test-unit`; `ruff check the_one/ tests/`; `ruff format --check the_one/ tests/`.

## Implementation Guidance
1. Read `_handle` and add the decision lines at each return path (the `due is None` early return is a corrupt row: log it at WARNING once, not INFO). Lateness is `late.total_seconds()` rounded to one decimal or whole seconds.
2. In `run_routine`, log a started line after the run row is inserted, and in `end()` and `_fail_early` the outcome line; the classify path ends through `end()` too, so one line covers it.
3. Add `logger = logging.getLogger(__name__)` to `service.py`; log in `agent_change` (both branches), `approve_proposal` (each return), `dismiss_proposal`.
4. Rewrite the purge log in `_run_purge_sweep_and_evict` so it logs before the early return (or restructure so one line covers both paths).
5. Tests per AC; reuse the existing fixtures and fakes in each test file. Use `caplog.at_level(logging.INFO, logger="the_one.routines.scheduler")` (and the right logger name per module).
6. Author the behavior spec last, so its expected lines match the code.

## Edge Cases
- A pass that finds a routine already running inside the runner set (`self._spawn` returns `None`): the still-running skip line, never a spawn line.
- Clock skew giving negative lateness (due slightly in the future at pass time cannot happen through `list_due`, but guard formatting so a negative value does not raise).
- The purge loop's exception path keeps its existing `logger.exception`.
- Existing tests that assert "no log records" at some level (e.g. `test_zone_change_skips_an_unreadable_schedule_quietly` asserts nothing at WARNING+) must still pass; new lines are INFO.

## Files Affected
- `the_one/routines/scheduler.py`, `the_one/routines/runner.py`, `the_one/routines/service.py`, `the_one/interfaces/web/app.py` (`_run_purge_sweep_and_evict` only; sortie 07's `_restore_session` is untouched)
- the test files above; `tests/behavior/routine-run-observable-from-logs.md`
- `the_one/agents.md`, `SECURITY-MODEL.md`, the flight log

## Citation Audit
Checked at `b497312f` (Flight Director, 2026-11-02): `scheduler.py::_handle` at :217 (returns at `advance_if_due` false, missed `_record`, `self._spawn` / `record_still_running_skip`) — verified; `runner.py` `async def end(outcome, reason)` at :262 and `_fail_early` at :201 — verified; `service.py` `agent_change` :494, `approve_proposal` :648, `dismiss_proposal` :725, no `logger` — verified; `app.py::_run_purge_sweep_and_evict` at :1499 with `if not ids: return result` before the only `logger.info` — verified (flight said ~L1462); `retention.py::run_purge_sweep` result keys `{deleted, ids, runs_deleted, routines_deleted, proposals_deleted, last_purge_at}` — verified; `config.py` `log_level: str = "INFO"` — verified.
