# Mission: Native Desktop Installers

**Status**: active
**Depends on**: [Mission 14 — Unified Tool-Execution Sandbox](../14-unified-tool-sandbox/mission.md) — **completed** (debrief 2026-06-07)

> **Split from the original combined scope.** The unified sandbox seam (the heaviest,
> riskiest piece) was carved out into Mission 14 and runs first. This mission
> consumes that seam: the macOS sandbox backend slots in behind it, and the Windows
> PTY backend routes through it — so the scary refactor is already done and
> validated before the distribution work begins.
>
> **Architect viability (Phase 4b): feasible with caveats.** The review of the
> combined scope corrected one overstatement (the sandbox seam did not exist — now
> Mission 14's job) and surfaced the distribution-side risks reflected below: the
> frozen-app spawn problem, the absence of any pytest CI, the `~/.the-one` path
> convention, and the host-native bwrap user-namespace requirement.
>
> **Dusted off 2026-06-07 (M14 now complete).** Refreshed after Mission 14 landed:
> the seam M15 builds on is verified M15-ready (see "What Mission 14 handed this
> mission" below); the owed M14 end-of-mission maintenance is folded into Flight 1
> rather than run as a separate pass; and the operator preference for fewer
> confirmation points carries into execution (see Carried Forward from Mission 14).
> No scope change — M14's completion only strengthens viability, so no fresh
> Phase-4b re-validation was warranted.
>
> **Mission re-scoped to Windows-only (2026-06-15).** Two sequential operator
> decisions this day reshaped the mission. **(1) Depth-first-on-Windows:** after F5
> landed the Windows installer, rather than spreading packaging to macOS/Linux next,
> the operator chose to first **harden the Windows native app into a polished,
> "right" desktop experience** — system-tray/background presence, splash screen,
> custom window chrome, window-state + single-instance focus — built behind a
> **single composable cross-platform desktop-shell module** (`the_one/interfaces/
> desktop/`, pywebview + pystray, OS quirks isolated as functions; chosen over a
> per-OS-backend split per the F4 debrief's "pywebview *is* the abstraction"
> lesson). **(2) Windows-only:** on reflection the operator then **pulled macOS and
> Linux out of this mission entirely** — both the macOS Seatbelt sandbox (the parked
> Flight 2) and the macOS/Linux packaging flights migrate to a **follow-up mission
> (not yet created)**. M15's outcome narrows to: a polished, hardened, installable
> **Windows** desktop app with a tag-driven release.
>
> The cross-platform **Outcome / Success Criteria / Constraints / Environment** text
> below is a **pre-narrowing snapshot** — superseded by this note, and annotated
> inline (→ follow-up mission) where it would otherwise read as live multi-platform
> scope. The **Flights list** is the live, Windows-only roadmap. The desktop-shell
> module is still built cross-platform-clean so the follow-up mission ports it
> rather than reworking it — that, not in-mission reuse, is now the "abstract now"
> payoff. In-body cross-references to old flight numbers are pre-re-scope snapshots.

## Outcome

> *Windows-only re-scope (2026-06-15): the live outcome is the **Windows** slice of
> the paragraph below — a Windows installer, native window, host data, ConPTY parity,
> frozen-child spawn, CLI, and a tag-driven Windows release. The macOS-Seatbelt
> enforcement and the "all three platforms" installer/release language are deferred to
> the follow-up mission. Docker retirement + host-native dev/test already landed (F1)
> and stays.*

A non-technical user on Windows, macOS, or Linux can download a single installer,
run it, and end up with GleepGlorp AI as a real desktop application — launched
from their OS application menu, opening in its own native window — **without
installing Python, Docker, or anything else first**. Pushing a release tag builds
those installers for all three platforms automatically and publishes them as
downloadable artifacts. The sandbox boundary built in Mission 14 now enforces on
macOS too (behind the same seam), interactive tools reach feature parity on
Windows, and Docker is retired from the project entirely.

## Context

GleepGlorp AI (`the-one`) is a single-user, local-first AI agent platform —
Python 3.11+, FastAPI + uvicorn + WebSocket serving a **no-build-step vanilla-JS**
web UI on `localhost:8484`, plus a Rich/prompt-toolkit CLI. Today it can only be
obtained two ways, **neither of which is an installer**:

1. `pip install -e ".[all-llms,dev]"` — for developers/tinkerers.
2. Docker / docker-compose — production-shaped, but requires Docker, `SYS_ADMIN`,
   and `seccomp:unconfined` (for the bubblewrap MCP sandbox).

Neither is reachable by a normal user who just wants to run the app. This mission
converts the project into a true native desktop application distributed as per-OS
installers, with a GitHub Actions release pipeline that builds and publishes them.
**Docker is retired from this project entirely** — not just as an end-user
distribution path but as the development and test environment too: the dev loop,
the test suite, and CI all move host-native. (`pip`-editable install remains the
developer entry point.) This is consequential because today **every** Makefile test
target runs via `docker exec the-one …` and the only CI workflow is lint-only —
there is no pytest CI at all yet.

**What Mission 14 handed this mission (now verified).** M14 is **completed**
(debrief 2026-06-07). It built the shared sandboxing boundary that all four spawn
paths (shell, Python, PTY, MCP stdio) route through, enforces it on Linux
(kernel-verified via bwrap), and added a passthrough backend + selection factory so
non-Linux runs without erroring. The seam survived all four M14 flights with **zero
re-architecture**, and the debrief confirms it is **M15-ready by design**: the
`runtime_checkable` `ToolSandbox` Protocol plus Windows-forward `SpawnSpec` fields
mean a new per-OS backend slots in **by satisfying the Protocol, with no call-site
changes**. This mission therefore does **not** create the seam — it (a) slots a
macOS Seatbelt backend in behind it, (b) makes the Linux backend work host-native
once Docker is gone (user-namespace probe + graceful degrade), and (c) adds a
Windows PTY backend through the same boundary. Native Windows still ships with the
sandbox in passthrough (unenforced) — a documented, accepted gap.

The codebase already anticipates the cross-platform direction:
`the_one/platform/paths.py` documents that "Windows/macOS support lands in future
missions," and the web UI's lack of a build step is a real simplifier — turning a
localhost server into a native app reduces to "show a chromeless window pointed at
the local URL."

This mission is deliberately sequenced **before** the planned "secure the API"
mission: hardening only needs to cover the network surface once the app is no
longer assumed to be reached exclusively through a developer's browser.

### Research summary (what shaped the decisions)

- **Native window**: a system-WebView window pointed at the local server fits a
  no-build-step server app far better than wrapping it in a Rust/Node desktop
  shell (those still require freezing Python underneath, for no benefit here). A
  system-browser fallback covers environments lacking a WebView backend.
- **Packaging's real risk is not the window** — it is spawning external child
  processes (`node`/`npx`/`uv`/`uvx`) from a **frozen, double-clicked** app:
  GUI launches inherit a stripped `PATH`, and freezers inject library-path env
  vars that corrupt spawned children. Since spawning MCP servers and tools is the
  app's core value, this must be solved and verified against the **packaged**
  artifact, not the dev entry point.
- **Windows PTY is feasible now, not a research project.** ConPTY
  (`CreatePseudoConsole`, Windows 10 1809+) is mature and wrapped by the
  maintained `pywinpty` library; the work is adding a Windows backend to
  `platform/pty.py` (which today raises `NotImplementedError` on Windows), routed
  through the Mission-14 seam.
- **macOS sandboxing** uses Seatbelt via Anthropic's `@anthropic-ai/sandbox-runtime`
  (already referenced in `sandbox/base.py`), which covers Linux + macOS with no
  Docker/root/VM. It slots in behind the M14 seam.
- **Signing/notarization is deferred** (private repo, no certificate spend).
  Unsigned macOS is the harshest UX (Gatekeeper reports "app is damaged"), so
  per-OS workarounds must be documented, and CI must be structured so signing can
  be enabled later without rework.

## Success Criteria

> *Windows-only re-scope (2026-06-15) — how to read the list below:*
> - *Wherever a criterion says "macOS / Linux / all three platforms," read it as
>   **Windows (x64) only** for this mission; the other-platform obligations move to
>   the follow-up mission.*
> - *The **macOS Seatbelt enforcement** criterion ("Sandbox enforcement … active on
>   macOS") is **fully deferred** to the follow-up mission. (Linux host-native
>   enforcement already landed in F1 and stays; native Windows remains the documented
>   passthrough gap.)*
> - *Re-scope **adds** one criterion to reflect the new hardening focus:*
>   - *[ ] The installed Windows app behaves like a polished, always-on desktop
>     app — system-tray presence with background-run (close-to-tray, quit from the
>     tray menu), a launch splash, themed window chrome, persisted window state, and
>     single-instance focus (a relaunch raises the running window). **(HAT +
>     Witnessed GUI behavior-test backed; F6/F7.)***

- [ ] A user can install the app on **Windows (x64)**, **macOS (Apple Silicon)**,
      or **Linux (x64)** from a single downloadable installer artifact, with **no
      pre-existing Python or Docker installation**, and launch it from their OS
      application launcher. *(behavior-test-backed, per platform)*
- [ ] Launching the installed app opens the agent UI in a **native application
      window**, falling back to the system browser only when no native web view is
      available. *(behavior-test-backed)*
- [ ] The installed app stores its data and encrypted secrets in an
      OS-appropriate per-user location and **preserves them across app restarts**;
      an existing `~/.the-one` directory is migrated rather than orphaned.
- [ ] Sandbox enforcement (from the Mission-14 boundary) is now active on **macOS**
      as well as Linux; the Linux backend continues to enforce **host-native**
      (no Docker). Windows runs through the passthrough — a documented gap.
      *(behavior-test-backed on macOS)*
- [ ] Interactive PTY-backed shell/session tools work at feature parity on **all
      three platforms**, including Windows, and remain governed by the shared
      sandbox boundary where a backend exists. *(behavior-test-backed)*
- [ ] When a required external runtime for MCP servers is absent, the app
      **detects this and presents actionable, non-Docker guidance** rather than
      failing silently. *(behavior-test-backed)*
- [ ] An MCP/tool child process **actually starts** when launched from the
      installed (frozen) app — not only from a source checkout.
      *(behavior-test-backed — guards the PATH/library-var risk)*
- [ ] The installed deliverable includes a working **command-line interface**
      alongside the windowed app.
- [ ] Pushing a release tag causes installers for **all three target platforms**
      to be built automatically and published as downloadable release artifacts.
- [ ] Installation and first-run steps — **including how to get past unsigned-app
      OS warnings** — are documented for each platform.
- [ ] The app builds, runs, and is **tested entirely without Docker**; the
      developer `pip` install path remains supported and the existing test suite
      passes host-natively in CI.

## Stakeholders

- **End users** — non-technical people who want to run their own local AI agent by
  double-clicking an installer, not by learning pip or Docker.
- **Project maintainer** — wants a repeatable, automated release process and a
  distribution + development story that does not depend on Docker.
- **Future "secure the API" mission** — depends on the CLI and any future
  programmatic surface staying architecturally distinct from the network surface,
  so hardening has a clean boundary to harden.

## Constraints

- **No code signing or notarization this mission.** The repository is private
  (so free OSS signing programs do not apply) and certificate spend is out of
  scope. Installers ship **unsigned**; per-OS click-through workarounds are
  documented. CI must be structured so signing can be enabled later (conditional
  steps gated on secret presence) **without reworking the pipeline**.
- **Sandbox backends slot behind the Mission-14 seam** — this mission adds the
  macOS (Seatbelt) backend and makes the Linux backend run host-native; it does
  not re-architect the boundary.
- **Native Windows ships unsandboxed** this mission (no AppContainer backend) —
  a documented, accepted gap. (WSL2 users inherit the full Linux sandbox path.)
  This is the *sandbox* gap only — PTY/tool functionality on Windows is at full
  parity via ConPTY.
- **Host-native bwrap requires unprivileged user namespaces.** Outside Docker,
  bubblewrap needs `kernel.unprivileged_userns_clone=1` (default on modern
  kernels, but not universal). The Linux installer docs must state the minimum
  requirement and degrade gracefully.
- **Future MCP exposure must front the gated API surface, not the in-process /
  CLI path.** Recorded so later missions honor it; no MCP-exposure work happens here.
- **Preserve the no-build-step vanilla-JS UI.** No new frontend framework or JS
  build toolchain.
- **External MCP runtimes are not bundled.** `node`/`uv`/etc. are required on
  `PATH`; the app detects and guides.
- **Out of scope**: macOS Intel and ARM Linux builds; an auto-update mechanism;
  API authentication/hardening (the following mission); MCP server-side exposure
  of the app; a Windows sandbox backend.

## Environment Requirements

- **Build/CI**: GitHub Actions runners — `windows-latest` (x64),
  `macos-latest` (Apple Silicon / arm64), `ubuntu-latest` (x64). Each runner
  carries the OS-native toolchain to produce that platform's installer and to run
  the host-native test suite (including Playwright/Chromium provisioning for
  browser tests, previously provided by the container).
- **End-user runtime**: no Python or Docker required. Native web view backends —
  Edge WebView2 (Windows, present on modern installs), WKWebView (macOS,
  built-in), WebKitGTK (Linux; system-browser fallback when absent). External
  runtimes (`node`/`uv`) needed only for MCP servers, detected and guided.
  Windows requires Windows 10 1809+ for ConPTY; Linux sandboxing requires
  `kernel.unprivileged_userns_clone=1`.
- **Developer environment**: Python 3.11+ host with the existing `pip -e` install,
  run and tested **host-natively (no Docker)**.

## Open Questions

- [ ] Resolve the **bundler** choice during the packaging flight (single tool that
      emits per-OS installers + notarization hooks, vs. a freezer paired with
      per-OS installer tooling). Capability criteria above are tool-agnostic. No
      freeze configuration exists yet; hidden-import discovery (pydantic-settings
      env-file discovery, uvicorn extras, dynamic imports in `main.py`, MCP SDK
      transports) is expected to be the long-tail effort.
- [ ] **Single-instance / port-conflict** behavior for the native app: what
      happens when the app is already running or `8484` is taken.
- [ ] **`requires_bwrap`-marked tests** in the host-native CI world: a dedicated
      Linux CI job with bwrap provisioned, or permanently skipped outside
      explicitly-provisioned Linux hosts?
- [ ] How aggressively to handle the **`~/.the-one` → OS-conventional path
      migration** (move vs. symlink vs. one-time copy with operator confirmation).

## Known Issues

- **Boxed mode requires the interpreter inside `/usr`** *(discovered F1 CI
  closeout, 2026-06-11)*: `minimal_rootfs` mounts only `/usr` + merged-usr
  symlinks, and `resolve_python()` deliberately fails-loud for interpreters
  outside it (e.g. GH Actions hostedtoolcache; fixed in CI by venv-from-system-
  python). **Flight 5 implication**: a frozen app's bundled interpreter also
  lives outside `/usr` — boxed mode on the packaged Linux artifact needs a
  deliberate design answer (read-only interpreter-prefix bind vs. documented
  host-mode fallback), not an accident.
- **`run_shell` timeout-kill is not prompt on Windows** *(discovered F3 L4 CI,
  2026-06-14)*: the shell-execution timeout fires and returns the correct
  "timed out" message, but killing the spawned `cmd.exe` does NOT promptly reap
  its child tree (no process-group / tree kill) — a backgrounded child runs to
  completion. Parallel to the PTY teardown gap that Leg 3 solved with a Win32
  Job Object. The prompt-kill regression test (`test_timeout_returns_promptly`)
  is POSIX-gated for now. **Follow-up (Flight 5 or a maintenance pass)**: give
  `run_shell`'s Windows path a tree-kill (`taskkill /F /T` or a Job Object,
  mirroring the PTY backend). Windows ships unsandboxed/best-effort (DD9), so
  this is a robustness gap, not a containment one.
  **F5 disposition (2026-06-14, Leg 5):** held **OUT** of Flight 5 — wiring a Job
  Object into `create_subprocess_shell`'s non-PTY proc is more than a one-liner and
  does not ride along in the freeze-seam leg; it is a robustness gap, not a freeze
  blocker. **Carried to F7 (Linux packaging) / a maintenance pass.**

- **Desktop single-instance silently defers to a no-window the-one** *(discovered F6
  Leg-6 HAT, 2026-06-15)*: when a headless `the-one serve` (no window) already holds
  `8484`, launching the desktop app POSTs `/api/window/focus`, gets `{"focused": false}`,
  and **silently exits** — no window, no message. Desktop-vs-desktop single-instance is
  correct (raises the running window); only the no-window-`serve` case is wrong. The
  operator chose to **land F6 and defer this** (HAT, 2026-06-15). **Follow-up**: settle
  the coexistence behavior (open a window onto the existing server / notify-and-exit /
  own free port) and harden the `is_ours` branch so it never silently no-ops — a small
  Leg in a follow-up flight. (Distinct from, but related to, the operator's broader point
  that the unauthenticated localhost API is the next mission's "secure the API" work.)

Lessons and follow-through items inherited from the M14 debrief (2026-06-07):

- **Operator preference — fewer confirmation points.** Reserve `AskUserQuestion`
  for genuine product/scope/architecture decisions where the answer changes *what*
  gets built. For routine lifecycle confirmations (mark landed→completed, apply an
  obvious self-evident fix, run the verification a flight already planned), **decide
  with the sensible default, state the assumption, and proceed** — the operator can
  reverse it. Carried explicitly into this mission's execution.
- **Owed M14 maintenance is folded into Flight 1** (see Flight 1) rather than run
  as a standalone `/routine-maintenance` pass — the `SandboxError` import-cycle
  relocation gates clean M15 backend error surfaces, so it lands first.
- **Optional forward-proofing M14 left available** (cheap, do-if-touched, not
  blocking): add a `network_allowed: bool = False` param to `_build_boxed_profile`
  (decouples a future boxed-network profile from a code change), and add a
  `@requires_bwrap` reaper-path boxed-session cleanup test. Pick up opportunistically
  in whichever flight touches the boxed path.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned
> and created one at a time as work progresses. This list will evolve based on
> discoveries during implementation.
>
> **Execution-order swap (2026-06-13):** Flight 3 (Windows PTY parity) is being
> executed **before** Flight 2 (macOS Seatbelt). Flight numbers are kept as
> stable identities (the macOS spec is already drafted + design-reviewed as
> Flight 2); only the order changes. Rationale: the operator has a native
> Windows host (under WSL2) — a *local* test apparatus the macOS flight lacks
> — and macOS GitHub runners bill at 10× vs. Windows 2× on this private repo.
> Both backends slot behind the M14 seam independently, so no dependency
> blocks the swap. Flight 2 is **parked** (see its Parking Note); the two F1
> ride-alongs whose deadline is "before the CI matrix expands" migrated from
> Flight 2's Leg 1 into Flight 3 (the Windows matrix expands first).
>
> **Packaging split — Windows-first (2026-06-14):** The original single Flight 5
> ("Packaging & installers" for all three OSes at once) is **split into one
> packaging flight per OS**, executed Windows-first. Planning recon (PyInstaller
> + the frozen-app child-spawn problem, per-OS native-dep surfaces — Windows
> pywinpty ABI, macOS Gatekeeper/Finder-PATH, Linux WebKitGTK wiring) confirmed
> all-three-in-one is a multi-week flight, not the 1–3 day target, and would
> leave three half-debugged toolchains with a behavior surface that can't be
> isolated. Windows goes first: the operator has a native Windows box (a *local*
> HAT apparatus the other OSes lack) and Windows runners bill at 2× vs. macOS
> 10×. The **cross-cutting freeze runtime seam** (the `clean_subprocess_env`
> child-env sanitizer, frozen-detection, the `resolve_python()` frozen fix, the
> unencoded-I/O audit) is built **once** in the Windows flight and reused by the
> macOS and Linux flights, which then add only their OS-specific freeze recipe +
> installer + env quirks. Downstream flights renumber (the release-pipeline flight
> moves to Flight 8); the original per-OS packaging intent is preserved across
> Flights 5–7.

- [x] Flight 1: **Host-native runtime readiness** *(completed)* — run the app as a normal host
      process with no Docker anywhere (dev, test, run): wire `Settings.data_dir`
      to an OS-appropriate per-user location (with `~/.the-one` migration);
      external-runtime (`node`/`uv`) detection + actionable non-Docker guidance;
      make the Linux sandbox backend work host-native (user-namespace probe +
      graceful degrade); and move the test suite + a new pytest CI host-native
      (replacing the `docker exec` Makefile flow, provisioning Playwright/Chromium
      on runners). **Also absorbs the owed Mission 14 end-of-mission maintenance**
      (folded here instead of a separate `/routine-maintenance` pass): relocate
      `SandboxError` out of the import cycle in `the_one/mcp/errors.py` (M14 debrief
      flags this as *"blocks clean M15 backend errors"* — a prerequisite for the
      Flight 2/3 backend error surfaces), and clear the deferred M14 doc/footgun
      debt (the non-merged-usr `--symlink` portability caveat + boxed-profile
      network-off note in `SECURITY-MODEL.md`; the `_TOOL_CLASSES` cross-config
      note, fork-safety convention, `@requires_bwrap` workspace-under-`$HOME`
      constraint, and PTY-echo sentinel footgun in `agents.md`/`CLAUDE.md`;
      investigate the pre-existing `test_connectors_e2e.py::test_e2e_full_lifecycle`
      flake).
- [→] Flight 2: **macOS sandbox backend (Seatbelt)** *(**MIGRATED out of M15** —
      Windows-only re-scope 2026-06-15)* — was: add the macOS backend behind the
      Mission-14 seam via **direct `sandbox-exec` + generated SBPL** (DD1: not the
      `sandbox-runtime` Node dependency); kernel-verified containment in CI on
      `macos-15`. The drafted + design-reviewed spec under
      `flights/02-macos-sandbox-seatbelt/` stays on disk as a parked artifact but is
      **no longer in M15 scope** — it moves to the follow-up macOS/Linux mission.
- [x] Flight 3: **Windows PTY parity (ConPTY)** *(landed 2026-06-14; behavior-test backing deferred to post-installer acceptance — Flight 7/8)* —
      add a Windows backend to `platform/pty.py` (via `pywinpty`/ConPTY) and a
      read/idle loop that does not depend on POSIX-only `select`/`fcntl`, routed
      through the shared seam, bringing interactive shell/session tools to feature
      parity on Windows. Absorbs the two migrated F1 ride-alongs
      (`skipif(which("bwrap"))` re-marking; `mcp/__init__` guard comments).
- [x] Flight 4: **Native application window** *(landed 2026-06-14; windowed-launch via `the-one app`; rendered-window HAT operator-run-pending)* — launch uvicorn in-process and open
      a chromeless native web-view window pointed at the local server, with a
      system-browser fallback; handle app lifecycle (port selection,
      single-instance, clean shutdown).
      - **Planning input (browser-test strategy, operator-directed 2026-06-14):**
        the browser suite (513 tests, ~15 min — now the CI long pole) tests the
        SAME web UI that ships inside the native window, so it stays valuable —
        but (a) **path-filter the browser CI job to UI-touching PRs only**
        (`interfaces/web/**`, templates, the relevant API): most PRs
        (connectors/DB/MCP/agent) don't touch the UI and pay 15 min for ~zero
        signal; (b) **dedup redundant browser tests** (e.g. `test_markdown` 91,
        overlapping editor flows — coverage-guided); (c) note the renderer shift —
        the native window uses Edge WebView2/WKWebView/WebKitGTK, so
        Playwright-Chromium becomes a *logic proxy*; the real-WebView acceptance
        check belongs here/Flight 7, not in the unit browser suite. The **full
        browser suite's "full tier" runs on RELEASES (Flight 6), not nightly**
        (releases don't exist yet — see Flight 6).
- [x] Flight 5: **Packaging & installer — Windows** *(landed 2026-06-14; freeze
      runtime seam + `.spec` + Inno installer + CI packaged-smoke — the frozen-app
      child-spawn fix proven green on the `windows-2022` runner; optional operator HAT
      deferred to F9)* — the cross-cutting freeze
      runtime seam (built here, reused by F6/F7) + the Windows installer. Freeze
      the app + dependencies with **PyInstaller (one-dir)**; bundle the web static
      assets; build the **`clean_subprocess_env()`** child-env sanitizer (restore
      PyInstaller's `*_ORIG` lib-path vars / drop the bundle-injected ones,
      augment `PATH`) + frozen-detection so every spawn path (MCP stdio, shell,
      interpreter, PTY) finds `node`/`uv` and children don't inherit the bundle's
      libs; fix the `resolve_python()` frozen footgun and the unencoded-I/O sites;
      produce an **Inno Setup** installer with a Start-menu shortcut → `the-one
      app`; ship the CLI alongside. **CI packaged-smoke proof** on the Windows
      runner: build the frozen artifact, launch it, and spawn a **real
      child-process** through a tool (the spawn-fix's only real proof). Rendered-
      window + full operator HAT against the real installer deferred to the
      comprehensive end-of-mission acceptance (F9).
- [x] Flight 6: **Windows native app hardening — desktop presence & lifecycle**
      *(landed 2026-06-15; operator HAT pass — tray/background-run, single-instance
      focus, window-state, splash deferred to F7; builds on F4's native window, not F5's
      packaging)* — make the installed Windows app behave like a real always-on
      desktop app, behind a **single composable cross-platform desktop-shell module**
      (`the_one/interfaces/desktop/`, pywebview + pystray, OS quirks isolated as
      functions — chosen over a per-OS-backend split per the F4 "pywebview *is* the
      abstraction" lesson; built cross-platform-clean so the follow-up mission ports
      it). Scope: **system-tray icon + background-run** (close-to-tray with a
      first-run "still running" notice, quit from the tray menu — the tray event-loop
      vs. pywebview GUI-loop integration, pystray on a detached thread with pywebview
      owning the main thread, is the lead risk); **single-instance focus** (a second
      launch raises the running window via a new `/api/window/focus` endpoint and
      exits, instead of opening a duplicate — closes F4's duplicate-window gap,
      reusing `_select_port`'s `is_ours`; the endpoint must clear the Origin
      allowlist); **window-state persistence** (size/position JSON under `data_dir`,
      clamped to visible bounds on restore). Validation: pytest for the focus
      endpoint / state serialization / module wiring + an **operator HAT** and a
      **Witnessed GUI behavior-test** spec (folds in the owed F4/F5
      theme-persists-across-restart check). Packaged-smoke on the `windows-2022`
      runner.
- [x] Flight 7: **Windows native app hardening — visual polish** *(landed 2026-06-17; HAT
      passed build #22)* — make the app *look* finished: a **splash/loading window** shown
      while uvicorn boots and dismissed when the UI is ready; app **icon/branding polish**
      (256-px brand `.ico` on the windowed exe); and a **branded native window**. *Mid-flight
      DD3 divert (2026-06-16): the originally-planned **frameless custom chrome** (HTML titlebar
      + pywebview js_api controls) was abandoned — it fights Windows WebView2 (drag/resize/js_api
      inert on edgechromium) — in favor of **DD2-alt: a native OS frame** (the F4/F6 known-good
      window; drag/min/max/close/resize all native, native X → close-to-tray). The `DesktopSession`
      refactor + splash + icon all shipped; the custom chrome did not.* Extends the F6
      desktop-shell seam.
> *The packaging flights **"— macOS" and "— Linux"** (former F8/F9) and the macOS
> Seatbelt backend (F2) **migrated to the follow-up macOS/Linux mission** (Windows-only
> re-scope, 2026-06-15). Their design notes — F5 freeze-seam reuse, `.app`/`.dmg`,
> `.deb`/`.rpm` via fpm, WebKitGTK-as-system-dependency, the boxed-mode
> interpreter-prefix Known Issue, and the per-OS unsigned-app workarounds — travel
> with them. The release/acceptance/alignment flights below renumber down and narrow
> to Windows.*

- [x] Flight 8: **CI cost-shift — move day-to-day CI to local Concourse**
      *(landed 2026-06-17 — reframes the original "Windows release pipeline (CI/CD)"
      entry below; routine CI now on the local Concourse `the-one` pipeline, GitHub Actions
      finalized release-only. Post-merge: first green `ci` on `main` + destroy the paused
      `windows-installer` pipeline — see the flight's `ci/README.md`)* — the project
      **exhausted its GitHub Actions minutes** (F7's PR #119
      CI was all-red purely from an Actions billing failure). Move routine CI
      (lint/test/browser/windows-subset, spike-permitting bwrap) to the local Concourse
      `the-one` team and finalize GitHub Actions as **release-only** (the `v*`-tag
      installer). Modeled on the operator's prior goldfinch CI-cost-shift. Goldfinch
      push-to-main model (per-PR gating via pre-push `fly execute`), installer auto-on-main
      kept + manual/on-demand for branches, spike-gated bwrap port.
      - *Original placeholder (now mostly satisfied / superseded):* the tag-driven Windows
        release **already shipped in F5** (`windows-installer.yml`: `v*` → Inno installer →
        GitHub Release); this flight keeps it as the sole active GitHub workflow (signing
        stays conditional/deferred per mission constraints). The deferred *"full browser
        suite as a release-gated tier"* is **superseded** — on free Concourse the full
        browser suite runs on every `main` push (the tiering existed only to ration Actions
        minutes).
- [ ] Flight 9: **Windows first-run UX, docs & acceptance** — first-run experience,
      **Windows** install + unsigned-app/SmartScreen-workaround documentation,
      replacing the remaining Docker-flavored runtime error messages, and end-to-end
      acceptance behavior tests on Windows (the **comprehensive operator HAT against
      the real Windows installer** lands here).
- [ ] Flight 10 *(optional)*: **Alignment** — hands-on session installing the real
      Windows artifact on a real machine, tuning first-run UX, and making
      judgment-call adjustments that benefit from human feedback.
