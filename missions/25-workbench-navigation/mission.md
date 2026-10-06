# Mission: Workbench Navigation and Control Library

**Status**: active

## Outcome

The operator works in one calm workbench instead of three separate areas. A slim rail
leads to four places — Chats, Agents, Library, Settings — and each place keeps its list
on screen while an item's details open beside it, so nothing is ever "behind" a Back
button and unsaved work is never silently lost. Starting a conversation begins with the
question that matters, *which agent?*, answered in a picker that stays usable with dozens
of agents. Every control on the redesigned surfaces comes from one reusable control
library, built without a framework, in the deep-violet refinement of the design language,
and the desktop window itself looks like part of the same product.

## Context

Mission 17 replaced the app's visual language ("quiet instrument panel", Design Language
v3) but kept the original information architecture: three top-bar areas (Chat, Agent
Studio, System), each with its own sidebar, and editors that *replace* their grid and need
a "← Back". A navigation survey this session found the structural pain points:

- Editors swap out their grids; switching sections discards the open editor.
- The same concern is configured in several places — knowledge in three (Studio ›
  Knowledge, System › Knowledge, the agent's Knowledge tab), built-in tools in two, MCP
  servers defined in one area and attached in another, providers in System but chosen in
  Studio.
- Naming collides ("Knowledge" names three surfaces; "MCP Servers" vs "MCP Sources";
  "System" in the UI vs `admin` in URLs).
- Chat asks for an agent through a dropdown that sits above the history, so it reads as a
  filter rather than "start a chat with…".
- Controls are built three different ways (HTML-string helpers, DOM-building helpers,
  per-editor copies); dirty tracking is re-implemented per editor (six copies of the
  leave-guard logic); the largest orchestrators run 2–3k lines (`studio.js` 3,047,
  `admin.js` 794).

With the operator, this session produced and iterated on prototypes, and the operator
chose a direction:

- **Design system** (published reference, built from the shipped tokens and component
  CSS): https://claude.ai/artifact/51jpj1RcXp18MehEQAteWs
- **Prototype canvas**: https://claude.ai/artifact/787XyAuiyoA969YSF5ZnFc — the approved
  samples are the clickable board **"B · Workbench — clickable (28 agents)"** and the
  **"Button treatments"** board (option **Deep violet**). The other boards (A, B1/B2, C)
  are rejected or superseded explorations, kept for reference.

Decisions already made by the operator (not open for re-litigation in flight planning):

1. **Workbench layout ("direction B")** — rail (Chats, Agents, Library, Settings) +
   persistent list column + detail pane. Library holds knowledge bases, MCP servers and
   connectors; Settings is one place, grouped (General: Appearance, Prompts, Encryption ·
   Models: Providers · Defaults for agents: Built-in tools, Knowledge indexing ·
   Developer: Design language). A keyboard-invoked jump-to palette reaches anything.
2. **Agents list** — flat A–Z with a filter (name, model, provider). No grouping, no
   pinning: both were prototyped and rejected.
3. **Chats** — a large primary **New chat** action at the top of the conversation list
   opens an **agent picker** in a modal (search; Recently used; All agents A–Z); choosing
   an agent immediately starts a new chat with it. No agent dropdown or filter on the
   chat list. A right-hand **drawer** shows the current chat's agent read-only
   (description, model, provider, what it can use) with **Open agent settings**; there
   are no per-chat tool toggles, because tools are configured per agent.
4. **Buttons — "Deep violet"** — saturated violet fill with a white label in both themes
   (dark `#7c3aed`, hover `#6d28d9`; light `#6d28d9`, hover `#5b21b6`), 13px medium
   labels, secondary actions on a raised fill (not an input-like outline), danger as a
   transparent button with a danger hairline.
5. **Reusable controls without a framework**, if at all possible.
6. **Window chrome is styled** to match the workbench (operator request; either mission
   was acceptable — placed here so the packaged app the operator installs at mission end
   is coherent inside and out).
7. **Agent editor**: this mission hosts the *current* tabbed editor beside the agent list
   with chrome-only changes. The prototype's single-page outline and merged
   "Capabilities" list are the configured-in-several-places fix and move to the **next
   mission**, so agent URLs and tests change once.
8. **Branching**: each flight merges to `main` as it lands; **no release is cut until the
   mission completes**.
9. **Operator checkpoint** after Flight 3 (see Flights).

This is the first of likely two or three missions. The next mission redesigns the
existing editors' *internals* (agent editor outline + Capabilities, MCP server, connector
and knowledge-base editors), resolves the configured-in-several-places problems, and adds
the live status data this mission's list rows omit; a later pass completes control
coverage for every remaining surface.

## Success Criteria

- [ ] **SC1 — Workbench navigation**: The app's primary navigation is a persistent rail
  with four destinations — Chats, Agents, Library, Settings. Every page that exists today
  is reachable from one of them, and every previously valid deep link (including agent
  editor tabs) lands on the equivalent new location. *(behavior-test-backed)*
- [ ] **SC2 — Lists stay put, work is never lost**: Opening any agent, Library item
  (knowledge base, MCP server, connector) or Settings page shows it beside a list that
  stays visible; no surface replaces its list with an editor or needs a Back control;
  creating an item opens it. Leaving unsaved changes always asks first, whichever route
  is used — list, rail, jump-to, drawer link, or browser navigation.
- [ ] **SC3 — Start a chat by choosing an agent**: From Chats, one primary New chat action
  opens an agent picker with search, a recently-used section and the full alphabetical
  list; choosing an agent starts a new conversation with it with no further step; the
  history lists conversations across all agents. In any conversation the operator can
  open a panel showing that conversation's agent read-only (description, model,
  provider, what it can use) with a one-step route to its settings.
  *(behavior-test-backed)*
- [ ] **SC4 — Agents at scale**: The agent list is alphabetical with a filter that narrows
  by name, model or provider, and stays responsive and visually intact with at least 30
  agents.
- [ ] **SC5 — Jump to anything**: A keyboard shortcut and a visible control open a jump-to
  palette that finds agents, conversations, Library items, Settings pages and the New
  chat action, and opens the chosen one.
- [ ] **SC6 — One reusable control library**: Buttons, form fields, selects, toggles,
  checkboxes, list panes, menus, modals, drawers, badges and empty states on the
  redesigned surfaces come from one shared control library that adds no build step and
  no third-party runtime dependency, and that the existing UI guard tests can still see
  (test ids, label/description wiring, no new HTML-string sinks). The in-app
  design-language reference demonstrates every library control in both themes, and a
  control inventory classifies every control in the app as library-defined or not yet
  defined, naming the surface that owns each undefined one.
- [ ] **SC7 — Deep-violet design language**: Primary actions use the approved deep-violet
  treatment and secondary actions the raised treatment, in both themes. Every contrast
  pair introduced or changed meets WCAG 2.1 AA in both themes (text; and non-text where
  the color identifies a control or its state), or is recorded as a band-pinned exception
  under the project's existing exception policy. The in-repo design reference and the
  published design system both describe the change.
- [ ] **SC8 — Matches the approved samples**: Each redesigned surface (rail, Chats with
  picker and drawer, Agents, Library and Settings frames, jump-to palette) matches the
  approved boards in both themes — verified by screenshots and computed-style probes of a
  running build against a reference committed with the mission. Board elements that need
  data the app cannot yet provide (provider health and its banner, MCP connection state,
  connector channel counts) are pre-accepted deviations; every other deviation is fixed
  or explicitly accepted by the operator.
- [ ] **SC9 — The window belongs to the product**: In the packaged Windows desktop app, the
  window frame matches the workbench in both themes and follows theme changes, while
  dragging, snapping, minimize/maximize/close and close-to-tray keep working; the app
  opens at a size the workbench fits. *(verified by the operator in the packaged app)*
- [ ] **SC10 — Operable and regression-safe**: Every new or changed interactive element is
  keyboard-reachable and operable with visible focus, with landmarks and the skip link
  preserved. The unit and browser suites and all UI guard tests pass; the existing
  behavior specs that use the old navigation are updated and pass, and new specs for the
  core flows (navigate the workbench; start a chat via the picker) pass in both themes.
  Library controls are exercised in a WebKit engine as well as Chromium.
  *(behavior-test-backed)*

## Stakeholders

- **Operator (sole user)** — uses the app daily; delegated implementation and sequencing
  to the agent crew; reviews at the post-Flight-3 checkpoint and the alignment flight;
  installs the packaged app only after the mission completes. Final acceptance authority.
- **Future agent maintainers** — the codebase is maintained almost entirely by LLM agents;
  the control library must be conventional, greppable and documented so later missions
  (editor internals, control-coverage completion) extend it without drift.

## Constraints

- **No framework, no build step, no third-party runtime dependency** (continuity with
  Mission 17's policy). Native platform capabilities are allowed. The existing code is
  ES5 classic scripts; adopting any newer construct the chosen mechanism needs (e.g. a
  `class` for a custom element) is an explicit, documented convention change, not drift.
- **Runtimes**: the packaged desktop shells (WebKit2GTK on Linux, WebView2 on Windows) and
  current browsers. No polyfills; features newer than the runtime floor the CSS already
  implies (`:has()`, `@layer`) need a fallback or are out.
- **Minimum width**: designed for 1280px and wider, usable at 1024px (list column narrows,
  drawer overlays instead of pushing).
- **Test-stability contract preserved**: load-bearing elements keep stable `data-testid`s
  registered in the testid registry; the existing UI guard tests stay green, and any
  extension a library needs for them to keep working (e.g. recognizing library-authored
  test ids, a runtime label/description resolver over library surfaces) is part of the
  library's own delivery. Legs touching `static/` run the UI guard, token-definition and
  contrast suites, not only the browser lane.
- **Both themes first-class**; contrast pairs gated by the existing accessibility suite and
  its token mirror.
- **Accessibility is a per-leg gate**, not a cleanup phase.
- **Scope fence**: orchestrators and editor *chrome* (headers, Back, save/cancel placement,
  leave guards) are in scope; editor *form internals* are not, and are redesigned next
  mission. Backend changes only where a decided surface needs data the API cannot
  provide and the gap is not a pre-accepted deviation (e.g. exposing a session's platform
  so connector-driven sessions don't count as "recently used").
- **Branching and releases**: per-flight branches (`flight/{NN}-{slug}`) merge to `main` as
  each flight lands; no release is cut from `main` while this mission is active. Every
  merge keeps the lint gate and test suites green.
- **References are committed**: the approved boards' source and a derived reference spec
  (measurements, tokens, copy) live in the mission directory, so crews do not depend on
  an external, mutable URL. This is design source, not a test baseline; screenshots taken
  for comparison are flight-log evidence and are never committed.
- **Published design system** is updated by the Flight Director (spawned crews cannot
  publish artifacts).
- **Production safety**: never drive port 8484 or the operator's default data directory;
  all live verification uses a dedicated dev instance (non-default port **and** scratch
  data directory).
- **Autonomous execution**: the crew sequences and implements without check-ins; human
  touchpoints are this mission's sign-off, the post-Flight-3 checkpoint and the alignment
  flight.

## Environment Requirements

- Host-native dev instance: `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> THE_ONE_DEV_MODE=true make up`
  (mock provider for deterministic chats), seeded with ≥30 agents across several providers
  and a spread of conversations, knowledge bases, MCP servers and a connector.
- Browser apparatus: goldfinch MCP for screenshots and DOM/computed-style probes against
  the dev instance. Known limits (`the_one/agents.md` "Browser apparatus doctrine"):
  `captureScreenshot` can wedge — fall back to printToPDF plus computed-style probes or
  Playwright screenshots; goldfinch cannot observe `:focus-visible`, so focus evidence
  needs a real-focus apparatus.
- Playwright browser suite via `scripts/run-tests.sh` (lanes re-mapped as areas change),
  plus a WebKit-engine smoke for library controls (`libwebkit2gtk-4.1` is installed on the
  dev host).
- Windows packaged build for the window-chrome flight (existing Windows CI worker and
  `packaging/windows/`); final visual check by the operator.

## Open Questions

- [ ] **Control-library mechanism** (Flight 1): factory functions returning native
  elements (current lean) vs. custom elements rendered into the page DOM, with custom
  elements reserved for stateful composites (modal, drawer, palette, list pane). Settled
  by a spike that must show: (1) library-authored test ids are seen by the registry guard
  with no manual exceptions; (2) fill, select, check, disabled and strict locators work in
  Chromium and WebKit; (3) a runtime label/description resolver passes over library
  surfaces; (4) no new HTML-string sinks; (5) a manual pass in the packaged WebKitGTK app.
- [ ] **Modal, drawer and palette mechanics** (Flight 1 rule, built where consumed): one
  focus-trap, Escape, scroll-lock and focus-restore rule, including chaining (palette →
  leave guard → confirm dialog); native `<dialog>` vs. the existing overlay.
- [ ] **Router contract** (Flight 2): URL scheme for the four destinations; legacy
  `#studio/…` / `#admin/…` redirect table (must not collide with the `#main-content` skip
  link); four registered areas vs. an alias layer over the current three; history policy
  (does browser Back step between items? does the rail restore the last-open item?).
- [ ] **Settings pages with item editors** (Flight 3): Providers and Built-in tools show a
  table/list in the board with no editor state — define how an item opens while the list
  stays visible, inside Settings' own nav.
- [x] **Drawer push vs. overlay** at different widths (Flight 4): resolved by Flight 4 DD7. The drawer pushes the pane at 1280px and wider (open by default), overlays below that (closed by default), and remembers each mode separately. The 1024 overlay covering Send is an open preview question.
- [ ] **Window chrome mechanism** (Flight 5): Mission 15 reverted frameless custom chrome
  because WebView2 ignored the drag-region CSS. Spike whether WebView2's opt-in
  non-client-region support can be enabled through pywebview (making a goldfinch-style
  custom title strip possible); otherwise tint the native title bar to the workbench
  surface and theme.

## Mission-level design decisions

**Library list shape**: one grouped list (Knowledge bases · MCP servers · Connectors) with
an **Add** menu to choose the type, as prototyped.

**List rows show only data the app has**: names, badges, models, counts derivable
client-side ("used by N agents" from agents' provider/knowledge/MCP references; MCP tool
counts; "recently used" from session recency, filtered to live agents and excluding
connector-driven sessions). Live health/status lines are deferred (see SC8).

**Deep violet**: a dedicated fill token pair (under the contrast-gated `--accent*` family)
for solid accent fills — buttons, checked checkboxes, switched-on toggles. The existing
lighter accent stays for focus rings, links, selection borders and washes.

**Shared client data layer**: one small store for agents, providers, Library items and
sessions with invalidation, so the picker, palette, drawer, lists and "used by" counts stay
consistent (delivered with the shell).

**Test migration first**: a central test navigation helper lands before the shell change;
a representative set of tests stays on legacy URLs to double as redirect coverage.

**Picker edge cases**: the synthetic default agent and sessions of deleted agents remain in
history but do not appear in the picker, and their drawer shows no settings link.

## Known Issues

*(populated during execution as flights surface problems)*

- [x] Flight Control methodology files in `.flightops/` were behind the installed plugin
  (migrations 008–012 pending at mission planning) — **resolved 2026-09-30** by
  `/mission-control:init-project`: methodology files synced, 008–012 applied (flight-end
  review and commit; Service Report section with upstream reporting enabled; Sortie
  artifact; Flight Director paragraph; leg checklist retired), crew customizations kept.
- [ ] **Ctrl K in WebView2**, carried from Flight 4 DD9 to **Flight 5**.
  - The jump-to shortcut is a page-level `keydown` listener (one on `document`, in `app.js`).
  - **WebKitGTK: partially verified (GTK-level key)**, Flight 4 leg 7, 2026-10-05.
    - **How:** WebKitGTK 2.52.6 on WSLg, through `scripts/webkitgtk_probe.py --press-keys
      ctrl+k` with the default `event` method: a `Gdk.EventKey` press/release pair through
      `WebView.event`.
    - **Result:** with focus in a text input, the page saw a trusted Ctrl+K keydown, the
      listener prevented it and the palette opened, in both themes.
    - **Caveat:** `Gtk.test_widget_send_key`, an X `XSendEvent`, never reached the page
      under XWayland. A GTK-level key proves nothing about what an OS window manager or
      input method does above GTK.
  - WebView2 can only be checked in the packaged Windows build: confirm that Ctrl K reaches
    the page and is not taken by a browser accelerator (the Edge address bar's own Ctrl K
    included).
  - Flight 5's scope is window chrome, so it is listed here explicitly.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Control library foundation** — commit the board references and derived
  spec; spike and settle the control mechanism against the exit criteria; set the
  modal/drawer stacking rule; deep-violet tokens applied app-wide (mirror and contrast
  gates updated); the core controls the shell needs (button, field, select, toggle,
  checkbox, list pane, menu, badge, empty state) with guard extensions; the Design
  language page rebuilt as the library's living reference; the app-wide control
  inventory; the published design system updated.
- [x] Flight 2: **Shell and router** — router contract (URL scheme, legacy redirects,
  history policy); one leave guard covering every navigation path, replacing the
  per-orchestrator copies; the rail; the shared client data layer; the central test
  navigation helper, lane re-mapping and migration of tests and the nine existing behavior
  specs that use the old navigation. Pages move into their destinations one-to-one.
- [x] Flight 3: **List and detail** — Agents (alphabetical list with filter; current tabbed
  editor hosted beside it, chrome only), Library (grouped list, Add menu; knowledge base,
  MCP server and connector editors hosted beside it) and Settings (grouped nav; item pages
  keep their list visible); Back controls retired; create opens the new item (resolves
  squawk 0101). Followed by an **operator checkpoint**: a running dev instance and
  screenshots; the operator says go or flags problems before Flight 4.
  *Checkpoint held on 2026-10-05.* The operator approved the other items and asked for
  Settings › Providers to be tiles matching Built-in tools. Flight 3 leg 7
  (`providers-tiles`) delivered that, and its re-runs passed. The full record is in the
  flight log.
- [x] Flight 4: **Chats and jump-to** — New chat with the agent picker, cross-agent
  history, the agent drawer, removal of the chat agent dropdown and welcome-screen agent
  list; the jump-to palette (sharing the picker's searchable-list control); new
  core-flow behavior specs; sample comparison in both themes.
  *Landed on 2026-10-06* (PR #220). The operator preview (DD13) was published and not
  awaited. The close-gate runs passed 96 of 96 checkpoints: `start-a-chat` and
  `jump-to-palette` in both themes, `workbench-navigation`, `shell-navigation-smoke` and
  `chat-roundtrip`. The operator then answered the preview. Leg 9 changed the palette's
  empty query to recent chats, New chat… and recent agents (option C), and its targeted
  re-run passed. The flight is completed.
- [ ] Flight 5: **Window chrome** — the WebView2 non-client-region spike; goldfinch-style
  custom chrome if it holds, otherwise a native title bar tinted to the workbench and
  following the theme; first-launch window size that fits the workbench; verified in a
  Windows packaged build.
- [ ] Flight 6: **Alignment** — hands-on session with the operator in the running app and
  the packaged build: walk the surfaces against the samples, adjust, and fix or accept
  remaining deviations.
