# Leg: client-hardening

**Status**: completed
**Flight**: [Automatic negotiation of protocol 2026-07-28](../flight.md)

## Objective
Land the Flight 1 carry-forwards while the client is still on the initialize handshake:
- a shared failure classifier implementing DD5's matrix;
- the owner-task cancellation rule (DD6);
- an override-safe stale-token clear on Test connection (DD7);
- a plain error when a tool asks for input (DD8);
- the doctor gate proving `httpcore2` (DD11);
- the `_era.py` leaf module, which nothing reads yet (DD2);
- squawk 0199's documentation items (DD12).

The suite stays green, and `connect` still calls `session.initialize()`.

## Context
- **The design is the flight spec.** It is in `../flight.md`, DD2 and DD5-DD8, DD11 and DD12. Read it in full first; where this file and the flight spec disagree, the flight spec wins, and you report the disagreement in the flight log.
- **Leg 1 doesn't negotiate.** Negotiation is leg 2 (`auto-negotiation-core`). So DD5's row 3 (any -32022 / no shared revision) and DD8's modern-era input-required case are tested through **mock sessions** in this leg. Leg 2 adds real fixtures.
- **Interim state, logged in the flight log by this leg:**
  - `MCPVersionMismatch.pinned` still holds `_PINNED_PROTOCOL_VERSION`; it is renamed in leg 2.
  - The mismatch message names 2026-07-28 before the client offers it.
  - `_era.py` exists, but only `forget_era` is called, from the row 3 cells.
- **Background in the flight log:**
  - "Reconnaissance Report", items A3-A5, A9, A11, A12;
  - "Design Inputs from Reconnaissance";
  - both design-review cycles.

  The probe scripts are in the session scratchpad (`f2probe/`, `archprobe/`).
- **Out of scope:**
  - negotiation, version-gate changes and the constant rename (leg 2);
  - `api.py` probe and driver changes (leg 3), except DD7's Phase A clear, which is in this leg;
  - the probe docstring (leg 3).

## Inputs
- Worktree `~/projects/the-one-sortie-03`, branch `flight/02-auto-negotiation`, at `a203563`. Its `.venv` is synced from `uv.lock` (`mcp` 2.3.0). Never re-resolve dependencies.
- Baseline: `make test-unit` (plain mode) gives 6068 passed, 12 skipped, 0 failed.

## Outputs
- **Code:** `the_one/mcp/client.py` (classifier, matrix, owner task, input-required), the new leaf module `the_one/mcp/_era.py`, `the_one/mcp/errors.py` (mismatch wording), `the_one/interfaces/web/api.py` (Test connection Phase A clear, plus the fix to the existing strip), `the_one/diagnostics.py` (`_probe_mcp_sdk`).
- **Docs:**
  - `the_one/mcp/__init__.py:3`'s docstring;
  - `CLAUDE.md:305`'s `requires_bwrap` count;
  - `the_one/agents.md`'s "MCP error translation" section: the matrix, the owner-task rule, the stale-token clear and the input-required error.
- **Tests:** described in the acceptance criteria.
- **Flight log:** a `### client-hardening` entry listing every changed test expectation and the interim state.

## Acceptance Criteria
- [x] AC1 (DD5, classifier):
  - `MCPClient._classify_failure(exc, *, op, baseline)` builds the typed exception for matrix rows 1-4 and 6. Each of `connect`, `list_tools` and `call_tool` keeps its own `try`/`except`/`except*` structure and cleanup: connect's `_safe_cleanup`, abandoning the stack on `CancelledError`, and reading the record before cleanup.
  - The three `except* (OAuthFlowError, OAuthTokenError)` blocks share only how their `MCPAuthRequired` is built.
  - Arm order follows the matrix:
    - `UrlElicitationRequiredError` first. Its pass-through in `connect` is an intended change; today the generic arm wraps it.
    - Then the sign-in record, which also consults the record in the `httpx2.HTTPError` / `anyio.ClosedResourceError` arms.
    - Then protocol-version rejection.
    - Then the SSE cap.
    - Then session terminated.
  - Every cell not named in rows 1-4 and 6 keeps today's behaviour. A test per row, per operation, covers rows 1-4.
- [x] AC2 (DD5, row 3), proven with mock sessions:
  - In `connect`: an `MCPError(-32022)` whose data parses with no shared version gives `MCPVersionMismatch`, with `observed` taken from `supported`. The `initialize()` `RuntimeError("Unsupported protocol version …")` keeps mapping to `MCPVersionMismatch`.
  - In `list_tools` and `call_tool`: any -32022 marks the client dead and calls `_era.forget_era(source.id)`. With no shared version it raises `MCPVersionMismatch`. Otherwise it raises `MCPConnectionError` saying the server changed protocol revision and the connection reconnects on the next call.
- [x] AC3 (DD5, the mismatch message): `errors.py`'s message becomes "the-one supports 2024-11-05 through 2026-07-28", built from `mcp.types.version`. `.pinned` is kept. `tests/test_mcp_client.py:451` still passes.
- [x] AC4 (DD5, contract): a test names and pins the two strings Test connection matches on, "did not respond" and "cancelled during initialize" (`client.py:440, 470`). The strings are unchanged byte-for-byte.
- [x] AC5 (DD6):
  - `connect` records `self._owner_task = asyncio.current_task()` when it enters the transport stack. It resets on every `connect` and clears in `disconnect`.
  - In every arm that catches `asyncio.CancelledError`, a cancellation on a task other than `_owner_task` re-raises. On the owner task, today's translation stays.
  - Two tests:
    - `tests/test_mcp_signin_detection.py::test_failed_signin_flow_yields_auth_required_end_to_end` still passes.
    - A new test cancels a `call_tool` issued from a different task than `connect`, while the last MCP-POST response was a 401, and asserts `CancelledError` propagates.
- [x] AC6 (DD7), in Test connection's Phase A:
  - **Clear.** The `except MCPAuthRequired` branch (`api.py` ~3698) clears `dcr_credentials`, `access_token`, `refresh_token` and `token_expires_at`. It re-reads the stored row with `repo.get(source_id)`, strips those keys and writes it back. Separately, it strips the same keys from the in-memory `source.secrets` with `source.model_copy(update={"secrets": …})`. It does not replace `source` with the stored row, because Phase B uses `source.config["url"]`.
  - **Existing strip.** The `looks_like_token_failure` strip (~3720-3734) is changed to the same re-read pattern: it currently does `repo.update(source.model_copy(...))` from a possibly-overridden `source`.
  - **Tests.**
    - `tests/test_mcp_test_connection_stale_tokens.py` asserts the four keys are cleared from the stored row. This is a changed expectation; log it.
    - A new test sends a request-body override with an unsaved URL. It asserts the stored row's non-secret config is unchanged after the clear, and that Phase B's consent flow targets the override URL.
- [x] AC7 (DD8):
  - `call_tool` passes `allow_input_required=True` to `session.call_tool`.
  - An `mcp.types.InputRequiredResult` result, checked before the content is flattened, raises `MCPCallError` whose `server_message` is exactly "the server asked for extra input, which the-one can't provide yet".
  - A mock-session test covers it.
  - `tests/test_mcp_client.py:1383` (`assert_awaited_once_with("t", {"x": 42})`) is updated to include `allow_input_required=True`, and the change is logged.
- [x] AC8 (DD11): `_probe_mcp_sdk` constructs and closes a synchronous `httpx2.Client()`. Its detail reads `mcp <ver>, handshake 2025-11-25, modern 2026-07-28, httpcore2 <ver>`, with versions from `importlib.metadata`. `tests/test_doctor.py` asserts the detail includes `httpcore2`.
- [x] AC9 (DD2):
  - `the_one/mcp/_era.py` exists as a leaf module. It imports nothing from `the_one` that would pull in `the_one.mcp.oauth`, and `tests/test_imports.py` passes.
  - It provides `era_for`, `remember_era`, `forget_era` and `_clear_for_test`.
  - An autouse fixture in `tests/conftest.py` calls `_clear_for_test()`.
  - Unit tests cover the four functions.
- [x] AC10 (DD12):
  - `the_one/mcp/__init__.py:3` no longer says "mcp==1.27.0".
  - `CLAUDE.md`'s `requires_bwrap` sentence states the real count, measured by this leg's run.
  - `the_one/agents.md`'s "MCP error translation" section documents the matrix, the owner-task rule, the stale-token clear and the input-required error.
- [x] AC11: all of the following pass:
  - `make test-unit` (plain mode), with the skip count still 12 or the difference explained;
  - `.venv/bin/python -m pytest -m requires_bwrap -x --timeout 120`;
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`;
  - the browser files that drive Test connection and OAuth, run with `THE_ONE_TEST_NETNS=1` and `-m browser`: `tests/browser/test_mcp_test_connection_button.py`, `tests/browser/test_oauth_modal_flow.py`, `tests/browser/test_flow_oauth_callback_cross_site.py`, `tests/browser/test_studio_mcps_tab.py`.
- [x] AC12: the flight log's `### client-hardening` entry lists every changed test expectation (with reason), the interim state and the measured `requires_bwrap` count. The leg status is `landed`.

## Design-Review Resolutions (authoritative where they differ from the criteria above)

The leg's Developer design review (approve with changes, 2026-10-12) settled these:

1. **Row 1 in `connect` keeps today's behaviour.** `UrlElicitationRequiredError` raised during `connect` stays wrapped by the generic arm as `MCPConnectionError`, with `_safe_cleanup`. It is **not** passed through, and it is not an intended change. Nothing outside `client.py` handles it: `_pool._entry_worker` stores it and `MCPToolProvider` catches only `SandboxError`, `MCPConnectionError` and `MCPVersionMismatch`, so a pass-through would crash agent builds. `list_tools` and `call_tool` keep passing it through, as today. The flight's DD5 matrix is amended to match.
2. **Row 3: "shared version" means `HANDSHAKE_PROTOCOL_VERSIONS + MODERN_PROTOCOL_VERSIONS`**, the same set the mismatch message names.
   - **No shared version** (`supported` parses and intersects that set in nothing): `MCPVersionMismatch`, with `observed` = the `supported` list joined with ", ".
   - **A shared version exists, in leg 1:** `connect` falls through to the generic `MCPConnectionError("MCP connect failed: …")`, because leg 2's policy will re-probe. `list_tools` and `call_tool` raise `MCPConnectionError`, saying the server changed protocol revision and it reconnects on the next call.
   - **`data` is `None` or doesn't parse** (no information): `MCPConnectionError`. In `list_tools` and `call_tool` it still marks the client dead and calls `forget_era`.
   - **The `initialize()` `RuntimeError` path** keeps `observed` = the regex group, as today.
3. **Behaviour changes to log as intended:**
   - **-32022 in `call_tool`:** today it is `MCPCallError`; it becomes `MCPConnectionError` or `MCPVersionMismatch`, and marks the client dead.
   - **-32022 in `list_tools`:** it now marks the client dead.
   - **`call_tool`'s SSE-cap and session-terminated checks** swap order. The messages are disjoint, so behaviour is unchanged.
4. **The owner-task rule (AC5) in detail.**
   - There are exactly three `CancelledError` arms: `connect` (~446), `list_tools` (~743) and `call_tool` (~889).
   - In `connect` the check is always true on the owner, so it does nothing there. Do not add a re-raise.
   - In `list_tools` and `call_tool`, `CancelledError` shares a tuple arm with `Exception` and `BaseExceptionGroup`. Bind the arm `as e`, then in order:
     1. If `isinstance(e, asyncio.CancelledError)` and this is not the owner task, `raise`.
     2. Otherwise consult the record.
     3. Otherwise `raise`.
   - Add a small helper `_on_owner_task()`.
   - `_owner_task is None` (never connected, or after `disconnect`) counts as "not owner", so the error re-raises. This is intended; log any test fixture that builds a client by hand and is affected.
   - Set `_owner_task` before `_transport_connect` is entered.
   - After this step, run `test_mcp_client`, `test_mcp_signin_detection`, `test_mcp_wire_shapes`, `test_mcp_pool`, `test_mcp_tool_provider`, `test_tool_call_timeout` and `test_oauth_test_connection_endpoint`.
5. **The stale-token clear (AC6) in detail.**
   - Factor one helper used by both sites (the new Phase A `except MCPAuthRequired` branch and the existing `looks_like_token_failure` strip). It:
     - re-reads the row with `persisted = await repo.get(source_id)`; `MCPSourceRepository.get` raises `KeyError` on a missing row, it does not return `None`;
     - writes `persisted.model_copy(update={"secrets": stripped})`;
     - returns `source.model_copy(update={"secrets": <source.secrets minus the four keys>})`.
   - The in-memory strip happens even if the re-read or write raises.
   - At the existing strip, `source = cleared` becomes the helper's returned in-memory source, so the override config survives into Phase B.
   - `tests/test_mcp_test_connection_stale_tokens.py`: add the four-keys-cleared assertion, and fix its now-wrong comment that says the stale secrets "stay". This is a new assertion plus a comment fix, not a changed expectation.
   - Also run `tests/test_oauth_test_connection_endpoint.py`. It seeds `dcr_credentials` and drives Phase A to `MCPAuthRequired`.
6. **The doctor gate (AC8) in detail.**
   - The `httpx2.Client()` construction and the version lookups (`mcp`, `httpcore2`) go **inside the `_import_mcp_sdk` seam**, so the existing failure test (`_boom`) still covers them. The seam may return a richer tuple or a small dict.
   - `tests/test_doctor.py` (~893), `re.fullmatch(r"mcp \d+\.\d+\.\d+\S*, handshake \d{4}-\d{2}-\d{2}", …)`, is a changed expectation. Update it to the new detail (`…, modern \d{4}-\d{2}-\d{2}, httpcore2 \S+`) and log it.
   - The Windows needles (`mcp sdk: OK`) are unaffected.
7. **The contract strings (AC4) become structural.**
   - Hoist "did not respond" and "cancelled during initialize" into named constants, for example `TOKEN_FAILURE_MARKERS` in `the_one/mcp/errors.py`. `client.py` builds its messages from them and `api.py`'s `looks_like_token_failure` imports them.
   - The pin test produces each message through the real code path and matches it with the same `in` test `api.py` uses.
8. **The docs (AC10) in detail.**
   - Rewrite the whole `requires_bwrap` parenthesis in `CLAUDE.md` (~305), not only the "12", with the measured total, and say whether the skips are counted.
   - Check the marker description around `the_one/agents.md` ~2363 too.
   - `tests/test_imports.py`: confirm `the_one.mcp._era` pulls in nothing new (add it to the import list if the file has one).
   - The autouse `_clear_for_test` fixture goes beside the others in `tests/conftest.py` (~393-430).
9. **Pass budget.** Gate each step on its focused test files, run the browser files last, and put the `agents.md` work in the final step.

## Verification Steps
- AC1-AC9: the named tests pass, and each new test is named in the flight log.
- AC10: read the diff.
- AC11: run the commands and record their exit codes in the flight log.

## Implementation Guidance
1. **`_era.py` first** (AC9). It's small and has no dependencies.
2. **Classifier and matrix** (AC1-AC4). Start by writing out today's arm order per method, as comments or notes in the flight log. Then introduce `_classify_failure` one method at a time, running `tests/test_mcp_client.py`, `tests/test_mcp_signin_detection.py` and `tests/test_mcp_wire_shapes.py` after each method.
3. **Owner task** (AC5).
4. **Input required** (AC7).
5. **Test connection's Phase A clear and the existing strip** (AC6).
6. **Doctor** (AC8).
7. **Docs** (AC10). Then do the full verification (AC11).

## Edge Cases
- **Mock sessions.** A bare `MagicMock` has truthy attributes. Tests that construct `MCPError(-32022, …, data=…)` must pass data that parses (or deliberately doesn't parse) as `UnsupportedProtocolVersionErrorData`.
- **`connect`'s `CancelledError` path** must still read the sign-in record before `_safe_cleanup` sets `self._session = None`.
- **Cancellations from `_pool.py::_teardown_entry`.** It cancels the worker, which is the owner task, and `connect` keeps translating that as it does today.
- **`repo.get(source_id)` raises `KeyError`** if the source was deleted mid-Test. Skip the write, and still strip the in-memory secrets (resolution 5).
- **Unloaded modules in the doctor.** If `importlib.metadata` can't find `httpcore2`, the gate fails with the reason. It must not crash.

## Files Affected
- `the_one/mcp/client.py`, `the_one/mcp/_era.py` (new), `the_one/mcp/errors.py`, `the_one/mcp/__init__.py` (docstring only)
- `the_one/interfaces/web/api.py` (Test connection Phase A only)
- `the_one/diagnostics.py`
- `tests/conftest.py`, `tests/test_mcp_client.py`, `tests/test_mcp_signin_detection.py`, `tests/test_mcp_test_connection_stale_tokens.py`, `tests/test_doctor.py`, plus new test files as needed (for example `tests/test_mcp_era.py` and `tests/test_mcp_failure_matrix.py`)
- `the_one/agents.md`, `CLAUDE.md`
- The flight log

## Citation Audit
Checked at leg design against `a203563`:
- `api.py`: Phase A's `except MCPAuthRequired:` (~3698) evicts and falls through. `except MCPConnectionError` with `looks_like_token_failure` (~3704-3739) strips through `source.model_copy(...)` and `repo.update(cleared)`, then sets `source = cleared`, writing from a possibly-overridden `source`.
- `client.py`: the `_auth_required_since` sites, the SSE-cap and session-terminated arms, the `except*` OAuth blocks and the `CancelledError` arms are as listed in the flight log's Reconnaissance Report A3 and A5, and as verified by both design-review cycles.
- `diagnostics.py:583-612`: `_import_mcp_sdk` / `_probe_mcp_sdk`.
- `the_one/agents.md:763`: the OAuth-managed secret set.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
