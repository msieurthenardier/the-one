# Flight Log: Settings on the library

**Flight**: [Settings on the library](flight.md)

## Summary
Planned 2026-10-23 from `main` at `bfeb3f6`. Squawk 0248 merged as `8a52a39` (#304). The branch is `flight/04-settings-on-the-library`, cut from `main` at or after `8a52a39`.

---

## Planning Notes

- **Operator decisions, 2026-10-23:**
  - squawk 0248 (the denylist wipe) is hotfixed on `main` now, not folded into this flight;
  - the flight shape is the FD's call (no preference): one flight (DD1);
  - the theme picker takes the library radio card look (DD7);
  - the presentation-debt items are decided on the review page (DD7; the operator pastes the decisions);
  - nothing else is added to or removed from the scope.
- **Planning surveys at `bfeb3f6`** (four read-only crew; reports in the FD scratchpad):
  - **Built-in tools:** `f4-survey-tools.md`.
  - **The other Settings pages and `admin.css`:** `f4-survey-pages.md`.
  - **Presentation debt:** `f4-presentation-debt.md`, 153 screenshots, on a scratch instance at port 8492, stopped by its recorded PID.
  - **Reconnaissance** of the Flight 3 debrief items and squawks: `f4-recon.md` (the report below).
- **The presentation-debt survey found a security defect:** the tool editor stores `[]` over the default denylists. That became squawk 0248 (hotfix, outside this flight).
- **Flight Director calls, made out loud:**
  - one flight, legs split at planning (DD1);
  - the error-placement rule (DD3), from Flight 3 debrief recommendation 4;
  - Knowledge indexing becomes an editor with Cancel and Save in its header (DD6; from presentation item A19);
  - the banner's three Library consumers move in leg 04a, so no allowance row is added (DD4). *(Superseded at Architect cycle 2: they move in leg 04c, and ownership follows DD12's marker-class rule.)*
  - the read-only key-value rows on Knowledge indexing stay page CSS, not a control (DD6). *(Superseded at Architect cycle 1: `App.ui.facts`.)*

## Reconnaissance Report

Sources: the Flight 3 debrief (Technical, Documentation, Recommendations 2-5, Carried items) and the open squawks. Classified at `bfeb3f6`.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `knowledge-folders.js` over 800 lines; stale comments | confirmed-live | 897 lines; `:62` "never call each other" is contradicted by `:732`; `:783` is false; `studio.css:143` names `buildOtherItemsPanel` | Leg 02b |
| No 800-line guard | confirmed-live | only `tests/test_store_static.py:450` (`studio.js`); over 800: `chat.js` 2399, `mcp-server-editor.js` 2153, `provider-models.js` 1014, `knowledge-folders.js` 897, `provider-editor.js` 896 | Leg 01 (guard with a shrink-only allowance) |
| Error placement split; three error readers | confirmed-live (debrief counts drifted: 7 `fetchJson` / 17 raw `fetch` in knowledge and connector) | `_errorMessageFromResponse` at `knowledge-shared.js:26`, 4 callers; Settings adds `formatDetail`, `e.detail\|\|`, `'Fetch failed: '`, `renderTestError` | Leg 03a (DD3) |
| Five "latest request wins" copies | confirmed-live | no shared helper (`core.js:83` has only `mountSlot`); counters in connector, connector-glue, knowledge-search, provider-models, self-config, `admin.js:164` `editorGen`, `date-time-page.js:18` `GEN` | Leg 03a (`latest()`); the Library editors convert in Flights 5-6 |
| Section rhythm | confirmed-live | `editor.js:188` is a plain `div.editor-section`; `components.css:1496-1502` has no gap; area rules at `studio.css:774`, `:784`, `:846`, `:1017` | Leg 03b |
| Duplicated helpers | confirmed-live | `knowledge-search.js:66` `el`, `:75` `baseName`; `syncChildren` only in `knowledge-folders.js:101`; `provider-models.js:126` `placeNodes` re-inserts later rows | Leg 03b (`syncChildren`); leg 02b (`baseName`) |
| Stale docs (squawk 0246) | confirmed-live; list incomplete | `agents.md:2153`, `:2157`, `:2163`; inventory `:46`, `:98` (also self-configuration and agent-editor); duplicate `studio.css:799/:810` | Leg 01 (0246 extended) |
| Single-consumer options | confirmed-live | all still single-consumer; Settings candidates: `status.ledTestid` (Test result), `disclosure` (Test technical details) | Leg 11 recheck |
| 27 fixed `wait_for_timeout` in knowledge and connector tests | drifted (27, not 25) | knowledge inventory 20, connector 7 | Not this flight (DD10 rule for new tests only) |
| Orphan hold-out server invariants | partially-satisfied | cascade pinned at repository level (`test_db_repositories.py:755`); the composed `/status` rule is not pinned | Not this flight (a backend test, log as a squawk if wanted) |
| Squawk 0230 | confirmed-live | `test_flow_agents_scale.py:113` `assert m60 <= 3 * m10` at about 0.005 ms | Leg 01 |
| Alias shims | already-satisfied (counts as Flight 3 recorded) | `confirmDelete` 4 (Settings 1), `showFlash` 11 (Settings 3), `icon` 17 (Settings 8), `tabs` 2 (Settings 2), `consentLink` 7 (Settings 0) | Settings retires 1/3/6/2; the 2 `icon` calls in `tools-form-helpers.js`'s chip path wait for Flight 5 |
| 0237, 0238 | confirmed-live | `ui/confirm.js:154-159`; `ui/key-value-table.js:163`, `:260` | Leg 03b |
| 0239 | drifted | `knowledge-inspect.js:121`, `:150` | Stays open |
| 0240 | drifted | 9 sites (connector `:200`, `:417`, `:909`; library list `:576`, `:1395`, …) | Leg 01 |
| 0243, 0244 | confirmed-live | `api.py:2113-2122`; `api.py:2038-2040` | Stay open (backend, knowledge) |
| 0245 | confirmed-live | `connector-editor.js:457`; formatter `knowledge-shared.js:111` | Leg 02b |
| 0247 | confirmed-live | `run-tests.sh:66` `[knowledge]=300`; `CLAUDE.md:382` | Leg 01 |
| 0231 | confirmed-live | `filesystem.py:85-111` has no descriptions | Leg 05 |
| 0228, 0232, 0236 | confirmed-live | `agent-model-picker.js:118`; `agent-editor-controller.js:179`; `provider-editor.js:346-354` | Stay open (not Settings) |

Also found:
- **Flash timer races:** `system-page.js:236`/`:244` and `knowledge-settings-page.js:291` (DD8-10, -16).
- **Chip-cascade selectors:** `admin.css:386-431` has 10 `.chip-list-editor:not(.ui-chip-list)` selectors, half of them Flight 5's (DD1).

## Presentation-Debt Survey (summary)

The full report, with every screenshot path and `file:line`, is in the FD scratchpad (`f4-presentation-debt.md`). Review page: https://claude.ai/artifact/FxJaiyiM6byDP81iaeLsr7

- **A (obvious), 24 items:**
  - Prompts: A1-A3;
  - Encryption: A4-A5;
  - tools grid: A6;
  - tool editor: A7-A17;
  - Knowledge indexing: A18-A24.
- **B (taste), 15 items:** B1-B15.
- **Fine, no change:** the Settings nav; Appearance (layout and copy); the Date and time choices, search, empty text, mismatch hint and preview; the tab bar and grid layout; the Encryption arm/confirm flow; dark-mode colours generally; no horizontal overflow at 1024.

## Visible-Differences Ledger

| # | Leg | Surface | Change | Source |
|---|---|---|---|---|
| 1 | 08b | Prompts | Platform code blocks trimmed of leading and trailing blank lines (display only) | A1 |
| 2 | 08b | Prompts | Captions get space above them (about 12 px) | A2 |
| 3 | 08b | Prompts | The variant is a sub-heading under its layer, not a second eyebrow | A3 |
| 4 | 08b | Encryption | Sentence-case labels: "Rotate encryption key", armed "Rotate key?" | A4 |
| 5 | 08b | Encryption | The intro explains rotation; the banner states only the consequence | A5 |
| 6 | 06 | Tools grid | The category badge is removed from tiles | A6 |
| 7 | 05 | Tool editor, agent Tools tab | Written sentence-case field labels (backend `Field(title=)`; not model-facing) | A7 |
| 8 | 05 | Tool editor, agent Tools tab | Custom preset values humanised ("4MB (custom)", "45s (custom)") | A8 |
| 9 | 07a | Tool editor | "Enabled for all agents" on one line with the library switch | A9 |
| 10 | 05 | Tool editor, agent Tools tab | Every yes/no setting is the library checkbox with an inline label (on the agent tab the label was stacked above) | A10 |
| 11 | 03a | Every editor using `fieldErrors` | Validation messages humanised ("Must be 0 or more") | A11 |
| 12 | 07a | Tool editor | "No additional configuration." left-aligned, plain muted text | A12 |
| 13 | 07a | Tool editor | The category subtitle shows the category name ("Filesystem"), or is dropped | A13 |
| 14 | 07a | Tool editor | The tool prompt moves to its own section below the header (no reflow when dirty) | A14 |
| 15 | 07c | Tool editor | Test result: one status mark, a fixed headline per outcome, raw output under "Technical details", the head of the output | A15 |
| 16 | 07c | Tool editor | The Test input is a standard field, with the button on its line | A16 |
| 17 | 05 | web_search (model-facing) | The stale "F6 admin will surface the picker." sentence is removed, with an eval run against `m30-platform` | A17 |
| 18 | 10 | Knowledge indexing | One rule per section | A18 |
| 19 | 10 | Knowledge indexing | Cancel and Save top right with the unsaved caption (the `editorShell` page variant) | A19 |
| 20 | 10 | Knowledge indexing | The watch label on one line with the library switch | A20 |
| 21 | 10 | Knowledge indexing | The error replaces the hint; the overlap is checked against its own limit | A21 |
| 22 | 10 | Knowledge indexing | The interval hint is "10 seconds to 24 hours", and the value is echoed humanised | A22 |
| 23 | 10 | Knowledge indexing | Read-only values humanised ("Local (bundled)", "USearch", "16-bit float") | A23 |
| 24 | 10 | Knowledge indexing | Plain wording in the read-only notes | A24 |
| 25 | 05, 06 | Tools grid | Each tile shows a short human summary per tool, not the cut-off model prompt (a new backend `summary`, not model-facing) | B1 |
| 26 | 07a | Tool editor | The breadcrumb keeps "Built-in tools" as the link back to the list (operator); the tool title becomes the Library editors' title size | B2 |
| 27 | 04a, 07a, 10 | Settings editors | One field width for Settings, matching the Library editors (full column), with short number inputs (`textInput` width option) | B3 |
| 28 | 04b | Every library chip list | A long chip shows on one line with a middle ellipsis; the full value in its tooltip and accessible name (operator). The agent Tools tab gets it too | B4 |
| 29 | 05 | Tool editor, agent Tools tab | Plain preset labels ("1MB (default)"), not model jargon; `ui_choices` labels (not model-facing) | B5 |
| 30 | 05 | Tool editor, agent Tools tab | Settings that don't apply to a tool are hidden (for example the read size cap on `delete_file`); a backend per-tool field list | B6 |
| 31 | 05 | Tool editor, agent Tools tab | Filesystem fields get descriptions and info buttons (squawk 0231) | B7 |
| 32 | 04b, 09 | Date and time | The selected zone is centred in the list; zone ids and offsets in one font | B8 |
| 33 | 09 | Date and time | The mismatch hint leads with city names | B9 |
| 34 | 09 | Date and time | No reserved gap below the zone card when there is no status | B10 |
| 35 | 08b | Prompts | The layer titles are the stronger heading level | B11 |
| 36 | 08b | Encryption | Shows when the key was last rotated and how many stored credentials it covers (a new read-only API route) | B12 |
| 37 | 04a | Every editor | Disabled Save readable in dark (the button's disabled tokens) | B14 |
| 38 | 10 | Knowledge indexing | An intro line | B15 |
| 39 | 08a | Appearance | The theme picker takes the library radio card look (operator) | DD6 |
| 40 | 06, 07a, 10 | Settings | The library switch replaces the legacy iOS switch everywhere in Settings (operator, 2026-10-22) | DD7 |
| 41 | 07a | Tool editor | Field info buttons are press-to-open toggletips, not hover `title` tooltips | Library behaviour |

Operator decisions, 2026-10-23: all of A1-A24 approved; B1-B3, B5-B12, B14 and B15 approved; B4 changed (one line with a middle ellipsis); **B13 skipped** (disabled tool tiles stay as they are). Each leg appends its own rows below these, including the ledger rows DD3, DD13 and squawk 0245 call for.

---

## Leg Progress

*(none yet)*

---

## Decisions

*(runtime decisions, recorded during execution)*

---

## Flight Director Notes

- 2026-10-23: **Flight start.** The operator approved the plan and ran `/mission-control:agentic-workflow flight 04 mission 31`. Phase file `.flightops/agent-crews/leg-execution.md` loaded (Crew, Interaction Protocol and Prompts present). Flight status planning → in-flight. Branch `flight/04-settings-on-the-library` created from `main` at `8a52a39` (squawk 0248 included). 19 legs (18 autonomous, plus the HAT).
- 2026-10-23: **Architect cycle 1: approve with changes** (2 high, 9 medium, 9 low, 4 environment; 13/13 citation spot-checks verified). All applied:
  - H1 → DD12 (a control owns its classes in the leg that migrates its last outside user; no leg raises the allowance);
  - H2 → DD3 (the section stack is opt-in, with child margins neutralised, the retire list corrected, and connector/kb captures);
  - M1 (`setBusy` does not cover fields) → DD5;
  - M2 (`syncChildren` `after` anchor and the blur test) → DD3;
  - M3 (404 tolerance and fallback texts as ledger rows) → DD3;
  - M4 (the `loc` rule, one humaniser, model-level errors to editor level) → DD3;
  - M5, M6: legs 03 and 07 split now (03a/03b, 07a/07b), plus 08 (08a Appearance, 08b Prompts and Encryption);
  - M7: the `editorShell` page variant for Knowledge indexing → DD4 and DD6;
  - M8: Agents and Library surfaces in the capture set, ledger and HAT → DD2;
  - M9 → DD13 (the field module's DOM and data contract; `parseInt` replaced; the dead `mcp_overrides` walk deleted);
  - the lows (pins mapped to legs, `.area-admin .field-error` moved to leg 10, all 8 `App.icon` calls go, `windows-native-frame-splash.md`, fixed Test headlines);
  - E1-E4 (pinned `TZ`, the stubbed ok Test result, the eval re-verify, the before set after 0248);
  - the missing controls: `App.ui.codeBlock` and `App.ui.facts` added (leg 04a), the rest declared not controls;
  - suggestions taken: squawk 0236 in 04a, the label-literal pin extended, the shell-before cache rule, re-mask only if unchanged, captures at 1024.
- 2026-10-23: **Architect cycle 2 (the last allowed): approve with changes.** Applied:
  - H1 → DD12 rewritten: each new control owns a marker class from its build leg, and the legacy names join the owned list at the handover leg, with a DD11 exception for area CSS in between. Also an emitted-class guard (04a), `admin.css:49` → 08b, the tools header → 06, `renderPage` delegating from 08a, and the Knowledge indexing header through the `editorShell` page variant composing `pageHeader`.
  - H2 → DD13: agent-mode numbers get a client-side field error. The agent PUT stores `tool_overrides` unvalidated, so a server error would surface only at the next chat. Blank is skipped; admin mode sends the raw value and gets the 422.
  - M1: 04a split into 04a (`page-controls`, library only), 04b (`list-controls`) and 04c (`library-consumers`: banner and codeBlock consumers, `dangerZone` notice, 0236). The banner gains a persistent live mode.
  - M2: the layout options planned in DD4 (`inset`, `panelPadding`, the slot option, `maxHeight`, `toolTile.grid()`, badge kinds).
  - M3: agent-mode booleans inline is a visible change → ledger row (DD6, DD13).
  - M4: the `loc` example corrected (Knowledge `["size_chars"]`; the overlap check is `[]`); a string `detail` is unmatched; "Value error, " is stripped.
  - M5: 07 split into 07a (frame, fields, errors), 07b (Save/Cancel value model) and 07c (Test).
  - Lows: the stale 0236, "Flights 5 and 6" and the Contributing text; the tool editor has no banner; the duplicate inline CSS recorded; `mcpOverrides` kept; `components.css:1245` deleted in 11; leg 01 ordered (dead CSS last, then a compare); the `test_deep_violet_computed_styles.py` fixture → 10; the Verification owned-list check.

  No issue left open. The design is approved on the two-cycle limit, so no third review and no escalation are needed.
- 2026-10-23: **Squawk 0248, item 3.** The Developer found that `resolver.py:249` reads the operator baseline with `field_info.default`, which is `PydanticUndefined` for a `default_factory` field. A NarrowSuperset override on a never-saved tool therefore raises, and the agent cannot be built. The 0248 schema fix makes this easier to hit, because the Overrides panel now seeds the defaults. FD call: fold the one-line resolver fix into 0248 (same root cause), with tests proving the agent still cannot drop a default entry.
- 2026-10-23: Planning. Four surveys at `bfeb3f6`. Squawk 0248 logged and hotfixed separately at the operator's request (a security surface, so it fails the squawk path's "bounded blast radius" criterion; run as a hotfix by operator instruction, with a security-briefed Reviewer).
