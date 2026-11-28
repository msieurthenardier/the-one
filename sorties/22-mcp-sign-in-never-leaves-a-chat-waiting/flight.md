# Sortie: MCP sign-in never leaves a chat waiting

**Status**: in-flight

## Charter

### Outcome
When an MCP source needs a sign-in, no chat sits waiting on it: after you sign in from a chat, the paused turn continues once with the new sign-in, and a chat nobody can sign in from stops waiting at once.

### Why Now
Production Cloudflare MCP, 2026-11-27: after a successful in-chat sign-in the chat hung and then asked to sign in again, and each failed routine run spent about 30 s waiting before "Needs a sign-in to Cloudflare MCP". Squawk 0444 (PR #404: stored tokens are now refreshed) makes a sign-in rare, but not gone: an expired or revoked refresh token still needs one.

### Success Criteria
- [ ] Signing in from a chat's sign-in prompt resumes the paused turn exactly once, its tool call uses the new tokens, and no second sign-in prompt appears.
- [ ] If the code exchange fails after the callback, the chat shows the sign-in failed instead of resuming or asking again.
- [ ] A routine run whose MCP source needs an interactive sign-in ends with "Needs a sign-in", and a connector chat's turn ends paused, in under 5 s, not after the 30 s connect timeout.
- [ ] A chat you have open still shows the sign-in prompt and can sign in as today.

*(Criterion 3 reworded by the operator after Architect review cycle 1: only routine runs produce "Needs a sign-in"; a paused connector turn sends the peer nothing, and adding a peer message would be a new surface.)*

### Constraints
- Nothing granted changes: consent, tokens and token storage stay as they are; refusals only stop waits that cannot succeed.
- Lands after squawk 0444 (PR #404), which also edits `the_one/mcp/oauth/provider_factory.py`.
- Never against the operator's production instance (ports 8484/8485, the real data directories); tests and the HAT use a dev instance on port 8490 or higher with a scratch data directory under `$HOME`.

---

## Pre-Flight

### Objective
An MCP connection that no one can sign in through never runs an interactive sign-in of its own. That covers pool connections opened for an agent's tools, and the saved-tokens phase of Test connection. It reports the need at once: an open chat shows **Sign in** immediately, a routine run ends "Needs a sign-in", a connector turn ends paused, and Test connection goes straight to its sign-in.

The chat's **Sign in** flow (`/api/oauth/start`) is the one place a chat sign-in runs. It resumes the paused turn only once it has saved the new tokens, and it alone reports a failure.

**No new or reshaped user-facing surface.** The chat's existing **Sign in** group, "Resuming…" and "OAuth failed: …" messages and the Library sign-in are reused unchanged; only when they appear changes. The one wording change is the popup's detail line (DD4), which drops a claim that is no longer true; its heading, the recorded contract, is unchanged. No mockup is needed (squawk 0293). Any other wording or layout change during the HAT goes through the fix-vs-feature gate.

### Open Questions
- [x] Which chats count as unable to sign in? → by kind (operator), then widened: every pool connection refuses the interactive step, because the chat ignores the pool's in-band consent URL anyway (DD1; operator chose "all pool connections").
- [x] Connector chats and "Needs a sign-in"? → criterion 3 reworded: a connector turn ends paused; no peer message (operator, Architect cycle 1).
- [x] Test connection's saved-tokens phase (Phase A) also waits 30 s on a dead refresh token → in scope, same rule (DD1; operator).
- [x] How does `_drive_flow` know the tokens were saved? → a flag on its `MCPSourceTokenStorage` instance, set in `set_tokens` (DD3; Architect).
- [x] Who reports an IdP denial? → `_drive_flow` alone (DD3; Architect).
- [x] The popup claims "Tokens have been securely persisted" before the exchange → neutral detail line (DD4; operator).
- [x] HAT: how to force "registration kept, refresh rejected"? → the operator revokes the app's grant at Cloudflare; "Reset connection" cannot be used because it also strips `dcr_credentials` (DD5; operator, Architect cycle 1).
- [x] HAT leg? → yes, against the real Cloudflare MCP on a dev instance, operator present (operator).
- [ ] Does a raw cancel ever reach the chat turn? → leg 1 reproduces through the real `MCPClient` first; DD2 lands only if it does.

### Design Decisions

**DD1. A connection no one can sign in through never runs an interactive sign-in.** `build_oauth_provider_for_source` gains a keyword `interactive: bool = True`. With `interactive=False`, `redirect_handler` raises `OAuthFlowError` at once, before registering any state or broadcasting, as squawk 0422 already does for an `agent_build:` csid. `MCPClient.connect` and `call_tool` translate that to `MCPAuthRequired` (`except* (OAuthFlowError, OAuthTokenError)`, client.py ~:629 and ~:1075), so the agent loop pauses the turn with no wait. The SDK tries the stored refresh token first (squawk 0444); only the interactive step is refused.

`interactive=False` callers:
- **`the_one/mcp/_pool.py::_entry_worker`** (every pool connection: chat, routine, connector, agent build).
- **`mcp_connection_flow.py:70`**, Phase A (`_connect_with_tokens`), shared by Library Test connection and the per-agent Test (`mcp_agent_test.py:186`). It never starts a flow (`consent_url_future=None`), and its `test:` csid has no session, so no one can receive its consent URL. Library Test's `MCPAuthRequired` arm already clears every OAuth-managed key (`_clear_stale_oauth_secrets`, `dcr_credentials` included) and falls through to Phase B; the per-agent Test returns `{"status": "auth_required"}` and touches no tokens. Both now skip the 30 s wait (operator: in scope). One behaviour change: on a step-up 403 the per-agent Test says `auth_required` where it said `error`. No test pins the 30 s wait (the stale-token tests set a 1.5 s timeout only to keep it short); comments in `tests/test_mcp_test_connection_stale_tokens.py` that describe it parking in the callback handler go stale and are updated.

`interactive=True` callers:
- **`mcp_connection_flow.py:421`**, Phase B (the Test-connection sign-in, with `consent_url_future`).
- **`api.py::oauth_start`**.

Why every pool connection, not only unattended ones:
- The chat already ignores an in-band consent URL (`static/js/areas/chat/sign-in.js::onAuthRequired`, Sortie 04 DD2 amendment). It is the only consumer of the in-band frame; GleepGlorp, the CLI, connectors and the MCP editor never use it.
- The pause frame (`app.py::_auth_required_event_from_metadata`) renders the same **Sign in** group, now at once.
- It also stops leaking `_state` entries and abandoned waiting tasks (up to 10 min each).
- It fixes a quiet misroute: a warm worker's handlers are bound to the csid of the chat that spawned it, so today's mid-session in-band frame can go to the wrong chat.

The agent-build refusal becomes a case of the same rule. The refusal raises a dedicated `OAuthFlowError` subclass (proposed `SignInNotAvailable`, in `the_one/mcp/oauth/errors.py`), raised for agent builds too. `MCPClient`'s existing `except* (OAuthFlowError, …)` still catches it. Whether the factory may then skip the csid requirement when `interactive=False` (dropping the `agent_build_csid` substitution) is a leg-1 call. `test_mcp_agent_build_oauth_refusal.py::test_real_chat_csid_still_waits_for_the_consent_code` builds handlers directly and stays valid for `interactive=True`. The agents.md "Synthetic csid pattern" rewrite keys the waiting rule on `interactive`, not on csid shape: a `test:` csid still waits in Phase B and no longer does in Phase A.

**Log noise.** Each refusal passes through the SDK's `logger.exception("OAuth flow error")` (an ERROR traceback per chat pause). Leg 1 adds a logging filter on the `mcp.client.auth.oauth2` logger that drops only records whose exception is the dedicated refusal class; other OAuth errors stay logged.

Unattended sessions need no session-kind check:
- A routine run's pause is classified "Needs a sign-in to …" (`the_one/routines/runner.py:162`).
- A connector turn ends paused (`connectors/inbound.py` runs `agent.step`; `_auto_deliver_reply` delivers only final assistant text).

**DD2. Conditional: a torn-down pool worker never cancels its caller.** The traced path: `/api/oauth/start` awaits `_evict_all_for_source`, and `_teardown_entry` waits 10 s (`_WORKER_TEARDOWN_TIMEOUT_SECONDS`), then cancels a worker that is mid-connect.

What a cancel does depends on where it lands:
- **Mostly, it does not cancel the turn.** `client.py::_connect_once`'s `except asyncio.CancelledError` arm (~:658) turns it into `MCPAuthRequired` when the initialize 401 is on record. The turn re-pauses about 10 s after the click. Without a 401 on record it becomes `MCPConnectionError("…cancelled during initialize…")`. That re-pause, followed by the callback's resume racing the token exchange (DD3), explains "hung, then asked to sign in again" on its own.
- **A raw `CancelledError` gets through only in narrow windows:** `resolve_source`, `get_connection`, or a cancel during `_cleanup_after_failed_connect`. There it lands in `entry.failure`; `acquire` re-raises it, `Agent._execute_tool` catches `Exception` only, and the turn ends cancelled with no pause.
- **Production evidence.** The 18:02:24 "Task exception was never retrieved … Attempted to exit cancel scope in a different task" is the abandoned transport stack of the cancelled connect.

What leg 1 does:
- Reproduce through the real `MCPClient` and `OAuthASStub` (never a fake worker that raises), **before DD1 lands** (DD1 removes the sign-in wait that triggers it). The connect timeout must strictly exceed `_WORKER_TEARDOWN_TIMEOUT_SECONDS`: pin it at 20 s or more, or lower the teardown timeout in the test. After DD1 the only remaining trigger is a slow server; whether that still reaches the turn decides keep or drop.
- If a raw cancel reaches the turn, translate it in `_entry_worker`, the sole writer of `entry.failure`: a `CancelledError` recorded there while the worker was being torn down becomes `MCPConnectionError` with fixed text free of the `TOKEN_FAILURE_MARKERS` phrases. `_tool.py` and `_tool_provider.py` already catch `MCPConnectionError`.
- If it cannot reproduce one, DD2 and its checkpoint are dropped (Adaptation Criteria). DD1 removes the common trigger either way, since no pool worker sits in a sign-in wait any more.

**DD3. The chat resumes from the flow that saved the tokens.** The completion logic moves out of `api.py`: `api.py` is exactly at its `ALLOWANCE` ceiling (5126, `tests/test_python_module_size.py`). It goes to a helper module, `the_one/interfaces/web/mcp_oauth_flow.py` (the `mcp_connection_flow.py` pattern). `oauth_start` calls it, and removing the callback's resume block keeps `api.py` net-neutral or smaller.

- **Detecting the save.** The flow's `MCPSourceTokenStorage` instance records that `set_tokens` completed: the flag is set after `repo.update` returns, so a failed write does not count. It is read through `provider.context.storage` (precedent: `mcp_connection_flow.py::_is_credentials_rejection` reads `provider.context`). That covers the code exchange and a refresh (`_handle_refresh_response` also calls `set_tokens`). The flag is reset when this flow's `redirect_handler` runs, so only a save made after the last redirect counts: a refresh that saved, then a 401 on the retry, then an abandoned interactive step is not resolved.
- **Completion rule.** The SDK saves before it retries the original request (`_handle_token_response` → `set_tokens`, then the retry `yield request`), so `client.post` returns only after the save and the retry.
  - **Resolved** if the save flag is set (even if the retried request then raised or failed), or if the final response is 2xx with no save (for example a valid stored token after a Library sign-in in the meantime).
  - **Failed** otherwise: an exception before any save, or any non-2xx final response with no save (401/403, and also 400/404/5xx, such as a modern-only server rejecting `initialize`, which `_drive_flow` does not negotiate). A no-exception failure needs its own `auth_failed` description, new text in "OAuth failed: …", pinned by a test.
  - **Known limitation, recorded.** When the pool's refusal came from something `initialize` cannot reproduce (a 403 `insufficient_scope` step-up on a tool call, or a 401 on one method only, the stub's `auth_required_methods` mode), `_drive_flow` sees 2xx with no save and resolves; the resumed call refuses again and the chat shows **Sign in** again. Before DD1 these ended as a 30 s tool error. A test with `auth_required_methods` pins today's outcome; handling them (driving the flow with the refused method) would be a follow-up.
- **On resolved:** look the session up with `_sessions.get(...)` at completion time, broadcast `auth_resolved`, and schedule `_resume_paused_session` through `_inflight_resume_tasks`.
- **Exactly once, claimed in the scheduler.** `mcp_oauth_flow.py` is the only scheduler of the resume after DD3. With no await in between, it checks `session.agent._deferred_tool_calls is not None` and that the session id is not in a module-level claimed set, adds the id, and calls `create_task`; the task's done-callback releases the id. Two flows finishing together (two tabs) then cannot both resume and send a duplicate `done`. This needs no change to `Agent.resume_after_auth` (which reads `_deferred_tool_calls` itself and no-ops on None, `core.py:556`) and no growth in `app.py`, which is also at its `ALLOWANCE` ceiling (4171). It imports from `app` at call time only, as `mcp_connection_flow.py` does (`app.py` imports `api` at load).
- **On failed:** broadcast `auth_failed` with no resume. The chat shows "OAuth failed: …" and **Sign in** again (`sign-in.js::onAuthFailed`).
- **One owner for failure.** `_drive_flow` is the only sender of `auth_failed`. The callback's IdP-error branch keeps `_state.fail` and its popup page but drops its broadcast. `str(OAuthFlowError(error_description or error))` keeps the visible text the same. Today an IdP denial broadcasts `auth_failed` twice.
- **Superseded flows.** A flow abandoned by a newer click for the same session and source sends nothing when it later fails (at the 10-min TTL). Its late `auth_failed` would otherwise close the newer flow's popup and clear its `loginFlows` via `settleClose`. Tracked with a dict keyed by (session, source) in `mcp_oauth_flow.py`.
- **`auth_failed.error` on an IdP denial** becomes `start_failed` (was the IdP's code). Harmless: `sign-in.js` shows `description` first, and the description stays non-empty.
- **The callback.** `oauth_callback` keeps resolving the code and rendering the popup page (heading "Login successful. You may close this tab." is a verbatim contract), but no longer broadcasts `auth_resolved` or resumes. After DD1 the only chat-bound flows are `/api/oauth/start`'s; `test:` flows have no session.
- **Eviction.** `/api/oauth/start` still evicts the source's pool entries first, so the resumed tool call opens a fresh connection that reads the saved tokens.
- **Out of scope, recorded.** `_drive_flow` is one of the hand-built OAuth drivers that drift from the real MCP client (Mission 29 Flight 2 debrief). This sortie changes when it reports, not its request shape.

**DD4. The popup stops claiming the save.** The callback page's success detail line ("Tokens have been securely persisted. This window will close automatically.") becomes neutral, for example "Return to the app to continue. This window will close automatically." The heading and the `mcp-oauth-result` postMessage are unchanged (operator). Update any test pinning the detail text.

**DD5. Tests and apparatus.**
- **Fixtures.** Unit tests run against the real `OAuthASStub` with `tests/_api_app.py::shared_app()` and template databases, with no mock libraries (Mission 29 Flight 1 debrief). The precondition for "needs an interactive sign-in" is `dcr_credentials` plus an expired token plus `OAuthASStub(refresh_status=400)`.
- **Timing.** Pin `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS` at 10 s or more so "under 2 s / under 5 s" proves there was no wait, and show each timing test failing before the fix.
- **Leg 1 tests:**
  - The DD2 reproduction.
  - A chat tool call pauses at once.
  - A routine run ends "Needs a sign-in" in under 5 s.
  - A connector turn ends paused in under 5 s.
  - A warm pooled connection whose mid-session `call_tool` gets a 401 after a failed refresh pauses at once. Assert the outcome (pause and timing), not the branch: the refused flow runs in a request task inside the transport's task group and may reach `call_tool` as a closed stream classified by `_classify_failure` and the 401 record rather than via the `except*` at ~:1075.
  - Test connection Phase A falls through to Phase B with no wait.
  - The `interactive=True` paths still register state and wait.
  - `/api/oauth/start` still starts a flow. Leg 1 keeps criterion-4 tests to "pause at once plus start works"; the full resume is leg 2, since between the legs an end-to-end sign-in still hits the race.
- **Leg 2 tests.** `OAuthASStub` gains a token-endpoint delay mode (for example `token_delay`; its handler runs on a thread, so `time.sleep` is safe), documented in its docstring and in the agents.md stub-modes list. The tests show:
  - no resume before `set_tokens`, and exactly one resume, also with two flows finishing together;
  - no second `auth_required`;
  - `auth_failed` with no resume when the exchange fails, and when the final response is non-2xx with no save (with its pinned description);
  - one `auth_failed` on an IdP denial;
  - resolved when a valid stored token makes the start flow a no-op;
  - the `auth_required_methods` limitation's outcome.
- **Pins to update.** Grep `tests/` and `tests/browser/` for `auth_resolved`, `auth_failed`, `_resume_paused_session`, `oauth_callback`, `oauth/callback`, the popup detail text and the agent-build refusal tests. No test pins the popup detail text today; `tests/browser/test_flow_oauth_callback_cross_site.py` asserts only "Login successful" and stays valid. The stub-modes list is agents.md "OAuth callback result and the RFC 9207 issuer" (~:883); it already omits `refresh_status`, so add both that and `token_delay`. Known files: `tests/test_oauth_callback_route.py`, `tests/test_app_websocket_pause_resume.py`, `tests/test_oauth_start_endpoint.py`, `tests/test_mcp_agent_build_oauth_refusal.py`, `tests/browser/test_oauth_modal_flow.py`, `tests/browser/test_flow_chat_turn_work.py`, `tests/browser/test_flow_chat_session_state.py`. Run every lane whose files match (squawk 0334), with lanes found via `scripts/run-tests.sh --list`. Browser tests synthesize frames, so an unchanged frame shape keeps them valid.
- **HAT apparatus.**
  - A dev instance on port 8490 or higher, with a scratch data directory under `$HOME`, started from a scratch cwd (CLAUDE.md "Behavior-test credential convention").
  - The real Cloudflare MCP added there; the operator signs in through Library (ATC may not handle secrets).
  - **Act:** the operator revokes the app's grant at Cloudflare, which keeps `dcr_credentials` and makes the refresh fail. "Reset connection" must not be used: it also strips `dcr_credentials` (`mcp_connection_api.py::reset_mcp_connection`), after which `/api/oauth/start` answers 400 and no interactive step is ever reached.
  - **Order matters.** A chat sign-in repairs the revoked state, and Library Test's fall-through strips every OAuth key like Reset does. So with one revoke, in this order:
    1. Run the routine: it ends "Needs a sign-in" with no 30 s gap.
    2. Run Library Test connection, and do not finish its sign-in: it goes straight to the sign-in. This also clears the registration, so the operator signs in through Library and revokes again before step 3.
    3. Use a Cloudflare tool in chat: **Sign in** appears at once; after sign-in there is one tool result, no second prompt, and the popup's neutral wording.
    Throughout, the instance log shows no "OAuth flow error" traceback per pause.
  - **Criterion 3's measure** is the gap from the routine's tool-call dispatch to the run's end in the log timestamps (no 30 s gap), not the whole run, which includes LLM latency. The routine's agent needs the source's cached tools (`_cache.tools`), from a successful sign-in before the revoke, or the build skips the source and the run never pauses. The connector half of criterion 3 is by test (no connector in the HAT).
  - **HAT-start questions for the operator** (they do not block legs 1 and 2):
    - Revoking at Cloudflare may also hit the production grant: both registrations are DCR clients named `the-one` (`provider_factory.py`). Can the dev client be identified before revoking, or does the operator accept a fresh production sign-in afterwards?
    - Does revoking the grant also delete the DCR client? If so, `/authorize` with the stored `client_id` fails at the IdP, and the HAT exercises criterion 2's failure path instead of criterion 1.
    - Which LLM provider does the dev instance use: a real one (its key is a secret the operator sets), or the dev-mode `mock` provider with a scripted `tool_calls` reply (no secret, no latency)?
  - If Cloudflare offers no revocation control, the HAT stops at that step and the operator chooses between a dev-only seam that clears only the token keys (a follow-up) and unit-test evidence for criteria 1 to 3.

### Citation Audit

Verified against `78b4b079` (main after v1.1.0); rows marked A re-checked by the Architect, cycle 1.

| Citation | Status |
|---|---|
| `api.py::oauth_start` awaits `_evict_all_for_source(source_id)` before scheduling `_drive_flow`; `_drive_flow` broadcasts `auth_failed` (`start_failed`) on exception | verified (A) |
| `api.py::oauth_callback` resolves via `_state.resolve`, then broadcasts `auth_resolved` and schedules `_resume_paused_session` when `_deferred_tool_calls is not None`; IdP-error branch calls `_state.fail` and broadcasts `auth_failed`; success page says "Tokens have been securely persisted" | verified (A) |
| `api.py` is at its `ALLOWANCE` ceiling (5126) in `tests/test_python_module_size.py`; `client.py` at 1171; `app.py` at 4171 | verified (A, cycle 2 for `app.py`) |
| `core.py:556`: `resume_after_auth` reads `_deferred_tool_calls` itself and no-ops on None | verified (A, cycle 2) |
| `_pool.py::_entry_worker` catches `BaseException` into `entry.failure`; `acquire` re-raises it; `_teardown_entry` waits 10 s then cancels | verified (A) |
| `client.py::_connect_once` `except asyncio.CancelledError` arm (~:658) turns a cancel into `MCPAuthRequired` (401 on record) or `MCPConnectionError` | verified (A) |
| `_pool.py::_entry_worker` builds the provider with the chat csid from `current_chat_session_id`, or `agent_build_csid` when none and an access token is stored | verified (A) |
| `oauth/handlers.py::redirect_handler` refuses an `agent_build:` csid at once; otherwise registers state, broadcasts `auth_required` with `consent_url`; `callback_handler` awaits the code | verified (A) |
| `MCPClient.connect` and `call_tool` translate `OAuthFlowError` / `OAuthTokenError` to `MCPAuthRequired` (`except*`, ~:629, ~:1075) | verified (A) |
| SDK `oauth2.py::_auth_flow`: `_handle_token_response` → `set_tokens` before the retry `yield request`; `_handle_refresh_response` also calls `set_tokens` | verified (A) |
| `agent/core.py::_execute_tool` catches `MCPAuthRequired` into the pause result and `Exception`-level errors, not `BaseException` | verified (A) |
| `sign-in.js::onAuthRequired` ignores an in-band consent URL; `onAuthResolved` shows "Resuming…"; `onAuthFailed` shows "OAuth failed: …" and **Sign in** again | verified (A) |
| `routines/runner.py:162` classifies a paused run as "Needs a sign-in to {source}."; `connectors/inbound.py` delivers only final assistant text | verified (A) |
| `connectors/inbound.py:449` binds `current_chat_session_id` to the connector chat | verified (A) |
| `mcp_connection_flow.py:70` is Phase A (`_connect_with_tokens`, no `consent_url_future`, `test:` csid; also used by `mcp_agent_test.py`); `:421` is Phase B (the Test-connection sign-in) | verified (A) |
| `mcp_connection_api.py::reset_mcp_connection` strips every `OAUTH_MANAGED_SECRET_KEYS` key, `dcr_credentials` included, and drops `config._cache` | verified (A) |
| `the_one/agents.md` "Synthetic csid pattern" (:1349) says real chat csids still wait for consent | verified (to be rewritten) |

### Prerequisites
- [x] Squawk 0444 (PR #404) merged (`a02c80f6`), and this branch fast-forwarded onto it (2026-11-28)
- [ ] A dev instance for the HAT: port 8490 or higher, scratch data dir under `$HOME`, scratch cwd; re-verify at HAT start
- [ ] The operator available to sign in to Cloudflare, and Cloudflare offering a way to revoke the app's grant; checked at HAT start
- [x] Branch `sortie/22-mcp-sign-in-never-leaves-a-chat-waiting` from `main` (worktree `/home/cprch/projects/the-one-sortie-22`; the main checkout is left to other sessions)

### Pre-Flight Checklist
- [x] All open questions resolved (DD2's premise is resolved by leg 1's reproduction, by design)
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified (0444 merge; the HAT checks at HAT start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Nothing waits for a sign-in no one can give (leg 1).**
   - Reproduce the DD2 cancel through the real client.
   - Add the `interactive` keyword and the refusal for the pool and Test connection Phase A (DD1), with the refusal's log quieted.
   - Translate a torn-down worker's cancel in `_entry_worker` if leg 1 reproduced one (DD2).
   - Add the leg-1 tests (DD5).
   - Update the docs: agents.md "Synthetic csid pattern", the sortie 04 sign-in paragraph (agents.md :30, which mentions the in-band flow), the `handlers.py` and `provider_factory.py` docstrings and the `_entry_worker` comment block.
2. **The chat resumes after the save (leg 2).**
   - `mcp_oauth_flow.py` owns completion: the save flag, the completion rule, `auth_resolved` and the claimed resume, and the sole `auth_failed`.
   - The callback renders only, with the neutral detail line (DD3, DD4).
   - Add the stub's delay mode and the leg-2 tests, update the pins and run the matching lanes.
   - Update the docs: the `oauth_start` / `oauth_callback` docstrings, agents.md "Auth-pause state is set before the yield" and the stub-modes list.
3. **HAT (leg 3).** A guided session on the dev instance with the real Cloudflare MCP, through the fix-vs-feature gate.

### Checkpoints
- [ ] A chat tool call on a source needing sign-in pauses at once and shows **Sign in**; a routine run ends "Needs a sign-in" and a connector turn ends paused, each in under 5 s; Test connection skips the 30 s wait
- [x] (DD2, DROPPED: not reproduced; leg 1 pins that a torn-down worker already gives the turn a pause or a tool error, never a cancel)
- [ ] Signing in resumes the turn exactly once, after the tokens are saved; a failed exchange shows the failure once and does not resume
- [ ] The HAT walks charter criteria 1, 4 and the routine half of 3 against Cloudflare; criterion 2 and the connector half of 3 by test

### Adaptation Criteria
- If leg 1 cannot reproduce a raw cancel reaching the turn, record what it found, keep DD1, and drop DD2 and its checkpoint rather than fix an unproven path.
- If DD3 needs a change to the `auth_resolved` / `auth_failed` frame shape, record it as a contract change and update every pin in the same leg.
- A second, independent design cluster surfacing (for example, reworking the hand-built OAuth drivers) is not folded in: it becomes its own sortie.

### Legs
- [ ] `01-nothing-waits-for-a-sign-in-no-one-can-give` — DD1, DD2 (charter criteria 3, 4)
- [ ] `02-resume-after-the-token-save` — DD3, DD4 (charter criteria 1, 2, 4)
- [ ] `03-hat` — operator HAT against Cloudflare on a dev instance (criteria 1, 4 and the routine half of 3 live; 2 and the connector half of 3 by test)

---

## Post-Flight

### Completion Checklist
- [ ] All legs landed
- [ ] Charter success criteria checked off with evidence
- [ ] Docs updated (agents.md "Synthetic csid pattern", the sortie 04 sign-in paragraph, "Auth-pause state is set before the yield", the stub-modes list; the module docstrings named in the Technical Approach)
- [ ] Unit tier and every matching browser lane green
- [ ] Debrief written

### Verification
Unit tests against `OAuthASStub` (legs 1 and 2), the matching browser lanes, and the operator HAT against the real Cloudflare MCP on a dev instance (leg 3).
