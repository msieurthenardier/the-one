# Flight Log: Windows on shared metadata, and one release

**Flight**: [Windows on shared metadata, and one release](flight.md)

## Summary
*(written at landing)*

---

## Reconnaissance Report

Sources: the Flight 3 debrief (`../03-macos-app/flight-debrief.md`, Recommendations and Action Items) and the mission's Flight 4 bullets. Walked against `f98f2c7`, 2026-10-25.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| R1: per-platform boot policy out of `shell.py` | confirmed-live | `shell.py` run/_boot: 11 `darwin` + 2 `win32` reads; `window_control.py`: 4 `darwin` reads (100, 165, 170, 228) | DD1, leg 2 (operator: in flight) |
| R2: probes fail loudly with a positive control | confirmed-live (a process rule) | n/a; it applies to this flight's probe | DD5's W1-W5 rows, `FAIL not-run` |
| R3: strict version grammar end to end; `[windows]` in `product.toml` | confirmed-live | `render.py::RELEASE_RE`; `product.toml` has no `[windows]`; `pyproject.toml` `version = "0.11.8"` hard-coded | DD3, DD6 |
| R4: probe Inno's close-running-app behaviour first | confirmed-live | `the-one.iss` `CloseApplications=force` + `KillRunning` (`taskkill /F`) | DD2, leg 1 (W3, W4) |
| R5: the pywebview canary and a `lifecycle` dispatch in the bump procedure | confirmed-live | squawk 0262 open; no doc names the procedure | DD9 (0262), leg 4 |
| A1: budget the macOS runs, one spare | confirmed-live | n/a | DD8: 4 runs |
| A2: consolidate the packaging workflows and the shell helpers (Flight 3 DD8's deferral) | partially-satisfied in scope | three workflows, two with `workflow_call`; `windows-installer.yml` has neither dispatch nor `workflow_call` | DD7 composes them; shell-helper merging is deferred again (DD3's "not done here") |
| A3: Windows `PATH`-walk regression tests | partially-satisfied | `tests/test_macos_runtime_seam.py::test_windows_alias_shadowing_walks_to_the_real_python` is the only one | leg 3 adds the rest |
| A4: contributor check additions (zsh/nvm, logout, quit during boot) | confirmed-live | `tests/behavior/macos-app-install.md` (draft, 12 steps) lacks them | DD10, leg 4 |
| A5: squawks 0260, 0261, 0262 | confirmed-live (all `open`) | `squawks/026{0,1,2}-*.md` | DD9 (operator: all three) |
| M1: dynamic `pyproject` version, after Mission 31 merges | confirmed-live; its precondition was amended | Mission 31 still active; `uv.lock` records `version = "0.11.8"` | DD6; additive, rebase on `main` |
| M2: tag-triggered release of all four behind the audit; a dry run first | confirmed-live | `windows-installer.yml` is the only tag workflow | DD7, DD8 |
| M3: the contributors' check on real Macs | confirmed-live | no run log exists | DD10, leg 6 |

No item was found already satisfied. Nothing is retired.

---

## Flight Director Notes

### Planning (2026-10-25)
- **The operator's answers:**
  - Release: "lets just cut a regular (minor) release at the end, Ill wait for confirmation before we close it. If we need to iterate we can cut patches."
  - Contributors: "just publish as part of a regular release, contibutors can download."
  - Windows: "Thats fine, ill upgrade locally after the tests just the like contributors will and report any issues."
  - Boot-policy refactor: "do it in flight."
  - Gate: "the real v release is the gate."
  - Follow-up answers: "amend the charter, we can release during this flight but only after as verified as we can get it"; dry run first; squawks 0260, 0261 and 0262; "I'll log fly in for fly execute".
- **Charter amendments made in the planning commit:** Mission 31's two "no release" lines are annotated (not rewritten) with the exception. Mission 32's matching constraint is annotated, and its "release vehicle" open question is resolved.
- **The macOS upgrade test for contributors:** with no second release yet, the dry run's `.dmg` (14-day retention) serves as N and the release as N+1. If it has expired, that step runs at the first patch release.
- **Design review (Architect, Opus), cycle 1: approve with changes.** Three high issues:
  - the Windows freeze could not carry a staged version, so DD3 now freezes from `stage.py`;
  - UAC is off on the runner, so DD2's elevation half is field-only, and DD11 proposes a two-step operator upgrade;
  - the v0.11.8 → new upgrade was never rehearsed, so DD5 gains an old-to-new row and W6.
  - Plus 17 medium and low items, all applied: the `shell.py` count, lazy policy selection, behaviour equivalence, 0261 as phase 2b, an early macOS run, a later `release.yml` stub, N+2 deferred, the 0260 fixture with no golden file, `--out`, the lock lanes, environment pins, per-leg re-checks, publish hardening, artifact names, phases, small items.
- **Cycle 2: approve with changes.** One high issue: `stage.py` dies without git, which `fly execute` and possibly the Windows worker lack, so leg 3a adds a no-git fallback and a per-build `--out`.
  - Medium: tag-path input fallbacks and a YAML test; the uninstall-time quit; each lane's uv version; row-to-phase attribution.
  - Low: 14-day `windows-installer` retention, leg 6 order, the PATH-walk tests' owner, `/DAppVersion` dropped.
  - All applied. That was the last allowed cycle, so the flight goes to the operator.
- **Approved (2026-10-25), operator: "approved, I've logged in".** The Windows field upgrade takes DD11's two-step form as written (v0.11.8 → `0.12.0.dev1` → `v0.12.0`). `fly` is logged in; it is re-checked at leg 3a.
- **The plugin notice:** mission-control 1.2.3 is available (1.2.2 installed). The operator was told; the Flight Director does not update plugins.

---

### Execution
- **Started 2026-10-25.** Phase file `.flightops/agent-crews/leg-execution.md` loaded (Developer Sonnet; Reviewer Haiku, or Sonnet for security-sensitive diffs). The flight is marked `in-flight`.
- **Leg 1 (`windows-probe`) is tiered high-risk.** Its `on:` block becomes an interface that `release.yml` will call. A wrong probe costs a hosted run, as Flight 3's did. So it gets a Developer design review.
- **The operator's go for leg 1's outward steps (2026-10-25):** "Yes, all three": push the branch; open and merge (once lint passes) the stub PR adding only `windows-packages.yml`; up to 2 probe dispatches.
- **Leg 1 design review (Developer, Sonnet): approve with changes.** Three high issues:
  - N equalled v0.11.8. N is now `--next-version`, and the old app is told apart by a 404 on `/api/window/state`.
  - The state route's `visible` is wrong for a tray-hidden window on Windows, so W1 and W5 now judge on native `IsWindowVisible`.
  - The drain line could match stale log lines. The evidence is now uvicorn's pid-matched `Finished server process`, read from new bytes only, with a concurrent watcher for the ordering.
  - Plus: a fail on a vacuous poll, bounded installers, W6's PASS rule, the credential poll, and an in-job `ParseFile` step.
  - The changes follow the reviewer's own recommendations, so the Flight Director judged a second cycle unnecessary.
- **A product defect found in the flight's path:** on Windows, `GET /api/window/state` keeps `visible: true` after close-to-tray. `shell.py::_close_to_tray` hides the window but never clears `state.tracked_visible`. DD5's lifecycle "state hidden" row depends on this, so it is fixed in leg 2 (`window_control` and the boot policy) with a unit test, not logged as a squawk.

## Leg Progress
### windows-probe (leg 1)
Status: landed (Developer pass; outward steps AC10 are the Flight Director's).

**Files added** (nothing existing in `packaging/windows/` was touched):
- `.github/workflows/windows-packages.yml` (frozen `on:` block; `probe` mode; `full` and `lifecycle` exit 1 with "lands in leg 3b"; Git Bash default shell, `pwsh` for the parse and probe steps; concurrency group `windows-packages`; job 60 min and a timeout on every step; `windows-packages-logs` artifact, 7 days)
- `packaging/windows/probe/windows-packages.stub.yml`, `probe.ps1`, `the-one-probe-quit.iss`, `the-one-probe-rm.iss`, `README.md`
- `tests/test_windows_packages_workflow.py` (7 tests: `on:` byte equality with the stub, inputs and mode list, no outputs, permissions/concurrency/timeouts, the 3b placeholder, probe seeding and `== probe done`, the anchored `^FAIL` check)

**The drain line.** Uvicorn's `Finished server process [<pid>]`, matched to the app's pid, read from the new bytes of `%LOCALAPPDATA%\the-one\logs\the-one-app.log`. Code path: `uvicorn.Server.serve()` (`uvicorn/server.py` ~l.96-101 in the venv's uvicorn) logs it only after `await self.shutdown()` returns; the desktop shell builds the server with `log_level="info"` (`the_one/interfaces/desktop/shell.py` l.610) and `_graceful_shutdown` (l.~266-275: `server.should_exit = True`, then `thread.join`) is what lets `serve()` reach it. The windowed exe has no stdout/stderr, so `ensure_stdio_streams` (`the_one/platform/env.py` l.81-104) points both at that file, line-buffered. `taskkill /F` ends the process before it can log. No product log line added. W4 also uses the positive control (`the-one.exe quit --wait`) so a missing line reads as "not observable" rather than a pass.

**Deviations from the leg text (judgement calls).**
- API calls use `Invoke-WebRequest -SkipHttpErrorCheck` (not `Invoke-RestMethod`) because the HTTP status (404 vs 200) is the evidence.
- The RM variant keeps the unused `KillRunning` procedure (smaller diff); only its call is removed.
- `choco install innosetup` is only a fallback when ISCC is not found (the runner ships it).
- ISCC output dirs are `$RUNNER_TEMP/m32-build/installers/{n,q,r}`, passed `//O<dir>` (forward-slash paths via `cygpath -m`).

**Tool availability (AC8).** `pwsh` and `actionlint` are not on this host (`which` finds neither), so `probe.ps1` was only reviewed by hand; the real parse check is the workflow's in-job `Parser::ParseFile` step. YAML of both workflow files parses with PyYAML and every `${{ }}` expression was reviewed (they only use `inputs.*`, `steps.*.outcome`, `github.token`, `runner.temp`). `probe.ps1` is pure ASCII (pinned by the test).

**AC8 diffs against `the-one.iss`** (`diff the-one.iss probe/the-one-probe-rm.iss`):
```
0a1,3
> ; PROBE VARIANT (Mission 32 Flight 4 leg 1, W3): the-one.iss with CloseApplications=yes and no
> ; KillRunning call, so the Restart Manager alone decides what happens to a running app.
> ; Only [Setup] CloseApplications, PrepareToInstall and the three relative paths differ.
50c53
< SetupIconFile=installer-assets\the-one.ico
---
> SetupIconFile=..\installer-assets\the-one.ico
69c72
< CloseApplications=force
---
> CloseApplications=yes
88c91
< Source: "..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
---
> Source: "..\..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
92c95
< Source: "installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion
---
> Source: "..\installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion
130c133,134
<   KillRunning;
---
>   // PROBE (W3): the Restart Manager alone. KillRunning is deliberately NOT called here.
>   Log('rm-variant: PrepareToInstall ran; no KillRunning in this variant');
```
(`diff the-one.iss probe/the-one-probe-quit.iss`, refreshed after the review fixes):
```
0a1,3
> ; PROBE VARIANT (Mission 32 Flight 4 leg 1, W4): the-one.iss plus flight DD2 candidate (a) in [Code]:
> ; quit --wait as the original user, a bounded poll for the processes to be gone, then KillRunning.
> ; Only PrepareToInstall (and its helpers) and the three relative paths differ.
50c53
< SetupIconFile=installer-assets\the-one.ico
---
> SetupIconFile=..\installer-assets\the-one.ico
88c91
< Source: "..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
---
> Source: "..\..\..\dist\the-one\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
92c95
< Source: "installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion
---
> Source: "..\installer-assets\the-one.ico"; DestDir: "{app}"; Flags: ignoreversion
128c131,166
< function PrepareToInstall(var NeedsRestart: Boolean): String;
---
> // PROBE (W4, flight DD2 candidate (a)): ask the running app to quit gracefully, poll until it is
> // gone (bounded), then KillRunning always. Every stage logs a line so /LOG shows the order.
> // tasklist through cmd + find: find exits 0 when the image name is in the list.
> function ImageRunning(const Image: String): Boolean;
> var
>   RC: Integer;
> begin
>   Result := False;
>   if Exec(ExpandConstant('{sys}\cmd.exe'),
>           '/C tasklist /FI "IMAGENAME eq ' + Image + '" /NH | find /I "' + Image + '"',
>           '', SW_HIDE, ewWaitUntilTerminated, RC) then
>     Result := (RC = 0);
> end;
> 
> // the-one.exe is watched as well as the-one-app.exe: the quit CLI IS a the-one.exe in {app}, and
> // it holds a file open until it has seen the app go (its own bound is 5 s plus 75 s, below 90 s).
> function AppsRunning: Boolean;
> begin
>   Result := ImageRunning('the-one-app.exe') or ImageRunning('the-one.exe');
> end;
> 
> // Declared here under unique names so this compiles whether or not Inno provides them as built-ins.
> // Note: ExecAsOriginalUser (used below) needs Inno Setup 6.1 or newer; the workflow fails the ISCC
> // step with a clear message below that, and the probe header records the ISCC version.
> function M32Tick: Cardinal;
> external 'GetTickCount@kernel32.dll stdcall';
> 
> procedure M32Sleep(Ms: Cardinal);
> external 'Sleep@kernel32.dll stdcall';
> 
> procedure QuitThenKill;
> var
>   RC, I: Integer;
>   Started: Cardinal;
>   Present: Boolean;
>   Exe: String;
129a168,201
>   Exe := ExpandConstant('{app}\the-one.exe');
>   if FileExists(Exe) then
>   begin
>     Log('quit-call: ExecAsOriginalUser ' + Exe + ' quit --wait');
>     if not ExecAsOriginalUser(Exe, 'quit --wait', '', SW_HIDE, ewNoWait, RC) then
>       Log('quit-call: ExecAsOriginalUser returned False, RC=' + IntToStr(RC))
>     else
>       Log('quit-call: started');
>   end
>   else
>     Log('quit-call: ' + Exe + ' does not exist, nothing to ask (an install without the quit command)');
> 
>   Started := M32Tick;
>   I := 0;
>   Present := AppsRunning;
>   if Present then
>     Log('quit-poll: present (iteration 0)')
>   else
>     Log('quit-poll: absent at iteration 0 (nothing was running)');
>   while Present and ((M32Tick - Started) < 90000) do
>   begin
>     M32Sleep(1000);
>     I := I + 1;
>     Present := AppsRunning;
>   end;
>   if Present then
>     Log('quit-poll: timeout after 90 s, processes still present')
>   else
>     Log('quit-poll: gone (iteration ' + IntToStr(I) + ')');
>   if AppsRunning then
>     Log('quit-poll: something left before KillRunning')
>   else
>     Log('quit-poll: nothing left before KillRunning');
>   Log('quit-killrunning: calling KillRunning');
130a203,208
>   Log('quit-killrunning: done');
> end;
> 
> function PrepareToInstall(var NeedsRestart: Boolean): String;
> begin
>   QuitThenKill;
```

**Tests.** `tests/test_windows_packages_workflow.py`: 7 passed. `make test-unit` (host quiet: load 0.36, no pytest/run-tests processes before the run): 7411 passed, 12 skipped, 2987 deselected (the expected 12). `ruff check` and `ruff format --check` over `the_one/ tests/ scripts/ evals/`: clean. No browser tests needed. Not dispatched, pushed or committed.

**For the Flight Director (AC10).** Open the stub PR from `packaging/windows/probe/windows-packages.stub.yml` (copy to `.github/workflows/windows-packages.yml` on a `.github/`-only branch from `main`), then `gh workflow run windows-packages.yml --ref flight/04-windows-and-release -f mode=probe`. Record the run id, minutes and row table below. Risks worth watching on the first run: the data dir assumption (`%LOCALAPPDATA%\the-one`; the probe logs a recursive search for `api-credential` if it is not there), and `POST /api/agents` for the W6 marker (a refusal is recorded and FAILs W6 with the response).

**Leg 1 review fixes (post-review, before the single hosted dispatch).**
- `the-one-probe-quit.iss`: `GetTickCount`/`Sleep` now declared as uniquely named kernel32 externals (`M32Tick`, `M32Sleep`); comment notes `ExecAsOriginalUser` needs Inno 6.1+. The ISCC step (now `shell: pwsh`) fails clearly when ISCC is below 6.1; probe.ps1's header already records the ISCC version. The RM-variant diff is unchanged; the quit-variant diff above is refreshed.
- ISCC step: pwsh, native `/DAppVersion=` and `/O<dir>` (no MSYS mangling), `$LASTEXITCODE` and `Test-Path` per build, timeout 8 -> 15 min.
- Job budget: probe.ps1 bounds itself to min(GlobalSeconds, M32_T0 + 45 min - now); probe step timeout 42 min as a hang backstop; arithmetic recorded in the workflow comment. (Used 45 min rather than 50: M32_T0 is set up to ~4 min after job start, so 45 leaves >= 11 min.)
- probe.ps1: `gh release download` runs as a process with a 120 s bounded wait and kills its recorded pid; W4's control calls `Stop-App` first; `== probe done` is written only on normal completion, `== probe aborted: <reason>` otherwise; still pure ASCII.
- README stub wording fixed; test pins full/lifecycle `exit 1`, the pwsh ISCC step and `$LASTEXITCODE` checks, and the job-relative bound. AC1-AC9 ticked in the leg file; AC10 left open.

- **Dispatch 1 lost: ISCC version gate.** Run 40242850115, about 3 minutes; the freeze succeeded. The "Build the three installers (ISCC)" step failed before compiling: ISCC.exe's FileVersion read 0.0.0.0 on windows-2022 (ImageVersion 20261022.344.1) and the review-fix version gate failed on it. Classification: harness defect introduced by a review fix, not a product result. Fix: the version is resolved best-effort (ISCC ProductVersion, ISCmplr.dll, registry DisplayVersion, `ISCC /?` banner), every attempt logged and exported as `M32_ISCC_VERSION` (read by probe.ps1's header); the step fails only on a parsed version below 6.1, and an unknown version continues because the quit variant's compile is then the check.
  - Review follow-up: GITHUB_ENV now gets only the single-line resolved `M32_ISCC_VERSION=<ver|unknown>` (attempts are logged with Write-Host, whitespace-collapsed and truncated; a multi-line banner would have broken the env file), and Test-Ver returns the matched version instead of callers reading `$Matches` across function scope (which made every run report unknown).

- **Leg 1 checkpoint review (Reviewer, Haiku; the diff touches no security-sensitive surface):**
  - Cycle 1 was not confirmed. Three blocking items: undeclared `GetTickCount`/`Sleep` in the quit variant, too short an ISCC step, and the job-budget arithmetic. All fixed, together with the non-blocking items.
  - Cycle 2: `[HANDOFF:confirmed]`.
  - Accepted, not fixed:
    - A1: the probe step's 42-minute backstop counts from the step's own start, so only a hang past the in-script bound could reach the job cap;
    - A2: the tests pin strings, not the bound's arithmetic;
    - A3: the wording of `== probe done` when the bound cut rows short (they stay `FAIL not-run`, so the job is red anyway).
- **Leg 1, probe dispatch 1 (`40242850115`): lost to a harness defect,** about 3 minutes. The freeze passed. The ISCC step's Inno version gate, added at review, read `ISCC.exe`'s `FileVersion` as `0.0.0.0` and refused to compile. A Developer is fixing it (a best-effort version read; fail only on a parsed version below 6.1). Dispatch 2 is the leg's last allowed probe run.
- **Leg 1, probe dispatch 2 (`40243446243`): lost to probe bookkeeping,** about 6 minutes. Build, freeze and all three ISCC builds passed; `probe.ps1` then aborted at once with `Add-Info: unknown row id 'W6'`, and the SUMMARY's six row lines were blank. The header it did write: `iscc: 6.7.1`; `uac: EnableLUA=1 ConsentPromptBehaviorAdmin=0`; `elevated: True`; `whoami: runnervma5ucf\runneradmin`; Windows NT 10.0.20348.0 UBR=5761; image win22 20261022.344.1; Python 3.11.9, PyInstaller 6.22.3. **EnableLUA=1 with ConsentPromptBehaviorAdmin=0 means UAC is on but an admin elevates silently**, so the runner never shows a prompt and cannot stand in for a prompting-admin or standard-user machine; that keeps DD2's elevation question field-only. The old W4 info text ("UAC off") was wrong and now says this.
  - **Root cause:** PowerShell variable names are case-insensitive, and the script's top level (outside any function) is script scope. The main section assigned `$rows = @(...)`, which IS `$script:Rows`, so it replaced the seeded row table (an ordered hashtable of `FAIL <id> not-run`) with an array of hashtables. `Contains('W6')` on that array was false (hence the throw) and `$script:Rows[$id]` on it gave nothing (hence the blank row lines, which also hid the not-run rows from the reader). The abort message named only the message text, not where it came from.
  - **Fix:** main-section variables renamed (`$mPlan`, `$mRow`); `Write-Summary` now tolerates a lost or damaged row table (any row it cannot read is written as `FAIL <id> not-run (the row table lost this row)`); the per-row catch no longer lets a bookkeeping failure abort the probe (`Add-Info`/`Set-Row` inside it are wrapped); abort and row-threw text come from `Get-AbortText` (message plus `$_.InvocationInfo.PositionMessage`, folded to one line, so it names the file, line and statement); the global-bound arithmetic is a function (`Get-EffectiveGlobalSeconds`); the Win32 `Add-Type` block, `System.Drawing`/`Forms` and the `%ProgramFiles%`/`%LOCALAPPDATA%` reads are guarded or defaulted so the script loads on Linux; the header's registry reads use `-ErrorAction Stop` inside their try.
  - **Rehearsal (new, so this class is caught on Linux):** `probe.ps1 -SelfTest` (all other parameters optional then) runs without any Windows-only API: a PowerShell AST check that no top-level variable shares a name (case-insensitively) with a `$script:` variable; seeding, `Write-Header` and the six `FAIL not-run` lines; `Set-Row`/`Add-Info` for every id, unknown id and bad status throwing; row order; the row-threw record; the abort path (six rows still shown, one `== probe aborted:` line carrying the failure and `file:line`, no done line); the normal path (`== probe done` last, six PASS); a destroyed row table; the bound arithmetic against a fake `M32_T0` (7 cases: 100 s, 1000 s, 2700 s, 3000 s in, empty, non-numeric, smaller request); `Get-FileLen`/`Read-NewBytes` on a temp file (missing, from 0, only the bytes after an offset with the file held open for write, no new bytes, rotation past the end); `Get-KeyLines` with CRLF; `Wait-Until` (true, timeout, throwing condition, global bound). A new workflow step, "Probe self test" (pwsh, before the freeze and the ISCC step), runs it on the runner too.
  - **Commands and results (host has no pwsh; all in the disposable container `m32-pwsh-selftest`, image `mcr.microsoft.com/powershell:latest`, default bridge, no `--privileged`, removed with `--rm`):**
    - `docker run --rm --name m32-pwsh-selftest -v "$PWD/packaging/windows/probe:/probe:ro" mcr.microsoft.com/powershell:latest pwsh -NoProfile -File /probe/probe.ps1 -SelfTest` -> 51 `ok` lines, `SELFTEST PASSED`, exit 0.
    - Mutation proof: the same script with `$mPlan` renamed back to `$rows` -> `FAIL no top-level variable shares a name with a $script: variable ($rows at line 919, $rows at line 927)`, `SELFTEST FAILED (1)`. (The first version of that check compared names with the `script:` prefix still on and missed the bug; the mutation run caught that.)
    - `[System.Management.Automation.Language.Parser]::ParseFile` over `probe.ps1` -> `parses clean (7802 tokens)`; over the ISCC step's `run:` text (extracted with a small python/yaml helper into a temp file) -> `parses clean (645 tokens)`.
    - The ISCC step's `Test-Ver`/`Try-Ver` (the text between `function Test-Ver` and `$vi = (Get-Item`, dot-sourced into a harness) -> `HELPERS OK`: `6.7.1` -> `6.7.1`; `0.0.0.0`, `0.0`, empty and a no-digit string -> `$null`; `6.1` -> `6.1`; a multi-line banner and a multi-line raw value -> the first parsed version (`6.7.1`, `6.2.0`); `Try-Ver` on zeros and on a throwing block leaves `found` null, a good value sets it, a later value does not replace it, attempts are recorded.
    - `.venv/bin/python -m pytest tests/test_windows_packages_workflow.py -x --timeout 30 -q` -> 12 passed (two new tests: the `-SelfTest` switch and its step before the build; no top-level `$rows`).
  - Not covered by the rehearsal (needs Windows): `Invoke-Installer`, the process and window code, `Start-App`, the Win32 calls, and the real `Test-Row*` bodies. Dispatch 3 is therefore still the first run of those, but their bookkeeping calls are now the tested ones.
  - Review follow-up: on Windows a missing `ProgramFiles` or `LOCALAPPDATA` now throws (the `fake-*` fallback applies only off Windows, for `-SelfTest` on Linux); the test file is ruff-clean; self test still `SELFTEST PASSED`, ParseFile clean.
- **Leg 2 (`desktop-boot-policy`) is tiered high-risk** (lifecycle and boot sequence). Its design review (Developer, Sonnet) returned approve with changes:
  - High: the policy is pure data (an import-time function reference would break monkeypatches and close an import cycle); the macOS run attribution is weaker than stated.
  - Medium: the pywebview facts that settle 2b's design; a fourth `Other` policy (the Linux policy differs from today's fallthrough); `_mark_hidden` as the single writer; out-of-scope reads stated.
  - Low: bind the policy once in `run()`; a fuller guard; the test list; AC12's exact commands.
  - All applied. 2a and 2b are separate spawns, with 2a reviewed and committed before 2b. 2b is one flag (`splash_hidden_until_loaded`), so the spare macOS run can bisect. A blank L1 screenshot reads as inconclusive, and 0261 then waits for the contributors.
  - The changes are the reviewer's own recommendations, so no second cycle.
- **A rule slip, recorded:** the leg 2 design reviewer ran one `ls` on a `site-packages` directory under `/home/cprch/projects/the-one/.venv` (Mission 31's checkout) before noticing. It listed a directory; nothing was read, run or changed. Later spawns are told again to use only the worktree's `.venv`.

### desktop-boot-policy (leg 2), phase 2a

**AC2 mapping table** (written before the code moved). Old line numbers are at `8676392`. `P` = `BootPolicy`; values are Windows / Linux / macOS / Other.

| # | Old site | Decision | Hook / flag | Values |
|---|---|---|---|---|
| 1 | shell 286 `_webview_available` | skip the gi probe | `webview_assumed_present` | T / F / T / F |
| 2 | shell 557 | tray mode set before the loop | `initial_tray_mode` | None / None / "dock" / None |
| 3 | shell 674 `first_launch_size(.., sys.platform)` | platform input to sizing (only `"win32"` matters there) | `first_launch_platform` | "win32" / "linux" / "darwin" / "other" |
| 4 | shell 705 | tint the splash border before first show | `splash_border` | T / F / F / F |
| 5 | shell 729 `_splash_blocked` | no splash destroy in quit states | `splash_blocked_in_quit_states` | F / F / T / F |
| 6 | shell 783 `_abort_if_quit` | quit in boot stops without destroy | `quit_in_boot_stops_without_destroy` | F / F / T / F |
| 7 | shell 848 | hold the main window hidden until its page loads | `wait_for_page_before_show` | F / F / T / F |
| 8 | shell 879 | native show fallback (else re-raise) | `native_show_fallback` | T / F / F / F |
| 9 | shell 906 | no tray (dock) | `tray.skip` | F / F / T / F |
| 10 | shell 908 | detect a tray before building one | `tray.detect` | F / T / F / F |
| 11 | shell 928 | record the detected mode | `tray.records_tray_mode` | F / T / F / F |
| 12 | shell 933 | record "failed" on a tray error | `tray.records_tray_mode` (same flag as 11) | F / T / F / F |
| 13 | shell 947 | a quit at publish time is left to the terminate path | `publish_quit_left_to_terminate` | F / F / T / F |
| 14 | shell 960 | boot error asks the app to terminate | `boot_error_terminates` | F / F / T / F |
| 15 | shell 990 | install the dock before the loop | `installs_dock` | F / F / T / F |
| 16 | shell 997 | path S after the loop | `runs_path_s` | F / F / T / F |
| 17 | shell 1027 | browser-fallback notification | `browser_fallback_notification` | F / T / F / F |
| 18 | window_control 100 | visibility from the native state | `native_visibility` | F / F / T / F |
| 19 | window_control 165 | path S answer in `quit_desktop` | `quit_after_loop_stopped_answers_window` | F / F / T / F |
| 20 | window_control 170 | quit through the dock terminate | `quit_via_dock_terminate` | F / F / T / F |
| 21 | window_control 228 | focus through the dock | `focus_via_dock` | F / F / T / F |

Notes: 11 and 12 share one flag (they can never diverge: both record into `state.tray_mode`), as do 9 to 11 in the `TrayPlan(skip, detect, records_tray_mode)` tuple. 6 (old 783) and 13 (old 947) stay two flags as the leg asked, as do 19 and 20 (old 165 and 170). All 21 became flags with no behaviour change, so the divert criterion was not reached. `Other` reproduces today's fall-through (gi probe, plain `build_tray`, re-raise, no notification); Linux differs on four of these.

**Implementation.** `the_one/interfaces/desktop/boot_policy.py` (new, stdlib only: no native imports): frozen `BootPolicy` dataclass, `TrayPlan` named tuple, `WINDOWS`, `LINUX`, `MACOS`, `OTHER`, and `current()` (the only platform read). `session_state.py`: `_policy` cleared in `_set_defaults` (so `reset()` clears it) and a lazy `policy` property (with a setter for tests). `shell.run()` binds `policy = state.policy` once right after `state.reset()`; `_boot`'s closures use that binding; `_webview_available` reads `state.policy`. `window_control` reads `state.policy` in its four sites. AC8: `window_control._mark_hidden()` added (the only writer of `tracked_visible = False`); `_close_to_tray` calls it after a successful `hide()` (not after a failed one); `_no_tray_hide` calls it instead of the direct assignment. `git grep -n "sys.platform"` over `shell.py` and `window_control.py` prints nothing (AC3).

**Tests added** (`tests/test_boot_policy.py`, new): the decision table (one parametrised case per flag, plus the tray plans, a full-field coverage check, `Other` is not Linux, frozen, `current()` per platform string, stdlib-only imports); lazy `state.policy` and `reset()`; `window_control` reading the policy with no `run()` after a platform patch (macOS native read, then Windows tracked read); `run()` binding the policy once after its reset (a stale policy does not survive; macOS sets `tray_mode` "dock"); the AC8 `tracked_visible` tests at the non-GTK backend level (hide then False; then tray Show, boot show and `focus_window` each give True; a failed hide leaves it; `_no_tray_hide` goes through `_mark_hidden`). `tests/test_desktop_session_state.py`: the defaults and reset tests gain "`policy` is unset" assertions (`_policy is None`) and `reset()` is exercised after a policy read. `tests/test_desktop_split_guard.py`: `_mark_hidden` added to the moved-names list; the new AST guard `find_policy_violations` (`sys.platform` under any `import sys as x`, `from sys import platform`, `getattr(sys, "platform")`, `os.name`, `from os import name`, the `platform` module, `policy.name`, `getattr(policy, "name")`, `isinstance`/`type` on a policy, `policy is/== <instance>`), its real-tree test, a parametrised catches-each-form test and an allows-flag-reads test.

**AC7, changed existing tests: none.** Every existing desktop test (shell, tray, takeover, window_state, macos_dock, macos_dock_shell, macos_runtime_seam, session_state, split guard) passed unmodified, including the `sys.platform` monkeypatches: they patch before the first policy read in the test, and the autouse reset clears the policy around each test. (Two assertion additions to `test_desktop_session_state.py`, above, are additions, not changes.)

**AC4 falsification.** Temporarily appended `def _x(policy): return sys.platform == "darwin" or policy.name == "macos"` to `window_control.py`; `tests/test_desktop_split_guard.py` failed with `window_control.py:287: policy.name` and `window_control.py:287: sys.platform` (1 failed, 32 passed); reverted (`git diff` shows only the intended changes).


**Verification.** Host check before the unit tier: another session's `agents` and `mcp` browser lanes were running (load 6); waited about 4 minutes until `ps` showed no pytest or run-tests, then ran. Desktop slice (`test_desktop_split_guard`, `test_boot_policy`, `test_desktop_shell`, `test_desktop_session_state`, `test_desktop_tray`, `test_desktop_takeover`, `test_window_state`, `test_macos_dock`, `test_macos_dock_shell`, `test_macos_runtime_seam`): all green (340 before the new tests; 98 in the three files touched). `make test-unit`: `7466 passed, 12 skipped, 2987 deselected` in 373 s (12 skips as expected; includes the pywebview canary). `ruff check` and `ruff format --check` clean on every file this phase touched (`tests/test_windows_packages_workflow.py` has an unrelated E501 from the concurrent workflow work, not touched here).

**2a green** (uncommitted, awaiting the Flight Director's review): AC1-AC8 done, AC11 unit tier and ruff done for 2a. 2b (AC9-AC10), AC12 and AC13 not started.
- **The operator's go for probe dispatch 3 (2026-10-25):** "Yes, one more". It comes from the flight's Windows spare, leaving 5 of 8 (4 lifecycle, 1 spare), and runs only after `probe.ps1 -SelfTest` passes in a local pwsh container. Dispatch 2 (`40243446243`) was lost to a probe bookkeeping defect: a case-insensitive name clash between `$rows` and `$script:Rows`. Two of two approved probe runs went to probe-script defects, which a local rehearsal now covers.

#### Leg 1 result: probe dispatch 3 (`40246340174`, head `2641bf6`, 2026-10-25 23:47-23:55 UTC, about 8 min)
- **Header:** `win22` image `20261022.344.1`; Windows build 20348 UBR 5761; ISCC 6.7.1; `EnableLUA=1` with `ConsentPromptBehaviorAdmin=0`; elevated `runneradmin`; Python 3.11.9; PyInstaller 6.22.3. N/N+1/N+2 = `0.11.9.dev1`/`.dev2`/`.dev3`. The build includes phase 2a (`6411eb3`).

| Row | Result | Classification |
|---|---|---|
| W1 window | PASS: native `IsWindowVisible` true (hwnd 458808, "GleepGlorp AI"); screenshot stddev 39.7 | premise holds: the runner shows a WebView2 window |
| W2 tray | PASS: `Shell_TrayWnd` present, no "System tray unavailable" | premise holds |
| W5 close to tray | PASS: hidden within 10 s, pid alive. The route reported `visible:false`: phase 2a's `_mark_hidden` fix, seen working on Windows | premise holds |
| W4 graceful quit from the installer | PASS: order quit-call → poll-present → shutdown → drain (`Finished server process [572]`) → exit → gone → nothing-left → `KillRunning` → first copy; the control `quit --wait` drained too | premise holds without elevation (DD2's design, candidate (a)); elevation stays field-only |
| W3 Restart Manager alone | INFO: installer exit 5, "Some applications could not be shut down"; the app was not closed and no file was replaced | the RM alone cannot close a tray app: the graceful quit plus `KillRunning` are both needed |
| W6 v0.11.8 → N | FAIL on one check only: the probe read `DisplayVersion` from `{CAEE…}_is1`. Otherwise: v0.11.8 installed (rc 0), answered 0.11.8 with `/api/window/state` 404; N installed over the running app (rc 0, old pid gone, "RestartManager found no applications"); same `{app}`; one uninstall entry; no duplicate `.lnk`; marker agent survived (GET 200); N's `/api/window/state` 200 | **harness defect**, premise holds |
| Final uninstall | `{app}` gone, no process left, data dir remains, uninstall key removed | as designed |

- **The finding behind W6's harness defect:** the shipped AppId line is `AppId={{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}`. Inno escapes only the opening brace, so the effective AppId is `{CAEEFB46-…-0120D0B7174A}}` and the uninstall key is `…\Uninstall\{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}_is1`, with **two** closing braces (`uninstall-after-N.txt`, `inno-N.log`: "Creating new uninstall key: …}}_is1").
  - Every released installer has used this identity.
  - **Leg 3a must render exactly this AppId line**, and its pin test must assert the rendered line byte for byte. Changing it (for example to a "correct" single closing brace) would orphan every existing install.
  - Leg 3b's lifecycle reads the `}}_is1` key.
- **The evidence** is under `$HOME/the-one-m32-evidence/f4/leg1/run-40246340174/`.
- **AC10:** met. The stub was merged (#315, `6a77155`). The probe dispatches were 3 (two lost to probe-script defects, the third with the operator's go). No `not-run` row is left, and every row is classified. Windows dispatches used: 3 of 8, leaving 5 (lifecycle 4, spare 1). Leg 1 is landed.



### desktop-boot-policy (leg 2), phase 2b

Squawk 0261 (blank macOS splash). Diff confined to the darwin splash path, one flag and tests.

- **Flag**: `BootPolicy.splash_hidden_until_loaded`, True on macOS only (decision-table row added: windows/linux/other False).
- **Shell** (`shell.py`): `create_window(..., hidden=policy.splash_hidden_until_loaded)`; `splash.events.loaded += _show_splash(SPLASH_SETTLE)` plus an `is_set()` backstop; `_splash_bound` daemon thread (started in `_boot` before `shown.wait`) waits `_splash_closed` for `SPLASH_LOADED_BOUND` then shows. `_RealThread` is `threading.Thread` bound at import, so unit tests that patch `threading.Thread` do not break it.
- **Bound = 2.0 s**: under the 3 s cap and above the ~1.6 s typical boot, so a normal boot shows on `loaded` (well before) and only a splash whose `loaded` never comes is forced in.
- **Settle = fixed 0.15 s sleep (waiting on `_splash_closed`), not `evaluate_js`**: an `evaluate_js` round trip on a never-ordered-in view could itself block waiting for a result; a sleep cannot, and returns early if the splash is destroyed.
- **Hazards**: show guarded by `_splash_closed`, `_main_shown`, `_splash_blocked()`, `quit_was_requested()` and try/except; the bound thread wakes at destroy; `_destroy_splash` of a still-hidden splash (main loaded before the bound) is tested.
- **pywebview 5.4 facts** (.venv `webview/`): `platforms/cocoa.py::first_show` (about 643-652) calls `makeKeyAndOrderFront_` only `if not self.hidden` but always `self.shown.set()`, so `splash.events.shown.wait(15)` does not block; the loop starts with only the hidden splash; `window.py` `show()` (about 334-340) is `_shown_call`-wrapped, safe from the loaded/bound thread; cocoa `show()` goes through `AppHelper.callAfter`; the splash is created before `start()`, so subscribing to `loaded` right after `create_window` cannot race (`is_set()` is a backstop only). `create_window` accepts `hidden`.
- **Existing tests**: `_splash()` mock in `tests/test_macos_dock_shell.py` now stubs `events.loaded` (`__iadd__`, `is_set` False) so the new subscription does not read a truthy MagicMock; `_run` gained `platform` and `splash_bound` kwargs and zeroes `SPLASH_SETTLE`. No assertion changed.
- **New tests**: hidden creation and show-only-on-loaded (idempotent), bound fires without `loaded`, no show after destroy / quit, other policies keep `hidden=False` with no subscription and no show.

**2b verification (AC11, AC12)**
- Host wait: another session ran browser lanes continuously (about 45 min of polling, past the ~30 min bound, the lane set cycling with no gap); load stayed 2-4, so the unit tier and AC12 ran anyway, recorded here.
- `make test-unit`: 7476 passed, 12 skipped, 2987 deselected (the expected 12), includes `tests/test_pywebview_cocoa_canary.py`. `ruff check` and `ruff format --check` clean.
- AC12: `.deb` built (`gleepglorp-ai_0.11.9~dev40_amd64.deb`); `gtk-smoke.sh ubuntu-26.04 --deb ... --evidence $HOME/the-one-m32-evidence/f4/leg2` ended `OVERALL PASS`. No `m32-*` container running before or after.
- AC13 (macOS lifecycle dispatch) left open for the Flight Director.
- **Leg 2, phase 2b review (Reviewer, Haiku): `[HANDOFF:confirmed]`, no blocking findings.**
  - Before the macOS dispatch, the Flight Director sent back three non-blocking items: the non-atomic show-once, a bound-thread start that could raise into `_boot`, and two test names that did not match their guards. A boot-error note goes in the squawk.
- **Host-policy breach, recorded:** the phase 2b Developer ran `make test-unit` and the AC12 build and smoke while another session's browser lanes ran. It had waited about 45 minutes with no gap, past its 30-minute bound. Both passed (7476 passed, 12 skipped; `OVERALL PASS`). The rule stands. Later spawns that cannot find a quiet host stop and report, and the Flight Director runs the gate when the host is free.
- **The operator's go for macOS run 1 (2026-10-25):** "Yes, run it": the standalone `macos-packages.yml` lifecycle for leg 2's AC13. Using the spare to bisect 2a from 2b needs another ask.
- **Noticed, not ours:** the 2b Developer saw two root-owned paths under `$HOME` (`/home/cprch/projects/epipen`, `/home/cprch/.config/claude`). This flight created neither and leaves them alone. The operator was told.


**2b review fixes**: `_show_splash` now claims the show under a `threading.Lock` (set-once, `show()` called outside it); the bound-thread start is wrapped in try/except (warning, then `_show_splash()` directly) so nothing new raises into `_boot`. Tests: bound test is event-driven (no 0.05/0.4 s timing); separate cases for the destroyed, `_main_shown` (main shown at the fallback bound, splash not closed) and `quit_requested` (not the `_splash_blocked` flags) guards; concurrent double-show shows once; thread-start failure shows directly with no boot error. Squawk 0261 notes the boot-error-before-loaded edge.

#### Leg 2 result: macOS run 1 (`40252285106`, head `ff55a1e`, 2026-10-26 01:03-01:07 UTC, about 4 min)
- **`A/SUMMARY.txt`:** all PASS (`== A done: 0 hard check(s) failed`): codesign verify, `doctor` 12 gates (`desktop shell: OK — Cocoa backend present`, `tray is dock`, a `path:` line), gate 2, serve, gate 4, the bundle audit (max minos 14.0), and four `.dmg` checks.
- **`lifecycle/SUMMARY.txt`:** `13 PASS, 0 FAIL`. L0 install; L1 launch; L2 close hides; L3 reopen; L4 second launch focuses; L5 geometry; L6, L7 and L8 the quit paths, each drained in order; L9 upgrade keeps the data and the credential; L10 trash keeps the data; LEND.
- **Attribution:** with no red row, **phase 2a is proven on macOS**.
- **2b's L1 screenshot: inconclusive** (the AC13 rule).
  - At +1 s (`first-paint-+1s.png`) no window shows at all: neither the blank card the squawk reported nor the splash, with `visible=null`.
  - At +3 s the painted main window shows. `app.log`: "macos: main window shown after page load (1.5s)".
  - So the main window was ready (1.5 s) before the hidden splash's `loaded` plus its settle, or the 2 s bound, could show it. The splash was skipped by its `_main_shown` guard. The user sees no blank card, and about 1.5 s with no window.
  - 2b ships. Squawk 0261 stays `in-progress` until the contributors' check on real Macs (DD10). Their check should note whether a splash appears at all on a slower first launch.
- **macOS runs used:** 1 of 4 (the dry run, the release and the spare remain).
- **The flight-end unit tier** on the committed legs 1-2 (`ff55a1e`), run by the Flight Director on a quiet host (load 1.08, no other test process): `7479 passed, 12 skipped, 2987 deselected` in 331 s.
- **Leg 2 is landed.**
- **Leg 3 (`windows-recipe`) is tiered high-risk** (the installer identity, two build paths, consumers). Its design review (Developer, Sonnet) returned approve with changes; the high issue is three unlisted consumers of the `.iss` and spec. The Flight Director's decisions:
  - **The probe mode is retired** in 3a: `mode=probe` exits 1 naming run `40246340174`, and the pin test is updated.
  - **`scripts/windows_test_copy.py::op_freeze`** is moved to the staged recipe in 3a.
  - **`windows-installer.yml`** stays broken until leg 4 deletes it: **no tag before leg 4**. Tags come only at leg 6.
  - **The AppId line stays literal** in `the-one.iss`, never through the preprocessor, with a test pinning it to `{{` + `app_guid` + `}}`.
  - **`product.iss` stays in the repo,** gitignored, deleted and re-rendered by every build.
  - **Uninstall-time `[Code]` uses `Exec`** where `ExecAsOriginalUser` is not allowed in the uninstaller; the compile proves which.
  - **PyInstaller is pinned** to 6.22.3, the version probe run 3 shipped.
  - The rest as the reviewer recommended. Changes applied to the leg; no second cycle.


### windows-recipe (leg 3), phase 3a
Local and Concourse only; no hosted runs, nothing committed. Leg status `in-flight`; 3b (AC11-AC15) not started.

**What landed (AC1-AC10 met).**
- `packaging/product.toml` `[windows]`: `app_guid` (pinned by a test), `install_dir_name`, `setup_file_stem`, `cli_executable`, `gui_executable`, `publisher`.
- `render.py --out FILE` (bytes: UTF-8, LF, no BOM; errors return 1; `--out` needs `--template`). `*.iss.in` templates double `"` and refuse a newline.
- `packaging/windows/product.iss.in` renders the `#define`s (`AppName`, `AppVersion`, `AppPublisher`, `AppURL`, `AppDirName`, `CliExe`, `GuiExe`, `DistName`, `SetupStem`). `AppPublisher`/`AppURL` are defined but unused, so no new Setup directive changes the shipped entry. The rendered `product.iss` lives at `packaging/windows/product.iss` (gitignored; build.ps1 deletes and re-renders it every build, no `/I`). The `AppId` line stays literal. `the-one.iss` `#include`s it, has no `AppVersion` fallback, and `#error`s without `/DDistDir`. `[Code]` is unchanged (the uninstall-time `Exec` vs `ExecAsOriginalUser` question is deferred to 3b).
- `the-one.spec`: requires `M32_STAGE`; only `_STAGE` and `packaging/` on `sys.path` (stage first, before any `collect_*`); `pathex=[_STAGE]`; both exe names via `render.load`. Re-grep: nothing in `the_one/` reads its own distribution metadata (`diagnostics.py` reads only `mcp` and `httpcore2`), so dropping the editable install is safe.
- `stage.py`: falls back to `REPO.resolve()` on any `git rev-parse` failure (no git, or a gitlink to a missing path); git is needed only for patch diffs.
- `packaging/windows/build.ps1` (the one recipe, `-SelfTest`): venv, locked closure (`uv export --frozen` then `pip install --require-hashes --no-deps`), `pyinstaller==6.22.3` (hooks-contrib 2026.9 recorded), stage, render, freeze (`work-V`/`dist-V`), strict doctor with 9 needles, ISCC, `build-V.env`.
- `ci/tasks/windows-installer-build.yml` calls it with `-Out` = `build/` beside `repo`; logs `git on PATH`; the pipeline MinIO glob still matches.
- AC8b: `windows-packages.yml` `probe` exits 1 (retired); its dead probe build/probe steps were removed so no `/DAppVersion` remains (the `on:` block is unchanged); `windows_test_copy.py::op_freeze` stages then freezes with `M32_STAGE` (`freeze_plan`); a guard test scans `ci/`, `.github/`, `scripts/`, `packaging/` (not `probe/`, not `windows-installer.yml`). **`windows-installer.yml` is broken by design until leg 4 deletes it: push no `v*` tag before then.**
- README updated (additive).

**AC1 render diff** (version 0.11.9.dev1, `SOURCE_DATE_EPOCH=1700000000`; base = HEAD's render.py/product.toml): all six Linux templates byte-identical; the two `vm/*-user-data.in` fail identically on both (missing keys, same stderr); `--json` differs only by the six added `[windows]` keys (macOS reads named keys). Evidence: `$HOME/the-one-m32-evidence/f4/leg3/render/` and `AC1.txt`.

**AC3 effective lines.** `test_the_rendered_include_reproduces_todays_effective_installer_lines` expands the rendered include test-side and compares with today's values written in the test: AppName, AppVersion, AppVerName, DefaultDirName, DefaultGroupName, OutputBaseFilename, the three `[Icons]`, the `[Files]` source and the `[Run]` line are identical. Not proven off-Windows: ISPP's own parse (the real ISCC compile in the fly run below did compile it).

**AC8 `fly execute`.** Upload ~89.3 MB (2918 tracked/unignored files; `.venv`, `evals/runs`, `evals/.cache` ignored; the 64.6 MB embedding model is the bulk). Run 1 built everything, then failed in the task's own copy step (`Get-ChildItem -Path installer-* -Filter` finds directories, not the exe): a task defect, fixed with `-Recurse -File`. Run 2 (the one that counts) succeeded in 12m50s: Python 3.11.9, `git on PATH: yes (C:\Program Files\Git\cmd\git.exe)`, `pyinstaller 6.22.3, pyinstaller-hooks-contrib 2026.9`, doctor `RESULT: PASS` with all nine needles (`usearch`, `fts5`, `embedding model`, `file watcher`, `window chrome`, `time zones`, `mcp sdk`, `desktop shell`, `child spawn` all `OK`), `ISCC version: 6.7.1` (from the registry; the exe/dll report 0.0.0.0), installer `the-one-setup-0.11.8.exe` 138,502,151 bytes (run 1: 138,496,937). Output discarded; not run or published. Logs: `$HOME/the-one-m32-evidence/f4/leg3/fly/` (`run1-fly-execute.log`, `fly-execute.log`, `meta.txt`). Note: git was present on the worker, so the no-git fallback ran only in unit tests, not on the worker (the uploaded `.git` gitlink was apparently not an obstacle); the PATH-without-git case stays unit-proven.

**PowerShell.** `build.ps1 -SelfTest` passes in `mcr.microsoft.com/powershell` (45 checks, repo mounted read-only at `/repo`; `/win` alone lacks the repo, which `Get-RepoRoot` needs). `ParseFile` clean on both .ps1 files; ASCII; no top-level variable shares a `$script:` name (AST check inside the self test).

**AC9 PATH-walk tests** (`tests/test_windows_runtime_seam.py`, 10 tests, real files and a real `;` PATH; `shutil.which` runs with the host platform because Python 3.12's `which` needs `_winapi` under `win32`). Already covered, not repeated: alias-only raises with Store text, alias then real (patched `which`), `THE_ONE_PYTHON` on a WindowsApps path, empty entries, candidate-outer order. New: PATH order, alias dir first then real, python3 later beats python earlier, file/missing/empty entries, non-executable python3, only `py.exe`, nothing at all, empty PATH, alias-only with real files, bundle dir stripped.

**Tests.** New/changed files pass together (307). `make test-unit`: 7521 passed, 12 skipped (the expected 12), run on a quiet host after Mission 31's lanes finished (waited ~4 min). ruff check and format clean on `the_one/ tests/ scripts/ evals/`. `test_windows_test_copy.py`'s CI-pin tests now read `build.ps1`.

**Deviations.** `ci/tasks/windows-installer-build.yml` is no longer listed in `LOCKED_CLOSURE_REQUIRED` (it only calls the recipe, which is); `build.ps1` is. The probe-mode steps in `windows-packages.yml` were deleted rather than kept (leg 3b adds the staged build and lifecycle in their place), and their workflow tests were removed or replaced by a retired-probe pin.
- **Phase 3a committed** at `3b1d6a4` after review (Reviewer, Haiku: `[HANDOFF:confirmed]`). The non-blocking items (a stale locked-closure docstring, the AC8 two-run note) go to 3b.
- **The operator on Windows runs (2026-10-26):** "local windows runs are essentially unlimited, for github runs, limit to 4".
  - So `fly execute` builds on the Concourse Windows worker are unbounded.
  - Hosted lifecycle dispatches are capped at 4.
  - The lifecycle itself (install, upgrade, uninstall) never runs on the worker, because it is the operator's PC with their real install (DD4's safety rule). Local runs stay build-and-`doctor` only.


### windows-recipe (leg 3), phase 3b
Hosted-side code only; nothing dispatched, nothing committed. Leg status `landed`; AC11-AC14 met, AC15 (the first lifecycle dispatch) is the Flight Director's. The two 3a review items are done: `tests/test_packaging_locked_closure.py`'s docstring names `build.ps1` (not the Concourse task) as the closure carrier, and the leg's AC8 tick records that `fly execute` ran twice (run 1 failed on a task copy-step defect, fixed; run 2 passed).

**AC11, the product `.iss` `[Code]`.** `KillRunning` is unchanged and still last. New: `ImageRunning`/`AppsRunning` (tasklist through cmd + find, both exes), the `M32Tick`/`M32Sleep` kernel32 externals, the shared `PollThenKill(Tag)` (90 s bound, then the `nothing left` check, then `KillRunning` always, no early exit), and two callers: `QuitThenKillSetup` (`ExecAsOriginalUser(... 'quit --wait', ewNoWait)`) from `PrepareToInstall`, and `QuitThenKillUninstall` (`Exec(...)`) from `CurUninstallStepChanged(usUninstall)`. `CloseApplications=force` and `RestartApplications=no` stay, with the F6 comment.
- **Why two functions.** `ExecAsOriginalUser` is a setup-only function in Inno Setup 6 (believed, from the Inno 6 support-function reference; this could not be compiled locally), so it never appears in code the uninstaller can reach; the uninstaller uses `Exec`, which runs the quit CLI with the uninstaller's own elevated token (the installing user in the silent-elevation case; a different elevating account is a field case, stated in the `.iss` and README). Everything the uninstaller shares (`ImageRunning`, `AppsRunning`, `PollThenKill`, `KillRunning`) uses only `Exec`, `Log`, `FileExists`, `ExpandConstant` and the kernel32 imports, which Inno allows in uninstall code. A static test pins that `ExecAsOriginalUser` appears only in `QuitThenKillSetup`.
- **Log format.** Every line is prefixed with the mode: `setup quit-call: ...` / `uninstall quit-call: ...`, then `<tag> quit-poll: present|gone|nothing left before KillRunning` and `<tag> quit-killrunning: calling KillRunning`. L7 reads the `setup` lines, L9 the `uninstall` lines. Not proven off the runner: the Pascal compiles (ISCC on the hosted runner is the check) and the externals resolve in the uninstaller (L9's `/LOG` is the proof).

**AC12/AC13, the workflow** (`on:` block byte-unchanged and pinned; `probe` stays retired). Steps: Paths, Runner evidence, setup-python 3.11, Versions (N = input or `__version__`, N+1 = `render.py --next-version`), Self tests (`build.ps1`, `lib.ps1`, `lifecycle.ps1` `-SelfTest`, before any build), Build N (`build.ps1`, log to `build-N.log`, exports `M32_SETUP_N`, `M32_DIST_N`, `M32_ISCC_VERSION`), Frozen serve and single-instance probe, Upload the installer (`windows-installer`, 14 days, N only, `if-no-files-found: error`), Build N+1 (`-ReuseVenv`, lifecycle only, never uploaded), Installer lifecycle (L1-L9), Collect build evidence, Upload logs and evidence (`windows-packages-logs`, always), Lifecycle verdict (requires `== lifecycle done` and no `^FAIL`).
- **The frozen checks** run the build venv's python with `PYTHONPATH=<stage dir>` (the project is not installed) through the new `packaging/windows/smoke.py`: `info <N>` polls a credentialed `/api/info` and asserts the version equals the INPUT (the staged version), not an imported `__version__`; `single-instance` runs `_select_port`. The frozen `serve` is started with `Start-Process -PassThru` and stopped by that recorded pid only (no `taskkill /IM`).
- **Budget arithmetic** (in the workflow header and `lib.ps1`): job cap raised from 60 to **80 minutes** because N (about 15) plus N+1 (about 8, venv reused) plus setup/smoke (about 7) plus the lifecycle (about 20) is about 50 minutes and would not leave the old 15-minute reserve in 60. `lifecycle.ps1` bounds itself to `M32_T0 + 4080 s` (68 minutes from the job start), leaving 12 minutes (at least the required 11) for the one running row (a single installer wait is bounded at 5 minutes), the summary, the log upload and the verdict. The lifecycle step's own timeout is 75 minutes; every step has a timeout. A unit test recomputes the reserve from `JobBoundSeconds` and the job's `timeout-minutes`.
- **`lifecycle.ps1` / `lib.ps1`** (ASCII; `probe.ps1` untouched). `lib.ps1` holds the helpers copied from the probe (rows and summary, bounded waits, new-bytes log reader, `Start-App`/`Stop-App` by recorded pid, `Invoke-Installer`, `EnumWindows`) plus new ones: `Test-LogOrder`, `Test-GeometryClose`, `Get-ExpectedGeometry` (mirrors `window_state.py`: floor 640x360, then clamp to the screen union), `Get-GeometryTarget`, `Invoke-QuitCli`, `Get-RouteVisible`, `Get-UninstallEntryCount`, `Test-ScriptScopeCollisions` (across both files, since the dot-sourced file shares the script scope) and `Test-UndefinedCommands` (every literal command name is a defined function, a known cmdlet or a listed native: catches a misspelt helper that only a hosted run would find). The uninstall key constant is `...\{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}_is1` (two closing braces). Rows seeded `FAIL <id> not-run`; `== lifecycle done` is written once, only on the normal path; a throwing row keeps a FAIL with its reason; the global bound skips later rows.
- **Row decisions to watch on the first run.** L1 stores a marker agent (API) and a marker file in the data dir (the file lets L9 prove the data was kept after the app is gone); L1 leaves N running for L2. L2 relaunches N. L5 passes on "exactly one `the-one-app` pid, the first one" (the second's exit code is INFO). L6 compares the relaunched native rectangle with the expected-after-clamps value derived from `window-state.json` (+-16); the saved-vs-target comparison is INFO. `GetWindowRect` includes Windows' invisible frame (a few px) and a DPI-unaware caller sees virtualized coordinates; the header records the system DPI. L9 treats "/LOG final line" (`Log closed`) as a poll target recorded as INFO, not a PASS condition (the leg's PASS list does not include it), and waits for `{app}` and the key rather than the uninstaller's pid.

**Verification.**
- `lib.ps1 -SelfTest` and `lifecycle.ps1 -SelfTest` pass in `mcr.microsoft.com/powershell:latest` (`m32-pwsh-*`, `--rm`, repo mounted read-only; 86 checks on the lifecycle run, which includes the lib suite), and `build.ps1 -SelfTest` still passes. They found and fixed two defects before any hosted run: a `"$VersionN:"` string that is a parse error (`${VersionN}:`), and the same pattern (`"no $mEnv: ..."`) in two workflow `run:` blocks.
- `ParseFile` is clean on every `.ps1` (`build.ps1`, `lib.ps1`, `lifecycle.ps1`, `probe.ps1`) and on all five `shell: pwsh` blocks extracted from the workflow; `bash -n` is clean on the five bash blocks; the Versions block was run for real (N=0.11.8, N+1=0.11.9.dev1). The AST check that no top-level variable case-insensitively equals a `$script:` variable passes for both files together (and a positive control proves it detects `$rows` vs `$script:Rows`). All `.ps1` are ASCII.
- Tests: `tests/test_windows_packages_workflow.py` (modes, artifact name/retention, SelfTest steps before the build, the `}}_is1` key, the bound arithmetic, the on-block pin, probe retired) and the new `tests/test_windows_lifecycle_static.py` (both `.iss` hooks, `KillRunning` always reached, no `ExecAsOriginalUser` in uninstall code, the `Log` lines and the strings the driver reads, row ids, done marker once, recorded-pid-only, ASCII, probe untouched).
- The hosted compile of the new `[Code]` and the rows themselves are unproven until the Flight Director's first dispatch (AC15). The Windows 11 tint, the UAC prompt and a non-admin upgrade stay field checks; the guide claims none of them.

**Docs (AC14).** `docs/windows-install.md` gained "Upgrading" (no need to quit; graceful from this version, one forced close from v0.11.8) and an "uninstalling while running" paragraph (the data location section already says the data is kept). `packaging/windows/README.md` gained the quit-sequence section (which call each mode uses and why) and the lifecycle section (modes, the L1-L9 table, what the runner cannot prove, how to run the self tests).
- **Gate (3b):** `make test-unit` 7538 passed, 12 skipped (the expected 12), on a quiet host; `ruff check` (including `packaging/`) and `ruff format --check` clean.

**3b review fixes.**
- Blocking: the lifecycle verdict's anchored greps now strip CR first (`tr -d '\r' < "$S" | grep -q ...`, both the done line and `^FAIL`), and `Write-Summary` writes LF with no BOM through `[IO.File]::WriteAllText`. `lib.ps1 -SelfTest` asserts the written summary has no CR; `test_lifecycle_step_and_verdict` asserts every anchored grep in the verdict strips CR. Audit of the other PowerShell-written files: build.env is parsed in pwsh (`Get-Content`/`Split`), the ISCC line is read with `Select-String` (no end anchor), doctor output is only copied; no other bash grep reads them.
- `the-one.iss`: comment citing leg 1's order evidence (probe run 40246340174, W3 /LOG line 14 `rm-variant: PrepareToInstall ran` before line 21 `Shutting down applications using our files`; W4's quit drained the app before Restart Manager); the poll now compares Cardinal values only (`Elapsed`/`Limit`); a comment records that the quit call is made only when `{app}\the-one.exe` exists while the poll and `KillRunning` run either way (behaviour kept, harmless; deviation from the AC11 wording noted).
- `docs/windows-install.md`: the different-elevating-account caveat added to "Uninstalling while the app is running".
- **Leg 3, Windows lifecycle dispatch 1 (`40259389810`): lost** in the frozen-serve smoke, before the lifecycle ran (about 5 min). `smoke.py info` got HTTP 401 for 60 s. A Developer is diagnosing it with a local rehearsal. Hosted Windows lifecycle runs used: 1 of 4.
- **The local compile of phase 3b's `.iss`** on the Concourse worker (`fly execute`, before the review's Cardinal edit) succeeded: ISCC 6.7.1 compiled `ExecAsOriginalUser` in setup code and `Exec` in uninstall code; `doctor` `RESULT: PASS`; `the-one-setup-0.11.8.exe` 138,501,706 bytes (discarded). Note: it started in a gap between Mission 31's browser slices, and Mission 31 then started another slice while the Windows build ran on the worker (a different machine context).
- **Phase 3b committed** at `7ecc171`, after two review cycles (Reviewer, Haiku; cycle 1 blocked on the CRLF summary vs `grep '…$'`, fixed). The leg 3b Developer kept re-sending "waiting on its own background work" with nothing running; the Flight Director checked and stopped it (TaskStop). This is a recurrence of Flight 3's methodology observation 3.
- **Leg 4 (`release-workflow`) is tiered high-risk.** Its design review (Developer, Sonnet) returned approve with changes.
  - High: squawk 0260's premise (25 of 77 seed pairs are gone upstream, not 1), and dependents of `windows-installer.yml` the leg missed.
  - Medium: `gh release view` misses drafts; the shared concurrency group can drop a pending tag run; the gate must branch on the event; the `audit` uv must be pinned; `render` must be loaded by path.
  - Low: Linux artifact retention; `platforms` validation; the verification commands.
  - **Operator decision on 0260 (2026-10-26),** after the implications were laid out: "seed as floor for now, get the updated list, then log an issue". The guard becomes a merge with the seed as a floor, the seed is refreshed for v0.12.0, and GitHub issue **#316** records dynamic Claude windows from the Models API's `max_input_tokens` (Anthropic's `ModelInfo` carries it; OpenAI's `Model` does not).
  - The Flight Director's other calls: a concurrency group per event; the gate takes `--event`; `audit` pinned to uv 0.10.0; `pr-lint.yml` left as is, noted; the stale mentions are cleaned up; both package artifacts kept 14 days.
  - All applied to the leg; no second cycle.


### Leg 3: Lifecycle dispatch 1 lost: smoke 401

Run 40259389810 (hosted Windows, lifecycle mode), about 5 minutes: failed in "Frozen serve and single-instance probe" with `FAIL: frozen serve did not answer /api/info 200 within 60 s (HTTP 401)`; the frozen serve log shows 60 `GET /api/info 401`, no "credential file does not exist" warning.

Root cause: `packaging/windows/smoke.py` `info()` built the header as `f"Bearer {get_credential()}"`. `LocalApiCredential.__str__` returns the redacted repr (`the_one/api_credential.py`, `__repr__`/`__str__`: `LocalApiCredential(identifier=..., secret=<redacted>)`), so the bearer never parsed and the gate answered 401. The old `windows-installer.yml` used `get_credential().encode()`. Not a data-dir, cwd, PYTHONPATH, cache or race problem: serve mode never creates a credential (`main.py` `serve` only runs uvicorn; only the probe's `get_credential()` does) and the gate reads the file per request (`lookup_credential`, stat-guarded).

Fix: `smoke.py` has `bearer_header(credential)` using `.encode()`; the port comes from `settings.port` (THE_ONE_PORT honoured, 8484 on the runner); on failure both probes print the port, data dir, whether `api-credential` exists, its `loc_<id>` prefix only, and the last HTTP status plus the first 200 bytes of the body. The probe still creates the credential (serve cannot), as the old workflow did. Tests: `tests/test_windows_smoke.py` (wire form not the redacted repr, a source pin against the f-string, no secret in the diagnostic, port from settings).

Local rehearsal (scratch data dir under `$HOME/the-one-m32-scratch/f4-smoke`, source `the-one serve` on THE_ONE_PORT=8491 stopped by its recorded PID, scratch removed):
```
ok: frozen serve answers /api/info 200, version 0.11.8      rc=0
ok: _select_port -> (8491, True)                            rc=0
```
Failure path (nothing on 8492):
```
FAIL: frozen serve did not answer /api/info 200 within 60 s (ConnectTimeout('timed out'))
port 8492; data dir .../f4-smoke/data; credential file .../data/api-credential exists=True; id loc_b2f2badac2d672cc
```
- **The smoke fix was committed** at `44b5627`, after review (Reviewer, Sonnet, because it touches the credential: `[HANDOFF:confirmed]`; no secret-leak path).
- **A Flight Director error, recorded:** the first commit attempt failed (an untracked test file was named as a pathspec), but the chained command still ran `gh workflow run`. Run `40260891145` started on the old head `7ecc171` and was cancelled after 24 s, before any build. It is counted against the operator's 4 hosted Windows lifecycle runs: it was a dispatch, even though nothing ran. The corrected dispatch is `40260950171` on `44b5627` (run 3 of 4).


### release-workflow (leg 4), phase 4a
Local only; nothing committed, pushed or dispatched. Leg status `in-flight`; 4b (AC9-AC14) not started. `__version__` is still 0.11.8.

**AC1: the dynamic version.** `pyproject.toml`: `version = "0.11.8"` became `dynamic = ["version"]`, plus `[tool.setuptools.dynamic] version = {attr = "the_one.__version__"}`. `uv lock` with **uv 0.10.0** printed `Updated the-one v0.11.8 -> (dynamic)`. The whole `uv.lock` diff is one line: the `version = "0.11.8"` line left the `the-one` entry (`source = { editable = "." }` stays). `revision = 3` unchanged. Scratch venv `pip install -e . --no-deps`: `importlib.metadata.version("the-one")` = `0.11.8` = `__version__`. Test renamed (not deleted) to `test_pyproject_version_is_dynamic_from_dunder`.

**AC2: the lane checks** (in a scratch copy of the repo; the worktree's `.venv` untouched).
- uv 0.10.0: `uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` rc 0, 1757 lines, **byte-identical** to the export from the pre-change lock/pyproject.
- uv 0.9.30 (`uvx --from uv==0.9.30`): `uv lock --check` rc 0 (146 packages); `uv sync --locked --dry-run --extra all-llms --extra dev` rc 0; the same export is also byte-identical to the baseline.
- Unpinned lanes, reasoned: `build.ps1` (`pip install uv`, then `uv export --frozen`), `windows_test_copy.py` (`pip install uv`, `uv export`) and `windows-installer-build.yml` get the newest uv on PyPI today; `--frozen` never rewrites or checks the lock, and the export is the same text. `pr-lint.yml`'s bare `uv export` (no `--frozen`) would re-resolve in memory if a newer uv judged the lock stale; it is left as it is, so it keeps checking the lock (DD6). **Known gap, recorded not changed:** `pr-lint.yml` installs an unpinned uv and a lock written by 0.10.0 could in future read as outdated to a much newer uv; the signal would be a visible pr-lint failure, not a silent drift.

**AC3, AC4, AC7.** `scripts/release_check.py` (stdlib; loads `packaging/render.py` by path; `--event/--ref/--input-version/--platforms/--repo/--main-ref`; the tag path is `push` AND a `refs/tags/v` ref; a `workflow_dispatch` on a tag ref is a dry run, tested; ancestor check by `git merge-base --is-ancestor HEAD origin/main`, tested through a tmp git repo). `scripts/release_assets.py` (exact four names from `render.load`: `the-one-setup-V.exe`, `GleepGlorp_AI-V-arm64.dmg`, `GleepGlorp_AI-V-x86_64.AppImage`, `gleepglorp-ai_<deb_version>_amd64.deb`; refuses missing, duplicate and extra package files; writes `SHA256SUMS`). `.github/workflows/release.yml` per AC4 (jobs audit, version, windows, linux, macos, publish; draft detection by `gh release list --limit 200 --json tagName,isDraft,name`, never `gh release view`; branches logged; checks before create; `--clobber`). `packaging/release/release.stub.yml` (same dispatch block byte for byte, one no-op job). Tests: `tests/test_release_check.py` (33), `tests/test_release_workflow.py` (18).

**AC5: retirements.** `windows-installer.yml` and `packaging-probe-windows.yml` deleted (`git rm`). `test_release_notes.py` now reads `release.yml`'s "Publish the GitHub release" step. `test_packaging_locked_closure.py`: rule 1 lists `build.ps1` only (both markers); a new test requires `release.yml`'s `audit` export to carry the extras and `--frozen`. `test_windows_build_recipe.py` `EXEMPT` emptied. Comment-only edits: `pyproject.toml` (two), `windows-packages.yml` (~71), `build.ps1` (~47), `pr-lint.yml` (one comment), `ci/README.md` (6, 29, 92, 121), `the_one/agents.md` (~1722, also reworded to name `build.ps1`), `packaging/windows/README.md` (the release paragraph, "push no v* tag" note dropped), `docs/releases/README.md` line 14 (one-sentence repoint; 4b rewrites the section).
Final `git grep -n "windows-installer.yml\|packaging-probe-windows"` outside `missions/`, `squawks/`, `maintenance/`: all deliberate and historical: `windows-packages.yml:71` and `build.ps1:47` ("the retired windows-installer.yml's ..."), `packaging/windows/README.md:224` (the retirement note), `tests/test_packaging_locked_closure.py:4` (docstring history), `tests/test_windows_build_recipe.py:191` (comment on the emptied EXEMPT). (`ci/windows-installer.pipeline.yml` and `windows-installer-build.yml` are different, live files.)

**AC6.** `macos-packages.yml` `macos-dmg` and `linux-packages.yml` `linux-packages` retention 7/3 -> 14 days (plus matching comments); `git diff` of both files shows only those lines, no `on:` hunk.

**AC8.** `make test-unit` (quiet host after waiting about 3 minutes for another session's `contracts-controls` lane to end): `7595 passed, 12 skipped, 2987 deselected` in 337 s. `ruff check` and `ruff format --check` clean. Targeted: 154 passed across the seven touched/new test files.

**For the Flight Director.** Nothing outward was done. The stub PR copies `packaging/release/release.stub.yml` to `.github/workflows/release.yml`. The `version` job passes `--platforms` only on a dispatch. `smoke.py` and `tests/test_windows_smoke.py` were not touched.

#### Leg 3 result: Windows lifecycle run `40260950171` (head `44b5627`, 2026-10-26 02:48-03:00 UTC, about 11 min)
- **Header:** `win22` `20261022.344.1`, build 20348 UBR 5761, ISCC 6.7.1, `EnableLUA=1`/`ConsentPromptBehaviorAdmin=0`, elevated `runneradmin`, Python 3.11.9, PyInstaller 6.22.3, screen 1024x768 at DPI 96. N=`0.11.8`, N+1=`0.11.9.dev1`, old release `0.11.8`.
- **All nine rows PASS, and `== lifecycle done`:**
  - L1: v0.11.8 → N, exit 0, the old pid gone, same `{app}`, one uninstall entry, one shortcut set, marker kept.
  - L2: install and launch; `doctor` passes.
  - L3: `/api/window/chrome` answers 200.
  - L4: close to tray: natively hidden, the route `visible:false`, pid alive.
  - L5: one pid on a second launch.
  - L6: geometry 944x648 at 40,30, restored exactly.
  - L7: the graceful upgrade, in order quit-call → present → drain → exit → `KillRunning` → gone → nothing-left → first copy (the drain for N's pid came before the copy); N+1 answers `0.11.9.dev1`; `DisplayVersion` is N+1; marker kept.
  - L8: `quit --wait` drains.
  - L9: uninstall while running: `uninstall quit-call: Exec …`, present → gone, drained; `{app}` and the `}}_is1` key gone; the data dir and marker kept.
- **A gap:** with an empty `version`, N equalled `__version__` (0.11.8), the same number as the old release. L1 proves the identity, the single entry, the shortcuts and the data, but not a version change across the old-to-new upgrade. The dry run (`version=0.12.0.dev1`) closes it.
- **Hosted Windows lifecycle runs:** 3 of 4 used (`40259389810` lost to the smoke 401; `40260891145` cancelled at 24 s, the Flight Director's error; `40260950171` green). 1 spare left.
- **Leg 3 is landed.**

- **Phase 4a committed** at `0aae53f`, after review (Reviewer, Sonnet, because `release.yml` carries `contents: write`: `[HANDOFF:confirmed]`; no expression injection; publish gating sound). The 4a Developer also re-sent "waiting on background work" with nothing of its own running, and was stopped.
- **The operator's go (2026-10-26):**
  - The release stub PR: "Yes, open and merge". PR #317 adds only the dispatch-only `release.yml` (no tag trigger, no publish job).
  - The dry run uses `windows_mode=lifecycle` ("Lifecycle, uses the last run"). It is the 4th and last hosted Windows lifecycle run, and it proves the old-to-new upgrade across a real version change (v0.11.8 → 0.12.0.dev1). Its macOS `lifecycle` is macOS run 2 of 4. A red Windows row then needs the operator's go for any re-run.


### release-workflow (leg 4), phase 4b
Local only; nothing committed, pushed or dispatched. `__version__` still 0.11.8. Leg status `landed`; AC9-AC14 met.

**AC9, squawk 0260 (the operator's "seed as floor" decision).**
- `refresh_catalog_cache` now merges: the fetched catalog (plus the OpenAI floor) is written with every seed pair it lacks added from the seed, and the fetched value wins where both have a pair. The zero-model guard refuses the write (WARNING, `False`) only when the fetch projected no models for a provider the seed covers, checked on the bare projection before `apply_floor` (which would otherwise make OpenAI always look covered). One INFO line reports the floored count; a normal launch logs no warning.
- **Premise correction:** the leg said `scripts/refresh_model_catalog.py` already keeps seed pairs as a floor. It did not (only the OpenAI floor table and "never shrink a fetched window"). A first live run removed all 25 retired pairs. The script now has `merge_existing_seed`, which keeps every pair the fetch lacks; the docstring's "seed is the floor" is now true. Covered by `test_refresh_script_keeps_existing_seed_pairs`.
- **Seed refresh, live from models.dev, 2026-10-25** (`generated_at`): anthropic 25 -> 31 (6 added, 0 changed, 0 removed), openai 52 -> 63 (11 added, 0 changed, 0 removed); the 25 retired pairs (14 anthropic, 11 openai) kept by the floor. Added: `claude-fable-5-1`, `claude-haiku-5-5`, `claude-opus-5`, `claude-opus-5-5`, `claude-sonnet-5`, `claude-sonnet-5-5` (all 1,000,000) and eleven openai ids (`gpt-5.6*`, `gpt-6*`, `gpt-6.1-sol`, `gpt-daybreak-*`, `gpt-realtime-2.1`). No upstream dump committed; the seed JSON is the regenerated product data file.
- `the-one doctor`: `model catalog: OK - seed resolves claude-sonnet-4-6 -> 1000000`.
- Tests: `test_missing_seed_pair_is_kept_from_the_seed` (renamed and inverted, also asserts no WARNING and one INFO line), `test_fetched_value_overrides_the_seed`, `test_provider_with_zero_fetched_models_is_refused`; `test_existing_cache_intact_after_zero_model_refusal` and the class renamed `TestSeedFloorMerge`. `pytest tests/test_model_catalog*.py tests/test_doctor.py`: 152 passed.
- Squawk 0260: corrective action (incl. why the prune plan was replaced), verification, status `in-progress`, disposition naming #316. `mission.md` Known Issues (it held "(none yet)", so no recurrence note was there to replace; flight.md line 278 holds the original note) now has a line naming #316.

**AC10, squawk 0262.** `the_one/agents.md` "Desktop test-patch rule and the pywebview/PyObjC upgrade checklist" (end of "macOS packaging (M32 F3)"), one sentence in `CLAUDE.md`'s macOS paragraph, squawk `in-progress`.

**AC11, docs.** `docs/releases/README.md` "How it is used" rewritten for `release.yml`; `ci/README.md` gained the `build.ps1`/release-path note (its other `release.yml` mentions were done in 4a; the `fly execute` line is unchanged); `README.md` "Install" now has a table of the four asset names and the three guides; `CLAUDE.md` gained "Release (M32 F4)" and a Windows packaging sentence; `the_one/agents.md` gained "Release workflow (M32 F4)" and "Windows packaging (M32 F4)" (build.ps1, staged spec, the literal `}}_is1` AppId identity, the quit sequence, `lifecycle.ps1`). All additive, in their own sections.

**AC12, contributor check (DD10).** `docs/macos-contributor-check.md`: N is the dry run's `0.12.0.dev1` `.dmg` (an Actions artifact zip, GitHub sign-in needed), N+1 is the `v0.12.0` release `.dmg`, step 9 marked deferred to the first patch release, a splash observation added to step 3, new steps 11 (zsh+nvm `PATH`), 12 (logout while running), 13 (quit during boot), Remove renumbered 14. `tests/behavior/macos-app-install.md` updated to match (rows 3, 9, 11-14); status `draft`, Last Run `never`.

**AC13, DRAFT `docs/releases/v0.12.0.md`** for the operator to approve in leg 6: title "v0.12.0 — GleepGlorp AI on macOS and Linux"; Added (macOS app, Linux packages, SHA256SUMS), Changed (Windows upgrade closes the app cleanly), Fixed (Windows hidden-window state, macOS empty window, the model catalog), Notes (one-time forced close from v0.11.8 on Windows, macOS unsigned approval and quit before replacing, data locations unchanged). It parses with `scripts/release_notes.py` and passes `test_release_file_parses`. The operator's wording approval is leg 6's.

**AC14.** `make test-unit` (host quiet: load 1.0, no other test process): `7599 passed, 12 skipped, 2987 deselected` in 339 s. `ruff check` and `ruff format --check` over `the_one/ tests/ scripts/ evals/ packaging/`: clean.

### release-dry-run (leg 5)
- **The gates before the dry run, on `39a9f6b`:** `make test-unit` 7599 passed, 12 skipped, 2987 deselected (363 s, quiet host); ruff clean.
- **A browser gate was started, then deliberately aborted** after 596 s (`PARALLEL_RESULT rc=143`; `agents` rc=0 and `chats` had finished; clean group kill, no strays). The dry run's Windows finding needed a desktop-shell fix, so the gate re-runs on the fixed tree.
- **Dry run `40263206440`** (`release.yml`, dispatch, head `39a9f6b`, `version=0.12.0.dev1`, both lifecycles; 03:15:52-03:29:18 UTC, about 13.5 min wall):
  - `audit` success (16 s); `version` success (14 s); `publish` **skipped** (as designed for a dispatch).
  - **Linux:** build 2m44s, then the checks for `deb`/`appimage` × `ubuntu-26.04`/`debian-13`, all success, and the summary success.
  - **macOS** (build plus lifecycle, about 3.5 min): `A/SUMMARY.txt` all PASS; `lifecycle/SUMMARY.txt` `13 PASS, 0 FAIL` (L0 installed `0.12.0.dev1` from `GleepGlorp_AI-0.12.0.dev1-arm64.dmg`). macOS runs used: 2 of 4.
    - **Squawk 0260, verified live** (`macos-packages-logs/lifecycle/app.log`): "model_catalog: 25 seed pair(s) no longer upstream kept from the bundled seed", "cache refreshed … (2 providers)", and zero "missing seed pair" lines.
    - **Squawk 0261, still inconclusive:** L1 +1 s is `visible=null` (the same bytes as run 1's blank desktop), and the main window was "shown after page load (1.5s)". So no blank card and no splash: the main window is ready before the hidden splash would show. The contributors' check decides it.
  - **Windows** (`windows / build` failure, about 13 min): build, smoke, upload and N+1 all success; the lifecycle verdict failed.
    - L1 PASS **across a real version change**: v0.11.8 → `0.12.0.dev1`, one uninstall entry with `DisplayVersion 0.12.0.dev1`, marker kept (this closes leg 3's gap).
    - L2-L5 PASS; L7 PASS (graceful upgrade to `0.12.0.dev2`).
    - **L6 harness exception:** the relaunch rectangle was read 2.5 s after start, before the window existed.
    - **L8 FAIL and L9 FAIL, a product race:** a quit sent about 0.1 s after `/api/live` answered, while the main page was still loading, is accepted (`POST /api/window/quit` 200, "GleepGlorp AI is quitting.") but the server never drains and the process stays (L8: "did not exit within 75 seconds"; L9: the uninstall poll timed out at 90 s, then `KillRunning`).
    - Hosted Windows lifecycle runs used: **4 of 4.**
  - **AC2, artifacts:** `windows-installer`, `linux-packages` and `macos-dmg` hold exactly `the-one-setup-0.12.0.dev1.exe`, `GleepGlorp_AI-0.12.0.dev1-x86_64.AppImage`, `gleepglorp-ai_0.12.0~dev1_amd64.deb` and `GleepGlorp_AI-0.12.0.dev1-arm64.dmg`. `scripts/release_assets.py --version 0.12.0.dev1` selected exactly those four (rc 0), wrote `SHA256SUMS`, and `sha256sum -c` gives OK ×4 (evidence `$HOME/the-one-m32-evidence/f4/leg5/assets/out`; nothing published).
- **Windows quit-during-boot** goes to a Developer (diagnosis, a unit test that fails first, the fix), with the L6 harness fix and a new L10 "quit during boot" row. Proving it on Windows needs a fifth hosted Windows run, which needs the operator's go.
- **The operator's go for a 5th hosted Windows run (2026-10-26):** "windows run is acceptable". One Windows-only dispatch to prove the quit-during-boot fix and the harness fixes, once the fix is reviewed.

## Leg 5: dry run 40263206440 findings and fixes

The release dry run on the hosted windows-2022 runner found one product defect and two harness defects.

**1. Quit while the page is still loading hangs (product, fixed).**
Root cause: `DesktopSession._on_quit` (`the_one/interfaces/desktop/shell.py`) destroyed only the main window. The launch splash is a second pywebview window, and the only things that close it are the main window's `loaded` handler (`_main_shown.wait(25)` then `_destroy_splash()`) and `_boot`'s own quit checkpoints. A quit that arrives after `publish_window` but before the page's `loaded` fired (L8 at 195.3 s, L9 about 1 s after launch) takes the `request_quit` "window" tag, so `quit_desktop` calls `_on_quit` from the HTTP thread; `loaded` never fires for a destroyed window, the splash stays open, `webview.start()` never returns, so the `finally: _graceful_shutdown` never runs (no "Shutting down" or "Finished server process"). The CLI's `--wait` then times out and KillRunning kills it. The windows before publish were already covered: `_abort_if_quit` destroys the splash, and the `quit_now` branch of step 6 calls `_destroy_splash()` after `_on_quit`. The tray Quit item hits the same hole.
Predates leg 2: yes. `git show f98f2c7:the_one/interfaces/desktop/shell.py` `_on_quit` (line 511) has the same body (stop icon, destroy main window, no splash teardown); the old `quit_desktop` also called it directly for a published window. The earlier green lifecycle run only quit after the page had loaded.
Fix: `DesktopSession._destroy_splash` is bound to `run()`'s idempotent `_destroy_splash` closure once the splash exists, and `_on_quit` calls it after destroying the main window. On macOS `_splash_blocked()` is true once `really_quit` is set, so it is a no-op there (darwin behaviour unchanged; the dock/terminate tests pass). No `sys.platform` added to shell.py.
Test: `tests/test_desktop_shell.py::test_quit_after_publish_before_page_loaded_destroys_the_splash` (win32 and linux policies) boots with the existing `_boot_harness`, leaves `loaded` unfired, calls `window_control.quit_desktop()` and asserts the main window and the splash are both destroyed. It failed first (splash.destroy not called), passes with the fix.

**WebView2 log line.** `WebView2 initialization failed ... NavigateToString` is the splash: `_splash_html()` embeds the brand logo as a base64 data URI and the page is 2,328,661 characters, above WebView2's 2 MB (2,097,152) `NavigateToString` limit, so on Windows the splash never renders its content. It is not the cause of the hang (splash teardown does not depend on its load). Separate pre-existing defect: note for a squawk (shrink the logo or serve the splash another way).

**2. Harness (lifecycle.ps1 / lib.ps1).**
- `Get-MainWindow` matched the splash ("GleepGlorp AI - starting") as the main window, so "visible main window" was satisfied by the splash and L6 read a rectangle of a window that was about to go: `Test-GeometryClose` then indexed a null. The splash is now excluded, `Test-GeometryClose` returns false on a null rectangle, and L6 waits up to 30 s for the real window's native rectangle and FAILs with a message if there is none.
- New `Wait-AppReady` (main window visible, route `visible:true`, 6 s settle) gates L8 and L9, so they test the normal case.
- New row L10 "quit during boot": `quit --wait` the moment `/api/live` answers; PASS = exit 0 within the bound, the drain line for the pid, no process left. It runs before L9 (the uninstall removes the install), so the run order is L1-L8, L10, L9; seeded FAIL not-run; README table, static test and self-tests updated (ten rows). The workflow step name "Installer lifecycle (L1-L9)" is pinned by a test and left unchanged.
- Verified: pwsh container self-tests for lifecycle.ps1 and lib.ps1 pass, ParseFile has 0 errors, ASCII and name-collision checks pass.

## squawk 0263: the Windows splash HTML

The splash embedded the 1024 px logo as a data URI (2,328,661 characters), over WebView2's ~2 MB `NavigateToString` limit. It now embeds a new 320 px `static/brand/gleepglorp_splash.png` (125 KB), giving 168,825 characters on every platform; the static glob in the three specs already collects it. `_destroy_splash` claims its teardown under a lock (review nit). Unit tests pin the size under 256 KB and the single destroy. Pending: the Windows run's app log must show no `NavigateToString` failure.
- **Squawk 0263 review** (Reviewer, Haiku): `[HANDOFF:confirmed]`. The new asset was untracked, so it is staged. The Flight Director made the one-line doc fix the reviewer named (`the_one/agents.md` line 70 now names `gleepglorp_splash.png`).
- **The Flight Director's error, again:** a mismatched check broke the commit chain, but a trailing `;` still dispatched `release.yml` (`40265725036`) on the old head `4caf728`. It was cancelled before any platform job started (windows, linux and macos `skipped`), so no Windows runner was used and the operator's 5th Windows run stands. From here on, a dispatch runs as its own command, after the push is verified.
