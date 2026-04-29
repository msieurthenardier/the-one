# agents.md

Development-facing architecture reference for the-one. This file describes the **target architecture** — the structure being implemented during the Structural Foundation mission. It is not loaded at runtime.

For usage, commands, and conventions, see `CLAUDE.md`.

---

## Architecture Overview

The-one is a general-purpose LLM agent built without frameworks. Four layers compose bottom-up:

```
┌─────────────────────────────────────────────────────┐
│  Interfaces (cli.py, web/app.py)                    │
│  → User-facing shells that create agents via factory │
├─────────────────────────────────────────────────────┤
│  Agent (core.py, factory.py, config.py, store.py)   │
│  → Agent loop, configuration, persistence, creation  │
├─────────────────────────────────────────────────────┤
│  Tools (base.py, provider.py, builtins.py, *.py)    │  LLM (base.py, registry.py, *_provider.py)
│  → Tool ABC, registry, provider protocol             │  → Provider ABC, lazy registry, 3 providers
├─────────────────────────────────────────────────────┤
│  Config (config.py)                                  │
│  → Pydantic-settings singleton, THE_ONE_* env vars   │
└─────────────────────────────────────────────────────┘
```

---

## Module Map

### `the_one/config.py`

Global configuration via `pydantic-settings`. All values from `THE_ONE_*` env vars or `.env` file.

| Export | Type | Purpose |
|--------|------|---------|
| `Settings` | class | Pydantic-settings model |
| `settings` | instance | Global singleton |

Key properties: `data_dir` (`~/.the-one`), `agents_dir` (`data_dir / "agents"`), `db_path` (`data_dir / "the-one.db"`), `dev_mode` (default: `false`).

### `the_one/encryption.py`

Fernet-based encryption for API keys stored in the database. Generates and caches an `Encryptor` per `data_dir`. Provides an `install_key()` helper plus a public `key_path` property; the API rotation path (`POST /api/encryption/rotate`) re-encrypts all provider credentials, commits the DB, then atomically replaces the key file via `os.replace`. The legacy `rotate_key()` callback API is retained for non-API callers.

### `the_one/db/repositories.py`

Database repositories including `LLMProviderRepository` for CRUD on `llm_provider_configs` table. Provider configs store `name`, `type`, `base_url`, and encrypted `api_key`. Referenced by `AgentConfig.provider_config_id`.

### `the_one/agent/`

| File | Exports | Purpose |
|------|---------|---------|
| `core.py` | `Agent` | The agent loop: `step()` yields messages, max 20 iterations |
| `config.py` | `AgentConfig`, `BASE_PROMPT` | Agent definition Pydantic model (includes `provider_config_id` for LLM provider resolution) and the foundational base prompt for layered composition |
| `factory.py` | `AgentFactory` | `create(name)` → configured Agent; `list_agents()` |
| `store.py` | `AgentConfigStore`, `FilesystemConfigStore` | CRUD for agent configs (`~/.the-one/agents/*.json`) |

**Agent.step() flow**: user input → LLM call → execute tools → repeat until no tool calls or max iterations.

### `the_one/llm/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `LLMProvider`, `Message`, `ToolCall`, `ToolResult`, `Role`, `TokenUsage` | Core types |
| `registry.py` | `register_provider`, `get_provider` | Lazy-loaded provider registry |
| `ollama_provider.py` | `OllamaProvider` | Local Ollama and OpenAI-compatible servers; model selection comes from agent config |
| `openai_provider.py` | `OpenAIProvider` | GPT-4o |
| `anthropic_provider.py` | `AnthropicProvider` | Claude (claude-sonnet-4-6 default) |

Providers are lazy-loaded on first `get_provider(name)` call. Each converts messages/tools to its wire format and back.

### `the_one/tools/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `Tool`, `ToolRegistry` | Tool ABC (`execute(**kwargs) -> str`) and registry |
| `provider.py` | `ToolProvider` | Protocol: `name` property + `get_tools()` method |
| `builtins.py` | `BuiltinToolProvider` | Provides all 7 built-in tools via lazy import |
| `shell.py` | `ShellTool` | Arbitrary shell commands |
| `filesystem.py` | `ReadFileTool`, `WriteFileTool`, `ListDirTool` | File operations |
| `python_exec.py` | `PythonExecTool` | Python subprocess execution |
| `web.py` | `HttpRequestTool`, `WebSearchTool` | HTTP and web search |

### `the_one/interfaces/`

| File | Exports | Purpose |
|------|---------|---------|
| `cli.py` | `run()` | Rich + prompt-toolkit REPL |
| `web/app.py` | `app` | FastAPI server with WebSocket sessions |

Both use `AgentFactory.create()` to get agents. The web app adds session management.

### App.chat helpers

The chat area's pure-helper layer lives at `the_one/interfaces/web/static/js/areas/chat/`. Each file is its own IIFE that attaches functions to `window.App.chat`; `chat.js` (the orchestrator) consumes them via the namespace and owns all closure state. A 3-line `App.markdown = {}` stub at `static/js/markdown.js` is loaded ahead of the chat helpers; flight F4 leg 03 replaces it with the real markdown library.

**Pure** (take inputs, return DOM):

- `App.chat.welcomeLink(text, areaId) → <a>`
- `App.chat.startOfDay(d) → number`
- `App.chat.bucketForSession(s, nowDay) → BucketLabel`
- `App.chat.fmtTokens(n) → string`
- `App.chat.renderMessage(cls, text, opts) → <div.msg>` — `opts.renderMarkdown: bool` is reserved for the markdown integration (leg 05). The flight spec's `(cls, text, attribution, opts)` shape is split into two functions: `renderMessage` (returns the bubble) plus `renderAttribution` (separate label). Leg 05's wire-up calls them as a pair, not as a single combined invocation.
- `App.chat.renderAttribution(side, text) → <div.msg-attribution>` — `side` is `'from-you'` (user) or `'from-agent'` (everything else); caller-determined.
- `App.chat.renderTelemetry() → <div.telemetry-overlay>` — returns the full overlay DOM (`.telemetry-summary`, `.context-bar-wrap` / `.context-bar`, `.t-ctx-pct`, `.telemetry-details`, the three `in:` / `out:` / `ctx:` rows). Built via `document.createElement` calls (not innerHTML) and preserves the F2/F3 `tabindex="0"` / `role="status"` / `aria-label="Token usage"` attributes verbatim.
- `App.chat.updateTelemetry(chromeContent, data)` — mutates the `.t-in` / `.t-out` / `.t-ctx` / `.t-ctx-pct` slots and the `.context-bar` width/class under the chrome content element.
- `App.chat.createThinking() → <div.msg.thinking>` — returns an element that owns its dot-animation interval (`el._dotTimer`); `THINKING_FRAMES` is module-private inside `thinking-indicator.js`.
- `App.chat.removeThinking(el)` — idempotent (no-op on null/undefined); clears the interval and removes the element from its parent.

**Callback-injected** (closure references replaced with explicit callbacks):

- `App.chat.renderWelcomeList(welcomeEl, welcomeListEl, agents, setupState, callbacks)` — `callbacks = { onStart: function(agentName) }`. (No `onLink` — `welcomeLink` returns `<a href>` and the browser handles navigation.)
- `App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, callbacks)` — `callbacks = { onJoin: function(id), onDelete: function(id, btn) }`.
- `App.chat.buildSessionItem(session, currentSessionId, callbacks)` — same callbacks shape.

The orchestrator (`chat.js`) owns closure state — `ws`, `currentSessionId`, `currentAgentName`, `pendingJoinId`, `availableAgents`, `setupState`, the WS lifecycle, the welcome-listbox roving-tabindex keydown handler, and the system-message `Loading model...` / `Model loaded.` flow. It wires WS events to helpers via the callbacks above.

Load order (set in `index.html`): `app.js` → `icons.js` → `markdown.js` → `areas/chat/welcome.js` → `areas/chat/history-buckets.js` → `areas/chat/message-bubble.js` → `areas/chat/telemetry-overlay.js` → `areas/chat/thinking-indicator.js` → `areas/chat.js` → `areas/studio.js` → `areas/admin.js`. Helpers MUST load before `chat.js` because the orchestrator calls `App.chat.renderTelemetry()` synchronously during `init`.

---

## Dependency Graph

```
config.py ←── llm/ ←──┐
    ↑                  │
    ├──── tools/ ←─────┤
    │                  │
    └── agent/core.py ─┘
            ↑
        agent/factory.py ←── interfaces/ ←── main.py
            ↑
        agent/store.py
        agent/config.py
```

**Rules**:
- Arrows point from dependent → dependency
- `config.py` is the leaf — imported by everything, imports nothing from the project
- `llm/` and `tools/` are peers — neither imports the other
- `agent/` imports from `llm/` and `tools/`
- `interfaces/` imports from `agent/factory.py` only (not core, not store)
- No circular imports anywhere

---

## Key Patterns

### Multi-Agent via AgentFactory

Agents are defined as JSON files in `~/.the-one/agents/` (or rows in the SQLite DB). The factory reads a config, resolves the LLM provider via `provider_config_id` (a reference to `llm_provider_configs` table), wires up filtered tools + prompt, and returns a ready-to-use `Agent`. A "default" agent has `provider_config_id=None` and must be configured through the Admin UI to assign a provider.

### Tool Filtering

`AgentConfig` has `enabled_tools` (whitelist, `null`=all) and `disabled_tools` (blacklist). Filtering happens in the factory — the Agent receives a pre-filtered `ToolRegistry` and never knows about disabled tools.

### Tool Providers

`ToolProvider` is a protocol with `name` + `get_tools()`. `BuiltinToolProvider` provides the 7 built-in tools. Future `McpToolProvider` implements the same protocol for MCP server tools.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`, defined inline in `core.py`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

---

## Browser test fixtures

Browser tests live in `tests/browser/` (with fixtures in `tests/browser/conftest.py` and seeders in `tests/browser/seeders.py`) and use Playwright (Python binding) to drive a real Chromium session against a per-test app subprocess. Three layered fixtures:

| Fixture | Setup | Use for |
|---------|-------|---------|
| `app_clean` | Fresh subprocess + empty DB + `THE_ONE_DEV_MODE=true` | First-start / setup-flow tests |
| `app_with_provider` | + 1 mock provider seeded via API | Agent CRUD tests |
| `app_with_agent` | + 1 agent referencing the mock provider | Chat tests |

Each test gets its own subprocess on a random port (via `socket.bind(('', 0))`) with an isolated `tmp_path` data_dir. Teardown sends SIGTERM, escalates to SIGKILL after 10s if needed. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2.

**Playwright fixtures (`playwright_instance`, `browser`) are module-scoped, NOT session-scoped.** Originally session-scoped during F1 leg 03 design; switched to module scope during implementation because session scope kept the asyncio loop alive across modules and broke the leg-01 standalone smoke test (`test_smoke.py` creates its own `sync_playwright()` context). Module scope still amortizes Chromium across tests within the same module while keeping the standalone smoke test green.

The `mock` provider type (production code, dev-mode-gated) provides deterministic LLM responses without external services — see "Provider type extension checklist" below for the full type wiring.

Tests rely on `data-testid` attributes on load-bearing UI elements rather than CSS classes, so the tests survive UI redesigns. Each flow leg adds 3-5 testids on a budget.

### Pytest markers and what runs where

| Marker | Tests | Default `pytest` | CI |
|---|---|---|---|
| (no marker) | unit tests | runs | runs |
| `live` | hits real LLM APIs (paid) | skipped | skipped |
| `browser` | Playwright **functional** flow tests | skipped (run with `-m browser`) | runs `-m browser` |
| `pixel` | Playwright **visual** snapshot regression | skipped (run with `-m pixel`) | **never runs** |

Default `addopts` deselects `live`, `browser`, AND `pixel` so a bare `pytest` runs only unit tests. Override at the CLI to opt in: `pytest -m browser`, `pytest -m pixel`, or `pytest -m "browser or pixel"`.

### Visual snapshot workflow (local-only)

Snapshot baselines under `tests/browser/__snapshots__/` are **gitignored** — they are local regression artifacts, not shared source. The flow:

1. **First run on a fresh checkout**: `pytest -m pixel --snapshot-update` (or `UPDATE_SNAPSHOTS=1 pytest -m pixel`). The helper writes a baseline PNG for each scenario (3 areas × 2 states × 2 themes = 12 baselines). Missing-baseline auto-generation also kicks in on a bare `pytest -m pixel` first run, but `--snapshot-update` is the explicit affordance.
2. **Subsequent runs**: `pytest -m pixel`. Each test compares its current screenshot against the locally-stored baseline; >2% pixel diff fails and writes `<name>-actual.png` + `<name>-diff.png` next to the baseline for inspection.
3. **After an intentional layout change**: `pytest -m pixel --snapshot-update` to regenerate.
4. **CI**: never runs `-m pixel`. Functional Playwright coverage is provided by `-m browser`. The pixel suite has no shared baselines to compare against in CI by design — pixel diffs are a developer's local feedback loop, not a regression gate.

If the visual-snapshot suite ever needs CI-side regression detection, the right move is to capture a fresh baseline on each run, store it as a build artifact, and compare against the previous successful build's artifact — not to commit baselines to git.

---

## Design system

The web UI uses a token-driven design system (mission M04 / flight F2). Both
themes (`[data-theme="dark"]` and `[data-theme="light"]`) live in
`the_one/interfaces/web/static/css/tokens.css` and share token names; only
values differ per theme. Component CSS files reference tokens — no hex/rgba
literals leak into component rules (enforced by a grep gate in CI; only
`tokens.css`, `fonts.css`, and SVG `data:` URLs may contain literals).

### Affordance patterns

The interface uses six recurring affordance patterns. Each is identifiable by its visual treatment and intended interaction class. New UI work should compose with these patterns rather than invent parallel idioms. Where the live UI diverges from these descriptions today, the divergence is pre-realization debt to be resolved during the per-area alignment flights (F4 Chat / F5 Studio / F6 Administration).

1. **Info banner** — neutral disclosure inside a surface. Documented pattern: background `var(--surface-elevated)`, border `1px solid var(--border)`, text `var(--fg-secondary)`. Live UI today: `.admin-note` uses `var(--surface)` and the `.chat-no-providers` banner uses a cyan-accented gradient — both are pre-realization variants. Used at the top of provider lists, agent editors, and admin sub-pages to surface non-actionable context.

2. **Outlined-cyan** — secondary action; reads as available but de-emphasized. Pattern: background transparent, border `1px solid var(--accent)`, text `var(--accent)`, hover background `var(--accent-translucent)`. Live UI today: `.new-chat` (chat sidebar's "+ new" button), `.new-entity-btn` (studio + admin page-headers, F6 leg 02 lift from `.new-agent-btn`). Future use: "edit", "configure", and similar non-CTA actions across all areas.

3. **Filled-cyan CTA** — primary action; reads as the recommended next step. Pattern: background `var(--accent)`, text `var(--fg-on-accent)`, hover via `filter: brightness(1.1)` or explicit hover token. Used for "save", "submit", "create" — one CTA per page is the convention.

4. **Muted-default-then-glow destructive** — irreversible action; reads as recessive at idle, glows on focus/confirm. Pattern: transparent background at idle, text/border `var(--status-danger-muted)`. Confirm state (after first click): background `var(--status-danger)`, text `var(--fg-on-danger)`, glow `var(--status-danger-glow)`. Used for delete affordances on session items, agent items, chip-removes. Never used for routine actions.

5. **Neutral utility** — small, non-categorical action with no surrounding chrome. Pattern: background transparent, text `var(--fg-secondary)`, hover text `var(--fg)`, no border. Examples: inline `x` icon buttons, dropdown-chevron indicators, decorative scroll affordances. NOT for "+ new" buttons (those are outlined-cyan, pattern 2).

6. **Palette-island rule** — components that establish their own chrome (the `#app-topbar` post-F3) declare their own `--nav-*` palette family in `tokens.css`. The body palette and the chrome palette MUST NOT share token names. Rule: never reach into chrome tokens from body components or vice versa. (The `--nav-*` token-family name is retained for continuity even though F3 replaced the original left nav rail with the topbar app-picker; the rule applies to chrome surfaces generally, not to a specific layout.)

#### Affordance vocabulary (shared class catalog)

The F4 leg 02 lift consolidates per-area duplications into shared primitives in `components.css`. Templates compose the shared class with the legacy area-specific class so existing test selectors and styling hooks keep working.

**Shared class catalog** (in `components.css` `@layer components`):
- `.list-item` + `.list-item-delete` — sidebar/category list rows with a focus-within-revealed inline delete affordance. Used in chat (`.session-item`), studio (`.agent-item`), admin (`.admin-category-item`).
- `.field-row` + `.field-input` + `.field-textarea` + `.field-select` — editable form rows with label + input. Used in studio (agent editor) and admin (provider form). Note: admin's `.admin-field-row` (read-only field-VALUE display, e.g., encryption status) is a DIFFERENT pattern and remains admin-only — distinct widths (label 120px vs 100px) and read-only `<div>` value vs editable `<input>`.
- `.section-title` (with `// PREFIX` `::before`) — section headers in editor / form contexts.
- `.btn-outlined-cyan` — secondary affordance buttons (transparent + 1px solid accent border).
- `.btn-filled-cyan` — primary CTAs (accent fill + glow).
- `.btn-muted-destructive` — delete-confirm-style buttons (muted danger color until hover).
- `.chip` + `.chip-remove` — tag-like rows (currently studio-only; lifted for vocabulary completeness).
- `.empty-state` — empty-list / empty-canvas messaging (4 active sites: `agent-empty`, `editor-empty`, `admin-provider-empty`, `admin-pf-models-empty`; the dead `chat-welcome-empty` rule was removed in this leg with no JS emitter).
- `.entity-tile` + `.entity-tile-name` + `.entity-tile-description` + `.entity-tile-meta` + `.entity-tile-badge` + `.entity-tile-grid` — CSS-grid tile primitive for area inventories. **Renamed from `.agent-tile` family in F6 leg 02** (no composition aliases retained — breaking rename). Two consumers: studio's agent inventory (`<button class="entity-tile agent-item">...</button>` per agent — composes the legacy `.agent-item` class for selector continuity) and admin's provider inventory (`<button class="entity-tile provider-tile">...</button>`). DOM: tile is a single `<button>` (no wrap-with-siblings sibling-X pattern — F5 HAT removed the per-tile X delete in favor of editor-only Danger Zone deletion). Tile content slots: `.entity-tile-name` (large bold), `.entity-tile-description` (2-line clamp; studio uses it for agent description), `.entity-tile-meta` (monospace, smaller, muted; studio uses "{provider} · {model}", admin uses base_url snippet or "—"), `.entity-tile-badge` (top-right absolute-positioned slot for type badges; admin uses for provider type — composes with admin's per-type color rules `.admin-provider-badge--{type}`). Test-attribute placement: `data-testid` (e.g. `agent-item`, `provider-card`), `data-id` / `data-name`, `aria-selected="true|false"` on the tile button. ARIA: grid container uses `role="listbox"`; tiles use `role="option"`. `.entity-tile-grid` is the canonical CSS-grid layout (`grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`) — un-area-scoped and consumed by both areas. Tile delete is NOT a per-tile affordance — clicking a tile navigates to its editor; deletion lives in the editor's Danger Zone (see `.danger-zone` entry below).
- **Confirm-delete (in-place two-step)** — `App.confirmDelete(itemEl, onConfirm, opts?)` in `static/js/confirm.js` (F5 leg 02). The single canonical helper for two-step destructive confirms: first call adds `.confirm-delete` to `itemEl`, swaps the title text (`opts.titleSelector`, default `[data-confirm-title]`) to `opts.confirmLabel` (default `'Confirm delete?'`), starts an `opts.revertMs` (default 3000) timer that restores the original on expiry. Second call within the timer window invokes `onConfirm(itemEl, revertFn)` — the helper passes `revertFn` so transport-failure callers can roll the UI back. Original-title capture happens ONLY in the first-click branch and is stored on `itemEl._confirmOriginalTitle` (capturing on every call would record the placeholder text on the second click, and a subsequent revert would overwrite the user's data). Title-element hook: callers add `<span data-confirm-title>` around the visible label text. **Four permanent consumers** post-F6: chat session items (`.session-item` parent, `.session-item-title` inner — uses default selector via title's data-attribute), studio agent editor's `Delete Agent` (`<button class="btn-muted-destructive delete-btn"><span data-confirm-title>Delete Agent</span></button>` — F6 leg 04 migration from inline two-step), admin's provider editor `Delete Provider` (`<button class="btn-muted-destructive delete-btn"><span data-confirm-title>Delete Provider</span></button>` — F6 leg 04), admin's system-page `Rotate Encryption Key` (F6 HAT migration; uses `confirmLabel: 'Confirm Rotate?'`). All editor consumers pass `confirmLabel: 'Confirm Delete?'` (capital-D) for label parity. Canonical armed-state class is `.confirm-delete` (NOT `.confirm` — F6 leg 04 rename); CSS rules at `components.css` cover both `.list-item.confirm-delete` (chat sidebar) and `.delete-btn.confirm-delete` (editor buttons). **Keydown-bubble guard is the parent activatable element's responsibility, NOT the helper's** — the parent applies `if (e.target !== el) return;` in its keydown listener so descendant focusable children don't bubble to fire the parent's activation. **The agent-tile per-tile X-button is gone** — F5 HAT removed it; deletion is centralized to the editor's Danger Zone. **Hard-block precedes confirm**: when the action would orphan related entities (admin's provider-with-active-agents), surface a sibling `.action-blocked-message` banner BEFORE invoking the helper (see "Action-blocked message" entry below); the confirm flow only runs when the action is safe.
- `.section-nav` + `.section-nav-header` + `.section-nav-item` — sidebar sub-section navigation. Vertical list of `<button class="section-nav-item">` elements representing in-area sections. The container uses `role="group"` (NOT `role="tablist"` — these sections have side-effects like URL change and content rerender, and are persistent destinations rather than tab-like alternative views of the same data). The "active" button carries `aria-current="page"` AND `tabindex="0"`; the others carry `tabindex="-1"` (roving tabindex, single-tabstop into the group). Keyboard contract: Tab into the group lands on the active button; Up/Down arrows move focus between buttons (wrapping); Home/End jump to first/last; Enter or Space (or click) commits — fires the `onSelect(sectionId)` callback. **Manual activation**: arrow-key navigation moves focus only; activation requires Enter/Space/click. Two consumers: studio's Agents/Knowledge/Tools sidebar (F5 leg 01) and admin's System/LLM Providers sidebar (F6 leg 01 migration from `.admin-category-item`). Helpers: **`App.layout.renderSectionNav(container, items, active, {onSelect, header, ariaLabel})` + `App.layout.updateActiveSection(container, active)`** in `static/js/areas/layout/section-nav.js` (lifted from `App.studio.*` namespace in F6 leg 01 to the area-agnostic `App.layout.*` so admin can consume the same helper). Each consumer passes its own `items` array + `header` text + `ariaLabel` — no values hardcoded in the helper. **Single-mount-per-container contract**: the helper sets `className` on the passed container, so callers MUST pass a child element (e.g., `<div class="admin-section-nav">`) rather than the area panel itself, otherwise the area scoping class (`.area-admin` / `.area-studio`) gets clobbered. **Section nav vs. tablist distinction (F5 leg 03)**: section navigation (this entry) is for *persistent destinations* — sections occupy distinct URL spaces (`#studio/agents`, `#studio/knowledge`, `#studio/tools`) and have side-effects like content rerender. The tab idiom (next entry) is for *within-entity views* — tabs are alternative facets of the same entity (the agent editor's General/Knowledge/Tools tabs all describe the same agent under `#studio/agents/{name}/{tab}`). Section nav uses `role="group"` with arrow-key roving focus; the tab idiom uses `role="tablist"` with arrow-key roving focus AND manual activation. Don't confuse the two — section nav inside the editor would be wrong (sections are persistent destinations, not within-entity views), and tablist for the sidebar would be wrong (each section has its own URL and its own data, not a different facet of the same data).
- **Tab idiom** — `.tablist` + `.tab` + `.tabpanel` (F5 leg 03). The codebase's first canonical tab vocabulary, established for the studio agent editor's General / Knowledge / Tools tabs. DOM shape: `<div role="tablist" class="tablist" aria-label="...">` containing `<button role="tab" class="tab" aria-controls="<panel-id>" data-tab-id="<short-id>" aria-selected="true|false" tabindex="0|-1">` elements, followed by `<div role="tabpanel" class="tabpanel" id="<panel-id>" data-tab-id="<short-id>" hidden>` panels. Only one panel is unhidden at a time (`[hidden]` controls visibility via `display: none`). **Manual activation contract** (W3C ARIA Authoring Practices for tabs whose activation has side effects): Arrow Left/Right and Home/End move focus + visual highlight ONLY — the URL does not mutate, `aria-selected` does not toggle, panel visibility stays put. Enter or Space (or click) on the focused tab commits — fires `onChange(tabId)`, swaps `[hidden]` on panels, updates `aria-selected` and roving `tabindex`. **Roving tabindex**: only the active tab carries `tabindex="0"`; the others carry `tabindex="-1"` (excluded from natural Tab order, but `.focus()` calls still land on them — that's how arrow-key navigation moves focus between tabs without losing the roving-tabindex contract). Roving tabindex updates only on activation, not on arrow nav. Helper: `App.tabs(tablistEl, panelsEl, {onChange, initial})` in `static/js/tabs.js` returns `{activate(tabId), getActive()}` for imperative control. Tab/panel id resolution prefers the short `data-tab-id` over `aria-controls` / `id` so callers can pass logical ids (`'general'`) without leaking DOM-id details. Why manual (not auto-on-arrow) activation: arrow-key auto-activation would mutate the URL on every keypress (Right arrow rotates through three URL states), polluting browser history even with `replaceState` and aligning poorly with screen-reader exploration patterns. Consumed in F5 leg 03 by the agent editor; future tabbed surfaces (admin's provider editor in F6 if needed) inherit the helper ready-to-use.
- **Editor header** — `.editor-header` + `.editor-header-text` + `.editor-title` + `.editor-subtitle` (F5 leg 03). Canonical entity-name + description block above an editor's tablist (or other content). Two consumers: studio's agent editor + admin's provider editor (F6 leg 03 — provider-editor.js consumes; title shows provider name, subtitle shows `{type} · {base_url}` in edit mode, omitted in create mode). DOM shape: `<div class="editor-header"><div class="editor-header-text"><h1 class="editor-title">{name}</h1><p class="editor-subtitle">{description}</p></div><div class="form-actions">...action cluster...</div></div>`. Flex layout — name/description on the left flex, action cluster on the right; bottom-border separator; padding 12px 20px. Designed to compose with `.form-actions` for the right-aligned button cluster.
- **Form actions** — `.form-actions` (F5 leg 03). Right-aligned button cluster. Used by the agent editor's `[← Back] [Delete] [Save] <error>` cluster inside `.editor-header`; reusable for future modal `.modal-actions` composition (F5 leg 04 will land `.modal-overlay` + `.modal-dialog` + `.modal-actions` for `App.confirmDialog`, where `.modal-actions` composes onto `.form-actions` since both are right-aligned button rows). Includes a `.editor-error` selector inside the cluster for inline error text. Designed to be theme- and area-agnostic; per-area button cosmetics (`.btn-filled-cyan`, `.btn-outlined-cyan`, `.btn-muted-destructive`) compose onto the cluster's children.
- **Test result** — `.test-result` + `.test-result-pending` + `.test-result-ok` + `.test-result-fail` (F5 leg 03 + F6 leg 03 `-pending` addition). Canonical span for connectivity-test results, used by studio's agent editor General-tab Test button + admin's provider editor Connection-section Test button (F6 leg 03 migration from `.admin-pf-test-*`). Pattern: container `<div class="test-result" aria-live="polite">`; in-flight content `<span class="test-result-pending">Testing…</span>`; success `<span class="test-result-ok">✓ {detail}</span>`; failure `<span class="test-result-fail">✗ {detail}</span>`. Status modifiers use the existing `--status-success` / `--status-danger` / `--fg-secondary` design tokens. Generic by design — area-agnostic. Pairs with the JS pattern: read the LIVE provider-select form value (NOT the persisted config) to support unsaved provider changes; surface a flash via `App.showFlash(container, detail, isError)`.
- **Confirm dialog (modal)** — `.modal-overlay` + `.modal-dialog` + `.modal-actions` (F5 leg 04). Canonical modal-blocking-decision primitive, paired with `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` in `static/js/dialog.js`. DOM shape: `<div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="<title-id>" aria-describedby="<message-id>"><div class="modal-dialog"><h2 class="modal-dialog-title">…</h2><p class="modal-dialog-message">…</p><div class="modal-actions form-actions">[Cancel][Confirm]</div></div></div>`. **`.modal-actions` composes onto `.form-actions`** via multi-class on the container (`class="modal-actions form-actions"`) so the existing `.form-actions` right-aligned layout applies; the `.modal-actions` class itself is currently a documentation/grep alias with no extra rules — the composition pattern is documented here so future modals are unambiguous about which side carries layout. **Defaults**: `title='Unsaved changes'`, `message='You have unsaved changes. Continue without saving?'`, `confirmText='Continue'`, `cancelText='Stay'`. The wording avoids the false-promise of "Discard" — the helper navigates without auto-reverting form state, so "Continue/Stay" reads more accurately than "Discard/Cancel". **Keyboard contract**: Escape calls `onCancel` then closes; Enter calls `onConfirm` then closes (skipped when focus is in a `<textarea>` so newline insertion still works); Tab and Shift-Tab implement a **full focus-trap** — focus cycles within the dialog's focusable descendants and wraps at both ends. **Restore-focus on close**: helper captures `document.activeElement` on open and refocuses it on close; if the trigger was removed from the DOM (e.g., a deleted tile), `.focus()` falls back to body. **Singleton**: only one dialog is open at a time; second `App.confirmDialog` call while one is open is a no-op + `console.warn('App.confirmDialog: already open; second call ignored.')` — surfaces spurious double-dispatch in dev/test. **Click-on-overlay is a deliberate no-op** (does NOT call `onCancel`); requires explicit Cancel/Escape. Prevents accidental dismissal from a stray outside-click. **Capture-phase keydown** (`document.addEventListener('keydown', ..., true)`) so the modal sees keys before any focused-field listener can swallow them. **Distinct from `App.confirmDelete`** — `confirmDelete` is the in-place two-step destructive confirm (single action, single agent/session); `confirmDialog` is the blocking modal for multi-option / unsaved-changes decisions. **Tile X-button delete on a dirty selected agent does NOT layer this dialog** — the X-button is itself an `App.confirmDelete` two-step flow with explicit user intent; layering an additional "you have unsaved changes" modal on top is UX clutter (the user is opting into a destructive action that obviously discards everything about that agent, including unsaved edits). Deliberate non-gate. Consumers (F5 leg 04): studio's `selectAgent`, `enterCreateMode`, `handleBack`, section-nav `onSelect` (only when in agents+selected-agent context), and tab `onBeforeChange` (via the `App.tabs` helper's new `onBeforeChange(tabId, commit)` hook that wraps both click and Enter/Space activation). Future use: any blocking decision modal across all areas.
- **Beforeunload guard** — register-once-in-area-init pattern (F5 leg 04 + F6 leg 04). Two consumer areas: studio + admin. Each registers a single `window.addEventListener('beforeunload', …)` listener at its own `init()` time, gated by its closure `dirty` flag. **Critical**: `init()` runs once per area lifetime (gated by `app.js`'s `initialized[areaId]` check), but `activate()` and `deactivate()` run on every cross-area transition. **Do NOT remove the listener on `deactivate()`** — that would silently break tab-close protection after cross-area round-trips. The closure `dirty` flag handles all cases: when in another area, dirty is `false` because the editor isn't mounted; when in the area with unsaved changes, dirty is `true` and the listener fires `e.preventDefault(); e.returnValue = ''`. **Modern browsers ignore the custom `returnValue` string** and show a generic "Leave site?" dialog. **Multi-area listener safety**: studio + admin each register their own listener; both fire independently on every `beforeunload`; the closure-flag short-circuit makes each a no-op when its own area is clean. **Test pattern**: Playwright's headless Chromium suppresses the native dialog, so dispatch a synthetic `beforeunload` event via `page.evaluate` and inspect `event.defaultPrevented`. **For admin specifically (F6 leg 04)**: the dirty flag lives in admin's orchestrator closure (`admin.js init()`), bridged from the editor sub-module's local flag via the `onDirtyChange(d)` callback the orchestrator passes into `App.admin.renderProviderEditor`. The orchestrator's mirror is the source of truth for navigation gates; the editor sub-module's local flag drives the disabled-button SSoT.

- **Page header** — `.page-header` + `.page-title` + `.new-entity-btn` (F6 leg 02 lift from studio's `.studio-page-header` family; breaking rename, no aliases). Top-of-area-content header bar: title on the left, "+ New {entity}" button on the right. Pattern: `<div class="page-header"><h1 class="page-title">{Label}</h1><button class="btn-outlined-cyan new-entity-btn" data-testid="new-{entity}-btn">{icon} <span>New {Entity}</span></button></div>`. Five consumers post-F6: studio Agents/Knowledge/Tools page-headers (3) + admin LLM Providers + admin System. The "+ New" affordance composes onto `.btn-outlined-cyan` for color/border; the `square-pen` icon is the canonical choice (`App.icon('square-pen')`).
- **Editor section + section divider** — `.editor-section` + `.editor-section + .editor-section` (F6 leg 03 lift from studio's per-area rule). Vertical rhythm + section-divider border for entity editors. Every direct-child `.editor-section` after the first gets a top border + 16px padding-top (sibling-adjacent selector). Studio's agent editor uses these inside `.tabpanel` (which provides 20px horizontal padding); admin's provider editor adds horizontal padding via per-area `.area-admin .editor-section` override since admin has no `.tabpanel` wrapper.
- **Danger Zone** — `.danger-zone` + `.danger-zone-title` (F6 leg 03 lift from studio's `.area-studio .danger-zone-title` rule). Destructive section at the bottom of an entity editor. Markup: `<div class="editor-section danger-zone"><div class="section-title danger-zone-title">Danger Zone</div>{destructive button}{optional .action-blocked-message}</div>`. Two consumers: studio agent editor + admin provider editor. The `.danger-zone-title` color is `var(--status-danger)` to flag the section visually.
- **API-key wrapper** — `.api-key-wrap` + `.api-key-eye` (F6 leg 03 lift from `.admin-pf-password-wrap` / `.admin-pf-eye`). Wrapper for password-typed inputs with a show/hide eye toggle. Pattern: `<div class="api-key-wrap"><input type="password" .../><button class="api-key-eye" type="button" aria-label="Show password">{eye-icon}</button></div>`. Eye-toggle handler swaps `passwordInput.type` between `password` and `text`, swaps `App.icon('eye')` ↔ `App.icon('eye-off')`, updates the `aria-label`. Generic by design — area-agnostic; future API-credential surfaces inherit ready-to-use.
- **Action-blocked message** — `.action-blocked-message` (F6 HAT). Sibling-of-button banner that surfaces "you can't do this right now" messaging WITHOUT deforming the button itself. Pattern: button stays at its idle label + becomes disabled; a sibling `<div class="action-blocked-message" role="status" aria-live="assertive" hidden>` becomes visible (remove `hidden`) with the explanation. Destructive-tinted (left red border + soft danger background). Used by admin's provider-editor Danger Zone for the agent-usage hard-block path (when a provider has agents attached, deletion is blocked). Layout: 10px margin-top from the button; 8px 12px padding; 3px solid `var(--status-danger)` left border; `var(--status-danger-bg-soft)` background; `var(--status-danger)` color. The `[hidden]` attribute is canonical (declarative show/hide via attribute toggle, not class). Pairs with a 3-second auto-revert: `removeAttribute('hidden')` + `setTimeout(() => setAttribute('hidden', ''), 3000)`.
- **Refresh button** — `.refresh-btn` (F6 HAT). Icon-button shape paired with `.btn-outlined-cyan` for color: `display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; svg { width: 14px; height: 14px; }`. Pattern: `<button class="btn-outlined-cyan refresh-btn">{App.icon('refresh-cw')} Refresh</button>`. Used by admin's provider-editor Models panel header (basic-list + Ollama lifecycle). Mirrors `.back-btn` and `.test-provider-btn` shape — three icon-button siblings forming a coherent family.
- **Button size modifiers** — `.btn-sm` + `.btn-lg` + `.btn-xl` (F6 HAT). Optional modifiers overriding the primitive's default padding + font-size + border-radius. Compose onto any of `.btn-outlined-cyan` / `.btn-filled-cyan` / `.btn-muted-destructive`. Defaults (no modifier) keep each primitive's idiomatic size; modifiers come AFTER the primitives in source order so equal-specificity later-wins resolves to them. Sizes: `.btn-sm` = `2px 8px / tiny / 4px-radius` (used by Ollama panel's per-row Load/Unload/Delete + Pull Model + Pull); `.btn-lg` = `8px 20px / body / panel-radius-sm`; `.btn-xl` = `12px 32px / h3 / panel-radius`. Add new size modifiers here when a new consumer earns the lift (≥2 consumers); avoid adding them speculatively. Example: `<button class="btn-outlined-cyan btn-sm">Refresh</button>`.
- **Cancel button** (`.cancel-btn`) — purely a JS testid/grep hook (F6 leg 03). NO canonical CSS rule. Disabled-when-clean opacity comes from `.btn-outlined-cyan:disabled`; the `.cancel-btn` class itself only marks the element for selector convenience. Convention: any "discard the current edit" button in an editor surface composes `class="btn-outlined-cyan cancel-btn"` and adds `data-testid="cancel-{entity}-btn"`.
- **Save button** (`.save-btn`) + **Back button** (`.back-btn`) + **Test-provider button** (`.test-provider-btn`) + **Delete button** (`.delete-btn`) — F5 leg 03 / F6 leg 04 canonical button shapes (lifted from `.area-studio` per-area scoping). All four compose onto the canonical color primitives (`.btn-filled-cyan` for Save, `.btn-outlined-cyan` for Back/Test, `.btn-muted-destructive` for Delete). `.save-btn[disabled]` + `:not([disabled])` opacity hooks key off the `disabled` attribute (Save + Cancel both flip together via `checkDirty()` — see "Dirty-state SSoT" entry below). `.back-btn` and `.test-provider-btn` carry `display: inline-flex; gap: 4px; padding: 4px 10px;` for icon-with-text spacing. `.delete-btn.confirm-delete` is the App.confirmDelete-armed state (full red-fill bg).
- **Dirty-state SSoT** — `disabled` attribute as single source of truth for Save + Cancel buttons (F5 leg 04 + F6 leg 03/04). The closure-local `dirty` flag drives `checkDirty()` which flips both `.save-btn[disabled]` and `.cancel-btn[disabled]` together — never use `.dirty` / `.clean` classes. Pattern: snapshot the form values on editor mount; on every `input`/`change` event, recompute snapshot and compare to baseline; flip both buttons' disabled state. **For F6 admin specifically**: the editor sub-module owns its local `dirty` and bridges to the orchestrator's closure mirror via `callbacks.onDirtyChange(dirty)`. The orchestrator's mirror is the gate for `App.confirmDialog`-protected navigation routes (Back, section-nav). The editor sub-module's flag is the gate for the disabled-button flip. Both reset on editor mount + on successful save.
- **Hydrate-vs-fetch race + stale-then guard** — when an area has hash-deep-linked sub-state but its data is fetched async (chat sessions, studio agents, admin providers), hash hydration may fire BEFORE the data load resolves. **Pattern**: each affected area carries a `_pendingX` field (e.g., `_pendingSelectName` in studio, `_pendingProviderId` in admin); hydrate stores the desired target there; the data-fetch's `.then()` calls `_tryConsumePendingX()` which finds the target in the now-loaded data and selects it. **F6 HAT addition — stale-then guard**: when the user has navigated AWAY from the loading area before the fetch resolves (e.g., clicked Studio while admin's `fetchProviders` is in-flight), the `.then()` handler must check `currentCategory` (or the area-equivalent) before mutating the DOM. Otherwise the late-resolving render clobbers the now-active surface (e.g., admin's grid `.then` would overwrite the System page if hydrate just switched to it). Guard pattern: `if (currentCategory !== 'providers') return;` at the top of `populateProviderGrid`.
- **Bare-area hash redirect** — when the user navigates to bare `#admin` (no sub), the area should redirect to its canonical default sub (`#admin/system`). **Two-piece contract** (F6 HAT fix): (1) the F3 router (`app.js`) calls `syncUrlFromState(areaId, sub)` after BOTH cross-area AND same-area-sub-change hydration to sync the URL with the area's `serializeState()` return value. (2) the area's `hydrateState(null)` MUST reset to its default — for admin, calling `_setCategory('system')` so `serializeState` returns `'system'` and the router's sync rewrites the URL. Without (2), the router's sync would rewrite to whatever sub the area was last on (e.g., `#admin/providers` after the user clicked Settings expecting "go to defaults"). Applies to any area with a default sub-state.

**Utility classes** (in `components.css` `@layer utilities`):
- `.is-hidden { display: none !important; }`
- `.u-flex { display: flex !important; }`
- `.u-block { display: block !important; }`

JavaScript should toggle visibility via `el.classList.toggle('is-hidden', !visible)` rather than writing `el.style.display = ...` inline. The `@layer utilities` declaration in `index.html` is the highest-precedence named layer, so utilities win over `@layer components` and `@layer areas` rules by design.

### Color contrast (WCAG AA)

The F2 design tokens were audited against WCAG 2.1 AA contrast standards on
2026-04-25 (manual + automated). All load-bearing color pairs pass at the
following thresholds:

- **4.5:1** for body text (success criterion 1.4.3)
- **3.0:1** for large text (≥18pt or ≥14pt bold), UI components, and non-text
  contrast (success criterion 1.4.11)

Pair ratios below are computed by `tests/test_design_tokens_a11y.py` using
the canonical WCAG 2.1 sRGB-luminance formula.

#### Dark theme load-bearing pairs

| Pair | Ratio | Threshold | Status |
|------|-------|-----------|--------|
| `--fg` on `--bg` | 15.00:1 | 4.5:1 (body) | PASS |
| `--fg` on `--surface` | 13.18:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--bg` | 5.58:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--surface` | 4.91:1 | 4.5:1 (body) | PASS |
| `--fg-tertiary` on `--bg` | 3.45:1 | 3.0:1 (large/UI) | PASS |
| `--fg-tertiary` on `--surface` | 3.03:1 | 3.0:1 (large/UI) | PASS |
| `--accent` on `--bg` | 10.96:1 | 3.0:1 (UI) | PASS |
| `--accent` on `--surface` | 9.63:1 | 3.0:1 (UI) | PASS |
| `--fg-on-accent` on `--accent` | 11.62:1 | 4.5:1 (body) | PASS |
| `--fg-on-danger` on `--status-danger` | 6.33:1 | 4.5:1 (body) | PASS (retuned to `#000` — see below) |
| `--status-success` on `--bg` | 9.42:1 | 3.0:1 (large/UI) | PASS |
| `--status-warning` on `--bg` | 9.77:1 | 3.0:1 (large/UI) | PASS |
| `--status-danger` on `--bg` | 5.97:1 | 3.0:1 (large/UI) | PASS |
| `--status-danger-muted` on `--bg` | 5.46:1 | 3.0:1 (large/UI) | PASS (idle-state delete affordance, leg 09 HAT) |
| `--status-danger-muted` on `--surface` | 4.80:1 | 3.0:1 (large/UI) | PASS |

#### Light theme load-bearing pairs

| Pair | Ratio | Threshold | Status |
|------|-------|-----------|--------|
| `--fg` on `--bg` | 17.23:1 | 4.5:1 (body) | PASS |
| `--fg` on `--surface` | 17.85:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--bg` | 9.99:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--surface` | 10.35:1 | 4.5:1 (body) | PASS |
| `--fg-tertiary` on `--bg` | 7.31:1 | 4.5:1 (body) | PASS |
| `--fg-tertiary` on `--surface` | 7.58:1 | 4.5:1 (body) | PASS |
| `--fg-muted` on `--bg` | 4.59:1 | 3.0:1 (large/UI) | PASS |
| `--fg-muted` on `--surface` | 4.76:1 | 3.0:1 (large/UI) | PASS |
| `--accent` on `--bg` | 5.17:1 | 3.0:1 (UI) | PASS (retuned cyan-600 → cyan-700) |
| `--accent` on `--surface` | 5.36:1 | 3.0:1 (UI) | PASS |
| `--fg-on-accent` on `--accent` | 5.36:1 | 4.5:1 (body) | PASS |
| `--fg-on-danger` on `--status-danger` | 4.83:1 | 4.5:1 (body) | PASS |
| `--status-success` on `--bg` | 4.84:1 | 4.5:1 (body) | PASS (retuned green-600 → green-700) |
| `--status-warning` on `--bg` | 4.75:1 | 4.5:1 (body) | PASS (retuned yellow-600 → yellow-700) |
| `--status-danger` on `--bg` | 4.66:1 | 4.5:1 (body) | PASS |
| `--status-danger-muted` on `--bg` | 5.16:1 | 3.0:1 (large/UI) | PASS (idle-state delete affordance, leg 09 HAT) |
| `--status-danger-muted` on `--surface` | 5.35:1 | 3.0:1 (large/UI) | PASS |

#### Token retunes (leg 07)

Four token values were retuned during the audit to lift them above the
applicable AA threshold:

- **Light `--accent`**: `#0891b2` (cyan-600) → `#0e7490` (cyan-700). White
  on `#0891b2` reads at 4.46:1 — a body-AA fail when used on filled cyan
  buttons (e.g., `.input-area button`, `.save-btn`). Cyan-700 reads at
  5.36:1. The accent-glow / accent-translucent rgba tokens were updated in
  lockstep so derived shadows, borders, and translucent fills track the
  new accent. `--panel-shadow-glow` cyan tint also updated.
- **Light `--status-success`**: `#16a34a` (green-600) → `#15803d` (green-700).
  Used as status text colour (e.g., model-loaded indicator); green-600 read
  at 3.18:1 (body-AA fail). Green-700 reads at 4.84:1.
- **Light `--status-warning`**: `#ca8a04` (yellow-600) → `#a16207`
  (yellow-700). Used as warning text in studio's VRAM warning and provider
  badges; yellow-600 read at 2.84:1 (body-AA fail). Yellow-700 reads at
  4.75:1.
- **Dark `--fg-on-danger`**: `#ffffff` → `#000000`. White on the bright
  dark-theme `--status-danger: #ff4a4a` reads at 3.32:1 (body-AA fail) on
  delete-confirm buttons. Black reads at 6.33:1. Black-on-bright-red
  remains a strong destructive-action signal, so the change is purely a
  contrast lift, not a design-language shift.

#### Deliberate exceptions

Two tokens are intentionally below body AA (4.5:1) and pinned by tests
that assert "ratio is in the faint band, not zero, not body-AA":

- **`--fg-faint` (dark)**: `#444` on `#0a0a0a` ≈ 2.03:1. Used for
  de-emphasized annotation labels (chat-area telemetry eyebrows
  "in:"/"out:"/"ctx:", env-var hints in admin), disabled placeholders, and
  decorative recessive marks. Never body prose, never an interactive UI
  affordance. Test: `test_fg_faint_dark_is_intentional_low_contrast`.
- **`--fg-faint` (light)**: `#94a3b8` on `#fafbfc` ≈ 2.47:1. Used for the
  same annotation-label / placeholder / decorative contexts as the dark
  counterpart. Test: `test_fg_faint_light_is_intentional_low_contrast`.

Each exception carries a `# DELIBERATE EXCEPTION` comment in the test file
explaining the rationale; the assertion bands trip if a future retune
drifts the value out of "faint" territory.

#### Focus visibility

All `:focus-visible` rules across `base.css`, `chat.css`, `studio.css`,
`admin.css`, and `components.css` use the same pattern:

```css
outline: 1px/2px solid var(--accent);
box-shadow: 0 0 0 3px var(--accent-glow);
```

In dark this resolves to a `#22d3ee` outline + cyan glow; in light it
resolves to a `#0e7490` outline + cyan glow. Both meet the 3:1 non-text
contrast threshold (WCAG 1.4.11) against adjacent surfaces. Manually
verified by tabbing through chat input, send button, and the topbar
app-picker in both themes.

#### Semantic attributes

`role="alert"` (errors) and `role="status"` + `aria-live="polite"` (info)
are set on `.app-flash` elements at creation time
(`the_one/interfaces/web/static/js/app.js`). Other live-region elements
(`.admin-system-flash`, `.admin-pf-test-result`, `.admin-pf-models-list`,
`.studio-vram-warning`) use `aria-live="polite"` and, where applicable,
`role="status"`. Verified intact post-leg-07.

#### Regression net

`tests/test_design_tokens_a11y.py` (36 tests) runs as part of
`pytest tests/` and fails if any token retune breaks AA. **Before changing
a color token, re-run this suite.** The tests hardcode token values to
mirror `tokens.css`; canonical mirror lives in
`tests/browser/design_tokens.py` (`DARK` / `LIGHT` dicts) — both the a11y
suite and any future test that needs to reference token values import
from there. If the CSS values change, update that single module in
lockstep — the brittleness is intentional (lightweight; no CSS-parser
dependency).

`tests/test_token_definitions.py` (1 test, leg 08) parses every
`var(--x)` reference across `static/css/*.css` and asserts each
referenced token has a definition in `tokens.css` or `fonts.css`. Catches
typos like `var(--accnet)` that CSS would silently treat as `unset` —
no visual failure, just a missing colour. Runs as part of `pytest
tests/`.

### Typography scale

Defined in `static/css/fonts.css` as CSS custom properties (theme-agnostic
— typography doesn't vary per theme; the scale lives in `:root`, NOT in
the `[data-theme]` blocks).

**Families** (Geist + Geist Mono, self-hosted, OFL/SIL pinned to
`vercel/geist-font@1.8.0`):

- `--font-family-sans`: `'Geist', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` — UI / prose / body text
- `--font-family-mono`: `'Geist Mono', 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace` — data, code, identifiers, section-header `// PREFIX` cyberpunk markers

**Sizes**:

| Token | Value | Used for |
|-------|-------|----------|
| `--font-size-display` | 24px | Future hero / display text |
| `--font-size-h1` | 18px | Top-level area / editor titles (`.editor-title`) |
| `--font-size-h2` | 16px | Sidebar group headings (`.sidebar h3`) |
| `--font-size-body-lg` | 14px | Default body, controls, primary CTAs |
| `--font-size-body` | 13px | Secondary body, form labels |
| `--font-size-body-sm` | 12px | Tool names, sidebar items, compact rows |
| `--font-size-caption` | 11px | Tool descriptions, captions, badges |
| `--font-size-tiny` | 10px | Section-title `// PREFIX` markers, telemetry |

**Weights**:

| Token | Value |
|-------|-------|
| `--font-weight-regular` | 400 |
| `--font-weight-medium` | 500 |
| `--font-weight-semibold` | 600 |
| `--font-weight-bold` | 700 |

**Line-heights**:

| Token | Value |
|-------|-------|
| `--line-height-tight` | 1.2 |
| `--line-height-normal` | 1.5 |

**Documented exception**: `.admin-category-badge` uses a hard-coded
`font-size: 9px` (one step below `--font-size-tiny`); inline-commented
in `admin.css` because the badge sits beside denser text and needs to
recede smaller than the scale's smallest token. The "Soon" label is the
only text that uses 9px; if a future leg adds another sub-tiny use case
it should be promoted to a token.

### Icon catalog

Lucide icons available via `App.icons.{name}` (returns inline SVG string)
or `App.icon(name)` (with miss-warn). Pinned to `lucide@v0.265.0` (see
`static/js/icons.js` header). All SVGs use `stroke="currentColor"` so
colour inherits from the surrounding context (theme-aware via
`var(--accent)`, `var(--fg-secondary)`, etc.).

| Name | Lucide source | Used in |
|------|---------------|---------|
| `chat` | `message-circle` | topbar app-picker (Chat area option) |
| `studio` | `bot` | topbar app-picker (Studio area option) |
| `admin` | `settings` | topbar app-picker (Admin area option) |
| `plus` | `plus` | new-agent button (Studio sidebar) |
| `x` | `x` | session-delete, agent-delete, chip-remove, password-toggle-close, model-pull-cancel |
| `edit` | `edit` | (curated; future use) |
| `trash` | `trash-2` | (curated; future use) |
| `check` | `check` | (curated; future use) |
| `alert-triangle` | `alert-triangle` | (curated; future use) |
| `alert-circle` | `alert-circle` | (curated; future use) |
| `info` | `info` | (curated; future use) |
| `eye` | `eye` | password-reveal toggle (admin add/edit-provider form, masked state) |
| `eye-off` | `eye-off` | password-reveal toggle (admin add/edit-provider form, revealed state) |
| `refresh` | `refresh-cw` | (curated; future use) |
| `send` | `send` | (curated; future use — chat send button is currently text "Send") |
| `download` | `download` | (curated; future use) |
| `chevron-down` | `chevron-down` | (curated; future use — current dropdown arrows are inline SVG `data:` URLs in CSS) |
| `chevron-right` | `chevron-right` | (curated; future use) |
| `zap` | `zap` | (curated; future use) |
| `sparkles` | `sparkles` | (curated; future use) |
| `menu` | `menu` | app-picker hamburger button (topbar) |

Add a new icon by editing `static/js/icons.js`: append the inlined
single-line SVG markup to the `Icons` object (preserving Lucide's
standard `width="24" height="24" viewBox="0 0 24 24" stroke="currentColor"`
shape) and pin the same release tag. Lucide is MIT-licensed.

CSS sizing: each icon's host element sets a `svg { width: Npx; height: Npx; display: block }` rule (e.g., `.nav-item svg { 20×20 }`,
`.session-item .delete svg { 12×12 }`, `.new-agent-btn svg { 14×14 }`).
Currents include `.nav-item svg` (20×20), `.new-agent-btn svg` (14×14),
`.agent-item-delete svg` (10×10), `.chip-remove svg` (10×10), `.session-item .delete svg` (12×12), `.admin-pf-eye svg` (14×14), `.admin-pf-pull-cancel svg` (12×12).

### App shell

The web UI shell (F3 leg 02) uses a vertical flex-column layout: a fixed-height top bar
across the full viewport width, with a flex-row inner row below containing the sidebar and
main content area.

```
<body>
  <a class="skip-link" href="#main-content">  ← first focusable element, visually hidden until focused
  <header id="app-topbar">                    ← chrome strip; height: var(--topbar-h)
    <h1 class="app-topbar-title">             ← "the-one"; single <h1> per page
    <div class="app-topbar-actions">          ← right side: theme toggle + picker button
      <div class="theme-toggle-compact-mount">
      <button class="app-picker-button">      ← hamburger; aria-haspopup + aria-expanded
    <nav class="app-picker-popover">          ← dropdown; data-open="true/false"
  <div class="app-shell-row">                 ← flex: 1; min-height: 0; overflow: hidden
    <aside id="app-sidebar">                  ← aria-label set per active area
    <main id="main-content" tabindex="-1">   ← skip-link target; tabindex="-1" for programmatic focus
```

#### Top bar

`#app-topbar` uses the `--nav-*` palette island (same chrome tokens as the old nav rail):
`--nav-bg` background, `--nav-border` bottom border, `--nav-fg` / `--nav-fg-active` for
icon and accent colours. The `--topbar-h: 48px` token replaces the old `--nav-w` (rail
width) — same 48 px value, new semantic name.

**Known limitation**: the picker popover uses `position: absolute; right: 16px` from the
topbar. On viewports narrower than ~200px it can overflow off-screen. Acceptable for v1
(the app is desktop-first).

#### App picker contract

The hamburger button (`<button class="app-picker-button">`) toggles an inline `<nav
class="app-picker-popover">` dropdown containing one `<button class="app-picker-option">`
per registered area.

- **Open**: `data-open="true"` on the popover (CSS switches `display: none → block`);
  `aria-expanded="true"` on the picker button; focus moves to the first option.
- **Close**: `data-open="false"`; `aria-expanded="false"`; triggered by: Escape key (focus
  returns to picker button), click-outside, or option selection.
- **Keyboard model**: Enter/Space opens when picker button is focused; ArrowDown / ArrowRight
  advances through options (wraps); ArrowUp / ArrowLeft reverses (wraps); Escape closes and
  returns focus to the button.
- **Active area accent**: the current area's option carries `.active` class → cyan
  `::before` left-border stripe (ported from the old `.nav-item.active::before` treatment).
- **Click-outside guard**: option-click handlers call `e.stopPropagation()` (defensive —
  the click-outside `document.addEventListener` fires on bubble; `stopPropagation` prevents
  a race if the outside listener fires after the option already called `closePicker()`).

All picker wiring (open/close, click-outside, keyboard) is defined INSIDE `renderTopBar()`
so `closePicker` is in shared closure scope — no separate `wirePicker` function (that
pattern introduced a closure-scope hazard in the F3 design-review round 1).

#### Skip-link contract

`<a class="skip-link" href="#main-content">` is the FIRST element in `<body>` (before the
topbar). CSS: `position: absolute; top: -40px;` at rest; `:focus { top: 0; }` to reveal.
Background `var(--accent)`, text `var(--fg-on-accent)` for visibility.

Activating the skip-link sets `location.hash = '#main-content'`, which fires the
`hashchange` listener. The listener bails immediately (`if (!areas[hash]) return`) because
`main-content` is not a registered area hash — the skip-link does NOT force-reset the active
area to chat. `<main id="main-content" tabindex="-1">` receives programmatic focus.

#### Area sidebar label (`sidebarLabel`)

`App.registerArea()` accepts an optional `sidebarLabel` property on the descriptor. After
each `switchTo`, `<aside id="app-sidebar">` receives `aria-label` set to:
- `descriptor.sidebarLabel` if present, OR
- `descriptor.label + ' sidebar'` as fallback.

Current values: chat → `'Chat sessions'`; studio → `'Agent list'`; admin → `'Admin categories'`.

### Hash routing

F3 leg 04 extends URL routing from area-only (`#chat`, `#studio`, `#admin`) to area-plus-sub (`#chat/sessions/<id>`, `#studio/agents/<name>`, `#admin/providers`), enabling browser refresh to restore the user's exact location within each area.

#### URL format

```
#area[/sub]
```

- **area**: one of `chat`, `studio`, `admin`. Required. Defaults to `chat` if absent or unknown.
- **sub**: optional, area-specific:
  - chat: `sessions/<uuid>` (e.g., `#chat/sessions/abc-123`)
  - studio: `agents/<name>` (URL-encoded, e.g., `#studio/agents/my%20agent`)
  - admin: bare category id (e.g., `#admin/providers`, `#admin/system`, `#admin/general`)

`serializeState()` returns the sub WITHOUT the area prefix. The framework (`app.js`) owns the `area/` segment.

#### `serializeState` / `hydrateState` contract

Each area descriptor passed to `App.registerArea()` may optionally define two methods:

```javascript
App.registerArea({
  id, label, icon, order, sidebarLabel,
  init, activate, deactivate,
  serializeState,   // optional: () => string | null  — null/undefined means "no sub"
  hydrateState,     // optional: (sub: string | null) => void
});
```

- **`serializeState()`** — returns the current sub-state string (e.g., `'sessions/<id>'`), or `null` if no sub state to encode. Called by area code to compute the sub before calling `App.router.replaceSub`.
- **`hydrateState(sub)`** — applies a sub-state string to the area (e.g., joins the given session). Called by `switchTo` immediately after `activate`. On cold entry (`activate` just fired async work), `hydrateState` MUST stash a pending target and resolve it when async work completes — it must NOT assume data is ready synchronously.

Areas without `serializeState`/`hydrateState` behave exactly as before.

#### `App.router` namespace

`app.js` exposes two helpers under `window.App.router`:

```javascript
App.router.parseHash(hashString)
// → { area: string|null, sub: string|null }
// Examples:
//   parseHash('#admin/providers') → { area: 'admin', sub: 'providers' }
//   parseHash('#chat')            → { area: 'chat', sub: null }
//   parseHash('')                 → { area: null, sub: null }
//   parseHash('#/something')      → { area: '', sub: 'something' }  ← bailed in listener

App.router.replaceSub(sub)
// Updates the URL sub-state WITHOUT pushing history.
// The area is implicit (currentId). sub=null clears to bare #area.
// Uses history.replaceState — does NOT fire hashchange.
```

#### History semantics

Two navigation modes have distinct history behavior:

| Navigation type | Mechanism | History effect |
|----------------|-----------|----------------|
| Cross-area (picker click, `location.hash = 'admin'`) | `location.hash =` assignment | Pushes new entry |
| Area-internal sub-change (session click, admin category click) | `history.replaceState` | Replaces current entry |

**Critical invariant**: `history.replaceState` does NOT fire `hashchange`, so calling it from inside an option-click handler does not re-enter `switchTo`. If this invariant is ever broken by using `location.hash =` for sub-navigation, a recursion loop results: `switchTo` → `replaceSub` → `hashchange` → `switchTo` → ...

The net effect: pressing browser back exits the area entirely (or returns to the previous area), and does NOT walk back through sub-page history within an area.

#### Lifecycle ordering

- **Cold entry** (first activation of an area, or cross-area navigation):
  `init()` → `activate()` → `hydrateState(sub)`
- **Same-area sub-change** (user was already in this area, hash sub changed):
  `hydrateState(sub)` only — `init` and `activate` do NOT re-fire.
- **No-op** (same area AND same sub): returns immediately.

#### Async hydration pattern

`hydrateState` runs synchronously after `activate` returns, but `activate` may have kicked off async work. Each area handles this differently:

- **Chat**: `hydrateState('sessions/<id>')` stashes `pendingJoinId`. The `session_list` WebSocket message (which fires when the WS opens after `activate`) checks `pendingJoinId` and joins it instead of auto-joining `sessions[0]`.
- **Studio**: `hydrateState('agents/<name>')` stashes `pendingSelectName`. The `loadAll().then(...)` continuation in `init` calls `tryConsumePendingSelect()` before the default-select-first behavior.
- **Admin**: `hydrateState` updates `currentCategory` synchronously. `init` sets `currentCategory='general'`; if hydration sets it to (e.g.) `providers`, there is a brief double-fetch (general then providers). The general fetch's completion checks for `.admin-form` element existence and bails — no visual flicker. Documented as benign.

#### `replaceSub` call sites

Each area calls `App.router.replaceSub(sub)` after every internal sub-state change:

| Area | Trigger | Call site |
|------|---------|-----------|
| chat | Session joined (WS `session_joined` message) | After `currentSessionId = data.session_id` |
| chat | New chat started | After `currentSessionId = null` (clears sub during gap) |
| chat | Session deleted | After `currentSessionId = null` |
| studio | Agent selected | Bottom of `selectAgent(agent)` |
| studio | Create mode entered | Inside `enterCreateMode()` |
| studio | Agent deleted | After `selectedAgent = null` in delete handler |
| admin | Category clicked | Inside `el.onclick` in `renderCategoryList`, before re-render |

### Keyboard operability

F3 leg 03 converts all interactive `<div>`/`<span>` elements to keyboard-operable equivalents. The two patterns used across all areas are:

#### Listbox/option pattern (list rows with child action affordances)

Used where a parent row is clickable AND contains an inline delete affordance (chat session-item, studio agent-item, admin category-item). The nested-button rule prohibits `<button>` inside `<button>`, so the parent stays as a `<div>` with ARIA roles instead.

- **Parent container** (`session-list`, `agent-list`, `admin-category-list`): receives `role="listbox"` and `aria-label="<purpose>"` at init time.
- **Each row** (`session-item`, `agent-item`, `admin-category-item`): `<div role="option" tabindex="0" aria-selected="true|false">`. The row keeps its existing class-based active/hover CSS. A `keydown` listener on each row fires the activation handler on Enter or Space (`e.preventDefault()` suppresses scroll on Space).
- **`aria-selected`** is set at render time inside the list-build loop (not in a separate post-render walk). `highlightActiveSession` / `selectAgent` also update `aria-selected` on all items after activating one.
- **Simplification**: all options use `tabindex="0"` (each adds a Tab stop); no roving tabindex. For ~5–20 items this is WCAG-compliant and simpler than arrow-key navigation. Revisit at ~50 items.
- **Deliberate accepted deviation**: `role="option"` technically SHOULD NOT contain interactive children (the ARIA spec says option is a leaf). In practice, NVDA and VoiceOver handle this correctly — they announce the option, then announce the inner button separately. Document in review if a strict audit requires sibling-restructure instead.

#### Button pattern (inline action affordances)

Used for elements that are purely action-only with no child interactive content — `<span class="delete">` → `<button class="delete" type="button" aria-label="Delete session">`, `<span class="agent-item-delete">` → `<button class="agent-item-delete" type="button" aria-label="Delete agent">`, and three `<span class="chip-remove">` → `<button class="chip-remove" type="button" aria-label="Remove">` sites. No keydown handler needed — native `<button>` activates on Enter (keydown) and Space (keyup) by default.

#### `:focus-within` reveal convention

Hover-only delete affordances (hidden by `display: none` at rest) are revealed via the parent's `:focus-within` selector when the user Tabs into the child button:

```css
/* Before: */
.area-chat .session-item:hover .delete { display: block; }

/* After: */
.area-chat .session-item:hover .delete,
.area-chat .session-item:focus-within .delete { display: block; }
```

The chip-remove (`chip-remove`) is always-visible — no `:focus-within` reveal needed.

#### `:focus-visible` accent-ring convention

Two variants, both using `var(--accent)` (cyan):

- **Inset variant** (list rows with backgrounds — `session-item`, `agent-item`, `admin-category-item`):
  ```css
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  box-shadow: inset 0 0 0 3px var(--accent-glow);
  ```
- **Standard variant** (inline action buttons — `.delete`, `.agent-item-delete`, `.chip-remove`):
  ```css
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px var(--accent-glow);
  ```

#### Button reset for converted `<span>` → `<button>` elements

Any `<span>` converted to `<button>` must neutralize browser button defaults. Add to the element's CSS rule: `background: transparent; border: none; cursor: pointer; padding: 0;` (preserve existing `padding` value if intentional).

#### SVG-resilient chip-remove dispatch

The chip-remove click handler uses `e.target.closest('.chip-remove')` (not `e.target.classList.contains('chip-remove')`). When the button contains an SVG icon, clicking on the SVG yields `e.target = <svg>` — the `classList` check fails silently. `closest()` walks up the DOM and reliably finds the button regardless of which descendant was the click target.

### Theme switching contract

Tri-state preference (`'dark'` | `'light'` | `'auto'`) persisted in
`localStorage` under the key `theme-preference`. The `<html>` element
carries `data-theme="dark"` or `"light"` attribute, applied
synchronously by `static/js/theme.js` BEFORE any stylesheet load — the
`<script>` tag is in `<head>` ahead of `<link rel="stylesheet">` to
avoid FOUC.

**API** (exposed on `App.theme`, defined in `static/js/theme.js`):

- `App.theme.get()` → `'dark'` | `'light'` | `'auto'` — the user's
  stored preference (or `'auto'` if unset).
- `App.theme.resolved()` → `'dark'` | `'light'` — the currently-applied
  theme (reads `data-theme` from `<html>`).  When the preference is
  `'auto'`, this is the OS-resolved value.
- `App.theme.set(pref)` — sets the preference.  `'auto'` removes the
  localStorage key (so the page falls back to OS).  Throws on any other
  value than `'dark'` / `'light'` / `'auto'`.

**Auto-mode resolution**: when preference is `'auto'`, theme.js queries
`matchMedia('(prefers-color-scheme: dark)')` and
`matchMedia('(prefers-color-scheme: light)')`.  Resolution priority:
`dark` if `darkMedia.matches`, else `light` if `lightMedia.matches`,
else `'dark'` (canonical default — the F2 design language is
dark-first).  Live OS-preference changes propagate via `change`
listeners on both media queries; `auto`-mode pages re-apply on the next
frame.

**localStorage**: key `theme-preference`, value `'dark'` | `'light'`
(never `'auto'` — auto removes the key).  Reads/writes wrapped in
try/catch (`safeGet`/`safeSet`/`safeRemove`) so private-browsing or
storage-disabled contexts degrade gracefully to in-memory
non-persistent.

**Test environment**: Playwright's `browser.new_context(color_scheme="no-preference")` (set in `tests/browser/conftest.py`)
makes neither `darkMedia` nor `lightMedia` match, exercising the
canonical-default branch (auto → dark).  To capture the light theme in
a test, call `page.evaluate("App.theme.set('light')")` after navigation
and wait for the next animation frame (`page.wait_for_function("App.theme.resolved() === 'light'")`).  The
`tests/browser/test_visual_snapshots.py` helper `_set_theme(page, theme)`
does this and waits for fonts + paint stability.

#### Visual snapshot regression net

`tests/browser/test_visual_snapshots.py` (12 baselines, leg 08): three UI
areas (chat, studio, admin) × two states (empty, populated) × two themes
(dark, light) = 12 PNG screenshots stored in `tests/browser/__snapshots__/`.
Implementation uses PIL + pixelmatch (the JS-Playwright
`expect(page).to_have_screenshot()` API is not exposed in the Python
binding); tolerance is 2% pixel diff via `pixelmatch`'s
`includeAA=False` mode.  Run via `pytest -m browser tests/browser/`;
regenerate baselines via `pytest -m browser tests/browser/test_visual_snapshots.py --snapshot-update`
(or `UPDATE_SNAPSHOTS=1 pytest ...`).  Baselines are committed to git;
CI runs comparison-only.  On mismatch, the helper writes
`<name>-actual.png` and `<name>-diff.png` next to the baseline for
inspection.

- **Lucide icon pin**: icons are pinned to `lucide-icons/lucide@v0.265.0`. Adding new icons requires fetching from this exact tag — do NOT pull from `main` or `latest`. The pin is what keeps `tests/browser/__snapshots__/` baselines stable.
- **Playwright `color_scheme`**: browser tests pin `color_scheme="no-preference"` so they don't inherit the host OS theme preference. Without this, a CI environment with `prefers-color-scheme: dark` would resolve `auto` to `dark` and produce a different snapshot than a developer's light-mode laptop.

---

## Markdown rendering

Hand-rolled CommonMark-subset library at `static/js/markdown.js`. Public API:

- `App.markdown.parse(text) → AST` — `{type: 'document', children: Node[]}`. Walk the tree to inspect or transform.
- `App.markdown.render(text) → DocumentFragment` — caller appends the fragment to a parent.
- `App.markdown.NodeType` — frozen object with the string constants for all 14 node types.

### AST node shape

`{type: NodeType_value, children?: Node[], value?: string, meta?: object}`. Specific shapes documented in markdown.js header comment.

### Supported subset (v1)

paragraphs, ATX headers (`#` to `######`), fenced code blocks with optional language tag, blockquotes (single level), unordered + ordered lists (one nesting level), horizontal rules (`---` / `***`), emphasis (`*` or `_`), strong (`**` or `__`), inline code (`` ` ``), links (`[text](url)` — including URLs with balanced parens like Wikipedia citations), soft breaks (single `\n`), hard breaks (trailing TWO spaces + `\n`; a single trailing space + `\n` is a soft break, not hard).

### Out of subset (v1 non-goals)

tables, footnotes, definition lists, autolinks (bare URLs), reference-style links, HTML passthrough, recursive nested emphasis. The test corpus locks v1 in; adding any of these requires a new flight or leg with a corresponding test-case expansion.

### Nested-emphasis v1 contract

`***word***` renders as `<em><strong>word</strong></em>` (outer-em-first, inner-strong). Recursive nested emphasis (the full CommonMark "left/right flanking delimiter run" algorithm) is v2 scope. `**bold *with em***` renders as `<strong>bold *with em*</strong>` — the inner `*with em*` is literal text since recursive emphasis is off. The mechanism is an `inEmphasisRun` suppression flag in the inline parser: once an emphasis or strong run opens, emphasis-delimiter recognition is disabled inside it (only inline code, links, soft/hard breaks, plain text are honoured). The closing-delimiter-run scan returns the position such that consuming `delimLen` chars lands at the END of the run, so a 3-char `***` closer for a `**` opener has its leading `*` fall INTO the inner span as literal content.

### XSS guarantee

Renderer constructs DOM via `document.createElement` + `textContent` exclusively. The library NEVER uses `innerHTML` — `grep -n innerHTML markdown.js` returns zero hits (including comments). The icons.js SVG string injection on the code-block copy button is done via `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` to keep the no-innerHTML invariant intact. Link `href` values pass through a scheme allow-list (`http`, `https`, `mailto`, `tel`, `/`, `#`); other schemes (notably `javascript:`, `data:`, `vbscript:`, `file:`) are stripped to `#`. Future contributors cannot accidentally introduce XSS via crafted markdown — the structural property of "no innerHTML anywhere in the markdown pipeline" makes this a compile-time guarantee.

### Robustness contract (streaming-friendly inputs)

`App.markdown.parse(null)`, `parse(undefined)`, and `parse('')` all return `{type: 'document', children: []}` — no exception. `render(null) / render(undefined) / render('')` all return an empty `DocumentFragment`. This is deliberate: streaming callers can pass partial buffers (or a not-yet-arrived text) without try/catch ceremony. Whitespace-only input behaves the same as empty.

### Streaming + flash attachment contract

Callers must attach the rendered `DocumentFragment` (or its host element) to the document tree BEFORE user interaction with the rendered DOM. The code-block copy button's "Copied!" flash uses `App.showFlash(container, msg)` which appends the flash element to the container; if the container is detached, the flash never becomes visible to the user. In leg 05's chat integration this is naturally satisfied (rendered messages are appended to `.messages` which is in the document); test cases must explicitly attach via `document.body.appendChild(host)` before clicking.

### Extension contract

Adding a new construct: (1) add a `NodeType` constant, (2) add the tokeniser/parser case, (3) add the renderer branch, (4) add at least 3 parametrized test cases. All four land together in the same leg or flight. PRs that add a parser case without test cases (or vice versa) fail review.

### Code-block copy-button a11y

`<button class="markdown-copy-btn" aria-label="Copy code" type="button">` with `aria-hidden="true"` on the SVG icon (carried over from the icons.js Lucide template). On click, copies `<code>.textContent` via `navigator.clipboard.writeText`; on success, emits a "Copied!" flash via `App.showFlash`; on failure (clipboard permission denied), emits a "Copy failed" error flash. Keyboard-reachable via Tab (the button is in the natural tab order); `:focus-within` on the `.markdown-code-wrap` reveals the button so keyboard users see it before activating, and `:hover` on the button itself keeps it visible if the pointer leaves the wrap (defence-in-depth).

### Chat integration

`App.chat.renderMessage(cls, text, opts)` renders assistant messages via `App.markdown.render(text)` by default (no opt-in needed). User, tool, and system messages stay `textContent` — markdown is assistant-only. Detection uses a first-token whitespace split (`cls.split(' ')[0] === 'assistant'`) so a hypothetical `'assistant-error'` composite would NOT trigger markdown rendering; only the bare `'assistant'` first token does.

Pass `{ renderMarkdown: false }` to force textContent — used by the streaming-accumulation path so chunk-by-chunk text appends as plain text. On the `done` event (and on every streaming-bubble reset boundary — `tool_call`, `tool_result`, direct-action `assistant`), `finalizeStreamingBubble()` swaps the accumulated text for the markdown-rendered DocumentFragment. The helper extracts the buffer via `currentStreamingMsg.textContent` (not `firstChild.nodeValue`) so the algorithm is robust to future structural changes; it clears the closure pointer via `void 0` so a stray bare `currentStreamingMsg = null` reset literal never appears outside the `var` declaration.

The same default applies to historical assistant messages on session-rejoin (`renderHistory` → `addMsg('assistant', ...)` → `renderMessage` → markdown). The persistence contract (leg 04: synthesized assistant `Message` added to `session.history` server-side) carries through cleanly: streamed markdown shows on first send AND on rejoin.

Mid-stream markdown rendering is intentionally NOT supported — partial markdown syntax has no canonical semantics (`**bold` mid-token has no end). The streaming path uses `textContent` accumulation followed by a single swap on `done`. Block-element resets in `static/css/chat.css` (scoped under `.area-chat .msg.assistant`) strip default top/bottom margins on `<p>`, `<ul>`, `<ol>`, `<pre>`, `<blockquote>` so paragraph-style markdown answers don't shift bubble heights from browser defaults.

---

## Streaming protocol

F4 leg 04 added a streaming path through the LLM stack so assistant content fans out to the chat client chunk-by-chunk during generation. The protocol is provider-agnostic at the agent layer; per-provider native streaming sits behind a single `LLMProvider.stream(...)` method.

### `LLMProvider.stream(...)`

```python
async def stream(
    self,
    messages: list[Message],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
) -> AsyncIterator[StreamChunk]
```

**NOT abstract** — the base class supplies a default implementation that calls `complete()` and yields exactly one `StreamChunk(is_final=True, ...)`. Forward-compat for any future provider that doesn't natively stream. Subclasses MAY override for native chunk delivery.

### `StreamChunk` shape

```python
@dataclass
class StreamChunk:
    content: str = ""               # NEW tokens since the last chunk; delta semantics, NOT cumulative
    is_final: bool = False           # True only on the final chunk
    tool_calls: list[ToolCall] = []  # populated on final chunk
    usage: TokenUsage | None = None  # populated on final chunk where exposed
    message: Message | None = None   # populated on final chunk; the synthesised assistant Message
```

**Delta semantics**: `content` is the NEW tokens for that chunk, NOT cumulative. The agent accumulates by string concatenation. The final chunk MAY carry a content delta (some providers emit a stop-event with trailing text); the agent's accumulator handles that by checking `chunk.content` regardless of `is_final`.

**Final-chunk contract**: providers populate `message` with the synthesised assistant `Message` so `Agent.step` can prefer it over rebuilding from accumulator state. When `message` is None on the final chunk, the agent rebuilds from accumulated `content` + `tool_calls` + `usage`.

### Per-provider streaming notes

- **Anthropic** (`anthropic_provider.py`): native streaming via `client.messages.stream(...)`. Yields `text_stream` deltas in real time; final message comes from `stream.get_final_message()` (text content + `tool_use` blocks + usage). **Ports the F3 `BadRequestError` temperature-retry**: catches `BadRequestError` containing "temperature", strips the kwarg, retries once. Gated by a `yielded_any` flag so the retry is only safe BEFORE any chunk has emitted (post-yield retries would duplicate output to the consumer; in practice Anthropic raises pre-stream, so the gate is defence-in-depth). The shared `_build_kwargs` helper DRYs the retry so `complete()` and `stream()` share a single kwargs construction path.
- **OpenAI** (`openai_provider.py`): native streaming via `chat.completions.create(stream=True, stream_options={"include_usage": True}, ...)`. The `include_usage` flag is **required** — without it the trailing metadata-only chunk has no `usage` field and the F4 telemetry overlay's end-of-stream update breaks. Tool-call deltas accumulate by `index` and emit on the final chunk.
- **Ollama** (`ollama_provider.py` + `ollama_api.chat_stream`): native streaming via the new `ollama_api.chat_stream(provider_url, body) → AsyncIterator[dict]` SSE helper. Wire format is **true SSE** (`data: {...}` lines + `data: [DONE]` terminator), distinct from `pull_model`'s JSONL. The provider consumes the parsed dicts and reuses the OpenAI-shape tool-call accumulation pattern (the Ollama OpenAI-compatible endpoint emits the same chunk shape).
- **Mock** (`mock.py`): honours a new `config["stream_chunks"]: list[str]` option. When set (non-empty list), `stream()` yields each chunk with the existing `delay_ms` between deltas; the final chunk synthesises a `Message` from accumulated content + the configured `response.tool_calls`. When `stream_chunks` is unset/empty, falls back to the default-impl path **inline** (calls `self.complete()` + yields one final chunk — NOT `super().stream(...)` delegation, for clarity and to avoid async-generator delegation overhead).

### `Agent.step` `on_chunk` callback

```python
async def step(
    self,
    user_input: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> AsyncIterator[Message]
```

Internally calls `self.llm.stream(...)` and accumulates content per iteration. When `on_chunk` is provided, it is invoked once per content delta during streaming. The Message-yielding contract is unchanged for callers that don't pass `on_chunk` — chunks fan out internally but only the synthesised final `Message` flows up via `yield`. The direct-action shortcut path bypasses the LLM entirely so `on_chunk` is never invoked there.

### WS event vocabulary

| Event | When | Direction |
|------|-----|-----------|
| `assistant_chunk` | Per-content-delta during streaming | server → client |
| `assistant` | Direct-action shortcut path only (no chunks fired) | server → client |
| `tool_call` | Tool-call emitted by the model (non-streamed) | server → client |
| `tool_result` | Tool execution result | server → client |
| `usage` | Token usage on each iteration's final chunk | server → client |
| `done` | End of agent step | server → client |

The streaming WS contract is **chunks-only-no-final-assistant**: when the chunk path fires, the legacy `assistant` event is suppressed server-side. The client already has the accumulated text via the chunk stream. The legacy `assistant` event survives for the direct-action shortcut path (early-return in `Agent.step` before any LLM call).

### `chunks_seen` invariant in `_process_and_broadcast`

The server distinguishes streaming from direct-action via a per-iteration `chunks_seen` flag captured in the agent-step closure. The flag is set inside `_broadcast_chunk` (the callback passed to `agent.step`), and reset **unconditionally at the end of each Role.ASSISTANT block** in the `async for msg in agent.step(...)` loop. The unconditional reset matters for multi-iteration agent loops: a tool-call-only iteration (empty `msg.content`, non-empty `msg.tool_calls`) must still reset the flag for iteration N+1. Resetting inside `if msg.content:` would skip the reset on tool-call-only responses and incorrectly carry `chunks_seen=True` into the next iteration.

### Persistence contract

The synthesised final assistant `Message` is **NOT broadcast** as `{"type": "assistant"}` over the WS during streaming (the client already has the text). It IS:

- Appended to `session.history` via `session.add_event(event)` so session rejoin / refresh re-renders the assistant text from server-side history.
- Appended to `result_messages` so the HTTP API caller (POST /api/sessions/{id}/messages) receives the full message list.

This split — stream-the-deltas-over-WS, persist-the-full-message-server-side — is the F4 leg-04 contract. Browser test `test_streaming_message_persists_to_history` enforces it end-to-end: send a streaming message, reload the page, and assert the assistant text re-appears from history.

### chat.js wire-up (option B minimal rendering)

The chat.js wire-up renders chunks via a `currentStreamingMsg` pointer that holds the current assistant bubble. First `assistant_chunk`: clear the thinking indicator, mint a fresh `<div class="msg assistant">` + attribution (built via `App.chat.renderMessage('assistant', '', { renderMarkdown: false })` so `textContent` semantics hold during accumulation), store the bubble pointer. Subsequent chunks: append the delta to the bubble's text node. At every streaming-bubble reset boundary (`tool_call`, `tool_result`, direct-action `assistant`, AND `done`) the wire-up calls `finalizeStreamingBubble()` — leg-05 — which swaps the accumulated `textContent` buffer for the markdown-rendered `DocumentFragment` and clears the pointer. Iteration N+1 (in a multi-iteration agent loop) therefore lands chunks in a fresh bubble after each iteration boundary, with the closed iteration's bubble already markdown-rendered.

---

## Provider type extension checklist

To add a new LLM provider type, six layers must coordinate. Missing any one of them causes either silent rejection (validation) or runtime errors.

> **History**: The M04 flight that added the `mock` provider type initially missed the SQLite CHECK constraint (#4 below) during state-machine reachability audit. First test run failed with `IntegrityError: CHECK constraint failed`, requiring schema migration v6. The checklist below is the post-incident enumeration.

1. **Pydantic `Literal`** — `db/models.py` `LLMProviderConfig.type`. Add the new value to the `Literal[...]` tuple. Without this, `model_validate` rejects.
2. **`_PROVIDER_TYPE_MAP`** — `agent/factory.py`. Add `"<type>": "<registry-name>"`. Without this, `AgentFactory.create()` raises `ValueError` for agents pointing at the new type.
3. **Registry `loaders` dict** — `llm/registry.py:_try_load_builtin`. Add `"<type>": lambda: __import__("the_one.llm.<provider_module>", fromlist=["_"])`. Without this, `get_provider("<type>")` raises a misleading `ImportError("requires extra dependencies")`.
4. **SQLite `CHECK` constraint** — `db/schema.py` (table definition AND migration). The `llm_providers` table's `CHECK (type IN (...))` clause hard-codes allowed values. Adding a new type requires a schema migration (see v6 for the pattern: `PRAGMA foreign_keys=OFF` + table rebuild). Without this, `INSERT` fails with `IntegrityError: CHECK constraint failed`.
5. **API gating / branches** — `interfaces/web/api.py`:
   - `create_provider` and `update_provider` — add type-specific gating if the new type has a precondition (e.g., dev-mode flag for `mock`)
   - `test_provider` — add a branch returning health/test result for the new type
   - `list_provider_models` — add a branch returning the model list (may query an upstream API or read from `LLMProviderConfig.config`)
   - `GET /api/providers/types` — include or exclude based on any feature gating
6. **Frontend handling** — `interfaces/web/static/js/areas/admin.js`:
   - `PROVIDER_TYPES` is fetched from `/api/providers/types` (post-leg-02), so the type appears in the dropdown when allowed by the API
   - Add `TYPE_DEFAULTS["<type>"] = { base_url, showBaseUrl, showApiKey }` (unconditional — needed for editing existing providers even if the type is later hidden from creation)
   - Add `<type>` to the `KNOWN_BADGE_TYPES` array in `admin.js` (so the renderer emits `.admin-provider-badge--<type>`) and add a `--badge-<type>` token in `tokens.css` plus the matching `.admin-provider-badge--<type>` rule in `admin.css` (post-leg-02 the badge styling is CSS-driven; no JS color literals)

When all six layers are aligned, an integration test posting a provider with the new type round-trips successfully through DB persistence, factory resolution, and UI rendering.

