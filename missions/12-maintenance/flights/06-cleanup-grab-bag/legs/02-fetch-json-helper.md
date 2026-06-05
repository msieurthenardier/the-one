# Leg: fetch-json-helper

**Status**: completed
**Flight**: [Cleanup Grab-Bag](../flight.md)

## Objective
Extract a shared `App.api.fetchJson(url, opts)` helper that centralizes the ok-check + 422-`detail` flattening + snippet-fallback logic, and replace the duplicated fetch-error-parsing blocks in the studio JS (resolves finding Q4).

## Context
- Maintenance report 2026-06-04, finding **Q4** (Advisory): `connector-editor.js:1522-1546` (`handleSave`) and `:1569-1593` (`handleCreateAndTest`) contain a byte-for-byte ~25-line `if (!r.ok) { return r.text().then(...) }` block (JSON-parse detail → flatten 422 `loc/msg` array → fallback snippet → throw). There is no shared fetch/JSON helper anywhere in the web JS; 13 raw `resp.ok` checks in `connector-editor.js` alone. Each new endpoint re-implements ok/parse/throw by hand, so error-rendering drifts per call site.

## Inputs
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (the two duplicated blocks + the 13 raw `resp.ok` checks).
- The web JS `App` namespace structure (where shared helpers live).

## Outputs
- An `App.api.fetchJson` (or similarly-namespaced) helper.
- Call sites in the studio JS switched to it.

## Acceptance Criteria
- [x] A single shared helper performs: fetch → ok-check → on-error parse JSON `detail` → flatten 422 `loc/msg` arrays → snippet fallback → throw a consistent error; on success returns parsed JSON
- [x] The two duplicated ~25-line blocks in `connector-editor.js` are replaced by calls to the helper
- [x] Other raw `resp.ok` sites in the studio JS are migrated where the pattern fits (at minimum the connector-editor ones)
- [x] **Error rendering is unchanged** from the user's perspective (same messages for 422, same snippet fallback)
- [x] Existing browser tests covering connector save/create error paths stay green

## Verification Steps
- `grep -c "\.ok" the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — materially fewer hand-rolled checks
- Manual / browser test: trigger a 422 (e.g. invalid connector config) and a 500, confirm the same error text renders as before
- `pytest -m browser tests/browser/test_flow_studio_connector_account_editor.py -q` green

## Implementation Guidance

1. **Locate or create the `App.api` namespace** — follow the existing `App.*` module convention (e.g. how `App.markdown`/`App.icon` are exposed).
2. **Port the existing logic verbatim** — the helper must reproduce the current ok-check + 422-flatten + snippet-fallback exactly; this is a dedupe, not a redesign of error handling.
3. **Switch the two duplicated blocks first** (`handleSave`, `handleCreateAndTest`), then migrate other `resp.ok` sites in the same file opportunistically.
4. **Confirm no error-message drift** — compare rendered errors before/after for 422 and non-422 cases.

## Edge Cases
- **Non-JSON error bodies** — the snippet fallback must still handle a plain-text or HTML error body (the current code does).
- **Network failure (fetch rejects)** vs **HTTP error (ok=false)** — preserve whatever the current code does for each.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - use the helper (remove dup)
- A shared JS module (e.g. `static/js/api.js` or the existing `App` bootstrap) - new `App.api.fetchJson`
- `the_one/interfaces/web/static/index.html` - script include if a new file is added

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (not final)
- [x] Commit all changes together (code + artifacts)
