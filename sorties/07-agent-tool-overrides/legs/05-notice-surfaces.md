# Leg: notice-surfaces

**Status**: completed
**Flight**: [Agent tool overrides](../flight.md)

## Objective
Show an agent's tool-override notices wherever the operator will look (the editor's Tools tab, the tool's override disclosure, the Agents list row and the chat's agent drawer), warn in Settings › Built-in tools before a save narrows any agent, keep every surface current after that save, and bring the docs and release notes in line with the sortie.

## Context
- Flight design decisions implemented here: **DD11** (the `App.ui.tabs` indicator and the list-row indicator), **DD12** (the drawer's notices group), **DD8** (the impact route, the Settings before-save warning and the `agents` invalidation) and **DD14** (docs). Read those sections of `../flight.md` in full: they are the spec. This leg covers charter criterion 3, the half of it that "the agent carries a notice … in the drawer, the tab and the list row; Settings lists the agents a save would narrow".
- **What legs 1-4 delivered** (uncommitted in this tree; see their flight-log entries):
  - `notices` on every agent response (`{kind, tool, field, field_title, dropped, effective, message}`), computed in `the_one/tools/override_validation.py` with the scope filter: only tools enabled for the agent and app-wide, only fields the tab renders.
  - Leg 4's per-field notice line and fixes on the Tools tab.
  - Leg 4's tools-tab handle API `fieldHandles()` / `openTool()`.
  - Leg 2's drawer fix: `renderAgentList` skips `setItems` unless a row signature changes. **The signature must include the row's notice state**, or a notice that appears or clears will not repaint the row.
- **Naming on screen:** the agent editor's tab is labelled "Tools" since M33 F1 L06 (the flight text says "Built-in tools tab"), and Settings' page is "Built-in tools". Notices concern built-in tools only.
- **Acceptable variations used here** (the flight's Adaptation Criteria):
  - The Agents-row indicator rides the existing `badges` and `nameSuffix` item options (a warning `App.ui.badge`/chip with visible text, plus a hidden suffix), with no new `listPane` option. That keeps `ui/list-pane.js` unchanged.
  - The tab indicator's visual form is open, as long as the accessible name reads "Tools, {n} notice(s)".
- **Release notes:** `docs/releases/` has no unreleased file, so this leg assembles the flight log's "Release notes to carry" into one block in the flight log, for the release that ships this sortie. It writes no new version file, because the version is decided at release time.
- **Not in this leg:** the HAT (leg 6).
- **Baseline:** the flight log's list. Legs 1-4 are uncommitted in this tree and are part of this leg's base.

## Inputs
- `static/js/ui/tabs.js` (items `{id, label, testid}`; no indicator) and its contract tests `tests/browser/test_ui_tabs_contract.py`; `docs/ui-control-inventory.md` (the tabs row).
- `static/js/areas/studio/agent-editor.js`: `TAB_ITEMS` `:47` (`tools`), the tab build and `h.toolsTab` `:298-299`.
- `static/js/areas/studio/tools-tab.js`: the per-tool override disclosure rows (`attachOverrides`, `:122+`).
- `static/js/areas/studio/agents-list.js`: `agentItem` (`nameSuffix` `:89`), the row signature `:162`, `renderAgentList` `:184`.
- `static/js/ui/list-pane.js` (`badges`, `nameSuffix`: unchanged).
- `static/js/areas/chat/agent-drawer.js`: `facts` `:292`, `group` `:310`, "What it can use" `:525-528`, `renderContent` `:589`; it reads the agent from `App.store.peek('agents')` `:271`.
- `api.py`: `upsert_tool_config` `:743-830+` (body parse, the `_merge_hidden_fields` (`:620`) and hidden-value fallback block `:789-812`, the validation and 422).
- `static/js/areas/admin/tools-editor.js::save` `:404-435` (PUT); `static/js/areas/admin/tools-page.js` the tile on/off toggle `:313-345` (an `enabled`-only PUT); nothing in `areas/admin/` invalidates `agents`.
- `App.confirmDialog` (the shared confirm dialog) and `App.ui.chip` / `App.ui.badge`.
- Docs per DD14: `the_one/agents.md` (the tool authorship contract, the constraint surface, the Built-in tools tab paragraph, the squawk 0223 rule; a new "Agent override validation and clipping" block); `SECURITY-MODEL.md` (the Tool Execution Boundary, the Windows section); `CLAUDE.md` (the agent-PUT watch-out); `docs/ui-control-inventory.md`. Find each by heading or phrase, not by the flight's line numbers, which predate Mission 33.

## Outputs
- **`App.ui.tabs`:**
  - A per-item `indicator` option (a label string or null).
  - A `setIndicator(id, label | null)` method.
  - Each renders a small dot inside the tab button plus a visually hidden text run, so the accessible name is "{label}, {indicator}" (for example "Tools, 1 notice"). Colour is never the only cue.
  - Its catalogue row is updated (options, owned classes) and its contract tests run in Chromium and WebKit.
- **The `tabs.js` hidden run** is the exact text `", {indicator}"` (with its leading comma) in a `.visually-hidden` span, so the name reads "Tools, 1 notice". The visible label is set with `text: item.label` today, so the indicator is added as sibling child nodes.
- **`App.ui.toolRow`** gains a `flag` option (a Node placed in the summary's label face, after the description) and a `setFlag(node | null)` method. Its catalogue row and a two-engine contract test cover them. There is no header slot today (`ui/tile.js:243`; the `note` option is a construction-time description line).
- **Agent editor:**
  - The Tools tab's indicator ("1 notice" / "{n} notices") and the tools tab's per-tool flags are patched by one small setter, `editorHandle.setNotices(notices)` → `h.tabs.setIndicator('tools', …)` plus `h.toolsTab.setNotices(notices)`. It never goes through `setAgent`, so no form value is re-patched and a dirty form is untouched.
  - It is called on mount and after a save.
  - **It is also called from the studio `agents` store subscription** (`studio.js:588-592`, which today only re-renders the list): a hook finds the selected agent's row in the fresh list and passes **only its `notices`**, never `tool_overrides` or any other field. That makes the editor follow a Settings tightening without a reload. Today only `self._refresh` → `doSelect` updates the editor.
- **Tools tab:** each tool's row carries, through `toolRow.setFlag`, an `App.ui.chip({label: "{n} notice(s)", tone: 'warning', size: 'sm'})` with `data-testid="tool-override-notice-flag"` when that tool has notices. `App.ui.chip` takes `label`, not `text`, and throws without it.
- **Agents list:**
  - A row with notices carries, as a `badges[]` **node** (the `nodeType` branch, `list-pane.js:268`), `App.ui.chip({label: 'Needs attention', tone: 'warning', size: 'sm'})` marked `aria-hidden="true"`, plus the `nameSuffix` text ", needs attention".
  - So the accessible name carries the phrase once. `App.ui.badge`'s kinds are provider kinds only (`ui/feedback.js:7-19`), so a `{text, kind}` badge cannot be a warning.
  - `agentItem` reads `notices`, and the row signature (`agents-list.js:162`) gains the notice count, because a node has no stable value to compare. Update the comment at `:177` that lists the fields `agentItem` reads.
- **Drawer:**
  - A "Needs attention" group (`data-testid="chat-drawer-notices"`) sits between the facts and "What it can use", only when `agent.notices` is non-empty.
  - It shows one sentence per notice (the notice `message`, set as text) and one link "Open the agent's Tools tab" to `#agents/{name}/tools` through the router (`_nav`/`App.router.href`). It is read-only.
- **Impact route:** `POST /api/tools/configs/{name}/impact`, behind the credential gate.
  - **The helper.** The PUT's config computation (`api.py` roughly `:789-858`) is extracted into one helper, `_compute_tool_config_update(cls, name, data, existing_row_or_None) -> (new_enabled, new_config, new_secrets)`, used by both routes so the preview equals what the PUT would store.
    - It covers: the merge with `_merge_hidden_fields`, `model_validate` with the hidden-value fallback, and its `logger.warning`; the 422 raised as today through `_validation_detail` (an `HTTPException`); `model_dump`; and the secret/config split with masked-secret preservation.
    - When `config` is omitted from the body, the stored config and secrets come back unchanged (the PUT's preserve branch).
  - **The comparison.**
    - The route builds the proposed row: `existing.model_copy(update={"enabled": …, "config": …, "secrets": …})`, or, for a tool with no row, a fresh `ToolConfig(name=name, enabled=True, config={}, secrets={})` updated the same way.
    - It swaps the proposed row into the rows list.
    - It computes `compute_notices(cfg, rows)` before and after for every agent, keeping only notices with `tool == name`.
    - **A field is listed** when it has an after-notice and either had no before-notice, or its after `dropped` holds a value not in the before `dropped`. A `dropped: []` notice (the "was any host" case) is listed only when it is new.
    - A notice that only shrinks or disappears is not listed, so a widening or a no-op lists nothing.
    - Disabling the tool yields no after-notices, because of the scope filter.
  - **Known gap, accepted under DD8:** re-enabling a tool through the tile toggle (an `enabled`-only PUT) can add notices without a warning; the warning is on the editor's Save only.
  - The response is `{"agents": [{"agent", "fields": [{"field", "field_title", "dropped"}]}]}`.
  - It reads one rows list and one agents list per request, and runs the clip in `asyncio.to_thread`.
  - An invalid body gets the PUT's 422. An unknown tool gets 404.
- **Settings editor `save()`:**
  - It calls the impact route first, **before** `App.focusAfter.begin` and before `saving = true` (`tools-editor.js:~407-408`), so a Cancel leaves no focus token or busy state behind.
  - A non-empty answer opens `App.confirmDialog({title: "Saving narrows {n} agent(s)", message, confirmText: 'Save anyway', cancelText: 'Cancel', opener})`. Its cancel button defaults to "Stay", so `cancelText` is required.
  - The message lists agent names and fields. Check whether `App.ui.modal`'s `body` accepts a Node: if it does, use a list; if it doesn't, use a plain multi-line sentence.
  - Cancel leaves the form dirty and saves nothing.
  - After a successful save (the host's `callbacks.onSaveSuccess`, `tools-editor.js:~419`, handled in `tools-page.js`) and after the tile's on/off toggle succeeds (`tools-page.js:~323`, its first `.then`), the page calls `App.store.invalidate('agents')`.
- **Docs per DD14**, plus the flight's DD6 text annotated with leg 2's path-form deviation, at its header rather than rewritten.
- **The assembled release-notes block** in the flight log.

## Acceptance Criteria
- [ ] **AC1 — tabs indicator (library).**
  - `App.ui.tabs` items accept `indicator`, and `setIndicator(id, label|null)` adds, changes and removes it.
  - The tab's accessible name becomes "{label}, {indicator}" and returns to "{label}" when cleared.
  - The dot is aria-hidden.
  - Keyboard behaviour and selection are unchanged.
  - Contract tests in `test_ui_tabs_contract.py` pass in Chromium and WebKit (`THE_ONE_REQUIRE_WEBKIT=1`).
  - The catalogue row lists the option and the new owned classes, and `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py` and `tests/test_ui_emitted_classes.py` pass.
- [ ] **AC1b — `toolRow` flag (library).** `flag` and `setFlag(node|null)` place and remove a node in the row's summary label face without toggling the disclosure or the checkbox. Contract tests run in both engines, and the catalogue row is updated.
- [ ] **AC2 — editor tab and tool flag.**
  - An agent with notices on two tools shows the Tools tab named "Tools, 2 notices" (by role and accessible name), and each of the two tools' rows shows its flag.
  - After the operator fixes both (leg 4's Use narrowed value or Reset) and saves, the indicator and flags clear without a reload.
  - With the agent's editor open and **dirty** (an unsaved description edit) in one tab, a Settings tightening saved in another tab makes the indicator and flag appear after the `agents` store refreshes. The unsaved description edit is kept.
- [ ] **AC3 — Agents list row.**
  - The row shows "Needs attention" as visible text, and its accessible name includes ", needs attention".
  - The row repaints when the notice clears: after a fix and Save, it loses the badge with no reload.
  - It repaints when a notice appears: after a Settings tightening, it gains the badge once the `agents` store refreshes.
- [ ] **AC4 — drawer group.**
  - In a chat with an agent that has notices, `chat-drawer-notices` shows each notice's sentence and a working link to the agent's Tools tab.
  - The group is absent when there are none.
  - It appears and clears through the `agents` store subscription, with no reload, when the notices change. That includes going from non-empty to empty, as the list row does in AC3.
- [ ] **AC5 — impact route.**
  - For a proposed tightening, the route lists exactly the agents whose notices for that tool would gain or change a narrowing, with their fields and dropped values.
  - A widening or a no-op lists none. An agent with the tool disabled, or a hidden field, is not listed.
  - The preview equals what a following PUT stores: same config, and the same notices on the next agent read.
  - An invalid body gets the PUT's 422 shape, and an unknown tool 404.
  - One rows list and one agents list read per request.
  - The PUT's own tests pass unchanged after the extraction.
- [ ] **AC6 — Settings warning.**
  - In Settings › Built-in tools, saving a tightening that narrows two agents opens the dialog naming both.
  - Cancel keeps the form dirty and stores nothing (read-back).
  - Save anyway stores it, and the affected agents then carry notices.
  - A save that narrows no agent saves with no dialog.
  - The tile toggle and the editor save both invalidate `agents`, asserted by an Agents-list or drawer change without a reload.
- [ ] **AC7 — docs.**
  - The DD14 targets describe the shipped behaviour: validation on save, clipping at build, notices, the union, `NO_HOSTS`, every redirect hop checked, the own/inherited tab, the cleanup, and the Shell/Python/downloads path note.
  - The agent-PUT watch-out in `CLAUDE.md` names the `tool_overrides` save validation.
  - The squawk 0223 rule in `agents.md` is updated to the own-only walk.
  - `docs/ui-control-inventory.md` covers AC1.
  - The flight's DD6 carries a header note for the path-form deviation.
  - The release-notes block is assembled in the flight log.
- [ ] **AC8 — no regressions.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` shows only the baseline failures.
  - These lanes show only baseline failures: `contracts-controls` and `contracts-overlay` (with `THE_ONE_REQUIRE_WEBKIT=1`), `agent-tabs`, `agents`, `settings-tools`, `chats`, `routing`.
  - The static and UI guards pass, and ruff is clean.

## Verification Steps
- AC1: `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_tabs_contract.py -x`.
- AC2, AC3: `agent-tabs` and `agents` lane tests. Check that a new file lands where intended with `--lane <lane> --list`.
- AC4: a `chats`-lane test, a `test_flow_chat_*` file.
- AC5: a unit test file for the impact route (credentialed client, template database).
- AC6: a `settings-tools`-lane test, a `test_flow_admin_tools_*` file.
- AC7: read-through; `grep -n` for each DD14 target. `tests/test_ui_control_inventory.py` covers the catalogue.
- AC8: as listed, one lane at a time or `--parallel 3`, never beside the unit tier.

## Implementation Guidance

1. **Library first.**
   - Add `indicator` and `setIndicator` to `ui/tabs.js`, with new owned classes (for example `ui-tab-indicator`, `ui-tab-indicator-dot`) defined in `components.css` with existing tokens.
   - Update the catalogue row.
   - Add contract tests: the name with and without the indicator, `setIndicator` changes, and focus and selection unchanged.
2. **The impact route.**
   - Extract the PUT's config computation into a helper returning the validated new config (or raising the same 422), use it in the PUT, and confirm the PUT tests are green before going on.
   - Then add the route, computing the before and after notices for that tool per agent.
3. **Settings:** the preview call and dialog in `tools-editor.js::save`, and the `agents` invalidation there and in `tools-page.js`'s toggle success path.
4. **Agent editor and Tools tab:** the indicator from `agent.notices` (updated wherever the editor applies a fresh agent, after save and on store refresh) and the per-tool chips in the disclosure headers.
5. **Agents list:** the badge, the suffix and the signature.
6. **Drawer:** the group in `renderContent`, re-rendered by the existing store subscription.
7. **Docs and release notes** last, once behaviour is final.

## Edge Cases
- **A notice on a tool whose disclosure was never opened** still flags its header: the flag is drawn from `agent.notices` at build, not from the loaded panel.
- **The agent editor open while Settings tightens a tool in another tab:** the studio `agents` subscription hook passes only `notices` to `setNotices`, so a dirty editor's values are never touched (AC2). Leg 4's per-field clipped lines inside an already-open panel update on the next panel render or mount, not live; that is acceptable.
- **Pluralisation:** "1 notice" / "2 notices"; "1 agent" / "2 agents".
- **The drawer for a chat with no agent** (`default`) has no notices group.
- **The impact route for a tool with an `_EmptyConfig`:** it always returns `{"agents": []}`.

## Files Affected
- `static/js/ui/tabs.js`, `static/css/components.css`, `docs/ui-control-inventory.md`, `tests/browser/test_ui_tabs_contract.py`
- `static/js/ui/tile.js` (`toolRow` flag), `tests/browser/test_ui_*` for toolRow
- `static/js/areas/studio/agent-editor.js`, `tools-tab.js`, `agents-list.js`, `studio.js` (the `agents` subscription hook)
- `static/js/areas/chat/agent-drawer.js`
- `static/js/areas/admin/tools-editor.js`, `tools-page.js`
- `the_one/interfaces/web/api.py`: the helper extraction and the impact route
- Tests: the new impact-route unit tests; new or updated browser tests in `agent-tabs`, `agents`, `chats` and `settings-tools`
- Docs: `the_one/agents.md`, `SECURITY-MODEL.md`, `CLAUDE.md`
- `sorties/07-agent-tool-overrides/flight.md` (the DD6 header note only) and `flight-log.md` (the release-notes block)

### Citation Audit
Checked by the Flight Director against the worktree (base `628a97dd` plus legs 1-3 uncommitted, leg 4 in progress), 2026-10-31: `ui/tabs.js:1-40`; `ui/list-pane.js:95-170`; `agents-list.js:89,162,184`; `agent-editor.js:47,298-299`; `tools-tab.js:122`; `agent-drawer.js:271,292,310,525-528,589`; `api.py:620,743-812`; `tools-editor.js:404-435`; `tools-page.js:313-345`; `ui/feedback.js` (`noteFlag` is note- or routine-only, so a chip is used for the tool flag). Leg 4 may move lines in `tools-tab.js` and `agent-form-data.js`: re-check them at the start of implementation.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
