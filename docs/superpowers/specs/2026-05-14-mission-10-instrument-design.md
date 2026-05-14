# Mission 10 — Scientific Instrument

**Status:** Draft · 2026-05-14
**Replaces / extends:** Mission 09 Holograph design system
**Scope:** Full UI pass — empty states, topnav, area headers, working states, motion layer, light theme

## Overview

A UI/UX rating pass on `localhost:8484` rated the live app **4.5 / 10** — competent foundation, but no committed aesthetic direction, generic typography, forgettable empty states, and several mechanical defects. The mechanical defects shipped in L8.7. This spec covers the creative work — the system-wide aesthetic lens that lifts the product out of "well-mannered admin panel" territory.

The chosen direction is **Scientific Instrument**: faint grid canvas, coordinate labels, live telemetry chips, status indicators, mono-typeset routing labels, bracket framing on focal moments. The product is a personal agent; the visual metaphor is the holographic projection of that agent's surface area. The name "Holograph" carries this load — Mission 09 set the colors, Mission 10 sets the personality.

## What This Is Not

- Not a rebrand — the Holograph wordmark, mark, and color tokens from Mission 09 stay.
- Not a logo redesign or new fonts. Inter + JetBrains Mono only.
- Not maximalist — the lens is precise, restrained, instrument-like. Every chrome element earns its place by carrying real data.
- Not animation-heavy — motion is ≤240ms, CSS-only, gated by `prefers-reduced-motion`.

## 1. Visual Vocabulary

Eight primitives. Every screen in the redesign is built from these. New CSS custom properties go into `tokens.css`; new component CSS goes into `components.css` unless otherwise noted.

### 1.1 Grid canvas (`--surface-grid`)

A body-level background applied to `<main id="main-content">`:

```css
:root[data-theme="dark"]  { --surface-grid: rgba(255,255,255,0.025); }
:root[data-theme="light"] { --surface-grid: rgba(0,0,0,0.025); }

#main-content {
  background-image:
    linear-gradient(var(--surface-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--surface-grid) 1px, transparent 1px);
  background-size: 20px 20px;
}
```

20px spacing. 2.5% opacity in both themes (looks faintly different because of the underlying bg, but the alpha is symmetric). Test-visible but never an attention-grabber. No interaction with content.

### 1.2 Corner ticks (`.corner-tick`)

Four 8px L-shaped marks pinned to each corner of `#main-content`, drawn in `--accent`. Decorative; sits in the gutter outside content. Pure CSS pseudo-elements on a `.canvas-frame` div appended once at app init by `app.js`.

### 1.3 Coord pill (`.pill-coord`)

`display: inline-flex; align-items: center; gap: 8px; padding: 5px 10px;` — mono label like `HOLOGRAPH · CHAT · 01`, separator dots in `--fg-dim`, optional leading violet `4px` dot. Used in: section-header eyebrows, embedded inline in the section-nav active-state if needed for editor sub-routes.

### 1.4 Status indicator (`.stat-dot` + states)

7px round dot with a 2px-spread halo via `box-shadow`. Four states keyed by class: `.idle` (muted, no pulse), `.work` (accent, 1.4s ease-in-out opacity pulse 1 → 0.55 → 1), `.ok` (good-green), `.err` (bad-red). When paired with a label, the pattern is `<span class="stat-dot work"></span><span class="stat-label">WORKING</span><span class="stat-detail">— agent is responding</span>`.

### 1.5 Telemetry chips (`.tele-chip`)

Compact mono cells: `font-family: 'JetBrains Mono'; font-size: 10px; letter-spacing: 0.04em;` label + `font-size: 16px; font-variant-numeric: tabular-nums; font-weight: 500;` value with optional `<small>` unit suffix. **Real numbers always** — every chip reflects backend state, never a decoration.

Data sources required (all already in the app):

| Chip | Source |
|---|---|
| SESSIONS | `ChatSessionRepository.count()` |
| AGENTS | `SQLiteAgentStore.list()` length |
| PROVIDERS | `LLMProviderRepository.list()` length |
| TOOLS | `19` baseline + `MCPToolProvider.get_tools_for_agent()` length for the active agent's enabled MCP sources |
| CTX | sum of `usage.input_tokens + usage.output_tokens` for current session |
| WS | round-trip time of the most recent WS ping/pong (new — see §11) |

Stable across area switches. Topnav-level chips reflect global state; section-header chips reflect the active scope.

### 1.6 Section eyebrow (`.eyebrow`)

Above every page-section title (`area-title`, `editor-name`, etc.) and stream-start markers in Chat. Markup: `<div class="eyebrow">STUDIO · AGENTS</div>`. CSS: small uppercase mono with a leading 18px violet rule (`::before`).

### 1.7 Bracket framing (`.brack`)

Two 14px corner brackets in `--accent` on a focal empty-state element (top-left + bottom-right). Used once per screen at most. Implementation: pseudo-elements on a `.brack` wrapper around the focal `<h-/>` + `<p>` pair.

### 1.8 Accent rule (`.accent-rule`)

`<div class="accent-rule" data-meta="END · SESSION">`. Gradient line `linear-gradient(90deg, var(--accent), transparent)` with optional right-aligned mono meta label. Replaces solid `border-bottom: 1px solid var(--line)` separators in section-heavy layouts (Admin, Studio editor).

## 2. Topnav (V2 — Mono Coord Segments)

Replaces the current `.navlink` triplet.

**Structure** (in `app.js::renderTopnav`):

```html
<nav class="topnav" id="app-topnav">
  <div class="brand">
    <div class="brand-mark">H</div>
    <div class="brand-name">Holograph</div>
  </div>
  <div class="nav-segments">
    <button class="navseg" data-area="chat"><span class="idx">01</span>CHAT</button>
    <button class="navseg" data-area="studio"><span class="idx">02</span>STUDIO</button>
    <button class="navseg" data-area="admin"><span class="idx">03</span>SYSTEM</button>
  </div>
  <div class="spacer"></div>
  <div class="tele-strip"><!-- 3-4 chips, area-scoped --></div>
  <div class="search">…</div>
  <div class="avatar">JD</div>
</nav>
```

`.nav-segments` is a `padding:4px; background: var(--bg-elev); border: 1px solid var(--line); border-radius: 6px` group. Each `.navseg` is `position: relative; padding: 5px 12px 5px 28px; font-family: 'JetBrains Mono'; font-size: 11px; letter-spacing: .08em`. The `.idx` absolute-positions at `left: 9px` and switches to `--accent` when its parent has `.active`. Active state adds `background: var(--accent-soft)` and a 22px accent underline at `bottom: -1px`.

The topnav `.tele-strip` displays 3 chips. The chip choice changes per area:

| Area | Chips shown |
|---|---|
| Chat | SESSIONS · CTX · WS |
| Studio | AGENTS · PROVIDERS · WS |
| Admin | PROVIDERS · TOOLS · WS |

`WS` is universal. Choice is hard-coded per area-mount in `topnav.js` (new module — see §10).

**Carried forward from L8.7**: `appearance: none` on the segment, ensuring no UA chrome ever swallows the labels in light theme.

## 3. Area Header Pattern

All three areas share one header pattern:

```html
<header class="area-header">
  <div class="area-header-titleblock">
    <div class="eyebrow">STUDIO · AGENTS</div>
    <h1 class="area-title">research</h1>
    <p class="area-sub">2 agents configured · last edit 5m ago</p>
  </div>
  <div class="area-header-actions">
    <button class="btn-mono">+ NEW AGENT</button>
  </div>
</header>
```

The block already exists in markup; this spec **adds** the eyebrow and **modifies** existing tokens:

- `.area-title` font-size: `22px → 26px`
- `.area-title` adds `line-height: 1.1`
- `.area-sub` stays as already shipped in L8.7 (block-level, muted, `margin-top: 4px`)
- New `.btn-mono` token: mono-typeset CTAs that match the lens — `padding: 9px 16px; background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(167,139,250,0.3); font-family: 'JetBrains Mono'; font-size: 12px; letter-spacing: .04em;`

Chat does not currently use `.area-header` (header lives in `convo-pane` per Mission-09 mockup). Chat retains its custom shell; the eyebrow lands as the first child of the session's message stream — see §5.1.

## 4. Sub-tab Section Nav

Existing `.holograph-section-nav` styling stays. Adds:

- Active tab underline thickens from `1px → 2px`, accent color
- Inactive tabs gain a hover state that fades to `--fg` at `120ms ease`
- Numeric index option (`01 Agents / 02 Knowledge / 03 MCP Sources`) — **deferred**, not part of M10. The eyebrow already carries route info; sub-tabs stay label-only.

## 5. Empty States

### 5.1 Chat empty state — first-run (no provider)

Sessions rail shows `SESSIONS — 0 · no sessions yet · ⌘N to create when ready` as a mono-typeset placeholder line on a dashed left rule (`border-left: 2px solid var(--line)`). The convo pane shows: eyebrow `HOLOGRAPH · CHAT · IDLE` → bracket-framed `<h2>Two steps to your first message.</h2><p>Configure a provider, build an agent, then come back here. The shortest path to a working setup takes about a minute.</p>` → two numbered step cards (STEP 01 / STEP 02), the first highlighted as `.next` (`border-color: var(--accent); background: var(--accent-soft);`). Composer stays visible-but-disabled.

Step cards link semantics: STEP 01 button navigates to `#admin/providers`; STEP 02 to `#studio/agents`. When a provider is added, STEP 01 swaps to `.done` (✓ prefix, `--good` color) and STEP 02 becomes `.next`. When an agent is added, both become `.done` and the empty state collapses — Chat enters its working state.

### 5.2 Chat empty state — provider exists, no agent

Same shape as 5.1 but STEP 01 is `.done` and STEP 02 is `.next`. The bracket headline changes to `<h2>One step left.</h2>`. The mono status chip in the topnav flips from `NO PROVIDER` (warn) to `AGENTS 0` (idle).

### 5.3 Chat empty state — agent exists, no session

Sessions rail unchanged shape, still showing the dashed-rule placeholder. Convo pane shows: eyebrow `HOLOGRAPH · CHAT · READY` → bracket-framed `<h2>Ready when you are.</h2><p>Press ⌘N or use the composer to start a conversation.</p>`. No step cards; composer is enabled. Send button reads `SEND →` in mono.

### 5.4 Studio · Agents · empty

Area header (eyebrow + title `Configure and edit your agents` + sub `A configured provider unlocks agent creation. You have N provider(s) wired up.`) → sub-tabs → two-column body with `AGENT LIST · 0` placeholder on the left + bracket-framed `<h2>Build your first agent.</h2>` on the right + two CTAs `+ NEW AGENT` and `→ start from preset`.

The "start from preset" CTA opens a dialog with 3 presets:
- **research** — opus/sonnet, broad tools, no write
- **shell-buddy** — haiku, shell + filesystem only
- **web-crawler** — sonnet, web tools only

Presets are JSON in `the_one/agent/_presets.py` — new file. The `+ NEW AGENT` button creates a blank.

### 5.5 Studio · Knowledge · empty / 5.6 Studio · MCP Sources · empty

Same area header pattern. Body: bracket-framed copy + one primary CTA. Knowledge: "No knowledge bases yet. Knowledge is searchable content an agent can cite." MCP: "No MCP sources connected. Connect a server to extend an agent's tool surface."

### 5.7 Admin · General · always populated

No empty state — General has Appearance + Encryption + Base Prompt rendered unconditionally. M10 changes: area header gets the eyebrow, "Appearance" / "Encryption" / "Base Prompt" cards adopt the `.accent-rule` separator pattern instead of plain borders.

### 5.8 Admin · LLM Providers · empty

Area header (`SYSTEM · LLM PROVIDERS` eyebrow, `Wire up a provider` title, `Holograph needs at least one configured LLM to do anything useful. API keys are encrypted at rest.` sub) → sub-tabs → 4-column provider-type grid: Anthropic (RECOMMENDED, accent border), OpenAI, OpenAI-compatible, Ollama. Each card has a mono category label (`RECOMMENDED` / `CLOUD` / `CLOUD` / `LOCAL`), name, and one-line description. Clicking a card opens the existing `provider-editor` modal.

### 5.9 Admin · Built-in Tools · always populated

No empty state — Built-in Tools renders 19 tools unconditionally. M10 changes: area header gets the eyebrow, each tool card adopts the `.eyebrow` pattern for its category strip (e.g., `EXECUTION` / `FILESYSTEM` / `WEB`).

## 6. Working States

### 6.1 Chat working state

Each conversation gets a stream-leading eyebrow: `SESSION 01 · {SESSION_TITLE}`. Each message uses a mono-typeset `who` line: `YOU →research` (for the user, with the agent name as a violet tag) or `research ← claude-opus-4-7` (for the agent, with the model in tail). Tool calls retain `.toolcall` blocks but adopt a 2px accent left-border (instead of full border-and-rounded) and a mono header `▶ shell · 0.6s · 3 hits`.

When the agent is responding, a `working-row` renders below the latest message: `<span class="stat-dot work"></span>WORKING — agent is responding · token N / M`. Disappears when the response completes.

### 6.2 Studio working state

Agent rail shows agent cards with name + READY-state dot + `OPUS-4-7 · 13 TOOLS` mono meta. Active card has `border-color: var(--accent)` and `background: var(--accent-soft)`. Editor pane gets its own internal header: `<div class="editor-coord">● EDITING · AGENT 01</div><div class="editor-name">research</div>` + revert/save actions in mono.

Fields adopt mono labels (`PROVIDER · MODEL`, `SYSTEM PROMPT`, `TOOLS · 13 / 19 enabled`) with optional `field-hint` smalls. Tool chips become small bordered mono cells; disabled ones get `text-decoration: line-through` + `border-style: dashed` + `color: var(--fg-dim)`.

### 6.3 Admin working state

Provider cards in the populated state get a status dot (READY / TESTING / ERROR), the mono category label, the friendly name, and a footer `LAST USED · 2h AGO` mono meta. Tools admin uses the same `.eyebrow` category strips already specified in §5.9.

## 7. Light Theme Adaptation

All tokens cross over via the existing dark/light theme switching in `tokens.css`. New mappings:

| Token | Dark | Light |
|---|---|---|
| `--surface-grid` | `rgba(255,255,255,0.025)` | `rgba(0,0,0,0.025)` |
| `--accent-soft` | `rgba(167,139,250,0.10)` | `rgba(51,88,192,0.10)` |
| `--good` | `#6ee7b7` | `#0d9166` |
| `--bad` | `#f87171` | `#c83232` |
| `--warn` | `#fbbf24` | `#b87900` |
| `--brand-mark-bg` | `linear-gradient(135deg, var(--accent), #7c5cff)` | `var(--accent)` (flat blue) |

Dark mode keeps the brand-mark gradient; light flattens to the solid Holograph blue. All other primitives are theme-agnostic (use `--fg`, `--fg-mute`, `--fg-dim`, `--line`, `--accent` which are already defined per-theme).

**Carried forward from L8.7**: the WCAG 2.1 AA contrast pair `--fg-mute × --bg = 4.88:1` in light theme. Mission-10 additions to verify in `tests/test_design_tokens_a11y.py`:
- `--accent × --bg` ≥ 4.5:1 (currently passes per Mission 09 audit)
- `--good × --bg` ≥ 4.5:1 (new — light theme `#0d9166` on `#f8f8f6`)
- `--bad × --bg` ≥ 4.5:1 (new — light theme `#c83232` on `#f8f8f6`)

## 8. Motion Policy

CSS-only. All durations ≤ 240ms. All gated by `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }` (already present in `base.css`; verify and keep).

| Element | Motion |
|---|---|
| `.stat-dot.work` | 1.4s ease-in-out opacity pulse, infinite |
| Area transitions | 150ms `opacity` cross-fade on `.content-panel` (extends L8.7's display toggle) |
| Telemetry counter value change | 240ms count-up via JS `requestAnimationFrame` lerping the displayed text — only when the value changes by ≥1 |
| `.stat-dot` state change | 200ms `background-color + box-shadow` transition |
| `.navseg.active` underline | 180ms `transform: scaleX()` from anchor center |
| Modal open | 160ms fade + 8px translate-up |
| `.brack` corner ticks | static (no animation) |

The counter lerp lives in a new utility `the_one/interfaces/web/static/js/utils/lerp-counter.js`. It accepts a DOM node + a target integer and animates the displayed text. Honors `prefers-reduced-motion` by jumping to the target value instantly.

## 9. Tokens to Add

`tokens.css` additions (both themes):

```
--surface-grid
--accent-soft
--good, --bad, --warn (status semantic tokens — L1 audits the existing tokens.css and either formalizes existing hex literals or introduces these fresh)
--brand-mark-bg
--space-1 .. --space-8       (4/8/12/16/20/24/32/48px — formalize spacing scale; Mission-09 used literals)
--font-mono-eyebrow-size     (10px)
--font-mono-eyebrow-tracking (.15em)
--corner-tick-size           (8px)
--corner-tick-inset          (12px)
--canvas-grid-step           (20px)
--motion-fast                (120ms)
--motion-base                (180ms)
--motion-slow                (240ms)
--motion-pulse-cycle         (1400ms)
```

Removing tokens: none. M10 is purely additive against the Mission-09 baseline.

## 10. New Modules

| Path | Purpose |
|---|---|
| `the_one/interfaces/web/static/js/topnav.js` | Extracts topnav render from `app.js`. Owns per-area `tele-strip` chip selection. Subscribes to `telemetry-store` (see §11) for live counts. |
| `the_one/interfaces/web/static/js/utils/lerp-counter.js` | Smooth counter value animation honoring reduced-motion. |
| `the_one/interfaces/web/static/js/utils/telemetry-store.js` | In-memory observable holding `{sessions, agents, providers, tools, ctx, ws_rtt_ms, ws_state}`. Single source for all chips. Subscribers (topnav, area headers, empty-state telemetry) re-render on change. |
| `the_one/agent/_presets.py` | The three agent presets from §5.4. |

CSS new files: none. All M10 styles land in `components.css` plus per-area files (`chat.css`, `studio.css`, `admin.css`).

## 11. WebSocket Round-Trip Telemetry

The `WS · 14ms` chip requires a measured round-trip time. Approach:

- Client sends a `{"type":"ping"}` frame every 10 seconds while a WS connection is open.
- Server `interfaces/web/websocket.py` echoes a `{"type":"pong"}` immediately on receipt.
- Client measures elapsed time and updates `telemetry-store.ws_rtt_ms`.

The chip displays the EMA of the last 5 samples (smoothing). If a ping goes unanswered for 5s, `telemetry-store.ws_state = "stale"` and the chip's status dot flips from `.ok` to `.err`. On full disconnect, `ws_state = "down"` and the chip reads `WS · OFFLINE`.

Server change is one line; client change is in `websocket.js` (existing module).

## 12. Areas of Intentional Non-Change

Preserved exactly as-is:

- Chat composer interaction (Attach, ctx counter, Send)
- Sessions rail interaction (create, rename, delete, select)
- Agent editor save/revert flow
- Provider edit modal (the `__MASKED__` sentinel contract stays intact per CLAUDE.md)
- Tool admin grid behavior (the operator-set kill-switch toggles)
- All URL hash routes (`#chat`, `#studio/agents`, `#admin/general`, etc. — operator bookmarks must keep working)
- The `.holograph-section-nav` class name and the canonical Mission-09 class taxonomy
- All `.holograph-*` CSS class names (those are already canonical)
- All ARIA labels and the skip-to-main-content link

Visual treatment changes; behavior does not.

## 13. Out of Scope

- Empty-state copywriting beyond what's in this spec (proceed with the strings shown).
- Sub-tab numeric indexing (`01 Agents / 02 Knowledge / 03 MCP Sources`) — deferred.
- A new theme beyond light/dark (e.g., high-contrast or solarized).
- The `chat`/`studio` area's height-calc bug noted in L8.7 — fix in a separate leg.
- The `.area.active { display: block }` dead-code rule in `components.css:183` — separate cleanup.
- Stale OAuth callback docstring at `api.py:1473` — separate doc PR.
- Brave / SerpAPI / Bing search backends (orthogonal MCP work).
- Authentication / multi-user. The product remains single-user per `SECURITY-MODEL.md`.

## 14. Accessibility

- All new color pairs audited against WCAG 2.1 AA in `tests/test_design_tokens_a11y.py` extensions (see §7).
- `prefers-reduced-motion: reduce` honored universally — pulse animation halts, counter lerp jumps, fades become instant.
- `.stat-dot` carries an `aria-label` describing the state (e.g., `aria-label="connection ok, 14ms"`) — purely visual otherwise.
- The mono-typeset coord pills and telemetry chips have textual content (no icon-only); screen readers read them naturally.
- Keyboard focus rings stay on `.navseg`, `.btn-mono`, all interactive elements. Focus ring uses `outline: 2px solid var(--accent); outline-offset: 2px;`.

## 15. Migration / Leg Plan

Mission 10 splits into six legs. Each leg is independently shippable and visually coherent — partial M10 doesn't look broken, just less complete.

- **L1 · Foundation.** Add tokens (§9). Add `.canvas-frame` body-level grid + corner ticks. Add `.eyebrow`, `.pill-coord`, `.stat-dot`, `.brack`, `.accent-rule`, `.btn-mono` CSS primitives. No JS. No markup changes. Visual diff: faint grid + corner ticks appear; nothing else changes. Visual snapshot baselines regenerate.
- **L2 · Topnav.** Replace topnav render in `app.js`. Add `topnav.js` + `telemetry-store.js`. Hook telemetry store to existing API counts (no WS pinging yet). Add `appearance: none` carry-forward verification.
- **L3 · Area headers.** Apply `.eyebrow` + larger `.area-title` to Studio + Admin. Wire `area-sub` to dynamic state strings (agent count, provider count, last-edit time). Chat retains custom header.
- **L4 · Empty states.** Implement §5.1 – §5.9. Add `_presets.py`. Wire step-card click handlers. Add visual snapshot baselines for each empty state in each theme.
- **L5 · Working states.** Apply §6.1 – §6.3 polish. Chat stream eyebrow + mono `who` lines + mono tool-call header + working-row indicator. Studio editor coord-header + mono fields + mono tool chips. Admin provider status dots + LAST-USED meta.
- **L6 · Motion + WS telemetry.** Implement §8 motion layer. Implement §11 WS round-trip ping + `ws_rtt_ms` telemetry. Add `lerp-counter.js`. Final `prefers-reduced-motion` audit.

Test coverage at each leg:
- L1: tokens defined, a11y pairs audited, grid renders.
- L2: topnav renders correct per-area chips, navseg active state correct, ⌘K + reload paths.
- L3: area headers carry eyebrow, subtitle reflects state, `.area-title` font-size 26px.
- L4: every empty state has a snapshot test + a flow test that exits the empty state on the relevant action.
- L5: every working-state addition has a snapshot test; tool-call rendering test extended.
- L6: motion durations bounded; `prefers-reduced-motion: reduce` audit passes; WS ping/pong round trip measured.

## 16. Risks

- **Telemetry chips are real-data-only.** If a count is unavailable (e.g., during an early init race), chips render `—` not `0`. A regression test pins the never-zero-on-startup behavior to prevent confusion with the "no agents" state.
- **Grid canvas + dense chat conversation.** The 2.5% grid is faint but theoretically distracts in a long chat. Light-pass review of the working chat mock confirmed it's acceptable; flag for re-review on long sessions at L5 (working-state polish) when the stream eyebrow + mono `who` lines land on top of the grid.
- **Counter lerp on rapid agent state changes.** If `WS_RTT` updates every ping (10s), no perceived issue. If a future feature pushes 4Hz updates, the lerp will visibly stutter. The lerp utility caps update frequency at 4Hz internally to prevent this.
- **Light-theme good/bad/warn unaudited contrast.** Adding the audit in L1 catches this before any color is used in production.

## 17. Open Questions

None for the M10 design. Plan-time decisions:

- Should the WS ping interval be configurable? Default 10s; for now, hard-code.
- Should empty-state copy be i18n-ready? Out of scope for M10; all strings stay in JS/CSS.
- Telemetry-store initial values: render `—` until first refresh succeeds. Confirmed approach.

---

*End of spec. Reviewer should focus on §1 (vocabulary primitives), §5 (empty-state inventory), §10 (new modules), and §15 (leg plan).*
