# Flight Debrief: Native Application Window

**Date**: 2026-06-14
**Flight**: [Native Application Window](flight.md)
**Status**: completed
**Duration**: 2026-06-14 (plan + 4 legs + 2d review + land, single day)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

The flight delivered the **windowed launch path**: `the-one app` starts uvicorn
in-process on a daemon thread and opens a **chromeless native system-WebView
window** (pywebview over WebView2/WKWebView/WebKitGTK — no Chromium) at the local
URL, with port selection, **single-instance** (one the-one per port — resolving
the mission's open question), a clean shutdown that honours the lifespan drain,
and a **system-browser fallback**. The operator-directed **browser-CI cost cut**
(path-filter) landed too. `serve`/`chat`/`version` are byte-identical. All CI
lanes green; no divert criterion fired. PR #111 carries the work (ready,
stacked on #110).

### Mission Criteria Advanced

- **"Launching the app opens the agent UI in a native application window,
  falling back to the system browser…"** — the **windowed-launch capability** is
  delivered (`the-one app`). The "installed app" packaging is Flight 5; the
  rendered-window acceptance is the operator HAT / Flight 7 / the next mission's
  gated MCP.

### Checkpoints

All in-CI checkpoints met (launcher serves on the bg thread, the readiness gate,
port-selection across the three cases, the fallback path, `serve`/`chat`
unchanged, the path-filter, Linux import-safe). The **window-close graceful
drain** checkpoint is asserted at the wiring level (`should_exit`+join) but not
end-to-end through the real 9-subsystem drain — covered by uvicorn's own tests +
the operator HAT (DD6). The rendered-window checkpoint is the **operator HAT
(pending)** — the only rendered-window check this flight.

## What Went Well

- **Per-leg design review on the delicate shutdown path was the highest-value
  activity** — and again paid off by **reading the dependency source, not the
  docs**. Leg 1's review counted the lifespan drain's 9 *sequential* subsystems
  and corrected the join timeout **30s → 60s** (a real correctness fix — 30s would
  truncate the drain mid-teardown); tightened the `_graceful_shutdown` no-op
  guard to `server is None` (not `server or thread is None`, which could hide a
  bug); and steered the readiness-poll test to a trivial ASGI app (not the slow
  full app). Leg 2's review replaced a bind-probe with a **connect-probe**
  (`SO_REUSEADDR` gives a false "free" on a `TIME_WAIT` port → uvicorn would
  crash on rebind) and a **startup-retry**, and made `_webview_available` a
  **typelib-only probe** (`gi.require_version` without importing Gtk/WebKit2 —
  won't init GLib / hang headless). Phase 5b had already caught the drain-cutoff
  race and the DD4 case-b contradiction pre-implementation.
- **The NORMAL batch model fit this flight** (design per leg → batch implement →
  one 2d review → one commit) — the right contrast to F3's per-leg-push CI-gating
  cadence. Enabled by DD6: the launcher logic is fully Linux-testable with the
  window mocked, so CI was not the only authoritative check.
- **Single-module launcher (not a per-OS split like `pty.py`)** is the correct
  structure — pywebview *is* the cross-platform abstraction, so a split would add
  structure without clarity. Clean integration with the existing `serve`/lifespan
  path (programmatic `uvicorn.Server` off the main thread; `serve` keeps its
  blocking `uvicorn.run`).
- **The forced DD7 pivot landed somewhere better.** `dorny/paths-filter` failed
  on CI (lacked `pull-requests: read` AND a Node-20 action in the same
  deprecation wave we'd just fixed) → replaced with a **dependency-free inline
  `git diff`** — no permission surface, no Node-version churn, transparent
  missing-base behaviour. A net improvement.
- **Bonus positive verification:** because the flight changed `pyproject.toml`
  (the `[gui]` extra), the path-filter correctly *ran* the browser suite on
  flight/04's PR — it passed, giving real verify-integration, not just the skip
  path.

## What Could Be Improved

### Process
- **The 30s join timeout was a flight-spec design error, caught one stage late.**
  It should have been caught at Phase 5b, not Leg 1 design review — the Phase-5b
  review verified the drain *exists* and *is load-bearing* but didn't **count the
  subsystems × their worst-case ceiling** (9 × ~10s ≈ 90s). Lesson: when a join
  timeout is the mechanism for a strict *sequential* drain, the DD must spell out
  "N subsystems × M s worst-case = floor" and let that drive the number.
- **DD7 named a third-party action (`dorny/paths-filter`) that collapsed under
  CI reality.** The permission requirement is documented and the Node-20 angle
  was a known theme (we'd just bumped the other actions). The right planning
  posture — *prefer an inline git-diff over a third-party paths-filter to avoid
  permission/Node-version unknowns* — is what the fix became. **Standing lesson:
  avoid non-Anthropic-maintained Actions where a viable inline equivalent
  exists.**
- **DD1 left the `[extra]`-vs-base-`dependencies` question unresolved**, surfaced
  at Leg 1 (a `pywebview[gtk]` base dep would pull PyGObject's system-GTK build
  headers and risk breaking the Linux CI install). The flight *named* the Linux
  system-package risk but didn't draw the CI-install consequence. Lesson:
  **whenever a dep pulls system packages, resolve `[extra]` vs `dependencies` at
  the flight DD level**, not at leg time.

### Technical
- **No rendered-window CI coverage — the flight's largest open risk** (HAT
  operator-run-pending, DD6). Bounded (the rendering path is all pywebview, no
  project-owned render code; the launcher *logic* is well-covered), but a
  pywebview 5→6 API shift or the **Origin-allowlist-vs-WebView POST** risk would
  be invisible to CI until the HAT or a real user. The next mission's gated MCP
  is the durable apparatus.
- **The SIGINT browser-fallback `thread.join()` has no timeout** — asymmetric
  with the window-close path (60s). If SIGINT never arrives (SIGTERM / terminal
  close), the main thread hangs. One-line fix: `thread.join(timeout=60)`.
- **`_select_port` TOCTOU races** (connect-probe → uvicorn-bind in case a; bind-0
  release → rebind in case c) are real but low-probability (8484 is dedicated)
  and untested. Acceptable; named.
- **`_webview_available` hardcodes the WebKit2 typelib versions** (4.1/4.0/6.0) —
  a future Ubuntu LTS with a new version requires a code change, not config.
- **The inline path-filter's `fetch-depth: 0`** runs unconditionally before the
  filter decision — a full-history fetch cost on every browser job (still far
  cheaper than the Chromium install it gates).

### Documentation
- Docs (README/CLAUDE.md/agents.md) are accurate and complete; no gaps. The
  browser-CI maintenance rule is in agents.md + an inline workflow comment.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD1 base-dep → optional `[gui]` extra (lazy import; tests mock `webview`) | `pywebview[gtk]` pulls system-GTK build headers → would break the Linux CI install | **Yes** — resolve `[extra]` vs `dependencies` at the DD when a dep pulls system packages |
| Join timeout 30s → 60s | Drain is 9 sequential subsystems (~90s worst case); 30s truncates | **Yes** — DDs with a sequential-drain join must compute N×M worst-case |
| `dorny/paths-filter` → inline `git diff` | Action lacked `pull-requests: read` AND is Node-20-deprecated | **Yes** — prefer inline git-diff over third-party path-filter actions |
| Test allocation: each leg tests its own surface (vs "all tests in Leg 4") | Don't land untested code in the branch between legs | **Yes** — default for multi-leg flights with independently-verifiable outputs |
| `create_window(frameless=False)` made explicit (2d review) | Guard against a pywebview default change; test-verifiable | Lesson — assert externally-defaulted kwargs that encode a DD |
| `_select_port` connect-probe (not bind-probe) | `SO_REUSEADDR` false-"free" on TIME_WAIT | **Yes** — canonical port-free check |

## Key Learnings

- **Test-metric snapshot** (host-native): default suite **3074 passed / 10
  skipped / 589 deselected / ~314s**; launcher **17 passed / 0.88s**. No flakes.
  vs F3 (3057/10/589/~332s): exactly **+17** (the new `test_app_launcher.py`,
  platform-neutral, no markers → all default-selected; clean attribution, no
  noise). vs F1 (3065/4/576/327s): the F1 de-Docker speedup holds; wall clock
  is run-to-run variance. Pre-existing warnings unchanged (aiosqlite teardown,
  Starlette/httpx, PTY-fork); two new `websockets.legacy` warnings come from
  uvicorn (the trivial ASGI test server), not this flight's code.
- **For a sequential-drain shutdown, the join timeout is a *computed* number**
  (subsystems × ceiling), not a round guess. The 30s slip is the concrete proof.
- **Read the library source for any DD that rests on threading/lifecycle
  behaviour** — uvicorn's `capture_signals`-no-op-off-main-thread and the
  daemon-thread-join-completes-the-drain facts were verified from the installed
  library, and both Phase-5b high-severity catches depended on it. Multi-flight
  pattern now (pywinpty in F3, pywebview/uvicorn here).
- **Third-party CI actions carry hidden permission + Node-version surface**;
  inline shell equivalents are more robust for simple needs.

## Recommendations

1. **Flight 5 (packaging) — scope the Linux WebKitGTK decision as an explicit
   DD, not a discovery.** `pywebview[gtk]` needs system PyGObject + the WebKit2
   typelib (not pip-installable); WebKitGTK is **AppImage-hostile**. Package
   Linux as a `.deb`/`.rpm` with `Depends: python3-gi, gir1.2-webkit2-4.1 |
   gir1.2-webkit2-4.0`; the browser fallback is the safety net. Also: the
   installer must pull the **`[gui]` extra** (adds `pythonnet` on Win, `pyobjc`
   on mac — both have native components for the freeze chain); the Windows
   shortcut must invoke **`the-one app`** (not `the-one`→chat); and **verify
   single-instance with the packaged binary** (the `/api/info` version match vs a
   dev-mode `serve`).
2. **Flight 5/6 — the operator HAT (and the Origin-allowlist validation) is a
   release prerequisite.** Before any packaging ships to users, confirm the
   WebView POST `Origin` is accepted by `OriginAllowlistMiddleware` (or add the
   allowlist entry). F5 picks the HAT result up from this flight log.
3. **Flight 6 (release) — force a full browser run before tagging**, regardless
   of the path-filter (the full release-gated browser tier is F6's mandate;
   the path-filter means some F5 PRs may not have run it).
4. **Standardize four patterns** (project conventions / methodology): inline
   git-diff over third-party path-filter actions; design-review-reads-the-
   dependency-source for threading/lifecycle DDs; per-leg-tests-its-own-surface;
   `_select_port`'s connect-probe over a bind-probe.
5. **Quick refactor:** give the SIGINT browser-fallback `thread.join()` a 60s
   timeout (symmetric with the window-close path).

## Action Items

- [ ] Flight 5: explicit DD for Linux `.deb`/`.rpm` WebKitGTK system-dependency;
      `[gui]` extra in the installer; `the-one app` shortcut; packaged-binary
      single-instance test; carry the F3 items (run_shell tree-kill, unencoded-
      open audit, pywinpty freeze check).
- [ ] Operator HAT for the rendered window (chromeless / single-instance /
      **Origin-allowlist POST** / clean close) — run before the F6 release.
- [ ] Add `thread.join(timeout=60)` to the SIGINT browser-fallback path.
- [ ] Methodology: codify the four standardized patterns (above) + the "join
      timeout = N×M worst-case for sequential drains" DD rule.
- [ ] Flight 6: force-run the full browser suite before a release tag.

## Skill Effectiveness

- **Mission/Flight/Leg hierarchy held up well**; the 4-leg breakdown was
  correctly sized and the per-leg design reviews were again the dominant quality
  driver.
- **The `flight` skill's Phase-5b review under-specified the join-timeout math** —
  it verified the drain is load-bearing but didn't count subsystems. Recommend the
  flight-design review prompt explicitly ask "for any timeout/bound that gates a
  *sequential* process, does the number cover the worst-case sum?"
- **The `flight` skill should prompt the `[extra]`-vs-base-dep decision at DD
  time** for any dependency that pulls system packages (the DD1 ambiguity).
- **`/agentic-workflow`'s normal batch model worked cleanly here** — the contrast
  with F3's CI-gated cadence confirms the archetype distinction the F3 debrief
  recommended: *normal batch when the implementer can verify locally; per-leg-push
  when CI is the only authoritative check.* Both archetypes have now been
  exercised; the skill should name them.
- **DD6 (light verification, deferred rendered-window apparatus) was correctly
  weighted** given the operator's stated next-mission MCP UI-testing apparatus —
  avoided premature Xvfb+WebKitGTK CI infrastructure against a surface that will
  be superseded.

---

## Follow-up — Cross-Flight Note (added 2026-06-15, from the F5 debrief)

**A latent F4 design omission surfaced in F5: the native window did not persist web
storage.** Flight 5 (Windows packaging) produced the first *persistent installed
binary*, and an operator HAT found that the **theme preference reset on every app
restart/reinstall**. Root cause traces to **this flight (F4)**, DD3: the
`webview.start()` call introduced here was invoked with no arguments, so pywebview's
**default `private_mode=True`** applied — an *ephemeral* profile that discards
`localStorage`/cookies between launches. It didn't surface in F4 because F4 was
verified from a source checkout, where the browser's own profile persists
`localStorage` across process restarts; only a frozen, installed, relaunched binary
exposes the ephemeral-profile behavior.

- **Fix (landed in F5, commit `9dbe8a2`):** `webview.start(private_mode=False,
  storage_path=str(settings.data_dir / "webview"))` — a persistent per-user webview
  profile under the platformdirs data dir (outside the install dir, migrated with
  other user data), so storage survives restart *and* reinstall. A launcher test now
  asserts the persistence config.
- **Lesson for future window/webview work (carry into F6/F7 and any `webview.start()`
  change):** the `private_mode`/`storage_path` choice is a **first-class decision**,
  not a default to accept implicitly — pywebview's privacy-first default is the wrong
  one for a desktop app that must remember user settings. The rendered-window behavior
  that DD6 deferred (no CI apparatus) is exactly where this hid; it reinforces the F5
  recommendation to author a **Witnessed GUI behavior test** (theme-persists-across-
  restart is one of its steps) before F6/F7 inherit this code.
