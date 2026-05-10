# Flight: Alignment — MCPs working well end-to-end

**Status**: ready
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] **#6** — Simplified inspector covers tools-list and tools-call subset (Test connection on source-edit page). Exercised end-to-end by L1 (HTTP) and L2 (stdio). F9 verifies that the operator-felt experience of "verify a configured MCP works before any agent attaches to it" is genuinely achievable on both transports without rework.
- [ ] **#7** — Agent attaches MCP sources; tools become callable. Exercised end-to-end by L3 (HTTP attach), L4 (stdio attach), L5/L6 (single-source chat), L7 (multi-source chat). F8 advanced the attach UI; F9 closes the loop on "tools become callable" via real chat exercise on both transports.
- [ ] **#8** — Stable namespacing for tool-name collisions. Exercised by L7 — operator attaches multiple MCPs that may expose overlapping short names; F6's `mcp__{source}__{tool}` scheme verified under live mixed-transport load.
- [ ] **#9** — Credentials never appear in plaintext outside the encryption boundary. Sanity-checked at every leg's save/reload + DOM/network inspection.
- [ ] **#10** — Graceful failure isolation. Exercised by L5/L6/L7 — operator scenarios that include token expiry mid-session, missing MCP source, server failing to start, server returning truncated/malformed payloads. Agent runtime continues; failures surface to operator without taking the chat session down.
- [ ] **#11** — Automated coverage. L8 final regression sweep verifies the full unit + browser suites against F8 baseline (1376 unit / 255 browser). Inline fixes during L1-L7 ship with their own minimal regression coverage.
- [ ] **#12** — Settings MCP section, simplified inspector, and Studio MCPs tab meet the M04/M06 design-language quality bar. **F9 IS the alignment surface** for this criterion. Per criterion phrasing ("without alignment-flight rework"): if F9 finds material design-language gaps requiring rework, criterion #12 is partially-met and the gaps document the gap; if F9 finds only cosmetic polish, criterion #12 holds.
- [ ] **#13** — MCP-protocol version pinned with explicit upgrade path; capability-gating degrades cleanly. Sanity-exercised whenever the live servers in L1-L7 announce capabilities outside the_one's pinned subset.

---

## Pre-Flight

### Objective

Mission-closing alignment flight: a multi-leg vibe-coding sweep across the seven core MCP operator workflows on both transports — create + test HTTP MCPs (L1) and stdio MCPs (L2), attach each transport to an agent with full per-source UI options exercised (L3, L4), use each transport in chat as a single-source agent build (L5, L6), and use multiple MCPs concurrently in a single chat session (L7) — with bugs, known issues, and UX rough edges fixed inline as they surface, then a closing leg (L8) that updates mission known-issues, runs the final regression sweep, and bundles any small carry-forwards. By flight close, MCPs work well end-to-end across both transports and Mission 7 is debrief-ready.

### Open Questions

- [x] Multi-leg vibe-coding shape vs single-leg HAT? → **Eight focused legs**, one per operator workflow surface. See Design Decision §1.
- [x] Fix-inline default vs defer-then-bundle? → **Fix inline by default**; per-anomaly decision for items F8 explicitly carved out. See Design Decision §2.
- [x] Stdio reference target for L2/L4/L6? → **Decide at L2 design time**, based on what L1 surfaces about which stdio target is most informative for the rest of the legs. Candidates: `@modelcontextprotocol/server-everything` via npx (broad surface, network-fetched), in-repo Python FastMCP fixture (hermetic but small surface), an operator-stack stdio MCP (most representative of steady state). See Design Decision §3.
- [x] Per-leg done-criteria? → **Operator-felt + caplog gate** (0 `MCPClient.disconnect` warnings across that leg's exercises). See Design Decision §4.
- [x] F8 carve-outs (per-agent OAuth re-auth, no-auth detection, `_pool.py` test isolation) if they surface? → **Decide per-anomaly mid-flight**. Default disposition: capture in flight log, scaffold the dedicated future-flight follow-up, continue. Inline absorption only if the fix is meaningfully smaller than F8 sized them and unblocks an in-flight leg's "working well" gate. See Design Decision §5.
- [x] Mission-close housekeeping placement? → **Explicit L8 closing leg**. Includes mission known-issues update + final regression sweep + small bundled carry-forwards. See Design Decision §6.
- [x] Inline-fix design review for known-problematic-paths? → **Spawn a quick architect pass** when an inline fix touches anyio task groups, cancel scopes, MCP client lifecycle, or OAuth flows; inline-only otherwise. See Design Decision §7.
- [x] Independent fresh-context review? → **Single bundled fresh-context review at flight close** across all F9 inline-fix LOC, before final commit. See Design Decision §8.
- [x] Code-change context isolation? → **All implementation work (file edits, code investigation, test additions) goes to subagents**. The Flight Director (parent context) drives vibing with the operator, triages, dispatches; subagents read code, write fixes, return summaries. Prevents rabbit-hole pollution of the parent context. See Design Decision §9.

### Design Decisions

**§1. Multi-leg vibe-coding shape (eight legs, one operator workflow each)** — operator-driven scope from the user. Each leg is a guided, interactive vibing session focused on one specific operator workflow surface. Legs are sequential (each leg builds operator confidence on the next surface) and HAT-style: setup → walk operator scenarios → capture issues → triage (fix-inline / absorb / defer) → fix or document → re-verify → close.

- Rationale: the seven core operator workflows (create+test on each transport, attach on each transport, single-MCP chat on each transport, multi-MCP chat) are the empirical surface area where M07 either feels good or doesn't. Splitting per workflow gives focused vibing context; bundling would blur the operator's signal across surfaces.
- Trade-off: more orchestration cost than a single HAT leg; each leg has its own design + close cycle. Justified by the F4-through-F8 empirical pattern that interactive HAT catches operator-felt issues no other test surface does.

**§2. Fix-inline default with per-anomaly triage** — operator-found bugs / known issues / UX gaps default to fix-inline within the leg that surfaces them. Triage decision per anomaly:

- **Inline fix** (default): bug or polish issue, fits the leg's surface, no cross-flight refactor implied. See Sizing Thresholds below.
- **Absorb into a sibling leg**: bug surfaces in L1 but the right fix lives in L3's surface — defer to that leg, log in flight log.
- **Defer to future flight**: matches an F8 carve-out (Design Decision §5), or the fix is mission-sized (F8-flight-sized), or requires a cross-cutting refactor. Document as known issue + scaffold a follow-up flight; continue F9.

The default is inline because the operator has explicitly committed appetite to "MCPs working well by end of flight". Triage prevents that appetite from turning F9 into a mission-sized rewrite.

#### Sizing Thresholds (one canonical set, applied across §2, §5, and Adaptation Criteria)

| Decision context | Threshold | Action |
|------------------|-----------|--------|
| Single inline fix in a leg | ≤ ~100 LOC | Fix inline (default). |
| Single inline fix touching a known-problematic-path (§7) | ≤ ~100 LOC | Architect pass (≤5 min) BEFORE fixing. |
| Single inline fix to F1-F8 functionality (regression-class) | ≤ ~200 LOC | Fix inline + architect pass + add to bundled fresh-context review queue. |
| Single inline fix to F1-F8 functionality (regression-class) | > ~200 LOC | Divert: defer to dedicated follow-up flight; do not ship F9 with new regressions. |
| F6 namespacing/criterion-#8 fix | ≤ ~50 LOC | Fix inline. |
| F6 namespacing/criterion-#8 fix | > ~50 LOC | Divert: dedicated future flight. |
| F8-carve-out absorb (per-anomaly per §5) | See §5 | Generally defer; absorb only for the specific cases §5 enumerates. |
| Cumulative inline-fix LOC across F9 (excluding the seven vibing-surface UI files) | ≤ ~600 LOC | Continue. |
| Cumulative inline-fix LOC across F9 (excluding the seven vibing-surface UI files) | > ~600 LOC | Divert: pause F9, audit cumulative scope with operator, decide per-anomaly which fixes to revert + defer. (~600 LOC is roughly 2x F8's L1+L2 inline-fix LOC of ~300 LOC each; cumulative scope above this is empirically mission-sized.) |

- Rationale: vibing is most valuable when the fix loop is short; defer is reserved for clear scope boundaries. The single threshold table prevents "wait, which threshold am I using here" pauses mid-vibing.
- Trade-off: inline fixes accumulate LOC across legs that lacks pre-design architectural review. Mitigated by Design Decision §7 (architect pass for known-problematic-paths) and Design Decision §8 (fresh-context review at flight close).

**§3. Stdio reference target — in-repo Python FastMCP fixture as L2 default; L4/L6 may switch** — locking in the in-repo FastMCP fixture as L2's default removes the "L2 design figures it out" hidden-prereq risk (npx availability, bubblewrap `node` allowlist, network egress for npx fetch — none of which are pre-verified). L4 and L6 may switch to a different stdio target if L2's signal makes one obviously more informative:

- **L2 default — in-repo Python FastMCP fixture**. Hermetic, deterministic, lowest-friction; whatever stdio fixture the test suite already uses (verified at L2 setup). Surface is small but it's enough to validate "create + Test + tools-list + capability flags + sandbox spawn + idle-TTL" — which is L2's job.
- **L4/L6 alternative — `@modelcontextprotocol/server-everything` via `npx`**. Broad tool surface (echo, add, longRunningOperation), maximally representative of "real third-party stdio MCPs". L4/L6 may switch to this if L2's vibing makes a strong case (e.g., FastMCP fixture's surface is too narrow to exercise sandbox + idle-TTL realistically). Switching requires a one-time prereq verification: `node`/`npx` available in dev container, bubblewrap profile allows `node` exec, network egress allowed for npx fetch.
- **L4/L6 alternative — an operator-stack stdio MCP**. Whatever the operator actually plans to use day-to-day (e.g., filesystem MCP, sqlite MCP). Most representative of steady state; reserved for L4/L6 if the operator wants to vibe attach + chat against their real-world target.

- Rationale: L2 needs a stdio target with low setup cost so the leg's vibing surface is "create + test + sandbox + idle-TTL", not "wrestle the sandbox into running node". The FastMCP fixture is already in the test suite; using it for L2 vibing piggybacks on existing infra.
- Trade-off: FastMCP fixture's small surface may not surface every stdio-specific bug the operator's real-world target would. Mitigated by L4/L6 switch path. If L2 vibing reveals zero stdio issues but the operator suspects there are some, L4/L6 should switch to a higher-surface target.

**§4. Per-leg done-criteria: operator-felt + caplog gate** — each leg closes when:

1. **Operator-felt**: the operator subjectively reports "this works well" for the leg's workflow. Subjective is the design intent — alignment is about feel, not just function.
2. **Caplog gate (HAT-only, F6 baseline pattern)**: across the leg's HAT exercises (operator-driven scenarios, NOT inline-fix unit tests), `caplog` count of `MCPClient.disconnect` warnings = 0. Measured against the F6 Tier-1 HAT baseline pattern (which explicitly verified 0 across "3 agent builds, 2 tool calls, and 1 full lifespan shutdown_drain" — see mission.md known-issue closure note). F8 didn't explicitly re-assert this number for HTTP-only paths but no regressions were noted; F9's L2/L4/L6 stdio-path measurements are the first stdio re-assertion since F6, so an anomaly here is high-signal (potential regression in stdio teardown since F6).

A leg can close with documented anomalies in the flight log if the anomaly was triaged to "defer" (per Design Decision §2) AND the operator-felt gate still holds for the in-scope workflow.

- Rationale: the caplog gate has paid off across the prior six MCP flights; folding it into per-leg close-out keeps the canary live throughout F9 instead of only at L8. HAT-only scope matches the F6 baseline.
- Trade-off: minor instrumentation overhead per leg. Acceptable.

**§5. F8 carve-out policy — defer, with one realistic absorb candidate** — when a leg surfaces work that F8 explicitly carved out, triage at the time:

- **Defer (default for all three F8 carve-outs)**: per-agent OAuth re-auth + per-(agent,source) credential storage (F8 sized at 4-5 legs / 1500-2000 LOC + binding HAT — no scaffolding to amortize against); SDK anyio cross-task cancel-scope leak / no-auth-server detection (genuinely complex per F6/F6.6/F8 logs; needs design choice between two architectural shapes); `_pool.py` test isolation / `_shutting_down` flag leak (pre-existing; cross-cutting refactor). Capture anomaly in flight log + scaffold the follow-up flight in mission #7's known-issues or as a post-mission successor planning surface; continue F9. **The absorb branch is empirically unreachable for these three** — F8's sizing reasoning was sound, and F9 is alignment-sized, not mission-sized.
- **Absorb (rare, single realistic candidate)**: the typed `MCPInitializeTimeout(MCPConnectionError)` exception (F8 debrief recommendation 4) — staged for L8 per Design Decision §6, with the contract-audit work scoped explicitly there. If a leg surfaces it as blocking before L8, it can be pulled forward with an architect pass per §7.
- **Other inline absorbs**: bugs/UX/polish that don't match an F8 carve-out follow §2's standard inline-fix path with the Sizing Thresholds table.

- Rationale: F8's carve-out reasoning was sound; F9's appetite is "MCPs working well", not "rebuild the carve-outs". Honest naming of which absorbs are realistic (one) prevents §5 from promising an absorb branch that never fires.
- Trade-off: a leg's operator-felt gate may genuinely fail because of an F8 carve-out (e.g., L5 chat session needs token re-auth and the per-agent re-auth flow doesn't exist). That leg closes with the workflow-class in known-issues and a documented "this surface needs the deferred follow-up flight to ship before it works well." F9 still lands; mission close acknowledges the gap.

**§6. Explicit L8 closing leg** — mission-close housekeeping lives in a dedicated final leg with three sub-deliverables:

1. **Mission known-issues update** — land entries in `mission.md` Known Issues reflecting F8's debrief delegation: F8 internally tracked A2/A3/A6-part-2 as resolved and A1/A4/A5/A6 as ongoing, but most of these were never written into mission.md's Known Issues (which currently has only the F2-era disconnect-noise close and the F6.5-era truncation entry). L8 lands new entries for the still-ongoing items (`_pool.py` test isolation; per-agent OAuth re-auth gap; no-auth-server detection / anyio cancel-scope leak); silently absorbs the resolved-but-never-listed ones; adds any F9-surfaced known issues that were triaged to "defer."
2. **Final regression sweep** — full unit suite + full browser suite. Verification command for the unit sweep: `docker compose exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py` (the `--ignore` matches F8's baseline measurement which excluded `test_mcp_pool.py` per Anomaly A1 — see F8 debrief Test Metrics line 44). Browser sweep: `docker compose exec the-one pytest tests/browser/ -q --timeout 120 -m browser`. Diff against F8 baseline (1376 unit pass / 255 browser pass / 43 pre-existing browser flakes); any net-new failure is a regression and must be fixed before mission close.
3. **Optional small bundled carry-forwards** — items that pair naturally with closing housekeeping. Bundle is pruned at L8 design time based on what survives L1-L7 inline fixes. Candidate (single, named): the typed `MCPInitializeTimeout(MCPConnectionError)` exception. **Sizing audit (architect-verified)**: ~30-50 LOC of code change (`errors.py` +5 for the subclass, `client.py:294,316` +4 for raise sites, `api.py:951-984` +10 to replace the message-pattern guard, `tests/test_mcp_client.py:411,444` +10 to update string-asserting tests) PLUS a non-trivial cross-flight invariant audit driven by the mission's `MCPClient` exception-translation contract (~41 consumer sites in `the_one/`, ~44 in `tests/` — most won't change because subclass-of-`MCPConnectionError` preserves catch-by-base, but the audit itself is the work) PLUS updating mission.md's exception-translation contract phrasing to allow subclasses. Total: tractable but not "trivial". L8 design pass decides fold-in vs punt-to-dedicated-tiny-flight at the time, weighing audit complexity against the operator's appetite for L8 to close cleanly.

- Rationale: separating housekeeping from vibing keeps L7 focused on the multi-MCP operator experience; a dedicated L8 gives a clean mission-close gate that can be signed off independently.
- Trade-off: one more leg in the count. Justified by clarity.

**§7. Architect pass for known-problematic-paths during inline fixes** — when an inline fix during any leg touches code in this list of known-problematic-paths, spawn a quick architect pass (≤5 min, single agent invocation, no full design review cycle) before implementing:

- `mcp` SDK anyio task groups, cancel scopes, transport-stack lifecycle (`MCPClient._open_*_transport_stack`, `disconnect`, `connect`)
- OAuth flows (`oauth/`, `_pool._entry_worker` synthetic-csid paths, `MCPSourceTokenStorage.set_tokens`)
- Pool worker spawn-path / `_shutting_down` flag / pool eviction
- `MCPToolProvider.get_tools_for_agent` filter / namespace prefixing
- Resolver dispatch (`tool_configs` × `tool_overrides` × `mcp_overrides`)
- **`the_one/mcp/errors.py` exception hierarchy** — adding/removing/renaming a typed exception risks the mission's `MCPClient` exception-translation contract (cross-flight invariant per mission constraints). The architect pass verifies the change preserves the contract or surfaces a contract-amendment requirement.

**Underlying principle** (use this when the enumerated list isn't an obvious match): any path where an inline fix could mutate a cross-flight invariant or known-fragile dependency lifecycle gets the architect pass. The list above is empirically-grounded; expand it with flight-log rationale when a new pattern is discovered.

Inline-only (no architect pass) for: UI/CSS/JS, copy edits, simple validation messages, browser test additions, error-message wording, accessibility attribute additions.

- Rationale: F8 debrief recommendation 5 — "for inline fixes that touch known-problematic SDK paths, spawn a quick architect pass even mid-HAT". The Phase A.5 wasted attempt in F8 L4 cost ~45 min; a 5-min architect pass would have caught it. Selective application keeps the pattern cheap.
- Trade-off: judgment call about what counts as "known-problematic". The principle + enumerated list together give the boundary; expand only with flight-log rationale.

**§8. Single bundled fresh-context review at flight close** — before the final commit, spawn a fresh-context Sonnet code reviewer over the full F9 inline-fix LOC across all legs. Pattern is the F6.6 + F8 precedent: the inline-fixer is too close to immediate problems and misses things a clean-context reviewer catches (F8: the `MCPConnectionError` token-clear path being too broad).

- Rationale: amortizes review cost across all eight legs (vs per-leg review which triples orchestration overhead). The reviewer reads the whole F9 diff against main and challenges decisions; high-signal-to-noise per orchestration step.
- Trade-off: a per-leg blind spot can persist for several legs before being surfaced. Mitigated by Design Decision §7 (architect pass for known-problematic-paths catches the highest-stakes blind spots earlier).

**§9. All code-change work delegated to subagents (parent context isolation)** — the Flight Director (parent context driving operator vibing) does NOT do file edits, multi-file code reads, or extended bug investigation directly. All such work goes to subagents via the Agent tool. The parent context only sees the subagent's return summary (file paths + brief description of what changed + LOC count + any notes the subagent flagged), not the full diff or investigation traces.

**What goes to subagents:**
- **Inline fixes** — when triage says "fix inline", spawn a subagent with the bug description, target file(s), and acceptance criteria. Subagent reads relevant code, makes the edit, returns a summary. Parent stages the diff for the operator's re-verification.
- **Bug investigation** — when an anomaly's root cause is unclear ("operator clicked Test, popup didn't open, no error in console"), spawn a subagent to investigate in isolation (read the relevant JS, trace the event handler chain, check the API response). Subagent returns a diagnosis + recommended fix shape; parent decides triage from the diagnosis without reading the investigation trace.
- **Test additions** — regression coverage for inline fixes goes to a subagent that knows the codebase's test patterns.
- **Architect passes (per §7)** — already subagent-based; no change.
- **Fresh-context flight-close review (per §8)** — already subagent-based; no change.

**What stays in parent context:**
- The vibing scenarios and operator dialogue
- Triage decisions (inline-fix / absorb / defer) and their rationale
- Flight log entries
- Subagent return summaries (not their working memory)
- Cross-leg state (which legs landed, cumulative inline-fix LOC tally for §2's threshold check, the L8 review queue)

**Subagent invocation pattern**: each spawn carries the bug description, target file(s) + line ranges, the acceptance criterion ("re-verify by re-walking Scenario N — operator should see X"), and any §7 architect-pass output if it preceded the fix. Subagents return a structured summary: "Modified `path/to/file.ext` at line N: changed X to Y. Added 12 LOC. No tests changed. One open question: …".

- Rationale: the F8 debrief flagged the Phase A.5 wasted attempt as ~45min of context cost on a rabbit hole the parent shouldn't have entered. Anchoring the parent in vibing-and-triage and pushing all implementation depth to subagents prevents the parent from getting pulled into multi-file investigation traces or false-start fix attempts that don't belong in the operator-facing dialogue. Compounded across 8 legs, the savings are large; the operator's vibing rhythm stays uncluttered.
- Trade-off: each inline fix incurs subagent-spawn overhead (~10-30s of dispatch + return summary). Acceptable; the alternative is the parent context drifting into investigation rabbit-holes that compromise the leg's vibing focus and the L8 final-review reviewer's signal-to-noise.
- Boundary case: trivial single-line edits (typo fix in a JS string, color-token swap) are arguably below the spawn-overhead threshold. Default still goes to subagent for consistency; the Flight Director may inline-edit only when the change is unambiguously ≤2 lines AND the file is already in the parent's recent context window. This boundary is auditable in the flight log.

### Prerequisites

- [x] F8 landed and merged to main (debrief: 2026-05-09).
- [x] All F1-F8 deliverables in production: encrypted source persistence (F1), MCP client lifecycle for stdio + streamable-http (F2), bubblewrap-backed sandbox layer (F3), idle-TTL pool (F4), OAuth 2.1 + PKCE end-to-end (F5), per-agent attach + tool-routing (F6), Test connection button + DCR-only OAuth surface (F6.5), connect-time 401 translation (F6.6), Studio MCPs tab + capability flags + collapsible schemas (F8).
- [ ] Operator's existing Cloudflare API MCP source (`https://mcp.cloudflare.com/mcp`) state confirmed — at L1 setup, operator decides whether L1 starts against a fresh-DCR + first-time-consent flow (delete + re-create the source) OR against the F8-HAT-leftover Cloudflare source (which exercises refresh-token rotation instead). Both are valuable; L1 design pass picks one based on which signal is more important to vibe.
- [x] Stdio MCP target identified — in-repo Python FastMCP fixture as L2 default per Design Decision §3 (verified at L2 setup; L4/L6 may switch).
- [ ] Browser test baseline pinned — F8 baseline of 1376 unit pass / 255 browser pass / 43 pre-existing browser flakes is the diff target; no new pre-flight measurement needed (F8 was the immediately-prior flight).
- [ ] Warm-pool clear before L1 — `docker compose restart the-one` to drop any in-memory pool entries from prior sessions. Cheaper than `make rebuild`; achieves the "no warm state masking first-time flows" intent without throwing away the dev DB. **Persistent state (OAuth tokens, registered sources) is NOT reset by this** — operator-driven decisions about Cloudflare source state are handled in the prior prerequisite, not by environment reset.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [ ] Prerequisites verified (one operator-side check at L1 setup; stdio target picked at L2 design)
- [x] Validation approach defined (per-leg operator-felt + caplog; flight-close regression sweep + bundled fresh-context review)
- [ ] Legs defined (eight legs sketched; per-leg `/leg` design happens just-in-time)

---

## In-Flight

### Technical Approach

Each vibing leg follows a structured procedure:

1. **Setup** — operator confirms environment ready (dev server up, MCP source for the leg's transport registered, agent for the leg's scenarios prepared). Architect-spawned `/leg` design produces the leg artifact with a numbered list of operator scenarios for that surface.
2. **Walk operator scenarios** — operator works through the scenarios in the leg's enumerated list. Each scenario has an expected operator-felt outcome (e.g., "Test button shows tools list within 2-5s on first click after consent").
3. **Capture issues** — anomalies, bugs, UX gaps, polish opportunities surfaced during the walk get captured in the flight log under that leg's section. Each gets triaged per Design Decision §2 (inline fix / absorb / defer).
4. **Fix or document** — inline fixes implemented in the same leg context; absorb-decisions logged with the target leg; defer-decisions logged with follow-up flight scaffolding.
5. **Re-verify** — operator re-walks the scenarios that touched the fix; caplog gate cleared.
6. **Close leg** — operator-felt sign-off + caplog count verification + flight log entry.

For inline fixes touching known-problematic-paths (Design Decision §7), the agent spawns a quick architect pass before implementing.

L8 closes the flight with mission-close housekeeping (Design Decision §6) and the bundled fresh-context review (Design Decision §8).

### Checkpoints

- [ ] **L1 landing**: HTTP MCP source create-from-scratch + Test → tools-list with capability flags + collapsible schemas → save → reload all behave per design language. Operator-felt clean. Caplog gate clean.
- [ ] **L2 landing**: Stdio MCP source create-from-scratch + Test → tools-list under sandbox + idle-TTL plumbing → save → reload all behave per design language. Operator-felt clean. Caplog gate clean. Stdio target selected and documented.
- [ ] **L3 landing**: Attach an HTTP MCP source to an agent via the agent-editor MCPs tab; toggle per-tool enabled/disabled; per-source overrides exercised; save → reload preserves state. Operator-felt clean. Caplog gate clean.
- [ ] **L4 landing**: Attach a stdio MCP source to an agent analogous to L3. Operator-felt clean. Caplog gate clean.
- [ ] **L5 landing**: Single HTTP MCP attached to an agent → start chat → agent calls MCP tool → result surfaces in chat → operator-felt confidence the tool is callable from chat. Caplog gate clean.
- [ ] **L6 landing**: Single stdio MCP attached analogous to L5. Caplog gate clean.
- [ ] **L7 landing**: Multi-MCP attached (mixed HTTP + stdio) → chat exercises tools across both servers in a single session → namespace collision (if any of the test servers' tools share short names) handled cleanly → graceful failure if one server fails mid-session. Caplog gate clean.
- [ ] **L8 landing**: Mission known-issues updated; full regression sweep matches or beats F8 baseline (1376 unit / 255 browser / 43 pre-existing flakes); bundled carry-forwards (if any) landed; bundled fresh-context review approves the full F9 diff.

### Adaptation Criteria

**Divert if** (see Sizing Thresholds table in §2 for the LOC bars):
- Any leg surfaces a regression in F1-F8 functionality that cannot be cleanly fixed inline. Per Sizing Thresholds: > ~200 LOC fix, requires cross-flight refactor, requires schema migration. Land in known-issues + scaffold dedicated follow-up flight; do not ship F9 with new regressions to prior-flight functionality.
- Cumulative inline-fix LOC across legs exceeds the cumulative ceiling per Sizing Thresholds (~600 LOC outside the seven vibing surfaces' UI files). Pause F9, audit cumulative scope with operator, decide per-anomaly which fixes to revert + defer.
- L7 multi-MCP reveals a tool-name collision that F6's `mcp__{source}__{tool}` namespacing scheme does not cleanly handle (e.g., source-name slugify collision) and the fix exceeds the per Sizing Thresholds criterion-#8 bar (> ~50 LOC). Defer to future flight.
- An F8 carve-out item blocks a leg's operator-felt gate. Per §5: defer is the default; the leg's offending workflow lands in known-issues with documented "needs the deferred follow-up flight to ship before it works well"; F9 continues.

**Acceptable variations**:
- Leg ordering can swap if operator's situation makes a different order more informative (e.g., L2 before L1 if Cloudflare token expired and stdio MCP is faster to set up).
- L8's bundled-carry-forwards list can shrink to zero if L1-L7 absorbed the candidates inline.
- Per-leg architect pass for known-problematic-paths can be inline (≤5 min, single agent prompt) rather than a full design-review cycle — the criterion is "did the architect read the relevant files and flag the risk", not "did we run the formal design review process".
- Stdio target can change between L2 and L4/L6 if L2's vibing surfaces a strong reason to switch (e.g., the chosen target turns out to have a flaky handshake; switch to `mcp-server-everything` for L4/L6).

### Legs

> **Note:** Tentative. Each leg is `/leg`-designed just-in-time before its session, since vibing-leg scope is shaped by what the prior leg surfaced.

- [x] `01-http-mcp-create-and-test` — Create + test an HTTP MCP source end-to-end (Studio MCP Servers area; OAuth flow exercised; capability flags + collapsible schemas verified). Cloudflare API MCP as primary target. **Landed 2026-05-09**: 9 subagent batches; 7 anomaly classes surfaced + fixed inline; F8 A6 absorbed via Shape C (HTTP-level pre-flight detection). Caplog clean; ~409 LOC production outside vibing surfaces (under §2 cumulative ceiling).
- [ ] `02-stdio-mcp-create-and-test` — Create + test a stdio MCP source end-to-end (sandbox spawn + idle-TTL + Test connection). Stdio target picked at this leg's design time per Design Decision §3. ~1-2h interactive + inline fixes.
- [ ] `03-http-mcp-attach-to-agent` — Attach the HTTP MCP from L1 to an agent via the Studio agent-editor MCPs tab; exercise per-tool enable/disable, per-source overrides, save/reload, hash-routing. **Cross-cut verification**: tool-list consistency between the source-edit Test view (L1's surface) and the agent-attach available-tools list (L3's surface) — flushes any L1 inline fix that didn't propagate to the attach path. ~1-2h interactive + inline fixes.
- [ ] `04-stdio-mcp-attach-to-agent` — Attach the stdio MCP from L2 to an agent analogous to L3. ~1-2h interactive + inline fixes.
- [ ] `05-http-mcp-in-chat` — Single HTTP MCP attached → chat session → tool-call → result rendering → operator-felt confidence in the chat path. Includes graceful-failure scenarios (token expiry mid-session, server returning malformed payload, server unreachable). ~1-2h interactive + inline fixes.
- [ ] `06-stdio-mcp-in-chat` — Single stdio MCP attached analogous to L5. Includes sandbox-specific failure scenarios (process crash mid-call, idle-TTL reap mid-session). ~1-2h interactive + inline fixes.
- [ ] `07-multi-mcp-in-chat` — Multi-source agent (mixed HTTP + stdio) → chat session exercising tools across both → namespace collision handling → graceful failure if one server fails mid-session. **Collision exercise**: L7 design picks whether to (a) accept whatever collisions the L1+L2/L4 servers happen to expose (may be zero — Cloudflare API tools and FastMCP fixture tools have no obvious short-name overlap), or (b) deliberately engineer a collision (e.g., attach two stdio MCPs that both export `read_file`) to actually exercise mission criterion #8. Operator picks at L7 design time based on appetite for engineered scenarios vs. naturalistic vibing. ~1-2h interactive + inline fixes.
- [ ] `08-mission-close` — Mission known-issues update + final regression sweep + small bundled carry-forwards (≤30 LOC each) + bundled fresh-context Sonnet review across the full F9 diff. ~1-2h.

---

## Post-Flight

### Completion Checklist

- [ ] All 8 legs completed (or any deferred-due-to-divert deferrals captured + follow-up flights scaffolded)
- [ ] All inline fixes merged
- [ ] Full unit suite passes (modulo pre-existing knowns); diff against F8 baseline 1376 pass shows no net-new regressions
- [ ] Full browser suite passes (modulo pre-existing flakes); diff against F8 baseline 255 pass / 43 fail shows no net-new regressions
- [ ] Caplog count of `MCPClient.disconnect` warnings = 0 across all leg HATs
- [ ] Mission known-issues section in `mission.md` reflects post-F9 state (closed: F1-F8 anomalies resolved this flight; added: F9-deferred items with follow-up scaffolding)
- [ ] Bundled carry-forwards (if any) landed
- [ ] Fresh-context Sonnet review approves the F9 diff (`[HANDOFF:confirmed]`)
- [ ] CLAUDE.md / agents.md updates for any new operator-facing conventions surfaced during F9 vibing
- [ ] Mission #7 ready for `/mission-debrief`

### Verification

- **Per leg**: operator-felt sign-off on the leg's enumerated scenarios + caplog gate clean. Captured in flight log per leg.
- **L8 regression sweep**: `docker compose exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py` (full unit, matching F8's baseline measurement which excluded `test_mcp_pool.py` per Anomaly A1) + `docker compose exec the-one pytest tests/browser/ -q --timeout 120 -m browser` (full browser); diff against F8 baseline.
- **Bundled fresh-context review**: spawn a Sonnet reviewer with no prior F9 context; reviewer reads the full F9 diff against main; reviewer approves or flags issues for inline-fix before final commit.
- **Mission criteria**: criteria #6, #7, #8, #9, #10, #12, #13 advanced as exercised. Criterion #11 advanced via L8 regression sweep + any inline-fix tests.
- **Mission close gate**: F9 is the last flight before `/mission-debrief`; F9's verification IS the practical mission-close gate. If F9 finds blocking issues that defer to future flights, mission #7 ends with explicit known-issues for those items but closes operationally.
