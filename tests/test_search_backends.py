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
    DDGSearchBackend,
    SearchBackend,
    SearchResult,
)

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
_DDG_HTML_EMPTY = "<html><body><p>nothing here</p></body></html>"
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

    async def test_no_results_returns_empty(self, monkeypatch) -> None:
        """Mock returns 200 + a page with NO ``result__a`` markers — backend
        returns ``[]`` without raising. (Anti-bot interstitial detection:
        the ``"result__a" not in text`` short-circuit fires.)"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_DDG_HTML_EMPTY)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        results = await backend.search("anything", max_results=5)

        assert results == []

    async def test_anti_bot_interstitial_returns_empty(self, monkeypatch, caplog) -> None:
        """Mock returns 202 + interstitial HTML (no result markers). Backend
        returns ``[]`` and logs a warning."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(202, text=_DDG_INTERSTITIAL_HTML)

        _install_owned_mock(monkeypatch, handler)
        backend = DDGSearchBackend()
        with caplog.at_level(logging.WARNING):
            results = await backend.search("anything", max_results=5)

        assert results == []
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
