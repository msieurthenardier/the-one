# Leg: 01-streamable-http-non-cm-helper

**Status**: landed
**Flight**: [Lazy OAuth 2.1 + PKCE](../flight.md)

## Objective

Land `_open_streamable_http_transport_stack` and `_open_stdio_transport_stack` (symmetric) — non-CM helpers returning `(ClientSession, AsyncExitStack)`. Modify `_transport_connect` dispatcher in `the_one/mcp/client.py` to consume the new helpers internally via explicit `await stack.aclose()` in its `finally:` block. Existing `@asynccontextmanager connect_streamable_http` and `connect_stdio` functions stay UNCHANGED — preserve back-compat with their 1 + 9 = **10 prior async-CM callers** (citation-audit-verified). Add a control test (`test_direct_cross_task_still_warns`) locking the safety-net's cross-task contract scope. **The mechanism is SPECULATIVE — empirical retirement of the F4-HAT-Finding-#1 warning is verified at L6 HAT (Tier-1 in-repo OAuth fixture), NOT at this leg's unit-test layer.** If L6 HAT shows the warning still fires under F4-pool routing, L1's mechanism is wrong; revert in a follow-up flight.

## Context

### Flight design decisions

- **§3 (F2-known-issue retirement scope)**: per Architect cycle-1 H2 reframe — retired ONLY for the F4-pool-routed path. Direct `MCPClient(source)` cross-task disconnect outside the pool STILL hits the cross-task safety net swallow. The F4 pool's `_entry_worker` runs disconnect on the same task as connect; combined with this leg's dispatcher rewrite, the dispatcher's exit chain has one fewer the-one-owned generator layer.
- **§5 (mechanism — cycle-1 H3 corrected; cycle-2 stake-test deferred)**: the SDK's `streamable_http_client` and `stdio_client` are themselves `@asynccontextmanager`-decorated (verified via `__wrapped__` introspection). Total `@asynccontextmanager` layers in the dispatcher's exit chain:
  - **OLD**: dispatcher (the-one) + `connect_streamable_http`/`connect_stdio` (the-one) + SDK transport CM = **3 generator layers**
  - **NEW**: dispatcher (the-one) + SDK transport CM = **2 generator layers** (AsyncExitStack runs `__aexit__` on registered CMs non-generatorically; the SDK CM is still entered via `enter_async_context` and is itself a generator)
  - The reduction is 3→2, NOT 2→1. The mechanism MAY help (one fewer the-one-owned layer in the generator-exit walkback) but is **speculative — there is no plausible unit-test that empirically verifies retirement** (cycle-2 reviewer found the F4 HAT path requires a real MCP subprocess that completes `initialize()` so disconnect runs; `/bin/cat` causes initialize to fail before disconnect runs; mock-based mocks miss the SDK's anyio task group internals).
  - **Empirical verification deferred to L6 HAT (Tier-1 in-repo OAuth fixture)**: the F5 HAT exercises the full streamable-HTTP + OAuth flow against an in-repo FastMCP-shaped server. The 5-step verification is extended (in flight.md §10) to assert NO `MCPClient transport close failed` log lines during the entire flow. If that assertion fails, L1's mechanism didn't help — file a follow-up flight that reverts L1's source changes and adds a Mission Known Issue carrying the F4 issue forward with a real diagnosis plan.

### Carries forward

- **F4 debrief R1 [Critical]**: F2-known-issue follow-on. F5 owns it. This is the leg.
- **L1a's `TestAsyncExitStackContract`** stake-test probe pattern from F4 — extended here only with the control test (`test_direct_cross_task_still_warns`) to lock the contract scope. The integration stake-test idea was found vacuous in cycle-2 (initialize-fails-before-disconnect-runs); deferred to L6 HAT.
- **L2's bwrap-stderr translation in `connect_stdio`** — stays in the existing `@asynccontextmanager`'s `finally:` block (unchanged). The new `_open_stdio_transport_stack` helper places translation in `except BaseException:` clause. **errbuf is read AFTER `await stack.aclose()` (cycle-2 M3 fix)** so the SDK's `stdio_client.__aexit__` has flushed stderr.
- **F4 HAT empirical baseline (Finding #1)**: `RuntimeError: generator didn't stop` fires on every disconnect, including under `shutdown_drain()` against the real `mcp-server-fetch` subprocess. The L6 HAT extends to capture caplog records during the OAuth-flow 5-step path.

### Why this leg lands second (after L0)

- **L0 prerequisite**: scaffolds the OAuth package (no overlap).
- **Lands BEFORE L2** so the OAuth refresh path (which always routes through the F4 pool) inherits the candidate clean dispatcher contract from day 1 — IF L1's mechanism actually works (verified at L6 HAT).
- **No load-bearing gate at this leg's unit-test layer**: ships speculatively. L6 HAT is the verification gate. If L6 HAT contradicts retirement, file a follow-up.

## Inputs

What exists before this leg runs:

- `the_one/mcp/transports/streamable_http.py::connect_streamable_http` `@asynccontextmanager`-decorated.
- `the_one/mcp/transports/stdio.py::connect_stdio` `@asynccontextmanager`-decorated; L2's bwrap-stderr translation in `finally:` block.
- `the_one/mcp/client.py::_transport_connect` `@asynccontextmanager`-decorated; nested `async with` over the existing CM-shaped transport functions.
- `the_one/mcp/client.py::MCPClient` post-L1a uses `self._transport_stack: AsyncExitStack | None`.
- **Citation audit (per `leg/SKILL.md` Phase 2 item 7) — verified at L1 design 2026-05-07**:
  - `connect_streamable_http` direct `async with` callers: **1** (`tests/test_mcp_client.py:1511`).
  - `connect_stdio` direct `async with` callers: **9** (`tests/test_mcp_stdio_sandbox.py` lines 160, 215, 255, 293, 334, 364, 409, 453, 485).
  - `_transport_connect`: ~40 monkeypatch references; substitution targets, not direct async-with callers.
- `tests/test_mcp_client.py::TestAsyncExitStackContract` exists with the L1a probe pattern + helper `_anyio_backed_transport_cm`.
- **Test counts at L1-start (post-L0, per L0 Developer's verified actuals — cycle-1 H2 + cycle-2 H2 corrected)**:
  - F5-MCP subset: **118 tests**.
  - Full project suite: **1254 selected = 1251 passed + 2 skipped + 1 pre-existing failure** (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`; cross-test pool state leakage; out of scope for L1).

## Outputs

What exists after this leg completes:

- **`the_one/mcp/transports/streamable_http.py`** gains `_open_streamable_http_transport_stack(source, *, http_client=None) -> tuple[ClientSession, AsyncExitStack]` — plain `async def`; constructs `AsyncExitStack`; enters httpx + `streamable_http_client` + `ClientSession`; returns `(session, stack)`; on `BaseException` during entry, runs `await stack.aclose()` and re-raises.

- **`the_one/mcp/transports/stdio.py`** gains `_open_stdio_transport_stack(source) -> tuple[ClientSession, AsyncExitStack]` — same shape; L2's bwrap-stderr translation in `except BaseException:` clause. **`errbuf = None` initialized BEFORE try block (cycle-1 M1 fix); except clause guards with `if errbuf is not None:`. errbuf is read AFTER `await stack.aclose()` (cycle-2 M3 fix) so SDK's `stdio_client.__aexit__` has flushed stderr.**

- **`the_one/mcp/client.py::_transport_connect`** body modified to consume the new non-CM helpers via `(session, stack) = await _open_*_transport_stack(source)` then `try: yield session; finally: await stack.aclose()`. Outward `@asynccontextmanager` shape preserved. Dead `yield  # type: ignore[unreachable]` line at `client.py:88` removed.

- **`tests/test_mcp_client.py::TestAsyncExitStackContract`** gains 1 NEW control test:
  - `test_direct_cross_task_still_warns` — explicit cross-task disconnect (`asyncio.create_task(c.disconnect())`) STILL produces the warning via the safety net. Uses `_anyio_backed_transport_cm` (mock — sufficient because the test exercises the CROSS-TASK safety net's `except Exception` swallow, which IS independent of the SDK transport stack). Locks the contract scope: F2-known-issue retirement applies ONLY to F4-pool-routed disconnects (same-task); direct outside-pool cross-task usage continues to hit the safety net.

- **NO integration stake-test in this leg.** Cycle-2 found the `/bin/cat` approach vacuous (initialize-fails-before-disconnect-runs path bypasses the warning). User picked A.2 (defer to L6 HAT). Implementation note in flight log captures this decision.

- **`flight.md §10 (HAT)`** updated to add F2-known-issue verification as a 6th step (or extension to the 5-step Tier-1 list): caplog assertion that NO `MCPClient transport close failed` log records appear during the lazy 401 → consent → token-exchange → resumed-tool-call → refresh-rotation sequence. If the assertion fails, L1's mechanism didn't help — file a follow-up flight that reverts L1 source changes.

- **`the_one/mcp/README.md §3`** updated with cycle-1 H3-correct + cycle-2 honest wording:
  > **F5 L1 update (2026-05-07)**: the dispatcher's body has been rewritten to remove the the-one-owned `@asynccontextmanager` wrapper layer (`connect_streamable_http` / `connect_stdio`) from the dispatcher's exit chain. The dispatcher itself remains `@asynccontextmanager`-decorated (one layer); the SDK's `streamable_http_client` / `stdio_client` ALSO remain `@asynccontextmanager`-decorated (one layer); these two are now composed via `AsyncExitStack` instead of via nested `async with`. Total layer reduction: 3 → 2. **This MAY retire the F4-HAT-Finding-#1 `RuntimeError: generator didn't stop` warning for F4-pool-routed (same-task) disconnects.** Empirical verification is at the F5 L6 HAT (Tier-1 in-repo OAuth fixture) — caplog assertion checks for absence of `MCPClient transport close failed` records during the 5-step OAuth-flow lifecycle. If that assertion fails, L1's mechanism didn't help; the F2-known-issue is reinstated as Mission Known Issue and a follow-up flight diagnoses the root cause. Cross-task disconnect on a direct `MCPClient(source)` instance OUTSIDE the F4 pool STILL fires the safety-net swallow — that contract is preserved (locked by `tests/test_mcp_client.py::TestAsyncExitStackContract::test_direct_cross_task_still_warns`).

- **`flight.md` L1 description** ("1+8 prior callers") corrected to "1+9 prior callers" (cycle-1 low fix; matches grep).

- F4 prior tests pass UNMODIFIED. The 1 + 9 = 10 prior async-CM direct callers continue to work because `connect_streamable_http` and `connect_stdio` retain their `@asynccontextmanager` shape unchanged. The ~40 `_transport_connect` monkeypatch references continue to work because the dispatcher's outward shape is unchanged.

- **Test count target (cycle-1 H2 + cycle-2 H2 corrected)**:
  - F5-MCP subset: 118 → 119 (+1 control test in `test_mcp_client.py`).
  - Full project suite: 1254 selected → 1255 collected; 1252 passed + 2 skipped + 1 pre-existing failure (carried from L0).

## Acceptance Criteria

- [ ] `the_one/mcp/transports/streamable_http.py::_open_streamable_http_transport_stack` exists with `async def ... -> tuple[ClientSession, AsyncExitStack]:` signature; NO `@asynccontextmanager` decorator. On entry-failure, runs `await stack.aclose()` and re-raises.
- [ ] `the_one/mcp/transports/stdio.py::_open_stdio_transport_stack` exists with same shape. **`errbuf = None` initialized BEFORE try block** (cycle-1 M1). **`errbuf.read()` happens AFTER `await stack.aclose()`** (cycle-2 M3) so SDK's stdio_client `__aexit__` has flushed stderr. L2's bwrap-stderr translation in except clause; raises translated `MCPSandboxError` on bwrap-prefix failures or unmodified original on non-bwrap failures.
- [ ] `the_one/mcp/client.py::_transport_connect` body modified per §Outputs. Outward `@asynccontextmanager` shape preserved. Dead `yield  # type: ignore[unreachable]` at `client.py:88` removed.
- [ ] **`@asynccontextmanager connect_streamable_http` and `connect_stdio` are UNCHANGED** — verified by `git diff <l1-start-sha>` showing ONLY the new `_open_*` helpers added. The 10 prior async-CM callers continue to work without test modifications.
- [ ] Control test passes: `tests/test_mcp_client.py::TestAsyncExitStackContract::test_direct_cross_task_still_warns` PASSES — explicit cross-task disconnect outside F4 pool produces the safety-net warning. Locks contract scope.
- [ ] Cumulative test count per cycle-2 H2 corrected baseline:
  - F5-MCP subset: 118 → 119 (passes); 1 skipped (EPERM #6c).
  - Full project suite: 1255 collected, 1252 passed + 2 skipped + 1 pre-existing failure (`test_acquire_lazy_spawn_creates_worker_and_returns_client`; carried from L0; not introduced by L1; not a regression).
- [ ] `ruff check the_one/mcp/transports/ the_one/mcp/client.py tests/test_mcp_client.py` clean.
- [ ] `the_one/mcp/README.md §3` updated with cycle-1 H3-correct + cycle-2 honest wording per §Outputs.
- [ ] `flight.md` L1 description "1+8" → "1+9" prior async-CM callers fix applied.
- [ ] **`flight.md §10 HAT description extended** to include caplog assertion that NO `MCPClient transport close failed` log records appear during the Tier-1 5-step sequence. This is the empirical verification gate; if it fails, file a follow-up flight to revert L1.
- [ ] Flight log Leg Progress entry added: citation-audit confirmation (10 prior callers preserved), test-count delta, deferred-verification framing.

## Verification Steps

1. **New helpers exist with correct signatures**: `grep -n "^async def _open_streamable_http_transport_stack\|^async def _open_stdio_transport_stack" the_one/mcp/transports/*.py` returns one match per file; signatures end with `-> tuple[ClientSession, AsyncExitStack]:`.
2. **`errbuf` init order**: `grep -B 2 "errbuf = stack.enter_context" the_one/mcp/transports/stdio.py` shows `errbuf = None` line BEFORE the `errbuf = stack.enter_context(...)` line.
3. **`errbuf` read AFTER aclose**: `grep -A 12 "except BaseException" the_one/mcp/transports/stdio.py` shows `await stack.aclose()` BEFORE `errbuf.seek(0); errbuf.read()` in `_open_stdio_transport_stack`'s except clause.
4. **Dispatcher body consumes new helpers**: `grep -A 12 "async def _transport_connect" the_one/mcp/client.py` shows the new shape.
5. **Dead yield removed**: `grep -c "type: ignore\[unreachable\]" the_one/mcp/client.py` returns 0.
6. **Existing transport functions unchanged**: `git diff <l1-start-sha> -- the_one/mcp/transports/streamable_http.py | grep -E '^[-+]' | grep -v "^[+-]async def _open_\|^+[^+]\|^-[^-]" | wc -l` returns 0. Same for `stdio.py`.
7. **Control test (contract scope)**: `docker compose exec the-one pytest tests/test_mcp_client.py::TestAsyncExitStackContract::test_direct_cross_task_still_warns -v --log-cli-level=WARNING --timeout=30` returns 1 passed; output DOES include `MCPClient transport close failed`.
8. **Prior callers unaffected**: `docker compose exec the-one pytest tests/test_mcp_client.py::TestConnectStreamableHttpProduction tests/test_mcp_stdio_sandbox.py -q --timeout=30` shows existing pass counts unchanged.
9. **Cumulative regression vs corrected baseline**: F5-MCP subset 119 collected, 118 passed + 1 skipped. Full suite: 1255 collected, 1252 passed + 2 skipped + 1 pre-existing failure (carried from L0).
10. **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/transports/ the_one/mcp/client.py tests/test_mcp_client.py` returns 0 exit.
11. **README §3 updated**: `grep -A 8 "F5 L1 update" the_one/mcp/README.md` shows the new paragraph with "3 → 2" reduction language AND the "verified at L6 HAT" framing AND the test-name reference for the control test.
12. **flight.md "1+9" fix**: leg description text in flight.md no longer says "1+8".
13. **flight.md §10 extended**: HAT Tier-1 description includes the caplog-no-warning-records assertion as part of the 5-step sequence.
14. **Flight log updated**: Leg Progress entry exists with status `landed`, timestamps, citation-audit confirmation, test-count delta, deferred-verification framing.

## Implementation Guidance

1. **Capture L1-start commit SHA**: `git rev-parse HEAD`. Note value.

2. **Add `_open_streamable_http_transport_stack` to `the_one/mcp/transports/streamable_http.py`** (at module-end). Imports: ensure `from contextlib import AsyncExitStack` is present.

   ```python
   async def _open_streamable_http_transport_stack(
       source: MCPSource,
       *,
       http_client: httpx.AsyncClient | None = None,
   ) -> tuple[ClientSession, AsyncExitStack]:
       """Open an entered ClientSession + return the AsyncExitStack that owns it.

       SAME-TASK CONTRACT: caller MUST drive ``stack.aclose()`` from the same task.
       The F4 pool's ``_entry_worker`` wraps everything in one task naturally.

       The dispatcher (``_transport_connect``) consumes this helper. Per F5 L1
       speculative-mechanism framing: this MAY retire the F4-HAT-Finding-#1
       warning for F4-pool-routed (same-task) disconnects by collapsing the
       dispatcher's the-one-owned ``@asynccontextmanager`` wrapper layer.
       Empirical verification at F5 L6 HAT.

       The existing ``connect_streamable_http`` ``@asynccontextmanager`` continues
       to exist for back-compat with its 1 prior async-CM caller.
       """
       url: str = source.config["url"]
       headers = build_request_headers(source)

       effective_client = http_client
       if effective_client is None:
           effective_client = _test_http_client_override

       stack = AsyncExitStack()
       try:
           if effective_client is not None:
               effective_client.headers.update(headers)
               read, write, _get_session_id = await stack.enter_async_context(
                   streamable_http_client(url, http_client=effective_client)
               )
           else:
               owned_client = await stack.enter_async_context(
                   httpx.AsyncClient(
                       headers=headers,
                       follow_redirects=True,
                       timeout=httpx.Timeout(30.0),
                   )
               )
               read, write, _get_session_id = await stack.enter_async_context(
                   streamable_http_client(url, http_client=owned_client)
               )
           session = await stack.enter_async_context(ClientSession(read, write))
           return session, stack
       except BaseException:
           await stack.aclose()
           raise
   ```

3. **Add `_open_stdio_transport_stack` to `the_one/mcp/transports/stdio.py`** (at module-end). **Note `errbuf = None` BEFORE try (cycle-1 M1) AND `errbuf.read()` AFTER `stack.aclose()` (cycle-2 M3)**:

   ```python
   async def _open_stdio_transport_stack(
       source: MCPSource,
   ) -> tuple[ClientSession, AsyncExitStack]:
       """Open an entered ClientSession over (sandboxed) stdio transport.

       SAME-TASK CONTRACT: caller MUST drive ``stack.aclose()`` from the same task.

       L2's bwrap-stderr translation in ``except BaseException:`` clause. Read
       order matters: ``stack.aclose()`` runs FIRST so SDK's
       ``stdio_client.__aexit__`` flushes the subprocess stderr; THEN read
       errbuf and pattern-match. Mirrors the existing ``connect_stdio``
       ``finally:`` block's invariant.

       The existing ``connect_stdio`` ``@asynccontextmanager`` continues to exist
       for back-compat with its 9 prior async-CM callers.
       """
       params = _build_stdio_params(source)
       sandboxed = not _sandbox_disabled_for_tests()
       stack = AsyncExitStack()
       errbuf = None  # cycle-1 M1: init before try so except clause guard is safe
       try:
           if sandboxed:
               errbuf = stack.enter_context(
                   tempfile.SpooledTemporaryFile(
                       mode="w+", encoding="utf-8", errors="replace"
                   )
               )
               read, write = await stack.enter_async_context(
                   stdio_client(params, errlog=errbuf)
               )
           else:
               read, write = await stack.enter_async_context(stdio_client(params))
           session = await stack.enter_async_context(ClientSession(read, write))
           return session, stack
       except BaseException as exc:
           # cycle-2 M3: aclose FIRST so SDK's stdio_client.__aexit__ flushes
           # the subprocess stderr; THEN read errbuf and pattern-match.
           # Note: stack.aclose() in an except clause cannot raise here because
           # AsyncExitStack handles its own teardown; even if it fails the
           # original exception (in `exc`) is what we re-raise below.
           await stack.aclose()
           stderr_text = ""
           if errbuf is not None:
               try:
                   errbuf.seek(0)
                   stderr_text = errbuf.read()
               except Exception:
                   stderr_text = ""
           sandbox_err = _translate_bwrap_stderr(stderr_text)
           if sandbox_err is not None:
               raise sandbox_err from exc
           raise
   ```

   **Note re: errbuf access post-aclose**: `SpooledTemporaryFile` registered via `stack.enter_context(...)` is closed by `stack.aclose()`. Reading from a closed `SpooledTemporaryFile` may raise. The original `connect_stdio.finally` block achieves the read by NOT closing the file — it reads inside the SDK CM's `__aexit__` chain, where the file is still open. To preserve correctness, ALTERNATIVE pattern: pop errbuf out of the stack BEFORE aclose, read it, then close it explicitly. Apply this if `errbuf.read()` fails post-aclose:

   ```python
   except BaseException as exc:
       # Take ownership of errbuf so we can read it post-aclose.
       errbuf_owned = errbuf
       if errbuf_owned is not None:
           # Pop from the stack's callback list so aclose() doesn't close it
           # before we read. SpooledTemporaryFile's __exit__ closes the file.
           # We re-close it manually after reading.
           pass  # The stack.enter_context registers __exit__; AsyncExitStack
                 # doesn't expose deregister. We instead read the buffer after
                 # aclose() — which closes the SpooledTemporaryFile but leaves
                 # the in-memory bytes accessible via .read() if we capture
                 # before close. Tested empirically at implementation: if read
                 # fails post-aclose, we capture pre-aclose into a local var:
       captured_stderr = ""
       if errbuf is not None:
           try:
               errbuf.seek(0)
               captured_stderr = errbuf.read()
           except Exception:
               captured_stderr = ""
       await stack.aclose()
       sandbox_err = _translate_bwrap_stderr(captured_stderr)
       if sandbox_err is not None:
           raise sandbox_err from exc
       raise
   ```

   Implementer chooses based on empirical behavior: if reading errbuf BEFORE `aclose()` returns full stderr (because SDK's stdio_client wrote on its own __aexit__ which already ran via the failure path), the original-order works. If reading post-`aclose` works on `SpooledTemporaryFile` (some implementations allow reading the in-memory buffer post-close), the cycle-2 M3 order works. Pick the one that empirically captures the bwrap stderr; document in flight log.

4. **Modify `the_one/mcp/client.py::_transport_connect`** body:

   ```python
   @asynccontextmanager
   async def _transport_connect(source: MCPSource) -> AsyncIterator["ClientSession"]:
       """Dispatch on source.type. Outward shape preserved for test contract.

       Body uses non-CM transport helpers (introduced in F5 L1) + explicit
       ``await stack.aclose()`` in finally — collapses the the-one-owned
       ``@asynccontextmanager`` wrapper layer from the dispatcher's exit chain.
       MAY retire the F4-HAT-Finding-#1 warning for same-task (F4-pool-routed)
       disconnects; verified at F5 L6 HAT.
       """
       if source.type == "streamable-http":
           from the_one.mcp.transports.streamable_http import (
               _open_streamable_http_transport_stack,
           )
           session, stack = await _open_streamable_http_transport_stack(source)
       elif source.type == "stdio":
           from the_one.mcp.transports.stdio import _open_stdio_transport_stack
           session, stack = await _open_stdio_transport_stack(source)
       else:
           raise MCPClientError(f"unknown MCP transport type: {source.type!r}")
       try:
           yield session
       finally:
           await stack.aclose()
   ```

   Remove the dead `yield  # type: ignore[unreachable]  # noqa: F821` line.

5. **Add the control test to `tests/test_mcp_client.py::TestAsyncExitStackContract`**:

   ```python
       async def test_direct_cross_task_still_warns(
           self, monkeypatch, mock_session, caplog
       ) -> None:
           """F5 L1: control test — direct cross-task disconnect (outside
           pool routing) STILL produces the warning via the safety net.

           Locks the contract scope: F2-known-issue retirement applies only
           to F4-pool-routed (same-task) disconnects. Direct ``MCPClient(source)``
           usage with cross-task disconnect continues to hit the safety net swallow.

           Mock-based (uses ``_anyio_backed_transport_cm``) is sufficient here
           because the test exercises the cross-task safety-net's ``except Exception``
           clause, which is independent of the SDK transport stack.
           """
           monkeypatch.setattr(
               client_mod,
               "_transport_connect",
               lambda source: _anyio_backed_transport_cm(mock_session),
           )

           caplog.set_level(logging.WARNING, logger="the_one.mcp.client")
           client = MCPClient(_stdio_source())
           await client.connect()  # connect on test task (host task)

           # Cross-task disconnect — exits the cancel scope on a different
           # task; anyio's guard fires; safety-net swallow catches it.
           disconnect_task = asyncio.create_task(client.disconnect())
           await disconnect_task

           messages = [r.getMessage() for r in caplog.records]
           assert any(
               "MCPClient transport close failed" in m for m in messages
           ), f"expected cross-task warning; got: {messages}"
           assert client.is_alive is False
   ```

6. **Update `the_one/mcp/README.md §3`** with the cycle-1 H3-correct + cycle-2 honest wording per §Outputs.

7. **Fix `flight.md` L1 description**: change "1+8" → "1+9" prior async-CM callers.

8. **Extend `flight.md §10 HAT Tier-1 description`** to add F2-known-issue verification: append a 6th step (or add to an existing step) — "**(F5 L1 verification, deferred from unit-test layer)**: throughout the 5-step sequence, capture pytest caplog records at WARNING level for `the_one.mcp.client`. Assert that NO record matches `MCPClient transport close failed`. If any do, L1's mechanism didn't help — file a follow-up flight that reverts `_open_*_transport_stack` helpers and the dispatcher rewrite, and re-add the F2-known-issue to mission Known Issues with a real diagnosis plan."

9. **Run lint + regression**:
   ```bash
   docker compose exec the-one ruff check the_one/mcp/transports/ the_one/mcp/client.py tests/test_mcp_client.py
   docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_pool.py tests/test_mcp_oauth_errors.py -q --timeout=30
   ```
   Expect F5-MCP subset 119 collected, 118 passed + 1 skipped. Full suite ~1255 collected, 1252 passed + 2 skipped + 1 pre-existing failure carried from L0.

10. **Update flight log**: append Leg Progress entry with status `landed`, ISO 8601 UTC timestamps, citation-audit confirmation, test-count delta, deferred-verification framing per A.2 design call. Document the errbuf-read-order-vs-aclose decision (whichever pattern empirically captures bwrap stderr in the chosen implementation).

## Edge Cases

- **L6 HAT verification fails**: file a follow-up flight that reverts L1's `_open_*` helpers + dispatcher rewrite + README §3 update. Re-add F2-known-issue to mission Known Issues with a real diagnosis plan. F5 itself ships even if L1 ends up reverted (the OAuth implementation in L2-L5 doesn't depend on L1's mechanism working — just on the dispatcher and transports being functional).
- **`errbuf.read()` post-`stack.aclose()` fails**: alternate pattern in step 3 captures stderr BEFORE aclose. Implementer picks empirically; documents in flight log.
- **Direct outside-pool usage**: covered by `test_direct_cross_task_still_warns` — control test confirms safety net still fires for cross-task `MCPClient(source)` usage.
- **Tests that monkeypatch `_transport_connect`**: continue to work (~40 such tests).

## Files Affected

- `the_one/mcp/transports/streamable_http.py` — add `_open_streamable_http_transport_stack` (~50 LOC).
- `the_one/mcp/transports/stdio.py` — add `_open_stdio_transport_stack` with errbuf-init + read-order fixes (~58 LOC).
- `the_one/mcp/client.py` — modify `_transport_connect` body; remove dead yield (~12 LOC change).
- `tests/test_mcp_client.py` — add `test_direct_cross_task_still_warns` (~30 LOC).
- `the_one/mcp/README.md` — add F5 L1 update paragraph to §3 (~10 LOC).
- `missions/07-mcp-integration/flights/05-oauth-pkce-remote-mcp/flight.md` — fix "1+8"→"1+9"; extend §10 HAT description with F2-known-issue caplog assertion (~5 LOC).
- `missions/07-mcp-integration/flights/05-oauth-pkce-remote-mcp/flight-log.md` — append Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] F5-MCP subset: 119 collected, 118 passed + 1 skipped; full suite: 1255 collected, 1252 passed + 2 skipped + 1 pre-existing failure (carried from L0)
- [ ] `ruff check` clean
- [ ] Citation-audit confirmation in flight log: 10 prior async-CM callers preserved
- [ ] `the_one/mcp/README.md §3` updated with cycle-1 H3-correct + cycle-2 honest wording
- [ ] `flight.md` L1 description "1+9" fix applied
- [ ] `flight.md §10` Tier-1 HAT description extended with F2-known-issue caplog assertion (verification gate deferred from this leg)
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

**Per `leg/SKILL.md` Phase 2 item 7**: 6 citations verified at L1 design (2026-05-07).

- `the_one/mcp/transports/streamable_http.py::connect_streamable_http` — `@asynccontextmanager`. **1 prior async-CM caller**: `tests/test_mcp_client.py:1511`. Will NOT be modified.
- `the_one/mcp/transports/stdio.py::connect_stdio` — `@asynccontextmanager`. **9 prior async-CM callers**: `tests/test_mcp_stdio_sandbox.py` lines 160, 215, 255, 293, 334, 364, 409, 453, 485. Will NOT be modified.
- `the_one/mcp/client.py::_transport_connect` — `@asynccontextmanager`. ~40 monkeypatch references. Body modified; outward shape preserved.
- `the_one/mcp/client.py:88` — dead `yield` line. Will be removed.
- `the_one/mcp/README.md §3` — "AsyncExitStack alone does NOT solve cross-task disconnect" line. Will be amended (NOT contradicted).
- **SDK fact verified at cycle-1 review**: `mcp.client.streamable_http.streamable_http_client` AND `mcp.client.stdio.stdio_client` are themselves `@asynccontextmanager`-decorated. Layer reduction is 3→2.

**New-symbol audit**: `_open_streamable_http_transport_stack` and `_open_stdio_transport_stack` — 0 prior callers (verified via grep at L1 design).
