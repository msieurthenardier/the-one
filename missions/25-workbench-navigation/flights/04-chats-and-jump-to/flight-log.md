# Flight Log: Chats and Jump-to

**Flight**: [Chats and Jump-to](flight.md)

## Summary

**Status**: ready (2026-10-05). 8 legs; design review: 2 Architect cycles (the cap).

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

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
