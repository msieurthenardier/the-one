# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A general-purpose, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. Built-in tools cover filesystem, execution, and web; a layered system prompt composes a foundational base with optional per-agent personas.

**Codebase reference**: `the_one/agents.md` is the canonical deep reference for architecture internals, module map, tool-authorship contract, MCP foundation/sandbox contracts, project conventions, and design system. This file is the always-loaded operational manual; consult `agents.md` when working on internals.

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

**Lint/format gate.** Run `pre-commit install` once to activate the pre-commit hook (`pipx install pre-commit` first if you don't have it; it's also in the `[dev]` extra). The same `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/` run in CI (`.github/workflows/lint.yml`) on every PR and on pushes to `main`. The gate exists to stop ruff-baseline drift — so a future maintenance cycle doesn't re-discover its absence.

## Local dev with Docker

There are two ways the container runs. The **image-baked default** (`Dockerfile CMD ["the-one","serve"]` → `uvicorn.run(...)`, no `--reload`) serves from code `COPY`'d at build time — **editing source on the host does NOT update that running app**. The **committed compose dev path** (`docker compose up`, `docker-compose.yml:18-23`) instead bind-mounts host `./the_one` over `/app/the_one` and runs `uvicorn ... --reload --reload-dir /app/the_one` — so host edits DO propagate and most hot-reload live. The test suite spawns its own uvicorn subprocess; that path is independent of the served daemon at port 8484. On the image-baked path, browser tests can therefore go green while the user-facing app serves stale JS — `make rebuild` is the cure.

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

**When `make rebuild` is required**: any change under `the_one/` when running the **image-baked path** — JS, CSS, HTML, Python. The Dockerfile `COPY`s these at build time and that path has no live-reload, so a rebuild exercises the same image-build path as a real deploy. (On the committed `docker compose up` dev path the bind-mount + `--reload` makes most edits take effect without a rebuild — but see the gotcha below.)

**When `make rebuild` is NOT required**: editing files under `tests/` (the test suite spawns its own uvicorn subprocess, independent of the served daemon) or running ad-hoc one-off pytest invocations.

**Gotcha — Pydantic model edits under `--reload` may not take effect (intermittent).** Most host edits hot-reload fine under the compose dev path, but editing a Pydantic **class definition** (`AgentConfig`, `Connector`, `ChatSession`, provider config models) is a known exception: each model has a compiled core schema bound to the class object at import, and if a surviving reference to the *pre-reload* class object (a registry, cached import, or already-instantiated dependency) lingers, the worker keeps validating against the stale schema. Symptom: a `ValidationError` on a field you just added, or a new validator not firing. Remedy: `docker compose restart the-one` (targeted — restarts the worker with fresh class objects); `make rebuild` is the always-works hammer.

## Architecture (orientation)

Four layers compose bottom-up: **Interfaces** (CLI + Web/FastAPI) → **Agent** (loop, factory, config, persistence) → **Tools / LLM** (tool registry + provider abstraction) → **Config / Persistence** (pydantic-settings + SQLite + Fernet-encrypted credentials).

**Watch-out**: the provider edit form sends the literal `__MASKED__` for unchanged API keys. `update_provider` in `interfaces/web/api.py` detects this sentinel and preserves the stored value. Anyone touching the provider edit form needs to know this contract.

Full module map, layer internals, tool-authorship contract, constraint surfaces (Filesystem/Execution/Web Configs), cross-Config dispatch, PTY session lifecycle, MCP F2/F3 contracts, MCP error translation, operator workflows — all in `the_one/agents.md`. Don't duplicate that material here.

## Configuration

Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode. Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. LLM provider configuration is managed through the database (not env vars) — see the `/api/providers` endpoints.

### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, a fifth provider type `mock` becomes available alongside `ollama`, `openai-compatible`, `openai`, and `anthropic`. The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field — defaults to `"Mock response from the mock provider."` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled

## Security posture

See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the project's threat model and intentional security choices (no-auth-by-design, single-user local-only, Origin-allowlist mitigation, SSRF/subprocess boundaries).

**Origin allowlist override**: set `THE_ONE_ORIGIN_ALLOWLIST` to a comma-separated list of `scheme://host:port` patterns (port supports `*` wildcard) to extend the default `http://127.0.0.1:*` / `http://localhost:*` allowlist. See `SECURITY-MODEL.md` for the threat-model context.

## Conventions

- Python 3.11+, async throughout
- ruff for linting (rules: E, F, I, N, W) and formatting, line length 100
- Tools return strings, errors are caught and wrapped by the agent loop
- LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others

Named project-wide patterns (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`, `host-side-bench-drift-detection`, `container-test-entrypoints-reach-via-make`, `landmark-elements-over-aria-roles`, …) live in `the_one/agents.md`'s "Project Conventions" section.

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

This format caught three bugs during Flight 04 HAT that end-state-only specs missed (simultaneous banner + error, race condition on auto-join, stuck button state).

## Testing

**Canonical command for non-interactive runs**: `docker exec the-one pytest …` (matches the Makefile's `make test*` targets). Do **NOT** use `docker compose exec the-one pytest …` from non-interactive contexts (CI, agents, scripts) — `docker compose exec` defaults to `-it` (interactive + TTY) and hangs forever when stdin isn't a TTY. If you must use compose subcommands, pass `-T` to disable TTY allocation. This applies to anything driven from Claude Code's Bash tool, GitHub Actions, or shell scripts. Interactive shells (operator at terminal) can use either.

**Always pair pytest with `-x`** for autonomous runs unless you specifically want to see full failure surface — pytest-asyncio's per-test loop teardown can hang if a test leaves orphaned state on a torn-down loop, and `-x` exits on first failure before that hang surfaces. Without `-x`, a single broken test can wedge the suite indefinitely.

**Unit tests** run by default with `docker exec the-one pytest tests/` — fast, no external dependencies, ~213 tests in <6s.

**`tests/test_mcp_pool.py`** ships 10 pure-unit pool tests + 2 bwrap-dependent integration tests. The integration tests use `@pytest.mark.requires_bwrap` (registered in `pyproject.toml::markers`) and are deselected by default via the `not requires_bwrap` clause in `addopts`. To run the integration tests on a host with bwrap available: `pytest -m requires_bwrap tests/test_mcp_pool.py`.

**Built-in tool containment** (M14 F1) is proven by `tests/test_builtin_tool_sandbox.py` (5 tests: `shell` + `python_exec` each run through `BubblewrapSandbox` when bwrap is available, write-protection of denylisted paths, `sandbox_network_allowed` propagation, and the `PassthroughSandbox` fallback path). To run the full `requires_bwrap` set (12 tests: 5 built-in containment + 2 MCP pool integration + 5 PTY containment (`test_pty_sandbox.py`)): `pytest -m requires_bwrap`.

**Color contrast tests** (`tests/test_design_tokens_a11y.py`): WCAG 2.1 AA contrast audits for the F2 design tokens. Run via default `pytest tests/`. See `the_one/agents.md` "Color contrast (WCAG AA)" for the audited pairs and any deliberate exceptions.

**Visual snapshot tests** (`@pytest.mark.pixel`, in `tests/browser/test_visual_snapshots.py`): 12 Playwright baseline screenshots covering 3 UI areas × 2 states × 2 themes. Run via `pytest -m pixel`. Baselines live in `tests/browser/__snapshots__/` and are **gitignored** — local regression artifacts only; each developer regenerates on a fresh checkout with `pytest -m pixel --snapshot-update`. Tolerance 2% pixel diff. CI never runs `-m pixel` (excluded by default in `pyproject.toml::addopts`).

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

## Flight Operations

This project uses [Flight Control](https://github.com/msieurthenardier/mission-control).

**Before any mission/flight/leg work, read these files in order:**
1. `.flightops/README.md` — What the flightops directory contains
2. `.flightops/FLIGHT_OPERATIONS.md` — **The workflow you MUST follow**
3. `.flightops/ARTIFACTS.md` — Where all artifacts are stored
4. `.flightops/agent-crews/` — Project crew definitions for each phase (read the relevant crew file)
