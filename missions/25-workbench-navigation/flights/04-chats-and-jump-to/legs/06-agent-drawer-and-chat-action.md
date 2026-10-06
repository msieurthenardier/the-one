# Leg: agent-drawer-and-chat-action

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Add the agent drawer (§5.7, DD7):
- a non-modal `App.ui.drawer` in a shell slot after `<main>`;
- toggled from the chat header;
- it pushes at 1280 and wider, and overlays below that;
- it shows the chat's agent read-only, including **what it can use** (A13);
- **Open agent settings** reaches the agent with the Agents filter cleared.

Add the agent editor's **Chat** header action (DD8). Close **squawk 0118** by documenting
the editor Cancel and dirty contract.

## Context

- **Flight decisions:** DD7 (the drawer), DD8 (Chat and the single `dirty` flag), DD14
  (`App.ui.drawer` and `listPane.setQuery` are built here, where they are consumed) and
  DD15 (A13, A20, A21).
- **The chat header** from leg 4 has no toggle yet; this leg adds it.
- **The `aria-controls` rule** (cycle 2): the drawer element is created **once** with the
  chat area and toggled with `hidden`. It is never removed while the header exists, so the
  toggle's `aria-controls` always resolves. `_a11y_resolve.js` (around 76–82) checks
  `aria-controls` unless `aria-expanded="false"`.
- **The agent editor header** is built by an HTML string (`areas/studio/agent-editor.js`,
  around 85–102: `.form-actions` holding the caption, Cancel and Save). To avoid editing a
  baselined sink template, the **Chat** button is inserted with DOM APIs after render,
  into the header's `.form-actions`, before Cancel. The Developer confirms the sink-guard
  impact.
- **The studio `dirty` flag stays single** (DD8). Chat and Open agent settings leave
  through `App.router.go`, so a dirty editor asks once.

## Inputs

- Legs 1–5: the store `sessions`; the session state (`activeId`, the agent of the current
  or pending chat); the chat header (`chat-header`) and the pane modules; the composer.
- `index.html`: the `.app-shell-row` (`#app-rail`, `<aside id="app-sidebar">` and
  `<main id="main-content">`). `css/base.css`: the shell row and `#main-content` rules.
- `areas/studio.js`:
  - the Agents list pane (`App.ui.listPane` with a filter);
  - `setActiveSection`, which owns the pane's lifetime;
  - the tool-category tables at around 460–477.
- `areas/admin/tools-grid.js:19` and `areas/admin/tools-editor.js:81`: the other two
  copies of the category table.
- `App.usage.mcpToolCount`. `GET /api/tools/configs`.
  `GET /api/agents/{name}/self-configuration` (`{enabled, source_id}`).
- `AgentConfig`'s `enabled_tools`/`disabled_tools` semantics (`the_one/agent/config.py`
  `is_tool_enabled`).

## Anchors after leg 4b (checked by the Flight Director)

- **The chat header** is built once in `static/js/areas/chat/chat-pane.js`:
  - `var title = el('h1', { className: 'chat-header-title' })` at around 164;
  - `header.chat-header` (testid `chat-header`) at around 167;
  - `renderHeader(view)` at around 170.

  The leg 4b hand-off says the drawer toggle goes at the **end** of the header.
- **The provider type** helper is `App.chat.agentPicker.providerType(agent, providers)`
  (`areas/chat/agent-picker.js` around 75, exported around 283). The drawer badge reuses
  it.
- **There is no `App.studio.clearAgentFilter` yet.** `App.studio` holds only render
  helpers (`renderAgentEditor`, `renderKnowledgeCreate`, and so on). The Agents list pane
  is local to `studio.js`'s closure, which is why AC12 adds the export.
- **Leg 5 is changing `composer.js` and the telemetry placement** in parallel. This leg
  does not touch either file.

## Acceptance Criteria

**A. `App.ui.drawer` (DD14).**

- [ ] **AC1. The factory.** `App.ui.drawer(opts)` returns
  `{el, open(), close(), toggle(), isOpen(), setMode('push'|'overlay'), destroy()}`.
  - The options are:
    - `label`, the `<aside>`'s `aria-label`, required;
    - `heading` (a node or text), `body` (a node) and `footer` (a node);
    - `testid`;
    - `onOpenChange(open)`.
  - The `<aside>` is toggled with `hidden`.
  - **Escape while focus is inside** closes it and returns focus to the element passed to
    `open(opener)`, or else the last opener.
  - It installs **no** document or window listener.
  - It is ES5 and built with DOM APIs.
- [ ] **AC2. Demo, inventory and contracts.**
  - A demo section is added on the Design language page.
  - `docs/ui-control-inventory.md` gets an `App.ui.drawer` row.
  - The registry gets the demo testids.
  - `tests/browser/test_ui_drawer_contract.py` runs in both engines in the `contracts`
    lane: toggle and `hidden`, Escape and focus return, both `setMode` modes, and no
    document listener (`test_ui_listener_cleanup.py` gains a case).
  - It is green with `THE_ONE_REQUIRE_WEBKIT=1`.

**B. The chat drawer (§5.7, DD7).**

- [ ] **AC3. The slot.** A **static** `<aside id="chat-drawer" aria-label="This chat's
  agent" data-testid="chat-drawer" hidden>` is added to `index.html` inside
  `.app-shell-row`, **after** `<main>` (design review question 2). The chat area does not
  reach outside itself to create it.
  - The chat area **fills** the slot, through `App.ui.drawer`, and **toggles** its
    `hidden`.
  - The chat area's `deactivate` hides it, and `activate` shows it only when there is a
    chat view (joined or pending) and the mode's state is open. It is also hidden when the
    header view is null.
  - So on Agents, Library or Settings it is always `hidden`, and `<main>` keeps its full
    width.
  - **`tests/browser/test_shell_rail.py`.**
    - Its shell-row children assertion (around 74,
      `["app-rail","app-sidebar","main-content"]`) is **updated** to include `chat-drawer`.
    - Its landmark test (around 84–110) passes with the drawer hidden and with it open,
      the name unique.
  - The skip link and `<main>` are unchanged. The `index.html` asset pin is updated.
- [ ] **AC4. Push and overlay.**
  - **At 1280px and wider:** push mode (a flex sibling, 320px wide, `border-left`,
    `--surface`), **open by default**.
  - **Below 1280px:** overlay mode, positioned over the right of the chat pane at 320px,
    with `border-left`, `--surface` and `--shadow-modal`. It has no scrim and no
    outside-click close, and is **closed by default**.
    - `.app-shell-row` gains `position: relative`, and the overlay is
      `position: absolute; top: 0; right: 0; bottom: 0`.
    - `#chat-drawer[hidden] { display: none; }` follows the `base.css` (around 38)
      pattern, so the drawer's own display never defeats `hidden`.
  - The state lives in one object (`{mode, open}`) applied by a single `apply()`. The open
    state persists in `localStorage` (`chat-drawer-open`, a JSON object
    `{push, overlay}`, wrapped in try/catch).
  - A resize across 1280 switches the mode, using `matchMedia('(min-width: 1280px)')` and
    its `change` event. That is not a document or window listener; it is removed on
    destroy. The mode's persisted state then applies.
  - **The test viewport** (design review high, question 1). Playwright's default is
    1280×720, which is push mode, so **the drawer is open in every Chats browser test**
    (main is 588px). That is accepted as the product default. The leg runs the full
    `chats` and `shared` lanes. Any test that assumed a full-width Chats pane is fixed in
    this leg, and the flight log lists them. Drawer flow tests cover **1280** as well as
    1440 and 1024.
- [ ] **AC5. The toggle.** A `btn-ghost` icon-only button in the chat header:
  - the `panel-right` icon;
  - `aria-label="Show this chat's agent"`, `aria-pressed` set to the open state,
    `aria-controls` the drawer id;
  - testid `chat-drawer-toggle`, at `margin-left: auto`.

  It shows only in `joined` and `pending`.
- [ ] **AC6. The header** is 48px (A21), so its hairline lines up with the chat header. It
  shows the agent name (13px, weight 600) and a `badge badge--{type}` whose **text is the
  provider type** (A20).
- [ ] **AC7. The body.**
  - The description, at 12px in `--fg-secondary`.
  - A `<dl>` of three rows:
    - **Model:** the `llm_model`, in mono;
    - **Provider:** the provider's **display name**, from the `providers` store;
    - **Chats:** the count of `sessions` with that `agent_name`, connector sessions
      included (DD4).
- [ ] **AC8. "What it can use"** (A13), read-only. These are a heading plus grouped lists:
  - **Knowledge bases:** the names for the agent's `kb_ids`, from `knowledge-bases`.
  - **MCP servers:** the names for `mcp_source_ids` that are in the plain `mcp-sources`
    store, with "{n} tools" where `App.usage.mcpToolCount` knows it. **Unknown ids are
    skipped**, which covers the self-configuration loopback source.
  - **Built-in tools:** the categories, each with its enabled count. Effective means
    globally enabled (one `GET /api/tools/configs` per drawer open) **and** the agent's
    `is_tool_enabled` semantics (`enabled_tools`, where `None` means all, minus
    `disabled_tools`).
  - **Self-configuration:** "On" when `GET /api/agents/{name}/self-configuration` reports
    it enabled, with one fetch per open. It returns `{enabled}` or `{enabled, source_id}`,
    and 404 for an unknown agent.
  - **The data shapes** (verified by the design review):
    - `GET /api/tools/configs` returns `[{name, description, enabled, config}]`; a missing
      row means enabled;
    - `App.usage.mcpToolCount(source)` takes the **source object**, not an id, and returns
      `null` when not loaded;
    - the `agents` list carries `enabled_tools`, `disabled_tools`, `kb_ids`,
      `mcp_source_ids` and `llm_model`, so no per-agent fetch is needed.
  - **Built-in effective logic**, reimplemented client-side for **built-ins only**:
    `(enabled_tools == null || enabled_tools.includes(name)) &&
    !disabled_tools.includes(name)`, combined with the global `enabled` flag. This matches
    `is_tool_enabled` (`config.py` around 155): `enabled_tools` gates built-ins, `mcp__`
    and `kb__` names are exempt, and `disabled_tools` is universal. A test pins the
    parity.
  - An empty group says "None".
  - A fetch failure shows "Couldn't load" for that group only.
- [ ] **AC9. One category table.** `static/js/tool-categories.js` (new) exports
  `App.toolCategories` with **every derived shape**:
  - `byCategory`, title-cased category → names, the `studio.js` around 460 shape;
  - `categoryOf`, tool → lowercase category, the `tools-grid.js:19` and
    `tools-editor.js:81` shape;
  - `order` and `labels`, from `tools-grid.js` around 50.

  So migrating the three copies is mechanical, and they **all** read it. Studio's
  `toolCategories` callback (`studio.js` around 2712 → `tools-tab.js:37`) keeps its
  shape. The script tag loads **before** `studio.js` and `admin/tools-*`.
  - **Completeness** (question 3). The table lists **every** tool in
    `the_one/tools/builtins.py::_TOOL_CLASSES`, including M23 F4 L3's connector lookup
    tool, which is checked against the current tables. A static unit test parses
    `_TOOL_CLASSES` and the JS table and asserts the same set, so a new built-in cannot be
    silently uncategorised.
- [ ] **AC10. The footer.** **Open agent settings** (`btn-outlined-primary`, the gear
  icon, testid `chat-drawer-settings-link`).
  - It runs `App.router.go(App.router.href({destination:'agents', id: name}))`.
  - On a commit, `App.studio.clearAgentFilter()` clears the Agents filter (§10 item 18).
- [ ] **AC11. Synthetic default, deleted agent, and loading.** There are three explicit
  states:
  - **A null or `"default"` agent** not in the `agents` store: "Default agent", with the
    text "The default agent" and **no** settings link.
  - **A name not in a *loaded* `agents` store:** the stored name, with "This agent no
    longer exists" and **no** settings link.
  - **The `agents` store not yet loaded:** a neutral loading state, **never** "deleted".

  The drawer subscribes to `agents`, `providers`, `knowledge-bases`, `mcp-sources` and
  `sessions`, re-rendering on each, and **unsubscribes on destroy**.
- [ ] **AC12. `listPane.setQuery(q)`.**
  - It sets `filterInput.value = q; query = q; applyView()` and is **silent**: no live
    announcement (question 4). It applies the view without rebuilding rows, which
    re-derives the selection and the tab stop. It is a no-op without a filter.
  - A `listPane` contract test is added, in both engines.
  - **`App.studio.clearAgentFilter()`** is defined at script load: a stub that is a safe
    no-op until studio's init runs, then calls `setQuery('')` on the Agents pane if one
    exists.
    - The pane survives a visit to Chats, because only `setActiveSection` destroys it
      (`studio.js` around 1798–1802), on Agents to Library.
    - **Timing.** It runs after `go()` commits. A test asserts the selected row is visible
      and scrolled into view after the clear.

**C. The agent editor's Chat (DD8).**

- [ ] **AC13. Chat.** An `App.ui.button` in the outlined variant, labelled "Chat" (testid
  `agent-chat-btn`, registered), is inserted with DOM APIs into the agent editor header's
  `.form-actions`, before Cancel. That happens in `renderAgentEditor` (`agent-editor.js`
  around 85–161), where `isCreate` is in scope, so it is **not inserted in create mode**.
  - It takes no part in `checkDirty`'s Save/Cancel bookkeeping.
  - It is re-created on every header render, so there is no stale handler.
  - It runs `App.router.go(App.router.href({destination:'chats', create:true, agent:
    name}))`.
  - It is **hidden in create mode**.
  - From a **dirty** editor it asks once. Stay keeps the edit; Continue lands on
    `#chats/~new/{name}` with the pending chat. A test pins both.
- [ ] **AC14. Squawk 0118.** `the_one/agents.md` gains an "Editor Save/Cancel contract"
  block:
  - **Create mode:** Cancel is always enabled; Save is enabled once valid.
  - **Edit mode:** Save and Cancel are enabled only while dirty; the caption shows only
    while dirty.
  - **Focus:** the DD8 focus rule (the item's row, else the neighbour, else the primary
    action).
  - **The save-create staleness guard:** `stillOnCreate`/`createGen`.
  - It cites the **grep-derived** `checkDirty` sites (`studio.js`, `agent-editor.js`,
    `mcp-server-editor.js`, `provider-editor.js`, `tools-editor.js`,
    `knowledge-section.js`). `stillOnCreate`/`createGen` are in `studio.js`. The single
    studio `dirty` flag stays.
  - The block's home is `the_one/agents.md`, beside "Agents list and detail" (around
    1853). The drawer slot goes into "App shell — invariants" (around 1845).
  - The squawk file is closed, with the sign-off at the flight review.

**D. Tests, gates and docs.**

- [ ] **AC15. Flow tests** (chats and agents lanes):
  - `test_flow_chat_drawer.py`:
    - the default push at 1440 and overlay at 1024;
    - the toggle and `aria-pressed`;
    - Escape;
    - the facts, with the provider name and the chats count;
    - what it can use, with the knowledge base and the MCP server, the self-config source
      skipped, and the built-in categories;
    - Open agent settings with the filter cleared;
    - a deleted agent shows no link;
    - persistence across a reload.
  - `test_agents_chat_action.py`: Chat from a clean and from a dirty editor, and hidden in
    create mode.
- [ ] **AC16. Accessibility.**
  - The resolver probe on `#chats` with the drawer open finds no unnamed control and no
    dangling `aria-controls`.
  - The landmarks are `main`, the "This chat's agent" complementary landmark, the nav, and
    the sidebar aside.
  - The drawer's text pairs on `--surface` pass AA, and are gated where they are new.
- [ ] **AC17. Gates.**
  - `make lint` and format;
  - the static guards (UI guards, tokens, contrast, inventory, nav helper, store static,
    index pin);
  - `make test-unit`;
  - the lanes `contracts` (`THE_ONE_REQUIRE_WEBKIT=1`), `chats`, `agents`, `settings`
    (if the tool tables moved) and `shared` (`TEST_TIMEOUT=3600`), through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`.
  - The numbers go in the flight log.
- [ ] **AC18. Docs.**
  - `CLAUDE.md`: a sentence in the Chats paragraph on the drawer and `chat-drawer*`, and
    on `agent-chat-btn`.
  - `the_one/agents.md`: the drawer contract and the editor contract (AC14).
  - The inventory and the registry.

## Verification Steps

- The lanes and guards in AC17.
- **A manual pass** at 1440 and 1024, in Light and Dark, on a dev instance (port 8486 or
  higher, scratch data dir, seeded with an agent that has a knowledge base, an MCP
  server, self-configuration and disabled tools).
- **Falsify once:** make the drawer remove itself from the DOM when there is no chat, and
  watch the `aria-controls` resolver test fail.

## Edge Cases

- **Opening the drawer in `pending`:** it shows the pending agent's details, and Chats is
  0 if there are no sessions yet.
- **The agent is renamed while the drawer is open:** the next store notification
  re-renders it.
- **Narrow overlay at 1024:** it may cover Send. This is accepted, and is a DD13 preview
  question.

## Files Affected

- New:
  - `static/js/ui/drawer.js`;
  - `static/js/tool-categories.js`;
  - `areas/chat/agent-drawer.js`;
  - a design-language drawer section;
  - `tests/browser/test_ui_drawer_contract.py`, `test_flow_chat_drawer.py` and
    `test_agents_chat_action.py`.
- Changed:
  - `static/js/ui/list-pane.js` (`setQuery`);
  - `areas/studio.js` (`clearAgentFilter`, and the category table if migrated);
  - `areas/studio/agent-editor.js`, or the studio render site (the Chat button);
  - `areas/chat.js` and the pane module (the toggle);
  - `areas/admin/tools-grid.js` and `tools-editor.js` (if migrated);
  - `index.html` (the static `#chat-drawer` slot, and the `drawer.js`,
    `tool-categories.js` and `agent-drawer.js` tags in order);
  - `css/components.css`, `css/chat.css` and `css/base.css`;
  - `js/icons.js`: add `panel-right` and `settings`. Neither exists yet.
  - `tests/browser/test_shell_rail.py`, the shell-row children.
- Docs: `CLAUDE.md`, `the_one/agents.md`, `docs/ui-control-inventory.md`,
  `docs/ui-testid-registry.md` and `squawks/0118-…`.
