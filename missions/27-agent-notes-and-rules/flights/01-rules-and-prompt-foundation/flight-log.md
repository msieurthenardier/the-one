# Flight Log: Rules and the Prompt Foundation

**Flight**: [Rules and the Prompt Foundation](flight.md)

## Summary

Planned 2026-10-09 while the operator was away overnight, under their
authorization to plan and execute up to the mission HAT, making judgement calls
along the way. Autonomous judgement calls are marked in the flight's Design
Decisions and gathered here for review at the HAT (Flight 3).

---

## Leg Progress

### rules-backend

**Status**: landed (not committed).

**Changes**
- Schema v42 (`CURRENT_VERSION = 42`): `agent_rules` table + index, and the
  guarded `agent_revisions` rebuild (`ON UPDATE CASCADE` on `agent_name`, the
  self-reference naming the final table, all 11 columns copied, index
  recreated, FK enforcement restored).
- `the_one/db/_rules.py` (limits, `RULES_HEADING`, errors, text validation,
  numbered-block renderer), `AgentRule` model, `AgentRuleRepository`.
- `compose_system_prompt(base, persona, *, rules=(), notes=())`;
  `AgentConfig.get_system_prompt` removed.
- `the_one/agent/prompt_layers.py::build_system_prompt`; wired into
  `AgentFactory.create` and an async `apply_pending_revision` (both `app.py`
  settle sites await it; failure falls back to base + persona and still sends
  `done`).
- Rules REST routes in `api.py` (GET/POST/PUT/DELETE and `PUT /rules/order`).
- `the_one/agents.md`: new "Rules and prompt composition (M27 F1)" section;
  the two existing `apply_pending_revision` mentions updated.
- Tests: `TestSchemaV42` (fresh replay; populated v41, both the normal and the
  `agent_revisions_new`-named self-reference shape; guard re-run; rename; delete
  cascade), `tests/test_prompt_layers.py`, `tests/test_agent_rules_api.py`,
  `TestRulesAtSettle` + updated pins in `test_self_configuration_write.py`
  (now under a patched `the_one.db.connection.get_connection` / `isolated_db`),
  connector AC20 test in `test_connectors_inbound.py`, composer tests replacing
  the `get_system_prompt` tests.

**AC5 evidence (the rename test fails without the rebuild).**
`test_rename_carries_revisions_and_rules` first rewinds the database to the
v41 shape (the old `agent_revisions` FK, no `ON UPDATE`) and asserts that
`SQLiteAgentStore.rename` raises `FOREIGN KEY constraint failed`
(`pytest.raises(aiosqlite.IntegrityError, match="FOREIGN KEY")`), then runs
`ensure_schema` and asserts the same rename succeeds and carries both the
revision and the rule rows. The test passes, so the pre-migration failure is
pinned inside the test itself.

**Verification**: `make test-unit` 5685 passed, 11 skipped (10 platform skips
plus one timing-conditional skip, within the CLAUDE.md 10-12 band);
`ruff check` and `ruff format --check` clean; `test_ui_guards.py`,
`test_nav_helper.py` and `test_settings_pages_static.py` pass. No static JS/CSS
was touched.

**Notes**
- Existing tests that build `AgentFactory` over an `AsyncMock` connection
  (`test_factory.py`, `test_mcp_tool_provider.py`, `test_search_tools.py`) now
  also patch `AgentRuleRepository`, since the factory reads rules through the
  connection.
- `TestSchemaV41::test_v41_upgrade_from_fresh_db` asserted
  `CURRENT_VERSION == 41`; it now asserts 42.

### rules-ui

**Status**: landed (not committed).

**Changes**
- New `areas/studio/rules-notes-tab.js` (`App.studio.renderRulesNotesTab`), a
  DOM-built, immediate-save Rules section behind a `makeSection` helper so
  Flight 2 can append Notes. Wired into `agent-editor.js` (tab second, after
  General; panel; `PANEL_IDS`), `studio.js` (five rules callbacks over
  `App.api.fetchJson`; `rules-and-notes` added to the tab whitelist) and
  `index.html` (script tag; `test_index_asset_cache_busting.py` count 85 -> 86).
- Drawer: `rulesGroup()` in `agent-drawer.js`, first in "What it can use";
  per-open raw `fetch` (404 = "No rules", other failure = "Couldn't load") with
  the same generation guards as the self-configuration fetch.
- CSS appended to `studio.css` (tab) and `chat.css` (drawer group); tokens only.
- Registry: 19 `rules-*`, `tab-rules-and-notes` and 4 `chat-drawer-rule*` ids
  added; `tab-self-configuration` now "last (sixth)".
- Tests: new `tests/browser/test_flow_agent_rules.py` (9 tests: deep link,
  empty state, section chrome, tab position/click/arrows, add + reload + focus,
  edit/save/cancel, toggle, move + focus, armed delete + focus, 501-char 422
  inline, create mode); 3 new drawer tests; updated `test_flow_agent_tabs.py`
  (count 6, ArrowRight reaches Rules and notes, Enter test presses twice) and
  `test_flow_agents_scale.py` (6 tabs, assertions unrelaxed).
- Docs: `the_one/agents.md` "Rules and notes tab (M27 F1 L2)"; one CLAUDE.md
  paragraph.

**AC3 measurement (1024x768, label "Rules and notes" kept)**: Chromium
`tablist scroll/client = 652/652`, last tab right edge 1005.0 vs main edge
1024.0; WebKit `652/652`, last tab right edge 994.1 vs 1024.0. One row, no
overflow, so the "Rules" fallback was not taken. No other tab or padding was
touched.

**Verification**: static guards (`test_ui_guards`, `test_token_definitions`,
`test_design_tokens_a11y`) pass; `agents` lane 165 passed; `chats` lane 171
passed; `contracts` lane (THE_ONE_REQUIRE_WEBKIT=1) 672 passed, 3 skipped;
`test_flow_agents_scale.py` passed in Chromium and WebKit with
THE_ONE_REQUIRE_WEBKIT=1; `make test-unit` 5683 passed after fixing the script
count pin (13 skipped under THE_ONE_TEST_NETNS=1, the documented extra root-only
skips); ruff check and format clean.

---

### Review fixes

Accessibility review items 1-4 and reviewer items A-B, in `rules-notes-tab.js`, `api.py`, `config.py`:

- Delete-arm announcement: a visually hidden `role=status` line (`rules-status`, registered) announces "Press Delete again to confirm deleting rule N." on arm.
- Failure focus: `mutate` records the pre-action control and restores focus on error (same control, else that row's Edit, else the Add textarea), including the inline Save failure path.
- Over limit: count reads "n / 500 \u2014 over the limit", textarea gets `aria-invalid="true"` and `aria-describedby` the count, Add and inline Save are disabled while over; the per-keystroke `aria-live` is removed and the status line announces only crossing into or out of over-limit.
- Rules routes now validate bodies through `_rules_body` using `_validation_detail` (no input echo); new test `test_type_validation_errors_never_echo_submitted_text`. `compose_system_prompt` import has a comment for why it is deferred.
- Replaced the 501-char click test with `test_over_limit_state_is_text_and_aria_and_blocks_add`, plus `test_failed_toggle_and_failed_save_restore_focus` (page.route 500 on PUT) and `test_delete_arm_is_announced`.
- Verified: static guards and changed unit files pass (323); agents lane 167 passed.
- Accepted, for HAT review: drawer clamp/title (a11y item 5), drawer loading announcements (6), target size (7).

### Review fixes (cycle 2)

- Blocking: a failed Add now restores focus to the Add textarea (`mutate` records focus that sits in the section outside the list; the typed text is kept). New browser test `test_failed_add_keeps_text_shows_error_and_refocuses_the_input` (POST routed to 500).
- Inline edit now announces the over-limit crossing through `rules-status`, as Add does.
- Removed the dead `'x'` fallback in the add-count id.
- Gates: static guards 261 passed; `test_flow_agent_rules.py` 12 passed.


## Decisions

### Autonomous judgement calls (for HAT review)

- **DD4:** rule limits of 500 characters per rule and 4,000 characters in
  total, with disabled rules counted.
- **DD5:** the prompt wording for the rules layer, with "the earlier rule wins"
  on conflict.
- **DD6:** the tab is labelled "Rules and notes" and sits second, after
  General. Its controls save immediately. Rules are reordered with Move up and
  Move down buttons.
- **DD7:** the chat agent panel's Rules group lists the enabled rules in order,
  plus "{n} off" and an "Edit rules" link.
- **DD9:** the behavior test uses the local Ollama provider and reads the stored
  session's system message as its composition read path.
- **DD6 (from the design review):**
  - Unsaved text in Add rule or an inline edit is not guarded by the leave
    prompt, as on the Self-configuration tab.
  - If "Rules and notes" overflows the tab strip at 1024 px, the label falls
    back to "Rules".
- **DD2 (from the design review):** if loading the rules fails at turn settle,
  the prompt is composed without rules and the turn completes.

- **rules-ui (autonomous judgement call):**
  - Rule rows show number, toggle, text (wraps, preserves line breaks), then
    Edit / Move up / Move down / Delete as small ghost buttons with text labels
    (not icons) for clarity; a disabled rule's text is `--fg-muted`, the row
    keeps its place.
  - A failed inline Save keeps the editor and its text open (other failures
    re-read the list); Add and the list controls are disabled while a request
    is in flight.
  - The drawer lists enabled rules unnumbered (two-line clamp), "{n} off" below
    them, "Edit rules" as a plain link.
  - AC3: "Rules and notes" fits at 1024 (652/652), so the label was kept.

### Accepted for HAT review (a11y review, items 5-7)

Drawer clamp/title, drawer loading announcements and target size: accepted as-is, for HAT review.

### Design review (2026-10-09)

- **Verdict:** approve with changes, after one cycle. Every point was applied
  to the spec.
- **What changed:**
  - the v42 self-reference now names the final table, with a guard on
    `PRAGMA foreign_key_list`;
  - DD2 states what happens on failure at settle, and how it gets its
    connection;
  - the existing tests that pin the bug and the tab tests are named;
  - `get_system_prompt` is deleted;
  - the drawer helper's limits and the 404 case are covered;
  - the behavior spec's preconditions are corrected.
- **Why no second cycle:** the changes add detail to existing decisions and do
  not restructure them.

---

## Deviations

- **rules-backend (autonomous judgement call):** the rules limits, errors and
  heading text live in `the_one/db/_rules.py`, not `the_one/agent/rules.py` as
  the leg suggested (an allowed module placement variation). Importing
  `the_one.agent.rules` from `repositories.py` creates an import cycle through
  `the_one/agent/__init__.py` (agent -> core -> mcp -> repositories).

---

## Anomalies

---

## Session Notes

### Flight Director Notes

- **2026-10-09:** loaded `.flightops/agent-crews/leg-execution.md` (valid
  structure). The flight was marked `in-flight`. Two autonomous legs, no HAT
  leg.
- **Leg 1 `rules-backend`:** tiered **high-risk** (a schema migration
  including a table rebuild, a shared-interface change to the async
  `apply_pending_revision` with existing callers, and a prompt-composition
  change on every agent build). It gets a Developer leg-design review before
  implementation.
- **Leg 1 design review:** approve with changes, after one cycle. Applied:
  - the database handle in the self-configuration tests (`isolated_db`, or
    patching `the_one.db.connection.get_connection`);
  - an AC20 harness that is concrete and realistic: the connector half through
    `test_connectors_inbound.py`'s real-factory test, the web half as the
    built agent plus a codec round trip, with end-to-end persistence left to
    the behavior test;
  - no separate fresh-install DDL;
  - a transaction shape that respects the non-re-entrant `write_transaction`;
  - migration tests on both the fresh-replay and the stopped-at-v41 paths;
  - 0-based dense positions;
  - AC18 widened.

  These are clarifications, not redesign, so there was no second cycle. The
  leg is `ready`.
- **Leg 2 `rules-ui`:** designed in parallel. Tiered **low-risk**: additive
  UI on established patterns, consuming leg 1's routes. It skips the per-leg
  design review, and the flight-end Reviewer plus an Accessibility Reviewer
  cover it.
- **Leg 1 landed** (Developer reported 5685 passed and 11 skipped, ruff clean). Leg 2 is set to `ready` and a Developer is spawned.
- **Leg 2 landed.** Phase 2d: spawned the Reviewer on **Sonnet** (the diff touches `the_one/self_configuration/pending.py`, the self-configuration surface, and the composition of every agent's prompt) and an Accessibility Reviewer (Sonnet) in parallel for the new tab and the drawer group.
- **Review cycles:**
  - **Cycle 1:** the Reviewer (Sonnet) and the Accessibility Reviewer
    (Sonnet) both confirmed with no blocking items. A fix pass took
    accessibility items 1-4 and Reviewer notes A-B.
  - **Cycle 2:** the re-review (Haiku: the fix delta is not
    security-sensitive) found one blocking issue: a failed Add lost focus.
    Its "config.py comment missing" item was a false alarm, because it
    checked `the_one/config.py` rather than `the_one/agent/config.py`.
  - **Cycle 3:** the re-review (Haiku) confirmed.
- **Carry-forward to Flight 2:** the cycle 3 residual is that a failed Add
  infers its origin from `document.activeElement`, and macOS Safari does not
  focus a clicked `<button>`. The desktop app runs on WebView2 (Windows) and
  WebKitGTK (Linux), not macOS Safari, so this is accepted for now. Flight 2
  edits `rules-notes-tab.js` for the Notes section, and should pass an
  explicit origin flag to `mutate` instead.
- **Gate:** `make gate` started detached (`setsid`) so the tool's background
  limit cannot cut it off. Settings: `THE_ONE_TEST_NETNS=1`,
  `THE_ONE_REQUIRE_WEBKIT=1`, `TEST_TIMEOUT=3600`.
- **Gate run 1:**
  - **Unit tier:** 5684 passed, 13 skipped (the netns count) in 171 s.
  - **Browser tier:** 7 of 8 lanes green. `shared` failed one test,
    `test_flow_dirty_confirm.py::test_arrow_keys_in_tablist_do_not_open_dialog`:
    it still assumes Knowledge follows General. That is the same tab-order
    contract change leg 2 made in `test_flow_agent_tabs.py`; a Developer is
    fixing it.
  - **Over budget (warning only):**

    | Lane | Wall | Budget |
    |---|---|---|
    | `routing` | 625 s | 600 s |
    | `settings` | 590 s | 540 s |
    | `agents` | 591 s | 510 s |

    `routing` and `settings` were not touched by this flight, so part of the
    overage is host load (netns mode, the WebKit requirement).
  - **Total:** browser wall 1107 s plus unit 171 s is about 21.3 min, over
    Mission 26's 20-minute target. `agents` grew by the new
    `test_flow_agent_rules.py` (12 tests).
  - **Recorded for the debrief:** the gate margin from Mission 26 is gone.

### Gate fix

`test_flow_dirty_confirm.py::test_arrow_keys_in_tablist_do_not_open_dialog` assumed ArrowRight from General lands on Knowledge; with "Rules and notes" now second it expects `agent-tab-rules-and-notes` (name and intent unchanged). A grep of `tests/browser/` found no other Knowledge-follows-General or five-tab assumptions (`test_flow_agent_tabs.py` was already updated). `test_flow_dirty_confirm.py` passes 21/21. The shared lane ran 247 passed and 2 failed, neither in flight-touched files: `test_confirm_contract.py::test_lapse_is_visually_distinct_and_clears_on_next_interaction` (a 50 ms `revertMs` race; it fails intermittently in isolation, 1 pass in 4 runs) and `test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url` (passed 6/6 twice in isolation, so a load flake). Both are pre-existing timing flakes unrelated to the Rules and notes tab.
- **Gate run 2 (the `shared` lane after the tab-order fix):**
  - **The fixed file:** `test_flow_dirty_confirm.py` passes, 21 of 21.
  - **Two lane runs** each showed **one different** failure in a file this
    flight did not touch:
    - `test_confirm_contract.py::test_lapse_is_visually_distinct_and_clears_on_next_interaction`
      (a 50 ms `revertMs` race), together with
      `test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url`,
      in the Developer's run while the host load average was about 20;
    - `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`, in the
      Flight Director's re-run.
  - **In isolation on a quiet host,** all three pass 3 of 3.
  - **Classified** as load-sensitive flakes, not regressions. Recorded as
    an anomaly for the debrief (candidate squawk: harden the `revertMs: 50`
    lapse test). Otherwise every lane is green.

## Anomalies (Flight Director)

### Load-sensitive flakes in the `shared` lane
- **Observed:** a different single `shared` test fails per run under load. The
  same tests pass in isolation.
- **Severity:** degraded (gate noise).
- **Resolution:** unresolved; carried to the debrief.
- **Behavior test:** `agent-rules-round-trip` passed **9/9**
  ([run log](../../../../tests/behavior/agent-rules-round-trip/runs/2026-10-09-22-40-11.md)).
  It ran live (`SendMessage`), on a scratch instance on port 8491 with
  `gpt-oss:20b`. Step 4 of the spec was reworded afterwards (the panel is open
  by default at 1280 px or wider).
- **Flight landed:**
  - Mission Known Issues 1 and 2 ticked, each with its pinning test.
  - Mission criterion "Rules shape new conversations" ticked.
  - The other contributing criteria wait for Flight 2's halves.
  - PR #257 marked ready.
  - `[COMPLETE:flight]`
