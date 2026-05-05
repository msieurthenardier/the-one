# Leg: 02-edge-case-tests

**Status**: completed
**Flight**: [Debrief Follow-ups](../flight.md)

## Objective

Add 1 edge-case test surfaced by Flight 01's debrief: lock in the WebSocket-with-no-Origin pass-through behavior so a future change to gate missing-Origin WS upgrades can't silently break server-to-server clients. The 2nd item from the debrief — `test_provider` happy-path test — was discovered during design review to **already exist** as the `TestConnectionTest` class (`tests/test_provider_api.py:653-768`), where `test_openai_compatible_success` (L688), `test_openai_success` (L716), and `test_anthropic_success` (L738) all exercise the validator-passes-through path with safe URLs. That checklist item is therefore retired as already-satisfied; no new provider test in this leg.

## Context

Flight 01 debrief — "Testing Assessment" section action items:

- **WS-with-no-Origin pass-through is correct but untested.** `OriginAllowlistMiddleware` (`the_one/interfaces/web/middleware.py:68-74`) passes through WebSocket upgrade requests when the `Origin` header is absent — the gate is `if origin and not self._is_allowed(origin)`, and `_extract_origin` returns `""` when the header is missing (L91), so the truthy-check short-circuits. This is correct because non-browser clients (curl-style server-to-server WS) don't send `Origin`. But no test asserts this branch. If a future change gates missing-Origin WS, it would silently break server-to-server clients and the only signal would be a runtime regression in some unrelated integration test.
- **`test_provider` happy-path test** — design-review surfaced that `TestConnectionTest` already covers this. `test_openai_compatible_success` uses `http://localhost:1234/v1` (passes localhost-exempt branch); `test_openai_success` and `test_anthropic_success` use `https://...` URLs (pass scheme-https branch). All three reach the upstream-mock invocation, which means the URL validator demonstrably passed through. The Flight 01 debrief's "rejection-only coverage" assessment was based on a grep that missed `TestConnectionTest`. Item retired; no new test.

## Inputs

- `tests/test_origin_allowlist.py` (existing; uses `starlette.testclient.TestClient` (NOT `httpx_ws`) + an in-file `_make_app(allowlist: Iterable[str]) -> FastAPI` helper at L36-69 that builds a throwaway FastAPI with a stub `/ws` echo route at L58-66; WS-rejection test pattern at `TestWebSocketGating.test_websocket_with_foreign_origin_closes_1008` L150-162; WS-allowed pattern at `test_websocket_with_allowed_origin_accepts` L164-169)
- `the_one/interfaces/web/middleware.py` (existing; WS branch at L68-74; no-Origin pass-through implicit via `_extract_origin` returning `""` on missing header at L91)
- `tests/test_provider_api.py` (existing; `TestConnectionTest` at L653-768 already covers `test_provider` happy-path — informational only, no edits in this leg)

## Outputs

- `tests/test_origin_allowlist.py` has a new test `test_websocket_with_no_origin_passes` inside the existing `TestWebSocketGating` class (after `test_websocket_with_allowed_origin_accepts` at L164-169 and before `test_websocket_with_port_wildcard_origin_accepts` at L171). The test mirrors the structure of `test_websocket_with_allowed_origin_accepts` exactly: `_make_app(["http://127.0.0.1:8484"])` → `TestClient(app)` → `client.websocket_connect("/ws")` with NO `headers=` kwarg → `ws.send_text("hello")` → `assert ws.receive_text() == "echo:hello"`. The absence of `headers=` means TestClient sends no `Origin`, exercising the pass-through branch.

## Acceptance Criteria

- [x] `tests/test_origin_allowlist.py` contains a new test `test_websocket_with_no_origin_passes` inside `TestWebSocketGating` class
- [x] The new test uses `_make_app(...)` + `TestClient` + `client.websocket_connect("/ws")` with NO `headers=` kwarg (mirrors `test_websocket_with_allowed_origin_accepts` shape)
- [x] The new test asserts `ws.receive_text() == "echo:hello"` after sending `"hello"` — proves the connection was accepted (i.e., the middleware did NOT close it with code 1008)
- [x] New test passes in isolation: `pytest tests/test_origin_allowlist.py::TestWebSocketGating::test_websocket_with_no_origin_passes -v --timeout=30` shows PASSED
- [x] No regression: full `pytest -q --ignore=tests/browser --timeout=120` shows the same green count as the pre-leg baseline plus exactly 1 new test
- [x] Ruff lint + format clean: `ruff check tests/ && ruff format --check tests/`
- [x] No new dependencies — TestClient is already imported in `test_origin_allowlist.py` (L23 area); no `httpx_ws` or `websockets` imports added

## Verification Steps

- `cd /home/cprch/projects/the-one && grep -n "test_websocket_with_no_origin_passes" tests/test_origin_allowlist.py`
- `cd /home/cprch/projects/the-one && pytest tests/test_origin_allowlist.py::TestWebSocketGating -v --timeout=30 2>&1 | tail -15`
- `cd /home/cprch/projects/the-one && pytest -q --ignore=tests/browser --timeout=120 2>&1 | tail -5`
- `cd /home/cprch/projects/the-one && ruff check tests/ && ruff format --check tests/`

## Implementation Guidance

> **Note**: design review verified all line numbers below as of branch `flight/02-debrief-followups` HEAD. Re-grep right before the edit if the working tree has drifted.

1. **Re-grep `tests/test_origin_allowlist.py` to confirm**:
   - `TestWebSocketGating` class location (was L149)
   - `test_websocket_with_allowed_origin_accepts` end line (was L169)
   - `test_websocket_with_port_wildcard_origin_accepts` start line (was L171)
   - The new test inserts between these two.

2. **Add the test** — copy `test_websocket_with_allowed_origin_accepts` (L164-169) verbatim and modify:
   ```python
   def test_websocket_with_no_origin_passes(self) -> None:
       """Server-to-server WS clients (no Origin header) pass through.

       The middleware's WS gate is ``if origin and not self._is_allowed(origin)``
       — when ``Origin`` is absent, ``_extract_origin`` returns ``""`` and the
       truthy-check short-circuits. Locks in the pass-through so a future
       change to gate missing-Origin WS can't silently break non-browser
       clients.
       """
       app = _make_app(["http://127.0.0.1:8484"])
       with TestClient(app) as client:
           with client.websocket_connect("/ws") as ws:
               ws.send_text("hello")
               assert ws.receive_text() == "echo:hello"
   ```
   - Insertion point: between `test_websocket_with_allowed_origin_accepts` and `test_websocket_with_port_wildcard_origin_accepts` inside `TestWebSocketGating`.
   - Allowlist value (`["http://127.0.0.1:8484"]`) is irrelevant for this test (no Origin sent) but mirrors the existing tests for consistency.
   - Critical: do NOT pass `headers=` to `websocket_connect` — `TestClient` will not auto-inject `Origin` when no `headers` kwarg is provided.

3. **Verify**:
   - Run the new test in isolation first.
   - Then run `TestWebSocketGating` as a class to confirm no class-level interaction.
   - Then run the full suite to confirm no regression elsewhere.

## Edge Cases

- **`TestClient` may auto-set headers**: Starlette's `TestClient` does NOT auto-inject `Origin` for HTTP/WS unless explicitly passed via `headers=`. Verified by reading the existing `test_websocket_with_foreign_origin_closes_1008` (L150-162) which only sets `Origin` because it explicitly passes `headers={"Origin": ...}`.
- **No-Origin path passes through to the route handler**: the stub `/ws` route at L58-66 calls `await ws.accept()` immediately, then echoes. The new test's assertion `receive_text() == "echo:hello"` proves both pass-through (no 1008 close) AND that the route handler ran.

## Files Affected

- `tests/test_origin_allowlist.py` — 1 new test method (~15 lines) inside `TestWebSocketGating` class

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] New test passes in isolation
- [x] `TestWebSocketGating` class passes as a unit
- [x] Full pytest suite green (delta: +1 passed)
- [x] Ruff lint + format clean
- [x] Update flight-log.md with leg progress entry (note the `test_provider` happy-path "already-satisfied" finding)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md (Checkpoints AND Legs lists)
- [ ] DO NOT commit — deferred to flight close
