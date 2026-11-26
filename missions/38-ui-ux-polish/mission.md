# Mission: UI/UX Polish

**Status**: active

## Outcome

The app looks and behaves like something made with care, at every window size
the desktop app allows. After this mission:

- **Every page works in a small window.** The desktop window can shrink to
  640×360 outer, which leaves a viewport of about 624×321. At that size, as at
  full size, every destination is usable: the conversation, forms and lists
  get a readable width and height, and the list column and side panels give
  way instead of crushing the main pane.
- **A new operator is guided to a first reply.** On an empty install, the app
  shows one short checklist (model provider → agent → first chat) that ticks
  off as each step is done. Each step hands the operator to the next one
  ("Create an agent with this model"), so the setup path never means hunting
  between Library and Agents. The checklist goes away once a chat has a reply.
- **What an agent can reach is legible at a glance.** Every agent page and the
  chat's agent panel say in a plain sentence what the agent can touch, and the
  sentence is honest about scope (for example "Can read and write files in
  the folders you allowed, run commands in a sandbox with no network, and use
  the web; uses no secrets"). On the Tools tab, the categories that act on the
  machine or send data out look and read as higher-stakes than the ones that
  don't, each with a one-line consequence. **Defaults do not change.**
- **Each screen has a focal point.** Page titles and section headings form a
  clear scale. The accent colour marks primary actions, focus, links and
  switched-on controls only, not selection. Selection is drawn once, as a
  neutral fill with a non-colour cue.
- **Same job, same pattern.** Creating something, empty states, toasts and the
  names of things are consistent across Chats, Agents, Library and Settings,
  and nothing on a screen repeats what the operator already knows.

## Context

On 2026-11-25 we reviewed the running app (v1.0.0, `9f5cbb1d`) with the
Interface Craft design-critique method (Josh Puckett). We used a scratch dev
instance at 1280×800 in light and dark mode, plus a 430px capture, and checked
the CSS. The review found the app calm and well written, with excellent plain
copy, but flat in hierarchy, over-accented, and broken at narrow widths. Its
top opportunities are this mission's flights.

The plan was then validated by the Architect and reviewed independently
(Fable). That review corrected several facts and sharpened the criteria; the
findings below include its corrections. Each flight design re-verifies them.

**Narrow widths (structural defect).**
- `static/css` has no width-based `@media` rule. The only media queries are
  `prefers-reduced-motion` (4) and `forced-colors` (3).
- The shell is a flex row (`base.css:31` `.app-shell-row`): the rail, then
  `#app-sidebar` (`width: var(--list-w)`, `flex-shrink: 0`), then `<main>`.
  The rail (72px) and the list column (`--list-w: 300px`, `tokens.css:56-60`)
  together take 372px.
- At 430px the main pane was 58px wide and the transcript wrapped about one
  character per line.
- The desktop launcher allows a small window. `MIN_SIZE = (640, 360)`
  (`interfaces/desktop/window_state.py:133-138`) is the **outer** window
  size. On Windows at 100% scaling the client area is about 16px narrower and
  39px shorter, so the real viewport is about **624×321**. With the rail and
  list column that leaves the main pane about 252px. Other platforms' chrome
  differs; Flight 1 measures each.
- **Height is the hard constraint.** 321px must hold the header, at least
  three transcript lines and the composer.
- Other fixed widths that break below about 900px: the Settings nav
  (`--settings-nav-w: 260px`), the agent panel (`--drawer-w: 320px`), the
  GleepGlorp drawer (360px, `gleepglorp-drawer.css:8`), and the tile grid
  `minmax(280px, 1fr)` (`components.css:2419`), which overflows a 252px pane.
  The widest component minimum is `ui-modal`'s 320px (`components.css:1756`).
- Both drawers already respond to width. The chat's agent panel
  (`agent-drawer.js:102`) and the GleepGlorp drawer
  (`gleepglorp-drawer/shell.js:27`) push only at
  `matchMedia('(min-width: 1280px)')` and overlay below it (M25 F4 L6, DD7).
- `App.ui.drawer` (`js/ui/drawer.js`) is **non-modal**: `open()` does not move
  focus, overlay mode has no scrim and no outside-click close, and it is
  right-anchored. It is a precedent for width switching, not for focus
  handling.
- The route already encodes list-versus-detail state (a destination with or
  without a selected item), which suits a one-pane-at-a-time narrow layout.
- One container query exists already (`components.css:3313`).
- The webview engines are WebKitGTK 4.1 on Linux
  (`packaging/linux/control.in:9`), WKWebView on macOS and WebView2 on
  Windows. Container queries need WebKitGTK 2.40 or later; viewport `@media`
  and `matchMedia` carry no such risk.
- `scripts/ui_capture.py:76-79` captures only 1280 and 1024 widths.

**Hierarchy and accent.**
- Type is tokenised and disciplined, but flat. `--font-size-body-sm` has 103
  uses and `--font-size-caption` 64, against 3 for `--font-size-h1`.
- Section labels ("IDENTITY", "LLM CONFIGURATION") are small uppercase grey.
- The same violet accent marks the selected rail item, the selected list row,
  the active tab, focus, primary buttons, every switch and the GleepGlorp
  corner button.
- Selected rows carry both a tinted fill and a violet outline
  (`components.css:103-108`: `background: var(--accent-translucent);
  box-shadow: inset 0 0 0 1px var(--accent)`). This is a recorded decision:
  DD14 and the "Accent restraint rule" in `the_one/agents.md` (~:2296).
  Under forced colours, selection is a `1px solid Highlight` border
  (`components.css:2622+`).
- **Operator decision (2026-11-25): reverse DD14.** Selection becomes a
  neutral fill plus a non-colour cue that survives forced colours. The
  Accent restraint rule is rewritten, and the new pairs join the contrast
  gate (`tests/test_design_tokens_a11y.py`).
- Disabled Cancel/Save in an editor header look close to the enabled "Chat"
  ghost button, especially in dark mode. They are disabled until the editor is
  dirty (`js/ui/editor.js:59-62, 222-226`), and about 394 `to_be_disabled`
  assertions in 78 browser-test files pin that.
- **Operator decision (2026-11-25): keep disabled-until-dirty** and its
  caption; make disabled buttons visibly inert instead of hiding them.
- Expanders use a Unicode "▸" ("9 tools ▸", "▸ Show data") beside line icons.

**Agent reach.**
- New agents have every built-in category on: Filesystem 9/9, Execution 6/6,
  Web 4/4, Connectors 3/3, Time 1/1.
- Those categories are scoped, and the sentence must say so:
  - Execution runs in a sandbox with no network by default
    (`tools/execution.py:299-306`).
  - Filesystem is limited to the agent's `path_allowlist`
    (`tools/filesystem.py:85`).
  - Per-agent `tool_overrides` can change both.
  - Web and Connectors send data off the machine; MCP stdio servers run local
    processes outside the sandbox.
- The Tools tab gives every category the same row: a switch, a name and an
  uppercase mono "N / N ENABLED" badge.
- The chat panel's "What it can use" already gathers the data for a capability
  sentence: rules, notes, routines, knowledge bases, MCP servers, secrets and
  built-in counts.
  - `agent-drawer.js` loads `/api/agents/{name}/rules`, `/notes`, `/routines`,
    `/self-configuration` and `/api/tools/configs`.
  - The groups are built in `agent-drawer-groups.js`.
  - The agent page does not load this today, so the sentence needs a shared
    client-side helper (resolved by the Architect review).
- **Operator decision (2026-11-25):** show the risk and keep the defaults. No
  `SECURITY-MODEL.md` change.

**Setup path.**
- The empty Chats page sends the operator to two other destinations ("Add a
  model provider in Library, then create an agent in Agents").
- That line is `App.chat.chatPane.guidance(setup)` (`chat-pane.js:75-95`),
  driven by `{hasProviders, hasAgents}` (`instance.js:187`).
- The Agents and Library start pages have their own intro cards
  (`agents-list.js:277-281`, `library-pane.js:543`). These and the chat
  welcome are hand-built by design (`docs/ui-control-inventory.md` ~:98).
- There is no onboarding module and no persisted first-run flag. The checklist
  extends or replaces these; it does not start from nothing.
- `localStorage` is not a reliable home for first-run state: when the
  preferred port is taken the desktop app falls back to a free one
  (`desktop/takeover.py:227-235`), which changes the origin.
- The sessions schema has no reply-count field.
- GleepGlorp is enabled by default and reports `needs_model` when no provider
  or model is set (`gleepglorp/settings.py`); its drawer says "GleepGlorp
  needs a model".
- The New Agent form shows all six tabs before the agent exists. GleepGlorp's
  create fill can set twelve keys (`agent-editor-fill.js:45`), spread across
  those tabs.

**Repetition and drift.**
- An open chat names its agent four times and its model three times.
- An empty Library lists the same five groups twice: the list column ("No X
  yet.") and the hub cards.
- The composer telemetry shows a raw readout ("0% in: 0 out: 94 ctx: 0 max:
  128.0k").
- "Create" has three looks: the full-width filled "New chat", small ghost
  "+ New"/"+ Add" in list headers, and a filled "New agent" in the main pane.
- Empty states have three styles, and `App.ui.emptyState` still has
  hand-built sites listed in `tests/_ui_ownership_allowance.py` (for example
  `mcps-tab.js`).
- Naming drifts: "MCP servers" vs "No MCP sources registered yet.";
  "Model provider" vs "Provider" vs "LLM configuration"; "Built in" vs
  "Built-in".
- Jump to lists "GleepGlorp" twice: the built-in chat target
  (`jump-to.js:131`, "GleepGlorp / Built in") and the Settings › GleepGlorp
  page entry. Fixing it is a relabel, not a removal.
- The GleepGlorp corner button clipped the last Tools-tab badge ("3 / 3
  ENABLE"). `gg-corner-on` bottom padding covers studio editors and admin
  content, not the agent editor's tab panel.
- The "Agent created" toast appeared faint and over the header. It is the
  fixed-top `.app-flash` (`components.css:11`).
- The agent panel already remembers whether it is open (`localStorage`
  `chat-drawer-open`, `{push, overlay}`). Only its push-mode default (open,
  DD7) is in question.
- `tests/test_gleepglorp_guide.py:5-10` checks the guide's structure, word
  count, internal names and routes. It does not check labels, so a relabel
  needs its own check.

**Motion.**
- Motion has tokens (`--motion-fast/medium/base`, `--ease-tactile`), and
  reduced motion is implemented by setting them to `0ms` (`tokens.css`
  ~:389).
- About ten CSS transitions hard-code `0.15s`, `0.25s` or `0.3s ease` and so
  ignore reduced motion. They are at `chat.css:340` and
  `components.css:11, 273, 333, 1275, 1695, 2648, 3185, 3190, 3198`, and
  include the flash, the telemetry meter and the progress fill.
- `@keyframes` spinners have their own per-rule reduced-motion overrides.
- JS-driven motion (`thinking.js:31`, `widget.js:513`) already checks reduced
  motion; it is out of this mission's motion criterion.

## Success Criteria

Each criterion is checkable by a test or a grep. The narrow-window size is the
client viewport, **624×321**, unless a criterion says otherwise.

- [ ] **The app works at 624×321.** For every destination (Chats with an open
  chat, Agents and every agent tab, Library and every editor, Settings and
  every page), a browser test at 624×321 and 1280×800 asserts:
  - the main pane is at least the width Flight 1 records (no less than
    360px), or the destination shows one pane at a time;
  - `document.scrollingElement.scrollWidth <= clientWidth` (no horizontal
    page scroll);
  - an open chat shows at least three transcript lines above the composer;
  - the last interactive control in each scroll container, scrolled into
    view, is the element at its own centre point (`elementFromPoint`), so
    nothing covers it, including the GleepGlorp corner button;
  - the list column and side panels open through a control and close again,
    and at most one overlay is open at a time;
  - focus moves into an opened overlay and returns to its trigger on close.
- [ ] **A new operator reaches a first reply guided only by the app.**
  - On a fresh data directory, a checklist shows provider → agent → first
    chat, with progress.
  - Each completed step offers the next one directly.
  - The checklist is derived from data and disappears once a chat has a
    reply, as Flight 6 defines "has a reply".
  - This is shown as a HAT state-transition sequence and a browser test.
- [ ] **Every agent's reach is stated in a sentence.**
  - The agent page and the chat's agent panel show the same capability
    sentence, built by one shared helper from a phrase table, not by string
    concatenation.
  - A unit-style test pins the exact sentence for a fixture matrix: all
    categories on; none on; Filesystem only; MCP servers only; a secret
    granted; Execution with network allowed by an override.
  - The Tools tab marks the categories that act on this computer or send data
    out, with a one-line consequence each.
  - Built-in tool defaults, tool descriptions and `SECURITY-MODEL.md` are
    unchanged (`git diff` on them is empty).
- [ ] **One focal scale and a reserved accent.**
  - Page titles and section headings use the documented heading roles.
  - Selected rail items, list rows and tabs use a neutral fill and a
    non-colour cue, with no accent outline; the cue is visible under forced
    colours.
  - The accent marks only primary actions, focus rings, links and switched-on
    controls; the Accent restraint rule in `the_one/agents.md` says so.
  - Disabled buttons fail no contrast-gate pair and are visibly distinct from
    enabled ghost buttons (new pairs in `tests/test_design_tokens_a11y.py`).
- [ ] **One pattern per job.**
  - Every create action uses one control pattern.
  - Every empty state is `App.ui.emptyState`, except the start-page cards and
    chat welcome recorded as hand-built by design; no empty-state entries
    remain in `tests/_ui_ownership_allowance.py`.
  - Toasts appear in one place.
  - Each concept has one name: a grep for the retired labels across
    `static/js` and `the_one/gleepglorp/guide/*.md` returns nothing.
- [ ] **CSS motion follows the tokens.**
  - No CSS `transition` or `animation` duration is a literal; a grep of
    `static/css` for `[0-9.]+m?s` in those properties returns only token
    definitions.
  - Every `@keyframes` animation has a reduced-motion rule.
- [ ] **The guide matches the app.** `the_one/gleepglorp/guide/*.md` describes
  every changed page, label and flow, `tests/test_gleepglorp_guide.py`
  passes, and the retired-label grep above is clean.
- [ ] **The gate is green.** `make gate` passes (unit, then every browser lane
  including the contracts lanes under `THE_ONE_REQUIRE_WEBKIT=1`).

## Stakeholders

- **The operator** (the sole user of an install). They want a desktop app they
  can resize freely, set up without a manual, and trust with access to their
  machine.
- **New users of the v1.0.0 desktop release.** Their first ten minutes are the
  setup path this mission rewrites.
- **GleepGlorp.** It answers "what does this page do?" from the app guide, so
  every label and flow change has to land in the guide in the same flight.

## Constraints

- **The control library owns UI.**
  - A new or changed control is an `App.ui` factory in `static/js/ui/`, with
    a row in `docs/ui-control-inventory.md` and contract tests
    (`tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`).
  - No HTML-string sinks, and no retired-API calls outside `js/ui/`.
  - New test ids are registered in `docs/ui-testid-registry.md`.
- **No change to agent capability.**
  - Built-in tool defaults, the `enabled_tools` semantics
    (`agent/config.py`), tool descriptions and parameter schemas, and
    `SECURITY-MODEL.md` stay as they are.
  - Tool descriptions are platform prompt text: changing them would need an
    eval run against `evals/baselines/notes-platform.json`.
  - Consequence lines and capability sentences are UI copy only.
- **Accessibility does not regress.**
  - The contrast gate, forced-colors rules, reduced motion, landmark elements
    (`landmark-elements-over-aria-roles`) and keyboard access hold.
  - `App.ui.drawer` does not manage focus today. Any overlay this mission
    adds or reuses at narrow widths moves focus in on open, returns it to the
    trigger on close, and closes on Escape; whether that lands in
    `App.ui.drawer` itself or a narrow-only wrapper is Flight 1's call.
- **Every webview is supported.** Packaged builds run WKWebView on macOS,
  WebKitGTK 4.1 on Linux and WebView2 on Windows. Layout features must work in
  all three; the contracts lanes run with `THE_ONE_REQUIRE_WEBKIT=1`. Prefer
  viewport `@media` and `matchMedia`, as the drawers do. A container query
  needs a pinned minimum WebKitGTK version (2.40).
- **The guide moves with the UI.** Every label, page or flow change updates
  `the_one/gleepglorp/guide/*.md` in the same flight. The `App.ui.emptyState`
  migration also edits `tests/_ui_ownership_allowance.py`.
- **Recorded decisions are reversed on the record.** DD14 and the Accent
  restraint rule (Flight 3) and DD7's push default (Flight 7) are reversed
  only with the operator's sign-off noted in the flight log and the
  `the_one/agents.md` text updated in the same flight.
- **Test rules.**
  - No committed visual baselines: snapshots and golden files are gitignored.
  - Browser tests navigate through `tests/browser/_nav.py`, `_lists.py` and
    `_chats.py`.
  - Relabels, recounts and restyles are shared-list changes (squawk 0334).
    Before choosing gate lanes, grep `tests/` (including
    `tests/browser/design_tokens.py`) for the old labels, counts and token
    values. A loose count found about 50 files matching the tool-count text
    and about 50 matching the "No … yet." lines; recount them per flight.
- **Safety rules.** Dev and HAT instances use port 8486 or above (8490 or
  above for the scratch tools) with a scratch data directory under `$HOME`,
  never 8484 or 8485 or the default data directory.
- **Out of scope.**
  - New chat features (retry, edit-and-resend, regenerate).
  - Phone layouts below 624px.
  - Changes to tool defaults.
  - A visual redesign or new brand.

## Environment Requirements

- Host-native dev per `CLAUDE.md`: the repo `.venv` on Python 3.12
  (`uv sync --all-extras --frozen --python 3.12`; uv picks 3.15 by default,
  and `watchfiles` has no 3.15 wheel), `make up` on a non-default port, and
  `THE_ONE_DEV_MODE=true` for the `mock` provider in HATs.
- Playwright Chromium and WebKit for the browser lanes, through
  `scripts/run-tests.sh` (`make test-browser`, at most 3 lanes at once).
  `THE_ONE_TEST_NETNS=1` applies on the WSL host only.
- `scripts/ui_capture.py` gains 640 and 624 widths (Flight 1).
- Desktop-window checks at the minimum size on at least one packaged webview
  (macOS WKWebView or Linux WebKitGTK) for the narrow-width flight.

## Open Questions

- ~~**The narrow layout.**~~ **Resolved (Flight 1):** below `900px` (`(max-width: 899px)`),
  `#app-sidebar` closes by default and opens as a left overlay (`280px` /
  `min(300px, calc(100vw - 72px))` for lists, `min(260px, calc(100vw - 72px))`
  for Settings) via a rail toggle button (`rail-sidebar-toggle`), closing via
  its Close button, `Escape`, clicking `#main-content`, or route navigation.
  Because `#main-content` never unmounts on toggle, route leave guards and
  dirty editors work identically to desktop without extra back navigation.
- ~~**Overlay exclusivity.**~~ **Resolved (Flight 1):** `App.narrowShell` acts as
  the single overlay coordinator for `#app-sidebar`, `#chat-drawer`, and
  `#gleepglorp-drawer`. Below their overlay breakpoints (`< 900px` for
  sidebar, `< 1280px` for right drawers), opening any overlay closes the
  others first, moves focus inside the opened overlay, and `Escape` / Close
  returns focus to the trigger control (when switching overlays, focus follows
  the newly opened overlay).
- ~~**A plain browser below 624px.**~~ **Resolved (Flight 1):** no shell
  `min-width` lock; the layout stays horizontal-scroll-free and crash-free
  below `624px` via fluid CSS bounds (`min(..., 100%)` grids, compact rail
  under `520px`, drawer width capped at viewport/available space).
- ~~**Higher DPI and other platforms.**~~ **Resolved (Flight 1):** CSS layout
  targets `(624, 321)` as the minimum client area (`640×360` outer at 100%
  DPI on Windows/macOS/Linux; higher DPI scales CSS pixels uniformly). Automated
  browser checks verify `(624, 321)` and `(1280, 800)` in Chromium and WebKit,
  plus `< 624px` (`(480, 321)`) overflow safety.
- ~~**Packaged-webview apparatus.**~~ **Resolved (Flight 1):** automated suite
  verifies Playwright Chromium and WebKit (`THE_ONE_REQUIRE_WEBKIT=1`), plus
  `scripts/ui_capture.py` at `624` (`624×321`) and `640` (`640×360`); packaged
  WKWebView/WebKitGTK/WebView2 manual/host verification stays noted as an
  environment-specific follow-up outside unit/Playwright CI.
- **The agent panel default.** M25 F4 DD7 made it open by default in push mode
  (1280px and up). Should push mode default to closed? It already remembers
  the operator's choice. Needs sign-off in Flight 7.
- **What counts as "has a reply".** The schema has no reply count. Does a
  routine run or an API-created session count? Does the checklist come back
  if every provider, agent and chat is deleted? Flight 6 decides.
- **The Library hub when populated.** Is it a status summary (counts, an
  unreachable provider or MCP server), or is the hub dropped once anything
  exists? Flight 7 decides.
- **Capability tiers.** Do MCP stdio servers and Web/Connectors get their own
  tier ("runs programs", "sends data out") beside "acts on this computer"?
  Flight 4 decides.
- ~~**The capability sentence's source.**~~ **Resolved (Architect review):**
  compose it client-side in a shared helper fed by the loaders
  `agent-drawer.js` already uses.
- ~~**Checklist state.**~~ **Resolved (Fable review):** derive it from data
  (providers, agents, a chat with a reply); no `localStorage`, because the
  port fallback changes the origin. If early dismissal is wanted later, it
  goes in `app_metadata` behind the credential gate.
- ~~**GleepGlorp and first-run.**~~ **Resolved (Fable review):** choosing
  GleepGlorp's model is an optional line inside the provider step, not a step
  of its own.

## Known Issues

*(none yet)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [x] **Flight 1: Narrow-window layout.**
  - A viewport breakpoint for the shell and the narrow layout chosen in the
    open question (recommended: list or detail, with a back control).
  - A height strategy for 321px: compact header, composer and transcript
    rules so three lines stay visible.
  - The Settings nav, the tile grid and editors reflow; the agent panel and
    GleepGlorp drawer fit as overlays; one overlay at a time with focus
    in and back.
  - Clear the corner button from every scroll container, including the agent
    editor's tab panel.
  - 640 and 624 widths in `scripts/ui_capture.py`.
  - Browser tests at 624×321 and 1280×800 per the criterion, and a
    packaged-webview check.
  - Goes first: it is a defect in the shipping desktop app, and later flights
    build on the shell it settles.
- [ ] **Flight 2: Motion and quiet controls.** A small blast radius.
  - Every CSS transition on `--motion-*` and `--ease-tactile`, including
    `.app-flash`, with the grep check.
  - A stronger disabled-button style (visibly inert, with contrast pairs);
    disabled-until-dirty and its caption stay.
  - Icon chevrons replace the "▸" glyphs.
- [ ] **Flight 3: Hierarchy and accent.** Broad: it re-runs every lane.
  - Heading roles (page title, section heading in sentence case) and their
    tokens.
  - Reverse DD14: a neutral selection fill with a non-colour cue (rail, list
    rows, tabs) that survives forced colours.
  - Rewrite the Accent restraint rule in `the_one/agents.md`; the accent is
    reserved for primary actions, focus, links and switched-on controls.
  - New contrast pairs in `tests/test_design_tokens_a11y.py`; the gate
    re-verified in both themes and under forced colours.
- [ ] **Flight 4: Agent reach.**
  - The shared capability helper and phrase table, with the fixture-matrix
    test; the sentence on the agent page and in the chat panel.
  - Risk tiers and consequence lines for the built-in categories on the
    Tools tab, per the tiers open question.
  - A quieter category count in place of the uppercase badge.
  - Guide updates for the Agents and Tools pages. Defaults are unchanged.
- [ ] **Flight 5: Names and patterns (mechanical).** Legs in this order, each
  with the squawk 0334 test grep:
  1. The naming pass across the UI and guide (MCP servers, model provider,
     Built-in), the Jump to relabel, and the retired-label grep check.
  2. Every empty state on `App.ui.emptyState`, with the start cards and chat
     welcome named as exceptions.
  3. A single create-action pattern and one toast placement.
  - Goes before first run, so the checklist is built on settled names and
    the settled create pattern.
- [ ] **Flight 6: Guided first run.**
  - A data-derived setup checklist that grows out of `chatPane.guidance(setup)`
    and the Agents and Library start cards (provider → agent → first chat),
    with next-step hand-offs after each create.
  - GleepGlorp's model as an optional line in the provider step.
  - A New Agent form that shows only identity, model and prompt until the
    agent exists, **only if** GleepGlorp's create fill can still reach all
    twelve fill keys; otherwise this item is dropped.
  - The "has a reply" definition, and a HAT state-transition sequence from an
    empty data directory.
- [ ] **Flight 7: De-duplication (product decisions).** Each item needs the
  operator's call before its leg is planned:
  1. The Library hub de-duplicated, per the open question.
  2. The chat header, panel and composer de-duplicated, with composer
     telemetry as a quiet meter with details on hover.
  3. The agent panel's push-mode default (DD7).
- [ ] **Flight 8 *(optional)*: Alignment.** A hands-on session with the
  operator at real window sizes for the adjustments the flights could not
  predict. Possibly GleepGlorp drawer states and motion (listening, thinking,
  filling), built storyboard-first.
