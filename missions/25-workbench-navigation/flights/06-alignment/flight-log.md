# Flight Log: Alignment

**Flight**: [Alignment](flight.md)

## Summary

**Status**: in-flight (2026-10-06).

---

## Reconnaissance Report

**Sources:**
- the open squawks (0112–0116, 0119–0125);
- the Flight 3, 4 and 5 debriefs' carried items;
- the reference spec §13 and §15;
- the mission's SC1–SC10.

This is a read-only sweep of `main` at `aaee705` (v0.10.0) by a Sonnet agent, on 2026-10-06.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| 0112: creating a provider without `base_url` returns 500 | confirmed-live | `api.py` `create_provider`: `model_validate` with no `ValidationError` catch | A small fix (422) |
| 0113: the Tools tab category master toggle has no name | confirmed-live | `areas/studio/tools-tab.js:125-137` | A small fix (`aria-label`) |
| 0114: info-icon buttons are named only by `title` | confirmed-live | `provider-editor.js:227,262,285`, `tools-editor.js:174`, `tools-form-helpers.js:120`, `mcp-server-editor.js:901` | A small fix |
| 0115: the KB re-index-all test searches mid-reindex | confirmed-live | `test_flow_studio_knowledge_inventory.py:599-613` | A test-only fix |
| 0116: Settings tile title row and badge overlap | confirmed-live | `admin.css:142,155,156` | A mechanical fix (a flex title row), or an `App.ui` tile factory (scope decision) |
| 0119: a degraded join of the same id stays subscribed | confirmed-live | `app.py:2783`, `:2798-2802` | A small backend fix |
| 0120: a cancel before the turn starts sends no `cancelled` | confirmed-live | `app.py:3037-3041` | A small backend fix, or leave (a human click cannot hit the window) |
| 0121: the behavior crew file lacks the CDP recipe | confirmed-live | `.flightops/agent-crews/behavior-tests-execution.md` is unchanged since Flight 4 | A docs fix |
| 0122: the Flight 4 spec wording | confirmed-live | `jump-to-palette.md:92,94` still name `studio-description` as a testid | A docs fix |
| 0123: the `windows-window-chrome` wording | confirmed-live | only the leg 4 Revised line | A docs fix |
| 0124: the helper closure pin | confirmed-live | `windows_test_copy.py:2237`; no pin test | A small test, or leave |
| 0125: the pywebview 6.x blocker note | confirmed-live | no mention in `agents.md` or `pyproject.toml` | A docs fix |
| F4 B1: the faint Dark pending-row wash | needs-human-recheck | `components.css:683` | Operator decision |
| F4 B2: no focus ring on `rail-jump-to` after a pointer close | needs-human-recheck | `components.css:511`; the browser's `:focus-visible` heuristic | Operator decision, or retire |
| F4 B3: focus on `<main>` after Continue into a pending chat | confirmed-live (by design) | `nav.js:56-59,96` | Operator decision |
| F4 B4: message timestamps 1–4s off after a reload | needs-human-recheck | `message-bubble.js:106-120` | Investigate, or a squawk |
| F4 B5: UTC bubble times against local list times | confirmed-live | `message-bubble.js:106-114` against `chats-list.js:10-19` | Operator decision |
| F4 A4: the 1024 drawer overlay covers Send | already-satisfied (operator-accepted) | the Flight 4 debrief addendum | Retire |
| F4 A5: the unlabelled `#app-sidebar` | partially-satisfied | `router.js:573` labels it per destination; `index.html:27` is bare until the router runs | Wording only; fix or retire |
| F4: the deleted-agent heal for a restored `#chats/~new/{agent}` | partially-satisfied | `test_flow_chat_start_flow.py:417-444` covers an unknown agent, not a deleted one | Add one browser test |
| F3 Q7: focus drops to BODY after Create, Save and Test | confirmed-live | no post-save focus in `areas/studio/*` or `provider-editor.js` | Fix (a shared helper), or operator decision |
| F3: an `h1` at the Agents and Library roots | needs-human-recheck | not seen in the empty states | Check, then fix if missing |
| F5 D: window widths 640–1023 | confirmed-live (gap) | `base.css:56-58` "Below 1024px is unsupported"; no layout media queries; at 640 the main pane is 268px | Operator decision (enforce 1024, add a narrow layout, or accept), then a geometry test |
| F5 DD12: the five preview questions | needs-human-recheck | the preview artifact | Operator decision |
| SC9: the operator's packaged-build walk | needs-human-recheck | `windows-native-frame-splash` steps 11–19 | The operator walk |
| SC5 and SC9: Ctrl K in the installed WebView2 | needs-human-recheck | crew-verified at the Flight 5 close gate | The operator's confirmation |
| Reference spec §13 (D1–D5) | already-satisfied | pre-accepted; D5 decided at the Flight 3 checkpoint | Carry as accepted |
| Reference spec §15 (A1–A32) | partially-satisfied | owner flights 1–4; the statuses are recorded only in flight logs, not in the spec | Sweep the statuses into the spec at mission close |

**Mission criteria.**
- **SC1–SC7 and SC10** were delivered by Flights 1–5, with SC10's remaining items listed
  above (0113, 0114, F3 Q7, the root `h1`).
- **SC8** closes here: the operator's sample walk and the decision-sheet items.
- **SC9** closes here: the operator's packaged-build walk.

---

## Leg Progress

### Leg 6: mission-close (documents)

- **Reference spec §15:** all 32 rows gained a Resolution column, each citing the flight spec
  or log that settled it. 29 resolved, 2 accepted as is (A4, A6), 1 informational (A22),
  none carried. Source flights: F1 (A1, A4-A11, A30, A31), F2 (A12 rail), F3 (A2, A3, A8,
  A12, A14-A16, A18, A19, A23, A24, A26, A27), F4 (A10, A11, A13, A16, A17, A20, A21, A25,
  A28, A29, A32).
- **Reference spec §13:** added "Operator-accepted deviations (Flight 6)", D6 (DD13 section
  labels), D7 (DD14 12-hour times), D8 (DD15 start pages), D9 (DD16 composer width), with the
  operator's words. D1-D5 unchanged. DD10's label noted as additive.
- **mission.md:** Ctrl K in WebView2 closed with the SC9 answer and the Flight 5 premise 9
  finding. The four unchecked open questions are ticked with pointers (F1 DD1, F1 DD8,
  F2 DD1, F3 DD7). No SC box or Flight 6 line ticked.
- **Docs read-through:** `the_one/agents.md` already described DD2, DD4, DD5, DD10, DD13-DD17
  and DD19; no edit. `CLAUDE.md` already covered DD2, DD4, DD10, DD14-DD16; added one brief
  paragraph for DD5, DD13, DD17 and DD19.
- Gates and the Flight Director's parts remain; the leg stays in-flight.

### Leg 4c: root-pages

**Landed** (uncommitted).
- **DD15.** `studio.js`: `buildRootHeading` now builds a visible `h1.start-page-title` (still the sibling node, so the Agents heading survives a `loadAll` failure). `renderAgentsEmpty` builds `div.start-page` (`agent-select-empty` / `agent-empty`): description, variant line ("Pick an agent from the list to edit it." / "No agents yet."), primary New agent; inserted after the heading. `renderLibraryEmpty` builds `div.start-page` (`library-empty-{route section}`): intro, then a `.start-page-card` per type (icon, `h2.start-page-card-title`, description, its Add button `library-empty-{id}-add`). All DOM APIs; `studio.css` adds the left-aligned 720px column, cards on the Settings tile recipe, wrap under 560px. Copy verbatim from the leg.
- **Testid guard.** The start-page nodes set their `data-testid` through `setAttribute('data-testid', ...)` literals, because the registry guard's extractor does not see a `'data-testid':` attrs key.
- **Squawk 0126** fixed and completed. `connector-editor.js` sets the title from `updated.name`. Checked the others: agent editor and knowledge-base detail re-mount on save (no gap); the MCP server editor had the same gap, fixed with the same one-line change in `mcp-server-editor.js`.
- **Tests.** New (in `test_flow_agents_root_heading.py`, agents lane): both Agents variants, the Library page at each root (h1, three h2s in order, three Adds, a cross-type Add), no overflow at 1024, the Library page with the three collection GETs at 500. New in `test_studio_connector_editor.py` (library lane): rename updates the title. Pins updated in place: root-heading visible (was hidden, width <= 1), the h2 count (3), `test_flow_studio_library_list` copy and h2 pins (the zero-`.page-header` assertion kept), `test_flow_agents_list` copy, `test_studio_connector_editor`, `test_flow_studio_knowledge_inventory`, `_lists.py` docstrings. `test_flow_agent_crud` "No agents yet" pins pass unchanged.
- **Specs.** `list-and-detail` steps 2, 8, 10, 15, 17; `workbench-navigation` steps 3, 4, 8; `shell-navigation-smoke` steps 4, 5; `studio-agent-crud` step 2. Each has an Updated line.
- **Docs.** CLAUDE.md (leg 1a sentence, Agents and Library paragraphs), agents.md (both detail-pane bullets, DD11 note), registry rows.
- **Gates.** Static guards, ruff, format clean. `make test-unit` 5439 passed, 12 skipped (11m16s; a first run failed `test_registered_testids_exist_in_source`, fixed, whole suite re-run). Lanes: agents 151 passed, 2 skipped (6m02s); library 152 passed, 1 skipped (8m23s); shared 465 passed (11m52s).
- **Not done.** The screenshot evidence (both pages, 1024 and 1440, both themes) was not captured; for the walk. The pixel baseline for `agent-empty` needs a local regenerate.

### Leg 4b: chat-polish

**Landed** (uncommitted).
- **DD14.** `App.time.formatClock(d)` in `static/js/app.js` (hand-formatted local `h:mm AM/PM`; no new script, so the index.html script-count pin stays at 83). The Chats list's Today rows and `fmtTs` (message attributions, now local, no seconds, no "UTC") both use it. Comments updated (issue #223 for a time tool and time-zone setting).
- **DD16.** `.composer-box`, `.chat-attachments` and `.pending-queued-region` lose the 760px cap and centring in `chat.css`; the readout's right edge now meets the box's.
- **DD17.** `shell.py` `_create_kwargs` gains `"text_select": True` (main window only; splash keeps the default). `agents.md` Desktop launcher note added.
- **Tests.** New: `test_clock_formatter_edges` (chat list), `test_the_box_fills_the_pane_and_meets_the_readout` (1024 / 1280 open / 1920 closed). Pins updated in place: composer width pin plus docstring, telemetry edge check, chat list `_hhmm` (12-hour), peer attribution's three regexes (`\d{1,2}:\d{2} [AP]M`), `test_desktop_shell.py` (`text_select` True on the main call at both asserted paths, splash not True).
- **Docs.** CLAUDE.md (Chats list, composer), agents.md (Message.created_at note, Times bullet, composer Layout), `start-a-chat.md` step 2 and Updated line.
- **Walk item (leg 5, Flight Director):** on a Windows test copy, `getComputedStyle(document.body).userSelect` is not `none` and a drag over a reply selects it. Not run here.
- **Deviation:** the queued region and chicklet row are hidden in the width test, so their left edge is pinned through computed margin 0 and max-width none rather than a rect.

### Leg 4: section-labels

**Status**: landed (2026-10-06). DD13, operator option D, "eyebrow with a rule". Not committed.

- **CSS.** `components.css`: the list-pane and nav-groups captions and `.section-title` are 10px semibold, `letter-spacing: 0.08em`, uppercase, `--fg-tertiary`, with a 1px `--border` `::after` rule. Captions: `nowrap`, rule `min-width: 0`, padding `10px 10px 6px`, a sibling rule gives every later visible group 16px (a hidden first group does not count). `.section-title`: `gap: 10px; margin: 22px 0 10px`, `:first-child` 0. `h2.section-title` bump deleted (D6). `.danger-zone-title` rule in `--status-danger` (D3). `.section-title-row` (admin.css): rule on the row's `::after` after the icon, the span's own rule suppressed (D1). D2: `.editor-section + .editor-section:has(> .section-title:first-child | > .section-title-row:first-child)` loses its `border-top`. D4: `.admin-pf-*` sub-labels untouched (comment reworded). `.section-description` unchanged: `-4px` under the 10px title margin leaves a 6px gap.
- **`.section-title` inventory** (every JS site; all are section headers unless noted): provider-editor (Connection, Available models, Danger Zone, Anthropic Account); tools-editor (Prompt, Configuration, Test connection row); general-tab (Identity, LLM Configuration, System Prompt, Behavior, Danger Zone); self-configuration-tab (5); mcp-server-editor (Server, Connection, Sandbox, Tools, Env/Headers `kv-section-title`, Danger Zone); knowledge-section (`_section` titles, Danger Zone); connector-editor (`_section` titles, Danger Zone); knowledge-settings-page (Chunking, Monitoring, Embedding, Vector Store); design-language-page (one per gallery section). **Not headers:** `kb-panel-title` (a file path) and the three telemetry-strip gallery samples (System, Agents, MCP).
- **Opt-outs (`.section-title--plain`, D5):** `kb-panel-title` (a path in capitals is unreadable), and the three telemetry-strip titles in `status-section.js` (one-word labels beside a value, not section headers). No others needed.
- **Design language.** `typography-section.js` demo rewritten: h2 and div headers in the new recipe plus the `--plain` opt-out, copy updated. The listPane and navGroups demos pick up the captions automatically.
- **Docs.** `the_one/agents.md` "Section titles" rewritten (eyebrow back, with a rule, by operator decision; `--plain`; D1-D3); `docs/ui-control-inventory.md` listPane and navGroups rows note the caption style; comments in `components.css` and `admin.css`. **SC8:** the reference spec section 3 group label (11px medium `--fg-muted`) is an operator-accepted deviation; leg 6's section 15 and 13 sweep must record it. The published design system is updated at mission close.
- **Tests.** Updated in place: `test_ui_nav_groups_contract.py` (captions: 10px/600/`--fg-tertiary`, padding 10px then 16px, uppercase, 0.8px, rule 1px `--border`; the pitch assertion still holds); `test_design_tokens_a11y.py` (the navGroups caption pair and rule pin now `--fg-tertiary`). New: `test_list_pane_caption_is_an_eyebrow_with_a_rule` (both engines; first group hidden, 180px column, long label stays one line, rule at 0), `tests/browser/test_flow_settings_section_labels.py` (3: provider editor in both themes incl. danger zone and no divider; Built-in tools Test connection rule right of the icon), `test_section_label_eyebrow_pairs_pass_body_aa` (x2 themes) and `test_section_label_rules_consume_the_gated_pair`. No other test pinned the old caption or title style.
- **Gates.** Static guards 261 passed; `make test-unit` 5441 passed, 10 skipped (11:23); lanes (all `THE_ONE_TEST_NETNS=1`): contracts (WebKit required) 672 passed, 3 skipped (2:52); settings 201 passed (6:23); agents 144 passed, 2 skipped (5:49); library 151 passed, 1 skipped (8:19); chats 164 passed (4:12); shared 465 passed (11:44). `ruff check` and `ruff format --check` clean.
- **Not done:** the two-theme screenshot pass (flight-log evidence only) was not taken; the computed-style probes stand in. The leg 5 walk will show it.

### Leg 4d: mcp-error-message

**Status**: landed (2026-10-06). DD19, a fix (presentation only). Not committed. No backend change (#226 owns the masked cause).

- **Helper.** `App.mcpErrorMessage(raw) -> {headline, detail}` and `App.buildMcpError(raw)` live in `areas/studio/mcps-tab.js` (loaded before `mcp-server-editor.js`, so no new script and no change to the 83-script pin). Headline by leading class, then phrase ("did not respond within"), then the non-OK shapes (`fetchMcpSourceTools: HTTP`, `Server error`); the detail is the raw text, unchanged. An empty error gets the fallback headline and no details block.
- **Both surfaces** build the same DOM block: headline in the error colour, then a collapsed `<details>` "Technical details" holding the raw text in a `pre.mcp-error-raw` (`mcp-error-raw`; wraps with `overflow-wrap: anywhere`, selectable). The MCPs tab's two copies share the builder and keep `mcp-tools-error-{id}`; the Library editor's result is DOM-built (`mcp-connection-error`), the "Network error" catch included. "Error loading tools:" and "✗ Error:" are gone. CSS in `studio.css`.
- **Pins.** `test_ui_guards.py`: two `innerHTML` baseline entries for `mcp-server-editor.js` removed (the baseline only went down). `docs/ui-testid-registry.md`: `mcp-connection-error`, `mcp-error-raw` added. The old 500-body test's comment updated in place (its assertions still hold, the raw text is in the details). No other test pinned the old text.
- **Docs.** `the_one/agents.md` "MCP error translation" gains the UI-presentation note.
- **Tests (new).** `test_mcp_error_message_helper_headlines` (every class, the operator's string, an unknown and an empty one), `test_mcps_tab_error_shows_plain_headline_and_details`, `test_library_editor_connection_error_plain_headline`. Proven: with the renderers reverted the tab and library tests fail, then restored.
- **Gates.** Static guards 265 passed; `make test-unit` 5441 passed, 10 skipped (11:06); lanes (`THE_ONE_TEST_NETNS=1`): agents 153 passed, 2 skipped (6:03); library 153 passed, 1 skipped (8:25); shared 465 passed (11:44). `ruff check` and `ruff format --check` clean.
- **Not done:** the two-theme screenshots (evidence only) were not taken; the DOM assertions stand in. The leg 5 walk will show it.

---

### Leg 2: chat-and-test-fixes

**Status**: landed (2026-10-06)

- **0119.** `join`'s degraded branch unsubscribes the bound socket (`remove_subscriber` before `session = None`). Test: `TestExistingIdJoins::test_degraded_same_id_rejoin_unsubscribes_the_socket`.
- **0120.** `app.py`: `_started_tasks`, `_running_tasks`, `_cancel_tokens` and `_notify_cancelled_once`. `_spawn_message_processing` is now a thin wrapper (first statement marks the task started; `except CancelledError` sends once unless the task or the batch was running) around the unchanged lock + `_process_and_broadcast` body (moved to `_locked_message_processing`). `_process_and_broadcast` marks running at its `try`, and its `except` sends through the helper after saving partial text. The `cancel` branch creates the token before any `t.cancel()` and sends only when no task in the batch started. Token dropped in `_clear_session_inflight`. Harness: `NoYield` step type, `_reset_state` clears the new state. Tests: `TestCancelSendsExactlyOneCancelled` (a)-(d). The squawk's browser check is dropped (reason in the squawk).
- **0115.** The test quiesces, records `content_freshness`, clicks Re-index all, and polls (bounded, fails loudly) for freshness changed and nothing pending or indexing. `indexed_at` is microsecond ISO and `scope=all` re-stamps each file, so no extra signal was needed.
- **Deleted-agent heal.** `chat.js`'s `~new` hydrate keeps the peek fast path and also runs a background forced `agents` read, re-validating through `validatePending` (one extra `GET /api/agents` per `~new` hydrate; no test pins that count). New `test_a_pending_chat_whose_agent_was_deleted_heals` (cold and warm, delete via the API); the warm half fails with the forced read disabled (falsified, restored).
- **Docs.** `the_one/agents.md`: the WebSocket protocol table rows (`join`, `cancel`) and the `~new` hydrate line.
- **Gates.** `ruff check`/`format --check` clean; static guards 258 passed; `TEST_TIMEOUT=3000 make test-unit` 5438 passed, 10 skipped (11:30); chats lane 164 passed (4:19); library 151 passed, 1 skipped (8:19); shared 465 passed (11:49).

---

### Leg 1b: focus-after-action

**Status**: landed (2026-10-06)

- **The helper.** `static/js/focus-after.js` (`App.focusAfter`: `begin`, `restore`, `cancel`, `defer`, `flush`), loaded in `index.html` right after `nav.js`. A `.editor-title:focus-visible` ring was added in `components.css`. The five studio titles gained `tabindex="-1"` (`agent-editor.js`, `mcp-server-editor.js`, `connector-editor.js`, `knowledge-section.js` create and detail).
- **Call sites** (`begin` -> `restore`):
  - **Agent** (`studio.js`): `save(false)` begins at the top and restores to the title after `renderEditor(found)` (the null-`found` branch does not restore); `save(true)` begins at the top, `defer`s once the name validates, and `doSelect`'s final `.then` `flush()`es after `renderEditor`/`writeUrl_`; `cancelEdit` (edit) begins on Cancel and restores after `renderEditor` + `checkDirty`. Failed Save/Create: the `.catch` restores to Save (and clears the deferred token). A create that is superseded (`!stayed`) clears the deferred token.
  - **MCP** (`mcp-server-editor.js`): Save begins before the request; edit restores to the title after the snapshot reset and disables; create `defer`s before `onSaveSuccess`, and `studio.js` `ready.then` `flush()`es after `renderMcpSourceEditor`; the `.catch` restores to Save. Edit-mode Cancel begins and restores after `recaptureSnapshot`. Test connection: `begin(testBtn)` in the click handler before `handleTestConnection` disables it, passed as `opts.focusTok`; `restore(tok, testBtn)` once, inside `settle()`. The auto-run Refresh after create passes a null token (so it never supersedes the create's parked restore).
  - **Connector** (`connector-editor.js`): Save begins before the request; edit restores after the disables; create `defer`s before `onSaveSuccess` and `renderConnectorsSection`'s `Promise.all.then` `flush()`es after `renderConnectorEditor`; the `.catch` restores to Save. Edit-mode Cancel `defer`s (it re-mounts through `fetchAgents`) and the same mount flushes it; create-mode Cancel takes none.
  - **Knowledge base** (`knowledge-section.js` detail): Save begins before the disable, `defer`s on success (the remount fetches status and items), and `mountKnowledgeDetail`'s `.then` `flush()`es after `renderKnowledgeDetail` (after the folder-path focus branch, which stays untouched); the `.catch` restores to Save. Cancel begins and restores to the title after `recapture`. Knowledge-base create is unchanged.
  - **Provider** (`provider-editor.js`, `admin.js`): `performSave` begins before the request; edit restores to the title after `checkDirty`; create `defer`s before `onSaveSuccess` and `mountProviderItem`'s `ready.then` `flush()`es (`else` of `reveal`; the reveal branch clears the deferred token, so the two stay exclusive); the `.catch` restores to Save. Edit-mode Cancel begins and restores after `checkDirty`. Test begins before the disable and restores in both the `.then` and `.catch`. `keepFocus`/`hadFocus` removed.
  - **Tool** (`tools-editor.js`): Save begins before the disable; success restores to the title after `onSaveSuccess`, failure restores to Save right after the re-enable; Cancel begins and restores after the re-mount; Test begins before the disable and restores in `.then` and `.catch`.
  - **Teardowns calling `cancel()`**: `studio.js` `closeOpenItem`; `admin.js` `_discardEditor`, the `_setCategory` rebuild branch and `_closeOpenItem`.
- **Design point found while testing.** The agent editor's Save re-renders the whole editor, so a user who focused a field *inside* that editor during a held save loses it to the re-render itself; the helper then restores to the title (focus was lost). The never-steal pin for the agent therefore moves focus to the Agents list filter, which survives the re-render. The provider (which patches in place) is pinned with the name field.
- **Tests.** New: `test_ui_focus_after_contract.py` (12 tests, x2 engines = 24), `test_flow_agents_focus_after.py` (4), `test_flow_settings_focus_after.py` (7), `test_flow_studio_library_focus.py` (6; added to `library_pat` in `scripts/run-tests.sh`). Changed: `test_index_asset_cache_busting.py` (the script count, 82 to 83).
- **Docs.** `the_one/agents.md` "Focus after an in-place action (M25 F6 L1b)"; one paragraph in `CLAUDE.md`.
- **Gates.** `ruff check` / `ruff format --check` clean; static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`) pass; `TEST_TIMEOUT=3000 make test-unit`: 5430 passed, 12 skipped, 1 failed (the script-count pin above, since fixed and re-run green); agents lane 144 passed, 2 skipped (6:02); library 151 passed, 1 skipped (8:21); settings 198 passed (6:19); contracts (`THE_ONE_REQUIRE_WEBKIT=1`) 670 passed, 3 skipped (2:52); shared 465 passed (11:46). The unit suite was run before the script-count fix; `test_index_asset_cache_busting.py`, `test_nav_helper.py` and `test_run_tests_lanes.py` re-ran green (81 passed).

---

### Leg 3: servicing

**Landed** (2026-10-06). Squawks 0121-0125 completed, commit reference "pending the Flight 6 legs 1-3 commit". No product code changed.

- **0121:** `.flightops/agent-crews/behavior-tests-execution.md` gains run rules 7-11 (driver and browser lifetime, PID-only stops, the report-file hand-off, the checkpoint ledger, verify evidence paths) and the matching Executor, Validator and per-step prompt text. Structure check: `## Crew`, `## Interaction Protocol`, `## Prompts` present; all six `###` prompt subsections hold a fenced block.
- **0122:** wording in `jump-to-palette`, `shell-navigation-smoke`, `chat-roundtrip`, `start-a-chat`, `workbench-navigation`, each with an `Updated` line; every step re-read against run `2026-10-06-06-01-26`. `studio-description` is named only as an `id`. `list-and-detail.md` untouched. No listed item skipped.
- **0123:** `windows-window-chrome.md` revised for all seven listed items (`Revised` line added); step 7 keeps its intent (dark survives a hard stop, no light frame on relaunch) and judges the outcome when the flush is not observed.
- **0124:** `CLOSURE_UV_EXPORT_ARGS`, `CLOSURE_PIP_REQUIREMENTS_ARGS`, `CLOSURE_PIP_EDITABLE_ARGS` in `scripts/windows_test_copy.py`; new `test_closure_commands_match_ci_task` parses the CI YAML. Mutation check: changing one side fails it.
- **0125:** "Upgrade blocker: pywebview 6.x" bullet in `the_one/agents.md`'s Window chrome block and a comment on the `gui` pin in `pyproject.toml`.
- **Gates:** `tests/test_windows_test_copy.py` 157 passed; `TEST_TIMEOUT=3000 make test-unit` 5433 passed, 10 skipped; `ruff check` and `ruff format --check` clean.

---

### Leg 1a: visible-fixes

**Status**: landed (2026-10-06)

- **DD4 / squawks 0112, 0081.** `create_provider` and `create_chat_session` catch `ValidationError` and raise 422 (`include_context=False, include_input=False`, so an `api_key` is never echoed). The provider form's `performSave` goes through `App.api.fetchJson` (only that switch changed in `provider-editor.js`; DD2 is leg 1b).
- **0113 / 0114.** The Tools tab master toggle has `aria-label="Enable all {cat} tools"`; the `field-info-icon` buttons in `provider-editor.js` (3), `tools-editor.js` and `tools-form-helpers.js` gained `aria-label` (the MCP editor's already had one).
- **DD3 / 0116.** `.tile-title-row` flex row in both tile builders; the badge is in the flow; the `calc(100% - 128px)` reserve is removed. `tools-grid.js` stayed inside its existing HTML string (no new sink).
- **A5.** `index.html`'s `#app-sidebar` carries `aria-label="Sidebar"`.
- **DD11.** A visually hidden `h1[data-testid=root-heading]` at the Agents root (synced in `updateContentVisibility`) and each Library root (beside `renderLibraryEmpty`); absent with an editor open. `list-and-detail.md` step 2 re-authored (`Updated` line added).
- **DD10.** The provider Models section is "Available models" with a help line linking Agents; rows lose affordance (`cursor: default`).
- **Tests.** New: 3 unit (`test_provider_api.py` x2, `test_db_api.py` x1), `tests/test_index_html_static.py` (1), browser `test_flow_settings_visible_fixes.py` (11 incl. parametrized) and `test_flow_agents_root_heading.py` (6). Changed: `test_design_tokens_a11y.py` (tile rules), `test_flow_settings_items.py` (reading order now inside the title row), `docs/ui-testid-registry.md` (3 new ids).
- **Gates.** `make test-unit` 5433 passed, 10 skipped (11:00); settings lane 191 (the one failure, the reading-order test above, fixed and re-run green: 30/30 in file); agents 140 passed, 2 skipped (5:39); library 145 passed, 1 skipped (7:58); shared 465 passed (11:47); static guards and ruff pass. `contracts` not run: no `ui/` file changed.
- **Squawks** 0081, 0112, 0113, 0114, 0116 completed; commit reference left "pending the Flight 6 legs 1-3 commit".

### Leg 5: inline batch (review polish)

- **MCP error announced (4.1.3):** `buildMcpError` (`mcps-tab.js`) now sets `role="alert"` on the error root. Each build is a fresh node, so it is announced on insertion only; unrelated re-renders do not rebuild it, and a successful Refresh still replaces it. Pinned on both surfaces (`test_studio_mcps_tab.py`, `test_flow_studio_mcp_editor.py`).
- **Info icons read once:** dropped `aria-describedby` from every `field-info-icon` button that also had an `aria-label` with the same text (`provider-editor.js` x3, `tools-editor.js`, `tools-form-helpers.js`). The "Test connection" hidden span (used only by the button) is removed. The hidden `-desc` spans in the provider editor and the tool form fields stay, because their inputs still use them as `aria-describedby` (a different control, read once there). `title` is unchanged. The MCP "Sensitive" icon already had no describedby. Pins updated: `test_flow_settings_visible_fixes.py` (now asserts no describedby on icons), `test_flow_provider_editor.py` (two pins flipped to None).
- **Cancel contract:** one clause added to the `cancel` row in `the_one/agents.md`: a second `cancel` during unwinding replaces the per-session token, so at most one `cancelled` per `cancel` message.
- **Proof:** each new assertion failed with the change reverted (info icons 2 failed; MCP agents-tab 1 failed; Library editor 1 failed), then passed restored.
- **Gates:** static guards 261 passed; agents lane 153 passed, 2 skipped; library lane 153 passed, 1 skipped; settings lane 201 passed (first run had 2 failures from the provider-editor pins, fixed, whole lane re-run); `make test-unit` 5441 passed, 10 skipped (11m44s).

## Flight Director Notes

### Planning (2026-10-06)

- **The operator said "start flight 6"** after v0.10.0 shipped (PR #221 and the release
  PR #222 were merged by the Flight Director at the operator's instruction).
- **The reconnaissance** above came from a read-only sweep by a Sonnet agent.
- **The operator's answers** (crew interview, 2026-10-06):
  1. **Session:** "Fixes first, then walk".
  2. **The carried squawks:** "Fix them in this flight".
  3. **Windows:** "I already installed the version we just released, we can use that"
     (the walk uses the operator's installed v0.10.0).
  4. **Narrow widths:** "Show me first" (decided during the walk).
- **The flight spec** is written: nine design decisions and five legs. It goes to an
  Architect design review next.
- **Design review, cycle 1** (Architect, Opus): **approve with changes**. Three highs,
  six mediums and four lows. All were applied:
  - **DD2 narrowed:** in-place actions only. Closing actions keep Flight 3's DD8, and
    knowledge-base create keeps its folder-path focus (squawk 0101). The fallback is
    `.editor-title` with heading levels unchanged. The rule records the control when the
    action starts, lands after `nav.js`'s `setTimeout`, is guarded by `editorGen`, and
    replaces `keepFocus`/`hadFocus`.
  - **New DD11:** a visually hidden root `h1`, with `list-and-detail` step 2 re-authored
    in leg 1.
  - **DD4:** `fetchJson` error flattening; no input echo (the `api_key` leak); squawk 0081
    folded in (`create_chat_session`).
  - **DD5:** 0120's queued-task case, "at most one `cancelled`", and the browser check
    included or explicitly dropped.
  - **DD3:** wrapper elements in both builders, and the bounding-box tests.
  - **0114:** six sites.
  - **DD6:** the walk's operating rules (reachability, the mint host, hard reload versus
    restart, re-verifying by probe, 8485 is the operator's call), SC9 step 16 judged from
    the operator's recollection, and steps 17 and 19 operator-only.
  - **DD8:** three more contract specs.
  - **New DD12:** review and commit for each phase.
  - **SC8's evidence:** the Flight 3 and 4 probe records.
- **Answers to the review's questions** (Flight Director):
  1. The root `h1` is option (c), visually hidden (DD11).
  2. Knowledge-base create keeps its folder-path focus.
  3. Squawk 0081 is folded into leg 1.
  4. SC9 step 16 is judged from the operator's recollection.
  5. Inline walk fixes get a batched Reviewer pass before leg 4's commit.
- **No second cycle.** Leg 1 is HIGH risk and gets its own design review, which re-checks
  DD2 and DD11 against the code. That saves the waiting operator about 10 minutes.
- **Status: ready.**

### Execution (2026-10-06)

- **Setup.** The agentic workflow started and the phase file `leg-execution.md` was
  loaded. The flight moved to `in-flight`.
- **Leg split.** `visible-fixes` was split into 1a (the independent fixes) and 1b
  (`focus-after-action`, DD2).
  - **Why:** DD2 changes focus behaviour in six editors, where existing tests and specs
    pin focus (the Flight 4 debrief's "pre-split behaviour changes" lesson).
  - **Order:** they run one after the other, since both touch `provider-editor.js`.
- **Leg 1a: designed, risk tier LOW.**
  - Why: additive, established patterns. The 422s follow the sibling routes' pattern,
    and the rest is names, CSS, a hidden heading and copy.
  - The flight-end Reviewer covers it, and the operator is waiting on the walk.
- **Leg 1b: designed, risk tier HIGH.**
  - Why: a behaviour change across six editors, with neighbouring focus pins.
  - It goes to a design review (a Developer, Sonnet).
  - **The survey's findings,** which shaped DD2's mechanism:
    - the disabled replacement buttons;
    - the studio titles with no `tabindex`;
    - the async mounts;
    - early disables;
    - `keepFocus`'s actual failure mode (a click that does not focus the button);
    - no existing pins after Save, Cancel or Test.
  - **The design:** one `App.focusAfter` helper (`begin` when an action starts, `restore`
    after its mount), with a never-steal rule and a supersede rule. Targets are the
    title, or the Test button once it is re-enabled.
- **Leg 1b design review, cycle 1** (a Developer, Sonnet): **approve with changes**. Two
  highs, four mediums and three lows. All were applied:
  - "focus lost" now also counts a disabled or detached `activeElement`, or the control
    itself;
  - a two-engine contract test (`test_ui_focus_after_contract.py`, `contracts` lane);
  - `begin` before the Test buttons' disable, and `restore` once, from `settle()`, with a
    null token tolerated;
  - `defer`/`flush` pending tokens for the async create mounts (agent, connector, MCP),
    and `cancel()` from every teardown;
  - the failed-save restore site per editor;
  - provider `reveal` and `restore` kept exclusive;
  - five title sites and a focus style;
  - routes named for the Test interceptions;
  - all the dirty-confirm and focus test files in the gate.

  **No second cycle:** each fix is the reviewer's own prescription, and the flight-end
  review covers the result. **Leg 1b: ready.**
- **Leg 2: designed, risk tier HIGH** (a change to the WebSocket state machine). It
  goes to a design review after 1b's.
- **Leg 2 design review, cycle 1:** **approve with changes**. Three highs, two mediums
  and three lows. All were applied:
  - **The 0120 design:**
    - *started* and *running* markers, with the started marker as the coroutine's first
      statement, since an unstarted task runs no body code;
    - a per-cancel token, and the `_notify_cancelled_once` helper;
    - the running task is the **sole sender** when one exists, after its partial save
      (the designer's decision on review question 1);
    - the lock-wait wrapper, and the `cancel` branch sending only for an all-unstarted
      batch.
  - **The harness** gains a `NoYield` step to make case (a) constructible, and the four
    cases are spelled out.
  - **The warm deleted-agent heal** needs a real fix: a background forced `agents` read on
    the `~new` hydrate (review question 2: accepted, with pinned request counts updated).
  - **0115's wait details:** pending and indexing at 0; the `indexed_at` resolution
    check.
  - **0119** is minimal, and its test reuses `TestExistingIdJoins`.
  - **Review question 3:** only the WebSocket spawn path changes.

  No second cycle: the fixes are the reviewer's prescriptions. **Leg 2: ready.**
- **Leg 3: designed, risk tier LOW** (docs, specs, one pin test, no product code).
- **Leg 4 (`section-labels`, DD13): designed, risk tier HIGH.** It is multi-surface: the
  `App.ui` library CSS plus about 50 editor sites. It went to a design review (a
  Developer, Sonnet).
- **Leg 4 design review, cycle 1:** **approve with changes**. Two highs, seven mediums
  and three lows. All were applied:
  - **The highs:**
    - the `.section-title-row` rule moves to the row's `::after`, since a flex-item
      span's own `::after` collapses;
    - `kb-panel-title` (a file path) opts out through `.section-title--plain`.
  - **The mediums:**
    - two test pins are named (`test_ui_nav_groups_contract.py:310`,
      `test_design_tokens_a11y.py:904-905`);
    - the first-group padding uses a sibling rule, since `:first-of-type` counts hidden
      groups;
    - the dead `h2.section-title` bump is deleted, and the typography demo rewritten;
    - the telemetry strip opts out;
    - the four review questions are decided below.
  - **The lows:** the `.section-description` gap, the docs locations, and `nowrap` on
    long labels.

  **The Flight Director's answers to the review questions** (leg D1–D6):
  - the rule runs past the info icon;
  - the editor-section divider is dropped where a section opens with a title, so the
    lines never stack;
  - the provider models sub-labels stay quiet;
  - the danger zone's rule is `--status-danger`, like its text.

  **No second cycle:** the fixes are the reviewer's prescriptions plus four style calls,
  and the flight-end review and the walk cover the result. **Leg 4: ready.**
- **Legs 4b (`chat-polish`, DD14 and DD16) and 4c (`root-pages`, DD15): added from operator reports
  during execution.** 4b is risk tier LOW, so it gets no design review. 4c is HIGH, since
  pinned copy and DD11 run across many tests and four specs.
- **Leg 4c design review, cycle 1** (a Developer, Sonnet): **approve with changes**. Two
  highs, three mediums and three lows. All were applied:
  - **The highs:**
    - the unnamed pins are now listed: `test_flow_agent_crud.py`'s "No agents yet" (kept
      valid by making the none-variant line "No agents yet."), and the strict-mode `h2`
      locators in `test_flow_agents_root_heading.py:58` and
      `test_flow_studio_library_list.py:619`;
    - the start page avoids `.page-header`, since a Library-root test asserts none.
  - **The mediums:**
    - the `h1` stays the existing synced sibling, restyled, never a second `h1`;
    - the full list of spec steps;
    - the page intro reworded so it does not repeat the Library list column's own intro.
  - **The lows:** `App.ui.util.icon`, the sink baseline, and the pixel-test note.
  - **The suggestions taken:** a failed-collections test, and the responsive wrap.
  - **The Flight Director's answer on alignment:** left-aligned, like the Settings
    pages.

  **No second cycle:** the fixes are the reviewer's prescriptions. **Leg 4c: ready.**
- **Implementation order:** 1a, then 1b, 2, 4, 4b and 4c, one Developer at a time (they
  share files). Leg 1a landed; its report was received after a resend request. Leg 1b
  landed: all lanes green, plus one unit pin (the `index.html` script count) fixed and
  re-run. Leg 2 was spawned next. Its prompt adds "re-run the full unit suite after any
  fix", because 1b re-ran only the fixed file.
- **Legs 2, 4, 4b, 4c and 4d landed** in turn, each with its lanes green. Leg 4d's prompt
  added "prove each new test fails without the change", because 4c had not.
- **The flight-end review of legs 1a–4d (DD12).** A Reviewer and an Accessibility
  Reviewer were spawned in parallel.
  - **The Reviewer is Sonnet, not Haiku.** The diff touches a credential surface: the
    422s must never echo a submitted `api_key` (`include_input=False`), and the crew file
    names credentials as a Sonnet trigger.
  - The Accessibility Reviewer runs because the legs change the UI.
- **Review result: both reviewers confirmed** (`[HANDOFF:confirmed]`), with no blocking
  issue.
  - **The Reviewer** ran the static guards (261), the index, nav, lanes and inventory
    pins (93), the WebSocket, cancel and desktop-shell suites (116), and the two
    provider 422 tests. All passed. It found no race giving a double or missing
    `cancelled`, and confirmed that the 422s never echo the `api_key`.
  - **Its non-blocking nits:**
    1. `mcp-server-editor.js`'s save `.catch` also catches an exception thrown by
       `onSaveSuccess`. **Accepted:** not new in kind.
    2. A second `cancel` during unwinding replaces the token, so there is one
       `cancelled` per `cancel`. **Document it** in `agents.md` (the leg 5 batch).
    3. One extra `GET /api/agents` per `~new` hydrate. **Intended** (leg 2).
  - **The Accessibility Reviewer** checked contrast, the guards (260), headings, focus,
    the decorative rules, the `text-transform`-only uppercase, the start pages and the
    disclosure. **Its non-blocking items:**
    1. The MCP error block is not announced (4.1.3; the old markup wasn't either).
       **Fix** in the leg 5 batch: `role="alert"` on the error root, or a polite live
       status host.
    2. Provider info icons have an `aria-label` and an `aria-describedby` with the same
       text, so a screen reader reads it twice. **Fix** in the leg 5 batch by dropping the
       duplicate description where the label carries it, at every info-icon site leg 1a
       touched.
    3. The danger-zone rule is decorative. No action.
    4. The 10px labels scale with zoom but not with a minimum font size, like every px
       size in the app. No action.
- **Legs 1a–4d are completed and committed together (DD12).** The polish items above go
  into the leg 5 inline batch, which gets its own review before leg 5's commit.

---

## Decisions

- **Committed:** `52f7612`, "flight/6: Fixes before the walk (legs 1a-4d)". It was pushed
  and opened as draft PR #227.
- **Leg 5 (the light walk, DD18).**
  - **The instance:** 8486, scratch data `/tmp/the-one-f6-walk`, dev mode, seeded through
    the API.
  - **Access:** a one-time handoff to the operator's Windows browser. The first link
    expired before use, and the operator asked for a second.
  - **The verdict: "the walk looks good."** All seven items are accepted as they are:
    - the section labels;
    - "Available models";
    - the tile title row;
    - the start pages;
    - 12-hour times and the composer;
    - the plain MCP error;
    - focus after Save.

    No inline fix came from the walk.
  - **The seed's caveat:** it was seeded before local midnight, so by the time of the walk
    its "today" chats had moved to Yesterday (weekday labels). The 12-hour list times are
    pinned by `test_clock_formatter_edges` and the chat-list tests.
  - **The inline batch:** a Developer took the review polish (the `role="alert"` MCP
    error, info icons read once, the cancel-contract note).
  - **DD17:** the Flight Director's live check on a Windows test copy, run in parallel.
- **The operator's direction after the walk** (2026-10-07): "go ahead and wrap up the
  mission and debriefs, then merge to main and cut a patch release".
  - **DD9 is answered:** a patch release, v0.10.1, cut after the merge.
  - **Authorized:** merging PR #227 to `main`, and the release.
  - **Autonomous from here:** leg 5's batch review and commit, leg 6 (mission close), the
    flight debrief and the mission debrief.
- **DD17 checked live on a Windows test copy (2026-10-07).**
  - **The copy:** built by `setup` from the working tree (source build, not frozen), run
    as `launch --port 8490 --cdp-port 9390 --max-minutes 15 --tree-id f6dd17`, with
    scratch data under the helper's root.
  - **Seeded** through the API: an `openai-compatible` provider pointing at an unused
    port (never called), an agent, and a session whose stored history holds one reply.
  - **The probe** used Playwright over CDP: `location.hash` to the session, then a mouse
    drag across the reply.
  - **The result:**
    - `pywebview.platform` is `edgechromium`;
    - `getComputedStyle(document.body).userSelect` is `auto` (pywebview's injected
      `user-select: none` is gone);
    - the reply's own `userSelect` is `auto`;
    - the drag selected "This reply should be selectable in the desktop window.", inside
      `.msg.assistant`.

    **Pass.**
  - **The session:**
    - bracketed by `snapshot --out` and `--compare`; the compare was `ok` with no
      allowed changes or failures;
    - the installed app was untouched (same PID and creation time);
    - the copy was stopped by identity (`stop --tree-id f6dd17`), watchdog included.
- **The published design system was updated (SC7, DD13)** at
  https://claude.ai/artifact/51jpj1RcXp18MehEQAteWs, versions 12 (files) and 13 (index).
  - **README:**
    - the section-label recipe, replacing "quiet" section titles and the "no eyebrows"
      rule;
    - the rail shell in Layout, replacing the top bar and the 240px sidebar;
    - the four destinations;
    - 12-hour clock times;
    - start-page and plain-error copy.
  - **A new SectionLabel card** (README and preview: nav captions, section headers, the
    danger zone, `--plain`).
  - **`bundle.css`:** the section-title, caption, editor-section and danger-zone blocks,
    copied from `components.css`.
  - **TopBar and SectionNav** are marked retired (Flights 2 and 3), not deleted.
- **GitHub issue #207** (a reusable JS component layer) was reviewed at the operator's
  request.
  - **The verdict: partly resolved.** Mission 25 delivered the layer: 16 `App.ui`
    factories, DOM-returning ES5 with no build step, a single icon path, the gallery
    rendering real factories, and two-engine contract tests.
  - **Not done:** the migration of the existing editors.
    - `_el` is still copied 3 times; `_fieldGroup` and `_section` twice each.
    - The danger zone is hand-written 5 times.
    - There are no factories for tiles, confirm-delete or an expandable panel.
    - 33 `App.icon` string call sites remain.
    - There is no guard on component-owned classes.
  - At the operator's direction, the issue stays open with a status comment
    (https://github.com/msieurthenardier/the-one/issues/207#issuecomment-6036899898).
    The mission debrief should carry it as the next control-library mission's scope.
- **The leg 5 inline batch and leg 6's documents were reviewed:** both reviewers confirmed.
  - **The Reviewer** (Haiku: no security surface) found no issues. It spot-checked five
    §15 resolutions and the D6–D9 rows.
  - **The Accessibility Reviewer** found `role="alert"` acceptable: a fresh node on
    insertion, and a collapsed `<details>` is not read until opened. No orphaned
    descriptions.
  - **Two non-blocking notes:**
    1. `mcp-server-editor.js`'s `renderRetryUi` sign-in message has no live role. It
       predates this flight and belongs to the OAuth sign-in flow. **Accepted**, out of
       DD19's scope.
    2. A stale comment in `tools-form-helpers.js` (about lines 115–118) still says the
       button carries `aria-describedby`. It is **fixed with leg 6's gates**.
- **Leg 5 is completed.** It is committed with leg 6's documents. Leg 6 stays in flight
  for the behavior re-runs, the gates and the SC ticks.
- **2026-10-06, during planning: the provider Models list (DD10).**
  - **Reported:** "you can't select a model on the provider page" (an Anthropic and a
    Claude Max provider).
  - **Diagnosis:** the Models list is informational. It is unchanged since before
    Mission 25 (`areas/admin/provider-models.js` `renderBasicModels`), and models are
    picked per agent.
  - **The operator's choice:** "We probably just need a label that explains that one of
    the available models can be selected per agent."
  - It goes into leg 1 as a look-and-feel fix.
- **2026-10-06, during execution: section labels (DD13).**
  - **Reported:** "the headers on the left navigation aren't great. They are hard to
    distinguish from the menu items themselves… its all of them including in the
    configuration pages."
  - **The options.** The Flight Director published four options
    (`https://claude.ai/artifact/HBur9t8QP7nguottk6VKAr`), and the operator chose **D:
    Eyebrow with a rule**.
  - **The work:** new leg 4, `section-labels`, which is multi-surface (library CSS plus
    about 50 `.section-title` sites), so it gets a lightweight design review under DD7.
    The walk and close legs move to 5 and 6.
  - It is an operator-accepted SC8 deviation from the reference spec's §3 group label.
- **2026-10-06, during execution: local 12-hour times (DD14).**
  - **Reported:** "The time on todays chats is military time. We should format that
    normally with am/pm."
  - **Fix or feature (DD7): a fix.** It is look-and-feel, with one shared formatter over
    two chat surfaces: the Chats list's Today rows (`HH:MM`) and the message attributions
    (`HH:MM:SS UTC`). Both now read local `h:mm AM/PM`, which also answers decision-sheet
    item B5. The work is new leg 4b (`local-times` then, renamed `chat-polish` with DD16), risk tier LOW.
  - **Left out:** the Knowledge `Indexed:` line, a precise freshness signal that tests and
    `kb-studio-round-trip` compare across a re-index.
  - **The time-zone setting: out of scope** (the Flight Director's call; the operator
    said "if its in scope"). It is new behaviour, so the DD7 gate sends it to design.
    Mission 25 is navigation, and the display already follows the OS time zone. The
    operator's other idea, a built-in time tool, needs the same zone answer, so both go
    into one GitHub issue: [#223](https://github.com/msieurthenardier/the-one/issues/223).
  - It is an operator-accepted SC8 deviation from the reference spec 5.1's Today `HH:MM`.
- **2026-10-06, during execution: the Agents and Library start pages (DD15).**
  - **Reported:** the Library root "just says select a kb or add one… it should be a
    description of what each of the things are with an add button for each of them".
    Then: "similarly we should add a friendly description to the agents base page
    including what agents are."
  - **Fix or feature (DD7): a fix.** It reshapes two existing empty states and reuses the
    existing create actions. The testids are kept (the contract); the copy and the root
    `h1`'s visibility (DD11) change.
  - **The work** is new leg 4c, `root-pages`, risk tier HIGH: pinned copy and DD11 run
    across many tests and four specs. It goes to a design review.
  - The Flight Director drafted the copy into the leg. The operator reviews it in the
    walk.
  - It is an operator-accepted SC8 deviation from the reference spec's root empty state.
- **2026-10-06, during execution: the composer's width (DD16).**
  - **Reported:** the message box's max width "looks a little strange because the
    context % indicator is pinned to the right. I think we just allow the message box to
    expand to the max width."
  - **Fix or feature (DD7): a fix.** It is CSS on one surface: the box, the staged-image
    row and the queued chip lose their 760px cap.
  - **The work** joins leg 4b, which had not started and is renamed `chat-polish`. One
    composer pin flips (`test_flow_chat_composer.py`).
  - It is an operator-accepted SC8 deviation from the reference spec 5.5's max 760px.
- **2026-10-06, during execution: text selection in the desktop app (DD17).**
  - **Reported:** "the regular response message box has no copy option, and you cant even
    highlight to copy paste. The code box does but not the regular message."
  - **Diagnosis.** pywebview's `create_window` defaults to `text_select=False`, and its
    `customize.js` then injects `body { user-select: none }`. This was confirmed in the
    installed v0.10.0's bundled `webview/js/customize.js`. `shell.py`'s main-window
    `_create_kwargs` never passed `text_select`.
  - **Fix or feature (DD7):**
    - the selection is a **fix** (`text_select=True`, joining leg 4b), verified live in
      the walk on a Windows test copy;
    - the per-message Copy button is a **feature**, out of scope:
      [#224](https://github.com/msieurthenardier/the-one/issues/224).
- **2026-10-06, during execution: a light walk (DD18), and the decision sheet answered.**
  - **The operator:** "I've been using the newly installed version for testing, it looks
    pretty good with the feedback I've already provided. We can keep the walk though
    pretty light."
  - **The decision sheet,** answered in one batch, with each item kept unless the
    operator ticked it:
    - **Flight 5 DD12** (window): all kept. The title bar stays the sidebar's colour, the
      inactive title text stays grey, and a first launch stays 1440×900, centred.
    - **Narrow widths and F5 DD12's "floor at 1024?"**: keep thirds snapping, and design a
      narrow layout later: [#225](https://github.com/msieurthenardier/the-one/issues/225).
      There is no narrow-width leg in this flight.
    - **Flight 4:**
      - B1 (the Dark pending-row wash), B2 (no visible ring on `rail-jump-to` after a
        pointer close) and B3 (focus on `<main>` after Continue): all kept;
      - B4 (bubble times 1–4 seconds off after a reload) is moot under DD14's minute
        precision, except across a minute boundary;
      - B5 is answered by DD14.
    - **SC9:** "All fine" from the operator's v0.10.0 use (the tint in both themes, an OS
      theme flip, inactive dimming, snap layouts and Win+arrows, the size kept after the
      upgrade, Ctrl K, the splash). Step 16 is judged from that use, and steps 17 and 19
      are not run (operator-only and optional under DD18).
  - **Leg 5 becomes a light walk:** one pass over this flight's own fixes on 8486, plus
    the Flight Director's DD17 probe on a Windows test copy.
- **2026-10-06, squawk 0126 logged** (from leg 1b's report): the connector editor's title
  keeps the old name after an edit-mode rename and save. It is a routine defect that
  predates the flight. It rides with leg 4c, which works in the same Library editors, and
  is completed there.
- **2026-10-06, during execution: the MCP connection error message (DD19).**
  - **Reported** with a screenshot of the production agent MCPs tab: "Error loading
    tools: MCPConnectionError: MCP connect failed: cancelled during initialize
    (cross-task cleanup deadlock; …): Cancelled via cancel scope …", called "far from
    friendly".
  - **Fix or feature (DD7): a fix.** It is presentation only: a shared helper gives a
    plain headline, with the raw text under "Technical details", on two surfaces (the
    MCPs tab and the Library MCP editor). The work is new leg 4d, risk tier LOW (no
    contract change; the flight-end review covers it).
  - **Out of scope:** the client's cancelled path hides the original cause, which is
    [#226](https://github.com/msieurthenardier/the-one/issues/226).
  - **The operator's instance** (8484) was not touched. The Flight Director's likely
    cause, from the screenshot: the failing "Goldfinch Robot" source last connected on
    Goldfinch v0.12.0, while its sibling "Goldfinch Family" reports v0.13.0. So the
    Robot source's key or URL is probably stale since the Goldfinch upgrade.

---

## Deviations

---

## Anomalies

---

## Session Notes
