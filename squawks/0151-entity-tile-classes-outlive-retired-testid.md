# Squawk 0151: The entity-tile CSS classes outlive their retired testid without a note

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
The `entity-tile` testid is retired, but the `entity-tile*` CSS classes are still live on the Built-in tools and Providers tiles. Anyone reading the retired-selector registry can reasonably conclude the tile component is gone. Found by routine maintenance 2026-10-08 (finding #30).

## Evidence
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` ~50-58, `providers-list.js` ~83-104
- `docs/ui-testid-registry.md` "Retired testids" lists `entity-tile` with no mention of the classes

## Corrective Action
Added an `entity-tile` row to the "Retired testids" table in `docs/ui-testid-registry.md` (the id was in `RETIRED_SELECTORS` but not in the table) noting the testid is retired while the `entity-tile*` CSS classes are deliberately kept and live on `areas/admin/tools-grid.js` and `areas/admin/providers-list.js`.

## Verification
`tests/test_nav_helper.py` and `tests/test_ui_guards.py`: 92 passed (including the registry-coverage guard). Doc review of the new row.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
