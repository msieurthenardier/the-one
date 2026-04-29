"""Direct unit tests for web tools after L6 (Tool ABC contract verification).

These tests cover the regression invariant for L6: `HttpRequestTool` and
`WebSearchTool` continue to honor the L3 Tool ABC contract (`Config = _EmptyConfig`,
`__init__(config)`) without any source migration — `httpx` is already cross-platform,
so no platform-layer routing is needed. The tests use `httpx.MockTransport` to
inject controlled responses without real network calls, locking in today's
formatted-string contracts (`[200]\\n<body>`, `[error] <msg>`, `(no output)` is
not used here — different formatter than the execution tools) before F5
introduces SSRF protection, response-size caps, redirect caps, and URL/host
allowlists.

Mocking pattern:
  `_install_mock(monkeypatch, handler)` replaces `httpx.AsyncClient` with a
  factory that injects a `MockTransport` carrying a per-test request handler.
  The handler signature is `(httpx.Request) -> httpx.Response`; it can also
  raise (e.g. `httpx.ConnectError`) to exercise the network-error path.

  CRITICAL: `original = httpx.AsyncClient` is captured BEFORE `monkeypatch.setattr`
  so the factory's call to `original(...)` does NOT recurse through the patched
  symbol. This is documented in the L6 leg's Edge Cases section.

F5 regression-net intent:
  These tests assert on the literal `[200]\\n...` and `[error] ...` formatted-string
  contracts. F5 (SSRF protection, response-size caps, redirect caps, URL/host
  allowlist) MUST NOT change those formatted-string contracts without consciously
  updating these assertions; a silent contract change will fail the L6 tests,
  which is the desired regression signal.

`MockTransport` and `follow_redirects=True`:
  `httpx.MockTransport` does NOT auto-handle redirect chains — F2 doesn't test
  them; F5 will. Documented here for forward reference.

Tests written as `async def` per the project's `asyncio_mode = "auto"` config
(consistent with L1/L4/L5 anomaly resolution). No `@pytest.mark.asyncio` needed.
"""

from __future__ import annotations

import httpx

from the_one.tools.resolver import _EmptyConfig
from the_one.tools.web import HttpRequestTool, WebSearchTool


def _install_mock(monkeypatch, handler) -> None:
    """Replace httpx.AsyncClient with a MockTransport-backed variant.

    `original` is captured BEFORE monkeypatch.setattr to avoid infinite
    recursion: if we called `httpx.AsyncClient(...)` inside the factory after
    patching, it would resolve back to the factory itself.
    """
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
        result = await HttpRequestTool().execute(
            method="GET", url="https://example.test/"
        )
        assert result.startswith("[200]")
        assert "hello world" in result

    async def test_non_200_status(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(
            method="GET", url="https://example.test/x"
        )
        assert result.startswith("[404]")
        assert "not found" in result

    async def test_headers_passed_through(self, monkeypatch) -> None:
        captured: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, text="ok")

        _install_mock(monkeypatch, handler)
        await HttpRequestTool().execute(
            method="GET",
            url="https://example.test/",
            headers={"Authorization": "Bearer abc"},
        )
        assert captured["auth"] == "Bearer abc"

    async def test_body_passed_through(self, monkeypatch) -> None:
        captured: dict[str, bytes] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content
            return httpx.Response(200, text="ok")

        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(
            method="POST", url="https://example.test/", body="payload"
        )
        assert captured["body"] == b"payload"
        # Closes the formatter contract loop on the POST happy path too.
        assert "[200]" in result

    async def test_truncation_at_10000_chars(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="x" * 20000)

        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(
            method="GET", url="https://example.test/"
        )
        # Format: "[200]\n" + first 10000 chars of body = 10006 total.
        # Locks in "no trailing newline, no header overhead beyond `[200]\n`".
        assert len(result) == len("[200]\n") + 10000
        assert len(result) == 10006

    async def test_network_error_returns_error_string(
        self, monkeypatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")

        _install_mock(monkeypatch, handler)
        result = await HttpRequestTool().execute(
            method="GET", url="https://example.test/"
        )
        assert result.startswith("[error]")
        assert "nope" in result


# DDG fixture HTML — structure matches the existing regex:
#   class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?
#   class="result__snippet"[^>]*>(.*?)</span>
# (re.DOTALL). Each result block must keep the anchor → snippet ordering
# the regex expects.
_DDG_HTML_TWO_RESULTS = """
<html><body>
<a class="result__a" href="https://a.example/">Title A</a>
<span class="result__snippet">Snippet A text</span>
<a class="result__a" href="https://b.example/">Title B</a>
<span class="result__snippet">Snippet B text</span>
</body></html>
"""

_DDG_HTML_FIVE_RESULTS = (
    "<html><body>"
    + "".join(
        f'<a class="result__a" href="https://r{i}.example/">Title {i}</a>'
        f'<span class="result__snippet">Snippet {i}</span>'
        for i in range(5)
    )
    + "</body></html>"
)

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
        # Exactly 2 results appear; results 2-4 do not.
        assert result.count("Title ") == 2
        assert "Title 0" in result and "Title 1" in result
        assert "Title 2" not in result
        assert "Title 3" not in result
        assert "Title 4" not in result

    async def test_post_body_form_encoded(self, monkeypatch) -> None:
        captured: dict[str, bytes] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content
            return httpx.Response(200, text=_DDG_HTML_NO_RESULTS)

        _install_mock(monkeypatch, handler)
        await WebSearchTool().execute(query="hi")
        # DDG requires form-encoded POST body with q=<query>.
        assert b"q=hi" in captured["body"]

    async def test_no_results(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_NO_RESULTS)

        _install_mock(monkeypatch, handler)
        result = await WebSearchTool().execute(query="hi")
        assert result == "No results found."

    async def test_network_error_returns_error_string(
        self, monkeypatch
    ) -> None:
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
