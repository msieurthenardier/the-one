# Leg: 01-lint-format-restoration-and-gate-audit

**Status**: ready
**Flight**: [Integrity Gate Restoration](../flight.md)

## Objective

Restore the `ruff check` zero-error and `ruff format --check` zero-would-reformat baselines that M06 F1 L01 established, and prove via deliberate-violation experiment that the Concourse pipeline's gate at `ci/pipeline.yml:24` actually rejects violations.

## Context

The 2026-05-15 maintenance report's central finding is that the CI integrity gate posture M06 codified was silently eroded across M07 and M08. Symptoms: `ruff check the_one/ tests/` returns 69 errors (32 E501, 13 I001, 10 F401, 7 E402, 3 F841, 2 N806, 2 N802) and `ruff format --check the_one/ tests/` returns 81 files would-reformat — both started at 0 after M06 F1 L01. The pipeline's gate command is `&&`-chained under `set -exc`, so it should have halted any PR that touched code with violations. The fact that the violations are on `main` post-M07 and post-M08 means either (a) CI never ran against PRs #45-#55, (b) the gate is being skipped before push, or (c) the gate command is no longer doing what it appears to.

Architect's framing: "The finding is 'CI integrity gate is not enforcing what we believe it enforces'" — restoring the baseline is necessary but not sufficient; the deliberate-violation experiment is the actual deliverable.

Predominantly the violations are in test files (60+ of 69 errors), so production-code impact is modest. Core MCP files affected: `mcp/_tool_provider.py:38 I001`, `mcp/client.py:263 E501`. Nine core MCP files would reformat (`mcp/_pool.py`, `mcp/_tool.py`, `mcp/_tool_provider.py`, `mcp/cache_cleanup.py`, `mcp/client.py`, `mcp/errors.py`, `mcp/transports/stdio.py`, `mcp/transports/streamable_http.py`).

Design decisions from flight:
- Deliberate-violation experiment result lands in `flight-log.md` under Decisions (not a separate appendix in the maintenance report)
- Run the experiment FIRST so a failure case can expand leg scope before cleanup; cleanup work is wasted if the gate doesn't actually enforce

## Inputs

- `pyproject.toml` `[tool.ruff]` configuration (excludes, line-length, target-version)
- `ci/pipeline.yml` (gate at line 24, `&&`-chained)
- Throwaway branch capability via `git checkout -b ci-gate-violation-experiment`
- Concourse `local` target authenticated; `fly -t local trigger-job` available
- Current 69 lint errors and 81 would-reformat baseline (snapshot at scaffold-time; small drift acceptable)

## Outputs

- All ruff lint errors fixed (0 baseline)
- All ruff format diffs applied (0 would-reformat baseline)
- Throwaway branch created, pushed, experiment run, branch deleted
- `flight-log.md` Decisions section populated with experiment result (Concourse build URL + observed gate behavior)

## Acceptance Criteria

- [ ] `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` exits 0 with "All checks passed!"
- [ ] `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` exits 0 with "X files already formatted"
- [ ] Deliberate-violation experiment executed; result documented in `flight-log.md`
- [ ] If experiment passed (gate rejected): leg complete
- [ ] If experiment failed (gate did NOT reject): pipeline issue documented in `flight-log.md` Anomalies; leg scope expanded to include CI repair; leg NOT marked complete until gate is proven to reject
- [ ] No production source change beyond format-driven whitespace / import-order / line-wrap changes (i.e., the code changes are purely lint/format hygiene)
- [ ] No NEW test failures or collection errors introduced beyond the pre-existing baseline (6 `asgi-lifespan` collection errors + 1 `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` failure — both fixed in Leg 2). Acceptance is "matching the pre-leg baseline," not absolute zero — Leg 2 is the leg that drives broad pytest to clean exit-code 0.

## Verification Steps

- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` — exit 0
- `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` — exit 0
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ --statistics` — confirm no error types remain
- `cd /home/cprch/projects/the-one && git diff --stat HEAD~1` — review the cleanup commit; verify no logic changes
- Read `flight-log.md` Decisions section — confirms deliberate-violation result is captured
- Concourse build URL in flight log opens to a build that either (a) successfully rejected the violation OR (b) shows the diagnosed CI issue and the fix that made it reject

## Implementation Guidance

1. **Run the deliberate-violation experiment FIRST**
   - **Pre-flight check**: confirm the live pipeline definition still contains the gate command before triggering. `fly -t local get-pipeline -p the-one | grep -A5 "test:"` — confirm `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` is in the test task's command. If it's not, the pipeline was set with a stale config; `set_pipeline` first.
   - The `ci/pipeline.yml` test task reads from `${WORKSPACE_PATH}` as a host bind-mount (`-v "${WORKSPACE_PATH}:/src:ro"` then `cp -r /src /work`). This means the experiment has **two valid shapes**; pick whichever the operator's workflow prefers:
     - **Option A (local-only, cheaper)**: introduce a single deliberate violation directly in the working tree on `main` (e.g., add a 200-char line to `the_one/main.py` to trigger E501). Trigger the pipeline: `fly -t local trigger-job -j the-one/test -w`. The pipeline reads the violating workspace via bind-mount. Observe outcome. Revert the local change: `git checkout the_one/main.py`. No branch, no commit, no push, no remote cleanup.
     - **Option B (branch+push)**: create throwaway branch `ci-gate-violation-experiment`; commit the violation; push; trigger pipeline; observe outcome; `git push origin --delete ci-gate-violation-experiment`. Required only if the bind-mount assumption breaks (e.g., `WORKSPACE_PATH` points elsewhere).
   - Watch the Concourse build; capture the URL.
   - If the gate REJECTS (build fails at the lint step): great. Record success in `flight-log.md` Decisions with the build URL.
   - If the gate PASSES (build succeeds despite the violation): record the anomaly. Investigate `ci/pipeline.yml`'s test task — confirm the `&&` chain is structurally intact, the container has `ruff` installed, the `cd` to the right directory is happening, exit codes aren't being swallowed by shell wrapping, and the bind-mounted workspace IS the violating tree (not a stale snapshot). Common failure modes: pipeline pinned to a config that lacks the gate (this is why the pre-flight check is step 1); stale image without ruff; `set -exc` getting overridden; the gate command silently replaced. Fix the pipeline; re-run the experiment until it rejects.
   - **Do NOT proceed to step 2 until the gate is proven to reject.**
   - **Branch-cleanup sanity-check (only if Option B was used)**: after `git push origin --delete`, run `fly -t local builds -j the-one/test | head -5` and confirm no new build was triggered by the branch deletion — the project's pipeline has no `git` resource so this should be a no-op, but worth confirming since the whole leg is about gate behavior verification.

2. **Restore the lint baseline**
   - `cd /home/cprch/projects/the-one && ruff check .` to capture current state
   - `cd /home/cprch/projects/the-one && ruff check --fix .` — applies the 23 autofixable items
   - `cd /home/cprch/projects/the-one && ruff check --fix --unsafe-fixes .` — applies the 3 unsafe-fixable items (review the diff carefully; unsafe fixes can include removing `# noqa` directives or adding `if` guards)
   - Hand-fix the remaining ~46 errors. Common patterns:
     - `E501 line-too-long`: wrap lines, extract intermediate variables, or break long strings into adjacent literals
     - `F401 unused import`: delete the import (verify it's truly unused, not pulled in for side-effect)
     - `F841 unused variable`: prefix with `_` or delete the assignment
     - `E402 module-level import-not-at-top`: move the import to the top of the file, or use `# noqa: E402` with explanation if there's a legitimate reason (e.g., needs env var set first)
     - `N806 non-lowercase variable in function`: rename (the M05-era `REMOVED` set in `db/schema.py` was the prior offender; check if it's resurfaced)
     - `N802 function name should be lowercase`: rename, or `# noqa: N802` for protocol-required names
     - `I001 unsorted imports`: should be auto-fixed by `--fix`; if not, `ruff check --fix --select I .` on the specific file
   - `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` — verify 0 errors
   - Common pitfall: `--fix` does NOT fix `E501`; line-too-long must be hand-fixed.

3. **Restore the format baseline**
   - `cd /home/cprch/projects/the-one && ruff format the_one/ tests/` — applies the 81-file diff
   - `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` — verify "all files already formatted"
   - Re-run `ruff check` to confirm format pass did not introduce new lint errors (it shouldn't, but verify)

4. **Verify the broad pytest collection still works**
   - `cd /home/cprch/projects/the-one && pytest --collect-only -q | tail -5` — should report 1683+ collected, 0 errors at collection time
   - Note: this leg does not fix the 6 `asgi-lifespan` collection errors (Leg 2's job) or the `test_sandbox_eperm_on_unshare` failure (Leg 2's job). Those persist after this leg.

5. **Commit**
   - Stage all changes: `cd /home/cprch/projects/the-one && git add -A`
   - Inspect: `git diff --cached --stat`
   - Commit with message describing the gate experiment result: e.g., `chore: restore ruff lint+format zero baseline; deliberate-violation experiment confirmed gate rejects (build #XXX)`
   - Push to a maintenance flight branch
   - Trigger a fresh CI run on the merge branch to confirm the gate passes cleanly with the cleanup landed

## Edge Cases

- **Unsafe autofix removes a `# noqa` that was load-bearing**: review every `--fix --unsafe-fixes` diff hunk; if removal seems load-bearing, restore the `# noqa` with an inline explanation comment.
- **A line that needs to stay long for clarity**: prefer `# noqa: E501` with an inline reason over awkward wrapping. Tests are the most common case where this is defensible.
- **F401 unused import that's actually used via `__init__.py` re-export**: add to `__all__` or use `# noqa: F401` with explanation.
- **Deliberate-violation experiment passes (gate rejects) but the cleanup commit then fails the gate on push**: indicates ruff config drift between branches; verify `pyproject.toml`'s `[tool.ruff]` section is identical on both branches.
- **`make` not available on the host**: this leg doesn't add a make target (Leg 2 does); not a blocker here.

## Files Affected

- Throughout `tests/` (majority of the 69 errors / 81 reformats live here)
- `the_one/mcp/_pool.py`, `_tool.py`, `_tool_provider.py`, `cache_cleanup.py`, `client.py`, `errors.py`, `transports/stdio.py`, `transports/streamable_http.py` — format diff + 2 lint fixes
- `the_one/agent/` — 1 lint fix
- `the_one/interfaces/` — 1 lint fix
- `flight-log.md` — Decisions section populated with experiment result
- Possibly `ci/pipeline.yml` — only if the deliberate-violation experiment reveals a pipeline issue requiring repair

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exits 0 modulo the two known failures Leg 2 will address)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in `flight.md`
- [ ] Commit all changes together (code + artifacts)
