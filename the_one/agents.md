# agents.md

Development-facing architecture reference for the-one. This file describes the **target architecture** — the structure being implemented during the Structural Foundation mission. It is not loaded at runtime.

For usage, commands, and conventions, see `CLAUDE.md`.

---

## Architecture Overview

The-one is a self-modifying LLM agent built without frameworks. Four layers compose bottom-up:

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

Key properties: `data_dir` (`~/.the-one`), `workspace_dir` (`/workspace`), `agents_dir` (`data_dir / "agents"`), `db_path` (`data_dir / "the-one.db"`).

### `the_one/encryption.py`

Fernet-based encryption for API keys stored in the database. Generates and caches an `Encryptor` per `data_dir`. Provides an `install_key()` helper plus a public `key_path` property; the API rotation path (`POST /api/encryption/rotate`) re-encrypts all provider credentials, commits the DB, then atomically replaces the key file via `os.replace`. The legacy `rotate_key()` callback API is retained for non-API callers.

### `the_one/db/repositories.py`

Database repositories including `LLMProviderRepository` for CRUD on `llm_provider_configs` table. Provider configs store `name`, `type`, `base_url`, and encrypted `api_key`. Referenced by `AgentConfig.provider_config_id`.

### `the_one/agent/`

| File | Exports | Purpose |
|------|---------|---------|
| `core.py` | `Agent` | The agent loop: `step()` yields messages, max 20 iterations |
| `config.py` | `AgentConfig`, `DEFAULT_SYSTEM_PROMPT` | Agent definition Pydantic model (includes `provider_config_id` for LLM provider resolution) and fallback prompt |
| `factory.py` | `AgentFactory` | `create(name)` → configured Agent; `list_agents()` |
| `store.py` | `AgentConfigStore`, `FilesystemConfigStore` | CRUD for agent configs (`~/.the-one/agents/*.json`) |
| `behaviors.py` | `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`, `match_direct_action()` | Behavioral patterns extracted from core |

**Agent.step() flow**: user input → check direct actions → LLM call → execute tools → repeat until no tool calls or max iterations.

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
| `builtins.py` | `BuiltinToolProvider` | Provides all 14 built-in tools via lazy import |
| `shell.py` | `ShellTool` | Arbitrary shell commands |
| `filesystem.py` | `ReadFileTool`, `WriteFileTool`, `ListDirTool` | File operations |
| `git.py` | `GitTool` | Version control with safety guards |
| `test_runner.py` | `TestRunnerTool` | pytest integration |
| `python_exec.py` | `PythonExecTool` | Python subprocess execution |
| `web.py` | `HttpRequestTool`, `WebSearchTool` | HTTP and web search |
| `memory.py` | `MemoryTool` | Persistent key-value store (`.memory/` directory) |
| `self_deploy.py` | `SelfDeployTool` | Concourse CI deployment trigger |
| `restart.py` | `RestartTool` | Container restart via Concourse |
| `rollback.py` | `RollbackTool` | Docker image rollback via Concourse |
| `mission_control.py` | `MissionControlTool` | Flight Control methodology access |

### `the_one/interfaces/`

| File | Exports | Purpose |
|------|---------|---------|
| `cli.py` | `run()` | Rich + prompt-toolkit REPL |
| `web/app.py` | `app` | FastAPI server with WebSocket sessions |

Both use `AgentFactory.create()` to get agents. The web app adds session management.

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
        agent/behaviors.py
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

`ToolProvider` is a protocol with `name` + `get_tools()`. `BuiltinToolProvider` provides the 14 built-in tools. Future `McpToolProvider` implements the same protocol for MCP server tools.

### Direct Actions

Regex patterns in `behaviors.py` that bypass the LLM for known commands (restart, rollback). This avoids small models reaching for `shell` when a dedicated tool exists.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

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

2. **Outlined-cyan** — secondary action; reads as available but de-emphasized. Pattern: background transparent, border `1px solid var(--accent)`, text `var(--accent)`, hover background `var(--accent-translucent)`. Live UI today: `.new-chat` (chat sidebar's "+ new" button), `.new-agent-btn` (studio sidebar). Future use: "edit", "configure", and similar non-CTA actions across all areas.

3. **Filled-cyan CTA** — primary action; reads as the recommended next step. Pattern: background `var(--accent)`, text `var(--fg-on-accent)`, hover via `filter: brightness(1.1)` or explicit hover token. Used for "save", "submit", "create" — one CTA per page is the convention.

4. **Muted-default-then-glow destructive** — irreversible action; reads as recessive at idle, glows on focus/confirm. Pattern: transparent background at idle, text/border `var(--status-danger-muted)`. Confirm state (after first click): background `var(--status-danger)`, text `var(--fg-on-danger)`, glow `var(--status-danger-glow)`. Used for delete affordances on session items, agent items, chip-removes. Never used for routine actions.

5. **Neutral utility** — small, non-categorical action with no surrounding chrome. Pattern: background transparent, text `var(--fg-secondary)`, hover text `var(--fg)`, no border. Examples: inline `x` icon buttons, dropdown-chevron indicators, decorative scroll affordances. NOT for "+ new" buttons (those are outlined-cyan, pattern 2).

6. **Palette-island rule** — components that establish their own chrome (the nav rail, the top bar arriving in F3 leg 02) declare their own `--nav-*` (or topbar-equivalent) palette family in `tokens.css`. The body palette and the chrome palette MUST NOT share token names. Rule: never reach into chrome tokens from body components or vice versa.

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
verified by tabbing through chat input, send button, and nav rail in both
themes.

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
| `chat` | `message-circle` | nav rail (Chat area) |
| `studio` | `bot` | nav rail (Studio area) |
| `admin` | `settings` | nav rail (Admin area) |
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

