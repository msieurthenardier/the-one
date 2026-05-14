# Holograph UI Migration — Design (v3)

**Date:** 2026-05-12
**Status:** Revision v3 — second independent review applied; awaiting user sign-off before implementation plan

## Revision notes (v3)

v3 addresses 3 blockers + 5 should-fix items from a second independent review pass on v2:

- **Section-nav primitive correction.** v2 invented `App.SectionNav.mount(...)`; actual API is `App.layout.renderSectionNav` + `App.layout.updateActiveSection`. v3 preserves the existing API verbatim and only restyles the emitted markup.
- **OAuth Reset surface correction.** v2 specified two reset buttons ("Reset tokens" + "Reset registration") that don't exist in the current code. v3 preserves the single "Reset connection" button (data-testid `reset-mcp-connection-btn`) in `mcp-server-editor.js:343-345`.
- **Per-agent MCP attachment editor designed.** v2 referenced `#studio/agents/{name}/mcps/{source-id}` without specifying the editor. v3 adds a dedicated subsection.
- **Contrast ratios re-verified.** v2's claimed ratios were close but off: `#3358c0 × #f8f8f6` is 5.99 (not 5.65); `#fff × #3358c0` is 6.37 (not 6.01); `#fff × #c5443d` is 4.92 (not 4.62). All values still pass AA at the body threshold.
- **Accent-tint opacity calibration** documented as Decision 20 (third calibration alongside accent and fg-faint).
- **`--fg-on-danger` un-retired** and added to both theme token tables (audit reference now valid).
- **Test count corrected** 22 → 24 flow tests; `test_flow_picker` ownership pinned to L3 only.
- **URL encoding rules** for `#studio/agents/{name}/{tab}` documented.
- **Backend contracts** (OAuth `client_secret` payload-key, encryption rotation invariant) explicitly noted as preserved.
- **Risk table** expanded with v3 items.

## Revision notes (v2)

v2 addressed 5 blockers + 8 should-fix items from the first independent review pass:

- **Studio IA** rewritten — Studio actually has 3 top-level sections (`agents` / `knowledge` / `mcp-sources`), not just agents-with-tabs. Holograph adopts a Studio internal sub-nav mirroring Admin's pattern.
- **Light accent darkened** from `#4070e0` (4.28:1 — fails AA) to `#3358c0` (5.99:1 against `#f8f8f6` — passes AA body; v3 re-verified, see Revision notes (v3)).
- **Fonts decision pinned**: self-host Inter + JetBrains Mono (replacing the self-hosted Geist Sans + Geist Mono). Matches the mockup AND the project's self-host-everything convention.
- **MCP source editor** properly spec'd: OAuth Reset surface, `__MASKED__` per-key secrets contract, masked-tail rendering preserved.
- **`#admin/system` legacy redirect** explicitly preserved.
- **`section-nav.js`** decision pinned: rewritten in L1 as `.holograph-section-nav` (shared primitive).
- **Test count** corrected to actual surface (22 flow tests + OAuth/MCP/streaming/seeders/smoke); risk table expanded.
- **Provider-card `.expanded` state** layout-shift mitigation defined.
- Misc: `.search` aria-label + behavior pinned; body-size 13.5px change called out; `--fg-faint` slightly darkened to pass AA-large.

## Summary

Replace the current web UI of GleepGlorp AI with a card-based, "spatial composition" design language called **Holograph**, in a single big-bang mission. Holograph swaps the current `topbar + global sidebar + content` shell for a `topnav + content` shell where each area owns its internal layout. The new visual language is light-first (neutral palette + restrained blue accent) with a paired dark theme that preserves the GleepGlorp violet accent. Implementation hews **pixel-for-pixel** (with documented a11y calibrations) to two reference HTML mockups already committed to the repo at `playground/mockups/holograph.html` (light) and `playground/mockups/holograph-dark.html` (dark).

The mission retires the entire Mission 08 visual vocabulary (glass, bezel, gleam, accent-glow, all `app-picker-button` / `entity-tile` class names) and replaces it with the mockup's flat, hairline-bordered, card-first vocabulary (`.session-card`, `.toolcall`, `.editor-pane`, `.provider-card`, etc.).

## Goals

- Deployed web UI matches the Holograph mockups pixel-for-pixel in both themes across Chat, Studio (Agents / Knowledge / MCP Sources), and Administration (Providers / Built-in Tools / General).
- Each area owns its internal layout; the global app sidebar is removed.
- Light theme uses `#3358c0` as its single accent (darker than the mockup's `#4070e0` to satisfy WCAG AA at the body threshold — a documented a11y calibration).
- Dark theme keeps GleepGlorp violet (`#a78bfa`).
- Mockup's CSS class vocabulary adopted verbatim; Mission 08 class names retired.
- Brand mark is the mockup's wordmark (small "G" square + text "GleepGlorp AI"); `gleepglorp_banner.png` is no longer referenced from live HTML.
- Inter + JetBrains Mono are self-hosted, replacing the self-hosted Geist Sans + Geist Mono (preserves the project's no-CDN convention while matching the mockup).
- Tri-state theme preference (Light / Dark / Auto) continues via `App.theme` and the `data-theme` attribute.
- Visual snapshot coverage expands from 12 to ≥28 baselines.
- All existing functionality continues: WebSocket streaming, MCP OAuth popup with synthetic-csid handling, encryption key rotation, dirty-leave confirmation, MCP source CRUD with secrets segregation, tool-config editor with marker dispatch (`Narrow` / `NarrowSuperset` / `NarrowPrefix` / `Substitute`), per-agent tool overrides, agent-build connection test, provider test-connection, model auto-discovery, the `__MASKED__` sentinel for credential preservation, the `#admin/system` legacy redirect, the Studio knowledge-stub route.
- WCAG AA contrast maintained per the documented audit table; `tests/test_design_tokens_a11y.py` passes against the new palettes.

## Non-goals (YAGNI)

- Animated view-transitions on area switch.
- Drag-and-drop card rearrangement.
- Per-agent color coding.
- Backdrop blur on regular surfaces (only the sticky topnav uses it).
- New features beyond visual migration.
- Mobile / narrow-viewport optimization. Min-width stays 1280px.
- A storybook / component-library package.
- Backwards-compatibility aliases for retired Mission 08 class names.
- Preserving the Mission 08 Design Language admin page.
- A v1 working command palette behind the `.search` topnav affordance.

## Design decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Approach B** — full shell refactor + visual rewrite | User chose big-bang + pixel-perfect + light+dark-together. Approach B matches the mockup architecture exactly. |
| 2 | Adopt mockup CSS class vocabulary verbatim | Cleaner grep; tests get clearer selectors. |
| 3 | `registerArea(content)` — drop the sidebar parameter | Global sidebar is removed; the shape change is explicit (not "impossible" — explicitly retired). |
| 4 | Brand mark is a text wordmark | Scales, themes naturally, removes binary-asset dep. |
| 5 | **Light accent `#3358c0`; dark accent `#a78bfa`** | Light is the mockup's `#4070e0` darkened just enough to pass WCAG AA at the 4.5:1 body threshold (5.99:1 against `#f8f8f6` — v3 re-verified). Dark keeps the existing GleepGlorp violet. |
| 6 | Both themes share token names; values differ by theme block | Continues the current tokens.css pattern. |
| 7 | Retire all bezel/glass/gleam tokens | Mission 08 vocabulary is gone. |
| 8 | Keep `prefers-reduced-motion` and `prefers-reduced-transparency` fallbacks | A11y. |
| 9 | ≥28-baseline visual snapshot matrix | Pixel-perfect commitment enforced in CI. |
| 10 | One migration per CSS file + one per area JS file, ordered by leg | Big-bang mission with reviewable internal legs. |
| 11 | Selectors in flow tests updated **as each area lands** | Test breakage contained per leg. |
| 12 | Existing `App.theme.*` API preserved | Public API unchanged. |
| 13 | Existing hash routing (`#area/sub`) preserved, including the `#admin/system → general` redirect AND the Studio routes (`#studio/agents/{name}/{tab}`, `#studio/agents/{name}/mcps/{source-id}`, `#studio/knowledge`, `#studio/mcp-sources`, `#studio/mcp-sources/new`, `#studio/mcp-sources/{id}`) | URL contracts are load-bearing for bookmarks + tests + the F3 router's serialize-after-hydrate path. |
| 14 | The Design Language admin page is removed | Mission 08 artifact. |
| 15 | **Self-host Inter + JetBrains Mono** in `fonts.css` | Matches mockup; preserves project's no-CDN convention. Retires the self-hosted Geist. |
| 16 | **Studio has an internal `.studio-subnav`** with Agents / Knowledge / MCP Sources | Mirrors Admin's `.admin-subnav` pattern. Preserves the 3 top-level Studio routes. |
| 17 | **`section-nav.js` markup restyled in L1; API preserved verbatim** | Actual API is `App.layout.renderSectionNav(container, items, active, options)` + `App.layout.updateActiveSection(container, active)`. Consumers in `admin.js:228, 243, 692` and `studio.js:285, 562` need no caller changes — L1 swaps the emitted markup only. |
| 18 | **`--fg-faint` light darkened from `#9da3ad` to `#878d96`** | Original value reads at 2.37:1 — fails AA-large (3:1 floor). Darkened to ~3.15:1. Documented as an a11y calibration; implementation authoritative. |
| 19 | Provider-card `.expanded` state ships with **all three column-position snapshots** | The 2-col-span inside a 3-col grid causes layout reflow. Three snapshots (expanded from col 1, col 2, col 3) cover all reflow shapes. |
| 20 | **`--accent-tint` opacity 0.08 → 0.10 and `--accent-tint-strong` 0.14 → 0.18 (light)** | With the darker `#3358c0` accent (Decision 5), the mockup's 0.08/0.14 alphas wash out — bumping to 0.10/0.18 keeps chip backgrounds and focus halos at the intended visual weight. Documented as a11y calibration alongside Decisions 5 and 18. |
| 21 | **OAuth Reset surface preserves single existing button**, not two | Current `mcp-server-editor.js:343-345` ships ONE "Reset connection" button (data-testid `reset-mcp-connection-btn`). v2 mistakenly invented two; v3 preserves the single-button semantic. No new endpoints. |
| 22 | **`--fg-on-danger` is preserved** (not retired) | Light `#fff`, dark `#0a0c10`. Required for `.btn-primary.danger` text on `--danger` bg. v2 mistakenly listed it in the retired tokens; v3 keeps it. |

## Visual ground truth

Two HTML mockups are the authoritative visual spec:

- `playground/mockups/holograph.html` — light theme (1,874 lines)
- `playground/mockups/holograph-dark.html` — dark theme (1,874 lines)

When spec text and mockups disagree, **the mockups win** EXCEPT for the deliberate a11y calibrations called out in Decisions 5 and 18. Those calibrations are spec-authoritative; the implementation diverges from the mockup's `#4070e0` and `#9da3ad` values intentionally.

## Token system

### Light theme tokens

| Token | Value | Notes |
|---|---|---|
| `--bg` | `#f8f8f6` | Warm-neutral page bg |
| `--surface` | `#ffffff` | Cards, panes |
| `--surface-2` | `#fbfbf9` | Card hover, user-message bubble |
| `--hairline` | `rgba(15, 17, 21, 0.07)` | Card borders |
| `--hairline-strong` | `rgba(15, 17, 21, 0.12)` | Button borders, focused-control border |
| `--fg` | `#16181d` | Body text |
| `--fg-mute` | `#6a6e76` | Secondary text (4.81:1 vs `--bg` — body AA) |
| `--fg-faint` | `#878d96` | Faint hints (3.14:1 vs `--bg` — AA-large) — **calibrated** from mockup `#9da3ad` |
| `--fg-on-danger` | `#ffffff` | Text on `--danger` (`.btn-primary.danger`) — 4.92:1 vs `--danger` (AA body) |
| `--accent` | `#3358c0` | Single accent (5.99:1 vs `--bg` — body AA) — **calibrated** from mockup `#4070e0` |
| `--accent-tint` | `rgba(51, 88, 192, 0.10)` | Accent backgrounds — opacity calibrated from mockup 0.08 (Decision 20) |
| `--accent-tint-strong` | `rgba(51, 88, 192, 0.18)` | Emphasis tint — opacity calibrated from mockup 0.14 (Decision 20) |
| `--success` | `#2f9c6a` | Status indicators |
| `--warn` | `#c98a2b` | Warn states |
| `--danger` | `#c5443d` | Danger states |
| `--shadow-1` | `0 1px 2px rgba(15,17,21,0.045), 0 1px 1px rgba(15,17,21,0.025)` | Default card shadow |
| `--shadow-2` | `0 4px 10px rgba(15,17,21,0.05), 0 1px 2px rgba(15,17,21,0.04)` | Hover card shadow |
| `--shadow-3` | `0 12px 28px rgba(15,17,21,0.08), 0 2px 4px rgba(15,17,21,0.04)` | Modal/popover surfaces |
| `--radius-card` | `12px` | Cards, panes |
| `--radius-control` | `8px` | Buttons, inputs |
| `--radius-chip` | `6px` | Chips |
| `--t` | `160ms cubic-bezier(0.2, 0, 0, 1)` | Single transition curve |

### Dark theme tokens (verbatim from `holograph-dark.html`)

| Token | Value | Notes |
|---|---|---|
| `--bg` | `#0a0c10` | Deep calm |
| `--surface` | `#14171c` | Cards, panes |
| `--surface-2` | `#181c22` | Hover surfaces |
| `--hairline` | `rgba(255, 255, 255, 0.08)` | |
| `--hairline-strong` | `rgba(255, 255, 255, 0.14)` | |
| `--fg` | `#e6e7ea` | Body text |
| `--fg-mute` | `#9aa1ac` | Secondary text |
| `--fg-faint` | `#6a7280` | Faint hints |
| `--fg-on-danger` | `#0a0c10` | Text on `--danger` (`.btn-primary.danger`) — deep ink on bright red (>=8:1) |
| `--accent` | `#a78bfa` | GleepGlorp violet |
| `--accent-tint` | `rgba(167, 139, 250, 0.10)` | |
| `--accent-tint-strong` | `rgba(167, 139, 250, 0.18)` | (reserved) |
| `--success` | `#4ade80` | |
| `--warn` | `#f5c97a` | |
| `--danger` | `#f87171` | |
| `--shadow-1` | `0 1px 2px rgba(0,0,0,0.25), 0 1px 1px rgba(0,0,0,0.18)` | |
| `--shadow-2` | `0 4px 12px rgba(0,0,0,0.32), 0 2px 4px rgba(0,0,0,0.22)` | |
| `--shadow-3` | `0 12px 30px rgba(0,0,0,0.40), 0 3px 6px rgba(0,0,0,0.25)` | |

Geometry / radii / motion tokens are identical across themes.

### Per-theme bespoke values

- `.brand-mark` background: light = `linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%)`; dark = `linear-gradient(135deg, #2a1f4d 0%, #1a1430 100%)`. Foreground stays `#fff`.
- `.agent-avatar` / `.provider-logo` background: light = `#e8eaef` / `#f0f1f3`; dark = `#26282d` / `#22262d`. Foreground: light = `#3c4048`; dark = `#c4c8cf`.
- `.btn-primary` foreground: light = `#fff` (on `#3358c0` — 6.01:1); dark = `#15101f` (on `#a78bfa` — calmer than glaring white).

### Per-theme `--badge-*`

Provider badges and tool-category badges have *theme-specific* values (continuation of the current pattern). The L1 author MUST preserve both sets — don't flatten:

```css
[data-theme="dark"] {
  --badge-filesystem: #008b8b; --badge-execution: #b8860b; --badge-web: #c71585;
}
[data-theme="light"] {
  --badge-filesystem: #0e8e8e; --badge-execution: #c5912a; --badge-web: #d63a93;
}
```

Provider brand colors (OpenAI / Anthropic / Ollama / OpenRouter / OpenAI-compatible / Mock / Unknown) are theme-stable (brand stability over palette consistency).

### Retired tokens

All `--glass-*`, all `--bezel-*`, `--accent-glow`, `--accent-glow-strong`, `--accent-translucent`, `--accent-translucent-hover`, `--bg-gradient`, `--panel-shadow`, `--panel-radius`, `--panel-radius-sm`, `--surface-translucent`, `--btn-v3-gradient`, `--sidebar-w`, `--sidebar-bg`, `--nav-bg`, `--nav-bg-active`, `--nav-border`, `--nav-fg`, `--nav-fg-hover`, `--nav-fg-active`, `--ease-tactile`, `--motion-fast`, `--motion-base`, `--topbar-h`, `--code-block-bg`, `--code-block-fg`, `--surface-elevated`, `--surface-tool`, `--border-hover`, `--border-strong`, `--fg-secondary`, `--fg-tertiary`, `--fg-muted` (renamed to `--fg-mute`), `--fg-on-accent`, `--fg-on-accent-muted`, `--fg-tool-msg`, `--accent-api`, `--status-success-glow`, `--status-warning-glow`, `--status-danger-glow`, `--status-warning-bg-soft`, `--status-warning-bg-soft-2`, `--status-warning-border`, `--status-danger-muted`, `--status-danger-bg-soft`.

(`--fg-on-danger` is NOT retired — it's preserved per Decision 22 for `.btn-primary.danger` text.)

### Reduced-motion + reduced-transparency

```css
@media (prefers-reduced-motion: reduce) {
  :root { --t: 0ms; }
}

@media (prefers-reduced-transparency: reduce) {
  .topnav { background: var(--bg); backdrop-filter: none; -webkit-backdrop-filter: none; }
}
```

The reduced-transparency query has exactly one consumer: the sticky `.topnav` (which uses `backdrop-filter: saturate(140%) blur(8px)` for the translucent header).

### Typography

Body size is **13.5px** (per mockup). Current app uses ~14-15px. The change cascades into any test or component that computes pixel sizes — call this out in L1 so authors don't accidentally preserve the old size.

Font stacks:

```css
body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
.mono, code, .toolcall-name, .toolcall-content, .stat-value.mono, .agent-card-model, .tool-name, .kbd
  { font-family: 'JetBrains Mono', monospace; }
```

Letter-spacing `-0.005em` applies to body; tightens to `-0.01em` on `.brand-name`, `.session-title`, `.convo-title`, `.editor-title`, `.provider-name`. Section labels use `0.06em-0.12em` positive tracking with uppercase.

## Component vocabulary

(Unchanged from v1 — see §"Component vocabulary" in v1 archive if needed; full table is preserved here.)

### Shared / chrome

`.topnav`, `.brand`, `.brand-mark`, `.brand-name` (with `.sub`), `.navlinks`, `.navlink` (`.active`), `.nav-right`, `.search` (with internal `.kbd`), `.avatar`, `.area` (`.active`), `.area-header`, `.area-title`, `.area-sub`, `.btn`, `.btn-primary`, `.btn-ghost`, `.icn`, `.icn-sm`, `.icn-lg`, `.chip` (`.accent`, `.success`, `.warn`, `.mono`), `.dot` (`.live`, `.warn`, `.idle`), `.card` (`.interactive`, `.selected`), `.toggle` (`.on`), `.seg`, `.seg-btn` (`.active`), `.tabs`, `.tab` (`.active`), `.form-row`, `.form-label`, `.form-help`, `.form-control`, `.section-label`.

### Chat-specific

`.chat-layout`, `.sessions-pane`, `.sessions-header`, `.new-session-btn`, `.sessions-list`, `.session-card` (`.active`), `.session-title`, `.session-meta`, `.session-snippet`, `.session-time`, `.session-agent-dot`, `.convo-pane`, `.convo-header`, `.convo-title`, `.convo-agent`, `.convo-actions`, `.convo-stream`, `.msg-row` (`.user`), `.agent-avatar`, `.msg-body`, `.msg-meta`, `.msg-author`, `.msg-time`, `.msg-text`, `.toolcall` (`.open`), `.toolcall-header`, `.toolcall-icon`, `.toolcall-name`, `.toolcall-summary`, `.toolcall-status`, `.toolcall-chevron`, `.toolcall-body`, `.toolcall-section`, `.toolcall-section-label`, `.toolcall-content`, `.composer`, `.composer-box`, `.composer-input`, `.composer-controls` (with `.right`).

### Studio-specific (NEW: sub-nav)

`.studio-subnav` (mirrors `.admin-subnav`), `.studio-sub` (one per Agents / Knowledge / MCP Sources), `.studio-layout`, `.agents-pane`, `.agents-list`, `.agent-card` (`.selected`), `.agent-card-avatar`, `.agent-card-body`, `.agent-card-title`, `.agent-card-model`, `.agent-card-meta`, `.editor-pane`, `.editor-header`, `.editor-title-row`, `.editor-title`, `.editor-actions`, `.editor-sub`, `.editor-body`, `.editor-section`. Plus knowledge-specific: `.knowledge-stub-pane` (centered empty-state card). Plus MCP-sources-specific: `.mcp-sources-grid`, `.mcp-source-card` (`.selected`), `.mcp-source-head`, `.mcp-source-body`, `.mcp-source-editor-pane`.

### Admin-specific

`.admin-subnav`, `.subnav-item` (`.active`), `.admin-sub`, `.providers-grid`, `.provider-card` (`.selected`, `.expanded`), `.provider-head`, `.provider-logo`, `.provider-name`, `.provider-type`, `.provider-body`, `.provider-expanded-body`, `.provider-status`, `.stat-label`, `.stat-value` (`.mono`), `.tools-section`, `.tools-section-head`, `.tools-section-title`, `.tools-section-meta`, `.tools-grid`, `.tool-card` (`.disabled`), `.tool-head`, `.tool-name`, `.tool-toggle-wrap`, `.tool-desc`, `.general-grid`, `.general-card`, `.general-card-title`, `.general-card-sub`.

### Holograph-section-nav (markup-restyled primitive)

`section-nav.js` is restyled in L1; its public API is preserved verbatim:
- `App.layout.renderSectionNav(container, items, active, options)` — initial render
- `App.layout.updateActiveSection(container, active)` — active-state mutation (no re-render)

Consumers in `admin.js:228, 243, 692` and `studio.js:285, 562` need no caller changes. Only the emitted markup changes: container gets `.holograph-section-nav`, items get `.holograph-section-item` styled as underline-tab strips. `.admin-subnav` and `.studio-subnav` are styling aliases that adopt the same primitive. The internal `data-section-id` attribute, `role="tablist"` / `role="tab"` attribute layout, and keydown handlers are preserved.

### Modal / overlay

`.modal-backdrop`, `.modal-shell` (uses `--shadow-3`, default max-width 560px), `.modal-header`, `.modal-title`, `.modal-close`, `.modal-body`, `.modal-footer`, `.confirm-dialog` (380px shell), `.confirm-dialog.danger`. Used by OAuth-status, dirty-leave-confirm, delete-confirm, tool-config-editor, and the MCP source editor when surfaced as a sheet.

## App shell architecture

### `index.html` (new)

```html
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <nav class="topnav" id="app-topnav"></nav>
  <main id="main-content" tabindex="-1"></main>
</body>
```

The `<style>@layer tokens, base, components, areas, utilities;</style>` declaration is retained. Layer placement (pinned per Decision 17):
- `tokens.css` → `@layer tokens` (palette, radii, shadows, motion)
- `base.css` → `@layer base` (typography reset, scrollbar, focus rings, skip-link, body bg)
- `components.css` → `@layer components` (shared chrome: `.btn`, `.chip`, `.toggle`, `.seg`, `.tabs`, `.form-row`, `.holograph-section-nav`, `.modal-*`)
- `chat.css`, `studio.css`, `admin.css` → `@layer areas` (area-specific)
- (no explicit `@layer utilities` consumers in v1; reserved for future helpers)

### `registerArea` API (new)

```js
App.registerArea({
  id: 'chat', label: 'Chat', order: 1,
  init: function (content) { /* receives ONE element: the content panel */ },
  activate: function () {}, deactivate: function () {},
  hydrateState: function (sub) {},
  serializeState: function () {},
  confirmLeave: function () {},
});
```

The `init(sidebar, content)` signature becomes `init(content)`. Compatibility is explicitly retired (not "impossible" — every area is touched anyway).

### Topnav rendering

`app.js` renders the brand wordmark + center `.navlinks` (Chat / Studio / Admin) + right cluster (`.search` + bell + `.avatar`). The `.search` affordance is a button with `aria-label="Open search"` and `aria-keyshortcuts="Control+K Meta+K"`. In v1, clicking it triggers a stub `App.search.open()` that surfaces a small toast "Search coming soon." Wiring the actual command palette is out of scope.

### Per-area internal layout

- **Chat** renders `<div class="chat-layout"> <aside class="sessions-pane">…</aside> <div class="convo-pane">…</div> </div>` inside content.
- **Studio** renders `<div class="area-header">…</div> <div class="studio-subnav">…</div> <div class="studio-sub" id="sub-agents">…</div> <div class="studio-sub" id="sub-knowledge">…</div> <div class="studio-sub" id="sub-mcp-sources">…</div>` inside content. Each `.studio-sub` is shown/hidden by display:block/none keyed off the active sub.
- **Admin** renders `<div class="area-header">…</div> <div class="admin-subnav">…</div> <div class="admin-sub" id="sub-providers">…</div> <div class="admin-sub" id="sub-tools">…</div> <div class="admin-sub" id="sub-general">…</div>`.

## Area-by-area IA

### Chat

Per mockup, two-column layout (280px sidebar + flex content). Existing behavior preserved: WebSocket streaming, tool-call rendering (one block per invocation, collapsible), multi-session model, agent picker (right side of convo header), telemetry overlay (repositioned as a `.chip` in `.convo-header` showing context-window usage), thinking indicator (renders as a `.toolcall.open` with `.dot.live` and the text "Thinking…" before any tools run), history buckets (Today / Yesterday / This week as small `.section-label` headings in `.sessions-list`), new-chat button, attach + mention-agent buttons.

Empty states: no-provider → full-pane "Get started" with link to Admin → Providers. No-agents → similar, link to Studio → New agent. Agents exist but no session → convo-pane placeholder.

### Studio (REWRITTEN)

Studio has a top-level `.studio-subnav` with **three sections**, each addressable via `#studio/<sub>`:

#### Agents (`#studio/agents`)

Two-column layout (320px `.agents-pane` + flex `.editor-pane`). Same as the mockup. When no agent is selected, `.editor-pane` shows a "Create your first agent" empty-state card. When an agent is selected, the editor renders title-row + four-tab strip + body. Tabs: **General** (Name, Avatar initial, Provider, Model, System prompt, Behavior toggles — per mockup); **Tools** (per-agent tool toggles + category filter chips, rendered as `.tools-grid` of tool cards mirroring Admin → Tools); **MCPs** (per-agent MCP source attachments — a list of `.mcp-source-card` instances with toggles; click → opens the per-agent MCP attachment editor — the F8 L3 deep-link `#studio/agents/{name}/mcps/{source-id}` preserved); **Tool Overrides** (per-tool override editor using marker-dispatched widgets via `tools-form-helpers.js`).

Routes preserved (URL encoding semantics from `studio.js:23-58, 74-120`):
- `#studio/agents` → list, no agent selected
- `#studio/agents/{name}/general` (or `/knowledge`, `/mcps`, `/tools`) — F5 L3 tab-in-URL
- `#studio/agents/{name}/mcps/{source-id}` — F8 L3 deep-link to per-agent MCP attachment editor

URL encoding rules (preserved verbatim from the existing router):
- Agent names are `encodeURIComponent`-encoded; literal `/` in a name renders as `%2F` so the segment separator is unambiguous.
- Defensive trailing-slash: `#studio/agents/{name}/` is treated as no-tab and defaults to `/general`.
- Tab whitelist `general|knowledge|mcps|tools` enforced in `hydrateState`; unknown tabs default to `general`.
- For the MCPs deep-link, `{source-id}` is also `encodeURIComponent`-encoded; defensive split-at-first-`/` ignores extra path segments.

#### Knowledge (`#studio/knowledge`)

Single `.knowledge-stub-pane` centered card with "Knowledge base coming soon" headline, 1-line sub, and (optionally) a disabled primary button. Preserves the `data-testid="studio-knowledge-stub"` selector used by `test_flow_studio_navigation.py`.

#### MCP Sources (`#studio/mcp-sources`)

Top-level grid view of `.mcp-source-card` instances. Each card: source name + transport type chip (`stdio` / `streamable-http`) + last-used timestamp + status dot. Clicking a card navigates to `#studio/mcp-sources/{id}` and opens a full `.mcp-source-editor-pane` (NOT a modal — the existing 1,654-line `mcp-server-editor.js` form is preserved verbatim, only its styling moves to the Holograph vocabulary).

The editor preserves:
- **OAuth Reset surface** — the single existing "Reset connection" button at `mcp-server-editor.js:343-345` (data-testid `reset-mcp-connection-btn`). Visible only for streamable-http sources with stored OAuth state; idempotent on already-clean state per the existing implementation. Clears the stored OAuth credentials + tools list. Confirm-gated via the existing tooltip-equipped button. Styling adopts the Holograph `.btn` vocabulary (`.btn-outlined-primary` class is renamed but the button position + behavior + data-testid stay).
- **`__MASKED__` per-key secrets contract** (per CLAUDE.md "MCP source storage contract") — the editor sends `__MASKED__` for any secret value the operator did not modify. GET masks secret values as `***...{tail4}` (or `***` for ≤4-char values). The submit handler walks the `secrets` dict; keys whose values are `__MASKED__` are preserved; other keys overwrite. **Backend contract preserved verbatim**: `oauth_client_secret` routes to `secrets["oauth_client_secret"]`, NOT `config.oauth.client_secret` (F1 payload-key contract).
- **Danger zone** — Delete source button at the bottom; danger-styled `.btn-primary.danger` with confirm-dialog.
- **Test connection button** — invokes `POST /api/mcp-sources/{id}/test/connect`. OAuth-protected sources drive the spec-compliant DCR + auth-code flow in a popup via `the_one/mcp/oauth/handlers.py`; the first click triggers consent at the IdP, the second click lists tools.
- The synthetic-csid pattern (`test:{source_id}` for Test Connection, `agent_build:{source.id}` for non-chat OAuth) is preserved in the backend; the frontend just shows the OAuth-status modal during the consent flow.

#### Per-agent MCP attachment editor (deep-link `#studio/agents/{name}/mcps/{source-id}`)

Inside the Studio · Agents · MCPs tab, clicking an attached MCP source's card opens a per-agent attachment editor (side-pane, NOT modal — composes inside the existing `.editor-pane`). The deep-link route `#studio/agents/{name}/mcps/{source-id}` is preserved (F8 L3).

Layout: header strip (source name + transport-type chip + back-arrow to the MCPs tab list) → "OAuth state" callout if applicable (read-only — operators reset OAuth from the top-level MCP source editor, not here) → "Cached tools" section (a list of tools the source has surfaced, each with a per-agent enable toggle and a per-tool small chip showing the agent override count) → "Tools mode" segmented control (`allowlist` / `denylist`, mirrors the existing `mcps-tab.js` mode toggle) → Save / Discard actions in the editor-header right side.

Dirty handling: the existing `confirmLeave` hook on the Studio area covers the back-arrow click + cross-area navigation. Auth-required notice: if the parent source is in `auth_required` state, the per-agent editor surfaces an inline notice "Connect this source from the MCP Sources page to enable tool selection" with a link to `#studio/mcp-sources/{id}`. Close-to-list behavior: clicking the back-arrow updates the URL to `#studio/agents/{name}/mcps` and the editor unmounts.

Routes preserved:
- `#studio/mcp-sources` → grid
- `#studio/mcp-sources/new` → editor in add mode
- `#studio/mcp-sources/{id}` → editor in edit mode

### Administration

Per mockup, subnav strip + content. Three subs: **Providers** (3-col `.providers-grid`, expandable card per Decision 19), **Built-in Tools** (grouped `.tools-section` per category with `.tools-grid`), **General** (2-col `.general-grid` — Appearance theme `.seg`, Encryption fingerprint + Rotate button, Base prompt readonly textarea, System info mono key/value list).

**Legacy redirect preserved**: `#admin/system` continues to redirect to `#admin/general` (Flight 3 Leg 06 contract — `admin.js:48-54`). The redirect is implemented in `admin.js`'s `hydrateState`; the v2 spec preserves the line verbatim. Saved bookmarks survive.

Removed: Design Language sub-page + the `js/areas/admin/design-language/` directory. Mission 08 artifact.

## Non-mockup surface coverage

### Confirm dialog

380px `.modal-shell`. Body: title + 1-2 sentences. Footer: ghost "Cancel" + primary "Confirm" (or `.btn-primary.danger` for delete). Used by dirty-leave, delete-confirm (agent, provider, MCP source).

### OAuth-status modal

Inside-app status while the OAuth popup is open. 480px `.modal-shell` with an inline-spinner + "Waiting for authorization at {idp_host}…" message + Cancel button. The popup itself is the system browser; we only style the in-app status. Preserves the `auth_required` event no-op suppression on synthetic csids.

### Tool-config editor (modal)

Reached from Admin → Built-in Tools by clicking a `.tool-card`. Modal with the per-tool config form using `tools-form-helpers.js` marker dispatch. Existing widget logic preserved; styling adopts `.form-row` / `.form-control` / `.chip` / `.toggle`.

### MCP source editor

Full-pane editor inside Studio → MCP Sources (not modal — too complex). Existing `mcp-server-editor.js` provides form structure; styling moves to Holograph.

### Per-agent tool overrides

Inside Studio → Agents → Tool Overrides tab. List of expandable tool cards; each expanded card renders the override form (marker-dispatched, agent-mode locked chips for `NarrowSuperset` operator-set entries — per the F6 admin-UI pattern in CLAUDE.md).

### Empty / error / loading

- **Empty state**: centered icon + headline + 1-line sub + primary button (no-providers, no-agents, no-sessions, no-MCP-sources).
- **Inline error**: `.field-error` red text below a form field; `.editor-error-banner` for model-level errors.
- **Loading**: subtle `.dot.live` next to a label. No big spinners.

### Streaming

Thinking indicator: `.toolcall.open` + `.dot.live` + "Thinking…" before tool calls start. Once tool calls run, real toolcall blocks render in their place.

## Theme switching + accent-color logic

`App.theme.set('light' | 'dark' | 'auto')` continues to work. `--accent` is theme-scoped (`#3358c0` light / `#a78bfa` dark) — switches automatically. The Admin → General → Appearance toggle uses existing `App.theme.renderToggle(container, options)` API with `.seg` + `.seg-btn` styling.

## Migration ordering (within the PR)

| Leg | Title | Scope |
|---|---|---|
| L1 | Tokens + base + section-nav primitive | New `tokens.css` (both themes), `base.css`, `components.css` (incl. `.holograph-section-nav`, `.modal-*`). New `fonts.css` self-hosting Inter + JetBrains Mono (purges Geist). `section-nav.js` rewritten. |
| L2 | Shell rewrite | `index.html` topnav-only structure. `app.js` updated: `renderTopNav`, `registerArea({init: fn(content)})`. Hash routing preserved (incl. `#admin/system` redirect verified). `.search` aria + stub toast. |
| L3 | Chat area | `chat.css` full rewrite. `chat.js` + inner JS (welcome, history-buckets, message-bubble, telemetry-overlay, thinking-indicator) emit new classes. Flow tests under `tests/browser/test_flow_chat.py`, `test_flow_streaming.py`, `test_flow_new_chat.py`, `test_flow_markdown_chat.py` get selector updates. |
| L4 | Studio area + sub-nav | `studio.css` full rewrite. `studio.js` renders area-header + `.studio-subnav` + 3 `.studio-sub` blocks. Agent editor (general/knowledge/mcps/tools tabs) migrated. Knowledge stub migrated. MCP Sources grid + editor migrated (incl. OAuth Reset + `__MASKED__` contract verified). Flow tests under `test_flow_studio_*.py`, `test_studio_mcps_tab.py`, `test_oauth_modal_flow.py`, `test_mcp_test_connection_button.py`, `test_flow_studio_mcp_*.py` updated. |
| L5 | Admin area | `admin.css` full rewrite. `admin.js` renders area-header + `.admin-subnav` + 3 `.admin-sub`. Provider grid + expanded state + 3-position snapshots (Decision 19). Tool-config editor modal restyled. System page (General) restyled. Design Language page DELETED. `#admin/system → general` redirect re-verified. Flow tests under `test_flow_admin_*.py` updated. |
| L6 | Modals + dialogs | `confirm.js`, `dialog.js` reskinned. OAuth-status modal restyled. Tool-config-editor modal restyled. All modal flow tests verified. |
| L7 | Cross-area tests + final snapshot rebase | Cross-area flow tests (`test_flow_hash_routing.py`, `test_flow_dirty_confirm.py`, `test_flow_keyboard.py`, `test_flow_picker.py`) get selector updates. All 28+ visual snapshots regenerated. Token a11y test re-audited. Token-definitions test passes. `tests/browser/design_tokens.py` rewritten. |
| L8 | Cleanup | Remove `gleepglorp_banner.png` reference from `index.html` (file stays on disk; deletion is housekeeping). Update CLAUDE.md "Design system" section. Update `the_one/agents.md` "Design system" section. Update `playground/index.html` to mark Holograph as the shipped direction. |

**Selector-update timing (Decision 11)**: per-area selector updates happen in their own leg. L7 catches cross-area stragglers (~5-7 tests).

## Test strategy

### Actual test surface

`tests/browser/` has 24 `test_flow_*.py` files plus 12 other browser tests (`test_oauth_modal_flow.py`, `test_mcp_test_connection_button.py`, `test_studio_mcps_tab.py`, `test_markdown.py`, `test_smoke.py`, `test_seeders.py`, `test_app_fixture.py`, `test_visual_snapshots.py`, etc.). The migration impacts essentially all of them; the per-leg ownership is (each test appears in exactly one leg):

| Leg | Tests touched |
|---|---|
| L3 (Chat) | test_flow_chat, test_flow_streaming, test_flow_new_chat, test_flow_markdown_chat, test_flow_picker, test_markdown |
| L4 (Studio) | test_flow_agent_crud, test_flow_agent_tabs, test_flow_agent_tile, test_flow_studio_navigation, test_flow_studio_mcp_editor, test_flow_studio_mcp_navigation, test_flow_studio_openrouter_picker, test_flow_studio_tools_overrides, test_studio_mcps_tab, test_mcp_test_connection_button |
| L5 (Admin) | test_flow_admin_navigation, test_flow_admin_openrouter, test_flow_admin_tools_editor, test_flow_admin_tools_grid, test_flow_provider_dirty_confirm, test_flow_provider_editor, test_flow_provider_grid, test_flow_provider_setup |
| L6 (Modals) | test_oauth_modal_flow |
| L7 (cross-area + final snapshot) | test_flow_hash_routing, test_flow_dirty_confirm, test_flow_keyboard, test_smoke, test_app_fixture, test_seeders |

### Visual snapshot matrix (≥28)

| Area | States | Themes | Total |
|---|---|---|---|
| Chat | active-session, empty-state | light, dark | 4 |
| Studio · Agents | agent-selected, agent-list-empty, mcps-tab, mcps-attachment-editor, tools-tab, overrides-tab | light, dark | 12 |
| Studio · Knowledge | stub-page | light, dark | 2 |
| Studio · MCP Sources | grid, editor | light, dark | 4 |
| Admin · Providers | grid, expanded-col1, expanded-col2, expanded-col3 (Decision 19) | light, dark | 8 |
| Admin · Tools | grid, tool-config-editor-modal | light, dark | 4 |
| Admin · General | page | light, dark | 2 |
| Modals | confirm-dialog, oauth-status | light, dark | 4 |

Total: 40 baselines (floor: 28). Exact count finalized in L7.

### A11y audit (recomputed contrast pairs)

| Pair | Theme | Contrast | Threshold | Pass? |
|---|---|---|---|---|
| `--accent` × `--bg` | light (`#3358c0` × `#f8f8f6`) | ~5.99:1 | 4.5 body | ✓ |
| `--accent` × `--bg` | dark (`#a78bfa` × `#0a0c10`) | ~7.19:1 | 4.5 body | ✓ |
| `--fg` × `--bg` | light (`#16181d` × `#f8f8f6`) | ~15.5:1 | 7.0 AAA | ✓ |
| `--fg` × `--bg` | dark (`#e6e7ea` × `#0a0c10`) | ~15.2:1 | 7.0 AAA | ✓ |
| `--fg-mute` × `--bg` | light (`#6a6e76` × `#f8f8f6`) | ~4.81:1 | 4.5 body | ✓ |
| `--fg-mute` × `--bg` | dark (`#9aa1ac` × `#0a0c10`) | ~7.6:1 | 4.5 body | ✓ |
| `--fg-faint` × `--bg` | light (`#878d96` × `#f8f8f6`) | ~3.14:1 | 3.0 AA-large/UI | ✓ |
| `--fg-faint` × `--bg` | dark (`#6a7280` × `#0a0c10`) | ~4.14:1 | 3.0 AA-large/UI | ✓ |
| `#fff` × `--accent` | light primary button | ~6.37:1 | 4.5 body | ✓ |
| `#15101f` × `--accent` | dark primary button | ~9.5:1 | 4.5 body | ✓ |
| `--fg-on-danger` × `--danger` | light (`#fff` × `#c5443d`) | ~4.92:1 | 4.5 body | ✓ |
| `--fg-on-danger` × `--danger` | dark (`#0a0c10` × `#f87171`) | ~8.7:1 | 4.5 body | ✓ |

`--fg-faint` is documented in tokens.css as "AA-large only; used for non-essential text (timestamps, unit suffixes, hint text); MUST NOT carry body content." Same convention as the current light theme.

### Token-definitions test

`tests/test_token_definitions.py` verifies every `var(--x)` reference. Retired tokens disappear from both sides.

### `tests/browser/design_tokens.py`

Mirror is rewritten with the new token names + values.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Approach B's `init(content)` change breaks an area we miss | L1-L7 sequence touches every JS file under `js/areas/`. Audit before merge. |
| 38 snapshot count slows CI | 12 → 38 ≈ 3× snapshot time, still ~90s. Parallelize via pytest-xdist if pain emerges. |
| Token rename (`--fg-muted` → `--fg-mute`) breaks `design_tokens.py` mirror or test imports | Renamed in L1; rest of mission runs against consistent tokens. |
| Modals lack a visual mockup → designs may diverge from pixel-perfect intent | v2 spec is explicit (sizes + structure). If misalignment surfaces in code review, a follow-up mockup pass is cheaper than rework. |
| Removing Design Language page deletes living docs | Page lives in git history; ref-pointer in CLAUDE.md if useful. |
| `gleepglorp_banner.png` orphaned on disk | Tracked as L8 cleanup item. Zero runtime risk. |
| Tests breaking mid-mission cause red CI | Per-leg selector updates contain breakage; feature branch tolerates red CI; main is gated. |
| `__MASKED__` per-key secrets contract regression | L4 verifies via `test_flow_studio_mcp_editor.py` AND a manual smoke covering: create source with secret → edit form shows `***...tail4` → save without modifying → backend retains original (round-trip test from current suite). |
| OAuth synthetic-csid suppression breaks if modal class names move | L6 verifies via `test_oauth_modal_flow.py` AND a chat-popup smoke. |
| Provider-card `.expanded` reflow blows past 2% snapshot tolerance | Decision 19: three column-position snapshots. Total Provider snapshots: 8 (grid + 3 expanded × 2 themes). |
| Mockup max-width 1440px vs current unconstrained width | Standardized via `.area { max-width: 1440px; margin: 0 auto; }`. Ultra-wide displays show centered content. |
| Light accent at body-AA edge — minor SRGB rounding could flip pass/fail | Use a rounded ratio (5.65 → 5.6:1) in the audit assertion to absorb rounding. |
| `--fg-faint` calibration deviates from mockup | Documented in §"Visual ground truth" — implementation authoritative on a11y calibrations. |
| Body-size 13.5px change cascades into pixel-size assertions | L1 author calls this out in commit body; per-leg test updates catch hits. |
| `section-nav.js` rewrite breaks consumers if API changes | API documented in §"Holograph-section-nav"; preserve `mount/setActive/getActive/destroy` shape. |
| Self-hosting Inter + JetBrains Mono adds binary assets to the repo | Use latin-subset WOFF2 only (~100-150KB total). Acceptable given the existing Geist self-host precedent. |
| Light primary button passes AA but at a thinner margin in some sub-states (hover bg `#2d4eb0`) | Hover state also computed: `#fff × #2d4eb0` ≈ 6.7:1 — passes. |
| **Section-nav restyle breaks consumer callers if data attributes change** | Decision 17: internal `data-section-id` attribute + `role="tablist"`/`role="tab"` semantics are preserved. L1 markup-only swap; behavior unchanged. |
| **Per-agent MCP attachment editor design under-specified** | v3 §"Per-agent MCP attachment editor" adds explicit layout + dirty handling + auth-required notice + back-arrow contract. Visual snapshot added in L7 (light + dark). |
| **OAuth Reset misrepresented as new feature in v2** | v3 Decision 21 corrects: single existing "Reset connection" button (data-testid `reset-mcp-connection-btn`) preserved verbatim. No new endpoints; non-goal "no new features" satisfied. |
| **`--fg-on-danger` retirement reversal** | Decision 22: token preserved in both theme tables (light `#fff` / dark `#0a0c10`). Audit pair re-valid. |
| **Backend contract preservation (OAuth `client_secret` payload-key)** | The MCP source editor's submit handler routes `oauth_client_secret` to `secrets["oauth_client_secret"]`, NOT `config.oauth.client_secret` (F1 contract). UI restyle doesn't touch this routing; L4 verifies via the existing `test_flow_studio_mcp_editor.py` save-flow assertion. |
| **Backend contract preservation (encryption rotation invariant)** | `/api/encryption/rotate` requires no non-DML between SELECT and commit (CLAUDE.md rotation invariant). The Holograph migration touches only frontend; the rotate handler is unchanged. L5 visual snapshot covers the General page "Rotate" button styling. |

## Out of scope

- Command palette behavior beyond a stub toast.
- Mobile/narrow-viewport.
- Snapshots for any state not in the matrix.
- Performance optimization.
- Animations beyond `--t`.
- Storybook.
- Migrating font files away from latin-subset.

## Open questions (resolved)

- ~~Should `.search` open a working palette in v1?~~ **No** — stub toast.
- ~~Banner cleanup~~ — **L8 removes the reference; file stays on disk** (housekeeping later).
- ~~Modal designs need own mockup?~~ **No** — spec is explicit; refine in code if review surfaces issues.
- ~~Self-host new fonts vs CDN?~~ **Self-host** (Decision 15).
- ~~Studio sub-nav vs flat tabs?~~ **Sub-nav** (Decision 16).
- ~~`section-nav.js` defer to L2?~~ **Decided in L1** (Decision 17).
- ~~`--fg-faint` AA-large floor?~~ **Calibrated to `#878d96`** (Decision 18).
- ~~Provider `.expanded` reflow~~ — **3-position snapshots** (Decision 19).

## Appendix: file-by-file change list

### CSS (full rewrites)

- `tokens.css`, `base.css`, `components.css`, `chat.css`, `studio.css`, `admin.css`, `fonts.css` (Inter + JetBrains Mono self-hosted; Geist purged)

### Font assets (new)

- `static/fonts/Inter-{400,500,600,700}.woff2` (latin subset)
- `static/fonts/JetBrainsMono-{400,500}.woff2` (latin subset)
- Delete: `static/fonts/Geist*.woff2` and `static/fonts/GeistMono*.woff2`

### HTML

- `index.html` — topnav-only structure; banner image reference removed

### JS

- `app.js` — renderTopBar → renderTopNav; switchTo updated; `init(content)` API
- `theme.js` — preserved (public API unchanged); `.seg` markup
- `areas/layout/section-nav.js` — rewritten as `.holograph-section-nav` (Decision 17)
- `areas/chat.js` + inner (welcome, history-buckets, message-bubble, telemetry-overlay, thinking-indicator) — render updates
- `areas/studio.js` (1851 lines) + inner (agent-editor, general-tab, knowledge-tab, mcps-tab, tools-tab, mcp-servers-grid, mcp-server-editor (1654 lines), stub-knowledge) — render updates; `.studio-subnav` introduced
- `areas/admin.js` + inner (providers-grid, provider-editor, provider-models, tools-grid, tools-editor, tools-form-helpers, system-page) — render updates; `system → general` redirect preserved verbatim
- `areas/admin/design-language-page.js` + `design-language/` directory — **DELETED**
- `confirm.js`, `dialog.js` — modal markup updated
- `tabs.js`, `icons.js`, `markdown.js` — verified compatible; minor markup updates only

### Tests

- `test_visual_snapshots.py` — 38 baselines
- `__snapshots__/` — regenerated
- `design_tokens.py` — rewritten
- `test_design_tokens_a11y.py` — audited pairs list updated; `--fg-faint` documented exception preserved
- `test_token_definitions.py` — verifies new `var(--*)`
- All ~22 `test_flow_*.py` files — selectors updated per leg
- `test_oauth_modal_flow.py`, `test_mcp_test_connection_button.py`, `test_studio_mcps_tab.py` — selectors updated
- `test_markdown.py`, `test_smoke.py`, `test_app_fixture.py`, `test_seeders.py` — selectors updated where chat/topnav DOM is asserted

### Documentation

- `CLAUDE.md` "Design system" — refreshed to point at Holograph tokens, mockups, class vocabulary
- `the_one/agents.md` "Design system" — same
- `playground/index.html` — note Holograph as shipped direction
