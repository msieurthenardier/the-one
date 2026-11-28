# Flight Log: MCP sign-in never leaves a chat waiting

**Flight**: [MCP sign-in never leaves a chat waiting](flight.md)

## Summary
Planning started 2026-11-27.

---

## Planning

### 2026-11-27: origin, qualification and charter
- **Origin.** Operator report: the Cloudflare MCP hung in chat on the production instance; resetting the connection and signing in from Library fixed it. The production app log was read only; the instance was not touched.
  - Root cause, split out as **squawk 0444** (PR #404): stored OAuth tokens were never refreshed.
  - The two remaining findings failed the squawk gate on design decisions and come here: the in-chat sign-in resume racing the token save, and unattended chats waiting 30 s for a sign-in nobody can give.
- **Qualified as a sortie.** One outcome: no chat sits waiting on an MCP sign-in. One cluster of decisions: the sign-in pause in the pool and the OAuth handlers, meaning who may answer a sign-in and when the paused turn resumes. Expected to fit one flight: two legs plus a HAT. No new subsystem. No active mission or open sortie covers it (sortie 12 is `planning` and unrelated).
- **Charter agreed** by the operator.
- **Operator calls.**
  - Unattended chats are decided by kind first. After code interrogation the rule widened: every pool connection refuses the interactive step, because the chat ignores the pool's in-band consent URL (the operator chose "all pool connections").
  - HAT leg: yes, against the real Cloudflare MCP on a dev instance.

### 2026-11-27: prior record
- Squawk 0422: an agent build waits 30 s on a stale OAuth source. Its refusal for `agent_build:` csids is the pattern DD1 generalizes.
- Squawk 0354: a worker that ended cancelled is the worker's outcome, not a cancel of the caller (`_teardown_entry`). DD2 applies the same rule where `entry.failure` is written (`_entry_worker`).
- Mission 29 Flight 1 debrief: real-fixture tests (`OAuthASStub`) over injected exceptions. A HAT against Cloudflare found what tests could not (the consent wait).
- Mission 29 Flight 2 debrief: the hand-built OAuth flow drivers are a second MCP client that drifts. `_drive_flow` is one of them. Out of scope here.
- Sortie 04 DD2 amendment: the chat stores and uses a consent URL only for a flow it started itself. This is the premise of DD1.

### 2026-11-27: production evidence (read-only, `the-one-app.log`)
- 14:04 sign-in through Library (reset and Test connection). From 16:21, "Observer - Center Label" routine runs fail with "Needs a sign-in to Cloudflare MCP", each about 40 s after start.
- 18:02 in chat:
  1. `POST /api/oauth/start`.
  2. "Task exception was never retrieved … Attempted to exit cancel scope in a different task", from `_transport_connect` / `streamable_http_client`.
  3. `GET /api/oauth/callback?code=…`.
  4. The chat hangs.
  5. In Library: reset, Test connection, callback, Test connection. Then a second in-chat `POST /api/oauth/start` with no callback.
- 18:04 a routine run succeeds.

### 2026-11-28: Architect review, cycle 1 (approve with changes)
- **High.** "Reset connection" strips `dcr_credentials`, so it cannot set up the HAT scenario: the operator chose to revoke the grant at Cloudflare. Criterion 3 promised connector chats "Needs a sign-in", which nothing produces: the operator reworded the criterion.
- **Medium, applied.**
  - DD2's trace missed `_connect_once`'s CancelledError arm (most cancels re-pause). DD2 is now conditional on leg 1's reproduction through the real client, and the translation moves to `_entry_worker`.
  - DD3 has an exact completion rule (tokens saved wins), detects the save with a flag on the flow's storage, and gives `_drive_flow` sole ownership of `auth_failed`.
  - `api.py` is at its size ceiling, so the completion logic goes to `mcp_oauth_flow.py`.
  - Test connection Phase A is in DD1's scope (operator).
  - The popup's detail line becomes neutral (operator; DD4).
- **Low, applied.** The stub's token-delay mode; timing tests pin the connect timeout; a warm-connection test; the docs list corrected; exactly-once resume claimed synchronously; superseded flows; the refusal's log noise.
- Re-review: a second Architect pass on the rewritten spec.

### 2026-11-28: Architect review, cycle 2 (approve with changes, no high issues; last cycle)
- **Applied (medium).**
  - The exactly-once resume is claimed in the `mcp_oauth_flow.py` scheduler with a claimed set (`app.py` is also at its ceiling; `resume_after_auth` unchanged).
  - The completion rule resolves only on a save or a 2xx; any other no-save outcome fails with a pinned description. The step-up / per-method refusal is recorded as a known limitation with a pinning test.
  - The HAT has an explicit order, because a chat sign-in and Library Test both clear the revoked state.
  - Criterion 3's HAT measure is the dispatch-to-end gap; its connector half is by test.
- **Applied (low).** The save flag is set after `repo.update` and reset at redirect; the warm-connection test asserts the outcome; the DD2 reproduction runs before DD1 with a connect timeout over the 10 s teardown; stale text corrected; pin and doc pointers.
- **Applied (suggestions).** A dedicated refusal subclass, filtered on the SDK logger; superseded flows tracked by (session, source).
- **Deferred to HAT start (operator):** whether revoking at Cloudflare also hits the production `the-one` registration or deletes the DCR client, and which LLM provider the dev instance uses.
- **Operator approval to fly:** "404 is merged, fly sortie 22" (2026-11-28). Status → `ready`.

---

## In-Flight

### Flight Director Notes
- **2026-11-28: execution start.**
  - Phase file `.flightops/agent-crews/leg-execution.md` loaded: Developer on Sonnet; Reviewer on Sonnet, because the diff touches a security-sensitive surface (OAuth credentials).
  - Status `ready` → `in-flight`.
  - Worktree `/home/cprch/projects/the-one-sortie-22` on `a02c80f6` (main with squawk 0444), `.venv` on Python 3.12.3. The main checkout belongs to another session and is not used.
- **Leg 1 risk tier: high.** It touches a security-sensitive surface (OAuth sign-in) and changes the sign-in pause lifecycle, so it gets a per-leg Developer design review before implementation.
- **Leg 1 design review.**
  - **Cycle 1: approve with changes.** Two high issues, both in the test plan:
    - The routine and connector tests must use a real `Agent`, not the scripted `_Agent` stub, which fakes the pause.
    - The DD2 reproduction must still drive the in-band wait after DD1.
  - Medium items applied: the pool DB wiring, both stale-token shapes, the warm-connection stub flip, test stand-ins.
  - **Cycle 2: approve with changes**, test-construction details only: the reproduction runs with no wrapper before DD1, the exact patch targets, binding a real csid, the `_spawn_routine_turn` and `_Factory` patterns. Applied as "Test Construction Notes".
  - Keeping the `agent_build_csid` substitution, as the review recommended. Leg status → `ready`.
- **Leg 1 landed** (see the Leg 1 entry): DD1 in place; DD2 dropped on evidence; Phase A moved onto its own task (an in-scope finding). The flight-end Reviewer should check for any other path where a refusing connect runs on a task that keeps working afterwards.
- **Leg 2 risk tier: high.** It changes the sign-in pause/resume lifecycle and the OAuth callback contract on a credential surface, so it gets a per-leg Developer design review.
- **Leg 2 design review, cycle 1: approve with changes.** Medium items, all applied:
  - A superseded flow that resolves now reports, resumes and cancels its siblings (only superseded failures stay silent).
  - Missed pin: `test_mcp_httpx_guard.py`.
  - `_oauth_driver_headers` stays in `api.py`.
  - A complete pins list, with rewrites.
  - Lows applied: provider None guard; `api.py`'s ceiling lowered; a storage-flag failure test; token delay on every grant; harness notes; storage flag first.
  - **No second cycle:** every change adopts the reviewer's own recommendation, with no new design beyond it, and the flight-end Reviewer covers the result. Leg status → `ready`.
- **Leg 2 landed.** Unit tier 12445 passed / 40 skipped / 0 failed; lanes `chats`, `chats-transcript` and `shared` green.
- **Leg 2 process slip, and the squawk it exposed.** The Developer changed the leg's status line with `sed -i`, which breaks the shell-write rule. The edit itself was a correct one-line change. The hook did not block it because it guards only paths under the session's project root, and this worktree is a sibling. Logged as **squawk 0445** (routine, deferred).
- **Flight-end review** spawned (Sonnet tier: credential surface), covering both legs' uncommitted changes. It includes a check for any other path where a refusing connect runs on a long-lived task.
- **Flight-end review: `[HANDOFF:confirmed]`**, no blocking issues.
  - DD1, DD3 and DD4 met; DD2's drop is consistent with its evidence. No other path awaits a refusing connect on a long-lived task: the only provider builders are the pool worker (ends), Phase A (its own task), and `/api/oauth/start` and Phase B (interactive).
  - Nothing granted, widened or logged.
  - Its pytest set passed (77), and lint is clean.
  - Non-blocking nits accepted: flight status and checklist flip at landing; some leg-2 tests not falsified (recorded); one long `noqa` line.
  - Legs 1 and 2 → `completed` and committed. Leg 3 (HAT) remains.

### Leg 1: nothing waits for a sign-in no one can give

- **Status** `ready` → `in-flight` (2026-11-28).
- **DD2 reproduction (run first, before any DD1 edit, no wrapper).** `tests/test_mcp_pool_teardown_cancel.py`, real pool, real `MCPClient`, `OAuthASStub(refresh_status=400)`, stored token expired, a real hex csid bound, connect timeout 20 s, teardown timeout lowered to 0.3 s. `_evict_all_for_source` called while the worker sat in the in-band sign-in wait (a `_state` entry registered).
  - **Sign-in-wait trigger.** The `acquire` caller got `MCPAuthRequired` (not cancelled). The agent turn paused: tool message with `metadata.is_auth_required`, `agent._deferred_tool_calls` set. No raw `CancelledError` reached the caller or the turn (`MCPClient._connect_once`'s cancel arm re-pauses on the recorded 401).
  - **Slow-server trigger** (an ASGI app that never answers; no sign-in wait, so it is the only trigger left after DD1). The turn got a tool error (`[error] MCP source 'pool-slow' unavailable: MCPConnectionError: MCP connect failed: cancelled during initialize ...`), not a cancel.
  - **Decision: DD2 DROPPED.** No raw cancel reaches the caller in any window the tests can drive; the client already translates it. No `_entry_worker` change lands for DD2, and the flight's DD2 checkpoint ("a worker cancelled mid-connect gives the turn a tool error, never a cancel") is marked dropped, since the slow-server test pins it as already true. The tests stay as pins of the observed behaviour.
- **DD1 landed.** `SignInNotAvailable(OAuthFlowError)` in `oauth/errors.py`; keyword-only `interactive: bool = True` on `make_oauth_handlers` and `build_oauth_provider_for_source`; `_entry_worker` and Phase A pass `interactive=False`; the `agent_build:` refusal raises the same class; `oauth/_log_filter.py` (filter on the SDK logger, installed once at `the_one.mcp.oauth` import) drops only the refusal's "OAuth flow error" record. Docs updated (agents.md Synthetic csid pattern and sortie 04 paragraph, handlers / provider_factory docstrings, `_entry_worker` comment).
- **Finding, fixed in scope: Phase A needed its own task.** With the refusal, `MCPClient.connect` takes its "bare CancelledError + recorded 401" arm and abandons the transport stack, leaving a cancelled anyio scope entered on the connecting task. In a pool worker that task just ends; in the Library Test route the next `await` (`_clear_stale_oauth_secrets`) raised `CancelledError`. `mcp_connection_flow._connect_with_tokens` now runs `_connect_with_tokens_inner` on its own task (same signature; tests that patch `_connect_with_tokens` unaffected).
- **Test files.** `tests/test_mcp_oauth_non_interactive.py` (handlers, pool, chat, routine via `_spawn_routine_turn`, connector via `dispatch_inbound`, warm connection, Phase A, per-agent Test, log filter), `tests/test_mcp_pool_teardown_cancel.py` (DD2 pins, with a forced-interactive wrapper), helper `tests/_mcp_pool_helpers.py`. Timing tests falsified by removing `interactive=False` from `_pool.py` (9 failures) and from Phase A (2 failures), then restored.
- **`agent_build_csid` choice.** The `agent_build_csid` substitution in `_entry_worker` is kept as is (smallest change; keeps "no csid plus a stored token still gets a provider"). With `interactive=False` the csid is only a label.

### Leg 2: resume after the token save

- **Status** `ready` → `in-flight` → `landed` (2026-11-28). Not committed.
- **Landed.** `the_one/interfaces/web/mcp_oauth_flow.py` (new, ~230 lines) owns the chat sign-in outcome: save detection, completion rule, `auth_resolved` / `auth_failed`, the claimed exactly-once resume, per-(session, source) superseded-flow tracking. `MCPSourceTokenStorage.tokens_saved` is set after `repo.update` returns; a wrapper on `provider.context.redirect_handler` resets it at each redirect. `api.py::oauth_start` delegates (it passes `_oauth_driver_headers` in; the squawk 0202 `Accept` header is unchanged). `oauth_callback` now only resolves the code and renders the popup: no `auth_resolved`, no resume, no IdP-error `auth_failed`. Popup detail line is "Return to the app to continue. This window will close automatically." `OAuthASStub(token_delay=...)` sleeps in `/token` for every grant.
- **Size.** `api.py` 5126 → 5040 lines; its `ALLOWANCE` ceiling lowered to 5040. `import httpx2` stays in `api.py` with a `noqa: F401` because `mcp_connection_flow` reaches it as `_api.httpx2` and tests patch `api.httpx2`.
- **Decisions.** The response success test is `200 <= status_code < 300` (the existing stand-in response objects carry only `status_code`). A no-provider guard reports `NO_PROVIDER_DESCRIPTION` through the same failure path (so superseded rules apply). A cancelled flow (superseded by a sibling's resolve) re-raises `CancelledError` and reports nothing.
- **Pins updated.** `test_oauth_callback_route.py` (two tests renamed and rewritten to assert no broadcast; success test also pins the new detail text), `test_app_websocket_pause_resume.py` (A12 test rewritten onto the flow, renamed; the callback client fixture removed), `test_mcp_httpx_guard.py` (scans `mcp_oauth_flow.py` and `mcp_connection_flow.py`), `test_python_module_size.py` (ceiling), docstring mentions in `test_oauth_start_endpoint.py`. `test_oauth_callback_gate.py`, `test_oauth_callback_page_static.py`, the browser tests and `tests/HAT.md` did not pin the old behaviour or text.
- **Known limitation pinned.** `test_known_limitation_a_method_only_401_resolves_then_repauses` (stub `auth_required_methods={"tools/call"}`): resolved, resumed once, re-paused with a new pause. Recorded in agents.md with the 403 step-up case. The re-pausing tool in that test is a repo-token-checking test tool, not a real MCP tool (same outcome by construction).
- **New tests** (`tests/test_mcp_oauth_chat_sign_in_completion.py`): e2e resume-after-save (`token_delay=1.0`), token-endpoint 400, IdP denial (with and without description), valid stored token, known limitation, final non-2xx, save-beats-failed-retry, provider guard, redirect wrapper, closed session, exactly-once with two flows, superseded failure silent, older-flow completion cancels the newer, storage flag on a failed write.
- **Falsification.** Re-adding the callback's `auth_resolved` plus resume by editing (then restored): `test_resume_waits_for_the_token_save_then_happens_once`, `test_token_endpoint_refusal_reports_one_failure_and_never_resumes` and `test_callback_success_resolves_the_code_and_broadcasts_nothing` fail. Disabling the `_resuming` claim: `test_two_flows_for_one_session_resume_once` fails. Disabling the superseded check: `test_a_superseded_flow_failing_later_sends_no_auth_failed` fails. Other new tests were not falsified.
- **Gates.** See the leg report (unit tier, lanes).
