# Squawk 0334: CLAUDE.md — choose gate lanes by what asserts on a shared list

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: —

## Report
Sortie 10 leg 3 part A added a fifth Library group and a fifth Prompts layer. Its per-part gate ran only the lanes owning the changed files (`library`, `routing`, `contracts-controls`). Twelve count and label pins in `agents`, `providers` and `settings` then failed at the flight's full gate, costing a fix round and a three-lane re-run. CLAUDE.md "Testing" has no rule for picking lanes when a shared list, menu, registry or table changes.

## Evidence
- `sorties/10-secrets/flight-log.md` — the "Part A pins found at G2" entry and the "Debrief item" note.
- The files fixed: `test_flow_agents_root_heading`, `test_flow_studio_navigation`, `test_flow_provider_library`, `test_studio_mcps_tab`, `test_flow_admin_encryption_page`.

## Corrective Action
*(written at completion)* Planned: one short paragraph in CLAUDE.md "Testing", near the lane list. When a change adds, removes or renames an entry in a shared list, menu, registry or table, grep `tests/browser/` for its old count and labels, and run every lane whose files match, besides the owning lanes.

## Verification
The paragraph is present, and `make test-unit` passes; no test pins CLAUDE.md prose beyond the existing guards.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
