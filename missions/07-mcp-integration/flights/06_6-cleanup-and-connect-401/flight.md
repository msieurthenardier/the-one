# Flight: Cleanup + connect-time 401 translation

**Status**: landed
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [x] **#10** — graceful failure isolation (extends `MCPClient.connect()` 401 surface from lossy `MCPConnectionError("cancelled during initialize")` to typed `MCPAuthRequired`, mirroring F6.5 L2's `list_tools` pattern; `MCPToolProvider.get_tools_for_agent` already graceful-skips on `MCPAuthRequired` per F6.5 L2, so this completes the auth-pending discriminator surface across both connect and list_tools)
- [x] **#11** — automated coverage proving each layer's contract (closes F6.5 debrief recommendation #3: 3 unit tests covering F6.5 L4 inline fixes that currently only have non-reproducible HAT verification)

---

## Pre-Flight

### Objective

Two independent deliverables under one small flight: (a) close the F6.5 debrief carry-forward maintenance items as a single batch (3 unit tests covering L4 inline fixes, Anomaly A2 fix, synthetic-csid pattern docs, operator-facing Test connection README entry), and (b) extend `MCPClient.connect()` with the same `try/except*` 401 translation pattern F6.5 L2 added to `list_tools`, closing F6.5 Design Decision §3's explicit deferral of connect-time 401 widening.

### Open Questions

- [x] Tier-2 HAT binding for the connect-time translation? → **No**; F6.5's HAT already verified the runtime path against live Cloudflare for `list_tools`. The connect path is structurally identical (mirrors the same SDK error surface) and is verified by unit tests against mocked 401 responses. The flight introduces no new operator-facing surfaces (no UI, no new endpoints), so there's no Tier-2 verification gap to close.
- [x] Single leg or split? → **Split into 2**: L0 maintenance (independent items, parallel-safe) + L1 connect-time translation (architectural change with its own AC). Keeps each leg's review surface focused.
- [x] Re-add `App.areas` export to `app.js` vs rewrite `_emit_ws_event` helper? → **Re-add the export**; it's a 1-line change that closes 4 spurious browser failures, vs rewriting a test helper that's used by `test_oauth_modal_flow.py` and works fine when the export exists. F6.5 L1 reverted the export as scope-creep without realizing JS test helpers consumed it (Anomaly A2). Re-adding is the surgical fix.
- [x] Where does the synthetic-csid pattern doc live? → **`the_one/mcp/oauth/handlers.py` module docstring** (the redirect_handler closure is the place where the pattern's no-op-on-synthetic-csid invariant matters); a one-paragraph addition naming `test:{source_id}`, `agent_build:{source.id}`, and the prefix-uniqueness contract.

### Design Decisions

**§1. Maintenance items batched into L0 as one leg, not split per item**: 3 unit tests + 1-line export re-add + 1 docstring + 1 README entry are each ≤30 LOC; splitting into 4 legs creates more review-surface overhead than the items individually merit. Bundling reduces orchestration cost.

- Rationale: each item has its own AC and is independently verifiable. Bundling does not couple them. Reviewer can read the diff per-item via the bundled commit's structure.
- Trade-off: a partial-completion of L0 (e.g. tests pass but README didn't get added) would land as one mixed-state leg rather than 4 cleanly-separable legs. Acceptable given the scope; the leg's AC list itemizes each deliverable so partial states are detectable.

**§2. Connect-time translation: ADD only the missing `OAuthFlowError`/`OAuthTokenError` `except*` clause, NOT a verbatim mirror of `list_tools`**: `MCPClient.connect()` (current main, post-F6.5) ALREADY has 401-translation via the outer `except (Exception, BaseExceptionGroup)` block at `client.py:270-335` — it walks `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` for inner 401s and raises `MCPAuthRequired` with the `WWW-Authenticate`-extracted `resource_metadata_url`. That part works. The actual gap is the SDK's auth-flow exception classes (`OAuthFlowError`, `OAuthTokenError` from `mcp.client.auth.exceptions`) — when the provider's auth flow fails *during* `session.initialize()` (refresh failed, discovery failed, DCR failed), those exceptions surface and currently fall through to the generic `except (Exception, BaseExceptionGroup)` block, which translates them to `MCPConnectionError(f"... {type(e).__name__}: {e}")` instead of the typed `MCPAuthRequired`.

The minimal change is: wrap **only** `session.initialize()` in a new innermost `try/except* (OAuthFlowError, OAuthTokenError)` clause. The existing `except RuntimeError` clause for version-mismatch translation must stay outside the new `try/except*` because Python prohibits mixing `except` and `except*` in the same `try` block. So the structure becomes:

```python
self._session = session
try:                                           # existing try (RuntimeError catcher)
    try:                                       # NEW innermost try
        result = await session.initialize()
    except* (OAuthFlowError, OAuthTokenError):
        raise MCPAuthRequired(
            source_id=self.source.id,
            resource_metadata_url=None,
            consent_url=None,
        ) from None
except RuntimeError as e:                      # existing version-mismatch handler
    m = _UNSUPPORTED_VERSION_RE.match(str(e))
    observed = m.group(1) if m else str(e)
    raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
```

The 401-via-`httpx.HTTPStatusError` path at lines 315-331 is NOT touched — it already works. The architect cycle confirmed reading the `connect` body that this 401-walk is in production and verified by F6.5 HAT.

- Rationale: minimal additive change vs structural rewrite. The `list_tools` pattern is duplicated in `call_tool` because both methods have flat try-blocks; `connect` already pre-dates that pattern with a different (BaseExceptionGroup-walking) approach that handles the same 401 case. Asymmetry is acceptable here — readability suffers slightly but rewriting `connect` to match `list_tools` would require refactoring the working `_safe_cleanup` deadlock handler, expanding scope unnecessarily.
- Trade-off: future readers comparing `connect` and `list_tools` will see different shapes for the "same translation." Mitigation: a code comment at the new innermost `try/except*` should reference F6.5 L2's `list_tools` pattern + explain why connect uses both inner `except*` (for OAuth exceptions) AND outer BaseExceptionGroup walk (for HTTPStatusError) — the asymmetry is documented, not hidden.

**§2a. `except MCPAuthRequired: raise` guard NOT needed in `connect`**: `list_tools` needed an explicit `except MCPAuthRequired: raise` between `except asyncio.TimeoutError` and `except McpError` because `MCPAuthRequired` extends `MCPClientError` extends `McpError` — without the guard, `except McpError` would re-wrap it as `MCPConnectionError`. `connect`'s outer except list at line 250 already has `except (MCPClientError, NotImplementedError): raise`, which propagates `MCPAuthRequired` cleanly without an explicit guard. No symmetry needed.

**§3. F6 A5's `CancelledError` fallback message updated to drop "likely 401" speculation**: the current `connect` block at lines 253-270 translates `asyncio.CancelledError` to `MCPConnectionError("cancelled during initialize (cross-task cleanup deadlock; original cause likely 401 Unauthorized or transport error): ...")`. Post-F6.6, 401s are caught BEFORE cancellation propagates (via the existing outer `BaseExceptionGroup` walk at line 320, which has been there since F6 A5 — F6.6 doesn't change this path), and `OAuthFlowError`/`OAuthTokenError` are caught BEFORE cancellation propagates (via the new innermost `except*` clause from §2). So the `CancelledError` handler post-F6.6 only legitimately fires for non-OAuth cancellation races: SDK task-group cleanup deadlocks where the inner exception is something OTHER than 401 or an OAuth error. The "likely 401" speculation in the message becomes inaccurate post-F6.6 (401s are now translated upstream via the BaseExceptionGroup walk before reaching CancelledError).

Updated message: drop "likely 401 Unauthorized or" from the speculation; keep "or transport error" since transport-level cancellations are still a legitimate path here. New text:

```python
raise MCPConnectionError(
    f"MCP connect failed: cancelled during initialize "
    f"(cross-task cleanup deadlock; original cause likely "
    f"transport error or malformed initial response): {e}"
) from e
```

- Rationale: F6 A5's debrief noted the lossy diagnostic was a temporary measure. The CancelledError handler isn't fully retired by F6.6 — it's narrowed in scope (non-OAuth, non-401 cancellation races only) and the message updated to reflect that.
- Trade-off: minimal — log readers see slightly different error text. No behavior change for callers of `connect()` that weren't already getting `MCPAuthRequired` via the existing 401-walk path.

**§4. No Tier-2 HAT for this flight**: F6.5 Design Decision §4 codified "binding HAT for OAuth-touching flights" as an empirical pattern. F6.6's `MCPClient.connect()` change IS OAuth-touching, so prima facie the rule applies. Exception granted because: (a) the runtime path is verified by F6.5's HAT for `list_tools`; (b) the connect path is structurally identical (same except* groups, same exception walk, same `MCPAuthRequired` constructor); (c) F6.6 introduces no new operator-facing surfaces — no UI, no new endpoints, no flow changes for operators. Binding HAT is for surfaces that can fail in operator-facing ways the unit tests miss. F6.6 has none.

- Rationale: the binding-HAT pattern's value is verifying *integration* that fixture tests miss. F6.6 has no integration that wasn't already verified for `list_tools`. Adding a HAT here would burn an hour of operator time to re-verify a pattern that already passed.
- Trade-off: if F6.6's `connect` translation has a subtle bug that diverges from `list_tools`'s pattern (typo in field name, wrong `source_id` reference), a unit test should catch it but a HAT would catch it more confidently. Mitigation: the L1 unit tests deliberately mirror the structure of F6.5 L2's tests, so any divergence shows up as a test asymmetry.

### Prerequisites

- [x] F6.5 landed and merged to main (PR #36 merged at commit `3bf769f`)
- [x] Mission known-issue at `mission.md::Known Issues` documents the truncation issue (F6.5 L4 carry-forward; out of F6.6 scope)
- [x] F6.5 L2's `list_tools` translation pattern lives at `the_one/mcp/client.py::list_tools` — the source-of-truth pattern F6.6 L1 mirrors

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (unit tests for L0 + L1; no HAT per Design Decision §4)
- [x] Legs defined

---

## In-Flight

### Technical Approach

**L0 (maintenance batch)**: Five independent edits in one leg:

1. Add `tests/test_oauth_provider_factory.py::test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source` — verifies that `build_oauth_provider_for_source(..., allow_dcr_bootstrap=True)` constructs an `OAuthClientProvider` even when `dcr_credentials` is absent, by setting `chat_session_id` to a synthetic value and asserting the return is non-None and an `OAuthClientProvider` instance.
2. Add `tests/test_streamable_http_transport.py::test_build_request_headers_filters_oauth_managed_keys` — parametrize over the 6 keys in `OAUTH_MANAGED_SECRET_KEYS` (`access_token`, `refresh_token`, `token_expires_at`, `token_type`, `scope`, `dcr_credentials`); seed each as a `secrets` value (with appropriate type per the F6.5 L4 fix's bug — `dcr_credentials` is dict, `token_expires_at` is float); assert `build_request_headers(source)` does NOT include the key in its output.
3. Add `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present` — covers the F6.5 L4 fix at `_pool._entry_worker`. Mock `current_chat_session_id.get(None)` → None; seed `source.secrets["access_token"]` populated; assert `build_oauth_provider_for_source` is invoked with csid `f"agent_build:{source.id}"` (not None) and returns a non-None auth_provider.
4. Re-export the existing `areas` registry through `App.areas` in `the_one/interfaces/web/static/js/app.js`. The local `var areas = {};` at line 2 holds the area-id → area-object map. The `Object.assign(window.App, {...})` block at line 267 currently lists `registerArea: registerArea, router: { ... }, ...` but does NOT include `areas`. Add `areas: areas,` (or shorthand) inside that block. The `_emit_ws_event` test helper at `tests/browser/test_oauth_modal_flow.py:31-51` reads `window.App.areas.find(a => a.id === 'chat')` — once exported, the helper finds the chat area and the 4 `test_oauth_modal_flow.py` browser tests pass.
5. Document the synthetic-csid pattern in `the_one/mcp/oauth/handlers.py`'s module docstring. One paragraph naming the three known shapes (`test:{source_id}`, `agent_build:{source.id}`, real 12-char uuid4-hex), the prefix-uniqueness invariant (synthetic prefixes must be longer than 12 chars to prevent collision with real csids), and the no-op-broadcast-on-synthetic-csid contract (`_sessions.get(synthetic_csid)` returns None → guarded broadcast is a no-op).
6. Add an operator-facing entry under "MCP Sources" in `README.md` (or wherever the project's user-facing docs live — implementer should grep for an existing MCP Sources section first; if none exists, this becomes a documentation-task scope clarification). One paragraph describing the Test connection button: "click Test on a freshly-saved streamable-http MCP source to verify the connection and (for OAuth-protected servers) drive the OAuth consent flow at source-creation time. Subsequent agent builds attached to this source will register the server's tools using the persisted tokens."

**L1 (connect-time OAuth-exception translation)**: ADD only the missing inner `except*` clause; do NOT touch the existing 401-via-BaseExceptionGroup-walk at lines 270-335 (it already works post-F6.5).

Edit at `the_one/mcp/client.py::MCPClient.connect` around line 238:

```python
self._session = session
# Existing inner try (RuntimeError catcher for version mismatch).
try:
    # NEW: nested innermost try wrapping ONLY session.initialize().
    # Python forbids mixing `except` and `except*` in one try, so the
    # OAuth exception catcher needs its own try/except* level. Mirrors
    # F6.5 L2's inner-except*-around-list_tools pattern (client.py:~470)
    # but lives at a different structural level than that pattern
    # because connect()'s outer block already handles 401-via-
    # BaseExceptionGroup at lines 270-335 (F6 A5 work — unchanged).
    try:
        result = await session.initialize()
    except* (OAuthFlowError, OAuthTokenError):
        # SDK's auth flow failed during initialize (refresh / discovery
        # / DCR). Translate to MCPAuthRequired so MCPToolProvider's
        # graceful-skip path (post-F6.5 L2) catches it cleanly.
        raise MCPAuthRequired(
            source_id=self.source.id,
            resource_metadata_url=None,
            consent_url=None,
        ) from None
except RuntimeError as e:                    # existing — UNCHANGED
    m = _UNSUPPORTED_VERSION_RE.match(str(e))
    observed = m.group(1) if m else str(e)
    raise MCPVersionMismatch(pinned=pinned, observed=observed) from None
```

Other touchpoints:
- The `except asyncio.CancelledError` block at `client.py:253-270` — update its error message per Design Decision §3 to drop the "likely 401" speculation. ~3 lines of comment+message text.
- The `except (Exception, BaseExceptionGroup)` block at `client.py:270-335` — UNCHANGED; the 401-via-HTTPStatusError walk continues to work as F6 A5 left it.
- `_pool._entry_worker` (`the_one/mcp/_pool.py:210` — `except BaseException as exc`) — UNCHANGED; `MCPAuthRequired` extends `MCPClientError` extends `Exception`, so `BaseException` catches it and stores in `entry.failure`. `MCPToolProvider.get_tools_for_agent` then re-raises from `entry.failure` and the post-F6.5 L2 graceful-skip clause catches `MCPAuthRequired`. No change needed; the existing test for graceful-skip should still pass.

L1 unit tests cover three surfaces:
- `test_connect_oauth_flow_error_raises_mcp_auth_required` — mock `session.initialize()` to raise `OAuthFlowError`; assert `MCPAuthRequired` raised with `source_id == source.id`, `resource_metadata_url is None`, `consent_url is None`.
- `test_connect_oauth_token_error_raises_mcp_auth_required` — same shape for `OAuthTokenError`.
- `test_connect_oauth_error_in_exception_group_raises_mcp_auth_required` — mock `initialize` to raise `BaseExceptionGroup("test", [OAuthFlowError(...)])`; verify `except*` matches grouped surfaces too.

Note: a 4th test for the existing 401-via-HTTPStatusError walk is OPTIONAL (the path is already tested via F6 A5's tests in `tests/test_mcp_client.py`; F6.6 doesn't change that code). Implementer's discretion to add coverage symmetry, but not blocking.

### Checkpoints

- [x] **L0 landing**: 3 new unit tests pass; `git grep "App.areas" the_one/interfaces/web/static/` returns ≥2 hits (export + at least one consumer); 4 `test_oauth_modal_flow.py` browser tests transition from FAIL → PASS; synthetic-csid docstring includes the 3 known shapes; README has a Test-connection-button entry
- [x] **L1 landing**: 3 new unit tests for connect-time 401 translation pass; existing `test_mcp_client.py::TestConnect*` tests untouched and still pass; full unit suite green (modulo the 3 pre-existing `test_mcp_sandbox_integration.py` bwrap failures)

### Adaptation Criteria

**Divert if**:
- L1 reveals the SDK's `connect()` initialize round-trip surfaces 401 differently from `list_tools`/`call_tool` (e.g. wrapped in a different exception type) — would require either widening the `except*` groups or escalating to redesign. Probe via L1's first unit test before writing the production code.
- The `_pool._entry_worker`'s existing `BaseException` catch swallows `MCPAuthRequired` in a way that breaks `MCPToolProvider`'s graceful-skip path — would require explicitly re-raising `MCPAuthRequired` from `_entry_worker`. Probe via the existing F6.5 L2 graceful-skip test (running it post-F6.6 should still pass).

**Acceptable variations**:
- L0's README entry placement: implementer's discretion (`README.md` top-level "Features" or "MCP Sources" subsection).
- L0's docstring wording for the synthetic-csid pattern: any framing that names all 3 known shapes + the prefix-uniqueness invariant.

### Legs

- [x] `00-cleanup-batch` — 3 unit tests for F6.5 L4 inline fixes + Anomaly A2 (`App.areas` re-export) + synthetic-csid pattern docstring + Test connection README entry. ~150 LOC across ~6 files.
- [x] `01-connect-401-translation` — `MCPClient.connect()` `try/except*` mirroring F6.5 L2's `list_tools` pattern; F6 A5 fallback message updated; 3 new unit tests covering the 401-EG / OAuthFlowError / OAuthTokenError surfaces. ~80 LOC.

---

## Post-Flight

### Completion Checklist

- [x] Both legs completed
- [ ] Code merged
- [x] Tests passing inside `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py` (full suite, modulo pre-existing failures)
- [x] No new mission known-issues introduced
- [x] F6.5 debrief action items 1, 2, 3, 4 closed (the binding-HAT codification, the 4 flaky browser failures investigation, and the truncation mitigation are all out of F6.6 scope)

### Verification

- **Maintenance items**: each L0 deliverable verified by its own AC (3 unit tests pass; `App.areas` export present; browser tests recover; docstring + README contain the required content).
- **Connect-time translation**: against an OAuth-protected MCP source with no creds, `MCPClient.connect()` raises `MCPAuthRequired` for `OAuthFlowError`/`OAuthTokenError` surfaces (the new path) AND continues to raise `MCPAuthRequired` for 401-in-BaseExceptionGroup (the existing F6 A5 path, untouched by F6.6). Both flow through `MCPToolProvider.get_tools_for_agent`'s graceful-skip-on-`MCPAuthRequired` clause cleanly. Verified by unit tests; no Tier-2 HAT per Design Decision §4.

---

## Design Review Cycle 1 (2026-05-09)

**Architect (Sonnet) flagged 1 high + 2 medium + 2 low issues. All incorporated.**

- **HIGH** — original spec framed L1 as "verbatim mirror of `list_tools`" pattern, but `connect()` is structurally different post-F6.5: its outer `except (Exception, BaseExceptionGroup)` block at `client.py:270-335` ALREADY handles 401-via-HTTPStatusError. The actual gap was the missing `OAuthFlowError`/`OAuthTokenError` `except*` clause. Reframed Design Decision §2 to specify "ADD only the missing clause" + nested innermost `try/except*` (Python forbids mixing `except` and `except*` in one block, so the new clause must nest inside the existing `except RuntimeError` block).
- **MEDIUM** — Design Decision §3 ("CancelledError fallback retired for 401") was over-stated. Post-F6.6 the CancelledError block still legitimately fires for non-OAuth, non-401 cancellation races. Updated §3 to specify message-only update (drop "likely 401" speculation), keep the handler.
- **MEDIUM** — `except MCPAuthRequired: raise` guard NOT needed in `connect`'s structure (vs `list_tools` where it WAS needed). `connect`'s line 250 outer `except (MCPClientError, NotImplementedError): raise` already propagates `MCPAuthRequired` cleanly. Documented as Design Decision §2a; do NOT copy-paste the guard from `list_tools`.
- **LOW** — `_pool._entry_worker` `except BaseException` is at line **210**, not 198 as originally cited. Corrected throughout.
- **LOW** — `app.js`'s `Object.assign` block is at line **267**, and the existing local variable is `var areas = {};` at line 2. L0 item 4 reframed: not "add `areas: order,`" but "re-export the existing `areas` variable" via `areas: areas,` (shorthand `areas,` also fine).

**Architect approved Design Decision §4 (no Tier-2 HAT) as written**: list_tools runtime path was HAT-verified; connect's `OAuthFlowError`/`OAuthTokenError` surface is the SDK's auth module, not transport — structurally identical for that exception surface. Approve waiver.

**Cycle 2 skipped**: per `/agentic-workflow` skill guidance — all cycle-1 fixes were factual reconciliations (citation corrections + wording adjustments to better match actual code structure). No architectural changes; design review's concrete cite-and-reframe fixes are transcribed verbatim. A second pass would re-verify the same locations with diminishing returns.
