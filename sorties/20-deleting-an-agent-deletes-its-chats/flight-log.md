# Flight Log: Deleting an agent deletes its chats

**Flight**: [Deleting an agent deletes its chats](flight.md)

## Summary
Planned on 2026-11-25. The operator approved the design and marked it `ready` the same day, and asked for execution through to an open PR (no merge).

---

## Planning

### 2026-11-25: qualification and charter
- Qualified as a sortie. It has one outcome (agent delete cascades to chats, behind a stronger confirmation), one cluster of decisions (what agent deletion means), it fits one flight (two legs, no HAT), and it adds no new subsystem. No active mission covers it; Mission 37 (maintenance) is unrelated.
- The charter was agreed by the operator. The operator chose to purge orphaned chats on upgrade.
- Worktree `/home/cprch/projects/the-one-sortie-20`, branch `sortie/20-deleting-an-agent-deletes-its-chats` from `main` at `c3df3d73`. The main checkout carries Mission 37 Flight 1 work.

### 2026-11-25: design calls (operator)
- Dialog layout Option A (name plus chat count) was approved as the mockup (DD6).
- Connector bindings are cleared in the same transaction (DD3).
- The legacy deleted-agent UI is kept, with a squawk at landing (DD7).
- No HAT leg.
- A peer session (signed "ATC") relayed matching answers and asked that DD4 be flagged to Mission 37 as a DB migration (schema v57). It is recorded in DD4's coordination note.

### 2026-11-25: Architect design review, cycle 1 (approve with changes)
- **High, folded in:** modal actions always close the dialog on click (`modal.js:229-235`). DD5 now has the dialog own its Cancel and Delete in `footerEnd`, as the custom-recurrence dialog does, with no library change. DD6's `onActivate` is replaced by the existing `beforeArm` (one click, no arming).
- **Medium, folded in:**
  - DD2 now cancels in-flight work through the socket's cancel path and broadcasts `session_deleted` before evicting. `sessions_changed` alone leaves the Chats pane's conversation open, and `aclose` does not stop a turn.
  - `tests/test_db_migration.py` pins and replay tests were added to leg 1.
  - DD4's SQL now uses `NOT EXISTS` (NULL-safe) with explicit guards.
  - The "not findable in the database" claim led to DD9.
- **Low, folded in:**
  - the protocol is named correctly (`AgentConfigStore`), and `FilesystemConfigStore` is left alone;
  - the PTY release is by agent;
  - the danger-row description changes;
  - the success sequencing is pinned (close the dialog first, flash the response's count, the double-click guard);
  - `default_agent` has its key removed rather than set to `None`;
  - the routine-run race is added to DD7;
  - the lane `chats` HTTP-driven test moves are in leg 1.
- Sortie gate re-check (Architect): no second independent cluster; two legs and no HAT is the right size.

### 2026-11-25: disk scrub (operator)
- The operator chose to scrub on delete: `secure_delete` plus `wal_checkpoint(TRUNCATE)` (DD9).
- A peer session (ATC) asked that the checkpoint run after the v57 commit and outside any write transaction, and that a busy checkpoint be tolerated. Both are folded into DD4 and DD9.
- **For Mission 37:** this sortie touches `the_one/db/connection.py` (one `PRAGMA secure_delete=ON` line) and claims schema v57.

### Reconnaissance (code interrogation)
- Deleted-agent rendering kept by DD7:
  - `static/js/areas/chat/agent-drawer.js` (`:84-86`, `:237-241`, `:498-501`, `:589`)
  - `agent-kind.js` (`:9`, `:59`)
  - `chats-list.js` (`:24`, `:118`)
  - `chat-pane.js` (`:24`, `:55`, `:101-103`)
  - `static/js/jump-to.js` (`:31`, `:144`)
  - `instance-render.js:258`
  - `session-state.js:56`
  - `socket.js:30-38`
  - server side: `SESSION_STATUS_AGENT_DELETED` and its handling in `app.py` (`:1841`, `:2062-2070`, `:2369-2395`, `:3700-3702`, `:3791-3802`), and `the_one/routines/runner.py:282`.
- Unit tests asserting that chats survive agent deletion, which leg 1 rewrites:
  - `tests/test_db_repositories.py:2086-2105`
  - `tests/test_schema.py:360-409`
- Route and session-health tests to re-check in leg 1:
  - `tests/test_db_api.py:82`, `:3740`
  - `tests/test_self_configuration_external.py:324`, `:536`
  - `tests/test_mcp_pool_resolve.py:372`
  - `tests/test_session_lifecycle.py:222`, `:350`, `:438`
  - `tests/test_session_joined_payload.py:101-135`
  - `tests/test_ws_start_session.py:744`, `:777`
  - `tests/test_last_usage_round_trip.py:259`
  - `tests/test_routines_runner.py:99`, `:338`
  - `tests/test_retention.py`
  - `tests/test_db_migration.py`: exact `56` pins (`:5035`, `:5391`, `:5537`, `:5678`, `:5684`, `:5817`) and orphan-seeding replays (`:1959-1985`, `:7058`, `:7093`)
- Browser tests that delete agents, for leg 2:
  - lane `agents`: `test_flow_agent_crud.py`, `test_flow_agents_list.py:716`, `test_flow_agent_general_tab.py:149`, `test_flow_studio_purge_now_button.py`
  - lane `routing`: `test_nav_guard.py:653`, `test_store.py:498`
  - lane `chats`: `test_flow_chat_drawer.py:518-545`, `test_flow_chat_composer_library.py:37-50`, `test_flow_chat_list.py:147`, `:196`, `test_flow_chat_pane.py:201-207`, `test_flow_chat_session_state.py:235`
  - contracts (`test_ui_modal_contract.py`, `test_ui_confirm_contract.py`, `test_ui_editor_contract.py`): no longer leg 2 work, since DD5 makes no library change. They run in the closing gate only.

### 2026-11-25: Architect design review, cycle 2 (approve with changes)
- All cycle-1 findings were confirmed resolved, with no stale DD5 or DD6 text left.
- Folded in:
  - the request-path checkpoint runs in its own sequential `write_transaction` (the connection is shared);
  - the raw-bytes test runs through the production WAL connection, with a falsification step and `busy == 0`;
  - the shared cancel path reads the Session before the pop, sets the token first and waits briefly before `aclose`;
  - the v57 checkpoint sits right after the step's commit;
  - DD9 lists every connection and says why the dev scripts are left alone.
- **Accepted (Flight Director):** a connector turn already running for the deleted agent is not cancelled. It is bounded to that one turn, because DD3 clears the bindings; recorded in DD2.
- Sortie gate (Architect): DD9 is not a second cluster; two legs remain right. The review cycles are complete (2 of 2).

---

## Leg Progress

### Flight Director Notes

#### 2026-11-25: execution start
- The phase file `.flightops/agent-crews/leg-execution.md` loaded and is valid (Crew, Interaction Protocol, Prompts).
- The design commit `8decdebf` is on `sortie/20-deleting-an-agent-deletes-its-chats`, in the worktree `/home/cprch/projects/the-one-sortie-20`. The flight status went from `ready` to `in-flight`.
- The worktree venv was created with `uv sync --all-extras --frozen` (version 1.0.0); the main checkout's `.venv` was not touched.
- Two autonomous legs, no HAT. The operator asked for execution through to an open PR, with no merge.

#### 2026-11-25: leg 1 designed, tiered high-risk
- `legs/01-cascade-delete-and-orphan-purge.md` was written. **Risk tier: high**, so a Developer design review runs before implementation. Rationale: a schema migration that deletes the operator's data, a shared delete path with existing consumers, a lifecycle reversal (schema v5's "chats survive"), and a security-sensitive surface (a connection pragma on the shared connection).
- Reachability: the FK cascades from `agents` take routine runs and proposals; `chat_sessions` has no FK, so the store method must delete them itself; GleepGlorp's chats have no agents row, so the purge must exclude them.
- Interface: `AgentConfigStore.delete`'s return type changes. Its consumers are `api.py::delete_agent` and the test fake `tests/test_factory.py:47`. Response pins: every test asserts only `status_code == 200` on `DELETE /api/agents/{name}`; none pins the body (grepped `tests/`).

#### 2026-11-25: leg 1 design review, one cycle (approve with changes)
Developer design review (Sonnet). Folded in:
- **High:** AC11's pin list was incomplete. There are 18 exact `56` pins in `test_db_migration.py`, not 6; `:7419` is a v56-exists check and is not bumped. The v53 `_seed` tests (`:7058`, `:7093`) lose `s-Default` to the purge, and seeding a `Default` agent row is the expected fix.
- **Medium:**
  - AC14 uses the `isolated_db` fixture (this worktree has no per-worker data directories, because the xdist change is on Mission 37's unmerged branch). It uses an ASCII marker in a non-first message with an explicit title, and reads the bytes before the connection closes.
  - The shared cancel function's signature is `(session_id, session | None)`, and only the eviction helper waits, so the socket's cancel timing is unchanged.
  - The checkpoint helper consumes its cursor.
- **Low:**
  - the `secure_delete` assertion sits beside the template's `foreign_keys` assertion, and ad hoc test connections are exempt;
  - three more lane `chats` files that delete agents;
  - AC3 names the statement to make fail;
  - a 404 delete runs no checkpoint.
- No second cycle: every change is the reviewer's own correction or a precision edit, and the scope is unchanged. The leg is `ready`.

#### 2026-11-25: coordination with Mission 37 (peer note from ATC)
- Mission 37 Flight 1's PR #390 may merge first. It touches:
  - `tests/conftest.py` (per-worker `THE_ONE_DATA_DIR`; `make test-unit` becomes `-n 4`);
  - `tests/test_chat_history_purge.py`;
  - `the_one/agents.md`, `CLAUDE.md`, `Makefile`, `pyproject.toml`, `uv.lock`.

  It does not touch `api.py`, `db/schema.py` or `test_db_migration.py`.
- At the PR step: if #390 has merged, rebase on `main`, then re-run the unit tier and the lane `chats` before opening. Expect conflicts only in `the_one/agents.md`.
- AC14's use of `isolated_db` is safe under xdist.
- Mission 37 Flight 2 will split `api.py` into routers. This sortie's `delete_agent` change should merge before that split.
- **Update:** #390 merged to `main` as `9f5cbb1d`. It changed no `the_one/` code; it touched `CLAUDE.md`, `Makefile`, `pyproject.toml`, `uv.lock`, `tests/conftest.py` and some test files. **Decision:** no rebase mid-leg, because the Developer's work is uncommitted in this tree. After the flight commit: rebase on `main`, run `uv sync --all-extras --frozen` (pytest-xdist), then re-run the unit tier (now `-n 4`) and the touched lanes before opening the PR.

#### 2026-11-25: leg 2 drafted while leg 1 builds
- `legs/02-delete-agent-dialog.md` was drafted. The legs share no file: leg 2 touches only `static/js`, the lanes `agents` and `routing`, the guide and the registry. It is finalised after leg 1 lands, with its citations re-checked against the tree as it is then.
- **Tier: low** (no design review). Rationale: a single surface, an established precedent (the custom-recurrence dialog's own buttons, the provider delete's checkbox gate), no library change, and the design already went through two Architect cycles (DD5, DD6). The flight's Accessibility Reviewer covers the new surface.

#### 2026-11-25: leg 1 landed; environment corrected
- `[LAND:leg]` received for `cascade-delete-and-orphan-purge`; nothing is committed. Its report is in the section below.
- **The worktree venv was Python 3.13** (`uv sync` chose it; the main checkout's venv is 3.12.3). It was rebuilt with `uv sync --all-extras --frozen --python 3.12`. Both unit failures the Developer called pre-existing (`test_fake_platforms_seam.py::test_refuses[...]`, `test_mcp_negotiation_fallback.py::test_stdio_slow_legacy_server_past_the_window_records_the_fallback`) pass on 3.12, along with `tests/test_agent_delete_cascade.py` (54 passed). They were 3.13 artifacts, not defects.
- **The 25 extra skips** ("o200k_base is not cached") come from the tiktoken cache, which is absent in this environment. They are environmental and none is in this flight's scope.
- **The four lane `chats` failures** (`TypeError: a._sessionState is not a function`) ran at load 5.2, beside another session's lane `shared`, on the 3.13 venv. The hook is set when the chat area mounts (`static/js/areas/chat.js:70`); a `wait_for_function` that evaluates before that throws instead of retrying. Not attributed to leg 1. The closing gate (quiet host, 3.12) decides; if any persists there, it is triaged then.
- The Developer used `sed -i` once on the leg's status line (an artifact, not source); the hook did not block it. Noted, not repeated.
- Squawk candidates carried to landing: remove the legacy deleted-agent UI (DD7); the Purge route does not evict live sessions; the `_sessionState` race if the gate reproduces it.

#### 2026-11-25: leg 2 finalised
- Citations re-checked: leg 1 changed nothing under `static/`, so leg 2's citations hold. Status set to `ready` (tier low, no design review, per the earlier note).

#### 2026-11-25: leg 2 landed; flight review
- `[LAND:leg]` received for `delete-agent-dialog`. Both autonomous legs are landed and uncommitted.
- The lane readings (`agents` 2034 s, `routing` 1705 s) ran at load 8 to 25, beside another session's browser run. They are not budget readings. The closing gate after the rebase provides those.
- The Developer attempted one `sed -i` on a source file; the permission classifier denied it and it was redone with Edit. No source was written by shell.
- Reviewer: **Sonnet**. The diff touches a security-sensitive surface: deletion of user data, a pragma on the shared connection, and the threat model text. The Accessibility Reviewer (Sonnet) runs in parallel, because leg 2 adds a user-facing dialog.

#### 2026-11-25: reviews confirmed; commit and rebase
- **Code Reviewer (Sonnet): `[HANDOFF:confirmed]`, no blocking issues.** It ran the static guards and the cascade, migration and schema tests (615 passed). Two non-blocking observations were accepted:
  - the lazy imports inside `delete_agent` avoid a circular import;
  - the checkpoint runs before `cascade_delete` and eviction, which is harmless.
- **Accessibility Reviewer (Sonnet): `[HANDOFF:confirmed]`, no blocking issues.** The Flight Director chose to fix three non-blocking findings anyway:
  - focus during the request and after a failure;
  - a "Deleting…" status;
  - the opener guarded until an escaped request settles.

  One fix pass, with 6 of 6 assertions falsified. The re-review confirmed it.
- **Accepted:**
  - `aria-busy` on the dialog may defer the status announcement in some screen readers. The text is set first, so it is probably queued; recorded as a squawk candidate if a screen-reader check shows it silent.
  - The wordy `aria-describedby`.
- **Deviation from the fix prompt:** the fix pass ran only the dialog file and the guards, not the full unit tier and lanes. The closing gate runs both right after the commit and the rebase onto `main` (`9f5cbb1d`), on the final tree.
- Both legs `completed`. Next: the commit (Developer), the rebase, `uv sync`, then the closing gate.

### Leg 1: cascade-delete-and-orphan-purge

**Landed (Developer), 2026-11-25. Not committed.**

**Implemented**
- `SQLiteAgentStore.delete` is one transaction (chat ids, GleepGlorp proposals and fills, chats, connector clearing, agents row) returning the chat ids. The `AgentConfigStore` protocol and the `tests/test_factory.py` fake return `list[str]`.
- `app.py`: `_cancel_session_tasks(session_id, session | None)` (the socket's `cancel` action calls it, no wait) and `_evict_deleted_sessions(ids)` (cancel, bounded `asyncio.wait` of 5 s, `session_deleted` broadcast, evict). `_run_purge_sweep_and_evict` uses the helper (log line and return value unchanged).
- Route: `chats_deleted`, `checkpoint_wal` (new, in `the_one/db/connection.py`), PTY release, one `notify_sessions_changed()`.
- Schema v57 (`CURRENT_VERSION` 57) with the `NOT EXISTS` predicate and a post-commit `wal_checkpoint(TRUNCATE)`. `PRAGMA secure_delete=ON` in `connection.py` and the template's three builders.
- Documents: `the_one/agents.md` (new section "Deleting an agent (sortie 20)", the drawer deleted-state note, the `sessions` paragraph), `SECURITY-MODEL.md` (DD8's three statements and the out-of-scope remnants).
- No change under `static/`.

**AC11 replay tests, per-test decision**
- `test_db_migration.py::TestSchemaV16::test_v16_legacy_v15_row_decodes_with_null_external_key_columns` (`seeded-session` for `test-agent`): subject is the v16 columns, so an `agents` row for `test-agent` is seeded.
- `TestSchemaV53._seed` (`s-Default`; feeds `test_v52_database_loses_the_default_agent_and_its_data` and `test_a_live_gleepglorp_agents_chats_survive`): subject is what v53 keeps, so a `Default` agents row is seeded in `_seed`. `s-research` and `s-gleep` already had live agent rows.
- `:2973` (`agent-1`) is seeded already; `tests/test_name_repair.py:228` saves the `Default` agent first. Neither needed a change.
- The 18 `56` pins moved to 57; `:7419` (`WHERE version = 56` count) is untouched and still passes; the `TestSchemaV56` rewind comment was reworded.

**AC15/AC16 test moves**
- `test_db_repositories.py::test_agent_delete_does_not_cascade_to_sessions` renamed `test_agent_delete_cascades_to_sessions` and rewritten. `tests/test_schema.py::test_v5_agent_delete_does_not_cascade_to_sessions` is a raw-SQL schema test (no FK since v5): assertion kept, docstring says the cascade is the store's.
- Browser: `test_flow_chat_composer_library.py` (two tests) and `test_flow_chat_picker.py` (`Ghost`) now use a never-existed agent name. The drawer, list and session-state files already used never-created names (the flight's reconnaissance line numbers there were not HTTP deletes). The remaining HTTP deletes (`test_flow_chat_pane.py:373`, `test_flow_chat_start_flow.py:367,487,502`) delete an agent with no chats (a pending chat), so they behave as before; `test_flow_chat_proposals.py:772` deletes a proposal's target agent whose chat is GleepGlorp's, so no chat is deleted. They were left in place.

**Falsification** (edit out, test fails, edit back)
1. drop the `chat_sessions` delete: yes (AC2 test, the route test, the raw-bytes test and the repository test failed).
2. connector update outside the transaction: yes (the atomicity test failed).
3. `NOT IN (SELECT name FROM agents)`: yes (both full V57 tests failed).
4. remove the `'GleepGlorp'` exclusion: yes.
5. remove `secure_delete` from `connection.py`: yes, at step 5 (the marker stays on disk after delete plus checkpoint). The first version of the raw-bytes test PASSED without the pragma, so it was vacuous: a page emptied by the delete is reset by SQLite regardless. The test now keeps a surviving neighbour chat (rows `keep-1` and `keep-2` around the deleted one) so the page stays alive; with that, the pragma is what scrubs it. `busy == 0` held either way. Also `test_the_app_connection_has_secure_delete_on` failed without the pragma.
6. skip the broadcast: yes (the eviction test failed).

**Results (host-native, `THE_ONE_TEST_NETNS=1`)**
- Unit tier, serial (`run-tests.sh tests/ -m 'not browser and not live and not pixel and not requires_bwrap'`), load 1.4 at start, no other test process: 12325 passed, 2 failed, 40 skipped in 580 s. The two failures also fail in isolation and on a pristine `git archive HEAD` copy (so not caused by this leg): `tests/test_fake_platforms_seam.py::test_refuses[http://[::ffff:127.0.0.1]:8490]` and `tests/test_mcp_negotiation_fallback.py::test_stdio_slow_legacy_server_past_the_window_records_the_fallback`. The worktree venv is Python 3.13 (the project targets 3.12), which is the likely cause of the first. Skip count is 40, not 15: 25 are `o200k_base is not cached` (no network cache of that tokenizer in this worktree).
- A doc/guide/DB subset re-run after the document edits: 1347 passed (load 3.6).
- Lane `chats` (`TEST_TIMEOUT=3600`): 174 passed, 4 failed in 794 s. NOT alone on the host: another session's lane `shared` was running in `/home/cprch/projects/the-one` (load 5.2). The 4 failures: `test_flow_chat_drawer.py::test_deleted_and_unknown_agents_show_no_settings_link`, `test_flow_chat_pane.py::test_header_while_joining_reads_the_store_and_no_empty_state_flashes`, `test_flow_chat_start_flow.py::test_a_late_cold_load_join_cannot_take_over_a_pending_chat` and `::test_new_chat_route_hydrates_and_heals`. All are `TypeError: a._sessionState is not a function` raised by the test's own `wait_for_function` (no guard that the area has mounted). They fail 4 of 4 in isolation (load 5.0), and the first two also fail on the pristine HEAD copy. None touches agent deletion or a file this leg changed. Needs a squawk (not fixed here).
- `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`: clean.

**Notes for the Flight Director**
- Squawk candidates: (a) the `_sessionState` race above; (b) the Purge route `DELETE /agents/{name}/chat/sessions` does not stop or evict live sessions (out of scope, as the leg says); (c) the DD7 squawk to remove the legacy deleted-agent UI is still to be logged at landing.
- Mission 37 coordination: leg 1 changes `the_one/db/connection.py` (one pragma line plus the new `checkpoint_wal` helper) and claims schema v57.
- Housekeeping (leg 1): the leg status is `landed`. I used `sed -i` once on the leg's status line (an artifact under `sorties/`, not source) before reading the hook rule; no source or test file was written by shell.

### Leg 2: delete-agent-dialog

**Landed (Developer), 2026-11-25. Not committed.**

**Implemented**
- New `static/js/areas/studio/agent-delete-dialog.js` (`App.studio.agentDeleteDialog.open/flashText`), loaded in `index.html`; three CSS rules in `studio.css`. Modal owns its Cancel and Delete buttons (`footerEnd`); module-level `busy` flag gives one dialog per click burst.
- `general-tab.js`: Delete uses `beforeArm` (calls `callbacks.onDelete(button)`, never `proceed`), new description (AC8). `agent-editor-controller.js`: `handleDeleteEditor` opens the dialog; `afterDelete` does invalidate sessions and agents, `loadAll`, navigation, DD8 focus and the flash from `chats_deleted`.
- Re-grep of `delete-agent-btn`: only the files the leg listed (plus old run logs, left alone). Nothing new.
- Tests: new `tests/browser/test_flow_agents_delete_dialog.py` (8 tests, lane `agents` via the `test_flow_agents_*` glob) and helper `tests/browser/_agent_delete.py`; moved `test_flow_agent_crud.py` (lapse test renamed in place to `test_delete_agent_cancel_leaves_the_agent_and_the_button_unarmed`), `test_flow_agents_list.py`, `test_flow_agent_general_tab.py`, `test_flow_studio_purge_now_button.py` (AC8 text), `test_store.py` (also asserts `sessions` invalidated), `test_nav_guard.py`.
- Documents: `docs/ui-testid-registry.md`, `the_one/gleepglorp/guide/agents.md`, `the_one/agents.md` (General tab danger zone), `tests/behavior/studio-agent-crud.md` (not run). No inventory row was needed (`test_ui_control_inventory.py` passes).

**Falsification**: (1) checkbox enabling dropped: yes, gate test failed. (2) `proceed()` in `beforeArm`: yes, "not armed" assertion failed. (3) flash a pre-read count: yes, the count-changes-after-open test failed. All restored by edit.

**Results (host-native, `THE_ONE_TEST_NETNS=1`)**
- New file alone: 8 passed (load 13).
- Lane `agents`: 194 passed, 2034 s. Lane `routing`: 193 passed, 1705 s. Not on a quiet host: another session's browser run was in progress, load 22-25 during `agents`, 8-13 during `routing`.
- Guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`, `test_ui_emitted_classes`, `test_ui_control_inventory`, `test_gleepglorp_guide`, `test_run_tests_lanes`, `test_nav_helper`): 610 passed. `ruff check` and `ruff format` on `the_one/ tests/ scripts/ evals/`: clean.

**Notes**: a first draft of a second-click test used a forced pointer click, which stole the dialog's focus (backdrop mousedown); it now uses `dispatch_event`. I also attempted one `sed -i` on `agent-editor-callbacks.js`; it was denied and redone with Edit.

### Review fixes

#### 2026-11-25: accessibility review fixes (agent-delete-dialog.js)

- WCAG 2.4.3: starting the request moves focus to Cancel (Delete and the checkbox just disabled); a failed request returns focus to Delete (still ticked, retry possible).
- WCAG 4.1.3: a `visually-hidden` `role="status"` span in the dialog body reads "Deleting…" while running and is cleared on failure; the dialog carries `aria-busy="true"` while running.
- WCAG 2.4.3 minor: `busy` is no longer released by the modal's `onClose` while the request is in flight; it is released when the request settles (success, or failure after Escape), so the opener opens nothing in that window.
- Tests (`test_flow_agents_delete_dialog.py`, now 10): `test_running_moves_focus_to_cancel_announces_and_failure_focuses_delete` (new), `test_opener_is_free_again_after_an_escaped_request_fails` (new), and an opener-click-after-Escape assertion added to the Escape-mid-request test.
- Falsified (fix edited out, test failed, restored): focus to Cancel yes; focus to Delete on failure yes; status text yes; `aria-busy` yes; opener guard held in flight yes; guard released after settle yes.
- `the_one/agents.md` dialog paragraph updated.

### Gate triage after rebase

**Rebase**: onto origin/main 7518aefa (#391), no conflicts (including `the_one/agents.md`); HEAD was 61da5b47 before this commit. `.venv` is Python 3.12.3.

**Cause of the gate noise**: the killed gate ran on the pre-rebase tree (several chats failures were `a._sessionState is not a function`, the predicates #391 fixed), under host load 16-26 with other sessions running browser lanes. A first chats-lane run hit the 1200 s TEST_TIMEOUT; reruns used `TEST_TIMEOUT=3600`.

**Fixed (ours)**: three tests in `test_flow_chat_transcript_library.py` deleted an agent over HTTP to reach the deleted-agent state (`test_a_deleted_agents_chat_makes_no_context_window_request`, `test_the_step_limit_notice_for_a_deleted_agent_is_plain_text`, `test_a_blocked_chat_renders_no_continue_button`). They now seed a chat for a never-existed agent name (`seed_session`, a user message for the two that need one) and keep their assertions. The step-limit test also asserts the no-button sentence (the chat is blocked) and waits for the disabled input first. File run alone: 30 passed. Falsification: not applicable (test moves; the old form could not pass after the cascade).

**Multi-line grep for agent deletion over HTTP** (tests/, tests/browser, tests/behavior; `.delete(` with `api/agents`, DELETE methods, wrapper helpers):
- `test_flow_chat_transcript_library.py` (3 sites): moved.
- `test_flow_chat_pane.py:374`, `test_flow_chat_start_flow.py:368,488,503`: not affected; they delete from a pending (`~new`) chat before any session exists and assert no sessions.
- `test_flow_agent_crud.py`, `_agent_delete.py`, `test_flow_agents_delete_dialog.py`: this sortie's UI delete tests.
- `test_flow_chat_composer_library.py`, `test_flow_chat_picker.py` and others: already moved in leg 1.
- Unit tier (`test_ws_start_session`, `test_self_configuration_api/_external`, `test_routines_self_config_api`, `test_agent_rules_api`, `test_db_api`, `test_mcp_pool_resolve`, `test_routines_service`): not affected; the full unit tier passes (below).
- Behavior specs (`workbench-navigation`, `list-and-detail`, `start-a-chat`, `studio-agent-crud`): teardown deletes only; `start-a-chat` deletes sessions first.

**Failures, classified** (isolated runs and a pristine origin/main worktree at 7518aefa, since removed):
- PRE-EXISTING on pristine main, fail identically there: `test_flow_new_chat.py` (4: `test_welcome_no_setup_shows_both_links`, `_provider_only_shows_studio_link`, `_with_agent_shows_the_empty_state`, `test_empty_state_new_chat_opens_the_picker_and_starts_a_chat`; empty `<main>`, `chat-welcome` never appears); `test_flow_chat_composer_library.py::test_the_empty_states_text_column_is_centred`; `test_flow_chat_live_updates.py` (2: `test_joining_mid_turn_ends_the_running_work_line_after_the_turn`, `test_a_message_sent_during_a_mid_turn_join_is_held_then_delivered`); `test_flow_provider_setup.py::test_first_start_provider_setup_flow`; `test_flow_provider_library.py::test_bare_providers_section_is_an_alias_for_the_library_root`; `test_flow_admin_navigation.py` (3); `test_flow_settings_window_chrome_signal.py` (3); `test_flow_context_overlay_thresholds.py::test_overlay_custom_warn_threshold_moves_transition`. Main run: 12 failed, 5 passed for that set; new_chat file alone 4 failed, 8 passed on both trees. Cause not investigated (not ours; likely host/environment).
- LOAD FLAKES (pass in isolation on our tree): `test_flow_gleepglorp_fill_provider.py` (gate: `test_cancel_restores...` KeyError: 1; lane: `test_an_options_only_fill...`; file alone 22 passed with the openrouter file), `test_flow_studio_openrouter_picker.py::test_rapid_provider_switch_uses_final_selection`, `tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client` (unit tier under xdist; passes alone; MCP code is not in our diff).
- Ours: none remaining.

**Verification on the final tree** (`TEST_TIMEOUT=3600`, `THE_ONE_TEST_NETNS=1`, `THE_ONE_REQUIRE_WEBKIT=1`, one lane at a time; load 5-23, other sessions busy):
- chats (before the final step-limit edit): 171 passed, 7 failed, all pre-existing (above), 1491 s.
- chats-transcript: 151 passed, 1 failed (overlay threshold, pre-existing), 1548 s; the edited file alone passes.
- settings: 120 passed, 6 failed (admin_navigation x3, chrome_signal x3, all pre-existing), 1275 s.
- gleepglorp-kinds: 101 passed, 1 failed (load flake), 1123 s.
- providers: 142 passed, 2 failed (pre-existing), 1123 s.
- agents: 195 passed, 1 failed (openrouter picker, load flake), 1928 s.
- routing: 193 passed, 1830 s.
- `make test-unit`: 12346 passed, 40 skipped, 1 failed (mcp_pool flake, passes alone), 159 s, load about 5.
- `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`: clean.
