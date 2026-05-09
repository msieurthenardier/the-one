# Leg: 06-hat-real-mcp-lifecycle

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## HAT Outcome (2026-05-07)

**Overall: PASS with documented findings.** 4 of 5 required steps PASSED end-to-end against real bwrap-spawned `mcp-server-fetch`. Step 5 PARTIAL — automated coverage from L4 tests #8 + #9 exists; end-to-end live-lifespan-kills-bwrap deferred to F6 HAT (chicken-and-egg: pool only populated via F6 wiring). Bonus per-(agent, source) keying step PASSED. Three findings recorded for debrief; all functional behaviors correct.

### Per-step results

| Step | Result | Notes |
|------|--------|-------|
| 1 — Pre-state | ✅ PASS | After installing `procps` (playwright image lacks pgrep). Pre-state clean. |
| 2 — Lazy spawn | ✅ PASS | `is_alive=True`, `tool_count=1`, `tool='fetch'`. PID count = 4 (bwrap subtree + script's own PID), not 1 — leg's expected "1 PID" was naive; actual invariant is ≥1 subtree. |
| 3 — Warm reuse | ✅ PASS | 5 acquires, all `same_client=True`, same PIDs unchanged, `last_activity` advances. |
| 4 — Idle reap + transparent respawn | ✅ PASS | Forced age via `c._last_activity = 0.0` + `_reap_once()`. Pool drained → 0; re-acquire returned a fresh client (`c1 is c2 → False`); fresh PIDs differ from pre-reap. |
| 5 — Lifespan drain | ⚠️ PARTIAL | Automated coverage from L4 test #8 (lifespan ordering spy — PASSED) + #9 (drain-timeout — 10.01s, PASSED). End-to-end "live FastAPI shutdown reaps real bwrap" requires F6 wiring (pool only populated via F6's `MCPToolProvider`); deferred to F6 HAT. |
| Bonus — per-(agent, source) keying | ✅ PASS | `agent-a` ≠ `agent-b` client; pool size = 2; keys = `[('agent-a', 'hat-fetch'), ('agent-b', 'hat-fetch')]`. |

### Findings (for debrief)

1. **F2 known-issue ("MCPClient.disconnect teardown noise") NOT transitively fixed by L1a.** `RuntimeError: generator didn't stop` still emits via the cross-task safety net swallow on EVERY disconnect — including under explicit `shutdown_drain()`, not just `asyncio.run()` shutdown. L1a's runtime deviation (transport modules kept as `@asynccontextmanager`) means the dispatcher's nested `async with` still has the generator-protocol incompatibility. Safety net catches; functional behavior correct (no orphan subprocesses from this root cause). **Action**: add to mission Known Issues.

2. **7 defunct `[bwrap] <defunct>` zombie processes in dev container** (from 17h ago, May06 — predates this HAT). Process-reaping gap somewhere in the SDK's `anyio.open_process` path: when bwrap exits, the parent doesn't `wait()` on it, leaving a zombie. Not a leak (zombies hold no resources beyond PID + struct task), but indicates a gap. **Action**: investigate at flight debrief; likely needs SDK-level workaround or upstream fix.

3. **HAT prerequisite gap: `procps` not installed in dev container's playwright base image.** All HAT steps depend on `pgrep`. **Action**: add `procps` to Dockerfile OR document as a HAT-setup step.

### What this HAT validated

- Worker-task-per-entry pattern works against real third-party MCP server (mcp-server-fetch).
- bwrap sandbox spawn + `mcp-server-fetch` python module + JSON-RPC handshake all compose correctly.
- Idle-TTL reaper actually reaps live processes (not just mock clients).
- Transparent respawn produces a fresh subprocess tree (PIDs differ).
- Per-`(agent, source)` keying produces independent processes for different agents.

### What this HAT did NOT validate (deferred to F6 HAT)

- End-to-end "operator triggers MCP via UI → pool acquires → tool call works → graceful shutdown reaps".
- Real attached-MCP usage in the agent loop (F6 territory).

## Objective

5-step interactive verification of the F4 pool lifecycle against a real third-party MCP server (`mcp-server-fetch`). Confirms — empirically, against a non-fixture server — that the worker-task-per-entry pattern actually works end-to-end: lazy spawn on first call, warm reuse on subsequent calls, idle reap after configurable TTL, transparent respawn after reap, lifespan drain on graceful shutdown. Plus one bonus step that locks per-`(agent, source)` keying with two different agents.

## Why this is a HAT, not autonomous

F4's lifecycle behavior — process spawning, idle reaping, lifespan drain — is hard to prove via unit tests alone. The L3/L4 unit tests use mock `MCPClient`; the integration tests use the in-repo `hello_server` fixture. Neither exercises a real third-party MCP's wire protocol or process model. The HAT closes that gap.

Per agentic-workflow methodology: HATs are guided one step at a time. The Flight Director (orchestrator) presents each step; the human performs it inside the dev container and reports results; the orchestrator confirms or fixes, then advances.

## Pre-state

- Flight 04 commit `b5a1e23` is on branch `flight/04-idle-ttl-lifecycle` (PR #31 open as draft).
- Working tree clean.
- Dev container is up and running (`docker compose ps the-one` shows `running`).
- `bubblewrap` is installed in the dev container.
- Cumulative test surface: 148 collected (147 passed + 1 skipped).

## Verification Steps

Each step has: a command for the human to run, expected output, a pass-criterion, and what the orchestrator does on failure.

### Step 1 — Pre-state (no warm processes; install mcp-server-fetch)

```bash
docker compose exec the-one pip install mcp-server-fetch
docker compose exec the-one bash -c 'pgrep -f mcp_server_fetch || echo "no warm processes — OK"'
```

**Pass**: `pgrep` returns no PIDs (the `|| echo` fires).
**Fail**: existing `mcp_server_fetch` PIDs are listed → kill them and re-check.

### Step 2 — Lazy spawn

Configure an MCP source via Studio UI or directly via API, then trigger an acquire.

```bash
docker compose exec the-one python -c "
import asyncio, os
from the_one.db.models import MCPSource
from the_one.mcp import _pool

async def main():
    source = MCPSource(
        id='hat-fetch', name='hat-fetch', type='stdio',
        config={
            'command': 'python',
            'args': ['-m', 'mcp_server_fetch'],
            'env': {},
            'cwd': None,
            'sandbox': {'writable_paths': [], 'network_allowed': True},
        },
        secrets={},
    )
    # Patch _load_source to short-circuit DB.
    _pool._load_source = lambda sid: asyncio.sleep(0, result=source)
    client = await _pool.acquire('hat-agent', source.id)
    print(f'is_alive: {client.is_alive}')
    print(f'tools: {[t.name for t in await client.list_tools()][:3]}')

asyncio.run(main())
"
docker compose exec the-one bash -c 'pgrep -f mcp_server_fetch | wc -l'
```

**Pass**: `is_alive: True`, `tools: [...]` (any non-empty list), and `pgrep | wc -l` returns `1`.
**Fail**: `is_alive: False` OR no tools OR no PID → diagnose connect path; the `connect_stdio` errlog should surface a clear `MCPSandboxError` if the bwrap wrap is misconfigured.

### Step 3 — Warm reuse

```bash
docker compose exec the-one python -c "
# ... same setup ...
async def main():
    # First acquire
    c1 = await _pool.acquire('hat-agent', 'hat-fetch')
    pid_before = c1._session._read_stream._fd if hasattr(c1._session, '_read_stream') else None
    # Five more acquires
    for _ in range(5):
        c = await _pool.acquire('hat-agent', 'hat-fetch')
        assert c is c1, 'warm reuse broken — got different client instance'
    print('warm reuse OK — same client instance for 6 acquires')

asyncio.run(main())
"
docker compose exec the-one bash -c 'pgrep -f mcp_server_fetch | wc -l'
```

**Pass**: print confirms warm reuse; PID count is still `1`.
**Fail**: assertion fires → `acquire`'s entry-existence check is broken, OR the client was disconnected mid-test.

### Step 4 — Idle reap + transparent respawn

```bash
docker compose exec the-one bash -c 'export MCP_POOL_IDLE_TTL_SECONDS=3 && python -c "
import asyncio
from the_one.mcp import _pool
# Re-trigger acquire to age it
async def main():
    c1 = await _pool.acquire(\"hat-agent\", \"hat-fetch\")
    pid1 = next(iter(p for p in []), None)  # placeholder
    print(f\"pre-reap is_alive: {c1.is_alive}\")
    # Wait for idle TTL + reaper interval
    await asyncio.sleep(35)
    # Verify reaped
    print(f\"post-reap pool size: {len(_pool._pool)}\")
    # Re-acquire — should respawn fresh
    c2 = await _pool.acquire(\"hat-agent\", \"hat-fetch\")
    print(f\"respawn is_alive: {c2.is_alive}\")
    print(f\"different client: {c1 is not c2}\")
asyncio.run(main())
"'
```

**Pass**: `pre-reap is_alive: True`; `post-reap pool size: 0`; `respawn is_alive: True`; `different client: True`. PID has changed (use `pgrep -f mcp_server_fetch` before and after — different PIDs).
**Fail**: pool size still has the entry post-reap → reaper not running, OR `_REAPER_INTERVAL_SECONDS` not honored.

### Step 5 — Lifespan drain

```bash
# Get a warm pool entry first (run step 2 again if needed).
docker compose exec the-one bash -c 'pgrep -f mcp_server_fetch | head -3'
# Then trigger a graceful shutdown.
docker compose down the-one
sleep 5
# From the host (outside dev container), check no orphan bwrap processes.
pgrep -af mcp_server_fetch
```

**Pass**: `pgrep -af mcp_server_fetch` from the host returns NOTHING — no orphans.
**Fail**: orphan processes remain → lifespan drain not triggered, OR `_evict`'s 10s timeout exceeded for a stuck worker. (If timeout exceeded, the SIGTERM cascade should still clean up via `--die-with-parent`.)

### Bonus — Per-(agent, source) keying

```bash
docker compose exec the-one python -c "
# Two different agents acquire the SAME source.
import asyncio
from the_one.mcp import _pool
async def main():
    c_a = await _pool.acquire('agent-a', 'hat-fetch')
    c_b = await _pool.acquire('agent-b', 'hat-fetch')
    assert c_a is not c_b, 'per-(agent, source) keying broken — same client for different agents'
    print('per-(agent, source) keying OK — different clients per agent')

asyncio.run(main())
"
docker compose exec the-one bash -c 'pgrep -f mcp_server_fetch | wc -l'
```

**Pass**: print confirms keying; PID count is `2` (one per agent).
**Fail**: same client returned for both agents → keying invariant broken.

## Acceptance Criteria

- [ ] Step 1 passes (clean pre-state)
- [ ] Step 2 passes (lazy spawn — 1 PID after first acquire)
- [ ] Step 3 passes (warm reuse — 1 PID after 6 acquires)
- [ ] Step 4 passes (idle reap → 0 entries → transparent respawn with new PID)
- [ ] Step 5 passes (lifespan drain — no orphans)
- [ ] Bonus passes (per-(agent, source) → 2 PIDs for 2 agents)

If any required step fails, file a flight-log Anomaly and remediate before flight close.

## Files Affected

This is a verification leg — no source/test changes. Only:
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append HAT outcome
- `flight.md` — flip C6 checkpoint to `[x]` if all steps pass

---

## Post-Completion Checklist

- [ ] All 5 required steps + 1 bonus passed
- [ ] Flight-log HAT-outcome entry appended
- [ ] C6 checkpoint flipped to `[x]` in flight.md
- [ ] Leg status: `completed` (NOT `landed` — flight is already committed; a HAT-only commit follows)
- [ ] If any step failed: file Anomaly in flight log + escalate
- [ ] Final commit: `flight/04: HAT verification (L6) — 5-step real-MCP lifecycle PASSED` (or whatever the actual outcome is)
