# F5 Sweep Coverage Report

**Date**: 2026-05-23
**Executor**: F5 L5 sweep agent (Chrome MCP-driven; operator not in loop per L5 protocol)
**Flight**: [Connector UX Cleanup](./flight.md)
**Leg**: [05 — connector-ux-sweep](./legs/05-connector-ux-sweep.md)

## Methodology

Each of the six target surfaces was navigated via `mcp__chrome-devtools__navigate_page` with `ignoreCache: true`, then walked top-to-bottom by combining the accessibility-tree snapshot (`take_snapshot`) with DOM-shape introspection (`evaluate_script`) to extract structural class names, `data-testid` anchors, and computed-style state. Each visible element is enumerated at the **primitive** level (a `field-row` is one row regardless of its label/input/info-icon children; a `<details>/<summary>` disclosure is one row; a tab strip is one row with per-tab buttons noted). Sub-element decomposition is only used where a child uses a different primitive than its parent. Each element row maps to (a) a Design Language primitive named in `the_one/interfaces/web/static/js/areas/admin/design-language/*.js`, (b) an MCP-editor pattern from `mcp-server-editor.js`, or (c) DEFERRED with a follow-up entry below.

Reference catalogs (re-read at sweep time):
- DL primitives: `field-input`, `field-select`, `field-textarea`, `field-info-icon`, `checkbox-primary`, `tool-enable-switch`, `chip` + `chip-remove`, `indicator-led` (success/warning/danger/idle), `test-result`, `app-flash`, `banner`, `entity-tile`/`entity-tile-grid`, `section-nav`, `list-item`, `app-picker-button`, `tablist` + `tab` + `tabpanels`, `modal-dialog`, `markdown`, `field-row` / `admin-pf-row`, `empty-state`, `empty-canvas`, button primitives (`btn-outlined-primary`, `btn-filled-primary`, `btn-muted-destructive` with size modifiers).
- MCP-editor patterns: `editor-section` + `section-title` (with `::before` `//` divider on `.section-title`), `mcp-test-row` (Connection footer-row pairing button + LED + message), `<details>` collapsibles with a single class, `field-info-icon` info-icon usage (`title=` + `aria-describedby` + `.visually-hidden` help-text), `entity-tile-grid` for sources listing, `mcp-tool-item` collapsible tool rows, `kv-section-title`, `editor-section.danger-zone` + `section-title.danger-zone-title`.

## Surface 1 — New Connector page (`#studio/connectors/new`)

Flat layout, no tabs (no A&R until save). Three sections in DOM order: Connection, Credentials, Lifecycle.

| Element | Primitive / Pattern | Source | Notes |
|---|---|---|---|
| Editor header (title `New Connector` + Back / Cancel / Create & Test buttons) | `editor-header` wrapper + `h1.editor-title` + `.form-actions` cluster | MCP editor convention | Buttons: `btn-outlined-primary.back-btn`, `btn-outlined-primary.cancel-btn`, `btn-filled-primary.save-btn` (Cancel + Save are `disabled` when no dirty state — canonical disabled-state from `buttons-section.js`). |
| Section: Connection (`editor-section` + `section-title`) | `editor-section` + `section-title` (MCP pattern) | `mcp-server-editor.js:441-442` | `section-title::before { content: "//" }` decorative divider (verified computed-style; `color: rgb(167,139,250)`, `font-family: Geist Mono`). `data-testid="connector-connection-section"`. |
| Name field-row | `field-row admin-pf-row` + `field-input admin-pf-input` (DL) | `fields-section.js:9` | Label + text input. |
| Type field-row | `field-row admin-pf-row` + `field-input field-select admin-pf-input admin-pf-select` (DL) | `fields-section.js:11-15` | Native `<select>` with single `Discord` option in this build. |
| Config field-row (KV adder) | `field-row admin-pf-row connector-account-config-wrap` + `.connector-account-config` body wrapping `+ Add row` button | `mcp-server-editor.js` KV pattern | Empty state shows only the `btn-outlined-primary kv-add-row-btn` (`connector-config-add-row-btn`). No rendered table until first row added. |
| Section: Credentials (`editor-section` + `section-title`) | `editor-section` + `section-title` (MCP pattern) | `mcp-server-editor.js:605-606` | Same divider treatment via `::before`. |
| Credentials KV adder | KV `+ Add row` button only (no rows yet) | `mcp-server-editor.js` KV pattern | `btn-outlined-primary kv-add-row-btn connector-secrets-add-row-btn`. Same shape as Config. |
| Section: Lifecycle (`editor-section` + `section-title`) | `editor-section` + `section-title` (MCP pattern) | F5 L3 placement | Lifecycle section moved from A&R to General-shared in non-edit; appears on the new page too. |
| Pool idle timeout field-row | `field-row admin-pf-row` + `field-input field-select admin-pf-input admin-pf-select` + `field-info-icon` (DL) | `fields-section.js:11,18-25` | Label + info-icon button (`title=`, `aria-describedby`, `.visually-hidden` help-text — MCP info-icon pattern verified in HTML). 7 TTL options; "30 minutes (default)" selected. |
| Chat-session continuation window field-row | `field-row admin-pf-row` + `field-input field-select` + `field-info-icon` (DL) | `fields-section.js` | 8 options; "1 day (default)" selected. Same info-icon pattern. |
| Auto-reply to platform messages field-row | `field-row admin-pf-row cf-auto-relay-row` + `tool-enable-switch` toggle + `field-info-icon` (DL) | `surfaces-section.js:90-101` (`tool-enable-switch`); `fields-section.js:18-25` (info-icon) | iOS-style toggle (`<label.tool-enable-switch><input.field-input type=checkbox><span.tool-enable-switch-track aria-hidden></span></label>`). Checked by default. |
| Section divider `//` (between sections) | `.section-title::before { content: "//" }` (CSS pseudo, not DOM node) | shared CSS | Verified via computed-style probe — NOT a separate primitive, just `section-title` decoration. |

Element count: 12 primitive rows (header counts as one cluster row).

L4 cold-pool verification on this surface: no `discoverable-dropdown-chips-*` containers exist on the new-connector page because the A&R tab itself doesn't render until after save (the dropdowns live in A&R). The L4 chips-hide side effect is best verified on Surface 2 (Discord edit-mode A&R) — see that surface's notes.

## Surface 2 — Discord Constellation edit-mode → General tab (`#studio/connectors/58f1fe5a833f`)

Tabbed layout. General tab visible; A&R tab in DOM but `hidden` (verified: panel `connector-tab-panel-general` `hidden=false`, `connector-tab-panel-access-and-routing` `hidden=true`).

| Element | Primitive / Pattern | Source | Notes |
|---|---|---|---|
| Editor header (title `Discord Constellation` + subtitle `discord · default TTL` + Back / Cancel / Save) | `editor-header` + `h1.editor-title` + subtitle span + `.form-actions` | MCP editor convention | Cancel + Save initially `disabled`. |
| Tablist (`General` / `Access and Routing`) | `tablist` + `tab` (DL) | `tabs-section.js:14-18` | Two tabs; `General` `aria-selected=true`, `Access and Routing` `aria-selected=false`. Uses canonical `window.App.tabs(...)` helper. |
| Section: Connection | `editor-section` + `section-title` | `mcp-server-editor.js:441-442` | `data-testid="connector-connection-section"`. |
| Name field-row | `field-row admin-pf-row` + `field-input admin-pf-input` (DL) | `fields-section.js:9` | Value: `Discord Constellation`. |
| Type field-row (read-only) | `field-row admin-pf-row` + `field-input admin-pf-input` `readonly` (DL) | `fields-section.js:9` | Read-only `discord`. |
| Config field-row (KV adder, populated) | `field-row admin-pf-row connector-account-config-wrap` + `.connector-account-config` | MCP KV pattern | Adopts same shape as new page; populated table rows are sub-children. |
| Test-connection footer row | `field-row admin-pf-row connector-test-row` + `btn-outlined-primary connector-test-connection-btn` + `indicator-led indicator-led--idle connector-test-led` + `.connector-test-message` | `status-section.js:17-24` (`indicator-led`); MCP `mcp-test-row` analog (`mcp-server-editor.js:473`) | This is a Discord-flavored `mcp-test-row` variant — uses `.connector-test-row` class instead of `.mcp-test-row` but the same compositional pattern (button + LED + message in a `field-row admin-pf-row`). Initial state: `idle` LED, "Not tested" message. |
| Section: Credentials | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Bot Token field-row | `field-row admin-pf-row` + `field-input admin-pf-input` masked + reveal button | DL field-input + MCP KV-sensitive reveal pattern (`mcp-server-editor.js:792`) | Mask shown as `••••••••••`; eye-icon "Show value" button. Hint: "Discord bot token. Stored encrypted at rest; shown masked on read." (`.form-hint` / `<small class="form-hint">`). |
| Section: Pairing (`editor-section.connector-pairing-section`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` shape | F4 introduced; class scoping for pairing-specific layout. |
| Pairing Status field-row | `field-row admin-pf-row` + `btn-outlined-primary connector-pairing-generate-btn` + `.connector-pairing-status` | DL button + status text | "Generate code" button + status string "No pairing code generated yet." |
| Pairing Code reveal row (hidden when no code) | `field-row admin-pf-row connector-pairing-reveal-row` + `field-input admin-pf-input connector-pairing-code-input` readonly + copy button | DL field-input + icon button | Initially `hidden=""` (verified). Copy button has `aria-label="Copy pairing code"`, `title="Copy"`. |
| Section: System Prompt Directive (`editor-section.connector-directive-section`) | `editor-section` + `section-title` + `<textarea>` + `.form-hint` + three `<details class="connector-directive-disclosure">` | `mcp-server-editor.js:237` (`<details>` collapsible single-class pattern) | Three disclosures: auto-relay-ON, auto-relay-OFF, platform-send-disabled — each `<details>/<summary>` is one row by granularity convention. Inner `<pre><code>` is the canonical default. |
| Section: Attached agents (`editor-section.connector-attached-agents-section`) | `editor-section` + `section-title` + `<table.connector-attached-agents-table>` | `editor-section` + DL table primitive (table itself is bespoke; see deferral) | Columns: Agent / Users / Channels. Rows have `<a.connector-attached-agent-link>` for agent name + `<em.form-hint>inherits</em>` for default axes + `<span class="chip">` for restrictions. The TABLE shell is bespoke; see deferral. |
| Section divider `//` (between sections) | `.section-title::before` (CSS pseudo) | shared CSS | Same as Surface 1. |
| Section: Danger Zone (`editor-section.danger-zone`) | `editor-section.danger-zone` + `section-title.danger-zone-title` | `mcp-server-editor.js:619-620` | Single `btn-muted-destructive` Delete Connector button (matches DL `buttons-section.js:13` destructive variant). |

Element count: 16 primitive rows.

L4 chips-hide verification on this surface (Discord A&R is in DOM): probed `[data-testid^="discoverable-dropdown-chips-"]` — `peers`/`groups`/`roles` chips containers all have `display: none` + `hidden=true`. `channels` container has `display: flex` because it contains 1 chip (`1506831630923333722`, label-unknown pre-Test-Connection). This confirms the L4 hidden-toggle + CSS override works: empty containers are hidden, non-empty render normally.

## Surface 3 — Discord Constellation edit-mode → Access and Routing tab

Activated by clicking the `Access and Routing` tab; the General panel becomes `hidden`, the A&R panel renders. Three sections: Lifecycle, Runtime Config, Account-scope allowlist, Routing rules.

| Element | Primitive / Pattern | Source | Notes |
|---|---|---|---|
| Tablist (still visible, A&R now selected) | `tablist` + `tab` (DL) | `tabs-section.js` | Tab state flipped: `Access and Routing` `aria-selected=true`. |
| Section: Lifecycle | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | Identical shape to Surface 1's Lifecycle section. |
| Pool idle timeout field-row | `field-row admin-pf-row` + `field-input field-select` + `field-info-icon` (DL) | `fields-section.js` | Identical to Surface 1. |
| Chat-session continuation window field-row | `field-row admin-pf-row` + `field-input field-select` + `field-info-icon` (DL) | `fields-section.js` | Identical to Surface 1. |
| Auto-reply to platform messages field-row | `field-row admin-pf-row cf-auto-relay-row` + `tool-enable-switch` + `field-info-icon` (DL) | `surfaces-section.js:90-101` | Identical to Surface 1. |
| Section: Runtime Config (`editor-section[data-testid=connector-account-runtime-config-section]`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606`; L3-introduced relabel | Discord-specific; renders only when connector type implements `renderRuntimeConfigFields`. |
| Intents fieldset row | `<fieldset.discord-intents-fieldset>` + `<legend>` + `field-info-icon` + three `<label.discord-intent-row><input.checkbox-primary>` | `fields-section.js:27-43` (`checkbox-primary`); `fields-section.js:18-25` (info-icon) | One row by granularity convention; three checkboxes (Message Content, Server Members, Servers) are sub-children. |
| Servers (guild-IDs) field-row | `<div.discord-guilds-row>` + label + `field-info-icon` + `<input.field-input>` (DL) | `fields-section.js:9`; info-icon pattern | NOT wrapped in `.field-row admin-pf-row` — uses a Discord-scoped class; see cross-cutting findings. |
| Presence field-row | `<div.discord-presence-row>` + label + `field-info-icon` + `<input.field-input>` + `<select.field-input.field-select>` | `fields-section.js:9,11` | Same: Discord-scoped wrapper class, two inputs side-by-side. |
| Advanced (kv-table) disclosure | `<details.discord-advanced-kv-disclosure>` + `<summary>Advanced (kv-table)</summary>` + KV table | `mcp-server-editor.js:237` `<details>` pattern + MCP KV table pattern | One row by granularity convention. |
| Section divider `//` | `.section-title::before` | shared CSS | |
| Section: Account-scope allowlist (`editor-section.connector-allowlist-section`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Peers axis | `.connector-account-acl-fieldrow` + label + `.discoverable-dropdown[data-axis=peers]` containing input-row + menu + `chip-list-editor discoverable-dropdown-chips` + status + `.form-hint` | bespoke `discoverable-dropdown` (DEFERRED) + DL `chip-list-editor` (`chip` + `chip-remove` from `status-section.js:73-80`) | One row per axis by granularity. Status message: "Run Test Connection first to populate the bot's discoverable view." Chips container `hidden + display:none` when empty. See deferral D1. |
| Channels axis | (same shape as Peers) | bespoke + DL chip | Chips container `display: flex` because it has 1 chip pre-Test-Connection (label-unknown, `data-unknown=true`, `title="label unknown — try Refresh"`). |
| Servers axis (renamed from Guilds per L3) | (same shape as Peers) | bespoke + DL chip | Empty; chips container hidden. |
| Roles axis | (same shape as Peers) | bespoke + DL chip | Empty; chips container hidden. |
| Section: Routing rules (`editor-section.connector-routing-section`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Default agent field-row | `field-row admin-pf-row connector-routing-default-row` + `field-input field-select` (DL) | `fields-section.js:11` | Three options: None/Cave Man Bot/Pirate Bot. |
| Routing-default hint row | `field-row admin-pf-row` with empty `<label>` + `<small.form-hint>` | DL field-row + form-hint | Hint: "Fall back to first-eligible-alphabetical agent." Empty-label `field-row` used for alignment — see cross-cutting findings (acceptable pattern). |
| Routing-rules table | `<table.connector-routing-table>` with `thead.is-hidden` (no rows yet) | bespoke (DEFERRED — see D2) | Table shell rendered; no `<tr>` rules in this build. |
| `+ Add rule` button | `btn-outlined-primary kv-add-row-btn connector-routing-add-row-btn` (DL button) | `mcp-server-editor.js` KV pattern | Same `+ Add row` convention as Config/Credentials. |

Element count: 18 primitive rows.

## Surface 4 — Stub HAT Account edit-mode → General tab (`#studio/connectors/0a75256c0a8c`)

Sections in DOM: Connection, Credentials, Pairing, Attached agents, Danger Zone. **Stub has NO System-Prompt-Directive section** (Discord-only). **Stub Pairing has a generated code on file** (different status text path than Discord).

| Element | Primitive / Pattern | Source | Notes |
|---|---|---|---|
| Editor header (title `Stub HAT Account` + subtitle `stub · default TTL` + Back/Cancel/Save) | `editor-header` + `h1.editor-title` + subtitle + `.form-actions` | MCP editor convention | Identical shape to Surface 2. |
| Tablist (`General` / `Access and Routing`) | `tablist` + `tab` (DL) | `tabs-section.js` | Identical to Surface 2. |
| Section: Connection | `editor-section` + `section-title` | `mcp-server-editor.js:441-442` | |
| Name field-row | `field-row admin-pf-row` + `field-input admin-pf-input` | `fields-section.js:9` | Value: `Stub HAT Account`. |
| Type field-row (read-only) | `field-row admin-pf-row` + `field-input admin-pf-input` `readonly` | `fields-section.js:9` | Read-only `stub`. |
| Config field-row (KV adder, empty) | `field-row admin-pf-row connector-account-config-wrap` + `.connector-account-config` + `<table.connector-account-config-table>` (empty tbody) + `+ Add row` | MCP KV pattern | Empty table with `thead.is-hidden` (hidden until rows exist). |
| Test-connection footer row | `field-row admin-pf-row connector-test-row` + button + LED + message | `connector-test-row` pattern (same as Surface 2) | "Not tested" idle state. |
| Section: Credentials | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Credentials KV table + adder | `<table.connector-account-secrets-table>` (empty tbody, hidden thead) + `+ Add row` | MCP KV pattern | Same shape as Config. |
| Section: Pairing (`editor-section.connector-pairing-section`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` shape | |
| Pairing Status field-row | `field-row admin-pf-row` + `btn-outlined-primary connector-pairing-generate-btn` ("Regenerate code") + `.connector-pairing-status` | DL button + status text | Status: "Code on file · issued 2026-05-19T15:25:47.360739+00:00". Different copy from Surface 2 (existing-code path). |
| Pairing Code reveal row (hidden) | (same as Surface 2) | DL field-input + copy button | `hidden=""` initially. |
| Section: Attached agents | `editor-section.connector-attached-agents-section` + `section-title` + `<em.form-hint>No agents attached.</em>` | DL `form-hint` for empty state | **Empty state** uses `<em.form-hint>` text — no `.empty-state` primitive (`status-section.js:84-89`). See cross-cutting + D3. |
| Section: Danger Zone | `editor-section.danger-zone` + `section-title.danger-zone-title` | `mcp-server-editor.js:619-620` | Single `btn-muted-destructive` Delete Connector. |
| Section divider `//` between sections | `.section-title::before` | shared CSS | |

Element count: 14 primitive rows.

## Surface 5 — Stub HAT Account edit-mode → Access and Routing tab

**Stub A&R Runtime-Config-absence VERIFIED**: A&R panel sections are exactly `Lifecycle`, `Account-scope allowlist`, `Routing rules` — NO `Runtime Config` section (confirmed via DOM probe: `arPanel.querySelector('[data-testid=connector-account-runtime-config-section]')` returns `null`). The Stub connector type doesn't implement `renderRuntimeConfigFields`, so the section is simply not appended; no half-rendered placeholder, no empty section-title — the missing-section is visually clean.

Stub allowlist uses plain `chip-list-editor` (DL `chip` + `chip-remove` + `.chip-list-input`) — NO `.discoverable-dropdown` wrapper (Stub has no discoverable API). This is a different code path than Surface 3 but uses the same DL chip primitive.

| Element | Primitive / Pattern | Source | Notes |
|---|---|---|---|
| Tablist (A&R selected) | `tablist` + `tab` (DL) | `tabs-section.js` | |
| Section: Lifecycle | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Pool idle timeout field-row | `field-row admin-pf-row` + `field-input field-select` + `field-info-icon` (DL) | `fields-section.js` | Identical to Surfaces 1/3. |
| Chat-session continuation window field-row | `field-row admin-pf-row` + `field-input field-select` + `field-info-icon` (DL) | `fields-section.js` | Identical. |
| Auto-reply to platform messages field-row | `field-row admin-pf-row cf-auto-relay-row` + `tool-enable-switch` + `field-info-icon` (DL) | `surfaces-section.js:90-101` | Identical. |
| Section divider `//` | `.section-title::before` | shared CSS | |
| Section: Account-scope allowlist (`editor-section.connector-allowlist-section`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Peers axis (chiplist) | `.connector-account-acl-fieldrow` + label + `chip-list-editor.connector-allowlist-chiplist` containing `<span.chip>×</span>` rows + `.chip-list-input` + `<small.form-hint>` | DL `chip` + `chip-remove` (`status-section.js:73-80`); DL `field-input` (input variant) | Two chips: `peer-1`, `peer-2`. **No discoverable-dropdown wrapper** — Stub uses plain typed-input chip-list. |
| Channels axis (chiplist) | (same shape) | DL chip + input | Two chips: `chanel-1`, `channel-2` (sic — first label has typo from seed data, unrelated to UX). |
| Guilds axis (chiplist) | (same shape) | DL chip + input | Empty (no chips). Hint: "Discord-flavored; ignored by other platforms." |
| Roles axis (chiplist) | (same shape) | DL chip + input | Empty. Hint: "Discord-flavored." |
| Section: Routing rules (`editor-section.connector-routing-section`) | `editor-section` + `section-title` | `mcp-server-editor.js:605-606` | |
| Default agent field-row | `field-row admin-pf-row connector-routing-default-row` + `field-input field-select` (DL) | `fields-section.js:11` | Sonnet option shown as `disabled` "(not attached)" — clear affordance. |
| Routing-default hint row | (empty-label `field-row` + `<small.form-hint>`) | DL field-row + form-hint | Same pattern as Surface 3. |
| Routing-rules table (populated) | `<table.connector-routing-table>` with visible `thead` + two `<tr.connector-routing-row>` | bespoke (D2) | Header columns: Reorder / Scope / Match / Agent / Actions. |
| Routing-rule row (one row, primitive enumeration) | drag handle + `field-select` scope + `chip-list-editor.connector-routing-match-chiplist` (chips + input) + `field-select` agent + remove button | DL chip + DL select + bespoke drag handle | One row per rule; chip-list-editor in match-cell is the same DL primitive as Stub allowlist. Drag handle is bespoke (see D2). |
| `+ Add rule` button | `btn-outlined-primary kv-add-row-btn connector-routing-add-row-btn` | DL button + MCP KV pattern | |

Element count: 16 primitive rows.

## Surface 6 — Agent Connectors tab (`#studio/agents/Cave%20Man%20Bot/connectors`)

The agent editor's Connectors tab. Cave Man Bot has BOTH Discord Constellation + Stub HAT Account attached, exercising both code paths (Discord = discoverable-dropdown chips + checkboxlist; Stub = checkboxlist). Per-connector tile uses the **MCP-source-tile pattern** (`mcp-source-tile`) — explicit shape reuse from the MCP sources area.

| Element | Primitive / Pattern | Source | Notes |
|---|---|---|---|
| Agent editor header (title `Cave Man Bot` + Back / Cancel / Save) | `editor-header` + `h1.editor-title` + `.form-actions` | MCP editor convention | (Outside tab scope; shared chrome.) |
| Agent tablist (5 tabs: General / Knowledge / MCPs / Connectors / Built-in Tools) | `tablist` + `tab` (DL) | `tabs-section.js` | Connectors tab `aria-selected=true`. |
| Connectors list container | `.mcp-sources-list.connector-accounts-list` (`data-testid="connector-accounts-list"`) | MCP-sources-area shape reused | Linear list of `.mcp-source-tile` rows; NO `entity-tile-grid` (this is the MCP sources convention, not the entity-tile-grid convention). |
| Discord Constellation tile row | `.mcp-source-tile.connector-account-tile` containing `.mcp-source-tile-row1` (toggle + name + protocol-badge) + `.mcp-source-tile-tools` ACL section | MCP-sources-area pattern | `aria-expanded=false` on the tile; toggle is `tool-toggle.connector-account-toggle` + `tool-switch` (the `.tool-enable-switch` two-element variant from MCP sources). Protocol badge: `.mcp-source-tile-protocol.connector-account-type-badge` reads `discord`. |
| Discord — Peers axis disclosure | `.connector-acl-axis` + `button.mcp-source-tile-expand-btn.connector-acl-axis-toggle` with `aria-expanded=false` + `.connector-acl-axis-title` + `.mcp-source-tile-tool-count` + `.mcp-source-tile-chevron▸` | MCP-sources-area expand-button shape | One axis = one row by granularity. Body hidden by default; body contains `chip-list-editor.connector-acl-chiplist` wrapping `.discoverable-dropdown` (chips path). Count text: "All peers (no restriction)". |
| Discord — Channels axis disclosure | (same shape) | MCP-sources-area expand-button | Body contains `.connector-acl-checkboxlist` (checkbox-list path, NOT chips path) — F4 L4's per-axis containment: known-channels rendered as `checkbox-primary` rows, plus optional `.form-hint.connector-acl-checkbox-warn` warning paragraph (hidden when no warning). Count: "All channels (inheriting)". |
| Stub HAT Account tile row | (same `.mcp-source-tile.connector-account-tile` shape) | MCP-sources-area pattern | Protocol badge `stub`. |
| Stub — Peers axis disclosure | (same shape) | MCP-sources-area expand-button | Body contains `.connector-acl-checkboxlist` (Stub uses checkbox-list path for known peers). Count: "All peers (inheriting)". |
| Stub — Channels axis disclosure | (same shape) | MCP-sources-area expand-button | Body contains `.connector-acl-checkboxlist`. Count: "All channels (inheriting)". |

Element count: 9 primitive rows (header + tablist + container + 2 tiles + 4 axis disclosures).

L4 axis-containment side effect on this surface: each axis renders only its own primitive — chips path doesn't bleed into checkbox path and vice versa. Verified via DOM probe: each `.connector-acl-axis-body` contains exactly one of `.connector-acl-chiplist` or `.connector-acl-checkboxlist`, never both.

## Cross-cutting findings

- **`editor-section` + `section-title` is the universal section primitive** across all 6 surfaces. The `::before { content: "//" }` decoration on `.section-title` is the universal visual divider — no surface uses a literal `//` DOM node. Confirmed via computed-style probe.
- **`field-row admin-pf-row` is the universal row primitive** for label+input pairs across Surfaces 1-5. Discord A&R Runtime Config introduces TWO Discord-scoped wrapper classes (`.discord-guilds-row`, `.discord-presence-row`) that bypass `field-row admin-pf-row` — these are content rows inside `<fieldset>`/section bodies, not standalone form rows, so the divergence is acceptable. **Not a deferral**; documenting for awareness.
- **`field-info-icon` info-icon pattern is consistent** across all surfaces — every info-icon has `title=` + `aria-describedby=` + a sibling `<span.visually-hidden>` help-text element. This is the MCP-editor info-icon convention (`mcp-server-editor.js:792`) faithfully applied throughout.
- **Test-connection treatment is consistent** between Discord (Surface 2) and Stub (Surface 4): both use `field-row admin-pf-row connector-test-row` with button + LED + message in the same row order. This IS the Discord-flavored analog of MCP's `mcp-test-row` (`mcp-server-editor.js:473`), differing only in class name.
- **KV-table adder pattern is consistent** across Config (all surfaces), Credentials (Surfaces 2/4), and Routing rules (Surfaces 3/5): all use `btn-outlined-primary kv-add-row-btn` + a section-scoped class. `+ Add row` / `+ Add rule` copy varies appropriately. Empty tables hide their `thead` via `.is-hidden`.
- **Chip primitive is universally `<span class="chip">…<button class="chip-remove">×</button></span>`** — same shape in Discord A&R discoverable-dropdown chips (Surface 3), Stub allowlist chiplist (Surface 5), Stub routing match cell (Surface 5), and Discord Attached-agents channels cell (Surface 2). Same primitive applied at five different sites; high consistency.
- **`<details>` collapsibles use single-class scoping** in two places: `connector-directive-disclosure` (Surface 2) and `discord-advanced-kv-disclosure` (Surface 3). Both match the MCP `<details class="mcp-tool-item">` convention (`mcp-server-editor.js:237`) — one class per disclosure, no nested wrapper. Consistent.
- **Per-agent overlay (Surface 6) reuses the MCP-sources-area tile shape** (`mcp-source-tile`, `mcp-source-tile-expand-btn`, `mcp-source-tile-chevron`, `tool-switch`) — this is shape-borrowing from a sibling area rather than from the DL page proper. The DL page does NOT document `mcp-source-tile` as a primitive; this is an undocumented convention worth surfacing (see D4).
- **Empty-state handling diverges**: Surface 4 Attached-agents uses `<em.form-hint>No agents attached.</em>` rather than the DL `.empty-state` primitive (`status-section.js:84-89`). Inconsistent with the DL catalog. See D3.
- **Hint-text alignment uses an empty-label `field-row`** in Routing rules sections (Surfaces 3, 5): `<div class="field-row admin-pf-row"><label></label><small class="form-hint">…</small></div>`. Functional but visually unusual; documenting as an accepted pattern (not a deferral — works within the existing primitive).
- **L4 cycle-1 positive side effect (empty chips container hidden)** verified on Surface 3: `peers`, `groups`, `roles` chips containers all have `display: none` + `hidden=true` because they have zero chips in the cold-pool state. Only `channels` (one label-unknown chip) renders. The CSS override + JS `hidden`-toggle work as designed.
- **L4 per-axis containment** verified on Surface 6: each axis body contains exactly one of chips-path or checkbox-path; no cross-bleed.

## Deferral list

> The following elements lack a canonical primitive in either the Design Language page (`#admin/design-language`) or the MCP editor (`#studio/mcp-sources/...`). They become future-UX-mission scope — NOT F5 work — per the operator's NO-new-UI-components constraint.

- **D1 — `.discoverable-dropdown` composite** (Surface 3, Surface 6 Discord-Peers): a wrapper that combines an autocomplete combobox (input + role=listbox menu + refresh button + status `aria-live` region) on top of the DL `chip-list-editor` (chips). The combobox+chiplist composition has no analog in DL or MCP editor. **Reason**: MCP editor uses native `<select>` for finite enumerations; DL has `field-input` and chips separately but no documented "discoverable-dropdown-with-chips" composite. **Follow-up**: a future UX mission could add `.discoverable-dropdown` to the DL catalog as a composite primitive (input+menu+chiplist+status), with documented states (cold-pool/loading/loaded/error). Used at four sites currently (peers/channels/groups/roles on Discord A&R + Discord-Peers on per-agent overlay) — n≥2 codification threshold met per F4 debrief recommendation #4.

- **D2 — `.connector-routing-table` rule-row drag-handle** (Surface 3, Surface 5): the routing-rules table uses a bespoke `<table>` shell with a custom drag-handle column (`.connector-routing-drag-handle` with a 6-dot SVG, `draggable=true`, `role=button`). The DL page documents tables only implicitly via `connector-attached-agents-table`; MCP editor uses tables minimally (KV tables). **Reason**: no canonical drag-handle primitive in either reference; no canonical "data-table-with-reorder" primitive. **Follow-up**: a future UX mission could add a `.data-table` + `.drag-handle` primitive pair to DL, with reorder affordance and keyboard-accessible reordering documented. (Note: tests in this build likely depend on the drag-handle's structure; codification should preserve test anchors.)

- **D3 — Empty-state copy NOT using `.empty-state` primitive** (Surface 4 Attached agents): "No agents attached." is rendered as `<em.form-hint>` rather than `<div class="empty-state">` (`status-section.js:84-89`). **Reason**: existing primitive available but not adopted at this site. **Follow-up**: a future UX-consistency mission could swap to `.empty-state` for visual consistency. NOT folded inline because (a) the swap touches markup in `connector-account-editor.js` rather than a stray inline-style — risks regressing tests — and (b) Stub may grow attached agents during F6 HAT, making the inconsistency moot.

- **D4 — `mcp-source-tile` family** (Surface 6 + the MCP sources area itself): `.mcp-source-tile`, `.mcp-source-tile-row1`, `.mcp-source-tile-toggle`, `.mcp-source-tile-tools`, `.mcp-source-tile-expand-btn`, `.mcp-source-tile-chevron`, `.mcp-source-tile-tool-count`, `.tool-switch` are used both by the MCP-sources area AND the connector per-agent overlay (Surface 6) but are NOT documented in the DL page. **Reason**: undocumented but widely-used tile-row primitive (≥ n=2 use sites). **Follow-up**: a future UX mission should add the `mcp-source-tile` family to the DL catalog (likely as a new section, e.g., "expandable-tile") and document the toggle+name+badge+expand-button composition.

- **D5 — `connector-attached-agents-table`** (Surface 2 only): bespoke `<table>` for the inverse-listing of agents attached to the connector. Columns are connector-specific (Agent/Users/Channels). **Reason**: no canonical "small-data-table" primitive in DL. **Follow-up**: same as D2 — a generic `.data-table` primitive would absorb both this and the routing-rules table.

## Inline-fix log

**No inline fixes needed.** All elements across the six surfaces either map cleanly to existing Design Language primitives, map cleanly to MCP-editor patterns (the canonical working reference), or are deferred to future-UX-mission scope (D1-D5 above). The post-L4 state is internally consistent — no stray inline-styles contradicting tokens, no missing `aria-label`s on icon buttons (verified: copy buttons, refresh buttons, chip-remove buttons, drag handles, delete-rule buttons all have either `aria-label=` or `data-testid` + nearby text), no wrong-class usage observed during the sweep.

The deferral list (D1-D5) is the escape valve for the cross-cutting gaps that ARE present — those are codification opportunities (add primitives to the DL catalog), not inline cleanups. The L5 abort-threshold (~25 LOC cumulative) was never approached: zero LOC of inline changes were made.
