# Squawk 0422: An agent build waits the full 30 s MCP timeout on a stale-token OAuth source

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

Some agents use an OAuth MCP source that has a stored access token whose refresh fails, and that has no cached tool list. Every build of such an agent waits 30 s before it skips the source. That includes a chat join, a session switch and a routine run. On a 401, the SDK runs the authorization flow: `redirect_handler` registers a state, and `callback_handler` waits for a code that never arrives. Only the connect timeout ends the wait. On the agent-build path there is no chat to sign in through, so the wait cannot succeed. The 30 s also hold up the chat's `join` reply, which feeds squawk 0423 (operator report: the pane was stuck on a GleepGlorp chat for about a minute). Workaround: sign in to the source again, or detach it from the agent.

Reproduce: attach an OAuth MCP source whose tokens are expired or revoked, with an empty `_cache.tools`, to an agent. Open one of that agent's chats. `session_joined` arrives about 30 s later.

## Evidence
- `the_one/mcp/_pool.py:_entry_worker`: when no chat session id is set and `source.secrets["access_token"]` exists, it builds the OAuth provider with the synthetic id `agent_build:{source.id}`. The comment there says: "callback_handler awaits a code that never arrives; the outer `MCPClient.connect` timeout fires".
- `the_one/mcp/oauth/handlers.py:callback_handler`: `return await entry.code_future`, with no bound and no check of the synthetic id.
- `the_one/mcp/client.py:_connect_once`: the `except asyncio.TimeoutError` branch turns the 401 into `MCPAuthRequired` only after `MCP_DEFAULT_TIMEOUT_SECONDS` (30).
- Installed Windows app log, 2026-11-25, agent 'MyMusic Builder', source 'Cloudflare MCP' (`f26ad9d319e8`). "requires authorization; skipping" is logged every ~30 s: 09:07:46, 09:08:17, 09:08:48, 09:09:18, 09:09:49, 09:10:19. A manual routine run logged "started" at 09:05:46, 30 s after its build began.

## Corrective Action
*(written at completion)*

Likely direction: for an `agent_build:` chat session id, raise `OAuthFlowError` at once in `redirect_handler` (or `callback_handler`). The existing `except* (OAuthFlowError, OAuthTokenError)` path in `connect` already turns that into `MCPAuthRequired`, and the source is then skipped as it is today. This only stops a wait that cannot succeed: no authorization is granted or loosened. The real chat path and the `test:` path still wait for consent.

## Verification
A unit test covers the agent-build path. On a 401 with a failed refresh, the provider raises `MCPAuthRequired` well under the timeout, and the build skips the source. A matching test shows that a real chat session id still waits for the code.

## Sign-Off
*(written at completion)*
