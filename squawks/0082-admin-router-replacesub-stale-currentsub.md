# Squawk 0082: `App.router.replaceSub` leaves the router's `currentSub` stale, so a same-document `hashchange` back to that exact URL no-ops

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-18
**Completed**: —

## Report

`app.js`'s router keeps its own `currentId`/`currentSub` closure variables,
updated only inside `switchTo()`. `App.router.replaceSub(sub)` — the helper
every within-area category/tab switch uses (Admin's `doSetCategory`, Studio's
agent/MCP-source selection, etc.) — updates the URL via
`history.replaceState(...)` **directly**, bypassing `switchTo()` entirely, so
it never updates `currentSub`. Its own doc comment says as much ("Calling this
does NOT fire hashchange … so it does not loop back through switchTo") but
does not flag the side effect: `currentSub` is left pointing at whatever sub
was active the last time `switchTo()` actually ran (typically the area's
sub-state at the last full navigation or cross-area switch).

Consequence: if an operator is on `#admin/X` (reached via `switchTo`, so
`currentSub === 'X'`), clicks to a different in-area category `Y` (via
`replaceSub`, URL becomes `#admin/Y`, `currentSub` stays stale at `'X'`), and
then navigates — by pasting/typing a URL, a bookmark, or any `location.href`/
`page.goto`-style navigation — back to `#admin/X`, the resulting `hashchange`
event's `switchTo('admin', 'X')` hits the early-return dedup check
(`if (areaId === currentId && sub === currentSub) return;`) because the stale
`currentSub` already reads `'X'`. The handler no-ops: the URL updates but the
visible panel does not change, silently stranding the operator on category
`Y`'s screen while the address bar reads `#admin/X`.

Found while writing Mission 24 Flight 6 Leg 4's
`test_flow_admin_knowledge_settings.py::test_dirty_confirm_on_navigate_away`:
a second `page.goto()` back to `#admin/knowledge` after a `replaceSub`-driven
click away to `#admin/general` reproduced exactly this — the assertion caught
the page still showing "General". Not scoped to the Knowledge panel or to
this leg: `doSetCategory` (all of Admin's categories: general/providers/
tools/knowledge/design-language) and Studio's equivalent all call
`replaceSub`, so any of them can leave `currentSub` stale for the same
class of bug. The test was rewritten to navigate back via the in-SPA
section-nav click (the realistic path an operator actually uses to return to
a panel) rather than a raw `goto()`, which avoids the bug but does not fix it.

## Evidence

- `the_one/interfaces/web/static/js/app.js::router.replaceSub` — `if
  (location.hash === newHash) return; history.replaceState(null, '',
  newHash);` — no update to the enclosing `currentSub`/`currentId` closure
  variables declared earlier in the same IIFE.
- `the_one/interfaces/web/static/js/app.js::switchTo` — `if (areaId ===
  currentId && sub === currentSub) return;` is the FIRST check in the
  function, before any hydrate/render happens.
- `the_one/interfaces/web/static/js/areas/admin.js::doSetCategory` — calls
  `App.router.replaceSub(currentCategory)` on every category change
  (general/providers/tools/knowledge/design-language) — the call site
  reproduced against.
- Reproduced live: `tests/browser/test_flow_admin_knowledge_settings.py`
  (pre-fix version) — `page.goto(f"{app_clean}#admin/knowledge")` after a
  `replaceSub`-driven navigation to `#admin/general` left the page-title
  reading "General" for the full 8s Playwright poll window.

## Disposition

**Deferred**: found incidentally while writing a browser test for Mission 24
Flight 6 Leg 4 (Knowledge settings panel, tiered LOW risk, no separate design
review). The bug lives in `app.js`'s shared router, not in the Knowledge panel
or in this leg's surface — fixing it is a shared-interface change (every area
using `replaceSub` is a potential caller) that deserves its own review rather
than a same-leg inline fix.

**Revisit when**: the router/`switchTo`/`replaceSub` contract is next touched,
or the next time an operator-visible symptom of this shape is reported (a
pasted or bookmarked in-area URL that "does nothing"). Candidate fixes to
weigh at that time: have `replaceSub` also update `currentSub` directly (the
narrowest fix — it already knows the target sub); or fold `switchTo`'s
same-area-sub-change branch to re-derive its dedup check from
`location.hash` instead of the closure variable, since the closure is what
actually goes stale.
