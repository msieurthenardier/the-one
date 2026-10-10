# Flight: HAT and Alignment

**Status**: planning
**Mission**: [Agent Notes and Rules](../../mission.md)

> Drafted by the Flight Director on 2026-10-10, at the end of the overnight
> autonomous run. The operator is the decision-maker here: confirm or reshape
> this plan before it moves to `ready`.

## Contributing to Criteria

- [ ] **Notes are presented as notes, not instructions**: the one criterion
      left open after Flight 2. Is the live model's post-save acknowledgement
      acceptable?
- [ ] Operator confirmation of every criterion ticked from automated and
      behavior-test evidence (Flights 1 and 2).
- [ ] Operator confirmation, or reversal, of each autonomous judgement call.

---

## Pre-Flight

### Objective

A guided human acceptance test of the whole mission, with the operator present.
It walks rules and notes end to end in the agent editor, the chat and a
connector channel. It fixes what surfaces: look-and-feel fixes inline, and new
behaviour through the fix-vs-feature gate. It settles every judgement call made
while the operator was away.

### Inputs

- PR #257 (Flight 1, rules) and PR #258 (Flight 2, notes, stacked on #257).
  Both are ready for review. This branch, `flight/03-hat-and-alignment`, is
  stacked on #258.
- **The HAT review list** is in
  [Flight 2's flight log](../02-notes/flight-log.md#hat-review-list-carried-to-flight-3).
  It covers look and feel, behaviour items (a) to (h), outside-the-feature
  items (i) to (k), and the judgement calls.
- Flight 1's judgement calls are under "Decisions" in its
  [flight log](../01-rules-and-prompt-foundation/flight-log.md).
- Behavior-test run logs:
  `tests/behavior/agent-rules-round-trip/runs/2026-10-09-22-40-11.md` (9/9) and
  `tests/behavior/agent-notes-round-trip/runs/2026-10-10-00-29-06.md` (11/11).

### Open Questions (for the operator, before or during the walk)

- [ ] **Environment:**
  - A dev instance on 8490 or higher with a scratch data directory, using the
    local Ollama provider as the behavior tests did? Or the operator's real
    providers?
  - The behavior tests used `gpt-oss:20b`. A stronger model may behave
    differently around the "save without comment" and rule-versus-note
    wording.
- [ ] **Connector:** walk a real Discord channel, or the stub seam?
- [ ] **Item (i):** should the default filesystem scope or the base prompt
      change? That is outside this mission, so is it a squawk or a new sortie?

### Design Decisions

**DD1 — One interactive HAT leg, a state-transition walk** (CLAUDE.md "HAT
Design Guidance").
- Each step names its transition and asserts the UI, the error area and the
  button states, with negative assertions ("no errors").
- Fixes route by the agentic-workflow's fix-vs-feature gate, and a
  multi-surface fix gets a quick design review.

**DD2 — Behavior-spec contracts are pinned.**
- `agent-rules-round-trip` and `agent-notes-round-trip` depend on these
  contracts:
  - testids: `tab-rules-and-notes`, `rules-*`, `notes-*`,
    `chat-drawer-rules*`, `chat-drawer-notes*`;
  - routes: `#agents/{name}/rules-and-notes`;
  - REST shapes: `/rules`, `/notes`, `/notes/settings`;
  - the prompt markers: "Rules set by the operator…", "Rules take precedence
    over saved notes.", `<saved_notes>`, "(unverified)".
- A HAT change to any of these is a **spec re-author**, done deliberately, not
  an inline fix.

### Prerequisites
- [ ] The operator has reviewed PRs #257 and #258, or chooses to review during
      the HAT.
- [ ] A dev instance is running from this branch (never port 8484 or 8485,
      never the default data directory). Ollama or a chosen provider is
      reachable.

---

## In-Flight

### Legs

- [ ] `hat-and-alignment` *(interactive)*: the guided walk below. Fixes are
      made inline or through the fix-vs-feature gate.

#### Draft walk (state transitions)

1. **[no rules, notes off]** Open an agent and its **Rules and notes** tab.
   - Check the tab label and its position (second).
   - Check the empty Rules state, the Notes switch (off) with the off message,
     and the "Changes apply…" line.
   - No Clear all is shown and no errors appear.
2. **[rules authored]** Add, edit, reorder, toggle and delete rules.
   - Try a 501-character rule: Add is disabled and the counter reads "over
     the limit".
   - Delete is armed, then confirmed.
   - Confirm the rule limits (500 / 4,000) and the prompt wording (DD4/DD5,
     shown in the stored prompt).
3. **[rules live]** Start a new chat; the rules are followed.
   - The agent panel's Rules group lists them, with "{n} off" and "Edit rules".
   - Connector: the next message follows the rules.
4. **[notes on]** Turn on the switch; the off message disappears.
   - Ask the agent to save a fact; the tool stream shows `save_note`.
   - Check whether the agent panel updates (**item (a)**).
   - Check the post-save reply for commentary (**item (e)**, the open
     criterion).
5. **[untrusted note]** Fetch a page that carries a planted instruction, or
   send a peer message.
   - The note shows "Check this" with its sources.
   - Review the badge copy and decide on **item (d)**, the operator clearing a
     flag.
6. **[rule beats note]** Use a stronger probe than step 8 of the behavior
   test (**item (f)**).
7. **[prune]**
   - Edit a note in the tab: "Edited by you" appears.
   - Delete from the panel (focus behaviour, **item (b)**).
   - Clear all through the dialog.
8. **[off keeps]** Turn notes off.
   - The notes are hidden from the agent and kept.
   - Observe **item (i)** (the filesystem fallback) and decide on a follow-up.
9. **[agent lifecycle]** Rename the agent: rules, notes and self-configuration
   history follow. Delete it: everything is removed.
10. **[judgement calls]** Go through the list in Flight 2's log and confirm or
    reverse each call.

### Checkpoints
- [ ] Walk complete with no open blocking findings.
- [ ] The open criterion is settled.
- [ ] Every judgement call is confirmed or reversed, recorded in the flight
      log.
- [ ] Gate green after the HAT fixes, and both behavior specs re-run if their
      contracts changed.

---

## Post-Flight

### Completion Checklist
- [ ] HAT leg completed
- [ ] Fixes committed, with the PRs updated
- [ ] Mission criteria final; mission debrief scheduled

### Verification
- The operator's sign-off on the walk.
- `make gate` green.
- The behavior specs re-run if touched.
