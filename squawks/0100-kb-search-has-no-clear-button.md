# Squawk 0100: Knowledge base search has no clear (×) button to dismiss its results

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —

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

*(written at completion)*

## Verification

## Sign-Off

*(written at completion)*
