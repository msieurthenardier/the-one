"""Web-tool category Config + helpers + SSRF transport (F5 L1).

Defines the per-category Pydantic ``WebConfig`` shared by all web tools
(``HttpRequestTool``, ``fetch_url``, ``download_file``, ``WebSearchTool``
landing in later legs of F5) plus the policy helpers and the custom
SSRF-guarded httpx transport.

References:

* **F5 Decision 1** — DNS-rebind defense via resolve-then-pin in a custom
  ``httpx.AsyncHTTPTransport`` subclass.
* **F5 Decision 2** — SSRF protection is on by default; ``extra_allowed_hosts``
  is the only opt-out (host-match short-circuit BEFORE resolution). There is
  NO full-disable toggle — the mission constraint is locked at the schema
  level by the absence of any ``disable_ssrf`` / ``ssrf_disabled`` /
  ``disable_ssrf_protection`` field.
* **F5 Decision 6** — Custom transport sets ``request.extensions["sni_hostname"]``
  to preserve TLS certificate validation against the original hostname after
  rewriting the URL host to the resolved IP.
* **F5 Decision 7** — ``extra_allowed_hosts`` carries the ``Narrow`` marker
  (agent ⊆ operator); ``host_allowlist`` is also ``Narrow`` (agent ⊆ operator);
  ``host_denylist`` is ``NarrowSuperset`` (agent ⊇ operator — agent may add
  but not remove operator-declared denials).
* **F5 Decision 9** — ``redirect_cap`` is Field-only (no marker). Agent
  overrides on this key raise ``ValueError("... no Narrow/Substitute marker ...")``
  at resolver time; the cap is operator-only.
* **F5 Decision 10** — ``_truncate_response`` mirrors F4's ``_truncate_output``
  pattern but for single-stream HTTP responses (no stdout/stderr split).
* **F5 Decision 11** — DNS-rebind regression test uses a monkeypatched
  ``asyncio.base_events.BaseEventLoop.getaddrinfo`` (NOT
  ``AbstractEventLoop`` — MRO does not intercept) with a per-test
  ``httpx.Limits(max_keepalive_connections=0)`` to force per-request
  resolution. See ``tests/test_web_helpers.py``.

This leg is pure scaffolding: no tool wiring. L2 migrates ``HttpRequestTool``;
L3 introduces ``fetch_url``; L4 introduces ``download_file``;
L5 + L6 cover the search backends.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Annotated
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from the_one.tools.base import ConstraintError
from the_one.tools.execution import _TIMEOUT_DEFAULT_UI_CHOICES
from the_one.tools.resolver import Narrow, NarrowSuperset, Substitute

# ---------------------------------------------------------------------------
# Module-level constants (NOT operator-configurable)
# ---------------------------------------------------------------------------

# Cloud-provider instance-metadata IPs — defensively blocked regardless of
# whether they would already be caught by ``is_link_local`` (the IPv4 entry
# IS link-local, but enumerating it explicitly makes the intent grep-able and
# survives a future libc tweak that re-classifies the range).
_BLOCKED_CLOUD_METADATA_IPS: tuple[str, ...] = (
    # AWS / GCP / OpenStack / Azure (all use 169.254.169.254 over IPv4)
    "169.254.169.254",
    # Azure also exposes an IPv6 metadata endpoint
    "fd00:ec2::254",
)

# Default User-Agent header for tool-originated HTTP requests. Tools may
# override per-call; this is the header surfaced when no other UA is set.
_DEFAULT_USER_AGENT: str = "the-one/0.2 (https://github.com/msieurthenardier/the-one)"

# Six dropdown choices mirroring F3's ``read_size_cap_bytes`` UI shape so
# operators see consistent cap labels across filesystem and web caps.
_RESPONSE_SIZE_UI_CHOICES: list[dict[str, object]] = [
    {"value": 51_200, "label": "50KB — very small models"},
    {"value": 102_400, "label": "100KB — small/7B-class friendly"},
    {"value": 262_144, "label": "256KB — most models comfortable"},
    {"value": 524_288, "label": "512KB — middle"},
    {"value": 1_048_576, "label": "1MB — default (Opus 200K headroom)"},
    {"value": 5_242_880, "label": "5MB — Opus 1M only"},
]

# Binary content-type prefixes (startswith match) and exact-match values
# consulted by ``_is_binary_content_type``. Kept module-level so test code
# can introspect / extend without re-implementing the matcher.
_BINARY_CONTENT_TYPE_PREFIXES: tuple[str, ...] = (
    "image/",
    "audio/",
    "video/",
    "application/x-",
)
_BINARY_CONTENT_TYPE_EXACT: frozenset[str] = frozenset(
    {
        "application/octet-stream",
        "application/pdf",
        "application/zip",
        "application/gzip",
        "application/wasm",
    }
)


# ---------------------------------------------------------------------------
# WebConfig — per-category Pydantic Config
# ---------------------------------------------------------------------------


class WebConfig(BaseModel):
    """Per-category Config for all web tools (F5 Decisions 2, 7, 9, 10).

    Seven constraint fields:

    * ``timeout_seconds_default`` (Narrow int) — used when agent omits timeout.
    * ``timeout_seconds_max`` (Narrow int) — hard ceiling; agent value clipped.
    * ``response_size_cap_bytes`` (Narrow int) — single-stream response cap.
    * ``redirect_cap`` (Field-only — NO marker) — operator-only HTTP-redirect
      cap. Agent overrides on this key raise ``ValueError`` at resolver time
      per F5 Decision 9. Tools call ``follow_redirects=cap > 0,
      max_redirects=cap`` so a value of ``0`` disables redirects entirely.
    * ``host_allowlist`` (Narrow list[str]) — when non-empty, ONLY hosts in
      this list are permitted. Empty = no allowlist constraint (only SSRF
      and denylist apply).
    * ``host_denylist`` (NarrowSuperset list[str]) — agent must contain
      every operator-declared entry; agent may add more.
    * ``extra_allowed_hosts`` (Narrow list[str]) — operator-declared hosts
      whose resolved IPs are exempt from the SSRF default-block list. Each
      entry is ``"hostname"`` or ``"hostname:port"`` (the F5 simplification
      matches on host only — port distinction deferred to F6+). Common
      example: ``"localhost:11434"`` to permit Ollama. The SSRF protection
      itself is NOT disable-able; this list is the only opt-out.

    Plus a ``model_validator(mode="after")`` cross-field invariant
    enforcing ``timeout_seconds_default <= timeout_seconds_max``
    (mirrors F4 D1).

    Frozen so ``cross_configs`` shared by reference cannot be mutated by one
    tool to corrupt a peer's view (mirrors ``ExecutionConfig`` and
    ``FilesystemConfig`` posture).

    **Mission invariant lock**: ``WebConfig`` deliberately has NO
    ``disable_ssrf`` / ``ssrf_disabled`` / ``disable_ssrf_protection``
    field. ``tests/test_web_config.py`` asserts this at the
    ``model_fields`` level so a future PR cannot silently introduce a
    full-disable toggle.
    """

    model_config = ConfigDict(frozen=True)

    timeout_seconds_default: Annotated[
        int,
        Narrow,
        Field(
            ge=1,
            le=3600,
            description="Used when agent omits timeout.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": _TIMEOUT_DEFAULT_UI_CHOICES,
            },
        ),
    ] = 30

    timeout_seconds_max: Annotated[
        int,
        Narrow,
        Field(
            ge=1,
            le=3600,
            description="Hard ceiling; agent value clipped.",
        ),
    ] = 120

    response_size_cap_bytes: Annotated[
        int,
        Narrow,
        Field(
            ge=1024,
            le=104_857_600,  # 100 MB hard ceiling, matches output_cap_bytes
            description="Per-response cap; tail-preserving truncation.",
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": _RESPONSE_SIZE_UI_CHOICES,
            },
        ),
    ] = 1_048_576  # 1 MB default

    # M16 F08 L01 (HIGH-1, DD1): the per-tool LLM-facing web text cap (the M16 F07
    # follow-up) is RETIRED — the central context-budget governor in
    # ``Agent._execute_tool`` now bounds every tool result uniformly (head-preserving
    # for web text). ``response_size_cap_bytes`` (the 1 MB streaming hard-abort)
    # remains as the transport/OOM safety cap. Removing that field drops
    # ``WebConfig.model_fields`` from 9 → 8 (see ``tests/test_web_config.py``).

    # F5 Decision 9: ``redirect_cap`` is Field-only — agents cannot narrow it.
    # Resolver raises ``ValueError("... no Narrow/Substitute marker ...")`` if
    # an agent override touches this key. Tests pin the rejection at the
    # resolver level (NOT at AgentFactory.create).
    redirect_cap: int = Field(
        5,
        ge=0,
        le=20,
        description=(
            "Maximum HTTP redirects per request. Tool-level only — agents "
            "cannot narrow this. Set to 0 to disable redirects entirely."
        ),
    )

    host_allowlist: Annotated[
        list[str],
        Narrow,
        Field(
            default_factory=list,
            description=(
                "If non-empty, ONLY hosts in this list are allowed. "
                "Empty = no allowlist constraint."
            ),
        ),
    ]

    host_denylist: Annotated[
        list[str],
        NarrowSuperset,
        Field(
            default_factory=list,
            description=(
                "Hosts in this list are always refused, regardless of "
                "allowlist. Agent must contain every operator entry; "
                "agent may add more."
            ),
        ),
    ]

    extra_allowed_hosts: Annotated[
        list[str],
        Narrow,
        Field(
            default_factory=list,
            description=(
                "Hosts whose resolved IPs are exempt from the SSRF "
                "default-block list. Each entry: 'hostname' or "
                "'hostname:port'. Common: 'localhost:11434' (Ollama). "
                "The SSRF protection itself is not disable-able; this "
                "list is the only opt-out."
            ),
        ),
    ]

    default_user_agent: Annotated[
        str,
        Substitute,
        Field(
            default=_DEFAULT_USER_AGENT,
            description=(
                "User-Agent header sent on every web-tool request unless "
                "the agent passes an explicit `User-Agent` in `headers`. "
                "Substitute marker: agents can replace this with their own "
                "identity (no narrowing semantic — UA strings aren't "
                "ordered). Operator-set baseline identifies the-one to "
                "remote servers; some sites (e.g. Wikipedia) reject this "
                "default and require a browser-class UA — set per-agent "
                "or override the operator default to work around."
            ),
        ),
    ]

    @model_validator(mode="after")
    def _default_le_max(self) -> "WebConfig":
        """Enforce the cross-field invariant ``default <= max`` (mirrors
        ``ExecutionConfig._default_le_max`` from F4 Decision 1).

        Runs at ``schema.model_validate(merged)`` time — i.e. AFTER the
        resolver's per-key narrowing dispatch. This guarantees that an
        agent cannot widen ``default`` past a narrowed ``max``: if
        narrowing leaves ``max < default``, this validator raises.
        """
        if self.timeout_seconds_default > self.timeout_seconds_max:
            raise ValueError(
                f"timeout_seconds_default ({self.timeout_seconds_default}s) "
                f"must be <= timeout_seconds_max ({self.timeout_seconds_max}s)"
            )
        return self


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_ssrf_blocked(ip: str) -> bool:
    """Return True if ``ip`` is in the SSRF default-block set.

    Blocks: loopback (``127.0.0.0/8``, ``::1``), link-local
    (``169.254.0.0/16``, ``fe80::/10``), private RFC1918
    (``10/8`` / ``172.16/12`` / ``192.168/16``), and the cloud-metadata IPs
    enumerated in ``_BLOCKED_CLOUD_METADATA_IPS``.

    **Does NOT consult ``extra_allowed_hosts``.** The operator's allowlist
    short-circuit happens at the transport level on the original *hostname*
    (BEFORE resolution), not on the resolved IP. By the time this helper
    is called, ``SSRFGuardedTransport`` has already decided the host is
    not in the operator's allowlist and proceeded to resolve.

    Invalid IP literals (``ipaddress.ip_address`` raises ``ValueError``)
    are treated as blocked — defensive default; callers that get here with
    non-IP strings have a bug.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if addr.is_loopback or addr.is_link_local or addr.is_private:
        return True
    if ip in _BLOCKED_CLOUD_METADATA_IPS:
        return True
    return False


def _url_check(url: str, cfg: WebConfig) -> str:
    """Check ``url`` against scheme + allowlist + denylist policies.

    Refuses (raises ``ConstraintError``):

    * Non-http/https schemes (``ftp://``, ``file://``, ``data:``, ...).
    * URLs without a host (e.g. ``http:///foo``).
    * If ``cfg.host_allowlist`` is non-empty: hosts not in the allowlist.
    * If host is in ``cfg.host_denylist``.

    Returns the URL unchanged on success. SSRF (resolved-IP filtering) is
    handled separately at the transport layer.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ConstraintError(f"scheme '{scheme}' refused; http/https only")
    host = parsed.hostname
    if not host:
        raise ConstraintError(f"URL missing host: {url!r}")
    if cfg.host_allowlist and host not in cfg.host_allowlist:
        raise ConstraintError(f"host '{host}' not in host_allowlist {cfg.host_allowlist}")
    if host in cfg.host_denylist:
        raise ConstraintError(f"host '{host}' is in host_denylist")
    return url


def _is_binary_content_type(ct: str | None) -> bool:
    """Return True if ``ct`` is a binary content-type.

    Prefix matches: ``image/``, ``audio/``, ``video/``, ``application/x-``.
    Exact matches: ``application/octet-stream``, ``application/pdf``,
    ``application/zip``, ``application/gzip``, ``application/wasm``.

    ``None`` or empty → ``False`` (treat as text — let downstream decode try).

    The match operates on the bare media-type — any ``;`` suffix
    (``; charset=utf-8``) is stripped before comparison so
    ``application/pdf; charset=binary`` is still classified as binary.
    """
    if not ct:
        return False
    bare = ct.split(";", 1)[0].strip().lower()
    if not bare:
        return False
    for prefix in _BINARY_CONTENT_TYPE_PREFIXES:
        if bare.startswith(prefix):
            return True
    return bare in _BINARY_CONTENT_TYPE_EXACT


def _truncate_response(
    body: bytes,
    cfg: WebConfig,
    *,
    content_type: str | None = None,
) -> tuple[str, bool]:
    """Tail-preserve ``body`` to ``cfg.response_size_cap_bytes`` (mirrors
    F4's ``_truncate_output`` for single-stream responses).

    Returns ``(text, was_truncated)``.

    Behavior:

    * If ``_is_binary_content_type(content_type)`` is True: returns
      ``(f"<binary content; {N} bytes; type={content_type}>", False)``
      regardless of cap. Binary detection bypasses both decode and
      truncation — agents shouldn't see raw bytes garbled into UTF-8.
    * Else: tail-preserving (drop FRONT, retain LAST cap bytes). On
      truncation, prepend
      ``"[... truncated N bytes; showing last M bytes of response ...]\\n"``
      (NO ``+stderr`` clause — web is single-stream, unlike execution).
    * Decoding uses ``errors="replace"`` so codepoints split mid-sequence
      by the byte-boundary tail slice produce the replacement char rather
      than raising.
    * Empty ``body`` → ``("", False)``. NOT ``(no output)`` — the
      ``"(no output)"`` fallback is execution-tool-specific (it reads
      better for ``ls /empty/dir`` than for ``HTTP 204``); web tools
      preserve empty as empty so callers can distinguish "no body" from
      "the literal string ``(no output)``".
    """
    if _is_binary_content_type(content_type):
        return (
            f"<binary content; {len(body)} bytes; type={content_type}>",
            False,
        )
    cap = cfg.response_size_cap_bytes
    if len(body) > cap:
        dropped = len(body) - cap
        tail = body[-cap:]
        marker = f"[... truncated {dropped} bytes; showing last {cap} bytes of response ...]\n"
        text = marker + tail.decode(errors="replace")
        return text, True
    return body.decode(errors="replace"), False


# ---------------------------------------------------------------------------
# SSRF-guarded httpx transport (F5 Decisions 1, 2, 6, 11)
# ---------------------------------------------------------------------------


def _host_matches(host: str, entry: str) -> bool:
    """Return True iff ``host`` matches ``extra_allowed_hosts`` entry.

    ``entry`` may be ``"host"`` or ``"host:port"``. F5 simplification:
    match on host part only — port distinction deferred to F6+.
    """
    entry_host = entry.split(":", 1)[0]
    return host == entry_host


class SSRFGuardedTransport(httpx.AsyncHTTPTransport):
    """Custom httpx transport that performs DNS resolution in-process,
    rejects requests that resolve to private / loopback / link-local /
    cloud-metadata IPs, and pins the connection to the validated IP
    (resolve-then-pin — F5 Decisions 1, 6).

    The pin step rewrites ``request.url.host`` to the resolved IP so the
    underlying connect targets exactly the IP the policy approved (no
    second resolve happens at connect time). To preserve TLS certificate
    validation against the original hostname, the transport sets
    ``request.extensions["sni_hostname"]`` (the httpx 0.28 SNI/cert seam)
    before rewriting, and also sets the ``Host:`` header so virtual-host
    routing on the server side keeps working.

    Operator overrides (``extra_allowed_hosts``) are checked BEFORE
    resolution: if the original hostname matches an entry in the list,
    the resolve+pin path is skipped entirely and the request is forwarded
    to the parent transport unchanged. Mission constraint: there is no
    full-disable toggle — the only opt-out is ``extra_allowed_hosts``.

    IP-literal URLs (``http://1.2.3.4/``) short-circuit the resolve+pin
    path — there's nothing to resolve — but the SSRF block check STILL
    applies. ``_is_ssrf_blocked(ip)`` is consulted in the IP-literal
    branch so that an agent passing ``http://127.0.0.1/``, ``http://10.0.0.1/``,
    or ``http://169.254.169.254/`` is refused with ``ConstraintError`` BEFORE
    any connect attempt. The operator's ``extra_allowed_hosts`` override
    is honored first (a literal IP listed there is allowed through), keeping
    the operator-opt-out semantic uniform between hostname and IP-literal
    paths.
    """

    def __init__(
        self,
        *args,
        extra_allowed_hosts: list[str] | tuple[str, ...] = (),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        # Materialize as tuple so callers passing a list don't accidentally
        # mutate state shared with the operator's WebConfig view.
        self._extra_allowed: tuple[str, ...] = tuple(extra_allowed_hosts)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        original_host = request.url.host

        # IP-literal short-circuit: if the URL host is already an IP, no
        # resolve+pin needed. SSRF block check STILL applies — operator
        # override (``extra_allowed_hosts``) is honored first, then the
        # default-block list refuses loopback / RFC1918 / link-local /
        # cloud-metadata literals BEFORE any connect attempt.
        try:
            ipaddress.ip_address(original_host)
            if any(_host_matches(original_host, entry) for entry in self._extra_allowed):
                return await super().handle_async_request(request)
            if _is_ssrf_blocked(original_host):
                raise ConstraintError(f"IP literal {original_host} is in the SSRF block list")
            return await super().handle_async_request(request)
        except ValueError:
            pass  # Not an IP literal; fall through to resolve+pin.

        # Operator override: if the hostname matches an ``extra_allowed_hosts``
        # entry, skip the resolve+pin path. (Common case: ``localhost:11434``
        # for a local Ollama server.)
        if any(_host_matches(original_host, entry) for entry in self._extra_allowed):
            return await super().handle_async_request(request)

        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        loop = asyncio.get_running_loop()
        resolved = await loop.getaddrinfo(original_host, port, type=socket.SOCK_STREAM)

        for _family, _stype, _proto, _canonname, sockaddr in resolved:
            ip = sockaddr[0]
            if not _is_ssrf_blocked(ip):
                # Rewrite for the connect target while preserving SNI +
                # ``Host:`` so cert validation and virtual-host routing
                # both still target the original hostname.
                request.extensions = {
                    **request.extensions,
                    "sni_hostname": original_host,
                }
                request.headers["Host"] = original_host
                # httpx 0.28 ``URL.copy_with(host=ip)`` accepts unbracketed
                # IPv6 strings and auto-brackets on serialization; no
                # special-case wrap for ``:`` is needed.
                request.url = request.url.copy_with(host=ip)
                return await super().handle_async_request(request)

        raise ConstraintError(
            f"all resolved IPs for {original_host} are blocked: {[s[4][0] for s in resolved]}"
        )
