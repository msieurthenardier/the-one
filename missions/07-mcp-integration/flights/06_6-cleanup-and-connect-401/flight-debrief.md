# Flight Debrief: Cleanup + connect-time 401 translation

**Date**: 2026-05-09
**Flight**: [Cleanup + connect-time 401 translation](flight.md)
**Status**: landed
**Duration**: 2026-05-09 (single-day execution; design + L0 + L1 + review + commit landed in one pass)
**Legs Completed**: 2 of 2

## Outcome Assessment

### Objectives Achieved

Both deliverables landed cleanly:

- **L0 (cleanup-batch)** — F6.5 debrief carry-forward maintenance: 3 unit tests covering F6.5 L4's inline production fixes (`allow_dcr_bootstrap` factory path, `OAUTH_MANAGED_SECRET_KEYS` filter, `_entry_worker` synthetic-csid bootstrap), `App.areas` re-export resolving Anomaly A2 (4 browser tests transitioned FAIL → PASS), synthetic-csid pattern docstring centralized at `the_one/mcp/oauth/handlers.py`, and a Test-connection-button operator-facing entry in `CLAUDE.md`.
- **L1 (connect-401-translation)** — `MCPClient.connect()` extended with a nested innermost `try/except* (OAuthFlowError, OAuthTokenError)` clause translating SDK auth-flow exceptions during `session.initialize()` to typed `MCPAuthRequired`. Closes F6.5 Design Decision §3's explicit deferral. CancelledError fallback message narrowed (drops "likely 401" speculation); 3 new unit tests + 1 updated test exercise the new auth-translation surface.

Net diff: 13 files, +1024/-22 lines on commit `03cd190`. Test count delta: +3 (1356 vs 1353), exactly accounting for L1's three new tests; L0's 9 new tests landed within the streamable_http_transport file count and provider_factory expansion without affecting the headline pass count due to test-count baseline mechanics.

### Mission Criteria Advanced

- **Criterion #10 (graceful failure isolation)** — extends `MCPClient.connect()` 401 surface from lossy `MCPConnectionError("cancelled during initialize")` to typed `MCPAuthRequired`, mirroring F6.5 L2's `list_tools` pattern. `MCPToolProvider.get_tools_for_agent` already graceful-skips on `MCPAuthRequired` (post-F6.5 L2), so F6.6 completes the auth-pending discriminator surface across both `connect` and `list_tools`.
- **Criterion #11 (automated coverage proving each layer's contract)** — closes F6.5 debrief recommendation #3: 3 unit tests covering F6.5 L4 inline fixes that previously had only non-reproducible HAT verification. Plus 3 connect-time translation tests + 1 updated cancellation test for L1.

Both criteria checked off in `flight.md::Contributing to Criteria`.

## What Went Well

- **2-leg split (L0 maintenance + L1 architectural change)** — right granularity. L0's six items shared a common origin (F6.5 carry-forward) and verification surface (unit tests + browser-test recovery); L1 had its own AC surface (3 new tests + production code). No coupling friction between the legs.
- **Pre-flight Design Review Cycle 1's HIGH issue catch on L1** — decisively load-bearing. The architect's reframe from "verbatim mirror of `list_tools`" to "ADD only the missing `except*` clause" prevented L1 from becoming a structural rewrite that would have lost F6 A5's `BaseExceptionGroup` 401-walk fidelity (which extracts `WWW-Authenticate` + `resource_metadata_url` from the actual HTTP response — a fidelity the `OAuthFlowError`/`OAuthTokenError` exceptions cannot replicate because they don't carry a response object). Single architect cycle, ~5 minutes of work, prevented a multi-hour rewrite.
- **Citation audits in both leg artifacts** — L0's audit caught 4 cycle-1 corrections (the `_RegistryEntry.ttl_seconds` requirement, `_pool.py:210` line correction, `app.js:267` block location, `OAUTH_MANAGED_SECRET_KEYS` shape). L1's audit was insurance rather than load-bearing but prevented design-time-to-review-time drift. Net: load-bearing in L0, defensive in L1; both pulled their weight.
- **Single bundled code review at flight close** — Reviewer (Haiku) covered all uncommitted changes from both legs in one pass, signaled `[HANDOFF:confirmed]` without issues. No iteration cycles needed. Saved the per-leg review/commit overhead the F6.6 protocol explicitly designed away.
- **Implementer skipped a known-failing first attempt** — for the `App.areas` dict-vs-array deviation, the implementer correctly read the leg's "MAY skip the failing first attempt" escape hatch and went directly to `areas: order`, saving ~30s of test-cycle time and reaching the working code path on the first try.
- **Code comment density at the new translation site** — `client.py:238-249` (11-line block explaining the nested-try shape, the Python no-mix constraint, F6.5 L2 pattern reference, and the asymmetry rationale) makes the divergence between `connect` and `list_tools` legible to future maintainers.

## What Could Be Improved

### Process

- **Architect-introduced bug class (App.areas dict-vs-array)**. Design Review Cycle 1 explicitly directed `areas: areas` (the dict export) over `areas: order` (the array export). The architect verified the variable declarations existed at `app.js:2-3` but did NOT cross-check what consumers do with the export. The test helper at `tests/browser/test_oauth_modal_flow.py:42` calls `window.App.areas.find(a => a.id === 'chat')` — `Array.prototype.find` semantics; a dict has no `.find` method. The leg author caught the mismatch at leg-design time and added a "TRY first / FALLBACK" path; the implementer went direct to `areas: order` per the escape hatch. The right phase to catch this was **flight design review**, not leg-design Edge Cases. Same class of issue F6.5 debrief flagged about Python signatures — F6.6 surfaces it for JS consumer call shapes.

- **Test 3's mock-stop strategy spec was empirically wrong**. The L0 leg specified `mock_factory.side_effect = RuntimeError(...)` would be caught by `_entry_worker`'s `except BaseException` block. The catch actually wraps `await client.connect()` only, NOT the factory call (`_pool.py:204` is unprotected). The implementer corrected the shape mid-implementation to `pytest.raises(RuntimeError)` + `call_args` assertion. **Cycle-1's architect mechanical citation re-check did not simulate test execution** — citation verification proves "this line exists" but doesn't prove "this test will hit the path the spec claims."

- **Leg specs that prescribe mock-stop strategies** should either (a) cite a verified existing test of similar shape (so the topology is empirically grounded), or (b) acknowledge the catch-block topology may force the implementer to choose between `pytest.raises` and `entry.failure` based on actual code reading.

- **The "TRY first / FALLBACK" path in L0's spec for App.areas** was a designer-CYA artifact more than implementation guidance. When the spec writer KNOWS the primary path will fail (mechanically predictable from reading the test), the spec should commit to the working path with a deviation note explaining the cycle-1 architect's directive — not stage a known-failing first attempt as a "discovery" exercise.

### Technical

- **`MCPClient.connect()` now has three structurally distinct 401-translation paths**:
  1. Inner `except* (OAuthFlowError, OAuthTokenError)` (F6.6 L1, NEW) — SDK auth module raised pre-HTTP.
  2. Outer `except (Exception, BaseExceptionGroup)` → `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` walk (F6 A5) — server replied 401, anyio task-group wrapped it.
  3. Outer `except asyncio.CancelledError` (F6 A5, narrowed by F6.6) — cleanup-deadlock cancellations unrelated to auth.

  Each path corresponds to a different layer failing, so the asymmetry is **semantically justified**, not accidental tech debt. The asymmetry IS documented in code comments, but maintenance burden is real: future readers comparing `connect()` and `list_tools()` will see different shapes; a hypothetical fourth exception class (e.g., `OAuthDiscoveryError`) would need explicit reasoning to slot into the right path; the cancellation narrowing is preserved by comments rather than structure (a future "tidy-up" refactor could silently widen it).

- **`asyncio.CancelledError` block (`client.py:283-302`) narrowing is unverified empirically**. The post-F6.6 stance is "fires only for non-OAuth, non-401 cancellation races," but the only test in the suite (`test_connect_cancelled_error_translates_to_connection_error`) stubs `CancelledError` directly rather than reproducing a real anyio task-group cleanup deadlock. Whether the path can ever fire in practice post-F6.6 is open — possibly dead code with operational cost; possibly a real defensive safety net.

- **`tests/test_mcp_pool.py` file-level exclusion has aged into too-coarse-grained**. F6.5 introduced `--ignore=tests/test_mcp_pool.py` because the file held real-bwrap integration tests that were slow + flaky in CI. F6.6 added a pure-unit test (`test_entry_worker_uses_synthetic_csid_when_tokens_present`, 0.02s, no bwrap dependency) to the same file — it is now silently excluded from the default suite by file-level filter. Test discoverability regression: the new unit test is well-isolated but invisible to standard test runs.

- **`OAuthFlowError` / `OAuthTokenError` constructor signatures aren't pinned by a contract test**. If the SDK changes them, F6.6's tests fail at construction — acceptable per L1 leg's Edge Cases note, but worth flagging as a future-proofing gap.

- **No cross-method integration test** that `connect()` via real OAuth → `list_tools()` errors with 401. The "F6.5 L2 graceful-skip cross-check" referenced in L1's verification stubs `list_tools` directly rather than running through real `MCPClient.connect()` first.

### Documentation

- **`CLAUDE.md` does not document the nested `try/except*` pattern** as a project convention. The pattern is now used at two sites (`connect` and `list_tools`) with non-trivial reasoning. Future contributors will re-derive "why is `connect`'s catch nested when `list_tools`' is flat?" without an anchor.

- **`MCPClient.connect()` has no `Raises:` docstring block**. The post-F6.6 raise surface includes `MCPVersionMismatch`, `MCPAuthRequired` (from two distinct paths), `MCPConnectionError` (multiple causes), `MCPClientError` re-raises, `NotImplementedError`, `asyncio.TimeoutError` translated. A 6-line `Raises:` block would help.

- **`tests/test_mcp_pool.py` exclusion rationale is undocumented in project-level docs**. The `--ignore` is named in flight checklists but not in `CLAUDE.md` or `pyproject.toml` comments. Convention is invisible to contributors who don't read flight artifacts.

- **The 306-deselected count in the full-suite output is undocumented**. Likely a marker filter (e.g., `not browser`), but `pyproject.toml::addopts` doesn't explain. Worth investigating + documenting before F8 lands more browser tests.

- **`mission.md` does not codify the `MCPClient.connect()` exception translation contract**. After F6.6, the contract is: `connect()` raises one of `MCPAuthRequired` / `MCPVersionMismatch` / `MCPConnectionError`; `MCPToolProvider.get_tools_for_agent` graceful-skips all three. Future flights MUST preserve this discriminator surface — adding a fourth typed exception requires updating both the translator and the consumer's match list. This is the kind of cross-flight contract that belongs in mission docs.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L0: `App.areas` exported as `areas: order` (array) instead of design review's directed `areas: areas` (dict) | The test helper at `test_oauth_modal_flow.py:42` calls `Array.prototype.find()`, which only works on the array; the dict shape would fail mechanically. Implementer skipped the leg's "TRY first" path and went direct to the working shape. | **No, but the underlying lesson should**: design reviews must cross-check exported-identifier consumer call shapes, not just verify declarations exist. Add to flight design-review checklist. |
| L0 Test 3: `pytest.raises(RuntimeError)` + `mock.call_args` assertion instead of asserting on `entry.failure` | The leg's spec assumed `_entry_worker`'s `except BaseException` catch wraps the factory call; reading `_pool.py:204` shows it wraps `await client.connect()` only. The factory call is unprotected, so `RuntimeError` propagates naturally. Implementer's shape was structurally cleaner than the spec. | **Yes**: leg specs that prescribe mock-stop strategies should either cite a verified test of similar shape OR acknowledge that catch-block topology may force shape choice based on real code. Cycle-1 architect re-check should simulate at least one test execution path mentally, not just verify citations. |
| L1: CancelledError docstring/comment block updated alongside the message text (cycle-1 SUGG promoted to soft-required) | The original "may optionally update" framing risked a doc drift where the message text dropped "401" but the comment still said "after a 401". Cycle-1 architect promoted to soft-required; implementer caught it gracefully. | **Yes**: cycle-1 SUGGs that prevent doc drift between code and adjacent comments should be promoted to soft-required by default. The cost (1 line) is much smaller than the future cost of stale comments. |

## Key Learnings

1. **The "ADD only" reframe is a powerful design pattern**. When a leg spec frames work as "mirror pattern X to method Y," design review's first job is to verify whether Y already has partial coverage of the relevant cases via a different mechanism. F6.6 L1 saved a structural rewrite by reframing as ADD-only after architect cycle-1 read the actual `connect()` body and found F6 A5's `BaseExceptionGroup` walk already handled HTTP 401s. **Standardize**: design reviews of "mirror X to Y" specs should explicitly answer "does Y already do part of what we're adding?"

2. **Citation audits are load-bearing in maintenance flights**. L0's 10-citation audit caught 4 real corrections at design time; L1's 12-citation audit was defensive but cheap. Future-flight ROI estimate: ~50% load-bearing, ~50% insurance — both pull weight. Keep the pattern.

3. **Mechanical citation re-checking ≠ test-execution simulation**. Architect cycle-1's mechanical re-check at review time confirmed every L0 citation was at the claimed line, but did NOT catch that the leg's mock-stop strategy hit a code path that doesn't exist (the `_entry_worker` catch doesn't wrap the factory). Citation verification proves "this line exists"; it does NOT prove "this test will hit the path the spec claims." Different verification surface needed.

4. **Synthetic-csid character-set disjunction invariant** (real csids are `[0-9a-f]` 12-char hex; synthetics contain `:`) is the right framing — collision-free regardless of synthetic-prefix length. The original design's "synthetic prefixes longer than 12 chars" framing was wrong (`agent_build:` is exactly 12 chars). Cycle-1 architect rewrite to character-set disjunction is the correct invariant.

5. **App.areas dict-vs-array** revealed that `App.areas` is now a public surface on `window.App` with array semantics + `.find()` consumer expectation. F8 inheritance: F8's MCP tab will register a new area; tests should assert registration via `App.areas.find(...)` to lock the contract. Do NOT refactor `App.areas` to dict shape during F8 — keep array as canonical.

6. **F6.5 debrief recommendation #5 (binding-HAT-for-OAuth-flights codification) is still uncodified.** F6.6 used the binding-HAT pattern as a rule with explicit waiver (Design Decision §4). The empirical pattern is now battle-tested across F4/F5/F6/F6.5/F6.6 (one waiver, four bindings). A subsequent mission-control flight should land the methodology template change.

7. **Test-metrics capture works** when the suite-timing pattern (added in mission-control commit `68ca4c5`) lands. F6.6 is the first flight with per-suite timings in the debrief input. Future flights now have a baseline for delta comparison: full unit suite ≈ 75–76s post-F6.6.

## Recommendations

1. **Add consumer-call-shape verification to flight design-review checklist** (highest impact). When a leg spec adds/modifies an exported identifier (function signature, class shape, JS object property), design review should grep for consumers and read at least one consumer site's call shape. ~2-5 minutes per affected identifier; would have caught the App.areas dict-vs-array issue at the right phase.

2. **Split `tests/test_mcp_pool.py` or migrate to marker-based filtering** (high impact, low effort). The file-level `--ignore=tests/test_mcp_pool.py` is now too coarse — F6.6's pure-unit test is silently excluded from the default suite. Either move unit tests to a separate file (`tests/test_mcp_pool_workers.py`) or replace the `--ignore` with `-m "not requires_bwrap"` and tag the bwrap-dependent tests accordingly.

3. **Add a "MCP error translation" subsection to `CLAUDE.md`** (medium impact, low effort). Document the nested-`try/except*` pattern, the three 401-translation paths in `connect()`, the asymmetry with `list_tools`'s flat shape, and the synthetic-csid invariant. Single source of truth for future contributors instead of distributed across F6.5/F6.6 flight artifacts.

4. **Add a `Raises:` block to `MCPClient.connect()`'s docstring** (medium impact, trivial effort). Enumerate `MCPVersionMismatch` / `MCPAuthRequired` (from two paths) / `MCPConnectionError` (multiple causes) / `MCPClientError` re-raise / `NotImplementedError` / `asyncio.TimeoutError` translated. Closes the docstring gap.

5. **Codify the `MCPClient.connect()` exception translation contract in `mission.md`** (medium impact, low effort). Short form: "`MCPClient.connect()` translates initialize-time failures to one of: `MCPAuthRequired` / `MCPVersionMismatch` / `MCPConnectionError`. `MCPToolProvider.get_tools_for_agent` graceful-skips all three. Adding a fourth typed exception requires updating both the translator and the consumer's match list." Cross-flight contract belongs in mission docs.

## Action Items

- [ ] Add consumer-call-shape verification to flight design-review checklist (mission-control template change; carry forward from F6.5 recommendation #5 in the same template flight)
- [ ] Split `tests/test_mcp_pool.py` into bwrap-dependent and pure-unit files, OR migrate `--ignore` to marker-based `-m "not requires_bwrap"` filtering — schedule for F8 or as a standalone maintenance flight
- [ ] Add "MCP error translation" subsection to `CLAUDE.md` documenting the nested-`try/except*` pattern, three 401-translation paths in `connect()`, and synthetic-csid invariant
- [ ] Add `Raises:` block to `MCPClient.connect()` docstring at `the_one/mcp/client.py:~210`
- [ ] Codify `MCPClient.connect()` exception translation contract in `mission.md` (mission-level F-contract, alongside existing F2/F3 contracts at lines ~306-334)
- [ ] Investigate + document the 306-deselected count in pytest output (likely `pyproject.toml::addopts` marker filter; document in `pyproject.toml` comment AND `CLAUDE.md` testing section)
- [ ] Document `tests/test_mcp_pool.py` exclusion rationale in `CLAUDE.md` testing section
- [ ] Decide: is `asyncio.CancelledError` block in `connect()` post-F6.6 still load-bearing? Either add a regression test that exercises a real cleanup-deadlock cancellation, OR document the path as "defensive only, never observed in production" and consider removal in a future maintenance pass
- [ ] F8 planning: lock the `App.areas` array-shape contract via a registration test; do NOT refactor to dict shape; consider exposing `App.areaById = (id) => order.find(...)` as a memoized lookup helper if a hot path emerges
- [ ] F8 or successor flight: consider consolidating `MCPClient.connect()` 401-translation via a `_translate_init_failure(e)` helper — defer until a 4th exception class or 4th maintenance pass surfaces it
- [ ] Mission-control template flight: codify F6.5 debrief recommendation #5 (binding-Tier-2-HAT-for-OAuth-flights) as a methodology checklist item, with the F6.6 waiver pattern as the documented exception shape
