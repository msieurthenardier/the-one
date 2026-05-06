# Flight Debrief: MCP Client Foundation — stdio + Streamable HTTP

**Date**: 2026-05-06
**Flight**: [MCP Client Foundation](flight.md)
**Status**: landed
**Duration**: 2026-05-06 (planning + execution + L7 HAT + post-flight retrofit, single working day)
**Legs Completed**: 7 of 7 autonomous (L1, L2, L3, L4, L5, L6a, L6b) + 1 of 1 optional (L7 HAT) + 1 post-flight retrofit (admin→studio relocation)

## Outcome Assessment

### Objectives Achieved

The flight landed a thin async wrapper around the `mcp==1.27.0` SDK with all 12 design decisions honored in implementation. F2's deliverables in concrete:

- **`MCPClient` lifecycle** with explicit `connect()`/`disconnect()` plus async-CM convenience, fail-hard version handshake (narrower than SDK's `SUPPORTED_PROTOCOL_VERSIONS`), `tools` capability negotiation, F4-pool-compat properties (`is_alive`/`last_activity` aligned to `PtySession`'s naming), idempotent disconnect
- **Both transports** wired end-to-end: streamable-http via `streamable_http_client(url, http_client=...)` (the SDK's current API; not the deprecated `streamablehttp_client`), with production-vs-test-seam paths for header injection; stdio via `stdio_client(StdioServerParameters)` reusing the canonical `_ENV_ALLOWLIST` from `the_one/platform/env.py`
- **`list_tools()` + `call_tool()`** with full MCP semantics: input validation via jsonschema (transitive direct dep of `mcp==1.27.0`), text-block flattening + non-text content placeholders, `MCPCallError` on `isError=True`, `MCPToolNotFoundError` BEFORE wire call, full SDK error translation matrix (timeout / `McpError` / httpx / anyio) with explicit `UrlElicitationRequiredError` re-raise ordered before `McpError` (subclass-ordering invariant — discovered at L6b design review)
- **In-repo FastMCP test fixture** at `tests/fixtures/mcp/hello_server.py` with `make_mcp_app()` factory + module-level `mcp_app`, in-process ASGI testing via `asgi-lifespan` `LifespanManager` (no real socket binding for streamable-http tests)
- **F1 backfill**: `_validate_mcp_source_config` extended in L1 to validate `config.env: dict[str, str]` (mirrors the existing `headers` validation pattern)
- **Documentation**: 6 F2 contracts enumerated in `CLAUDE.md` and `the_one/agents.md` covering module placement, SDK pin, fail-hard policy, F4-pool compat invariants, env-var assembly, and dataclass shapes

Verification: 1169 unit + integration tests passing (1099 baseline + 70 net new); lint clean across all 7 legs; L7 HAT walkthrough validated the full F1+F2 stack end-to-end against the in-repo fixture.

### Mission Criteria Advanced

This flight contributes to two M07 success criteria:
- ✓ **Both transports defined in the current MCP specification supported** — F2 lands the client-side wrapper; runtime composition into agents is F6
- ✓ **Each layer of the integration has automated coverage** — F2 contributes the client-side connection lifecycle for both transports (4 unit + 13 lifecycle + 11 list/call_tool + 9 stdio + 8 streamable-http + 18 input-validation/error-paths + 14 integration = 70 net new tests)

The mission's spec-version-pinning constraint is also advanced: `_PINNED_PROTOCOL_VERSION = "2025-11-25"` is a module constant; the L1 tripwire test (`test_pinned_protocol_version_matches_sdk`) fires loudly on SDK upgrade drift; the upgrade procedure is documented in code.

## What Went Well

**Architecture**: the runtime foundation is structurally clean. Small public API surface (`MCPClient`, the 7-error family, `MCPTool`, `MCPToolResult`, `_PINNED_PROTOCOL_VERSION`, two timeout constants), narrow module boundary at `the_one/mcp/`, transport plug-ins isolated under `transports/`. F4/F5/F6/F7 all consume from a single point. PtySession naming alignment in §9 is genuinely load-bearing (F4 can build one reaper code path via structural typing across both client types).

**Design decisions held up**: 11 of 12 design decisions held cleanly through implementation. The one revision (§3 error hierarchy: `UrlElicitationRequiredError` is a subclass of `McpError`, not a sibling) was caught at L6b design review and absorbed via an explicit re-raise clause + regression test. No design decision required mid-flight rework.

**SDK probe + wheel-inspection recipe**: the flight-design Phase 1b reconnaissance pinned the SDK version, transitive deps, and protocol revision constants exactly. The reproducible recipe (`pip download mcp==1.27.0 --no-deps -d /tmp/mcp-wheel && unzip -p ...`) in flight-log.md Part C made re-validation trivial during implementation.

**L4 design review caught two real high-severity issues** before implementation: (1) `streamable_http_client` does NOT accept a `headers=` kwarg (only `http_client`), forcing the production path to construct its own httpx client; (2) the test seam path was dropping headers on the floor. Both fixed in the leg artifact, both validated by Option-C unit test (`test_production_path_constructs_client_with_assembled_headers`) that mocks the SDK functions and asserts the constructed httpx client carries the bearer header.

**L3 surfaced three SDK gotchas at design review** (factory-per-test for `StreamableHTTPSessionManager.run()` once-per-instance; `LifespanManager` for ASGITransport; `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)` for synthetic Host headers). All three were absorbed into the leg artifact; all three landed working on first implementation pass.

**Per-leg lint gate honored throughout**: every leg's flight-log entry confirms `Lint: clean (0 errors, 0 warnings)` before signaling `[HANDOFF:review-needed]`. F1 debrief's process improvement was mechanically enforced.

**L6 pre-split into L6a/L6b** was the right call: L6a (15 tests, happy-path) and L6b (18 tests, validation + error paths + non-text rendering) had structurally distinct concerns. Combined into a single leg, it would have been a 33-test commit with a fuzzy review focus. Pre-splitting let each leg's design review focus tightly on its concern.

**L4↔L5 swap (streamable-http first) validated**: in-process ASGI is structurally simpler than stdio subprocess management, and getting MCPClient's transport-agnostic plumbing exercised end-to-end before subprocess complications was the correct ordering.

**L7 HAT format effective**: lightweight 5-step + bonus binary go/no-go format surfaced a real defect (the disconnect-teardown noise) that no automated test caught. The structured-step format with bonus version-mismatch path is reusable for F3+ flights.

**Test count progression matched leg-artifact predictions exactly** through all 7 legs: 1099 → 1104 → 1117 → 1119 → 1127 → 1136 → 1151 → 1169. No surprises; no test-count drift caught at the flight-end Reviewer pass.

**Anchor-by-symbol-name citation convention adopted from leg 1**: F1 debrief's recommendation propagated cleanly. Zero stale-citation drift caught at design review (vs F1's 3+ drift fixes).

**The post-flight admin → studio retrofit was handled cleanly**: a single Developer-pass commit on the same branch, no leg artifact (sub-leg-sized work), captured in flight-log Decisions section, F1 retrospective + mission spec retrospective notes added, browser tests renamed via `git mv` (history preserved). The reversibility of the closure-mirror enumeration (admin→studio in one commit) is itself evidence the pattern is well-understood.

## What Could Be Improved

### Process

- **The disconnect contract said "never raises"; reality swallows `RuntimeError: generator didn't stop` on every disconnect cycle.** Captured as Anomaly A01. The `except Exception: logger.warning(...)` swallow is a workaround, not the design — `contextlib.AsyncExitStack` should have been the design from the start. Cosmetic now, will amplify under F4's pool eviction. **Recommendation**: F4 must bundle the AsyncExitStack refactor across `client.py` + both transport modules; do NOT carry the warning forward into F4.

- **L1's "match this docstring verbatim" prescriptions created review-cycle noise on small drift.** Every L1 review-cycle issue (test count off-by-one, missing `import pytest`, incoherent docstring update instruction) was a small mechanical drift between prescribed-text and reality. **Recommendation**: for skeleton legs that touch many files, prefer pattern-match instructions ("mirror the existing headers validation block, substituting field name") over verbatim-text prescriptions when the existing code is the source of truth.

- **L3's three SDK gotchas could have been caught at flight design**, not L3 leg design. The flight-design Phase 1b recon was thorough on imports/exports but didn't run the in-process ASGI path end-to-end. **Recommendation**: when a flight stakes integration tests on a specific SDK pattern (here: in-process ASGI lifespan-driven testing), the flight-design Phase 1b reconnaissance should include a 10-line "does this actually work" probe script, not just static wheel inspection. Catches three classes of gotcha (lifespan, host-validation, run-once-per-instance) for the cost of one test-script invocation.

- **L6a/L6b test-count math was unclear in the leg artifact** about rework-in-place vs add-new. The L2 `test_last_activity_updates_via_list_tools` was explicitly reworked in L6a (drops `pytest.raises(NotImplementedError)`), and the spec called it out — but the test-count delta math required parenthetical explanation. **Recommendation**: leg specs should always enumerate tests in three buckets — "new tests added," "tests reworked in place," "tests deleted" — rather than a single delta number.

- **L5 test-name inconsistency** (`_raises` suffix on some tests, not others) caught at review. Symptomatic of the leg artifact not pinning a naming convention up front. **Recommendation**: leg artifacts should declare a test-naming convention in their "Outputs" section when they introduce new test classes.

### Technical

- **`_DEFAULT = object()` sentinel** for timeout defaults (`client.py:54`) is invented; not consistent with the rest of the project's `None`-with-or-default pattern (e.g., `the_one/llm/ollama_api.py`). The choice was defensible but isolated. **Recommendation**: either document the sentinel pattern in `the_one/mcp/README.md` or refactor to match the project's `None`-with-or-default style. Low priority.

- **`App.adminFormHelpers` namespace consumed by Studio post-retrofit** (6 call sites in `static/js/areas/studio/mcp-server-editor.js` lines 284, 300, 313, 697, 763, 825). Cross-area coupling, not just a name. **Recommendation**: rename to neutral `App.formHelpers` OR re-home the helper module to `static/js/shared/form-helpers.js` and re-export under both namespaces during a migration window. Routine-maintenance candidate; not blocking.

- **`admin-` CSS class prefixes still in studio markup** (24 occurrences across mcp-server-editor.js + 4 in mcp-servers-grid.js: `admin-pf-row`, `admin-pf-input`, `admin-pf-select`, `admin-pf-password`, `admin-mcp-badge`, `admin-loading`, `admin-provider-empty`). Browser tests use `.area-studio` selectors but markup classes still carry `admin-` prefix. CSS rules also live under those `admin-` selectors — moving them is a follow-up commit, not a quick fix. **Recommendation**: routine-maintenance pass.

- **Two-path header injection in streamable-http transport** (production constructs new client; test path mutates existing client). Not debt per se — it's structural — but F5's OAuth flow will need to thread Bearer through the production path's `httpx.AsyncClient` constructor or extend `connect_streamable_http` to accept headers post-construction. **Recommendation**: F5 design must plan for this; consider an httpx native auth handler rather than static-headers-at-construction.

- **The `_test_http_client_override` test seam is module-level mutable global.** Three layers of hint that it's not production (underscore prefix, `__all__` exclusion, "TEST-ONLY" comment) — clean enough as a one-off. **Watch list**: if F5 (OAuth) introduces a similar transport-detail seam, extract a shared `the_one/mcp/transports/_test_seams.py` with documented patterns.

- **`UrlElicitationRequiredError` propagation tested for `call_tool` but NOT for `list_tools`.** The implementation DOES re-raise it from list_tools (`client.py:302-303`) but no test exercises that branch. **Recommendation**: add a 10-line mock-based test in `TestCallToolErrorTranslation` (or `TestListToolsErrorTranslation`); minor but documents the contract.

### Documentation

- **No `the_one/mcp/README.md` exists.** F3-F8 will read F2's contracts continuously and CLAUDE.md is getting dense. **Recommendation**: add `the_one/mcp/README.md` covering: test-seam pattern, F4-pool-compat invariants (with test names that lock each invariant), AsyncExitStack TODO + cross-link to L7 leg artifact + F4 fix plan, `_DEFAULT = object()` sentinel pattern, read-at-call-time invariant for both `_PINNED_PROTOCOL_VERSION` and timeout defaults, 2-layer flat-merge pattern for both transports, dead-yield-after-raise pattern in `_transport_connect`. Scope to runtime invariants; let CLAUDE.md keep cross-cutting policy.

- **The "admin = system settings vs studio = user-managed entities" UI placement heuristic is missing from project conventions.** F1's L5 chose admin placement at design time; only post-F2 (when operator-interaction frequency became concrete) did the mismatch surface. **Recommendation**: codify the heuristic explicitly in `the_one/agents.md` under a "UI placement conventions" section. This belongs in the project's own `agents.md`, not in mission-control's methodology docs — it's project-specific UX convention, not flight-control methodology.

- **The closure-mirror enumeration (4-times-applied) needs a registry helper.** Pattern has now landed: providers, tools-admin, mcp-sources-in-admin, mcp-sources-in-studio. **Strong recommendation**: extract a `defineSection(spec)` helper in `static/js/areas/_shared/section-registry.js` that takes `{id, label, area, fetch, render, hydrate, serialize, dirtyMode}` and registers all 18 touchpoints from one description. Codify before F8 (Studio MCPs override panel) lands a 5th call site. The retrofit's reversibility suggests the touchpoints are well-understood; extracting a registry now is low-risk.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `_DEFAULT = object()` sentinel for timeout defaults invented in L2 (not consistent with rest of codebase) | L2 spec ambiguity around "what if caller passes None for timeout?"; pre-decided too late | No — but document the rationale in `the_one/mcp/README.md` so future maintainers don't refactor it away |
| `streamable_http_client` does NOT accept `headers=` kwarg; production path forced to build its own httpx client | SDK shape verified at L4 design review; F2 design assumed `headers=` was passable | Yes — flight-design Phase 1b should run a 10-line "does this actually work" probe when integration tests stake on an SDK pattern |
| `UrlElicitationRequiredError` IS a subclass of `McpError` (flight design assumed sibling); explicit re-raise clause ordered before `except McpError` in both list_tools and call_tool | Caught at L6b design review via `issubclass()` probe | Yes — the subclass-ordering invariant should be called out explicitly in §3 of any future error-translation flight design |
| `asgi-lifespan>=2.0` and `pytest-timeout>=2.4` added to `[dev]` (unanticipated at flight design) | L3 design review surfaced LifespanManager need; L5 design surfaced subprocess-hang protection need | No — both are tactical; flag in F5 design as candidates for OAuth callback ASGI test reuse |
| Post-flight admin → studio relocation as a single Developer-pass commit (no leg artifact) | F1's L5 admin placement was a UX miss; sub-leg-sized work shouldn't carry a leg artifact | Yes — codify "post-flight retrofit" as a first-class change category in mission-control methodology (sits between leg and routine maintenance) |
| Disconnect raises `RuntimeError: generator didn't stop`; swallowed by existing `except Exception:` in disconnect | `@asynccontextmanager` + nested `async with` interaction with anyio task-group-managed CMs; not predicted at design | No — but the canonical fix (AsyncExitStack refactor) is captured for F4 and must not carry the warning forward |

## Key Learnings

1. **Flight-design Phase 1b reconnaissance should run a 10-line "does this actually work" probe** when integration tests stake on a specific SDK pattern. The wheel-inspection recipe is necessary but not sufficient. F2 caught L3's three SDK gotchas at leg-design review; an earlier probe would have caught them at flight design and reduced leg-design-review churn.

2. **The "admin = system settings vs studio = user-managed entities" UX heuristic is a project-specific convention worth codifying.** Operator-interaction frequency (rare = admin, frequent = studio) is the discriminator. Missing this at F1 design was a 4-touchpoint UX miss reverberable through L5/L6 of F1; surfacing it post-F2 is acceptable, but the heuristic should be in `the_one/agents.md` so F3+ doesn't repeat it.

3. **`@asynccontextmanager` + nested `async with` does NOT compose cleanly with anyio task-group-managed CMs.** The SDK's `stdio_client`, `streamable_http_client`, and `ClientSession` all use anyio task groups internally; teardown ordering is sensitive. `contextlib.AsyncExitStack` is the canonical fix; the design should have used it from the start. Not catastrophic in F2 (subprocess cleanup verified working via /proc scan; warning is suppressed) but will amplify under F4's pool eviction.

4. **Leg pre-splitting (L6a/L6b) is a structural win for legs with two distinct concerns.** L6a (happy path) + L6b (error matrix + content rendering) are reviewable independently and avoid 33-test commits with fuzzy review focus. Apply the heuristic: when a leg combines "core implementation" + "edge cases / error paths," pre-split.

5. **Test-seam patterns should follow a 3-property contract**: (a) underscore-prefix the attribute, (b) exclude from `__all__`, (c) "TEST-ONLY" tag in surrounding comment. F2's `_test_http_client_override` validates the pattern. If F5 adds a similar seam, this is the contract.

6. **Closure-mirror enumeration (admin.js / studio.js) has now landed 4 times.** F1 debrief flagged this; F2 retrofit confirmed the pattern is reversible. Extracting a `defineSection(spec)` helper is high-leverage before F8 lands a 5th call site.

7. **The post-flight retrofit pattern works** for sub-leg-sized UI corrections (zero functional/API/schema changes; mechanical refactor; captured in flight-log Decisions). Don't force a leg artifact when the work is reversible and validated via existing tests + a Reviewer pass.

8. **F1 debrief contract consumption was clean** — all 5 forward-looking action items from F1 debrief consumed by F2: config.env validation backfill, OAuth slot non-dependency, env-var assembly shape clarification, anchor-by-symbol-name citations, per-leg lint gate. Closure was mechanical, not aspirational.

## Recommendations

1. **F4 must bundle the AsyncExitStack disconnect refactor.** The `RuntimeError: generator didn't stop` swallow is cosmetic now, structural for F4's pool eviction patterns. Refactor must touch `client.py` + both transport modules; test under pool-eviction race conditions. F4's L1 should be the AsyncExitStack landing; pool work follows.

2. **Add `the_one/mcp/README.md` covering F2's runtime invariants** before F3 starts. Specifically: test-seam pattern, F4-pool-compat invariants (cross-link to CLAUDE.md but co-locate the test names that lock each invariant), AsyncExitStack TODO, `_DEFAULT` sentinel rationale, 2-layer flat-merge pattern, dead-yield-after-raise pattern. Scope to runtime invariants; ~150-200 lines.

3. **Codify the "admin = system settings vs studio = user-managed entities" UX heuristic in `the_one/agents.md`** under a "UI placement conventions" section. Project-specific UX convention, not flight-control methodology — belongs in the project's own `agents.md`. Prevents F8 (Studio MCPs override panel) from repeating F1's L5 mistake.

4. **Extract a `defineSection(spec)` helper** in `static/js/areas/_shared/section-registry.js` to consolidate the 4-times-applied closure-mirror enumeration. Takes `{id, label, area, fetch, render, hydrate, serialize, dirtyMode}` and registers all 18 touchpoints from one description. Land before F8.

5. **Update flight-design Phase 1b reconnaissance prompt** in `mission-control/.claude/skills/flight/SKILL.md` to include a "stake-test probe" recommendation: when a flight stakes integration tests on a specific SDK pattern, the recon should include a 10-line "does this actually work" probe script, not just static wheel inspection. Catches LifespanManager / once-per-instance / DNS-rebinding-style gotchas at flight design rather than leg design.

## Action Items

- [ ] **F3 (sandbox) leg design**: F2's stdio transport spawns subprocesses bare via `stdio_client(StdioServerParameters)`. F3 must wrap with bubblewrap inside `connect_stdio` (NOT in `MCPClient.connect()` — keep dispatch transport-agnostic). The wrap point should preserve `build_stdio_environ`'s 2-layer flat-merge contract; bubblewrap's sandbox-profile env-policy is a third layer under the operator kv table.

- [ ] **F4 (warm-pool) leg design**: bundle the AsyncExitStack disconnect refactor as F4's L1 (or as a prerequisite leg). Don't carry the `RuntimeError: generator didn't stop` warning forward. Validate the fix under pool-eviction race conditions. F2's §9 invariants (`is_alive`, `last_activity`, idempotent disconnect, picklable-free) are sufficient — no new invariants needed; only the noise issue.

- [ ] **F5 (OAuth) leg design**: thread Bearer tokens through the streamable-http transport's two-path header injection. Static-bearer entry point is the kv table; F5 extends. Consider an httpx native auth handler for dynamic token refresh mid-session rather than static-headers-at-construction (the current production path constructs the httpx client once at connect). F5 introduces `secrets["access_token"]`, `["refresh_token"]`, `["token_expires_at"]` slots — F1 debrief KL #6 confirmed F2 doesn't pre-depend on them; clean room.

- [ ] **F5 OAuth callback handler**: reuse the in-process ASGI lifespan-driven test pattern from L3 if F5 builds an OAuth-callback ASGI test app. Worth flagging in F5 design as a precedent.

- [ ] **F6 (agent integration) leg design**: F2 doesn't expose tool-name namespacing. `MCPTool.name` is the server's local name; F6 must namespace at the `MCPToolProvider` wrapping layer to avoid collisions. `MCPToolResult.text` flattening is what F6 dispatches into the agent's tool-result rendering; `MCPToolResult.is_error` is always False on a returned result (because `MCPCallError` raises before return when server isError=true) — F6 ignores it; F7 reads it for inspector trace pane.

- [ ] **F8 (Studio MCPs tab) leg design**: extract the `defineSection(spec)` helper before F8 lands a 5th closure-mirror call site. Codify the registry pattern.

- [ ] **Routine maintenance — `App.adminFormHelpers` cross-namespace consumption**: 6 call sites in `static/js/areas/studio/mcp-server-editor.js` (lines 284, 300, 313, 697, 763, 825) call `App.adminFormHelpers.*` after the admin→studio retrofit. Rename to neutral `App.formHelpers` OR re-home the helper module to `static/js/shared/form-helpers.js` and re-export under both namespaces during a migration window. Land before F4/F8 add a second cross-namespace consumer.

- [ ] **Routine maintenance — `admin-` CSS class prefixes in studio markup**: 24 occurrences across `static/js/areas/studio/mcp-server-editor.js` + 4 in `static/js/areas/studio/mcp-servers-grid.js`. Move corresponding CSS rules; rename markup classes. Mechanical pass; ~30-50 LOC of CSS + JS edits.

- [ ] **Routine maintenance — add `UrlElicitationRequiredError` propagation test for `list_tools`**: 10-line mock-based test in `TestCallToolErrorTranslation` (or new `TestListToolsErrorTranslation` class) asserting the implementation's `client.py:302-303` re-raise path is exercised. Documents the contract; minor.

- [ ] **Methodology improvement (mission-control)**: update `flight/SKILL.md` Phase 1b recommendation to include the "stake-test probe" pattern (10-line script verifying integration test path actually works against the SDK).

- [ ] **Methodology improvement (mission-control)**: codify "post-flight retrofit" as a first-class change category in the agentic-workflow skill — sits between "leg" and "routine maintenance," characterized by (i) targets a recently-landed flight, (ii) zero functional change, (iii) captured as a "Decisions" entry in the flight log not as a leg artifact, (iv) a single commit on the flight branch.

- [ ] **Project doc update — `the_one/mcp/README.md`**: write the runtime invariants README per Recommendation #2.

- [ ] **Project doc update — UI placement heuristic in `the_one/agents.md`**: codify "admin = system settings (rare changes) vs studio = user-managed entities (frequent changes)" per Recommendation #3.
