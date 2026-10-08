# Squawk 0140: Warn when the ollama.com library page parses to zero models

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

The library-page parser depends on ollama.com's Tailwind class names (`items-baseline`, `text-blue-600`, `text-cyan-500`). If ollama.com restyles its library page, the fetch succeeds but `parse_library_page` returns `[]`.

The fill then quietly falls back to the last persisted listing plus the `/api/tags` names, and logs nothing about it. The "page fetch failed" warning fires only on an HTTP error. The panel slowly goes stale, and nothing tells the operator why.

Log a distinct warning when a successful page fetch parses to zero entries, naming the likely cause (page markup changed), so the scraping break is visible in the log. No behaviour change: keep the fallback, and keep not pruning on an empty parse.

Found in the sortie 01 debrief (Architect).

## Evidence

- `the_one/llm/ollama_library.py:141` `parse_library_page`. The fetch at `:407-412` warns only in `except (httpx.HTTPError, OSError)`.
- `:422` `base = page or (_library["entries"] …)`, a silent fallback. `:427` prunes only `if page:`, which is correct to keep.

## Corrective Action
*(written at completion)*

## Verification
- A unit test feeds a 200 response whose HTML has no matching entries, and asserts one warning naming the empty parse. It also asserts the fallback listing is served and nothing is pruned.
- `make test-unit` is green, and `ruff check` and `ruff format --check` are clean.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
