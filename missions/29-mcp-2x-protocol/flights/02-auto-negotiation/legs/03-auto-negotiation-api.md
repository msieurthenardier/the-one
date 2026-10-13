# Leg: auto-negotiation-api

**Status**: completed
**Flight**: [Automatic negotiation of protocol 2026-07-28](../flight.md)

## Objective
Adapt the web routes to negotiation:
- the auth-posture probe gains a fourth verdict, so a server that speaks only 2026-07-28 can be tested and signed in to (DD9);
- the two OAuth flow drivers send the handshake version header (DD10);
- era memory is cleared on source update, delete and Reset, and is not recorded by a Test that used a body override (DD2);
- the negotiation docs land and squawk 0199 closes (DD12).

The flight's full verification then runs: the unit suite, every browser lane, the bwrap set and lint.

## Context
- **The design is in the flight spec.** Read `../flight.md` (DD2, DD9, DD10, DD12) and the flight log, including legs 1 and 2's entries. Where this file and the flight spec disagree, the flight spec wins; report the disagreement in the flight log.
- **Legs 1 and 2 have landed, uncommitted, in the same tree.** Don't regress them. Leg 2 added `MCPClient(..., fresh_negotiation=..., record_era=...)`, `the_one/mcp/_era.py` (`era_for` / `remember_era` / `forget_era`) and `_HANDSHAKE_OFFER_VERSION`. The three Test-connection sites already pass `fresh_negotiation=True` (`api.py:3321, 3416, 3686`).
- **Probe today.** `transports/streamable_http.py::_probe_auth_posture` (~190-288) returns `"error"` for a transport error (`httpx2.RequestError`, timeout), for any other exception, and for any HTTP status other than 200 or 401 (~279-288). Phase 0 (`api.py` ~3648-3654) answers `"error"` with `{"status":"error","error":"connection probe failed"}`.
- **The no-auth SDK path.** `_build_and_test_no_auth_mcp` (~3288) turns `MCPAuthRequired` into `{"status":"error"}` in its "probe said no_auth but server now wants auth (race)" branch (~3365).
- **The flow drivers.** `_drive_flow_test` (~3810, payload `"protocolVersion": "2025-11-25"` at ~3821) and `_drive_flow` (~4672, ~4688) post a header-less `initialize`.
- **Out of scope.** Client-side negotiation (done in leg 2) and anything in `the_one/mcp/client.py` beyond what DD9 needs.

## Inputs
- Legs 1 and 2 landed. Unit suite: 6200 passed, 12 skipped, 0 failed. `requires_bwrap`: 41 passed, 3 skipped.

## Outputs
- Code: `the_one/mcp/transports/streamable_http.py` (probe verdicts and docstring), `the_one/interfaces/web/api.py` (Phase 0, the no-auth path, the drivers, era clearing, the `record_era` gate).
- Docs:
  - `the_one/agents.md`: the negotiation policy, era memory, modern-era 404 behaviour, DD9 and DD10.
  - `the_one/mcp/README.md`.
  - `CLAUDE.md`'s Mission 29 paragraph.
  - `squawks/0199-…md`, marked completed.
- Tests, and a flight-log `### auto-negotiation-api` entry.

## Acceptance Criteria
- [x] AC1 (DD9, probe): `_probe_auth_posture` returns `"unexpected_status"` for an HTTP response whose status is neither 200 nor 401. `"error"` stays for transport errors, timeouts and other exceptions, and they still fail fast. 401 still gives `"oauth"` and 200 still gives `"no_auth"`. Its docstring is corrected: the request is made with httpx2, and it describes the four verdicts. `tests/test_auth_posture_probe.py` covers all four verdicts.
- [x] AC2 (DD9, fall-through):
  - **New Phase 0 branch.** On `"unexpected_status"`, Phase 0 runs the no-auth SDK path. That path negotiates, so a server that speaks only 2026-07-28 connects there.
  - **401 from the fall-through.** When this fall-through raises `MCPAuthRequired`, the route persists `auth_posture: "oauth"` (the same re-read-and-write as Phase 0's `"oauth"` branch). It then continues into Phase B's sign-in, rather than returning the race branch's error.
  - **Race branch unchanged.** When the probe genuinely said `"no_auth"`, the race branch behaves exactly as today.
  - **Unchanged verdicts.** `"error"` still returns "connection probe failed" without trying the SDK.
  - **Tests**, each against a real fixture:
    - (a) A server that answers a bare `initialize` with 400 but speaks 2026-07-28 connects through the fall-through. Use the ASGI fixture or a wrapper that rejects `initialize` with 400 and passes `server/discover` through.
    - (b) Such a server that also needs sign-in ends in Phase B's consent flow, and `auth_posture` is persisted as `"oauth"`.
    - (c) An unreachable URL still fails in about the probe's timeout, not the SDK connect budget.
- [x] AC3 (DD10):
  - Both flow drivers keep their `initialize` body and add the header `MCP-Protocol-Version: <the_one.mcp._HANDSHAKE_OFFER_VERSION>`, read at call time. Their payload's `protocolVersion` reads the same constant, not the literal "2025-11-25".
  - A test pins that each driver's first request carries the header and the constant.
  - No other change to what the drivers do.
- [x] AC4 (DD2, clearing): `_era.forget_era(source_id)` runs on these routes, each covered by a test:
  - `update_mcp_source` (~3009), on any successful update;
  - `delete_mcp_source` (~3112);
  - `reset_mcp_connection` (~3248).
- [x] AC5 (DD2, body override): when `test_mcp_connection` applied a request-body override, all three Test-connection construction sites pass `record_era=False`. This covers the no-auth helper and the stdio helper too, which receive the overridden `source`, so thread the flag. A test asserts that an override Test leaves the era map untouched, while a plain Test records the era.
- [x] AC6 (DD12, docs):
  - **`the_one/agents.md`** documents:
    - the negotiation policy (`_negotiate.py`, mirroring the SDK's `negotiate_auto`; the parity test);
    - era memory (`_era.py`: in-memory only, `fresh_negotiation` on Test, `record_era`, the clearing points, the trade-offs);
    - that a modern connection has no session id, so its 404s read "Not Found" and never self-heal;
    - the modern serverInfo `version: ''` note;
    - the 1 MiB SSE cap applying only to SSE responses (the handshake era in practice);
    - DD9's verdicts and fall-through;
    - DD10.
  - **`the_one/mcp/README.md`** agrees with `agents.md`.
  - **`CLAUDE.md`'s "MCP client on the `mcp` 2.x SDK (Mission 29 F1)" paragraph** gains Flight 2's operator-facing facts: servers on 2026-07-28 show it in the editor, and older servers fall back automatically with no added delay after the first connect per run.
  - **Squawk 0199** is set to `completed`. Its Corrective Action and Verification name the leg 1 and leg 3 changes that cleared each item. The sign-off is left for the Flight Director at commit time.
- [x] AC7 (the flight's full verification):
  - `make test-unit` (plain mode), with the skip count explained.
  - `.venv/bin/python -m pytest -m requires_bwrap -x --timeout 120`.
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`.
  - **The full browser suite:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`, recording the `PARALLEL_RESULT` line and any `OVER BUDGET`.
- [x] AC8: the flight log's `### auto-negotiation-api` entry lists every changed test expectation (with its reason), the new tests, and the AC7 results. The leg status is `landed`.

## Design-Review Resolutions (authoritative where they differ from the criteria above)

The leg's Developer design review returned "approve with changes" (2026-10-12). Below are the Flight Director's decisions.

1. **Phase B after the fall-through triggers sign-in with `server/discover` (a narrow DD10 amendment).**
   - **The problem.** The fall-through exists for a server that answered the probe's bare `initialize` with 400. Such a server may answer the driver's `initialize` with 400 too. httpx does not raise on 400, so no 401 arrives and Phase B would end in `consent_url_timeout`.
   - **The decision.** Only when Phase B is entered from the DD9 fall-through, `_drive_flow_test` posts a `server/discover` request (`{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}}` or the SDK's discover shape) with `MCP-Protocol-Version: <mcp.types.version.LATEST_MODERN_VERSION>`, read at call time.
   - **Why the general rejection doesn't apply here.** DD10 rejected a discover-body driver because the drivers have no fallback. Here, the server is already known to reject `initialize`.
   - **Everywhere else** (the normal Phase B, and `_drive_flow` in the OAuth-start route) DD10 stands unchanged: an `initialize` body with the handshake header.
   - **Resource parameter.** Because this discover-driven sign-in carries a 2026-07-28 header, `should_include_resource_param` is true. Document that in `agents.md` with DD10.
   - **Logging.** Record the amendment in the flight log and add a one-line note under DD10 in the flight spec.
2. **"Override applied" means the server under test differs from the saved row.**
   - The editor sends its form body on every Test (`mcp-server-editor.js` ~2008-2014). So the test is not whether a body was present. It is: after the body is merged, does the effective `source.type`, or `source.config` (excluding `_cache`), differ from the persisted row's?
   - Compute `override_applied` once in `test_mcp_connection`, and pass `record_era = not override_applied`.
   - Secrets are not compared: a changed credential does not change which server is under test.
3. **Threading `record_era`.**
   - Add a keyword-only `record_era: bool = True` to `_build_and_test_no_auth_mcp` and `_build_and_test_stdio_mcp`.
   - Pass it at their call sites in `test_mcp_connection` (no-auth: ~3632 and ~3652; stdio: ~3607) and at the Phase A `MCPClient` (~3687).
   - Phase B's drivers construct no `MCPClient`, so they need nothing.
   - Check `tests/test_mcp_pool.py:1315`'s `_CapturingClient` (no `**kwargs`). If it reaches a Test-connection site, update it and log the change.
4. **The no-auth helper's two `MCPAuthRequired` cases.**
   - `_build_and_test_no_auth_mcp` gains a keyword-only `from_fallthrough: bool = False`.
   - On `MCPAuthRequired`, when `from_fallthrough` is set it returns a module-level sentinel (`_SIGNIN_REQUIRED = object()`). Otherwise it keeps today's race-branch error envelope.
   - The cached `"no_auth"` direct call (~3632) and the probe's `"no_auth"` call (~3652) never set the flag.
   - On the sentinel, the route calls a new shared helper `_persist_oauth_posture(repo, source_id)`, extracted from Phase 0's `"oauth"` branch and used by both, then continues into Phase B in its discover mode (resolution 1).
   - A fall-through that succeeds persists `auth_posture: "no_auth"` as the helper does today, so the next Test skips the probe. That is intended; say so in `agents.md`.
5. **AC2 tests, made feasible.**
   - **(a)** Patch `_probe_auth_posture` to return `"unexpected_status"`. Add a new small ASGI wrapper that answers `initialize` with 400 and passes `server/discover` through to the dual-era app (via `tests/_mcp_signin_helpers.py::serve_asgi`). Assert that the route connects on 2026-07-28.
   - **(b)** Use the existing Phase B test pattern: `api.httpx2.AsyncClient` patched with `_StubHttpxClient`, plus the stub provider (`tests/test_oauth_test_connection_endpoint.py` ~285-292). Make the wrapper answer `server/discover` with 401 + `WWW-Authenticate`. Assert:
     - `auth_required`;
     - a consent URL;
     - `_cache.auth_posture == "oauth"`;
     - the driver's posted body is `server/discover` with the modern header.
   - **(c)** An unreachable URL gives the real probe's `"error"` within its timeout. Add an assertion that no `MCPClient` is constructed.
6. **AC4 placement.**
   - `update_mcp_source`: call `forget_era(source_id)` immediately after `await repo.update(updated)`. Validation raises happen earlier, so a failed update never clears.
   - `reset_mcp_connection`: call it after its `repo.update`.
   - `delete_mcp_source`: verify no `return` precedes the row delete, and call `forget_era` right after the delete, before the best-effort cache cleanup.
7. **Changed test expectations.** `tests/test_auth_posture_probe.py` (~82-90) asserts `"error"` for an HTTP 500, which becomes `"unexpected_status"`. Check every other 4xx/5xx case in that file and log each change. The probe's return `Literal` gains `"unexpected_status"`.
8. **Driver tests.** Use a stub client that records `post(url, json=..., headers=...)`.
   - Assert the handshake header, and `payload["params"]["protocolVersion"] == the_one.mcp._HANDSHAKE_OFFER_VERSION`.
   - Monkeypatch the constant to a sentinel to prove it is read at call time.
   - `_drive_flow`'s test goes through `tests/test_oauth_start_endpoint.py`'s setup.
9. **AC7 is split.** The Developer runs:
   - the targeted tests;
   - the OAuth and Test-connection browser files as a smoke check, with `THE_ONE_TEST_NETNS=1` and `-m browser`: `tests/browser/test_oauth_modal_flow.py`, `tests/browser/test_mcp_test_connection_button.py`, `tests/browser/test_flow_oauth_callback_cross_site.py`, `tests/browser/test_studio_mcps_tab.py`;
   - `make test-unit`;
   - the `requires_bwrap` set;
   - ruff.

   The Flight Director runs the full `--parallel 3` browser suite after the leg lands, so the Developer does **not** run it. Record the smoke results in the flight log.

## Verification Steps
- AC1-AC5: the named tests pass. Each new test is named in the flight log.
- AC6: read the diff.
- AC7: run the commands and record their exit codes and result lines in the flight log.

## Implementation Guidance
1. Probe verdicts and docstring (AC1).
2. Phase 0 fall-through and the no-auth path's `MCPAuthRequired` handling (AC2). The no-auth helper needs to signal "sign-in required" back to the route rather than returning an error when entered from the fall-through: a keyword argument plus a sentinel, or raising, whichever matches the file's style.
3. Drivers (AC3).
4. Era clearing and the override gate (AC4, AC5).
5. Docs and squawk 0199 (AC6).
6. Full verification (AC7). Run the unit suite first, then the browser suite, never concurrently.

## Edge Cases
- **Double sign-in.** The fall-through runs only when `not has_live_tokens`, which also gates Phase 0. So it goes straight to Phase B, never through Phase A, and there is exactly one sign-in.
- **A server that answers 400 to both `initialize` and discover.** The SDK path fails with a plain `MCPConnectionError`. Return it as the route's usual error envelope.
- **`repo.get` raises `KeyError` on a missing row.** The `auth_posture` persistence is best-effort, as in Phase 0's `"oauth"` branch.
- **Era clearing on update must not run if the update fails validation.** Only clear after a successful write.
- **WebKit.** The browser suite may skip WebKit without `THE_ONE_REQUIRE_WEBKIT=1`. Use the flag, as CLAUDE.md says.

## Files Affected
- `the_one/mcp/transports/streamable_http.py`, `the_one/interfaces/web/api.py`
- `tests/test_auth_posture_probe.py`, `tests/test_oauth_test_connection_endpoint.py` and/or new test files (for example `tests/test_mcp_test_connection_negotiation.py`), plus tests for era clearing and the drivers
- `the_one/agents.md`, `the_one/mcp/README.md`, `CLAUDE.md`, `squawks/0199-stale-mcp-docs-after-2x-port.md`
- The flight log

## Citation Audit
Checked at leg design against the working tree (legs 1 and 2 landed):
- `streamable_http.py`: `_probe_auth_posture` at ~190; its returns at ~279 and ~282 (`"error"`), ~285 (`"no_auth"`), ~287 (`"oauth"`) and ~288 (`"error"`).
- `api.py`:
  - `update_mcp_source` ~3009, `delete_mcp_source` ~3112, `reset_mcp_connection` ~3248;
  - `_build_and_test_no_auth_mcp` ~3288 and its race branch ~3365;
  - `test_mcp_connection` ~3511, with body-override handling in its first ~50 lines;
  - Phase 0 probe ~3648-3654;
  - `_drive_flow_test` ~3810 / payload ~3821; `_drive_flow` ~4672 / payload ~4688;
  - Test-connection `MCPClient` sites ~3321, ~3416, ~3686.

**Risk tier: HIGH.** The leg touches a security-sensitive surface (the OAuth flow drivers, Test connection's sign-in path and `auth_posture` persistence), a shared route behaviour, and a cache lifecycle (era clearing).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
