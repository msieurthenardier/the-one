# Leg: verify-integration

**Status**: completed
**Flight**: [Change Monitoring](../flight.md)

## Objective

Prove the flight against the real environment and the by-hand gates the
mission's branch layout requires: premise-audit and run the behavior test
`kb-folder-watch-round-trip` on a dedicated dev instance, run `make lint`,
`make test-unit` (verbatim), the release-closure `pip-audit`, and one frozen
Windows `fly execute` asserting the ninth needle; then record the results
and amend the mission artifact (DD-12).

## Context

- Flight DD-10 (apparatus: shell + http + filesystem against port 8485 and
  a scratch data directory; fixture on a native filesystem; timing at the
  10 s interval; Step 3 as the clean event-path proof), DD-11 (no closure
  change; one frozen run budgeted as a diagnostic — a `file watcher` FAIL
  is iterated with a `hiddenimports` entry), DD-12 (the Windows 1M
  re-measure folds into Flight 6 / mission close; `get_vector_store()`
  shutdown hook stays recorded), DD-6's operator call (the Flight 3 spec
  is amended only, not re-run), and the mission's Branch Layout (no CI
  lane on a PR into the mission branch — every gate by hand, recorded
  here).
- Legs 1–3 are committed at `560b7dd` + `abc555c` (draft PR #202). This
  leg changes no source; it may correct the `draft` behavior spec
  (authoring, not drift) and edits `mission.md` and the flight log.
- Flight 3's apparatus, reused verbatim: mint the credential before the
  first `make up` on a fresh scratch dir; detached `fly execute`
  (`setsid nohup … &` in a subshell with literal paths) watched with
  anchored greps (`^RESULT: (PASS|FAIL)`, `^(succeeded|failed|errored|
  aborted)$`), stale clients via `pgrep -f "^fly -t the-one execute"`;
  `make test-unit` verbatim, alone, foreground. Baseline installer size
  at Flight 3 close: 134,886,157 bytes (build 608700).
- Behavior-test execution mode: `SendMessage` is available in this
  session → live two-agent mode (Flight 3 ran the same way).

## Inputs

- Prerequisite probes (2026-09-16, after Leg 3): port 8485 free, nothing
  on 8484, no `.the-one.8485.pid`, no stale `fly execute` client;
  `pip-audit` 2.10.0, `uv` 0.10.0; `fly -t the-one status` → logged in
  (operator re-login during Leg 3); `windows-worker` running; `/tmp` is
  native ext4.
- `tests/behavior/kb-folder-watch-round-trip.md` (status `draft`, never
  run; 11 steps).
- `ci/tasks/windows-installer-build.yml` (now asserts `file watcher: OK`
  by name beside the three Flight 2/3 needles).
- `missions/24-knowledge-bases/mission.md`: the 1M re-measure open
  question (`:321-328`), the Flight 4 bullet (`:409-413`), the Flight 6
  bullet (`:418-421`).

## Outputs

- `tests/behavior/kb-folder-watch-round-trip.md` corrected if the premise
  audit finds drift; status `active` after its first pass; `Last Run` set.
- `tests/behavior/kb-folder-watch-round-trip/runs/<timestamp>.md` (run log,
  committed; evidence directory gitignored / outside the tree).
- `missions/24-knowledge-bases/mission.md`: the 1M open question amended
  with the operator's vehicle decision (a synthetic 1M-chunk corpus
  measured at mission close on the Windows worker, flush constants
  re-checked); the Flight 6 bullet carries it; the Flight 4 bullet checked
  at landing.
- Flight log: gate figures, frozen-run build number and installer size,
  the behavior-test verdict and run-log path.

## Acceptance Criteria

- [x] **AC-1 — Premise audit.** A Developer traces every apparatus premise in the behavior spec against the landed code (route paths and bodies; the `monitoring` PUT shapes and the three 422s; the `watch` / `watch_error` fields and the four state words; the settle, interval floor and hold-cap numbers against `watcher.py` constants and `MonitoringSettings` bounds; what the walk does when the root is gone and when it returns; the `starting` allowance; the `idle`-or-`running` and one-re-poll tolerances; the credential and `make up`/`make down` mechanics; the native-filesystem precondition) and either confirms each or corrects the `draft` spec; findings recorded in the flight log before the first run.
- [x] **AC-2 — Dev instance.** `THE_ONE_DATA_DIR=<scratch> .venv/bin/python -m the_one.main rotate-api-credential` then `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> make up` brings up a dedicated instance with a scratch data directory outside the repository; `GET /api/live` → 200; never 8484, never the default data directory. Torn down (`make down` with the same env) after the run.
- [x] **AC-3 — Behavior test passes.** `/mission-control:behavior-test kb-folder-watch-round-trip` → `pass` on every checkpoint, Steps 3, 6, 9 and 10 included. A failing step is investigated and fixed in a new commit (never amended), then re-run. The run-log path is recorded in the flight log; the spec's `Last Run` and `Status: active` are set.
- [x] **AC-4 — Lint and unit gates.** `make lint` clean; `make test-unit` run once, alone, foreground: green, with passed / skipped / wall time recorded (expected 4,649 passed / 10 skipped at `abc555c`).
- [x] **AC-5 — Release closure.** `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` piped to `.venv/bin/pip-audit --disable-pip -r …` → `No known vulnerabilities found`; the export lists `watchfiles==1.1.1` exactly once and contains no `hf-xet` and no `sqlite-vec` line.
- [x] **AC-6 — Frozen run.** One detached `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=<dir>` at `abc555c`: `^RESULT: PASS`, all nine doctor gates `OK` including `file watcher: OK`, task `succeeded`, installer size recorded against 134,886,157 bytes (expected within a few hundred KB — no closure change; `watcher.py` is pure Python and `watchfiles` was already bundled). A `file watcher` failure is iterated as a diagnostic inside the flight (DD-11: a `hiddenimports` entry for `watchfiles._rust_notify`); one outside this flight's files is raised to the operator.
- [x] **AC-7 — Mission artifact.** `mission.md`'s 1M re-measure open question is amended with the DD-12 decision and points at Flight 6; the Flight 6 bullet names it; the Flight 4 bullet is checked `[x]` at landing (Phase 3 of the workflow).
- [x] **AC-8 — Documentation check.** `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`, `README.md`, `docs/windows-install.md` reflect the monitoring settings, the watch fields, the data-directory refusal and the ninth gate (landed in Legs 1 and 3; verified, not re-written).

## Verification Steps

- AC-1: the Developer's report in the flight log.
- AC-2: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8485/api/live` → `200`; `ss -ltn | grep -c ':8484 '` → `0` throughout.
- AC-3: the run log's `**Status**: pass`.
- AC-4: `make lint`; `make test-unit` (foreground, ≥ 900 s budget).
- AC-5: the two commands above; `grep -c "^watchfiles==" <export>` → `1`; `grep -c "hf-xet\|sqlite-vec" <export>` → `0`.
- AC-6: `grep -E '^RESULT: (PASS|FAIL)' <log>`; `grep -E '^(succeeded|failed|errored|aborted)$' <log>`; `grep -c ': OK' <log>` ≥ 9; `grep 'file watcher: OK' <log>`; `ls -l <dir>/the-one-setup-*.exe`.
- AC-7/AC-8: read the files.

## Implementation Guidance

1. Premise audit (Developer spawn, read-only on code, may edit the spec).
2. In parallel, launch the frozen run detached and run `pip-audit`
   (independent of the instance).
3. Start the dev instance; run the behavior test via the skill (live
   mode); tear the instance down.
4. `make lint`; then `make test-unit` alone.
5. Artifact edits; flight-log entry; leg `completed`; commit
   (`flight/4: verify-integration — …`) and push; PR checklist updated;
   Phase 3 flight completion.

## Edge Cases

- **Frozen `file watcher` gate fails**: read the detail line — an import
  failure means the extension was not collected (add `hiddenimports`);
  a round-trip failure on the Windows worker means native notification
  did not deliver inside the CI container within 10 s — raise to the
  operator before changing the gate.
- **Behavior Step 3 slow on a loaded host**: the 30 s bound covers a 5 s
  settle plus a walk and a short index; if it fails on timing alone,
  re-run once before treating it as a defect, and record the observed
  latency either way.
- **Step 9's re-subscribe log noise**: one warning per 10 s tick per
  missing folder is the designed retry (spec row conventions).
- **Leftover dev instance on 8485**: `THE_ONE_PORT=8485 make down` first;
  the probe says none exists.

## Files Affected

- `tests/behavior/kb-folder-watch-round-trip.md` (status / corrections)
- `tests/behavior/kb-folder-watch-round-trip/runs/*.md` (new)
- `missions/24-knowledge-bases/mission.md`
- `missions/24-knowledge-bases/flights/04-change-monitoring/flight-log.md`

## Citation Audit

Checked at `abc555c` on 2026-09-16: `mission.md:321-328` (the 1M open
question), `:409-413` (Flight 4 bullet), `:418-421` (Flight 6 bullet);
`ci/tasks/windows-installer-build.yml` needle array (Leg 1 added
`file watcher: OK`); Flight 3 flight-log `:868-876` (frozen-run baseline
figures). All present.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
