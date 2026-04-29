# Leg: 06-test-sweep

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Sweep the test suite to remove obsolete coverage tied to the seven removed tools and the deleted `behaviors.py`, update the AIAT live tests so the surviving probes target paths that exist in the post-L4 runtime (`/app/...` not `/workspace/...`), and run the full default unit suite + browser suite to confirm the cumulative effect of L1-L5 is green. Specifically: delete `tests/test_aiat.py::test_git_status` and `test_run_tests`, update `test_tool_use_file_read` and `test_multi_step` probe paths from `/workspace/...` to `/app/...`, fix the long-broken `test_health` assertion to match the actual `/api/info` shape, and confirm the full suite is green modulo the pre-existing CSS-token anomaly. AIAT live verification against a running instance is deferred to L7 (HAT).

## Context

L6 is the last autonomous leg before the flight's batched code review and single commit (per the agentic-workflow skill). It does no source edits other than test file cleanup; the goal is to leave the test suite consistent with the post-L1-L5 codebase so the Reviewer in Phase 2d can read green-bar tests as a baseline rather than triaging stale failures.

Per flight Decision 5 + Technical Approach, L6 was originally scoped to also delete `tests/test_behaviors.py`, `tests/test_agent.py::test_restart_bypass`, and three `direct_actions` references in `tests/test_config.py`. **Those moved into L1** during design (recorded as a flight Deviation) because leaving them after L1's source-side deletion would have broken the green-build-between-legs invariant that the post-L6 batch-commit promise depends on. L6 retains the AIAT updates (off the default suite, no green-build invariant violation between legs) and the run-the-full-suite verification.

**Codebase audit findings (2026-04-28, post-L1+L2+L3+L4+L5 uncommitted):**

### `tests/test_aiat.py` — six surviving live tests, two removals, two path updates, one shape fix

| Line | Test | L6 action |
|------|------|-----------|
| 102-109 | `test_health` | **Fix** — assertion `"model" in data` is broken (was never in `/api/info`'s shape, predates F1). After L5, `/api/info` returns `{"version": "0.1.0", "base_prompt": "..."}`. Replace `"model"` assertion with `"base_prompt"` assertion (positive coverage of L5's surface). |
| 112-117 | `test_basic_chat` | No change. |
| 120-132 | `test_tool_use_file_read` | **Update** — change `/workspace/pyproject.toml` (line 126) to `/app/pyproject.toml`. Same target the L4 selftest fix used. |
| 135-149 | `test_git_status` | **Delete** — `git` tool removed in L1. Test exercises a tool that no longer exists. |
| 152-159 | `test_reset` | No change. |
| 162-172 | `test_run_tests` | **Delete** — `run_tests` tool removed in L1. |
| 175-184 | `test_self_awareness` | No change — generic question (agent's name + source-code directory). The agent will now answer with `/app` rather than `/workspace`; the assertion `"the-one" in text.lower()` survives either way. |
| 187-199 | `test_multi_step` | **Update** — change `/workspace/the_one/tools/` (line 193) to `/app/the_one/tools/`. Update line 197 assertion `"git" in text.lower() or "base" in text.lower() or len(text) > 20` to `"shell" in text.lower() or "base" in text.lower() or len(text) > 20` since `git.py` is gone but `base.py` (Tool ABC) and `shell.py` are still in the directory. |

After L6: 6 live tests remain (`test_health`, `test_basic_chat`, `test_tool_use_file_read`, `test_reset`, `test_self_awareness`, `test_multi_step`). The deletions reduce coverage, but the deleted tests targeted features that no longer exist.

### `tests/test_aiat.py::test_health` shape note

The current assertion at line 109:
```python
assert "model" in data, f"missing model in {data}"
```
fails against any `/api/info` shape this codebase has shipped — `info()` has never returned a `model` field (verified via git log on `app.py`'s `info` handler). This is a pre-existing AIAT-only break that hasn't surfaced because AIAT lives behind `pytest -m live` and the deploy pipeline's health-check uses `/api/selftest`, not `/api/info`. L6 fixes it as part of the AIAT cleanup so the L7 HAT pass doesn't trip on it. Strictly speaking this is out of flight spec; documented as a deviation.

### Full default unit suite at L6 start

- Test count: 395 passed, 1 pre-existing CSS-token red (`test_token_definitions.py::test_every_var_reference_is_defined`, predates F1, L1+L4+L5 modified zero CSS files / one CSS file with no new token references).
- L6 doesn't add or remove tests in the default suite. The count stays at 395 + 1 red.

### Browser suite

- Run via `pytest -m browser tests/browser/` against a per-test app subprocess. Each test spawns its own subprocess on a random port. Mock LLM provider used for deterministic responses.
- Visual snapshot baselines are gitignored (`tests/browser/__snapshots__/`); per the user's global instruction, snapshot tests are local-only. CI / Reviewer paths skip snapshot comparison.
- L1-L5 didn't touch any test fixture except via L1's `seeders.py` docstring update and L2's `test_agent.py` constructor edits. No browser test should regress.
- L5 added one new admin-page UI element (Base Prompt section) but no browser test asserts on its presence. No expected browser-test break.
- L4 simplified `/api/info` to `{"version": "0.1.0"}` then L5 extended it to `{"version", "base_prompt"}`. Browser tests use `/api/info` only for liveness probes; shape-agnostic.
- L6 verification: `pytest -m browser tests/browser/ --tb=short -q` should be green. Baseline preserved.

### AIAT live verification

- Runs against a running instance (`THE_ONE_TEST_URL` env var; defaults to `http://localhost:8484`).
- L6 cannot run AIAT against a live instance from inside the agentic-workflow (no live container available to the Developer agent).
- Deferred to **L7 HAT** — the operator runs `make rebuild` + `pytest -m live tests/test_aiat.py` against the fresh-built container, expecting all 6 surviving tests to pass.
- L6's responsibility is restricted to ensuring the test source is consistent with the post-L1-L5 runtime; live-pass verification is the operator's L7 job.

### `tests/test_aiat.py::has_tool_call` and friends

- The helper functions at the top of `test_aiat.py` (`has_tool_call`, `has_tool_result`, etc.) are tool-name agnostic. They just inspect response dicts. No update needed.

### Other test files audited (no L6 work needed)

- `tests/test_agent.py` — six `Agent(...)` sites already updated in L2; `TestDirectAction` already deleted in L1.
- `tests/test_config.py` — `direct_actions` references already stripped in L1; `BASE_PROMPT` rename + composition assertions already updated in L2.
- `tests/test_behaviors.py` — file already deleted in L1.
- `tests/test_db_migration.py` — fixture cleanup + new `TestSchemaV7::test_v7_strips_removed_tool_names` already done in L3.
- `tests/test_db_api.py` — `test_path_values_are_strings` already updated in L4.
- `tests/test_schema.py` — two tests already updated in L3 (out-of-flight-spec inline fix; flagged for the post-L6 reviewer).
- `tests/browser/seeders.py` — docstring already updated in L1.
- All other `tests/*.py` and `tests/browser/*.py` files — no references to removed tools, `behaviors.py`, `DEFAULT_SYSTEM_PROMPT`, `direct_actions`, `workspace_dir`, or Concourse env vars (verified via grep).

## Inputs

- L1 + L2 + L3 + L4 + L5 landed (uncommitted): seven tool source files removed, `behaviors.py` removed, `DIRECT_ACTIONS` / `match_direct_action` / `CONTINUE_SCHEMA` migrated to `core.py`, `direct_actions` field removed from `AgentConfig`, `BASE_PROMPT` constant established with additive composition, `Agent.__init__` no-default, schema at v7, CI pipeline trimmed, `/workspace` mount removed, `/api/info` extended with `base_prompt`, `/api/selftest` probe path fixed, agents.md + CLAUDE.md narrative updated, `.env.example` cleaned.
- `tests/test_aiat.py` carries `test_git_status`, `test_run_tests` (both targeting removed tools), and three `/workspace/...` path references.
- Default unit test baseline: 395 passed + 1 pre-existing CSS-token red.

## Outputs

After this leg:
- `tests/test_aiat.py::test_git_status` no longer exists.
- `tests/test_aiat.py::test_run_tests` no longer exists.
- `tests/test_aiat.py::test_tool_use_file_read` probes `/app/pyproject.toml`.
- `tests/test_aiat.py::test_multi_step` probes `/app/the_one/tools/` and asserts on a tool name that survives.
- `tests/test_aiat.py::test_health` asserts on `"base_prompt"` instead of the always-broken `"model"`.
- Default unit test suite green (395 passed, 1 pre-existing CSS-token red).
- Browser test suite green (run via `pytest -m browser tests/browser/`; snapshot baselines gitignored, CI / Reviewer skip snapshot comparison).
- `tests/test_aiat.py` has 6 `@pytest.mark.live` test functions (down from 8).
- No commit — deferred to Phase 2d batched review and commit.

## Acceptance Criteria

- [ ] `tests/test_aiat.py` does NOT contain `def test_git_status` or `def test_run_tests`.
- [ ] `tests/test_aiat.py` contains exactly 6 `@pytest.mark.live` test functions.
- [ ] `rg -n "/workspace" tests/test_aiat.py` returns no matches.
- [ ] `tests/test_aiat.py::test_tool_use_file_read` references `/app/pyproject.toml`.
- [ ] `tests/test_aiat.py::test_multi_step` references `/app/the_one/tools/`.
- [ ] `tests/test_aiat.py::test_multi_step` does NOT assert on `"git" in text.lower()`. Replacement asserts on `"shell"` or `"base"` (or `len(text) > 20` as the catch-all).
- [ ] `tests/test_aiat.py::test_health` does NOT assert on `"model" in data`. Replacement asserts on `"base_prompt" in data`.
- [ ] `python -m pytest tests/ --tb=short -q --ignore=tests/browser` exits 0 (modulo the pre-existing CSS-token anomaly). Test count unchanged from the post-L5 baseline (395 expected; verify by capturing the count before any L6 edits and comparing after).
- [ ] `python -m pytest -m browser tests/browser/ --tb=short -q --ignore=tests/browser/test_visual_snapshots.py` exits 0. Browser suite (excluding `test_visual_snapshots.py`, which compares against gitignored local baselines per user-global instruction) is green. If the agentic-workflow environment doesn't support Playwright/Chromium, document the limitation in the leg-progress entry and defer the run to L7 — does NOT block landing the leg.
- [ ] `rg -n "self_deploy|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool|behaviors\.py|DIRECT_ACTIONS|match_direct_action|direct_actions|workspace_dir|/workspace|concourse_target|concourse_pipeline|THE_ONE_CONCOURSE|THE_ONE_WORKSPACE|14 built-in tools|currently v3|## Self-Deployment|self-modifying" the_one/ tests/ ci/ scripts/ docker-compose.yml CLAUDE.md` returns matches ONLY in: (a) `the_one/db/schema.py` `REMOVED` set inside the v7 strip block (legitimate — migration target list); (b) fixture data in `tests/test_db_migration.py` exercising the v7 strip migration — both `test_preserves_all_fields` (1 match — the kept fixture row, e.g. `disabled_tools=["shell"]` after the L3 cleanup; this should NOT include any removed-tool names) and `test_v7_strips_removed_tool_names` (multiple matches — seeded "mixed", "removedonly" rows that test stripping). All other matches indicate a regression.
- [ ] Working tree on branch `flight/01-tool-reduction-self-modification-teardown`; **no commit made**.
- [ ] Flight log updated with leg progress entry under `## Leg Progress`, status `landed`. Add a Deviation entry for the `test_health` shape fix (out of flight spec — pre-existing AIAT-only break that L6 cleans up alongside the in-spec edits to keep the AIAT pass coherent for L7).
- [ ] Leg status set to `landed` in this file's header.

## Verification Steps

```bash
# 1. Removed tests gone
rg -n "def test_git_status|def test_run_tests" tests/test_aiat.py
# Expected: no output

# 2. Live test count
rg -n "@pytest\.mark\.live" tests/test_aiat.py | wc -l
# Expected: 6

# 3. /workspace gone from AIAT
rg -n "/workspace" tests/test_aiat.py
# Expected: no output

# 4. /app probes present
rg -n "/app/pyproject\.toml|/app/the_one/tools/" tests/test_aiat.py
# Expected: two matches

# 5. test_health no longer asserts "model"
rg -n '"model" in data' tests/test_aiat.py
# Expected: no output

# 6. test_health asserts base_prompt
rg -n '"base_prompt" in data' tests/test_aiat.py
# Expected: one match

# 7. test_multi_step assertion no longer hard-codes "git"
rg -n '"git" in text\.lower\(\)' tests/test_aiat.py
# Expected: no output

# 8. Default unit suite green (modulo pre-existing CSS red)
python -m pytest tests/ --tb=short -q --ignore=tests/browser
# Expected: 395 passed, 1 pre-existing CSS-token failure

# 9. Browser suite green (excluding visual snapshots, which are gitignored)
python -m pytest -m browser tests/browser/ --tb=short -q --ignore=tests/browser/test_visual_snapshots.py
# Expected: all collected pass

# 10. Comprehensive regression sweep — confirm L1-L5 + L6 changes are coherent
rg -n "self_deploy|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool|behaviors\.py|DIRECT_ACTIONS|match_direct_action|direct_actions|workspace_dir|/workspace|concourse_target|concourse_pipeline|THE_ONE_CONCOURSE|THE_ONE_WORKSPACE|14 built-in tools|currently v3|## Self-Deployment|self-modifying" the_one/ tests/ ci/ scripts/ docker-compose.yml CLAUDE.md
# Expected: matches ONLY in the_one/db/schema.py (REMOVED set) and tests/test_db_migration.py (TestSchemaV7 fixture data)
```

## Implementation Guidance

Work from project root `/home/cprch/projects/the-one`. Branch must be `flight/01-tool-reduction-self-modification-teardown`. Leg status `ready` → `in-flight` at start; `landed` at end. **No commit.**

1. **Delete `tests/test_aiat.py::test_git_status`** — remove lines 135-149 (the entire `@pytest.mark.live\ndef test_git_status(...) -> None: ...` function). Adjacent blank line spacing should be preserved (one blank line between functions).

2. **Delete `tests/test_aiat.py::test_run_tests`** — remove lines 162-172 (the entire `@pytest.mark.live\ndef test_run_tests(...) -> None: ...` function).

3. **Update `tests/test_aiat.py::test_tool_use_file_read`** at line 126:
   ```python
   "Read the file /workspace/pyproject.toml and tell me the project name.",
   ```
   to:
   ```python
   "Read the file /app/pyproject.toml and tell me the project name.",
   ```

4. **Update `tests/test_aiat.py::test_multi_step`** at line 193:
   ```python
   "List the files in /workspace/the_one/tools/ and tell me how many there are.",
   ```
   to:
   ```python
   "List the files in /app/the_one/tools/ and tell me how many there are.",
   ```
   And at line 197 (the assertion), change:
   ```python
   assert "git" in text.lower() or "base" in text.lower() or len(text) > 20, (
   ```
   to:
   ```python
   assert "shell" in text.lower() or "base" in text.lower() or len(text) > 20, (
   ```
   Rationale: `git.py` is gone post-L1; `shell.py` and `base.py` survive in `the_one/tools/`. Either name is a reasonable signal that the agent listed the directory and described its contents.

5. **Update `tests/test_aiat.py::test_health`** at line 109:
   ```python
   assert "model" in data, f"missing model in {data}"
   ```
   to:
   ```python
   assert "base_prompt" in data, f"missing base_prompt in {data}"
   ```
   The `"model"` assertion was always wrong (the `info()` handler never returned a `model` field). The `"base_prompt"` assertion provides positive coverage of L5's `/api/info` extension.

6. **Fix the L5-missed `/workspace` reference in `CLAUDE.md`**. Line 58 currently reads:
   ```
   **When `make rebuild` is NOT required**: editing files under `tests/` (tests run from `/workspace` via subprocess) or running ad-hoc one-off pytest invocations.
   ```
   After L4 dropped the `/workspace` bind-mount, the parenthetical is stale. Replace with:
   ```
   **When `make rebuild` is NOT required**: editing files under `tests/` (the test suite spawns its own uvicorn subprocess, independent of the served daemon) or running ad-hoc one-off pytest invocations.
   ```
   This mirrors the Makefile fix L4 made and the `CLAUDE.md:35` sentence L5 already rewrote. L5 missed this second site; L6 catches it as part of the regression sweep. Document as a deviation: "L5 docs-cleanup oversight — second `/workspace` reference in CLAUDE.md missed; corrected here."

7. **Run the default unit suite**:
   ```bash
   python -m pytest tests/ --tb=short -q --ignore=tests/browser
   ```
   Expected: 395 passed, 1 pre-existing CSS-token red. No regression.

8. **Run the browser suite** (excluding visual snapshots — gitignored per user-global instruction):
   ```bash
   python -m pytest -m browser tests/browser/ --tb=short -q --ignore=tests/browser/test_visual_snapshots.py
   ```
   Expected: green. If a browser test fails, investigate before signaling `[HANDOFF:review-needed]` — it's a regression worth catching now rather than during Phase 2d review.

   Note: browser tests require Playwright Python binding installed (`pip install -e ".[dev]"` should pull it in). If Playwright complains about missing browsers, run `python -m playwright install chromium` once. If the environment doesn't support browser tests at all, document the limitation in the leg-progress entry and let the operator run them at L7.

9. **Run the targeted verification commands** from the Verification Steps section (1-7 + 10).

10. **Document any browser-suite environment limitations** in the flight log if the browser suite couldn't run in the agentic-workflow's environment. The operator's L7 HAT pass will run the browser suite manually.

11. **Update the flight log**:
    - Append a `### 06-test-sweep` entry under `## Leg Progress` with status `landed`. Summary should include: tests deleted, paths updated, `test_health` shape fix, CLAUDE.md:58 cleanup, full unit suite result, browser suite result (or "deferred to L7" if the env couldn't run them).
    - Add Deviation entries under `## Deviations` for: (a) the `test_health` shape fix — pre-existing AIAT-only break L6 cleans up alongside the in-spec edits; (b) the CLAUDE.md:58 inline fix — L5 docs-cleanup oversight that L6 caught via the regression sweep.

12. **Set leg status to `landed`** in this file's header. Do **NOT** commit. Do **NOT** check off the leg in `flight.md`. **Signal `[HANDOFF:review-needed]`** — this is the last autonomous leg; Phase 2d (code review + commit) follows.

## Edge Cases

- **AIAT live-test verification deferred**: The Developer agent in L6 cannot spin up a live container with `make rebuild`. AIAT pass-fail against a live instance is verified at L7 (HAT), not L6. L6's responsibility ends at "test source is consistent with the post-rip runtime."
- **Browser suite environment**: Playwright is heavy. If the agentic-workflow's environment doesn't have Chromium installed, the browser suite step may fail at collection. Document the environment limitation in the leg-progress entry and let L7 run the suite manually. The default unit suite remaining green is sufficient for the L6 acceptance criteria's hard gate.
- **Comprehensive regression sweep matches**: the AC step 10 grep is intentionally broad. It expects matches in two known-legitimate places (the `REMOVED` set in `schema.py`, the v7 strip test's fixture data) and nothing else. If a match shows up elsewhere, it's a regression worth investigating before Phase 2d.
- **`test_self_awareness` answer-set drift**: the test asks for the agent's "name and source-code directory". After L4, `/workspace` is gone and the source is at `/app`. The agent's answer will reference `/app` (or simply not mention a path). The assertion `"the-one" in text.lower() or "the_one" in text.lower()` survives either way. No update needed.
- **Test count stability**: L6 deletes 2 AIAT tests; both are `@pytest.mark.live` (off the default suite). Default-suite test count stays at 395.
- **`test_health` always-broken history**: git blame on the `"model" in data` assertion will show this has been wrong since the test was added. L6's fix is a stealth bug repair; documented in the deviation note so the post-L6 reviewer knows it wasn't caused by F1 work.
- **Schema test inline fix from L3**: `tests/test_schema.py` had two tests that L3 inline-repaired (replacing `assert row[0] == 6` with `assert row[0] == CURRENT_VERSION`). L6's grep step 10 might surface `CURRENT_VERSION = 7` matches in `schema.py`; that's expected and legitimate. The grep targets `currently v3` (a stale narrative phrase), not the version constant.

## Files Affected

- `tests/test_aiat.py` — delete `test_git_status` and `test_run_tests`; update `test_tool_use_file_read` and `test_multi_step` probe paths + one assertion; fix `test_health` `"model"` assertion to `"base_prompt"`
- `CLAUDE.md` — line 58 parenthetical update (drop `/workspace` reference; L5 oversight)
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — append leg progress + deviation entries

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (NOTE: per the agentic-workflow skill, this is the last autonomous leg; the post-L6 review handles commit. Mark leg `landed`, not `completed`.):

- [ ] All acceptance criteria verified
- [ ] Default unit suite green (`pytest tests/ --ignore=tests/browser` modulo pre-existing CSS anomaly)
- [ ] Browser suite green (run if environment supports it; otherwise deferred to L7)
- [ ] Comprehensive regression sweep (AC step 10) shows only legitimate matches
- [ ] Update flight-log.md with leg progress entry (status `landed`)
- [ ] Update flight-log.md `## Deviations` section with the `test_health` shape fix
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do **NOT** check off this leg in flight.md yet (deferred to post-L6 commit)
- [ ] Do **NOT** commit (deferred to post-L6 batch commit — Phase 2d)
- [ ] Signal `[HANDOFF:review-needed]`
