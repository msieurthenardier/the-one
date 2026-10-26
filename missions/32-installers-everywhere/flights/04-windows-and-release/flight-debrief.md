# Flight Debrief: Windows on shared metadata, and one release

**Date**: 2026-10-26
**Flight**: [Windows on shared metadata, and one release](flight.md)
**Status**: landed (marked `completed` at this debrief)
**Duration**: 2026-10-25 (planning) - 2026-10-26 (landed)
**Legs Completed**: 6 of 6 (legs 2-4 in two phases each; leg 6 absorbed the `v0.12.1` patch release)
**Plugin version**: mission-control 1.2.2 during planning and execution; 1.2.3 installed for this debrief

## Outcome Assessment

### Objectives Achieved
**Windows now builds the same way as Linux and macOS.**
- **The metadata:** the installer and the frozen app read their names, version, GUID and file names from `packaging/product.toml` through `render.py`.
- **The freeze:** it runs from `stage.py`'s staged copy.
- **The recipe:** one script, `packaging/windows/build.ps1`, is used both by the Concourse per-push task and by GitHub.

**The installer quits a running app gracefully** on upgrade and on uninstall, keeping a forced close as the fallback.

**One `BootPolicy` replaces every platform branch in the desktop shell.** All 21 `sys.platform` reads in `shell.py` and `window_control.py` were replaced by four frozen policies, with an AST guard. No existing desktop test changed.

**The version lives in one place,** `the_one/__init__.py`, and `pyproject.toml` reads it dynamically.

**One `release.yml` replaced the Windows-only tag workflow:**
- the audit runs first, then a version gate;
- the three platform workflows then build;
- `publish` creates a draft, uploads the four packages and `SHA256SUMS`, then publishes.

**Two releases shipped on 2026-10-26:**
- **`v0.12.0`** (run `40269216641`), the first release with all three platforms.
- **`v0.12.1`** (run `40328839364`). It fixes the one field defect: in v0.12.0 the Windows wizard froze during an interactive upgrade.

**The operator's own Windows install was upgraded twice:**
- v0.11.8 → 0.12.0: the install worked, but the wizard froze.
- 0.12.0 → 0.12.1: "worked fine".
- The field checks were "all fine": startup logo, data intact, tray, second-launch focus and title-bar tint.

**Squawks:**
- Completed: 0260 (the model catalog uses the bundled seed as a floor, with the seed refreshed by 17 models), 0262 (the dependency-bump procedure) and 0263 (the Windows splash was over WebView2's 2 MB limit).
- Carried: 0261 (macOS blank splash) is deferred until the contributors' real-Mac report.

### Mission Criteria Advanced
| Criterion | This flight's contribution | State |
|---|---|---|
| One packaging source of truth, within the CI budget | Windows on `product.toml`, `stage.py` and `build.ps1`; a one-edit version bump; the Concourse build proven by `fly execute` (three times) | Met |
| A release ships all three | `release.yml`: a dry run first, then two real releases with four packages plus `SHA256SUMS`, verified | Met |
| Windows does not regress | Hosted lifecycle L1-L11 (doctor, window, tray hide, focus, geometry, quits, upgrade, uninstall, interactive wizard), plus the operator's field checks | Met |
| Upgrades keep the user's data (Windows) | The marker agent and file survive v0.11.8 → N → N+1 and the uninstall; the operator's data survived two upgrades | Met |
| The window behaves like a native app | Windows hosted run; macOS lifecycle 13/13 after the `BootPolicy` refactor; Linux GTK smoke | Met (macOS real-Mac half carried) |
| macOS install without an Apple developer account | Contributor checklist extended (steps 11-14); no real-Mac report yet | **Carried** (operator: "Land now, carry it") |
| Install guides for every platform | `docs/windows-install.md` covers the upgrade, uninstalling while the app runs and the setup log; README "Install" lists the four assets and the three guides | Met |
| Existing gates pass | Unit 7604 passed; browser 13 lanes `rc=0`; ruff clean (see Test Metrics) | Met |

## What Went Well
- **The dry run (DD8) was the flight's most valuable decision.** Before anything was published, it found two Windows-only defects that no unit test could reach:
  - **A quit while the page was still loading hung the app.** The splash was never destroyed, so `webview.start()` never returned and the server never drained. The bug predates Mission 32.
  - **The splash never rendered on Windows.** Its HTML was 2.3 MB, over WebView2's `NavigateToString` limit (squawk 0263).
- **The leg 1 probe found the installer's real identity.** The shipped `AppId={{…}}` line makes the uninstall key end in `}}_is1`, with two closing braces. The rendered `.iss` keeps that line literal, and a test pins it. "Correcting" it would have silently orphaned every existing install.
- **`BootPolicy` was refactored before Windows work started** (the Flight 3 debrief's Recommendation 1).
  - The 21-row mapping table was written before any code moved, which made the refactor reviewable. The policy is pure data, as leg 2's design review required.
  - Every existing desktop test passed unchanged, and macOS came back 13/13 on its first run.
  - Both later Windows fixes (`_mark_hidden` and the splash teardown on quit) were added without a single `sys.platform` read.
- **Local rehearsal of the PowerShell harness made hosted runs count.** After two probe runs were lost to script bookkeeping, the scripts got `-SelfTest` in a disposable pwsh container, `ParseFile`, an AST name-collision check with a mutation proof, and an undefined-command check. Later dispatches failed only on real findings.
- **`fly execute` on the operator's Concourse Windows worker** cost nothing per run. It caught a task copy-step defect and proved the `.iss` compile three times, including the v0.12.1 `[Code]` before its hosted run.
- **The tag path was pinned by tests before it ever ran.** `release_check.py`, `release_assets.py`, the YAML `inputs.*` fallbacks and the draft detection were all unit-tested. Both real tags then published on the first try, about 9 minutes each.
- **The field defect was fixed the same morning.** The operator reported the frozen wizard. The fix, a new interactive-wizard row (L11), a local compile, one hosted run, the PR, the tag and the operator's re-upgrade all happened within the day. The operator's view: "a patch was fine".
- **Squawk 0260's premise was corrected rather than forced.** 25 of 77 seed pairs had gone upstream, not 1, and the refresh script did not keep a floor. The operator chose "seed as floor now", and issue #316 tracks dynamic context windows. The floor was verified live on the dry run's macOS log.

## What Could Be Improved

### Process
- **Every hosted test ran the installer silently, so the first interactive upgrade froze.**
  - DD2's quit step ran `ExecAsOriginalUser(..., ewNoWait)` and then a 90 s `tasklist`/`Sleep` loop in `PrepareToInstall`. That loop blocks the wizard's UI thread.
  - The probe row (W4) and lifecycle rows L7 and L9 checked the quit order and the drain, never whether the wizard stayed responsive.
  - DD12's verification table had no interactive row, and the runner (elevated, `ConsentPromptBehaviorAdmin=0`) never shows UAC.
  - The operator considered a patch release an acceptable cost. Even so, from now on any installer change should include an L11-style interactive row from the start (Recommendation 1).
- **The hosted-run budgets were overrun, mostly on first-use harness defects and dry-run findings.**
  - **Windows: 6 lifecycle runs against a cap of 4**, the extra two approved by the operator. One dispatch was lost to the smoke 401, and one went out on a stale commit. The other four were the green leg 3 run, the dry run, the dry-run fix and v0.12.1.
  - **Windows probe dispatches: 3.** Two were lost to probe-script defects.
  - **macOS: 4 of 4.** The "spare that stays spare" went to the patch release.
  - A new harness's first dispatches should be budgeted at 2-3 runs, plus one per patch release (Recommendation 4).
- **Twice, a dispatch went out on a stale commit** (Flight Director error). A `gh workflow run` was chained after a commit that failed:
  - `40260891145` was cancelled at 24 s and still counted against the Windows budget.
  - `40265725036` was cancelled before any platform job started.
  - The rule adopted mid-flight, "a dispatch runs as its own command, after the push is verified", lives only in the flight log (Recommendation 3).
- **Leg 5's acceptance boxes were ticked against criteria the run did not meet as written:**
  - AC1 says "green on every job except `publish`", but the dry run's Windows job was red until the fix run.
  - AC6 says Windows runs "end at 4 of 4", but they ended at 5.
  - The log explains both. The boxes should still have been amended before they were ticked.
- **The gates waited on the shared host.** The operator named this the flight's main slowdown. Mission 31's lanes kept the host busy ("the machine is never quiet"):
  - one Developer ran its gate beside another session's lanes after a 45-minute wait;
  - the leg-5 browser gate ran with four lanes host-wide for a while;
  - this debrief's run waited 5 minutes.
- **Leg 6 turned into a second, smaller flight.** It went from an interactive checklist to a patch fix with its own design, a new test row, a compile, a hosted run, a PR and a tag. The flight described patches only generically.

### Technical
- **The Windows freeze is fixed, but its root cause was never proven.** The fix replaced the loop with a wait that pumps messages, one check, and `KillRunning`. L11 and the operator's report show the fix works, but the root cause stays a hypothesis: the review noted the Finish-page freeze was never proven to share the stall's cause.
- **The installer log prefixes no longer describe what happens.** v0.12.1 has no poll, yet its log still writes `quit-poll: present (iteration 0)`. The prefixes were kept so L7 and L9 parse unchanged; rename them together with the parsers.
- **The quit and splash teardown has no single owner.**
  - `DesktopSession._destroy_splash` is a late-bound attribute that `run()` sets and `_on_quit` reads.
  - That split ownership of teardown, across two code paths, is how the quit-during-boot bug arose.
  - Squawk 0264 (a tray Quit between the tray start and the window publish) is the same class.
  - `run()` is still about 500 lines of nested closures.
- **`BootPolicy` has a scaling cost.** It has about 20 boolean flags, roughly 12 of them macOS-only and named after macOS behaviour. That is correct and guarded, but a new platform means writing out every field. If more flags arrive, group them by phase (tray, splash, quit, show).
- **There are now three lifecycle harnesses:** about 1,500 lines of PowerShell (`lib.ps1`, `lifecycle.ps1`), the macOS `lifecycle.sh`/`lib.sh`, and the Linux gates. They implement the same row rules three ways: `FAIL not-run` seeding, anchored `^FAIL`, CR stripping. Merging the shell helpers has been deferred twice (Flight 3 DD8, then this flight's A2). The retired `packaging/windows/probe/` tree (about 1,400 lines) is still in the repo.
- **A credential's string form is its redacted repr.** `f"Bearer {get_credential()}"` cost a hosted run as a silent 401. A `bearer()` method on `LocalApiCredential` would remove the whole class instead of fixing one caller. It is credential-adjacent, so it is a recommendation, not a squawk.
- **Windows `[Code]` and the PowerShell harness cannot run on the Linux host.**
  - The `.iss` is checked only by regex (`tests/test_windows_lifecycle_static.py`).
  - The pwsh self-tests run only in a local container, never in the unit tier.
  - The real checks are `fly execute` (compile) and the hosted run (behaviour).

### Documentation
- `docs/releases/v0.12.0.md` and the v0.12.0 release page carry no note that its Windows installer can freeze interactively and that v0.12.1 supersedes it.
- **Three documents still describe v0.12.0's quit sequence, a poll of up to 90 s:**
  - `the_one/agents.md` "Windows packaging (M32 F4)" ("poll up to 90 s until neither exe is running");
  - `packaging/windows/README.md`'s quit-sequence step 2 ("Poll. Up to 90 s");
  - `docs/windows-install.md` ("waits up to 90 seconds").

  v0.12.1 waits for `quit --wait` itself (the CLI bounds it at about 80 s), checks once, then runs `KillRunning`. The README does describe the L11 row.

## Test Metrics
Run by the debrief Developer on `flight/04-leg6-close` (code identical to `main` `43bbd55`). The host was quiet: they waited 5 minutes for Mission 31's `--parallel 3` to finish (load 1.6), and never ran the unit tier and the browser lanes at the same time.

- **Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`): 7604 passed, 0 failed, 15 skipped (the documented netns count), in 323 s. No flakes.
- **Browser** (all 13 lanes, `--parallel 3`, netns, WebKit required): `PARALLEL_RESULT rc=0 total=1461s lanes=13 failed=-`, about 2909 tests, no failures, no flakes, nothing over budget.
  - Each lane, measured against its budget, in seconds:

    | lane | measured | budget |
    |---|---|---|
    | routing | 512 | 600 |
    | agents | 441 | 540 |
    | chats | 390 | 450 |
    | mcp | 334 | 450 |
    | knowledge | 297 | 420 |
    | providers | 326 | 420 |
    | contracts-controls | 326 | 420 |
    | shared | 314 | 420 |
    | agent-tabs | 296 | 360 |
    | settings | 279 | 360 |
    | settings-tools | 249 | 330 |
    | contracts-overlay | 214 | 270 |
    | library | 160 | 210 |
- **Ruff:** check and format clean (714 files).
- **Compared with earlier numbers:**
  - **Unit tier:**
    - Flight 1: 6783 tests, 341 s.
    - Flight 2: 7100 tests, 339 s.
    - Flight 3: 7404 tests, 364-369 s.
    - Flight 4: 7604 tests, 323-355 s.
    - That is 200 more tests this flight, about 100 of them from Mission 31's merges, with the time flat or down. The leg-5 gate showed 12 skips and this run 15; the difference is netns only.
  - **Browser:**
    - Flight 2: 1411 s with 12 lanes.
    - Flight 3: 1542 s.
    - Leg 5: 1557 s, while Mission 31 started a fourth lane (load about 9.5).
    - Today: 1461 s.
    - Every lane is 5-15% faster than its leg-5 reading. That is host load, not code (squawk 0259's quiet-host rule).
  - **The chats lane,** which Flight 3 flagged as near its budget, is at 390/450 (86%), down from 422.
  - **This flight's tests are all unit-tier,** about 217 of them, chiefly `test_windows_test_copy`, `test_release_check`, `test_release_workflow`, `test_windows_packages_workflow`, `test_windows_build_recipe`, `test_boot_policy`, `test_windows_lifecycle_static` and `test_windows_runtime_seam`. No browser tests were added.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| v0.12.1 patch release inside leg 6 | The v0.12.0 wizard froze during the operator's interactive upgrade | Yes: plan a patch path (fix, compile, one hosted run, tag) as a named option of any release leg |
| L11 interactive-wizard row added | Every earlier row was silent | Yes: required for any installer change |
| L10 quit-during-boot row added | The dry run found the hang; earlier rows quit only after the page loaded | Yes: quit tests cover each boot phase |
| Two-step field upgrade collapsed to one, no backup | Operator's call ("yolo it") | No: the plan stays two-step; it would have found the freeze one release earlier |
| Windows lifecycle runs 6 against a cap of 4 | A smoke 401, a stale-head dispatch, the dry-run fix, the patch | Yes: budget first-use cost and one per patch |
| Probe mode retired in 3a; `windows-installer.yml` broken until leg 4 deleted it | Design review: fewer moving workflows | n/a (held by "no tag before leg 6") |
| 0260 became "seed as floor", not "prune the retired pair" | 25 pairs had gone, not 1; the refresh script kept no floor | Yes: check a squawk's premise with live data before fixing |
| Squawk 0263 fixed in flight | Found by the dry run, a one-asset fix | n/a |
| `_mark_hidden` (Windows tray-hide state) fixed in leg 2, not logged as a squawk | A lifecycle row depended on it | n/a |
| Dispatch as its own command, after the push is verified | Twice a chained command dispatched on a stale head | Yes: a crew-file rule |
| Version bump reviewed by the Flight Director, with no Reviewer spawn | A one-line diff | No |

## Key Learnings
1. **A silent installer test proves the install, not the installer.** The wizard's message loop is part of the product. Anything that waits inside `[Code]` must pump messages, and only an interactive run shows whether it does.
2. **A wait with a time limit can still freeze the UI.** The 90 s limit was correct. The defect was that the wait ran on the wizard's UI thread.
3. **A dry run of the whole release is cheap compared with what it finds.** It produced two product defects and one harness defect, about 13 minutes before anything was published.
4. **A hosted runner proves the order of events and the drain, not what the user sees.** The real UAC prompt, a non-admin account, the Windows 11 tint and the interactive wizard are all field checks. Plan a field step for each one.
5. **Rehearse harness code locally before spending a hosted run.** `-SelfTest`, a parse check and a check that a known bug is caught, all in a disposable container, cost minutes. Each lost hosted run cost a slice of a budget of four.
6. **Port a working probe as it is.** The old `get_credential().encode()` worked, and the rewrite's `f"Bearer {…}"` did not.

## Methodology Observations
Recorded against mission-control 1.2.2 (execution); this debrief ran on 1.2.3.

1. **`agentic-workflow`, crew hand-backs ("background work"), recurring.**
   - **What happened:** the leg 3b and leg 4a Developers each kept sending "waiting on background work" after they had finished, with nothing of theirs running. The Flight Director checked and stopped them with TaskStop.
   - **Recurrence:** Flight 3, observation 3. This flight it happened twice.
   - **Cost:** two checks and two stops, and the risk of stopping a Developer that really was waiting.
   - **Expected:** a hand-back that states nothing is pending.
2. **`agentic-workflow`, Phase 2d (a checkpoint per hosted dispatch), recurring.**
   - **What happened:** hosted runs build from the pushed branch, so the flight committed after review at every phase before a dispatch (1, 2a, 2b, 3a, 3b, the smoke fix, 4a, 4b, the leg 5 fixes, squawk 0263, v0.12.1) instead of once at the end.
   - **Recurrence:** this is the fourth flight in a row (Flights 1-3 recorded the same).
   - **Expected:** a named "checkpoint per outward dispatch" mode.
   - **Cost:** the Flight Director designed the checkpoint plan again.
3. **`agentic-workflow`, Phase 2a (immutable legs versus amended acceptance criteria).**
   - **What happened:** two of leg 5's acceptance criteria (green except `publish`; Windows runs end at 4) stopped matching reality during the leg. The fix run and an operator-approved fifth run changed the plan, and the boxes were ticked with the outcome explained only in the log.
   - **What the skill offers:** for a leg that is already in flight, only "abort and create a new leg", which is heavy for a changed budget number.
   - **Expected:** a light "amend the criterion, record why" step.
   - **Cost:** a misleading record, found by the debrief Developer.
4. **`agentic-workflow`, interactive legs that grow a patch release.**
   - **What happened:** leg 6 (interactive) absorbed a full fix cycle: a design, a Developer, a Reviewer, a compile, a hosted run, a PR and a tag.
   - **What the skill offers:** the fix-vs-feature gate, which covers fixes inside a HAT. It does not cover a defect found in the field after a release, which needs its own release.
   - **Expected:** a named "patch release" path.
   - **Cost:** the Flight Director improvised the shape.
5. **`agentic-workflow`, outward steps chained to local commands.**
   - **What happened:** twice the Flight Director chained `gh workflow run` after a commit that failed, and dispatched on a stale head. One budgeted run was lost.
   - **Expected:** the skill (or the project's leg-execution crew file) says that an outward step runs alone, after its precondition is verified.
   - **Cost:** one hosted Windows run.
6. **`flight`, Phase 4 (the verification layers).**
   - **What happened:** the flight's verification table (DD12) named every layer the runner can drive, but not the user-facing path the runner cannot represent (an interactive, prompting install).
   - **Expected:** the premise audit, besides "can it act" and "can it observe", asks "which path a real user takes is never exercised?".
   - **Cost:** a public release with a frozen wizard, and a patch release.
7. **Shared-host gate contention, recurring.**
   - **What happened:** the skills have no notion of another mission's crew sharing the host's test capacity. Developers waited up to 45 minutes. One gate ran beside another session's lanes, and this debrief's metrics run waited 5 minutes.
   - **Recurrence:** Flight 3, observations 6 and 7. The operator named it the flight's main slowdown.
   - **Cost:** wall time on every gate.

## Recommendations
1. **Every installer or updater change ships with an interactive row from its first leg** (Critical). That means driving the real wizard, probing that it stays responsive (`WM_NULL` with `SMTO_ABORTIFHUNG`), checking that Finish closes it, and keeping the setup log. L11 is the template. Treat a silent-only run as an untested installer.
2. **Give the desktop shell's splash and window teardown one owner** (Important). Make it a small lifecycle object that every quit path calls, instead of a late-bound `_destroy_splash` and closures inside a 500-line `run()`. Fold squawk 0264 in, and test a quit at each boot phase (before the window is published, between publish and load, after load), for both the window and the tray.
3. **Put "an outward dispatch runs as its own command, after the push is verified" in `.flightops/agent-crews/leg-execution.md`** (Important). It is a project rule and cheap (squawk 0268).
4. **Budget hosted runs as first-use cost plus one per patch** (Important). Plan 2-3 runs for a new harness's first dispatches and one per platform for each patch release, and count the dry run separately. Keep using the free Concourse `fly execute` for compiles.
5. **Before a release-bearing flight's final tag, the operator upgrades their own install from a prerelease build** (Minor). Use the dry run's installer and the interactive path, so the field check comes before the public release, not after it.

## Action Items
- [ ] **The contributors' real-Mac check** (`docs/macos-contributor-check.md`, `tests/behavior/macos-app-install.md`). It decides squawk 0261. N could be the dry run's `0.12.0.dev1` `.dmg` (its artifact expires around 2026-11-09), or v0.12.0 with v0.12.1 as N+1. The Mission 32 debrief decides whether the macOS criterion is met or carried.
- [ ] Squawk 0264: a tray Quit between the tray start and the window publish leaves the window shown (Recommendation 2 may absorb it).
- [ ] Squawk 0265: the artifact actions target Node 20. Fix it before GitHub's cutoff.
- [ ] Issue #316: dynamic context windows from the providers' model APIs. The seed floor is a stopgap.
- [ ] Mission 32 debrief or the next flight: Recommendations 1-2 and 4; a `bearer()` method on `LocalApiCredential`; consolidating the three lifecycle harnesses; retiring `packaging/windows/probe/`.
- [ ] Re-measure the browser lane budgets at mission end, from today's quiet-host numbers (every lane is 5-15% under its leg-5 reading).
- [ ] Squawk 0266: three docs still describe the retired 90 s quit poll (the Documentation note above).
- [ ] Squawk 0267: rename the installer's `quit-poll` log prefixes together with the lifecycle parsers.
- [ ] Squawk 0268: the outward-dispatch rule in `.flightops/agent-crews/leg-execution.md` (Recommendation 3).
- Not logged (operator's choice): a note on the v0.12.0 release page that v0.12.1 supersedes its Windows installer.
