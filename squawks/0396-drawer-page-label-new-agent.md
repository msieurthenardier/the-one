# Squawk 0396: The drawer's "Looking at" line reads "Agents › New" on the New Agent editor

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

## Report
On `#agents/~new`, the GleepGlorp drawer's "Looking at" line reads "Agents › New", while the editor's
title, and the page line the server builds for the same page, say "New Agent". The Windows and macOS
evidence in Mission 36 Flight 3 Leg 9 shows this after a create fill.

Reproduce: open Agents, click New, open the drawer, and read the line under its title. Align the
client's create label with the server's page names, so the operator sees the same words the model
does.

## Evidence
- `the_one/interfaces/web/static/js/router.js:572`, `if (p.create) item = 'New';` (the
  `describeCurrent` parts the drawer shows).
- `the_one/gleepglorp/page.py:61-62`, `CREATE_NAMES = {"agents": "New Agent", …}` (the stored page
  line, e.g. `Agents › New Agent`).

## Corrective Action
*(written at completion)*

## Verification
A drawer browser test on `#agents/~new` asserts the "Looking at" text equals the page line's words.
Check the other create routes (`#library/mcp/~new` and others) the same way.
