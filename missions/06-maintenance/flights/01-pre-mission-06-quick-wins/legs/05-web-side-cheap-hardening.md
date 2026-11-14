# Leg: 05-web-side-cheap-hardening

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Add an Origin-allowlist middleware to FastAPI that rejects state-mutating requests from disallowed origins, and add scheme validation to the LLM provider save path so that non-`https://` `base_url` for non-localhost hosts is warned (or refused) at save time. Both are cheap mitigations that close meaningful attack surface without violating the project's documented no-auth posture.

## Context

Maintenance report findings 1.2 and 1.3 (see `maintenance/2026-05-04.md`).

- **1.2**: No CSRF/Origin verification on state-mutating routes. `docker-compose.yml` overrides bind to `0.0.0.0` and enables `THE_ONE_DEV_MODE=true`. Routes include `POST /api/encryption/rotate`, `PUT /api/agents/{name}`, `PUT /api/providers/{provider_id}`, `POST /api/providers/{provider_id}/models/pull`. A malicious page in the operator's browser can issue `fetch('http://127.0.0.1:8484/api/...', {method:'POST'})` cross-origin; SOP blocks reading the response but not the side-effecting write. Same-origin check via `Origin`/`Referer` header in middleware closes this without adding auth.
- **1.3**: LLM provider API keys can be sent over `http://` if operator configures non-https `base_url`. `the_one/interfaces/web/api.py:817-822` (provider save / test path) does no scheme validation. Bearer token in cleartext to attacker-controlled URL if operator misconfigures. Ollama's default `http://host.docker.internal:11434` is fine (no auth, localhost), but `openai-compatible`/`anthropic`/`openai` types over `http://` to non-localhost are a real exposure.

Per flight.md design decision: middleware is a small ASGI function in `the_one/interfaces/web/`, NOT a new package dependency.

## Inputs

- `the_one/interfaces/web/app.py` (existing; FastAPI app construction, route registration)
- `the_one/interfaces/web/api.py` (existing; provider save endpoints around line 817)
- `the_one/config.py` (existing; `Settings` class with `host` field)

## Outputs

- New ASGI middleware (or function) registered on the FastAPI app that rejects state-mutating requests (POST/PUT/PATCH/DELETE) when `Origin` or `Referer` doesn't match the allow-list
- Default allow-list derived from `settings.host` + dev-mode `127.0.0.1`/`localhost`/`::1` patterns; configurable via `THE_ONE_ORIGIN_ALLOWLIST` env var (comma-separated)
- Provider save path validates `base_url` scheme: refuse (or warn loudly) `http://` for non-localhost hosts
- Tests for both behaviors

## Acceptance Criteria

- [x] FastAPI ASGI middleware (`app.add_middleware(...)` — NOT `Depends`, which runs after `ws.accept()` and cannot gate WebSocket upgrades) checks `Origin` on state-mutating methods (POST, PUT, PATCH, DELETE) and on WebSocket upgrades
- [x] Default allowlist matches exact `{scheme}://{host}:{port}` strings, with port-wildcard `:*` accepted for `127.0.0.1`/`localhost`/`[::1]` (the `app_clean` browser-test fixture binds uvicorn to `127.0.0.1` on a random OS-allocated port; allowlist must accept any port to keep Playwright tests green)
- [x] Same-origin AND missing-Origin (curl, server-to-server) both pass; foreign Origin returns 403 on state-mutating methods
- [x] `THE_ONE_ORIGIN_ALLOWLIST` env var (comma-separated) extends the allowlist for operator-configurable trusted origins (e.g., reverse-proxy hostname)
- [x] HTTP `GET`/`HEAD`/`OPTIONS` requests are NOT gated (preserve normal browser behavior; SOP already protects reads)
- [x] WebSocket `/ws` upgrade rejects (close code 1008) BEFORE `ws.accept()` if origin is foreign
- [x] Provider URL validation: **shared `_is_safe_provider_url()` helper** is called from THREE endpoints — `create_provider` (POST `/api/providers`), `update_provider` (PUT `/api/providers/{id}`), and `test_provider` (POST `/api/providers/{id}/test`)
- [x] Provider validation runs on the RESOLVED `base_url` (post-merge with stored value when the request sends `__MASKED__`-style preserved fields) — NOT raw request data — so unchanged http://example.com cannot survive untouched updates
- [x] Provider types `mock` and `ollama` skip URL validation entirely (mock has no real URL; ollama is local-by-design)
- [x] Provider URL with scheme `http://` AND host NOT in `{localhost, 127.0.0.1, ::1, *.localdomain}` returns **422** with a clear error message (refusal, NOT warning — pinned contract)
- [x] Provider URL with scheme `https://` always passes
- [x] Unit tests added to `tests/test_provider_api.py` (NOT `test_db_api.py` — provider tests live in `test_provider_api.py`): `create_provider` and `update_provider` reject `http://example.com:5000`; `http://localhost:11434` passes (ollama default); `https://api.openai.com` passes; `mock` type skips validation
- [x] New file `tests/test_origin_allowlist.py`: parametrized tests for allowed/foreign origins on POST and GET (using `starlette.testclient.TestClient`); WebSocket Origin test using `TestClient.websocket_connect` with custom Origin header
- [x] Existing browser tests pass (Playwright sets Origin to `http://127.0.0.1:<random_port>` from the `app_clean` fixture; covered by the port-wildcard rule)

## Verification Steps

- `cd ~/projects/the-one && pytest tests/test_origin_allowlist.py -v` (or wherever the new tests land) — passes
- `cd ~/projects/the-one && pytest tests/test_db_api.py -v` — provider save validation tests pass
- `cd ~/projects/the-one && pytest -m browser tests/browser/ -q 2>&1 | tail -10` — no browser-test regression
- `curl -X POST http://127.0.0.1:8484/api/encryption/rotate -H 'Origin: http://evil.example.com'` — returns 403
- `curl -X POST http://127.0.0.1:8484/api/encryption/rotate -H 'Origin: http://127.0.0.1:8484'` — returns its normal status (200/400/etc., not 403)
- `curl -X GET http://127.0.0.1:8484/api/info -H 'Origin: http://evil.example.com'` — returns 200 (GET not gated)
- Manual UI test: save an LLM provider with `http://example.com:5000` base_url and `openai-compatible` type — error/warning surfaces; with `http://localhost:11434` — saves normally

## Implementation Guidance

1. **Origin-allowlist middleware** — **Option A is REQUIRED** (not optional). `Depends()` on the WS handler runs AFTER `ws.accept()` (`app.py:731` registers `@app.websocket("/ws")` and the body unconditionally calls `await ws.accept()` at line 733). Only ASGI middleware can intercept the upgrade BEFORE `accept()`.
   - **Allowlist construction** — build a list of exact `{scheme}://{host}:{port}` strings PLUS support for port-wildcard `:*` for localhost variants:
     ```python
     def _build_default_allowlist(settings) -> list[str]:
         items = [
             "http://127.0.0.1:*",       # any port (browser tests use random port)
             "http://localhost:*",
             "http://[::1]:*",
         ]
         # Operator-configured bind
         items.append(f"http://{settings.host}:{settings.port}")
         # Extend from THE_ONE_ORIGIN_ALLOWLIST env var
         extra = os.environ.get("THE_ONE_ORIGIN_ALLOWLIST", "")
         items.extend(s.strip() for s in extra.split(",") if s.strip())
         return items
     ```
   - **Matcher** — exact match OR port-wildcard match:
     ```python
     def _origin_matches(origin: str, allowlist: list[str]) -> bool:
         for entry in allowlist:
             if entry.endswith(":*"):
                 prefix = entry[:-1]  # "http://127.0.0.1:"
                 if origin.startswith(prefix):
                     # ensure what follows the colon is a port (digits only), not a domain like "127.0.0.1.evil.com"
                     rest = origin[len(prefix):]
                     port_part = rest.split("/")[0]
                     if port_part.isdigit():
                         return True
             elif origin == entry:
                 return True
         return False
     ```
   - **Middleware skeleton**:
     ```python
     # the_one/interfaces/web/middleware.py (new file) OR inline in app.py
     class OriginAllowlistMiddleware:
         GATED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

         def __init__(self, app, allowlist: list[str]):
             self.app = app
             self._allowlist = tuple(allowlist)

         async def __call__(self, scope, receive, send):
             if scope["type"] not in ("http", "websocket"):
                 return await self.app(scope, receive, send)
             # Extract origin from headers
             headers = dict(scope.get("headers") or [])
             origin = headers.get(b"origin", b"").decode("latin-1")
             # WebSocket: always check
             if scope["type"] == "websocket":
                 if origin and not self._is_allowed(origin):
                     # Reject before accept
                     await send({"type": "websocket.close", "code": 1008})
                     return
             else:  # http
                 method = scope.get("method", "GET").upper()
                 if method in self.GATED_METHODS and origin and not self._is_allowed(origin):
                     await self._send_403(send)
                     return
             return await self.app(scope, receive, send)

         def _is_allowed(self, origin: str) -> bool:
             # Match scheme://host[:port] against allowlist
             return any(origin == allowed or origin.startswith(allowed + "/") for allowed in self._allowlist)

         async def _send_403(self, send): ...
     ```
   - Build the default allowlist from `settings.host`, `127.0.0.1`, `localhost`, `[::1]` and the configured port.
   - Read `THE_ONE_ORIGIN_ALLOWLIST` env var and split on comma; append to the default.
   - Register the middleware in `app.py` BEFORE other middleware (so it gates earliest).

2. **Provider URL scheme validation** — applied at THREE endpoints, NOT one
   - The mutating surface is broader than the original maintenance report cited. After Leg 01's ruff format, `api.py` is ~1080 lines; provider endpoints span 657–960. Specifically:
     - `create_provider` — `POST /api/providers` (~line 717)
     - `update_provider` — `PUT /api/providers/{provider_id}` (~line 733)
     - `test_provider` — `POST /api/providers/{provider_id}/test` (~line 796)
   - Use **function names** as anchors (stable across formatting passes), not numeric line citations.
   - Add a helper (centralized; called from all 3 endpoints):
     ```python
     def _is_safe_provider_url(url: str) -> tuple[bool, str | None]:
         from urllib.parse import urlparse
         parsed = urlparse(url)
         if parsed.scheme == "https":
             return True, None
         if parsed.scheme == "http":
             host = (parsed.hostname or "").lower()
             if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localdomain"):
                 return True, None
             return False, "Provider base_url uses http:// for a non-localhost host. API keys would be sent in cleartext. Use https:// or restrict to localhost."
         return False, f"Provider base_url scheme '{parsed.scheme}' not supported. Use http:// (localhost only) or https://."
     ```
   - **Pinned contract**: REFUSE (raise `HTTPException(422, detail=msg)`), do NOT warn. Implementer should NOT choose between refuse/warn — refuse is the contract.
   - Skip validation entirely for `provider.type in {"mock", "ollama"}` (mock has no real URL; ollama is local-by-design). Only validate for `openai`, `anthropic`, `openai-compatible`.
   - **Call sites**:
     - `create_provider`: validate AFTER `model_validate` parses the request body, BEFORE any DB write.
     - `update_provider`: validate on the RESOLVED `base_url` (post-merge with stored value when the request sends `__MASKED__`-preserved fields), not raw request data. This prevents an unchanged http://example.com from surviving an untouched update.
     - `test_provider`: reads `provider.base_url` from the DB. Validation here is belt-and-suspenders — if `create_provider`/`update_provider` did their job, the stored URL is already safe. Add the call anyway in case operator data was loaded from a pre-leg backup.

3. **Tests**
   - **New file** `tests/test_origin_allowlist.py`: parametrized tests using `starlette.testclient.TestClient` (already transitive via FastAPI; do NOT add `httpx_ws` as a new dep). Cover:
     - GET request with foreign Origin → passes (safe method).
     - POST with foreign Origin → 403.
     - POST with allowed Origin (`http://127.0.0.1:8484`) → not 403 (passes through to handler).
     - POST with no Origin header (curl, server-to-server) → passes through.
     - POST with port-wildcard match (`http://127.0.0.1:54321`) → passes (browser-test scenario).
     - WebSocket connect with foreign Origin → close code 1008 BEFORE accept.
     - WebSocket connect with allowed Origin → accepts normally.
     - `THE_ONE_ORIGIN_ALLOWLIST` env var extension: reverse-proxy-style hostname is allowed.
   - **Extend** `tests/test_provider_api.py` (NOT `test_db_api.py` — provider tests live in `test_provider_api.py`; verified file presence): add to existing `TestProviderAPI` (or new `TestProviderUrlValidation` class):
     - `create_provider` with `type="openai-compatible"` and `base_url="http://example.com:5000"` → 422 with clear message.
     - `create_provider` with `type="ollama"` and `base_url="http://localhost:11434"` → 201 (skip validation).
     - `create_provider` with `type="openai-compatible"` and `base_url="http://localhost:11434"` → 201 (localhost-OK).
     - `create_provider` with `type="openai"` and `base_url="https://api.openai.com"` → 201.
     - `update_provider` with `base_url="http://example.com:5000"` → 422.
     - `update_provider` with masked api_key + unchanged http://example.com → 422 (resolved-base-url validation).
     - `test_provider` against a stored `http://example.com` URL (legacy data) → 422.

4. **Document the allowlist env var in `.env.example`**
   - Add: `# THE_ONE_ORIGIN_ALLOWLIST=http://example.local:8484` (commented out by default).

## Edge Cases

- **No Origin header (curl, server-to-server, Postman)**: per-spec, allow when missing. The threat is browser-mediated cross-origin POSTs which always include `Origin` for state-mutating methods.
- **`Referer` fallback**: some older clients omit `Origin` but include `Referer`. Optional second-line check on `Referer` if `Origin` is missing on a state-mutating method. Implementer's call.
- **WebSocket close code**: `1008` is "policy violation"; appropriate semantic.
- **Reverse proxy in front of the-one**: operator deploying behind nginx/caddy will need to add the proxy's hostname to `THE_ONE_ORIGIN_ALLOWLIST`. Document in `.env.example` comment.
- **Provider URL warning UX**: if the implementer chooses warn-not-refuse, ensure the warning is clearly visible in the UI (red banner, not just a toast that auto-dismisses).
- **Existing browser tests must not break**: Playwright defaults Origin to the test server's origin (which matches `127.0.0.1`). No test changes should be needed unless a test explicitly sets a foreign Origin.

## Files Affected

- `the_one/interfaces/web/middleware.py` — NEW file with `OriginAllowlistMiddleware` ASGI class
- `the_one/interfaces/web/app.py` — `app.add_middleware(OriginAllowlistMiddleware, ...)` registration (BEFORE other middleware)
- `the_one/interfaces/web/api.py` — `_is_safe_provider_url()` helper called from `create_provider`, `update_provider`, `test_provider` (3 call sites)
- `tests/test_origin_allowlist.py` — NEW tests using `starlette.testclient.TestClient`
- `tests/test_provider_api.py` — provider URL validation test extension (NOT `test_db_api.py`)
- `.env.example` — documented `THE_ONE_ORIGIN_ALLOWLIST` env var

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (unit + browser)
- [ ] Manual curl verification: foreign Origin gets 403, same-origin passes
- [ ] Manual UI verification: provider save with non-https non-localhost URL surfaces warning/error
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
