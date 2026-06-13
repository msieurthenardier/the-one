# Flight: macOS Sandbox Backend (Seatbelt)

**Status**: planning (**PARKED** 2026-06-13 — see Parking Note)
**Mission**: [Native Desktop Installers](../../mission.md)

> ## Parking Note (2026-06-13)
>
> **Parked in favor of Windows PTY parity (now Flight 3, executed first).**
> Rationale: the operator runs WSL2 on a native Windows host, so the Windows
> flight has a *local* test apparatus (hands-on interactive testing + operator
> can run the behavior test himself) where this flight has none (no macOS
> hardware; behavior-test backing already deferred to Flight 8). Plus cost:
> macOS GitHub runners bill at **10×** on private repos vs. Windows **2×**,
> and a from-scratch backend flight is iterate-heavy. No dependency blocks the
> swap — both backends slot behind the M14 seam independently. This spec is
> complete and twice-design-reviewed; it resumes after the Windows flight.
>
> **Two ride-alongs migrated OUT of this flight's Leg 1** into the Windows
> flight, because their F1-debrief deadline is "before the CI matrix expands"
> — and the Windows matrix now expands first: (1) re-mark the ~12
> `skipif(which("bwrap"))` integration tests as `@requires_bwrap`; (2) the
> `mcp/__init__` eager-load-cycle guard comments. When this flight resumes,
> Leg 1 no longer owns them (verify they were done by the Windows flight).
>
> **Dust-off checklist when resuming:**
> - Re-verify the pinned `macos-15` runner image still exists / is still the
>   right pin (image deprecation cadence).
> - Re-check macOS runner pricing (the 10× multiplier and DD9's cost note).
> - Re-run recon on the DD5/DD6/DD7 couplings (`_seam.py:33`,
>   `stdio.py:479/:599`, `pty.py:294/:327-328/:587`): the Windows flight will
>   touch `pty.py` and the seam, and **may have already landed the DD5
>   capability-attribute refactor** (it's platform-independent) — if so, this
>   flight's Leg 4 scope shrinks accordingly.
> - Confirm the `requires_seatbelt` marker isn't already registered (Leg 1
>   was to add it; check it didn't land early).

## Contributing to Criteria

- [ ] Sandbox enforcement (from the Mission-14 boundary) is now active on **macOS**
      as well as Linux *(CI-containment-backed this flight; the criterion's
      behavior-test backing is formally deferred to Flight 8 — see DD8)*
- [ ] The app builds, runs, and is tested entirely without Docker; the existing
      test suite passes host-natively in CI *(extended to macOS: the full default
      suite becomes a required `macos-latest` job)*

---

## Pre-Flight

### Objective

Implement the macOS Seatbelt backend behind the Mission-14 `ToolSandbox` seam so
tool, PTY, and MCP stdio spawns are kernel-sandboxed on macOS exactly as they are
on Linux: a `SeatbeltSandbox` that compiles `SandboxProfile` into a generated SBPL
policy and wraps spawns with `/usr/bin/sandbox-exec`; a `darwin` branch in the
selection factory with an empirical capability probe; boxed-mode (`minimal_rootfs`)
semantics mapped to deny-default SBPL; and a `macos-latest` CI lane that both
kernel-verifies containment (`@requires_seatbelt`) and runs the full default suite
as a required job. No call-site changes — the backend slots in by satisfying the
Protocol (the M14 design promise this flight cashes in).

### Open Questions

- [x] sandbox-runtime as dependency vs. reference → **resolved, DD1**
- [x] Verification apparatus without operator macOS hardware → **resolved, DD8**
      (CI is load-bearing; friend channel explicitly skipped this flight)
- [x] macOS CI scope → **resolved, DD9** (containment job + full default suite,
      both required)
- [x] How boxed mode finds the interpreter on macOS (no `/usr`-merged layout)
      → **resolved, DD4**

### Design Decisions

**DD1 — Direct `sandbox-exec` + generated SBPL; `@anthropic-ai/sandbox-runtime`
is reference material only.**
- Rationale: srt's macOS backend is itself SBPL-generation + `sandbox-exec`
  invocation — there is no private API to lose. Taking srt as a dependency puts
  Node on the core tool-execution path for every macOS spawn, contradicting the
  mission constraints ("external runtimes needed only for MCP servers"; Flight 5's
  "no pre-existing runtime" success criterion) and importing the frozen-app spawn
  problem into our own security layer. srt's headline advantage (per-domain
  network proxy) is unused: `SandboxProfile.network_allowed` is deliberately
  binary, matching bwrap `--unshare-net` parity.
- Trade-off: we own SBPL profile correctness (dyld/system-path allowlist is the
  finicky part) and `sandbox-exec`'s formal deprecation risk — mitigated by the
  fact that Chrome, Bazel, Nix, and srt itself ride the same binary, and by
  kernel-verified containment tests in CI (same evidence standard as bwrap).
- Reference: srt's open-source SBPL templates inform profile conventions;
  `base.py`'s capability matrix (sandbox-exec column) was paper-validated in M14.

**DD2 — Seatbelt capability probe mirrors the F1 userns probe template.**
`_seatbelt_available()` runs `sandbox-exec -p '(version 1)(allow default)'
/usr/bin/true` with a timeout; `"ok"`/`"unavailable"`/`"error"` literals, result
cached module-level, cache cleared by `_reset_selection_log_state()`. Factory
selection on `sys.platform == "darwin"`: probe ok → `SeatbeltSandbox`; otherwise
passthrough with the same once-per-process WARNING/ERROR log-key discipline as
the Linux branch (`factory.py`). The F1 debrief explicitly blesses this pattern
as the template ("probe + cache + reset-in-log-guard").

**DD3 — Profile mapping (host mode).** `prepare_spawn` emits
`SpawnSpec(command="sandbox-exec", args=["-p", <SBPL>, command, *args], ...)`.
SBPL host-mode shape: allow-default; deny `file-write*` everywhere, then allow
write under each `writable_paths` entry plus the tempdir; re-deny write under
each `readonly_overlay_paths` entry (overlay-wins ordering = SBPL last-match
precedence — exact rule-order semantics are pinned by unit tests in the leg);
`network*` denied unless `profile.network_allowed`. The three namespace-unshare
flags (`pid/ipc/uts`) have **no macOS equivalent and are ignored** by this
backend — with a once-per-process DEBUG log naming the dropped knobs so a
security audit can see them (they are bwrap-shaped knobs; `base.py` matrix
anticipated this). HOME handling matches bubblewrap: `profile.home` else
`/tmp`, overriding any operator-supplied HOME, input env dict not mutated.
**All profile paths are canonicalized (realpath) at SBPL generation time**:
macOS `/tmp`, `/etc`, `/var` are symlinks into `/private/...`, and SBPL path
filters match canonical paths — un-realpath'd `writable_paths`, `home`, or the
per-spawn scratch dir would silently fail to match (architect review,
2026-06-12). SBPL last-match precedence (overlay-wins ordering) is **verified
empirically by a smoke step in the Leg 1 CI lane** before boxed mode is built —
string-level unit tests pin our emission order, not kernel precedence (the F1
"verify the load-bearing premise at design time" lesson).

**DD4 — Boxed mode (`minimal_rootfs`) on macOS = deny-default reads + explicit
system allowlist + the interpreter prefix.** SBPL denies `file-read*` by default
and allowlists: `/usr` (system), `/System`, the **narrow dyld-relevant
`/Library` subset only** (`/Library/Frameworks`, `/Library/Apple` — NOT all of
`/Library`, which can hold third-party app data; broaden only on observed
runner failures), `/private/etc` essentials, `/dev`, the per-spawn tempdir,
`writable_paths`, and —
deliberately, unlike Linux — **`sys.base_prefix` read-only** (macOS interpreters
live outside `/usr`: Homebrew `/opt/homebrew`, python.org `/Library/Frameworks`,
CI hostedtoolcache `/Users/runner/hostedtoolcache`). This is the designed answer
to the constraint F1's CI closeout hit on Linux (interpreter-outside-`/usr`
breaks boxed spawns — mission Known Issues), and it pre-answers Flight 5's
frozen-app variant of the same question.
- Trade-off: the box exposes the interpreter installation read-only. Acceptable:
  it contains no user data, and the Linux box already exposes all of `/usr`.
- Tempdir parity difference — **host mode AND boxed mode**: bwrap mounts a
  **private** tmpfs `/tmp` unconditionally (`bubblewrap.py:188`, outside the
  `minimal_rootfs` branch), so Linux children never see host `/tmp`; SBPL can
  only scope writes within the **shared** host `/private/tmp` (cross-spawn
  visibility, persistence, other processes' temp files readable). The backend
  points `TMPDIR` at the per-spawn scratch dir in `spec.env` for boxed spawns
  (leg verifies); SECURITY-MODEL.md documents the difference for **both**
  modes (round-2 architect review: the gap is not boxed-only).

**DD5 — Backend-name couplings become capability attributes on the Protocol.**
Three call sites currently couple to the concrete Linux backend and would lie
once Seatbelt enforces (architect review, 2026-06-12):
1. `warn_if_isolation_unenforced` (`platform/sandbox/_seam.py:33`) warns when
   `backend.name != "bubblewrap"` → false "isolation not enforced" warning on
   every boxed macOS spawn.
2. `mcp/transports/stdio.py:479` and `:599` gate the sandboxed-stderr capture/
   translation path on `isinstance(backend, BubblewrapSandbox)` → with Seatbelt
   selected, `sandbox-exec` setup failures surface as raw `MCPConnectionError`
   with stderr leaking, no `SandboxError` translation.
3. `pty.py:294` wrapped-detection (see DD6).
Resolution (locked): **additive capability attributes on the `ToolSandbox`
Protocol** (e.g. `enforces_isolation`, `wraps_stderr` — exact names at leg
design), one mechanism for all three. Passthrough declares neither capability;
bubblewrap declares both; seatbelt declares per its actual semantics —
**with `wraps_stderr=False` at Leg 4, flipped to True only when Leg 5's
translation lands** (declaring it earlier would divert sandbox-exec stderr
into a buffer with only bwrap-shaped patterns: possible mistranslation,
diagnostics lost from `sys.stderr`).

**DD6 — PTY path macOS-readiness.** (a) Env replacement is **already
correct**: the forked child does `os.environ.clear()` then
`os.environ.update(spec.env)` (`pty.py:327-328`) — the earlier draft of this
DD claimed a leak that does not exist (corrected at architect review,
2026-06-12). Leg 4 only **verifies** the replacement holds on the seatbelt
path and adds a regression test if none exists; no fix is in scope. (b) The
`self._wrapped = spec.command == "bwrap"` predicate (`pty.py:294`) exists to
select SIGKILL-fast teardown **because bwrap does not forward SIGTERM** to the
inner process. `sandbox-exec` applies the profile and execs the target
in-place — the child PID *is* the shell and SIGTERM reaches it directly, so
the graceful SIGTERM→1s→SIGKILL path is already correct for seatbelt. The
predicate is therefore **renamed/documented to its real semantic**
("SIGTERM-not-forwarded", a bwrap-specific property) rather than extended to
match `sandbox-exec` — extending it would needlessly discard graceful
teardown. Leg 4 verifies exec-in-place behavior empirically on the macOS lane.
Env-allowlisting on macOS is otherwise inherent: `shell.py:146` passes
`spec.env` as the child's entire environment, and the MCP stdio path passes it
to the SDK (which merges its `get_default_environment()` HOME/LANG-class,
non-secret defaults *under* ours — noted in `connect_stdio`'s docstring;
immaterial to the allowlist guarantee) (verified at planning).

**DD7 — Process supervision parity is accepted-different on macOS — and the
existing machinery does NOT cover grandchildren.** No `--die-with-parent`
equivalent exists, and (architect review, 2026-06-12) the PTY teardown path
kills a **single PID only** (`pty.py:587/:597/:618` — no `killpg`); on Linux,
bwrap's PID namespace is what reaps grandchildren. On macOS nothing would.
Leg 4 therefore **adds a process-group/session kill to the non-bwrap PTY
teardown path** (the PTY child is a session leader, so `killpg` on its group
is well-defined; job-control subgroups remain a documented residual gap), with
a macOS reap test scoped to what the mechanism actually guarantees
(direct-child + same-group descendants — NOT namespace-kill semantics).
SECURITY-MODEL.md documents the full platform difference, including the
job-control-subgroup residual.

**DD7b — Seatbelt stderr translation is in scope, minimal.** The bwrap stdio
path translates recognizable sandbox-setup stderr into `SandboxError`
(`stdio.py:159`, bwrap-signature-specific). Leg 5 adds the minimal seatbelt
analogue — recognize `sandbox-exec:`-prefixed setup failures and translate per
the same catalog convention — exercised by real failure cases in the
containment suite. Error-surface parity with bwrap beyond that recognizable
prefix is not promised this flight.

**DD8 — Verification apparatus: `macos-latest` CI is load-bearing; the
behavior-test backing of the mission criterion is deferred to Flight 8.**
Operator has no macOS hardware; the friend-on-a-Mac channel is explicitly
skipped this flight (operator decision, 2026-06-12). Enforcement evidence is
kernel-verified `@requires_seatbelt` containment tests on `macos-latest` —
the same evidence standard F1 set with the bwrap CI job. No behavior-test spec
is authored this flight (no interactive macOS apparatus exists to run it; per
AUTHORING guidance, don't author tests that can't be run). The mission
criterion's "(behavior-test-backed on macOS)" annotation is satisfied at
Flight 8's hands-on alignment, on real hardware.

**DD9 — macOS CI scope: containment job + full default suite, both required.**
Operator decision (2026-06-12), chosen over the seatbelt-only recommendation:
the flight also owns making the full default suite green on `macos-latest`,
as a required job. Scope consequence: a dedicated early portability leg
(Leg 1) absorbs unknown-unknowns; the divert criterion below caps it.
- Cost note: this is a private repository — GitHub bills macOS runner minutes
  at 10×. Two macOS jobs per PR (~1 min containment + ~4–6 min suite) ≈ 50–70
  billed minutes per PR push. Flagged for awareness; reversible by demoting
  the suite job to non-required later without rework.

### Prerequisites

- [x] Flight 1 merged to `main` (PR #109, `c25a908`, 2026-06-12) — host-native
      test suite + CI baseline all green on clean runners
- [x] M14 seam verified M15-ready (`ToolSandbox` Protocol, zero call-site slot-in)
- [x] `macos-latest` (Apple Silicon) GitHub-hosted runners available — standard
      GH offering, no self-hosting needed; mission Environment Requirements
      already name it
- [ ] Branch protection / required-checks config updated for the two new macOS
      jobs when they land (operator action at Leg 5, requires repo admin)
- [ ] `sandbox-exec` present and functional on the pinned macOS runner image —
      settled by a one-minute probe step in Leg 1's CI lane (divert criterion
      if it fails), not assumed
- [ ] `[all-llms,dev]` extras install cleanly on arm64 macOS (wheel
      availability) — verified by Leg 1's first CI run; any sdist-only
      stragglers are a Leg 1 finding

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (one operator action pending at Leg 5, non-blocking)
- [x] Validation approach defined (DD8/DD9; per-leg acceptance below)
- [x] Legs defined

---

## In-Flight

### Technical Approach

`SeatbeltSandbox` lands as a sibling of `BubblewrapSandbox`
(`the_one/platform/sandbox/seatbelt.py`), structurally satisfying the
`ToolSandbox` Protocol — no call-site changes (M14's design promise). SBPL
policies are generated as strings from `SandboxProfile` (host mode per DD3,
boxed mode per DD4) and passed inline via `sandbox-exec -p`. The factory gains
a `darwin` branch gated by the DD2 probe. Seam/PTY couplings (DD5/DD6) are
corrected so enforcement and warnings are truthful across backends. Containment
is proven by a `@requires_seatbelt` test suite mirroring the bwrap containment
tests (canary-unreadable, write-outside-denied, overlay re-protection,
network-denied/allowed, boxed interpreter runs), wired into a `macos-latest`
CI job; a second required job runs the full default suite (DD9). SBPL
generation itself is pure string-building — its unit tests run on every
platform, so most of the backend is testable on Linux dev boxes and only
kernel enforcement needs the macOS runner.

Sequencing note: Leg 1 (suite portability) runs first because it de-risks the
flight's largest unknown (DD9's scope expansion) before backend work begins,
and its CI lane is the substrate Legs 2–5 test against.

### Checkpoints

- [ ] Full default suite green on `macos-latest` (Leg 1) — the DD9 unknown is
      bounded before backend work starts
- [ ] `SeatbeltSandbox` unit tests (SBPL generation, both modes) green on
      Linux AND macOS lanes (Legs 2, 4)
- [ ] Factory selects seatbelt on darwin-with-probe-ok; passthrough + correct
      log key otherwise (Leg 3)
- [ ] Kernel-verified containment: `@requires_seatbelt` suite green on
      `macos-latest` (Leg 5)
- [ ] No Linux regression: existing `test`/`browser`/`bwrap` jobs stay green
      throughout (every leg)
- [ ] SECURITY-MODEL.md documents the macOS enforcement story and platform
      differences (Leg 6)

### Adaptation Criteria

**Divert if**:
- Leg 1 surfaces macOS suite portability work exceeding roughly a leg's worth
  of effort (a long tail of platform-specific failures) → split portability
  into its own flight, demote the suite job to non-required, re-scope Flight 2
  to the seatbelt lane only (reverses half of DD9 — requires operator sign-off)
- SBPL cannot express a profile guarantee the bwrap backend enforces (e.g.
  overlay re-protection ordering proves unreliable) → stop, re-design the
  profile mapping with operator input before any further legs
- The `sandbox-exec` binary is missing/non-functional on `macos-latest` images
  → DD1 needs re-evaluation (this would also break srt, so it would be
  ecosystem-level news)

**Acceptable variations**:
- Exact SBPL rule set for the DD4 system allowlist (leg design iterates against
  real runner failures)
- Attribute shape within DD5's locked capability-attribute resolution
  (a single capability *set* attribute vs. individual boolean attributes —
  both are Protocol attributes; the resolution itself is not open) and the
  DD6(b) predicate's new name/documentation
- Whether the two macOS CI jobs share a workflow job with a matrix or stay
  separate named jobs

### Legs

> Tentative breakdown — refined per-leg at design time (`/leg`).

1. **macos-suite-portability** — Add a macOS full-default-suite CI job on a
   **pinned image** (`macos-15`, not `macos-latest` — avoids image drift
   between Leg 1's green and Leg 5's required flip; unpin review at Leg 6)
   (non-required while iterating; flipped to required at Leg 5); fix
   portability failures it surfaces; add two one-minute lane smokes: the
   `sandbox-exec` presence/function probe and the SBPL last-match-precedence
   probe (DD3); register the `requires_seatbelt` marker + addopts deselect in
   `pyproject.toml` now (cheap insurance for Legs 2–4 unit tests).
   *(The two F1 ride-alongs — `skipif(which("bwrap"))` re-marking and the
   `mcp/__init__` guard comments — **migrated to the Windows flight** when
   this flight was parked 2026-06-13; their "before the CI matrix expands"
   deadline is met by the Windows matrix, which now expands first. On resume,
   verify they landed there rather than re-doing them.)*
2. **seatbelt-backend-host-mode** — `SeatbeltSandbox` with host-mode SBPL
   generation (DD3, canonicalized paths) + platform-independent unit tests
   (string-level, run everywhere) + contract-test parity with
   `test_sandbox_contract.py`; construction-failure message follows the
   existing backend error-catalog convention (seatbelt-worded, not
   bwrap-worded). **Interim boxed semantic (until Leg 4)**: `prepare_spawn`
   with `minimal_rootfs=True` emits host-mode SBPL gracefully (degraded — the
   `_seam.py` warning fires truthfully, since DD5's capability attributes also
   land in Leg 4), never raises; Leg 4 replaces this fallback. Pinned now so
   the Leg 3 selection-flip window (boxed `python_exec` spawns routing into a
   host-mode-only backend) has defined behavior instead of improvised
   handling.
3. **factory-darwin-probe** — `_seatbelt_available()` probe (DD2), `darwin`
   factory branch, selection log keys (existing key strings like
   `passthrough:non-linux:{platform}` are test-pinned — darwin gets its own
   probe-gated keys without disturbing them), monkeypatchable selection tests
   (run everywhere). **Acceptance includes the selection-flip audit**: once this
   leg lands, every macOS-lane default-suite test that reaches the real
   factory starts spawning under sandbox-exec instead of passthrough — the
   macOS suite job must be re-verified green post-flip, and tests reaching the
   real factory on darwin audited (architect review: hidden Leg 1↔Leg 3
   coupling).
4. **boxed-mode-and-seam-truth** — DD4 boxed SBPL mapping (incl.
   `sys.base_prefix`, TMPDIR-to-scratch, canonicalized paths); DD5 capability
   attributes across all three call sites (`_seam.py`, `stdio.py` ×2,
   `pty.py`); DD6 verification (env-replace regression test; wrapped-predicate
   rename + exec-in-place verification); DD7 non-bwrap process-group kill;
   unit tests for all (run everywhere). M14 carried-forward "do-if-touched"
   items fall in this leg's surface — leg design decides whether
   `_build_boxed_profile(network_allowed=...)` falls out naturally.
   **Pre-existing adjacent leak (decision, not silent fix)**: `is_alive`
   reaping an exited child sets `_closed=True` (`pty.py:430-432`), making a
   later `close()` early-return without closing `master_fd` or removing
   `cleanup_dir` (`pty.py:570-572`) — Leg 4's reap test lands in exactly this
   method; the leg spec must decide whether to fix or explicitly leave it.
5. **seatbelt-containment-ci** — containment test suite mirroring the bwrap
   tests (marker already registered in Leg 1), DD7b minimal stderr
   translation, macOS containment CI job on the pinned image; flip both macOS
   jobs to required (operator flips branch protection). Kernel-verification
   checkpoint.
6. **docs-and-verify-integration** — SECURITY-MODEL.md macOS section (DD7
   platform differences, DD4 interpreter-prefix exposure), `agents.md`/CLAUDE.md
   touch-ups, mission Known Issues review, end-to-end verify-integration pass
   (all CI lanes green, factory behavior re-verified, no Linux regression).

### Verification

- **Kernel-enforced containment on macOS** — `@requires_seatbelt` CI suite
  (Leg 5): canary file unreadable in boxed mode, write-outside-allowlist
  denied, `readonly_overlay_paths` re-protection holds, network denied by
  default / allowed when enabled, boxed interpreter executes. Same evidence
  standard as F1's bwrap job.
- **No-regression** — existing `test` / `browser` / `bwrap` jobs required and
  green on every leg's PR push.
- **Cross-platform unit coverage** — SBPL generation and selection logic tested
  on both Linux and macOS lanes (pure string/logic tests).
- **Behavior test** — none authored this flight (DD8); mission criterion's
  behavior-test backing deferred to Flight 8 on real hardware.
