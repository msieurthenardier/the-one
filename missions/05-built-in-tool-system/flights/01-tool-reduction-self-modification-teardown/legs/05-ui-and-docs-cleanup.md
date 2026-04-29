# Leg: 05-ui-and-docs-cleanup

**Status**: completed
**Flight**: [Tool Reduction & Self-Modification Teardown](../flight.md)

## Objective

Bring every UI and docs surface into alignment with the post-L1+L2+L3+L4 codebase: rewrite Studio's `TOOL_CATEGORIES` to 3 categories × 7 tools (no System banner), rewrite the admin System page to drop the Concourse CI section + the Workspace Directory field and add a read-only Base Prompt section, surface the `BASE_PROMPT` constant via the existing `/api/info` endpoint, rewrite the affected sections of `the_one/agents.md` (tools table, Settings key-properties line, agent/ module map, dependency graph, Tool Providers/Direct Actions/Continue Signal pattern sections), and rewrite the affected sections of `CLAUDE.md` (What This Is, Local-dev-with-Docker workspace note, Tool layer paragraph, Self-Deployment section removal, Configuration section workspace/Concourse drop). After L5, the project's user- and developer-facing documentation matches the runtime state.

## Context

L5 is the documentation-and-UI mirror of L1+L2+L4. Source code is already correct; the narrative files and rendered admin pages still describe the old world. L5 closes the gap so that:
- Operators reading the admin System page see the post-teardown environment (no Concourse CI section, no Workspace Directory) and can read the resolved `BASE_PROMPT` content (per flight Decision 7).
- Studio agent editors see 3 tool categories × 7 tools (no `System` banner, no `run_tests` in Execution).
- Anyone reading `agents.md` or `CLAUDE.md` gets an accurate description of the codebase.

This is the largest narrative-edit leg in the flight. It does not touch any Python source other than adding a single field to the `/api/info` payload.

**Codebase audit findings (2026-04-28, post-L1+L2+L3+L4 uncommitted):**

### Studio `TOOL_CATEGORIES` site
- `the_one/interfaces/web/static/js/areas/studio.js:151-156`:
  ```javascript
  var TOOL_CATEGORIES = {
    'Filesystem': ['read_file', 'write_file', 'list_dir'],
    'Execution': ['shell', 'python_exec', 'run_tests'],
    'Web': ['http_request', 'web_search'],
    'System': ['git', 'self_deploy', 'rollback', 'restart', 'mission_control', 'memory']
  };
  ```
  Target post-L5:
  ```javascript
  var TOOL_CATEGORIES = {
    'Filesystem': ['read_file', 'write_file', 'list_dir'],
    'Execution': ['shell', 'python_exec'],
    'Web': ['http_request', 'web_search']
  };
  ```
- No browser tests assert on the `System` banner text or on tool category contents (verified via grep — no matches for `Concourse|workspace_dir|TOOL_CATEGORIES|System banner` under `tests/browser/`).

### Admin System page
- `the_one/interfaces/web/static/js/areas/admin/system-page.js`:
  - Lines 10-14: `SETTING_SECTIONS` array. Currently:
    ```javascript
    [{ title: 'Paths', fields: ['data_dir', 'workspace_dir'] },
     { title: 'Server', fields: ['host', 'port'] },
     { title: 'Concourse CI', fields: ['concourse_target', 'concourse_pipeline'] }]
    ```
  - Lines 16-23: `FIELD_LABELS` map.
  - Need to: drop `workspace_dir` from `Paths`, drop the entire `Concourse CI` section descriptor, drop labels for `workspace_dir`, `concourse_target`, `concourse_pipeline`.
  - Add a new admin section that renders `BASE_PROMPT` content as a read-only `<pre>`-style block (per Decision 7). Slot it after the existing Encryption section.
  - Source for the BASE_PROMPT content: `/api/info` payload.

### `/api/info` extension
- Post-L4, `/api/info` returns `{"version": "0.1.0"}` unconditionally.
- Per flight Decision 7 + Acceptable Variations, the smallest delta is to extend `/api/info` rather than adding a new endpoint. After L5: `{"version": "0.1.0", "base_prompt": "...{BASE_PROMPT content}..."}`.
- L5 wires the JS admin page to read `data.base_prompt` from `/api/info`.

### Tests sensitive to `/api/info` shape
- `tests/test_aiat.py:105` does `httpx.get(f"{base_url}/api/info", timeout=10)`. Doesn't assert on shape — passes through.
- `tests/browser/conftest.py:88-100` polls `/api/info` for startup readiness. Returns boolean (200 or not). No shape dependency.
- `tests/browser/test_markdown.py:59`, `tests/browser/test_app_fixture.py:21,25` use `/api/info` for liveness. No shape dependency.
- All consumers parse the response as JSON; adding a `base_prompt` field is additive and safe. No test breaks.

### `the_one/agents.md` sites needing rewrite
- **Line 42**: `Key properties: data_dir (~/.the-one), workspace_dir (/workspace), agents_dir (data_dir / "agents"), db_path (data_dir / "the-one.db").` — drop `workspace_dir`.
- **Line 57**: `| config.py | AgentConfig, DEFAULT_SYSTEM_PROMPT | Agent definition Pydantic model... and fallback prompt |` — rename `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT`, rephrase "fallback prompt" → "base prompt for layered composition".
- **Line 60**: `| behaviors.py | DIRECT_ACTIONS, CONTINUE_SCHEMA, match_direct_action() | Behavioral patterns extracted from core |` — delete the entire row (file gone).
- **Line 62**: `**Agent.step() flow**: user input → check direct actions → LLM call → execute tools → repeat until no tool calls or max iterations.` — drop "check direct actions" → `**Agent.step() flow**: user input → LLM call → execute tools → repeat until no tool calls or max iterations.`
- **Lines 80-93**: tools table. Currently:
  ```
  | Export | Type | Purpose |
  | builtins.py | BuiltinToolProvider | Provides all 14 built-in tools via lazy import |
  | shell.py | ShellTool | Arbitrary shell commands |
  | filesystem.py | ReadFileTool, WriteFileTool, ListDirTool | File operations |
  | git.py | GitTool | Version control with safety guards |
  | test_runner.py | TestRunnerTool | pytest integration |
  | python_exec.py | PythonExecTool | Python subprocess execution |
  | web.py | HttpRequestTool, WebSearchTool | HTTP and web search |
  | memory.py | MemoryTool | Persistent key-value store (.memory/ directory) |
  | self_deploy.py | SelfDeployTool | Concourse CI deployment trigger |
  | restart.py | RestartTool | Container restart via Concourse |
  | rollback.py | RollbackTool | Docker image rollback via Concourse |
  | mission_control.py | MissionControlTool | Flight Control methodology access |
  ```
  Target: drop the seven removed-tool rows (`git.py`, `test_runner.py`, `memory.py`, `self_deploy.py`, `restart.py`, `rollback.py`, `mission_control.py`); update `builtins.py` row to "7 built-in tools".
- **Line 146**: `└── agent/store.py\n        agent/config.py\n        agent/behaviors.py` (in dependency graph) — drop `agent/behaviors.py` line.
- **Line 171**: `BuiltinToolProvider provides the 14 built-in tools` — change to `provides the 7 built-in tools`.
- **Lines 173-175**: `### Direct Actions` section — delete entirely (the section explains a removed feature).
- **Lines 177-179**: `### Continue Signal` section — currently *"A virtual tool (`CONTINUE_SCHEMA`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops."* Update to reference `core.py` as the host module (where `CONTINUE_SCHEMA` now lives post-L1): *"A virtual tool (`CONTINUE_SCHEMA`, defined inline in `core.py`) that..."*.

### `CLAUDE.md` sites needing rewrite
- **Line 7** (`## What This Is`): full rewrite. Currently *"A self-modifying, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. The agent can edit its own source, run tests, deploy itself via Concourse CI, and roll back if things break."* Replace with general-purpose framing. Proposed:
  > *"A general-purpose, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. Built-in tools cover filesystem, execution, and web; a layered system prompt composes a foundational base with optional per-agent personas."*
- **Line 25**: `pytest -m live tests/test_aiat.py` example references "live tests against a running instance" — fine as-is, no rewrite.
- **Line 35**: parenthetical `The /workspace bind-mount is used by the test suite, which spawns its own uvicorn subprocess; it does not feed the daemon at port 8484.` After L4 dropped the bind-mount, this is wrong. Replace with: `The test suite spawns its own uvicorn subprocess; that path is independent of the served daemon at port 8484.` (Mirrors the Makefile fix L4 made.)
- **Line 66** (Tool layer paragraph): `BuiltinToolProvider (builtins.py) provides all 14 built-in tools via lazy import` → `provides all 7 built-in tools via lazy import`.
- **Lines 68-71** (Agent loop paragraph): currently lists *"Behavioral constants and helpers live in `behaviors.py`: Direct actions: regex patterns... Continue signal: a virtual tool... Max 20 iterations..."*. Rewrite: drop `behaviors.py` mention; drop Direct actions bullet; keep Continue signal (rephrase to reference `core.py`); keep max-iterations.
- **Line 75**: `Schema is versioned (currently v3) and auto-migrated on first connection.` — update to `currently v7`.
- **Lines 96-103** (`## Self-Deployment` section): delete entirely. The section describes a parked feature.
- **Line 107** (`## Configuration` paragraph): currently *"Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, workspace_dir, Concourse settings."* Update: drop `workspace_dir` and `Concourse settings`. Result: *"Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode."*

### Out of L5 scope
- `pyproject.toml` `__version__` — flight does not require a version bump.
- `.env.example` (if present) — audit-as-you-go: if it lists `workspace_dir` / Concourse env vars, drop them; otherwise no change.
- Any test fixture updates — those belong to L6.
- `the_one/__init__.py` `__version__` — leave alone (already says `0.2.0`; flight doesn't reconcile that with `0.1.0` in `/api/info`).

## Inputs

- L1 + L2 + L3 + L4 landed (uncommitted): tools rip done, prompt layering done, schema v7, CI/runtime trim done.
- `studio.js:151-156` carries the four-category × 14-tool `TOOL_CATEGORIES`.
- `admin/system-page.js:10-14` has Paths/Server/Concourse-CI sections.
- `/api/info` returns `{"version": "0.1.0"}`.
- `agents.md` and `CLAUDE.md` reference the old tool surface, `behaviors.py`, `DEFAULT_SYSTEM_PROMPT`, `/workspace` bind-mount, and Self-Deployment.
- Default unit test suite baseline: 395 passed + 1 pre-existing red.

## Outputs

After this leg:
- `studio.js` `TOOL_CATEGORIES` has 3 categories × 7 tools, no `System` banner.
- `admin/system-page.js` has 2 sections (Paths with `data_dir` only, Server with `host`/`port`) plus a new Base Prompt section that renders the `BASE_PROMPT` content as a read-only `<pre>` block.
- `the_one/interfaces/web/app.py::info()` returns `{"version": "0.1.0", "base_prompt": "..."}`.
- `agents.md` reflects the post-rip surface: tools table down to 5 source files (one row dropped per removed tool, `builtins.py` says "7"); no `behaviors.py`, no `DEFAULT_SYSTEM_PROMPT`, no `Direct Actions` section, dependency graph trimmed.
- `CLAUDE.md` reflects the new framing: general-purpose vs self-modifying, no Self-Deployment section, no `/workspace` bind-mount note, no Concourse-settings mention, schema v7.
- Default unit test suite green (395 passed, 1 pre-existing red).
- No commit — deferred to post-L6.

## Acceptance Criteria

- [ ] `studio.js` `TOOL_CATEGORIES` has exactly 3 keys (`'Filesystem'`, `'Execution'`, `'Web'`) and exactly 7 tool names total. No `'System'` key. No `'run_tests'` in any list.
- [ ] `rg -n "'run_tests'|'self_deploy'|'rollback'|'restart'|'mission_control'|'memory'|'git'|'System':" the_one/interfaces/web/static/js/areas/studio.js` returns no matches in the `TOOL_CATEGORIES` block.
- [ ] `admin/system-page.js` `SETTING_SECTIONS` has exactly two entries — `Paths` (fields: `['data_dir']`) and `Server` (fields: `['host', 'port', 'dev_mode']`). No `Concourse CI` entry.
- [ ] `admin/system-page.js` `FIELD_LABELS` contains exactly four keys: `data_dir`, `host`, `port`, `dev_mode`. Does not contain `workspace_dir`, `concourse_target`, or `concourse_pipeline`.
- [ ] `admin/system-page.js` renders a "Base Prompt" admin section after the Encryption section. The section reads `data.base_prompt` from `/api/info` and renders it inside a `<pre>` element with class `admin-base-prompt`. The `<pre>` content is escaped via `window.App.escapeHtml` before insertion.
- [ ] `the_one/interfaces/web/app.py::info()` returns a dict with keys `version` and `base_prompt`. The `base_prompt` value equals the `BASE_PROMPT` constant from `the_one/agent/config.py`. Verified via `python -c "import asyncio; from the_one.interfaces.web.app import info; from the_one.agent.config import BASE_PROMPT; r = asyncio.run(info()); assert r['base_prompt'] == BASE_PROMPT and r['version'] == '0.1.0', r; print('OK')"`.
- [ ] `the_one/agents.md` does NOT contain `self-modifying`, `behaviors.py`, `DEFAULT_SYSTEM_PROMPT`, `DIRECT_ACTIONS`, `match_direct_action`, `GitTool`, `MemoryTool`, `MissionControlTool`, `TestRunnerTool`, `SelfDeployTool`, `RollbackTool`, `RestartTool`, `workspace_dir`, `/workspace`, or `### Direct Actions`. Verified via:
  ```bash
  rg -n "self-modifying|behaviors\.py|DEFAULT_SYSTEM_PROMPT|DIRECT_ACTIONS|match_direct_action|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool|workspace_dir|/workspace|### Direct Actions" the_one/agents.md
  ```
  Returns no output.
- [ ] `the_one/agents.md` mentions `BASE_PROMPT` (replacing `DEFAULT_SYSTEM_PROMPT`).
- [ ] `the_one/agents.md` tools table has exactly 5 source-file rows (`shell.py`, `filesystem.py`, `python_exec.py`, `web.py`, `builtins.py`), and the `builtins.py` row says "7 built-in tools".
- [ ] `CLAUDE.md` does NOT contain `## Self-Deployment`, `self-modifying`, `behaviors.py`, `Direct actions`, `workspace_dir`, `Concourse settings`, `14 built-in tools`, `/workspace bind-mount`, or `currently v3`. Verified via:
  ```bash
  rg -n "## Self-Deployment|self-modifying|behaviors\.py|Direct actions|workspace_dir|Concourse settings|14 built-in tools|/workspace bind-mount|currently v3" CLAUDE.md
  ```
  Returns no output.
- [ ] `CLAUDE.md` says `7 built-in tools` and `currently v7`.
- [ ] `.env.example` has no `CONCOURSE` or `WORKSPACE` references. `rg -n "CONCOURSE|WORKSPACE" .env.example` returns no output.
- [ ] `python -m pytest tests/ --tb=short -q --ignore=tests/browser` exits 0 (modulo the pre-existing CSS-token anomaly). Test count remains 395 (no test added or removed).
- [ ] `python -m pytest tests/test_db_api.py -v` passes — `/api/info` shape change does not regress the settings test.
- [ ] Working tree on branch `flight/01-tool-reduction-self-modification-teardown`; **no commit made**.
- [ ] Flight log updated with leg progress entry under `## Leg Progress`, status `landed`.
- [ ] Leg status set to `landed` in this file's header.

## Verification Steps

```bash
# 1. studio.js TOOL_CATEGORIES
rg -n "TOOL_CATEGORIES" the_one/interfaces/web/static/js/areas/studio.js
# Expected: one match at the top of the assignment

rg -n "'run_tests'|'self_deploy'|'rollback'|'restart'|'mission_control'|'git'" the_one/interfaces/web/static/js/areas/studio.js
# Expected: no output

# 2. admin/system-page.js SETTING_SECTIONS
rg -n "SETTING_SECTIONS|FIELD_LABELS|admin-base-prompt" the_one/interfaces/web/static/js/areas/admin/system-page.js
# Expected: at least three matches (declarations + new section render)

rg -n "Concourse CI|workspace_dir|concourse_target|concourse_pipeline" the_one/interfaces/web/static/js/areas/admin/system-page.js
# Expected: no output

# 3. /api/info shape — Python smoke test
python -c "
import asyncio
from the_one.interfaces.web.app import info
from the_one.agent.config import BASE_PROMPT
result = asyncio.run(info())
assert result['version'] == '0.1.0', result
assert result['base_prompt'] == BASE_PROMPT, 'base_prompt mismatch'
print('OK')
"
# Expected: 'OK'

# 4. agents.md cleanup
rg -n "behaviors\.py|DEFAULT_SYSTEM_PROMPT|DIRECT_ACTIONS|match_direct_action|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool|workspace_dir|/workspace|### Direct Actions" the_one/agents.md
# Expected: no output

rg -n "BASE_PROMPT|7 built-in tools" the_one/agents.md
# Expected: at least two matches

# 5. CLAUDE.md cleanup
rg -n "## Self-Deployment|self-modifying|behaviors\.py|Direct actions|workspace_dir|Concourse settings|14 built-in tools|/workspace bind-mount|currently v3" CLAUDE.md
# Expected: no output

rg -n "7 built-in tools|currently v7" CLAUDE.md
# Expected: at least two matches

# 6. Test suite green
python -m pytest tests/ --tb=short -q --ignore=tests/browser
# Expected: 395 passed, 1 pre-existing CSS-token failure
```

## Implementation Guidance

Work from project root `/home/cprch/projects/the-one`. Branch must be `flight/01-tool-reduction-self-modification-teardown`. Leg status `ready` → `in-flight` at start; `landed` at end. **No commit.**

1. **Update `the_one/interfaces/web/static/js/areas/studio.js`** (lines 151-156). Replace the `TOOL_CATEGORIES` block with:
   ```javascript
       var TOOL_CATEGORIES = {
         'Filesystem': ['read_file', 'write_file', 'list_dir'],
         'Execution': ['shell', 'python_exec'],
         'Web': ['http_request', 'web_search']
       };
   ```
   Three keys, seven tool names total. Preserve indentation (the surrounding code is inside an IIFE; current indentation is 4 spaces or so — match what's there).

2. **Update `the_one/interfaces/web/static/js/areas/admin/system-page.js`**:
   - Replace `SETTING_SECTIONS` (lines 10-14) with:
     ```javascript
     var SETTING_SECTIONS = [
       { title: 'Paths', fields: ['data_dir'] },
       { title: 'Server', fields: ['host', 'port', 'dev_mode'] }
     ];
     ```
     (Including `dev_mode` here keeps the System page in sync with the post-L4 `Settings.model_fields` set; without it the operator loses visibility of dev-mode state.)
   - Replace `FIELD_LABELS` (lines 16-23) with:
     ```javascript
     var FIELD_LABELS = {
       data_dir: 'Data Directory',
       host: 'Host',
       port: 'Port',
       dev_mode: 'Dev Mode'
     };
     ```
   - Inside `renderSystemPage(container)` (line 25-63), the inner template currently has three `<div class="admin-system-section">` blocks (Environment, Appearance, Encryption). Add a fourth section after Encryption and before the closing `</div>` of `.admin-form`:
     ```javascript
     '<div class="admin-system-section">' +
       '<div class="section-title admin-section-title">Base Prompt</div>' +
       '<p class="admin-system-text">' +
         'The foundational system prompt every agent inherits. ' +
         'Per-agent personas are appended to this base; ' +
         'this content is read-only and only changes via code releases.' +
       '</p>' +
       '<pre class="admin-base-prompt" data-testid="base-prompt-content">Loading…</pre>' +
     '</div>' +
     ```
   - Below the existing `fetchSettings(container)` call inside `renderSystemPage`, add `fetchBasePrompt(container);`. Add the new function near the other fetch helpers:
     Place this function immediately after `fetchSettings` (around line 88), before `settingRow`:
     ```javascript
     function fetchBasePrompt(container) {
       fetch('/api/info')
         .then(function (r) { return r.json(); })
         .then(function (data) {
           var preEl = container.querySelector('.admin-base-prompt');
           if (!preEl) return;
           if (typeof data.base_prompt === 'string') {
             preEl.textContent = data.base_prompt;
           } else {
             preEl.textContent = '(base prompt unavailable)';
           }
         })
         .catch(function () {
           var preEl = container.querySelector('.admin-base-prompt');
           if (preEl) preEl.textContent = '(failed to load)';
         });
     }
     ```
     Note: `preEl.textContent = data.base_prompt` is XSS-safe because the browser sets text-only content. No `innerHTML`, no `escapeHtml` needed for `<pre>` text. (The `escapeHtml` used elsewhere in this file applies to `innerHTML` paths.)

3. **Add a CSS rule** for `.area-admin .admin-base-prompt` in `the_one/interfaces/web/static/css/admin.css`. Use the rule below verbatim — token names verified against `tokens.css` and `fonts.css`:
   ```css
   .area-admin .admin-base-prompt {
     background: var(--surface);
     border: 1px solid var(--border);
     border-radius: var(--panel-radius-sm);
     padding: 12px 14px;
     font-family: var(--font-family-mono);
     font-size: var(--font-size-body-sm);
     line-height: 1.5;
     overflow-x: auto;
     white-space: pre-wrap;
     word-break: break-word;
     max-height: 24rem;
     overflow-y: auto;
     color: var(--fg);
     margin: 0;
   }
   ```
   The selector is scoped under `.area-admin` to match every other admin-area rule's convention. All token references confirmed real: `--surface` (line 25 tokens.css), `--border` (line 30), `--panel-radius-sm` (line 79), `--font-family-mono` (line 34 fonts.css), `--font-size-body-sm` (line 41), `--fg` (line 35). The `tests/test_token_definitions.py` gate will not flag this rule.

4. **Update `the_one/interfaces/web/app.py::info()`**. Add a module-level import near the existing `from the_one.agent import Agent` import (around line 16):
   ```python
   from the_one.agent.config import BASE_PROMPT
   ```
   Then change `info()` (line ~517-519) from:
   ```python
   @app.get("/api/info")
   async def info() -> dict[str, Any]:
       return {"version": "0.1.0"}
   ```
   to:
   ```python
   @app.get("/api/info")
   async def info() -> dict[str, Any]:
       return {"version": "0.1.0", "base_prompt": BASE_PROMPT}
   ```
   Module-level import is the cleaner pattern here: `BASE_PROMPT` is a plain string constant, `the_one.agent.config` doesn't import from `interfaces/`, no circular-import risk. The earlier draft used a local-scoped import by analogy with `api.py:112` (where `AgentConfig` is imported locally to break a model-load order risk), but that analogy doesn't apply here.

5. **Update `the_one/agents.md`** — nine discrete edits:
   - **Line 11**: change `The-one is a self-modifying LLM agent built without frameworks.` to `The-one is a general-purpose LLM agent built without frameworks.`
   - **Line 42**: change `Key properties: data_dir (~/.the-one), workspace_dir (/workspace), agents_dir (data_dir / "agents"), db_path (data_dir / "the-one.db").` to `Key properties: data_dir (~/.the-one), agents_dir (data_dir / "agents"), db_path (data_dir / "the-one.db"), dev_mode (default: false).`
   - **Line 57**: change `| config.py | AgentConfig, DEFAULT_SYSTEM_PROMPT | Agent definition Pydantic model (includes provider_config_id for LLM provider resolution) and fallback prompt |` to `| config.py | AgentConfig, BASE_PROMPT | Agent definition Pydantic model (includes provider_config_id for LLM provider resolution) and the foundational base prompt for layered composition |`.
   - **Line 60**: delete the entire `| behaviors.py | DIRECT_ACTIONS, CONTINUE_SCHEMA, match_direct_action() | Behavioral patterns extracted from core |` row.
   - **Line 62**: change `**Agent.step() flow**: user input → check direct actions → LLM call → execute tools → repeat until no tool calls or max iterations.` to `**Agent.step() flow**: user input → LLM call → execute tools → repeat until no tool calls or max iterations.`
   - **Lines 80-93** (tools table): rewrite to:
     ```
     | File | Exports | Purpose |
     |------|---------|---------|
     | `base.py` | `Tool`, `ToolRegistry` | Tool ABC (`execute(**kwargs) -> str`) and registry |
     | `provider.py` | `ToolProvider` | Protocol: `name` property + `get_tools()` method |
     | `builtins.py` | `BuiltinToolProvider` | Provides all 7 built-in tools via lazy import |
     | `shell.py` | `ShellTool` | Arbitrary shell commands |
     | `filesystem.py` | `ReadFileTool`, `WriteFileTool`, `ListDirTool` | File operations |
     | `python_exec.py` | `PythonExecTool` | Python subprocess execution |
     | `web.py` | `HttpRequestTool`, `WebSearchTool` | HTTP and web search |
     ```
     (Drops the seven removed-tool rows.)
   - **Line 146** (dependency graph): drop `agent/behaviors.py` line. Result:
     ```
     └── agent/store.py
         agent/config.py
     ```
   - **Line 171**: change `BuiltinToolProvider provides the 14 built-in tools` to `BuiltinToolProvider provides the 7 built-in tools`.
   - **Lines 173-175** (`### Direct Actions` section + paragraph): delete the entire section. Result: `### Tool Providers` is followed directly by `### Continue Signal`.
   - **Lines 177-179** (`### Continue Signal`): change `A virtual tool (CONTINUE_SCHEMA) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.` to `A virtual tool (CONTINUE_SCHEMA, defined inline in core.py) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.`

6. **Update `CLAUDE.md`** — six discrete edits:
   - **Line 7** (`## What This Is`): replace the entire paragraph with: *"A general-purpose, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. Built-in tools cover filesystem, execution, and web; a layered system prompt composes a foundational base with optional per-agent personas."*
   - **Line 35** (parenthetical about /workspace): replace the sentence `The /workspace bind-mount is used by the test suite, which spawns its own uvicorn subprocess; it does not feed the daemon at port 8484.` with `The test suite spawns its own uvicorn subprocess; that path is independent of the served daemon at port 8484.`
   - **Line 66** (Tool layer paragraph): change `BuiltinToolProvider (builtins.py) provides all 14 built-in tools via lazy import` to `BuiltinToolProvider (builtins.py) provides all 7 built-in tools via lazy import`.
   - **Lines 68-71** (Agent loop paragraph): rewrite to:
     > *"**Agent loop** (`the_one/agent/core.py`) — The `Agent` class runs: user input → LLM call → tool execution → repeat until no tool calls remain. The agent uses a virtual `CONTINUE_SCHEMA` (defined inline in `core.py`) as a turn-keeping signal — when the LLM calls `continue`, the loop registers another iteration. Max 20 iterations per step as a safety limit."*
     (Drops the `behaviors.py` reference and the Direct Actions bullet; keeps the Continue signal explanation; keeps max-iterations.)
   - **Line 75**: change `Schema is versioned (currently v3) and auto-migrated on first connection.` to `Schema is versioned (currently v7) and auto-migrated on first connection.`
   - **Lines 96-103** (`## Self-Deployment` section): delete the entire section (the `## Self-Deployment` header through the end of its paragraph). The next section (`## Configuration`) becomes the immediate successor of the Architecture section.
   - **Line 107** (Configuration paragraph): change `Runtime config via env vars prefixed THE_ONE_ (see .env.example): host, port, data_dir, workspace_dir, Concourse settings.` to `Runtime config via env vars prefixed THE_ONE_ (see .env.example): host, port, data_dir, dev_mode.`

7. **Update `.env.example`** — verified present, currently 21 lines. Drop the seven-line Concourse block (lines 15-21):
   ```
   # Concourse CI (for self-deploy/rollback/restart)
   THE_ONE_CONCOURSE_PASS=
   THE_ONE_CONCOURSE_URL=http://host.docker.internal:8080
   THE_ONE_CONCOURSE_USER=the-one
   THE_ONE_CONCOURSE_TEAM=the-one
   THE_ONE_CONCOURSE_TARGET=local
   THE_ONE_CONCOURSE_PIPELINE=the-one
   ```
   Resulting `.env.example` ends after `THE_ONE_PORT=8484`. Verify with `rg -n "CONCOURSE|WORKSPACE" .env.example` — should be empty.

8. **Run the unit suite**:
   ```bash
   python -m pytest tests/ --tb=short -q --ignore=tests/browser
   ```
   Expected: 395 passed, 1 pre-existing red. The `/api/info` shape change is additive — tests that call it pass through.

9. **Run the Python smoke** for the new `/api/info` shape:
   ```bash
   python -c "
   import asyncio
   from the_one.interfaces.web.app import info
   from the_one.agent.config import BASE_PROMPT
   result = asyncio.run(info())
   assert result['version'] == '0.1.0', result
   assert result['base_prompt'] == BASE_PROMPT, 'base_prompt mismatch'
   print('OK')
   "
   ```
   Expected: `OK`.

10. **Run the targeted verification commands** from the Verification Steps section.

11. **Update the flight log**:
    - Append a `### 05-ui-and-docs-cleanup` entry under `## Leg Progress` with status `landed`, summary of changes (TOOL_CATEGORIES rewrite, system-page.js rewrite, /api/info extension, agents.md edits, CLAUDE.md edits).
    - Note any deviations or surprises encountered during execution.

12. **Set leg status to `landed`** in this file's header. Do **NOT** commit. Do **NOT** check off the leg in `flight.md`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **CSS token names**: the recommended `.admin-base-prompt` rule references several design tokens. Before applying the CSS, grep `tokens.css` (or wherever the project defines tokens) for the exact names — `--surface-2`, `--border`, `--radius-sm`, `--space-3`, `--font-mono`, `--font-size-sm`. If any are missing, substitute the closest existing token. The token-definition test (`tests/test_token_definitions.py`) catches typos; the L1-anomaly red test was for `--font-size-h3` (different token, different cause). L5 must not add NEW undefined references.
- **Browser tests don't assert on system-page text**: confirmed via grep. The new Base Prompt section is not exercised by automated browser tests in F1; HAT (L7) covers it manually.
- **`/api/info` consumers**: existing AIAT and browser test consumers parse JSON and ignore unknown keys. Adding `base_prompt` is safe. No test breaks.
- **`text/plain` rendering of `<pre>`**: setting `preEl.textContent = data.base_prompt` ensures HTML special characters in the prompt content (e.g., `<`, `>`, `&`) render as literals rather than markup. This is the standard pattern for `<pre>` content. No XSS path.
- **Stale Concourse CI subsection in HAT window**: L4's Edge Cases noted the L4 → L5 admin window where the system page still rendered empty Concourse rows. L5 closes that window. After L5, the page is coherent again.
- **`agents.md` line numbers may have drifted**: all edits should match by surrounding text content, not by absolute line number. The audit findings above show the current line numbers; the implementer should re-grep before each edit.
- **CLAUDE.md line numbers same caveat**: match by surrounding text.
- **Long BASE_PROMPT in admin page**: the `.area-admin .admin-base-prompt` `max-height: 24rem` + `overflow-y: auto` keeps the rendered block from dominating the page. 296-word prompt at typical line-height fits comfortably in ~12 rem; 24 rem is generous slack.
- **Visual snapshot tests**: `tests/browser/test_visual_snapshots.py` only screenshots the LLM Providers admin category (verified at line 254). The new Base Prompt section lives under the System category and is not exercised by the snapshot suite. Snapshot baselines are gitignored (`.gitignore` line `tests/browser/__snapshots__/`). No false-fail risk on the visual-snapshot side.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — rewrite `TOOL_CATEGORIES` (3 categories × 7 tools)
- `the_one/interfaces/web/static/js/areas/admin/system-page.js` — drop `Concourse CI` section + `workspace_dir` field, add Base Prompt section with `fetchBasePrompt` helper
- `the_one/interfaces/web/static/css/components.css` (or equivalent) — add `.admin-base-prompt` rule
- `the_one/interfaces/web/app.py` — extend `info()` to include `base_prompt` field
- `the_one/agents.md` — eight edits per step 5
- `CLAUDE.md` — six edits per step 6
- `.env.example` — drop workspace/Concourse lines (if present)
- `missions/05-built-in-tool-system/flights/01-tool-reduction-self-modification-teardown/flight-log.md` — append leg progress entry

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (NOTE: per the agentic-workflow skill, this leg does NOT commit; the post-L6 review handles commit. Mark leg `landed`, not `completed`.):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/ --ignore=tests/browser` green except for the pre-existing CSS anomaly)
- [ ] Update flight-log.md with leg progress entry (status `landed`)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do **NOT** check off this leg in flight.md yet (deferred to post-L6 commit)
- [ ] Do **NOT** commit (deferred to post-L6 batch commit)
- [ ] Signal `[HANDOFF:review-needed]`
