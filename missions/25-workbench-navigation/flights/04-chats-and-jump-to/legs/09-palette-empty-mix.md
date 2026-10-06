# Leg: palette-empty-mix

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Give the jump-to palette's **empty query** a useful starting list, as the operator chose in
the DD13 preview (question 2, option C, 2026-10-06). The empty query now shows recent chats,
then New chat…, then the recently used agents, filled up to the cap from the existing board
order. A typed query is unchanged.

This leg follows the operator preview; DD13 says feedback that arrives before the PR merges
becomes a leg. It **changes DD10's empty-query rule**, which was "the first 8 candidates in
board order, agents first, as the board draws it". DD10's typed-query rule, its cap of 8 and
everything else stay.

## Context

- **`static/js/jump-to.js`:**
  - `candidates()` builds the board-order list: agents A–Z, chats newest first
    (`sortedChats`), the New chat… action, knowledge bases, MCP servers, connectors, then
    the Settings pages.
  - `match(query)` returns the first `CAP` (8) candidates whose `label + " " + where`
    contains the trimmed query. With an empty query that is the first 8 candidates.
  - `source(query)` maps the results to items in one unlabelled group.
- **`static/js/areas/chat/agent-picker.js`** already exports
  `App.chat.agentPicker.recentAgents(agents, sessions)`. It is the picker's "Recently used"
  rule: live agents ordered by their latest `updated_at || created_at` over sessions with
  no `platform`. A connector session is not the operator's use (A32); ties break A–Z, and
  the list is capped at `RECENT_MAX` (5).
- **The palette loads its collections** (`agents`, `sessions`, the Library ones, providers)
  and `refresh()`es as each resolves. The "keep the active row only if the user moved off
  the first one" rule (leg 7) stays.

## Acceptance Criteria

- [ ] **AC1. The empty query shows, in this order, capped at `CAP` (8) in total.** The query
  is trimmed, so a whitespace-only query takes this path too.
  1. Up to **3** most recent chats (`RECENT_CHATS = 3`), in the same order as the chat
     candidates, newest first. Connector chats are included, as in the Chats list. They
     are the same `{kind: 'chat'}` candidates as today.
  2. The **New chat…** action.
  3. Up to **4** recently used agents (`RECENT_AGENTS = 4`), from
     `App.chat.agentPicker.recentAgents(agents, sessions)` sliced to 4.
     - **Feed it** the palette's agents with null and nameless rows dropped and the
       synthetic `default` name excluded, as the picker's `liveAgents` does. A `default`
       or deleted agent is therefore never a "recently used" agent.
     - **Guard the call.** If `App.chat.agentPicker` is absent or `recentAgents` throws,
       this part is empty, through a `typeof` check and a try/catch.
     - **Map each returned row** to the same candidate shape as `candidates()`:
       `{kind: 'agent', key: String(name), label: String(name), where: 'Agent'}`.
     - **Connector-only agents are excluded** (A32, already `recentAgents`' rule). Their
       chats still appear among the recent chats; that is deliberate.
  4. **Fill:** the remaining slots, up to `CAP`, from the existing board-order candidate
     list, skipping any candidate already shown (compared by `kind` and `key`).
     - With no chats the list is New chat… then agents A–Z, then the other kinds.
     - An empty install still lists New chat… then the Settings pages.
     - Fill rows keep board order, so agents come before any further chats. That is
       accepted.
     - A chat row and an agent row for the same agent can both show; they are different
       kinds.

  **Where the mix lives.** Implement it as a small pure helper (`emptyMix(all)`, given
  `candidates()`'s list) called from `match()` when the trimmed query is empty. Then
  `match('')`, `source('')` and the exported `match` all return the mix, and `candidates()`
  stays pure board order.

  **While the stores load:**
  - With `sessions` loaded and `agents` not, the mix is the chats, New chat…, then the
    fill, with no recent agents.
  - Each `refresh()` re-derives the mix as a collection arrives, so the first row
    visibly flips from New chat… to the newest chat when `sessions` loads.
  - The leg 7 keep rule still applies: a row the user moved to is kept by id.
- [ ] **AC2. A typed query is unchanged:** the first 8 board-order matches.
- [ ] **AC3. Rendering is unchanged:**
  - one unlabelled group;
  - the same item shape (`jump-to-result`, `data-kind`, `data-id`, the "where" text);
  - the first row active (the most recent chat, or New chat… when there are no chats);
  - the active-row keep rule on refresh;
  - `App.jumpTo.candidates()` keeps its meaning (board order).

  Export `App.jumpTo.RECENT_CHATS`, `App.jumpTo.RECENT_AGENTS` and `emptyMix` beside
  `CAP`.
- [ ] **AC4. Tests in `tests/browser/test_flow_jump_to.py`:**
  - **Rename** `test_empty_query_shows_the_first_eight_candidates_in_board_order` to
    `test_empty_query_mixes_recent_chats_new_chat_and_recent_agents`. Rename rather than
    delete and re-add, so `git blame` shows the intent shift. Against the existing `world`
    fixture its rows are:
    1. Newest chat;
    2. Tie one and Tie two, in store order;
    3. New chat…;
    4. Alpha, then test-agent (the recent agents);
    5. the fill: the untitled chat, then `alpha_chat`.

    That is 8 rows. The first active row is the newest chat.
  - **Wait for the final state**, not "agent and chat rows exist": `sessions` and
    `agents` load independently, so the mix changes as they arrive. Poll `_rows` until it
    equals the expected list, or expect the row at a recent agent's position. The
    first-row-active assertion becomes the newest chat.
  - **New cases with their own seeding.** `world` has only two agents.
    - **More than 3 chats and more than 4 used agents.** Use at least 5 agents with web
      sessions and distinct timestamps. Expect exactly 3 chats, New chat… at index 3,
      exactly 4 agents in recency order, total 8.
    - **A connector-only agent.** Its chat appears among the recent chats, and it is
      absent from the slots right after New chat…. It may still appear later as an A–Z
      fill row.
    - **No sessions.** Assert the exact rows: New chat… then the agents A–Z, then the
      other kinds by board order. Seed enough agents, or state the expected tail.
    - **No duplicate in the fill.** A recently used agent is not repeated.
    - **A deleted agent.** A chat whose `agent_name` is no longer an agent still shows
      as `Chat · {name}` among the recent chats, and is not a recent agent.
  - `test_an_empty_install_lists_new_chat_and_the_settings_pages` must still pass
    unchanged.
  - The other palette tests type a query first, so they should be unaffected. The
    `shared` lane confirms it.
- [ ] **AC5. The spec `tests/behavior/jump-to-palette.md`:**
  - Re-author step 2's Expected Result for the seed. The empty query shows exactly 8:
    1. "jtp chat about tiles" (`Chat · jtp-agent-02`, `data-kind="chat"`), active;
    2. "New chat…" (`Action`);
    3. `jtp-agent-02` (`Agent`);
    4. `jtp-agent-01`, `jtp-agent-03`, `jtp-agent-04`, `jtp-agent-05`, `jtp-agent-06`
       (`Agent`).
  - Update the Intent bullet ("finds agents…"), if needed, and the Preconditions line
    "(the empty query's first 8 results … depend on it)", which becomes "the empty query's
    mix". Add an `Updated` line.
  - Check that no other step depends on the empty query's content (step 13 opens the
    palette but does not read the rows).
- [ ] **AC6. Docs and comments.** Remove every claim that the empty query shows "the first
  8 (the board as drawn)":
  - `CLAUDE.md`'s "Jump-to palette" paragraph.
  - `the_one/agents.md`'s "Jump-to palette" Candidates/Matching bullet: replace "(the
    board as drawn; a DD13 preview question)" with the operator's decision.
  - `jump-to.js`'s header comments (the `match` lines and the "empty query shows the first
    8" lines).
  - `tests/browser/test_flow_jump_to.py`'s module docstring.
  - `docs/ui-control-inventory.md`'s jump-to row, if its wording implies the empty query.
  - `flight.md`:
    - in DD10, a dated note under the empty-query bullet recording option C and this leg;
      keep the original text;
    - in DD13's question list, mark the empty-query item resolved;
    - a nod to the new rule on the A17 row.
  - `missions/25-workbench-navigation/reference/reference-spec.md` §9's empty-query line
    gets a one-line "superseded by Flight 4 leg 9" note. Do not rewrite the spec.
  - Leave `legs/07-jump-to-palette.md` as the historical record.
- [ ] **AC7. Gates:**
  - `ruff check`;
  - the static guards (`tests/test_ui_guards.py tests/test_token_definitions.py
    tests/test_design_tokens_a11y.py tests/test_nav_helper.py
    tests/test_ui_control_inventory.py tests/test_run_tests_lanes.py
    tests/test_settings_pages_static.py`);
  - the `shared` browser lane (it holds `test_flow_jump_to.py`), through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` and `TEST_TIMEOUT=3600`;
  - the `chats` lane, as a smoke check that the picker's exported helper is unaffected.

  The numbers go in the flight log.

## Verification Steps

- AC7's commands.
- **Falsify once:** make the empty query return the plain board order again, watch the
  renamed test fail, then restore it. Record the result.

## Files Affected

- `the_one/interfaces/web/static/js/jump-to.js`
- `tests/browser/test_flow_jump_to.py`
- `tests/behavior/jump-to-palette.md`
- `CLAUDE.md`, `the_one/agents.md`, `missions/25-workbench-navigation/flights/04-chats-and-jump-to/flight.md` (DD10 note)
- The flight log
