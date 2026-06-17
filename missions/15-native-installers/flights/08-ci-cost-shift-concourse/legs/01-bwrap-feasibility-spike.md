# Leg: bwrap-feasibility-spike

**Status**: completed
**Flight**: [CI cost-shift — move day-to-day CI to local Concourse](../flight.md)

## Objective

Empirically determine, on a real Concourse `the-one` worker, whether the
`-m requires_bwrap` lane can run with **kernel-enforced containment** (not
graceful-degrade passthrough) — and decide the exact **image + interpreter/venv +
privilege** strategy the lane will use — so DD4 resolves GREEN (port `bwrap.yml` to
Concourse) or RED (keep one `bwrap` job on GitHub Actions).

## Context

- **DD4** (flight): the bwrap lane is *spike-gated* — Leg 1 decides. This applies the
  **F7 debrief top lesson**: exercise the exact runtime surface a design depends on,
  *before* the dependent leg, not at integration. bwrap-on-a-CI-worker is an
  unverified-runtime premise (worker container privilege + the host's
  `kernel.apparmor_restrict_unprivileged_userns` / `unprivileged_userns_clone` posture
  are not knowable from a config read).
- **How the GH `bwrap` job earns real containment** (`.github/workflows/test.yml:118-144`):
  (a) `apt-get install -y bubblewrap`; (b) `sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`
  (root, on the runner host); (c) a **venv from the SYSTEM python3** (not setup-python's
  `/opt` hostedtoolcache) so `resolve_python()` follows symlinks back into `/usr` —
  boxed-mode `minimal_rootfs` mounts only `/usr` + merged-usr symlinks and **fails loud**
  for interpreters outside it (the "Boxed mode requires the interpreter inside `/usr`"
  Known Issue, mission.md).
- **The containment-vs-passthrough observable** (`the_one/platform/sandbox/factory.py`):
  the factory logs `sandbox backend: bubblewrap — tool spawns are sandboxed` (INFO) only
  when Linux + `bwrap` present + `_userns_available()=="ok"`. Otherwise it logs a
  `passthrough (...)` WARNING/ERROR and tools run **unconfined**. The `-m requires_bwrap`
  tests carry real containment assertions that **fail under passthrough** — so a *passing*
  `-m requires_bwrap` run is itself proof of real kernel containment. That pass/fail is
  the spike's GREEN/RED signal; no separate "is it really contained?" check is needed.
- **The userns probe** is empirical: it runs `bwrap --unshare-user --ro-bind / / /usr/bin/true`
  with a 5s timeout; `/proc/sys/kernel/unprivileged_userns_clone` reading `"0"` short-circuits
  to `unavailable`, an absent knob (WSL2) falls through to the empirical probe.
- **The double-flag bypass does NOT fire here.** `tests/conftest.py` sets `THE_ONE_TEST_MODE=1`
  but the factory's test-bypass requires **both** `THE_ONE_TEST_MODE=1` *and*
  `THE_ONE_SANDBOX_DISABLED=1` (`factory.py:139-142`); the `requires_bwrap` tests
  `delenv("THE_ONE_SANDBOX_DISABLED")` to be sure. So with bwrap present + userns ok the
  factory selects `BubblewrapSandbox`, as intended — a single flag never triggers passthrough.
- **`/usr/local` is covered by the boxed bind, but confirm empirically.** `python:3.11`'s
  interpreter at `/usr/local/bin/python3.11` sits *under* `/usr`, and the bwrap backend binds
  `--ro-bind /usr /usr` — so it is expected to be reachable. The residual risk is image-specific
  venv symlink chains that `resolve_python()` could follow *outside* `/usr`; exercise a real
  boxed-mode spawn rather than eyeballing the path.

## Inputs (what must be true before this leg runs)

- `fly -t the-one` session valid; linux worker `334c0e4b22cd` running. *(verified by FD
  at flight start — flight log)*
- Working tree of `the-one` available as a `fly execute -i repo=.` input.
- `the_one` installable via `pip install -e ".[all-llms,dev]"` on the candidate image.

## Outputs (what exists after this leg completes)

- A **recorded GREEN/RED verdict** in the flight log, plus the **chosen image + venv +
  privilege strategy** (or, on RED, the documented reason and the Actions-stays fallback).
- DD4 resolved. **No committed pipeline/task artifact** from this leg — any spike task YAML
  or throwaway pipeline is ephemeral and is removed before the leg lands. (If a GREEN spike
  produces a task file worth keeping verbatim, Leg 2 adopts it as `ci/tasks/bwrap.yml`; the
  spike itself still commits nothing.)

## Acceptance Criteria

- [x] A throwaway bwrap task ran on a Concourse `the-one` worker, invoking
      `python -m pytest -m requires_bwrap tests/` in a documented image + interpreter
      layout. The exact image, interpreter path, venv approach, and privilege mode
      (unprivileged `fly execute` vs. a `privileged: true` pipeline task) are captured.
- [x] The run's outcome is unambiguous and the **GREEN/RED interpretation is justified by
      the observed signal**. The **primary** signal is the test result: a passing
      `-m requires_bwrap` run *is* proof of real containment (its assertions fail under
      passthrough). As corroboration, run with `--log-cli-level=INFO` so the factory's
      `bubblewrap — tool spawns are sandboxed` line is visible in the build log (vs a
      `passthrough (...)` line). For RED: the specific failure is named (userns
      `unavailable`/`error`, a boxed-mode `/usr` execvp failure, or no privilege path works).
- [x] The verdict **and** the chosen image/venv/privilege strategy are written to the
      flight log (Decisions or Session Notes), explicitly resolving **DD4**.
- [x] No spike scaffolding remains: any throwaway pipeline is destroyed (`fly destroy-pipeline`)
      and no uncommitted spike YAML is left staged for commit.

## Verification Steps

- Show the `fly` invocation (execute or set-pipeline+trigger-job) and the build output
  containing **either** the `requires_bwrap` tests passing + the `bubblewrap — tool spawns
  are sandboxed` log line (GREEN) **or** the passthrough/degrade/execvp failure (RED).
- `fly -t the-one pipelines` shows no leftover `*-spike` pipeline after cleanup.
- The flight log's DD4 entry states the verdict and the strategy a GREEN Leg 2 would use
  (or the RED fallback Leg 4 would apply).

## Implementation Guidance

1. **Confirm the containment observable before running anything heavy.** Skim
   `the_one/platform/sandbox/factory.py` (selection order + the `bubblewrap`/`passthrough`
   log lines) and how the `-m requires_bwrap` tests assert containment, so the spike's
   GREEN/RED reading is grounded in what the code actually emits.
2. **Cheapest path first — unprivileged `fly execute`.** Author a throwaway task
   (`/tmp/bwrap-spike.yml`, NOT under `ci/`) on a Linux image, install bubblewrap, set up
   the interpreter, and run
   `python -m pytest -m requires_bwrap tests/ --timeout=300 --tb=short --log-cli-level=INFO`
   (the `--log-cli-level=INFO` surfaces the factory's backend-selection line in the build log).
   Run it: `fly -t the-one execute -c /tmp/bwrap-spike.yml -i repo=.`. Observe whether the
   empirical userns probe succeeds in an **unprivileged** Concourse container (it may not —
   that is a primary finding).
3. **Decide the image + interpreter layout deliberately** (this is half the leg, not an
   afterthought): try `python:3.11` first (interpreter at `/usr/local/bin/python3.11` — verify
   whether boxed-mode `minimal_rootfs`'s `/usr` mount actually covers `/usr/local`, or whether
   boxed-mode execvp fails the same way the `/opt` hostedtoolcache trap did). If `python:3.11`
   trips the boxed-mode `/usr` constraint, fall back to a debian/ubuntu image + `apt-get install
   python3.11 bubblewrap` + **venv-from-system-python**, mirroring the GH job exactly. Record
   which layout was needed and why.
4. **If unprivileged userns is blocked, re-run privileged.** `fly execute` supports a
   `-p/--privileged` flag (verified on this machine, Concourse 8.1.0) — just re-run
   `fly -t the-one execute -p -c /tmp/bwrap-spike.yml -i repo=.`. No throwaway pipeline is
   needed for the spike. A privileged container is an acceptable strategy for the real
   `bwrap.yml` lane *if* it is what makes containment work — note that for **Leg 2** (which
   authors `bwrap.yml`; a pipeline task ships privilege via `privileged: true` on the task step).
   Only if you find a reason `fly execute -p` behaves differently from a pipeline's
   `privileged: true` task would a throwaway pipeline be worth setting (and then destroy it
   with `fly destroy-pipeline -p <name> -n`).
5. **Interpret and record.** GREEN = `requires_bwrap` passes with the `bubblewrap` backend
   selected. RED = passthrough degrade / boxed-mode `/usr` failure / no privilege path. Write
   the verdict + chosen strategy into the flight log, explicitly resolving DD4. **Report the
   verdict and evidence back to the Flight Director — do not edit DD4 in the flight spec
   yourself; the FD records the DD4 resolution.**
6. **Clean up** every throwaway artifact (pipeline destroyed, no staged spike YAML).

## Edge Cases

- **Unprivileged-first, then `-p`**: bare `fly execute` runs unprivileged; if the
  unprivileged userns probe fails, re-run with `fly execute -p` (step 4) before concluding RED.
- **`python:3.11` `/usr/local` vs boxed `/usr`**: the interpreter being under `/usr/local`
  (a subdir of `/usr`) does not guarantee `minimal_rootfs` mounts it the way `resolve_python()`
  needs — verify by actually exercising a boxed-mode spawn, not by path-eyeballing.
- **AppArmor on the worker host**: if the host enforces `apparmor_restrict_unprivileged_userns=1`
  and the container can't relax it, even a privileged container may not get nested userns →
  that is a legitimate RED (record it; Leg 4 keeps the one `bwrap` job on Actions).
- **Shared-worker contention**: the single linux worker is shared with the existing
  `the-one`/`windows-installer` pipelines (and the goldfinch/epipen teams) — keep the spike
  single-shot and tear it down promptly.
- **Probe `error` vs `unavailable`**: distinguish them — `error` means the probe mechanism
  broke (investigate the image), `unavailable` is a definitive negative.

## Files Affected

- *(none committed)* — throwaway spike task/pipeline YAML under `/tmp`, removed after the run.
- `missions/15-native-installers/flights/08-ci-cost-shift-concourse/flight-log.md` — verdict +
  strategy + DD4 resolution recorded by the Flight Director.

---

## Post-Completion Checklist

**Complete ALL steps before signaling completion:**

- [x] All acceptance criteria verified
- [x] Throwaway spike pipeline/task destroyed; nothing spike-related staged for commit
- [x] Flight log updated with GREEN/RED verdict, chosen image/venv/privilege strategy, DD4 resolution
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch review)
- [x] (No flight.md leg-checkoff yet — legs commit together at flight end per the batched workflow)
