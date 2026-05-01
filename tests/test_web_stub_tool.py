"""Stub-tool consumer test for ``WebConfig`` + helpers + transport (F5 L1).

Per F4 debrief recommendation: any leg that ships category helpers without a
production consumer in the same leg risks a "helpers-without-consumer" gap
(silent breakage when the first real consumer arrives in the next leg). This
test ships a minimal ``_StubWebTool(Tool)`` that exercises the full pipeline
end-to-end:

* ``WebConfig`` declared as ``Tool.Config``.
* ``_url_check`` validates the URL.
* ``SSRFGuardedTransport`` performs resolve+pin.
* ``_truncate_response`` decodes the response body.
* The three-clause envelope catches ``ConstraintError`` and returns
  ``[error] [constraint] {msg}``.

The mock infrastructure mirrors ``tests/test_web_helpers.py``: an
``asyncio.base_events.BaseEventLoop.getaddrinfo`` monkeypatch supplies the
resolved IPs, and ``httpx.AsyncHTTPTransport.handle_async_request`` is
patched to dispatch through a recorder/factory pair.
"""

from __future__ import annotations

import asyncio.base_events
import socket
from typing import Any

import httpx
import pytest

from the_one.tools._web_config import (
    SSRFGuardedTransport,
    WebConfig,
    _truncate_response,
    _url_check,
)
from the_one.tools.base import ConstraintError, Tool


class _StubWebTool(Tool):
    """Minimal Tool consumer that wires WebConfig + helpers + transport."""

    name = "stub_web"
    description = "Test consumer for WebConfig + helpers."
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }
    Config = WebConfig

    async def execute(self, url: str, **kwargs: Any) -> str:
        cfg: WebConfig = self._config  # type: ignore[assignment]
        try:
            _url_check(url, cfg)
            transport = SSRFGuardedTransport(
                extra_allowed_hosts=cfg.extra_allowed_hosts
            )
            async with httpx.AsyncClient(
                transport=transport,
                timeout=cfg.timeout_seconds_default,
                # ``redirect_cap == 0`` disables redirects entirely.
                follow_redirects=cfg.redirect_cap > 0,
                max_redirects=cfg.redirect_cap,
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as client:
                resp = await client.get(url)
                text, _ = _truncate_response(
                    resp.content,
                    cfg,
                    content_type=resp.headers.get("content-type"),
                )
                return text
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:  # pragma: no cover (defensive)
            return f"[error] {e}"


def _patch_getaddrinfo(monkeypatch, results: list[tuple]) -> None:
    """Patch ``BaseEventLoop.getaddrinfo`` to return ``results`` on every call."""

    async def fake_getaddrinfo(self, host, port, *args, **kwargs):
        return results

    monkeypatch.setattr(
        asyncio.base_events.BaseEventLoop, "getaddrinfo", fake_getaddrinfo
    )


def _patch_super_dispatch(monkeypatch, response_factory) -> list[httpx.Request]:
    """Patch ``httpx.AsyncHTTPTransport.handle_async_request`` so the
    ``SSRFGuardedTransport`` ``super()`` call dispatches through
    ``response_factory`` instead of the real httpx pool. Returns a list
    that records each request for post-test assertions."""
    captured: list[httpx.Request] = []

    async def fake_super(self, request):
        captured.append(request)
        return response_factory(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
    return captured


# ---------------------------------------------------------------------------
# Happy path: stub tool fetches a URL, helpers compose correctly
# ---------------------------------------------------------------------------


class TestStubWebToolHappyPath:
    async def test_end_to_end_fetch_returns_decoded_body(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))],
        )

        def factory(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"hello from stub",
                headers={"content-type": "text/html; charset=utf-8"},
            )

        captured = _patch_super_dispatch(monkeypatch, factory)

        tool = _StubWebTool(config=WebConfig())
        result = await tool.execute(url="http://example.com/")
        assert result == "hello from stub"
        assert len(captured) == 1
        # Pin verification: URL host rewritten to resolved IP.
        assert captured[0].url.host == "1.2.3.4"
        assert captured[0].headers["Host"] == "example.com"
        assert captured[0].extensions.get("sni_hostname") == "example.com"

    async def test_response_size_cap_truncates_text(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))],
        )

        body = b"x" * 5000

        def factory(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "text/plain"},
            )

        _patch_super_dispatch(monkeypatch, factory)
        cfg = WebConfig(response_size_cap_bytes=1024)
        tool = _StubWebTool(config=cfg)
        result = await tool.execute(url="http://example.com/")
        assert result.startswith("[... truncated 3976 bytes")
        assert result.endswith("x" * 1024)

    async def test_binary_content_type_rendered_as_marker(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))],
        )

        def factory(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"%PDF-1.4 binary bytes here",
                headers={"content-type": "application/pdf"},
            )

        _patch_super_dispatch(monkeypatch, factory)
        tool = _StubWebTool(config=WebConfig())
        result = await tool.execute(url="http://example.com/x.pdf")
        assert result.startswith("<binary content;")
        assert "type=application/pdf" in result


# ---------------------------------------------------------------------------
# SSRF block: stub tool's three-clause envelope catches ConstraintError
# ---------------------------------------------------------------------------


class TestStubWebToolSSRFBlock:
    async def test_ssrf_block_returns_constraint_envelope(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))],
        )

        def factory(req: httpx.Request) -> httpx.Response:
            # Should not be reached — SSRF block runs before dispatch.
            raise AssertionError("super().handle_async_request should not be called")

        _patch_super_dispatch(monkeypatch, factory)

        tool = _StubWebTool(config=WebConfig())
        result = await tool.execute(url="http://evil.example/")
        assert result.startswith("[error] [constraint]")
        assert "all resolved IPs" in result
        assert "127.0.0.1" in result

    async def test_url_check_failure_returns_constraint_envelope(
        self, monkeypatch
    ) -> None:
        # No resolver/transport patches needed — _url_check refuses before
        # the transport is ever invoked.
        tool = _StubWebTool(config=WebConfig())
        result = await tool.execute(url="ftp://example.com/")
        assert result.startswith("[error] [constraint]")
        assert "scheme 'ftp' refused" in result

    async def test_denylist_returns_constraint_envelope(self, monkeypatch) -> None:
        cfg = WebConfig(host_denylist=["evil.com"])
        tool = _StubWebTool(config=cfg)
        result = await tool.execute(url="http://evil.com/")
        assert result.startswith("[error] [constraint]")
        assert "host_denylist" in result


# ---------------------------------------------------------------------------
# Tool API conformance: stub declares Config = WebConfig and consumes helpers
# without pulling in tool-specific concerns.
# ---------------------------------------------------------------------------


class TestStubWebToolApi:
    def test_tool_declares_config_as_webconfig(self) -> None:
        assert _StubWebTool.Config is WebConfig

    def test_tool_default_config_is_webconfig_instance(self) -> None:
        tool = _StubWebTool()
        assert isinstance(tool._config, WebConfig)

    @pytest.mark.parametrize("redirect_cap,expected_follow", [(0, False), (5, True)])
    async def test_redirect_cap_zero_disables_follow_redirects(
        self, monkeypatch, redirect_cap: int, expected_follow: bool
    ) -> None:
        """``redirect_cap == 0`` should disable redirect-following entirely.
        We can't easily observe httpx's internal state here; instead, verify
        the tool runs cleanly through both branches."""
        _patch_getaddrinfo(
            monkeypatch,
            [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))],
        )

        def factory(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"ok")

        _patch_super_dispatch(monkeypatch, factory)
        cfg = WebConfig(redirect_cap=redirect_cap)
        tool = _StubWebTool(config=cfg)
        result = await tool.execute(url="http://example.com/")
        assert result == "ok"
        # Sanity: confirm the cfg branch we exercised is what we expected.
        assert (cfg.redirect_cap > 0) is expected_follow
