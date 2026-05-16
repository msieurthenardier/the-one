# Leg: 01-lint-format-restoration-and-gate-audit

**Status**: completed
**Flight**: [Code Hygiene + Concourse Removal](../flight.md)

> **Scope pivot 2026-05-15**: this leg's original framing centered on a deliberate-violation experiment to prove the Concourse pipeline gate enforces. Operator decision during execution: Concourse + self-improvement framing will be removed in this flight's new Leg 4. With no pipeline to test, the experiment is moot and dropped from this leg. The lint+format cleanup remains valuable — it's still the M06 F1 L01 zero-baseline restoration — and is now this leg's sole deliverable. Slug retained (`01-lint-format-restoration-and-gate-audit`) for branch-history continuity; the leg's effective scope is "lint + format restoration."

## Objective

Restore the `ruff check` zero-error and `ruff format --check` zero-would-reformat baselines that M06 F1 L01 established.

## Context

The 2026-05-15 maintenance report's Cat-4 finding is that `ruff check the_one/ tests/` returns 69 errors (32 E501, 13 I001, 10 F401, 7 E402, 3 F841, 2 N806, 2 N802) and `ruff format --check the_one/ tests/` returns 81 files would-reformat — both started at 0 after M06 F1 L01.

The original framing was that this proves CI gate evasion (Concourse `&&`-chained gate didn't fail-fast on PRs #45-#55). With Concourse being removed in Leg 4, the gate-evasion concern dissolves — but the baseline restoration is still valuable as code hygiene independent of any CI substrate. A replacement enforcement mechanism (pre-commit hook, `make doctor`-style lint check, or none) is a M10 decision once the no-CI shape settles.

Predominantly the violations are in test files (65 of 69 errors), so production-code impact is modest. Production code lint hits at scaffold time: `agent/core.py:98 E501`, `interfaces/web/api.py:660 E402`, `mcp/_tool_provider.py:38 I001`, `mcp/client.py:263 E501`. Nine core MCP files would reformat (`mcp/_pool.py`, `mcp/_tool.py`, `mcp/_tool_provider.py`, `mcp/cache_cleanup.py`, `mcp/client.py`, `mcp/errors.py`, `mcp/transports/stdio.py`, `mcp/transports/streamable_http.py`).

## Inputs

- `pyproject.toml` `[tool.ruff]` configuration (excludes, line-length, target-version)
- Current 69 lint errors and 81 would-reformat baseline (snapshot at scaffold-time; small drift acceptable; current production-side hits are 4 across `agent/core.py`, `interfaces/web/api.py`, `mcp/_tool_provider.py`, `mcp/client.py` — the remaining 65 are in `tests/`)

## Outputs

- All ruff lint errors fixed (0 baseline)
- All ruff format diffs applied (0 would-reformat baseline)
- Single commit on the flight branch with the cleanup

## Acceptance Criteria

- [ ] `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` exits 0 with "All checks passed!"
- [ ] `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` exits 0 with "X files already formatted"
- [ ] No production logic change. Acceptable production changes are limited to: format-driven whitespace, import-order, line-wrap, deletion of provably-unused imports, hand-fix of E501 via wrapping/extraction (no behavior change), and resolution of E402 (`interfaces/web/api.py:660`) via either reordering or a justified `# noqa: E402` comment naming the reason (e.g., "side-effect import; must precede X")
- [ ] No NEW test failures or collection errors introduced beyond the pre-existing baseline (6 `asgi-lifespan` collection errors + 1 `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` failure — both fixed in Leg 2). Acceptance is "matching the pre-leg baseline," not absolute zero — Leg 2 is the leg that drives broad pytest to clean exit-code 0.

## Verification Steps

- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` — exit 0
- `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` — exit 0
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ --output-format=concise | wc -l` — returns 0 lines (belt-and-suspenders over `exit 0`)
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ --statistics` — confirm no error types remain
- `cd /home/cprch/projects/the-one && git diff --stat HEAD~1` — review the cleanup commit; verify no logic changes

## Implementation Guidance

1. **Restore the lint baseline**
   - `cd /home/cprch/projects/the-one && ruff check .` to capture current state
   - `cd /home/cprch/projects/the-one && ruff check --fix .` — applies the autofixable items (currently ~23, small drift acceptable)
   - `cd /home/cprch/projects/the-one && ruff check --fix --unsafe-fixes .` — applies the unsafe-fixable items (currently ~3; review the diff carefully; unsafe fixes can include removing `# noqa` directives or adding `if` guards)
   - Hand-fix the remaining ~46 errors. Common patterns:
     - `E501 line-too-long`: wrap lines, extract intermediate variables, or break long strings into adjacent literals
     - `F401 unused import`: delete the import (verify it's truly unused, not pulled in for side-effect)
     - `F841 unused variable`: prefix with `_` or delete the assignment
     - `E402 module-level import-not-at-top`: at `interfaces/web/api.py:660`, READ the surrounding code first. If the import placement is intentional (side-effect ordering — env var must be set first, or a module-init dependency), add `# noqa: E402  # <reason>` with the reason inline. If it's just sloppy ordering, move the import to the top of the file.
     - `N806 non-lowercase variable in function`: rename (the M05-era `REMOVED` set in `db/schema.py` was the prior offender; check if it's resurfaced)
     - `N802 function name should be lowercase`: rename, or `# noqa: N802` for protocol-required names
     - `I001 unsorted imports`: should be auto-fixed by `--fix`; if not, `ruff check --fix --select I .` on the specific file
   - `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` — verify 0 errors
   - Common pitfall: `--fix` does NOT fix `E501`; line-too-long must be hand-fixed.

2. **Restore the format baseline**
   - `cd /home/cprch/projects/the-one && ruff format the_one/ tests/` — applies the 81-file diff
   - `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` — verify "all files already formatted"
   - Re-run `ruff check` to confirm format pass did not introduce new lint errors (it shouldn't, but verify)

3. **Verify the broad pytest collection still works**
   - `cd /home/cprch/projects/the-one && pytest --collect-only -q | tail -5` — should report 1683+ collected, 0 errors at collection time
   - Note: this leg does not fix the 6 `asgi-lifespan` collection errors (Leg 2's job) or the `test_sandbox_eperm_on_unshare` failure (Leg 2's job). Those persist after this leg.

4. **Commit**
   - Stage all changes: `cd /home/cprch/projects/the-one && git add -A`
   - Inspect: `git diff --cached --stat`
   - Commit on the current branch (`flight/01-integrity-gate-restoration`) with message: `flight/01: restore ruff lint+format zero baseline\n\nMission: 09`
   - Do NOT push yet — the flight uses a single end-of-flight review + commit pattern; per crew protocol, signal `[HANDOFF:review-needed]` at leg end, NOT `[COMPLETE:leg]`.
   - Update leg status from `in-flight` to `landed` (NOT `completed` — completion happens at flight close).
   - Update `flight-log.md` with a Leg Progress entry.

## Edge Cases

- **Unsafe autofix removes a `# noqa` that was load-bearing**: review every `--fix --unsafe-fixes` diff hunk; if removal seems load-bearing, restore the `# noqa` with an inline explanation comment.
- **A line that needs to stay long for clarity**: prefer `# noqa: E501` with an inline reason over awkward wrapping. Tests are the most common case where this is defensible.
- **F401 unused import that's actually used via `__init__.py` re-export**: add to `__all__` or use `# noqa: F401` with explanation.
- **E402 at `interfaces/web/api.py:660` is load-bearing** (side-effect ordering): authorized to add `# noqa: E402` with an inline comment naming the reason. This counts as a legitimate production change under the acceptance criterion.

## Files Affected

- Throughout `tests/` (majority of the 69 errors / 81 reformats live here)
- `the_one/mcp/_pool.py`, `_tool.py`, `_tool_provider.py`, `cache_cleanup.py`, `client.py`, `errors.py`, `transports/stdio.py`, `transports/streamable_http.py` — format diff + 2 lint fixes
- `the_one/agent/` — 1 lint fix (`agent/core.py:98 E501`)
- `the_one/interfaces/` — 1 lint fix (`interfaces/web/api.py:660 E402`)
- `flight-log.md` — Leg Progress entry

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest at pre-leg baseline; Leg 2 + Leg 3 work still pending)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Commit the cleanup work (single commit on the flight branch)
