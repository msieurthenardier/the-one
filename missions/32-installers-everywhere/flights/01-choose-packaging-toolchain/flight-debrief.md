# Flight Debrief: Choose the packaging toolchain

**Date**: 2026-10-24
**Flight**: [Choose the packaging toolchain](flight.md)
**Status**: completed
**Duration**: 2026-10-23 (planning) - 2026-10-24 (decision)
**Legs Completed**: 7 of 7 (planned as 5; two in-flight splits)
**Plugin version**: mission-control 1.2.2

## Outcome Assessment

### Objectives Achieved
The flight decided Mission 32's packaging toolchain from measured evidence. The operator chose **candidate A: PyInstaller on every platform, with Inno Setup kept on Windows** ("pyinstaller it is."). The AppImage will bundle the AppIndicator and girepository libraries while still using the desktop's own WebKitGTK ("bundle the two libs").

Both candidates were built and measured against the same hard gates:
- strict `doctor` inside the installed bundle;
- a real Python for tool spawns;
- exactly one host GTK/WebKit stack in the running process;
- an unchanged data directory.

Plus soft criteria: upgrade, single-instance, tray, size, build time and upkeep.

The evidence covered:
- fresh Ubuntu 26.04 and Debian 13 containers, both stock-desktop and bare images;
- two hosted macOS jobs;
- two hosted Windows jobs.

PyInstaller's Linux and macOS recipes stay under `packaging/` as prototypes, the starting points for Flights 2 and 3. Briefcase's files were removed (DD8).

The decision rested on four findings:
- A's single `.deb` passes every gate on both distros, with no app patches.
- Briefcase needs two app patches (start-up default and frozen detection), one `.deb` per distro, and a migration on Windows: its MSI coexists with Inno rather than replacing it.
- Briefcase's AppImage does not build.
- On macOS both candidates pass, and A is half the size.

Nothing under `the_one/`, `tests/`, `pyproject.toml` or `uv.lock` changed. The two dispatch-only probe workflows reached `main` through PR #305. Squawk 0250 (filelock CVEs in the release closure) was filed along the way.

### Mission Criteria Advanced
All of this is evidence, not shipped behaviour (DD contributing list):
- **The frozen runtime works in every build.**
  - A passes strict `doctor` in the Linux `.deb` and AppImage (Ubuntu), and in the macOS `.app`. The existing Windows path is proven by Concourse.
  - The frozen seam's PyInstaller assumptions now hold on all three platforms with no change.
- **One packaging source of truth, built within the CI budget.**
  - The decision is made.
  - The version currently lives in three places; the single metadata source is Flight 2's.
  - Hosted cost per release is measured: macOS A at about 1.5 job-minutes, about 15 billed.
- **Linux install, no setup.**
  - The `.deb`'s declared dependencies are proven complete on bare images.
  - The AppImage's two missing host libraries are identified, and the operator chose to bundle them.
- **Windows does not regress / Upgrades keep the user's data.**
  - Windows stays on Inno, so there is no regression risk from a toolchain change.
  - The MSI's coexistence (rather than replacement) is measured.
  - The shared-data checks were not measured, due to a harness defect, and are moot after the decision.

## What Went Well
- **Strict, independent gates decided the comparison cleanly** (design review cycle 1's best catch). Two of them caught results the planned design would have missed:
  - **Gate 3's single-host-stack check** (`/proc/<pid>/maps` of the UI and web processes) caught a dead window: the A AppImage on stock Debian opened none.
  - **Gate 2's independent interpreter check** caught a self-spawn bug: unpatched Briefcase would re-launch itself for every Python spawn, even though its `doctor` interpreter gate passed.
- **Stock-desktop plus bare container baselines** turned guesses into facts:
  - the Ayatana typelib is absent on both stock desktops, and `libgirepository-2.0` on Debian 13;
  - `apt` proves the `.deb`'s declared dependencies complete.
- **The window check through forwarded WSLg worked inside the target containers**, so no window result is directional (the plan treated this as unproven).
- **The live-window check found a real recipe defect that `doctor` cannot see.** `gi.overrides` was not collected: `doctor` passed and the server started, but no window opened. That is the Mission 15 lesson, "the packaged smoke proves spawn behaviour, never the rendered window", now enforced by the gates.
- **Developer design reviews that read the tool's actual source** (Briefcase 0.4.6) corrected four wrong premises before any minute was spent: `allow_subprocesses`, the fixed `.desktop` `Exec`, Debian `Depends` alternatives becoming shell pipes, and `--only-binary` with sdist-only `proxy-tools`.
- **Staged-only patches (DD4)** let Briefcase's cost be measured on all three platforms without touching `the_one/`. The patches disappeared with the candidate.
- **The cost guards held.** Hosted spend for the flight was about 50 billed macOS minutes and about 22 billed Windows minutes, against an approved budget of about 400. The layered caps, the logs-only uploads and the fail-on-missing-summary step all worked.
- **Overnight autonomy, with every call logged in the Flight Director Notes.** The macOS run 2 scope, the Windows retry, the per-user MSI and the merge were all accepted by the operator in the morning ("All stand").

## What Could Be Improved

### Process
- **Every hosted failure in this flight was first-run harness code**, never the candidate. The flight lost three of its six hosted jobs to scripts' own first runs:
  - macOS run 1: `$WORK` was created after the icon step;
  - Windows run 1: PowerShell's case-insensitive `$log` overwrote `$LOG`;
  - Windows run 2 lost three checks: `Use-EnvVars` left variables set to empty strings.

  The Mission 15 debrief predicted "2 to 4 CI-only issues per first freeze". The Linux rehearsals covered pip resolution and syntax (`bash -n`, `actionlint`, a `pwsh` parse), not execution order or variable semantics. A dry run of each hosted script under a shim (as leg 5 later did for `macos-checks.sh`), plus `PSScriptAnalyzer`, would likely have caught all three.
- **The Windows hosted job answered a question the decision no longer needed.** DD7 ran it "if Briefcase survives Linux". Briefcase survived only with two patches, per-distro packages and no AppImage. The result, "the MSI coexists with Inno rather than replacing it", followed from the AppId and upgrade-code model and could have been priced on paper. Its cost was small (about 22 billed minutes plus agent time), but the gate should have been "only if B wins Linux outright".
- **Leg sizing needed two in-flight splits:**
  - `linux-pyinstaller` became build plus gates (too big for one session, per its design review);
  - `macos-probe` became prepare plus run (a human checkpoint: push, PR, dispatch).

  Both splits were right. The second was foreseeable at flight design: any leg that spans a hosted run needs an operator-approved outward step in its middle.
- **The deferred-commit default does not fit hosted runs.** Hosted legs build from the pushed branch, so the Linux legs had to be reviewed, committed and pushed before leg 4. That was recorded as a deviation, and it worked.

### Technical
- **Debt carried forward:**
  - `packaging/spike/` (the measurement harness) should be folded into Flight 2's real build checks or deleted at its end.
  - The host-GTK exclude list depends on the build host's GLib (PyInstaller's gi hooks collected almost nothing on the 24.04 dev host because GLib 2.80 lacks `GIRepository-3.0`), so a hosted runner may collect differently.
  - The version lives in three places.
  - The Linux and macOS spec and build files duplicate their collection logic.
  - The probe workflows (`packaging-probe-*.yml`) must become a real release workflow. The Windows stub's comment on `main` is stale but must stay byte-identical to `main`'s copy until Flight 4.
  - `rthook_host_gtk.py` lists the amd64 typelib path first.
- **Python 3.11 versus 3.12.** In leg 1, a uv-managed CPython 3.11.14 venv failed 21 unit tests (MCP sign-in, connection negotiation, wire shapes and the credential gate: `CancelledError` in `MCPClient._cleanup_after_failed_connect`) that pass on 3.12. This matters on two counts:
  - CI's unit tier runs a `python3.11-bookworm` image, and `pyproject.toml` requires `>=3.11`;
  - **A freezes with Python 3.11**, so the shipped installers would carry whatever this is.

  It is unresolved.
- **Test metrics (unit tier, this debrief, worktree `.venv` CPython 3.12, not under netns):**
  - 6783 passed, 0 failed, 12 skipped (the expected 12 on this host), 2556 deselected.
  - 341 s in pytest (6m03s wall); no flakes.
  - Against Mission 31: F1 6705 passed, 281 s; F2 6717, 300 s; F3 6773, 297 s, all with 14 skips under netns.
  - The pass count growth is `main`'s own, since this flight added no tests.
  - The 12-against-14 skip difference is the netns uid-0 effect, not a regression.
  - The about 15% time rise since F3 is not isolated (single process, host load or disk). The tier has crept since Mission 31 F2 and has never been profiled.
  - The browser gate was not run, since no app code changed.

### Documentation
- **The decision and recipe are documented only** in the flight log and the packaging READMEs. `the_one/agents.md` and `CLAUDE.md` were deliberately not touched (shared with the concurrent Mission 31). Flight 2 should add the packaging section once a recipe ships.
- **The evidence files live outside the repo** (`$HOME/the-one-m32-evidence/`). The Evidence Table and the excerpts in the flight log are the durable record; the raw evidence is not reproducible from git.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Five planned legs became seven (build and gates; prepare and run) | Leg 1 was too big for one session; the macOS leg spans an operator-approved push, PR and dispatch | Yes: plan a separate leg on each side of any hosted run that needs an outward-facing human step |
| Review, commit and push after leg 3 instead of once at flight end | Hosted runs build from the pushed branch | Yes, for any flight with hosted runs |
| A `.github/`-only PR to `main` (#305) to make the workflows dispatchable | GitHub offers manual runs only for workflows on the default branch | Yes: plan it at flight design whenever a new hosted workflow is introduced |
| PR #305 merged with `pip-audit` red | Pre-existing filelock CVE on `main`, unrelated; operator approved; squawk 0250 | No: one-off |
| A second Windows job, beyond DD7's one | Run 1 died on a recipe defect; operator's overnight delegation | No: better pre-run rehearsal instead |
| macOS run 2 built A only | B's row was complete from run 1 | Yes: spend reruns only on the missing rows |
| Pinned tray backend changed from `appindicator` to `gtk` | `appindicator` fails on every stock baseline and measures nothing | Yes: choose pins by measurement |
| The real-machine MSI try and the Linux window walk were skipped at the decision | The operator decided from the brief; B was rejected | No |

## Key Learnings
1. **The most expensive defects in a packaging spike are in the harness, not the product.** Rehearse hosted scripts by executing them under shims, not just by parsing them.
2. **The tool's source is the specification.** Four Briefcase premises were wrong until a reviewer read 0.4.6's code. At flight design, any decision that rests on a third-party tool's behaviour should cite that tool's source or docs, at the pinned version.
3. **Container baselines modelled on the distro's own desktop metapackage give honest "stock desktop" answers.** A bare image proves a `.deb`'s declared dependencies.
4. **Strict `doctor` scoring matters outside PyInstaller.** Any packager where `is_frozen()` is false downgrades hard gates to "skipped", so "exit 0" is not a pass.
5. **PyInstaller's gi collection depends on the build host's GLib.** Flight 2 must measure the bundle produced on the actual release runner, not the dev host.
6. **The operator's standing preference (2026-10-24):** when told to continue autonomously, the Flight Director makes and logs the calls, and alignment happens afterwards.

## Methodology Observations
Recorded against mission-control 1.2.2.

1. **`agentic-workflow`, Phase 2c/2d (deferred review and commit).**
   - **What happened:** the skill defers review and commit to after the last autonomous leg. This flight's hosted legs (4-6) needed the earlier legs' code reviewed, committed and pushed first, because `gh workflow run --ref` runs the pushed branch.
   - **Expected:** the skill names this exception.
   - **Cost:** the Flight Director had to design and log a deviation, and ran three review checkpoints instead of one. No rework.
2. **`agentic-workflow`, Phase 2b (leg completion signals).**
   - **What happened:** a leg whose acceptance depends on a remote run (`windows-cost`'s AC6) had no protocol state between "prepared, needs review and dispatch" and "landed". The Flight Director used `[HANDOFF:review-needed]` with the status left `in-flight`, then a follow-up Developer pass.
   - **Expected:** a defined pattern for legs that pause on an external run.
   - **Cost:** improvised wording in three spawn prompts; no rework.
3. **`flight`, Phase 4 (crew interview and design decisions).**
   - **What happened:** the flight design did not surface that `workflow_dispatch` requires the workflow file on the default branch.
   - **Caught by:** design review cycle 1.
   - **Expected:** an "external platform prerequisites" prompt beside the apparatus act/observe audit.
   - **Cost:** one operator question and one extra PR, caught before execution, so nothing was lost.
4. **`flight`, Leg Identification.** The flight skill's leg sizing did not anticipate that a leg spanning a hosted run needs a human outward step in its middle. Both in-flight splits came from leg design reviews (`agentic-workflow` 2a). Cost: two leg re-authorings and flight-artifact updates mid-flight.
5. **`agentic-workflow`, Phase 2a design review (positive).** Developer design reviews told to read the third-party tool's source at the pinned version corrected four wrong premises. The default "Review Leg Design" prompt does not ask for this; it came from the Flight Director's spawn prompt.
6. **`agentic-workflow`, concurrency in one worktree.** Two Developers worked in the same worktree at once (the leg 5 follow-up and leg 6), on disjoint files named in their prompts. It worked, but the skill gives no guidance on concurrent crew in one tree.
7. **`agentic-workflow`, HAT legs.** The `decision-hat` leg was designed as a five-step guided walk. The operator decided in one message from the written brief, and most of the steps were skipped. The HAT shape was heavier than a decision gate needs; no cost beyond leg authoring.
8. **Operator delegation.** The skills have no explicit "operator away, Flight Director decides" mode. The Flight Director logged each call under a stated delegation, with limits (budget caps, no installs on the operator's machine, no release). The operator accepted every call and asked for this to be the standing mode.

## Recommendations
1. **Rehearse hosted scripts by running them, not only by parsing them** (Critical; it would have saved three of six hosted jobs). For every script a hosted job calls:
   - a Linux dry run under shims for OS-only commands;
   - `PSScriptAnalyzer` for PowerShell, and `shellcheck` with `set -u` for bash;
   - a check of variable-name collisions and the order of directory creation.

   This is an acceptance criterion of any leg that prepares a hosted run.
2. **Settle the Python 3.11 failures before Flight 2 freezes on 3.11** (Critical). Run the five MCP and credential test files under a Debian `python3.11` (CI's image). If they fail, either fix the cause or move the freeze and the floor to 3.12 deliberately. A shipped installer must not carry it.
3. **Flight 2 measures the bundle the release runner produces** (Important). The exclude list and gi collection depend on the build host's GLib. A dispatch-only Linux build on the real hosted runner, plus a container install check of that artifact, comes before trusting tag-only builds. Plan the `.github/`-only PR for any new workflow at flight design.
4. **Consider splitting Flight 2** (Important). The AppImage library bundling (ABI risk) is a different risk from the `.deb`, the metadata source, the tray fix and no-tray hiding. The `.deb` already passes.
5. **Flight 3 should budget three to four macOS jobs**, rehearse every macOS-only spec line, and treat A's blank first paint on a bare launch as a defect owed a fix (Important). It also needs the darwin desktop-session mode.

## Action Items
- [ ] Investigate the 21 unit failures under CPython 3.11 versus 3.12: **squawk 0251**.
- [ ] Squawk 0250 (filelock CVEs) must be fixed before Flight 4's release dry run, and blocks a green `pip-audit` on every PR, including #306.
- [ ] Flight 2 planning: the AppImage bundling, the pystray `ValueError` fall-through (no squawk, operator 2026-10-23), hide-without-tray, the single metadata source, fresh-VM desktop checks (WebKit's sandbox and `bwrap` under AppArmor, FUSE AppImage launch, the hidden-until-focused window), a hosted-runner build check, and a decision to fold or delete `packaging/spike/`.
- [ ] Flight 2 or 3: a small unit tier for packaging helpers (`stage.py`, `score.py`'s scoring, `excludes.txt` sanity, the macOS argv shim extracted as a pure function).
- [ ] Flight 4: replace or remove the probe workflows and the stale Windows stub on `main`; the `.iss` reads the metadata source.
- [ ] When a recipe ships: document the packaging toolchain in `the_one/agents.md` and `CLAUDE.md` (deferred during Mission 31's concurrency).
- [ ] Profile the unit tier (341 s, creeping since Mission 31 F2).
