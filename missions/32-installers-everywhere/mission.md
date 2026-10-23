# Mission: GleepGlorp AI installs like an app on Windows, macOS and Linux

**Status**: active

## Outcome
Someone on macOS or Linux can download GleepGlorp AI, install it the way they install any other app on their system, and open it in its own window. They need no Python, no command line and no compiler, and on Linux no manual system-package step. Windows keeps the experience it has today. All three installers come from one packaging approach kept in the repository, and a tagged release publishes all three together. The operator, who is on Windows and has no Mac, can ship a macOS build with confidence because the build itself proves the app's frozen-runtime diagnostic passes. Contributors with Macs then confirm on real hardware that it works.

## Context
- **Today only Windows has an installer.** PyInstaller freezes the app into a one-folder bundle (`packaging/windows/the-one.spec`, with two exes: the CLI and the windowed launcher), and Inno Setup (`packaging/windows/the-one.iss`) wraps that folder in the installer. It is built on the local Concourse Windows worker on every push to `main` (published to the local MinIO bucket, `ci/windows-installer.pipeline.yml`), and on GitHub Actions `windows-2022` for `v*` tags (the official release, `.github/workflows/windows-installer.yml`, gated by a release-closure `pip-audit`).
- **macOS and Linux users install from source** (README "Install"): `pip install -e ".[all-llms,gui]"`. On Linux the `gui` extra builds PyGObject and pycairo from source (distro dev packages needed first), and the WebKitGTK typelib needs `sudo apt install gir1.2-webkit2-4.1`. Without it, `the-one app` falls back to the browser on Linux. This manual step is the most visible unfinished part of the packaging.
- **The backlog seed** (`BACKLOG.md`, "Packaging consolidation: evaluate Briefcase + close the cross-platform installer gap", 2026-06-20) is this mission's starting point. It proposes:
  - evaluating one tool for all three platforms (BeeWare Briefcase as the candidate), with a hybrid an acceptable outcome;
  - building Linux on the free Concourse Linux workers (superseded by the operator's build topology below: Linux builds on GitHub, release only);
  - reserving hosted GitHub runners for what they alone can build (macOS), and only on demand or a release tag;
  - making `the-one doctor` passing inside the new bundle the go/no-go gate.
- **The sibling project `goldfinch`** ships an unsigned macOS `.dmg` (`identity: null`) plus Linux AppImage and `.deb` from a tag-triggered GitHub build. It is the precedent for unsigned macOS distribution here.
- **The frozen-runtime seam is Python-inherent** and must survive any bundler. It lives in `the_one/platform/env.py`:
  - `is_frozen`, `clean_subprocess_env`, `resolve_python`, and bundle-dir stripping on `PATH`;
  - the `THE_ONE_PYTHON` and `THE_ONE_EXTRA_PATH` overrides;
  - `.env` anchored to the per-user data dir when frozen.

  `the-one doctor` (twelve gates) is its end-to-end proof. The seam's bundle-dir detection assumes PyInstaller's layout (`sys._MEIPASS`, or the directory holding the exe). A macOS `.app` bundle or a different freezer lays files out differently.
- **Desktop window facts that differ by platform:**
  - **Window backends:** `pywebview` uses WebView2 on Windows, WKWebView on macOS and WebKitGTK on Linux.
  - **The tray:** it runs `pystray` through `run_detached()` beside a `pywebview` main loop that holds the main thread. On macOS, AppKit wants both on the main thread, so close-to-tray as built may not carry over.
  - **Window chrome:** the tinted title bar (M25 F5) is Windows 11 only.
  - **Sandboxing:** boxed execution is Linux-only (bubblewrap); macOS, like Windows, runs unsandboxed (`PassthroughSandbox`). A packaged Linux build must still reach a working `bwrap` (the host's), or degrade the way the source install does.
- **The operator's decisions (2026-10-23):**
  - No Mac is available to the operator. Contributors with Macs will test, as one "does this work?" check at the end rather than iteratively.
  - Unsigned builds are acceptable for now, on macOS as on Windows. On Apple Silicon this means ad-hoc signed (`codesign -s -`, no Apple account), the only form arm64 macOS will run.
  - Linux "basics" means a portable single-file app (AppImage) and a Debian package (`.deb`), targeting Ubuntu 26.04 LTS and Debian 13 on x86-64.
  - The AppImage uses the WebKitGTK the desktop already has, rather than bundling its own. The `.deb` declares it as a dependency.
  - On a Linux desktop with no tray, closing the window keeps the app running hidden, and launching it again brings the window back.
  - The Windows installer may change toolchain; the operator is its only user. There is no default going in: the Flight 1 spike compares the options and the operator chooses from the evidence.
  - On macOS, native Mac window behaviour is an acceptable stand-in for close-to-tray.
  - No alignment flight.
  - **Build topology:** the Windows installer keeps its per-push Concourse build for incremental work. The macOS and Linux packages build on GitHub Actions only, on a `v*` release tag, never on every push. During development (and while Mission 31 forbids a release) they build on a manually started GitHub run, and Linux packages can also be built and checked locally on the dev host.
- **Architect review (2026-10-23): feasible with caveats.** The risks that shape the plan:
  - **The macOS window lifecycle is the largest code change.** The desktop shell has no darwin branch. `pystray`'s detached mode is fragile on macOS, and Dock reopen, Cmd-Q and window-close handling likely need PyObjC reach into `pywebview`'s Cocoa delegate. None of this can be debugged interactively, so it is built as an explicit, unit-tested desktop-session mode early, not at the end.
  - **A hosted macOS runner proves `doctor` and a `serve` start, not the window.** A GUI window and Dock behaviour cannot be reliably asserted there, so those are contributor-verified.
  - **macOS first-run hazards:** `/usr/bin/python3` on a fresh Mac is the Xcode command-line-tools stub, which opens an install dialog, so `resolve_python()` and the doctor gate must not trip it. A GUI-launched `.app` gets launchd's minimal `PATH` (the seam's augment list already includes `/opt/homebrew/bin` and `/usr/local/bin`). On macOS 15 and later, right-click Open no longer bypasses Gatekeeper; the user approves through System Settings, Privacy & Security, Open Anyway.
  - **Native wheels on macOS arm64** (vector store, tokenizer and file-watcher dependencies) are unverified. A gap costs a hosted-runner iteration, so the spike checks the lock's arm64 coverage and runs one macOS build.
  - **Linux:** a frozen app must still load GObject introspection and the host's WebKitGTK typelib (a libgirepository ABI question). Ubuntu restricts unprivileged user namespaces through AppArmor, which can stop the host's `bwrap` from working in a packaged app; the sandbox then falls back to passthrough, and that must be visible in `doctor` and the guide, not hidden.
  - **Windows:** a different installer technology (MSI) cannot upgrade an Inno Setup install in place, and loses its AppId and Restart Manager handling, so a toolchain change on Windows carries a migration cost the spike must price.
- **Concurrency:** Mission 31 is active on its own branch, and its charter says no release is cut while it is active. This mission plans and builds in its own worktree.

## Success Criteria
- [ ] **Linux install, no setup.** On a stock Ubuntu 26.04 LTS and a stock Debian 13 desktop (x86-64), a user installs GleepGlorp AI either as a downloaded single-file portable app or as a Debian package through the system package manager. Neither path needs Python, a compiler, a terminal or a manual system-package step (the Debian package pulls in what it needs; the portable app uses the desktop's own WebKitGTK and, if it is missing, says so plainly and opens in the browser instead). The app appears in the desktop's application menu with the brand icon, and opens in its own window. *(Behavior-test-backed: fresh-VM install of each package on each distro.)*
- [ ] **macOS install, without an Apple developer account.** On a recent macOS on Apple Silicon, a user opens a downloaded disk image, drags GleepGlorp AI to Applications, approves the app once through the steps in the install guide (correct for the macOS versions it names), and it opens in its own window with the brand icon in the Dock. *(Behavior-test-backed: run by a contributor on a real Mac at mission close.)*
- [ ] **The frozen runtime works in every build.** `the-one doctor` passes from inside each installed build on Windows, macOS and Linux: it spawns a real Python child, finds `node`/`uv`/`python` on the user's PATH, and its other gates pass or skip for the platform's documented reason. The macOS build proves this on the build machine before any contributor runs it, so a failed seam fails the build, not the contributor's test. On macOS the build proves `doctor` and a server start; the window itself is contributor-verified.
- [ ] **The window behaves like a native app on each platform.** On Windows and Linux with a tray, closing the window hides it to the tray and Quit exits. On a Linux desktop with no tray, closing the window keeps the app running hidden, and launching it again brings the window back. On macOS, closing the window keeps the app running in the Dock, clicking the Dock icon brings it back, and Quit (app menu or Cmd-Q) exits cleanly. On every platform, a second launch brings the running window forward instead of opening a second app, and the window's size and position are remembered. *(Windows and Linux: build- and test-proven. macOS: unit-tested in code, confirmed by the contributor check.)*
- [ ] **Upgrades keep the user's data.** Installing a newer build over an older one, on each platform, keeps chats, agents, providers, stored secrets and the local-API credential. Uninstalling removes the app and leaves the user's data, and the install guides say where that data lives and how to remove it. An existing Windows install upgrades in place to the new installer with no manual uninstall, or, if a toolchain change makes that impossible, the one-time step is automated or documented in the installer's own flow.
- [ ] **Windows does not regress.** The installed Windows app still passes its existing checks: the windowed launcher, the CLI, `doctor`, close-to-tray, single-instance focus, and the tinted Windows 11 title bar. The operator's per-push local CI build of the Windows installer keeps working.
- [ ] **One packaging source of truth, built within the CI budget.** Product name, version, identifier and icon are defined once and feed every platform's installer (including any installer script with its own defines, such as the Inno Setup `.iss`), so a version bump or rename is one edit. The Windows installer keeps building on the local CI on every push to `main`. The macOS and Linux packages build on hosted runners only on a release tag or a manually started run, and no per-push hosted build is added.
- [ ] **A release ships all three.** A `v*` tag publishes the Windows installer, the macOS disk image, and both Linux packages to the GitHub releases page in one run, gated by the existing release-closure dependency audit, so a finding stops the release before any build time is spent.
- [ ] **Install guides for every platform.** README "Install" and an install guide per platform (beside `docs/windows-install.md`) cover downloading, installing, the unsigned-app approval on macOS, where data lives, upgrading, and uninstalling. The manual WebKitGTK `apt` step is gone from the guides for packaged installs (it stays for source installs only).
- [ ] **Existing gates pass.** Unit, browser (every lane) and lint gates pass. Packaging code stays out of `the_one/` imports, as `packaging/windows/` is today.

## Stakeholders
- **Operator** (sole maintainer, daily Windows user): wants GleepGlorp AI to be a real app on every platform, built cheaply from one recipe, without breaking the Windows install used every day.
- **macOS contributors**: get a disk image they can install with no Python setup, and run the end-of-mission check on real hardware.
- **Linux users**: install from a package and stop compiling PyGObject or running `apt` by hand.
- **Future crews**: maintain one packaging contract instead of a different recipe per platform.

## Constraints
- **No paid signing.** No Apple Developer account and no Windows code-signing certificate. macOS builds are ad-hoc signed (required for arm64 to run them) and not notarized; Windows stays unsigned. Keep an inert signing/notarization hook ready (as the `.iss` has today).
- **Hosted CI minutes are scarce.** No per-push GitHub Actions builds. Windows builds on the local Concourse Windows worker on every push, as today. macOS and Linux build on GitHub-hosted runners (Apple Silicon Mac, Ubuntu) on a `v*` tag or `workflow_dispatch` only. Each macOS run costs the most minutes, so a flight plans its macOS runs rather than iterating on them; Linux iteration happens locally on the dev host before a hosted run.
- **No Mac in the loop until the end.** The operator cannot run or debug a macOS build interactively. Everything provable without a human (bundle contents, `doctor` inside the built app, a headless launch smoke on the runner) is proven by the build itself. The contributor check is a confirmation, not a debugging session. Anything that needs a human eye on macOS is gathered into one written checklist they run once.
- **No release while Mission 31 is active.** Mission 31's charter forbids cutting a release during it. Until Mission 31 closes, this mission proves the release path with manually started builds (downloadable build artifacts, or a draft or pre-release that the operator controls). The first real three-platform `v*` release happens only after Mission 31 closes, and only with the operator's go.
- **The frozen-runtime seam stays one implementation.** It lives in `platform/env.py`. Bundle-layout differences (a macOS `.app`, a new freezer, AppImage's mount) are handled there behind `is_frozen()` and the bundle-dir detection, never re-implemented per call site.
- **User data location does not change.** The per-user data dir is derived from the `the-one` slug through `platformdirs` and must stay where it is on every platform, so upgrades and existing Windows installs keep their data. A display-name cleanup ("GleepGlorp AI" for everything a user sees) must not move it.
- **Packaging stays outside the app.** Recipes and build helpers live under `packaging/` (and `ci/`, `.github/`); nothing under `the_one/` imports them. Build-only tools stay out of the app's runtime dependencies.
- **Scope limits:**
  - x86-64 Linux and Apple Silicon macOS only. Intel Macs, Linux arm64, Flatpak, Snap, distro repositories and auto-update are out of scope.
  - The source install keeps working as documented today.
- **Shared files with Mission 31.** `CLAUDE.md`, `the_one/agents.md`, `README.md`, `ci/README.md`, `pyproject.toml` and `uv.lock` are touched by both missions. Keep edits there additive and in their own sections, and rebase on `main` when Mission 31 merges.

## Environment Requirements
- **Dev host:** Linux/WSL2 (this repo's host). Linux packages can be built and smoke-tested locally during development. A clean Ubuntu LTS and Debian stable desktop environment (VM or container with a display) is needed for install checks.
- **Concourse** (local, on the operator's Windows PC through Docker): the Windows worker keeps the per-push Windows installer build.
- **GitHub Actions:** a hosted macOS runner (Apple Silicon) and a hosted Ubuntu runner for the macOS and Linux packages, started by hand or by a `v*` tag; `windows-2022` stays the official Windows release runner unless the flight moves it.
- **Native Windows:** the existing Windows worker or the operator's desktop (`scripts/windows_test_copy.py`) for Windows installer checks.
- **Real Macs:** contributor-owned, for the single end-of-mission behavior test.

## Open Questions
- **Which toolchain?** One tool for all three (Briefcase), PyInstaller extended to macOS and Linux with per-platform wrappers (a `.app`/`.dmg` and AppImage/`.deb`), or a hybrid. No default: the Flight 1 spike compares them on the load-bearing pieces, which are `doctor` in the bundle, the `pywebview` backend, the tray, native dependencies (`pywinpty` on Windows, arm64 wheels on macOS), the cost of each in maintenance, and the upgrade path from the existing Inno Setup install. The operator chooses.
- **macOS tray:** can `pystray` and `pywebview` share AppKit's main thread (a menu-bar icon as a bonus), or does macOS use native Dock behaviour only (the agreed fallback)? How much PyObjC reach into `pywebview` does Dock reopen need?
- **macOS headless proof on the runner:** how much of the window launch can be smoke-tested on a hosted runner (no logged-in GUI session guarantee) beyond `doctor` and a `serve` start?
- **The CLI on macOS and Linux:** how does a user reach `the-one` from a terminal for `doctor` and other subcommands? The `.deb` can put it on `PATH`; on macOS (a drag-install disk image has no install script) a documented path inside the `.app` is the likely answer.
- **Side-by-side Linux installs:** the AppImage and the `.deb` share the data dir and port. Single-instance focus should treat them as one app; confirm and document.
- **The macOS runner budget:** roughly how many hosted runs each flight plans for (the Architect estimates three to six across the mission).
- **Windows upgrade path** if the toolchain changes: can a new installer replace an Inno Setup install in place (same AppId semantics, or an uninstall-first step), and does close-to-tray still get Restart Manager handling?
- **Release vehicle during Mission 31:** build artifacts on a dispatched run, or a draft or pre-release on GitHub?

## Known Issues
_(none yet)_

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [ ] **Flight 1: Choose the packaging toolchain.**
  - A spike, ending in the operator's go/no-go: build the app with each candidate (Briefcase; PyInstaller extended with per-platform wrappers) on Linux, the cheapest platform to validate, and compare `doctor` inside the bundle, the window, the tray, and an upgrade over an older build.
  - One hosted macOS run per serious candidate, building a `doctor`-only bundle, retires the arm64 wheel and frozen-seam risks before Flight 3 depends on them.
  - Price the Windows side of each option: the in-place upgrade from the current Inno Setup install, `pywinpty`, WebView2, the tray and Restart Manager.
  - Output: a recorded decision (one tool, or a named hybrid) with its evidence. No shipped packages.
- [ ] **Flight 2: Linux packages.**
  - The AppImage and `.deb` on the chosen recipe, built locally during development and on a GitHub-hosted runner on a release tag or a manual run.
  - One source of product metadata, the data-dir invariant, the frozen-seam adjustments for the bundle layout, and the sandbox fallback made visible.
  - Fresh-VM install, upgrade and uninstall checks on Ubuntu 26.04 and Debian 13, and the Linux install guide.
- [ ] **Flight 3: macOS app.**
  - Starts with the macOS desktop-session mode (native Dock behaviour in place of close-to-tray, single instance, Cmd-Q), unit-tested, because it cannot be iterated on cheaply.
  - The ad-hoc signed `.app` and `.dmg`, built on a hosted Mac runner by hand.
  - The frozen seam on the `.app` layout, proven by `doctor` and a server start inside the built app on the runner.
  - The macOS install guide with the Gatekeeper approval steps, and the written contributor checklist.
- [ ] **Flight 4: Windows on the chosen recipe, and one release path.**
  - Windows moves to the chosen recipe, or keeps PyInstaller and Inno with shared metadata if Flight 1 chose a hybrid. Prove in-place upgrade from the current install and the existing Windows checks, without breaking the per-push Concourse build.
  - Wire the tag-triggered release to publish all four packages behind the dependency audit, dry-run it through a manual run while Mission 31 is active, and update README and CLAUDE.md.
  - Mission close: the contributors' end-to-end check on real Macs.
