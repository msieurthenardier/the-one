# Leg: 03-fetch-url-tool

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Add `FetchUrlTool` to `the_one/tools/web.py` — fetches a URL and returns the main content as markdown when the response is HTML, raw decoded body for text/JSON, refuse-with-guidance for binary. Routes through `WebConfig` + `SSRFGuardedTransport` + `_truncate_response` (L1 helpers). Mirrors L2's `_build_transport` test seam, four-clause envelope, and float-preserving timeout clip. Registers in `_TOOL_CLASSES` (post-L3 count: 18 tools).

## Context

- **L0 + L1 + L2 landed** (uncommitted). `WebConfig`, helpers, transport, and migrated `HttpRequestTool` all in place. `readability-lxml` + `markdownify` deps verified importable in the running container.
- **F5 Decision 8** (`fetch_url` parameter shape): single required `url`. Always runs readability+markdownify when `Content-Type: text/html`; raw decoded body for text/JSON; refuse-with-guidance for binary.
- **Resolves Open Question** (from F5 flight spec): "`fetch_url` content-type handling — readability only on `text/html`; raw decoded body for text/JSON; refuse-with-guidance for binary."
- **Tool description disambiguation**: agents choose between `fetch_url` (extract main content; ideal for articles/docs) and `http_request` (raw HTTP; ideal for APIs / arbitrary methods). Description must be small-model-friendly to steer the right pick.
- **`readability.Document(html).summary()`** returns a string of cleaned HTML. **`markdownify.markdownify(html)`** converts to markdown. Pipeline: `markdown = markdownify(Document(resp.text).summary())`.

## Inputs

- `the_one/tools/_web_config.py` — `WebConfig`, `_url_check`, `_truncate_response`, `_is_binary_content_type`, `SSRFGuardedTransport`.
- `the_one/tools/web.py` — `HttpRequestTool` (post-L2 reference for the envelope/transport-seam pattern).
- `readability.Document` and `markdownify.markdownify` (verified importable in container).
- `the_one/tools/builtins.py::_TOOL_CLASSES` — currently 17 entries; post-L3 = 18.

## Outputs

- `the_one/tools/web.py`:
  - **`FetchUrlTool(Tool)`** appended after `HttpRequestTool`.
  - `name = "fetch_url"`.
  - `description = "Fetch a URL and return its main content as markdown. For HTML pages, runs a readability extractor to strip navigation/ads/sidebars before converting to markdown — ideal for articles, blog posts, docs. For text/JSON responses, returns the raw decoded body. For binary content (PDF, images, archives), refuses with guidance to use download_file instead. Same SSRF + URL allowlist + size cap + timeout cap as http_request."`.
  - `parameters = {"type": "object", "properties": {"url": {"type": "string", "description": "URL to fetch."}}, "required": ["url"]}`.
  - `Config = WebConfig`.
  - `_build_transport(self, cfg) -> httpx.AsyncBaseTransport`: returns `SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)`. **Same shape as L2** for test-seam consistency.
  - `execute(self, url, **kwargs) -> str`:
    1. `cfg = self._config`.
    2. `clipped = cfg.timeout_seconds_default` (no agent-passed timeout — keep param surface tiny). If F6 admin needs an override, agents can use `http_request`.
    3. Four-clause envelope (mirrors L2):
       - `try`:
         - `_url_check(url, cfg)`.
         - Build SSRF-guarded client (same shape as L2; `redirect_cap` semantics applied).
         - `resp = await client.get(url)`.
         - **Content-type dispatch**:
           - `ct = resp.headers.get("content-type", "")`.
           - If `_is_binary_content_type(ct)`:
             - return `f"[error] binary content ({len(resp.content)} bytes; type={ct.split(';')[0]}) — use download_file for binary downloads"`. **No `[200]` prefix** — keeps `[error] {...}` shape consistent with L2's envelope; agents don't need the status code on a refusal.
           - Else if `"text/html"` in `ct.lower()`:
             - `from readability import Document`
             - `from markdownify import markdownify`
             - `summary_html = Document(resp.text).summary()` — extract main content
             - `markdown = markdownify(summary_html, heading_style="ATX")` — convert to markdown using `#` headings (compact + agent-friendly; default `"underlined"` style produces `===` underlines that are clunkier).
             - Then truncate via `_truncate_response(markdown.encode("utf-8"), cfg, content_type=None)` (None content-type → text path; we've already produced markdown bytes).
             - return `f"[{resp.status_code}]\n{text}"`.
           - Else (text/plain, application/json, etc.):
             - `text, _ = _truncate_response(resp.content, cfg, content_type=ct)`.
             - return `f"[{resp.status_code}]\n{text}"`.
       - `except ConstraintError as e: return f"[error] [constraint] {e}"`
       - `except (asyncio.TimeoutError, httpx.TimeoutException): return f"[error] Fetch timed out after {clipped}s"` (F5 wording — distinct from `http_request`'s "Request timed out").
       - `except httpx.TooManyRedirects: return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"`.
       - `except Exception as e: return f"[error] {e}"`.
- `the_one/tools/builtins.py`:
  - Import `FetchUrlTool`.
  - Add to `_TOOL_CLASSES` (insert after `http_request`, before `web_search`):
    ```python
    "fetch_url": FetchUrlTool,
    ```
  - Total: 18 entries post-L3.
- `the_one/interfaces/web/static/js/areas/studio.js`:
  - Update `TOOL_CATEGORIES`: add `"fetch_url"` to the `'Web'` group, before `"http_request"` (or after — alphabetical is cleanest).
- `tests/test_web_tools.py`:
  - **New `TestFetchUrlTool` class**:
    - `test_html_extraction`: mock returns realistic article HTML — header + nav with several links + `<article>` containing `<h1>Title</h1>` plus 3 substantive paragraphs (~50 words each so readability's scoring actually triggers) + footer. Assert: `"# Title"` substring (ATX heading style), `"Para 1"` (or whatever distinctive article-body phrase) substring, response status `[200]` substring. **Do not** assert `"nav" not in markdown` — readability's stripping is content-density-based and may keep nav on shorter fixtures; the regression net is the article's presence, not the boilerplate's absence. Architect verified the trivial fixture (the leg's first draft) does NOT strip nav reliably.
    - `test_text_plain_passthrough`: mock returns `Content-Type: text/plain`; body returned decoded.
    - `test_json_passthrough`: mock returns `Content-Type: application/json`; body returned decoded.
    - `test_binary_refused`: mock returns `Content-Type: application/pdf` and 50-byte body; tool returns `[error] binary content (50 bytes; type=application/pdf) — use download_file for binary downloads`. **No `[200]` prefix** in the asserted error string.
    - `test_url_check_refused`: mock not invoked; agent passes `ftp://...` → `[error] [constraint] scheme 'ftp' refused`.
    - `test_size_cap_truncated`: mock returns 5KB HTML body; cfg has `response_size_cap_bytes=1024`; markdown output contains the truncation marker.
    - `test_timeout_via_httpx_readtimeout`: mock raises `httpx.ReadTimeout`; tool returns `[error] Fetch timed out after Ns`.
    - `test_construction_shape`: `FetchUrlTool(WebConfig())` builds; `Config is WebConfig`.
- `tests/test_builtins.py` — **update all sites explicitly** (architect-enumerated):
  - Three numeric assertions: lines ~56, ~63, ~108 — change `17` → `18`.
  - One tool-name set literal at lines ~67-83 — add `"fetch_url"` (alphabetical position: after `"edit_file"` / before `"glob"` if sorted, or simply append).
  - Two comment references at lines ~54, ~103 — update `17` → `18` so the comments stay accurate.

## Acceptance Criteria

- [x] `the_one/tools/web.py::FetchUrlTool` exists with `Config = WebConfig`.
- [x] `description` mentions readability-extraction-for-HTML, raw-for-text/JSON, refuse-binary, and the same constraint surface as `http_request`. Small-model-readable (~80 words).
- [x] `parameters.url` is the only required param; no `timeout` exposed.
- [x] Four-clause envelope (mirrors L2): `ConstraintError → (asyncio.TimeoutError, httpx.TimeoutException) → httpx.TooManyRedirects → Exception`.
- [x] Float-preserving timeout: `clipped = cfg.timeout_seconds_default` (no per-call clip needed since no agent param).
- [x] **Content-type dispatch correct**:
  - `text/html` → readability extraction → markdownify → `_truncate_response`.
  - Binary → `[error] binary content` with size + type + guidance to `download_file`.
  - Other text → `_truncate_response` directly.
- [x] `_build_transport(cfg)` helper mirrors L2's test-seam pattern.
- [x] Timeout-error wording: `[error] Fetch timed out after Ns` (F5-specific; distinct from L2 wording).
- [x] Registered in `_TOOL_CLASSES` (18 entries) and Studio `TOOL_CATEGORIES['Web']`.
- [x] All 8 new `TestFetchUrlTool` tests pass.
- [x] `test_builtins.py::_TOOL_CLASSES` count assertions updated (17 → 18) at all sites.
- [x] Full unit suite green (modulo CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
docker exec the-one python -c "
from the_one.tools.web import FetchUrlTool
from the_one.tools._web_config import WebConfig
t = FetchUrlTool(WebConfig())
assert t.Config is WebConfig
print('OK construction')
"

docker exec the-one python -c "
from the_one.tools.builtins import _TOOL_CLASSES
assert len(_TOOL_CLASSES) == 18, len(_TOOL_CLASSES)
assert 'fetch_url' in _TOOL_CLASSES
print('OK 18 tools')
"

docker exec the-one python -c "
import asyncio
import httpx
from the_one.tools.web import FetchUrlTool
from the_one.tools._web_config import WebConfig
async def main():
    def handler(request):
        return httpx.Response(200, content=b'<html><body><article><h1>Hello</h1><p>World</p></article></body></html>', headers={'content-type': 'text/html'})
    t = FetchUrlTool(WebConfig())
    t._build_transport = lambda cfg: httpx.MockTransport(handler)
    out = await t.execute(url='http://example.com/article')
    assert '[200]' in out
    assert 'Hello' in out
    assert 'World' in out
    print('OK readability extraction')
asyncio.run(main())
"

docker exec the-one pytest tests/test_web_tools.py tests/test_builtins.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined
docker exec the-one ruff check the_one/tools/web.py the_one/tools/builtins.py tests/test_web_tools.py tests/test_builtins.py
```

## Implementation Guidance

1. **Append `FetchUrlTool` to `the_one/tools/web.py`** following L2's `HttpRequestTool` pattern. Reuse the same `_build_transport(cfg)` shape.

2. **Lazy import `readability` and `markdownify` inside the HTML branch** — keeps tool-class import time fast, and lets unit tests that don't exercise HTML extraction skip the heavy lxml import.

3. **`Document(...).summary()`** returns HTML, NOT markdown. Need `markdownify(...)` to convert.

4. **markdownify default options**: leave defaults for F5; `markdownify(html, heading_style="ATX")` is a possible refinement (uses `#` instead of underline style for h1/h2). Defer to a future flight if the agent's output looks ugly.

5. **HTML extraction edge cases**:
   - Document with no `<article>` / `<main>` / sensible structure → readability falls back to whole `<body>` content. Acceptable.
   - Empty HTML → readability raises or returns empty summary. Catch `Exception` in the generic branch (the four-clause envelope's last branch covers this).

6. **Binary content size message format**: `f"[{status_code}] [error] binary content ({len(content)} bytes; type={ct_no_charset}) — use download_file for binary downloads"`. The `[status_code]` prefix is included so the agent knows the request succeeded but the content was refused for content-type reasons (vs. SSRF/policy refusal which doesn't have a status).

7. **Lint**: ruff may flag the lazy imports; that's fine, they're inside the function.

## Edge Cases

- **`readability.Document` raises on weird HTML**: caught by the generic `except Exception` clause → `[error] {e}`. Acceptable.
- **`markdownify` strips images by default**: agents see text-only output. For F5 that's fine; image-preservation is a future concern.
- **JSON pretty-printing**: not done. Agents that want pretty JSON can pipe through `python_exec`. Don't expand the tool surface.
- **`Content-Type: text/html; charset=utf-8`** (with parameters): the dispatch uses `"text/html" in ct.lower()` substring match, so charset suffix doesn't break detection.
- **Empty body**: `Document("")` likely raises; caught by generic Exception. Tool returns `[error] {e}`. Acceptable.
- **Redirect to a binary**: the redirect is followed by httpx, then content-type dispatch picks the binary branch. Same outcome as a direct binary URL.

## Files Affected

- `the_one/tools/web.py` — append `FetchUrlTool` class.
- `the_one/tools/builtins.py` — import + register in `_TOOL_CLASSES`.
- `the_one/interfaces/web/static/js/areas/studio.js` — add `"fetch_url"` to `TOOL_CATEGORIES['Web']`.
- `tests/test_web_tools.py` — new `TestFetchUrlTool` class with 8 tests.
- `tests/test_builtins.py` — update count assertions (17 → 18) and tool-name set.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
