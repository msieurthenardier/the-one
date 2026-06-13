# Flight Debrief: Windows PTY Parity (ConPTY)

**Date**: 2026-06-14
**Flight**: [Windows PTY Parity (ConPTY)](flight.md)
**Status**: landed
**Duration**: 2026-06-13 (plan + Legs 1–3) → 2026-06-14 (Legs 4–5, land, PR #110 ready)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The flight achieved its objective and its **enabling consequence**: `the_one` now
**imports and runs on Windows for the first time** (Leg 1 unblocked the
`pty.py` import cascade that previously made the web app and CLI un-importable on
`nt`), and `WindowsPtySession` (ConPTY via `pywinpty`) brings the interactive
`shell_session_*` tools to functional parity on Windows — **verified 7/7 on the
`windows-2022` lane**. The Win32 Job Object teardown (`KILL_ON_JOB_CLOSE`) is in
place (code correct-by-construction; the definitive tree-reap *proof* deferred —
see below). A mid-flight operator pivot turned the Windows CI lane into a
**curated platform-relevant subset**, cutting it ~25 min → ~42 s. All 5 legs
landed; no divert criterion fired. PR #110 carries the work and is ready for
review.

### Mission Criteria Advanced

- **"Interactive PTY tools at feature parity on all three platforms, including
  Windows (behavior-test-backed)"** — Windows functional parity delivered and
  CI-verified. The **behavior-test backing is deferred** to post-installer
  acceptance (Flight 7/8) per operator decision (a real installer is a stronger
  apparatus than a pip-dev-install; mirrors how Flight 2 macOS defers its
  behavior test). Spec authored + ready: `tests/behavior/windows-pty-parity.md`.
- **"Tested without Docker; suite passes in CI"** — extended to Windows: the
  curated `windows-2022` lane is green and runs on every PR. (Linux keeps the
  full suite as source of truth.)

### Checkpoints

All flight checkpoints met. The load-bearing premise (the app/CLI import cascade
un-importable on Windows) was confirmed empirically in Leg-1 CI before later legs
built on it. The one empirical open question (DD-OQ orphan reap) is resolved at
the *code* level (Job Object correct-by-construction; round-trip 7/7) with the
*observable* tree-reap proof deferred to the behavior test.

## What Went Well

- **Design reviews repeatedly paid for themselves — by reading the dependency
  source, not by running code.** The standout process win. Leg 2's review read
  pywinpty's source and caught that the planned `read_blocking`-after-spawn idle
  read is a **no-op** (the daemon thread captures the flag at construction) —
  correcting it to the socket-timeout mechanism *before* implementation. Leg 3's
  review caught the two classic blind-ctypes traps (`c_ulong` is 8 bytes on
  Linux / 4 on Windows → use `wintypes.DWORD`; `HANDLE` must be `c_void_p` or it
  truncates on x64). Each would have cost multiple **25-minute** CI round-trips
  to discover empirically.
- **"Pull the real CI message before fixing" overturned wrong diagnoses.** In
  Leg 4 the reviewer proposed parametrizing `test_timeout_returns_promptly`'s
  command — but the actual CI message was `kill+reap blocked: 5.03s`, not
  "command not found": `sleep` *ran*; the gap was the **`run_shell` Windows
  tree-kill**. The name-based fix would have been wrong. The same discipline
  corrected the tilde failures (a `USERPROFILE`-not-`HOME` setup issue, not a
  hardcoded assertion) and the Leg-3 orphan failure (a quoting-through-PTY
  harness bug, not a Job Object failure).
- **Split-module architecture (DD2) is a clean, extensible improvement.**
  `pty.py` (neutral ABC + dispatcher + shared constants) / `pty_unix.py` /
  `pty_windows.py` made the platform surfaces fully disjoint at the module
  boundary and sets Flight 2 macOS up to slot in with an `elif sys.platform ==
  "darwin"` branch and zero consumer/ABC changes.
- **The DD7 curation delivered a large, measured cost win** (~25 min → ~42 s
  Windows; ~80%) on a ~14% platform-relevant subset — and the *original* DD7
  full-suite gate is what produced the failure inventory that justified the
  revision. Good risk structure, then a good cost adaptation.
- **Honest tracking of every gap.** The `run_shell` tree-kill gap, the
  orphan-reap CI-harness flakiness (xfailed, deferred), and the deferred
  encoding audit are all recorded in mission Known Issues / the flight log with
  forward-pointers — nothing swept under green.
- **Per-leg-push CI-gating cadence** (a deliberate deviation from the skill's
  batch model) made CI the load-bearing oracle work: each Windows-relevant leg
  was pushed so its `windows-2022` result scoped the next.
- **Node-20→24 actions deprecation** handled cleanly mid-flight (verified each
  target declares `runs.using: node24` before pinning; separate labeled commit).

## What Could Be Improved

### Process
- **DD3's `read_blocking` mistake was a *planning* miss, not a "can't-test-on-
  Linux" discovery.** The correct mechanism was discoverable at planning time by
  reading pywinpty's `PtyProcess.__init__`/daemon-thread source — the "can't run
  it on Linux" constraint blocked *empirical* discovery, not *source reading*.
  Lesson: **design-review-reads-the-dependency-source** should be a pre-flight
  discipline for platform-backend flights, not just a lucky catch at review.
- **A test mechanism that quotes through multiple shell layers should mandate
  the filesystem-mediated approach from the spec.** Leg 3's orphan test used an
  inline `start /b "" python -c "<one-liner>"` sent through cmd.exe-through-PTY;
  the quoting/backslash fragility was flagged "possible" but not "high-risk," and
  it failed twice (inline, then temp-.py with the PID still not written). Specs
  that drive a subprocess to report back through a PTY should mandate a temp
  `.py` file launched via `"{exe}" "{script}"` (both quoted) from the start.
- **The skill's agentic-workflow has no built-in archetype for "CI-gated legs."**
  When the implementing agent can't run the authoritative verification locally,
  the default "batch all legs → one commit" model is actively wrong (it scopes
  legs blind to CI). The per-leg-push adaptation worked but had to be invented
  and justified mid-flight.

### Technical
- **Curated-CI file-list maintenance debt.** The `test.yml` windows job is a hand
  list with a `MAINTENANCE NOTE`; a new platform-divergent test file silently
  misses Windows coverage unless added. The idiomatic fix (a `cross_platform`
  pytest marker, matching the project's marker convention) was deferred for
  scope — it's the most actionable debt from this flight.
- **`run_shell` (non-PTY) Windows tree-kill gap.** `shell.py` falls to bare
  `proc.kill()` on Windows; a timeout kills cmd.exe but leaves its child tree
  running. Surfaced by CI, documented (SECURITY-MODEL/agents/CLAUDE/Known
  Issues). Fix: `taskkill /F /T /PID` or a Job Object mirroring the PTY backend.
- **DD-OQ orphan reap is empirically unproven at the reap-assertion level.** Code
  is correct-by-construction and the lifecycle (start/close) runs clean (7/7);
  but both reap tests are `xfail` (CI harness can't reliably exercise them). The
  definitive proof genuinely rides the deferred behavior test on the installer.
- **ABC `close()` docstring is Unix-specific** ("SIGKILL-fast on bwrap-wrapped…")
  — now wrong for the Windows backend and will be wrong for macOS. Documentation
  debt: abstract the ABC docstring to the *contract* (idempotent; ensures the
  process tree is gone), not the Unix *mechanism*. (Flight 2 should fix this.)

### Documentation
- **`agents.md` "Sandbox testing footguns" needs a fourth entry:** test-side
  ctypes calls also need explicit `argtypes`/`restype` — a bare
  `windll.kernel32.OpenProcess` truncates the 64-bit HANDLE and makes the
  liveness assertion unreliable (the `_typed_kernel32()` helper is the pattern).
- **The behavior spec deserves a one-line run-context note** (run in Flight 7/8
  on the real installer; what its DD-OQ resolution means) for the next reader.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD3 `read_blocking` idle read → socket-timeout (`fileobj.settimeout`+`recv`+catch `socket.timeout`) | Planned mechanism is a no-op after spawn (daemon-thread closure) | **Yes** — design-review-reads-the-dependency-source for platform bindings |
| DD7 full Windows suite → curated platform subset | Operator CI-cost pressure; 86% of tests are platform-agnostic | **Yes** — apply curation to the macOS lane (10× billing) from day one |
| Per-leg review→commit→push vs the skill's batch model | CI is the only authoritative Windows check; leg scoping depends on CI output | **Yes** — name "CI-gated platform flight" as an archetype in the methodology |
| Reviewer's fix overridden by the real CI message (`kill+reap blocked` ≠ "not found") | Diagnosing from test names is unreliable for remote-CI failures | **Yes** — pull the verbatim CI failure message before designing the fix |
| Both orphan-reap tests `xfail(strict=False)` + behavior-test deferral | CI harness can't reliably launch the grandchild-through-PTY; code is correct-by-construction | **Yes** — honest `xfail` naming the harness limit + where the proof comes from beats a skip or false-green |
| Inline `-c` → temp `.py` for the orphan grandchild | Quoting through cmd.exe→PTY mangled the launch | Lesson: mandate temp-file-mediated subprocess comms through a PTY in the spec |
| FD issued host-native test commands directly, overriding the crew file's stale `docker exec` | Crew file predates F1 de-Dockerization | No — narrow; the crew file is project-owned, the per-spawn override is the SKILL.md protocol |

## Key Learnings

- **Test-metric snapshot** (seeds future comparisons): default suite **3057
  passed / 10 skipped / 589 deselected / ~332s** (host-native); bwrap **41
  passed** (was 31 — the Leg-1 `@requires_bwrap` re-mark made ~10 previously
  invisible tests selectable, closing an F1 action item); **NEW curated
  `windows-2022` lane: 398 passed / 12 skipped / 2 xfailed / ~42s** (vs the
  ~25-min / ~3050-test full-suite Leg-1 baseline). Default-suite deltas vs F1
  (3065/4/576/327s) are fully attributable: the bwrap re-mark moved ~10 tests
  skip→deselect (+13 deselect), and the new nt-gated `test_pty_windows.py` (9) +
  `test_pty_dispatch.py` Windows case add to the Linux skip bucket (+6). Wall
  clock essentially flat (+5s).
- **For a platform you can't run locally, CI is the oracle and source-reading is
  the cheap insurance.** The two highest-cost-avoided bugs (read mechanism,
  ctypes structs) were caught by reading pywinpty/Win32 docs+source at review,
  not by burning CI cycles.
- **A behavior test can double as a deferred empirical proof.** The Windows PTY
  behavior spec's orphan-reap rows (`tasklist` after close + parent-death) are
  the *definitive* DD-OQ resolution — better run on the real installer than a
  dev-install, so deferring it strengthens rather than weakens the evidence.
- **Curating per-platform CI by the OS-divergent subset is the dominant
  CI-minutes lever** — far more than deleting overlapping tests (which only saves
  cheap Linux minutes). ~86% of the suite gave ~zero Windows signal.

## Recommendations

1. **Apply DD7 curation to Flight 2 (macOS) from day one.** macOS runners bill at
   **10×**; do NOT run the full suite. Build the curated platform-relevant list at
   flight-design time (reuse the `test.yml` list + a `pty_macos` entry), and
   pre-register "pull real CI messages before fixing" in the FD notes.
2. **Flight 5 (packaging) must explicitly scope three carried items** (not as
   discovery): (a) the **unencoded-`open()`/`read_text()` product audit**
   (`grep -rn "open(\|read_text(\|write_text(" the_one/ | grep -v encoding`) — a
   `UnicodeDecodeError` in a frozen, console-less Windows app is a silent
   failure; (b) the **pywinpty native-binary freeze check** (ABI-specific `.pyd`
   + DLL must be collected; test an actual freeze early); (c) the **`run_shell`
   Windows tree-kill fix** (`taskkill /F /T` or a Job Object).
3. **Adopt a `cross_platform` pytest marker** to replace the curated file list (a
   small maintenance leg): register in `pyproject.toml::markers`, annotate the
   OS-divergent files, run the per-platform jobs with `-m "cross_platform and not
   requires_bwrap and not browser and not live and not pixel and not discord_hat"`.
4. **Standardize the three process patterns in the methodology** (skill-level):
   *CI-gated platform flight* archetype (per-leg-push cadence), *pull-the-real-
   CI-message-before-fixing*, and *design-review-reads-the-dependency-source*.
5. **Run the `windows-pty-parity` behavior test during Flight 7/8** on the real
   installer — it closes the DD-OQ orphan-reap proof and the mission's
   behavior-test-backed PTY criterion.

## Action Items

- [ ] Flight 2 macOS dust-off: curate its CI lane (DD9) from day one; read the
      chosen macOS PTY/Seatbelt binding's source before leg design.
- [ ] Flight 5: scope the unencoded-open audit, the pywinpty freeze check, and
      the `run_shell` Windows tree-kill fix as explicit legs/criteria.
- [ ] Maintenance: adopt the `cross_platform` marker (retire the `test.yml`
      hand list).
- [ ] `agents.md`: add the 4th sandbox-testing footgun (test-side ctypes
      argtypes / HANDLE truncation; reference `_typed_kernel32()`).
- [ ] Abstract the `PtySession.close()` ABC docstring to the contract, not the
      Unix mechanism (do in Flight 2 when macOS makes it a 3rd backend).
- [ ] Run `/behavior-test windows-pty-parity` on the real Windows installer
      (Flight 7/8) — definitive DD-OQ proof; record the run log.
- [ ] Opportunistic: fix `test_provider_repository::test_update_changes_fields`
      coarse-clock timestamp fragility (`>=` or injected clock) if touched.

## Skill Effectiveness

- **Mission / Flight / Leg hierarchy held up well.** The flight's DD framing
  (esp. elevating the import-cascade "enabling" fact) gave execution a clear
  spine, and the leg breakdown (5 legs; Leg 1 as a *gate*) was correctly sized —
  the failure inventory fit comfortably in Leg 4.
- **The `flight`/`leg` skills' design-review loops were the dominant quality
  driver** and should be reinforced; the highest-value catches came from
  reviewers reading dependency source, which the prompts could explicitly request
  for platform-binding work.
- **Gap: `/agentic-workflow` lacks a "CI-gated leg" execution archetype.** Its
  default "batch all autonomous legs → one commit, single review" model assumes
  the implementer can verify locally. For a platform the agent can't run, CI is
  the oracle and per-leg push is required. Recommend the skill recognize this
  archetype (and the per-leg-push cadence) explicitly rather than leaving it to
  FD improvisation.
- **DD8 (behavior-test-backed, deferrable) worked as designed** — the criterion
  was satisfiable via an authored-spec-now / operator-run-later disposition,
  which the mid-flight installer-timing decision exercised cleanly.
