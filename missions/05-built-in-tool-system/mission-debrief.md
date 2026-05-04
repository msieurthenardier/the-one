# Mission Debrief: Built-In Tool System

**Date**: 2026-05-04
**Mission**: [Built-In Tool System](mission.md)
**Status**: completed
**Duration**: 2026-04-28 (F1 design start) → 2026-05-04 (F6 landed)
**Flights Completed**: 6 of 6 planned non-optional flights (F7 alignment was optional and not required — F6 HAT absorbed alignment work)

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| Built-in tool surface focused on filesystem/execution/web; deployment/methodology/memory/git tools removed without breaking M01-M04 capability | ✅ Met | F1: 7 tools deleted, 14→7 surface, 305+/1263- LoC. M01-M04 functionality preserved. |
| Default system prompt is general-purpose; no self-modification/deployment/methodology framing | ✅ Met | F1: `BASE_PROMPT` 296→202 words after L7 HAT operator review. Layered composition with persona. |
| Autopilot scheduling surface removed cleanly with CI plumbing | ✅ Met | F1: pipeline trimmed from 6 jobs+1 resource to 1 job (`deploy` w/ `auto-rollback`). |
| Filesystem lifecycle: read/write/edit/delete/move/mkdir/glob/grep with predictable constraint behavior | ✅ Met | F3: 9 filesystem tools, 4 constraint types (path allowlist NarrowPrefix, denylist NarrowSuperset, read-size cap, binary refusal). |
| Execution: one-shot + interactive multi-command sessions, isolated per-agent | ✅ Met | F4: shell/python_exec hardened; `shell_session_*` tools on Unix PTY; per-agent session registry. |
| Subprocesses inherit only minimal hardcoded env allowlist | ✅ Met | F4: `platform/env.py` `_build_subprocess_env` enforces fixed allowlist at all 3 execution call sites. HAT scenario 5 verified. |
| Web: HTTP, reader-mode, file download, pluggable search; SSRF default-block with curated opt-out | ✅ Met | F5: `fetch_url` + `download_file`; `SSRFGuardedTransport` resolve-then-pin against loopback/RFC1918/link-local/cloud-metadata; IP-literal short-circuit added at L7 HAT. `SearchBackend` Protocol w/ DDG default. |
| Tool-level constraints + agent-level narrowing-only override at single named resolution layer | ✅ Met | F2: `ToolPolicyResolver.resolve()`; F3 added `NarrowPrefix`/`NarrowSuperset` markers; F3-F5 each consume the same resolver. |
| Two override semantics — narrowing AND substitution — implemented; ready for MCP without restructuring | ✅ Met | F2: both paths shipped; substitution exercised via fixture Configs. F5 stretched the contract: `cross_configs` widened to `dict[type, object]` to accept Protocol-keyed services alongside Pydantic Configs. |
| Existing agent configs referencing removed tools load cleanly via schema migration | ✅ Met | F1: schema v7 strips removed names from `enabled_tools`/`disabled_tools` JSON; NULL preserved as NULL (no privilege escalation). |
| Admin tool-management surface with per-tool enable/disable/configure + verification controls | ✅ Met | F6: `Settings → Built-in Tools` peer section; per-category tabs; per-tool editor driven by marker-enriched JSON Schema; test panels for `web_search`/`fetch_url`. |
| Studio reflects tool-level state + per-agent override surface for narrowing | ✅ Met | F6: tool-disabled tools show strikethrough+dim+tooltip; marker-aware widgets (Narrow ceiling, NarrowSuperset locked chips, Substitute free-form). |
| Cross-platform-ready architecture; Linux-verified | ✅ Met | F2: `the_one/platform/` (paths, shell, interpreter, env, pty, tempdirs); F4 `PtySession` ABC + `UnixPtySession`; Windows ConPTY explicitly deferred. |
| Each kept tool has automated coverage for happy-path + constraint-violation | ✅ Met | F3 +75, F4 ~150+, F5 +157, F6 +34 browser tests. 522→700+ unit tests across mission. |
| Tools admin section meets M04 quality bar without alignment-flight rework | ✅ Met | F6 HAT iterated UX in-flight (per-category tabs, error banner, info-icon tooltips, custom test inputs); F7 alignment unnecessary. |

**All 15 success criteria met.** F7 (alignment) was scoped as optional and proved unnecessary — F6's HAT-driven UX iteration absorbed the work that would have required a separate alignment flight.

### Overall Outcome

The mission delivered exactly what was scoped: the self-modification surface is gone (cleanly, with no regression in M01-M04), three focused tool categories now exist with operator-controlled bounds, the resolver pattern is shipped and ready to absorb MCP integration without restructuring, the platform layer isolates Linux-only assumptions behind a clear seam, and operators have a real admin surface for tool-level + agent-level configuration. The mission also delivered substantive architectural infrastructure beyond the success criteria — frozen Pydantic Configs as cross-tool dispatch values, the `cross_configs`/`Requires` plumbing, the `_session_registry` async-lock idiom, schema migrations v7-v9 reinforcing one shape — all of which become load-bearing for MCP work.

The pivot the mission was built on (parking the self-modifying-agent narrative for general-purpose-personal-assistant) is validated by the result: removing the deploy/rollback/restart loop did not create operational gaps, and the new direction feels structurally cleaner than the one it replaced. The deletion was the correct decision.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1: Tool Reduction & Self-Modification Teardown | completed | 7 tools deleted; `BASE_PROMPT` rewritten (general-purpose, layered with per-agent persona); Concourse trimmed to single `deploy` job; schema v7 migration strips removed tool names. Net –975 LoC. |
| F2: Cross-Platform Foundations & Policy Resolver | completed | `the_one/platform/` package (paths/shell/interpreter/tempdirs); `ToolPolicyResolver` with `Narrow`/`Substitute` markers; schema v8 (`tool_configs` + `agents.tool_overrides`); 7 existing tools migrated; `run_shell`/`run_python` strictly more robust than legacy `proc.kill()`. |
| F3: Filesystem Expansion & Constraints | completed | 9 filesystem tools (`edit_file`/`delete_file`/`move_file`/`mkdir`/`glob`/`grep` added); `NarrowPrefix`/`NarrowSuperset` markers; `ConstraintError` typed exception; `[error] [constraint] {msg}` envelope. HAT separated comprehensibility (wording-fixable) from agency (capability floor). |
| F4: Execution Expansion & Constraints | completed | `ExecutionConfig`/`PythonExecConfig`; PTY session tools (`shell_session_*`) on `UnixPtySession`; `platform/env.py` env allowlist; `cross_configs` + `Tool.Requires` plumbing for cross-tool dispatch; `_session_registry` snapshot-under-lock idiom. WebSocket UX bugs surfaced by 120s timeout cap fixed in follow-up commits. |
| F5: Web Expansion & Constraints | completed | `WebConfig`; `FetchUrlTool` + `DownloadFileTool`; `SSRFGuardedTransport` (resolve-then-pin against loopback/RFC1918/link-local/cloud-metadata, SNI-preserved, IP-literal short-circuit); `SearchBackend` Protocol w/ DDG fix for F1's known issue; four-clause envelope for httpx tools. L0 unified F3+F4 filesystem-check helpers behind `CheckMode`. |
| F6: Tools Admin Section | completed | `Settings → Built-in Tools` peer section; per-category tabs at 19-tool surface; marker-aware editor (`tools-form-helpers.js` shared substrate); test panels w/ custom inputs; Studio per-agent override panels w/ marker-aware widgets; schema v9. Two-Reviewer-pass batching debuted with zero stale-doc deviations. |

## What Went Well

**Architect-review-per-leg cadence consistently caught high-severity bugs at design time.** F2 caught a Pydantic v2 `BaseModel()` instantiation bug that would have broken every existing tool. F4 caught a registry-deadlock pattern (lock held across `~1s` SIGTERM/SIGKILL ladder). F5 caught five library-API drifts (SNI preservation via `request.extensions["sni_hostname"]`, DNS-rebind defense, allowlist marker semantic). F6 caught a cross-Config shadowing bug in the test endpoint that would have run `web_search` through `http_request`'s saved config silently. The pattern's catch rate stayed high enough to be load-bearing — the mission likely shipped 4-6 fewer production defects because of it.

**HAT proved to be a design-completion gate, not a victory lap.** Five flights had HAT phases (F1, F3, F4, F5, F6) and every single one surfaced findings that no unit test could have caught: F1 minimized `BASE_PROMPT` 296→202 words after the operator concluded voice/tone belongs in persona, not base. F3 distinguished comprehensibility (fixable by wording) from agency (model capability floor) via Qwen 2.5:7b vs. Haiku 4.5 re-verification. F4 surfaced WebSocket UX bugs that were pre-existing but made deterministic by the 120s timeout cap. F5 caught the IP-literal SSRF bypass. F6 batched seven UX revisions in one Developer pass (per-category tabs, error banner, info-icon tooltips, custom test inputs, iOS-toggle CSS, chip-list polish). The cumulative case for HAT-as-mandatory is now strong.

**The two-layer config model survived three consecutive expansion flights without restructuring.** F3 added `NarrowPrefix`/`NarrowSuperset` markers on top of F2's `Narrow`/`Substitute` without touching the resolver core. F4 added `cross_configs` + `Tool.Requires` for cross-tool dispatch. F5 widened `cross_configs` from `dict[type[BaseModel], BaseModel]` to `dict[type, object]` to admit Protocol-keyed services. None of these required reverting earlier decisions. The provider-drives-resolution choice (F2 D7) was the load-bearing call — it generalizes naturally to MCP servers sourcing schemas from runtime manifests.

**Schema migrations established a stable shape.** Three migrations across the mission (v7 row-content strip, v8 table+column, v9 idempotent ALTER) reinforced the same conventions: idempotent via `IF NOT EXISTS` + `PRAGMA table_info`, individual `await conn.execute(...)` not `executescript`, `INSERT OR IGNORE INTO schema_version` runs LAST, NULL-preservation under privilege-relevant strips. This is now a documented pattern future migrations will follow.

**Two-Reviewer-pass batching debuted in F6 and worked.** F4/F5 each had 4 stale-doc deviations from L8 doc authors working from spec rather than as-built. F6 split: first Reviewer pass on code correctness across L0-L8, second Reviewer pass on doc-vs-code accuracy after L9. Zero stale-doc deviations in F6. Cost was small (~78 insert / 3 delete to verify in the second pass). Net-positive at the F6 scale (50 files, +10414 LoC, 9 implementation legs).

**Methodology contributions accumulated cleanly.** Each flight produced reusable patterns the next inherited: F1's layered-prompt model + schema-migration locked-down pattern → F2's resolver markers + kill+reap subprocess robustness → F3's `ConstraintError` envelope + helper-strictness gradient → F4's three-clause envelope + cross-Config dispatch + snapshot-under-lock → F5's four-clause envelope (httpx) + scaffolding-leg consumer test → F6's two-Reviewer-pass + shared-substrate JS extraction. The cross-flight pattern handoff was effectively friction-free.

## What Could Be Improved

**The configuration surface area is larger than initial scoping anticipated.** Operator feedback flagged this as the biggest mission-level surprise: 19 tools (was 13), each with its own marker-enriched Config, and ~80+ ongoing per-key narrow/substitute decisions across all of them. The two-layer model is correct, but the long-term validation surface — operator-facing UI tooltips, per-tool constraint semantics, the bool-narrowing convention (`True → False is narrowing`), the asymmetry between tool-level vs. agent-level fields — will need sustained attention as agents and operators learn to navigate it. The admin surface is a first-cut substrate, not a finished product. **Implication for future missions**: any flight that adds a Config field also adds documentation/UX surface; the F6 admin surface is the single point of operator-discoverability and should not be allowed to drift behind tool additions.

**Doc-refresh ordering caused recurring drift.** F4 and F5 each had 4 stale-doc deviations from L8 doc authors working off spec rather than as-built code. F6 fixed this with two-pass batching but at additional methodology cost. The class problem — "spec drifts from implementation as architect catches accrue, doc author works from spec" — recurs whenever a doc-refresh leg lands before the Reviewer pass. The two-Reviewer-pass pattern works but should be made the default at the right scale threshold rather than discovered per-flight.

**Library-API drift is a systemic risk.** F5 had 5/5 high-severity L1-L3 catches in this class (SNI preservation, deprecated `asyncio.get_event_loop()`, marker semantic for allowlist, etc.). All five came from leg-spec authoring relying on training-cutoff knowledge rather than verifying against installed-version docs. This will compound for MCP work where the library landscape (`anthropic-mcp`, `httpx`, `pydantic`, etc.) is evolving fast.

**Live-environment provisioning surfaced too late repeatedly.** F2 hit a pytest-base-url ScopeMismatch at L4 implementation (not design). F2 hit dev-DB provider-seeding gaps at L7. F4 needed a uvicorn `--reload` fix as a follow-up. F4/F5 each had bind-mount widening mid-flight. The class problem is "scaffolding flights' environmental dependencies aren't audited before legs start." A pre-flight environmental-provisioning audit would catch this before HAT.

**Helper-set strictness gradient was under-specified twice.** F3 L3 retroactively added `_filesystem_check_write_path` because L2b's helper set didn't account for the auto-create-parents contract. F4 hit similar trouble at L1's `_truncate_output` consumer mismatch. F5 L0 finally unified everything under `CheckMode` but the cleanup was deferred-then-belatedly-done. **Implication**: any leg introducing helpers should specify the strictness matrix (must-exist / may-exist / must-not-exist) and consumer count up front.

**Small-model agency limits surfaced as project-relevant.** F3 HAT against Qwen 2.5:7b discovered agents loop or fabricate when constraint scenarios require multi-step recovery. Confirmed model-agnostic-correct via Haiku 4.5 re-verification — the wording is well-formed; this is a model-capability floor. The mission's "small-model friendly" constraint conflated comprehensibility (wording-fixable) with autonomous recovery (capability-bounded). Future flights should target comprehensibility in error strings; recovery is a model+prompt concern with a known floor.

**Documentation handoffs from F1 are still in flight.** F1 debrief flagged "layered-prompt model has no `agents.md` reference." F2 carried it forward. F3-F6 didn't fully absorb it. Specific docs that have been deferred for ≥2 flights: layered-prompt-model table; `/api/info` contract; schema-migration locked-down policy as a principle; `ConstraintError` + envelope shape as project-wide. The F6 two-Reviewer-pass got F6's docs in good shape; F1-F5's residual debt is still owed.

## Lessons Learned

1. **The two-layer config model + resolver markers compose well.** Three expansion flights (F3, F4, F5) plus the operator surface (F6) extended the contract without regressing it. The pattern is ready for MCP. The marker-class identity-dispatch (`m is Narrow`) with `Annotated[T, Marker]` is reusable for any future per-key declarative dispatch.

2. **HAT ≠ validation; HAT = design completion.** Every HAT phase produced substantive design refinement, not just confirmation. Future flights touching user-visible constraint behavior, prompt content, or operator UX should treat HAT as a gate, not a verification step.

3. **Architect-review-per-leg has a sustained ~30-50% catch rate** for high-severity issues. F5's library-API drift catches (5/5) suggest the leg-design template should explicitly require verifying third-party library APIs against installed-version docs, especially as MCP brings more SDK surface area.

4. **Schema migrations under tightening preserve operator intent; never widen scope under ambiguity.** F1's v7 NULL-preservation rule and the inline rationale comment establish a precedent. Future schema bumps that touch privilege-relevant data should follow the same shape.

5. **Scaffolding-leg consumer tests prevent integration-time discovery of envelope mismatches.** F4 debrief recommendation; F5 L1's `_StubWebTool` proved the pattern. Codify as default for any leg landing helpers without immediate consumers.

6. **Cross-Config dispatch widens naturally from frozen Pydantic to Protocol-keyed services** as long as the per-call lifecycle replaces frozenness as the safety mechanism. The F4→F5 transition validates this. MCP-arrived runtime services (server connections, OAuth identities) will fit the same shape.

7. **The Linux/WSL-only verification target was the right scope-narrowing for this mission.** The platform-abstraction layer (F2) is real (`PtySession` ABC, `_run_shell`/`_run_python`, `_build_subprocess_env`) but Windows/macOS validation would have ballooned scope. Future cross-platform mission can swap implementations rather than rewrite tool code.

8. **Removing systems is a coordinated multi-flight investment.** F1's net –975 LoC seven-tool teardown could not have shipped as a single leg without breaking M01-M04. Decomposing into design-decisions-per-component (Concourse pipeline, schema migration, prompt rewrite, test cleanup, docs alignment) and validating M01-M04 preservation at each step was the right shape.

9. **Operator surprises happen at the *aggregate* level.** Individual tools/Configs each look reasonable in isolation; the sum across 19 tools is not. Future expansion missions should explicitly include a "configuration surface tally" deliverable (count of fields × tools × markers) so the operator-facing scope is visible at flight-design time.

## Methodology Feedback

**Promote to convention/skill update:**

1. **Architect-review-per-leg as standard cadence** for any leg modifying a security-bearing surface or introducing new architectural patterns. F4-F6's design-pass-per-leg evidence is now sufficient to default-on.
2. **Two-Reviewer-pass batching** in `agentic-workflow` skill. Threshold recommendation: flights with ≥5 legs OR ≥1 new shared-substrate module OR ≥1 new public API surface default to two-pass. Below that, single-pass with "doc author reads as-built" admonition is fine.
3. **HAT as design-completion gate** for any flight touching user-visible constraint behavior, prompt content, WebSocket lifecycle, or operator UX. Promote from "optional verification leg" to "mandatory design-completion gate" at the right scope threshold.
4. **HAT scope must enumerate per-threat-vector scenarios** for security-bearing surfaces (F5 IP-literal lesson). Generic "happy + violation" rubrics miss subclasses.
5. **Library-API drift checklist in leg-design template**: for each third-party library touched, document the installed version and verify API shape against current docs (not training-cutoff knowledge).
6. **Pre-flight environmental-provisioning audit**: any flight with AIAT or browser-test dependencies surfaces environment requirements at flight-design time, not at L7.
7. **Scaffolding-leg consumer test requirement**: any leg landing helpers without immediate consumers ships at least one consumer-facing test through a stub.
8. **Helper-set strictness gradient specification at flight-design time**: enumerate {strictness, context-of-use} matrix across the entire flight, not per-leg.
9. **Pre-flight `rg` consumer-audit when removing a config field**: pre-enumerate every consumer to avoid leg-time logical-consequence discoveries.
10. **Leg artifacts are spec snapshots, not as-built records.** Document explicitly in `agentic-workflow` skill so future contributors know flight-log Deviations is the canonical as-built diff index.
11. **Pin merge-vs-replace explicitly for any new PUT endpoint** at flight-design time (F6 D11 was a leg-time discovery).
12. **HAT-induced test growth is a separate budget line** (~2x multiplier per F6 data point). Flight-design test estimates should account for HAT-discovery regression coverage.

**Project-level conventions to document in `agents.md` / `CLAUDE.md`:**

- Layered-prompt model (base = mechanical, persona = identity/voice).
- `/api/info` contract.
- Schema-migration locked-down policy as a principle.
- `ConstraintError` + tool authorship contract (three-clause vs. four-clause envelope; float-preserving timeout clip; two-phase lock-and-await; frozen Configs vs. per-call-fresh services in `cross_configs`).
- Resolver-as-security-boundary statement ("client-side widget shape is UX; resolver at AgentFactory.create() is the security check").
- First-tool-wins cross-Config semantic at the `builtins.py` dispatch site.
- Bool/int/list narrow semantics (`True → False is narrowing`).
- JSON-encoding gotcha for Pydantic 422 (`include_context=False`) — audit all FastAPI endpoints.
- Async-lock idiom ("snapshot under lock, close after release") as a documented pattern.
- "Small-model friendly" refined: comprehensibility (wording-fixable) vs. autonomous recovery (capability-bounded).
- F3 threat model ("operator-trusted setup, NOT malicious filesystem actor") inherited by F4/F5.

## Action Items

### Routine maintenance pass (recommended before next mission)

- [ ] Extract duplicated `_kill_process_tree` from `platform/shell.py` and `platform/interpreter.py` to `platform/_subprocess.py`.
- [ ] Extract `TOOL_CATEGORIES` triplication (`admin/tools-grid.js`, `admin/tools-editor.js`, Studio `tools-tab.js`) to `tools-form-helpers.js`.
- [ ] Promote `humanizeValidationMsg` to a shared `App.humanize` utility; de-duplicate the mirror.
- [ ] Audit FastAPI endpoints (providers/agents/kbs/mcp) for `ValidationError` JSON-encoding (`e.errors(include_context=False)` should be project default); add regression tests for the model-validator path.
- [ ] Drop `_ensure-playwright` from Makefile `up`/`rebuild`; keep only in `test-browser`/`hat`.
- [ ] Wrap schema migration row-content updates in explicit transactions (atomicity carried forward from F1 → F2 → F4 → F6).
- [ ] Migrate `_filesystem_check_write_parent` / `_filesystem_check_write_path` shim call sites to direct `CheckMode` form, then delete the shims.
- [ ] Add IPv6 IP-literal SSRF regression test (`http://[::1]/`).
- [ ] Add edge-case tests: stale-narrow override factory-raise; chip-list non-string items; panel close-during-fetch race.
- [ ] Fix `agent/factory.py` duplicate comment "3" numbering.
- [ ] Document drift-warn behavior at `tools-tab.js:194-196` in CLAUDE.md F6 section.
- [ ] Add regression test for `list_dir` not filtering denylisted descendants.

### Documentation backlog (carried forward from F1, F2 debriefs)

- [ ] Add layered-prompt-model section to `agents.md` (F1 → F2 → carryforward).
- [ ] Document `/api/info` contract.
- [ ] Schema-migration locked-down policy as a reusable principle.
- [ ] Tool authorship contract section in `CLAUDE.md` consolidating F2-F6 patterns.
- [ ] Cross-Config dispatch documented at `builtins.py:120-127` and `agents.md`.
- [ ] Resolver-as-security-boundary statement in CLAUDE.md.
- [ ] F3 threat model documented once for F4/F5 inheritance.
- [ ] Bool-narrowing semantic in operator-facing tooltips.
- [ ] HAT-as-design-completion-gate principle in `agents.md` "When to require HAT" section.
- [ ] Test conventions (`tests/CONVENTIONS.md` + `agents.md` Test Conventions section) — most done in F3, gaps remain.

### Pre-MCP architecture work

- [ ] Promote `cross_configs` keying contract to documented + tested first-class API (lift out of `builtins.py`).
- [ ] Make `Requires` enforced (project `cross_configs` per-tool based on `cls.Requires`) before MCP work begins.
- [ ] Generalize `_enrich_schema_with_markers` to accept JSON Schema input (translation layer for MCP tool-config JSON Schema → Pydantic `Annotated` markers).
- [ ] Widen session-registry keying from `(agent_name, session_id)` to admit MCP provider/session identity.
- [ ] Address `max_concurrent_sessions` race with `register_if_under_cap()` registry helper before any surface admits parallel tool calls per agent.
- [ ] Address default-factory resolver gap (`NotImplementedError` when `tool_config={}` AND agent override sets list-narrowing field).
- [ ] Split `ToolConfigRepository.upsert` into `update_config()` / `update_enabled()` to remove last-write-wins footgun.

### Methodology updates (mission-control skill repo)

- [ ] Update `/agentic-workflow` skill: pin two-Reviewer-pass batching threshold; document leg artifacts as spec snapshots.
- [ ] Update `/flight` skill: HAT-rubric requirement for security-bearing surfaces; HAT-induced-test budget line; WebSocket/long-running HAT scenarios.
- [ ] Update `/leg` skill: doc-refresh leg runs AFTER Reviewer pass; library-API-version checklist; helper-set strictness gradient field; AC.tests-claimed consistency check; scaffolding-leg consumer-test requirement; pre-flight `rg` consumer-audit on config-field removal.
- [ ] Update `/routine-maintenance` skill: dev-loop friction primitives check (source/tests bind-mount, uvicorn `--reload`, Playwright pre-install); pre-flight environmental-provisioning audit.

### Mission Known Issues to carry forward (deferred, not closed)

- [ ] Qwen 2.5:7b small-model agency limits on `read_size_cap_exceeded` retry-loop and `edit_file` multi-match fabrication (model-capability floor; no fix planned).
- [ ] `python_exec` exit-code-suffix behavior change (now project contract; agent prompts referencing pre-F4 shape need updating).
- [ ] Chip-list editor UX polish (commit-on-Enter affordance, pill density, Add button, flash-on-add) — future UX-polish flight or maintenance pass.
