# Behavior Test: A Routine's History Is Readable From the App Log

**Slug**: `routine-run-observable-from-logs`
**Status**: active
**Created**: 2026-11-02
**Last Run**: 2026-11-02-19-15-26 (pass, 6/6; the first run 2026-11-02-18-55-16 was partial, 4/6, and led to the run-id fix and this re-authoring)

> Authored at Mission 34 Flight 2 leg 2 (`routine-logging`), against the INFO lines the
> code writes. Re-authored after the first run (`runs/2026-11-02-18-55-16.md`, partial):
> the setup (mock provider `base_url`, the routine create body, whole-minute rounding of
> `next_run_at`, timing measured from the actual due times, B's one-minute repeat, C's
> real failure path, console-duplicated lines) is corrected, and the product gap that run
> found (a pre-chat failure and a `missed` decision logged without the stored run id) is
> fixed: both lines now carry `run=<id>`.

## Intent

Verifies that every unattended routine decision and run outcome is written to the app
log (`serve.log`), so the history of a routine can be reconstructed from the log alone
(mission criterion 12):
- the scheduler's decision for each routine that came due while the app was closed: a
  catch-up spawn, or a `missed` record with the reason;
- the run's start (run id, session id) and its outcome and reason, for a run that
  succeeds and one that fails;
- the daily purge sweep writes one line per sweep, with counts, even when it deleted
  nothing;
- nothing sensitive reaches the log: no prompt text, and agent names only repr-quoted.

Every line is cross-checked against `GET /api/agents/{name}/routines/{id}/runs`.

## Preconditions

- **Dev instance** started from a scratch working directory (CLAUDE.md "SAFETY RULE"),
  never port 8484 or 8485 and never the operator's default data directory:
  ```bash
  mkdir -p $HOME/the-one-behavior-test-scratch/cwd && cd $HOME/the-one-behavior-test-scratch/cwd
  THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data the-one rotate-api-credential
  THE_ONE_PORT=<port >= 8490> THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data \
    THE_ONE_DEV_MODE=true <repo>/.venv/bin/the-one serve >serve.log 2>&1 &
  echo $! > serve.pid
  ```
  `GET /api/live` returns 200. Every other request carries
  `Authorization: Bearer <contents of the data dir's api-credential>` (shell-only
  Executor). Stop the instance only by the PID in `serve.pid`.
- The scratch data directory is fresh. The default log level (INFO) is in force.
- `sqlite3` is on the PATH (used once, while the instance is stopped).
- The host clock is correct. Steps 3 and 4 wait on real time (about 5 minutes).
- Each routine and purge line appears once in `serve.log`, in the app's logger format
  (`<date> INFO the_one.routines.scheduler: routine decision=...`); the rich console
  handler no longer repeats `the_one` records (squawk 0308).
- **Line formats** (key=value, ids bare, agent names `%r`-quoted):
  - `routine decision=spawn|still_running_skip routine=<id> agent='<name>' trigger=schedule|catch_up due=<iso> late_s=<n> next=<iso|none> finished=<True|False>`
  - `routine decision=missed run=<run id> routine=<id> agent='<name>' due=<iso> late_s=<n> next=<iso|none> finished=<True|False> reason='<text>'`
  - `routine decision=skip_changed routine=<id> agent='<name>' due=<iso> late_s=<n>`
  - `routine run=<run id> routine=<id> agent='<name>' session=<sid> trigger=<kind> started`
  - `routine run=<run id> routine=<id> agent='<name>' session=<sid|none> trigger=<kind> outcome=<o> reason=<repr>`
  - `purge sweep deleted=<n> runs_deleted=<n> routines_deleted=<n> proposals_deleted=<n> evicted=<n> last_purge_at=<iso>`

## Observables Required

- shell: `grep` over `serve.log`; process start and stop by recorded PID.
- http: JSON bodies, through curl.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Create mock provider `p-ok` (`type` `mock`, `base_url` `http://localhost`, `config.response.content` "ok") and `p-bad` (same). Create agent `ok-agent` on `p-ok` and `broken-agent` on `p-bad` (`provider_config_id`, `llm_model` `mock-default`). | (setup) Both agents exist. |
| 2 | Create three routines through `POST /api/agents/{agent}/routines`, each with body `{"name", "prompt": "LOGMARK-5b2e", "schedule": {"start": …, "repeat": …}}`: `A` on `ok-agent` with start `{"in": {"amount": 3, "unit": "minutes"}}` and no repeat; `B` on `ok-agent` with start in 2 minutes and `repeat` `{"every": 1, "unit": "minute"}`; `C` on `broken-agent` with start in 3 minutes and no repeat. Record the three ids and each routine's actual `next_run_at` (it is rounded up to the whole minute, so A and C are due at the next whole minute after creation + 3 min, B one minute earlier). Stop the instance (`kill $(cat serve.pid)`), wait for exit. Then `sqlite3 <data>/the-one.db "PRAGMA foreign_keys=OFF; DELETE FROM llm_providers WHERE name='p-bad';"` (use the table's real name column if it differs). | The instance is down. `serve.log` so far holds no `routine decision=` or `routine run=` line (nothing came due). |
| 3 | Wait until at least 190 s after A's and C's actual `next_run_at` (so `late_s >= 180`; measured from those due times, not from creation). Restart the instance with the same command (append to `serve.log`) and start the read within 20 s of the restart. | (wait only) B keeps firing every minute after the restart; that is expected. |
| 4 | Read the log, logger-format lines only: `grep -E 'the_one\.routines\.[a-z]+: routine (decision\|run)=' serve.log` (the console duplicates are ignored). Judge per routine. | `A`: `routine decision=spawn routine=<A> agent='ok-agent' trigger=catch_up due=… late_s=<>=180> next=none finished=True`, then a `started` line and an `outcome=ok reason=None` line, both carrying the same `run=` and `session=` ids. `B`: exactly one `routine decision=missed run=<id> routine=<B> agent='ok-agent' due=… late_s=… next=<iso> finished=False reason='Missed N runs while the app was closed.'` with N >= 2 (later `decision=spawn trigger=schedule` lines for B, with their started/ok lines, are allowed). `C`: `routine decision=spawn routine=<C> agent='broken-agent' trigger=catch_up … next=none finished=True`, then a single `routine run=<id> routine=<C> agent='broken-agent' session=none trigger=catch_up outcome=failed reason="Couldn't find or create the chat."` and no `started` line (with the provider row deleted the chat cannot be created, so no chat or running row exists); a WARNING from `the_one.routines.runner` ("could not create its chat", with traceback) is allowed. No line anywhere in the whole log contains `LOGMARK-5b2e`. |
| 5 | `GET /api/agents/ok-agent/routines/{A}/runs`, `.../{B}/runs` and `GET /api/agents/broken-agent/routines/{C}/runs`. | `A`: one run, `outcome` `ok`, `trigger_kind` `catch_up`; its `id` and `session_id` equal the ids in the log's `A` lines. `B`: exactly one run with `outcome` `missed`, its `id` equal to the log's `decision=missed run=` id and its `reason` equal to the log's `reason=` text (other `ok` runs of B from later minutes are allowed). `C`: one run, `outcome` `failed`, `reason` "Couldn't find or create the chat.", its `id` equal to the `run=` id of the log's failure line, `session_id` null. |
| 6 | `grep 'purge sweep' serve.log`. | At least one logger-format line (the sweep comes from the first start; a restart within the day logs none, since the sweep is not due) in the form `purge sweep deleted=0 runs_deleted=0 routines_deleted=0 proposals_deleted=0 evicted=0 last_purge_at=<iso>`; the line exists although nothing was deleted, and no line reads `daily purge swept`. |
| 7 | Stop the instance by PID. | A clean exit: the PID is gone and `serve.log` ends with "Finished server process". C's WARNING from step 4 is expected; no `ERROR` line appears in `serve.log`. |

## Out of Scope

- Log rotation and the log's destination (mission criterion 13).
- The wording of the model's reply (the mock provider is scripted).
- Agent-made routine changes and proposal decisions: covered by the unit tier
  (`tests/test_routines_service.py`, "log lines").
