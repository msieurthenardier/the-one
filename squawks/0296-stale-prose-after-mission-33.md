# Squawk 0296: Remove prose that still describes pre-M33-F4 routines and the retired MCPs tab

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

`grep -n "no runner yet\|nothing schedules yet\|missing\` chat target\|MCPs tab" the_one/agents.md SECURITY-MODEL.md` returns only historical, marked-as-retired mentions; each listed comment and docstring states current behaviour.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
