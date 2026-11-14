# Leg: 01b-bwrap-argv-reorder-tmpfs-before-bind

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## Objective

Reorder `the_one/platform/sandbox/bubblewrap.py::prepare_spawn` so `--tmpfs /tmp` is emitted BEFORE the `--bind PATH PATH` loop (and before `--proc /proc` / `--dev /dev`), making `writable_paths=["/tmp/foo"]` actually persist when the operator configures one.

## Context

### Flight design decisions

- **§7 (A03 argv reorder)**: single-block move in `prepare_spawn`. Anomaly A03 from F3 was that `--tmpfs /tmp` was emitted AFTER the `--bind PATH PATH` loop, which means the tmpfs lays down `/tmp` over any operator-configured writable bind under `/tmp` — silently shadowing the bind. Fixing this means the tmpfs lays first, and subsequent `--bind` calls layer on top. The leg's documentation impact: the L5b help text proposed in F3 debrief ("Paths under `/tmp` are not persisted; use `/var/tmp`...") is NO LONGER NEEDED.

### Carries forward

- F3 debrief Anomaly A03 + Action Item to land argv reorder in F4.
- F3 debrief recommendation that L5a's documentation references the workaround language ("paths under `/tmp` not persisted") be dropped. **Cycle-1 reviewer caught a gap in the original drafting**: workaround language exists in **four** docstring locations, not just one — both `bubblewrap.py` docstrings list the OLD argv order, and `tests/test_mcp_sandbox_integration.py` has the workaround caveat in two places. All four are updated in this leg to prevent stale handoff to L5.

### Why this leg lands second (after L1a)

L1a touches `client.py` and adds new tests; L1b touches `platform/sandbox/bubblewrap.py` and reorders argv. Different files, different concerns — pre-split per Architect cycle-1 recommendation. L1b is the smallest leg in the flight; it could parallelize with L1a but the agentic-workflow flow runs them sequentially for review-cycle simplicity.

## Inputs

What exists before this leg runs:

- `the_one/platform/sandbox/bubblewrap.py::BubblewrapSandbox.prepare_spawn` (lines 86-124 in current source) emits `--tmpfs /tmp` at line 112, AFTER:
  - line 107: `bwrap_args.extend(["--ro-bind", "/", "/"])`
  - lines 108-109: `for path in profile.writable_paths: bwrap_args.extend(["--bind", path, path])`
  - line 110: `bwrap_args.extend(["--proc", "/proc"])`
  - line 111: `bwrap_args.extend(["--dev", "/dev"])`
- `tests/test_sandbox_bubblewrap.py` has 16 tests at the L1b-start baseline. Argv-asserting tests (verified at design):
  - `test_prepare_spawn_minimal_no_writable_no_env` (line 65 area) — asserts `"--ro-bind" in a`, `"--proc" in a`, `"--dev" in a`, `"--tmpfs" in a`. Does NOT assert ordering. **Safe — unmodified after reorder.**
  - `test_prepare_spawn_with_writable_paths` (lines 101-119) — asserts `--bind PATH PATH` structure for two paths and operator-order preservation between them (`d_idx < c_idx`). Does NOT assert ordering vs `--tmpfs` or `--ro-bind`. **Safe — unmodified after reorder.**
  - `test_prepare_spawn_writable_paths_with_relative_path` (lines 243-254) — asserts `--bind data/foo data/foo` structure only. **Safe.**
  - `test_prepare_spawn_command_and_args_at_end` (lines 231-240) — asserts the last 4 elements are `["--", "/bin/echo", "hello", "world"]`. The reorder doesn't touch the tail. **Safe.**
  - `test_prepare_spawn_cwd_is_set` (lines 154-169) — asserts `--chdir cwd` precedes `--`. The reorder doesn't touch that span. **Safe.**
- L1a's source-code refactor on `the_one/mcp/client.py` is complete and the working tree's source state is clean except for that L1a refactor.
- L1a's flight-log Leg Progress entry has captured the L1a-start SHA `4ad63611008abcdbf3154e52c3209f3f413c7a44`. L1b uses the post-L1a SHA — capture it via `git rev-parse HEAD` BEFORE first L1b edit (working tree has L1a uncommitted source changes; that's fine — capture HEAD anyway, it's the regression-test baseline).

## Outputs

What exists after this leg completes:

- `the_one/platform/sandbox/bubblewrap.py::BubblewrapSandbox.prepare_spawn` emits argv in this order (changes are bracketed; everything else unchanged):
  ```
  --die-with-parent --unshare-user [--unshare-pid] [--unshare-ipc] [--unshare-uts]
  [--unshare-net] --clearenv [--setenv KEY VALUE]* --ro-bind / /
  **[--tmpfs /tmp]**       <-- moved up: was at the end of the floor block
  [--bind PATH PATH]*      <-- now after --tmpfs (bind layers on top)
  --proc /proc --dev /dev
  [--chdir cwd] -- command [*args]
  ```
- A short comment near the move explains the precedence: `--tmpfs /tmp` lays the tmpfs first; subsequent `--bind PATH PATH` for any path under `/tmp` then layers on top, allowing operator-configured writable paths under `/tmp` to actually persist.
- `the_one/platform/sandbox/bubblewrap.py` class docstring (lines 36-43) — argv-structure listing updated to reflect the new order (`--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH` → `--proc /proc` → `--dev /dev`).
- `the_one/platform/sandbox/bubblewrap.py::prepare_spawn` method docstring (lines 76-82) — same listing updated to match.
- `tests/test_mcp_sandbox_integration.py` module docstring (lines 42-46) — workaround language ("L3's argv compiler emits `--bind` BEFORE `--tmpfs /tmp`...operators must use writable_paths OUTSIDE `/tmp`") REMOVED; replaced with a one-line note that post-A03 ordering means `/tmp`-scoped writable paths now persist.
- `tests/test_mcp_sandbox_integration.py::writable_scratch_dir` fixture docstring (lines 131-144) — workaround paragraph REMOVED; replaced with a one-line rationale that `/var/tmp` is still used (orthogonally) for parallel-safe pytest-xdist isolation alongside the unconditional `HOME=/tmp` override.
- `tests/test_sandbox_bubblewrap.py` gains ONE new test: `test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind` (per Architect cycle-1 suggestion — explicit three-way assertion). Asserts `--ro-bind` (or its position) precedes `--tmpfs /tmp`, which precedes `--bind PATH PATH` for any operator-configured writable path. Test count goes 16 → 17.
- All 16 prior `tests/test_sandbox_bubblewrap.py` test METHODS pass UNMODIFIED (verified above — none assert ordering between the moved span and the `--bind` loop). Docstring-only changes in `tests/test_mcp_sandbox_integration.py` do NOT modify any test method bodies; the 10 tests in that file pass UNMODIFIED.
- `tests/test_mcp_stdio_sandbox.py` (9 tests) and `tests/test_mcp_sandbox_integration.py` (10 tests) pass unmodified — they don't assert argv ordering.
- F1, F2, L1a tests pass unmodified — `prepare_spawn` is invoked by `the_one/mcp/transports/stdio.py::_build_stdio_params` only at sandbox-spawn time, so the reorder is observable to MCPClient only via spawn-time bwrap behavior; the L1a tests use the test-mode bypass (`THE_ONE_SANDBOX_DISABLED=1`) which routes around `prepare_spawn`, so they are insensitive to argv ordering.
- `pytest tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_sandbox_integration.py -q --timeout=30` is green; cumulative count for L1a + L1b = 117 prior + 5 (L1a) + 1 (L1b) = 123.
- `ruff check the_one/platform/sandbox/ tests/test_sandbox_bubblewrap.py` is clean (no new findings vs baseline).
- Flight log Leg Progress entry added.

## Acceptance Criteria

- [ ] `the_one/platform/sandbox/bubblewrap.py::BubblewrapSandbox.prepare_spawn` emits `--tmpfs /tmp` BEFORE the `for path in profile.writable_paths: bwrap_args.extend(["--bind", path, path])` loop.
- [ ] The relative ordering after reorder is: `--ro-bind / /` (line 107 area) → `--tmpfs /tmp` (the moved line) → `--bind PATH PATH` per writable path (the loop) → `--proc /proc` → `--dev /dev` → optional `--chdir cwd` → `--` → command + args.
- [ ] A new test `test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind` exists in `tests/test_sandbox_bubblewrap.py` asserting `index("--ro-bind") < index("--tmpfs") < index("--bind")` for a `SandboxProfile(writable_paths=["/data"])`-shaped invocation.
- [ ] `tests/test_sandbox_bubblewrap.py` count goes 16 → 17 (one new test, no deletions or modifications of existing tests).
- [ ] All 117 prior test METHODS across the F2/F3 + L1a-modified surface pass UNMODIFIED (docstring-only changes in `tests/test_mcp_sandbox_integration.py`'s module + fixture docstrings do NOT count as test-method modifications). Specifically `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30` returns: `tests/test_mcp_client.py` 59 (54 prior + 5 L1a), the rest at their pre-L1b baselines, `tests/test_sandbox_bubblewrap.py` 17 (16 prior + 1 L1b new). Total: 123 = 117 (pre-L1a baseline: 54+14+10+9+16+14) + 5 (L1a) + 1 (L1b).
- [ ] `ruff check the_one/platform/sandbox/ tests/test_sandbox_bubblewrap.py` produces no NEW errors versus baseline.
- [ ] Flight log Leg Progress entry added with: (a) lines changed (expected: ~3 lines moved in `bubblewrap.py`); (b) new test count; (c) confirmation that no existing tests required modification.

## Verification Steps

How to confirm each criterion is met:

1. **Argv reorder applied**: `grep -n "--tmpfs\|--bind\|--ro-bind\|--proc\|--dev" the_one/platform/sandbox/bubblewrap.py` shows the emit-order `--ro-bind` → `--tmpfs` → `--bind`-loop → `--proc` → `--dev`. Compared to current order which is `--ro-bind` → `--bind`-loop → `--proc` → `--dev` → `--tmpfs`.
2. **Three-way order test passes**: `docker compose exec the-one pytest tests/test_sandbox_bubblewrap.py::test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind -v --timeout=10` returns 0 exit.
3. **Sandbox tests green**: `docker compose exec the-one pytest tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_sandbox_integration.py -q --timeout=30` returns 0 exit; counts: `test_sandbox_bubblewrap.py` 17, `test_sandbox_contract.py` 14, `test_mcp_stdio_sandbox.py` 9, `test_mcp_sandbox_integration.py` 10 → 50 passed.
4. **Cumulative regression invariant**: `docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30` reports 123 passed (59 + 14 + 10 + 9 + 17 + 14).
5. **No prior test modifications**: against the L1b-start commit (`git rev-parse HEAD` captured before first L1b edit), `git diff <l1b-start-sha> -- tests/test_sandbox_bubblewrap.py | grep -E '^-[^-]' | wc -l` returns 0 (no deletions or modifications of existing tests; only the new test class/function ADDED).
6. **Lint clean**: `docker compose exec the-one ruff check the_one/platform/sandbox/ tests/test_sandbox_bubblewrap.py` returns 0 exit with no new findings vs baseline.
7. **Flight log updated**: `grep -A 6 "01b-bwrap-argv-reorder" missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` shows a Leg Progress entry with status `landed`, started/completed timestamps, lines-changed count, new test count, and the prior-test-unmodified confirmation.

## Implementation Guidance

1. **Capture the L1b-start commit SHA**: `cd ~/projects/the-one && git rev-parse HEAD` and note the value (this is post-L1a; L1a's source changes are uncommitted in the working tree but that's expected — Flight Director batches commit at flight-end).

2. **Run the L1b-affected test baseline**:
   ```bash
   docker compose exec the-one pytest tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_sandbox_integration.py -q --timeout=30
   ```
   Expect: 16 + 14 + 9 + 10 = 49 passed.

3. **Update the docstrings in `the_one/platform/sandbox/bubblewrap.py`** to reflect the new argv order. Both the class docstring (lines 36-43) and the `prepare_spawn` method docstring (lines 76-82) currently list `--proc /proc, --dev /dev, --tmpfs /tmp` at the end of the floor-mount block. Update both to: `--ro-bind / /, --tmpfs /tmp, --bind PATH PATH per writable_paths entry, --proc /proc, --dev /dev`.

4. **Update the docstrings in `tests/test_mcp_sandbox_integration.py`**:
   - Module docstring (lines 42-46): replace the "Edge case documented in the flight log..." paragraph with a one-line note like: `Post-A03 (F4 L1b), --tmpfs /tmp is emitted BEFORE the --bind PATH PATH loop, so writable_paths under /tmp persist correctly.`
   - `writable_scratch_dir` fixture docstring (lines 131-144): drop the "Uses /var/tmp (NOT /tmp) to dodge the L3 argv-compilation edge case..." paragraph; replace with `Uses /var/tmp for parallel-safe pytest-xdist isolation alongside the unconditional HOME=/tmp sandbox override (avoids collision with the bwrap tmpfs-rooted HOME).`

5. **Reorder the argv block** in `the_one/platform/sandbox/bubblewrap.py::prepare_spawn`. Move line 112 (`bwrap_args.extend(["--tmpfs", "/tmp"])`) to just after line 107 (`bwrap_args.extend(["--ro-bind", "/", "/"])`). Add a short comment:

   ```python
   bwrap_args.extend(["--ro-bind", "/", "/"])
   # --tmpfs /tmp BEFORE the --bind loop so writable_paths under /tmp
   # actually persist (the tmpfs lays /tmp first; the --bind layers on
   # top). Pre-A03 ordering had --tmpfs after --bind, silently shadowing
   # operator-configured writable paths under /tmp. See F3 anomaly A03.
   bwrap_args.extend(["--tmpfs", "/tmp"])
   for path in profile.writable_paths:
       bwrap_args.extend(["--bind", path, path])
   bwrap_args.extend(["--proc", "/proc"])
   bwrap_args.extend(["--dev", "/dev"])
   ```

   The original `bwrap_args.extend(["--tmpfs", "/tmp"])` line at the old position (between `--dev` and the `if cwd is not None` block) is DELETED — only one `--tmpfs /tmp` should appear in the argv.

6. **Add the new test** to `tests/test_sandbox_bubblewrap.py`. Place it AFTER `test_prepare_spawn_with_writable_paths` (around line 119):

   ```python
   def test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind() -> None:
       """A03 fix: --ro-bind / / precedes --tmpfs /tmp precedes --bind PATH PATH.

       This locks the post-A03 ordering so a future refactor can't
       silently re-introduce the shadowing bug where writable paths
       under /tmp got overlaid by the tmpfs.
       """
       sb = BubblewrapSandbox()
       spec = sb.prepare_spawn(
           SandboxProfile(writable_paths=["/data"]),
           "/bin/echo",
           [],
           {},
       )
       a = spec.args
       ro_bind_idx = a.index("--ro-bind")
       tmpfs_idx = a.index("--tmpfs")
       data_idx = a.index("/data")
       bind_idx = data_idx - 1  # --bind precedes the path
       assert a[bind_idx] == "--bind"
       assert ro_bind_idx < tmpfs_idx < bind_idx, (
           f"Expected --ro-bind ({ro_bind_idx}) < --tmpfs ({tmpfs_idx}) "
           f"< --bind ({bind_idx}); got argv: {a}"
       )
   ```

7. **Run the full L1b regression suite**:
   ```bash
   docker compose exec the-one pytest tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_sandbox_integration.py tests/test_mcp_client.py tests/test_mcp_integration.py -q --timeout=30
   ```
   Expect 123 passed (59 + 14 + 10 + 9 + 17 + 14). If any prior test fails, revert the source change and signal `[BLOCKED:reason]`.

8. **Lint**:
   ```bash
   docker compose exec the-one ruff check the_one/platform/sandbox/ tests/test_sandbox_bubblewrap.py
   ```

9. **Update the flight log**: append a Leg Progress entry with status `landed`, ISO 8601 UTC timestamps, lines-changed (~3 in `bubblewrap.py` + new test + comment + 4 docstring updates), test-count reconciliation (16 → 17 in `bubblewrap.py`; cumulative 123 across the L1a + L1b combined surface), and confirmation that `tests/test_mcp_sandbox_integration.py` test METHODS are unmodified (only docstrings changed).

## Edge Cases

- **Non-`/tmp` writable paths**: `writable_paths=["/data", "/cache"]` (paths NOT under `/tmp`) are unaffected by tmpfs ordering — they bind onto the read-only root mount regardless. Existing tests cover this; no new edge-case test needed.
- **Empty `writable_paths`**: the `--bind` loop runs zero iterations; the argv has no `--bind` between `--tmpfs /tmp` and `--proc /proc`. The new three-way test uses a non-empty `writable_paths` to exercise the ordering invariant; for `writable_paths=[]`, the invariant is vacuously satisfied (no `--bind` to position).
- **`writable_paths=["/tmp/foo"]` smoke test**: not added in this leg per leg-sizing principles. The three-way ordering test is sufficient to lock the contract; the operator-facing observable (tmpfs no longer shadows `/tmp/foo`) is exercised at L4 / L6 HAT against a real bwrap subprocess.
- **CI compatibility**: the CI image (`mcr.microsoft.com/playwright/python:v1.58.0-jammy`) runs bwrap (per F3 §10's compatibility probe). The argv reorder doesn't change the privilege grants required — bwrap still needs `cap_add: SYS_ADMIN AND security_opt: seccomp:unconfined`. CI should remain green.
- **Three-way assertion message**: failure-mode message in the new test surfaces all three indices and the full argv so diagnosis is fast if a future change breaks the ordering.

## Files Affected

- `the_one/platform/sandbox/bubblewrap.py` — single-block argv reorder + ~5-line explanatory comment + class docstring (lines 36-43) + `prepare_spawn` method docstring (lines 76-82) updated to reflect new argv order.
- `tests/test_sandbox_bubblewrap.py` — one new test method (`test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind`).
- `tests/test_mcp_sandbox_integration.py` — docstring-only changes: (a) module docstring (lines 42-46) — drop "operators must use writable_paths OUTSIDE `/tmp`" workaround language, replace with note that post-A03 `/tmp`-scoped writable paths persist; (b) `writable_scratch_dir` fixture docstring (lines 131-144) — drop the L3-shadowing-edge-case paragraph, retain the orthogonal `/var/tmp` rationale (parallel-safe pytest-xdist isolation; `HOME=/tmp` override). Test METHODS in this file are unmodified.
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30` green; counts: 59 + 14 + 10 + 9 + 17 + 14 = 123
- [ ] `ruff check the_one/platform/sandbox/ tests/test_sandbox_bubblewrap.py` clean (no NEW findings vs baseline)
- [ ] Flight log Leg Progress entry added (status `landed`, timestamps, lines-changed count, new test count, prior-test-unmodified confirmation)
- [ ] Set this leg's status to `landed` (header at top of this file). Do NOT set to `completed` — the flight-level commit transitions it.
- [ ] Check off this leg in flight.md (the `[ ] 01b-bwrap-argv-reorder-tmpfs-before-bind` line)
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

5 citations verified against current code at leg design time (2026-05-07; design-review cycle 1 expanded coverage to include downstream docstrings).

- `the_one/platform/sandbox/bubblewrap.py:107-112` (in `BubblewrapSandbox.prepare_spawn`) — `bwrap_args.extend(["--ro-bind", "/", "/"])` followed by the `--bind` loop, then `--proc`, `--dev`, `--tmpfs /tmp` at line 112 — **OK** (verified via Read 2026-05-07).
- `the_one/platform/sandbox/bubblewrap.py:36-43` (class docstring "Argv structure" listing) — currently lists `--proc /proc, --dev /dev, --tmpfs /tmp` at the end of the floor-mount block; **will be updated in this leg**.
- `the_one/platform/sandbox/bubblewrap.py:76-82` (`prepare_spawn` method docstring "Argv structure" listing) — same listing; **will be updated in this leg**.
- `tests/test_sandbox_bubblewrap.py:101-119` (`test_prepare_spawn_with_writable_paths`) — asserts only `--bind PATH PATH` structure and operator order; does NOT assert tmpfs/bind ordering — **OK**, safe under reorder.
- `tests/test_sandbox_bubblewrap.py:243-254` (`test_prepare_spawn_writable_paths_with_relative_path`) — same pattern; safe under reorder — **OK**.
- `tests/test_mcp_sandbox_integration.py:42-46` (module docstring) — contains stale "Edge case... `--bind` BEFORE `--tmpfs /tmp`... operators must use writable_paths OUTSIDE `/tmp`" workaround language; **will be updated in this leg**.
- `tests/test_mcp_sandbox_integration.py:131-144` (`writable_scratch_dir` fixture docstring) — contains stale "Uses /var/tmp (NOT /tmp) to dodge the L3 argv-compilation edge case" paragraph; **will be updated in this leg**.
