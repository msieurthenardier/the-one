# Squawk 0151: The entity-tile CSS classes outlive their retired testid without a note

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
The `entity-tile` testid is retired, but the `entity-tile*` CSS classes are still live on the Built-in tools and Providers tiles. Anyone reading the retired-selector registry can reasonably conclude the tile component is gone. Found by routine maintenance 2026-10-08 (finding #30).

## Evidence
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` ~50-58, `providers-list.js` ~83-104
- `docs/ui-testid-registry.md` "Retired testids" lists `entity-tile` with no mention of the classes

## Corrective Action
*(written at completion)* Expected: a one-line note in the registry's retired table saying the testid is retired but the classes are deliberately kept, and where they're used.

## Verification
Doc review; `tests/test_nav_helper.py` registry-coverage guard still passes.

## Sign-Off
*(written at completion)*
