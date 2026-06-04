# Leg: bring-tree-into-compliance

**Status**: ready
**Flight**: [Lint/Format Enforcement Gate](../flight.md)

## Objective
Bring the working tree to a zero ruff baseline (0 lint violations, 0 would-reformat) and remove the dead `# noqa: BLE001` vestiges — the one-time cleanup that the enforcement gate (Leg 2) will then hold.

## Context
- Maintenance report 2026-06-04, finding **Q1**: 78 ruff violations + 97 of 322 files would be reformatted; third recurrence of baseline drift.
- Breakdown: 33 I001 (unsorted-imports), 21 E501 (line-too-long), 10 F401 (unused-import), 6 N802 (invalid-function-name), 5 N818 (error-suffix-on-exception-name), 2 E402 (module-import-not-at-top), 1 N806 (non-lowercase-var). 43 of 78 are auto-fixable.
- Top offenders: `tests/test_connectors_discord.py` (14), `the_one/connectors/_inference.py` (4), `the_one/db/schema.py` (4), `tests/test_connectors_policy_gate.py` (4).
- The 10 `# noqa: BLE001` comments (in `api.py`, `connector_history.py`, `test_connectors_discord.py`) suppress a rule not in the selected ruleset (`select = ["E","F","I","N","W"]`) — dead no-ops.

## Inputs
- Current tree with 78 violations + 97 unformatted files.
- `pyproject.toml` ruff config (`[tool.ruff]` line-length 100, `[tool.ruff.lint] select = ["E","F","I","N","W"]`).

## Outputs
- Tree at 0 lint violations and 0 would-reformat.
- Dead `noqa: BLE001` comments removed.

## Acceptance Criteria
- [ ] `ruff check the_one/ tests/` → 0 errors
- [ ] `ruff format --check the_one/ tests/` → all files already formatted
- [ ] N802/N818 residuals resolved by an actual rename or a *scoped, justified* `noqa` (not a blanket suppression) — no naming-contract issue left silently suppressed
- [ ] No `# noqa: BLE001` comments remain (or `BLE` is added to `select` so they become meaningful — pick one and note the decision)
- [ ] Full test suite green (renames/import changes didn't break anything)

## Verification Steps
- `make lint` (or `ruff check the_one/ tests/`) → exits 0
- `ruff format --check the_one/ tests/` → "all files already formatted"
- `grep -rn "noqa: BLE001" the_one/ tests/` → no results (if removal chosen)
- `docker exec the-one pytest tests/ -q -x` → green

## Implementation Guidance

1. **Auto-fix the mechanical 43**
   - `ruff check --fix the_one/ tests/` clears I001 + F401. Review the diff (unused-import removal can occasionally remove a re-export — confirm none are intentional `__all__` surface).

2. **Format**
   - `ruff format the_one/ tests/` clears the 97 would-reformat files.

3. **Resolve the ~35 manual residuals**
   - E501 (21): wrap or restructure long lines.
   - N802 (6 invalid-function-name) / N818 (5 error-suffix) / N806 (1): these may be deliberate (e.g. a test helper mimicking an external name, or an exception class without an `Error` suffix). For each, decide: rename to satisfy the rule, or add a *targeted* `# noqa: N8xx` with a one-line justification. Do not blanket-suppress — a real naming-contract issue should be fixed, per the flight's divert criteria.
   - E402 (2 module-import-not-at-top): move the import, or justify with `# noqa: E402` if there's a load-order reason.

4. **Remove the dead BLE001 vestiges**
   - Either delete the 10 `# noqa: BLE001` comments, or add `"BLE"`/`"B"` to `select` if the team wants blind-except linting (a broader decision — if unsure, just remove the dead comments and leave the ruleset as-is).

5. **Re-run the suite** — renames and import reordering can break references; confirm green.

## Edge Cases
- **An N818 rename touches a public exception name** (e.g. `ConnectorAuthRequired` lacks an `Error` suffix): coordinate with Flight 03 Q2, which may delete that type entirely — check before renaming to avoid churn on a doomed symbol.

## Files Affected
- Many across `the_one/` and `tests/` (formatting); specifically `tests/test_connectors_discord.py`, `the_one/connectors/_inference.py`, `the_one/db/schema.py`, `tests/test_connectors_policy_gate.py` (lint residuals); `pyproject.toml` only if `BLE` is added to `select`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (not final)
- [ ] Commit all changes together (code + artifacts)
