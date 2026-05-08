# HAT — F6 Per-agent MCP attach + tool-routing

**Type**: Human Acceptance Test. The operator runs each step, observes the result, and reports the outcome. There is no automated assertion — the human's judgment is the gate.

**Scope**: Two tiers.

- **Tier 1** (required, per F6 flight §7): in-repo dev-container procedure against `mcp-server-fetch`. The binary go/no-go for retiring the F2-known-issue (`MCPClient transport close failed` warning) from `missions/07-mcp-integration/mission.md::Known Issues`.
- **Tier 2** (optional, quarterly): live-GitHub-MCP procedure against the F5 manual-entry OAuth path. Verifies F5 + F6 wiring against a production-grade server. Not blocking; not part of any merge gate.

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
    schemas = agent.tools.all_schemas()
    print(f"Total tools: {len(schemas)}")
    mcp_tools = [s for s in schemas if s["name"].startswith("mcp__")]
    print(f"MCP tools: {[s['name'] for s in mcp_tools]}")

asyncio.run(main())
PY
```

**Verify**: at least one MCP tool listed under `mcp__fetch_local__*`. `mcp-server-fetch` exposes a `fetch` tool; expect `mcp__fetch_local__fetch`. The full prefix MUST be `mcp__fetch_local__`.

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

## Tier 2 — Optional (live GitHub MCP, quarterly)

Manual operator verification against `https://api.githubcopilot.com/mcp/` via F5's manual-entry OAuth path. Documents that F5 + F6 work together against a production server. Not blocking; not part of CI.

### Setup

1. Register an OAuth app at <https://github.com/settings/developers> → "OAuth Apps" → "New OAuth App". Set the callback URL to `http://127.0.0.1:8484/api/oauth/callback`.
2. Copy the `client_id` (and `client_secret` if confidential).
3. Confirm `the-one` is up at `http://localhost:8484`.

### Procedure

1. Register a streamable-http MCP source pointing at `https://api.githubcopilot.com/mcp/` (no OAuth fields populated — manual-entry path).
2. Configure an agent with `mcp_source_ids` including the GitHub source.
3. Open the chat UI for that agent. Send: *"List my five most recently updated repositories."*
4. The agent dispatches the GitHub tool call; the chat surfaces a Login-required button (lazy 401 path per F5 §1).
5. Click Login-required → modal opens with a manual-entry form (per F5 §2 — GitHub doesn't advertise a DCR endpoint).
6. Paste `client_id` + `auth_endpoint = https://github.com/login/oauth/authorize` + `token_endpoint = https://github.com/login/oauth/access_token` into the manual-entry form. Submit.
7. The modal opens GitHub's consent page in a new tab. Consent.
8. The loopback redirect resolves at `/api/oauth/callback`. Modal closes; agent loop resumes the original tool call (per F5 L3 pause/resume).
9. Verify: the agent returns the repo list.

### Bonus — revoke + re-auth

10. At <https://github.com/settings/applications>, revoke the OAuth app's grant.
11. Trigger another tool call from the agent. The next 401 should surface a fresh Login-required button. Re-consent. Verify the new token roundtrips.

### Tier-2 outcome

There is no binary gate for Tier 2 — it's a live integration smoke test. If anything fails, file a follow-up flight with the specific failure mode + reproduction steps. Pass is informational; does not gate F2-known-issue retirement.
