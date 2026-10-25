# packaging/windows/probe - the Windows premise probe (Mission 32 Flight 4, leg 1)

Build-time tooling (never imported by `the_one/`). One dispatch of `.github/workflows/windows-packages.yml`
with `-f mode=probe` answers the flight's premises W1-W6 on a hosted `windows-2022` runner and writes
`probe/SUMMARY.txt` in the `windows-packages-logs` artifact (7 days).

```bash
gh workflow run windows-packages.yml --ref flight/04-windows-and-release -f mode=probe
```

(The workflow must exist on `main` first, as the `.github/`-only stub `windows-packages.stub.yml`; its `on:` block
is frozen and pinned by `tests/test_windows_packages_workflow.py`. The stub is copied to `.github/workflows/` only on a `.github/`-only branch for the stub PR (it is now on `main` as PR #315, merge 6a77155), never on the flight branch.)

## Files

| file | role |
|---|---|
| `probe.ps1` | the driver: header, one function per row, `Set-Row` (throws on an unknown id), bounded waits, a global bound (also relative to the job start: `M32_T0` + 45 min), `try/finally` so the summary is always written; `== probe done` only on the normal completion path, `== probe aborted: <reason>` otherwise |
| `the-one-probe-quit.iss` | today's `the-one.iss` plus DD2 candidate (a): `ExecAsOriginalUser(quit --wait)`, a bounded 90 s poll for `the-one-app.exe` and `the-one.exe` to be gone, then `KillRunning`; every stage logs a line (`quit-call`, `quit-poll: present`, `quit-poll: gone`, `quit-poll: nothing left`, `quit-killrunning`). For W4 (built at N+1) |
| `the-one-probe-rm.iss` | today's `.iss` with `CloseApplications=yes` and no `KillRunning` call. For W3 (built at N+2) |
| `windows-packages.stub.yml` | working copy of the `main` stub (an echo job, same `on:` block) |

The probe builds N (the `version` input, or `render.py --next-version` of `__version__`, so N never equals a released version),
N+1 and N+2 from one unstaged freeze. The frozen app reports `__version__` for all three, so the probe tells the
installers apart by the uninstall key's `DisplayVersion` and the `/LOG`, never by `/api/info`. It tells the v0.11.8 app
from today's by `GET /api/window/state`: 404 on v0.11.8, 200 now.

## Rows

Every W row is seeded `FAIL <id> not-run` and replaced only by the code path that performed the check. The final step
fails the job on a missing `SUMMARY.txt`, a missing `== probe done`, any `^FAIL` line or a failed build step.

| row | what | PASS needs |
|---|---|---|
| W6 | the v0.11.8 release installer installs silently and runs; N installs over it while running | download ok; v0.11.8 install rc 0; the old app answers (`/api/info` 0.11.8, window/state 404); N install rc 0; `DisplayVersion` is N; window/state 200 on N. INFO: install dirs, uninstall entries, Start-menu links, force-path lines, data marker (`probe-marker` agent) surviving |
| W1 | window | a native `IsWindowVisible` window titled `GleepGlorp AI` owned by an app pid within 60 s, and a screenshot whose pixel stddev is above 3 (a flat or black screen fails) |
| W2 | tray | `Shell_TrayWnd` present and no `System tray unavailable` line in the new app-log bytes since launch. `doctor`'s `tray:` line is INFO (static text on Windows) |
| W5 | close to tray | `WM_CLOSE` to the found handle (visible before, post ok): not visible within 10 s, pid alive |
| W4 | graceful quit | control `the-one.exe quit --wait` drains the app; then the quit variant's installer over a running app: `present` before `gone`, `nothing left` before `KillRunning`, the first file copy after, and the app's drain line before the first copy |
| W3 | the Restart Manager alone | INFO only: the `/LOG`'s RM lines, order, whether the app closed (gracefully), files replaced, exit code. Every installer is bounded; on timeout the probe kills its own recorded pid and records `installer did not finish` |

The state route's `visible` is `state.tracked_visible`, which close-to-tray never clears on Windows (fixed in leg 2), so
W1 and W5 judge on native `IsWindowVisible` and record the route's value as INFO only.

## The drain line

A graceful drain is uvicorn's `Finished server process [<pid>]`, matched to the app's pid (with `Application shutdown
complete.` before it), read from the NEW bytes of `%LOCALAPPDATA%\the-one\logs\the-one-app.log`. The windowed exe has no
stdout or stderr, so `ensure_stdio_streams` (`the_one/platform/env.py`) appends both to that file, and uvicorn is created
with `log_level="info"` (`the_one/interfaces/desktop/shell.py`, `uvicorn.Server(uvicorn.Config(...))`). The line comes from
`uvicorn.Server.serve()`, which logs it only after `shutdown()` returns, and `_graceful_shutdown` (`should_exit = True`,
then the join) is what reaches it; `taskkill /F` ends the process before it can log. No product log line was added.

## Ordering across sources

`Invoke-Installer` polls the installer's `/LOG`, the app log's new bytes and the watched pid about every 250 ms and stamps
each event's first-seen time from one clock (resolution 250 ms, stated in the summary header). Order inside the `/LOG`
comes from the position of its lines, not from the watcher.
