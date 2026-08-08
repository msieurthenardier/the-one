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

# Diagnose the runtime spawn seam (esp. inside a frozen/packaged build):
# spawns a probe child, resolves the external Python interpreter, detects
# node/uv/python on PATH. Prints PASS/FAIL; exits non-zero on failure.
the-one doctor

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

**Lint/format gate.** Run `pre-commit install` once to activate the pre-commit hook (`pipx install pre-commit` first if you don't have it; it's also in the `[dev]` extra). The same `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/` run in CI on every push to `main` (Concourse, `ci/tasks/lint.yml`). The gate exists to stop ruff-baseline drift — so a future maintenance cycle doesn't re-discover its absence. CI now runs on local Concourse; the GitHub Actions `lint.yml` and `test.yml` are `workflow_dispatch`-only break-glass fallbacks — see `ci/README.md` for the full topology.

## Local dev (host-native)

The app runs host-native via `the-one serve` (console script → `uvicorn.run(app, settings.host, settings.port)`, no `--reload`). For day-to-day dev use `make up` to launch it backgrounded against the repo venv (writes `.the-one.pid` + `.the-one.log`, both gitignored). Because `serve` has no `--reload`, **source edits take effect on `make restart`** — there is no live hot-reload. The test suite spawns its own uvicorn subprocess; that path is independent of the `make up` server at port 8484.

```bash
make up                     # start the-one host-native in the background (PID + log) + verify
make restart                # restart to pick up source edits (no --reload) + verify
make down                   # stop (by PID)
make logs                   # tail the host log file (.the-one.log)
make reset-db CONFIRM=1     # wipe the host data dir + restart. Gated to prevent accidental data loss.
make test                   # run all default tests (host-native)
make test-unit              # unit tests only
make test-browser           # Playwright browser tests
make lint                   # ruff check
make format                 # ruff format
make verify-serving         # curl-check that admin sub-modules return 200
make help                   # list all targets
```

**When `make restart` is required**: any change under `the_one/` you want reflected in the running `make up` server — JS, CSS, HTML, Python. There is no live-reload, so a restart re-imports the source.

**When `make restart` is NOT required**: editing files under `tests/` (the test suite spawns its own uvicorn subprocess, independent of the served daemon) or running ad-hoc one-off pytest invocations.

**Note — restart to pick up Pydantic class-definition edits.** Editing a Pydantic **class definition** (`AgentConfig`, `Connector`, `ChatSession`, provider config models) requires a fresh process to take effect: each model binds a compiled core schema to the class object at import, so a long-lived server keeps validating against the schema it imported at startup. `make restart` re-imports everything with fresh class objects.

## Architecture (orientation)

Four layers compose bottom-up: **Interfaces** (CLI + Web/FastAPI) → **Agent** (loop, factory, config, persistence) → **Tools / LLM** (tool registry + provider abstraction) → **Config / Persistence** (pydantic-settings + SQLite + Fernet-encrypted credentials).

**Watch-out**: the provider edit form sends the literal `__MASKED__` for unchanged API keys. `update_provider` in `interfaces/web/api.py` detects this sentinel and preserves the stored value. Anyone touching the provider edit form needs to know this contract.

**LLM layer — `anthropic-plan` provider type (M19)**: chats on a Claude Pro/Max subscription via OAuth sign-in from Administration (popup or copyable URL + code paste) — no API key ever; tokens live Fernet-encrypted in `llm_providers.secrets` (stripped from every response — `oauth_active` is the UI signal) and auto-refresh via the per-provider single-flight credential source in `the_one/llm/plan_credentials.py`.

Full module map, layer internals, tool-authorship contract, constraint surfaces (Filesystem/Execution/Web Configs), cross-Config dispatch, PTY session lifecycle, MCP F2/F3 contracts, MCP error translation, operator workflows — all in `the_one/agents.md`. Don't duplicate that material here.

## Desktop launcher (`the-one app`)

`the_one/interfaces/app.py` (M15 F4). `uvicorn.Server` on a **daemon thread** + `pywebview` on the **main thread**. The shared `_graceful_shutdown(server, thread)` helper sets `server.should_exit = True` then joins the thread (60s timeout); **no-op when `server is None`** (window-only client — attached to an existing server, owns nothing to drain). `_select_port` uses a connect-probe + startup-retry to classify the configured port as: free (start new server) / ours-by-version (attach a window only) / foreign (bind-0 a free port). `_webview_available` probes the Linux WebKit2 typelib via `gi.require_version` without importing Gtk/WebKit2 (importing can touch a display connection and hang headless). `pywebview` is the optional `[gui]` extra — `import webview` is **lazy** inside `run()`, NOT at module top-level; the base install is GTK-free.

M15 F6 added the desktop-shell module (`the_one/interfaces/desktop/`): **close-to-tray** (× hides the window; the process keeps running), **Quit from the tray menu is the real exit**, **single-instance focus** via `POST /api/window/focus` (second launch focuses the existing window instead of spawning a new one), and **window-state persistence** (`{data_dir}/window-state.json` — size + position restored on next launch, clamped to visible screen bounds).

M15 F7 refactored into the **`DesktopSession`** lifecycle class (`the_one/interfaces/desktop/shell.py`) and added: a **launch splash** (small frameless branded window shown during the uvicorn boot wait, dismissed on the main window's `loaded` event); a **native OS-framed main window** (`frameless=False`, `resizable=True` — native title bar, min/max/close, resize; the native × hides to tray via the F6 `_on_closing` path); and a **brand `.ico`** (256/128/64/48/32/16 px, generated by `packaging/windows/regenerate_icon.py`) embedded in the windowed exe. See `the_one/agents.md` "Desktop launcher" for the full contract reference and the pywebview/WebView2 frameless footgun note.

## Configuration

Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode. Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. LLM provider configuration is managed through the database (not env vars) — see the `/api/providers` endpoints.

### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, an extra provider type `mock` becomes available alongside the standard types (`ollama`, `openai-compatible`, `openai`, `anthropic`, `anthropic-plan`, `openrouter`). The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field — defaults to `"Mock response from the mock provider."` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

**Mock provider `config` options** (all optional, set in `LLMProviderConfig.config`):

- `"response"` — scripted reply text (default: `"Mock response from the mock provider."`)
- `"stream_chunks"` — a LIST of strings; when set (non-empty), `stream()` yields each list element as one streaming chunk in order. When unset/empty, the provider is non-streaming (default). (Not a chunk *count* — the values are the literal chunk texts, e.g. `["Hello, ", "world", "!"]`.)
- `"input_tokens"` — `input_tokens` value emitted in `TokenUsage` for each turn (default: `0`). Set to a positive integer in tests that exercise the telemetry overlay or the `last_usage` persistence path (M10 F06); the default preserves all existing test expectations.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled

## Security posture

See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the project's threat model and intentional security choices (no-auth-by-design, single-user local-only, Origin-allowlist mitigation, SSRF/subprocess boundaries).

**Origin allowlist override**: set `THE_ONE_ORIGIN_ALLOWLIST` to a comma-separated list of `scheme://host:port` patterns (port supports `*` wildcard) to extend the default `http://127.0.0.1:*` / `http://localhost:*` allowlist. See `SECURITY-MODEL.md` for the threat-model context.

**Boxed execution mode (M14 F4)**: `shell` and `python_exec` are **box-by-default** — each call runs in a disposable sandbox with a minimal read-only system rootfs, a fresh scratch directory as the only writable location, and network unconditionally off. The agent sets `host_access=true` to escalate out of the box and reach the host workspace (real `$HOME`, operator allowlist, network opt-in). See [SECURITY-MODEL.md](SECURITY-MODEL.md) "Boxed Execution Mode" for the full isolation model, scratch lifecycle, and read-scoping status.

**Windows PTY (M15 F3)**: interactive shell sessions use `WindowsPtySession` via
`pywinpty`/ConPTY (`pywinpty>=2.0; sys_platform == "win32"`). Windows is **unsandboxed**
— the sandbox factory returns `PassthroughSandbox` on non-Linux (DD9; see
`SECURITY-MODEL.md`). The PTY split-module structure: `platform/pty.py` = neutral ABC +
`create_pty_session` dispatcher; `platform/pty_unix.py` = `UnixPtySession`;
`platform/pty_windows.py` = `WindowsPtySession`. The idle-read mechanism uses
`proc.fileobj.settimeout()` + `recv()` + catch `socket.timeout` — NOT `proc.read()`.
**Do NOT set `read_blocking` after spawn** — pywinpty's read thread captures the flag at
construction; setting it later is a no-op (silent regression trap). See `the_one/agents.md`
"Windows PTY backend (M15 F3)" for the full developer reference (env allowlist, curated
CI lane rule, `_wrapped`-always-False).

**Frozen-runtime seam (M15 F5)**: a packaged (PyInstaller) double-clicked app launches with
a stripped `PATH` and a bundle dir (`sys._MEIPASS` / the exe's dir) prepended — neither of
which lets it spawn the real `node`/`uv`/`python` runtimes the agent needs. The seam lives in
`platform/env.py`: `is_frozen()` + `clean_subprocess_env()` (strip the bundle dir from the
front of the child `PATH`, then augment with common runtime install dirs plus a
`THE_ONE_EXTRA_PATH` operator override). It is applied inside `_build_subprocess_env()`, so
**every** spawn path (MCP stdio, shell, python-exec, PTY) inherits the sanitized env with no
per-call-site change; when not frozen it is a no-op. The MCP transport re-applies
`strip_bundle_dir_from_path()` at the caller *after* `build_stdio_environ`'s merge so an
operator-supplied `PATH` can't re-introduce the bundle dir (strip always wins; augmentation
yields to an explicit operator `PATH`). PyInstaller's loader-path leakage
(`LD_LIBRARY_PATH`/`DYLD_*`/`*_ORIG`) is defeated **by construction** — those keys are not in
the env allowlist, so no restore-`*_ORIG` code exists (an invariant test enforces it). When
frozen, `resolve_python()` resolves a real *external* interpreter (`THE_ONE_PYTHON` override or
`python`/`python3` on the augmented PATH) and raises an actionable error if none is found; the
POSIX shell/`execvp` path resolves to an absolute binary. Frozen builds anchor `.env` to the
per-user data dir (CWD is unpredictable when double-clicked); `THE_ONE_*` env vars always work.
`the-one doctor` is the diagnostic that exercises all of this end-to-end (and the apparatus the
Windows packaged-smoke CI reads).

**Windows packaging (M15 F5)**: the checked-in PyInstaller one-dir spec + frozen entry live in
`packaging/windows/` (build artifacts — never imported by `the_one/`); must build on native
Windows. See `packaging/windows/README.md`.

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

**The test suite runs host-native — no Docker.** (Mission 15 Flight 01 retired the `docker exec` test flow.) Canonical command for non-interactive runs: `make test` (or `make test-unit` / `make test-bwrap` / `make test-browser`), which routes through `scripts/run-tests.sh` and uses the repo `.venv` when present (else `python3`). For ad-hoc single-file/single-test runs, `python -m pytest tests/...` against the project venv is fine.

**The local-API credential gate is live (Mission 20 Flight 1) — a stray 401 in a new test or a manual `curl` almost always means a missing credential, not a real regression.** Every route except `GET /api/live` requires an identified caller (see `SECURITY-MODEL.md` "Authentication"). `make test` / `make test-unit` / `make test-browser` need nothing extra — the existing fixtures already attach a credential: unit-test client fixtures via `tests/_credential_helpers.py::auth_headers()`, browser fixtures/seeders via `tests/browser/_credential_registry.py::auth_headers_for()`. Where this bites is a *new* ad-hoc `httpx`/`TestClient` call added to a test body, or a bare `curl`/browser hit against a `make up` instance — either will get a 401 with no credential attached. Read the credential from `<data_dir>/api-credential` (verbatim, single line) or mint a fresh one with `the-one rotate-api-credential`.

**Browser tests MUST go through `scripts/run-tests.sh` (i.e. `make test-browser`), never bare `python -m pytest -m browser`.** Browser tests spawn a per-test uvicorn subprocess plus a Playwright node driver + Chromium. Bare `python -m pytest` does NOT group-kill that subtree on interruption — the uvicorn/Chromium children orphan (re-parent to init) and peg a CPU core indefinitely, and the leaked load then starves *other* tests into timeout-failures that look like flakiness. `run-tests.sh` puts pytest in its own process group and SIGKILLs the whole group on exit or at `TEST_TIMEOUT` (default 1200s), so nothing orphans. Set a tighter `TEST_TIMEOUT` for small slices. For FULL `make test-browser` runs set `TEST_TIMEOUT=3600` — the default 1200s is tighter than the ~12.5min suite runtime plus load overhead and will kill a healthy run. (Inside CI this matters less — Concourse task containers are ephemeral and torn down after each build, so `ci/tasks/*.yml` call `python -m pytest` directly with `--timeout`. The GitHub Actions `test.yml` is now a `workflow_dispatch`-only break-glass fallback — see `ci/README.md`.)

**Always pair pytest with `-x`** for autonomous runs unless you specifically want to see full failure surface — pytest-asyncio's per-test loop teardown can hang if a test leaves orphaned state on a torn-down loop, and `-x` exits on first failure before that hang surfaces. Without `-x`, a single broken test can wedge the suite indefinitely.

**Unit tests** run by default with `make test-unit` (host-native `python -m pytest tests/ -m 'not browser and not live and not pixel'`) — fast, no external dependencies.

**`tests/test_mcp_pool.py`** ships 10 pure-unit pool tests + 2 bwrap-dependent integration tests. The integration tests use `@pytest.mark.requires_bwrap` (registered in `pyproject.toml::markers`) and are deselected by default via the `not requires_bwrap` clause in `addopts`. To run the integration tests on a host with bwrap available: `pytest -m requires_bwrap tests/test_mcp_pool.py`.

**Built-in tool containment** (M14 F1) is proven by `tests/test_builtin_tool_sandbox.py` (5 tests: `shell` + `python_exec` each run through `BubblewrapSandbox` when bwrap is available, write-protection of denylisted paths, `sandbox_network_allowed` propagation, and the `PassthroughSandbox` fallback path). To run the full `requires_bwrap` set (12 tests: 5 built-in containment + 2 MCP pool integration + 5 PTY containment (`test_pty_sandbox.py`)): `pytest -m requires_bwrap`.

**Color contrast tests** (`tests/test_design_tokens_a11y.py`): WCAG 2.1 AA contrast audits for the F2 design tokens. Run via default `pytest tests/`. See `the_one/agents.md` "Color contrast (WCAG AA)" for the audited pairs and any deliberate exceptions.

**Visual snapshot tests** (`@pytest.mark.pixel`, in `tests/browser/test_visual_snapshots.py`): 12 Playwright baseline screenshots covering 3 UI areas × 2 states × 2 themes. Run via `pytest -m pixel`. Baselines live in `tests/browser/__snapshots__/` and are **gitignored** — local regression artifacts only; each developer regenerates on a fresh checkout with `pytest -m pixel --snapshot-update`. Tolerance 2% pixel diff. CI never runs `-m pixel` (excluded by default in `pyproject.toml::addopts`).

**Token-definition test** (`tests/test_token_definitions.py`): asserts every `var(--x)` reference in component CSS is defined in `tokens.css` or `fonts.css`. Catches typos that CSS would silently treat as `unset`.

**AIAT tests** (Agent-in-a-Test) are live integration tests that hit a running instance. They are excluded from default runs via `addopts = "-m 'not live'"` in `pyproject.toml`.

- **`THE_ONE_TEST_URL`** env var sets the target URL (default `http://localhost:8484`)
- **`@pytest.mark.live`** decorator marks AIAT tests — all live in `tests/test_aiat.py`
- Run live tests: `pytest -m live tests/test_aiat.py`

> **Reviewers/verifiers: the canonical unit gate is `make test-unit`, NEVER `-m live`.** The `-m live` AIAT lane defaults `THE_ONE_TEST_URL` to `http://localhost:8484` — the operator's PROD app (`the-one-app.exe` / `make up`). Running `-m live` as an acceptance/verification step points the suite at that live prod instance (mutating it, and reporting *its* state — not the branch's). `make test-unit` (`-m 'not browser and not live and not pixel'`) is self-contained and the only correct box-checking gate; use the browser lanes (`scripts/run-tests.sh --lane …`) for UI verification and a dedicated dev instance (e.g. port 8485) for any live/manual checks — never 8484.

**Browser tests** are end-to-end browser-driven tests using Playwright. They are excluded from default runs via `addopts = "-m 'not live and not browser'"` in `pyproject.toml`.

- **`@pytest.mark.browser`** marks browser tests — all live in `tests/browser/`
- Run browser tests: `pytest -m browser tests/browser/`
- Each test spawns its own app subprocess on a random port with an isolated `tmp_path` data_dir; teardown via SIGTERM
- Mock LLM responses are deterministic via the `mock` provider type (see below)
- See `tests/browser/conftest.py` for fixture documentation

**Per-area browser test lanes** (M17 F5). The full browser suite runs ~13min, so a verification pass that only touches one UI area shouldn't have to pay the whole tax. `scripts/run-tests.sh` accepts a `--lane {chat|studio|system|shared}` selector that runs just that area's slice:

```bash
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio    # Agent Studio slice
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chat      # Chat slice
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane system    # Admin / providers slice
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane shared    # cross-cutting slice
# Extra pytest args pass straight through, e.g. add `-x` or `-q`:
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio -q
```

Each lane runs independently green under the venv python (browser tests need `discord`, which the venv has and system `python3` does not — always pass `PYTHON=.venv/bin/python`). The full suite still runs exactly as before (`make test-browser`, no `--lane`).

- **`chat`** — `test_flow_chat*`, `test_flow_markdown_chat`, `test_flow_new_chat`, `test_flow_streaming`, `test_flow_context_overlay_thresholds`, `test_flow_usage_restore`
- **`studio`** — `test_flow_studio_*`, `test_studio_*`, `test_connector_*`, `test_mcp_*`, `test_flow_agent_*`, `test_flow_connector_*`
- **`system`** — `test_flow_admin_*`, `test_flow_provider_*`
- **`shared`** — the **complement**: every browser test file not claimed by the three area lanes (smoke, theme sync, markdown, keyboard, hash routing, oauth modal, dirty-confirm, cross-area gate, picker, seeders, app fixture, …)

Lanes are hand-rolled basename globs over `tests/browser/` — no new deps, no per-test markers. Because `shared` is defined as the complement, the four lanes' union is *always* exactly the whole browser suite and no test file can be orphaned — a newly added `tests/browser/test_*.py` lands in `shared` until it is given an area glob in `scripts/run-tests.sh`. (Union verified: the four lanes collect the same test count as `-m browser tests/browser/`.)

**Test patterns** (no mock libraries):

- **`FakeLLM`** (`tests/conftest.py`): An `LLMProvider` subclass that returns pre-scripted `Message` responses in order. Records all calls for assertion. Enables deterministic agent loop testing.
- **`StubTool`** (`tests/conftest.py`): A `Tool` subclass that records calls and returns a canned string. Used to verify the agent executes tools correctly without side effects.
- **`make_registry`** fixture: Creates a `ToolRegistry` pre-loaded with StubTools for quick test setup.

**Sandbox testing footguns** — three patterns that cause confusing false-passes or false-failures in `@requires_bwrap` tests. Full documentation in `the_one/agents.md` "Sandbox testing footguns"; summary here:

1. **Teardown-dispatch bit** — `UnixPtySession._wrapped` is set at `start()` time from `spec.command == "bwrap"`; mocking the backend after `start()` does not change the teardown path. Observe teardown behavior via the test's observable outputs, not backend state.
2. **PTY-echo sentinel** — the PTY echoes the sent command before executing it. Use the `"con"+"nected"` string-concat trick to keep assertion targets out of the echoed source. Assert on the post-echo output, not the full response.
3. **`@requires_bwrap` workspace under `$HOME`** — bwrap mounts a fresh `tmpfs` at `/tmp`, making `/tmp`-rooted workspaces invisible inside the sandbox. Always use `home_workspace()` from `tests/_sandbox_fixtures.py`; never use `tmp_path` or `/tmp` for bwrap test workspaces.

## Behavior-test credential convention

Every document request is gated by the long-lived local-API credential
(`the_one/api_credential.py`; see "Security posture" above and
[SECURITY-MODEL.md](SECURITY-MODEL.md)). A **behavior-test Executor**
(`/behavior-test`, driven from `tests/behavior/*.md`) is an
**out-of-process** caller — it authenticates the same way any external
tool would, not the way the desktop launcher does in-process. This
section is the standing, project-side instruction for that; per Mission
20 / Flight 1's DD13, no individual spec's Action/Expected-Result step
table should encode credential mechanics — a spec's Preconditions may
reference this section by name instead.

### SAFETY RULE — never target the operator's production instance

**Never point a behavior test at port 8484 with the operator's default
data directory.** That is the real, running app — the default `make up`
instance — and driving it mutates the operator's actual chat sessions,
providers, and credential file, then reports *its* state instead of the
branch's under test. (This mirrors the existing AIAT rule above for
`-m live` — the same production instance, the same hazard.)

Always drive a **dedicated dev instance** instead — a non-default port
AND a scratch data directory, together, every time:

```bash
THE_ONE_PORT=8485 THE_ONE_DATA_DIR=/tmp/the-one-behavior-test-scratch make up
```

Port alone is not enough — an instance on 8485 that still points at the
operator's default `~/.the-one` data directory shares the same credential
file, database, and sessions as production. A spec's Preconditions must
name (or require an operator-provided) port and data directory; never
default to `:8484` or the default data directory.

### 1. Reading the long-lived credential

The credential lives at `<data_dir>/api-credential` — a single line, the
opaque literal token `loc_<identifier>.<secret>`. Read the file's content
verbatim (trim surrounding whitespace) and use it as-is as the bearer
token — there is nothing to parse:

```bash
cat /tmp/the-one-behavior-test-scratch/api-credential
```

If the file does not exist, the instance has never reached
`get_credential()`'s create-on-first-use path — start the instance first
(it creates the file on first launch) or run
`THE_ONE_DATA_DIR=<dir> the-one rotate-api-credential` against it directly.

### 2. Obtaining access — two apparatus shapes

Do not assume browser. A spec's apparatus is either browser-driving or
shell-only, and the mechanics differ:

**Browser-driving Executor**: mint a one-time handoff credential via the
authenticated mint endpoint, then navigate to the URL it returns:

```
POST http://127.0.0.1:8485/api/session/handoff
Authorization: Bearer <credential from step 1>

→ {"url": "http://127.0.0.1:8485/?handoff=<one-time-token>"}
```

Navigate the browser to that `url`. The server sets a session cookie on
the redirect and strips the `handoff` query param from the address bar —
the browser is then authenticated for the rest of the session (reload,
further same-context navigation) with nothing more to resupply. This is
the exact exchange `tests/browser/conftest.py`'s
`_establish_session_cookie` performs (mint via `context.request.post`,
then `context.request.get(handoff_url)`) — treat it as the reference
implementation of "known to work" for this mechanism.

Do **not** call `mint_handoff_credential()` in
`the_one/interfaces/web/handoff_store.py` — that is the **in-process**
mint the desktop launcher uses because it shares a process (and memory)
with the server. An Executor is a separate process and cannot reach it;
it must go through the `POST /api/session/handoff` endpoint above, which
exists specifically for out-of-process callers that hold the long-lived
credential.

**Shell-only Executor** (no browser involved): skip the handoff exchange
entirely. Attach `Authorization: Bearer <credential from step 1>` directly
to every request.

### 3. The handoff credential is single-use and short-lived

Each minted handoff token is consumed on its first successful navigation
and cannot be replayed — a second use is refused as unauthenticated. It
also expires a few minutes after minting. Reloading the *same*
page/context does not need a new mint (the session cookie already covers
it) — but a spec whose steps open a **second** browser context, a fresh
tab, or otherwise navigate to the app root a second time from an
unauthenticated state needs a **second mint**, one per such navigation.

### 4. `/api/live` needs no credential

`GET /api/live` is the one unauthenticated route (a liveness probe,
status only). A spec's "confirm the instance is up" precondition can hit
it directly with no credential at all.

## Flight Operations

This project uses [Flight Control](https://github.com/msieurthenardier/mission-control).

**Before any mission/flight/leg work, read these files in order:**
1. `.flightops/README.md` — What the flightops directory contains
2. `.flightops/FLIGHT_OPERATIONS.md` — **The workflow you MUST follow**
3. `.flightops/ARTIFACTS.md` — Where all artifacts are stored
4. `.flightops/agent-crews/` — Project crew definitions for each phase (read the relevant crew file)
