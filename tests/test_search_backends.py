"""Direct unit tests for ``the_one.tools._search_backends`` (F5 L5).

Three test classes:

* ``TestSearchResult`` — frozen-dataclass shape.
* ``TestSearchBackendProtocol`` — runtime_checkable + method-signature
  isinstance behavior.
* ``TestDDGSearchBackend`` — F1 fix (browser UA), DDG HTML parsing
  (multiple results), ``max_results`` clamp, empty-page + anti-bot
  interstitial graceful empty return, owned-client + injected-client
  lifecycle.

Mocking pattern: ``httpx.MockTransport`` wraps a handler closure that can
either capture the inbound request (for the UA test) or return a canned
response (for parsing tests). The injected-client tests construct
``httpx.AsyncClient(transport=httpx.MockTransport(...))`` directly and
hand it to ``DDGSearchBackend(http_client=...)``. The owned-client tests
monkeypatch ``httpx.AsyncClient`` at module scope so the backend's
``async with httpx.AsyncClient(...)`` block transparently uses the mock.

Tests written as ``async def`` per the project's ``asyncio_mode = "auto"``
config — no ``@pytest.mark.asyncio`` decorator needed.
"""

from __future__ import annotations

import dataclasses
import logging

import httpx
import pytest

from the_one.tools._search_backends import (
    _DDG_BROWSER_UA,
    BraveSearchBackend,
    DDGSearchBackend,
    GooglePSESearchBackend,
    SearchBackend,
    SearchBlockedError,
    SearchResult,
    SearchUnavailableError,
    SearxngSearchBackend,
    TavilySearchBackend,
    build_search_backend,
)
from the_one.tools._web_search_config import WebSearchConfig

# ---------------------------------------------------------------------------
# DDG HTML fixtures (small but exercise the parsing path verbatim)
# ---------------------------------------------------------------------------


def _make_ddg_html(n: int) -> str:
    """Build a minimal DDG-like HTML response with ``n`` result markers.

    The parsing regex captures ``result__a`` href + title and
    ``result__snippet`` body — anything around those markers is ignored.
    Title and snippet contain a stub ``<b>`` tag so the HTML-tag-strip
    assertions have something to verify.
    """
    body_parts = []
    for i in range(n):
        body_parts.append(
            f'<a class="result__a" href="https://example.com/page{i}">'
            f"Result <b>{i}</b> Title</a>"
            f'<span class="result__snippet">'
            f"Snippet <b>{i}</b> body text</span>"
        )
    return "<html><body>" + "".join(body_parts) + "</body></html>"


_DDG_HTML_TEN = _make_ddg_html(10)
# Genuine zero-hit page — carries DDG's positive ``no-results`` marker but no
# ``result__a`` markers. M16 F08 L02 Option B: this returns ``[]``.
_DDG_HTML_NO_RESULTS = '<html><body><div class="no-results">No results.</div></body></html>'
# Interstitial / parse-failure — NEITHER ``result__a`` NOR ``no-results``.
# M16 F08 L02 Option B: this raises ``SearchBlockedError``.
_DDG_INTERSTITIAL_HTML = (
    "<html><head><title>DuckDuckGo</title></head>"
    "<body><p>Please wait while we verify your request</p></body></html>"
)


# ---------------------------------------------------------------------------
# Owned-client monkeypatch helper
# ---------------------------------------------------------------------------


def _install_owned_mock(monkeypatch, handler) -> None:
    """Replace ``httpx.AsyncClient`` with a factory that injects a
    ``MockTransport(handler)`` so ``DDGSearchBackend()``'s owned-client
    path (``async with httpx.AsyncClient(...) as client:``) transparently
    uses the mock.
    """
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# ---------------------------------------------------------------------------
# TestSearchResult
# ---------------------------------------------------------------------------


class TestSearchResult:
    def test_dataclass_frozen(self) -> None:
        result = SearchResult(title="t", url="u", snippet="s")
        assert result.title == "t"
        assert result.url == "u"
        assert result.snippet == "s"
        assert dataclasses.is_dataclass(result)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.title = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestSearchBackendProtocol
# ---------------------------------------------------------------------------


class TestSearchBackendProtocol:
    def test_protocol_runtime_checkable(self) -> None:
        backend = DDGSearchBackend()
        assert isinstance(backend, SearchBackend)

    def test_protocol_method_signature(self) -> None:
        # A class missing ``search`` fails the runtime isinstance check.
        class _NoSearch:
            name = "stub"

        assert not isinstance(_NoSearch(), SearchBackend)

        # A class with a ``search`` attribute (callable; signature is not
        # validated by ``runtime_checkable`` — Protocol checks attribute
        # presence only, NOT call signatures) passes the check.
        class _HasSearch:
            name = "stub"

            async def search(self, query: str, max_results: int) -> list[SearchResult]:
                return []

        assert isinstance(_HasSearch(), SearchBackend)


# ---------------------------------------------------------------------------
# TestDDGSearchBackend
# ---------------------------------------------------------------------------


class TestDDGSearchBackend:
    async def test_user_agent_sent(self, monkeypatch) -> None:
        """F1 fix pin — the backend MUST send the Chrome-on-Linux UA so DDG
        bypasses the anti-bot interstitial. Without this, DDG returns 202 +
        empty results (verified live during F5 planning)."""
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["user_agent"] = request.headers.get("User-Agent", "")
            captured["url"] = str(request.url)
            captured["method"] = request.method
            return httpx.Response(200, text=_DDG_HTML_TEN)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        await backend.search("python asyncio", max_results=5)

        assert captured["user_agent"] == _DDG_BROWSER_UA
        assert captured["method"] == "POST"
        assert "duckduckgo" in captured["url"]

    async def test_parses_10_results(self, monkeypatch) -> None:
        """Realistic DDG HTML with 10 ``result__a`` / ``result__snippet``
        pairs — assert all 10 parsed, all fields populated, HTML tags
        stripped from title and snippet."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_TEN)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        results = await backend.search("anything", max_results=10)

        assert len(results) == 10
        for i, result in enumerate(results):
            assert result.title == f"Result {i} Title"
            assert result.url == f"https://example.com/page{i}"
            assert result.snippet == f"Snippet {i} body text"
            # HTML tags stripped.
            assert "<b>" not in result.title
            assert "<b>" not in result.snippet

    async def test_max_results_limits(self, monkeypatch) -> None:
        """Mock returns 10 result markers; ``max_results=3`` clamps to 3."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_TEN)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        results = await backend.search("x", max_results=3)

        assert len(results) == 3
        assert results[0].title == "Result 0 Title"
        assert results[2].title == "Result 2 Title"

    async def test_genuine_no_results_returns_empty(self, monkeypatch) -> None:
        """M16 F08 L02 (Option B): 200 with NO ``result__a`` markers but WITH
        DDG's positive ``no-results`` marker is a GENUINE empty search —
        backend returns ``[]`` without raising. (Was ``test_no_results_returns_empty``
        under the old blanket-``[]``-on-no-marker contract.)"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_NO_RESULTS)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        results = await backend.search("zxqzqweqweqwe nonexistent", max_results=5)

        assert results == []

    async def test_anti_bot_interstitial_raises_blocked(self, monkeypatch, caplog) -> None:
        """M16 F08 L02 (Option B): 200 with NEITHER ``result__a`` NOR the
        ``no-results`` marker is an interstitial / parse-failure — backend
        raises ``SearchBlockedError`` (was ``test_anti_bot_interstitial_returns_empty``
        which asserted the old ``[]``-on-failure contract). Distinguishes a
        broken search from "the web has nothing"."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_INTERSTITIAL_HTML)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        with caplog.at_level(logging.WARNING):
            with pytest.raises(SearchBlockedError):
                await backend.search("anything", max_results=5)

    async def test_non_200_raises_blocked(self, monkeypatch, caplog) -> None:
        """M16 F08 L02: a non-200 status (anti-bot 202) raises
        ``SearchBlockedError`` and logs a warning (no key/secret in the log —
        DDG is keyless)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(202, text=_DDG_INTERSTITIAL_HTML)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        with caplog.at_level(logging.WARNING):
            with pytest.raises(SearchBlockedError):
                await backend.search("anything", max_results=5)
        assert any(
            "non-200" in record.message or "202" in record.message for record in caplog.records
        )

    async def test_owned_client_lifecycle(self, monkeypatch) -> None:
        """``DDGSearchBackend()`` (no injected client) creates a fresh
        ``httpx.AsyncClient`` per call. Two consecutive ``search()`` calls
        succeed without errors — proves the per-call ``async with`` block
        opens and closes cleanly each time."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_TEN)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        first = await backend.search("call-1", max_results=2)
        second = await backend.search("call-2", max_results=2)

        assert len(first) == 2
        assert len(second) == 2

    async def test_injected_client_lifecycle(self) -> None:
        """``DDGSearchBackend(http_client=injected)`` uses the injected
        client directly. Caller is responsible for opening + closing."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_TEN)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            backend = DDGSearchBackend(http_client=client)
            results = await backend.search("anything", max_results=5)

        assert len(results) == 5
        assert results[0].url == "https://example.com/page0"


# ---------------------------------------------------------------------------
# Keyed-backend mock helper (M16 F08 L02)
# ---------------------------------------------------------------------------


def _install_keyed_mock(monkeypatch, handler) -> dict:
    """Replace ``_search_backends._new_client`` so each keyed backend's per-call
    ``async with _new_client(...)`` block transparently uses a
    ``MockTransport(handler)``-backed client. Returns a dict the handler can
    write the captured request into."""
    import the_one.tools._search_backends as sb

    captured: dict = {}
    transport = httpx.MockTransport(handler)

    def factory(extra_allowed_hosts):
        captured["extra_allowed_hosts"] = extra_allowed_hosts
        return httpx.AsyncClient(timeout=15, transport=transport)

    monkeypatch.setattr(sb, "_new_client", factory)
    return captured


# ---------------------------------------------------------------------------
# TestSearxngSearchBackend
# ---------------------------------------------------------------------------


class TestSearxngSearchBackend:
    async def test_success_maps_results(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params.get("format") == "json"
            assert "/search" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "T1", "url": "https://a/", "content": "C1"},
                        {"title": "T2", "url": "https://b/", "content": "C2"},
                    ]
                },
            )

        _install_keyed_mock(monkeypatch, handler)
        backend = SearxngSearchBackend(base_url="https://searx.example.org")
        results = await backend.search("q", max_results=5)
        assert results == [
            SearchResult(title="T1", url="https://a/", snippet="C1"),
            SearchResult(title="T2", url="https://b/", snippet="C2"),
        ]

    async def test_missing_base_url_raises_unavailable(self) -> None:
        backend = SearxngSearchBackend(base_url="")
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)

    async def test_non_200_raises_unavailable(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="oops")

        _install_keyed_mock(monkeypatch, handler)
        backend = SearxngSearchBackend(base_url="https://searx.example.org")
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)

    async def test_genuine_empty_returns_empty(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"results": []})

        _install_keyed_mock(monkeypatch, handler)
        backend = SearxngSearchBackend(base_url="https://searx.example.org")
        assert await backend.search("q", max_results=5) == []

    async def test_non_json_html_raises_unavailable(self, monkeypatch) -> None:
        """JSON format not enabled on the instance -> HTML body -> unavailable."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        _install_keyed_mock(monkeypatch, handler)
        backend = SearxngSearchBackend(base_url="https://searx.example.org")
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)


# ---------------------------------------------------------------------------
# TestGooglePSESearchBackend
# ---------------------------------------------------------------------------


class TestGooglePSESearchBackend:
    async def test_success_maps_items(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params.get("key") == "KEY"
            assert request.url.params.get("cx") == "CSE"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"title": "T", "link": "https://g/", "snippet": "S"},
                    ]
                },
            )

        _install_keyed_mock(monkeypatch, handler)
        backend = GooglePSESearchBackend(api_key="KEY", cse_id="CSE")
        results = await backend.search("q", max_results=5)
        assert results == [SearchResult(title="T", url="https://g/", snippet="S")]

    async def test_missing_key_raises_unavailable(self) -> None:
        with pytest.raises(SearchUnavailableError):
            await GooglePSESearchBackend(api_key="", cse_id="CSE").search("q", max_results=5)

    async def test_missing_cse_raises_unavailable(self) -> None:
        with pytest.raises(SearchUnavailableError):
            await GooglePSESearchBackend(api_key="KEY", cse_id="").search("q", max_results=5)

    async def test_non_200_raises_unavailable(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        _install_keyed_mock(monkeypatch, handler)
        backend = GooglePSESearchBackend(api_key="KEY", cse_id="CSE")
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)

    async def test_genuine_empty_returns_empty(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"searchInformation": {"totalResults": "0"}})

        _install_keyed_mock(monkeypatch, handler)
        backend = GooglePSESearchBackend(api_key="KEY", cse_id="CSE")
        assert await backend.search("q", max_results=5) == []


# ---------------------------------------------------------------------------
# TestBraveSearchBackend
# ---------------------------------------------------------------------------


class TestBraveSearchBackend:
    async def test_success_maps_web_results(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-Subscription-Token") == "KEY"
            assert request.headers.get("Accept") == "application/json"
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"title": "BT", "url": "https://br/", "description": "BD"},
                        ]
                    }
                },
            )

        _install_keyed_mock(monkeypatch, handler)
        backend = BraveSearchBackend(api_key="KEY")
        results = await backend.search("q", max_results=5)
        assert results == [SearchResult(title="BT", url="https://br/", snippet="BD")]

    async def test_missing_key_raises_unavailable(self) -> None:
        with pytest.raises(SearchUnavailableError):
            await BraveSearchBackend(api_key="").search("q", max_results=5)

    async def test_429_raises_blocked(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="rate limited")

        _install_keyed_mock(monkeypatch, handler)
        backend = BraveSearchBackend(api_key="KEY")
        with pytest.raises(SearchBlockedError):
            await backend.search("q", max_results=5)

    async def test_other_non_200_raises_unavailable(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized")

        _install_keyed_mock(monkeypatch, handler)
        backend = BraveSearchBackend(api_key="KEY")
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)

    async def test_genuine_empty_returns_empty(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"web": {"results": []}})

        _install_keyed_mock(monkeypatch, handler)
        backend = BraveSearchBackend(api_key="KEY")
        assert await backend.search("q", max_results=5) == []


# ---------------------------------------------------------------------------
# TestTavilySearchBackend
# ---------------------------------------------------------------------------


class TestTavilySearchBackend:
    async def test_success_maps_results(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "TT", "url": "https://tv/", "content": "TC"},
                    ]
                },
            )

        _install_keyed_mock(monkeypatch, handler)
        backend = TavilySearchBackend(api_key="KEY")
        results = await backend.search("q", max_results=5)
        assert results == [SearchResult(title="TT", url="https://tv/", snippet="TC")]

    async def test_missing_key_raises_unavailable(self) -> None:
        with pytest.raises(SearchUnavailableError):
            await TavilySearchBackend(api_key="").search("q", max_results=5)

    async def test_non_200_raises_unavailable(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="bad request")

        _install_keyed_mock(monkeypatch, handler)
        backend = TavilySearchBackend(api_key="KEY")
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)

    async def test_genuine_empty_returns_empty(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"results": []})

        _install_keyed_mock(monkeypatch, handler)
        backend = TavilySearchBackend(api_key="KEY")
        assert await backend.search("q", max_results=5) == []


# ---------------------------------------------------------------------------
# TestBuildSearchBackend (registry / factory)
# ---------------------------------------------------------------------------


class TestBuildSearchBackend:
    def test_default_is_ddg(self) -> None:
        backend = build_search_backend(WebSearchConfig())
        assert isinstance(backend, DDGSearchBackend)
        assert backend.name == "duckduckgo"

    def test_explicit_duckduckgo(self) -> None:
        backend = build_search_backend(WebSearchConfig(search_backend="duckduckgo"))
        assert isinstance(backend, DDGSearchBackend)

    def test_selects_searxng(self) -> None:
        backend = build_search_backend(
            WebSearchConfig(search_backend="searxng", searxng_base_url="https://x")
        )
        assert isinstance(backend, SearxngSearchBackend)

    def test_selects_google_pse(self) -> None:
        backend = build_search_backend(
            WebSearchConfig(
                search_backend="google_pse",
                google_pse_api_key="K",
                google_pse_cse_id="C",
            )
        )
        assert isinstance(backend, GooglePSESearchBackend)

    def test_selects_brave(self) -> None:
        backend = build_search_backend(WebSearchConfig(search_backend="brave", brave_api_key="K"))
        assert isinstance(backend, BraveSearchBackend)

    def test_selects_tavily(self) -> None:
        backend = build_search_backend(WebSearchConfig(search_backend="tavily", tavily_api_key="K"))
        assert isinstance(backend, TavilySearchBackend)

    async def test_selected_but_unconfigured_raises_no_silent_ddg_fallback(self) -> None:
        """A keyed engine selected without its key still CONSTRUCTS, and raises
        ``SearchUnavailableError`` at call time — NOT a silent DDG fallback
        (that would hide misconfig)."""
        backend = build_search_backend(WebSearchConfig(search_backend="tavily"))
        assert isinstance(backend, TavilySearchBackend)
        with pytest.raises(SearchUnavailableError):
            await backend.search("q", max_results=5)

    def test_extra_allowed_hosts_threaded_to_ddg(self) -> None:
        backend = build_search_backend(WebSearchConfig(), extra_allowed_hosts=["localhost:8888"])
        assert backend._extra_allowed_hosts == ("localhost:8888",)
