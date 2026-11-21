# Leg: page-awareness

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective
Every message sent from the drawer carries the page the operator is on.
- **The model.** GleepGlorp reads it as one marked line,
  `[Page: Library › MCP servers › New MCP server]`, on the turn it was sent
  and byte-identical on every later turn.
- **The transcript.** Both chat instances show the server's line as a quiet
  chip above the operator's bubble, live and after a reload.
- **Chats and other agents.** Chats sends no page, and every other agent
  never sees one.

## Context
- **Flight DD5** is the design. **Operator approval (2026-11-19):** one
  optional `page=` keyword on the frozen `Agent.step`, and nothing else in
  `agent/core.py`. The flight's divert rule applies: if the page needs more
  of `core.py` than that one keyword, stop and report `[BLOCKED]`.
- **Legs 1-3 (landed, batch A):**
  - `App.chat.create(config)` builds both instances, and `ctx.profile` is
    `'chats'` or `'drawer'`.
  - The drawer instance is `js/gleepglorp-drawer/chat.js` (`profile:
    'drawer'`, ~:121).
  - `App.router.describeCurrent()` returns `{route, destination, parts}`.
- **Why not a turn-end mark, and why not a prefix in `user_input`:** see
  DD5.
- **Leg 5 needs `TurnContext.page`.** It is the gate for `fill_form` (fills
  only from the drawer), and its descriptor says which editor the operator
  is on.
- **Design review (2026-11-20, approve with changes).** The FD's decisions
  are folded in below:
  - the sender's chip comes from the server (`page_line`);
  - descriptors are validated sync and resolved async;
  - `page=` is passed to `step` only when there is a page;
  - a new eval turn form;
  - the chip is a sibling of the bubble;
  - malformed pages are refused for every agent;
  - create names copy the editor titles;
  - `›` is stripped from names.

## Inputs
- Batch A landed (Legs 1-3).
- The code cited in the Citation Audit below.

## Outputs

### Server: `the_one/gleepglorp/page.py` (new)
Pure functions plus one async resolver. The harness and Leg 5 import the
pure parts without the database.
- **`validate_descriptor(raw) -> (dict | None, error | None)`** (pure, sync).
  It checks the shape only. The descriptor is
  `{destination, section?, item?, item_name?, tab?, create?}`:
  - `destination`: one of `agents`, `library`, `settings`. `chats` is
    refused.
  - `section`:
    - for `library`, a Library group (`providers`, `knowledge`, `mcp`,
      `connectors`, `secrets`);
    - for `settings`, a Settings page section, including `gleepglorp`;
    - for `agents`, absent.
  - `item`: the route's item segment, a string of 1-200 characters, or
    absent.
  - `item_name`: a string of at most 200 characters, or absent.
  - `tab`: an agent editor tab id, or absent.
  - `create`: a boolean.
  - **Two kinds of fault, handled differently** (design review cycle 2: a
    client and server table drift must never break the drawer):
    - **A shape fault refuses the message.** That is a non-dict, an unknown
      key, a wrong type, or a string over its cap.
    - **A value fault keeps the message and drops the page.** That is a
      destination, section or tab not in the tables. The server logs one
      warning line and the turn runs with no page.
  - The client truncates `item` and `item_name` to their caps before
    sending.
- **Label tables:**
  - the destinations: Agents, Library, Settings;
  - the Library group labels (router.js `LIBRARY_LABELS`);
  - the Settings page labels (settings-pages.js);
  - the agent tab labels (the agent editor's `TAB_ITEMS`);
  - the create names, copied exactly from the editor titles: **"New
    Agent"** (`agent-editor.js` ~:234), "New model provider", "New
    knowledge base", "New MCP server", **"New Connector"**, "New secret".
- **`sanitize_name(s)`:**
  - removes control and bidi characters, newlines, `[`, `]` and `›`;
  - collapses whitespace;
  - caps the result at 80 characters with "…".
- **`build_line(descriptor, resolved_name=None) -> str`** (pure). It joins
  the labels with " › ", for example "Library › MCP servers › New MCP
  server", "Agents › Researcher › Tools", or "Settings › Built-in tools ›
  web_search". The line is capped at 240 characters.
- **`async resolve_page(conn, descriptor) -> {"line", "descriptor"}`.**
  - An agent item resolves to itself when the agent exists.
  - A Library id resolves to the stored name through the matching
    repository's async `get`. The Developer names each repository in the
    flight log:
    - `LLMProviderRepository` (providers);
    - `KnowledgeBaseRepository` (knowledge);
    - `MCPSourceRepository` (mcp);
    - `ConnectorRepository` (connectors);
    - `SecretRepository` (secrets).
  - A Settings tool item is the tool name.
  - When nothing resolves, the line uses the sanitised `item_name`, and
    failing that the sanitised segment.
  - A repository error falls back the same way and never fails the turn.
- **The pin.** `tests/_app_routes.py` gains label readers:
  - a new regex over router.js `LIBRARY_LABELS`;
  - the settings and tab regexes also capture their label;
  - per-file regexes for the six create-name title literals:
    - `areas/studio/agent-editor.js`;
    - `provider-editor.js`;
    - `knowledge-create.js`;
    - `mcp-server-editor.js`;
    - `connector-editor.js`;
    - `secret-editor.js`.

    The literals come in two shapes: `title: isCreate ? 'X' :` and, in
    `knowledge-create.js`, `title: 'X',`. The `LIBRARY_LABELS` object spans
    several lines.

  Existing callers keep their id-only results. `tests/test_gleepglorp_page.py`
  pins every `page.py` table equal to these.

### Server: the WebSocket and the turn
- **`_validate_message_payload`** calls `validate_descriptor` on an optional
  `page`. `ValidatedPayload` gains `page` (append the field with a default
  of `None`, so every existing constructor still works).
  - A page with a shape fault refuses the message for **every** agent, with
    the text "Malformed page context.". On `message` it is a `system` frame.
    On `start_session` it is `start_failed`, and no session is created.
  - The order is: the message type, then emptiness, then the page, then the
    images. An empty message stays an empty message, even with a malformed
    page.
  - Validation runs before `/reset`, so a `/reset` with a malformed page is
    refused, and a `/reset` with a valid page ignores the page.
- **One helper, `async _page_for(agent_name, page)`, called before each of
  the three spawn sites:**
  - the start_session existing/deliver site (~:3864);
  - the start_session new site (~:3914);
  - the `message` site (~:4023).

  It returns `None` unless `agent_name == GLEEPGLORP_AGENT_NAME` and a
  valid page was sent. A valid page for any other agent is dropped
  silently. Use the agent name of the session that actually runs the turn:
  - `existing.agent_name` at the existing/deliver site (a restored session
    can belong to another agent than `start_agent`);
  - the new session's `agent_name` at the new site;
  - `session.agent_name` at the `message` site.
- **`_spawn_web_message(session, content, ws, page=None)`** passes
  `turn_info={"page": page}` to `_spawn_message_processing` **only when
  `page` is set** (follow the `extra = {}` precedent near app.py:1342).
  Tests patch these signatures.
- **`_process_and_broadcast`** reads `turn_info.get("page")`. When it is
  set:
  - it calls `session.agent.step(..., page={"line": line})`. With no page,
    the call is byte-identical to today, with no `page` keyword, because at
    least twelve test files define `step` doubles without it;
  - it sets `TurnContext.page = {"line", "descriptor"}`;
  - it adds `"page": {"line": line}` to the `user` event that goes to the
    other subscribers;
  - **it sends the sender alone** (`exclude_user_echo`, the socket that sent
    it) one new frame, `{"type": "page_line", "session_id", "line"}`. The
    sender never gets the echo, and this is how its chip shows the server's
    line. No helper sends to one socket (`_send_to_session` only excludes).
    Send it directly with `exclude_user_echo.send_json(...)`, guarded by a
    try, with `remove_subscriber` on failure, and only when
    `exclude_user_echo` is not None.

  The title still comes from the plain text.
- **Turns with no page, each unchanged:**
  - routine turns and proposal continuations;
  - `resume_after_auth` and connector turns;
  - the REST `/api/chat` route;
  - `/api/selftest` and `the-one chat`.
- **`agent/core.py`.** `step(self, user_input, on_chunk=None,
  on_usage=None, page=None)` sets `.page = page` on the appended user
  message when `page` is not `None`, plus one docstring line. Nothing else
  changes.
- **`Message.page: dict | None = None`** (`llm/base.py`).
  - It is USER-only and holds `{"line": str}` only.
  - The codec emits it only when it is non-None, and decodes it only when it
    is a dict with a string `line`; anything else is `None`.
  - `messages_to_ui_events` spreads `page` next to `routine_spread`.
- **The projection.** `build_user_message_content` leads with the page:
  - str content: `"[Page: {line}]\n" + <today's result>`;
  - list content: `TextContent("[Page: {line}]")` prepended;
  - no page: byte-identical to today.

  The verified call sites are:
  - anthropic `_to_api_message` (~:731), which the plan providers inherit;
  - openai `_to_api_message` (~:298), which openrouter inherits;
  - ollama `_to_native_message` (~:575) and `_to_api_message` (~:748).

  Ollama's native list path joins text blocks with a space, so it reads
  `[Page: X] [from p]: text`. That is accepted and stable.
- **`TurnContext.page: dict | None = None`.**

### Evals
- **A new user-turn form**, a TOML table `{text = "...", page = {line =
  "...", descriptor = {...}?}}`, parsed in `evals/scenario.py` (~:601-620)
  as a `PageTurn(text, page)` dataclass with its own validation:
  - `line` is required;
  - `descriptor` is optional, and is checked with
    `page.validate_descriptor`.
- **The rest of the scenario code follows the new form.** The sites, from
  design review cycle 2:
  - `scenario.py`:
    - the `Turn` alias (~:154) and the `list[Turn]` annotations gain
      `PageTurn`;
    - `is_user_turn` (~:156; it has no callers) is true for it;
    - `Scenario.instantiate` (~:242) expands `text` and `line`;
    - the dict-turn parse (~:608-620) dispatches on `text`/`page` before
      `_step_turn`, and its error texts are reworded (check
      `tests/test_evals_scenario.py` and
      `test_evals_gleepglorp_proposals.py` for tests matching them; a text
      match there is not an assertion about behaviour, but report any edit
      to one);
    - the first-turn check (~:625) accepts a `PageTurn`;
  - `runner.py`:
    - `llm_calls` (~:105) counts `PageTurn`s;
    - the turn serialisation (~:266-273) records `page`;
  - `harness.py`:
    - `user=` (~:776-783) uses `turn.text`;
    - the page, and `TurnContext.page`, are passed only when set (~:804-805);
  - `TurnTrace` gains `page`;
  - `checks.py::conversation_messages` (~:122) sets `.page` on the
    `Message.user`.
- **No scenario uses it yet.** Leg 7 writes them and decides which carry a
  descriptor (Leg 5's `fill_form` gate needs one).

### Client
- **The page hook, `config.pageContext()`, returns a descriptor or `null`.**
  - The drawer profile supplies it, from `App.router.current()`/`parse()`,
    the agent tab, and the open editor's display name (`item_name`) when
    the route has an item.
  - The Chats profile has no hook, so its payloads have no `page` key.
- **`performSend` and `startSend`** add `payload.page` when the hook returns
  one.
- **The hold queue.**
  - Entries become `{text, page}`, with the page captured when the message
    is queued. Update every reader: the `hold-queue.js` chips use
    `.text`; so do `session-flow.js` (~:371-387, the restore after
    `start_failed`) and `socket.js` (~:338).
  - The push callers are `send.js` (~:128) and `sendText` (Continue, ~:165).
    Both capture the page.
  - `sendHeld` passes `held.page` to `performSend`.
  - A message restored to the composer after `start_failed` drops its page;
    it is re-captured at the next send.
- **The chip is a sibling of the bubble, never a `.ui-message`.** It is a
  new sub-factory, `App.ui.message.context(text)`, next to
  `App.ui.message.attribution`.
  - It returns a quiet line (`ui-message-context`, aligned with a user
    bubble), and the text is set with `textContent`.
  - The transcript inserts it before the bubble, the way `addMsg` places the
    attribution.
  - Add `ui-message-context` to the `message` row's owned classes in
    `docs/ui-control-inventory.md`, with the sub-factory in its option
    list. Add Chromium + WebKit contract tests in
    `tests/browser/test_ui_message_contract.py`, with the testid
    `message-context`.
  - `message_sel('user')` and its counts must not see it.
- **The transcript seam.** `addMsg` gains `opts.pageLine`, which inserts
  the chip before the bubble, and returns the bubble node. The attribution
  is appended after the bubble, as today.
- **Where the chip text comes from:**
  - **The sender's own bubble: one slot, not a FIFO.** The client sends one
    turn at a time and holds the rest, so at most one sent bubble waits for
    its chip.
    - `pendingPageBubble` is set by `performSend` and `startSend` when the
      payload has a page.
    - A `page_line` for the bound session consumes it and inserts the chip
      with `insertBefore`.
    - The slot is cleared on `done`, `cancelled`, `system`, `start_failed`,
      `clearLog`, a session switch, and a `page_line` for another session.
      So a refused turn (GleepGlorp not ready, or a malformed page) can
      never put its chip on a later bubble.
    - `page_line` gets an explicit branch in `turn-frames.js` `handle`,
      because unknown types fall through silently.
    - `startBubbleNodes` is snapshotted before the chip exists. That is
      harmless: one start never gets both `start_failed` and `page_line`.
  - other sockets get it from the `user` event's `page.line`;
  - a join or reload gets it from the UI events' `page.line`, through the
    shared `addUserEvent` (~:176-203), the same in both profiles.

  So a drawer conversation opened in Chats shows its chips with no hook.
  Routine and proposal events carry none.

### Docs
- `the_one/agents.md`: a "GleepGlorp page awareness (M36 F3 L4)" section
  covering:
  - the descriptor, the line and the sanitiser;
  - the projection and the call sites;
  - `page_line`;
  - the turns that carry no page;
  - `TurnContext.page`;
  - the `core.py` touch, beside sortie 10's.
- A short CLAUDE.md paragraph after "The drawer's chat (M36 F3 L3)".
- `SECURITY-MODEL.md`, one paragraph. The page line is operator-context data
  built from route ids. Names are sanitised and cannot open a bracket, a
  line or a breadcrumb level. Unsaved editor values are never sent.
- The guide is not touched; that is Leg 7.

## Acceptance Criteria
- [ ] **AC1. The core touch.** `git diff 3aa9ea94 -- the_one/agent/core.py`
  shows only the `page=None` parameter, the line that sets `.page`, and a
  docstring line. A unit test shows that `step(text, page={"line": "X"})`
  stores the page on the appended user message, and that `step(text)` leaves
  it `None`.
- [ ] **AC2. The projection.** Unit tests on `build_user_message_content`
  cover:
  - str content with a page;
  - a page plus a peer, in the order `[Page: …]\n[from p]: text`;
  - list content with a page;
  - no page, byte-identical to before.

  Four adapter tests (anthropic, openai, ollama native, ollama `/v1`) show
  that the request's user content for a two-turn history carries the page
  line on the turn that had it and not on the other, each for str and for
  list content.
- [ ] **AC3. The codec.**
  - A `Message` with a page round-trips.
  - No page, a non-dict, or a dict without a string `line` decodes to
    `None`.
  - `test_encode_emits_no_keys_when_all_optional_fields_default` stays green
    unedited.
  - `messages_to_ui_events` carries `page` on that user event only.
  - A stored page keeps its line after the item is renamed. The projection
    never calls the resolver.
- [ ] **AC4. `page.py`.** Unit tests cover:
  - every destination, Library group and Settings page (including
    `gleepglorp`);
  - an agent with and without a tab;
  - each create name;
  - a Library id resolved to the stored name (one per repository);
  - unknown ids and repository errors falling back to `item_name`, then to
    the segment;
  - refusal of unknown keys, unknown destinations (`chats` included),
    unknown sections, wrong types and over-long strings;
  - the sanitiser on `[`, `]`, `›`, newlines, control and bidi characters,
    and its caps;
  - the line cap;
  - the tables pinned equal to the client sources.
- [ ] **AC5. The server path.** App-level WebSocket tests show that:
  - a GleepGlorp `start_session` and `message` with a page store the page on
    `agent.messages[...]` and in the stored row;
  - `TurnContext.page` is set during the turn;
  - the other subscriber's `user` frame carries `page.line`;
  - the sender gets exactly one `page_line` frame with the same line, and
    no `user` echo;
  - the title holds no `[Page:`;
  - a page with a shape fault is refused with the exact text for a
    GleepGlorp agent, for an ordinary agent, and on `/reset`, and creates
    no session;
  - an empty message with a malformed page is still silently empty;
  - a page with a value fault (an unknown section) delivers the message
    with no page and logs one warning;
  - at the existing/deliver site, the page follows the restored session's
    agent;
  - a valid page on an ordinary agent stores none, sends no `page_line`, and
    calls `step` without the keyword;
  - routine and proposal turns have `TurnContext.page` `None`;
  - every existing test that defines a `step` double passes unedited.
- [ ] **AC6. Chats is unchanged.** A frame-capture browser test shows that a
  Chats `message` and `start_session` have no `page` key. The chats,
  chats-transcript and chats-widgets lanes pass with their assertions
  unedited.
- [ ] **AC7. The drawer sends the page.** Browser tests in the drawer-chat
  file (scripted mock) show:
  - on Library › New MCP server, the drawer's first `start_session` carries
    `{destination: 'library', section: 'mcp', create: true}`;
  - on an agent's Tools tab, the next `message` carries
    `{destination: 'agents', item, tab: 'tools'}`;
  - a message queued on page A and sent after navigating to page B carries
    page A.
- [ ] **AC8. The chip.**
  - In the drawer, the operator's bubble gains the server's line ("Library
    › MCP servers › New MCP server") once `page_line` arrives.
  - After a reload, and when the conversation is opened in Chats, the chip
    shows the same line.
  - A Chats-only conversation shows no chip.
  - A refused turn leaves no chip on the next, successful message. Test it
    with GleepGlorp not ready, then ready, and with a malformed page
    injected through the socket.
  - Every route the drawer can be on gives a descriptor the server accepts
    with no value fault: one browser pass over the Agents, Library and
    Settings routes and their create routes.
  - `messages(page, 'user')` counts are unchanged by chips.
  - The `App.ui.message.context` contract tests pass in both engines.
- [ ] **AC9. Evals.** The offline evals tests pass, plus new ones:
  - a `PageTurn` parses (with and without a descriptor) and is refused when
    it has no `line` or a bad descriptor;
  - it reaches `agent.step(page=)` and `TurnContext.page`;
  - `conversation_messages` carries the page;
  - a str turn is unchanged.
- [ ] **AC10. Falsified.** Each of these new tests is shown to fail with
  its fix removed (by editing) and to pass with it restored:
  - AC1 (remove the set line);
  - AC2 str (drop the page branch);
  - AC2 list (drop the prepended block);
  - AC5's ordinary-agent drop (remove the GleepGlorp check);
  - AC7's queued page (send the current page instead);
  - AC8's sender chip (ignore `page_line`).

## Verification Steps
- `THE_ONE_TEST_NETNS=1 make test-unit`, including `test_llm_base.py`,
  `test_db_codec.py` and the files that define `step` doubles.
- Lanes one at a time, with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`:
  `chats`, `chats-transcript`, `chats-widgets`, `contracts-chat` and
  `shared`.
- Then the full `--parallel 3` run, with `TEST_TIMEOUT=3600`. Report the
  start load; it is not a budget reading unless the host is quiet.
- The static guards, `ruff check` and `ruff format --check`.
- Paste `git diff 3aa9ea94 -- the_one/agent/core.py` into the flight-log
  entry.

## Implementation Guidance
1. **`page.py`.** The pure functions, the label tables, `_app_routes.py`'s
   label readers and the pin, and the unit tests. Then `resolve_page`.
2. **The message and the projection.** `Message.page`, the codec, the UI
   events and the projection, with the adapter tests. Then the `core.py`
   keyword and `TurnContext.page`.
3. **The WebSocket path.** `ValidatedPayload.page` (with a default), the
   validator, `_page_for`, `_spawn_web_message` (with `turn_info` only when
   a page is set), `_process_and_broadcast` (with the keyword only when a
   page is set), and `page_line`.
4. **Evals.** `PageTurn`, the harness, `TurnTrace` and `checks.py`, with
   the offline tests.
5. **The client.** The hook, the payloads, the hold-queue entries and their
   readers, `App.ui.message.context`, the transcript chip (the
   `page_line` FIFO plus `addUserEvent`).
6. **Browser tests, then the docs.**
- Keep the `app.py` additions small. The resolve lives in `page.py`.
- An assertion edit in an existing test is a `[BLOCKED]`.
- Edit source and test files only with the Edit/Write tools.

## Edge Cases
- **A deleted item.** The name falls back to `item_name`, then to the
  segment, and nothing is refused.
- **A rename.** The stored line keeps the old name, by design.
- **A reconnect during `starting`** re-sends the same frame, so the page is
  unchanged.
- **The drawer on Settings › GleepGlorp:** "Settings › GleepGlorp".
- **A create agent with no tab:** "Agents › New Agent".
- **A hostile `item_name`** (brackets, `›`, newlines or over-long) is
  sanitised and capped.
- **A drawer socket that reconnects between the send and `page_line`:** the
  bubble keeps no chip until a re-join redraws it from the history.
  Accepted.

## Files Affected
- **New:** `the_one/gleepglorp/page.py`, `tests/test_gleepglorp_page.py`.
- **Edited, server and evals:**
  - `the_one/agent/core.py` (the keyword only);
  - `the_one/agent/_context.py`;
  - `the_one/llm/base.py`;
  - `the_one/db/codec.py`;
  - `the_one/interfaces/web/app.py`;
  - `evals/scenario.py`, `evals/harness.py`, `evals/checks.py`;
  - `tests/_app_routes.py`.
- **Unit tests** beside the existing llm-base, codec, adapter, WebSocket and
  evals tests.
- **Client:**
  - `js/ui/message.js` and its CSS;
  - `js/areas/chat/send.js`, `session-flow.js`, `hold-queue.js`,
    `socket.js`, `transcript.js` (and `turn-frames.js` if `page_line` is
    routed there);
  - `js/gleepglorp-drawer/chat.js`.
- **Browser tests:** `tests/browser/test_ui_message*`,
  `test_flow_gleepglorp_drawer_chat.py`, and a Chats frame-capture test in
  the chats lane.
- **Docs:** `docs/ui-control-inventory.md`, `the_one/agents.md`,
  `CLAUDE.md`, `SECURITY-MODEL.md`.

## Citation Audit
Checked by the FD on 2026-11-20 against the working tree (batch A
uncommitted on `3aa9ea94`). The design review re-verified every row and the
adapter call sites.

| Citation | Status |
|---|---|
| `agent/core.py::Agent.step` (~:226) — `(user_input, on_chunk, on_usage)`, appends `Message.user(user_input)`; untouched vs `3aa9ea94` | verified |
| `llm/base.py::Message` (:166), `Message.user` (~:305), `build_user_message_content` (~:443) | verified |
| anthropic `_to_api_message` (~:731), openai (~:298), ollama `_to_native_message` (~:575) and `_to_api_message` (~:748) — all call the helper; plan, plan-token and openrouter inherit | verified (review) |
| `agent/_context.py::TurnContext` (:83) | verified |
| `app.py` `ValidatedPayload` (~:1125), `_validate_message_payload` (:1144), `_spawn_web_message` (~:1366), the `extra = {}` precedent (~:1342) | verified |
| `app.py::_process_and_broadcast` (:2633), `TurnContext(...)` (~:2798), `agent.step(...)` (~:2822) | verified |
| `app.py` spawn sites ~:3864, ~:3914, ~:4023; `/reset` ~:4003 | verified (review) |
| `db/codec.py` `proposal_*` encode (~:212) / decode (~:278), `messages_to_ui_events` spread (~:405-415) | verified |
| `db/repositories.py` async `get` on the agent, MCP, connector, secret, KB and provider repositories (~:637, 1332, 1498, 2187, 3607) | verified (review) |
| `static/js/areas/chat/send.js` `performSend` (~:47), `sendHeld` (~:72), push (~:128, ~:165) | verified |
| `session-flow.js` `startSend` (~:331), start_failed restore (~:371-387); `socket.js` (~:338); `transcript.js` `addMsg` (~:151-163), `addUserEvent` (~:176-203) | verified (review) |
| `static/js/ui/message.js` — one `div.ui-message`; chips inside (~:97-107); `attribution` sub-factory | verified (review) |
| `router.js` `LIBRARY_LABELS` (~:481), `describeRoute` (~:567); `settings-pages.js` has `gleepglorp` | verified (review) |
| editor create titles: `secret-editor.js` ~:230, `provider-editor.js` ~:107, `mcp-server-editor.js` ~:131, `knowledge-create.js` ~:47, `connector-editor.js` ~:318 ("New Connector"), `agent-editor.js` ~:234 ("New Agent"; `agents-list.js` holds button labels, not the title) | verified (review cycle 2) |
| `turn-frames.js` `handle` (~:73-175) — an if/else chain; unknown types fall through; `transcript.js` `addMsg` returns nothing (~:151-167) | verified (review cycle 2) |
| `evals/runner.py` `llm_calls` (~:105), turn serialisation (~:266-273) | verified (review cycle 2) |
| `evals/scenario.py` `Turn` (~:154), `expand` (~:240), parse (~:601-620); `harness.py` (~:799-802); `checks.py` (~:122) | verified (review) |
