# Leg: 02-resume-after-the-token-save

**Status**: completed
**Flight**: [MCP sign-in never leaves a chat waiting](../flight.md)

## Objective
The chat's **Sign in** flow (`POST /api/oauth/start`) owns its outcome. It broadcasts `auth_resolved` and resumes the paused turn exactly once, only after the new tokens are saved. On failure it broadcasts the only `auth_failed` and does not resume. The OAuth callback only resolves the code and renders the popup, whose detail line no longer claims the save.

## Context
- Flight DD3 (completion rule, save flag, exactly-once claim, one failure owner, superseded flows, known limitation), DD4 (neutral popup detail line), DD5 (leg-2 tests). Charter criteria 1, 2, 4.
- **Leg 1 outcome** (flight log "Leg 1"):
  - Every pool connection and Test Phase A refuse the interactive step (`SignInNotAvailable`), so after leg 1 the only chat-bound OAuth flows are `/api/oauth/start`'s. `test:` flows have no session.
  - DD2 was dropped: a teardown mid-connect already pauses or errors the turn.
  - A refusal leaves a cancelled anyio scope on the connecting task, which is why Phase A now runs on its own task. `/api/oauth/start`'s flow is interactive, so it does not take that path, but keep it in mind if any new code awaits a refusing connect on a task that keeps working.
- Today, `api.py::oauth_callback` resolves the code, then at once broadcasts `auth_resolved` and schedules `_resume_paused_session`. Meanwhile `oauth_start._drive_flow`'s SDK flow still has to exchange the code and `set_tokens`. The resumed tool call can read the old token, hit a 401, refuse (after leg 1), and re-pause asking for **Sign in** again. That is the production symptom at 18:03.
- The SDK saves before it retries the original request (`oauth2.py::_auth_flow`: `_handle_token_response` → `storage.set_tokens`, then the retry `yield request`), so `client.post` in `_drive_flow` returns only after the save and the retry.

## Inputs
- Leg 1 landed, uncommitted, in the same worktree. Its diff must not be disturbed.
- `api.py` at its `ALLOWANCE` ceiling (5126); `app.py` (4171) and `client.py` (1171) at theirs (`tests/test_python_module_size.py`).

## Outputs
- New `the_one/interfaces/web/mcp_oauth_flow.py` owning the chat sign-in completion:
  - the save detection;
  - the completion rule;
  - `auth_resolved` and `auth_failed`;
  - the claimed, exactly-once resume;
  - superseded-flow tracking.
- `api.py::oauth_start` delegates to it.
- `api.py::oauth_callback` no longer broadcasts `auth_resolved` or `auth_failed` and no longer resumes. It keeps `_state.resolve` / `_state.fail`, the popup page, and the "Login expired" path.
- The popup success detail line is neutral.
- `MCPSourceTokenStorage` records a completed save.
- `OAuthASStub` gains a token-endpoint delay mode.
- Tests and docs updated; `api.py` net-neutral or smaller.

## Acceptance Criteria
- [ ] **Save detection.** `MCPSourceTokenStorage` gains an instance flag (for example `tokens_saved: bool`, initially False) set only after `repo.update` returns in `set_tokens`, so a failed write does not count.
  - `mcp_oauth_flow.py` wraps `provider.context.redirect_handler` (the SDK calls `self.context.redirect_handler(authorization_url)`, `oauth2.py` ~:430) so that each redirect first resets that flow's flag, then calls the original.
  - Only a save made after the last redirect counts. A refresh that saved, then a 401 on the retry, then an abandoned interactive step is not resolved.
  - No other `MCPSourceTokenStorage` behaviour changes. The squawk 0444 tests and the existing storage tests pass unchanged.
- [ ] **Completion rule.** `_drive_flow`'s logic, moved to `mcp_oauth_flow.py`, classifies the outcome when its `client.post` returns or raises.
  - **Resolved** if the save flag is set (even if the retried request then raised or answered non-2xx), or if the final response is 2xx with no save.
  - **Failed** otherwise: an exception before any save, or any non-2xx final response with no save (401, 403, 400, 404, 5xx).
  - A no-exception failure broadcasts `auth_failed` with `error: "start_failed"` and a fixed, pinned description, for example "The server did not accept the sign-in (HTTP {status})." It must be non-empty, contain no token text, and be shown by `sign-in.js::onAuthFailed` as "OAuth failed: …".
  - An exception keeps today's `description: str(exc)`.
- [ ] **On resolved:**
  - Look the session up with `_sessions.get(chat_session_id)` at completion time, not at start.
  - If found, broadcast `{"type": "auth_resolved", "source_id", "tool_call_id"}` (same shape as today's callback frame).
  - Schedule `_resume_paused_session(session)` through `_inflight_resume_tasks` when the claim below succeeds.
  - Import from `app` at call time only (the `mcp_connection_flow.py` pattern: `app.py` imports `api` at load).
- [ ] **Exactly once, claimed in the scheduler.** `mcp_oauth_flow.py` keeps a module-level set of session ids with a resume in flight. With **no await in between**, it checks `session.agent is not None and session.agent._deferred_tool_calls is not None`, checks the id is not in the set, adds it, and calls `asyncio.create_task(...)`. The task's done-callback discards the id.
  - `Agent.resume_after_auth` and `app.py::_resume_paused_session` are not changed.
  - A test with two flows for the same session completing back to back shows exactly one `_resume_paused_session` call and one `done` frame.
- [ ] **On failed:** broadcast `auth_failed` (shape `{"type", "source_id", "error", "description"}`, as `_drive_flow` sends today), and no resume.
- [ ] **One owner for failure.**
  - `oauth_callback`'s IdP-error branch keeps `_state.fail(state, OAuthFlowError(error_description or error))` and its "Login failed" popup page, but no longer broadcasts `auth_failed`.
  - The flow module's exception path reports it, with a description equal to `str(OAuthFlowError(error_description or error))`.
  - A test shows an IdP denial produces exactly one `auth_failed` frame whose `description` is the IdP's `error_description`, or `error` when there is no description.
- [ ] **Superseded flows (design review cycle 1).** The flow module tracks the in-flight flows per (chat session id, source id); `oauth_start` is called once per click, and each call builds its own provider and storage.
  - **A resolved flow always reports and resumes** (claimed, as above), whether or not it is the latest, then cancels the other in-flight flows for the same key. For example, the operator clicked **Sign in** twice and completed the older consent window.
  - **A failed or cancelled flow is silent** when, at its end, it is no longer the latest flow for its key or another flow for the key has resolved since it started. Otherwise it reports `auth_failed` as above.
  - Tests:
    - a superseded flow failing at its TTL sends no `auth_failed`;
    - completing the older of two flows resumes once, the newer flow is cancelled, and no `auth_failed` follows.
  - Note in the module docstring: a late-resolving flow after a resume that re-paused resumes the new pause. Accepted.
- [ ] **The callback.** `oauth_callback` no longer broadcasts `auth_resolved`, no longer imports or schedules `_resume_paused_session`, and no longer reads `session.agent._deferred_tool_calls`. Its success page keeps the heading "Login successful. You may close this tab." and the `mcp-oauth-result` postMessage. The "Login expired" branch is unchanged.
- [ ] **Popup detail line (DD4).** The success detail becomes neutral and no longer says the tokens were persisted, for example "Return to the app to continue. This window will close automatically." A test pins the new detail text; no existing test pins the old one.
- [ ] **`OAuthASStub` token delay.** It gains an option (for example `token_delay: float = 0.0`) that sleeps in the `/token` handler (`tests/fixtures/oauth/__init__.py` ~:233) before answering, for every grant (code and refresh), documented as such. The handler runs on a thread, so `time.sleep` is safe. Document it in the stub docstring, and in agents.md "OAuth callback result and the RFC 9207 issuer" (~:883), whose stub-modes list also gains the missing `refresh_status`.
- [ ] **End-to-end tests** (real `OAuthASStub`, `shared_app()`, template databases, no mock libraries). A chat session paused on a source that needs sign-in, then `POST /api/oauth/start`, then the flow's consent URL followed to the stub's authorize, then `GET /api/oauth/callback?code=…&state=…`, as existing `test_oauth_start_endpoint.py` / `test_oauth_callback_route.py` tests drive it. With `token_delay` set (for example 1 s):
  - no `_resume_paused_session` call and no `auth_resolved` before `set_tokens` completes;
  - after it: exactly one `auth_resolved`, then exactly one resume, then the resumed tool call succeeds with the new token;
  - no second `auth_required` frame for that turn.
  - Falsify: move the resume back to the callback by editing, see the test fail, restore by editing.
- [ ] **Failure tests:**
  - token endpoint 400 → one `auth_failed`, no resume, no `auth_resolved`;
  - final non-2xx with no save → one `auth_failed` with the pinned description;
  - IdP denial → one `auth_failed` (see above);
  - valid stored token (start flow is a 2xx no-op) → resolved and resumed.
- [ ] **Known limitation pinned.** With the stub's `auth_required_methods` mode (a 401 only on `tools/call`), `/api/oauth/start`'s `initialize` gets a 2xx with no save: the flow resolves, the resumed call refuses again, and the turn re-pauses. A test pins this outcome and names it a known limitation. Record it in the flight log and agents.md, with the step-up 403 case.
- [ ] **Pins.**
  - Grep `tests/` and `tests/browser/` for `auth_resolved`, `auth_failed`, `_resume_paused_session`, `oauth_callback`, `oauth/callback`, `_drive_flow`, `securely persisted` and the popup detail text, and update every test that asserts the callback broadcasts or resumes. Known, from design review cycle 1:
    - `tests/test_oauth_callback_route.py::test_callback_success_resolves_and_broadcasts` and `::test_callback_error_fails_and_broadcasts` are rewritten to assert no broadcast (rename them to say so; rename over delete-and-re-add). `::test_callback_sweep_race_returns_login_expired` keeps its check.
    - `tests/test_app_websocket_pause_resume.py::test_oauth_callback_resume_dispatches_resume_after_auth` (~:210) is rewritten onto the new owner. The `_real_agent_*` tests (~:653, ~:682) are unaffected.
    - `tests/test_oauth_start_endpoint.py` stub clients answer 200 with no save, which now resolves. Confirm they still pass with `cs-1` absent from `_sessions`.
    - `tests/test_mcp_httpx_guard.py::test_the_two_oauth_flow_drivers_in_api_use_httpx2` scans `api.py` and `mcp_connection_flow.py` for `AsyncClient(..., auth=...)`. Add `mcp_oauth_flow.py` to its scan, keep the call spelled `httpx2`, and update its docstring.
    - Check `tests/test_oauth_callback_gate.py`, `tests/browser/test_flow_oauth_callback_cross_site.py` and `tests/HAT.md` for the old popup text or callback broadcasts.
  - `_oauth_driver_headers` stays in `api.py` (`tests/test_oauth_test_connection_endpoint.py` ~:316 calls `api_mod._oauth_driver_headers`, and `mcp_connection_flow.py` uses it). `oauth_start` passes the built headers, or the version, into the flow module instead of the module importing it.
  - Browser tests that synthesize `auth_resolved` / `auth_failed` frames stay valid, because the frame shapes are unchanged. Run every browser lane whose files match (`scripts/run-tests.sh --list`; squawk 0334) with `THE_ONE_TEST_NETNS=1` and `PYTHON=.venv/bin/python`, at most 3 lanes at a time, never concurrent with the unit tier.
  - The existing `patch("the_one.interfaces.web.api.httpx2.AsyncClient")` in `test_oauth_start_endpoint.py` patches the `httpx2` module object, so it still applies after the move. Confirm, or patch the new module's reference.
- [ ] **Size.** `api.py` ends smaller (about 80 lines less is expected), and its `ALLOWANCE` ceiling in `tests/test_python_module_size.py` is lowered to the new size (ceilings only shrink). Check ruff F401 for now-unused imports (`contextlib`, `HTMLResponse`, `OAuthFlowError`). `app.py` and `client.py` are not edited, and the new module is under 800 lines.
- [ ] **Provider guard.** `build_oauth_provider_for_source` is typed `httpx2.Auth | None`. The flow module handles `None` or a provider without `context.storage` / `context.redirect_handler` by reporting `auth_failed` with a fixed description, never an `AttributeError`.
- [ ] **Storage unit test.** `MCPSourceTokenStorage.tokens_saved` stays False when `repo.update` raises.
- [ ] **Docs:**
  - the `oauth_start` / `oauth_callback` docstrings;
  - the new module's docstring (who owns completion, the rule, exactly-once, superseded flows);
  - agents.md: the sortie 04 sign-in paragraph, "Auth-pause state is set before the yield", the stub-modes list, and the known limitation;
  - the GleepGlorp guide only if a page or label changed (it should not; `tests/test_gleepglorp_guide.py`).
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes, run alone, with the skip count read; ruff check and format clean; the matching browser lanes green.

## Verification Steps
- Run the new and touched test files with `.venv/bin/python -m pytest <files> -x --timeout 90 -q`.
- Falsify the end-to-end resume test and the exactly-once test by editing the fix out, then back in; report yes or no per new test.
- Run `THE_ONE_TEST_NETNS=1 make test-unit` alone, in the background.
- Run the matching browser lanes, as listed under Acceptance Criteria.

## Test Harness Notes (design review cycle 1)
- **Fixtures to reuse:**
  - `tests/test_oauth_callback_route.py`: the `client` fixture, and `chat_session_in_app`, which captures `_send_to_session` as `(session_id, payload)` pairs.
  - `tests/test_app_websocket_pause_resume.py`: `oauth_callback_client`, the `StubAgent`, and `_real_agent_session` / `_SwitchableAuthTool` (~:615-690) for a real paused `Agent` whose tool call succeeds once the token is valid.
  - `tests/test_oauth_start_endpoint.py::client_and_repo` (DB, repo and pool for `/api/oauth/start`).
  - `tests/_mcp_pool_helpers.py` (leg 1: `pool_db`, `oauth_source`, `build_tool`, `tool_call_script`).
  - `tests/_mcp_signin_helpers.py`.
  - `OAuthASStub` in `tests/fixtures/oauth/__init__.py`.
- **Observing:** monkeypatch `web_app._send_to_session` to collect frames, and `web_app._resume_paused_session` with a recording coroutine to count resumes. The flow module imports both at call time, so the patches apply. For "the resumed tool call succeeds with the new token", use the real-agent helpers.
- **Driving the flow:**
  1. POST `/api/oauth/start`.
  2. Wait for the `auth_required` frame carrying `consent_url`.
  3. GET that URL against the stub with `follow_redirects=False` to get the 302 `Location`.
  4. GET only its path and query (`/api/oauth/callback?code=…&state=…`) on the test client. The redirect host is `127.0.0.1:{settings.port}`.
- **Constants:** put the pinned no-exception `start_failed` description in a module constant that tests import.
- **The known-limitation test** asserts the full sequence: resolved, resumed, then re-paused with a new pause.

## Implementation Guidance
0. **Order:** the storage flag (step 3) is needed by the flow module (step 2): do step 3 first.
1. **Read leg 1's diff first** (`git diff`, and the new files `the_one/mcp/oauth/_log_filter.py`, `tests/_mcp_pool_helpers.py`, `tests/test_mcp_oauth_non_interactive.py`). Reuse `tests/_mcp_pool_helpers.py` for DB wiring where it fits.
2. **The flow module.** Move `_drive_flow`'s body (the httpx2 client with `auth=provider`, the `initialize` POST with `_oauth_driver_headers(version)`) into `mcp_oauth_flow.py` as, for example, `start_chat_sign_in(...)`, which returns after scheduling the task. Keep `oauth_start`'s request validation, its 400/404 responses and `_evict_all_for_source` in `api.py`. Move or keep `_oauth_driver_headers` as size allows; do not change the request shape (squawk 0202's `Accept` header must survive).
3. **The storage flag** and the redirect wrapper, as in Acceptance Criteria.
4. **The callback.** Remove the `auth_resolved` broadcast, the resume block and the IdP-error `auth_failed` broadcast. Keep everything else.
5. **The popup detail line.**
6. **The stub's delay mode.**
7. **The tests**, the pins, then the docs.

## Edge Cases
- **The session closed or the tab reloaded before completion:** `_sessions.get` returns None; send nothing and do not resume. The tokens are saved anyway, and the next tool call uses them.
- **No paused turn** (the operator signed in from a chat whose pause was already superseded by a new message): resolved; broadcast `auth_resolved`, and the claim's `_deferred_tool_calls is None` check skips the resume.
- **The flow never completes** (the operator closes the popup): `callback_handler` waits until `_state`'s 10-minute TTL fails it. Then `auth_failed` is sent, unless the flow was superseded.
- **Two tabs on the same chat session:** both get the frames through `_send_to_session`; one resume.
- **A refresh succeeds inside `_drive_flow`** (squawk 0444 path; for example the pause came from a transient 401): the save flag is set, so resolved and resumed.

## Files Affected
- `the_one/interfaces/web/mcp_oauth_flow.py` (new) - completion owner
- `the_one/interfaces/web/api.py` - `oauth_start` delegates; `oauth_callback` trimmed; popup detail line
- `the_one/mcp/oauth/storage.py` - `tokens_saved` flag
- `tests/fixtures/...` or wherever `OAuthASStub` lives - `token_delay`
- New tests (for example `tests/test_mcp_oauth_chat_sign_in_completion.py`); updated `tests/test_oauth_callback_route.py`, `tests/test_app_websocket_pause_resume.py`, `tests/test_oauth_start_endpoint.py`, as the grep finds
- `the_one/agents.md` - sections listed above
- `sorties/22-mcp-sign-in-never-leaves-a-chat-waiting/flight-log.md` - leg entry

## Citation Audit
Checked against the worktree (`a02c80f6` plus leg 1's uncommitted diff):
- `api.py::oauth_start` - validates `source_id` / `chat_session_id`, 404 / 400 (no `dcr_credentials`), builds the provider, awaits `_evict_all_for_source`, schedules `_drive_flow` (httpx2 `AsyncClient(auth=provider, timeout=30.0)` POST `initialize`, `_oauth_driver_headers(version)`), broadcasts `auth_failed` (`start_failed`, `str(exc)`) on exception, returns `{"status": "started"}` - verified
- `api.py::oauth_callback` (~:3398) - IdP-error branch: `_state.fail` + `auth_failed` broadcast + "Login failed" page; `_state.resolve` False → "Login expired"; success: `auth_resolved` broadcast, resume when `_deferred_tool_calls is not None`, page with detail "Tokens have been securely persisted. This window will close automatically." (~:3540) - verified
- `app.py::_resume_paused_session` (~:3250) - returns early if `_deferred_tool_calls is None`; awaits `_ensure_ollama_model_loaded` before `resume_after_auth` - verified
- `agent/core.py` ~:556 - `resume_after_auth` reads `_deferred_tool_calls` itself, no-ops on None - verified (Architect)
- SDK `oauth2.py` - `OAuthContext.redirect_handler` attribute (:157), called as `self.context.redirect_handler(authorization_url)` (:430); `_handle_token_response` / `_handle_refresh_response` call `storage.set_tokens` before the retry - verified
- `the_one/mcp/oauth/storage.py::MCPSourceTokenStorage.set_tokens` - one `repo.get` then one `repo.update` - verified
- `static/js/areas/chat/sign-in.js` - `onAuthResolved` shows "Resuming…"; `onAuthFailed` shows `'OAuth failed: ' + (description || error)` - verified
- `tests/test_python_module_size.py` - `api.py` 5126, `app.py` 4171 at their ceilings - verified (Architect)
- Leg 1 changes to `mcp_connection_flow.py` and `the_one/mcp/oauth/` are re-checked at leg start (the Developer reads the diff first)

---

## Post-Completion
*(filled in by the Developer at landing)*
