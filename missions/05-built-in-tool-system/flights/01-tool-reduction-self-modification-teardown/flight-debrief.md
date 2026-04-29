# Flight Debrief: Tool Reduction & Self-Modification Teardown

**Date**: 2026-04-29
**Flight**: [Tool Reduction & Self-Modification Teardown](flight.md)
**Status**: landed
**Duration**: 2026-04-28 (L1-L6 design + implementation + Phase 2d) → 2026-04-29 (L7 HAT + landing)
**Legs Completed**: 7 of 7

## Outcome Assessment

### Objectives Achieved

The flight delivered every decision in the spec and every leg in the planned sequence. Cumulative diff: **305 insertions, 1263 deletions across 33 files** (L1-L6 batch `dc57080`) plus **207 insertions, 25 deletions across 5 files** (L7 HAT inline-fix `abaa53a`). Net negative ~975 lines — a healthy ratio for a teardown flight.

Concrete deliverables:
- Seven self-modification tool source files deleted (`git`, `memory`, `mission_control`, `restart`, `rollback`, `self_deploy`, `test_runner`).
- `behaviors.py` deleted; `CONTINUE_SCHEMA` inlined into `core.py` (its only consumer).
- `direct_actions` field removed from `AgentConfig`; the dead direct-action call site in `Agent.step()` removed.
- `DEFAULT_SYSTEM_PROMPT` renamed to `BASE_PROMPT` and content rewritten — first to a 296-word general-purpose draft (L2), then minimized to 202 words at L7 HAT after the operator concluded that voice/tone prescriptions belong in per-agent personas, not the base.
- `AgentConfig.get_system_prompt()` rewritten for additive composition (base prompt + `\n\n---\n\n` + per-agent persona). `Agent.__init__`'s `system_prompt` default removed, closing the bypass that previously let direct constructions inherit `DEFAULT_SYSTEM_PROMPT`.
- Schema migration v7 strips removed tool names from existing agents' `enabled_tools`/`disabled_tools` JSON columns. `NULL` whitelist preserved as `NULL` (no silent privilege escalation).
- Concourse pipeline trimmed from 6 jobs + 1 resource to 1 job (`deploy` with `auto-rollback`). Heartbeat resource and `autopilot`, `pause-autopilot`, `unpause-autopilot`, agent-facing `rollback`, and `restart` jobs gone.
- `/workspace` bind-mount, `THE_ONE_WORKSPACE_DIR`, and six `THE_ONE_CONCOURSE_*` env vars removed from `docker-compose.yml` and `ci/deploy.sh`. `entrypoint.sh` minimized to 4 lines. `Settings` shrunk from 8 fields to 4.
- `/api/selftest` probe redirected from `/workspace/pyproject.toml` to `/app/pyproject.toml` — caught at L4 design just before it would have auto-rolled-back every deploy.
- `/api/info` extended with `base_prompt` field; admin System page displays it as a read-only `<pre>` block (XSS-safe via `textContent`). Concourse CI section gone, Workspace Directory field gone, `dev_mode` added to Server section.
- Studio `TOOL_CATEGORIES` rewritten from 4 categories × 14 tools to 3 categories × 7 tools.
- `agents.md` (9 edits) and `CLAUDE.md` (7 edits, including L6's catch of the L5-missed `/workspace` parenthetical at line 58) brought into alignment.
- `tests/test_aiat.py` swept: `test_git_status` and `test_run_tests` deleted; `test_tool_use_file_read` and `test_multi_step` repointed to `/app/...`; `test_health` shape assertion fixed (pre-existing AIAT-only break).

### Mission Criteria Advanced

| Mission Success Criterion | Advanced by F1? |
|---|---|
| Tool surface focused on filesystem/execution/web; deployment/methodology/memory/git tools removed | ✅ Fully delivered |
| Default system prompt reflects general-purpose identity, no self-modification framing | ✅ Fully delivered (and refined further at L7 HAT) |
| Autopilot scheduling surface removed cleanly | ✅ Fully delivered |
| Stale tool names silently stripped via schema migration | ✅ Fully delivered (v7) |
| Filesystem tooling supports full lifecycle (read/write/edit/delete/move/mkdir/glob/grep) | Untouched (F3) |
| Execution tooling supports interactive sessions | Untouched (F4) |
| Subprocess env hardcoded-allowlist | Untouched (F4) |
| Web tooling SSRF-protected | Untouched (F5) |
| Per-tool constraints with narrowing-only override semantics | Untouched (F2 resolver scaffolding, F3-F5 use sites) |
| Two-layer config model (tool-level + agent-level overrides) | Untouched (F2) |
| Existing configs referencing removed tools load cleanly | ✅ Fully delivered (v7) |
| Admin tool-management surface | Untouched (F6) |
| Studio per-agent override surface | Untouched (F6) |
| Cross-platform-ready architecture | Untouched (F2) |
| Each tool has automated coverage for happy-path + constraint-violation | Partially advanced (existing tools' coverage preserved; new tools land F3-F5) |
| Tools admin section meets M04 quality bar | Untouched (F6) |

F1 fully delivered four of the sixteen criteria (the four assigned to it) and didn't regress any of the others. F1's job was the teardown; it did the teardown. F2 inherits a clean canvas to build on.

## What Went Well

**The seven design decisions held up in implementation.** Decisions 1, 2, 3, 5, 6, 7 executed verbatim with no architectural revision. Decision 4 (layered prompt) had three meaningful refinements but the core composition rule (additive, single separator, no escape hatch, single read site) was preserved. Architect's verdict: "F1 delivered all seven decisions … established the schema-migration locked-down pattern."

**Design-review-then-implement cadence caught real defects.** Across L1-L6, design reviews flagged:
- L1: grep over-scoping that would false-positive against `agents.md` (high) — fixed before implementation
- L2: forbidden-vocabulary list missing tools (medium); BASE_PROMPT tonal redlines for small-model accessibility (low) — applied
- L3: cursor idiom inconsistent with codebase (medium) — switched to `async with` matching `_get_version` and `repositories.py`
- L4: AC typo "five fields" vs four (medium); the Makefile L5 missed (low → folded into L4); CSS regression in L4→L5 window (medium) — documented as edge case
- **L5: five undefined CSS tokens (high — would have failed `test_token_definitions.py`)** — caught and rewritten using verified token names *before* implementation. This is the pattern's clearest save.
- L6: AC step 10 grep would catch L5-missed `CLAUDE.md:58` /workspace reference (high) — folded into L6 scope
None of the high-severity issues reached production code.

**HAT delivered design-level work, not just validation.** L7 minimized BASE_PROMPT from 296→202 words after the operator concluded that voice/tone prescriptions in the base fight the layered-composition contract. This is a substantive refinement to the layering allocation — discoverable only with a real LLM in the loop. Architect notes: *"Without L7 the flight would have shipped with a worse base/persona allocation."*

**Schema migration sets a strong pattern.** The v7 strip's NULL-preservation, locked-down-on-empty semantics, idempotency, and inline rationale comment (`schema.py:251-260`) establish a precedent for how future row-content migrations should handle privilege-relevant data. The `TestSchemaV7` rewind-`schema_version` testing technique is also reusable.

**Batched-commit pattern eliminates inter-leg coherence concerns.** The original spec planned for L1+L2 to "commit back-to-back" because L1 deletes tools the prompt mentions. Under agentic-workflow's post-L6 batch commit, this concern evaporates — L1+L2 are automatically a single observable release. Future flight specs can drop the back-to-back framing.

## What Could Be Improved

### Process

- **Stale line-citations decay.** Flight spec named two test files as the implicit-default sites for `Agent.__init__`'s `system_prompt`; both already passed explicit prompts. The actual six bypass sites were elsewhere. The L2 design audit caught this but cost a design-cycle. Recommendation: treat line-cited prereqs as **regenerable hints**, not contracts. Each leg-design phase should re-grep against current HEAD.
- **Test cleanup belongs with the source rip, not a deferred sweep.** The flight spec planned to clean up `test_behaviors.py`, `test_agent.py::TestDirectAction`, and three `test_config.py::direct_actions` references in L6's "test sweep." But L1's source-side deletions broke those tests immediately; they had to migrate to L1 to preserve the green-build invariant. F2-F7 should plan test cleanup as part of the source rip, not deferred. The agentic-workflow's batched commit makes this practically free.
- **Multi-leg config-removal flights need a `rg <field>` audit at flight-design time, not leg-implementation time.** Four of the recorded deviations (L4's `test_db_api.py`, `/api/info` `.deploy-status` block, `ci/deploy.sh`, `pipeline.yml CONCOURSE_PASS`) were logical-consequence edits that surfaced during L4 leg-design audit. The flight spec under-enumerated them. Recommendation: when a config field is removed, the flight spec should pre-enumerate every consumer.
- **CSS-token risk needs a pre-write check.** L5's original draft referenced five non-existent token names — caught by reviewer before implementation, but the leg's own design used token names from training-data muscle memory rather than from the project's actual tokens.css. Recommendation: any leg adding CSS rules must include a "grep tokens against `tokens.css`/`fonts.css`" step *before* writing the rule, not after.
- **Prompt-content review can't be auto-mode'd reliably.** L2 applied reviewer-suggested redlines to BASE_PROMPT in auto mode. L7 redid the redlines from scratch when the operator engaged. Two review cycles when one would have sufficed. Recommendation: prompt-content design decisions should either (a) defer content-review entirely to HAT, or (b) hard-block on operator review at design time. Don't pretend a Sonnet reviewer's redlines on prompt voice are equivalent to operator redlines.

### Technical

- **Stale "direct-action" comments in `app.py`.** Lines 415-422 and 448-453 still reference "the direct-action shortcut path" in the `chunks_seen` rationale comments. The code path is defensible (handles non-streaming providers) but the documentation now misrepresents it. Future maintainers grepping for "direct-action" will get false positives suggesting the rip is incomplete. **Action**: rewrite the comments to refer to "non-streaming providers" instead, or simplify the dead branch entirely.
- **No end-to-end test of layered prompt composition through the production path.** `tests/test_config.py::test_custom_prompt_appended` validates the composition at the `AgentConfig` level. No test asserts that an agent built via `AgentFactory.create()` with a non-empty `system_prompt` actually receives `BASE_PROMPT + separator + persona` as its `Message.system(...)`. The headline architectural feature of this flight is unit-tested, not integration-tested. **Action**: add an integration test in `tests/test_factory.py`.
- **No unit test for `/api/info` shape post-L5.** L5 added the `base_prompt` field via an ad-hoc Python smoke. L6's AIAT `test_health` covers it but only against a running container. **Action**: add a unit test in `tests/test_db_api.py` (or wherever `info()` is currently covered) that calls `info()` directly and asserts both keys.
- **No browser test for the new admin Base Prompt section.** L5 added `data-testid="base-prompt-content"` for testability but didn't follow up with an assertion. ~10-line Playwright test would close the gap.
- **Schema migration atomicity.** The v7 SELECT/UPDATE pair inside `ensure_schema()` runs without an explicit `BEGIN/COMMIT` wrapper. aiosqlite's default isolation means each UPDATE auto-commits — a process crash mid-migration could leave partial strips. Low probability, but schema migrations are exactly where atomicity matters. **Action**: wrap the v7 block in an explicit transaction.
- **Pre-existing pre-built-in CSS-token red carried through the entire flight.** `test_token_definitions.py::test_every_var_reference_is_defined` has been red since `18a0cd8` (flight 06). F1 didn't fix it (out of scope), but it's been red for the entire mission. Routine-maintenance candidate.
- **`test_aiat.py::test_health` "model" assertion was broken since the test was added.** L6 fixed it as an out-of-flight-spec edit. The lesson: AIAT live-only tests can rot indefinitely without a CI gate that surfaces persistent reds. Routine-maintenance candidate.

### Documentation

- **Layered-prompt model has no `agents.md` reference.** The flight spec's table (`Layer | Scope | Where it lives`) is excellent material. It should live in `agents.md` as a permanent reference, not just in a flight artifact (which gets archived). The L7 minimization decision (base prompt = mechanical requirements only; identity/voice = persona) should be the documented principle.
- **`/api/info` contract is undocumented.** New `base_prompt` field has no API doc. The contract that *only the static base prompt* (not runtime context) flows through this field is load-bearing for security and should be written down.
- **Schema migration policy isn't captured.** The v7 strip's "row-content migrations preserve operator intent under tightening, never widen scope" decision is in the inline comment but should be a reusable principle in `agents.md`. Future schema bumps will hit the same dilemma.
- **HAT-as-design-completion-gate isn't formalized.** L7 reshaped BASE_PROMPT semantically. Future flights with HAT legs should plan for design-completion, not just feel-validation. Worth promoting from this flight to an `agents.md` "When to require HAT" section.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L1 absorbed test cleanup (`test_behaviors.py`, `TestDirectAction`, `direct_actions` refs) originally scoped to L6 | Green-build-between-legs invariant — leaving those after L1's source-side rip would break the suite | **Yes**: test cleanup belongs with the source rip, not a deferred sweep |
| L2 corrected the flight-spec's two-sites-named bypass-prompt audit (six actual sites in `test_agent.py`) | Spec was authored before another flight shifted line numbers; cited prereqs were stale | **Yes**: re-grep cited prereqs at leg-design time |
| L3 inline-repaired `tests/test_schema.py` (imported `CURRENT_VERSION`, replaced literal `6` with symbol, renamed test) | Schema bump broke baseline; required for green-build | **Yes**: test assertions against schema state should reference constants, not literals |
| L4 four logical-consequence edits (`test_db_api.py`, `/api/info` `.deploy-status` removal, `ci/deploy.sh` parallel cleanup, `pipeline.yml CONCOURSE_PASS` drop) | Removing `Settings.workspace_dir` cascaded; flight spec under-enumerated consumers | **Yes**: pre-flight `rg <field>` audit before leg design |
| L5 added `dev_mode` to System page Server section (not in original flight spec) | Post-L4 `Settings.model_fields` reduction would have left `dev_mode` invisible to operators | **Yes**: when shrinking config visibility, audit which surviving fields lose their UI surface |
| L6 fixed `test_aiat.py::test_health` "model" assertion (pre-existing AIAT-only break) and `CLAUDE.md:58` stale `/workspace` parenthetical (L5 oversight) | Caught by regression sweep; both required for L7 HAT path coherence | **Yes**: docs-cleanup legs should self-grep their just-touched files; AIAT live tests need a CI gate against persistent reds |
| L7 minimized BASE_PROMPT from 296 → 202 words (operator-driven) | Voice/tone prescriptions in base prompt fight per-agent persona freedom | **Yes**: base prompt = mechanical requirements only; identity/voice = persona |

All seven deviations are healthy adaptations, not architectural surprises. The pattern across most of them is the same: **flight specs under-enumerate consumers and decay against drifting line-citations.** The leg-design phase is the right place to catch this, but flight spec authors can preempt it with field-name greps and test-suite audits.

## Key Learnings

1. **Flight spec line-citations are hints, not contracts.** Re-audit at leg-design time. Other flights modify line numbers between flight authoring and flight execution.
2. **Test cleanup is part of the source rip.** Defer-to-sweep models break the green-build invariant under batched commits. The agentic-workflow's batched commit makes inline cleanup practically free.
3. **HAT is design-completion, not just feel-validation.** L7's BASE_PROMPT minimization reshaped the layering contract. Future prompt-rewrite flights should treat HAT as a gate, not a victory lap.
4. **Locked-down-on-ambiguity is the right default for privilege-relevant migrations.** Document the reasoning inline so future readers don't accidentally widen.
5. **Batched commits eliminate inter-leg coherence concerns.** Drop "back-to-back" framing from future flight specs.
6. **`textContent` over `innerHTML` for server-supplied admin data** — pattern worth codifying.
7. **Pre-write CSS-token verification is mandatory for any new rule.** Reviewer-saved-the-day cases are still cases-saved; standardize the check pre-write.
8. **Pre-existing red tests carried indefinitely is a maintenance smell.** AIAT `test_health` and `test_token_definitions::test_every_var_reference_is_defined` both predate F1; both should land on routine-maintenance.

## Recommendations

1. **Update flight skill / leg template**: re-grep line-cited prereqs at leg-design time; flight specs should include `rg <field>` consumer-audit when removing a config field; CSS-rule legs must include pre-write token verification step.
2. **Move test cleanup into the source rip leg in F2-F7.** Don't defer to a trailing sweep.
3. **Document the layered-prompt model in `agents.md`.** Copy the flight spec's `Layer | Scope | Where it lives` table; capture the L7 minimization principle (base = mechanical, persona = voice). Add `/api/info` contract documentation.
4. **Add three test gaps**: integration test for layered prompt composition through `AgentFactory.create()`; unit test for `/api/info` shape; browser test for admin Base Prompt section using the existing `data-testid`.
5. **Wrap v7 (and future row-content) migrations in an explicit transaction** for atomicity.
6. **Clean up stale "direct-action" comments in `app.py`** and decide whether to keep the `chunks_seen` guard or simplify it.
7. **Promote HAT-as-design-completion-gate to a documented principle.** Worth an `agents.md` section.

## Action Items

- [ ] **Routine-maintenance pass** (next after PR merge): fix the pre-existing CSS-token red (`--font-size-h3` missing); fold the `make rebuild` Playwright Chromium pre-install into `test-browser`/`hat` only.
- [ ] **F2 design preflight**: include a `rg` consumer-audit for any config field F2 plans to add or remove. Re-audit Decision 4's "two read sites" claim against current HEAD before locking it as a prereq.
- [ ] **F2 design**: reconcile the new `tool_overrides` AgentConfig field with the `enabled_tools=NULL` semantics (triple-NULL resolver decision needs documentation).
- [ ] **F3 design preflight**: list every path-shaped string-literal in `the_one/interfaces/web/app.py` and `tests/test_aiat.py`; verify each survives the proposed default path-allowlist scope to avoid the L4-style `/api/selftest` near-miss.
- [ ] **F5 design**: address the `web_search` empty-DuckDuckGo-results issue surfaced at L7 HAT (recorded in mission Known Issues).
- [ ] **Documentation pass** (could pair with F6): update `agents.md` with the layered-prompt model table + composition principle + `/api/info` contract + schema-migration locked-down policy + when-to-require-HAT.
- [ ] **Test backfill** (could pair with F2 or as a standalone maintenance leg): add the three identified test gaps (composition integration, `/api/info` unit, admin Base Prompt browser).
- [ ] **CI gate against persistent reds** in AIAT: ensure `pytest -m live` is run somewhere that surfaces failures, otherwise live-only assertions rot like `test_health::"model" in data` did.
- [ ] **Refactor**: rewrite stale "direct-action" comments in `app.py:415-422,448-453` to reference "non-streaming providers" or simplify the dead branch.
