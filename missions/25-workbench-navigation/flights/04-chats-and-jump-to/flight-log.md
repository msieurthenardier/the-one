# Flight Log: Chats and Jump-to

**Flight**: [Chats and Jump-to](flight.md)

## Summary

**Status**: landed (2026-10-06). 10 legs (two planned legs split at design review), committed as `340dad4` and opened as draft PR #220. The flight-end review needed one fix cycle. The close-gate behavior runs passed 96 of 96 checkpoints across five specs. `vision-round-trip` was not run, because it needs a live Anthropic key.

---

## Reconnaissance Report

**Sources:**
- the Flight 4 research digest (read-only reconnaissance of `c3f0a86` by an Opus research
  agent, 2026-10-05; kept in the Flight Director's scratchpad);
- the Flight 3 debrief's recommendations and action items;
- the open squawks that touch this flight's surfaces;
- the reference spec §15 items assigned to Flight 4.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0110 (`chat-image-input` has no accessible name) | confirmed-live | `chat.js:309-323`; the hidden `<input type=file>` with no name | Fix in leg 3, in the composer rebuild (DD6). |
| Squawk 0111 (a stalled join orphans a session) | confirmed-live | `chat.js:509-521` timer, `:1202-1210` drain re-send | Closes by construction in leg 2: no client path sends `new_session` (DD1). |
| Squawk 0117 (split the `shared` lane) | confirmed-live | `scripts/run-tests.sh:94-104`; shared 867 tests in 12m38s | Leg 1, before any new dual-engine contract (DD11). |
| Squawk 0118 (document the editor Cancel contract) | confirmed-live | `grep -i cancel the_one/agents.md` finds no editor contract | Bundled into leg 4, with the Chat action's header chrome (DD8). |
| Squawk 0116 (Settings tile title row) | confirmed-live; **not this flight's surface** | `admin.css` `.provider-tile-link` 128px reserve | Stays a squawk for Flight 6 or the next mission (the entity-tile extraction). |
| F3 debrief rec. 1: an operator preview before the close gate | confirmed-live (a process item) | — | DD13: non-blocking, after leg 5. |
| F3 debrief rec. 2: the studio `dirty` flag decision before Flight 4 | confirmed-live | `studio.js:365` one flag; 30 writes; `isDirty` `:3855-3858` | Decided in DD8: it stays single, and every exit goes through `go()`. |
| F3 debrief rec. 3: split the shared lane | duplicate of 0117 | — | DD11. |
| F3 debrief rec. 5: behavior-test crew-file rules | confirmed-live; **not a code item** | `.flightops/agent-crews/behavior-tests-execution.md` lacks them | The Flight Director carries them in every spawn prompt, and updates the crew file at leg 6. |
| F3 checkpoint question 7 (focus drops to BODY after Create, Save and Test) | confirmed-live; **not this flight's surface** | the Flight 3 log observation | Carried to Flight 6 (alignment). Flight 4's own new surfaces keep focus on a sensible control (leg acceptance). |
| §15 A10, A11, A13, A16, A17, A20, A21, A25, A28, A29, A30 (scrim), A32 | confirmed-live | reference spec §15 | Resolved in DD15. |
| The welcome reads `agent.provider`, which is always undefined | confirmed-live | `welcome.js:70`; `AgentConfig` has no `provider` | Goes away with the welcome list's retirement (DD3). |
| A start failure is invisible while the welcome shows | confirmed-live | `chat.js:434-438`, `app.py:2565-2575` | Leg 2: start errors show in the pending pane (DD1). |

---

## Leg Progress

### Leg 1: controls-and-data (landed, 2026-10-05)

**What landed.** Nothing user-visible changes in Chats: the new controls appear only on the
Design language page and in contract tests, and the chat area only primes the new `sessions`
collection.

- **Lanes (squawk 0117, DD11).** `scripts/run-tests.sh` gains a sixth lane, `contracts`
  (`contracts_pat=('test_ui_*')`, 12 files today, 14 with this leg's two new ones), and
  `shared` is now the complement of all five named lanes. `--list` (parsed explicitly,
  `--list) list=1; shift ;;`) prints a lane's files and exits 0 without running pytest;
  `--list` without `--lane` exits 2; an unknown lane still exits 2 with the usage text, which
  now lists `chats|agents|library|settings|contracts|shared`.
  - `tests/test_run_tests_lanes.py` (new, unit tier): the six lanes are pairwise disjoint,
    their union is every `tests/browser/test_*.py` minus `test_visual_snapshots.py`, the
    `contracts` lane is exactly `test_ui_*`, and the two exit-2 paths.
  - Union by test count (DD11): the six lanes collect 42 + 132 + 146 + 178 + 559 + 438 = 1495
    tests, exactly the `-m browser tests/browser/` selection (1495/1507, 12 deselected).
  - The `test_ui_*` docstrings now say "Falls in the `contracts` browser lane".
- **`App.ui.searchList`** (`static/js/ui/search-list.js`, new; DD14, A10). A combobox input
  (`role=combobox`, `aria-autocomplete=list`, `aria-expanded=true`, `aria-controls`,
  `aria-activedescendant`) over a `role=listbox` of labelled `role=group`s (a
  `role=presentation` caption) and `role=option` rows with generated ids; only the active row
  has `aria-selected="true"`; rows are never focusable and a listbox `mousedown` is prevented,
  so focus stays in the input. Up/Down (clamped), Enter (`preventDefault`; nothing with no
  options); Home/End and Escape not intercepted; IME keys ignored; a pointermove activates, a
  click picks; the active option scrolls into view inside the listbox only (manual
  `scrollTop`). Empty: the listbox hides, an `App.ui.emptyState` shows `emptyText(query)`, and
  a persistent visually hidden `role=status` region carries the same text. `source` output is
  validated before the DOM changes; empty groups are dropped; a label-less group renders no
  caption. `destroy()` removes its five listeners (input and listbox only) and clears
  `aria-activedescendant`. CSS in `components.css` (reference spec 5.6's picker row), a
  forced-colors Canvas/Highlight border, a script tag in `index.html`, and a new
  `ui-search-section.js` demo (12 agents in "Recently used" and "All agents", plus an
  empty-result list) registered in `design-language-page.js`'s `SECTIONS`.
- **`App.ui.modal` chooser options** (DD14): `width`, `top` (inline card styles only),
  `initialFocus`, `closeButton` ({label, ariaLabel, testid}: a `btn-ghost btn-sm` at the end of a
  `.modal-dialog-header` row, closing with `cancelValue`), `footer` (`.modal-dialog-footer`; a
  DocumentFragment's items become the row's flex children and it is copied per `open()`;
  `.modal-dialog-footer-end` pushes an item right) and `layout: 'chooser'` (zero padding, the
  `16px 20px 12px` header, a full-bleed flexing body, the 11px `--fg-muted` footer, **no
  `aria-describedby`**, no actions). Focus on open: `initialFocus`, else (with a close button or
  the chooser) the body's first focusable, else the usual order, never landing on the close
  button while anything else is focusable. With no new option a modal is unchanged (pinned).
  The `ui-modal` demo gains "Open chooser" (640 wide at top 72, a `searchList` body).
- **`App.ui.listPane` additions** (DD5, DD12, DD14): `rowStyle: 'chats'` (line 1 the title
  with `time` pushed to the end, line 2 the meta then the badges; `8px 10px`), `block` (a node
  after the `<header>`, outside it), `item.dataset`, `data-confirm-title` on every label, and
  row actions under the DD5 contract: a sibling `button.ui-list-pane-action` in the row's `li`,
  `display:none` until `li:hover`/`li:focus-within`; only the stop row's action is
  `tabindex=0` (`setStop` and a body `focusin` re-derive it); Up/Down/Home/End on an action
  move to the rows; a focused action restores to the same item's action, else the
  neighbouring row (next old item still visible, else previous); a focused row keeps Flight
  3's rule; an armed (`.confirm-delete`) `li` is reused across `setItems` with `entry.item`
  replaced (row `onSelect` and action `onClick` read the entry at click time); an armed item
  that disappears has its `li` dropped and the lapse timer runs harmlessly on the detached
  node. The `ui-lists` demo gains a Chats-style pane (New chat block, pending row, platform
  badge, delete through `App.confirmDelete`).
- **Data (DD4).** `api.py::_session_summary` adds `platform` (list, detail, create and update
  responses). `App.store` gains `sessions` (`/api/chat/sessions`) and `prime(name, rows)`
  (copy in, loaded/ok/fresh, `gen` bumped, in-flight dropped, then a notify). The chat area's
  `session_list` handler primes `sessions` in the REST summary shape. `studio.js` invalidates
  `sessions` on agent rename (beside `invalidate('agents')`) and in Purge now's success
  `.then`, after the `deleted` count.
- **Tests.** New: `test_ui_search_list_contract.py` (21 tests x 2 engines),
  `test_ui_list_pane_chats_contract.py` (26 x 2), `test_run_tests_lanes.py` (5). Extended:
  `test_ui_modal_contract.py` (+12 chooser tests), `test_ui_listener_cleanup.py` (+2 searchList
  cases), `test_store.py` (+5 prime/sessions tests), `test_store_static.py` (six collections,
  the `LITERAL_LIST` probe, the `prime` pin, the chat prime pin, the rename and Purge-now rows),
  `test_db_api.py` (`platform` on all four responses; the REST summary keys are a subset of
  `_session_to_list_payload` with equal values), `test_design_tokens_a11y.py` (searchList and
  chats-row pairs plus their rule-consumption pins, two forced-colors rows),
  `test_index_asset_cache_busting.py` (71 to 73), `test_ui_control_inventory.py` (eight
  sections), `test_ui_guards.py` (the camelCase test-id probes), and
  `test_ui_library_contract.py`'s unknown-`rowStyle` assertion (`'chats'` to `'bogus'`).
- **Docs.** `docs/ui-control-inventory.md` (a `searchList` row; the `listPane` and modal rows),
  `docs/ui-testid-registry.md` (the four `ui-demo-chooser*` ids; the camelCase key note),
  `CLAUDE.md` (the lane list, `--list`, the partition test; `App.store`'s six collections,
  `prime` and the new invalidations), `the_one/agents.md` (the lane summary; the test-id rule;
  Search list, Modal chooser options and List pane additions bullets; the living reference;
  the store's `sessions` row, `prime`, the two invalidation rows and the WebSocket note; the
  `detail-endpoint-attaches-rich-payload` precedent now sanctions the one scalar `platform`).

**Gates.**

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (499 files formatted) |
| Static guards: `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_control_inventory`, `test_nav_helper`, `test_store_static`, `test_index_asset_cache_busting`, `test_ui_library_source`, `test_run_tests_lanes` | 393 passed in 2.8s |
| `make test-unit` | 5067 passed, 10 skipped, 1573 deselected in 658.6s (10m59s) |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`, `THE_ONE_TEST_NETNS=1`) | 556 passed, 3 skipped in 145.2s (2m30s wall); the 3 skips are the existing in-test "WebKit has no forced-colors emulation" skips, so WebKit launched and ran |
| `--lane shared` (`TEST_TIMEOUT=3600`, `THE_ONE_TEST_NETNS=1`) | 438 passed in 654.3s (11m10s wall); before the split the lane was 867 tests in 12m38s |
| `--lane chats` (`THE_ONE_TEST_NETNS=1`) | 42 passed in 99.8s (1m43s wall) |

**Falsifications** (each restored from a scratch copy and re-run green; no residue, grep
`FALSIFIED` is empty):
- **Lane partition (AC3).** A scratch `tests/browser/test_zz_probe.py` landed in `shared`
  (and the partition test stayed green, as it should for a new file); adding
  `'test_flow_chat.py'` to `contracts_pat` failed `test_lanes_are_pairwise_disjoint` ("lanes
  'chats' and 'contracts' both claim ['tests/browser/test_flow_chat.py']") and
  `test_contracts_lane_is_exactly_the_ui_contract_files`. Probe deleted, pattern reverted,
  5 passed.
- **`searchList`**: dropping the active row's `aria-selected` failed 10 tests (5 per engine:
  the ARIA test, arrows, pointer, both themes' active style). Restored: 42 passed.
- **`modal`**: giving the chooser an `aria-describedby` failed
  `test_chooser_layout_structure_and_no_describedby` in both engines. Dropping the body-first
  focus rule at first failed **nothing**: the close-button-skipping fallback masked it in every
  case the test covered. Test gap closed with a close-button modal that has actions and a body
  input (the rule is what puts focus on the input rather than the first action); the
  re-falsification failed it in both engines. Restored: 72 passed.
- **`listPane`**: dropping the actions' tabindex re-derivation in `setStop` failed 16 tests (8
  per engine: tab policy, roving re-derivation, arrows on an action, hidden-row reach, and the
  four focus-restore cases); dropping the armed-`li` reuse failed the two armed-survival tests
  in both engines. Restored: 52 passed.
- **`App.store.prime`** (not a control, but the race is the contract): dropping the `gen` bump
  failed `test_prime_supersedes_a_racing_older_get` (`['stale'] == ['p1']`) and the static pin
  `test_store_prime_bumps_the_generation_and_is_exported`. Restored.

**Design-language check** (a dev instance on 8486 with a scratch data dir, dev mode, Chromium
1440x900; stopped afterwards): the `searchList`, Chats-style `listPane` and chooser demos render
in both panes with no console error; the chooser opens 640x449 at (400, 72) with focus on its
search input, filters, and Enter closes it.

**Deviations and decisions** (also in "Deviations" below):
1. **AC8's description pair.** `--fg-muted` on the active row's `--accent-translucent-hover`
   wash over `--surface` is 3.85:1 dark and 3.92:1 light, below body AA. The description is
   `--fg-secondary` throughout (as reference spec 5.6 draws it) and the meta, `--fg-muted` at
   rest, takes `--fg-secondary` on the active row (Flight 1's A24 precedent). The gate checks
   those pairs instead of `--fg-muted` on the wash.
2. **AC7: Home/End are not intercepted** by `searchList`; they move the caret per the APG
   combobox pattern. This deliberately narrows DD10's "Home, End jump" wording; the palette
   (leg 7) inherits it.
3. **Shift+Tab into a list with actions lands on the stop row, not its action.** The action
   is `display:none` until its `li` has focus (AC15 forbids visibility/opacity), so it is
   reachable forward only (row, Tab, action), as the legacy chat list was. Pinned by
   `test_tab_goes_stop_row_then_its_action_then_out`.
4. **Focus restore to a hidden action** uses a transient `li.ui-list-pane-reveal` class around
   `action.focus()`, because a `display:none` button cannot take focus; `:focus-within` keeps
   it shown afterwards. Found by the contract test (focus had dropped to `<body>`).
5. **The test-id guard learns `<lower>Testid` keys.** `searchList`'s `inputTestid` and
   `rowTestid` (named by AC5) were invisible to `_PROP_LITERAL`/`_TESTID_KEY` (case-sensitive
   `testid:`), so their ids would have been silent manual exceptions. `tests/_ui_guard_helpers.py`
   now treats `testid|[a-z]+Testid` as a test-id key in extraction and value checks, with
   probes in `test_ui_guards.py`.
6. **Modal option guards.** `layout` other than `'chooser'` throws; the chooser throws on
   actions and on a non-Node body; `footer` must be a Node; a fragment footer is copied per
   `open()`.
7. **The chats style ignores `icon`, `lead` and `count`**, and `time` is drawn only in it
   (documented in the factory comment).

### Leg 2: ws-start-protocol (landed, 2026-10-05)

**What landed.** The server side of DD1 only. `chat.js` still sends `new_session` (AC9), so
nothing user-visible changes; `static/js` is untouched.

- **`the_one/interfaces/web/app.py`:**
  - **`_validate_message_payload(payload) -> ValidatedPayload`** (a `NamedTuple` of
    `user_input, images, content, error, empty`; AC1). Order: the `message` type (`None` is
    `""`; any other non-`str` is `"Message must be text."`), emptiness, image shape, count
    and size (today's texts and warning logs, moved verbatim), then `_build_user_content`
    (`"Cannot process message: {exc}"`). The message path uses it: silent `continue` on
    empty, a `system` frame with the same text on error.
  - **`_spawn_web_message(session, content, ws)`**: the task plus both inflight bookkeeping
    sets, registered synchronously; used by the message path and `start_session`.
  - **`leave`** (AC2): `remove_subscriber`, touch `last_activity`, `session = None`; no
    frame, no DB write, no cancel; a no-op when unbound.
  - **`start_session`** (AC3-AC7), in the DD1 order: validate (`session_id` type, then
    `[0-9a-f]{32}`; `agent_name`; empty; `/reset`; the shared validator) → reserve
    (`_acquire_start_reservation`: a synchronous check-and-set on `_start_reservations`,
    waiters `wait_for(shield(fut), _START_RESERVATION_WAIT_S = 30)` per wait, looping) →
    look up inside the reservation (its own narrow `try`) → ok joins like `join`
    (delivering the message only if never delivered) / degraded unbinds whatever was bound
    → strict create (the only thing in the `try`) → swap (bind and subscribe before the
    first send) → `session_joined` (`is_processing: true`) → pause snapshot →
    `_spawn_web_message` → `finally` resolves and pops the reservation
    (`_release_start_reservation`). Every non-success exit sends `start_failed` via
    `_start_failed_frame` (echoes a `str` id, else `null`) and `continue`s.
  - **`join` of an unknown id** (AC8a): unbinds whatever was bound, `session = None`, sends
    `{type: "join_failed", session_id, error: "not_found"}`, creates nothing. `join`
    without an id keeps the re-bind / auto-create.
  - **`_create_session(..., strict=False)`** (AC6): with `strict=True` the persist `except`
    catches `BaseException`, pops `_sessions[sid]` under `_sessions_lock` (identity-guarded,
    with a `finally` so a second cancel while waiting for the lock cannot skip the pop) and
    re-raises; `strict=False` still swallows `Exception` and lets a cancel propagate, as
    before.
  - **`_build_session_joined_ok(session, is_processing=None)`** (`None` derives from the
    lock, as before; the returned dict is never mutated).
  - **`_restore_session`'s skip-rebuild guard** also checks `_session_inflight` (AC8b).
  - **The bare-message auto-create** catches `except Exception` with
    `logger.exception` (AC8).
- **Tests.**
  - `tests/test_ws_start_session.py` (new, 53 tests), per the prescribed harness: a copied
    `FakeWebSocket` with awaitable script steps (`Wait`, `WaitFrame`, `Do`) and an optional
    send failure; `isolated_db` (rows via `ChatSessionRepository.list()`/`.get(sid)`, no
    agent row seeded); `_get_factory` patched to a fake factory whose `_QuickAgent`-style
    agents append to `messages` and yield one assistant reply (per-text gates park a turn);
    `_send_to_session` and `_save_session_to_db` real; `_create_session` patched only to
    park or fail it; an async autouse cleanup (cancel and gather `_inflight_tasks`; clear
    `_session_inflight`, `_start_reservations`, `app._sessions`, `clear_for_test`,
    `clear_locks_for_test`); spawned turns awaited before persistence asserts.
    Coverage: the message path through the validator (non-text, null, the order change,
    a happy path); `leave` (unbind with no frame, no DB write, the turn completes and
    persists, the disconnect after it does nothing; unbound no-op; after the session was
    deleted); 23 parametrized `start_session` rejections, each exactly one `start_failed`,
    nothing created, the prior binding still receiving a probe broadcast; the existing-id
    join (one socket twice plus a second socket: one entry, one row, one processed message;
    empty history delivers exactly once; another agent's session is joined; lookup failure
    for `RuntimeError` and `ImportError`; degraded unbinds the same id and another id); the
    three AC5 reservation tests (`gather` over two or three endpoints and a director
    coroutine); strict create (factory and persist failures keep the binding and leave no
    entry or row; cancellation pops; `strict=False` still swallows); frame order and
    persistence (`session_joined` with `is_processing: true` first, reply persisted under
    the new id with the agent name and title); a swap while the old session's turn runs
    (it completes and persists, its frames stop); a send failure on `session_joined`
    (no `start_failed`, the subscription cleaned up, nothing spawned) then a re-send that
    delivers once; AC8 (`ImportError`, `system` frame, live socket); AC8a (unknown id and an
    id deleted while bound) and `join` without an id; AC8b with its control; AC9
    `new_session`.
  - `tests/test_ws_build_user_content.py` gains `TestValidateMessagePayload` (18 tests), the
    validator's pure unit tests, kept out of the new file because its autouse fixture
    builds a DB (about 0.45s per test).
  - `tests/test_ws_message_branch_crash_guard.py` is unchanged: its monkeypatch targets
    (`_create_session`, `_spawn_message_processing`) are still module globals looked up at
    call time, and its `create_calls` assertions hold.
- **Docs.** `the_one/agents.md` gains "Chat WebSocket protocol (`/ws`)" after "Web-session
  idle reaper": an action table (`join` with `join_failed`, `leave`, `start_session` with
  `start_failed`, `new_session` until leg 3, `message`), the shared validation and its
  order change, and the `start_session` contract (validation, the idempotency rule,
  reservation, strict create, post-create order, the restore guard, re-send never `join`).
  Its MCP "Synthetic csid pattern" line said "12-char hex" too and is updated with
  `the_one/mcp/oauth/handlers.py`'s docstring (12 server-allocated, 32 client-allocated;
  the charset argument unchanged). `CLAUDE.md` documents no WebSocket actions, so it gets
  no line.

**Gates.**

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (500 files formatted) |
| `test_ws_start_session.py` + `test_ws_build_user_content.py` + `test_ws_message_branch_crash_guard.py` | 89 passed |
| WebSocket and session neighbours (those three plus `test_ws_responsiveness`, `test_cancel`, `test_session_lifecycle`, `test_web_session_reaper`, `test_app_websocket_pause_resume`, `test_last_usage_round_trip`, `test_session_registry_lock_unification`) | 160 passed in 30.9s |
| The reservation, leave, swap and existing-id classes, repeated for timing stability | 16 passed in each of 8 runs with the timeout test's patched wait at 0.3s, then 5 more at the final 1.0s (widened for margin under a loaded machine) |
| `make test-unit` | 5138 passed, 10 skipped, 1573 deselected in 672.7s (11m31s wall); leg 1 was 5067, and this leg adds 71 (53 + 18) |
| `--lane chats` (`THE_ONE_TEST_NETNS=1`, `TEST_TIMEOUT=1200`, `-x`) | 42 passed in 97.7s (1m41s wall), unchanged from leg 1 |
| Spot check, `test_flow_hash_routing.py` + `test_router_items.py` (`THE_ONE_TEST_NETNS=1`), because `join` semantics changed | 40 passed in 102.0s |

**Falsifications** (each applied in place with the good file saved to the scratchpad, run, then
restored by copying it back; `cmp` confirms byte-identical; grep `FALSIFIED` is empty):
- **AC4, the existing-id check** (`if False and restored.status == SESSION_STATUS_OK`):
  `test_resend_is_idempotent_on_one_socket_and_across_sockets` fails. The second send falls
  into the strict create, hits `sqlite3.IntegrityError: UNIQUE constraint failed:
  chat_sessions.id`, pops the entry and answers `start_failed`, so the second
  `session_joined` never arrives (the script's `WaitFrame` times out).
- **AC5, the reservation** (the check replaced by `existing = None`):
  `test_concurrent_starts_create_once` and
  `test_a_waiter_timeout_does_not_cancel_the_shared_reservation` fail. B creates while A is
  parked; A's later insert collides and A never joins.
  (`test_failed_creator_hands_over_to_the_waiter` still passes without it, as expected:
  with A failing anyway, B creating on its own gives the same outcome.)
- **The shield** (`wait_for(existing, ...)` unshielded):
  `test_a_waiter_timeout_does_not_cancel_the_shared_reservation` fails. B's timeout
  cancels the shared future, and C, arriving later, dies with `CancelledError` awaiting it.

**Decisions and deviations** (the Flight Director should review; also in "Deviations"
below):
1. **Waiters look up only inside a reservation.** AC5 has a woken waiter run the lookup and
   re-enter the reservation step only if the creator failed. Here a woken waiter loops
   straight back to the reservation step and looks up inside its own reservation. The
   reason: `_restore_session`'s `not_found` path pops `_sessions[sid]`, so a lookup
   outside a reservation could pop a re-reserving creator's in-memory session between its
   `_sessions[sid] = session` and its DB insert (the same hazard as the leg 3 `join`
   constraint). The outcomes are the same (join what was created, or create), with one
   lookup per decision, and the "several waiters" behaviour is unchanged.
2. **Delivery on an existing id also requires the lock to be free.** AC4 delivers when the
   history is empty and `not _session_inflight.get(sid)`. This adds
   `not is_session_processing(sid)`, because a connector dispatcher turn holds the lock
   without registering in `_session_inflight`. When it delivers, that `session_joined`
   carries `is_processing: true` (AC7's `inflight or locked` formula would read false just
   before the spawn); otherwise it uses AC7's formula.
3. **Error texts the leg left open:** `"Invalid session id."`, `"Invalid agent name."`,
   `"Timed out waiting for this chat to start."`, and `"Cannot start chat: {exc}"` for a
   lookup or create failure (today's `system` wording). Leg 3b shows the text in the
   pending pane.
4. **Recorded order changes (AC1):**
   - the content build now runs before the bare-message auto-create, so a build failure
     creates no session (pinned by `test_content_build_failure_creates_no_session`);
   - a `/reset` carrying a malformed image is now an error rather than a clear;
   - a non-null, non-`str` `message` (e.g. `5`) is now a `system` "Message must be text."
     with no session created. It used to be spawned and fail inside the turn.
5. **The validator's unit tests live in `test_ws_build_user_content.py`** (see Tests).

**For leg 3 (constraints this leg leaves):**
- **Re-send `start_session` while starting, never `join`.** The reservation does not cover
  `join`. A `join(sid)` landing between `_create_session`'s `_sessions[sid] = session` and
  its DB insert finds no row, pops the in-memory entry, and now answers `join_failed`.
- **A start's `session_joined` has `is_processing: true` whenever this request spawned the
  message.** A re-send to an id whose first message was already delivered gets the real
  state, which may be `false` once the turn has finished.
- **`join_failed` is `{type, session_id, error: "not_found"}`**, and the session id is
  echoed as sent.
- **`start_failed.session_id`** is the id when it was a string, else `null`.

**Observation (not changed, out of scope).** `join`'s degraded branch still only
unsubscribes when the requested id differs from the bound one: a `join(sid)` while bound to
that same `sid`, now degraded, sets `session = None` but leaves the socket subscribed. The
leg told `start_session` not to copy this; `join` itself is unchanged. It may merit a
squawk.

### Leg 3a: chats-test-seam (landed, 2026-10-05)

**What landed.** Test-only: every browser test that starts, joins or expects a chat now goes
through one helper module, on today's semantics (the client still sends `new_session`, so a
session exists when a start returns) and today's DOM. Nothing under `the_one/` changed (AC4:
no `the_one/` file is newer than the leg's first scratch file; the `the_one/` entries in
`git status` are legs 1 and 2's).

- **`tests/browser/_chats.py`** (new; AC1). Each docstring names today's mechanism and the
  leg (3b or 4) that changes its body:
  - `start_chat(page, agent, timeout=8000)`: waits for the chat area to settle (the welcome
    is shown, or a session is bound), then starts through whichever surface a user has: the
    welcome option (no chat open), the header `new-chat-btn` (the open chat's agent), else
    the `agent-select` dropdown. It returns once a NEW session is bound
    (`_currentSessionId` set and different from before), the badge reads the agent and
    `chat-input` is enabled;
  - `send_first(page, text)`: fill, Enter, then wait for the user's bubble (the turn has
    begun);
  - `expect_chat(page, agent)`: the badge reads the agent (after a start, a deep link or a
    reload);
  - `current_session_id(page)` (the area's `_currentSessionId`, else None),
    `chat_row(page, id)` (`button.session-item[data-id]`), `chat_rows(page)`,
    `open_chat(page, id)` (click, then the route `chats/{id}` and the current id);
  - `chat_frames(page, actions=None)`: a live list of the parsed JSON frames the page
    sends, through Playwright's `websocket`/`framesent` events (call it before `goto`);
  - `welcome(page)`, `welcome_item(page, agent)` (exact name, through
    `.chat-welcome-item-name`), `new_chat_button(page)`, `agent_badge(page)`.
- **`seeders.seed_session(base, agent_name, title, updated_at, created_at=None,
  platform=None, messages=None)`** (AC2): `POST /api/chat/sessions`, returning the
  server-allocated id. A `datetime` is sent in `now_iso`'s format (UTC `isoformat`; a naive
  one is taken as UTC), `created_at` defaults to `updated_at`, and `messages` is a list
  (JSON-encoded) or an encoded string. `test_seeders.py::test_seed_session_round_trips_past_dates_and_platform`
  seeds a session 3 days old with `platform="discord"`, an explicit `created_at` and one
  message, plus a recent web session, and reads them back through `GET /api/chat/sessions`
  (exact summary rows) and the detail route (the messages).
- **Helper smoke tests** (new, chats lane): `tests/browser/test_chats_helper.py`, two tests.
  One drives all three `start_chat` paths (welcome, same agent, dropdown; three distinct
  session ids, exactly three `new_session` frames with the right agents), the exact-name
  welcome match (`Alpha` vs `Alpha 2`), `chat_row`'s `aria-current` and `open_chat` (exactly
  one `join`). The other drives `send_first`. The file is added to `chats_pat` in
  `scripts/run-tests.sh` and to `CLAUDE.md`'s lane list.
- **Migration** (AC3), file by file, each run green before the next. 20 files:
  `test_flow_chat`, `test_flow_streaming`, `test_flow_markdown_chat`,
  `test_flow_chat_image_attach`, `test_flow_chat_thinking_disclosure`,
  `test_flow_chat_visibility_distinction`, `test_flow_chat_peer_attribution`,
  `test_flow_context_overlay_thresholds`, `test_flow_usage_restore`,
  `test_flow_chat_queued_render`, `test_flow_chat_start_recovery`, `test_flow_new_chat`,
  `test_flow_keyboard`, `test_flow_hash_routing`, `test_router_items`, `test_router_core`,
  `test_nav_guard`, `test_oauth_modal_flow`, `test_shell_rail`, `test_visual_snapshots`
  (pixel only; its migrated test passed locally, not a gate). The other three files the
  design review's greps reached need nothing: `test_flow_agents_list.py`,
  `test_agents_library_isolation.py` and `_lists.py` name only Flight 3's
  `agent-select-empty`.
  - Starts became `start_chat`; badge waits after a deep link or reload became
    `expect_chat`; a first send that follows the start became `send_first`. Across the
    20 files that is 45 `start_chat`, 10 `expect_chat` and 20 `send_first` calls. The
    welcome-visible preconditions stay, as `expect(_chats.welcome(page))`.
  - `test_router_items.py`: both chat tests use `chat_frames` (their own `framesent`
    listeners removed, the `json` import with them), `start_chat` for the second chat,
    `chat_row`/`chat_rows`, and `open_chat` for the row click. The `new_session` counts are
    unchanged; leg 3b inverts them.
  - `test_flow_chat_start_recovery.py`: the start is `start_chat(..., timeout=15000)`; the
    drop-first init script and the "exactly two `new_session` sends" assertion stay.
  - `test_router_core.py` reads the id through `current_session_id`.
  - `test_flow_hash_routing.py` checks the session's own row (`chat_row`) for
    `aria-current`, where it checked "a row with `aria-current`".
- **Kept on purpose** (the leg's "some sites remain"):
  - `test_flow_new_chat.py`: `test_welcome_with_agent_shows_listbox` and
    `test_picking_agent_from_welcome_starts_session` pin the welcome listbox, so they keep
    `.chat-welcome-item` (the guard's one allow-listed file). The dropdown test keeps
    `agent-select`. The header test clicks `_chats.new_chat_button(page)`;
  - `test_flow_keyboard.py::test_session_list_shape` keeps `.session-item` and
    `.session-list` (leg 4 rewrites it as `test_chats_list_shape`);
  - `test_shell_rail.py` keeps its `.session-item-title` geometry JS (leg 4);
  - `test_flow_new_chat.py`'s row-delete tests keep `.list-item`/`.list-item-delete`
    (leg 4);
  - `test_flow_chat_image_attach.py`'s two-image test still sends on the button with
    empty text, as its comment requires.
- **The guard** (`tests/test_nav_helper.py`, unit tier), worded after the Flight 3
  retired-selector guard:
  - `CHAT_SEAM_SELECTORS = ("chat-welcome-item", "session-agent-badge")`, left boundary
    only;
  - `test_no_chat_seam_selectors_outside_chats_helper` walks every `tests/browser/*.py`
    string literal (docstrings and comments exempt; JS passed to `evaluate` counts) except
    in `_chats.py`. Test modules and helpers count alike, with no `test_router_*.py`
    exemption. Non-vacuity: it requires the helper modules, more than 50 test files, and
    that `_chats.py` itself names a seam selector;
  - `CHAT_SEAM_ALLOWLIST = {"test_flow_new_chat.py"}`, per file. A listed file that no
    longer names one fails as a stale entry, and a listed file that is missing fails too.
    **Leg 4 empties and removes it** (AC17);
  - `test_chat_seam_guard_self_test` covers the hit, exempt, boundary, seam-module,
    no-router-exemption and stale cases;
  - the literal walk is factored into `_selector_hits(source, filename, pattern)`.
    `find_retired_selectors` now delegates to it, with its behaviour unchanged.
- **Docs.** A `CLAUDE.md` Testing paragraph ("Chats go through `tests/browser/_chats.py`")
  and the chats lane list. `the_one/agents.md` is under `the_one/`, so AC4 keeps it
  unchanged. Its `_lists.py`-style helper note for `_chats.py` falls to leg 3b or 4, which
  edit `agents.md` anyway.

**Grep counts** (`grep -rn --include='*.py' tests/browser`, excluding `_chats.py`; lines /
files, comments and docstrings included):

| Selector or token | Before | After | What remains |
|---|---|---|---|
| `chat-welcome-item` | 45 / 18 | 2 / 1 | `test_flow_new_chat.py`'s two welcome-listbox pins (allow-listed) |
| `session-agent-badge` | 51 / 18 | 0 / 0 | — (the one comment that named it was reworded) |
| `new-chat-btn` | 3 / 2 | 0 / 0 | — (through `new_chat_button` / `start_chat`) |
| `agent-select` | 8 / 4 | 8 / 4 | 7 are Flight 3's `agent-select-empty`; the dropdown testid (`agent-select"`) is 1 / 1 before and after: the dropdown test |
| `.session-item` | 16 / 4 | 5 / 2 | `test_flow_keyboard.py`'s shape test (3 code lines, 1 comment), `test_shell_rail.py`'s `.session-item-title` |
| `session-item` (any) | 24 / 5 | 13 / 3 | the above plus docstrings and comments |
| `new_session` | 12 / 3 | 16 / 4 | `test_router_items.py` (4), `test_flow_chat_start_recovery.py` (6), `test_flow_new_chat.py` (2, a test name and a comment), `test_chats_helper.py` (4, the frame assertions). Leg 3b inverts them |
| `currentSessionId` | 1 / 1 | 0 / 0 | — (through `current_session_id`) |

**Gates** (browser lanes via `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, `-x`, one at a time):

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (502 files formatted; leg 2 was 500, plus `_chats.py` and `test_chats_helper.py`) |
| `test_nav_helper.py` | 72 passed (70 + the two guard tests) |
| `--lane chats` | **44** passed in 99.2s (1m43s wall): leg 1's 42 + `test_chats_helper.py`'s 2 |
| `--lane shared` (`TEST_TIMEOUT=3600`) | **439** passed in 656.9s (11m14s wall): leg 1's 438 + the seeder test |
| `--lane settings` | **178** passed in 334.6s (5m43s wall), unchanged |
| `--lane library` | **146**: 145 passed, 1 skipped in 477.6s (8m10s wall), unchanged. The skip is `test_mcp_test_connection_button.py`'s committed `@pytest.mark.skip` (mission 08 known issue) |
| `--lane agents` | **132**: 130 passed, 2 skipped in 317.8s (5m27s wall), unchanged. The skips are the committed `@pytest.mark.skip` in `test_flow_agent_tabs.py` and `test_flow_studio_openrouter_picker.py`; no agents-lane file changed in this leg |
| `make test-unit` | 5140 passed, 10 skipped, 1576 deselected in 682.4s (11m41s wall): leg 2's 5138 + the 2 guard tests; deselected 1573 + the 3 new browser tests |
| `test_visual_snapshots.py -m pixel -k chat_with_messages` | 2 passed (local only, not a gate) |

The new tests are three: `test_chats_helper.py` (2, chats) and the seeder test (1, shared).
The `contracts` lane (559) was not re-run: none of its files changed.

**Falsifications** (each applied in place with the good file saved to the scratchpad, run,
then restored and `cmp`-checked; grep `FALSIFIED` is empty):
- A raw `.session-agent-badge` in `test_flow_chat.py` failed
  `test_no_chat_seam_selectors_outside_chats_helper` (`test_flow_chat.py:74:
  session-agent-badge`).
- Allow-listing `test_flow_chat.py` (which names no seam selector) failed it as a stale
  entry.
- Dropping `start_chat`'s new-session wait (`_STARTED_JS`) failed
  `test_chats_helper_start_paths_rows_and_frames` (`assert s2`: None). Without the wait,
  the same-agent start returns while the id is still cleared.

**Deviations and decisions** (also in "Deviations" below):
1. **`start_chat` has a third path.** The leg says "the welcome item, or falls back to the
   dropdown". For the open chat's own agent it clicks the header `new-chat-btn`, because a
   real dropdown fires no `change` for the value it already shows. That is the path
   `test_router_items.py`'s second same-agent chat takes.
2. **Helpers beyond the leg's list:**
   - `welcome_item` (exact name; used by `start_chat` and the smoke test);
   - `chat_rows` (`test_router_items.py`'s row counts, so leg 4 changes one body);
   - `agent_badge`.
3. **`send_first` presses Enter where the tests clicked Send.** It is used for the 20 first
   sends that follow a start, so leg 3b's flip lands in its body. Both paths call the same
   `send()`. Today's "reply started" is the user's bubble (`performSend` renders it as it
   sends), with a `>` count wait in case the server ever echoes a second bubble.
4. **`chat_frames` uses Playwright's `framesent`** rather than raw CDP or an init script.
   It is engine-neutral, and it is what `test_router_items.py` already used. The init
   script in `test_flow_chat_start_recovery.py` stays, because it drops a frame rather
   than observing one.
5. **`seed_session`'s `created_at` defaults to `updated_at`**, not to now, so a seeded
   past session is never created after its last update.
6. **New helper tests** in the chats lane (`chats_pat` gains `test_chats_helper.py`).
7. **`the_one/agents.md` not updated** (AC4). `CLAUDE.md` carries the paragraph.
8. **The guard's walk is shared** with the retired-selector guard (`_selector_hits`). That
   is a refactor; Flight 3's behaviour is unchanged and its self-test passes.

**For leg 3b:**
- `start_chat`, `send_first` and `expect_chat` are the bodies to flip. `test_chats_helper.py`
  asserts today's frames (`new_session` x3), so it flips with them.
- **A pre-existing client race, not exercised by any test.** `start_chat`'s "a chat is
  open" path clicks as soon as an id is bound. A start while a cold-load auto-join's
  `session_joined` is still in flight lets that late reply take over, because
  `startSessionWith` nulls `currentSessionId` and the stale-join guard then accepts the old
  id. No test starts a chat during a cold auto-join. Leg 3b's state gating (frames in
  flight) removes it.
- The `new_session` sites listed in the grep table are the ones AC15 and AC18 invert or
  delete.

### Leg 3b: start-flow-client (landed, 2026-10-05)

**What landed.** Chats creates a session on the first send (DD1, DD2), on the **existing**
DOM. Picking an agent is the route `#chats/~new/{agent}`: a *pending* chat, with no session,
that sends only a `leave`. The first Send is one `start_session` with a client id; the first
turn behaves like any turn. A pure state machine gates every inbound frame. Reconnects re-send
while starting and re-join while joined. `new_session` is gone from the client and the server,
which closes squawk 0111.

- **`static/js/areas/chat/session-state.js`** (new; AC1). `App.chat.createSessionState()`:
  no DOM, WebSocket or timers (pinned by a source scan in its test). It has `state()`, the
  transitions `pick`, `openConversation`, `startSend`, `onFrame` and `reset`, and the queries
  `accepts`, `activeId`, `boundId`, `serialize`, `startFrame`, `reconnectAction` and
  `idleRules`. Every transition returns its effects as data, for example `{leave,
  discardHeld, clearPendingJoin, render: 'pending'}`, `{accept, render: 'history'|'keep',
  sync, refreshList, fromStart}`, `{startFailed, error, payload, clientId}` and `{toIdle,
  notice}`. `App.chat.newClientId()` returns 32 hex characters from
  `crypto.getRandomValues`. The `index.html` tag sits before `areas/chat.js`, so the asset
  pin goes 73 to 74.
- **`static/js/areas/chat.js`**, rewired onto it:
  - `currentSessionId` is gone, and so is every "null means idle" check (see the AC4 table
    below).
  - `startSessionWith`, `joinSession`, `pendingStart`, the 10s timer and
    `App.chatStartJoinTimeoutMs` are gone.
  - **New paths.** `requestPick` (every entry point) goes through `App.router.go(href({chats,
    create, agent}))`, with `{replace: true}` from a `~new` route. The hydrate's
    `pickAgent` sends `leave` and shows the pending pane. `startSend` sends `start_session`.
    `applyStartFailed` handles a start failure, and `openConversation` and `runIdleRules`
    handle opening and the idle state.
  - **Hydrate** (`hydrateSession`, `hydrateNew`): it validates the agent and heals a bad
    route.
  - **The `onmessage` gate.** `session_joined` is the only conditional render (AC2).
    `start_failed` and `join_failed` are new handlers. The OAuth popup close runs before the
    gate.
  - **Reconnect** (AC8). `boundOn` records the socket of the last binding. A `starting`
    chat re-sends at `onopen`. A joined or joining chat acts at the first list on the fresh
    socket. `rebinding` holds Send and Stop meanwhile. `onclose` keeps the held slot and
    busy while starting.
  - **The socket itself.** Stale-socket handlers are ignored, and there is a single
    reconnect timer.
  - **Exports.** `_currentSessionId` is now `boundId()`, the joined or joining id.
    `_pendingJoinId` and `_joinSession` keep their meaning. The test seams
    `_sessionState()`, `_serialize` and `_hydrate` are new.
- **`static/js/areas/chat/history-buckets.js`** (AC14). `renderSessionList(..., {pending})`
  adds the pending "New chat" row: `data-pending`, selected, at the top of Today, with no
  delete action, and re-added on every render. The selected row's button now carries
  `.active` on render too, as `highlightActiveSession` marks it.
- **`static/js/router.js`** (AC10). The route `chats/~new/{agent}` is implemented as the
  leg prescribes: `href`, `parse` (a bare `~new` is plain Chats), `resolve` (the area sub
  stays encoded; a bare `~new` and extra segments fold, marked redirected),
  `areaSubToRoute`, and `describeRoute` ("New chat with {agent}", key
  `chats//~new/{enc(agent)}`). The legacy `#chat/new/...` resolves to `#chats`, since the
  route never had a legacy form.
- **`tests/browser/_nav.py`** (AC11). `canonical` folds `chats/~new` to `chats`, and
  `legacy_hash` raises for `chats/~new/...`.
- **`the_one/interfaces/web/app.py`** (AC15). The `new_session` branch is deleted. A stray
  frame now falls into the message path and is a silent no-op. The leftover local in
  `start_session` is renamed `created_session`.
- **Tests.**
  - **New:**
    - `test_flow_chat_session_state.py`: 55 cases, the pure module loaded from disk with no
      app. They cover every AC2 row, the no-op frames, the AC2b idle rules, the AC3 gate in
      every state, a quick A-then-B open with a late `joined(A)`, the abandoned-start list
      refresh, the suppressed auto-join, `serialize`/`activeId` and `reconnectAction`.
    - `test_flow_chat_start_flow.py`: 11 tests on the real chat area:
      - the AC3 frames after a pick (real chunks plus fed frames of every kind);
      - the late cold-load join;
      - AC7, the first turn;
      - AC6 (`/reset`, a closed socket, Stop while starting);
      - `start_failed` restoring the text and the image;
      - AC9 and AC9b;
      - AC12 (hydrate, validate, heal; a re-pick replaces, a first pick pushes).
    - `test_router_announce.py::test_new_chat_route_announces_the_agent_and_the_first_send_sync_is_silent`.
    - `test_router_core.py::test_chats_create_route_contract`, with 3 round-trip specs and 4
      parity rows.
    - `test_nav_helper.py::test_chats_new_route_canonical_and_no_legacy_form`.
    - `test_store_static.py`: `test_start_session_join_refreshes_the_list_that_primes_sessions`
      (AC19) and `test_retired_new_session_path_is_gone_from_the_client` (AC13 and AC20).
  - **Inverted:**
    - `test_flow_chat_start_recovery.py` became `test_flow_chat_start_reconnect.py`, with 4
      tests: the dropped variant (the start never reached the server, with a send in the
      reconnect gap that is held, never a plain message), the reached variant (its
      `session_joined` swallowed), the joined re-join, and the joined session deleted while
      down (idle, no default-agent session).
    - In `test_router_items.py`, the two `new_session` tests are renamed
      `test_two_first_sends_make_two_rows_and_a_row_pushes_and_joins_once` and
      `test_a_first_send_before_a_pending_session_list_creates_exactly_one_session`.
    - In `test_ws_start_session.py`, `test_new_session_still_creates_and_joins` became
      `test_new_session_is_gone_and_creates_nothing`.
  - **The flip** (AC16):
    - `_chats.py`. `start_chat` returns at the pending chat (state `pending`, route
      `chats/~new/{agent}`). `send_first` waits for the join and returns the id.
      `expect_chat` reads the header, which the pending pane sets too. `open_chat` waits
      for `joined`. `chat_rows` excludes the pending row. `session_state` and
      `pending_row` are new.
    - `test_chats_helper.py` now asserts the `start_session` and `leave` frames.
    - **Send-first counts.** In the 19 surviving migrated files, `send_first` went from 20
      to 39 calls (+19):
      - `test_flow_new_chat` +7;
      - `test_router_items` +4;
      - `test_flow_keyboard` +3;
      - one each in `test_flow_context_overlay_thresholds`, `test_flow_hash_routing`,
        `test_router_core`, `test_shell_rail` and `test_oauth_modal_flow`.
    - **Files that pass unchanged.** `test_flow_chat_image_attach.py` (9 starts, then Send)
      and `test_flow_markdown_chat.py` (already a `send_first` per start) pass unchanged:
      a first Send in a pending chat is the `start_session`, images included.
- **Docs.**
  - `the_one/agents.md`:
    - the `_chats.py` note that leg 3a could not add (with the sync-API event-dispatch
      warning);
    - the protocol table's `new_session` row, marked removed;
    - a new "Chat start flow (client)" section (the state table, the gate, the idle rules,
      the route and hydrate, AC9, reconnect, busy/hold/Stop, the interim UI);
    - the router scheme's `chats/~new/{agent}`;
    - the Chats item-history bullet;
    - the invalidation map's `start_session` row.
  - `CLAUDE.md`: the router line and the `_chats.py` paragraph.
  - Squawk 0111: Corrective Action and Verification are written, and the status is
    `completed`, with the sign-off pending at the flight-end review.
  - Squawk 0120 logged (below).

**AC4 null-check sites** (`chat.js` at leg 1's tip; 47 `currentSessionId` uses, 20 of them
null, truthiness or equality checks):

| Site | Old check | Replacement |
|---|---|---|
| `:9` `serializeState` | `this._currentSessionId ? 'sessions/'+id : null` | `chatState.serialize()` (`new/{agent}` while pending or starting) |
| `:15` `hydrateState` | `!id \|\| id === this._currentSessionId` | `hydrateSession`: `chatState.boundId() === id` |
| `:35` `isCurrentBusy` | `currentSessionId && inFlightSessions[currentSessionId]` | `name === 'starting'`, else `activeId()` in the in-flight map |
| `:101` `cancelPendingQueued` | `if (currentSessionId)` | `activeId()` |
| `:484` `startSessionWith` | `if (currentSessionId)` (discard held) | removed; `pick()`'s `discardHeld: activeId()` effect |
| `:589` `joinSession` | `currentSessionId && currentSessionId !== id` | `openConversation()`'s `discardHeld` (the previous `activeId()` when it differs) |
| `:1000` `performSend` | `if (currentSessionId)` | `activeId()` |
| `:1016` `send`, `/reset` | `isReset && currentSessionId` | pending or starting: a notice, never sent; else `activeId()` |
| `:1027` `send`, hold | `if (!currentSessionId) return` | `activeId()` (idle and joining return earlier, by state) |
| `:1059` `refreshAgentsAndSetup` | `!currentSessionId && !welcomeEl.hidden` | `name === 'idle'` |
| `:1061` `refreshAgentsAndSetup` | `setupIncomplete && !currentSessionId` | `name === 'idle'` (pending: `applyComposerState`) |
| `:1117` `handleSystem` "Model loaded." | `currentSessionId && inFlightSessions[...]` | `activeId()` |
| `:1123` `handleSystem` error | same | `activeId()` |
| `:1238` `session_list` auto-join | `sessions.length > 0 && !currentSessionId` | `idleRules()` (idle only; `suppressAutoJoin`) |
| `:1239` `session_list` welcome | `!currentSessionId` | `idleRules().welcome` |
| `:1245` `session_joined` stale guard | `currentSessionId && currentSessionId !== data.session_id` | `chatState.onFrame()` (the AC2 rows) |
| `:1345` `session_deleted` | `currentSessionId === data.session_id` | `onFrame`: the `joined(id)` delete row |
| `:1511` `done` | `var sid = currentSessionId; held = sid ? ... : null` | `activeId()` |
| `:1540` `cancelled` | `if (currentSessionId)` | `activeId()` |
| `:1657` Stop | `if (currentSessionId)` | `activeId()` (and `socketOpen() && !rebinding` first) |

The other 27 uses:
- **Assignments** (`:488`, `:593`, `:1220`, `:1251`, `:1347`) became state transitions.
- **`session_joined`'s per-id writes** (`:1253`, `:1295`, `:1299`, `:1302`, `:1303`) key
  on `data.session_id`.
- **`:392`** (the row highlight) is state-based.
- **`:899`** (`startLoginFlow`'s `chat_session_id`) is `activeId()`.
- **`:1205`** (the `renderSessionList` argument) became `renderList()`, with `boundId()`
  plus the pending option.
- **`:1685`** (the export) is `boundId()`.
- The rest are declarations and comments.

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, `-x`, one at a time):

| Gate | Result |
|---|---|
| Leg start: `--lane chats` on leg 3a's tip | 44 passed in 100.7s (the seam was green) |
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (504 files formatted) |
| Static guards: `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static`, `test_index_asset_cache_busting`, `test_ui_control_inventory`, `test_ui_library_source`, `test_run_tests_lanes` | 398 passed in 3.1s |
| `make test-unit` | 5143 passed, 10 skipped, 1647 deselected in 674.3s (11m14s): leg 3a's 5140, plus `test_nav_helper` +1 and `test_store_static` +2 (the inverted `new_session` unit test is a net 0); deselected +71 = the new browser tests |
| `--lane chats` | **113** passed in 147.9s (2m32s wall): 44 + 55 (`test_flow_chat_session_state`) + 11 (`test_flow_chat_start_flow`) + 3 (the reconnect file's 4 replace the recovery file's 1) |
| `--lane shared` (`TEST_TIMEOUT=3600`) | **441** passed in 659.1s (11m16s wall): leg 3a's 439 + `test_chats_create_route_contract` + the announcer test |
| `--lane agents` | 130 passed, 2 skipped in 317.8s (5m27s wall), unchanged |
| `--lane settings` | 178 passed in 334.8s (5m44s wall), unchanged |
| `--lane library` (no migrated file there; run because `router.js` and `chat.js` are app-wide) | 145 passed, 1 skipped in 477.5s (8m10s wall), unchanged |
| `--lane contracts` (no control changed; run for the router) | 556 passed, 3 skipped in 146.6s (2m31s wall), unchanged |
| Stability: `test_flow_chat_start_reconnect.py` + `test_flow_chat_start_flow.py`, three back-to-back runs | 15 passed each time (51s) |
| WebSocket units: `test_ws_start_session` + `test_ws_build_user_content` + `test_ws_message_branch_crash_guard` | 89 passed |

**Falsifications** (each applied in place with the good file saved to the scratchpad, run,
then restored and `cmp`-checked; grep `FALSIFIED` is empty):
- **AC3, the gate.** `accepts` returned true for session-scoped frames in `pending` too. That
  failed `test_frame_gate[pending]` (`(True, True) == (False, False)`),
  `test_frames_after_a_pick_are_dropped_and_a_late_joined_keeps_pending`, and
  `test_frames_from_the_previous_session_never_reach_a_pending_chat`. In the last, the pane
  showed "LEAK user… LEAK chunk… Log in to LEAK auth".
- **AC8, the dropped-send variant.** `onopen` re-sent nothing while starting:
  `test_start_session_that_never_reached_the_server_is_resent_on_reconnect` failed (it never
  joined). With a `join(cid)` re-sent instead, it fails the same way, deterministically: the
  server answers `join_failed` for the unknown id, so the chat stays starting.
- **AC9, the rail restore.** With the `startedFrom` rule disabled,
  `test_leaving_chats_while_starting_and_coming_back_keeps_the_session` failed. The route
  stayed `chats/~new/test-agent`: a new pending chat.
- **AC19, the store row.** With the join's `refreshSessionList()` dropped,
  `test_start_session_join_refreshes_the_list_that_primes_sessions` failed. Its assertion
  was then made explicit ("the accepted session_joined path must refresh").

**Manual check.** On a dev instance on 8486 with a scratch data dir and dev mode
(`/proc/<pid>/environ` verified), a mock provider and two agents, driven with headless
Chromium:
- **Pick.** The hash was `#chats/~new/Manual%20Alpha`, the state `pending`, and the pending
  row read "New chat · Manual Alpha". `GET /api/chat/sessions` returned 0. No frame was
  sent (nothing was bound).
- **Send.** The hash became `#chats/{id}` and the API returned 1 session; the only frame
  sent was `start_session`.
- **Rail away and back while starting** (`session_joined` held 1.5s). Away, `lastRoute`
  stayed `chats/~new/Manual%20Alpha`. Back, the hash was `#chats/{the new id}` and the
  state `joined` from that start, with 2 sessions in all and the second chat's bubble kept.

The instance was stopped with `make down`, and its log removed.

**Deviations and decisions** (the Flight Director should review; also in "Deviations"
below):
1. **`idleRules(list, pendingJoinId)`** takes `pendingJoinId` as a second argument. It
   lives in `chat.js`, behind its export, so the module stays pure.
2. **`reconnectAction` moves the state itself** (joined or joining to `joining(id)` or
   `idle`), although AC1 lists it as a query. That keeps the transition in the table.
3. **The API has additive parts:**
   - `boundId()` (backs `_currentSessionId`);
   - `startFrame()`;
   - effects carry `frame` and `id`;
   - `App.chat.newClientId()`.
4. **A heal resets only a pending chat.** AC12 says `state.reset()`, then
   `sync('chat', null)`. A joined or starting conversation is left alone for a bad
   `~new` URL, and the router's post-hydrate sync re-canonicalises to it. Resetting would
   drop a live conversation, or abandon a start, because of a typo.
5. **A loaded agents cache that lacks the agent is revalidated through
   `App.store.get('agents')`** (which refetches a stale cache) before it heals, with the
   chat pending behind a neutral pane. Healing at once would wrongly heal an agent created
   since the cache loaded (studio invalidates on create). An agent listed in the peeked
   cache still picks at once, as AC12 says.
6. **Entry points set a one-shot `pickIntent`.** As written, AC9's rail-restore rule would
   also swallow the header New Chat after a first send: the hydrate of `~new/{agent}`
   while `joined(id)` with `startedFrom` matching. A deliberate pick is therefore always a
   pick (pinned at the end of the AC9 test).
7. **Send in `idle` or `joining` returns early and keeps the text.** This is not in the AC.
   An unbound socket, or a join that turns into `join_failed`, would otherwise auto-create
   a default-agent session.
8. **The idle notice** ("That conversation no longer exists") is a `role=status`
   paragraph on the welcome canvas, built with DOM APIs, since the chrome is hidden while
   idle. Pending and joined notices go into the message log. No new testid.
9. **`renderHistory` and the pending pane reset the streaming-bubble pointer.** A stale
   pointer to a detached bubble would swallow the next conversation's first chunk. That
   gap predates this leg; the reconnect re-join made it reachable.
10. **The socket.** `connect()` ignores a superseded socket's events, closes a superseded
    socket on open, and keeps one reconnect timer, so `activate()` during a reconnect gap
    no longer opens a second socket.
11. **`history-buckets.js` marks the selected row's button `.active` on render**, as the
    highlight does. The inverted router test found it: `open_chat` now waits for the join
    reply, so the list re-render won the race against the class check.
12. **Integration tests live in a new `test_flow_chat_start_flow.py`**, in the chats lane
    through `test_flow_chat*`. It is not in the leg's file list, and it keeps the reconnect
    file to AC8.
13. **Squawk 0120 logged.** A `cancel` that the server processes before the spawned turn's
    first step gets no `cancelled` (or `done`), so the client stays busy. A task cancelled
    before it starts never enters its `except CancelledError`. This predates the flight:
    the plain `message` path is the same. "Stop while starting" therefore clicks once the
    server has created the session; the cancel is still sent while the client is
    `starting`, ordered after `start_session`.
14. **The test harness for frame delays holds every frame behind a held `session_joined`.**
    A delay that reorders frames would be an artefact, since the server never reorders a
    socket's frames: the turn's frames would arrive while starting and be dropped. The
    existing `test_router_items.py` delay script keeps its reordering; that test asserts
    only rows and frames.

### Leg 4a: chats-sidebar-and-picker (landed, 2026-10-05)

**What landed.** The Chats list column has its board shape (§5.1, DD5) and New chat opens the
agent picker (§5.6, DD4, A16). The sidebar is DOM-built; the dropdown, the old history list and
the sidebar sink are retired. The pane (welcome canvas and its agent list, the header
`h2.session-agent-badge` and `new-chat-btn`, the composer, the content sink) is untouched for
4b, and so is the `CHAT_SEAM_*` guard.

- **`static/js/areas/chat/chats-list.js`** (new; `App.chat.chatsList`). `create({onNew,
  onDelete})` builds an `App.ui.listPane` (testid `chats-list`, title "Chats", `rowStyle:
  'chats'`, no filter, `emptyText` "No conversations yet.") whose `block` is the New chat button
  (`App.ui.button` primary `lg`, the `square-pen` icon node, testid `chats-new-btn`); it returns
  `{el, newButton, render(rows, view), setNewDisabled, destroy}`. `groups(rows, view, onDelete,
  now)` buckets by local `updated_at || created_at` (whole calendar days, rounded for DST: 0 or
  future Today, 1 Yesterday, 2-6 Last 7 days, 7-29 Last 30 days, 30+ / missing / invalid
  Older), newest first (stable sort), empty groups dropped, the pending row first in Today.
  `timeFor` is hand-formatted (`HH:MM`, `Mon`, `Sep 12`, `''`). Rows: the title (`Untitled
  chat` if empty), the agent or "Default agent", a connector's platform as a plain-string badge,
  `href` `#chats/{id}`, `dataset {id}`, testid `chat-row`, and the delete action (trash,
  "Delete chat: {title}", `chat-row-delete`). The pending row: id `__pending__`, "New chat",
  "now", the agent, `href` `#chats/~new/{agent}`, `dataset {pending:'true'}`, no action.
- **`static/js/areas/chat/agent-picker.js`** (new). `App.chat.openPicker({opener})` (a Promise:
  `go(href chats)` first from another destination, rejecting on a Stay; queued until
  `App.chat.registerPickerHost`, which the chat area calls last in `init`; inert with setup
  incomplete; a second call focuses the open picker). The picker is built fresh per open:
  `App.ui.searchList` (`agent-picker-search`, `agent-picker-row`, `dataset {agent}`, the
  provider dot as `lead`) in an `App.ui.modal` chooser (`agent-picker`, 640 at top 72,
  dismissible, "Start a chat with…", the "Esc" `agent-picker-close`, `initialFocus` the input,
  the fragment footer). Groups: Recently used (5; latest `updated_at` over sessions with no
  platform and a live agent) then All agents A-Z, or "{n} matching" A-Z over name, model, type
  slug and description; `No agents match "{q}".`, "Loading agents…", "No agents yet.". A pick
  closes the modal and runs `onPick(agent, {opener})` from `onClose`.
- **`static/js/areas/chat.js`.** The sidebar sink, `agentSelect`, `syncDropdownToCurrent`, the
  dropdown `change` handler, `highlightActiveSession`, `renderList` and `sessionCallbacks` are
  gone. One `renderChatsList()` reads `App.store.peek('sessions')` plus the state; it runs from
  `App.store.subscribe('sessions', ...)` (never released: the area is never destroyed, a comment
  says so) and from `renderPending`, `openConversation`, the accepted `session_joined`,
  `resetToIdle` and `clearConversation`. The `session_list` handler only primes. `requestPick`
  takes `{opener}` into `go`. `refreshAgentsAndSetup` disables New chat while setup is
  incomplete. The header button keeps working (current agent, else the first agent).
- **`history-buckets.js` deleted**; `index.html` -1 +2 tags (the asset pin 74 to 75).
- **CSS.** `base.css`: `#app-sidebar[data-destination="chats"]` joins the `--list-w` and
  padding-top-zero rules; the default aside width is `--list-w`; the 1279px media rule and
  `--sidebar-w` (both themes, `tokens.css`) are removed (nothing else used them;
  `test_token_definitions` green). `chat.css` loses the sidebar rules (`#sidebar-header`,
  `.sidebar-actions`, `.agent-select`, `.session-list*`, `.session-group*`, `.session-item*`)
  and gains the list host (`.sidebar-panel.area-chat > .ui-list-pane`) and the picker body
  (`.agent-picker-body`, not area-scoped: the `<dialog>` is under `<body>`). `components.css`
  keeps `.list-item-delete` and `.list-item.confirm-delete` (the surfaces demo) and gains the
  chats-style scroller hairline (§5.1's separator).
- **Retirement and selectors** (AC13, AC14). `tests/test_ui_guards.py`'s baseline drops the
  `areas/chat.js` sidebar entry and `history-buckets.js` (the content entry stays for 4b). The
  registry's Retired table gains `agent-select`; the live table gains `agent-picker`,
  `agent-picker-close`, `agent-picker-row`, `agent-picker-search`, `chat-row`,
  `chat-row-delete`, `chats-list` and `chats-new-btn`. `tests/test_nav_helper.py`:
  `RETIRED_SELECTORS` gains `session-item`, `session-list`, `session-group` and
  `list-item-delete`; `RETIRED_EXACT = ("agent-select",)` compiles as
  `(?<![\w-])agent-select(?![\w-])` into the same `_RETIRED_RE`; the coverage test checks the
  union; the self-test gains the new cases; `test_retired_exact_spares_the_live_agent_select_empty`
  pins `agent-select-empty`.
- **Test seam.** `_chats.py`: `start_chat` waits for the area to settle, then `pick` (New chat,
  type, ArrowDown to the exact agent if the A-Z order puts another match first, Enter) and
  returns at pending, as in 3b. New helpers: `chats_new_button`, `open_picker`, `pick`,
  `picker`, `picker_search`, `picker_rows`, `picker_row`, `chat_row_delete`. `chat_row` /
  `chat_rows` / `pending_row` / `open_chat` use `chat-row[data-id]` / `[data-pending]`.
  `_lists.py` gains `"chats"` (rows by exact title).
- **Docs.** `CLAUDE.md` (a "Chats list and agent picker" paragraph; the App shell widths; the
  `_chats.py` paragraph; the retired selectors), `the_one/agents.md` (a new "Chats list and
  agent picker (client, M25 F4 L4a)" section; the route bullet; the interim-UI bullet; the
  `_chats.py` note; the retired-selector note; the shell widths and padding; the token and
  section-title notes), the inventory (the chat history row → `library: App.ui.listPane`; an
  agent-picker composition row; the list pane, search list and modal rows) and the registry.

**Old to new test names** (every removed or renamed test):

| Old | New | How |
|---|---|---|
| `test_flow_new_chat.py::test_dropdown_change_starts_new_session` | `test_picker_pick_of_another_agent_starts_new_chat` | replaced: New chat, type, Enter; also pins the frames (`start_session`, `leave`) |
| `test_flow_new_chat.py::test_chat_history_today_group_renders` | `test_chats_list_title_and_today_group_render` | re-pinned on the listPane title "Chats" and the "Today" caption (pending, then session row) |
| `test_flow_new_chat.py::test_session_delete_confirm_lapse_is_visually_distinct` | (same name) | re-pinned on the listPane `<li>` (`.confirm-lapsed`), through `chat-row-delete`; waits for the reply so no list refresh lands mid-arm |
| `test_flow_new_chat.py::test_delete_last_session_returns_to_welcome` | (same name) | through `chat-row-delete` (it named `.list-item-delete`, now retired); 4b keeps it |
| `test_flow_keyboard.py::test_session_list_shape` | `test_chats_list_shape` | the listPane `<section>`/`<ul>`/`<li>`/`<a>` and the action `<button>`; Tab row → action → out |
| `test_flow_keyboard.py::test_session_delete_keyboard_reveal` | `test_chat_row_delete_keyboard_reveal` | re-pinned on `chat-row-delete`; adds Enter arms in place |
| `test_shell_rail.py::test_shell_geometry_at_supported_widths[1024-768-200 / 1279-800-200 / 1280-800-240 / 1440-900-240]` | `...[1024-768 / 1279-800 / 1280-800 / 1440-900]` | renamed and inverted: Chats is 300 at every width |
| `test_shell_rail.py::test_aside_data_destination_follows_every_commit` | (same name) | `expect_state("chats", 240)` twice → `LIST_W` |
| `test_shell_rail.py::test_settings_nav_labels_and_chat_rows_do_not_clip_at_1024` | (same name) | `.session-item-title` → the `chat_row`'s `.ui-list-pane-label` |
| `test_store_static.py::test_chat_session_list_primes_sessions_in_the_summary_shape` | (same name) | its tail inverted: the handler renders nothing (no `renderList`/`renderSessionList` anywhere) |
| `test_router_items.py::test_two_first_sends_make_two_rows_and_a_row_pushes_and_joins_once` | (same name) | the row-selected check `to_have_class(/\bactive\b/)` → `aria-current="page"` on the opened row, absent on the other (found by the first shared run) |

Also moved without a rename: `test_flow_chat_start_flow.py`'s two dropdown `select_option` calls
→ `_chats.pick` (the cold-join test picks while `joining`, so it cannot use `start_chat`'s
settle wait). `test_router_items.py` had no `.session-item` left after 3a, but its AC6 test pinned the old row's `.active` class (see the table).
`test_chats_helper.py`: comments only.

**New tests.**
- `test_flow_chat_list.py` (8): groups and boundaries (days 0, 0, 1, 2, 6, 7, 29, 30, 400;
  sentence case; times; the REST round trip honours `updated_at`; missing, invalid and future
  dates through `App.chat.chatsList`), cross-agent rows, "Default agent", the connector badge
  (class `ui-list-pane-badge` only), the selection; the pending row (a link, `aria-current`,
  no action, no `data-id`) through the first send and an open; row delete (arm, confirm, focus
  to the next row); off-Chats REST fetches (AC6); empty; setup incomplete (disabled, an inert
  `openPicker`, enabled after setup); 300px with a full-width 36px New chat at 1024 and 1440.
- `test_flow_chat_picker.py` (7): open (title, Esc button, label, footer, 640 × top 72, focus),
  no match, Escape / close button / backdrop with focus back, a fresh query per open; Recently
  used (connector, deleted-agent and default sessions excluded; the cap) and All agents A-Z;
  matching on description, type slug (case-insensitive), model, name, trimmed, not the
  provider's display name; Enter picks (`~new/Alpha`, a push), a re-pick replaces
  (`history.length` unchanged), no frames; a guard Stay (the picker closed first, focus on New
  chat, route unchanged); `openPicker` from a cold area on Agents (a Stay rejects, a clean move
  opens); provider dots (`badge--ollama`, `badge--mock`, `badge-dot--none`).
- `test_nav_helper.py` +1 (`test_retired_exact_spares_the_live_agent_select_empty`);
  `test_store_static.py` +1 (`test_chats_list_renders_from_the_sessions_subscription_only`).

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, `-x --timeout 60`, one at a time):

| Gate | Result |
|---|---|
| **Mid-leg gate (AC17)**: `--lane chats` after the sidebar swap, before the new flow tests | **113** passed in 151.2s (2m31s): 3b's 113, unchanged (the replaced and re-pinned `test_flow_new_chat.py` tests are one-for-one) |
| Mid-leg spot check: `test_flow_keyboard.py` + `test_shell_rail.py` (shared lane files) | 24 passed in 58.5s |
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (506 files formatted) |
| Static guards: `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static`, `test_index_asset_cache_busting` (75), `test_ui_control_inventory`, `test_ui_library_source`, `test_run_tests_lanes` | **400** passed in 3.4s (3b's 398 + `test_nav_helper` 1 + `test_store_static` 1) |
| `make test-unit` | **5145** passed, 10 skipped, 1661 deselected in 694.6s (11m34s wall 717s): 3b's 5143 + 2; deselected +14 (the new browser tests collected at that point; the eighth list test was added during the run) |
| `--lane chats` | **128** passed in 180.1s (3m07s wall): 113 + `test_flow_chat_list.py` 8 + `test_flow_chat_picker.py` 7 |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`; `components.css` changed) | **556** passed, 3 skipped in 156.9s (2m42s wall), unchanged; the 3 are the in-test WebKit forced-colors skips (a WebKit launch failure fails under `REQUIRE_WEBKIT`) |
| `--lane agents` | 130 passed, 2 skipped in 318.2s (5m27s wall), unchanged (the committed skips) |
| `--lane settings` | 178 passed in 342.7s (5m53s wall), unchanged |
| `--lane library` | 145 passed, 1 skipped in 478.9s (8m12s wall), unchanged (the committed skip) |
| `--lane shared` (`TEST_TIMEOUT=3600`), first run | 1 failed, 360 passed: `test_router_items.py::test_two_first_sends_make_two_rows_and_a_row_pushes_and_joins_once` pinned the old row's `.active` class (deterministic; the listPane marks selection with `aria-current` only). Re-pinned on `aria-current="page"` (and the other row's absence of it) |
| `--lane shared` (`TEST_TIMEOUT=3600`), re-run | **441** passed in 657.9s (10m57s), as 3b (renames are one-for-one) |

**Falsification.** With the connector exclusion dropped from Recently used (`if (!s || s.platform)
continue;` → `if (!s) continue;`), `test_recently_used_and_all_agents` failed: Recently used read
`['Bravo', 'Golf', 'Delta', 'Alpha', 'Echo']` (the Discord session's agent at second place)
instead of `['Bravo', 'Delta', 'Alpha', 'Echo', 'Foxtrot']`. Restored from the scratchpad copy
(`cmp` clean, grep `FALSIFIED` empty) and green.

**Manual pass.** A dev instance on 8486 with a scratch data dir and dev mode
(`/proc/<pid>/environ` verified), 32 agents over a mock and an ollama provider, and nine sessions
(today ×2, yesterday's Discord session, 3, 5, 9, 20, 45 days with a default agent, 400 days),
driven with headless Chromium at 1440×900 and 1024×768 in dark and light: the aside 300px, the
five groups, the times, the connector badge, the selected auto-joined row; the picker 640 wide at
y 72 (713px tall at 1440, 680 at 1024), Recently used excluding the Discord session's agent,
"16 matching" for `oll`; ArrowDown + Enter → the pending row selected at the top of Today with
focus back on New chat; hover reveals the trash action. No console errors, no horizontal scroll.
Stopped with `make down`; its pid and log removed.

**Deviations and decisions** (also in "Deviations" below):
1. **The chats-style scroller hairline** (§5.1's separator under the New chat block) is a
   `components.css` rule on `.ui-list-pane-style-chats .ui-list-pane-body`, a library CSS
   change (the contracts lane re-ran with WebKit).
2. **`requestPick(agent, opts)`** passes the picker's opener to `go`, so a guard Stay returns
   focus to New chat explicitly (the dialog would otherwise fall back to `activeElement`, the
   same element today).
3. **The reconnect re-join no longer renders the list**: `joined(id)` → `joining(id)` keeps the
   same selection and the prime has just rendered, so the `session_list` handler renders nothing
   itself (AC6's "never from both", pinned).
4. **`emptyText` "Loading agents…"** while the agents store has not loaded (not in AC10).
5. **The picker refreshes only the stores not loaded at open** (a loaded cache renders at once;
   a redundant refresh would reset the active row), and only peeks `sessions` (the WebSocket
   primes it on Chats; no REST fetch).
6. **API beyond the leg's list**: `App.chat.registerPickerHost`, `App.chat.chatsList` (`groups`,
   `bucketFor`, `timeFor`, `PENDING_ID`) and `App.chat.agentPicker` (`source`, `recentAgents`).
7. **`_chats.pick`** (open, type, ArrowDown to the exact agent, Enter; no waits) is separate
   from `start_chat` (settle, `pick`, pending), because the cold-join test must pick while
   `joining`.
8. **Three more tests than the leg listed changed now**: `test_delete_last_session_returns_to_welcome`
   (4b's list) and `test_flow_keyboard.py::test_session_delete_keyboard_reveal`, because both
   named `.list-item-delete`, which AC14 retires in 4a; and `test_router_items.py`'s AC6 test,
   which pinned the old row's `.active` class (the listPane marks selection with
   `aria-current` only; found by the first shared run).
9. **No provisional row** between the starting-to-joined swap and the list refresh: for one
   round trip no row is selected (the pending row goes, the session's row arrives with the
   refresh's `session_list`).
10. **`--sidebar-w` removed** (both themes) with the 1279px media rule; the default aside width
    before the first commit is `--list-w`.
11. **The picker body is capped at 624px** so the card stays within the board's 720px; the
    search field is 40px at 14px (§5.6).
12. **Stale copy fixed**: the dead `.session-list-empty` rule, the typography demo's quiet-label
    note and `components.css`'s section-title comment (both named the retired sidebar label).

**For leg 4b:**
- The content sink, the welcome list (`welcome_item`, the `CHAT_SEAM_ALLOWLIST` file
  `test_flow_new_chat.py`'s two welcome-listbox tests), the header `new-chat-btn`
  (`new_chat_button`, used by `test_flow_chat_start_flow.py`'s AC9 test and
  `test_header_new_chat_button_starts_session_with_current_agent`) and `h2.session-agent-badge`
  (`expect_chat`, `agent_badge`) are untouched.
- `_chats.chats_new_button` is the list's New chat; AC11's `new_chat_button` →
  `chats-new-btn` can delegate to it.
- `App.chat.openPicker({opener})` is ready for "Pick a different agent" and the empty state's
  New chat.

### Leg 4b: chats-pane (landed, 2026-10-05)

**What landed.** The Chats detail pane has its board shape (§5.2, §5.4; DD3, DD6, A20): the
chat header with an `h1` and "with {agent}", the new-chat state, and the empty and guidance
states under one "Hello." `h1`. The pane and the composer are DOM-built: the chat area's last
HTML-string sink is gone. The welcome's agent list, the header's `new-chat-btn` and
`h2.session-agent-badge` are retired, and leg 3a's chat-seam guard is replaced by
`RETIRED_SELECTORS` entries.

- **`static/js/areas/chat/chat-pane.js`** (new; `App.chat.chatPane`; `welcome.js` folded in and
  deleted). `create({onNewChat, onPickDifferent})` builds, once:
  - **the welcome** (`div.chat-welcome`, testid `chat-welcome`, kept): the "Hello."
    **`h1.chat-welcome-greeting`**, the idle notice (`p.chat-welcome-notice`, the only
    `role=status`), the prompt, a guidance slot and an actions row; the mascot is prepended
    by `chat.js`. `renderWelcome(setup)`: setup complete is the empty state (the prompt "Start
    a conversation with one of your agents." and **New chat**, `App.ui.button` primary with
    the square-pen icon, testid `chat-empty-new-btn`); incomplete is the guidance (prompt
    hidden, `guidance(setup)` with the former `welcome.js` copy and router hrefs, no New
    chat).
  - **the chrome** (`div.chat-chrome`, kept): the **header** (`header.chat-header`, testid
    `chat-header`, hidden while idle) with **`h1.chat-header-title`** and
    `span.chat-agent-line` (testid `chat-agent-line`, "with {agent}", "Default agent" for
    null); the **new-chat state** (`div.chat-new-state`, testid `chat-new-state`): a
    `badge badge--{kind}` whose text is the model, the agent `h2`, the description, and
    **Pick a different agent** (`App.ui.button` ghost `sm`, testid
    `chat-pick-different-btn`); then the message log.
  - Renderers patch those nodes (`renderHeader`, `renderNewState`, `renderWelcome`,
    `setNotice`); nothing is rebuilt, so a store notification never drops focus.
    `agentInfo(name, agents, providers)` resolves the badge kind through 4a's
    `providerType` (now exported as `App.chat.agentPicker.providerType`), `unknown` for a
    type outside `App.ui.badge.KINDS`, no provider or an unknown agent.
- **`static/js/areas/chat/composer.js`** (new; `App.chat.composer.create()` ->
  `{el, input, fileInput, attachBtn, stopBtn, sendBtn, attachmentsEl, attachmentsStatusEl}`):
  a pure DOM builder, today's markup carried over (testids, classes, `hidden`,
  `aria-keyshortcuts`, the attachments row's inline `display:none` and its footgun comment;
  the Stop icon is `App.ui.util.icon('stop')`, a new `icons.js` entry holding the former
  inline SVG). `el` is `.input-area`; `chat.js` places the attachments row, its status, the
  telemetry overlay and the queued region before it, in the old order, and uses the returned
  references (the `content.querySelector` lookups are gone, `setSessionHealth`'s included).
- **`static/js/areas/chat.js`.** The content sink, `welcomeListEl`, the welcome keydown
  handler, `applyAgents`/`availableAgents`, `updateAgentBadge`/`agentBadgeEl` and the header
  button's handler are gone. A new **`renderPane()`** maps the state onto the pane: pending
  and starting read "New chat" with "with {agent}" (the agent line blank while a cold `~new`
  validates; the new-chat state empty then); joining and joined read the title **from the
  `sessions` store by id** (`sessionRow`), else the `session_joined` payload's
  (`joinedTitle`), else "Untitled chat", with the agent likewise; idle hides the header. The
  chrome carries `.chat-chrome--new` while pending. It runs from `renderPending`,
  `openConversation`, `resetToIdle`, `clearConversation`, `startSend`, `applyStartFailed`,
  `finishValidation`, the accepted `session_joined`, and the `sessions`, `agents` and
  `providers` subscriptions (never released). `openConversation` shows the chrome at once (no
  welcome while joining). `refreshAgentsAndSetup` re-renders a welcome already shown and no
  longer SHOWS it while idle: only the idle rules do (idle with no chat to auto-join).
- **CSS.** `chat.css` loses `.header`, `.session-agent-badge`, `.new-chat-header*`,
  `.chat-welcome-list` and `.chat-welcome-item*`; it gains `.chat-header` (48px, a hairline,
  `0 16px 0 24px`), `.chat-header-title` (13px/600, ellipsis), `.chat-agent-line` (12px
  `--fg-muted`), the new-chat state (centred, inner max 480px, gap 8px; `h2` 18px/600; the
  description 14px `--fg-secondary`; the button 8px above), `.chat-chrome--new .messages`
  (`flex: 0 1 auto`, no padding when `:empty`) and `.chat-welcome-actions`. `components.css`
  had no `.new-chat-header` rule, only a page-header comment naming it; the comment is updated.
- **`index.html`**: `welcome.js` out, `composer.js` and `chat-pane.js` in (the asset pin
  75 -> 76).
- **The sinks (AC8).** `DYNAMIC_SINK_BASELINE` has no `areas/chat*` entry. The two static
  literals were **converted** (trivial two-span builds): the model-loading row
  (`loadEl.innerHTML`) and the thinking indicator (`thinking-indicator.js`). The `= ''` clears
  are **left alone**. `test_ui_guards.py::test_chat_area_has_no_baselined_sink` pins all
  three facts.
- **Retirement and selectors (AC9, AC10).** The registry's Retired table gains `new-chat-btn`;
  the live table gains `chat-agent-line`, `chat-empty-new-btn`, `chat-header`,
  `chat-new-state` and `chat-pick-different-btn` (and describes `chat-welcome`).
  `RETIRED_SELECTORS` gains `new-chat-btn`, `chat-welcome-item`, `chat-welcome-list` and
  `session-agent-badge`, with a comment that the kept `chat-welcome` testid and its other
  `chat-welcome-*` classes are not retired. The whole `CHAT_SEAM_*` block (the selectors, the
  allow-list, `find_`/`check_chat_seam_selectors`, the guard, its self-test and the
  stale/missing checks) is removed; the retired-selector self-test gains the new cases (the
  kept welcome classes pass, `_chats.py` is not exempt), and the browser walk asserts it covers
  `_chats.py`.
- **Test seam.** `_chats.py`: `expect_chat(page, agent, title=None)` reads `chat-header`
  (visible) and `chat-agent-line` ("with {agent}"), and the `h1` given a title;
  `new_chat_button` returns the list's `chats-new-btn`; `welcome` stays; `welcome_item` and
  `agent_badge` are removed; new `chat_header`, `chat_title`, `chat_agent_line`,
  `new_chat_state`, `pick_different_button` and `empty_new_button`. `pending_row`,
  `chat_row(s)`, `chat_row_delete`, `open_chat` and `pick` are unchanged from 4a (checked).
  The module docstring is current, and it names no retired selector outside docstrings.
- **Docs.** `CLAUDE.md` (a "Chats pane" paragraph with the five testids and `composer.js`; the
  `_chats.py` paragraph; the retired selectors), `the_one/agents.md` (a new "Chats pane
  (client, M25 F4 L4b)" section; the start-flow route, neutral-pane, interim-UI and table
  rows; the `_chats.py` and retired-selector notes; the inset-ring list), the inventory (the
  composer row; a chat-pane composition row) and the registry.

**Old to new test names** (every removed, replaced or re-pinned test):

| Old | New | How |
|---|---|---|
| `test_flow_new_chat.py::test_welcome_with_agent_shows_listbox` | `test_welcome_with_agent_shows_the_empty_state` | replaced: the "Hello." `h1`, the prompt, New chat (`btn-filled-primary`), no guidance, no listbox, no header |
| `test_flow_new_chat.py::test_picking_agent_from_welcome_starts_session` | `test_empty_state_new_chat_opens_the_picker_and_starts_a_chat` | replaced: the empty state's New chat opens the picker (focus in search, Escape back to it), a pick is the pending chat (header, new-chat state), the first send hides the new-chat state |
| `test_flow_new_chat.py::test_header_new_chat_button_starts_session_with_current_agent` | `test_pick_a_different_agent_re_picks` | replaced: "Pick a different agent" opens the picker (Escape back to it); a pick replaces the `~new` route (`history.state.seq` unchanged), no frames; the first send is one `start_session` for the new agent |
| `test_flow_new_chat.py::test_welcome_no_setup_shows_both_links` | (same name) | greeting asserted as `h1.chat-welcome-greeting` "Hello."; prompt still hidden (AC5); no `chat-empty-new-btn` |
| `test_flow_new_chat.py::test_welcome_provider_only_shows_studio_link` | (same name) | the same three additions |
| `test_flow_new_chat.py::test_delete_last_session_returns_to_welcome` | (same name) | through the row action (since 4a); now also the empty state's New chat |
| `test_flow_chat_start_flow.py::test_leaving_chats_while_starting_and_coming_back_keeps_the_session` | (same name) | the header New Chat (around 394) -> `_chats.pick(page, agent)` (the list's New chat, the same agent) |
| `test_flow_chat_start_flow.py::test_new_chat_route_hydrates_and_heals` | (same name) | comment only: the welcome checks (around 429, 436) hold under the idle rules (idle, nothing to auto-join: the empty state) |
| `test_flow_chat.py::test_chat_message_log_has_live_region` | (same name) | the log is attached in pending (zero height under the new-chat state) and visible after the first send; found by the first chats run |
| `test_chats_helper.py::test_chats_helper_start_paths_rows_and_frames` | (same name) | `welcome_item` -> the empty state's New chat and `new_chat_button` = `chats-new-btn`; `expect_chat` with a title |
| `test_nav_helper.py::test_chat_seam_guard_self_test` | `test_retired_selector_guard_self_test` | removed; its cases joined the retired-selector self-test |
| `test_nav_helper.py::test_no_chat_seam_selectors_outside_chats_helper` | `test_no_retired_selectors_in_browser_tests` | removed; the retired-selector walk covers `_chats.py` |

`test_flow_context_overlay_thresholds.py` is unchanged (`.chat-chrome` kept).

**New tests.**
- `test_flow_chat_pane.py` (8, chats lane): the header in idle (hidden), pending, starting
  (behind a held `session_joined`), joined (the title follows the auto-title; a store prime
  changes the title and agent at once; a null agent reads "Default agent"), its geometry
  (`HEADER`, 48px, `1px solid`, `0px 16px 0px 24px`, 13px/600, 12px in `--fg-muted`); joining
  (the store's title, the welcome never shown across a cold auto-join, a MutationObserver
  count of 0; then from the empty state an auto-join hides the welcome at once); the
  new-chat state (badge text = model `llama3.1:8b`, `badge badge--ollama`, `--mock`,
  `--unknown` for no provider, `agentInfo`'s unknown-type fallback, the `h2`, the
  description in `--fg-secondary` and hidden when empty, the button's classes, 480px centred,
  the re-pick); a start failure's error under the new-chat state; the empty state; the
  guidance state; one visible `h1`, the landmarks (one `main`, the skip link, no banner) and
  the resolver in guidance, empty, pending and joined; the composer's carried-over markup.
- `test_ui_guards.py` +1 (`test_chat_area_has_no_baselined_sink`).

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, `-x --timeout 60`, one at a time):

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (507 files formatted) |
| Static guards: `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static`, `test_index_asset_cache_busting` (76), `test_ui_control_inventory`, `test_ui_library_source`, `test_run_tests_lanes` | **399** passed in 2.8s (4a's 400 − the 2 chat-seam tests + `test_chat_area_has_no_baselined_sink`) |
| `make test-unit` | **5144** passed, 10 skipped, 1670 deselected in 658.2s (10m58s): 4a's 5145 − 2 + 1 |
| `--lane chats`, first run | 1 failed, 3 passed: `test_flow_chat.py::test_chat_message_log_has_live_region` asserted the log VISIBLE in a pending chat (deterministic; it is zero height under the new-chat state, deviation 4). Re-pinned: attached while pending, visible after the first send |
| `--lane chats`, re-run | **136** passed in 197.1s (3m23s wall): 4a's 128 + `test_flow_chat_pane.py` 8 (the three replaced `test_flow_new_chat.py` tests are one-for-one) |
| `--lane shared` (`TEST_TIMEOUT=3600`) | **441** passed in 674.4s (11m14s), as 4a |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`; no `ui/` file changed, run because `components.css` was touched, a comment only) | **556** passed, 3 skipped in 145.3s (2m31s wall), unchanged; the 3 are the in-test WebKit forced-colors skips |
| `--lane agents` | 130 passed, 2 skipped in 318.5s (5m28s wall), unchanged (the committed skips) |
| `--lane settings` | 178 passed in 335.4s (5m45s wall), unchanged |
| `--lane library` | 145 passed, 1 skipped in 478.2s (8m12s wall), unchanged (the committed skip) |
| Stability: `test_flow_chat_pane.py` alone | 8 passed, three runs (19.9s, 20.0s, 20.0s) |

**Falsification (A20).** With the new-chat badge rendering the provider type instead of the
model (`badge.textContent = view.kind`), `test_new_chat_state_shows_the_model_badge_name_description_and_re_picks`
failed: `Locator expected to have text 'llama3.1:8b'`, actual `ollama`. Restored from the
scratchpad copy (`cmp` clean, grep `FALSIFIED` empty) and green.

**Manual pass.** A dev instance on 8487 with a scratch data dir and dev mode
(`/proc/<pid>/environ` verified), driven with headless Chromium at 1440×900 and 1024×768 in
dark and light: the guidance (no provider), the empty state (a mock and an ollama provider,
two agents, no chats), pending (`Gardener`: the green `llama3.1:8b` badge, the name, the
two-line description, Pick a different agent; header "New chat with Gardener") and joined
(the header title is the auto-title, which the server cuts at 50 characters; it fits at
1024 beside "with Helper"). No console errors, no horizontal scroll. Stopped with
`make down`; its log removed.

**Deviations and decisions** (also in "Deviations" below):
1. **`chat-welcome-list`** is also in `RETIRED_SELECTORS` (AC10 named `new-chat-btn`,
   `chat-welcome-item` and `session-agent-badge`): the welcome listbox is retired too (AC6).
2. **The two static `innerHTML` literals were converted** (AC8 allowed it); the `= ''` clears
   stay. A new guard pins it.
3. **The welcome is shown only by the idle rules.** `refreshAgentsAndSetup` no longer shows it
   while idle (it did with setup incomplete), so the guidance never flashes before an
   auto-join; it re-renders a welcome already shown. `openConversation` shows the chrome at
   once, so nothing flashes while joining either.
4. **A pending chat's log stays in the tree** under the new-chat state (`.chat-chrome--new`:
   zero height when empty), so a start failure's error, the `/reset` notice and the attach-cap
   notices show in the pending pane and the live region exists before they are announced.
   `test_chat_message_log_has_live_region` was re-pinned for it.
5. **The welcome is hand-built**, not `App.ui.emptyState` (DD3 named one): the leg keeps the
   "Hello." `h1` as the state's one heading (the design review's answer). DD3's "Start a
   conversation" lives in the prompt.
6. **The guidance state hides the prompt**, as `welcome.js` did (AC5's "the prompt and the
   guidance links" read with "the same copy as welcome.js today").
7. **The empty state's New chat** is `App.ui.button` primary at the default size with the
   square-pen icon (the leg named the variant only).
8. **API beyond the leg**: `App.chat.chatPane.agentInfo`, `agentLine` and `guidance`;
   `App.chat.agentPicker.providerType` exported; `agents` and `providers` subscriptions.
9. **A `stop` icon** in `icons.js` (a filled square, the former inline SVG; not a Lucide
   stroke glyph), so the Stop icon comes from `App.ui.util.icon` as AC7 asks.
10. **No `h1` during the brief idle before the first `session_list`** (the header is hidden
    while idle and the welcome not yet shown); every named state has exactly one.
11. **A joining id with no `sessions` row** shows a blank header until its reply (a deep link
    on an open socket to a session the store has not seen).
12. **The header's height is a 48px literal**: the app defines no `--topbar-h`.
13. **Two more files changed than the leg listed**: `test_chats_helper.py` (it used
    `welcome_item`) and `test_flow_chat.py` (deviation 4).

**For leg 5:**
- The composer is `App.chat.composer.create()`; restyle it there. `chat.js` holds only the
  references and the listeners.
- The telemetry overlay still shows in pending (DD6 says the new-chat state has none);
  `test_flow_new_chat.py::test_telemetry_overlay_collapses_by_default` pins it visible right
  after `start_chat`. Leg 5's telemetry row decides.
- Squawk 0110: `test_flow_chat_pane.py::test_one_h1_landmarks_and_named_controls_in_every_state`
  ends by asserting the raw resolver result is exactly the one `chat-image-input` failure;
  leg 5 flips it to `[]` (and `_unnamed`'s filter can go).

**For leg 6:** the drawer toggle goes at the end of `pane.header` (`margin-left: auto`); the
header is hidden while idle, which matches DD7's "no chat, no toggle".

**For leg 8: behavior specs to re-author** (they name the retired welcome agent list, the
agent badge or the old start path):
- `workbench-navigation` step 2 ("the main region lists `wbnav-agent` among the agents
  available to chat with": the welcome agent list);
- `vision-round-trip` step 1 ("the vision-capable agent's chat welcome item", "the session
  agent badge");
- `shell-navigation-smoke` step 3 ("the main region shows either the agent picker, a message
  composer, or a welcome/config-needed message": now the empty state "Hello. Start a
  conversation…" with New chat, a pending/joined chat, or the guidance);
- `chat-roundtrip` step 3 ("start a new session with the `chat-roundtrip-agent`": through New
  chat and the picker; "bound to the selected agent" is the header's "with {agent}");
- `agent-purge-now-clears-history` step 6 (the "Chat-area session list" is the Chats list);
- `stub-connector-round-trip` step 5 (and its apparatus line's "Chat unified history");
- the generic "start a new chat with X" steps: `agent-governance-and-search` step 6,
  `chat-loop-hang-and-cancel` step 1, `extended-thinking-tool-turn` step 1 ("Select … the
  agent. Start a new chat").
- `start-a-chat` (draft) already names `chat-new-state`; its finalisation can use
  `chat-header`, `chat-agent-line`, `chat-pick-different-btn` and `chat-empty-new-btn`.
No spec names `Select Agent`, `agent-select`, `new-chat-btn` or `session-agent-badge` by id.

### Leg 5: composer-and-telemetry (landed, 2026-10-05)

**What landed.** The chat composer has reference spec 5.5's look, and the telemetry readout
moved out of its absolute overlay into a row above it (5.3; DD6, A25). Squawk 0110 is closed:
the hidden file input is named.

- **`static/js/areas/chat/composer.js`** (rewritten; still a DOM builder with no listeners).
  `App.chat.composer.create()` -> `{el, box, input, fileInput, attachBtn, modelEl, stopBtn,
  sendBtn, attachmentsEl, attachmentsStatusEl, queuedRegion, telemetryRow, render(view), fit()}`.
  - **The wrapper** `.composer` (`padding: 12px 24px 20px`) holds, top to bottom: the
    **telemetry row** (`.composer-telemetry`, flex-end, `hidden` by default), the chicklets
    (`chat-attachments`) and their status, the **queued-message region**
    (`pending-queued-region`, built here now, not in `chat.js`), then the **box**
    (`.composer-box`: max 760px, centred, a flex column with an 8px gap, `--surface`, a
    hairline, `--radius-md`, `10px 12px`).
  - **In the box:** a `.visually-hidden` `<label for="chat-composer-input">` "Message", the
    `<textarea rows=2>` (`chat-input`, `.composer-input`, `enterkeyhint=send`, no `aria-label`,
    placeholder "Message…" until `render`), and the toolbar (`.composer-toolbar`):
    - **Attach images**: `App.ui.button` ghost `sm` `iconOnly`, the new `paperclip` icon,
      `aria-label="Attach images"` (`chat-attach-btn`);
    - the hidden file input, with `aria-label="Attach images"` (`chat-image-input`, squawk
      0110);
    - the **model id** (`span.composer-model`, new testid `chat-model`);
    - **Stop** (`App.ui.button` danger, `chat-stop-btn`, `hidden`);
    - **Send** (`App.ui.button` primary, the send icon and "Send", `aria-keyshortcuts=Enter`,
      `chat-send-btn`).
  - `render({agent, model})` sets the placeholder ("Message {agent}…", or "Message…" with no
    agent) and the model text. `fit()` sizes the textarea to its content: it resets to the
    two-row height, reads `scrollHeight` and sets the height (the CSS `max-height` caps it at
    about eight lines, then it scrolls). It holds the box's `min-height` while it measures, so
    the message log above does not grow for the measurement and clamp its `scrollTop` (a log
    pinned to its end would otherwise drift on every keystroke).
- **`static/js/areas/chat.js`.**
  - The chrome appends only `composer.el`. `chat.js` fills `composer.telemetryRow` with
    `App.chat.renderTelemetry()`, and `pendingQueuedRegionEl` is `composer.queuedRegion`.
  - **`renderPane()`** also renders the composer from the header's agent: pending or starting
    use the pending agent ("Message…" while a cold `~new` validates); joined or joining use the
    store row's or the payload's agent ("Message…" for a null agent, or a joining id with no
    row). The model comes from `agentInfo(...).model` ('' when the `agents` store lacks the
    agent). It sets **`telemetryRow.hidden = name !== 'joined'`**.
  - **Keys:** the `keydown` returns on Shift, and on `e.isComposing || e.keyCode === 229`;
    otherwise Enter calls `preventDefault` and sends. An `input` listener calls
    `composer.fit()`.
  - A new **`setInputValue(text)`** is now the only scripted write: it sets the value and
    re-fits. It covers the three clears in `send()` and the two restores in
    `applyStartFailed`.
- **`css/chat.css`.**
  - The `.input-area` row and its `border-top` are gone, with its `[hidden]` re-assert
    (retargeted to `.composer-toolbar`).
  - New rules: `.composer`, `.composer-telemetry` (`justify-content: flex-end`,
    `margin-bottom: 8px`), `.composer-box` and `.composer-box:focus-within`
    (`outline: 2px solid var(--accent); outline-offset: 2px`).
  - `.composer-input`: `resize: none`, `border: 0`, transparent, `--fg`, 14px at
    `--line-height-normal`, `max-height: calc(var(--line-height-normal) * 8em)`,
    `overflow-y: auto` and `outline: none`. Its `::placeholder` is `--fg-muted`.
  - `.composer-toolbar`: flex, centred, 8px gap. `.composer-model`: 11px mono `--fg-muted`,
    ellipsis.
  - Send has `margin-left: auto`. A shown Stop takes the auto margin instead, and Send
    follows it (`.composer-stop:not([hidden]) + .composer-send { margin-left: 0 }`).
  - `.telemetry-overlay` loses `position: absolute; right; bottom; z-index`. Its opacity
    (0.7), its type and the hover/focus expansion are unchanged.
  - `.pending-queued-region` loses its `z-index` stacking workaround and its `0 20px`
    inset, and takes the box's 760px column. So does `.chat-attachments`, whose static inline
    styles (wrap, gap, margin) moved into CSS (`display` stays inline: the `.chip`
    `[hidden]` footgun).
- **`static/js/icons.js`**: `paperclip` (Lucide geometry as drawn on B3). Leg 4 had not added
  it. **`telemetry-overlay.js`**: a comment only (the readout's new home; the class name is
  historical).
- **Docs.**
  - `CLAUDE.md`: a "Chat composer" paragraph; the Chats-pane paragraph points at it;
    `input-area` joins the retired-selector list.
  - `the_one/agents.md`: a new "Chat composer (client, M25 F4 L5)" section (layout, the
    telemetry row, the textarea and `fit`, Enter/Shift+Enter/IME, the `:focus-within` ring,
    the toolbar, the tests). The focus convention's `:focus-within` variant names the
    composer box as the one full-ring exception. The Chats-pane bullets and the
    retired-selector note are updated.
  - The inventory: the "Chat composer" row stays "not yet defined", with the note that it
    meets 5.5's look but is not a library control. The telemetry row is renamed "Telemetry
    readout", with its new placement.
  - The testid registry: `chat-model` is new; `chat-input`, `chat-attach-btn`,
    `chat-image-input`, `chat-send-btn`, `chat-stop-btn` and `chat-attachments` are described.

**Old to new test names** (every removed, replaced or re-pinned test):

| Old | New | How |
|---|---|---|
| `test_flow_chat_pane.py::test_composer_markup_is_carried_over_unchanged` | `test_flow_chat_composer.py::test_composer_box_textarea_and_toolbar_match_the_board` | replaced: the 5.5 markup and computed styles instead of 4b's carried-over row |
| `test_flow_chat_pane.py::test_one_h1_landmarks_and_named_controls_in_every_state` | (same name) | the 0110 allow-list is gone: `_unnamed` no longer filters `chat-image-input`, and the closing "exactly one failure" assertion is removed (every state expects `[]`) |
| `test_flow_chat.py::test_chat_message_log_has_live_region` | (same name) | `aria-label == "Message"` -> `to_have_accessible_name("Message")` and no `aria-label` (a real label now) |
| `test_flow_new_chat.py::test_telemetry_overlay_collapses_by_default` | (same name) | **re-pinned to a joined chat** (the 4b hand-off): it asserts the readout hidden in the pending chat, sends the first message, then checks the collapsed details and the focus expansion as before |
| `test_nav_helper.py::test_retired_selector_guard_self_test` | (same name) | gains the `input-area` cases (caught) and the kept `.composer-box`, `.composer-telemetry` and composer testids (pass) |

`test_flow_context_overlay_thresholds.py` and `test_flow_usage_restore.py` are **unchanged**
and green: they read the readout by class and text, never its position, and they act in a
joined chat. `test_telemetry_ghost_value_holds_annotation_floor` stays valid (the opacity is
still 0.7 and the readout still sits over `--bg`); the `_TELEMETRY_RESTING_OPACITY` comment
now names the row.

**New tests.**
- `tests/browser/test_flow_chat_composer.py` (chats lane; 8 functions, 9 tests, the ring
  test parametrized by theme):
  - the wrapper, box, label, textarea and toolbar against 5.5, through computed styles and
    token probes; the placeholder and model id through a re-pick, a join and two store primes
    (an unknown agent gives an empty model; a null agent gives "Message…");
  - **keys**: Shift+Enter makes a two-line value; synthetic `isComposing` and `keyCode` 229
    Enters are not prevented and send nothing; Enter sends both lines as one `start_session`;
    a pasted multi-line draft goes as one plain message;
  - **the ring** in both themes: on the textarea, Attach and Send (by Tab); none when blurred,
    and none for a disabled textarea;
  - Stop 8px before Send, and Send at the toolbar's end, while a turn runs (`delay_ms`);
  - the textarea heights 42, 84 and 168px, scrolling at the cap, and back to 42 after a send;
  - **the telemetry row**: hidden in pending and starting (read in the same task as the
    send); shown joined, 8px above the box with nothing rendered between, the readout 24px
    from the pane's right edge, `position: static`, resting at 0.7, and focus still expands
    it; hidden again by a new pick, shown again by reopening the chat;
  - the chicklets above the box, in its column;
  - **squawk 0110**: the resolver over `body` on `#chats` with a joined chat, Light and
    Dark, gives `[]`.
- `tests/test_design_tokens_a11y.py::test_composer_text_pairs_pass_body_aa` (2): `--fg` and
  `--fg-muted` on `--surface`.

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, `-x --timeout 60`, one at a time):

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (508 files formatted) |
| Static guards (4b's set: `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static`, `test_index_asset_cache_busting`, `test_ui_control_inventory`, `test_ui_library_source`, `test_run_tests_lanes`) | **401** passed in 3.0s (4b's 399 + `test_composer_text_pairs_pass_body_aa` x2). No new sink; the asset pin is unchanged (no new script) |
| `make test-unit` | **5146** passed, 10 skipped, 1678 deselected in 689.0s (11m29s): 4b's 5144 + `test_composer_text_pairs_pass_body_aa` x2 (an earlier run also exited 0; its summary line was lost to a `tail`) |
| `--lane chats` | **144** passed in 214.2s (3m34s): 4b's 136 − the replaced carried-over test + `test_flow_chat_composer.py` 9 |
| `test_flow_chat_composer.py` alone | 9 passed, three runs (19.7s, 19.9s, 22.9s) |
| `--lane shared` (`TEST_TIMEOUT=3600`) | **441** passed in 667.5s (11m07s), as 4b |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`; no `ui/` file changed, run because the harness loads `icons.js`, which gained `paperclip`) | **556** passed, 3 skipped in 147.6s (2m27s), unchanged; the 3 are the in-test WebKit forced-colors skips |

**Falsification (AC4).** With the `.composer-box:focus-within` rule removed from `chat.css`,
`test_the_box_shows_the_focus_ring_while_the_textarea_or_a_toolbar_button_has_focus` failed in
**both** themes. The ring read `style: 'none'` and `offset: '0px'` with the textarea focused,
where the test expects `solid`, 2px, `--accent` and 2px. Restored from the scratchpad copy:
`cmp` is clean, a grep for `FALSIFIED` is empty, and the test is green.

**Manual pass.** A dev instance on 8486 (scratch data dir, dev mode, `/proc/<pid>/environ`
verified), driven with headless Chromium at 1440×900 and 1024×768, in Light and Dark.
Seeded: a mock agent and an ollama agent (`llama3.1:8b`).
- **Pending** ("Message Gardener…", `llama3.1:8b`, no telemetry) and **joined** (the readout
  24px from the pane's edge at both widths, "Message Helper…", `mock-default`) match 5.5.
- The ring shows on the textarea and on Attach (Tab), in both themes.
- A Shift+Enter draft grows the box.
- An `agent_deleted` health banner sits above the composer, with the textarea disabled, no
  ring and an empty model id.
- No console errors and no horizontal scroll.

Stopped with `make down`, and its log and PID files were removed.

**Deviations and decisions** (also in "Deviations" below):
1. **The telemetry row has no horizontal padding of its own.** AC7 puts it inside the wrapper,
   whose 24px side padding is the board's `0 24px` inset (on B3 the row sits outside the
   wrapper). The readout's right edge is 24px from the pane's, as drawn, and a test pins it.
   `padding: 0 24px` inside the wrapper would have inset it 48px.
2. **The order inside the wrapper** is the telemetry row, then the chicklets, their status and
   the queued region, then the box. The row is directly above the box whenever nothing is
   staged or queued, which is the common case. A staged image or a held message sits between
   them, so the transient composer items hug the box they belong to.
3. **Attach is `btn-ghost btn-sm btn-icon`**: `App.ui.button` `iconOnly`, 24×24 with a 14px
   icon. The board renders it unsquared at 34×24 with a 16px icon; this follows Flight 1's
   icon-only modifier (A4, A5).
4. **The composer's three buttons are `App.ui.button`s** (so `type="button"`), each with a
   `composer-*` class. Stop keeps its icon, label and `aria-label`.
5. **`input-area` is a new `RETIRED_SELECTORS` entry**, though the leg did not list it: a test
   naming the old row would now match nothing in silence.
6. **The queued region is built in `composer.js`**, and its z-index workaround is gone (the
   readout is in the flow). The chicklets' static inline layout moved to `chat.css`.
7. **The readout keeps its class `.telemetry-overlay`** (`telemetry-overlay.js`, the browser
   tests and the `extended-thinking-tool-turn` spec read it); the row is the new `.composer-telemetry`.
8. **The textarea grows by script**: `fit()`, with `setInputValue` as the one scripted-write
   path, not CSS `field-sizing`, which not every engine the app runs in supports.
9. **The model id's pair was already gated** by the fg-ladder sweep
   (`test_body_text_passes_aa[*-fg_muted-surface]`). A named consumer test was added anyway,
   with the textarea's text and placeholder.
10. **The telemetry row is hidden while starting and joining too** (AC7 says "only in
    `joined`"), so a session switch never shows the previous chat's numbers. A reconnect's
    re-join keeps it shown, since `renderPane` does not run until the reply.
11. **Ctrl, Alt and Meta with Enter still send**, as before; only Shift is excluded.
12. **Files beyond the leg's list**: `test_flow_chat.py` (the accessible name),
    `test_nav_helper.py`, `CLAUDE.md` and the testid registry.

**For leg 6:** the composer is untouched by the drawer. The drawer's model and provider can
reuse `App.chat.chatPane.agentInfo`, as the composer's model id does.

**For leg 8:** `extended-thinking-tool-turn` step 5 compares the readout with "the empty-chat
baseline (0% at Step 1)". Since this leg, a pending new chat shows no telemetry, so step 1 has
no baseline: re-word it (absent before the first send, non-zero after the turn).
`agent-governance-and-search` step 8 still holds (a joined chat, class-based). The
`vision-round-trip` testids are all kept.

### Leg 6: agent-drawer-and-chat-action (landed, 2026-10-05)

**What landed.** The agent drawer on Chats (reference spec 5.7; DD7, DD15 A13, A20, A21) on
a new `App.ui.drawer` factory (DD14), the agent editor's Chat header action (DD8), one shared
built-in tool category table (AC9), `listPane.setQuery` with `App.studio.clearAgentFilter`
(AC12), and squawk 0118's editor Save/Cancel contract (AC14).

- **`static/js/ui/drawer.js`** (new): `App.ui.drawer({label, heading, body, footer, el,
  testid, onOpenChange})` -> `{el, open(opener), close(), toggle(opener), isOpen(),
  setMode('push'|'overlay'), destroy()}`.
  - A non-modal `<aside>` (the `aria-label` from `label`): a 48px header (an `h2` from text,
    or a node), a body that alone scrolls, an optional footer over a hairline. Built closed;
    shown and hidden with `hidden`, never removed.
  - `el` fills an existing `<aside>` (the static shell slot): children replaced, id kept.
  - `open()` never moves focus; `open(opener)` records the opener (no argument keeps the last
    one). `close()` returns focus to it only when focus is inside at that moment.
  - Escape while focus is inside closes it (`preventDefault`, `stopPropagation`; ignored
    while an IME composes), so focus returns to the opener.
  - `setMode`: `.ui-drawer--push` (a `--drawer-w` 320px flex sibling, `--surface`, a 1px
    `--border` left edge) or `.ui-drawer--overlay` (`position: absolute; top/right/bottom: 0;
    z-index: 10`, `--shadow-modal`, no scrim, no outside-click close); `data-mode` mirrors it.
  - One keydown listener on the `<aside>`, none on the document or window. `destroy()`
    unbinds it, empties and hides the drawer, and leaves the element in place.
  - CSS in `components.css` (with `[hidden]` re-asserted for the drawer, its header and its
    footer in the components layer); the `--drawer-w` token in `tokens.css`.
- **`static/js/areas/chat/agent-drawer.js`** (new, `App.chat.agentDrawer`): fills the static
  slot.
  - `create({slot})` -> `{drawer, toggle, render(view), setActive(on), destroy()}`. One
    state object `{mode, open: {push, overlay}}` applied by one `apply()`: shown only while
    the area is active, there is a chat view and the mode's state is open.
  - The mode comes from `matchMedia('(min-width: 1280px)')` and its `change` listener (on
    the `MediaQueryList`; removed by `destroy`). Defaults: push open, overlay closed. The
    open state persists in `localStorage` `chat-drawer-open` (`{push, overlay}`, try/catch);
    only the user's changes are written (the toggle, Escape).
  - The toggle (`chat-drawer-toggle`): `App.ui.button` ghost icon-only, `panel-right`,
    `aria-label="Show this chat's agent"`, `aria-pressed`, `aria-controls="chat-drawer"`,
    `margin-left: auto`, hidden with no chat view.
  - Header: the name (`h2`, 13px/600) and the provider-TYPE badge (A20). Body: the
    description; the facts `<dl>` (Model mono, Provider by display name, Chats with
    connector sessions); "What it can use" (Knowledge bases, MCP servers with "{n} tools",
    the loopback source skipped, Built-in tools "{n} of {total}" per category, effective =
    global AND `is_tool_enabled`, Self-configuration On/Off; "None" and "Couldn't load" per
    group). Footer: Open agent settings (`chat-drawer-settings-link`).
  - Fetches only while open with a known agent: one `GET /api/tools/configs` per open, one
    self-configuration `GET` per open and agent, `App.store.get` for `knowledge-bases` and
    `mcp-sources` once per open; responses from an earlier open are dropped.
  - The default, deleted and loading states, none with the link (the footer wrapper is
    `hidden`). It subscribes to the five stores and unsubscribes on `destroy`.
  - Exports `isToolEnabled(agent, name)` (`AgentConfig.is_tool_enabled` mirrored, the
    `mcp__`/`kb__` exemption included) and `builtinGroups(agent, configs)`.
- **`index.html`**: the static `<aside id="chat-drawer" aria-label="This chat's agent"
  data-testid="chat-drawer" hidden>` after `<main>`; script tags for `ui/drawer.js`,
  `tool-categories.js` (before `studio.js` and `admin/tools-*`), `areas/chat/agent-drawer.js`
  and the design-language `ui-drawer-section.js` (the asset pin is 80).
- **`css/base.css`**: `.app-shell-row { position: relative }`; `#chat-drawer[hidden]
  { display: none }`.
- **`areas/chat.js`**: creates the drawer in `init` and appends its toggle at the header's
  end; `renderPane()` feeds it the header's agent (a loading view while the agent line is
  blank, null while idle); `activate`/`deactivate` call `setActive`. `requestPick`'s go is
  now `goPick` (it resolves with the go's result), shared with the picker host's new
  `chatWith`.
- **`areas/chat/agent-picker.js`**: `App.chat.chatWith(agent, {opener})`, the Chat action's
  entry: the host's `goPick` (the guarded go WITH the one-shot `pickIntent`), or a plain go
  before the chat area exists.
- **`areas/studio/agent-editor.js`**: Chat (`agent-chat-btn`, `App.ui.button` secondary,
  the `chat` icon) inserted with DOM APIs into `.form-actions` before Cancel, saved agents
  only; the markup string is unchanged.
- **`static/js/tool-categories.js`** (new, `App.toolCategories`, frozen): `order`,
  `labels`, `byCategory`, `categoryOf`. `studio.js`, `admin/tools-grid.js` and
  `admin/tools-editor.js` read it; their copies are gone.
- **`ui/list-pane.js`**: `setQuery(q)`, silent, no row rebuilt. **`areas/studio.js`**:
  `App.studio.clearAgentFilter` (a no-op stub at script load; in `init`, `setQuery('')`
  then a scroll of the selected row into view).
- **`js/icons.js`**: `panel-right` and `settings`.
- **`css/chat.css`**: the toggle rules (above the overlay, see deviation 2) and the drawer
  content rules (unscoped `.chat-drawer-*`, since the slot is outside `.area-chat`).
- **Design language**: `ui-drawer-section.js` (push and overlay frames per theme, the
  drawer narrowed through `--drawer-w`), its `admin.css` rules and its SECTIONS entry.
- **Docs**: `CLAUDE.md` (the App shell paragraph and the Chats pane paragraph's drawer and
  Chat sentence); `the_one/agents.md` (the drawer and `setQuery` bullets in "Control
  library", the slot bullet in "App shell — invariants", a new "Agent drawer (client, M25
  F4 L6)" section, and the "Editor Save/Cancel contract (squawk 0118)" block); the
  inventory (a Drawer row; the list pane's `setQuery`; the chat pane's toggle); the registry
  (`agent-chat-btn`, the six `chat-drawer*` ids, the `ui-demo-drawer-` and
  `ui-demo-drawer-toggle-` families).

**Tests fixed for the open-by-default drawer.** Playwright's 1280x720 default is push mode,
so every Chats browser test now runs with the drawer open and a 588px pane (748px at 1440).
The full `chats` and `shared` lanes ran against it. One test assumed a full-width pane:

| Test | How |
|---|---|
| `test_flow_chat_composer.py::test_composer_box_textarea_and_toolbar_match_the_board` | asserted the box at its 760px cap at 1440; with the drawer open the wrapper's column is 700px. It now asserts `max-width: 760px`, centred, and `width == min(760, column)` |

Re-pinned by the leg itself (AC3): `test_shell_rail.py::test_top_bar_is_gone_and_the_shell_is_a_flex_row_with_a_rail`
(the shell row's children now end with `chat-drawer`) and `::test_landmarks_and_aside_labels`
(the drawer hidden while idle, then a chat started: its complementary landmark, named
uniquely, then hidden again off Chats). No `shared` test needed a change: they run idle
(no drawer) or read nothing that the narrower pane moves.

**The tool tables.** The three copies migrated mechanically to `App.toolCategories`
(`studio.js` reads `byCategory`; `tools-grid.js` `categoryOf`, `order`, `labels`;
`tools-editor.js` `categoryOf`). The completeness check against `_TOOL_CLASSES` found
**`find_platform_destination` missing from all three** (M23 F4 L3): it showed in no Settings
tab and had no Tools-tab checkbox. It is under Connectors now, which moved four pins:

| Test | Old | New |
|---|---|---|
| `test_flow_studio_tools_overrides.py::test_studio_tools_tab_renders_category_tiles` | 21 tool tiles | 22 |
| `test_flow_studio_tools_overrides.py::test_studio_connectors_category_renders_both_tools` | "2 / 2 enabled", two tools | "3 / 3 enabled", three |
| `test_flow_studio_tools_overrides.py::test_studio_connectors_category_checkbox_toggle_round_trips_via_api` | "1 / 2 enabled" | "2 / 3 enabled" |
| `test_flow_admin_tools_grid.py::test_admin_tools_each_tab_renders_correct_tile_count` and `::test_admin_tools_connectors_tab_renders_both_tools_with_connectors_badge` | Connectors 2 | 3 (the third with the `connectors` badge) |

`_lists.py`'s `TOOL_TABS` comment now names the shared table. The `settings` lane ran
(the tables moved): green.

**New tests.**
- `tests/browser/test_ui_drawer_contract.py` (contracts lane, Chromium and WebKit, 20
  functions, 40 tests): the API and markup; a node heading and text never HTML; five
  rejected options; filling a static `<aside>`; `hidden` and `onOpenChange`; `hidden` wins
  in both modes; Escape inside closes and focus returns; Escape outside does nothing; close
  returns focus only from inside; Escape consumed, and ignored while composing; push (320px,
  the main area yields, `--surface`, the border, the 48px header and its hairline, the 13px
  title) in both themes; overlay (absolute over the frame's right, the shadow, z-index 10, the
  main area keeps its width); no outside-click close; `destroy`; the resolver.
- `test_ui_listener_cleanup.py::test_drawer_installs_no_document_listener_and_wiping_leaves_nothing`
  (both engines).
- `test_ui_library_contract.py::test_list_pane_set_query_applies_the_view_silently` and
  `::test_list_pane_set_query_is_a_no_op_without_a_filter` (both engines).
- `tests/browser/test_flow_chat_drawer.py` (chats lane, 18 tests): push open at 1280 and
  1440 (588 and 748px panes, the header hairlines aligned, the toggle); overlay closed at
  1024 and the toggle on top of the open overlay; the toggle and Escape (focus back,
  persisted); persistence across a reload and a resize both ways; the badge, description and
  facts (Provider by display name, Chats 2 with a connector session, then 3 after the first
  send) with their type and colours; "What it can use" (the knowledge base, the MCP servers
  with "12 tools" and a cold one without, the loopback source skipped, the built-ins
  8/9, 4/6, 3/4, 3/3 with a global and per-agent off, self-configuration On; then a bare
  agent: None, None, Filesystem 1 of 9, Off); "Couldn't load" per group; one fetch of each
  per open; `isToolEnabled` against `AgentConfig.is_tool_enabled` over five configs and six
  names; Open agent settings with the filter cleared and the row in view among 30 agents;
  `clearAgentFilter` a no-op before studio's init; the deleted and default agents; a failed
  agents read shows "Loading…", never "deleted", then the agent; hidden while idle and on
  Agents, Library and Settings; landmarks and the resolver in both themes (idle and open);
  the five subscriptions and the matchMedia listener released by `destroy`.
- `tests/browser/test_agents_chat_action.py` (agents lane, 4 tests): Chat from a clean
  editor (its place before Cancel, its class and icon); absent in create mode; from a dirty
  editor, Stay (edit kept, focus on Chat) then Continue (pending chat), one dialog each; a
  deliberate start, not the rail restore.
- `tests/test_tool_categories.py` (unit, 6): every `_TOOL_CLASSES` tool exactly once, the
  connector lookup tool, the tab order, the guard's own falsification (a dropped and an extra
  tool are caught), the three consumers on the shared table, the script order.
- `tests/test_design_tokens_a11y.py::test_drawer_text_pairs_pass_body_aa` (2): `--fg`,
  `--fg-secondary` and `--fg-muted` on `--surface`, both themes.

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, one at a time; final runs after every change):

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (512 files formatted) |
| Static guards (leg 5's set plus `test_tool_categories`) | **413** passed in 3.0s: leg 5's 401 + `test_tool_categories.py` 6 + `test_drawer_text_pairs_pass_body_aa` 2 + `test_ui_library_source.py`'s three per-file checks of `drawer.js` 3 + `test_ui_control_inventory.py`'s per-section check of `ui-drawer-section.js` 1. The testid registry, the inventory (`App.ui.drawer`), the sink guards (no new sink: every new node is DOM-built) and the asset pin (80) are in it |
| `make test-unit` | **5158** passed, 10 skipped, 1746 deselected in 665.7s (11m06s): leg 5's 5146 + the 12 new static and unit tests above (the 68 more deselected are the new browser tests) |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`) | **602** passed, 3 skipped in 158.8s: leg 5's 556 + the drawer contract 40 + the listener case 2 + `setQuery` 4; the 3 are the in-test WebKit forced-colors skips. The reference page's demo-root, both-panes and resolver checks cover the drawer demo |
| `--lane chats` | **162** passed in 249.8s (4m10s): leg 5's 144 + `test_flow_chat_drawer.py` 18 |
| `--lane agents` | **134** passed, 2 skipped in 331.9s (5m32s); the 2 are static `@pytest.mark.skip`s (`test_flow_agent_tabs.py:265`, `test_flow_studio_openrouter_picker.py:203`) |
| `--lane settings` (the tool tables moved) | **178** passed in 337.4s |
| `--lane shared` (`TEST_TIMEOUT=3600`) | **441** passed in 663.6s (11m04s), as leg 5 (the two `test_shell_rail.py` tests changed in place) |

A first `chats` run had the one composer failure above, and a first `agents` run the three
Tools-tab pins; both were fixed and the lanes re-run green.

**Falsification.**
- **The drawer slot (the leg's).** With `apply()` changed to remove the drawer from the DOM
  when there is no chat view, `test_flow_chat_drawer.py::test_landmarks_and_resolver_with_the_drawer_open_and_while_idle`
  failed in **both** themes on the idle state: `<button data-testid=chat-drawer-toggle> ::
  aria-controls references missing id "chat-drawer"`. Restored from the scratchpad copy: `cmp`
  is clean, a grep for `FALSIFIED` is empty, and the test is green.
- **The pick intent (an extra).** With `App.chat.chatWith`'s host branch removed (a plain
  `go`), `test_agents_chat_action.py::test_chat_is_a_deliberate_start_not_the_rail_restore`
  failed: the route stayed `chats/{id}` (the AC9 rail restore kept the joined session).
  Restored the same way.
- `test_tool_categories.py::test_the_guard_catches_a_missing_and_a_stale_tool` falsifies the
  completeness guard in place on every run.

**Manual pass.** A dev instance on 8486 (scratch data dir, dev mode, `/proc/<pid>/environ`
verified), seeded with an agent that has a knowledge base, an MCP server with a 12-tool
cache, self-configuration enabled and three disabled tools; driven with headless Chromium.
- **1440, Light and Dark:** push, open; the 748px pane; the drawer's header hairline meets
  the chat header's; "Research assistant" with the `mock` badge, the description, Model
  (mono), Provider "Claude Max", Chats 0 (pending); Team wiki; GitHub "12 tools" (the
  loopback source is not listed); Filesystem 9 of 9, Execution 4 of 6, Web 3 of 4,
  Connectors 3 of 3; Self-configuration On; Open agent settings in the footer.
- **1024, Light and Dark:** overlay, closed on arrival (the 652px pane); opened by the toggle
  it covers the pane's right, Send included (accepted, DD13). Here the first pass found the
  open overlay covering the header's toggle (deviation 2); after the fix the toggle sits in
  the overlay header's right corner and closes it.
- A deleted agent's chat: the name, "This agent no longer exists", Chats 1, no link. The
  Design language page's drawer demo in both panes. No console errors and no horizontal
  scroll at either width.

Stopped with `make down`, and its log and PID files were removed.

**Deviations and decisions** (also in "Deviations" below):
1. **The drawer and its toggle follow the header**, so they show in `starting` and `joining`
   too, not only `pending` and `joined` (AC3, AC5): the first send (pending, starting,
   joined) and a switch between chats (joined, joining, joined) would otherwise hide and
   re-show the drawer, shifting the pane twice in push mode. A blank header (a cold `~new`
   validating its agent, a joining id with no `sessions` row) gets the neutral loading view.
2. **The toggle stays above the open overlay** (`position: relative; z-index: 11`), and the
   overlay's header keeps its right corner clear (`padding-right: 56px`). Below 1280 the
   overlay covers the chat pane from the top (`top: 0`, as AC4 says), header included, and
   the reference draws no close control inside the drawer, so a pointer user had no way to
   close it. The toggle now reads as the drawer's own close control there. A DD13 preview
   question alongside the covered Send.
3. **`App.ui.drawer` takes an `el` option** (beyond AC1's list): it fills the static
   `<aside>` slot (AC3), so the slot itself is the landmark, with no `<aside>` nested in
   another. Without `el` the factory creates the `<aside>`.
4. **The footer is hidden through its wrapper's `hidden`** (the chat drawer reads
   `settingsBtn.parentNode`), with `.ui-drawer-header[hidden]` and `.ui-drawer-footer[hidden]`
   in the factory CSS; no factory method was added (AC1 fixes the API).
5. **`App.chat.chatWith(agent, {opener})`** (in `agent-picker.js`, beyond the leg's files):
   Chat must carry the chat area's one-shot pick intent, or the AC9 rail restore keeps a
   joined session started from the same agent instead of opening the pending chat (DD2's
   "a deliberate New Chat is always a pick"). The go is exactly AC13's
   `href({destination: 'chats', create: true, agent})`; before the chat area's init it is a
   plain go. Unlike a pick it is not inert while setup is incomplete.
6. **`isToolEnabled` mirrors `is_tool_enabled` whole**, the `mcp__`/`kb__` exemption
   included (AC8 gave the built-ins-only formula); the drawer calls it for built-ins only,
   and the parity test covers all six names.
7. **Built-in tools list only the categories with an effective tool**, "{n} of {total}",
   and "None" when there are none (a category with nothing usable is not "what it can use").
   **Self-configuration reads "Off"** when it is not enabled ("None" would misread).
8. **The default and deleted states show the Chats fact**; the loading state shows only
   "Loading…". Knowledge bases and MCP servers list A-Z.
9. **`setQuery` clears the status region** (silent: it never writes one, so a stale
   "N results" does not linger after the clear).
10. **A `--drawer-w` token** (320px, in `tokens.css` beside `--list-w`); the design-language
    demo narrows it per frame.
11. **The editor contract states what the code does**: Save ("Create") enables on the first
    change and required fields are checked on click; the squawk report's "enabled once the
    required fields are valid" is not true of any editor. Documentation only.
12. **`find_platform_destination` joined Connectors** (the completeness check), so the
    per-agent Tools tab has 22 tool tiles and Settings › Connectors 3; four pins in two test
    files moved.
13. **Chat has the `chat` icon** (reference spec Appendix B) and the class `agent-chat-btn`.
    The demo test ids are per-pane families (`ui-demo-drawer-{theme}-{push|overlay}` and
    `ui-demo-drawer-toggle-…`, registered as prefixes), since the demo is built twice.
14. **Files beyond the leg's list**: `agent-picker.js`, `chat-pane.js` (a comment),
    `css/tokens.css`, `css/admin.css`, `design-language-page.js`; tests
    `test_flow_chat_composer.py`, `test_flow_studio_tools_overrides.py`,
    `test_flow_admin_tools_grid.py`, `_lists.py` (a comment), `test_ui_control_inventory.py`,
    `test_index_asset_cache_busting.py`, `test_design_tokens_a11y.py`, and the new
    `test_tool_categories.py`.

**Squawk 0118** is completed, pending sign-off at the flight review: the "Editor
Save/Cancel contract" block is in `the_one/agents.md`, and the squawk file has its Corrective
Action and Verification.

**For leg 7:** `App.studio.clearAgentFilter()` is defined from script load (a no-op until
studio's init), so the palette can call it after any committed `go()`. The drawer's Escape
handler stops propagation only for an Escape with focus inside the drawer; the leg 7
shell-level `keydown` listener sees Ctrl K from inside it as usual. `App.chat.chatWith` is
there if the palette ever starts a chat with a named agent (its "New chat…" uses
`openPicker`, per AC10).

**For leg 8 (and DD13's preview):** every Chats screen at 1280 and wider now has the drawer
open (a 588px pane at 1280); at 1024 the open overlay covers Send and its toggle sits in the
overlay header's corner. Specs that start or inspect a chat can name `chat-drawer`,
`chat-drawer-toggle` and `chat-drawer-settings-link`; `start-a-chat` (SC3) can check the
drawer's facts and "What it can use".

### Leg 7: jump-to-palette (landed, 2026-10-05)

**What landed.** The jump-to palette (reference spec 9, SC5; DD9, DD10, DD14, DD15 A10, A11,
A17), its rail control and Ctrl K, the two modal additions and the rail's bottom slot (DD14),
and one shared Settings page table (AC9).

- **`static/js/settings-pages.js`** (new, `App.settingsPages`, frozen): the seven Settings
  pages in nav order as `{section, label, group, devOnly}`, where `section` is the ROUTE
  segment (`knowledge-indexing`). No dependencies; loaded before `router.js`.
  - **`areas/admin.js`** builds its `navGroups` from it (groups in table order, `devOnly`
    filtered at init after the boot config fetch) and its Providers / Built-in tools page
    headers through `pageLabel(category)`; `ROUTE_SECTION` and the `knowledge` category
    alias stay internal. No page label or group name is left in `admin.js`.
  - **`router.js`**: `SECTION_LABELS` keeps its Library keys; `sectionLabel()` merges the
    Settings labels from the table lazily, on the first `describeRoute`.
- **`ui/modal.js`**:
  - `ariaLabel`: the dialog gets `aria-label`, no `aria-labelledby`, and the card no `h2` and
    no `.modal-dialog-header` row (the body is first). It throws with a `title`, with a
    `closeButton`, or when it is not a non-empty string. The caller's body owns any close
    button and calls `close()`; it is in the Tab wrap.
  - `App.ui.modal.anyOpen()`: `stack.length > 0` over the shared stack (every
    `App.confirmDialog` included).
- **`ui/rail.js`**: `footer`, an array of Nodes (it throws on a non-array or a non-Node),
  rendered last as `.ui-rail-footer` (`margin-top: auto`). The factory binds nothing on the
  nodes, `setCurrent`/`setHref` never touch them, and each is its own Tab stop outside the
  roving arrows. A `.btn-icon` there is 44px (`components.css`).
- **`js/icons.js`**: `search` (Lucide geometry at the pinned version).
- **`js/app.js`**:
  - `mountRail` builds the Jump to control (`rail-jump-to`: `App.ui.button` ghost icon-only,
    `search`, `aria-label="Jump to (Ctrl K)"`, `aria-keyshortcuts="Control+K"`; "⌘ K" /
    `Meta+K` on macOS) before `App.ui.rail()` and passes it as `footer`. Its click calls
    `App.jumpTo.open(control)`.
  - `App.shortcuts`: `isMacPlatform(nav)`, `isJumpToKey(e, mac)`, `jumpToKeys(mac)`, all pure.
  - `onJumpToKeydown`, the one `keydown` on `document`, installed once by `installJumpToKey()`
    after `mountRail()` in the `DOMContentLoaded` handler. It looks up `App.ui.modal` and
    `App.jumpTo` at keydown and calls `preventDefault()` on every match. It ignores an IME
    composition; with the palette open it focuses its input; with any other modal open it
    does nothing; otherwise it opens the palette with `document.activeElement` as the opener.
- **`js/jump-to.js`** (new, `App.jumpTo`: `open`, `isOpen`, `focusInput`, `candidates`,
  `match`, `CAP`):
  - a fresh `App.ui.searchList` in an `ariaLabel` "Jump to" chooser per open (600 at top 96,
    dismissible, `id` `jump-to-dialog`, testid `jump-to`, `initialFocus` the input);
  - the input bar is the search list's field wrapper with the search icon first and the
    palette's own Esc (`jump-to-close`, "Close (Esc)") last; the footer "{Ctrl K|⌘ K} from
    anywhere" and "Enter to open", both on the left;
  - candidates, matching, cap, "where" copy and the empty state as AC7 and AC8;
  - cold data as AC11 (`sessions` forced; a refresh only while this palette is open);
  - a pick closes first, then acts from `onClose` with the captured opener (AC10).
- **`css/components.css`**: the rail footer rules and a "Jump-to palette" block (the bar as a
  row with an inset `:focus-within` ring, the borderless 14px input, 8px 12px rows at regular
  weight, results inside 420px, the footer's 16px inset).
- **`index.html`**: `settings-pages.js` (before `router.js`) and `jump-to.js` (after
  `tool-categories.js`); the asset pin is 82.
- **Design language**:
  - the modal section's "Open labelled chooser" (an `ariaLabel` chooser with the palette's
    bar and body classes and its own Esc), with an `App.ui.modal.anyOpen()` caption in each
    pane;
  - the rail demo's `footer` (a 44px search button in a 360px rail).
- **`scripts/webkitgtk_probe.py`**:
  - it refuses 8485 as well as 8484 (`FORBIDDEN_PORTS`, the DD13 preview instance);
  - new flags `--press-keys` (repeatable; a bad combo exits 2 before any GTK),
    `--key-method event|gtk-test`, `--focus-selector`, `--assert-selector` and
    `--assert-timeout`;
  - the JSON's `keys` block reports the method, each combo's `sent`, `webview_has_focus`,
    `assert_found` and `key_verdict`. A miss ends the run without the resolver and fails it.
- **Docs**:
  - `CLAUDE.md`: a "Jump-to palette (M25 F4 L7)" paragraph, the App shell paragraph's footer,
    and the probe's ports and flags;
  - `the_one/agents.md`: the modal `ariaLabel`/`anyOpen()` and rail `footer` bullets in
    "Control library", the shell invariant, a new "Jump-to palette (client, M25 F4 L7)"
    section, the Settings nav and router label notes, the probe in "UI test apparatus", and
    the demos;
  - the inventory: the Rail and Modal rows, the Search list row, and a Jump-to palette
    composition row;
  - the registry: `jump-to`, `jump-to-close`, `jump-to-input`, `jump-to-result`,
    `rail-jump-to`.

**New tests.**
- `tests/browser/test_flow_jump_to.py` (shared lane, by the complement rule, with no
  `run-tests.sh` change; 20 tests):
  - the rail control (name, `aria-keyshortcuts`, 44px, 12px above the bottom) and the
    dialog's shape;
  - Escape, the Esc button and the backdrop returning focus to it;
  - the resolver and the active row in both themes (↑ ↓, pointer, Enter);
  - Ctrl K from Agents (`defaultPrevented`), from inside the filter field (nothing typed;
    focus back to the field) and from Settings;
  - Ctrl K with the palette open (focus back to its input);
  - Ctrl K with the picker open, and with the confirm open: nothing (two tests);
  - Shift, Alt, Meta and Ctrl+Meta variants and an IME composition (`isComposing`, keyCode
    229): nothing. Caps Lock and a non-Latin layout open it;
  - the platform detector and key matcher unit cases;
  - macOS through `add_init_script` (Meta K opens, Ctrl K does not, "⌘ K");
  - the empty-query board order and cap of 8 (ties in store order);
  - matching each kind, trimmed and case-insensitive, with the chat titled like an agent;
  - an empty install (New chat… and the seven pages);
  - Design language with and without dev mode;
  - each kind opened (an agent with the filter cleared, a chat joined, a knowledge base by
    click, an MCP server, a connector, two Settings pages);
  - New chat… opening the picker, from Agents and from Chats;
  - a pick from a dirty editor: one confirm, opened with `anyOpen()` false and no palette;
    Stay keeps the edit and focus; New chat… asks once; Continue navigates;
  - the forced `sessions` read on every open, a failed `knowledge-bases` read left out;
  - a closed palette never refreshed (a held `sessions` response released after Escape).
- `test_ui_rail_contract.py`: `test_rail_footer_edge_rules_throw` (6) and five footer
  contracts (pinned, nodes in order, 44px, own click handler; own Tab stop outside the
  arrows; untouched by `setCurrent`/`setHref`; no listener but the nav's roving `keydown`;
  the resolver). 11 functions, so 22 tests in both engines.
- `test_ui_modal_contract.py`: `ariaLabel` (no title or header, the body's Esc in the Tab
  wrap and closing to the opener, a plain modal keeping its description, four option
  errors) and `anyOpen()` (across controllers, after a bypassed `close` and a throwing
  `onClose`, counting `App.confirmDialog`). 10 functions, so 20 tests in both engines.
- `tests/test_settings_pages_static.py` (unit, 5):
  - the table;
  - `settings-pages.js` before `router.js`, and `store.js` before `jump-to.js`;
  - the router's Settings routes and dev row equal the table's;
  - no label or group literal in `admin.js` or `router.js`;
  - the three readers read the table, and the palette builds no `#settings/...`.
- `tests/test_webkitgtk_probe_safety.py`: 8485 refused (2), the key flags, combo parsing (4
  good, 5 bad) and a bad combo refused before GTK. 14 new tests; 8485 became 8486 in the
  existing ones.

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, one at a time):

| Gate | Result |
|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (514 files formatted) |
| Static guards (leg 6's set plus `test_settings_pages_static` and `test_webkitgtk_probe_safety`) | **441** passed in 3.3s: leg 6's 413 + `test_settings_pages_static.py` 5 + `test_webkitgtk_probe_safety.py` 23 (9 existing, 14 new). The registry (five new ids), the inventory, the sink guards (every new node is DOM-built), the token definitions and the asset pin (82) are in it |
| `make test-unit` | **5177** passed, 10 skipped, 1808 deselected in 671.1s (11m11s): leg 6's 5158 + the 19 new unit tests (the 62 more deselected are the new browser tests) |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`) | **644** passed, 3 skipped in 166.7s: leg 6's 602 + the rail footer 22 + the modal `ariaLabel`/`anyOpen` 20; the 3 are the in-test WebKit forced-colors skips. The reference page's demo-root, both-panes and resolver checks cover the new demos |
| `--lane shared` (`TEST_TIMEOUT=3600`) | **461** passed in 702.3s (11m42s): leg 6's 441 + `test_flow_jump_to.py` 20 (`test_shell_rail.py` unchanged: the footer sits below the four links and is its own Tab stop) |
| `--lane settings` (the nav reads the shared table) | **178** passed in 338.8s, as leg 6 |
| `--lane agents` | **134** passed, 2 skipped in 328.8s, as leg 6 (the same two static skips) |
| `--lane chats` | **162** passed in 250.6s, as leg 6 |
| `test_flow_jump_to.py` alone | 19/19 before the confirm/picker split, then 20/20 after the falsifications were restored, and 20/20 again inside the shared lane |
| WebKitGTK probe (AC5) | **partially verified (GTK-level key)**, below |

**Falsification.**
- **Close first.** With `onPick` changed to `act()` before `close('pick')`,
  `test_a_pick_from_a_dirty_editor_asks_once_and_stay_returns_to_the_opener` failed: the
  confirm opened with `{anyOpen: true, openDialogs: 1, palette: 1}` instead of
  `{anyOpen: false, openDialogs: 0, palette: 0}`.
- **The `anyOpen()` rule.** With the check dropped from `onJumpToKeydown`, both
  `test_ctrl_k_while_the_confirm_is_open_does_nothing` (`test_flow_jump_to.py:351`) and
  `test_ctrl_k_while_the_picker_is_open_does_nothing` failed: the palette opened over the
  confirm or the picker (count 1, expected 0). The original single test was split in two so
  the confirm case fails on its own.
- Both files were restored from scratchpad copies: `cmp` is clean, a grep for `FALSIFIED`
  is empty, and the file runs 20/20.

**Manual pass.** A dev instance on 8486 (scratch data dir, dev mode, `/proc/<pid>/environ`
verified), seeded with nine agents, three sessions, two knowledge bases, two MCP servers and
a connector; driven with headless Chromium at 1440x900 and 1024x768, Light and Dark.
- The rail control sits 12px above the rail's bottom.
- The palette is centred at top 96, 600 wide (at 1024 too), with the empty query, "lib"
  (five Library rows, ↓ moved the active row) and the empty state.
- The Settings nav renders from the table (four groups in dev mode).
- Escape returns focus to the control.
- No console errors and no horizontal scroll at either width.
- The Design language page shows the rail demo's footer and the labelled chooser: its
  `anyOpen()` caption reads true while it is open and false after it closes.

**WebKitGTK probe (AC5, the leg's last step).** A dev instance on **8486** (scratch data dir, dev mode; `/proc/<pid>/environ` verified),
system `/usr/bin/python3`, WebKitGTK **2.52.6**, `GDK_BACKEND=x11` on WSLg (`DISPLAY=:0`).
The probe now refuses 8484 and 8485.

```
/usr/bin/python3 scripts/webkitgtk_probe.py --url 'http://127.0.0.1:8486/#agents' \
  --data-dir <scratch> --theme dark|light --setup-script <keydown logger> \
  --focus-selector '[data-testid=agents-filter]' --press-keys ctrl+k \
  --assert-selector '[data-testid=jump-to]' --root-selector '[data-testid=jump-to]'
```

| Method | Theme | Result |
|---|---|---|
| `event`: a `Gdk.EventKey` KEY_PRESS/KEY_RELEASE pair through `WebView.event` | dark | **pass**, `ok: true`, exit 0. The WebView had GTK focus and the Agents filter input DOM focus. The page saw one keydown: `key "k"`, `code "KeyK"`, `ctrlKey`, `isTrusted: true`, target `agents-filter`, `defaultPrevented` at `window` (our listener). `[data-testid=jump-to]` appeared, and the resolver passed over it (10 controls, 0 failures) |
| `event` | light | **pass**, the same |
| `gtk-test`: `Gtk.test_widget_send_key` (an X `XSendEvent`) | dark | **no keydown reached the page** (an empty log), although the call returned true; the palette never opened; `unverified`, exit 1 |

**Verdict: partially verified (GTK-level key).** A real GTK key event, delivered with keyval,
modifier state, hardware keycode and the seat's keyboard device, goes through WebKitGTK's
key handling into the page as a trusted Ctrl+K keydown. Our `document` listener takes it
from inside a text field, and nothing in WebKitGTK's GTK layer swallows it first. It does
not prove what an OS-level key does above GTK (a window manager or input method could take
Ctrl+K before GTK), which is why the verdict is partial. pywebview defines no accelerators.
The mission Known Issue (WebView2, Flight 5) now records it.

**Deviations and decisions** (also in "Deviations" below):
1. **A fifth testid, `jump-to-close`**, for the palette's own Esc button (the picker has
   `agent-picker-close`); registered.
2. **The probe gained three flags beyond AC5's two:**
   - `--focus-selector` (step 2's text input);
   - `--key-method` (`event` default; `gtk-test` kept);
   - `--assert-timeout`.

   `Gtk.test_widget_send_key` (an X `XSendEvent`) reported success but never reached the
   page under WSLg's XWayland (an empty keydown log), so the `Gdk.EventKey` pair through
   `WebView.event`, AC5's second method, is the default. A failed assertion ends the run
   instead of polling the root selector into the hard timeout.
3. **The input bar is the search list's field wrapper** with the icon and the Esc button
   inserted (a DOM composition, no new `searchList` option); the inventory row records it.
4. **A store refresh keeps the user's active row only when they moved off the first row.**
   Otherwise the new first row is active (DD10). The first cut kept any active row, so a
   palette opened before `agents` loaded kept a chat active above the agents: the flow tests
   caught it.
5. **`preventDefault()` on every matched key**, including when another modal is open and
   the palette is not opened, so the browser's own Ctrl K never runs over a confirm.
6. **`App.shortcuts`** (in `app.js`) is the home of AC4's pure detector, with the key
   matcher and the copy. On macOS `isJumpToKey` requires Meta without Ctrl ("only
   `metaKey`").
7. **"Untitled chat" is a defensive fallback.** The server stores an empty title as "New
   chat" (`repositories.py:2290`), as `chats-list.js` already assumes; the flow tests reach
   it by blanking a title on the wire.
8. **The palette footer's 16px inset uses the modal's `id` option** (`#jump-to-dialog`);
   the chooser's footer default is 20px.
9. **Files beyond the leg's list:** `ui-modal-section.js` and `ui-lists-section.js` (the
   demos), `test_index_asset_cache_busting.py` (pin 82), `test_webkitgtk_probe_safety.py`,
   and the new `tests/test_settings_pages_static.py`.

**For leg 8:** the `jump-to-palette` spec can name `rail-jump-to`, `jump-to`,
`jump-to-input`, `jump-to-result` (`data-kind`, `data-id`) and `jump-to-close`. The confirm
after a pick is the only modal (`App.ui.modal.anyOpen()` is the observable). The DD13
preview's palette question is the empty query showing agents first (with nine agents, the
first eight).

### Leg 8: behavior-specs-and-close (landed, 2026-10-05)

**Landed** 2026-10-05 (the Developer's acceptance criteria AC1–AC6).

**What landed.** Text only: the two new behavior specs finalized against the shipped build,
the affected specs re-authored, the behavior-test crew file's run rules, a docs sweep and
the four squawks made ready for sign-off. No product code changed (`scripts/run-tests.sh`
changed in a comment only). The Flight Director's part (the DD13 preview, the flight-end
review and the close-gate runs) is not in this entry.

- **AC1, the new specs** (`tests/behavior/start-a-chat.md`, `tests/behavior/jump-to-palette.md`,
  both `draft` → **`active`**, with an `Updated` line). Every step was checked against the
  code of legs 1–7 (the testids, the copy, the routes and the frames), not the drafts:
  - **Preconditions name a FRESH scratch instance** (no agents, providers or sessions
    before step 1), because the recency groups, Recently used, the auto-opened chat and the
    palette's empty-query results are exact only then; never 8484 or the default data dir.
  - **Seeding through the API**, with the exact bodies: the `seed_session`-shaped
    `POST /api/chat/sessions` (`updated_at` = `created_at`, `platform`), providers, agents,
    a knowledge base, an MCP server with a cached tool list (so no server is ever started
    when an agent with it attached is built), and a disabled Discord connector.
  - **The apparatus**: a CDP-driven headless Chromium with real input (never a synthetic
    `dispatchEvent` or an eval `click()`); `start-a-chat` also records the WebSocket frames
    sent (attached before load). **Evidence notes**: focus by `document.activeElement`
    identity, dialogs by `dialog[open]`, the session count by `GET /api/chat/sessions`,
    attributes by DOM eval, the hidden row action needs a real hover, toasts by screenshot.
  - **Variants**: Light and Dark, each in its own fresh browser context, the theme set
    inside it before step 2 (the choice is the context's `localStorage`).
  - **`start-a-chat`** (15 steps): 32 agents and 8 sessions (Today, Yesterday, Last 7 days,
    Last 30 days; the newest a Discord session) → the list and the auto-opened newest chat
    → the picker (title, focus, Recently used exactly `02, 03, 04, 06, 08` with the
    connector's agent excluded, All agents A–Z, the footer) → "10 matching" and ↓ →
    Escape (focus to New chat) → a pick (`#chats/~new/sac-agent-05`, a push; the pending
    row, the header, the new-chat state's `badge--mock` model badge, the placeholder and
    `chat-model`, no telemetry; frames: one `leave`; count unchanged) → a re-pick (a replace,
    no frame) → the first send (one `start_session`, `#chats/{id}` by replace, count +1)
    → a pick then an older row (the pending chat discarded, one `join`) → the drawer at 1440
    (push, 748px pane; facts; "What it can use": the KB, "3 tools", Filesystem 9 of 9,
    Execution 5 of 6 through `disabled_tools: ["shell"]`, Web 4 of 4, Connectors 3 of 3,
    Self-configuration Off; the toggle's `aria-pressed`, 1068px closed) → 1024 (closed on
    arrival, the overlay keeps the 652px pane, Tab into the drawer, Escape back to the
    toggle) → Open agent settings with the Agents filter cleared (no dialog) → the editor's
    Chat from a dirty editor (one dialog; Stay keeps the edit, focus on Chat; Continue
    lands pending) → row delete (arm, confirm, focus to the next row) → teardown.
  - **`jump-to-palette`** (14 steps): Ctrl K from Agents with nothing focused (the dialog's
    `aria-label`, the Esc button, the empty query's 8 agents, the footer) → ↓↓, ↑, ↓↓↓ over
    `jtp-agent-1`'s three results (clamped, no wrap), then `tiles` → Enter opens the chat →
    the rail control and a knowledge base → an MCP server and a connector → a Settings page
    → New chat… from Settings (the picker, one dialog) → Ctrl K from inside a dirty
    Description (nothing inserted) → a pick asks once (the palette closed first) → Stay
    (focus back on Description) → Continue (the filter cleared) → Escape from the filter
    and the Esc button from the rail control (focus back to each) → teardown.
- **AC2, the re-authored specs** (each with an `Updated` line). The leg's verification grep
  (`chat-welcome-item|agent-select|new-chat-btn|session-agent-badge` over
  `tests/behavior/*.md`) now has **no hit at all**; `.session-item`, "welcome item",
  "session agent badge", "session list" and "agent selector" have none either.
  - `workbench-navigation` step 2: the Chats list and New chat, the empty state, and the
    picker listing `wbnav-agent` (opened, then Escape); the hash may be `#chats/{id}` when
    the instance holds a conversation. Out of Scope names `jump-to-palette` and
    `start-a-chat`; the Variants line now says the theme is set inside the variant's own
    context.
  - `shell-navigation-smoke` step 3: the Chats list, then exactly one of a conversation,
    the empty state (`chat-empty-new-btn`) or the guidance (the list's New chat disabled);
    step 1 also names the rail's Jump to control.
  - `chat-roundtrip` step 3 (New chat, the picker, a pending chat), steps 4 and 6 (the
    first send creates `#chats/{id}`), and the Dark variant in its own fresh context.
  - `vision-round-trip` step 1 (the picker; the header instead of the badge), step 3 (the
    first send creates the session), step 8 (the Chats list) and the locators.
  - `agent-purge-now-clears-history` step 6 (the Chats list, by `data-id` and title; the
    bystander's row present; the Purge-now `sessions` invalidation).
  - `stub-connector-round-trip` step 5 (`chat-row[data-id]` with its `stub` badge, not
    `.session-item`) and its browser observable.
  - The generic "start a new chat" steps (the leg 4b hand-off): `agent-governance-and-search`
    step 6 (and step 8 names where the readout sits), `chat-loop-hang-and-cancel` step 1,
    `extended-thinking-tool-turn` step 1.
  - `extended-thinking-tool-turn` step 5 (the leg 5 hand-off): step 1's pending chat shows
    no readout, so the baseline is the first joined reading (0%, reset when step 3's send
    joins the chat).
  - **Every other hit** (generic starts that the grep's phrasing missed, same fix):
    `directory-lookup-send` step 2, `agent-self-revision-propagation` steps 1 and 5,
    `anthropic-plan-chat-parity` steps 2 and 5.
- **AC3, the crew file** (`.flightops/agent-crews/behavior-tests-execution.md`). The six
  rules are now in the **Executor and Validator initial prompts** ("PROJECT RUN RULES" plus a
  lifecycle line each): per-run scratch subdirectories
  (`<scratchpad>/{test-slug}-{run-timestamp}/`); no unrequested state-changing actions (and
  read-only fresh observations for the Validator); the input-delivery probe before
  `[READY]` (a real click and key press reach capture-phase listeners, else
  `[BLOCKED:input-delivery]`); "you are resumed by SendMessage after each step" (also in
  both per-step prompts); the variant rule (its own fresh context, set before the first
  checkpoint; the Validator checks it is in effect); the toast rule (a screenshot, never
  `offsetParent`). The apparatus discovery names the CDP-driven Chromium as the project
  default, goldfinch unused. A short "Run rules (this project)" section gives the why for
  each, and the Interaction Protocol gains "Variants and concurrent runs". The required
  `## Crew` / `## Interaction Protocol` / `## Prompts` sections, the signal names and every
  fenced prompt are intact.
- **AC5, the docs sweep.** Checked against the code of legs 1–7: `CLAUDE.md` (the lanes and
  `--list`, the Chats list and picker, the pane and drawer, the agent editor's Chat, the
  composer, the palette, `_chats.py`, `App.store`'s `sessions`), `the_one/agents.md` (the
  `/ws` protocol, the start flow, the list and picker, the pane, the composer, the drawer and
  `App.toolCategories`, the palette, the store's `sessions` row, the editor Save/Cancel
  contract), the inventory and the testid registry (every new testid has a row; `agent-select`
  and `new-chat-btn` are in the Retired table). Drift found and fixed:
  - the full browser suite's runtime: `CLAUDE.md` said "~13min" (lanes) and "~12.5min"
    (`TEST_TIMEOUT`), and `scripts/run-tests.sh`'s comment "~13min"; it is about 38 minutes
    (the six lanes summed; it was already ~33 at the end of Flight 3);
  - `agents.md`'s start-flow section called `test_flow_chat_start_flow.py` "the flow on the
    old DOM" (legs 4a and 4b moved it onto the picker and the new pane);
  - `agents.md`'s browser apparatus doctrine still called goldfinch the canonical apparatus;
    it now says behavior runs use the CDP-driven Chromium (M25 F2–F4) and points at the crew
    file's run rules;
  - the inventory's provider model-picker row still said "a selection listbox is a separate
    Flight 4 control"; Flight 4 built `searchList` instead.
- **AC6, the squawks.** 0110, 0111 and 0118 already carried Corrective Action and
  Verification (legs 5, 3b and 6); every test name and grep they cite was re-run and
  resolves. **0117** (implemented in leg 1) is now `completed` with its Corrective Action
  (the `contracts` lane, `shared` as the complement, `--list`, the partition test, the
  docs) and Verification (the partition by file list and by count, each lane green, every
  Flight 4 contract landing in `contracts`, the leg 8 `--list` counts). Each of the four
  has a leg 8 re-check line; all four await the flight-end Reviewer's sign-off.

**Gates** (browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and
`PYTHON=.venv/bin/python`, `-x --timeout 60 -q`, one at a time, after every text change but
the flight log; the unit suite ran beside the agents and library lanes):

| Gate | Leg 1 baseline | Leg 7 | Leg 8 |
|---|---|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (499 files) | clean (514) | clean (514 files) |
| Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_control_inventory`, `test_nav_helper`, `test_store_static`, `test_index_asset_cache_busting`, `test_ui_library_source`, `test_run_tests_lanes`, `test_tool_categories`, `test_settings_pages_static`, `test_webkitgtk_probe_safety`) | 393 (the first nine) | 441 | **441** passed in 3.4s |
| `make test-unit` | 5067 passed, 10 skipped | 5177 passed, 10 skipped | **5177** passed, 10 skipped, 1808 deselected in 728.1s (12m08s) |
| `--lane chats` | 42 | 162 | **162** passed in 252.7s |
| `--lane agents` | 132 (130 + 2 skipped) | 134 + 2 skipped | **134** passed, 2 skipped in 327.3s (the two static `@pytest.mark.skip`s) |
| `--lane library` | 146 (145 + 1 skipped) | 145 + 1 skipped (leg 6) | **145** passed, 1 skipped in 488.1s (the committed skip) |
| `--lane settings` | 178 | 178 | **178** passed in 341.8s |
| `--lane contracts` (`THE_ONE_REQUIRE_WEBKIT=1`) | 556 + 3 skipped | 644 + 3 skipped | **644** passed, 3 skipped in 166.0s (the three in-test "WebKit has no forced-colors emulation" skips; under `REQUIRE_WEBKIT` a WebKit launch failure fails) |
| `--lane shared` (`TEST_TIMEOUT=3600`) | 438 | 461 | **461** passed in 704.1s (11m44s) |
| Union by count | 1495 | — | **1730** = 162 + 136 + 146 + 178 + 647 + 461, exactly `-m browser tests/browser/` (1730 of 1742, 12 deselected) |

Across the flight: unit +110 (5067 → 5177), browser +235 tests (1495 → 1730): chats +120,
contracts +88, shared +23, agents +4.

**Deviations and decisions** (also in "Deviations" below):
1. **Both specs require a fresh scratch instance**, so their expectations can be exact
   (groups, Recently used, the auto-opened chat, the palette's first 8). The drafts allowed
   any instance with no `sac-`/`jtp-` data.
2. **`jump-to-palette` exercises ↑ and ↓ in a step of its own** (`jtp-agent-1`'s three
   results, clamped). The draft's ↑/↓ on `jtp-kb` was a no-op: it has one result.
3. **`start-a-chat` picks by typing and Enter in step 6, by a click in step 7**, so both
   pick paths are covered and no step depends on scrolling the 37-row picker.
4. **`start-a-chat` seeds exact drawer facts**: `sac-agent-03` has two sessions, a KB, an
   MCP server with a 3-tool cache (no server start: the factory hydrates from the cache) and
   `disabled_tools: ["shell"]`, so "What it can use" has exact counts.
5. **Step 11 reaches the drawer by Tab from the message box**: the drawer's only focusable
   is its footer button, after `<main>` in DOM order.
6. **AC2 went beyond the listed specs**: the three generic starts the grep's phrasing missed,
   `shell-navigation-smoke` step 1's Jump to control, and the fresh-context variant wording
   in `workbench-navigation` and `chat-roundtrip` (the Flight 3 debrief's variant lesson).
7. **The crew file also carries the apparatus default** (Flight 2 recommendation 1: the
   CDP-driven Chromium, goldfinch unused), a "Run rules" rationale section and a protocol
   subsection; the per-step prompts repeat the resume line.
8. **Docs drift fixed beyond the sweep's list**: the suite runtime in `CLAUDE.md` and the
   `run-tests.sh` comment, and `agents.md`'s goldfinch doctrine.
9. **The unit suite ran concurrently with the agents and library lanes** (20 cores); every
   number matches leg 7's, and no lane needed a re-run.

**For the Flight Director:** the close-gate specs are `active`. `start-a-chat` and
`jump-to-palette` each need their own fresh instance (dev mode, a scratch data dir, 8486 or
higher; 8485 is the preview), and each variant its own fresh browser context with the theme
set first. `vision-round-trip` needs a live Anthropic key (it cannot run on the mock).

---

## Flight Director Notes

- 2026-10-05: **Flight drafted** by the Flight Director, autonomously.
  - **Why there was no operator interview.** The mission's constraints make execution
    autonomous, with only three human touchpoints (sign-off, the post-Flight-3 checkpoint,
    the alignment flight). DD13 adds a non-blocking preview instead.
  - **Inputs:**
    - the Flight 4 research digest;
    - the Flight 3 debrief and checkpoint outcome;
    - reference spec §2, §5, §9, §10 and §15.
  - **Premise checked before locking DD1.** `app.py:2688-2700`: a message that arrives with
    no bound session already auto-creates a session, sends `session_joined`, then processes
    the message. `start_session` makes that path explicit, takes an agent, and first leaves
    any bound session.
  - **Draft shape:** 16 DDs and 6 legs (7 after Architect cycle 1, 8 after cycle 2).
  - **Branch.** `flight/04-chats-and-jump-to` stacks on `flight/03-list-and-detail`
    (`c3f0a86`), because PR #219 is still open.
- 2026-10-05: **Architect cycle 1** (Opus) returned "approve with changes": 1 high,
  10 medium and several low issues, plus 6 questions. All applied.
  - **High: the pending-chat isolation.** With no frame on pick, the socket stays bound to
    the previous session. Its frames (which carry no `session_id`) render into the pending
    pane, and `done` or a reconnect auto-joins the pending chat away.
    - **Fix:**
      - a non-persisting `leave` action on pick;
      - auto-join and drain suppression while pending or starting;
      - `serializeState` `new/{agent}`;
      - a transition table required in leg 2a.
  - **The first-send transition.**
    - The joined frame carries `is_processing: true`, so the first turn behaves like any
      turn.
    - The server orders `start_session` as validate, then create, then swap, then joined,
      then spawn. It catches broadly and sends a typed `start_failed`.
    - **Reconnect.** The client generates the session id, and `start_session` is idempotent
      on it (question 2). That trades neither a duplicate nor a lost first message.
    - **`new_session` removed** (question 4).
  - **Stale premises corrected:**
    - `--scrim` already exists per theme (dark 0.5), and Flight 1 resolved A30. No new
      token; the dark 0.5 versus 0.3 is a preview question (question 3).
    - The WebKitGTK probe cannot test Ctrl K with synthetic events. Leg 5 adds a real key
      injection on 8486 or higher, otherwise the premise is "unverified".
    - Squawk 0110 needs `aria-label`, because the resolver does not skip `aria-hidden`.
    - Retiring `agent-select` needs an exact match, because `_RETIRED_RE` would hit
      `agent-select-empty`. Class fragments go into `RETIRED_SELECTORS` only.
    - The sink removal is split across legs 2b and 3.
    - The citation line numbers are fixed.
  - **The `listPane` row-action contract:** the tab policy, focus restore to the
    neighbouring row, armed-state preservation, the `dataset` option, and the block slot
    below the `<header>`.
  - **Leg 2 split** into 2a `start-flow-core` (protocol and state on the old DOM, with the
    test migration) and 2b `chats-list-and-picker`. `drawer` moved to leg 4 and the rail
    slot to leg 5, so each control's API is shaped by its consumer. **7 legs.**
  - **Spec steps that could not run, fixed:**
    - no dirty source exists on Chats, so SC2 is tested through the agent editor's Chat
      from a dirty editor;
    - filtering before opening hid the target row.
  - **Also:**
    - `go()` takes a string (`go({…})` stringifies), so hrefs are built with
      `App.router.href`;
    - `#chats/~new/x` belongs in `PARITY_CORPUS`, not `DD2_ROWS`;
    - the announce key includes the agent;
    - the store `prime` clears in-flight requests; the invalidation rows and the
      `LITERAL_LIST` are added;
    - `activate` refreshes sessions;
    - the `index.html` asset pin;
    - the time formats are hand-formatted;
    - Ctrl K is Meta K on macOS;
    - the IME guard;
    - `App.ui.modal.anyOpen` and `ariaLabel`;
    - `App.studio.clearAgentFilter`;
    - the drawer skips unknown MCP ids and is hidden with no chat;
    - local WebKit must run (`THE_ONE_REQUIRE_WEBKIT=1`);
    - the WebView2 Ctrl K check is carried to Flight 5 in the mission's Known Issues.
  - **Question 5** (Ctrl K on macOS): Meta K only. **Question 6** (the drawer with no
    chat): not rendered.
  - **The changes are substantive**, so cycle 2 follows. It is the last cycle under the
    methodology cap.
- 2026-10-05: **Architect cycle 2** (Opus) returned "approve with changes": 1 high,
  6 medium and 11 low issues, plus 3 questions. It spot-checked every Citation Audit row:
  all accurate, with three line fixes.
  - **High: frames already in flight.** A late `session_joined` from a cold-load auto-join
    still took over the pending chat (`chat.js:586-593`, `:1230`).
    - **Fix:** the client state gates every inbound frame (`idle`, `joining`, `joined`,
      `pending`, `starting`).
    - The 18 `currentSessionId` null checks become explicit state checks.
  - **`start_session`:**
    - "already exists" is `_get_or_restore_session`, and behaves exactly like `join`, even
      for another agent's session (question 2: yes);
    - a module-level id reservation closes the cross-socket reconnect race;
    - the create is strict, because the persist failure is otherwise swallowed;
    - a shared `_validate_message_payload()` includes the content build;
    - every non-success exit sends `start_failed`;
    - a missing or `"default"` agent is rejected (question 1: yes);
    - `is_processing: true` overrides the lock-derived builder.
  - **The client:**
    - busy, hold and Stop key on `currentSessionId || startingId`;
    - a reconnect while joined re-joins (a pre-existing gap);
    - the bubble is kept only when the history is empty;
    - a sync dropped off Chats re-syncs on hydrate;
    - the interim pending UI on the old DOM is defined;
    - the pending row has no discard action (question 3: no).
  - **The router:** `href({destination:'chats', create:true, agent})`, because `id:'~new'`
    would encode to `%7Enew`. Plus `resolve` folding, `areaSubToRoute`, the
    `describeRoute` key, a **silent** first-send sync, `_nav.canonical`,
    `legacy_hash` raising, and `PARITY_CORPUS` in `test_router_core.py`.
  - **The drawer** is created once and toggled with `hidden`, so `aria-controls` always
    resolves (`_a11y_resolve.js:76-82`). The toggle moves to the drawer's leg.
  - **`RETIRED_EXACT`** for `agent-select`, keeping the deliberate left-only boundary. The
    class fragments `session-item`, `session-list` and `list-item-delete` are added.
  - **The test rewrites are budgeted:** the recovery test is inverted; leg 4's
    old-surface tests are rewritten.
  - **Smaller items:** the icons (`square-pen` already exists; `settings` added), the
    `keyCode 229` IME guard, the picker opener from the palette, the leg 3 invalidation
    row, `crypto.getRandomValues`, and the `leave` semantics (never cancels, touches
    `last_activity`).
  - **Suggestions adopted:**
    - **The leg split.** Leg 2a becomes `ws-start-protocol` (server) and
      `start-flow-client` (the migration runs seam first). **8 legs.**
    - **Built where consumed.** `setQuery` moves to leg 6, and `ariaLabel` and `anyOpen`
      to leg 7.
    - **All chat sinks** are removed in the list-and-picker leg.
  - **The specs** are corrected:
    - the intent's SC2 clause;
    - the seeded agents named, with "today" at now minus a few minutes;
    - the frame wording;
    - "Tab into the drawer";
    - `chat-new-state`;
    - a connector seeded and opened in `jump-to-palette`.
  - **The cap is reached.** The fixes are prescribed concretely, and they are applied
    without a third cycle. Per-leg design reviews re-verify: legs 1, 2, 3, 4, 6 and 7 are
    high-risk.
  - **Flight set `ready`.**
- 2026-10-05: **Execution started** (`/mission-control:agentic-workflow`). The flight
  moved to `in-flight`. PR #219 is still open, so the branch stays stacked, and the
  rebase is re-checked at each leg start.
- **Leg 1 `controls-and-data` designed.** **Risk tier: high.** It touches shared
  control-library factories with existing consumers (`listPane`, `modal`), the store
  contract and its pins, and the lane script that every verification uses. A Developer
  design review (Sonnet) follows.
- **Leg 1 design review** (Developer, Sonnet): "approve with changes", with 1 high and
  7 medium issues. All are folded in.
  - **High.** The neighbour-row focus fallback, applied to all rows, would break the
    Flight 3 pin `test_ui_library_contract.py:1172-1184`. It is narrowed to an
    **action**-focused delete; plain rows keep the same-id, then selected, then first
    rule (question 1).
  - **Medium:**
    - `focusedEntry` must see the action (an `li.contains` and `action` ref), with keys on
      an action;
    - `_session_summary` collides with an `agents.md` anti-pattern note, which is updated
      (one scalar is sanctioned), and a REST/WebSocket key-subset pin is added;
    - the index pin is 73 with the demo section's tag (question 2);
    - the invalidation sites are corrected: rename and Purge now only. There is no
      per-session client purge, and agent delete leaves sessions (questions 3 and 4);
    - the chooser's `aria-describedby` and default focus are specified, the close button
      is in the Tab wrap, and the inline `width`/`top` are scoped;
    - `--list` is parsed explicitly and errors without `--lane` (question 5);
    - the contrast pairs are named (`--accent-translucent-hover` is not yet audited as a
      background; chats-row 11px text on the selected wash, with A24 to check);
    - the armed-`li` reuse updates `entry.item` and drops a missing item safely;
    - the IME guard, the listener-cleanup case, and the WebKit userland note.
  - **No second cycle.** The high was resolved by **narrowing back** to the existing
    behaviour, and the rest are prescriptive edits. Leg 1 → `ready`.
- **Leg 2 `ws-start-protocol` designed.** **Risk tier: high** (WebSocket lifecycle,
  session creation, concurrency). Its design review (Developer, Sonnet) runs in parallel
  with leg 1's implementation; it is read-only, and leg 2 comes after leg 1.
- **Leg 1 implementation** spawned (Opus, as in Flight 3's implementation legs).
- **Leg 2 design review cycle 1** (Developer, Sonnet): "approve with changes", with
  2 high and 5 medium issues. All are folded in.
  - **High:**
    - the reservation must be taken **first**, as a synchronous check-and-set, with the
      lookup inside it;
    - a `/reset` first message would leave the client stuck busy, so it is rejected with
      `start_failed` (question 1).
  - **Medium:**
    - the `try` wraps only the strict create;
    - the validator returns an `empty` flag and type-checks its fields (question 3);
    - the content-build order change is accepted and recorded;
    - the test harness is prescribed (`isolated_db`, a fake factory, awaitable script
      steps, `gather` over two endpoints, teardown);
    - the degraded path removes whatever was bound;
    - `_build_session_joined_ok(is_processing=…)`;
    - the existing-id join's `is_processing` comes from the inflight set.
  - A waiter whose creator failed becomes the creator (question 2).
  - **Leg 3 constraint recorded:** re-send `start_session` while starting, never `join`.
    A `join` can pop a just-created in-memory session before its DB insert.
  - The changes are substantive (the reorder), so cycle 2 is spawned. It runs in parallel
    with leg 1's implementation.
- **Leg 2 design review cycle 2** (Developer, Sonnet): "approve with changes", with
  1 high and 4 medium issues. All applied; the cap is reached, and leg 2 → `ready`.
  - **High.** `wait_for` on the shared reservation future would cancel it for every
    waiter, so the wait becomes `wait_for(shield(fut), _START_RESERVATION_WAIT_S)`, with a
    timeout test.
  - **Medium:**
    - the lookup gets its own narrow `try` → `start_failed`;
    - `_restore_session`'s skip-rebuild guard also checks the inflight set (AC8b);
    - the harness citation is fixed (`test_cancel.py`'s `_LLMShim`/`_QuickAgent`, a
      persisting `step`, no agent seeding);
    - the teardown also clears `app._sessions` and awaits tasks;
    - the stale text is fixed: the `NamedTuple`, `/reset` only in the message path, the
      harness step, the waiter loop, and the `message` type contract.
  - **Low:** the strict create pops on `BaseException` (cancellation); the bind and
    subscribe come before the first send.
  - **Decision (the reviewer's question).** A `start_session` re-send to an existing id
    whose history is empty, with nothing in flight, **delivers** the message. A disconnect
    between the create and the spawn therefore never loses the first message. This
    refines DD1's "not processed again" to "processed exactly once".
- **Leg 3 `start-flow-client` designed.** **Risk tier: high** (the client session
  lifecycle, the router contract, a large test migration). Its design review runs in
  parallel with leg 1's implementation.
- **Leg 3 design review** (Developer, Sonnet): "approve with changes", with 3 high and
  8 medium issues. All applied.
  - **High:**
    - a `system` "Cannot start chat" frame, or a foreign `session_joined` (the server's
      auto-create on a `not_found` join), would strand the client in `joining`. Both now
      go to `idle` with a notice (question 1);
    - `onclose` re-enables Send while `starting`, so a plain `message` could slip out. Now
      `isCurrentBusy()` is true in `starting`, and `onclose` keeps the slot and the
      disabled Send there;
    - a reconnect re-join could target a session deleted while the socket was down, and
      the server would auto-create a default-agent session. Now it is checked against the
      fresh `session_list`, else `idle` (question 2).
  - **Medium:**
    - missing table rows: a same-agent pick is a **no-op** (question 3);
    - `leave` is sent from `joining` too;
    - the full `start_failed` restore (bubble, busy, re-staged images, the held message);
    - the remembered `startedFrom`;
    - a `joined` re-join goes through `joining`;
    - a send with the socket closed returns before `startSend`;
    - `/reset` in `pending` is a client-side no-op;
    - the agent segment is percent-encoded in the sub;
    - the router specifics (`parse`, `resolve`, `areaSubToRoute`, `href`, the
      `describeRoute` special case, and pinning the silent first-send sync);
    - the synchronous hydrate (a loading pane on a cold load);
    - the `renderHistory` branch;
    - the hold slot keys on `activeId()`, so there is no carry-over;
    - the OAuth popup close is global;
    - every null-check site (not "18"), with the exports keeping their meaning;
    - the interim row survives re-renders;
    - per-socket reconnect detection and two drop-variant tests.
  - **Bare `#chats` while pending** keeps the pending chat (question 4, AC9b).
  - **Leg 3 is split** (question 5):
    - **3a `chats-test-seam`**: the mechanical migration on today's semantics, with no
      app change;
    - **3b `start-flow-client`**: the state machine, the router and the flip.

    **9 legs.** 3a → `ready`, with no design review: it is low risk, a test-only
    mechanical migration whose gate is that every lane stays green. 3b gets a **second
    design review** before its implementation, because its changes were substantive.
- **Leg 3b design review cycle 2** (Developer, Sonnet): "approve with changes", with
  2 high and 5 medium issues. All applied; the cap is reached, and 3b → `ready`.
  - **High 1.** The `joining` "another id" row could not tell a server auto-create from a
    late reply to a superseded join. **Root fix, taken from the reviewer's question 2:**
    leg 2 gains **AC8a**, where `join` of an unknown id sends `join_failed` and creates
    nothing. So a foreign `session_joined` is always a late reply and is dropped, and
    `join_failed` → `idle` with a notice. The "Cannot start chat" row is gone.
  - **High 2.** The reconnect hook acted on bindings made on the current socket, and the
    rebind window let a plain message reach an unbound socket.
    - **Fix:**
      - a per-socket `boundOn` record;
      - `starting` re-sends at `onopen`;
      - `joined` and `joining` act at the first list;
      - a `rebinding` flag gates Send and Stop;
      - a same-id `session_joined` in `joined` is dropped.
  - **Medium:**
    - `leave` from `starting`, and a list refresh when a dropped `session_joined` comes
      from an abandoned start;
    - `/reset` in `starting`;
    - one `idleRules(list)` on every list while `idle`, with `suppressAutoJoin`;
    - the dropped-send test closes the socket. **A lost reply on an open socket is
      deliberately unrecovered** (question 1), recorded under squawk 0111;
    - the `session_joined` side effects run, with only `renderHistory` conditional;
      `inFlightSessions` keys on `activeId()`.
  - **Low:**
    - numbering and stale text;
    - the `reconnectAction(listedIds, boundOnEarlierSocket)` signature, with
      `startedFrom` in `state()`;
    - a degraded re-send restores the composer;
    - the exact router edits (`parse`, `resolve`, `areaSubToRoute`, `href`,
      `describeRoute`, the URIError heal);
    - the header button is inert with no agent.
  - **Leg 2 updated** with AC8a (`join_failed`), still `ready` and not yet in-flight.
- 2026-10-05: **Leg 1 landed** (`[LAND:leg]`).
  - **Gates:**
    - lint clean;
    - static guards 393;
    - unit 5,067 (10m59s);
    - **contracts lane 556, 3 skipped (2m25s)**, with WebKit running;
    - shared lane 438 (10m54s; it was 867 in 12m38s before the split);
    - chats lane 42.
  - **The six lanes partition the suite**, by file list and by count (1,495 tests).
  - Seven deviations are recorded in the leg entry. Notably:
    - `--fg-muted` fails AA on the active-row wash, so the active row uses
      `--fg-secondary`;
    - a reveal class lets a hidden action take focus during a restore;
    - the testid guard now extracts `inputTestid` and `rowTestid`.
  - The Flight Director accepts all seven; they go to the flight-end review.
  - No leftover processes; PR #219 is still open.
- **Leg 2 implementation** spawned (Opus).
- 2026-10-05: **Leg 2 landed** (`[LAND:leg]`).
  - **Gates:** lint clean (500 files); unit 5,138 (+71; 11m31s); chats lane 42; the
    hash-routing and router-items spot check 40; the timing-sensitive classes repeated
    8 + 5 times, all green.
  - **Falsifications:** existing-id, reservation, and shield.
  - **Four deviations, all accepted:**
    - the waiter's lookup runs inside a fresh reservation;
    - delivery on an existing id also needs a free session lock;
    - the error texts were chosen by the Developer;
    - the recorded order changes.
  - **Squawk 0119 logged:** a degraded `join` of the already-bound session leaves the
    socket subscribed. It predates this flight and is out of scope.
- **Leg 3a implementation** spawned (Opus). It is low risk and mechanical, with no design
  review (decided at 3a's design).
- 2026-10-05: **Leg 3a landed** (`[LAND:leg]`).
  - **The migration:** 20 files moved onto `_chats.py`. `session-agent-badge` went from
    51 uses to 0, and `chat-welcome-item` from 45 to 2, both in the allow-listed
    `test_flow_new_chat.py`.
  - **Lanes:** chats 44, shared 439, settings 178, library 145 (1 skipped), agents 130
    (2 skipped). Unit 5,140. Lint clean.
  - **No `the_one/` change.**
  - **Eight deviations, accepted.** Notably `start_chat`'s third path (the header button
    for the open agent), and that `agents.md` is untouched (handed to 3b).
  - **Leg 3b updated** with the hand-off (the helper bodies and `test_chats_helper.py` to
    flip, plus the `agents.md` note).
- **Leg 3b implementation** spawned (Opus). It was designed and reviewed twice (the cap).
- 2026-10-05: **Leg 3b landed** (`[LAND:leg]`).
  - **Gates:**
    - lint clean;
    - static guards 398;
    - unit 5,143;
    - chats lane **113** (from 44);
    - shared 441;
    - agents, settings, library and contracts unchanged.
  - The new start-flow and reconnect tests passed 15/15, three runs in a row.
  - **Falsifications:** AC3, AC8, AC9 and AC19.
  - **The null-check table** has 20 sites. Squawk 0111 is closed, pending sign-off.
  - **Squawk 0120 logged** by the Developer: a `cancel` handled before a turn starts gets
    no `cancelled` reply. It predates this flight.
  - **14 deviations, accepted.** Notably:
    - heal leaves a live conversation alone;
    - a stale agents cache is re-fetched before healing;
    - a one-shot pick flag, so the header New Chat still picks after a first send;
    - a send in `idle` or `joining` keeps the text;
    - small state-API differences.
- **Leg 4 `chats-list-and-picker`.** Citations re-verified against the post-3b tree.
  **Risk tier: high** (a large UI replacement, retired selectors, sink removal, and many
  test rewrites). A design review (Developer, Sonnet) is spawned.
- **Leg 4 design review** (Developer, Sonnet): "approve with changes", with 3 high and
  7 medium issues. All applied.
  - **High:**
    - the test inventory was incomplete: more files bypass `_chats.py` or pin old
      classes. Each is now listed;
    - setup incomplete contradicted `requestPick`'s inertness. Decision: **New chat is
      disabled** while setup is incomplete, and the guidance explains (question 1);
    - `openPicker` had no cold-area trigger. It now navigates to Chats first and returns a
      Promise (question 3).
  - **Medium:**
    - the provider type comes from the `providers` store, with a fallback;
    - the pending row is a **link** to its own `~new` route, with id `__pending__`
      (question 4);
    - one `renderChatsList()` is called from the subscription and every transition;
    - one `h1` per state: the "Hello." greeting is kept (question 2);
    - the header title is read from the `sessions` store (question 7);
    - `composer.js` is extracted as a DOM builder rather than deferred;
    - the day-7 boundary goes to Last 30 days; the labels are sentence case; the
      connector badge is a neutral span;
    - picking runs from the modal's `onClose`, so no guard dialog stacks under it;
    - the picker is built fresh per open.
  - **Question 5:** the picker's empty state is text only. **Question 6:** `.chat-chrome`
    is kept.
  - **Leg 4 split** (question 8):
    - **4a `chats-sidebar-and-picker`**: the list, the picker, `openPicker`, and the
      dropdown and old list retired;
    - **4b `chats-pane`**: the header, the new-chat state, the empty and guidance states,
      `composer.js`, the remaining retirements, the seam-guard swap, and the last sink.

    **10 legs.** Both are `ready`. There is no second cycle: the fixes were prescribed by
    the reviewer, and the flight-end review covers the code.
- **Leg 4a implementation** spawned (Opus).
- **Leg 4a landed** (`[LAND:leg]`).
  - **Gates:**
    - the mid-leg chats gate 113;
    - lint clean;
    - static guards 400;
    - unit 5,145;
    - lanes: chats **128**, contracts 556, agents 130, settings 178, library 145, shared
      441, with one deterministic re-pin of `.active` → `aria-current` in
      `test_router_items` before the green run.
  - The Recently-used connector exclusion falsification was done.
  - A manual pass at 1440 and 1024, both themes, on 8486.
  - **12 deviations, accepted.** Notably:
    - `--sidebar-w` is removed;
    - "Loading agents…" shows while the store loads;
    - three extra tests were re-pinned because they named retired selectors.
- **Leg 4b implementation** spawned (Opus).
- **Leg 4b landed** (`[LAND:leg]`).
  - **Gates:**
    - lint clean;
    - static guards 399;
    - unit 5,144;
    - lanes: chats **136**, shared 441, contracts 556, agents 130, settings 178,
      library 145;
    - `test_flow_chat_pane.py` 8/8, three runs in a row.
  - **No `areas/chat*` sink is left**, with a pin.
  - The A20 falsification was done. A manual pass on 8487.
  - **13 deviations, accepted.** Notably:
    - the welcome is shown only by the idle rules;
    - the pending log stays in the DOM at zero height, so a start failure's error stays
      visible;
    - `chat-welcome-list` is retired too.
  - The hand-offs for legs 5, 6 and 8 are recorded in the leg 4b entry.
- **Leg 5 `composer-and-telemetry`.** Citations re-verified, and the 4b hand-off folded
  in. **Risk tier: low.** It is a restyle of one surface within established patterns:
  testids are kept, the textarea keeps `fill` plus Enter working, and no shared interface
  or lifecycle changes. So there is no per-leg design review; the flight-end review covers
  it. Implementation is spawned (Opus).
- **Leg 6 design review** (Developer, Sonnet), run in parallel with leg 5: "approve with
  changes", with 2 high and 6 medium issues. All applied, and leg 6 → `ready` with no
  second cycle (the fixes are prescriptive).
  - **High:**
    - the default Playwright viewport (1280) is push mode, so the drawer is open in every
      Chats test. **Accepted as the product default** (question 1): the full `chats` and
      `shared` lanes verify it, and full-width assumptions get fixed;
    - `test_shell_rail.py` pins the shell-row children, so it is added to the leg.
  - **Medium:**
    - **a static `index.html` slot** (question 2); chat fills and toggles it and hides it
      on leaving Chats;
    - `.app-shell-row` gets `position: relative`, with a `[hidden]` guard;
    - `App.toolCategories` exports every derived shape, so migration is mechanical. A
      static test pins the table against `_TOOL_CLASSES`, including the connector lookup
      tool (question 3);
    - the AC8 data shapes are corrected (`mcpToolCount` takes a source object), with the
      built-ins-only effective logic;
    - three explicit default, deleted and loading states, and the drawer unsubscribes;
    - `setQuery` is silent (question 4); `clearAgentFilter` is a safe stub before studio's
      init.
  - **Low:** `App.ui.button` for Chat; the grep-derived `checkDirty` list; the `agents.md`
    homes; the icons are unconditional; drawer tests at 1280.
- **Leg 7 design review** (Developer, Sonnet), run in parallel with leg 5: "approve with
  changes", with 3 high and 5 medium issues. All applied, and leg 7 → `ready` with no
  second cycle.
  - **High:**
    - `ariaLabel` collided with the modal's header and h2, so a chooser with no title
      omits both, and the palette's body owns its close button (question 1, option c);
    - New chat… calls `openPicker({opener})` **alone** (question 2);
    - AC5 has a concrete method: GDK `Gtk.test_widget_send_key` with a focused WebView
      (there is no `xdotool` on this host), plus new probe flags and refusing 8485. A GTK
      pass is recorded as **"partially verified"** (question 6).
  - **Medium:**
    - `anyOpen()` is `stack.length > 0`, since confirms are in the stack;
    - **`settings-pages.js` loads before `router.js`**, keyed by route segment, with the
      router building the Settings labels lazily (question 3);
    - the AC4 detection, key matching and lazy lookups;
    - the opener is captured and passed to `go()`, and Stay keeps the palette closed;
    - `sessions` is force-fetched on open (question 4);
    - refresh happens only while open.
  - **Low:**
    - platform-aware copy and `aria-label` (question 5);
    - rail footer rules (Nodes only, its own Tab stop);
    - the chat label fallbacks;
    - a second falsification.
- **Leg 5 landed** (`[LAND:leg]`).
  - **Gates:**
    - lint clean;
    - static guards 401;
    - unit 5,146;
    - chats lane **144**;
    - shared 441;
    - contracts 556;
    - `test_flow_chat_composer.py` 9/9, three runs.
  - The `:focus-within` falsification was done, failing in both themes.
  - **Squawk 0110 is completed**, pending sign-off. The pane test now expects `[]`.
  - **12 deviations, accepted.** Notably:
    - the telemetry row relies on the wrapper's 24px, giving the board's inset;
    - the attach button is a square 24×24 icon button;
    - `input-area` is retired;
    - telemetry is hidden while starting and joining too.
  - Leg 8 gains the `extended-thinking-tool-turn` step 5 re-wording.
- **Leg 6 implementation** spawned (Opus).
- **Leg 6 landed** (`[LAND:leg]`).
  - **Gates:**
    - lint clean;
    - static guards 413;
    - unit 5,158;
    - lanes: contracts **602**, chats **162**, agents 134, settings 178, shared 441.
  - **The open-by-default drawer** needed one test fix: the composer width at 1440 with
    the drawer open. The shell-row children and landmarks are updated as planned.
  - The falsification was done: a removed drawer fails the `aria-controls` resolver.
  - **Findings:**
    1. **`find_platform_destination` (M23 F4 L3) was in none of the three category
       tables**, so it was invisible in Settings and the Tools tab. It is now under
       Connectors, a visible fix.
    2. At 1024 the overlay covered the header toggle, so the toggle now stays above it.
       Both are added to the DD13 preview questions.
  - **Deviations, accepted:**
    - `App.chat.chatWith` carries the pick intent;
    - the drawer follows the header states;
    - `App.ui.drawer` gets an `el` option for the static slot;
    - squawk 0118's wording matches the code: Save enables on the first change.
- **Leg 7 implementation** spawned (Opus).
- **Leg 7 landed** (`[LAND:leg]`).
  - **Gates:**
    - lint clean;
    - static guards 441;
    - unit 5,177;
    - lanes: contracts **644**, shared **461**, settings 178, agents 134, chats 162.
  - **Two falsifications:** navigate-before-close, and `anyOpen` dropped from the
    listener.
  - **WebKitGTK verdict: partially verified (GTK-level key).** A `Gdk.EventKey` pair
    through `WebView.event`, with focus in the Agents filter, produced a trusted Ctrl+K
    keydown, and the palette opened in both themes. `Gtk.test_widget_send_key` never
    reached the page under XWayland. The mission Known Issue is amended.
  - **9 deviations, accepted.** Notably:
    - a `jump-to-close` testid;
    - three extra probe flags;
    - `preventDefault` on every matched key;
    - "Untitled chat" is defensive only (the server stores "New chat").
- **Leg 8 `behavior-specs-and-close`.** **Risk tier: low** (specs, crew-file and docs
  text, plus the gates). There is no design review. The Developer's part is spawned
  (Opus). **In parallel**, the Flight Director runs DD13: the preview instance on 8485 (a
  fresh scratch data dir), the screenshots and the comparison page.
- **DD13 preview published** (not awaited):
  <https://claude.ai/artifact/WfJC1d4cWUe5TXCdbBigoo> (private).
  - **Instance:** 8485, data dir `/tmp/the-one-f4-preview`, dev mode, environment
    verified through `/proc/<pid>/environ`. Seeded with 32 agents over four providers,
    11 chats aged from 12 minutes to 45 days (one a Discord connector chat), knowledge
    bases and MCP servers.
  - **Captures:** 30 app screenshots, both themes. Joined, picker, picker with a query,
    pending and the palette (empty and with a query) at 1440 and 1024. The agent
    editor's Chat at both widths. The drawer overlay at 1024 only. No page errors.
  - **Boards:** B3 rendered at 1440 for chats, picker, pending and palette, in both
    themes. The pending board needed a dispatched click, because the board runtime's
    rows are not HTML buttons.
  - **Questions:** DD13's nine, as listed in the flight spec.
  - **One observation offered as a possible squawk:** message bubbles show UTC
    ("04:07:18 UTC") while the list shows local time (23:07). The bubble format
    predates this flight.
  - **Nothing in the captures contradicts the legs' outcomes.**
- **Leg 8 (Developer part) landed** (`[LAND:leg]`).
  - **AC1–AC6 reported met.** The two new specs are `active`, and the affected specs
    are re-authored (three more generic starts beyond the leg's list). The crew file
    carries the six run rules. The docs sweep fixed four drifts. Squawk 0117 is
    completed, and 0110, 0111 and 0118 are re-checked.
  - **Gates match leg 7:**
    - lint clean;
    - static guards 441;
    - unit 5,177;
    - lanes: chats 162, agents 134, library 145, settings 178, contracts 644 (WebKit
      required), shared 461. 1,730 browser tests in all.
  - **All legs landed.** Next is the flight-end review: a Reviewer (Sonnet, because the
    WebSocket start protocol and session lifecycle are security-adjacent) and an
    Accessibility Reviewer (Sonnet), in parallel. The review scope is every uncommitted
    change over `af86324`. PR #219 is still open, so a rebase waits for the commit.
- **Flight-end review: both reviewers `[HANDOFF:confirmed]`, with no blocking findings.**
  - **Reviewer (Sonnet).**
    - Squawks 0110, 0111, 0117 and 0118 are signed off.
    - Gates it ran:
      - static guards 355;
      - `test_ws_*` 78;
      - ruff clean;
      - chats lane 160 passed. Two failures came from a midnight window, below.
    - Non-blocking findings:
      - **R1:** `test_flow_chat_list.py` seeds "today" stamps at fixed minutes after local
        midnight, so it fails in the first minutes of the day.
      - **R2:** a theoretical cross-socket race. A plain `join` of an id whose
        `start_session` create is still in flight pops the cached session. The shipped
        client never sends it.
      - **R3:** a flight-log heading nit.
  - **Accessibility Reviewer (Sonnet).** It read the code and ran the contrast audit (237).
    Non-blocking findings:
    - **A1:** an armed row delete gives a screen reader no cue (4.1.3).
    - **A2:** the search list keeps `aria-expanded="true"` with no results (4.1.2).
    - **A3:** no result count is announced while filtering (4.1.3).
    - **A4:** the 1024 overlay drawer covers Send and sits late in the tab order.
    - **A5:** `#app-sidebar` has no label beside the labelled drawer aside.
  - **Decisions.**
    - **Fixing:** R1, R2 (guard the not-found pop on a reservation, add a unit test and an
      `agents.md` line), R3, A1, A2 and A3.
    - **Accepting A4:** DD7's recorded trade-off, already DD13 preview question 3. Flight
      6 (the alignment flight) may revisit it with the operator's answer.
    - **Accepting A5:** it predates this flight (the Flight 2 shell), the list pane's
      named section already labels the column, and a second name would double the
      announcement. Carried to the debrief.
  - The working tree is snapshotted as tree `5bf9b51` (a scratch index, not committed), so
    the re-review sees only the fix diff (`git diff 5bf9b51 <post-fix tree>`).
- **Flight-end review fixes (Developer).**
  - R1: `test_flow_chat_list.py` early-today stamps are now `[0, "f", fraction]` (a fraction of the way from local midnight to now, so always today and before "now"); `_stamps` skips in the first minute after midnight; the "Early chat" time is read from the stamp, not `00:05`. No other fixed-from-midnight stamp remained.
  - R2: `_restore_session`'s not-found branch in `app.py` no longer pops `_sessions[sid]` while the id is in `_start_reservations`; `TestRestoreNotFoundVsReservation` in `tests/test_ws_start_session.py` pins it (falsified: guard removed, the test failed, guard restored, passes); one sentence added to `agents.md`'s start-protocol section.
  - R3: Leg 8 heading renamed to "(landed, 2026-10-05)".
  - A1: `chat.js` row `onDelete(id, li, btn)` keeps the action button's `aria-label` in step with the li's `.confirm-delete` class through one MutationObserver per li ("Confirm delete: {title}" armed, "Delete chat: {title}" on lapse, commit or re-render); `confirm.js` and `list-pane.js` untouched. Asserted in `test_row_delete_arms_confirms_and_focuses_the_neighbour` and the new `test_armed_delete_label_reverts_on_lapse`.
  - A2/A3: `ui/search-list.js` `render()` sets `aria-expanded` to false with no matches, and the status region reads "1 result" / "{n} results" for a non-blank query (empty text for none, empty otherwise); contract tests extended and `docs/ui-control-inventory.md` searchList row updated. Callers' tests unchanged.
  - Gates: ruff check and format clean; static guards 355 passed; `make test-unit` 5,178 passed, 10 skipped; chats lane 163 passed; contracts lane 646 passed, 3 skipped (WebKit required); shared lane 461 passed. (An earlier unit run alongside a browser lane showed one load-related failure; the rerun alone was clean.)
- **Fix re-review (Sonnet) `[HANDOFF:confirmed]`.** The diff reviewed was `5bf9b51` →
  `c2f96dc` (tree snapshots).
  - **R2:** the guard cannot strand a cached session, because a failed or cancelled
    strict create removes its own entry.
  - **A1:** the observer is created once per `li` and is collected with it.
  - **One cosmetic nit, accepted:** an auto-title landing during the 3-second armed
    window leaves the reverted label briefly stale until the next render.
  - **The review loop is closed** (one fix cycle). The commit Developer commits the
    flight with every leg `completed`.

- **Flight committed** as `340dad4` (every leg `completed`), pushed, and opened as draft PR
  #220, stacked on #219 (base `flight/03-list-and-detail`). It will be rebased onto `main`
  after #219 merges.
- **Close-gate behavior runs** (run timestamp `2026-10-06-06-01-26`; all **pass**,
  **96 of 96** checkpoints).
  - Results:
    - `start-a-chat` 26/26 (Light and Dark);
    - `jump-to-palette` 24/24 (Light and Dark);
    - `workbench-navigation` 28/28 (Light and Dark);
    - `shell-navigation-smoke` 9/9;
    - `chat-roundtrip` 9/9 (Light steps 1–6, Dark steps 3–6).
  - **`vision-round-trip`: not run.** It needs a live Anthropic API key, and the mock
    provider cannot judge vision grounding, as the leg 8 plan allows.
  - **Setup.**
    - Five concurrent live Executor and Validator pairs (Sonnet), each on its own fresh
      instance: 8486, 8488, 8489, 8490 and 8491.
    - Scratch data dirs `/tmp/the-one-f4gate-*`, dev mode, environments verified through
      `/proc/<pid>/environ`.
    - CDP Chromium with real input. Never 8484, 8485 or the default data dir.
    - Run logs are in `tests/behavior/<slug>/runs/2026-10-06-06-01-26.md`, and each spec's
      `Last Run` is updated.
  - **Apparatus lessons** (debrief material):
    1. A Playwright `new_context()` over `connect_over_cdp` dies when the script
       disconnects. A variant's fresh context must be a new Chromium process with a fresh
       profile, or a long-lived driver. An advisory went out mid-run.
    2. One Executor's `pkill -f` matched its own shell. A broad-kill ban went out mid-run.
       Another run's Chromium exited at about 01:08:53 (cause not established) and was
       recovered on the same profile.
    3. **Orchestrator slip:** the Validator hand-off for workbench-navigation's Light
       step 7 was skipped in a burst of concurrent reports. It was judged after
       `[CLOSING]` from the evidence recorded at the time, and passed. The run log says
       so.
    4. Executors wrote `step-N-report.json` files without their notes, and Validators read
       them. That kept the Orchestrator's context small and the Validator independent of
       the notes.
  - **Product observations** (none failed a spec):
    - The Dark picker and palette scrim is 0.5, against the board's 0.3 (DD13 preview
      question 7).
    - The Dark pending-row wash (alpha 0.10) is faint; the border carries it.
    - `rail-jump-to` shows no visible focus ring after a pointer-initiated close, because
      `:focus-visible` does not apply; the focus identity is correct.
    - After Continue from a dirty editor into a pending chat, focus lands on `<main>`.
    - Message timestamps re-render from the persisted server times after a reload, 1–4
      seconds off the live render.
  - **Spec feedback:** Validators raised wording fixes, including the step 9 Description id,
    a true reload in shell-smoke step 8, and frame accounting per step. These are carried
    to the debrief.
- **Operator preview:** no comments on the artifact by the close gate. Feedback that arrives
  before PR #220 merges becomes a follow-up leg.
- **Flight landed** (2026-10-06). Next: mark PR #220 ready, then the Flight 4 debrief.

---

## Decisions

---

## Deviations

- **Leg 1 (controls-and-data), 2026-10-05.** Seven recorded in the leg's entry under "Leg
  Progress": the searchList description and active meta use `--fg-secondary` (`--fg-muted`
  fails body AA on the active wash; AC8 named `--fg-muted`); Home/End not intercepted (AC7's
  deliberate narrowing of DD10); Shift+Tab into a list with row actions lands on the stop row;
  a transient reveal class lets a hidden action take focus on restore; the test-id guard learns
  `<lower>Testid` option keys; the modal's chooser option guards; the chats row style ignores
  `icon`, `lead` and `count`.
- **Leg 2 (ws-start-protocol), 2026-10-05.** Recorded in the leg's entry under "Leg
  Progress": woken reservation waiters look up only inside their own reservation (a lookup
  outside one could pop a re-reserving creator's in-memory session); existing-id delivery
  also requires the session lock to be free, and its `session_joined` reports
  `is_processing: true` when it delivers; the error texts the leg left open; the AC1 order
  changes (content build before the auto-create, `/reset` with a malformed image errors, a
  non-text `message` is rejected); the validator's unit tests live in
  `test_ws_build_user_content.py`.
- **Leg 3a (chats-test-seam), 2026-10-05.** Recorded in the leg's entry under "Leg
  Progress": `start_chat` clicks the header `new-chat-btn` for the open chat's own agent
  (the leg named the welcome item and the dropdown; a dropdown fires no `change` for its
  current value); helpers beyond the leg's list (`welcome_item`, `chat_rows`,
  `agent_badge`); `send_first` (Enter) replaces the Send click for the 20 first sends
  that follow a start; `chat_frames` uses Playwright's `framesent`; `seed_session`'s
  `created_at` defaults to `updated_at`; new helper smoke tests in the chats lane
  (`test_chats_helper.py`); `the_one/agents.md` left unchanged under AC4; the guard
  shares the retired-selector guard's literal walk (`_selector_hits`).

- **Leg 3b (start-flow-client), 2026-10-05.** Recorded in the leg's entry under "Leg
  Progress":
  - `idleRules` takes `pendingJoinId`, and `reconnectAction` moves the state itself;
  - additive state-machine API (`boundId`, `startFrame`, `newClientId`, `frame` and `id` in
    effects);
  - a heal resets only a pending chat (a joined or starting one is kept and re-synced);
  - an agent missing from a loaded cache is revalidated through `App.store.get` before
    healing;
  - entry points set a one-shot `pickIntent`, so AC9's rail-restore rule cannot swallow a
    deliberate New Chat;
  - Send in `idle` or `joining` keeps its text;
  - the idle notice sits on the welcome canvas;
  - the streaming-bubble pointer resets on a history render and the pending pane;
  - stale-socket guards and a single reconnect timer;
  - the selected history row's button carries `.active` on render;
  - the integration tests live in a new `test_flow_chat_start_flow.py`;
  - "Stop while starting" clicks once the server has created the session (squawk 0120);
  - the order-preserving `session_joined` delay harness.

- **Leg 4a (chats-sidebar-and-picker), 2026-10-05.** Recorded in the leg's entry under "Leg
  Progress":
  - the chats-style scroller hairline is a `components.css` (library) rule;
  - `requestPick` passes the picker's opener to `go`;
  - the reconnect re-join no longer renders the list (the selection is unchanged);
  - the picker's "Loading agents…" empty text, and its refresh only for stores not loaded at
    open (`sessions` is only peeked);
  - API beyond the leg (`registerPickerHost`, `App.chat.chatsList`, `App.chat.agentPicker`);
  - `_chats.pick` separate from `start_chat` (the cold-join test picks while `joining`);
  - `test_delete_last_session_returns_to_welcome` and `test_session_delete_keyboard_reveal`
    moved now (they named `.list-item-delete`), and `test_router_items.py`'s `.active` pin;
  - no provisional row between the starting-to-joined swap and the list refresh;
  - `--sidebar-w` and the 1279px media rule removed; the picker body capped at 624px;
  - stale copy fixed (`.session-list-empty`, two comments naming the retired label).

- **Leg 4b (chats-pane), 2026-10-05.** Recorded in the leg's entry under "Leg Progress":
  - `chat-welcome-list` is also a `RETIRED_SELECTORS` entry;
  - the two static `innerHTML` literals (the model-loading row, the thinking indicator) were
    converted, the `= ''` clears kept, and a guard pins it;
  - the welcome is shown only by the idle rules (`refreshAgentsAndSetup` no longer shows it
    while idle), and `openConversation` shows the chrome at once;
  - a pending chat's log stays in the tree under the new-chat state (zero height when empty),
    so notices show in the pending pane; `test_chat_message_log_has_live_region` re-pinned;
  - the welcome is hand-built (not `App.ui.emptyState`), its "Hello." `h1` the state's one
    heading; the guidance state hides the prompt, as `welcome.js` did;
  - the empty state's New chat at the default size with the square-pen icon;
  - API beyond the leg (`agentInfo`, `agentLine`, `guidance`, the exported `providerType`, the
    `agents` and `providers` subscriptions) and a `stop` icon;
  - no `h1` during the brief idle before the first list; a joining id with no store row shows
    a blank header; the 48px header height is a literal;
  - `test_chats_helper.py` and `test_flow_chat.py` changed beyond the leg's file list.

- **Leg 5 (composer-and-telemetry), 2026-10-05.** Recorded in the leg's entry under "Leg
  Progress":
  - the telemetry row has no horizontal padding of its own: inside the wrapper, the
    wrapper's 24px is the board's `0 24px` inset (the readout's right edge is 24px from the
    pane's, pinned);
  - the wrapper's order is the telemetry row, the chicklets and the queued region, then the
    box (the row is directly above the box unless something is staged or queued);
  - Attach is `btn-ghost btn-sm btn-icon` (24×24, Flight 1's icon-only modifier), not the
    board's unsquared 34×24;
  - the three composer buttons are `App.ui.button`s;
  - `input-area` joins `RETIRED_SELECTORS`;
  - the queued region is built by `composer.js`, and its z-index workaround is gone;
  - the readout keeps its `.telemetry-overlay` class;
  - the textarea grows by script (`fit`, through `setInputValue`);
  - a named a11y gate for the composer's text pairs, although the ladder sweep already
    covered them;
  - the telemetry row is hidden while starting and joining too;
  - Ctrl, Alt and Meta with Enter still send;
  - `test_flow_chat.py`, `test_nav_helper.py`, `CLAUDE.md` and the registry changed beyond
    the leg's file list.

- **Leg 6 (agent-drawer-and-chat-action), 2026-10-05.** Recorded in the leg's entry under
  "Leg Progress":
  - the drawer and its toggle follow the header, so they show in `starting` and `joining`
    too (the first send and a chat switch never hide and re-show it);
  - the toggle stays above the open overlay (z-index), the overlay header keeping its corner
    clear: at 1024 the overlay covered the only close control;
  - `App.ui.drawer` takes an `el` option (it fills the static slot), and the chat drawer
    hides the footer through its wrapper's `hidden`;
  - `App.chat.chatWith` carries the chat area's pick intent, so Chat is never swallowed by
    the AC9 rail restore; it is not inert while setup is incomplete;
  - `isToolEnabled` mirrors `is_tool_enabled` whole (the `mcp__`/`kb__` exemption too);
  - Built-in tools list only categories with an effective tool; self-configuration reads
    "Off"; the default and deleted states show the Chats fact; lists are A-Z;
  - `setQuery` clears (never writes) the status region;
  - a `--drawer-w` token;
  - the editor contract documents click-time validation, not "enabled once valid";
  - `find_platform_destination` joined Connectors, moving four pins in two test files;
  - Chat has the `chat` icon; the demo test ids are per-pane prefix families;
  - files beyond the leg's list (`agent-picker.js`, `tokens.css`, `admin.css`,
    `design-language-page.js` and seven test files).

- **Leg 7 (jump-to-palette), 2026-10-05.** Recorded in the leg's entry under "Leg Progress":
  - a fifth testid, `jump-to-close` (the palette's own Esc);
  - the probe's extra flags `--focus-selector`, `--key-method` and `--assert-timeout`, with
    `event` (`Gdk.EventKey` through `WebView.event`) the default, because
    `Gtk.test_widget_send_key` never reached the page under WSLg's XWayland; a failed
    assertion ends the run;
  - the input bar is the search list's field wrapper with the icon and Esc inserted;
  - a refresh keeps the active row only when the user moved off the first one;
  - `preventDefault()` on every matched key, even when another modal is in charge;
  - `App.shortcuts` in `app.js` (macOS: Meta without Ctrl);
  - "Untitled chat" is a defensive fallback (the server stores "New chat");
  - the footer's 16px inset through the modal `id` (`#jump-to-dialog`);
  - files beyond the leg's list (the two demo sections, the asset pin test, the probe's unit
    test and the new `test_settings_pages_static.py`).

- **Leg 8 (behavior-specs-and-close, Developer part), 2026-10-05.** Recorded in the leg's
  entry under "Leg Progress":
  - both new specs require a fresh scratch instance, so their expectations are exact;
  - `jump-to-palette` exercises ↑ and ↓ in a step of its own (the draft's `jtp-kb` had one
    result);
  - `start-a-chat` picks by keyboard in step 6 and by pointer in step 7, and seeds exact
    drawer facts (two sessions, a KB, a cached 3-tool MCP server, `disabled_tools`);
  - the drawer is reached by Tab from the message box (its only focusable is the footer);
  - AC2 beyond the listed specs (three more generic starts, the smoke's Jump to control,
    the fresh-context variant wording);
  - the crew file also names the apparatus default and gains a rationale section;
  - docs drift fixed beyond the sweep's list (the suite runtime, the goldfinch doctrine);
  - the unit suite ran beside two browser lanes, with every number matching leg 7.

---

## Anomalies

- **Leg 3b, 2026-10-05: squawk 0120 logged.** A `cancel` that the WebSocket loop processes
  before a spawned turn's first step (the frame already queued when the loop returns to
  `receive_text`) cancels a task whose coroutine never runs. No `cancelled` (or `done`) is
  sent, and the client stays busy. It predates the flight (the `message` path is the same)
  and is reachable only by a near-instant Stop. Out of this leg's scope (client-side).

---

## Session Notes
