"""Direct unit tests for web tools after F5 L2 (HttpRequestTool migration).

These tests cover the F5 constraint surface for ``HttpRequestTool``:

* ``Config = WebConfig`` — the tool participates in the operator/agent
  resolver pipeline; construction takes a ``WebConfig`` instance.
* SSRF default-block via ``SSRFGuardedTransport`` (production path) — a
  separate test exercises the resolve+pin block; tool-behavior tests
  bypass SSRF via the ``_build_transport`` monkeypatch seam.
* ``_url_check`` integration — host_allowlist / host_denylist refusals
  surface as ``[error] [constraint] ...`` with the L1 wording.
* Float-preserving timeout clip (F4 L3 pattern) — clipped values used as
  the httpx client timeout; the grouped ``(asyncio.TimeoutError,
  httpx.TimeoutException)`` clause catches both production paths.
* ``redirect_cap`` semantic — 0 disables redirects (3xx body returned
  verbatim); >= 1 follows up to N (overrun → ``[error] [constraint]
  exceeded redirect cap of N``).
* Response-size cap — ``_truncate_response`` truncation marker surfaces
  on oversize responses.
* ``extra_allowed_hosts`` narrowing — agent-narrowed empty list lets
  SSRF block a host the operator originally allowed.

Mocking pattern:
  ``_patch_transport(monkeypatch, handler)`` replaces
  ``HttpRequestTool._build_transport`` to return ``httpx.MockTransport(handler)``.
  The handler signature is ``(httpx.Request) -> httpx.Response``; it can
  also raise (e.g. ``httpx.ReadTimeout``, ``httpx.ConnectError``) to
  exercise the timeout / generic-error paths.

  This replaces the pre-F5 ``_install_mock`` factory that popped
  ``transport=`` from the kwargs — incompatible with F5 because the new
  tool always builds its own transport.

F5 regression-net intent:
  These tests assert on the literal ``[200]\\n...`` and ``[error] ...`` formatted-string
  contracts. F6+ (e.g. fetch_url, download_file) MUST NOT change those formatted-string
  contracts without consciously updating these assertions; a silent contract change will
  fail these tests, which is the desired regression signal.

Tests written as ``async def`` per the project's ``asyncio_mode = "auto"`` config
(consistent with L1/L4/L5 anomaly resolution). No ``@pytest.mark.asyncio`` needed.
"""

from __future__ import annotations

import socket
from typing import Callable

import httpx

from the_one.tools._search_backends import DDGSearchBackend, SearchBackend, SearchResult
from the_one.tools._web_config import WebConfig
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.web import (
    DownloadFileTool,
    FetchUrlTool,
    HttpRequestTool,
    WebSearchTool,
)


def _patch_transport(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Replace ``HttpRequestTool._build_transport`` to inject a
    ``MockTransport`` carrying ``handler``. Bypasses SSRF for
    tool-behavior tests; the SSRFGuardedTransport's own coverage lives
    in ``tests/test_web_helpers.py``."""
    monkeypatch.setattr(
        HttpRequestTool,
        "_build_transport",
        lambda self, cfg: httpx.MockTransport(handler),
    )


class TestHttpRequestTool:
    async def test_happy_path_get(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            return httpx.Response(200, text="hello world")

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/"
        )
        assert result.startswith("[200]")
        assert "hello world" in result

    async def test_non_200_status(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/x"
        )
        assert result.startswith("[404]")
        assert "not found" in result

    async def test_headers_passed_through(self, monkeypatch) -> None:
        captured: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, text="ok")

        _patch_transport(monkeypatch, handler)
        await HttpRequestTool(WebConfig()).execute(
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

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="POST", url="https://example.test/", body="payload"
        )
        assert captured["body"] == b"payload"
        # Closes the formatter contract loop on the POST happy path too.
        assert "[200]" in result

    async def test_network_error_returns_error_string(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/"
        )
        assert result.startswith("[error]")
        assert "nope" in result


# ---------------------------------------------------------------------------
# F5 L2 — new constraint-surface tests
# ---------------------------------------------------------------------------


class TestHttpRequestToolConstraints:
    async def test_ssrf_block_loopback(self, monkeypatch) -> None:
        """When DNS resolves a hostname to a loopback IP, the SSRFGuardedTransport
        raises ``ConstraintError`` and the tool surfaces ``[error] [constraint]
        all resolved IPs ... blocked``. Exercises the production transport
        path (no ``_build_transport`` monkeypatch — only ``getaddrinfo``)."""
        import asyncio.base_events

        async def fake_getaddrinfo(self, host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))]

        monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)

        result = await HttpRequestTool(WebConfig()).execute(method="GET", url="http://example.com/")
        assert "[error] [constraint]" in result
        assert "all resolved IPs" in result

    async def test_redirect_cap_zero_returns_3xx_body(self, monkeypatch) -> None:
        """``redirect_cap=0`` → ``follow_redirects=False``; tool returns
        the 3xx response body verbatim with the 302 status header."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302,
                headers={"Location": "https://elsewhere.test/"},
                text="<redirect-body>",
            )

        _patch_transport(monkeypatch, handler)
        cfg = WebConfig(redirect_cap=0)
        result = await HttpRequestTool(cfg).execute(method="GET", url="https://example.test/")
        assert result.startswith("[302]")
        assert "<redirect-body>" in result

    async def test_redirect_cap_exceeded(self, monkeypatch) -> None:
        """``redirect_cap=1`` with a 302→302 chain → tool surfaces
        ``[error] [constraint] exceeded redirect cap of 1``."""

        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(
                302,
                headers={"Location": f"https://example.test/next-{call_count['n']}"},
                text=f"redirect-{call_count['n']}",
            )

        _patch_transport(monkeypatch, handler)
        cfg = WebConfig(redirect_cap=1)
        result = await HttpRequestTool(cfg).execute(method="GET", url="https://example.test/")
        assert result == "[error] [constraint] exceeded redirect cap of 1"

    async def test_response_size_cap_exceeded_aborts(self, monkeypatch) -> None:
        """F7 streaming behavior: when the response body exceeds
        ``response_size_cap_bytes``, ``_stream_read_with_cap`` raises
        ``ConstraintError`` mid-stream and the tool surfaces
        ``[error] [constraint] response exceeded N bytes``.

        Pre-F7 the full body was buffered first and then tail-truncated
        (hang risk on large/endless streams).  Now the cap fires during
        streaming iteration."""

        def handler(request: httpx.Request) -> httpx.Response:
            # 5KB body, far exceeds 1024 cap.
            return httpx.Response(200, content=b"x" * 5120)

        _patch_transport(monkeypatch, handler)
        cfg = WebConfig(response_size_cap_bytes=1024)
        result = await HttpRequestTool(cfg).execute(method="GET", url="https://example.test/")
        assert result.startswith("[error] [constraint]")
        assert "response exceeded 1024 bytes" in result

    async def test_url_allowlist_refuse(self, monkeypatch) -> None:
        """When ``host_allowlist`` is non-empty and the URL host is not in
        it, ``_url_check`` raises ``ConstraintError`` and the tool surfaces
        ``[error] [constraint] ... not in host_allowlist`` (per L1 wording)."""

        # No transport patch needed — _url_check refuses before transport.
        cfg = WebConfig(host_allowlist=["github.com"])
        result = await HttpRequestTool(cfg).execute(method="GET", url="http://other.com/")
        assert result.startswith("[error] [constraint]")
        assert "not in host_allowlist" in result

    async def test_url_denylist_refuse(self, monkeypatch) -> None:
        """When the URL host is in ``host_denylist``, the tool surfaces
        ``[error] [constraint] host '...' is in host_denylist``."""

        cfg = WebConfig(host_denylist=["evil.com"])
        result = await HttpRequestTool(cfg).execute(method="GET", url="http://evil.com/")
        assert result.startswith("[error] [constraint]")
        assert "host_denylist" in result

    async def test_timeout_clipped_to_max(self, monkeypatch) -> None:
        """Agent passes ``timeout=10`` with ``timeout_seconds_max=2`` →
        clipped to 2. Mock handler raises ``httpx.ReadTimeout`` (the actual
        production exception class, NOT ``asyncio.TimeoutError``) to
        exercise the grouped clause's ``httpx.TimeoutException`` branch.
        Tool surfaces ``[error] Request timed out after 2s``."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout")

        _patch_transport(monkeypatch, handler)
        cfg = WebConfig(timeout_seconds_default=2, timeout_seconds_max=2)
        result = await HttpRequestTool(cfg).execute(
            method="GET", url="https://example.test/", timeout=10
        )
        assert result == "[error] Request timed out after 2s"

    async def test_agent_narrow_extra_allowed_hosts(self, monkeypatch) -> None:
        """Operator allows ``localhost`` via ``extra_allowed_hosts``; agent
        narrows to ``[]``. The agent's tool instance must build a transport
        whose SSRF default-block applies to localhost (no host-match
        short-circuit). Asserts via the resulting SSRF block on the agent's
        invocation against ``http://localhost/``."""
        import asyncio.base_events

        async def fake_getaddrinfo(self, host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))]

        monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)

        # Operator config would have extra_allowed_hosts=["localhost"];
        # agent override narrowed to []. Tool sees the narrowed cfg.
        agent_cfg = WebConfig(extra_allowed_hosts=[])
        result = await HttpRequestTool(agent_cfg).execute(method="GET", url="http://localhost/")
        assert "[error] [constraint]" in result
        assert "all resolved IPs" in result


# ---------------------------------------------------------------------------
# F5 L3 — FetchUrlTool tests
# ---------------------------------------------------------------------------


def _patch_fetch_transport(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Replace ``FetchUrlTool._build_transport`` to inject a
    ``MockTransport`` carrying ``handler``. Mirrors the
    ``_patch_transport`` shape used for ``HttpRequestTool``."""
    monkeypatch.setattr(
        FetchUrlTool,
        "_build_transport",
        lambda self, cfg: httpx.MockTransport(handler),
    )


# Realistic article fixture — header + nav (multiple links) + <article>
# with <h1> and 3 substantive paragraphs (~50 words each) + footer.
# Readability's content-density scoring needs real content to fire; the
# trivial fixture (single short <p>) does NOT reliably trip the extractor.
_ARTICLE_HTML = """<!doctype html>
<html>
<head><title>Site Name</title></head>
<body>
<header>
  <nav>
    <a href="/home">Home</a>
    <a href="/about">About</a>
    <a href="/blog">Blog</a>
    <a href="/contact">Contact</a>
    <a href="/login">Login</a>
  </nav>
</header>
<article>
  <h1>The Title</h1>
  <p>Para 1: This is a substantive paragraph about a topic of considerable
  interest to the reader. The content here is long enough to register on
  readability's content-density scoring system, ensuring that the article
  body will be selected over the surrounding boilerplate sections such as
  navigation menus and site footer chrome elements that frame the page.</p>
  <p>Para 2: A second body paragraph extends the discussion with further
  detail and analysis. By providing multiple substantive paragraphs we
  ensure that the readability extractor has enough content density in
  the article element to reliably select it as the main content of the
  page, rather than falling back to other candidate sections.</p>
  <p>Para 3: A third paragraph rounds out the body content. With three
  full paragraphs of fifty words apiece, the article element decisively
  outweighs the navigation, header, and footer sections in the content
  scoring algorithm. This produces a stable extraction outcome across
  readability versions and is the recommended fixture shape.</p>
</article>
<footer>
  <p>Copyright 2026 Site Name. All rights reserved.</p>
</footer>
</body>
</html>
"""


class TestHttpRequestToolUserAgent:
    """Post-F5-debrief: verify the operator's `default_user_agent` flows
    through to the httpx request, and that an agent-supplied `User-Agent`
    in `headers` wins over the operator default."""

    async def test_default_user_agent_sent(self, monkeypatch) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["ua"] = request.headers.get("User-Agent")
            return httpx.Response(200, text="ok")

        _patch_transport(monkeypatch, handler)
        from the_one.tools._web_config import _DEFAULT_USER_AGENT

        await HttpRequestTool(WebConfig()).execute(method="GET", url="https://example.test/")
        assert captured["ua"] == _DEFAULT_USER_AGENT

    async def test_operator_override_sent(self, monkeypatch) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["ua"] = request.headers.get("User-Agent")
            return httpx.Response(200, text="ok")

        _patch_transport(monkeypatch, handler)
        cfg = WebConfig(default_user_agent="Mozilla/5.0 OperatorOverride")
        await HttpRequestTool(cfg).execute(method="GET", url="https://example.test/")
        assert captured["ua"] == "Mozilla/5.0 OperatorOverride"

    async def test_agent_per_call_header_wins(self, monkeypatch) -> None:
        """Agent passing `User-Agent` in `headers` overrides the operator
        default for that call only."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["ua"] = request.headers.get("User-Agent")
            return httpx.Response(200, text="ok")

        _patch_transport(monkeypatch, handler)
        await HttpRequestTool(WebConfig()).execute(
            method="GET",
            url="https://example.test/",
            headers={"User-Agent": "AgentPerCallUA/1.0"},
        )
        assert captured["ua"] == "AgentPerCallUA/1.0"


class TestFetchUrlTool:
    async def test_html_extraction(self, monkeypatch) -> None:
        """Realistic article fixture → readability extracts the article;
        markdownify converts to ATX-headed markdown. Assert: ATX heading
        substring (``# The Title``), distinctive body phrase (``Para 1``),
        and the ``[200]`` status prefix. Do NOT assert ``"nav" not in
        markdown`` — readability's stripping is content-density-based and
        may keep nav on smaller fixtures; the regression net is the
        article's presence, not the boilerplate's absence."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_ARTICLE_HTML.encode("utf-8"),
                headers={"content-type": "text/html; charset=utf-8"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        result = await FetchUrlTool(WebConfig()).execute(url="https://example.test/article")
        assert "[200]" in result
        assert "# The Title" in result
        assert "Para 1" in result

    async def test_text_plain_passthrough(self, monkeypatch) -> None:
        """``Content-Type: text/plain`` → body returned decoded via
        ``_truncate_response``; no readability/markdownify pipeline."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"hello plain text body",
                headers={"content-type": "text/plain"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        result = await FetchUrlTool(WebConfig()).execute(url="https://example.test/plain")
        assert result.startswith("[200]")
        assert "hello plain text body" in result

    async def test_json_passthrough(self, monkeypatch) -> None:
        """``Content-Type: application/json`` → body returned decoded
        verbatim. No pretty-printing (agents that want pretty JSON pipe
        through python_exec)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b'{"key": "value", "n": 42}',
                headers={"content-type": "application/json"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        result = await FetchUrlTool(WebConfig()).execute(url="https://example.test/api")
        assert result.startswith("[200]")
        assert '{"key": "value", "n": 42}' in result

    async def test_binary_refused(self, monkeypatch) -> None:
        """Binary content (``application/pdf``) → tool returns
        ``[error] binary content (N bytes; type=...) — use download_file
        for binary downloads``. NO ``[200]`` prefix — the ``[error] {...}``
        envelope shape is preserved (mirrors L2)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"x" * 50,
                headers={"content-type": "application/pdf"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        result = await FetchUrlTool(WebConfig()).execute(url="https://example.test/file.pdf")
        assert result == (
            "[error] binary content (50 bytes; type=application/pdf) "
            "— use download_file for binary downloads"
        )

    async def test_url_check_refused(self, monkeypatch) -> None:
        """Non-http/https scheme → ``_url_check`` raises
        ``ConstraintError``; tool surfaces ``[error] [constraint]
        scheme 'ftp' refused; ...``. Mock not invoked."""
        result = await FetchUrlTool(WebConfig()).execute(url="ftp://example.test/file")
        assert result.startswith("[error] [constraint]")
        assert "scheme 'ftp' refused" in result

    async def test_size_cap_truncates_large_html_head_preserving(self, monkeypatch) -> None:
        """F7 streaming behavior: ``response_size_cap_bytes=1024`` with a 6KB
        HTML body → ``_stream_read_head_capped`` reads the first 1024 bytes,
        readability extracts from that partial HTML, and the tool returns a
        ``[200]`` result (not an error).  The HTML fixture puts the article
        title in the first ~60 bytes so extraction still finds it.

        Pre-F7 the cap was applied AFTER readability extraction (tail-
        preserving truncation of the markdown); now it is applied to the
        raw HTML body BEFORE extraction (head-preserving, no ConstraintError).
        See ``test_large_html_head_preserve`` for a more rigorous assertion
        on a specific known substring from the document head."""
        big_paragraph = "lorem ipsum dolor sit amet " * 30  # ~800 chars
        big_html = (
            "<html><body><article><h1>Big Title</h1>"
            + "".join(f"<p>{big_paragraph}</p>" for _ in range(8))
            + "</article></body></html>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=big_html.encode("utf-8"),
                headers={"content-type": "text/html"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        cfg = WebConfig(response_size_cap_bytes=1024)
        result = await FetchUrlTool(cfg).execute(url="https://example.test/big")
        # Head-preserving cap: first 1024 bytes contain the article title.
        assert result.startswith("[200]")
        assert "Big Title" in result

    async def test_timeout_via_httpx_readtimeout(self, monkeypatch) -> None:
        """Mock raises ``httpx.ReadTimeout`` → tool surfaces F5-specific
        wording ``[error] Fetch timed out after Ns`` (distinct from L2's
        ``Request timed out`` wording)."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout")

        _patch_fetch_transport(monkeypatch, handler)
        cfg = WebConfig(timeout_seconds_default=2, timeout_seconds_max=2)
        result = await FetchUrlTool(cfg).execute(url="https://example.test/slow")
        assert result == "[error] Fetch timed out after 2s"

    def test_construction_shape(self) -> None:
        """``FetchUrlTool(WebConfig())`` builds; ``Config is WebConfig``."""
        t = FetchUrlTool(WebConfig())
        assert isinstance(t._config, WebConfig)
        assert FetchUrlTool.Config is WebConfig


# ---------------------------------------------------------------------------
# F7 L1 — Stream-and-cap tests (never-ending transport, media short-circuit,
#           large-HTML head-preserve)
# ---------------------------------------------------------------------------


class _InfiniteByteStream(httpx.AsyncByteStream):
    """Never-ending async byte iterator for ``httpx.Response(stream=...)``.

    Yields 1 KB chunks indefinitely.  Used by ``MockTransport`` handlers to
    simulate a continuous audio/video stream or a server that never closes the
    connection.  The ``aclose`` method is a no-op — MockTransport handles the
    lifecycle; ``async with client.stream(...)`` exits cleanly when the caller
    breaks out of ``aiter_bytes()`` (e.g. after a ``ConstraintError``).
    """

    async def __aiter__(self):
        while True:
            yield b"x" * 1024

    async def aclose(self) -> None:
        return None


class TestStreamCapAbort:
    """Never-ending transport proves both tools cap-abort (not hang)."""

    async def test_http_request_caps_on_endless_stream(self, monkeypatch) -> None:
        """``HttpRequestTool`` with a never-ending body and
        ``response_size_cap_bytes=4096`` → tool returns
        ``[error] [constraint] response exceeded 4096 bytes`` after
        consuming at most a few KB, without hanging."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "text/plain"},
            )

        _patch_transport(monkeypatch, handler)
        cfg = WebConfig(response_size_cap_bytes=4096)
        result = await HttpRequestTool(cfg).execute(method="GET", url="https://example.test/stream")
        assert result.startswith("[error] [constraint]")
        assert "response exceeded 4096 bytes" in result

    async def test_fetch_url_caps_on_endless_stream(self, monkeypatch) -> None:
        """``FetchUrlTool`` with a never-ending plain-text body and
        ``response_size_cap_bytes=4096`` → tool returns
        ``[error] [constraint] response exceeded 4096 bytes``."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "text/plain"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        cfg = WebConfig(response_size_cap_bytes=4096)
        result = await FetchUrlTool(cfg).execute(url="https://example.test/stream")
        assert result.startswith("[error] [constraint]")
        assert "response exceeded 4096 bytes" in result

    async def test_fetch_url_caps_on_endless_html_stream(self, monkeypatch) -> None:
        """``FetchUrlTool`` HTML path with a never-ending HTML body and
        ``response_size_cap_bytes=4096`` → tool reads at most 4096 bytes
        (head-preserving), then runs readability on the partial bytes and
        returns a ``[200]`` result rather than hanging.

        Unlike plain-text streaming, the HTML path uses
        ``_stream_read_head_capped`` which stops at cap and returns the
        accumulated bytes (no ConstraintError raised).  This lets readability
        extract whatever structure is in the head of the truncated document."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "text/html; charset=utf-8"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        cfg = WebConfig(response_size_cap_bytes=4096)
        result = await FetchUrlTool(cfg).execute(url="https://example.test/stream")
        # Does NOT hang — tool terminates at the byte cap.
        # The result may be sparse (raw binary as HTML) but must not be an
        # asyncio timeout or an infinite wait.
        assert "looks like a media stream" not in result
        assert "[200]" in result


class TestMediaShortCircuit:
    """Media content-type short-circuits both tools before body is consumed."""

    async def test_http_request_audio_short_circuit(self, monkeypatch) -> None:
        """``Content-Type: audio/aac`` → ``HttpRequestTool`` returns the
        media-stream error message without consuming the body."""

        def handler(request: httpx.Request) -> httpx.Response:
            # Body is a never-ending stream; the tool must not consume it.
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "audio/aac"},
            )

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/radio"
        )
        assert result == "[error] looks like a media stream (type=audio/aac), not fetchable as text"

    async def test_http_request_video_short_circuit(self, monkeypatch) -> None:
        """``Content-Type: video/mp4`` → short-circuit message."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "video/mp4"},
            )

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/clip"
        )
        assert result == "[error] looks like a media stream (type=video/mp4), not fetchable as text"

    async def test_http_request_octet_stream_short_circuit(self, monkeypatch) -> None:
        """``Content-Type: application/octet-stream`` → short-circuit message."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "application/octet-stream"},
            )

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/blob"
        )
        assert result == (
            "[error] looks like a media stream "
            "(type=application/octet-stream), not fetchable as text"
        )

    async def test_fetch_url_audio_short_circuit(self, monkeypatch) -> None:
        """``FetchUrlTool``: ``Content-Type: audio/mpeg`` → short-circuit."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=_InfiniteByteStream(),
                headers={"content-type": "audio/mpeg"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        result = await FetchUrlTool(WebConfig()).execute(url="https://example.test/radio")
        assert result == (
            "[error] looks like a media stream (type=audio/mpeg), not fetchable as text"
        )

    async def test_http_request_image_not_short_circuited(self, monkeypatch) -> None:
        """``Content-Type: image/png`` is NOT a media stream type — it goes
        through the normal binary tail-truncation path (``_is_binary_content_type``
        returns the ``<binary content; ...>`` message), not the media short-circuit.
        Regression guard: narrow predicate must NOT widen to image/*."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"\\x89PNG\\r\\n" + b"x" * 50,
                headers={"content-type": "image/png"},
            )

        _patch_transport(monkeypatch, handler)
        result = await HttpRequestTool(WebConfig()).execute(
            method="GET", url="https://example.test/image.png"
        )
        # Should NOT be the media-stream short-circuit message
        assert "looks like a media stream" not in result
        # Should be the binary tail-truncation path from _truncate_response
        assert "<binary content" in result


class TestLargeHtmlHeadPreserve:
    """Large HTML page: head-preserving cap + readability still extracts."""

    # A fixture with a large body that exceeds the small test cap when fully
    # read, but whose HEAD contains a known distinctive string.  We use a
    # cap large enough to include the article title (which is near the top)
    # and enough body text for readability to fire, but smaller than the full
    # document so we confirm head-preservation is what makes it work.
    _HEAD_MARKER = "DISTINCTIVE-ARTICLE-TITLE-MARKER"

    def _build_large_html(self) -> str:
        """Build an HTML document whose HEAD contains ``_HEAD_MARKER`` near
        the top, followed by a large body that would push the total well
        beyond any small cap."""
        filler_para = "word " * 80  # ~400 chars per paragraph
        paragraphs = "".join(
            f"<p>Para{i}: {filler_para}</p>" for i in range(30)
        )  # ~12 KB of paragraphs
        return (
            f"<!doctype html><html><head>"
            f"<title>{self._HEAD_MARKER}</title></head>"
            f"<body><article>"
            f"<h1>{self._HEAD_MARKER}</h1>" + paragraphs + "</article></body></html>"
        )

    async def test_large_html_extracts_head_content(self, monkeypatch) -> None:
        """A large HTML page (>8KB) with ``response_size_cap_bytes=8192``
        → the tool reads the first 8192 bytes (head-preserved), feeds them
        to readability, and the extracted markdown contains the known heading
        substring from the HEAD of the document."""
        large_html = self._build_large_html()
        # Document is ~12KB; cap at 8192 — head is preserved, article title
        # is in the first few hundred bytes, so extraction must succeed.
        assert len(large_html.encode("utf-8")) > 8192, "fixture must exceed cap"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=large_html.encode("utf-8"),
                headers={"content-type": "text/html; charset=utf-8"},
            )

        _patch_fetch_transport(monkeypatch, handler)
        cfg = WebConfig(response_size_cap_bytes=8192)
        result = await FetchUrlTool(cfg).execute(url="https://example.test/large-article")
        # With head-preservation the article title is in the capped bytes.
        assert "[200]" in result
        assert self._HEAD_MARKER in result


# ---------------------------------------------------------------------------
# F5 L4 — DownloadFileTool tests
# ---------------------------------------------------------------------------


def _patch_download_transport(
    monkeypatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Replace ``DownloadFileTool._build_transport`` to inject a
    ``MockTransport`` carrying ``handler``. Mirrors the
    ``_patch_transport`` shape used for ``HttpRequestTool`` /
    ``FetchUrlTool``."""
    monkeypatch.setattr(
        DownloadFileTool,
        "_build_transport",
        lambda self, cfg: httpx.MockTransport(handler),
    )


def _make_download_tool(
    web_cfg: WebConfig | None = None,
    fs_cfg: FilesystemConfig | None = None,
) -> DownloadFileTool:
    """Construct a ``DownloadFileTool`` with the cross-Config dispatch
    mapping wired so ``execute`` can read ``self._cross_configs[FilesystemConfig]``.
    Tests that need a non-default ``FilesystemConfig`` (e.g. a constrained
    ``path_allowlist``) supply it here."""
    return DownloadFileTool(
        web_cfg or WebConfig(),
        cross_configs={FilesystemConfig: fs_cfg or FilesystemConfig()},
    )


class TestDownloadFileTool:
    def test_construction_shape(self) -> None:
        """``DownloadFileTool`` builds; ``Config is WebConfig``;
        ``Requires == (FilesystemConfig,)``."""
        t = _make_download_tool()
        assert isinstance(t._config, WebConfig)
        assert DownloadFileTool.Config is WebConfig
        assert DownloadFileTool.Requires == (FilesystemConfig,)

    async def test_happy_path(self, monkeypatch, tmp_path) -> None:
        """In-scope path; mock returns 1KB body; tool writes file and
        returns ``[200] downloaded 1024 bytes to /path``. Verify file
        content."""
        body = b"x" * 1024

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        _patch_download_transport(monkeypatch, handler)
        target = tmp_path / "out.bin"
        tool = _make_download_tool(fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]))
        result = await tool.execute(url="https://example.test/file.bin", path=str(target))
        assert result == f"[200] downloaded 1024 bytes to {target}"
        assert target.read_bytes() == body

    async def test_path_outside_allowlist_refused(self, monkeypatch, tmp_path) -> None:
        """When ``path`` is outside the allowlist, the L0 ``_filesystem_check``
        raises ``ConstraintError``; tool surfaces ``[error] [constraint]
        path '...' outside allowlist`` and the file is not created."""

        def handler(request: httpx.Request) -> httpx.Response:
            # Should not be reached — _filesystem_check fires first.
            return httpx.Response(200, content=b"should not be written")

        _patch_download_transport(monkeypatch, handler)
        tool = _make_download_tool(fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]))
        # /etc/passwd resolves outside the tmp_path allowlist.
        result = await tool.execute(url="https://example.test/x", path="/etc/passwd")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_mid_stream_size_cap_aborts(self, monkeypatch, tmp_path) -> None:
        """``response_size_cap_bytes=1024``; mock returns 5KB; tool aborts
        mid-stream, unlinks the partial file, returns
        ``[error] [constraint] response exceeded 1024 bytes; partial file
        removed``. The partial file must not exist post-call."""
        # 5KB body — far exceeds the 1024 cap.
        body = b"y" * 5120

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        _patch_download_transport(monkeypatch, handler)
        target = tmp_path / "partial.bin"
        cfg = WebConfig(response_size_cap_bytes=1024)
        tool = _make_download_tool(
            web_cfg=cfg,
            fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]),
        )
        result = await tool.execute(url="https://example.test/big", path=str(target))
        assert result == ("[error] [constraint] response exceeded 1024 bytes; partial file removed")
        assert not target.exists()

    async def test_url_check_refused(self, monkeypatch, tmp_path) -> None:
        """Non-http/https scheme → ``_url_check`` raises ``ConstraintError``;
        tool surfaces ``[error] [constraint] scheme 'ftp' refused; ...``.
        No file created."""
        target = tmp_path / "shouldnotexist.bin"
        tool = _make_download_tool(fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]))
        result = await tool.execute(url="ftp://example.test/file", path=str(target))
        assert result.startswith("[error] [constraint]")
        assert "scheme 'ftp' refused" in result
        assert not target.exists()

    async def test_redirect_cap_exceeded(self, monkeypatch, tmp_path) -> None:
        """``redirect_cap=1`` with a 302→302 chain → tool surfaces
        ``[error] [constraint] exceeded redirect cap of 1``. No partial
        file on disk."""
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(
                302,
                headers={"Location": (f"https://example.test/next-{call_count['n']}")},
                text=f"redirect-{call_count['n']}",
            )

        _patch_download_transport(monkeypatch, handler)
        target = tmp_path / "redirect.bin"
        cfg = WebConfig(redirect_cap=1)
        tool = _make_download_tool(
            web_cfg=cfg,
            fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]),
        )
        result = await tool.execute(url="https://example.test/", path=str(target))
        assert result == "[error] [constraint] exceeded redirect cap of 1"
        assert not target.exists()

    async def test_timeout_via_httpx_readtimeout(self, monkeypatch, tmp_path) -> None:
        """Mock raises ``httpx.ReadTimeout`` → tool surfaces F5 wording
        ``[error] Download timed out after Ns`` (distinct from L2's
        ``Request timed out`` and L3's ``Fetch timed out``). No file
        (or partial file unlinked)."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout")

        _patch_download_transport(monkeypatch, handler)
        target = tmp_path / "slow.bin"
        cfg = WebConfig(timeout_seconds_default=2, timeout_seconds_max=2)
        tool = _make_download_tool(
            web_cfg=cfg,
            fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]),
        )
        result = await tool.execute(url="https://example.test/slow", path=str(target))
        assert result == "[error] Download timed out after 2s"
        assert not target.exists()

    async def test_relative_path_resolves_against_cwd(self, monkeypatch, tmp_path) -> None:
        """Relative ``path`` resolves against the process CWD. Use
        ``monkeypatch.chdir(tmp_path)`` to control CWD; agent passes
        ``path="file.bin"`` (parent is ``tmp_path``, which exists, so
        ``WRITE_EXISTING_PARENT`` passes). Verify the file lands at
        ``tmp_path / "file.bin"``."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"relative-path-content")

        _patch_download_transport(monkeypatch, handler)
        monkeypatch.chdir(tmp_path)
        tool = _make_download_tool(fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]))
        result = await tool.execute(url="https://example.test/x", path="file.bin")
        expected = tmp_path / "file.bin"
        assert "[200]" in result
        assert "downloaded 21 bytes" in result
        assert expected.exists()
        assert expected.read_bytes() == b"relative-path-content"

    async def test_partial_file_cleaned_on_unexpected_error(self, monkeypatch, tmp_path) -> None:
        """Simulate a generic ``RuntimeError`` from inside the
        ``aiter_bytes()`` loop. The tool's generic ``except Exception``
        clause must unlink the partial file; ``target.exists()`` is False
        after the call."""

        class _FailingByteStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                # Yield a chunk so the file gets created+partially-written
                # before the failure fires; this is the regression that
                # exercises the generic-exception cleanup path.
                yield b"first-chunk-"
                raise RuntimeError("boom mid-stream")

            async def aclose(self) -> None:  # pragma: no cover - trivial
                return None

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=_FailingByteStream())

        _patch_download_transport(monkeypatch, handler)
        target = tmp_path / "partial.bin"
        tool = _make_download_tool(fs_cfg=FilesystemConfig(path_allowlist=[str(tmp_path)]))
        result = await tool.execute(url="https://example.test/x", path=str(target))
        assert result.startswith("[error]")
        assert "boom mid-stream" in result
        assert not target.exists()


# ---------------------------------------------------------------------------
# F5 L6 — WebSearchTool tests (post-migration to SearchBackend injection)
# ---------------------------------------------------------------------------
#
# Pre-F5-L6 ``WebSearchTool`` POSTed to DDG directly via ``httpx.AsyncClient``;
# tests intercepted via ``_install_mock_websearch`` (replaced ``httpx.AsyncClient``
# with a ``MockTransport``-backed factory). Post-F5-L6 the tool consumes a
# ``SearchBackend`` instance via ``cross_configs[SearchBackend]`` — backend-level
# tests (``test_user_agent_sent``, parsing, anti-bot interstitial) live in
# ``tests/test_search_backends.py``; tool-level tests focus on the tool's
# format-and-error envelope around the backend's ``list[SearchResult]`` output.
#
# The ``_StubBackend`` fixture replaces ``_install_mock_websearch``: each test
# constructs ``WebSearchTool(WebConfig(), cross_configs={SearchBackend: stub})``
# with the stub configured for that test (canned results / captured args /
# raised exception).


class _StubBackend:
    """Test stub implementing the ``SearchBackend`` protocol shape.

    Each ``WebSearchTool`` test constructs a fresh ``_StubBackend`` configured
    with one of: canned ``results`` (list[SearchResult] returned verbatim),
    ``raise_exc`` (exception raised from ``search``), or ``capture_max``
    (a list mutated in-place with the ``max_results`` arg the tool forwarded).

    ``runtime_checkable`` Protocol checks attribute presence only — NOT call
    signatures — so this class doesn't need to inherit from ``SearchBackend``;
    declaring the ``name`` attribute and an ``async def search`` method is
    sufficient for the ``cross_configs[SearchBackend] = stub`` injection
    plumbing to find it.
    """

    name = "stub"

    def __init__(
        self,
        results: list[SearchResult] | None = None,
        raise_exc: BaseException | None = None,
        capture_max: list[int] | None = None,
    ) -> None:
        self._results = results or []
        self._raise_exc = raise_exc
        self._capture_max = capture_max

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if self._capture_max is not None:
            self._capture_max.append(max_results)
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._results


def _make_websearch_tool(stub: _StubBackend) -> WebSearchTool:
    """Construct a ``WebSearchTool`` with the cross-Config dispatch wired so
    ``execute`` can read ``self._cross_configs[SearchBackend]``."""
    return WebSearchTool(
        WebConfig(),
        cross_configs={SearchBackend: stub},
    )


class TestWebSearchTool:
    def test_construction_shape(self) -> None:
        """``WebSearchTool`` builds with a real ``DDGSearchBackend`` injected;
        ``Config is WebConfig``; ``Requires == (SearchBackend,)``;
        ``SearchBackend`` is in the cross_configs dict."""
        t = WebSearchTool(
            WebConfig(),
            cross_configs={SearchBackend: DDGSearchBackend()},
        )
        assert isinstance(t._config, WebConfig)
        assert WebSearchTool.Config is WebConfig
        assert WebSearchTool.Requires == (SearchBackend,)
        assert SearchBackend in t._cross_configs
        assert isinstance(t._cross_configs[SearchBackend], DDGSearchBackend)

    async def test_results_formatted_correctly(self) -> None:
        """Stub backend returns 3 ``SearchResult``s with known fields; tool
        returns the ``- title\\n  url\\n  snippet`` format with double-newline
        separation (preserves pre-F5 wording for agent compatibility)."""
        results = [
            SearchResult(title="Title A", url="https://a.example/", snippet="Snippet A"),
            SearchResult(title="Title B", url="https://b.example/", snippet="Snippet B"),
            SearchResult(title="Title C", url="https://c.example/", snippet="Snippet C"),
        ]
        stub = _StubBackend(results=results)
        result = await _make_websearch_tool(stub).execute(query="hi")
        expected = (
            "- Title A\n  https://a.example/\n  Snippet A\n\n"
            "- Title B\n  https://b.example/\n  Snippet B\n\n"
            "- Title C\n  https://c.example/\n  Snippet C"
        )
        assert result == expected

    async def test_no_results_message(self) -> None:
        """Stub backend returns ``[]``; tool returns the F1 wording
        ``"No results found."`` (preserved verbatim from pre-F5)."""
        stub = _StubBackend(results=[])
        result = await _make_websearch_tool(stub).execute(query="hi")
        assert result == "No results found."

    async def test_max_results_passed_to_backend(self) -> None:
        """Tool forwards the agent's ``max_results`` argument to the backend
        verbatim. Captures via the stub's ``capture_max`` list."""
        captured: list[int] = []
        stub = _StubBackend(results=[], capture_max=captured)
        await _make_websearch_tool(stub).execute(query="hi", max_results=3)
        assert captured == [3]

    async def test_max_results_default_passed_to_backend(self) -> None:
        """When the agent omits ``max_results``, the tool forwards the default
        (5) to the backend verbatim."""
        captured: list[int] = []
        stub = _StubBackend(results=[], capture_max=captured)
        await _make_websearch_tool(stub).execute(query="hi")
        assert captured == [5]

    async def test_backend_exception_caught(self) -> None:
        """Backend raises ``RuntimeError`` → tool's generic ``except Exception``
        clause surfaces ``[error] {msg}``. No timeout-specific clause: the
        backend owns its own client + timeout; if a timeout fires it
        propagates as ``httpx.TimeoutException`` (an ``Exception``) and
        lands in this same generic clause."""
        stub = _StubBackend(raise_exc=RuntimeError("backend boom"))
        result = await _make_websearch_tool(stub).execute(query="hi")
        assert result == "[error] backend boom"


class TestWebToolInstantiation:
    def test_http_request_tool_uses_web_config(self) -> None:
        # Post-F5-L2: HttpRequestTool's Config is WebConfig.
        t1 = HttpRequestTool()  # falls back to self.Config() = WebConfig()
        t2 = HttpRequestTool(WebConfig())
        assert isinstance(t1._config, WebConfig)
        assert isinstance(t2._config, WebConfig)
        assert HttpRequestTool.Config is WebConfig

    def test_web_search_tool_uses_web_config(self) -> None:
        # Post-F5-L6: WebSearchTool's Config migrated from _EmptyConfig to
        # WebConfig. Zero-arg fallback constructs an empty WebConfig() —
        # but the Tool will fail at execute time without a SearchBackend in
        # cross_configs. This test only asserts the construction-shape
        # post-migration; behavioral tests inject a stub backend.
        t1 = WebSearchTool()
        t2 = WebSearchTool(WebConfig())
        assert isinstance(t1._config, WebConfig)
        assert isinstance(t2._config, WebConfig)
        assert WebSearchTool.Config is WebConfig
        assert WebSearchTool.Requires == (SearchBackend,)
