# Sortie: Deleting an agent deletes its chats

**Status**: in-flight

## Charter

### Outcome
When you delete an agent, all of its chat history goes with it, and you confirm that knowingly in a dialog first.

### Why Now
Chats outlive their agent indefinitely: a "deleted" agent's conversations, which may hold sensitive content, stay readable in Chats and in the database. The operator rates this a security risk. It reverses the schema v5 decision (`the_one/db/schema.py`, the `if version < 5` block) that chats survive agent deletion so the session-health classifier can show `agent_deleted`.

### Success Criteria
- [ ] Deleting an agent removes every chat session and message that belongs to it, along with its routine run history. Afterwards none of them can be found in Chats, through the API, or in the database.
- [ ] Deleting an agent opens a confirmation dialog in place of the two-step button. Its Delete button stays disabled until the box "I understand this will delete all of this agent's chat history" is checked. Cancel or Escape leaves the agent and its chats untouched.
- [ ] On upgrade, chats left behind by agents deleted earlier are purged.
- [ ] The agent and its chats are deleted together or not at all; a failure never leaves chats without their agent.

### Constraints
- Rename keeps carrying chats with the agent, as it does today.
- GleepGlorp's own chats are not touched (`agent_name = 'GleepGlorp'` has no `agents` row).
- Delete flows for providers, MCP servers and other entities stay as they are. The agent's **Purge** (clear history) button keeps its two-step confirm.
- The existing cascades (self-configuration surface, MCP credential eviction, live MCP connections) are kept.
- An open chat with the deleted agent ends cleanly instead of failing.
- Work happens in the worktree `/home/cprch/projects/the-one-sortie-20` on `sortie/20-deleting-an-agent-deletes-its-chats`, branched from `main` at `c3df3d73`, so it does not touch `flight/01-unit-tier-runtime-iii` (Mission 37).

---

## Pre-Flight

### Objective
Make agent deletion a full cascade. One store transaction removes the agent row (which already cascades its rules, notes, routines and their runs, routine proposals, revisions and tool cache through foreign keys), every chat session keyed to it, the GleepGlorp proposals and fills that belong to those chats, and the connector bindings that name it. The route then evicts the deleted sessions from memory and pushes `sessions_changed`. A data-only migration (v57) purges chats already orphaned by earlier deletions. In the browser, the General tab's Delete opens a modal: it names the agent and its chat count and needs an acknowledgement checkbox before Delete is enabled.

### Open Questions
- [x] What happens to chats orphaned before this lands? → purged on upgrade (DD4; operator's choice)
- [x] Dialog layout? → Option A, name plus chat count (DD6; operator's choice, mockup below)
- [x] Connector bindings that name the deleted agent? → cleared in the same transaction (DD3; operator's choice)
- [x] The legacy deleted-agent UI ("Unknown agent", the `agent_deleted` banner)? → kept as a safety net, documented as reached only by a race; a squawk to remove it is logged at landing (DD7; operator's choice)
- [x] HAT leg? → no (operator's choice); tests and the flight code review are the acceptance

### Design Decisions

**DD1. One store transaction deletes the agent and everything keyed to it**: `SQLiteAgentStore.delete(name)` (`the_one/db/repositories.py:447`) becomes the single cascade. Inside one `write_transaction` it:
1. checks the agent exists (`KeyError` as today),
2. collects the ids of `chat_sessions WHERE agent_name = ?`,
3. deletes `gleepglorp_proposals` and `gleepglorp_fills` whose `session_id` is one of them (the statements `ChatSessionRepository.delete_all_for_agent` already runs, `repositories.py:3510-3539`),
4. deletes those `chat_sessions` rows,
5. clears the connector bindings (DD3), and
6. deletes the `agents` row, whose `ON DELETE CASCADE` children go with it (rules, notes, routines, their runs through `routine_id`, routine proposals, revisions, MCP tool cache).

It returns the deleted session ids. The `AgentConfigStore` protocol (`the_one/agent/store.py:13`, `delete` at `:22`) and the test fake (`tests/test_factory.py:47`) change their return type to match. The legacy synchronous `FilesystemConfigStore.delete` (`store.py:56`) does not satisfy the protocol (its own docstring) and is left alone.
- Rationale: `write_transaction` is one module-level lock that is not re-entrant (`the_one/db/_write_lock.py:52-68`, raises `RuntimeError`), so the existing per-repo methods cannot be composed into one transaction; a single method is the only atomic shape. `SQLiteAgentStore.rename` (`repositories.py:458-560`) is the precedent: agents, chats, GleepGlorp rows and connectors in one transaction.
- Trade-off: the agent store now writes chat and connector tables. Rename already does.
- No attachment files: chat images live inside the messages JSON; nothing per-chat is stored on disk (verified during code interrogation; PTY scratch under `data_dir/boxes/` is wiped at startup, `the_one/tools/execution.py:575-601`).
- Not cleaned (provenance text only, no reader breaks): `gleepglorp_notes.origin_session_id`, and GleepGlorp proposals and fills **in GleepGlorp's own chats** whose `agent_name` is the deleted agent. Those already resolve as "target gone".

**DD2. The route stops, tells and evicts each deleted chat, then reports the count**: `delete_agent` (`the_one/interfaces/web/api.py:1253-1266`) calls the store, then the existing `self_configuration_manage.cascade_delete` and `_evict_agent_connections`, unchanged. It then hands the returned ids to one shared eviction helper in `app.py` and calls `notify_sessions_changed()` once when any chat was deleted. The response becomes `{"status": "ok", "chats_deleted": N}`.

For each id, the helper does three things in order:
1. **Cancel in-flight work** for that id through the existing operator-cancel path (`app.py:4066-4079`). The path is factored so the socket's `cancel` action and the helper share it:
   - read the `Session` with `_sessions.get(sid)` before any pop;
   - set the cancel token in `_cancel_tokens[sid]`;
   - call `t.cancel()` on each not-done task in `_session_inflight[sid]`;
   - call `_notify_cancelled_once(session)` (`app.py:1021`) when nothing had started;
   - wait briefly for the batch to unwind (`asyncio.wait(batch, timeout=…)`, like the runner's `_CANCEL_WAIT_SECONDS`) before step 3's `aclose`.

   Routine-run turns are covered because `_spawn_routine_turn` registers them through `_register_turn_task` (`app.py:1464-1467`).
2. **Tell the subscribers**: `broadcast_to_session(sid, {"type": "session_deleted", "session_id": sid})` (`the_one/sessions/_broadcast.py:87`). The client already resets cleanly on `session_deleted` (`static/js/areas/chat/socket.js:417-439`), in the Chats pane as well as the drawer.
3. **Evict**: the existing eviction half of `_run_purge_sweep_and_evict` (`app.py:1727-1760`: pop under `_sessions_lock`, then `session_locks.pop` and `agent.aclose()` outside it), factored out. The purge sweep calls the same helper, so it gains steps 1 and 2.

The route also releases the agent's PTY tool sessions: `list_for_agent(name)` and `close()` on each (`the_one/tools/_session_registry.py:85-108`; the key is `(agent_name, pty-<uuid>)`, not a chat id). Otherwise an agent re-created under the same name would share them until the TTL reaper ran.
- Rationale: `sessions_changed` alone does not end an open chat. `sessionFlow.dropGoneBound` acts only in the drawer profile (`static/js/areas/chat/session-flow.js:443-444`; the Chats pane keeps its conversation, `socket.js:148-150`), and the server's socket loop keeps its local `session` (`app.py:4082+`). `agent.aclose()` only closes the LLM client (`the_one/agent/core.py:733`), and is a no-op for some providers (`the_one/llm/base.py:709`). Without the cancel, a turn, its tools or a routine run would keep running for a deleted agent.
- **Accepted gap: a connector turn already running is not cancelled.** `dispatch_inbound` runs its turn inline under `track_turn` with its own `factory.create` agent (`the_one/connectors/inbound.py:420-431`), outside `_session_inflight` and `_sessions`. That one turn finishes, tools included, and delivers its reply; its save is dropped because the row is gone. It is bounded to that turn: DD3 clears the bindings in the same transaction, so no further inbound message reaches the agent. `the_one/agents.md` records this.
- Already tolerated after the row is gone: a late save (`app.py:2246-2250`, `:2291-2296`; `the_one/routines/runner.py:119-131`, `:355-375`); a rejoin returns `not_found` and `join_failed` (`app.py:1993-2001`, `:3803-3815`); a running routine run's row cascades away and `_finish_row` swallows the miss (`runner.py:178-182`).

**DD3. Connector bindings naming the agent are cleared in the same transaction**: inside DD1's transaction, a `connectors.config.default_agent` equal to the name has its **key removed (never set to `None`**: `the_one/db/models.py:235-236` rejects a non-string, and v53 removes the key too). Any `channel_map` entry whose value is the name is dropped. This mirrors the loop `rename` uses to rewrite them (`repositories.py:532-553`). A channel without a `channel_map` entry falls back to `default_agent` (`the_one/connectors/inbound.py:321-328`). With no `default_agent`, an inbound message is dropped with a log line (`inbound.py:401-404`).
- Rationale: today `dispatch_inbound` calls `resolve_session` before `factory.create` (`inbound.py:420-431`), so a binding to a deleted agent re-creates an orphan chat on every inbound message.
- Trade-off: a connector bound only to that agent goes quiet until the operator picks a new agent. That is the honest state.

**DD4. Migration v57 purges chats orphaned before this lands (a data-only DB migration)**: a new `if version < 57:` step in `the_one/db/schema.py`, bumping `CURRENT_VERSION` from 56 to 57. An orphan is a chat where `agent_name IS NULL OR (agent_name <> 'GleepGlorp' AND NOT EXISTS (SELECT 1 FROM agents WHERE agents.name = chat_sessions.agent_name))`.
- It uses `NOT EXISTS`, never `NOT IN`. `agents.name` is a `TEXT PRIMARY KEY` without `NOT NULL` (`schema.py:54`), so one NULL name would make `NOT IN` delete nothing, silently. `NOT EXISTS` is the v53 style (`schema.py:3499-3501`).
- Guards: the chat delete runs only when both `chat_sessions` and `agents` exist. The `gleepglorp_proposals` and `gleepglorp_fills` deletes (orphan chats' rows, by `session_id`, run first) only run when their own table also exists.
- DD9's `wal_checkpoint(TRUNCATE)` goes inside the `if version < 57` block, immediately after its `await conn.commit()`, so it runs only on upgrade and never inside an open transaction. A PRAGMA is not an import, so the frozen-migration rule (`tests/test_schema_frozen_imports.py`) holds. On the template build's non-WAL connection it is a harmless no-op.

The literal `'GleepGlorp'` is hard-coded, because `tests/test_schema_frozen_imports.py` forbids live imports in `schema.py`. v53 (`schema.py:3445-3536`) is the precedent for a data-only delete of chat rows that excludes GleepGlorp.
- Rationale: the retention sweep never reaches orphans (`the_one/retention.py:48-97` enumerates only agents rows and GleepGlorp), so without this they stay forever.
- Irreversible on the operator's real database at first start after upgrade. The release notes must say so.
- **Coordination:** this is a schema version bump. Mission 37 (Flight 1 test runtime, Flight 2 backend boundaries) must not also claim v57. Re-check at merge time. The exact pin `tests/test_gleepglorp_fill_store.py:58` (`CURRENT_VERSION == 56`) moves to 57. So do the exact `56` pins in `tests/test_db_migration.py` (`:5035`, `:5391`, `:5537`, `:5678`, `:5684`, `:5817`). Full-replay tests there that seed chats for an agent with no `agents` row and expect them to survive will see them purged: `seeded-session` for `test-agent` (`:1959-1985`) and `s-Default` (`:7058`, `:7093`). Each is either given an agents row or rewritten to assert the purge, whichever its subject needs.

**DD5. No control-library change: the dialog owns its buttons**: the dialog is an `App.ui.modal` with a node `body` and **no `actions`**. Its Cancel and Delete are `App.ui.button`s it builds and passes as `footerEnd`, with `initialFocus: cancelBtn`. It calls `modal.close()` itself, only on Cancel or on success. The precedent is the custom-recurrence dialog (`static/js/areas/studio/routines-custom-recurrence.js:162-200`).
- Rationale: a modal action's click always calls `finish(s, a.value)`, which closes the dialog (`static/js/ui/modal.js:229-235`). So modal actions cannot keep the dialog open during the request or after a failure. Owning the buttons gives `btn.disabled` without reaching into library DOM.
- Escape and the native `cancel` event still close the dialog at any time (`modal.js:277-282`, `:300-303`). Escape while the request runs closes it, and the request completes anyway. Its result (the post-delete navigation and flash, or the error flash) lands in the page region, because no modal is open any more.
- Rejected: `disabled` actions on `App.ui.modal` (would not prevent the close on click), and an "acknowledge" option on `App.confirmDialog` (it is the leave guard's adapter).

**DD6. The agent-delete dialog (layout Option A, operator-approved)**: a composition (like the agent picker, not a new factory) in a new `static/js/areas/studio/agent-delete-dialog.js`. The General tab's danger-zone Delete (`static/js/areas/studio/general-tab.js:226-257`) opens it instead of arming.

The Delete action passes `beforeArm: openDialog` and never calls `proceed()`. `App.ui.dangerZone` runs `beforeArm` on the first click and arms only when `proceed()` is called (`static/js/ui/editor.js:417-425`; its contract says `beforeArm` "decides whether to call proceed()"). One click therefore opens the dialog with no arming, and the library is unchanged. The Purge action and every other danger zone keep the two-step. The Delete row's description (`general-tab.js:247-248`, "Deletes the agent with its routines, rules, notes and settings") adds its chats.

```
┌────────────────────────────────────────────┐
│ Delete "Research Bot"?                     │
│                                            │
│ This deletes the agent and its 14 chats,   │
│ with every message in them. This can't be  │
│ undone.                                    │
│                                            │
│ [ ] I understand this will delete all of   │
│     this agent's chat history              │
│                                            │
│                 [ Cancel ]  [ Delete ]     │
└────────────────────────────────────────────┘
```
- Title: `Delete "{name}"?`.
- Message, with the count from a fresh `App.store.get('sessions', {force: true})` filtered by `agent_name` (the list route returns every chat, interactive and connector, `api.py:5099-5103`):
  - N > 1: "This deletes the agent and its N chats, with every message in them. This can't be undone."
  - 1 chat: "its 1 chat".
  - 0 chats: "This deletes the agent. It has no chats. This can't be undone."
  - The read fails: "This deletes the agent and all of its chats, with every message in them. This can't be undone."
- Checkbox `App.ui.checkbox` (`static/js/ui/choice.js:77`), label "I understand this will delete all of this agent's chat history", required even at 0 chats. Its precedent is the provider delete's `delete-force-checkbox` (`static/js/areas/studio/provider-delete.js:73-95`).
- Delete is the danger variant, disabled until the box is ticked, and disabled again if it is unticked.
- Focus and dismissal: Cancel has focus on open, Escape cancels, and a backdrop click does nothing (the modal's existing rules).
- Opening: a second click on the opener while the count is being read opens nothing more (one dialog at a time). `App.store.get` exists with that signature (`static/js/store.js:91-96`) and notifies the store's subscribers, which is harmless here.
- On Delete: Delete and the checkbox are disabled while the request runs (no double submit).
  - Success, in this order:
    1. close the dialog first, so the modal's restore-to-opener (`modal.js:132-142`) runs while the opener still exists and cannot land on `#main-content` later;
    2. `App.store.invalidate('sessions')` and `'agents'`;
    3. the existing `loadAll`, the post-delete navigation and focus (`agent-editor-controller.js:339-373`, M25 DD8: Agents root, focus to the nearest row);
    4. flash "Deleted {name} and N chats." (or "Deleted {name}." at 0), with N taken from the response's `chats_deleted`, not the count shown in the dialog.
  - Failure: the dialog stays open, an error flash shows inside it (`App.ui.flash` already targets the top modal), and Delete and the checkbox are enabled again.
- Testids: `delete-agent-btn` stays as the opener. New ids, registered in `docs/ui-testid-registry.md`: `delete-agent-dialog`, `delete-agent-ack-checkbox`, `delete-agent-confirm-btn`, `delete-agent-cancel-btn`.

**DD7. The legacy deleted-agent UI stays as a safety net**: the "Unknown agent" and "This agent no longer exists" rendering and the `agent_deleted` degraded session state are kept. The agent drawer, chats list, chat pane, jump-to, instance render, session state and socket are listed in the flight log's reconnaissance. A chat can still reach that state only by a race. Two are known:
- a chat created (`POST /chat/sessions`, which does not validate the agent, `api.py:5126-5138`) for an agent while it is being deleted;
- a routine run that loaded its routine just before the delete and then calls `create_web_session(agent_name)` (`the_one/routines/runner.py:226-236`). Its run insert then fails the foreign key and returns quietly, leaving one orphan chat. `the_one/agents.md` says so where it describes that state. At landing a squawk is logged to prove that code dead and remove it (method `removing-dead-code`).
- The browser tests that reach the state by deleting an agent over HTTP (lane `chats`: `test_flow_chat_composer_library.py`, `test_flow_chat_drawer.py`, `test_flow_chat_pane.py`, `test_flow_chat_session_state.py`, `test_flow_chat_list.py`) reach it instead by creating a chat for a name that never existed (`POST /api/chat/sessions`). It is leg 1's change that breaks them, so leg 1 moves them.

**DD9. Deleted chat content is scrubbed from the database files**: the shared connection sets `PRAGMA secure_delete=ON` beside its existing pragmas (`the_one/db/connection.py:54-55`), so freed pages are zeroed rather than left readable. This covers every delete path, including the single-chat delete, Purge and the retention sweep. After an agent delete commits, and after the v57 step, `PRAGMA wal_checkpoint(TRUNCATE)` folds the WAL into the main file and truncates it, so pre-delete page images do not linger in the `-wal` file.
- Where the pragma is set:
  - The session template sets it too (`tests/_schema_template.py:45`, `:95`, `:111`, which pin `foreign_keys` the same way), so tests run with production's setting.
  - It is set explicitly rather than relying on SQLite's compile-time default.
  - `connection.py` is the only connection the app opens (`the_one/diagnostics.py:619` is an in-memory probe). `ensure_schema` runs on it after its pragmas are set, so v57 deletes with `secure_delete` on.
  - The dev scripts' own connections (`scripts/sweep_fusion_constants.py`, `scripts/bench_vector_store.py`, `scripts/ui_capture.py`, read-only) delete no chats and are left alone.
  - Chat messages have no full-text index (FTS5 covers knowledge chunks only), so there is no second copy to scrub.
- The request-path checkpoint runs in **its own `write_transaction` block**, after the delete's block has exited (sequential, never nested). The connection is shared, so only the lock guarantees that no other task holds an implicit transaction open at that moment. The PRAGMA opens no transaction, so the block's commit does nothing. The v57 checkpoint runs after v57 commits (DD4). A busy or partial result (the pragma reports `busy=1` rather than raising) is logged and tolerated; it never fails the delete or the startup. The pages are already zeroed, and the next checkpoint finishes the job. An unexpected exception from the checkpoint is caught and logged for the same reason.
- **Coordination:** `the_one/db/connection.py` is shared with Mission 37 (Flight 2, backend boundaries). The change there is one pragma line, and the flight log records it for the Mission 37 session.
- Trade-off: deletes write more (zeroed pages). This app's deletes are small and rare.
- Out of scope: backups and copies the operator made, and filesystem-level remnants (SSD wear levelling). `SECURITY-MODEL.md` says so.

**DD8. Documents move with the behaviour**:
- `the_one/agents.md`: the "agent delete leaves sessions in place" text (around `:2811`, `:2829-2833`), the General tab danger zone (around `:2572`), the drawer and row-meta states (around `:1843`, `:1892`).
- `SECURITY-MODEL.md`, beside the existing agent-delete cascade text (around `:439`, `:460`), says:
  - deleting an agent deletes its chats in the same transaction;
  - v57 purged earlier orphans;
  - deleted content is scrubbed (`secure_delete` plus checkpoint, DD9), with the out-of-scope remnants named.
- The GleepGlorp guide `the_one/gleepglorp/guide/agents.md:40-42`: Delete now asks in a dialog and deletes the chats. Drift alarm: `tests/test_gleepglorp_guide.py`.
- `docs/ui-testid-registry.md` (the dialog's new ids). `docs/ui-control-inventory.md` gets a row only if `tests/test_ui_control_inventory.py` requires one for a composition (the agent picker has one); no library row changes.
- The behavior spec `tests/behavior/studio-agent-crud.md`'s delete steps describe the dialog. It is not run as a gate.

### Citation Audit

Verified against the worktree at `c3df3d73`:

| Citation | Status |
|---|---|
| `the_one/db/_write_lock.py::write_transaction`: one module-level `asyncio.Lock`, raises `RuntimeError` on re-entry from the same task | verified |
| `the_one/db/repositories.py::SQLiteAgentStore.delete`: `exists()` check then one `DELETE FROM agents` in `write_transaction` | verified |
| `the_one/db/repositories.py::ChatSessionRepository.delete_all_for_agent`: deletes GleepGlorp proposals and fills by session, then chats, in one transaction; notifies when the count is non-zero | verified |
| `the_one/db/repositories.py::SQLiteAgentStore.rename`: rewrites `connectors.config.default_agent` and `channel_map` values in the same transaction | verified |
| `the_one/interfaces/web/api.py::delete_agent`: store delete, `cascade_delete`, `_evict_agent_connections`; no chat or `_sessions` handling | verified |
| `the_one/interfaces/web/app.py::_run_purge_sweep_and_evict`: pop ids under `_sessions_lock`, then `session_locks.pop` and `agent.aclose()` outside it | verified |
| `the_one/connectors/inbound.py::dispatch_inbound`: `resolve_session` runs before `factory.create`; no `default_agent` → warning and return | verified |
| `the_one/db/connection.py`: one shared connection with `PRAGMA foreign_keys=ON` | verified (code interrogation) |
| `the_one/db/schema.py`: `CURRENT_VERSION = 56`; child tables `ON DELETE CASCADE` from `agents(name)`; `chat_sessions` has no FK since v5; v53 is a data-only chat delete excluding GleepGlorp | verified (code interrogation) |
| `static/js/ui/modal.js`: every action's click calls `finish(s, a.value)`, which closes the dialog; Escape and `cancel` always close; `footerEnd` and `initialFocus` options | verified (Architect, Flight Director) |
| `static/js/areas/studio/routines-custom-recurrence.js`: own buttons in `footerEnd`, `modal.close()` called by the caller | verified |
| `static/js/ui/editor.js::App.ui.dangerZone`: `beforeArm(proceed)` runs on the first click and arms only if `proceed()` is called; `onConfirm(revert)` on the second | verified (Architect) |
| `app.py` socket `cancel` action: token first, `t.cancel()` per not-done `_session_inflight` task, `_notify_cancelled_once` when none started | verified |
| `the_one/sessions/_broadcast.py::broadcast_to_session(session_id, payload, *, exclude)` | verified |
| `static/js/areas/chat/session-flow.js::dropGoneBound`: returns unless the drawer profile | verified (Architect) |
| `the_one/db/connection.py`: WAL and `foreign_keys=ON`, no `secure_delete` | verified |
| `static/js/areas/studio/provider-delete.js`: `App.ui.checkbox` gates a disabled danger button | verified |
| `api.py::list_chat_sessions`: no filter beyond the optional `agent_name` | verified |
| `the_one/gleepglorp/`, self-configuration surface, CLI: none can delete an agent; `delete_agent` and v53 are the only paths that delete an `agents` row | verified (code interrogation) |

### Prerequisites
- [x] Worktree `/home/cprch/projects/the-one-sortie-20` on `sortie/20-deleting-an-agent-deletes-its-chats` from `main` at `c3df3d73`, with no upstream set.
- [ ] Worktree venv: the worktree has none of its own. Leg 1 creates one with `uv sync --all-extras --frozen` in the worktree (never touching the main checkout's `.venv`). Re-verify per leg.
- [ ] Schema version 57 is unclaimed on `main` and on Mission 37's open branches. Re-check at merge.
- [x] Every implementer of `AgentConfigStore.delete` was found: `grep -rn "def delete(self, name: str)" the_one tests` gave `the_one/agent/store.py:22`, `:56`, `the_one/db/repositories.py:447`, `tests/test_factory.py:47` (plus unrelated rule, note and tool deletes).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete: every code-asserting design decision verified
- [x] Prerequisites verified at planning (venv and v57 re-checked at leg time)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Backend first, then the UI. Each leg ends consistent with its own tests.

**Leg 1** gives the data layer its new meaning:
- the single cascading store delete;
- the route's cancel, tell and evict, and the count it returns;
- connector clearing;
- the v57 purge;
- secure deletion.

It updates every unit test that asserted chats survive, and it moves the lane `chats` browser tests that deleted an agent over HTTP onto a never-existed agent.

**Leg 2** builds the dialog as a composition that owns its buttons (no library change), wires it into the General tab through `beforeArm`, and updates the UI-driven delete tests.

The closing gate runs after both.

### Checkpoints
- [ ] Unit: deleting an agent leaves no `chat_sessions`, GleepGlorp proposal or fill, routine run, or connector binding for it; a forced failure mid-transaction leaves agent and chats intact.
- [ ] Unit: v57 on a database with orphans, a live agent's chats and GleepGlorp chats deletes only the orphans.
- [ ] Route: `DELETE /api/agents/{name}` returns `chats_deleted`, cancels an in-flight turn, sends `session_deleted` to the chat's subscribers, evicts the cached sessions, releases the agent's PTY sessions and pushes `sessions_changed`.
- [ ] Unit: the connection has `secure_delete` on. A raw-bytes test runs through the production `get_connection()` (WAL mode, the worker's own data directory; template connections are `journal_mode=DELETE` or `:memory:` and would pass vacuously):
  1. put a unique marker in one message's text only;
  2. assert the marker **is** in the `.db` or `-wal` bytes before the delete (the falsification);
  3. delete the agent and assert the checkpoint reported `busy == 0`;
  4. assert the marker is in neither file.
- [ ] Browser: the dialog's checkbox gate, Cancel focus, Escape, success navigation and flash, and the failure path.
- [ ] Closing gate green: `make test-unit`, then `make test-browser` with `THE_ONE_TEST_NETNS=1`, on a quiet host.

### Adaptation Criteria

**Divert if**:
- The existing cancel path cannot be shared with the eviction helper without changing what the socket's `cancel` action does (DD2).
- Mission 37 claims schema v57 before merge (renumber, re-run the schema tests).
- The dialog cannot be built without a control-library change (DD5, DD6). That brings in the inventory and contract-test rules.
- `secure_delete` breaks or measurably slows a test lane (DD9).

**Acceptable variations**:
- The eviction helper's name and home in `app.py`.
- The dialog's copy, within Option A's shape.
- Whether `delete_all_for_agent` is reused by the store method or the statements are inlined. It is not callable inside the transaction (it takes the lock itself).

### Legs

- [ ] `cascade-delete-and-orphan-purge`: DD1 to DD4, DD9, DD7's lane `chats` test moves, and DD8's backend documents (`the_one/agents.md` and `SECURITY-MODEL.md`).
  - Code: the store transaction; the route's cancel, tell, evict and PTY release, and `chats_deleted`; connector clearing; migration v57 with its pins and the `tests/test_db_migration.py` replay tests; `secure_delete` and the checkpoints.
  - Unit tests: cascade, atomicity, connectors, eviction (including the purge sweep's), the purge, and scrubbing.
  - Risk: high (a migration that deletes the operator's data; a shared delete path).
- [ ] `delete-agent-dialog`: DD5, DD6 and DD8's UI documents.
  - Code: the dialog composition with its own buttons, the General tab's `beforeArm` wiring and row description, the controller.
  - Documents: the guide, the testid registry.
  - Tests: new browser tests in lane `agents` (checkbox gate, Cancel focus, Escape, Escape mid-request, success navigation and flash, failure path, the opener's double click), plus `test_flow_agent_crud.py`, `test_flow_agents_list.py`, `test_flow_agent_general_tab.py`, and lane `routing`'s `test_store.py:498` and `test_nav_guard.py:653` moved off the two-step.
  - Risk: medium.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Squawk logged: remove the legacy deleted-agent UI (DD7)

### Verification
- Unit tier (`make test-unit`): the store, route, migration and eviction tests named in the legs.
- Browser lanes in the closing gate, all of them: the change touches `agents`, `chats` and `routing`, and a connection pragma every lane runs under, so the full `make test-browser` runs.
- No behavior test is run as a gate. No HAT, by the operator's choice.
