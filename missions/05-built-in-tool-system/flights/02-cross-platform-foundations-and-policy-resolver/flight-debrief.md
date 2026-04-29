# Flight Debrief: Cross-Platform Foundations & Policy Resolver

**Date**: 2026-04-29
**Flight**: [Cross-Platform Foundations & Policy Resolver](flight.md)
**Status**: landed
**Duration**: 2026-04-29 (single-day execution via /agentic-workflow)
**Legs Completed**: 7 of 7

## Outcome Assessment

### Objectives Achieved

F2 delivered both coupled deliverables exactly as scoped:

- **`the_one/platform/` package** — paths/shell/interpreter/tempdirs submodules abstracting platform-divergent concerns. Cross-platform contracts documented; Linux/WSL verified. The `run_shell` / `run_python` helpers go beyond the spec — kill+reap with `start_new_session=True` + `killpg(SIGKILL)` + second `communicate()` to drain pipes — which is strictly more robust than today's `proc.kill()`-only behavior. This was discovered as an L1 anomaly fix; the platform helpers are now a cleanly-isolated improvement.

- **ToolPolicyResolver** — pure-function `resolve(schema, tool_config, agent_override) -> BaseModel` with `Narrow` / `Substitute` sentinel markers, per-type narrow comparison rules (bool True→False, int cap, list subset), and tested narrow + substitute paths via fixture Pydantic Configs. The resolver is invoked once at `AgentFactory.create()`; resolved configs flow into per-agent tool instances via `__init__(config)`.

- **Schema v8 migration** — `tool_configs` table (PK name, JSON config) + `agents.tool_overrides` column (TEXT, nullable, no DEFAULT NULL clause). `INSERT OR IGNORE` on `schema_version` neutralizes the concurrent-`ensure_schema` PK-violation race. Tested on fresh DB, v7-fixture DB, idempotent re-run, and chained v6→v7→v8.

- **All 7 tools migrated** through the Tool ABC contract with byte-for-byte behavior preservation. Filesystem + execution tools route through the platform layer; web tools needed no source changes (httpx is already cross-platform) but gained 12 regression tests via `httpx.MockTransport` to lock in formatted-string contracts ahead of F5.

- **Bonus L7 fix**: pre-existing pytest-base-url ScopeMismatch resolved with single-line `@pytest.fixture(scope="session")` change. AIAT live smoke now runs (2 pass, 4 environmentally gated on dev-DB provider seeding).

### Mission Criteria Advanced

The flight contributed materially to four mission success criteria:

| Criterion | Advanced |
|-----------|----------|
| "Each tool category enforces tool-level constraints ... at a single named resolution layer" | F2 built the resolution layer (`ToolPolicyResolver`); F3-F5 will add real values |
| "Two override semantics — narrowing and substitution ... designed to absorb substitution case without restructuring" | Both paths implemented and unit-tested via fixture |
| "Filesystem and execution tooling architected for cross-platform support ... isolated behind a clear abstraction layer" | Platform package ships; tools migrated |
| "Existing agent configurations referencing removed tools load cleanly" | F2's v8 migration adds `tool_overrides` and `tool_configs` without disturbing existing rows |

### Checkpoints

All 7 of the flight's defined checkpoints checked off in `flight.md::In-Flight::Checkpoints`. All 12 Completion-Checklist items checked off in `flight.md::Post-Flight`.

## What Went Well

- **Design discipline**: 8 of 10 design decisions held verbatim into implementation; 1 (Decision 5: Tool.Config default) was caught and refined at L3 design review BEFORE coding (Pydantic v2 forbids bare `BaseModel()`); 1 (Decision 7: regression-only) had a forward-cost (AIAT environmental gap) but the contract held. Design-review pipeline worked — the failure mode was caught upstream of implementation.

- **Copy-don't-cut pattern (L1)**: writing the platform helpers alongside the existing platform-coupled code paid off cleanly across L4-L6. Each tool migration was a 1-3 line swap with regression tests proving behavior unchanged. Zero scope creep, zero L1-rework.

- **Two flight-log anomalies caught and fixed at L1 implementation**:
  1. `asyncio.run` in tests broke `test_provider_repository.py`'s legacy `asyncio.get_event_loop().run_until_complete` pattern — fixed by writing tests as `async def` (rely on pytest-asyncio's `asyncio_mode = "auto"`).
  2. `proc.kill()` alone doesn't unblock `proc.communicate()` for shell-spawned subtrees — fixed with `start_new_session=True` + `killpg(SIGKILL)` + second `communicate()`. **This is strictly more robust than legacy `ShellTool.execute` behavior.**

- **Per-leg design review caught the high-severity Pydantic instantiation bug** (L3 first-pass review). The fix (`_EmptyConfig` private sentinel) was applied at design time, not after implementation broke 7 tools.

- **L6 anticipated zero-source-change correctly**: the leg-design review re-verified twice that no source migration was needed for web.py, then L6's `git diff -- the_one/tools/web.py` confirmed empty. No false-effort leg.

- **Test coverage strong**: 522 unit tests passing (+127 net new across L1-L6: 30 platform + 25 schema/repo/config/api + 37 resolver/Tool-ABC + 12 filesystem + 11 execution + 12 web). Pre-existing CSS-token red unchanged.

- **L2 SQL audit was exhaustive**: every site needing update was enumerated with line citations at flight-design time, then re-grepped at L2 leg-design per F1's "line citations decay" lesson. Implementation went smoothly.

- **Per-agent isolation invariant proven**: today's latent bug (shared singleton tools) is now fixed; verified by per-agent isolation smoke at L3.

## What Could Be Improved

### Process

- **Live-environment provisioning gap surfaced too late.** The pre-existing pytest-base-url ScopeMismatch was discovered at L4 implementation (not design); subsequent legs deferred AIAT to L7. The dev-DB default-agent-no-provider issue (4 AIAT tests still gated) was only surfaced at L7. **Recommendation**: scaffolding flights (Decision 7 regression-only) should include a "live-environment provisioning audit" sub-checklist at flight-design time so environmental dependencies are surfaced before any leg starts.

- **L3 spec was overweight (~536 lines)**. The factor-of-the-factor "factory-drives vs provider-drives" decision was thoroughly argued in `flight.md` AND re-argued in the leg spec. **Recommendation**: leg specs should reference the flight's design decisions by number rather than re-deriving them.

- **Migration legs lacked an explicit "AIAT skip" deferral statement upfront.** L4/L5/L6 each independently rediscovered the AIAT block. **Recommendation**: when a flight has a known live-test gap, the flight's Pre-Flight Adaptation Criteria should explicitly defer AIAT smoke to the verification leg by default.

### Technical

- **`_kill_process_tree` duplicated** across `the_one/platform/shell.py:101-117` and `the_one/platform/interpreter.py:81-93` — identical bodies. Extract to a shared module (e.g., `the_one/platform/_subprocess.py`) before F4 adds a third subprocess-launching helper.

- **Kill+reap boilerplate duplicated** between `run_shell` and `run_python` (the wait_for / except / kill / re-drain pattern). A shared `_run_subprocess(launcher, *, timeout, env)` helper could absorb the boilerplate cleanly.

- **`AgentFactory.create()` has comment numbering bug** — comment "3" appears twice (`factory.py:112` and `factory.py:121`) from L3 wiring. Cosmetic but visible.

- **Schema migration atomicity deferred again** (F1 debrief recommendation, F2 debrief carries forward). Real multi-DDL atomicity requires switching `aiosqlite` to `isolation_level=None`; that's a connection-setup change beyond F2 scope. Will compound if F3-F5 add more DDL per migration. Track as a maintenance task.

- **`_TOOL_CLASSES` test seam not documented**. The module-level `the_one.tools.builtins._TOOL_CLASSES` dict is the supported monkeypatch target for tests that need to substitute tool classes; this should be pinned in `agents.md` so F4-F6 test authors don't reinvent.

- **`StubTool` in `tests/conftest.py` doesn't call `super().__init__()`**, so its instances lack `_config`. Low severity — only matters if a future test introspects `_config` on stubs. Forward-flagged in flight log.

### Documentation

- **No project-level "test conventions" doc**. Patterns established across L1-L6 are scattered:
  - `asyncio_mode = "auto"` test convention (L1)
  - `monkeypatch.setenv("HOME", ...)` for `~` expansion (L4)
  - `httpx.MockTransport` `_install_mock` pattern (L6)
  - kill+reap test budget assertions (L5)
  - **Recommendation**: create `tests/CONVENTIONS.md` documenting these patterns canonically.

- **F1 layered-prompt-model documentation carryover** is now deferred TWICE (F1 debrief → F2 → next). Track carefully so it doesn't disappear.

- **Bool-narrowing semantic ("True → False is narrowing")** is opinionated and operator-facing once F6 admin UI lands. Document in `agents.md` Tool Policy Resolver section so operators who configure `follow_redirects: True → False` know this is the canonical permission-revocation pattern.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Tool.Config default became `_EmptyConfig` (not bare `BaseModel`) | Pydantic v2 forbids `BaseModel()` instantiation | YES — flight specs must never quote uninstantiable Pydantic v2 placeholders without verification smoke |
| Tests use `async def` not `asyncio.run(...)` | `asyncio.run` closes main thread's loop; breaks legacy `get_event_loop().run_until_complete` callers | YES — write into `tests/CONVENTIONS.md` |
| `run_shell`/`run_python` use `start_new_session=True` + `killpg(SIGKILL)` | `proc.kill()` alone doesn't unblock `communicate()` for shell-spawned subtrees | YES — already documented in module docstrings; codify as the canonical subprocess kill+reap pattern |
| `INSERT OR IGNORE INTO schema_version` for v8 (vs bare INSERT on v3-v7) | Closes narrow concurrent-`ensure_schema` race; deliberate non-backport | YES — adopt for all future migration version bumps |
| `~` expansion tests use `monkeypatch.setenv("HOME", ...)` | `Path.expanduser()` reads `os.environ["HOME"]` directly via posixpath; patching `Path.home` is a silent no-op | YES — write into `tests/CONVENTIONS.md` |
| L6 made zero source-code changes | httpx is already cross-platform; no platform-coupled call to abstract | NO — leg-specific outcome, not a pattern |
| AIAT smoke deferred from L4/L5/L6 to L7 | Pre-existing pytest-base-url ScopeMismatch blocked live tests | NO — but standardize "defer AIAT to verification leg" as a process pattern when a flight has a known live-test gap |

## Key Learnings

1. **Sentinel-class markers + class-identity dispatch** (`m is Narrow`) work cleanly with Pydantic v2's `Annotated` field metadata. Reusable pattern for any future per-key declarative dispatch.

2. **Per-leg design review pipeline catches high-severity bugs upstream of code.** L3's `BaseModel` instantiation bug would have broken every existing tool — caught at design review, fixed before any code was written. The "max 2 design review cycles" rule held.

3. **Copy-don't-cut for migration scaffolds is uncontroversially the right pattern.** L1 wrote helpers alongside existing platform-coupled code; L4-L6 swapped call sites with confidence because the helpers were already proven against direct unit tests.

4. **The "default-instantiable Config" forward constraint** (Decision 9 trade-off) becomes load-bearing the moment F3 adds real Configs. Any required field would break the introspection-call contract `BuiltinToolProvider.get_tools(None)`.

5. **Provider-drives-resolution beats factory-drives-resolution** for MCP alignment. The factory passes raw dicts to `provider.get_tools(...)` and the provider does its own internal name→Config mapping — matches how MCP servers will source schemas from runtime manifests.

6. **The kill+reap pattern is non-obvious enough that the leg-spec pseudo-code was insufficient.** L1's first implementation followed the literal spec and the timeout test took the full 5s of the inner sleep. This is exactly the kind of in-leg discovery that should generate a flight-log Anomaly entry — and did.

7. **Test design at the module-import level matters**: `tests/conftest.py`-level fixtures (like `asyncio_mode = "auto"`) silently affect every test file. The L1 anomaly was not a test bug but a project-wide test-runner contract violation.

## Recommendations

1. **Extract `_kill_process_tree` and the kill+reap loop into a shared helper** (`the_one/platform/_subprocess.py`) before F4 adds pty session as a third subprocess-launching site. Avoids triplicate maintenance burden.

2. **Create `tests/CONVENTIONS.md`** documenting: `asyncio_mode = "auto"` (write tests as `async def`), `monkeypatch.setenv("HOME", ...)` for tilde expansion, `httpx.MockTransport` `_install_mock` pattern (capture original AsyncClient before patching), kill+reap timeout-budget assertions (`elapsed < 3.0` for tool-layer, `< 1.0` for platform-layer).

3. **Document `_TOOL_CLASSES` as the test monkeypatch seam in `agents.md`** so F4-F6 test authors don't reinvent. One-line addition under Tool Providers section.

4. **For F3 path-scope design**: decide BEFORE leg-design between (a) extending the resolver with prefix-containment narrow semantics, or (b) keeping the resolver pure and using `Substitute` + per-tool `model_validator` for path-scope checks. Option (b) is preferred — keeps the resolver contract simple.

5. **Adopt "live-environment provisioning audit"** as a Pre-Flight checklist item for any flight that depends on AIAT or browser tests. Surface environmental gaps (default-agent provider seeding, container DB state, etc.) at flight-design time, not at L7.

## Action Items

- [ ] **Pre-F3**: extract `_kill_process_tree` + kill+reap loop into `the_one/platform/_subprocess.py`
- [ ] **Pre-F3**: create `tests/CONVENTIONS.md` documenting the 4 patterns from F2
- [ ] **Pre-F3**: document `_TOOL_CLASSES` test seam in `agents.md`
- [ ] **F3 design**: pick path-scope narrow semantics (resolver-extend vs Substitute+model_validator)
- [ ] **F3 design**: confirm `FilesystemConfig` is default-instantiable (preserves Decision 9 introspection contract)
- [ ] **Pre-F6**: seed dev-DB with a default LLM provider so AIAT live smoke is genuinely usable as a regression net
- [ ] **F6 design**: communicate session-bound freshness contract in admin UX ("applies to next session")
- [ ] **Maintenance**: schema migration atomicity (deferred from F1 debrief, carried forward in F2)
- [ ] **Maintenance**: F1 layered-prompt-model documentation (deferred from F1 debrief, carried forward in F2)
- [ ] **Maintenance**: `tests/test_provider_repository.py` legacy `asyncio.get_event_loop()` cleanup
- [ ] **Maintenance**: fix `factory.py` duplicate comment "3" numbering
- [ ] **Future**: `StubTool.__init__` super-call (forward-reference; only blocks if a test introspects `_config`)
