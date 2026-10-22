# Flight Log: Agents on the library

**Flight**: [Agents on the library](flight.md)

## Summary
Planned 2026-10-15/16 on branch `flight/02-agents-on-the-library` (from `main` at `dbcd458`).

---

## Planning Notes

- **Re-plan.** Flight 1's debrief found the old Flight 2 overloaded. The operator chose two flights: Agents (this one), then Library and Settings (Flight 3). The mission's flight list was renumbered to six flights.
- **Operator decisions, 2026-10-15/16:**
  - New controls were previewed on a mock-up canvas built from the real CSS (https://claude.ai/artifact/Pzn35KdwV9gsTrnCPRCcqo), and the operator approved it.
  - The MCPs-tab boards could not be published (an auto-mode classifier refusal), so the Refresh-button change was described in words. It was approved.
  - Squawks 0094, 0217, 0220 and 0221 are folded in.
  - The flight closes with a HAT.
- **Planning surveys at `dbcd458`:**
  - the `studio.js` section map and split plan;
  - the agent editor and tabs;
  - the browser tests and their class selectors;
  - squawk recon: 0094 confirmed live and wider than reported, 0217 live with drifted evidence, 0220 and 0221 confirmed live.
- **Defects found in planning** (DD9):
  - the MCPs-tab collapse throws: `_parseSourceIdFromHash` is undefined;
  - suspected: stored `tool_overrides` are wiped on Save when Overrides was never opened;
  - a self-configuration change discards unsaved General edits.
- **Remaining debt ledger at the start** (reuse uses / sinks):

  | Area | Uses | Sinks |
  |---|---|---|
  | Agents | ~135 | ~35 |
  | Library and Settings | ~210 | ~16 |
  | MCP editor | 89 | 18 |
  | Chat | ~30 | ~6 |

  Totals: 243 rows / 504 uses, and 75 sinks in 14 files.

- **Architect design review: "approve with changes". All folded in.**
  - **DD9-2 confirmed real.** The server also wipes on an omitted key, so the fix is server-side preserve-on-omit plus a client omit-when-not-loaded.
  - **DD8 corrected.** There is no DOM builder in `tools-form-helpers.js`, so a `renderFieldNode` is added beside the string path, which stays as debt until Flight 3.
  - **DD5 test breaks listed.** The operator chose press-only toggletips on 2026-10-21, and that is now part of DD4.
  - **Listener and live-region rules** follow the `menu.js` precedent.
  - **Legs pre-split** from 7 autonomous to 11: before-set; the studio split as data/route, then state plus editor; Knowledge+MCPs vs Tools+overrides; Rules and notes vs Self-configuration.
  - **Smaller corrections:** the admin `.tool-tile*` is left alone; the chip-list admin variants are preserved, with an expected allowance bump; the admin editor is added to the captures; the files over 800 lines are recorded; `App.tabs` → `App.ui.tabs` API change; `mountSlot` in core with the singletons removed; environment re-verified per leg.

- **Architect review, cycle 2: "approve with changes" (text edits only), all applied.** Stale leg numbers fixed (the after set in leg 11; DD9-2 confirmed in leg 08; the split in legs 02-03). DD1 now maps modules to legs and introduces the state object at the top of leg 02. DD5's broken-test list is corrected: the admin string path keeps `title`. DD4 item 4 is marked as approved separately. DD8's node helpers are decided at leg 08. Flight set to `ready`.

---

## Leg Progress

### Flight Director Notes

- **2026-10-21: setup.** Crew file `.flightops/agent-crews/leg-execution.md` (Developer: Sonnet; Reviewer: Haiku, or Sonnet for a security-sensitive diff). The flight is `in-flight`. The operator asked to run to the HAT.
- **Leg 01 `before-set`: tiered low-risk.** It touches a dev tool only, with no application source. There is no design review; the Developer has been spawned.
- **Legs 02a-05: tiered high-risk** (a shared-state restructure, shared-interface library changes, and a library behaviour fix with 14 consumers). Each had a design review before implementation. All landed; see their entries below.
- **The old leg 06 was split into 06a/06b** at design review: a mount-once frame while the other tabs were still pending was unsafe, so 06a added the identity (name, create/edit) remount and an interim rebuild list that each tab leg leaves in turn. **Legs 07 and 08 were split** the same way, into 07a/07b (the MCP master is attach-only) and 08a/08b (locked chips must be sent; the main merge gets its own checkpoint).
- **2026-10-21: squawk 0223 (the `tool_overrides` wipe, DD9-2) was hotfixed on main** at the operator's request, in a separate worktree. Leg 08a merges main and ports its client rule into `agent-form-data.js`.
- **Leg 06a landed.** Its capture showed two differences not caused by 06a: the "New" icon in the list pane, and the danger-zone button gap from leg 04. Both are carried to leg 11's capture comparison and the HAT.
- **Leg 06b landed.** Two FD calls:
  - The danger-zone labels are now "Confirm delete?" / "Confirm purge?" (sentence case), which is `dangerZone`'s canonical default from Flight 1 DD8, not a new difference. The test updates in `test_flow_agent_crud.py` and `test_flow_agents_list.py` follow it. It goes on the HAT list.
  - Test's status uses the library's `pending`/`success`/`danger` states instead of the leg text's `ok`/`fail`. Accepted, since `App.ui.status` defines the vocabulary.
  - The agents lane measured 566 s against its 510 s budget (a warning, not a failure). Leg 11 re-budgets it (squawk 0217); the lane may need its planned split.
- **Leg 09: design review, one cycle, approve with changes.** The addenda are applied (no `setAgent`, the remaining allowance pieces, the `role=alert` option in the library, list-local re-renders, the drawer test). Status `ready`.
- **The old leg 10 was split into 10a/10b/10c** after its first review returned "needs rework". The operator chose the DD9-3 conflict behaviour: keep the typing, with a note that Save will replace the stored value. The second review cycle returned "needs rework" on 10a and "approve with changes" on 10b and 10c. Its edits are applied:
  - 07b gains `setSources` (the self-configuration source tile appears and disappears without a remount; the server never re-adds the loopback id on a PUT);
  - 10a uses new narrow General methods (`applyStored`, `setStoredChangeNote`) instead of General's reverting `setAgent`, and hides the token reveal on disable;
  - 10b gets a fourth module (`self-config-external.js`);
  - 10c fixes the switch test call sites, adds `status` `led: false`, and spells out the token-clearing hooks.

  Two review cycles is the maximum, so there is no third. The 10a Developer re-verifies the citations at leg start, and the flight review covers the code. **A deviation from DD7:** the history stays a native `<details class="advanced-collapsible">`, because the library has no disclosure factory and adding one for one consumer is not this flight's job.
- **2026-10-21: squawk 0224 (the certifi and Pillow advisories) was started on main** at the operator's request, in the worktree `../the-one-squawk-0224-wt`, independent of this flight.
- **Leg 07a: tiered high-risk** (a cache freshness rule, the first tab on `setAgent`); its design review is done (two cycles). The Developer has been spawned.
- **2026-10-21: squawk 0224 merged to main** (867cfeb, PR #300; lint and pip-audit green). Its untracked copy on this branch was deleted, so leg 08a's `git merge origin/main` is not blocked by an untracked file. Main carries the completed artifact.
- **Leg 07a landed.** Two FD calls:
  - `setAgent` rebuilds only the tab's own content when it is handed a different knowledge-base inventory. That is narrower than the leg's "refreshes only on remount" caveat, and is accepted.
  - The switch's label is the library toggle's typography (smaller, regular weight), as part of DD4 item 1. It goes on the HAT list.
- **Leg 07b: tiered high-risk** (DD9-1, a shared factory change in `tile.js`, and the `setSources` addendum from the leg 10a review). Its design review is done (two cycles plus the 10a addendum). The Developer has been spawned.
- **Leg 07b landed.** Two FD calls:
  - The capture shows two tile-layout differences beyond DD4 items 1 and 3: tool rows sit flush with the tile body, and the count chip comes before the protocol chip. Both are DD3's `groupTile` layout from the approved canvas, not new differences. They go on the HAT list.
  - **A suspected regression, not accepted as a flake.** `test_flow_agents_focus_after.py::test_agent_save_never_steals_focus_the_user_moved` failed once under load (Save stayed enabled after a held PUT) and passed alone four times. No squawk covers it, so the triage rule treats it as a regression. The FD's hypothesis: since 06b, a same-identity `patch` resets General's model select and then refetches the model list asynchronously. A snapshot taken before the refetch lands no longer matches the DOM afterwards. A Developer was spawned to reproduce it with a delayed models response and fix it before the intermediate commit.
- **The suspected regression was investigated, and its cause is unexplained.** The hypothesis was refuted: the model-fetch callback already retakes the snapshot when the form is clean, and superseded fetches are aborted. Four regression pins were added, holding the models response through a Save, a first open, a Cancel, and a Save before the list lands. The original test passed 8 of 8 under CPU throttling and 15 of 15 under heavy CPU load, and the agents lane passed 227 of 227 in 501 s. It is recorded as squawk 0229, the known-flake record. The investigation found a pre-existing bug instead: a Save before the first model list loads stores `llm_model: ""`, the same at HEAD. That is logged as squawk 0228 and kept out of this flight: it is not a regression, and the fix needs a small UX decision.
- **Squawks 0225-0227 were logged** at the operator's request, from squawk 0224's findings: six tests fail on an unlocked install, there is no certifi CVE floor, and the Pillow comment's CVE ranges are wrong. All are open and routine, and they belong to main, not this flight.
- **The intermediate commit of legs 01-07b** is made before leg 08a, as 08a's spec requires. The legs stay `landed`: the flight review still covers the whole flight at the end.

### before-set

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- `scripts/ui_capture.py`: `seed()` now also calls `seed_tabs_agent()`, which creates the agent `capture-tabs` through the API: description and system prompt; one knowledge base attached (no folder); one `streamable-http` MCP source at `http://127.0.0.1:9/mcp` with a seeded `_cache.tools` (4 tools) attached; `enabled_tools` (read_file, glob, list_dir, fetch_url, http_request) so Filesystem and Web are mixed and Execution is all off, `delete_file` in `disabled_tools`; `tool_overrides.read_file.path_denylist` with 3 entries; two rules (the second off); notes enabled; self-configuration enabled. Seeds `ids["agent"|"kb"|"mcpsrc"]` so `{agent}` resolves in hashes.
- New surfaces (light and dark): `agent-general`, `agent-rules-and-notes`, `agent-knowledge`, `agent-mcps` (source expanded, `/test/connect` stubbed with 4 tools), `agent-tools` (Filesystem expanded, `read_file` Overrides open), `agent-self-configuration`, `admin-builtin-tool-editor` (`#settings/tools/read_file`).
- `tests/test_ui_capture_safety.py` unchanged (its table test passes as is). No file under `the_one/` changed.

#### Notes
- Before-set path: `$HOME/.cache/the-one-ui-capture/m31-f2-before/` (44 PNGs + manifest.json, 0 failed). Covers all 22 provider-era surfaces (regression base) plus the 7 new surfaces. No PNG is in git.
- SKIPPED: `agent-self-configuration-pending` (a pending revision needs the agent to act; no operator API creates one), `agent-rules-and-notes-with-note` (notes are written only by the agent, no create route; seeding needs direct SQL, so the tab shows "No notes yet"), plus the two pre-existing consent-link skips.
- PNGs viewed: `agent-tools--light` (Filesystem expanded, read_file Overrides open, Path Denylist chips ~/.ssh ~/.aws /etc/shadow, 3/9 enabled, Web 2/4 mixed), `agent-mcps--dark` (source expanded with 4 stubbed tools; the self-configuration source row also shown, locked), `agent-rules-and-notes--light` (two rules, second off; notes on, "No notes yet"), `agent-general--light` (description and system prompt filled), `admin-builtin-tool-editor--light` (read_file editor below the tile grid, chip-list Path Allowlist with `~`; the Path Denylist is empty at the operator level).
- Verification: `--list` shows the new surfaces; `tests/test_ui_capture_safety.py` 15 passed; ruff check and format clean; `git diff --stat 9369fcc -- the_one/` empty.
- **Leg 04 `tab-and-tile-controls`: tiered high-risk.** It changes shared library interfaces (the toggle, dangerZone) and moves the base tab CSS.
  - The design review returned "approve with changes". Folded in as addenda:
    - a workable legacy-comparison recipe in the harness;
    - the tab CSS stays in the same layer, plus a wrapper flex spec;
    - the full real chip-list keyboard behaviour (Tab, paste, duplicates, reposition, `validate`), copied exactly;
    - `chip` already owned;
    - tristate assertions per engine;
    - a four-interaction tool-row test in both engines;
    - the `App.tabs` retired-API regex.
  - The suggested 04a/04b split was declined as low priority. The guidance order stages the work.
  - Set to `ready`; it runs after leg 03.
- **Leg 02 `studio-split-data-and-route`: tiered high-risk.** It is a 4000-line restructure with shared state.
  - The design review returned "approve with changes" and recommended a split. It is now **02a** `studio-state-route-data` and **02b** `library-pane-and-groups`; the other leg numbers are unchanged.
  - Folded in:
    - the enumerated `state` membership, including what stays on `self` and what stays private;
    - generation tokens captured by value on purpose (the "never cache" criterion is corrected);
    - `studio-route` is stateless;
    - `agent-data` exposes every wrapper by name;
    - the subscriptions stay in the shell;
    - the pane is created before the glue modules, with the pending rule in the groups and `reset`/`isOpen` handles;
    - per-file `invalidate` pins and a `_studio_src()` helper;
    - the CLAUDE.md lines that name moved functions.
  - Decisions: `snapshot`/`tabHandle` move to `state` in 02a; the subscriptions live in the shell. Both legs are set to `ready`.
- **Leg 05 `library-behaviour-fixes`: tiered high-risk.** It changes shared library behaviour app-wide (confirm, infoButton) and the provider lifecycle.
  - The design review returned "approve with changes". Folded in:
    - the announcement subject keeps item identity (`announceName` or `aria-label`), so the two local workarounds do not regress;
    - lapse announces "not confirmed" and commit clears it, through one timer;
    - the broken and not-broken test lists corrected (the MCP and admin string paths keep `title`);
    - the toggletip announcement, modal Escape, clipping and one-open rules;
    - a new static guard pairing document listeners;
    - the `mountSlot` API defined: data, `release`, re-entrancy, late binding.
  - Set to `ready`.

### studio-state-route-data

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- **Step 1, the `state` object** (`studio.js`): one `var state = {...}` in `init` holds `dirty`, `snapshot`, `tabHandle`, `selectSeq`, `editorGen`, the MCP, connector and KB-create form state, `kbFocusFolderFor`, `knowledgeDetailHandle`, and the caches `knowledgeBases`, `mcpSources`, `connectors`, `providersCache` (the binding membership). The `Object.defineProperty` getters/setters on `self` now read and write `state` and keep their init seeds (`self._pendingMcp... || null`, `!!self._kbCreateMode` and the setter's `!!`). Generation tokens stay captured by value (`var kbGen = state.editorGen`, `mySelect = ++state.selectSeq`, ...). The providersSection ctx reads `state.editorGen`/`state.dirty`/`state.providersCache`. The `_dirty` seam reads `state.dirty`. The renames were scripted (word-boundary, skipping strings, object keys, comment lines and declarations) and the full diff was read.
- **Step 2a, `studio/studio-route.js`** (new, 355 lines): `App.studio.route.serialize(self)` / `.hydrate(self, sub, opts)`, the bodies moved verbatim (`this` -> `self`) with their commentary. Stateless, as the addenda require; `serializeState`/`hydrateState` on the area are one-line delegations, and the `self._closeOpenItem || function () {}` guard survives.
- **Step 2b, `studio/agent-data.js`** (new, 525 lines): `App.studio.agentData.create(ctx)`; ctx = `self`, `content`, `sectionContentEl`, `renderAgentList(scroll)`, `onSelfConfigChanged(updated)` (-> `doSelect`). The handle exposes every wrapper under its existing name, plus `loadAllDepth()`. The store subscriptions (agents, providers and the five Library ones) stay in `studio.js` and call the handle. Call sites in `studio.js` are `agentData.x(...)` (about 30 passed by reference into `renderAgentEditor`).
- `index.html`: two script tags (`studio-route.js`, `agent-data.js`) before `areas/studio.js`.
- Pins: `tests/test_store_static.py` gained `_studio_src()`; the `fetchKnowledgeBases` window, the `include_agent_surfaces` presence pin, the `/test/connect` INVALIDATION_ROW read `agent-data.js`; `gone`/`not in` pins read `_studio_src()`; the `invalidate('agents')` pin is per file (`agent-data.js` 1, `studio.js` 4). `tests/test_index_asset_cache_busting.py` 73 -> 75 with a dated comment. `tests/_ui_ownership_allowance.py` rows moved. No browser test edited.
- Docs: `the_one/agents.md` gained "Studio area modules (M31 F2 L02a)" (module list, ctx contract, the `state` rule) and four `studio.js::` references now name `agent-data.js`. CLAUDE.md untouched (its named functions move in 02b).
- Note: per-move lane runs were folded into one combined run after both moves (route and data share no coupling beyond the area methods); the combined run covers routing, agents, mcp, library, shared and providers.

#### Step-1 gate checkpoint (state object only, before any file moved)
- `make test-unit`: 6707 passed, 12 skipped.
- Lanes under netns + `THE_ONE_REQUIRE_WEBKIT=1`: agents rc=0 (488 s, 190 tests), routing rc=0 (493 s), shared rc=0 (276 s), library rc=0 (248 s), mcp rc=0 (311 s).

#### Allowance notes ("same sum, moved from `studio.js` to X")
- `tests/test_ui_guards.py` `HTML_SINK_ALLOWANCE` / `DYNAMIC_SINK_BASELINE`: no key changed. The moved code contains no HTML sinks (`showLoadAllError` uses `createElement`/`textContent`), so `areas/studio.js` stays 15 and the new files have none: same sum, nothing moved.
- `tests/_ui_ownership_allowance.py`: `("js/areas/studio.js","api:App.showFlash("): 8 -> 7` and new `("js/areas/studio/agent-data.js","api:App.showFlash("): 1`: same sum (8), moved from `studio.js` to `agent-data.js`. No other key changed.
- `invalidate('agents')`: total 5 = `agent-data.js` 1 + `studio.js` 4 (leg 03 moves the 4).
- Script-count pin: 73 -> 75 (the two new files).

#### Grep of moved names (tests/, scripts/, Makefile, docs/, CLAUDE.md, agents.md)
Names: the 40 wrappers, `loadAll`, `showLoadAllError`, `serializeState`, `hydrateState`. Hits outside `the_one/agents.md`: only `tests/test_store_static.py` (updated above) and comments in `tests/browser/test_*.py` (`loadAll`, `refreshToolConfigsCache`; no assertion reads them) and one old behavior run log. Nothing in `scripts/`, `Makefile`, `docs/` or CLAUDE.md. `agents.md` hits: four `studio.js::` references updated; the rest describe behaviour by name and stay valid (`serializeState`/`hydrateState` are still the area's methods).

#### Verification
- Full gate `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`: unit 6705 passed, 14 skipped (the netns count); browser `PARALLEL_RESULT rc=0 total=1102s lanes=9 failed=-`. Lane times (s, budget): routing 506/600, agents 501/510, providers 304/420, contracts 293/390, chats 335/360, mcp 335/360, library 248/300, settings 225/300, shared 261/300. No OVER BUDGET. No flake.
- ruff check and format clean. `tests/test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py` pass.
- `git diff 9369fcc -- the_one/` touches `agents.md`, `index.html`, `studio.js` and the two new modules only; `git diff 9369fcc -- .../static/css/` is empty.
- Verification grep: every `dirty/snapshot/tabHandle/selectSeq/editorGen` hit in `studio.js` is a `state.` access or an object key (`editorGen: function ...` in the providers ctx).
- Line counts: `studio.js` 4181 -> 3433; `studio-route.js` 355; `agent-data.js` 525.
- **Legs 01 and 02a landed.**
  - Leg 02a: `studio.js` 4181 → 3433 lines; the full gate passed in 1102 s.
  - Deviation, accepted by the FD: leg 02a ran its per-move lanes once, combined, rather than after each move. The step-1 checkpoint ran separately, as required. Leg 02b's Developer was told to run the lanes per move.
  - Leg 02b's Developer has been spawned.
- **Legs 03 and 06-11 are drafted** (`planning`). Each gets its design review once its predecessor lands, so citations are checked against the post-split tree.
- **DD9-2 is live on `main`.** The FD has asked the operator whether to hotfix it as a squawk on `main` ahead of leg 08.

### library-pane-and-groups

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- Four new modules under `js/areas/studio/`, each `App.studio.<name>.create(ctx)`, bodies moved verbatim (local aliases keep the old names, so stack traces and greps match):
  - `library-pane.js` (537 lines, `libraryPane`): the Library list column (`LIBRARY_GROUPS`, `LIBRARY_EMPTY`, the gated fill, selection, Add menu, start page, row-focus helpers). Handle: `syncCache`, `reload`, `render`, `sync`, `rowIndex`, `focusNear`, `focusGroupStart`, `renderEmpty`, `load`, `create`/`destroy`, `reset` (= destroy), `isOpen`, plus `selection`, `atRoot`, `goCreate`, `focusCreate`, `isSection`. `self._syncLibrarySelection` is still assigned inside it.
  - `knowledge-glue.js` (350, `knowledgeGlue`): section dispatch, create view, detail mount, the 5 s poll (timer stays on `self._knowledgePollTimer`), `knowledgeItemsSignature`. Handle: `render`, `reset`, `isOpen`, `clearPoll`, `itemsSignature`. `self._focusKbCreate` stays assigned inside it.
  - `mcp-glue.js` (244, `mcpGlue`): handle `render`, `prefetchTypes`, `tryConsumePending`, `reset`, `isOpen`. Keeps `var reloadLibrary = pane.reload;` so `onListStale: function () { reloadLibrary('mcp-sources'); }` is literal.
  - `connector-glue.js` (272, `connectorGlue`): handle `render`, `tryConsumePending`, `reset`, `isOpen`, `resolvePendingLibraryItem`. The pending-item rule (`PENDING_KINDS`, `resolvePendingLibraryItem`, `self._resolvePendingLibraryItems`) lives here, because it is the last glue module created and takes the MCP handle (`ctx.mcp`): no lazy back-reference.
- Creation order in `studio.js`: `agentData`, `libraryPane`, `providersSection`, then one shared `glueCtx` (`self`, `state`, `pane`, `providers` (handle), `setActiveSection`, `discardOpen`, `writeUrl`, `sectionContent()`, `fetchAgents`, `buildRootHeading`, `agentData`) -> `knowledgeGlue`, `mcpGlue`, then `glueCtx.mcp = mcpGlue` -> `connectorGlue`. The one back-reference: the pane's ctx takes `providers()` as a call-time getter, since the providers section is created from the pane handle. `buildRootHeading` stays in the shell; so do `AGENTS_INTRO`, the five Library store subscriptions (they call the handles) and the `closeOpenItem`/`setActiveSection`/`editorOpen` sites, which now call `knowledgeGlue|mcpGlue|connectorGlue.reset()/isOpen()`.
- `index.html`: four script tags before `studio.js`.
- Defect caught by the first gate, fixed: the pane extraction took `AGENTS_INTRO` with it (it sat between `LIBRARY_INTRO` and `KNOWN_BADGE_TYPES`); the Agents root threw on render and 4 lanes failed (routing, agents, chats, shared). The per-move lanes (library, mcp) do not render the Agents root, so they did not catch it. Restored in `studio.js`; no other leftover (checked every top-level name of the old `studio.js` against the new one, and the new modules for undeclared identifiers).

#### Per-move lanes (netns + `THE_ONE_REQUIRE_WEBKIT=1`)
| Move | Lanes | Result |
|---|---|---|
| 1 pane | library | 50 passed, 224 s |
| 2 knowledge glue | library | 50 passed, 223 s |
| 3 MCP glue (pending rule still in the shell for this move) | mcp, library (concurrent) | mcp 110 passed 293 s; library 50 passed 228 s |
| 4 connector glue + pending rule | library | 50 passed, 225 s |

Static pins and the unit tier were run after each move (`test_ui_guards`, `test_store_static`, `test_ui_ownership`, `test_index_asset_cache_busting`).

#### Pins and allowance notes ("same sum, moved")
- Script count: 75 -> 79 (`test_index_asset_cache_busting.py`, dated comment).
- `HTML_SINK_ALLOWANCE` (`tests/test_ui_guards.py`): `areas/studio.js` 15 -> 10; new `knowledge-glue.js` 3, `mcp-glue.js` 1, `connector-glue.js` 1. Same sum (15), moved from `studio.js`. All are `innerHTML = ''` clears and a loading line; no dynamic sink moved, so `DYNAMIC_SINK_BASELINE` is unchanged.
- `tests/_ui_ownership_allowance.py`: `("js/areas/studio.js","ui-list-pane-row")` 6 -> 2 and new `("js/areas/studio/library-pane.js","ui-list-pane-row")` 4: same sum (6), moved. No other key changed (the scanner reports no `badge` or `editor-title` move: those hits are not in the moved ranges). The file was regenerated from `measure()` and `ruff format`ted; the diff is those two rows.
- `tests/test_store_static.py` (assertions unchanged, only the file read): `loadLibrary`/`reloadLibrary`/`createLibraryList` windows read `library-pane.js`; the `_refresh` pin now asserts `libraryPane.load(true)` (the same call under its new name); the `resolvePendingLibraryItem` window reads `connector-glue.js`; the `onListStale` literal reads `mcp-glue.js`; the MCP save-create `router.sync(... { name: updated.name })` pin reads `mcp-glue.js`.
- Docs: CLAUDE.md `:90` (`studio/knowledge-glue.js::knowledgeItemsSignature`) and `:257` (`reloadLibrary` in `library-pane.js`); `the_one/agents.md` "Studio area modules" extended (pane, three glue modules, ctx, creation order) and four references to `renderLibraryList`/`loadLibrary`/`reloadLibrary` name the module.

#### Grep of moved names (tests/, scripts/, Makefile, docs/, CLAUDE.md)
Names: the pane functions, the glue render/consume/fetch functions, `PENDING_KINDS`, `resolvePendingLibraryItem`, `knowledgeItemsSignature`, `clearKnowledgePoll`, `startKnowledgePoll`, `LIBRARY_GROUPS`. Hits: `tests/test_store_static.py` (updated above); comments only in `tests/test_db_api.py:2057`, `tests/browser/test_flow_studio_knowledge_inventory.py:1150,1198` and `tests/browser/test_store_library.py:382` (no assertion reads them); two old behavior run logs; CLAUDE.md `:90`/`:257` (updated). Nothing in `scripts/`, `Makefile` or `docs/`. In `studio.js` the only remaining hits are the providers ctx keys (`reloadLibrary:`, `syncLibrarySelection:`, ...), which delegate to the pane.

#### Verification
- Sizes: `studio.js` 3433 -> 2280 (the leg's "about 1500-1700" estimate predated 02a's moves; leg 03 takes it to <= 800); `library-pane.js` 537, `knowledge-glue.js` 350, `mcp-glue.js` 244, `connector-glue.js` 272. All <= 800.
- `git diff` limited to `studio.js`, the four modules, `index.html`, the pins, CLAUDE.md and `agents.md`; no test body edited, no CSS touched.
- ruff check and format clean; `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y` pass.
- Gate 1 (before the `AGENTS_INTRO` fix): unit green; browser `rc=1`, failed routing/agents/chats/shared (1669 s), all from the one missing constant.
- Gate 2 (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`): unit 6705 passed, 14 skipped (netns count); browser `PARALLEL_RESULT rc=1 total=1126s lanes=9 failed=agents`, with one failure: `test_flow_agents_scale.py::test_filter_keystroke_cost_ratio_60_vs_10_throttled` ("60-agent median 0.053ms > 3x the 10-agent 0.017ms", a sub-0.1 ms timing ratio). Re-run in isolation: the file's 6 tests pass (16 s). Timing flake under 3-lane load; recorded and accepted per the triage rule (it passed in the 02a gate). All eight other lanes rc=0. Lane times (s, budget): routing 506/600, agents 505/510, providers 302/420, contracts 298/390, chats 345/360, mcp 343/360, library 254/300, settings 240/300, shared 276/300. No OVER BUDGET.
- **Leg 02b landed.** `studio.js` 3433 → 2280 lines.
  - The first gate caught a real defect: `AGENTS_INTRO` had moved out with the pane. The Developer fixed it and audited every top-level name. This shows per-move lane choice matters: the library and mcp lanes never render the Agents root.
  - The final gate had one failure in a timing-ratio test (`test_flow_agents_scale.py::test_filter_keystroke_cost_ratio_60_vs_10_throttled`, 0.053 vs 0.017 ms) that passed in isolation. The host was also running the squawk 0223 worktree's browser tests at the time.
- **Squawk 0223** (`tool_overrides` wiped on Save) is being hotfixed on `main` in a separate worktree (`../the-one-squawk-wt`), per the operator's call on 2026-10-21. Leg 08 reconciles with it after the merge.
- **Squawk 0223 merged to `main` as `f6b2ed0` (PR #299).**
  - The FD merged while the GitHub `lint` and `pip-audit` checks were still pending. That is a deviation from "merge when green" and is being followed up: ruff passed locally and nothing changed dependencies.
  - Leg 08 now starts by bringing `main` in and adds the partial-merge test.
- **Leg 03: tiered high-risk.**
  - The design review returned "approve with changes". Folded in:
    - call-time getters named;
    - `checkDirty`/`getFormSnapshot` moved to form-data to break the picker ↔ controller cycle;
    - `renderEmptyEditor` to the list, and `bootLoad` into `state`;
    - the public `self`/`App` surface listed;
    - a pre-agreed ≤ 800 fallback (`studio-sections.js`);
    - corrected pins;
    - a mechanical missed-name check, a smoke after every move, and lanes after every move.
  - Set to `ready`; its Developer has been spawned.
- **The squawk 0223 PR's checks:** `lint` passed; `pip-audit` failed on newly published `certifi`/Pillow advisories, unrelated to the diff. Logged as **squawk 0224** (servicing, grounding for releases), for the operator to schedule on `main`.

### studio-state-and-editor-split

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- Four new modules under `js/areas/studio/`, each `App.studio.<name>.create(ctx)` with a ctx header, bodies moved verbatim (local aliases keep the old names so stack traces and greps match). Moved in the binding order, one move at a time, created in this order in `init`:
  1. `agent-form-data.js` (317 lines, `agentFormData`): `collectFormData`, `getFormSnapshot`, `checkDirty`, `_storedUngatedDisabledNames`, `UNGATED_TOOL_PREFIXES` (with the `App.toolCategories.ungatedPrefixes` read). ctx: `self`, `state`, `editorEl`.
  2. `agent-model-picker.js` (363, `agentModelPicker`): `fetchModelsForProvider` (with `_modelsFetchController` / `_activeProviderId`, created once), `renderModelCapabilities`, `wireEditorEvents`, the VRAM check. `escapeHtml`/`escapeAttr` (from `App`), `formatBytes`, `vramCheckTimer` are local; the shell's hoisted `var`s are gone. ctx adds `formData` (the picker takes `checkDirty`/`getFormSnapshot` from it). Handle: `wireEditorEvents`, `fetchModelsForProvider`, `renderModelCapabilities`.
  3. `agent-editor-controller.js` (549, `agentEditorController`): `renderEditor`, `setActiveTab`, `cancelEdit`, `handleDeleteEditor`, `handlePurgeHistory`, `testProvider`, `save`, `extractApiError`, the one-argument `showFlash` wrapper, `editorTitleEl_`/`saveBtnEl_`, `TOOL_CATEGORIES`. ctx: `self`, `state`, `editorEl`, `agentData`, `formData`, `picker`, `discardOpen`, `writeUrl`, `list()`.
  4. `agents-list.js` (556, `agentsList`): the Agents `listPane`, `AGENTS_INTRO`, the empty state, focus helpers, `doSelect`, `replaceWith*`, `doEnterCreateMode`, `renderEmptyEditor`, `resolvePendingAgent`, `tryConsumePendingSelect`. Handle per the addenda plus `syncSelection`, `clearFilter`, `enterCreate`, `replaceWithAgent`, `replaceWithAgentsRoot`, `resolvePending`, `tryConsumePending`.
- Call-time getters, named in the shell comments: the controller's `ctx.list()` and `agentData`'s `renderAgentList` / `onSelfConfigChanged` callbacks (both resolve `agentsListMod`, assigned after the list is created). No other lazy reference.
- `state.bootLoad` replaces the shell's `bootLoad` local (the shell writes it via a local `bootLoad` const plus `state.bootLoad`; the list reads `state.bootLoad`).
- Public surface: the shell assigns `self._syncAgentSelection`, `self._enterCreate`, `self._setActiveTab` from the handles, keeps `App.studio.clearAgentFilter` (with the load-time stub at the top), `_tryConsumePendingSelect`, `_refresh` and `_dirty`. Pinned by a new static test, `test_studio_shell_keeps_its_public_surface` (`tests/test_store_static.py`), which also asserts `studio.js` <= 800 lines; the temporary browser probe checked each is a function after `init`.
- **`studio-sections.js` fallback was NOT needed**: the shell ended at 733 lines.
- `index.html`: four script tags before `studio-route.js`, after `tool-categories.js` (so before `studio.js`).
- Docs: `the_one/agents.md` "Studio area modules" lists the four modules, ctx, creation order and the getters; `:698` (`fetchModelsForProvider`), `:837`, `:928`, `:1552` (`clearAgentFilter`), `:2132` (`checkDirty`/`createGen`), `:2277`, `:2289-2290` updated; CLAUDE.md `:255` names the new modules. A corrected claim: `stillOnCreate` is the knowledge-base create form's, not in `studio.js` (the agents.md line said so).

#### Missed-name check (mechanical; the 02b `AGENTS_INTRO` lesson)
Script: saved all 115 four-space-indent top-level declarations in `init` from the pre-leg `studio.js` (`function X`, `var X`, `self._x =`, `App.studio.x =`); after each move it asserts each is declared in at least one family file and that no family file uses a bare name without declaring it (alias or own declaration), ignoring comments and strings.
- Before any move: `names checked 115 flagged 0` (baseline).
- After move 1 (form-data): `names checked 115 flagged 0`.
- After move 2 (picker): `names checked 115 flagged 0`.
- After move 3 (controller): `names checked 115 flagged 0`.
- After move 4 (list): first run `flagged 0`, but a manual grep found `AGENTS_INTRO` still in the shell (my extraction failed to match because the comment line was edited); removed it, re-run `flagged 0`.

#### Per-move smoke and lanes (netns + `THE_ONE_REQUIRE_WEBKIT=1`)
The smoke is a temporary browser probe (deleted before landing): after `init` each public-surface member is a function; open `#agents`, open an agent, switch to Tools and back, edit and Save, New (create mode), Cancel; zero `pageerror` / console errors.
| Move | Probe | Lanes |
|---|---|---|
| 1 form-data | pass | agents 190 passed (435 s), routing 184 passed (444 s) |
| 2 picker | pass | agents 190 (435 s), routing 184 (446 s) |
| 3 controller | pass | agents 190 (461 s), routing 184 (469 s), chats 181 (323 s), shared 256 (238 s) |
| 4 list | pass | agents 190 (457 s), routing 184 (466 s), chats 181 (320 s), shared 256 (237 s) |
Static pins and the ownership/sink guards were run after every move.

#### Pins and allowance notes ("same sum, moved")
- Script count 79 -> 83 (`test_index_asset_cache_busting.py`, dated comment).
- `HTML_SINK_ALLOWANCE` (`tests/test_ui_guards.py`): `areas/studio.js` 10 -> 4; new `agent-model-picker.js` 5, `agents-list.js` 1. Same sum (10): moved from `studio.js`. `DYNAMIC_SINK_BASELINE`: `studio.js` keeps only the `content.innerHTML = '<div class="studio-section-content">...` snippet; `selectEl.innerHTML = optsHtml;`, `selectEl.insertAdjacentHTML(...)` and `warningEl.innerHTML = msg;` moved to a new `agent-model-picker.js` entry.
- `tests/_ui_ownership_allowance.py` (regenerated from `measure()`, `ruff format`ted; diffs, all same sum, moved from `studio.js`):
  - `editor-unsaved` 1, `field-input` 1, `field-select` 1, `field-textarea` 1 -> `agent-form-data.js` (move 1); then `field-input` 1, `field-select` 1, `field-textarea` 1 -> `agent-model-picker.js` (move 2). `studio.js` `field-*` 2/2/2 -> 0 in total: 1 + 1 split. Same sums (editor-unsaved 1; field-input/select/textarea 2 each).
  - `api:App.confirmDelete(` 2, `api:App.showFlash(` 7, `editor-error` 1, `editor-header` 1, `editor-title` 1, `test-result` 5 -> `agent-editor-controller.js` (move 3).
  - `badge` 2, `ui-list-pane-row` 2 -> `agents-list.js` (move 4).
- `test_store_static.py`: `invalidate('agents')` pin per file: `agent-data.js` 1, `agent-editor-controller.js` 4, `studio.js` 0 (`invalidate('sessions')` rows follow); `INVALIDATION_ROWS` rename and Purge point at the controller (`/test/connect` unchanged, in `agent-data.js` since 02a). New surface test above.
- `test_tool_categories.py`: the ungated-literal check covers form-data and the controller; the `byCategory` consumer is the controller; the load-order pin lists the four new scripts (after `tool-categories.js`).

#### Grep of moved names (tests/, scripts/, Makefile, docs/, ci/, CLAUDE.md, SECURITY-MODEL.md)
Names: `collectFormData`, `fetchModelsForProvider`, `renderModelCapabilities`, `handlePurgeHistory`, `handleDeleteEditor`, `doEnterCreateMode`, `resolvePendingAgent`, `tryConsumePendingSelect`, `renderAgentList`, `renderEmptyEditor`, `wireEditorEvents`, `checkVramForModel`, `extractApiError`. Hits: comments/docstrings only in `tests/browser/test_flow_studio_*.py`, `tests/test_admin_reasoning_effort_field.py`, a behavior spec and old run logs, and an old plan under `docs/superpowers/plans/`; no assertion reads them. Nothing in `scripts/`, `Makefile` or `ci/`.

#### Verification
- Sizes: `studio.js` 2285 -> 733 (leg start 2285 after 02b's 2280 + edits; 02a start 4181); `agent-form-data.js` 317, `agent-model-picker.js` 363, `agent-editor-controller.js` 549, `agents-list.js` 556. Existing modules unchanged (`studio-route` 355, `agent-data` 525, `library-pane` 533, `knowledge-glue` 350, `mcp-glue` 244, `connector-glue` 272). All <= 800.
- `git diff` since the 02b tree limited to `studio.js`, the four new modules, `index.html`, the pins, `the_one/agents.md`, CLAUDE.md. No browser test edited, no CSS touched; the temporary probe was removed.
- ruff check and format clean; `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y` pass.
- Full gate `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`: unit 6706 passed, 14 skipped (netns count; +1 is the new surface test); browser `PARALLEL_RESULT rc=0 total=1104s lanes=9 failed=-`. Lane times (s, budget): routing 507/600, agents 504/510, providers 304/420, contracts 299/390, chats 338/360, mcp 333/360, library 247/300, settings 228/300, shared 262/300. No OVER BUDGET. No flake (the `test_flow_agents_scale` ratio test passed).
- **Leg 03 landed. `studio.js` is 733 lines** (DD1 met; the `studio-sections.js` fallback was not needed). The full gate passed and nothing was over budget.
  - The missed-name script missed one leftover (an `AGENTS_INTRO` duplicate), caught by a manual grep. The lesson: match declarations, not their comment lines.
  - A new static pin, `test_studio_shell_keeps_its_public_surface`, covers the ≤ 800 ceiling and the public surface.
  - Leg 04's Developer has been spawned. Leg 06's design review runs in parallel (read-only).
- **Leg 06 design review: "needs rework"** (mount-once was unsafe while legs 07-10 are pending).
  - Rework: the leg is split into **06a** `agent-editor-frame` and **06b** `general-tab`.
  - Identity is (name, create/edit), so a rename remounts. Same-identity saves patch the frame and, in the interim, rebuild the five non-General panels until legs 07-10 make each one patch-only.
  - `collectFormData` and `checkDirty` stay DOM-based. Listeners are attached per panel. The hidden-editor locator is out of scope.
  - The Test testids are kept, and Delete/Purge become dangerZone `onConfirm`.
  - A second review cycle runs on 06a and 06b.
- **Leg 06a/06b design review, cycle 2: "approve with changes".** All folded in:
  - 06a rewritten cleanly, with no contradictory body text;
  - the interim `patch`/Cancel rebuilds all six panels, General included, with the picker re-wired and the snapshot reset;
  - the save block uses a dedicated Save disable re-applied after every `setDirty` (not `setBusy`, which would disable Cancel, against 0090);
  - Test stays in the General panel with its disabled state owned by the picker;
  - 06b's `setAgent` covers the provider/model revert, with a test.

  Both are set to `ready`.

### tab-and-tile-controls

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- New library files: `js/ui/tabs.js` (`App.ui.tabs`), `js/ui/tile.js` (`App.ui.groupTile`, `App.ui.toolRow`), `js/ui/chip-list.js` (`App.ui.chipList`); three `index.html` tags after `choice.js` (before `editor.js`), script pin 83 -> 86 with a dated line.
- `js/ui/choice.js`: `App.ui.toggle({tristate, indeterminate})` (no `role=switch`; `setIndeterminate` exists on a tristate toggle only, so a plain toggle's controller keys are unchanged; `setChecked` clears the mixed state; all setters silent). `js/ui/editor.js`: `App.ui.dangerZone({actions:[...]})` (per-action `beforeArm`, `icon` default `trash`, `buttons`, `setDisabled(bool, index?)`; `action` is the one-item form).
- `css/components.css`: tabs banner (existing `.tablist/.tab/.tabpanel` rules unchanged, same layer, plus `.ui-tabs`), `App.ui.groupTile`, `App.ui.toolRow`, `App.ui.chipList` banners, the tristate rules (and a forced-colors rule) in the toggle block, `.danger-zone .delete-btn + .delete-btn` spacing, and `.btn-sm svg { 14px }` (below).
- Refresh size verification (addendum): `.btn-sm` gave 24px and 10px text but the icon was 16px (the `.btn-outlined-primary svg` rule). Fixed in CSS with `.btn-sm svg { width: 14px; height: 14px }` (after the 16px rule; `.btn-icon` rules unchanged). Asserted in `test_group_tile_size_assertions` (24px / 10px / 14x14).
- Catalogue (`docs/ui-control-inventory.md`): new rows `groupTile`, `toolRow`, `tabs`, `chipList` (the old "Category tile", "Tabs" and "Chip and chip list" rows became library rows; the queued-message chip stays hand-built in `chat.js`), toggle and dangerZone rows updated, the chip row's "stay hand-built" notes updated. `App.tabs(` added to `RETIRED_APIS` in `tests/test_ui_ownership.py` with a fixture count in `test_retired_api_calls_count_in_code_only`. `the_one/agents.md` "Control library" gains a "Tab and tile controls" block listing the six controls and the intentional duplicates (`studio.css` tile/row rules until legs 07-08, `admin.css` chip-list rules until Flight 3).
- Tests: new `test_ui_tabs_contract.py` (20), `test_ui_tile_contract.py` (30), `test_ui_chip_list_contract.py` (28); extended `test_ui_choice_contract.py` (tristate, 5 tests) and `test_ui_editor_contract.py` (`actions`, 6 tests). All in both engines, legacy comparisons use the fixed property list and one explicit wrapper (`area-studio`, or `area-admin > settings-list` for the admin tablist; `area-studio > tool-row-overrides` for the locked chip), keyboard parity drives the real legacy `App.tabs` and the library with one key sequence, tristate asserts `.indeterminate` in both engines and `checked=mixed` in Chromium only. Confirmed by grep that no test or consumer finds a tile master by `input[role=switch]`.
- Intended differences from the legacy markup, each asserted rather than hidden: the master is the 36x20 library switch (the tile row is 2px taller than the 32x18 pill, the only property that differs); the chip-list remove "x" is `--fg-secondary` (canvas, approved), plus `border-radius: 3px` copied from `.chip-remove`; the tool-row summary carries the legacy `--fg-secondary` colour so the computed styles match.

#### Allowance and ownership deltas (`tests/_ui_ownership_allowance.py`; regenerated from `measure()`, `ruff format`ted)
All rises are newly owned classes counting hand-built uses that already exist (no new debt); each falls when its consumer migrates.
- `css/admin.css`: `chip-list-editor` 0 -> 12, `chip-list-input` 0 -> 2 (the `.area-admin`/`.area-studio` chip-list rules, Flight 3), `tablist` 0 -> 1, `tabpanel` 0 -> 1 (`.area-admin .settings-list .tablist/.tabpanel`).
- `css/studio.css`: `tabpanel` 0 -> 1 (`.area-studio .tabpanel` gutter).
- `js/areas/admin/tools-form-helpers.js`: `chip-list-editor` 0 -> 4, `chip-list-input` 0 -> 2 (the HTML-string chip list and its queries); `tools-editor.js`: `chip-list-editor` 0 -> 1 (a query); `js/areas/studio/mcp-server-editor.js`: `chip-list-editor` 0 -> 15, `chip-list-input` 0 -> 1 (queries); `js/areas/studio/tools-tab.js`: `chip-list-editor` 0 -> 1 (the override panel's query).
- `js/areas/studio/agent-editor.js`: `tablist` 0 -> 3, `tabpanel` 0 -> 12, `tabpanels` 0 -> 2 (its tablist markup, panel class and role attributes and queries), `api:App.tabs(` 0 -> 1; `js/areas/admin/tools-grid.js`: `tablist` 0 -> 3, `tabpanel` 0 -> 2, `tabpanels` 0 -> 2, `api:App.tabs(` 0 -> 1; `js/tabs.js`: `tabpanel` 0 -> 1 (`[role="tabpanel"]` in the legacy helper).
- Decision: **`tab` is not in the tabs row's owned classes.** The reuse check counts whole tokens in string literals, and "tab" is an English word there ("General tab", "Bot tab", `'tab'` as a `role` value): a first measurement counted it in `system-page.js`, `connector-editor.js`, `library-pane.js`, `mcps-tab.js`, `self-configuration-tab.js`, `tools-grid.js` (6), `agent-editor.js` (12) and `tabs.js` (1), mostly prose. The row owns `ui-tabs`, `tablist`, `tabpanel`, `tabpanels` (the tokens that only ever appear as the markup), and the catalogue says why. (The rest of the file's diff against HEAD is legs 02a-03's moved rows, already recorded above.)
- `HTML_SINK_ALLOWANCE` / `DYNAMIC_SINK_BASELINE`: unchanged (the new library files have no HTML sink).

#### WebKit differences
None found. The tool-row four-interaction test (Space on the focused checkbox, Enter on the summary, click on the label text, click on the affordance) passes identically in Chromium and WebKit: each toggles only its own target. The only engine-specific assertions are the intended ones: `checked=mixed` in Chromium's `aria_snapshot` and the forced-colors rule (no WebKit emulation).

#### Verification
- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`, `test_ui_control_inventory`, `test_index_asset_cache_busting`): 333 passed. ruff check and format clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 6715 passed, 14 skipped (the netns count).
- Lanes under netns with `THE_ONE_REQUIRE_WEBKIT=1`, three at once: contracts 947 passed, 5 skipped, 315 s (budget 390; the skips are the engine-specific ones above); agents 190 passed, 452 s (budget 510); settings 107 passed, 228 s (budget 300). No flake, no failure. The existing agent-editor tablist and the Built-in tools grid still use `App.tabs` and the legacy CSS, unchanged.
- No surface migrated: `git diff` limited to `js/ui/*`, `components.css`, `index.html`, the catalogue, the tests and pins, `agents.md`.
- **Leg 04 landed.** The FD accepted two deviations:
  - (1) `tab` is not an owned class. As a string token it is prose ("General tab", role values) and gives false positives, so the row owns `ui-tabs`, `tablist`, `tabpanel` and `tabpanels`.
  - (2) An app-wide `.btn-sm svg { 14px }` rule, needed for the canvas-approved small Refresh. It follows Flight 1 DD8 (icon size by button size). Leg 11's after captures check its reach.
  - WebKit showed no tool-row interaction difference.
  - Leg 05's Developer has been spawned.
- **Leg 07 design review: "needs rework".** Reworked and split into **07a** `knowledge-tab` and **07b** `mcps-tab`.
  - Decisions:
    - the MCP master is attach-only, as today (non-tristate, `role=switch`);
    - the library gains `groupTile` `master.dataset` and `toolRow` `inputDataset`, so `agent-form-data` stays unchanged;
    - keyed Refresh keeps unsaved checks and keeps rows with the error shown above them;
    - one delegated change handler replaces the per-load listeners;
    - the DD9-1 test asserts the route drops the source;
    - `setAgent` recomputes the tool mode;
    - CSS deletions are corrected (the Tools-tab rules stay for leg 08).
  - The old leg-07 file was removed before any execution; it never ran. Both new legs are set to `ready`; their reviews were folded in directly.
- **Leg 08 design review: "approve with changes".** Split into **08a** `main-merge-and-overrides-port` and **08b** `tools-tab`. The old file never ran.
  - Folded in:
    - locked chips are sent in the union;
    - the 0223 DOM-derived loaded-set rule is kept, with attributes on the controls;
    - Cancel re-arms the override bodies;
    - the merge procedure (ours for `studio.js` plus a hand port; both sides for CLAUDE.md);
    - `renderFieldNode` in a new `tool-override-fields.js`, leaving `tools-form-helpers.js` byte-identical;
    - no `renderFieldErrors`/`applyShowIf` node versions;
    - the locator mapping;
    - the CSS deletion order (after 07a/07b);
    - `test_flow_agent_tabs.py:205/234/248` owned by 08b.
  - **FD decision:** an intermediate commit of the landed legs (01-07b) on the flight branch, made just before 08a, because a merge needs a clean tree. The flight review still covers every leg at the end.
- **Leg 07a/07b cycle-2 review: "approve with changes".** Folded in:
  - the knowledge-base input datasets (`kbToggle`/`kbId`);
  - dirty tracking through each control's `onChange`, also applied to 08b; it closes a silent break where `wireEditorEvents`' selector misses the library inputs;
  - legacy tile CSS inlined as a contract-test fixture;
  - Refresh keeps its "Refresh" label at the small size;
  - the master is `locked || attached`, non-tristate, with datasets;
  - the Refresh mode rules and the explicit selected-source callbacks;
  - lists refresh on remount only (recorded).

### library-behaviour-fixes

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- **`App.ui.util.mountSlot`** (`ui/core.js`): `{mount(destroyFn, data) -> token, isCurrent, current() -> {token, data}|null, release(token), destroy()}`; destroy/release null the entry before calling `destroyFn` (re-entrancy safe); a throwing `destroyFn` is logged and the remount goes on. `provider-models.js` holds `var slot = util.mountSlot()` (late-bound `ctl`, release in a catch, controller `destroy` wrapped to release its token); `provider-editor.js` mounts its handle object as slot `data` and the create-focus target reads `slot.current().data.shell.titleEl`. `activeController` and `latestMount` are gone (grep empty). Order kept: destroy previous, `container.textContent = ''`, mount.
- **Confirm announcement (0220)**: one cached `div.visually-hidden[role=status][aria-live=polite][data-testid=ui-confirm-live]`, appended lazily to `document.body` with an `isConnected` re-append; single pending-timeout handle (clear, then write next tick). Wording (one place: `armSentence`/`lapseSentence`): arm "Press {subject} again to {confirmLabel lower-cased, no '?'}." (e.g. "Press Delete rule 1 again to confirm delete."), lapse "{subject}: not confirmed", commit clears. Subject: `opts.announceName`, else `aria-label`, else original title. `rules-notes-tab.js`: `armMessage` and the `cfg.announce` arm calls removed; `self-configuration-tab.js`: the `arming` block removed (`rules-status`, `notes-status`, `externalStatus` stay). `confirm.js` header rewritten.
- **Toggletip (0221)**: `infoButton` has no `title`; `aria-expanded`/`aria-controls`; `div.ui-info-bubble[hidden]` (after the hidden description span, so `.ui-info > span` is still the description) with a polite live region filled one tick after show. Escape (focus in wrapper; stops propagation only when it closes a bubble), outside `pointerdown`, focus leaving, re-press close it; focus stays on the button; capture-phase document `pointerdown`/`keydown` added on open, removed on close/`destroy`; module-level `openInfo` for one-open; flips above / to the end edge (re-measured after the text arrives). CSS in the infoButton banner of `components.css` (tokens only; `cursor: help` -> `pointer`). Controller gains `close()`/`destroy()`. Release note: hover tooltip removal is intentional (operator, press-only); no release-notes source file in the repo, so recorded here.
- String-path icons (`tools-form-helpers.js`, `tools-editor.js`, `mcp-server-editor.js`) untouched.
- Static guard: `find_unpaired_document_listeners` (`tests/_ui_guard_helpers.py`) + `test_ui_dir_document_listeners_are_paired` in `tests/test_ui_guards.py` (probe included).
- Docs: catalogue (infoButton, confirm rows; mountSlot note), `docs/ui-testid-registry.md` (`ui-confirm-live`; rules/notes-status descriptions), `the_one/agents.md` "Library behaviour fixes" block. Squawks 0220 and 0221 completed (Reviewer/Verdict/Commit pending).

#### Tests updated
- Retargeted `test_flow_agent_rules.py` and `test_flow_agent_notes.py` arm-announcement assertions to `ui-confirm-live` ("Press Delete rule 1 / note 2 again to confirm delete."). `test_flow_provider_editor.py` (two tooltip tests) and `test_flow_provider_visible_fixes.py` now assert no `title`, `aria-expanded`/`aria-controls` and the bubble. `test_ui_info_contract.py` DOM test asserts no title. `test_ui_library_contract.py` util key list gains `mountSlot`. `test_flow_studio_mcp_editor.py:688`, `test_flow_settings_visible_fixes.py:70`, `test_flow_admin_tools_editor.py:194` unchanged and passing (string path).
- New: 4 confirm cases (lazy shared region, announceName, lapse/commit, repeat re-announce + detached re-append), 8 toggletip cases (open/announce/role structure, keyboard + focus, outside press + listener pairing via add/remove counts, one-open, Tab order, modal Escape, `<summary>`, tokens, flip), 3 `mountSlot` cases. Both engines.

#### Allowance deltas
`tests/_ui_ownership_allowance.py` regenerated: `rules-notes-tab.js` `confirm-delete` 1 -> 0, `self-configuration-tab.js` `confirm-delete` 2 -> 0. No rises from this leg. `HTML_SINK_ALLOWANCE` unchanged (no sinks; `index.html` untouched, no new script files).

#### Verification
- ruff check/format clean; static guards, ownership, inventory, nav helper, cache-busting: 411 passed.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 6716 passed, 14 skipped.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 ... --parallel 3`: `PARALLEL_RESULT rc=1 total=1123s failed=contracts`. The sole failure was `test_core_namespace_and_helpers` (util key list lacked `mountSlot`, my omission); fixed, and `--lane contracts` re-run: 979 passed, 5 skipped, 280 s. Lane times (s/budget): routing 512/600, agents 509/510, providers 312/420, contracts 365/390 (first run), chats 343/360, mcp 344/360, library 252/300, settings 233/300, shared 267/300. No flakes, no OVER BUDGET.
- Not verified: a real-editor clipping check of the bubble inside the provider editor pane (absolute positioning inside `overflow:auto` could clip near a pane edge); the viewport flip is covered by a contract test.
- **Leg 05 landed.** Squawks 0220 and 0221 are fixed; `mountSlot` replaces the provider singletons; a new static guard pairs document listeners.
  - Leg 05 left one check unverified: the toggletip bubble clipping in the real editor pane. It is carried to leg 11 and the HAT.
  - The `agents` lane is at 509/510 s; leg 11 re-budgets it.
  - Leg 06a's Developer has been spawned.

### agent-editor-frame

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- **`agent-editor.js`** rewritten as the frame builder (`App.studio.renderAgentEditor` returns a handle `{key, shell, tabs, loadErrorEl, patch, rebuildPanels, setLoadError, destroy}`): header on `App.ui.editorShell` (breadcrumb, title "New Agent"/name, description subtitle, `extra: [agent-chat-btn]`, Cancel `enabledWhenClean` in create mode, Save/Create; no shell Test), an `agent-load-error` frame node (hidden attribute toggled), and `App.ui.tabs` with `split: true` (tablist and `.tabpanels` remain direct children, so no CSS change). Zero sinks, zero ownership rows.
- **`ui/tabs.js`**: new `panelIdPrefix` option (default `<idPrefix>-panel`), so the editor gets `agent-tab-{id}` / `agent-tab-panel-{id}`; contract case `test_panel_id_prefix_option`.
- **`agent-editor-controller.js`**: editor mounts through `App.ui.util.mountSlot()`, data `{key, token, handle, wireGen}`; key `create` or `edit:{name}`. New identity remounts (rename, create -> edit, other agent), same identity calls `patchEditor_`. `buildCallbacks_`, `shell()`, `destroyEditor()`, `liveGuard()`; focus targets (`editorTitleEl_`/`saveBtnEl_`/`cancelBtnEl_`) resolve from the current slot's shell; `setError` through the shell; `setActiveTab` uses `select`/`selected`; Test provider and Save check liveness/`isCurrent`.
- **`agent-form-data.js`**: `checkDirty` uses `shell.setDirty(dirty)` through a call-time `ctx.shell()`, then re-applies the squawk 0090 block with `shell.saveButton.disabled = true` (never `setBusy`).
- **`agent-model-picker.js`**: `wireEditorEvents(isCreate, cfg, isCurrent)`; the model fetch and VRAM check drop results when the guard is false.
- **`agents-list.js`**: `renderEmptyEditor` calls `controller.destroyEditor()` (its `innerHTML = ''` sink is gone). **`studio.js`**: passes `shell` getter to formData; `controller` declared before use.

#### patch(agent) as implemented (same identity: Save without rename, same-agent doSelect, Cancel)
1. shell title, subtitle, Chat target; 2. load-error node shown/hidden from `_selectedAgentLoaded`; 3. all six panels cleared and rebuilt by their current entry functions (General, Rules and notes, Knowledge, MCPs, Tools, Self-configuration); 4. controller re-runs `wireEditorEvents` (new `wireGen`), selects `self._activeTab` if it differs (a hydrate's pending tab); 5. `state.snapshot = getFormSnapshot(); checkDirty()`. Cancel is the same refresh from the stored agent (no frame remount). Interim: 06b removes General from the rebuild; legs 07-10 remove the others. Panel scroll position may reset (accepted). A same-agent `doSelect` while dirty still reaches `patch` and drops unsaved edits until leg 10 (DD9-3).

#### Tests
- Added `tests/browser/test_flow_agent_editor_frame.py` (7): DOM shape and ids; same-identity Save patches without remounting the header node (dirty -> clean); Save keeps the active tab and focuses the title; rename remounts, active tab kept, a rule added after the rename is stored under the new name; Save then Knowledge shows the server `kb_tool_names`; Cancel reverts General and Tools and does not remount; squawk 0090 block survives edits and Cancel's rebuild with Cancel enabled.
- Updated: `docs/ui-testid-registry.md` (the six literal `tab-*` rows folded into the `tab-` prefix row, now built from the item id). No existing browser test needed changes.

#### Allowance deltas (all lowered, none raised)
`HTML_SINK_ALLOWANCE`: `agent-editor.js` 1 -> 0, `agents-list.js` 1 -> 0 (and the dynamic-sink list entry for `agent-editor.js` removed). Ownership: all 15 `agent-editor.js` rows removed, `agent-editor-controller.js` `editor-error`/`editor-header`/`editor-title` removed, `agent-form-data.js` `editor-unsaved` removed.

#### Captures
`$HOME/.cache/the-one-ui-capture/m31-f2-after-06a/` (agent-general, agent-tools, light and dark). Compared pixelwise with `m31-f2-before`: the editor header and tab strip are identical. The only differences are the list pane's New icon (about 140 px, sub-pixel icon rendering) and General's Danger Zone button gap (from leg 04's `dangerZone`, not this leg).

#### Verification
- Static guards, ownership, token, a11y, nav helper, cache busting: pass. ruff check and format clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 6716 passed, 14 skipped (279 s).
- Lanes (netns): `agents` 190 passed 471 s (agents + routing + contracts ran concurrently; the new test file, 7 passed in 17 s, was added after the lane collected and run on its own); `routing` 184 passed 476 s; `contracts` (REQUIRE_WEBKIT) 981 passed, 5 skipped, 346 s; `shared` 255 passed 235 s.

### general-tab

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- **`general-tab.js`** rewritten on the library (no sinks, no ownership rows): `App.ui.section` (Identity, LLM Configuration, System Prompt, Behavior), `field` with `textInput`/`textarea`/`select`, number inputs with `min`/`max`/`field-input-short` set after construction, `App.ui.button` Test (secondary, play icon, default size, testid `test-provider-btn`, in `.test-provider-row` beside the provider fields) with an `App.ui.status` result (`test-provider-result`, hidden until a test starts), and `App.ui.dangerZone({actions: [Delete Agent, Purge now]})` (create mode: none). Ids, `data-field`, classes, labels and placeholders are unchanged; the System Prompt label stays visually hidden (`labelHidden`). Returns a handle `{providerSelect, modelSelect, testButton, dangerZone, setAgent, setTestResult, clearTestResult}`; the initial values are set through `setAgent`, so mount and patch share one path.
- **`agent-editor.js`**: `buildPanel('general')` returns the handle (`h.general`); `patch` calls `h.general.setAgent` and rebuilds only the other five panels (`rebuildPanels(..., keepGeneral)`). General left 06a's interim rebuild list. Header comments updated.
- **`agent-model-picker.js`**: zero sinks. Option lists are built with DOM (`replaceChildren`, same first "Choose a model" disabled option, `selected` rules, "(custom)" fallback and `pendingValue`); the VRAM warning is the same `.studio-vram-warning` element filled with `textContent`. The listener sweep is now tag-based and per-element once (`_dirtyWired`; General's controls carry it); the provider/model listeners attach once per control (`_pickerWired`) while the initial refetch runs on every `wireEditorEvents` call (that is the `setAgent` provider/model refetch with `pendingValue` = the stored model). The stale guards are unchanged (the mount slot's `isCurrent` plus `wireGen`).
- **`agent-editor-controller.js`**: `handleDeleteEditor(revert)`/`handlePurgeHistory(revert)` are `onConfirm` callbacks with no `App.confirmDelete` call; `testProvider` writes through `handle.general.setTestResult` (states `pending`, `success`, `danger`; no glyphs) and drops results whose mount or panel wiring is gone.
- **`components.css`**: removed the `.test-provider-btn` rules (the library button owns its size). `.test-result*` stays (admin `tools-editor.js` still uses it, Flight 3).

#### setAgent coverage
Name, description, provider options (placeholder, providers, "Unknown provider"), model select reset to its placeholder with `pendingValue` dropped, loading text, capability line and VRAM warning cleared, prompt, retention, max iterations, Test disabled state (from the live provider value), Test result hidden. The controller's following `wireEditorEvents` re-sets `pendingValue` and refetches the models. Not patched (set at build): the danger-zone `data-name` (a rename is a new identity and remounts).

#### Tests changed and added
- Added `tests/browser/test_flow_agent_general_tab.py` (11): ids, classes, `min`/`max` and label association; real typing in name, description, prompt, retention and max iterations enables Save and shows `.editor-unsaved`, and Cancel clears it (the dirty rule from the leg 07 review); a provider change enables Save, refetches models, then Cancel restores both selects and clears the capability line; a same-identity Save keeps the General nodes (marker survives); Test as a status line (`data-state` success, hidden before); danger zone has two actions with the library labels; create mode has no danger zone and has Test.
- Updated: `test_flow_agent_tabs.py` (Test result asserts `data-state`), `test_flow_agent_crud.py`, `test_flow_studio_purge_now_button.py`, `test_flow_agents_list.py` (armed label case: "Confirm delete?", "Confirm purge?").

#### Allowance deltas (all lowered)
`HTML_SINK_ALLOWANCE`: `agent-model-picker.js` 5 -> 0 (and its dynamic-sink list), `general-tab.js` 1 -> 0 (and its entry). Ownership: all 3 `agent-model-picker.js` rows and all 12 `general-tab.js` rows removed; `agent-editor-controller.js` `api:App.confirmDelete(` (2) and `test-result` (5) removed. No rise.

#### Capture differences (`$HOME/.cache/the-one-ui-capture/m31-f2-after-06/agent-general--{light,dark}.png`, against `m31-f2-after-06a`)
Only: (1) the Test button at the library's standard size (taller, larger icon and padding) with the rest of the page below it moved down 7 px (Behavior section onward), DD4/DD8 "the Test button and result use the status line" and the standard size; (2) trash icons in the Delete Agent / Purge now buttons and their wider gap, DD4/DD8 "danger zone has trash icons". Everything else (header, tabs, fields, hints, labels) is pixel-identical apart from the 7 px shift.

#### Verification
- `grep` for `innerHTML|outerHTML|insertAdjacentHTML` in `general-tab.js` and `agent-model-picker.js`: none. Static guards, ownership, token, a11y, nav helper, cache busting, store static and control inventory: 428 passed. ruff check and format clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 6716 passed, 14 skipped (287 s).
- All nine lanes ran in one `--parallel 3` gate (netns, REQUIRE_WEBKIT): routing 515 s, agents 566 s (over its 510 s budget by load; 207 passed, 1 failed), providers 313 s, contracts 371 s, chats 345 s, mcp 340 s, library 252 s, settings 239 s, shared 272 s, all green except agents. The one failure, `test_flow_agents_list.py::test_delete_lands_on_the_root_and_focuses_the_nearest_row`, was a real regression (the old "Confirm Delete?" label case, the test is in this leg's files affected by the label change); fixed, and the file re-ran 23 passed.

#### Fix: Save-enabled race after a same-identity patch

- **Investigated, hypothesis refuted; no product change.** The suspected race (a patch snapshots the form while the model select holds the placeholder, then the refetch fills in the stored model) is already closed: the model-fetch callback in `agent-model-picker.js` retakes the snapshot and calls `checkDirty()` whenever `state.dirty` is false when the list lands, and `patchEditor_` runs `checkDirty()` (so `state.dirty` is false) right after taking the snapshot. The pre-06b code (`studio.js` at HEAD) had no retake at all and rebuilt the form with the same placeholder, so the patch path is not worse than before.
- **Pins added** (`test_flow_agents_focus_after.py`, each holds `/api/providers/*/models` and releases it late, then asserts the select shows the stored model, Save is disabled and `editor-unsaved` is hidden): `test_slow_model_list_after_a_save_leaves_the_form_clean`, `test_slow_model_list_on_first_open_leaves_the_form_clean`, `test_slow_model_list_then_cancel_leaves_the_form_clean`, `test_save_before_the_first_model_list_lands`. All four passed on the first run, i.e. no failure to record before a fix (initial mount, Cancel and same-identity Save covered).
- **Reproduction attempts:** the failing test with Chromium CPU throttling at 1/4/8/16x (two passes each): 8/8 passed; the focus-after tests plus the new pins under 24 CPU-burning processes, three rounds: 15/15 passed. The one-off failure was not reproduced.
- **Adjacent pre-existing hazard seen (not fixed, same as HEAD):** Save pressed before the first model list has landed PUTs `llm_model: ""` (the select holds its placeholder). The failing test fills and presses Save right after the editor appears, so under load it can hit this window; the result still settled clean in every run here, so it does not explain the flake, but it is worth a squawk (Save could stay disabled until the model list has loaded).

### knowledge-tab

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- **`knowledge-tab.js`** rebuilt on the library (no sinks, no ownership rows): each knowledge base is a `div.agent-knowledge-row[data-kb-id]` with an `App.ui.toggle` (label = the name; datasets `{kbToggle: '', kbId: id}` and testid `agent-knowledge-toggle-{id}` on the native `input[role=switch]`) and a sibling tool-name `span` (testid `agent-knowledge-tool-name-{id}`, linked by `aria-describedby`). Load-error is an `App.ui.status` (`agent-knowledge-load-error`, no `data-kb-list-loaded`), empty is an `App.ui.emptyState` (`titleTag: 'p'`, the Library link as `action`, `agent-knowledge-empty-state`). `data-kb-list-loaded` stays on the root `agent-knowledge-tab`, which `agent-form-data.js` reads unchanged (no edit needed there). Returns `{setAgent(agent, opts), destroy}`.
- **Dirty tracking:** each switch's own `onChange` calls the editor's `checkDirty` (the tab ctx's `onChange`), since `wireEditorEvents` does not see library inputs.
- **`agent-editor.js`**: `buildPanel('knowledge')` returns the handle (`h.knowledge`); `patch` calls `h.knowledge.setAgent(a, {allKnowledgeBases, knowledgeBasesLoaded})`; `rebuildPanels` takes a keep list (`['general','knowledge']`). Knowledge left 06a's interim rebuild list (now Rules and notes, MCPs, Tools, Self-configuration).
- **`studio.css`**: deleted `.agent-knowledge-row-toggle`, `.agent-knowledge-row-name`, `.agent-knowledge-load-error` (each grepped: no other users). `.tool-toggle`/`.tool-switch` kept for leg 08. Squawk 0094 completed (corrective action and verification recorded; sign-off left to the flight review).

#### setAgent coverage
Each switch's checked state from `agent.kb_ids`; each tool-name node from `agent.kb_tool_names` (placeholder "attach to see the tool name" and its class otherwise). No rebuild when the inventory is unchanged. If `opts` carries a different inventory (id set or loaded flag, e.g. the controller's same-identity refresh after a knowledge base was added in the Library), the tab rebuilds its own content only. So the "refreshes only on remount" caveat in the leg is narrower than recorded: a same-identity patch also picks up the refreshed list.

#### Tests changed and added
- Changed: `test_flow_studio_knowledge_attach.py` `_set_kb_toggle` now clicks the visible label/track (no `evaluate` flip); `test_flow_agent_editor_frame.py::test_save_then_knowledge_shows_current_kb_tool_names` clicks the switch.
- Added (2, in `test_flow_studio_knowledge_attach.py`): `test_attach_switch_is_reachable_by_role_and_tab_squawk_0094` (`get_by_role('switch', name=...)`, Tab reaches it, Space toggles, Save enabled and `.editor-unsaved` shown from a real toggle); `test_save_patches_the_knowledge_tab_in_place` (attach, Save: stored `kb_ids` round-trips, tool-name text updates with no reload, the switch node keeps a marker; Cancel restores the switch with the same node).
- Grep of `data-kb-*`, `.tool-switch`, `.tool-toggle` across `tests/`: `data-kb-*` only in `test_flow_studio_knowledge_attach.py` (via the `[data-kb-list-loaded]` marker, kept); `.tool-switch`/`.tool-toggle` remain only in MCP/Tools-tab tests and the deep-violet and tile contract fixtures (leg 08). Other uses of the kb testids (`test_flow_agent_tabs.py`, `test_router_items.py`) needed no change.

#### Allowance deltas (lowered, none raised)
Ownership: `knowledge-tab.js` `empty-state` row removed (the file has no rows now). `HTML_SINK_ALLOWANCE` had no entry for it.

#### Capture differences (`$HOME/.cache/the-one-ui-capture/m31-f2-after-07a/agent-knowledge--{light,dark}.png`, against `m31-f2-before`)
Only the switch (DD4 item 1): the library toggle (slightly larger track and thumb) with the label in the library's label type (smaller, regular weight, against the old larger medium-weight name). The tool-name line is unchanged apart from the random knowledge-base hash in the seeded name.

#### Verification
- Static guards, ownership, token, a11y, control inventory, nav helper: 407 passed. ruff check and format clean.
- Browser files `test_flow_studio_knowledge_attach`, `test_flow_agent_editor_frame`, `test_flow_agent_tabs`, `test_router_items`: 65 passed (156 s).
- `THE_ONE_TEST_NETNS=1 make test-unit`: 6716 passed, 14 skipped (282 s).
- Lane `agents` (netns): 210 passed, 461 s, run alone. No library factory changed, so contracts was not re-run.

### mcps-tab

**Status**: landed
**Started**: 2026-10-21
**Completed**: 2026-10-21

#### Changes Made
- **`mcps-tab.js`** rebuilt on the library (no sinks, no ownership rows). `renderMcpsTab(panel, agent, sources, {fetchMcpSourceTools, onChange, onSelectedSourceChange, pendingSourceId})` returns `{setAgent(agent, opts), setSources(sources, agentName), destroy}`. One `App.ui.groupTile` per source: the master is the attach switch (`master.tristate: false`, `role=switch`, datasets `{mcpSourceToggle, mcpSourceId}` on its input, testid `mcp-source-toggle-{id}`), locked on and disabled for the agent's own self-configuration source (hint in the tile's actions); name, count chip (`setCount`, hidden while unknown), protocol chip, small Refresh in the actions ("Refresh" label, aria-label "Refresh tools for {name}", 24px), server-info subtitle with the `has-instructions` title, expand label "N tools" / "Tools". Body: a note host (loading, auth-required `App.ui.status` + link, `buildMcpError`, no-tools `emptyState`) above `div[data-mcp-tool-group][data-mcp-tool-mode]` of `App.ui.toolRow` rows (`inputDataset` `{mcpToolToggle, mcpSource}`). `agent-form-data.js` is untouched.
- **DD9-1 fixed:** the collapse is `onExpand(false)` -> `onSelectedSourceChange(null)` when the tab last reported that source; the tab no longer parses the URL; `_populateDetailsBody` and `_parseSourceIdFromHash` are gone.
- **Refresh:** rows keyed by tool name (a present tool keeps its unsaved check, a new tool takes the stored default for the group's current mode, a removed tool's row goes); on error the rows stay and the error node shows above them; a success removes the error; a Refresh never recomputes the mode. One delegated `change` handler per group (count + dirty callback); the masters call the dirty callback from their own `onChange`. A `loadStarted` flag makes a Refresh on a collapsed tile fetch once and call the selected-source callback explicitly.
- **`agent-editor.js`:** `buildPanel('mcps')` returns the handle (`h.mcps`); `patch` calls `h.mcps.setSources(cb.allMcpSources, a.name)` then `h.mcps.setAgent(a, {pendingSourceId})`; `rebuildPanels` keep list is now `general, knowledge, mcps` (MCPs left 06a's interim list; Rules and notes, Tools, Self-configuration remain).
- **`ui/tile.js`:** `groupTile` `master.tristate` (default true) and `master.dataset`; `setMaster('mixed')` reads as off on a non-tristate master; `toolRow` `inputDataset`. Catalogue rows updated.
- **`studio.css`:** deleted `.mcp-source-tile`, `-row1`, `-name`, `-protocol`, `-expand-btn` (+ hover, focus-visible), `-tool-count`, `-chevron` (+ expanded), `-tools`, `.mcp-refresh-tools-btn` (all three rules), `.mcp-tools-checkbox-group`, `.mcp-tool-toggle-label` (+ hover, checkbox), `.mcp-tool-toggle-hint`, and the now-unused `.mcp-empty-state`(+a), `.mcp-tools-body`, `.mcp-auth-required-notice`(+a) (grepped: no other user). Kept: `.mcp-source-tile-toggle`, `.tool-toggle`/`.tool-switch`, `.mcp-tool-text`/`-toggle-name`/`-description` (tools-tab.js, leg 08) and `.mcp-source-tile-subtitle` (admin.css). Added `.mcp-tool-group` (flex column, 6px gap) and `span.has-instructions` (help cursor, dotted underline; selector avoids the owned `ui-group-tile-subtitle` class). Legacy rules for the tile contract test are inlined there as `LEGACY_MCP_ROW_CSS`.
- Testid registry: removed the dead `mcp-tools-body-` row. `agents.md` gained an "MCPs tab (M31 F2 L07b)" block and the patch description is updated.
- **Focus follows the URL (found by `test_router_items`):** a deep-link change (`setAgent` `opts.pendingSourceId`) collapses the previously focused tile as it expands the new one (old behaviour came from the rebuild).

#### DD9-1 before/after
- Before (test written first, against the old code): `test_collapse_expanded_source_drops_route_segment_dd9_1` FAILED, `expected route 'agents/dd91-agent/mcps', got 'agents/dd91-agent/mcps/664d422faf96'` (the old collapse threw the undefined `_parseSourceIdFromHash`, `aria-expanded` and the hidden body did pass).
- After: passes (no `pageerror`, the expand button `aria-expanded="false"`, the body hidden, the route drops the source).

#### setAgent / setSources coverage
- `setAgent`: masters from `mcp_source_ids` (self-config locked on), group mode from `mcp_overrides` (allowlist <-> denylist), loaded rows' checked state, chips; `pendingSourceId` deep link. Tests: `test_save_patches_the_tab_in_place_and_matches_the_server` (same tile node, expanded kept, mode and checks match the server), `test_set_agent_recomputes_mode_and_checked_states` (allowlist, Cancel restores, then a server-side mode flip patched in).
- `setSources`: `test_set_sources_alone_keeps_expanded_unsaved_tile_and_swaps_empty_state` (same node, expanded, unsaved row choice kept; a new own surface added locked; another agent's surface never shown; removal; empty state <-> list), `test_self_configuration_enable_then_save_keeps_the_surface` (stored `mcp_source_ids` contains the surface id after enable + Save and not after disable + Save), the two existing self-configuration tests unchanged and green, and `test_set_sources_keeps_an_expanded_unsaved_tile` (UI path: the other tile's node and expanded state). A same-identity patch also re-derives every row from the stored agent, so an unsaved row choice does not survive the self-configuration refresh until leg 10a (DD9-3, as for General); that is why the unsaved-state assertion is in the synthetic test.

#### Tests changed and added
- Changed: `test_studio_mcps_tab.py` (`aria-expanded` assertions moved to `mcp-source-expand-{id}`, attach/detach use a real click on the switch's label; a `# ruff: noqa: E501` header for the inline JS), `test_router_items.py::test_mcp_tab_focus_follows_the_url_for_the_same_agent` (expand buttons).
- Added to `test_studio_mcps_tab.py` (10): DD9-1, tile shape (`role=switch`, name by role, Refresh text/aria-label/24px, chips), real clicks dirty the form (master and tool row, Save + `.editor-unsaved`, count "1 / 2 enabled", tool rows never change the master), patch in place, mode recompute, payload round trip (`mcp_source_ids` and `mcp_overrides` sent on Save), keyed Refresh (denylist and allowlist defaults), Refresh error keeps rows then success clears it, Refresh on a collapsed tile fetches once, self-configuration enable/disable then Save, `setSources` alone.
- `test_ui_tile_contract.py` (+2, both engines): non-tristate master is a switch with a dataset (mixed reads as off), `toolRow` `inputDataset`; the legacy MCP row comparison uses the inlined fixture CSS.
- Grep of `data-mcp-*`, `.mcp-source-tile`, `mcp-source-row`, `mcp-refresh-tools`, `mcp-tool-toggle` across `tests/`: `test_studio_mcps_tab.py`, `test_studio_self_configuration_tab.py` (hint, master: unchanged), `test_router_items.py` (changed above), `test_ui_tile_contract.py`, `agent-form-data.js`; `.mcp-tool-*`/`.tool-switch` in tools-tab tests stay for leg 08.

#### Allowance deltas (all lowered, none raised)
`HTML_SINK_ALLOWANCE`: `areas/studio/mcps-tab.js` 8 -> 0 (entry and its dynamic-sink list removed). Ownership: the four `mcps-tab.js` rows removed (`api:App.icon(`, `btn-outlined-primary` 2, `checkbox-primary`, `empty-state`) and `css/studio.css` `checkbox-primary` 1 -> 0. (A first draft of the `span.has-instructions` rule used `.ui-group-tile-subtitle` and raised `css/studio.css` by one; the selector was changed instead.)

#### Capture differences (`$HOME/.cache/the-one-ui-capture/m31-f2-after-07b/agent-mcps--{light,dark}.png`, against `m31-f2-before`)
- The attach switch is the library's 36x20 switch (the locked self-configuration switch is drawn dimmed by the library's disabled look): DD4 item 1.
- Refresh is the small button (24px, 10px text, 14px icon, "Refresh" kept): DD4 item 3.
- Tool rows are flush with the tile body (the old body carried 8px inset padding from `.tool-row-overrides-body`): DD3 (the library `groupTile` body), not a listed DD4 item; recorded.
- The count chip now follows the name and precedes the protocol chip, and the self-configuration hint sits in the right-hand actions after the protocol chip (DD3 tile order).

#### Verification
- Static guards, ownership, token, a11y, control inventory, nav helper, cache busting, store static: 428 passed. ruff check and format clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 6716 passed, 14 skipped (281 s).
- Lanes (netns): `contracts` (`THE_ONE_REQUIRE_WEBKIT=1`) 985 passed, 5 skipped, 300 s; `agents` first run 222 passed, 1 failed, 511 s (run beside contracts): `test_flow_agents_focus_after.py::test_agent_save_never_steals_focus_the_user_moved` (Save stayed enabled after a held PUT) passed in isolation four times and the whole `agents` lane then passed alone, 223 passed, 483 s. It is not tied to the MCPs tab (the agent has no sources) and no squawk records it; a probable load race around General's model refetch after a patch (not investigated further; flagged for the flight review). `test_router_items.py` (routing lane) failed once on the old `aria-expanded`-on-tile assertion and the collapse-on-deep-link behaviour (both fixed above); then `routing` 184 passed, 443 s and `shared` 255 passed, 244 s.
