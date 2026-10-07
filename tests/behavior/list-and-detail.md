# Behavior Test: List and Detail — Agents list, Library groups, Settings nav and items

**Slug**: `list-and-detail`
**Status**: active
**Created**: 2026-10-02
**Updated**: 2026-10-06 (steps 2, 8, 10, 15 and 17: the Agents and Library start pages, M25 F6 leg 4c); 2026-10-06 (step 2: the visually hidden root `h1`, M25 F6 leg 1a); 2026-10-05 (step 20: Providers tiles, M25 F3 leg 7)
**Last Run**: 2026-10-05-14-53-19 (targeted re-run after leg 7, steps 18 and 20 in both themes: 4/4 pass); full run 2026-10-02-12-08-59 (38/38; see runs/)

## Intent

Verify the Mission 25 Flight 3 list-and-detail shell end to end, against a live instance
seeded with a realistically long list.

- **Agents.** The Agents destination is a filterable, counted list beside the detail pane,
  and selection and scroll follow the open agent.
- **Library.** One grouped list with an Add menu, where creating each item type opens the
  new item.
- **Settings.** A grouped nav of links. General is split into Appearance, Prompts and
  Encryption, with redirects from the old routes, and a provider opens under the
  Providers tiles.
- **Across all three:**
  - a dirty editor asks once when the operator clicks another row;
  - Cancel on a create form returns to the destination's empty state;
  - deleting the open item returns to the empty state, with focus on a neighbouring row;
  - the breadcrumb's last segment closes the open item.

This is a behavior test, not only the Playwright suite, because the observables are the
rendered list and detail layout of a real browser: scroll position in a long list, the
Add menu's popup inside the 300px column, the dialog, and the address bar and history
across multi-step flows. It is the behavior gate for Mission 25 Flight 3, and it runs in
both themes (see Variants). It is not read-only: it creates and deletes data, all named
with the prefix `lnd-`.

## Preconditions

- **Instance under test.** A **dedicated dev instance** with a non-default port AND a
  scratch data directory together, dev mode on, and the stub connector gate open, for
  example:

  ```
  THE_ONE_PORT=8485 THE_ONE_DATA_DIR=/tmp/the-one-lnd-scratch THE_ONE_DEV_MODE=true THE_ONE_STUB_TEST_ENDPOINT=1 make up
  ```

  - Create the credential first with
    `THE_ONE_DATA_DIR=/tmp/the-one-lnd-scratch the-one rotate-api-credential`.
  - **Never** port 8484, and never the operator's default data directory (CLAUDE.md,
    "Behavior-test credential convention" safety rule).
  - The orchestrator states the actual base URL (`{base}`, default
    `http://127.0.0.1:8485`) and scratch directory at run time; both apply to every step.
- **Probes**, run immediately before the run:
  - `GET {base}/api/live` returns HTTP 200;
  - `GET {base}/api/providers/types` (with the credential) lists `mock`;
  - `GET {base}/api/connectors/types` lists `stub`.
- **Credential.**
  - Read `<scratch>/api-credential` verbatim and send it as
    `Authorization: Bearer <credential>` on every API call.
  - For the browser, mint a handoff URL with `POST {base}/api/session/handoff` and
    navigate to the URL it returns. It is single-use; mint again only for a fresh context
    or tab.
- **Clean start.** The instance holds no agent, provider, knowledge base, MCP server or
  connector named with the prefix `lnd-`. If a prior partial run left some, delete them
  before step 1.
- **Browser apparatus, in fallback order** (DD12):
  1. goldfinch MCP, if its input delivery works on the host;
  2. otherwise a headless Chromium driven over CDP with real input events. This was the
     Flight 2 and Flight 3 practice: Playwright `connect_over_cdp`, a persistent context
     created with `Target.createBrowserContext {disposeOnDetach:false}`, and the page found
     again by `window.name`.

  Concurrent Executors each use their own scratch subdirectory and script names. The run
  log states which apparatus was used.
- **Evidence notes:**
  - **Focus** is asserted as `document.activeElement` identity (tag, `data-testid`,
    `id`, text) through an eval, never as a visible ring.
  - **Dialogs** are counted with `document.querySelectorAll('dialog[open]').length`.
  - **"Fully in view"** for a list row means its bounding rect lies inside the list body's
    scroll container rect.
  - **The route announcer** is the visually hidden live region the router writes on
    every committed navigation. Read its text right after the step.
  - **Error banners.** Report only rendered ones (`offsetParent !== null`, non-empty
    text).
  - **No unrequested probes.** Never add a full-document load or any other
    history-altering probe that a step does not call for.

## Observables Required

- **browser**: the rendered rail, list column, detail pane, dialog and menu; `location.hash`;
  `history.length`; `document.activeElement`; element rects; computed styles. Measured
  through goldfinch MCP, or the CDP Chromium fallback.
- **http**: the setup and teardown API calls, and the saved-value checks. Measured
  through curl in the shell.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Seed (setup).** With the credential: POST `{base}/api/providers` with `{"name":"lnd-mock-a","type":"mock","base_url":"","config":{"models":["mock-default"]}}`, then `{"name":"lnd-mock-b","type":"mock","base_url":"","config":{"models":["mock-alt"]}}`, keeping both ids (`{provA}`, `{provB}`). POST `{base}/api/knowledge-bases` `{"name":"lnd-kb-alpha"}`, keeping `{kbAlpha}`. POST `{base}/api/agents` 30 times for `lnd-agent-01` … `lnd-agent-30` (zero-padded), each `{"name":"lnd-agent-NN","provider_config_id":"{provA}","llm_model":"mock-default","system_prompt":"mock"}`, where `lnd-agent-01` and `lnd-agent-02` also carry `"kb_ids":["{kbAlpha}"]`. POST one more agent, `{"name":"lnd-zeta","provider_config_id":"{provB}","llm_model":"mock-alt","system_prompt":"mock"}`. Expect HTTP 201 for every POST. | (setup row, no judgment) |
| 2 | [Agents, nothing open]: open a fresh browser tab at 1440×900, mint and follow a handoff URL, navigate to `{base}/#agents` and reload (cold). | **Rail and address.** Hash `#agents`. Only the rail's "Agents" link has `aria-current="page"`. **List column** (the aside, 300px wide): a list titled "Agents" with the count "31 of 31", a "New" button whose accessible name is "New agent", and a filter field labelled "Filter agents" with the placeholder "Filter by name, model or provider". **Rows** are links in A–Z order: `lnd-agent-01` first … `lnd-agent-30`, then `lnd-zeta` last. Each row shows the agent's model (`mock-default`, or `mock-alt` for `lnd-zeta`) on a second line in a monospace face, and has a small provider dot before the name. **Detail pane**: the Agents start page (DD15): the visible `h1` "Agents", the description "An agent is an assistant you set up for a kind of work. …", the line "Pick an agent from the list to edit it." and a "New agent" button; no editor. **The page's one `h1`** is that visible "Agents" (it is gone once an agent opens, where the editor title is the only `h1`). No error banners. |
| 3 | [Agents, filtered]: type `zeta` into the filter. Then select-all and type `mock-alt`. Then select-all and type `nomatch-xyz`. Then clear the field. Read the count and the visible rows after each. | **`zeta`:** count "1 of 31", and only `lnd-zeta` is visible. **`mock-alt`:** count "1 of 31", only `lnd-zeta` (a model match). **`nomatch-xyz`:** count "0 of 31", no rows, and the line `No agents match "nomatch-xyz".`. **After clearing:** count "31 of 31", and all rows are back in A–Z order. The detail pane is unchanged throughout (the empty state). No error banners. |
| 4 | [Deep link into a long list]: navigate to `{base}/#agents/lnd-agent-25/general` and reload (cold). Read the row rects and the detail pane. | **Address.** The hash stays `#agents/lnd-agent-25/general`. **Selection.** The row `lnd-agent-25` has `aria-current="page"`, is the only row that does, and is **fully in view** inside the list's scroll area. The list column is still visible beside the editor. **Detail.** The `lnd-agent-25` editor with a General tab selected; above the title, the breadcrumb is a link reading "Agents"; there is exactly one `h1` in the detail pane, `lnd-agent-25`. No error banners. |
| 5 | [Clean editor] -> [dirty editor] -> row click -> Stay -> row click -> Continue: in the open editor, type `lnd-unsaved` into Description. Read the editor's actions row. Click the row `lnd-agent-03`; read the dialog and the hash; click "Stay". Click the row `lnd-agent-03` again, and click "Continue". | **After typing:** the actions row shows the status text "Unsaved changes". **After the first row click:** exactly ONE dialog is open, titled "Unsaved changes", with "Stay" and "Continue"; the hash is still `#agents/lnd-agent-25/general`. **After Stay:** no dialog; the hash is unchanged; Description still holds `lnd-unsaved`; `lnd-agent-25` is still the selected row. [a11y] **After Continue:** the hash is `#agents/lnd-agent-03/general`; the `lnd-agent-03` editor shows with an empty Description and no "Unsaved changes" text; `lnd-agent-03` is the only selected row. `GET {base}/api/agents/lnd-agent-25` returns an empty or absent `description` (nothing saved). |
| 6 | [Create form] -> Cancel: click "New". Read the hash, the detail pane and `document.activeElement`. Click "Cancel". Read the hash, the detail pane and `document.activeElement`. | **After "New":** hash `#agents/~new`; the detail pane shows the create form with an empty Name field, and `document.activeElement` is that Name field; no row is selected. **After Cancel:** no dialog appeared; hash `#agents`; the detail pane shows the empty state again; no row is selected; `document.activeElement` is a row link inside the Agents list. [a11y] |
| 7 | [Create] -> the new agent opens: click "New", type `lnd-new-agent` as the Name, choose provider `lnd-mock-a` and model `mock-default`, then Save. Read the hash, the list, the announcer and the detail. | **Address.** Hash `#agents/lnd-new-agent/general`. **List.** The count reads "32 of 32"; a row `lnd-new-agent` exists in A–Z position (after `lnd-agent-30`, before `lnd-zeta`), is the only selected row, and is in view. **Detail.** The editor shows `lnd-new-agent`, with no "Unsaved changes" text. **Announcer.** Its text names `lnd-new-agent`. No error banners. |
| 8 | [Delete the open item]: in the `lnd-new-agent` editor, use Delete and confirm it, using the two-step confirm. Read the hash, the list, the detail pane and `document.activeElement`. | **Address.** Hash `#agents`. **List.** The count reads "31 of 31", and there is no `lnd-new-agent` row. **Detail.** The Agents start page (the line "Pick an agent from the list to edit it."). **Focus.** `document.activeElement` is the row link `lnd-zeta`, the next row after the deleted one. `GET {base}/api/agents/lnd-new-agent` returns 404. [a11y] |
| 9 | [Breadcrumb close]: click the row `lnd-zeta`, then click the breadcrumb link "Agents" in its editor header. Read the hash, the detail pane and `document.activeElement`. | **After the row click:** hash `#agents/lnd-zeta/general`. **After the breadcrumb click:** no dialog (the editor is clean); hash `#agents`; the empty state; no row selected; `document.activeElement` is the row link `lnd-zeta`. [a11y] |
| 10 | [Agents] -> [Library]: click the rail's "Library" link. | **Address.** Hash `#library/knowledge`, and only "Library" is current in the rail. **List column:** <ul><li>a list titled "Library";</li><li>the intro "Things agents can use. Attach them from an agent’s Knowledge and MCPs tabs.";</li><li>an "Add" button;</li><li>three groups in this order: "Knowledge bases" (one row, `lnd-kb-alpha`, with meta "2 agents"), "MCP servers" (the line "No MCP servers yet.") and "Connectors" (the line "No connectors yet.").</li></ul> There is no "Library sections" navigation. **Detail pane.** The Library start page: the visible `h1` "Library", an intro line, and three cards in order, "Knowledge bases", "MCP servers" and "Connectors", each with a description and its own Add button ("Add knowledge base" first). No error banners. |
| 11 | [Add menu]: click "Add" and read the menu. Press Escape, and read `document.activeElement`. Then focus "Add" and press ArrowDown; read the menu and `document.activeElement`. Press Escape. | **Click.** A menu opens with three items in order: "Knowledge base", "MCP server", "Connector". Every item's rect lies wholly inside the list column (`#app-sidebar`) rect, and `document.elementFromPoint` at each item's four inset corners returns that item (nothing is clipped). **Escape:** the menu closes, and `document.activeElement` is the "Add" button. **ArrowDown:** the menu opens with `document.activeElement` on "Knowledge base". **Escape:** it closes again. [a11y] |
| 12 | [Create a knowledge base] -> it opens (squawk 0101): choose Add → "Knowledge base". Read the hash, the header and `history.length`. Click Create with the Name empty. Type `lnd-kb-beta` as the Name and click Create. Read the hash, `history.length`, the list, the announcer, the detail and `document.activeElement`. | **The form.** Hash `#library/knowledge/~new`; the breadcrumb reads "Library / Knowledge bases" (with "Knowledge bases" a link); the single `h1` is "New knowledge base". **Empty name:** the form shows "Name is required." and stays on `~new`. **After Create:** <ul><li>the hash is `#library/knowledge/{id}` for the new knowledge base, and `history.length` is unchanged since the form opened (the route was replaced);</li><li>the detail shows `lnd-kb-beta`;</li><li>in the "Knowledge bases" group, `lnd-kb-beta` sits after `lnd-kb-alpha`, is the only selected row and shows "0 agents";</li><li>the announcer's text names `lnd-kb-beta`;</li><li>`document.activeElement` is the folder-path input of the new knowledge base.</li></ul> No error banners. [a11y] |
| 13 | [Create an MCP server] -> it opens: choose Add → "MCP server". Type `lnd-mcp` as the Name, choose the Streamable HTTP transport, enter the URL `http://127.0.0.1:9/mcp`, and click Create. Wait 3 seconds. Read the hash, the list, the announcer and the detail. | **Address.** The hash goes from `#library/mcp/~new` to `#library/mcp/{id}`, without a page reload (a marker set on `window` before the step is still present). **List.** In the "MCP servers" group, `lnd-mcp` is the only selected row; its meta begins "Tools not loaded" and ends "0 agents". **Detail.** The editor shows `lnd-mcp` in edit mode, with no "Unsaved changes" text. A connection error about the unreachable URL may show inside the editor's own connection status area; that is expected and is not an error banner for this step. **Announcer.** Its text names `lnd-mcp`. |
| 14 | [Create a connector] -> it opens: choose Add → "Connector". Type `lnd-conn` as the Name, choose type `stub`, type `dummy` as the token, choose `lnd-agent-01` as the default agent, and Save. Read the hash, the list, the announcer, the token field and the detail. | **Address.** The hash goes from `#library/connectors/~new` to `#library/connectors/{id}` without a page reload. **List.** In the "Connectors" group, `lnd-conn` is the only selected row, with meta "1 agent". **Detail.** The editor stays open in edit mode (Delete is now visible), with no "Unsaved changes" text. The token field does not show `dummy`, and `dummy` appears nowhere in the page. **Announcer.** Its text names `lnd-conn`. No error banners. |
| 15 | [Create form] -> Cancel: choose Add → "Connector", type `lnd-tmp` as the Name, then click Cancel. Read the hash, the list and the detail. | **No dialog appeared** (Cancel is an explicit discard). **Address.** Hash `#library/connectors`. **Detail.** The Library start page (the detail pane, not the list column). **List.** There is no `lnd-tmp` row anywhere, and no row is selected. `GET {base}/api/connectors` lists no `lnd-tmp`. |
| 16 | [Dirty Library editor] -> row click -> Stay -> Continue: click the row `lnd-kb-beta`, change its name field to `lnd-kb-beta-x` without saving, and read the actions row. Click the row `lnd-mcp`; read the dialog; click "Stay". Click the row `lnd-mcp` again; click "Continue". | **Edit.** "Unsaved changes" shows. **First click:** exactly one "Unsaved changes" dialog; the hash stays `#library/knowledge/{id of lnd-kb-beta}`. **After Stay:** the edit is kept, and `lnd-kb-beta` stays selected. [a11y] **After Continue:** the hash is `#library/mcp/{id of lnd-mcp}`, the MCP editor shows, and `lnd-mcp` is selected. `GET {base}/api/knowledge-bases/{id}` still returns the name `lnd-kb-beta` (nothing saved). |
| 17 | [Breadcrumb close] and [delete the open item]: click the row `lnd-conn`, then click the breadcrumb link "Connectors". Read the hash, the detail and `document.activeElement`. Click the row `lnd-mcp`, then use Delete and confirm. Read the hash, the list, the detail and `document.activeElement`. | **After the breadcrumb:** hash `#library/connectors`; the Library start page in the detail pane; `document.activeElement` is the row link `lnd-conn`. [a11y] **After the delete:** <ul><li>hash `#library/mcp`;</li><li>the detail pane shows the Library start page;</li><li>the "MCP servers" group shows "No MCP servers yet.";</li><li>`document.activeElement` is the row link `lnd-conn`, the next row in list order;</li><li>`GET {base}/api/mcp-sources` lists no `lnd-mcp`.</li></ul> [a11y] |
| 18 | [Library] -> [Settings]: click the rail's "Settings" link. Then click, in turn, each link in the Settings navigation. Read the hash, the current link and the page `h1` after each. | **The rail click:** hash `#settings/appearance`, only "Settings" current in the rail. **The nav.** A navigation landmark labelled "Settings" holds the heading "Settings" and grouped links, in this order: <ul><li>"General": Appearance, Prompts, Encryption;</li><li>"Models": Providers;</li><li>"Defaults for agents": Built-in tools, Knowledge indexing;</li><li>"Developer": Design language (dev mode is on).</li></ul> **Each link** gives its hash (`#settings/appearance`, `#settings/prompts`, `#settings/encryption`, `#settings/providers`, `#settings/tools`, `#settings/knowledge-indexing`, `#settings/design-language`). That link alone has `aria-current="page"`, and the page shows exactly one `h1` with the link's label. Appearance shows the theme control, Prompts the base prompt, and Encryption the rotate-key control. No error banners. |
| 19 | **Redirects.** Load `{base}/#settings/general` **as a new document** (navigate from `about:blank` or a fresh tab; an in-app hash change is redirected by the router before any reload, so it does not test the cold boot), then reload; read the hash. Do the same for `{base}/#admin/system`. | Each lands on `#settings/appearance`, rewritten in the address bar, with "Appearance" current and its `h1` "Appearance". Neither leaves the old form in the address bar. No error banners. |
| 20 | [Providers tiles] -> [provider item under the tiles]: click "Providers" in the Settings nav. Read the tiles. Click the name `lnd-mock-b` on its tile. Read the hash, the tiles, the item, the breadcrumb and `document.activeElement`. Then click the breadcrumb link "Providers". | **The tiles** (Mission 25 Flight 3 leg 7, by the operator's checkpoint decision): a grid of provider tiles, a list labelled "Providers", with no table. The `lnd-mock-a` tile shows the type badge `mock` and "30 agents"; the `lnd-mock-b` tile shows "1 agent". **After the name click:** <ul><li>the hash is `#settings/providers/{provB}`;</li><li>the tiles are still visible above, with the `lnd-mock-b` tile marked current (the selected treatment, and `aria-current="page"` on its link alone);</li><li>the provider editor renders below the tiles, with the breadcrumb "Settings / Providers" ("Providers" a link) above its title `lnd-mock-b`, an `h2`. The page keeps exactly one `h1`, "Providers";</li><li>`document.activeElement` is that `h2` title;</li><li>there is no Back button.</li></ul> **After the breadcrumb:** hash `#settings/providers`; no editor under the tiles; focus on the `lnd-mock-b` name link. [a11y] |
| 21 | **Teardown (setup row).** With the credential, DELETE every `lnd-` item: <ul><li>the connector `lnd-conn`;</li><li>the knowledge bases `lnd-kb-alpha` and `lnd-kb-beta`;</li><li>the agents `lnd-agent-01` … `lnd-agent-30` and `lnd-zeta`;</li><li>the providers `{provA}` and `{provB}`.</li></ul> Then close the tab. Confirm each list endpoint shows no `lnd-` names. | (setup row, no judgment) |

## Out of Scope

- **Rail, routes, history and the leave guard across destinations:**
  `workbench-navigation`. **Rail smoke and cold deep links:** `shell-navigation-smoke`.
- **Agent save, rename and tab round-trips:** `studio-agent-crud`. **Provider CRUD and
  OAuth:** `system-provider-config`, `anthropic-plan-signin`.
- **Knowledge-base folders, indexing and search:** `kb-studio-round-trip`,
  `kb-folder-index-round-trip`. **The connector pairing and reply loop:**
  `stub-connector-round-trip`.
- **Covered by Playwright:**
  - Built-in tools items under the tool list; the Library list's loading and failure
    states;
  - list-pane keyboard roving, focus rings, and the 1024×768 layout gates — the contract
    and lane tests (`test_ui_library_contract`, `test_flow_agents_scale`,
    `test_flow_studio_library_list`, `test_flow_admin_settings_nav`).
- **Later flights:** the Jump-to palette and workbench tabs (Flight 4); window chrome
  (Flight 5).

## Variants

- **Theme.** Run the step table twice: once with the theme explicitly **Light**, once
  explicitly **Dark**.
  - **Switching.** Switch through Settings › Appearance **before step 2** of each
    variant: click the radiogroup option, then confirm its `aria-checked="true"` and the
    document's `data-theme`.
  - **Restoring.** Record the operator's original option before the first switch, and
    restore it after the last variant.
  - **Seeding.** Re-seed (step 1) and tear down (step 21) per variant, or seed once and
    tear down once, as long as no `lnd-` items remain at the end.
  - **In both themes:**
    - the selected row's wash and the list text are legible against the column ground;
    - the dialog, the Add menu and the Providers tiles are legible;
    - the provider dots and the breadcrumb link are distinguishable from their ground.

    Evidence is screenshots, or computed colours when pixels are unavailable; the report
    says which. All route, focus and dialog expectations are identical in both themes.
