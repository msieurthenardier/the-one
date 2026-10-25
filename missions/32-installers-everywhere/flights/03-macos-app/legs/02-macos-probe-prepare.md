# Leg: macos-probe-prepare

**Status**: completed
**Flight**: [macOS app](../flight.md)

## Objective
Prepare everything one hosted macOS dispatch needs to answer the flight's premises (P1-P9 and the `LC_BUILD_VERSION` read): the dispatch-only `macos-packages.yml` workflow (branch copy and `main` stub), a minimal probe `.app`, and a probe driver. All of it is rehearsed by execution on Linux, so the dispatch spends its minutes on the premises, not on harness bugs.

## Context
- **Flight DDs:** DD9 (the premises and how each is acted on and observed), DD10 (the workflow, the stub PR, cost guards, rehearsal by execution, a budget of 4 dispatches with 1 spent by leg 3), DD11 (the first-paint series), DD4 (what the probe `.app` must prove), DD3 (the two quit paths), DD5 (P5), DD7 (P8), DD8 (the `otool` read).
- **This leg has no outward step.** It does not push, open a PR or dispatch. The Flight Director does those between this leg and leg 3, with the operator's standing go for a `.github/`-only stub PR (as #310) and the flight's budget.
- **Runs beside leg 1**, on disjoint files: this leg touches `packaging/macos/` and `.github/workflows/` only. Leg 1 touches `the_one/` and `tests/`.
  - Because leg 3 dispatches from the pushed branch, this leg's files are committed alone, by the Flight Director, after review.
  - The product `.app` in the probe is therefore built from `main`'s desktop code. Its observations describe today's build (DD9), not the target.
- **What Flight 1 already showed** (`packaging/macos/checks.sh`, run 2 evidence in the Flight 1 log):
  - the runner has a GUI session;
  - `open -n --env THE_ONE_PORT=8490 --env THE_ONE_DATA_DIR=…` launched the app on port 8490, so **`open --env` does pass variables** (P8's second half is likely answered; the probe still records it with `ps eww`);
  - `screencapture -x` works;
  - `perl`-alarm bounding works (`tl`).
- **Lessons the harness must carry:**
  - Flight 1's first-run harness bugs: `$WORK` created late, a PowerShell case-insensitive variable clobber, empty-string env restores;
  - Flight 2 leg 9's rehearsal-by-execution, which caught three bugs before a green first dispatch;
  - macOS bash is 3.2: no `mapfile`, no `${var,,}`, no `[[ =~ ]]` captures, and `"${a[@]}"` of an empty array under `set -u` needs `${a[@]+"${a[@]}"}`.

## Inputs
- `packaging/macos/{build.sh,checks.sh,the-one.spec,frozen_entry_mac.py,make-icns.py,README.md}` (Flight 1's prototype).
- `.github/workflows/packaging-probe-macos.yml` (on `main`), `.github/workflows/linux-packages.yml` (the pattern), the `#310` stub (`git show ea5d8c0`).
- pywebview 5.4 and pyobjc in the locked closure (`uv export … --extra gui`); PyInstaller 6.22.3 pinned in `build.sh`.

## Outputs
- **`.github/workflows/macos-packages.yml`** (branch copy): dispatch-only plus `workflow_call`, on `macos-15`.
  - **Inputs, frozen for the whole flight:**
    - `version` (string, empty = `__version__`);
    - `mode` (`full` | `lifecycle` | `probe`; a `choice` under `workflow_dispatch`, a `string` under `workflow_call`, default `full`).

    GitHub validates dispatch inputs against `main`'s stub, so the branch's `on:` block can't diverge from it. `lifecycle` is reserved for legs 6-7 (N and N+1 freezes plus `lifecycle.sh`). In this leg it runs the same steps as `full`. Adding an input later needs another stub PR.
  - **`probe` mode**, in one job:
    1. builds the product `.app` with today's `packaging/macos/build.sh` and `M32_SKIP_CHECKS=1`, which skips **all** of `checks.sh`. Its `doctor`/`serve`/gate-4 runs would create the default data dir and a credential before P1, so P1 would not be a cold first launch. The switch also saves about 5 min;
    2. freezes the probe `.app`, then runs it once with `--selftest` (bounded at 60 s). That imports `webview.platforms.cocoa`, `AppKit`, `Foundation`, `WebKit`, `objc` and `PyObjCTools.AppHelper`, defines the delegate subclass, prints the registered signatures and exits 0. A missing hidden import shows here, as a clear step failure, not as a dead probe mid-run;
    3. runs `packaging/macos/probe/probe.sh` under an outer `tl` bound, in a step with `timeout-minutes: 20`.
  - **`full` mode** runs today's Flight 1 build and checks unchanged, so the workflow is never broken. Leg 6 replaces it.
  - **Guards (Flight 1's, kept):**
    - a job timeout of 50 min, and a timeout on every step;
    - `concurrency: macos-packages` with `cancel-in-progress: false`;
    - `permissions: contents: read`, no secrets;
    - `defaults: run: shell: bash`;
    - uploads: the logs and evidence directory (`retention-days: 7`). In probe mode, no `.app`/`.dmg` upload.
- **`packaging/macos/probe/macos-packages.stub.yml`**, the working copy of the stub. It never goes under `.github/workflows/`, where GitHub would load it as a second workflow. Its `on:` block is byte-identical to the branch copy's, and it has one echo job, as #310 did. The Flight Director copies it into the stub PR.
- **`packaging/macos/probe/`** (new; build-time tooling, never imported by `the_one/`):
  - `delegate_probe.py`, a ~150-200-line pywebview app with no product code (sketched under Implementation Guidance), with the modes `wait`, `destroy` and `--selftest`;
  - `probe.spec`, a PyInstaller spec that freezes it into `M32 Probe.app` with a `BUNDLE` (bundle id `ai.gleepglorp.m32probe`, `LSMinimumSystemVersion` 11.0, NO ATS key: the probe app tests what pywebview's in-memory key alone does);
  - `probe.sh`, the driver;
  - `README.md`, saying what each premise is, how it is acted on, what it records, and how to read the evidence.
- **Removal:** `.github/workflows/packaging-probe-macos.yml` is deleted on the branch; `main` keeps its copy until this flight's PR merges.
- **`packaging/macos/README.md`** gains a short "Probe mode" pointer.

## Acceptance Criteria
- [x] **AC1 — The workflow.**
  - `actionlint` (1.7.7, the tool Flight 1 and 2 used) is clean on `macos-packages.yml` and on the stub copy.
  - The two `on:` blocks are byte-identical (checked with a script that extracts both, recorded).
  - The trigger list has only `workflow_dispatch` and `workflow_call`: no `push`, `pull_request` or `schedule`.
  - Every job and step has a `timeout-minutes`.
  - No `secrets.` reference.
- [x] **AC2 — The probe `.app` freezes.** `delegate_probe.py` passes `ruff` and `py_compile`. `probe.spec` runs through PyInstaller Analysis on Linux against the build venv (its `BUNDLE` is a no-op there), as Flight 1 rehearsed the product spec. The pyobjc/`webview.platforms.cocoa` hidden imports are listed explicitly. The Linux venv has no pyobjc (darwin markers), so Analysis cannot prove them. The runner's `--selftest` step is the real check, and the leg says so.
- [x] **AC3 — The driver covers every premise.** For each item below, `probe.sh` writes evidence files and a one-line `P<n>: …` row in `$M32_LOGS/probe/SUMMARY.txt`, saying what was observed, never PASS/FAIL. A premise it could not act on records why: a timeout, a refused TCC prompt, `rc` and stderr.
  - **P1** (product, cold then warm):
    - first `rm -rf "$HOME/Library/Application Support/the-one"`, so the cold launch is a first-ever launch;
    - `open` with `--stdout`/`--stderr` to absolute, pre-created files;
    - a `screencapture -x` series at +1, +3, +5, +10, +20 and +30 s, with `/api/live` and `/api/window/state` at each mark;
    - then quit with `the-one quit` and repeat for the warm launch.

    **Control:** the same series (+1, +3, +5, +10 s) on the probe `.app`'s data-URL window, with no server. It separates "WKWebView is slow on this runner" from "our shell" (DD11).
  - **P2:** the quit Apple event to the product app and to the probe app, **addressed by path** (`tell application "/abs/path/X.app" to quit`), never by id or name. Several copies exist by P5/P6, and an Apple event to an app that isn't running launches it. The driver asserts the target pid is alive immediately before sending. Recorded: did the process exit, how long it took, and the probe's log (`terminate` called? `NSTerminateLater` returned, then the reply after 3 s?).
  - **P3:** System Events `keystroke "w" using command down`, then `keystroke "q" using command down`, with each app frontmost (after `open -a`). Recorded: rc and stderr (a TCC refusal shows here), the visible state before and after, and, for the probe, which quit path ran (the delegate's `applicationShouldTerminate_` log line, or `webview.start` returning with no terminate log).
  - **P4:**
    - `open -a` on each running app: the pid set before and after (`ps -axo pid,command` filtered to the bundle's executable path), and the probe's reopen log line;
    - then `open -n` the product app: a second process appears and exits after focusing (`/api/window/focus`'s answer is in the product log), and `lsappinfo front` plus a screenshot show which app is frontmost.
  - **P5:**
    - copy the product `.app` to `/Applications` and launch it;
    - make a marked copy: add `Contents/Resources/m32-marker`, then re-sign ad-hoc;
    - remove `/Applications/GleepGlorp AI.app` (`rm -rf`) and `ditto` the marked copy in, all while running;
    - `open -a`.

    Recorded: the pid before and after, and whether the answering process is the old one. `/api/window/state`'s `pid` and `version` are identical across both copies, so the marker is checked through the new process's `ps` path plus `lsof` on the marker, or simply whether the pid changed.
  - **P6 (runs last; nothing runs after it):**
    - `xattr -w com.apple.quarantine "0083;<hex time>;Safari;"` on a copy in `~/Downloads`;
    - `spctl -a -vv -t exec` and (if present) `syspolicy_check distribution` output;
    - `open` that copy (bounded at 30 s): what happens (a process starts or not), a screenshot, and the process path if one started (translocation shows as `/private/var/folders/.../AppTranslocation/...`);
    - every started process is stopped by recorded pid;
    - a Gatekeeper dialog may stay up after the bounded `open`. Take the screenshot first, then try a bounded `osascript` to dismiss it, and record whether that worked;
    - DD9's "`doctor` from a translocated path" is dropped here: translocation happens only through a LaunchServices launch, and P6 records the launched process's path instead. The leg 7 lifecycle check or the contributor check covers `doctor` itself.
  - **P7:** `xcode-select -p` (rc and path), `/usr/bin/python3 --version`.
  - **P8:** the environment of an `open`-launched product app (no `--env`), captured with all three forms (BSD `ps` may drop the environment with `-o command=`): `ps eww -p <pid>`, `ps -Eww -p <pid> -o command=`, and `lsappinfo info -only <keys> <asn>`. Recorded: its `PATH`, `SHELL`, `HOME` and `TMPDIR`. Then the same with `--env M32_PROBE_ENV=1`.
  - **P9 (informational):** the probe app destroys its last window from a worker thread and logs the time until `webview.start` returns (or the 20 s bound).
  - **`LC_BUILD_VERSION`:** for every Mach-O file in the product `.app` (`file` says Mach-O), `otool -l | grep -A4 LC_BUILD_VERSION` minos. Written as a sorted table plus the maximum (report-only).
- [x] **AC4 — Bounded, isolated and clean.**
  - Every `osascript`, `screencapture`, `open`, `spctl`, `syspolicy_check`, `log show` and `lsappinfo` call goes through `tl <seconds>`.
  - Every process the driver starts is recorded by pid and stopped by that pid (TERM, then KILL after 10 s). A pid may be **discovered** by filtering `ps` on the bundle's absolute executable path, or from the probe's own startup log line; it is only ever **stopped** by that recorded pid, never by name or pattern.
  - **Quiescence:** before and after each premise, the driver checks that no tracked pid is alive and that port 8484 has no listener (`lsof -nP -iTCP:8484 -sTCP:LISTEN`). It escalates TERM then KILL by pid. A premise that starts with something still listening says so in its row.
  - **Each quit scenario starts from a fresh launch** (`open -n -a /abs/path --args wait` for the probe; the product relaunched). An "is it up" gate (the probe's startup log line plus its pid alive; for the product, `/api/live` plus the pid) runs before every act.
  - **Before each keystroke (P3),** `lsappinfo front` is checked and any mismatch recorded. pywebview sets the activation policy to *regular* at import (`cocoa.py` module level), so each app should own the Dock and the menu bar when frontmost.
  - **Order:** P7, the `otool` read, P8, P1 (with control), P4, P2, P3, P9, P5, then P6 last.
  - **The worst-case total** (every bound firing) is computed from a bound table in the README and is at most the step's 20 min, with the outer `tl` just under it. The typical total is estimated too.
  - The driver traps `EXIT`, `TERM` and `INT`, so a step timeout still stops every tracked pid.
  - The driver never exits non-zero for an observation, only for its own error (a missing input). The workflow's probe step is `continue-on-error: true` so the upload always runs.
  - Total probe wall time is estimated in the README and is at most 15 min.
- [x] **AC5 — Rehearsed by execution on Linux** (the Flight 2 leg 9 pattern):
  - `probe.sh` runs to completion on the dev host against a fake `.app` tree, with shims on `PATH` for `open`, `osascript`, `screencapture`, `lsappinfo`, `spctl`, `syspolicy_check`, `xattr`, `ditto`, `codesign`, `otool`, `xcode-select`, `log`, `sw_vers`, `plutil`. The shims log their argv and return canned output. `ps eww` is a shim too, if the host's differs.
  - **Three rehearsal runs:**
    - all shims succeed;
    - `osascript` returns a TCC error (`-1743`) and never answers (the bound must fire);
    - `open` fails.
  - Each run writes a complete `SUMMARY.txt` with one row per premise, and the bounded call is shown timing out at its bound. In the `open`-fails run, P7 and the `otool` table are still present, which shows the premises are independent.
  - `shellcheck` is clean on `probe.sh`. A bash-3.2 syntax check passes: run it under a bash 3.2 binary if one is obtainable in a container, else a grep for the banned constructs, recorded.
  - The workflow's probe-mode steps are rehearsed: the step scripts extracted and run with the shims and a fake `RUNNER_TEMP`, so the paths, env and the step order are exercised.
- [x] **AC6 — Hygiene.**
  - Nothing outside `packaging/macos/` and `.github/workflows/` changed (plus this leg's flight-log section).
  - No push, PR or dispatch.
  - Rehearsal scratch lives under `$HOME/the-one-m32-build/f3/` and evidence under `$HOME/the-one-m32-evidence/f3/leg2/`.
  - No port 8484/8485; no containers left; nothing from the rehearsal is left running.

## Verification Steps
- AC1: `actionlint` output; the `on:`-block diff script output; `grep -n "timeout-minutes\|secrets\." …`.
- AC2: the PyInstaller Analysis log tail for `probe.spec` on Linux; `ruff check packaging/`.
- AC3/AC5: the three rehearsal `SUMMARY.txt` files, quoted in the flight log; the shim argv logs showing every premise's commands.
- AC4: a grep listing each bounded command and its bound; the rehearsal run in which the bound fired.
- AC6: `git status --porcelain`.

## Implementation Guidance
1. **The probe app (`delegate_probe.py`).** It runs only on darwin (it exits 2 elsewhere with a message), imports `webview` and, after `webview` initialises Cocoa, `webview.platforms.cocoa.BrowserView`, `AppKit`, `Foundation`, `objc`, `PyObjCTools.AppHelper`. Before `webview.start`, on the main thread, it:
   - defines `class M32ProbeAppDelegate(BrowserView.AppDelegate)` (a unique Objective-C name) with:
     - `applicationShouldTerminate_(self, app)`, declared explicitly as leg 4 will declare it: `@objc.typedSelector(b"Q@:@")` or the equivalent signature, an `NSUInteger` return. It logs, returns `AppKit.NSTerminateLater` (2), and starts a thread that sleeps 3 s, logs, then `AppHelper.callAfter(app.replyToApplicationShouldTerminate_, True)`. At startup the probe logs the registered selector signature of this method and of the superclass's, since what the probe really tests is whether the return type survives;
     - `applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag)`: logs and returns `False`;
     - `applicationWillTerminate_`: logs (to show AppKit reached its exit);
   - sets `BrowserView.AppDelegate = M32ProbeAppDelegate`;
   - logs the class actually set as the app's delegate, once the window exists (`NSApp.delegate().className()`);
   - creates one window loading a data URL with a timestamp.

   It writes every log line, flushed, to `~/Library/Logs/m32-probe/probe.log` (fixed, so an `open` launch without env still logs). Its first line records its own pid and `sys.executable`, which is how the driver tracks an `open`-launched probe (`open` returns no pid).
   - **Modes, chosen by argv** (passed through `open --args`):
     - `wait` (default; stays up);
     - `destroy` (P9: after 5 s, a worker calls `window.destroy()` and the main code logs when `webview.start` returns);
     - `--selftest` (the imports, the subclass definition, the signature log, exit 0; no window).

     Every exit path logs whether `applicationShouldTerminate_` ran first, which is how P3 tells path T from path S: a "terminate" line means T; `start` returning with no terminate line means S.
   - Also log `NSProcessInfo.processInfo().arguments()` and the environment's `PATH`.
   - Read pywebview 5.4's `cocoa.py` first, to confirm the class attribute is looked up at `BrowserView.__init__` (`BrowserView.AppDelegate.alloc()`) and that the subclass definition must come after `webview` has imported its Cocoa backend. If the subclass cannot be defined because of how PyObjC handles subclasses of Python-defined `NSObject` subclasses, use `objc.classAddMethods(BrowserView.AppDelegate, [...])` and log which route was used.
2. **The driver (`probe.sh`).**
   - Arguments: the product `.app` path, the probe `.app` path, the product's bundle id (a parameter: today `ai.gleepglorp.the-one`, which DD8 changes in leg 6), and an output dir. Apps are addressed by absolute path everywhere.
   - Structure: one function per premise, each writing `$OUT/P<n>/` and appending its summary row.
   - Use `tl` (copied from `build.sh`).
   - A pid registry file: `start_tracked` and `stop_tracked`, and an EXIT trap that stops everything still registered.
   - Product launches use `THE_ONE_DATA_DIR` only where a test needs isolation. P1 uses the default data dir (the runner is disposable) so the credential path matches DD9's read path. Keep a premise's state out of the next premise's way, and quit between premises.
   - The credential for authenticated reads comes from `~/Library/Application Support/the-one/api-credential`. Only its `loc_<id>` prefix is ever echoed.
3. **The workflow.** Record `/Applications` writability (`test -w`) in the runner evidence step.
   - Start from `packaging-probe-macos.yml`'s steps (runner evidence, `setup-python` 3.11, the closure export with `uv==0.10.0`, the version), then `build.sh`, then the probe freeze (`pyinstaller packaging/macos/probe/probe.spec` in the same venv), then `probe.sh`.
   - `build.sh` takes an `M32_SKIP_CHECKS=1` switch that skips `checks.sh` entirely. That is the only edit to Flight 1's scripts in this leg.
4. **Rehearsal.** Write the shims under the rehearsal scratch dir, not in the repo. Run the three scenarios and record them. Keep the rehearsal script itself out of the repo too; copy it to the evidence dir.

## Edge Cases
- **A Gatekeeper dialog (P6) is also modal,** which is why P6 runs last.
- **A TCC prompt is modal and silent to the shell.** The bound is the only defence. After any bounded failure, take a screenshot so the evidence shows the prompt.
- **An app that never exits after a quit attempt** is stopped by pid at the end of that premise, and the row says so.
- **`/Applications` may not be writable** (it is on GitHub's images, but check): if `ditto` fails, P5 records it and uses `~/Applications`.
- **`lsappinfo` may need the GUI session.** If it errors, record the error and rely on the screenshot.
- **The product app built from `main`** builds pystray on darwin on a worker thread. It may crash or log an AppKit thread warning. That is evidence for DD2, recorded in P1's row, not a harness failure.

## Files Affected
- `.github/workflows/macos-packages.yml` (new), `.github/workflows/packaging-probe-macos.yml` (deleted)
- `packaging/macos/probe/{delegate_probe.py,probe.spec,probe.sh,README.md,macos-packages.stub.yml}` (new)
- `packaging/macos/build.sh` (one skip switch), `packaging/macos/README.md` (pointer)

### Citation Audit
Checked at `09bdda5`:
- `packaging/macos/checks.sh`'s `tl` and its `open -n --env` block;
- `build.sh`'s steps and the PyInstaller pins;
- `packaging-probe-macos.yml`'s steps;
- the `#310` stub shape (`git show ea5d8c0`);
- `cocoa.py`'s `BrowserView.AppDelegate.alloc()` in `BrowserView.__init__`, and `applicationShouldTerminate_` in `AppDelegate`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
