# Leg: chats-sidebar-and-picker

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Give the Chats **list column** its board shape (§5.1). It becomes an `App.ui.listPane`
titled "Chats", 300px wide, with:
- a full-width **New chat** button;
- cross-agent history in recency groups;
- row delete;
- the pending row.

Add the **agent picker** (§5.6): an `App.ui.searchList` in an `App.ui.modal` chooser, with
Recently used and All agents. **New chat** opens it.

Retire the sidebar's agent dropdown, the old history list (`history-buckets.js`) and the
sidebar HTML-string sink. Move `_chats.start_chat` onto the picker.

Split from leg 4 at its design review: **4a** is the sidebar, **4b** the pane.

## Context

- **Flight decisions:** DD3, DD4, DD5, DD12, DD14 and DD15 (A16 and A28). The leg 4 design
  review answers are in the flight log, "Leg 4 design review".
- **What stays for 4b:** the old pane, which is the welcome canvas and its agent list,
  the chat header with `h2.session-agent-badge` and `new-chat-btn`, and the composer, all
  still inside the `content.innerHTML` sink. Those old entry points keep calling
  `requestPick` (`chat.js` around 583–592), so nothing is half-broken between 4a and 4b.
- **Reuse leg 3b's `requestPick`.** It computes the `~new` replace and goes through the
  router. The picker module gets `onPick` from `chat.js`; it does not own `pickIntent`.
- **The `providers` store** is needed for an agent's provider type: the dot, search by
  type slug, and the badge. Agents carry only `provider_config_id`. Resolve it as Studio
  does (`studio.js` around 2304–2330, `providerFor` plus `App.ui.badge.KINDS`).

## Inputs

- Leg 1:
  - `ui/list-pane.js`: `rowStyle:'chats'`, `block`, `item.action`, `item.dataset`;
    `aria-current` is `"page"` for `href` rows and `"true"` for button rows;
  - `ui/search-list.js`;
  - `ui/modal.js`: the chooser options `layout`, `width`, `top`, `initialFocus`,
    `closeButton` and `footer`. A `DocumentFragment` footer is cloned per `open()`. Pass
    the opener explicitly to `open(opener)`.
- Leg 1's `App.store` `sessions` with `prime`. Leg 3b:
  - `session-state.js` (the real API: `state()`, `idleRules(list, pendingJoinId)`);
  - `chat.js` (`renderList` at around 463, 653 and 1542; `highlightActiveSession` around
    419; `requestPick` around 583; the local `sessions` and `listSeen` around 111 and
    1524);
  - `history-buckets.js` (the interim pending item, `bucketForSession`, and the labels at
    around 9–12, "Last 7 Days" and "Last 30 Days").
- Leg 3a: `_chats.py`, `seed_session` and the `CHAT_SEAM_*` guard (`tests/test_nav_helper.py`
  around 444).
- `css/base.css`: `#app-sidebar` takes `--sidebar-w` (line 27), with its comment block at
  around 42–45, a 1279px media rule, and the padding-top-zero rule.

## Acceptance Criteria

**A. The column (§5.1, DD5).**

- [ ] **AC1. Width.** `#app-sidebar[data-destination="chats"]` takes `--list-w` (300px) at
  every width, and joins the padding-top-zero rule.
  - The `base.css` comment block (around 42–45) is updated.
  - `--sidebar-w` is removed only if nothing else uses it; `test_token_definitions` is
    checked.
  - `test_shell_rail.py`'s width pins (around 154–163, and `expect_state("chats", 240)` at
    247 and 257) are **renamed and inverted** to 300 at every width.
- [ ] **AC2. The pane.** `App.ui.listPane`, with testid `chats-list`, title "Chats" (its
  `h2`), `rowStyle:'chats'` and no filter. Its `block` is the **New chat** button:
  - `btn-filled-primary btn-lg`, full width;
  - the `square-pen` icon as a DOM node (`App.ui.util.icon`), plus the label "New chat";
  - testid `chats-new-btn`;
  - a click calls `App.chat.openPicker({opener: <the button>})`.
  - **While setup is incomplete** (no provider or no agent), the button is natively
    `disabled`, and the pane's guidance (still the old welcome, until 4b) explains why.

  The "Select Agent" label and the `agent-select` dropdown are removed.
- [ ] **AC3. Groups.** Today, Yesterday, Last 7 days, Last 30 days and Older, in **sentence
  case** (a change from "Last 7 Days" and "Last 30 Days"; the flight log notes it).
  - Bucket by `updated_at || created_at` in local time:
    - day 0 is Today;
    - day 1 is Yesterday;
    - days 2–6 are Last 7 days;
    - days 7–29 are Last 30 days;
    - everything older, missing or invalid is Older.

    Day 7 therefore goes to Last 30 days, so a weekday label is never ambiguous with
    today's.
  - Each group is newest first. Empty groups are not shown.
- [ ] **AC4. Rows.**
  - `label` is the title.
  - `time` is hand-formatted:
    - Today: `HH:MM`, 24-hour;
    - Yesterday and Last 7 days: the short weekday (`Mon`);
    - Last 30 days and Older: the short month and day (`Sep 12`);
    - a missing or invalid date: `''`.
  - `meta` is the agent name, or "Default agent" for a null `agent_name`.
  - **Connector rows** get `badges: [platform]`, a neutral muted span through listPane's
    plain-string badge path, with no class built from the value.
  - `href` is `App.router.href({destination:'chats', id})`, and `dataset` is `{id}`.
  - The testid is `chat-row`.
  - `action` is delete: the trash icon, `label` "Delete chat: {title}", testid
    `chat-row-delete`. It runs `App.confirmDelete(li, …)` (arm, then confirm), then the
    WebSocket `delete_session`, as today's delete does.
  - After a delete, focus goes to the neighbouring row (leg 1's action rule).
- [ ] **AC5. The pending row.** While the state is `pending` or `starting`:
  - one row at the top of Today, with id `'__pending__'`, label "New chat", time "now" and
    the agent as meta;
  - `href` is its own `#chats/~new/{agent}`, so it is a **link** and gets
    `aria-current="page"`;
  - `dataset {pending:'true'}`, with **no** `data-id` and **no** `action`;
  - it is the selected row.

  It replaces leg 3b's interim item. `_chats.py`'s pending helper is updated if it differs.
- [ ] **AC6. One render.** A single `renderChatsList()` reads `App.store.peek('sessions')`
  (the rows) plus the session state (the pending row and `selectedId`).
  - It is called from the `App.store.subscribe('sessions')` callback **and** from every
    state transition that changes the pending row or the selection: pick, open, joined,
    the starting-to-joined swap, idle and delete.
  - It is safe off-Chats: a REST-primed list with no socket renders nothing visible and
    never throws.
  - **The subscription lives as long as the chat area.** The area is never destroyed,
    and a code comment says so.
  - The local `sessions` array may remain for `idleRules` and `listSeen`; "one source"
    applies to **rendering**.
- [ ] **AC7. Empty.** With no sessions and no pending chat, the list shows "No
  conversations yet." through the pane's empty state.

**B. The picker (§5.6, DD4, A16).**

- [ ] **AC8. The modal.** It is **built fresh on every open**, so the query is cleared on
  the next open (§10 item 11). It is `App.ui.modal`:
  - `layout:'chooser'`, `width:640`, `top:72`, `dismissible:true`;
  - title "Start a chat with…";
  - `closeButton {label:'Esc', ariaLabel:'Close (Esc)', testid:'agent-picker-close'}`;
  - `initialFocus` is the `searchList` input, created before `open()`;
  - testid `agent-picker`;
  - the footer is a fragment with "Picking an agent starts a new chat with it", and "Enter
    to start" in `.modal-dialog-footer-end`.
- [ ] **AC9. The list.** `App.ui.searchList`:
  - `label` "Find an agent", placeholder "Find an agent by name, model or provider";
  - `inputTestid` `agent-picker-search`, `rowTestid` `agent-picker-row`.
  - **Rows:**
    - `lead` is the provider dot (`badge badge--{type} badge-dot`, `aria-hidden`), with the
      type from the `providers` store; an unknown or missing provider uses `badge-dot--none`
      or the existing fallback Studio uses;
    - `label` is the agent name;
    - `description` is the description;
    - `meta` is the model, with `metaMono`;
    - `dataset` is `{agent: name}`.
  - The picker waits on **both** `agents` and `providers` (`App.store.get`), and refreshes
    as each resolves.
- [ ] **AC10. Groups.**
  - **Empty query:** "Recently used", up to 5, using the latest `updated_at` over
    sessions with a null `platform` and a live `agent_name` (DD4). Then "All agents",
    every agent A–Z, including the recent ones.
  - **With a query:** one group, "{n} matching", A–Z. A16 is a deviation from the board.
    A case-insensitive substring is matched over name, model, provider type slug and
    description.
  - **No match:** `No agents match "{q}".`
  - **Zero agents** cannot reach the picker, because New chat is disabled (AC2). The empty
    text still reads "No agents yet." defensively.
  - The synthetic default agent and deleted agents never appear.
- [ ] **AC11. Picking.**
  - The picker closes, and **from `onClose`**, after focus restore, it calls leg 3b's
    `requestPick(agent)`, so a leave-guard dialog never stacks under the chooser.
  - Escape, the close button and the backdrop close it, with focus back at the opener.
- [ ] **AC12. `App.chat.openPicker({opener})`.**
  - It returns a Promise that resolves when the picker is open.
  - If Chats is not the active destination, it first runs
    `App.router.go(App.router.href({destination:'chats'}))`, and continues on a commit;
    it rejects on a guard Stay.
  - If the chat area is not yet initialised, it waits for its init (a queue flushed at
    the end of `init`).
  - With setup incomplete, it resolves without opening, as an inert no-op.

**C. Retirement, tests and gates.**

- [ ] **AC13. The sidebar retirement.**
  - The sidebar is built with DOM APIs, so the `chat.js` sidebar sink (around 276) is gone.
  - `history-buckets.js` is deleted, and its bucketing moves into `areas/chat/chats-list.js`.
  - The `agent-select` dropdown, its label, `syncDropdownToCurrent` and the dropdown
    `change` handler are removed.
  - `chat.css` loses `.session-*`, `.sidebar-header`, `.session-item-source*` and
    `.session-group*`.
  - `components.css`'s `.list-item-delete` and `.list-item.confirm-delete` are **kept**:
    the design-language page (`surfaces-section.js` around 85) uses them.
  - `tests/test_ui_guards.py`'s baseline drops the `areas/chat.js` sidebar entry and the
    `history-buckets.js` entry. The content entry stays for 4b.
- [ ] **AC14. Selectors.**
  - **The registry's "Retired testids" table** gains `agent-select`.
  - **`tests/test_nav_helper.py`:**
    - `RETIRED_EXACT = ("agent-select",)` is compiled as
      `(?<![\w-])agent-select(?![\w-])`, and the coverage test checks the union;
    - `RETIRED_SELECTORS` gains the class fragments `session-item`, `session-list`,
      `session-group` and `list-item-delete`. The latter applies to browser tests only:
      the design-language CSS keeps the class;
    - the live `agent-select-empty` (Flight 3) is unaffected, and a test pins that.
  - **`chat-welcome-item`, `session-agent-badge` and `new-chat-btn` retire in 4b.**
- [ ] **AC15. `_chats.py` and tests.**
  - `start_chat` moves onto the picker: open it, type, press Enter. It returns at pending,
    as in 3b.
  - `chat_row` and `open_chat` use `chat-row[data-id]`.
  - `_lists.py` gains a `chats` list.
  - **These files bypass `_chats.py` and are fixed directly:**
    - `test_flow_chat_start_flow.py`: the dropdown `select_option` at around 153 and 189
      moves to the picker. `new_chat_button(page)` at around 394 stays until 4b; it is the
      header button.
    - `test_flow_new_chat.py`: `test_dropdown_change_starts_new_session` is **replaced**
      by a picker test. `test_session_delete_confirm_lapse_is_visually_distinct`
      (around 214 and 243) re-pins on the listPane `li` (`.confirm-lapsed`), keeping its
      M24 regression intent. `test_chat_history_today_group_renders` (around 265–266)
      re-pins on the listPane caption "Today" and the pane title "Chats".
    - `test_flow_keyboard.py::test_session_list_shape` becomes `test_chats_list_shape`
      (listPane rows plus the row action, Tab from the row to its action).
    - `test_shell_rail.py` around 326 (`.session-item-title`) → `_chats.chat_row`.
    - `test_router_items.py`: any `.session-item` → `_chats.chat_row`.
  - The flight log maps every removed test name to its replacement.
- [ ] **AC16. New flow tests** (chats lane), seeding with `seed_session`. First confirm
  that `POST /api/chat/sessions` honours `updated_at`, so ages above 7 and above 30 days
  are possible.
  - **`test_flow_chat_list.py`:**
    - the groups and boundaries (day 0, 1, 6, 7 and 30, sentence-case labels);
    - the time formats;
    - the cross-agent rows;
    - the connector badge;
    - the pending row (a link, `aria-current="page"`, no action);
    - the selection;
    - row delete (arm, confirm, focus to the neighbour);
    - empty;
    - the 300px width at 1024 and 1440;
    - New chat disabled with setup incomplete.
  - **`test_flow_chat_picker.py`:**
    - open, with focus on search;
    - Recently used (connector sessions and deleted agents excluded; five at most);
    - All agents A–Z;
    - "{n} matching" A–Z on name, model, type slug and description;
    - no match;
    - Enter picks and goes to `#chats/~new/{agent}`;
    - Escape returns focus;
    - a re-pick replaces (`history.length` unchanged);
    - a guard Stay keeps the picker's opener focused;
    - provider dots per type.
- [ ] **AC17. A mid-leg gate.** After the sidebar swap and before the new flow tests, the
  chats lane is green, and recorded.
- [ ] **AC18. Gates.**
  - `make lint` and format;
  - the static guards: UI guards, tokens, contrast, `nav_helper`, `store_static`, the
    index pin (script tags added and removed) and the inventory;
  - `make test-unit`;
  - the lanes `chats`, `shared` (`TEST_TIMEOUT=3600`), `contracts`
    (`THE_ONE_REQUIRE_WEBKIT=1`), `agents`, `settings` and `library`, through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`.
  - The numbers go in the flight log.
- [ ] **AC19. Docs.**
  - `CLAUDE.md`: the Chats list and picker paragraph (the testids, `openPicker`, the
    `_chats.py` helpers, the 300px width).
  - `the_one/agents.md`.
  - `docs/ui-control-inventory.md` (the chat history row → `library: App.ui.listPane`;
    the picker as a composition).
  - `docs/ui-testid-registry.md`.

## Verification Steps

- AC17 and AC18.
- **A manual pass** at 1440 and 1024, in Light and Dark, on a dev instance (port 8486 or
  higher, scratch data dir, 30+ agents, and seeded sessions of various ages including a
  connector one). Stop it afterwards.
- **Falsify once:** drop the connector exclusion from Recently used, and watch the picker
  test fail. Restore, and record it.

## Files Affected

- New: `static/js/areas/chat/chats-list.js`, `areas/chat/agent-picker.js`,
  `tests/browser/test_flow_chat_list.py` and `test_flow_chat_picker.py`.
- Changed: `static/js/areas/chat.js`, `index.html`, `css/chat.css` and `css/base.css`.
- Removed: `static/js/areas/chat/history-buckets.js`.
- Tests: `_chats.py`, `_lists.py`, `test_flow_new_chat.py`, `test_flow_chat_start_flow.py`,
  `test_flow_keyboard.py`, `test_shell_rail.py`, `test_router_items.py`,
  `tests/test_nav_helper.py`, `tests/test_ui_guards.py` and
  `tests/test_index_asset_cache_busting.py`.
- Docs: `CLAUDE.md`, `the_one/agents.md`, the inventory and the registry.
