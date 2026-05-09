# Flight Log: Cleanup + connect-time 401 translation

**Flight**: [Cleanup + connect-time 401 translation](flight.md)

## Summary

Flight in `in-flight` state — design phase complete; design review cycle 1 passed; L0+L1 execution underway via /agentic-workflow.

---

## Flight Director Notes

### 2026-05-09 — Flight execution start

**Status transition**: `ready` → `in-flight`. Branch already at `flight/6_6-cleanup-and-connect-401` (created at design time, pre-flight). Project crew loaded from `the-one/.flightops/agent-crews/leg-execution.md` — Developer (Sonnet) for design + implement, Reviewer (Haiku) for code review. No Accessibility Reviewer needed (no UI surfaces). Leg cycle: design L0 → review L0 → implement L0 → design L1 → review L1 → implement L1 → single code review over both → commit. Per skill guidance, commit and PR are deferred until all autonomous legs land.

### 2026-05-09 — Flight closeout

**Status transition**: `in-flight` → `landed`. Code review for Flight 6.6 PASSED with `[HANDOFF:confirmed]` — no blocking issues raised by the Reviewer. All acceptance criteria across both legs verified and checked off; both legs transitioned from `landed` to `completed`. Flight 6.6 checkbox marked complete in `missions/07-mcp-integration/mission.md`. The batched commit covers L0 + L1 production code, tests, the `CLAUDE.md` operator-facing entry, and all updated artifacts (legs, flight, mission, flight-log). Push and draft PR follow immediately. No Tier-2 HAT per Design Decision §4; verification entirely via unit tests (3 new L0 tests + 3 new L1 tests + 1 updated L1 test) plus the 4 browser tests in `test_oauth_modal_flow.py` that transitioned FAIL → PASS as a side effect of the `App.areas` re-export.

### 2026-05-09 — Flight kickoff

**Origin**: Born from F6.5 debrief recommendations 1-4 (carry-forward maintenance) + F6.5 Design Decision §3's explicit deferral of connect-time 401 widening. Replaces the originally-scoped F7 inspector flight, which was reframed away post-F6.5 review (form-driven invocation + JSON-RPC trace pane judged developer-tooling rather than operator-facing). Useful F7 leftovers (capability flags display, input-schema visibility) folded into F8's scope per mission amendment in this same commit.

**Scope tightness**: 2 legs, no HAT, ~230 LOC total. Verification entirely via unit tests since no new operator-facing surfaces are introduced. F6.5 Design Decision §4's binding-HAT-for-OAuth-flights pattern explicitly waived (see flight.md Design Decision §4 for rationale).

---

## Leg Progress

> Append leg-execution entries below as L0 + L1 land.

### L1 — implementation

**Status**: landed
**Implemented**: 2026-05-09
**Branch**: `flight/6_6-cleanup-and-connect-401`

#### Deliverables

1. **Production code change** — `the_one/mcp/client.py::MCPClient.connect()`. Added a nested innermost `try/except* (OAuthFlowError, OAuthTokenError):` block wrapping ONLY `session.initialize()`, raising `MCPAuthRequired(source_id=self.source.id, resource_metadata_url=None, consent_url=None) from None`. The existing `except RuntimeError` for version-mismatch translation stays at the outer try level (Python's no-mix-`except`-with-`except*` constraint preserved). Existing `except (Exception, BaseExceptionGroup)` block at lines 270-335 untouched.
2. **CancelledError message update** — `client.py` lines 265-269: replaced `"401 Unauthorized or transport error"` with `"transport error or malformed initial response"`. Adjacent docstring/comment at lines 254-263 also updated to reflect the post-F6.6 narrowing ("non-OAuth, non-401 transport-level failure" instead of "after a 401 (or other transport-level failure)"). Mentions in the comment that OAuth-flow exceptions are now caught upstream by the inner `except*` block.
3. **Test 1** — `tests/test_mcp_client.py::TestMCPClientLifecycle::test_connect_oauth_flow_error_raises_mcp_auth_required` added (~22 LOC). Bare `OAuthFlowError` side_effect; asserts `MCPAuthRequired` with `source_id == client.source.id`, `resource_metadata_url is None`, `consent_url is None`.
4. **Test 2** — `test_connect_oauth_token_error_raises_mcp_auth_required` added (~17 LOC, same shape with `OAuthTokenError`).
5. **Test 3** — `test_connect_oauth_error_in_exception_group_raises_mcp_auth_required` added (~21 LOC). `BaseExceptionGroup("auth-flow-group", [OAuthFlowError(...)])` side_effect; verifies `except*` matches grouped exceptions.
6. **Updated test** — `test_connect_cancelled_error_translates_to_connection_error` retained `assert "cancelled during initialize" in str(exc_info.value)` and added `assert "401" not in str(exc_info.value)` immediately after, with a comment explaining the post-F6.6 narrowing.

Total LOC: ~35 LOC production code change (with comments) + ~70 LOC tests. No deviations.

#### Test counts

- New + updated tests (`docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle -v -k "oauth or cancelled" --timeout 60`): **4 PASSED** in 0.12s (3 new OAuth tests + the updated CancelledError test).
- Full TestMCPClientLifecycle suite (`docker compose exec the-one pytest tests/test_mcp_client.py::TestMCPClientLifecycle -v --timeout 90`): **18 PASSED** in 0.16s. No regressions.
- L0 cross-check (`tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present`): **1 PASSED** in 0.02s. Confirms `MCPAuthRequired` flows through `_entry_worker`'s `except BaseException` capture unchanged.
- F6.5 L2 graceful-skip cross-check (`tests/test_mcp_tool_provider.py -k "graceful"`): **1 PASSED** in 0.03s (`test_get_tools_for_agent_graceful_skips_on_mcp_auth_required`). Confirms the post-F6.5 graceful-skip path is structurally compatible with the new connect-time `MCPAuthRequired` flow.
- Full unit suite (`docker compose exec -T the-one pytest --ignore=tests/test_mcp_pool.py -q --timeout 120`): **3 failed, 1356 passed, 2 skipped, 306 deselected, 2 warnings in 72.32s**. The 3 failures are the pre-existing `test_mcp_sandbox_integration.py` bwrap regressions; no new ones (test count up by 3 vs L0 baseline of 1353 — exactly accounts for the 3 new tests added in this leg).

### L0 — implementation

**Status**: landed
**Implemented**: 2026-05-09
**Branch**: `flight/6_6-cleanup-and-connect-401`

#### Deliverables

1. **Test 1** — `tests/test_oauth_provider_factory.py::test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source` added (~25 LOC). Covers F6.5 L3 bootstrap path: returns non-None `OAuthClientProvider` when `dcr_credentials` absent AND `allow_dcr_bootstrap=True` AND `chat_session_id` is set. Negative control without the flag returns None. PASS in 0.15s.
2. **Test 2** — `tests/test_streamable_http_transport.py` created (NEW file, ~80 LOC). Parametrized over the 6 `OAUTH_MANAGED_SECRET_KEYS` values via `sorted(OAUTH_MANAGED_SECRET_KEYS)` (mechanical iteration — future expansions caught automatically). Adds a negative control verifying non-OAuth-managed secrets pass through. 7 PASS in 0.03s.
3. **Test 3** — `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present` added (~85 LOC). Patches `the_one.mcp.oauth.build_oauth_provider_for_source` (source-module target — required because of the function-local `from ... import` re-resolution at `_pool.py:196`). Asserts the synthetic csid `agent_build:src-pool-test` is forwarded as the third positional arg. PASS in 0.02s. See Deviations §1 for the test-shape correction vs leg guidance (the worker's `except BaseException` does NOT cover the factory call, so the test uses `pytest.raises` instead of asserting on `entry.failure`).
4. **App.areas export** — `the_one/interfaces/web/static/js/app.js` line 267 `Object.assign(window.App, {...})` block grew by one entry: `areas: order` (the array, not the dict). Comment block names the consumer (`Array.prototype.find` semantics in `tests/browser/test_oauth_modal_flow.py:42`) and the deviation rationale. See Deviations §2.
5. **handlers.py docstring** — `the_one/mcp/oauth/handlers.py` module docstring extended with one paragraph (~20 lines inside the existing triple-quoted block) naming the three csid shapes (real 12-char hex, `test:{source_id}`, `agent_build:{source.id}`), the character-set-disjunction collision invariant, and the no-op-broadcast contract.
6. **Operator-facing doc** — `grep -rn -i "MCP Sources|Test connection|mcp.sources" CLAUDE.md docs/` returned no operator-facing fit. Appended a new top-level `## MCP Sources operator workflows` section to `CLAUDE.md` (between "F6 admin UI patterns" and "## Configuration") with a 6-line **Test connection button** paragraph naming location, behaviour, and side effect.

#### Test counts

- `tests/browser/test_oauth_modal_flow.py` (browser marker): **PRE-state 4 FAILED, 0 PASSED** → **POST-state 0 FAILED, 4 PASSED** (5.85s). All 4 tests transitioned FAIL → PASS as predicted by the design.
- `tests/test_oauth_provider_factory.py::test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source`: 1 PASSED in 0.15s.
- `tests/test_streamable_http_transport.py`: 7 PASSED in 0.03s (6 parametrized + 1 negative control).
- `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present`: 1 PASSED in 0.02s.
- Full unit suite (`docker compose exec -T the-one pytest --ignore=tests/test_mcp_pool.py -q --timeout 120`): **3 failed, 1353 passed, 2 skipped, 306 deselected, 2 warnings in 75.30s**. The 3 failures are the pre-existing `test_mcp_sandbox_integration.py` bwrap regressions noted in flight Checkpoints. No new regressions introduced.

### L0 — design + design review

**Status**: ready
**Designed**: 2026-05-09
**Reviewed**: 2026-05-09 (cycle 1, single pass)

#### Design highlights
- Six independent deliverables bundled in one leg per flight Design Decision §1: 3 unit tests covering F6.5 L4 inline fixes, `App.areas` re-export (Anomaly A2), synthetic-csid pattern docstring, operator-facing Test connection button doc.
- Citation audit run at design time: 10 citations verified against current code (provider_factory.py, streamable_http.py, storage.py, _pool.py, app.js, test_oauth_modal_flow.py, handlers.py, api.py, models.py).

#### Design review cycle 1 (Developer/Sonnet)
Architect flagged 2 high + 5 medium + 4 low issues. All high+medium incorporated; selected lows applied at discretion:
- **HIGH (incorporated)**: `tests/test_streamable_http_transport.py` does NOT exist — committed leg to "create new file" unconditionally; removed grep-discovery hedge.
- **HIGH (incorporated)**: synthetic-csid prefix-uniqueness invariant was technically wrong (`agent_build:` is exactly 12 chars, not longer). Rewrote invariant as character-set disjunction: real csids are `[0-9a-f]` 12-char hex; synthetics contain `:` separator that hex cannot produce — collision impossible regardless of length.
- **MED (incorporated)**: `_RegistryEntry` requires `ttl_seconds: int` as positional field (per `_pool.py:92`); leg's Test 3 guidance overlooked it. Added explicit construction snippet.
- **MED (incorporated)**: tightened monkeypatch rationale — `from … import …` re-resolves on each function call; correct target is `the_one.mcp.oauth.build_oauth_provider_for_source`; wrong target raises `AttributeError`.
- **MED (incorporated)**: simplified Test 3's mock-stop strategy to single-mock with `side_effect=RuntimeError` instead of double-mock with separate `MCPClient.connect` patch.
- **MED (incorporated)**: replaced "lines 106+ and 120+" placeholder with explicit test names `test_modal_closes_on_auth_resolved_event` (line 100), `test_button_clears_on_auth_resolved_event` (line 114).
- **LOW (incorporated)**: dropped `current_chat_session_id.set(None)` advice — ContextVar default already handles unset case.
- **LOW (incorporated, option (b))**: kept "try design intent first" framing for `App.areas` but added explicit "mechanically predictable to fail" note. Implementer may skip the failing first attempt with a deviation rationale; both paths land same code.
- **LOW (incorporated)**: replaced loose "≥2 hits" git-grep AC with explicit named-sites pin.

Cycle 2 skipped per skill guidance — all cycle-1 fixes were factual reconciliations against verified code state. No architectural changes.

---

### L1 — design + design review

**Status**: ready
**Designed**: 2026-05-09
**Reviewed**: 2026-05-09 (cycle 1, single pass)

#### Design highlights
- ADD-only change to `MCPClient.connect()` per flight Design Decision §2: nested innermost `try/except* (OAuthFlowError, OAuthTokenError):` wrapping ONLY `session.initialize()`. Existing `except RuntimeError` for version-mismatch translation stays at outer try level (Python no-mix-`except`-with-`except*` constraint). Existing `except (Exception, BaseExceptionGroup)` block at lines 270-335 is UNTOUCHED.
- CancelledError message at lines 265-269 updated per Design Decision §3: drop "likely 401 Unauthorized" speculation; new wording "transport error or malformed initial response."
- 3 new unit tests (bare OAuthFlowError, bare OAuthTokenError, BaseExceptionGroup-wrapped OAuthFlowError) + 1 existing test updated (CancelledError test gets a "401 not in" assertion).
- Citation audit at design time: 12 citations verified.

#### Design review cycle 1 (Developer/Sonnet)
Architect APPROVED with 4 non-blocking suggestions. Two incorporated as soft requirements:
- **SUGG (incorporated)**: Implementation Guidance step 5 anchors test placement by name (after `test_connect_cancelled_error_translates_to_connection_error`, before `test_disconnect_idempotent`) instead of line number — line numbers shift as the 3 tests land sequentially.
- **SUGG (incorporated)**: Implementation Guidance step 3 promoted the CancelledError docstring update from "may optionally update" to soft-required — the existing comment at `client.py:254-263` says "after a 401 (or other transport-level failure)" which contradicts the post-F6.6 narrowing. New wording: "after a non-OAuth, non-401 transport-level failure."
- **SUGG (deferred)**: line-precision tightening of the `client.py:467-512` range citation — non-blocking; current range citation is accurate.
- **SUGG (deferred)**: noting `OAuthTokenError ⊆ OAuthFlowError` inheritance (so Test 2 is technically redundant under bare `except OAuthFlowError`) — keeping the explicit pair for symmetry with F6.5 L2's source-of-truth pattern at `client.py:477`.

Architect's open question — graceful-skip cross-check terminology — noted: existing test at `tests/test_mcp_tool_provider.py:590` exercises the skip-clause via stub `list_tools`, which is structurally similar to but not identical to the connect-time path. Re-framed in Verification Steps as a "regression check" rather than a true integration test of the new path. Unit tests cover the new connect-time path directly.

Citation re-verification at review time: all 12 verified at exact lines (mechanical re-check by architect).

Cycle 2 skipped — only soft suggestions; no architectural changes.

---

## Decisions

> Append runtime decisions not in original plan.

---

## Deviations

> Append departures from planned approach.

### 2026-05-09 — L0 §1: Test 3 mock-stop pattern + assertion shape

**Deviation**: Leg Implementation Guidance Item 4 stated "the `RuntimeError` from the factory propagates up to `_entry_worker`'s `except BaseException as exc:` branch (line 210), which sets `entry.failure = exc` and returns — no second mock needed for `MCPClient.connect`." Empirical run revealed this is incorrect: the `except BaseException` block at `_pool.py:208-213` wraps ONLY `await client.connect()`, not the factory call at line 204. The mock's `RuntimeError` therefore propagates out of `_entry_worker` rather than being captured into `entry.failure`.

**Resolution**: Test wraps the `await _entry_worker(...)` call in `pytest.raises(RuntimeError, match="captured-and-stopped")` and asserts on `mock_factory.call_args` (MagicMock records args before side_effect raises). Same one-mock-stops-worker pattern; same csid-forwarding assertion; only the post-await assertion shape differs. Test is otherwise as designed.

**Citation correction for L0**: leg's Implementation Guidance Item 4 (and Acceptance Criterion #3) referenced `entry.failure is not None` as evidence the worker reached its early-return path. That assertion is unreachable from this mock arrangement; removed from the test. The csid-forwarding assertion (`call_args.args[2] == f"agent_build:{source.id}"`) remains as the load-bearing AC.

### 2026-05-09 — L0 §2: App.areas export — direct to `areas: order`

**Deviation**: Leg Implementation Guidance Item 5 directed "TRY first: `areas: areas` to honor design intent ... if tests fail with 'areas.find is not a function' or similar (the dict-vs-array discrepancy materializes): switch to `areas: order`." Per the leg's Edge Cases note ("the implementer MAY skip the failing first attempt and go directly to `areas: order` with a deviation note"), implemented `areas: order` directly.

**Rationale**: The browser-test helper at `tests/browser/test_oauth_modal_flow.py:42` calls `window.App.areas.find(a => a.id === 'chat')` — `Array.prototype.find` semantics. The closure-private `var areas = {}` is a dict (no `.find` method); the closure-private `var order = []` is the sorted array of descriptors. Exporting `areas: areas` would mechanically fail with `TypeError: window.App.areas.find is not a function`. The leg explicitly identified this as "mechanically predictable" — the first-attempt confirmation step would have added ~30s of test runtime without changing the outcome. Going direct lands the same code with one less iteration.

**Verification**: 4 browser tests transitioned FAIL → PASS on first run after the export landed (5.85s).

---

## Anomalies

> Append unexpected issues encountered.

---

## Session Notes

### 2026-05-09 — F6.6 design + mission scope amendment

Flight artifact authored against F6.5 debrief carry-forward items + F6.5 Design Decision §3 deferral. Mission amendment in the same commit: F7 entry struck through with rationale; useful leftovers absorbed into F8's scope. F9 prose updated to drop "inspector" reference.

Open questions all resolved at design time (no Phase 4 user iteration needed — the scope is mechanical: maintenance batch + a small connect-time addition). Spec passed design review cycle 1 with corrections; see `flight.md::Design Review Cycle 1` for the trail.

**Design review correction (cycle 1)**: original spec mis-framed L1 as "verbatim mirror of F6.5 L2's `list_tools` pattern." Architect verified the actual `connect()` body — it already has 401-translation via outer BaseExceptionGroup walk (F6 A5 work). Real gap is the `OAuthFlowError`/`OAuthTokenError` `except*` clause. L1 reframed as "ADD only the missing clause" with nested `try/except*` (Python's no-mix-`except`-with-`except*` constraint forces the nesting). Net diff estimate dropped from ~80 LOC to ~30 LOC for L1.
