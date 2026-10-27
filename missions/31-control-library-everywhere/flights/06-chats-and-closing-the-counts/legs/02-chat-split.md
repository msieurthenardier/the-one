# Leg: chat-split

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Split `js/areas/chat.js` (2,399 lines) into the modules of DD3 (seven, plus `send.js` added at this leg's design review) with **no behaviour change**, so `chat.js` drops to 800 lines or fewer and the later legs each touch one concern:
- strings, DOM shapes, frame handling order, timers, testids and public seams are moved unchanged;
- the guard bookkeeping records every moved ownership use as a move.

## Context
- **Flight decisions:** DD3 (the split, its modules and the three-phase frame order), DD13 (standing rules), DD15 (lanes; the full gate after this leg).
- **After leg 01:** the five sinks are gone (`replaceChildren()`), `HTML_SINK_ALLOWANCE` is empty and `START_ROWS` is the Flight 6 start set. So this split moves **no sinks**, and needs no `SINK_MOVES`.
- **The house pattern** (studio, M31 F2; `areas/studio.js:218-262`):
  - each module is an `App.studio.<name>.create(ctx)` factory;
  - the shell passes one mutable `state` object and explicit callbacks;
  - a module created later is reached through a **call-time getter** (`list: function () { return agentsListMod; } // call-time`).

  The MCP editor split (M31 F5 L02, `areas/studio/mcp-editor-shared.js:10-14`) used a sub-namespace the same way.
- **`chat.js` today** is one `init` closure. The code survey's group map (`$HOME/.cache/the-one-ui-capture/m31-f6-planning/f6-code-survey.md` §1.1) lists every function, its line range, the closure state it reads and writes, and its callers. Re-derive the line ranges from the file as it stands after leg 01, because the clears changed a few lines.
- **The existing `App.chat` namespace** holds `agentDrawer`, `agentPicker`, `appendToTrace`, `chatPane`, `chatWith`, `chatsList`, `composer`, `createSessionState`, `createThinking`, `fmtTokens`, `newClientId`, `openPicker`, `registerPickerHost`, `removeThinking`, `renderAttribution`, `renderMessage`, `renderTelemetry`, `renderThinking`, `renderTrace`, `resetTelemetry`, `setTelemetryMax` and `updateTelemetry`. The new members (`transcript`, `signIn`, `attachments`, `holdQueue`, `sessionFlow`, `socket`, `turnFrames`) collide with none of them. Inside `chat.js` there is also a private `renderThinking(evt)` (the thinking disclosure from a frame), distinct from `App.chat.renderThinking`. Keep it private to the module that takes it.
- **The test seams** set in `init` (`chat.js:2351-2381`):
  - `self._connect`, `_ws`, `_refreshAgentsAndSetup`, `_serialize`, `_hydrate`, `_joinSession`, `_sessionState`, `_currentSessionId`, `_pendingJoinId` (a getter and setter) and `_agentDrawer`;
  - `registerPickerHost`, which must stay the **last** statement of `init`.

  Tests use `_sessionState` (28 uses), `_ws` (10), `_joinSession` and `_currentSessionId`. They keep working unchanged.
- **The code-text anchors to re-anchor** (never relax: each assertion keeps its strength and points at the file that now holds the code):
  - `tests/test_store_static.py:105-213`:
    - the `session_list`, `sessions_changed` and `session_joined` → `start_failed` windows;
    - `toSessionSummary`;
    - `App.store.prime('sessions'` exactly once per branch;
    - `renderChatsList()` count 1, and its presence in `renderPending`, `openConversation`, `resetToIdle`, `clearConversation` and the `session_joined` window;
    - `App.store.subscribe('sessions'` count 1;
    - `if (joinedEff.render === 'history') renderHistory(` and the single `return;`;
    - `"sendBinding({ action: 'leave' })"`.

    Where a call becomes `ctx.renderChatsList()` or similar, the assertion targets the new spelling in the new file, and keeps its counts and windows. A window that now spans two files becomes two assertions, never a looser one. In detail:
    - `test_chat_session_list_primes…` (`:105`): `toSessionSummary` stays in `chat.js`, and the `session_list`, `sessions_changed` and `session_joined` windows are read from `socket.js`. The "not in" needles stay as substring checks. `"renderList(" not in src` and `"renderSessionList" not in src` run over the **concatenation** of `chat.js` and every new module, so they do not weaken.
    - `test_chats_list_renders_from_the_sessions_subscription_only` (`:140`): the `renderChatsList` definition, its count of 1 and the subscribe stay in `chat.js`. The windows of `renderPending`, `openConversation`, `resetToIdle` and `clearConversation` are read from `session-flow.js`, where `ctx.renderChatsList();` still contains `renderChatsList();`. The `session_joined` window is read from `socket.js`.
    - `test_start_session_join_refreshes…` (`:171`): `renderHistory(` becomes the new spelling (for example `ctx.transcript.renderHistory(`). `function refreshSessionList()` is anchored in `session-flow.js`.
    - `test_retired_new_session_path…` (`:211`): `"sendBinding({ action: 'leave' })"` sits in `goPick`, so it is read from `session-flow.js` (with the new spelling if it gains a prefix).
  - `tests/test_consent_link_static.py:20-23` (script order: the module holding sign-in loads after `ui/consent-link.js`) and `:47-49` (`isSafeUrl(` ≥ 2 and `consentSafe` ≥ 3, now counted in `chat/sign-in.js`).
  - Windows close on `"\n    }"`. Functions nested in `create(ctx)` inside an IIFE keep the same four-space indent, so the closers still match, but check each one.
- **Script tags.** The eight new modules go in `index.html` between the existing chat modules (`:70-79`) and `areas/chat.js` (`:80`). `tests/test_index_asset_cache_busting.py:85-98` pins only the order (every `js/areas/chat/*` before `js/areas/chat.js`); there is no count pin. The Makefile's `verify-serving` list derives only admin modules, so nothing changes there.
- **The line guard.** `tests/test_area_module_size.py:24-28` lists `"chat.js": 2399`. It fails on a listed module at 800 or fewer, so the entry is **removed in this leg**. Every new module must be 800 or fewer.
- **The ownership moves.** `chat.js`'s rows today:

  | Key | Uses | Moves to |
  |---|---|---|
  | `api:App.consentLink.` | 4 | `chat/sign-in.js` |
  | `consent-link` | 1 | `chat/sign-in.js` |
  | `btn-filled-primary` | 1 | `chat/sign-in.js` (the "Log in" button) |
  | `chip` | 1 | `chat/attachments.js` |
  | `api:App.confirmDelete(` | 1 | stays in `chat.js` (construction, the Chats list delete) |
  | `confirm-delete` | 2 | stays in `chat.js` (the same block) |

  Each moved row gets an `OwnershipMove(key, from_file, to_file, uses, retire_by)` entry in `tests/_ui_ownership_allowance.py`, with paths relative to `static/` (`js/areas/chat.js`, `js/areas/chat/sign-in.js`). `retire_by` names the leg that removes the use (05a for `chip`; 05b for the sign-in rows). In `OWNERSHIP_ALLOWANCE`:
  - the four old `("js/areas/chat.js", key)` rows are **deleted**, since `measure()` then finds 0 uses there and the exact-match test would fail;
  - four new rows are added with the same counts under the new files.

  `TOTAL_USES` is unchanged. `stale_move_errors` checks only `to_file`, so check every `from_file` by hand. Today's sites: `btn-filled-primary` `:1378` (`renderLoginRequiredButton`), `consent-link` `:1337` (`resetLoginGroups`), `chip` `:239` (`buildAttachmentChip`). `confirm-delete` `:320`, `:323` and `App.confirmDelete(` `:332` stay in the `chatsList` construction block.

## Inputs
- Leg 01 landed (the sinks at zero, `START_ROWS` rewritten, the lanes split). Its tree is uncommitted on the flight branch.

## Outputs
- **New modules** under `js/areas/chat/` (names fixed by DD3; boundaries may shift within a group where a function's closure state demands it, and each shift is recorded in the flight log):
  - `transcript.js` (`App.chat.transcript.create(ctx)`): `addMsg`, the scroll pin, clear, `renderHistory`, streaming (pacing, safe boundary, finalize), thinking show and hide and the model-loading row, trace shells, tool bubbles, delivered results.
  - `sign-in.js` (`App.chat.signIn`): popups, `loginFlows`, `sourceNames`, the login group render and reset, the `auth_*` handlers, and the settle-close that runs above the frame gate.
  - `attachments.js` (`App.chat.attachments`): staging, chips, caps, the file input and its listeners.
  - `hold-queue.js` (`App.chat.holdQueue`): the one-slot client hold and its chip.
  - `session-flow.js` (`App.chat.sessionFlow`): pick, open, reset, clear, the idle rules, hydrate, validate, heal, `startSend`, `applyStartFailed` and the live-refresh flags.
  - `socket.js` (`App.chat.socket`): `connect`, `onopen`, `onclose`, the single `sock.onmessage` entry and the session frames.
  - `turn-frames.js` (`App.chat.turnFrames`): the gated frames and `handleSystem`. It delegates `auth_*` to sign-in, and **the entire `auth_required` branch body moves to `sign-in.js`**. That keeps `test_consent_link_static.py`'s counts (`isSafeUrl(` ×2, `consentSafe` ×3) and all four `App.consentLink.` uses in one file.
  - `send.js` (`App.chat.send`; added at design review, within DD3's "module boundaries may vary"): `performSend`, `sendHeld`, `send()`, `setInputValue`, `updateStopControl` and `isCurrentBusy`. Without it, `chat.js` lands at about 760 lines before the `create(ctx)` plumbing.
- **`chat.js` remains** with:
  - the descriptor and `state`;
  - construction (the list, pane, composer and drawer);
  - `renderPane`, `renderChatsList`, `toSessionSummary` and the subscriptions;
  - the welcome;
  - `applyComposerState`, `setSessionHealth`, `refreshAgentsAndSetup`;
  - the composer and Stop wiring, and the seams, with `registerPickerHost` after every module's creation.

  **The bound is about 650-750 lines, with a hard cap of 800.** After the leaves-first moves (hold queue, attachments, send, transcript), measure. If the projection for the rest would pass 800, move more before the last groups, and record the decision.
- **One owner for every variable and function** (the design review's table; the Developer copies it into the flight log as step 1's map, with any change):

  | Name | Owner |
  |---|---|
  | `ws` | `socket.js`, exposed as `ctx.ws()`; `self._ws` returns it |
  | `boundOn`, `sendBinding`, `socketOpen` | `socket.js`; `sendBinding` and `socketOpen` exposed on its handle |
  | `pendingJoinId` | `session-flow.js`, with a get/set accessor on its handle for the `_pendingJoinId` seam |
  | `clearLiveRefresh`, `rejoinForUpdate`, `requestRefresh`, `refreshSessionList`, `showNotice`, `setWelcomeNotice` | `session-flow.js` |
  | `handleSystem` | `turn-frames.js` |
  | `clearLoginRequiredButton`, `openConsentPopup`, the login-flow functions | `sign-in.js` |
  | `performSend`, `sendHeld`, `send`, `setInputValue`, `updateStopControl`, `isCurrentBusy` | `send.js` |
  | **shared mutable state, in `state`:** `inFlightSessions`, `ownTurn`, `refreshAfterTurn`, `updateRejoin`, `refreshAfterJoin`, `pendingQueuedMessages`, `sessions`, `listSeen`, `firstListPending`, `rebinding`, `validating`, `pickIntent`, `currentAgentName`, `currentSessionPlatform`, `joinedTitle`, `liveToolNames`, `startBubbleNodes`, `sessionBannerEl`, `setupState`, `setupIncomplete` | read and written as `state.x` by every module |

  A variable used by one module only stays in that module's closure.
- **The `session_joined` handler** (about 190 lines, touching nearly every group) moves to `socket.js` as **one block**, with calls prefixed mechanically. No helpers are extracted from it: `test_start_session_join_refreshes_the_list…` asserts exactly one `return;` in its window.
- **The module shape:** an IIFE at two spaces, `function create(ctx) {` at two spaces, and the functions inside it at four (the shape of the existing chat modules). A `create:` method in an object literal would put the functions at six spaces and break every `"\n    }"` window.
- **The frame order** in `sock.onmessage` stays exactly:
  1. `boundOn = sock` on `session_joined` runs first;
  2. the session lifecycle frames, each returning;
  3. the global popup close for `auth_resolved` / `auth_failed`;
  4. the frame gate `if (!chatState.onFrame(data).accept) return;`;
  5. the gated frames.

  There is one `onmessage` entry. `tests/browser/test_oauth_modal_flow.py:51-70` calls `ws.onmessage({data})` directly.
- **`ws`** stays a closure variable in the owner of `connect` and is exposed as `ctx.ws()`. `self._ws` returns the live socket.
- **`index.html`:** eight new script tags before `areas/chat.js`, in dependency order. No test checks the order among them, so check it by hand.
- **Guards:**
  - `tests/test_area_module_size.py` loses the `chat.js` entry;
  - `tests/_ui_ownership_allowance.py` gains the four `MOVES` entries, and `OWNERSHIP_ALLOWANCE` moves those rows to the new files;
  - the anchors above are re-anchored.
- **Docs:**
  - `the_one/agents.md`: a module-map note, plus the chat passages that name moved internals. These are about `:927` (the drawer notes' live refresh and `liveToolNames`), `:1499` (`toSessionSummary`), `:1501` (the live-refresh flags), `:1505`, `:1540`, `:1552-1554`, `:1556`, `:1561`, `:1572` and `:2444` (the invalidation table's `chat.js` `session_joined` row);
  - CLAUDE.md's "Chats pane" / "Chat composer" mentions of `chat.js` internals are updated only where they name a function that moved.
- **The flight log:** this leg's entry (the module map with final line counts, any boundary shifts) and the full-gate result.

## Acceptance Criteria
- [ ] `wc -l js/areas/chat.js` is 800 or fewer, every new module is 800 or fewer, and `tests/test_area_module_size.py` passes with the `chat.js` entry removed.
- [ ] **No behaviour change.** No test's assertions are edited except the re-anchored static tests (path and spelling only, with counts and windows kept). Every browser lane that touches chat passes: `chats`, `chats-transcript`, `shared` (`test_oauth_modal_flow.py`, `test_markdown.py`, `test_flow_jump_to.py`), `routing` and `agents` (`test_agents_chat_action.py`).
- [ ] **The frame order holds:** a reading of `chat/socket.js` shows the five steps above in order, and `test_oauth_modal_flow.py` passes unchanged.
- [ ] **The moves:** `tests/test_ui_ownership.py` passes with exactly the four `MOVES` entries and `TOTAL_USES` unchanged. `tests/test_ui_guards.py` passes with no `SINK_MOVES`.
- [ ] `tests/test_store_static.py` and `tests/test_consent_link_static.py` pass with every assertion's strength kept. The diff of those two files shows path and spelling changes only.
- [ ] `tests/test_index_asset_cache_busting.py` passes.
- [ ] `registerPickerHost` is still called after every module's creation in `init`; only seam assignments (such as today's `self._agentDrawer`) may follow it.
- [ ] **No stray bare names.** A grep check, recorded in the flight log, finds no bare use of any name moved into `state` (for example `\bsessions\b`, `\binFlightSessions\b`, `\bownTurn\b` without `state.`) in `chat.js` or the new modules, apart from declarations and documented locals. A grep for `=>`, `\blet\b`, `\bconst\b` and backticks in the new modules finds nothing (ES5 house style; no guard covers `js/areas`).
- [ ] **The full gate:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes (unit, then every browser lane), and `ruff check` and `ruff format --check` pass. Lane times are recorded but not re-budgeted from this run unless the host is quiet.

## Verification Steps
1. `wc -l the_one/interfaces/web/static/js/areas/chat.js the_one/interfaces/web/static/js/areas/chat/*.js`.
2. `.venv/bin/python -m pytest tests/test_area_module_size.py tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_store_static.py tests/test_consent_link_static.py tests/test_index_asset_cache_busting.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`.
3. `git diff -- tests/test_store_static.py tests/test_consent_link_static.py` (path and spelling only).
4. `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x --tb=short`, then the same for `chats-transcript`, while iterating.
5. The full gate (above), once, at the end.

## Implementation Guidance
1. **Map first.** Re-derive the group map from the post-leg-01 file. For each group, list the closure variables it reads and writes, and decide where each lives:
   - in `state` (shared and mutable);
   - in one module's closure (owned there, with an accessor on its handle when another module reads it);
   - or a closure variable in `chat.js` behind a `ctx` getter (`ws`).

   Write the map into the flight log before moving code.
2. **Move one group at a time**, leaves first: hold queue, attachments, send, transcript, sign-in, turn frames, session flow, socket. Measure `chat.js` after the first four, and decide on any extra move before the last groups. After each move, run the static guards and `--lane chats` (or `chats-transcript` for the transcript group). Keep each moved function's text identical apart from `ctx.` / `state.` prefixes.
3. **Call-time getters** for any module created later, as in studio. Construction order in `init`: `state`, construction (list, pane, composer, drawer), then the modules in dependency order, then the seams, with `registerPickerHost` last.
4. **The static anchors** next. Re-point each assertion to the file that now holds the code, keeping counts and windows.
5. **`MOVES`, the line guard and the allowance rows.** Then the docs, then the full gate.

## Edge Cases
- **Hoisting.** Function declarations inside the old closure were hoisted, so calls that appear before a definition worked. In a module, a call into another module must go through `ctx` or a handle that exists at call time. Watch the frame handlers that call into session flow, and the reverse.
- **`this`-free, ES5 only.** No arrow functions, `let`, `const`, classes or template literals in `js/areas/` (the house style; the library's ES5 guard covers `js/ui`, so hold area modules to the same).
- **Timers keyed on closure state** (pacing, the reconnect timer, the model-loading dots) must keep reading the same variable after the move. One owner per timer.
- **A superseded socket.** The `sock !== ws` checks must compare against the live `ws` through the getter, not a copy captured at module creation.
- **`pendingJoinId`'s getter and setter seam:** the seam must still read and write the same variable the flow uses.
- **Tests that spy on globals:** `test_oauth_modal_flow.py` replaces `window.open` before the click. `window.open` is called at click time (`:1237-1260`, `:2133`); make sure no module captures it at creation time.
- **Shadowed names.** `sessions` and similar short names appear as locals and parameters too. The `state.` prefixing must not touch a local of the same name. The bare-name grep covers this.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js`.
- `the_one/interfaces/web/static/js/areas/chat/{transcript,sign-in,attachments,hold-queue,send,session-flow,socket,turn-frames}.js` (new).
- `the_one/interfaces/web/static/index.html`.
- `tests/test_area_module_size.py`, `tests/_ui_ownership_allowance.py`, `tests/test_store_static.py`, `tests/test_consent_link_static.py`.
- `the_one/agents.md`, CLAUDE.md (only where a moved function is named), the flight log.

## Citation Audit
- `areas/studio.js:218-262`: the `create(ctx)` pattern with call-time getters. FD-verified (read).
- `areas/chat.js:2351-2381`: the `self._*` seams; `registerPickerHost` last. FD-verified (grep).
- `index.html:70-80`: the chat module tags, then `areas/chat.js`. FD-verified.
- `tests/test_store_static.py:105-130`: the `session_list` / `sessions_changed` windows and `toSessionSummary`. FD-verified (read). `:140-213` per the code survey §1.4; re-verify after leg 01.
- `tests/test_area_module_size.py:24-28`: `"chat.js": 2399`. FD-verified.
- **Re-verified after leg 01 (FD grep, 2026-10-27):** `chat.js` is 2,398 lines. `buildAttachmentChip` `:237`, `confirm-delete` `:320`/`:323`, `App.confirmDelete(` `:332`, `resetLoginGroups` `:1332` (`.consent-link` `:1337`), `renderLoginRequiredButton` `:1353` (`btn-filled-primary` `:1378`), the seams from `:2350`, `registerPickerHost` `:2375`, `self._agentDrawer` `:2380`. The leg's other line citations are within one line of these; the Developer still re-derives ranges from the file.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only during leg 01's runs): approve with changes.** Applied in place:
  - **[high] ownership:** the one-owner table for shared state and cross-group functions; `boundOn`, `sendBinding` and `socketOpen` in socket; the live-refresh flags in `state` (FD answers to the reviewer's questions);
  - **[high] the line bound:** a new `send.js`, the bound restated as about 650-750 with a hard cap of 800, and a measure-and-decide step after the leaves;
  - **[medium] `session_joined`** moves as one block;
  - **[medium] the anchors:** each re-anchor spelled out, the concatenated-source "not in" checks, the whole `auth_required` body in sign-in, and the four-space indent shape;
  - **[medium] the allowance:** delete the old rows and add the new ones; check `from_file` by hand;
  - **[low] `registerPickerHost`** reworded to after every module's creation;
  - **[low] checks:** the bare-name grep and the ES5 grep;
  - **[low] edge cases:** the `window.open` timing note and the `agents.md` line list.
- The FD judged these a sharpening of the leg's own design, plus one module added within DD3's stated latitude, so there is no second cycle. The leg goes `ready` when leg 01 lands and its `chat.js` line numbers are re-checked.
