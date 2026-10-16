# Mission: Every control comes from one library

**Status**: active

## Outcome
Every control the app shows has exactly one definition in the shared control library: its markup, its class names, its styles and its keyboard and accessibility behaviour. Each surface, in Chats, Agents, Library, Settings and the shell, builds its controls through that library, and nothing re-creates a control by copying its class names. The current look and feel stays as it is. The difference is that it is now written down in code, so a global change to a control, such as a button, toggle, tile or editor header, is one edit that reaches every place it appears. The old in-app Design language page is gone. The control catalogue and each control's own tests are the reference.

## Context
- **Mission 25 delivered half of this.** Its debrief records the outcome "every control on the redesigned surfaces comes from one reusable control library" as only partly delivered:
  - the shell, lists, navigation, picker, palette, modals and drawer use `App.ui`;
  - the editor bodies kept their old construction and gained only the new chrome.
  - The first action item of that debrief is this mission ("the editor shell and migration").
- **Issue #207 is the operator's write-up of the cost.** Pages are made to match by hand-copying another page's class names, with no record of the dependency. One behaviour (`App.confirmDelete`) has three visual definitions. The danger-zone block is hand-written in five editors, in two idioms (HTML strings and DOM). The `_el`/`_fieldGroup`/`_section` helpers are copied across editors. Restyling one page silently restyles another. #207's warning: a component layer adopted halfway leaves three ways to build a control where there were two, which is worse than today.
- **The control inventory** (`docs/ui-control-inventory.md`) lists about 28 control kinds as "not yet defined, next mission". Among them:
  - the two legacy toggles; the pill toggle removes its input from the keyboard order;
  - info-icon and copy buttons, chips, the key-value table and tabs;
  - the KB item menu, which is hand-built and not the accessible menu pattern;
  - the item-header breadcrumb and unsaved caption, built separately in six editors;
  - entity and category tiles, the status LED and status lines, and the provider model picker and Pull control;
  - the flash message, the two-step confirm, and the chat surfaces (composer, message bubble, thinking indicator, trace, telemetry).
- **The debt, measured (Architect review 2026-10-14; re-measured 2026-10-15 after sortie 04):**
  - About 130 HTML-string sinks across about 25 files. The largest are `mcp-server-editor.js` (24 sinks in 2,153 lines, about 180 lines of string markup), `studio.js` (19), `tools-editor.js` (9), `provider-models.js`, `mcps-tab.js` and `provider-editor.js` (8 each), and `chat.js` (7).
  - `App.icon()` returns SVG markup at 34 call sites. Until an icon can be placed as a node, string sinks cannot reach zero.
  - `studio.js` (4,175 lines) and `chat.js` (2,268 lines, still growing) are monoliths that Mission 25 flagged for splitting.
  - Sortie 04 (2026-10-15) added a new shared block outside the library: `App.consentLink` (`js/consent-link.js`, the MCP sign-in link shown in chat and in the MCP editor). It has its own Copy button and an anchor styled as a button, and the inventory has no row for it yet. It is DOM-built with no sinks, so it migrates rather than being rewritten.
  - Surfaces built after Mission 25 (Date and time, the agent drawer, the picker, the palette) already use the library. The chat area is mostly modular already.
  - Stylesheets: `components.css` 2,117 lines, `studio.css` 1,680, `admin.css` 811.
- **The Design language page is half old and half new.** Nine of its fifteen sections are `App.ui` demos. The other six (Tokens, Typography, Surfaces, Status, Tabs, Markdown) are hand-written mock markup from Missions 08 and 17: a second copy of the vocabulary that nothing tests. The library's contract tests run against their own disk harness, not this page. The page's reach is wider than it looks, though:
  - about a dozen test files and helpers;
  - the pinned script count in `test_index_asset_cache_busting.py` and the Makefile's `verify-serving` file list;
  - the testid registry, the router and Settings page tables, `scripts/webkitgtk_probe.py`;
  - about six behavior specs;
  - `CLAUDE.md` and `the_one/agents.md`.
- **The operator's direction (2026-10-14):**
  - The whole Design language page goes.
  - Nothing is to be redesigned; the look and feel is good.
  - The focus is clean code and completeness: codified, reusable and globally changeable.
  - The few inconsistencies found in passing are resolved by choosing one version, with the operator's approval.
  - Squawks 0094, 0100, 0139, 0190, 0191 and 0192 fold into the migration where it touches their code.
  - No release is cut while the mission is active.

## Success Criteria
- [x] The app has no design-language page. Its route, its Settings navigation entry and its Jump to entry are gone, along with the scripts, styles, tests and spec steps that only it used. The old address shows no page.
- [ ] Every kind of control the app renders is defined once in the shared control library. The control catalogue lists no control as "not yet defined", and every surface (Chats, Agents, Library, Settings and the shell) builds its controls through the library.
- [ ] A change to one control's definition reaches every place that control appears. This is enforced by a unit-tier check that fails when a control's owned class names appear in application code or stylesheets outside that control's own definition. At mission close the check's exception list is empty.
- [ ] No UI markup is built from HTML strings outside the markdown renderer. The unit-tier sink check (assignments to `innerHTML` or `outerHTML`, and `insertAdjacentHTML`) has an empty baseline outside the markdown renderer, and an icon is placed in the page only as a node.
- [ ] Each control's styles are owned by that control, and no area stylesheet restyles a library control (both enforced by the reuse check). Style rules no longer used by any built markup are removed. Each flight reviews an unused-selector report to confirm this.
- [ ] Every migrated surface looks as it did before, in both themes. Before and after captures for each surface are local flight-log evidence, never committed. The operator approves each flight's capture set. Every visible difference is one the operator approved beforehand from the catalogue of resolved inconsistencies, or one of the absorbed squawk fixes, each listed by name.
- [ ] Every library control works by keyboard and by accessibility role in Chromium and WebKit. Each control's contract tests prove its tab order and its role-based reachability. The known gaps are fixed: the pill toggle out of the keyboard order, the knowledge-base attach toggle not reachable by role (squawk 0094), and the knowledge-base item menu outside the accessible menu pattern.
- [ ] The area code is organised by surface. Each editor, tab, section and chat surface lives in its own module, and no area entry module (`studio.js`, `chat.js`, `admin.js`) exceeds 800 lines.
- [ ] The control catalogue documents every control: its options, states and owned styles, plus the tokens and typography the deleted page used to show. Adding a control without a catalogue entry and its contract tests fails the unit gate.
- [ ] Existing behaviour holds. The unit, browser (every lane, both engines for the library contracts) and lint gates pass. The UI-touching behavior specs pass on a dedicated dev instance. Every testid either survives or is recorded as retired in the testid registry.

## Stakeholders
- **Operator** (sole user and maintainer): uses the app daily and wants future UI work (new pages, global restyles) to be one edit rather than a copy-and-adjust hunt. Approves every visible change.
- **Future crews**: build new surfaces from the catalogue, so a new page cannot quietly diverge from the rest.

## Constraints
- **No redesign.** The current look and feel is the target. A visible change lands only as an operator-approved resolution of an existing inconsistency, or as a named absorbed squawk fix.
- **No build step.** The client stays plain ES5 IIFEs loaded by `<script>` tags and attached to `window.App`. There is no bundler, no ES modules and no framework. New controls follow the existing `App.ui` factory mechanism chosen in Mission 25 Flight 1: they return DOM nodes, use no HTML-string sinks and take a caller-supplied testid. Controls that change while shown (streaming chat, live status, progress) return an update handle rather than a static node. Splitting modules adds script tags, so the pinned script count and the `verify-serving` list move with each split as a deliberate bump.
- **No migration that stops halfway.** Each flight leaves every surface it touched fully on the library. No surface ends a flight with a mix of the two ways of building a control. The reuse check's and the sink check's exception lists only shrink. Moving an existing sink while splitting a file is not a new sink.
- **Library rules stay in force:**
  - every control has contract tests in Chromium and WebKit;
  - the contrast gate (`test_design_tokens_a11y.py`) and the token-definition check pass;
  - the testid registry stays in sync.
  - The `contracts` lane's budget is re-measured as controls are added, or the lane is split.
- **Snapshots are never committed.** Before and after captures are local evidence in the flight log. The lasting regression net is DOM-shape assertions, accessibility checks and contract tests.
- **Production safety.** Never drive port 8484 or the operator's default data directory. Captures and live checks use a dedicated dev instance (non-default port and scratch data directory, started from a scratch working directory).
- **Host policy.** At most 3 browser lanes run at once locally (`make test-browser`). The unit suite runs outside the concurrent set. Browser runs and gates on this host use `THE_ONE_TEST_NETNS=1`.
- **Releases.** Each flight lands green on `main`, but no release is cut from `main` while this mission is active. The next release follows mission close.

## Environment Requirements
- Local WSL2 host with the repo venv (`pip install -e ".[all-llms,dev]"`), Playwright Chromium and WebKit (`scripts/setup-webkit-userland.sh`), and `THE_ONE_TEST_NETNS=1` for browser runs.
- A dedicated dev instance (non-default port and scratch data directory) for before and after captures in both themes, with dev mode on so the mock provider can drive the chat surfaces and a provider's model list.
- Optional: the desktop engines for a final check (`scripts/webkitgtk_probe.py` for WebKitGTK; `scripts/windows_test_copy.py` for WebView2 on the operator's Windows desktop).

## Open Questions
- **Patch in place or re-mount?** Should an editor patch its nodes on state changes or re-mount them? Flight 1 settles this on the stateful pilot (the provider editor and its model panel), because the later stateful editors depend on the answer.
- **Where do a control's styles live?** One file per control, or owned sections of `components.css`? The owner must be obvious, the reuse check must be able to read it, and the token-definition and contrast checks must still find every rule.
- **What does the reuse check match?** The working assumption (Architect):
  - each control declares its owned base classes;
  - the check scans application JS and the area stylesheets for them, outside the owner;
  - modifier options passed through the factory are legitimate;
  - it ratchets on a count-anchored exception list, like the existing sink freeze.
  Structural copies (the same DOM shape under new class names) are left to review.
- **Icons.** May the icon table in `icons.js` stay as SVG data behind a single node-returning icon control? The sink is the insertion, not the table.

## Known Issues

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Library completion and a stateful pilot.**
  - Retire the Design language page in an early leg, with every dependency: tests, the script-count pin, `verify-serving`, the registry, behavior-spec amendments and docs. Rewrite the inventory guard's demo rule as "every control has a catalogue entry and contract tests". Move the tokens and typography reference into the catalogue.
  - Settle the open questions: re-mount policy, style ownership, the reuse check and the icon node.
  - Catalogue every variant of each shared shape and get the operator's approval of the canonical choices. This is the checkpoint where the mission's visible changes are decided.
  - Build the shared controls with contract tests: the editor shell (header, breadcrumb, unsaved caption, Save/Cancel with focus-after, error blocks), danger zone, tiles, toggle, info and copy buttons (including the consent link's), chips, the key-value table, tabs, the status LED and line, the flash message, the two-step confirm's visual states and the icon.
  - Land the reuse check with its starting exception list.
  - Migrate the pilot end to end: the provider editor and its model panel (model list, Pull with streaming progress, Test), absorbing squawk 0139.
- [ ] Flight 2: **Forms, tabs and Settings on the library.**
  - The agent editor and its tabs (general, rules and notes, tools, MCPs, knowledge, self-configuration with its approval queue), the connector editor, the knowledge section and Settings' built-in tools, knowledge indexing, appearance, prompts, encryption and date and time.
  - Split `studio.js` and `admin.js` by surface.
  - Absorb squawks 0094, 0100, 0190, 0191 and 0192.
  - Remove each migrated surface's exceptions and orphaned styles.
- [ ] Flight 3: **The MCP server editor on the library.** The largest and riskiest editor gets its own flight, with no other surface in it. It has 24 string sinks, chip and key-value editors mounted after string markup, OAuth popup polling, live connection and protocol status, and masked secrets.
- [ ] Flight 4: **Chats, and closing every count to zero.**
  - Build the chat controls with update handles (composer, message bubble, thinking indicator, trace, telemetry) and migrate the chat surfaces.
  - Split `chat.js`.
  - Drive the reuse check's exceptions, the sink baseline and the catalogue's "not yet defined" rows to zero.
  - Finish the style ownership cleanup.
  - Bring `agents.md`, CLAUDE.md and the catalogue to the final state.
- [ ] Flight 5 *(optional)*: **Alignment.** A vibe coding session: the operator and the agent walk the app together, in both themes and in the desktop window, and make hands-on adjustments.
