# Leg: windows-recipe

**Status**: ready
**Flight**: [Windows on shared metadata, and one release](../flight.md)

## Objective
The Windows app and installer get one recipe, `packaging/windows/build.ps1`, used both by GitHub and by Concourse. It:
- stages the source at a chosen version;
- renders `product.toml` into the installer;
- freezes from the staged copy.

The installer quits a running app gracefully, with a force fallback, on both install and uninstall.

`windows-packages.yml` gains `full` and `lifecycle` modes. The lifecycle mode proves on a hosted runner:
- the install;
- the upgrade from v0.11.8;
- the window and tray behaviour;
- a graceful upgrade over a running app;
- quitting;
- an uninstall while the app runs.

## Context
- **Flight DDs:**
  - DD2: the graceful upgrade. Candidate (a) is confirmed by leg 1's W4, and the leg adds the uninstall hook.
  - DD3: `[windows]`, `--out`, the `product.iss` include, the staged spec, `stage.py` without git, a per-build stage directory, `/DAppVersion` dropped, the GUID and AppId pins, the probe frozen, the `PATH`-walk tests.
  - DD4: the Concourse task and `fly execute`.
  - DD5: `full`/`lifecycle`, the rows, artifact names, `windows-installer` retention of 14 days, the environment header, the budget.
- **Leg 1's findings** (flight log, "Leg 1 result"):
  - **The identity.** The shipped `AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}` is the effective AppId `{CAEEFB46-…}}`, and the uninstall key is `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}_is1`, with two closing braces. The `AppId` line stays literal and byte-identical (AC3), and the lifecycle reads that key.
  - **The probe's version check was a harness defect.** It read `DisplayVersion` from a single-brace key.
  - **The runner premises:**
    - the runner shows a WebView2 window (W1);
    - it has a tray (W2);
    - `WM_CLOSE` hides to the tray (W5);
    - `ExecAsOriginalUser(... 'quit --wait')`, then the poll, then `KillRunning` drains the server before the first file copy (W4);
    - the Restart Manager alone cannot close a tray app (W3: installer exit 5);
    - v0.11.8 → N works by the force path, with one uninstall entry, no duplicate shortcuts, and data kept (W6).
  - **The runner:** `win22` `20261022.344.1`, ISCC 6.7.1, `EnableLUA=1` `ConsentPromptBehaviorAdmin=0` (admins elevate silently).
- **Leg 2's fix:** `_mark_hidden` makes `GET /api/window/state` report `visible:false` after close-to-tray. It was seen working on Windows in probe run 3. The lifecycle may now use the route as well as native `IsWindowVisible`.
- **Leg 1's lesson:** two hosted dispatches were lost to PowerShell defects that a local run would have caught. Every new or changed `.ps1` gets a `-SelfTest` that runs in a local `mcr.microsoft.com/powershell` container (`m32-pwsh-*`, `--rm`, no `--privileged`, no host network) and again on the runner before the build.
- **Reusable code:** `packaging/windows/probe/probe.ps1` has tested helpers: rows and summary, bounded waits, new-bytes log reads, `Start-App`/`Stop-App` by recorded pid, `EnumWindows`/`IsWindowVisible`, the credential poll, and `Invoke-Installer` with a bounded wait.
  - The probe stays frozen (DD3).
  - Copy what `lifecycle.ps1` needs into a shared `packaging/windows/lib.ps1`, which `lifecycle.ps1` dot-sources. The probe keeps its own copy.
- **Locked closure:** `tests/test_packaging_locked_closure.py` requires `ci/tasks/windows-installer-build.yml` and `.github/workflows/windows-installer.yml` to carry the locked-closure sequence (`uv export … --extra gui … --extra all-llms`, then `pip install … --no-deps`). If the closure install moves into `build.ps1`, that file joins `LOCKED_CLOSURE_REQUIRED`. Its rule 2 scans `.ps1` too. `windows-installer.yml` is deleted in leg 4, not here.
- **macOS precedent:** `packaging/macos/build.sh` never installs the project (no `pip install -e .`): it installs the closure `--no-deps` plus PyInstaller, and the spec puts only `M32_STAGE` on `sys.path`. Windows follows that.

## Inputs
- Legs 1 and 2 are committed (`ff55a1e` is the head at design time).
- `packaging/windows/{the-one.iss, the-one.spec, frozen_entry*.py, README.md}`, `ci/tasks/windows-installer-build.yml`, `packaging/{product.toml, render.py, stage.py}`.
- `fly -t the-one status` was logged in at the flight's start. Re-check it at the leg (tokens expire in about 24 h). If it has expired, ask the operator to log in again.

## Outputs
**Phase 3a** (local and Concourse only, no hosted runs):
- `packaging/product.toml`: a `[windows]` section.
- `packaging/render.py`: `--out FILE`, writing UTF-8 with LF line endings.
- `packaging/windows/product.iss.in`, and `.gitignore` covering `packaging/windows/product.iss`.
- `packaging/windows/the-one.iss`: `#include "product.iss"`, and the hard-coded values replaced. The `[Code]` stays unchanged in 3a.
- `packaging/windows/the-one.spec`: staged.
- `packaging/stage.py`: a fallback that needs no git.
- `packaging/windows/build.ps1` (new): the one recipe, with `-SelfTest`.
- `ci/tasks/windows-installer-build.yml`: calls `build.ps1`.
- Tests:
  - `tests/test_packaging_metadata.py`: the `[windows]` keys, the GUID pin, the rendered effective-AppId-line pin, `--out`, and version agreement between `render.py` and `stage.py`;
  - `tests/test_packaging_locked_closure.py` gains `build.ps1`;
  - Windows `PATH`-walk tests (in `tests/test_macos_runtime_seam.py`'s style, or a new `tests/test_windows_runtime_seam.py`);
  - `stage.py` tests;
  - a `build.ps1` static test.
- `packaging/windows/README.md`.

**Phase 3b** (hosted):
- `the-one.iss` `[Code]`: DD2's graceful quit on install (`PrepareToInstall`) and on uninstall (`CurUninstallStepChanged(usUninstall)`).
- `windows-packages.yml`: `full` and `lifecycle` modes call `build.ps1`, and `lifecycle.ps1` with its `-SelfTest`.
- `packaging/windows/lib.ps1` and `lifecycle.ps1` (new).
- `docs/windows-install.md`: the upgrade (the app is quit for you, gracefully when the running version allows it), the data location, and uninstall-while-running.
- Tests for the new workflow modes.
- The flight log: run ids, minutes and row tables.

## Acceptance Criteria

### Phase 3a
- [ ] **AC1: `[windows]` in `product.toml`.** The keys are `app_guid`, `install_dir_name`, `setup_file_stem`, `cli_executable`, `gui_executable` and `publisher`. Add others only if the `.iss` needs them, and none may clash with an existing key in another section (`render.load` rejects duplicates).
  - `app_guid` is `CAEEFB46-2698-4048-AD9F-0120D0B7174A`, and a test pins that value.
  - Linux and macOS renders are byte-identical before and after. Show it: render every existing template at a fixed version and `SOURCE_DATE_EPOCH`, on the base and the leg, and diff.
- [ ] **AC2: `render.py --out FILE`.** It writes UTF-8 with LF line endings and no BOM, the same text the stdout path writes. Its errors return 1 like today's. Tests cover it, including an `.iss.in` render. The Linux and macOS build scripts keep stdout.
- [ ] **AC3: the rendered include.** `product.iss.in` renders every `#define` the `.iss` needs (name, version, publisher, URL, dir name, exe names, setup stem). The GUID is not a `#define`: the `AppId` line stays literal and a test checks it.
  - `the-one.iss` `#include`s it. The `#ifndef AppVersion` fallback and any `/DAppVersion` use are gone, so the include is the only version source, and a missing `product.iss` is an ISCC error.
  - The effective `[Setup]` lines (`AppName`, `AppVersion`, `AppVerName`, `DefaultDirName`, `DefaultGroupName`, `OutputBaseFilename`) and the `[Icons]` names, after preprocessing, are identical to today's for the same version.
  - **The `AppId` line stays literal in `the-one.iss`** (`AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}`) and never goes through the preprocessor: a test-side expander cannot prove how ISPP treats `{{` next to `{#`. A test pins that the literal line equals `AppId={{` + `app_guid` + `}}` from `product.toml`.
  - **Escaping:** every string `#define` doubles any `"` (ISPP string syntax), and `render.py` refuses an `.iss.in` value with a newline. A test covers this.
  - **The dist path:** `[Files] Source:` uses `{#DistDir}\the-one\*`, with `#ifndef DistDir` → `#error`, and `build.ps1` passes `/DDistDir=…`. A missing value is a clear ISCC error.
  - **The rendered file:** `product.iss` stays at `packaging/windows/product.iss`, gitignored. ISPP searches the including file's directory first, so `build.ps1` deletes it and re-renders it on every build, and no `/I` copy is used.
  - A test proves this without ISCC. It renders the include, substitutes the `#define`s into the `.iss`'s `{#Name}` uses with a small test-side expander, and compares against a checked-in expectation of today's effective lines. That expectation is today's values written in the test, not a generated golden file.
- [ ] **AC4: the staged spec.**
  - Insert `_STAGE` at the front of `sys.path` **before** any `collect_*` call, as the macOS spec does, so `collect_data_files("the_one")` reads the staged copy. `Analysis(["frozen_entry.py"])`, `icon=` and the other `SPECPATH`-relative paths keep resolving from `packaging/windows/`.
  - `tests/test_packaging_winpty_spec.py` (it reads the spec text) must keep passing.
  - Dropping `pip install -e .` is safe because nothing in `the_one/` reads its own distribution metadata (no `importlib.metadata.version("the-one")`; `diagnostics.py` reads only `mcp` and `httpcore2`). Re-grep and record this.
  - `the-one.spec` requires `M32_STAGE`, as the macOS spec does (`SystemExit` with a clear message if unset). Its `pathex` and `sys.path` hold the staged copy and `packaging/` (for `import render`) only, never the repo root.
  - The two exe names come from `render.load`.
  - The version that appears in names comes from the staged `__version__`.
  - Everything else (the hidden imports, `collect_*`, datas, icon, console flags) is unchanged.
  - `py_compile` passes.
  - A test asserts the spec never inserts the repo root, and reads both names from `render`.
- [ ] **AC5: `stage.py` without git.**
  - `--target windows` works.
  - The fallback triggers on **any** failure of `git rev-parse --show-toplevel`: a non-zero exit (for example a worktree's `.git` gitlink pointing at a path that does not exist on the worker, which is what `fly execute` uploads), or `FileNotFoundError` (no git). The outside-the-repo check then uses `REPO.resolve()`, and git is required only when `packaging/<target>/patches/*.diff` exist.
  - Tests cover: no git on `PATH`; a `.git` file pointing at a missing path; a real repo.
  - Tests cover both paths, plus refusing an `--out` inside the repo.
  - The Linux and macOS behaviour is unchanged (their tests pass).
- [ ] **AC6: `build.ps1`, the one recipe.** It takes `-Version` (empty: `__version__`), `-Out` (the parent of the stage and build directories, which must be outside the repo) and `-Python`. It then:
  1. creates or reuses a build venv under `-Out`;
  2. exports the locked closure with `uv export --frozen …` and the same extras as today, and installs it `--no-deps` with hashes;
  3. installs `pyinstaller==6.22.3` (what Windows probe run 3 shipped and the macOS build pins), with the hooks-contrib version recorded;
  4. runs `stage.py --target windows --version V --out <Out>`;
  5. deletes, then renders, `packaging\windows\product.iss` with `render.py --set version=V --out …`. Without `--set`, `render.load` reads the repo's `__version__`, which is wrong for N+1;
  6. freezes with `M32_STAGE` set, `--clean`, and per-version `--workpath <Out>\work-<V>` and `--distpath <Out>\dist-<V>`, so an N+1 build never clobbers N;
  7. runs strict `doctor` with today's by-name needles (`windows-installer.yml`'s list, plus `desktop shell: OK` and `child spawn: OK`);
  8. runs ISCC (located as today, Inno ≥ 6.1 when a version parses, never failing on an unparsed one, from leg 1's fix);
  9. runs ISCC with `/O<Out>\installer-<V>` and `/DDistDir=<Out>\dist-<V>`, checks that the installer file `<setup_file_stem>-<V>.exe` exists, and writes `<Out>\build-<V>.env` (`VERSION`, `SETUP_EXE`, `DIST`).

  The `uv export …--extra gui…--extra all-llms` command and the `pip install …--no-deps` command each sit on one line (no splatting or wrapping), because `tests/test_packaging_locked_closure.py`'s regexes match single lines. `uv export --frozen` runs with the repo root as its working directory.

  It also must:
  - never run `pip install -e .`;
  - check `$LASTEXITCODE` after every native call;
  - throw on any failure;
  - pass `-SelfTest` (argument handling, path validation, the version resolution and the needle list, with no Windows API) in the local pwsh container;
  - be ASCII.
- [ ] **AC7: the Concourse task.**
  - `ci/tasks/windows-installer-build.yml` provisions Python 3.11 and Inno (as today) and calls `build.ps1` with `-Out` set to a directory inside the task's own working directory, a sibling of `repo` such as `build`. It then copies the installer to `installer/`.
  - It records the ISCC version and whether `git` is on `PATH` (`Get-Command git`).
  - `ci/windows-installer.pipeline.yml`'s MinIO step still matches `the-one-setup-*.exe`.
  - `tests/test_packaging_locked_closure.py` passes, with `build.ps1` added to rule 1.
- [ ] **AC8: the `fly execute` proof.** First re-check `fly -t the-one status`, then confirm the Windows worker is `running` (`fly -t the-one workers`) and that no local test gate is running. Then run `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=<scratch dir under $HOME/the-one-m32-evidence/f4/leg3/fly>` from the worktree, once.
  - It succeeds, and the output holds `the-one-setup-<V>.exe`, with `V` = `__version__` (0.11.8) unless the task passes a version.
  - The task log shows strict `doctor` passing with every needle, the ISCC version and git's presence. Save the log to the evidence dir.
  - The installer is not run or published, and the output dir is deleted after its name and size are recorded.
  - If `fly` needs a login, stop and hand back `[BLOCKED:fly-login]`.
  - Before running it, check what `fly execute -i repo=.` will upload: `.venv`, `evals/.cache` and `evals/runs` must be gitignored. Record the upload size.
- [ ] **AC8b: the other consumers of the spec and `.iss`.**
  - **`windows-packages.yml` `mode=probe` is retired.** It exits 1 with "retired after leg 1 (run 40246340174); the product .iss/spec are staged now". `tests/test_windows_packages_workflow.py` is updated (the `/DAppVersion` pin goes; a retired-probe pin comes in), and the `on:` block is unchanged.
  - **`scripts/windows_test_copy.py::op_freeze`** moves to the staged recipe: it runs `stage.py --target windows` into its own out dir and freezes with `M32_STAGE`. Its existing tests pass, and a new one asserts it sets `M32_STAGE`.
  - **`.github/workflows/windows-installer.yml`** is left as is, broken by design until leg 4 deletes it. No tag may be pushed before leg 4, which the flight log records.
  - **A guard test** fails if any file under `ci/`, `.github/`, `scripts/` or `packaging/` (excluding `packaging/windows/probe/` and `windows-installer.yml`) passes `/DAppVersion` or runs `the-one.spec` without `M32_STAGE`.
- [ ] **AC9: the Windows `PATH`-walk tests** (the Flight 3 debrief's item). These are Linux-run unit tests: frozen, `sys.platform` patched to `win32`, and a real `;`-separated `PATH` with `os.pathsep` patched, in the existing `test_windows_alias_shadowing_walks_to_the_real_python` style. They cover only cases not already in `tests/test_platform_interpreter.py` (about lines 86-120) and `tests/test_macos_runtime_seam.py`:
  - `PATH` order across several real interpreters (the first wins);
  - an alias first, then a real one later in `PATH`;
  - a `PATH` entry that is a file, missing, or empty;
  - only `py.exe` on `PATH`: `walk_python_candidates` considers only `python3`/`python`, so this yields the actionable error;
  - no interpreter at all, giving the actionable error text.

  List the cases that turned out to be already covered, and skip them. No new skips.
- [ ] **AC10:** `make test-unit` passes (12 skips) and ruff is clean. Run it only on a quiet host. If another session's browser lanes are running, wait up to 30 minutes, then stop and report rather than run beside them.

### Phase 3b
- [ ] **AC11: graceful quit in the product `.iss`.** `[Code]` holds DD2's sequence, from leg 1's `the-one-probe-quit.iss` `QuitThenKill` (the `M32Tick`/`M32Sleep` externals, `ExecAsOriginalUser(... 'quit --wait', ewNoWait)`, the poll that logs `present` and `gone` with a 90 s bound, a last `tasklist` check, then `KillRunning`). It is called:
  - from `PrepareToInstall`, when `{app}\the-one.exe` exists;
  - from `CurUninstallStepChanged(usUninstall)`, before files are removed.

  `CloseApplications=force` and `RestartApplications=no` stay, as the backstop. Comments say why.
  - **The uninstaller's restrictions:** some functions, such as `ExecAsOriginalUser`, are not available in uninstall-time `[Code]`. Check Inno 6's documentation, and if needed use `Exec` there: the uninstaller runs as the installing admin, the same user in the silent-elevation case. The quit CLI resolves that user's own data dir. Record which call each mode uses and why.
  - The externals `M32Tick`/`M32Sleep` and `Log()` must work in both modes. The 3b compile on the runner, and L9's `/LOG`, prove it.
- [ ] **AC12: `windows-packages.yml` `full`.**
  - Builds through `build.ps1`, then:
    - the frozen `serve` `/api/info` check, asserting the **staged** version (the input, or `__version__`);
    - the single-instance probe (`_select_port`), with `the_one` importable from the stage directory through `PYTHONPATH`, since the project is not installed;
    - uploads the installer as `windows-installer` (14 days, N only).
  - The logs go to `windows-packages-logs`, as today.
  - The `on:` block is unchanged (the test pins it). `probe` mode stays retired (AC8b).
- [ ] **AC13: `windows-packages.yml` `lifecycle`.** `full`, plus N+1 (`render.py --next-version`; built with `build.ps1` reusing the venv, no upload), then `lifecycle.ps1`.
  - `lifecycle.ps1` writes `lifecycle/SUMMARY.txt`:
    - a header like the probe's (the image, the Windows build, ISCC, UAC, elevation, versions);
    - every row seeded `FAIL <id> not-run`;
    - `== lifecycle done` only on normal completion.
  - The fail step requires that line and no `^FAIL`.
  - The rows, each with its PASS rule:
    - **L1 old-to-new:** install the v0.11.8 release silently, start it, create the marker agent, then install N over it. PASS needs:
      - exit 0;
      - the old pid gone;
      - the same `{app}`;
      - exactly one uninstall entry, read from the `}}_is1` key, whose `DisplayVersion` is N;
      - no duplicate `.lnk` files;
      - the marker present;
      - N's `/api/info` version is N.
    - **L2 install and launch:** the Start-menu shortcut exists, `doctor` from `{app}` passes, and `the-one-app.exe` starts with the window natively visible within 60 s and the route `visible:true`.
    - **L3 title bar:** `GET /api/window/chrome` returns 200, and its DWM results are recorded as INFO (Server 2022 reports "dark mode only"). PASS needs 200 plus a parseable body.
    - **L4 close to tray:** after `WM_CLOSE` the window is natively hidden, the route is `visible:false`, and the pid is alive.
    - **L5 second launch:** start a second `the-one-app.exe` (bounded wait of 20 s). The real check is that exactly one app pid remains, the first one; the second process's exit code is INFO. The window is natively visible again, with the route `visible:true`.
    - **L6 geometry:** move and resize the main window through `SetWindowPos` to a target inside the runner's work area, quit with `the-one.exe quit --wait`, then relaunch. The values compared are those in `{data_dir}\window-state.json` after the quit, and the native window rectangle after relaunch (`GetWindowRect`), against the saved values. Tolerance is ±16 px, after the app's own clamps (cite `window_state.py`). The screen size is recorded, and the drain line must appear for the quit.
    - **L7 graceful upgrade:** install N+1 silently while N runs. PASS needs:
      - the `/LOG` shows quit, then `present`, then `gone`, then nothing left, then `KillRunning`, then the first copy;
      - the drain line for N's pid comes before the first copy;
      - N+1's `/api/info` is N+1;
      - `DisplayVersion` is N+1;
      - the marker is present.
    - **L8 quit:** `the-one.exe quit --wait` exits 0, with the drain line and no process left.
    - **L9 uninstall while running:** start the app, then uninstall silently (`unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /LOG=<path>`). The uninstaller re-spawns a temp copy and exits at once, so do not wait on its pid. Poll, bounded, for `{app}` gone, the key gone, and the `/LOG`'s final line. PASS needs:
      - the uninstall `/LOG` shows the quit sequence (from AC11);
      - the drain line;
      - `{app}` gone;
      - no process left;
      - the data dir and its marker kept;
      - the `}}_is1` key gone.
  - **Engineering:**
    - `lifecycle.ps1` dot-sources `lib.ps1`;
    - every wait is bounded, and the global bound comes from `M32_T0`, as in the probe;
    - pids are recorded, and only recorded pids are killed;
    - its `-SelfTest` covers the summary, the rows and the bookkeeping, plus `lib.ps1`'s non-Windows helpers;
    - both pass in the local pwsh container, and the workflow runs both `-SelfTest`s before the build.
- [ ] **AC14: `docs/windows-install.md` and `packaging/windows/README.md`.** Update them for:
  - the build (`build.ps1`, how Concourse and GitHub call it);
  - upgrading (no need to quit first; a running app is closed, gracefully from this version on, and a v0.11.8 app is closed by force once);
  - the data location (`%LOCALAPPDATA%\the-one`, kept on uninstall);
  - uninstalling while running.

  Edits are additive. No guide text may claim more than the runner proved: the Windows 11 tint and the UAC prompt are field-checked (DD11).
- [ ] **AC15 (the Flight Director, outward):**
  - **Run 1 of 4 Windows lifecycle dispatches:** `gh workflow run windows-packages.yml --ref flight/04-windows-and-release -f mode=lifecycle`.
  - All L1-L9 rows PASS, and the `windows-installer` artifact is uploaded.
  - Fixes for red rows follow the Flight 3 rule (product defect, harness defect or runner limit), within the remaining three dispatches.
  - The run ids, minutes and row tables go in the flight log.

## Verification Steps
- AC1-AC5, AC9:
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_packaging_metadata.py tests/test_packaging_locked_closure.py tests/test_windows_packages_workflow.py tests/test_macos_runtime_seam.py <new test files> -x --timeout 30`;
  - the AC1 render diff, shown in the flight log.
- AC6 and AC13's self-tests: in the local pwsh container, `pwsh -NoProfile -File /win/build.ps1 -SelfTest` and `pwsh -NoProfile -File /win/lifecycle.ps1 -SelfTest`, with `packaging/windows` mounted read-only at `/win`. Also `ParseFile` on every `.ps1`.
- AC7-AC8: the `fly execute` output and log in the evidence dir, summarised in the flight log.
- AC10: `make test-unit`, ruff.
- AC11-AC15: the dispatch's `lifecycle/SUMMARY.txt` and the Inno `/LOG`s.

## Implementation Guidance
1. **Two spawns.** Phase 3a is one Developer; it hands back `[HANDOFF:review-needed]` after AC1-AC10. The Flight Director reviews and commits it. Phase 3b is a second Developer, who lands the leg; AC15 is the Flight Director's.
2. **Start 3a from the render.** Write `product.iss.in`, the include and the AC3 expectation test. Then do `stage.py`, the spec, `build.ps1`, and the Concourse task last.
3. **Keep the build's working files out of the repo.** `build.ps1` writes the stage, the venv, PyInstaller's `build`/`dist` (`--workpath`/`--distpath` under `-Out`) and the ISCC output (`/O<Out>\installer`) outside the repo. The single exception is the rendered `product.iss`, which ISCC `#include`s relative to the `.iss` and which is gitignored.
   - Alternatively, have ISCC take the include path through `/I`, or pass a full path to the include, so nothing is written into the repo. Prefer that if it works on paper; record the choice.
   - Today's `[Files] Source: "..\..\dist\the-one\*"` then needs a `#define` for the dist path (`DistDir`) rendered or passed through `/D`, plus a test.
4. **Sharing helpers.** `lifecycle.ps1` reuses `probe.ps1`'s proven helpers through `lib.ps1`. `probe.ps1` is not changed (it is frozen).
5. **No pushes and no dispatches** by Developers. The Flight Director pushes after each phase's review and commit.

## Edge Cases
- **A `product.toml` value with `"` or `;`** would break an `.iss` `#define`: escape it in the template, or have `render.py` reject it for `.iss.in`, with a test.
- **The Concourse worker's persistent state:** the build venv lives under the task's own `-Out`, so each build is fresh, like today's `.buildvenv` (which was in `repo`). Nothing is shared with other builds.
- **`fly execute` uploading a large tree:** check what it uploads (it honours `.gitignore` in a git repo, and the worktree's `.git` is a gitlink). If it would upload `.venv` or `evals/` caches, use `--exclude` or `-i repo=<a git-archive export>`, and record the choice.
- **The single-instance probe after `full`'s `serve`:** it needs the credential from the runner user's data dir, as today.
- **v0.11.8's uninstaller in L1:** the upgrade replaces it. L9 uninstalls with N+1's uninstaller, which carries AC11's hook.

## Citation Audit
Checked at `ff55a1e`:
- `packaging/windows/the-one.iss`: `AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}`, `#ifndef AppVersion`/`#define AppVersion "0.2.0"`, `OutputBaseFilename=the-one-setup-{#AppVersion}`, `Source: "..\..\dist\the-one\*"`, `[Code] KillRunning`/`PrepareToInstall`: verified.
- `packaging/windows/the-one.spec`: `_REPO_ROOT` on `sys.path`, `from the_one import __version__`, `pathex=[_REPO_ROOT]`: verified.
- `packaging/macos/the-one.spec`: `M32_STAGE` required, `pathex=[_STAGE]`; `packaging/macos/build.sh`: no editable install, closure `--no-deps`: verified.
- `packaging/stage.py::repo_toplevel` (always called), `--out` default, `rmtree`: verified.
- `ci/tasks/windows-installer-build.yml`: choco Python 3.11 + Inno, `.buildvenv` in `repo`, `iscc /DAppVersion=$ver`, `Copy-Item $exe "..\installer\"`: verified.
- `tests/test_packaging_locked_closure.py::LOCKED_CLOSURE_REQUIRED`, `EXECUTABLE_SUFFIXES` (includes `.ps1`): verified.
- `packaging/windows/probe/the-one-probe-quit.iss::QuitThenKill`: verified (leg 1, W4 PASS).
- The uninstall key `{CAEEFB46-…}}_is1`: verified in run `40246340174`'s `uninstall-after-N.txt` and `inno-N.log`.
