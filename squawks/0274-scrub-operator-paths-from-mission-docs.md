# Squawk 0274: Remove the operator's username and home paths from mission docs

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: 2026-11-14

## Report
Older Flight Control artifacts quote absolute paths that carry the operator's username and home directory (WSL home paths, Windows profile paths). The operator asked (2026-10-27, sortie 06 debrief) that paths in planning docs be de-identified. Replace them with placeholders (`<home>`, `<user>`, `<repo>`, `<main checkout>`) without changing meaning. Sortie 06's own flight log was scrubbed on its debrief branch.

## Evidence
- `grep -rln "<operator username>" missions/` lists 119 files at `3b3d42a` (the literal username is not repeated here); examples: `missions/01-structural-foundation/flights/01-architecture-blueprint/legs/01-target-architecture.md`, `missions/16-llm-provider-hardening/flights/02-anthropic-tool-input-schema/legs/01-sanitize-tool-schema.md`, `missions/25-workbench-navigation/flights/05-window-chrome/legs/01b-windows-apparatus-input.md`.
- Also check `sorties/`, `squawks/`, `maintenance/`, `tests/behavior/` runs and `docs/`.

## Corrective Action
Scope covered: `missions/`, `sorties/`, `squawks/`, `maintenance/` and `tests/behavior/` (`docs/` and `maintenance/` held none). 385 lines in 134 files were changed with the edit tool, by pattern: `/home/<user>/...` became `~/...` (the bulk; `$HOME`-relative meaning kept), the username inside the encoded scratchpad directory names (`/tmp/claude-1000/-home-<name>-projects-the-one/...`) became `<user>`, `C:\Users\<user>\` and `\home\<user>\` kept their shape with `<user>`, one `'/home/<user>'` became `'~'`, and one prose "run as user <name>" became "run as the operator's own user, `<user>`". No quoted command output had its meaning changed (only the path prefix). Squawks 0223, 0248 and 0358 were in scope and edited (0358 belongs to the other Developer's batch; only its one path was touched).

Not changed: the three behavior-test run logs under `tests/behavior/agent-schedules-follow-up/runs/` (one line each). `.flightops/ARTIFACTS.md` says a behavior test run is terminal and never edited after the run completes, so they were left alone. The Flight Director should decide whether to scrub them anyway. Also left: `tests/test_windows_test_copy.py` mentions the username but is test code outside the squawk's covered scope.

## Verification
`grep -rn <username> missions sorties squawks tests/behavior --exclude-dir=runs` (the literal username, not repeated here) returns nothing (0 matches). The only remaining matches in the covered scope are the 3 run-log lines above. Spot-read of edited lines (for example `missions/25-workbench-navigation/.../01a-windows-apparatus-core.md`, `missions/35-rich-visuals-in-chat/.../flight-log.md`, `missions/01-.../05-ci-pipeline-hardening.md`) shows each sentence keeps its meaning.

Review fixes: the two Python snippets (`03-fastmcp-hello-fixture.md`, `05a-fixture-extension-and-integration-tests.md`) that held a quoted `'~/projects/the-one'` now hold `'<repo>'` as an evident placeholder; the one search pattern turned into `'~'` (`05-ci-pipeline-hardening.md`) is back to `grep -r '/home/<user>' ci/pipeline.yml`. A sweep of the added lines in the four scrubbed directories found no other quoted `~` or `~/` literal or search pattern.

Left on purpose: three behavior-test run logs under `tests/behavior/agent-schedules-follow-up/runs/` and `tests/test_windows_test_copy.py` still contain the username. Run logs are never edited, and the test file is code outside this squawk's scope.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
