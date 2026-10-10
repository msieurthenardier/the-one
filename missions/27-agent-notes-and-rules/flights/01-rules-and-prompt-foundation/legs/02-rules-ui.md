# Leg: rules-ui

**Status**: completed
**Flight**: [Rules and the Prompt Foundation](../flight.md)

## Objective

Let the operator manage an agent's rules from a new **Rules and notes** tab in
the agent editor. Show the rules read-only in the open conversation's agent
panel, with a link to edit them.

## Context

- Flight design decisions **DD6** (the tab), **DD7** (the drawer group) and
  **DD10** (test placement) govern this leg. Read them in
  [flight.md](../flight.md) first.
- Leg 1 (`rules-backend`) provides the REST routes and shapes in DD8:
  - `GET /api/agents/{name}/rules` returns `{rules: [{id, text, enabled,
    position, created_at, updated_at}], limits: {rule_chars, total_chars}}`;
  - `POST` takes `{text, enabled?}` and returns 201;
  - `PUT /rules/{id}` takes `{text?, enabled?}`;
  - `DELETE /rules/{id}`;
  - `PUT /rules/order` takes `{ids}`.

  Each 422 carries a plain `detail`. Read the flight log's leg 1 entry for
  anything that landed differently.
- Flight 2 adds a Notes section to the same tab. Build the tab so a second
  section can be appended below Rules without restructuring: one module, with a
  `section` helper or equivalent.
- The new code is **DOM-built**: no HTML-string sinks (`tests/test_ui_guards.py`
  baselines). It uses `App.ui` controls (`App.ui.button`, `App.ui.textarea`,
  `App.ui.toggle`, `App.ui.emptyState` or the feedback helpers) and
  `App.confirmDelete` for delete. Calls go through `App.api.fetchJson`, so a
  422's `detail` reaches the UI.
- No new `App.ui` factory is planned. If one becomes necessary, the CLAUDE.md
  control-library rules apply: a Design language demo, an inventory row, and
  contract tests in both engines.

## Inputs

- Leg 1 landed (uncommitted) on `flight/01-rules-and-prompt-foundation`.
- `areas/studio/agent-editor.js` (five tabs today), `areas/studio.js`
  (callbacks, tab whitelist at `:248`), `areas/chat/agent-drawer.js`
  (`group()` at `:274-300`, per-open fetches in `ensureFetches`).

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/rules-notes-tab.js` (new),
  exposing `App.studio.renderRulesNotesTab(panel, agent, callbacks)`.
- The editor scaffold gains the tab and panel.
- `studio.js` gains the callbacks and the whitelist entry.
- `index.html` gains the script tag.
- The drawer gains a Rules group.
- CSS for both, in the existing studio and chat stylesheets, using only defined
  tokens.
- Testids registered.
- Browser tests.
- Docs: `the_one/agents.md` and CLAUDE.md.

## Acceptance Criteria

**The tab (DD6)**
- [ ] AC1. The agent editor shows a sixth tab with these properties:
      - label "Rules and notes" (or the width fallback below);
      - `data-tab-id="rules-and-notes"`, testid `tab-rules-and-notes`, panel
        id `agent-tab-panel-rules-and-notes`;
      - placed second, after General.
- [ ] AC2. The tab is reachable by click, by arrow keys in the tablist, and by
      `#agents/{name}/rules-and-notes` (studio's tab whitelist accepts it).
- [ ] AC3. **Width at the supported minimum:** at 1024×768, in Chromium and
      WebKit, the tab strip fits on one row with no overflow.
      `tests/browser/test_flow_agents_scale.py:260-263` stays unrelaxed and is
      updated to 6 tabs.
      - If "Rules and notes" cannot fit, the label is **"Rules"** (id
        unchanged).
      - Record the measured strip width and the label chosen in the flight log.
- [ ] AC4. The Rules section shows:
      - an `h2`/`h3` "Rules" heading in the project's section-title style
        (DD13 eyebrow);
      - the line "Changes apply to new and reopened chats, and to the next
        message in connector channels.";
      - the rule list in `position` order, or an empty state ("No rules yet.")
        when there are none;
      - an Add rule control: a textarea with a visible label and a live
        "{n} / 500" count, and an Add button that is disabled while the text
        is empty after trimming.
- [ ] AC5. Each rule row has:
      - its number and text;
      - an on/off `App.ui.toggle` (`aria-label` naming the rule's number);
      - Edit, which switches to an inline textarea with Save and Cancel; Cancel
        restores the text;
      - Move up and Move down, disabled at the ends;
      - Delete through `App.confirmDelete`.
- [ ] AC6. Every action saves immediately through the REST API, then re-reads
      the list and re-renders. A failure (a 422 or a network error) shows its
      `detail` inline in the section's error area, and the list stays as the
      server has it. None of these controls marks the General form dirty or
      triggers the leave guard.
- [ ] AC7. Disabled rules render visibly muted, with the toggle off, and stay in
      their place in the order.
- [ ] AC8. **Create mode** (no saved agent) shows "Save the agent first to add
      rules." and no controls.
- [ ] AC9. Focus is kept sensible:
      - after Add, focus returns to the Add textarea (cleared);
      - after a Move, focus stays on the moved row's same Move button, or the
        other one when it is now at an end;
      - after Delete, focus goes to the neighbouring row's Edit button, or to
        the Add textarea when the list is empty;
      - after an inline Save or Cancel, focus goes to that row's Edit button.

**The drawer (DD7)**
- [ ] AC10. With a chat open, the agent panel's "What it can use" has a
      `.chat-drawer-group[data-group=rules]` group, labelled "Rules", placed
      first, before Knowledge bases, containing:
      - the enabled rules in order, each text clamped to two lines, with the
        full text in `title`;
      - "{n} off" when any rules are disabled;
      - an "Edit rules" link to `#agents/{name}/rules-and-notes`.
- [ ] AC11. The group shows:
      - "No rules" when the agent has none, or none enabled (with "{n} off"
        still shown);
      - "No rules" on a 404, not "Couldn't load";
      - "Loading…" or "Couldn't load" for the other states, as the existing
        groups do.

      The rules are fetched once per open, beside the self-configuration fetch,
      with the same generation guards.
- [ ] AC12. The default-agent and deleted-agent views are unchanged; they show
      no Rules group.

**Registry, tests, docs**
- [ ] AC13. Every new testid is registered in `docs/ui-testid-registry.md`
      (literals or a parametric family). `tab-self-configuration`'s "fifth" is
      corrected. `tests/test_ui_guards.py` passes both ways.
- [ ] AC14. Existing tests updated for six tabs and the new position:
      - `tests/browser/test_flow_agent_tabs.py:85` (count);
      - `:124` and `:147` (ArrowRight from General now reaches Rules and notes;
        keep the tests' intent of proving arrow navigation);
      - `tests/browser/test_flow_agents_scale.py:260` (count).
- [ ] AC15. A new `tests/browser/test_flow_agent_rules.py` (in the `agents`
      lane via its glob; confirm with
      `bash scripts/run-tests.sh --lane agents --list`) covers:
      - add, edit and cancel;
      - toggle;
      - move up and down;
      - armed delete;
      - the empty state;
      - create mode;
      - a 422 shown inline (a 501-character rule);
      - that persistence survives a reload;
      - the deep link.
- [ ] AC16. `tests/browser/test_flow_chat_drawer.py` gains tests for the Rules
      group:
      - enabled rules listed in order;
      - "{n} off";
      - "No rules";
      - the Edit rules link navigating to the tab.
- [ ] AC17. Static guards pass: `tests/test_ui_guards.py`,
      `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`.
      `make test-unit` passes.
- [ ] AC18. The `agents`, `chats` and `contracts` browser lanes pass. Use
      `THE_ONE_REQUIRE_WEBKIT=1` for any lane holding an engine-parametrized
      test touched here.
- [ ] AC19. Docs updated:
      - `the_one/agents.md` gains the tab and drawer contract under the
        section leg 1 created, or a sibling "Rules and notes tab (M27 F1)";
      - CLAUDE.md gains one short paragraph in Conventions naming the tab, its
        route, the immediate-save model, the drawer group and the REST routes;
      - the paragraph is brief, in the style of its neighbours.

## Verification Steps

- AC1-AC9, AC15:
  `TEST_TIMEOUT=1500 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents -x`
  (or the new file alone while iterating:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_agent_rules.py -x --timeout 60`).
- AC3: `test_flow_agents_scale.py` in both engines
  (`THE_ONE_REQUIRE_WEBKIT=1`).
- AC10-AC12, AC16: the `chats` lane.
- AC13, AC17: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x`,
  then `make test-unit`.
- AC18: each named lane. The flight-end gate (`make gate`) runs all of them
  once more after review.

## Implementation Guidance

1. **Scaffold.** In `agent-editor.js`:
   - add `'rules-and-notes': 'agent-tab-panel-rules-and-notes'` to
     `PANEL_IDS`;
   - insert the tab button after General and the panel after General's panel;
   - call
     `window.App.studio.renderRulesNotesTab(panel, agent, {fetchRules, createRule, updateRule, deleteRule, reorderRules})`.

   In `studio.js`:
   - define those callbacks beside `fetchSelfConfigurationStatus` (`:1911`),
     using `App.api.fetchJson` with `encodeURIComponent(name)`;
   - pass them in the callbacks object near `:2815`;
   - add `'rules-and-notes'` to the whitelist at `:248`.

   Add the `<script>` tag in `index.html` beside `self-configuration-tab.js`
   (`:78`). If a test pins the script count (`tests/test_ui_guards.py` or a
   sibling), raise it deliberately.
2. **Tab module.** `rules-notes-tab.js`, ES5 IIFE, DOM APIs only.
   - Render the section from a `fetchRules` result.
   - Keep a module-local generation counter so a stale fetch never overwrites
     a newer render.
   - Re-render the list only (not the whole panel) after each action, so the
     Add textarea keeps its focus.
   - Testids follow `rules-*`: `rules-section`, `rules-list`,
     `rules-row` (with `data-id`), `rules-row-toggle`, `rules-row-edit`,
     `rules-row-up`, `rules-row-down`, `rules-row-delete`,
     `rules-row-edit-input`, `rules-row-save`, `rules-row-cancel`,
     `rules-add-input`, `rules-add-btn`, `rules-add-count`, `rules-empty`,
     `rules-error`, `rules-applies-note`, `rules-create-mode`.
   - Adjust names to the registry's `{area}-{element}` convention if a
     neighbour suggests otherwise, and register them.
3. **Width.**
   - Before styling further, run `test_flow_agents_scale.py`'s strip
     measurement with the new tab.
   - If it overflows at 1024 in either engine, take the "Rules" label fallback
     (AC3). Do not shrink other tabs' labels or the tab padding: that changes
     surfaces outside this leg.
4. **Drawer.**
   - Add a `rules` fetch state beside `selfConf` in `ensureFetches`, keyed on
     generation and agent: a 404 means an empty list, other errors mean the
     error state.
   - Build the group with a sibling builder (`rulesGroup(...)`) rather than
     overloading `group()`.
   - Insert it first in `uses()`.
   - The link is a plain `<a href>` built from `App.router.href` (or the
     existing link pattern used by `chat-drawer-settings-link`'s `go`); the
     global link interceptor runs the leave guard.
   - New testids: `chat-drawer-rules-edit-link`, plus
     `chat-drawer-rules-off` if useful.
5. **CSS.** Add the styles to the studio and chat stylesheets that already hold
   the tab and drawer styles. Use tokens only, and add no new tokens unless
   necessary (if you do, define them in `tokens.css` and pass the a11y
   contrast test). The two-line clamp uses `-webkit-line-clamp` with
   `display: -webkit-box`, which works in both engines.
6. **Tests.** Use `tests/browser/_nav.py` for routes and `_lists.py` helpers
   to open an agent. Seed the rules through the REST API with the credential
   helpers (`tests/browser/_credential_registry.py::auth_headers_for`), never
   through raw route hashes or retired selectors.
7. **Docs** per AC19.

## Edge Cases

- **A very long rule (500 characters):** the row wraps and the drawer clamps
  it.
- **Rapid double-click on Add:** disable the button while a request is in
  flight.
- **Moving a rule while another request is in flight:** disable the row's
  controls during the request. The server's order wins on re-read.
- **Agent renamed while the tab is open:** the editor re-renders on rename
  (existing flow), so the callbacks use the current name.
- **Drawer open while rules change in Studio:** the drawer shows a fresh list
  on its next open. No cross-area push is required, but stated: the panel
  reflects saved rules as of when it was opened.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/rules-notes-tab.js` (new).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`.
- `the_one/interfaces/web/static/js/areas/studio.js`.
- `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js`.
- `the_one/interfaces/web/static/index.html`.
- The studio and chat CSS under `the_one/interfaces/web/static/css/`.
- `docs/ui-testid-registry.md`.
- `tests/browser/test_flow_agent_rules.py` (new),
  `tests/browser/test_flow_chat_drawer.py`,
  `tests/browser/test_flow_agent_tabs.py`,
  `tests/browser/test_flow_agents_scale.py`.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit

Checked against the working tree at `08db2cb`:
- `PANEL_IDS` is at `agent-editor.js:56-62`.
- The `renderSelfConfigurationTab` call is at `agent-editor.js:230-250`.
- The tab whitelist is at `studio.js:248`.
- `fetchSelfConfigurationStatus` is at `studio.js:1911`, passed at `:2815`.
- The drawer's `group()` is at `agent-drawer.js:274-300`, the self-config fetch
  in `ensureFetches` at `:425-440`, and `renderContent` at `:367-399`.
- The script tags are at `index.html:70` and `:78`.
- The registry rows are at `ui-testid-registry.md:75-80` (chat-drawer) and
  `:293` (tab-self-configuration).

All were verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
