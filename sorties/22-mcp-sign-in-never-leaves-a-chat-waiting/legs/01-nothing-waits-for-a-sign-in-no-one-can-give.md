# Leg: 01-nothing-waits-for-a-sign-in-no-one-can-give

**Status**: completed
**Flight**: [MCP sign-in never leaves a chat waiting](../flight.md)

## Objective
An MCP connection no one can sign in through refuses the interactive sign-in step at once. That covers every pool connection, and Test connection's saved-tokens phase (Phase A). So a chat tool call, a routine run and a connector turn pause immediately instead of after the 30 s connect timeout. A pool worker torn down mid-connect is translated into a connection error for its caller, but only if a reproduction shows a raw cancel reaches the turn.

## Context
- Flight DD1 (refuse for every pool connection and Phase A; dedicated refusal class; quiet its SDK log line), DD2 (conditional: reproduce first, translate in `_entry_worker`), DD5 (tests and timing rules). Charter criteria 3 and 4.
- Squawk 0444 (merged, `a02c80f6`): `build_oauth_provider_for_source` returns `TheOneOAuthClientProvider`, which seeds the stored token's expiry so the SDK refreshes before any interactive step. The refusal here applies only after the refresh fails.
- Squawk 0422 is the precedent: `redirect_handler` already refuses an `agent_build:` csid before registering any state; `MCPClient.connect` turns the `OAuthFlowError` into `MCPAuthRequired`.
- The chat UI already ignores the pool's in-band consent URL (`static/js/areas/chat/sign-in.js::onAuthRequired`, Sortie 04 DD2 amendment). The pause frame (`app.py::_auth_required_event_from_metadata`) renders the same **Sign in** group. No frontend change is in this leg.
- Out of scope here (leg 2): the resume after sign-in, `auth_resolved` / `auth_failed` ownership, the callback page wording. Between this leg and leg 2, an end-to-end chat sign-in still races the token save. Keep this leg's criterion-4 tests to "pause at once, `/api/oauth/start` still starts a flow".

## Inputs
- Branch `sortie/22-mcp-sign-in-never-leaves-a-chat-waiting` at `a02c80f6` (main with squawk 0444), worktree `/home/cprch/projects/the-one-sortie-22`, `.venv` on Python 3.12.3.
- `the_one/mcp/oauth/handlers.py::make_oauth_handlers` / `redirect_handler` with the `agent_build:` refusal; `provider_factory.py::build_oauth_provider_for_source` (no `interactive` keyword yet); `_pool.py::_entry_worker` builds the provider from `current_chat_session_id` or `agent_build_csid`.

## Outputs
- `build_oauth_provider_for_source(..., interactive: bool = True)`; with `False`, `redirect_handler` raises the dedicated refusal (an `OAuthFlowError` subclass) before registering state or broadcasting.
- `_entry_worker` and `mcp_connection_flow.py` Phase A pass `interactive=False`; Phase B (`mcp_connection_flow.py` ~:421) and `api.py::oauth_start` keep the default.
- The agent-build refusal raises the same class.
- A logging filter drops only that class's `"OAuth flow error"` record on the SDK logger.
- The DD2 reproduction test, and either the `_entry_worker` translation or a recorded drop of DD2.
- Tests listed under Acceptance Criteria; docs updated.

## Acceptance Criteria

**Order of work:**
1. The DD2 reproduction, with its outcome recorded in the flight log.
2. The refusal class, the `interactive` keyword and the callers (DD1).
3. The log filter.
4. The DD2 translation, only if reproduced.
5. The docs.

The criteria below are listed in that order.

- [ ] **DD2 reproduction, done first and before the DD1 change.** A test drives the real `MCPClient` against `OAuthASStub` through the real pool. The source row has `dcr_credentials`, a stored token and `refresh_status=400`; a chat csid is bound; the connect timeout is 20 s or more, or the teardown timeout is lowered in the test. It calls `_evict_all_for_source` while the worker is mid-connect and records what reaches the `acquire` caller (`MCPAuthRequired`, `MCPConnectionError`, or a raw `CancelledError`) and what the agent turn does (pauses, tool error, or cancelled). The outcome is recorded in the flight log before any DD1 edit.
  - **It must keep working after DD1**, which removes the in-band wait from real pool connections. The test forces an interactive pool provider explicitly: monkeypatch the factory as `_pool` calls it so it passes `interactive=True`. It therefore still drives the in-band wait as a regression pin of the cancel path. A second variant uses a slow-initialize server with no sign-in wait, via a small in-test ASGI wrapper around `serve_asgi` in `tests/_mcp_signin_helpers.py`. That variant is the only trigger left after DD1 and informs keep-or-drop.
  - If a raw `CancelledError` reaches the caller in any window the tests can drive, `_entry_worker` translates a `CancelledError` recorded while the entry was being torn down into `MCPConnectionError` with fixed text free of `TOKEN_FAILURE_MARKERS` phrases. The tests then assert the caller gets that error and the turn gets a tool error, never a cancel.
  - If not, DD2 is dropped: the flight log says so with the evidence, the flight's DD2 checkpoint is marked dropped there, and no `_entry_worker` change lands. The tests stay as pins of the observed behaviour.
- [ ] `build_oauth_provider_for_source` and `make_oauth_handlers` take keyword-only `interactive: bool = True` (after `*`; every existing caller passes keywords). With `interactive=False`, `redirect_handler` raises the dedicated refusal class (proposed `SignInNotAvailable(OAuthFlowError)` in `the_one/mcp/oauth/errors.py`) at once: no `_state.register`, no `auth_required` broadcast, no `consent_url_future` resolution. A direct `make_oauth_handlers(..., interactive=False, consent_url_future=fut)` test asserts the future stays unresolved; Phase A passes no future, so it cannot show this. The agent-build csid raises the same class. Existing callers that pass nothing behave as today.
- [ ] `_pool.py::_entry_worker` builds every pool provider with `interactive=False`. With `MCP_DEFAULT_TIMEOUT_SECONDS` pinned at 10 s or more, a pool connection refuses on both stale-token shapes (each in its own test case):
  - **expired:** past `token_expires_at` plus `refresh_status=400`, the squawk 0444 refresh-first path;
  - **valid-but-revoked:** future `token_expires_at`, the stub rejecting the token, then a 401 and the flow (as `_stale_secrets` in `test_mcp_test_connection_stale_tokens.py` sets up).

  For each shape:
  - `acquire` raises `MCPAuthRequired` in under 2 s, with no `_state` entry left registered and no `auth_required` frame sent to the chat session.
  - A chat tool call pauses (`metadata.is_auth_required`) in under 2 s.
  - A routine run ends with `classify(...)` giving the reason "Needs a sign-in to …" in under 5 s.
  - A connector turn ends paused in under 5 s, through `dispatch_inbound` with `AgentFactory` / `set_factory` / `StubPlugin` as in `tests/test_connectors_inbound.py`. "Ends paused" means the persisted history ends with a tool message whose `metadata.is_auth_required` is true, and `agent._deferred_tool_calls` is set. `dispatch_inbound` has no paused signal of its own.

  **Every one of these uses the real path**: a real `Agent` with `FakeLLM` (`tests/conftest.py`) scripting one assistant message with a `ToolCall` to a real MCP tool, whose `execute` reaches `_pool.acquire`, then `_entry_worker`, then the factory. Never the scripted `_Agent` stub of `tests/test_routines_runner.py` / `test_routine_turn_path.py`, whose `mode="pause"` fakes the pause and would pass without the fix. The routine test names its entry point (`_spawn_routine_turn` or `run_routine` with a factory-built agent) and reaches `turn_info["paused"]` through `app.py::_process_and_broadcast`.

  Each timing test is shown failing (about the pinned timeout) with `interactive=False` removed, then restored.
- [ ] A warm pooled connection: after a successful connect and one tool call, the stub is flipped mid-test (set `stub.refresh_status = 400`, expire the stored `token_expires_at`, and make the stub reject the old token). The next `call_tool` pauses the turn in under 2 s, well under the 30 s tool timeout that could otherwise mask it. Assert the outcome (pause and timing), not which branch fires (`client.py` ~:936 / ~:1075 or `_classify_failure`). If the stub cannot reject a previously accepted token, add the smallest mode that does, documented in its docstring.
- [ ] `mcp_connection_flow.py` Phase A (`_connect_with_tokens`, ~:70) passes `interactive=False`:
  - Library Test connection on a dead refresh token falls through to Phase B (which returns `auth_required` with a consent URL) with no 30 s wait.
  - The per-agent Test (`mcp_agent_test.py`) returns `{"status": "auth_required"}` fast and touches no tokens.
  - Existing tests in `tests/test_mcp_test_connection_stale_tokens.py` still pass, with their stale "parks in its callback handler" comments updated.
- [ ] `interactive=True` paths unchanged:
  - `test_mcp_agent_build_oauth_refusal.py::test_real_chat_csid_still_waits_for_the_consent_code` passes unchanged.
  - A Phase B Test connection still registers state and returns a consent URL.
  - `POST /api/oauth/start` for a paused chat still starts a flow and broadcasts `auth_required` with a `consent_url` (existing `tests/test_oauth_start_endpoint.py` passes).
- [ ] A logging filter on the `mcp.client.auth.oauth2` logger itself (not a handler) drops the SDK's `"OAuth flow error"` record (`oauth2.py` ~:788, inside `except Exception`) only when `record.exc_info[1]` is the refusal class. A `caplog` test (`caplog.set_level(logging.ERROR, "mcp.client.auth.oauth2")`) shows that a refusal logs no ERROR record. It also confirms the exception reaches that log call unwrapped (the redirect handler runs inside `_perform_authorization_code_grant`, ~:430). Another OAuth error, for example a token endpoint 500, still logs. The filter is installed once at import of `the_one/mcp/oauth/__init__.py`, with a guard against adding it twice.
- [ ] Docs:
  - `the_one/agents.md` "Synthetic csid pattern" is rewritten so the waiting rule keys on `interactive`, not csid shape: pool connections and Test Phase A refuse at once; `/api/oauth/start` and Test Phase B wait for consent.
  - The sortie 04 sign-in paragraph (agents.md around :30, which mentions the in-band flow) is corrected.
  - The `handlers.py` module docstring, the `provider_factory.py` docstring and the `_entry_worker` comment block are updated, and the refusal class is listed with the OAuth errors.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes, run alone, with the skip count read via `-rs`; `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/` are clean.
- [ ] No module grows past its `tests/test_python_module_size.py` ceiling; `client.py` (1171) and `app.py` (4171) are at their ceilings and should not need edits in this leg.

## Verification Steps
- Run the new and touched test files with `.venv/bin/python -m pytest <files> -x --timeout 90 -q`.
- Falsify each timing test by editing `interactive=False` out of `_entry_worker` (and Phase A), see it fail, then restore by editing. Report falsified yes/no per new test.
- Run the DD2 reproduction and paste its observed outcome into the flight log.
- Unit tier: `THE_ONE_TEST_NETNS=1 make test-unit` alone, in the background, waiting for its completion notification.
- No browser lane is required: no static file changes. If any frontend file is touched, run the static guards and the owning lane.

## Implementation Guidance

1. **Reproduce DD2 first** (before editing `_entry_worker` or the handlers).
   - Reuse the stub patterns in `tests/test_mcp_agent_build_oauth_refusal.py` and `tests/test_mcp_test_connection_stale_tokens.py` (`OAuthASStub`, `refresh_status`, the in-process server wiring).
   - Drive the pool with `current_chat_session_id` set to a real-looking hex csid so the in-band wait happens, start `acquire` in a task, wait until the worker is inside the sign-in wait (a `_state` entry is registered), then call `_evict_all_for_source`.
   - Lower `_pool._WORKER_TEARDOWN_TIMEOUT_SECONDS` via monkeypatch for speed if needed, keeping the connect timeout strictly above it.
   - Also try a slow-server variant (no sign-in wait; a server that delays its initialize response past the teardown timeout) to inform keep-or-drop after DD1.
2. **Refusal class and keyword.**
   - Add the class in `the_one/mcp/oauth/errors.py` (subclass `mcp.client.auth.exceptions.OAuthFlowError`, so `MCPClient`'s `except* (OAuthFlowError, OAuthTokenError)` arms still catch it).
   - Thread `interactive` from `build_oauth_provider_for_source` into `make_oauth_handlers`. In `redirect_handler`, refuse when `not interactive or is_agent_build_csid(chat_session_id)`, before anything else.
   - Keep the `agent_build_csid` substitution in `_entry_worker` as it is (design review recommendation: the smallest change, and it preserves "no csid plus a stored token still gets a provider"). With `interactive=False` the csid is only a label. Record this in the flight log.
   - Before changing signatures, grep the tests for stand-ins that patch `build_oauth_provider_for_source` or `make_oauth_handlers` with a fixed signature (for example `tests/test_oauth_test_connection_endpoint.py` ~:171-250, `tests/test_mcp_pool.py`, `tests/test_mcp_pool_resolve.py`). Update any stand-in so it accepts `interactive=`.
3. **Callers.** `_entry_worker` passes `interactive=False`; `mcp_connection_flow.py` Phase A passes `interactive=False`; Phase B and `api.py::oauth_start` keep the default. `api.py` is at its size ceiling (5126): do not grow it in this leg.
4. **Log filter.** A `logging.Filter` subclass on `logging.getLogger("mcp.client.auth.oauth2")`, installed once (guard against double-adding), checking `record.exc_info` for the refusal class. Exceptions inside an `ExceptionGroup` are not the case here: the SDK logs inside its own `try/except Exception` around the flow, so `exc_info[1]` is the raised exception itself. Confirm that against the SDK source.
5. **DD2 translation (only if reproduced).** In `_entry_worker`'s `except BaseException as exc:` arm, when `exc` is a `CancelledError` and the entry's `evict_event` is set (the worker is being torn down), record `MCPConnectionError("The MCP connection was closed while it was opening.")` (or similar fixed text without `TOKEN_FAILURE_MARKERS` phrases) as `entry.failure` instead. Keep the "worker always sets `client_ready`" contract. Do not swallow a genuine cancel of the worker for any other reason.
6. **Tests.** Prefer one new file (for example `tests/test_mcp_oauth_non_interactive.py`) for the refusal, pool, warm-connection, routine, connector and log-filter tests, plus the DD2 reproduction (its own file is fine). Use `tests/_api_app.py::shared_app()` and template databases where an app or DB is needed (`tests/test_api_app_guard.py`, `tests/test_schema_template.py`). No mock libraries.
   - **Pool DB wiring.** The factory's `MCPSourceTokenStorage(repo, source.id)` reads tokens from the DB row, not from `source_override`. So:
     - Create the source row (with `dcr_credentials`, `access_token`, `refresh_token`, `token_expires_at`) through `MCPSourceRepository` over `connect_template_db`, as `test_mcp_test_connection_stale_tokens.py` (~:55) does.
     - Patch `the_one.mcp._pool.get_connection` and `get_encryptor` (imported at module level, `_pool.py` ~:50-53) to that database.
     - Add an autouse fixture that runs `_pool._clear_for_test()` and clears `the_one.mcp.oauth._state._pending` around each test.
     - Put this in one shared helper in the new test file.

## Test Construction Notes (design review cycle 2)
- **The reproduction before the wrapper.** Step 1's reproduction runs with **no** wrapper: before DD1 the default pool behaviour is the in-band wait, and a wrapper passing `interactive=True` would raise `TypeError` before the keyword exists. Record the outcome, then add the forced-interactive wrapper in step 2, when the keyword lands.
- **Patch targets.**
  - Forced-interactive wrapper: `monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", wrapper)`, capturing the original first. `_entry_worker` imports it function-locally from the package (`_pool.py` ~:210), and `oauth/__init__.py` rebinds the name, so patching `provider_factory.build_oauth_provider_for_source` does nothing.
  - Check how `mcp_connection_flow.py` imports it before patching there.
  - Connect timeout: `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS`.
  - Pool DB: `the_one.mcp._pool.get_connection` and `get_encryptor`. Patch `make_source_resolver`'s own DB imports in `_tool_provider.py` to the same database, so a missing agent row gives the fallback source (`KeyError`) and not `MCPConnectionError(_RESOLVE_FAILED_MESSAGE)`.
- **The real tool.** `the_one.mcp._tool.MCPClientTool(MCPTool(name=..., description=..., input_schema={"type": "object", "properties": {}}, output_schema=None, annotations=None), source.id, source.name, "a", source)` (as `tests/test_self_configuration_agent_writes.py` ~:357-365), registered with `ToolRegistry().register(tool)`. Then `Agent(llm=FakeLLM([assistant message with ToolCall(name=tool.name, ...), final message]), tools=reg, system_prompt="sys")`. An agent name not in the store makes the resolver return the fallback source. The source id must match the DB row (token storage reads by id). `MCPAuthRequired` is not an `MCPConnectionError`, so `MCPClientTool.execute` does not swallow it.
- **Bind a real csid, or falsification fails.** Without one, `_entry_worker` substitutes `agent_build_csid`, which squawk 0422 already refuses, so the test would pass with the fix removed.
  - The chat-tool-call and pool-level `acquire` tests set `current_chat_session_id` to a hex csid around the call.
  - The routine path binds `session.id` itself (`app.py` ~:1400).
  - `dispatch_inbound` binds the connector session's id itself.
- **The routine test** uses `_spawn_routine_turn`, not `run_routine` (which needs a registered turn host and `create_web_session`):
  - Follow `tests/test_routine_turn_path.py`: build `Session(id=..., agent=<real Agent + FakeLLM>, created=...)`.
  - Monkeypatch `web_app._send_to_session`, `_save_session_to_db`, `_ensure_ollama_model_loaded` and `_resync_session_from_db`.
  - Await `_spawn_routine_turn(session, "go", {"routine": {"id": "r1", "name": "x"}})`, then assert `runner.classify("done", turn_info, timed_out=False, timeout_seconds=...)` gives "Needs a sign-in to …".
  - Reuse that file's cleanup pattern (`_inflight_tasks`, `_session_inflight`, `_clear_session_registry`).
- **The connector test** uses the `_Factory` stand-in from `tests/test_connectors_inbound.py` (~:1190), via `set_factory(_Factory())`, returning an `Agent` with `FakeLLM` and a `ToolRegistry` holding the `MCPClientTool`. A real `AgentFactory` would skip the stale source (no cached tools) and never register the tool.
  - Keep `StubPlugin` and `dispatch_inbound`.
  - The `conn` / `chat_repo` / `conn_repo` fixtures are local to that file: redefine them, or reuse `isolated_db`.
  - Use one database for both: point the pool patch at the same connection `dispatch_inbound` uses.
- **`_pool._clear_for_test` is async**, so the autouse cleanup fixture is an async fixture. It also clears `the_one.mcp.oauth._state._pending`.
- **Import cycle.** Define the refusal class in `the_one/mcp/oauth/errors.py`; run an import smoke check (`python -c "import the_one.mcp.oauth, the_one.mcp._pool, the_one.interfaces.web.app"`) after installing the filter.

## Edge Cases
- **A source with no `dcr_credentials`**: the factory returns `None` today (no provider). Unchanged: the 401 surfaces through the sign-in signal record as `MCPAuthRequired`.
- **A cached `no_auth` posture**: `_entry_worker` skips the provider. Unchanged.
- **A step-up 403 (`insufficient_scope`) on a tool call**: the SDK's step-up branch calls `_perform_authorization`, so the refusal fires there too, and the turn pauses. Leg 2 records the resulting sign-in loop as a known limitation. Here, just do not special-case it.
- **Two pool entries for the same source** (two agents): each refuses independently, and neither registers state.
- **A refresh that succeeds** (squawk 0444 path): no interactive step and no refusal. The existing 0444 tests must still pass.

## Files Affected
- `the_one/mcp/oauth/errors.py` - the refusal class
- `the_one/mcp/oauth/handlers.py` - `interactive` threading and the refusal; module docstring
- `the_one/mcp/oauth/provider_factory.py` - `interactive` keyword; docstring
- `the_one/mcp/oauth/__init__.py` - export or filter install, if that is where the package wires things
- `the_one/mcp/_pool.py` - `interactive=False`; comment block; the DD2 translation if reproduced
- `the_one/interfaces/web/mcp_connection_flow.py` - Phase A `interactive=False`
- `tests/test_mcp_oauth_non_interactive.py` (new), the DD2 reproduction test (new), `tests/test_mcp_test_connection_stale_tokens.py` (comments), any pinned test that changes
- `the_one/agents.md` - "Synthetic csid pattern", the sortie 04 sign-in paragraph, the OAuth errors list
- `sorties/22-mcp-sign-in-never-leaves-a-chat-waiting/flight-log.md` - leg entry, the DD2 outcome

## Citation Audit
Checked against the worktree at `a02c80f6`:
- `the_one/mcp/oauth/handlers.py::make_oauth_handlers` - `redirect_handler` refuses `is_agent_build_csid(chat_session_id)` with `OAuthFlowError` before `_state.register`; otherwise registers state, resolves `consent_url_future`, broadcasts `auth_required` to `_sessions.get(csid)` - verified
- `the_one/mcp/oauth/provider_factory.py::build_oauth_provider_for_source` - keyword-only `consent_url_future`, `allow_dcr_bootstrap`; `chat_session_id is None → None`; no `dcr_credentials` → `None`; returns `TheOneOAuthClientProvider` (0444) - verified
- `the_one/mcp/oauth/errors.py` - `MCPOAuthError(MCPClientError)` family; no `OAuthFlowError` subclass yet - verified
- `the_one/mcp/_pool.py::_entry_worker` - csid from `current_chat_session_id`, `agent_build_csid` when none and an access token is stored; `except BaseException as exc: entry.failure = exc; client_ready.set()` - verified
- `the_one/mcp/_pool.py::_teardown_entry` / `_WORKER_TEARDOWN_TIMEOUT_SECONDS = 10.0` - waits then cancels - verified
- `the_one/mcp/client.py::_connect_once` - `except* (OAuthFlowError, OAuthTokenError)` → `_oauth_flow_auth_required()`; `except asyncio.CancelledError` → `MCPAuthRequired` when a 401 is on record (~:658) - verified
- `the_one/interfaces/web/mcp_connection_flow.py` ~:70 - Phase A `build_oauth_provider_for_source(..., f"test:{source_id}", consent_url_future=None)`; ~:421 Phase B - verified
- `the_one/routines/runner.py:162` - "Needs a sign-in to {turn_info['paused']}." - verified
- SDK `mcp/client/auth/oauth2.py::_auth_flow` - `logger.exception("OAuth flow error")` inside `except Exception` around the 401 branch - verified (cycle 2 Architect)
- `tests/test_python_module_size.py` - `api.py` 5126, `client.py` 1171, `app.py` 4171 at their ceilings - verified (Architect)
- Design review (cycle 1) re-checked: every `make_oauth_handlers` caller passes keywords (`provider_factory.py`, `tests/_mcp_signin_helpers.py` ~:84, `tests/test_mcp_agent_build_oauth_refusal.py` ~:38). The SDK logger is `logging.getLogger(__name__)` = `mcp.client.auth.oauth2`, and its only `"OAuth flow error"` is at ~:788. `tests/test_routines_runner.py` / `test_routine_turn_path.py` drive a scripted `_Agent` stub whose `mode="pause"` never touches the pool. `tests/test_connectors_inbound.py` drives `dispatch_inbound` with `AgentFactory`, `FakeLLM` and `StubPlugin`. `_pool.py` imports `get_connection` / `get_encryptor` at module level - verified

---

## Post-Completion
*(filled in by the Developer at landing)*
