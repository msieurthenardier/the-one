# Flight: Lazy tool discovery — search-tools / search-mcps as the only catalog entries

**Status**: landed
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] **#7** — Agent attaches MCP sources; tools become callable. F10 changes WHEN tools become callable: not at session-build time, but at search-time within a session. The criterion's phrasing ("the attached MCP servers' tools become callable by the agent during a session") still holds — F10 is consistent with the criterion, just shifts the mechanism.
- [ ] **#10** — Graceful failure isolation. F10 must handle search misses, empty MCP source lists, MCP sources without cached tools, and per-agent denylists without surfacing user-facing errors.
- [ ] **#11** — Automated coverage. F10 ships unit + integration + browser coverage for the new agent-loop pattern, the two new built-in tools, and the success scenario the operator stated.
- [ ] **#12** — Studio MCP / Tools / Agents UI design-language quality bar. **F10 explicitly defers** Studio UI relabeling ("Allowed tools" / "Allowed MCPs") and a chat-time loaded-set indicator; both flagged for a successor flight. F10 keeps Studio UI semantics unchanged so #12 status doesn't regress.

---

## Pre-Flight

### Objective

Replace the agent's eager-load-all-tools catalog model with a 2-tool baseline (`search_tools` + `search_mcps`) plus per-iteration dynamic loading. By flight close, every new chat session begins with the agent seeing only `search_tools`, `search_mcps`, and the existing `continue` signal — and the agent must call search at least once before any built-in tool or MCP tool becomes callable. Search results auto-load matched tools' schemas into the agent's per-session loaded set; the loaded set persists across user turns within the session and is cleared on session end. The success criterion is operator-felt: ask "what tools do you have available?" → agent searches and lists; operator attaches a new MCP via Studio mid-session OR creates a new session after attaching → agent's next search reflects the new state. Token-cost reduction (the secondary motivation) is measured but not gated on a target number — the architectural shift is the primary deliverable.

### Open Questions

- [x] Search returns matches + auto-loads, OR returns matches + agent calls a separate `load_*` step? → **Auto-load** (search = discover + load in one step). See Design Decision §1.
- [x] Always-loaded "core" of common tools (e.g. `read_file`, web fetch) outside the strict 2-tool baseline? → **No**. Strict 2-tool baseline. See Design Decision §2.
- [x] Loaded-set persistence semantics? → **Per-session, no expiry, cleared on session end**. New chat sessions start blind. See Design Decision §3.
- [x] Search ranking algorithm? → **Substring match on name + description, case-insensitive, MVP**. No embeddings, no scoring; results returned in catalog order. See Design Decision §4.
- [x] MCP source-level description for `search_mcps` results when the source has no operator-authored description? → **Synthetic description from concatenated tool short-names** (e.g. `"cloudflare_api: list_zones, get_zone, list_dns_records, ..."`). See Design Decision §5.
- [x] System prompt update: extend `BASE_PROMPT` in `agent/config.py`, or smuggle through tool descriptions? → **Extend `BASE_PROMPT`**. See Design Decision §6.
- [x] Mission constraint amendment for the agent-loop semantic change? → **Yes — explicit amendment** in `mission.md` Constraints, landed at L5 alongside the regression sweep. See Design Decision §7.
- [x] Studio UI relabel ("Allowed tools" / "Allowed MCPs") + chat-time loaded indicator? → **Defer to follow-up flight**. F10 keeps Studio UI semantics unchanged. See Design Decision §8.
- [x] Auto-load matching schemas in the SAME LLM iteration that the search returned, or only on the next iteration? → **Next iteration only**. Schemas computed once per iteration; the model's tool-call response that triggered the search has already committed to its `tools=` array. The auto-loaded schemas land on the next request. See Design Decision §9.
- [x] F9's remaining legs (L5/L6/L7/L8) — pause and resume after F10, or absorb? → **Pause F9; resume-or-absorb decision at F10 close**. See Design Decision §10.

### Design Decisions

**§1. Search auto-loads matched schemas (no separate `load_*` step)** — calling `search_tools(query)` or `search_mcps(query)` returns a structured result AND mutates the agent's loaded-schema set. Matched schemas appear in the next iteration's `tools=` array. Two-step protocols (search-then-load) add an LLM hop without giving the agent meaningful new control — the agent already chose to search; auto-load preserves intent.

- Rationale: matches the operator's stated success criterion ("ask about tools → see list" — implicit auto-list). One-tool-call-per-discovery is the minimum. Avoiding the `load_*` step also keeps the catalog at exactly 2 (plus `continue`), simplifying the system prompt teaching surface.
- Trade-off: the agent has no "preview before load" hook. In practice, irrelevant matches just sit in the loaded set unused; the cost is token bloat per iteration, not correctness. Future tuning (e.g., loaded-set eviction policy) can land in a follow-up flight if measurement shows persistent bloat.

**§2. Strict 2-tool baseline — no always-loaded core** — pure-chat queries don't load any tool. The catalog at session start is exactly `[search_tools, search_mcps, continue]`. No `read_file`, no web fetch, no shell — operators ask the agent to "search for read_file" if they need it, and the agent does.

- Rationale: clean architectural line. An always-loaded core blurs the discovery contract ("which things are loaded? which need search?") and re-introduces the per-call token cost the design was meant to amortize. The minor latency cost of one search call for the first-time-using-a-common-tool case is acceptable given the lazy-discovery wins.
- Trade-off: first-tool-using turn is always 2-3 LLM iterations instead of 1. For pure-chat the cost is zero.

**§3. Per-session loaded set, no expiry, cleared on session end. Loaded set = MODEL-VISIBILITY FILTER, not registry membership.** — `Agent._loaded_schemas` lives on the Agent instance. New session = new Agent instance via `AgentFactory._build` = empty loaded set = blind start. Within a session, loaded tools stay loaded across user turns until the Agent instance is disposed (typically when the chat session ends).

**Critical clarification**: the agent's `ToolRegistry` (`self.tools`) holds the FULL candidate set — every built-in tool the operator's `enabled_tools`/`disabled_tools` allows, plus every MCP tool from every attached source. Dispatch via `self.tools.get(name)` in `_execute_tool` (`agent/core.py:255`) always finds the tool, regardless of loaded-set state. The loaded set is purely a model-visibility filter: it controls what schemas appear in the LLM's `tools=` array per iteration. This means:
- F5's deferred-then-resumed tool-call path (`_dispatch_tool_calls` defers a tool whose schema is in `_loaded_schemas`; `resume_after_auth` re-dispatches via `self.tools.get(name)`) composes trivially. The tool was always in the registry; the loaded-set state is irrelevant to dispatch.
- Search calls mutate the loaded set without mutating the registry. `search_tools(query)` and `search_mcps(query)` add matched schemas to `_loaded_schemas` for next-iteration visibility; the underlying `Tool` instances were already constructed at agent build time.

- Rationale: matches operator mental model. "I asked the agent about tools earlier in this conversation; it should remember." No need to re-search every turn for tools already discovered. New session = clean slate, which matches "starting fresh." The visibility-filter framing also resolves the F5 pause/resume invariant cleanly without special-casing.
- Trade-off: long-running sessions can accumulate a large loaded set (every search call adds matched tools, no eviction). For F10 we accept this; if measurement shows persistent bloat, a follow-up flight can add LRU or session-time eviction.

**§4. Substring match on name + description, case-insensitive, catalog order** — the search implementation is simple: lowercase the query, lowercase each candidate's `name` + `description`, return candidates whose lowercased text contains the query substring. Empty query returns all matching the per-agent filter. No scoring, no embeddings, no fuzzy match.

- Rationale: F10 is an architectural shift, not a search-quality flight. Substring is good enough for the operator's stated success criterion (which doesn't even need a query — empty-query enumeration is the dominant case). Embeddings would add a model dependency and an index-build phase neither of which is needed at MVP.
- Trade-off: bad query phrasing yields no results. Mitigation: agents can iterate the query; future flight can add fuzzy match if measurement shows agents commonly fail to find tools they could use.

**§5. Synthetic source-level descriptions for `search_mcps`** — when an MCP source has no operator-authored description (today none do — `MCPSource` has `name` + `config` + `_cache`, no `description` field), `search_mcps` builds a description from the source's cached tool short-names: `"cloudflare_api: list_zones, get_zone, list_dns_records, ... (37 tools)"`. Truncated to a reasonable length (~200 chars).

- Rationale: gives the agent enough signal to decide whether the source is relevant without paying the per-tool schema cost. Operator-authored descriptions are a separate concern; F10 doesn't add a description field on `MCPSource`.
- Trade-off: synthetic descriptions are noisy and don't reflect server intent. Adding a description field on `MCPSource` (as a follow-up) lets operators type the high-level value. F10 ships the synthetic for now; mission known-issues captures the gap.

**§6. Extend `BASE_PROMPT` to teach the discovery protocol** — `agent/config.py:BASE_PROMPT` gets a new section explaining the 2-tool baseline + the search-to-load mechanic. The instruction is global (all agents inherit it). Tool descriptions on `search_tools` and `search_mcps` reinforce the same protocol but the canonical statement lives in the prompt.

- Rationale: protocol is global; the prompt is where global protocol lives. Tool descriptions are read post-tool-selection (the model sees them when deciding which tool to call), but the meta-instruction "search before you act" is a pre-decision instruction. Prompt is the right surface.
- Trade-off: marginally larger system prompt on every agent. Small absolute cost; high signal value.

**§7. Mission constraint amendment** — `mission.md`'s constraint "Agent-loop semantic changes are limited to a documented pause/resume primitive (F5 amendment)" is amended at L5 to allow lazy tool catalog scope change as a second sanctioned loop-level extension. The amendment notes:
- Agent dispatches by tool name — UNCHANGED.
- Iteration cap — UNCHANGED.
- Continue-tool signal — UNCHANGED.
- Capability-gate fallback (no-tool-support providers run plain chat) — UNCHANGED.
- F5's pause/resume primitive (`auth_required` → modal → resume) — UNCHANGED.
- **F10 NEW**: agents may carry a session-scoped mutable loaded-schema set; the catalog presented to the LLM is `[search_tools, search_mcps, continue] + loaded_schemas` per iteration; `search_*` tools mutate the loaded set as a side effect.

- Rationale: the original constraint was rightly conservative ("no surprise loop semantics"). F10's change is bounded and well-defined; explicit amendment preserves the constraint's audit trail without weakening it.
- Trade-off: amendment process is a small cost paid at L5. Acceptable.

**§8. Studio UI relabel + chat-time loaded indicator deferred** — `tools-tab.js` and `mcps-tab.js` currently use phrasing like "Tools" and "MCPs" which under F10's architecture means "tools the agent CAN load" rather than "tools the agent has." Operator mental model needs the relabel for accuracy. F10 does NOT ship the relabel — the architectural change lands first, and a follow-up flight in M07 (or M08 if M07 closes first) handles the UI semantics. Similarly, a chat-time indicator showing the currently-loaded set is high-value but not in F10's MVP.

- Rationale: separating the architecture from the UI semantics keeps F10 focused. The architecture is harder to validate than the labels; the labels are easy to evolve once the architecture is locked.
- Trade-off: between F10 landing and the follow-up flight landing, the Studio UI's labels mismatch the runtime semantics. Operator-facing confusion is possible. Mitigation: F10's debrief calls out the deferred relabel as an immediate-priority follow-up.

**§9. Schemas computed per iteration, not within a single LLM call** — `_run_iterations` re-reads `_compute_visible_schemas()` at the top of each iteration. A search call within iteration N adds schemas that show up in iteration N+1's `tools=` array; the LLM cannot search-and-call in the same iteration because its commit point is the assistant message that contained the search call.

**Implementation detail**: `_run_iterations` currently awaits `self.llm.supports_tools()` once before the while-loop (`agent/core.py:108`). F10 keeps the `supports_tools()` await OUTSIDE the iteration loop (a one-time gate); only the schema computation moves into the loop body. This avoids re-awaiting `supports_tools()` per iteration (which could be a cached property today but might involve network in some provider implementations).

- Rationale: matches LLM API semantics. The `tools=` array is a per-request commitment; once the model's response with tool-call has come back, the next request is the next iteration. There's no "in-flight schema mutation" mechanism without breaking the request shape.
- Trade-off: minimum 2-iteration cost for a tool-using turn (turn 1: search; turn 2: call the tool). Already accepted in §2.

**§10. Candidate-set construction — Path B (cache-only hydration) with Path A fallback** — to construct `MCPClientTool` instances without paying the per-source `acquire`+`list_tools` cost at agent build time, F10 introduces a cache-only hydration path:

- **Path B (preferred)**: a new `MCPToolProvider.build_candidates_from_cache()` (or equivalent) reads each attached source's `source.config._cache.tools` (populated by L1's source-edit Refresh; payload shape `{name, description, input_schema}` per `api.py:1014-1042`), constructs `MCPTool` dataclasses from the cached payload, and instantiates `MCPClientTool` instances bound to the source — without calling `acquire()` or `list_tools()`. The actual MCP connect happens lazily on first tool execute (the existing `MCPClientTool.execute` path already calls `acquire()` via the pool, so dispatch works unchanged).
- **Path A (fallback)**: if L3 implementation discovers `MCPClientTool.__init__` requires connection state that can't be deferred (e.g., session-scoped resources beyond the `MCPTool` dataclass + `effective_source`), fall back to keeping the existing `factory._build` integration with `MCPToolProvider.get_tools_for_agent` (which DOES `acquire`+`list_tools`). The candidate registry is built eagerly; only model-visibility is lazy. Functionally equivalent for the F10 user-facing wins (token-cost reduction + mid-session attach), at the cost of per-source connect-on-build.

L3 design pass picks Path A vs Path B based on what `MCPClientTool.__init__` actually requires. Both paths preserve §3's "registry holds full candidate set; loaded set is visibility filter" invariant.

- Rationale: F10's primary win is the model-side token-cost reduction + mid-session catalog mutability. Whether the server-side acquire happens at build-time or first-use is a secondary concern; locking F10 to Path B at design time would block on a verification we can do at L3-design instead.
- Trade-off: Path A keeps server-side eager-connect cost. For attached sources the operator never uses, this is wasted work. Mitigation: a follow-up flight can add lazy-connect once F10's catalog model is in place.

**§11. F9 paused; F10 takes the working copy** — branch workflow strategy = `branch` per ARTIFACTS.md, single-checkout. F9's L5/L6/L7/L8 cannot proceed in parallel with F10 on the same working copy. F9 paused at L3-landed; resume-or-absorb decision deferred to F10 close. At F10 close:
- F9's remaining legs may be revived as-is if F10's architecture doesn't invalidate L5/L6/L7's chat-side scenarios.
- Or F9 may be re-scoped: L5/L6/L7 absorbed into a single rebuilt leg under the new architecture.
- Or F9 marked `aborted` with M07 mission-close inheriting the partial work.

The decision lives at F10 close, when we know what F10 surfaced.

- Rationale: keeps branch lifecycle clean. F10 is operator-prioritized; F9 cycle yields. Absorbing F9's remaining legs into F10 would blow F10's scope (architectural change + alignment vibing in one flight = ungovernable).
- Trade-off: M07 close is delayed. F9's vibing investment isn't lost — L1+L2+L3 polish ships unchanged; L5/L6/L7 chat-side polish was always going to follow architecture decisions.

### Prerequisites

- [x] F9 L3 landed (`flight/09-alignment` merged to main; current branch `flight/09-alignment` has been hard-reset to main per the post-merge cleanup pattern).
- [x] **F9 paused** — F9 flight log Decision entry "F9 paused for F10 lazy-tool-discovery pivot (2026-05-10)" landed; F9's flight.md left in `ready` (its actual current state of `in-flight` was never updated; not F10's fix).
- [ ] **New branch `flight/10-lazy-tool-discovery`** created off `main` (= F9 L3-landed state) — handled by `/agentic-workflow` at flight start.
- [x] Agent runtime baseline understood: `_run_iterations` reads `tool_schemas` once per step via `tools.all_schemas()`; `_execute_tool` translates `MCPAuthRequired` and generic exceptions; tool registry built once at `factory._build`.
- [x] `BASE_PROMPT` location and shape confirmed (`agent/config.py:9-32`).
- [x] `MCPToolProvider.get_tools_for_agent` integration in `factory._build` confirmed (`factory.py:157`).
- [x] `source.config._cache.tools` populated by L1's source-edit Refresh confirmed; usable as the search index for `search_mcps`.
- [ ] Mission constraint amendment text drafted and reviewed before L5 lands.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented (including architect-review feedback incorporated 2026-05-10)
- [x] Prerequisites verified (branch creation deferred to `/agentic-workflow` at flight start)
- [x] Validation approach defined (per-leg unit/integration tests + L4 system-prompt integration test + L5 operator-felt HAT + final regression sweep)
- [x] Legs defined (5 legs sketched; per-leg `/leg` design just-in-time by `/agentic-workflow`)

---

## In-Flight

### Technical Approach

The runtime change is small and well-localized:

1. **`Agent.__init__` adds session state** (`agent/core.py:42-58`):
   ```python
   self._loaded_schemas: list[dict] = []
   self._loaded_tool_names: set[str] = set()
   ```

2. **New module-level constants** alongside `CONTINUE_SCHEMA` (`agent/core.py:11`):
   ```python
   SEARCH_TOOLS_SCHEMA = {"name": "search_tools", "description": "...", "parameters": {...}}
   SEARCH_MCPS_SCHEMA = {"name": "search_mcps", "description": "...", "parameters": {...}}
   ```

3. **`_compute_visible_schemas()` method on Agent**:
   ```python
   def _compute_visible_schemas(self) -> list[dict]:
       return [SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas
   ```

4. **`_run_iterations` reads per-iteration** (`agent/core.py:108-111`): replace the once-per-step `tool_schemas = (self.tools.all_schemas() or []) + [CONTINUE_SCHEMA]` with a per-iteration call to `_compute_visible_schemas()`. The `supports_tools()` gate stays — providers without tool support still run plain chat with empty tools.

5. **`Agent.reset()`** (`agent/core.py:284`) clears loaded state alongside messages.

6. **Two new tool implementations**:
   - `the_one/tools/_search_tools.py` — receives the agent's full ToolRegistry + AgentConfig at construction; on call, filters by `enabled_tools`/`disabled_tools`, substring-matches name + description, mutates the agent's loaded set, returns formatted result text.
   - `the_one/tools/_search_mcps.py` — receives the agent's MCPToolProvider + AgentConfig at construction; on call, enumerates `mcp_source_ids`, reads each source's `_cache.tools`, applies per-source `mcp_overrides`, substring-matches across source name + synthetic description + per-tool name+description, mutates the agent's loaded set, returns formatted result text.

7. **`AgentFactory._build`** (`agent/factory.py`) keeps populating the `ToolRegistry` with the FULL candidate set (built-ins + every MCP tool from every attached source). What changes is the MCP-tool construction path per Design Decision §10: Path B uses a new `MCPToolProvider.build_candidates_from_cache()` that hydrates `MCPClientTool` from `source.config._cache.tools` without calling `acquire()`+`list_tools()`; Path A keeps the existing eager-acquire `get_tools_for_agent` integration if Path B turns out infeasible at L3 design. Either way, the registry holds the full candidate set; `search_*` tools mutate `_loaded_schemas` (the model-visibility filter) as a side effect of search results matching.

8. **`agent/config.py:BASE_PROMPT`** gets a new paragraph explaining the discovery protocol.

9. **`mission.md` Constraints** gets an amendment at L5 documenting the agent-loop scope change.

### Checkpoints

- [ ] **L1 landing**: Agent loop reads per-iteration `_compute_visible_schemas()`. Baseline catalog = `[search_tools_stub, search_mcps_stub, continue]`. Search tool implementations are stubs that return empty results — agent loop is exercised end-to-end before the search logic lands. Tests cover the new agent-instance state, the per-iteration recompute, and the loaded-set persistence across user turns.
- [ ] **L2 landing**: `search_tools` real implementation lands. Agent can search built-in tools and have them appear in subsequent iterations' `tools=`. Per-agent `enabled_tools`/`disabled_tools` filter applied. Tests cover filter, persistence, no-match, empty-query.
- [x] **L3 landing**: `search_mcps` real implementation lands. Agent can search MCP sources, get source-level summaries with synthetic descriptions, and have matched MCP tools' schemas appear in subsequent iterations' `tools=`. Per-agent `mcp_source_ids` + `mcp_overrides` filter applied. Tests cover filter, no-cache fallback (source registered but never Refreshed), override application.
- [ ] **L4 landing**: `BASE_PROMPT` updated to teach the protocol. End-to-end integration test: real LLM call (mock or fixture provider) drives a search → load → call sequence. Browser test for the operator's stated success scenario.
- [ ] **L5 landing**: Mission constraint amendment drafted + landed in `mission.md`. Final regression sweep against F8 baseline (1376 unit / 255 browser / 43 pre-existing flakes); diff for net-new failures. Bundled fresh-context Sonnet review across full F10 diff. Operator-felt HAT verifying the success scenario end-to-end with a real Cloudflare API MCP attached.

### Adaptation Criteria

**Divert if**:
- L1 surfaces an architectural blocker in the agent loop refactor (e.g., the per-iteration recompute breaks streaming-bubble semantics in `chat.js` or breaks the F5 OAuth pause/resume contract). Pause F10, audit, decide whether to re-shape the loop or defer the architecture.
- The token-cost measurement at L5 shows the new architecture is WORSE than the baseline (search overhead exceeds the per-call schema savings) for typical operator workloads. F10 still ships for the mid-session-attach win, but the token-cost narrative gets corrected in mission close.
- L4's integration test reveals a model-side behavior gap: small models (Ollama Gemma) consistently fail to call `search_*` tools and just respond without searching. F10 may need to ship with a "no-tool-support → plain chat" fallback that's distinct from the current `supports_tools()` gate (since the new gate is "supports tool-search protocol", not "supports tools at all").
- Cross-flight invariant breaks: the F5 `auth_required` pause/resume pattern must continue working. Specifically, the deferred-tool-calls path in `_dispatch_tool_calls` must compose with the new loaded-set state — a tool-call that triggers auth-required, gets deferred, and resumes after consent must still find its schema in the loaded set.

**Acceptable variations**:
- Leg ordering can swap (e.g., L3 before L2 if `search_mcps` is the operator-felt priority).
- L1's stub search tools can return canned data rather than empty if that helps drive L1's tests.
- L4's integration test's mock LLM can be a fixture rather than a real provider call if real-provider testing has flakes.
- Studio UI relabel deferred to follow-up flight (already in §8).

### Legs

> **Note:** Tentative. Each leg is `/leg`-designed just-in-time before its session.

- [x] `01-agent-loop-2-tool-baseline` — Agent-loop refactor: `_compute_visible_schemas` reads per-iteration; baseline catalog `[search_tools_stub, search_mcps_stub, continue]`; loaded-set state on Agent instance; `reset()` clears it. **Stub `search_*` implementations return CANNED results** (a fixed set of 1-2 tool schemas added to `_loaded_schemas`) so the persistence-across-turns test actually exercises the mutation; empty-results stubs would pass the test trivially. **L1's standalone value is purely architectural** — no mission criterion ticks at L1, since the operator-felt search behavior only becomes meaningful at L2+. **HAT-script interpretive note**: `tests/HAT.md:111` and `:167` script-counts of `mcp__*` schemas reflect REGISTRY membership ("agent CAN load these"), not model-visibility ("LLM sees these"); update the HAT prose to reflect the contract shift, even though the assertion still passes. Tests for state machine + per-iteration recompute + reset behavior + canned-stub mutation. ~150-200 LOC.
- [x] `02-search-tools-implementation` — `the_one/tools/_search_tools.py` real implementation. Substring match on name + description, case-insensitive. Per-agent `enabled_tools`/`disabled_tools` filter. Mutates agent's `_loaded_schemas`. Empty query returns all. Tests cover filter, persistence, mutation idempotency. ~150-200 LOC.
- [x] `03-search-mcps-implementation` — `the_one/tools/_search_mcps.py` real implementation. Enumerates agent's `mcp_source_ids`; reads `source.config._cache.tools`; synthesizes source descriptions (truncated to ~200 chars); substring matches on source name + synthetic description + per-tool name+description. **First task: extract the `mcp_overrides` filter logic** currently in `_tool_provider.py:264-284` (the `enabled_tools`/`disabled_tools` mode-detection + `StdioMCPOverride.model_validate` dance) into a shared helper in `_tool_provider.py`; both `get_tools_for_agent` (existing) and `search_mcps` (new) call it — avoids forking the per-source filter. Then `search_mcps` mutates agent's `_loaded_schemas` based on filtered candidates. Path B vs A from §10 is resolved at L3 design via a quick architect probe of `MCPClientTool.__init__` requirements. Tests cover filter, no-cache fallback (source registered but never Refreshed), override application, **50-tool-source synthetic-description truncation**. ~200-250 LOC.
- [x] `04-system-prompt-and-integration` — `BASE_PROMPT` extension teaching the protocol. End-to-end integration test (mock or fixture provider) driving search → load → call sequence. Browser test for the operator's stated success scenario. ~50-100 LOC.
- [x] `05-mission-amendment-regression-and-commit` — Mission constraint amendment in `mission.md`. Full unit + browser regression sweep against F8 baseline; diff for net-new failures. Bundled fresh-context Sonnet review across full F10 diff. Operator-felt HAT verifying success scenario with real Cloudflare API MCP attached. **HAT scenario explicitly calls out the new model**: operator should see the agent search after attach, NOT immediate tool availability — this is consistent with F10's design, but operators trained on F1-F9's eager-load model may read it as a regression on first encounter; the HAT prose makes the new contract visible. **Token-cost measurement**: capture iteration count + total prompt-tokens for the HAT scenario before-and-after F10 (run the same scenario against `main` pre-F10, then post-F10) and report deltas in F10 debrief. ~50 LOC + verification.

---

## Post-Flight

### Completion Checklist

- [ ] All 5 legs completed
- [ ] All inline fixes merged
- [ ] Full unit suite passes (modulo pre-existing knowns); diff against F8 baseline 1376 pass shows no net-new regressions
- [ ] Full browser suite passes (modulo pre-existing flakes); diff against F8 baseline 255 pass / 43 fail shows no net-new regressions
- [ ] Mission constraint amended in `mission.md` reflecting F10's agent-loop scope change
- [ ] Bundled fresh-context Sonnet review approves the F10 diff
- [ ] F9 resume-or-absorb decision documented (in F10 debrief or M07 known-issues)
- [ ] Studio UI relabel + chat-time loaded indicator deferred to follow-up flight; flagged in mission known-issues
- [ ] Mission #7 status reviewed; if F9 + F10 both close cleanly, M07 ready for `/mission-debrief`

### Verification

- **Per leg**: unit + integration tests for the leg's deliverable. L4 + L5 add browser + HAT verification.
- **L5 regression sweep**: `docker compose exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py` (full unit) + `docker compose exec the-one pytest tests/browser/ -q --timeout 120 -m browser` (full browser); diff against F8 baseline.
- **Bundled fresh-context review**: spawn a Sonnet reviewer with no prior F10 context; reviewer reads the full F10 diff against main; reviewer approves or flags issues for inline-fix before final commit.
- **Operator-felt HAT (L5)**: success scenario "what tools do you have available?" → list (after agent searches) → operator attaches a new MCP → operator opens new chat → "what tools do you have available?" → updated list. Caplog clean across the exercise.
- **Mission criteria**: criteria #7, #10, #11 advanced. #12 status preserved (no Studio UI changes).
