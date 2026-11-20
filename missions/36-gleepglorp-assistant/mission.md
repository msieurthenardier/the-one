# Mission: GleepGlorp, the In-App Assistant

**Status**: active

## Outcome

An operator can set up and tune the app by asking for what they want, in plain
language, instead of learning every form first. A built-in assistant named
GleepGlorp ships with the app and knows how the app works. It can be reached in
two ways, and in both of them nothing changes until the operator clicks.

- **A help button in the corner of every page.** It opens a small chat beside
  whatever the operator is looking at. GleepGlorp knows which page and item are
  open. It answers "what does this do?" and, given a request like "here's the
  link to the MCP server I want, set it up", fills in the open form. The
  operator reviews the filled form and clicks Save, exactly as if they had typed
  it.
- **GleepGlorp in Chats.** GleepGlorp is the built-in agent listed first in the
  agent picker. In a normal chat the operator can ask for bigger things: "make
  me an agent that does X, Y and Z", "add my GitHub MCP server to the ABC agent".
  GleepGlorp answers with a proposal card that shows exactly what will change,
  and the change happens only when the operator clicks Approve.

GleepGlorp sticks to supporting the app. It declines anything else and points
the operator to their own agents. It never handles secrets. When a step needs
one, it says where to enter it and links to that page, for example "Sign in to
the Claude Max provider on the [Model providers] page first." The operator
chooses its model and how long its chats are kept, and can turn it off, turn
off its web access, and turn off its memory. Nothing else about it is
configurable: its prompt ships with the app,
and it has no rules or operator instructions that could steer it toward harm.

GleepGlorp replaces the old "Default agent", which is removed.

## Context

The app now does a lot: agents with prompts, tools, rules, notes, routines and
secrets; MCP servers with headers, sign-in and per-agent credentials; model
providers with three Claude sign-in variants; knowledge bases; Discord and
Telegram connectors; app settings. Each part has a careful editor, but a new
operator has to learn all of them, and even an experienced one spends time
turning an MCP server's README into form fields. An assistant that knows the
app and can do the typing, while the operator keeps the final say, lowers that
cost for everyone. It also suits a desktop app sold as "your personal AI
agent": the product's own agent should be able to help set up the product.

Results will differ by model. Small local models will do worse than Haiku. The
prompt evals (Mission 30) are how we find out and improve: GleepGlorp gets its
own scenario set and baseline, Haiku must meet a pass bar, and small models are
measured and reported but best effort.

Facts about the codebase that shape the design. They come from a research survey
at `9fea53cd`; each flight design re-verifies them.

- **Every agent is a row in the `agents` table, except `default`.**
  `AgentFactory._load_config` returns the stored row, falls back to
  `_default_config()` (no provider) for `"default"`, and raises
  `AgentNotFoundError` for anything else (`agent/factory.py` ~:743-752); the
  missing provider fails later, at provider resolution. `list_agents` adds
  `"default"` (~:738). GleepGlorp needs its own build path, a reserved-name
  branch that assembles its config in memory from its settings and the shipped
  prompt, never a row the operator can edit. Its settings fit `app_metadata`
  as JSON, as the time-zone setting does.
- **A chat can name an agent that is not a row.** `chat_sessions.agent_name`
  has had no foreign key to `agents` since v5 (`db/schema.py` ~:534-545), so
  GleepGlorp chats need no schema change to be stored.
- **Chat retention is per agent today.** `AgentConfig.chat_history_retention_days`
  (default 30, 1-365, `agent/config.py:143`, an `agents` column since v30)
  drives the daily purge in `the_one/retention.py::run_purge_sweep`, which
  iterates `agent_store.list_retention_windows()` over the `agents` table only
  (and also purges routine runs and proposals per agent). GleepGlorp is not a
  row, so its retention setting and an extra pass in the sweep are new.
- **The Default agent is already vestigial.** Since the agent picker (M25 F4),
  a new chat must name an agent, and `start_session` refuses `default`
  (`interfaces/web/app.py:3608`). Connectors and routines always name a real
  agent. The only "Default agent" chats are old ones stored with
  `agent_name = NULL` (`_create_session` stores `default` as NULL,
  `app.py:1765`). "Default agent" still appears as a label in `chats-list.js`,
  `chat-pane.js`, `agent-drawer.js` and `jump-to.js`, and `default` is still a
  legal agent name (naming rule; `the_one/agents.md` "Naming rule").
  **Operator decision: delete the Default agent outright.** The operator is the
  only user, so no data needs to be kept.
- **Native tool providers are the established way to give an agent its own
  tools.** Notes and routines register tools through providers passed to
  `AgentFactory` (`RoutineToolProvider`, the notes provider), outside the
  operator's tool filters. This needs no loopback MCP source or credential. The
  M21 self-configuration surface is a loopback MCP source with a confined
  credential, and is the heavier precedent.
- **Validation lives in the route handlers, not in reusable functions.**
  Examples are the naming rule and its 409, the `__MASKED__` preserve sentinel,
  `_merge_preserved_mcp_credentials`, `_normalize_surface_fields` and the
  reserved `self-configuration` name. Applying a GleepGlorp proposal must go
  through the same validation the forms use. The Architect review recommends
  extracting per-entity service functions (as routines did with
  `routines/service.py`) rather than calling routes in-process, which would
  drag in the credential gate and the HTTP 422 shape.
- **The agent write API has traps.** `PUT /api/agents/{name}` replaces almost
  the whole body (an omitted `system_prompt` becomes `""`). Saves are
  last-writer-wins with no version check, and M21's Known Issues already noted
  that a second writer would need one. GleepGlorp is that second writer.
- **There are two approval queues to learn from, and neither fits as is.**
  `agent_revisions` (M21) and `agent_routine_proposals` (M33) both do
  propose → stale check → approve (with override) or dismiss. Both are keyed to
  one agent and one field or routine. GleepGlorp needs proposals over any
  entity and operation.
- **The chat area runs as a single instance.** `areas/chat.js` holds one state,
  `chat/socket.js` one socket, and the session flow assumes both. The library
  controls the overlay would use (`App.ui.composer`, `message`, `turnWork`,
  `drawer`, `modal`) are reusable factories, but the chat orchestration is not.
  The overlay can be open beside a chat in Chats (operator decision), so the
  chat must be able to run twice in one window. This refactor is the riskiest
  UI work in the mission.
- **Every chat appears in the Chats list.** `list_sessions`,
  `GET /api/chat/sessions` and `sessions_changed` list every session row. Only
  connector chats carry a marker (`platform`).
- **Nothing in the frontend fills a form on someone else's behalf.** Editors
  are "mount once, patch through handles" with their own dirty state, and
  `App.nav` guards leaving a dirty editor. The server pushes no change events
  for agents, MCP servers or providers (only sessions are pushed), so a change
  approved in chat would leave an open editor stale. A server-side tool cannot
  reach the DOM: the channel to the browser is the chat's WebSocket (a frame
  to the session's subscribers), and each editor needs its own seam to take
  filled values through its handles.
- **Secrets have firm contracts.** `__MASKED__` is a preserve sentinel on
  providers, MCP secrets, connectors and tool configs. Library secret values
  are write-only. Agents use `{{secret:key}}` placeholders that are resolved
  at run time and masked in results. A key typed into chat would be stored in
  the transcript and sent to the model provider, outside the encrypted
  storage.
- **The eval harness can carry this.** Scenario sets are TOML with their own
  directory and baseline (routines, visuals and widgets already do this). The
  harness builds agents from a stored row today, so GleepGlorp needs a harness
  path, and the checks need new state checks (for example "a proposal was made
  with these fields" or "no secret appears in the reply"). Form filling can be
  scored only at the level of what GleepGlorp sends to the browser, not what
  the form shows; browser and behavior tests cover the rest.
- **Web tools exist.** `web_search` and `web_fetch` are built-in tools
  (`the_one/tools/web.py`). Search depends on the operator's search backend
  settings.

## Success Criteria

- [ ] **GleepGlorp is ready once its model is chosen.**
  - The operator picks a model provider and model for GleepGlorp in Settings.
  - Until both are chosen, the corner button and a GleepGlorp chat show setup
    guidance with a link to that setting, and they work once a model is chosen.
  - Its other settings are an on/off switch (off hides the corner button and
    removes GleepGlorp from the agent picker), a web access switch, a memory
    switch and chat retention (default 30 days, the same range as an agent's).
    Nothing else about it can be configured.
  - The daily chat-history purge removes GleepGlorp chats older than that
    retention, as it does for every agent.
- [ ] **Help is one click away on every page.**
  - The corner button opens GleepGlorp beside the current page in every
    destination, in the browser and in the desktop app.
  - GleepGlorp knows which page and item are open, and correctly answers
    "what does this do?" about them.
  - The overlay can be open at the same time as a chat with another agent in
    Chats, and each keeps its own conversation.
  - The overlay conversation continues across page changes and can be reopened
    later from Chats.
  - *(Behavior-test-backed: real overlay, real model, real page.)*
- [ ] **GleepGlorp fills the form; the operator saves it.**
  - Asked in the overlay to configure something, GleepGlorp opens the matching
    editor and fills its fields in place.
  - The editor behaves exactly as if the operator had typed: its validation
    messages, unsaved-changes caption and leave guard all apply.
  - Nothing is stored until the operator clicks Save, and GleepGlorp says the
    form is filled, not saved.
  - This works for every editor in scope: agents (prompt, description, model,
    tools, rules, MCP servers, knowledge bases), MCP servers, model providers,
    knowledge bases, connectors, routines, Library secrets (name, description
    and allowed tools, never values) and app settings.
  - *(Behavior-test-backed: an MCP server set up from a pasted link.)*
- [ ] **GleepGlorp proposes; the operator approves.**
  - Asked in a chat to create or change something, GleepGlorp answers with a
    proposal that shows exactly what will change.
  - A request with several steps becomes one proposal per step. Each later
    step is proposed after the earlier one is approved, using its result.
  - Approve applies it through the same validation the forms use, changing only
    the fields the proposal names. An error is shown on the proposal. Dismiss
    changes nothing.
  - A proposal whose target changed after it was made is refused as stale and
    is not applied blindly.
  - An editor that is open on the changed item shows the new values without a
    reload, and an unsaved edit there is never overwritten silently.
  - *(Behavior-test-backed: create an agent, and attach an existing MCP server
    to an agent, both by approval.)*
- [ ] **Nothing changes without the operator's click.**
  - No GleepGlorp turn can change the app's configuration (agents, MCP servers,
    providers, knowledge bases, connectors, routines, secrets, settings, or
    GleepGlorp's own settings) by any route. This holds by construction: each
    of its tools reads, fills a form on screen, records a proposal or (with
    memory on) keeps its own notes. A test checks its whole registered tool set
    against that allowlist.
  - Its own notes are the one write without a click. They are flagged "Check
    this" when written after untrusted content, as every agent's notes are.
  - It cannot propose deleting anything.
  - There is no setting that lets it apply changes by itself.
- [ ] **Secrets never pass through GleepGlorp.**
  - Nothing it can read returns a secret value; every read shows masks.
  - It never puts a secret value into a form or a proposal.
  - When a step needs a secret or a sign-in, it says so and links to the exact
    page where the operator enters it.
- [ ] **GleepGlorp sticks to the app.**
  - It declines requests that are not about the app and points the operator to
    their own agents.
  - Its tools are only: reading the app's configuration and status, filling
    forms, proposing changes, web search and fetch (when allowed) and notes
    (when allowed). It has no shell, code, file or other tools.
  - It cannot be bound to a connector or own a routine.
  - A proposal or form fill made after it read untrusted content (a web page,
    an MCP server's tool descriptions) is marked "Check this".
- [ ] **The Default agent is gone.**
  - "Default agent" no longer appears anywhere in the app.
  - At upgrade, the stored `default` agent (if any) is deleted, and so is
    every chat that belonged to it or has no agent. Nothing is kept (operator
    decision).
  - "GleepGlorp" and "default" (any letter case) are refused as names for new
    agents with the naming rule's plain error. A stored agent already using
    either name is renamed once at startup, as the naming rule's repair does.
  - GleepGlorp's own chats are marked as GleepGlorp chats from the start.
- [ ] **Quality is measured on every default eval model.**
  - GleepGlorp has its own eval scenario set and baseline, covering questions
    about the app, form filling, proposals, secret handoffs and declining
    off-topic requests.
  - Haiku meets the pass bar agreed when Flight 1 records the baseline (later
    flights extend the set and re-baseline it).
  - Form filling is scored on what GleepGlorp sends to the browser. Browser and
    behavior tests prove what the form then shows.
  - The small default model `qwen3-4b` is measured and reported, and the model
    setting notes that small models may struggle. *(Amended 2026-11-18,
    operator decision during Flight 1 Leg 9: `lfm3` is not evaluated for
    GleepGlorp; it is too small to follow the link and tool format, and its
    numbers would not move with prompt wording.)*
  - The prompt that makes GleepGlorp does not change the prompt or token cost
    of any other agent.

## Stakeholders

- **The operator** (currently the only user). They want to set up MCP servers,
  agents and providers faster, ask "what does this do?" while they work, and
  stay in control of every change.
- **New installs.** Someone opening the app for the first time is the reader
  who gains most from a guide that knows the app. The one thing GleepGlorp
  cannot help with is choosing its own model, so that guidance must stand on
  its own.
- **Small local models.** Operators running local models should get a useful
  GleepGlorp where possible. The prompt and tool set stay compact enough to
  give them a chance, and their limits are measured and stated, not hidden.

## Constraints

- **Every change takes an operator click.** GleepGlorp's tools only read, fill
  forms on screen, create proposals or keep its own notes. Applying a proposal
  is an operator action through the app's own validation, as a field-level
  change (never a whole-body replace). GleepGlorp cannot change its own
  settings, enablement or prompt, and no setting relaxes this.
- **Create and change only.** GleepGlorp never proposes or fills a delete.
  Deleting stays with the operator in the editors (a possible later mission).
- **No secret material, ever.** No GleepGlorp read path returns a secret value
  (including the `__MASKED__` contract and write-only Library secret values).
  It never writes a secret into a form or proposal. Credentials, API keys and
  sign-ins are always left to the operator on the right page.
- **App support only, minimal configuration.** The prompt ships with the app.
  The operator configures only the model provider and model, on/off, web access,
  memory (notes) and chat retention. There are no rules, no operator instructions and no
  per-tool overrides. GleepGlorp is available only in the app: never on a
  connector, never as a routine owner.
- **Prompt injection is expected, not assumed away.** Web pages, MCP server
  READMEs and tool descriptions, knowledge-base text and notes are
  attacker-influenced. The approval click is the main control, and a proposal
  or form fill that follows untrusted content is flagged using the existing taint tracking
  (`the_one/agent/taint.py`). Read access is limited to configuration and
  status: never other agents' chats, the operator's files or app logs.
- **Other agents are unaffected.** GleepGlorp's prompt is separate from the
  platform prompt other agents get. Their prompt text and token cost do not
  change, so the existing `notes-*` baselines and size gates stay valid.
- **The shipped prompt is platform prompt text.** It lands with an eval run
  against GleepGlorp's own baseline (CLAUDE.md "Prompt evals"). Evals stay out
  of CI and the test gate.
- **Existing project rules apply.** New UI is built from `App.ui` controls
  (catalogue rows, Chromium + WebKit contract tests, no HTML-string sinks).
  Navigation goes through `App.router` and `App.nav`. A schema change is a new
  versioned step. New name-setting routes call `check_name`. Every route sits
  behind the credential gate. The overlay works in all three desktop webviews
  and at the 1024px minimum width.

## Environment Requirements

- Host-native dev environment with the repo `.venv`
  (`pip install -e ".[all-llms,dev]"`).
- Playwright Chromium and WebKit (`scripts/setup-webkit-userland.sh`), with
  `THE_ONE_REQUIRE_WEBKIT=1` for contract lanes and `THE_ONE_TEST_NETNS=1` for
  browser runs on this WSL host.
- Prompt evals: `pip install -e ".[evals]"`, the plan token in
  `~/.config/the-one-evals/plan-token`, and local Ollama with the default
  small models (`qwen3-4b`, `lfm3`).
- Behavior tests against a dedicated dev instance (port and data directory
  away from 8484 and the default data dir), with a real model provider for the
  overlay and proposal round trips.
- The real desktop engines for the overlay check: `scripts/webkitgtk_probe.py`
  (WebKitGTK), `scripts/windows_test_copy.py` (WebView2) and a hosted macOS run
  (WKWebView).

## Planning Decisions

Taken with the operator on 2026-11-18, after the Architect review:

- **One change shape.** A form fill is a proposal shown as a pre-filled editor
  instead of a card: one schema, one validator, one taint path, one eval check.
  Flight 2 defines it; Flight 3 uses it.
- **No deletes.** Create and change only.
- **One proposal per step** for requests with several steps, each checked
  against current data when approved. No bundles.
- **The overlay runs beside Chats.** It is a second, independent chat, so the
  chat code must run twice in one window.
- **Every editor in scope gets form filling.** Flight 3 may split at planning
  into the overlay first, then filling across the editors.
- **Where GleepGlorp's knowledge comes from.** Five sources, plus its notes:
  1. **The shipped prompt:** identity, limits and a short map of the app,
     compact for small models.
  2. **The app guide:** short topic files shipped in the package (what an MCP
     server is, stdio vs HTTP, sign-in, what rules, notes and routines are
     for, ...), looked up by topic through a read tool rather than carried in
     the prompt.
  3. **Field definitions** for every form (fields, allowed values, required,
     secret), generated from the same schema as the change shape, never
     hand-written, so they cannot drift from the real forms.
  4. **Live reads** of the current configuration and status, secrets masked.
  5. **The web** (when allowed), treated as untrusted.

  It does not rely on the model's training about the app, on the developer
  docs (`agents.md`, `CLAUDE.md`), or on the knowledge-base feature, which
  would add an embedding model and fuzzier, harder-to-evaluate lookups.
- **The guide stays current.** A test fails when the guide names a page,
  editor or field that no longer exists. Project convention from this mission
  on: a change to a page or form updates the guide in the same flight, as
  prompt text already lands with an eval run.
- **The guide is written for people too.** It is plain help text a person can
  read, so the same topics can later be shown as in-app Help pages. Showing
  them to people is a follow-on, not in this mission's criteria.
- **A key pasted into chat** is steered to the right page from Flight 1. A
  warning before sending is optional extra work.
- **No search backend means fetch only.** `web_search` is not offered and
  GleepGlorp says so.
- **The shipped prompt is shown read-only in Settings › Prompts.**
- **GleepGlorp's settings live in app metadata**, not an agents row.

Taken with the operator on 2026-11-19, at Flight 2 planning:

- **Proposals are split by kind of item.**
  - Flight 2 covers agents, their rules and their routines.
  - The other kinds (MCP servers, providers, knowledge bases, connectors,
    Library secrets' metadata and app settings) become proposable with their
    form filling in Flight 3 or a later flight.
- **Approve starts GleepGlorp's next turn**, so a request with several steps
  continues one approved step at a time. Dismiss does not.
- **qwen3-4b is measured only.** Its results, safety checks included, are
  reported every round and never block a prompt change. The Settings hint that
  small models may struggle stays. This settles the Flight 1 debrief's
  question.
- **The eval method is adopted** from the Flight 1 lessons and written into
  `evals/README.md` in Flight 2. It covers:
  - offline tests for every check;
  - a fairness review before quota;
  - safety checks versus ranking checks;
  - an n=5 parallel screen with a control;
  - shortening at the ceiling;
  - one n=20 confirmation;
  - operator sign-off before quota or a re-pin;
  - a re-baseline when the scenario set changes.

## Open Questions

- **The overlay's chat instance.** How does the chat area become something
  that can run twice (a `create(ctx)` refactor of the session flow and socket,
  or a lighter second client)? Decided in Flight 3's design.
- **The same chat in two places.** If an overlay conversation is also opened
  in Chats in the same window, which one is live? Decided in Flight 3.
- **The stale-check record.** Does a proposal store a snapshot of the fields it
  changes, or a version for the whole row? Decided in Flight 2.
- **The Haiku pass bar.** Set when Flight 1 records the baseline.
- **A tool-count budget for small models.** How many tools GleepGlorp can carry
  before small models fail to choose. Measured in Flight 1.

## Known Issues

*(none yet)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [x] **Flight 1: GleepGlorp exists and can answer.** Remove the Default agent
  (the schema step that deletes it and its chats, the reserved names, the
  labels). Add GleepGlorp's identity, its settings (model, on/off, web, memory,
  retention) with the setup gate and purge coverage, its own build path and
  shipped prompt (shown in Settings › Prompts), the GleepGlorp chat marker,
  read-only tools for configuration and status (masked), the app guide, notes
  and web access, and its place first in the agent picker. Record the eval
  scenario set and baseline for questions, secret handoffs and declines.
  Outcome: the operator can ask GleepGlorp about the app in Chats.
- [x] **Flight 2: Proposals and approval.** Define the one change shape. Extract
  the forms' validation into service functions so proposals use it. Build the
  proposal store with stale checks and taint flags, and add the Approve/Dismiss
  card in chat with field-level apply. Push changes to open editors, with no
  silent overwrite. Extend the evals. Outcome: "create me an agent that does X"
  and "attach my MCP server to ABC" work by approval. This flight carries the
  write-boundary risk. *(Scoped 2026-11-19 to agents, their rules and their
  routines; the other kinds move to Flight 3.)*
- [ ] **Flight 3: The corner overlay and form filling.** Make the chat able to
  run twice and put the second one in a floating overlay on every page, with
  page and item awareness. Add form filling across every editor in scope
  through the change shape, with secret handoff links and the desktop-webview
  checks. Extend the evals. Outcome: the help button works everywhere and fills
  the open form. *(2026-11-19: proposals for the kinds Flight 2 left out arrive
  with their form filling, through Flight 2's change shape and services.)* This flight carries the most unknowns and may split at
  planning (the overlay, then filling across the editors).
- [ ] **Flight 4 *(optional)*: Alignment.** A hands-on session to tune
  GleepGlorp's prompt, tone and overlay feel with the operator, against the
  evals and the real app.
