# Flight: Agents on the library

**Status**: completed
**Mission**: [Every control comes from one library](../../mission.md)

## Contributing to Criteria
- [x] **The area code is organised by surface** (≤ 800 lines per area entry module). This flight brings `studio.js` from 4181 lines to ≤ 800 by moving each section into its own module. `admin.js` (760) is Flight 3's.
- [x] **Every kind of control is defined once in the library** (partial). This flight adds:
  - tabs;
  - the group tile;
  - the tool row;
  - the editable chip list;
  - the tristate switch;
  - a multi-action danger zone.

  The agent editor and its six tabs are then built only from library controls.
- [x] **A change to one control's definition reaches every place it appears** (partial). Every agent-editor file reaches zero reuse-allowance rows.
- [x] **No UI markup is built from HTML strings** (partial). Every agent-editor file reaches zero sinks, `studio.js` included.
- [x] **Each control's styles are owned by that control** (partial). The agent-tab CSS is folded into the owning controls, and the dead rules are removed.
- [x] **Every migrated surface looks as it did before, apart from approved differences.** There are before and after captures of the agent editor's tabs, and the operator approves them at the HAT.
- [x] **Every library control works by keyboard and by role in both engines.** This covers the new controls, plus two library behaviour fixes: squawks 0220 and 0221.
- [x] **Existing behaviour holds.** Two live defects found in planning are fixed, each with a test that reproduces it first (DD9).

---

## Pre-Flight

### Objective
This flight moves the Agents destination onto the library.
1. Split `studio.js` into modules of no more than 800 lines, without changing behaviour.
2. Build the controls the agent editor needs, in the canonical versions the operator approved on the 2026-10-16 canvas:
   - tabs;
   - one group tile, used for both the built-in tool categories and MCP sources;
   - one tool row;
   - the editable chip list;
   - the tristate switch;
   - a multi-action danger zone.
3. Fix two library behaviours app-wide: arming a confirm is now announced (squawk 0220), and an info button's text becomes visible on focus and press (squawk 0221).
4. Rebuild the agent editor and all six tabs on the library, under Flight 1's mount-once / patch-through-handles policy (Flight 1 DD1).

When it lands, every agent-editor file has zero sinks and zero reuse-allowance rows. Squawk 0094 is closed, and the lane budgets are re-measured (squawk 0217).

### Open Questions
- [x] How should `studio.js` split without breaking its shared editor state? → DD1
- [x] Which shared mount lifecycle should replace Flight 1's module-level singletons? → DD2
- [x] Which new controls, and with what visible results? → DD3, DD4 (operator canvas, 2026-10-16)
- [x] The tristate master switch: the ARIA switch role has no mixed value. → DD4 (native checkbox semantics; the canvas master uses `role=checkbox`)
- [x] Both Delete Agent and Purge now sit in the agent danger zone, but `dangerZone` takes one action. → DD3 (an `actions` array)
- [x] How far do the squawk 0220 and 0221 fixes reach? → DD5 (in the library, so every consumer benefits)
- [x] What about the two defects found in planning? → DD9
- [x] Do tabs re-render on switch? → DD6 (no: each tab mounts once per agent and patches)

### Design Decisions

**DD1: Split `studio.js` first, as a behaviour-free restructure leg.**

`studio.js` (4181 lines) moves into modules under `static/js/areas/studio/`. Each module follows the `providers-section.js` ctx precedent: `App.studio.<module>.create(ctx)` returns a handle, and the module reaches studio only through `ctx`. The split, from the planning survey:

| Module | Contents | Approx. lines |
|---|---|---|
| `studio.js` shell | area object, init state, layout, close/discard/breadcrumb, `setActiveSection`, nav source, boot | ~580 |
| `studio-route.js` | `serialize` / `hydrate` | ~340 |
| `library-pane.js` | the Library list and the pending-item rule | ~590 |
| `library-groups.js` | knowledge, MCP and connector section glue (or three ctx factories) | ~630 |
| `agent-data.js` | API wrappers, caches, `loadAll` | ~500 |
| `agents-list.js` | list and selection | ~470 |
| `agent-editor-controller.js` | `renderEditor`, tab activation, cancel/delete/purge/test, `checkDirty`, save | ~560 |
| `agent-form-data.js` | `collectFormData` | ~285 |
| `agent-model-picker.js` | model picker, capabilities, VRAM check | ~370 |

- **Which leg moves which module:**
  - leg 02 moves `studio-route`, `agent-data`, `library-pane` and `library-groups`;
  - leg 03 moves `agents-list`, `agent-editor-controller`, `agent-form-data` and `agent-model-picker`.
- **Leg 02 introduces the shared `state` object first**, before any module moves. The data modules' caches and `dirty`/`snapshot` reach them only through it. Leg 03 then moves the editor modules onto the same object. A module never caches a `state.x` value in a local variable.
- **Shared state becomes one object.** The state shared across sections today is closure variables: `dirty` (about 60 write sites), `snapshot`, `editorGen`, `selectSeq`, the layout hosts and the section caches. It moves into one `state` object owned by the shell and passed by reference in every ctx, so a write anywhere is the same write it is today. The `Object.defineProperty` getters that `serializeState` reads (`studio.js` about `:441-501`) delegate to it.
- **Legs 02-03 are a pure restructure.** They keep behaviour and DOM byte-identical, so any visible or test change in them is a defect. Static pins that read `studio.js` text are retargeted to the new modules deliberately, never relaxed:
  - `tests/test_store_static.py` (`_window` reads, the `invalidate('agents')` count of ≥ 5, `INVALIDATION_ROWS`, the `router.sync` call text);
  - `tests/test_tool_categories.py` (`App.toolCategories.byCategory`);
  - the sink allowance and baselines;
  - the ownership allowance;
  - the script-count pin.
- **Trade-off.** More script tags and ctx plumbing. In exchange, every later leg edits one module instead of a 4000-line file.

**DD2: A shared mount-lifecycle helper replaces the singletons.**
- `App.ui.util.mountSlot()` returns `{mount(fn) → {gen, isCurrent(), destroy hook}, current(), destroy()}`. It holds one current mount with a generation counter. Mounting a new one destroys the previous one first. An async result checks `isCurrent()` before it writes.
- It lives in `js/ui/core.js` with the other `util` helpers. `provider-models.js`'s `activeController` and `provider-editor.js`'s `latestMount` (Flight 1 debrief debt) are **removed outright**, and the provider contract and browser tests stay unchanged. The agent editor and its tabs use the same slot.
- The VRAM check in the model picker is async: its result must check `isCurrent()`.
- It has unit-level contract tests in the harness. It is a utility (`util`), not a factory, so it gets no catalogue row; a note in the catalogue's header covers it.

**DD3: New library controls, each built with its first consumer.**

These follow the operator's canvas decisions (2026-10-16, "Agent tabs preview": approved) and Flight 1 DD8 (confirmed at the Flight 1 HAT):
- **`App.ui.tabs(opts)`**: a W3C tablist with roving focus. Arrows move focus only; Enter, Space and click select. It reproduces `.tablist`/`.tab` and today's `App.tabs` behaviour exactly.
  - Returns `{el, select(id), selected(), panel(id), destroy}`. Panels are created once and hidden or shown.
  - `App.tabs` stays as a retired-API alias while `tools-grid.js` (Flight 3) still uses it, counted in the reuse check's retired-API rows.
  - `App.tabs` returns `{activate, getActive}` and the new control returns `{select, selected, panel, destroy}`. The callers in `agent-editor.js:285` and `studio.js` change in leg 06.
- **`App.ui.groupTile(opts)`**: the merged built-in-category / MCP-source tile.
  - Header: a master switch (`tristate`), name, count chip, optional extra chips and actions.
  - Optional subtitle.
  - Expand button ("**N** tools ▸"). Its body mounts lazily on first expand.
  - Returns `{el, setCount, setMaster(state), setExpanded, body, destroy}`.
  - It owns today's `.tools-category-tile*` and `.mcp-source-tile*` looks, which are identical per the extraction. The two class families collapse into one owned `ui-group-tile*` family with the same declarations.
  - It does **not** touch the admin Built-in tools grid's `.area-admin .tool-tile*` / `.tool-tile-link` family (`admin.css:153-205`, `tools-grid.js`). That family is unrelated, belongs to Flight 3, and keeps its rules.
- **`App.ui.toolRow(opts)`**: one row for a tool, with a checkbox, mono name, " — " and the description truncated to 100 characters (full text in `title`).
  - With `disclosure: {label: 'Overrides', onOpen}`, it renders as `<details>` with the affordance and lazily fills its body on first open.
  - Without it, it renders as a label row (the MCP tool row).
  - It covers the disabled, struck-through state (`tool-row-disabled`).
- **`App.ui.chipList(opts)`**: the editable chip list: chips, locked chips with no remove button, a remove "×" and an add input.
  - The remove "×" is **muted (`--fg-secondary`), turning danger red on hover and focus** (canvas-approved).
  - Returns `{el, values(), setValues, setError}`.
  - It owns `.chip-list-editor` and `.chip-list-input`. The admin and studio area copies of those rules fold into its banner, with their specificity variants preserved: `.tools-editor-field .chip-list-editor` and `.field-error-highlight` (`admin.css:345-420`).
  - The unmigrated admin string path (`tools-form-helpers.js`, `tools-editor.js`) and `mcp-server-editor.js` keep emitting those classes until Flights 3 and 4. That raises their ownership-allowance rows, an **expected bump** recorded with its reason in the flight log, as Flight 1's leg 05 did.
  - A computed-style check proves the admin Built-in tools editor's chip list looks unchanged (DD10 captures).
  - Its first consumer is the Tools-tab overrides. The Built-in tools editor in Flight 3 is the second, through `tools-form-helpers.js`.
- **`App.ui.toggle` gains `tristate`** (Flight 1 DD8 note):
  - with `tristate`, `role=switch` is skipped and the control keeps native checkbox semantics in every state;
  - `setIndeterminate(bool)` is added, and `setChecked` clears the indeterminate state;
  - the mixed thumb is the accent thumb at the midpoint on the accent-translucent track;
  - there is a forced-colors rule.
- **`App.ui.dangerZone` gains `actions: [...]`**, a list of `{label, testid, confirmLabel, beforeArm, onConfirm, icon}`. `action` stays as a one-item alias. The agent zone holds Delete Agent and Purge now.

**DD4: The visible changes are exactly those approved on the canvas** (2026-10-16; anything else visible is a defect):
1. **The switch.** The 32×18 studio pill, which Tab cannot reach, becomes the library switch on every agent tab: tool categories, MCP sources and knowledge-base attach. The category masters show the mixed state.
2. **The chip remove "×"** in editable chip lists goes from accent violet to muted, turning red on hover and focus.
3. **MCP's Refresh button** becomes the library's small button: 24px tall, 10px text, 14px icon.

4. **Info buttons** lose their hover tooltip and show their text on press, as a toggletip (DD5). This one was not on the canvas: the operator approved it separately on 2026-10-21 (press-only). `test_flow_admin_tools_editor.py:194` keeps passing because the admin string path keeps `title` (DD5).

Also carried over from Flight 1 DD8 and confirmed:
- the Test button and result use the status line;
- the danger zone has trash icons and the armed style;
- the shell header matches the provider editor's.

**DD5: The library behaviour fixes, squawks 0220 and 0221.**
- **0220:** `App.ui.confirm` announces arming through one shared, visually hidden polite live region, for example "Press again to confirm delete", built from the confirm label. Lapse and commit clear it. The local workarounds in `rules-notes-tab.js` (about `:211-214`) and `self-configuration-tab.js` (about `:1293-1298`) are removed. Every consumer benefits at once: 14 call sites, plus dangerZone.
- **0221:** `App.ui.infoButton` becomes a toggletip:
  - pressing it (click, Enter or Space) shows its description in a small bubble anchored to the button, and Escape or a press elsewhere closes it;
  - focus alone shows nothing new, but the description stays in `aria-describedby`;
  - the bubble is announced once through a polite live region inside it;
  - the `title` hover tooltip is removed, so the text is not shown twice.

  This is the WAI toggletip pattern. It is new behaviour, recorded under squawk 0221, and the HAT confirms it.
- **Library rules for both:**
  - **Toggletip listeners.** Outside-press and Escape use a capture-phase `pointerdown`/`keydown` listener that is added when the bubble opens and removed when it closes and on `destroy`. This follows the `menu.js:96` precedent; no permanent document listener.
  - **The confirm live region** is one node, appended lazily on the first arm, never at load. Its text is set *after* insertion (empty first, then the text) so that it announces. The harness can find it.
  - Both get role-structure assertions (DD11). `tests/test_ui_guards.py` shows no new permanent `document.addEventListener`.
- **Tests that 0221 breaks** (leg 05 updates them):
  - `tests/browser/test_ui_info_contract.py:34-40`;
  - `test_flow_provider_editor.py:510,556`;
  - `test_flow_studio_mcp_editor.py:688`.
- **The string path is not covered.** `tools-form-helpers.js`'s string-built info icons do not get the toggletip until Flight 3 migrates that path. Until then they keep their current `title` behaviour, a recorded inconsistency that Flight 3 removes.

**DD6: The tabs mount once per agent and patch.**
- `renderEditor` re-mounts the editor only on a new agent identity (selection, create → edit).
- Switching tabs shows or hides panels that are already built.
- Save patches the shell (title, subtitle, unsaved caption), the General fields and each tab's toggles through handles.
- A tab whose data reloads (a self-config revision, a rules change) patches its own content through its handles.
- Lazy bodies (overrides, MCP tool lists) mount once on first open and are kept.

**DD7: The canonical form of each agent surface.**
- **The agent editor** uses `editorShell`: the breadcrumb "Agents", the Chat button through `extra`, Cancel and Save, the inline error. Its tabs use `App.ui.tabs`.
- **General** uses `field`, `select` and `textarea` for its fields. The model picker's options and capability line are patched through handles; there is no `innerHTML` for options. The Test result is `status`. The danger zone has two actions: Delete Agent and Purge now.
- **Knowledge** uses one library switch per knowledge base. This closes squawk 0094.
- **MCPs** uses `groupTile` per source:
  - the protocol chip and the small Refresh button sit in the header;
  - the self-configuration source is locked on and disabled;
  - tool rows are `toolRow` without a disclosure;
  - the auth-required notice is a status line.
- **Built-in Tools** uses `groupTile` per category (the tristate master) and `toolRow` with the "Overrides" disclosure. The override fields come from the library through `tools-form-helpers.js`; the chip-list fields use `chipList`. The `time-tool-note` stays.
- **Rules and notes** keeps its library controls. Its remaining hand-built pieces move onto the library: the status and alert lines, the empty states and the `.ui-toggle` class query. "Clear all" stays an `App.confirmDialog`.
- **Self-configuration** uses `toggle` for its two switches (the library switch, label beside it). It uses `status` lines, `emptyState`, `copyField` for the token reveal (the hand-rolled clipboard code goes), `confirm` for revoke, and a library disclosure for history. The revision cards keep their structure, built from library buttons. Since this flight rewrites `self-configuration-tab.js` (1424 lines), it also splits it into modules of ≤ 800 lines: status and credentials, revisions, history.
- **Files over 800 lines that stay over.** The mission's ≤ 800 criterion names the area entry modules only. `provider-models.js` (1004), `provider-editor.js` (895), `knowledge-section.js` (1493) and `mcp-server-editor.js` (2153) are not split in this flight. That is recorded, not silent.

**DD8: Settle shared helpers by the second consumer.**
- **`tools-form-helpers.js` gains a DOM builder, `renderFieldNode`, beside the string `renderField`.**
  - `renderFieldNode` builds the field kinds the Tools-tab overrides render from library controls: text, number, select, `chipList`, checkbox, `infoButton`.
  - The Tools tab switches to `renderFieldNode`, while `admin/tools-editor.js` (Flight 3) keeps consuming the string `renderField` through `innerHTML` (about `:147`). So the string path and its sinks and allowance rows in `tools-form-helpers.js` survive until Flight 3, as recorded debt.
  - The shared helpers `renderFieldErrors`, `applyShowIf` and the `.field-row`/`.chip-list-editor` queries (about `:603-679`) gain node-path equivalents where the Tools-tab overrides use them (errors on override fields at least). Leg 08's design states which ones, and the rest stay string-path-only until Flight 3.
- Flight 1's single-consumer options are checked: `dangerZone.beforeArm` (second consumer: Delete Agent's usage check), `field.host` and `setLabel`, `consentLink.help`. Any that still has one consumer is noted, not removed: Flights 3-5 may supply the second.

**DD9: The defects found in planning are fixed, test first.**
1. **MCPs tab: collapsing an expanded source throws.** `mcps-tab.js` `_setExpanded(false)` calls `_parseSourceIdFromHash`, which is defined nowhere (about `:364`). This is a grounding defect in this flight's path, confirmed at review: the collapse handler aborts partway, so the collapse state and `aria-expanded` are not updated. It is fixed in leg 07, with a test asserting `aria-expanded=false` and a hidden body after collapse.
2. **Stored `tool_overrides` are wiped on Save when the Overrides panel was never opened.** This was **confirmed at design review**:
   - `AgentConfig.tool_overrides` defaults to `None`;
   - the repository upsert writes it unconditionally (`db/repositories.py:255,273`);
   - `update_agent` (`api.py` about `:946-974`) preserves only `mcp_overrides`, `self_revision_requires_approval`, `notes_enabled` and `kb_ids` when they are omitted;
   - the client sends `null` for an empty map (`studio.js:3614`), and the override inputs exist only after the `<details>` opens.

   So both an omitted key and `null` wipe the stored overrides. This was the planned divert trigger, now resolved as design: the fix is **server and client together**.
   - **Server:** `update_agent` preserves `tool_overrides` when the key is omitted, like `kb_ids`. An explicit `null` stays an explicit clear. Unit tests pin both cases.
   - **Client:** when the Overrides UI for the agent was never loaded, the PUT omits `tool_overrides`. When it was loaded, the PUT sends the edited map, including `{}` when the operator cleared every override (an explicit clear). It never sends `null` for "not loaded".
   - **Browser test:** seed an agent with overrides, change the description, Save, read the agent back: the overrides survive.

   It lands in leg 08 with its own server-side change, kept separate from the UI migration in that leg's report.
3. **A self-configuration change discards unsaved General edits.** `_refreshAgentAfterSelfConfigurationChange` → `doSelect` re-renders and resets `dirty` (`studio.js` about `:2040-2057`, `:2756`). Under DD6 the change patches the agent record and the Self-configuration tab only, through `agent-editor-controller.js` (the module that owns `doSelect` after the split), keeping the form and its dirty state. This is fixed in leg 10. Its browser test types into General, triggers a self-configuration change, and asserts that the field value and the unsaved caption survive.

**DD10: Captures, budgets and the test contract.**
- **Captures.** `scripts/ui_capture.py` gains the agent-editor surfaces in both themes:
  - each tab for a seeded agent;
  - the Tools tab with Filesystem expanded and an override open;
  - MCPs with a stubbed source expanded;
  - Self-configuration enabled, with one pending revision;
  - Rules and notes with entries.
  - **The admin Built-in tools editor with a chip-list field.** Flight 3 migrates it, but this flight folds its chip-list rules into the library, so its look is guarded here.

  The "before" set is taken in leg 01, before any agent file changes. The "after" set is taken in leg 11 (`agents-close`).
- **Lane budgets (squawk 0217).** The `agents` and `shared` lanes are re-measured at the flight gate and re-budgeted with the script's own headroom rule (about 25%, rounded to 30 s). The squawk's evidence has drifted: CLAUDE.md now reads 510/497 and 300/286. If `agents` would exceed 1.3× its budget, it is split into an `agents` and an `agent-tabs` lane. `tests/test_run_tests_lanes.py` pins hold.
- **Test contract.** All testids are kept, and so are the ids `#studio-*`. Tests that select retired classes move to role, testid or label locators. Each leg lists the tests it will break from a grep made at leg design (the Flight 1 debrief lesson). Known class selectors:
  - `.tool-switch`, `.tool-toggle` (`test_flow_agent_tabs.py:205,234,248`);
  - `.tools-category-tile*`, `.tool-tile*`, `.chip-list-editor` (`test_flow_studio_time_tool.py`, `test_flow_studio_tools_overrides.py`);
  - `.test-result*` (`test_flow_agent_tabs.py:294-296`);
  - `.studio-editor.is-hidden` (`test_flow_agent_crud.py:141`, `test_flow_agent_tabs.py:55`, `knowledge_attach:102`).

**DD11: Contract-test additions from the Flight 1 debrief.** Every new size-bearing control (tabs, the group tile header actions, chips, tool rows, the danger-zone buttons) gets computed-size assertions against its canonical neighbours. Every control with an ARIA composite role (tabs, toggletip) gets a role-structure assertion: required owned elements, and no interactive descendants inside presentational-children roles.

### Citation Audit
Verified at `dbcd458` (planning surveys, 2026-10-15/16):

| Citation | Status |
|---|---|
| `js/areas/studio.js` section ranges; the `dirty`/`snapshot`/`editorGen`/`selectSeq` state; the `defineProperty` getters at `:441-501` (DD1) | verified (survey) |
| `js/areas/studio/providers-section.js:1-30` ctx contract, the precedent for DD1 | verified (Flight 1) |
| `tests/test_store_static.py:192-219,232,245,297,321,327,350`; `tests/test_tool_categories.py:86,103,120`; `tests/test_index_asset_cache_busting.py:90` (`== 73`) (DD1) | verified (survey) |
| `js/ui/choice.js:97-98` toggle has no indeterminate (DD3) | verified (survey) |
| `js/ui/editor.js:212-236` dangerZone takes one action (DD3) | verified (survey) |
| `js/areas/studio/tools-tab.js:118-197,212-317,379,441-451`; `mcps-tab.js:113-310,364,406-486,506-558`; `knowledge-tab.js:120-135` (DD3, DD7, DD9) | verified (survey + extraction) |
| `css/studio.css:69-85` (`.tool-toggle{display:none}`, pill), `:410-604` (the tiles), `:611-714` (rows); `css/admin.css:391-448` (`chip-list-editor`) (DD3, DD4) | verified (extraction) |
| `js/ui/confirm.js:64-71,120-124` (arm path, no live region) (DD5) | verified (survey) |
| `js/ui/field.js:123-141` infoButton (`title` plus a hidden span) (DD5) | verified (survey) |
| `js/areas/studio/mcps-tab.js:364` `_parseSourceIdFromHash` is undefined anywhere in `static/` (DD9-1) | verified (survey grep) |
| `studio.js:3614` empty override map becomes `null`; `api.py:946-974` merges only `mcp_overrides`/`kb_ids` (DD9-2) | verified (survey), and **confirmed** at design review (the repository upsert writes it unconditionally; `update_agent` has no preserve). Fixed in leg 08 |
| `studio.js:2040-2057,2756` self-config refresh calls `doSelect`, resetting `dirty` (DD9-3) | verified (survey) |
| `scripts/run-tests.sh:61,68` budgets `agents` 510, `shared` 300 (DD10) | verified (survey) |

### Prerequisites
- [x] Flight 1 is completed and merged (`main` at `dbcd458`); the branch is `flight/02-agents-on-the-library`.
- [x] The operator approved the canvas (2026-10-16): https://claude.ai/artifact/Pzn35KdwV9gsTrnCPRCcqo
- [x] WebKit userland and `THE_ONE_TEST_NETNS=1` work. Re-verify at the start of **every** leg that runs browser tests.
- [x] The before captures of the agent surfaces are taken in leg 01, before any agent file changes.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Restructure first, then controls, then surfaces: the order Flight 1 proved. Leg 01 takes the before captures. Legs 02-03 split `studio.js` with no behaviour change, introducing the state object on its own before the editor modules move. Legs 04-05 build and fix library controls in the harness. Legs 06-10 move the editor and each tab onto them, removing their files' allowance rows and sinks. Leg 11 closes the counts, captures the after set, re-budgets the lanes and updates the docs. Leg 12 is the HAT.

### Checkpoints
- [x] `studio.js` ≤ 800 lines; the full gate is green with no test behaviour change; before captures taken.
- [x] The new controls are contract-tested in both engines.
- [x] The 0220/0221 fixes are live; the mount slot replaces the Flight 1 singletons.
- [x] The agent editor and every tab are on the library; the DD9 defects are fixed.
- [x] Every agent-editor file is at zero sinks and zero allowance rows; budgets re-measured; full gate green.
- [x] HAT passed.

### Adaptation Criteria

**Divert if**:
- The `studio.js` split cannot stay behaviour-free (a test changes behaviour, not just a path pin): stop, and re-plan the split boundary.
- A server-side change beyond DD9-2's preserve-on-omit turns out to be needed. Raise it as its own design question.

**Acceptable variations**:
- Module boundaries and names inside the DD1 table.
- Merging or splitting the two studio-split legs (02/03) or the two control legs (04/05).
- Option names on the new controls.
- An `agents` lane split.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `before-set`: extend `scripts/ui_capture.py` with the agent-editor surfaces and the admin Built-in tools editor (DD10), then take the before set. No source change.
- [x] `studio-state-route-data` (02a): the shared `state` object (its own gate), then `studio-route` (stateless) and `agent-data`. Retarget the pins.
- [x] `library-pane-and-groups` (02b): `library-pane`, then the knowledge, MCP and connector glue modules. Pins, docs, full gate. Split from leg 02 at design review (2026-10-21); the other leg numbers are unchanged.
- [x] `studio-state-and-editor-split`: first introduce the shared `state` object in the shell with no module moves, and run the gate. Then move `agents-list`, `agent-editor-controller`, `agent-form-data` and `agent-model-picker`. `studio.js` ≤ 800; pin the script count and order; full gate.
- [x] `tab-and-tile-controls`: `App.ui.tabs`, `groupTile`, `toolRow`, `chipList`, `toggle` tristate, `dangerZone` actions; catalogue rows, owned classes, contract tests with size and role-structure assertions (DD3, DD11).
- [x] `library-behaviour-fixes`: the confirm arm announcement (0220), the infoButton toggletip (0221) and its four broken tests, and `mountSlot` with the provider singletons removed (DD2, DD5).
- [x] `agent-editor-frame` (06a): `editorShell` and `App.ui.tabs` for the frame, plus the mount slot. Identity is (name, create/edit): a rename remounts. Same-identity saves patch the frame and, in the interim, rebuild the five non-General panels. Includes the load-error node and dirty-tracking wiring per panel.
- [x] `general-tab` (06b): the General fields with `setAgent`, the model picker, Test as status (testids kept), the two-action danger zone. Split from leg 06 at design review (2026-10-21).
- [x] `knowledge-tab` (07a): a library switch per knowledge base, `setAgent` patch-only; closes 0094.
- [x] `mcps-tab` (07b): `groupTile` (attach-only master), `toolRow` rows (input datasets added to the library), keyed Refresh, `setAgent`; DD9-1 test first. Split from leg 07 at design review (2026-10-21).
- [x] `main-merge-and-overrides-port` (08a): merge `main` (squawk 0223), port its client rule into `agent-form-data.js`, add the `{}`, partial-merge, stale-stored and locked-chip tests. (DD9-2 is completed by 0223 plus this leg.)
- [x] `tools-tab` (08b): `groupTile` (tristate master) and `toolRow` with Overrides; the new `tool-override-fields.js` (`tools-form-helpers.js` untouched); `setAgent`; Cancel re-arms bodies; CSS removals. Split from leg 08 at design review (2026-10-21).
- [x] `rules-and-notes-tab`: the remaining hand-built pieces of Rules and notes on the library.
- [x] `self-config-refresh` (10a): the DD9-3 fix, test first: the controller's `onSelfConfigChanged` patches General (clean fields silently, dirty fields kept with a note, the operator's choice of 2026-10-21), MCPs and Self-configuration; the tab's `setAgent` and local refetches.
- [x] `self-config-split` (10b): a mechanical split into four ≤ 800-line modules around a shared context, with no behaviour change.
- [x] `self-config-library` (10c): the modules on library controls (switches, status, emptyState, section, button, copyField copy-once, confirm; the history stays a native `<details>`), with the token-attribute test. Leg 10 was split into 10a-10c at design review (2026-10-21).
- [x] `agents-close`: zero counts on every agent file, after captures (including the admin editor guard), the lane re-budget (0217), the full gate, docs.
- [x] `flight-hat` *(optional)*: the operator walks each tab in both themes, the DD4 differences, the 0220/0221 behaviours and the DD9 fixes, and approves the capture set.

> Leg design greps every moved path, renamed class and retired selector across `tests/`, `scripts/`, `Makefile` and `docs/ui-testid-registry.md`, and pastes the hits into the leg (Flight 1 debrief).

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- `wc -l the_one/interfaces/web/static/js/areas/studio.js` ≤ 800, and every new studio module ≤ 800.
- In `tests/_ui_ownership_allowance.py` and `HTML_SINK_ALLOWANCE`, these files have no rows: `studio.js` and its new modules, `agent-editor.js`, `general-tab.js`, `rules-notes-tab.js`, `tools-tab.js`, `mcps-tab.js`, `knowledge-tab.js`, `self-configuration-tab.js` and its split modules.
- `make test-unit`; `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` is green, with the new budgets.
- HAT: the operator approves the agent-tab capture set and the 0220/0221 behaviours.
