# Leg: 07-hat-and-closing-gate

**Status**: ready
**Flight**: [The remaining kinds](../flight.md)

## Objective

Close Flight 5 with the operator's guided HAT of the four new kinds (DD15), then the quiet-host
closing gate, which re-budgets the lanes.

## Context

- **Flight DD15:** the HAT walks, the apparatus and the quiet gate. The known gaps (DD15) are
  accepted and are not HAT failures:
  - direct saves don't push to other windows;
  - the rename carry isn't atomic;
  - a pasted key stays in the transcript;
  - the grid toggle has no fill path.
- **Leg 6's outcome** is carried to alignment, so the operator may see these shapes first-hand:
  - Haiku may repeat a pasted secret value in its handoff (`p5d` behaviour);
  - "Done!" openers;
  - in the drawer, a proposal where a fill was asked for.

  The HAT checks the product, not the prompt. A prompt-quality observation is recorded for
  alignment, not fixed here, because the prompt is frozen at `p5d`.
- **The fix-vs-feature gate** (agentic-workflow) applies to anything raised mid-HAT. A
  look-and-feel fix rides inline: a Developer, an FD diff read, then a re-check of the step. New
  behaviour goes to a scoped design review first. A fix that spans more than one surface gets a
  lightweight design review before it is implemented.
- **The dev instance** (CLAUDE.md "Behavior-test credential convention"):
  - port 8486, or the first free port at or above it;
  - `THE_ONE_DATA_DIR=$HOME/the-one-f5-hat/data`;
  - `THE_ONE_DEV_MODE=true`;
  - started from the scratch working directory `$HOME/the-one-f5-hat/cwd`, with `cd` on its own
    line, so the recorded PID is the server's (squawk 0404);
  - stopped by that PID at the end.

  Never port 8484 or 8485, and never the default data directory.
- **The model:** the operator adds a Claude Plan (Token) provider in the UI and sets GleepGlorp to
  it. The FD never handles a key and never reads the eval plan token.
- **Seed rows** (FD, via the instance's API, the credential never printed): one agent,
  `hat-agent`, with a knowledge base attached, created by the operator in step 1 or seeded.
  Seeding uses only the dev instance.

## Steps

### 7.1 The dev instance (FD)
Start it, create the credential (`the-one rotate-api-credential` against the scratch data
directory), check `/api/live`, mint a handoff URL and give it to the operator. The operator adds
the provider and sets GleepGlorp to it.

### 7.2 The HAT (operator; one step at a time; the operator's own phrasing first)
Each step is a state transition, with several assertions and a negative check: no error line,
and nothing saved before a Save or an approval.

1. **[empty Library] → [knowledge base filled]: create a knowledge base by fill.** In the drawer
   on Library › Knowledge bases › New, ask GleepGlorp to create one.
   - The name and description fill, with fill notes. Nothing is saved until Save.
   - The reply says to add folders after saving.
   - No error line.
2. **[knowledge base saved and used by `hat-agent`] → [rename proposed, then approved]: rename it
   by proposal.**
   - The card shows Now and Proposed, plus the warning about the agent's tool name.
   - After approval, the knowledge base is renamed and the agent's tool follows.
   - An open editor on that knowledge base shows the follow note.
3. **[no secret] → [secret filled, value handed off]: create a secret and paste a value.**
   - Name, description and allowed tools fill. The value is not filled.
   - The reply sends the operator to type it on the page. Note whether it repeats the value; that
     is a Leg 6 finding for alignment.
   - Save, then type the value.
4. **[secret saved] → [allowed tools widened by proposal]: widen its allowed tools by proposal.**
   - The card shows the whole list and the "can then be sent to …" warning.
   - Approve it. The secret editor, if open, follows with a note.
5. **[web tool editor open and dirty] → [timeout proposal approved]: change a web tool's timeout
   by proposal.** Open Settings › Tools › `fetch_url` and edit a field without saving. Then ask
   in Chats for a new default timeout, and approve.
   - The dirty editor keeps the operator's edits and shows the follow note.
   - No edit is lost.
6. **[Chats] → [refusal]: "Let my agents read my home folder."**
   - Nothing is proposed or filled.
   - The reply hands off to the Built-in tools page with a link.
   - No false "done".
7. **[web_search on DuckDuckGo] → [Brave proposed, key handed off]: switch search to Brave and
   paste a key.**
   - A `search_backend` proposal is made. The key is not in the proposal.
   - The reply sends the operator to the Built-in tools page for the key, not to Library Secrets
     (the exit-1 fix).
   - Approve, then check the grid and the editor.
8. **[Date and time open in a second window] → [time zone proposal approved]: change the time
   zone by proposal.**
   - It is proposed even from the drawer.
   - After approval, the second window's clock and its Date and time page follow, with the note,
     though the operator is not looking at it.
9. **[Knowledge indexing] → [chunk size filled] → [leave guard]: fill the chunk size from the
   drawer, then navigate away without saving.**
   - The field fills with its note and the "from now on" warning.
   - Leaving the page asks the leave guard. Stay keeps the value; Leave drops it.

### 7.3 Closing gate (FD, after the HAT and any fix commits)
- **The quiet-host check:** no other test process, and a 1-minute load below about 1.0. Then
  `TEST_TIMEOUT=3600 THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python make
  gate`.
- **Re-budget:** each lane's wall time is read. The three GleepGlorp lanes get real budgets, and
  any lane that moved more than 15% is re-budgeted (wall × 1.25, rounded up to 30 s). The
  full-gate target is restated, in `scripts/run-tests.sh` and the `the_one/agents.md` budget
  history. A Developer makes the change, and it gets a review and a commit.
- **Batch C note:** `test_flow_hash_routing.py::test_hash_routing_settings_nav_pushes_history`
  failed once in a loaded parallel run. **A failure on this quiet gate is a regression.**

## Acceptance Criteria

- [ ] **AC1.** The dev instance ran on port 8486 or higher with a scratch data directory. It was
  stopped by its recorded PID, and production was not touched.
- [ ] **AC2.** Each of the nine HAT steps passed, or was fixed and re-checked, or was recorded as
  a known gap or an alignment finding with the operator's agreement.
- [ ] **AC3.** Every HAT fix was reviewed and committed.
- [ ] **AC4.** The quiet-host `make gate` passed. The unit tier had 15 skips, and every browser
  lane passed.
- [ ] **AC5.** The lane budgets and the full-gate target are re-budgeted from that run, reviewed
  and committed.
