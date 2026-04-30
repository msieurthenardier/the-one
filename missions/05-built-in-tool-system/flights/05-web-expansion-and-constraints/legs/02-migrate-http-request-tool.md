# Leg: 02-migrate-http-request-tool

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Migrate `HttpRequestTool` to the F5 constraint surface: declare `Config = WebConfig`, route through `_url_check` + `SSRFGuardedTransport`, clip timeouts via the F5 D1 pattern, apply `_truncate_response` for the cap, and wire `redirect_cap` to httpx's `follow_redirects` / `max_redirects` correctly. Three-clause try/except envelope (mirrors F4 L3).

## Context

- **L0 + L1 landed** (uncommitted). `WebConfig`, `_url_check`, `_is_ssrf_blocked`, `_truncate_response`, `SSRFGuardedTransport` all ship in `the_one/tools/_web_config.py`. L1's stub-tool consumer test exercised the full pipeline.
- **F5 Decisions 1, 4, 6, 9, 10** all converge here:
  - One `HttpRequestTool` (no split — D4); SSRF + caps + allowlist apply uniformly.
  - SSRF transport per Decision 6.
  - Redirect cap is tool-level only (D9); the tool consumes `cfg.redirect_cap` directly without checking for agent override (the resolver already rejected overrides).
  - Response-size cap via `_truncate_response` (D10).
- **Existing tool**: 49 LoC, no constraints. Existing test file `tests/test_web_tools.py::TestHttpRequestTool` uses `httpx.MockTransport` to inject controlled responses without real network calls. The L6 (F4) regression-net intent in `test_web_tools.py:24-30` explicitly says F5 must update those formatted-string contracts when introducing constraints — ours to update now.
- **Three-clause envelope** (per F4 L3 contract): `ConstraintError → asyncio.TimeoutError → Exception`. Order matters — TimeoutError IS an Exception subclass.
- **`redirect_cap` semantic**: when `cfg.redirect_cap == 0`, set `follow_redirects=False` so httpx returns the 3xx body verbatim (most agent-friendly). When `cfg.redirect_cap >= 1`, set `follow_redirects=True, max_redirects=cfg.redirect_cap` so httpx raises `httpx.TooManyRedirects` if exceeded.

## Inputs

- `the_one/tools/_web_config.py` — `WebConfig`, `_url_check`, `_truncate_response`, `SSRFGuardedTransport` (post-L1).
- `the_one/tools/base.py` — `ConstraintError`, `Tool` (`Tool.__init__(config, cross_configs, agent_name)` from F4 L1b).
- `the_one/tools/web.py` — current `HttpRequestTool` (will be rewritten).
- `tests/test_web_tools.py::TestHttpRequestTool` — five existing tests must pass after migration with construction shape updated.

## Outputs

- `the_one/tools/web.py`:
  - `HttpRequestTool` declares `Config = WebConfig`.
  - `description` updated to mention SSRF default-block + path-allowlist + size cap + redirect cap (small-model-readable).
  - `parameters.timeout` is now optional integer with description "Timeout in seconds. Uses the resolved default if omitted; clipped to operator-set max."
  - `execute(method, url, headers=None, body=None, timeout=None)` rewritten:
    1. `cfg = self._config` (typed `WebConfig`).
    2. Float-preserving timeout clip: if `timeout is None: clipped = cfg.timeout_seconds_default`; else `clipped = min(timeout, cfg.timeout_seconds_max); if clipped <= 0: clipped = 1`. (F4 L3 pattern; preserves fractional values.)
    3. Three-clause envelope:
       - `try`:
         - `_url_check(url, cfg)` — refuse non-http(s), apply allowlist + denylist.
         - Build the SSRF-guarded client:
           ```python
           transport = SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)
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
           ) as client:
               resp = await client.request(method, url, headers=headers, content=body)
           ```
         - Decode + truncate via `_truncate_response`:
           ```python
           text, _ = _truncate_response(
               resp.content, cfg, content_type=resp.headers.get("content-type"),
           )
           return f"[{resp.status_code}]\n{text}"
           ```
       - `except ConstraintError as e: return f"[error] [constraint] {e}"`
       - `except (asyncio.TimeoutError, httpx.TimeoutException): return f"[error] Request timed out after {clipped}s"` — **MUST catch both**: httpx 0.28.1's `httpx.TimeoutException` (parent of `ReadTimeout`/`ConnectTimeout`/`PoolTimeout`/`WriteTimeout`) does NOT inherit from `asyncio.TimeoutError`. The MRO is `TimeoutException → TransportError → RequestError → HTTPError → Exception`. Catching only `asyncio.TimeoutError` would let production httpx timeouts fall through to the generic handler and return `[error] {e}` instead of the F5 wording.
       - `except httpx.TooManyRedirects: return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"` (operator-policy refusal — formatted as constraint).
       - `except Exception as e: return f"[error] {e}"`
- `tests/test_web_tools.py::TestHttpRequestTool`:
  - All 5 existing tests updated to construct `HttpRequestTool(WebConfig())` (or narrower).
  - **Test transport seam — single chosen pattern**: replace the pre-F5 `_install_mock` factory with `monkeypatch.setattr(HttpRequestTool, "_build_transport", lambda self, cfg: httpx.MockTransport(handler))`. The pre-F5 `_install_mock` popped `transport=` from kwargs, which would silently discard the test's mock transport — incompatible with the L2 design. **Delete** `_install_mock` entirely and migrate each test to the `_build_transport` monkeypatch shape. SSRF coverage lives in `tests/test_web_helpers.py::TestSSRFGuardedTransport`; tool-behavior coverage uses the bypass.
  - **Pattern for new tests**:
    ```python
    def _patch_transport(monkeypatch, handler):
        """Replace HttpRequestTool._build_transport to inject a MockTransport
        carrying `handler`. Bypasses SSRF for tool-behavior tests."""
        from the_one.tools.web import HttpRequestTool
        monkeypatch.setattr(
            HttpRequestTool,
            "_build_transport",
            lambda self, cfg: httpx.MockTransport(handler),
        )
    ```
  - **Eight new constraint tests**:
    - `test_ssrf_block_loopback`: `_StubResolver` returns 127.0.0.1; agent passes `http://example.com`; tool returns `[error] [constraint] all resolved IPs ... blocked`. (Tests via SSRFGuardedTransport — separate from MockTransport-based tests.)
    - `test_redirect_cap_zero_returns_3xx_body`: `cfg.redirect_cap=0`; mock transport returns 302; tool returns `[302]\n<body>` without following.
    - `test_redirect_cap_exceeded`: `cfg.redirect_cap=1`; mock chain emits 302 → 302; tool returns `[error] [constraint] exceeded redirect cap of 1`.
    - `test_response_size_cap_truncated`: `cfg.response_size_cap_bytes=1024`; mock returns 5KB body; tool's response contains the truncation marker.
    - `test_url_allowlist_refuse`: `cfg.host_allowlist=["github.com"]`; agent passes `http://other.com`; tool returns `[error] [constraint] ... not in host_allowlist` (per L1 `_url_check` wording).
    - `test_url_denylist_refuse`: `cfg.host_denylist=["evil.com"]`; agent passes `http://evil.com`; tool returns `[error] [constraint] ...`.
    - `test_timeout_clipped_to_max`: `cfg.timeout_seconds_max=2`; agent passes `timeout=10`; mock handler raises `httpx.ReadTimeout("simulated timeout")` (NOT `asyncio.TimeoutError` — covers the production path that goes through httpx's own timeout class). Tool returns `[error] Request timed out after 2s` via the grouped `(asyncio.TimeoutError, httpx.TimeoutException)` clause.
    - `test_agent_narrow_extra_allowed_hosts`: agent's `tool_overrides` narrows `extra_allowed_hosts` from `["localhost"]` (operator) to `[]` (agent); resolver enforces; SSRF blocks localhost on the agent's invocation.

## Acceptance Criteria

- [x] `HttpRequestTool.Config is WebConfig`.
- [x] `HttpRequestTool.parameters.timeout` is optional (no `default` field; description says "Uses the resolved default if omitted").
- [x] `HttpRequestTool.description` mentions SSRF default-block, host allowlist/denylist, response-size cap, redirect cap (small-model-readable, not >150 words).
- [x] `HttpRequestTool.execute(method, url, headers=None, body=None, timeout=None)` calls `_url_check`, builds `httpx.AsyncClient(transport=SSRFGuardedTransport(...))`, decodes via `_truncate_response`, returns `[{status}]\n{text}`.
- [x] Float-preserving timeout clip applied (mirrors F4 L3 — `if clipped <= 0: clipped = 1`, fractional preserved).
- [x] `redirect_cap=0` sets `follow_redirects=False` (tool returns 3xx body verbatim); `redirect_cap >= 1` sets `follow_redirects=True, max_redirects=cap` (tool returns `[error] [constraint] exceeded redirect cap of N` on overrun).
- [x] Four-clause envelope: `ConstraintError → (asyncio.TimeoutError, httpx.TimeoutException) → httpx.TooManyRedirects → Exception`. The grouped timeout clause is mandatory — `httpx.TimeoutException` does NOT inherit from `asyncio.TimeoutError`.
- [x] **`httpx.TooManyRedirects` is formatted as `[error] [constraint] ...`** (operator policy refusal), NOT `[error] {e}` (generic exception).
- [x] Timeout-error wording: `"[error] Request timed out after Ns"` (F5-specific; distinct from F4 wordings).
- [x] All 5 existing `TestHttpRequestTool` tests pass with construction shape updated.
- [x] 8 new constraint-surface tests pass.
- [x] `BuiltinToolProvider().get_tools({}, {}, agent_name="x")` constructs `HttpRequestTool` with the resolved `WebConfig` — no regression in `test_builtins.py`.
- [x] Full unit suite green (modulo pre-existing CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
# Construction shape
docker exec the-one python -c "
from the_one.tools.web import HttpRequestTool
from the_one.tools._web_config import WebConfig
t = HttpRequestTool(WebConfig())
assert t.Config is WebConfig
print('OK construction')
"

# SSRF block (real transport, mocked resolver via monkeypatch happens in unit tests)
docker exec the-one python -c "
import asyncio
from the_one.tools.web import HttpRequestTool
from the_one.tools._web_config import WebConfig
async def main():
    t = HttpRequestTool(WebConfig())
    out = await t.execute(method='GET', url='http://169.254.169.254/latest/meta-data/')
    assert '[error] [constraint]' in out, out
    print('OK SSRF block via cloud-metadata IP literal')
asyncio.run(main())
"

# Tests
docker exec the-one pytest tests/test_web_tools.py tests/test_builtins.py tests/test_web_helpers.py tests/test_web_config.py tests/test_web_stub_tool.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# Lint
docker exec the-one ruff check the_one/tools/web.py tests/test_web_tools.py
```

## Implementation Guidance

1. **Rewrite `the_one/tools/web.py::HttpRequestTool`** following the F4 `ShellTool` template:

   ```python
   from __future__ import annotations

   import asyncio
   from typing import Any

   import httpx

   from the_one.tools._web_config import (
       SSRFGuardedTransport,
       WebConfig,
       _truncate_response,
       _url_check,
   )
   from the_one.tools.base import ConstraintError, Tool


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
               "body": {"type": "string", "description": "Request body (POST/PUT/PATCH)."},
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
           """Tests monkeypatch this method to inject `httpx.MockTransport`
           and bypass SSRF resolve+pin for tool-behavior coverage. The
           SSRF transport's own coverage lives in `tests/test_web_helpers.py`."""
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
               async with httpx.AsyncClient(
                   transport=transport,
                   timeout=clipped,
                   follow_redirects=follow,
                   max_redirects=max_redirs,
               ) as client:
                   resp = await client.request(method, url, headers=headers, content=body)
                   text, _ = _truncate_response(
                       resp.content, cfg, content_type=resp.headers.get("content-type"),
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
   ```

2. **Update existing `tests/test_web_tools.py::TestHttpRequestTool`** test construction:
   - Each test constructs `HttpRequestTool(WebConfig())` (or narrower).
   - Tests that need to inject mock responses use `monkeypatch.setattr(HttpRequestTool, "_build_transport", lambda self, cfg: httpx.MockTransport(handler))`.
   - Existing assertions on `[200]\n<body>` and `[error] {msg}` formats stay valid.

3. **Add 8 new constraint tests** per the Outputs section. The SSRF block test should use the actual `SSRFGuardedTransport` with a monkeypatched `BaseEventLoop.getaddrinfo` (mirrors L1's pattern).

4. **Verify `BuiltinToolProvider`** still constructs `HttpRequestTool` correctly. After L2, the cross_configs dispatch should pass `WebConfig` to the tool's `__init__`, OR the resolved config is passed as `config` (the F4 L1b shape). Confirm no test_builtins.py regression.

5. **Update `test_builtins.py::test_cross_configs_contains_three_distinct_configs`**: post-L2 the count becomes 4. **Rename** to `test_cross_configs_contains_four_distinct_configs`, update its docstring (currently says "EXACTLY three"), and update the assertion set to `{FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig}`.

## Edge Cases

- **`httpx.TimeoutException` vs `asyncio.TimeoutError`**: httpx 0.28 raises `httpx.ReadTimeout`/`httpx.ConnectTimeout` subclasses of `httpx.TimeoutException`. The leg's `except asyncio.TimeoutError` may NOT catch httpx's timeout exceptions (since they're separate hierarchies). **Fix**: catch `(asyncio.TimeoutError, httpx.TimeoutException)` together. Verify against httpx 0.28's exception hierarchy.

- **Redirect to a blocked IP**: a 302 to `http://169.254.169.254/` would be followed by httpx (with the SSRF transport in the chain), which would re-resolve the new URL and block it. Expected: `[error] [constraint] all resolved IPs ...`. Test if time permits.

- **`HEAD` / `OPTIONS`**: not in the `enum` list of methods today. Stay this way for F5 — agents don't need them, and adding them later is a one-line change.

- **Empty body on `POST`**: agent passes `method="POST"` without `body`. Today the tool sends `content=None` — same after migration. httpx accepts None.

- **`content-type` charset auto-detection**: L1's `_truncate_response` uses `errors="replace"` regardless of charset hint. Acceptable for F5; charset-aware decoding is a future enhancement.

- **Very long `description`**: keep under ~150 words for small-model parsing. Current draft: ~50 words. Good.

## Files Affected

- `the_one/tools/web.py` — full rewrite of `HttpRequestTool` (WebSearchTool migration is L6).
- `tests/test_web_tools.py` — update existing 5 tests; add 8 new constraint tests.
- `tests/test_builtins.py` — rename `test_cross_configs_contains_three_distinct_configs` → `..._four_distinct_configs`; update docstring; expand assertion set to include `WebConfig` (4 distinct types post-L2).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
