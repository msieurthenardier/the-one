# Flight Debrief: Browser Test Foundation

**Date**: 2026-04-26
**Flight**: [Browser Test Foundation](flight.md)
**Status**: landed
**Duration**: 2026-04-25 → 2026-04-26 (~1.5 days, single agentic-workflow session)
**Legs Completed**: 8 of 8 (all landed and committed in single bundled commit `08546e0`)

## Outcome Assessment

### Objectives Achieved

The flight delivered against all stated objectives. Per the original spec:

- **Playwright (Python binding) installed and integrated** — toolchain unified with existing pytest infra; `@pytest.mark.browser` marker excluded by default alongside `live`. ✓
- **`mock` provider type as production code, dev-mode-gated** — 5th provider type (`ollama`/`openai-compatible`/`openai`/`anthropic`/`mock`) wired through 6 layers; `THE_ONE_DEV_MODE=true` controls visibility and creation. Dual-use: tests + offline dev work. ✓
- **Per-test app subprocess fixture stack** — `app_clean` / `app_with_provider` / `app_with_agent` with isolated `tmp_path` data dirs, random ports, SIGTERM teardown, wait-for-ready loop. ✓
- **3 baseline flow tests** covering M03-era critical user flows: provider setup, agent CRUD, chat. All deterministic (mock provider eliminates LLM nondeterminism). ✓
- **`data-testid` attributes** on 14 load-bearing UI elements (5 admin, 5 studio, 3 chat, 1 in-banner) so tests survive F2/F3 redesigns. ✓
- **CI integration** — Concourse `test` task swapped to `mcr.microsoft.com/playwright/python:v1.58.0-jammy`, two pytest invocations chained. Operator verification of live Concourse run still pending (out of autonomous scope). ⚠ Partial — see Known Issues
- **Documentation** — CLAUDE.md (4 additions), `the_one/agents.md` (Browser test fixtures + Provider type extension checklist). ✓

### Mission Criteria Advanced

This flight contributes to one of the nine M04 success criteria:

- ✓ **"Automated browser tests cover the critical user flows and fail on regression"** — 8 browser tests passing (1 smoke + 2 fixture sanity + 2 seeder + 3 flow), runnable locally with `pytest -m browser tests/browser/`. CI integration in place pending operator verification.
- ⊙ **"Critical user flows progress without dead-ends, unexplained errors, or unclear next steps"** — F1 establishes the *regression net* for these flows; F4-F6 polish the flows themselves. F1 also caught and fixed one real UX bug (admin.js base_url validation for hidden-field types) as a side effect.

## What Went Well

### Mock-provider-as-production-code pivot was the right call
Mid-design (after first architect review), the user proposed swapping the planned HTTP-stub server for a `mock` provider type as production code. This pivot:
- Eliminated the "track Ollama API surface" maintenance burden (the original spec had the chat-completion path wrong — `/v1/chat/completions`, not `/api/chat`)
- Avoided needing 5 stub endpoints (`/api/tags`, `/api/show`, `/v1/chat/completions`, `/api/ps`, `/api/generate`)
- Created dual-use value: offline dev work + demos + tests
- Cleanly extended the existing `LLMProvider` ABC without subclass tricks

The cost — a 6-layer wiring surface for any future provider type — is real but documented and bounded.

### Test stability across the full browser suite
Across 5+ stability runs per flow test (3 stability + 2 verification), zero flakes observed. Max wall-time delta within a single test: 170ms. Per-test breakdowns stayed under 2 seconds. The per-test subprocess + `tmp_path` isolation pattern delivered exactly the determinism it promised.

### Design-review process caught real bugs before implementation
The two-pass architect review on the flight spec caught the wrong-stub-LLM-API-surface (would have blocked leg 02). Per-leg design reviews caught:
- Leg 02: `_fake_get_provider` `**kwargs` compatibility check
- Leg 05: Test scenario was unreachable as written (post-Create switches to edit, not list)
- Leg 06: AC/IG test name discrepancy
- Leg 08: CLAUDE.md placement vagueness, autopilot-task off-limits framing

None of these would have been caught at implementation time without a fail-and-rework cycle. The investment in design-review-heavy methodology continued to pay off.

### Architectural debt was bounded and documented
Every deviation was caught in either design review or implementation, fixed surgically (no half-finished states), and documented in the flight log with rationale. The `/leg` skill's State-Machine Reachability Audit caught 5 of 6 wiring layers in leg 02 — the 6th (SQLite CHECK constraint) is now a methodology improvement target.

### One real UX bug discovered as flight side effect
Leg 05's flow test surfaced a real bug in `admin.js` (the save handler unconditionally validated `base_url` non-empty, blocking creation of types where the field is hidden — mock, openai, anthropic). Caught by the regression net before it would have annoyed a user. Implementer fixed inline as a deliberate one-line change with rationale; tests then locked the fix.

### Bundled-commit-at-flight-end discipline held cleanly
Eight legs across 16 modified files + 4 new directories committed atomically in one reviewable change. The Reviewer (Haiku) covered the entire change set in one pass, signaled `[HANDOFF:confirmed]` with no blocking issues. No per-leg commit churn.

## What Could Be Improved

### Process

- **State-Machine Reachability Audit missed DB-layer constraints again.** M03 debrief flagged FK constraints; F1 added schema migration v6 because we missed CHECK constraints. The audit checklist in `/leg` should generalize from "FK choices" to "all schema-layer constraints" (Literal/CHECK/FK/NOT NULL/triggers).

- **Specs traced UX from user mental model rather than code paths** (leg 05 — assumed Create → list, code does Create → auto-edit). For any flow leg with save/submit actions, the spec should cite the exact source-line range of the post-success branch and assert the assumed next-state matches what the JS does.

- **Testid-budget-per-leg may not scale.** F1 used 3-5 testids per flow leg (14 total). F3 will likely need 8-12 just for the new app shell. The budget should shift from "raw count" to "load-bearing test selectors," with a registry/convention to prevent drift.

- **CI verification was deferred to operator** rather than verified in-flight. This is the expected default for autonomous execution but creates a soft dependency: the flight is "landed" but the CI half of "runnable both locally and in CI" is not yet proven. Operator follow-up needed.

### Technical

- **Provider-type extension is now a 6-layer change** — Pydantic Literal, `_PROVIDER_TYPE_MAP`, registry loaders, SQLite CHECK + migration, API gating + 4 branches, frontend dropdown + defaults + badge. The agents.md checklist makes this discoverable but does not reduce it. The hardcoded list at `api.py:438-446` *duplicates* the Literal at `db/models.py:20`; deriving via `typing.get_args()` would save one of the 6 layers.

- **admin.js / studio.js divergence widened.** Leg 02 added `_renderProviderFormImpl` + `providerTypesReady` promise gating to admin.js; studio.js has nothing equivalent. The M03 debrief flagged this divergence; F1 widened it. F3's form-primitive extraction must consolidate both, not just M03-era admin.js.

- **`data-testid` naming convention is inconsistent.** Mix of `-btn` suffix vs bare nouns (`add-provider-btn`, `provider-card`, `agent-empty`, `chat-input`). No source-of-truth file or naming rule. F2 should establish a convention before adding more testids.

- **`from conftest import` import pattern still used by 5 existing test files.** F1 papered over the collision with `pythonpath = ["tests"]` + `--import-mode=importlib`. Sustainable but fragile to future restructuring. Worth a 30-min cleanup leg in a future maintenance flight.

- **`THE_ONE_DEV_MODE` is a binary flag.** Currently gates exactly one thing (mock provider visibility). If F3+ accumulate other dev-only affordances, this flag will either drift (multiple env vars) or overload (one flag for many features). Decide at next add: extend with a granular pattern (`Settings.dev_features: dict[str, bool]`) or accept overload.

- **`subprocess.PIPE` for stdout/stderr without a reader** can deadlock if a subprocess fills the OS pipe buffer (~64KB on Linux). Mitigated today by `--log-level warning`; F4 (Chat alignment) may exercise enough chat traffic to risk this.

### Documentation

- **No `README.md` at project root** — the flight added playwright tooling and the mock provider but neither is mentioned in any project-root readme (because there isn't one). CLAUDE.md and agents.md are good for AI-facing context but a human-facing README mentioning `playwright install chromium` in dev setup would help. Flight 08's checklist explicitly noted this.

- **Per-test subprocess fixture details scattered.** The *what* is in `tests/browser/conftest.py` and `agents.md`; the *why and how* (port allocation race, `proc.poll()` early-exit, IPv6 WSL2 quirk, `--log-level warning`) is across docstrings. Worth a single consolidated section.

- **Mock provider's `config["response"]` schema** documented only in `mock.py` docstring. Should be lifted into `agents.md` so test authors find it without grepping source.

- **Testid registry / naming convention** does not exist. Worth establishing now before F2 expands the surface.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Pytest `--import-mode=importlib` + `pythonpath = ["tests"]` (leg 01) | Existing 5 test files use bare `from conftest import`; nested `tests/browser/conftest.py` shadowed root conftest under default `prepend` mode | Yes — modern pytest recommendation; standard for projects with non-package test dirs |
| Schema migration v6 (leg 02) | State-Machine Reachability Audit missed the SQLite CHECK constraint at `db/schema.py:18,129` | No (the migration itself follows the v3/v5 pattern) — but YES the audit checklist should explicitly include DB-layer constraints |
| Playwright fixtures module-scoped, not session (leg 03) | Session scope kept asyncio loop alive across modules and broke leg-01 standalone smoke test's own `sync_playwright()` context | Yes — "any test that creates a parallel `sync_playwright()` context cannot coexist with a session-scoped fixture"; lift into mission-control as a Playwright-Python testing rule |
| `app_with_agent` composes on `app_with_provider` (rather than re-seeding) (leg 04) | Cleaner pytest fixture caching semantics | Yes — canonical pattern for layered fixture stacks |
| admin.js base_url validation fix (leg 05) | Existing UX bug — form blocked save for types where field is hidden (mock, openai, anthropic) | Already fixed; lock down with explicit test |
| Test scenario rewritten in design review (leg 05) | Spec traced user-mental-model UX; actual code auto-switches to edit mode after Create | Yes — methodology rule for flow legs: cite exact source-line range of post-success branch |
| `app_with_agent` fixture deps composed via pytest, not duplicated | Per-test fixture caching makes it cheap and clean | Yes — already standard |

## Key Learnings

### Technical

1. **Mock-provider-as-production-code is a generalisable pattern.** When a flight needs deterministic stand-ins for an external dependency (LLM, KB, MCP server, tool), follow this shape: (a) production class implementing the existing ABC, (b) dev-mode env-var gate, (c) audit checklist for the wiring layers, (d) UI dropdown filtered by gate. Trade-off: more layers to maintain than a test-only stub, but dual-use value makes it net positive.

2. **DB-layer constraints belong in the State-Machine Reachability Audit alongside application-state machines.** M03 flagged FK constraints; F1 added CHECK constraints. The pattern is broader: "any layer that can foreclose a state value must be enumerated." Generalise the `/leg` skill's audit prompt from "FK CASCADE" to "any DB constraint that hard-codes the state value enumeration."

3. **Per-test subprocess + `tmp_path` data dir is the canonical isolation pattern** at the scale of <20 tests per suite. Beyond that, shared-app-with-DB-reset becomes worth considering — but the M03 known issues (singleton aiosqlite, unbounded `_sessions` dict) make per-test the cleaner default for now.

4. **Playwright fixture scoping has a Python-specific trap**: any standalone `sync_playwright()` context in the test suite forces module-scope (not session-scope) on the shared Playwright fixtures. The asyncio-loop ownership conflict is invisible until the standalone context tries to spin up.

5. **The `__MASKED__` sentinel is a JS+Python contract** that needs documentation at both call sites, not just one. Magic strings traversing language boundaries without typed bindings are a footgun; F3's form primitive extraction is the place to consolidate.

### Process

1. **Two-pass architect review on flight specs catches real bugs before legs start.** The first pass caught the wrong stub LLM API surface; the second caught the dev-mode gating placement and route ordering invariant. Worth maintaining as the standard for any flight introducing production code that crosses ≥4 wiring layers.

2. **Bundled-commit-at-flight-end (single commit for 8 legs) reduces review friction without losing per-leg discipline.** The flight log + per-leg artifacts captured the per-leg detail; the single commit gave the Reviewer one coherent change set to evaluate. Keep.

3. **Inline UX fixes during flow tests are signal, not noise.** Leg 05's `admin.js` base_url bug fix surfaced because the test ran the actual production path. The implementer correctly recognized it as a bug (not a test workaround) and fixed inline with documentation. Repeat this discipline in F4-F6.

4. **Vibe-coding flights need explicit "regression net intact" leg-end ACs.** F4-F6 are nominally "patterns emerge as we go" but the test surface is not negotiable. Make this distinction explicit in F4-F6 mission notes: testids and fixture contracts are prescribed-stable; CSS and UX patterns are fluid.

### Domain

1. **The default mock response (`"Mock response from the mock provider."`) is currently a module-level constant.** Adequate for F1; if F4-F6 tests need varied default responses, this becomes a coordination point. Revisit if multiple test classes need divergent defaults.

2. **Browser tests and standalone smoke tests have different lifecycle requirements.** The leg-01 smoke test deliberately doesn't depend on the app fixture (it runs against a `data:` URL) so it stays green even if the app fixtures break. This separation paid off when the Playwright scope deviation in leg 03 happened — the smoke test isolated the broken layer cleanly.

## Recommendations

1. **Update the `/leg` skill's State-Machine Reachability Audit checklist** to explicitly include DB-layer constraints (Pydantic Literal, SQLite CHECK, FK with ON DELETE behavior, NOT NULL, triggers) alongside the application-state machine. Direct follow-through on M03's recurring "schema constraints not audited" pattern.

2. **Establish a `data-testid` naming convention and registry before F2 begins.** Proposed: `{area}-{element}` pattern (`chat-message`, `admin-provider-card`, `studio-agent-item`); a single source-of-truth file (`tests/browser/testids.py` exporting symbolic constants); a CI grep that fails if a flow test references a testid not present in any `*.js` file. Without this, F2/F3 redesigns will dissolve the regression net silently.

3. **F3 form primitive extraction must absorb the admin.js / studio.js divergence widened by F1.** Specifically: `_renderProviderFormImpl` + `providerTypesReady` machinery in admin.js (leg 02) needs to consolidate with studio.js's form rendering. The shared primitive must accept and forward `data-testid` so existing test selectors keep matching after extraction.

4. **Lift the per-test subprocess + `tmp_path` pattern into `agents.md` as the canonical test isolation pattern** for subprocess-driven tests. Include the *why* (port race window, `proc.poll()` early-exit, IPv6 WSL2 quirk, `--log-level warning`), not just the *what*.

5. **Verify Concourse CI integration with `fly` (operator action)** to close out the F1 acceptance criteria. The pipeline change is committed and the local run path is green; only the live Concourse run is pending.

## Action Items

### Immediate (next 1-3 sessions)

- [ ] **Operator: verify Concourse CI pipeline** — `fly -t self set-pipeline -p the-one -c ci/pipeline.yml`, trigger `the-one/deploy`, watch the test task. Confirm Playwright image pulls and both pytest invocations pass. Document outcome in mission debrief or a known-issues entry.
- [ ] **Establish `data-testid` naming convention** (lift into `agents.md` Browser Test Fixtures section). Decide on the `{area}-{element}` pattern or alternative; document the registry approach (constants file vs allow-list).
- [ ] **Mission `Known Issues`**: add three carry-forwards into M04 mission.md:
  1. F2 must preserve all 14 F1-deployed `data-testid` values during CSS rewrite
  2. F3 must keep regression net intact across form-primitive extraction; shared primitives must forward `data-testid`
  3. admin.js / studio.js form-render divergence widened in F1 (leg 02); F3 must address both
- [ ] **Mission constraint addition**: vibe-coding flights (F4-F6) must keep `pytest -m browser tests/browser/` green at every leg-end. Testids on load-bearing elements are prescribed-and-stable; CSS/UX patterns are fluid.

### Near-term (small follow-up legs or bundled in maintenance)

- [ ] **Lock the leg-05 admin.js fix with an explicit unit/flow test** that validates `base_url` is required for types with `showBaseUrl=true` (e.g., ollama, openai-compatible) but NOT required when `showBaseUrl=false`. Currently only the side-effect catch.
- [ ] **Strengthen mock provider tests**: defensive test for malformed `config["response"]` (e.g., `{"response": "not-a-dict"}`) to ensure graceful failure rather than AttributeError.
- [ ] **Refactor 5 test files** to drop bare `from conftest import` in favor of `from tests.fixtures import` (or move FakeLLM/StubTool to `tests/fixtures.py`). Then drop `pythonpath = ["tests"]` indirection from pyproject.toml.
- [ ] **Derive frontend `PROVIDER_TYPES` list from Pydantic Literal** via `typing.get_args(LLMProviderConfig.__pydantic_fields__["type"].annotation)` — eliminates one of the 6 wiring layers.
- [ ] **Add a unit test asserting `len(_PROVIDER_TYPE_MAP) == len(LLMProviderConfig.__pydantic_fields__["type"].annotation.__args__)`** — pins the provider-type-checklist invariant.
- [ ] **Add `playwright install chromium` to README.md dev setup** — currently no README exists; if creating one, include this.
- [ ] **Pre-existing 8 ruff errors in `tests/test_auto_load.py`** — clean up in a routine-maintenance pass.

### Mission-Control methodology

- [ ] **Update `/leg` State-Machine Reachability Audit checklist** to explicitly include DB-layer constraints alongside FK behaviors. Generalise from "FK CASCADE" to "all schema-layer constraints."
- [ ] **Add to `/flight` pre-flight check**: when a flight introduces production code that crosses ≥4 wiring layers (application + UI + DB + API), require an explicit per-layer audit checklist in the flight design.
- [ ] **Add Playwright-Python rule to `/leg` testing notes**: "module-scope by default; never session-scope when standalone `sync_playwright()` may exist elsewhere in the suite."
- [ ] **Vibe-coding flight template additions** (for F4-F6 and similar): include "regression-net intact" as a default leg-1 AC and as flight-exit AC. Distinguish prescribed-stable surface from fluid surface.
- [ ] **Methodology rule for flow legs**: when a leg's IG involves any save/submit action, cite the exact source-line range of the post-success branch and assert the assumed next-state matches what the code actually does.

### Mission-Level Known Issues at Close

These cross flight boundaries; future flights touching these areas must coordinate:

- **CI verification operator-pending**: pipeline change committed, local run green; live Concourse run not yet verified
- **Provider-type extension is a 6-layer change**: any future provider type must walk the agents.md checklist (Pydantic Literal, `_PROVIDER_TYPE_MAP`, registry loaders, schema CHECK + migration, API gating + 4 branches, frontend dropdown + defaults + badge)
- **admin.js / studio.js form-render divergence widened**: `_renderProviderFormImpl` in admin.js has no studio.js equivalent; F3 form-primitive consolidation must address both
- **Inherited from M03**: singleton aiosqlite connection (no concurrent transactions), unbounded `_sessions` dict, C-lite mid-message limitation, `__MASKED__` sentinel as untyped JS+Python contract
- **`data-testid` registry / naming convention not established**: 14 testids deployed with mixed conventions; F2/F3 will multiply the surface
