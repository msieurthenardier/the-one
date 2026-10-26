# Mission Debrief: GleepGlorp AI installs like an app on Windows, macOS and Linux

**Date**: 2026-10-26
**Mission**: [GleepGlorp AI installs like an app on Windows, macOS and Linux](mission.md)
**Status**: completed
**Duration**: 2026-10-23 (planning) - 2026-10-26 (`v0.12.1` released, Flight 4 completed)
**Flights Completed**: 4 of 4
**Plugin version**: mission-control 1.2.2 for planning and execution of all four flights; 1.2.3 for the Flight 4 debrief and this one

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| Linux install, no setup | met | Flight 2. The AppImage and `.deb` install on stock Ubuntu 26.04 and Debian 13 with no terminal, and open in their own window. The `linux-package-install` behavior test passed 44/44 across all four variants. One known limit, accepted by the operator: Ubuntu's App Center cannot upgrade or remove a local `.deb`, so on Ubuntu the guide gives the `apt` commands and recommends the AppImage first. |
| macOS install, without an Apple developer account | **partly met, carried** | Flights 3 and 4. The ad-hoc signed `.dmg` (macOS 14+, Apple Silicon) is built, installed by drag, launched and quit on a hosted runner: two lifecycle runs went 13/13, and so did the run after the `BootPolicy` refactor. It is published in `v0.12.0` and `v0.12.1`. No contributor has run the real-Mac check yet, so Gatekeeper's Open Anyway flow and a physical Dock click are unconfirmed. The mission closes with this carried (operator, 2026-10-26: "Partly met, carried"). It is tracked by squawk 0261 and `docs/macos-contributor-check.md`. |
| The frozen runtime works in every build | met | Strict `doctor` passes inside every installed build: Linux on stock and bare images, macOS on the build machine (a failed seam fails the build), and Windows on Concourse and the hosted lifecycle (L1). The Command Line Tools `python3` stub is never run, and a Finder launch gets the login shell's `PATH`. |
| The window behaves like a native app on each platform | met (macOS real-hardware half carried) | Linux, with and without a tray: Flight 2, a real-GTK smoke test and the VM walk. Windows: hosted rows L1-L11, plus the operator's field checks (tray, second-launch focus, geometry, tint). macOS: Dock close and reopen, second-launch focus, geometry and four quit paths with a drain, all on the runner. A real Dock click, the Dock menu's Quit and logout are for the contributor. |
| Upgrades keep the user's data | met | Linux: the VMs' upgrades, with a takeover that waits for the old pid. macOS: N to N+1, and moving the app to the Trash keeps the data. Replacing the app while it runs crashes the old copy, so the guide says to quit first. Windows: hosted v0.11.8 → N → N+1 and uninstall, plus the operator's own install upgraded twice (v0.11.8 → 0.12.0 → 0.12.1). The v0.12.0 wizard froze during an interactive upgrade; v0.12.1 fixed it the same day. |
| Windows does not regress | met | The windowed launcher, CLI, `doctor`, close-to-tray, single-instance focus and the Windows 11 tint all pass on the hosted run and in the operator's field checks. The per-push Concourse build was proven by `fly execute` three times. The one field defect (the frozen v0.12.0 wizard) shipped and was patched in v0.12.1. |
| One packaging source of truth, built within the CI budget | met | `packaging/product.toml` → `render.py` / `stage.py` feeds the Inno `.iss`, the Info.plist, the `.desktop` file and AppStream. The version lives only in `the_one/__init__.py`, and `pyproject.toml` reads it dynamically. No per-push hosted build was added. Hosted macOS used 2 + 5 + 4 dispatches across Flights 1, 3 and 4. |
| A release ships all three | met | `release.yml`: audit → version gate → three platform builds → `publish` (draft, then public). `v0.12.0` (run `40269216641`) and `v0.12.1` (run `40328839364`) each published four packages plus `SHA256SUMS`, verified, in about 9 minutes. |
| Install guides for every platform | met | `docs/linux-install.md`, `docs/macos-install.md` and `docs/windows-install.md` (upgrade, uninstall while running, the setup log), plus README "Install" listing the four assets. The WebKitGTK `apt` step stays for source installs only. Three docs still describe the retired 90 s quit poll (squawk 0266). |
| Existing gates pass | met | At the Flight 4 debrief: unit 7604 passed and 15 skipped (netns), 323 s; browser `PARALLEL_RESULT rc=0 total=1461s lanes=13`, nothing over budget; ruff clean. Nothing under `the_one/` imports `packaging/`. |

### Overall Outcome
**Yes, with one carried confirmation.** Someone on Linux or Windows can download GleepGlorp AI from the release page today, install it the way their system expects, and open it in its own window. A Mac user can do the same as far as a hosted runner can prove. One tag publishes all four packages behind the dependency audit.

The outcome stayed the right goal to the end. The one charter change was operator-made (2026-10-25): a release was allowed while Mission 31 was active, after a green dry run. That amendment is what let the field check happen inside the mission. Without it, the frozen wizard would have reached the first release after Mission 31 instead.

**Value delivered:**
- **Linux users** no longer compile PyGObject or run `apt` by hand.
- **The operator** builds every platform from one recipe and bumps the version with one edit.
- **macOS contributors** have a downloadable `.dmg` and a written check.
- **Two public releases** shipped inside four days of mission time.

The operator's biggest surprise was "macOS without a Mac": how much a hosted runner could prove (a GUI session, Accessibility, Apple events, 13/13 lifecycle) with no hardware in the loop.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1. Choose the packaging toolchain | completed | **PyInstaller on every platform, Inno kept on Windows**, decided from measured evidence against strict gates. Briefcase needed two app patches, one `.deb` per distro, and an MSI that would coexist with Inno instead of replacing it; its AppImage did not build. Three of six hosted jobs were lost to first-run harness code. |
| 2. Linux packages | completed | **AppImage and `.deb` from one pinned container and `product.toml`**, plus a host-first library fallback. Two GTK lifecycle traps were found at design review and fixed. The flight added a no-tray hide, `the-one quit`, the takeover, and a QEMU fresh-VM apparatus (44/44). One divert: App Center cannot manage a local `.deb`. The first hosted dispatch was green. |
| 3. macOS app | completed | **`shell.py` split first**, then Dock mode in `macos_dock.py`, with a drain on every quit. The frozen runtime is safe on a stock Mac. An ad-hoc signed `.dmg` passed lifecycle 13/13 on the runner, and the remote evidence HAT worked. One dispatch was lost to a probe that passed on its own fallback. |
| 4. Windows on shared metadata, and one release | completed | Windows moved to `product.toml`, `stage.py` and `build.ps1`, with a graceful quit on upgrade. One `BootPolicy` replaced 21 platform branches. The version now has one source. `release.yml` shipped, then `v0.12.0` and the `v0.12.1` wizard fix. The dry run found two Windows defects before publication. |

### Flight Patterns
- **The smooth flights had a design review that read the real toolkit's source.**
  - Flight 2: pywebview's GTK backend, pystray's `__init__`, the autoinstall schema.
  - Flight 3: pywebview's Cocoa run loop, AppKit's two quit paths.
  - Flight 4: the shipped `AppId={{…}}` braces.
  - Each review was cheap and caught what a hosted run would otherwise have found at the price of a slice of its budget.
- **Every flight lost hosted runs to the apparatus, never to the product decision.**
  - Flight 1: three jobs to first-run script bugs.
  - Flight 3: one, to a probe whose selftest passed on its fallback.
  - Flight 4: two probe runs to bookkeeping, one to a 401 from a credential's redacted repr, one to a stale-head dispatch.
  - Rehearsal by execution (shims on Linux, `-SelfTest` in a pwsh container) was adopted after Flight 1. It turned Flight 2 into one green dispatch, and it cut the losses in Flights 3 and 4.
- **Each flight's verification missed exactly one layer that only a real user or real OS exercises:**
  - Flight 2: App Center's upgrade and remove;
  - Flight 3: the delegate probe never really ran;
  - Flight 4: an interactive, prompting install.
  - The act/observe premise audit was done well every time. The missing question was always a third one (see the Methodology Feedback section, observation 3).
- **Debt was paid forward, not carried.** Flight 2's top recommendation (split `shell.py`) became Flight 3's first leg. Flight 3's (a per-platform boot policy) became Flight 4's. Both refactors changed no behaviour and kept every existing test green.

## What Went Well
- **Evidence-first decisions.**
  - Flight 1 compared the two toolchains against strict, independent gates (one host GTK stack, a real interpreter, an unchanged data dir). The operator then decided in one message.
  - The release was dry-run before any tag, and that dry run found two Windows-only defects about 13 minutes before anything was public.
- **Refactor before extend.** The splits came before the new platforms: `shell.py` into `takeover.py`, `window_control.py` and `session_state.py` before macOS, and `BootPolicy` before Windows. The Architect: the shell "stopped scattering `if sys.platform`", and `shell.py` and `window_control.py` now have none.
- **One metadata source and one version source.**
  - A rename or bump is one edit, rendered into four formats and pinned by tests.
  - The strict `X.Y.Z[.devN]` grammar in `render.py` caught drift on every platform.
- **Packaging stayed outside the app.** `packaging/` is never imported by `the_one/`. The frozen seam stayed one implementation in `platform/env.py` across three freezer layouts.
- **Apparatus that showed real desktops.** The QEMU VMs through WSLg (Flight 2) and the runner's screenshots on a private review page (Flight 3) let the operator judge look-and-feel on platforms they don't run. Both walks found things a green behavior test had marked "shown".
- **The tag path was unit-tested before it ever ran.** Both real tags published on the first try.
- **The field defect turned around within the day.** The operator reported the frozen wizard in the morning. By the end of the day there was a fix, a new interactive row (L11), a compile, one hosted run, a PR, a tag and the operator's re-upgrade. The operator: "a patch was fine".
- **The standing autonomy mode.** Overnight delegation, with every Flight Director call logged and aligned afterwards, held for the whole mission. No logged call was reversed, and the operator rated the level "about right".
- **Concurrency with Mission 31 never collided in code.** The shared files stayed additive, and `main` was merged at checkpoints, never under running Developers.

## What Could Be Improved
- **Shared-host gate contention was the main slowdown** (operator, Flight 4: "Waiting on gates").
  - Mission 31's lanes kept the host busy: Developers waited up to 45 minutes, gates ran at `--parallel 2`, and one leg briefly ran four lanes host-wide.
  - The three-lane host policy was enforced by crew counting other sessions' processes.
  - Asked what they would change, the operator answered "nothing major". So this is a cost to schedule for, not a reason to stop overlapping missions.
- **Silent test paths reached a public release.**
  - Every hosted Windows row ran the installer silently, so the wizard's message loop was never exercised. `v0.12.0` froze on the first interactive upgrade.
  - The planned two-step field upgrade would have caught it one release earlier. The operator's one-step "yolo" was their accepted call.
  - Flight 4 Recommendation 5 (upgrade from a prerelease before the final tag) closes the gap.
- **The hosted budgets ran over every time.** Flight 3 used 5 of 5 dispatches after the operator raised the cap, and Flight 4 used 6 Windows lifecycle runs against a cap of 4. A new harness's first dispatches and each patch release were never budgeted.
- **The lifecycle harnesses were written three times.** About 3,200 lines in two languages implement the same steps (install N, close and reopen, focus, three quit paths, upgrade, remove):
  - `packaging/windows/lifecycle.ps1` + `lib.ps1`, about 1,565 lines;
  - `packaging/macos/lifecycle.sh` + `lib.sh`, about 900 lines;
  - Linux `vm/` + `checks/`.

  Consolidating them was deferred twice (Flight 3 DD8, Flight 4 A2).
- **Leg records drifted from reality.**
  - Leg 5's acceptance boxes were ticked against criteria the run did not meet as written.
  - Leg 6 grew into a second, smaller flight (a patch release).
  - Verification legs were re-run beside already-landed legs.

  The log explained each one, but the artifacts misled a reader.
- **Flight Director errors on outward steps.** Twice, a `gh workflow run` was chained after a failed commit and dispatched on a stale head, costing one budgeted run. The rule now adopted, "dispatch runs as its own command, after the push is verified", lives in the flight log until squawk 0268 puts it in the crew file.

## Lessons Learned
**Technical**
1. **A silent installer test proves the install, not the installer.** Any wait inside Inno `[Code]` must pump messages, and only an interactive run shows whether it does. Every installer change gets an L11-style row from its first leg.
2. **The tool's source is the specification.** Read the third-party tool's source or schema at the pinned version before designing on it. This held for Briefcase, pywebview's GTK and Cocoa backends, pystray, subiquity, `appstreamcli` and Inno's `AppId`. It became the mission's default design-review method.
3. **A lifecycle change needs a test on the real toolkit.** Fakes missed both GTK traps and both AppKit quit paths. Shape for platform code the operator can't run: pure decisions, a thin native layer, and a source canary (`macos_dock` plus the `ast` canary over pywebview's `cocoa.py`).
4. **The bundle sets the minimum OS, not the wheel tags.** `LC_BUILD_VERSION` moved `min_os` from 11.0 to 14.0.
5. **Host-first library preloading through `ctypes` with `RTLD_GLOBAL`, never `LD_LIBRARY_PATH`.** This keeps a bundled fallback out of WebKit's helper processes. PyInstaller's stock gi hooks silently undo environment-variable fixes (squawk 0255 guards this).
6. **A credential's string form is its redacted repr.** `f"Bearer {get_credential()}"` sends a 401. A `bearer()` method would remove the class of bug.

**Process**
1. **Rehearse hosted scripts by executing them, not only parsing them:** shims on Linux, `-SelfTest` in a pwsh container, `shellcheck` with `set -u`, and an AST name-collision check. This saved the most hosted minutes of anything in the mission.
2. **Every premise probe needs a positive control and a fail-loud check that the intended path ran.** A suspiciously fast green gets audited row by row before it counts.
3. **Probe "the OS manages it" premises end to end in the first leg that can reach them:** install, upgrade and remove; launch, quit and replace.
4. **Classify a visual finding from the recorded state before narrating it to the operator.** The Flight 3 P1 splash was misdescribed at first.
5. **A dry run of the whole release is cheap compared with what it finds.**
6. **A visual walk is worth it even after a green behavior test.** The Validator judged a truncated notice "shown".

**Domain**
- **Ubuntu 26.04's App Center cannot upgrade or remove a local `.deb`.** "Stock desktop" means the installer's own default (`ubuntu-desktop-minimal`).
- **macOS 15 removed right-click Open for unsigned apps.** Approval goes through Privacy & Security, Open Anyway.
- **Replacing a running macOS `.app` crashes the old copy.**
- **The Windows uninstall key ends in `}}_is1`.** The `{{` in `AppId` is literal, and "correcting" it would orphan every existing install.

**Reusable patterns** (the Architect recommends naming these in `the_one/agents.md`):
- **Workflow stub first.** A dispatch-only workflow lands on `main` first, because GitHub only dispatches workflows on the default branch. The real workflow then ships from the flight branch.
- **A packaging gate per platform**, wired to a unit test. On Linux and macOS this is `audit.py`, `checks.sh` or `gates.sh`; on Windows it is `doctor` plus the lifecycle smoke.
- **Product metadata rendered from one TOML**, with a strict version grammar.
- **A policy object instead of platform branches** (`BootPolicy`), with an AST guard.
- **A checkpoint per hosted dispatch**: review, commit and push before every dispatch.

**Documentation**
- **`CLAUDE.md` and `the_one/agents.md`** already carry sections for Linux, macOS, Windows and release (added additively during the Mission 31 overlap). The gaps:
  - the named patterns above;
  - a rule that a new `BootPolicy` flag is decided for all three platforms;
  - the stale quit-poll text (squawk 0266).
- **README** is current.

## Methodology Feedback
Each finding below is triaged by destination. These restate observations already recorded in the four flight debriefs, so a later `/mission-control:service-report` sweep should count each occurrence once. The source flights are named on every finding. All four flights executed on mission-control 1.2.2.

### Methodology observations
These reproduce from the methodology alone, and each cost something observable.

1. **`agentic-workflow` Phase 2d: deferred review and commit do not fit hosted or VM runs.**
   - **What the methodology did:** it defers review and commit to after the last autonomous leg.
   - **What happened:** hosted and VM legs build from the pushed branch. Every flight therefore ran a review-commit-push checkpoint before each dispatch: three checkpoints in Flight 1, three in Flight 2, five in Flight 3 and about eleven in Flight 4.
   - **Expected:** a named "checkpoint per outward dispatch" mode.
   - **Cost:** the Flight Director designed and logged a deviation every flight, and twice the improvised sequencing went wrong (the stale-head dispatches, Flight 4).
   - **Recurrence: 4 of 4 flights.** Sources: F1 obs 1, F2 deviation table, F3 obs 2, F4 obs 2.
2. **`agentic-workflow` Phase 2a / `flight` Leg Identification: multi-session legs have no named shape.**
   - **What the methodology offers:** only "split into new legs" or "abort and re-create".
   - **What happened:** legs too large for one Developer session ran as in-flight splits (Flight 1, two legs) or as phases A/B/C under one leg (Flight 2 legs 4-5, Flight 3 legs 1, 4 and 6, Flight 4 legs 2-4).
   - **Cost:** two leg re-authorings mid-flight in Flight 1, and improvised phase wording in a dozen spawn prompts.
   - **Recurrence: 4 of 4 flights.** Sources: F1 obs 4, F2 obs 1, F3 "What Could Be Improved", F4 header.
3. **`flight` Phase 4: the premise audit has two axes but needs a third.** The act/observe audit was done well in every flight, yet each flight lost something to a third question it never asked:
   - **Flight 2:** an Adaptation Criterion's premise was probed only partly in the planned leg. Cost: leg 6 grew in place, and the divert came late.
   - **Flight 3:** "will a non-answer read as a failure?" Cost: one hosted dispatch and an added leg.
   - **Flight 4:** "which path a real user takes is never exercised?" Cost: a public release with a frozen wizard, and a patch release.

   **Expected:** the audit asks whether the apparatus can *act*, whether it can *observe*, and whether a premise that was never exercised could read as a pass. That last question covers the user path the apparatus cannot represent.
   **Recurrence: 3 of 4 flights.** Sources: F2 obs 4, F3 obs 4, F4 obs 6. This cost the most of any finding in the mission.
4. **`agentic-workflow` Phase 2a: the leg lifecycle has no light path for pause, re-run or amend.**
   - **What the methodology offers:** legs are immutable once in flight, and "abort and create a new one" is the only tool.
   - **What happened:**
     - **Flight 1:** a leg waiting on a remote run had no protocol state between "prepared" and "landed".
     - **Flight 3:** a verification leg had to be re-run beside an already-landed leg (`03b`).
     - **Flight 4:** two acceptance criteria stopped matching reality mid-leg and were ticked anyway. In the same flight, an interactive leg absorbed a patch release.
   - **Cost:** improvised artifacts every time. In Flight 4 the record was misleading until the debrief Developer found it.
   - **Recurrence: 3 of 4 flights.** Sources: F1 obs 2, F3 obs 1, F4 obs 3 and 4.
5. **Crew hand-backs that claim pending "background work".**
   - **What happened:** Developers kept reporting, or re-reporting, after they had finished, with nothing running.
   - **Cost:** the Flight Director checked or stopped them four times (TaskStop three times), with the risk of stopping a Developer that really was waiting.
   - **Recurrence: 3 of 4 flights.** Sources: F2 obs 7, F3 obs 3, F4 obs 1.
   - Flight 2 judged the root cause to be the harness rather than the plugin. It is recorded here so the sweep can decide.
6. **`flight-debrief` Phase 2: "run the full test suite" has no instruction for a busy shared host.**
   - **What happened:** the debrief Developer could not run, or had to wait, because another mission's lanes were live. In Flight 3 the Flight Director ran the metrics itself.
   - **Cost:** wall time, and once a substitute runner.
   - **Recurrence: 2 of 4 flights.** Sources: F3 obs 7, F4 Test Metrics.
   - The wider shared-host scheduling between concurrent missions is a local lesson (below), not a methodology finding.

### Local fixes
These change this project's own crew files.
- **Outward steps run alone, after their precondition is verified** (F4 obs 5). Squawk 0268 adds this to `.flightops/agent-crews/leg-execution.md`.
- **Crew leave no processes or files outside the repo, and record and stop the PIDs they start** (F2 obs 6). This is already in this project's working rules (squawk 0160, the "no root-owned files" constraint). It should be written into the leg-execution crew prompts too, alongside squawk 0268.
- **Design reviews read the third-party tool's source at the pinned version** (F1 obs 5, positive). This came from the Flight Director's spawn prompts. Add it to this project's "Review Leg Design" prompt.

### Local lessons
These are real findings, but they did not cost anything observable, or they came from this project's own choices.
- **Several Developers in one worktree** on disjoint, named file sets worked every time (F1 obs 6, F2 obs 2, F3). There was no cost; it rests on prompt wording.
- **Concurrent missions on one host** cost wall time on every gate in Flights 3 and 4. This is the operator's chosen trade-off, and the three-lane host policy in `CLAUDE.md` is the project's control.
- **Delegated autonomy** (operator away, the Flight Director decides and logs) became the standing mode in Flight 1 and held through Flight 4 (F1 obs 8).
- **HAT shapes vary.** An evidence HAT (a review page of runner output) works for hardware the operator does not have (F3 obs 5). A one-message decision brief beats a five-step guided walk for a decision gate (F1 obs 7).
- **A patch-release path** inside a release-bearing flight came up once (F4 obs 4). Watch for recurrence.
- **External platform prerequisites**, such as `workflow_dispatch` needing the workflow on the default branch (F1 obs 3), were caught at design review. They are now the "workflow stub first" pattern.
- **Positive:**
  - live-mode behavior tests with grouped checkpoints (F2 obs 5);
  - the debrief test-metrics instruction producing like-for-like comparisons (F2 obs 8).

## Action Items
**For the maintenance mission** (the operator plans one after Mission 31):
- [ ] **The contributors' real-Mac check** (`docs/macos-contributor-check.md`, `tests/behavior/macos-app-install.md`). It decides the carried macOS criterion and squawk 0261. N/N+1 can be `v0.12.0` → `v0.12.1`. The dry run's `0.12.0.dev1` `.dmg` artifact expires around 2026-11-09.
- [ ] **User-visible squawks first** (Architect): 0253 (the AppImage's blank first launch), 0261 (the macOS splash), 0264 (a tray Quit before the window is published), 0254 (the no-WebKit notice length).
- [ ] **Servicing squawks:**
  - 0265 (actions on Node 20, before GitHub's cutoff);
  - 0255 (the PyInstaller stock-hook canary; run it before any PyInstaller bump);
  - 0256 (the Linux behavior-test spec);
  - 0259 (the chats lane budget; 86% at the last reading);
  - 0266 and 0267 (the stale quit-poll docs and log prefixes);
  - 0268 (the crew-file dispatch rule).
- [ ] **Flight-sized: one declarative lifecycle scenario spec with thin per-OS drivers.** It replaces about 3,200 lines across the PowerShell, bash and Linux VM harnesses (Architect recommendation 1; deferred twice).
- [ ] **Flight-sized: one owner for desktop teardown.** A small lifecycle object for splash and window teardown that every quit path calls, with squawk 0264 folded in, and a quit tested at each boot phase. Then split `BootPolicy` into a base policy plus a macOS Dock strategy (about 20 flags, about 12 of them macOS-only), and set a size cap or split plan for `shell.py` (1144 lines) (Flight 4 recommendation 2, Architect recommendation 3).
- [ ] **Shared workflow steps** (Python setup, the closure export, the summary, the artifact upload) moved into a composite action or a reusable workflow, with the Python version read from `product.toml`. It is hard-coded 12 times across the workflows, plus the Linux Dockerfile.
- [ ] **Retire the probe trees:** `packaging/windows/probe/` and `packaging/macos/probe/` (10 tracked files, about 2,500 lines), plus the macOS workflow's `mode=probe` branch.
- [ ] **A `bearer()` method on `LocalApiCredential`.** It is credential-adjacent, so it needs a Reviewer on Sonnet.
- [ ] **Document the named patterns in `the_one/agents.md`:** the workflow stub first, a gate per platform, and a `BootPolicy` flag decided for all three platforms.
- [ ] **Re-measure the browser-lane budgets** from a quiet-host `--parallel 3` run (squawk 0259's rule).
- [ ] **Issue #316:** dynamic model context windows; the seed floor is a stopgap.

**Process:**
- [ ] **Any installer or updater change ships with an interactive row from its first leg** (L11 is the template).
- [ ] **Budget hosted runs** as 2-3 for a new harness's first dispatches, plus one per platform for each patch release, with the dry run counted separately.
- [ ] **Before a release-bearing flight's final tag, the operator upgrades their own install from the dry run's prerelease, interactively.** Consider a short behavior-test spec for this field upgrade (Windows interactive upgrade: data intact, tray, focus, tint) so it runs the same way each release. Author it during the next release-bearing flight's planning.
- [ ] **Premise audits ask the third question:** can a premise that was never exercised read as a pass, and which real-user path does the apparatus never take?
