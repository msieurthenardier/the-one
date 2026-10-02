# Flight: Shell and Router

**Status**: completed
**Mission**: [Workbench Navigation and Control Library](../../mission.md)

## Contributing to Criteria

- [x] **SC1 — Workbench navigation**: the primary navigation becomes a rail with four
  destinations: Chats, Agents, Library and Settings.
  - Every existing page is reachable from one of them.
  - Every previously valid deep link, including agent editor tabs, lands on its
    equivalent.
  - *(behavior-test-backed: `workbench-navigation`, plus the updated
    `shell-navigation-smoke`)*
- [x] **SC2 — Work is never lost** (leave-guard half): leaving unsaved changes always asks
  first, by any route the browser page controls: the rail, section nav, an in-app link,
  browser Back/Forward, a typed URL, or reloading or closing the page. "Continue" really
  discards.
  - Scope: in the packaged desktop app, × hides to the tray and the page survives. Tray
    **Quit** is unguarded, and `beforeunload` may not run under pywebview. Both are
    recorded as out of scope for this flight.
  - The list/detail half of SC2 is Flight 3's.
- [x] **SC6 — Control library** (continued): the confirm dialog, the modal it is built on,
  and the rail come from the library.
- [x] **SC10 — Operable and regression-safe**:
  - the central test navigation helper;
  - lane re-mapping;
  - migration of the browser tests and the behavior specs that use the old navigation;
  - landmarks and the skip link preserved;
  - a keyboard-operable rail;
  - the four recurring lane flakes stabilised before the migration.

---

## Pre-Flight

### Objective

Replace the three-area top bar with the workbench shell, without changing what each page
shows inside it. The flight delivers:

- **Router.** One router owns the URL scheme for the four destinations, the legacy
  redirects, and a history policy in which Back steps between items.
- **Leave guard.** One leave guard covers every navigation path. Its confirm dialog moves
  onto the native-`<dialog>` modal from the library.
- **Rail.** A slim rail replaces the top bar.
- **Data layer.** A shared client data layer starts with agents and providers.

Pages move into their destinations one-to-one:

| Destination | Pages it receives |
|---|---|
| Chats | Chat |
| Agents | Studio's Agents section |
| Library | Studio's Knowledge, MCP servers and Connectors sections |
| Settings | System |

Two things land before the shell changes. Tests stop depending on the shell's markup,
through a central test navigation helper, and the known lane flakes are fixed.

### Open Questions

- [x] URL scheme → DD1
- [x] Legacy redirect table → DD2 (derived from the alias table)
- [x] Four areas vs an alias layer → DD3 (alias layer, with the studio.js changes it needs)
- [x] History policy, rail restore, URL write primitives → DD4
- [x] One leave guard; what "Continue" does; registry lifecycle → DD5
- [x] Link interception rules → DD5
- [x] Focus after Stay/Continue → DD5
- [x] Confirm dialog on native `<dialog>`; pinned-test dispositions; Enter semantics → DD6
- [x] Rail, shell layout, empty sidebar, labels and copy → DD7
- [x] Client data layer scope, copies, load state, invalidation → DD8
- [x] Test migration, flakes, lanes → DD9
- [x] Behavior specs → DD10
- [x] Squawk 0082 → DD4 (fixed by construction)
- [x] Reference-spec §15 items owned by Flight 2 → DD11
- [x] Where shell code lives → DD12

### Design Decisions

**DD1 — URL scheme: destination-first hash routes; reserved `~new` create segment.**

| Destination | Routes | Today's surface |
|---|---|---|
| Chats | `#chats`; `#chats/{sessionId}` | Chat area |
| Agents | `#agents`; `#agents/{name}`; `#agents/{name}/{tab}`; `#agents/{name}/mcps/{sourceId}` | Studio › Agents, plus the tabbed editor |
| Library | `#library` → `#library/knowledge`; `#library/knowledge[/{kbId}]`; `#library/mcp[/~new\|/{sourceId}]`; `#library/connectors` | Studio › Knowledge, MCP servers, Connectors |
| Settings | `#settings` → `#settings/general`; `#settings/general`; `#settings/providers[/~new\|/{id}]`; `#settings/tools[/{name}]`; `#settings/knowledge-indexing`; `#settings/design-language` (dev mode only) | System |

Agent editor tabs are `general`, `knowledge`, `mcps`, `tools` and `self-configuration`.

Route rules:
- **Create routes.** Create uses the reserved segment `~new`, because `new` is a legal
  agent name (`AgentConfig.name` is a free string). `#agents/~new` is reserved now and
  implemented in Flight 3. In this flight it redirects to `#agents`.
- **Encoding.** One route builder, `App.router.href({destination, section, id, tab, sub})`,
  is the single owner of `encodeURIComponent`. It is used by every link the shell or the
  areas emit.
  - It also encodes a **leading `~`** in an id or name as `%7E`. `encodeURIComponent`
    leaves `~` alone, so this is what lets an agent named `~new` never collide with the
    reserved segment.
- **Bare `#chats`** keeps today's chat behaviour: it opens the current or most recent
  session (chat.js:11-12). Flight 4 redesigns Chats.
- **No element-id collisions.** The ids `chats`, `agents`, `library` and `settings` never
  equal an element id, and a router test asserts it.

Deferred to Flight 3:
- connector item URLs (`#library/connectors/{id}`); connectors have no deep links today
  (studio.js:29-34);
- the General split into appearance, prompts and encryption;
- agent create routes.

The redirect mechanism (DD2) handles current-scheme redirects too, e.g.
`#settings/general` → the split pages in Flight 3.

**DD2 — Legacy redirects: derived from the alias table, applied with `replaceState`.**

The derivation:
- A legacy hash parses into (legacy area, sub).
- The alias table (DD3) maps (area, sub) to a new route.
- The few exceptions are explicit rows:
  - `#studio/tools` → `#agents`
  - `#admin/system` → `#settings/general`
  - `/new` → `/~new`, **only** for providers and MCP sources. `#studio/agents/new…` is
    an agent named "new" and maps to `#agents/new…`.
  - `#chat/sessions/{id}` → `#chats/{id}`

Representative mappings:

| Legacy | New |
|---|---|
| `#chat` | `#chats` |
| `#studio`, `#studio/agents` | `#agents` |
| `#studio/agents/{name}[/{tab}[/{sid}]]` | `#agents/…` |
| `#studio/knowledge[/{kbId}]` | `#library/knowledge[/…]` |
| `#studio/mcp-sources[/new\|/{id}]` | `#library/mcp[/~new\|/…]` |
| `#studio/connectors` | `#library/connectors` |
| `#admin` | `#settings/general` |
| `#admin/general` | `#settings/general` |
| `#admin/providers[/new\|/{id}]` | `#settings/providers[/~new\|/…]` |
| `#admin/tools[/{name}]` | `#settings/tools[/…]` |
| `#admin/knowledge` | `#settings/knowledge-indexing` |
| `#admin/design-language` | `#settings/design-language` |

Where the rewrite runs:
- Rewriting happens on boot and on every traversal, before the unknown-route check.
  Today app.js:191 drops unregistered areas.
- It always uses `replaceState`, so Back never bounces.

Unknown and empty hashes:
- **At boot:** an unknown or empty hash goes to `#chats`.
- **After boot:** an unknown or empty hash restores the **current route** (replace),
  instead of navigating away. A sanitised `href="#"` link or an agent-authored in-page
  anchor such as `#installation` in a chat message therefore does nothing.
- **Element ids:** a hash naming an element id (`#main-content`) is never treated as a
  route, and returning from it to the current route is a no-op.

Tests:
- A browser test walks every row of the table.
- The Python `_nav.py` mapping (DD9) is checked against the same JS table, so the two
  cannot drift. The test reads the JS table through `page.evaluate`.

**DD3 — Alias layer: four destinations over the existing three area modules.**

The data-driven destination table, `App.router.destinations`:

| Destination | Area module | Sections | Sidebar |
|---|---|---|---|
| chats | `chat` | — | yes (session list) |
| agents | `studio` | `agents` | none in this flight |
| library | `studio` | `knowledge`, `mcp-sources`, `connectors` | section nav |
| settings | `admin` | System's | section nav |

Splitting studio later is a table edit.

What stays the same:
- Panels keep their `.area-*` classes. About 600 area-scoped CSS rules depend on them;
  `admin.css` has 141.
- `App.areas` keeps its shape. Tests depend on it (test_studio_mcps_tab.py:433-455,
  test_oauth_modal_flow.py:54-55).

Required studio.js changes (the review traced a reachable cross-destination leak):
- (a) **Outgoing-section cleanup moves into `setActiveSection`, with the previous
  section captured correctly.**
  - **The cleanup.** It lives today in the section-nav `commit()` (studio.js:395-445):
    clearing `_selectedAgent`, form mode, KB, MCP and connector editor state, and
    stopping polls. Moving it lets section nav, `hydrateState` and destination switches
    share one path.
  - **Capture the previous section first.** `hydrateState` assigns
    `this._activeSection = section` *before* calling `_setActiveSection`
    (studio.js:169, :184). Inside, `prevSection === section`, so cleanup would never run
    on the hydrate path. The comment at :1100-1104 is wrong. `prevSection` is therefore
    captured before assignment, or passed in.
  - **Same-section branch.** `commit()`'s same-section branch (studio.js:421-444)
    re-renders the section root and closes the open item, and it moves with the
    cleanup.
  - **`doSelect` stale-then guard.** `doSelect` gains a check: an in-flight select that
    completes after the user has left the agents section (studio.js:1847-1858) is
    discarded, not applied.
- (b) **`_refresh` re-selects only on the Agents section.** It re-selects an agent only
  when `_activeSection === 'agents'` (studio.js:2938-2948).
- (c) **The section nav is rendered per destination.** `renderSectionNav` is
  single-mount, and its roving array includes hidden buttons (section-nav.js:21-24,
  88-104), so items are not hidden but rebuilt. The labels become "Library sections" and
  "Settings sections".
- (d) **Studio URL writes map through the alias table.** Every one goes through
  `App.router.sync('studio', sub)` (DD4), which maps `knowledge…` → `library/knowledge…`,
  `mcp-sources…` → `library/mcp…` and `agents…` → `agents…`.

A regression test walks Agents (open an item) → Library → Chats → Library. It asserts:
- the user stays in Library;
- `App.studio`'s `_selectedAgent === null` and `_mcpSourceFormMode === null`;
- no agent request is re-issued.

**Section-root routes render exactly the root (all areas).** `hydrateState(sub)` renders
exactly `sub`. A section-root route (`#settings/providers`, `#library/mcp`, `#agents`)
closes any open item or create form, including URL-less ones: connector edit and create,
and agent create.
- **Admin.** Today admin's `_setCategory` is a no-op when the category is unchanged
  (admin.js:664-680), and serialize-after-hydrate rewrites the URL back to the open
  item. That is fixed here.
- **`go()` and equal routes.** `go()` does **not** skip a route equal to the current one
  while a URL-less item or create form is open.
- **Clean Back tests.** Clean (not dirty) Back from an item to its list is tested for
  Settings › Providers and Library › MCP.
- **Deleted items.** An item route whose item no longer exists (Back into a deleted
  provider or MCP source) `sync`s to the section root. A dead pending id is never kept
  (admin.js:15-18, studio.js:44-48).

**DD4 — Two URL primitives; Back steps between items; the rail restores.**

`App.router.go(route, {replace, bypassGuard}) → Promise<boolean>` is for **user
intents**: rail, links, item clicks, section nav, Back/Cancel buttons and palette picks.
- It runs the leave guard (DD5) unless `bypassGuard` is set.
- It writes the URL (push, or replace) and hydrates the target through the areas'
  existing `hydrateState` deep-link paths.
- It resolves `true` if the user navigated and `false` if they stayed.
- **Item opens are `go()` calls made at the intent site.** That is where push is decided.
  Async completions such as `doSelect`'s URL write, chat's `session_joined`, and
  reconnect re-selects never push.

`App.router.sync(areaId, sub)` is for **area-internal canonicalisation**: tab switches,
the MCP source focus, default sub-routes, `doSelect` completing, `session_joined`, and
filter state.
- It maps (area, sub) to a route through the alias table.
- It always uses `replaceState`. It never guards and never hydrates.
- It is **dropped** when the mapped route's destination is not the current destination,
  **or** while a leave decision is pending, **or** whenever `location.hash` differs from
  the router's current URL (a traversal landed but is not yet committed).
  - So a background write, such as chat's reconnect auto-join while the user is in
    Settings, can never move the user or overwrite a traversal's target entry.
  - The router **commits the new current route before** calling `activate`/`hydrateState`
    (app.js:148 is the precedent), so legitimate syncs during hydrate are kept.
- The 28 `App.router.replaceSub` call sites are each assigned one disposition, listed in
  a per-site table that the router leg produces:
  - intent `go()`, push;
  - bypass `go({bypassGuard})`, push or replace;
  - `sync`;
  - delete.

  Item selection and Back/Cancel become intent `go()`. Post-save, post-delete and the
  KB-404 bounce become bypass `go()`. Canonicalisation becomes `sync`.
  `replaceSub` is then removed.

**History state.** Every router write stamps `history.state = {seq}`. A `replace` keeps
the entry's seq. At boot, the router adopts `history.state.seq` (it survives a reload),
or stamps one.
- **Stay after a traversal.** The router reverts with `history.go(-delta)`.
  - `delta` is computed from the **live** `history.state` at the moment of decision,
    because more traversals may arrive while the dialog is open.
  - If the state is `null` (a typed URL), it falls back to re-pushing the stayed route.
  - The revert fires its own `popstate`. A `popstate` whose URL equals the router's
    current route is a no-op, which generalises the element-id rule.
- **Continue after a traversal** does not push, because the URL is already there.
  It hydrates the **latest** location.
- **Concurrent `go()`.** A `go()` issued while a decision is pending **joins** it, and
  the latest target wins. All joined promises resolve with the same outcome.

**Traversal events.** `popstate` is the single authoritative traversal event.
- A fragment navigation fires `popstate` synchronously and queues `hashchange` as a
  later task. The router therefore drops a `hashchange` whose URL equals the URL last
  handled by `popstate`, and handles any other `hashchange` as a traversal.
- The router leg proves, in Chromium and WebKit, that `popstate` fires for:
  - Back/Forward;
  - a typed hash (`page.goto` with only a fragment change);
  - an `<a href="#…">` click that slipped past interception.
- De-duplication keys on "the URL being handled", not on the router's current route.

Squawk 0082, `replaceSub` leaving `currentSub` stale, is fixed by construction: the
router's current route updates on every write. The stale-rollback bug goes with it.

**Rail restore and bare routes.**
- Each **non-current** rail link's `href` is its destination's last-visited route, kept
  in memory for the session.
- The **current** destination's link `href` is always its **root**. Every router write
  updates it, so a click on the current item goes to the root, as the top bar does
  today. The rail still needs no click handler.
- A typed or bare `#agents` shows the root.
- This reverses the M10 F6 L7 "return to the listing" contract for *other-destination*
  clicks. The authority is reference board B3 §10 item 2: each destination keeps its
  selection.
- Pinned tests that are **inverted or renamed** (rename over delete):
  - `test_flow_hash_routing.py:209-265` (history growth);
  - `test_flow_studio_navigation.py:247-278` (other-destination restore).
- Pinned tests that **keep their behaviour** and become legacy-redirect tests:
  - `test_flow_admin_navigation.py:34-46` (a current-destination click goes to General);
  - `test_flow_hash_routing.py:148-166` (`#studio` → Agents).

**Chats history.** Clicking a session row in the chat sidebar is an intent `go('#chats/{id}')`,
pushed (DD5 path 4). The join completion (`session_joined`) only `sync`s.

**DD5 — One leave guard: per-area dirty sources, a teardown "discard", every path
routed.**

`App.nav` lives in `static/js/nav.js`, loaded after `app.js` and the router.
- **Sources.** Each area that owns editors registers **one** dirty source:
  `App.nav.registerSource(areaId, {isDirty, discard})`.
  - Studio and admin already keep one shared `dirty` closure across their editors
    (studio.js:238, admin.js:153), and the editor trackers already bridge into it. That
    stays: the six trackers and the agent tracker keep their logic.
  - Their `isDirty` is `dirty && editorOpen()`, which ports today's `inEditor` predicate
    (studio.js:2966-2967, admin equivalent) and extends it with the create modes
    (`_createMode`, MCP and connector create, provider create). A stale `dirty` left
    behind by an exit that didn't reset it can therefore never raise a phantom
    "Unsaved changes" or `beforeunload` prompt.
  - The connector editor's one-way `markDirty` is acceptable: dirty until discarded or
    saved.
  - Chat registers no source.
- **Discard means teardown to "no item open".** It clears form mode and the selection,
  resets `dirty` and stops polls, like the existing `doHandleBack` bodies minus their URL
  writes. It is never "re-render from saved state", which is async and unsafe. A later
  restore (rail href, Back) re-opens the item fresh from the server.
- **Liveness.** Registration is per area and lives as long as the page, so there are no
  per-editor entries and no unregister. Re-registering an id replaces it.
- **`App.nav.confirmLeave(context) → Promise<boolean>`.**
  - It is **single-flight**: a second request while a decision is pending joins the
    pending one.
  - If any source is dirty, it opens the confirm dialog with today's copy: "Unsaved
    changes", Stay and Continue, default focus Stay.
  - Continue calls each dirty source's `discard()` and resolves `true`. Stay resolves
    `false`.

Paths:
1. **Rail.** Plain `<a href>` links handled by the interceptor below. The rail has no
   click handler of its own.
2. **Section nav** in each destination: `go()`.
3. **In-app hash links.** A **bubble-phase** document `click` interceptor on
   `a[href^="#"]` is the single navigation path for same-document links. It is also what
   Flight 3's list-pane rows rely on. In the bubble phase, a target handler's
   `preventDefault` is visible to it.
   - It **skips** clicks with modifiers (ctrl, meta, shift, alt), non-primary buttons,
     `target`, `download` and `defaultPrevented`.
   - It routes a recognised route, legacy or new, through `go()`, with the matched `<a>`
     as the opener.
   - It lets an existing element-id fragment (`#main-content`) through.
   - It `preventDefault`s every other `#…`: a bare `#`, or an unknown fragment such as
     `#installation` from an agent-authored link. This leaves no dead history entry.
   - In-app hrefs are rewritten to the new scheme with `App.router.href`: knowledge-tab.js:93,
     mcps-tab.js:76 and :590, welcome.js:9 and :32-42.
4. **Item selection** (agent tile, KB tile, MCP/provider/tool rows): `go()`.
5. **Editor Back/Cancel that leaves an editor**: `go()`.
   - Create-mode **Cancel** means "abandon this new item" and stays **unguarded**,
     consistently for the provider, MCP, connector and agent create forms.
   - Leaving a dirty create form any other way *is* guarded.
6. **Browser Back/Forward and typed URLs**: `popstate` → guard → Stay reverts (DD4).
7. **Reload and close** (`beforeunload`): one listener that prompts if any source is dirty.
8. **Background navigations bypass the guard** (`bypassGuard`), and each one calls the
   area source's `discard()` for the item it leaves:
   - the KB-404 bounce in the KB poll (studio.js:683-692);
   - save→delete race fallbacks;
   - post-save and post-delete navigation.

Removed: the per-orchestrator gate copies.
- the `_confirmLeaveImpl`s (admin.js:664-673, studio.js:2965-2985);
- the per-orchestrator `beforeunload` (admin.js:213-219, studio.js:309-315);
- the area `confirmLeave` hooks;
- the inline `App.confirmDialog` gate calls at the 11 guard sites.

Editor tab switches inside one agent stay unguarded, since the form state persists across
tabs (studio.js:1928-1931). This is documented.

Focus:
- The guard dialog's opener resolves in this order: an explicit opener, then the event's
  `currentTarget`, then the active element (if it is not `body`), then `#main-content`.
- On **Stay**, focus returns to the opener.
- On **Continue**, focus moves to the new view's `<main>`, which already has
  `tabindex=-1`.

**DD6 — Confirm dialog on a library modal (native `<dialog>`).**

New factory `App.ui.modal({title, body, actions, opener, dismissible, testid})` in
`ui/modal.js`. It follows the full "Adding a factory" checklist: inventory row,
`data-ui-demo` demo, contract tests in both engines, and registry rows. It implements F1
DD8:

**F1 DD8 behaviour:**
- `showModal()` with an explicit opener, and explicit focus on open (the declared
  default button);
- Escape on `keydown` with `preventDefault()` + `stopPropagation()`, closing only the
  topmost dialog;
- `cancel` routed through the same path;
- a `close` listener that **ignores a stale `close` event while `dlg.open` is true**;
- a backdrop click closes only when `dismissible`.

**Beyond DD8:**
- **Tab wrap.** A manual Tab/Shift+Tab wrap inside the dialog, because native modals let
  Tab escape to browser chrome (F1 L2 finding).
- **Removal.** The `<dialog>` element is removed from the DOM on close.
- **Attributes.** `role="dialog"` and `aria-modal="true"` are set explicitly, along with
  `aria-labelledby`/`aria-describedby` wired to the title and body.
  `test_modal_aria_contract` (test_flow_dirty_confirm.py:374) asserts all four.
- **Styling.** `.modal-overlay` (components.css:1354) is a fixed full-screen overlay
  today. On the `<dialog>` it is restyled so the element fills the viewport and the
  inner `.modal-dialog` is the visible card. Backdrop-click detection compares the
  click target with the `<dialog>` element, so the restyle is load-bearing and is
  tested.

`App.confirmDialog` keeps its API and becomes a thin adapter over `App.ui.modal`:
- The `confirm-dialog-overlay` test id moves to the `<dialog>`. `modal-cancel-btn` and
  `modal-confirm-btn` stay.
- The `.modal-overlay` and `.modal-dialog` classes stay on the corresponding elements, so
  class-based tests and CSS keep matching.
- There is no singleton: a second call stacks above the first.
- **Enter** follows native semantics: it activates the focused button, which is Stay by
  default. Today's document-capture "Enter fires Continue" handler is **removed**, because
  once Continue discards, Enter on a visibly focused Stay would destroy work.

Pinned-test dispositions (rename over delete):

| Test | Disposition |
|---|---|
| `test_flow_dirty_confirm.py::test_singleton_modal_second_call_warns` (:485) | inverted → `test_second_confirm_stacks_above_first` |
| `test_modal_focus_trap_tab_cycles_forward` / `…_shift_tab_cycles_backward` (:269, :297) | kept (manual wrap) |
| `test_modal_enter_confirms` (:341) and `test_flow_provider_dirty_confirm.py::test_dialog_enter_confirms` (:219) | inverted → `…_enter_activates_focused_stay` |
| `.modal-overlay` selector (test_flow_studio_mcp_editor.py:252) | kept (class retained) |
| `to_have_count(0)` after close | kept (element removed) |
| `aria-modal="true"` (test_flow_dirty_confirm.py:374) | kept |

Also: F1's reusable DD8 checks (`tests/browser/_dialog_rule_checks.py`) gain an adapter for
`App.ui.modal` and run against it in both engines. Of today's 12 call sites, 11 are guard
sites that DD5 replaces with `App.nav`, so only the design-language modal demo stays a
direct caller.

**DD7 — Rail and shell layout.**

The rail factory: `App.ui.rail({items, currentId})` in `ui/rail.js`, returning
`{el, setCurrent(id), setHref(id, href)}`.
- **Structure.** `<nav class="ui-rail" aria-label="Main">`. The brand mark is the
  existing 24px asset, shown at 24px; the 28px on the board would be a non-integer
  pixel-art scale. Four `<a>` items, each an icon plus a label.
- **Geometry** comes from the reference spec (§2): rail 72px, item 60px wide, icon 18px,
  label `--font-size-tiny`.
- **Selection.** The current item has `aria-current="page"` and the DD14 marker (wash
  plus inset ring).
- **Keyboard.** Roving focus with a **single tab stop**, ArrowUp/Down, clamped. This
  matches `listPane`.
- **Test ids:** `rail-chats`, `rail-agents`, `rail-library`, `rail-settings`.
- **New icons** go in `icons.js`, from Lucide v0.265.0, the pinned version: `bot`
  (Agents), `database` (Library), `settings` (Settings). Chats uses the existing chat
  icon.

The shell:
- `#app-topbar` is removed, along with `renderTopBar`'s inner-HTML sink and baseline
  entry, and `nav-chat-btn` with its registry row.
- The layout is a grid: rail (72px), then `<aside id="app-sidebar">`, then
  `<main id="main-content">`.
- **The aside collapses** (`hidden`) when the destination has no sidebar content. That is
  Agents in this flight, so no empty labelled landmark ships.
  - The collapse lands in the **router leg**, where Agents loses its section nav. The
    router sets `data-destination="<id>"` on the active content panel, which is also the
    tests' readiness probe.
- **Labels.** The aside's `aria-label` is the destination name: "Chats", "Library",
  "Settings". The section nav inside keeps "Library sections" and "Settings sections",
  so no two landmarks share a name. This fixes Studio's "Agent list".
- **Skip link.** It stays first in the tab order and targets `#main-content`.
- **Widths.** The design target is ≥1280px and it must stay usable at 1024px. Below
  1280px the aside narrows to 200px. Below 1024px is unsupported: there is no horizontal
  scroll, because `body` keeps `overflow:hidden`. This is documented.
- **`.visually-hidden`** moves from `admin.css`/`chat.css` (`@layer areas`) into
  `components.css` as a global utility, ending the library's hidden dependency (F1
  debrief).

User-visible copy that names old areas is updated:
- welcome.js:32-42: "Agent Studio" and "LLM Settings" become "Agents" and "Settings ›
  Providers";
- chat.js:1034: "Configure a provider in Studio", which is already wrong today;
- mcps-tab.js:76: "MCP Sources" becomes "MCP servers in the Library".

**DD8 — Client data layer: `App.store`, agents and providers first.**

`static/js/store.js` loads after `api.js`. It provides the collections `agents` and
`providers` (plus `toolConfigs` = `/api/tools/configs` if a migrated site needs it;
`tools` = `/api/tools` is named separately). Library collections arrive in Flight 3 with
their first consumers.

API:
- `get(name, {force}) → Promise`.
  - `force` means: join an in-flight request, else refetch.
  - Values are **copies**. Callers may mutate their copy without leaking into the cache.
    The in-place mutation sites (studio.js:1854-1856, :2766; admin.js:582-589,
    :469-480) are migrated to update through the store, or are left on their own copies.
- `peek(name) → {value, loaded, ok, error}`. It returns a copy; `value` is `null` until
  the first load.
- `invalidate(name)`.
- `subscribe(name, fn) → unsubscribe`.

Fetching:
- Fetches use `App.api.fetchJson`, which rejects on non-2xx. Today's `r.json()` sites
  parse error bodies as data.
- A failure is **never cached** and sets `ok:false`. The last good value stays available
  with its `loaded` flag, so callers can gate as the KB cache does today (DD-4/DD-15,
  squawks 0050, 0080, 0090).

Freshness:
- **Source of truth:** REST.
- **Rebuild trigger:** `invalidate`.
- **Bound:** destination activation uses `get(…, {force:true})` where today's code
  refetches on activate. Agents can change server-side with no WebSocket notice, through
  self-configuration writes, so activation stays the freshness bound, as it is today.

Invalidation map:

| Mutation | Invalidates |
|---|---|
| agent create, save, rename or delete | agents |
| provider create, save or delete | providers |
| provider OAuth sign-in or sign-out (`oauth_active`) | providers |
| KB rename or delete (rewrites agents' `kb_ids` and KB tool references) | agents |
| self-configuration enable/disable, revision approve or restore | agents |
| MCP source delete (detaches from agents) | agents |

Consumers migrated in this flight:
- chat's two `/api/agents` fetches per activate (chat.js:405, :1017) and
  `/api/providers` (chat.js:1016);
- studio `loadAll`'s agents and providers (studio.js:1150, 1349);
- admin providers (admin.js:378).

**DD9 — Tests migrate first through one helper; flakes fixed first; lanes follow
destinations.**

Flakes first. Four load-sensitive lane failures recurred across Flight 1 and were never
investigated:
- `test_flow_keyboard.py::test_agent_item_keyboard_select`
- `test_flow_admin_tools_editor.py::test_editor_renders_prompt_block`
- `test_flow_agent_crud.py::test_studio_agent_crud_flow`
- `test_flow_studio_mcp_editor.py::test_sandbox_chip_add_remove_marks_form_dirty`

Each is investigated and fixed (a deterministic wait, never a longer timeout alone)
before the migration touches its file, so the migration does not misattribute failures.

`tests/browser/_nav.py`:
- `goto(page, base, route)` takes a new-scheme route.
- `expect_route(page, route)` asserts the current route through the router once it
  exists, and through the hash before that.
- `open_destination(page, name)` uses the rail once it exists, the top-bar buttons
  before that, and falls back to `goto` for Library before leg 3's top bar has a fourth
  button.
- One mapping switch selects legacy hashes (before the router) or new routes (after).

The migration covers every browser test that navigates by hash, asserts the URL, or
clicks the top bar: about 45 files, 289 hash `goto`s, 88 URL assertions, and top-bar
clicks in 5 files. It is done with a scripted codemod, reviewed by hand. The four lanes
run once at the end of the leg.

Legacy-URL redirect coverage:
- At least 8 tests keep their **legacy `goto`** but assert through `expect_route`, so
  they prove the redirects after leg 3 instead of failing at the flip.
- They are listed in the `_nav.py` docstring:
  - 1 Chats;
  - 2 Agents, one with a tab;
  - 2 Library (KB, MCP);
  - 3 Settings (a provider item, a tools item, bare `#admin`).

Section nav and readiness probes:
- Agents loses its section nav in leg 3. These Agents-side clicks and readiness probes
  move in that leg to `open_destination('agents')` or a new readiness probe
  (`[data-destination="agents"]` on the panel):
  - test_flow_studio_navigation.py's `data-section="agents"` clicks;
  - test_flow_dirty_confirm.py:149;
  - the `.section-nav[aria-label="Agent Studio sections"]` readiness probes in about 9
    files (test_flow_agent_crud, agent_tabs, agent_tile, purge_now, retention_error,
    knowledge_attach, cross_area_dirty_gate, hash_routing, dirty_confirm).
- Library and Settings section-nav clicks stay, with their new `aria-label`s.

Lanes become `chats | agents | library | settings | shared`.
- `chat`, `studio` and `system` stay as aliases for the rest of the mission.
- Library files are listed explicitly: knowledge inventory, MCP editor and MCP
  navigation, MCP test-connection button, connector editor.
- Docs in CLAUDE.md and `agents.md` are updated.

**DD10 — Behavior specs.**

- **`shell-navigation-smoke`** is **updated**, not archived. It stays the
  data-independent, read-only gate (M17-F1), rewritten for the rail and its four
  destinations, the theme flip and restore, and a cold deep link. Its run log's
  spec-quality notes are folded in.
- **New `workbench-navigation`** is the deep spec. It seeds one mock provider, one agent
  and one KB through the API, and covers:
  - each destination's section navigation;
  - Back stepping between two opened items;
  - rail restore;
  - legacy deep links redirecting (`#admin/providers`, `#studio/agents/{name}/tools`);
  - a dirty editor asking before leaving via the rail and via browser Back, with Stay
    and Continue (Continue discards);
  - focus after Stay.

  It runs in **both themes** and is the flight gate.
- **Step-text updates** for `system-provider-config`, `save-preserves-config`,
  `stub-connector-round-trip`, `studio-agent-crud`, `agent-retention-setting-roundtrip`,
  `agent-purge-now-clears-history`, `anthropic-plan-signin`,
  `agent-governance-and-search`, `kb-studio-round-trip` and
  `anthropic-plan-chat-parity`. The soft mentions in `chat-roundtrip`,
  `extended-thinking-tool-turn` and `windows-native-frame-splash` (`#app-topbar` becomes
  the rail) are updated too.
- **Runs:**
  - In this flight: `studio-agent-crud` and `system-provider-config`, both mock-capable.
  - At mission end (Flight 6): the rest. Live-credential specs are run by the operator.
  - SC10 is complete only at mission end.

**DD11 — Reference spec §15 items owned by Flight 2.**

| Item | Disposition |
|---|---|
| A12 — `aria-current` missing on the rail | Rail items carry `aria-current="page"` (DD7). Chat rows and Settings items are Flights 3–4 |
| A15 — no unsaved-changes indicator on B3 | **Flight 3** (detail-pane header) |
| A11 (shell part) — keys not bound | No global shortcut in this flight. Ctrl K is Flight 4 |

**DD12 — Code placement.**

- **Shell code** (`router.js`, `nav.js`, `store.js`) lives at `static/js/` top level. It
  touches app globals, so it cannot live in `ui/`, which forbids them.
- **Library code.** `ui/rail.js` and `ui/modal.js` are pure UI and live in `ui/`.
- **Load order** in `index.html`, as insertions into today's order:
  - `router.js` and `nav.js` immediately after `app.js`;
  - `ui/modal.js` and `ui/rail.js` with the other `ui/` scripts, after `icons.js`;
  - `store.js` immediately after `api.js`.

  Everything else keeps its place: `perf.js`, `markdown.js`, `confirm.js`, `dialog.js`,
  `tabs.js`, `section-nav.js`, the areas.
- **Testing.** The disk harness keeps loading only `ui/`; shell code is tested in-app.
- **Cache-busting.** Every new tag bumps the count test.

### Citation Audit

Verified against `fe595cc` by the Flight-2 survey, then re-checked by the Architect
(2026-10-01):

| Citation | Status |
|---|---|
| `static/js/app.js:56-62` `parseHash` splits on first `/`; `:68-75` `syncUrlFromState` `replaceState`; `:77-187` `switchTo`; `:163-186` confirmLeave cross-area only; `:189-193` hashchange ignores unregistered; `:309-314` `replaceSub` never updates `currentSub` | verified (Architect) |
| `app.js:14-54` `renderTopBar` `topbar.innerHTML`, baselined | verified |
| `studio.js:84-191` hydrateState and `:1078-1123` setActiveSection do not clear `_selectedAgent`; section-nav `commit()` cleanup `:395-445`; `_refresh` `:2938-2948`; doSelect `:1796-1798` forces agents section | verified (Architect trace) |
| `studio.js:238`, `admin.js:153` one shared `dirty` closure per orchestrator | verified (Architect) |
| `connector-editor.js:614-621` one-way `markDirty` | verified (Architect) |
| `section-nav.js:21-24, 88-104` single-mount, roving array includes hidden buttons | verified (Architect) |
| `dialog.js:59-77` singleton; document-capture Enter → onConfirm | verified |
| `test_flow_dirty_confirm.py:269, 297, 341, 374, 485`; `test_flow_provider_dirty_confirm.py:219`; `test_flow_studio_mcp_editor.py:252` | verified (Architect) |
| `chat.js:405, 1016-1017, 1167, 1187`; `studio.js:1150, 1349, 1406-1414, 1854-1856, 2766`; `admin.js:378, 469-480, 582-589` | verified (Architect) |
| `markdown.js:111-121, 746` `safeHref` coerces to `#`, passes `#…` fragments | verified (Architect) |
| `base.css:10` `body { overflow: hidden }` | verified (Architect) |
| `admin.css` `.area-admin` occurrences = 141 (corrected) | verified (Architect) |
| `App.router.replaceSub` call sites = 28 (corrected) | verified (Architect, cycle 2) |
| `admin.js:664-680` `_setCategory` no-op on unchanged category; `studio.js:169/:184` `_activeSection` assigned before `_setActiveSection`; `studio.js:421-444` same-section branch of `commit()`; `studio.js:1847-1858` doSelect completion | verified (Architect, cycle 2) |

### Prerequisites

- [x] Flight 1 landed (`fe595cc`). It provides `App.ui`, the DD8 checks and the WebKit
  apparatus.
- [ ] PR #217 merged to `main`. **Not required to start.**
  - Flight 2 stacks on `flight/01-control-library-foundation`.
  - Re-check before opening the Flight 2 PR, and retarget it to `main` after the merge.
  - The operator merges; autonomous merges are blocked by the session's permission
    policy.
- [ ] CI WebKit install (`3.11-bookworm`, `--with-deps webkit`,
  `THE_ONE_REQUIRE_WEBKIT=1`) has never run. Concourse is unreachable on this host.
  Re-check reachability before the PR; if CI is still unavailable, record it as an
  operator item.
- [x] A dev instance on 8485 with a scratch data dir. **Re-verify per leg.** Never 8484.
- [x] goldfinch MCP for behavior runs: screenshots were unavailable on this host in F1,
  so the PDF/AX evidence path is used. **Re-verify at leg 7.**

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified, or explicitly deferred with a re-check point
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. **`test-navigation-helper`.** Fix the four flakes, then land `_nav.py` with its legacy
   mapping. Migrate every navigating test, keep the legacy set, re-map the lanes, and
   update the docs. No app code changes.
2. **`confirm-dialog-native`.** `App.ui.modal` with the full factory checklist;
   `App.confirmDialog` as an adapter; the pinned-test dispositions; the DD8 checks run
   against the real wrapper. This leg is independent of the router.
3. **`router-core` + `item-history-and-exact-rendering`** (split at leg design, 2026-10-01;
   see the leg artifacts). The text below is the original single-leg plan, kept for
   context. The live split is: router-core with the `replaceSub` → `sync` shim, then the
   per-call-path migration. The **interim guard** is widened: the area's `confirmLeave`
   runs on **every** `go()` unless `bypassGuard`, and on every traversal, and the in-area
   section-nav and `setCategory` gates are deleted, so no path prompts twice.
   **`router-and-redirects`** (original plan):
   - `router.js`, with `go` and `sync`, the destination table, the route builder, the
     redirect table, history seq stamps, popstate authority and rail-restore href state.
   - **Interim guard.** Until leg 4's `App.nav` lands, the router calls the existing area
     `confirmLeave` hook on **every** destination or section change and on `popstate`,
     not only on cross-area-module switches (app.js:170). Agents ↔ Library is one module,
     so without this a dirty agent editor would lose work silently between the two legs,
     and the dirty-gate tests would regress.
   - **Exact rendering.** Section-root routes render exactly the root, and dead item ids
     sync to the root (DD3).
   - **Per-site table.** Every `replaceSub` site gets its disposition (DD4).
   - **Aside.** It collapses on Agents, and `data-destination` is set on the panel
     (DD7).
   - The studio.js alias changes (a)–(d) and the 29 `replaceSub` sites moved to `sync`.
   - A four-button top bar rendered from destinations, as an interim step.
   - The helper flips to new routes; pinned routing tests inverted; Agents-side
     section-nav clicks and probes migrated; squawk 0082 closed.
4. **`unified-leave-guard`.** `nav.js` with per-area sources, teardown discard,
   single-flight and focus rules; every path including the link interceptor;
   `beforeunload`; the gate copies removed.
5. **`rail-and-shell`.** `App.ui.rail` and its icons; the top bar removed; the grid; the
   aside collapse and labels; widths; the `.visually-hidden` lift; the copy updates; the
   inventory and demo.
6. **`client-data-store`.** `store.js` for agents and providers, with copies, load state
   and the invalidation map; consumers migrated.
7. **`behavior-specs-and-close`.**
   - `shell-navigation-smoke` updated and `workbench-navigation` authored.
   - Spec texts updated.
   - Runs: `workbench-navigation` in both themes, `shell-navigation-smoke`,
     `studio-agent-crud` and `system-provider-config`.
   - Flight-close verification.

### Checkpoints

- [x] Four flakes fixed; every navigating test on `_nav.py`; lanes re-mapped; green (L1)
- [x] `App.ui.modal`; confirm on native `<dialog>`; dispositions done; DD8 checks pass on
  the real wrapper in both engines (L2)
- [x] Router with `go`/`sync`, redirects and seq history; Agents→Library→Chats→Library
  regression passes; 0082 closed (L3 `router-core`)
- [x] Every URL-writing call path dispositioned; item opens push; exact rendering; shim
  deleted (L4 `item-history-and-exact-rendering`)
- [x] Every path guarded; Continue tears down; Stay restores URL and focus (L4)
- [x] Rail replaces the top bar; aside collapses on Agents; usable at 1024px (L5)
- [x] `App.store` for agents and providers; no in-place cache mutation; failures not
  cached (L6)
- [x] Specs run and pass; full lanes green (L7)

### Adaptation Criteria

**Divert if**:
- **The alias layer still leaks state** between Agents and Library after changes
  (a)–(d). Split the studio area module in this flight. That is a recorded scope
  increase.
- **`popstate` does not fire reliably** for typed-hash navigations in WebKit. Fall back
  to `hashchange` as authoritative, and record that the Stay revert is a re-push in that
  engine.
- **The native confirm breaks a call-site behaviour** that the checks don't cover. Fix
  it, or record a compatibility path as debt.

**Acceptable variations**:
- The helper API names differ.
- The membership of the legacy set differs, as long as it has ≥8 tests across all four
  destinations.
- A `toolConfigs` collection is added to the store if migrating the admin tools grid is
  natural. Otherwise it is deferred to Flight 3.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created
> one at a time as the flight progresses.

- [x] `test-navigation-helper` - Fix the four recurring lane flakes; `tests/browser/_nav.py`;
  migrate every navigating browser test; legacy-URL set; lanes re-mapped with aliases;
  docs.
- [x] `confirm-dialog-native` - `App.ui.modal` (factory checklist); `App.confirmDialog`
  adapter on native `<dialog>`; pinned-test dispositions; DD8 checks on the real wrapper.
- [x] `router-core` - `router.js` (tables, scheme, redirects, `go`/`sync`, seq history,
  popstate, boot rules); `app.js` driven by the router; studio (a)–(c); the interim guard
  on every `go()` and traversal, with the in-area gates deleted; shell bits; the
  deprecated `replaceSub` shim over `sync` (closes 0082); the `_nav` flip and test
  migrations. Split from `router-and-redirects` at its design review.
- [x] `item-history-and-exact-rendering` - a per-call-path disposition table (about 40
  rows); item opens push; section-root exact rendering; dead ids; Chats row → `go()`;
  links and the MCP tab; the shim deleted.
- [x] `unified-leave-guard` - `nav.js` (per-area sources, teardown discard, single-flight,
  focus rules); link interceptor; `beforeunload`; gate copies removed.
- [x] `rail-and-shell` - `App.ui.rail` and its icons; top bar removed; grid; aside
  collapse and labels; widths; `.visually-hidden` lift; copy updates; inventory and demo.
- [x] `client-data-store` - `store.js` for agents and providers (copies, load state,
  invalidation map); consumers migrated.
- [x] `behavior-specs-and-close` - `shell-navigation-smoke` updated, `workbench-navigation`
  authored; spec texts; runs (both themes); flight-close verification.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged to `main` (after #217; the operator merges)
- [x] Tests passing: `make lint`, `make test-unit`, all five lanes, library contract tests
  in both engines
- [x] Documentation updated:
  - `CLAUDE.md` (lanes, routes, shell)
  - `the_one/agents.md` (router, leave guard, store, rail, modal; hash-format section
    rewritten)
  - `docs/ui-testid-registry.md`
  - `docs/ui-control-inventory.md`
  - `tests/HAT.md` route references
- [x] Squawk 0082 closed in the flight commit

### Verification

- **Unit**: `make lint`, `make test-unit`. These cover the guards, the registry, the
  cache-busting count and the inventory.
- **Browser**: the five lanes one at a time, plus every `test_ui_*` in both engines.
- **WebKitGTK**: the probe at `#agents` and `#settings/general` (`--root-selector body`).
  Record any legacy failure.
- **Behaviour**:
  - `workbench-navigation` (dark and light);
  - `shell-navigation-smoke`;
  - `studio-agent-crud`;
  - `system-provider-config`.
- **Flight review**: a Reviewer and an Accessibility Reviewer.
