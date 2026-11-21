# Leg: hat

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective

The operator walks the flight's behaviour with a real Claude model (DD13),
fixing what they find through the fix-vs-feature gate. Then the closing
gate: a full quiet-host `make gate` on HEAD, from which the unit and
full-gate targets in `CLAUDE.md` are restated and the lanes re-budgeted.

## Apparatus (the FD checks it once before step 1)
- **Instance:** a dev instance on port 8486, with a scratch data dir under
  `$HOME` and a scratch working directory. `THE_ONE_DEV_MODE=true`. Start it
  with `the-one serve`, record its PID, and stop it by that PID.
- **Never** 8484 or 8485, or the default data directory.
- **Browser:** the operator's own browser at `http://127.0.0.1:8486`,
  through a handoff URL minted with the instance credential.
- **The model:** the operator adds a Claude provider in Library › Model
  providers themselves (OAuth or a token they paste into the provider form,
  never into a chat) and picks it for GleepGlorp in Settings › GleepGlorp.
  The FD never sees or handles the key.
- **Agents:** the FD seeds two agents and one MCP server through the API (no
  secrets), so the walk has something to change.

## Steps (state transitions; each lists what to see, including what must NOT appear)
1. **[off] → [setup].** Settings › GleepGlorp with no model:
   - the corner button shows on Agents, Library and Settings, and not on
     Chats;
   - the drawer opens to the setup block, whose link goes to Settings ›
     GleepGlorp;
   - no error.
2. **[setup] → [ready].** Pick the provider and model:
   - the setup block goes away without a reload;
   - the composer is enabled.
3. **[ready] Esc and Close.**
   - Open the drawer, then Esc: the drawer closes and focus is on the
     button.
   - Open it, then Close: the same.
   - At 1280px and wider it pushes the page; narrower, it overlays.
4. **[ready] Continuity.** Ask something on Agents, move to Library, then
   reload:
   - the same conversation is there after each move and after the reload;
   - the "Looking at" line follows the page;
   - each sent message shows its page chip;
   - New chat starts empty.
5. **[ready] Open in Chats.** The drawer conversation opens in Chats with the
   chips, and the drawer is hidden there. Back on Agents, the drawer still
   has the conversation.
6. **[ready] "What does this page do?"** On Library › MCP servers › New MCP
   server, then on Settings › Built-in tools:
   - the answer is about that page;
   - the link it ends with lands (a known weak cell, `page-what-is-link`
     7/20 on Haiku).
7. **[ready] A fill for a new agent.** On Agents › New, "Create an agent
   called Trip Planner that plans holidays":
   - the editor fills as unsaved edits, with a note per field;
   - the receipt reads "Form filled … Not saved", and the reply says not
     saved;
   - the reply's link goes to `#agents/~new`, not to the unsaved agent's
     page;
   - nothing is saved until Create.
8. **[ready] A fill over an unsaved edit.** Open an existing agent and type
   in its description without saving. Then ask GleepGlorp to change its
   description and its system prompt:
   - your description is kept, and the receipt says "partly filled" and why;
   - the system prompt is filled;
   - Cancel restores everything.
9. **[ready] Stay at the leave guard.** With unsaved edits on one agent, ask
   for a fill on another. At the leave dialog, choose Stay:
   - the fill is not applied and the receipt offers Fill now;
   - Fill now later applies it.
10. **[ready] A fill after a fetched page.** Ask GleepGlorp to read a public
    web page about an agent idea, then to fill an agent from it:
    - the receipt carries "Check this";
    - the fields hold no link or address from the page (the accepted
      residual: if one appears, record it, since Save is still yours).
11. **[ready] A key on a provider page.** Paste a fake-looking key
    (`sk-test-not-real-0000`) while on Library › Model providers › New:
    - GleepGlorp refuses and links the page;
    - no fill;
    - the key is not repeated.
12. **[ready] → [off].** Turn GleepGlorp off in Settings:
    - the corner button and the drawer go away;
    - turning it back on brings back the button and the conversation.

## Carry items to settle during the walk
- **The overlay and the page:** whether an open overlay should make `<main>`
  inert (from Leg 2).
- **The bot icon:** whether the robot icon matching the Agents rail icon is
  wanted (from Leg 2).
- **The page line after a fill:** the drawer reads "Looking at Agents ›
  New" while the editor title is "New Agent" (Leg 9).
- **The old Windows scratch root:**
  `%LOCALAPPDATA%\Temp\the-one-f5` holds earlier missions' data dirs and no
  sentinel. Clean it, or leave it (the operator's call).

## Closing gate (after the walk's fixes are committed)
- **Quiet host first:** 1-minute load below 1.0, no other test process
  (`uptime`, `ps`).
- **The run:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1
  TEST_TIMEOUT=3600 make gate` on HEAD.
- **From it:**
  - restate the `CLAUDE.md` unit target and full-gate total;
  - re-budget every lane that moved more than 15%, including `shared`
    (610 s against 420 s at batch B, loaded) and the fill and drawer lanes;
  - closing squawk 0389's quiet re-measure note.
- **A loaded run** is recorded but not used for budgets.

## Acceptance
- Every step passes, or its failure is fixed (through a Developer, a review
  and a commit) and the step re-walked.
- The carry items are decided and recorded.
- The closing gate is green on a quiet host, and the targets and budgets
  are restated in `CLAUDE.md` and `scripts/run-tests.sh` in the same commit
  as the flight's landing.
