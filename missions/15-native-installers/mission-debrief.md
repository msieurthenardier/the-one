# Mission Debrief: Native Desktop Installers

**Date**: 2026-06-17
**Mission**: [Native Desktop Installers](mission.md)
**Status**: completed
**Duration**: 2026-06-07 (dusted off, M14 complete) → 2026-06-17
**Flights Completed**: 8 in-scope flights completed (F1, F3–F9); F2 (macOS Seatbelt) migrated to the follow-up mission; F10 (optional alignment) not needed.

## Outcome Assessment

The mission **achieved its (Windows-only re-scoped) outcome in full**. A non-technical Windows user
can download a single unsigned installer, click past SmartScreen, and end up with GleepGlorp AI as a
real desktop app — native window, system-tray background presence, splash, persisted window state,
single-instance focus — launched from the Start menu, with a bundled CLI, host-appropriate data, and
a tag-driven Windows release. Docker is retired entirely (dev, test, CI all host-native); routine CI
runs free on local Concourse. The operator confirmed the outcome matches intent, and that the
mid-mission pivot to **Windows-only was the right call**.

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| Single installer, no Python/Docker prereq, OS-launcher install | **Met (Windows)** / Deferred (macOS, Linux) | Windows `.exe` (F5); per-OS installers → follow-up mission |
| Launch opens a native window (browser fallback) | **Met (Windows)** / Deferred (cross-platform) | Edge WebView2 window (F4/F6/F7) |
| Data in OS-appropriate per-user location, preserved across restarts, `~/.the-one` migrated | **Met** | `%LOCALAPPDATA%`/platformdirs + `_maybe_migrate_legacy` (F1) |
| Sandbox enforcement on macOS + Linux; Windows passthrough = documented gap | **Linux Met** / macOS Deferred / Windows passthrough = **accepted documented gap** | Linux host-native bwrap (F1); macOS Seatbelt → follow-up (F2 parked) |
| Interactive PTY parity incl. Windows | **Met (Windows, ConPTY)** / Deferred (macOS, Linux) | F3; `pty_unix.py` is the macOS/Linux path |
| Runtime-absent → actionable non-Docker guidance | **Met** | F1 detection + F9 removed the last Docker-flavored messages |
| MCP/tool child starts from the frozen app | **Met** | F5 freeze seam, packaged-smoke CI proof |
| Working CLI alongside the windowed app | **Met** | `the-one.exe` two-exe model (F5), documented (F9) |
| Release tag builds + publishes installers (all three platforms) | **Met (Windows)** / Deferred (macOS, Linux) | `windows-installer.yml` `v*`→Release (F5) |
| Install + unsigned-app docs per platform | **Met (Windows)** / Deferred (macOS, Linux) | `docs/windows-install.md` (F9) |
| Builds/runs/tested without Docker; `pip` path supported; suite green in CI | **Met** | F1 host-native + F8 Concourse |

**Overall**: 7 criteria fully met; 4 met-for-Windows with the cross-platform half **deferred** (operator
re-scope, not unmet) to the follow-up macOS/Linux mission. The Windows-only goal was the right goal by
the end (operator-confirmed).

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1 Host-native runtime readiness | completed | Docker retired (dev/test/CI host-native); data-dir + migration; Linux userns-probe sandbox; M14 maintenance folded in |
| F2 macOS Seatbelt | **migrated** | Drafted + twice-design-reviewed; parked → follow-up mission |
| F3 Windows PTY parity (ConPTY) | completed | `pty_windows.py` behind the M14 seam, zero call-site change; Win32 Job Object teardown |
| F4 Native application window | completed | pywebview window; "pywebview *is* the abstraction" → single composable shell |
| F5 Packaging & installer (Windows) | completed | PyInstaller one-dir + Inno; the `clean_subprocess_env()` freeze seam; packaged-smoke CI |
| F6 Desktop presence & lifecycle | completed | Tray/background-run, single-instance, window-state; `desktop/` module |
| F7 Visual polish | completed | Splash + icon + branded native frame; `DesktopSession` refactor (frameless chrome reverted → native frame) |
| F8 CI cost-shift → Concourse | completed | Routine CI moved to local Concourse (GATE-spiked bwrap); GitHub Actions release-only |
| F9 Install docs & closeout | completed | `docs/windows-install.md`; last Docker-era messages removed; reference-doc pass |

**Patterns**: the flights that went smoothly (F3, F5) leaned on a verified seam/insight before
implementation; the one with the most rework (F7, builds #18–#20) traced to a spike that exercised
the *wrong* interaction surface — the mission's clearest argument for the platform-verification gate.

## What Went Well

1. **The M14 sandbox seam held for the entire mission with zero re-architecture.** Every spawn path
   routed through `ToolSandbox` unchanged across all nine flights — the F3 Windows PTY backend slotted
   in by satisfying the Protocol. The heaviest risk (carved into M14) paid off exactly as designed.
2. **The "pywebview *is* the abstraction" call (F4) → a single composable cross-platform desktop-shell
   module** (`the_one/interfaces/desktop/`) rather than per-OS backends. The Architect confirms it's
   genuinely follow-up-portable (the macOS port is localized — chiefly pystray's main-thread tray
   requirement), so the cross-platform-clean build pays off even though the mission went Windows-only.
3. **Spike-gated, design-reviewed execution caught real defects before they shipped** — the freeze
   env-leak analysis (F5), the `webview.screens` runtime-type bug (F6), the `fly execute -p` +
   `--tmpfs /tmp` discoveries (F8), the two-exe/`%APPDATA%` doc-accuracy catches (F9). The
   design-review-as-fact-check was especially valuable on the docs flight.
4. **Honest re-scoping kept the mission shippable.** Windows-only (operator-confirmed right) and the
   F9 docs-only narrowing both traded breadth for a clean, low-risk close — rather than executing a
   stale roadmap bundle or risking core-path regressions on unwitnessed edge cases.

## What Could Be Improved

- **Process** — A few cross-flight items recurred without being actioned: the `cross_platform` pytest
  marker (recommended F3, still a hand-maintained Windows list with a "you must update this" warning),
  the `tests/desktop_helpers.py` extraction (recommended F6, deferred F7, now diverged across 3 files).
  Carry-forward recommendations need a home that gets picked up — a per-mission "debt ledger" the next
  flight's planning consults, rather than living only in individual debriefs.
- **Technical** — Two deferred Known Issues remain open (both never witnessed in normal use): the
  single-instance no-window-`serve` silent-exit (`shell.py:488-496`) and the `run_shell` Windows
  tree-kill gap (`platform/shell.py`). Plus a quick-wins pile (stale comments, the crew-file
  `docker exec` line, HAT.md/pty-spec Docker-era references, the `skipif(system-account)` guard).
- **Documentation** — macOS/Linux install docs are intentionally absent (re-scope); the README is now
  Windows-first. This is scoped to the follow-up mission, not an oversight.

## Lessons Learned

- **Technical**: native-frame-first is the cross-platform default (F7's frameless-chrome divert proved
  WebView2 inertness on js_api/drag/resize); the env allowlist already blocks the lib-path leak class,
  so the freeze seam only needed PATH handling (F5); a packaged-smoke proves *spawn*, never
  *rendered-window* behavior — GUI needs an operator-witnessed behavior test (F5/F6).
- **Process**: a GATE spike must exercise the *exact* interaction surface the dependent leg relies on,
  before that leg — the single most expensive miss of the mission (F7) was a spike that tested the
  wrong surface. The inverse (F3/F8 spikes that hit the real surface) went smoothly.
- **Domain**: Windows ships sandbox-passthrough by accepted design; the security story is Linux/WSL2;
  the frozen-Linux boxed-mode `/usr` interpreter conflict is a real design task waiting for the
  follow-up Linux packaging flight.

## Methodology Feedback (Flight Control)

Strong candidates to codify into the methodology (surfaced repeatedly this mission):
1. **Platform-verification GATE spike** as a first-class pre-implementation gate for any leg resting on
   an unverified-runtime premise (dependency-API behavior, privilege, OS account, in-container
   networking). *(F3, F7, F8.)*
2. **"Verify runtime form, mock the real type"** in the leg-design-review step — confirm a library
   attribute's runtime type against a real install; make the mock match it. *(F6.)*
3. **Operator-witnessed behavior-test variant** — the Witnessed pattern with a human Executor + FD
   Validator for GUI surfaces no headless apparatus can reach. *(F6/F7.)*
4. **Operator-checkpoint (Phase-A/Phase-B split)** for legs that mutate live credentials or shared
   infra — autonomous artifact authoring, then operator-authorized reversible cutover. *(F8.)*
5. **Security-invariants design-review altitude** — any leg touching a denylist/allowlist/capability
   probe/sandbox selection lists the invariants it must preserve + ships tests asserting each. *(F1.)*
6. **Pre-flight live-infra enumeration** (e.g. `fly pipelines`) for infra-touching flights; and a noted
   **friction**: the batched-commit model conflicts with infra flights whose deliverable needs *pushed*
   refs to verify (F8 handled it as post-merge verification — worth a methodology note).

## Action Items

- [ ] **Create the follow-up macOS/Linux mission** — inherits the parked F2 Seatbelt spec, the
      freeze seam, the desktop-shell module, and the Concourse CI as baselines. Pre-leg audits it must
      do: macOS `_common_runtime_dirs()` (NVM/Homebrew/fnm node paths), the boxed-mode `/usr`
      interpreter answer for a frozen Linux artifact, macOS pystray main-thread tray, Linux WebKitGTK
      as a system dependency (`.deb`/`.rpm`, not AppImage), macOS Gatekeeper "app is damaged" docs,
      macOS 10× CI billing (curate the lane / use a Concourse Apple-Silicon worker).
- [ ] **Run `/routine-maintenance`** next (the methodology's between-missions health pass) to scope a
      maintenance leg/mission for the quick-wins pile + the two deferred Known Issues + the
      `cross_platform` marker + `tests/desktop_helpers.py` + the HAT.md/pty-spec Docker cleanup +
      MinIO-IP stabilization + the GitHub break-glass-workflow sync note.
- [ ] **Two deferred Known Issues** (carried in the mission Known Issues): single-instance
      no-window-`serve` coexistence policy (needs an operator design call); `run_shell` Windows
      tree-kill (`taskkill /F /T` or Job Object + un-gate the regression test).
- [ ] **Mission Control methodology**: fold the six items above into the relevant skills (leg-design
      review, agentic-workflow pre-flight recon, behavior-test authoring guide).
