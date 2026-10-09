# Mission: Agent Notes and Rules

**Status**: active

## Outcome

An agent carries what it has learned and what the operator expects of it from
one conversation into the next. Each agent gets two persistent layers:

- **Rules**: standing instructions the operator writes. They outrank anything
  the agent saved for itself, and the agent cannot change them.
- **Notes**: short notes the agent saves for itself while it works. The agent
  can update or remove a note, and the operator can see, edit and remove every
  note.

Both layers belong to one agent and reach every new conversation with it, in
the app and in connector channels alike. The operator always knows what the
agent has saved, where each note came from, and whether untrusted content was
in play when the agent saved it. Turning notes off deletes nothing.

Source: GitHub issue [#230](https://github.com/msieurthenardier/the-one/issues/230).
The issue calls the feature "Memory", with `memory_*` tools. This mission
renames it **Notes** throughout (operator decision): one note is one discrete
item the agent saved.

## Context

Today every conversation starts from the same place: the base prompt plus the
agent's persona. An operator who wants an agent to keep doing something has to
edit the persona. An agent that learns a fact about the operator, a project or a
channel loses it when the conversation ends. Issue #230 settles the product
shape. Prior art was reviewed there (Letta memory blocks, ChatGPT saved
memories, Anthropic's memory tool, Mem0), and the issue chose:

- **Prompt layering with explicit tool writes.** Every write the agent makes is
  a visible tool call in the normal tool stream.
- **No background extraction.** A hidden summarisation pass would build a
  synthesis layer the operator never sees.

Facts about the codebase that shape the design (verified at `77308c5`):

- **One place composes the prompt.** `compose_system_prompt`
  (`the_one/agent/config.py:82`) joins the base prompt and the persona, and
  production calls it once, in `AgentFactory.create`. Rules and notes slot in
  after the persona. Chat-only models get them too: the degraded path swaps
  only the base-prompt prefix (`the_one/agent/core.py:444-465`). The
  composed prompt must therefore keep starting with the base prompt. A
  chat-only model reads notes but has no tools to write them. That is
  intended.
- **Changes apply on the agent's next build.** This is an operator decision
  taken while planning, and it removes the costliest seam. A note the agent
  saves mid-conversation is already in that conversation's context, as its own
  tool call. A Rules edit made mid-conversation behaves like any Studio edit
  today: it takes effect when the agent is next built. The agent is built:
  - for a new conversation;
  - on every web rejoin (`_restore_session`, `app.py:1526`), except while a
    turn is in flight;
  - on every incoming connector message (`the_one/connectors/inbound.py:437`).

  Nothing pushes a change into a web conversation that is open and not
  rejoined.
- **Turning notes on and off.** The built-in tool whitelist cannot carry it.
  An agent saved with a narrowed `enabled_tools` list would silently never see
  new tools. Prompt injection of notes also needs a signal of its own. A
  dedicated operator-owned per-agent setting has precedent:
  `self_revision_requires_approval` (v35).
- **Nothing tracks where content came from.**
  - Tool results carry only `is_error`.
  - Web, MCP, knowledge-base and file results come back as plain text.
  - A connector message's author is attached to the history only after the
    turn finishes (`_bind_peer_name`, `inbound.py:210-238`), so no tool can
    see who sent the current message.

  Recording a note's origin peer, and whether untrusted content came before
  it, is new plumbing:
  - The only turn-scoped context today is two context variables, the session id
    and the tool call id (`the_one/agent/_context.py`).
  - The connector side can set the current author beside the existing
    session-id set in `dispatch_inbound` (`inbound.py:451`).
  - Tracking untrusted content means classifying tool output where tools are
    dispatched, in `the_one/agent/core.py`. `factory.py:501-504` describes
    that loop as frozen, so touching it is a deliberate, owner-approved
    exception.
- **This is the self-configuration risk again.** Mission 21 named indirect
  prompt injection as the live residual risk of an agent that writes to its own
  prompt (`SECURITY-MODEL.md`, "Self-configuration surface"). Notes are a second
  instance, and a wider one:
  - its writes are ungated by design, with no approval mode (a non-goal of
    #230);
  - in a connector channel, one peer's conversation can plant a note that later
    reaches other peers.

  The mitigation is provenance, an explicit boundary in the prompt, and limits.
  An approval gate is not part of it.

## Success Criteria

- [ ] **Rules shape new conversations.** The operator can add, edit, reorder,
      enable, disable and delete an agent's rules. Every new conversation with
      that agent, web or connector, follows its enabled rules in order. A
      disabled rule has no effect. *(Behavior-test-backed: needs a live agent
      turn.)*
- [ ] **The agent keeps notes across conversations.** With notes on, the agent
      can save, update and forget notes during a conversation. Each write
      appears in the normal tool stream. The notes reach every later
      conversation with that agent, web and connector. *(Behavior-test-backed.)*
- [ ] **Notes are the operator's to see and control.**
  - The operator can see every note an agent holds, with when it was written,
    its origin conversation and, for connector conversations, its origin peer.
  - The operator can edit or delete any single note, or clear them all.
  - The notes are visible from the agent's settings and from the open
    conversation's agent panel.
- [ ] **Off by default, and off loses nothing.** Notes are off for every
      existing and every new agent until the operator turns them on. With notes
      off, the agent neither sees nor writes notes, nothing is deleted, and the
      UI says so.
- [ ] **Rules outrank notes, and the agent cannot touch rules.** No capability
      offered to the agent can create, change or remove a rule. Where a note
      conflicts with a rule, the rule wins. *(Behavior-test-backed.)*
- [ ] **Notes are bounded.**
  - The total size of an agent's notes has a limit, and so does the size of a single
    note. The number of writes in one turn has a limit too.
  - A duplicate of an existing note is not stored twice.
  - When a write is refused, the agent gets an error telling it what to do (for
    example, consolidate or forget notes), and the operator sees the refusal in
    the tool stream.
- [ ] **Notes are presented as notes, not instructions.**
  - Saved notes reach the agent clearly marked as reference material, beneath
    the rules.
  - The agent refers to them as saved notes, not as personal recollection, and
    saves without commentary.
  - Every operator-facing surface uses the same flat language.
- [ ] **Injected content cannot plant a note unnoticed.**
  - Once untrusted content has appeared anywhere in a conversation, every note
    written later in that conversation is flagged. Untrusted content includes
    fetched pages, results from tools that read outside sources, and another
    peer's message.
  - The flag is shown to the operator wherever the note is shown.
  - The flag survives the conversation being resumed or rebuilt.
  - The contract: a planted instruction cannot produce an unflagged note. In a
    test where a fetched page tells the agent to save a malicious note, any note
    written carries the flag. A test with scripted tool calls proves this
    deterministically.
  - With a live model, the run also records whether the agent wrote the note at
    all, and confirms the rules still win. *(Behavior-test-backed.)*
- [ ] **An agent's rules and notes follow it.**
  - Renaming an agent keeps its rules, its notes and its self-configuration
    revision history.
  - Deleting an agent removes all three.
  - Existing installs upgrade with no data loss.
- [ ] **The UI says when changes apply.** Wherever the operator edits rules or
      notes, the UI states when the change takes effect: new conversations and
      reopened ones, and the next message in a connector channel.

## Stakeholders

- **Operator (device owner)**, the only human. Gains agents that improve over
  time without hand-editing personas. Must never be surprised by a note they
  cannot see, trace or remove.
- **Connector peers**: people talking to an agent in Discord or Telegram. Their
  messages can lead to notes, and they will see the effects of notes other peers
  caused. Their interest is that the agent behaves predictably and does not
  surface one peer's details carelessly to another. The design accepts
  agent-wide sharing, and the security model should say so plainly.
- **Agents**: gain continuity. Their interest is a notes surface that is
  cheap to use and honest about its limits.

## Constraints

- **Per agent only.** No global or shared notes, and no cross-agent reads.
- **Writes are explicit tool calls by the model.** No background extraction or
  summarisation pass. Every write is visible in the tool stream.
- **No approval gate on note writes** (a non-goal of #230). Oversight is by
  visibility, provenance and removal, not by pre-approval.
- **Rules are operator-authored only.** No agent capability can write or delete
  them, and they take precedence over notes in the prompt.
- **Notes are shared agent-wide** (operator decision): a note produced in one
  conversation or channel reaches all of that agent's later conversations. Each
  note records its origin, and the security model documents the cross-peer
  exposure.
- **Notes have their own per-agent on/off switch, off by default** (operator
  decision). It does not ride the built-in tool whitelist, and it governs both
  the tools and the notes reaching the prompt. Turning it off deletes nothing.
- **Changes apply on the agent's next build** (operator decision): a new
  conversation, a web rejoin, or the next connector message. Getting a rules
  or notes change into a web conversation that is open and not rejoined is not
  required.
- **Untrusted content flags for the whole conversation** (operator decision).
  The flag covers everything the model has seen in the conversation so far, not
  just the current turn. In tool-heavy conversations most notes will carry it,
  so the UI presents it as "check this", not as an alarm. Tools whose trust is
  not declared count as untrusted (fail closed).
- **A note's origin outlives its conversation.** Chat-history retention purges
  sessions, so a note keeps its origin as a plain reference plus a readable
  label. A purged origin conversation must not break or delete the note.
- **Limits hold under concurrency.** Different connector sessions for the same
  agent run turns concurrently (session locks are per session), so caps and
  de-duplication must hold across concurrent writers.
- **One agent-editor tab, two sections** (operator decision). Rules and notes
  share a single new tab in the agent editor (working label "Rules and
  notes"), with a Rules section and a Notes section, because they are closely
  related layers of the same prompt. The open conversation's agent panel shows
  both as well: rules read-only with a link to the tab, notes with delete and
  clear all.
- **Flat, non-personified language.** In the UI and the prompt: "saved notes",
  never "I remember". No cheerful announcements in the UI.
- **The feature is called Notes, never Memory** (operator decision). This
  covers the UI, the prompt, the docs, the tool names and the schema. The exact
  tool names are a Flight 2 decision. Avoid a tool named plain `memory`: schema
  v7 strips a retired tool of that name from stored tool lists.
- **Single-user, loopback-only posture unchanged** (`SECURITY-MODEL.md`).
- **Project conventions apply:** migrations in `the_one/db/schema.py` with
  migration tests, new testids registered in `docs/ui-testid-registry.md`, the
  `App.ui` control library for any new control, and tests built on the schema
  template.
- **Planning skills do not implement.** Implementation runs through
  `/mission-control:agentic-workflow`.

## Environment Requirements

- Local host-native toolchain. `make test-unit` is the canonical unit gate.
  Browser lanes run via `make test-browser` / `scripts/run-tests.sh --lane …`.
- **Behavior tests run on a dedicated dev instance** (non-default port and a
  scratch data directory). Never port 8484 or the operator's default data
  directory.
- The dev-mode mock provider can script tool calls
  (`config.response.tool_calls`). That is enough to prove deterministically
  that writes, limits and provenance flags work. Whether a real model follows
  the rules, prefers rules over notes, and resists a planted instruction needs a
  live provider turn, so those criteria are marked behavior-test-backed.
- A connector round trip uses the stub connector test seam
  (`THE_ONE_DEV_MODE=true` + `THE_ONE_STUB_TEST_ENDPOINT=1`).
- No new external accounts or services.

## Open Questions

- **Limits.** What are the total notes cap, the per-note cap, the per-turn
  write cap and the rules cap, and in what unit (characters or tokens)? Decide
  in the flight that builds each one. Rules and notes are sent on every turn,
  so the caps must be sized against small context windows (Ollama defaults)
  and the context-usage display. Ordering them before the conversation keeps
  the prompt-cache prefix stable until notes change.
- **How each tool's trust is declared and tracked.** The scope is settled:
  the whole conversation. Still open:
  - where trust is declared (preferably registry metadata, with undeclared
    tools untrusted);
  - which built-ins count as trusted (the notes and self-configuration tools
    themselves, for example);
  - whether connector messages from the operator's own account count as
    trusted;
  - how a resumed or rebuilt conversation recovers its flag state from the
    persisted history;
  - how the tracking works with parallel tool dispatch, given the frozen loop.
- **How the agent finds its notes tools.** Built-in tools stay hidden until
  `search_tools` finds them (the strict baseline). Notes tools the agent has to
  search for before saving will rarely be used. Seeding them into the baseline,
  as the DD-5/DD-6 path in `factory.py` does, touches the frozen loop's
  baseline. That needs a deliberate decision.
- **How update and forget name a note.** If notes are addressed by id, the
  prompt must show the ids, which spends context and puts machine detail in
  front of the model. Matching on content is fragile. Decide alongside the
  prompt format.
- **What "duplicate" means**: exact, normalised, or near-duplicate.
- **How the notes switch relates to the existing tool controls.** Do the
  notes tools also appear in the Built-in Tools tab and the global Settings ›
  Built-in tools list? If so, how do the global toggle, the per-agent tool
  toggles and the notes switch combine?
- **Origin peer plumbing.** Making the current connector message's author
  visible to a tool needs a new channel into the turn. Choose one that does not
  disturb the post-turn `_bind_peer_name` attribution.
- **How rules and notes are keyed for the built-in "default" agent.** It is
  synthesised when no stored row exists (`factory.py:541-548`), so a foreign
  key to `agents(name)` cannot hold for it. One option is a materialised row.
  The other is a plain name column with an explicit cascade in rename and
  delete, which is the `chat_sessions` precedent. Decide in Flight 1.
- **The `agent_revisions` fix.** A table-rebuild migration with an update
  action, or an explicit update inside `rename`? The rebuild removes the trap
  for future tables. The explicit update needs no schema change.
- **Edit surface split.** #230 has the chat drawer delete notes and clear them
  all, and the agent's Rules and notes tab manage them. Is editing a note's text
  offered in both places or only in agent settings?

## Known Issues

- [ ] **Renaming an agent that has self-configuration revision history fails.**
      `agent_revisions.agent_name` references `agents(name)` with
      `ON DELETE CASCADE` but no update action
      (`the_one/db/schema.py:2061`, `:2195`). `SQLiteAgentStore.rename`
      (`the_one/db/repositories.py:323`) updates `agents` and `chat_sessions`
      only, so the primary-key update hits a foreign-key failure. The SQLite
      behaviour was reproduced on a minimal schema. No test renames an agent
      that has revisions. The new rules and notes tables would inherit the same
      failure. **Disposition: fixed in Flight 1**, alongside the rename cascade
      for the new tables, with a test that renames an agent holding revisions,
      rules and notes.
- [ ] **A `next_turn` self-configuration system-prompt revision drops the base
      prompt.** `self_configuration/pending.py::apply_pending_revision` puts the
      raw persona text in as the live agent's whole system prompt
      (`pending.py:94-97`) instead of recomposing base + persona. For the rest
      of that web conversation, the agent loses the tool-discovery and turn
      rules. Tests build the agent with a bare prompt, so they cannot see it.
      **Disposition: fixed in Flight 1.** Rules and notes need one "compose
      this agent's prompt" helper anyway, and the pending path should call it
      too, so the fix comes with that helper. The pending path applies at a
      settle point in `app.py` and has no store access today, so the helper
      must be callable there without an awkward sync/async seam.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [ ] Flight 1: **Rules and the prompt foundation.**
  - The single compose-this-agent's-prompt helper (persona, then rules, then a
    reserved notes slot), with the pending-revision path moved onto it.
  - The rules store and migration.
  - The rename/delete cascade, with the `agent_revisions` fix.
  - A new **Rules and notes** tab in the agent editor, with its Rules section
    (Flight 2 adds the Notes section).
  - Read-only Rules in the chat agent panel, with a link to edit them.
  - Low risk. Lets the operator see the layering working before notes build
    on it.
- [ ] Flight 2: **Notes.**
  - The notes store and migration, and the per-agent notes switch.
  - The notes tools and how the agent finds them.
  - Limits and de-duplication.
  - The "notes, not instructions" prompt boundary.
  - Provenance: origin conversation, origin peer, and the untrusted-content
    flag.
  - The Notes section of the Rules and notes tab, and the notes list in the
    chat agent panel with delete and clear all.
  - The planted-note behavior test and the security-model update.
  - This flight carries the mission's risk and its own cluster of security
    decisions.
- [ ] Flight 3: **HAT and alignment.** One guided human acceptance test for the
      whole mission, with the operator present (operator decision: Flights 1
      and 2 carry no HAT legs of their own and land on automated gates and
      behavior tests). It walks rules, notes, the Rules and notes tab and the
      chat agent panel together, including a connector channel. It fixes what
      surfaces, routing new behavior through the fix-vs-feature gate. It is
      also where the judgement calls made while the operator was away are
      reviewed: each is recorded as a design decision in its flight, marked
      *(autonomous judgement call)*.

**Pre-declared split point:** if Flight 2's untrusted-content tracking
needs more than a contained change to the frozen loop, split it into its own
flight. That covers the trust classification, the conversation-scoped flag,
and its recovery on rebuild. The rest of notes (store, tools, limits, UI) then
lands first with origin conversation and peer only. The signal is the design
review's assessment of the loop change, not the volume of work.

**Why two and not one.** The boundary sits at a risk seam, not a layer. Rules
are operator-authored, low risk and design-light. Notes carry every
untrusted-input decision in the mission: the trust flag, peer attribution, tool
discovery and limits. Putting the shared prompt helper and the cascade fix in
Flight 1 means Flight 2 builds on a proven layering and a rename that already
works. Each flight carries its own schema, backend, UI and tests.
