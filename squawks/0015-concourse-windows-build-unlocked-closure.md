# Squawk 0015: Concourse Windows build still installs an unlocked dependency closure — squawk 0009's fix reached only the GitHub release path

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

Squawk 0009 fixed `.github/workflows/windows-installer.yml` to install the locked
closure (`uv export … | pip install -r`, then `pip install -e . --no-deps`) so the
frozen app ships the exact tested dependency set. The Concourse task that builds the
Windows installer on every push to `main` — `ci/tasks/windows-installer-build.yml` —
still runs `pip install -e ".[gui,all-llms]"`, re-resolving ranges at build time. No
unlocked artifact reaches a user (official releases come only from the tag-gated
GitHub path, and the Concourse artifact goes to a local minio bucket), but the
every-push gate — including its frozen `doctor` smoke — now verifies a different
closure than the one that ships, so it can go green on a commit the release build
would fail, or vice versa. Nothing guards against a third packaging entry point
repeating the pattern. Found by the 2026-08-27 maintenance inspection (E1).

Fix: port the same `uv export --no-dev --no-emit-project --extra gui --extra all-llms`
+ `pip install -r` + `pip install -e . --no-deps` sequence into the Concourse task, and
add a small guard test (grep over `ci/`, `.github/`, `packaging/`, `Makefile`) that
fails if any packaging entry point installs `.[gui,all-llms]` outside the locked
export.

## Evidence

- `ci/tasks/windows-installer-build.yml:30` — `& $py -m pip install -e ".[gui,all-llms]" --quiet`
- `.github/workflows/windows-installer.yml:43-54` — the squawk-0009 fix and its
  rationale comment ("install the LOCKED closure, not a fresh resolve")
- `ci/README.md:5` — the GitHub `v*`-tag path "still owns official releases";
  `packaging/windows/README.md:176-183` — Concourse is the day-to-day build, minio only
- `ci/the-one.pipeline.yml` — `build-windows-installer` triggers on every `main` commit

## Corrective Action

Ported the squawk-0009 locked-closure sequence into the Concourse task:

- `ci/tasks/windows-installer-build.yml` step `[2/6]` no longer runs
  `pip install -e ".[gui,all-llms]"` (a fresh resolve). It now installs `uv`,
  runs `uv export --no-dev --no-emit-project --extra gui --extra all-llms
  --format requirements-txt > release-requirements.txt`, `pip install -r
  release-requirements.txt`, then `pip install -e . --no-deps` — the same
  closure `.github/workflows/windows-installer.yml` installs and the same one
  `pr-lint.yml`'s pip-audit job audits — before installing `pyinstaller`. Kept
  the existing `& $py -m pip ...` PowerShell idiom, `--quiet` flags, and the
  `[N/6]` echo numbering unchanged. Added a comment referencing squawk 0009
  and squawk 0015, mirroring the rationale comment in the GitHub workflow.
- Added `tests/test_packaging_locked_closure.py`: a plain-text (no YAML
  parsing) guard with two rules — (1) an explicit allowlist of the two
  artifact-producing entry points (`ci/tasks/windows-installer-build.yml`,
  `.github/workflows/windows-installer.yml`) that must contain the
  locked-closure sequence, and (2) a denylist scanning every executable
  packaging/CI entry point (`ci/tasks/*.yml`, `.github/workflows/*.yml`,
  `packaging/**`, `Makefile`, `scripts/**`, restricted to executable
  extensions — `.md` docs and the PyInstaller `*.spec`'s embedded manual-build
  docstring are excluded, since neither is executed by any automated
  packaging entry point) for a fresh-resolve install of the `gui` extra
  specifically, unless that file also carries the locked sequence. `[gui`
  is a deliberately narrow trigger — no test/dev install (`.[all-llms,dev]`,
  including `ci/tasks/windows-tests.yml`'s source-checkout test install) ever
  requests it, so those are correctly left unflagged. Guards against a third
  packaging entry point repeating the pattern, per the squawk's report.
- Checked `ci/README.md` and `packaging/windows/README.md`: neither describes
  the Concourse task's install step in reproducible detail — `ci/README.md`
  only references the task file by name in its lane table, and
  `packaging/windows/README.md`'s "Where the installer is built" section
  (~176-183) says only that Concourse "runs the same freeze + packaged-smoke,"
  with no install command to correct. The README's `pip install -e
  ".[gui,all-llms]"` snippet (~37-38) is a manual native-Windows developer
  build recipe, not a description of the Concourse pipeline, so it was left
  unchanged. No README edits made.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_packaging_locked_closure.py -x --timeout 60` — 2 passed against
  the fixed tree.
- Confirmed the guard is load-bearing (would have caught the pre-fix state):
  built a scratch copy of the repo's `ci/`, `.github/`, `packaging/`,
  `scripts/`, `Makefile` alongside the new test file, restored the pre-fix
  `ci/tasks/windows-installer-build.yml` into it via `git show
  HEAD:ci/tasks/windows-installer-build.yml`, and ran the guard test directly
  against that scratch tree — both rules failed as expected: rule 1
  (`test_artifact_producing_entry_points_use_locked_closure`) reported the
  file missing the locked-closure sequence, and rule 2
  (`test_no_unlocked_gui_extra_install_outside_locked_files`) reported the
  exact unlocked line (`ci/tasks/windows-installer-build.yml:30: & $py -m pip
  install -e ".[gui,all-llms]" --quiet`). Scratch copy deleted afterward.
- `make lint` — `ruff check the_one/ tests/` — all checks passed.
- `make format-check` — `ruff format --check the_one/ tests/` — 443 files
  already formatted (no changes needed).
- `ruff format`/`ruff check` run directly on the new test file only — already
  formatted, all checks passed.
- Not run (per instruction): `fly`/`ci/set-pipeline.sh` — the Concourse
  pipeline update is applied by the operator, not by this squawk.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `5cf3cac` on `squawk/turnaround-2026-08-27` — PR #178
