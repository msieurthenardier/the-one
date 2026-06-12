# Flight Debrief: Host-Native Runtime Readiness

**Date**: 2026-06-08
**Flight**: [Host-Native Runtime Readiness](flight.md)
**Status**: completed
**Duration**: 2026-06-07 (plan + Legs 1–4) → 2026-06-08 (Legs 5–7, review, commit, PR)
**Legs Completed**: 7 of 7

## Outcome Assessment

### Objectives Achieved

The flight achieved its objective: GleepGlorp now runs, develops, and **tests entirely
host-native with no Docker**. All seven legs landed; no divert criterion fired. Draft
PR #109 carries the work (3 commits: Flight-1, recovered orphan UI fixes, CLAUDE.md
host-native doc update).

### Mission Criteria Advanced

- **"Tested entirely without Docker; existing suite passes host-natively in CI"** — met
  for the test flow: default suite **3065 passed**, `-m requires_bwrap` **31 passed**
  (real kernel-enforced containment), browser **478 passed**, all host-native; CI
  `test.yml` (test/browser/bwrap jobs) added. (App dev/run still uses the container —
  later flights.)
- **"Data + secrets in an OS-appropriate per-user location; `~/.the-one` migrated"** —
  path + guarded move-migration logic landed (the "installed app" part is later flights).
- **"Linux sandbox enforces host-native (no Docker)"** — empirical userns probe +
  graceful degrade; containment verified host-native.
- **"Missing external runtime → actionable non-Docker guidance"** — detection + per-runtime
  host-native install hints landed.

### Checkpoints

All flight checkpoints met. The load-bearing premise (host-native bwrap containment) was
verified empirically at design time before legs were locked.

## What Went Well

- **Design-time empirical verification of the load-bearing DD.** Running host-native bwrap
  on the WSL2 dev box *before* specing Leg 4 found the `unprivileged_userns_clone` procfs
  knob is absent on that kernel while userns works — directly shaping the "empirical probe,
  not procfs knob" design and removing the "sandbox leg collapses" risk pre-emptively.
  This is the flight's standout process win (and repeats M14's lesson).
- **Per-leg design review caught real issues before implementation on every leg** — the
  complete `SandboxError` importer set (naive "~2" was 3× short), the migration-into-temp-dir
  hazard, the `@requires_bwrap` default-deselect, the monkeypatchable-probe requirement,
  and the host-native browser known-failures roadmap.
- **Reviewer scaled to diff risk (Sonnet, not Haiku) for the security-critical diff** — and
  the Phase-2d batched review earned it by catching a genuine **security regression** (a
  dead `data_dir/secrets` denylist entry).
- **De-Docker delivered a measurable speedup**: default suite **417s (container, M14 F4) →
  327s host-native** — a ~90s improvement from removing container overhead and `docker exec`
  round-trips.
- **Candid flight log.** Developer stalls, the self-modification guard, and the orphan/CPU
  incident are all recorded with root causes, not hidden.

## What Could Be Improved

### Process
- **A flawed leg spec produced the security regression.** Leg 2's spec called the
  `DEFAULT_PATH_DENYLIST` `~/.the-one/secrets` entry a *"doc example, no behavior change"* —
  but it was a live access-control guard. The implementer faithfully replaced it with a
  non-expanding `"<data_dir>/secrets"` literal, silently removing protection. Caught only at
  Phase-2d (correctly), but the root cause was a **design-phase misclassification of a
  security invariant as documentation** — which a per-leg implementation review would also
  have missed (the implementer matched the spec).
- **Two implementing-Developer agents stalled mid-run** (Leg 3 and Leg 6) — returned before
  their final wrap-up (status flip + log entry). The Flight Director recovered both
  (verification + artifact closeout only, no code authored), but it required FD vigilance
  and `SendMessage` was unavailable to resume them.
- **The orphan/CPU incident.** Running the browser suite via **bare `python -m pytest`**
  (bypassing the group-kill wrapper) orphaned 5 per-test uvicorns that pegged a core and
  starved 4 browser tests into *false* timeout-failures. The operator's "you don't detect
  deadlocks" instinct surfaced it; the real fix was process hygiene, not the tests (clean
  wrapped run: 478/0).

### Technical
- **`test-bwrap` / `test-live` Makefile targets use bare `$(PY) -m pytest`, not the wrapper**
  — lower orphan risk than browser (no uvicorn/Chromium) but an inconsistency.
- **`mcp/__init__` eagerly imports `_tool`/`_tool_provider`**, which forced lazy `SandboxError`
  imports (in `except` clauses) to avoid a load-time cycle. Correct but fragile — a future
  top-level import re-opens the cycle. A comment naming the hazard in both files would guard it.
- **~12 bwrap *integration* tests use `skipif(which("bwrap"))` not `@pytest.mark.requires_bwrap`**
  → not selected by the CI `bwrap` job; they skip on the no-bwrap `test` job. No CI coverage
  for that integration layer.
- **Untested edge cases** in the migration: EXDEV copy-fallback, symlink-legacy skip,
  empty-string `THE_ONE_DATA_DIR` (resolves `data_dir` to `Path('.')` — pre-existing pydantic
  behavior the new code surfaces more prominently).

### Documentation
- CLAUDE.md host-native test-command update was blocked twice by the self-modification guard;
  applied at flight end after explicit operator authorization (commit `38322b7`).
- The CI `test.yml` jobs use bare `python -m pytest` (correct — ephemeral runners kill
  orphans with the runner) but carry no comment explaining *why*, risking a well-meaning
  future "fix" to the wrapper.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Lazy `SandboxError` imports in `_tool`/`_tool_provider` | `mcp/__init__` eager-load cycle once the moved module became real | No — narrow fix; add a guard comment |
| `resolve_python()` symlink fix (Leg 5, not Leg 4) | host-native `sys.executable` = `.venv/bin/python` outside the box's `/usr` | Lesson: host-native legs must enumerate container-baked path assumptions |
| Browser tests run via `run-tests.sh` only | bare pytest orphans uvicorn/Chromium → CPU peg → false flakes | **Yes** — never run browser tests bare; document in CLAUDE.md (done) |
| `model_post_init` dynamic denylist append (Phase-2d fix) | static tuple placeholder `<data_dir>` can't track the live data_dir | **Yes** — prefer dynamic config entries over static placeholders |
| Reviewer = Sonnet for the security diff | scale reviewer to diff risk (M14 precedent) | **Yes** — Sonnet for any sandbox/denylist/security-model diff |

## Key Learnings

- **Test-metric snapshot** (seeds future comparisons): default **3065 passed / 4 skipped /
  576 deselected, 327s**; bwrap **31 passed, ~20s**; browser **478 passed**. Suite grew +14
  vs M14 F4 (3051) — new `test_config_data_dir.py` (7), per-runtime hint cases (Leg 3),
  factory probe tests (Leg 4), `TestDataDirSecretsDenylist` (3). Pre-existing warnings
  (aiosqlite teardown in `test_db_migration.py`; Starlette deprecation in
  `test_origin_allowlist.py`) persisted — not introduced here.
- **Security invariants must be enforced by *explicit, prior* tests** — the regression
  survived because no test asserted `data_dir/secrets` was in the canonical denylist; green
  ≠ protected. The fix added that net.
- **`model_fields_set` cleanly distinguishes default-resolved vs explicitly-supplied** pydantic
  fields — reusable for any default-only migration guard.
- **Probe + cache + reset-in-log-guard** (`_userns_available`/`_USERNS_PROBE`/
  `_reset_selection_log_state`) is a clean, monkeypatchable, test-safe template for the macOS
  Seatbelt and Windows capability probes to come.
- **Complete importer enumeration for relocation legs must include `__init__`-mediated
  transitive importers** — one design-review pass missed the eager-load chain; two caught it.

## Recommendations

1. **Add a "security invariants" altitude to design review.** Any leg touching a
   `*_DENYLIST`/`*_ALLOWLIST`/capability-probe/sandbox-selection construct must list the
   invariants it must preserve and ship tests asserting each — *before* the change. Don't
   trust existing coverage to catch a removal.
2. **Standardize "scale reviewer to diff risk"**: Sonnet (never Haiku) for any diff touching
   `FilesystemConfig`, `DEFAULT_PATH_DENYLIST`, `factory.py`, `bubblewrap.py`, or a security
   model file.
3. **Codify the group-kill rule** (browser/long-subprocess tests via `run-tests.sh`, never
   bare pytest) — done in CLAUDE.md; consider a hooked guard so the lesson can't silently
   regress.
4. **For host-native apparatus legs, enumerate container-baked path assumptions** (interpreter
   path, workspace binds) at design time — this flight found `resolve_python()` only when the
   apparatus flipped.
5. **Re-mark the ~12 `skipif(which("bwrap"))` integration tests** as `@requires_bwrap` before
   the CI matrix expands (Flights 2/3) — else they become invisible false-skips on
   macOS/Windows runners.

## Action Items

- [ ] Re-mark ~12 `skipif(which("bwrap"))` integration tests as `@pytest.mark.requires_bwrap`
      (`test_mcp_sandbox_integration.py`, `test_mcp_stdio_sandbox.py:447`).
- [ ] Add a guard comment in `_tool.py`/`_tool_provider.py` naming the `mcp/__init__`
      eager-load cycle hazard that requires the lazy `SandboxError` import.
- [x] Add a one-line comment to `.github/workflows/test.yml` explaining bare pytest is safe
      on ephemeral runners (orphans die with the runner) — done in the PR-#109 CI-red
      closeout (see flight log).
- [ ] Fix `test-live` `test_aiat.py` `/app/...` paths for host-native (needs a running
      host-native server) — future leg.
- [ ] Consider deferring `mcp/__init__`'s eager `_tool`/`_tool_provider` imports to remove the
      cycle-hazard class permanently — future maintenance.
- [x] Re-characterize the `test_connectors_e2e` flake — root-caused in the PR-#109 CI-red
      closeout (see flight log): the `last_activity = 0.0` aging idiom is uptime-dependent
      (`time.monotonic()` starts near zero at boot, so 0.0 is within TTL on freshly-booted
      hosts). Fixed by monotonic-relative aging across both pools' tests.
- [x] CLAUDE.md host-native test-command update — done (`38322b7`).
