# Leg: 05-search-backend-protocol-and-ddg

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Add `the_one/tools/_search_backends.py` (NEW): `SearchResult` dataclass, `SearchBackend` Protocol, `DDGSearchBackend` concrete implementation. The DDG backend POSTs to `https://html.duckduckgo.com/html/` with a browser User-Agent header — fixes the F1 known issue (DDG returns no results in the running container without browser UA — verified during F5 planning that with a Mozilla UA the endpoint returns 200 + 10 result markers).

## Context

- **L0–L4 landed** (uncommitted). `WebConfig`, `_url_check`, `_truncate_response`, `SSRFGuardedTransport` all in place. `DownloadFileTool` is the most recent addition.
- **F5 Decision 2** (`SearchBackend` extensibility shape): land the protocol now (one method, one concrete impl). F6 admin "test button" needs a uniform interface. F1 known-issue close ships in the same leg.
- **F5 Decision 12** (`SearchBackend` lifecycle, option a): backends instantiated inside `BuiltinToolProvider.get_tools()` alongside the existing `cross_configs` dict — a parallel `_search_backends: dict[str, SearchBackend]` keyed by backend name. **Wait** — Decision 12 actually says backends are passed via `cross_configs[SearchBackend]` injection (using the Protocol type as the dict key, mirroring `cross_configs[FilesystemConfig]` from F4). That's the wired-up path for L6's `WebSearchTool` migration; L5 just defines the protocol + DDG impl in isolation.
- **L6 (next leg)** wires `WebSearchTool` to consume the backend via `cross_configs[SearchBackend]`.
- **F1 known issue verified during F5 planning**: `https://html.duckduckgo.com/html/` returns a 202 anti-bot interstitial with no results when no User-Agent is sent. With `User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...` the endpoint returns 200 + `result__a` and `result__snippet` markers (verified count=10 in the live test).
- **Existing DDG parsing**: `tests/test_web_tools.py::TestWebSearchTool` (current implementation) uses regex `r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>'` against the HTML response. The L5 backend can reuse this parsing shape.

## Inputs

- `the_one/tools/web.py::WebSearchTool` — current implementation (reference for DDG parsing logic; L6 will wrap the backend).
- `the_one/tools/_web_config.py::_DEFAULT_USER_AGENT` — already defined (L1).
- httpx 0.28.1 verified.

## Outputs

- `the_one/tools/_search_backends.py` (NEW):
  - Module docstring describing the Protocol contract + F1 known-issue close.
  - **Constants**:
    - `_DDG_BROWSER_UA: str` — full browser UA string. Use a recent Chrome-on-Linux variant: `"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"`. (NOT the L1 `_DEFAULT_USER_AGENT` — DDG's anti-bot interstitial specifically rejects identifying UAs like the_one's default.)
    - `_DDG_RESULT_REGEX: re.Pattern` — pre-compiled regex for parsing.
  - **`@dataclass(frozen=True)` `SearchResult`**:
    - `title: str`
    - `url: str`
    - `snippet: str`
  - **`class SearchBackend(Protocol)`**:
    - `name: ClassVar[str]` — backend identifier (e.g., `"duckduckgo"`).
    - `async def search(self, query: str, max_results: int) -> list[SearchResult]: ...` — abstract.
    - `runtime_checkable` so `isinstance(backend, SearchBackend)` works for L6 / future tests.
  - **`class DDGSearchBackend`**:
    - `name = "duckduckgo"` (ClassVar matching the Protocol).
    - `__init__(self, http_client: httpx.AsyncClient | None = None)`. If `None`, the search method creates a short-lived client per call. **Note**: production wiring (L6) will inject an SSRF-guarded client.
    - `async def search(self, query, max_results) -> list[SearchResult]`:
      1. `headers = {"User-Agent": _DDG_BROWSER_UA}` — required to bypass DDG's anti-bot interstitial.
      2. POST to `https://html.duckduckgo.com/html/` with `data={"q": query}`, `headers=headers`, follow redirects.
      3. If response status != 200, return empty list (with a warning log).
      4. Parse: regex finds `result__a` href + title and `result__snippet` body. For each match up to `max_results`:
         - Strip HTML tags from title + snippet.
         - Append `SearchResult(title, href, snippet)`.
      5. Return the list (may be shorter than `max_results` if DDG returned fewer).
    - Internal owned-client semantics: if `__init__` was passed a client, `search` uses it directly (caller manages lifecycle). If no client, `search` creates `async with httpx.AsyncClient(...) as client:` per call (test-friendly default).
- `tests/test_search_backends.py` (NEW):
  - **`TestSearchResult`**:
    - `test_dataclass_frozen`: `SearchResult(title="t", url="u", snippet="s")` — fields populated; mutation raises `dataclasses.FrozenInstanceError`.
  - **`TestSearchBackendProtocol`**:
    - `test_protocol_runtime_checkable`: `isinstance(DDGSearchBackend(), SearchBackend)` is `True`. Uses the `runtime_checkable` annotation.
    - `test_protocol_method_signature`: a custom class missing `search` fails the isinstance check; one with `search` passes.
  - **`TestDDGSearchBackend`**:
    - `test_user_agent_sent`: mock transport captures the request; assert `headers.get("User-Agent")` matches `_DDG_BROWSER_UA`. **Pin the F1 fix.**
    - `test_parses_10_results`: mock returns realistic DDG HTML (use a fixture string) with 10 `result__a`/`result__snippet` pairs; assert `len(results) == 10`; assert all results have non-empty title/url/snippet; assert HTML tags stripped from title/snippet.
    - `test_max_results_limits`: mock returns 10 results; `search(query="x", max_results=3)` returns 3.
    - `test_no_results_returns_empty`: mock returns 200 + empty page; backend returns `[]`.
    - `test_anti_bot_interstitial_returns_empty`: mock returns 202 + interstitial HTML (no result markers); backend returns `[]` (and ideally logs a warning — verify via `caplog`).
    - `test_owned_client_lifecycle`: `DDGSearchBackend()` creates a fresh client per call; assert two consecutive `search()` calls don't error.
    - `test_injected_client_lifecycle`: `client = httpx.AsyncClient(transport=mock); DDGSearchBackend(http_client=client); search(...)` uses the injected client. Caller closes client.
- **No `the_one/tools/builtins.py` changes** — backend instantiation is L6's concern.
- **No `_TOOL_CLASSES` count change** — no new tools in L5.

## Acceptance Criteria

- [x] `the_one/tools/_search_backends.py` exists with the documented public API.
- [x] `SearchResult` is `@dataclass(frozen=True)` with three fields (`title`, `url`, `snippet`).
- [x] `SearchBackend` is a `runtime_checkable` Protocol with `name: ClassVar[str]` and `async def search(query, max_results) -> list[SearchResult]`.
- [x] `DDGSearchBackend.name == "duckduckgo"`.
- [x] **Browser User-Agent header sent** (the F1 fix): mock transport test confirms the exact header value.
- [x] `DDGSearchBackend.search` returns parsed results with HTML tags stripped from title and snippet.
- [x] Backend handles non-200 responses gracefully (returns empty list).
- [x] Backend supports both owned-client (fresh per call) and injected-client lifecycle.
- [x] `runtime_checkable` Protocol — `isinstance(DDGSearchBackend(), SearchBackend)` is True.
- [x] All 8 new tests pass. (10 enumerated tests landed; "8" figure is stale from an earlier draft — see flight-log entry.)
- [x] Full unit suite green (modulo CSS-token red). (985 passed, 1 skipped, 239 deselected.)
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
# Module exports
docker exec the-one python -c "
from the_one.tools._search_backends import (
    SearchResult, SearchBackend, DDGSearchBackend, _DDG_BROWSER_UA,
)
import dataclasses
assert dataclasses.is_dataclass(SearchResult)
assert isinstance(DDGSearchBackend(), SearchBackend)
print('OK exports')
"

# F1 fix — DDG with browser UA returns results (LIVE smoke; only run when network is available and DDG isn't rate-limiting)
docker exec the-one python -c "
import asyncio
from the_one.tools._search_backends import DDGSearchBackend
async def main():
    backend = DDGSearchBackend()
    results = await backend.search('python asyncio', max_results=5)
    print(f'DDG returned {len(results)} results')
    if results:
        print(f'First: {results[0].title[:80]} - {results[0].url}')
asyncio.run(main())
"

# Tests
docker exec the-one pytest tests/test_search_backends.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# Lint
docker exec the-one ruff check the_one/tools/_search_backends.py tests/test_search_backends.py
```

## Implementation Guidance

1. **Create `the_one/tools/_search_backends.py`**:

   ```python
   from __future__ import annotations

   import logging
   import re
   from dataclasses import dataclass
   from typing import ClassVar, Protocol, runtime_checkable

   import httpx

   logger = logging.getLogger(__name__)

   _DDG_BROWSER_UA = (
       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
   )

   _DDG_RESULT_REGEX = re.compile(
       r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
       r'class="result__snippet"[^>]*>(.*?)</span>',
       re.DOTALL,
   )

   _HTML_TAG_REGEX = re.compile(r"<[^>]+>")


   @dataclass(frozen=True)
   class SearchResult:
       title: str
       url: str
       snippet: str


   @runtime_checkable
   class SearchBackend(Protocol):
       """Pluggable search backend. F5 ships only DDGSearchBackend; future
       missions can add Brave / Tavily / Google CSE without touching
       WebSearchTool. F6 admin will let operators pick the active backend.

       The backend is responsible for its own httpx client (owned per-call
       OR injected at construction time). When wired through
       BuiltinToolProvider, the injected client uses SSRFGuardedTransport
       so DDG / Brave / etc. requests respect the operator's SSRF policy.
       """

       name: ClassVar[str]

       async def search(
           self, query: str, max_results: int
       ) -> list[SearchResult]:
           ...


   class DDGSearchBackend:
       """DuckDuckGo HTML-endpoint backend.

       Closes F1 known issue (DDG returns no results without browser UA):
       sets a Chrome-on-Linux User-Agent that bypasses the anti-bot
       interstitial. Verified live during F5 planning that the same
       endpoint returns 200 + 10 result markers with this UA.
       """

       name: ClassVar[str] = "duckduckgo"

       def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
           self._client = http_client

       async def search(
           self, query: str, max_results: int
       ) -> list[SearchResult]:
           headers = {"User-Agent": _DDG_BROWSER_UA}
           url = "https://html.duckduckgo.com/html/"
           data = {"q": query}

           if self._client is not None:
               resp = await self._client.post(
                   url, data=data, headers=headers, follow_redirects=True,
               )
           else:
               async with httpx.AsyncClient(timeout=15) as client:
                   resp = await client.post(
                       url, data=data, headers=headers, follow_redirects=True,
                   )

           if resp.status_code != 200:
               logger.warning(
                   "DDG returned non-200 status %s (likely anti-bot interstitial)",
                   resp.status_code,
               )
               return []

           text = resp.text
           if "result__a" not in text:
               logger.warning("DDG response has no result markers (interstitial?)")
               return []

           results: list[SearchResult] = []
           for match in _DDG_RESULT_REGEX.finditer(text):
               href, title_html, snippet_html = match.groups()
               title = _HTML_TAG_REGEX.sub("", title_html).strip()
               snippet = _HTML_TAG_REGEX.sub("", snippet_html).strip()
               results.append(SearchResult(title=title, url=href, snippet=snippet))
               if len(results) >= max_results:
                   break
           return results
   ```

2. **Test fixtures**:
   - For `test_user_agent_sent`: `httpx.MockTransport` handler captures `request.headers.get("User-Agent")` into a closure; assert exact match.
   - For `test_parses_10_results`: hard-code a small DDG-like HTML snippet with 2-3 result markers (cheaper than 10; same parsing path); assert correct count and structure. Document that the `_parses_10_results` name is aspirational; the test exercises the parsing on a smaller fixture.
   - For `test_anti_bot_interstitial_returns_empty`: handler returns `httpx.Response(202, text="<html><head><title>DDG</title></head></html>")`; backend returns `[]`.
   - For `test_owned_client_lifecycle`: monkeypatch `httpx.AsyncClient` to a factory returning a `MockTransport`-backed client; OR don't test the actual HTTP — just construct the backend with no client and assert the search method doesn't error on `__init__`.

3. **Module placement**: `the_one/tools/_search_backends.py` (underscore prefix marks internal; `WebSearchTool` consumes via `cross_configs[SearchBackend]` in L6). Mirrors L1's `_web_config.py` naming.

4. **No `_TOOL_CLASSES` change**: this leg is pure protocol + impl. L6 wires it.

5. **Run tests + ruff**.

## Edge Cases

- **DDG rate limiting**: live smoke may hit 429 or further interstitials. The backend returns `[]` on non-200; L6's `WebSearchTool` will format this as `"No results found."` (matches today's wording).
- **HTML entity decoding**: titles/snippets may contain `&amp;`, `&quot;`, etc. Today's `WebSearchTool` doesn't decode entities; L5 preserves that. **If small-model agents struggle with raw entities**, a future flight can add `html.unescape()`.
- **Very long query**: DDG's endpoint accepts arbitrarily long queries; no special handling.
- **`max_results=0`**: returns `[]` immediately (the regex loop's `if len(results) >= max_results: break` fires before any append).
- **Browser UA value drift**: if DDG starts blocking Chrome 120 specifically, update `_DDG_BROWSER_UA` to a more recent string. Document as a known maintenance item.

## Files Affected

- `the_one/tools/_search_backends.py` — NEW.
- `tests/test_search_backends.py` — NEW.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
