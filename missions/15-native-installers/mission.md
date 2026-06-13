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

## Outcome

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

## Carried Forward from Mission 14

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
- [ ] Flight 2: **macOS sandbox backend (Seatbelt)** *(spec drafted + design-reviewed;
      **PARKED** — executes after Flight 3)* — add the macOS backend behind the
      Mission-14 seam via **direct `sandbox-exec` + generated SBPL** (DD1: not the
      `sandbox-runtime` Node dependency) so macOS tool/PTY/MCP execution is enforced;
      kernel-verified containment in CI on `macos-15`. Behavior-test backing of the
      macOS containment criterion deferred to Flight 8 (no operator macOS hardware).
- [ ] Flight 3: **Windows PTY parity (ConPTY)** *(executes first — see order swap)* —
      add a Windows backend to `platform/pty.py` (via `pywinpty`/ConPTY) and a
      read/idle loop that does not depend on POSIX-only `select`/`fcntl`, routed
      through the shared seam, bringing interactive shell/session tools to feature
      parity on Windows. Absorbs the two migrated F1 ride-alongs
      (`skipif(which("bwrap"))` re-marking; `mcp/__init__` guard comments).
- [ ] Flight 4: **Native application window** — launch uvicorn in-process and open
      a chromeless native web-view window pointed at the local server, with a
      system-browser fallback; handle app lifecycle (port selection,
      single-instance, clean shutdown).
- [ ] Flight 5: **Packaging & installers** — freeze the app + dependencies and
      produce per-OS installer artifacts (Windows, macOS `.dmg`, Linux AppImage);
      bundle the web static assets; resolve/scrub frozen-environment vars so
      spawned child processes find `node`/`uv` and resolve libraries correctly;
      ship the CLI alongside. Behavior-test the **packaged** artifact (launch +
      real child-process spawn).
- [ ] Flight 6: **Release pipeline (CI/CD)** — GitHub Actions matrix builds the
      three installers on a release tag and publishes them to GitHub Releases;
      signing steps are present but conditional/no-op until certificates exist.
- [ ] Flight 7: **First-run UX, docs & acceptance** — first-run experience, per-OS
      install + unsigned-app-workaround documentation, replacing the remaining
      Docker-flavored runtime error messages, and end-to-end acceptance behavior
      tests on each target platform.
- [ ] Flight 8 *(optional)*: **Alignment** — hands-on session installing the real
      artifacts on real machines, tuning first-run UX, and making judgment-call
      adjustments that benefit from human feedback.
