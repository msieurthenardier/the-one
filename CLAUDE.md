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
ruff check the_one/ tests/ scripts/ evals/
ruff format the_one/ tests/ scripts/ evals/
```

**Lint/format gate.** Run `pre-commit install` once to activate the pre-commit hook (`pipx install pre-commit` first if you don't have it; it's also in the `[dev]` extra). The same `ruff check the_one/ tests/ scripts/ evals/` + `ruff format --check the_one/ tests/ scripts/ evals/` run in CI on every push to `main` (Concourse, `ci/tasks/lint.yml`). The gate exists to stop ruff-baseline drift — so a future maintenance cycle doesn't re-discover its absence. CI now runs on local Concourse; the GitHub Actions `lint.yml` and `test.yml` are `workflow_dispatch`-only break-glass fallbacks — see `ci/README.md` for the full topology.

## Local dev (host-native)

The app runs host-native via `the-one serve` (console script → `uvicorn.run(app, settings.host, settings.port)`, no `--reload`). For day-to-day dev use `make up` to launch it backgrounded against the repo venv (writes `.the-one.$(THE_ONE_PORT).pid` + `.the-one.$(THE_ONE_PORT).log`, both gitignored — so the default instance writes `.the-one.8484.pid` and `.the-one.8484.log`). A dev instance started on another port (e.g. `THE_ONE_PORT=8485`) keeps its own PID/log files, which is what makes `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> make down` safe against the default instance. Because `serve` has no `--reload`, **Python source edits take effect on `make restart`** — there is no live hot-reload for imported code (static JS/CSS is a different story; see below). The test suite spawns its own uvicorn subprocess; that path is independent of the `make up` server at port 8484.

```bash
make up                     # start the-one host-native in the background (PID + log) + verify
make restart                # restart to pick up source edits (no --reload) + verify
make down                   # stop (by PID)
make logs                   # tail the host log file (.the-one.$(THE_ONE_PORT).log, e.g. .the-one.8484.log)
make reset-db CONFIRM=1     # wipe the host data dir + restart. Gated to prevent accidental data loss.
make test                   # default tests (the unit tier under pyproject addopts)
make test-unit              # unit tests only
make test-browser           # all browser lanes, 3 at a time (run-tests.sh --parallel 3)
make gate                   # the full local gate: test-unit, then test-browser (never concurrent)
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

**LLM layer — `anthropic-plan` provider type (M19)**: chats on a Claude Pro/Max subscription via OAuth sign-in from Library › Model providers (popup or copyable URL + code paste) — no API key ever; tokens live Fernet-encrypted in `llm_providers.secrets` (stripped from every response — `oauth_active` is the UI signal) and auto-refresh via the per-provider single-flight credential source in `the_one/llm/plan_credentials.py`. A sibling `anthropic-plan-token` type ("Claude Plan (Token)", sortie 03) takes a token pasted from `claude setup-token` instead, stored encrypted in `api_key` with a server-stamped `token_set_at` that drives an "expires around" line in the editor; the OAuth type is labelled "Claude Plan (OAuth)", and both translate a plan's bare `429 "Error"` into a clearer error.

**Self-configuration surface (M21 F01 L02-L03)**: an agent's Studio editor gains a sixth "Self-configuration" tab, off by default. Enabling it mints a per-agent credential and attaches a loopback MCP source through which the agent can act on its own configuration — a real `streamable-http` source, so the operator's existing per-source and per-tool checkboxes on the MCPs tab govern it exactly like any other MCP server (the row there is locked checked+disabled; only the Self-configuration tab can enable/disable it). Four tools: `get_my_configuration` / `describe_my_capabilities` (read), and `update_my_description` / `update_my_system_prompt` (write, M21 F01 L03) — each write tool takes `text` (the new value, whole-value replacement — no append or partial edit) and `apply`, either `"next_turn"` (the change lands when the agent's current turn in this conversation ends — never mid-turn) or `"next_session"` (this open conversation is untouched; the change is visible the next time the conversation is rejoined). No tool takes a field name, so no other part of an agent's configuration is reachable through this surface. **Operator oversight (M21 F02):** every self-revision is recorded in the `agent_revisions` log (L01), and each agent carries an operator-owned `self_revision_requires_approval` flag (L02, a v35 `agents` column, default off, unreachable by the agent). When approval mode is on, a proposed revision is held in the queue as `pending` instead of applied; the operator approves (fail-closed against staleness) or dismisses it from the Self-configuration tab. New endpoints under `/api/agents/{name}/self-configuration`: `PUT /approval-mode`, `GET /revisions`, `GET /revisions/pending-count`, `POST /revisions/{id}/approve` (`?override=true` to overwrite a drifted value), `POST /revisions/{id}/dismiss`. **Restore (L03):** `POST /revisions/{id}/restore` (`?side=proposed|base`, default `proposed`) rolls a field back to any earlier value it held — operator-direct, so it applies immediately regardless of approval mode and is logged as a new `applied`/`restore` row (never queued). The target must be an `applied` revision (a value the field actually took); a non-applied target is refused 409. `side=base` reinstates the target row's before-image — the only way to reach the original pre-first-revision value. There is no agent-facing restore tool. See `the_one/agents.md` "Self-configuration surface contract" and `SECURITY-MODEL.md`'s "Self-configuration surface" for the credential-scoping, approval-mode, restore, and residual-risk detail.

**Knowledge bases (M24)**: `POST /api/knowledge-bases/{kb_id}/items` with `type: "folder"` registers a folder on disk — operator-only (no agent-facing route creates items) and read with the app's own privileges, no allowlist; a folder that equals, contains, or lies inside the application data directory is refused with 422 (Flight 4); a `file` item lying inside it is refused with 422 too (squawk 0147), since the app's own database and index live there. Item routes (`GET`/`POST /items`, `GET`/`DELETE /items/{item_id}`, `POST /items/{item_id}/retry`) plus four Flight 3 routes: `GET /status` (per-KB item-status counts, each folder's walk status and watch state, chunk count, indexer state), `POST /reindex?scope=changed|all` (202; `changed` just re-walks, `all` also re-embeds every file), `GET /items/{item_id}/chunks` (paged, `seq` order), `GET /items/{item_id}/source` (extracted text read-back with a freshness flag). Indexing itself runs in a background worker (`IndexingManager`, one per knowledge base) started by the web app's lifespan; a killed or restarted process resumes rather than restarts — any item stranded mid-index (`indexing`) is requeued to `pending` at startup and at the top of every worker pass. **Change monitoring (M24 F04)**: a registered folder is kept current with no operator action — a per-folder filesystem watcher (native OS change notification, one dedicated thread per folder, at most 64 concurrent) that only ever triggers a re-index pass, backed by a periodic reconciliation walk (every 5 minutes by default) that is the actual source of truth and the only path that works on every platform. Both are operator-configurable, live, under `monitoring` in `GET`/`PUT /api/knowledge-settings`; `GET .../status`'s `folders[]` entries carry `watch`/`watch_error`. `the-one doctor` gained a ninth gate, `file watcher`, proving the native notifier loads (and, when frozen, round-trips a real change); a tenth, `window chrome` (M25 F5 L3), proves the DWM path loads on Windows (skipped elsewhere); an eleventh, `time zones` (M28 F1 L1), runs on every host and proves the bundled tzdata zone data and the exact date-line strings; a twelfth, `mcp sdk` (M29 F1 L2), runs on every host and proves the `mcp` 2.x import closure and a `truststore` SSL context. See `the_one/agents.md`'s "Knowledge storage"/"Knowledge indexing"/"WatchManager" sections for the full pipeline and manager contracts.

**Agent-facing retrieval (M24 F5)**: an agent reaches its attached knowledge bases (`AgentConfig.kb_ids`) through one `kb__{slug}__search` tool per attachment, built per agent by `KBToolProvider` and registered by `AgentFactory` beside the MCP tools. `the_one/knowledge/retrieval.py::search` fuses the vector store's semantic hits with FTS5's keyword hits by reciprocal rank, with one result slot reserved for a keyword-only exact-term hit the embedding model would otherwise rank out of the returned set — so a query naming an identifier the model ranks poorly still surfaces it. The tool degrades honestly rather than failing silently: a stale, busy, or otherwise unavailable vector index falls back to keyword-only results (and the reverse for a keyword-index failure), each surfaced as one line above the hits. `search_tools` discovers these tools under a `kb:<slug>:` group, matched purely through the tool's own name and description (a knowledge base gets no separate `source_index` entry — see `the_one/agents.md`'s "Knowledge retrieval" section for why one would be inert). Attachment is authorization: an agent can only ever reach the knowledge bases the operator attached it to, and no agent-facing route creates or attaches one.

**Studio surfaces + operator-facing search (M24 F6)**: `GET /api/knowledge-bases/{kb_id}/search` (query param `q`, `limit: int = Query(10, ge=1, le=20)`, 404 on an unknown `kb_id`) wraps `retrieval.search` for a human caller — read-only, returning `{hits: [...], degraded: str | null, indexer: str}`; it sits behind the same credential gate as every other route (see SECURITY-MODEL.md). Studio's **Knowledge section** (since M25 F3, the Library list's Knowledge bases group) is the global inventory (create/rename/delete a knowledge base, register and inspect folders, read items/chunks/source, and preview search through the route above); the agent editor's **Knowledge tab** is attach-only — a per-knowledge-base row toggle (mirroring the MCPs tab's pattern) that also renders the knowledge base's derived `kb__…__search` tool name, served by the backend (`compute_tool_names`, promoted from a private helper) rather than recomputed in JavaScript. Administration gained a **Knowledge** panel (now `#settings/knowledge-indexing`) for the app-wide `chunking`/`monitoring` settings — `embedding` and `vector_store` render read-only, each with its reason stated on screen: the embedding model is pinned (there is no operator path to change it — see DD-7 in `missions/24-knowledge-bases/flights/06-studio-surfaces/flight.md`), and the vector-store record is written by the app, not chosen by the operator.

**Mission close, non-UI defect closure (M24 F7 L1)**: the vector store now has a shutdown hook — `the_one/vectors/__init__.py::close_vector_store()` closes the process-wide store if one was built (never builds one just to close it) and is called unconditionally from the lifespan, between the indexing-manager drain and `close_connection()`. It skips any knowledge base whose most recent `IndexingManager.stop()` took the cancel fallback (`IndexingManager.cancelled_kb_ids()`, DD-3a) — flushing one right after would race a still-running mutation and tear the index; the lost write is recovered by re-indexing instead. Separately, `AgentFactory.create()`'s `kb_tools` loop now reconciles a stale `disabled_tools` entry against a knowledge base's `kb_id` (not just its current derived name) — closes the hole where a disable made while an agent was attached silently stopped applying after the knowledge base was detached, renamed, and reattached. See `the_one/agents.md`'s "Vector-store shutdown hook" and "DD-13" blocks for the full contract.

**Mission close, inventory freshness (M24 F7 L2a)**: `GET /api/knowledge-bases/{kb_id}/status` gains two additive keys. `"content_freshness"` is `MAX(indexed_at)` across the KB's `file` items — it moves **iff** a file item actually re-indexes (never on a no-op walk pass, unlike a folder item's own `indexed_at`, which advances on every completed walk regardless of change) — and `studio.js::knowledgeItemsSignature` now folds it in, so a content-only edit to an already-indexed file (previously invisible to the poll) now triggers the `/items` re-fetch that repaints the item row's new `Indexed: …` freshness line. Each `folders[]` entry also gains `"skipped_dirs"`/`"skipped_entries"` — the last completed walk's counts, persisted via `AppMetadataRepository` under a key from the new `the_one.knowledge.settings.walk_skip_counters_key()` helper (one shared implementation across the write site, the read site, and both delete-path cleanup sites, since a kv key sits outside `kb_items`' FK cascade). `AppMetadataRepository` gained a `delete(key)` method. Separately, squawk 0087 is fixed: `KBItemRepository.list`/`.list_children`/`.list_folders` now order `..., path_or_url` ascending, so a tied `created_at` batch (a folder walk inserting every file in one pass) reads back in stable, walk-matching order. See `the_one/agents.md`'s "`get_kb_status` gains two ADDITIVE signals" block for the full contract.

**Mission close, confirm-lapse cue (M24 F7, `confirm-lapse` leg)**: the shared two-step `App.confirmDelete` helper (`the_one/interfaces/web/static/js/ui/confirm.js`) now distinguishes a timed-out arm from a never-armed control. A `.confirm-lapsed` CSS class is added ONLY by the arm timer's own expiry callback (never by `revert()` itself, which also runs on a successful commit and on a credential-rotation success path that must not be mislabeled "lapsed"), and is cleared unconditionally at the top of every `confirmDelete` call — arm or commit alike — so a returning operator always starts from a clean visual slate. Feedback-only: the arm/commit decision still depends solely on the pre-existing `.confirm-delete` class; `.confirm-lapsed` never gates it. Applies uniformly across all 13 `App.confirmDelete` call sites, with no per-call-site opt-in. Closed squawk 0088's third invariant (`renderAllItems` must never rebuild a folder's armed `<summary>` node) along the way, with a falsified-and-reverted regression test proving the pin. See `the_one/agents.md`'s "confirm-lapse cue" section for the full contract and the squawk for the invariant-pinning test.

**Mission close, Windows vector-store measurement (M24 F7, `measurement` leg)**: `ci/tasks/windows-vector-bench.yml` is a new ad-hoc (not part of the standard five-lane CI matrix) Concourse task that runs `scripts/bench_vector_store.py` on the `platform: windows` worker for one synthetic-corpus rung at a time (`-v bench_n=<N>`, no default — an unset rung size fails loudly rather than running silently at the wrong size). It re-confirms the flush-cadence constants from Flight 3 against measured data up to a 500k-vector rung (the operator's stop-at-500k decision; the 1M rung was not run — its cost/benefit was projected from two independent anchors instead) and records per-cell `usearch_acceleration` so a stale/unaccelerated Windows backend cannot silently produce numbers for a build the product does not ship. `scripts/sweep_fusion_constants.py` (new) is the accompanying `RRF_K`/`candidate_k` sweep that closed the mission's fusion-balance open question as "fixed by evidence, not tuned" (DD-4) — no product constant changed. See `the_one/agents.md`'s vector-store bench section and `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`'s "Leg measurement (3)" for the full ladder, band declarations and verdicts.

Full module map, layer internals, tool-authorship contract, constraint surfaces (Filesystem/Execution/Web Configs), cross-Config dispatch, PTY session lifecycle, MCP F2/F3 contracts, MCP error translation, operator workflows — all in `the_one/agents.md`. Don't duplicate that material here.

## Desktop launcher (`the-one app`)

`the_one/interfaces/app.py` (M15 F4). `uvicorn.Server` on a **daemon thread** + `pywebview` on the **main thread**. The shared `_graceful_shutdown(server, thread)` helper sets `server.should_exit = True` then joins the thread (60s timeout); **no-op when `server is None`** (window-only client — attached to an existing server, owns nothing to drain). `_select_port` uses a connect-probe + startup-retry to classify the configured port as: free (start new server) / ours-by-version (attach a window only) / foreign (bind-0 a free port). `_webview_available` probes the Linux WebKit2 typelib via `gi.require_version` without importing Gtk/WebKit2 (importing can touch a display connection and hang headless). `pywebview` is the optional `[gui]` extra — `import webview` is **lazy** inside `run()`, NOT at module top-level; the base install is GTK-free.

M15 F6 added the desktop-shell module (`the_one/interfaces/desktop/`): **close-to-tray** (× hides the window; the process keeps running), **Quit from the tray menu is the real exit**, **single-instance focus** via `POST /api/window/focus` (second launch focuses the existing window instead of spawning a new one), and **window-state persistence** (`{data_dir}/window-state.json` — size + position restored on next launch, clamped to visible screen bounds and floored at 640×360; a first launch opens at 1440×900 fitted to the work area, centred by the OS).

M15 F7 refactored into the **`DesktopSession`** lifecycle class (`the_one/interfaces/desktop/shell.py`) and added: a **launch splash** (small frameless branded window shown during the uvicorn boot wait, dismissed once the main window is shown and has loaded); a **native OS-framed main window** (`frameless=False`, `resizable=True` — native title bar, min/max/close, resize; the native × hides to tray via the F6 `_on_closing` path); and a **brand `.ico`** (256/128/64/48/32/16 px, generated by `packaging/windows/regenerate_icon.py`) embedded in the windowed exe. See `the_one/agents.md` "Desktop launcher" for the full contract reference and the pywebview/WebView2 frameless footgun note.

M25 F5 L2 added the **tinted title bar** (`the_one/interfaces/desktop/chrome.py`, Windows 11 only; the frame stays native): the page's `theme.js` posts its resolved theme to `POST /api/window/chrome` (desktop webview only; `GET` reads back the state and each DWM HRESULT), and the shell tints the caption, border and title text from the workbench tokens (pinned by a test), dimming the title text when the window is inactive. The theme persists in `{data_dir}/window-chrome.json` so the next launch's first frame (the themed splash, the main window's `background_color`, created hidden, tinted, then shown) is already in the right colours; a first launch uses the OS app theme. Every DWM apply runs on the UI thread through `BeginInvoke` with a 2s bounded wait. See `the_one/agents.md` "Window chrome (M25 F5)".

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

### Test seams at a glance

Every `/api/_test/*` route needs `THE_ONE_DEV_MODE=true` **and** its own flag, checked at request time (403 otherwise). Disposable dev/test instances only.

| Route | Flag (set to `1`) | Purpose |
|---|---|---|
| `POST /api/_test/stub/inbound`, `GET /api/_test/stub/outbound` | `THE_ONE_STUB_TEST_ENDPOINT` | inject/observe messages on a stub connector |
| `POST /api/_test/discord/sever` | `THE_ONE_DISCORD_TEST_ENDPOINT` | kill a Discord gateway websocket (resume proof) |
| `POST /api/_test/purge-sweep` | `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT` | fire the daily chat-history purge sweep |
| `POST /api/_test/oauth/pending` | `THE_ONE_OAUTH_TEST_ENDPOINT` | register a pending OAuth flow for the callback tests |

### Stub connector test endpoints (Mission 23 Flight 2)

`THE_ONE_STUB_TEST_ENDPOINT=1`, set **together with** `THE_ONE_DEV_MODE=true` (both gates, not either alone), unlocks the `"stub"` connector type end-to-end: it's admitted into `GET /api/connectors/types` (so it's creatable from the Library list's Add menu), a lifespan-startup hook registers the in-process `StubPlugin` (`the_one/connectors/stub.py`) under type `"stub"`, and the two test-seam routes `POST /api/_test/stub/inbound` / `GET /api/_test/stub/outbound` (`interfaces/web/api.py`) stop 403-ing — they inject/observe messages against a stub connector's live listener without a real chat platform. Dual-gated like the purge-sweep seam (real LLM calls and tool execution, not inert metadata) — never set on an instance other than a disposable dev/test one. Never touch port 8484 or the operator's default data directory when this is set. See `the_one/connectors/README.md` "Test seams" and `tests/behavior/stub-connector-round-trip.md` for the end-to-end usage.

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

## Prompt evals (Mission 30)

`evals/` is a hand-rolled developer tool, not product code (nothing under `the_one/` imports it): it runs declared scenarios through the app's real agent factory, prompt assembly and agent loop, in a scratch data directory and a scratch home, against Claude Haiku 4.5 (plan token) and a local `gpt-oss:20b` (Ollama), scores each run with program checks, and reports pass rates with Wilson intervals, the platform text's size by part, and the gate results that decide whether a prompt change may land. Run it with `make eval ARGS="<subcommand> ..."` (`run`, `measure-prompt`, `report`, `baseline`, `derive-bars`, `compare`; `make eval ARGS="run --help"`). Full usage, the scenario format, the check vocabulary, outcomes, statistics, gate rules, token measurement and the file layout are in `evals/README.md`.

- **Never production.** It refuses to start when its scratch data directory would overlap the real default data directory or a configured `THE_ONE_DATA_DIR`, never touches port 8484, switches `HOME` to the run directory, and disables the execution tools. It makes real model calls and burns plan quota, so it is local-only.
- **The plan token** lives in `~/.config/the-one-evals/plan-token` (override with `--plan-token-file`); it is read after the guard, kept in memory, and redacted from every file and log line.
- **Out of CI and the gates.** `make test-unit` runs only the offline `tests/test_evals_*.py` (scripted provider, injected counter, no network). CI does not install the `[evals]` extra (`tiktoken`, the reference tokenizer); `make eval ARGS="measure-prompt"` needs `pip install -e ".[evals]"` and downloads the `o200k_base` encoding once into `evals/.cache/tiktoken` (gitignored).
- **Convention (current baseline `evals/baselines/m30-platform.json`).** A change to platform prompt text lands with an eval run compared against that baseline, including its token cost (`measure-prompt`, then `compare --baseline evals/baselines/m30-platform.json`). Platform prompt text is: `the_one/agent/platform_prompt.py`, the rules and notes layers in `the_one/db/_rules.py` and `the_one/db/_notes.py`, the date-line templates in `the_one/time_zones.py`, and the starting tool descriptions. Evals stay out of CI and the test gate. A changed scenario set needs a same-prompt re-baseline (`baseline` on the unchanged prompt), never a comparison across scenario sets. `m30-platform` size targets use ratio 1.0 (`derive-bars --size-ratio 1.0`: no larger than the baseline). Run directories (`evals/runs/`) are gitignored; baselines (`evals/baselines/*.json`) are committed, the recorded exception to the no-golden-files preference.

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

**MCP client on the `mcp` 2.x SDK (Mission 29 F1)**: the MCP client, its OAuth sign-in, the self-configuration loopback server and the MCP test fixtures run on `mcp==2.3.0` (pinned exactly; soak waived by the operator), which is built on `httpx2`. Operator-facing facts: (1) everything under `the_one/mcp/` and the two OAuth flow drivers in `interfaces/web/api.py` use `httpx2` (an AST guard, `tests/test_mcp_httpx_guard.py`, bans `import httpx` there), and `httpx2` verifies TLS against the **OS trust store**, not `certifi`; `SSL_CERT_FILE`/`SSL_CERT_DIR` override it (SECURITY-MODEL.md "MCP client transport"); (2) sign-in detection no longer relies on an HTTP 401 exception (2.x swallows it): a response hook on the transport's client records MCP POST statuses and `MCPClient` reads the record (`the_one/agents.md` "MCP error translation"); (3) `GET /api/oauth/callback` forwards an optional RFC 9207 `iss`; (4) four deliberate, plain-error behaviour changes: a single SSE event over 1 MiB fails the call, a cross-origin redirect is not followed, the authorization-server issuer must match, and a stateless server's mid-use 404 no longer self-heals; (5) `the-one doctor` gained a twelfth gate, `mcp sdk`, which runs on every host and is asserted by both Windows lanes; (6) the OAuth consent popup poll in the MCP editor now waits up to 2 minutes (was 15 s) for a sign-in to land, inside the server's 10-minute pending-flow TTL. Self-configuration refusals are `ToolError`-typed (`SelfConfigPermissionError` / `SelfConfigValueError`) so their one-line reason survives 2.x. **Automatic protocol negotiation (M29 F2)**: the client tries the newest protocol (2026-07-28) first and falls back to the older handshake on its own, so a server on 2026-07-28 shows that version in the MCP editor and an older server keeps working with no setting to change. The negotiated revision is remembered in memory per source (cleared when the source is edited, deleted or reset), so after the first connect in a run an older server adds no delay. Test connection always re-negotiates and does not remember the result when the form differs from the saved server. A server that answers the connection probe with an unexpected status (such as 400) is now tried through the full client rather than refused, so 2026-07-28-only servers can be tested and signed in to. See `the_one/agents.md` "MCP F2 Client Foundation". **Honest sign-in (sortie 04)**: a 401 from a source with operator-supplied headers, no `resource_metadata` and no OAuth provider is `MCPCredentialsRejected` (an `MCPConnectionError`: "the server rejected the configured credentials", no login button, no `oauth` posture) through the single `MCPClient._signin_signal` factory and Test connection paths (a)-(c); a sign-in this window started shows an "Open sign-in page" / Copy link block (`App.consentLink`) in chat and the MCP editor (chat shows it only for a flow its own "Log in" click started; any other consent URL, such as the SDK's in-band flow, is ignored and "Log in" always starts a fresh flow) (http(s) addresses only: any other scheme renders a plain notice and is never opened, linked or navigated to, via `App.consentLink.isSafeUrl`), and a `null` from `window.open` (always the case in the desktop webview, `App.desktop.isWebview()`) no longer ends the flow. See `the_one/agents.md` "MCP error translation" and "Desktop launcher".

## Conventions

- Python 3.11+, async throughout
- ruff for linting (rules: E, F, I, N, W) and formatting, line length 100
- Tools return strings, errors are caught and wrapped by the agent loop
- LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others

**Destination router (`App.router`, M25 F2 L3)**: the app is four destinations — Chats, Agents, Library, Settings — over the chat/studio/admin area modules, routed by `static/js/router.js` with destination-first hashes (`#chats[/{id}|/~new/{agent}]`, `#agents[/~new|/{name}[/{tab}]]`, `#library` (Library's own route, the start page; a bare `#library/{providers|knowledge|mcp|connectors}` is an alias that redirects to it, and nothing produces one), `#library/{providers|knowledge|mcp|connectors}/{~new|{id}}` (providers are "Model providers"), `#settings/{appearance|date-and-time|prompts|encryption|tools|knowledge-indexing}`, with the item route `#settings/tools/{name}` (`#settings/providers…` and `#admin/providers…` are unknown routes, dropped with no redirect); `~new` is the reserved create segment, and an agent name's leading `~` is written `%7E`; `#chats/~new/{agent}` is the pending new chat, M25 F4 L3b: `href({destination:'chats', create:true, agent})` builds it, bare `#chats/~new` folds to `#chats`). Legacy `#chat`/`#studio`/`#admin` hashes redirect (replaceState); `#settings/general` (any suffix) is an alias for `#settings/appearance` since M25 F3 L5a, and `#admin`, `#admin/system` and `#admin/general` go there directly. User intents call `App.router.go(route)` (guarded, pushes history, hydrates); area-internal canonicalisation calls `App.router.sync('<area>', sub)` (replace only, never guards, dropped when it would move the user). The one leave guard is `App.nav` (`static/js/nav.js`, M25 F2 L5): per-area dirty sources with a teardown-only `discard`, a synchronous clean fast path in the router adapter (never promisify it), one `beforeunload`, and a bubble-phase `a[href^="#"]` interceptor. See `the_one/agents.md` "Hash routing — the router" ("Leave guard (`App.nav`)").

**App shell (M25 F2 L6)**: no top bar. `<div class="app-shell-row">` is a flex row of `#app-rail` (the `App.ui.rail` workbench rail: four plain `<a data-testid="rail-{chats|agents|library|settings}">` links, hrefs kept current through `App.router.onCommit`, and since M25 F4 L7 the Jump to button `rail-jump-to` in its bottom `footer` slot), `<aside id="app-sidebar">` (its width follows the `data-destination` the router stamps on it: Chats, Agents and Library `--list-w` 300px (Chats since M25 F4 L4a; `--sidebar-w` is retired) and Settings `--settings-nav-w` 260px, at every width; 1024px is the supported minimum), `<main id="main-content">` and, since M25 F4 L6, the agent drawer's static `<aside id="chat-drawer">` (hidden off Chats; `.app-shell-row` is `position: relative` for its overlay mode). Browser tests open a destination with `_nav.open_destination` (the rail). `.visually-hidden` is a global utility in `components.css`. `base.css` holds the one global `[hidden]` reset (`display: none !important`), so no author `display` can defeat `hidden`; add no per-component copies. See `the_one/agents.md` "App shell — invariants".

**Chats list and agent picker (M25 F4 L4a)**: the Chats aside is an `App.ui.listPane` (testid `chats-list`, title "Chats", `rowStyle: 'chats'`, 300px at every width) built with DOM APIs by `static/js/areas/chat/chats-list.js` (`history-buckets.js` and the `agent-select` dropdown are retired). Its header block is the full-width New chat (`chats-new-btn`, disabled while setup is incomplete), which calls `App.chat.openPicker({opener})`. Rows (`chat-row`, links to `#chats/{id}` with `data-id`) sit in recency groups by local `updated_at` (Today `h:mm AM/PM`, local 12-hour via `App.time.formatClock`, Yesterday and Last 7 days a weekday, Last 30 days and Older `Mon D`; day 7 is Last 30 days), carry the agent ("Default agent" for none) and a connector's platform badge, and a delete action (`chat-row-delete`, arm then confirm, then focus to the neighbouring row); the pending chat's row (`data-pending`, a link to `#chats/~new/{agent}`, no action) is selected at the top of Today. One `renderChatsList()` (store `sessions` + session state) runs from the `sessions` subscription and every state transition. `App.chat.openPicker({opener})` (`areas/chat/agent-picker.js`) goes to Chats first when needed (rejects on a guard Stay), queues until the chat area's init, is inert with setup incomplete, and opens a fresh `App.ui.searchList` in an `App.ui.modal` chooser (`agent-picker`, `agent-picker-search`, `agent-picker-row` with `data-agent`, `agent-picker-close`): "Recently used" (5, web sessions of live agents) then "All agents" A-Z, or "{n} matching" A-Z over name, model, provider type slug and description; Enter picks, and the pick runs from the modal's `onClose` (after focus returns) through `requestPick`. Tests reach both through `tests/browser/_chats.py` (`start_chat` picks through it; `chats_new_button`, `open_picker`, `pick`, `picker*`, `chat_row_delete`) and `_lists.py`'s `"chats"` list. See `the_one/agents.md` "Chats list and agent picker".

**Chats pane (M25 F4 L4b)**: the detail pane is DOM-built by `static/js/areas/chat/chat-pane.js` (`App.chat.chatPane`; `welcome.js` folded in, the content sink gone: `tests/test_ui_guards.py` baselines no `areas/chat*` path) and the composer by `areas/chat/composer.js` (restyled in leg 5; see "Chat composer" below). One `h1` per state. **The header** (`chat-header`, a 48px `<header>` with a hairline; hidden while idle): the `h1` is "New chat" while pending or starting, else the session's title **read from the `sessions` store by id** (so it follows the auto-title; the `session_joined` payload's title is the fallback, then "Untitled chat"), and `chat-agent-line` reads "with {agent}" ("Default agent" for a null agent). **The new-chat state** (`chat-new-state`, only while pending): a `badge badge--{providerType}` whose text is the model (A20; the type through the picker's `providerType`, `badge--unknown` as the fallback), the agent name (`h2`), the description, and "Pick a different agent" (`chat-pick-different-btn`, `openPicker`). **The empty and guidance states** stay in `chat-welcome` (shown only by the idle rules: idle with no chat to auto-join, never while joining): the mascot, the "Hello." `h1.chat-welcome-greeting`, then the prompt "Start a conversation with one of your agents." and New chat (`chat-empty-new-btn`, opens the picker) when setup is complete, or the DOM-built guidance links (no New chat; the list's is disabled) when it is not. The welcome's agent list, the header's `new-chat-btn` and `h2.session-agent-badge` are retired. `renderPane()` in `chat.js` runs from every transition and the `sessions`/`agents`/`providers` subscriptions, patching nodes built once. Tests: `tests/browser/test_flow_chat_pane.py`. See `the_one/agents.md` "Chats pane". **The agent drawer (M25 F4 L6)**: `areas/chat/agent-drawer.js` fills the static `<aside id="chat-drawer" aria-label="This chat's agent">` slot after `<main>` through `App.ui.drawer` (`chat-drawer*` testids: the toggle `chat-drawer-toggle` at the header's end with `aria-pressed`/`aria-controls`, `chat-drawer-facts`, `chat-drawer-uses`, `chat-drawer-note`, `chat-drawer-settings-link`); it shows only on Chats with a chat open (hidden, never removed, so the toggle's `aria-controls` always resolves), pushing `<main>` at 1280px and wider (open by default, so EVERY Chats browser test at Playwright's 1280 default has a 588px pane) and overlaying below (closed by default), the open state per mode in `localStorage` `chat-drawer-open`. Its Open agent settings goes to `#agents/{name}` and then calls `App.studio.clearAgentFilter()`. The agent editor's header **Chat** (`agent-chat-btn`, saved agents only) starts a pending chat through `App.chat.chatWith(name)`, a guarded go with the chat area's pick intent. See `the_one/agents.md` "Agent drawer".

**Chat composer (M25 F4 L5)**: `areas/chat/composer.js` (`App.chat.composer.create()`, a DOM builder; `render` sets the placeholder and model id, `fit` the height) builds reference spec 5.5: the wrapper `.composer` holds the telemetry row (`.composer-telemetry`, the `.telemetry-overlay` readout, flex-end, **shown only while a chat is joined**), the staged-image row, the queued-message region, then `.composer-box` (fills the wrapper's content width, no cap since DD16, `--surface`, a hairline). In the box: a visually hidden `<label for>` "Message", the `<textarea rows=2>` `chat-input` (placeholder "Message {agent}…"; it grows to about eight lines, then scrolls) and the toolbar: Attach images (`chat-attach-btn`, ghost, small, icon only, paperclip), the hidden `chat-image-input` (named "Attach images", squawk 0110), the model id (`chat-model`), Stop and Send (`chat-stop-btn`, `chat-send-btn`). **Enter sends, Shift+Enter is a newline, and an Enter with `isComposing` or `keyCode` 229 does nothing (IME).** The focus ring is the box's `:focus-within` (A25; the textarea has `outline: none`). Scripted writes to the textarea go through `setInputValue` in `chat.js` so it re-fits. Tests: `tests/browser/test_flow_chat_composer.py`. See `the_one/agents.md` "Chat composer".

**Jump-to palette (M25 F4 L7)**: **Ctrl K** (Meta K on macOS; never with Shift or Alt; it works from inside inputs and calls `preventDefault`) and the rail footer's **Jump to** control (`rail-jump-to`, a 44px ghost search button, `aria-label="Jump to (Ctrl K)"`, `aria-keyshortcuts="Control+K"`; "⌘ K"/`Meta+K` on macOS) open `App.jumpTo` (`static/js/jump-to.js`): an `App.ui.searchList` in an `App.ui.modal` chooser named by the new `ariaLabel` option ("Jump to", no title, no header row; testids `jump-to`, `jump-to-input`, `jump-to-result` with `data-kind`/`data-id`, and its own Esc `jump-to-close`). The Ctrl K listener is the ONE shell-level `keydown` on `document`, in `app.js` beside `mountRail` (`installJumpToKey`; library factories may not install document listeners); it ignores an IME composition, focuses the palette's input when the palette is open, and does nothing while any other modal is open (the new `App.ui.modal.anyOpen()`, which counts every `App.confirmDialog`). `App.shortcuts` (`isMacPlatform`, `isJumpToKey`, `jumpToKeys`) are its pure helpers. Candidates in board order: agents A-Z, chats newest first, "New chat…", knowledge bases, MCP servers, connectors, Settings pages; the first 8 matches of a case-insensitive substring over label + "where"; the EMPTY query is instead a mix (M25 F4 L9, operator option C): up to 3 recent chats, "New chat…", up to 4 recently used agents (`App.chat.agentPicker.recentAgents`), then the board order as fill, 8 in total (`App.jumpTo.emptyMix`). A pick CLOSES the palette first, then `App.router.go(href, {opener})` (an agent also clears the Agents filter; New chat… is `App.chat.openPicker({opener})`), so a dirty editor asks exactly once and Stay returns focus to the opener. `App.ui.rail`'s new `footer` option holds the control. **`App.settingsPages`** (`static/js/settings-pages.js`, loaded before `router.js`) is the ONE Settings page table (`{section, label, group}`, `section` the route segment): the Settings nav, the router's spoken labels (built lazily) and the palette read it; `tests/test_settings_pages_static.py` pins it. Tests: `tests/browser/test_flow_jump_to.py` (shared lane). See `the_one/agents.md` "Jump-to palette".

**Time zone setting (M28 F1 L1)**: `the_one/time_zones.py` is a leaf module (stdlib, pydantic, `tzlocal`, `tzdata`) holding the operator's time-zone setting and the pure, locale-neutral date formatters. The setting is stored as JSON under the `time_zone` key in `app_metadata` (`{mode: "system"|"zone", zone}`; default `system`, which follows the host zone as detected by `tzlocal`, re-read at most once a minute). Zone names are validated against the tzdata package's own name set (never the host, never used as paths). Routes: `GET`/`PUT /api/time-settings` (the setting, the effective zone, the system zone and four preview strings; a PUT 422 detail is one plain sentence) and `GET /api/time-zones` (picker rows). `/api/info` gained `date_prompt_example` and `date_prompt_example_without_tool` (static placeholders). Tests freeze the clock and system zone with the `frozen_clock` fixture in `tests/conftest.py`. See `the_one/agents.md` "Time zones (M28)". Every clock time, weekday and day group the browser shows follows the operator zone through `App.time` (`static/js/time.js`, loaded before the first render; the only module that may call the `Date` getters; `App.time.onChange(fn, ownerEl)` also drops a listener once `ownerEl` disconnects, `App.time.applySettings(s)` applies a settings response including its `effective.offset_minutes` fallback), see `the_one/agents.md` "`App.time` (M28 F2)".

**current_time and the date layer (M28 F1 L2-L3)**: `current_time` is a 23rd built-in (category "Time", its own badge) that is exempt from an agent's `enabled_tools` whitelist (`WHITELIST_EXEMPT_TOOLS` (in `the_one/agent/config.py`); only `disabled_tools` or the operator's global off removes it), part of every agent's starting toolset, and every agent's system prompt ends with a date line in the operator's time zone, worded differently with and without the tool (the wording predicate `time_tool_available` fails CLOSED, to the tool-free wording, when the provider probe times out or errors). The drawer, the Tools tab and the Tools-tab save mirror the exemption through `App.toolCategories.whitelistExempt`; Settings › Prompts shows both date wordings. See `the_one/agents.md` "current_time and the date layer (M28)".

**Date and time page (M28 F2 L3)**: `#settings/date-and-time` (`areas/admin/date-time-page.js`, `App.admin.renderDateTimePage`, second under General) picks the time zone agents and the app use. A system / chosen-zone `App.ui.radioGroup`; under "Choose a time zone" an inline `App.ui.searchList` over `GET /api/time-zones` (alias names are searchable and stored as the operator chose them); a mismatch hint when the browser's zone and the effective zone are different clocks (compared by canonical name), with a one-step "Use {zone}"; and a "What agents see" preview taken from the server's own strings. It saves on choice with a module-level generation counter (only the latest response is applied; a failed save re-GETs), and calls `App.time.applySettings` so the app's clocks follow without a reload. See `the_one/agents.md` "Date and time page (M28 F2 L3)".

**Rules and notes tab (M27 F1 L2)**: the agent editor's second tab (after General; `data-tab-id="rules-and-notes"`, route `#agents/{name}/rules-and-notes`, `areas/studio/rules-notes-tab.js`) holds the operator's ordered Rules for the agent: add, edit, on/off toggle, move up/down, armed delete. Every control saves immediately through `GET`/`POST /api/agents/{name}/rules`, `PUT`/`DELETE .../rules/{id}` and `PUT .../rules/order` (no Save button, never the General form's dirty state; unsaved Add/edit text is not leave-guarded). The chat agent drawer's "What it can use" gains a Rules group first (enabled rules, "{n} off"). **Notes (M27 F2 L3)**: the tab's Notes section below Rules has the "Let this agent keep notes" switch (saves at once through `PUT /api/agents/{name}/notes/settings`) and lists the agent's notes (`GET .../notes`) with origin link, time, "Edited by you" and a "Check this" badge for notes written after content not from the operator, with inline edit (`PUT .../notes/{id}`), armed delete (`DELETE .../notes/{id}`) and Clear all (`DELETE .../notes`, through a confirm dialog); the drawer gains a Notes group after Rules (Off + "{n} kept"). **The drawer's Rules and Notes groups are read-only (M27 F3 L2):** no delete, Clear all or edit links (Open agent settings reaches the tab), a warning-triangle flag replaces the "Check this" chip, notes the open chat's prompt does not carry yet are muted under "Pending · used from the next chat" (`GET .../notes?session_id=` sets `pending`), and the group refreshes live when the agent saves, updates or forgets a note. **Settings › Prompts (M27 F3 L3; platform sections since Flight 2 leg 1c)** shows every hard-coded layer read-only in assembly order: the platform prompt as one titled block per section with an "Applies when" line (from `GET /api/info`'s `platform_sections`, `platform-section-{variant}-{id}`; the "With tools" and "Without tools" variants), then the rules and notes examples (`rules_prompt_example`/`notes_prompt_example`/`notes_prompt_example_tool_free`, rendered by the real render functions). Note text is attacker-influenced and is rendered with `textContent` only. See `the_one/agents.md` "Rules and notes tab (M27 F1 L2)".

**Agents list and detail (M25 F3 L3)**: Agents is an `App.ui.listPane` column in the aside (testid `agents-list`: A-Z rows `agent-item`, filter `agents-filter`, "New" `new-agent-btn`) beside the tabbed editor (an "Agents" breadcrumb, a link to `#agents` since L4b; an `editor-unsaved` caption; no Back) or, since M25 F6 L4c (DD15), the Agents start page (the visible `root-heading` `h1` "Agents", then `div.start-page` `agent-select-empty` / `agent-empty`: what an agent is, a variant line, a primary New agent `agent-empty-new`). `#agents/~new` is the create route. `setActiveSection` in `studio.js` owns the list pane's lifetime (created on entering Agents, destroyed on leaving). Tests reach it through `_lists.py` (`expect_selected`, `filter_agents`, `agents_new`, `agents_empty_state`). See `the_one/agents.md` "Agents list and detail".

**Library list and detail (M25 F3 L4a)**: Library is one grouped `App.ui.listPane` column (testid `library-list`: Model providers / Knowledge bases / MCP servers / Connectors, rows `provider-card` (sortie 02; the type badge and `App.usage.providerAgents` meta) / `knowledge-base-card` / `mcp-source-card` / `connector-card` with `App.usage` meta) with an Add menu (`library-add-btn`, the first production `App.ui.menu`, `align: 'end'`) beside the existing editors or, at the Library root (`#library`), the Library start page (M25 F6 L4c, DD15: the visible `root-heading` "Library", an intro and one `.start-page-card` per type with an `h2`, a description and its Add button `library-start-{providers|knowledge|mcp|connectors}-add`, in `div.start-page` `library-start`). The section nav and the three tile grids are retired. Knowledge bases (`#library/knowledge/~new`: creating opens the new item, squawk 0101) and connectors (`/~new` and `/{id}`, with MCP's pending-id rule) are routed like MCP. Fetch policy: pane creation and studio activate force-get the four collections, a move between Library sections fetches nothing, mutations `reloadLibrary`. Tests: `_lists.library_add` / `library_start`. **Model providers (sortie 02):** the provider editor (`areas/studio/provider-editor.js`, `App.studio.renderProviderEditor`; one host: Library) mounts in the detail pane through `areas/studio/providers-section.js` (`App.studio.providersSection.create(ctx)`: the section module reaches studio only through `ctx`, see `the_one/agents.md` "Providers section"). **Item header chrome (L4b):** every Agents and Library editor header (the knowledge-base `~new` form too) shows a breadcrumb ("Agents", "Library / {Group}") whose link ("Agents", or "Library" -> `#library`; the group is plain text) goes to its root (`editor-breadcrumb-link`): with Back retired it is how an item closes (router-guarded; focus goes to the item's row), and tests close items with `_lists.close_item(page)`. Each editor carries the stable `editor-unsaved` caption. See `the_one/agents.md` "Library list and detail" ("Item header chrome").

**Settings nav and pages (M25 F3 L5a)**: Settings' column is one `App.ui.navGroups` (`<nav aria-label="Settings">`, testid `settings-nav`, links `settings-nav-{section}`): General (Appearance, Date and time, Prompts, Encryption), Defaults for agents (Built-in tools, Knowledge indexing). Plain links with `aria-current="page"` on the current page's section (item routes included); no click handler, so the router's leave guard asks once. The former General page is three pages (`system-page.js`: `renderAppearancePage` / `renderPromptsPage` / `renderEncryptionPage`); every Settings page has a section 4 page header with the board's label ("Built-in tools", "Knowledge indexing"). `areas/layout/section-nav.js` is deleted. Tests: `_lists.settings_nav_link` / `open_settings_page` / `expect_settings_selected`. See `the_one/agents.md` "Settings nav and pages".

**Settings item pages (M25 F3 L5b)**: Built-in tools is the only Settings page with items (providers moved to Library, sortie 02): an open tool renders its editor BELOW the tile list, in the page scaffold `admin.js` builds per category render (page header, `.settings-list`, `.settings-item`); list renders target the list section only and editors mount in the item section, so a store notification, a toggle or `_refresh` never re-mounts the editor. A tool's NAME is its item link (`a.tool-tile-link`; the tile `tool-card` is no click target; the `tool-toggle` never navigates). The editor carries the "Settings / Built-in tools" breadcrumb, no Back and the `editor-unsaved` caption; an intent open scrolls the editor header into view and focuses its title, an `h2` (the page header keeps the page's one `h1`). Tests: `_lists.item_link` / `settings_item` / `open_tool` / `tool_toggle`, `close_item`; the retired-selector guard exempts no file. A Settings tile's name and badge share a flex title row (`.tile-title-row`) so they never overlap; `POST /api/providers` and `POST /api/chat/sessions` return 422 (not 500) on a validation error, with `include_input=False` so a submitted `api_key` is never echoed; at the Agents and Library roots with no editor open the page has one visible `h1` (`root-heading`) that is the start page's title.
See `the_one/agents.md` "Settings item pages".

**Focus after an in-place action (M25 F6 L1b)**: `App.focusAfter` (`static/js/focus-after.js`) returns keyboard focus after a Save, edit-mode Cancel, Test or in-place Create in the six editors: `begin(control)` when the action starts, `restore(token, target)` after the final mount (the editor's `.editor-title`, or the Test button once re-enabled), never when the user has moved focus meanwhile; `cancel()` from every teardown, `defer`/`flush` for async create mounts. Closing actions keep DD8's rule, and knowledge-base create keeps focusing its folder-path input. See `the_one/agents.md` "Focus after an in-place action".

**Flight 6 alignment notes (M25 F6)**: (DD13) every section label is one "eyebrow with a rule" recipe, small semibold letter-spaced uppercase in `--fg-tertiary` plus a hairline to the edge, on `listPane`/`navGroups` captions and `.section-title`. (DD14) a clock time shown to a person is local 12-hour `h:mm AM/PM` through `App.time.formatClock`, never `toLocaleString` (the Knowledge `Indexed:` line stays precise). (DD17) the desktop main window passes `text_select=True`, because pywebview's default injects `user-select: none`. (DD19) an MCP connection error shows a plain headline with the raw text under a collapsed "Technical details" (`App.mcpErrorMessage` / `App.buildMcpError`, `static/js/mcp-error.js`; `App.time.formatClock` is `static/js/time.js`). (DD5) on the WebSocket, a `cancel` sends at most one `cancelled`, and a degraded `join` of the already-bound session unsubscribes the socket. Detail in `the_one/agents.md` ("Section titles", "MCP error translation", the WebSocket protocol table). (L6) bare `<a>` links take `--accent` from `base.css` (`a:any-link`); give a link its own class rule only when it needs another colour, and keep the underline on links in running text.

**Client data store (`App.store`, M25 F2 L7; F3 L2; F4 L1)**: `static/js/store.js` is the shared client cache for six list collections: `agents`, `providers`, `knowledge-bases`, `mcp-sources` (the plain list; the agent editor's `?include_agent_surfaces=1` variant stays a direct fetch), `connectors` and `sessions` (`GET /api/chat/sessions`, rows `{id, agent_name, title, created_at, updated_at, platform}`; M25 F4 L1) (`get(name,{force})` returns a copy and rejects on failure, and `force` joins an in-flight request; `peek`, generation-safe `invalidate`, `subscribe`). `App.store.prime(name, rows)` sets a collection from a push (loaded, ok, fresh), bumping its generation and dropping its in-flight request like `invalidate`, then notifies: the chat area primes `sessions` from every WebSocket `session_list` reply (mapped to the REST summary shape), so while Chats is active the WebSocket is its source. Read those lists through it, never a literal `fetch('/api/<collection>')`, and call `App.store.invalidate(...)` after any mutation of them (an agent rename and the agent editor's Purge now invalidate `sessions`). `App.usage` (in the same file) derives "used by" counts from the list-shaped agents array: `providerAgents`, `kbAgents`, `mcpAgents`, `connectorAgents` (distinct names in `default_agent` plus `channel_map`) and `mcpToolCount` (`null` = tools not loaded). See `the_one/agents.md` "Client data store (`App.store`)" for the invalidation map, the freshness bound and the request counts.

**Control library (`App.ui`, M25)**: new UI controls are factories in `the_one/interfaces/web/static/js/ui/` (ES5, native elements, no HTML-string sinks, caller-supplied `testid`). Every factory needs a row in the catalogue `docs/ui-control-inventory.md` (which also lists the colour, spacing and type tokens) and engine-parametrized contract tests (Chromium + WebKit); `tests/test_ui_control_inventory.py` enforces both: the row, and a `tests/browser/test_ui_*.py` file that calls `App.ui.<name>(`. Each row declares its owned classes, and `tests/test_ui_ownership.py` fails on any owned class or retired-API call outside `js/ui/` beyond a frozen, shrink-only allowance (`HTML_SINK_ALLOWANCE` in `tests/test_ui_guards.py` does the same for HTML-string sinks). The editor family (`App.ui.editorShell`/`section`/`dangerZone`, M31 F1 L4) lives in `js/ui/editor.js`; `App.ui.confirm` (alias `App.confirmDelete`) in `js/ui/confirm.js`; the feedback and value controls (`status`, `flash`, `progress`, `chip` in `js/ui/feedback.js`, `copyButton`/`copyField` in `js/ui/copy.js`, and `App.ui.consentLink`, alias `App.consentLink`, in `js/ui/consent-link.js`, M31 F1 L5). The provider models panel (`areas/studio/provider-models.js`, M31 F1 L6) is the first stateful pilot: `renderProviderModels` mounts once and returns a `{refresh, destroy}` controller, and refreshes reconcile rows by key instead of rebuilding, so a pull in progress, the pull select's choice and focus survive. The provider editor (`areas/studio/provider-editor.js`, M31 F1 L7) is built once per mount from the library (`editorShell`, `section`, `field`, `secretInput` in `js/ui/field.js`, `status`, `dangerZone`), with the key re-masked after a successful Save; its OAuth sign-in (three states over one replaced node, `App.ui.consentLink` with its `help` option, an `App.ui.confirm` Reset) and token-expiry line are library controls too (leg 8), so the editor and `providers-section.js` have no HTML-string sinks and no ownership-allowance rows. See `the_one/agents.md` "Control library (`App.ui`)" and "UI test apparatus".

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

**The test suite runs host-native — no Docker.** (Mission 15 Flight 01 retired the `docker exec` test flow.) Canonical commands for non-interactive runs: `make test-unit` (the unit tier; `make test` is the same set under `addopts`), `make test-browser` (all browser lanes, 3 at a time) and `make gate` (the full local gate: unit, then browser, never concurrently; on this WSL host every browser run and gate needs `THE_ONE_TEST_NETNS=1`, see below); also `make test-bwrap`, which routes through `scripts/run-tests.sh` and uses the repo `.venv` when present (else `python3`). For ad-hoc single-file/single-test runs, `python -m pytest tests/...` against the project venv is fine.

**The local-API credential gate is live (Mission 20 Flight 1) — a stray 401 in a new test or a manual `curl` almost always means a missing credential, not a real regression.** Every route except `GET /api/live` requires an identified caller (see `SECURITY-MODEL.md` "Authentication"). `make test` / `make test-unit` / `make test-browser` need nothing extra — the existing fixtures already attach a credential: unit-test client fixtures via `tests/_credential_helpers.py::auth_headers()`, browser fixtures/seeders via `tests/browser/_credential_registry.py::auth_headers_for()`. Where this bites is a *new* ad-hoc `httpx`/`TestClient` call added to a test body, or a bare `curl`/browser hit against a `make up` instance — either will get a 401 with no credential attached. Read the credential from `<data_dir>/api-credential` (verbatim, single line) or mint a fresh one with `the-one rotate-api-credential`.

**Browser tests MUST go through `scripts/run-tests.sh` (i.e. `make test-browser`), never bare `python -m pytest -m browser`.** Browser tests spawn a per-test uvicorn subprocess plus a Playwright node driver + Chromium. Bare `python -m pytest` does NOT group-kill that subtree on interruption — the uvicorn/Chromium children orphan (re-parent to init) and peg a CPU core indefinitely, and the leaked load then starves *other* tests into timeout-failures that look like flakiness. `run-tests.sh` puts pytest in its own process group and SIGKILLs the whole group on exit or at `TEST_TIMEOUT` (default 1200s), so nothing orphans. Set a tighter `TEST_TIMEOUT` for small slices. A single lane keeps the default 1200s; for a FULL run `make test-browser` (`--parallel 3`) defaults its whole-run cap to 2400s — set `TEST_TIMEOUT=3600` for margin under load (the parent's cap bounds the entire parallel run, and each lane inherits the same value). (Inside CI this matters less — Concourse task containers are ephemeral and torn down after each build, so `ci/tasks/*.yml` call `python -m pytest` directly with `--timeout`. The GitHub Actions `test.yml` is now a `workflow_dispatch`-only break-glass fallback — see `ci/README.md`.)

**Always pair pytest with `-x`** for autonomous runs unless you specifically want to see full failure surface — pytest-asyncio's per-test loop teardown can hang if a test leaves orphaned state on a torn-down loop, and `-x` exits on first failure before that hang surfaces. Without `-x`, a single broken test can wedge the suite indefinitely.

**Test databases and the parallel runner**: new tests build their database from the session schema template (`tests/_schema_template.py`), not `ensure_schema`/`init_db`, and `scripts/run-tests.sh --parallel N` has a lifecycle/exit-code contract — see `the_one/agents.md` "Test databases come from the session template" and "Parallel test runner contract".

**Unit tests** run by default with `make test-unit` (host-native `python -m pytest tests/ -m 'not browser and not live and not pixel'`) — fast, no external dependencies.

**Expected unit skip count (squawks 0132, 0167)**: `make test-unit` normally reports **12 skipped** on a Linux host without `fr_FR`/`de_DE` locales (measured at the end of Mission 28; **11** where one of them is installed) — the 10 `tests/test_pty_windows.py` tests and `tests/test_pty_dispatch.py`'s Windows-only dispatch test (11 platform skips on Linux), plus `tests/test_time_zones.py::TestFormatters::test_locale_neutral`, which skips when neither locale is installed. A count of 14 means two timing-conditional tests skipped themselves: `tests/test_kb_watcher.py::TestRealWatch::test_real_watch_change_triggers_request_index` / `::test_real_watch_root_removal` (and, if a third appears, `tests/test_doctor.py`'s native round-trip test) skip when a 1-second native file-watch self-probe sees no event on a loaded host. Read `-rs` before treating any other count as drift. Under `THE_ONE_TEST_NETNS=1` the count is 14 even on a quiet host: `unshare -rn` maps the test process to uid 0, so `tests/test_kb_walk.py`'s and `tests/test_kb_watcher.py`'s root-only permission tests skip ("root bypasses permission bits"), and their coverage is lost in that mode. Running with an explicit `-m` that omits `not requires_bwrap` (the `addopts` default is overridden) adds 3 more `test_mcp_sandbox_integration.py` skips (15 measured, 17 under netns).

**Test databases come from a template (Mission 26 F1 L1).** A unit test that needs a fresh current-schema database builds it through `tests/_schema_template.py` (`connect_template_db(path)`, `copy_template(path)` for a settings-path pre-seed before `init_db` or the lifespan, `connect_template_memory()` for `:memory:`), which copies one migrated template built per pytest process instead of replaying every migration (~0.4 s each). Never call `ensure_schema(` or `init_db(` directly on a fresh database in a test: `tests/test_schema_template.py` fails on any test file outside its `ALLOWED_DIRECT_CALLERS` list (the real-migration files `test_db_migration.py`, `test_schema.py`, `test_db_connection.py`). Migration tests set `PRAGMA synchronous=OFF` on their connections.

**`tests/test_mcp_pool.py`** ships 10 pure-unit pool tests + 2 bwrap-dependent integration tests. The integration tests use `@pytest.mark.requires_bwrap` (registered in `pyproject.toml::markers`) and are deselected by default via the `not requires_bwrap` clause in `addopts`. To run the integration tests on a host with bwrap available: `pytest -m requires_bwrap tests/test_mcp_pool.py`.

**Built-in tool containment** (M14 F1) is proven by `tests/test_builtin_tool_sandbox.py` (5 tests: `shell` + `python_exec` each run through `BubblewrapSandbox` when bwrap is available, write-protection of denylisted paths, `sandbox_network_allowed` propagation, and the `PassthroughSandbox` fallback path). To run the full `requires_bwrap` set (44 tests collected, measured at Mission 29 Flight 2 leg 1: 7 `test_box_isolation.py` + 10 built-in containment + 1 `test_cli_sandbox_parity.py` + 2 MCP pool integration + 12 `test_mcp_sandbox_integration.py` + 1 `test_mcp_stdio_sandbox.py` + 11 PTY containment (`test_pty_sandbox.py`); on this WSL host **41 pass and 3 skip**, the 3 being `test_mcp_sandbox_integration.py` skips (two documented F6-A5 deadlock deferrals, one no-privilege-grants test that skips on WSL2)): `pytest -m requires_bwrap`.

**Color contrast tests** (`tests/test_design_tokens_a11y.py`): WCAG 2.1 AA contrast audits for the F2 design tokens. Run via default `pytest tests/`. See `the_one/agents.md` "Color contrast (WCAG AA)" for the audited pairs and any deliberate exceptions.

**Visual snapshot tests** (`@pytest.mark.pixel`, in `tests/browser/test_visual_snapshots.py`): 12 Playwright baseline screenshots covering 3 UI areas × 2 states × 2 themes. Run via `pytest -m pixel`. Baselines live in `tests/browser/__snapshots__/` and are **gitignored** — local regression artifacts only; each developer regenerates on a fresh checkout with `pytest -m pixel --snapshot-update`. Tolerance 2% pixel diff. CI never runs `-m pixel` (excluded by default in `pyproject.toml::addopts`).

**UI test apparatus (M25 F1)**: library contract tests run in Chromium and WebKit through the `engine_page` fixture (`tests/browser/_ui_engines.py`); a WebKit launch failure skips locally and fails under `THE_ONE_REQUIRE_WEBKIT=1` (CI). `bash scripts/setup-webkit-userland.sh` provisions WebKit's host libraries without sudo; `scripts/webkitgtk_probe.py` (system `/usr/bin/python3`, a dev instance on 8486 or higher — it refuses 8484, 8485 (the Flight Director's preview instance, since M25 F4 L7) and the default data dir) checks pages in the real desktop engine; `--press-keys ctrl+k --assert-selector <css>` (with `--focus-selector`) sends a real GTK key event (a `Gdk.EventKey` pair through `WebView.event`) and reports `key_verdict` "partially verified (GTK-level key)" or "unverified". `scripts/windows_test_copy.py` (M25 F5 L1a) runs a test copy of the working tree on the operator's Windows desktop from WSL (setup/freeze/launch/observe/stop; M25 F5 L1b added gated keys, clicks, drags, captures, own helper windows and focus save/restore, each behind a foreground or `WindowFromPoint` gate and a hands-off wait, with a key-grammar denylist; M25 F5 L4 added `resize`, an outer-size `SetWindowPos` the live floor test needs, and `capture --splash --series`, a series that follows the splash window): it refuses ports 8484/8485 and below 8490/9390, any data dir at, inside or containing the operator's Windows data dir, a frozen run while that dir holds a `.env`, and any kill whose process identity does not match its record, and every session is bracketed by `snapshot --out`/`--compare`. See `the_one/agents.md` "UI test apparatus" ("Windows test copy", "Windows test copy, input and capture").

**UI capture tool (M31 F1 L3)**: `scripts/ui_capture.py --out DIR` (outside the repo; `--list` shows the surfaces) starts its own scratch dev instance (port 8490 or higher, scratch data dir under `$HOME`), seeds it and writes light/dark PNGs of named UI surfaces; refuses ports 8484/8485 and below 8490, the default or any configured data dir, and an `--out` inside the repo; `THE_ONE_TEST_NETNS=1` re-runs it in a loopback namespace. Captures are local evidence and never committed. See `the_one/agents.md` "UI capture tool".

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

**Per-area browser test lanes** (M17 F5; re-mapped to the four destinations in M25 F2; `contracts` added in M25 F4 L1, squawk 0117; `mcp` and `routing` split out and `--parallel` added in M26 F1 L4). `make test-browser` runs every lane **three at a time** through `scripts/run-tests.sh --parallel 3` (about 15 minutes on the 20-core / 16 GB WSL host, against about 37 minutes sequential), and `make gate` is the full local gate (unit, then browser; about 18 minutes measured, against about 53 minutes sequential before Mission 26). **Host policy** (operator decision, M26): at most 3 browser lanes run concurrently on a local host (about 1.15 GB and 3-4 cores each), the unit suite always runs outside the concurrent set, and a local gate and a CI build never run at the same time. Do not raise the default above 3. `--parallel N` starts each lane as its own child `run-tests.sh --lane <lane>` (longest budget first), writes `<dir>/<lane>.log` and `<dir>/<lane>.xml` (`<dir>` is `$TEST_LANE_DIR` or a fresh `mktemp -d`, printed at start and in the summary), and ends with a per-lane summary plus a machine-readable `PARALLEL_RESULT rc=<n> total=<s>s lanes=<k> failed=<list or ->` line. The parent exits 0 only if every lane exited 0 and wrote a non-empty junit file; a lane killed or timed out (137/143) makes it exit 137; otherwise it exits with the first failing lane's code in schedule order. `--parallel N --plan` prints the schedule without running; `--help` prints the lanes, budgets and policy. `TEST_TIMEOUT` (default 2400 s in parallel mode) bounds the whole parallel run: at the cap the parent exits 137 and group-kills every lane; Ctrl-C or TERM does the same with TERM-first cleanup, and a SIGKILLed parent is detected by each lane's watchdog within about a second. A single lane keeps its own `TEST_TIMEOUT` (default 1200 s). `scripts/run-tests.sh` accepts a `--lane {chats|agents|library|mcp|routing|settings|providers|contracts|shared}` selector that runs just one slice:

```bash
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats      # Chats slice
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents     # Agents slice (Studio agent editor)
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane library    # Library slice (knowledge, connectors, MCP navigation)
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp        # MCP editor and Library list
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane routing    # router, leave guard, client store
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings   # Settings slice (admin pages / tools)
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane providers  # provider editor + Library Model providers
THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts  # App.ui contracts, both engines
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane shared     # cross-cutting slice
# Extra pytest args pass straight through, e.g. add `-x` or `-q`:
PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents -q
# List a lane's files (one per line) without running pytest:
bash scripts/run-tests.sh --lane contracts --list
# All lanes, 3 at a time (what `make test-browser` does):
THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short
```

**Lane time budgets** (wall seconds in a `--parallel 3` run, re-measured at the end of M31 F1 leg 8 (the full `make gate`, 1041 s total; `providers` and `contracts` re-budgeted to measured plus 25% headroom, rounded up to 30 s, after the provider-editor pilot and the library contract files grew them); the table in `scripts/run-tests.sh` is the source of truth and the `--parallel` summary flags `OVER BUDGET`, a warning rather than a failure):

| lane | budget (s) | measured in the gate run (s) |
|---|---|---|
| `routing` | 600 | 505 |
| `settings` | 300 | 232 |
| `agents` | 510 | 497 |
| `chats` | 360 | 342 |
| `mcp` | 360 | 328 |
| `library` | 300 | 248 |
| `providers` | 420 | 315 |
| `shared` | 300 | 286 |
| `contracts` | 390 | 296 |

**Aliases** (the pre-M25 names still work and expand to the union of their lanes): `chat` = `chats`, `studio` = `agents` + `library` + `mcp`, `system` = `settings` + `providers`. `--parallel` schedules only the canonical lanes, so no file runs twice.

Each lane runs independently green under the venv python (always pass `PYTHON=.venv/bin/python`).

- **`chats`** — `test_flow_chat*`, `test_flow_markdown_chat`, `test_flow_new_chat`, `test_flow_streaming`, `test_flow_context_overlay_thresholds`, `test_flow_usage_restore`, `test_chats_helper` (the `_chats.py` smoke tests, M25 F4 L3a)
- **`library`** — an **explicit file list**: `test_flow_studio_knowledge_inventory`, `test_flow_studio_mcp_navigation`, `test_mcp_test_connection_button`, `test_studio_connector_editor`, `test_flow_studio_library_focus`. A new Library-owned test file must be added to `library_pat` in `scripts/run-tests.sh`.
- **`mcp`** — an **explicit file list** split from `library` for balance (M26 F1 L4): `test_flow_studio_mcp_editor`, `test_flow_studio_library_list` (`mcp_pat`)
- **`agents`** — the old studio globs (`test_flow_studio_*`, `test_studio_*`, `test_mcp_*`, `test_flow_agent_*`) plus the Agents list/detail files (`test_flow_agents_*`, `test_agents_*`, M25 F3 L3) **minus** the `library` and `mcp` lists (so the agent-editor tabs, e.g. `test_flow_studio_knowledge_attach` and `test_studio_mcps_tab`, stay here)
- **`routing`** — `test_router_*`, `test_nav_guard*`, `test_store*`: the hash router, the leave guard and the client data store (M26 F1 L4, taken out of `shared`, which they dominated)
- **`settings`** — `test_flow_admin_*`, `test_flow_settings_*` (M25 F3 L5b; Settings no longer has providers)
- **`providers`** — `test_flow_provider_*`: the provider editor and the Library "Model providers" group (sortie 02, the ninth lane; `providers_pat`)
- **`contracts`** — `test_ui_*`: the `App.ui` control-library contract files (engine-parametrized, Chromium + WebKit) (M25 F4 L1, squawk 0117). Run it with `THE_ONE_REQUIRE_WEBKIT=1` after any library change, so a WebKit launch failure fails rather than skips
- **`shared`** — the **complement**: every browser test file not claimed by the eight named lanes (smoke, theme sync, markdown, keyboard, hash routing, oauth modal, dirty-confirm, cross-area gate, picker, seeders, app fixture, …)

Lanes are hand-rolled basename globs over `tests/browser/` — no new deps, no per-test markers. Because `shared` is defined as the complement of the eight named lanes, the nine lanes' union is *always* exactly the whole browser suite and no test file can be orphaned — a newly added `tests/browser/test_*.py` lands in `shared` until it is given a lane glob in `scripts/run-tests.sh`. `--list` (with `--lane`) prints a lane's files and exits 0 without running pytest; `--list` without `--lane` exits 2. `tests/test_run_tests_lanes.py` (unit tier) lists all eight lanes and pins that they are pairwise disjoint, that their union is every `tests/browser/test_*.py` except the pixel-only `test_visual_snapshots.py`, the `--parallel`/`--plan` argument errors, the budget table (every canonical lane once) and the parallel exit-code rules.

**Browser tests navigate through `tests/browser/_nav.py`, never raw route hashes** (M25 F2 L1). A browser test states a route in the **new** scheme (`"library/providers/~new"`, `"agents/<name>/tools"`, `"library/mcp/<id>"`, `"chats"`) and `_nav.goto` / `expect_route` / `set_route` / `current_route` / `wait_for_route_prefix` / `href` / `open_destination` map it to whatever the app serves (one `SCHEME` switch). Ids go through `_nav.seg()` (JS `encodeURIComponent` parity). `tests/test_nav_helper.py::test_no_raw_route_hashes_in_browser_tests` (an `ast` guard, runs in `make test-unit`) fails on a raw `#studio…`/`#admin…`/`#chat…` hash or a top-bar selector in any `tests/browser/test_*.py`, except in the deliberate `_nav.LEGACY_URL_TESTS` set (tests that keep a raw legacy `goto` to prove the redirect) — and, at file level, the router's own contract tests `tests/browser/test_router_*.py`. `SCHEME` is `"new"` since the router landed.

**List rows go through `tests/browser/_lists.py`** (M25 F3 L1): `list_row` / `open_item` reach rows through the kept testids, and `tests/test_nav_helper.py::test_no_retired_selectors_in_browser_tests` fails on a retired selector (`RETIRED_SELECTORS`: `entity-tile`, `section-nav-item`, `back-*-btn`, the Library grids' `new-{knowledge-base|mcp-source|connector}-btn`, the agent tiles' `agent-tile-{tool|mcp-tool}-count`, since M25 F4 L4a the old chat history list's `session-item`, `session-list`, `session-group` and `list-item-delete`, since L4b the chat pane's `new-chat-btn`, `chat-welcome-item`, `chat-welcome-list` and `session-agent-badge` (the kept `chat-welcome` testid and its other `chat-welcome-*` classes stay live), and since L5 the composer's old row `input-area`; plus `RETIRED_EXACT`, matched with a right boundary too: `agent-select`, so the live `agent-select-empty` stays usable) in any browser test file or helper module. No file is exempt: the per-file allow-list that carried the Flight 3 migration emptied in L5b and was removed in L6, and `test_retired_selectors_cover_the_registry_retired_table` keeps `RETIRED_SELECTORS` covering every id in `docs/ui-testid-registry.md`'s "Retired testids" table, so a retired id cannot come back. See `the_one/agents.md` "`browser-tests-navigate-through-nav-helper`".

**Chats go through `tests/browser/_chats.py`** (M25 F4 L3a; flipped in L3b): a browser test starts, joins and inspects a chat through `start_chat(page, agent)` (the agent picker since L4a: `pick(page, agent)` opens it from the Chats list's New chat, types the name and presses Enter; a pick is the route `#chats/~new/{agent}`, so it returns at a PENDING chat: no session, the state `pending`, the chat header "New chat" with "with {agent}", `chat-input` enabled; a pick sends only `leave`), `send_first(page, text)` (the first send's `start_session` creates the session; it waits for the join and returns the session id), `current_session_id(page)` (the joined or joining id; None while pending), `session_state(page)` (the chat area's state machine: `idle|joining|joined|pending|starting`), `chat_row(page, id)` / `chat_rows(page)` (the Chats list's `chat-row[data-id]`; never the pending row; `pending_row(page)` is that one) / `chat_row_delete(page, id)` / `open_chat(page, id)` (waits until joined), `chats_new_button` / `open_picker` / `pick` / `picker` / `picker_search` / `picker_rows` / `picker_row(page, agent)`, `chat_frames(page, actions=None)` (a live list of the sent WebSocket frames; call it before `page.goto`; it fills only while Playwright calls run, so poll with `page.wait_for_timeout`, never `time.sleep`), `welcome(page)` / `empty_new_button(page)` (the empty and guidance state, and its New chat), `new_chat_button(page)` (the list's `chats-new-btn` since L4b), `chat_header` / `chat_title` / `chat_agent_line` and `new_chat_state` / `pick_different_button` (L4b). `expect_chat(page, agent, title=None)` reads the chat header ("with {agent}", and the `h1` given a title). A test that needs a session calls `send_first` after `start_chat`. `seeders.seed_session(base, agent_name, title, updated_at, created_at=None, platform=None, messages=None)` seeds a session (past dates, a connector `platform`) through `POST /api/chat/sessions`. Flight 4 changes the helper BODIES, not the tests: leg 3b flipped the start semantics, leg 4a the sidebar (the Chats list and the picker), leg 4b the pane. Leg 3a's chat-seam guard (`CHAT_SEAM_*`) is gone since L4b: its selectors are `RETIRED_SELECTORS` entries, and `_chats.py` is checked like every other file.

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
mkdir -p $HOME/the-one-behavior-test-scratch/cwd && cd $HOME/the-one-behavior-test-scratch/cwd
THE_ONE_PORT=8485 THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data THE_ONE_DEV_MODE=true \
  <repo>/.venv/bin/the-one serve >serve.log 2>&1 &
echo $! > serve.pid        # stop later with: kill $(cat serve.pid)
```

Start it from a **scratch working directory**, not the repo root, and not
with `make up` (which runs from the repo): an agent's file tools resolve
relative paths and `~`-scoped allowlists against the server's environment,
so a repo cwd let an agent write into the repo (Mission 30,
`tests/behavior/agent-notes-round-trip/runs/2026-10-14-15-03-23.md`). Keep the
scratch data directory under `$HOME` rather than `/tmp` (bwrap mounts a
fresh `/tmp`). Record the PID and stop the instance by that PID.

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
cat $HOME/the-one-behavior-test-scratch/data/api-credential
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
