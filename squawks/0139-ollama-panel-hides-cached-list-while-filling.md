# Squawk 0139: The Ollama Pull list hides a cached list while a fill runs

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

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
*(written at completion)*

## Verification
- A browser test stubs `/api/ollama-library/search` with `loading: true` and a non-empty `models`, and asserts the list renders and is selectable at once.
- The existing empty-list loading test still shows the loading copy and re-requests.
- `make test-unit` and the settings lane are green, and the static guards pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
