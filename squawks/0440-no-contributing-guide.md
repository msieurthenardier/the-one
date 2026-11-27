# Squawk 0440: no contributing guide requires the Mission Control plugin

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: 2026-11-27

## Report

The repository has no contributing guide. The README's "How it was built" section describes Flight Control but never says an outside contributor must use it. PR #393 (Mission 38 Flight 1, an outside contribution) was built without the Mission Control plugin: no leg specs, flight briefing or debrief, no independent Reviewer, and no `scripts/run-tests.sh` gate (it was run on macOS with bare pytest). The operator will close #393 and wants the rule written down first, so the closing comment can link to it.

Add:
- `CONTRIBUTING.md` at the repo root: every contribution goes through the Mission Control plugin, with the full artifact set, or the PR is closed; how to install the plugin and where to start; open an issue first; host requirements and the required gate; a short summary of the safety rules.
- A short "Contributing" section in `README.md` linking to it.
- `.github/pull_request_template.md` with checkboxes for the artifacts and the gate run.

## Evidence
- No `CONTRIBUTING.md` and no `.github/pull_request_template.md` exist (`ls *.md .github`).
- `README.md` "How it was built" and "Developing": no contribution requirement.
- PR #393 head `d84ad6b4`: `missions/38-ui-ux-polish/flights/01-narrow-window-layout/` has only `flight.md` and `flight-log.md`; no `legs/`, `flight-briefing.md` or `flight-debrief.md`. Its flight log records bypassing `scripts/run-tests.sh` because macOS Bash 3.2 lacks `declare -A` (`scripts/run-tests.sh:67`) and `setsid`.
- Plugin install, per the plugin README: `/plugin marketplace add msieurthenardier/mission-control`, then `/plugin install mission-control@flight-control`.

## Corrective Action
Added three docs, no code. `CONTRIBUTING.md` (repo root) states the rule (plugin-only, artifacts and independent Reviewer required, otherwise closed), the three routes with their artifact sets, plugin install and preflight-check, reading order, open-an-issue-first, host requirements and gate (Linux or WSL2; Bash 4 and `setsid`), and a short safety summary linking to `CLAUDE.md`. It is short and links out rather than copying `CLAUDE.md`. `README.md` gained a three-sentence "Contributing" section before "Developing". `.github/pull_request_template.md` carries a route line and checkboxes for plugin use, artifacts, Reviewer sign-off, gate run and ruff.

Review fix: removed an unsourced "not mergeable" sentence from "Talk first"; added a clause that `.flightops/` is committed, so a fresh clone does not run `init-project`; corrected the "Talk first" sentence on agreement gates to cover sorties (a sortie's charter takes the mission's place), sourced from the phase gates in `.flightops/FLIGHT_OPERATIONS.md`.

## Verification
- Artifact names, routes and branch conventions checked against `.flightops/ARTIFACTS.md` and `FLIGHT_OPERATIONS.md`; `declare -A` and `setsid` confirmed in `scripts/run-tests.sh`; safety rules and `THE_ONE_TEST_NETNS` wording checked against `CLAUDE.md`.
- Every relative link in the new and changed docs resolves (`ls`).
- Re-run after the review fix: `tests/test_shell_write_hook.py`, `test_release_notes.py`, `test_packaging_linux_hook_pin.py`, `test_packaging_locked_closure.py`, `test_gleepglorp_guide.py` together: 239 passed. No test pins the repo README's content. No browser lanes (docs only).

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; docs only, no security-sensitive surface), three cycles
**Verdict**: confirmed.
- Cycle 1: not confirmed. Blocking: an unsourced "a flight from a mission not on `main` is not mergeable" rule; removed. Non-blocking: test counts re-run; init-project clause added.
- Cycle 2: confirmed. Non-blocking N2 (the "Talk first" agreement sentence ignored sorties) fixed. N1 (Linux or WSL2 host) accepted: it is in this squawk's Report and follows from `scripts/run-tests.sh` needing `declare -A` and `setsid`.
- Cycle 3: confirmed. Optional note on "before any design starts" accepted as written: the README's "How it was built" uses the same wording.

**Commit**: `squawk/0440: ...` on squawk/0440-contributing-guide
