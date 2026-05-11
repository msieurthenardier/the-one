# HAT — F6 Per-agent MCP attach + tool-routing

## F10 contract note

Post-F10 (lazy tool discovery): `agent.tools.all_schemas()` returns the
full CANDIDATE registry — every tool the agent CAN load via search. The
LLM only sees `[search_tools, continue] + agent._loaded_schemas` per
iteration. The unified `search_tools` covers both built-in and MCP
catalogs; there is no separate `search_mcps`. HAT scripts in this file
that script-count `all_schemas()` filtered by `mcp__*` prefix are
validating registry membership, not model-visibility. The assertions
still hold; the prose interpretation has shifted.

**Type**: Human Acceptance Test. The operator runs each step, observes the result, and reports the outcome. There is no automated assertion — the human's judgment is the gate.

**Scope**: Two tiers.

- **Tier 1** (required, per F6 flight §7): in-repo dev-container procedure against `mcp-server-fetch`. The binary go/no-go for retiring the F2-known-issue (`MCPClient transport close failed` warning) from `missions/07-mcp-integration/mission.md::Known Issues`.
- **Tier 2** (binding for F6.5 close): live Cloudflare API MCP procedure against F6.5's Test connection button + F5's DCR happy path. Per F6.5 Design Decision §4 — flight cannot land without this PASS. Replaces the prior GitHub manual-entry procedure (deleted at F6.5 L0+L1 along with the manual-entry OAuth surface).

**Prerequisites**:

```bash
# Inside the project root
docker compose ps                              # the-one service shows (healthy)
docker compose exec the-one which bwrap        # → /usr/bin/bwrap
docker compose exec the-one python -c "import mcp_server_fetch; print('OK')"
# If the import fails:
docker compose exec the-one pip install mcp-server-fetch
# WARNING: the install downgrades httpx to 0.27.x. F5 OAuth is import-clean
# under that version but has not been runtime-tested. If F5 OAuth breaks at
# runtime post-install, file a follow-up flight to pin httpx>=0.28 in the
# Dockerfile and bump mcp-server-fetch's compat range.
```

---

## Tier 1 — Required (in-dev-container, ~10 min)

### Pre-flight

Open a shell at the project root. The procedure assumes the dev container at `localhost:8484` (default `the_one.config::settings.port`).

Capture the start timestamp so the post-run log scan is bounded:

```bash
HAT_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "HAT_START=$HAT_START"   # e.g. 2026-05-08T11:30:00Z
```

### Step 1 — Pre-state: register the MCP source

Register a stdio source pointing at `mcp-server-fetch`. Both agents will attach to this same source (per-agent isolation is verified in step 4).

```bash
curl -s -X POST http://localhost:8484/api/mcp-sources \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "fetch_local",
    "type": "stdio",
    "config": {"command": "python", "args": ["-m", "mcp_server_fetch"], "cwd": null},
    "secrets": {}
  }' | jq

# Capture the source id for later steps.
FETCH_ID=$(curl -s http://localhost:8484/api/mcp-sources | jq -r '.[] | select(.name == "fetch_local") | .id')
echo "FETCH_ID=$FETCH_ID"
```

**Verify**: `FETCH_ID` is a non-empty UUID-shaped string. If you get an error, paste the response + the relevant `docker compose logs --tail=20 the-one` and stop here.

### Step 2 — Configure two agents with attach + override

Pick a provider config to assign and create two agents. Attach `fetch_local` to both with **different** `mcp_overrides[fetch_local].env` values so per-agent isolation kicks in (F4's per-`(agent, source)` keying spawns distinct subprocesses when overrides differ).

```bash
PROVIDER_ID=$(curl -s http://localhost:8484/api/llm-providers | jq -r '.[0].id')
echo "PROVIDER_ID=$PROVIDER_ID"

# Agent A — attach with env override A.
curl -s -X PUT http://localhost:8484/api/agents/hat_agent_a \
  -H 'Content-Type: application/json' \
  -d "{
    \"name\": \"hat_agent_a\",
    \"description\": \"F6 HAT agent A\",
    \"provider_config_id\": \"$PROVIDER_ID\",
    \"llm_model\": \"qwen2.5:7b\",
    \"mcp_source_ids\": [\"$FETCH_ID\"],
    \"mcp_overrides\": {\"fetch_local\": {\"env\": {\"HAT_AGENT\": \"A\"}}}
  }" | jq

# Agent B — same source, different env override.
curl -s -X PUT http://localhost:8484/api/agents/hat_agent_b \
  -H 'Content-Type: application/json' \
  -d "{
    \"name\": \"hat_agent_b\",
    \"description\": \"F6 HAT agent B\",
    \"provider_config_id\": \"$PROVIDER_ID\",
    \"llm_model\": \"qwen2.5:7b\",
    \"mcp_source_ids\": [\"$FETCH_ID\"],
    \"mcp_overrides\": {\"fetch_local\": {\"env\": {\"HAT_AGENT\": \"B\"}}}
  }" | jq
```

**Verify**: both PUTs return the agent payload echoed back, including `mcp_source_ids: [<FETCH_ID>]` and the distinct `HAT_AGENT` env values.

### Step 3 — Tool-list visibility

Build agent A and inspect its tool registry. The MCP tools appear under the prefixed namespace `mcp__fetch_local__*`.

```bash
docker compose exec the-one python <<'PY'
import asyncio
from the_one.agent.factory import AgentFactory
from the_one.agent.store import SQLiteAgentStore
from the_one.db.connection import get_connection

async def main():
    conn = await get_connection()
    factory = AgentFactory(store=SQLiteAgentStore(conn))
    agent = await factory.create("hat_agent_a")
    # NOTE (F10 L1): agent.tools.all_schemas() returns the full CANDIDATE
    # registry — the tools the agent CAN load via search, not the ones
    # currently visible to the LLM in tools=. The MCP-prefix count below
    # still validates "the registry was correctly populated by factory."
    schemas = agent.tools.all_schemas()
    print(f"Total candidate tools: {len(schemas)}")
    mcp_tools = [s for s in schemas if s["name"].startswith("mcp__")]
    print(f"MCP tools: {[s['name'] for s in mcp_tools]}")

asyncio.run(main())
PY
```

**Verify**: at least one MCP tool listed under `mcp__fetch_local__*`. `mcp-server-fetch` exposes a `fetch` tool; expect `mcp__fetch_local__fetch`. The full prefix MUST be `mcp__fetch_local__`.

Note (F10): the LLM does NOT see these MCP tools in its `tools=` array at session start. The agent must call `search_tools` to load them into the model-visible set (the unified `search_tools` covers both built-in and MCP catalogs). This HAT step validates registry membership, not model-visibility.

If you see zero MCP tools but no Python error: check `docker compose logs --tail=50 the-one` for a `WARNING: MCP source 'fetch_local' failed to connect` (failure class #2 — graceful-degrade kicked in). Diagnose + report.

### Step 4 — Tool-call dispatch + per-agent isolation

Open the chat UI for agent A in a browser at `http://localhost:8484/chat?agent=hat_agent_a`. Send a message that should trigger the fetch tool:

> Use the fetch tool to retrieve `https://example.com/`. Show me the title.

Watch the response. The tool call should round-trip through the F4 pool to the bwrap-spawned subprocess and return the page text. Then **immediately** check the subprocess count:

```bash
docker compose exec the-one pgrep -af mcp_server_fetch
```

**Verify**: exactly **one** PID running.

Now open a second tab to `http://localhost:8484/chat?agent=hat_agent_b` and send the same prompt. After the response lands:

```bash
docker compose exec the-one pgrep -af mcp_server_fetch
```

**Verify**: now **two** PIDs (one per agent — F4's per-`(agent, source)` keying with distinct env overrides forces distinct subprocesses).

### Step 5 — Graceful degrade

Delete the source via the API while both agents have warm pool entries:

```bash
curl -s -X DELETE "http://localhost:8484/api/mcp-sources/$FETCH_ID" -w 'HTTP %{http_code}\n'
```

Now rebuild agent A and inspect the tool registry:

```bash
docker compose exec the-one python <<'PY'
import asyncio
from the_one.agent.factory import AgentFactory
from the_one.agent.store import SQLiteAgentStore
from the_one.db.connection import get_connection

async def main():
    conn = await get_connection()
    factory = AgentFactory(store=SQLiteAgentStore(conn))
    agent = await factory.create("hat_agent_a")
    # NOTE (F10 L1): all_schemas() returns CANDIDATE registry membership —
    # validates that the deleted source's tools are absent from the registry.
    mcp_tools = [s["name"] for s in agent.tools.all_schemas() if s["name"].startswith("mcp__")]
    print(f"MCP tools after delete + rebuild: {mcp_tools}")

asyncio.run(main())
PY
```

**Verify**: zero `mcp__fetch_local__*` tools. The agent rebuild succeeded (no exception); the deleted source's tools are absent.

Also check the docker logs for the expected WARNING:

```bash
docker compose logs --since="$HAT_START" the-one 2>&1 | grep -E "deleted MCP source|failed to connect"
```

**Verify**: at least one log line matching `agent 'hat_agent_a' references deleted MCP source <FETCH_ID>; skipping`.

### Caplog gate — the binary go/no-go for F2-known-issue retirement

This is the F2-known-issue retirement decision point. Scan the docker logs from `HAT_START` to now for the verbatim warning string F5 L1 sought to retire:

```bash
docker compose logs --since="$HAT_START" the-one 2>&1 \
  | grep "MCPClient transport close failed" \
  | wc -l
```

**Decision**:
- Count is **0** → **PASS**. F2-known-issue retirement gate satisfied. Report PASS.
- Count is **> 0** → **FAIL**. Capture the matching lines (`docker compose logs --since="$HAT_START" the-one 2>&1 | grep "MCPClient transport close failed"`) and report FAIL.

### Cleanup (optional)

```bash
curl -s -X DELETE http://localhost:8484/api/agents/hat_agent_a -w 'HTTP %{http_code}\n'
curl -s -X DELETE http://localhost:8484/api/agents/hat_agent_b -w 'HTTP %{http_code}\n'
# fetch_local already deleted in Step 5
```

---

## Outcomes

### On PASS

The Flight Director:

1. Edits `missions/07-mcp-integration/mission.md` to remove the F2-known-issue line under `## Known Issues`.
2. Commits as a fixup on `flight/06-mcp-attach-and-tool-routing`: `flight/06: Tier-1 HAT PASS — retire F2-known-issue`.
3. Marks PR #35 ready for review (drops draft status).

### On FAIL

The Flight Director files a follow-up flight with this scope:

- Revert F5 L1's `_open_streamable_http_transport_stack` helper at `the_one/mcp/transports/streamable_http.py`.
- Revert F5 L1's `_open_stdio_transport_stack` helper at `the_one/mcp/transports/stdio.py`.
- Revert `MCPClient._transport_connect`'s consumption of those helpers in `the_one/mcp/client.py`.
- Revert the `the_one/mcp/README.md §3` scoping update.
- Keep the F2-known-issue line in `mission.md::Known Issues` with an updated diagnosis plan.
- F6 is NOT blocked by the revert; F6 lands the runtime; F2-known-issue stays open as separate carry-forward debt.

---

## Tier 2 — Binding (live Cloudflare API MCP, F6.5 close gate)

Manual operator verification against `https://mcp.cloudflare.com/mcp` via F6.5's Test connection button + F5's RFC 7591 DCR happy path. Binding go/no-go for F6.5 flight close per Design Decision §4 — flight cannot transition to `landed` without a PASS.

### Setup

1. Operator has a Cloudflare account (free-tier acceptable — sign up at <https://dash.cloudflare.com/sign-up> if needed).
2. `the-one` dev container is up at `http://localhost:8484` (verify: `docker compose ps`).
3. Operator's browser allows popups for `localhost:8484`.

### Procedure

1. **Register source**. In Studio, navigate to `#studio/mcp-sources/new`. Fill: name=`cloudflare_api`, type=`streamable-http`, url=`https://mcp.cloudflare.com/mcp`. Click Save. Verify: editor transitions to edit-mode and the Test connection section appears below the form.
2. **First Test click**. Click the Test connection button. Verify within 15 seconds: result panel shows "Opening consent popup..."; a popup opens at the Cloudflare consent URL; Test button is disabled while the popup is open.
3. **Cloudflare consent**. Complete Cloudflare login + authorize the-one in the popup. Verify: popup redirects to `http://127.0.0.1:8484/api/oauth/callback?code=...&state=...`; popup body renders "Login successful". Close the popup tab.
4. **Auto re-test**. Within ~500ms of popup close, the UI auto-runs the Test re-POST. Verify: result panel updates to "Connected. Tools (N): ..." with N > 0; the tool list includes Cloudflare-API tools (e.g. `accounts_list`, `zones_list` — exact list depends on Cloudflare's server scope at HAT time); Test button re-enabled.
5. **Agent build**. Navigate to `#studio/agents/new`. Create agent `hat_cloudflare_api`: pick any configured LLM provider; in MCPs tab, attach `cloudflare_api`; Save. Verify: agent build succeeds with no error toast and the agent appears in the grid.
6. **Chat tool call**. Open chat with `hat_cloudflare_api`. Send: *"List my Cloudflare accounts using your MCP tool."* Verify: agent dispatches a `mcp__cloudflare_api__*` tool (most likely `accounts_list`); tool result lands in chat as a non-empty list of accounts; no "Login required" button surfaces (tokens valid from Step 3-4).
7. **Cleanup**. Delete the test source and agent (run from host):
   ```bash
   curl -X DELETE http://localhost:8484/api/agents/hat_cloudflare_api
   curl -X DELETE http://localhost:8484/api/mcp-sources/<source_id>
   ```
   `<source_id>` is the id assigned at Step 1 (read from the Studio MCP Servers list URL or via `curl -s http://localhost:8484/api/mcp-sources | jq '.[] | select(.name=="cloudflare_api") | .id'`). Verify both DELETEs return 204 No Content.

### Caplog gate

After Step 7, check the dev container logs for `MCPClient.disconnect` warnings:
```bash
docker compose logs the-one --since 30m | grep -i "transport close failed\|disconnect" | wc -l
```

Expected: 0 occurrences. Carry-forward from F6 Tier-1 HAT — F4's worker-task-per-entry pattern + F5 L1's dispatcher-owned-stack mechanism work as designed against real subprocess teardown.

### Tier-2 outcome

**On PASS** — record date + caplog count in `flight-log.md` L4 entry; mark flight `landed`; tick mission.md flight 6.5 checkbox; mark PR ready-for-review.

**On FAIL** — record the specific failure mode + reproduction steps in `flight-log.md` Anomalies. The flight cannot transition to `landed` without addressing the failure (either a code fix landing as a fixup commit on this branch, or a follow-up flight). Per Design Decision §4 + flight Adaptation Criteria: if no DCR target reachable within 1 hour of L4 kickoff, abort flight.
