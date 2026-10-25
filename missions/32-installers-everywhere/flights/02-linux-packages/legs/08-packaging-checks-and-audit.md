# Leg: packaging-checks-and-audit

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Retire `packaging/spike/` (DD8):
- the staging step becomes `packaging/stage.py`;
- the container gate suite and the real-GTK smoke test become `packaging/linux/checks/`;
- the macOS checks move beside the macOS recipe.

Also:
- enforce the post-freeze bundle audit in the Linux build (DD2);
- rename the shipped runtime debug variables out of the `M32_` namespace;
- add the packaging unit tier the Flight 1 debrief asked for.

Every path that used `packaging/spike/` keeps working.

## Context
- **Flight DDs:** DD8 (the fold, the macOS move, the unit tier), DD2 (the audit), DD10 (the hosted job runs this check suite on bare images, under `xvfb`, in leg 9, so the window phase must not depend on WSLg).
- **The spike after legs 1-7** (uncommitted), 1239 lines:
  - `stage.py` (111, with `M32_SOURCE`);
  - `check.sh` (43: `--env`, `--variant`, `--extra-apt`, the WSLg X mount for `baseline`);
  - `inner.sh` (280);
  - `score.py` (421: per-soname gate 3, the probe scorer);
  - `xwd2png.py`;
  - `gtk-smoke.sh` and `gtk-smoke-inner.sh` (legs 3 and 5);
  - `macos-checks.sh` (143);
  - `images/{ubuntu-26.04,debian-13}.Dockerfile`;
  - `README.md`.
- **References to `packaging/spike/`:**
  - `packaging/linux/build.sh:67` (`stage.py`);
  - `packaging/macos/build.sh:32` (`stage.py`) and `:75` (`macos-checks.sh`);
  - the docstrings in `packaging/{linux,macos}/the-one.spec` and `packaging/macos/README.md`.
  - `.github/workflows/packaging-probe-macos.yml` calls only `packaging/macos/build.sh`, so the workflow file itself needs no edit (its `on:` block stays as on `main`).
- **Runtime debug variables shipped in both Linux packages** (`rthook_host_gtk.py`): `M32_DEBUG_ENV`, `M32_FORCE_FALLBACK` (only with `M32_DEBUG_ENV`), `M32_ABI_PROBE`. `Settings` uses `extra: "ignore"` (`the_one/config.py`), so `THE_ONE_`-prefixed names that are not settings fields are safe. Rename them to `THE_ONE_PKG_DEBUG`, `THE_ONE_PKG_FORCE_FALLBACK` and `THE_ONE_PKG_ABI_PROBE`.
  - Build-time variables (`M32_BUILD`, `M32_STAGE`, `M32_SOURCE`, `M32_FROM_HEAD`, `M32_NO_EXCLUDES`, `M32_ICNS`, `M32_REQUIREMENTS`, `M32_LOGS`, `M32_VM`, `M32_EVIDENCE`) never ship. They stay unchanged, to avoid churning the macOS probe, Flight 3's files and the VM tooling. The README records this.
- **Concurrency:**
  - Leg 5 phase A (`the_one/`, `tests/` other than `test_packaging_*`) may still be running, and **may be running `packaging/spike/gtk-smoke.sh`**. Leg 1 found that editing a harness script while a run uses it corrupts that run.
  - So this leg starts only after leg 5 phase A has handed off, and the Flight Director confirms that before spawning. Leg 5 phase B then uses the new paths.
  - Leg 4 is running VMs from `packaging/linux/vm/` (untouched here).

## Inputs
- `packaging/spike/*`, `packaging/linux/{build.sh,build-inner.sh,the-one.spec,rthook_host_gtk.py,excludes.txt,README.md}`, `packaging/macos/{build.sh,the-one.spec,README.md}`
- Existing packaging tests: `tests/test_packaging_metadata.py`, `tests/test_packaging_apprun.py`, `tests/test_packaging_locked_closure.py`, `tests/test_packaging_winpty_spec.py`
- `$HOME/the-one-m32-build/f2/packages/` (leg 7's 0.11.8 and 0.11.9.dev1 builds), for re-running the checks after the move

## Outputs
- **`packaging/stage.py`:** moved with `git mv` (history kept). The `--candidate` argument is renamed `--target` (`linux`/`macos`); the old flag stays accepted as an alias for one release. The docstring no longer says "spike". `REPO` resolves one level up.
- **`packaging/linux/checks/`,** all moved with `git mv`:
  - `check.sh` (renamed `gates.sh`, with `check.sh` kept as a one-line forwarding shim until leg 9 lands, then deleted there);
  - `inner.sh` → `gates-inner.sh`;
  - `score.py`;
  - `xwd2png.py`;
  - `gtk-smoke.sh`, `gtk-smoke-inner.sh`;
  - `images/`;
  - `README.md`, rewritten as product check documentation, not spike notes.
- **Window-phase display selection:** `gates.sh --display wslg|xvfb`.
  - `wslg` mounts `/mnt/wslg/.X11-unix`, as today.
  - `xvfb` starts a private `Xvfb :99 -screen 0 1920x1080x24` inside the container, which the images' observe layer already has. Gate 3 and single-instance then run under it.
  - The default is `wslg` when `/mnt/wslg/.X11-unix/X0` exists, else `xvfb`, so the runner gets `xvfb` with no flag.
- **`packaging/macos/checks.sh`:** moved from `spike/macos-checks.sh` with `git mv`. `packaging/macos/build.sh` calls it at its new path and calls `packaging/stage.py --target macos`. The `macos/` README and spec docstring are updated. Nothing else in `packaging/macos/` changes (Flight 3 owns it).
- **`packaging/linux/build.sh`** calls `packaging/stage.py --target linux`.
- **`packaging/spike/`** is deleted entirely: no file, shim or `README` left.
- **The post-freeze bundle audit (DD2):** `packaging/linux/audit.py`, stdlib only, run by `build-inner.sh` right after the freeze, before wrapping. It fails the build (non-zero, with the offending paths printed) when, scoped to the PyInstaller bundle directory only (`dist/the-one/`, never the fallback directory):
  - any file's base name matches an `excludes.txt` pattern;
  - any `*.typelib` is present;
  - any ELF file requires a `GLIBC_` symbol version newer than 2.39. It reads the `.gnu.version_r` of each ELF with `readelf -V`, which the build image has, and takes the maximum.

  The audit prints a summary: file count, maximum glibc found, and pass/fail.
- **Runtime debug variable rename** in `rthook_host_gtk.py`, `gates-inner.sh`, `score.py`, the READMEs and any test. No `M32_DEBUG_ENV`/`M32_FORCE_FALLBACK`/`M32_ABI_PROBE` string may remain in `packaging/` or `tests/`.
- **The packaging unit tier,** all loading scripts by path, as `tests/test_windows_test_copy.py` does:
  - `tests/test_packaging_stage.py`:
    - refuses an output inside the repo;
    - rewrites exactly one `__version__`;
    - fails on zero or two matches;
    - `M32_SOURCE` stages from another tree;
    - the `--candidate` alias works.
  - `tests/test_packaging_audit.py`, on a fake bundle in `tmp_path`:
    - an `excludes.txt` match fails;
    - a typelib fails;
    - a fake ELF needing `GLIBC_2.41` fails (`readelf` output stubbed through a seam if needed);
    - a clean tree passes;
    - the fallback directory is never scanned;
    - every `excludes.txt` line is a valid pattern, with no blank-only or duplicate lines.
  - `tests/test_packaging_score.py`, on synthetic evidence dirs:
    - gate 1's strict "skipped" rule (window chrome's `skipped (not Windows)` excepted);
    - gate 3 per soname (host library from `/usr/lib` passes; the fallback path when the host lacks it passes; the fallback path when the host has it fails; a web process mapping the mount fails);
    - the probe scorer's grep patterns and control exclusion.
  - The macOS argv shim (`packaging/macos/frozen_entry_mac.py`'s `-psn_*` handling): extract it as a pure function inside that file only if the change is trivial, and test it. Otherwise record it as Flight 3's.

## Acceptance Criteria
- [ ] **AC1** — `packaging/spike/` no longer exists. `git grep -n "packaging/spike\|spike/" -- packaging .github ci tests the_one` shows nothing. The moves are `git mv`, and `git log --follow` on a moved file shows its spike history.
- [ ] **AC2** — after the move, the build and both check suites still work:
  - `packaging/linux/build.sh --version 0.11.9.dev6` builds, and its log shows the audit summary passing;
  - `packaging/linux/checks/gates.sh` re-runs the leg 7 pair, the `.deb` on `ubuntu-26.04-baseline` and the AppImage on `debian-13-baseline`, giving the same PASS lines;
  - one `.deb` run on `debian-13-bare` with `--display xvfb` passes (G3 N/A on bare, as before; this proves the runner path's scaffolding);
  - `gtk-smoke.sh` on one baseline passes.
- [ ] **AC3** — the audit fails a build. A deliberately broken staging of the exclude list, done in a scratch copy and never committed, makes `build.sh` exit non-zero with the offending file named. Recorded, then reverted. The audit has unit tests (AC5).
- [ ] **AC4** — no `M32_DEBUG_ENV`, `M32_FORCE_FALLBACK` or `M32_ABI_PROBE` remains in `packaging/` or `tests/`. `THE_ONE_PKG_DEBUG=1` in a frozen run prints the hook's report (one run inside a gate container, or the extracted AppImage on the dev host with `--version`).
- [ ] **AC5** — the four test files above pass. `make test-unit` passes, with 12 skips.
- [ ] **AC6** — the macOS side still works: `bash -n packaging/macos/build.sh packaging/macos/checks.sh`, `shellcheck` on both, and a dry read that every path `packaging/macos/build.sh` references exists. It cannot run on Linux, so it is a static check. `actionlint` (`$HOME/the-one-m32-build/tools/actionlint-1.7.7/actionlint`) is clean on `packaging-probe-macos.yml`, which is unchanged.
- [ ] **AC7** — gates:
  - `ruff check`/`ruff format --check` on `the_one/ tests/ scripts/ evals/ packaging/`;
  - `shellcheck` on every moved or changed shell script, keeping the file-level disables leg 1 added and adding none new without a reason in a comment;
  - no `m32-` container left running;
  - no 8484/8485;
  - the operator data dir untouched;
  - only `packaging/`, the new test files and this flight's log changed by this leg.

## Verification Steps
- AC1: `ls packaging/spike` (absent); the `git grep`; `git log --follow --oneline packaging/stage.py | head`.
- AC2: the build log; the `gates.sh` and `gtk-smoke.sh` score lines.
- AC3: the deliberate-failure transcript in the flight log.
- AC4: `git grep`; the debug output.
- AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_packaging_stage.py tests/test_packaging_audit.py tests/test_packaging_score.py tests/test_packaging_metadata.py tests/test_packaging_apprun.py -x --timeout 30`; `make test-unit`.
- AC6, AC7: the commands named.

## Implementation Guidance
1. Confirm that no `m32-gate-*`/`m32-gtk-smoke-*` container is running (`docker ps --filter name=m32-`) before moving any harness file.
2. `git mv` everything, then fix every reference: the `git grep` in AC1, plus relative paths inside the moved scripts (`HERE`, `../linux`, the `images/` build context).
3. The display selection in `gates.sh`/`gates-inner.sh`.
4. `audit.py`, then wire it into `build-inner.sh`.
5. The debug variable rename.
6. The unit tests.
7. Rebuild, then run the AC2 suite one container at a time.
8. READMEs (`packaging/linux/README.md`, `checks/README.md`, `packaging/macos/README.md`), then the flight-log section `### packaging-checks-and-audit`.

## Edge Cases
- **The `check.sh` shim:** kept only so a notes or flight-log command still works until leg 9. Leg 9 deletes it.
- **`stage.py`'s repo-refusal logic** used `git rev-parse` from the spike location. After the move, check that it still finds the top level from `packaging/`.
- **`score.py`'s imports:** if any test or script imports it as a module, update the import path.
- **The macOS workflow:** it runs `packaging/macos/build.sh` on a hosted Mac, which must find `packaging/stage.py` and `packaging/macos/checks.sh`. A path typo there costs a hosted run in Flight 3, which is why AC6 includes a static path check.

## Files Affected
- `packaging/spike/*` → `packaging/stage.py`, `packaging/linux/checks/*`, `packaging/macos/checks.sh` (moves)
- `packaging/linux/{build.sh,build-inner.sh,the-one.spec,rthook_host_gtk.py,README.md}`, `packaging/linux/audit.py` (new)
- `packaging/macos/{build.sh,the-one.spec,README.md}` (path references only)
- `tests/test_packaging_stage.py`, `tests/test_packaging_audit.py`, `tests/test_packaging_score.py` (new)
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section)

## Citation Audit
Checked against the worktree after leg 7 landed (uncommitted):
- `packaging/linux/build.sh:67` → `packaging/spike/stage.py`. Verified.
- `packaging/macos/build.sh:32` (`stage.py`) and `:75` (`macos-checks.sh`). Verified.
- `.github/workflows/packaging-probe-macos.yml:96` runs `bash packaging/macos/build.sh`; no `spike/` path in the workflow. Verified.
- `rthook_host_gtk.py`: `M32_DEBUG_ENV` (lines 92, 165), `M32_FORCE_FALLBACK` (93), `M32_ABI_PROBE` (around 174). Verified.
- `the_one/config.py` `model_config` has `"extra": "ignore"`. Verified.
- The spike file list and sizes, as above. Verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
