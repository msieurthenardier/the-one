# Leg: activate-refresh-convention

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Audit all three areas' activate() methods for data refresh, fix any gaps, and document the convention in app.js.

## Context

- Flight 02 debrief recommended establishing a cross-area refresh convention
- All three areas already implement activate() with data refresh:
  - **Chat**: reconnects WS if needed, fetches agents, checks providers (added in Leg 4)
  - **Admin**: refreshes settings or provider list depending on current category
  - **Studio**: calls loadAll() to refresh agents, providers, KBs, and MCP sources
- The convention is already followed but not documented

## Inputs

- `the_one/interfaces/web/static/js/app.js` — `switchTo()` calls `activate()` on area switch
- All three area files with their activate() implementations

## Outputs

- Convention documented in app.js as a comment near the `switchTo` function
- Any missing refresh gaps fixed (audit result)

## Acceptance Criteria

- [ ] Comment block in app.js near `switchTo()` documenting that `activate()` must refresh data
- [ ] All three areas' activate() methods confirmed to refresh their data on area switch
- [ ] No functional gaps found (or gaps fixed if discovered)

## Verification Steps

- Read app.js and verify convention comment exists
- Review all three activate() methods — each should fetch/refresh its data

## Implementation Guidance

1. **Audit activate() implementations** (read all three area files):
   - Chat: ✓ reconnects WS, fetches agents, checks providers
   - Admin: ✓ refreshes settings or providers based on current category
   - Studio: ✓ calls loadAll() to refresh everything
   - If any gaps found, fix them

2. **Add convention comment** in `app.js` above the `activate()` call in `switchTo()`:
   ```javascript
   // Convention: activate() must refresh the area's data so changes made in
   // other areas (e.g. adding a provider in Admin) are reflected immediately.
   ```

3. **Update flight log** with audit results

## Files Affected

- `the_one/interfaces/web/static/js/app.js` — Convention comment
