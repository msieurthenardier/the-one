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

- **Leg 1 checkpoint review (Reviewer, Haiku; the diff touches no security-sensitive surface):**
  - Cycle 1 was not confirmed. Three blocking items: undeclared `GetTickCount`/`Sleep` in the quit variant, too short an ISCC step, and the job-budget arithmetic. All fixed, together with the non-blocking items.
  - Cycle 2: `[HANDOFF:confirmed]`.
  - Accepted, not fixed:
    - A1: the probe step's 42-minute backstop counts from the step's own start, so only a hang past the in-script bound could reach the job cap;
    - A2: the tests pin strings, not the bound's arithmetic;
    - A3: the wording of `== probe done` when the bound cut rows short (they stay `FAIL not-run`, so the job is red anyway).

