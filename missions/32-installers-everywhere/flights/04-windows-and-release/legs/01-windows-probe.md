# Leg: windows-probe

**Status**: landed
**Flight**: [Windows on shared metadata, and one release](../flight.md)

## Objective
Build the reusable `windows-packages.yml` workflow with its `on:` block frozen and its `probe` mode working, and its default-branch stub. The probe answers premises W1-W6 on a hosted `windows-2022` runner, and each premise row:
- carries a positive control;
- reads `FAIL not-run` unless its check actually ran.

## Context
- **Flight DD2:** the graceful upgrade design, candidate (a): `ExecAsOriginalUser('{app}\the-one.exe', 'quit --wait')`, then a process-gone poll with its own 90 s bound, then `KillRunning` always. Elevation is field-only. W3 uses a variant without `KillRunning`.
- **Flight DD5:** the workflow shape, artifact names, the environment rule (header fields), ports, W1-W6, budget.
- **Flight DD7:** the stub pattern (a `.github/`-only PR to `main`).
- **Flight 3's lessons:**
  - A probe that can silently fall back is not a probe. Every row's success must depend on its intended path having run.
  - Native signatures and behaviours come from the runtime, not from a hard-coded guess.
- **The `macos-packages.yml` precedent:**
  - the `Paths` step's mode `case`;
  - the `Runner evidence` step;
  - the anchored `^FAIL` "Fail on a failed or missing result" step;
  - the logs upload;
  - `packaging/macos/probe/macos-packages.stub.yml` as the stub's source.
- **Probe builds use today's unstaged recipe,** the same as `windows-installer.yml`'s install-and-freeze steps: the `uv export` closure with `--no-deps`, `pip install -e . --no-deps`, `pyinstaller packaging/windows/the-one.spec`. `probe` mode stays frozen as a historical mode once leg 3b moves `full`/`lifecycle` to the staged build (DD3).
- **The windowed app's log:** `ensure_stdio_streams` (`the_one/platform/env.py`) writes `{data_dir}\logs\the-one-app.log`; on Windows the data dir is `%LOCALAPPDATA%\the-one`. The drain is `the_one/interfaces/desktop/shell.py::_graceful_shutdown`. The Developer must find a log line that appears only on a graceful drain, or add none and rely on uvicorn's shutdown lines in that file, and record which.

## Inputs
- `origin/main` at `f98f2c7`. The branch `flight/04-windows-and-release` is at the planning commit `eb75143`.
- `packaging/windows/the-one.iss`, `the-one.spec` and `frozen_entry*.py` are unchanged; this leg does not modify them.
- The `v0.11.8` GitHub release has asset `the-one-setup-0.11.8.exe` (`gh release view v0.11.8`).

## Outputs
- **`.github/workflows/windows-packages.yml`:**
  - its `on:` block (below) is frozen from this leg on;
  - `mode=probe` is implemented;
  - `full` and `lifecycle` exit 1 with "lands in leg 3b".
- **`packaging/windows/probe/windows-packages.stub.yml`:** the stub, an identical `on:` block plus a trivial job.
- **`packaging/windows/probe/probe.ps1`:** the probe driver.
- **`packaging/windows/probe/the-one-probe-rm.iss`:** today's `.iss`, but no `KillRunning`, and `CloseApplications=yes`. It is for W3.
- **`packaging/windows/probe/the-one-probe-quit.iss`:** today's `.iss` plus DD2's candidate (a) `[Code]` (quit, then poll, then `KillRunning`). It is for W4.
- **`packaging/windows/probe/README.md`:** what each row means and how to dispatch.
- **Evidence:** a logs artifact `windows-packages-logs` (7 days) holding `probe/SUMMARY.txt`, the Inno `/LOG` files, app logs, screenshots, `doctor` output, `tasklist` snapshots and registry dumps.
- **The flight log:** the dispatch's run id, its minutes, and the row table.

### The frozen `on:` block
```yaml
on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version to build (empty: the version in the_one/__init__.py)"
        type: string
        required: false
        default: ""
      mode:
        description: "full, lifecycle or probe"
        type: choice
        options: [full, lifecycle, probe]
        default: full
  workflow_call:
    inputs:
      version:
        description: "Version to build (empty: the version in the_one/__init__.py)"
        type: string
        required: false
        default: ""
      mode:
        description: "full, lifecycle or probe"
        type: string
        required: false
        default: full
```
`workflow_call` deliberately has no `outputs`. Callers find artifacts by name (DD7). Keep `permissions: contents: read` at the top. The job reads releases through `GH_TOKEN: ${{ github.token }}`, which `contents: read` allows on this private repo.

## Acceptance Criteria
- [x] **AC1:** `windows-packages.yml` passes `actionlint` (if available, or a YAML parse plus a review of every expression otherwise). Its `on:` block is byte-identical to the stub's, and a unit test (`tests/test_windows_packages_workflow.py`) pins that equality and the mode list.
- [x] **AC2:** `probe` mode builds N (the input version, or, when the input is empty, `render.py --next-version` of `__version__`; today `0.11.9.dev1`, so N never equals the released 0.11.8), passed as `/DAppVersion`. It then builds the two variant installers at N+1 and N+2 (`--next-version` of N and of N+1), and runs `probe.ps1`. Before any build, an in-job step parses `probe.ps1` with `[System.Management.Automation.Language.Parser]::ParseFile` and fails on any error, so a syntax error costs a minute, not the dispatch.
  The probe's frozen app reports `__version__` for all three builds, because the build is unstaged. The probe tells the installers apart by their `AppVersion` (the uninstall key's `DisplayVersion` and the `/LOG`), never by `/api/info`. It tells the old v0.11.8 app from today's by `GET /api/window/state`: 404 on v0.11.8, which has only `/api/window/focus` and `/api/window/chrome`, and 200 on today's build.
- [x] **AC3:** `probe/SUMMARY.txt` opens with a header recording:
  - the runner image name and version (`$env:ImageOS`, `$env:ImageVersion`);
  - the Windows build (`[Environment]::OSVersion`, plus `UBR` from the registry);
  - the ISCC version (from `ISCC.exe /?` or its file version);
  - the UAC state (`EnableLUA`, `ConsentPromptBehaviorAdmin`);
  - whether the process is elevated;
  - `whoami`;
  - the Python and PyInstaller versions.
- [x] **AC4:** every premise row is one of `PASS <id> <text>`, `FAIL <id> <text>` or `INFO <id> <text>`.
  - Every W row is seeded as `FAIL <id> not-run` before any step runs, and is replaced only by the code path that performed its check. `Set-Row` throws on an unknown id.
  - **Window truth is native.** On Windows, `GET /api/window/state`'s `visible` is `state.tracked_visible`. The tray hide (`shell.py::_close_to_tray`) never clears it, and it is set at the show call even if no window appeared. So W1 and W5 judge on `IsWindowVisible` for the handle found by `EnumWindows` filtered by pid and title, plus the screenshot, and record the route's `visible` as an INFO row. The route defect is fixed in leg 2 (`window_control`), not here.
  - **Log reads take only new bytes.** `the-one-app.log` is appended across launches. Every log check records the file length before its action and reads only the bytes after it, opened with `FileShare.ReadWrite`.
  - `SUMMARY.txt` ends with `== probe done`; without it the job fails.
  - The rows:
    - **W6 (old-to-new apparatus):**
      - the v0.11.8 release installer downloads (`gh release download v0.11.8 -p 'the-one-setup-0.11.8.exe'`) and installs silently (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=…`);
      - the installer polls (bounded) for `%LOCALAPPDATA%\the-one\api-credential` before the first API call;
      - its windowed app starts, and `/api/info` reports `0.11.8` while `/api/window/state` returns 404 (the positive control that this is the old app);
      - N (today's `.iss`) then installs silently over it while it runs.
      - **PASS** needs all of: the download succeeded; the v0.11.8 install exit code was 0; the old app answered as above; N installed with exit code 0; afterwards the uninstall key's `DisplayVersion` is N and `/api/window/state` returns 200 once N is launched.
      - INFO rows record the install dir before and after, the count of uninstall-registry entries whose `DisplayName` matches `GleepGlorp AI`, the Start-menu `.lnk` files, the force path's evidence in the `/LOG`, and that a data marker survives. The marker is an agent created through `POST /api/agents` before the upgrade and read back after.
    - **W1 (window):**
      - N's `the-one-app.exe` starts, and within 60 s `GET /api/window/state` reports the main window visible;
      - a full-screen screenshot (`System.Drawing` `CopyFromScreen`) is saved. Positive control: the PNG's pixel variance is above a flat-colour threshold, and a window titled `GleepGlorp AI` exists (`EnumWindows`/`Get-Process`'s `MainWindowTitle`).
    - **W2 (tray):**
      - `doctor`'s `tray:` line;
      - whether `Shell_TrayWnd` exists;
      - PASS needs `Shell_TrayWnd` present (`FindWindow`) and no `System tray unavailable` line in the new bytes of the app log since launch.
      - `doctor`'s `tray:` line is INFO only: on Windows it is static text keyed on `sys.platform` (`the_one/diagnostics.py`). The state route's tray field is `null` on Windows (`tray_mode` is set only on linux and darwin), so it is never a PASS condition.
    - **W5 (close to tray):** `WM_CLOSE` posted to the main window's handle (`PostMessage`, found by pid and title). Within 10 s `IsWindowVisible` is false and the pid is alive. Positive control: the handle was found, it was visible before, and the post returned success. The route's `visible` is an INFO row.
    - **W4 (graceful quit):**
      - *Positive control first:* `{app}\the-one.exe quit --wait` from the runner shell. The pid exits, and the drain line (AC5) for that pid appears in the app log's new bytes.
      - Then: relaunch, and run `the-one-probe-quit.iss`'s N+1 installer silently over the running app. In the `/LOG` and the app log, record the order:
        - the installer's quit call;
        - the app's drain line;
        - the process exit;
        - `KillRunning`;
        - the first file copy.
      - **The ordering** comes from a concurrent watcher in `probe.ps1`. It polls the app log's new bytes, the installer's `/LOG` and the app pid about every 250 ms, and stamps each event's first-seen time from one clock. The summary states the resolution.
      - **The quit variant's poll** logs `present` at iteration 0 and `gone` when the processes are gone. It runs a `tasklist` check just before `KillRunning` and logs whether anything was left. W4 FAILs if the `/LOG` shows no `present` before `gone`, which would mean the poll passed vacuously.
      - **PASS** needs all of: `present` then `gone`; the drain line for the app's pid before the first file copy; and "nothing left" before `KillRunning`.
      - An INFO row records that elevation here is `runneradmin` with UAC off (field-only, DD2).
    - **W3 (the Restart Manager alone):** relaunch, and run `the-one-probe-rm.iss`'s N+2 installer silently over the running app. INFO rows record:
      - the `/LOG` lines about the Restart Manager and closing applications;
      - the order of `PrepareToInstall` against the RM check;
      - whether the app was closed (and whether gracefully: did its drain line appear);
      - whether `{app}` files were replaced (the exe's file version or timestamp);
      - the installer's exit code.
      - **A bounded installer:** every installer in the probe runs with a recorded pid and a bounded `WaitForExit` (W3's `CloseApplications=yes` against a tray app may hang on a file in use). On timeout, the probe kills that pid and records `INFO W3 installer did not finish`.

      W3's verdict row is `INFO`, not PASS/FAIL: it describes behaviour. Its `not-run` sentinel is still `FAIL`.
  - The final step is a silent uninstall (`unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /LOG=…`). INFO rows record whether `{app}` is gone, any leftover process, and that the data dir remains.
- [x] **AC5:** the drain evidence is uvicorn's `Finished server process [<pid>]`, matched to the app's pid (with `Application shutdown complete.` before it), in the new bytes of `{data_dir}\logs\the-one-app.log`.
  - The windowed exe's stdout and stderr are `None`, so `ensure_stdio_streams` appends both to that file. Uvicorn is created with `log_level="info"` in `shell.py`, and its handlers write to `sys.stderr`.
  - A drain (`should_exit`, then the join) logs it; `taskkill /F` does not.
  - No product log line is added in this leg.
  - The README and the flight log name the line, and the Developer cites the code path that makes it appear only on a drain.
- [x] **AC6:** the "Fail on a failed or missing result" step fails the job on:
  - a missing `SUMMARY.txt`;
  - a missing `== probe done`;
  - any `^FAIL` line;
  - a failed build step.

  The logs upload runs `if: always()`.
- [x] **AC7:** the job has `timeout-minutes` (at most 60) and every step has its own timeout. Every wait in `probe.ps1` is bounded and logs its own timeout as a FAIL or INFO, never a silent continue. The whole probe has a global bound below the step's timeout.
- [x] **AC8:** neither `pwsh` nor `actionlint` is on this host, so the real parse check is AC2's in-job step. Locally, the Developer records that both tools are unavailable.
  - The two `.iss` variants differ from `the-one.iss` only in the stated `[Code]` and `[Setup]` changes plus the path rewrites: `SetupIconFile=..\installer-assets\the-one.ico`, `Source: "..\..\..\dist\the-one\*"`, `Source: "..\installer-assets\the-one.ico"`.
  - Each build's output dir is set with `/O<dir>`, written `//O<dir>` under Git Bash, as `//D` is today.
  - The Developer shows the `diff`s in the flight log.
- [x] **AC9:** `make test-unit` passes (expected skips: 12, or 14 under netns) and ruff is clean.
- [ ] **AC10 (with the Flight Director, outward):**
  - the stub PR is merged to `main`;
  - one `probe` dispatch is run (a second only if the first is lost to a harness defect);
  - its run id, minutes and the full row table are in the flight log;
  - no `FAIL … not-run` row remains;
  - each W row's result is classified (premise holds / premise fails / harness defect).

## Verification Steps
- AC1: `python -m pytest tests/test_windows_packages_workflow.py -x --timeout 30`; `actionlint .github/workflows/windows-packages.yml` (or the recorded fallback).
- AC2-AC7: read the workflow and `probe.ps1`. After the dispatch, `gh run download <id> -n windows-packages-logs`, then read `probe/SUMMARY.txt` top to bottom.
- AC8: the parse command and the `diff`s in the flight log.
- AC9: `make test-unit`; `ruff check the_one/ tests/ scripts/ evals/` and `ruff format --check …`.
- AC10: `gh run view <id>`; the flight-log table.

## Implementation Guidance
1. **The workflow:**
   - Copy `macos-packages.yml`'s skeleton: the `Paths` mode `case`, `Runner evidence`, logs upload and the anchored fail step.
   - `runs-on: windows-2022`. Bash defaults, as `windows-installer.yml` uses (Git Bash), with PowerShell steps where needed (`shell: pwsh`).
   - Concurrency: group `windows-packages`, `cancel-in-progress: false`.
   - The probe's build steps reuse `windows-installer.yml`'s install and freeze commands verbatim (closure `--no-deps`, editable `--no-deps`, PyInstaller, the `test -f`), then ISCC for the three installers with `/DAppVersion` and an `/O` output dir per installer (so names cannot collide), located the same way.
2. **`probe.ps1`:**
   - one function per row;
   - a `Set-Row` helper that replaces the pre-written `FAIL <id> not-run` line;
   - `try/finally` so the summary is always written;
   - bounded `Wait-Until` helpers.
   - Read the credential from `$env:LOCALAPPDATA\the-one\api-credential` (one line, the bearer token) for every API call. Use `Invoke-RestMethod` with `-TimeoutSec`. Port 8484 on the runner (DD5).
   - Record pids. Kill only recorded pids, and only on the runner.
   - Poll (bounded) for the credential file after each first launch.
   - The data marker: `POST /api/agents` with `{"name": "probe-marker"}`. `AgentConfig` needs only `name`, and `provider_config_id` defaults to `None`, so no provider is needed. Read it back with `GET /api/agents/probe-marker`. If the POST is refused, record the response and FAIL W6 with it, rather than guess.
   - Capture `Shell_TrayWnd`/`EnumWindows` results to files, so a "no desktop" result carries evidence.
   - Download the v0.11.8 installer into its own directory, apart from the build outputs.
3. **The variant `.iss` files:** copy `the-one.iss` into `packaging/windows/probe/`, and fix the relative `Source:` and icon paths (`..\..\..\dist\…`, `..\installer-assets\…`) so they resolve from the new directory.
   - **The quit variant:** in `PrepareToInstall`:
     - if `{app}\the-one.exe` exists, `if not ExecAsOriginalUser(ExpandConstant('{app}\the-one.exe'), 'quit --wait', '', SW_HIDE, ewNoWait, RC) then Log(...)` (it returns False when the exe is missing, which is the v0.11.8 case);
     - the poll also waits for the quit CLI itself, which is a `the-one.exe` in `{app}`: say so in a comment. The 90 s bound is above the CLI's own 5 s plus 75 s;
     - poll up to 90 s for `the-one-app.exe` and `the-one.exe` to be gone (for example `Exec` of `tasklist /FI "IMAGENAME eq the-one-app.exe" /NH` through `cmd /c … | find /I`, with `Sleep(1000)`);
     - then `KillRunning`;
     - `Log(…)` lines at each stage, so the `/LOG` shows the order.
   - **The RM variant:** drop the `KillRunning` call, and set `CloseApplications=yes`.
4. **The stub:** `packaging/windows/probe/windows-packages.stub.yml` has a header comment like the macOS stub's, and one job that echoes and exits 0 on `ubuntu-latest`. The Flight Director opens the stub PR from it, so nothing from this leg's other files goes to `main`.
5. **Do not dispatch, push or open PRs.** Hand back with `[LAND:leg]`. The Flight Director does the outward steps (AC10) and records the dispatch, then spawns a Developer to read the evidence if needed.

## Edge Cases
- **The v0.11.8 install** may show a post-install launch checkbox. Silent mode skips it (`skipifsilent`), so the probe launches the app itself.
- **The silent install of N over a running v0.11.8:** today's `KillRunning` kills it. That is the expected force path. Record it, do not FAIL it.
- **ISCC output names collide** between N, N+1 and N+2 if they share `OutputDir`: use `/O<dir>` per build.
- **`MainWindowTitle`** may be empty for a hidden window. Find handles by `EnumWindows` filtered by pid.
- **Between rows, the app may already have exited.** Every row starts by establishing its own precondition (launch if not running, and wait for visible) and records it.
- **A runner without a desktop session:** W1 FAILs with the evidence (an all-black screenshot, no window). W2, W5 and W4's positive control still run where they can (W4 needs only the server). This is the flight's divert condition, so the evidence must be complete.

## Citation Audit
Checked at `eb75143`:
- `packaging/windows/the-one.iss::PrepareToInstall`, `KillRunning`, `CloseApplications=force`, `Source: "..\..\dist\the-one\*"`, `SetupIconFile=installer-assets\the-one.ico`: verified.
- `.github/workflows/windows-installer.yml`'s install/freeze steps and the ISCC location logic: verified.
- `the_one/platform/env.py::ensure_stdio_streams` → `settings.data_dir / "logs" / "the-one-app.log"`: verified.
- `the_one/interfaces/desktop/shell.py::_graceful_shutdown`: verified.
- `the_one/main.py`'s quit (`--wait`, 75 s): verified.
- `packaging/macos/probe/macos-packages.stub.yml`: verified.
- `/api/window/state`: verified (`the_one/interfaces/web/app.py`).
