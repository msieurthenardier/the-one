# Leg: linux-briefcase

**Status**: completed
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
Build GleepGlorp AI for Linux with Briefcase (candidate B): a system-package `.deb` per target distro, plus Briefcase's AppImage. Measure them with leg 2's gate runner against every DD2 hard gate and soft criterion, unpatched first, then with any app-side patch a gate needs (DD4), and add B's rows to the Evidence Table.

## Context
- **Flight decisions:**
  - DD1 (B's formats: per-distro system `.deb`s through Docker targets; the AppImage expected to fail gate 3);
  - DD2 (strict gates; under Briefcase, `is_frozen()` is false, so gate 1's frozen-only gates read `skipped` and score FAIL by design);
  - DD3 (shared staging; the pinned closure; config outside the root `pyproject.toml`);
  - DD4 (app-side patches are diffs under `packaging/briefcase/patches/`, applied to the staging copy only);
  - DD5 (apparatus).

  Read them, plus the flight log's `linux-pyinstaller-build` and `linux-pyinstaller-gates` entries and the Evidence Table, before starting.
- **Reuse leg 2's harness unchanged where possible.**
  - The gate runner is `packaging/spike/check.sh <candidate> <deb|appimage> <distro> <baseline|bare> --n 0.11.8 --n1 0.11.9.dev1 [--pkgdir DIR]`, run with `PYTHON=.venv/bin/python` and `M32_EVIDENCE` set.
  - It expects package files named `gleepglorp-ai_<N>_amd64.deb` and `GleepGlorp_AI-<N>-x86_64.AppImage` in `--pkgdir`. It expects a `the-one` command on `PATH` that accepts `version`, `doctor`, `serve`, `app` and `rotate-api-credential`.
  - Its `find_ui` (in `inner.sh`) greps the command line for `the-one`.

  Where B differs, make the smallest candidate-neutral change to the harness, such as a package-name option or a process-match option, so A's runs would still reproduce, and log it. Do not fork the harness per candidate.
- **The app's entry points:**
  - `the_one/__main__.py` calls `the_one.main.cli_entry()`.
  - With no arguments, `cli_entry` starts the terminal `chat`, not the desktop window (`the_one/main.py::cli_entry`). So a Briefcase launcher that runs the app module with no arguments (the `.desktop` entry) opens no window.
  - B needs either a Briefcase configuration that passes `app` (such as a different main module or launcher arguments, if the pinned Briefcase version supports one), or a DD4 patch. Prefer configuration, and record which was used. Either counts toward upkeep.
- **Naming:**
  - Briefcase derives the module name from `app_name` (`the-one` → `the_one`), so the Debian package name will likely be `the-one`, not leg 1's `gleepglorp-ai`.
  - Use `formal_name = "GleepGlorp AI"`, and keep Briefcase's natural package name. Record the difference as an upkeep and naming point; do not fight the tool for it.
  - Copy or symlink the produced files to the names `check.sh` expects (or use the new option), and log the real names.
- **Versions:** N = `0.11.8`, N+1 = `0.11.9.dev1`. Briefcase's version field must match the staged `__version__`. Generate the Briefcase `pyproject.toml` into the staging root with the version filled in, so the version still lives in one place: the staging argument.
- **Gates 1 and 2 under Briefcase, measured honestly:**
  1. Run them on the unpatched build first and record the result: expect `skipped` lines, and `resolve_python` returning `sys.executable`.
  2. Find out what `sys.executable` and `sys.frozen` are inside B's installed app (a one-line probe through the app's own Python, if B's layout allows it), and log them.
  3. Only then, if a small, well-scoped patch to `the_one/platform/env.py::is_frozen` (or the interpreter resolution) makes the gates meaningful, write it as `packaging/briefcase/patches/NN-<slug>.diff` and re-run. Score "PASS with patch NN", and log the diff and why.

  A patch must not weaken a gate: it may make the bundle count as frozen, but it may not skip a check.
- **The dependency closure:** B must install the same pinned versions A did (the `uv export --no-dev --no-emit-project --extra gui --extra all-llms` closure). If Briefcase's `requires` cannot take hashes, pin exact versions (`==`) generated from the export, and log the deviation.
  - PyGObject and pycairo compile inside Briefcase's Docker build, so the build image needs `libgirepository-2.0-dev`, `libcairo2-dev`, `pkg-config` and a compiler. Use Briefcase's system-requirements settings for this, if it has them.
  - The `.deb`'s runtime dependencies must cover the GTK/WebKit/introspection/AppIndicator stack, as A's do. Leg 2 proved A's list complete on `bare`; reuse that list as the reference.
- **Docker and Briefcase under WSL2:** Briefcase's `--target` builds bind-mount the project directory into a container. The staging root lives under `$HOME` (`$M32_BUILD`), which Docker Desktop can mount. Briefcase may want to build its own images; give them an `m32-` or Briefcase-default name, and never prune others.
- **The AppImage:** if the pinned Briefcase version no longer offers an AppImage format, or marks it deprecated, record that (with the documentation or CLI output) and score the AppImage N/A rather than forcing it. If it builds, run the gates. Expect gate 3 to fail (an old base bundling GTK). A hard-gate FAIL stops that format; record gates 1 and 2 anyway.
- **Safety:** as leg 2 (CLAUDE.md):
  - containers named `m32-…`; no `--privileged`; no `--network host`;
  - no 8484 or 8485; ports of 8490 or higher;
  - the default data dir `~/.local/share/the-one` is never used, and its newest mtime is unchanged at the end (leg 2 recorded `1791383047.9672937840`);
  - kill only PIDs you recorded.

- **Briefcase facts from the leg design review** (Briefcase 0.4.6 source and its linux-system template, read by the reviewer; confirm them against the version you pin):
  - **The launcher.** `/usr/bin/<app_name>` is a C bootstrap that runs `the_one` as `__main__` with the user's arguments. So `the-one doctor`/`serve`/`version` work, and the CLI is on `PATH`. The `.desktop` `Exec` is fixed to `/usr/bin/<app_name> %F`, and the main module is fixed to the module name. Neither is configurable, so opening the window from the desktop entry needs a DD4 patch (AC3).
  - **`sys.executable`.** It is set only when `allow_subprocesses = true`; otherwise it is `""`, and `resolve_python()` (not frozen) returns the current directory. **`allow_subprocesses = true` is required in B's config.** With it, `sys.executable` is `/usr/bin/python3.<minor>`. `sys.frozen` is never set.
  - **Debian `Depends`.** Briefcase writes `libc6`, `libpython3.<minor>` and the `system_runtime_requires` list. It does not add `python3`, so add it explicitly. The list is pasted unquoted into a Dockerfile `apt-get install` line, so `a | b` alternatives would become shell pipes. Use per-vendor and per-codename sections with exact package names, taken from leg 1's AC2 image listings.
  - **File names.** Debs are named `the-one_<ver>-1~<vendor>-<codename>_amd64.deb`. B's `0.11.9.dev1` versus A's `0.11.9~dev1` both sort above `0.11.8`; note the difference.
  - **Templates.** The template is cloned from GitHub at build time (host `git` is needed). Each target's build image is cached as `briefcase/<bundle_id>:<vendor>-<codename>`, so record cold and warm build times separately.
  - **The AppImage.** Briefcase calls it best-effort. It builds on python-build-standalone plus a manylinux base, without binary wheels, so `usearch`, `numpy` and PyGObject 3.56 (which needs girepository-2.0) would build from source. A build failure is likely, and the bundled Python would fail gate 2.
- **Flight Director calls on the review's questions:**
  - a startup-default patch (no arguments opens the window) is an acceptable DD4 patch, scored as B's cost;
  - an AppImage that fails to build is scored FAIL with the build log;
  - gate 1 is recorded unpatched, a FAIL by design, and a narrowly scoped `is_frozen()` patch is allowed as a supplementary "patched" row, provided it skips no check.

## Inputs
- `packaging/spike/` (`stage.py`, `images/`, `check.sh`, `inner.sh`, `score.py`, `xwd2png.py`) and leg 2's images `m32/{ubuntu-26.04,debian-13}:{bare,baseline}`.
- The flight log's Evidence Table, with A's rows.

## Outputs
- `packaging/briefcase/`:
  - the Briefcase `pyproject.toml` template (the app metadata, `requires` generated from the export, system requirements, the `.desktop`/icon settings);
  - `build.sh <version>` (stage, generate the config, build the `.deb` for each `--target`, and the AppImage if offered);
  - `patches/` (only if needed);
  - `README.md` (spike prototype, Mission 32 Flight 1, not wired into CI; the pinned Briefcase version).
- Any candidate-neutral harness option added to `packaging/spike/` (logged).
- Under `$M32_BUILD/packages-briefcase/`: B's packages at N and N+1 (not committed).
- The flight log: a `### linux-briefcase` entry; B's rows and an upkeep paragraph in the Evidence Table.

## Acceptance Criteria
- [ ] **AC0 — `allow_subprocesses = true` is in B's config.** The probe in step 5 shows `sys.executable` as `/usr/bin/python3.<minor>`, that the file exists in each target image, and `sys.frozen` is absent.
- [ ] **AC1 — B builds from the shared staging step with the pinned closure.**
  - `packaging/briefcase/build.sh 0.11.9.dev1` stages through `stage.py --candidate briefcase` and builds from the staged copy.
  - The installed app reports `GleepGlorp AI v0.11.9.dev1` (and `v0.11.8` for N).
  - The log shows the pinned Briefcase version and how the closure was pinned (hashes, or exact versions as a logged deviation).
  - `git status --porcelain -- the_one/ pyproject.toml uv.lock` is empty.
- [ ] **AC2 — A system `.deb` per target.** Briefcase produces a `.deb` for `--target ubuntu:26.04` and one for `--target debian:13`, at both N and N+1 (four files). The log records:
  - their real file names and package names;
  - `dpkg-deb -I` excerpts (`Depends`);
  - each target's system Python version;
  - the build time per target.
- [ ] **AC3 — The desktop entry opens the window.**
  - The installed `.desktop` `Exec` (`/usr/bin/the-one %F`) opens the desktop window, not the terminal chat.
  - This is expected to come from a DD4 patch (`packaging/briefcase/patches/`) that makes no-argument start-up run `app`. The `%F` with no files must still open the window.
  - The log records the patch, that it changes what bare `the-one` does (no longer the terminal chat), and the other options considered (a custom template, post-processing the `.desktop`).
- [ ] **AC4 — Gates 1 and 2: unpatched, then patched if needed.** For each `.deb` × distro on `baseline`, plus each `.deb` on `bare`, the evidence holds gate 1 (`PYSTRAY_BACKEND=gtk` and unset) and gate 2, scored by `score.py`.
  - First on the unpatched build.
  - Then, if a DD4 patch was written, again on the patched build.
  - The log records `sys.executable` and `sys.frozen` inside B's app, and the patch's diff and reason.
  - If the patch makes `is_frozen()` true, it uses a narrow Briefcase marker (logged), and it handles `_bundle_dir()`, which would otherwise be `/usr/bin`. The patched run then shows that `PATH` handed to a child process is unchanged versus unpatched, apart from intended augmentation, and that the `.env` location is where the frozen path expects it. Both are logged.
  - Each target's pip outcome is logged: which pins installed from wheels and which built from source on that target's Python.
- [ ] **AC5 — Gates 3 and 4, upgrade, single-instance.** The same matrix as leg 2 for B's `.deb`s, on the final (patched, if any) build: gate 3 (maps and screenshot), gate 4, the N to N+1 upgrade, and single-instance. Each is recorded in the evidence.
- [ ] **AC6 — The AppImage.** One of the following, with evidence:
  - B's AppImage was built, and run through the gates on both `baseline` images (expected: gate 2 and gate 3 FAIL);
  - its build failed, scored FAIL with the build log excerpt;
  - the pinned version no longer offers the format, scored N/A with the CLI output.
- [ ] **AC7 — B's rows and upkeep are in the Evidence Table.**
  - The same columns and legend as A's.
  - An "unpatched" and a "patched" row where a patch exists.
  - An upkeep paragraph: files and lines under `packaging/briefcase/`; where the version and name live; per-distro artifacts (2 `.deb`s against A's 1); the build image's extra system requirements; the CLI on `PATH`; the launcher arrangement (AC3); sizes; build times; and what a hosted CI build of B would need (Docker on the runner).
- [ ] **AC8 — Safety and the forbidden paths.**
  - The log's safety statement (no 8484 or 8485, no `--privileged`, no `--network host`, scratch data dirs).
  - The default data dir's newest mtime is unchanged.
  - `git diff --stat mission/32-installers` shows changes only under `packaging/` and `missions/`.
  - `ruff check packaging/` and `ruff format --check packaging/` pass.
  - The harness change (if any) still reproduces one A run (re-run `check.sh A deb ubuntu-26.04 baseline`, or prove it by inspection if the change only adds an optional flag).

## Verification Steps
- AC1-AC2: the build log; `ls -l $M32_BUILD/packages-briefcase/`; `dpkg-deb -I` excerpts; `the-one version` inside the containers (from the gate runner's evidence).
- AC3: the `.desktop` file's content (`dpkg-deb -c` and `-x`), and the window screenshot from AC5.
- AC4-AC6: the gate runner's evidence under `$M32_EVIDENCE/B/…`, plus `score.py` summary lines in the log.
- AC7: the Evidence Table.
- AC8: the commands named in the criterion.

## Implementation Guidance
1. **Re-verify the environment**: the Docker daemon, the `m32/*` images, leg 2's evidence, and the default data dir's mtime.
2. **Pin and install Briefcase** in a tool venv under `$M32_BUILD` (not the worktree `.venv`, and not `uv.lock`). Record the version. Read its documentation for the version you pinned: the Linux system-package `--target` builds, system requirements, the AppImage format's status, and how the main module and launcher arguments are set.
3. **Generate the closure pins** from `uv export …`. Use hashes if Briefcase accepts them, otherwise `==` pins (logged).
4. **Write the config template and `build.sh`.**
   - `stage.py --candidate briefcase` stages the copy.
   - `build.sh` writes the Briefcase `pyproject.toml` into the staging root, with `version` set and `sources = ["the_one"]`.
   - It runs `briefcase create/build/package linux system --target <image>` for each target, without signing.
   - The target images are plain `ubuntu:26.04` and `debian:13` (Briefcase builds its own build image from them). Install from the produced `.deb` into leg 2's `baseline` and `bare` images.
5. **Build the unpatched N+1 with `allow_subprocesses = true`, install it in a throwaway container, and probe `sys.executable` and `sys.frozen` first** (AC0), then the launcher behaviour. Then decide AC3 (configuration or patch) and whether gates 1 and 2 need a DD4 patch.
6. **Run the matrix** through `check.sh`: unpatched gates 1 and 2 first; then the patched build (if any) through everything. Add a candidate-neutral harness option only where needed.
7. **The AppImage**: build it if the pinned version offers it, else document N/A.
8. **Fill B's rows and the upkeep paragraph**, run the AC8 checks, update the flight log, and set the leg to `landed`.

## Edge Cases
- **Briefcase's Docker build cannot reach PyPI, or needs network inside its build container**: that is normal for its builds. If the WSL2 Docker network fails, record it and retry once. Never use `--network host`.
- **`sys.executable` is `""`**: this means `allow_subprocesses` did not take effect. Fix the config before measuring anything; `resolve_python()` would return the current directory. (The "app binary" case does not occur with Briefcase's system template.)
- **Hash pinning**: try writing each pin with its `--hash=` flags inline on one `requires` line, or `requirement_installer_args = ["--require-hashes"]`. Fall back to `==` pins (logged).
- **Briefcase refuses `sources` from the staging root, or insists on its own layout**: adapt `build.sh` (staging is ours to arrange) rather than touching the repo layout. Log it.
- **The CLI is not on `PATH` after install** (Briefcase may install only a launcher): record how a user reaches `doctor`, and make `check.sh` find it through a candidate-neutral option. The CLI arrangement is an upkeep point, not a failure.
- **A gate fails for a reason A also hit, and A fixed it in its recipe** (the `gi.overrides` collection): check whether B has the same gap. B installs real packages rather than freezing, so it likely does not. Do not assume either way; measure it.

- **Icons**: Briefcase expects `icon-<size>.png` sizes. Either generate them from `icon-512.png` in `build.sh` (Pillow is in the closure), or accept Briefcase's default for missing sizes and log it.

## Files Affected
- `packaging/briefcase/` (new): the config template, `build.sh`, `README.md`, and `patches/` if needed.
- `packaging/spike/check.sh`, `inner.sh` and `README.md`, only for candidate-neutral options (logged).
- `missions/32-installers-everywhere/flights/01-choose-packaging-toolchain/flight-log.md`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked against the worktree on 2026-10-23:
- `the_one/__main__.py` calls `the_one.main.cli_entry()`; `the_one/main.py::cli_entry` runs `chat` when `sys.argv[1:]` is empty, and `app` runs `the_one.interfaces.app.run`.
- `the_one/platform/env.py::is_frozen` (`sys.frozen` or `sys._MEIPASS`) and `the_one/platform/interpreter.py::resolve_python` (not frozen: returns `Path(sys.executable).resolve()`).
- `packaging/spike/check.sh` invocation, the package-name expectations and `inner.sh::find_ui` are as reported by leg 2's Developer, and appear in the flight log.
