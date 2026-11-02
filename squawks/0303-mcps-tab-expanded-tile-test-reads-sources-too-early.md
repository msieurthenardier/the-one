# Squawk 0303: an MCPs-tab browser test reads the agent's sources before the surface is attached

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-31
**Completed**: 2026-11-02

## Report
`tests/browser/test_studio_mcps_tab.py::test_set_sources_keeps_an_expanded_unsaved_tile` fails intermittently on an unchanged base with `IndexError: list index out of range`. After the Self-configuration switch shows checked, it reads `GET /api/agents/keep-agent` once and indexes the first `mcp_source_ids` entry other than the seeded one, but the loopback surface may not be attached yet when that read lands. The switch's checked state is not proof that the attachment write has finished.

## Evidence
- Sortie 07 baseline (worktree, `628a97dd`, quiet host, `--parallel 3`): the `agents` lane's only failure; 172 passed.
- Two isolated re-runs on the same base: 1 passed, 1 failed (same `IndexError`).
- `tests/browser/test_studio_mcps_tab.py:1139-1143` — `expect(toggle).to_be_checked(...)`, then `surface = [i for i in _get_agent(...)["mcp_source_ids"] if i != sid][0]` with no wait.
- **A second instance in the same file** (2026-10-31, sortie 07 leg 2 fix pass, `agents` lane): `test_self_configuration_enable_then_save_keeps_the_surface` failed once with `IndexError` at `:1100` (`_get_agent(app_clean, "sc-keep-agent")["mcp_source_ids"][0]`, the same read right after the switch). Isolated runs: 8/8 on the base, 8/8 on the branch. The fix covers both tests (one shared poll helper).

## Corrective Action
Added `_wait_surface_id(base_url, name, exclude=())` to `tests/browser/test_studio_mcps_tab.py`: it polls `GET /api/agents/{name}` (100 ms steps, 10 s monotonic deadline, no fixed sleep) until a source id outside `exclude` is attached, then returns it. Both sites use it (`test_self_configuration_enable_then_save_keeps_the_surface`, `test_set_sources_keeps_an_expanded_unsaved_tile`). Test-only; no product change.

## Verification
Each of the two tests passed 10 of 10 isolated runs (`THE_ONE_TEST_NETNS=1`, `scripts/run-tests.sh -m browser <test> -x`), and the `agents` lane passed in the Mission 34 Flight 1 Leg 2 `--parallel 3` run (174 passed). Not falsified (a race fix; the unfixed code failed only intermittently under load).

## Sign-Off
**Reviewer**: Mission 34 Flight 1 flight review (Reviewer agent, Sonnet)
**Verdict**: confirmed
**Commit**: the Mission 34 Flight 1 commit on branch flight/01-test-suite-runtime-ii (see the flight PR)

## Disposition
- **Deferred** (2026-10-31, Flight Director, mid-sortie 07): out of the sortie's scope; logged per the agentic workflow's out-of-scope rule. **Revisit trigger:** the next squawk turnaround, or Mission 34 Flight 1's `browser-lane-budgets-and-flakes` leg, whichever comes first. Until then, a failure of this test alone in the `agents` lane is accepted as this squawk when an isolated re-run passes.
