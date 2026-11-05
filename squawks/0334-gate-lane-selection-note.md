# Squawk 0334: CLAUDE.md — choose gate lanes by what asserts on a shared list

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: 2026-11-05

## Report
Sortie 10 leg 3 part A added a fifth Library group and a fifth Prompts layer. Its per-part gate ran only the lanes owning the changed files (`library`, `routing`, `contracts-controls`). Twelve count and label pins in `agents`, `providers` and `settings` then failed at the flight's full gate, costing a fix round and a three-lane re-run. CLAUDE.md "Testing" has no rule for picking lanes when a shared list, menu, registry or table changes.

## Evidence
- `sorties/10-secrets/flight-log.md` — the "Part A pins found at G2" entry and the "Debrief item" note.
- The files fixed: `test_flow_agents_root_heading`, `test_flow_studio_navigation`, `test_flow_provider_library`, `test_studio_mcps_tab`, `test_flow_admin_encryption_page`.

## Corrective Action
Added one paragraph to CLAUDE.md "Testing", directly after the "Each lane runs independently green" line that closes the per-area lane list. Bold lead-in "Choose gate lanes by what asserts on a shared list (squawk 0334)": when a change adds, removes or renames an entry in a shared list, menu, registry or table, grep `tests/browser/` and `tests/` for its old count and labels and run every matching lane besides the owning lanes. It cites the sortie 10 leg 3 part A case (12 pins in `agents`, `providers` and `settings`). No other file changed.

## Verification
`.venv/bin/python -m pytest tests/ --collect-only -q -k "claude_md or docs or nav_helper"` collected 92. `.venv/bin/python -m pytest tests/ -q -x --timeout 60 -k "claude_md or docs or nav_helper"`: 92 passed, 13138 deselected, 1 warning.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-11-05 squawk turnaround, scoped to the diff. `[HANDOFF:confirmed]`; the paragraph is accurate, sensibly placed and in house style.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-05` commit on `squawk/turnaround-2026-11-05`.
