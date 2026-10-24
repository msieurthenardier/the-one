# Leg: windows-cost

**Status**: in-flight
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
Price the Windows side of each candidate. On paper: what keeping PyInstaller and Inno Setup costs, against moving to Briefcase's MSI. On a disposable hosted Windows runner: build Briefcase's MSI, install today's released Inno installer, install the MSI over it, and record what happens. Then hand the operator a downloadable MSI, with a backup step, a checklist and a rollback, for the real-machine try in the morning.

## Context
- **Flight decisions:**
  - DD7: the Windows probe runs because Briefcase survived Linux; one hosted Windows job; the operator runs the installer on their own PC (Windows 11 Home, no Sandbox), with backup and rollback; the paper half always;
  - DD2: strict gates;
  - DD3: staging and the pinned closure;
  - DD4: staged patches only.

  Read the flight log's Evidence Table and the `linux-briefcase`, `macos-probe-prepare` and `macos-probe-run` entries first.
- **The operator is asleep.** This leg's autonomous part ends with the MSI ready for download, and the operator's checklist, backup and rollback written in the flight log. **The operator's install is not part of this leg's acceptance.** The Flight Director runs it as a guided step in the morning, alongside `decision-hat`, and appends the result.
- **The workflow** `.github/workflows/packaging-probe-windows.yml` is a stub on `main` (merged in #305), with a `candidates` choice input. Fill in its steps **on the flight branch only**: `gh workflow run --ref` runs the branch's copy, and the trigger and inputs must stay identical to `main`'s, or a new PR would be needed.
  - The job: `windows-2022`, `timeout-minutes` of 40 or less, a per-step cap, `contents: read`, no secrets, a `concurrency` group.
  - **Only the MSI and the logs are uploaded**, `retention-days` of 7 or less. A draft release asset is the fallback if the artifact upload fails on quota (DD7). It must be a draft, never published, and named `m32-probe-<sha>`. Using it needs the `contents: write` permission, so it is only a fallback, logged if used.
- **Today's Windows install, the "before" state for the upgrade test:**
  - `packaging/windows/the-one.iss`: fixed `AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}`, `PrivilegesRequired=admin`, `DefaultDirName={autopf}\GleepGlorp AI`, `CloseApplications=force`, `RestartApplications=no`.
  - The released installer is the latest `v*` release's asset on the releases page (`gh release download --pattern 'the-one-setup-*.exe'`; read-only, no token needed beyond the workflow's `GITHUB_TOKEN` for a private repo).
  - It installs silently with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.
- **B on Windows (Briefcase 0.4.6), unverified premises to probe first:**
  - The MSI is built by WiX through `briefcase package windows --adhoc-sign`, or with no signing at all; record which.
  - The app's executable is GUI-subsystem unless `console_app = true`. A GUI-subsystem stub may swallow `doctor`'s output. **Try redirecting `doctor`'s output to a file first.** If nothing arrives, record that B needs `console_app` or a second console app for its CLI, as an upkeep cost (A has the two-exe split today). Do not switch the whole app to `console_app = true`, which would show a console window on every launch.
  - `sys.executable` is the app exe in the install dir, and `app_packages` is beside it. So patch 02 needs a Windows clause, added in the same additive way as the macOS one: narrow, `_bundle_dir()` returning `None`, the Linux and macOS clauses byte-identical. The faked-layout check in `packaging/briefcase/check-env-layouts.py` gains a Windows case.
  - Briefcase likely forces binary installs on Windows, as on macOS, so `--no-binary proxy-tools` may be needed. Rehearse on Linux with `pip download --platform win_amd64 --python-version <B's Windows support Python> --only-binary :all: …`, as leg 4 did for macOS.
  - `pywinpty` and `pywin32` have Windows wheels (the planning audit).
- **What the hosted job records** (each step in its own log; nothing aborts the later steps):
  1. The MSI build log, its size and its file name.
  2. **A fresh install of the MSI** (`msiexec /i … /qn /l*v msi-install.log`), then:
     - the install path;
     - the Start-menu entries;
     - the Uninstall registry entries (`HKLM\…\Uninstall\*`, `HKCU\…\Uninstall\*`, filtered by display name);
     - `doctor` (strictly scored with `score.py`'s `score_doctor`);
     - gate 2 (the resolved interpreter, which must be `setup-python`'s and never the app's directory);
     - `serve` start-up on port 8490 with a scratch data dir, `GET /api/live`;
     - `rotate-api-credential` with no override, whose path is under `%LOCALAPPDATA%\the-one\` (platformdirs on Windows).
  3. **The upgrade-over-Inno scenario, on the same disposable runner, after uninstalling step 2's MSI:**
     - install the released Inno installer silently, run its `the-one.exe version`, and seed data (start its `serve`, then create one agent through the API with the credential read from its data dir);
     - stop it, then install the MSI;
     - record: whether there are two Add/Remove entries or one; both installs' directories; the Start-menu entries (one "GleepGlorp AI" or two); which executable the Start-menu shortcut now runs; and whether the seeded agent reads back through the MSI install's `serve` (the shared data dir `%LOCALAPPDATA%\the-one\`);
     - finally, uninstall the MSI and record what remains (the Inno install, the data dir).
  4. Upload the MSI and the logs.
- **The paper half**, written in the flight log under `windows-cost`, one paragraph per item, each with a code or doc citation:
  - **A (keep PyInstaller and Inno):**
    - the existing two-exe split;
    - Restart Manager handling;
    - the stable AppId upgrade path;
    - `pywinpty`'s helper-exe collection (squawk 0162);
    - WebView2 and the tinted title bar (the M25 F5 chrome);
    - the per-push Concourse build;
    - what "one metadata source" would take (the `.iss` reading a generated include or `/D` defines).
  - **B (Briefcase MSI):**
    - what the hosted job showed;
    - AppId versus the MSI upgrade code (no in-place upgrade from Inno; the migration options: an Inno-uninstall-first custom action, or a one-time documented step);
    - Restart Manager (WiX `CloseApplications` or `util:CloseApplication`);
    - the tray, the WebView2 and title-bar chrome under Briefcase's stub;
    - `pywinpty`'s helper exes under `app_packages`;
    - the CLI story;
    - what moving the Concourse Windows build to Briefcase would need.
- **The operator's morning step**, written in the flight log as a numbered guide that the Flight Director walks through:
  1. Back up the data dir: `robocopy "%LOCALAPPDATA%\the-one" "%USERPROFILE%\the-one-backup-m32" /E`, or the PowerShell equivalent. Confirm the real path with `the-one.exe doctor` or Explorer first; do not guess.
  2. Quit GleepGlorp AI from the tray.
  3. Download the MSI artifact from the run and install it.
  4. The checklist: one or two Start-menu entries; Add/Remove Programs entries; does the app open from the new shortcut; are the existing chats, agents and providers there; `doctor` (from a console, if B has a console path); close-to-tray; the tinted title bar; a second launch focuses the existing window.
  5. **Rollback:** uninstall "GleepGlorp AI" (the MSI entry) from Add/Remove Programs. If the Inno install was removed or broken, reinstall the latest release's `the-one-setup-*.exe` from the releases page. If the data changed, quit the app and restore the backup with `robocopy … /MIR` back to `%LOCALAPPDATA%\the-one`.

- **Findings from the leg design review (folded in; these override anything above that conflicts):**
  1. **`stage.py` on Windows:** use `git apply` on `win32` as well as `darwin`; GNU `patch` is not on `PATH` under pwsh. The workflow sets `git config --global core.autocrlf false` before checkout, so the diffs and sources keep LF.
  2. **Install scope, a Flight Director call:** a **per-user** MSI. Set `system_installer = false` in B's Windows config section, if 0.4.6 honours it (confirm from the generated `.wxs`), and pass `MSIINSTALLPERUSER=1 ALLUSERS=2` on every `msiexec` in the job. Per-user avoids the real collision, which is the MSI landing in `C:\Program Files\GleepGlorp AI` beside the Inno install. (The AppId is not the collision: the MSI's upgrade code is a uuid5 of the bundle, unrelated to Inno.) The `.wxs` is dumped into the logs. The operator's guide says which wizard option to pick, if a wizard asks.
  3. **Step order and uploads:** separate workflow steps, each with its own cap: build; **upload the MSI and its SHA-256 (`if: always()`)**; fresh-install checks; the upgrade-over-Inno scenario; upload the logs (`if: always()`); the fail-on-FAIL step. `gh release download` gets `GH_TOKEN: ${{ github.token }}`; `contents: read` suffices for a same-repo release.
  4. **`doctor` from the GUI stub:** `Start-Process -PassThru -RedirectStandardOutput <out> -RedirectStandardError <err>` (two different files), `Wait-Process -Timeout`, `PYTHONUTF8=1`, files read with `-Encoding utf8`, and `rc=N` appended for `score_doctor`. If stdout is `None` under the stub, `serve` may crash on uvicorn's `isatty` too. Record it either way (a CLI cost for B).
  5. **Patch 02's Windows clause:** a layout marker only, never gated on `sys.platform`: the exe's suffix is `.exe` (case-insensitive) and `<exe dir>/app_packages` is a directory; `_bundle_dir()` returns `None`. `check-env-layouts.py` builds a real tree (`X/src/GleepGlorp AI.exe` and `X/src/app_packages`), plus near-misses: no `app_packages`; `app_packages` with a non-`.exe` stub; a venv `Scripts/python.exe`. The "byte-identical" check is on the patched file's existing clauses, not the hunk (the `is_frozen` return line gains an `or`). The job lists the install dir's top level, any `._pth` file, and `PATH`. If an embeddable `python.exe` sits in the stub's directory and that directory is on `PATH`, gate 2 shows it.
  6. **Upgrade-scenario hygiene:**
     - delete `%LOCALAPPDATA%\the-one` between the fresh-install step and the Inno scenario;
     - build the MSI at version `0.11.9.dev1` (or `0.11.9` if WiX refuses a dev version; logged), so the scenario is a real version step;
     - seed the agent as `inner.sh` does (a bearer `POST /api/agents`), with `curl.exe` or `Invoke-RestMethod`;
     - stop `serve` with `Stop-Process -Force`;
     - never run two builds' servers at once.
  7. **Build environment:**
     - a short build root (`C:\m32`) against `MAX_PATH`;
     - time Briefcase's WiX and rcedit downloads;
     - `--no-binary proxy-tools` on Windows too (binary-only by default);
     - the Linux `win_amd64` pip rehearsal uses the same marker filtering as `macos-resolution-rehearsal.py`, so `pywinpty` and `pywin32` are included;
     - note that the embeddable Python ignores `.pth` files (`pywin32`'s path setup), which the `mcp sdk` gate may reveal.
  8. **`candidates`:** this job builds only B; A is today's Inno path. With `A` selected, it logs "A: the existing Inno installer, not built here" and skips. The input stays as declared on `main`.
  9. **AC1's diff:** `git fetch origin main` first. The `on:` block, comment lines included, stays byte-identical to `main`'s.
  10. **The operator's guide, rewritten for safety** (PowerShell syntax throughout):
      1. Quit GleepGlorp AI from the tray. Confirm `Get-Process the-one-app -ErrorAction SilentlyContinue` returns nothing.
      2. Back up: `$src = "$env:LOCALAPPDATA\the-one"; $bak = "$env:USERPROFILE\the-one-backup-m32"; robocopy $src $bak /E` (exit codes 0 to 7 mean success). Check that `$bak` holds the database.
      3. Download the MSI and check its SHA-256 against the run's hash file.
      4. Install, per-user. If SmartScreen appears, choose "More info", then "Run anyway".
      5. The checklist.
      6. **Rollback:** `msiexec /x "<path to the downloaded .msi>"` (unambiguous, even though both installs show as "GleepGlorp AI"). If the Inno install is broken, reinstall the latest `the-one-setup-*.exe` from the releases page. Restore data only if needed, with the app quit: `robocopy $bak $src /MIR`, with the variables exactly as defined in step 2, so the direction cannot be swapped.

## Inputs
- The flight branch at its current head; the Briefcase recipe and patches; `score.py`; `macos-checks.sh` (a model for the checks script).
- `gh` authenticated. Dispatching is the Flight Director's job; this leg only prepares, then reads.

## Outputs
- `packaging/briefcase/`: a Windows config section, patch 02's Windows clause, `build-windows.ps1` (or `.sh` under Git Bash), and the Windows case in `check-env-layouts.py`.
- `packaging/spike/windows-checks.ps1`: the Windows checks and the upgrade scenario.
- `packaging/spike/stage.py`: `git apply` on `win32` (finding 1), with the Linux path unchanged.
- `.github/workflows/packaging-probe-windows.yml`, filled in on the flight branch, with its trigger and inputs unchanged from `main`.
- The flight log: a `### windows-cost` entry with the rehearsal, the paper half, and the operator's morning guide. After the Flight Director's dispatch, the hosted results and Evidence Table rows (Windows, B).

## Acceptance Criteria
- [ ] **AC1 — The workflow is capped, publishes nothing by default, and keeps `main`'s trigger and inputs.** `actionlint` is clean. The diff of the `on:` block against `main`'s copy is empty.
- [ ] **AC2 — B's Windows recipe, rehearsed on Linux.**
  - The Windows pip resolution (`win_amd64`, B's support Python, binary-only with the `proxy-tools` exception if needed) succeeds, logged.
  - Patch 02's Windows clause is additive, with the Linux and macOS clauses byte-identical (hunk diff shown).
  - `check-env-layouts.py` passes for Windows, macOS, Linux, a source install, and a near-miss Windows path.
  - The PowerShell scripts parse cleanly (`pwsh -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile(…)"`, if `pwsh` can be obtained without root; otherwise record that they are unparsed).
- [ ] **AC3 — The paper half** is in the flight log, with every item in Context covered and cited.
- [ ] **AC4 — The operator's morning guide** (backup, install, checklist, rollback) is in the flight log, with exact commands and paths.
- [ ] **AC5 — Nothing outward-facing by the Developer.** No dispatch, push, PR or commit.
- [ ] **AC6 — After the Flight Director's dispatch and a follow-up Developer pass:** the hosted results (Context, "What the hosted job records" items 1 to 4) are in the flight log and the Evidence Table, each with a log excerpt, and the MSI download link is recorded for the operator.

## Verification Steps
- AC1: the pinned `actionlint`; `diff <(git show origin/main:.github/workflows/packaging-probe-windows.yml | sed -n '/^on:/,/^[a-z]/p') <(sed -n '/^on:/,/^[a-z]/p' .github/workflows/packaging-probe-windows.yml)`.
- AC2: the rehearsal output in the flight log.
- AC3-AC4: the flight log.
- AC5: `git status`, and no `gh workflow run`/`gh pr` in the session.
- AC6: the run's artifact and the flight-log entry.

## Implementation Guidance
1. Re-read the flight log. Confirm B's macOS findings (the stub's `sys.executable` and argv forwarding) from `macos-probe-run`, since Windows likely mirrors them.
2. The Windows config section, patch 02's Windows clause, the layout check, and the pip resolution rehearsal.
3. `build-windows.ps1` and `windows-checks.ps1`, with every external call time-limited (`Start-Process -Wait` with a timeout, or `Wait-Process -Timeout`) and every result logged. A failure is recorded, and the script moves on.
4. Fill the workflow on the flight branch.
5. Write the paper half and the operator's guide. Update the flight log. **Stop at `[HANDOFF:review-needed]`** (not `[LAND:leg]`) so the Flight Director can review, commit, push and dispatch. AC6 is completed by a follow-up pass after the run.

## Edge Cases
- **The released Inno installer is missing or unreachable from the runner**: record it, skip the upgrade scenario (item 3), and keep item 2.
- **WiX is missing or Briefcase needs to download it**: Briefcase fetches WiX itself; record the time. If it fails, B's Windows build is a FAIL with the log.
- **`msiexec` returns 1603**: capture the verbose MSI log's last 200 lines, and continue to the upload.
- **The MSI artifact is too large for artifact storage**: use the draft-release fallback (Context), logged.

## Files Affected
- `packaging/briefcase/` (the Windows section, patch 02, `build-windows.ps1`, `check-env-layouts.py`).
- `packaging/spike/windows-checks.ps1` (new); `packaging/spike/stage.py` (`git apply` on `win32`).
- `.github/workflows/packaging-probe-windows.yml` (the flight branch only).
- The flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked on 2026-10-24: `packaging/windows/the-one.iss` (AppId line 35, `PrivilegesRequired` line 61, `CloseApplications`/`RestartApplications` lines 69-70, `DefaultDirName` line 39); `.github/workflows/packaging-probe-windows.yml` on `main` at `df30153` (a stub with a `candidates` choice input); patch 02 (the Linux and macOS clauses as committed at `f6a546e`).
