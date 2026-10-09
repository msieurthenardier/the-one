# Flight Log: Rules and the Prompt Foundation

**Flight**: [Rules and the Prompt Foundation](flight.md)

## Summary

Planned 2026-10-09 while the operator was away overnight, under their
authorization to plan and execute up to the mission HAT, making judgement calls
along the way. Autonomous judgement calls are marked in the flight's Design
Decisions and gathered here for review at the HAT (Flight 3).

---

## Leg Progress

---

## Decisions

### Autonomous judgement calls (for HAT review)

- **DD4:** rule limits of 500 characters per rule and 4,000 characters in
  total, with disabled rules counted.
- **DD5:** the prompt wording for the rules layer, with "the earlier rule wins"
  on conflict.
- **DD6:** the tab is labelled "Rules and notes" and sits second, after
  General. Its controls save immediately. Rules are reordered with Move up and
  Move down buttons.
- **DD7:** the chat agent panel's Rules group lists the enabled rules in order,
  plus "{n} off" and an "Edit rules" link.
- **DD9:** the behavior test uses the local Ollama provider and reads the stored
  session's system message as its composition read path.
- **DD6 (from the design review):**
  - Unsaved text in Add rule or an inline edit is not guarded by the leave
    prompt, as on the Self-configuration tab.
  - If "Rules and notes" overflows the tab strip at 1024 px, the label falls
    back to "Rules".
- **DD2 (from the design review):** if loading the rules fails at turn settle,
  the prompt is composed without rules and the turn completes.

### Design review (2026-10-09)

- **Verdict:** approve with changes, after one cycle. Every point was applied
  to the spec.
- **What changed:**
  - the v42 self-reference now names the final table, with a guard on
    `PRAGMA foreign_key_list`;
  - DD2 states what happens on failure at settle, and how it gets its
    connection;
  - the existing tests that pin the bug and the tab tests are named;
  - `get_system_prompt` is deleted;
  - the drawer helper's limits and the 404 case are covered;
  - the behavior spec's preconditions are corrected.
- **Why no second cycle:** the changes add detail to existing decisions and do
  not restructure them.

---

## Deviations

---

## Anomalies

---

## Session Notes
