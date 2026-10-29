# Mission: Routines

**Status**: active

## Outcome

An agent can act on a schedule, not only when someone writes to it. A
**routine** is a named, per-agent scheduled task: when it is due, the agent runs
a turn with the routine's prompt in a chosen chat, with nobody watching, and
the reply lands where the operator will read it. If that chat is a connector
chat, the reply is sent out to its channel.

- The operator sets routines up on the agent: "every weekday at 9 AM, check my
  schedule and send it to me on Discord", "every morning, search for a used car
  that matches what I want".
- The agent can schedule its own routines, when the operator allows it: "I'm
  waiting on that build, so I'll check back in two hours". The operator governs
  this from the Self-configuration tab, the same way as the agent's existing
  edits to its own prompt, and each routine can require approval.

Routines belong to one agent. They are configured on the agent, not in the
Library, and they are visible from any chat with that agent. A routine that
runs does not announce itself. It runs, and the result is in the chat.

## Context

Today every agent turn starts with a person: a message typed in the app or a
message in a connector channel. Missions 21 and 27 gave agents controlled ways
to change themselves (self-configuration, notes). Routines are the first time an
agent acts without being prompted, and the first time an agent can arrange for
itself to act later. That makes routines as much a security feature as a
convenience one.

Facts about the codebase that shape the design (verified at `c2366221`; the
branch's working tree moves line numbers, so the flight designs re-verify them):

- **A turn can already run with no socket attached.**
  - A web turn goes `_spawn_web_message` → `_spawn_message_processing` →
    `_locked_message_processing`, which takes the per-session lock that
    connectors share (`the_one/sessions/_locks.py:23`), then
    `_process_and_broadcast` (`the_one/interfaces/web/app.py:1101`, `:2184`).
  - The in-memory `Session` holds no socket, and broadcasting to a chat nobody
    has open does nothing (`_send_to_session`, `app.py:1930`).
  - `/api/chat` already runs a turn with no socket, but it does not take the
    session lock.
  - Anyone who has the chat open sees a routine turn stream live.
  - Only the connector path sends `session_updated` to make an open chat
    re-join after a turn it did not start (`the_one/connectors/inbound.py:536`).
  - A headless web turn sends no `session_updated`.
- **Replying through a connector is not reachable from the web turn path.**
  - `_process_and_broadcast` marks every message in a connector chat as
    operator-only and never delivers (`app.py:2549-2556`).
  - Delivery lives in the connector pipeline: `_auto_deliver_reply`
    (`inbound.py:285`), which takes an inbound envelope.
  - A stored chat can produce its own send target (`keying_to_target`,
    `the_one/connectors/base.py:70`).
  - A routine run in a connector chat needs a run path that delivers the
    reply and clears its operator-only marking. Today that logic is welded to
    an incoming message.
- **Messages carry no record of where they came from.**
  - `Message` has `visibility` (operator-only or not) and peer fields on user
    messages (`the_one/llm/base.py:151-230`).
  - The live event's `source` is never stored.
  - A routine-origin marker is new: an optional field, written only when set
    (the `db/codec.py` pattern).
- **There is no scheduler.**
  - The purge loop and the catalog refresh are due-based loops: they catch up
    at startup, then sleep and check again, and they store their last run in
    `app_metadata` (`app.py:1416`, `:1464`).
  - `the_one/time_zones.py` gives the operator's effective zone
    (`load_effective_zone`) but computes no next occurrence.
  - "9 AM daily" must follow the operator zone across daylight-saving changes.
- **The self-configuration tools cannot see the conversation.**
  - The four tools are an MCP server on a loopback `streamable-http` URL
    (`the_one/self_configuration/surface.py`), and they find the agent from the
    credential on the request.
  - The notes tools are native tools. They work out whether to flag a write
    by scanning the bound agent's messages (`compute_taint`,
    `the_one/notes/tools.py:60`), using turn context variables that do not
    cross into a separate HTTP request.
  - So agent routine tools that flag writes made after untrusted content
    cannot simply be four more tools on the existing surface. They must reach
    the conversation the way the notes tools do, or the conversation's state
    must be carried to them.
  - Recording the agent's routine changes also needs its own record:
    `agent_revisions.field` is CHECK-limited to description and system prompt
    (`the_one/db/schema.py:2664-2686`).
- **The Self-configuration tab is one item today.** The tab is assembled from
  section modules (`static/js/areas/studio/self-configuration-tab.js`):
  - one enable switch and one approval switch (`selfConfigStatus`);
  - pending revisions, history and external sections.

  Enabling attaches the loopback source to the agent. The approval flag is the
  operator-owned `self_revision_requires_approval` (`agent/config.py:143`).
- **Agent-keyed tables cascade by foreign key.**
  - `agent_rules`, `agent_notes` and `agent_revisions` use
    `REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE`.
  - A rename also fixes `chat_sessions` and the connector bindings by hand
    (`repositories.py:380`).
  - Schema is at v44.
- **Chat history purge deletes by age.** Per agent, sessions whose `updated_at`
  is older than the retention window (default 30 days) are deleted
  (`the_one/retention.py:48`), with no pin. A routine's target chat can vanish
  under it.

## Success Criteria

- [ ] **The operator manages an agent's routines.** On a Routines tab in the
      agent editor, the operator can create, edit, turn on or off, and delete
      named routines. Each routine has:
      - a prompt;
      - a schedule: once, at a time or after a delay, or a calendar
        recurrence (every N minutes, hours, days, weeks on chosen days,
        months or years, ending never, on a date or after N occurrences;
        Flight 3, replacing the original five kinds: daily, weekdays,
        weekly, every N hours, once);
      - a target: an existing chat of that agent, a new chat on every run, or
        the routine's own chat, created on its first run and reused after.

      Choosing an existing chat is a real picker over the agent's chats, web
      and connector, not a pasted id. The tab shows each routine's next run
      and its run history.
- [ ] **Routines run on time, unattended.**
  - A routine runs when it is due, in the operator's time zone, including across
    daylight-saving changes, whether or not any chat is open.
  - A one-off routine runs once and is then done.
  - Routines survive restarts.
  - Anyone who has the target chat open sees the run as it happens.
- [ ] **The reply lands in the target.**
  - In a web chat, the routine's message and the agent's reply are in the chat.
  - In a connector chat, the reply is sent to that chat's channel.
  - *(Behavior-test-backed: a routine run delivered through a connector.)*
- [ ] **A routine's message says it came from the routine.**
  - The transcript marks the run's message as from the routine, by name, never
    as typed by the operator.
  - The chat agent panel shows when the open chat was activated by a routine,
    and lists the agent's routines by name.
- [ ] **Unattended runs are honest.** Run history records each run's outcome,
      with a readable reason when it fails or skips:
  - **Missed run:** a run missed while the app was closed or asleep runs
    once on return if the miss is recent (within a grace window), and is
    otherwise recorded as missed. A backlog is never run.
  - **Chat busy:** a run due while the target chat is mid-turn waits its turn.
  - **Still running:** a run due while the same routine's previous run is
    still going is skipped.
  - **Chat gone:** a run whose target chat no longer exists (deleted or
    purged by retention) starts a new chat and records that it did. A
    connector target starts it in the same channel.
  - **Other failures:** a turn that fails, or needs a sign-in nobody can
    give, is recorded as failed.
- [ ] **The Self-configuration tab governs two things.**
  - The tab has two items, **Agent prompt** (the existing description and
    system prompt tools) and **Routines**.
  - Each item has its own on/off switch and its own "require approval" switch.
  - Routines is off by default.
  - Every existing agent keeps exactly its current self-configuration
    behaviour through the upgrade.
- [ ] **An agent schedules its own routines when allowed.**
  - With the Routines item on, the agent can list, create, change and cancel
    its own routines. That includes routines the operator made, so the
    operator decides through the approval switch.
  - Each change appears in the normal tool stream.
  - With the item off, the agent has no routine tools.
  - No agent can reach another agent's routines, or target a chat belonging
    to another agent.
  - *(Behavior-test-backed: a live model schedules "check back later" and the
    run lands.)*
- [ ] **Agent routine changes are overseen.**
  - With Routines approval on, an agent's create, change or cancel is held as
    pending, with no effect, until the operator approves or dismisses it.
  - Every routine change the agent makes, applied or not, is recorded where the
    operator can see it.
- [ ] **Injected content cannot plant a routine unnoticed, and routines are
      bounded.**
  - A routine created or changed by the agent after untrusted content appeared
    in its conversation is flagged "Check this" wherever it is shown. A
    scripted-tool-call test proves this deterministically.
  - An agent's active routines are capped in number and frequency.
  - A refused change tells the agent why.
- [ ] **Routines follow their agent.** Renaming an agent keeps its routines,
      deleting it removes them, and existing installs upgrade with no data
      loss.

## Stakeholders

- **Operator (device owner)**, the only human. Gets agents that do recurring
  work and follow-ups without being prompted. Must always be able to see every
  routine, where it came from, what it did and why a run did not happen, and
  must never find a routine they did not expect running unnoticed.
- **Connector peers**: people in a Discord or Telegram channel that a routine
  targets. They receive messages the agent was not asked for in that moment.
  Their interest is that only the operator's or an approved routine posts into
  their channel.
- **Agents**: gain a way to follow up. Their interest is routine tools that are
  simple, describe their limits honestly, and refuse with a reason.

## Constraints

- **Per agent only.** A routine belongs to one agent. Routines are not a Library
  section, and no agent reaches another agent's routines.
- **Routines are per agent, not per chat** (operator decision).
  - An agent with Routines self-configuration on can retarget any of its
    routines to any of its own chats, operator routines included. That is
    what turning the item on means.
  - An operator who wants a routine the agent cannot touch creates a
    separate agent for it.
- **Targets are that agent's chats.**
  - An existing-chat target is one of the agent's own chats, web or connector.
  - New and own-chat targets are web chats. A connector chat cannot be created
    from the app side.
- **No notification on run** (operator decision). A run is visible in its chat
  and in run history, and nothing else announces it.
- **Agent routine tools are governed by the Self-configuration tab**
  (operator decision).
  - The tab becomes two items, Agent prompt and Routines, each with its own
    enable and approval switch.
  - The agent has **full control** of its routines (operator decision): it
    can list, change and cancel operator-made routines too. The approval
    switch is the operator's check.
- **Missed runs: one recent catch-up, never a backlog** (operator decision).
- **Only the reply goes out to a connector channel.** A routine's prompt is
  never posted to the channel; peers see the agent's reply alone.
- **Every run ends.**
  - A run has a time limit and always reaches an outcome in run history.
  - A run that needs input nobody can give (a sign-in, a stalled tool) fails.
    It never holds the session lock waiting.
  - A run left in progress by a restart or shutdown is marked interrupted at
    startup, as the knowledge indexer requeues stranded items.
  - The scheduler loop starts and drains in the web app's lifespan beside the
    purge loop.
- **Routine names are names.** A name is unique within its agent. If the
  name rule (`the_one/naming.py::check_name`) applies, `tests/test_api_name_rule.py`
  classifies the new write routes.
- **Rename and delete carry everything routine-shaped.** That means routines,
  their run history, any proposals record and own-chat references, all
  cascading with the agent.
- **Every agent routine change is a visible tool call**, recorded with whether
  untrusted content preceded it. This is the notes precedent: undeclared tools
  count as untrusted (fail closed).
- **Time follows the operator's time-zone setting** (Mission 28), not the host
  zone directly.
- **The frozen agent loop** (`factory.py`) is touched only by deliberate,
  owner-approved exception, as in Mission 27.
- **Single-user, loopback-only posture unchanged** (`SECURITY-MODEL.md`). The
  security model gains a routines section: an agent that can schedule itself is
  a persistence mechanism for injected instructions.
- **Project conventions apply:**
  - migrations in `the_one/db/schema.py`, with migration tests;
  - agent-keyed tables cascade on rename and delete;
  - new testids registered in `docs/ui-testid-registry.md`;
  - new controls from the `App.ui` library;
  - tests built on the schema template;
  - any new test seam behind dev mode and its own flag.
- **Platform prompt text** changed by this mission (routine tool descriptions,
  any routine-run framing) lands with an eval run compared against the current
  baseline (Mission 30 convention).
- **Planning skills do not implement.** Implementation runs through
  `/mission-control:agentic-workflow`.

## Environment Requirements

- Local host-native toolchain. `make test-unit` is the canonical unit gate.
  Browser lanes run through `make test-browser` / `scripts/run-tests.sh --lane …`
  with `THE_ONE_TEST_NETNS=1` on this WSL host.
- **Behavior tests run on a dedicated dev instance** (non-default port and a
  scratch data directory, started from a scratch working directory). Never port
  8484 or the operator's default data directory.
- **Time can't wait.** A behavior test cannot wait until 9 AM. Tests need a
  way to make a routine due now: a dev-mode, separately flagged test seam, or a
  short one-off delay. The way is decided in Flight 1. Schedule arithmetic
  (daylight-saving changes, weekdays, catch-up) is proven at the unit tier
  with a frozen clock (`frozen_clock`).
- The mock provider scripts tool calls, so routine tool writes, limits,
  approval and flagging can be proven deterministically. Whether a real model
  schedules a follow-up sensibly needs a live provider turn.
- A connector delivery uses the stub connector test seam
  (`THE_ONE_DEV_MODE=true` + `THE_ONE_STUB_TEST_ENDPOINT=1`).
- No new external accounts or services.

## Open Questions

- **Schedule representation.** Lean (architect and Flight Director):
  structured data for the five schedule kinds and a small hand-rolled
  next-run calculator, as pure functions tested with `frozen_clock`. No RFC
  5545 and no cron. The operator and the agent see the same structured
  choices.
- **What happens on a daylight-saving change.** A 2:30 AM daily routine on
  the spring-forward day, and a 1:30 AM one on the fall-back day. Lean: in
  the spring-forward gap, run once at the next valid time. On the fall-back
  repeat, run once, never twice.
- **The grace window.** A fixed duration, or relative to the interval? An
  "every 2 hours" routine and a daily one probably differ.
- **What the run's message is.** Options:
  - a user-role message with a routine marker (architect's lean: it is least
    likely to confuse the model, and it fits the peer-field pattern);
  - a system-style notice followed by the prompt.

  The choice affects how the model reads it and the "Routine: {name}" chip.
  A new optional `Message` field must be handled by every provider's message
  serializer and by `db/codec.py`, so it never leaks into a provider payload.
- **How the drawer knows a chat was activated by a routine.** Read it from
  the stored message marker, or record it on the session?
- **Is a routine run's own content untrusted?** If an agent wrote a routine's
  prompt after untrusted content, each run replays agent-authored text with no
  human present. Should notes written during that run be flagged? Lean: a
  run of a flagged routine counts as untrusted.
- **How the agent's routine tools reach the conversation.** They are governed
  by the Self-configuration tab, but the loopback surface cannot see turn
  context. Options:
  - native tools gated by the Routines item, as notes are gated by their
    switch (lean, architect and Flight Director);
  - surface tools that receive the conversation's flag state some other way.

  Native tools mean the two Self-configuration items work by different
  mechanisms: Agent prompt stays on the loopback source and its credential,
  and Routines gates native tools. The tab hides that difference. Registering
  native tools should be a provider hook in `AgentFactory.create`, as for
  notes and knowledge bases, not a change to the frozen loop. The Flight 2
  design review confirms this.
- **How the agent finds its routine tools.** Notes faced the same problem: built-ins stay
  hidden behind `search_tools`.
- **The approval record.** Extend `agent_revisions` (a table-rebuild for the
  CHECK, routine-shaped payloads in text columns, and prompt-specific restore
  semantics) or give routines their own proposals table? Lean (architect): a
  separate table, with the Routines item showing its own pending and history,
  including the "Check this" flag on a pending proposal.
- **Approve against a changed routine.** Prompt revisions refuse to approve
  over a drifted value (409, `?override=true`). Does a pending routine change
  follow the same rule?
- **Keeping a connector target alive.** A purged or deleted target starts a
  new chat (operator decision). For a connector target, the new chat must be
  in the same channel, so the routine should keep the channel's identity
  (platform, connector, channel, thread) and not just a session id. The same
  applies to a connector chat closed with `/new` or past its continuation
  window: deliver to the stored channel, or into the session a fresh inbound
  message would use? Decide in Flight 1.
- **The upgrade mapping.** How today's single enable and approval switches
  map onto Agent prompt (enabled and approval carried over) and Routines (off).
- **Who wins an edit race.** The operator edits a routine while the agent
  proposes a change to it, or a run is in flight.

## Known Issues

*(None yet.)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [x] Flight 1: **Operator routines, end to end.**
  - The routines store and migration (cascading with the agent).
  - The schedule kinds and next-run calculation in the operator zone.
  - The scheduler loop and the unattended run path. The run path takes the
    session lock, and in a connector chat it delivers through the connector,
    which needs the delivery step taken out of the inbound pipeline.
  - The routine-origin message marker and the three target kinds.
  - Missed, overlapping, busy and missing-target handling.
  - Run history.
  - The Routines tab.
  - The drawer's "activated by a routine" line and routines list.
  - The test seam for making a routine due.

  This flight carries the mission's runtime risk: a new background loop, a
  headless run path and the connector delivery refactor. The operator can use
  routines before any agent can create them.
- [x] Flight 2: **Agents schedule their own routines.**
  - The Self-configuration tab split into Agent prompt and Routines, each with
    enable and approval switches, and the upgrade mapping.
  - The agent routine tools, with full control of the agent's routines.
  - How the tools are reached, discovered and scoped to the agent's own chats.
  - Approval: pending, approve or dismiss, the change record.
  - Untrusted-content flagging, and caps on count and frequency.
  - The security-model section.
  - The live behavior test.

  This flight carries every untrusted-input decision.
- [ ] Flight 3: **Schedules and limits.** Added in Flight 3 planning, when
      the operator reviewed the Flight 1 and 2 judgement calls:
  - a calendar recurrence (Google Calendar style) replaces the five schedule
    kinds, in the form and the agent's tools;
  - one active-routine cap for everyone, a 1-minute floor, no runs-a-day cap;
  - finished routines and resolved proposals age out with retention;
  - maintenance on the same surfaces (route and turn-host moves, the agent
    editor controller split, squawks 0232, 0273, 0284, lane headroom).
- [ ] Flight 4: **HAT and alignment.** One guided human acceptance test for the
      whole mission, with the operator present. Flights 1-3 carry no HAT
      legs of their own and land on automated gates and behavior tests
      (operator decision). The walk covers:
  - an operator daily routine to a connector chat, including a real Discord
    DM (Flight 1 debrief, Recommendation 4);
  - an agent-scheduled follow-up;
  - approval mode;
  - the Routines and Self-configuration tabs and the chat panel together;
  - the recurrence form.

  Fix what surfaces through the fix-vs-feature gate, and review the
  judgement calls still open (Flight 1's *(autonomous judgement call)* and
  Flight 2's *(J)* decisions not already settled in Flight 3 planning, and
  Flight 3's *(FD)* calls).

**Pre-declared split point:** Flight 1 is heavy. If the design review finds
that moving connector delivery out of the inbound pipeline needs more than a
contained change, split it into its own flight. It would be preceded by
characterization tests of today's delivery. The scheduler, web-chat runs,
the Routines tab and the panel then land first, with connector-chat targets
following. The signal is the design review's assessment of the delivery
change, not the volume of work.

**Why this split.** The boundary is a risk seam, not a layer:
- Flight 1 is operator-authored and carries runtime risk (scheduling and
  unattended execution).
- Flight 2 carries the security decisions. It builds on a run path that
  already works, so its tests can prove an agent-made routine actually runs.

Each flight carries its own schema, backend, UI and tests.
