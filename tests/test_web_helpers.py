"""Tests for ``the_one.tools._web_config`` helpers (F5 L1).

Covers:

* ``_is_ssrf_blocked`` — IPv4/IPv6 loopback, link-local, RFC1918,
  cloud-metadata, and public IPs.
* ``_url_check`` — scheme refusal, hostless URLs, allowlist, denylist.
* ``_is_binary_content_type`` — prefix and exact matchers, charset suffix.
* ``_truncate_response`` — under-cap, tail-preserving truncate, binary
  content-type, empty body.
* ``SSRFGuardedTransport`` — passes when first IP is public; raises
  ``ConstraintError`` when all resolved IPs are blocked; ``extra_allowed_hosts``
  short-circuits the resolve+pin path; **DNS-rebind regression** (resolve-then-pin
  invariant — second resolve to a private IP is blocked).
"""

from __future__ import annotations

import asyncio.base_events
import socket

import httpx
import pytest

from the_one.tools._web_config import (
    SSRFGuardedTransport,
    WebConfig,
    _host_matches,
    _is_binary_content_type,
    _is_ssrf_blocked,
    _truncate_response,
    _url_check,
)
from the_one.tools.base import ConstraintError

# ---------------------------------------------------------------------------
# _is_ssrf_blocked
# ---------------------------------------------------------------------------


class TestIsSSRFBlocked:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "127.0.0.255",
            "169.254.0.1",  # link-local
            "169.254.169.254",  # cloud metadata
            "10.0.0.1",  # RFC1918
            "10.255.255.255",
            "192.168.1.1",  # RFC1918
            "172.16.0.1",  # RFC1918
            "172.31.255.255",
            "::1",  # IPv6 loopback
            "fe80::1",  # IPv6 link-local
            "fc00::1",  # IPv6 unique-local (private)
        ],
    )
    def test_blocked(self, ip: str) -> None:
        assert _is_ssrf_blocked(ip) is True

    @pytest.mark.parametrize(
        "ip",
        [
            "1.1.1.1",
            "8.8.8.8",
            "151.101.1.69",
            "2606:4700:4700::1111",  # public IPv6 (Cloudflare)
        ],
    )
    def test_public_allowed(self, ip: str) -> None:
        assert _is_ssrf_blocked(ip) is False

    def test_invalid_ip_blocked_defensively(self) -> None:
        """Invalid input is treated as blocked — defensive default; callers
        that get here with non-IP strings have a bug."""
        assert _is_ssrf_blocked("not-an-ip") is True


# ---------------------------------------------------------------------------
# _url_check
# ---------------------------------------------------------------------------


class TestUrlCheck:
    def test_http_url_returns_unchanged(self) -> None:
        cfg = WebConfig()
        assert _url_check("http://example.com/foo", cfg) == "http://example.com/foo"

    def test_https_url_returns_unchanged(self) -> None:
        cfg = WebConfig()
        assert _url_check("https://example.com/", cfg) == "https://example.com/"

    def test_ftp_scheme_refused(self) -> None:
        cfg = WebConfig()
        with pytest.raises(ConstraintError) as exc:
            _url_check("ftp://example.com/", cfg)
        assert "scheme 'ftp' refused" in str(exc.value)

    def test_file_scheme_refused(self) -> None:
        cfg = WebConfig()
        with pytest.raises(ConstraintError) as exc:
            _url_check("file:///etc/passwd", cfg)
        assert "scheme 'file' refused" in str(exc.value)

    def test_data_scheme_refused(self) -> None:
        cfg = WebConfig()
        with pytest.raises(ConstraintError):
            _url_check("data:text/plain,hello", cfg)

    def test_url_without_host_refused(self) -> None:
        cfg = WebConfig()
        with pytest.raises(ConstraintError) as exc:
            _url_check("http:///foo", cfg)
        assert "missing host" in str(exc.value)

    def test_allowlist_match_passes(self) -> None:
        cfg = WebConfig(host_allowlist=["example.com"])
        assert _url_check("http://example.com/", cfg) == "http://example.com/"

    def test_allowlist_miss_refused(self) -> None:
        cfg = WebConfig(host_allowlist=["example.com"])
        with pytest.raises(ConstraintError) as exc:
            _url_check("http://other.com/", cfg)
        assert "host_allowlist" in str(exc.value)

    def test_denylist_match_refused(self) -> None:
        cfg = WebConfig(host_denylist=["evil.com"])
        with pytest.raises(ConstraintError) as exc:
            _url_check("http://evil.com/", cfg)
        assert "host_denylist" in str(exc.value)

    def test_empty_lists_no_constraint(self) -> None:
        cfg = WebConfig()
        assert _url_check("http://anywhere.com/", cfg) == "http://anywhere.com/"

    def test_denylist_overrides_allowlist(self) -> None:
        """Denylist runs AFTER allowlist; an entry in both lists is denied."""
        cfg = WebConfig(host_allowlist=["a.com", "evil.com"], host_denylist=["evil.com"])
        with pytest.raises(ConstraintError):
            _url_check("http://evil.com/", cfg)


# ---------------------------------------------------------------------------
# _host_matches
# ---------------------------------------------------------------------------


class TestHostMatches:
    def test_bare_host_matches(self) -> None:
        assert _host_matches("localhost", "localhost") is True

    def test_host_port_matches_on_host(self) -> None:
        assert _host_matches("localhost", "localhost:11434") is True

    def test_different_host_does_not_match(self) -> None:
        assert _host_matches("example.com", "localhost:11434") is False


# ---------------------------------------------------------------------------
# _is_binary_content_type
# ---------------------------------------------------------------------------


class TestIsBinaryContentType:
    @pytest.mark.parametrize(
        "ct",
        [
            "image/png",
            "image/jpeg",
            "audio/mpeg",
            "video/mp4",
            "application/x-tar",
            "application/x-executable",
            "application/octet-stream",
            "application/pdf",
            "application/zip",
            "application/gzip",
            "application/wasm",
        ],
    )
    def test_binary_types(self, ct: str) -> None:
        assert _is_binary_content_type(ct) is True

    @pytest.mark.parametrize(
        "ct",
        [
            "text/html",
            "text/plain",
            "application/json",
            "application/xml",
            "application/xhtml+xml",
        ],
    )
    def test_text_types(self, ct: str) -> None:
        assert _is_binary_content_type(ct) is False

    def test_none_is_text(self) -> None:
        assert _is_binary_content_type(None) is False

    def test_empty_is_text(self) -> None:
        assert _is_binary_content_type("") is False

    def test_charset_suffix_stripped(self) -> None:
        assert _is_binary_content_type("application/pdf; charset=binary") is True
        assert _is_binary_content_type("text/html; charset=utf-8") is False

    def test_case_insensitive(self) -> None:
        assert _is_binary_content_type("Image/PNG") is True


# ---------------------------------------------------------------------------
# _truncate_response
# ---------------------------------------------------------------------------


class TestTruncateResponse:
    def test_below_cap_returns_decoded(self) -> None:
        cfg = WebConfig()
        text, was_trunc = _truncate_response(b"hello world", cfg)
        assert text == "hello world"
        assert was_trunc is False

    def test_above_cap_tail_preserved(self) -> None:
        cfg = WebConfig(response_size_cap_bytes=1024)
        body = b"x" * 2048
        text, was_trunc = _truncate_response(body, cfg)
        assert was_trunc is True
        assert text.startswith("[... truncated 1024 bytes; showing last 1024 bytes")
        # Ensure the marker is followed by exactly the cap-many bytes.
        assert text.endswith("x" * 1024)

    def test_at_cap_not_truncated(self) -> None:
        cfg = WebConfig(response_size_cap_bytes=1024)
        body = b"x" * 1024
        text, was_trunc = _truncate_response(body, cfg)
        assert was_trunc is False
        assert text == "x" * 1024

    def test_binary_content_type_bypasses_cap(self) -> None:
        cfg = WebConfig(response_size_cap_bytes=1024)
        body = b"\x00\x01\x02" * 10  # tiny but binary
        text, was_trunc = _truncate_response(body, cfg, content_type="application/pdf")
        assert text == f"<binary content; {len(body)} bytes; type=application/pdf>"
        assert was_trunc is False

    def test_binary_large_body_no_truncation_marker(self) -> None:
        cfg = WebConfig(response_size_cap_bytes=1024)
        body = b"\x00" * 10_000
        text, was_trunc = _truncate_response(body, cfg, content_type="image/png")
        assert text.startswith("<binary content; 10000 bytes")
        assert was_trunc is False

    def test_empty_body_returns_empty_string_not_no_output(self) -> None:
        """Web-tool fallback: empty stays empty (NOT ``(no output)`` —
        that's the execution-tool helper's behavior)."""
        cfg = WebConfig()
        text, was_trunc = _truncate_response(b"", cfg)
        assert text == ""
        assert was_trunc is False

    def test_invalid_utf8_replaced_not_raised(self) -> None:
        cfg = WebConfig()
        body = b"hello \xff\xfe world"
        text, was_trunc = _truncate_response(body, cfg)
        # ``errors="replace"`` produces the U+FFFD replacement char, not raise.
        assert "hello " in text and " world" in text
        assert was_trunc is False


# ---------------------------------------------------------------------------
# SSRFGuardedTransport — fixture infrastructure
# ---------------------------------------------------------------------------


class _Recorder:
    """Captures requests dispatched through the parent transport's
    ``handle_async_request``."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.response_factory = lambda req: httpx.Response(200, content=b"ok")


def _patch_super_dispatch(monkeypatch, recorder: _Recorder) -> None:
    """Monkey-patch ``httpx.AsyncHTTPTransport.handle_async_request`` so the
    production ``SSRFGuardedTransport.handle_async_request`` (which calls
    ``super().handle_async_request``) lands here instead of in the real
    httpx connection pool.

    This is the cleanest seam: the production class is exercised verbatim.
    """

    async def fake_super(self, request):
        recorder.requests.append(request)
        return recorder.response_factory(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)


def _patch_getaddrinfo(monkeypatch, results_per_call: list[list[tuple]]) -> None:
    """Patch ``BaseEventLoop.getaddrinfo`` to return a different result list
    on each successive call.

    Patch target verified at architect level: ``asyncio.base_events.BaseEventLoop``
    overrides ``getaddrinfo`` and sits ahead of ``AbstractEventLoop`` in the
    running loop's MRO; patching ``AbstractEventLoop`` does NOT intercept.
    """
    counter = {"n": 0}

    async def fake_getaddrinfo(self, host, port, *args, **kwargs):
        idx = counter["n"]
        counter["n"] += 1
        # On overflow, return the last-defined result (simplifies single-call tests).
        chosen = results_per_call[min(idx, len(results_per_call) - 1)]
        return chosen

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)


# ---------------------------------------------------------------------------
# SSRFGuardedTransport — behavior tests
# ---------------------------------------------------------------------------


class TestSSRFGuardedTransport:
    async def test_resolves_to_public_ip_passes(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))]],
        )
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://example.com/path")
        assert resp.status_code == 200
        assert resp.content == b"ok"

        # Verify pin happened.
        assert len(recorder.requests) == 1
        captured = recorder.requests[0]
        assert captured.url.host == "1.2.3.4"
        assert captured.headers["Host"] == "example.com"
        assert captured.extensions.get("sni_hostname") == "example.com"

    async def test_all_resolved_blocked_raises_constraint_error(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [
                [
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80)),
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 80)),
                ]
            ],
        )
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            with pytest.raises(ConstraintError) as exc:
                await client.get("http://evil.example/")
        assert "all resolved IPs" in str(exc.value)
        assert "127.0.0.1" in str(exc.value)
        assert "10.0.0.1" in str(exc.value)
        assert recorder.requests == []  # nothing dispatched

    async def test_first_public_ip_wins_over_blocked(self, monkeypatch) -> None:
        _patch_getaddrinfo(
            monkeypatch,
            [
                [
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 80)),
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80)),
                ]
            ],
        )
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://example.com/")
        assert resp.status_code == 200
        captured = recorder.requests[0]
        # Iterates resolved list; first non-blocked wins.
        assert captured.url.host == "1.2.3.4"

    async def test_extra_allowed_hosts_short_circuits_resolve(self, monkeypatch) -> None:
        """If the host matches ``extra_allowed_hosts``, the resolve+pin path
        is skipped entirely — request reaches super with original host
        (no rewrite)."""
        # If resolution were attempted, this would return a private IP and
        # the request would be blocked. Short-circuit means resolution never
        # fires and the request passes unchanged.
        called = {"n": 0}

        async def should_not_be_called(self, host, port, *args, **kwargs):
            called["n"] += 1
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", port))]

        monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", should_not_be_called)
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport(extra_allowed_hosts=["localhost"])
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://localhost/foo")
        assert resp.status_code == 200
        assert called["n"] == 0
        captured = recorder.requests[0]
        # Host NOT rewritten to an IP — short-circuit preserved the original.
        assert captured.url.host == "localhost"

    async def test_extra_allowed_hosts_with_port_matches_on_host(self, monkeypatch) -> None:
        """``"localhost:11434"`` should match ``localhost`` regardless of
        the actual request port (F5 simplification)."""
        called = {"n": 0}

        async def should_not_be_called(self, host, port, *args, **kwargs):
            called["n"] += 1
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", port))]

        monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", should_not_be_called)
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport(extra_allowed_hosts=["localhost:11434"])
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://localhost:11434/api")
        assert resp.status_code == 200
        assert called["n"] == 0

    async def test_ip_literal_url_short_circuits_resolve(self, monkeypatch) -> None:
        """A URL whose host is already an IP needs no resolution."""
        called = {"n": 0}

        async def should_not_be_called(self, host, port, *args, **kwargs):
            called["n"] += 1
            return []

        monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", should_not_be_called)
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://1.2.3.4/")
        assert resp.status_code == 200
        assert called["n"] == 0

    async def test_ip_literal_loopback_blocked(self, monkeypatch) -> None:
        """**SSRF IP-literal regression** — agent fetches ``http://127.0.0.1/``;
        the transport raises ``ConstraintError`` BEFORE any connect attempt.
        Pre-fix bug: the IP-literal short-circuit fell through to super
        unconditionally, so loopback IPs reached the connect layer and
        surfaced as httpx network errors instead of SSRF policy refusals."""
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            with pytest.raises(ConstraintError) as exc:
                await client.get("http://127.0.0.1/")
        assert "127.0.0.1" in str(exc.value)
        assert "SSRF block list" in str(exc.value)
        assert recorder.requests == []  # nothing dispatched

    async def test_ip_literal_rfc1918_blocked(self, monkeypatch) -> None:
        """RFC1918 IP literal (``http://10.0.0.1/``) is refused before connect."""
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            with pytest.raises(ConstraintError) as exc:
                await client.get("http://10.0.0.1/")
        assert "10.0.0.1" in str(exc.value)
        assert "SSRF block list" in str(exc.value)
        assert recorder.requests == []

    async def test_ip_literal_cloud_metadata_blocked(self, monkeypatch) -> None:
        """Cloud-metadata IP literal (``http://169.254.169.254/``) — the
        canonical AWS/GCP/Azure SSRF target — is refused before connect.
        F5 mission constraint: SSRF protection refuses cloud-metadata
        addresses by default."""
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            with pytest.raises(ConstraintError) as exc:
                await client.get("http://169.254.169.254/latest/meta-data/")
        assert "169.254.169.254" in str(exc.value)
        assert "SSRF block list" in str(exc.value)
        assert recorder.requests == []

    async def test_ip_literal_public_passes(self, monkeypatch) -> None:
        """Public IP literal (``http://1.2.3.4/``) is allowed — only
        loopback / RFC1918 / link-local / cloud-metadata are blocked.
        Mirrors the existing ``test_ip_literal_url_short_circuits_resolve``
        but explicitly asserts the SSRF check fired and returned False."""
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://1.2.3.4/")
        assert resp.status_code == 200
        assert len(recorder.requests) == 1
        # Host NOT rewritten (no resolve happened — IP literal).
        assert recorder.requests[0].url.host == "1.2.3.4"

    async def test_ip_literal_extra_allowed_hosts_override(self, monkeypatch) -> None:
        """Operator override: with ``extra_allowed_hosts=["127.0.0.1"]``,
        the IP literal ``http://127.0.0.1/`` passes — the operator
        explicitly opted into the loopback target. This preserves the
        ``extra_allowed_hosts``-as-only-opt-out semantic uniformly across
        hostname and IP-literal paths."""
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport(extra_allowed_hosts=["127.0.0.1"])
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            resp = await client.get("http://127.0.0.1/")
        assert resp.status_code == 200
        assert len(recorder.requests) == 1
        assert recorder.requests[0].url.host == "127.0.0.1"

    async def test_dns_rebind_blocked_on_second_resolve(self, monkeypatch) -> None:
        """**DNS-rebind regression test** — the resolve-then-pin invariant:
        first resolve returns a public IP; the request succeeds. Second
        resolve (rebind attack) returns a loopback IP; the request is blocked.

        Patch target: ``asyncio.base_events.BaseEventLoop.getaddrinfo``.
        Pool config: ``max_keepalive_connections=0`` so the second request
        actually triggers a fresh connect (and therefore a fresh resolve)
        instead of reusing the request-1 connection.
        """
        _patch_getaddrinfo(
            monkeypatch,
            [
                [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 80))],
                [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))],
            ],
        )
        recorder = _Recorder()
        _patch_super_dispatch(monkeypatch, recorder)

        transport = SSRFGuardedTransport()
        async with httpx.AsyncClient(
            transport=transport,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as client:
            # First request: public IP — succeeds.
            resp1 = await client.get("http://target.example/")
            assert resp1.status_code == 200

            # Second request: rebound to loopback — must be blocked.
            with pytest.raises(ConstraintError) as exc:
                await client.get("http://target.example/")
        assert "all resolved IPs" in str(exc.value)
        assert "127.0.0.1" in str(exc.value)
        # Only the FIRST request should have reached super; the second
        # was rejected before dispatch.
        assert len(recorder.requests) == 1


# ---------------------------------------------------------------------------
# Sanity: production SSRFGuardedTransport instantiates without args
# ---------------------------------------------------------------------------


class TestSSRFGuardedTransportConstruction:
    def test_default_construction(self) -> None:
        t = SSRFGuardedTransport()
        assert t._extra_allowed == ()

    def test_extra_allowed_hosts_materialized_as_tuple(self) -> None:
        src = ["a.com", "b.com"]
        t = SSRFGuardedTransport(extra_allowed_hosts=src)
        assert t._extra_allowed == ("a.com", "b.com")
        # Mutating the source list does not affect the transport's view.
        src.append("c.com")
        assert t._extra_allowed == ("a.com", "b.com")
