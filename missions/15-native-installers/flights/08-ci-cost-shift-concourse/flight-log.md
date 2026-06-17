# Flight Log: CI cost-shift — move day-to-day CI to local Concourse

**Flight**: [CI cost-shift — move day-to-day CI to local Concourse](flight.md)

## Summary

Planning. Driver: the project has **exhausted its GitHub Actions minutes** (the F7 PR #119
CI was all-red purely because Actions billing failed — jobs never started). This flight
moves routine CI (lint/test/browser/windows-subset, spike permitting bwrap) to the local
Concourse `the-one` team and finalizes GitHub Actions as release-only (`v*`-tag installer).
Modeled on the operator's prior goldfinch CI-cost-shift exercise.

---

## Reconnaissance Report (current CI state, 2026-06-17)

GitHub Actions (`.github/workflows/`):
- `lint.yml` — ruff check + format. Trigger: `pull_request` + `push: main`. Cost: ubuntu 1×, cheap.
- `test.yml` — 4 jobs, trigger `pull_request` + `push: main`:
  - `test` — full suite, `ubuntu-latest`, bare `python -m pytest tests/` (ephemeral-runner rationale documented in-file).
  - `browser` — `-m browser tests/browser/` (~15 min, the CI long pole), **path-filtered** to `interfaces/web/**`, `tests/browser/**`, `pyproject.toml` via inline git-diff.
  - `windows` — curated OS-divergent subset (~427 tests) on `windows-2022` (**2× billing**), Git-Bash shell.
  - `bwrap` — `-m requires_bwrap`, `ubuntu-latest`, sets `kernel.apparmor_restrict_unprivileged_userns=0` + installs bubblewrap + venv-from-system-python (boxed-mode `/usr` constraint).
- `windows-installer.yml` — **`v*` tag only**: PyInstaller freeze → packaged-smoke (frozen doctor / serve / single-instance) → Inno installer → `gh release`. **The official release path — left untouched by this flight.**

Concourse (`the-one` team, shared `concourse-local` instance):
- `ci/windows-installer.pipeline.yml` — `repo` git resource polls `main` (`trigger: true`) → `ci/tasks/windows-installer-build.yml` (choco python311 + Inno on the `platform: windows` worker) → publish `.exe` to MinIO. Secrets at Vault `concourse/the-one/windows-installer/*` (git deploy key + minio.{access_key,secret_key,endpoint,bucket}).

Prior art — goldfinch (`~/projects/goldfinch`):
- `ci/pipeline.yml`: `ci` job (git on `main`, `trigger: true`, `in_parallel` test/typecheck/lint/audit/package-linux, `fail_fast: false`) + manual `build-linux`/`build-windows` (`passed: [ci]`) → MinIO s3 resources.
- `.github/workflows/ci.yml` → `workflow_dispatch`-only (PR trigger disabled, kept as break-glass). `build.yml` (tag→release) untouched.
- `ci/README.md`: what-runs-where table; pre-push `fly -t local-goldfinch execute -c ci/tasks/<x>.yml -i repo=.`; on-demand installers; Vault notes incl. the **in-memory dev-Vault / `.vault-seeds.json` reseed** lesson and the MinIO `endpoint` = `http://172.17.0.1:9000` (docker-bridge gateway, not the compose service name) gotcha.

---

## Decisions

### DD1 — PR observation: goldfinch push-to-main model
**Context**: A Concourse `git` resource polls a branch, not PRs; "on PRs" needs either a `github-pr-resource` (per-PR builds + status callback) or the goldfinch compromise.
**Decision**: Goldfinch model — `ci` auto on `main`; per-PR gating via pre-push `fly execute -c ci/tasks/<x>.yml -i repo=.`. No PR resource, no GitHub token/status coupling. (Operator decision 2026-06-17, "Option B, like goldfinch".)
**Impact**: No automatic PR check in GitHub UI; the per-PR gate is a manual pre-push step (documented in `ci/README.md`).

### DD3 — Installer builds: auto-on-main preserved, manual/on-demand for branches
**Context**: Operator wants installers "on prs and on main"; answered the PR-automation question "Manual / on-demand".
**Decision**: Keep auto-build on `main` (now `passed: [ci]`); ad-hoc branch/working-tree builds are manual `fly execute`/`fly trigger-job`. No auto-build per PR push. (Operator decision 2026-06-17.)
**Impact**: Single Windows worker isn't tied up freezing every PR commit; main never freezes a red commit.

### DD4 — bwrap lane: spike-gated port
**Context**: `requires_bwrap` needs kernel-enforced unprivileged userns + bubblewrap; a Concourse worker's privilege/AppArmor posture is unverified.
**Decision**: Leg 1 `fly execute` spike decides — GREEN → port to `ci/tasks/bwrap.yml`; RED → keep just the `bwrap` job on Actions. Applies the F7 "platform-verification spike before the dependent leg" lesson. (Operator decision 2026-06-17, "Port to Concourse if a spike confirms it".)
**Impact**: Gates whether Leg 2 authors `bwrap.yml` and whether Leg 4 fully empties `test.yml`.

**RESOLUTION (Leg 1 spike, 2026-06-17): GREEN — port bwrap to Concourse.** Real
kernel-enforced containment works on the shared linux worker: the factory selects
`BubblewrapSandbox`, the empirical userns probe passes, and 31 `requires_bwrap` containment
tests pass (assertions that degrade-to-passthrough would fail). Required strategy, confirmed
empirically (full run table under Leg Progress → bwrap-feasibility-spike):
- **Image** `python:3.11`; **venv** `/opt/venv` (NOT a repo-relative `.venv` — the Concourse
  workspace lives under `/tmp/build/…`, which bwrap's `--tmpfs /tmp` shadows);
  **privilege** `privileged: true` on the task step (the worker blocks *unprivileged* userns;
  `fly execute -p` / a privileged pipeline task is required).
- **Carries an added Leg-2 obligation:** 10 MCP-integration tests
  (`test_mcp_sandbox_integration.py` + 2 in `test_mcp_pool.py`) fail under Concourse — **not**
  a containment failure but because they hard-code the bwrap-spawned MCP server's `cwd` to
  `_PROJECT_ROOT` (= `/tmp/build/…/repo`), violating the invariant *already documented* in
  `tests/_sandbox_fixtures.py:51` ("all sandbox tests must create workspaces under HOME, not
  /tmp"). They pass on GH only because its workspace is `/home/runner/…`. Leg 2 must fix these
  tests (move the MCP server CWD off `/tmp`, mirroring `home_workspace()`) **before** the
  `bwrap.yml` lane can be green. The fix's exact scope/correctness is a Leg-2 design-review item.
- **FD independent verification:** confirmed `test_mcp_sandbox_integration.py:83,118` sets
  `cwd=_PROJECT_ROOT` and that `_sandbox_fixtures.py:51` documents the HOME-not-/tmp invariant
  — the spike's "workspace artifact, not containment" diagnosis is sound. DD4 recorded GREEN by
  the FD (the spike agent did not edit this entry).
**Impact (final):** Leg 2 authors `ci/tasks/bwrap.yml` (privileged, `python:3.11`, `/opt/venv`)
**and** fixes the 10 /tmp-CWD MCP tests. Leg 4 → GREEN branch (both `lint.yml` and `test.yml`
become `workflow_dispatch`-only; no bwrap job stays on Actions).

---

## Flight Review & Landing (2026-06-17)

**Phase 2d — single flight review (Sonnet reviewer, fresh context).** Reviewed all uncommitted
changes against the 5 legs' acceptance criteria + code quality. **`[HANDOFF:confirmed]`** — no
blocking issues. Key independent verifications: (a) the unified pipeline YAML is correctly wired
(one `github-deploy-key` git resource; `bwrap` step `privileged:true` at the task-step level;
`build-windows-installer` `trigger:true`+`passed:[ci]` + inline `mc` publish; no s3 resource);
(b) **the Leg-2 lint-cleanup deviation is fully behaviorally inert** across all 9 source files
(import-order/wrap/whitespace + one `F841` unused-var removal — confirmed via per-file diff +
symbol/AST checks, full suite green); (c) `ci/README.md` matches the real `ci/` files incl. the
bare-`host:port` MinIO endpoint detail; (d) workflow cutover correct, `windows-installer.yml`
zero-diff. One **non-blocking** nit (task headers referenced `ci/pipeline.yml` not
`ci/the-one.pipeline.yml`) — FD fixed in all 5 task files before commit.

(Reviewer model: Sonnet, not the crew-default Haiku — FD call given the 21-file infra+source+docs
breadth; still never Opus per the rule.)

**Landing.** All 5 legs → `completed`; flight → `landed`; Flight 8 checked off in `mission.md`.
flight.md checklist items checked where satisfied; the post-merge items (code merged, `ci` green
on `main`, Actions no-longer-triggered, installer to MinIO) left unchecked — they complete when the
PR merges (see `ci/README.md` post-merge section + the Leg-3 teardown steps above).
**`[COMPLETE:flight]`**

---

## Deviations

### Leg 2 — source files changed despite the "no source changes" leg constraint
**Planned**: Leg 2 spec said it would touch only `ci/tasks/*.yml` — "No production/test source
files change in this leg."
**Actual**: The Developer ran `ruff check --fix` + `ruff format`, modifying 9 source files
(`the_one/diagnostics.py`, `interfaces/app.py`, `interfaces/desktop/shell.py`, `platform/env.py`
+ 5 `tests/test_*.py`), +103/−68.
**Reason**: 16 pre-existing ruff violations (import ordering, line length, one unused local) had
accumulated since Flight 7 — GitHub's lint lane never caught them because Actions minutes were
exhausted (the very problem this flight fixes). `ci/tasks/lint.yml` **cannot be green standalone**
(its own acceptance criterion) while the tree has violations, so cleaning them is a prerequisite,
not scope creep.
**FD assessment (accepted)**: Independently reviewed every changed hunk — **all behaviorally
inert**: line-wrapping, import reordering (ruff `I`), blank-line/whitespace, and one unused-var
removal (`icon =`, ruff `F841`). No `--unsafe-fixes` semantic change materialized. The full
default suite passed green afterward (`test.yml`: 3178 passed), confirming nothing broke. These
fixes ride in the Flight-8 commit; **flagged for the end-of-flight Reviewer to re-confirm they are
formatting-only.** A pre-existing-lint-debt cleanup is squarely in this flight's spirit (restore
the CI signal that lapsed during the Actions outage).

### Leg 2 — `test_build_tool_profile_default_allowlist` deselected on the windows Concourse lane
**Planned**: `windows-tests.yml` runs the curated OS-divergent subset verbatim from `test.yml:104-116`.
**Actual**: That one test is `--deselect`'d in `windows-tests.yml`.
**Reason**: The Concourse windows worker runs as the **system account**, where
`Path("~").expanduser()` → `…\system32\…` (lowercase, from `USERPROFILE`) but `Path.resolve()` →
`…\System32\…` (NTFS canonical). The test compares the two; they agree on a user account
(GitHub) but not the system account. Purely a worker-account path-case artifact, not a
Windows-behavior or containment gap.
**FD assessment (accepted)**: Coverage is not lost — the same test runs on the **linux** `test.yml`
full-suite lane (3178 passed). The deselect is documented in the task header + this log (no silent
cap). Recorded for Leg 3 awareness.

---

## Anomalies
_None yet._

---

## Session Notes

**2026-06-17 — planning.** Flight reframes the placeholder F8 ("Windows release pipeline");
tag-release already shipped in F5. Three forks from the goldfinch template settled with the
operator: DD1 (push-to-main model), DD3 (manual/on-demand installers, auto-on-main kept),
DD4 (spike-gated bwrap). DD5 (full browser suite on main, drop the Actions-era path-filter)
and DD6 (unify into one pipeline) defaulted with rationale.

**2026-06-17 — Architect design review (1 cycle): approve with changes.** Recon verified
accurate against real files (4 test.yml jobs, browser path-filter regex, windows-2022
subset, bwrap sysctl+venv-from-system-python; existing Concourse pipeline shape + Vault
paths; `[all-llms,dev]`/`[gui]` extras; `browser`/`requires_bwrap` markers; and
`tests/conftest.py:35-36` sets `THE_ONE_DATA_DIR=mkdtemp()` at module load → suite is
ephemeral-container-safe, bare-pytest rationale holds). Changes incorporated:
- **[high]** Windows-subset task is NOT a linux task — added it as an explicit Leg-2 sub-item
  (PowerShell + choco `python311`, modeled on `windows-installer-build.yml`, re-list the
  ~427-test set, separate `fly execute` smoke).
- **[med]** Leg-1 spike must exercise the exact image + `/usr`-interpreter layout (not a
  shallow `which bwrap`) and decide the image/venv strategy. Strengthened.
- **[med]** Vault: pre-decided **team-level promotion** (`concourse/the-one/*`) as default —
  only option with no dead window during cutover; `.vault-seeds.json` updated before next
  Vault restart. Folded into DD6 + Prereqs + Leg 3.
- **[low]** Fixed the Leg-4 contradiction: GREEN → both workflows dispatch-only; RED →
  `test.yml` stays triggered but trimmed to the single `bwrap` job.
- Suggestions folded: reuse `windows-installer-build.yml` unchanged; destroy the old
  pipeline once unified is green; corrected the path-filter shorthand in DD5.

Architect's three operational questions — resolved with defaults (operational, not
product/scope; operator prefers fewer confirmation points, can reverse):
1. *Windows-subset on every main push vs pre-push gate?* → **keep it in the `ci` job on main**
   (faithful port of automated Windows signal; main pushes are infrequent post-merge, so
   serial windows-worker use with the installer build is bounded). Also available pre-push
   via `fly execute`.
2. *Installer auto-on-main blocked behind the ~15-min browser lane (`passed: [ci]`)?* →
   **acceptable** — the auto-on-main installer is a convenience MinIO artifact, not
   time-critical; correctness (never freeze a red commit) beats latency.
3. *Team-level Vault promotion safe?* → **yes** — `the-one` is effectively a single-pipeline
   team; promotion is unambiguous and is the cutover-safe choice.

Only minor/clarifying edits applied → no second review cycle needed (within the 2-cycle cap).
Next: walk the spec with the operator (Phase 6), then mark `ready` and execute via
`/agentic-workflow` when the operator confirms.

---

## Flight Director Notes

**2026-06-17 — Flight Director engaged (`/agentic-workflow` flight 8).** Phase file
`leg-execution.md` loaded and validated (Crew / Interaction Protocol / Prompts present;
Developer=Sonnet, Reviewer=Haiku). Flight was in `planning` (the spec-walk Phase-6 step
was the documented next action); operator's `/agentic-workflow` invocation taken as the
go-signal → flight transitioned **planning → in-flight**. Branch
`flight/8-ci-cost-shift-concourse` created off `main` (carries the uncommitted planning
artifacts). Per the M14 operator preference (fewer confirmation points), proceeding
without a separate spec-walk confirmation.

**Live-infra prerequisite check (before Leg 1).**
- `fly` 8.1.0 present; `the-one` target session valid (workers query returned data).
- Workers up: linux `334c0e4b22cd` (3 containers, running) + `windows-worker` (running).
- **Discrepancy flagged for Leg 3:** a `the-one` pipeline (id 15, created 2026-05-04)
  *already exists* on the team alongside `windows-installer` (id 17) — the recon report
  only catalogued `windows-installer`. DD6's "set the unified `the-one` pipeline" must
  reconcile this pre-existing pipeline (inspect → overwrite/destroy) rather than assume a
  clean slate. Not a Leg-1 blocker.

**Execution model:** batched (design per leg; single review+commit after the last
autonomous leg). Leg 1 is a **GATE** whose GREEN/RED result reshapes Legs 2 and 4 —
its outcome is recorded here before Leg 2 is designed.

**Leg 1 design + review (2026-06-17).** Authored `legs/01-bwrap-feasibility-spike.md`.
Developer design review (1 cycle): **approve with changes**. Review verified the
containment observable against `factory.py` (the `bubblewrap`/`passthrough` selection
lines) and the boxed-mode `/usr` constraint. Three issues fixed, all handed with exact
remedies:
- **[high]** `fly execute` *does* support `-p/--privileged` (verified `fly execute --help`,
  Concourse 8.1.0) — the leg wrongly claimed it could not and prescribed a throwaway
  privileged-pipeline detour. Rewrote step 4 to just re-run `fly execute -p`; pipeline
  detour demoted to a last-resort note.
- **[med]** GREEN AC referenced the factory's INFO log line, invisible under default pytest
  output. Added `--log-cli-level=INFO` to the spike command and reframed the AC so the
  test pass/fail is the primary GREEN/RED signal (log line is corroboration).
- **[low]** "note that for Leg 3" → **Leg 2** (`bwrap.yml` is a Leg-2 deliverable).
Plus three clarifying suggestions folded in (double-flag bypass needs *both* flags;
`/usr/local` is under the `--ro-bind /usr` so expected-covered but confirm empirically;
contention note now names the existing `the-one`/`windows-installer` pipelines).
Fixes were corrections/simplifications (no scope or risk added) → **second design-review
cycle skipped** (within the 2-cycle cap). Leg 1 → `ready`.

---

## Leg Progress

### bwrap-feasibility-spike (Leg 1 — 2026-06-17)

#### Runs executed

**Run 1 — unprivileged `fly execute` (image: `python:3.11`, venv in repo `.venv`):**

```
fly -t the-one execute -c /tmp/bwrap-spike.yml -i repo=.
```

- Workspace: `/tmp/build/b1dda4c3/repo` (Concourse default location)
- bubblewrap 0.11.0 installed via `apt-get`
- `/proc/sys/kernel/unprivileged_userns_clone`: absent (falls through to empirical probe)
- `/proc/sys/kernel/apparmor_restrict_unprivileged_userns`: absent
- Empirical userns probe: **FAILED** — `bwrap: No permissions to create new namespace`
- Factory selected: **passthrough (userns-unavailable)** — tests degraded, multiple FAILs
- Verdict for this run: worker blocks unprivileged userns in unshared containers

**Run 2 — privileged `fly execute -p` (image: `python:3.11`, venv in repo `.venv`):**

```
fly -t the-one execute -p -c /tmp/bwrap-spike.yml -i repo=.
```

- Empirical userns probe: **OK** — privileged container permits user namespaces
- Factory: `sandbox backend: bubblewrap — tool spawns are sandboxed` ✓
- Test result: 31 passed, 10 failed, 3 skipped
- Failures: all `test_mcp_sandbox_integration.py` + 2 `test_mcp_pool.py` (bwrap integration)
- Failure cause: `bwrap: execvp /tmp/build/…/repo/.venv/bin/python: No such file or directory`
  - `sys.executable` = venv under `/tmp/build/…` is shadowed by bwrap's `--tmpfs /tmp`

**Run 2b (diagnostic) — privileged, /opt/venv layout:**

```
fly -t the-one execute -p -c /tmp/bwrap-spike-v2.yml -i repo=.
```

Confirmed: `resolve_python()` from `/opt/venv` returns `/usr/local/bin/python3.11`
(under `/usr` — correct). Manual boxed-mode bwrap spawn of that interpreter: **SUCCESS**.
The `/usr/local` interpreter path IS covered by `--ro-bind /usr /usr`.

**Run 3 — privileged `fly execute -p` (image: `python:3.11`, venv at `/opt/venv`):**

```
fly -t the-one execute -p -c /tmp/bwrap-spike.yml -i repo=.
```

- Venv at `/opt/venv` (outside `/tmp`); package installed with `pip install -e repo/.[all-llms,dev]`
- `sys.executable` = `/opt/venv/bin/python3` → resolves to `/usr/local/bin/python3.11` (under `/usr`)
- `resolve_python()` = `/usr/local/bin/python3.11` ✓ (`under /usr? True`)
- Manual boxed-mode spawn: **SUCCESS**
- Factory log: `sandbox backend: bubblewrap — tool spawns are sandboxed` ✓
- Test result: **31 passed, 10 failed, 3 skipped**
- Remaining failures: all MCP sandbox/pool tests — new error:
  `bwrap: Can't chdir to /tmp/build/b1dda4c3/repo: No such file or directory`
  - Root cause: `test_mcp_sandbox_integration.py` sets `cwd=_PROJECT_ROOT`
    (`Path(__file__).resolve().parent.parent` = `/tmp/build/…/repo`).
    bwrap's `--tmpfs /tmp` shadows the Concourse workspace CWD inside the sandbox.
    On GitHub Actions the workspace is under `/home/runner/work/…` — not `/tmp` — so
    this issue is Concourse-specific.

#### Key finding: the Concourse `/tmp` workspace issue

The 10 MCP test failures are NOT caused by passthrough degrade — the bubblewrap backend
IS selected and kernel containment IS enforced. They fail because:

1. Concourse places the build workspace at `/tmp/build/<id>/repo/`
2. bwrap's `--tmpfs /tmp` (standard sandbox argv, both host-mode and boxed) replaces `/tmp`
   with a fresh empty tmpfs — making the repo path invisible inside the sandbox
3. `test_mcp_sandbox_integration.py` hard-codes `cwd=str(_PROJECT_ROOT)` for the bwrap-spawned
   MCP server subprocess, and `_PROJECT_ROOT` resolves to the Concourse workspace path

The 31 tests that DO pass (box isolation × 7, builtin tool sandbox × 7, PTY sandbox × 5,
CLI sandbox parity × 3, MCP pool + factory tests) include all the tests that assert
real kernel-enforced containment through the `run_python` / `run_shell` / PTY code paths.
Those tests use `home_workspace()` (under `$HOME`, not `/tmp`), which is why they work.

#### Verdict

**CONDITIONAL GREEN** — bwrap IS viable on Concourse with `privileged: true`. The
factory selects `BubblewrapSandbox`, the empirical userns probe passes, and 31 containment
tests pass with real kernel enforcement. The 10 MCP integration tests fail due to a
Concourse-specific workspace-under-`/tmp` incompatibility that requires a small,
targeted fix in `test_mcp_sandbox_integration.py` (substitute a non-`/tmp` CWD
in the sandbox MCP server fixture, mirroring `_sandbox_fixtures.py::home_workspace()`).
This fix is within scope of Leg 2 (`bwrap.yml` authoring).

**Chosen image/venv/privilege strategy for `ci/tasks/bwrap.yml`:**
- **Image**: `python:3.11` (Debian-based; bubblewrap available via apt; interpreter at
  `/usr/local/bin/python3.11` which is under `/usr` — covered by boxed-mode bind)
- **Venv**: `/opt/venv` (NOT `.venv` in the repo input, which is under `/tmp/build/…`
  and would be shadowed by `--tmpfs /tmp`). Install: `pip install -e repo/.[all-llms,dev]`
- **Privilege**: `privileged: true` on the Concourse task step (unprivileged userns is
  blocked on the shared worker; privileged grants the nested user namespace capability)
- **Concourse task working dir**: set to `/opt` or leave default; run pytest with
  explicit `tests/` path relative to the repo input

**Leg 2 action item:** Before authoring `ci/tasks/bwrap.yml`, fix
`tests/test_mcp_sandbox_integration.py` (and the two `test_mcp_pool.py` bwrap tests) to
use a CWD and `sys.executable`-derived path outside `/tmp` for the bwrap-spawned MCP
server subprocess. The natural fix: mirror `home_workspace()` — use `HOME`-relative or
`/var/tmp`-based paths for MCP server CWDs in bwrap tests.

#### Cleanup

- `/tmp/bwrap-spike.yml` — removed ✓
- `/tmp/bwrap-spike-v2.yml` — removed ✓
- No spike pipelines set (`fly -t the-one pipelines` shows no `*-spike` entries) ✓

### concourse-ci-tasks (Leg 2 — design, 2026-06-17)

**Design + 2 review cycles → ready.** Authored `legs/02-concourse-ci-tasks.md` (5 task files
+ the bwrap `/tmp`-workspace remedy). Cycle-1 review (approve-with-changes) caught a **[high]**
flaw in the original remedy: the plan was to move the MCP tests' CWD off `/tmp` but keep
`PYTHONPATH=_PROJECT_ROOT` — yet host-mode bwrap emits `--ro-bind / /` **then** `--tmpfs /tmp`
(`bubblewrap.py`), so a `/tmp/build/…/repo` PYTHONPATH is *also* wiped inside the sandbox.

**Remedy reconsidered — relocation, not test edits (supersedes the Leg-1 verdict's "fix the
tests" action item above).** Rather than modify 10 tests + `conftest.py` to dodge `/tmp`, the
revised Leg-2 has `ci/tasks/bwrap.yml` **copy the checkout to `/opt/the-one`** and install +
run from there, so `_PROJECT_ROOT` resolves outside `/tmp` — exactly reproducing the GitHub
`/home/runner/…` condition that makes the suite green. Zero source changes; the tests aren't
buggy (they assume a non-`/tmp` checkout, which the host-mode full RO bind exposes); the
Concourse `/tmp/build` workspace was the anomaly. Cycle-2 review **approved**: traced the
relocation end-to-end (`_PROJECT_ROOT`/PYTHONPATH/cwd → `/opt/the-one`, editable finder baked at
`/opt/the-one`, `home_workspace` tests under `$HOME` unaffected, no repo symlinks resolving back
to `/tmp`). Folded in: explicit `cd /opt/the-one` chained through the pytest call; a header note
that the runner's `/tmp` `THE_ONE_DATA_DIR` is harmless. Leg 2 → `ready` (within the 2-cycle cap).

### concourse-ci-tasks (Leg 2 — implementation, 2026-06-17)

**All 5 task files green standalone via `fly execute`.**

| Task file | `fly execute` result | Notes |
|---|---|---|
| `ci/tasks/lint.yml` | **succeeded** | `ruff check` + `ruff format --check` passed; 361 files formatted |
| `ci/tasks/test.yml` | **succeeded** | 3178 passed, 10 skipped, 589 deselected in 93s |
| `ci/tasks/browser.yml` | **succeeded** | 478 passed, 35 skipped, 12 deselected in 524s (~8:44) |
| `ci/tasks/windows-tests.yml` | **succeeded** | 403 passed, 15 skipped, 1 deselected, 2 xfailed in 56s |
| `ci/tasks/bwrap.yml` (`fly execute -p`) | **succeeded** | 41 passed, 3 skipped, 3733 deselected in 21s |

**bwrap relocation confirmed working**: log shows `sandbox backend: bubblewrap — tool spawns
are sandboxed`. The relocation to `/opt/the-one` resolved all 10 MCP integration failures
from the Leg-1 spike (Leg-1: 31 pass / 10 fail; Leg-2: 41 pass / 0 fail). The 3 skipped are
the 2 `@pytest.mark.skip` tests plus 1 additional skip. No source edits — the relocation
approach in `bwrap.yml` alone was sufficient.

**Surprises and adaptations:**

1. **Pre-existing lint violations (Flight 7 technical debt)**: The codebase had 16 ruff
   violations (import ordering, unused imports, long lines) in tests and `the_one/` files
   authored in Flight 7 — these were never caught because GH Actions minutes were exhausted.
   `ruff check --fix` + `ruff format` resolved all 16. The formatting changes appear in
   `tests/` and `the_one/` files in `git status` alongside the 5 new task files.

2. **Windows worker: Git-Bash tools needed** — the Concourse Windows worker runs PowerShell
   without `true`/`sleep` on PATH. GitHub Actions Windows runner uses `shell: bash` (Git-Bash).
   Fix: prepend `C:\Program Files\Git\usr\bin` to `PATH` and set `HOME=$USERPROFILE` in the
   task. Reduced failures from 4 → 1.

3. **Windows worker: system-account path-case mismatch** — `test_build_tool_profile_default_allowlist`
   fails because the Concourse Windows worker runs as the system account:
   `Path("~").expanduser()` returns `C:\Windows\system32\config\systemprofile` (lowercase,
   from `USERPROFILE`) but `Path.resolve()` returns `C:\Windows\System32\...` (NTFS canonical,
   uppercase S). The test compares both; they agree on a user account (GitHub Actions) but not
   on the system account (Concourse worker). Resolved via `--deselect` in the task invocation —
   not a containment or logic failure, purely a worker-environment artifact. Recorded for
   Leg 3 (pipeline wiring) awareness.

4. **browser.yml wall-clock**: ~9 min (expected ~15 min from the flight spec); Concourse was
   faster than GitHub's shared runners.

### ci-pipeline (Leg 3 — design, 2026-06-17)

**Design + 1 review cycle → ready.** Authored `legs/03-ci-pipeline.md` — unified `the-one`
pipeline (`ci` job + `build-windows-installer`), team-level Vault promotion, reversible cutover.
Split into **Phase A (autonomous: author pipeline YAML + `set-pipeline.sh` + `validate-pipeline`)**
and **Phase B (operator checkpoint: Vault secret promotion + `.vault-seeds.json` edit + live
pipeline set/unpause/pause)** — the credential ops + shared-infra mutations are gated behind
operator authorization.

Design review (approve-with-changes) — fixes incorporated, all reviewer-vetted:
- **[high]** Secret name: the existing pipeline uses `((github-deploy-key.private_key))`, NOT
  goldfinch's `((git-key.private_key))`. Locked the new pipeline to `github-deploy-key`; promotion
  is a path move (`concourse/the-one/windows-installer/*` → team-level `concourse/the-one/*`),
  originals left in place → no rename, no dead window (DD6 intent preserved).
- **[med]** MinIO publish: the live `minio.endpoint` Vault value is a bare `host:port` (no
  `http://`), which an `s3` resource rejects → **reuse the existing inline `minio/mc`
  publish-to-minio task verbatim** instead of a goldfinch `s3` put resource. Sidesteps the scheme
  issue; leaves the `minio` secret untouched.
- **[med]** Promotion is **two** secrets (`github-deploy-key` + the single `minio` kv), not
  "four/five" — corrected.
- **[low]** `build-windows-installer` `get: repo` gets **`trigger: true`** (goldfinch's build jobs
  are manual; DD3 requires auto-on-main) + `passed: [ci]`.
- Folded: `privileged: true` comment on the bwrap step; goldfinch seed-update snippet for `.vault-seeds.json`.

**Key recon (overwrite safety):** the pre-existing `the-one` pipeline (id 15) is a **dormant
Docker-era deploy/rollback** pipeline, last build `deploy/19` on **2026-04-23** (predates F1's
Docker retirement). Overwriting it with the unified CI pipeline is desirable cleanup; confirmed no
activity since April. The live `windows-installer` (id 17, build #23 today) is **paused, not
destroyed** during cutover (reversible; avoids a post-merge double-build); destroy is post-merge
once the unified pipeline proves green.

**Commit-timing note:** the `git` resource pulls *pushed* refs and this flight batches its commit
at flight end, so a live green `ci` build cannot be produced during this leg — that (and the
`windows-installer` teardown) is **post-merge verification**, exactly as the flight's Verification
section frames it. Leg 3 → `ready`; review skipped a 2nd cycle (fixes were reviewer-validated).

### ci-pipeline (Leg 3 — implementation, 2026-06-17)

**Phase A (autonomous):** authored `ci/the-one.pipeline.yml` (one `repo` git resource on `main`
with `((github-deploy-key.private_key))`; `ci` job `trigger:true` → `in_parallel{fail_fast:false}`
over the 5 task files, `bwrap` step `privileged:true`; `build-windows-installer` job
`trigger:true`+`passed:[ci]` → `windows-installer-build.yml` unchanged → the inline `minio/mc`
publish task verbatim) + `ci/set-pipeline.sh` (goldfinch-parity helper, executable).
`fly validate-pipeline` → `looks good`. FD verified the YAML directly.

**Phase B (operator-authorized — operator chose "I run all of it now"):**
1. **Vault secrets promoted to team-level** via MCP `set_secret`: `concourse/the-one/github-deploy-key`
   + `concourse/the-one/minio` (copied from the `windows-installer/*` originals, which were left in
   place — no rename, no dead window). `list_secrets concourse/the-one` now shows both at team level.
2. **`.vault-seeds.json` persistence:** the concourse-local manifest **already contained** the two
   team-level entries (`concourse/the-one/{github-deploy-key,minio}`) — it was *ahead* of live Vault
   (the entries were seeded into the manifest but not applied to the running dev-Vault). The
   promotion in step 1 brought live Vault into sync; `seed-vault.sh` will restore them after any
   restart. No manifest edit needed (verified via the concourse-local `seed-vault.sh` schema).
3. **Unified pipeline set + unpaused** (`bash ci/set-pipeline.sh --non-interactive` → "configuration
   updated"; `unpause_pipeline`). This **overwrote the dormant Docker-era `the-one` pipeline (id 15)**
   in place — its old `deploy`/`auto-rollback` jobs are gone, replaced by `ci` + `build-windows-installer`.
4. **`check-resource -r the-one/repo` succeeded** — the git deploy key resolved from the promoted
   team-level secret (`Identity added: …concourse-the-one-windows-installer`) and fetched `main`.
   This is the DD6 "no dead window" guarantee proven live.
5. **`windows-installer` (id 17) paused** (reversible) — prevents a post-merge double-build of the
   installer. NOT destroyed (its replacement isn't green-on-main yet).

**Final live state:** `the-one` unpaused with the unified config; `windows-installer` paused.

### github-actions-cutover (Leg 4 — 2026-06-17)

GREEN branch applied (DD4 resolved GREEN): both `lint.yml` and `test.yml` converted to
`workflow_dispatch`-only. The `pull_request` + `push: { branches: [main] }` triggers were
removed and replaced with `on: workflow_dispatch:` in each file. Header comments added to
both files explaining the intentional trigger-disable (routine CI on Concourse; break-glass
fallback; pre-push gate via `fly execute`). `windows-installer.yml` left byte-for-byte
unchanged (confirmed via `git status` — not listed as modified). Both edited files are valid
YAML (confirmed via `python3 -c "yaml.safe_load(...)"`).

The live "open a PR → no lint/test runs" check is a **post-merge step** — the new trigger
blocks take effect only once these files land on `main`; pre-merge the old triggers still
live on `main` but Actions minutes are exhausted regardless. This is consistent with the
flight's Verification section framing.

#### Post-merge verification + teardown (NOT done this flight — deferred, per the flight's Verification section)

Once this flight's PR merges to `main` (the commit carries `ci/tasks/*` + `ci/the-one.pipeline.yml`):
1. The `the-one/ci` job auto-triggers on the merge commit → confirm it goes **green** across
   lint/test/browser/windows-tests/bwrap.
2. `build-windows-installer` runs `passed:[ci]` → confirm the `.exe` lands in MinIO (`the-one-installers`).
3. **Then destroy the paused `windows-installer` pipeline** (`fly -t the-one destroy-pipeline -p windows-installer -n`)
   so only the unified pipeline auto-builds on `main`.
4. If the `ci` build is red post-merge, the paused `windows-installer` pipeline is the rollback
   (unpause it) while the unified pipeline is fixed.

### docs (Leg 5 — 2026-06-17)

Files written/edited (docs-only — no code, no workflow, no pipeline changes):

- `ci/README.md` — **new**. Authored from the goldfinch template with the-one specifics:
  what-runs-where table (5 CI lanes + installer build), pre-push `fly execute` gate (incl.
  bwrap `-p` caveat and clean-tree warning), auto-CI on main, on-demand installer build,
  Vault/secrets section (team-level paths `concourse/the-one/{github-deploy-key,minio}`,
  in-memory Vault / `.vault-seeds.json` reseed lesson, bare-`host:port` MinIO endpoint
  with explicit anti-goldfinch note, IP-not-service-name gotcha), bwrap privileged +
  `/opt/the-one` relocation rationale, Windows-worker quirks (Git-Bash PATH + system-account
  path-case + `--deselect` note), DD5 (full browser suite on every main push), and
  post-merge verification + `windows-installer` pipeline teardown steps.
- `CLAUDE.md` — updated line ~40 (lint gate now points to Concourse `ci/tasks/lint.yml`;
  GH `lint.yml`/`test.yml` framed as `workflow_dispatch`-only break-glass; pointer to
  `ci/README.md` added) and line ~176 (CI parenthetical repointed from "test.yml jobs" to
  "Concourse task containers"; same break-glass framing + pointer).
- `the_one/agents.md` — updated two stale GitHub Actions references: the browser-CI
  path-filter block (lines ~76-85, now describes Concourse no-path-filter topology) and the
  curated Windows CI lane block (lines ~909-922, now points to `ci/tasks/windows-tests.yml`
  and frames `.github/workflows/test.yml` as dispatch-only break-glass).

Confirmed docs-only: `git diff --stat` shows only `CLAUDE.md` and `the_one/agents.md` as
modified tracked files; `ci/README.md` is a new untracked file. No `.py`, `.yml`
(ci/tasks or workflows), or pipeline files touched in this leg.
