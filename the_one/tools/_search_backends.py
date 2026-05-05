"""Pluggable search-backend protocol + DuckDuckGo concrete implementation (F5 L5).

Defines the ``SearchBackend`` Protocol contract — one method (``async search``)
plus a ``name`` ClassVar — and ships ``DDGSearchBackend`` as the first concrete
implementation. F5 ships only DDG; future missions can add Brave / Tavily /
Google CSE without touching ``WebSearchTool``. F6 admin will let operators
pick the active backend at runtime.

References:

* **F5 Decision 2** — ``SearchBackend`` extensibility shape: land the protocol
  now (one method, one concrete impl); F6 admin's "test button" needs a
  uniform interface across backends.
* **F5 Decision 12** — Backends are passed via ``cross_configs[SearchBackend]``
  injection (using the Protocol type as the dict key, mirroring
  ``cross_configs[FilesystemConfig]`` from F4). L6 wires
  ``WebSearchTool`` to consume it; L5 just defines the protocol + DDG impl in
  isolation (no ``BuiltinToolProvider`` changes here).
* **F1 known issue close** — ``https://html.duckduckgo.com/html/`` returns a
  202 anti-bot interstitial with no results when no User-Agent is sent (or
  when the_one's identifying default UA is sent). With a Chrome-on-Linux
  ``User-Agent`` the endpoint returns 200 + ``result__a`` / ``result__snippet``
  markers (verified live during F5 planning, count=10).

The backend is responsible for its own httpx client (owned per-call OR
injected at construction time). When wired through ``BuiltinToolProvider``
in L6, the injected client uses ``SSRFGuardedTransport`` so DDG / Brave /
etc. requests respect the operator's SSRF policy.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DDG anti-bot bypass (F1 fix)
# ---------------------------------------------------------------------------

# Browser User-Agent string sent to DDG's HTML endpoint to bypass the
# anti-bot interstitial. NOT the_one's ``_DEFAULT_USER_AGENT`` from L1 —
# DDG's interstitial specifically rejects identifying UAs. Verified live
# during F5 planning that this exact string returns 200 + 10 result markers
# from ``https://html.duckduckgo.com/html/``.
#
# Maintenance note: if DDG starts blocking Chrome 120 specifically, update
# this string to a more recent Chrome-on-Linux UA.
_DDG_BROWSER_UA: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Pre-compiled regex extracted verbatim from the pre-F5 ``WebSearchTool``
# implementation. Captures (href, title_html, snippet_html) per result.
# ``re.DOTALL`` so the inner ``.*?`` spans newlines in the response HTML.
_DDG_RESULT_REGEX: re.Pattern[str] = re.compile(
    r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
    r'class="result__snippet"[^>]*>(.*?)</span>',
    re.DOTALL,
)

# HTML tag stripper — removes ``<...>`` runs from title/snippet HTML so the
# returned ``SearchResult`` carries plain text. Does NOT decode entities
# (``&amp;``, ``&quot;``); future flight can add ``html.unescape()`` if
# small-model agents struggle with raw entities.
_HTML_TAG_REGEX: re.Pattern[str] = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# SearchResult dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """Single search result. Frozen so a backend's returned list is safe to
    pass through tool layers without defensive copies — a hostile or buggy
    consumer cannot mutate one result to corrupt a peer's view."""

    title: str
    url: str
    snippet: str


# ---------------------------------------------------------------------------
# SearchBackend Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SearchBackend(Protocol):
    """Pluggable search backend. F5 ships only ``DDGSearchBackend``; future
    missions can add Brave / Tavily / Google CSE without touching
    ``WebSearchTool``. F6 admin will let operators pick the active backend.

    The backend is responsible for its own httpx client (owned per-call OR
    injected at construction time). When wired through ``BuiltinToolProvider``
    (L6), the injected client uses ``SSRFGuardedTransport`` so DDG / Brave /
    etc. requests respect the operator's SSRF policy.

    ``runtime_checkable`` so ``isinstance(backend, SearchBackend)`` works
    for L6 wiring + future tests / admin UI introspection.
    """

    name: ClassVar[str]

    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# DDGSearchBackend concrete impl
# ---------------------------------------------------------------------------


class DDGSearchBackend:
    """DuckDuckGo HTML-endpoint backend.

    Closes F1 known issue (DDG returns no results without browser UA): sets
    a Chrome-on-Linux ``User-Agent`` that bypasses the anti-bot interstitial.
    Verified live during F5 planning that the same endpoint returns 200 +
    10 result markers with this UA.

    Lifecycle (F5 Decision 12 — internal owned-client semantics):

    * If ``__init__`` was passed an ``http_client``, ``search`` uses it
      directly — caller manages the client's lifecycle (open + close).
      L6 wires the SSRF-guarded client this way.
    * If no client was passed, ``search`` creates a short-lived
      ``async with httpx.AsyncClient(timeout=15) as client:`` per call —
      test-friendly default; backend works in isolation without the
      provider's SSRF transport.
    """

    name: ClassVar[str] = "duckduckgo"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        headers = {"User-Agent": _DDG_BROWSER_UA}
        url = "https://html.duckduckgo.com/html/"
        data = {"q": query}

        if self._client is not None:
            resp = await self._client.post(
                url,
                data=data,
                headers=headers,
                follow_redirects=True,
            )
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    data=data,
                    headers=headers,
                    follow_redirects=True,
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
