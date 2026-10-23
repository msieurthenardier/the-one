# Squawk 0100: Knowledge base search has no clear (×) button to dismiss its results

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-10-23

## Report

On a knowledge base's detail page in Studio (Knowledge section), the Search
field has no × / clear control. Once a search has run, its hits stay on the page
with no direct way to dismiss them. The only way out today is the non-obvious one:
delete the query text by hand, then press Search (or Enter) on the empty field.

Repro: Studio → Knowledge → open a knowledge base → type a query → Search. Hits
render below; there is no control to clear the field and the results together.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js` — the Search
  section (`// ── Search (AC-6, DD-6)`) builds only `kb-search-input` and
  `kb-search-btn`; no clear control exists.
- Same file, `runSearch()` — `resultsEl.textContent = ''; degradedEl.hidden = true;
  if (!q.trim()) return;`: an empty-query search already clears the hits and the
  degraded line, so the reset logic a clear button needs is already there.

## Corrective Action

M31 Flight 3 Leg 05b rebuilt the Search section on the library (`knowledge-search.js`). The query is now `App.ui.clearableInput` (testids `kb-search-input`, `kb-search-clear-btn`): the x button, or Escape while the field has text, empties the query, and its `onClear` also empties the results, hides the degraded line and bumps the search generation so an in-flight response is dropped. Focus lands in the input. Enter still runs the search.

## Verification

- `tests/browser/test_flow_studio_knowledge_inventory.py::test_search_clear_empties_query_results_and_degraded_line[button|escape]` (query, results and degraded line cleared, focus in the input, x hidden) and `::test_clearing_during_an_in_flight_search_drops_the_late_response`.

## Sign-Off
**Reviewer**: Sonnet, the Mission 31 Flight 3 flight review (code and accessibility reviewers, then a scoped re-review of the fix pass)
**Verdict**: confirmed
**Commit**: `flight/3: Knowledge and connectors on the library (Mission 31)` on branch `flight/03-knowledge-and-connectors-on-the-library`
