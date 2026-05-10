# Leg: 05-http-mcp-in-chat

**Status**: planning
**Flight**: [Alignment — MCPs working well end-to-end](../flight.md)

## Objective

Vibe-code-walk the operator workflow for using a single attached HTTP MCP source from a chat session — exercising the happy-path tool-call → tool-result → assistant-synthesis loop, the mid-session OAuth re-auth path (`MCPAuthRequired` → inline Login button → modal → `auth_resolved` → resume), and the graceful-failure paths that mission criterion #10 demands (token expiry mid-call, server unreachable mid-call, malformed payload). Surface and fix bugs / UX gaps / polish issues inline. By leg close, the operator should feel that "I can use an HTTP MCP's tools from chat, and when something goes wrong the chat keeps working" both feel solid on the streamable-http transport.

## Context

- **F9 §1** — multi-leg vibe-coding shape; this leg is L5 (HTTP-in-chat analog of L6's stdio-in-chat). The vibing surface shifts from the studio area (L1-L4) to the chat area (L5-L7).
- **F9 §2 + Sizing Thresholds** — fix-inline default; per-anomaly LOC bars. **Cumulative production LOC outside vibing surfaces is at ~1193 (above §2's ~600 ceiling) after L1+L2+L3.** L5 should aim for ~0 production LOC outside the chat-area vibing-surface UI files. Backend changes that aren't in those files trigger immediate operator audit before dispatch. Per the L1+L2+L3 union pattern, the seven F9 vibing-surface UI files are: `mcp-server-editor.js`, `studio.js`, `studio.css`, `mcps-tab.js`, `agent-editor.js`, `chat.js`, `chat.css`. L5 primarily touches the last two plus `chat/*.js` submodules and `oauth-modal.js`, all of which qualify as chat-area vibing surface for §2 carve-out purposes.
- **F9 §4** — operator-felt + caplog gate (0 `MCPClient.disconnect` warnings across this leg's HAT exercises). L5 is the first chat-execution caplog measurement since F6's HAT baseline; signal is high if anything regresses.
- **F9 §5** — F8 carve-outs default defer. The per-agent OAuth re-auth gap (F8 A4 + A5) is the most likely L5 carve-out collision: if the operator's `cloudflare_api` refresh-token has expired and the chat triggers a tool call, the existing per-source re-auth flow (F5 L5) handles it via the inline Login button + OAuth modal — that's the carve-out-conformant landing. **The chat-side mid-session re-auth path is from F5 and is independent of F8 A4/A5.** F8's carve-out is about *per-(agent, source)* credential storage; the chat session reuses the source's tokens, which is what works today.
- **F9 §7** — architect pass before any inline fix touching: `MCPClient` lifecycle, OAuth flows in the chat path (`api.py:/api/oauth/start` + `_broadcast_one`'s auth-required emission), pool worker spawn-path (`_pool._entry_worker` synthetic-csid path used for source-edit Test, NOT used for chat), `MCPToolProvider.get_tools_for_agent` filter / namespace prefixing, agent core's `_dispatch_tool_calls` deferral logic. UI/CSS/copy edits inline-only.
- **F9 §9** — all code-change work delegated to subagents; parent context = vibing + triage only.
- **L1 outcome carry-forward**: `cloudflare_api` (OAuth) registered with `_cache.tools` populated and `_cache.auth_posture: "oauth"`. `cloudflare_docs` (no-auth, Shape C) registered. Both available for L5's chat exercise.
- **L3 outcome carry-forward**: at least one agent (call it the "L3 agent" here) has `cloudflare_api` attached via the agent-editor MCPs tab; `mcp_overrides` may have been exercised on it (denylist or allowlist mode). The L3 agent is the default L5 chat target.
- **F5 L5 carry-forward** (mid-session OAuth re-auth) — the inline "Login required" button + OAuth modal flow is in production at `chat.js:renderLoginRequiredButton` (line 369) and the WS event handlers `chat.js:643-668` (`auth_required` / `auth_resolved` / `auth_failed`). Reconnect-snapshot replay is idempotent via `clearLoginRequiredButton` (line 351). L5 vibing exercises this path under live conditions for the first time since F5's HAT.
- **F6 L3 / L4 carry-forward** — runtime tool resolver `_tool_provider.py:get_tools_for_agent` (line 183) applies `mcp_overrides` → namespaced tool names `mcp__{source}__{tool}`. Agent factory wires this in at `factory.py:get_tools_for_agent` integration (line 157). Tool execution dispatch + auth-required translation are at `agent/core.py:_execute_tool` (line 244) — the tool runtime catches `MCPAuthRequired` (line 258) and translates to `ToolResult(metadata={"is_auth_required": True, ...})`; generic exceptions are caught at line 275 and translate to `ToolResult(content="[error] Tool execution failed: {e}", is_error=True)`.
- **Methodology insight from L1+L2+L3 flight log** (carry-forward): exploratory vibing surfaces operator-felt issues more effectively than scripted scenarios. L5 follows the same pattern — scenarios below are coverage-check, NOT a strict script. Predicted-upfront anomaly hypotheses (L3's pattern) carry forward.
- **Cross-cut verification per F9 leg sketch** — explicit goal: confirm tool-list parity between L3's MCPs-tab attach view and L5's chat-time runtime-resolver view (after `mcp_overrides` applied). Drift here would be a regression in either L3's UI semantics or `_tool_provider.get_tools_for_agent`'s filter logic.

## L5 Carry-Forward Setup

For L5 to start cleanly, the operator confirms (at leg setup time):

- [ ] Dev container running on `http://localhost:8484`; web UI loads; chat area opens to welcome or session list.
- [ ] `cloudflare_api` source still registered + tokens valid. Quick check: navigate to source-edit page, click Refresh — should NOT trigger OAuth popup; tools list renders fast-path.
- [ ] L3 agent (with `cloudflare_api` attached) still exists. Quick check: navigate to Studio → Agents → tile shows `{N} MCP tools` count > 0 (per A-L3-3).
- [ ] If L3 agent's `mcp_overrides` are interesting (denylist or allowlist that excluded specific tools), operator notes which tools should NOT appear in chat-time tool inventory — sets up the cross-cut criterion's drift check.
- [ ] (Optional) `docker compose restart the-one` to clear warm pool — only if operator wants to verify cold-start chat UX. NOT required.
- [ ] Caplog baseline pre-flight: `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` = 0 before chat session starts.

If `cloudflare_api`'s refresh-token has expired since L3, operator can either re-Test on source-edit page first (clean baseline) OR start the chat session and let the mid-session OAuth re-auth flow fire as Scenario 4 — both are valuable. Operator picks at setup time.

## Inputs

What exists before this leg runs:

- F1-F8 + F9-L1+L2+L3 production state (HTTP create+test polished; stdio create+test polished; agent-editor MCPs tab + agent-tile tool counts + cache-first details polished).
- L3 agent with `cloudflare_api` attached + (possibly) `mcp_overrides` exercised.
- `the_one/interfaces/web/static/js/areas/chat.js` (731 LOC) — the L5 primary vibing surface.
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js` (67 LOC) + `chat/thinking-indicator.js` (35 LOC) + `chat/welcome.js` (91 LOC) + `chat/history-buckets.js` (142 LOC) + `chat/telemetry-overlay.js` (96 LOC) — chat sub-modules likely to surface during vibing.
- `the_one/interfaces/web/static/css/chat.css` (153 LOC) — chat styling.
- `the_one/interfaces/web/static/js/oauth-modal.js` (216 LOC) — OAuth modal load-bearing for mid-session re-auth.
- `the_one/agent/core.py:_execute_tool` (line 244) — tool execution + `MCPAuthRequired` translation (line 258) + generic exception catch (line 275).
- `the_one/agent/core.py:_dispatch_tool_calls` (line 159) — sequential tool dispatch + auth-required deferral.
- `the_one/agent/factory.py:_build` MCP-tools integration (line 157 — `if self.mcp_provider is not None and config.mcp_source_ids: mcp_tools = await self.mcp_provider.get_tools_for_agent(...)`).
- `the_one/mcp/_tool_provider.py:get_tools_for_agent` (line 183) — runtime resolver applying `mcp_overrides` → namespaced names.
- `the_one/mcp/errors.py:MCPAuthRequired` (line 75) — control-flow signal class.
- `the_one/interfaces/web/app.py:_send_to_session` (line 491) — WS broadcast helper.
- `the_one/interfaces/web/app.py:_broadcast_one` (line 602) — per-message broadcast routing including auth-required emission.
- `tests/browser/test_flow_chat.py` (72 LOC, 2 tests) + `tests/browser/test_flow_new_chat.py` (319 LOC, 11 tests) + `tests/browser/test_flow_markdown_chat.py` (176 LOC) — chat regression baseline.

## Outputs

What exists after this leg completes:

- The L3 agent's chat session has exercised at least one MCP tool call against `cloudflare_api` end-to-end with operator-felt "tool result rendered usefully in chat".
- The mid-session OAuth re-auth path has been exercised at least once (either naturally if tokens expired, or engineered via Reset on source-edit page mid-conversation).
- At least one graceful-failure scenario exercised: server unreachable OR token expiry mid-call. Malformed payload optionally exercised if engineerable; otherwise documented for L6/L7 follow-up.
- Any L5 inline fixes captured in diff and logged in flight log under "L5 → Inline Fixes Implemented".
- Flight log appended: per-scenario operator-felt notes, anomalies + triage + resolution, caplog count, cross-cut verification result.
- Chat session handed off to L7 (multi-MCP) with at least the L3 agent ready for multi-source attach.

## Acceptance Criteria

- [ ] Operator opens a chat with the L3 agent; sends a prompt that triggers at least one `cloudflare_api` MCP tool call; sees `tool_call` event render as `> tool_name(args)`; sees `tool_result` render with the API's response; sees the assistant message synthesize the result.
- [ ] Operator-felt sign-off on the tool-call → result rendering: "this works well" — formatting, timing, attribution, scrollback.
- [ ] **Cross-cut verified**: tool-list available to the L3 agent at chat-time (the agent's `tools` dict from `factory._build`) matches the L3 MCPs-tab attach-time tool-list for `cloudflare_api`, after applying `mcp_overrides`. Operator inspects via either (a) asking the agent to list its tools, (b) inspecting the WS `tool_call` events that fire across a few diverse prompts, or (c) checking `/api/agents` response field if the runtime resolver exposes a tools-list summary. No drift between L3's attach-time view and L5's runtime view.
- [ ] **Mid-session OAuth re-auth path exercised at least once**: either naturally (tokens expired between L3 and L5) or engineered (operator Resets `cloudflare_api` tokens on source-edit page mid-conversation, then sends a chat prompt that triggers a tool call). Expected flow: `tool_call` event → `auth_required` event → inline "Login required for cloudflare_api" button renders → operator clicks → OAuth modal → completes consent → modal closes + button disappears + "Resuming…" placeholder appears → resumed `tool_result` arrives → assistant continues. **Caplog must remain clean across the recovery.**
- [ ] **Graceful-failure scenario exercised at least once**: either token-expiry-mid-call (above) OR server-unreachable. Server-unreachable engineering options: (a) operator attaches a second agent to a deliberately-bogus URL source created for the purpose, then chats; (b) operator temporarily blocks outbound to `mcp.cloudflare.com` via container network rule; (c) operator opportunistically observes if Cloudflare's MCP server has any natural blip during the leg. Expected flow: tool call → connection error → `tool_result` with `is_error: true, content: "[error] Tool execution failed: ..."` → agent step continues (potentially retries or surfaces error in next assistant turn). Chat session does NOT crash; WS does NOT close.
- [ ] Caplog gate clean: `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` = 0 across L5's HAT exercises. **L5 is the first chat-execution caplog measurement since F6 baseline** — any non-zero count is high-signal regression.
- [ ] All prior `test_flow_chat.py` (2 tests) + `test_flow_new_chat.py` (11 tests) + `test_flow_markdown_chat.py` tests still pass UNMODIFIED unless an inline fix structurally changes the chat-event surface (in which case the test is updated as part of the same batch and flagged for L8 review).
- [ ] Any anomaly surfaced is triaged per F9 §2 + §5 and recorded in the flight log under "L5 → Anomalies Captured".
- [ ] Cumulative production LOC for L5 outside the seven vibing-surface UI files (chat-area files counted as in-budget for L5) is logged at leg close — target ~0 LOC; actual count flagged for L8 review queue if non-zero.

## Verification Steps

For each scenario, the operator reports the observed outcome in plain language. The Flight Director compares against the expected outcome and asks the operator to confirm "works well" before moving to the next scenario. Any divergence triggers triage + fix-or-defer.

Caplog gate check at any anomaly + at leg close: `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` — count should remain at 0.

Cross-cut tool-list parity check (criterion #3): the L3 MCPs-tab tool-list (with overrides applied; visible in agent-editor MCPs tab details panel) should match the chat-time tool-list. Operator inspects via WS events on a few diverse prompts — every `tool_call` event's `data.name` should be in the namespaced form `mcp__cloudflare_api__{tool}`, and the set of `{tool}` short names invoked over the leg should be a subset of what L3's attach-time view exposes (modulo overrides applied at attach-time).

Mid-session OAuth re-auth verification (criterion #4): visual chain — `> tool_name(args)` tool-call message → "Login required for cloudflare_api" button (NOT auto-popup; operator-initiated click) → OAuth modal opens → consent screen → modal closes → button disappears → "Resuming…" system message → tool result arrives within a few seconds of consent.

Graceful-failure verification (criterion #5): on connection error, the tool message renders with the `tool error` class (red-tinted bubble per `chat.css`'s `.tool` styling). The error content is operator-readable. The `done` event still fires on the WS, so the input box re-enables and `inFlightSessions` clears (`chat.js:670-678`). Subsequent send works normally.

## Implementation Guidance

### Procedure shape (F9 §1's structured pattern, exploratory mode per L1+L2+L3 methodology insight)

1. **Setup** — operator confirms L5 Carry-Forward Setup checklist; L5 begins.
2. **Walk operator scenarios** — exploratory primary, scenario list below as coverage check / fallback.
3. **Capture issues** — anomalies logged immediately into flight log under "L5 → Anomalies Captured".
4. **Triage** — per §2 + §5: inline-fix (default for ≤100 LOC + leg-scope) / absorb-into-sibling (typically L6 for stdio-equivalents or L7 for multi-source) / defer-to-follow-up. Architect pass per §7 if the fix touches a known-problematic-path.
5. **Fix or document** — inline fixes implemented immediately via Implementer subagent (per §9); absorbs/defers logged with target-leg or follow-up-flight reference.
6. **Re-verify** — re-walk affected scenarios to confirm fix.
7. **Close leg** — operator-felt sign-off + caplog gate verification + flight log finalization.

### Operator scenarios (7 total, coverage check for exploratory mode)

**Scenario 1 — Open chat with the L3 agent + tool-inventory parity.**
Operator: navigate to chat area → sidebar agent dropdown → pick the L3 agent → new session starts (`chat.js:startSessionWith`, line 182).
Expected: chat chrome renders; agent badge updates; welcome canvas hidden if setup complete. Send first prompt that's deliberately introspective (e.g., "what tools do you have available?"); observe assistant's response — should mention `cloudflare_api` tools by their namespaced names. Cross-cut check: the named tools should be a subset of what L3's MCPs tab showed for cloudflare_api after `mcp_overrides` applied.
Vibing prompts: Is the agent's self-description of its tools clear? Does it explicitly mention which MCP source the tools came from? Are the namespaced names (`mcp__cloudflare_api__list_zones`, etc.) ergonomic when the agent surfaces them in conversation, or do they look like internal plumbing leaking?

**Scenario 2 — Happy-path tool-call → result rendering.**
Operator: send a prompt that triggers a `cloudflare_api` tool call (e.g., "list my Cloudflare zones" or "show recent analytics for {a known domain}"). Backend runs through `agent/core.py:_run_iterations` → tool call dispatched via `_execute_tool` → `tool_call` WS event → tool runs → `tool_result` WS event → assistant synthesizes.
Expected: thinking indicator shows briefly; `> tool_name(args)` message renders (`chat.js:628 — tool_call handler`); after the tool completes, `tool_result` content renders as a separate message bubble; assistant response synthesizes the result and continues. Iteration boundaries handled by `finalizeStreamingBubble` (`chat.js:633, 638`).
Vibing prompts: Tool-call rendering readable (or is `Object.entries(...).map(...)` formatting awkward for nested args)? Tool-result formatting useful (or does a large JSON dump break layout)? Does the assistant's synthesis of the tool result feel like a coherent response, or does it parrot the tool output? Is the visual distinction between assistant text + tool messages strong enough? Latency feels acceptable?

**Scenario 3 — Multiple tool calls in single agent step.**
Operator: send a prompt that requires the agent to make 2-3 tool calls before answering (e.g., "list my zones and then show the DNS records for the first one"). Backend dispatches tool calls sequentially via `agent/core.py:_dispatch_tool_calls` (line 159).
Expected: multiple `tool_call` / `tool_result` pairs render in order; `finalizeStreamingBubble` correctly resets the streaming bubble at each iteration boundary; final assistant synthesis uses all results.
Vibing prompts: Multi-tool-call sequences readable in the chat history? Iteration boundaries visually clear? Does the chat lag noticeably across multiple calls? Any flicker / jumpiness in the message list as new bubbles append? Does scrollback work?

**Scenario 4 — Token expiry mid-session (mission criterion #10 + F5 L5 path).**
Operator: in the middle of a chat session, navigate to `cloudflare_api`'s source-edit page → click Reset connection (clears tokens server-side per L1's polish). Return to chat → send a prompt that triggers a tool call.
Expected flow: `tool_call` event renders `> tool_name(args)`; backend tool execution catches `MCPAuthRequired` at `agent/core.py:258` → returns `ToolResult(metadata={"is_auth_required": True, source_id, resource_metadata_url, consent_url, tool_call_id})`; `_dispatch_tool_calls` defers remaining tool calls (line 206); `_broadcast_one` emits `auth_required` event INSTEAD of broadcasting a tool message (`app.py:_broadcast_one`, line 602); `chat.js:643 — auth_required handler` calls `renderLoginRequiredButton` (line 369) which appends the inline "Login required for cloudflare_api" button to the message list. Operator clicks button → `App.oauthModal.open` (`oauth-modal.js:212 — window.App.oauthModal`); modal opens to OAuth consent flow → operator completes → `auth_resolved` event arrives → `clearLoginRequiredButton` clears the inline button + `App.oauthModal.close` (`chat.js:655-661`); "Resuming…" placeholder appears (`chat.js:renderResumingPlaceholder`, line 395); deferred tool calls re-dispatch (`agent/core.py:resume_after_auth`, line 209); `tool_result` arrives; assistant continues.
Vibing prompts: Inline button copy operator-readable? Modal experience clear? "Resuming…" placeholder reassuring or noise? Latency from consent → tool_result acceptable? Caplog stays clean across the recovery? Does the chat scrollback after recovery look right (no orphaned `<auth required>` placeholder content showing the literal string from `agent/core.py:266`)?

**Scenario 5 — Server unreachable mid-call (mission criterion #10).**
Operator: engineer a connection error. **Engineering options** (operator picks):
  - (a) Create a deliberately-bogus URL source (e.g., `https://bogus-mcp.invalid/mcp`) → attach to a second test-agent → chat with that agent → tool call attempt fails connection.
  - (b) Temporarily block outbound to `mcp.cloudflare.com` via container network rule (operator-side; not in-scope to engineer in the leg).
  - (c) Opportunistic — wait for Cloudflare service blip during the leg (unreliable).
Expected: tool execution catches the connection error at `agent/core.py:275 — except Exception` → returns `ToolResult(content="[error] Tool execution failed: {e}", is_error=True)`; chat renders with `tool error` class (`chat.js:639 — addMsg(data.is_error ? 'tool error' : 'tool', ...)`); assistant either retries or acknowledges the error in its next turn; `done` event fires; input re-enables.
Vibing prompts: Error message operator-readable, or does the exception type leak through unhelpfully? Is `tool error` styling visually distinct from `tool` (red tint? icon?)? Does the agent's recovery message handle the error gracefully? WS stays connected? Caplog clean?

**Scenario 6 — Server returning malformed payload (mission criterion #10, optional / engineer-as-able).**
Hard to engineer naturally with a healthy MCP server. **Engineering options**:
  - (a) Deliberately point a source at an HTTP endpoint that responds 200 with JSON that's not valid MCP (e.g., a static JSON file URL) — wraps Scenario 5's bogus-URL pattern with a different failure mode.
  - (b) Skip if no clean engineering path; document for L6/L7 follow-up. **Acceptable variation.**
Expected (if exercised): SDK-level parsing error → caught at `agent/core.py:275` → translated to `is_error: true` tool result. Same surface as Scenario 5 but different exception type. Operator-readable error message?
Vibing prompts: Same as Scenario 5; specifically how the malformed-payload error message reads vs the connection-error one.

**Scenario 7 — Agent without MCP attached fallback / sanity.**
Operator: switch to a different agent that has NO MCPs attached (built-in tools only). Send a prompt that would have triggered an MCP tool call.
Expected: agent uses built-in tools or replies without tool. Sanity check that MCP tab attach is the only thing wiring MCP availability — i.e., `factory.py:157 — if self.mcp_provider is not None and config.mcp_source_ids:` correctly short-circuits when `mcp_source_ids` is empty.
Vibing prompts: Does the agent gracefully degrade? Does it explicitly mention what it can/can't do? Any leakage of the L3 agent's tools into this agent's context (would indicate factory caching bug)?

### Predicted anomalies (Flight Director's setup hypotheses; not commitments)

Surfaced upfront so the operator's vibing time is spent on *surfacing* rather than *anticipating*. If actually surfaces, triage per §2:

1. **`<auth required>` literal placeholder content in chat history**: when the auth-required path fires, `agent/core.py:266 — content="<auth required>"` is the placeholder content stored on the `ToolResult`. The deferred-tool-calls pause means this `ToolResult` is NOT emitted as a normal tool message — `_broadcast_one` emits `auth_required` event instead. BUT if the chat history is re-rendered from server-side stored events on reconnect (per `chat.js:renderHistory` at line 192), and the deferred ToolResult got persisted with the literal placeholder content, the operator might see `<auth required>` rendered as a tool message after reconnect. **Triage TBD if surfaces**: cosmetic if scrollback only; degraded if it corrupts the conversation flow.

2. **`[error] Tool execution failed:` prefix is generic**: `agent/core.py:278` constructs the error content as `f"[error] Tool execution failed: {e}"`. No source attribution (which MCP failed?), no tool-name attribution (which tool?), exception type leaks through (`MCPConnectionError: ...`). **Triage TBD if surfaces**: cosmetic-to-degraded; an operator-readable error format could improve graceful-failure UX significantly. Mission criterion #10 explicitly cares about how failures surface to operator.

3. **`Resuming…` placeholder is a system message**: `chat.js:395 — renderResumingPlaceholder` adds `addMsg('system', 'Resuming…')`. After the resumed `tool_result` arrives, the placeholder stays in chat history forever. Operator may want it auto-removed once the result lands, or styled distinctly. **Triage TBD**: cosmetic.

4. **`tool error` styling weak vs `tool`**: `chat.js:639 — addMsg(data.is_error ? 'tool error' : 'tool', ...)` — the class string is `'tool error'` (space-separated → two CSS classes). Need to verify `chat.css` actually defines a distinct `.msg.tool.error` style; if not, the visual signal of "this tool failed" is lost. **Triage cosmetic if needs CSS bump; degraded if the bubble is identical to a successful tool result**.

5. **Long-running tool with no progress indicator**: `chat.js:629 — hideThinking()` is called at `tool_call` event. If a tool takes >3s, the chat shows the `> tool_name(args)` message but nothing else. No progress dots, no spinner. Operator may feel chat is hung. **Triage cosmetic**: a between-tool indicator (or a per-tool spinner on the tool message bubble) could help.

6. **Tool result content rendering — large/structured payloads**: `addMsg('tool', content)` calls `App.chat.renderMessage('tool', text, opts)` — does this render markdown for tool results? Code blocks? JSON dumps? Large lists? `chat.js:208 — addMsg(ev.is_error ? 'tool error' : 'tool', ev.content, null, histOpts)` is the history-replay path; live path is at `chat.js:639`. Both pass content through the same renderer. Need to verify `renderMessage` handles plain text vs markdown for the tool class. **Triage TBD if surfaces**: degraded if a 50KB JSON dump breaks layout; cosmetic if just ugly.

7. **F5 L5 inline Login button reconnect-snapshot replay**: `chat.js:351 — clearLoginRequiredButton` is called BEFORE `renderLoginRequiredButton` to ensure idempotency on WS reconnect. Verify under live conditions: trigger Scenario 4, then force a WS reconnect (network blip simulation or browser refresh), confirm only one button renders. **Triage TBD if surfaces**: known-fragile path; F5 L5 already shipped fix.

8. **`mcp_overrides` keyed-by-name orphan after rename**: if the operator renames `cloudflare_api` mid-session via API (unlikely but possible), the agent's `mcp_overrides` keyed by old name would orphan; `_tool_provider.py:_warn_orphan_overrides` (line 149) logs WARNING but the runtime resolver returns no overrides → all tools enabled. **Triage cosmetic**: edge case; operators don't typically rename sources mid-chat. F8 carve-out adjacent.

### Subagent dispatch pattern (F9 §9)

Same as L1+L2+L3: parent context = vibing + triage; all code-change work via subagent. Each spawn carries:

- bug description + acceptance criterion (re-verify by re-walking Scenario N — operator should see X)
- target file(s) + line ranges using cite-by-symbol + snippet form (e.g., `chat.js:renderLoginRequiredButton — "Login required for"`)
- §7 architect-pass output if it preceded the fix
- noted §2 LOC budget — L5 should stay ~0 LOC outside the chat-area vibing-surface UI files (`chat.js`, `chat.css`, `chat/*.js`, `oauth-modal.js`)

Returns structured summary: file paths + brief description + LOC count + any flagged questions or follow-ups.

## Edge Cases

- **Token expiry between L3 and L5 (natural)**: cloudflare_api tokens may have expired since L3 attach. Operator can re-Test on source-edit page first (clean baseline) OR let Scenario 4 fire naturally on the first chat tool call. Both are valid; either way the F5 L5 path handles it. Caplog should remain clean across the recovery.
- **Reconnect during tool execution**: WS may drop mid-tool-call (mobile network, container restart). On reconnect, `chat.js` re-establishes; pending tool execution may have completed server-side. `app.py:_send_pause_snapshot_if_needed` (referenced in `chat.js:349 — "L3 reconnect-snapshot replay"`) re-broadcasts pending auth-required state. Verify visual recovery is clean.
- **Empty `mcp_source_ids` after re-edit**: if operator edits the L3 agent during the chat session and removes `cloudflare_api`, the existing chat session's agent instance still has the old toolset (factory-built once at session start). New tool calls will succeed using the stale toolset. **Triage cosmetic**: documented behavior; not L5's defect. May be worth flagging for L8 review queue if surfaces.
- **Multi-tool-call with auth_required mid-batch**: if Scenario 3 (multi-tool-call) AND Scenario 4 (auth expiry) intersect — first tool call triggers auth_required, subsequent tool calls in the same agent step are deferred — verify `_dispatch_tool_calls`'s deferral (line 206) correctly captures `tcs[i:]` and resume re-dispatches them in order. F5 L5 specifically handles this; verify under live conditions.
- **Cloudflare service hiccup**: if `cloudflare_api` server is genuinely unreachable during L5, every Scenario 2/3 tool call surfaces as Scenario 5 (graceful-failure) until service recovers. Triage as external noise, not L5 defect. Operator can switch to `cloudflare_docs` (no-auth) for an alternate target.
- **`thinking_indicator` lifecycle around `auth_required`**: `chat.js:629 — hideThinking()` fires on `tool_call`; `chat.js:651 — hideThinking()` also fires on `auth_required`. If the auth_required event arrives WITHOUT a preceding tool_call event (unusual but possible during reconnect-snapshot replay), the thinking indicator might leak. Verify.
- **`done` event semantics during auth pause**: when `_dispatch_tool_calls` defers, does the agent emit a `done` event (closing the iteration) or stay in pending state? `chat.js:670 — done handler` re-enables the input; if it fires during the pause, operator could send another message before the deferred tool result arrives. Verify protocol.

## Files Affected (likely)

Read-only on most files; vibing surfaces are bolded. Actual files depend on what surfaces.

**Vibing-surface UI files (chat-area; treated as in-budget for L5 per §2's seven-vibing-surface carve-out):**
- `the_one/interfaces/web/static/js/areas/chat.js` — primary L5 vibing surface
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js` — message rendering
- `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js` — thinking dots
- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — welcome canvas
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — session sidebar grouping
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — token/context telemetry
- `the_one/interfaces/web/static/css/chat.css` — chat styling
- `the_one/interfaces/web/static/js/oauth-modal.js` — OAuth modal load-bearing for mid-session re-auth

**Backend / non-vibing files (changes here count toward §2 ceiling — currently ~1193 / ~600):**
- `the_one/agent/core.py:_execute_tool` (line 244) — only if anomaly forces backend change to `MCPAuthRequired` translation OR generic exception translation. Architect pass per §7 required.
- `the_one/agent/core.py:_dispatch_tool_calls` (line 159) — only if multi-tool-call deferral surfaces an anomaly. Architect pass per §7 required.
- `the_one/interfaces/web/app.py:_broadcast_one` (line 602) — only if WS event-emission anomaly surfaces. Architect pass per §7 required.
- `the_one/interfaces/web/api.py:/api/oauth/start` (line 1733) — only if mid-session OAuth flow surfaces a backend anomaly. Architect pass per §7 required.
- `the_one/mcp/_tool_provider.py:get_tools_for_agent` (line 183) — only if `mcp_overrides` resolution at chat-time surfaces a cross-cut drift anomaly. Architect pass per §7 required.

**Test baseline (must remain unmodified unless inline fix structurally changes the chat-event surface):**
- `tests/browser/test_flow_chat.py` (72 LOC, 2 tests)
- `tests/browser/test_flow_new_chat.py` (319 LOC, 11 tests)
- `tests/browser/test_flow_markdown_chat.py` (176 LOC)

## Citation Audit

Citations to verify against current code at leg design time:

- `the_one/agent/core.py:244 — async def _execute_tool`
- `the_one/agent/core.py:258 — except MCPAuthRequired as e:`
- `the_one/agent/core.py:266 — content="<auth required>"`
- `the_one/agent/core.py:275 — except Exception as e:`
- `the_one/agent/core.py:278 — content=f"[error] Tool execution failed: {e}"`
- `the_one/agent/core.py:159 — async def _dispatch_tool_calls`
- `the_one/agent/core.py:206 — self._deferred_tool_calls = list(tcs[i:])`
- `the_one/agent/core.py:209 — resume_after_auth`
- `the_one/agent/factory.py:157 — if self.mcp_provider is not None and config.mcp_source_ids:`
- `the_one/mcp/_tool_provider.py:183 — async def get_tools_for_agent`
- `the_one/mcp/_tool_provider.py:149 — _warn_orphan_overrides`
- `the_one/mcp/errors.py:75 — class MCPAuthRequired(MCPClientError)`
- `the_one/interfaces/web/app.py:491 — async def _send_to_session`
- `the_one/interfaces/web/app.py:602 — async def _broadcast_one`
- `the_one/interfaces/web/api.py:1733 — Body: source_id, chat_session_id, tool_call_id?, resource_metadata_url?`
- `chat.js:182 — function startSessionWith`
- `chat.js:192 — function renderHistory`
- `chat.js:208 — addMsg(ev.is_error ? 'tool error' : 'tool', ev.content, ...)`
- `chat.js:351 — function clearLoginRequiredButton`
- `chat.js:369 — function renderLoginRequiredButton`
- `chat.js:395 — function renderResumingPlaceholder`
- `chat.js:628 — else if (data.type === 'tool_call')`
- `chat.js:633 — finalizeStreamingBubble (after tool_call)`
- `chat.js:636 — else if (data.type === 'tool_result')`
- `chat.js:638 — finalizeStreamingBubble (after tool_result)`
- `chat.js:639 — addMsg(data.is_error ? 'tool error' : 'tool', data.content)`
- `chat.js:643 — else if (data.type === 'auth_required')`
- `chat.js:651 — hideThinking()` (in auth_required handler)
- `chat.js:655 — else if (data.type === 'auth_resolved')`
- `chat.js:663 — else if (data.type === 'auth_failed')`
- `chat.js:670 — else if (data.type === 'done')`
- `oauth-modal.js:1 — App.oauthModal — OAuth Login modal`
- `oauth-modal.js:212 — window.App.oauthModal`
- `tests/browser/test_flow_chat.py` (72 LOC, 2 tests) — baseline
- `tests/browser/test_flow_new_chat.py` (319 LOC, 11 tests) — baseline
- `tests/browser/test_flow_markdown_chat.py` (176 LOC) — baseline

**Audit summary**: 35 citations verified at leg design time. 33 OK, 2 drift repaired inline:

| Citation (drafted) | Classification | Resolution |
|---|---|---|
| `_tool_provider.py:153 — _warn_orphan_overrides` | drifted | Repaired to `:149` (def line; current code) |
| `agent/core.py:211 — _resume_after_auth` | drifted (line + symbol-name typo) | Repaired to `:209 — resume_after_auth` (no leading underscore — public method) |

All chat.js / oauth-modal.js / app.py / api.py / errors.py / factory.py / core.py (other than the one above) citations verified line-exact. No `gone` or `unverifiable` classifications.
