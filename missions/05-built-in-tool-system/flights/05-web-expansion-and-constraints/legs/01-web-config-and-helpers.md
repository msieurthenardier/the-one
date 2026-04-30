# Leg: 01-web-config-and-helpers

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Define `WebConfig` Pydantic model, the policy helpers (`_url_check`, `_is_ssrf_blocked`, `_truncate_response`), and the `SSRFGuardedTransport` custom httpx transport — all in a new `the_one/tools/_web_config.py` module. Add `readability-lxml` and `markdownify` to `pyproject.toml` and pip-install them in the running container. No tool wiring in this leg — pure scaffolding with full unit coverage and a stub-tool consumer test.

## Context

- **L0 landed** (uncommitted): unified `_filesystem_check(path, cfg, mode)` with `CheckMode` enum. F5 tools downstream consume this.
- **F5 Decisions 1, 2, 6, 7, 9, 10, 11** all converge here:
  - SSRF resolve-then-pin via custom `httpx.AsyncHTTPTransport` (D6) with `request.extensions["sni_hostname"]` to preserve TLS validation.
  - `extra_allowed_hosts` is `Annotated[list[str], Narrow]` (D7 — agent ⊆ operator).
  - `redirect_cap` is Field-only (no marker — D9; agent overrides raise `ValueError` at agent-build time).
  - `_truncate_response` mirrors F4's `_truncate_output` pattern but for single-stream responses (D10).
  - DNS-rebind unit test uses `monkeypatch.setattr(socket, "getaddrinfo", ...)` (D11 — moved from HAT to L1).
- **Mission constraint preserved**: SSRF protection is on by default; `extra_allowed_hosts` is the only opt-out; **no full-disable toggle**. L1 lock-tests this invariant.
- **`lxml` wheel install verified**: `docker exec the-one pip install lxml` succeeded with version 6.1.0 (no Dockerfile changes needed). `readability-lxml` depends on `lxml`; `markdownify` depends on `beautifulsoup4` (pure-Python wheel).
- **Stub-tool consumer test** (F4 debrief recommendation): L1 ships a fake tool that exercises the full pipeline — `WebConfig` resolution + `SSRFGuardedTransport` + `_truncate_response` — through a mocked httpx response. Catches the L2 helper-without-consumer gap class.

## Inputs

- `the_one/tools/base.py` — `ConstraintError`, `Tool`.
- `the_one/tools/resolver.py` — `Narrow`, `NarrowSuperset`, `_check_narrow`, `resolve()`.
- `the_one/tools/filesystem.py` — `CheckMode` (post-L0; not used in L1 directly but L4 will).
- `the_one/tools/execution.py` — `_TIMEOUT_DEFAULT_UI_CHOICES` constant (will reuse for `WebConfig.timeout_seconds_default` ui_choices).
- httpx 0.28.1 + httpcore 1.0.9 (verified in container).
- `pyproject.toml` — current dependencies block.

## Outputs

- `pyproject.toml`:
  - Add to `dependencies = [...]`:
    - `"readability-lxml>=0.8"`
    - `"markdownify>=0.13"`
  - L4 also needs `lxml` indirectly via `readability-lxml`; pip resolves automatically.
  - **Container side-effect**: implementer runs `docker exec the-one pip install readability-lxml markdownify` after editing pyproject.toml so the running uvicorn worker has the deps. Document in flight log.

- `the_one/tools/_web_config.py` (NEW):
  - Module docstring referencing F5 Decisions 1, 2, 6, 7, 9, 10.
  - **Constants**:
    - `_BLOCKED_CLOUD_METADATA_IPS: tuple[str, ...]` — `("169.254.169.254",)` for AWS/GCP/Azure metadata; IPv6 metadata IPs (Azure: `fd00:ec2::254`) added defensively.
    - `_DEFAULT_USER_AGENT: str` — `"the-one/0.2 (https://github.com/msieurthenardier/the-one)"`.
  - **`class WebConfig(BaseModel)`**:
    - `model_config = ConfigDict(frozen=True)`.
    - `timeout_seconds_default: Annotated[int, Narrow]` = `Field(30, ge=1, le=3600, json_schema_extra={"ui_hint": "dropdown", "ui_choices": _TIMEOUT_DEFAULT_UI_CHOICES})`. (Reuses F4's hoisted constant.)
    - `timeout_seconds_max: Annotated[int, Narrow]` = `Field(120, ge=1, le=3600)`.
    - `response_size_cap_bytes: Annotated[int, Narrow]` = `Field(1_048_576, ge=1024, le=104_857_600, json_schema_extra={"ui_hint": "dropdown", "ui_choices": _RESPONSE_SIZE_UI_CHOICES})`. Default 1 MB. **Pin exact choices** mirroring F3's `read_size_cap_bytes` (six entries):
      ```python
      _RESPONSE_SIZE_UI_CHOICES = [
          {"value": 51_200,    "label": "50KB — very small models"},
          {"value": 102_400,   "label": "100KB — small/7B-class friendly"},
          {"value": 262_144,   "label": "256KB — most models comfortable"},
          {"value": 524_288,   "label": "512KB — middle"},
          {"value": 1_048_576, "label": "1MB — default (Opus 200K headroom)"},
          {"value": 5_242_880, "label": "5MB — Opus 1M only"},
      ]
      ```
    - `redirect_cap: int` = `Field(5, ge=0, le=20, description="Maximum HTTP redirects per request. Tool-level only — agents cannot narrow this.")` — **NO marker** (Decision 9). The resolver raises `ValueError` if an agent override sets this key.
    - `host_allowlist: Annotated[list[str], Narrow]` = `Field(default_factory=list, description="If non-empty, ONLY hosts in this list are allowed. Empty = no allowlist constraint.")` — Narrow (agent ⊆ operator).
    - `host_denylist: Annotated[list[str], NarrowSuperset]` = `Field(default_factory=list, description="Hosts in this list are always refused, regardless of allowlist.")` — NarrowSuperset (agent must contain all operator entries; agent may add more).
    - `extra_allowed_hosts: Annotated[list[str], Narrow]` = `Field(default_factory=list, description="Hosts whose resolved IPs are exempt from the SSRF default-block list. Each entry: 'hostname' or 'hostname:port'. Common: 'localhost:11434' (Ollama). The SSRF protection itself is not disable-able; this list is the only opt-out.")` — Narrow (agent ⊆ operator).
    - `@model_validator(mode="after")` `_default_le_max` enforcing `timeout_seconds_default ≤ timeout_seconds_max` (mirrors F4 D1).
  - **Helpers**:
    - `def _is_ssrf_blocked(ip: str) -> bool`:
      - Parses `ip` via `ipaddress.ip_address(ip)`.
      - Returns `True` if any of: `is_loopback`, `is_link_local`, `is_private` (covers RFC1918), `ip in _BLOCKED_CLOUD_METADATA_IPS`.
      - Otherwise returns `False`.
      - **Does NOT consult `extra_allowed_hosts`** — the operator's allowlist short-circuit happens at the transport level on the original hostname (BEFORE resolution), not on the resolved IP. By the time `_is_ssrf_blocked` is called, the transport has already decided the host is not in the operator's allowlist.
    - `def _url_check(url: str, cfg: WebConfig) -> str`:
      - Parses URL via `urllib.parse.urlparse`.
      - Refuses non-http/https schemes (`raise ConstraintError(f"scheme '{scheme}' refused; http/https only")`).
      - Refuses URLs without a host.
      - If `cfg.host_allowlist` non-empty: refuse if host not in list.
      - If host in `cfg.host_denylist`: refuse.
      - Returns the URL unchanged on success.
    - `def _is_binary_content_type(ct: str | None) -> bool`:
      - Helper. Returns `True` if `ct` matches any of:
        - `startswith("image/")`, `startswith("audio/")`, `startswith("video/")`
        - `startswith("application/x-")` (covers `application/x-executable`, `application/x-tar`, etc.)
        - Exact match: `application/octet-stream`, `application/pdf`, `application/zip`, `application/gzip`, `application/x-bzip2` (already covered by `x-` prefix), `application/wasm`
      - `ct is None` or empty → `False` (treat as text).
    - `def _truncate_response(body: bytes, cfg: WebConfig, *, content_type: str | None = None) -> tuple[str, bool]`:
      - If `_is_binary_content_type(content_type)`: return `(f"<binary content; {len(body)} bytes; type={content_type}>", False)` regardless of cap.
      - Tail-preserving like F4's `_truncate_output`. If `len(body) > cfg.response_size_cap_bytes`: drop FRONT, retain LAST cap bytes.
      - Marker: `[... truncated N bytes; showing last M bytes of response ...]\n` (no `+stderr` since web is single-stream).
      - For text content (`_is_binary_content_type` returned False), decodes via `errors="replace"` (charset auto-detection from response is L2/L3's concern; L1 helper takes raw bytes and returns text).
      - Returns `(text, was_truncated)`.
    - `class SSRFGuardedTransport(httpx.AsyncHTTPTransport)`:
      - Subclass override. `__init__(self, *args, extra_allowed_hosts: list[str] = (), **kwargs)`: stash the list, call super.
      - `async def handle_async_request(self, request)`:
        - Extract `original_host = request.url.host`. Skip the rewrite if host is already an IP literal.
        - **`extra_allowed_hosts` short-circuit**: if `original_host` matches an entry in `extra_allowed_hosts`, skip the resolve+pin path and call super directly. (Operators allowing `localhost:11434` etc. don't need their resolved IP rewritten.)
        - Resolve via `loop = asyncio.get_running_loop(); resolved = await loop.getaddrinfo(original_host, port, type=SOCK_STREAM)`.
        - Iterate results; first IP that passes `not _is_ssrf_blocked(ip, extra_allowed_hosts)` wins.
        - Rewrite: `request.extensions = {**request.extensions, "sni_hostname": original_host}`; `request.headers["Host"] = original_host`; `request.url = request.url.copy_with(host=ip)`.
        - Call super.
        - If no IPs pass: raise `ConstraintError(f"all resolved IPs for {original_host} are blocked: {[s[4][0] for s in resolved]}")` — three-clause envelope at the tool layer translates this to `[error] [constraint] ...`.

- `tests/test_web_config.py` (NEW):
  - Pydantic-side tests:
    - Defaults populated (`timeout_seconds_default=30`, `..._max=120`, `response_size_cap_bytes=1_048_576`, `redirect_cap=5`, all lists empty).
    - Bounds enforced (`Field(ge=, le=)` on each numeric field).
    - `_default_le_max` cross-field validator: `default > max` raises; equal/less succeed.
    - `frozen=True` — mutation raises `pydantic.ValidationError`.
    - `host_allowlist`/`extra_allowed_hosts` default-factory returns a list (not tuple — consistent with F4 D3 lesson on `command_denylist`).
    - **Resolver narrowing** for each Narrow field: `Narrow` int-narrows correctly; `Narrow` list-narrow is subset (agent ⊆ tool) — covers `host_allowlist`, `extra_allowed_hosts`. `NarrowSuperset` for `host_denylist` (agent ⊇ tool).
    - **`redirect_cap` markerless rejection**: agent override on `redirect_cap` raises `ValueError` from `resolver.resolve(WebConfig, {}, {"redirect_cap": 0})` with message containing `"no Narrow/Substitute marker"`. Pin the test at the resolver level (NOT at AgentFactory.create level — that's L2's concern).
    - **No `disable_ssrf` field invariant**: `assert "disable_ssrf" not in WebConfig.model_fields and "ssrf_disabled" not in WebConfig.model_fields and "disable_ssrf_protection" not in WebConfig.model_fields`. Mission constraint lock.

- `tests/test_web_helpers.py` (NEW):
  - `_is_ssrf_blocked`:
    - Loopback `127.0.0.1` → True.
    - Link-local `169.254.0.1` → True.
    - Cloud metadata `169.254.169.254` → True.
    - RFC1918 `10.0.0.1`, `192.168.1.1`, `172.16.0.1` → True.
    - Public `1.1.1.1`, `8.8.8.8` → False.
    - IPv6 loopback `::1` → True. IPv6 link-local `fe80::1` → True.
    - **Operator override is NOT consulted by `_is_ssrf_blocked`**. The override short-circuit happens at `SSRFGuardedTransport` level (host-match BEFORE resolution); see `tests/test_web_helpers.py::TestSSRFGuardedTransport::test_extra_allowed_hosts_short_circuits_resolve` instead.
  - `_url_check`:
    - http/https URLs to public hosts → returns URL unchanged.
    - `ftp://example.com` → `ConstraintError` "scheme 'ftp' refused".
    - URL without host (e.g., `http:///foo`) → `ConstraintError`.
    - `host_allowlist=["example.com"]`, URL with `example.com` → passes; URL with `other.com` → refused.
    - `host_denylist=["evil.com"]`, URL with `evil.com` → refused.
    - Empty `host_allowlist` + empty `host_denylist` → no constraint (only SSRF applies later).
  - `_truncate_response`:
    - Below cap: returns body decoded.
    - Above cap: tail-preserved with marker; was_truncated=True.
    - Binary content type (`application/pdf`): returns `<binary content; N bytes; type=application/pdf>`, was_truncated=False (binary detection bypasses cap).
    - Empty body + 200: returns `("", False)` (NOT `(no output)` — that's an execution-tool fallback).
  - `SSRFGuardedTransport` (mocked-resolver tests):
    - Resolves hostname; passes if first IP is public; rewrites URL host to IP, preserves Host header + sni_hostname extension.
    - Resolves to all-blocked IPs → raises `ConstraintError`.
    - **DNS-rebind regression test**: monkeypatch `loop.getaddrinfo` to return `1.1.1.1` first, then `127.0.0.1` on second call. First call passes; second call (rebind) is blocked even though the public IP was allowed first. Pin the resolve-then-pin invariant.
    - `extra_allowed_hosts=["localhost"]` + URL `http://localhost/` → super().handle_async_request called with original URL (no rewrite).

- `tests/test_web_stub_tool.py` (NEW):
  - **Stub-tool consumer test** per F4 debrief recommendation. Defines a minimal `_StubWebTool(Tool)` that takes a URL, runs `_url_check`, executes via an httpx client wired to `SSRFGuardedTransport`, decodes via `_truncate_response`, returns the text. Tests:
    - End-to-end happy path: stub fetches a URL via `httpx.MockTransport` injected as base transport (not SSRF guard) — confirms the helpers compose correctly in a tool-shaped scenario.
    - End-to-end SSRF block: real `SSRFGuardedTransport` over a mocked resolver returning `127.0.0.1`. Stub's three-clause envelope catches `ConstraintError` and returns `[error] [constraint] ...`.
    - Confirms tools can declare `Config = WebConfig` and consume the helpers without pulling in tool-specific concerns.

## Acceptance Criteria

- [x] `the_one/tools/_web_config.py` exists with the documented public API.
- [x] `WebConfig` is frozen, has 7 fields (3 Narrow ints + Field-only redirect_cap + 2 Narrow lists + 1 NarrowSuperset list), and the `_default_le_max` cross-field validator.
- [x] `redirect_cap` is Field-only (no Narrow/Substitute marker); agent override on this key raises `ValueError` at resolver time.
- [x] **No `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field on `WebConfig`** — mission invariant lock.
- [x] `_is_ssrf_blocked` correctly identifies loopback, link-local, RFC1918, cloud-metadata, IPv6 loopback, and IPv6 link-local addresses as blocked.
- [x] `_url_check` refuses non-http/https schemes, hostless URLs, and applies host_allowlist + host_denylist correctly.
- [x] `_truncate_response` tail-preserves with the documented marker; binary content types bypass via `<binary content; N bytes>` form.
- [x] `SSRFGuardedTransport`:
  - Sets `request.extensions["sni_hostname"]` for SNI preservation.
  - Sets `Host:` header.
  - Rewrites URL host to resolved IP via `request.url.copy_with(host=ip)`.
  - Uses `asyncio.get_running_loop().getaddrinfo` (not deprecated `get_event_loop()`).
  - Short-circuits resolve+pin when host matches `extra_allowed_hosts`.
  - Raises `ConstraintError` when all resolved IPs are blocked.
- [x] **DNS-rebind regression test**: monkeypatched resolver returning public-IP-then-loopback-IP — second call blocked.
- [x] Stub-tool consumer test exercises `WebConfig` + helpers + transport in a tool-shaped scenario (per F4 debrief recommendation).
- [x] `pyproject.toml` includes `"readability-lxml>=0.8"` and `"markdownify>=0.13"` in `dependencies`.
- [x] Container has the deps installed: `docker exec the-one python -c "import readability, markdownify"` succeeds.
- [x] All new tests pass.
- [x] No regressions: full unit suite green (modulo pre-existing CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
# Module exists and exports the right names
docker exec the-one python -c "
from the_one.tools._web_config import (
    WebConfig, _is_ssrf_blocked, _url_check, _truncate_response,
    SSRFGuardedTransport, _BLOCKED_CLOUD_METADATA_IPS, _DEFAULT_USER_AGENT,
)
import inspect
assert WebConfig.model_config['frozen'] is True
assert 'disable_ssrf' not in WebConfig.model_fields
print('OK exports')
"

# Defaults
docker exec the-one python -c "
from the_one.tools._web_config import WebConfig
c = WebConfig()
assert c.timeout_seconds_default == 30
assert c.timeout_seconds_max == 120
assert c.response_size_cap_bytes == 1_048_576
assert c.redirect_cap == 5
assert c.host_allowlist == [] and c.host_denylist == [] and c.extra_allowed_hosts == []
print('OK defaults')
"

# redirect_cap markerless rejection
docker exec the-one python -c "
from the_one.tools._web_config import WebConfig
from the_one.tools.resolver import resolve
try:
    resolve(WebConfig, {}, {'redirect_cap': 0})
    raise SystemExit('FAIL: expected ValueError')
except ValueError as e:
    assert 'no Narrow/Substitute marker' in str(e), e
    print(f'OK markerless rejection: {e}')
"

# SSRF block
docker exec the-one python -c "
from the_one.tools._web_config import _is_ssrf_blocked
assert _is_ssrf_blocked('127.0.0.1', []) is True
assert _is_ssrf_blocked('169.254.169.254', []) is True
assert _is_ssrf_blocked('10.0.0.1', []) is True
assert _is_ssrf_blocked('1.1.1.1', []) is False
print('OK SSRF block')
"

# Tests
docker exec the-one pytest tests/test_web_config.py tests/test_web_helpers.py tests/test_web_stub_tool.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# Lint
docker exec the-one ruff check the_one/tools/_web_config.py tests/test_web_config.py tests/test_web_helpers.py tests/test_web_stub_tool.py
```

## Implementation Guidance

1. **First step — install deps in the running container** (BEFORE editing pyproject.toml so the dev loop has the deps available):
   ```bash
   docker exec the-one pip install readability-lxml markdownify
   docker exec the-one python -c "import readability, markdownify; print('OK')"
   ```
   THEN edit `pyproject.toml` to add the deps to the `dependencies = [...]` list (so future container rebuilds get them too).

2. **Create `the_one/tools/_web_config.py`** following the F4 `execution.py` pattern:
   - Top-of-file imports: `asyncio`, `socket`, `ipaddress`, `urllib.parse`, `httpx`, Pydantic bits.
   - Module docstring referencing F5 Decisions.
   - Constants block.
   - `WebConfig` class (mirror `ExecutionConfig`'s shape; add 4 list fields).
   - Helpers (`_is_ssrf_blocked`, `_url_check`, `_truncate_response`).
   - `SSRFGuardedTransport` class.

3. **`SSRFGuardedTransport.handle_async_request` exact shape** (per Decision 6, architect-corrected):
   ```python
   async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
       original_host = request.url.host
       # IP-literal short-circuit: if URL is already an IP, no resolve+pin needed.
       try:
           ipaddress.ip_address(original_host)
           return await super().handle_async_request(request)
       except ValueError:
           pass

       # extra_allowed_hosts host-match short-circuit (operator override).
       if any(_host_matches(original_host, entry) for entry in self._extra_allowed):
           return await super().handle_async_request(request)

       port = request.url.port or (443 if request.url.scheme == "https" else 80)
       loop = asyncio.get_running_loop()
       resolved = await loop.getaddrinfo(original_host, port, type=socket.SOCK_STREAM)

       for family, _type, _proto, _canonname, sockaddr in resolved:
           ip = sockaddr[0]
           if not _is_ssrf_blocked(ip, self._extra_allowed):
               # Rewrite for connect target; preserve SNI + Host header.
               request.extensions = {
                   **request.extensions,
                   "sni_hostname": original_host,
               }
               request.headers["Host"] = original_host
               request.url = request.url.copy_with(host=ip)
               return await super().handle_async_request(request)

       raise ConstraintError(
           f"all resolved IPs for {original_host} are blocked: "
           f"{[s[4][0] for s in resolved]}"
       )
   ```

4. **`_host_matches(host, entry)` helper** for the short-circuit:
   ```python
   def _host_matches(host: str, entry: str) -> bool:
       """`entry` may be 'host' or 'host:port'. F5 simplification: match
       on host part only — port distinction deferred to F6+."""
       entry_host = entry.split(":", 1)[0]
       return host == entry_host
   ```

5. **DNS-rebind regression test**:
   - **Patch target**: `asyncio.base_events.BaseEventLoop.getaddrinfo` (architect-verified). The naive `AbstractEventLoop.getaddrinfo` patch does NOT intercept calls because `BaseEventLoop` overrides the method and sits ahead in MRO.
   - **Connection pool affinity**: httpx's default connection pool may reuse the connection from request 1 and skip the second resolve entirely. Force per-request resolution by constructing the test client with `limits=httpx.Limits(max_keepalive_connections=0)`.

   ```python
   async def test_dns_rebind_blocked_on_second_resolve(monkeypatch):
       import asyncio.base_events

       call_count = {"n": 0}

       async def fake_getaddrinfo(self, host, port, *args, **kwargs):
           call_count["n"] += 1
           if call_count["n"] == 1:
               return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", port))]
           return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", port))]

       monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)
       # ... build SSRFGuardedTransport, fire two requests through MockTransport,
       # assert first succeeds, second raises ConstraintError.
   ```

6. **Stub-tool consumer test pattern**:
   ```python
   class _StubWebTool(Tool):
       name = "stub_web"
       description = "Test consumer for WebConfig + helpers."
       parameters = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
       Config = WebConfig

       async def execute(self, url: str, **kwargs) -> str:
           cfg = self._config
           try:
               _url_check(url, cfg)
               transport = SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)
               async with httpx.AsyncClient(
                   transport=transport,
                   timeout=cfg.timeout_seconds_default,
                   max_redirects=cfg.redirect_cap,
                   follow_redirects=cfg.redirect_cap > 0,
               ) as client:
                   resp = await client.get(url)
                   text, _ = _truncate_response(
                       resp.content, cfg, content_type=resp.headers.get("content-type"),
                   )
                   return text
           except ConstraintError as e:
               return f"[error] [constraint] {e}"
           except Exception as e:
               return f"[error] {e}"
   ```

   Tests inject controlled responses via `httpx.MockTransport` wired UNDER `SSRFGuardedTransport` (which delegates to its parent for the actual transport).

## Edge Cases

- **`extra_allowed_hosts` host-vs-IP semantic**: the leg's `_is_ssrf_blocked(ip, extra_allowed_hosts)` receives an IP, not a hostname. The match operates on the post-resolution `original_host` separately (in `SSRFGuardedTransport.handle_async_request`'s short-circuit). So `_is_ssrf_blocked` passed `extra_allowed_hosts=["localhost"]` and IP `127.0.0.1` would NOT match by hostname-string equality. **Resolution**: `_is_ssrf_blocked` does NOT consult `extra_allowed_hosts` — the short-circuit happens at the transport level on `original_host`. Update the helper to take only the IP. The short-circuit has already happened by the time `_is_ssrf_blocked` is called.

- **IPv6 metadata IP**: Azure exposes `fd00:ec2::254`. Add to `_BLOCKED_CLOUD_METADATA_IPS` defensively. Most operators won't use IPv6 in practice, but the constant should be complete.

- **`request.url.copy_with(host=ip)` IPv6 syntax**: architect-verified that httpx 0.28.1 `URL.copy_with(host="::1")` accepts the unbracketed IPv6 string and produces a valid URL (httpx auto-brackets on serialization). **No special-case wrap needed** — pass `request.url.copy_with(host=ip)` directly regardless of IP family. (If a future httpx version regresses this, the implementer can re-introduce the `if ":" in ip: f"[{ip}]"` wrap, but L1 ships without it.)

- **`redirect_cap=0` interaction with httpx**: when `redirect_cap=0`, set `follow_redirects=False`. When `>= 1`, set `follow_redirects=True, max_redirects=cap`. Stub-tool test exercises both branches.

- **Resolver raises `ValueError` not `ConstraintError`** for markerless agent overrides on `redirect_cap`. This is intentional — surfaces at agent-build time as a configuration error, not at tool-execution time. L2 will need to handle this when building a `WebSearchTool` factory; for L1, the resolver-level test is sufficient.

- **`getaddrinfo` monkeypatch target** (architect-verified): patch `asyncio.base_events.BaseEventLoop.getaddrinfo` — `BaseEventLoop` overrides the method and sits ahead of `AbstractEventLoop` in the running loop's MRO, so patching `AbstractEventLoop` does NOT intercept calls. If a future loop implementation (uvloop) bypasses `BaseEventLoop`, the test should `monkeypatch.setattr(socket, "getaddrinfo", ...)` as a fallback.
- **Connection pool affinity for DNS-rebind**: httpx's default connection pool may reuse the request-1 connection on request-2, skipping the second resolve. Force per-request resolution in the rebind test via `httpx.Limits(max_keepalive_connections=0)`. Production tools (L2-L4) construct fresh `httpx.AsyncClient` per call so this isn't a concern outside the test.
- **`pyproject.toml` ordering**: existing deps grouped by role (http → pydantic → ui → web → storage → crypto). Append `readability-lxml` and `markdownify` after `httpx>=0.27` (web role) — keeps the role-grouping coherent.

## Files Affected

- `pyproject.toml` — add `readability-lxml>=0.8` and `markdownify>=0.13` to `dependencies`.
- `the_one/tools/_web_config.py` — NEW.
- `tests/test_web_config.py` — NEW.
- `tests/test_web_helpers.py` — NEW.
- `tests/test_web_stub_tool.py` — NEW.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
