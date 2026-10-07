# Leg: servicing

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

Complete the five servicing squawks that carry the mission's documentation and apparatus
debt:
- **0121:** the behavior crew file's CDP recipe and concurrent-run rules;
- **0122:** the wording of five specs from the Flight 4 close gate;
- **0123:** the wording of `windows-window-chrome`;
- **0124:** a test pinning the Windows helper's closure commands;
- **0125:** the pywebview 6.x upgrade-blocker note.

## Context

- **Each squawk file names its Report, Corrective Action and Verification.** Follow them;
  they are the spec. In each, write the Corrective Action and Verification and mark it
  `completed`, with the commit reference "pending the Flight 6 legs 1–3 commit".
- **0121's file** (`.flightops/agent-crews/behavior-tests-execution.md`) is
  project-modifiable scaffolding read by the behavior-test skill. It must keep its
  `## Crew`, `## Interaction Protocol` and `## Prompts` sections, and every prompt stays a
  fenced block. The rules to add are listed in the squawk and were carried by hand in
  Flights 4 and 5:
  - one long-lived driver per run, or a fresh Chromium process and `--user-data-dir` per
    variant, driving its persistent default context, never a `new_context()` that a
    short-lived script owns;
  - PIDs recorded at launch and stopped by PID only, never `pkill -f` or `killall`;
  - the report-file hand-off (`step-N[-variant]-report.json` without `executor_notes`,
    which the Validator reads);
  - the per-run checkpoint ledger for concurrent runs;
  - **added from Flight 5:** "verify every evidence path you list exists before reporting".
- **0122 and 0123 are wording only.** Do not change any expectation's meaning. Each edited
  spec gets an `Updated` line. Re-read each edited step against the run log it came from.
  - **The sources** are the Validator closings in the run logs the squawks cite: the five
    Flight 4 runs `2026-10-06-06-01-26`, and `windows-window-chrome/runs/2026-10-06-20-06-24.md`.
  - **The `list-and-detail` exception.** Leg 1a re-authored `list-and-detail.md` step 2.
    It is not one of 0122's five, so do not touch it here.
- **0124:** keep the pinned constant beside the existing `NEEDLES` pin
  (`tests/test_windows_test_copy.py::test_needles_match_ci_foreach_list`).

## Acceptance Criteria

- [ ] **0121.** The crew file adds the rules above in its "Run rules" rationale list
  **and** in the Executor and Validator Initial prompts where each acts, and keeps its
  required sections and fenced prompts. A quick parse check (each `###` prompt subsection
  under `## Prompts` has a fenced block) passes.
- [ ] **0122.** Every wording item the squawk lists is applied to:
  - `jump-to-palette.md`, including step 9 no longer naming `studio-description` as a
    testid;
  - `shell-navigation-smoke.md`;
  - `chat-roundtrip.md`;
  - `start-a-chat.md`;
  - `workbench-navigation.md`.

  Each has an `Updated` line. `grep -n "studio-description" tests/behavior/*.md` shows no
  step naming it as a testid.
- [ ] **0123.** Every item in the squawk is applied to
  `tests/behavior/windows-window-chrome.md`:
  - step 7's flush poll (click a different preference first, or poll after step 6's last
    change, and the verdict when the outcome is observed but the flush is not);
  - the splash statistic as the frame mean or body, with `no-window` and
    `covered_by_tree` frames not judged;
  - step 5's ±8 tolerance;
  - step 4 anchored on `frame_bounds`;
  - a required capture at steps 3 and 9;
  - step 9's minimize judged on the rect, own window A re-shown before a late `front`, and
    formula-only coordinates;
  - step 1's "the run creates none" and a 300-frame series.

  A `Revised` line is added.
- [ ] **0124.** The closure commands live in a module constant in
  `scripts/windows_test_copy.py`. A new test parses the `uv export` argument list and the
  two `--no-deps` installs from `ci/tasks/windows-installer-build.yml` and asserts they
  equal the constant. Changing either side alone fails it.
- [ ] **0125.**
  - `the_one/agents.md`'s Window chrome block gains an "upgrade blocker" note naming
    `update_title_bar_theme()` and the re-check a pywebview 6.x upgrade needs.
  - `pyproject.toml`'s `gui` pin gets a matching comment.
  - `grep update_title_bar_theme the_one/agents.md pyproject.toml` finds both.
- [ ] **All five squawk files** are completed per `.flightops/ARTIFACTS.md`'s squawk
  conventions.
- [ ] **Gates.**
  - `ruff check` and `ruff format --check` pass.
  - `tests/test_windows_test_copy.py` passes, and `TEST_TIMEOUT=3000 make test-unit`
    passes.
  - No product code changes in this leg.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_windows_test_copy.py -x
  --timeout 60`.
- The greps above. Re-read each edited spec step against its run log.

## Implementation Guidance

1. **Read each squawk in full first.**
2. **0124 and 0125** (code and docs).
3. **0121** (the crew file).
4. **0122 and 0123** (the specs), one spec at a time, checked against its run log.
5. **Squawks and gates;** then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A wording item that would change an expectation's meaning:** skip it, and say so in
  the squawk's Corrective Action.
- **0123's step 7 rewrite** must keep the step's intent: the dark preference survives a
  hard stop, and the relaunch shows no light frame.

## Files Affected

- `.flightops/agent-crews/behavior-tests-execution.md`.
- `tests/behavior/{jump-to-palette,shell-navigation-smoke,chat-roundtrip,start-a-chat,workbench-navigation,windows-window-chrome}.md`.
- `scripts/windows_test_copy.py`, `tests/test_windows_test_copy.py`.
- `the_one/agents.md`, `pyproject.toml`.
- Squawks 0121–0125; the flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
