# Leg: 07-integration-verification

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Comprehensive verification that L1-L6 left the system in the desired state — full default unit suite + browser suite + AIAT live smoke + F2-specific regression sweep + `/api/agents` payload audit + documentation updates. Triages the pre-existing AIAT pytest-fixture ScopeMismatch (documented under L4 Session Notes); fixes it if scope-isolated, otherwise records as a forward-reference. Emits the final go/no-go signal for the flight Reviewer pass.

## Context

L7 is **scaffolding-refactor verification** per Decision 7. F2 introduced no new constraint values, no new user-facing surfaces, no new agent behaviors — the seven tools should behave identically before and after. L7 confirms that empirically across:

- Default unit suite (≥522 passes vs `main` baseline of 395; +127 net adds across L1-L6 = 30 platform + 25 schema/repo/config/api + 37 resolver/Tool-ABC + 12 filesystem + 11 execution + 12 web = 127; verified per-leg in flight log)
- Browser suite (M04 baseline preserved; visual snapshots gitignored per user-global instruction)
- AIAT live smoke (currently blocked by pre-existing pytest-base-url ScopeMismatch)
- Documentation: `agents.md` and `CLAUDE.md` reflecting platform layer, resolver, and session-bound freshness contract
- `/api/agents` payload shape: `tool_overrides` field present, defaults to `null`, Pydantic `extra: "ignore"` roundtrip clean

Per the flight Verification section, the F2-specific regression sweep targets new patterns that could regress:
- Direct `Path(p).expanduser().resolve()` calls remaining in `the_one/tools/` outside the platform layer
- Zero-arg `BuiltinToolProvider().get_tools()` callers that now need `None` explicitly (none should — the introspection path was preserved)
- Any tool that doesn't subclass `Tool.Config = _EmptyConfig` (none should — the empty default is inherited)
- Any leftover hardcoded `"python3"` string in tool code

Per F1 debrief carryover: the layered-prompt-model documentation update is OUT OF SCOPE for F2 (defer to F6 or a maintenance task).

### Cumulative state at L7 start (post-L6)

- Branch `flight/02-cross-platform-foundations` with all L1-L6 changes uncommitted
- Schema v8 applied: `tool_configs` table + `agents.tool_overrides` column
- Platform package: `the_one/platform/{paths,shell,interpreter,tempdirs}.py`
- Resolver: `the_one/tools/resolver.py` with `Narrow`/`Substitute`/`_EmptyConfig`/`resolve()`
- Tool ABC: `Config = _EmptyConfig`, `__init__(config)`
- Per-agent provider: `BuiltinToolProvider.get_tools(tool_configs, agent_overrides)` with module-level `_TOOL_CLASSES` eager dict
- Factory: `AgentFactory.create()` invokes resolver via `ToolConfigRepository.list_all()`
- Tools migrated: filesystem (L4) + execution (L5) through platform layer; web (L6) unchanged but tested
- Test suite: 522 passing (modulo pre-existing CSS-token red), zero new regressions
- AIAT: blocked by pre-existing pytest-base-url ScopeMismatch (see `flight-log.md::Session Notes::L4` entry — `tests/test_aiat.py:30-33` declares `base_url` at function scope but pytest-base-url's `_verify_url` is session-scoped autouse, causing the conflict)
- Documentation drift: `the_one/agents.md` updated in L3 (resolver + Tool ABC); other docs not yet updated

## Inputs

What exists before this leg runs:

- L1-L6 all landed and uncommitted in working tree
- All 522 currently-passing unit tests
- One pre-existing CSS-token failure (predates F1)
- One pre-existing AIAT ScopeMismatch (predates L4 — surfaced under L4 verification)
- Branch: `flight/02-cross-platform-foundations`

## Outputs

What exists after this leg completes:

- Full default unit suite green (modulo pre-existing CSS-token red)
- Browser suite green (M04 baseline preserved; visual snapshots gitignored)
- AIAT live smoke status determined: green, or skip-with-explanation if the pre-existing ScopeMismatch is genuinely outside F2 scope to fix, OR fixed-in-L7 if scope-isolated
- F2-specific regression sweep: zero unexpected matches
- `/api/agents` payload audit: `tool_overrides` field present, default `null`, roundtrip clean
- `the_one/CLAUDE.md` updated: platform layer, resolver, session-bound tool-config freshness contract documented
- `the_one/agents.md` cross-referenced (L3 already touched it; L7 adds session-freshness contract documentation if missing)
- `the_one/.flightops/` artifacts updated (flight log final entry, leg landed, flight checkpoints checked off)
- Flight status set to `landed` (transitions to `completed` happen via `/flight-debrief`)

## Acceptance Criteria

- [ ] **Default unit suite**: `make test-unit` returns the L6-tip pass set plus zero new failures. Acceptable: 1 pre-existing CSS `--font-size-h3` token red. Document the exact pass count in flight log.
- [ ] **Browser suite**: `make test-browser` passes; M04 baseline preserved. Visual snapshots are gitignored per user-global instruction — verified at design time: root `.gitignore` line 19 excludes `tests/browser/__snapshots__/` directory; no per-directory `.gitignore` exists or is needed.
- [ ] **AIAT live smoke triage**:
  - Run `pytest -m live tests/test_aiat.py` (or `docker exec the-one pytest -m live tests/test_aiat.py`).
  - **Diagnose** the pytest-base-url ScopeMismatch documented in `flight-log.md::Session Notes::L4 entry`:
    - The conflict is at `tests/test_aiat.py:30-33`: `base_url` declared `@pytest.fixture` (default function scope) overrides pytest-base-url's session-scoped fixture; `_verify_url` (session autouse from the plugin) sees the function-scoped override and raises ScopeMismatch.
    - **Fix scope: changing the single `@pytest.fixture` decorator line to `@pytest.fixture(scope="session")` is the in-scope L7 fix.** Anything more invasive (deleting the override, dropping the plugin, refactoring URL plumbing) is OUT OF SCOPE for L7.
    - If the single-decorator fix works, apply it; record a one-line note in the flight log under a "Decision" entry: "L7 promoted `base_url` fixture to session scope to resolve pre-existing pytest-base-url ScopeMismatch; AIAT live smoke now runs."
    - If even the single-decorator fix exposes deeper coupling (e.g., `_verify_url` rejects the new scope contract), **leave deferred** as a forward-reference for F2 debrief / maintenance task; document the decision and use `-p no:base_url` (or whichever plugin name `pytest --plugins` reports) as the AIAT-run workaround. Verify the correct plugin name via `docker exec the-one pytest --plugins | grep -i base` before locking it in.
  - Whichever path is chosen, the flight log must explain it explicitly.
  - **Deferred-branch safeguard**: if AIAT remains skipped at L7 hand-off, run `docker exec the-one curl -s http://localhost:8484/api/selftest` (the existing self-test endpoint that exercises one tool path against the running agent) and document the result in the flight log as the live regression net for F2's tool-execution paths.
- [ ] **Pre-flight working tree state**: `git status` shows the expected uncommitted L1-L6 deltas (the_one/ tools, db, agent files; tests/ new test files; missions/.../ artifacts); no unrelated working-tree changes. Run `git status` and confirm before proceeding.
- [ ] **Tool ABC static check** (mirrors flight.md Verification block): `rg -n 'Config: type\[BaseModel\]' the_one/tools/base.py` returns at least one match — confirms the L3 ABC change persists.
- [ ] **F2-specific regression sweep** — run these grep checks on the host:
  ```bash
  # No direct platform-coupled calls remain in tools/ outside the platform layer
  rg -n 'Path\([^)]+\)\.expanduser\(\)\.resolve\(\)' the_one/tools/
  # Expected: empty (canonicalize() replaced all sites)

  rg -n '"python3"' the_one/tools/
  # Expected: empty (resolve_python() / sys.executable replaced)

  rg -n 'asyncio\.create_subprocess_(shell|exec)' the_one/tools/
  # Expected: empty (run_shell / run_python encapsulate these)

  # Tool ABC inheritance: catch leftover bare-BaseModel placeholder pattern.
  # F3+ will replace empty Configs with concrete subclasses (e.g., `class
  # FilesystemConfig(BaseModel): ...`), which is fine — this grep specifically
  # targets the placeholder.
  rg -n 'Config\s*=\s*BaseModel' the_one/tools/
  # Expected: empty (ABC default is _EmptyConfig; tools inherit it)

  # No L1-L6 leftovers from prior bad state
  rg -n 'self_deploy|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|behaviors\.py|DEFAULT_SYSTEM_PROMPT' the_one/ tests/
  # Expected: matches confined to the_one/db/schema.py REMOVED set + tests/test_db_migration.py fixtures (per F1 baseline; L6 added nothing here)
  ```
  Each grep result is documented in flight log; any unexpected match is flagged before signaling complete.
- [ ] **`/api/agents` payload shape audit**:
  ```bash
  # Programmatic check: the field is present and defaults to null
  docker exec the-one python -c "
  import asyncio
  from the_one.agent.config import AgentConfig
  cfg = AgentConfig(name='test')
  assert 'tool_overrides' in cfg.model_dump()
  assert cfg.model_dump()['tool_overrides'] is None
  # Roundtrip with stale 'direct_actions' (extra='ignore' regression check from F1)
  cfg2 = AgentConfig.model_validate({'name': 'test2', 'direct_actions': True})
  assert cfg2.tool_overrides is None
  print('OK')
  "
  ```
  Browser tests' agent CRUD assertions should be unchanged (verified via `make test-browser` above).
- [ ] **Resolver smoke** (re-run from L3 to confirm no regression):
  ```bash
  docker exec the-one python -c "
  from typing import Annotated
  from pydantic import BaseModel
  from the_one.tools.resolver import resolve, Narrow, Substitute, _EmptyConfig

  class Cfg(BaseModel):
      cap: Annotated[int, Narrow] = 100
      paths: Annotated[list[str], Narrow] = []
      redirects: Annotated[bool, Narrow] = True
      token: Annotated[str, Substitute] = ''

  r = resolve(Cfg,
      {'cap': 50, 'paths': ['/home', '/tmp'], 'redirects': True, 'token': 'tool'},
      {'cap': 30, 'paths': ['/home'], 'redirects': False, 'token': 'agent'})
  assert r.cap == 30 and r.paths == ['/home'] and r.redirects is False and r.token == 'agent', r
  r = resolve(_EmptyConfig, {'anything': 1}, {'foo': 2})
  assert r.model_dump() == {}, r
  print('OK')
  "
  ```
- [ ] **Per-agent isolation smoke** (re-run from L3):
  ```bash
  docker exec the-one python -c "
  from the_one.tools.builtins import BuiltinToolProvider
  p = BuiltinToolProvider()
  a = p.get_tools({}, {})
  b = p.get_tools({}, {})
  for ta, tb in zip(a, b):
      assert ta is not tb, f'singleton leaked for {ta.name}'
  print('OK')
  "
  ```
- [ ] **Documentation updates**:
  - `the_one/CLAUDE.md` — add a new top-level section "## Tool Configuration Layer (M05 F2)" **inserted between the existing `## Architecture` section and the `## Configuration` section** (verified insertion point at design time — section structure is `What This Is` → `Commands` → `Local dev with Docker` → `Architecture` → **NEW SECTION HERE** → `Configuration` → `Conventions` → `HAT Design Guidance` → `Testing`). The new section documents:
    - The two-layer config model (tool-level `tool_configs` table; agent-level `AgentConfig.tool_overrides` field)
    - The resolver's `Narrow` / `Substitute` semantics with the per-type narrow comparisons (bool: True→False; int/float: cap; list: subset)
    - The session-bound freshness contract (resolved at `AgentFactory.create()`; mid-session operator updates apply at next agent build)
    - The platform package layout (`the_one/platform/{paths,shell,interpreter,tempdirs}`)
    - Forward-reference: F3-F5 will populate per-tool Configs with real constraint fields
  - `the_one/agents.md` — **NO EDIT REQUIRED**: verified at design time that L3 already documented the resolver, `Narrow`/`Substitute` markers, AND the session-bound freshness contract (lines 167-174 reference Decision 8 explicitly). Confirm those lines still match by reading the file; if any documentation drift is found, fix in-place. Otherwise leave untouched.
  - **F1 layered-prompt-model documentation carryover**: explicitly NOT in F2 scope per the flight spec — note in flight log Decision section that this remains deferred (target: F6 or a maintenance task).
- [ ] **Flight artifact final state**:
  - All seven legs (L1-L7) checked off in `flight.md`
  - All six checkpoints checked off in `flight.md::In-Flight::Checkpoints`
  - Flight status updated `in-flight` → `landed`
  - Flight `Post-Flight::Completion Checklist` items all checked
  - Flight log final entry summarizes: net test deltas, any deviations from the original L1-L6 plan, the AIAT triage outcome, and a clean go signal for the Reviewer pass
- [ ] **Mission artifact**:
  - Flight 2 checked off in `missions/05-built-in-tool-system/mission.md::Flights` list
  - No new mission Known Issues added in F2 (the F1-discovered DDG and Playwright issues remain; F2 added no new ones)
- [ ] **No commit yet**: per agentic-workflow batched-review pattern, commit happens AFTER L7 completes and the Reviewer signals `[HANDOFF:confirmed]` on the whole flight.

## Verification Steps

```bash
# 1. Pre-flight: confirm working tree is the expected L1-L6 cumulative state
git status
git diff --stat | tail -5  # expect cumulative L1-L6 deltas

# 2. Build container with current state
make rebuild

# 3. Default unit suite
make test-unit
# Document the exact pass/fail count in flight log

# 4. Browser suite
make test-browser
# Document pass count; visual snapshots gitignored per user-global instruction

# 5. AIAT live smoke triage
docker exec the-one pytest -m live tests/test_aiat.py -v
# If ScopeMismatch — diagnose:
#   pytest --fixtures tests/test_aiat.py | grep -i base_url
#   Read tests/test_aiat.py:30 to find the conflicting fixture
# If fix is small (1-3 lines) — apply, re-run, document in flight log
# If fix requires refactor — leave deferred, document forward-reference

# 6. F2 regression sweep
rg -n 'Path\([^)]+\)\.expanduser\(\)\.resolve\(\)' the_one/tools/
rg -n '"python3"' the_one/tools/
rg -n 'asyncio\.create_subprocess_(shell|exec)' the_one/tools/
rg -n 'Config\s*=\s*BaseModel' the_one/tools/
rg -n 'self_deploy|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|behaviors\.py|DEFAULT_SYSTEM_PROMPT' the_one/ tests/

# 7. /api/agents payload + resolver + isolation smokes (see ACs above)

# 8. Documentation diff
git diff -- the_one/CLAUDE.md the_one/agents.md
# Expect: CLAUDE.md gains a Tool Configuration section; agents.md unchanged or
# minor session-freshness note added
```

## Implementation Guidance

### Step 1 — AIAT triage

Read `tests/test_aiat.py:30-33` to confirm the ScopeMismatch root cause. The current shape (verified at design time) is:

```python
@pytest.fixture
def base_url() -> str:
    return os.environ.get("THE_ONE_TEST_URL", "http://localhost:8484")
```

This declares `base_url` at function scope (the `@pytest.fixture` default), overriding pytest-base-url's session-scoped fixture of the same name. The plugin's session-autouse `_verify_url` then sees the function-scoped override and raises ScopeMismatch.

**The L7 fix (single-line change)**:

```python
@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("THE_ONE_TEST_URL", "http://localhost:8484")
```

This is the in-scope L7 fix. **Default URL stays `http://localhost:8484`** (do NOT change it to anything else — that would be a behavior change orthogonal to the scope fix). Run `docker exec the-one pytest -m live tests/test_aiat.py -v` to verify.

If the single-decorator fix exposes deeper coupling (e.g., the plugin's `_verify_url` rejects the override even at session scope, or `THE_ONE_TEST_URL` is mutated by another fixture mid-session), document the diagnosis and use the workaround:
```bash
# Verify the correct plugin name first (likely "base_url" without the "pytest-" prefix)
docker exec the-one pytest --plugins 2>&1 | grep -i base
# Then disable for AIAT runs only
docker exec the-one pytest -m live -p no:base_url tests/test_aiat.py -v
```

Whichever branch is taken, document the outcome in the flight log under a Decision entry. **Note for the implementing agent**: each `pytest` invocation is a fresh session, so promote-to-session does NOT introduce env-var staleness across separate developer test runs.

### Step 2 — `the_one/CLAUDE.md` update

Add a new section after the existing tool-system documentation:

```markdown
## Tool Configuration Layer (M05 Flight 2)

### Two-layer config model
- **Tool-level**: `tool_configs` SQLite table — operator-set defaults shared by all agents.
- **Agent-level**: `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None` — per-agent narrowing or substitution. NULL means "no overrides set".

### Resolver semantics
`the_one/tools/resolver.py::resolve(schema, tool_config, agent_override)` composes the two layers per-key:
- `Annotated[type, Narrow]`: agent override must be ≤ tool-level value (bool: True→False or equal; int/float: cap; list: subset). Widening raises `ValueError`.
- `Annotated[type, Substitute]`: agent override replaces tool-level value (no comparison). For identity / shared-credential / KV values.
- Unannotated fields raise `ValueError("...no Narrow/Substitute marker...")` when overridden — F3-F5 must annotate every field they introduce.

### Session-bound freshness
Resolved tool configs are computed at `AgentFactory.create()` time and held as instance state on each tool. Mid-session operator updates to `tool_configs` rows or `AgentConfig.tool_overrides` apply at the **next** `AgentFactory.create()` invocation, NOT to in-flight agents. F6's admin UI must communicate "applies to next session" clearly.

### Platform abstraction layer
`the_one/platform/` isolates platform-divergent concerns:
- `paths.py` — `canonicalize`, `safe_resolve`, `is_within`
- `shell.py` — `select_shell`, `run_shell` (kill+reap on timeout via `start_new_session=True` + `killpg(SIGKILL)`)
- `interpreter.py` — `resolve_python` (returns `sys.executable`), `run_python`
- `tempdirs.py` — `temp_dir`, `user_home`, `user_config_dir`

F3-F5 will populate per-tool Pydantic Configs with real constraint values on top of this seam.
```

### Step 3 — `the_one/agents.md` cross-check

L3 already added Tool ABC + resolver entries. Verify the resolver section mentions session-bound freshness; add one sentence if not present.

### Step 4 — Flight log final entry

Append to flight log under `## Leg Progress`:

```markdown
### L7 — Integration Verification (landed YYYY-MM-DD)

- Default unit suite: <PASSES> passed, 1 failed (pre-existing CSS-token red), 238 deselected — <DELTA> net new from F2 baseline; zero new regressions.
- Browser suite: <PASSES> passed; M04 baseline preserved; visual snapshots gitignored.
- AIAT live smoke: <green / fixed-in-L7 / deferred-with-rationale>
- F2 regression sweep: zero unexpected matches.
- `/api/agents` payload: `tool_overrides` field present, default `null`, extra=ignore roundtrip clean.
- Resolver + per-agent isolation smokes: green.
- Documentation: `CLAUDE.md` gains "Tool Configuration Layer" section; `agents.md` cross-checked.

Flight status: `in-flight` → `landed`. Ready for Reviewer pass.
```

### Step 5 — Mark flight landed

**L7 leg artifact**:
- Set `Status: ready → in-flight` when L7 work begins; flip to `landed` after all ACs verified

**`flight.md`**:
- Status: `in-flight` → `landed`
- All Legs items checked off
- All Checkpoints items checked off
- All Completion Checklist items checked off

**`mission.md::Flights`**:
- Check off Flight 2

**Note on flight status timing**: per agentic-workflow methodology, the flight is `landed` (implementation complete) before the Reviewer pass. The Reviewer signals `[HANDOFF:confirmed]` on the cumulative working tree, then the commit happens. The flight transitions to `completed` later via `/flight-debrief` — that's not L7's responsibility.

## Edge Cases

- **AIAT triage requires deep refactor**: if `_verify_url` is session-scoped because pytest-base-url owns it and changing it is brittle, the cleanest in-L7 fix is `-p no:base-url` to disable the plugin for AIAT runs. Document the choice; keep the fix scope-isolated to `tests/test_aiat.py` or its conftest. Do NOT modify `pyproject.toml` test config to globally disable the plugin (that affects other tests).
- **Browser suite snapshot drift**: per user-global instruction, visual snapshots are gitignored. If `make test-browser` produces snapshot diffs that fail, regenerate locally and confirm the diff is gitignored. F2 introduced no UI changes (`tool_overrides` is null in payloads; no admin UI yet) so snapshot diffs would indicate an unrelated regression.
- **`/api/agents` payload shape**: the new `tool_overrides: null` field appears in every agent payload. Verify with the regression-sweep grep that no browser test asserts negative field membership (per L2 design's verification: zero matches expected).
- **F1 layered-prompt-model carryover**: explicit non-goal per the flight spec. If a reviewer asks why CLAUDE.md doesn't document the BASE_PROMPT layering, the answer is: "out of F2 scope; deferred to F6 or maintenance task per F1 debrief recommendation."
- **No leg-immutability conflict**: this leg is L7 the verification leg; immutability rules apply to L1-L6 ONLY (per the leg lifecycle: legs become immutable once `in-flight`). L7 is itself in-flight during this work; modifying its OWN artifact is allowed.
- **State-machine reachability** (per `/leg` skill section 5): no states added or modified by L7. Verifying state reachability for L1-L6 outcomes:
  - Schema v8 reachable: yes (v7 → v8 migration tested)
  - `tool_overrides=NULL` reachable: yes (default, ALTER without DEFAULT)
  - `tool_overrides={}` reachable: yes (operator clears)
  - `tool_overrides={"shell": {}}` reachable: yes (operator deletes specific override)
  - All states verified by L2/L3 tests.
- **Cache freshness contract** (per `/leg` skill section 6): the resolved `Tool.Config` instance is the cache; per-agent rebuild on `AgentFactory.create()`; max staleness "until next session start". Documented in CLAUDE.md per Step 2 above.

## Files Affected

- `the_one/CLAUDE.md` — add "Tool Configuration Layer (M05 Flight 2)" section
- `the_one/agents.md` — minor session-freshness note (only if missing post-L3)
- `tests/test_aiat.py` (or its conftest) — possible 1-3 line ScopeMismatch fix (pending diagnosis)
- `missions/.../flight-log.md` — append L7 progress entry; AIAT triage outcome; final go signal
- `missions/.../flight.md` — set status `landed`; all legs/checkpoints/completion-items checked off
- `missions/.../legs/07-integration-verification.md` — set status `landed`
- `missions/05-built-in-tool-system/mission.md` — check off Flight 2 in Flights list

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (this is the LAST autonomous leg; the Reviewer pass on the whole flight follows):

- [ ] All acceptance criteria verified
- [ ] Default unit suite, browser suite, AIAT live smoke (or skip with rationale) all green
- [ ] F2 regression sweep: zero unexpected matches
- [ ] `/api/agents` payload audit clean
- [ ] CLAUDE.md updated; agents.md cross-checked
- [ ] Flight log final entry appended
- [ ] L7 leg status set to `landed`
- [ ] All seven legs and six checkpoints checked off in flight.md
- [ ] Flight.md status set to `landed`
- [ ] Mission.md Flight 2 checked off
- [ ] Do NOT commit — the Reviewer agent inspects the cumulative working tree first; commit happens after [HANDOFF:confirmed]
