# Leg: list-rows-and-mcps-tab

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Show each MCP server's connection state and a Local or Remote badge in the Library list (B6), from the same `App.usage.mcpState` the editor's status line reads, with a test that the two agree. Name each agent MCPs tab tile's Tools button for its server (A20), and fix the agent editor tab label "Built-in Tools" (A21).

## Context
- **Flight decisions:** DD6 (one derivation, two readers; the badge words from B3), DD7 (B6, A20, A21; ledger rows 20, 21, 27), DD10 (derived-relationship criteria).
- **The Library list** (`js/areas/studio/library-pane.js::libraryItem`, about `:215-255`):
  - MCP rows' meta is `App.usage.mcpToolCount(row)`: "Tools not loaded" or "{n} tools", plus "{n} agents";
  - provider rows get `item.badges = [{text: row.type, kind}]`, with `KNOWN_BADGE_TYPES` (`:115`) and the `.badge--{kind}` rules in `components.css` (about `:1929-1940`), each a token pair pinned by the contrast gate.
- **`App.usage.mcpState(source)`** (leg 08a) → `{state: 'signin'|'error'|'connected'|'none', tools, checkedAt}`. The editor's status line (leg 08b) reads it.
- **The MCPs tab** (`js/areas/studio/mcps-tab.js`): each source is an `App.ui.toolTile` with `toolLabel: 'Tools'` (`:219`) and `setToolCount(total === null ? 'Tools' : total)` (`:283`). Every unloaded server's expand button is therefore named just "Tools" (A20). The chips already show `stdio` or `http` (`:206`).
- **The agent editor tabs** (`js/areas/studio/agent-editor.js:41-49`): `{id: 'tools', label: 'Built-in Tools'}`, with the comment "only the visible label narrows to 'Built-in Tools'". Tests and specs that read the label: `tests/browser/test_flow_agent_tabs.py`, `test_flow_studio_tools_tab_patch.py`, `tests/behavior/studio-agent-crud.md`, `tests/behavior/workbench-navigation.md`, `scripts/ui_capture.py`, `README.md` (grep at the start).

## Inputs
- Legs 08a and 08b landed (`mcpState`; the status line; invalidation on every outcome, so the list follows a Test).

## Outputs
- **The Library MCP rows (B6):**
  - **the meta's first part** comes from `mcpState`: `connected` → "{n} tools"; `none` → "Not connected"; `error` → "Couldn't connect"; `signin` → "Sign-in needed". Then " · {n} agents" as today;
  - **a badge** "Local" (stdio) or "Remote" (streamable-http). No new colour tokens: use the neutral `unknown` badge kind (its pair is already contrast-pinned). If the list control needs a different look for these badges, that is a library option in this leg, with a catalogue row and a contract test (DD10). Prefer the existing kind;
  - **the words** come from `App.usage.mcpStateLabel(state)`, which leg 08a adds beside `mcpState` (amended there) and leg 08b's status line already uses. A static unit test pins it: `mcp-connection-status.js` and `library-pane.js` contain none of the four words as literals, so the two readers cannot drift;
  - **an `error` row shows "Couldn't connect" only,** even when tools were cached before (FD decision; the editor's status line carries "last connected {time}"). A `signin` row likewise hides a cached count. Both cases are seeded and tested;
  - **build the MCP meta from one `mcpState` call,** so the tool count and the state cannot disagree. `mcpToolCount` stays for its other readers (the agent and chat drawers).
- **A20, a library option (required; the review confirmed `tile.js:102-110` names the button only by its content):**
  - `App.ui.toolTile` gains `expandLabel`, a function of the current count text that sets the expand button's `aria-label` and is re-applied by `setToolCount`;
  - `mcps-tab.js` passes `function (text) { return text + ' for ' + source.name; }`, which gives "Tools for Docs search" and "3 tools for Docs search". Label-in-name holds, because the name starts with the visible text;
  - when `expandLabel` is set, the button's `aria-describedby` to the name span is dropped, so the server is not read twice;
  - the visible text stays "Tools" or the count;
  - without the option nothing changes: the Tools-tab group tile in `tools-tab.js` is unaffected, which a contract test proves;
  - the tile row in `docs/ui-control-inventory.md` documents it; contract tests in `tests/browser/test_ui_tile_contract.py`, both engines, with the `contracts-controls` lane run.
- **A21:** "Built-in tools" (sentence case). The `tools` id, the testid and the routes are unchanged.
  - No test asserts the label today, so a new test asserts it.
  - The hits to update:
    - `tests/behavior/workbench-navigation.md:46, :50` (steps 6 and 10);
    - `tests/behavior/studio-agent-crud.md:89`;
    - `README.md:68`;
    - `scripts/ui_capture.py:874` (a description);
    - `the_one/agents.md:2170`;
    - the comments in `tools-tab.js:1`, `css/studio.css:34`, `agent-editor.js:46-47`, `test_flow_agent_tabs.py:71, :84, :202, :231` and `test_flow_studio_tools_tab_patch.py:1`.
  - Historical files keep the old text: the mission files and `tests/behavior/**/runs/*.md`.
- **`tests/browser/seeders.py::seed_mcp_source`** (`:195`) gains optional `type` and `url` (streamable-http, for the "Remote" badge), `last_check` and `last_updated`, with existing callers unchanged. `signin` is seeded as `last_check.status == "auth_required"` with no token (no OAuth storage). Check at the start that a streamable-http create with a URL is accepted without a live connect.
- **Tests:**
  - **`tests/browser/test_flow_studio_library_list.py`** (lane `mcp`):
    - **retargeted, never deleted:** `:183-184`, `:207` ("3 tools · 1 agent", "Tools not loaded · 0 agents", `name="alpha-mcp 3 tools · 1 agent"`, which now ends with the badge text) and the "never read zero while agents load" test (`:222-246`, "Tools not loaded" → "Not connected");
    - each seeded state's row meta, including `error` with cached tools and `signin` with cached tools;
    - the badge text by type;
    - **a derived relationship:** for each seeded server, read the row's state word first, then open the editor, assert that no `/test/connect` request fired (only a create auto-runs a Test, and a Test against the fake seeds would record a real error), then compare the status line's word;
  - **`tests/browser/test_studio_mcps_tab.py`** (lane `agents`): each expand button's accessible name contains its server's name, and no two buttons share a name;
  - **if a tile option is added,** `tests/browser/test_ui_tile_contract.py` (both engines);
  - **A21:** the tab's accessible name and visible text are "Built-in tools".
- **B7's agent half** (operator, 2026-10-25: "yes on Delete agent"; leg 05 had left it out):
  - `general-tab.js:220` reads "Delete agent", and its armed label stays "Confirm delete?";
  - the tests that assert the old label are retargeted (`tests/browser/test_flow_agent_crud.py`, `test_flow_agent_general_tab.py`, `test_flow_studio_purge_now_button.py`; grep at the start);
  - the behavior specs `tests/behavior/studio-agent-crud.md` and `agent-purge-now-clears-history.md` are amended (spec text only, never the run logs);
  - the `agent-general` capture shows the change under ledger row 28;
  - lanes `agents` and `agent-tabs`.
- **`tests/behavior/list-and-detail.md` and `the_one/agents.md`** replace "Tools not loaded" with the new wording.
- **Captures:** `mcp-library-list`, `agent-mcps` / `agent-mcps-full` and `agent-general` (the tab bar) into this leg's set. Check that `seed_mcp()` in `scripts/ui_capture.py` gives the list a Remote server, an errored server and a sign-in server (it seeds Docs search, Billing API (rejected), Team calendar and two stdio servers, after seed-time Tests); adjust the seed if not. Differences map to rows 20, 21 and 27 only.

## Acceptance Criteria
- [ ] **The Library rows show the state and badge** for every seeded state, and the row and the editor agree (tested).
- [ ] **A20:** every MCPs tab expand button is uniquely named with its server (tested).
- [ ] **A21:** "Built-in tools" (tested), with every spec and test that read the old label updated, none deleted.
- [ ] **No new colour token,** or, if one was unavoidable, it is in `tokens.css` and passes `tests/test_design_tokens_a11y.py`.
- [ ] **Lanes and files pass:** `mcp`, `agents`, `agent-tabs` (the tabs tests), `contracts-controls` if the tile changed; the static guards; `make test-unit`.
- [ ] **The captures differ only on rows 20, 21 and 27** (FD-checked).

## Verification Steps
- `git grep -n "Built-in Tools" the_one/ tests/ docs/ scripts/ README.md` before and after; only historical mission files keep it.
- The lanes above with `THE_ONE_TEST_NETNS=1`, at most 3 at a time; then the static guards and `make test-unit`.
- The capture compare.

## Implementation Guidance
1. **Tests first:** the row states and badge, the derived relationship, the A20 names, the A21 label.
2. **`mcpStateLabel`, the list rows and the badge.**
3. **A20,** through a tile option only if needed.
4. **A21** and its retargets.
5. **Captures, the ledger and the flight log.**

## Edge Cases
- **A server with no `_cache` at all** reads "Not connected".
- **A pre-flight server** (`_cache.tools`, no `last_check`) reads "{n} tools".
- **The list while `agents` is still loading:** the agent count is left out (today's rule), and the state is still shown.
- **The row's accessible name** includes the meta (today's rule), so a screen reader hears the state too.

## Files Affected
- `js/areas/studio/library-pane.js`, `mcps-tab.js`, `agent-editor.js`, `tools-tab.js` (a comment); `js/ui/tile.js`; `docs/ui-control-inventory.md`.
- `tests/browser/seeders.py`; `tests/behavior/list-and-detail.md`; `the_one/agents.md`; a static unit test for the state words.
- `tests/browser/test_flow_studio_library_list.py`, `test_studio_mcps_tab.py`, `test_flow_agent_tabs.py`, `test_flow_studio_tools_tab_patch.py`, and `test_ui_tile_contract.py` if needed; `tests/behavior/studio-agent-crud.md`, `workbench-navigation.md`; `scripts/ui_capture.py`; `README.md`; the flight log and ledger.

## Citation Audit
- `library-pane.js:115` (`KNOWN_BADGE_TYPES`), `:215-255` (`libraryItem`); `mcps-tab.js:206, :219, :283`; `agent-editor.js:41-49`; `components.css` badge rules about `:1929`. FD grep at the leg 06 working tree (2026-10-25).
- The "Built-in Tools" hits: a grep across the repo (the mission files' historical mentions stay).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes.** Applied in place:
  - A20 needs a required tile option, `expandLabel`, with a contract test (H);
  - the existing list tests that assert the old meta, retargeted (H);
  - the seeder extended for the states (H);
  - the derived test reads the row first and guards against a `/test/connect` (M);
  - A21's real hits listed (M);
  - the `error` and `signin` rows hide a cached count, as an explicit decision with tests (M);
  - `mcpStateLabel` owned by leg 08a, with a static test against drift (L);
  - the capture seed checked (L).
  - **Tier raised to high** (a shared control option). Clarifications and decisions within the design, so there is no second cycle. Status `ready`.
