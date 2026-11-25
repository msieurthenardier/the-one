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

_No legs executed yet._
