# Flight Debrief: Studio — Agent Builder

**Date**: 2026-04-23
**Flight**: [Studio — Agent Builder](flight.md)
**Status**: landed
**Duration**: 2026-04-23 (single session)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

The Studio area is fully functional: agent CRUD, tool toggles grouped by category, MCP/KB chip attachment, dirty tracking with save feedback, and inline delete confirmation. All 13 UAT acceptance criteria passed on the deployed application via Concourse.

### Mission Criteria Advanced

- [x] Users can create, edit, and delete agents through Studio (name, description, LLM provider/model, system prompt)
- [x] Built-in tools selectively enabled/disabled per agent through Studio
- [x] MCP sources registered and attached to agents through Studio (data model only — connection stubbed)
- [x] Knowledge bases attached to/detached from agents through Studio (association persisted)

This flight addresses 4 of 10 mission success criteria.

## What Went Well

1. **All 7 design decisions held.** D1-D7 were implemented as specified with zero revisions. The single-scrollable-form (D1), inline delete (D6), and smart tool state mapping (D7) all proved sound in practice. Only D5 (dirty tracking) had a minor gap — missing save success feedback — caught and fixed during UAT.

2. **App shell architecture validated.** Studio was added as a second area using the same `App.registerArea()` pattern from Flight 02 with zero changes to `app.js`. CSS scoping via `.area-studio` prevented collisions. The framework delivered on its promise of extensibility.

3. **REST API from Flight 01 worked without modification.** All agent, MCP, and KB endpoints worked exactly as needed. The only backend addition was `GET /api/tools` (7 lines).

4. **UAT caught a real UX gap.** The flash toast for save/create feedback was a legitimate missing feature discovered through interactive testing. The fix-deploy-verify cycle via Concourse worked cleanly (3 deploys during UAT, all passing selftest).

5. **Concourse deploy pipeline is reliable.** Test, build, deploy, selftest — the full pipeline ran 3 times during UAT without issues. Deploys take ~60 seconds including health checks.

## What Could Be Improved

### Process

- **Legs 1-3 had no spec files.** Implementation was done before flight artifacts were created. The flight plan existed in conversation context, which was sufficient for the outcome, but bypassed the methodology's spec-before-implementation discipline. This likely reduced architectural rigor — design decisions were documented after the fact rather than guiding implementation. **Future flights should always use `/agentic-workflow` which enforces leg spec creation.**

- **Leg 2 and 3 were inseparable.** The sidebar and editor share state (selection drives rendering, dirty guard spans both). They were implemented as a single unit. Future master-detail patterns should be planned as a single leg.

### Technical

- **Hardcoded `TOOL_CATEGORIES` in studio.js.** This static JS map must stay in sync with `BuiltinToolProvider.get_tools()` in Python. If a tool is added to the backend, it silently disappears from the UI. The API should return categories, or the UI needs a catch-all "Other" group.

- **No error handling on `loadAll()`.** Four parallel fetches with no `.catch()`. A network failure silently leaves the UI broken with no user-visible error. Contrast with `save()` which handles errors properly.

- **Duplicate delete logic.** Sidebar inline delete and editor header delete are two independent implementations of the same API call with slightly different post-delete behavior. Should be consolidated.

- **No test coverage for `GET /api/tools`.** All other endpoints have tests in `test_db_api.py`. The tools endpoint was missed.

- **`activate()` is a no-op.** Studio loads data on init but doesn't refresh on re-activation. Data goes stale when switching back from other areas. Will matter more as cross-area interactions increase (Flight 04 agent picker, Flight 05 admin settings).

### Documentation

- **Tool category coupling** should be tracked as known debt.
- **Studio patterns** (form sections, toggle switches, chip widgets, dirty tracking, flash toast) are reusable but undocumented.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Legs 2+3 merged into single implementation | Sidebar and editor share state; separation was impractical | Yes — plan master-detail as single leg |
| Retroactive flight artifacts | Implementation preceded artifact creation | No — always create specs first via agentic workflow |
| Flash toast added during UAT | Save success had no visible feedback | Yes — all state-changing actions should specify UX feedback in design decisions |

## Key Learnings

1. **Design decisions that specify state changes should also specify feedback.** D5 defined dirty tracking but not success feedback. The gap was caught in UAT, but could have been caught in design review.

2. **The app shell pattern works.** Two areas now coexist without framework changes. The closure-based, CSS-scoped, REST-backed pattern is validated for vanilla JS.

3. **Hardcoded mappings between frontend and backend are fragile.** The tool categories will drift. Any frontend constant that mirrors backend data should be served from an API endpoint.

4. **Concourse deploy-during-UAT is viable.** The build/deploy/selftest cycle is fast enough (~60s) for interactive testing. No need for a separate local dev workflow — though persistent data storage for dev environments is a future need.

5. **Methodology discipline matters even when outcomes are good.** The flight landed successfully without formal leg specs, but the architectural review process was weakened. The methodology exists to maintain rigor at scale, not just for this one flight.

## Recommendations

1. **Extend `GET /api/tools` to return categories** — Eliminate the hardcoded `TOOL_CATEGORIES` map. Add a `category` field to each tool in the API response. Highest-value debt reduction from this flight.

2. **Add error handling to `loadAll()`** — A `.catch()` that shows a visible error prevents silent UI breakage on network failures.

3. **Add test for `/api/tools` endpoint** — Single test confirming 14 tools with name/description fields. Cheap to add, closes a coverage gap.

4. **Refresh data on `activate()`** — When Studio becomes active, re-fetch agents/tools/MCP/KB to prevent stale data. Will be important for Flight 04+ cross-area interactions.

5. **Always use `/agentic-workflow` for implementation flights** — Even when the scope seems small. Leg specs before implementation maintain architectural rigor and enable meaningful debrief analysis.

## Action Items

- [ ] Extend `/api/tools` to include `category` field (Flight 04 or maintenance)
- [ ] Add `.catch()` to `loadAll()` (next Studio touch)
- [ ] Add test for `GET /api/tools` (next test pass)
- [ ] Add data refresh in Studio `activate()` (Flight 04 or 05)
- [ ] Consolidate duplicate delete logic (next Studio touch)
