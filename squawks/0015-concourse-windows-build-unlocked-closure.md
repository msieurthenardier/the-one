# Squawk 0015: Concourse Windows build still installs an unlocked dependency closure — squawk 0009's fix reached only the GitHub release path

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
