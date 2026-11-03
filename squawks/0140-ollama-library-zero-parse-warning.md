# Squawk 0140: Warn when the ollama.com library page parses to zero models

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-11-03

## Report

The library-page parser depends on ollama.com's Tailwind class names (`items-baseline`, `text-blue-600`, `text-cyan-500`). If ollama.com restyles its library page, the fetch succeeds but `parse_library_page` returns `[]`.

The fill then quietly falls back to the last persisted listing plus the `/api/tags` names, and logs nothing about it. The "page fetch failed" warning fires only on an HTTP error. The panel slowly goes stale, and nothing tells the operator why.

Log a distinct warning when a successful page fetch parses to zero entries, naming the likely cause (page markup changed), so the scraping break is visible in the log. No behaviour change: keep the fallback, and keep not pruning on an empty parse.

Found in the sortie 01 debrief (Architect).

## Evidence

- `the_one/llm/ollama_library.py:141` `parse_library_page`. The fetch at `:407-412` warns only in `except (httpx.HTTPError, OSError)`.
- `:422` `base = page or (_library["entries"] …)`, a silent fallback. `:427` prunes only `if page:`, which is correct to keep.

## Corrective Action
`_fetch_listing` in `the_one/llm/ollama_library.py` now logs one WARNING ("Ollama library page fetched but parsed to zero models; the ollama.com page markup has probably changed. Serving the last known listing.") when a successful fetch parses to `[]`. Fallback and no-prune behaviour unchanged. Added `tests/test_ollama_library.py::TestSearch::test_zero_parse_warns_once_serves_fallback_and_does_not_prune` (200 response, no entries: one warning, no "page fetch failed", fallback listing served, an extra size key not pruned). Falsified: with the warning disabled the test fails; restored.

## Verification (results)
`pytest tests/test_ollama_library.py` green; ruff check and format --check clean; unit tier result in the batch report.

## Verification (spec)
- A unit test feeds a 200 response whose HTML has no matching entries, and asserts one warning naming the empty parse. It also asserts the fallback listing is served and nothing is pruned.
- `make test-unit` is green, and `ruff check` and `ruff format --check` are clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
