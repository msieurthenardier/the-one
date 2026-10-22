# Leg: studio-state-and-editor-split

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Finish the behaviour-free `studio.js` split (flight DD1). Move the Agents list, the agent editor controller, form-data collection and the model picker into their own modules, using the `state` object from leg 02a:
- `agents-list.js`;
- `agent-editor-controller.js`;
- `agent-form-data.js`;
- `agent-model-picker.js`.

`studio.js` ends at ≤ 800 lines as the shell: area object, init, layout, `state`, close/discard/breadcrumb, `setActiveSection`, subscriptions, nav source, boot.

## Context
- **Legs 02a and 02b** introduced `state` (membership in 02a's addenda) and moved `studio-route`, `agent-data`, `library-pane` and the three glue modules. Read both artifacts, their addenda and their flight-log entries. Line numbers below are pre-split (at `dbcd458`); re-locate by symbol.
- **Sections that move:**

  | Pre-split lines | Section | Destination |
  |---|---|---|
  | 2478-2718 | the Agents list (`agentItem`, `createAgentsList`, `renderAgentList`, `renderAgentsEmpty`, focus helpers) | `agents-list.js` |
  | 2720-2888 | selection (`doSelect`, `replaceWith*`, `doEnterCreateMode`) | `agents-list.js` |
  | 4009-4067 | pending-agent (`resolvePendingAgent`, `tryConsumePendingSelect`) | `agents-list.js` |
  | 2890-3028 | `renderEditor` (the 55-key callback bag) and `setActiveTab` | `agent-editor-controller.js` |
  | 3030-3174 | cancel, delete, purge, `testProvider` | `agent-editor-controller.js` |
  | 3404-3462 | `checkDirty`, the ungated union | `agent-editor-controller.js` |
  | 3690-3907 | `save`, `extractApiError` | `agent-editor-controller.js` |
  | 3436-3688 | `collectFormData` | `agent-form-data.js` |
  | 3176-3402, 3909-4004 | the model picker, `renderModelCapabilities`, `fetchModelsForProvider`, `wireEditorEvents`, the VRAM check | `agent-model-picker.js` |

  In the table, 3404-3462 and 3436-3688 overlap: the boundary runs between `checkDirty` and `collectFormData`.
- **Coupling** (planning survey):
  - `doSelect` resets `state.dirty` and depends on `state.selectSeq` ordering;
  - the async model fetch re-takes `state.snapshot` when it is not dirty (about `:3324-3326`);
  - `save` uses `state.editorGen`;
  - `renderEditor` passes about 30 `agent-data` wrappers into `renderAgentEditor` by reference;
  - the `_refreshAgentAfterSelfConfigurationChange` → `doSelect` path goes through 02a's `ctx.onSelfConfigChanged`, which this leg wires to the controller. Its behaviour is unchanged here; leg 10 changes it.
- **Generation tokens** are captured by value on purpose and compared live (02a's addenda).

## Acceptance Criteria
- [ ] **The four modules exist**, each `App.studio.<name>.create(ctx)` with a documented ctx header and ≤ 800 lines. The create order resolves dependencies with no lazy back-references: form-data and the model picker are created before the controller, the controller before the list (selection calls the controller), or whichever order the code needs, stated in the shell.
- [ ] **`studio.js` is ≤ 800 lines.** It keeps the area object, `init` (`state`, layout, module creation), `closeOpenItem`/`discardOpen_`/breadcrumb/`setActiveSection`/`updateContentVisibility`/`writeUrl_`, the store subscriptions, the `_refresh` and `_dirty` test seams, the nav source, boot, and activate/deactivate.
- [ ] **No behaviour change.** No browser or unit test is edited except the pins and allowances. There is no DOM, testid or class change, and `git diff` since the leg-02b tree is limited to `studio.js`, the new modules, `index.html` and the pins.
- [ ] **Pins:**
  - `test_store_static.py`: the per-file `invalidate('agents')` counts update (the four editor sites move to `agent-editor-controller.js`; `agent-data.js` keeps 1), and `INVALIDATION_ROWS` (`/test/connect`, `/rename`, Purge) point at the controller;
  - `test_tool_categories.py` pins move with `App.toolCategories.byCategory` (used by `renderEditor`, so now in the controller);
  - the script count rises by 4;
  - the sink and ownership rows move with the same sums, stated per key in the flight log.
- [ ] **Docs:** `the_one/agents.md` "Studio area modules" lists every module, its ctx and the create order. CLAUDE.md lines naming moved functions are updated.
- [ ] **The full gate passes:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`, plus ruff.

## Verification Steps
- `wc -l` on `studio.js` and every `js/areas/studio/*.js` module created in legs 02a, 02b and 03.
- `grep -c` of each moved function name in `studio.js` is 0, except delegating calls.
- `git diff --stat` since the leg-02b tree.
- The full gate (background, explicit timeout).

## Implementation Guidance
1. Move `agent-model-picker`, and run the `agents` lane (model picker tests: `test_flow_studio_openrouter_picker.py`, `test_flow_agent_tabs.py`).
2. Move `agent-form-data`, and run `agents`.
3. Move `agent-editor-controller`, and run `agents`, `routing` and `shared` (`test_flow_dirty_confirm.py`).
4. Move `agents-list` with the pending-agent functions, and run `agents` and `routing`.
5. Pins, docs, then the full gate.

## Edge Cases
- **`escapeHtml`/`escapeAttr`** are hoisted `var`s defined at the end of `studio.js` (about `:4006-4007`) and used by the VRAM code. The model picker takes `App.escapeHtml`/`App.escapeAttr` (they exist on `App`) or its own local definitions; it must not rely on hoisting.
- **`self._selectedAgent` and `self._createMode`** stay on `self` (tests read them). Modules access them through ctx's `self`.
- **`editorTitleEl_`/`saveBtnEl_`** query by owned classes. They move as they are; leg 06 replaces them with shell handles.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio.js`, new `js/areas/studio/{agents-list,agent-editor-controller,agent-form-data,agent-model-picker}.js`, `index.html`.
- `tests/test_store_static.py`, `tests/test_tool_categories.py`, `tests/test_index_asset_cache_busting.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Pre-split line ranges are from the planning survey (`dbcd458`). They are re-verified by symbol at leg design review, after 02b lands.

## Design Review Addenda (2026-10-21)
These are binding and take precedence over the text above, which cites pre-split lines. Re-locate by symbol.

**Move order and creation order:** `agent-form-data` → `agent-model-picker` → `agent-editor-controller` → `agents-list`, created once each in `init`, in that order.
- **Call-time getters replace "no lazy back-references".** Exactly these are allowed, named in a shell comment:
  - `ctx.list()` in the controller: its cancel, delete and save call `replaceWithAgentsRoot_`, `replaceWithAgent_`, `focusAgentRowNear` and `visibleIndexOf`;
  - `agentData`'s `renderAgentList`/`doSelect` callbacks, which become getters into the list. Today hoisting resolves them.
- **`getFormSnapshot`, `checkDirty`, `_storedUngatedDisabledNames` and `UNGATED_TOOL_PREFIXES` move into `agent-form-data`** (not the controller). That breaks the picker ↔ controller cycle: the picker and the controller both take `checkDirty` from the form-data handle. The `App.toolCategories.ungatedPrefixes` read moves with them, and its `test_tool_categories.py` literal pin is retargeted.
- **`renderEmptyEditor` goes to `agents-list`** and is exposed. The shell uses it at about `:336`, `:428` and `:2260`.
- **`bootLoad` moves into `state`** (`state.bootLoad`), because the shell's boot writes it and the moved `tryConsumePendingSelect` reads it.
- **The list handle** exposes `isOpen`, `create`, `destroy`, `resetEmpty` (the `agentsEmptyEl`/`agentsEmptyKind` reset), `focusNear`, `indexOf`, `selection`, `render`, `renderEmptyEditor` and `doSelect`.
- **Local helpers:**
  - the one-argument `showFlash` wrapper (about `:2011`) is defined in the controller, and the explicit `App.showFlash(editorEl, …, true)` calls stay verbatim;
  - `escapeHtml`/`escapeAttr`, `formatBytes` and `vramCheckTimer` are local to the picker, and the hoisted shell `var`s are removed once they have no reader;
  - the picker's `_modelsFetchController`/`_activeProviderId` live in the picker, created once.

**Public surface preserved.** The shell keeps exposing exactly these, even when a module assigns them:
- `self._syncAgentSelection`;
- `App.studio.clearAgentFilter` (with the early stub at line 10);
- `self._enterCreate`;
- `self._setActiveTab`;
- `self._tryConsumePendingSelect`;
- the `_refresh` and `_dirty` test seams.

A test or a probe checks that each is a function after `init`.

**The 800-line target, with a pre-agreed fallback.** `wc -l` counts comments.
- If the shell is over 800 after the four moves, move `closeOpenItem`, `discardOpen_`, `closingItem_`, `focusClosedItem_`, `onBreadcrumbClick`, `setActiveSection` and `updateContentVisibility` (about 190 lines) into `js/areas/studio/studio-sections.js`, which takes the glue and list handles. Only if that is still not enough, also move the `Object.defineProperty` accessor block into a stateless `studio-state.js`.
- The mission criterion (≤ 800) is not relaxed.

**Pins, corrected:**
- `INVALIDATION_ROWS`: `/test/connect` is no longer in `studio.js`; leave it. Rename and Purge go to `agent-editor-controller.js`, and their text anchors are unchanged.
- `invalidate('agents')`: replace `("areas/studio.js", 4)` with `("areas/studio/agent-editor-controller.js", 4)`; `studio.js` drops to 0. `invalidate('sessions')` moves too.
- `test_tool_categories.py`:
  - `:86` adds the controller and form-data files;
  - `:103`'s `App.toolCategories.byCategory` moves with `renderEditor`, so it points at the controller;
  - `:120`'s load order includes the four new scripts, placed after `tool-categories.js` and before `areas/studio.js`.
- `test_ui_guards.py`:
  - `DYNAMIC_SINK_BASELINE` for `studio.js` keeps only the `content.innerHTML = '<div class="studio-section-content">…'` snippet;
  - `selectEl.innerHTML = optsHtml;`, the `insertAdjacentHTML` and `warningEl.innerHTML = msg;` move to an `agent-model-picker.js` entry;
  - `HTML_SINK_ALLOWANCE` for `studio.js` (10) is re-split, with the per-key sums stated.
- `_ui_ownership_allowance.py` is regenerated with the redistribution stated per key.
- The script-count pin goes from 79 to 83, or 84 with `studio-sections.js`.
- Docs: `the_one/agents.md` `:698` (`fetchModelsForProvider`), `:2132`, `:2277` and `:2289-2290` (`handlePurgeHistory`, the `checkDirty` sites); CLAUDE.md `:255` (check it).

**The mechanical missed-name check (the 02b `AGENTS_INTRO` lesson) runs after every move:**
1. Before the first move, save every 4-space-indent top-level declaration in `init` (`function X`, `var X`, `self._x =`, `App.studio.x =`).
2. After each move, a short Python script asserts that each saved name is declared in exactly one file, and that every other file using `\bname\b` outside comments gets it through ctx or an alias. Paste its output into the flight log.
3. A smoke after each move: load `#agents`, open an agent, open create mode, switch tabs, save, and check the console for `ReferenceError` (a small Playwright script, or the agents-lane smoke tests).
4. Lanes after **every** move: `agents` and `routing`; add `chats` and `shared` after the controller and list moves.

**Unchanged:** generation tokens are captured by value; local aliases keep stack traces and greps matching.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
