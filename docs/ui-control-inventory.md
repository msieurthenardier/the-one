# UI control inventory

The app-wide classification of every control kind: which ones the `App.ui` control
library defines, and which are not yet defined. (M25 F1 L6, DD11.) The library is
documented in `the_one/agents.md` ("Control library (`App.ui`)"); its living reference
is the dev-mode `#admin/design-language` page, one `[data-ui-demo="<factory>"]` root per
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
| Badge (`.badge`, `.badge--<kind>`) | `js/ui/feedback.js`; per-area `.admin-provider-badge--*`, chat badges | library: App.ui.badge | Per-area badge classes migrate with their surfaces (Flights 2-3) | Chat-area approved/dismissed pair is outside the contrast gate |
| Empty state (`.empty-state`, `.empty-canvas`) | `js/ui/feedback.js`; hand-built in `providers-grid.js`, `provider-models.js`, `mcps-tab.js`, `tools-grid.js` | library: App.ui.emptyState | Flights 2-3 | Hand-built sites keep their own markup |
| Flash message (`App.showFlash`) | `showFlash()` in `js/app.js` | not yet defined | Shell, Flight 2 | None recorded |
| Indicator LED (`.indicator-led--*`) and status lines (`.self-configuration-status`) | `provider-editor.js`, `provider-models.js`, `self-configuration-tab.js` | not yet defined | Their owning editors, next mission | LED is `aria-hidden`; text carries the meaning |
| Telemetry overlay | `js/areas/chat/telemetry-overlay.js` | not yet defined | Chat surface, next mission | None recorded |
| Thinking indicator, trace shell | `js/areas/chat/thinking-indicator.js`, `trace-shell.js` | not yet defined | Chat surface, next mission | None recorded |

## Lists, navigation and surfaces

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| List pane (groups, selection, filter, density) | `js/ui/list-pane.js` | library: App.ui.listPane | Flight 3 (Library) | None |
| List row (`.list-item`, chat history) | `js/areas/chat/history-buckets.js`, `css/components.css` | not yet defined | Flight 3 (Library), replaced by the list pane | Row delete is a hand-built button |
| Entity tile and tile grid (`.entity-tile`) | `providers-grid.js`, `knowledge-section.js`, `css/components.css` | not yet defined | Flights 2-3 retire tiles | Tile grid carries `role=listbox` in providers |
| Category tile (`.tools-category-tile`, `.mcp-source-tile`) | `js/areas/studio/tools-tab.js`, `mcps-tab.js` | not yet defined | Studio tabs, next mission | Master toggle is the legacy pill |
| Section nav (`.section-nav-item`) | `App.layout.renderSectionNav` in `js/areas/layout/section-nav.js` | not yet defined | Shell, Flight 2 | None recorded |
| App picker (top bar) | `js/app.js` (`.app-picker-button`) | not yet defined | Shell, Flight 2 | None recorded |
| Tabs (W3C tablist) | `App.tabs` in `js/tabs.js`; used by `agent-editor.js`, `tools-grid.js` | not yet defined | Studio, next mission | None recorded |
| Chip and chip list (`.chip-list-editor`, queued-message chip) | `js/areas/admin/tools-form-helpers.js`, `js/areas/chat.js` (`.pending-queued-chip`) | not yet defined | Tool editors, next mission | `.chip-remove` buttons are hand-built |
| Key-value table (`renderKvTable`, `.admin-kv-row`) | `mcp-server-editor.js`, `knowledge-settings-page.js` | not yet defined | MCP editor, next mission | Sensitive-value rows carry an info-icon |
| Message bubble controls (copy, attribution, peer labels) | `js/areas/chat/message-bubble.js` | not yet defined | Chat surface, next mission | None recorded |

## Menus and dialogs

| Control | Built today | Status | Owner / migration | Debt |
|---|---|---|---|---|
| Menu (APG menu button) | `js/ui/menu.js` | library: App.ui.menu | Consumed from Flight 2 | No edge flipping; popup always opens downward |
| KB item menu (`buildItemMenu`) | `js/areas/studio/knowledge-section.js` | not yet defined | Superseded by the library menu; migrates with the KB editor internals, next mission | Hand-built popup, not the APG pattern |
| Dialog (`App.confirmDialog`) | `js/dialog.js` | not yet defined | Moves to the DD8 dialog rule in Flight 2 | 12 call sites; the reference page's modal section still demonstrates it |
| Two-step confirm (`App.confirmDelete`) | `js/confirm.js` | not yet defined | Shell, Flight 2 or later | 13 call sites; feedback-only `.confirm-lapsed` cue |
