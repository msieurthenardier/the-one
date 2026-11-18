# Leg: gleepglorp-in-chats

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Make GleepGlorp usable end to end in Chats: pick it, start and continue a chat
with it, see its setup and off states, its Chats row, header and drawer, find it
in Jump to, and have every open page follow a change to its settings, while
every "Default agent" label and `default` check in the chat surfaces goes.

## Context
- Flight DD8 and DD11 (both as amended), the approved board's screens 2-5, and
  the Leg 2 deviation recorded in the flight log (the chat-surface "Default
  agent" labels moved here).
- Leg 3 (landed) provides: `GLEEPGLORP_AGENT_NAME` in `the_one/naming.py`; the
  settings, `GET`/`PUT /api/gleepglorp` with `state` (`off`, `needs_model`,
  `provider_missing`, `ready`); `GleepGlorpUnavailableError(state)` raised by
  `AgentFactory.create("GleepGlorp")` (a `ProviderNotConfiguredError`); the
  client module `App.gleepglorp` (`get`, `peek`, `invalidate`, `subscribe`,
  `prime`) and its Save invalidation; `_create_session` refusing a missing name.
  Re-read Leg 3's flight-log entry for the exact names it shipped before
  starting.
- **The setup gate changes** (found in this leg's code survey):
  `setupIncomplete = !hasProviders || !hasAgents` (`areas/chat.js` ~:446)
  disables the list's New chat (~:450), makes `requestPick` inert
  (`session-flow.js` ~:101) and the picker's open inert (`agent-picker.js`
  ~:218). GleepGlorp exists to help an operator set up their first agent, so
  while GleepGlorp is on the picker always opens and offers at least GleepGlorp
  (its setup state then explains what is missing). With GleepGlorp off, the gate
  is as today.
- Code map (read-only survey of the current tree, `app.py` lines may shift by a
  few after Leg 3; re-locate by symbol):
  - Server: `start_session` `app.py` ~:3602-3728 (reserved refusal ~:3608-3615;
    `_start_failed_frame` ~:1413-1420); `join` ~:3505-3581;
    `_build_session_joined_ok` ~:2142-2178, `_build_session_joined_degraded`
    ~:2181-2208; restore classification ~:1869-1915; statuses ~:1697-1705;
    per-turn path: message branch ~:3798-3832 → `_spawn_web_message` ~:1327 →
    `_locked_message_processing` ~:1279 (re-syncs from the DB ~:1293) →
    `_process_and_broadcast` ~:2498; refusals use `{"type":"system", "content"}`
    (~:3802, ~:1316-1322), and the client ends a turn on any such frame
    (`turn-frames.js` ~:38-60); `_SessionsPushListener` ~:139-202 with
    `broadcast_to_all` (`the_one/sessions/_broadcast.py` ~:44-63).
  - Client: `socket.js` (`agentMayExist` ~:34-41; `sessions_changed` handled
    before the state gate ~:107-115; `session_updated` ~:117-130;
    `setSessionHealth` call ~:241; context-window fetch ~:285-298);
    `session-state.js` (`DEGRADED_REASONS` ~:55-59; `accepts()` ~:172-189);
    `areas/chat.js` (`healthBanner` ~:173, `setSessionHealth` ~:466-475,
    `computeBlocked` ~:420-423, `applyComposerState` ~:429-433, setup gate
    ~:446-450, renderPane ~:277-319, picker host ~:552-556);
    `session-flow.js` (`agentListed` ~:89-93, `requestPick` ~:100,
    `hydrateNew` ~:245-286 refusing `'default'` ~:249, `validatePending` ~:291,
    `heal` ~:308-318, `requestRefresh` ~:405); `chat-pane.js` (`agentLine`
    ~:98-100, `agentInfo` ~:102-117, new-chat state ~:181-210, `guidance`
    ~:76-96); `transcript.js` step-limit link ~:380-408; `agent-picker.js`
    (`liveAgents` ~:61-71, `providerType` ~:75-84, `recentAgents` ~:93-115,
    `source` ~:123-152, openers ~:218, ~:241-258); `chats-list.js` ~:118;
    `jump-to.js` (`candidates` ~:124-160, `recentAgentCandidates` ~:166-185,
    `emptyMix` ~:190-217, `act` ~:268-279); `agent-drawer.js` (`STORES` ~:108,
    settings button ~:213-220 and target ~:259-267, `describe` ~:271-282,
    `chatsCount` ~:286-295, `uses` ~:527-593, `renderContent` ~:595-638,
    render key ~:713-719).
  - `App.ui.banner` has `setChildren(nodes)` usable at any time
    (`ui/page.js` ~:65-147).
  - Tests can seed a GleepGlorp chat: `seeders.seed_session` posts to
    `/api/chat/sessions`, whose `agent_name` is unvalidated
    (`api.py` ~:5887-5899, `db/models.py` ~:442).

- Design-review facts and decisions (verified against the tree with Leg 3 in
  it):
  - Leg 3's names: `GleepGlorpUnavailableError` lives in
    `the_one/agent/factory.py` (~:321) with `.state`; settings in
    `the_one/gleepglorp/settings.py` (`load_settings` ~:33, `state` ~:62; the
    state literals are `off`, `needs_model`, `provider_missing`, `ready` —
    confirm against its constant). `update_gleepglorp` is `api.py` ~:3212-3250.
    The provider delete is refused while GleepGlorp uses the provider
    (`_gleepglorp_uses_provider`, `api.py` ~:6489), so `provider_missing` is
    reachable only by a direct database edit: cover it at the unit level only.
  - **Badge**: `App.ui.badge.KINDS` (`ui/feedback.js` ~:8-20) is closed and the
    constructor throws on another kind (~:32). **Decision: add a `builtin`
    kind** (neutral: `--surface-elevated` fill, `--fg-secondary` ink, a
    `--border` hairline, as on the board), with its CSS, the catalogue row in
    `docs/ui-control-inventory.md`, the contract test, and every "eleven kinds"
    pin (CLAUDE.md, `tests/test_ui_control_inventory.py`,
    `tests/test_ui_emitted_classes.py`, the badge contract test) updated.
    `chat-pane.js` ~:109 maps unknown types to `unknown`, so GleepGlorp needs
    its own branch there.
  - **Turn end on a refusal**: the client's system-frame path
    (`turn-frames.js` ~:38-60) ends the turn and discards held messages but
    does not clear `state.ownTurn[sid]` or `refreshAfterTurn`; only `done`
    (~:146) and cancel (~:178) do, and `requestRefresh` defers on `ownTurn`
    (`session-flow.js` ~:405-408), so a push after a refusal would never
    re-join. **Decision: the client clears `ownTurn[sid]` and runs a deferred
    refresh on any system frame that ends a turn** (one place, covered by a
    browser test of refuse-then-push).
  - **No REST message path exists** (no `/api/chat` message route reaches a
    joined session); only the WebSocket `message` branch and
    `_spawn_message_processing`'s connector and routine callers.
  - **Lane**: `chats` sits at its budget (417 of 420 s). **Decision: the new
    `test_flow_chat_gleepglorp.py` joins the explicit `chats-transcript` list**
    in `scripts/run-tests.sh` (`chats_transcript_pat`; 430 of 540 s), and
    `tests/test_run_tests_lanes.py` still passes.

## Inputs
- Leg 3 landed (uncommitted in the tree, Batch B).

## Outputs
- Server: `start_session` admits exact `GleepGlorp`; GleepGlorp degraded
  statuses on join and restore; a per-turn refusal; the `gleepglorp_changed`
  push; GleepGlorp model pre-load already done in Leg 3.
- Client: `App.chat.agentKind(name)` (the "which agent" helper); the picker's
  Built in group; the setup and off new-chat states; the degraded banner with a
  button; the Chats row, header, drawer kind, step-limit link and Jump-to
  candidate; the setup-gate change; every "Default agent" label and `default`
  check removed; the push handling with the re-join.
- Tests, catalogue and registry updates, docs.

## Acceptance Criteria

**Starting and continuing**
- [ ] `start_session` with `agent_name` exactly `GleepGlorp` and GleepGlorp
      `ready` creates the chat (stored `agent_name` `GleepGlorp`) and runs the
      turn; `gleepglorp`, `GLEEPGLORP`, `default` and `Default` still get
      "Invalid agent name.". `tests/test_ws_start_session.py` (~:524, which pins
      the refusal of `GleepGlorp`) is updated to the new rule.
- [ ] `start_session` with GleepGlorp not `ready` sends `start_failed` with the
      plain sentence for its state ("GleepGlorp is turned off.", "GleepGlorp
      needs a model.", "GleepGlorp's model provider was removed.") and stores
      nothing.
- [ ] Joining or restoring a stored GleepGlorp chat when GleepGlorp is not
      `ready` sends `session_joined` with `status` `gleepglorp_off`,
      `gleepglorp_needs_model` or `gleepglorp_provider_missing` (new constants
      beside `SESSION_STATUS_*`, classified from
      `GleepGlorpUnavailableError.state` before the generic
      `ProviderNotConfiguredError` catch); it is degraded like the others.
- [ ] A message on a joined GleepGlorp chat while GleepGlorp is not `ready`
      (read from the settings at that moment, not from the agent cached on the
      session) is refused with one `{"type": "system", "content": <the state's
      sentence>}` frame to that session's subscribers, runs no turn and stores
      nothing; the client ends its busy state as for any system frame and
      clears its own-turn flag, so a later push still re-joins. The check sits
      in `_locked_message_processing` before the turn, so a stale tab and a
      second tab are both covered.

**The settings push**
- [ ] A successful `PUT /api/gleepglorp` sends `{"type": "gleepglorp_changed",
      "state": …, "settings": <the GET shape>}` to every socket through
      `broadcast_to_all` (called from the route after the save; no coalescing
      needed); a refused PUT (422) sends nothing. The client handles it in
      `socket.js`'s early branch before the session-state gate, as
      `sessions_changed` is (so an idle or pending tab gets it):
      `App.gleepglorp.prime(...)`, which notifies subscribers.
- [ ] On that frame a client with a GleepGlorp chat joined re-joins it through
      the existing `requestRefresh` path (deferred until its own turn ends), so
      its banner and composer reflect the new state without a reload; a client
      with a pending GleepGlorp chat re-renders its new-chat state; the picker,
      drawer and Jump to re-read on their next render.

**The picker**
- [ ] With GleepGlorp `enabled`, the picker's empty query shows a "Built in"
      group first with one row, GleepGlorp (testid `agent-picker-row`,
      `data-agent="GleepGlorp"`, description "Help setting up the app", meta its
      model, or "Needs a model" in `needs_model`/`provider_missing`), then
      "Recently used" (GleepGlorp never in it), then "All agents" (GleepGlorp
      never in it). A query matches GleepGlorp by name and description and lists
      it first among the matches. With GleepGlorp off it appears nowhere.
- [ ] The setup gate: with GleepGlorp `enabled`, New chat, the picker and
      `requestPick` work even with no providers or no agents; with GleepGlorp off
      the gate is unchanged. The welcome's guidance links still show when setup
      is incomplete.

**The new-chat states**
- [ ] Picking GleepGlorp `ready` opens the pending chat as for any agent, with
      a "Built in" badge (the new `builtin` kind) and the model, the h2 "GleepGlorp", the
      description, and an enabled composer; sending the first message starts the
      chat (`send_first` works for it).
- [ ] Picking GleepGlorp `needs_model` or `provider_missing` shows the board's
      screen 3: the badge, h2, description, then a warning block "GleepGlorp
      needs a model first." with a primary "Choose a model for GleepGlorp"
      (link to `#settings/gleepglorp`), and "Pick a different agent"; with no
      model providers at all the line is "Add a model provider first." and the
      button "Add a model provider" (`#library/providers/~new`); the composer is
      blocked. A direct `#chats/~new/GleepGlorp` while GleepGlorp is off shows
      the same block with "GleepGlorp is turned off." and "Open GleepGlorp
      settings". `hydrateNew` no longer heals `GleepGlorp` away.
- [ ] Testids for the new block: `chat-new-gleepglorp-setup`,
      `chat-new-gleepglorp-setup-action`.

**Joined chats**
- [ ] A GleepGlorp chat's row meta is "GleepGlorp"; its header reads "with
      GleepGlorp"; its composer shows its model; the context-window fetch is
      skipped for it (no 404 noise; `agentMayExist` answers through the new
      helper).
- [ ] A GleepGlorp chat in a degraded GleepGlorp status shows the warning
      banner with the state's sentence ("GleepGlorp is turned off. Turn it on to
      continue this chat.", "GleepGlorp needs a model.", "GleepGlorp's model
      provider was removed.") and an "Open GleepGlorp settings" button (testid
      `chat-health-banner-action`) through `setChildren`, with the composer
      blocked; never the agent "provider missing" text or the deleted-agent
      notice (board screen 5).
- [ ] The drawer has a `gleepglorp` kind (board screen 4): h2 "GleepGlorp" with
      a "Built in" badge, the description, Facts (Model, Provider, Web access
      On/Off, Memory On/Off, Keeps chats N days), "What it can use" (fixed list:
      "Your app's settings and status, read only, secrets hidden", "The app
      guide", "Web search and web pages" only when web access is on, "Its own
      notes" only when memory is on), the line "GleepGlorp can't change anything
      by itself.", and a footer button "Open GleepGlorp settings"
      (`#settings/gleepglorp`, testid `chat-drawer-settings-link` kept). It makes
      no per-agent fetches. (The "What it can use" lines describe Leg 5's tools;
      until Leg 5 lands, web and notes are inert but the lines follow the
      switches, which is what the operator sees configured.)
- [ ] The step-limit notice in a GleepGlorp chat links to
      `#settings/gleepglorp`, never `#agents/GleepGlorp`.

**The helper and the labels**
- [ ] One helper, `App.chat.agentKind(name)`, returns `{kind: 'agent' |
      'gleepglorp' | 'unknown' | 'loading', settingsHref}` and is used by the
      five membership checks (`session-flow.js` `agentListed`, `socket.js`
      `agentMayExist`, `chat-pane.js` `agentInfo`, the transcript step-limit
      link, the drawer `describe`). No code path builds `#agents/GleepGlorp`
      (a test greps the rendered hrefs).
- [ ] Every "Default agent" string and `'default'` agent check in
      `chats-list.js`, `chat-pane.js`, `agent-drawer.js` (the `default` kind,
      `chatsCount(null)`, the routines skip), `jump-to.js`, `agent-picker.js`
      `liveAgents`, `session-flow.js` ~:249 and `transcript.js` is gone; a row
      with a null agent (impossible after v53) renders the agent as "Unknown
      agent". `grep -rn "Default agent" the_one/interfaces/web/static/js` finds
      only the connector editor's field label.
- [ ] The browser tests that pinned "Default agent" are rewritten for
      GleepGlorp or for the unknown-agent case, not deleted:
      `test_flow_chat_list.py` (~:147, ~:196), `test_flow_jump_to.py` (~:542,
      ~:721-723), `test_flow_chat_drawer.py` (~:540-545), `test_flow_chat_pane.py`
      (~:201-207), `test_flow_chat_picker.py` (~:10 docstring).

**Jump to**
- [ ] With GleepGlorp enabled, Jump to lists a candidate of its own kind
      (`data-kind="gleepglorp"`) labelled "GleepGlorp" with "Built in" as its
      where, first among the agents; picking it opens the pending
      `#chats/~new/GleepGlorp` (through the router, guarded). It is not in the
      empty query's recent-agents mix. A chat candidate's where reads
      "Chat · GleepGlorp".

**Tests and gate**
- [ ] New browser tests (a new `test_flow_chat_gleepglorp.py`, listed in the
      `chats-transcript` lane; ready-path tests create a mock provider first and
      set GleepGlorp's settings through `PUT /api/gleepglorp`, copying the
      credential pattern in `test_flow_settings_gleepglorp.py`)
      cover: the Built in group (enabled, off, needs a model); the setup state
      and its no-providers variant; starting a GleepGlorp chat on the mock
      provider and getting a reply; the degraded banner with its button after
      turning GleepGlorp off in a second page (the push); the refused turn; the
      drawer kind; the step-limit link; the setup gate with no agents. Server
      unit tests cover the start, join, restore statuses, the turn refusal and
      the push. `test_flow_jump_to.py` covers the Jump-to kind.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; the lanes
      `chats`, `chats-transcript`, `shared`, `routing`, `agents` (holds
      `test_agents_chat_action.py`) pass; the static guards pass.

## Verification Steps
- Targeted unit: `tests/test_ws_start_session.py tests/test_session_lifecycle.py` plus new server tests.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x` and the other lanes named above.
- Static guards: `tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_nav_helper.py tests/test_ui_control_inventory.py`.
- Manual on a scratch instance (port 8490+, scratch data dir under `$HOME`,
  `THE_ONE_DEV_MODE=true`, mock provider): pick GleepGlorp, chat, turn it off in
  a second tab and watch the first tab's banner appear; record in the flight log.

## Implementation Guidance
1. **Server constants and classification.** Add `SESSION_STATUS_GLEEPGLORP_OFF`,
   `_NEEDS_MODEL`, `_PROVIDER_MISSING` beside the others and include them in
   `is_degraded`. In the restore classification catch
   `GleepGlorpUnavailableError` before `ProviderNotConfiguredError` and map its
   `state`. One small function maps a state to its sentence (shared by
   `start_failed`, the turn refusal and the banner text the client may need;
   the client keeps its own copy of the three banner sentences).
2. **`start_session`.** Replace the reserved refusal with: refuse when
   `is_reserved_agent_name(name) and name != GLEEPGLORP_AGENT_NAME`. On
   `_create_session` raising `GleepGlorpUnavailableError`, send `start_failed`
   with its sentence (today any exception becomes "Cannot start chat: {exc}";
   keep that for others).
3. **Turn refusal.** In `_locked_message_processing` (`app.py` ~:1273), inside
   `track_turn` (~:1281) and after the DB re-sync (~:1291), when the session's
   agent is `GleepGlorp`: `get_connection()`, `load_settings(conn)`,
   `state(conn, settings)`; if not `ready`, send the system frame to the
   session's subscribers and return. `turn.ran` is already set there; that is
   harmless (state it in a comment). Connector and routine spawns share this
   function; they never carry GleepGlorp (Leg 2), so the branch is web-only in
   practice.
4. **Push.** In `update_gleepglorp` (`api.py` ~:3212-3250), after
   `save_settings`, `await broadcast_to_all({"type": "gleepglorp_changed",
   ...})` with the same body the route returns (`from the_one.sessions import
   broadcast_to_all`). Client: handle the type in `socket.js`'s early branch
   (~:107-115, beside `sessions_changed`), prime `App.gleepglorp`, and if the
   bound session's agent is `GleepGlorp` call `sessionFlow.requestRefresh`. In
   `turn-frames.js`'s system-frame end path, clear `state.ownTurn[sid]` and
   run any deferred refresh (`refreshAfterTurn`), so a refusal followed by a
   push still re-joins.
5. **The helper.** `App.chat.agentKind(name)` in a small module (or
   `agent-picker.js`, which already owns `liveAgents`): `GleepGlorp` (exact) →
   `gleepglorp` with `#settings/gleepglorp`; a row in the loaded agents store →
   `agent` with `App.router.href({destination:'agents', id})`; store not loaded
   → `loading`; else `unknown`. Swap the five checks to it. `agentMayExist`
   returns false for `gleepglorp` (today an unloaded store answers true), so
   the context-window fetch is skipped for it.
6. **Picker.** Add the Built in group in `source()` from `App.gleepglorp.peek()`
   (fetch on open if not loaded); exclude GleepGlorp from `liveAgents` and
   `recentAgents`. Item: `{id: 'GleepGlorp', label: 'GleepGlorp', description:
   'Help setting up the app', meta: model or 'Needs a model', dataset: {agent:
   'GleepGlorp'}}`.
7. **Setup gate.** `setupIncomplete` (`chat.js` ~:446) stays as the welcome's
   guidance signal (`chat-pane.js` ~:80, ~:143 unchanged). Add
   `gleepglorpEnabled` in `chat.js` from `App.gleepglorp` (loaded at the area's
   init and kept current with `subscribe`), and gate on
   `setupIncomplete && !gleepglorpEnabled` at: `setNewDisabled` (~:450), the
   host's `setupIncomplete()` callback (~:553, read by `agent-picker.js` ~:218),
   `session-flow.js` ~:101, and `computeBlocked` (~:422: a pending chat is
   blocked by `setupIncomplete` only when it is not a GleepGlorp chat; a
   pending GleepGlorp chat is blocked by its own state instead).
8. **New-chat states.** In `chat-pane.js`, `agentInfo` returns GleepGlorp's
   info (badge neutral "Built in" plus model, description, `kind:
   'gleepglorp'`, `state`); the new-chat state renders the setup block for a
   non-ready state; `computeBlocked` blocks a pending GleepGlorp chat that is
   not ready. `hydrateNew` accepts `GleepGlorp`; `validatePending` treats it as
   listed while GleepGlorp is enabled, and while off keeps the pending chat
   with the off block (not `heal()`).
9. **Banner.** `setSessionHealth` maps the three GleepGlorp statuses to their
   sentences and adds the button through `healthBanner.setChildren`, clearing
   it for any other status. Add the three statuses to `DEGRADED_REASONS` for
   the start path too.
10. **Drawer, list, header, step-limit, Jump to.** As the AC. The drawer
    subscribes to `App.gleepglorp` directly (its `STORES` list holds
    `App.store` collections only), unsubscribes in its teardown, and its
    render key (~:713-719) includes the settings so a push re-renders it.
    Jump to: add the `gleepglorp` kind in the candidate builder (~:123-160)
    and an `act` branch (~:268); drop the `'default'` checks (~:129, ~:174);
    the chat candidate's where (~:135) reads "Chat · GleepGlorp".
11a. **One sentence table.** Put the state → sentence mapping in one server
    module (for example `the_one/gleepglorp/messages.py`), and add a unit test
    that reads the client's three banner sentences out of the JS source and
    checks they match it.
11. **Labels.** Remove every "Default agent" string and `'default'` check in
    the listed chat files; update the listed browser tests.
12. **Docs.** CLAUDE.md "Chats list and agent picker", "Chats pane", "Agent
    drawer", "Jump-to palette" paragraphs (the Built in group, the GleepGlorp
    drawer kind, the setup gate, the push); `the_one/agents.md` matching
    sections and the WebSocket protocol table (`gleepglorp_changed`, the new
    statuses); `docs/ui-testid-registry.md`.

## Edge Cases
- **GleepGlorp turned off mid-turn**: the running turn finishes; the next
  message is refused; the push re-joins after the turn ends.
- **Two tabs, one pending GleepGlorp chat**: the push re-renders the pending
  state in both.
- **Agents store not loaded yet** when the picker opens: the Built in group
  shows as soon as `App.gleepglorp` is loaded, independent of the agents store.
- **An agent named `GleepGlorp 2`** (from Leg 2's startup rename) is an ordinary
  agent: it is `agent` kind, not `gleepglorp`.
- **Reduced motion, both themes, 1024px**: the setup block and banner button
  use library controls only.

## Files Affected
- `the_one/interfaces/web/app.py`, `the_one/interfaces/web/api.py` (push after
  PUT), maybe `the_one/sessions/_broadcast.py` (none expected).
- `static/js/areas/chat.js`, `areas/chat/{socket,session-state,session-flow,
  chat-pane,chats-list,agent-picker,agent-drawer,transcript}.js`,
  `static/js/jump-to.js`, `static/js/gleepglorp.js`, possibly a new
  `areas/chat/agent-kind.js` (and its `index.html` script tag).
- Tests: `tests/test_ws_start_session.py`, new server tests, the listed browser
  tests, new `tests/browser/test_flow_chat_gleepglorp.py`.
- Docs: CLAUDE.md, `the_one/agents.md`, `docs/ui-testid-registry.md`.

## Citation Audit
Read-only survey of the tree during Leg 3's implementation; `app.py` and
`api.py` are being edited by Leg 3, so every app.py/api.py line here is
approximate and the Developer re-locates each by symbol. The chat JS files are
untouched by Leg 3 except possibly `store.js`-adjacent wiring.
- `app.py` `start_session` ~:3602-3728, reserved refusal ~:3608-3615 - verified (survey)
- `app.py` restore classification ~:1869-1915; `_build_session_joined_degraded` ~:2181-2208 - verified (survey)
- `app.py` `_locked_message_processing` ~:1279, DB re-sync ~:1293 - verified (survey)
- `app.py` `_SessionsPushListener` ~:139-202; `sessions/_broadcast.py` `broadcast_to_all` ~:44-63 - verified (survey)
- `areas/chat.js` setup gate ~:446-450, `setSessionHealth` ~:466-475, `healthBanner` ~:173 - verified (survey)
- `session-flow.js` `hydrateNew` ~:245-286 (`'default'` ~:249), `requestPick` ~:100-101 - verified (survey)
- `agent-picker.js` `liveAgents` ~:61-71, `source` ~:123-152, opener ~:218 - verified (survey)
- `agent-drawer.js` `describe` ~:271-282, `renderContent` ~:595-638 - verified (survey)
- `ui/page.js` `App.ui.banner` `setChildren` ~:65-147 - verified (survey)
- `api.py` `/api/chat/sessions` ~:5887-5899 accepts any `agent_name` - verified (survey)
- test pins: `test_flow_chat_list.py` ~:147/:196, `test_flow_jump_to.py` ~:542/:721-723, `test_flow_chat_drawer.py` ~:540-545, `test_flow_chat_pane.py` ~:201-207, `test_ws_start_session.py` ~:524 - verified (survey)
