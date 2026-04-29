# Flight Log: Tool Reduction & Self-Modification Teardown

**Flight**: [Tool Reduction & Self-Modification Teardown](flight.md)

## Summary

Flight execution started 2026-04-28 via `/agentic-workflow`. Branch `flight/01-tool-reduction-self-modification-teardown` created off `main`. L1-L6 are autonomous; L7 is HAT (interactive). Per the agentic-workflow skill, code review and commit are deferred to a single pass after L6 completes.

---

## Leg Progress

### 01-rip-tools-and-behaviors

**Status**: landed
**Started**: 2026-04-28
**Completed**: 2026-04-28

**Summary of changes:**
- Deleted 7 self-modification tool source files: `the_one/tools/{git,memory,mission_control,restart,rollback,self_deploy,test_runner}.py`.
- Updated `the_one/tools/builtins.py` to register exactly 7 built-in tools (`ShellTool`, `ReadFileTool`, `WriteFileTool`, `ListDirTool`, `HttpRequestTool`, `WebSearchTool`, `PythonExecTool`); count comment now reads "7 built-in tools".
- Deleted `the_one/agent/behaviors.py` (entire module, including `DIRECT_ACTIONS`, `match_direct_action`, `CONTINUE_SCHEMA`).
- Inlined `CONTINUE_SCHEMA` into `the_one/agent/core.py` at module scope (the only consumer per Decision 1).
- Removed `behaviors` import, the direct-action call site in `step()`, and the `_match_direct_action` static helper from `the_one/agent/core.py`. `step()` now begins with `self.messages.append(Message.user(user_input))` followed directly by the iteration loop. Stale docstring sentence about direct-action `on_chunk` bypass removed.
- Dropped `direct_actions: bool = True` field from `AgentConfig` in `the_one/agent/config.py`.
- Deleted `tests/test_behaviors.py`; removed `TestDirectAction` class (containing `test_restart_bypass`) from `tests/test_agent.py`; stripped three `direct_actions` references from `tests/test_config.py`; updated `tests/browser/seeders.py:71` docstring to drop `direct_actions` from the optional-field list.

**Verification:**
- Import smoke test: `BuiltinToolProvider().get_tools()` returns 7 tools.
- All grep sweeps from Verification Steps section returned clean (no references to removed classes, `behaviors` module, `DIRECT_ACTIONS`, `match_direct_action`, or `direct_actions`, modulo `--glob '!*.md'` exclusions for `agents.md`/`CLAUDE.md` narrative files L5 will rewrite).
- `pytest tests/ --ignore=tests/browser`: 394 passed, 1 unrelated pre-existing failure (`tests/test_token_definitions.py::test_every_var_reference_is_defined` — CSS token check; `--font-size-h3` referenced in `components.css:284` but not defined; the offending line was added by flight 06 commit `18a0cd8`, predates L1, and L1 modified no CSS files). See Anomalies section.
- L1-affected test files run clean in isolation: 18 passed in `tests/test_agent.py` + `tests/test_config.py`.

**Deviation note:** Per the leg artifact, `tests/test_behaviors.py`, `tests/test_agent.py::TestDirectAction::test_restart_bypass`, and three `direct_actions` references in `tests/test_config.py` were moved from the flight-spec L6 sweep into L1 to preserve the green-build-between-legs invariant. See Deviations section.

**No commit made.** Per agentic-workflow, commit is deferred to post-L6 batch review.

### 02-prompt-layering-and-base-rewrite

**Status**: landed
**Started**: 2026-04-28
**Completed**: 2026-04-28

**Summary of changes:**
- Renamed `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT` in `the_one/agent/config.py` and replaced its content with a general-purpose personal-assistant base prompt (296 words). New content contains no self-modification / deployment / methodology / `/workspace` / `/app` / `/mission-control` language; mentions `continue` and `tool` generically; closes with the layered-composition signal.
- Rewrote `AgentConfig.get_system_prompt()` for additive composition: returns `BASE_PROMPT` when `self.system_prompt == ""`, else `f"{BASE_PROMPT}\n\n---\n\n{self.system_prompt}"`. No replace-mode escape hatch (per Decision 4).
- Updated module docstring on `the_one/agent/config.py` from "default system prompt" to "base system prompt".
- Dropped the `system_prompt` default value from `Agent.__init__`'s signature in `the_one/agent/core.py` — the parameter is now required. Removed the now-unused `from the_one.agent.config import DEFAULT_SYSTEM_PROMPT` import. `core.py` no longer imports `BASE_PROMPT` either; it just consumes whatever string the caller passes (composition happens in `AgentConfig.get_system_prompt()` upstream).
- Updated six `Agent(...)` construction sites in `tests/test_agent.py` (lines 59, 78, 105, 135, 159, 173 — within the `TestNormalFlow`, `TestToolExecution`, `TestContinueSignal`, `TestMaxIterations`, `TestToolError`, `TestReset` classes) to pass `system_prompt="test"` explicitly, matching the convention in `test_auto_load.py:99`.
- Updated `tests/test_config.py`: import renamed (`DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT`); `TestGetSystemPrompt::test_empty_returns_default` now asserts on `BASE_PROMPT`; `test_custom_prompt_returned` renamed to `test_custom_prompt_appended` and asserts the additive composition `BASE_PROMPT + "\n\n---\n\nCustom prompt."`; `TestDefaultSystemPrompt` class renamed to `TestBasePrompt` with docstring + comment-header + assertion-variable rename.

**Verification:**
- `rg -n "DEFAULT_SYSTEM_PROMPT" the_one/ tests/ --glob '!*.md'`: no output.
- `rg -n "^BASE_PROMPT = " the_one/agent/config.py`: one match at line 7.
- `rg -n "from the_one.agent.config import.*(BASE_PROMPT|DEFAULT_SYSTEM_PROMPT)" the_one/agent/core.py`: no output.
- `inspect.signature(Agent.__init__).parameters['system_prompt'].default is inspect.Parameter.empty`: True.
- Composition smoke test (empty → `BASE_PROMPT`; non-empty → `BASE_PROMPT + "\n\n---\n\nPersona X"`): OK.
- Forbidden-vocabulary check (substrings + word-boundary `git`/`memory` + path-shaped `/app` + methodology phrases): no hits.
- Positive coverage: `continue` and `tool` both present in `BASE_PROMPT`.
- Word count: 296 (within 180-450 band; comfortably within flight-spec target 200-400).
- `rg -n 'Agent\(llm=' tests/test_agent.py | grep -v "system_prompt"`: no output (all six sites now pass an explicit prompt).
- `pytest tests/ --ignore=tests/browser`: 394 passed, 1 failed (pre-existing CSS-token anomaly carried over from L1 — `test_token_definitions.py::test_every_var_reference_is_defined`; out of L2 scope).

**Forward reference:** L5's docs sweep must rewrite `the_one/agents.md:57` to use `BASE_PROMPT` (not the old `DEFAULT_SYSTEM_PROMPT`). L2 deliberately leaves that `*.md` narrative file alone (verification greps use `--glob '!*.md'`).

**Deviation note:** Flight spec Decision 4 cited `tests/test_auto_load.py:99` and `tests/test_streaming.py:268` as the implicit-default sites. Fresh codebase audit shows those already pass explicit prompts. The actual six implicit-default sites were all in `tests/test_agent.py`. Recorded in Deviations section.

**No commit made.** Per agentic-workflow, commit is deferred to post-L6 batch review.

### 03-schema-v7-tool-name-strip

**Status**: landed
**Started**: 2026-04-28
**Completed**: 2026-04-28

**Summary of changes:**
- `the_one/db/schema.py`: bumped `CURRENT_VERSION` 6 → 7; added `import json` (sibling to `import aiosqlite`); appended an `if version < 7:` block to `ensure_schema()` that mirrors the v3/v5/v6 inline-migration pattern. Block defines `REMOVED = {"self_deploy", "rollback", "restart", "run_tests", "git", "memory", "mission_control"}`, selects every agents-table row, parses both JSON columns, filters out the seven removed names, and writes back via parameterized UPDATE. NULL whitelist preserved as NULL (never coerced to `[]`); empty-list-after-strip is the locked-down default. Uses the `async with conn.execute(...) as cursor:` aiosqlite idiom matching `_get_version` and `repositories.py`. Closes with `INSERT INTO schema_version (version) VALUES (?)` and `await conn.commit()`.
- `tests/test_db_migration.py`: fixture cleanup per Decision 5 — `test_preserves_all_fields` now seeds `disabled_tools=["shell"]` instead of `["self_deploy"]`, so the JSON-migration test no longer overlaps with the v7 strip. Appended `TestSchemaV7::test_v7_strips_removed_tool_names` covering the four edge-case rows (mixed kept+removed, NULL whitelist, removed-only whitelist, all-kept) plus a final schema-version assertion. Test uses the "rewind schema_version" technique (`DELETE FROM schema_version WHERE version = 7`) to drive a real v6→v7 transition through `ensure_schema()`.

**Verification:**
- `rg -n "^CURRENT_VERSION = " the_one/db/schema.py`: `9:CURRENT_VERSION = 7`.
- `rg -n "if version < 7:" the_one/db/schema.py`: one match at line 251.
- `rg -n "def test_v7_strips_removed_tool_names" tests/test_db_migration.py`: one match at line 103.
- `rg -n "self_deploy|rollback|restart|run_tests|GitTool|MemoryTool|MissionControlTool" the_one/db/ tests/test_db_migration.py --glob '!*.md'`: matches confined to (a) the `REMOVED` set in `schema.py` and (b) the new `TestSchemaV7` fixture data — no stale matches in `test_preserves_all_fields`.
- `pytest tests/test_db_migration.py -v`: 5 passed (4 existing + the new v7 test).
- End-to-end smoke: fresh DB → ensure_schema → MAX(version) == CURRENT_VERSION == 7; second `ensure_schema` call adds zero rows to schema_version (idempotent). Output: `OK`.
- `pytest tests/ --ignore=tests/browser`: 395 passed, 1 pre-existing CSS-token failure (`test_token_definitions.py::test_every_var_reference_is_defined` — carried over from L1, predates this flight). Test-count delta: 394 → 395 (the new v7 test adds one).

**Out-of-scope edits (regression repair):**
The `CURRENT_VERSION = 7` bump immediately broke two assertions in `tests/test_schema.py` (`test_fresh_db_schema_version_is_6` line 144 and `test_idempotent_ensure_schema` line 323) which hardcoded `assert row[0] == 6`. These tests live outside the leg's stated "Files Affected" scope, but leaving them red would violate the green-build-between-legs invariant that the agentic-workflow skill relies on for regression detection. Repaired by:
- Adding `CURRENT_VERSION` to the existing `from the_one.db.schema import ensure_schema` line (one-token import addition).
- Replacing the two hardcoded `6` literals with `CURRENT_VERSION`.
- Renaming `test_fresh_db_schema_version_is_6` → `test_fresh_db_schema_version_is_current` so the test name no longer encodes a specific version (future-proofs against v8+).

The leg artifact's "Files Affected" section did not anticipate this coupling. Flagging for the post-L6 reviewer to confirm the fix is acceptable; if not, alternatives are (a) revert and pin the assertions to literal `7`, or (b) move the fix into L6 (test sweep) — but option (b) leaves an intermediate red between L3 and L6, which the skill's review-after-L6 model assumes will not happen.

**No commit made.** Per agentic-workflow, commit is deferred to post-L6 batch review.

### 04-ci-and-runtime-teardown

**Status**: landed
**Started**: 2026-04-28
**Completed**: 2026-04-28

**Summary of changes:**
- `ci/pipeline.yml`: dropped the `resources:` section (heartbeat time resource) and four agent-facing jobs (`autopilot`, `rollback`, `pause-autopilot`, `unpause-autopilot`, `restart`). Retained the `deploy` job with its three tasks (`test`, `build-and-deploy`, `health-check`) and the `on_failure: do: - task: auto-rollback` block. Also dropped the `CONCOURSE_PASS` parameter and `-e CONCOURSE_PASS` env-var passthrough from the `build-and-deploy` and `auto-rollback` tasks (deploy.sh no longer consumes it). `WORKSPACE_PATH` retained on `test`, `build-and-deploy`, and `auto-rollback` tasks (legitimate source-mount needs for tests / docker build / accessing deploy.sh).
- `docker-compose.yml`: dropped `- .:/workspace` volume, `THE_ONE_WORKSPACE_DIR=/workspace`, six `THE_ONE_CONCOURSE_*` env vars, the `concourse` network attachment in the service, and the `concourse: external: true ; name: concourse-local_default` network definition. Retained `extra_hosts: host.docker.internal:host-gateway` (used by the Ollama provider), `the_one_data` named volume, port mapping `8484:8484`, Ollama env vars, `THE_ONE_HOST=0.0.0.0`, and `THE_ONE_DEV_MODE=true`.
- `scripts/entrypoint.sh`: shrunk from 33 lines to 4 — shebang, one-line comment header (`# Container startup`), `set -e`, `exec "$@"`. No more git config / mission-control clone / fly install / fly login.
- `ci/deploy.sh`: dropped `-v "${WORKSPACE_PATH}:/workspace"`, `-e THE_ONE_WORKSPACE_DIR`, all five `-e THE_ONE_CONCOURSE_*` env vars, and `--network concourse-local_default`. Retained `--add-host host.docker.internal:host-gateway`. `WORKSPACE_PATH` and `CONCOURSE_PASS` parameter requirements dropped; the script now needs only the image-tag positional arg. `THE_ONE_DEV_MODE` intentionally not set here (production deploys are non-dev — asymmetric vs docker-compose).
- `the_one/config.py`: dropped `workspace_dir`, `concourse_target`, `concourse_pipeline` fields and the `# Concourse CI` section header from `Settings`. Resulting public fields: `host`, `port`, `dev_mode`, `data_dir` plus `agents_dir` and `db_path` `@property` accessors. Verified via `Settings.model_fields == {'host', 'port', 'dev_mode', 'data_dir'}`.
- `the_one/interfaces/web/app.py`: simplified `/api/info` to `return {"version": "0.1.0"}` — dropped the `.deploy-status.json` read block (no writer remains since L1 deleted `self_deploy.py`) and the local `import json as _json` (only used inside the deleted block; module-level `json` import covers other call sites). Changed `/api/selftest` tool-use probe path from `/workspace/pyproject.toml` to `/app/pyproject.toml` (the path that exists in the running container per Dockerfile `WORKDIR /app` + `COPY pyproject.toml .`).
- `tests/test_db_api.py::test_path_values_are_strings`: dropped the two `workspace_dir` assertions; now asserts only on `data["data_dir"]` (and the `PosixPath` substring guard on it).
- `Makefile` lines 6-7 parenthetical: rewritten from "(The `/workspace` bind-mount is used by tests which spawn their own uvicorn subprocess; it does NOT feed the served app.)" to "(Tests spawn their own uvicorn subprocess via the conftest fixtures; that path is independent of the container.)" — preserves the spirit (tests don't go through the container) without referencing the removed mount.

**Verification:**
- `rg -n "^  - name:" ci/pipeline.yml`: one match (`- name: deploy`).
- `rg -n "name: (autopilot|pause-autopilot|unpause-autopilot|heartbeat)|^  - name: rollback$|^  - name: restart$" ci/pipeline.yml`: no output.
- `rg -n "/workspace|THE_ONE_CONCOURSE|THE_ONE_WORKSPACE_DIR|concourse-local_default" docker-compose.yml`: no output.
- `rg -n "host.docker.internal:host-gateway|the_one_data|THE_ONE_LLM_PROVIDER" docker-compose.yml`: matches confirming preserved entries.
- `wc -l scripts/entrypoint.sh`: 4 lines.
- `rg -n "fly|mission-control|safe.directory" scripts/entrypoint.sh`: no output.
- `rg -n "/workspace|THE_ONE_CONCOURSE|--network concourse-local_default" ci/deploy.sh`: no output.
- `rg -n "host.docker.internal:host-gateway" ci/deploy.sh`: one match.
- `python -c "from the_one.config import Settings; assert set(Settings.model_fields) == {'host', 'port', 'dev_mode', 'data_dir'}"`: OK.
- `rg -n "deploy-status|workspace_dir" the_one/interfaces/web/app.py`: no output.
- `rg -n '/app/pyproject.toml' the_one/interfaces/web/app.py`: one match (line 548).
- `rg -n '/workspace/pyproject.toml' the_one/interfaces/web/app.py`: no output.
- `rg -n 'workspace_dir' tests/test_db_api.py`: no output.
- `rg -n "workspace_dir|concourse_target|concourse_pipeline" the_one/ tests/ --glob '!*.md'`: matches confined to `the_one/interfaces/web/static/js/areas/admin/system-page.js` (L5's responsibility — Edge Cases section explicitly flags the L4→L5 acceptable interim incoherence; browser tests don't assert on the text).
- `rg -n "/workspace" the_one/ tests/ --glob '!*.md' --glob '!test_aiat.py'`: no matches.
- `pytest tests/ --ignore=tests/browser`: 395 passed, 1 failed (pre-existing CSS-token anomaly from L1 — `test_token_definitions.py::test_every_var_reference_is_defined`; unrelated to L4). Test count delta: 0 (L4 neither adds nor removes tests).

**Forward references:**
- L5 sweeps `the_one/interfaces/web/static/js/areas/admin/system-page.js` (drop the `workspace_dir`, `concourse_target`, `concourse_pipeline` field renderers and the "Concourse CI" subsection).
- L5 sweeps `the_one/agents.md:42` (the Settings module description still mentions `workspace_dir` — `*.md` narrative file, out of L4 scope).
- L6 sweeps `tests/test_aiat.py:126` and `:193` (`/workspace/pyproject.toml`, `/workspace/the_one/tools/` — AIAT tests live under `pytest -m live`, off the default suite, so they don't break the build).
- Concourse pipeline must be re-pushed (`fly set-pipeline -p the-one -c ci/pipeline.yml`) for the trim to take effect against the live Concourse instance — operator concern, out of leg scope.

**No commit made.** Per agentic-workflow, commit is deferred to post-L6 batch review.

### 05-ui-and-docs-cleanup

**Status**: landed
**Started**: 2026-04-28
**Completed**: 2026-04-28

**Summary of changes:**
- `the_one/interfaces/web/static/js/areas/studio.js` (lines 151-156): rewrote `TOOL_CATEGORIES` to 3 categories × 7 tools — `Filesystem` (`read_file`, `write_file`, `list_dir`), `Execution` (`shell`, `python_exec`), `Web` (`http_request`, `web_search`). Dropped `run_tests` from Execution; deleted the entire `System` banner key.
- `the_one/interfaces/web/static/js/areas/admin/system-page.js`:
  - `SETTING_SECTIONS` reduced to `Paths` (`data_dir` only) + `Server` (`host`, `port`, `dev_mode`). Dropped the `Concourse CI` section descriptor and `workspace_dir` from `Paths`.
  - `FIELD_LABELS` reduced to `data_dir`, `host`, `port`, `dev_mode`. Dropped `workspace_dir`, `concourse_target`, `concourse_pipeline` labels.
  - Added new `Base Prompt` admin section after the `Encryption` section: a `<pre class="admin-base-prompt" data-testid="base-prompt-content">` block with introductory copy explaining the layered-prompt architecture.
  - Added `fetchBasePrompt(container)` helper (placed immediately after `fetchSettings`) that GETs `/api/info`, reads `data.base_prompt`, and writes it via `preEl.textContent = ...` (XSS-safe text-node assignment, no `innerHTML`). Falls back to `'(base prompt unavailable)'` when the field is missing and `'(failed to load)'` on fetch error.
  - `renderSystemPage` now calls `fetchBasePrompt(container)` after `fetchSettings(container)`.
- `the_one/interfaces/web/static/css/admin.css`: added `.area-admin .admin-base-prompt` rule (16 lines, after the existing `.admin-system-flash.error` declaration). Uses tokens `--surface`, `--border`, `--panel-radius-sm`, `--font-family-mono`, `--font-size-body-sm`, `--fg` — all six pre-verified against `tokens.css` / `fonts.css` before the edit landed. `max-height: 24rem; overflow-y: auto` keeps a long base prompt from dominating the page.
- `the_one/interfaces/web/app.py`:
  - Added module-level `from the_one.agent.config import BASE_PROMPT` immediately after the `from the_one.agent import Agent` import (no circular-import risk; `agent.config` does not import from `interfaces/`).
  - `info()` now returns `{"version": "0.1.0", "base_prompt": BASE_PROMPT}`. Verified via the leg's prescribed Python smoke (`asyncio.run(info())` round-trip equals `BASE_PROMPT`).
- `the_one/agents.md` — nine narrative edits:
  - Line 11: `self-modifying LLM agent` → `general-purpose LLM agent`.
  - Line 42 (config Key properties): dropped `workspace_dir`, added `dev_mode (default: false)`.
  - Line 57 (`agent/config.py` row): `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT`; "fallback prompt" → "the foundational base prompt for layered composition".
  - Line 60: deleted entire `behaviors.py` row from the agent module map.
  - Line 62 (`Agent.step() flow`): dropped `→ check direct actions` step.
  - Tools table (formerly lines 80-93): rewrote to 5 source-file rows + 2 base/provider rows (7 entries total): `base.py`, `provider.py`, `builtins.py` (now says "all 7 built-in tools"), `shell.py`, `filesystem.py`, `python_exec.py`, `web.py`. Dropped the seven removed-tool rows.
  - Dependency-graph block: dropped the `agent/behaviors.py` line.
  - Tool-Providers paragraph: `provides the 14 built-in tools` → `provides the 7 built-in tools`.
  - Deleted the entire `### Direct Actions` section (header + paragraph). `### Tool Providers` now flows directly into `### Continue Signal`.
  - `### Continue Signal`: clarified `CONTINUE_SCHEMA` is "defined inline in `core.py`" (was implicitly part of the deleted `behaviors.py`).
- `CLAUDE.md` — six narrative edits:
  - Line 7 (`## What This Is`): replaced the self-modifying framing with general-purpose framing per the leg spec.
  - Line 35 parenthetical: rewrote the `/workspace bind-mount` sentence to `The test suite spawns its own uvicorn subprocess; that path is independent of the served daemon at port 8484.` Mirrors the L4 Makefile fix.
  - Line 66 Tool-layer paragraph: `14 built-in tools` → `7 built-in tools`.
  - Lines 68-71 Agent-loop paragraph: rewrote to drop the `behaviors.py` reference and the Direct-actions bullet; kept the Continue-signal explanation (now anchored to `core.py`); kept the max-iteration safety limit.
  - Line 75: schema `currently v3` → `currently v7`.
  - Deleted the entire `## Self-Deployment` section (header through the bind-mount paragraph). `## Configuration` now follows the Architecture section directly.
  - `## Configuration` paragraph: dropped `workspace_dir` and `Concourse settings`; result lists `host, port, data_dir, dev_mode`.
- `.env.example`: dropped the seven-line `# Concourse CI (for self-deploy/rollback/restart)` block + the six `THE_ONE_CONCOURSE_*` lines. Resulting file ends after `THE_ONE_PORT=8484` (14 lines vs. 21 before).

**Verification:**
- Pre-edit token grep against `the_one/interfaces/web/static/css/tokens.css` and `fonts.css`: all six referenced tokens (`--surface`, `--border`, `--panel-radius-sm`, `--font-family-mono`, `--font-size-body-sm`, `--fg`) confirmed defined. The `.admin-base-prompt` rule introduces no new undefined references.
- `rg -n "TOOL_CATEGORIES" the_one/interfaces/web/static/js/areas/studio.js`: 2 matches (the assignment + one consumer reference at line 441 in `studioContext`); neither contains `'run_tests'`, `'self_deploy'`, `'rollback'`, `'restart'`, `'mission_control'`, or `'git'` in the categories block.
- `rg -n "Concourse CI|workspace_dir|concourse_target|concourse_pipeline" the_one/interfaces/web/static/js/areas/admin/system-page.js`: no output.
- `rg -n "self-modifying|behaviors\.py|DEFAULT_SYSTEM_PROMPT|DIRECT_ACTIONS|match_direct_action|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool|workspace_dir|/workspace|### Direct Actions" the_one/agents.md`: no output.
- `rg -n "BASE_PROMPT|7 built-in tools" the_one/agents.md`: 3 matches.
- `rg -n "## Self-Deployment|self-modifying|behaviors\.py|Direct actions|workspace_dir|Concourse settings|14 built-in tools|/workspace bind-mount|currently v3" CLAUDE.md`: no output.
- `rg -n "7 built-in tools|currently v7" CLAUDE.md`: 2 matches.
- `rg -n "CONCOURSE|WORKSPACE" .env.example`: no output.
- `python3 -c "import asyncio; from the_one.interfaces.web.app import info; from the_one.agent.config import BASE_PROMPT; r=asyncio.run(info()); assert r['version']=='0.1.0' and r['base_prompt']==BASE_PROMPT; print('OK')"`: `OK`.
- `python3 -m pytest tests/ --tb=short -q --ignore=tests/browser`: **395 passed, 1 failed** — the failed test is `tests/test_token_definitions.py::test_every_var_reference_is_defined`, the L1-anomaly red, reporting only the pre-existing `--font-size-h3` undefined ref (no new tokens flagged from L5's CSS). Test count delta from pre-L5 baseline: 0 (L5 neither adds nor removes tests).
- `python3 -m pytest tests/test_db_api.py -v`: 13 passed (the `/api/info` shape change is additive; the settings test doesn't regress).

**Deviations / surprises:**
- None. Implementation followed the leg spec verbatim. The sole judgment call (where to slot the `.admin-base-prompt` CSS rule) was placed after the `.admin-system-flash.error` declaration and before the `.admin-theme-toggle` block — keeping it grouped with the `admin-system-section`-related rules.

**Forward references:**
- L6 may want to cover the new `/api/info` `base_prompt` shape with an explicit unit test (the L5 smoke covers it ad-hoc; L6's test sweep is the natural home for a permanent assertion).
- HAT (L7) will manually exercise the rendered `Base Prompt` admin section — there is no automated browser/visual coverage for it (snapshot suite only screenshots LLM Providers).

**No commit made.** Per agentic-workflow, commit is deferred to post-L6 batch review.

### 06-test-sweep

**Status**: landed
**Started**: 2026-04-28
**Completed**: 2026-04-28

**Summary of changes:**
- `tests/test_aiat.py`:
  - Deleted `test_git_status` (targeted the removed `git` tool).
  - Deleted `test_run_tests` (targeted the removed `run_tests` tool).
  - `test_tool_use_file_read`: probe path `/workspace/pyproject.toml` → `/app/pyproject.toml` (matches the L4 `/api/selftest` fix).
  - `test_multi_step`: probe path `/workspace/the_one/tools/` → `/app/the_one/tools/`; assertion `"git" in text.lower()` → `"shell" in text.lower()` (since `git.py` was removed in L1; `shell.py` and `base.py` remain).
  - `test_health`: assertion `"model" in data` → `"base_prompt" in data` — the `"model"` assertion never matched any `/api/info` shape this codebase has shipped (pre-existing AIAT-only break); replacement provides positive coverage of L5's `/api/info` extension.
  - Removed unused `import json` (logical consequence — only `test_git_status` and `test_run_tests` used `json.dumps`; both were just deleted). `ruff check tests/test_aiat.py` returns "All checks passed!".
- `CLAUDE.md` line 58: rewrote the parenthetical from `(tests run from /workspace via subprocess)` to `(the test suite spawns its own uvicorn subprocess, independent of the served daemon)` — L5 docs-cleanup oversight that L6 caught via the regression sweep. Mirrors the L4 Makefile fix and the L5 rewrite of `CLAUDE.md:35`.

**Verification:**
- AC step 1 (`rg "def test_git_status|def test_run_tests" tests/test_aiat.py`): no output.
- AC step 2 (`rg "@pytest.mark.live" tests/test_aiat.py | wc -l`): 6.
- AC step 3 (`rg "/workspace" tests/test_aiat.py`): no output.
- AC step 4 (`rg "/app/pyproject.toml|/app/the_one/tools/" tests/test_aiat.py`): two matches at lines 125 and 162.
- AC step 5 (`rg '"model" in data' tests/test_aiat.py`): no output.
- AC step 6 (`rg '"base_prompt" in data' tests/test_aiat.py`): one match at line 108.
- AC step 7 (`rg '"git" in text.lower\(\)' tests/test_aiat.py`): no output.
- AC step 8 — default unit suite: **395 passed, 1 failed** (`test_token_definitions.py::test_every_var_reference_is_defined` — the L1-anomaly CSS-token red, predates F1, expected). Pre-L6 baseline captured before any edits: 395 passed, 1 failed, 396 collected. Post-L6: 395 passed, 1 failed, 396 collected. Test-count delta: **0** (the two AIAT deletions are `@pytest.mark.live`, off the default suite — collected count moved from 8 deselected pre-L6 to 6 deselected post-L6, default-suite counts unchanged).
- AC step 9 — browser suite (excluding `test_visual_snapshots.py` per user-global gitignored-snapshots instruction): **220 passed** in 132s. No regression.
- AC step 10 — comprehensive regression sweep: matches confined to (a) `the_one/db/schema.py:262` (the `REMOVED` set in the v7 strip block — legitimate migration target list); (b) `tests/test_db_migration.py:124,125,138` (all inside `TestSchemaV7::test_v7_strips_removed_tool_names`'s fixture rows — `mixed`, `removedonly`, plus the `disabled_tools` mirror — all legitimate seed data exercising the v7 strip). `test_preserves_all_fields` returns no matches (per the L3 cleanup). **No unexpected matches; full L1-L6 coherence confirmed.**
- `ruff check tests/test_aiat.py`: All checks passed.

**Live AIAT verification deferred to L7 (HAT).** L6 cannot spin up a live container from inside the agentic-workflow; the operator runs `make rebuild` + `pytest -m live tests/test_aiat.py` against the fresh-built container during HAT, expecting all 6 surviving tests to pass.

**No commit made.** Per agentic-workflow, this is the last autonomous leg — Phase 2d (Reviewer over the cumulative L1-L6 changes, then single commit) follows.

### Flight Director Notes

**2026-04-28 — Flight start**

- Phase file loaded from `the-one/.flightops/agent-crews/leg-execution.md` (project-specific, not default fallback). Crew: Developer (Sonnet) + Reviewer (Haiku) + optional Accessibility Reviewer (Sonnet).
- Crew file validated: `## Crew`, `## Interaction Protocol`, and `## Prompts` sections present with fenced code blocks. No malformations.
- Flight transitioned `ready` → `in-flight`.
- Branch strategy: `branch` (per `.flightops/ARTIFACTS.md`). All agents work in `/home/cprch/projects/the-one`.
- Leg planning order: L1 → L2 → L3 → L4 → L5 → L6 → review/commit → L7 (HAT).
- L7 will be handled interactively (no autonomous Developer/Reviewer agents) per the skill's HAT protocol.

**2026-04-28 — L1 design + design-review cycle 1**

- Drafted leg artifact `01-rip-tools-and-behaviors.md`. Identified during cross-reference that `tests/test_behaviors.py`, `tests/test_agent.py::TestDirectAction::test_restart_bypass`, and `tests/test_config.py` `direct_actions` assertions all directly exercise infrastructure L1 removes. Flight spec assigned these to L6, but green-build-between-legs invariant requires moving them to L1. Recorded as a flight deviation in the leg's plan.
- Spawned Developer (Sonnet, `general-purpose`) for design review. Verdict: **approve with changes**. Issues:
  - **High**: acceptance-criteria greps over-scoped against `the_one/` would hit the `agents.md` narrative file (which L5 will rewrite) and produce false-positive failures. Fixed by adding `--glob '!*.md'` to the relevant grep checks; documented `agents.md` and `CLAUDE.md` as stale-until-L5 in Context.
  - **Medium**: `/api/agents` response shape silently loses `direct_actions` after L1. Verified no JS/browser-test consumer reads it. Added an Edge Cases entry noting the change so the L1 reviewer doesn't flag it as a regression.
  - **Medium**: CLAUDE.md narrative also stale-until-L5; added to Context.
  - **Low**: line-range citation in step 4 was off by one; replaced numeric range with prose-only direction.
  - **Low**: noted `test_db_migration.py:85` `disabled_tools=["self_deploy"]` is intentionally untouched by L1 (L3 will edit it as part of the v7 migration test split).
  - Suggestion accepted: added an explicit import smoke-test verification step.
  - Suggestion accepted: dropped `--timeout=60` from the primary pytest run; kept as a defensive option in Edge Cases.
  - Suggestion accepted: deviation entry now lists each test file by name with rationale.
- Edits applied are mechanical (grep-scope additions, Context/Edge Cases notes, prose-only step 4). No structural change to the leg's design. Skipping a second design review per agentic-workflow rules ("Skip if only minor/cosmetic fixes were applied").

**2026-04-28 — L1 implementation close**

- Spawned Developer (Sonnet, `general-purpose`) for L1 implementation. Agent updated leg `ready` → `in-flight`, executed all 15 steps, ran the unit suite, signalled `[HANDOFF:review-needed]`, marked leg `landed`. No commit (per agentic-workflow deferral).
- 394 tests pass. One pre-existing CSS-token test (`test_token_definitions.py::test_every_var_reference_is_defined`) is red on `main` — Developer audited and confirmed it predates this flight (introduced by flight 06 commit `18a0cd8`); L1 modified zero CSS files. Recorded as Anomaly. Flight Director note: this contradicts the leg's Inputs assertion that the suite was green at branch start; the assertion was incorrect and the suite was already 1-test red. Carrying forward as a known-issue rather than fixing here — fixing it sits outside the L1 (and arguably the F1) scope. Flag for the post-L6 reviewer to decide whether to address inline before commit, or punt to a separate maintenance task.
- Proceeding to L2.

**2026-04-28 — L2 design + design-review cycle 1**

- Drafted leg artifact `02-prompt-layering-and-base-rewrite.md`. Codebase audit revealed flight spec Decision 4 had an inverted reading: `test_auto_load.py:99` and `test_streaming.py:268` were cited as relying on `Agent.__init__`'s default `system_prompt`, but those sites already pass explicit prompts. The actual six implicit-default sites are all in `tests/test_agent.py:59,78,105,135,159,173`. Recorded as a flight deviation in the leg's plan.
- Spawned Developer (Sonnet, `general-purpose`) for design review. Verdict: **approve with changes**. Issues:
  - **Medium**: stale line cite `tests/test_streaming.py:471` should be `:468`. Fixed.
  - **Medium**: forbidden-vocabulary list missed `git`, `memory`, `autopilot`. Added (with word-boundary check for the tool names so "category"/"happen" don't false-positive).
  - **Medium**: bare `'/app'` substring check would false-positive on `/application`, `mapping`, etc. Tightened to path-shaped variants only.
  - **Low**: BASE_PROMPT draft tonal redlines for small-model accessibility — replace em-dashes with commas/colons, "throat-clearing" → "filler openings", "scratchpad" → "note-taker", "foundations" → "rules". Applied all of these.
  - **Low**: word-count gate slop (180-450) wider than "approximately 200-400". Aligned the AC text to "180-450" to match the gate (rather than tightening the gate, since user redlines might push to either edge).
  - **Low**: made the `test_custom_prompt_returned` → `test_custom_prompt_appended` rename mandatory in AC (was hedged with "Optionally").
  - **Low**: tightened `reset()` edge-case description to distinguish production-path (composed-via-factory) from test-path (literal fixture).
  - Suggestion accepted: positive `'tool' in BASE_PROMPT` check added.
  - Suggestion accepted: comment header rename surfaced in AC.
  - Suggestion accepted: forward-reference to L5 (rewrite `agents.md:57` to use `BASE_PROMPT`) added to deviation entry.
- All edits are clarifications, gate-tightening, and tonal redlines on the draft. No structural change to the leg's design. Skipping a second design review per agentic-workflow rules.
- Per Decision 4, the user is supposed to redline the BASE_PROMPT draft; in auto mode, applying the reviewer's suggested redlines and proceeding. The user can interject (or use L7's HAT pass) to course-correct voice if needed.

**2026-04-28 — L2 implementation close**

- Spawned Developer (Sonnet, `general-purpose`) for L2 implementation. Agent updated leg `ready` → `in-flight`, executed all guidance steps, ran the unit suite, signalled `[HANDOFF:review-needed]`, marked leg `landed`. No commit (per agentic-workflow deferral).
- Test suite remains 394 passed / 1 pre-existing red (CSS-token anomaly carried over from L1) — no L2 regression.
- Developer also updated the `the_one/agent/config.py` module docstring from "default system prompt" to "base system prompt" — minor follow-on edit, not in the leg's Files Affected list but consistent with the rename. Acceptable variation; flagged for the post-L6 reviewer.
- Developer note: had to install `anthropic>=0.40` and `openai>=1.0` into the venv to enable `tests/test_streaming.py` collection. Pre-existing optional-deps state was apparently incomplete in this fresh environment; reinstall restored the same baseline as L1's run. Recorded as an environment note, not an L2 regression.
- Proceeding to L3.

**2026-04-28 — L3 design + design-review cycle 1**

- Drafted leg artifact `03-schema-v7-tool-name-strip.md`. Included `import json` plumbing, the v7 strip block following the v3/v5/v6 pattern, fixture cleanup of `test_preserves_all_fields`, and a new `TestSchemaV7` class with a four-row test seed + five-assertion bundle.
- Spawned Developer (Sonnet, `general-purpose`) for design review. Verdict: **approve with changes**. Issues:
  - **Medium**: cursor pattern was bare `cursor = await conn.execute(...)` (matched flight pseudocode but not codebase idiom). Switched to `async with conn.execute(...) as cursor:` matching `_get_version` and `repositories.py`.
  - **Low**: AC grep was over-broad — would catch `tests/test_aiat.py::test_run_tests`, `tests/browser/seeders.py`, and incidental `restart` mentions in unrelated comments. Tightened the scope to `tests/test_db_migration.py` only.
  - **Low**: edge cases didn't cover `enabled_tools = ""` (empty string). Added a note explaining empty-string is treated identically to NULL.
  - **Low**: invalid-JSON edge case wasn't tagged "no test required" explicitly. Added the tag.
  - Suggestion accepted: added an "all-kept" row to the test seed to guard against over-stripping; added a 4th-bullet AC for that case.
  - Suggestion accepted: dropped the function-scoped `import json` / `import aiosqlite` from the new test (existing module-level imports cover both).
  - Suggestion accepted: clarified the test-suite baseline (394 + pre-existing CSS red) so the implementer knows what to expect.
  - Reviewer confirmed the "rewind schema_version" testing technique is correct (`_get_version` returns `MAX(version)`; deleting the v7 row makes it report 6, triggering the v7 block on re-run).
  - Reviewer confirmed cache-freshness audit comes back clean — `AgentFactory.create()` reloads `AgentConfig` on every call; no in-memory cache to invalidate post-migration.
- Edits are non-structural (idiom alignment, scope tightening, an extra test row). Skipping a second design review per agentic-workflow rules.

**2026-04-28 — L3 implementation close**

- Spawned Developer (Sonnet, `general-purpose`) for L3. Agent updated leg `ready` → `in-flight`, executed all guidance steps, ran tests, signalled `[HANDOFF:review-needed]`, marked leg `landed`. No commit (per agentic-workflow deferral).
- Test count: 394 → 395 (the new `test_v7_strips_removed_tool_names` adds one). Pre-existing CSS-token red still present (out of scope).
- Developer surfaced an unanticipated coupling: the `CURRENT_VERSION` bump broke `tests/test_schema.py::test_fresh_db_schema_version_is_6` and `::test_idempotent_ensure_schema`, both of which hardcoded `assert row[0] == 6`. Developer repaired inline by (a) importing `CURRENT_VERSION` into the test, (b) replacing the two `6` literals with the symbol, and (c) renaming the first test to `test_fresh_db_schema_version_is_current` for futureproofing. **Flight Director assessment**: this fix was required to preserve the green-build invariant — leaving those tests red would have violated the post-L6 batch-commit promise that the suite stays green at every leg boundary. The repair is mechanical and the rename surfaces the right intent in git blame. Acceptable inline fix; flagged for the post-L6 reviewer to confirm.
- Proceeding to L4.

**2026-04-28 — L4 design + design-review cycle 1**

- Drafted leg artifact `04-ci-and-runtime-teardown.md`. Largest leg by surface area: pipeline trim, docker-compose cleanup, entrypoint minimization, deploy.sh cleanup, Settings shrink, /api/info simplification, /api/selftest probe-path fix, test_db_api fixture update.
- Audit surfaced four out-of-flight-spec edits required for green-build / coherence: (a) tests/test_db_api.py::test_path_values_are_strings update, (b) /api/info `.deploy-status.json` block removal (`workspace_dir` is gone, no writer remains), (c) ci/deploy.sh parallel cleanup, (d) pipeline.yml `CONCOURSE_PASS` parameter drop. Plus a Makefile comment touch-up (in-scope, not a deviation).
- Spawned Developer (Sonnet, `general-purpose`) for design review. Verdict: **approve with changes**. Issues:
  - **Medium**: AC #9 typo "five fields" → "four fields". Fixed.
  - **Medium**: `system-page.js` cosmetic regression in the L4→L5 window — admin Environment view will show empty rows / stale Concourse subsection until L5. Browser tests don't assert on the text. Documented as Edge Case.
  - **Low**: Makefile:6 has stale `/workspace` bind-mount reference. Folded into L4 (natural responsibility — same surface as compose).
  - **Low**: AC entrypoint.sh "is exactly" vs "optional comment is acceptable" was contradictory. Reworded to "at most 5 lines, containing only [shebang/comment/set -e/exec]".
  - **Low**: AC #5 missed `THE_ONE_DEV_MODE=true` in the preserved-vars list. Added.
  - Suggestion accepted: noted /api/selftest path-fix verification deferred to L7 / next deploy run.
  - Suggestion accepted: documented dev_mode asymmetry between docker-compose (dev) and deploy.sh (production).
  - Suggestion accepted: reconciled deviations list — four entries in AC matching step 11.
  - Reviewer confirmed `--network concourse-local_default` removal is safe (default bridge network suffices).
  - Reviewer confirmed `auto-rollback` task continues to work after deploy.sh parameter shrink.
  - Reviewer confirmed `import json as _json` removal is safe (`json` already imported at module level; `_json` was local-only).
  - Reviewer confirmed cache-freshness audit comes back clean: only one `settings.workspace_dir` access site (app.py:525) — already in-scope.
- All edits are clarification/documentation/scope additions; no structural change. Skipping a second design review per agentic-workflow rules.

**2026-04-28 — L4 implementation close**

- Spawned Developer (Sonnet, `general-purpose`) for L4. Agent updated leg `ready` → `in-flight`, executed all guidance steps, ran tests, signalled `[HANDOFF:review-needed]`, marked leg `landed`. No commit.
- Test count unchanged: 395 passed, 1 pre-existing CSS-token red. No regression.
- File-size targets all hit: `pipeline.yml` 286 → 113, `docker-compose.yml` 25 lines, `entrypoint.sh` 4 lines, `deploy.sh` 21 lines.
- All four out-of-flight-spec deviations recorded under `## Deviations`. The L4 → L5 cosmetic regression in `system-page.js` is documented as an acceptable interim incoherence per the leg's Edge Cases.
- Proceeding to L5.

**2026-04-28 — L5 design + design-review cycle 1**

- Drafted leg artifact `05-ui-and-docs-cleanup.md`. Covers studio TOOL_CATEGORIES rewrite, admin/system-page.js rewrite (drop Concourse + workspace_dir, add Base Prompt section), `/api/info` extension, nine `agents.md` edits, six `CLAUDE.md` edits, and `.env.example` cleanup.
- Spawned Developer (Sonnet, `general-purpose`) for design review. Verdict: **needs rework** — high-severity CSS issue. Issues:
  - **High**: recommended `.admin-base-prompt` CSS rule used five non-existent token names. Reviewer verified actual tokens in `tokens.css` and `fonts.css`. Rewrote rule using real tokens (`--surface`, `--border`, `--panel-radius-sm`, `--font-family-mono`, `--font-size-body-sm`, `--fg`) and scoped under `.area-admin` per existing convention.
  - **High**: `.env.example` cleanup was hedged ("audit-as-you-go"). Reviewer verified the 7-line Concourse block at lines 15-21. Made the edit concrete with explicit before/after.
  - **Medium**: `agents.md` line 11 still said "self-modifying LLM agent". Added an edit (now nine `agents.md` edits, was eight).
  - **Medium**: leg dropped `dev_mode` from the System page Server section. Added it back (Server now has `host, port, dev_mode`).
  - **Medium**: `BASE_PROMPT` import in `info()` was local-scoped by analogy with an unrelated codebase pattern. Moved to module-level (cleaner; no circular-import risk).
  - Suggestion accepted: noted explicit `fetchBasePrompt` placement (after `fetchSettings`, before `settingRow`).
  - Suggestion accepted: visual-snapshot tests only screenshot LLM Providers category — no false-fail risk for the new Base Prompt section. Noted in Edge Cases.
  - Reviewer confirmed all `agents.md` and `CLAUDE.md` line numbers cited in the leg are accurate. Confirmed `data-testid="base-prompt-content"` is novel (no existing usage). Confirmed `tests/browser/__snapshots__/` is gitignored.
- All edits applied. The original draft had one high-severity issue (the CSS), now resolved with verified token names. No structural change to the design — adjustments are scope additions and idiom alignment. Skipping a second design review per agentic-workflow rules ("Skip if only minor/cosmetic fixes were applied").
- The CSS-token risk warrants caution: the implementer should grep-verify the rewritten rule's six token references against `tokens.css` and `fonts.css` before adding the rule, not after.

**2026-04-28 — L5 implementation close**

- Spawned Developer (Sonnet, `general-purpose`) for L5. Agent updated leg `ready` → `in-flight`, executed all guidance steps, ran tests, signalled `[HANDOFF:review-needed]`, marked leg `landed`. No commit.
- All six CSS tokens grep-verified before the rule was added. `test_token_definitions.py` reports only the pre-existing `--font-size-h3` red (no new undefined references introduced).
- Test count unchanged: 395 passed, 1 pre-existing CSS-token red. No regression.
- Files touched (per the leg's "Files Affected" list, all in scope): studio.js, system-page.js, admin.css, app.py, agents.md (9 edits), CLAUDE.md (6 edits), .env.example.
- Proceeding to L6 — last autonomous leg before code review and commit.

**2026-04-28 — L6 design + design-review cycle 1**

- Drafted leg artifact `06-test-sweep.md`. Covers: delete two AIAT tests targeting removed tools (`test_git_status`, `test_run_tests`), update two AIAT path probes (`/workspace/...` → `/app/...`), fix `test_health`'s long-broken `"model" in data` assertion to `"base_prompt" in data`, run full default unit + browser suites.
- Spawned Developer (Sonnet, `general-purpose`) for design review. Verdict: **approve with changes**. Issues:
  - **High**: AC step 10 grep would catch `CLAUDE.md:58` (`(tests run from /workspace via subprocess)`) — a stale narrative L5 missed. Added the CLAUDE.md fix to L6 scope as step 6 with a deviation note ("L5 docs-cleanup oversight"). Renumbered subsequent steps.
  - **Medium**: AC step 8 hard-coded "395" was brittle. Tightened to "test count unchanged from the post-L5 baseline" with a capture-and-compare approach.
  - **Medium**: AC step 10 expected-matches narrative undercounted `test_db_migration.py` matches. Rewritten to acknowledge the multiple legitimate matches in `test_preserves_all_fields` + `test_v7_strips_removed_tool_names`.
  - **Medium**: browser suite framing didn't allow for env limitations. Tightened to "if the agentic-workflow environment doesn't support Playwright/Chromium, document and defer to L7 — does NOT block landing".
  - Reviewer confirmed all `test_aiat.py` line numbers still match (file untouched by L1-L5).
  - Reviewer confirmed `info()` never returned `model` field — `test_health` `"model" in data` assertion was broken since the test was added.
  - Reviewer confirmed `the_one/tools/` post-L1 contents include `base.py` and `shell.py` — both valid targets for the updated `test_multi_step` assertion.
  - Reviewer confirmed `tests/browser/__snapshots__/` is gitignored, snapshots are local-only.
- Edits are non-structural (scope addition for the CLAUDE.md fix, AC tightening, narrative cleanup). Skipping a second design review per agentic-workflow rules.

**2026-04-28 — L4 implementation close**

- Spawned Developer (Sonnet, `general-purpose`) for L4. Agent updated leg `ready` → `in-flight`, executed all guidance steps (pipeline trim, docker-compose cleanup, entrypoint minimization, deploy.sh cleanup, Settings shrink, /api/info simplification, /api/selftest probe-path fix, test_db_api fixture update, Makefile comment touch-up), ran the unit suite, signalled `[HANDOFF:review-needed]`, marked leg `landed`. No commit (per agentic-workflow deferral).
- Test suite: 395 passed, 1 pre-existing CSS-token red carried over from L1. No regression. Test count unchanged from L3 (L4 doesn't add or remove tests).
- The wider grep over `system-page.js` correctly surfaces the documented L4→L5 acceptable interim incoherence (admin Environment view will render empty rows / stale Concourse subsection until L5's UI cleanup; browser tests don't assert on the text).
- Proceeding to L5.

---

## Decisions

*Runtime decisions not in original plan will be recorded here as they happen.*

---

## Deviations

**2026-04-28 — L1: Test deletions moved from L6 to L1**

The flight Technical Approach assigned cleanup of `direct_actions`-coupled tests to L6 (test sweep). During L1 design, codebase audit identified that those tests directly exercise infrastructure L1 removes — so leaving them in place after L1's source-side deletion would leave the default `pytest tests/` run red between L1 and L6, violating the "build stays green between legs" guarantee.

Moved into L1:
- **`tests/test_behaviors.py`** — entire file deleted. It imports `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`, `match_direct_action` from `the_one.agent.behaviors`, all of which L1 removes.
- **`tests/test_agent.py::TestDirectAction`** (containing the lone test `test_restart_bypass`) — entire class removed. The test asserted that "restart yourself" matched a direct-action pattern and bypassed the LLM, but L1 removes the direct-action branch from `Agent.step()`.
- **`tests/test_config.py`** — three references to `direct_actions` stripped: assertion of default `True` (was line 24), keyword arg in full-fields constructor (was line 36), and assertion of `False` (was line 46). After L1, `AgentConfig` no longer has the field.
- **`tests/browser/seeders.py:71`** docstring — comment listing optional `AgentConfig` fields no longer includes `direct_actions`. Comment-only change with no behavioral consequence; bundled with the L1 source rip for cohesion.

**Reason:** green-build-between-legs invariant. The agentic-workflow back-to-back commit promise (post-L6) doesn't tolerate intermediate red builds because the operator/Reviewer relies on `pytest tests/` as a regression net at every leg boundary.

**2026-04-28 — L2: Implicit-default `Agent(...)` call sites — flight-spec audit correction**

The flight Technical Approach Decision 4 named two test sites as relying on `Agent.__init__`'s default `system_prompt` value: `tests/test_auto_load.py:99` and `tests/test_streaming.py:268`. A fresh `grep -n "Agent(" tests/` audit during L2 design showed the spec inverted the reading — both of those cited sites already pass explicit prompts (`system_prompt="test"` and `system_prompt="sys"` respectively). They did not rely on the default.

The sites that **actually** relied on the default were six in `tests/test_agent.py` (lines 59, 78, 105, 135, 159, 173 — covering classes `TestNormalFlow`, `TestToolExecution`, `TestContinueSignal`, `TestMaxIterations`, `TestToolError`, `TestReset`). L2 updated those six sites with `system_prompt="test"`, matching the convention already established in `test_auto_load.py:99`.

Verified-untouched (already pass an explicit prompt):
- `tests/test_auto_load.py:99` — `system_prompt="test"`
- `tests/test_streaming.py:268, 282, 300, 468` — `system_prompt="sys"`
- `tests/test_session_lifecycle.py:39` — `system_prompt="You are helpful"`
- `the_one/agent/factory.py:112` (production path — passes `cfg.get_system_prompt()` resolved value)

**Reason:** spec drift. The flight spec was written before L1 deleted the `TestDirectAction` class from `test_agent.py`, which may have shifted Decision 4's mental model of which file held the implicit-default sites. The L2 leg's design captured the corrected list; this deviation entry preserves the audit trail for the post-flight debrief.

**2026-04-28 — L4: Out-of-flight-spec edits required for green-build / coherence**

The flight Technical Approach mentioned trimming `pipeline.yml` and `docker-compose.yml` but did not enumerate four logical-consequence edits that L4's audit identified as required to keep the suite green and the runtime coherent post-cleanup:

- **`tests/test_db_api.py::test_path_values_are_strings` updated** — dropped the two `data["workspace_dir"]` assertions. After dropping `workspace_dir` from `Settings`, the field disappears from the `/api/settings` payload and the test would `KeyError` on `data["workspace_dir"]`. Default-suite test, so the fix has to land with the source change to preserve the green-build-between-legs invariant.
- **`/api/info` `.deploy-status.json` block removal** — dropped the `status_file = settings.workspace_dir / ".deploy-status.json"` block from `the_one/interfaces/web/app.py::info()`. After dropping `workspace_dir` from `Settings`, this line would raise `AttributeError` at runtime. Audit traced the writer: only `tools/self_deploy.py` ever wrote `.deploy-status.json` (deleted in L1); `ci/deploy.sh` does NOT write it. The file is no longer produced, so the read site is dead code and removal is the correct response. Also dropped the local `import json as _json` since it was only used inside the removed block.
- **`ci/deploy.sh` parallel cleanup** — removed the same env vars / mounts / network attachment from `ci/deploy.sh` that were dropped from `docker-compose.yml`, plus dropped the `WORKSPACE_PATH` and `CONCOURSE_PASS` parameter requirements from the script (`WORKSPACE_PATH` was used only for the `/workspace` mount; `CONCOURSE_PASS` was used only for `THE_ONE_CONCOURSE_PASS`). Flight Technical Approach explicitly mentioned trimming docker-compose but didn't mention the parallel deploy.sh cleanup. Logical consequence and required for the deploy pipeline to keep working.
- **`pipeline.yml` `CONCOURSE_PASS` parameter drop** — dropped the `CONCOURSE_PASS: ((concourse-pass))` parameter and the `-e CONCOURSE_PASS="${CONCOURSE_PASS}"` env-var passthrough from both the `build-and-deploy` task and the `auto-rollback` task. Required because `ci/deploy.sh` no longer consumes that env var.

Plus a Makefile comment touch-up (lines 6-7 parenthetical rewritten to drop the `/workspace` bind-mount reference) — folded into L4 during design review since it's the same surface as the compose cleanup. **Not a deviation** (in-scope edit), but mentioned here for traceability with the L4 design-review log.

**Reason:** L4's surface area expanded during audit. The flight spec captured the headline cleanup; the leg artifact captured the logical-consequence edits required to keep the build green and the runtime coherent. All four edits are mechanical/dead-code/parallel-cleanup; the post-L6 reviewer can confirm.

**2026-04-28 — L6: `test_health` shape fix (out of flight spec)**

The flight spec's L6 brief covered AIAT cleanup (delete `test_git_status`/`test_run_tests`, update `/workspace` → `/app` paths) but did not anticipate that `tests/test_aiat.py::test_health`'s `assert "model" in data` line was broken against any `/api/info` shape this codebase has ever shipped. Verified via git blame on the `info()` handler in `the_one/interfaces/web/app.py`: the handler has never returned a `model` field. The assertion is a pre-existing AIAT-only break — invisible because AIAT lives behind `pytest -m live` (off the default suite) and the deploy pipeline's health check uses `/api/selftest`, not `/api/info`.

L6 fixes the assertion (`"model" in data` → `"base_prompt" in data`) as part of the AIAT cleanup so the L7 HAT pass against the fresh-built container doesn't trip on an unrelated stale break. The replacement also provides positive coverage of L5's `/api/info` shape extension (`{"version": "0.1.0", "base_prompt": BASE_PROMPT}`), which previously had only an ad-hoc Python smoke from L5's verification.

**Reason:** stealth bug repair, bundled with the in-spec AIAT edits to keep the post-L7 live-test pass coherent. Strictly out of flight spec; documented here for the post-L6 reviewer's audit trail.

**2026-04-28 — L6: CLAUDE.md:58 `/workspace` reference (L5 docs-cleanup oversight)**

L5's `CLAUDE.md` sweep rewrote `CLAUDE.md:35` (the bind-mount paragraph) to drop the `/workspace` reference, mirroring the L4 Makefile fix. L5 missed a second `/workspace` reference at `CLAUDE.md:58` — the parenthetical "(tests run from `/workspace` via subprocess)" inside the `make rebuild` guidance section. After L4 dropped the `/workspace` bind-mount, this parenthetical was stale.

L6's AC step 10 regression grep surfaced this match (the `/workspace` token in `CLAUDE.md`). Rather than escalate as a regression, L6 inline-fixes it during the test sweep — same surface (docs cleanup) and same fix shape as the L5 work, just at a second site. Replacement: "(the test suite spawns its own uvicorn subprocess, independent of the served daemon)".

**Reason:** docs-cleanup gap from L5 (single overlooked second site). The L6 regression sweep is exactly the right place to catch and patch this — no green-build cost (CLAUDE.md is narrative; default suite doesn't read it), and folding the fix into L6 saves spawning a new leg or carrying the gap into the post-L6 reviewer's queue. Documented here for the post-L6 reviewer's audit trail.

---

## Anomalies

**2026-04-28 — L1: Pre-existing CSS token test failure (not caused by L1)**

`tests/test_token_definitions.py::test_every_var_reference_is_defined` fails with: `Undefined CSS custom properties referenced: --font-size-h3 (referenced in: components.css)`. The offending reference is at `the_one/interfaces/web/static/css/components.css:284` (`.btn-xl { ...; font-size: var(--font-size-h3); ... }`), introduced by commit `18a0cd8` ("flight/06: HAT walkthrough + inline fixes + agents.md absorption (leg 05)"), which predates this flight. L1 modified zero CSS files (verified by `git diff --stat`: only `.py` files in `the_one/` and `tests/` plus the leg artifact / flight log).

The leg artifact's "Inputs" section asserts the suite was green at branch start; the audit on this anomaly contradicts that — the assertion was incorrect, the test was already red on `main`. Surfaced here as an anomaly for the post-L6 reviewer / flight debrief; out of scope for L1 to fix (CSS token sites are not in L1's "Files Affected" list, and adding `--font-size-h3` to `tokens.css` would be a separate concern unrelated to tool-reduction). The remaining 394 unit tests pass; the 18 L1-affected tests (`test_agent.py` + `test_config.py`) pass in isolation.

---

## Session Notes

*Chronological notes from work sessions will be recorded here.*
