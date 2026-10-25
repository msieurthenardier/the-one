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

