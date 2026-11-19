# Leg: proposal-card

**Status**: ready
**Flight**: [Proposals and approval](../flight.md)

## Objective
Show each GleepGlorp proposal in its chat as the approved card: board option A,
the field table, with the states as drawn. The card offers Approve, Dismiss,
Try again and Approve anyway. It sits after the turn that made it, follows the
proposal's status live and after a reload, and shows an approval as the quiet
line of option B. It also writes the two behavior-test specs.

## Context
- **Design references:**
  - Flight DD6 (the card), DD7 (the routes), DD8 (the quiet line), DD14 (the
    behavior tests and their contract).
  - The Mockups section and the option board
    (https://claude.ai/artifact/Y99KpiQHEzW7Lo6SZLrBKH): card A, states 1-7
    with their tones, the rule and routine cards, flow option B.
- **What earlier legs built:**
  - Leg 2: the `proposal_view` payload (`store.py`).
  - Leg 4: the routes (`GET /api/gleepglorp/proposals?session_id=`,
    `POST …/{id}/approve[?override=true]`, `POST …/{id}/dismiss`) and their
    responses:
    - `{"proposal": view}` for an apply or a failure (`status` `applied` or
      `failed` with `result.errors`);
    - 409 `{"error": "busy" | "stale" | "gone" | "closed"}`, where stale
      carries `fields: [{field, label, current, proposed}]`;
    - 404 for an unknown id.
  - Leg 5: the marked user messages (`proposal_id`, `proposal_event` ∈
    `approved`, `approved_no_turn`, `dismissed`) on live `user` frames and in
    history events, and the in-flight handling of an approval turn.
- **Client facts** (a survey at this leg's design):
  - **Placement.** A turn's work group has no id. Tool bubbles inside it carry
    `data-tool-call-id` (`transcript.js:271`), so a group is found by
    `messagesEl.querySelector('[data-tool-call-id="X"]').closest('[data-testid="turn-work"]')`.
    Delivered tool results are also top-level bubbles with the attribute, so
    skip any match outside a group.
  - **Timing.** The reply bubble lands at `done` (`turn-work.js` `onDone`),
    appended at the end. A card inserted earlier would sit above the reply.
  - **Wipes.** `clearLog` and `renderHistory` wipe the log, and so does
    `ensureOpen`, which can call `renderHistory`. Cards must therefore live in
    state and be redrawn by `renderHistory`, with their handles dropped in
    `clearLog`, as `widgetHandles` are.
  - **Replay** (`splitTurns`) starts a turn at every `type: 'user'` event, so
    an approval message starts its turn. That is correct, since it is the
    continuation's turn.
  - **The frame gate** (`session-state.js` `accepts`) passes gated frames only
    while joined. `proposal_changed` has no `session_id` today
    (`proposals/events.py`).
  - **Join builders.** `_build_session_joined_ok` is sync (`app.py:2186`, six
    production call sites and seven test call sites), and
    `_build_session_joined_degraded` is async (`app.py:2225`, two production
    call sites). The pause snapshot precedent (`_send_pause_snapshot_if_needed`,
    `app.py:3149`) sends a follow-up frame after `session_joined` at each join
    site.
  - **Library gaps.** No three-column label/now/proposed control exists
    (`facts` is two columns). `App.ui.button` has no busy state; busy is done
    by `disabled` in the self-configuration queue. `App.ui.noteFlag`'s
    `subject` accepts only `note` and `routine`.
  - **Lane.** A new `test_flow_chat_*` file lands in the `chats` lane unless
    it is added to `chats_transcript_pat`.
  - **Sizes.** `transcript.js` is 433 lines, `turn-work.js` 536,
    `turn-frames.js` 208, `socket.js` 410 and `areas/chat.js` 627 (cap 800).

## Inputs
- `static/js/areas/chat/`: `transcript.js` (`addUserEvent` L170-183,
  `renderHistory` L206-220, `clearLog` L187-202), `turn-work.js` (`onDone`,
  `replay`, `renderTurn`, `groupEl`), `turn-frames.js` (`handle`), `socket.js`
  and `areas/chat.js` (module `create(ctx)` wiring at L525-528).
- `static/js/ui/`: `page.js` (`facts`, `banner`, `codeBlock`), `editor.js`
  (`section`), `feedback.js` (`status`, `noteFlag` L197), `button.js` and
  `notice.js`.
- `static/js/api.js`: `fetchJson` (errors carry `.status`, `.detail`, `.body`)
  and `fieldErrors`.
- Server: `the_one/gleepglorp/proposals/store.py` (`proposal_view`),
  `events.py` (`push_proposal_changed`), and `app.py`'s join sites and
  `_send_pause_snapshot_if_needed`.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`,
  `scripts/run-tests.sh` (lanes), and `tests/browser/_chats.py`
  (`emit_frame`, `open_chat`, `message_sel`, `turn_groups`).

## Outputs
- **Server:**
  - `proposal_view` gains `title`, `target_gone`, `schedule_text` and
    `next_runs` (routines).
  - `proposal_changed` gains `session_id`.
  - A `proposals_snapshot` frame is sent after every successful or degraded
    join.
- **A new library control, `App.ui.changeTable`**, with its catalogue row,
  CSS and contract tests. `App.ui.noteFlag` gains the subject `proposal`.
- **`areas/chat/proposal-cards.js`** (new): the cards' state, rendering,
  placement and actions.
  - Hooks in `transcript.js` for the redraw, the clear and the quiet line.
  - Hooks in `turn-frames.js` for `proposal_changed` and `proposals_snapshot`.
  - Wiring in `areas/chat.js` and a `<script>` tag.
- **Testids** in the registry.
- **Browser tests:** a flow file in `chats-transcript`, and a contract file.
- **Behavior-test specs:** `tests/behavior/gleepglorp-proposal-create-agent.md`
  and `tests/behavior/gleepglorp-proposal-attach-mcp.md`.
- **Docs.**

## Acceptance Criteria
1. **Server payload.**
   - **`title`:**
     - "Create agent “X”" and "Change agent “X”";
     - "Add a rule to “X”" and "Change rule N of “X”", where N is the rule's
       current 1-based position, read when the view is built;
     - "Schedule a routine for “X”" and "Change routine “R”".
   - **`target_gone`:** `true` when a change's target (agent, rule or
     routine) no longer exists, or a create's agent is gone (rule and routine
     creates). It is computed when read and never written.
   - **Routines** gain `schedule_text` (the server sentence,
     `values_schedule_text` or `describe.schedule_sentence`) and `next_runs`
     (up to 3 human times) for both the proposed and, on a change, the current
     schedule.
   - **`push_proposal_changed`** adds `session_id` to the frame.
   - **`proposals_snapshot {session_id, proposals: [view…]}`** goes to the
     joining socket right after `session_joined`, through a new helper keyed by
     `session_id` and `agent_name`, not by `Session`. Neither builder changes.
     - **Join sites:** it runs at all eight: the six ok sites (`app.py` ~3591,
       3622, 3645, 3748, 3794, 3893), which pass `session.id`, and the two
       degraded sites (~3599, ~3759), which have only `restored` and set
       `session = None`.
     - **GleepGlorp only.** Only GleepGlorp chats can hold proposals, so other
       chats send nothing.
     - **Contents.** It carries every proposal of the chat, open and resolved,
       because the folded lines need them. It is capped at the newest 200, in
       id order.
     - **Idempotent.** A reconnect re-sends `join`, so the snapshot repeats.
     - **Degraded joins.** A test covers each of GleepGlorp off, needs model
       and provider missing, and that the repository read works with no live
       session.
   - Tests cover the titles, `target_gone`, and the snapshot on a ready and a
     degraded join.
2. **`App.ui.changeTable(opts) -> {el, set(opts)}`** (`static/js/ui/
   change-table.js`).
   - **Options:** `{columns: 1 | 2, headers?: [now, proposed], rows: [{label,
     now?, proposed, mono?}], clampChars?: 160, testid}`.
   - **Markup:** native `<table>` with `<caption class="visually-hidden">`
     from an option. Each row is `<th scope="row">` plus one or two `<td>`s.
     The column headers are `<th scope="col">`, drawn as eyebrows.
   - **Long values** (over `clampChars`) show clamped text and a "Show all"
     text button (`aria-expanded`) that reveals the rest in place. The button
     is named "Show all {label}".
   - **Look:** hairline rows on `--border`; the Now column in
     `--fg-secondary`; values wrap.
   - **The usual library rules:** DOM APIs only, no HTML strings, owned
     classes in a catalogue row, CSS in `components.css` `@layer
     components`.
   - **Contract tests:** `tests/browser/test_ui_change_table_contract.py`,
     Chromium and WebKit through `engine_page`. They cover one and two
     columns, headers, the clamp and Show all (keyboard too), `set()`
     replacing rows, and no HTML injection from values.
   - **Lane:** add `test_ui_change_table*` to `contracts_chat_pat` in
     `scripts/run-tests.sh`, so the file runs in `contracts-chat`. No other
     pattern matches it, so the lanes stay disjoint.
     - Update CLAUDE.md's `contracts-chat` lane text.
     - Record in the flight log that `contracts-chat` (150 s budget) and
       `chats-transcript` (540 s budget, which it had already passed) need a
       quiet-host re-budget at the flight-end gate.
   - **`App.ui.noteFlag`** accepts `subject: 'proposal'`, worded "Check this
     proposal: it was made after content that didn't come from you ({list}).
     It may have been planted.". Its contract test gains the case.
3. **Card states** (`proposal-cards.js`), one per proposal, keyed by id. The
   look and wording follow the board, built from library controls plus
   area-owned layout classes in `css/chat.css` `@layer areas`. The root is
   `<section data-testid="proposal-card" data-proposal-id data-state
   aria-label="Proposed change: {title}">`.
   - **`pending`, waiting:**
     - an eyebrow "Proposed change" and the time;
     - `noteFlag` `proposal` when `untrusted`, plus a hint line "Proposed
       after GleepGlorp read content not from you: {sources}. Read every field
       before you approve.";
     - the title as an `h3` (the chat page's `h1` is the header);
     - a `changeTable`: one column for a create, listing every field it sets;
       two columns (Now, Proposed) for a change, built from `base` and
       `changes`; for routines, the schedule rows use `schedule_text` and
       `next_runs`;
     - the footer: Approve (primary), Dismiss (secondary), and a hint, "Other
       settings keep their defaults." (create) or "Only these {n} fields
       change." (change).
   - **`applying`:** both buttons disabled with `aria-disabled`, the card has
     `aria-busy="true"`, and Approve reads "Approving…".
   - **`applied`:** the card folds to one line: a check icon, "Applied"
     (`--status-success` with the word), and the summary (`result.summary`)
     with its time.
     - "Open agent" is a link to `#agents/{name}`, built with the router's
       `href`.
     - "Details" is an `App.ui.disclosure` variant `plain` that holds the
       table.
   - **`dismissed`:** a quiet line, "Dismissed · {title} · {time}", with
     Details.
   - **`failed`:** the card stays open with an `App.ui.status` (`danger`,
     `role: alert`, `led: false`): "Couldn't apply this change." followed by
     each `result.errors` message with its field label (by `loc[0]` through
     the payload `labels`). The buttons are Try again (primary, which
     approves again) and Dismiss.
   - **Stale** (from a 409 `stale`): an `App.ui.banner` (`warning`, `role:
     alert`) reading "{Field label(s)} changed after GleepGlorp proposed this.
     Approving anyway replaces the current value below.", then a two-column
     `changeTable` of the stale fields (current versus proposed), then Approve
     anyway (primary, `?override=true`) and Dismiss. The status stays
     `pending`, so a reload shows the waiting state.
   - **`withdrawn`**, or `pending` with `target_gone`: a quiet line,
     "Withdrawn · {title}: the agent no longer exists." (or "…: replaced by the
     proposal below." when `result.reason == "replaced"`). There are no
     buttons.
   - **Tones:** warning appears only for "Check this" and stale, and danger
     only for failed.
4. **Placement.**
   - **The anchor.** A card belongs to the turn whose work group contains
     `[data-tool-call-id="{tool_call_id}"]`. It goes after the last node of
     that turn: walk forward from the group to the node before the next
     `.ui-message--user` element, `[data-testid="turn-work"]` group, or
     `[data-testid="chat-approval-line"]`.
   - **No anchor.** With no matching group (trimmed history, or a missing
     `tool_call_id`), the card is appended at the end of the log in id order.
   - **Live:**
     - **Hold.** A `proposal_changed` is held only when its card is not yet in
       the DOM and a turn is open. Otherwise it is drawn or updated at once.
     - **Release.** A single `turnEnded()` hook flushes the held cards. It runs
       from every path that ends a turn: `done`, cancelled (Stop), the system
       end, an agent error, the step limit, and the socket closing. With a
       reply, the card lands after it. With no reply, it lands after the work
       group, under the same walk-forward rule. A test asserts group, reply,
       card on `done`, and that a card still shows after a Stop and after the
       step limit.
     - **Update.** A status change for a drawn card updates it in place, with
       no move and no focus loss. A late card (drawn after its turn ended) is
       still anchored by its tool call, and goes to the end only when no group
       matches.
   - **Reload.** `session_joined` renders the history first, then
     `proposals_snapshot` arrives.
     - On the snapshot, the module reconciles its state and draws at once:
       anchored cards in place, unanchored ones at the end.
     - Every later `renderHistory` or `ensureOpen` redraw re-draws from the
       state.
     - A snapshot that arrives during an in-flight join (`is_processing`)
       draws the cards with their buttons busy (AC5).
     - A test joins, sees the history, receives the snapshot and finds the
       cards in place.
     - `clearLog` drops every card handle.
   - **Session scoping.** `proposal_changed` and `proposals_snapshot` are
     applied only when `session_id === chatState.boundId()`.
5. **Actions.**
   - **Calls.** Approve, Try again, Approve anyway and Dismiss call the Leg 4
     routes through `App.api.fetchJson` (POST).
   - **Disabled while busy.** The buttons are disabled while the chat's turn is
     running. Each disabled button carries the hint "Wait for GleepGlorp to
     finish."
     - The busy state is `send.isCurrentBusy()` (`send.js:18`), which is
       polled, not subscribed. `updateStopControl()` and `applyComposerState()`
       (`chat.js` ~454-456) also call `cards.refreshBusy()`, which re-reads it
       and sets every drawn card's buttons.
     - That covers Leg 5's approval turn: the cards go busy when it starts and
       are released at its end.
     - The server's 409 `busy` is the backstop.
   - **Responses:**
     - `{"proposal": view}` updates the card.
     - 409 `busy` shows a status line, "GleepGlorp is still working. Try again
       when it finishes.", in neutral tone.
     - 409 `stale` shows the stale panel.
     - 409 `gone` shows withdrawn.
     - 409 `closed` re-fetches the session's proposals (`GET`) and redraws.
     - Any other error shows "Couldn't reach the app. Try again." plus the raw
       message under a collapsed "Technical details".
   - **Frames are idempotent.** The response and the later `proposal_changed`
     frame for the same id and status are applied once (compare `status` and
     `resolved_at`).
   - **Focus**, through `App.focusAfter`:
     - `begin(button)` when the button is clicked;
     - `restore(token, target)` after the re-render;
     - `cancel()` from `clearLog`.

     The targets:
     - after an apply, the folded line's "Open agent" link;
     - after a dismiss, the composer;
     - after a failure, Try again;
     - on stale, Approve anyway.

     `focusAfter` already skips the restore when the operator moved focus
     meanwhile.
6. **The quiet line** (board option B).
   - **`approved`** (live and replay): `addUserEvent` draws `App.ui.notice`
     (`tone: 'muted'`, testid `chat-approval-line`) reading "You approved this
     change. GleepGlorp is continuing.", never a bubble.
   - **`approved_no_turn`** reads "You approved this change."
   - **`dismissed`** draws nothing (the card's Dismissed line covers it).
   - The approval text the model sees is never shown.
   - The line starts the replayed turn as the user event does today (Leg 5),
     so GleepGlorp's reply groups under it.
   - **Order with Leg 5's client tweak.** In `turn-frames.js`, Leg 5's
     in-flight marking for a `proposal_id` user frame runs first. Then this
     leg's `addUserEvent` branch draws the notice in place of the bubble.
     - The notice branch is checked before the routine marker branch.
     - `approved_no_turn` and `dismissed` frames mark nothing in flight, and
       start no work group or work state. Leg 5's tweak checks
       `proposal_event === 'approved'` only.
     - In replay, `splitTurns` makes a dismissed or approved-no-turn event a
       turn with no reply. A test checks that `renderTurn` handles that empty
       turn.
7. **Testids** are added to `docs/ui-testid-registry.md`, sorted, following
   `{area}-{element}`:
   - the card and its parts: `proposal-card`, `proposal-title`,
     `proposal-table`, `proposal-approve`, `proposal-dismiss`,
     `proposal-approve-anyway`, `proposal-try-again`, `proposal-error`,
     `proposal-stale`, `proposal-flag`, `proposal-details`,
     `proposal-open-agent`, `proposal-status-line`;
   - `chat-approval-line`;
   - the control's testids from its own options.

   This set is the behavior tests' contract (flight DD14). A later change to
   it is a spec re-author.
   - Every testid is a literal in `proposal-cards.js`, so the guard
     (`tests/test_ui_guards.py`, which syncs both ways) finds it. That includes
     `proposal-details` and `proposal-open-agent`, and the `changeTable`'s
     caller-supplied `proposal-table`.
   - A per-row or per-field id goes in the prefix-family table.
8. **Browser tests** (`tests/browser/test_flow_chat_proposals.py`, added to
   `chats_transcript_pat`). They use scripted frames with `_chats.emit_frame`
   and seeded proposals through the API seeder or the repository, with the
   Leg 4 routes live.
   - **Every state renders** with its testids and tone. A create and a change
     render with their tables. The rule and routine titles render.
   - **Live order:** group, reply, card.
   - **Reload redraws** the cards in place, through `proposals_snapshot`.
   - **Approve:**
     - Approve applies (real route) and folds the card.
     - Two windows in one browser context are not used (the operator dropped
       two-tab steps). Instead, a `proposal_changed` emitted for the same
       status after the response leaves one card.
   - **Refusals:**
     - A stale proposal (base changed through the API) shows the panel, and
       Approve anyway applies.
     - Busy: the buttons are disabled while a turn is running.
   - **Failed:** the card shows the field error and Try again.
   - **Withdrawn** by deleting the agent, then a reload.
   - **The quiet line:** an approval message renders the line, not a bubble,
     live and on reload.
   - **Accessibility:** the card's `aria-label`, the alert roles, and focus
     after each action.
   - **Static guards** are run, along with the `chats`, `chats-transcript` and
     `contracts-chat` lanes (`THE_ONE_REQUIRE_WEBKIT=1` for contracts).
9. **Behavior-test specs** (DD14), written in the project's behavior-test
   format (`.flightops/ARTIFACTS.md`):
   - `tests/behavior/gleepglorp-proposal-create-agent.md`: create an agent by
     approval, then a continued second step;
   - `tests/behavior/gleepglorp-proposal-attach-mcp.md`: attach an existing
     MCP server to an existing agent, with the agent editor open in another
     route of the same window, so it checks Leg 7's follow-through.

   Both specs:
   - run on a scratch instance (port 8486 or higher, a scratch data
     directory, a real Claude provider);
   - act by typing in the chat and clicking `proposal-approve`;
   - observe through the card's testids, `GET
     /api/gleepglorp/proposals?session_id=` and `GET /api/agents/{name}`;
   - name the credential convention section of CLAUDE.md in their
     Preconditions.

   They are run in Leg 10.
10. **Docs:**
    - `the_one/agents.md` gains "Proposal cards (M36 F2 L6)": placement,
      states, the frames, the snapshot, and the quiet line.
    - The WebSocket frame table gains `proposals_snapshot` and the
      `proposal_changed` `session_id`.
    - The catalogue gains its `changeTable` row.
    - CLAUDE.md's proposals paragraph gains one sentence on the card.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_proposals_*.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_area_module_size.py tests/test_run_tests_lanes.py tests/test_css_layers.py -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat`,
  then `--lane chats-transcript` and `--lane chats`, one at a time.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `ruff check` and `ruff format --check` on the touched files.

## Implementation Guidance
1. **The server payload:** `title`, `target_gone`, the routine schedule text
   and next runs, `session_id` on the frame, and the snapshot frame at every
   join site (follow `_send_pause_snapshot_if_needed`'s call sites). Write the
   unit tests.
2. **The control:** `App.ui.changeTable` with its catalogue row, CSS, contract
   tests and lane glob. Add the `noteFlag` subject.
3. **The cards module:** state, rendering per state, placement, and the redraw
   hook in `renderHistory`, `ensureOpen` and `clearLog`.
4. **Frames:** handlers in `turn-frames.js`, with the session check.
5. **Actions:** the actions, busy wiring and focus.
6. **The quiet line** in `addUserEvent`.
7. **Testids** in the registry.
8. **Browser tests**, then the lanes and the static guards.
9. **Behavior-test specs.**
10. **Docs.**

## Edge Cases
- **Several cards in one turn** (a replaced proposal and its replacement):
  both anchor to their own tool call. The replaced one shows "Withdrawn …
  replaced by the proposal below", above the new one, in id order.
- **The applied card for a turn that is still open after `ensureOpen`:**
  redrawn by the hook.
- **A proposal in a chat with GleepGlorp off:** the card still works
  (degraded join plus snapshot). Approve applies and shows "You approved this
  change." (`approved_no_turn`).
- **A very long prompt in `changes`** is clamped with Show all. Nothing is
  ever rendered as HTML (DOM text only).
- **The open-agent link for a rule or routine** goes to the agent's tab:
  `#agents/{name}/rules-and-notes` or `#agents/{name}/routines`. These are
  `TAB_ITEMS` ids from `agent-editor.js` ~42-50, built through `App.router`
  `href`, never as raw hash strings.
  - A failed or withdrawn create has no Open link.
  - A withdrawn change has none either, since its target is gone.
- **Narrow pane** (588px at 1280 with the drawer): the two-column table
  wraps. The labels column has a fixed width (`120px` on the board) that
  shrinks at narrow widths.

## Files Affected
- **Server:** `the_one/gleepglorp/proposals/store.py`, `events.py`,
  `the_one/interfaces/web/app.py` (the snapshot after joins), plus tests.
- **Library:** `static/js/ui/change-table.js` (new), `ui/feedback.js`
  (`noteFlag` subject), `css/components.css`, `index.html` (script tags),
  `docs/ui-control-inventory.md`.
- **Chat:**
  - `static/js/areas/chat/proposal-cards.js` (new);
  - `transcript.js`, `turn-frames.js`, `turn-work.js` (the redraw hook only,
    if needed);
  - `areas/chat.js`;
  - `css/chat.css`.
- **Tests:**
  - `docs/ui-testid-registry.md`;
  - `scripts/run-tests.sh` (two lane lists);
  - `tests/browser/test_flow_chat_proposals.py`,
    `tests/browser/test_ui_change_table_contract.py`, and the `noteFlag`
    contract case;
  - `tests/behavior/gleepglorp-proposal-create-agent.md`,
    `tests/behavior/gleepglorp-proposal-attach-mcp.md`.
- **Docs:** `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
From the design-time survey on the working tree with Legs 1-2 landed. Leg 4
and Leg 5 are not yet built, so re-check their names at implementation.
- `sign-in.js:239-244` places its block after `ctx.turnWork.groupEl()`.
  `turn-work.js:411-414` is `groupEl`, and `onDone` (~L315-342) appends the
  reply at the end — verified.
- `transcript.js`: `buildToolMsg` sets `data-tool-call-id` (L271); delivered
  tool results are top-level (L295); `clearLog` (L187-202) drops
  `widgetHandles`; `renderHistory` (L206-220); `addUserEvent` (L170-183) uses
  the routine marker — verified.
- `session-state.js` `accepts` (L181-198) gates every frame except the
  pre-gate types until the chat is joined — verified.
- `app.py`: `_build_session_joined_ok` (sync, L2186), `_build_session_joined_degraded`
  (async, L2225), `_send_pause_snapshot_if_needed` (L3149, called at six join
  sites) — verified.
- `ui/feedback.js::noteFlag` L197-210 (subject check), `ui/button.js` (no
  busy state), `ui/page.js::facts` (two columns), `ui/notice.js` (muted, not a
  live region) — verified.
- `scripts/run-tests.sh`: `contracts_chat_pat` L261-262 and
  `chats_transcript_pat` L193-200 — verified.
- `proposals/events.py`: the frame has no `session_id`; `store.py::proposal_view`
  keys — verified.
- **Design review** (Developer, Sonnet): approve with changes. The findings,
  all folded in above:
  - **Three high issues:**
    - only `onDone` appends a reply (`turn-work.js:315-342`), so a `turnEnded`
      hook was added;
    - the snapshot arrives after `renderHistory`, so cards are drawn on the
      snapshot;
    - the degraded join sites (~3599, ~3759) have no `Session`.
  - **The other findings:**
    - `send.isCurrentBusy()` (`send.js:18`) is polled through
      `updateStopControl` and `applyComposerState` (`chat.js` ~454-456);
    - `session-state.js:240-242` covers joins;
    - the `TAB_ITEMS` ids are at `agent-editor.js:42-50`;
    - `App.focusAfter` is reused;
    - the testid guard's two-way sync.

  No second cycle: these are the reviewer's own mechanisms, with no new
  design.
