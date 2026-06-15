# Flight Debrief: Packaging & Installer — Windows

**Date**: 2026-06-15
**Flight**: [Packaging & Installer — Windows](flight.md)
**Status**: landed
**Duration**: 2026-06-14 (planned + executed + landed) — 2026-06-15 (post-landing fixes, merge to main, v0.2.1 release)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The flight delivered a **double-click Windows desktop installer** for `the-one`, and
— critically — the **frozen-app child-spawn fix proven against the real packaged
binary**. A user can install `the-one-setup-0.2.1.exe`, launch a native window from
the Start-menu shortcut, and have MCP/tool child processes actually spawn (the
mission's single biggest packaging risk). The cross-OS **freeze runtime seam** built
here (`clean_subprocess_env`, `is_frozen`, frozen `resolve_python`, `.env` anchoring,
the `the-one doctor` diagnostic) is reusable by F6/F7 by construction.

Shipped: the PyInstaller one-dir `.spec`, the Inno Setup installer, a CI
packaged-smoke (frozen `doctor` + `serve` + single-instance), and — beyond the
original scope, forced by environment realities — a **local Concourse build pipeline**
publishing to minio and a **tag-triggered GitHub release** workflow. Merged to `main`,
tagged `v0.2.1`, published as a GitHub Release with the installer attached.

### Mission Criteria Advanced

- ✅ Install on **Windows (x64)** from a single installer, no pre-existing Python/Docker, launch from the OS launcher.
- ✅ Launching opens a **native window** (windowed `the-one-app.exe`), system-browser fallback intact.
- ✅ An MCP/tool **child process actually starts** from the frozen app (packaged-smoke `doctor` proof — green on the real binary).
- ✅ The deliverable includes a working **CLI** alongside the windowed app (`the-one.exe chat|serve|doctor`).
- ✅ **Absent-runtime detection + non-Docker guidance** (`the-one doctor` / `detect_runtimes`).
- ◑ **Installation/first-run docs incl. SmartScreen** — Windows done (`packaging/windows/README.md`); cross-OS completes at F9.
- ✅ App **builds/runs/tested without Docker**; pip-editable dev path intact; suite passes host-native.
- ◑ **Release tag → installers** — Windows half delivered (pulled forward from F8); mac/Linux matrix is F8.

## What Went Well

- **DD2 — the freeze seam is the flight's architectural crown jewel.** The planning-phase premise correction (the env allowlist *already* blocks the `LD_LIBRARY_PATH`/`DYLD_*` leak class; only `PATH` leaks) narrowed the "textbook two-part PyInstaller fix" to a provable PATH-strip + augment, with **zero dead restore-`*_ORIG` code**. The allowlist invariant is asserted by a test, not a comment. The strip-always-wins precedence (caller-side re-strip at `stdio.py`, keeping `build_stdio_environ` pure) decoupled the MCP transport from the freeze concept cleanly. Both debrief agents called this out as textbook.
- **Doctor-as-apparatus (DD5).** `the-one doctor` exercises the exact `_build_subprocess_env()` path, spawns a real probe child, and emits grep-able PASS/FAIL — the right machine-readable instrument for the CI smoke. Advisory-not-gate runtime detection behaved correctly (CI green with `uv` absent-but-advisory while child-spawn held).
- **Methodology resilience under environment shock.** Per-leg design review caught two high-severity latent `.spec` build-breakers *in review* (the `EXE(version=)` string trap; the `[gui]`-extra install gap). When the dev-host-can't-freeze reality + the GitHub artifact quota blocked the planned path, the flight pivoted to a Concourse pipeline and a manual→automated release without re-opening the landed flight (recorded in flight-log Decisions/Post-Landing).
- **Honest defer-to-CI framing.** Legs 2–4 were explicit that the real proof is the observed green CI run, not local execution. The three CI-surfaced issues (mcp.cli/typer, Inno pin, artifact quota) are evidence the approach correctly identified what Linux can't catch.

## What Could Be Improved

### Process
- **The rendered-window gap shipped two defects.** Both post-landing operator-HAT findings (stray **console window**; **theme not persisting**) live in the GUI/webview path that `doctor`/`serve` *cannot* observe. DD5 named this gap and deferred it to the F9 HAT — but it materialized within ~24 h of landing, confirming the F9 HAT is **not optional in practice**. The lesson: a GUI behavior test should exist *before* F6/F7 inherit this codebase, not only at F9.
- **"CI proves it on the PR" (DD5) was superseded post-landing.** The build-trigger policy moved to tag-only on GitHub + Concourse for day-to-day. F6/F7 designs should **not** re-state the per-PR-freeze premise.
- **The artifact-storage quota was not pre-identified as a risk.** It blocked the planned upload and forced the Concourse fallback. A first-time freeze flight should pre-plan the distribution apparatus (and its quotas), not discover it.
- **First-time freeze recipes carry 2–4 CI-only-discoverable issues.** Budget push-and-iterate CI cycles into F6/F7 leg estimates; this isn't a spec failure, it's the cost of cross-compiling a Windows/mac recipe from Linux.

### Technical
- **Test wall-clock regression: ~314 s (F4) → 419 s (F5), +105 s** for +41 tests. The new doctor/seam tests spawn real subprocesses in tight loops. No failures/flakes, but if F6/F7 add OS-specific subprocess-heavy tests the suite could get meaningfully slow — monitor. (Counts: 3115 passed / 10 skipped / 589 deselected; skip+deselect flat vs F4.)
- **Bundle growth 38 → 56 MB.** `MERGE` de-dupes binaries/data but not the per-EXE **PYZ bytecode** — two archives = ~18 MB. Acceptable for v0.2; the `AttachConsole` single-exe alternative is documented in the `.spec` if size matters later.
- **minio-by-IP coupling.** The Concourse publish reaches minio by compose-network IP (Vault `minio.endpoint`) because build containers use external DNS. A `docker compose down/up` that reassigns the IP silently breaks publish until the Vault value is updated. Operational gotcha, documented, inherited by any F6/F7 use of the pipeline.
- **Untested edge cases** (structural, Linux-only host): `THE_ONE_PYTHON` pointing at a non-interpreter; `_bundle_dir()` frozen-but-`_MEIPASS`-absent fallback (dead on a real one-dir binary); Windows case-insensitive PATH compare (`normcase` is a no-op on Linux); `frozen_entry_gui.py`'s `sys.argv=["…","app"]` injection isn't asserted against a dispatching `cli_entry`.
- **`_common_runtime_dirs()` is macOS-incomplete.** Missing the most common dev node installs: `~/.nvm/versions/node/*/bin` (NVM), `/opt/homebrew/opt/node/bin`, `~/.fnm/.../bin`. F6 should audit/extend before relying on PATH augmentation for `node`/`uv`.

### Documentation
- No runbook for "update the minio endpoint Vault secret when the compose network changes" (only a pipeline comment).
- No declarative record of the pipeline's Vault path dependencies (deploy key, minio creds) beyond YAML comments — add a `pipeline-secrets.example` or reference the epipen pattern.
- When F6/F7 add packaging dirs, a top-level `packaging/README.md` index would cut navigation friction.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Build moved to a **local Concourse pipeline** (not GitHub-only) | PyInstaller/iscc can't run on the Linux dev host; GitHub artifact quota blocked uploads | **Yes** — F6/F7 plan Concourse as the primary day-to-day build apparatus from the start |
| **DD6 single multi-call exe → two-exe split** (console `the-one.exe` + windowed `the-one-app.exe`) | A console-subsystem PE *always* gets a console window — no argv escape; the GUI shortcut popped a blank cmd | **Yes** — console-vs-windowed subsystem is a *first-class* design decision for any packaged Windows GUI app |
| `iscc` installer build **consolidated into the CI smoke leg** (flight.md said "Leg 5") | The CI leg already provisions the Windows runner + builds the one-dir | Yes (one CI leg owns build+smoke+installer) |
| GitHub installer build **moved to tag-only** + Release-on-tag | Operator-directed: Concourse builds always; GitHub only on a version tag | **Yes** — pulls Flight-8 release-on-tag intent forward |
| `webview.start(private_mode=False, storage_path=…)` (theme persistence) | pywebview's `private_mode=True` default = ephemeral profile; localStorage dropped each launch | **Yes** — every `webview.start()` must make the `private_mode` decision explicit (see cross-flight note) |
| Release **assets** instead of Actions artifacts | Release assets bypass the artifact-storage quota entirely | **Yes** — the right distribution home; now automated in `windows-installer.yml` |

## Key Learnings

1. **The packaged-smoke proves spawn behavior, never rendered-window behavior.** Console-subsystem and webview-profile defects are invisible to `doctor`/`serve`. A **Witnessed GUI behavior test** (no console on GUI launch; theme survives restart; single-instance from the shortcut) is the missing apparatus — author it before F6.
2. **Cross-flight: the `private_mode` default was a Flight-4 omission** that only surfaced once F5 produced a persistent installed binary (F4 testing was source-checkout, where the browser's own profile persisted `localStorage`). **F4's debrief should record:** any `webview.start()` call must document the `private_mode`/`storage_path` decision explicitly.
3. **`settings.data_dir` is now the single anchor** for `.env` (DD8) *and* the webview profile — the right pattern for all frozen-app state that must survive restart/reinstall; document it for the frozen path.
4. **"Runtime seam shared, freeze recipe per-OS" (DD1 trade-off) held exactly** — F6/F7 inherit the seam unchanged and add only their freeze recipe + installer.
5. **Build-host split is unavoidable and changes the verification loop** — dev-host "verify" is synthetic (py_compile/yaml-parse); real proof is push-and-iterate on the runner. Plan for it.

## Recommendations

1. **Author a Windows GUI behavior-test spec now** (before F6) — Witnessed pattern, three steps (no console window on GUI launch; theme persists across restart; single-instance from the shortcut). Apparatus = the Concourse-published installer on a HAT-connected Windows VM (Playwright/DevTools against the webview). F6/F7 inherit it with OS-specific deltas; runs as the F9 acceptance gate. *(This is the single highest-leverage fix — it directly closes the gap that shipped both defects.)*
2. **F6/F7: inherit the seam unchanged; budget 2–4 CI-only freeze issues per OS; design the Concourse build path in from the start;** and treat the two-exe/subsystem question explicitly (macOS `.app` vs CLI binary; Linux desktop-entry target).
3. **Audit & extend `_common_runtime_dirs()` for macOS** (NVM/fnm/Homebrew node paths) before F6 relies on PATH augmentation.
4. **Carry the `run_shell` Windows tree-kill into an explicit F7/maintenance leg** (Job Object / `taskkill /F /T`), mirroring the PTY backend — still open from F3.
5. **Add the minio-endpoint runbook + a pipeline-secrets manifest**, and a top-level `packaging/README.md` index when F6/F7 land their dirs.

## Action Items

- [ ] Author the Windows GUI behavior-test spec (Rec 1) during F6/F9 planning — see `.claude/skills/behavior-test/AUTHORING.md`.
- [ ] Append the cross-flight `private_mode`/`webview.start()` note to **Flight 4's debrief** (Key Learning 2).
- [ ] F6 leg design: audit/extend `_common_runtime_dirs()` for macOS node installs.
- [ ] F7: explicit leg for the `run_shell` Windows tree-kill (carried from F3 Known Issues).
- [ ] Add the minio-endpoint Vault runbook + `pipeline-secrets.example` (or reference epipen) under `ci/`.
- [ ] Monitor suite wall-clock in F6/F7 (419 s baseline; investigate if subprocess-heavy OS tests push it materially higher).
- [ ] (Opportunistic) Close the named untested edge cases (`THE_ONE_PYTHON` non-interpreter; `_bundle_dir` no-`_MEIPASS`; `frozen_entry_gui` argv injection).

## Methodology Feedback

- **mission/flight/leg skills held up well.** The per-leg design review (a Developer cross-referencing the spec against real code) earned its keep — it caught two high-severity `.spec` build-breakers before implementation that would otherwise have been CI-only discoveries. The "author-locally, prove-on-CI" leg framing was honest and the flight log's Decisions/Anomalies/Post-Landing sections captured the pivots cleanly (append-only, flight stayed `landed`).
- **One friction:** a leg can reach "locally complete" while carrying latent CI-only failures, raising the Flight Director's post-commit vigilance burden. Not a skill defect — inherent to cross-compilation — but worth a standard "forward dependencies / CI-only acceptance" callout in packaging-style leg specs (F5's legs already did this well; codify it for F6/F7).
