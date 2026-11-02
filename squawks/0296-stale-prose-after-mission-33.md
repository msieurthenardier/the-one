# Squawk 0296: Remove prose that still describes pre-M33-F4 routines and the retired MCPs tab

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-01

## Report
Mission 33 Flight 4 removed routine targets and made the scheduler live, and Flight 1 folded the MCPs tab into Tools, but reference prose still describes the old state. Crew agents read `the_one/agents.md` as canonical, so stale lines mislead later legs. From maintenance report 2026-10-30, finding #9 (the agents.md lines were also recorded in the Mission 33 debrief's action items).

## Evidence
- `the_one/agents.md:2837`: "A target left out is not re-validated, so a `missing` chat target may stay until re-pointed" (contradicts the "No target" bullet at 2838).
- `the_one/agents.md:2840`: heading "no runner yet, nothing sets `turn_info["routine"]`"; `:2845`: "Run now only, nothing schedules yet".
- `SECURITY-MODEL.md:304`: "per-tool checkboxes on that agent's MCPs tab".
- `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js:31-38`: header comment omits the Rules, Notes and Routines groups.
- `the_one/interfaces/web/app.py::_get_or_restore_session` docstring describes the earlier cache short-circuit.
- `the_one/db/repositories.py:2433-2434`: says the resolver imports `list_all`; `the_one/agent/factory.py:402` reads `list()` and `resolver.py` makes no repository call. (`the_one/tools/resolver.py:6` says the same, but sortie 07 rewrites that file; leave it to the sortie.)

## Corrective Action
- `agents.md` (PUT precedence): dropped the "`missing` chat target" sentence; it now points to the "No target" bullet.
- `agents.md` routine-turn-path heading: marked as written before the runner; the runner now sets `turn_info["routine"]`.
- `agents.md` runner heading: marked as written when only Run now existed; the leg 5 `RoutineScheduler` also schedules into the registry.
- `SECURITY-MODEL.md`: "MCPs tab" is now the "MCP servers" section of the agent's Tools tab.
- `agent-drawer.js` header comment: added the Needs attention (notices) group from sortie 07; Rules, Notes and Routines were already described.
- `app.py::_get_or_restore_session` docstring: states there is no cache short-circuit and the rebind is skipped only while a turn is in flight.
- `repositories.py` `ToolConfigRepository` class and `list_all` docstrings: no longer say the resolver imports `list_all`; the factory reads `list()`.
- `resolver.py:6` (sortie 07 had not fixed it): now says `AgentFactory.create()` reads `ToolConfigRepository.list()` and the module makes no repository call.

## Verification
`grep -n "no runner yet\|nothing schedules yet\|missing\` chat target\|MCPs tab" the_one/agents.md SECURITY-MODEL.md` returns only historical, marked-as-retired mentions; each listed comment and docstring states current behaviour.

Result: the grep returns three agents.md lines (938, 2224, 2281), all dated "after the MCPs tab folded into Tools (M33 F1 L06)" or "MCPs tab (M31 F2 L07b), now the Tools tab's ..." records. SECURITY-MODEL.md: none.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 60`: 338 passed.
- Tests that read agents.md or SECURITY-MODEL.md: 645 passed; `tests/test_mcp_wire_shapes.py::test_httpx2_uses_the_os_trust_store_unless_overridden` fails in this environment and is unrelated to prose (deselected).
- `ruff check` and `ruff format --check` on app.py, repositories.py, resolver.py: clean.

`grep -n "no runner yet\|nothing schedules yet\|missing\` chat target\|MCPs tab" the_one/agents.md SECURITY-MODEL.md` returns only historical, marked-as-retired mentions; each listed comment and docstring states current behaviour.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch states security-model residual risks, 0298 and 0299), batch review of the 2026-11-01 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]`. Comment, docstring and prose edits only; the static UI guards passed for the `agent-drawer.js` comment.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-01` commit on `squawk/turnaround-2026-11-01`. Unit tier under `THE_ONE_TEST_NETNS=1`: 8560 passed, 23 skipped, 3 failed (the known `tests/test_desktop_host.py` baseline, unchanged from main).
