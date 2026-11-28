# HAT feature: narrow tabs menu and header actions menu

**Status**: completed
**Flight**: [Usable at the smallest window](../flight.md)
**Raised in**: HAT step S5 (`uat-and-alignment`), 2026-11-27, promoted through the fix-vs-feature gate (new controls, so a scoped design review before implementation).

## Objective
Below a 768px-wide viewport, a tabbed page shows one menu button naming the current tab instead of a tab strip that wraps and scrolls sideways, and an editor header's secondary actions (the agent editor's Chat) move into a "More actions" menu beside Cancel and Save; at 768px and wider both are unchanged.

## Operator decisions (2026-11-27)
- **Tabs:** option "Menu with current tab": the strip becomes one button showing the current tab's name and a chevron (e.g. "Rules and notes ▾"); it opens a list of every tab with the current one marked; choosing one switches to it.
- **Header actions:** option "Into a ⋯ menu": a "⋯" More actions button beside Cancel and Save holds Chat (and any other secondary header action on other pages); Cancel and Save stay visible.
- Observed: at about 750 CSS px wide the agent editor's six tabs wrap ("Rules and notes" on three lines) and the strip scrolls sideways with Self-configuration cut off; Chat, Cancel and Save take most of the header.

## Acceptance Criteria
- [x] **F1 Tabs factory.** The control library's tabs factory (`js/ui/tabs.js`, `App.ui.tabs`; verify) renders, below 768px, a single menu button in place of the tablist: its label is the current tab's label plus a chevron icon; it opens a menu (reusing `App.ui.menu`) listing every tab in order with the current one marked (`menuitemradio` + `aria-checked`, or the library's equivalent); choosing an item activates that tab exactly as clicking it would (same events, same routing, same leave-guard behaviour). The tabpanel keeps its accessible name. Keyboard: Enter/Space/ArrowDown open the menu, arrows move, Enter chooses, Escape closes and returns focus to the button. At 768px and wider the tablist renders and behaves exactly as today. Contract tests cover both modes in Chromium and WebKit; the inventory row and test ids are registered.
- [x] **F2 Header actions.** The editor shell's header (`App.ui.editorShell`, `js/ui/editor.js`; verify) moves its secondary actions (the `extra` actions, e.g. the agent editor's Chat) into a "More actions" menu button (icon `more-horizontal` or the library's ⋯ icon, `aria-label` "More actions") below 768px; Cancel and Save (and Test, if the design review decides it is primary) stay as buttons. Choosing a menu item runs the same handler as the button. At 768px and wider the header is unchanged.
- [x] **F3 Every tabbed page and editor.** Every page that uses the tabs factory or the editor shell gets the behaviour (agent editor, and any Library or Settings editor or tabbed page the design review finds), verified at 624×321 with nothing scrolling sideways in the header or tab area.
- [x] **F4 Records.** `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md` (control library), the app guide (how to switch tabs and find Chat in a small window), and `tests/test_gleepglorp_guide.py` passes.
- [x] **F5 Gates.** Static guards; the contracts lanes holding the tabs, menu and editor tests (with `THE_ONE_REQUIRE_WEBKIT=1`); `layout`; `agent-tabs`; `agents`; `library`; `settings`; `settings-tools`; the unit tier if Python changes.

## Design review outcome (Developer, 2026-11-27: approve with changes) and FD calls
- **Mode switch in JS, not dual CSS render**: the narrow menu is built only in narrow mode; at 768px and wider the DOM is unchanged (pinned by `test_ui_tabs_contract.py` and `test_ui_editor_contract.py`).
- **Shared narrow helper**: `App.ui.util.narrow = {matches(), subscribe(fn) -> unsubscribe}` in `js/ui/core.js`, query `(max-width: 767.98px)`; factories unsubscribe in `destroy()` (`test_ui_listener_cleanup.py`).
- **`App.ui.menu` additions (additive)**: item `checked` (`menuitemradio` + `aria-checked`), `setItemChecked(i, bool)`, `setTriggerLabel(text)`, `popupLabel` option; `ITEM_SELECTOR` and `resetTabindex` widened to both roles; plain menus unchanged.
- **Tabs (`js/ui/tabs.js`)**: menu items call `commit(id)` (keeps `onBeforeChange` veto and the leave guard); `activate()` updates the trigger label and checked item (covers router, hydrate, GleepGlorp fills, `tools-grid` `select`); `setIndicator` repaints the trigger and item (the Tools "1 notice" cue); new controller `focusTab(id)` and `opener(id)` returning the visible control, used by `areas/admin/tools-page.js` and `tools-grid.js` instead of focusing `[role=tab]` directly; `.tablist[hidden] { display: none }`; narrow state built before the constructor's `activate(initial)`; the tabpanel keeps `aria-labelledby` to its (hidden) tab. Trigger: full-width, left-aligned, ellipsis, `chevron-down`; label = current tab name only (FD call), `popupLabel` = the group name (e.g. "Agent settings"). Testids: `<idPrefix>-tabs-menu-btn`, items `<tab testid>-menu-item`.
- **Header actions (`js/ui/editor.js`)**: new `actions.secondary: [{label, icon, testid, className, onClick({opener})}]` rendered as buttons at wide (DOM identical to today's `extra` placement) and as a `⋯` menu at narrow (`App.ui.menu`, `align: 'end'`, icon `more`, `aria-label` "More actions", testid `editor-more-btn`); exposes `secondaryButtons`; `extra` kept for compatibility; the agent editor's Chat migrates to `secondary`, passing the visible control as the `chatWith` opener. **`actions.test` stays a visible button** (FD call: stateful "Waiting…"/busy, primary on provider and MCP editors).
- **Built-in tools page gets the tab menu** (FD call; its 7+ categories are the strongest case).
- **Two batches** (FD call): A = narrow helper + menu additions + tabs (+ tools-page/tools-grid focus, narrow tests that waited on a visible `[role=tab]`); B = editor `secondary` + agent editor Chat. F3's 624×321 audit after both.

## For the design review
- Where the tabs factory and editor shell live, their current API and contract tests, and every consumer.
- Whether GleepGlorp fills or proposals drive tabs or header actions in a way the menu must keep working (e.g. a fill switching tabs programmatically).
- The ARIA pattern: a menu button controlling a tabpanel; what the existing `App.ui.menu` supports.
- Whether the editor shell's `test` action (e.g. "Test connection") is secondary (goes into the menu) or stays a button.
- Mode switching on resize without losing focus or the selected tab.
