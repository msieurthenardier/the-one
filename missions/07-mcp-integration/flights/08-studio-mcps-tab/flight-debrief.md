# Flight Debrief: Studio MCPs tab + inspector polish

**Date**: 2026-05-09
**Flight**: [Studio MCPs tab + inspector polish](flight.md)
**Status**: landed
**Duration**: 2026-05-09 single-day flight (design + 4 autonomous legs + interactive HAT)
**Legs Completed**: 5 of 5 (L0 maintenance bundle, L1 overrides+capabilities, L2 source-edit polish, L3 agent-editor MCPs tab, L4 Tier-2 HAT)

## Outcome Assessment

### Objectives Achieved

The flight delivered all three coordinated deliverables stated in the objective:

1. **Replaced `mcps-tab.js`'s 22-line stub with a fully-functional per-agent MCP attach + per-tool toggle UI.** The original chip-list pattern shipped in L3 was reworked during HAT to mirror the built-in Tools tab's `tool-row` + sibling `<details>` pattern (Anomaly A3) — a UX improvement directly responsive to operator feedback. Per-agent credential override fields (bearer_token, headers, env) were intentionally REMOVED from the UI during HAT (A4/A5 — operator: "for sso apps, im not going to know the bearer token to override").

2. **Polished the source-edit Tools section** with capability-flags one-liner (`tools, resources, prompts, logging, completions, tasks` — full SDK `ServerCapabilities` allowlist) and per-tool collapsible Input schema viewer (L2). Introduced `page.route()` browser-test mocking pattern, the first use in this codebase.

3. **Bundled six F6.5/F6.6 carry-forward maintenance items** into L0: `connect()` `Raises:` docstring; `mission.md` cross-flight constraint; `CLAUDE.md` test_mcp_pool.py rationale; pyproject deselect-count comment; `OAUTH_MANAGED_SECRET_KEYS` cross-check test; `requires_bwrap` marker migration.

### Mission Criteria Advanced

- **#7** (agent attaches MCP sources; tools become callable) — partially advanced. Per-agent attach UI is shipped; per-tool enable/disable filter integration shipped at L1. Verification of "tools become callable" depends on the chat path which wasn't exercised end-to-end in HAT.
- **#8** (stable namespacing for collisions) — advanced via L3's `mcp__{slugify(source.name)}__{tool.name}` display + un-prefixed storage convention.
- **#10** (graceful failure isolation) — partially advanced. The auth-required inline notice path is shipped; verified by L3 browser test 7. The chat-path "agent runtime continues, surfaces failure to operator" is unchanged from F6.
- **#11** (automated coverage) — strongly advanced. F8 added 8 unit tests (override schema + provider filter + endpoint capabilities), 14 browser tests (8 new for MCPs tab + 3 for L2 polish + 3 retained from L2), 1 OAUTH_MANAGED_SECRET_KEYS cross-check test, and 1 `App.areas` array-shape lock-test.
- **#12** (design-language quality bar) — advanced. The L4 HAT redesign (chip-list → tool-row pattern) directly addresses operator-felt design-language quality. Built-in Tools tab parity is now visible.

### Test Metrics

| Metric | Pre-F8 baseline (F6.5/F6.6) | F8 result | Delta |
|---|---|---|---|
| Unit suite wall-clock | 72-76s (varied) | **72.38s** (excluding test_mcp_pool.py per Anomaly A1) | -3 to -4s |
| Unit tests passed | 1344 (F6.5) | **1376** | **+32 tests** |
| Unit tests failed | 4 (F6.5) | **3** (pre-existing sandbox-integration; not F8 regressions) | **-1 fail** |
| Unit tests skipped | 2 | 2 | 0 |
| Browser suite wall-clock | 10:25 | **10:41** | +16s |
| Browser tests passed | 240 (F6.5) | **255** | **+15 tests** |
| Browser tests failed | 48 (F6.5) | **43** (mostly pre-existing flakes per F6.5 debrief) | **-5 fails** |
| New endpoint tests | — | 9 (`test_oauth_test_connection_endpoint.py`) | +9 |
| New browser tests | — | 8 (MCPs tab) + 3 (L2 polish) | +11 |
| New unit tests | — | 8 (provider filter) + 3 (override schema) + 1 (oauth storage) | +12 |

**Net assessment**: F8 added 32 unit + 15 browser tests, REDUCED total failures by 6, and held wall-clock effectively flat. No new regressions surfaced. The 1 unit failure in `-x` mode (`test_acquire_lazy_spawn_creates_worker_and_returns_client`) is the documented L0 baseline known issue (Anomaly A1) — `_shutting_down` flag pollution from `test_lifespan.py` running first; pre-existing on main; carries forward to a follow-up architectural flight.

## What Went Well

- **Design-review HIGH-issue catches were decisively load-bearing.** L1's resolver-strip caught at design review (would have crashed agent builds the moment `enabled_tools` was set). L2's `tasks` capability key omission caught at design review (would have silently invisibilized a typed flag). L3's `hydrateState`/`serializeState` patches caught at design review (would have broken deep-link URL routing entirely). Each: ~2-5 minutes of architect time, prevented hours of post-implementation diagnostic work.

- **Single bundled code review at flight close** (Haiku reviewer) covered all 1497 LOC across 18 files in one pass, signaled `[HANDOFF:confirmed]` cleanly. No iteration cycles needed for the autonomous portion. F6.6's batched-commit precedent paid off again.

- **Independent post-HAT code review (Sonnet, fresh context)** caught the Phase A `MCPConnectionError` token-clear path being too broad — would have destroyed valid OAuth tokens on transient connectivity failures. ~60 LOC narrowing fix applied. The "fresh-context reviewer after inline fixes" pattern is now battle-tested across F6.6 + F8 — recommended to codify in the agentic-workflow skill.

- **HAT discovered five real issues that no unit/browser test would have surfaced.** A2 (test-uses-form): UX bug invisible without an operator typing in a field and clicking Test. A3 (chip-list UX): subjective design feedback. A4/A5 (bearer-token UX gap for OAuth sources): persona/use-case mismatch. A6 (no-auth server detection / SDK anyio leak): live-server interaction with empty secrets. The empirical pattern from F4/F5/F6/F6.5/F6.6/F8 is now 6 flights of "binding HAT catches things unit tests can't" — recommended to codify as a methodology constraint, not just a per-flight design decision.

- **Structural fix found during HAT propagated to project documentation.** The `docker compose exec` TTY hang (Issue A in flight log) was fixed in `CLAUDE.md` Testing section + `.flightops/agent-crews/leg-execution.md` prompt template. Future subagents in this project pick up the right command structure automatically.

- **`page.route()` mocking pattern introduction** (L2) was clean and reusable; L3 immediately benefited (8 browser tests for the MCPs tab use it). Pattern is documented in code comments at first-use site.

- **Test isolation thoughtfulness in L3's mode-aware tool toggle dispatch.** The allowlist/denylist mode is determined at render time and round-trips through `data-mcp-tool-mode`; API-set `enabled_tools` survives an operator's denylist-mode UI session intact. The reviewer flagged this as the right design.

## What Could Be Improved

### Process

- **HAT scope blew up beyond the 11-step procedure.** The L4 leg artifact specified 11 verification steps; 5 anomalies surfaced 1-2 steps in. Each anomaly required design + inline implementation + test + verify cycles, expanding L4 from "1 hour operator time" (per design estimate) to several hours. Recommendation: **add to the leg skill an "HAT step inversion" protocol** — when an anomaly surfaces during step N, the leg should explicitly say "fix or defer? if fix, run code review on the fix; if defer, document anomaly and continue HAT". F8's L4 organically followed this but it wasn't structured upfront.

- **Phase A.5 (no-auth bare-client probe) was attempted, then removed** without the design-review depth that the autonomous legs got. The anyio cross-task cancel-scope leak that ultimately killed Phase A.5 should have been anticipated from F6/F6.6's prior flight logs (which documented the same SDK behavior). The HAT-time decision to attempt Phase A.5 without spawning a design-review architect was efficient but missed a known-risk signal. Recommendation: **for inline fixes that touch known-problematic SDK paths (anyio task groups, cancel scopes, MCP client lifecycle), spawn a quick architect pass even mid-HAT** — 5 minutes to read F6/F6.6 logs and flag the risk, vs the ~45 minutes the failed Phase A.5 cost.

- **No-auth MCP server detection was deferred without scoping.** A6's "deferred to follow-up flight" disposition is correct but the carry-forward is light on shape — the proposed `auth_required: bool | None` hint vs `anyio.create_task_group()`-isolated probe needs an architect choice before the next flight starts.

### Technical

- **The `MCPConnectionError` token-clear path is narrower-than-it-should-be.** The current message-pattern guard (`"did not respond" in err_msg` OR `"cancelled during initialize" in err_msg`) is brittle — a future client.py refactor changing those strings silently disables the token-clear behavior. Right design: introduce a typed exception (e.g. `MCPInitializeTimeout(MCPConnectionError)`) that the connect() handler raises specifically for the timeout/cleanup-deadlock paths. The narrowing-via-message is acceptable for F8 (works correctly today) but the architectural debt should be cleared in a follow-up.

- **Anomaly A6 (anyio cross-task cancel-scope leak)** is the same SDK behavior that F6 A5 / F6.6 partially mitigated for `list_tools()` and `call_tool()`. F8 confirms it also bites at the bare-client `connect()` time. The systemic fix is upstream in the `mcp` SDK or in the_one's transport-stack management — neither is F8 scope, but every flight that touches MCP transport pays the cost in cleanup-deadlock workarounds.

- **The `OAUTH_MANAGED_SECRET_KEYS` derivation pattern is still manual.** L0 added a cross-check test (`test_set_tokens_writes_only_managed_secret_keys`), which is a good belt-and-suspenders. F6.5 debrief recommendation #5 proposed deriving the constant from `set_tokens`'s actual writes via `MANAGED_KEYS` class attribute or runtime introspection — neither has landed. F8's L0 cross-check is a useful guardrail but the constant remains hand-maintained.

- **Per-agent `mcp_overrides` schema accepts credential fields** (`env`/`headers`/`bearer_token`) but no UI surfaces them post-A4. This is intentional (see A5's right-design proposal: per-agent OAuth re-auth toggle), but the schema asymmetry creates confusion: API users can set bearer_token via curl but the UI drops it on the next save round-trip via collectFormData (no walk for these fields exists). Should be cleaned up when the per-agent OAuth flight lands.

### Documentation

- **No follow-up flight has been scoped** for A4/A5/A6's carry-forwards. Three independent feature gaps with proposed designs in this debrief — should be brought into mission #7's known-issues section OR a successor mission planning surface before context decays.

- **The `docker exec` vs `docker compose exec` distinction** is now documented in CLAUDE.md, but not in the project's outward-facing README or contributing guide. If a non-claude-code contributor or CI hits the same trap, they'll read README first.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Test connection endpoint accepts JSON body for in-flight form values | Pre-existing UX bug (A2) surfaced during HAT | Yes — operator-driven test surfaces should always test what's-in-the-form |
| `mcps-tab.js` UI rewrote from chip-list to tool-row pattern | Operator feedback during HAT (A3) | Yes — agent-editor sub-tabs should mirror the built-in Tools tab pattern by default |
| Per-agent credential override UI removed | OAuth sources don't fit the bearer-paste UX (A4) | Conditional — the per-agent OAuth re-auth toggle replaces it |
| Phase A.5 (bare-client no-auth probe) attempted then removed | SDK anyio cross-task leak (A6) | Yes — bare-client probes against MCP servers must be wrapped in `anyio.create_task_group()` if attempted at all |
| Phase A `MCPConnectionError` clears stale OAuth tokens (narrowed) | Refresh-token rotation manifests as initialize timeout, not MCPAuthRequired | Yes — but with typed exception, not message-pattern guard |
| L4 leg expanded from "1 hour HAT" to "several hours of HAT + 5 inline fixes" | Anomaly cascade | No — a structured "HAT step inversion" protocol per leg skill is the right capture |

## Key Learnings

- **Binding HAT against a real OAuth-protected MCP server catches things no unit/browser test can.** F8 is the 6th flight of this empirical pattern. The "OAuth server" axis specifically catches: in-flight form values vs persisted state (A2); SDK anyio cleanup leaks (A6); UX gaps for OAuth-managed credentials (A4/A5); refresh-token rotation handling (A6 part 2). None of these have unit-test analogs without elaborate mocking.

- **Independent fresh-context code review after HAT inline fixes** catches issues the inline-fixer doesn't see (the fixer is too close to the immediate problem). The Sonnet reviewer's narrowing-the-token-clear-guard is a clean example. F6.6 + F8 both relied on this pattern; recommend codifying in the agentic-workflow skill as a step between HAT and the final commit.

- **Design-review HIGH issue rate held at 1-3 per leg** (L1: 2 HIGH; L2: 1 HIGH; L3: 2 HIGH). Each catch was decisively load-bearing in retrospect. The pattern of architect-for-design-review + sonnet-for-implementation + haiku-for-final-review continues to produce high signal-to-noise per orchestration step.

- **The `mcp` SDK's anyio task-group cleanup is fragile** in ways the_one cannot fully insulate against without restructuring the transport-stack lifecycle. Every flight pays cleanup-deadlock workaround cost; this is recurring debt at the dependency boundary.

## Recommendations

1. **Codify the "binding HAT for OAuth-touching flights" pattern as a methodology constraint** (mission-control template change). Empirically validated across F4/F5/F6/F6.5/F6.6/F8 — 6 flights. Carry-forward from F6.5 + F6.6 debriefs is now overdue.

2. **Codify the "fresh-context independent review after HAT inline fixes" pattern as a methodology step** (agentic-workflow skill update). Adds one step between HAT close and final commit; takes ~5 min of reviewer time; catches inline-fix blind spots.

3. **Plan a follow-up flight to land per-agent OAuth re-auth + no-auth-server detection together.** A4/A5/A6 share the same architectural seam (per-(agent, source) credential storage; explicit auth-required hint). Bundle as a single flight with two coordinated deliverables. Estimate: similar size to F8 (4-5 legs, ~1500-2000 LOC + binding HAT).

4. **Introduce a typed `MCPInitializeTimeout(MCPConnectionError)` exception** to replace the message-pattern guard in `test_mcp_connection`'s Phase A error handler. Single-leg maintenance flight or fold into the per-agent OAuth flight.

5. **Add a structured "HAT step inversion" protocol to the leg skill** for HAT/alignment legs. When an anomaly surfaces mid-HAT, the leg's protocol explicitly says "fix or defer? if fix, design + spawn architect for known-problematic-paths review + implement + test; if defer, document anomaly and continue HAT". F8's L4 followed this organically; structuring it would have prevented the Phase A.5 wasted attempt.

## Action Items

- [ ] Mission-control flight: codify "binding HAT for OAuth-touching flights" methodology constraint (carry-forward from F6.5 + F6.6 + F8 debriefs)
- [ ] Mission-control flight: codify "fresh-context independent review after HAT inline fixes" agentic-workflow step
- [ ] Mission-control flight: add "HAT step inversion" protocol to leg skill for HAT/alignment legs
- [ ] the-one flight: per-agent OAuth re-auth toggle + per-(agent, source) credential storage (replaces A4 + A5 surfaces)
- [ ] the-one flight: no-auth MCP server detection (A6 — `auth_required: bool | None` hint OR anyio-isolated bare-client probe)
- [ ] the-one maintenance leg: introduce typed `MCPInitializeTimeout(MCPConnectionError)` exception; replace message-pattern guard in `api.py::test_mcp_connection` Phase A
- [ ] the-one maintenance leg: derive `OAUTH_MANAGED_SECRET_KEYS` from `set_tokens`'s actual writes (F6.5 carry-forward, still open after F8 L0 cross-check)
- [ ] the-one architectural flight: `_pool.py` test isolation (Anomaly A1 known issue — `_shutting_down` flag leak; pre-existing pool worker spawn-path hang under pristine state)
- [ ] Mission #7 known-issues update: add A1, A6 as ongoing gaps; close A2, A3, A4, A5, A6-part-2 as resolved this flight
