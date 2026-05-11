# Leg: 01-connect-401-translation

**Status**: completed
**Flight**: [Cleanup + connect-time 401 translation](../flight.md)

## Objective

Extend `MCPClient.connect()` with a nested innermost `try/except*` clause that translates `OAuthFlowError` and `OAuthTokenError` raised during `session.initialize()` to `MCPAuthRequired` — closing the F6.5 Design Decision §3 deferral and completing the auth-pending discriminator surface across both `connect` and `list_tools`.

## Context

- Origin: F6.5 Design Decision §3 explicitly deferred connect-time 401 widening; F6.5 L2 landed the `list_tools` translation pattern; this leg lands the structurally-equivalent piece for `connect`.
- Per flight Design Decision §2: this is an **ADD-only** change. The existing 401-via-`BaseExceptionGroup` walk at `client.py:270-335` (F6 A5) already handles HTTPStatusError 401s and is UNCHANGED. The actual gap is the SDK auth-flow exception classes (`OAuthFlowError`, `OAuthTokenError`) which currently fall through to the generic `except (Exception, BaseExceptionGroup)` translator and emerge as `MCPConnectionError("...OAuthFlowError: ...")` instead of typed `MCPAuthRequired`.
- Per flight Design Decision §2: Python prohibits mixing `except` and `except*` in the same `try` block. The existing `except RuntimeError` clause (version-mismatch translation) at `client.py:240-243` cannot be modified; the new `except*` must nest inside its own innermost `try` block.
- Per flight Design Decision §2a: NO `except MCPAuthRequired: raise` guard is needed in `connect`. The outer `except (MCPClientError, NotImplementedError): raise` clause at `client.py:250-252` already propagates `MCPAuthRequired` (which extends `MCPClientError`) cleanly. The `list_tools` pattern at `client.py:517-518` needed the explicit guard because its outer `except McpError` would have re-wrapped the auth signal; `connect` does not have that asymmetric outer clause.
- Per flight Design Decision §3: post-F6.6, the `CancelledError` block at `client.py:253-269` legitimately fires only for non-OAuth, non-401 cancellation races (since F6.6 catches OAuth exceptions before they can propagate to the cancellation race). The "likely 401 Unauthorized or transport error" speculation in the message is no longer accurate — replace with "transport error or malformed initial response."
- L0 is `landed`; full unit suite is green modulo 3 pre-existing `test_mcp_sandbox_integration.py` bwrap regressions. L1 builds on a known-good baseline.

## Inputs

What exists before this leg runs:

- `the_one/mcp/client.py:25 — "from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError"` — imports already in place from F6.5 L2's `list_tools` translation; no new imports needed.
- `the_one/mcp/client.py:32 — "MCPAuthRequired,"` — already imported (alongside other `MCPClientError` subclasses) from `the_one.mcp.errors`.
- `the_one/mcp/client.py:237 — "self._session = session"` — assignment immediately preceding the `session.initialize()` call site.
- `the_one/mcp/client.py:238-243 — current shape:`
  ```python
  try:
      result = await session.initialize()
  except RuntimeError as e:
      m = _UNSUPPORTED_VERSION_RE.match(str(e))
      observed = m.group(1) if m else str(e)
      raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
  ```
- `the_one/mcp/client.py:250-252 — "except (MCPClientError, NotImplementedError): … raise"` — the outer guard that propagates `MCPAuthRequired` (since it extends `MCPClientError`) without rewrapping. This is why §2a says no explicit `except MCPAuthRequired: raise` guard is needed inside the new `except*` block's enclosing structure.
- `the_one/mcp/client.py:253-269 — current `except asyncio.CancelledError as e:` block:`
  ```python
  except asyncio.CancelledError as e:
      # F6 A5: SDK's anyio task-group cleanup chain after a 401 (or
      # other transport-level failure) ends with the surrounding task
      # cancelled. Calling _cleanup_after_failed_connect from this
      # path re-triggers the cross-task cancel-scope guard inside the
      # SDK and either hangs or re-raises CancelledError. Abandon the
      # transport stack reference (leak the partial connection — GC
      # + process shutdown will clean up) and translate to
      # MCPConnectionError so MCPToolProvider's class #2 graceful-
      # degrade catches it. Do NOT await further cleanup.
      self._transport_stack = None
      self._session = None
      raise MCPConnectionError(
          f"MCP connect failed: cancelled during initialize "
          f"(cross-task cleanup deadlock; original cause likely "
          f"401 Unauthorized or transport error): {e}"
      ) from e
  ```
- `the_one/mcp/client.py:270-335 — "except (Exception, BaseExceptionGroup) as e:"` and the inner `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` 401-walk → `raise MCPAuthRequired(...)` at line 327 — UNCHANGED by this leg.
- `the_one/mcp/client.py:467-512 — list_tools' inner `try/except*` pattern from F6.5 L2`:
  ```python
  try:
      result = await self._session.list_tools()
  except* (OAuthFlowError, OAuthTokenError):
      raise MCPAuthRequired(
          source_id=self.source.id,
          resource_metadata_url=None,
          consent_url=None,
      ) from None
  except* httpx.HTTPStatusError as eg:
      ...
  ```
  This is the source-of-truth pattern; the OAuth `except*` clause is what L1 mirrors (NOT the `httpx.HTTPStatusError` `except*` clause — that's already covered by the BaseExceptionGroup walk in `connect`'s outer block).
- `tests/test_mcp_client.py:160 (in patch_transport fixture) — "Returns a callable: patch_transport() uses mock_session"` — the established test fixture for installing a mock transport. Use this to mock `session.initialize` and assert connect-time exception translation without spinning up real transports.
- `tests/test_mcp_client.py:288 — "class TestMCPClientLifecycle:"` — the existing test class that owns connect-time tests. New L1 tests append to this class to follow project convention.
- `tests/test_mcp_client.py:416-450 — "test_connect_cancelled_error_translates_to_connection_error"` — exists and asserts `"cancelled during initialize"` substring (line 444) and the message contains "likely 401 Unauthorized or transport error" by implication. This test's assertion MUST be updated to match the new message text (see Acceptance Criteria below).
- L0 landed: `Object.assign(window.App, {…})` exposes `areas: order`; `tests/test_streamable_http_transport.py` exists; `tests/test_mcp_pool.py` has the synthetic-csid test; `the_one/mcp/oauth/handlers.py` docstring documents the synthetic-csid pattern; `CLAUDE.md` describes the Test connection button.
- Branch `flight/6_6-cleanup-and-connect-401` working tree contains L0's uncommitted changes (deferred batch commit per skill protocol).

## Outputs

What exists after this leg completes:

- `the_one/mcp/client.py::MCPClient.connect` — the `try: result = await session.initialize() except RuntimeError ...` structure at lines 238-243 is restructured to wrap `session.initialize()` in a NEW innermost `try/except*` block that catches `(OAuthFlowError, OAuthTokenError)` and raises `MCPAuthRequired`. The existing `except RuntimeError` block stays in place at the outer try level. ~12 LOC added.
- `the_one/mcp/client.py::MCPClient.connect` — the `except asyncio.CancelledError` block's error message at lines 265-269 is updated to drop "401 Unauthorized" speculation per Design Decision §3. New text: "transport error or malformed initial response" (instead of "401 Unauthorized or transport error"). ~3 LOC of message text changed.
- `tests/test_mcp_client.py::TestMCPClientLifecycle` — three new tests appended:
  - `test_connect_oauth_flow_error_raises_mcp_auth_required` — `mock_session.initialize` raises `OAuthFlowError`; assert `MCPAuthRequired` raised with `source_id == source.id`, `resource_metadata_url is None`, `consent_url is None`.
  - `test_connect_oauth_token_error_raises_mcp_auth_required` — same shape for `OAuthTokenError`.
  - `test_connect_oauth_error_in_exception_group_raises_mcp_auth_required` — `mock_session.initialize` raises `BaseExceptionGroup("test", [OAuthFlowError(...)])`; verify `except*` matches grouped exceptions too.
- `tests/test_mcp_client.py::test_connect_cancelled_error_translates_to_connection_error` — assertion at line 444 updated to match the new message text (drops the `likely 401` substring).
- `the_one/mcp/_pool.py::_entry_worker` — UNCHANGED. `MCPAuthRequired` extends `MCPClientError` extends `Exception`, so the existing `except BaseException as exc:` catch (line 210) stores `MCPAuthRequired` in `entry.failure` and `MCPToolProvider.get_tools_for_agent`'s graceful-skip clause (post-F6.5 L2) catches it cleanly.
- Flight log updated; flight checklist `Checkpoints::L1 landing` checked off.

## Acceptance Criteria

- [x] `the_one/mcp/client.py::MCPClient.connect` contains a nested innermost `try/except* (OAuthFlowError, OAuthTokenError):` block wrapping ONLY `session.initialize()`. The `except*` clause raises `MCPAuthRequired(source_id=self.source.id, resource_metadata_url=None, consent_url=None)` with `from None`.
- [x] The existing `except RuntimeError` clause for version-mismatch translation remains structurally outside the new `try/except*` (Python's no-mix-`except`-with-`except*` constraint preserved).
- [x] The existing `except (Exception, BaseExceptionGroup) as e:` block at lines 270-335 is UNTOUCHED — including its `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` 401-walk → `MCPAuthRequired` translation. Verify by `git diff client.py` showing zero changes in lines 270-335.
- [x] The `except asyncio.CancelledError` block's error message at lines 265-269 drops the "likely 401 Unauthorized" substring. New message is "MCP connect failed: cancelled during initialize (cross-task cleanup deadlock; original cause likely transport error or malformed initial response): {e}" (or equivalent wording that omits "401 Unauthorized" while preserving the cross-task-cleanup-deadlock context). The block's body otherwise unchanged.
- [x] `tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_flow_error_raises_mcp_auth_required` exists and passes. Test shape:
  - `mock_session.initialize = AsyncMock(side_effect=OAuthFlowError("test-flow-error"))`
  - `patch_transport(mock_session)`
  - `with pytest.raises(MCPAuthRequired) as exc_info: await client.connect()`
  - `assert exc_info.value.source_id == client.source.id`
  - `assert exc_info.value.resource_metadata_url is None`
  - `assert exc_info.value.consent_url is None`
- [x] `tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_token_error_raises_mcp_auth_required` exists and passes (identical shape, substituting `OAuthTokenError`).
- [x] `tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_error_in_exception_group_raises_mcp_auth_required` exists and passes. Verifies `except*` matches grouped exceptions:
  - `mock_session.initialize = AsyncMock(side_effect=BaseExceptionGroup("test", [OAuthFlowError("inner")]))`
  - `patch_transport(mock_session)`
  - `with pytest.raises(MCPAuthRequired): await client.connect()`
- [x] `tests/test_mcp_client.py::test_connect_cancelled_error_translates_to_connection_error` is updated: the assertion `assert "cancelled during initialize" in str(exc_info.value)` (line 444) stays — that substring survives. Add an assertion that the message does NOT contain "401" substring: `assert "401" not in str(exc_info.value)`. The test's docstring MAY be updated to reflect the post-F6.6 stance (CancelledError fires only for non-OAuth, non-401 cancellation races).
- [x] All existing `tests/test_mcp_client.py::TestConnect*` tests continue to pass UNMODIFIED (other than the one CancelledError assertion update).
- [x] Full unit suite passes: `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py -q` returns the same 3 pre-existing `test_mcp_sandbox_integration.py` bwrap failures and no new ones.
- [x] `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present` (L0 Test 3) continues to pass — proves `MCPAuthRequired` flowing through `_entry_worker`'s `except BaseException` catch is unchanged by L1.
- [x] `MCPToolProvider.get_tools_for_agent`'s graceful-skip-on-`MCPAuthRequired` clause (from F6.5 L2) continues to catch the new connect-time `MCPAuthRequired` flow. Verify by running any existing F6.5 L2 graceful-skip test post-L1; it must still pass.

## Verification Steps

How to confirm each criterion:

- **Structural check**: `grep -A 10 "self._session = session" the_one/mcp/client.py` should show the nested `try/except*` block immediately after the assignment, with `except* (OAuthFlowError, OAuthTokenError):` on its own line and the `MCPAuthRequired` raise inside.
- **Existing-block unchanged**: `git diff the_one/mcp/client.py` should show changes ONLY in lines 237-269 (new nested try + CancelledError message edit). Lines 270-335 (the `except (Exception, BaseExceptionGroup)` block) MUST show zero diff.
- **Run the new tests individually**:
  - `docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_flow_error_raises_mcp_auth_required -v --timeout 30`
  - `docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_token_error_raises_mcp_auth_required -v --timeout 30`
  - `docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_error_in_exception_group_raises_mcp_auth_required -v --timeout 30`
- **Run the updated CancelledError test**: `docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_cancelled_error_translates_to_connection_error -v --timeout 30`. Confirm pass.
- **Run the full TestConnect* surface**: `docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle -v --timeout 60`. Confirm all green.
- **Full unit suite**: `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py -q --timeout 120`. Confirm same 3 pre-existing failures, no new ones, no new test_mcp_client failures.
- **L0 test cross-check**: `docker compose exec the-one pytest tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present -v --timeout 30`. Confirm pass.
- **F6.5 L2 graceful-skip cross-check**: `grep -ln "graceful.*skip\|MCPAuthRequired" tests/test_mcp_tool_provider.py tests/test_*provider*.py 2>/dev/null` — locate the F6.5 L2 test that exercises `MCPToolProvider.get_tools_for_agent`'s graceful-skip clause; run it; confirm pass.

## Implementation Guidance

1. **Verify imports at `client.py:25,32`** — `OAuthFlowError`, `OAuthTokenError`, `MCPAuthRequired` are already imported per F6.5 L2's `list_tools` work. Confirm with `grep -n "OAuthFlowError\|MCPAuthRequired" the_one/mcp/client.py | head -5` BEFORE editing — if the imports were removed for some reason, re-add them.

2. **Edit `MCPClient.connect()` at `client.py:237-243`** — the change is a localized restructure inside the `async with asyncio.timeout(...)` block. Replace the current shape:

   ```python
   self._session = session
   try:
       result = await session.initialize()
   except RuntimeError as e:
       m = _UNSUPPORTED_VERSION_RE.match(str(e))
       observed = m.group(1) if m else str(e)
       raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
   ```

   with this shape:

   ```python
   self._session = session
   # F6.6 L1: nested innermost try wrapping ONLY session.initialize() so
   # the SDK's auth-flow exceptions (OAuthFlowError, OAuthTokenError) are
   # translated to MCPAuthRequired at the same structural level as the
   # F6.5 L2 list_tools pattern (client.py:~470). Python forbids mixing
   # `except` and `except*` in one try block; the existing `except
   # RuntimeError` clause for version-mismatch translation MUST stay at
   # the outer try level. The 401-via-HTTPStatusError walk in the outer
   # `except (Exception, BaseExceptionGroup)` block at lines 270-335 is
   # F6 A5 work and remains the path for transport-layer 401s; F6.6 only
   # adds the OAuth-exception path (which currently emerges from the SDK
   # at a different layer than HTTPStatusError).
   try:
       try:
           result = await session.initialize()
       except* (OAuthFlowError, OAuthTokenError):
           # SDK's auth flow failed during initialize (refresh / discovery
           # / DCR). Translate to MCPAuthRequired so MCPToolProvider's
           # graceful-skip path (post-F6.5 L2) catches it cleanly via
           # _pool._entry_worker's `except BaseException → entry.failure`
           # capture. resource_metadata_url and consent_url are None
           # because we don't have a WWW-Authenticate response at this
           # point — the auth flow failed before the server's challenge
           # could surface. F5's chat-path lazy-OAuth flow re-runs at
           # next tool call when the operator re-establishes credentials.
           raise MCPAuthRequired(
               source_id=self.source.id,
               resource_metadata_url=None,
               consent_url=None,
           ) from None
   except RuntimeError as e:
       m = _UNSUPPORTED_VERSION_RE.match(str(e))
       observed = m.group(1) if m else str(e)
       raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
   ```

   Note the indentation: the new innermost `try` is one level deeper than the existing `try`. Total LOC addition is ~12.

3. **Update the CancelledError message at `client.py:265-269`** — the current text is:

   ```python
   raise MCPConnectionError(
       f"MCP connect failed: cancelled during initialize "
       f"(cross-task cleanup deadlock; original cause likely "
       f"401 Unauthorized or transport error): {e}"
   ) from e
   ```

   Replace with:

   ```python
   raise MCPConnectionError(
       f"MCP connect failed: cancelled during initialize "
       f"(cross-task cleanup deadlock; original cause likely "
       f"transport error or malformed initial response): {e}"
   ) from e
   ```

   Single substring replacement: `"401 Unauthorized or transport error"` → `"transport error or malformed initial response"`.

   **Also update the docstring/comments at `client.py:254-263`** — the current text says "after a 401 (or other transport-level failure)" which contradicts the post-F6.6 narrowing (401s are now caught upstream by both the new `except*` block and the existing BaseExceptionGroup walk). Replace "after a 401 (or other transport-level failure)" with "after a non-OAuth, non-401 transport-level failure" (or equivalent wording that names the post-F6.6 invariant). Single-line tweak; keeps the comment honest.

4. **Update the `test_connect_cancelled_error_translates_to_connection_error` test at `tests/test_mcp_client.py:416-450`** — the assertion at line 444 (`assert "cancelled during initialize" in str(exc_info.value)`) stays. ADD a new assertion that "401" no longer appears in the message:

   ```python
   assert "401" not in str(exc_info.value)
   ```

   Place it immediately after the existing substring-lock assertion. Do NOT change the rest of the test body — `is_alive`, `_transport_stack`, `_session` assertions all hold post-F6.6.

5. **Add the three new tests** to `tests/test_mcp_client.py::TestMCPClientLifecycle`. **Anchor placement by test names, not line numbers**: insert the three new tests AFTER `test_connect_cancelled_error_translates_to_connection_error` and BEFORE `test_disconnect_idempotent`. Line numbers will shift as Test 1/2/3 land in sequence — the test-name anchors are stable. Use the same `patch_transport` + `mock_session` fixtures the existing tests use.

   **Test 1 — `test_connect_oauth_flow_error_raises_mcp_auth_required`**:

   ```python
   async def test_connect_oauth_flow_error_raises_mcp_auth_required(
       self, patch_transport, mock_session
   ) -> None:
       """F6.6 L1: OAuthFlowError raised inside session.initialize() translates
       to MCPAuthRequired with the standard auth-pending discriminator shape.
       Mirrors F6.5 L2's list_tools pattern at client.py:~470 against the
       same SDK exception surface, but at the connect-time entry point.
       """
       mock_session.initialize = AsyncMock(
           side_effect=OAuthFlowError("auth flow failed during initialize")
       )
       patch_transport(mock_session)
       client = MCPClient(_stdio_source())
       with pytest.raises(MCPAuthRequired) as exc_info:
           await client.connect()
       assert exc_info.value.source_id == client.source.id
       assert exc_info.value.resource_metadata_url is None
       assert exc_info.value.consent_url is None
   ```

   **Test 2 — `test_connect_oauth_token_error_raises_mcp_auth_required`**: identical shape, substitute `OAuthTokenError("token error during initialize")`.

   **Test 3 — `test_connect_oauth_error_in_exception_group_raises_mcp_auth_required`**: verifies `except*` matches grouped exceptions (the SDK's anyio-task-group-wrapping path):

   ```python
   async def test_connect_oauth_error_in_exception_group_raises_mcp_auth_required(
       self, patch_transport, mock_session
   ) -> None:
       """F6.6 L1: the SDK's anyio task-group can wrap OAuth exceptions in a
       BaseExceptionGroup; `except*` matches both bare and grouped shapes.
       Mirrors F6.5 L2's `except*` semantics at client.py:~477.
       """
       mock_session.initialize = AsyncMock(
           side_effect=BaseExceptionGroup(
               "auth-flow-group",
               [OAuthFlowError("inner auth-flow failure")],
           )
       )
       patch_transport(mock_session)
       client = MCPClient(_stdio_source())
       with pytest.raises(MCPAuthRequired) as exc_info:
           await client.connect()
       assert exc_info.value.source_id == client.source.id
   ```

   The `_stdio_source()` helper is the project's existing test-source factory (used by adjacent tests at lines 299, 313, etc.); reuse it without modification.

6. **Run the new tests** as itemized in Verification Steps. Each new test should pass in <0.1s. The `BaseExceptionGroup` test in particular validates the `except*` semantics — a regression that uses bare `except` instead of `except*` would fail this test specifically.

7. **Run the existing TestMCPClientLifecycle suite** to confirm no regressions: `docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle -v --timeout 60`. Pre-existing tests pass; the updated `test_connect_cancelled_error_translates_to_connection_error` passes with its new "401" not-in-message assertion.

8. **Run the full unit suite**: `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py -q --timeout 120`. Confirm only the 3 pre-existing `test_mcp_sandbox_integration.py` bwrap failures, no new ones.

9. **Cross-check L0 test**: `docker compose exec the-one pytest tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present -v --timeout 30`. The `_entry_worker`'s `except BaseException as exc: entry.failure = exc` catch handles `MCPAuthRequired` identically to the pre-L1 state — this test confirms.

10. **Cross-check F6.5 L2 graceful-skip path**: locate the F6.5 L2 test that exercises `MCPToolProvider.get_tools_for_agent`'s graceful-skip-on-`MCPAuthRequired` clause via `grep -ln "MCPAuthRequired" tests/`. Run it; pass confirms the new connect-time `MCPAuthRequired` flow is structurally compatible with the existing graceful-skip surface.

11. **Update flight log** — append an `### L1 — connect-401-translation` entry under `## Leg Progress` with: completion timestamp, the 3 new tests + 1 updated test summary, the production code change (~15 LOC), and the test counts. Do NOT commit; deferred to the post-review batch commit per skill protocol.

12. **Post-completion**: update this leg's status to `landed` (NOT `completed`). Do NOT check off this leg in `flight.md` yet (deferred to post-review commit). Do NOT signal `[COMPLETE:leg]`. DO signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`except*` semantics with bare exceptions**: `except* (OAuthFlowError, OAuthTokenError):` matches BOTH a bare `OAuthFlowError` raised directly AND an `OAuthFlowError` wrapped inside a `BaseExceptionGroup`. Test 1 covers the bare case; Test 3 covers the grouped case. If the SDK's auth module changes to always wrap exceptions, the tests catch it; if it changes to never wrap, the tests still catch it. The `except*` syntax is the right tool here precisely because the SDK's wrapping behaviour can vary.

- **`MCPAuthRequired` propagation past the outer except blocks**: the new `MCPAuthRequired` is raised from the new innermost `except*` block. It exits the inner `try` (no other catch matches), exits the outer `try` (the `except RuntimeError` doesn't match), then hits the OUTER except chain at `client.py:244+`. The first matching clause is `except (MCPClientError, NotImplementedError): … raise` at line 250-252. `MCPAuthRequired` extends `MCPClientError` (verified at `the_one/mcp/errors.py`), so this clause matches and re-raises cleanly via `raise`. No version of the message is constructed; the typed exception passes through. Per Design Decision §2a, no explicit `except MCPAuthRequired: raise` guard is needed because the inheritance + propagation order does the right thing already.

- **`asyncio.CancelledError` race with new translation**: post-F6.6, the order of evaluation when `session.initialize()` raises is:
  1. New innermost `except* (OAuthFlowError, OAuthTokenError)` — matches bare or grouped OAuth flow exceptions; raises `MCPAuthRequired`.
  2. Outer `except RuntimeError` — matches version-mismatch RuntimeErrors.
  3. Outer outer `except asyncio.TimeoutError` (line 244) — matches the `asyncio.timeout(...)` context manager's timeout fire.
  4. Outer outer `except (MCPClientError, NotImplementedError)` (line 250) — re-raises `MCPAuthRequired` and other typed errors.
  5. Outer outer `except asyncio.CancelledError` (line 253) — matches CancelledError, fires only for non-OAuth, non-401 races (since the new `except*` and the existing BaseExceptionGroup walk catch those before propagation).
  6. Outer outer `except (Exception, BaseExceptionGroup)` (line 270) — fallback, includes the existing 401-via-HTTPStatusError walk.
  This ordering is preserved by the new `try/except*` being NESTED, not flattened — flattening would break the `except RuntimeError` adjacency required by Python's no-mix syntax constraint.

- **Mock fixture limitations**: `patch_transport` installs a mock session that returns from `connect_streamable_http` / `connect_stdio` without going through real transport setup. The mock's `initialize` is the only part that matters for the OAuth-translation tests. If a future refactor changes `patch_transport`'s shape to require additional fields on the mock session, the new tests must adapt — but the current mock is sufficient (verified by adjacent tests like `test_connect_cancelled_error_translates_to_connection_error` at line 416 which uses the exact same fixture pattern).

- **`OAuthFlowError`/`OAuthTokenError` constructor signatures**: confirmed via the import at `client.py:25`. Both constructors accept a single positional message string. Tests use `OAuthFlowError("test message")` form. If the SDK's exception classes change constructor shape in a future SDK upgrade, the tests will fail at construction; that's an acceptable failure mode — surface the SDK breaking change at test-time.

- **Test name collision**: `test_connect_oauth_flow_error_raises_mcp_auth_required` doesn't currently exist in `tests/test_mcp_client.py` (verified via `grep -n test_connect tests/test_mcp_client.py | grep oauth` returning zero matches at L1 design time). No collision.

## Files Affected

- `the_one/mcp/client.py` — `MCPClient.connect()` body around lines 237-269: new innermost `try/except*` block; CancelledError message text update. ~15 LOC net addition.
- `tests/test_mcp_client.py::TestMCPClientLifecycle` — 3 new tests appended around line 451 (immediately after `test_connect_cancelled_error_translates_to_connection_error`); 1 existing test updated with one additional assertion. ~60 LOC net addition.
- `missions/07-mcp-integration/flights/06_6-cleanup-and-connect-401/flight-log.md` — append `### L1 — connect-401-translation` entry under `## Leg Progress`.
- `missions/07-mcp-integration/flights/06_6-cleanup-and-connect-401/legs/01-connect-401-translation.md` — status transitions to `landed` (NOT `completed`).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]` — F6.6 batches review and commit at flight close):**

- [x] All acceptance criteria verified (run each verification step; record pass/fail counts)
- [x] Tests passing: 3 new connect-translation tests; updated CancelledError test; all existing `TestMCPClientLifecycle` tests; full unit suite green modulo the 3 pre-existing bwrap failures
- [x] L0 cross-check passes: `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present`
- [x] F6.5 L2 graceful-skip cross-check passes
- [x] Update flight-log.md with an L1 progress entry under `## Leg Progress` (timestamps, deliverable summary, test counts, deviations if any)
- [x] Set this leg's status to `landed` (NOT `completed`) in the artifact header
- [x] Do NOT check off this leg in `flight.md` (deferred to post-review commit)
- [x] Do NOT update `flight.md` status (still `in-flight`)
- [x] Do NOT commit (deferred to post-review batch commit)
- [x] Signal `[HANDOFF:review-needed]`

## Citation Audit

12 citations verified against current code at leg design time:

- `the_one/mcp/client.py:25 — "from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError"` — verified at exact line; F6.5 L2 already imports both — OK.
- `the_one/mcp/client.py:32 — "MCPAuthRequired,"` — verified at exact line; imported with other `MCPClientError` subclasses — OK.
- `the_one/mcp/client.py:237 — "self._session = session"` — verified; immediately precedes the `session.initialize()` call site — OK.
- `the_one/mcp/client.py:238-243 — current try/except RuntimeError shape` — verified line-by-line; the `try: result = await session.initialize() except RuntimeError as e:` form matches the spec — OK.
- `the_one/mcp/client.py:250-252 — "except (MCPClientError, NotImplementedError):"` — verified; this is the propagation guard for typed errors including `MCPAuthRequired` — OK.
- `the_one/mcp/client.py:253-269 — "except asyncio.CancelledError as e:"` — verified; F6 A5 block with the speculation-message update target — OK.
- `the_one/mcp/client.py:265-269 — "MCP connect failed: cancelled during initialize ... 401 Unauthorized or transport error: {e}"` — verified at exact lines; the substring to replace is `"401 Unauthorized or transport error"` → `"transport error or malformed initial response"` — OK.
- `the_one/mcp/client.py:270-335 — "except (Exception, BaseExceptionGroup) as e:"` block — verified; UNCHANGED in this leg; the `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` 401-walk → `raise MCPAuthRequired(...)` at line 327 is the F6 A5 path — OK.
- `the_one/mcp/client.py:467-512 — list_tools' inner try/except* pattern from F6.5 L2` — verified; specifically `except* (OAuthFlowError, OAuthTokenError):` at line 477 raising `MCPAuthRequired` is the source-of-truth pattern this leg mirrors — OK.
- `tests/test_mcp_client.py:160 — "patch_transport fixture"` — verified at line 160; established test fixture for mocking transports — OK.
- `tests/test_mcp_client.py:288 — "class TestMCPClientLifecycle:"` — verified; the test class to append into — OK.
- `tests/test_mcp_client.py:416-450 — "test_connect_cancelled_error_translates_to_connection_error"` — verified; the assertion at line 444 (`assert "cancelled during initialize" in str(exc_info.value)`) is the substring lock; new assertion `assert "401" not in str(exc_info.value)` lands here — OK.
