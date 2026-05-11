# Mission Debrief: MCP Integration

**Date**: 2026-05-10
**Mission**: [MCP Integration](mission.md)
**Status**: completed
**Duration**: ~6 weeks (F1 design started early-April 2026; F10 closed 2026-05-10)
**Flights Completed**: 11 of 11 originally-planned-or-emergent (F1-F8 + F6.5 + F6.6 + F9 + F10; F7 retired pre-execution by post-F6.5 review)

---

## Outcome Assessment

### Success Criteria Results

| # | Criterion (abbrev) | Status | Evidence |
|---|---|---|---|
| 1 | Encrypted MCP source registration via Settings UI | **Met** | F1 landed `MCPSourceRepository` with `Encryptor` envelope; Studio MCP Servers page from F1 + polished by F9 L1. Sensitive fields encrypted with same Fernet key + rotation pipeline as LLM providers. `__MASKED__` sentinel preserved. |
| 2 | Both transports supported (stdio + streamable-http) per spec | **Met** | F2 landed `MCPClient` + `_pool` for both. Capability negotiation handled (initialize handshake, version negotiation, post-init protocol-version header). `_PINNED_PROTOCOL_VERSION` constant in code. |
| 3 | OAuth 2.1 + PKCE end-to-end usable from Settings UI | **Met** | F5 landed full DCR flow with RFC 8707 Resource Indicators, audience-bound tokens, refresh-token rotation. F6.5 simplified to spec-compliant DCR-only (manual-paste fallback removed). F6.6 closed connect-time 401 translation. |
| 4 | Local stdio MCP servers run in OS-level sandbox | **Met (Linux only)** | F3 landed `MCPSandbox` adapter + bubblewrap Linux backend. Env-allowlist (8-key allowlist + operator overlay), FS scope, network policy, process supervision. macOS / Windows backends explicitly out-of-scope and paper-exercised per F3 design. |
| 5 | Idle local MCP processes reaped + respawned transparently | **Met** | F4 landed per-(agent, source) registry + idle-TTL reaper, FastAPI lifespan integration, shutdown_drain verified caplog-clean across F6 + F9 baselines. |
| 6 | Simplified inspector covers tools-list + tools-call subset | **Met** | F6.5 + F8 + F9 L1 polished the source-edit page's Test connection button + capability flags + collapsible schemas. F7 (full inspector) retired pre-execution post-F6.5 review; useful pieces folded into F8. |
| 7 | Agent attaches MCPs; tools become callable | **Met** | F6 landed per-agent attach + tool routing. F8 landed agent-editor MCPs tab. F9 L3 polished the attach UX. F10 shifted semantics from eager-load to lazy-search; criterion phrasing ("tools become callable during a session") still holds — just via search-then-call. |
| 8 | Stable namespacing for tool-name collisions | **Met** | F6 §2 `mcp__{normalize(source.name)}__{tool.name}` scheme with 64-char ceiling. F10 `SearchMcps` `_filter_mcp_candidates` correctly handles prefixed names. Not engineered-collision-tested in F9 vibing; carry as known issue if real collisions surface in operator's stack. |
| 9 | Credentials never plaintext outside encryption boundary | **Met** | `__MASKED__` sentinel preserved across all flights. F5 OAuth tokens stored encrypted via `Encryptor`. F6 confirmed no plaintext leakage in API responses / logs / inspector trace. F9 L1 vibing verified the post-OAuth fetch path masks tokens. |
| 10 | Graceful failure isolation | **Met** | F6 §8 enumerated five failure classes; `MCPToolProvider.get_tools_for_agent` graceful-skips deleted sources, connect failures, auth-required, prefix collisions, name-overflow. `MCPClientTool.execute` returns `[error]` envelope on per-call failure. F10 Path B fix (cache-first agent build) further isolated agent-build-time failures from operator UX. |
| 11 | Automated coverage at each layer | **Met** | Encrypted persistence, transport lifecycle, sandbox spawn, idle-TTL reaper, resolver substitution, tool-name-spacing, inspector round-trip all have unit + integration coverage. Final regression: 1507 unit pass / 283 browser pass / 0 net-new failures vs F8 baseline (1376/255). |
| 12 | Settings + inspector + MCPs tab meet M04/M06 design-language quality bar | **Met (with deferral)** | F8 landed Studio MCPs tab + F8 polish absorbed from retired F7. F9 L1+L2+L3 vibing polished the source-edit page + MCPs tab + agent tile. F10 §8 explicitly DEFERS "Allowed tools" / "Allowed MCPs" relabeling under F10's new semantics — operator-facing accuracy gap that worsens with use. Flagged for M08. |
| 13 | MCP protocol version pinned + capability-gating degrades cleanly | **Met** | `mcp==X.Y.Z` exact-pin + `_PINNED_PROTOCOL_VERSION` module constant landed at F2. Capability-gate fallback for older revisions verified at F2 + sanity-exercised across F4-F10 against live servers. |

### Overall Outcome

**Achieved.** Mission 7 turned MCPs into a first-class user-managed capability in the-one. The operator can register/edit/remove MCP sources via the Settings surface (F1, polished by F9 L1), test them inline (F6.5 + F8 + F9 L1), attach them to agents via the Studio MCPs tab (F8 + F9 L3), and use them in chat — under F10's lazy-discovery architecture — by asking the agent what tools it has and watching it search. Cross-flight invariants (the `MCPClient` four-typed-exceptions contract, the resolver chain shape, the encryption envelope reuse, the sandbox adapter abstraction, the agent-loop semantic-changes constraint with its F5 + F10 amendments) were maintained without shortcuts.

Two notable shifts from the original mission spec:
1. **F7 (full inspector) retired pre-execution** post-F6.5 review — the operator-persona analysis concluded a Postman-class developer tool didn't fit the user. F8 absorbed the useful pieces (capability flags, input-schema visibility). This was a deliberate scope correction, not a failure.
2. **F10 (lazy tool discovery) added late** mid-F9 when the operator surfaced an architectural concern about token-cost scaling with attached-MCP count + no mid-session attach pickup. F9 paused at L3-landed for the F10 pivot; F9 resumed post-F10-merge and closed with two inline polish fixes. This pivot is structurally clean (the architect-debrief verdict: "the cleanest element of the mission") and adds an explicit second sanctioned loop-level extension to the agent-loop semantic-changes constraint.

---

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| F1: Encrypted persistence + Settings | completed | Schema migration to `streamable-http` literal + `Encryptor`-envelope on `mcp_sources.config`; Studio MCP Servers list/detail/create/edit/delete UI; `__MASKED__` sentinel preserved. Settings nav relocation from admin → Studio post-F2 retrospective correction. |
| F2: MCP client foundation | completed | `mcp` SDK pinned exact-version + `_PINNED_PROTOCOL_VERSION`. Thin `MCPClient` wrapper around `ClientSession` for both transports. Initial unit + integration tests for connect-list-call. F2 L7 HAT surfaced the disconnect-noise teardown issue (resolved at F5 L1 + verified at F6 baseline). |
| F3: Sandbox adapter + bubblewrap | completed | `MCPSandbox` adapter contract + Linux bubblewrap backend. Env-allowlist, FS scope, network policy, process supervision. macOS / Windows backends paper-exercised. CI-compatibility probe verified bwrap runs in the Playwright Python image. |
| F4: Idle-TTL lifecycle | completed | Per-(agent, source) registry of sandboxed processes. Single async reaper task. FastAPI lifespan shutdown_drain. Worker-task-per-entry pattern for same-task connect/disconnect (satisfies anyio cross-task cancel-scope guard). |
| F5: OAuth 2.1 + PKCE | completed | Full DCR flow surfaced from Settings. PKCE on every flow. RFC 8707 Resource Indicators. Audience-bound tokens, refresh-token rotation, no token-passthrough. Loopback redirect integrated with FastAPI. F5 L5's chat-side `auth_required` pause/resume primitive amends the agent-loop constraint. |
| F6: Per-agent attach + tool routing | completed | `AgentConfig.mcp_source_ids` wired through `MCPToolProvider`. `mcp__{source}__{tool}` prefix scheme with 64-char ceiling. Override resolver composes MCP-shaped overrides. Five failure-class graceful degrade. |
| F6.5: OAuth simplification + Test button | completed | Stripped GitHub-legacy manual-entry fallback. DCR happy path becomes canonical. Test connection button on source-edit page. Auth-on-tools/list common posture (Cloudflare API MCP + most production OAuth MCPs) graceful-degrades. |
| F6.6: Cleanup + connect-time 401 | completed | F6.5 debrief follow-ups landed (3 unit tests for inline fixes, `_emit_ws_event` test helper re-export, synthetic-csid pattern documentation). `MCPClient.connect()` 401 translation mirroring F6.5 L2's `list_tools` pattern — closes F6 A5 lossy-diagnostic case. |
| F7: Simplified inspector | **retired pre-execution** | Post-F6.5 review concluded the operator-persona didn't fit a Postman-class developer tool. Useful pieces (capability flags, input-schema visibility) folded into F8. Content-block rendering deferred until real MCP servers return those types. |
| F8: Studio MCPs tab | completed | Replaced stub `mcps-tab.js` with real attach + override UI. Multi-attach chip-list, per-tool toggle, credential override, hash routing, capability flags + collapsible schemas. Browser tests cover attach/detach/override/per-tool-toggle/empty-state. |
| F9: Alignment | completed (collapsed L5-L8) | Multi-leg vibe-coding flight. L1+L2+L3 landed (HTTP+stdio source-edit polish; agent-editor MCPs tab polish). **Paused at L3-landed for F10 pivot.** Resumed post-F10-merge; two polish anomalies fixed inline (login button name; chat-UI table rendering). L4 absorbed into L3 (transport-agnostic UI surface). L5/L6/L7/L8 collapsed per F9 §1+§2 operator-driven scope adaptation. PR #42. |
| F10: Lazy tool discovery | completed | **Late architectural pivot.** 2-tool catalog baseline (`search_tools` + `search_mcps` + `continue`); per-iteration visibility filter; auto-load on search match; per-session loaded set; new-session-starts-blind. Path B (cache-first agent build) absorbed inline during HAT vibing. Constraint #71 amended with F10 clause + 5 UNCHANGED invariants enumerated. Token-cost shape: ~27% reduction per 3-iteration session estimate. PR #41 (squash-merged as `6238f7d`). |

---

## What Went Well

**1. Cross-flight invariant discipline.** The `MCPClient` four-typed-exceptions contract held across 11 flights without erosion. F6.5 + F6.6 added `MCPAuthRequired` to `list_tools` + `connect` translation paths without introducing a fifth type. F10's massive agent-loop refactor preserved the dispatch-by-name contract and F5 pause/resume primitive trivially under the visibility-filter framing. Constraint #71 amendments (F5 + F10) explicitly enumerate UNCHANGED invariants, creating an audit trail.

**2. The F10 late pivot.** When the operator surfaced the token-cost-scaling + mid-session-attach concern during F9 L5 design, the flight was paused mid-mission, F10 was opened, designed, reviewed (architect + Sonnet code reviewer), implemented in 5 legs over a single day, and merged with zero net-new test failures. The architect-debrief verdict: "the cleanest element of the mission." Branch lifecycle handling (F9 paused-not-aborted; F10 own branch off F9 L3-landed main; F9 resumed by rebasing onto post-F10 main) preserved both flights' investment.

**3. Subagent isolation pattern (F9 §9).** All code-change work delegated to subagents; parent context stayed in vibing + triage + dispatch. F9 L1 (9 batches), L2 (14 batches), L3 (2 batches), F10 (1 implementer per leg + 2 design reviewers + 1 closing review): the pattern scaled cleanly without context overflow. The parent context never read full diffs or investigation traces, only structured summaries.

**4. Operator-driven scope adaptation.** F4 absorbed into F3 (L4 absorbed into L3 — transport-agnostic UI surface). F7 retired pre-execution. F8 absorbed F7's polish pieces. F10 absorbed F10 §10's Path B during HAT vibing when the operator surfaced the chat slowness. F9 L5-L8 collapsed into the resume vibing. The mission grew, shrunk, and shifted shape across the 6-week arc — and the methodology accommodated each shift with explicit decision capture in flight logs.

**5. Caplog gate retired the disconnect-noise teardown debt.** F2 L7 surfaced; F4 + F5 L1 designed the fix (worker-task-per-entry pool + dispatcher-owned-stack); F6 Tier-1 HAT verified retirement (0 `MCPClient.disconnect` warnings across 3 agent builds + 2 tool calls + 1 full lifespan shutdown_drain including uvicorn WatchFiles reload under real bwrap subprocess teardown). F4 + F5's design pattern is correct against real subprocess teardown.

---

## What Could Be Improved

### Process

- **F9 cumulative-LOC ceiling overrun (~1193 / ~600).** The §2 Sizing Thresholds underestimated the real shape of alignment-flight work when closing F1-F8 functional gaps (vs. pure UI polish). For future alignment flights: either raise the ceiling for "functional gap closures" vs. "polish-only," or split alignment legs more aggressively when functional gaps surface mid-leg.
- **F10 §10 sizing estimate (~200-250 LOC) underestimated.** Actual L3 came in at ~545 LOC due to the shared filter helper extraction + source index plumbing. Architectural-shift legs that touch multiple modules underestimate by ~2x when the LOC budget is set by the "leg only" framing without accounting for adjacent-refactor seams.
- **Mid-flight pivot mechanics.** The F9 → F10 pivot at L3-landed worked but the branch hygiene was ad-hoc (`flight/09-alignment` paused; new `flight/10-lazy-tool-discovery` off main; rebase F9 onto post-F10 main at F9 resume). Document this as a Mission Control methodology pattern if it recurs.
- **F10 architect identified a misread during pre-review** — the "_search_backends.py was unplanned" flag from the Flight Director was actually a pre-existing F5 DDG-search backend file. Lesson: when listing "unplanned additions" pre-Reviewer, verify against git history rather than trusting the file inventory.

### Technical

- **A-F10-1 (OAuth login opens in new tab vs inline modal).** Operator-visible regression captured at F10 HAT. Not F10's regression (F10 didn't touch the OAuth modal or chat.js handlers); likely environment-specific or pre-existing F5/F6.6 quirk. **Investigate priority** at M08's first flight.
- **`_build_source_index` non-`KeyError` exception swallow without logging** (`factory.py:70-74`). F10 Phase 2d Reviewer item 1; single-line diff fix; land before M08's first flight.
- **Duplicate `_cache.tools` DB read** (`_build_source_index` + `_tool_provider.get_tools_for_agent` Path B). Architectural duplication that a future maintainer will trip over. Extract a shared `MCPCacheHydrator` utility OR pass the loaded cache between callers.
- **`_search_stubs.py` in production package.** Now test-only fixture; should move to `tests/` next maintenance pass.
- **Studio UI relabeling deferred.** F10 §8 explicitly defers "Allowed tools" / "Allowed MCPs" labels. Operator-facing accuracy gap that worsens with use. **Block any M08 flight touching the agent config UI on this.**
- **Server-side truncation of verbose tool results not surfaced** (M07 known-issue from F6.5). MCP spec is silent on pagination; the-one has no truncation detection. Affects verbose-output servers (Cloudflare API, GitHub on long file lists). Mitigation candidates documented in the known-issue entry.
- **Per-agent OAuth re-auth + per-(agent, source) credential storage** still deferred from F8. Blocker for "two agents with distinct GitHub credentials on the same source" beyond credential substitution at agent-build time. Sized at 4-5 legs / 1500-2000 LOC at F8 — successor mission scope.
- **`_pool.py` test isolation / `_shutting_down` flag leak.** Pre-existing from F8. Cross-cutting refactor. Deferred to follow-up architectural flight.
- **Search quality is substring-only.** Intentional MVP. Operators with 10+ attached MCP sources + 50+ tools each will hit false-negative query mismatches. Fuzzy match or BM25 index is the natural upgrade path; F10's architecture supports it without structural change.

### Documentation

- **Promote architectural conventions to `CLAUDE.md`** per the architect debrief recommendation:
  - The four-typed-exceptions contract (confirm "MCP Error Translation Contracts" section exists).
  - The `_compute_visible_schemas` + shared-mutable-containers pattern as the sanctioned extension point for future loop-level visibility changes.
  - The anyio worker-task-per-entry pattern for connection pools.
  - The factory.create() ordering invariant (source index BEFORE `SearchMcps` registration BEFORE MCP tool loop).
- **F3 sandbox seam validation.** Document that the `prepare_spawn() → SpawnSpec` interface was paper-exercised against macOS + Windows shapes at F3 and survived F4-F10 without Linux-specific leakage. The next mission targeting macOS / Windows can rely on the abstraction.

---

## Lessons Learned

### Technical
- **`anyio` cross-task cancel-scope guard is load-bearing.** F4's worker-task-per-entry pattern + F5 L1's dispatcher-owned-stack mechanism were the correct architectural responses; naive "connect in caller task" would have collapsed under cleanup-deadlock + cancel-scope violations. Replicate this pattern for any future async connection pool.
- **Cache-first hydration eliminates connect-timeout amplification.** F10's Path B (deferred from F10 §10, absorbed inline during HAT) demonstrated the value: agent build went from N × 30s timeout to sub-100ms when `_cache.tools` is populated. Eager-acquire-then-list is an anti-pattern for client-side latency when a cached representation is available.
- **Visibility-filter > registry mutation for catalog scope changes.** F10's framing (registry holds full candidates; loaded set is the visibility slice) preserved F5 pause/resume composition trivially. Registry mutation would have required special-casing the deferred-then-resumed dispatch path.

### Process
- **Architect pass at known-problematic-paths during inline fixes saves 30-60 min per false start.** F8 debrief recommendation 5 + F9 L2's repeated use of architect-pass (3 fired across 14 batches; each caught real complexity that would have cost the implementer time). Mission Control should standardize this pattern in the agentic-workflow skill.
- **Fresh-context bundled review at flight close catches blind spots.** F6.6 + F8 + F10's pattern. The iterative implementer is too close to local problems and misses what a clean-context reviewer flags trivially (F8: the `MCPConnectionError` token-clear path being too broad; F10 Phase 2d: the `_build_source_index` silent exception swallow). Worth its orchestration cost.
- **Exploratory vibing > scripted scenarios for alignment flights.** F9 L1 + L2 + L3 + the F9-resume wrap demonstrated this clearly — scripted scenarios were a coverage check fallback; the real polish issues surfaced organically through operator-driven cycles.

### Domain
- **MCP server quality varies widely.** Cloudflare API MCP returned truncated JSON mid-string with no `truncated` indicator (M07 known issue). The-one's runtime can't repair what the server doesn't telegraph; mitigations are heuristic at best.
- **DCR (Dynamic Client Registration) is the right OAuth default.** F6.5 simplification (removing GitHub-legacy manual-entry) was correct in hindsight — the manual fallback added complexity for one non-RFC-7591-compliant vendor while the DCR path serves the broad spec-compliant ecosystem.
- **OAuth re-auth UX at chat time** (F5 L5's lazy-OAuth) is more useful than at source-edit time alone. The inline "Login required for X" button → modal → resume pattern composes with the chat WS protocol cleanly.

---

## Methodology Feedback

**Flight Control patterns to keep:**
- Operator-driven scope adaptation as a first-class methodology pattern. Multiple flights diverted (F4 absorbed into F3, F7 retired pre-execution, F8 absorbed F7 polish, F10 pivot, F9 collapse). The flight log Decisions section captured each shift with rationale.
- Architect pass at design time + at known-problematic-path inline fixes.
- Bundled fresh-context Sonnet review at flight close.
- Subagent isolation (parent stays in vibing + triage + dispatch).

**Flight Control patterns to refine:**
- LOC ceiling estimation for alignment flights with functional gap surfacing. Calibrate higher OR split alignment legs more aggressively.
- Mid-flight pivot mechanics (branch hygiene, rebase pattern, leg-disposition format).
- "Unplanned addition" verification pre-Reviewer (verify against git history).

**New methodology patterns surfaced this mission:**
- **HAT-style alignment flight with scripted-scenarios-as-fallback.** F9 §1's "operator drives exploratory vibing; scripted scenarios are coverage check" became the de-facto pattern.
- **L4-absorbed-into-L3 / L5-L8-collapsed-into-wrap** as acceptable variations when transport-agnostic UI surface or operator-driven sign-off makes the planned scope redundant.
- **Constraint amendment discipline** (F5 + F10 both amend Constraint #71 with explicit UNCHANGED invariants enumeration). Document as the canonical pattern for cross-flight invariant changes.

---

## Recommendations

1. **A-F10-1 OAuth-new-tab investigation** — first M08 leg or standalone maintenance pass. Operator-visible regression of the F5 modal experience.
2. **`_build_source_index` exception logging + duplicate `_cache.tools` read consolidation** — small maintenance batch; can land alongside #1.
3. **Studio UI relabeling under F10 semantics** — blocks any M08 flight that touches agent config UI; do it first.
4. **Promote architectural conventions to `CLAUDE.md`** per the architect-debrief inventory (four-typed-exceptions, `_compute_visible_schemas` extension point, anyio worker-task pattern, factory.create() ordering).
5. **Consider M08 successor for deferred F8 carve-outs** (per-agent OAuth re-auth + per-(agent, source) credential storage; `_pool.py` test isolation) if those use cases become operator priorities.

---

## Action Items

- [ ] A-F10-1: investigate OAuth-new-tab vs inline-modal regression (M08 L1 or maintenance pass)
- [ ] `factory.py:70-74` non-`KeyError` exception logging fix (single-line diff)
- [ ] Extract shared `MCPCacheHydrator` utility (or pass cache between callers) to eliminate duplicate DB read
- [ ] Move `_search_stubs.py` from `the_one/tools/` to `tests/` (test-only fixture)
- [ ] Studio UI relabeling: "Allowed tools" / "Allowed MCPs" per F10 §8 deferral; chat-time loaded-set indicator (telemetry-overlay-adjacent)
- [ ] Promote architectural conventions to `CLAUDE.md` (four-typed-exceptions, visibility-filter extension point, anyio worker-task pool pattern, factory.create() ordering invariant)
- [ ] Successor mission consideration: per-agent OAuth re-auth + per-(agent, source) credential storage (F8 carve-out)
- [ ] Successor consideration: `_pool.py` test isolation refactor (pre-existing from F8)
- [ ] Successor consideration: server-side truncation detection for verbose MCP tool results (M07 known-issue)
- [ ] M07 mission status updated to `completed` (this debrief)
