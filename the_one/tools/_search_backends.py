"""Pluggable search-backend registry + concrete implementations (F5 L5; M16 F08 L02).

Defines the ``SearchBackend`` Protocol contract — one method (``async search``)
plus a ``name`` ClassVar — and ships five concrete backends behind a registry
+ factory (``build_search_backend``): DuckDuckGo (keyless default), SearXNG,
Google Programmable Search Engine, Brave Search, and Tavily. The active engine
is chosen from the ``web_search`` tool's own ``WebSearchConfig.search_backend``.

**Honest-empty contract (M16 F08 L02 — HIGH-3).** Every backend distinguishes
three outcomes:

* **Genuine empty** — a valid provider response that carries zero hits →
  return ``[]``.
* **Blocked / throttled** — non-200 (or a provider-specific block code such as
  Brave 429), or a 200 that is an anti-bot interstitial / parse-failure with
  NEITHER results NOR a positive no-results marker → raise ``SearchBlockedError``.
* **Unavailable / misconfigured** — required config (url / api key / cse id)
  missing, or an unexpected non-2xx → raise ``SearchUnavailableError``.

``WebSearchTool.execute`` surfaces the raised typed error honestly
(``[error] …``) instead of collapsing every failure to "No results found." so
the model stops mistaking a broken search for "the web has nothing" and
guessing URLs.

References:

* **M16 F08 DD3 (refinement)** — the F5 "pluggable backend" decision is widened
  to a configurable engine *registry* inside the ``web_search`` tool config.
  This module is the backend half only — no admin UI, no secret-at-rest
  encryption (leg ``search-config-admin`` owns those).
* **F5 Decision 2** — ``SearchBackend`` extensibility shape: one uniform
  interface across backends (admin "test button" reads it).
* **F5 Decision 12** — backends are passed via ``cross_configs[SearchBackend]``
  injection (Protocol type as the dict key, mirroring
  ``cross_configs[FilesystemConfig]``).
* **F1 known issue close** — ``https://html.duckduckgo.com/html/`` returns a
  202 anti-bot interstitial with no results when no User-Agent is sent (or
  when the_one's identifying default UA is sent). With a Chrome-on-Linux
  ``User-Agent`` the endpoint returns 200 + ``result__a`` / ``result__snippet``
  markers (verified live during F5 planning, count=10). For a genuine
  zero-hit query the same endpoint returns 200 with a
  ``<div class="no-results">No results.</div>`` block and NO ``result__a``
  markers — that ``no-results`` class is the positive no-results marker keyed
  on below (Option B); it is the same marker the upstream ``ddgs`` /
  ``duckduckgo_search`` libraries and Open WebUI rely on.

Each backend owns a PER-CALL ``async with httpx.AsyncClient(transport=
SSRFGuardedTransport(extra_allowed_hosts=…))`` client (DDG additionally still
supports an injected client for the legacy test path). The factory passes the
SSRF *policy* (``extra_allowed_hosts``), NOT a live client — each backend
opens/closes its own client per call, matching DDG's owned-client pattern and
avoiding any client-lifecycle hook that ``get_tools`` does not have.

**Secret hygiene**: backends NEVER log api-key or base-url values — warnings
carry the provider name + status only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

import httpx

from the_one.tools._web_config import SSRFGuardedTransport

if TYPE_CHECKING:
    from the_one.tools._web_search_config import WebSearchConfig

logger = logging.getLogger(__name__)

# Per-call client timeout shared by all backends (seconds). DDG keeps its
# historical 15s; the keyed JSON APIs are fast enough to share it.
_CLIENT_TIMEOUT: float = 15.0


# ---------------------------------------------------------------------------
# Typed errors (M16 F08 L02 — HIGH-3)
# ---------------------------------------------------------------------------


class SearchError(Exception):
    (
        """Base for backend failures that ``WebSearchTool.execute`` surfaces
    honestly as ``[error] …`` rather than collapsing to "No results found."""
        ""
    )


class SearchBlockedError(SearchError):
    """The provider blocked / throttled the request, or returned an
    interstitial / unparseable page with no positive no-results marker.
    Distinct from a genuine empty result (``[]``)."""


class SearchUnavailableError(SearchError):
    """The backend cannot run: required config (url / api key / cse id) is
    missing, or the provider returned an unexpected non-2xx. Carries an
    actionable "configure X" message for the misconfig case."""


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

# DDG's positive no-results marker (Option B, M16 F08 L02). For a genuine
# zero-hit query ``html.duckduckgo.com/html/`` returns 200 with a
# ``<div class="no-results">No results.</div>`` block and NO ``result__a``
# markers. Keying on the ``no-results`` class (the same marker ``ddgs`` /
# Open WebUI use) lets us return ``[]`` for a real empty search while still
# raising ``SearchBlockedError`` for an interstitial / parse-failure that has
# NEITHER results NOR this marker.
_DDG_NO_RESULTS_MARKER: str = "no-results"


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
      directly — caller manages the client's lifecycle (open + close). The
      legacy test path uses this to inject a ``MockTransport``.
    * Otherwise ``search`` creates a short-lived per-call
      ``async with httpx.AsyncClient(transport=SSRFGuardedTransport(
      extra_allowed_hosts=…)) as client:`` — the wired path (M16 F08 L02):
      ``build_search_backend`` constructs DDG with the operator's
      ``extra_allowed_hosts`` so even DDG's request respects the SSRF policy.
    """

    name: ClassVar[str] = "duckduckgo"

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        extra_allowed_hosts: list[str] | tuple[str, ...] = (),
    ) -> None:
        self._client = http_client
        self._extra_allowed_hosts = tuple(extra_allowed_hosts)

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
            async with httpx.AsyncClient(
                timeout=_CLIENT_TIMEOUT,
                transport=SSRFGuardedTransport(extra_allowed_hosts=list(self._extra_allowed_hosts)),
            ) as client:
                resp = await client.post(
                    url,
                    data=data,
                    headers=headers,
                    follow_redirects=True,
                )

        # Honest-empty contract (Option B, M16 F08 L02):
        #   non-200                                -> SearchBlockedError
        #   200 + ``result__a`` markers            -> parse + return
        #   200, no results, WITH ``no-results``   -> [] (genuine empty)
        #   200, no results, no marker (interstitial/parse-fail)
        #                                          -> SearchBlockedError
        if resp.status_code != 200:
            logger.warning(
                "DDG returned non-200 status %s (likely anti-bot interstitial)",
                resp.status_code,
            )
            raise SearchBlockedError(
                f"DuckDuckGo returned {resp.status_code} (likely anti-bot interstitial)"
            )

        text = resp.text
        if "result__a" not in text:
            if _DDG_NO_RESULTS_MARKER in text:
                # Genuine zero-hit page — DDG's positive no-results block.
                return []
            logger.warning(
                "DDG 200 response has neither result markers nor the no-results "
                "marker (interstitial / parse failure)"
            )
            raise SearchBlockedError(
                "DuckDuckGo returned a page with no result markers and no "
                "no-results marker (interstitial / parse failure)"
            )

        results: list[SearchResult] = []
        for match in _DDG_RESULT_REGEX.finditer(text):
            href, title_html, snippet_html = match.groups()
            title = _HTML_TAG_REGEX.sub("", title_html).strip()
            snippet = _HTML_TAG_REGEX.sub("", snippet_html).strip()
            results.append(SearchResult(title=title, url=href, snippet=snippet))
            if len(results) >= max_results:
                break
        return results


# ---------------------------------------------------------------------------
# Keyed JSON backends (M16 F08 L02)
# ---------------------------------------------------------------------------
#
# Each owns a per-call ``async with httpx.AsyncClient(transport=
# SSRFGuardedTransport(extra_allowed_hosts=…))`` client. Required config
# missing -> ``SearchUnavailableError`` (actionable "configure X"). Genuine
# zero-hit -> ``[]``. Provider-specific block code (Brave 429) ->
# ``SearchBlockedError``. Other non-2xx -> ``SearchUnavailableError``. Secrets
# are NEVER logged — warnings carry the provider name + status only.


def _new_client(extra_allowed_hosts: tuple[str, ...]) -> httpx.AsyncClient:
    """Per-call SSRF-guarded async client shared by the keyed backends."""
    return httpx.AsyncClient(
        timeout=_CLIENT_TIMEOUT,
        transport=SSRFGuardedTransport(extra_allowed_hosts=list(extra_allowed_hosts)),
    )


class SearxngSearchBackend:
    """SearXNG meta-search backend.

    GET ``{base_url}/search?q=…&format=json``; maps ``results[]``
    ``{title, url, content}`` onto ``SearchResult``. Missing ``base_url`` ->
    ``SearchUnavailableError``. A non-JSON (HTML) 200 means the operator's
    instance does not have the JSON format enabled -> ``SearchUnavailableError``
    with an actionable message.
    """

    name: ClassVar[str] = "searxng"

    def __init__(
        self,
        *,
        base_url: str = "",
        extra_allowed_hosts: list[str] | tuple[str, ...] = (),
    ) -> None:
        self._base_url = (base_url or "").strip()
        self._extra_allowed_hosts = tuple(extra_allowed_hosts)

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not self._base_url:
            raise SearchUnavailableError(
                "SearXNG backend selected but no base URL configured; "
                "configure the SearXNG base URL"
            )
        url = self._base_url.rstrip("/") + "/search"
        params = {"q": query, "format": "json"}
        async with _new_client(self._extra_allowed_hosts) as client:
            resp = await client.get(url, params=params, follow_redirects=True)

        if resp.status_code != 200:
            logger.warning("SearXNG returned non-200 status %s", resp.status_code)
            raise SearchUnavailableError(f"SearXNG returned HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as e:
            raise SearchUnavailableError(
                "SearXNG returned a non-JSON response; enable JSON format in "
                "the SearXNG instance settings"
            ) from e

        items = payload.get("results") or []
        results: list[SearchResult] = []
        for item in items:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or "",
                    snippet=item.get("content", "") or "",
                )
            )
            if len(results) >= max_results:
                break
        return results


class GooglePSESearchBackend:
    """Google Programmable Search Engine (Custom Search JSON API) backend.

    GET ``https://www.googleapis.com/customsearch/v1?key=…&cx=…&q=…``; maps
    ``items[]`` ``{title, link, snippet}`` onto ``SearchResult``. Missing key
    OR cse id -> ``SearchUnavailableError``. A genuine zero-hit query returns
    200 with no ``items`` key -> ``[]``.
    """

    name: ClassVar[str] = "google_pse"

    def __init__(
        self,
        *,
        api_key: str = "",
        cse_id: str = "",
        extra_allowed_hosts: list[str] | tuple[str, ...] = (),
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._cse_id = (cse_id or "").strip()
        self._extra_allowed_hosts = tuple(extra_allowed_hosts)

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not self._api_key or not self._cse_id:
            raise SearchUnavailableError(
                "Google PSE backend selected but API key and/or CSE id not "
                "configured; configure the Google PSE API key and CSE id"
            )
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": self._api_key, "cx": self._cse_id, "q": query}
        async with _new_client(self._extra_allowed_hosts) as client:
            resp = await client.get(url, params=params, follow_redirects=True)

        if resp.status_code != 200:
            logger.warning("Google PSE returned non-200 status %s", resp.status_code)
            raise SearchUnavailableError(f"Google PSE returned HTTP {resp.status_code}")

        items = resp.json().get("items") or []
        results: list[SearchResult] = []
        for item in items:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("link", "") or "",
                    snippet=item.get("snippet", "") or "",
                )
            )
            if len(results) >= max_results:
                break
        return results


class BraveSearchBackend:
    """Brave Search API backend.

    GET ``https://api.search.brave.com/res/v1/web/search`` with headers
    ``X-Subscription-Token`` AND ``Accept: application/json`` (some endpoints
    4xx without the Accept header); maps ``web.results[]``
    ``{title, url, description}`` onto ``SearchResult``. Missing key ->
    ``SearchUnavailableError``. HTTP 429 (rate-limited) ->
    ``SearchBlockedError``; other non-2xx -> ``SearchUnavailableError``.
    """

    name: ClassVar[str] = "brave"

    def __init__(
        self,
        *,
        api_key: str = "",
        extra_allowed_hosts: list[str] | tuple[str, ...] = (),
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._extra_allowed_hosts = tuple(extra_allowed_hosts)

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not self._api_key:
            raise SearchUnavailableError(
                "Brave backend selected but no API key configured; configure the Brave API key"
            )
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "X-Subscription-Token": self._api_key,
            "Accept": "application/json",
        }
        params = {"q": query, "count": max_results}
        async with _new_client(self._extra_allowed_hosts) as client:
            resp = await client.get(url, params=params, headers=headers, follow_redirects=True)

        if resp.status_code == 429:
            logger.warning("Brave returned 429 (rate limited)")
            raise SearchBlockedError("Brave rate-limited the request (HTTP 429)")
        if resp.status_code != 200:
            logger.warning("Brave returned non-200 status %s", resp.status_code)
            raise SearchUnavailableError(f"Brave returned HTTP {resp.status_code}")

        web = resp.json().get("web") or {}
        items = web.get("results") or []
        results: list[SearchResult] = []
        for item in items:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or "",
                    snippet=item.get("description", "") or "",
                )
            )
            if len(results) >= max_results:
                break
        return results


class TavilySearchBackend:
    """Tavily Search API backend.

    POST ``https://api.tavily.com/search`` json ``{api_key, query,
    max_results}`` (in-body key form — still supported); maps ``results[]``
    ``{title, url, content}`` onto ``SearchResult``. Missing key ->
    ``SearchUnavailableError``. Non-2xx -> ``SearchUnavailableError``.
    """

    name: ClassVar[str] = "tavily"

    def __init__(
        self,
        *,
        api_key: str = "",
        extra_allowed_hosts: list[str] | tuple[str, ...] = (),
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._extra_allowed_hosts = tuple(extra_allowed_hosts)

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not self._api_key:
            raise SearchUnavailableError(
                "Tavily backend selected but no API key configured; configure the Tavily API key"
            )
        url = "https://api.tavily.com/search"
        body = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
        }
        async with _new_client(self._extra_allowed_hosts) as client:
            resp = await client.post(url, json=body, follow_redirects=True)

        if resp.status_code != 200:
            logger.warning("Tavily returned non-200 status %s", resp.status_code)
            raise SearchUnavailableError(f"Tavily returned HTTP {resp.status_code}")

        items = resp.json().get("results") or []
        results: list[SearchResult] = []
        for item in items:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or "",
                    snippet=item.get("content", "") or "",
                )
            )
            if len(results) >= max_results:
                break
        return results


# ---------------------------------------------------------------------------
# Registry + factory (M16 F08 L02 — DD3 refinement)
# ---------------------------------------------------------------------------

# Keyed by ``WebSearchConfig.search_backend`` enum value. The factory below
# constructs the matching backend from the config + the SSRF policy. DDG is
# the keyless default for unset / unknown names — but a SELECTED-but-
# unconfigured keyed engine still constructs and raises
# ``SearchUnavailableError`` at call time (NO silent DDG fallback — that hides
# misconfig).
SEARCH_BACKENDS: tuple[str, ...] = (
    "duckduckgo",
    "searxng",
    "google_pse",
    "brave",
    "tavily",
)


def build_search_backend(
    config: "WebSearchConfig",
    *,
    extra_allowed_hosts: list[str] | tuple[str, ...] = (),
) -> SearchBackend:
    """Construct the active ``SearchBackend`` from ``config.search_backend``.

    Each backend builds its own per-call SSRF-guarded client from
    ``extra_allowed_hosts`` (the operator's SSRF policy read off the resolved
    shared ``WebConfig`` at the wiring site). Default DDG when the engine name
    is unset / unknown. A selected-but-unconfigured keyed engine still
    constructs and raises ``SearchUnavailableError`` at call time.
    """
    hosts = tuple(extra_allowed_hosts)
    backend_name = getattr(config, "search_backend", None) or "duckduckgo"

    if backend_name == "searxng":
        return SearxngSearchBackend(
            base_url=config.searxng_base_url,
            extra_allowed_hosts=hosts,
        )
    if backend_name == "google_pse":
        return GooglePSESearchBackend(
            api_key=config.google_pse_api_key,
            cse_id=config.google_pse_cse_id,
            extra_allowed_hosts=hosts,
        )
    if backend_name == "brave":
        return BraveSearchBackend(
            api_key=config.brave_api_key,
            extra_allowed_hosts=hosts,
        )
    if backend_name == "tavily":
        return TavilySearchBackend(
            api_key=config.tavily_api_key,
            extra_allowed_hosts=hosts,
        )
    # "duckduckgo" + any unknown name -> keyless DDG default.
    return DDGSearchBackend(extra_allowed_hosts=hosts)
