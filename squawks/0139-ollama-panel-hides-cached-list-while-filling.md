# Squawk 0139: The Ollama Pull list hides a cached list while a fill runs

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-15

## Report

With a full disk cache, opening an Ollama provider's Models panel can show the disabled "Loading models and sizes. The first load takes a little while…" for up to about 20 s when ollama.com is slow or unreachable. A refresh of the model list is in progress, and the panel ignores the list it already has.

The server starts a fill whenever the library *listing* is older than 300 s, even when every size is fresh (7 days). The route waits up to 8 s and then answers `loading: true` together with the full `models` snapshot. The panel throws the snapshot away and shows the first-load copy. Two 10 s timeouts on a blackholed host keep that going for about 20 s.

This contradicts sortie 01's DD4: "an ollama.com outage after a restart still shows the full list". Fix it on the panel side: render `models` whenever the response carries any, and keep the loading copy for a genuinely empty first load. Optionally, refresh the listing in the background with a longer listing TTL (hours), stale-while-revalidate.

Found in the sortie 01 debrief (Developer and Architect).

## Evidence

- `the_one/llm/ollama_library.py:55` `_LISTING_TTL = 300.0`; `:388` `_needs_fill` returns true when `now - max(fetched, _last_attempt) > _LISTING_TTL`.
- `the_one/interfaces/web/static/js/areas/admin/provider-models.js:255-256`: `if (data.loading) { setSelectMessage(LOADING_COPY); …`, which ignores `data.models`.
- No test pairs `loading: true` with a non-empty `models`. `tests/browser/test_flow_provider_ollama_pull.py`'s loading test stubs `{"loading": true, "models": []}`.

## Corrective Action
Fixed on the panel side in the M31 F1 L6 rebuild of `provider-models.js` (the file moved from `areas/admin/` to `areas/studio/` earlier). `loadLibrary` now calls `showLibrary(models)` whenever the response carries any `models`, even with `loading: true`, so the cached list is offered (select enabled) while the 2 s poll continues through the one library timer. The loading copy (`LOADING_COPY`) is shown only when `models` is empty. The chosen model also survives each poll while it is still offered. The optional listing-TTL change was not made.

## Verification
- A browser test stubs `/api/ollama-library/search` with `loading: true` and a non-empty `models`, and asserts the list renders and is selectable at once.
- The existing empty-list loading test still shows the loading copy and re-requests.
- `make test-unit` and the settings lane are green, and the static guards pass.

Run 2026-10-15: `tests/browser/test_flow_provider_models_patch.py::test_loading_response_with_models_shows_them_while_polling` (stubbed `loading: true` with one cached model: the select is enabled with "Select a model…" and "cached:1b (1.0 GB)" at once, the loading copy is absent, the second poll replaces it with the 7-option catalog) passes; `test_flow_provider_ollama_pull.py::test_loading_response_keeps_select_disabled_then_the_list_appears` (empty `models`) still passes. The `providers` lane and the static guards are recorded in the flight log's `provider-models-pilot` entry.

## Sign-Off
**Reviewer**: Mission 31 Flight 1 Reviewer (Sonnet)
**Verdict**: confirmed
**Commit**: Mission 31 Flight 1 commit (flight/01-library-completion-and-pilot)
