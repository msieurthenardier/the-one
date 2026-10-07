# Leg: root-pages

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

Replace the one-line empty states at the Agents root and the Library section roots with
start pages that explain what lives there (flight DD15):
- **Agents:** what an agent is, and New agent;
- **Library:** one block per type (Knowledge bases, MCP servers, Connectors), each with a
  description and its own Add button.

**Rider: squawk 0126.** The connector editor's title keeps the old name after a rename.
It sits in the same Library editors, so this leg completes it too (see the last
Acceptance Criterion).

## Context

- **The operator's reports** (2026-10-06):
  - "on the library main page...it just says select a kb or add one. Instead, it should
    be a description of what each of the things are with an add button for each of
    them."
  - "similarly we should add a friendly description to the agents base page including
    what agents are."
- **Today's Agents root.** `studio.js` `renderAgentsEmpty()` (about line 2494) builds an
  `App.ui.emptyState` (pane size, `h2`). There are two copies:
  - with agents: "Select an agent to edit it, or create a new one." (`agent-select-empty`);
  - with none: "No agents yet. Create one to get started." (`agent-empty`).

  Both carry a New agent button (`agent-empty-new`, `goCreateAgent`). The node is
  inserted at the top of `sectionContentEl`, and only its own node is ever replaced,
  because the `loadAll` failure line lives in `sectionContentEl` too.
- **Today's Library roots.** `studio.js` `renderLibraryEmpty(section)` (about line 923)
  builds one `App.ui.emptyState` per section from `LIBRARY_EMPTY` (about line 532):
  "Select a knowledge base, or add one." and so on, with
  `library-empty-{knowledge|mcp|connectors}` and an Add button
  `library-empty-{id}-add` (`goLibraryCreate(group.route, opener)`).
  - Bare `#library` redirects to `#library/knowledge` (`router.js`, the destination's
    `root`), so that is the "main page".
  - `LIBRARY_GROUPS` (about line 518) already carries each type's label and icon
    (`database`, `server`, `plug`).
- **The root heading (DD11, leg 1a).** `buildRootHeading(text)` (about line 914) makes a
  visually hidden `h1[data-testid=root-heading]`.
  - For Library, `renderLibraryEmpty` builds it.
  - For Agents, `updateContentVisibility` syncs it (about line 1846).
  - It is absent while an editor is open, where `.editor-title` is the only `h1`.
  - DD15 makes it **visible** on these pages: it becomes the page title. It **stays the
    existing sibling node** (design review cycle 1). For Agents it exists before the first
    load and through a `loadAll` failure, and moving it inside the page node would lose
    that.
- **The Library list column's own intro** (`studio.js` about line 828): "Things agents can
  use. Attach them from an agent's Knowledge and MCPs tabs." The page's intro must not
  repeat it, so an Executor matching text finds one node.
- **Not `.page-header`.** `system-page.js` `renderPage` builds `div.page-header >
  h1.page-title` (`.page-header` is shared in `components.css`, about line 1182), but
  `test_flow_studio_library_list.py` (about lines 631–636) asserts that a Library root has
  **no** `.studio-section-content .page-header`. Keep that assertion, and use the start
  page's own classes (`.start-page`, `.start-page-title`).
- **The contract** (DD15): the testids above are kept, and only the copy changes.
  - The Library page shows at every section root, with the container's
    `library-empty-{section}` keyed by the **route's** section.
  - Every type's Add button keeps `library-empty-{id}-add`. So at `#library/mcp` the
    page is `library-empty-mcp`, and it holds `library-empty-knowledge-add`,
    `library-empty-mcp-add` and `library-empty-connectors-add`.
- **Leg 4 (section labels)** restyles `.section-title`. The block titles here are not
  section labels. They are `h2` card titles; see the Acceptance Criteria.

## Acceptance Criteria

- [ ] **The Agents page** (`#agents` with no agent open):
  - **the title.** The existing `root-heading` `h1` ("Agents") becomes visible:
    `buildRootHeading` drops `visually-hidden` and takes `start-page-title`. It stays the
    sibling that `updateContentVisibility` syncs. **Do not build a second `h1`** inside
    the page node;
  - the description below it, as one or two short paragraphs (the copy below);
  - **New agent** (`agent-empty-new`, `goCreateAgent`, a primary button) after the
    description;
  - **the two variants kept** (`agent-select-empty` with agents, `agent-empty` with
    none). They differ by one line under the description: "Pick an agent from the list to
    edit it." when agents exist, and "No agents yet." when none do (the phrase
    `test_flow_agent_crud.py` pins). The testid sits on the page node, which holds
    everything but the `h1`;
  - **the existing lifetime kept.** Nothing renders before the first load, only its own
    node is replaced, and the `loadAll` failure line survives.
- [ ] **The Library page** (each of `#library/knowledge`, `#library/mcp` and
  `#library/connectors` with no item open):
  - **the title.** The existing `root-heading` sibling ("Library") becomes visible, as for
    Agents, followed by one intro line in the page node;
  - **three blocks in `LIBRARY_GROUPS` order.** Each has:
    - the type's icon (decorative, `aria-hidden`);
    - an `h2` with the type's name ("Knowledge bases", "MCP servers", "Connectors");
    - its description;
    - its Add button (`library-empty-{id}-add`, the labels kept: "Add knowledge base",
      "Add MCP server", "Add connector"), which calls `goLibraryCreate` exactly as today
      and passes itself as the opener;
  - the container carries `library-empty-{route section}`, and the same three blocks show
    at every section root;
  - **block styling.** The blocks read as cards: a hairline, `--surface`, the radius
    and padding of the Settings tiles. The `h2` is a card title (body size, semibold,
    `--fg`), not a `.section-title` eyebrow;
  - **layout** (both pages). The page is **left-aligned** in the pane, like the Settings
    pages, with the pane's padding. The `h1` and the page node share one maximum width
    (about 720px) through one CSS rule, so the title and the cards line up at 1440. The
    cards sit in one column. Below about 560px of pane width, the Add button wraps under
    the text (CSS only). Nothing overflows at 1024;
  - **the existing lifetime kept.** It is built only at a root, never while a deep-link
    id is pending, so a cold item link never flashes it.
- [ ] **The copy.** It is plain, accurate and in sentence case. The Flight Director's
  draft follows. Adjust only for accuracy against the code (say what changed in the
  flight log); the operator reviews it in the walk.
  - **Agents:** "An agent is an assistant you set up for a kind of work. Each one has a
    model from one of your providers, instructions that shape how it behaves, and the
    tools and knowledge it can use. Chat with an agent from Chats, or connect it to a
    chat platform with a connector."
  - **Library intro:** "Add something here once, then choose which agents use it in each
    agent's settings." (This is distinct from the list column's intro.)
  - **Knowledge bases:** "Folders of your documents that agents can search. The app
    indexes the files and keeps the index current as they change. Attach a knowledge
    base to an agent on the agent's Knowledge tab."
  - **MCP servers:** "Tool servers that use the Model Context Protocol, such as a
    browser, a database or another app's API. Choose which agents get which tools on each
    agent's MCPs tab."
  - **Connectors:** "Links to chat platforms such as Discord, so people can talk to your
    agents there. Each connector routes its channels to the agents you choose."
- [ ] **Headings.** Each page has exactly one `h1` (`root-heading`, now visible, so the
  `visually-hidden` class is removed for these pages). There is still no `h1` but
  `.editor-title` while an editor is open. The Library blocks are `h2`s, and the Agents
  page has no `h2`.
- [ ] **Focus is unchanged.** Closing an item through its breadcrumb still focuses the
  item's row, and a pick from the list still opens the editor. An Add or New agent click
  opens the create form as today. Nothing on these pages takes focus on render.
- [ ] **Tests.**
  - **New** (`agents` and `library` lanes, beside the existing root tests):
    - the Agents page in both variants: the visible `h1`, the description, New agent
      opens `#agents/~new`;
    - the Library page at each section root: the visible `h1`, the three `h2`s in
      order, each Add opening its own `~new` route (one click from a non-matching root,
      for example `library-empty-connectors-add` from `#library/knowledge`);
    - no horizontal overflow at 1024;
    - the Library page still renders, all three blocks and Adds, when the three
      collection GETs fail (route them to 500).
  - **Updated in place,** each noted in the flight log:
    - `tests/browser/test_flow_agents_root_heading.py`:
      - line 36 asserts `visually-hidden`, and line 38 a width of 1px or less. Flip both
        to visible;
      - line 58 asserts `library-empty-{section} h2`, which is now three `h2`s, a strict
        mode violation;
    - `tests/browser/test_flow_studio_library_list.py`:
      - lines 618–622: the old copy;
      - line 619: `empty.locator("h2")`, now three;
      - **keep** the zero-`.page-header` assertion (lines 631–636);
    - `tests/browser/test_flow_agents_list.py` lines 338 and 352 (the old Agents copy).
      Line 357 is the list pane's own empty line, so leave it;
    - `tests/browser/test_flow_agent_crud.py` lines 54 and 137 (`"No agents yet"`), which
      stay valid with the none-variant line above. Confirm they pass;
    - `tests/browser/test_studio_connector_editor.py` line 42, and
      `tests/browser/test_flow_studio_knowledge_inventory.py` line 161;
    - any other assertion the greps find: `Select a`, `or add one`,
      `Create one to get started`, `root-heading`, `library-empty`, `agent-empty`;
    - the `_lists.py` docstrings at lines 31, 43, 199 and 224. `library_empty_state(kind)`
      still returns the route section's container, which now holds the whole start page.
      The bodies stay the same.
  - `tests/browser/test_visual_snapshots.py` (pixel, local only) uses `agent-empty`. Its
    baseline needs regenerating locally; no change.
- [ ] **Specs.** Re-author the steps that assert the old copy or a hidden root `h1`, each
  with an `Updated` line and no change to an expectation's intent:
  - `tests/behavior/list-and-detail.md`, steps 2 (leg 1a's re-author), 8, 10, 15 and 17;
  - `workbench-navigation.md`, steps 3, 4 and 8;
  - `shell-navigation-smoke.md`, steps 4 and 5;
  - `studio-agent-crud.md`, step 2 and any later step naming the old copy (grep the whole
    spec). Leave the run logs alone; they are history.

  Where a step quotes text, it names the region the text is in (the list column or the
  start page).
- [ ] **Docs.**
  - `the_one/agents.md`: "Agents list and detail" and "Library list and detail" describe
    the start pages, and DD11's root-heading note is amended.
  - `CLAUDE.md`: the leg 1a sentence ("one visually hidden `h1` (`root-heading`…)") and
    the "Agents list and detail" and "Library list and detail" paragraphs.
  - `docs/ui-testid-registry.md`: the rows for `root-heading`, `agent-select-empty`,
    `agent-empty` and `library-empty-*`.
- [ ] **Squawk 0126** (`squawks/0126-connector-title-stale-after-rename.md`):
  - the connector editor's edit-save branch sets `connTitle` from the saved row
    (`updated.name`), so the `h1` shows the new name at once;
  - a browser test (the `library` lane, beside the connector editor tests) renames a
    connector, saves, and asserts the `h1` reads the new name without re-opening;
  - check the agent, MCP and knowledge-base editors for the same gap and say what you
    found in the squawk (fix any that share it, if the fix is one line; otherwise note it);
  - complete the squawk per `.flightops/ARTIFACTS.md` (Corrective Action, Verification,
    `completed`), with the commit reference "pending the Flight 6 legs commit".
- [ ] **Gates:**
  - the static guards (`test_ui_guards.py`; a new HTML-string sink fails it, so build with
    DOM APIs), `test_token_definitions.py` and `test_design_tokens_a11y.py`;
  - `ruff`, and `TEST_TIMEOUT=3000 make test-unit`;
  - the `agents` and `library` lanes;
  - `shared` (`TEST_TIMEOUT=3600`), which holds the hash-routing, dirty-confirm and
    isolation tests that reach these pages.

  All with `THE_ONE_TEST_NETNS=1`.

## Verification Steps

- The new tests, then the lanes in the background.
- Screenshots of the Agents page (both variants) and the Library page at 1024 and 1440,
  in both themes. These are flight-log evidence only, never committed.

## Implementation Guidance

1. Read `renderAgentsEmpty`, `renderLibraryEmpty`, `buildRootHeading` and its Agents sync
   in `updateContentVisibility`, then every test and spec the greps above find.
2. Build the Agents page, then the Library page, with DOM APIs (`App.ui.util.el`,
   `App.ui.button`, `App.ui.util.icon`). Keep the testids and the lifetimes. Add no
   `innerHTML` writes; `studio.js` has a frozen sink baseline in `test_ui_guards.py`.
3. CSS in `studio.css` (or `components.css` if shared), using tokens only.
4. The new tests, then the pins.
5. The specs and docs.
6. The lanes; then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A failed agents load.** The `loadAll` failure line still shows, and the page follows
  the existing rule (nothing before the first load).
- **A Library collection that fails to load:** the start page still shows. Its blocks
  depend on no collection.
- **A dev-mode stub connector type:** the Connectors copy names Discord "such as", so it
  stays true.
- **A narrow pane** (1024 with the 300px list): the blocks stack, and the buttons wrap
  under the text rather than overflow.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (squawk 0126).
- `the_one/interfaces/web/static/js/areas/studio.js` (`renderAgentsEmpty`,
  `renderLibraryEmpty`, `buildRootHeading` and its sync), `css/studio.css`.
- Tests: `test_flow_agents_root_heading.py` and the copy pins above, plus new tests in the
  `agents` and `library` lanes.
- Specs: `list-and-detail`, `shell-navigation-smoke`, `workbench-navigation`,
  `studio-agent-crud`.
- `the_one/agents.md`, `CLAUDE.md`, `docs/ui-testid-registry.md`; the flight log.

## Citation Audit

Checked on 2026-10-06 in the working tree (with leg 1a landed):
- **`studio.js`:** `LIBRARY_GROUPS` (line 518), `LIBRARY_EMPTY` (line 532),
  `buildRootHeading` (line 914), `renderLibraryEmpty` (line 923), the Agents root-heading
  sync (line 1846), `renderAgentsEmpty` (line 2494).
- **`system-page.js`:** `renderPage` (line 21).
- **`components.css`:** `.page-header` (line 1182).
- **`studio.js`:** the Library list's intro (line 828).
- **Tests:** `test_flow_agents_root_heading.py` lines 36, 38 and 58; `test_flow_agent_crud.py`
  lines 54 and 137; `test_flow_agents_list.py` lines 338, 352 and 357;
  `test_flow_studio_library_list.py` lines 631–636;
  `test_flow_studio_knowledge_inventory.py` line 161; `test_flow_studio_library_list.py`
  lines 618–622; `test_studio_connector_editor.py` line 42; `_lists.py` lines 199 and 224.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
