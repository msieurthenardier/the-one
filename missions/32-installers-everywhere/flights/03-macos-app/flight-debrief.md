# Flight Debrief: macOS app

**Date**: 2026-10-25
**Flight**: [macOS app](flight.md)
**Status**: completed
**Duration**: 2026-10-24 (planning) - 2026-10-25 (landed)
**Legs Completed**: 9 of 9 (planned as 8; `macos-probe-rerun` was added after the first probe lost its delegate answer)
**Plugin version**: mission-control 1.2.2

## Outcome Assessment

### Objectives Achieved
GleepGlorp AI ships for macOS as an ad-hoc signed `GleepGlorp AI.app` in a drag-to-Applications `.dmg`, for macOS 14 or later on Apple Silicon. It behaves like a Mac app:
- closing the window hides it while the app stays in the Dock;
- the Dock icon (or `open -a`) brings it back;
- every quit drains the server before the process exits: the app menu, Cmd-Q, the Dock, the quit Apple event, logout, and `the-one quit`;
- a second launch focuses the running window;
- the window's size and position are remembered;
- the main window waits for its page, so no empty frame shows.

The frozen runtime is safe on a stock Mac: the Command Line Tools `python3` stub is never run, the interpreter search walks every `PATH` entry, and a Finder launch gets the login shell's `PATH`. `doctor` reports `tray: dock`, the `PATH` source and a Cocoa desktop-shell gate.

The work, in order:
- **The split first.** `shell.py` (1478 lines) was split into `takeover.py`, `window_control.py` and `session_state.py` (debrief recommendation 1 from Flight 2), with a guard against test patches that miss. The Dock mode then landed in its own `macos_dock.py` rather than in the monolith.
- **The recipe:**
  - it reads `packaging/product.toml` through `render.py`, with one app id shared with Linux (Linux output byte-identical apart from a key name);
  - an Info.plist with App Nap off and local networking allowed;
  - an enforcing bundle audit;
  - a Finder-launch log at `~/Library/Logs/GleepGlorp AI/app.log`.
- **The workflow:** `macos-packages.yml` gained `full`, `lifecycle` and `probe` modes. `lifecycle.sh` drives the installed app on a hosted runner through 13 steps.
- **The proof:** two lifecycle runs (`40214604211` and `40228973240`) each passed 13/13 build checks and 13/13 lifecycle steps.
- **Docs:** `docs/macos-install.md` and `docs/macos-contributor-check.md`, and the `macos-app-install` behavior test drafted for Flight 4's contributor run.

### Mission Criteria Advanced
- **macOS install, without an Apple developer account: met for the build and the runner.** Drag install from the `.dmg`, the first window and the Dock icon are proven on the runner. Gatekeeper's "Open Anyway" flow (macOS 15 shows "Not Opened" with no Open button) is documented but not observable there; the contributor check confirms it (Flight 4).
- **The frozen runtime works in every build: met on macOS.** Strict `doctor` passes inside the built app on the runner, and a failed seam fails the build. The stub rule and the login-shell `PATH` are unit-tested; a stock Mac without Python is a contributor item.
- **The window behaves like a native app: met on macOS, as far as a runner can drive.** Close, reopen, second launch, geometry and four quit paths with their drain are proven. A real Dock click, the Dock menu's Quit and logout are for the contributor.
- **Upgrades keep the user's data: met.** N to N+1 keeps the provider, agent, chat and credential, and moving the app to the Trash keeps the data. **Replacing the app while it runs crashes the old copy** (pywebview's JS dir disappears), so the guide says to quit first.
- **One packaging source of truth, built within the CI budget: advanced.** macOS reads `product.toml` (one `app_id`); manual runs only. The budget was 5 of 5 dispatches (the operator raised it from 4), about 230 billed minutes.
- **Install guides for every platform: macOS done.**
- **Existing gates pass: met** (see Test metrics).

## What Went Well
- **The split first (DD1) paid back immediately.** Leg 1 changed no behaviour: the unit tier, the `settings` lane, the Linux GTK smoke on both baselines, a takeover over Flight 2's `~dev20` `.deb`, and the container gates all passed. Legs 4 and 5 then built the macOS states in new modules. The guard caught 122 test patch sites to re-point, and one stale patch that had been silently patching nothing.
- **Premise probes before building (DD9) worked as intended:**
  - the runner's GUI session, Accessibility and the quit Apple event;
  - Gatekeeper's real dialog;
  - `open --env`;
  - the inherited `PATH`;
  - the `LC_BUILD_VERSION` minimums (which set `min_os` 14.0);
  - the delegate subclass and the `NSTerminateLater` reply.

  All were settled before leg 4's code depended on them. No divert criterion triggered.
- **Design reviews caught the AppKit traps on paper:**
  - Cmd-Q's second path (`WebKitHost.keyDown_` → `app.stop_`);
  - `destroy()` reaching `app.stop_` without an event;
  - the splash's `windowWillClose_` stopping the loop mid-drain;
  - path S having no exit (a non-daemon `_boot`);
  - a boot abort re-entering a pending terminate;
  - the spec rendering from the staged copy;
  - universal2 wheels failing an arm64-only audit;
  - two owners for `checks.sh`;
  - a timeout layering that could lose the evidence upload.

  Each was fixed before it cost a run.
- **A pure decision core plus a thin PyObjC layer (DD4)** kept the Dock logic unit-testable on Linux. A canary reads pywebview 5.4's `cocoa.py` with `ast` and pins the facts the design relies on.
- **Rehearsal by execution on Linux** (shims for every macOS tool) found 4 `lifecycle.sh` bugs and 1 timeout defect before dispatch. Three of the five dispatches went green on the first try.
- **Every hosted green was checked for vacuity.** Run 3's 3.5-minute green looked too fast, so a reader cross-checked every row against logs, state and screenshots before it was trusted (the freezes take about 30 s on that runner).
- **The remote HAT worked** (operator: "Worked well"). With no Mac, a private review page carried the runner's screenshots, the summaries and the decisions. It led to a real fix (P1) and a real defect found on all platforms (squawk 0260).
- **Parallel legs on disjoint files** (legs 1 and 2; 4 and 5; 4 and 6A) and early merge-main timing kept two Developers busy without collisions.

## What Could Be Improved

### Process
- **A probe hid its own failure (one dispatch lost).** Leg 2's `delegate_probe.py` hard-coded `applicationShouldTerminate:` as `Q@:@` (the runtime's is `I@:@`). Both install routes failed, the probe fell back to the stock delegate, and its `--selftest` passed anyway. Leg 3 then had to read the evidence to learn the premise was unanswered, and leg 3b plus dispatch 2 re-ran it.
  - The leg should have said: derive signatures from the superclass or the protocol, and make the selftest fail unless the intended route installs.
  - More generally: a premise probe needs a **positive control** and a **fail-loud check that the premise actually ran**.
- **A HAT finding was misdiagnosed before the operator decided.** The Flight Director described P1 as "the splash drawn with a title bar". The recorded fields (`visible=true` at +1 s, the window's title and size) showed it was the main window shown before its page painted. The correction was logged and the review page fixed, and the decision's intent was unchanged. Lesson: classify from the recorded fields before narrating a finding to the operator.
- **The macOS budget was fully used** (5 of 5, about 230 billed min; operator: "Acceptable"). One dispatch went to the probe bug above; the last verified the HAT fix, with nothing in reserve. Flight 4 should plan its macOS runs with one spare that stays spare.
- **Two leg sizes needed phases again** (legs 1, 4 and 6 in A/B). Flight 2 saw the same, so it is the norm for this mission's legs, not an exception.
- **Host contention with Mission 31:**
  - the flight-end browser gate ran at `--parallel 2` beside Mission 31's lanes;
  - its first launch briefly made four lanes host-wide (stopped within about 15 s by recorded pid);
  - the debrief Developer could not run tests at all while Mission 31's lane was live.

  Shared-host scheduling between concurrent missions is informal.

### Technical
- **Darwin branches are spreading.** `shell.py` (still 1056 lines) has 9 `sys.platform == "darwin"` branches inside `DesktopSession.run`/`_boot`, and `window_control.py` has 4. Three platform policies now interleave in one boot sequence. **Before Windows adds its own (Flight 4), move per-platform ordering behind a small platform-policy object or `macos_dock` hooks the shell calls unconditionally.**
- **The PyObjC bodies are proven only by hosted runs.** `macos_dock._install_delegate` and `_begin_activity` carry `# pragma: no cover`. A pywebview or PyObjC bump can break them silently on Linux CI; only the canary and a `lifecycle` dispatch catch it. That belongs in the dependency-bump procedure.
- **The shell harness is large and rehearsal-tested only:** `lifecycle.sh` 744 lines, `probe/probe.sh` 610, `lib.sh` 158, `checks.sh` 178. They are covered by shellcheck, bash 3.2 `-n` and shim rehearsals, with no unit-style tests. DD8 deferred a shared shell library and workflow consolidation to Flight 4.
- **`render.py` is now strict:** only `X.Y.Z` and `X.Y.Z.devN` are accepted, and every render, Linux included, fails otherwise. That is good for catching drift, but Flight 4's dynamic version must emit only that grammar. A test that feeds the release workflow's version through `render.load` should come with it.
- **Known product leftovers:**
  - replacing a running `.app` crashes the old process without a drain (no data loss seen; the guide says quit first);
  - the splash's card shows blank for about 1.5 s before its logo and text paint;
  - the second Dock icon on a second launch (accepted).
- **The login-shell `PATH` probe ran only under the runner's `SHELL=/bin/bash`.** A real zsh with nvm is a contributor-check item.
- **Test metrics** (this debrief, HEAD `129e913`, worktree `.venv` CPython 3.12, not under netns):
  - **Unit tier:** 7404 passed, 0 failed, 12 skipped (the expected Linux set), 2987 deselected; 364 s in pytest, 369 s wall; no flakes.
  - **Against earlier debriefs:** Flight 1 6783 passed, 341 s; Flight 2 7100 passed, 338.6 s. Now +304 tests over Flight 2. From the per-leg counts in the flight log, about 210 are this flight's own: leg 1's guard and `SessionState` +46, leg 5 +46, leg 4 +75, leg 6 +41, the P1 fix +5. About 90 arrived with Mission 31 Flight 4's merge.
  - **Time:** +26 s (+8%), within the run-to-run noise seen before (Flight 2 ran 338.6 s on fewer tests); not isolated.
  - **Browser lanes** (`--parallel 3`, netns, WebKit required, an idle host): `PARALLEL_RESULT rc=0 total=1542s lanes=13`. No lane over budget. The closest: `routing` 547/600 s and `chats` 422/450 s.
    - **Against Flight 2:** its 1411 s was at 12 lanes before Mission 31 Flight 4's merge added UI tests and the `settings-tools` lane. +131 s (+9%) for one more lane and the merged suite, with each lane's time within about 10% of Mission 31's measured table.
    - The flight-end gate's 2137 s (`--parallel 2`, beside Mission 31's lanes) is not comparable.
    - **Watch:** `chats` keeps landing within 30 s of its 450 s budget, and squawk 0259 (from Mission 31) already tracks it.

### Documentation
- **Add to `the_one/agents.md`:**
  - the test rule the split guard enforces ("patch a name in the module that defines it");
  - a pywebview/PyObjC upgrade checklist: run the canary and a `lifecycle` dispatch;
  - a line saying macOS CI is hosted-only and dispatch-limited.
- **The guide hedges** what the runner could not see (Open Anyway, Dock clicks, logout). The contributor run will confirm or correct them.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 3b (`macos-probe-rerun`) and dispatch 2 added | The probe hard-coded a delegate signature, and its selftest passed on the fallback | Yes: probes derive native signatures from the runtime and fail loudly unless the intended path ran |
| Dispatch cap raised from 4 to 5 | The re-probe | No: plan one spare that stays spare |
| `min_os` 11.0 → 14.0 | The bundled numpy's arm64 extensions require macOS 14 (`LC_BUILD_VERSION`) | Yes: set the minimum from the bundle's measured minos, never from wheel tags |
| Path S ends in `os._exit(0)` after the drain | pywebview runs `_boot` on a non-daemon thread | Yes: an explicit exit after a completed drain is part of the design, not a fallback |
| The DD9 test seam not built | Accessibility and the quit Apple event work on the runner | n/a |
| The Finder-launch log file added (`frozen_entry_mac.py`) | A Finder launch's output goes nowhere; contributors and `lifecycle.sh` need a log | Yes |
| `_destroy_splash` suppressed on quit states, not on `boot_stopped` alone | `_boot` sets `boot_stopped` on a normal boot too | n/a (a leg-text correction) |
| The P1 fix: on darwin the main window waits for its page (12 s fallback) | HAT: the main window showed before its page painted, covering the splash | Yes, for any platform whose web view paints late |
| Leg 2's planned "`doctor` from a translocated path" dropped | Translocation happens only through LaunchServices | No |
| Mission 31 Flight 4 merged mid-flight (`16484eb`) | It landed on `main` while legs ran | Yes: merge `main` at a checkpoint, never under running Developers |

## Key Learnings
1. **A probe that can silently fall back is not a probe.** Give every premise a positive control and a fail-loud check that the intended path actually ran.
2. **Classify a visual finding from the recorded state before describing it to the operator.** A window's title, size and the state route's `visible` told a different story than the screenshot alone.
3. **A green run that is suspiciously fast gets audited row by row before it counts.** Here it was genuinely fast; the habit is still right.
4. **Pure decisions plus a thin native layer plus a source canary** is the right shape for platform code that can only run on hardware the operator does not have.
5. **The bundle, not the wheel tags, sets the minimum OS.** `otool`'s `LC_BUILD_VERSION` read is cheap and authoritative.
6. **On macOS, pywebview's run loop has two quit paths and a missing-event stop.** Read the GUI toolkit's source for its quit and close paths before designing a lifecycle on top of it (it held for GTK in Flight 2 and for Cocoa here).

## Methodology Observations
Recorded against mission-control 1.2.2.

1. **`agentic-workflow`, Phase 2a (legs added mid-flight).**
   - **What happened:** when the probe's answer came back unanswered, the leg that read it (leg 3) was already `landed`. The skill's rule is that a leg is immutable once in-flight, and offers "abort and create a new one". The Flight Director created `03b-macos-probe-rerun` as a new leg beside a landed one and added it to the flight's leg list with an annotation.
   - **Expected:** a named pattern for "re-run a verification leg with a fixed apparatus".
   - **Cost:** a little artifact improvisation; no rework.
2. **`agentic-workflow`, Phase 2d (early review checkpoints).**
   - **What happened:** with hosted runs building from the pushed branch, the flight ran **five** review-and-commit checkpoints (legs 2; 1; 4+5; 6; 3b/7 plus the HAT fix) instead of one at the end.
   - **Recurrence:** Flights 1 and 2 recorded the same deviation, so this is now three flights in a row.
   - **Expected:** the skill names "checkpoint per hosted dispatch" as a mode.
   - **Cost:** the Flight Director designed the checkpoint plan each time.
3. **`agentic-workflow`, crew hand-backs ("background work").**
   - **What happened:** a Developer reported "waiting on its own background work" after finishing. The Flight Director found nothing running.
   - **Cost:** one check. A hand-back that says nothing is pending would save it.
4. **`flight`, Phase 4 (premise audits).**
   - **What happened:** the act/observe audit was thorough, but it did not ask whether **a probe's own success check can pass when the premise was never exercised**. That gap cost dispatch 1's delegate answer.
   - **Expected:** a third axis beside "can act" and "can observe": "will a non-answer read as a failure?".
5. **HAT with no hardware (positive).** The `agentic-workflow` HAT protocol assumes the operator performs steps. Here the "walk" was a review page of runner evidence plus decisions, and it worked (operator: "Worked well"). The skill could name this "evidence HAT" shape for platforms the operator cannot run.
6. **Shared-host concurrency between missions.** The skills have no notion of another mission's crew sharing the host's test capacity. The 3-lane host policy was enforced by Developers counting other sessions' processes; one brief over-run happened.
7. **`flight-debrief`, Phase 2 (test metrics).**
   - **What happened:** the Developer could not run tests while another session's browser lane was live. The Flight Director ran the unit tier and the browser gate itself once the host was free.
   - **Expected:** the skill could say what to do when the host is busy (wait, or record the latest gate with its commit).

## Recommendations
1. **Move per-platform boot policy out of `shell.py` before Flight 4 adds Windows branches** (Important). A small policy object (`show_main_when`, `close_behaviour`, `quit_path`, …) or `macos_dock`/`windows_*` hooks that `DesktopSession.run` calls unconditionally. There are 13 darwin branches today across `shell.py` and `window_control.py`.
2. **Make every premise probe fail loudly and carry a positive control** (Critical for Flight 4's Windows and release probes). A run where the intended path never executed must read red, not green.
3. **Flight 4: keep the strict version grammar end to end** (Important). The dynamic version emits only `X.Y.Z[.devN]`, with a test through `render.load`. Decide `CFBundleVersion` for release builds. Add a `[windows]` section to `product.toml` whose AppId derives from or matches `app_id`.
4. **Flight 4: probe Inno's close-running-app behaviour first** (Important), as P5 did for macOS. Reuse `takeover.py` and `the-one quit --wait` for a graceful replace, and consider the same guard for macOS (the old copy crashes when replaced while running).
5. **Fold the pywebview canary and a `lifecycle` dispatch into the dependency-bump procedure** (Important). The PyObjC bodies have no other net between releases.

## Action Items
- [ ] Flight 4 planning: recommendations 1, 3 and 4; budget the macOS runs (fresh `.dmg`s for the contributor check, with one spare); consolidate the three packaging workflows and the shell helpers (deferred by DD8); add the Windows `PATH`-walk regression tests (leg 5 changed `interpreter.py` for Windows too).
- [ ] The contributor check (`tests/behavior/macos-app-install.md` with `docs/macos-contributor-check.md`): fresh N, N+1, N+2 builds; add a real zsh/nvm `PATH`, logout while running, and a quit during boot.
- [ ] **Squawk 0261**: the macOS splash card shows blank for about 1.5 s.
- [ ] **Squawk 0262**: document the desktop test-patch rule and the pywebview/PyObjC upgrade checklist (Recommendation 5).
- [ ] Squawk 0260 (the model catalog never refreshes): open; it affects every platform.
- [x] Housekeeping: `$HOME/the-one-m32-evidence/A-recheck` (Flight 1's evidence, 48 files, 44 root-owned) was deleted through a throwaway `m32-cleanup-recheck` container, on the operator's decision ("Delete it").
