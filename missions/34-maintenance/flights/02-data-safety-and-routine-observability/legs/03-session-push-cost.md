# Leg: session-push-cost

**Status**: completed
**Flight**: [Data safety and routine observability](../flight.md)

## Objective
A `sessions` push no longer rebuilds the chat agent drawer while the drawer is closed or when the chat count it shows is unchanged, and a `sessions_changed` frame is JSON-encoded once per broadcast however many sockets receive it.

## Context
- Flight Technical Approach step 3; mission criterion "Session pushes cost less" (#11). Mission 33 made every routine run start a new chat, so `sessions_changed` pushes (the full list, coalesced to ~250 ms, CLAUDE.md "Client data store") now arrive with routine volume.
- **Drawer today.** `static/js/areas/chat/agent-drawer.js` subscribes `render()` to five stores (`var STORES = ['agents', 'providers', 'knowledge-bases', 'mcp-sources', 'sessions']`; `App.store.subscribe(STORES[s], function () { render(); })`). `render()` calls `renderContent(info)`, which starts with `content.textContent = ''` and rebuilds the whole drawer body, then `ensureFetches(info)` (which already returns early unless `drawer.isOpen()`). The only thing the drawer reads from `sessions` is `chatsCount(name)`, the Chats fact.
- **Why a subscription guard alone is not enough** (design review cycle 1): `areas/chat.js` subscribes `function () { renderChatsList(); renderPane(); }` to `sessions`, and `renderPane()` always ends in `agentDrawer.render(drawerView)`; the drawer's `render(next)` sets `view` and calls `apply()`, which ends in an unconditional `render()`. So every push rebuilds the drawer through `renderPane`, open or closed. The dedupe must live in `apply()`.
- **Rule for this leg.**
  - **One render key.** Keep `lastKey` (string) beside `render()`. The key is `JSON.stringify(view)` (agent, `loading`, `sessionId`), the mode, `want` (open), and, only while open, the Chats count for the current view (`chatsCount` per the `describe()` kind; `null` for kinds with no Chats fact). Closed, the key carries no store data.
  - **`apply()`** always does the open/close, mode, `openGen` and toggle work as today, then calls `render()` only when `want && !was` (a transition into open always renders) or the key changed. `render()` writes `lastKey` after `renderContent`.
  - **Store subscriptions.** One closure per store through a small helper (`App.store` passes the rows, not the store name; store.js `subscribe(name, fn)` calls `fn(copy(value))`). `sessions`: go through the same key check (skip when unchanged). The other four stores: render when open (as today, these are rare and change content beyond the key), skip when closed. Keep exactly one subscription per store (`test_the_drawer_subscribes_to_five_stores…` counts them).
  - **Direct `render()` calls** from fetch completions (`ensureFetches`), `setSessionMetadata`, `refreshNotes`/`refreshRoutines` stay unconditional (they carry new content). They are rare and only follow an open.
  - Closed and the view changes (another chat joined): the key changes, so it renders, as today; existing tests that read content while closed (`test_hidden_off_chats_and_while_idle`, the deleted/default tests) keep their behaviour.
  - Do **not** change what the drawer shows or when it fetches. Only `chatsCount` reads the `sessions` store in the drawer (verified: one `App.store.peek('sessions')`); the Routine fact, notes `pending` and `viewSession()` come from session metadata and `view.sessionId`.
- **Server today.** `the_one/sessions/_broadcast.py::broadcast_to_all` calls `await ws.send_json(payload)` per socket. Starlette's `WebSocket.send_json` serialises with `json.dumps(data, separators=(",", ":"), ensure_ascii=False)` and sends text, so encoding once with exactly those arguments and calling `ws.send_text(text)` per socket puts the same bytes on the wire. The only production caller is the `sessions_changed` pusher in `the_one/interfaces/web/app.py` (`await broadcast_to_all({"type": "sessions_changed", ...})`). Keep the per-socket error handling (a socket whose send raises is dropped). The encode moves out of the per-socket `try`, so wrap it: a payload that fails to encode is logged at WARNING and nothing is sent (no socket dropped).
- **Test fakes.** `tests/test_session_changes.py::FakeWS` implements only `send_json`, and other tests may register fake sockets with `add_socket`. It is the only fake registered through `add_socket` (review grep). It gains `send_text(text)` that honours `fail` (raises `RuntimeError`) and appends `json.loads(text)` to `sent`, so existing assertions keep reading dicts; keep `send_json` (`broadcast_to_session` still uses it).
- **Out of scope:** capping the pushed session list (an open operator decision); `broadcast_to_session` (per-session frames, not the growth path); the Chats list's own render.
- The inspection's figures for context (not an AC): 24 ms per push at 5k sessions, 106 ms / 7.3 MB at 20k. Rerun a rough figure if cheap and record it in the flight log; it is not a gate.

## Design Review
2026-11-02, Developer (Sonnet), cycle 1: **needs rework**. High: the drawer is re-rendered through `chat.js` `renderPane` → `render(view)` → `apply()` on every push, so a subscription guard does not remove the rebuild; fixed by moving the dedupe into `apply()` with a render key. Medium: `App.store` does not pass the store name (per-store closures); late fetch completions can mutate the drawer after close (the tests settle first). Low, applied: the only `add_socket` fake is `FakeWS`; wrap the hoisted encode; the content selector `#chat-drawer .chat-drawer-content`; a rename-only push in AC2. Starlette's `send_json` arguments confirmed. Cycle 2 requested.

Cycle 2 (Developer, Sonnet): **approve with changes**. The render key is complete: every input skipped while closed is recomputed on the transition into open, and open-drawer inputs from other stores, metadata and fetches keep their own render paths; no existing drawer test breaks. Applied: Outputs text fixed, explicit `renderKey()` inputs and synchronous `lastKey` write, the header-comment rewrite, the close-time render stated as intentional, AC3 made concrete, a repeat-push assertion in AC2. Leg `ready`.

## Inputs
- Legs 1 and 2 landed (no shared files).

## Outputs
- `agent-drawer.js`: `renderKey()` / `lastKey`, the `apply()` dedupe and the per-store subscription helper; header comment updated (the "re-rendered on every view change and on each ... notification" sentence).
- `the_one/sessions/_broadcast.py::broadcast_to_all`: encode once, `send_text`.
- Tests: a browser test in `tests/browser/test_flow_chat_drawer.py` (the `chats` lane); a unit test in `tests/test_session_changes.py`; updated fakes.
- `the_one/agents.md`: the socket-registry bullet (`broadcast_to_all`) and the "Agent drawer" section, one clause each.

## Acceptance Criteria
- [ ] **AC1 — closed drawer, no rebuild.** A browser test joins a chat, lets the drawer settle (the Chats fact and the Rules/Notes/Routines groups loaded, then a short `page.wait_for_timeout`, so no fetch started while open lands later), closes the drawer (the toggle), installs a `MutationObserver` (`childList: true, subtree: true`) on `#chat-drawer .chat-drawer-content` counting mutations, then causes a real `sessions_changed` push (seed a new session for any agent through the REST API, which the server pushes to every socket) and waits until the Chats list shows the new row. The observer has counted 0 mutations. Then open the drawer: the Chats fact shows the new count (rendered on open).
- [ ] **AC2 — open drawer, unchanged count.** With the drawer open and settled on agent A, a push that adds a session for a different agent B (A's count unchanged) causes 0 content mutations, and so does a push that only changes another session (a rename through whichever chat-session route calls `notify_sessions_changed`; find it in `repositories.py` and the routes); a push that adds a session for A causes a rebuild and the Chats fact shows the new count. Wait for the Chats list to show the change, then ~400 ms, before reading the observer.
- [ ] **AC3 — other stores still render.** An existing drawer test that depends on an `agents`/`providers` notification while open (e.g. the model or description changing after an agent save) still passes unmodified; if none exists, add one (edit the agent's description through the API, then `App.store.get('agents', {force: true})` while open, and the drawer shows the new description). In AC2, after the push that changed A's count, a second push that changes nothing for A causes 0 mutations (pins `lastKey` being written by `render()`).
- [ ] **AC4 — encode once.** A unit test registers 3 fake sockets, patches `json.dumps` in `the_one.sessions._broadcast` with a counting wrapper (or asserts the identical `str` object reached all three `send_text` calls), broadcasts once, and asserts one encode and three sends of the same text; the text equals `json.dumps(payload, separators=(",", ":"), ensure_ascii=False)`. The existing dead-socket test still passes (a socket whose `send_text` raises is dropped).
- [ ] **AC5 — wire format unchanged.** The existing browser tests that read `sessions_changed` (the Chats list following pushes; grep `sessions_changed` in `tests/browser/`) pass.
- [ ] **AC6 — suites green.** `make test-unit`; `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats` and `--lane chats-transcript`; the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`); ruff clean.
- [ ] **AC7 — falsified.** AC1's and AC4's new tests each fail with their fix removed (by editing), then pass with it restored (by editing).

## Verification Steps
- AC1–AC3, AC5: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_chat_drawer.py -x`, then the two chat lanes.
- AC4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_session_changes.py -x --timeout 30`.
- AC6/AC7: the commands above; report falsification per test.

## Implementation Guidance
1. Server first: rewrite `broadcast_to_all` (import `json`; `text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)`; loop `await ws.send_text(text)`), update every fake, add the AC4 test.
2. Drawer: add `renderKey()` and `lastKey`; make `apply()` render only on `want && !was` or a changed key; replace the subscription loop with a per-store helper (`sessions` through the key check, others render-if-open). `renderKey()` calls `describe()` and uses `chatsCount(info.name)` for the `agent` and `deleted` kinds, `chatsCount(null)` for `default`, `null` for `loading` and `none`; `render()` sets `lastKey = renderKey()` synchronously right after `renderContent`, so the key matches what was drawn. Because `want` is in the key, closing the drawer renders once; that is intentional and harmless (state it in the comment). Rewrite the header comment's "Content (re-rendered on every view change and on each ... notification)" sentence: content re-renders when the render key changes, on a transition into open, on an `agents`/`providers`/`knowledge-bases`/`mcp-sources` notification while open, and on fetch and metadata completions; name `chat.js`'s `renderPane` as the other entry point and say the dedupe lives in `apply()`.
3. Browser tests per AC1/AC2, using `_chats.py` helpers and `seeders.seed_session` for the pushes; poll with `page.wait_for_timeout`/`expect`, never `time.sleep`. Read `test_flow_chat_drawer.py` first for how it opens and closes the drawer at 1280px (push mode, open by default).
4. Update the drawer header comment and agents.md.

## Edge Cases
- The drawer is open but the chat area is inactive (Chats not the destination): `drawer.isOpen()` is false there (apply() closes it when `!active`), so the closed rule covers it.
- A `sessions` push that arrives before the drawer's first render: `lastKey` starts `null`, so the first `apply()` renders.
- The view object from `renderPane` is a fresh object each time; comparing its JSON (not identity) is what makes an unchanged view skip.
- An agent rename changes `view.agent`; the next `render(view)` goes through `apply()` and renders unconditionally.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js`
- `the_one/sessions/_broadcast.py`
- `tests/test_session_changes.py` (and any other file whose fake socket goes through `add_socket`), `tests/browser/test_flow_chat_drawer.py`
- `the_one/agents.md`, the flight log

## Citation Audit
Checked at `b497312f` (Flight Director, 2026-11-02): `agent-drawer.js` `var STORES = [...]` :108, `function chatsCount(name)` :286, `function renderContent(info)` :594 with `content.textContent = ''`, `function render()` :710, `function apply()` :716-729 ending in `render()`, subscriptions :743-745 — verified (flight cited :737, drifted). `_broadcast.py::broadcast_to_all` with `await ws.send_json(payload)` — verified. Sole production caller `app.py` `await broadcast_to_all({"type": "sessions_changed", ...})` :189 — verified. `tests/test_session_changes.py::FakeWS` has only `send_json` (:210-216) — verified.
