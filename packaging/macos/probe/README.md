# packaging/macos/probe - the macOS premise probe (Mission 32 Flight 3, leg 2)

Build-time tooling (never imported by `the_one/`). One dispatch of `.github/workflows/macos-packages.yml`
with `-f mode=probe` answers the flight's premises P1-P9 and reads the bundle's `LC_BUILD_VERSION`. It
records **observations, never PASS/FAIL**: each premise is one `P<n>: ...` row in
`$M32_LOGS/probe/SUMMARY.txt`, with the raw evidence in `$M32_LOGS/probe/P<n>/`.

## Files

| file | role |
|---|---|
| `delegate_probe.py` | the probe app: a pywebview window on a data URL, no server, no product code. Subclasses `BrowserView.AppDelegate` (`applicationShouldTerminate_` defined with no explicit signature so PyObjC takes the inherited prototype, returns `NSTerminateLater`, replies after 3 s; the reopen handler's signature is read from the `NSApplicationDelegate` protocol; `applicationWillTerminate_`; every signature is read from the runtime and logged, never hard-coded; leg 3's `Q@:@` raised `BadPrototypeError` against the installed `I@:@`). Logs `NSApp.delegate().className()` once the window shows. Modes `wait`, `destroy` (P9), `--selftest` (exit 3 when no delegate route installed, so the workflow's selftest step goes red while the premise probe still runs). Logs to `~/Library/Logs/m32-probe/probe.log` |
| `probe.spec` | PyInstaller spec -> `M32 Probe.app` (`ai.gleepglorp.m32probe`, min OS 11.0, no ATS key). The pyobjc hidden imports are listed explicitly; Linux Analysis cannot prove them (no pyobjc there), the runner's `--selftest` step does |
| `probe.sh` | the driver (`probe.sh PRODUCT_APP PROBE_APP BUNDLE_ID OUT_DIR`) |
| `macos-packages.stub.yml` | working copy of the `main` stub (an echo job; same `on:` block as the branch copy). Never place it under `.github/workflows/`; the Flight Director copies it into the stub PR |

The product `.app` here is built from `main`'s desktop code, so its rows describe today's build, not the target.

## Premises: how each is acted on, what is recorded

Apps are always addressed by absolute path (an Apple event to a not-running app launches it).

| premise | acted on | recorded |
|---|---|---|
| P7 | `xcode-select -p`, `/usr/bin/python3 --version` | rc, path, version |
| OTOOL | `file` over the bundle, `otool -l` per Mach-O | table of minos values and their counts, the maximum and its files (`OTOOL/`) |
| P8 | product via plain `open`; probe via `open --env M32_PROBE_ENV=1` | `ps eww`, `ps -Eww -o command=`, `lsappinfo info`: PATH, SHELL, HOME, TMPDIR; the probe's own log line shows whether `--env` passed (the product's `--env THE_ONE_PORT` already worked in Flight 1) |
| P1 | rm the data dir; cold launch, then quit and warm launch; `screencapture` at +1, +2, +3, +5, +10, +20, +30 s with `/api/live` and `/api/window/state` at each; control: the probe's data-URL window at +1, +2, +3, +5, +10 s | `P1/<tag>-series.tsv` and PNGs; screenshot byte size is a crude blank-vs-painted hint, read the PNGs. Control separates a slow WKWebView from our shell |
| P4 | `open -a` on each running app; `open -n` on the product | pid sets before/after, the probe's reopen log line, the second process's life, `lsappinfo front` and a screenshot |
| P2 | `tell application "<path>" to quit`, product then probe | rc, exit and time, the probe's terminate/reply log lines, registered selector signatures |
| PLN | after the product's first (cold) launch, before any dismissal: screenshot and a System Events read of the alert windows of `UserNotificationCenter`, `CoreServicesUIAgent`, `SecurityAgent`, `NotificationCenter`, `universalaccessd` | owner, window name, texts and buttons (`P1/pln-read-lnp.txt`, `P1/pln.png`); whether it names GleepGlorp AI; the dismissal attempt (Allow, else Don't Allow). Every probe launch (P8, P4, P2, P3, P9; P1's control after its series) also attempts a dismissal so a stale prompt does not overlay later screenshots (`<tag>-lnp.txt`) |
| P3 | System Events Cmd-W and Cmd-Q with each app frontmost; the probe's Cmd-W follows a raise and a click at the centre of its window (System Events `click at`) | rc and stderr (TCC shows here), `lsappinfo front` match, the window's count/visible/frontmost/position/size before and 2 s after Cmd-W, state before/after, which probe path ran: T (`applicationShouldTerminate_` logged) or S (`webview.start` returned with no terminate line) |
| P9 | the probe destroys its last window from a worker | time until `webview.start` returns, or the hang line |
| P5 | copy the product to `/Applications` (else `~/Applications`), launch, replace with a marked, re-signed copy while running, `open -a` | pid before/after, whether the old process answers |
| P6 (last) | quarantine xattr on a copy in `~/Downloads`; `spctl`, `syspolicy_check`, bounded `open`, screenshot, a dismiss attempt | assessment text, whether a process started and its path (AppTranslocation?), dismiss result |

`doctor` from a translocated path is dropped (translocation happens only through a LaunchServices launch; P6
records the launched process's path instead).

## Bounds

- Every `osascript` (15 s; the local-network alert read, 8 s), `screencapture` (10), `open` (20), `spctl`/`syspolicy_check` (20), `log show` (25),
  `lsappinfo` (10), `the-one quit` (15), `ditto` (60), `codesign` (40) call runs through `tl <seconds>`
  (a perl alarm); `curl` has `-m`.
- Each premise runs as a child (`probe.sh --run Pn`) under its own hard cap, so the worst case is the sum of the
  caps, not a count of inner calls. A cap that fires writes a row saying so, and the child's EXIT trap stops every
  tracked pid.
- Pids: discovered by filtering `ps` on a bundle's absolute executable path (or the probe's startup log line),
  recorded in `tracked.pids`, stopped only by that pid (TERM, KILL after 10 s). Before and after each premise the
  driver stops tracked pids and checks that port 8484 has no listener (a finding goes into the premise's row).
- The driver traps EXIT/TERM/INT/ALRM. It exits non-zero only for its own error (a missing input).

| premise | cap (s) | typical (s) |
|---|---|---|
| P7 | 20 | 2 |
| OTOOL | 70 | 30 |
| P8 | 120 | 35 |
| P1 | 260 | 140 |
| P4 | 110 | 40 |
| P2 | 110 | 40 |
| P3 | 180 | 90 |
| P9 | 60 | 12 |
| P5 | 80 | 40 |
| P6 | 100 | 45 |
| **sum** | **1110** | **about 480 (8 min)** |

Worst case: 1110 s of caps, plus at most 11 stop waits of 10 s (about 1220 s, 20.3 min) -- under the workflow
step's 23 min (`timeout-minutes: 23`); the outer `tl` bound is 1290 s. The Premise probe step runs with
`!cancelled()`, so a failed selftest still yields the evidence and the upload. Typical wall time is estimated at
8-9 minutes (the premise launches are the cost), at most 15.

## Reading the evidence

`SUMMARY.txt` first, then `P<n>/*.txt|png|tsv`, `P<n>/*-probe.log` for the probe's side, `*.stdout|stderr` for the
product's launch output. `tracked.pids` and `quiesce.log` show every pid started and
any forced kill.
