# Leg: 06-migrate-web-tools

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Confirm `HttpRequestTool` and `WebSearchTool` work correctly under L3's Tool ABC contract (`Config = _EmptyConfig`, `__init__(config)`) without any platform-layer routing — `httpx` is already cross-platform. Add direct execute-path regression tests using `httpx.MockTransport` so behavior is locked in before F5 introduces SSRF protection, response-size caps, redirect caps, and the URL/host allowlist.

## Context

Third and final tool-migration leg in F2. Per the flight Technical Approach: "L6 is small — `HttpRequestTool` and `WebSearchTool` don't need platform-layer routing (httpx is already cross-platform; their HTML parsing is platform-independent)." Per Decision 5, `Tool.Config = _EmptyConfig` empty default still applies. F5 (Web Expansion & Constraints) will introduce real fields.

**No source migration is needed.** Both web tools already inherit the L3 Tool ABC change without code changes. L6's deliverables are:

1. Verify the inheritance is observably correct (Tool ABC instantiation regression test, mirroring L4/L5 patterns)
2. Add direct execute-path regression tests with `httpx.MockTransport` — locking in today's behavior so F5 has a regression net
3. Document the no-source-migration outcome in the flight log

`web_search` is known to return zero results in the running container (per mission Known Issues, L4 of F1). The L6 tests use mocked DDG HTML content, NOT real network calls, so the known-issue does not block L6.

### v8 baseline (verified at L6 design time, post-L5)

- `the_one/tools/web.py:10-48` — `HttpRequestTool.execute(method, url, headers=None, body=None, **kwargs)`:
  - Uses `httpx.AsyncClient(timeout=30, follow_redirects=True)` as async context manager
  - Calls `client.request(method, url, headers=headers, content=body)`
  - Truncates response text to first 10000 chars
  - Returns `f"[{resp.status_code}]\n{text}"`
  - On `Exception`: returns `f"[error] {e}"`
- `the_one/tools/web.py:51-90` — `WebSearchTool.execute(query, max_results=5, **kwargs)`:
  - Uses `httpx.AsyncClient(timeout=15, follow_redirects=True)`
  - POSTs `data={"q": query}` to `https://html.duckduckgo.com/html/`
  - Regex extracts `result__a` href + title and `result__snippet` text
  - Returns `\n\n`-joined snippets, each formatted as `f"- {title}\n  {href}\n  {snippet}"`
  - Returns `"No results found."` if no snippets
  - On `Exception`: returns `f"[error] {e}"`
- `httpx >= 0.27` is a project dependency (per `pyproject.toml`); `httpx.MockTransport` is built-in (no `respx` needed).
- **No dedicated unit tests for `HttpRequestTool.execute` / `WebSearchTool.execute` exist today.** L6 adds them as regression coverage (paralleling L4/L5).

## Inputs

What exists before this leg runs:

- L1-L5 landed: platform package, schema v8, resolver + Tool ABC + per-agent instantiation, filesystem + execution tools migrated
- `httpx >= 0.27` available; `httpx.MockTransport` is the canonical mocking primitive
- Branch: `flight/02-cross-platform-foundations` (continuing from L5)

## Outputs

What exists after this leg completes:

- `the_one/tools/web.py` — **unchanged** (no source migration needed; httpx is already cross-platform)
- `tests/test_web_tools.py` (new) — direct execute-path tests for both web tools using `httpx.MockTransport` to inject controlled responses
- All previously passing tests continue passing (regression invariant)
- Flight log notes the no-source-migration outcome
- Flight log + leg + flight artifact updated

## Acceptance Criteria

- [ ] `the_one/tools/web.py` has **zero source modifications** in L6 — verify by `git diff -- the_one/tools/web.py` returning empty
- [ ] **Test: `tests/test_web_tools.py` (NEW)** — uses `httpx.MockTransport` (or monkeypatched `httpx.AsyncClient`) to inject controlled responses without real network calls:
  - `TestHttpRequestTool`:
    - Happy path GET: mock returns `200` with body `"hello world"`; `HttpRequestTool().execute(method="GET", url="https://example.test/")` returns string starting with `"[200]"` and containing `"hello world"`
    - Non-200 status: mock returns `404` with body `"not found"`; result starts with `"[404]"`
    - Headers passed through: mock asserts the request had `Authorization: Bearer abc`; tool call passes `headers={"Authorization": "Bearer abc"}`
    - Body passed through: mock asserts request body is the bytes `b"payload"`; tool call passes `body="payload"` and `method="POST"`
    - Truncation at 10000 chars: mock returns `"x" * 20000`; result length is exactly `len("[200]\n") + 10000` = 10006 chars (locks in "no trailing newline, no header overhead beyond `[200]\n`")
    - Network error: MockTransport handler raises `httpx.ConnectError("nope")`; result starts with `"[error]"` and contains `"nope"`
  - `TestWebSearchTool`:
    - Happy path: mock returns DDG-shaped HTML with two result blocks (each containing `result__a` + `result__snippet`); `WebSearchTool().execute(query="hi")` returns a string with both titles, links, and snippets
    - `max_results` honored: mock returns 5 result blocks; `execute(query="hi", max_results=2)` returns exactly 2 result blocks (`assert result.count("Title ") == 2` AND `assert "Title 2" not in result and "Title 3" not in result and "Title 4" not in result`)
    - POST body is form-encoded with `q=`: handler asserts `b"q=hi" in request.content` (locks in DDG's required form encoding)
    - No results: mock returns HTML with no `result__a` matches; result equals `"No results found."`
    - Network error: MockTransport handler raises; result starts with `"[error]"`
- [ ] **Tool ABC instantiation regression test** (in `test_web_tools.py`): each web tool can be instantiated with `cls()` and `cls(_EmptyConfig())`; both produce an `_EmptyConfig` `_config`
- [ ] All 7 existing tools' tests pass unchanged (no regressions). Notably:
  - `tests/test_builtins.py` — all 9 tests still pass
  - `tests/test_factory.py` — unchanged
  - `tests/test_filesystem_tools.py` (L4) and `tests/test_execution_tools.py` (L5) unchanged
- [ ] Pre-existing test suite still green (modulo pre-existing CSS-token red): `make test-unit` returns the L5-tip pass/fail set plus the new L6 tests
- [ ] No source code modified outside `tests/`
- [ ] Flight log explicitly documents the no-source-migration outcome (single sentence under L6 leg progress: "L6 added regression tests; no source migration was needed because httpx is already cross-platform")
- [ ] **F5 regression-net intent**: these tests assert on the literal `[200]\n...` and `[error] ...` formatted-string contracts. F5 (SSRF protection, response-size caps, redirect caps, URL/host allowlist) MUST not change those formatted-string contracts without consciously updating these assertions; a silent contract change will fail the L6 tests, which is the desired regression signal.
- [ ] AIAT live smoke (best-effort): try `pytest -m live tests/test_aiat.py`; document continued skip if pre-existing fixture ScopeMismatch persists (per L4/L5 Session Notes)

## Verification Steps

```bash
# Source diff inspection: web.py must NOT change (host)
git diff -- the_one/tools/web.py
# Expected: empty

# Build container with new test file
make rebuild

# Targeted tests
docker exec the-one pytest tests/test_web_tools.py -v
docker exec the-one pytest tests/test_builtins.py tests/test_factory.py \
    tests/test_filesystem_tools.py tests/test_execution_tools.py -v

# Full unit suite (pre-existing CSS red expected)
make test-unit

# Smoke: web tools instantiate cleanly under the L3 Tool ABC contract
docker exec the-one python -c "
from the_one.tools.web import HttpRequestTool, WebSearchTool
from the_one.tools.resolver import _EmptyConfig

for cls in (HttpRequestTool, WebSearchTool):
    t1 = cls()
    t2 = cls(_EmptyConfig())
    assert isinstance(t1._config, _EmptyConfig)
    assert isinstance(t2._config, _EmptyConfig)
print('OK')
"

# AIAT live smoke (best-effort — same pre-existing skip as L4/L5)
docker exec the-one pytest -m live tests/test_aiat.py -v || echo "AIAT skipped (pre-existing)"
```

## Implementation Guidance

### Mocking pattern: `httpx.MockTransport`

`httpx.MockTransport` is the canonical way to intercept httpx requests in tests. The web tools construct their own `httpx.AsyncClient` inside `execute()`, so we have to monkeypatch the `AsyncClient` constructor to inject the transport. Pattern:

```python
import httpx
import pytest

def _make_mock_client(handler):
    """Return a factory that produces an AsyncClient backed by MockTransport."""
    transport = httpx.MockTransport(handler)
    def factory(*args, **kwargs):
        # Drop any caller-supplied transport; force ours.
        kwargs.pop("transport", None)
        return httpx.AsyncClient(*args, transport=transport, **kwargs)
    return factory


@pytest.fixture
def mock_httpx(monkeypatch):
    """Yields a function: install a request handler that intercepts AsyncClient."""
    def install(handler):
        monkeypatch.setattr(httpx, "AsyncClient", _make_mock_client(handler))
    return install
```

The handler signature is `(request: httpx.Request) -> httpx.Response`. Use this for both happy-path and assertion-on-request tests.

### Test file skeleton

```python
from __future__ import annotations

import httpx
import pytest

from the_one.tools.resolver import _EmptyConfig
from the_one.tools.web import HttpRequestTool, WebSearchTool


def _install_mock(monkeypatch, handler):
    """Replace httpx.AsyncClient with a MockTransport-backed variant."""
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


class TestHttpRequestTool:
    async def test_happy_path_get(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            return httpx.Response(200, text="hello world")
        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(method="GET", url="https://example.test/")
        assert result.startswith("[200]")
        assert "hello world" in result

    async def test_non_200_status(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")
        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(method="GET", url="https://example.test/x")
        assert result.startswith("[404]")
        assert "not found" in result

    async def test_headers_passed_through(self, monkeypatch) -> None:
        captured = {}
        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, text="ok")
        _install_mock(monkeypatch, handler)
        await HttpRequestTool().execute(
            method="GET", url="https://example.test/",
            headers={"Authorization": "Bearer abc"},
        )
        assert captured["auth"] == "Bearer abc"

    async def test_body_passed_through(self, monkeypatch) -> None:
        captured = {}
        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content
            return httpx.Response(200, text="ok")
        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(
            method="POST", url="https://example.test/", body="payload",
        )
        assert captured["body"] == b"payload"
        assert "[200]" in result  # closes the formatter contract loop

    async def test_truncation_at_10000_chars(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="x" * 20000)
        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(method="GET", url="https://example.test/")
        # Format: "[200]\n" + first 10000 chars of body = 10006 total
        assert len(result) == len("[200]\n") + 10000

    async def test_network_error_returns_error_string(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")
        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(method="GET", url="https://example.test/")
        assert result.startswith("[error]")
        assert "nope" in result


_DDG_HTML_TWO_RESULTS = """
<html><body>
<a class="result__a" href="https://a.example/">Title A</a>
<span class="result__snippet">Snippet A text</span>
<a class="result__a" href="https://b.example/">Title B</a>
<span class="result__snippet">Snippet B text</span>
</body></html>
"""

_DDG_HTML_FIVE_RESULTS = """
<html><body>
""" + "".join(
    f'<a class="result__a" href="https://r{i}.example/">Title {i}</a>'
    f'<span class="result__snippet">Snippet {i}</span>'
    for i in range(5)
) + "</body></html>"

_DDG_HTML_NO_RESULTS = "<html><body><p>nothing here</p></body></html>"


class TestWebSearchTool:
    async def test_happy_path(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert "duckduckgo" in str(request.url)
            return httpx.Response(200, text=_DDG_HTML_TWO_RESULTS)
        _install_mock(monkeypatch, handler)
        result = await WebSearchTool().execute(query="hi")
        assert "Title A" in result and "Title B" in result
        assert "https://a.example/" in result and "https://b.example/" in result
        assert "Snippet A text" in result and "Snippet B text" in result

    async def test_max_results_honored(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_FIVE_RESULTS)
        _install_mock(monkeypatch, handler)
        result = await WebSearchTool().execute(query="hi", max_results=2)
        # Exactly 2 results appear; results 3-5 do not.
        assert result.count("Title ") == 2
        assert "Title 0" in result and "Title 1" in result
        assert "Title 2" not in result
        assert "Title 3" not in result
        assert "Title 4" not in result

    async def test_post_body_form_encoded(self, monkeypatch) -> None:
        captured = {}
        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content
            return httpx.Response(200, text=_DDG_HTML_NO_RESULTS)
        _install_mock(monkeypatch, handler)
        await WebSearchTool().execute(query="hi")
        # DDG requires form-encoded POST body with q=<query>
        assert b"q=hi" in captured["body"]

    async def test_no_results(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_NO_RESULTS)
        _install_mock(monkeypatch, handler)
        result = await WebSearchTool().execute(query="hi")
        assert result == "No results found."

    async def test_network_error_returns_error_string(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")
        _install_mock(monkeypatch, handler)
        result = await WebSearchTool().execute(query="hi")
        assert result.startswith("[error]")


class TestWebToolInstantiation:
    def test_each_tool_has_empty_config(self) -> None:
        for cls in (HttpRequestTool, WebSearchTool):
            t1 = cls()
            t2 = cls(_EmptyConfig())
            assert isinstance(t1._config, _EmptyConfig)
            assert isinstance(t2._config, _EmptyConfig)
```

### Implementation steps

**Pytest-asyncio note**: async tests rely on pytest-asyncio's `asyncio_mode = "auto"` (already configured for the project per L1/L4/L5 precedent). Write tests as `async def test_...` directly on test classes without `@pytest.mark.asyncio`.

**This is the first httpx-mocked test in this codebase.** Future leg authors that need httpx mocking can copy this `_install_mock` pattern.

1. **Verify no source migration is needed**: re-read `the_one/tools/web.py` and confirm there are no `Path(...).expanduser().resolve()` calls, no hardcoded `/bin/sh` or `python3`, no platform-specific subprocess invocation. Just `httpx.AsyncClient` calls. Do NOT modify `web.py`.

2. **Write `tests/test_web_tools.py`** per the skeleton above. Adapt the `_install_mock` helper as needed; keep handler functions tight.

3. **Run targeted tests**, then full suite:
   ```bash
   make rebuild
   docker exec the-one pytest tests/test_web_tools.py -v
   make test-unit
   ```

4. **AIAT smoke** (best-effort): same pre-existing fixture ScopeMismatch as L4/L5 likely persists; document the continued skip in the flight log under Session Notes (or under L6 progress entry; mirror the L4/L5 wording).

## Edge Cases

- **`httpx.MockTransport` constructor pattern**: `_install_mock` saves the original `httpx.AsyncClient` reference BEFORE patching, then the factory calls the original with the injected transport. This avoids infinite recursion when the factory itself triggers another `httpx.AsyncClient` lookup.
- **Test fixtures isolation**: `monkeypatch` is per-test; the patched `httpx.AsyncClient` is restored automatically. No teardown logic needed.
- **`MockTransport` and `follow_redirects=True`**: `httpx.MockTransport` does NOT auto-handle redirect chains — you'd need to return a `301`/`302` and have the handler called again. F2 doesn't test redirect chains; F5 will. Document explicitly.
- **`_DDG_HTML_FIVE_RESULTS` regex matching**: the existing `WebSearchTool` uses a multiline DOTALL regex to match `result__a` href + title and `result__snippet`. The fixture HTML must keep the structural relationship (anchor → snippet) the regex expects. The skeleton fixture follows the regex's expected format; verify visually before running.
- **Cache freshness contract** (per `/leg` skill section 6): no caches in web tools. Each `execute()` opens a fresh `httpx.AsyncClient` and closes it via the async context manager. No staleness concern.
- **State-machine reachability** (per `/leg` skill section 5): no states added or modified by L6. Both tool inputs/outputs are unchanged.
- **`web_search` real-world failure** (mission Known Issues, F1 L7 HAT): DuckDuckGo returns no results in the running container; F5 owns the fix. L6's mocked tests bypass this — the regression net is robust against real-DDG flakiness because we never call DDG.
- **Why no `respx`**: `httpx.MockTransport` is built-in to httpx ≥0.20 (verified against project's `httpx >= 0.27` pin). `respx` would be an additional dependency for the same outcome. Avoid.

## Files Affected

- `the_one/tools/web.py` — **unchanged** (no source migration)
- `tests/test_web_tools.py` — created
- `missions/.../flight-log.md` — append L6 progress entry (note no-source-migration outcome)
- `missions/.../flight.md` — check off L6 in Legs section + check off "Web tools migrated" checkpoint
- `missions/.../legs/06-migrate-web-tools.md` — set status `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (per agentic-workflow batched-review pattern, Developer does NOT commit; review and commit happen once at flight end):

- [ ] All acceptance criteria verified (especially the empty-diff check on `the_one/tools/web.py`)
- [ ] New `test_web_tools.py` tests passing
- [ ] Pre-existing unit suite still green (modulo pre-existing CSS-token red)
- [ ] AIAT smoke green or skip-with-explanation in flight log
- [ ] Update flight-log.md with L6 progress entry (note no-source-migration outcome)
- [ ] Set this leg's status to `landed`
- [ ] Check off L6 in flight.md (legs section AND "Web tools migrated" checkpoint)
- [ ] Do NOT commit — final commit happens once after L7
