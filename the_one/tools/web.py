from __future__ import annotations

import asyncio
from typing import Any

import httpx

from the_one.tools._search_backends import SearchBackend
from the_one.tools._web_config import (
    SSRFGuardedTransport,
    WebConfig,
    _is_binary_content_type,
    _truncate_response,
    _url_check,
)
from the_one.tools.base import ConstraintError, Tool
from the_one.tools.filesystem import CheckMode, FilesystemConfig, _filesystem_check


def _safe_unlink(target: Any) -> None:
    """Best-effort cleanup helper for ``DownloadFileTool``'s error paths.

    ``target.open("wb")`` creates the destination file BEFORE streaming
    begins, so any error firing inside the stream context (timeout,
    redirect-cap overrun, mid-stream RuntimeError) leaves an empty or
    partial file behind. Each error clause calls this helper to remove
    the file; ``target`` is ``None`` when ``_filesystem_check`` raised
    before returning, in which case this is a no-op.

    Swallows ``OSError`` so a cleanup failure cannot mask the original
    error the caller is formatting."""
    if target is None:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass


class HttpRequestTool(Tool):
    name = "http_request"
    description = (
        "Make an HTTP/HTTPS request and return the status + body. "
        "Default block of internal-network/loopback/cloud-metadata addresses "
        "(operator can broaden via extra_allowed_hosts). Host allowlist + "
        "denylist apply. Response is capped + tail-truncated when oversize. "
        "Timeout is clipped to operator-set max. Redirects follow up to the "
        "operator-set redirect_cap; 0 returns 3xx body verbatim."
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method.",
            },
            "url": {"type": "string", "description": "The URL to request."},
            "headers": {
                "type": "object",
                "description": "Optional headers.",
                "additionalProperties": {"type": "string"},
            },
            "body": {
                "type": "string",
                "description": "Request body (POST/PUT/PATCH).",
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Timeout in seconds. Uses the resolved default if omitted; "
                    "clipped to the operator-set max."
                ),
            },
        },
        "required": ["method", "url"],
    }

    Config = WebConfig

    def _build_transport(self, cfg: WebConfig) -> httpx.AsyncBaseTransport:
        """Tests monkeypatch this method to inject ``httpx.MockTransport``
        and bypass SSRF resolve+pin for tool-behavior coverage. The
        SSRF transport's own coverage lives in ``tests/test_web_helpers.py``."""
        return SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)

    async def execute(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> str:
        cfg: WebConfig = self._config  # type: ignore[assignment]
        # Float-preserving timeout clip (F4 L3 pattern).
        if timeout is None:
            clipped = cfg.timeout_seconds_default
        else:
            clipped = min(timeout, cfg.timeout_seconds_max)
            if clipped <= 0:
                clipped = 1
        try:
            _url_check(url, cfg)
            transport = self._build_transport(cfg)
            if cfg.redirect_cap == 0:
                follow = False
                max_redirs = 0
            else:
                follow = True
                max_redirs = cfg.redirect_cap
            # Merge agent-supplied headers over the operator's default UA;
            # explicit User-Agent in `headers` wins. `Substitute` marker on
            # `default_user_agent` means agents can replace via tool override.
            merged_headers = {"User-Agent": cfg.default_user_agent}
            if headers:
                merged_headers.update(headers)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=clipped,
                follow_redirects=follow,
                max_redirects=max_redirs,
            ) as client:
                resp = await client.request(method, url, headers=merged_headers, content=body)
                text, _ = _truncate_response(
                    resp.content,
                    cfg,
                    content_type=resp.headers.get("content-type"),
                )
                return f"[{resp.status_code}]\n{text}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except (asyncio.TimeoutError, httpx.TimeoutException):
            return f"[error] Request timed out after {clipped}s"
        except httpx.TooManyRedirects:
            return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"
        except Exception as e:
            return f"[error] {e}"


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = (
        "Fetch a URL and return its main content as markdown. For HTML "
        "pages, runs a readability extractor to strip navigation/ads/"
        "sidebars before converting to markdown — ideal for articles, "
        "blog posts, docs. For text/JSON responses, returns the raw "
        "decoded body. For binary content (PDF, images, archives), "
        "refuses with guidance to use download_file instead. Same SSRF "
        "+ URL allowlist + size cap + timeout cap as http_request."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch."},
        },
        "required": ["url"],
    }

    Config = WebConfig

    def _build_transport(self, cfg: WebConfig) -> httpx.AsyncBaseTransport:
        """Tests monkeypatch this method to inject ``httpx.MockTransport``
        and bypass SSRF resolve+pin for tool-behavior coverage. Mirrors
        ``HttpRequestTool._build_transport`` for test-seam consistency."""
        return SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)

    async def execute(self, url: str, **kwargs: Any) -> str:
        cfg: WebConfig = self._config  # type: ignore[assignment]
        # No agent-passed timeout — keep param surface tiny. Operators
        # who need an override can use http_request.
        clipped = cfg.timeout_seconds_default
        try:
            _url_check(url, cfg)
            transport = self._build_transport(cfg)
            if cfg.redirect_cap == 0:
                follow = False
                max_redirs = 0
            else:
                follow = True
                max_redirs = cfg.redirect_cap
            async with httpx.AsyncClient(
                transport=transport,
                timeout=clipped,
                follow_redirects=follow,
                max_redirects=max_redirs,
                headers={"User-Agent": cfg.default_user_agent},
            ) as client:
                resp = await client.get(url)
                ct = resp.headers.get("content-type", "")
                if _is_binary_content_type(ct):
                    bare = ct.split(";", 1)[0].strip()
                    return (
                        f"[error] binary content ({len(resp.content)} bytes; "
                        f"type={bare}) — use download_file for binary downloads"
                    )
                if "text/html" in ct.lower():
                    # Lazy imports — keep tool-class import time fast and
                    # let unit tests skip the heavy lxml import unless
                    # they exercise HTML extraction.
                    from markdownify import markdownify
                    from readability import Document

                    summary_html = Document(resp.text).summary()
                    markdown = markdownify(summary_html, heading_style="ATX")
                    text, _ = _truncate_response(markdown.encode("utf-8"), cfg, content_type=None)
                    return f"[{resp.status_code}]\n{text}"
                # Other text (text/plain, application/json, etc.) — pass
                # through ``_truncate_response`` directly.
                text, _ = _truncate_response(resp.content, cfg, content_type=ct)
                return f"[{resp.status_code}]\n{text}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except (asyncio.TimeoutError, httpx.TimeoutException):
            return f"[error] Fetch timed out after {clipped}s"
        except httpx.TooManyRedirects:
            return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"
        except Exception as e:
            return f"[error] {e}"


class DownloadFileTool(Tool):
    name = "download_file"
    description = (
        "Download a URL's content to a file. Path may be absolute or "
        "relative; relative paths resolve against the agent server's CWD. "
        "Refused if path is outside the operator-set path allowlist. "
        "Streams the response and aborts (removing the partial file) if "
        "the size cap is exceeded mid-stream. Same SSRF + URL allowlist + "
        "timeout cap as http_request. Use this for binary content (PDFs, "
        "images, archives); use fetch_url for HTML/text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to download."},
            "path": {
                "type": "string",
                "description": "Where to write the file. Refused if outside path allowlist.",
            },
        },
        "required": ["url", "path"],
    }

    Config = WebConfig
    Requires = (FilesystemConfig,)

    def _build_transport(self, cfg: WebConfig) -> httpx.AsyncBaseTransport:
        """Tests monkeypatch this method to inject ``httpx.MockTransport``
        and bypass SSRF resolve+pin for tool-behavior coverage. Mirrors
        ``HttpRequestTool._build_transport`` / ``FetchUrlTool._build_transport``
        for test-seam consistency."""
        return SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)

    async def execute(self, url: str, path: str, **kwargs: Any) -> str:
        cfg: WebConfig = self._config  # type: ignore[assignment]
        fs_cfg: FilesystemConfig = self._cross_configs[FilesystemConfig]
        # No agent-passed timeout — keep param surface tiny. Operators
        # who need an override can use http_request.
        clipped = cfg.timeout_seconds_default
        # ``target`` is referenced from the generic-exception cleanup path;
        # initialize to ``None`` so the cleanup is a no-op when the error
        # fires before ``_filesystem_check`` returns (e.g. ``_url_check``
        # refusal — caught by the ConstraintError clause first; defensive).
        target: Any = None
        try:
            _url_check(url, cfg)
            target = _filesystem_check(path, fs_cfg, mode=CheckMode.WRITE_EXISTING_PARENT)
            transport = self._build_transport(cfg)
            if cfg.redirect_cap == 0:
                follow = False
                max_redirs = 0
            else:
                follow = True
                max_redirs = cfg.redirect_cap

            total_bytes = 0
            cap = cfg.response_size_cap_bytes
            status: int | None = None

            # Inner try/except so a mid-stream cap overrun can clean up the
            # partial file BEFORE re-raising into the outer ConstraintError
            # clause (which formats and returns). Pattern (a) from the leg
            # implementation notes — re-raise after cleanup.
            try:
                with target.open("wb") as fh:
                    async with httpx.AsyncClient(
                        transport=transport,
                        timeout=clipped,
                        follow_redirects=follow,
                        max_redirects=max_redirs,
                        headers={"User-Agent": cfg.default_user_agent},
                    ) as client:
                        async with client.stream("GET", url) as resp:
                            status = resp.status_code
                            async for chunk in resp.aiter_bytes():
                                if total_bytes + len(chunk) > cap:
                                    raise ConstraintError(
                                        f"response exceeded {cap} bytes; partial file removed"
                                    )
                                fh.write(chunk)
                                total_bytes += len(chunk)
                return f"[{status}] downloaded {total_bytes} bytes to {target}"
            except ConstraintError:
                target.unlink(missing_ok=True)
                raise
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except (asyncio.TimeoutError, httpx.TimeoutException):
            # Opening ``target`` in 'wb' mode creates the file BEFORE the
            # stream starts; a redirect/timeout/connect error firing inside
            # ``client.stream(...)`` leaves an empty (or partial) file
            # behind. Clean it up so the agent doesn't see ghost zero-byte
            # downloads after a failed call.
            _safe_unlink(target)
            return f"[error] Download timed out after {clipped}s"
        except httpx.TooManyRedirects:
            _safe_unlink(target)
            return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"
        except Exception as e:
            # Defensive partial-file cleanup on unexpected errors. ``target``
            # is ``None`` if the error fired before ``_filesystem_check``
            # returned (e.g. ``_url_check`` raised ConstraintError, which
            # the earlier clause caught first); ``_safe_unlink`` handles
            # that case as a no-op.
            _safe_unlink(target)
            return f"[error] {e}"


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web and return results (title, URL, snippet). The "
        "backend is operator-configurable (default DuckDuckGo); F6 admin "
        "will surface the picker. Useful for finding URLs to feed into "
        "fetch_url or read."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {
                "type": "integer",
                "description": "Max results (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    Config = WebConfig
    # F5 L6: declares the cross-Config dependency on the SearchBackend
    # protocol — `BuiltinToolProvider.get_tools` injects the chosen
    # backend (F5: only `DDGSearchBackend`; F6: operator pick) into
    # `cross_configs[SearchBackend]`.
    Requires = (SearchBackend,)

    async def execute(self, query: str, max_results: int = 5, **kwargs: Any) -> str:
        try:
            # `_cross_configs[SearchBackend]` — Protocol-keyed service entry
            # injected by `BuiltinToolProvider.get_tools`. F5 L6 widens
            # `cross_configs` from `dict[type[BaseModel], BaseModel]` to
            # `dict[type, object]` to allow Protocol-keyed entries
            # alongside Pydantic-keyed Config entries.
            backend: SearchBackend = self._cross_configs[SearchBackend]  # type: ignore[assignment]
            results = await backend.search(query, max_results)
            if not results:
                return "No results found."
            return "\n\n".join(f"- {r.title}\n  {r.url}\n  {r.snippet}" for r in results)
        except ConstraintError as e:
            # Defensive — current `DDGSearchBackend` does not raise these,
            # but a future operator-policy-aware backend may.
            return f"[error] [constraint] {e}"
        except Exception as e:
            # Backend-side failures (network errors, httpx timeouts, parsing
            # errors) surface here. No dedicated timeout clause: the
            # backend owns its own client + timeout; if the timeout fires
            # it propagates as `httpx.TimeoutException`, which inherits
            # from `Exception` and lands here.
            return f"[error] {e}"
