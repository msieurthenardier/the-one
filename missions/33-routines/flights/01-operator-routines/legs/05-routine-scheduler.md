# Leg: routine-scheduler

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Run routines on their own, on time, in the operator's time zone. A
lifespan-owned `RoutineScheduler`:
- sweeps interrupted runs at startup;
- catches up once within the grace window, or records one `missed` row;
- finishes one-offs before they run;
- never overwrites an operator edit made during a pass;
- wakes on every routine write;
- follows time-zone changes;
- stops promptly on shutdown.

## Context

- Flight DD4 (grace, missed, one-offs), DD5 (the scheduler), DD11 (the
  scheduled path is proven live by the behavior test; catch-up and DST are
  proven here at the unit tier), DD15 (security model).
- **From leg 1:**
  - `schedule.next_run`, `grace`, `occurrences_between` (counts `(start, end]`);
  - `AgentRoutineRepository.list_due`, `set_next_run`;
  - `RoutineRunRepository.insert`, `finish`, `mark_running_interrupted(reason)`;
  - `_now_iso()`.
- **From leg 4:** `the_one/routines/runner.py`, which provides:
  - `registry` (`try_spawn`, `drain`);
  - `run_routine(routine_id, trigger_kind, due_at)`, which tolerates a
    missing routine;
  - `_RoutineTurnHost`, registered in the lifespan after the factory and
    connector `start_all`;
  - the lifespan's `registry.drain()` call, which this leg replaces with
    `scheduler.stop()`.

  Leg 4's runner-cancel handling writes `interrupted` before the database
  closes, and AC5 relies on it.
- Re-read the flight log entries for legs 1 and 4 for the actual names.
- **Accepted loss (DD5).** A crash, or a `stop()` cancel, between a routine's
  advance write and its spawn loses that one occurrence with no history row: a
  one-off shows Done, and a repeating routine skips one run. Routines not yet
  advanced in that pass are recovered at the next boot. This is documented in
  `agents.md`, not engineered away.

## Inputs

- `the_one/interfaces/web/app.py` lifespan:
  - the purge loop start (`:357`) and drain (`:1433-1440`) pattern;
  - connector `start_all` (`~:418-424`);
  - `_sessions_push` registered just before `yield` (`~:476`);
  - the shutdown section after `yield`, which starts with the comment "First:
    stop pushing…";
  - the in-flight cancel (`:499-503`).
- `the_one/time_zones.py`: `utcnow()` and `load_effective_zone(conn)`, which
  returns `EffectiveZone(key, tzinfo)`.
- `the_one/db/repositories.py`: `AppMetadataRepository`.
- `the_one/interfaces/web/api.py`:
  - `PUT /time-settings` (`:2925`);
  - the routine write routes (leg 1, near `:1783`, `:1834`, `:1895`).

## Outputs

- `the_one/routines/scheduler.py` (new):
  - `RoutineScheduler(clock: Callable[[], datetime], spawn, conn_factory, sleep=None)`
    with `start()`, `stop()`, `poke()`, `run_pass(now)` and `startup(now)`;
  - a pure `next_sleep(now, earliest)`;
  - module-level `get_scheduler()` and `set_scheduler()`.
- `the_one/routines/repository.py` gains:
  - `advance_if_due(routine_id, due_iso, next_iso, finished_iso) -> bool`, a
    compare-and-set;
  - `earliest_next_run() -> str | None` (enabled, unfinished);
  - `list_active_wall_clock(after_iso)` (enabled, unfinished, a daily,
    weekdays or weekly schedule, `next_run_at > after_iso`);
  - `recompute_next_run(routine_id, expected_next_iso, new_next_iso) -> bool`,
    also a compare-and-set.
- `the_one/interfaces/web/app.py`:
  - the scheduler starts after `_sessions_push`;
  - it stops first in shutdown, above the "stop pushing" block, replacing leg
    4's `registry.drain()` call.
- `the_one/interfaces/web/api.py`: `_poke_scheduler()`, called by routine
  create, update and delete and by `PUT /time-settings`.
- `tests/test_routines_scheduler.py` (new).
- Docs: `the_one/agents.md`, CLAUDE.md and `SECURITY-MODEL.md`.

## Acceptance Criteria

- [ ] AC1. **`startup(now)`**, in this order:
      1. `mark_running_interrupted("The app stopped during this run.")`.
      2. One due pass (AC2), using the stored `next_run_at` values and the
         zone as currently stored. A routine that was due during the outage is
         caught up or recorded as missed before anything is recomputed.
      3. **The zone check.** Read the effective zone key and `app_metadata`
         `routines_zone`:
         - **Stored, and different from the current key:** for every routine
           from `list_active_wall_clock(after=now)`, recompute `next_run_at`
           with `next_run(after=now)` in the new zone, using
           `recompute_next_run`. Then store the new key.
         - **Absent** (the first boot after v45): store the key and recompute
           nothing.
         - **Equal:** do nothing.
- [ ] AC2. **`run_pass(now)`.** For each row from `list_due(now)`, each
      inside its own `try/except Exception`, so a failure is logged and the
      pass continues:
      1. `due = next_run_at`, `late = now - due`, and
         `g = grace(schedule, due, zone, anchor)`. If the stored schedule does
         not parse, log it and skip that routine (AC3 handles it).
      2. **Decide.** If `late <= g`, it runs, with trigger `schedule` when
         `late < 60 s` and `catch_up` otherwise. Otherwise it is a miss.
      3. **Advance, compare-and-set.**
         `advance_if_due(id, due_iso=next_run_at, next_iso, finished_iso)`
         applies only `WHERE id = ? AND next_run_at = ? AND enabled = 1 AND
         finished_at IS NULL`.
         - **One-off:** `finished_iso = now` and `next_iso = NULL`.
         - **Repeating:** `next_iso = next_run(after=now)`, and `finished_at`
           is untouched.

         If no row changes, the routine was edited, disabled or deleted after
         `list_due`. The edit wins: skip the routine, with nothing spawned and
         nothing recorded.
      4. **Run.** `registry.try_spawn(id, lambda: run_routine(id, trigger, due))`,
         with no other `await` between the advance and this call. If it
         refuses because a run is already going, insert a run row:
         - `trigger_kind` = the trigger;
         - `outcome` = `skipped`;
         - reason "The previous run was still going.";
         - `due_at` = due;
         - `started_at` and `finished_at` = now.

         A one-off consumed this way stays finished.
      5. **Miss.** Insert one run row:
         - `trigger_kind` = `schedule`;
         - `outcome` = `missed`;
         - `due_at` = due;
         - `started_at` and `finished_at` = now;
         - reason: for a one-off, "The scheduled time passed while the app
           was closed."; for a repeating routine, with
           `n = max(1, occurrences_between(due - timedelta(microseconds=1), now, cap=1001))`,
           "Missed {n} runs while the app was closed." (or "Missed 1 run …"),
           or "Missed more than 1000 runs …" when n is 1001.
- [ ] AC3. **No hot loop.** `next_sleep(now, earliest)` returns
      `clamp((earliest - now).total_seconds(), 1.0, 60.0)`, or 60 when
      `earliest` is `None`. The floor of 1 second means a routine whose due
      row cannot be processed (an unparsable schedule, a failing write) is
      retried at most once a second, logged each time. Test, with an
      injected `sleep` seam that records calls: one corrupt due routine
      across 5 loop iterations gives 5 sleeps of at least 1 second, the other
      routines still run, and there are no zero-length sleeps.
- [ ] AC4. **The loop.**
      - Each iteration:
        1. sleeps for `next_sleep(clock(), await earliest_next_run())`,
           through the `sleep` seam (default
           `asyncio.wait_for(event.wait(), timeout)` under
           `suppress(TimeoutError)`), and clears the event;
        2. if the effective zone key differs from the key stored at the last
           check, applies AC1 step 3 (already-due routines are left to the
           pass);
        3. calls `run_pass(clock())`.
      - The clock is passed as `lambda: time_zones.utcnow()`, so a
        `monkeypatch` applied after construction still bites.
      - **`poke()` and a once routine.**
        - With a fake clock and a recording `sleep`, `poke()` ends the current
          sleep.
        - In a real-time test (real clock), a once routine created 2 seconds
          ahead through the API runs within 10 seconds. That proves the 60-s
          tick is not what triggers it.
- [ ] AC5. **`stop()`.**
      1. Set `_stopped`, so any later `poke()` or `run_pass` is a no-op.
      2. Cancel the loop task and await it with `suppress(CancelledError)`.
      3. Call `registry.drain(5.0)`. `drain` also makes `try_spawn` refuse
         afterwards, so a Run now after `stop()` returns `None`, and the route
         maps that to 409 (or the app is already closing).

      The lifespan calls `stop()` first in shutdown, above the
      push-listener teardown, so the interrupted-run writes are still pushed
      and settled. Test: with a run mid-turn (mock `delay_ms` long), `stop()`
      returns in under 8 seconds, well short of the delay, and the run row is
      `interrupted`.
- [ ] AC6. **Unit tests with an injected clock and a fake spawn,** no
      sleeping. Each case uses concrete instants:
      - **On time:** due 09:00, now 09:00:30 gives `schedule`.
      - **Late within grace:** daily due 09:00, now 10:30 gives `catch_up`.
        Interval 2, 50 minutes late, gives `catch_up`.
      - **Beyond grace, daily:** due D 09:00 and now D+4 10:00 gives a miss
        with n = 5. Now D+4 08:00 gives n = 4.
      - **Beyond grace, interval 1:** over 2000 hours gives "more than
        1000".
      - **One-off miss:** the one-off reason text.
      - **One-off finished before spawn:** finished even when the spawned run
        then fails.
      - **Overlap:** `try_spawn` refusing records `skipped`.
      - **Not picked:** disabled and finished routines.
      - **CAS race:** an edit lands between `list_due` and the advance (the
        test edits the row through the repository inside a patched hook). The
        edit survives, nothing is spawned, and nothing is recorded.
      - **Deletion race:** a routine deleted between `list_due` and the
        advance is skipped, with no `IntegrityError` and the pass continuing.
      - **Startup order:** a routine due during the outage is recorded or
        caught up under the old values before the zone recompute. Only future
        routines are recomputed (LA to London, daily 09:00).
      - **First boot:** an absent `routines_zone` stores the key only.
      - **Startup sweep:** a seeded `running` row becomes `interrupted`.
- [ ] AC7. **Run now is independent.** A manual run never touches
      `next_run_at` or `finished_at`. A due pass during a manual run of the
      same routine records `skipped`.
- [ ] AC8. **Lifespan wiring and isolation.**
      - **Start:** after `_sessions_push` registration, which comes after the
        host registration and connector `start_all`:
        1. construct the scheduler;
        2. `set_scheduler(s)`;
        3. `s.start()`, which creates the loop task, and the task runs
           `startup(now)` as its first step, so boot is not delayed.
      - **Isolation:** each step is wrapped in `try/except Exception` with
        logging, so a scheduler failure never blocks app boot or shutdown.
      - **`_poke_scheduler()`** tolerates no scheduler. A unit test covers it.
- [ ] AC9. **Docs.**
      - **CLAUDE.md:** a short "Routines (M33 F1)" paragraph under
        Architecture: what a routine is, the REST routes, Run now, the env var
        `THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS`, and a pointer to `agents.md`.
      - **`the_one/agents.md`:**
        - the scheduler, with its startup order, compare-and-set advance,
          sleep floor and stop order;
        - the `routines_zone` key;
        - the accepted advance-to-spawn loss;
        - that every schedule instant goes through `_now_iso()`'s
          `isoformat()` form, so text comparison is correct.
      - **`SECURITY-MODEL.md`:** a "Routines" section:
        - unattended turns run with the agent's full tool access;
        - a connector routine posts with no human present;
        - only the reply is posted, never the prompt;
        - the authorized-agent rule;
        - every outcome is recorded;
        - Flight 2 extends it with agent-authored routines.
- [ ] AC10. **Gate.** `THE_ONE_TEST_NETNS=1 make test-unit` green with the
      expected skip count; `make lint` and `ruff format --check` clean.

## Verification Steps

- AC1-AC3, AC6-AC7: `tests/test_routines_scheduler.py`, as pure passes with
  an injected clock, fake spawn and `sleep` seam over a schema-template DB.
- AC4 (real-time case), AC5, AC8: over leg 4's `routine_app` fixture, or a
  minimal lifespan.
- AC9: read the diffs.
- AC10: the commands.

## Implementation Guidance

1. Repository additions (the compare-and-set methods, `earliest_next_run`,
   `list_active_wall_clock`), with unit tests.
2. `next_sleep`, `run_pass` and `startup`, pure apart from the repository.
3. The loop, `poke`, `stop` and `_stopped`. Make `registry.drain` set a
   refuse flag; edit `runner.py` minimally.
4. Lifespan wiring: start after `_sessions_push`; stop as the first shutdown
   block, with a comment explaining why it precedes "stop pushing". Remove
   leg 4's direct `registry.drain()` call.
5. `_poke_scheduler()` in `api.py`, and its call sites.
6. Docs.

## Edge Cases

- **Many routines due at once:** each is spawned as its own task, and they
  serialize per chat on the lock.
- **An interval routine after a long outage:** `next_run(after=now)` keeps
  the anchor's phase.
- **A time-zone change while a routine is mid-run:** the next wake recomputes
  future routines only. The running run is unaffected.
- **A wake a few milliseconds before the due instant:** `list_due` excludes
  the row. The next sleep is the 1-second floor, and the routine runs about a
  second late, which is `schedule` (under 60 seconds).

## Files Affected

- `the_one/routines/scheduler.py` (new)
- `the_one/routines/repository.py` (the compare-and-set and query methods)
- `the_one/routines/runner.py` (the drain refuse flag)
- `the_one/interfaces/web/app.py` (lifespan)
- `the_one/interfaces/web/api.py` (pokes)
- `tests/test_routines_scheduler.py` (new)
- `the_one/agents.md`, `CLAUDE.md`, `SECURITY-MODEL.md`

## Citation Audit

Checked at `c2366221` and by the leg 5 design reviewer:
- `app.py` purge loop start `:357` and drain `:1433-1440`;
- connector `start_all` `~:418-424`;
- `_sessions_push` before `yield` `~:476`;
- in-flight cancel `:499-503`;
- `api.py:2925` `PUT /time-settings`;
- leg 1 routes near `api.py:1783`, `:1834`, `:1895` (working tree);
- `time_zones.py:135` `utcnow`.

The names from legs 1 and 4 come from their plans and the working tree.
Re-read the flight log before starting.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off the
leg in the parent flight, and the commit) are Flight Control protocol, driven
by the execution workflow, and are not repeated here.
