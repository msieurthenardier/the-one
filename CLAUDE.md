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

# Lint & format
ruff check the_one/ tests/
ruff format the_one/ tests/

# Docker
docker compose up --build
```

## Architecture

The system has four layers that compose bottom-up:

**LLM layer** (`the_one/llm/`) — Abstract `LLMProvider` base with `complete()` method. Three implementations (ollama, openai, anthropic) lazy-loaded via a registry (`get_provider(name)`). All share the `Message`/`ToolCall`/`ToolResult` dataclasses from `base.py`. Provider is selected by `THE_ONE_LLM_PROVIDER` env var.

**Tool layer** (`the_one/tools/`) — Abstract `Tool` base class with `execute(**kwargs) -> str`. `ToolRegistry` holds all tools and generates JSON schemas for the LLM. `load_defaults()` registers all 14 built-in tools. Tools are the agent's only way to affect the outside world.

**Agent loop** (`the_one/agent/core.py`) — The `Agent` class runs: user input → LLM call → tool execution → repeat until no tool calls remain. Key mechanisms:
- *Direct actions*: regex patterns that bypass the LLM for known commands (restart, rollback)
- *Tool call extraction*: parses JSON tool calls from text output (for models without native tool use)
- *Continue signal*: a virtual tool that keeps the agent's turn going
- Max 20 iterations per step as a safety limit

**Interfaces** (`the_one/interfaces/`) — CLI (Rich + prompt-toolkit) and Web (FastAPI + WebSocket). Both create an Agent with an LLM provider and tool registry, then call `agent.step(user_input)` which yields messages. The web app adds session management and broadcasts events to WebSocket subscribers.

## Self-Deployment

The agent deploys itself through Concourse CI (`ci/pipeline.yml`). Key jobs:
- `deploy`: test → build Docker image → health check via `/api/selftest` → auto-rollback on failure
- `autopilot`: runs every 30min, sends a work-cycle prompt to `/api/chat`
- `rollback`, `restart`, `pause-autopilot`, `unpause-autopilot`

The container runs from `/app` (built code) but mounts the source repo at `/workspace` (editable). Changes to `/workspace` take effect after a deploy.

## Configuration

All config via env vars prefixed `THE_ONE_` (see `.env.example`). Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly.

## Conventions

- Python 3.11+, async throughout
- ruff for linting (rules: E, F, I, N, W) and formatting, line length 100
- Tools return strings, errors are caught and wrapped by the agent loop
- LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others
