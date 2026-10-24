# Leg: hosted-build-prepare

**Status**: ready
**Flight**: [Linux packages](../flight.md)

## Objective
Write `.github/workflows/linux-packages.yml`: a dispatch-only (and `workflow_call`-able) GitHub Actions workflow that builds both Linux packages in the pinned build container and runs the container gate suite on the bare Ubuntu 26.04 and Debian 13 images under `xvfb` (DD10).

Rehearse every script it calls by executing it locally, exactly as the runner will (debrief recommendation 1). Then prepare the `.github/`-only stub that must reach `main` before a manual run is possible. The Flight Director does the outward steps (push, PR, merge, dispatch). The Developer does not.

## Context
- **Flight DDs:** DD10 (the workflow, the matrix, the budget, the rehearsal, the stub PR), DD2 (the pinned container), DD8 (the check suite at `packaging/linux/checks/`).
- **Flight 1 lessons:**
  - every hosted failure in Flight 1 was first-run harness code: directory creation order, PowerShell variable case, env restore;
  - a workflow must exist on the default branch before `gh workflow run --ref <branch>` can run the branch's copy;
  - the macOS probe's layered caps and fail-on-missing-summary pattern worked (`.github/workflows/packaging-probe-macos.yml`, the house style for this file).
- **State after legs 1-8** (committed at the review checkpoint before leg 6):
  - `packaging/linux/build.sh [--version X]`: host staging (`packaging/stage.py`, `git rev-parse`; on the runner the checkout is a normal repo), host `uv export --frozen`, `docker build` of `m32/linux-build:f2`, a container freeze with audit and wrap;
  - `packaging/linux/checks/gates.sh <candidate> <deb|appimage> <distro> <image> --n VER --n1 VER [--display wslg|xvfb] …`, with the images built from `packaging/linux/checks/images/*.Dockerfile` (targets `bare` and `baseline`);
  - `score.py` writes `score.json` and a PASS/FAIL line;
  - `packaging/linux/checks/check.sh` is a forwarding shim that this leg deletes.
- **Runner facts to verify, not assume** (record them in the leg's flight-log section):
  - `ubuntu-24.04` has Docker and about 14 GB of free disk;
  - Linux minutes bill at 1×;
  - artifact storage has room for two packages of about 140 MB each at short retention: check `gh api /repos/msieurthenardier/the-one/actions/cache/usage` and the account's artifact usage if visible, and record what is visible.
- **The hosted matrix (DD10):** both formats × both distros' **bare** images, with `--display xvfb`:
  - strict `doctor`, pinned and unpinned;
  - G2 and G4;
  - G3 on the `.deb` runs (its `Depends` bring in WebKitGTK);
  - the AppImage on bare images proves DD14's browser fallback, and `doctor` passing with the "no desktop GTK" desktop-shell line (leg 2).
  - The upgrade check needs an N/N+1 pair. The hosted job builds only the one version it was asked for, so `gates.sh` gains a single-version mode (`--n1` omitted, so the upgrade check is reported as `upgrade=N/A (single version)`). Upgrade stays proven locally and in the VMs.

## Inputs
- `packaging/linux/build.sh`, `build-inner.sh`, `build.Dockerfile`, `packaging/linux/checks/*`, `packaging/stage.py`, `packaging/render.py`
- `.github/workflows/packaging-probe-macos.yml` (style), `.github/workflows/windows-installer.yml` (release-closure audit, for reference only; not wired here)
- `$HOME/the-one-m32-build/tools/actionlint-1.7.7/actionlint`, `shellcheck-0.10.0`

## Outputs
- **`.github/workflows/linux-packages.yml`** (the flight branch's full version):
  - **Header comment:** purpose, how to dispatch (`gh workflow run linux-packages.yml --ref flight/02-linux-packages [-f version=…]`), the cost caps, "publishes nothing, uses no secrets", and the Flight 4 note that `workflow_call` is the release workflow's entry point.
  - **Triggers:** `on: workflow_dispatch` (input `version`: optional, default empty, meaning `__version__`) and `workflow_call` (the same input). No `push`, `pull_request` or `tag` trigger.
  - `permissions: contents: read`; `concurrency: {group: linux-packages, cancel-in-progress: false}`.
  - **Job `build`** (`runs-on: ubuntu-24.04`, `timeout-minutes: 45`):
    - checkout, `fetch-depth: 0` (`SOURCE_DATE_EPOCH` uses the last commit);
    - runner evidence (`lsb_release`, `docker version`, `df -h`, `nproc`, `free -g`) into the logs;
    - `uv` installed at the pinned **0.10.0**, the same as the host's `uv export` (`pip install uv==0.10.0`, as the macOS probe does);
    - `packaging/linux/build.sh --version "$V"`, under a step `timeout-minutes: 30`, with `M32_BUILD=$RUNNER_TEMP/m32-build`;
    - record the build log's audit line and the package sha256s into `SUMMARY.txt`;
    - upload the two packages (`retention-days: 3`) and the logs (`retention-days: 7`) as separate artifacts.
  - **Job `checks`** (`needs: build`, `runs-on: ubuntu-24.04`, `timeout-minutes: 30`):
    - matrix `distro: [ubuntu-26.04, debian-13]` × `format: [deb, appimage]`, `fail-fast: false`, `max-parallel: 4`;
    - download the packages;
    - build the `bare` image for the distro from `packaging/linux/checks/images/<distro>.Dockerfile`, with a step timeout;
    - `packaging/linux/checks/gates.sh A <format> <distro> bare --n "$V" --display xvfb --pkgdir …`;
    - upload the evidence;
    - a final step fails the job on any FAIL or a missing `score.json`.
  - **Job `summary`** (`needs: [build, checks]`, `if: always()`): collects the score lines into `$GITHUB_STEP_SUMMARY`, and fails if any score line is missing.
  - **Every action pinned:** `actions/checkout@v5`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`, matching the repo's existing usage.
- **`gates.sh` single-version mode:** `--n1` optional. Without it, the upgrade steps are skipped and `score.py` reports `upgrade=N/A`. Covered by `tests/test_packaging_score.py`.
- **`packaging/linux/checks/check.sh`** deleted (leg 8's shim), and any reference to it updated.
- **The stub for `main`:** `.github-stub/linux-packages.yml`, written to the leg's **evidence dir**, not committed in the repo. It has:
  - the same `name`;
  - the same `on:` block (`workflow_dispatch` with the same input, plus `workflow_call`), so `--ref` can run the branch's copy;
  - `permissions: contents: read`;
  - one trivial job that echoes "the real steps live on the flight branch; dispatch with --ref".

  Its `on:` block must be byte-identical to the flight branch's: GitHub validates dispatch inputs against the default branch's file. The Flight Director opens the PR with it.
- **Rehearsal by execution, recorded in the flight log:**
  - `actionlint` clean on the workflow, and on the stub;
  - `shellcheck` clean on every script the workflow calls, and on the workflow's `run:` blocks (extract them, or rely on `actionlint`'s shellcheck integration with the pinned `shellcheck` on `PATH`);
  - **the exact command sequence the jobs run,** executed locally in a fresh shell with the runner's env shape (`RUNNER_TEMP` set to a scratch dir, `GITHUB_ENV`/`GITHUB_STEP_SUMMARY` pointed at scratch files):
    1. the build step;
    2. the summary step;
    3. one `checks` matrix cell per format (`deb`/`debian-13`, `appimage`/`ubuntu-26.04`), with `--display xvfb` and no WSLg;
    4. the fail-on-FAIL step, fed both a passing and a doctored failing score, which must fail;
    5. the summary job's script.
  - A dry run with `set -u` and `set -o pipefail` everywhere.

## Acceptance Criteria
- [ ] **AC1** — the workflow file exists as specified.
  - `actionlint` is clean.
  - Its triggers are only `workflow_dispatch` and `workflow_call`.
  - No `secrets.` reference.
  - Every job and step has a timeout.
  - Concurrency is set.
  - Artifact retention is ≤ 7 days, and 3 for packages.
- [ ] **AC2** — `gates.sh` single-version mode works and is unit-tested (`upgrade=N/A`). `check.sh` is deleted, with no references left (`git grep -n "checks/check.sh"`).
- [ ] **AC3** — the local rehearsal executes every job's commands in the runner's env shape:
  - the build produces both packages, with the audit line PASS;
  - the two matrix cells pass under `--display xvfb` with no WSLg socket mounted (assert `/mnt/wslg` is not mounted in the cell's `docker run`);
  - the fail step fails on a doctored FAIL and passes on PASS;
  - the summary script renders.

  The transcripts are in the evidence dir and summarized in the flight log.
- [ ] **AC4** — the stub exists in the evidence dir, its `on:` block is byte-identical to the branch file's (a `diff` of the extracted `on:` blocks is empty), and `actionlint` is clean on it.
- [ ] **AC5** — the runner facts and budget are recorded: an estimated minutes per run (build plus the four cells), the 6-dispatch cap, and the artifact storage seen.
- [ ] **AC6** — gates:
  - `make test-unit` passes (12 skips);
  - `ruff` clean;
  - no `m32-` container left running;
  - no 8484/8485;
  - the operator data dir untouched;
  - only `.github/workflows/linux-packages.yml`, `packaging/linux/checks/*`, tests and this flight's log changed.

## Verification Steps
- AC1, AC4: `actionlint`; `grep -n "secrets\.\|on:" -A8`; the `diff`.
- AC2: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_packaging_score.py -x --timeout 30`; `git grep`.
- AC3: the rehearsal transcripts.
- AC5, AC6: the flight log; the commands named.

## Implementation Guidance
1. Add the single-version mode and delete the shim, with their tests.
2. Write the workflow, modelled on `packaging-probe-macos.yml`: the evidence step, the `SUMMARY.txt`, the last-step fail pattern.
3. Rehearse in a fresh shell with `RUNNER_TEMP=$HOME/the-one-m32-build/f2/runner-rehearsal` (outside the repo). Use the exact `run:` text from the workflow, by extracting it with a small script or by copying it carefully, and note which.
4. Write the stub, then diff the `on:` blocks.
5. Flight-log section `### hosted-build-prepare`: the rehearsal transcripts summary, any defect the rehearsal found and its fix (this is the point of the leg: Flight 1's three hosted failures would all have been caught here), and the runner facts.
6. **Do not** push, open a PR, merge, or dispatch. Report that the stub is ready. The Flight Director does those, with the operator's standing approval for this flight's `.github/`-only PR.

## Edge Cases
- **`SOURCE_DATE_EPOCH` on a shallow clone:** use `fetch-depth: 0`, or `git log -1 --format=%ct`, which works on depth 1 too. Verify which `build.sh` uses.
- **Docker layer caching on the runner:** none. The first build compiles PyGObject and pycairo, about 5-10 minutes. Within budget; record it.
- **The images' `apt-get update`** needs network at check time. It is fine on the runner. Mirror flakiness is environmental: let the cell retry once (a bounded loop in the script, not `continue-on-error`).
- **Matrix cells share no Docker cache.** Each builds its own bare image (about 1-2 minutes).
- **`gates.sh` uses fixed container names** (`m32-gate-…`). On a runner each cell is its own VM, so there is no clash.

## Files Affected
- `.github/workflows/linux-packages.yml` (new)
- `packaging/linux/checks/{gates.sh,gates-inner.sh,score.py,README.md}`, `packaging/linux/checks/check.sh` (deleted)
- `tests/test_packaging_score.py`
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section)

## Citation Audit
Checked against the worktree after leg 8 landed (uncommitted):
- `.github/workflows/packaging-probe-macos.yml`: `actions/checkout@v5`, `actions/upload-artifact@v4`, `pip install uv==0.10.0`, the `Paths` step writing `GITHUB_ENV`, the last-step `Fail on a failed or missing candidate`. Verified.
- `packaging/linux/checks/gates.sh`, with `--display`; `check.sh` is a shim (leg 8). Verified, per leg 8's report.
- `packaging/linux/build.sh`: `--version`; `M32_BUILD`. Verified (leg 7).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
