# Leg: 01-rip-tools-and-behaviors

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Delete the seven self-modification tool files and the `behaviors.py` direct-action module, update `builtins.py` to expose the seven kept tools, drop the `direct_actions` field from `AgentConfig`, remove the dead direct-action call site from `core.py`, and inline `CONTINUE_SCHEMA` into `core.py` (its only consumer) — all while keeping the default unit test suite green.

## Context

L1 is the foundational reduction. Everything downstream (prompt rewrite in L2, schema strip in L3, CI teardown in L4, UI/docs cleanup in L5, test sweep in L6) refers back to a stable post-rip codebase, so getting the seven tool names actually gone — at the source-of-truth level — has to land first.

Per **Decision 1**, `CONTINUE_SCHEMA` survives the `behaviors.py` deletion: it moves inline into `core.py`, which is its only consumer.

Per **Decision 2**, `behaviors.py`, `DIRECT_ACTIONS`, `match_direct_action`, and `AgentConfig.direct_actions` are all removed because `restart` and `rollback` (the only patterns) are gone, leaving `DIRECT_ACTIONS` empty. The `core.py` direct-action call site (`step()` lines 50-62 and the `_match_direct_action` static helper at lines 130-133) becomes dead code and is also removed.

**Codebase audit findings (2026-04-28):**
- All 7 tool source files exist: `the_one/tools/{git.py,memory.py,mission_control.py,restart.py,rollback.py,self_deploy.py,test_runner.py}`.
- `the_one/tools/builtins.py` registers 14 tools; will become 7 (`shell`, `read_file`, `write_file`, `list_dir`, `http_request`, `web_search`, `python_exec`).
- `the_one/agent/behaviors.py` exports `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`, `match_direct_action`. `CONTINUE_SCHEMA`'s only importer is `the_one/agent/core.py:5`.
- `the_one/agent/core.py:5` imports `CONTINUE_SCHEMA` and `match_direct_action` from `behaviors`. Both must move/disappear.
- `the_one/agent/config.py:92` defines `direct_actions: bool = True` on `AgentConfig`.
- **Test-suite blocker:** `tests/test_behaviors.py` (entire file) and `tests/test_agent.py::TestDirectAction::test_restart_bypass` (lines 92-105) directly exercise the removed direct-action infrastructure. The flight Technical Approach assigns these to L6, but if they remain after L1's source-side deletion, the default `pytest tests/` run goes red between L1 and L6, violating the "build stays green between legs" guarantee that L1+L2's back-to-back commit promise relies on. **Deviation from flight spec:** delete both in L1, not L6. Record in flight log Deviations.
- **Test-suite blocker (test_config.py):** `tests/test_config.py` asserts `cfg.direct_actions is True` (line 24), constructs with `direct_actions=False` (line 36), and asserts `cfg.direct_actions is False` (line 46). Same green-build invariant — fix in L1.
- `tests/test_aiat.py::test_run_tests` is `pytest -m live` (off the default suite), so deferring its deletion to L6 is safe.
- `tests/browser/seeders.py:71` mentions `direct_actions` only in a comment listing optional `AgentConfig` fields. Update the comment in L1; no behavioral consequence.
- The Studio `TOOL_CATEGORIES` site at `studio.js:151-156` references `run_tests`, `git`, `self_deploy`, `rollback`, `restart`, `mission_control`, `memory`. Out of scope for L1 — that's L5 (UI/docs cleanup). The JS module is untested by the default unit suite, so leaving it stale until L5 doesn't break anything.
- `the_one/agent/config.py`'s `DEFAULT_SYSTEM_PROMPT` describes the seven removed tools. Out of scope for L1 — that's L2 (prompt rewrite). Acceptable interim incoherence per flight Technical Approach inter-leg coherence note.
- `the_one/agents.md` table includes the seven removed tools (lines 60, 85-93, 146, 175 — references `GitTool`, `MemoryTool`, `MissionControlTool`, `TestRunnerTool`, `SelfDeployTool`, `RollbackTool`, `RestartTool`, `behaviors.py`, `DIRECT_ACTIONS`, `match_direct_action`). Out of scope for L1 — L5 will rewrite the table. **L1 verification greps must therefore exclude `*.md` files** to avoid false-positive failures against this stale-until-L5 narrative.
- `CLAUDE.md` (project-level, lines ~68-70) describes `behaviors.py` and `match_direct_action()`. Same stale-until-L5 status; same grep-exclusion requirement.
- `tests/test_db_migration.py:85` carries `disabled_tools=["self_deploy"]`. Intentionally untouched by L1 — L3 updates the fixture to use a surviving tool name as part of the schema-v7 migration test split (per flight spec).
- **API surface impact (medium, non-blocking)**: `the_one/interfaces/web/api.py` invokes `AgentConfig.model_dump()` in GET/POST/PUT `/api/agents` handlers. Today every response payload includes `"direct_actions": true`. After L1, the field disappears from all `/api/agents` responses. Verified no JS or browser-test consumer reads it (`rg "direct_actions" the_one/interfaces/web/static tests/browser` returns no matches). Inbound payloads carrying the legacy field will be silently dropped by `extra: "ignore"` on `AgentConfig`. Safe in practice; documented here so the L1 reviewer doesn't flag it as a regression.
- `the_one/tools/__init__.py` does NOT re-export tool classes (verified). No update needed in this leg.

## Inputs

- Branch `flight/01-tool-reduction-self-modification-teardown` checked out (already done by Flight Director).
- Schema is at v6 (verified pre-flight).
- All 14 tool files present in `the_one/tools/`.
- `behaviors.py` present in `the_one/agent/`.
- Default unit test suite (`pytest tests/`) green at branch start.

## Outputs

After this leg:
- 7 tool source files deleted: `git.py`, `memory.py`, `mission_control.py`, `restart.py`, `rollback.py`, `self_deploy.py`, `test_runner.py`.
- `the_one/tools/builtins.py` returns 7 tools, count comment updated to "7 built-in tools".
- `the_one/agent/behaviors.py` deleted.
- `the_one/agent/core.py` no longer imports from `behaviors`, has `CONTINUE_SCHEMA` defined inline at module level, has the direct-action call site removed (`step()` simplified), and the `_match_direct_action` static helper removed.
- `the_one/agent/config.py` no longer has the `direct_actions` field on `AgentConfig`.
- `tests/test_behaviors.py` deleted.
- `tests/test_agent.py::TestDirectAction::test_restart_bypass` (and its containing `TestDirectAction` class if that leaves the class empty) removed.
- `tests/test_config.py` no longer asserts on `direct_actions`.
- `tests/browser/seeders.py:71` comment updated (drop `direct_actions` from the list).
- Default unit test suite (`pytest tests/ -q`) green.
- No commit yet — agentic-workflow defers commit to post-L6.

## Acceptance Criteria

- [ ] `the_one/tools/git.py`, `memory.py`, `mission_control.py`, `restart.py`, `rollback.py`, `self_deploy.py`, `test_runner.py` no longer exist.
- [ ] `rg -n "GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool" the_one/ tests/ --glob '!*.md'` returns no matches outside `__pycache__` (the Python files for those classes are gone, and no test imports them). The `--glob '!*.md'` exclusion intentionally skips `the_one/agents.md` and similar narrative files that L5 will rewrite.
- [ ] `the_one/tools/builtins.py` returns exactly 7 tools — `ShellTool`, `ReadFileTool`, `WriteFileTool`, `ListDirTool`, `HttpRequestTool`, `WebSearchTool`, `PythonExecTool` — and the docstring/comment says "7 built-in tools".
- [ ] `the_one/agent/behaviors.py` no longer exists.
- [ ] `rg -n "from the_one.agent.behaviors|behaviors\.py|DIRECT_ACTIONS|match_direct_action" the_one/ tests/ --glob '!*.md'` returns no matches. (The `*.md` exclusion skips `agents.md` line 60 / 146 / 175 and `CLAUDE.md` lines ~68-70 — both L5's job.)
- [ ] `the_one/agent/core.py` defines `CONTINUE_SCHEMA` inline (at module level, before the `Agent` class), no longer imports from `behaviors`, no longer has a direct-action branch in `step()`, no longer defines `_match_direct_action`. `step()` starts directly with `self.messages.append(Message.user(user_input))` followed by the `for _ in range(self.max_iterations):` loop.
- [ ] `AgentConfig` (in `the_one/agent/config.py`) no longer has a `direct_actions` field.
- [ ] `rg -n "direct_actions" the_one/ tests/` returns no matches. (No `*.md` exclusion needed — `agents.md` doesn't reference `direct_actions`.)
- [ ] `tests/test_behaviors.py` no longer exists.
- [ ] `tests/test_agent.py` no longer contains `TestDirectAction` or `test_restart_bypass`.
- [ ] `tests/test_config.py` no longer references `direct_actions`.
- [ ] `tests/browser/seeders.py:71` docstring no longer lists `direct_actions`.
- [ ] `python -m pytest tests/ --tb=short -q --ignore=tests/browser` exits 0 with no test errors.
- [ ] Working tree on branch `flight/01-tool-reduction-self-modification-teardown`; **no commit made** (commit deferred to post-L6 per agentic-workflow).
- [ ] Flight log updated with leg progress entry under `## Leg Progress`, status `landed`.

## Verification Steps

```bash
# 1. Tool files removed
ls the_one/tools/ | grep -E '^(git|memory|mission_control|restart|rollback|self_deploy|test_runner)\.py$'
# Expected: empty (no matches)

# 2. behaviors.py removed
ls the_one/agent/behaviors.py 2>&1
# Expected: "ls: cannot access ...: No such file or directory"

# 3. No references to removed classes (excluding *.md narrative files L5 will rewrite)
rg -n "GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool" the_one/ tests/ --glob '!*.md'
# Expected: no output

# 4. No references to behaviors module / direct-action symbols (excluding *.md)
rg -n "from the_one.agent.behaviors|behaviors\.py|DIRECT_ACTIONS|match_direct_action" the_one/ tests/ --glob '!*.md'
# Expected: no output

# 4b. direct_actions field gone everywhere (md is fine — agents.md does not reference it)
rg -n "direct_actions" the_one/ tests/
# Expected: no output

# 5. builtins.py count
rg -n "7 built-in tools" the_one/tools/builtins.py
# Expected: one match

# 6. core.py defines CONTINUE_SCHEMA inline
rg -n "^CONTINUE_SCHEMA = " the_one/agent/core.py
# Expected: one match

# 7. Import smoke-test — confirms the post-rip tree imports cleanly without pytest
python -c "from the_one.agent.core import Agent, CONTINUE_SCHEMA; from the_one.agent.config import AgentConfig; from the_one.tools.builtins import BuiltinToolProvider; tools = BuiltinToolProvider().get_tools(); assert len(tools) == 7, len(tools); print('OK', len(tools))"
# Expected: "OK 7"

# 8. Test suite green (unit only — browser tests excluded; AIAT live-marked tests excluded by default)
python -m pytest tests/ --tb=short -q --ignore=tests/browser
# Expected: exit 0, all collected tests pass
```

## Implementation Guidance

Run all steps from the project root `~/projects/the-one`. Update the leg status to `in-flight` before starting; update to `landed` at the end (the Flight Director defers `completed` until after the post-L6 commit lands).

1. **Delete the 7 tool source files**
   ```bash
   rm the_one/tools/git.py
   rm the_one/tools/memory.py
   rm the_one/tools/mission_control.py
   rm the_one/tools/restart.py
   rm the_one/tools/rollback.py
   rm the_one/tools/self_deploy.py
   rm the_one/tools/test_runner.py
   ```

2. **Update `the_one/tools/builtins.py`** — drop the seven imports and seven entries. The result should look like:
   ```python
   from __future__ import annotations

   from the_one.tools.base import Tool


   class BuiltinToolProvider:
       """Provides all built-in tools via lazy imports."""

       @property
       def name(self) -> str:
           return "builtin"

       def get_tools(self) -> list[Tool]:
           """Lazy-import and instantiate all 7 built-in tools."""
           from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
           from the_one.tools.python_exec import PythonExecTool
           from the_one.tools.shell import ShellTool
           from the_one.tools.web import HttpRequestTool, WebSearchTool

           return [
               ShellTool(),
               ReadFileTool(),
               WriteFileTool(),
               ListDirTool(),
               HttpRequestTool(),
               WebSearchTool(),
               PythonExecTool(),
           ]
   ```

3. **Inline `CONTINUE_SCHEMA` into `the_one/agent/core.py`** — add the constant at module scope, just below the existing imports and above the `Agent` class. Copy the constant verbatim from `behaviors.py`:
   ```python
   # The agent can call this to keep its turn. It's a signal, not a real tool.
   CONTINUE_SCHEMA = {
       "name": "continue",
       "description": (
           "Call this when you're not done yet — you have more steps to take "
           "but need another turn to think or act. If you don't call this or "
           "any other tool, your turn ends and the user sees your response."
       ),
       "parameters": {
           "type": "object",
           "properties": {
               "reason": {
                   "type": "string",
                   "description": "Brief note to yourself about what you're doing next.",
               },
           },
           "required": [],
       },
   }
   ```

4. **Strip the direct-action call site from `core.py`'s `step()`** — remove the import line `from the_one.agent.behaviors import CONTINUE_SCHEMA, match_direct_action` (the `CONTINUE_SCHEMA` import is replaced by the inline definition from step 3). Inside `step()`, delete the block that starts with the comment `# Check for direct-action patterns before calling the LLM` and runs through (and including) the trailing blank line before `for _ in range(self.max_iterations):`. Specifically, this whole block goes:
   ```python
   # Check for direct-action patterns before calling the LLM
   direct = self._match_direct_action(user_input)
   if direct:
       tool_name, tool_kwargs = direct
       try:
           tool = self.tools.get(tool_name)
           output = await tool.execute(**tool_kwargs)
       except Exception as e:
           output = f"[error] {e}"
       msg = Message.assistant(content=output)
       self.messages.append(msg)
       yield msg
       return
   ```
   Also delete the `_match_direct_action` static helper near the bottom of the class:
   ```python
   @staticmethod
   def _match_direct_action(user_input: str) -> tuple[str, dict] | None:
       """Delegate to standalone match_direct_action function."""
       return match_direct_action(user_input)
   ```
   `step()` should now begin with `self.messages.append(Message.user(user_input))` followed directly by the `for _ in range(self.max_iterations):` loop. Update the `step()` docstring — the line saying "Direct-action responses bypass the LLM entirely so `on_chunk` is never invoked on that path." is no longer true; remove that sentence.

5. **Delete `the_one/agent/behaviors.py`**
   ```bash
   rm the_one/agent/behaviors.py
   ```

6. **Drop `direct_actions` from `AgentConfig`** in `the_one/agent/config.py`:
   - Remove the line `direct_actions: bool = True` (the only line under `# Behavior` other than `max_iterations`).
   - Leave the `# Behavior` section comment if `max_iterations` remains there; the section is still meaningful with one field.

7. **Delete `tests/test_behaviors.py`**
   ```bash
   rm tests/test_behaviors.py
   ```

8. **Remove `TestDirectAction` from `tests/test_agent.py`** — delete the entire `class TestDirectAction:` block (the class is currently a single test, `test_restart_bypass`, lines 92-105). Confirm nothing else in `test_agent.py` depends on the surrounding context (e.g., shared fixtures); the previous and following classes (`TestStep`, `TestContinueSignal`) remain.

9. **Strip `direct_actions` from `tests/test_config.py`** — three edits:
   - Line 24: delete `assert cfg.direct_actions is True`.
   - Line 36: delete the `direct_actions=False,` keyword argument inside the `AgentConfig(...)` call.
   - Line 46: delete `assert cfg.direct_actions is False`.

10. **Update `tests/browser/seeders.py:71` comment** — change the docstring sentence from `(description, enabled_tools, kb_ids, mcp_source_ids, max_iterations, direct_actions)` to `(description, enabled_tools, kb_ids, mcp_source_ids, max_iterations)`.

11. **Run the unit test suite**
    ```bash
    python -m pytest tests/ --tb=short -q --ignore=tests/browser
    ```
    Expected: green. If anything fails, inspect the failure — most likely a missed reference to a removed symbol. If a hang surfaces unexpectedly, install `pytest-timeout` and re-run with `--timeout=60` to isolate it.

12. **Sanity-check grep sweeps** (the verification commands from the Verification Steps section above) — all should return clean.

13. **Update the flight log**
    Append a `### 01-rip-tools-and-behaviors` entry under `## Leg Progress` in `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` with status `landed`, started/completed timestamps, summary of changes, and a note about the Deviation (test_behaviors.py + test_restart_bypass + test_config.py direct_actions edits — flight spec assigned these to L6, but green-build invariant required moving them to L1).

14. **Add a Deviation entry** to the flight log's `## Deviations` section, naming what moved from L6 to L1 and why. List explicitly: deletion of `tests/test_behaviors.py`, deletion of `tests/test_agent.py::TestDirectAction` (containing `test_restart_bypass`), three `direct_actions` references stripped from `tests/test_config.py`, and the comment touch-up in `tests/browser/seeders.py`. Reason: green-build-between-legs invariant — these tests directly exercise infrastructure L1 removes.

15. **Update leg status to `landed`**, **do NOT commit**, and signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`step()` docstring stale after direct-action removal**: the existing docstring claims "Direct-action responses bypass the LLM entirely so `on_chunk` is never invoked on that path." After removal, that's no longer true. Remove the sentence rather than leaving it (small-model-friendly: don't lie in docstrings).
- **Empty `# Behavior` section**: after removing `direct_actions`, only `max_iterations` remains under that comment. Leave the comment; one field is still a behavior section.
- **Other importers of `CONTINUE_SCHEMA`**: confirmed via `rg` that only `core.py` imports it. If a stray importer surfaces during execution, follow the import to its caller — most likely the new inline location is correct, so update the importer to `from the_one.agent.core import CONTINUE_SCHEMA`.
- **`TestDirectAction` is the only class with `test_restart_bypass`**: deleting the whole class is fine; it's not a shared base class, no other test inherits from it.
- **`pytest --timeout=60`**: requires `pytest-timeout`. If it's not installed, drop the flag — the suite shouldn't have hanging tests after this leg, but the flag is defensive against the kind of hang that the agentic-workflow phase file warns about.
- **A test suite import error**: if `pytest tests/` fails at collection time with `ImportError: No module named 'the_one.agent.behaviors'`, the most likely culprit is a test file (other than the two known ones) still importing from `behaviors`. Run `rg "from the_one.agent.behaviors" tests/` and update accordingly.
- **`/api/agents` response shape**: `AgentConfig.model_dump()` is invoked for GET/POST/PUT `/api/agents` responses (`the_one/interfaces/web/api.py` lines 107, 118, 134). After this leg, `direct_actions` no longer appears in those payloads. Verified no JS or browser-test consumer reads it (`rg "direct_actions" the_one/interfaces/web/static tests/browser` returns empty). Inbound legacy payloads carrying the field are silently dropped by `extra: "ignore"` on `AgentConfig`. Documented here so the L1 reviewer doesn't flag the response-shape change as a regression.

## Files Affected

- `the_one/tools/git.py` — deleted
- `the_one/tools/memory.py` — deleted
- `the_one/tools/mission_control.py` — deleted
- `the_one/tools/restart.py` — deleted
- `the_one/tools/rollback.py` — deleted
- `the_one/tools/self_deploy.py` — deleted
- `the_one/tools/test_runner.py` — deleted
- `the_one/tools/builtins.py` — drop 7 imports + entries, update count comment to "7 built-in tools"
- `the_one/agent/behaviors.py` — deleted
- `the_one/agent/core.py` — drop `behaviors` import, inline `CONTINUE_SCHEMA`, remove direct-action branch in `step()`, remove `_match_direct_action` helper, fix docstring
- `the_one/agent/config.py` — drop `direct_actions` field on `AgentConfig`
- `tests/test_behaviors.py` — deleted
- `tests/test_agent.py` — drop `TestDirectAction` class
- `tests/test_config.py` — drop three `direct_actions` references (lines 24, 36, 46)
- `tests/browser/seeders.py` — drop `direct_actions` from docstring sentence at line 71
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — append leg progress + deviation

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (NOTE: per the agentic-workflow skill, this leg does NOT commit; the post-L6 review handles commit. Mark leg `landed`, not `completed`.):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/ --ignore=tests/browser` green)
- [ ] Update flight-log.md with leg progress entry (status `landed`)
- [ ] Update flight-log.md `## Deviations` section noting the L6→L1 test moves
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do **NOT** check off this leg in flight.md yet (deferred to post-L6 commit)
- [ ] Do **NOT** commit (deferred to post-L6 batch commit)
- [ ] Signal `[HANDOFF:review-needed]`
