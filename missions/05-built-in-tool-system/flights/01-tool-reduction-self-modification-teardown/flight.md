# Flight: Tool Reduction & Self-Modification Teardown

**Status**: completed
**Mission**: [Built-In Tool System](../../mission.md)

## Contributing to Criteria

- [ ] The agent's built-in tool surface is focused on filesystem, execution, and web; deployment, methodology-awareness, persistent-memory, and version-control tools are removed without breaking the agent runtime, the chat experience, or any M01-M04 capability
- [ ] The default system prompt reflects a general-purpose personal-assistant identity, free of self-modification, deployment, and methodology-reader instructions
- [ ] The autopilot scheduling surface is removed cleanly along with its supporting CI plumbing
- [ ] Existing agent configurations referencing removed tools load cleanly and continue functioning — stale tool names in `enabled_tools`/`disabled_tools` are silently stripped via schema migration with no operator-visible breakage

---

## Pre-Flight

### Objective

Rip the self-modification surface out of the-one in one coordinated pass. Seven tools delete (`self_deploy`, `rollback`, `restart`, `run_tests`, `git`, `memory`, `mission_control`); five Concourse jobs and the heartbeat resource come out of the pipeline; the runtime stops mounting `/workspace`, stops cloning mission-control, stops installing the fly CLI, stops carrying the `THE_ONE_CONCOURSE_*` env vars and config settings. The bundled `DEFAULT_SYSTEM_PROMPT` is replaced with a layered model — a foundational **base prompt** that establishes identity / tone / turn semantics / tool-use disposition, with per-agent prompts now composing additively on top rather than replacing the base. The base prompt is surfaced read-only in System Settings for operator visibility. A v7 schema migration silently strips the seven removed tool names from existing `enabled_tools`/`disabled_tools` JSON so stale agent configs load cleanly. The Studio Tools tab and admin System page lose their Concourse / system-tool surfaces. A test sweep removes obsolete coverage and verifies the full suite stays green. The deploy pipeline's `test` and `deploy` jobs remain so the project's CI/CD path is preserved — only the agent-facing self-management surface is torn out.

### Open Questions

- [x] **`CONTINUE_SCHEMA` (the virtual `continue` tool) fate** → Keep it (resolved: see Design Decisions / Decision 1)
- [x] **`behaviors.py` / `DIRECT_ACTIONS` / `AgentConfig.direct_actions` fate** → Rip them all (resolved: see Decision 2)
- [x] **`/workspace` mount fate** → Rip in F1, clean break (resolved: see Decision 3)
- [x] **Prompt layering vocabulary and composition** → Layered model with **base prompt** + **agent prompt** + **tool descriptions** + (future) **runtime context** + **user prompt**; agent prompts compose additively on top of base, no escape hatch (resolved: see Decision 4)
- [x] **Tool guidance — its own layer or part of base?** → Part of base (resolved: see Decision 4)
- [x] **Who drafts the new base prompt** → Flight Director drafts; user reviews & redlines in L2 (resolved: see Decision 4)
- [x] **Migration verification approach** → Update existing fixture in `test_db_migration.py` + add a new `test_v7_strips_removed_tool_names` (resolved: see Decision 5)
- [x] **HAT leg yes/no** → Yes (resolved: see Decision 6)
- [x] **Base prompt visible in admin** → Yes, read-only section in System page (resolved: see Decision 7)
- [x] **`BASE_PROMPT` vs `DEFAULT_SYSTEM_PROMPT` constant name** → Rename to `BASE_PROMPT` for symmetry with the layer vocabulary (resolved: see Decision 4)

### Design Decisions

**Decision 1 — Keep `CONTINUE_SCHEMA`**: The virtual `continue` tool stays. The agent uses it to signal "I have more work to do, give me another turn." This is independent of the self-modification narrative — it's general-purpose turn control. The mission-text reference to "reconcile stale `continue` references" was a misread; the only reconciliation needed is making sure the new base prompt mentions it correctly. **Move target**: when `behaviors.py` is deleted (per Decision 2), `CONTINUE_SCHEMA` moves inline into `core.py` (its only consumer) rather than landing in a new placeholder file.
- Rationale: `continue` is genuinely useful for multi-step tool-using turns. Removing it would make every multi-step task a separate user-prompted iteration. Inlining keeps the constant next to its only consumer; no new file overhead.
- Trade-off: One more thing the new base prompt has to explain to small models. Acceptable.

**Decision 2 — Rip `behaviors.py`, `DIRECT_ACTIONS`, and `AgentConfig.direct_actions`**: With `restart` and `rollback` patterns gone, `DIRECT_ACTIONS` is empty. Inline `match_direct_action` logic is no longer needed since there are no patterns to match. Delete the file, drop the field from `AgentConfig`, remove the import from `core.py`. The `core.py` direct-action call site becomes dead code and is removed.
- Rationale: Empty seams accumulate as cargo. Direct actions can come back as a small new file when a real pattern justifies it; until then, the maintenance cost is unjustified.
- Trade-off: Slightly more work later if direct actions return. Easy to re-create.

**Decision 3 — Rip the `/workspace` bind mount in F1**: Remove `.:/workspace` from `docker-compose.yml`, drop `THE_ONE_WORKSPACE_DIR=/workspace`, drop `workspace_dir` from `config.py` and any callers. Path-allowlist design in F3 will independently decide what the default scope is — F1 doesn't need to take a position by leaving the mount as latent state.
- Rationale: The mount only made sense as the editable target for the self-modification loop. Without that loop, it's a confusing artifact that suggests semantics we've removed. Clean break.
- Trade-off: If F3's path-allowlist work decides it wants a workspace-style mount, it'll be re-added with explicit semantics. That's better than carrying it forward with implicit ones.

**Decision 4 — Establish prompt layering with additive composition**: Today, `DEFAULT_SYSTEM_PROMPT` is monolithic and `AgentConfig.system_prompt` (when non-empty) fully replaces it. F1 establishes a layered model:

| Layer | Scope | Where it lives |
|-------|-------|----------------|
| **Base prompt** | Foundational — identity, tone, turn semantics (`continue`), tool-use disposition, light tool guidance. Same for every agent | Code constant (renamed or kept as `DEFAULT_SYSTEM_PROMPT` per L2 decision) |
| **Agent prompt** | Per-agent persona | `AgentConfig.system_prompt` (per-row in DB) |
| **Tool descriptions** | Per-tool: what it does, when to use it | Each `Tool.description` (already isolated) |
| **Runtime context** *(future)* | Date, environment, agent name, available tools — injected at step time | Not in F1 scope |
| **User prompt** | Per-turn user message | Conversation message |

Composition rule: when `AgentConfig.system_prompt` is non-empty, it's **appended** to the base prompt with a separator (e.g., `\n\n---\n\n`); when empty, base prompt alone applies. No escape hatch / replace mode — single composition rule keeps semantics simple. Tool guidance lives inside the base prompt rather than being its own layer; if tool overlap creates ambiguity later, a dynamic tool-guidance layer can be added.

**Two read sites, not one** (correction to original spec): `AgentConfig.get_system_prompt()` is the production composition site invoked from `AgentFactory.create()` (`factory.py:109`). But `Agent.__init__` at `core.py:18` *also* takes `system_prompt: str = DEFAULT_SYSTEM_PROMPT` as a default parameter — bypassing `get_system_prompt()` when callers construct an `Agent` directly. Two test files do this: `tests/test_auto_load.py:99` and `tests/test_streaming.py:268`. L2 strategy: drop the default value from `Agent.__init__`'s signature (require callers to pass a resolved prompt) and update those two test sites. This makes `AgentConfig.get_system_prompt()` the genuinely-single resolution path.

- Rationale: Layering is what the user wants; additive-only is the simplest rule that gets there. "Nobody is using this yet" (per mission decision D4 sign-off) means no migration risk for existing per-agent prompts. Eliminating the `Agent.__init__` default closes the gap that would otherwise let a caller silently bypass layering.
- Trade-off: An agent author can't suppress base behavior. If that ever blocks something, the override mode can be added later. Two test files need a small edit to pass an explicit prompt.

**Constant naming resolved**: rename `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT` for symmetry with the new layer vocabulary. `agents.md:57` references the old name and gets updated as part of L5's docs sweep.

The Flight Director drafts the new base prompt content (~200-400 words) in L2; the user reviews and redlines.

**Decision 5 — Schema v7 verification**: New test `test_v7_strips_removed_tool_names` seeds v6-shaped rows with stale tool names (`["self_deploy", "git", "memory", "shell"]`) in both `enabled_tools` and `disabled_tools`, runs `ensure_schema()` to v7, and asserts the stale names are gone while legitimate ones (`shell`) survive. Existing `test_preserves_all_fields` fixture in `test_db_migration.py` is updated to use only legitimate tool names so it doesn't accidentally pass through v7 unchanged.
- Rationale: Two-part coverage — the new test proves the strip works; the fixture update prevents the migration test suite from having a no-op-when-strip-runs case it can't distinguish from a no-op-when-strip-doesn't-run case.
- Trade-off: Two test edits instead of one. Cheap.

**Decision 6 — Include HAT leg as L7**: F1 changes the agent's voice (new base prompt) and removes capabilities. A short HAT pass — chat against the new prompt with a real LLM — verifies the agent feels right and can still do basic tasks (read a file, run a shell command, search the web) before mission-debrief.
- Rationale: Prompt-rewrite-by-LLM has a track record of feeling slightly off in subtle ways that automated tests don't catch.
- Trade-off: 30-60 minutes of human time. Worth it.

**Decision 7 — Base prompt visible read-only in System Settings**: Add a new section to the admin System page showing the resolved base prompt content as a read-only block. No editing — operators see what's baked in but can't change it without code changes. Slots in alongside the Encryption / Appearance / Environment sections; the Concourse CI section being removed leaves natural space for it.
- Rationale: Operator visibility into the agent's foundational behavior. Right now the only way to know what the agent's base prompt says is to read the source. Making it visible in the UI improves transparency.
- Trade-off: One more admin section; trivial UI work given M04 components canon.

### Prerequisites

- [x] M05 mission spec signed off (status `active`)
- [x] M04 closeout: not blocking — F1 doesn't touch UI surfaces M04 didn't already settle, and the mission-debrief / routine-maintenance for M04 can run in parallel with F1 execution
- [x] Current schema version is v6 (verified: `schema.py:7 CURRENT_VERSION = 6`)
- [x] AgentConfig prompt-composition sites located: `agent/config.py:get_system_prompt()` (production path via `AgentFactory.create()` at `factory.py:109`) AND `agent/core.py:18` `Agent.__init__` default parameter (bypass path used by `tests/test_auto_load.py:99` and `tests/test_streaming.py:268`). L2 closes the bypass
- [x] Concourse pipeline jobs inventoried: `autopilot`, `pause-autopilot`, `unpause-autopilot`, `rollback`, `restart`, `deploy`, plus `heartbeat` time resource (5 jobs to remove + 1 resource to remove; `deploy` stays)
- [x] Studio TOOL_CATEGORIES site located: `studio.js:151-156`
- [x] Admin System page Concourse CI site located: `admin/system-page.js:13,21,22`
- [x] `mission-control` clone path in `entrypoint.sh` confirmed as the only consumer of that clone (no other code reads from `/mission-control`)
- [x] Operator confirms the base prompt draft (first-pass content review happens in L2)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [ ] Legs defined → see Legs section below

---

## In-Flight

### Technical Approach

The flight is a coordinated teardown across six surfaces (Python source, default prompt, schema, CI/runtime, web UI/docs, tests) plus a mandatory HAT pass, executed in dependency order so each leg lands a coherent reduction without leaving the build broken between legs.

**Order rationale:**

1. **Tools first** — Deleting the seven tool files and updating `builtins.py` is the foundational change everything else acknowledges. Once the tools are gone, downstream surfaces (prompt, UI, tests, CI) can refer to a stable post-rip state.
2. **Prompt rewrite second** — Establishes the new layering and the new base content. This is a content change; nothing else depends on it being done first beyond the obvious user-visible-correctness ordering.
3. **Schema migration third** — Independent of the tool/prompt changes; lives entirely in `db/schema.py` + tests. Done early so it's available before any leg touches the agent runtime in a way that might hit a stale config.
4. **CI/runtime teardown fourth** — Pipeline file, docker-compose, entrypoint, config settings. None of this is referenced by Python tool code anymore (post-L1), so it's a safe sweep.
5. **UI/docs cleanup fifth** — Studio TOOL_CATEGORIES, admin Concourse CI section removal + base-prompt visibility section addition, agents.md table, CLAUDE.md narrative. All UI work.
6. **Test sweep sixth** — Removes obsolete tests, verifies full suite green. Last because it confirms the cumulative effect of the previous five legs.
7. **HAT seventh** — Real-LLM chat against the new agent feel. Mandatory because the prompt rewrite changes voice in ways that automated tests cannot detect, and the test sweep in L6 leaves no other gate that exercises the live agent.

**Inter-leg coherence between L1 and L2:** L1 deletes the seven tools but doesn't touch `DEFAULT_SYSTEM_PROMPT`, which still describes them. Between L1's commit and L2's commit, the agent's system prompt is incoherent — it claims tools that no longer exist. Tests don't exercise this (no test asserts on prompt content), so the build stays green, but operator-visible HAT behavior in this window would be confusing. **Mitigation**: L1 and L2 commit back-to-back with no separate verification or review pause. The flight log should record a single "L1+L2 batch landed" note rather than treating them as independently observable releases.

**Composition contract for the prompt layer (L2 deliverable):**

```python
# AgentConfig.get_system_prompt() — new behavior
def get_system_prompt(self) -> str:
    if self.system_prompt:
        return f"{BASE_PROMPT}\n\n---\n\n{self.system_prompt}"
    return BASE_PROMPT
```

`BASE_PROMPT` is the renamed (or kept) constant. Single composition rule. No mode flag.

**Schema v7 migration (L3 deliverable):**

Inline migration in `ensure_schema()` matching the v3/v5/v6 pattern. Pseudocode:

```python
if version < 7:
    REMOVED = {"self_deploy", "rollback", "restart", "run_tests",
               "git", "memory", "mission_control"}
    cursor = await conn.execute(
        "SELECT name, enabled_tools, disabled_tools FROM agents"
    )
    rows = await cursor.fetchall()
    for name, enabled_json, disabled_json in rows:
        enabled = json.loads(enabled_json) if enabled_json else None
        disabled = json.loads(disabled_json or "[]")
        new_enabled = (
            [t for t in enabled if t not in REMOVED]
            if enabled is not None else None
        )
        new_disabled = [t for t in disabled if t not in REMOVED]
        await conn.execute(
            "UPDATE agents SET enabled_tools = ?, disabled_tools = ? WHERE name = ?",
            (json.dumps(new_enabled) if new_enabled is not None else None,
             json.dumps(new_disabled), name),
        )
    await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (7,))
    await conn.commit()
```

`CURRENT_VERSION` bumps from 6 to 7.

**Concourse pipeline trim (L4 deliverable):**

Resulting `pipeline.yml` keeps:
- No `resources:` section (heartbeat was the only resource)
- One job: `deploy` (with its existing `on_failure` auto-rollback — that's deploy-internal recovery, not the standalone `rollback` job)

Lines preserved verbatim: deploy plan steps (test / build-and-deploy / health-check) and the on_failure block. Lines removed: lines 1-79 (`resources:` + `autopilot` job) and lines 199-285 (`rollback`, `pause-autopilot`, `unpause-autopilot`, `restart` jobs).

**Runtime teardown (L4 deliverable):**

- `docker-compose.yml`: drop `.:/workspace` volume mount, drop `THE_ONE_WORKSPACE_DIR`, drop `THE_ONE_CONCOURSE_*` env vars (5 vars), drop `concourse` external network and the `extra_hosts` entry that exposed the host to the container. The `the_one_data` volume + port 8484 + Ollama-host extra-host stay.
- `scripts/entrypoint.sh`: drop the `git config --add safe.directory /mission-control` line, drop the mission-control clone block, drop the fly CLI download block, drop the fly login block. Keep the `git config --add safe.directory /workspace` only if `/workspace` is still mounted — since it isn't (per Decision 3), this line goes too. The script becomes minimal: `set -e` + `exec "$@"`. Consider whether to delete the file entirely; defer to L4 design.
- `the_one/config.py`: remove `concourse_target` and `concourse_pipeline` fields from `Settings`; remove `workspace_dir` field. Settings file shrinks to web/host/port + dev_mode + data_dir.
- `Dockerfile`: `git` apt package may still be wanted as a general-purpose binary available in the container (keeps `shell` invocations of `git` working if the operator wants ad-hoc git-via-shell). Keep for now; revisit when F2 hardens the platform layer.
- `the_one/interfaces/web/app.py`: `/api/selftest` (line 535) currently invokes the agent against `Read the file /workspace/pyproject.toml` (line 561). With `/workspace` unmounted, that probe fails and the deploy pipeline's health-check job auto-rolls-back every deploy. **Fix in L4**: change the probe to a path that exists in the running container — `/app/pyproject.toml` (baked into the image) or `/app/the_one/__init__.py`. Pick the smaller change in L4 design.

**UI cleanup (L5 deliverable):**

- `studio.js:151-156`: `TOOL_CATEGORIES` becomes `{ 'Filesystem': ['read_file', 'write_file', 'list_dir'], 'Execution': ['shell', 'python_exec'], 'Web': ['http_request', 'web_search'] }`. Three categories, seven tools.
- `admin/system-page.js`: drop the `Concourse CI` section descriptor at line 13 and its labels at lines 21-22. Add a new `Base Prompt` section descriptor that renders the `BASE_PROMPT` constant as a read-only `<pre>`-style block. Where the constant value comes from: a new `GET /api/info/base-prompt` endpoint (or extend the existing `/api/info` payload) that returns the constant string. Pick the simpler of the two in L5 design.
- `agents.md` lines 80-93: rewrite the tools table to drop the seven removed entries; the count comment in `builtins.py` (`14 built-in tools`) becomes `7 built-in tools`.
- `CLAUDE.md`: drop the entire `## Self-Deployment` section (lines ~96-103), drop Concourse mentions in `## Configuration`, drop Concourse and self-modification language from `## What This Is`. Update the `pytest -m live` example to drop the `run_tests`-related description.

**Test sweep (L6 deliverable):**

Remove:
- `tests/test_aiat.py::test_git_status` (lines 135-149)
- `tests/test_aiat.py::test_run_tests` (lines 162-172)
- `tests/test_agent.py::test_restart_bypass` (lines 93-103)
- `tests/test_behaviors.py` — entire file (all tests target removed direct-actions)

Update:
- `tests/test_db_migration.py:85` — `disabled_tools=["self_deploy"]` becomes `disabled_tools=["shell"]` (a tool that survives) so the `test_preserves_all_fields` doesn't accidentally exercise v7-strip logic. New `test_v7_strips_removed_tool_names` covers that path explicitly.
- `tests/test_aiat.py::test_tool_use_file_read` (line ~126) — currently prompts the agent to read `/workspace/pyproject.toml`. With `/workspace` unmounted, this probe targets a missing path. Update the prompt to a path that exists in the running container — same target chosen by the L4 selftest fix (e.g., `/app/pyproject.toml`). Keep the assertion semantics unchanged.
- `tests/test_auto_load.py:99` and `tests/test_streaming.py:268` — currently call `Agent(..., system_prompt="...")` directly, relying on the `Agent.__init__` default. After L2 drops the default parameter, these tests must pass an explicit `system_prompt` argument. Both already pass one — the test sites just need to confirm they no longer rely on default fallback (low risk, mechanical verification).

Verify:
- `python -m pytest tests/ --tb=short -q` green
- `pytest -m browser tests/browser/ --tb=short -q` green (M04 baseline preserved)
- `pytest -m live tests/test_aiat.py` green against a running instance (smoke for HAT)

### Checkpoints

- [x] **Tools-rip clean** — 7 tool source files deleted, `builtins.py` updated to 7 tools, `behaviors.py` deleted, `core.py` no longer imports from `behaviors`, `AgentConfig.direct_actions` field gone, full test suite green for the *remaining* tests
- [x] **Prompt-layer landed** — `BASE_PROMPT` constant in place with new content, `get_system_prompt` uses additive composition, base prompt content reviewed and approved by user
- [x] **Schema v7 applied** — `CURRENT_VERSION = 7`, migration in `ensure_schema()`, both new test and updated fixture green
- [x] **CI/runtime trimmed** — `pipeline.yml` has only `deploy` job, `docker-compose.yml` has no Concourse env vars / no workspace mount / no concourse network, `entrypoint.sh` minimized, `config.py` no longer carries Concourse or workspace settings
- [x] **UI/docs aligned** — `TOOL_CATEGORIES` shows 3 categories with 7 tools, admin System page has no Concourse CI section and has a read-only Base Prompt section, `agents.md` and `CLAUDE.md` reflect the post-rip state
- [x] **Test suite clean** — obsolete tests removed, full suite green (unit + browser + AIAT smoke)
- [x] **HAT pass (L7)** — operator and agent walk through a short interactive session against the new base prompt; agent reads a file, runs a shell command, performs a web search; prompt feel approved

### Adaptation Criteria

**Divert if**:
- The schema v7 migration fails on a real DB fixture in a way that suggests the strip logic mishandles `null` `enabled_tools` (whitelist-mode rows). Stop, redesign the migration to handle the `None` case explicitly, re-test
- The new base prompt content review (L2) reveals the layering model itself doesn't fit the user's mental model. Stop the leg, return to mission-level design discussion before proceeding
- Removing `behaviors.py` surfaces unexpected callers outside `core.py` and the test files inventoried (defensive search planned in L1, but if surprises emerge, pause)
- The `/api/selftest` path-fix (L4) doesn't survive a `make rebuild` + deploy-cycle smoke test — auto-rollback fires. Investigate before considering L4 landed; the deploy pipeline's auto-rollback is the M01-M04 capability F1 cannot regress

*Confirmed safe (no divert needed):* the `concourse` external Docker network is owned by the `concourse-local` sibling project at `~/projects/concourse-local`. The-one is only an attached client. Dropping the `external: true` reference from the-one's compose file does not affect the concourse-local stack.

**Acceptable variations**:
- Whether `entrypoint.sh` becomes minimal-`exec-"$@"` or is deleted entirely (Dockerfile would then change `ENTRYPOINT` accordingly) — pick the simpler outcome in L4 design
- Whether the base prompt is exposed via `GET /api/info/base-prompt` or as a field in the existing `/api/info` payload — pick the smaller delta in L5 design
- Whether `test_behaviors.py` is deleted as a file or kept as an empty placeholder for future direct-action tests — delete (consistent with Decision 2)
- The exact path chosen as the new selftest/AIAT probe target (`/app/pyproject.toml` vs `/app/the_one/__init__.py` vs another) — pick whichever results in the simpler assertion in L4 design and reuse the same path in L6 update of `test_tool_use_file_read`

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-rip-tools-and-behaviors` — Delete the 7 tool source files, update `builtins.py` (drop imports + entries, update `14 built-in tools` → `7 built-in tools` count comment), delete `behaviors.py`, move `CONTINUE_SCHEMA` constant inline into `core.py` (its only consumer), drop `AgentConfig.direct_actions` field, remove `core.py`'s direct-action call site (dead code post-`behaviors.py` deletion). Verify no remaining references to deleted symbols.

- [x] `02-prompt-layering-and-base-rewrite` — Establish additive composition in `AgentConfig.get_system_prompt()`. Drop the `system_prompt` default value from `Agent.__init__` (`core.py:18`) so callers must pass an explicit prompt, closing the bypass path; update the two call sites (`tests/test_auto_load.py:99`, `tests/test_streaming.py:268`) to confirm they pass explicit prompts (mechanical). Rewrite the foundational prompt content (~200-400 words covering identity, tone, turn semantics including `continue`, tool-use disposition, light generic tool guidance) — Flight Director drafts; user reviews and redlines before commit. Apply constant rename `DEFAULT_SYSTEM_PROMPT` → `BASE_PROMPT` across all callers. **Commit back-to-back with L1** (per Technical Approach inter-leg coherence note).

- [x] `03-schema-v7-tool-name-strip` — Bump `CURRENT_VERSION` to 7, add the `if version < 7:` block to `ensure_schema()` implementing the strip migration (handle `enabled_tools=NULL` whitelist case explicitly; preserve any indexes; match v3/v5/v6 style). Add `tests/test_db_migration.py::test_v7_strips_removed_tool_names`. Update existing fixture in `test_preserves_all_fields` to use only surviving tool names.

- [x] `04-ci-and-runtime-teardown` — Trim `ci/pipeline.yml` to one `deploy` job (remove autopilot/pause-autopilot/unpause-autopilot/rollback/restart jobs + heartbeat resource). Update `docker-compose.yml` (drop `/workspace` mount, drop `THE_ONE_CONCOURSE_*` env vars, drop concourse network, drop `THE_ONE_WORKSPACE_DIR`). Update `scripts/entrypoint.sh` (drop fly install, drop fly login, drop mission-control clone, drop both `safe.directory` lines; minimize to `exec "$@"` or delete file). Update `the_one/config.py` (drop `concourse_target`, `concourse_pipeline`, `workspace_dir` fields). **Update `/api/selftest` in `the_one/interfaces/web/app.py:561`** — change the tool-use probe path from `/workspace/pyproject.toml` to `/app/pyproject.toml` (or equivalent baked-in path) so the deploy pipeline's health check survives the workspace-mount removal.

- [x] `05-ui-and-docs-cleanup` — Update `studio.js` `TOOL_CATEGORIES` to 3 categories × 7 tools (drop System banner, drop `run_tests` from Execution). Update `admin/system-page.js` to drop Concourse CI section and add a read-only Base Prompt section showing the `BASE_PROMPT` constant. Add the API endpoint or `/api/info` field that surfaces the base-prompt constant. Rewrite `agents.md` tools table (lines 80-93) and update its `DEFAULT_SYSTEM_PROMPT` reference to `BASE_PROMPT`. Update `CLAUDE.md` (drop Self-Deployment section, drop Concourse mentions in Configuration, update What This Is, update tool list).

- [x] `06-test-sweep` — Delete obsolete tests (`test_aiat.py::test_git_status`, `test_aiat.py::test_run_tests`, `test_agent.py::test_restart_bypass`, entire `test_behaviors.py`). Update `test_aiat.py::test_tool_use_file_read` (line ~126) to read a path that survives the workspace-mount removal — same path chosen for the L4 selftest fix. Run full unit suite (`pytest tests/`), browser suite (`pytest -m browser tests/browser/`) — both must be green. Run AIAT smoke (`pytest -m live tests/test_aiat.py`) against a fresh `make rebuild` and confirm the surviving live tests pass.

- [x] `07-hat-prompt-feel` — Guided HAT session: operator chats with the agent against the new base prompt. **Probes**: (a) ask the agent "list your tools" — none of the seven removed names should appear (no ghost-tool hallucination); (b) verify identity / voice feels right; (c) read a file with `read_file`, run a shell command with `shell`, search the web with `web_search` — all should succeed; (d) verify admin System page shows the Base Prompt section read-only; (e) verify Studio Tools tab shows 3 categories × 7 tools. Inline-fix any voice or copy issues that surface; divert any structural ones to a follow-up. **L7 is mandatory** — F1 cannot land without it.

---

## Post-Flight

### Completion Checklist

- [ ] All legs landed (L1-L7 all mandatory)
- [ ] No references to `self_deploy`, `rollback`, `restart`, `run_tests`, `git` (tool), `memory` (tool), `mission_control` (tool), `behaviors.py`, `direct_actions`, `concourse_target`, `concourse_pipeline`, `workspace_dir` remain in the codebase (verified by grep)
- [ ] `ci/pipeline.yml` contains only the `deploy` job
- [ ] `docker-compose.yml` no longer mounts `/workspace` or carries `THE_ONE_CONCOURSE_*` env vars
- [ ] `the_one/config.py::Settings` no longer has Concourse or workspace fields
- [ ] `agents.md` tools table reflects 7 remaining tools
- [ ] `CLAUDE.md` no longer references self-modification, autopilot, fly CLI, or `/mission-control`
- [ ] Schema is v7; migration tested on a v6 fixture with stale tool names
- [ ] Full unit test suite green
- [ ] Browser test suite green (M04 baseline preserved — no regressions in chat / studio / admin)
- [ ] AIAT smoke green for surviving tests (`test_health`, `test_basic_chat`, `test_tool_use_file_read`, `test_reset`, `test_self_awareness`, `test_multi_step`)
- [ ] Base prompt visible read-only in admin System page
- [ ] Studio Tools tab shows 3 categories × 7 tools (no System banner)
- [ ] Code committed; flight log updated; flight status set to `landed`

### Verification

**Static (grep / read):**

```bash
# Should return nothing
rg -n "self_deploy|rollback|restart|run_tests|GitTool|MemoryTool|MissionControlTool|TestRunnerTool|SelfDeployTool|RollbackTool|RestartTool" the_one/ tests/ ci/ scripts/ docker-compose.yml

# Should return nothing
rg -n "concourse_target|concourse_pipeline|workspace_dir|THE_ONE_CONCOURSE|/workspace" the_one/ docker-compose.yml scripts/

# Should return nothing
rg -n "from the_one.agent.behaviors|behaviors\.py|DIRECT_ACTIONS|direct_actions" the_one/ tests/

# Should show 7 tools, 3 categories
rg -n "TOOL_CATEGORIES" the_one/interfaces/web/static/js/areas/studio.js
```

**Dynamic (test suite):**

```bash
make rebuild               # full rebuild against new code
make test                  # all default tests must pass
make test-browser          # browser tests must pass
pytest -m live tests/test_aiat.py  # surviving AIAT tests must pass
```

**Manual (HAT, L7):**

- Open the chat area, start a conversation with the default agent
- Verify the agent's response style matches the new base prompt voice
- Verify the agent does not reference `self_deploy`, `rollback`, `run_tests`, `git`, `memory`, `mission_control` when listing its capabilities
- Read a file with `read_file`, run a shell command with `shell`, search the web with `web_search` — all should succeed
- Open admin System page, verify Concourse CI section is gone and Base Prompt section is visible (read-only)
- Open Studio agent editor → Tools tab, verify 3 categories × 7 tools, no System banner
