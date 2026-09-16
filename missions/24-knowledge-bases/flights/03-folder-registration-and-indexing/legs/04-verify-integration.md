# Leg: verify-integration

**Status**: completed
**Flight**: [Folder Registration and Indexing](../flight.md)

## Objective

Prove the flight against the real environment and the by-hand gates the
mission's branch layout requires: premise-audit and run the behavior test
`kb-folder-index-round-trip` on a dedicated dev instance, run `make lint`,
`make test-unit` (verbatim), the release-closure `pip-audit`, and one frozen
Windows `fly execute`; then record the results and resolve the mission's
open questions this flight answered.

## Context

- Flight DD-9 (apparatus: shell + http + filesystem against port 8485 and a
  scratch data directory; the seeded resume step), DD-11 (no closure change;
  one frozen run at flight close budgeted as a diagnostic — plan for an
  iteration if it fails), DD-12 (the Windows 1M re-measure leaves the
  flight as a mission open question), and the mission's Branch Layout
  section (no CI lane runs on a PR into the mission branch — every gate
  by hand, recorded here).
- Legs 1–3 are committed at `e39da94` (draft PR #200). This leg changes no
  source; it may correct the `draft` behavior spec (authoring, not drift)
  and edits `mission.md` and the flight log.
- Flight 2's debrief lesson on metrics: `make test-unit` verbatim, alone,
  foreground — an explicit `-m` replaces `addopts` and lets the
  `requires_bwrap` tests run.
- Flight 2's frozen-run apparatus: detached `fly execute` (`setsid nohup …
  &` in a subshell with literal paths), watched with anchored greps
  (`^RESULT: (PASS|FAIL)`, `^(succeeded|failed|errored|aborted)$` — the task
  script's own comments contain "RESULT: PASS"), stale clients killed via
  `pgrep -f "^fly -t the-one execute"`. Baseline installer size at Flight 2
  close: 134,790,292 bytes (build 606735).

## Inputs

- Prerequisite probes at leg design (2026-09-15): `sqlite3` 3.44.4 on PATH;
  `uv` 0.10.0; `.venv/bin/pip-audit` 2.10.0; port 8485 free and nothing
  listening on 8484; `fly -t the-one status` → logged in; `windows-worker`
  `running`; no stale `fly execute` client.
- `tests/behavior/kb-folder-index-round-trip.md` (status `draft`, never
  run).
- `Makefile`: `make up` / `make down` keyed by `THE_ONE_PORT` (PID file
  `.the-one.$(THE_ONE_PORT).pid`, log `.the-one.$(THE_ONE_PORT).log`).
- `ci/tasks/windows-installer-build.yml` (`platform: windows`, input
  `repo`, output `installer`; asserts `usearch: OK`, `fts5: OK`,
  `embedding model: OK` by name plus `RESULT: PASS`).
- `missions/24-knowledge-bases/mission.md` Open Questions: the `parent_id`
  question (`:304-306`) and the skipped-files question (`:307-310`).

## Outputs

- `tests/behavior/kb-folder-index-round-trip.md` corrected if the premise
  audit finds drift; status `active` after its first pass.
- `tests/behavior/kb-folder-index-round-trip/runs/<timestamp>.md` (run log,
  committed; evidence directory gitignored).
- `missions/24-knowledge-bases/mission.md`: two open questions resolved,
  one added.
- Flight log: gate figures, frozen-run build number and installer size,
  the behavior-test verdict and run-log path.

## Acceptance Criteria

- [x] **AC-1 — Premise audit.** A Developer traces every apparatus premise in the behavior spec against the landed code (route paths, status codes, body keys, the `requeued: 3` arithmetic, the `.the-one.8485.pid` path, the `sqlite3` seeded-resume step's table/column names, the credential file location) and either confirms each or corrects the `draft` spec; the audit's findings are recorded in the flight log before the first run.
- [x] **AC-2 — Dev instance.** `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> make up` brings up a dedicated instance with a scratch data directory outside the repository; `GET /api/live` → 200; never 8484, never the default data directory. Torn down (`make down` with the same env) after the run.
- [x] **AC-3 — Behavior test passes.** `/mission-control:behavior-test kb-folder-index-round-trip` → `pass` on every step including Step 10 (seeded resume). A failing step is investigated and fixed in a new commit (never amended), then re-run. The run log path is recorded in the flight log; the spec's `Last Run` and `Status: active` are set.
- [x] **AC-4 — Lint and unit gates.** `make lint` clean; `make test-unit` run once, alone, foreground: green, with passed / skipped / wall time recorded (expected 4,547 passed / 10 skipped at `e39da94`).
- [x] **AC-5 — Release closure.** `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` piped to `.venv/bin/pip-audit --disable-pip -r …` → `No known vulnerabilities found`; the export contains no `hf-xet` and no `sqlite-vec` line (unchanged closure).
- [x] **AC-6 — Frozen run.** One detached `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=<dir>` at `e39da94` (or the latest flight commit): `^RESULT: PASS`, all eight doctor gates `OK`, task `succeeded`, installer size recorded against 134,790,292 bytes (expected within a few hundred KB — no closure change; the new `the_one/knowledge/` modules are pure Python). A failure inside this flight's files is iterated as a diagnostic (DD-11); one outside them is raised to the operator.
- [x] **AC-7 — Mission artifact.** In `mission.md` Open Questions: the `parent_id` question and the skipped-files question are checked `[x]` with a one-line "Resolved in Flight 3 (DD-2 / DD-3)" note; a new open question records the Windows 1M `usearch` build and incremental-upsert re-measure (Flight 2 debrief Recommendation 5, Flight 3 reconnaissance R6) as needing a real corpus of that size.
- [x] **AC-8 — Documentation check (workflow Phase 3).** `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md` reflect the four routes, operator-only registration, the resume behaviour and the walk rules (landed in Legs 1–3; verified, not re-written); `README.md` and `docs/windows-install.md` need no change (no new doctor gate, no new command).

## Verification Steps

- AC-1: the Developer's report in the flight log.
- AC-2: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8485/api/live` → `200`; `ss -ltn | grep -c ':8484 '` → `0` throughout.
- AC-3: the run log's `**Status**: pass`.
- AC-4: `make lint`; `make test-unit` (foreground, ≥ 900 s budget).
- AC-5: the two commands above; `grep -c "hf-xet\|sqlite-vec" <export>` → `0`.
- AC-6: `grep -E '^RESULT: (PASS|FAIL)' <log>`; `grep -E '^(succeeded|failed|errored|aborted)$' <log>`; `ls -l <dir>/the-one-setup-*.exe`.
- AC-7/AC-8: read the files.

## Implementation Guidance

1. Premise audit (Developer spawn, read-only on code, may edit the spec).
2. In parallel, launch the frozen run detached and run `pip-audit`
   (independent of the instance).
3. Start the dev instance; run the behavior test via the skill; tear the
   instance down.
4. `make lint`; then `make test-unit` alone.
5. Artifact edits; flight-log entry; leg `completed`; commit
   (`flight/3: verify-integration — …`) and push; PR checklist updated.

## Edge Cases

- **Build fails on a Windows-only path** (the walk's `os.scandir` and
  `os.replace` are exercised by the doctor only indirectly — no new probe):
  a `RESULT: FAIL` names the gate; iterate per DD-11.
- **Behavior Step 10 races the restart**: the spec waits for `/api/live`
  before polling; if the worker has already finished before the first
  poll, the assertion still holds (`indexed_at` later than
  `alpha_indexed_at`).
- **Leftover dev instance from a prior session on 8485**: `make down
  THE_ONE_PORT=8485` first; the probe above says none exists today.

## Files Affected

- `tests/behavior/kb-folder-index-round-trip.md` (status / corrections)
- `tests/behavior/kb-folder-index-round-trip/runs/*.md` (new)
- `missions/24-knowledge-bases/mission.md`
- `missions/24-knowledge-bases/flights/03-folder-registration-and-indexing/flight-log.md`

## Citation Audit

Checked at `e39da94` on 2026-09-15: `Makefile:34-38` (`THE_ONE_PORT`, PID
and log file names), `ci/tasks/windows-installer-build.yml:4-13` and
`:110-112` (platform, inputs/outputs, the three by-name needles),
`mission.md:304-310` (the two open questions). All present.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
