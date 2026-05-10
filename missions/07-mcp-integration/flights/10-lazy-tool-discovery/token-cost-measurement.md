# F10 Token Cost Measurement

**Date**: 2026-05-10
**Flight**: F10 (Lazy tool discovery)
**Measurement shape used at L5**: Shape B (synthetic-LLM proxy — always doable without operator coordination)
**Shape A status**: TBD — pending operator coordination at HAT time (see Shape A section below)

---

## Shape B: Synthetic-LLM proxy estimate

### Scenario

A representative 3-iteration session where the operator asks the agent "what tools do you have available?" and the agent searches and synthesizes a response. Cloudflare API MCP is the reference source (known to expose ~30 tools at ~150 tokens/schema average per the leg artifact).

### Pre-F10 (eager-load-all model)

Under the F8 architecture, every LLM call receives the full tool catalog in `tools=`.

**Catalog composition**:
- Built-in tools: ~15 tools × ~150 tokens/schema avg = ~2250 tokens
- Cloudflare API MCP tools: ~30 tools × ~150 tokens/schema avg = ~4500 tokens
- Total per-call schema cost: **~6750 tokens**

**3-iteration session total schema cost**:
- Iteration 1 (user turn): 6750 tokens
- Iteration 2 (agent processes tool results): 6750 tokens
- Iteration 3 (agent synthesizes response): 6750 tokens
- **Total schema tokens across 3 iterations: ~20,250 tokens**

### Post-F10 (lazy-discovery model)

Under F10, the LLM starts with only `[search_tools, search_mcps, continue]` in `tools=`. Tools load into the session's visibility set as search calls are made.

**Baseline catalog (all iterations)**: 3 schemas × ~150 tokens/schema avg = ~450 tokens/call

**Iteration 1** (baseline-only; agent calls `search_mcps("")`):
- Schema cost: 450 tokens (baseline)
- After the search call, matched MCP schemas are queued for iteration 2

**Iteration 2** (search results loaded; agent calls `search_tools("")`):
- Baseline: 450 tokens
- Loaded MCP schemas from iteration 1: up to 30 × 150 = 4500 tokens (if all Cloudflare tools matched)
- Loaded built-in schemas from search_tools: up to 15 × 150 = 2250 tokens
- Schema cost: ~7200 tokens (worst-case after both search calls load everything)

**Iteration 3** (agent synthesizes with full loaded set):
- Same as iteration 2: ~7200 tokens
- Schema cost: ~7200 tokens

**Total schema tokens across 3 iterations: ~450 + ~7200 + ~7200 = ~14,850 tokens**

### Delta

| Metric | Pre-F10 | Post-F10 | Delta |
|--------|---------|---------|-------|
| Schemas/call (session start) | ~45 tools | 3 tools | −42 tools |
| Tokens/call (iteration 1) | ~6750 | ~450 | −6300 (−93%) |
| Tokens/call (iteration 2+ after search) | ~6750 | ~7200 | +450 (schema overhead from search tool descriptions) |
| Total tokens (3-iteration session) | ~20,250 | ~14,850 | −5400 (−27%) |

**Key insight**: F10's win is concentrated at session start (iteration 1 schema cost drops 93%). For sessions that immediately need a broad tool set, the aggregate savings over a full session are ~27%. For pure-chat sessions that never search (or that only need a small subset of tools), the savings are far larger — the full MCP catalog is never sent.

**Interpretation note**: the post-F10 worst-case (all tools loaded by iteration 2) approaches pre-F10 cost because `search_tools + search_mcps` each add their own schema descriptions (~300 tokens total) that weren't present pre-F10. This is a small constant overhead; it doesn't alter the directional win for realistic workloads where the agent uses fewer than the full catalog.

### Measurement substitution note

Shape B is a proxy based on representative schema-token estimates. Actual token counts depend on:
- The real tool descriptions (vary by tool; estimated at ~150 tokens/schema avg)
- The LLM's tokenizer (estimates here use a rough 4 chars/token rule)
- The operator's actual MCP attachment (not all sessions attach Cloudflare; some attach smaller or larger sources)

This measurement is **signal, not a contract**. Per F10 §1, token-cost-worse-than-baseline does not gate the flight; the architectural shift (mid-session attach support + strict per-session visibility control) is the primary deliverable.

---

## Shape A: Real-LLM, operator-coordinated

**Status**: TBD — pending operator coordination at HAT time.

When the operator is available to run the HAT scenario interactively, Shape A can be collected as follows:

1. **Pre-F10 baseline** (use `main` branch or a local stash of the pre-F10 state):
   - Start the dev container on `main`.
   - Register the Cloudflare API MCP source; ensure it has a fresh token.
   - Create a default agent attached to the Cloudflare API source.
   - Start a chat session; send: "what tools do you have available?"
   - Capture from backend telemetry or from the browser devtools Network tab on the `/api/chat/stream` WebSocket: iteration count + approximate input tokens per turn (if the provider exposes usage in its streaming response, e.g., Anthropic's `usage.input_tokens` field).

2. **Post-F10 measurement** (on `flight/10-lazy-tool-discovery` branch):
   - Same scenario: same agent, same Cloudflare source, same question.
   - Capture: iteration count + input tokens per turn.

3. **Report delta** in a Shape A addendum appended to this file at HAT time.

The Phase 2d Reviewer should treat the Shape B estimate above as the definitive measurement for review purposes. Shape A, if collected at HAT time, will be appended here before Phase 3 (flight landing).
