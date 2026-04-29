# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A general-purpose, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. Built-in tools cover filesystem, execution, and web; a layered system prompt composes a foundational base with optional per-agent personas.

## Commands

```bash
# Install (editable, with all optional deps)
pip install -e ".[all-llms,dev]"

# Run CLI
the-one chat

# Run web server (port 8484)
the-one serve

# Tests
python -m pytest tests/ --tb=short -q
python -m pytest tests/test_example.py -q          # single file
python -m pytest tests/test_example.py::test_name   # single test
pytest -m live tests/test_aiat.py                   # AIAT (needs running instance)
pytest -m browser tests/browser/                    # Browser tests (needs THE_ONE_DEV_MODE=true)

# Lint & format
ruff check the_one/ tests/
ruff format the_one/ tests/
```

## Local dev with Docker

The container at `localhost:8484` serves from image-baked code (`Dockerfile COPY the_one/`) — **editing source on the host does NOT update the running app**. The test suite spawns its own uvicorn subprocess; that path is independent of the served daemon at port 8484. Browser tests can therefore go green while the user-facing app serves stale JS — `make rebuild` is the cure.

Use the Makefile rather than raw `docker compose` calls so the rebuild + verify step is consistent:

```bash
make rebuild                # rebuild image + restart + verify static assets (use after editing JS/CSS/Python)
make rebuild-clean          # rebuild + wipe DB volume + restart fresh (HAT prep — empty-state walkthroughs)
make reset-db CONFIRM=1     # wipe DB volume + restart (without rebuild). Gated to prevent accidental data loss.
make up                     # start without rebuilding
make down                   # stop
make logs                   # follow container logs
make shell                  # bash into the container
make test                   # run all default tests inside the container
make test-unit              # unit tests only
make test-browser           # Playwright browser tests
make lint                   # ruff check
make format                 # ruff format
make verify-serving         # curl-check that admin sub-modules return 200 (catches stale-image bugs)
make help                   # list all targets
```

**When `make rebuild` is required**: any change under `the_one/` — JS, CSS, HTML, Python. The Dockerfile copies these at build time; live-reload is intentionally NOT enabled (mirrors the Concourse CI/prod path).

**When `make rebuild` is NOT required**: editing files under `tests/` (the test suite spawns its own uvicorn subprocess, independent of the served daemon) or running ad-hoc one-off pytest invocations.

## Architecture

The system has four layers that compose bottom-up:

**LLM layer** (`the_one/llm/`) — Abstract `LLMProvider` base with `complete()` method. Three implementations (ollama, openai, anthropic) lazy-loaded via a registry (`get_provider(name)`). All share the `Message`/`ToolCall`/`ToolResult` dataclasses from `base.py`. Provider is resolved from the database via `LLMProviderRepository` — each agent references a provider config by `provider_config_id`.

**Tool layer** (`the_one/tools/`) — Abstract `Tool` base class with `execute(**kwargs) -> str`. `ToolRegistry` holds all tools and generates JSON schemas for the LLM. `BuiltinToolProvider` (`builtins.py`) provides all 7 built-in tools via lazy import, implementing the `ToolProvider` protocol (`provider.py`). Tools are the agent's only way to affect the outside world.

**Agent loop** (`the_one/agent/core.py`) — The `Agent` class runs: user input → LLM call → tool execution → repeat until no tool calls remain. The agent uses a virtual `CONTINUE_SCHEMA` (defined inline in `core.py`) as a turn-keeping signal — when the LLM calls `continue`, the loop registers another iteration. Max 20 iterations per step as a safety limit.

Agent configuration (`agent/config.py`) defines `AgentConfig` (Pydantic model) with `provider_config_id` (FK to `llm_providers`), `llm_model`, prompt, tool filtering, and behavior settings. `AgentFactory` (`agent/factory.py`) resolves the provider config from DB, maps the provider type to the registry name, and wires config + LLM + tools into a ready-to-use Agent. Agent configs persist via `SQLiteAgentStore` in the DB.

**Persistence** (`the_one/db/`) — SQLite via aiosqlite. `get_connection()` returns a shared async connection. Repository classes (`SQLiteAgentStore`, `KnowledgeBaseRepository`, `MCPSourceRepository`, `ChatSessionRepository`, `KBItemRepository`, `LLMProviderRepository`) each wrap a table with CRUD operations over Pydantic models. `LLMProviderRepository` takes an `Encryptor` for transparent encrypt-on-write / decrypt-on-read of API keys. Schema is versioned (currently v7) and auto-migrated on first connection.

**Encryption** (`the_one/encryption.py`) — Fernet symmetric encryption for API credentials. Key auto-generated at `{data_dir}/encryption.key` (mode 0600). `get_encryptor(data_dir)` returns an `Encryptor` instance. Supports key rotation via `rotate_key()`.

### `__MASKED__` sentinel for API key updates

The provider edit form sends the literal string `__MASKED__` as the `api_key` field when the user has not modified it. The backend (`update_provider` in `interfaces/web/api.py`) detects this sentinel and preserves the existing stored key rather than overwriting it with the masked display value. Anyone touching the provider edit form needs to know this contract.

**Interfaces** (`the_one/interfaces/`) — CLI (Rich + prompt-toolkit) and Web (FastAPI + WebSocket). Both use `AgentFactory.create()` to get configured agents, then call `agent.step(user_input)` which yields messages. The web app adds session management and broadcasts events to WebSocket subscribers.

The web UI has three functional areas sharing a sidebar + content panel layout:
- **Chat** — Multi-session chat with agent selection, WebSocket streaming, context telemetry
- **Studio** — Agent configuration editor (CRUD agents, tool toggles, connections)
- **Administration** — Settings display from `GET /api/settings`, provider management via `/api/providers` endpoints (CRUD, connection test, model discovery, key rotation). Provider configurations are stored in the database with encrypted API keys.

Areas register via `App.registerArea({ id, label, icon, order, init, activate, deactivate })`. The `init(sidebar, content)` function receives DOM elements on first activation; `activate()` fires on every switch-to (use for data refresh); `deactivate()` fires on switch-away. CSS is scoped under `.area-{id}`. Shared utilities like `App.escapeHtml()` are available on the `App` object.

The web UI ships with a token-based design system (NEXUS-style cyan accent, Geist Sans + Geist Mono self-hosted, ~20 Lucide SVG icons via `App.icon('name')`) and a tri-state theme switcher (`App.theme.{get,resolved,set}` with `'light'/'dark'/'auto'` semantics, OS-preference fallback, localStorage persistence under key `theme-preference`). The user-facing toggle lives in **Admin → System → Appearance**. Token definitions and the load-bearing contrast pair tables for both themes live in `the_one/agents.md` "Design system" section; per-theme values are mirrored in `tests/browser/design_tokens.py` for tests that assert on token values.

For architecture internals, see `the_one/agents.md`.

## Configuration

Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode. Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. LLM provider configuration is managed through the database (not env vars) — see the `/api/providers` endpoints.

### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, a fifth provider type `mock` becomes available alongside `ollama`, `openai-compatible`, `openai`, and `anthropic`. The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field — defaults to `"Mock response from the mock provider."` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled (the `TYPE_DEFAULTS` defaults and the `KNOWN_BADGE_TYPES` array are unconditional, so the badge styling resolves regardless of dev_mode)

## Conventions

- Python 3.11+, async throughout
- ruff for linting (rules: E, F, I, N, W) and formatting, line length 100
- Tools return strings, errors are caught and wrapped by the agent loop
- LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others

## HAT Design Guidance

For UI-heavy flights, structure HAT steps as **state transition sequences** rather than isolated checks. Name each transition explicitly and include multiple assertions per state (UI elements, error area, button states). Include negative assertions ("no error messages") to catch race conditions and leftover state.

Example format:
```
1. [no-setup]: Open Chat with empty DB
   - Banner: "Getting started..."
   - Session list: empty, no auto-create
   - No error messages
2. [no-setup] -> [provider-only]: Add provider, switch to Chat
   - Banner updates to "No agents..."
   - No error messages (catches race conditions)
3. [provider-only] -> [fully-configured]: Create agent, switch to Chat
   - Banner: gone
   - Session auto-created
```

This format caught three bugs during Flight 04 HAT that end-state-only specs missed (simultaneous banner + error, race condition on auto-join, stuck button state). If this approach proves effective across 2-3 more flights, recommend a permanent update to the mission-control leg skill to include state-transition guidance for UI-focused HAT legs.

## Testing

**Unit tests** run by default with `pytest tests/` — fast, no external dependencies, ~212 tests in <6s.

**Color contrast tests** (`tests/test_design_tokens_a11y.py`): WCAG 2.1 AA contrast audits for the F2 design tokens. Run via default `pytest tests/`. See `the_one/agents.md` "Color contrast (WCAG AA)" for the audited pairs and any deliberate exceptions.

**Visual snapshot tests** (`tests/browser/test_visual_snapshots.py`): 12 Playwright baseline screenshots covering 3 UI areas × 2 states × 2 themes. Run via `pytest -m browser tests/browser/test_visual_snapshots.py`. Baselines live in `tests/browser/__snapshots__/`; tolerance 2% pixel diff. Regenerate with `--snapshot-update` (commit baselines to git; CI compares only).

**Token-definition test** (`tests/test_token_definitions.py`): asserts every `var(--x)` reference in component CSS is defined in `tokens.css` or `fonts.css`. Catches typos that CSS would silently treat as `unset`.

**AIAT tests** (Agent-in-a-Test) are live integration tests that hit a running instance. They are excluded from default runs via `addopts = "-m 'not live'"` in `pyproject.toml`.

- **`THE_ONE_TEST_URL`** env var sets the target URL (default `http://localhost:8484`)
- **`@pytest.mark.live`** decorator marks AIAT tests — all live in `tests/test_aiat.py`
- Run live tests: `pytest -m live tests/test_aiat.py`

**Browser tests** are end-to-end browser-driven tests using Playwright. They are excluded from default runs via `addopts = "-m 'not live and not browser'"` in `pyproject.toml`.

- **`@pytest.mark.browser`** marks browser tests — all live in `tests/browser/`
- Run browser tests: `pytest -m browser tests/browser/`
- Each test spawns its own app subprocess on a random port with an isolated `tmp_path` data_dir; teardown via SIGTERM
- Mock LLM responses are deterministic via the `mock` provider type (see below)
- See `tests/browser/conftest.py` for fixture documentation

**Test patterns** (no mock libraries):

- **`FakeLLM`** (`tests/conftest.py`): An `LLMProvider` subclass that returns pre-scripted `Message` responses in order. Records all calls for assertion. Enables deterministic agent loop testing.
- **`StubTool`** (`tests/conftest.py`): A `Tool` subclass that records calls and returns a canned string. Used to verify the agent executes tools correctly without side effects.
- **`make_registry`** fixture: Creates a `ToolRegistry` pre-loaded with StubTools for quick test setup.
