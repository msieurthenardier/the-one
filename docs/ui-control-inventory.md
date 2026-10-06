# UI control inventory

The app-wide classification of every control kind: which ones the `App.ui` control
library defines, and which are not yet defined. (M25 F1 L6, DD11.) The library is
documented in `the_one/agents.md` ("Control library (`App.ui`)"); its living reference
is the dev-mode `#settings/design-language` page, one `[data-ui-demo="<factory>"]` root per
factory.

## The guard and how to update this file

`tests/test_ui_control_inventory.py` (unit tier) reads every `App.ui.<name> = function`
export in `the_one/interfaces/web/static/js/ui/*.js` (`App.ui.util.*` excluded) and
checks both directions against this file:

- every factory appears here as `App.ui.<name>` (a missing row fails);
- every `App.ui.<name>` cited here is a real factory (a stale citation fails).

`tests/browser/test_ui_reference_page.py` checks that each factory also has a demo root
on the reference page.

When you add a factory: write its demo section, add or change its row here, and add its
contract tests (see "Adding a factory" in `agents.md`). When a control migrates to the
library, change its status from `not yet defined` to `library: App.ui.<factory>`. A row
is either `library: App.ui.<factory>` or `not yet defined` with the owning surface and the
expected migration. "Flight 2/3" means Mission 25's shell and Library flights; "next
mission" means the editor-internals mission.

Paths below are relative to `the_one/interfaces/web/static/`.

## Buttons

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| Button, variants primary / secondary / ghost / danger, sizes sm / lg / xl, icon, icon-only | `js/ui/button.js`; CSS classes `.btn-filled-primary`, `.btn-outlined-primary`, `.btn-ghost`, `.btn-muted-destructive` in `css/components.css` | library: App.ui.button | Flights 2-3 (shell, Library) call the factory; editors keep hand-built `<button class="btn-...">` until the next mission | Hand-built buttons exist in every editor (`_btn` copies, HTML strings in `provider-editor.js`, `tools-editor.js`) |
| Compact row actions (`.area-studio .tool-actions .btn-outlined-primary`) | CSS-only override in `css/studio.css` | not yet defined | Studio tools tab, next mission | Documented exception to the standard button size |
| Info-icon button (`.field-info-icon`) | HTML strings in `js/areas/admin/tools-form-helpers.js`, `provider-editor.js`, `tools-editor.js`; `mcp-server-editor.js` (`renderKvTable`) | not yet defined | Admin and Studio editors, next mission | Tooltip carried by `title` plus `aria-describedby`; no keyboard-visible popover |
| Copy buttons (sign-in code, pairing code, API token, markdown code block) | `provider-editor.js`, `connector-editor.js`, `self-configuration-tab.js`, `markdown.js` (`.markdown-copy-btn`) | not yet defined | Each owning editor, next mission | None recorded |
| Pull button, refresh button (Ollama model lifecycle) | HTML string in `js/areas/admin/provider-models.js` | not yet defined | Admin providers, next mission | Hand-built; see model picker below |

## Text entry

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| Text input (`.field-input`) | `js/ui/field.js`; hand-built in every editor | library: App.ui.textInput | Flights 2-3 chrome; editors next mission | Per-editor `_el`/`_btn`/`_fieldGroup` copies in `knowledge-section.js`, `knowledge-tab.js`, `connector-editor.js` (deferred) |
| Textarea (`.field-input.field-textarea`) | `js/ui/field.js` | library: App.ui.textarea | As above | As above |
| Select (`.field-input.field-select`) | `js/ui/field.js`; hand-built `<select>` in `studio.js`, `provider-editor.js`, `general-tab.js` | library: App.ui.select | As above | As above |
| Field group (label + control + hint + error) | `js/ui/field.js`; `fieldGroup()`/`_fieldGroup()` copies in editors and `tools-form-helpers.js` | library: App.ui.field | As above | Label-association is wired by hand at every non-library site (guarded by `tests/test_ui_guards.py`) |
| Chat composer (`data-testid="chat-input"`, send, attach) | HTML string in `js/areas/chat.js` | not yet defined | Chat surface, next mission | Single-line input labelled by `aria-label` |
| Provider model picker (selection of the model list) | `js/areas/admin/provider-models.js` (HTML string, `.admin-pf-models-*`) | not yet defined | Admin providers, next mission | A selection listbox is a separate Flight 4 control (DD14) |
| Pull-model control (select + Pull button + streaming progress) | `js/areas/admin/provider-models.js` (`.admin-pf-pull-*`) | not yet defined | Admin providers, next mission | None recorded |

## Choices and toggles

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| Checkbox (`.checkbox-primary`) | `js/ui/choice.js`; hand-built in `js/areas/studio/tools-tab.js`, `knowledge-tab.js`, `mcps-tab.js`, provider and tool editors | library: App.ui.checkbox | Flights 2-3 chrome; editors next mission | Squawk 0094: the KB attach checkbox in `knowledge-tab.js` is not reachable by role |
| Toggle, library (`input[role=switch]`) | `js/ui/choice.js` | library: App.ui.toggle | Replaces both legacy toggles as their surfaces migrate | None |
| Legacy toggle 1: iOS switch (`.tool-enable-switch` + `-track`) | HTML strings and DOM in `tools-grid.js`, `tools-editor.js`, `provider-editor.js`, `knowledge-settings-page.js`, `connector-editor.js`, `self-configuration-tab.js`; CSS in `css/admin.css` | not yet defined | Admin and Studio editors, next mission | Two DOM templates with different anchoring (`--corner` modifier) |
| Legacy toggle 2: studio pill (`.tool-toggle` hidden input + `.tool-switch`) | `js/areas/studio/tools-tab.js`; `css/studio.css` | not yet defined | Studio tools tab, next mission | `.area-studio .tool-toggle { display: none }` (`css/studio.css:64`) removes the native input from the keyboard order |
| Radio group (theme: Light / Dark / Auto) | `App.theme.renderToggle` in `js/theme.js` | not yet defined | Settings surface, Flight 2 | None recorded |

## Feedback and status

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| Badge (`.badge`, `.badge--<kind>`) | `js/ui/feedback.js`; per-area `.admin-provider-badge--*` (now only the Design language status demo), chat badges | library: App.ui.badge | Per-area badge classes migrate with their surfaces (Flights 2-3); the Providers table's Type column uses App.ui.badge (M25 F3 L5b) | Chat-area approved/dismissed pair is outside the contrast gate |
| Empty state (`.empty-state`, `.empty-canvas`) | `js/ui/feedback.js`; hand-built in `provider-models.js`, `mcps-tab.js`, `tools-grid.js` | library: App.ui.emptyState | Flights 2-3; the zero-providers state is App.ui.emptyState since M25 F3 L5b (`providers-empty`) | Hand-built sites keep their own markup |
| Flash message (`App.showFlash`) | `showFlash()` in `js/app.js` | not yet defined | Shell, Flight 2 | None recorded |
| Indicator LED (`.indicator-led--*`) and status lines (`.self-configuration-status`) | `provider-editor.js`, `provider-models.js`, `self-configuration-tab.js` | not yet defined | Their owning editors, next mission | LED is `aria-hidden`; text carries the meaning |
| Telemetry overlay | `js/areas/chat/telemetry-overlay.js` | not yet defined | Chat surface, next mission | None recorded |
| Thinking indicator, trace shell | `js/areas/chat/thinking-indicator.js`, `trace-shell.js` | not yet defined | Chat surface, next mission | None recorded |

## Lists, navigation and surfaces

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| List pane. Options: `title`, `count` ("{shown} of {total}"), `intro`, `actions`, `filter` ({label, placeholder, predicate, testid}), `emptyText` (a string, or a function of the trimmed query, M25 F3 L3), `items` or `groups` (group: {id (optional, unique, M25 F3 L4a), label, emptyText, items}; item: {id, label, meta, nameSuffix, href or onSelect, badges, count, icon, lead (M25 F3 L3), testid}), `selectedId` (the selected row carries `aria-current="page"` on a link row, `"true"` on a button row), `density`, `rowStyle` (`agents` / `library`), `testid`. `nameSuffix` is a separate text run: callers pass a leading separator and, when meta follows, a trailing one (`", Claude Max,"`). Methods: `setItems` (keeps the filter query, the body's scroll position and focus), `setSelected`, `focusSelected`, `scrollToSelected`, `scrollToGroup` (M25 F3 L4a), `getItems`, `destroy` | `js/ui/list-pane.js` | library: App.ui.listPane | Hosts the Agents list (M25 F3 L3: provider-dot `lead`, `No agents match "{q}".`) and the grouped Library list (M25 F3 L4a: Knowledge bases / MCP servers / Connectors, `rowStyle: 'library'`, a section root scrolls its group into view) in the aside | None |
| List row (`.list-item`, chat history) | `js/areas/chat/history-buckets.js`, `css/components.css` | not yet defined | Flight 4 (the Chats list), replaced by the list pane; Flight 3 moved Agents and Library onto the list pane but not the chat history | Row delete is a hand-built button |
| Entity tile and tile grid (`.entity-tile`) | `tools-grid.js`, `css/components.css` | not yet defined | Flights 2-3 retired the tiles (the agents grid in M25 F3 L3, the three Library grids in L4a, the providers grid in L5b, a table that L7 turned back into tiles); the Built-in tools tiles stay as an accepted variation (L5b): the tile is no longer a click target, its tool name is the item link; the Settings › Providers tiles (L7, `providers-list.js`, `.provider-tile` on the `.entity-tile` base, grid `.provider-tile-grid`) follow the same model | The tool name runs under the corner badge when long |
| Item header breadcrumb (`.editor-breadcrumb`; its last segment is the root link `editor-breadcrumb-link`) | `js/areas/studio/agent-editor.js`, `mcp-server-editor.js`, `connector-editor.js`, `knowledge-section.js` (`_breadcrumb()`), `js/areas/admin/provider-editor.js`, `tools-editor.js` (DOM APIs in each); routed by delegated listeners in `js/areas/studio.js` and `js/areas/admin.js`; `css/components.css` | not yet defined | Every Agents, Library and Settings item header (M25 F3 L3, L4b, L5b): the visible way to close an item since the editors' Back controls were retired; a shared item-header factory is next-mission editor work | Built per editor (string-built editors insert it after setting their markup); no factory. The root link is underlined at rest (not colour alone, WCAG 1.4.1) |
| Unsaved-changes caption (`.editor-unsaved`, `role="status"`) | the same six editors' `.form-actions`; `css/components.css` | not yet defined | Every item header (M25 F3 L3, L4b, L5b; A15, a DD14 checkpoint question) | One stable span per mount whose text each editor toggles from its own dirty report; no factory |
| Data table (Providers: Name, Type, Used by) | none (retired) | not yet defined | Retired in M25 F3 L7: Settings › Providers was a DOM-built table in L5b (reference spec 8.2) and went back to tiles at the Flight 3 operator checkpoint, to match Built-in tools; no consumer remains, and a library table is next-mission work | The row is kept so the history stays visible; `providers-table.js` is now `providers-list.js` (tiles) and the `.providers-table` CSS is deleted |
| Category tile (`.tools-category-tile`, `.mcp-source-tile`) | `js/areas/studio/tools-tab.js`, `mcps-tab.js` | not yet defined | Studio tabs, next mission | Master toggle is the legacy pill |
| Grouped nav of links (Settings nav) | `js/ui/nav-groups.js`; mounted as the Settings nav by `js/areas/admin.js` (testid `settings-nav`) | library: App.ui.navGroups | The Settings nav since M25 F3 L5a (DD6): it replaced the section nav (`App.layout.renderSectionNav`, a `<button>` list with roving tabindex), whose module `areas/layout/section-nav.js` and CSS were deleted with their last caller | None |
| Rail (destination links) | `js/ui/rail.js`; mounted in `#app-rail` by `js/app.js` | library: App.ui.rail | Replaced the interim top bar and `.app-picker-button` (Flight 2 L6) | Jump-to control is Flight 4 |
| Tabs (W3C tablist) | `App.tabs` in `js/tabs.js`; used by `agent-editor.js`, `tools-grid.js` | not yet defined | Studio, next mission | None recorded |
| Chip and chip list (`.chip-list-editor`, queued-message chip) | `js/areas/admin/tools-form-helpers.js`, `js/areas/chat.js` (`.pending-queued-chip`) | not yet defined | Tool editors, next mission | `.chip-remove` buttons are hand-built |
| Key-value table (`renderKvTable`, `.admin-kv-row`) | `mcp-server-editor.js`, `knowledge-settings-page.js` | not yet defined | MCP editor, next mission | Sensitive-value rows carry an info-icon |
| Message bubble controls (copy, attribution, peer labels) | `js/areas/chat/message-bubble.js` | not yet defined | Chat surface, next mission | None recorded |

## Menus and dialogs

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| Menu (APG menu button) | `js/ui/menu.js` | library: App.ui.menu | First production use: the Library list's Add menu (M25 F3 L4a; `align: 'end'`, destroyed with the list pane) | No edge flipping; popup always opens downward |
| KB item menu (`buildItemMenu`) | `js/areas/studio/knowledge-section.js` | not yet defined | Superseded by the library menu; migrates with the KB editor internals, next mission | Hand-built popup, not the APG pattern |
| Modal (native `<dialog>`, DD8) | `js/ui/modal.js` | library: App.ui.modal | Consumed from Flight 2 | None |
| Dialog (`App.confirmDialog`) | `js/dialog.js` | library: App.ui.modal | Library-backed adapter over `App.ui.modal`; guard sites move to `App.nav` in Flight 2 L5 | 11 guard call sites; keeps a single-open policy until then |
| Two-step confirm (`App.confirmDelete`) | `js/confirm.js` | not yet defined | Shell, Flight 2 or later | 13 call sites; feedback-only `.confirm-lapsed` cue |
