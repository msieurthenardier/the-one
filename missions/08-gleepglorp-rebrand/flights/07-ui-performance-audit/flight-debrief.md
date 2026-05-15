# Flight Debrief: UI Performance Audit

**Date**: 2026-05-15
**Flight**: [UI Performance Audit](flight.md)
**Status**: landed
**Duration**: 2026-05-14 — 2026-05-15 (planning span; L01 implementation 2026-05-14, L02-L06 same-day 2026-05-15)
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

F7's stated objective — measure browser-side performance against realistic usage and bring it under explicit budgets — is delivered. Headline numbers:

- **Heap-retention budget**: pre-fix +30.88% across 200 area-switches → post-fix +3.92% (first capture) → -14.62% (HAT re-run). The H1 admin-theme-toggle leak (statically-confirmed in L02, fixed in L03) was the dominant retainer. Budget threshold (≤20%) met with substantial margin.
- **F6 KI #5 closed**: mid-stream `usage` event emission via per-provider chunk-byte heuristic, threaded through a new `Agent.step(on_usage=…)` callback (interim-only contract).
- **F6.5 carry-forwards closed**: AI #5 (eager-resolve at session-join) via new `GET /api/agents/{name}/context-window` endpoint; AI #1 (`_init_provider_state` hook defusing OpenRouter "skip super" tripwire); AI #2 (Anthropic explicit no-op override with migration-template docstring); AI #3 (`_process_and_broadcast` live-read regression test); AI #6 (`make rebuild` Chromium-wipe note in agents.md).
- **Methodology substrate**: NEW `App.perf` JS module gated by `?perf=1`/localStorage with 7-method API surface; instrumentation hooks at the four critical interaction points (area-switch, session-join WS-to-DOM + DOM-to-paint, addMsg, telemetry-update); 4 MCP-runnable measurement scenarios documented in `the_one/agents.md` with operator-runnable recipes.
- **Pixel baselines**: final-mission regen at L06 HAT, 12/12 clean on rerun.

### Mission Criteria Advanced

| Criterion | Status | Notes |
|-----------|--------|-------|
| Browser-side performance measured under realistic use ... no unbounded growth | **Met** | -14.62% heap retention in HAT; well under the +20% budget |
| Per-area routing and navigation correctness | **Met** | L06 HAT MCP-verified deep-link to chat/studio/admin all activate correctly |
| Automated browser tests pass; pixel baselines regenerate cleanly | **Met** | 316 browser passing / 35 skipped; pixel 12/12 clean |
| No regression in M01-M07 functionality | **Met** | Broad pytest 1679p/4s/375d (+10 new tests; 0 regressions) |

## What Went Well

- **Cycle-1 design reviews caught real bugs in every implementation leg.** Across L01, L02, L04, L05 the cycle-1 spawn surfaced high-severity issues that would have cost rework: agents.md path mismatch + MCP-scope split (L01), OpenAI prefix-collision trap pattern (catching itself in a new context), Agent.step double-emission risk + AgentFactory store-wiring + Anthropic SDK abstraction-layer constraints (L04). The investment in design review pre-implementation continues to be the highest-ROI gate in the protocol.
- **L02-investigative → L03-conditional shape paid off.** L02 produced a code-reading-derived hypothesis table (8 candidates, 3 statically-confirmed) rather than running a long heap-diff campaign. L03 fixed the H1 candidate with a 22-LOC theme.js refactor. The post-fix capture validated the call. Investigative legs that are constrained to "ship a hypothesis table, no code" are cheap to design and high-signal.
- **The Developer/Flight-Director split was load-bearing.** L01 explicitly partitioned the leg into "Developer ships instrumentation + TBD-placeholder template" and "FD captures baselines via MCP" — Developer agents lack `mcp__chrome-devtools__*` access, so any leg requiring MCP work must define this boundary. The same pattern carried through L02 (FD validates the hypothesis table via MCP heap-diff) and L06 (FD executes the operator-delegated HAT via MCP).
- **`?perf=1`/localStorage gate is a reusable pattern.** Production runs pay zero measurement cost; the gate survives SPA navigation; the API surface is minimal. Architect recommends promoting to a documented convention for future debugging-only modules.
- **Investigative-leg static analysis beat dynamic measurement here.** L02's grep `addEventListener` vs `removeEventListener` (70 vs 5 callsites repo-wide) localized H1 cleanly; the FD's 10-cycle heap-diff was GC-dominated and inconclusive. The durable signal was L01's 200-transition baseline.
- **Cycle-2 skipping discipline held.** Three consecutive flights (F6, F6.5, F7) have applied "skip cycle-2 if changes are content-only / mechanical" without regrettable consequences. The pattern is operator-protocol stable.

## What Could Be Improved

### Process

- **Operator-delegated-HAT coverage gap on stateful scenarios.** L06 Scenario 8 (long-streaming usage progress + pre-first-turn `max:` populated) was NOT driven end-to-end because operator state was unseeded. Unit + integration tests cover the contract, but a human-eyes HAT would have caught e.g. an overlay-update jank or a `max:` rendering at wrong z-index. **Recommend**: formalize an FD-delegated-HAT protocol that requires explicit enumeration of "scenarios FD CAN cover (MCP + tests)" vs "scenarios FD CANNOT cover (visual confirmation requiring stateful operator setup)" with the latter explicitly carried-forward rather than silently passing.
- **Methodology fragility — MCP-only measurement.** F7 pivoted from manual DevTools recipes to MCP-driven recipes when the operator pre-installed Chrome DevTools MCP. The Playwright `CDPSession` parity recipes were "documented as fallback" but never actually written. If the MCP server breaks before a future perf flight, the methodology has to be re-derived. **Recommend**: F8 (or a maintenance flight) writes the Playwright equivalent of L01 Scenario 1 so the methodology survives MCP-server churn.

### Technical

- **`BYTES_PER_TOKEN_*` distributed across 4 provider files** vs consolidated on `LLMProvider`. Developer recommends consolidating; Architect recommends keeping distributed (per-provider variance IS the point). **Disposition**: keep distributed but tighten naming consistency (currently `BYTES_PER_TOKEN_OPENAI = 4.0` vs `INTERIM_USAGE_BYTE_THRESHOLD_OLLAMA` — promote the threshold to `LLMProvider.INTERIM_USAGE_BYTE_THRESHOLD = 200` since it's not provider-specific). ~10 min cleanup.
- **Anthropic uniform byte-heuristic** deferred the originally-spec'd "real `message_delta` numbers" approach. Anthropic SDK's high-level `client.messages.stream() + text_stream` iterator doesn't expose raw events. **Carry-forward**: a future provider-touching flight refactors Anthropic to raw-event iteration (`RawMessageDeltaEvent`); the byte heuristic stays as fallback for SDK abstraction layers that hide the primitive.
- **`/api/agents/{name}/context-window` instantiates a full Agent** via `AgentFactory.create()`. Currently called once per `session_joined` — free. If a future scenario calls this from a hot loop, the construction cost (LLM client + tool registry + MCP plumbing) becomes a concern. **Disposition**: add a `// TODO(perf): cache resolved value keyed by (agent_name, provider_config_version)` and revisit on demand. Do NOT optimize speculatively.
- **`session_joined` eager-fetch failure path has no test.** `chat.js` swallows fetch errors via `.catch(() => {})`. If the endpoint 5xxs or returns malformed JSON, the silent fallback could mask real bugs. **Recommend**: add a browser test stubbing `fetch` to 500; assert the overlay stays at 0 (not crashing). ~20 LOC.
- **`BYTES_PER_TOKEN` heuristic accuracy is unvalidated.** No test asserts that a 1000-token stream produces ~1000 interim-emitted `output_tokens`. The constants are tunable but un-validated.

### Documentation

- **"Live-read across lazy-resolver boundary" is now pinned by a test** (L05 `test_process_and_broadcast_live_read.py`) but the pattern itself isn't codified as a project convention. **Recommend**: promote to a CONVENTIONS section in `agents.md` or CLAUDE.md so future maintainers don't reinvent the eager-capture trap.
- **`AgentFactory(store=...)` store-wiring** was discovered at L04 implementation as a 404-trap when `store=None`. The factory's docstring should call this out; or add a `make_agent_from_request(...)` helper for endpoints that need a runtime Agent.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Cycle-2 design reviews skipped (5 of 6 legs) | All cycle-1 changes were content/wording corrections, no structural pivots | Yes — codify "skip cycle-2 if changes are mechanical only" guidance |
| L02 investigative-only contract (no code) | Investigation needed before targeted fixes; ships a hypothesis table | Yes — codify investigative-only legs as a first-class shape |
| Anthropic uniform byte-heuristic (vs spec'd `message_delta` approach) | SDK abstraction-layer constraint discovered at implementation | Codify "verify upstream API surface" recon step for provider-touching legs |
| FD/Developer split per-leg for MCP-dependent work | Developer agents lack MCP tools | Yes — codify the FD/Developer split shape |
| Operator-delegated L06 HAT | Operator: "you have access to all the data" | Yes — codify FD-delegated-HAT protocol w/ explicit "FD CAN vs CANNOT" enumeration |
| L01 cycle-1 corrected agents.md path | Recon caught path-as-repo-root vs `the_one/agents.md` discrepancy | Doc-level only; recon already canonical |

## Key Learnings

1. **Static-analysis grep beats dynamic measurement for "leak roots in event-listener-heavy code."** L02's hypothesis ranking was 70:5 callsite-ratio analysis; H1 was the standout immediately. The FD heap-diff (dynamic) was inconclusive at 10-cycle scale due to GC noise. The static-then-confirm-with-longer-scenario pattern is the right tool order.
2. **Lazy-resolver boundary mistakes are a recurring class.** F6.5 L04 HAT-cycle found one in `_process_and_broadcast` (eager-capture before resolver fired); F7 L05 pins the contract with a regression test. The category is "any value lazily resolved inside a coroutine MUST be read live by readers, never pre-captured at caller's function entry."
3. **MCP-dependent measurement is high-leverage but architecturally fragile.** The MCP server is a single point of failure for repeating the measurements. The flight's mission-fit was clean; the long-term maintainability hinges on Playwright parity recipes being captured before MCP-server churn.
4. **The 5-Developer-agent-spawns-per-flight rate is sustainable for this codebase.** F7 spawned design-review agents 5 times (L01-L05) and implementation agents 5 times; one cycle-2 in L01; one mid-leg API timeout in L01 recovered by post-hoc verification. The Developer/FD scope split kept each spawn focused.

## Test Metrics

Captured at debrief (post-L06, post-`fe630a9` analog — F7 commit `0e2078a`):

| Suite | Pass | Skip | Deselect | Wall | Pytest time |
|-------|------|------|----------|------|------|
| Broad pytest | **1679** | 4 | 375 | 108.45s | 97.28s |
| Browser (`-m browser`) | **316** | 35 | 1707 | 294.33s | 265.02s |
| Pixel (`-m pixel`) | **12** | 0 | 2046 | 23.87s | 19.32s |

**Comparison vs prior debriefs**:
- F6 close baseline: 1627p/4s broad; 315p/35s browser; 12/0 pixel
- F6.5 close baseline: 1669p/4s broad (+42 from F6 — mostly L01 mocked tests); 315/35 browser; 12/0 pixel
- F7 close: **1679p/4s broad (+10 from F6.5: L04's 9 + L05's 1); 316/35 browser (+1 from F6.5: L03's theme-toggle-cleanup); 12/0 pixel unchanged**

Wall times within noise across F6/F6.5/F7 baselines (~95-100s broad; ~260-270s browser; ~19s pixel). Zero flakes, zero regressions. Pre-existing 2 `AsyncMock` warnings on `test_provider_api::test_ollama_models` confirmed present unchanged — F6.5 carry-forward, not introduced by F7.

## Recommendations

1. **Promote the `App.perf` gate pattern** (URL + localStorage + `App.x.enabled` short-circuit) to a documented convention in `agents.md`. Future debugging-only modules (`App.debug`, `App.trace`) should mirror exactly. ~10 min.
2. **Capture Playwright `CDPSession` parity recipes** for at least L01 Scenario 1 in `agents.md` so the measurement methodology survives MCP-server churn. Schedule for F8 or a maintenance pass. ~1-2 hours.
3. **Formalize the FD-delegated-HAT protocol** as a documented skill addition: when an operator delegates HAT to FD, the leg artifact must enumerate scenarios FD can cover (MCP + test-suite verifiable) vs cannot (stateful visual confirmation), with the latter explicitly carried-forward rather than silently marked pass. Promote to skill update.
4. **Refactor Anthropic to raw-event iteration for real `message_delta` interim usage.** Replace estimation with provider-reported truth for one of the four providers. Defer to a streaming-API-touching flight or maintenance pass. Trade-off documented inline already.
5. **Codify the "live-read across lazy-resolver boundary" pattern.** Promote to a CONVENTIONS section + reference the F6.5 L04 HAT regression and the F7 L05 regression test. ~10 min doc work.
6. **Add browser test for `session_joined` eager-fetch failure path** (stub fetch → 500; assert overlay stays at 0 without crashing). ~20 LOC. Pin the silent-fallback contract.

## Action Items

- [ ] Promote `?perf=1`/localStorage gate to documented convention in `agents.md`
- [ ] Capture Playwright `CDPSession` parity recipe for L01 Scenario 1 (MCP independence)
- [ ] Formalize FD-delegated-HAT protocol in mission-control skill update
- [ ] Refactor Anthropic to raw-event iteration for real interim `message_delta` usage (deferred — schedule)
- [ ] Codify "live-read across lazy-resolver boundary" pattern in CONVENTIONS section
- [ ] Add browser test for `session_joined` eager-fetch failure path (~20 LOC)
- [ ] Tighten `BYTES_PER_TOKEN`/threshold naming + promote `INTERIM_USAGE_BYTE_THRESHOLD` to `base.py` (~10 min)
- [ ] Document `AgentFactory(store=...)` wiring requirement in factory docstring + agents.md
- [ ] Validate `BYTES_PER_TOKEN` heuristic accuracy via a parametrized test (1k-token stream → ~1k interim tokens)
- [ ] Investigate pre-existing `test_provider_api::test_ollama_models` `AsyncMock` warnings (F6.5 carry, unchanged)
