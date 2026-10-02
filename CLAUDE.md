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
ruff check the_one/ tests/ scripts/
ruff format the_one/ tests/ scripts/
```

**Lint/format gate.** Run `pre-commit install` once to activate the pre-commit hook (`pipx install pre-commit` first if you don't have it; it's also in the `[dev]` extra). The same `ruff check the_one/ tests/ scripts/` + `ruff format --check the_one/ tests/ scripts/` run in CI on every push to `main` (Concourse, `ci/tasks/lint.yml`). The gate exists to stop ruff-baseline drift — so a future maintenance cycle doesn't re-discover its absence. CI now runs on local Concourse; the GitHub Actions `lint.yml` and `test.yml` are `workflow_dispatch`-only break-glass fallbacks — see `ci/README.md` for the full topology.

## Local dev (host-native)

The app runs host-native via `the-one serve` (console script → `uvicorn.run(app, settings.host, settings.port)`, no `--reload`). For day-to-day dev use `make up` to launch it backgrounded against the repo venv (writes `.the-one.$(THE_ONE_PORT).pid` + `.the-one.$(THE_ONE_PORT).log`, both gitignored — so the default instance writes `.the-one.8484.pid` and `.the-one.8484.log`). A dev instance started on another port (e.g. `THE_ONE_PORT=8485`) keeps its own PID/log files, which is what makes `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> make down` safe against the default instance. Because `serve` has no `--reload`, **Python source edits take effect on `make restart`** — there is no live hot-reload for imported code (static JS/CSS is a different story; see below). The test suite spawns its own uvicorn subprocess; that path is independent of the `make up` server at port 8484.

```bash
make up                     # start the-one host-native in the background (PID + log) + verify
make restart                # restart to pick up source edits (no --reload) + verify
make down                   # stop (by PID)
make logs                   # tail the host log file (.the-one.$(THE_ONE_PORT).log, e.g. .the-one.8484.log)
make reset-db CONFIRM=1     # wipe the host data dir + restart. Gated to prevent accidental data loss.
make test                   # run all default tests (host-native)
make test-unit              # unit tests only
make test-browser           # Playwright browser tests
make lint                   # ruff check
make format                 # ruff format
make verify-serving         # curl-check that admin sub-modules return 200
make help                   # list all targets
```

**When `make restart` is required**: any **Python** change under `the_one/` you want reflected in the running `make up` server — there is no live-reload, so a restart re-imports the source. One static file joins them: `the_one/interfaces/web/static/index.html` is served through `_cache_busted_index_html()` in `the_one/interfaces/web/app.py`, which is `@functools.lru_cache`-memoized, so the file is read from disk exactly **once per process** and an edit to it needs a restart like any Python change.

**When `make restart` is NOT required**: (a) **JS and CSS under `the_one/interfaces/web/static/`** — those are served by the `StaticFiles` mount in `app.py`, which reads from disk per request, so an edit is live to the very next request with no restart (measured: with the process unrestarted, the served body was byte-identical to the just-edited working-tree file); (b) editing files under `tests/` (the test suite spawns its own uvicorn subprocess, independent of the served daemon) or running ad-hoc one-off pytest invocations.

**If a JS/CSS edit appears not to have landed, suspect the browser cache, not the server.** `index.html`'s `/static` asset refs are cache-busted with `?v={__version__}` — the *package* version, which an edit does not change — so a browser keeps serving its cached copy no matter how many times the server is restarted (squawk 0085). Hard-reload the page, or `curl` the asset with the local-API credential to see what the server is actually serving. Restarting will not fix this, and reaching for a restart is what keeps the real cause hidden.

**Note — restart to pick up Pydantic class-definition edits.** Editing a Pydantic **class definition** (`AgentConfig`, `Connector`, `ChatSession`, provider config models) requires a fresh process to take effect: each model binds a compiled core schema to the class object at import, so a long-lived server keeps validating against the schema it imported at startup. `make restart` re-imports everything with fresh class objects.

## Architecture (orientation)

Four layers compose bottom-up: **Interfaces** (CLI + Web/FastAPI) → **Agent** (loop, factory, config, persistence) → **Tools / LLM** (tool registry + provider abstraction) → **Config / Persistence** (pydantic-settings + SQLite + Fernet-encrypted credentials).

**Watch-out**: the provider edit form sends the literal `__MASKED__` for unchanged API keys. `update_provider` in `interfaces/web/api.py` detects this sentinel and preserves the stored value. Anyone touching the provider edit form needs to know this contract.

**Watch-out**: agent PUTs preserve stored MCP credential overrides server-side — `update_agent` resolves incoming `mcp_overrides` against the stored row per credential key (omitted/masked → keep, `null` → clear), because Studio rebuilds `mcp_overrides` from the DOM and never sends credential fields at all. See `the_one/agents.md` "Agent override secrets storage".

**LLM layer — `anthropic-plan` provider type (M19)**: chats on a Claude Pro/Max subscription via OAuth sign-in from Administration (popup or copyable URL + code paste) — no API key ever; tokens live Fernet-encrypted in `llm_providers.secrets` (stripped from every response — `oauth_active` is the UI signal) and auto-refresh via the per-provider single-flight credential source in `the_one/llm/plan_credentials.py`.

**Self-configuration surface (M21 F01 L02-L03)**: an agent's Studio editor gains a sixth "Self-configuration" tab, off by default. Enabling it mints a per-agent credential and attaches a loopback MCP source through which the agent can act on its own configuration — a real `streamable-http` source, so the operator's existing per-source and per-tool checkboxes on the MCPs tab govern it exactly like any other MCP server (the row there is locked checked+disabled; only the Self-configuration tab can enable/disable it). Four tools: `get_my_configuration` / `describe_my_capabilities` (read), and `update_my_description` / `update_my_system_prompt` (write, M21 F01 L03) — each write tool takes `text` (the new value, whole-value replacement — no append or partial edit) and `apply`, either `"next_turn"` (the change lands when the agent's current turn in this conversation ends — never mid-turn) or `"next_session"` (this open conversation is untouched; the change is visible the next time the conversation is rejoined). No tool takes a field name, so no other part of an agent's configuration is reachable through this surface. **Operator oversight (M21 F02):** every self-revision is recorded in the `agent_revisions` log (L01), and each agent carries an operator-owned `self_revision_requires_approval` flag (L02, a v35 `agents` column, default off, unreachable by the agent). When approval mode is on, a proposed revision is held in the queue as `pending` instead of applied; the operator approves (fail-closed against staleness) or dismisses it from the Self-configuration tab. New endpoints under `/api/agents/{name}/self-configuration`: `PUT /approval-mode`, `GET /revisions`, `GET /revisions/pending-count`, `POST /revisions/{id}/approve` (`?override=true` to overwrite a drifted value), `POST /revisions/{id}/dismiss`. **Restore (L03):** `POST /revisions/{id}/restore` (`?side=proposed|base`, default `proposed`) rolls a field back to any earlier value it held — operator-direct, so it applies immediately regardless of approval mode and is logged as a new `applied`/`restore` row (never queued). The target must be an `applied` revision (a value the field actually took); a non-applied target is refused 409. `side=base` reinstates the target row's before-image — the only way to reach the original pre-first-revision value. There is no agent-facing restore tool. See `the_one/agents.md` "Self-configuration surface contract" and `SECURITY-MODEL.md`'s "Self-configuration surface" for the credential-scoping, approval-mode, restore, and residual-risk detail.

**Knowledge bases (M24)**: `POST /api/knowledge-bases/{kb_id}/items` with `type: "folder"` registers a folder on disk — operator-only (no agent-facing route creates items) and read with the app's own privileges, no allowlist; a folder that equals, contains, or lies inside the application data directory is refused with 422 (Flight 4), since the app's own database and index live there. Item routes (`GET`/`POST /items`, `GET`/`DELETE /items/{item_id}`, `POST /items/{item_id}/retry`) plus four Flight 3 routes: `GET /status` (per-KB item-status counts, each folder's walk status and watch state, chunk count, indexer state), `POST /reindex?scope=changed|all` (202; `changed` just re-walks, `all` also re-embeds every file), `GET /items/{item_id}/chunks` (paged, `seq` order), `GET /items/{item_id}/source` (extracted text read-back with a freshness flag). Indexing itself runs in a background worker (`IndexingManager`, one per knowledge base) started by the web app's lifespan; a killed or restarted process resumes rather than restarts — any item stranded mid-index (`indexing`) is requeued to `pending` at startup and at the top of every worker pass. **Change monitoring (M24 F04)**: a registered folder is kept current with no operator action — a per-folder filesystem watcher (native OS change notification, one dedicated thread per folder, at most 64 concurrent) that only ever triggers a re-index pass, backed by a periodic reconciliation walk (every 5 minutes by default) that is the actual source of truth and the only path that works on every platform. Both are operator-configurable, live, under `monitoring` in `GET`/`PUT /api/knowledge-settings`; `GET .../status`'s `folders[]` entries carry `watch`/`watch_error`. `the-one doctor` gained a ninth gate, `file watcher`, proving the native notifier loads (and, when frozen, round-trips a real change). See `the_one/agents.md`'s "Knowledge storage"/"Knowledge indexing"/"WatchManager" sections for the full pipeline and manager contracts.

**Agent-facing retrieval (M24 F5)**: an agent reaches its attached knowledge bases (`AgentConfig.kb_ids`) through one `kb__{slug}__search` tool per attachment, built per agent by `KBToolProvider` and registered by `AgentFactory` beside the MCP tools. `the_one/knowledge/retrieval.py::search` fuses the vector store's semantic hits with FTS5's keyword hits by reciprocal rank, with one result slot reserved for a keyword-only exact-term hit the embedding model would otherwise rank out of the returned set — so a query naming an identifier the model ranks poorly still surfaces it. The tool degrades honestly rather than failing silently: a stale, busy, or otherwise unavailable vector index falls back to keyword-only results (and the reverse for a keyword-index failure), each surfaced as one line above the hits. `search_tools` discovers these tools under a `kb:<slug>:` group, matched purely through the tool's own name and description (a knowledge base gets no separate `source_index` entry — see `the_one/agents.md`'s "Knowledge retrieval" section for why one would be inert). Attachment is authorization: an agent can only ever reach the knowledge bases the operator attached it to, and no agent-facing route creates or attaches one.

**Studio surfaces + operator-facing search (M24 F6)**: `GET /api/knowledge-bases/{kb_id}/search` (query param `q`, `limit: int = Query(10, ge=1, le=20)`, 404 on an unknown `kb_id`) wraps `retrieval.search` for a human caller — read-only, returning `{hits: [...], degraded: str | null, indexer: str}`; it sits behind the same credential gate as every other route (see SECURITY-MODEL.md). Studio's **Knowledge section** is the global inventory (create/rename/delete a knowledge base, register and inspect folders, read items/chunks/source, and preview search through the route above); the agent editor's **Knowledge tab** is attach-only — a per-knowledge-base row toggle (mirroring the MCPs tab's pattern) that also renders the knowledge base's derived `kb__…__search` tool name, served by the backend (`compute_tool_names`, promoted from a private helper) rather than recomputed in JavaScript. Administration gained a **Knowledge** panel (now `#settings/knowledge-indexing`) for the app-wide `chunking`/`monitoring` settings — `embedding` and `vector_store` render read-only, each with its reason stated on screen: the embedding model is pinned (there is no operator path to change it — see DD-7 in `missions/24-knowledge-bases/flights/06-studio-surfaces/flight.md`), and the vector-store record is written by the app, not chosen by the operator.

**Mission close, non-UI defect closure (M24 F7 L1)**: the vector store now has a shutdown hook — `the_one/vectors/__init__.py::close_vector_store()` closes the process-wide store if one was built (never builds one just to close it) and is called unconditionally from the lifespan, between the indexing-manager drain and `close_connection()`. It skips any knowledge base whose most recent `IndexingManager.stop()` took the cancel fallback (`IndexingManager.cancelled_kb_ids()`, DD-3a) — flushing one right after would race a still-running mutation and tear the index; the lost write is recovered by re-indexing instead. Separately, `AgentFactory.create()`'s `kb_tools` loop now reconciles a stale `disabled_tools` entry against a knowledge base's `kb_id` (not just its current derived name) — closes the hole where a disable made while an agent was attached silently stopped applying after the knowledge base was detached, renamed, and reattached. See `the_one/agents.md`'s "Vector-store shutdown hook" and "DD-13" blocks for the full contract.

**Mission close, inventory freshness (M24 F7 L2a)**: `GET /api/knowledge-bases/{kb_id}/status` gains two additive keys. `"content_freshness"` is `MAX(indexed_at)` across the KB's `file` items — it moves **iff** a file item actually re-indexes (never on a no-op walk pass, unlike a folder item's own `indexed_at`, which advances on every completed walk regardless of change) — and `studio.js::knowledgeItemsSignature` now folds it in, so a content-only edit to an already-indexed file (previously invisible to the poll) now triggers the `/items` re-fetch that repaints the item row's new `Indexed: …` freshness line. Each `folders[]` entry also gains `"skipped_dirs"`/`"skipped_entries"` — the last completed walk's counts, persisted via `AppMetadataRepository` under a key from the new `the_one.knowledge.settings.walk_skip_counters_key()` helper (one shared implementation across the write site, the read site, and both delete-path cleanup sites, since a kv key sits outside `kb_items`' FK cascade). `AppMetadataRepository` gained a `delete(key)` method. Separately, squawk 0087 is fixed: `KBItemRepository.list`/`.list_children`/`.list_folders` now order `..., path_or_url` ascending, so a tied `created_at` batch (a folder walk inserting every file in one pass) reads back in stable, walk-matching order. See `the_one/agents.md`'s "`get_kb_status` gains two ADDITIVE signals" block for the full contract.

**Mission close, confirm-lapse cue (M24 F7, `confirm-lapse` leg)**: the shared two-step `App.confirmDelete` helper (`the_one/interfaces/web/static/js/confirm.js`) now distinguishes a timed-out arm from a never-armed control. A `.confirm-lapsed` CSS class is added ONLY by the arm timer's own expiry callback (never by `revert()` itself, which also runs on a successful commit and on a credential-rotation success path that must not be mislabeled "lapsed"), and is cleared unconditionally at the top of every `confirmDelete` call — arm or commit alike — so a returning operator always starts from a clean visual slate. Feedback-only: the arm/commit decision still depends solely on the pre-existing `.confirm-delete` class; `.confirm-lapsed` never gates it. Applies uniformly across all 13 `App.confirmDelete` call sites, with no per-call-site opt-in. Closed squawk 0088's third invariant (`renderAllItems` must never rebuild a folder's armed `<summary>` node) along the way, with a falsified-and-reverted regression test proving the pin. See `the_one/agents.md`'s "confirm-lapse cue" section for the full contract and the squawk for the invariant-pinning test.

**Mission close, Windows vector-store measurement (M24 F7, `measurement` leg)**: `ci/tasks/windows-vector-bench.yml` is a new ad-hoc (not part of the standard five-lane CI matrix) Concourse task that runs `scripts/bench_vector_store.py` on the `platform: windows` worker for one synthetic-corpus rung at a time (`-v bench_n=<N>`, no default — an unset rung size fails loudly rather than running silently at the wrong size). It re-confirms the flush-cadence constants from Flight 3 against measured data up to a 500k-vector rung (the operator's stop-at-500k decision; the 1M rung was not run — its cost/benefit was projected from two independent anchors instead) and records per-cell `usearch_acceleration` so a stale/unaccelerated Windows backend cannot silently produce numbers for a build the product does not ship. `scripts/sweep_fusion_constants.py` (new) is the accompanying `RRF_K`/`candidate_k` sweep that closed the mission's fusion-balance open question as "fixed by evidence, not tuned" (DD-4) — no product constant changed. See `the_one/agents.md`'s vector-store bench section and `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`'s "Leg measurement (3)" for the full ladder, band declarations and verdicts.

Full module map, layer internals, tool-authorship contract, constraint surfaces (Filesystem/Execution/Web Configs), cross-Config dispatch, PTY session lifecycle, MCP F2/F3 contracts, MCP error translation, operator workflows — all in `the_one/agents.md`. Don't duplicate that material here.

## Desktop launcher (`the-one app`)

`the_one/interfaces/app.py` (M15 F4). `uvicorn.Server` on a **daemon thread** + `pywebview` on the **main thread**. The shared `_graceful_shutdown(server, thread)` helper sets `server.should_exit = True` then joins the thread (60s timeout); **no-op when `server is None`** (window-only client — attached to an existing server, owns nothing to drain). `_select_port` uses a connect-probe + startup-retry to classify the configured port as: free (start new server) / ours-by-version (attach a window only) / foreign (bind-0 a free port). `_webview_available` probes the Linux WebKit2 typelib via `gi.require_version` without importing Gtk/WebKit2 (importing can touch a display connection and hang headless). `pywebview` is the optional `[gui]` extra — `import webview` is **lazy** inside `run()`, NOT at module top-level; the base install is GTK-free.

M15 F6 added the desktop-shell module (`the_one/interfaces/desktop/`): **close-to-tray** (× hides the window; the process keeps running), **Quit from the tray menu is the real exit**, **single-instance focus** via `POST /api/window/focus` (second launch focuses the existing window instead of spawning a new one), and **window-state persistence** (`{data_dir}/window-state.json` — size + position restored on next launch, clamped to visible screen bounds).

M15 F7 refactored into the **`DesktopSession`** lifecycle class (`the_one/interfaces/desktop/shell.py`) and added: a **launch splash** (small frameless branded window shown during the uvicorn boot wait, dismissed on the main window's `loaded` event); a **native OS-framed main window** (`frameless=False`, `resizable=True` — native title bar, min/max/close, resize; the native × hides to tray via the F6 `_on_closing` path); and a **brand `.ico`** (256/128/64/48/32/16 px, generated by `packaging/windows/regenerate_icon.py`) embedded in the windowed exe. See `the_one/agents.md` "Desktop launcher" for the full contract reference and the pywebview/WebView2 frameless footgun note.

## Configuration

Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode. Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. LLM provider configuration is managed through the database (not env vars) — see the `/api/providers` endpoints.

### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, an extra provider type `mock` becomes available alongside the standard types (`ollama`, `openai-compatible`, `openai`, `anthropic`, `anthropic-plan`, `openrouter`). The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field (a dict, whose `content` holds the reply text) — defaults to `{"content": "Mock response from the mock provider."}` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

**Mock provider `config` options** (all optional, set in `LLMProviderConfig.config`). **Mind the nesting**: only the five top-level keys below sit in `config` itself; `content`, `tool_calls` and `thinking` live *inside* `response`, not beside it. (Cross-check against `MockProvider`'s class docstring in `the_one/llm/mock.py` — that is the other copy of this list.)

- `"response"` — a **dict** describing what a turn returns (default: `{"content": "Mock response from the mock provider."}`). It must be a dict: `MockProvider` calls `.get()` on it, so a bare string (`{"response": "hi"}`) raises `AttributeError` rather than being treated as the reply text. Its keys:
  - `"content"` — the reply text (default: `""`)
  - `"tool_calls"` — a LIST of `{"id": str, "name": str, "arguments": dict}` dicts (`arguments` optional, defaults `{}`), synthesized into real `ToolCall`s on the assistant `Message`. This is the only way to drive a deterministic tool-calling agent turn with no live provider — two behavior specs depend on it — and it is what lets an apparatus make an agent *attempt* a tool call. Also attached to the final chunk of a `stream_chunks` run.
  - `"thinking"` — a LIST of block dicts parsed into `ThinkingBlock`s: `{"type": "thinking", "thinking": "...", "signature": "..."}` or `{"type": "redacted_thinking", "data": "..."}`. Drives the real thinking-disclosure path end-to-end with no live Anthropic key (M16 F10 L05).
- `"stream_chunks"` — a LIST of strings; when set (non-empty), `stream()` yields each list element as one streaming chunk in order. When unset/empty, the provider is non-streaming (default). (Not a chunk *count* — the values are the literal chunk texts, e.g. `["Hello, ", "world", "!"]`.)
- `"delay_ms"` — simulated latency in milliseconds (default: `0`, so tests stay fast): awaited once before `complete()` returns, and *between* successive `stream_chunks`. Useful interactively to exercise the client-side "thinking…" indicator.
- `"input_tokens"` — `input_tokens` value emitted in `TokenUsage` for each turn (default: `0`). Set to a positive integer in tests that exercise the telemetry overlay or the `last_usage` persistence path (M10 F06); the default preserves all existing test expectations.
- `"models"` — a LIST of model-id strings returned by `GET /api/providers/{id}/models` for this provider (default: `["mock-default"]`). Read by the API layer (`interfaces/web/api.py`), not by `MockProvider` itself — so it shapes the Studio/Administration model picker, not the chat response.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled

### Stub connector test endpoints (Mission 23 Flight 2)

`THE_ONE_STUB_TEST_ENDPOINT=1`, set **together with** `THE_ONE_DEV_MODE=true` (both gates, not either alone), unlocks the `"stub"` connector type end-to-end: it's admitted into `GET /api/connectors/types` (so it's creatable in Studio), a lifespan-startup hook registers the in-process `StubPlugin` (`the_one/connectors/stub.py`) under type `"stub"`, and the two test-seam routes `POST /api/_test/stub/inbound` / `GET /api/_test/stub/outbound` (`interfaces/web/api.py`) stop 403-ing — they inject/observe messages against a stub connector's live listener without a real chat platform. Dual-gated like the purge-sweep seam (real LLM calls and tool execution, not inert metadata) — never set on an instance other than a disposable dev/test one. Never touch port 8484 or the operator's default data directory when this is set. See `the_one/connectors/README.md` "Test seams" and `tests/behavior/stub-connector-round-trip.md` for the end-to-end usage.

### Discord test endpoint + live HAT env conventions (Mission 23 Flight 3)

`THE_ONE_DISCORD_TEST_ENDPOINT=1`, set **together with**
`THE_ONE_DEV_MODE=true` (both gates, same shape as the stub gate above,
but its own name — see `the_one/agents.md`'s `risk-tiered-test-seam-gating`),
unlocks `POST /api/_test/discord/sever`: a controlled-disconnect test seam
that abruptly kills a live Discord connector's gateway websocket via the
optional `sever_for_test` client hook, never a production kill switch. See
`the_one/connectors/README.md` "Test seams" for the route's error
taxonomy and `tests/behavior/discord-live-round-trip.md` step 6 for the
resume proof it drives.

The **live HAT** (Hardware-Approximation Test) driver-bot env contract
lives in `tests/behavior/.env.hat.example` (copy to `tests/behavior/.env.hat`,
gitignored via the repo `.gitignore`'s `*.env.hat` pattern — never commit
real tokens): `THE_ONE_HAT_DRIVER_TOKEN` (a second bot, separate from the
connector's MAIN bot, that acts + observes over Discord REST),
`THE_ONE_HAT_GUILD_ID`, `THE_ONE_HAT_TEST_CHANNEL_ID`,
`THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`, `THE_ONE_HAT_UNTRACKED_CHANNEL_ID`.
This simplifies the pre-reset `discord_hat` convention's N-sender-bot-token
list (`THE_ONE_HAT_BOT_TOKENS`) down to one driver bot — the behavior
test's apparatus only needs to post and read back its own sends via REST,
never to differentiate multiple senders. See the `.env.hat.example` file's
own comments for bot-provisioning notes (real browser required — the
Developer Portal's hCaptcha/MFA block automation; the driver bot does NOT
need Message Content intent, the MAIN bot does).

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

**Destination router (`App.router`, M25 F2 L3)**: the app is four destinations — Chats, Agents, Library, Settings — over the chat/studio/admin area modules, routed by `static/js/router.js` with destination-first hashes (`#chats[/{id}]`, `#agents[/{name}[/{tab}]]`, `#library/{knowledge|mcp|connectors}[/{id}]`, `#settings/{general|providers|tools|knowledge-indexing|design-language}[/{id}]`; `~new` is the reserved create segment). Legacy `#chat`/`#studio`/`#admin` hashes redirect (replaceState). User intents call `App.router.go(route)` (guarded, pushes history, hydrates); area-internal canonicalisation calls `App.router.sync('<area>', sub)` (replace only, never guards, dropped when it would move the user). The one leave guard is `App.nav` (`static/js/nav.js`, M25 F2 L5): per-area dirty sources with a teardown-only `discard`, a synchronous clean fast path in the router adapter (never promisify it), one `beforeunload`, and a bubble-phase `a[href^="#"]` interceptor. See `the_one/agents.md` "Hash routing — the router" ("Leave guard (`App.nav`)").

**App shell (M25 F2 L6)**: no top bar. `<div class="app-shell-row">` is a flex row of `#app-rail` (the `App.ui.rail` workbench rail: four plain `<a data-testid="rail-{chats|agents|library|settings}">` links, hrefs kept current through `App.router.onCommit`), `<aside id="app-sidebar">` (hidden on Agents; 240px, 200px below 1280px; 1024px is the supported minimum) and `<main id="main-content">`. Browser tests open a destination with `_nav.open_destination` (the rail). `.visually-hidden` is a global utility in `components.css`. See `the_one/agents.md` "App shell — invariants".

**Client data store (`App.store`, M25 F2 L7)**: `static/js/store.js` is the shared client cache for `agents` and `providers` (`get(name,{force})` returns a copy and rejects on failure; `peek`, generation-safe `invalidate`, `subscribe`). Read those two lists through it, never a literal `fetch('/api/agents')`/`('/api/providers')`, and call `App.store.invalidate(...)` after any mutation of them. See `the_one/agents.md` "Client data store (`App.store`)" for the invalidation map and freshness bound.

**Control library (`App.ui`, M25)**: new UI controls are factories in `the_one/interfaces/web/static/js/ui/` (ES5, native elements, no HTML-string sinks, caller-supplied `testid`). Every factory needs a demo on the dev-mode `#admin/design-language` page, a row in `docs/ui-control-inventory.md`, and engine-parametrized contract tests (Chromium + WebKit); `tests/test_ui_control_inventory.py` enforces the first two. See `the_one/agents.md` "Control library (`App.ui`)" and "UI test apparatus".

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

**UI test apparatus (M25 F1)**: library contract tests run in Chromium and WebKit through the `engine_page` fixture (`tests/browser/_ui_engines.py`); a WebKit launch failure skips locally and fails under `THE_ONE_REQUIRE_WEBKIT=1` (CI). `bash scripts/setup-webkit-userland.sh` provisions WebKit's host libraries without sudo; `scripts/webkitgtk_probe.py` (system `/usr/bin/python3`, dev instance on 8485 only — it refuses 8484 and the default data dir) checks pages in the real desktop engine. See `the_one/agents.md` "UI test apparatus".

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

**WSL2 mirrored networking (`THE_ONE_TEST_NETNS=1`).** On WSL2 hosts with mirrored networking, Windows' rotating temporary IPv6 addresses make Chromium's network-change notifier abort in-flight requests, even to 127.0.0.1, so browser lanes fail 1-4 random tests with `net::ERR_NETWORK_CHANGED`. Set `THE_ONE_TEST_NETNS=1` and `scripts/run-tests.sh` runs pytest inside an isolated loopback-only network namespace (`unshare -rn`, `lo` brought up; process-group kill and env passthrough unchanged). It fails loudly (exit 2) if `unshare -rn` or `ip` is unavailable rather than falling back. CI (containers) is unaffected.

**Per-area browser test lanes** (M17 F5; re-mapped to the four destinations in M25 F2). The full browser suite runs ~13min, so a verification pass that only touches one UI area shouldn't have to pay the whole tax. `scripts/run-tests.sh` accepts a `--lane {chats|agents|library|settings|shared}` selector that runs just that destination's slice:

```bash
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats      # Chats slice
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents     # Agents slice (Studio agent editor)
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane library    # Library slice (knowledge, MCP servers, connectors)
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings   # Settings slice (admin / providers / tools)
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane shared     # cross-cutting slice
# Extra pytest args pass straight through, e.g. add `-x` or `-q`:
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents -q
```

**Aliases** (the pre-M25 names still work and expand to the union of their lanes): `chat` = `chats`, `studio` = `agents` + `library`, `system` = `settings`.

Each lane runs independently green under the venv python (always pass `PYTHON=.venv/bin/python`). The full suite still runs exactly as before (`make test-browser`, no `--lane`).

- **`chats`** — `test_flow_chat*`, `test_flow_markdown_chat`, `test_flow_new_chat`, `test_flow_streaming`, `test_flow_context_overlay_thresholds`, `test_flow_usage_restore`
- **`library`** — an **explicit file list**: `test_flow_studio_knowledge_inventory`, `test_flow_studio_mcp_editor`, `test_flow_studio_mcp_navigation`, `test_mcp_test_connection_button`, `test_studio_connector_editor`. A new Library-owned test file must be added to `library_pat` in `scripts/run-tests.sh`.
- **`agents`** — the old studio globs (`test_flow_studio_*`, `test_studio_*`, `test_mcp_*`, `test_flow_agent_*`) **minus** the `library` list (so the agent-editor tabs, e.g. `test_flow_studio_knowledge_attach` and `test_studio_mcps_tab`, stay here)
- **`settings`** — `test_flow_admin_*`, `test_flow_provider_*`
- **`shared`** — the **complement**: every browser test file not claimed by the four destination lanes (smoke, theme sync, markdown, keyboard, hash routing, oauth modal, dirty-confirm, cross-area gate, picker, seeders, app fixture, …)

Lanes are hand-rolled basename globs over `tests/browser/` — no new deps, no per-test markers. Because `shared` is defined as the complement, the five lanes' union is *always* exactly the whole browser suite and no test file can be orphaned — a newly added `tests/browser/test_*.py` lands in `shared` until it is given an area glob in `scripts/run-tests.sh`. (Union verified by file list and by test count: the five lanes collect the same tests as `-m browser tests/browser/`, with no file in two lanes.)

**Browser tests navigate through `tests/browser/_nav.py`, never raw route hashes** (M25 F2 L1). A browser test states a route in the **new** scheme (`"settings/providers/~new"`, `"agents/<name>/tools"`, `"library/mcp/<id>"`, `"chats"`) and `_nav.goto` / `expect_route` / `set_route` / `current_route` / `wait_for_route_prefix` / `href` / `open_destination` map it to whatever the app serves (one `SCHEME` switch). Ids go through `_nav.seg()` (JS `encodeURIComponent` parity). `tests/test_nav_helper.py::test_no_raw_route_hashes_in_browser_tests` (an `ast` guard, runs in `make test-unit`) fails on a raw `#studio…`/`#admin…`/`#chat…` hash or a top-bar selector in any `tests/browser/test_*.py`, except in the deliberate `_nav.LEGACY_URL_TESTS` set (tests that keep a raw legacy `goto` to prove the redirect) — and, at file level, the router's own contract tests `tests/browser/test_router_*.py`. `SCHEME` is `"new"` since the router landed.

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

**Do not guess the default data directory — read it.** It is
platformdirs-derived (`the_one/config.py::_default_data_dir`), NOT a literal
path, and it differs by platform. Print it with:

```bash
python -c "from the_one.config import settings; print(settings.data_dir)"
```

A check against a hardcoded guess is not a check: a stale guess returns a clean
result whether or not the real directory was just written to. (Squawk 0084 — an
earlier version of this section named `~/.the-one`, which does not exist, so every
"production untouched" verification against it passed unconditionally. A
credential rotation reached the real directory before anyone noticed.) To confirm
which directory a *running* instance owns, read that process's own
`/proc/<pid>/environ` rather than assuming.

Always drive a **dedicated dev instance** instead — a non-default port
AND a scratch data directory, together, every time:

```bash
THE_ONE_PORT=8485 THE_ONE_DATA_DIR=/tmp/the-one-behavior-test-scratch make up
```

Port alone is not enough — an instance on 8485 that still points at the
operator's default data directory shares the same credential
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

This project uses [Flight Control](https://github.com/msieurthenardier/mission-control) via the `mission-control` Claude Code plugin. Skills are invoked as `/mission-control:<skill>` from this project's root.

**Before any mission/flight/leg/squawk work, read these files in order:**
1. `.flightops/README.md` — What the flightops directory contains
2. `.flightops/FLIGHT_OPERATIONS.md` — **The workflow you MUST follow**
3. `.flightops/ARTIFACTS.md` — Where all artifacts are stored
4. `.flightops/agent-crews/` — Project crew definitions for each phase (read the relevant crew file)

**Flight Director role.** This session — the one the human talks to — is the Flight Director: it runs the Flight Control skills, plans directly, and orchestrates spawned crew, and never edits source itself. Spawned agents are crew, never the Flight Director. When a human says a leg is ready to implement, invoke `/mission-control:agentic-workflow`. Do not read the leg spec, plan execution steps, or execute commands directly — the skill orchestrates separate Developer and Reviewer agents and emits `[HANDOFF:...]` and `[COMPLETE:...]` signals. Planning skills (`/mission-control:mission`, `/mission-control:sortie`, `/mission-control:flight`, debriefs, `/mission-control:routine-maintenance`) produce artifacts only and never modify source files.

**Spawned agents** (Developer, Reviewer, Architect, Executor, Validator) do not have the Skill tool. Everything they need is in `.flightops/`; they must not try to load plugin skills.

**Methodology drift.** A SessionStart notice from the plugin means this project is behind the installed plugin version. Recommend `/mission-control:preflight-check` or `/mission-control:init-project` to bring it current; never apply migrations by hand.
