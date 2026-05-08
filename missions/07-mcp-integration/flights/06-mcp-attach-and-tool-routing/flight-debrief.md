# Flight Debrief: Per-agent MCP attach + tool-routing in agent loop

**Date**: 2026-05-08
**Flight**: [Per-agent MCP attach + tool-routing in agent loop](flight.md)
**Status**: landed
**Duration**: 2026-05-08 design (~1h) → L0-L5 implementation (~5-6h orchestration) → HAT (~30min interactive)
**Legs Completed**: 5 of 5 required (L0+L1+L2+L3+L5; L4 folded into L2; L6 deferred to routine maintenance)

## Outcome Assessment

### Objectives Achieved

The flight delivered the per-agent MCP attach + tool-routing runtime end-to-end:

- `AgentConfig.mcp_source_ids` (persisted since F1, ignored at runtime) now contributes tools to the agent's `ToolRegistry` under stable `mcp__{source}__{tool}` namespacing.
- Per-agent credential overrides land via the parallel `AgentConfig.mcp_overrides` dict, source-name-keyed, dispatched through the M05 F2 Narrow/Substitute resolver.
- Tool-call dispatch routes through F4's pool (`acquire(agent_name, source_id, source_override=effective_source)` → `MCPClient.call_tool` → `MCPToolResult.text`) with the per-`(agent, source)` keying producing distinct bwrap subprocesses for distinct overrides — verified end-to-end at HAT step 4 (two PIDs with `--setenv HAT_AGENT A` and `HAT_AGENT B` respectively).
- All four failure classes from §8 (deleted source, source-fails-to-start, source-fails-mid-session, prefix collision) graceful-degrade with WARNING logs; class #1 sub-case (64-char ceiling) per-tool drops survive.
- Three F5 carry-forward debts retired: circular import chain (L0), `_pool_default` ContextVar fallback + multi-tab cross-routing bug (L3), F2-known-issue HAT verification (L5/HAT-PASS). The fourth (`_drive_flow` httpx-error broadcast) was already-satisfied per F6 Phase 1b reconnaissance.

The Tier-1 HAT executed end-to-end on 2026-05-08, with caplog gate count = 0 across 3 agent builds + 2 tool calls + 1 full lifespan shutdown_drain. **F2-known-issue retired** at `mission.md:104`.

### Mission Criteria Advanced

- ✓ **#7** — agent attaches MCP sources; tools become callable. Verified: agent A's registry contained `mcp__fetch_local__fetch`; chat dispatch round-tripped through bwrap subprocess.
- ✓ **#8** — stable namespacing for collisions. Verified: prefix scheme `mcp__{normalize(source.name)}__{tool}` plus 64-char ceiling enforcement; failure-class #4 first-source-wins drops second source's tools cleanly.
- ✓ **#10** — graceful failure isolation. Verified: 4 failure classes each tested + HAT step 5 exercised the deleted-source-rebuild path with two WARNINGs (failure class #1 + cycle-1 M4 orphan-warn).
- ◐ **#11 partial** — automated coverage of resolver substitution + tool-name-spacing. Pool tests (`test_mcp_pool.py::test_acquire_with_source_override`) deferred to docker run per the env-dependence pattern documented in anomalies A1/A2/A3; HAT exercised the runtime-equivalent path manually.

## What Went Well

**Architectural decisions held up clean.** Five design choices from the flight spec survived implementation untouched:

1. **Override surface as parallel `mcp_overrides` field** (§1) — source-name-keyed, sibling to `tool_overrides`; the collision-class argument materialized exactly as predicted (orphan-warn diagnostic surfaces cleanly when an operator deletes a source while overrides reference it).
2. **`mcp__{source}__{tool}` prefix + 64-char ceiling** (§2) — Architect cycle-1 M2 caught the OpenAI/Anthropic ceiling before implementation; cycle-2 inner-loop catch site preserved per-source resilience when one tool over-runs.
3. **Sibling-class `MCPToolProvider`** (§3) — sync Protocol vs async work + tool-name vs source-name keying + introspection caller incompatibility — all three justifications proved load-bearing. `AgentFactory` integration lands in ~25 LOC.
4. **ContextVar relocation to canonical `agent/_context.py`** (§5 / L3) — the cleanest leg of the flight. `interfaces` layer no longer owns shared state read by `mcp` and `agent` layers; dependency direction is correct. `_pool_default` sentinel grep returns zero hits in production. 13 new tests, no design deviations, single-pass implementation.
5. **Circular-import structural break** (§6 / L0) — `MCPAuthRequired` canonical at `the_one/mcp/errors.py` with re-export in `oauth/errors.py`; subprocess-isolated regression test in `tests/test_imports.py` locks the chain break.

**Phase 1b upstream reconnaissance worked.** Caught that the F5 debrief's `_drive_flow` "no error handling" claim was empirically wrong (`api.py:1106-1121` already catches `Exception` and broadcasts `auth_failed`). Recon classified 4 of 13 source items as in-scope, retired 1 as already-satisfied, deferred 6 to routine maintenance, and noted 1 as procedural — saving wasted leg work.

**2-cycle Architect design review caught real architectural defects pre-implementation.** Cycle-1 H1 (Pydantic `Annotated` metadata-hoisting in Union types) blocked a silent regression that would have made every override schema's marker dispatch fail. Cycle-2 H1 (`list_tools` doesn't propagate `MCPAuthRequired`) collapsed a planned 5-class failure model into 4 + a documented diagnostic-name caveat — a structural simplification.

**The agentic-workflow stacking pattern held.** F4 + F5 + F6 stacked uncommitted across branches; the targeted-test-only outside-docker discipline emerged in response to A1/A2/A3 hangs and let L3, L5, and the HAT recovery proceed without further hangs once disciplined.

**HAT execution recovered from misframing without losing the verification value.** When the user pushed back on the misframed `tests/test_mcp_attach_hat.py` integration-test-as-HAT, deleting the file + rewriting `tests/HAT.md` as a clean human procedure took ~10 minutes; the actual HAT then ran cleanly through the Studio UI + chat UI + curl + REPL combination, with the caplog gate verified against real bwrap subprocess teardown.

**Cycle-1 low #5 fix held.** `MCPClientTool._effective_source` per-instance caching survives post-OAuth-evict reuse — the design correctly anticipated the post-`_evict_all_for_source` re-acquire scenario where the override would otherwise be lost. Test `test_execute_acquires_and_calls` locks `acquire(source_override=effective_source)` propagation.

## What Could Be Improved

### Process

**1. A4 escaped past 3 review gates because citation-audit verifies symbol existence, not contract shape.** The L2 leg artifact's `_apply_override` pseudocode nested the agent overlay under `secrets["env"]` (stdio) / `secrets["headers"]` + `secrets["bearer_token"]` (streamable-http). The F2 transport contract treats `source.secrets` as a flat kv table — `transports/stdio.py:225` does `{**allowlist_env, **config_env, **source.secrets}`; `transports/streamable_http.py:69` does `{**config_headers, **source.secrets}`. The nesting made env-var/header VALUEs into dicts, which Pydantic rejected with `string_type` validation errors at HAT step 3.

The bug survived: Architect cycle-1, Architect cycle-2, Reviewer (Haiku) over the full L0-L5 delta. The L2 unit tests asserted the broken nested shape (self-consistent with the bug). HAT was the only verification layer that caught it.

**Why it escaped**: design-phase + implementation-phase + review-phase all referenced the transport files by file/line citation but never spot-read the contract. The §1 prose described overlay/replace semantics in English without grepping the implementation. The L2 tests pinned the wrong shape because they never reached the transport layer.

**2. HAT framing was inherited and amplified.** The agentic-workflow SKILL.md defines HAT as "the human performs verification — the Flight Director guides them through it." But F4 + F5 precedents in this codebase had drifted into calling automated bwrap integration tests "Tier-1 HAT." F6 inherited the misframing without questioning it; L5 produced a 410-LOC pytest scaffold (`tests/test_mcp_attach_hat.py`) that the user correctly pushed back on with "the hat is supposed to be human." The file was deleted in the fixup commit and replaced with a clean `tests/HAT.md` human procedure.

The Phase 5b architect review should have flagged the misframing against the SKILL.md HAT contract; instead it waved it through under "F4/F5 precedent." This is a meta-gap: precedent in the project codebase silently overrode methodology spec in mission-control.

**3. Implementer-Developer hangs (anomalies A1, A2, A3).** Three independent hangs occurred when the implementer ran the full pytest suite (or a too-broad targeted subset including `test_mcp_pool.py`) outside the dev container. Each hang was env-dependent: `_entry_worker` calls `get_connection()` for OAuth provider construction, which blocks on aiosqlite worker-thread setup outside docker. L1 cost ~40 minutes before the user killed it; L2 hung similarly; L3 went smoothly because the targeted-only discipline had landed by then.

The leg-execution prompt's "Run tests with a timeout flag" instruction is necessary but insufficient — the per-test timeout doesn't bound full-suite walltime when 30+ tests independently hit the ceiling. The discipline that worked: run `tests/test_mcp_*.py` (excluding `test_mcp_pool.py` and `test_mcp_attach_hat.py`) for outside-docker verification; defer pool + HAT to inside-docker at flight-end.

**4. Docker Desktop hang during HAT setup.** Mid-HAT, `make rebuild` hung; `docker info` and `docker ps` hung; root cause was the WSL2 backend wedging (~5 hour session wear-and-tear). Recovery required a Windows-side Docker Desktop restart. Not a code issue, but worth flagging for HAT prerequisites in `tests/HAT.md` (already noted: WARNING about pip install side-effects on httpx version).

### Technical

**1. The `_apply_override` dispatcher is now transport-aware, with a switch on `source.type`.** Future transports (e.g. WebSocket-based MCP if/when the spec adds one) must update both `_apply_override` and the transport contract in lockstep. Single mutation point is `_tool_provider.py:60-130`; if F7+ adds a transport, this is an architectural seam to track.

**2. `bearer_token` → `Authorization: Bearer <token>` translation couples schema field name to wire-protocol header name.** If the MCP spec adds DPoP or mTLS-style auth, the schema and translation widen together. Document in `_apply_override`'s docstring beyond the current note.

**3. F4 task-pinning trade-off is unfixed and now compounded.** Pool entry's OAuth provider + override material both pin to FIRST acquire's `(csid, tcid, source_override)` for the entry's lifetime (default 5min). Mid-session edits don't take effect until idle reap. Cross-session warm-pool routing still depends on F5's "most-recently-active session fallback." Re-keying the pool on `(agent, source, csid)` fixes both — but it's an F4 contract change requiring its own dedicated flight.

**4. OAuth-401-at-build collapses into failure class #2** (cycle-2 H1). Diagnostic name "failed to connect" rather than "requires authorization" remains lossy. F7 (inspector) is exactly the surface where the typed diagnostic matters most — extending `list_tools` and `connect` with `except* OAuthFlowError` translation should be in F7's scope.

### Documentation

**1. F2 transport contract document missing.** A `the_one/mcp/README.md` section titled "Transport contract: source.secrets is a flat kv table" would have been the load-bearing reference document that prevented A4. Routine maintenance.

**2. HAT-vs-integration-test taxonomy needs explicit naming.** The codebase's drift from F4/F5 onward conflated "automated regression scaffold under realistic conditions" with "Human Acceptance Test." The agentic-workflow SKILL.md is clear; the project precedent eroded it. Routine maintenance + a `agents.md` testing-conventions section.

**3. `agents.md::Project Conventions` 5th convention `same-task-anyio-cm-ownership`** still deferred from L6. F4's worker-task pattern + F5's verbatim subclass override + F6's per-tool-dispatch ContextVar bind are all variations on the same theme; the convention writes naturally given F6's example.

**4. F5 → F6 carry-forwards table in `the_one/mcp/README.md`** still pending (note: `_drive_flow` already-satisfied per Phase 1b reconnaissance — surface this in the table so future readers don't redo the recon).

**5. `provider_factory.py` flowchart docstring** for manual-vs-DCR flow still pending from L6.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| **L4 folded into L2** | Test-fortification surface fits inside L2's `TestMCPToolProvider` class; cycle-1 expanded inventory absorbed all 5 failure classes plus 64-char ceiling + collision step-trace + duplicate-source-id. | **Yes** — when a leg is "test fortification" with no production code, default to fold into the leg whose tests are the natural home. Codify in `flight/SKILL.md` or `leg/SKILL.md`. |
| **L5 misframed as automated pytest; corrected mid-execution** | F4/F5 precedent had drifted from the agentic-workflow SKILL.md HAT contract; F6 inherited and amplified. User push-back ("the hat is supposed to be human") corrected the framing; `tests/test_mcp_attach_hat.py` deleted; `tests/HAT.md` rewritten as clean human procedure. | **NO** — this should not be standardized. The cleanup recommendation is to retroactively reframe F4 + F5's "Tier-1 automated HAT" as "Tier-1 integration test" in their flight artifacts (or file the rename as routine maintenance). The flight-template HAT section should add a checklist gate "Is this Tier-1 HAT actually executable by a human, or is it pytest masquerading as HAT?" |
| **A4 — `_apply_override` flat-merge correction** | Cycle-1 medium #3's "REPLACE for streamable-http headers" disposition was structurally wrong against the F2 transport contract (would nuke OAuth-managed `Authorization` headers living in `source.secrets`). Both transports want overlay-merge flat. | **Yes (the post-fix shape)** — flat-merge into `source.secrets` is the only structurally coherent answer given the F2 contract. Future override schemas MUST flat-merge. Document via F2 transport contract section in `mcp/README.md`. |
| **L1 implementer hung 40min on full-suite pytest** | Run-the-full-suite-outside-docker reaches `test_mcp_pool.py` which blocks on aiosqlite worker-thread setup. | **Yes (as inverse rule)** — implementer-Developer prompts must specify "targeted tests only outside docker; full suite at flight-end inside `docker compose exec`." Carry to `agentic-workflow/SKILL.md` Process section. |
| **L2 leg artifact's targeted gate over-broad (A3)** | The leg artifact specified `tests/test_mcp_pool.py` in step 9's gate despite L0/L1 anomalies already documenting it as env-dependent. | **Yes** — leg-design-time citation audit must include "does each gate-listed test run cleanly in the environment we're using?" not just "does the file exist?" |
| **Docker Desktop wedge mid-HAT** | WSL2 backend hung after ~5 hours of session wear; required Windows-side restart. | Not a methodology issue; document as operator-side prerequisite in `tests/HAT.md`. |

## Key Learnings

**1. Citation audit must verify shape against consumer contract, not just symbol existence.** A4's root cause was that 2 cycles of design review + a Reviewer pass cited the transport modules by file/line but never grep'd the read-site. The proposed override shape was self-consistent with the (broken) tests but broke at the actual consumer. **Generalized recommendation**: extend the citation-audit pattern (mission-control PR #5 / F4 debrief R2) to require, for every helper that produces data consumed by another module, "grep the consumer's read-site and show how the proposed shape lands there."

**2. HAT execution catches what unit tests can't — and that's the point.** A4 escaped 3 review gates because it lived in the integration seam between `_apply_override`'s shape and the F2 transport's read shape. No mock could surface it; only a real bwrap spawn against a real MCP subprocess did. This is why HAT is non-negotiable for flights that touch shared-state contracts (override application, OAuth, sandbox profiles). **Generalized recommendation**: HAT should remain in scope for any flight that wires data across module boundaries (override → transport, agent → pool, etc.), even if the leg-design appears mostly mechanical.

**3. Methodology spec can be silently overridden by codebase precedent.** The agentic-workflow SKILL.md HAT definition was clear; F4/F5 drifted; F6 inherited the drift without questioning it. **Generalized recommendation**: when a leg artifact references "F4 precedent" or "F5 precedent" for a load-bearing concept (HAT framing, sandbox profile, lifecycle pattern), the design phase MUST verify that the precedent itself matches the methodology spec. If it doesn't, retrofit the precedent in the same flight or in routine maintenance — don't compound the drift.

**4. Phase 1b upstream reconnaissance pays dividends but must be exhaustive on contract surfaces.** F6's recon caught the `_drive_flow` already-satisfied case (saving wasted L-N work) but missed the F2 transport contract shape (causing A4). The recon checklist should explicitly include "for every helper that produces data consumed by another module, spot-read the consumer's contract surface." Already noted in §1 above.

**5. Implementer-Developer prompts need outside-docker test discipline baked in.** Three sequential hangs across L1, L2, L5 ran the implementer over the full pytest suite outside the dev container. Each hang cost real time (40min in L1's case). **Generalized recommendation**: leg-execution prompts MUST specify (a) targeted-tests-only outside docker, (b) explicit exclusion list (`test_mcp_pool.py` and any other env-dependent test file), (c) full-suite gate runs at flight-end inside `docker compose exec`. Codify in `agentic-workflow/SKILL.md`.

**6. The 2-cycle Architect cap forces escalation at the right pressure point.** F6 had 2 design-review cycles each at flight-design and at L1+L2 leg-design. The cap forced human-decision at every architectural pressure point (cycle-1 H1 metadata-hoisting, cycle-2 H1 list_tools-vs-MCPAuthRequired, L2 cycle-1 H1 streamable-http REPLACE-was-OVERLAY — all surfaced cleanly). The cap is doing real work; preserve it.

**7. The implementer-Developer + Reviewer separation is producing useful objective code review.** Reviewer (Haiku) over the L0-L5 delta caught no blocking or non-blocking issues — but the Reviewer's job is "do the changes match the spec," not "is the spec right against unspec'd consumer contracts." That gap is what A4 lived in. The Reviewer is doing its job; don't expect it to catch design-spec-vs-consumer-contract mismatches. Architect at debrief is the right layer for that retrospective.

## Recommendations

1. **Codify "verify schema matches consumer contract" in citation-audit.** Extend the `mission-control` flight + leg + agentic-workflow skills to require, for every helper that produces data consumed by another module: "grep the consumer's read-site and show how the proposed shape lands there." Generalizes F4 debrief R2.

2. **Codify "outside-docker targeted-tests-only" discipline in agentic-workflow SKILL.md.** Implementer-Developer prompts MUST list excluded test files (env-dependent ones) explicitly + specify full-suite gates run inside `docker compose exec` at flight-end. F1-F5 anomalies showed this; F6 anomalies A1/A2/A3 confirmed it; L3/L5 followed the discipline cleanly.

3. **Add an explicit HAT framing checklist gate to flight design Phase 5b** asking "Is the planned Tier-1 HAT actually executable by a human, or is it pytest masquerading as HAT?" + an architect-review item that pattern-matches against the agentic-workflow SKILL.md HAT contract. Retroactively reframe F4 + F5's "Tier-1 automated HAT" framing as "Tier-1 integration test" in their flight artifacts (routine maintenance — small doc edits).

4. **Codify "test fortification" leg fold-into-host-leg as default** in `flight/SKILL.md` or `leg/SKILL.md`. F6's L4 fold worked cleanly; the principle is "if a planned leg has no production code, default to absorbing its tests into the leg whose tests are the natural home."

5. **F7 (inspector) design phase must extend `list_tools` and `connect` with `except*` OAuth translation.** Cycle-2 H1's lossy diagnostic ("failed to connect" rather than "requires authorization") is acceptable for F6 but the inspector is exactly where the typed diagnostic matters. Track as a F7 design open question.

## Action Items

- [ ] **mission-control PR**: extend citation-audit pattern with "consumer contract shape verification" rule (Recommendation #1).
- [ ] **mission-control PR**: codify outside-docker targeted-tests-only discipline + env-dependent exclusion list in `agentic-workflow/SKILL.md` (Recommendation #2).
- [ ] **mission-control PR**: add HAT framing checklist gate to flight design Phase 5b (Recommendation #3).
- [ ] **mission-control PR**: codify test-fortification leg fold-into-host-leg default (Recommendation #4).
- [ ] **the-one routine maintenance**: F2 transport contract doc section in `the_one/mcp/README.md` (the load-bearing reference that would have prevented A4).
- [ ] **the-one routine maintenance**: 5th `same-task-anyio-cm-ownership` convention in `agents.md` (F4 + F5 + F6 carry-forward; L6 deferral).
- [ ] **the-one routine maintenance**: F5→F6 carry-forwards table in `the_one/mcp/README.md` including `_drive_flow` already-satisfied note.
- [ ] **the-one routine maintenance**: `provider_factory.py` flowchart docstring for manual-vs-DCR flow (L6 deferred).
- [ ] **the-one routine maintenance**: retroactively reframe F4 + F5 flight artifacts' "Tier-1 automated HAT" wording as "Tier-1 integration test" — small doc edits that align precedent with the agentic-workflow SKILL.md HAT contract.
- [ ] **F7 design**: extend `MCPClient.list_tools` and `MCPClient.connect` with `except* OAuthFlowError` translation so OAuth-401-at-build surfaces typed `MCPAuthRequired` rather than collapsing into `MCPConnectionError` (Recommendation #5; cycle-2 H1 carry-forward).
- [ ] **F7 / F8 design**: bake F4 task-pinning trade-off into operator-facing copy (Studio UI shows "MCP overrides apply on next agent build, not mid-session"). Do NOT attempt re-key fix in F7/F8 — separate dedicated flight if needed.
- [ ] **F8 design**: render against post-A4 flat-secrets shape; wire `__MASKED__` round-trip pattern for the override edit form (F1 sentinel preservation).
- [ ] **the-one local cleanup** (operator-side): delete `hat_agent_a` and `hat_agent_b` test agents (still in DB). Optional — not blocking.
- [ ] **F4-followup flight (if scope warrants)**: pool re-keying on `(agent, source, chat_session_id)` to fix both warm-pool override-pinning AND OAuth-broadcast cross-session routing. Out of F6 scope; track as F4-followup or new mission item.
