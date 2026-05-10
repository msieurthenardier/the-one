# Operator HAT Script — F10 Lazy Tool Discovery

**Flight**: F10 (Lazy tool discovery — search-tools / search-mcps as the only catalog entries)
**Date drafted**: 2026-05-10
**Walked by**: Flight Director (interactive, between Phase 2d PR draft and Phase 3 flight landing)

This script walks the operator through the F10 acceptance test. The HAT validates the operator-felt success criterion: the agent must *search* before tools become available, mid-session MCP attachment is reflected in new sessions, and the caplog remains clean throughout.

---

## Prerequisites

Before beginning the HAT:

- Dev container is running (`make rebuild` or `docker compose up` if not already). Verify: `docker ps` shows `the-one` container running.
- At least one registered MCP source with a cached tool list. Recommended: Cloudflare API MCP (`https://mcp.cloudflare.com/mcp`) — if already registered from F9 vibing, verify the OAuth token is still valid by opening Studio → MCP Sources → cloudflare_api → clicking "Refresh connection." If the token has expired, complete the OAuth flow again.
- A default agent exists in Studio. If not, create one (any provider/model that supports tool use).

---

## Step 1: Confirm environment

- Open Studio in the browser.
- Navigate to Studio → MCP Sources. Confirm at least one source is registered with a non-empty tools list visible in the source-edit page's Tools section.
- Navigate to Studio → Agents. Confirm a default agent exists with the Cloudflare API source attached (or attach it now via the agent editor → MCPs tab).
- Confirm the agent's MCPs tab shows the source as attached.

**Expected**: environment is ready. No errors in the container logs from this navigation.

---

## Step 2: Test the lazy-discovery model — "what tools do you have available?"

> **Operator-felt callout**: this is the NEW model — agent searches before listing. NOT a regression.

- Open a new chat session with the attached agent.
- Send the message: **"what tools do you have available?"**
- Observe the chat UI's tool-call events as they appear.

**Expected behavior**:
1. **Iteration 1**: the agent's first tool call is `search_tools("")` or `search_mcps("")` (or both in sequence). The `tools=` array for this call contains only the 3-baseline entries: `search_tools`, `search_mcps`, `continue`. The agent does NOT have access to any built-in tools or MCP tools yet.
2. **Iteration 2**: after the search calls return, the matched schemas are now visible. If the agent called `search_mcps("")`, Cloudflare API tool schemas appear in this iteration's `tools=` array.
3. **Final response**: the agent synthesizes a text list of the tools it discovered. The response mentions the Cloudflare API tools by name.

**What you should NOT see**: the agent immediately listing all tools in its first response without making any search calls. If you see that, it's a sign the eager-load model is still active — stop and investigate before continuing.

**Why this is correct**: F10 replaced the eager-load-all-tools model with a 2-tool baseline. The agent must search to discover what it can do. This is intentional and improves token efficiency by only loading schemas the agent needs in the current session.

---

## Step 3: Verify mid-session attach is reflected in a NEW session

- From a different browser tab (or after the current chat session ends), go to Studio → Agents → the same agent → MCPs tab.
- Attach an additional MCP source that was NOT attached before (or, if only one source is registered, register a second source now — e.g., a local `uvx mcp-server-time` stdio source — then attach it).
- **Start a NEW chat session** with this agent (the previously-open chat session must be ended first — close the chat tab or navigate away and back).
- In the new session, send: **"what tools do you have available?"**

**Expected**: the agent's `search_mcps("")` call returns results that now include the newly-attached source. The agent lists tools from both the original source AND the newly-attached source.

---

## Step 4: Verify session isolation — new attachment NOT visible in old session

- Return to the original chat session that was open BEFORE the new attachment (if it is still open in another tab). If it was closed, note that this step is "pass by definition" — closed sessions don't persist loaded sets.
- If the original session is still open, repeat the question: **"what tools do you have available?"**

**Expected**: the newly-attached source's tools are NOT listed in this response. The original session's loaded set was established before the new attachment; it does not refresh mid-session.

**Operator confirmation**: confirm this behavior is expected. The design choice (sessions don't refresh mid-session; new session required to see new attachments) is intentional per F10 Design Decision §3. This isolates session state from concurrent configuration changes and keeps the LLM's tool catalog stable within a conversation.

---

## Step 5: Caplog gate verification

After completing Steps 1-4, run the caplog check:

```
docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"
```

**Expected result**: `0`

If the result is non-zero, note the count and check the full log around those lines:

```
docker compose logs --tail 200 the-one 2>&1 | grep -B 2 -A 2 "MCPClient.disconnect"
```

A non-zero count means the `_open_*_transport_stack` fix from F6.6 L1 has regressed. This is a blocking defect — do not proceed to Phase 3 until resolved.

---

## HAT sign-off

After completing all 5 steps, the Flight Director records the outcome:

- **PASS**: all 5 steps completed with expected results. Record in F10 flight log. Phase 3 (flight landing) may proceed.
- **FAIL**: one or more steps produced unexpected results. File anomalies in the F10 flight log. Phase 3 blocked until anomalies are resolved (likely requires an additional Developer loop and amended PR commit before returning to the HAT gate).

For Shape A token-cost measurement: if the operator wishes to run the real-LLM measurement during this HAT session, collect pre-F10 and post-F10 input-token counts per the instructions in `token-cost-measurement.md` Shape A section and append the results there.
