# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. It is the always-loaded operational manual: commands, safety rules and test entry points. Detail lives in the docs it points to; do not grow this file with per-feature paragraphs (squawk 0397).

## What This Is

A general-purpose, LLM-powered personal agent. No agent frameworks: the agent loop, tool registry, LLM abstraction and message protocol are hand-rolled. Built-in tools cover filesystem, execution and web; a layered system prompt composes a foundational base with optional per-agent personas.

**Codebase reference**: `the_one/agents.md` is the canonical deep reference (architecture internals, module map, tool-authorship contract, MCP contracts, project conventions, design system, every feature's contract). Consult it when working on internals. Threat model: `SECURITY-MODEL.md`. Prompt evals: `evals/README.md`. CI topology: `ci/README.md`. Connectors: `the_one/connectors/README.md`. UI control catalogue: `docs/ui-control-inventory.md`; test ids: `docs/ui-testid-registry.md`.

## Commands

```bash
# Install (editable, with all optional deps)
pip install -e ".[all-llms,dev]"

# Run CLI
the-one chat

# Run web server (port 8484)
the-one serve

# Diagnose the runtime spawn seam (esp. inside a frozen/packaged build):
# spawns a probe child, resolves the external Python interpreter, detects
# node/uv/python on PATH. Prints PASS/FAIL; exits non-zero on failure.
the-one doctor

# Quit the running desktop app (window, tray or hidden; reads the credential
# read-only and never creates one; --wait also waits for the process to exit,
# default on in a terminal)
the-one quit

# Tests
python -m pytest tests/ --tb=short -q
python -m pytest tests/test_example.py -q          # single file
python -m pytest tests/test_example.py::test_name   # single test
pytest -m live tests/test_aiat.py                   # AIAT (needs running instance; see Testing)
pytest -m browser tests/browser/                    # Browser tests: use run-tests.sh, see Testing

# Lint & format
ruff check the_one/ tests/ scripts/ evals/
ruff format the_one/ tests/ scripts/ evals/
```

**Lint/format gate.** Run `pre-commit install` once to activate the pre-commit hook (`pipx install pre-commit` first if needed; it is also in the `[dev]` extra). CI runs the same `ruff check the_one/ tests/ scripts/ evals/` and `ruff format --check the_one/ tests/ scripts/ evals/` on every push to `main` (Concourse, `ci/tasks/lint.yml`; the GitHub Actions workflows are `workflow_dispatch`-only break-glass fallbacks; see `ci/README.md`).

## Local dev (host-native)

The app runs host-native via `the-one serve` (no `--reload`). `make up` starts it backgrounded against the repo venv (writes `.the-one.$(THE_ONE_PORT).pid` and `.log`, gitignored; a dev instance on another port keeps its own files, so `THE_ONE_PORT=8486 THE_ONE_DATA_DIR=<scratch> make down` is safe against the default instance). The test suite spawns its own uvicorn subprocess, independent of `make up`.

```bash
make up                     # start host-native in the background (PID + log) + verify
make restart                # restart to pick up source edits + verify
make down                   # stop (by PID)
make logs                   # tail the host log
make reset-db CONFIRM=1     # wipe the host data dir + restart (gated: data loss)
make test                   # default tests (unit tier under pyproject addopts)
make test-unit              # unit tests only
make test-browser           # all browser lanes, 3 at a time (run-tests.sh --parallel 3)
make gate                   # full local gate: test-unit, then test-browser (never concurrent)
make lint                   # ruff check
make format                 # ruff format
make verify-serving         # curl-check that admin sub-modules return 200
make eval ARGS="..."        # prompt evals (see Prompt evals)
make help                   # list all targets
```

**`make restart` is required** for any Python change under `the_one/` (no live reload; a Pydantic class-definition edit such as `AgentConfig` needs a fresh process too) and for `static/index.html` in production (it is lru-cached; in dev mode `THE_ONE_DEV_MODE=true` it is rebuilt per request). **It is not required** for JS and CSS under `the_one/interfaces/web/static/` (served from disk per request) or for `tests/`. If a JS/CSS edit appears not to have landed, suspect the browser cache (production asset refs are `?v={__version__}`; dev mode uses a content hash), not the server: hard-reload or `curl` the asset with the credential. A restart will not fix it.

## Architecture (orientation)

Four layers compose bottom-up: **Interfaces** (CLI + Web/FastAPI) -> **Agent** (loop, factory, config, persistence) -> **Tools / LLM** (tool registry + provider abstraction) -> **Config / Persistence** (pydantic-settings + SQLite + Fernet-encrypted credentials). Runtime config is `THE_ONE_*` env vars (`the_one/config.py`, `.env.example`); LLM providers are configured through the database (`/api/providers`), not env vars. Dev mode (`THE_ONE_DEV_MODE=true`) adds the `mock` provider type (deterministic scripted replies; options in the `MockProvider` docstring, `the_one/llm/mock.py`).

**Contracts every change must respect** (detail in `the_one/agents.md`):

- **`__MASKED__`**: the provider edit form sends the literal `__MASKED__` for an unchanged API key; `update_provider` (`interfaces/web/api.py`) preserves the stored value. See "`__MASKED__` sentinel (LLM providers)".
- **Agent PUT preserves credentials**: `update_agent` resolves incoming `mcp_overrides` against the stored row per credential key (omitted or masked keeps, `null` clears); `tool_overrides` is preserved when omitted, and a new or changed override is validated on save (422 on its `loc`). See "Agent override secrets storage", "Agent override validation and clipping (sortie 07)", "Per-agent MCP credentials (sortie 09)".
- **Naming rule**: agent, provider, knowledge-base and MCP-server names go through `the_one/naming.py::check_name` at the API write boundary (never on pydantic models); `default` and `GleepGlorp` are reserved agent names; a new name-setting route must call it (`tests/test_api_name_rule.py` classifies every POST/PUT route). See "Naming rule (sortie 06)".
- **Secrets, self-configuration, routines**: Library secrets (`{{secret:key}}` placeholders, Fernet-encrypted, granted per agent), the per-agent self-configuration surface and routines are operator-owned surfaces with approval modes; see "Secrets (sortie 10)", "Self-configuration surface contract", "Routines (M33)" and `SECURITY-MODEL.md`.
- **GleepGlorp (M36)**: the built-in assistant is not an agent (no `agents` row); settings, chats, read tools, memory, guide, prompt, proposals, drawer, page awareness and fills: see "GleepGlorp (M36)" and the sections after it. Its prompt and its tools' descriptions are platform prompt text (see Prompt evals).
- **Knowledge bases (M24)**, **LLM layer** (Claude plan providers, extended thinking, prompt caching), **MCP client on the `mcp` 2.x SDK**, **desktop launcher and packaging** (Windows, Linux, macOS), **release workflow**, **boxed execution, PTY and the frozen-runtime seam**, **time zones and `current_time`**, **tool exposure for small models**: see "Knowledge storage", "Knowledge retrieval", "Anthropic prompt caching (sortie 14)", "Claude Plan providers: OAuth and Token (sortie 03)", "MCP F2 Client Foundation", "MCP error translation", "Desktop launcher", "Frozen-runtime seam (M15 F5)", "Windows packaging (M32 F4)" (also the M15 F5 spec location), "Linux packaging (M32 F2)", "macOS packaging (M32 F3)", "Release workflow (M32 F4)", "Windows PTY backend (M15 F3)", "Time zones (M28)", "current_time and the date layer (M28)", "Tool exposure (sortie 11)". The release version lives only in `the_one/__init__.py`; never dispatch a standalone platform packaging workflow while a release is running.
- **Browser UI**: destination router and leave guard (`App.router`, `App.nav`), app shell, client store (`App.store`), control library (`App.ui`), Chats list/pane/composer/transcript, agent drawer, Jump to, Settings and Library pages, focus-after: see "Hash routing — the router", "App shell — invariants", "Client data store (`App.store`)", "Control library (`App.ui`)", "Chats list and agent picker", "Chats pane", "Chat composer", "Agent drawer", "Jump-to palette", "Settings nav and pages", "Library list and detail", "Agents list and detail", "Focus after an in-place action". New UI controls are factories in `static/js/ui/`; each needs a row in `docs/ui-control-inventory.md` and contract tests (`tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py` enforce it; no HTML-string sinks, no retired-API calls outside `js/ui/`).
- **Charts and widgets**: `docs/chart-format.md` and `docs/widget-format.md` are the specs; a new chart rule lands in the document, the corpus `tests/fixtures/charts/` and both implementations together. See "Charts in chat", "Widgets in chat", "Native bridge removal and the widget crash record" and `SECURITY-MODEL.md` "Live visuals".

## Safety rules (these prevent harm; do not relax them)

- **Never target the operator's production instance.** Never use port 8484 or 8485 (8485 is the Flight Director's preview instance) or the operator's default data directory, for tests, behavior tests, probes, captures or evals. Use a dedicated dev instance: a non-default port (8486 or higher; scratch tools refuse below 8490) AND a scratch data directory under `$HOME` (not `/tmp`). Full recipe: "Behavior-test credential convention" below. Tools that enforce it: `scripts/ui_capture.py`, `scripts/webkitgtk_probe.py`, `scripts/windows_test_copy.py`, `evals/`.
- **Print, never guess, the default data directory**: `python -c "from the_one.config import settings; print(settings.data_dir)"` (platformdirs-derived, not a literal path).
- **Eval plan token**: `~/.config/the-one-evals/plan-token` (override `--plan-token-file`). Never print it, log it or commit it.
- **Credentials and secrets**: never print the API credential or any token; never commit `.env`, `*.env.hat` or credential files.
- **Shell-write rule**: source, tests, docs, scripts, missions, evals, sorties, squawks and the root docs (`CLAUDE.md`, `SECURITY-MODEL.md`, `README.md`) are edited only with the Edit/Write tools, never `sed -i`, redirects or heredocs; `.claude/hooks/block_shell_writes.py` enforces it (`tests/test_shell_write_hook.py`).
- **Test snapshots are not committed** (user-global rule): visual snapshot baselines and golden files are gitignored (`tests/browser/__snapshots__/`); do not design legs that depend on committed baselines as the regression net. The recorded exception is `evals/baselines/*.json`.
- **Local-API credential gate**: every route except `GET /api/live` requires a credential (`SECURITY-MODEL.md` "Authentication"). A stray 401 in a new test or a manual `curl` almost always means a missing credential, not a regression. Fixtures attach one (`tests/_credential_helpers.py::auth_headers()`, `tests/browser/_credential_registry.py::auth_headers_for()`); in an ad-hoc call read `<data_dir>/api-credential` (verbatim, one line) or mint one with `the-one rotate-api-credential`.
- **Origin allowlist**: default `http://127.0.0.1:*` and `http://localhost:*`; `THE_ONE_ORIGIN_ALLOWLIST` extends it (`SECURITY-MODEL.md`).
- **Test seams** (`/api/_test/*`) need `THE_ONE_DEV_MODE=true` and their own flag (`THE_ONE_STUB_TEST_ENDPOINT`, `THE_ONE_DISCORD_TEST_ENDPOINT`, `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT`, `THE_ONE_OAUTH_TEST_ENDPOINT`; `THE_ONE_FAKE_PLATFORMS_URL` is an env seam); disposable instances only, never on a real one. Details, the HAT env and `tests/behavior/.env.hat.example`: "Dev mode seams and HAT env".

## Prompt evals (Mission 30)

`evals/` is a hand-rolled developer tool (nothing under `the_one/` imports it): it runs scenarios through the real agent factory, prompt assembly and loop in a scratch data directory and home, against Claude Haiku 4.5 and local models, and reports pass rates and the platform text's size by part. Run it with `make eval ARGS="<subcommand> ..."` (`run`, `measure-prompt`, `report`, `baseline`, `derive-bars`, `compare`, `cache-probe`); usage, scenario format, checks, statistics and gate rules are in `evals/README.md`. It makes real model calls and burns plan quota (local only, never CI; approve quota first), refuses to overlap the real or configured data directory, never touches port 8484 and disables the execution tools.

**Rule: a change to platform prompt text lands with an eval run compared against its baseline, including its token cost** (`make eval ARGS="measure-prompt"`, then `compare --baseline ...`). Platform prompt text is: `the_one/agent/platform_prompt.py` (including its Rich visuals section), the rules, notes and secrets layers (`the_one/db/_rules.py`, `_notes.py`, `_secrets.py`), the date-line templates in `the_one/time_zones.py`, the starting tool descriptions and, since sortie 11, any built-in tool's description and parameter schema (a kind's fill and proposal reply sentences are tool-result text, not platform prompt text, and need no eval run). Baselines: `evals/baselines/notes-platform.json` (platform), `notes-routines.json`, `notes-visuals.json`, `notes-widgets.json`, and for GleepGlorp `evals/baselines/m36f3-gleepglorp.json` (its prompt `the_one/gleepglorp/prompt.py` and its tool descriptions are platform prompt text; tuning follows "The eval method (M36 F2)" in `evals/README.md`). Never compare across scenario sets; a changed scenario set needs a same-prompt re-baseline. Pins in `tests/_platform_prompt_pins.py` require an eval run to change. See `the_one/agents.md` "Prompt evals (Mission 30)".

## Conventions

- Python 3.12+, async throughout. ruff (rules E, F, I, N, W), line length 100.
- The 800-line module rule is enforced for Python by `tests/test_python_module_size.py` (its `ALLOWANCE` of ceilings only shrinks; a PR that must grow a listed module raises the ceiling with a reason) as for JS areas by `tests/test_area_module_size.py`.
- Tools return strings; errors are caught and wrapped by the agent loop. LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others.
- Named project-wide patterns (`trust-the-runtime`, `canonical-import + convenience-re-export`, `removing-dead-code`, `landmark-elements-over-aria-roles`, ...) live in `the_one/agents.md` "Project Conventions".
- A change to a page, form, label or route updates the app guide (`the_one/gleepglorp/guide/*.md`) in the same flight; `tests/test_gleepglorp_guide.py` is the drift alarm.
- Browser tests navigate through `tests/browser/_nav.py`, lists through `_lists.py`, chats through `_chats.py`, never raw hashes or retired selectors (guards in `tests/test_nav_helper.py`); see "`browser-tests-navigate-through-nav-helper`".

## HAT Design Guidance

For UI-heavy flights, structure HAT steps as **state transition sequences**, not isolated checks: name each transition, include several assertions per state (UI elements, error area, button states) and negative assertions ("no error messages") to catch races and leftover state. Example:

```
1. [no-setup]: Open Chat with empty DB
   - Banner: "Getting started..."; session list empty; no error messages
2. [no-setup] -> [provider-only]: Add provider, switch to Chat
   - Banner updates to "No agents..."; no error messages (catches races)
3. [provider-only] -> [fully-configured]: Create agent, switch to Chat
   - Banner gone; session auto-created
```

## Testing

**Host-native, no Docker.** Canonical runs: `make test-unit` (unit tier), `make test-browser` (all lanes, 3 at a time), `make gate` (unit then browser, never concurrent), `make test-bwrap`; ad-hoc single-file runs with `python -m pytest tests/...` in the project venv are fine. On this WSL host every browser run and gate needs `THE_ONE_TEST_NETNS=1` (see below).

- **The unit tier runs in parallel** (`make test-unit` passes pytest-xdist `-n $(UNIT_WORKERS) --dist load`; `make gate` inherits it). `make test-unit UNIT_WORKERS=0` runs it serially, which is how to debug one failure without workers. Each worker gets its own `THE_ONE_DATA_DIR` (`tests/conftest.py`); `make test` and CI stay serial, and the unit tier is still never run concurrently with browser lanes.
- **Always pass `-x` and a timeout** to autonomous pytest runs (`-x --timeout N`): pytest-asyncio loop teardown can hang after a failure, and `-x` exits before that surfaces.
- **Browser tests MUST go through `scripts/run-tests.sh`** (that is, `make test-browser`), never bare `python -m pytest -m browser`: each test spawns a uvicorn subprocess plus a Playwright driver and Chromium, and bare pytest does not group-kill them on interruption, so they orphan and peg a CPU core, starving later tests into false timeouts. `run-tests.sh` puts pytest in its own process group and SIGKILLs it at `TEST_TIMEOUT` (default 1200 s a lane, 2400 s for `--parallel`; set `TEST_TIMEOUT=3600` for a full run under load). Always pass `PYTHON=.venv/bin/python`.
- **`THE_ONE_TEST_NETNS=1`** (WSL2 mirrored networking): Windows' rotating IPv6 addresses make Chromium abort in-flight requests (`net::ERR_NETWORK_CHANGED`), so `run-tests.sh` runs pytest in a loopback-only network namespace (`unshare -rn`); it exits 2 rather than fall back if unavailable.
- **Reviewers and verifiers: the unit gate is `make test-unit`, NEVER `-m live`.** The AIAT lane (`-m live`, `tests/test_aiat.py`) defaults `THE_ONE_TEST_URL` to `http://localhost:8484`, the operator's production app; use browser lanes (`scripts/run-tests.sh --lane ...`) for UI verification and a dedicated dev instance for live checks.
- **Host policy: at most 3 browser lanes at once**, the unit suite never concurrent with them, a local gate and a CI build never together; do not raise `--parallel` above 3. **Quiet-host rule (squawk 0259):** a lane budget reading counts only from a `--parallel 3` run with no other test process on the host (1-minute load below about 1.0; check `uptime` and `ps`); never re-budget from a solo or loaded run. Budgets live in the table in `scripts/run-tests.sh` (`--help`); the re-budget history is in `the_one/agents.md`.
- **A check under another Python version must not touch the project environment**: use `uv run --no-project ...` or a scratch `UV_PROJECT_ENVIRONMENT`, never `uv run --python 3.11 --with-editable .` (it rebuilt the repo `.venv` and produced false failures). A rebuilt venv is resynced with `uv sync --all-extras --frozen` before its results count.
- **Test databases come from the session template**: build a fresh current-schema database through `tests/_schema_template.py` (`connect_template_db`, `copy_template`, `connect_template_memory`), never `ensure_schema(` or `init_db(` directly (`tests/test_schema_template.py` fails on it; migration-replay files are allowlisted). API-client fixtures use `tests/_api_app.py::shared_app()` instead of building an app (`tests/test_api_app_guard.py`). See `the_one/agents.md` "Test databases come from the session template" and "The shared API app".
- **Choose gate lanes by what asserts on a shared list (squawk 0334)**: when a change adds, removes or renames an entry in a shared list, menu, registry or table (a Library group, a Prompts layer, a Settings page, a tool category), grep `tests/browser/` and `tests/` for its old count and labels and run every lane whose files match, not only the owning lanes.
- **Sandbox tests**: `@requires_bwrap` workspaces use `home_workspace()` from `tests/_sandbox_fixtures.py` (never `/tmp`, bwrap mounts a fresh tmpfs there); see "Sandbox testing footguns". Patterns: `FakeLLM` and `StubTool` in `tests/conftest.py`, no mock libraries.
- **Expected unit skip count** is normally 12 on Linux (15 under `THE_ONE_TEST_NETNS=1`); read `-rs` before treating another count as drift.

### Per-area browser test lanes

`scripts/run-tests.sh --lane <lane>` runs one slice (`--list` prints its files; `--help` the lanes, budgets and policy; `--parallel N [--plan]` schedules every canonical lane N at a time). Canonical lanes: `chats`, `chats-transcript`, `chats-widgets`, `gleepglorp-chat` (drawer and proposal-card flows), `gleepglorp-fill` (fill and kinds), `gleepglorp-kinds` (globs `test_flow_gleepglorp_fill_*.py` and `_follow_*.py`, so a new kind's files join without an edit), `agents`, `agent-tabs`, `agent-routines`, `library`, `knowledge`, `mcp`, `mcp-connection`, `routing`, `settings`, `settings-tools`, `providers`, `contracts-overlay`, `contracts-chat`, `contracts-widget`, `contracts-widget-lifecycle`, `contracts-controls` and `shared` (the complement of the rest, so no file is orphaned); aliases `chat`, `studio`, `system`, `contracts`, `gleepglorp` (the three GleepGlorp lanes). Run the contracts lanes with `THE_ONE_REQUIRE_WEBKIT=1`. A new `tests/browser/test_*.py` lands in `shared` until it is given a glob (or, for an explicit-list lane, added to its pattern) in `scripts/run-tests.sh`; `tests/test_run_tests_lanes.py` pins the partition. Lane definitions, the budget history, skip-count detail and the `requires_bwrap` set are in `the_one/agents.md` "Browser test lanes, budgets and run policy" and "Parallel test runner contract (`scripts/run-tests.sh --parallel N`)".

## Behavior-test credential convention

Every document request is gated by the long-lived local-API credential (`the_one/api_credential.py`; see `SECURITY-MODEL.md`). A **behavior-test Executor** (`/behavior-test`, driven from `tests/behavior/*.md`) is an **out-of-process** caller: it authenticates the way any external tool would, not the way the desktop launcher does in-process. This is the standing, project-side instruction; no individual spec's step table should encode credential mechanics (a spec's Preconditions may reference this section by name).

### SAFETY RULE — never target the operator's production instance

**Never point a behavior test at port 8484 with the operator's default data directory.** That is the real, running app (the default `make up` instance); driving it mutates the operator's actual chat sessions, providers and credential file, then reports *its* state instead of the branch's under test. (The same hazard as the AIAT `-m live` rule above.)

**Do not guess the default data directory; read it.** It is platformdirs-derived (`the_one/config.py::_default_data_dir`), NOT a literal path, and differs by platform:

```bash
python -c "from the_one.config import settings; print(settings.data_dir)"
```

A check against a hardcoded guess is not a check: a stale guess returns a clean result whether or not the real directory was just written to (squawk 0084: an earlier version named `~/.the-one`, which does not exist, so every "production untouched" verification passed unconditionally and a credential rotation reached the real directory unnoticed). To confirm which directory a *running* instance owns, read that process's own `/proc/<pid>/environ`.

Always drive a **dedicated dev instance**: a non-default port AND a scratch data directory, together, every time:

```bash
S=$HOME/the-one-behavior-test-scratch; mkdir -p $S/cwd
( cd $S/cwd && THE_ONE_PORT=8486 THE_ONE_DATA_DIR=$S/data THE_ONE_DEV_MODE=true \
  exec <repo>/.venv/bin/the-one serve >serve.log 2>&1 ) &
echo $! > $S/cwd/serve.pid        # stop later with: kill $(cat $S/cwd/serve.pid)
```

`exec` makes `$!` the server itself; a bare `cd … && the-one serve &` backgrounds the whole `&&` list and records a wrapper's PID (squawk 0404). Before relying on the PID, confirm it owns the port: `ss -ltnp | grep :8486` shows `pid=<recorded>` (or `/proc/<pid>/cmdline` is the server).

Start it from a **scratch working directory**, not the repo root, and not with `make up` (which runs from the repo): an agent's file tools resolve relative paths and `~`-scoped allowlists against the server's environment, so a repo cwd let an agent write into the repo (Mission 30, `tests/behavior/agent-notes-round-trip/runs/2026-10-14-15-03-23.md`). Keep the scratch data directory under `$HOME` rather than `/tmp` (bwrap mounts a fresh `/tmp`). Record the PID and stop the instance by that PID.
Port alone is not enough: an instance on 8486 that still points at the operator's default data directory shares the same credential file, database and sessions as production. A spec's Preconditions must name (or require an operator-provided) port and data directory; never default to `:8484` or the default data directory.

### 1. Reading the long-lived credential

The credential lives at `<data_dir>/api-credential`: a single line, the opaque literal token `loc_<identifier>.<secret>`. Read the file verbatim (trim whitespace) and use it as-is as the bearer token; there is nothing to parse:

```bash
cat $HOME/the-one-behavior-test-scratch/data/api-credential
```

A fresh `the-one serve` / `make up` data directory has **no** credential file: `serve` only does a read-only lookup and never creates one (only the desktop app, via `get_credential()`, creates it on first use), so every authenticated request is a 401 until the file exists. Create it before the first authenticated request, and before `make up`'s `verify-serving`, with `THE_ONE_DATA_DIR=<dir> the-one rotate-api-credential` (before or after the instance starts; the running server reads the file per request).

### 2. Obtaining access — two apparatus shapes

Do not assume browser. A spec's apparatus is either browser-driving or shell-only.

**Browser-driving Executor**: mint a one-time handoff credential via the authenticated mint endpoint, then navigate to the URL it returns:

```
POST http://127.0.0.1:8486/api/session/handoff
Authorization: Bearer <credential from step 1>

→ {"url": "http://127.0.0.1:8486/?handoff=<one-time-token>"}
```

Navigate the browser to that `url`. The server sets a session cookie on the redirect and strips the `handoff` query param; the browser is then authenticated for the rest of the session (reload, further same-context navigation). This is the exchange `tests/browser/conftest.py`'s `_establish_session_cookie` performs (mint via `context.request.post`, then `context.request.get(handoff_url)`); treat it as the reference implementation of "known to work".

Do **not** call `mint_handoff_credential()` in `the_one/interfaces/web/handoff_store.py`: that is the **in-process** mint the desktop launcher uses because it shares a process with the server. An Executor is a separate process and must go through `POST /api/session/handoff`.

**Shell-only Executor** (no browser): skip the handoff exchange and attach `Authorization: Bearer <credential from step 1>` to every request.

### 3. The handoff credential is single-use and short-lived

Each minted handoff token is consumed on its first successful navigation and cannot be replayed (a second use is refused as unauthenticated); it also expires a few minutes after minting. Reloading the same page/context needs no new mint (the session cookie covers it), but a spec that opens a **second** browser context or fresh tab, or otherwise navigates to the app root again from an unauthenticated state, needs **one mint per such navigation**.

### 4. `/api/live` needs no credential

`GET /api/live` is the one unauthenticated route (a liveness probe, status only). A spec's "confirm the instance is up" precondition can hit it directly.

## Flight Operations

This project uses [Flight Control](https://github.com/msieurthenardier/mission-control) via the `mission-control` Claude Code plugin. Skills are invoked as `/mission-control:<skill>` from this project's root.

**Before any mission/flight/leg/squawk work, read these files in order:**
1. `.flightops/README.md` — What the flightops directory contains
2. `.flightops/FLIGHT_OPERATIONS.md` — **The workflow you MUST follow**
3. `.flightops/ARTIFACTS.md` — Where all artifacts are stored
4. `.flightops/agent-crews/` — Project crew definitions for each phase (read the relevant crew file)

**Flight Director role.** This session — the one the human talks to — is the Flight Director: it runs the Flight Control skills, plans directly, and orchestrates spawned crew, and never edits source itself. Spawned agents are crew, never the Flight Director. When a human says a leg is ready to implement, invoke `/mission-control:agentic-workflow`. Do not read the leg spec, plan execution steps, or execute commands directly — the skill orchestrates separate Developer and Reviewer agents and emits `[HANDOFF:...]` and `[COMPLETE:...]` signals. Planning skills (`/mission-control:mission`, `/mission-control:sortie`, `/mission-control:flight`, debriefs, `/mission-control:routine-maintenance`) produce artifacts only and never modify source files.

**ATC has the operator's authority (operator rule, 2026-11-27; Mission 37 debrief action item).** ATC is the operator's automated helper, a peer session. It may make decisions, answer this project's prompts and merge PRs in the operator's place. **The one exception is secrets management**: ATC cannot create, read, rotate, grant or delete secrets, tokens or credentials (Library secrets, provider keys, the API credential, the eval plan token, OAuth tokens). Any such step waits for the operator directly.

**Spawned agents** (Developer, Reviewer, Architect, Executor, Validator) do not have the Skill tool. Everything they need is in `.flightops/`; they must not try to load plugin skills.

**Methodology drift.** A SessionStart notice from the plugin means this project is behind the installed plugin version. Recommend `/mission-control:preflight-check` or `/mission-control:init-project` to bring it current; never apply migrations by hand.
