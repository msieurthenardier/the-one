# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A self-modifying, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. The agent can edit its own source, run tests, deploy itself via Concourse CI, and roll back if things break.

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

# Lint & format
ruff check the_one/ tests/
ruff format the_one/ tests/

# Docker
docker compose up --build
```

## Architecture

The system has four layers that compose bottom-up:

**LLM layer** (`the_one/llm/`) — Abstract `LLMProvider` base with `complete()` method. Three implementations (ollama, openai, anthropic) lazy-loaded via a registry (`get_provider(name)`). All share the `Message`/`ToolCall`/`ToolResult` dataclasses from `base.py`. Provider is selected by `THE_ONE_LLM_PROVIDER` env var.

**Tool layer** (`the_one/tools/`) — Abstract `Tool` base class with `execute(**kwargs) -> str`. `ToolRegistry` holds all tools and generates JSON schemas for the LLM. `BuiltinToolProvider` (`builtins.py`) provides all 14 built-in tools via lazy import, implementing the `ToolProvider` protocol (`provider.py`). Tools are the agent's only way to affect the outside world.

**Agent loop** (`the_one/agent/core.py`) — The `Agent` class runs: user input → LLM call → tool execution → repeat until no tool calls remain. Behavioral constants and helpers live in `behaviors.py`:
- *Direct actions*: regex patterns that bypass the LLM for known commands (restart, rollback) — `match_direct_action()`
- *Continue signal*: a virtual tool (`CONTINUE_SCHEMA`) that keeps the agent's turn going
- Max 20 iterations per step as a safety limit

Agent configuration (`agent/config.py`) defines `AgentConfig` (Pydantic model) with LLM, prompt, tool filtering, and behavior settings. `AgentFactory` (`agent/factory.py`) wires config + LLM + tools into a ready-to-use Agent. Agent configs persist as JSON files via `AgentConfigStore` (`agent/store.py`).

**Interfaces** (`the_one/interfaces/`) — CLI (Rich + prompt-toolkit) and Web (FastAPI + WebSocket). Both use `AgentFactory.create()` to get configured agents, then call `agent.step(user_input)` which yields messages. The web app adds session management and broadcasts events to WebSocket subscribers.

For architecture internals, see `the_one/agents.md`.

## Self-Deployment

The agent deploys itself through Concourse CI (`ci/pipeline.yml`). Key jobs:
- `deploy`: test → build Docker image → health check via `/api/selftest` → auto-rollback on failure
- `autopilot`: runs every 30min, sends a work-cycle prompt to `/api/chat`
- `rollback`, `restart`, `pause-autopilot`, `unpause-autopilot`

The container runs from `/app` (built code) but mounts the source repo at `/workspace` (editable). Changes to `/workspace` take effect after a deploy.

## Configuration

All config via env vars prefixed `THE_ONE_` (see `.env.example`). Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. The `agents_dir` property (`settings.data_dir / "agents"`) provides the path for stored agent configurations.

## Conventions

- Python 3.11+, async throughout
- ruff for linting (rules: E, F, I, N, W) and formatting, line length 100
- Tools return strings, errors are caught and wrapped by the agent loop
- LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others

## Testing

**Unit tests** run by default with `pytest tests/` — fast, no external dependencies, ~65 tests in <1s.

**AIAT tests** (Agent-in-a-Test) are live integration tests that hit a running instance. They are excluded from default runs via `addopts = "-m 'not live'"` in `pyproject.toml`.

- **`THE_ONE_TEST_URL`** env var sets the target URL (default `http://localhost:8484`)
- **`@pytest.mark.live`** decorator marks AIAT tests — all live in `tests/test_aiat.py`
- Run live tests: `pytest -m live tests/test_aiat.py`

**Test patterns** (no mock libraries):

- **`FakeLLM`** (`tests/conftest.py`): An `LLMProvider` subclass that returns pre-scripted `Message` responses in order. Records all calls for assertion. Enables deterministic agent loop testing.
- **`StubTool`** (`tests/conftest.py`): A `Tool` subclass that records calls and returns a canned string. Used to verify the agent executes tools correctly without side effects.
- **`make_registry`** fixture: Creates a `ToolRegistry` pre-loaded with StubTools for quick test setup.
