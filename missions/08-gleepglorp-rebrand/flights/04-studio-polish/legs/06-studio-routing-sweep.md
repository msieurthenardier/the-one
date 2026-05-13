# Leg: 06-studio-routing-sweep

**Status**: landed
**Flight**: [Studio Polish](../flight.md)
**Mode**: HAT (operator-driven walkthrough; Flight Director applies inline scope-light fixes)

## Objective

Manually walk every Studio sub-route × 3 transitions (deep-link / refresh / back-button) to verify hash routing is correct end-to-end. Smoke-check the cross-area dirty-gate paths from Studio editors. Apply scope-light fixes inline as the operator surfaces them. Log non-trivial gaps as Known Issues for Leg 07 cleanup or a future flight.

## Context

**Background**: Flight 3 Leg 06 established the routing-sweep pattern for the Admin area (catalog-first, fix-second cadence). Flight 4 carries that template into Studio. Studio's routing is more complex than Admin's — agent-editor has 4 tabs (general / knowledge / tools / mcps), the mcps tab itself has a per-attachment sub-route, MCP sources have create + edit forms, and the F3 router performs serialize-after-hydrate URL normalization that can surprise unprepared deep-links.

**Relevant prior-leg outcomes**:
- Leg 05 added the `confirmLeave` hook + `tryConsumePendingMcpSource` stale-then guard + Playwright B2 cross-area dirty-gate regression test (`tests/browser/test_flow_cross_area_dirty_gate.py` — 4 parametrized invocations passing). Leg 06's beforeunload/dirty-gate smoke is a quick visual confirmation, NOT a re-derivation of that coverage.
- Leg 02 introduced agent rename, MCP `serverInfo` capture, Tools/MCPs-tab restructure (uncommitted; expected to influence routing if tab-state machinery shifted).
- Leg 03 added the Server-info section + OAuth popup-loop fix (uncommitted; touches `mcp-server-editor.js` heavily — routing-relevant only at the MCP source-editor mount path).
- Leg 04 was SKIPPED.
- The pre-existing `test_flow_dirty_confirm.py` (19 failures) and `--toggle-width` regressions are EXPLICITLY out of scope here — operator-deferred to Leg 07.

**Working-tree state at kickoff**: Legs 02 + 03 + 05 uncommitted edits accumulated. Leg 06 inline fixes MAY touch any Studio-surface file (studio.js, studio sub-modules, studio.css) — those files are already in the uncommitted set, so fix-additions land alongside without separate commits.

## Routes Catalog

Pre-filled from `studio.js:serializeState` + `studio.js:hydrateState` (verified at design time). Operator fills each cell during the walkthrough: ✓ (works as expected) / ✗ (broken — fixed inline OR logged) / KI (known issue — non-trivial, logged for Leg 07 or future flight). Add notes in the Notes column.

| # | Route | Deep-link | Refresh | Back-button | Notes |
|---|---|---|---|---|---|
| 1 | `#studio` (bare) | ✓ | ✓ | ✓ | URL upgrade to `#studio/agents` confirmed |
| 2 | `#studio/agents` | ✓ | ✓ | ✓ | Tile grid renders, no auto-selection |
| 3 | `#studio/agents/{name}` | ✓ | ✓ | ✓ | Auto-upgrade to `/general` fired correctly |
| 4 | `#studio/agents/{name}/general` | ✓ | ✓ | ✓ | |
| 5 | `#studio/agents/{name}/knowledge` | ✓ | ✓ | ✓ | Knowledge stub-deferred content visible |
| 6 | `#studio/agents/{name}/tools` | ✓ | ✓ | ✓ | |
| 7 | `#studio/agents/{name}/mcps` | ✓ | ✓ | ✓ | |
| 8 | `#studio/agents/{name}/mcps/{source-id}` | ✓ | ✓ | ✓ | **Bridge held under refresh** — design-review concern about the `_pendingMcpAgentSourceId` → `_selectedMcpAgentSourceId` window was speculative; in practice the render-after-hydrate ordering serializes correctly. |
| 9 | `#studio/knowledge` | ✓ | ✓ | ✓ | |
| 10 | `#studio/mcp-sources` | ✓ | ✓ | ✓ | Grid renders with LED slots from Leg 03's Server-info work |
| 11 | `#studio/mcp-sources/new` | ✓ | ✓ | ✓ | |
| 12 | `#studio/mcp-sources/{id}` | ✓ | ✓ | ✓ | Edit form pre-populated incl. Server-info section |

**Defensive routes** (from `hydrateState`'s fallback branches — should NOT crash):
- `#studio/agents/{name}/<unknown-tab>` → defaults to `general` (tab whitelist fallback)
- `#studio/<unknown-section>` → defaults to `agents` (section fallback)
- `#studio/agents/{name}/` (trailing slash) → defensive, defaults to general
- `#studio/agents/new` — NOT a real route. `serializeState`'s branch 4 falls back to `agents` when createMode is active (so this URL is never emitted by the app). If an operator navigates here manually, `hydrateState` parses it as an agent named `new` (which will then 404 at `tryConsumePendingSelect` since no such agent exists). The behavior is benign but worth confirming on the walkthrough.

Operator can spot-check these if time allows; not in the core 12.

## Beforeunload + Cross-Area Dirty-Gate Smoke

Leg 05's Playwright test already covers these mechanically; Leg 06 confirms the dialog visually fires in real browser usage:

| # | Scenario | Result |
|---|---|---|
| B1 | Agent editor dirty → topbar Chat → confirm dialog appears | ✓ |
| B2 | Agent editor dirty → topbar System → confirm dialog appears | ✓ |
| B3 | MCP editor dirty → topbar Chat → confirm dialog appears | ✓ |
| B4 | MCP editor dirty → topbar System → confirm dialog appears | ✓ |

Plus the browser-level beforeunload (covered by existing tests; smoke only):

| # | Scenario | Result |
|---|---|---|
| U1 | Agent editor dirty → Cmd-W / browser close-tab → native "Leave site?" prompt appears | ✓ |

## Acceptance Criteria

- [ ] All 36 routing check cells (12 routes × 3 transitions) marked ✓ / ✗ / KI in the flight log.
- [ ] All 4 cross-area dirty-gate combos (B1–B4) confirmed ✓.
- [ ] U1 beforeunload smoke confirmed ✓.
- [ ] All scope-light fixes applied during the walkthrough recorded in the flight log under "Inline Fixes" — one entry per fix: route number, what changed, why, file + symbol/snippet locator.
- [ ] All non-trivial gaps recorded as Known Issues — either in `mission.md` (if cross-flight scope) OR as Leg 07 carry-forward entries in the flight log (if scope-light enough to clean up in Leg 07's pre-close).
- [ ] No regression in the new Leg 05 Playwright test: `docker exec the-one pytest tests/browser/test_flow_cross_area_dirty_gate.py -x -q --timeout 30 -m browser` → 4 passed.
- [ ] No regression in the existing hash-routing browser test: `docker exec the-one pytest tests/browser/test_flow_hash_routing.py -x -q --timeout 30 -m browser` stays green (current baseline + any new failures must be either fixed inline or routed to Leg 07).
- [ ] Working-tree edits from Legs 02 + 03 + 05 preserved (Leg 06's inline fixes are net-additive, not reverting prior work).
- [ ] Flight log updated with the catalog table results, dirty-gate smoke results, inline fixes list, and Known Issues list.
- [ ] **No commit per agentic-workflow spec.** Leg 06 lands; Leg 07's 10-step close handles the commit.

## Verification Walkthrough

**Prerequisites**:

1. `make rebuild` to incorporate Legs 02 + 03 + 05 uncommitted edits + any Leg 06 inline fixes.
2. Seed at least one agent (any provider works — `make seed-agent` if such a target exists, otherwise the operator creates one via UI before starting).
3. Seed at least one MCP source (the operator's existing Cloudflare Docs source from the Leg 03 OAuth flow work qualifies).
4. Open the app in a browser; have DevTools Network + Console panes visible to catch errors.

**Walkthrough cadence** — per route, per transition. The operator reports each result; the Flight Director records in the catalog table + flight log; scope-light fixes apply inline.

For each route in the table:

1. **Deep-link**: paste the URL into the browser address bar (or use `location.hash = '...'` from the console). Hit enter. Does the right surface mount? Console clean? Mark `✓` or `✗`.
2. **Refresh**: with the URL still loaded, hit F5 / Cmd-R. Does the post-refresh state match pre-refresh? Mark `✓` or `✗`.
3. **Back-button**: navigate to `#chat` (a different area — cross-area back-button is the meaningful case; in-area back is identical to popstate and less informative), then click browser-back. Does it return to the prior Studio state correctly? Mark `✓` or `✗`.

For a **`✗` result**: the Flight Director investigates immediately. If the fix is scope-light (< 10 LOC, no new abstractions, no test changes), apply inline + re-verify the cell. If the fix is bigger, log as a Known Issue and mark the cell `KI`.

**Suggested operator order** (covers complexity progressively):

1. Start with the simplest routes (1, 2, 9, 10) to establish baseline. These should be the lowest-risk.
2. Then the agent-editor deep routes (3 → 4 → 5 → 6 → 7 → 8). The serialize-after-hydrate upgrade behavior is most likely to surface bugs at 3 (the upgrade-to-`/general` path).
3. Then MCP-source forms (11 → 12).
4. Then the beforeunload + dirty-gate smoke (B1–B4 + U1).

**Existing test coverage already validates** (operator can skip re-deriving):
- `#studio/agents/{name}` refresh persistence — `test_flow_hash_routing.py::test_hash_routing_studio_agent_persists_on_refresh`.
- `#studio` → `#studio/agents` redirect — same test file.
- `#studio/knowledge` refresh — same test file.
- Cross-area dirty-gate dialog mechanics (B1–B4 equivalents) — `tests/browser/test_flow_cross_area_dirty_gate.py`.

The HAT walkthrough is the in-browser visual confirmation that the tests don't directly exercise (e.g., the URL upgrade animation, console errors during transitions, content panel mount race conditions).

## Inline Fix Protocol

When the operator surfaces a `✗`:

1. **Reproduce** the failure (operator + Flight Director observe together).
2. **Diagnose** — Flight Director reads the relevant code (typically `studio.js:serializeState` / `studio.js:hydrateState` / the consume-pending paths).
3. **Scope-gate**:
   - **Scope-light** (≤ ~10 LOC, no new abstractions, no test changes needed): apply inline via `Edit` calls, re-verify, mark cell `✓`. Log the fix in the flight log's Inline Fixes section.
   - **Non-trivial** (architectural, multi-file, requires new tests): log as Known Issue + mark cell `KI`. Do NOT attempt a deeper fix during the walkthrough — momentum matters more than completeness.
4. **Re-verify** the cell after the fix; only mark `✓` if the fix actually resolves the symptom.

## Known-Issues Logging Protocol

Non-trivial routing gaps logged in one of two places:

- **Leg 07 carry-forward** (preferred for cleanup-scope items): append to a new "## Leg 07 carry-forward" section in the flight log, with: route number, symptom, suspected cause, suggested fix scope.
- **Mission.md Known Issues** (for cross-flight scope items): append to `missions/08-gleepglorp-rebrand/mission.md` under "## Known Issues" mirroring the existing entry format (route number, symptom, where surfaced, suggested follow-up).

Examples of items that go to mission.md instead of Leg 07:
- A routing bug whose fix requires touching the F3 router itself (not Studio-local).
- A behavior that's actually correct-as-designed but operator surfaces a UX preference (route to a future polish flight).
- Browser-specific behavior (e.g., Safari handling of hash refresh).

## Files Affected

**Likely touched during inline fixes** (depending on what the walkthrough surfaces):
- `the_one/interfaces/web/static/js/areas/studio.js` — most routing logic.
- `the_one/interfaces/web/static/js/areas/studio/*.js` — sub-module routing (e.g., tabs.js, mcp-server-editor.js).
- `the_one/interfaces/web/static/js/app.js` — only if a cross-cutting router bug surfaces (less likely; Admin already exercises the same router).

**Definitely touched**:
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-log.md` — catalog + dirty-gate + inline-fixes + known-issues entries.
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/legs/06-studio-routing-sweep.md` — this file, status update.
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight.md` — Leg 06 leg-list checkoff.

**Possibly touched** (only if cross-flight scope items surface):
- `missions/08-gleepglorp-rebrand/mission.md` — Known Issues additions.

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All 36 routing check cells populated (✓ / ✗ / KI)
- [ ] All 4 dirty-gate combos (B1–B4) + U1 beforeunload smoke confirmed
- [ ] All inline fixes applied + recorded in the flight log
- [ ] All non-trivial gaps logged as Known Issues (mission.md or Leg 07 carry-forward)
- [ ] No regression in Leg 05 Playwright test (4 passed)
- [ ] No regression in existing hash-routing browser test
- [ ] Flight log updated with full Leg 06 progress entry
- [ ] Leg status set to `landed` in this file's header
- [ ] Leg 06 checked off in `flight.md`
- [ ] **Do NOT commit per agentic-workflow spec** — Leg 07's close handles the commit. Signal `[COMPLETE:leg]` when done.

## Citation Audit

Citations in this artifact verified against current HEAD code at design time (2026-05-13):

| Citation | Form | Resolution |
|---|---|---|
| `studio.js:serializeState` (lines ~23-58) | symbol + line range | OK at HEAD. Branch order: knowledge / mcp-sources / agents-with-selection / hydrate-before-loadAll fallback / agents bare. |
| `studio.js:hydrateState` (lines ~74-157) | symbol + line range | OK at HEAD. Parses bare / knowledge / mcp-sources[/new\|/id] / agents/[name][/tab][/mcps/source-id] / unrecognized→agents. |
| `studio.js:tryConsumePendingSelect` | symbol | OK at HEAD (deep-link resolution path for agent selection). |
| `studio.js:tryConsumePendingMcpSource` | symbol | OK at HEAD (post-Leg-05 guard added; deep-link resolution path for MCP source selection). |
| `tests/browser/test_flow_hash_routing.py` | file reference | OK at HEAD. Existing test coverage for `#studio` → `#studio/agents` redirect, agent-name persist, knowledge persist. |
| `tests/browser/test_flow_cross_area_dirty_gate.py` (Leg 05 new) | file reference | OK at HEAD (uncommitted). 4 parametrized invocations cover B1-B4 mechanically. |
| `app.js:syncUrlFromState` (lines 57-61) + call sites at 73-77 + 137-143 | symbol + line range | **Corrected during design review.** Initial draft cited `app.js:179-185` (inherited from a stale studio.js prose comment) — actual implementation lives in the `syncUrlFromState` helper at lines 57-61 and its two call sites in the boot/cross-area-switch paths. |
| `mission.md` Known Issues format | non-source reference | OK at HEAD. Existing entries provide the format. |
| `flight.md` Routing sweep (Leg 06) block | non-source reference | OK at HEAD. Source of the 24-checks framing. |

9 citations verified clean. No drift corrected at design time (no `file:line` brittle references introduced; symbol + line-range citations are durable against the routing code's relative stability between legs).

**Note on routes-catalog grounding**: the 12 routes + defensive-route branches enumerated above were derived directly from `serializeState` (5 emission cases) + `hydrateState` (6 parse branches + 3 defensive fallbacks). The pre-Leg 06 flight-spec catalog mentioned `#studio/agents/new` — this is NOT a route Studio actually serves (createMode falls back to `agents` in `serializeState` branch 4). Also: `#studio/agents/{name}/mcps/{source-id}` (route #8) was missing from the flight-spec's 8-route enumeration; it's a real F8 L3 Patch B route surfaced from the code reading. The catalog above is grounded in code, not spec.
