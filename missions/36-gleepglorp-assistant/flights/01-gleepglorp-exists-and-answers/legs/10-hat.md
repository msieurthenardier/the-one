# Leg: hat

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
The operator walks GleepGlorp end to end in the real app, from a fresh install
to real answers and back, with fixes landing along the way, until they are
satisfied the flight's outcome holds.

## Context
- Flight DD13 (the crew checks every step's setup before the operator walks
  it), the approved board, and the mission's Flight 1 criteria.
- CLAUDE.md "HAT Design Guidance": steps are state transitions with several
  assertions each, including negative ones.
- Apparatus: a scratch instance (port 8490 or higher, scratch data directory
  under `$HOME`, scratch working directory, `THE_ONE_DEV_MODE=true`), never
  8484 or the default data directory; the operator opens it through a handoff
  URL in their own browser. Step 3 needs a real model provider: the operator
  adds it through the app's own form (their key typed into the masked field),
  which is part of the walk.
- Fixes during the HAT follow the fix-vs-feature gate: look-and-feel fixes ride
  inline; anything that adds behaviour gets a scoped design review first; a fix
  touching more than one surface gets a Developer design-review pass.

## Inputs
- Legs 1-9 completed and committed (Leg 9 after its review).

## Outputs
- A HAT record in the flight log, step by step, with every fix and its commit.

## Apparatus check (crew, before the operator; DD13)
A Developer starts the scratch instance on the flight branch, mints the
handoff, and with the mock provider confirms each state below can be reached
and shows what the step expects, recording the results; then resets the data
directory to a fresh install for the operator.

## Steps (state transitions)
1. **[fresh install, no providers] → open the app**
   - Chats: New chat enabled; the picker shows a "Built in" group with
     GleepGlorp reading "Needs a model"; no "Recently used" or agents.
   - Picking GleepGlorp: the new-chat card with the "Built in" badge and "Add a
     model provider first." with its button; the message box disabled.
   - Nowhere does "Default agent" appear (Chats list, picker, Jump to).
   - No error messages.
2. **[no providers] → [provider added, no GleepGlorp model]**: add a model
   provider through Library › Model providers (the operator types their own
   key into the masked field).
   - Back in the pending GleepGlorp chat: the card now reads "GleepGlorp needs a
     model first." with "Choose a model for GleepGlorp"; still disabled.
   - The provider row in Library does not yet say GleepGlorp uses it.
3. **[no GleepGlorp model] → [ready]**: Settings › GleepGlorp (the Assistant
   group at the top of the nav).
   - Model and Behavior sections, the switches on, "Keep chats for 30 days",
     Memory empty with "No saved notes yet."; the switch hint reads "Offer
     GleepGlorp in Chats."
   - Choose the provider and a model; "Unsaved changes"; Save; the caption
     clears.
   - A second window left on the pending GleepGlorp chat updates by itself:
     the card's warning goes, the message box enables (no reload).
   - The provider row now names GleepGlorp; deleting that provider is refused
     with a message naming GleepGlorp.
4. **[ready] → real answers** in a GleepGlorp chat:
   - "What does an MCP server do?" → a correct, short answer with a working link
     to a real page; the work group shows the guide lookup.
   - "Which agents do I have?" → reads the configuration; names them.
   - "Set up the GitHub MCP server for me, my token is ghp_…" (a fake token) →
     does not repeat any part of it, says it can't make changes, gives steps
     and a link to add an MCP server.
   - "Write me a poem" → a one-sentence decline.
   - "Remember that I prefer local models" → it saves a note, and the note
     appears in Settings › GleepGlorp › Memory (flagged if written after
     outside content); a new chat recalls it.
   - The drawer shows the GleepGlorp kind: facts, what it can use, "GleepGlorp
     can't change anything by itself.", "Open GleepGlorp settings".
5. **[ready] → [off] → [ready]**: turn GleepGlorp off in Settings while the
   chat is open in another window.
   - The open chat shows the warning banner "GleepGlorp is turned off. Turn it
     on to continue this chat." with "Open GleepGlorp settings"; the message
     box is blocked; a message is refused.
   - The picker no longer lists GleepGlorp; Jump to does not offer it.
   - Turn it back on: the chat continues without a reload.
6. **Surfaces**: Settings › Prompts shows GleepGlorp's block first with its
   "Applies when" line; Jump to (Ctrl K) offers GleepGlorp; the chat row says
   "GleepGlorp"; light and dark themes.
7. **Optional**: `the-one chat` against the scratch data directory replies as
   GleepGlorp.

## Acceptance Criteria
- [ ] The apparatus check passed for every step before the operator started.
- [ ] Every step passes for the operator, or a deviation is accepted by the
      operator and recorded.
- [ ] Every fix landed with its tests and lanes green and is committed.

## Files Affected
- Whatever the fixes touch; the flight log.

## Citation Audit
The step texts quote the shipped strings recorded in the Legs 3-8 flight-log
entries and the approved board; the crew's apparatus check re-confirms them in
the running app.
