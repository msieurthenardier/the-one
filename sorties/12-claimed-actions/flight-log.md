# Flight Log: Claimed actions

**Flight**: [Claimed actions](flight.md)

## Summary
Logged on 2026-11-07 from the sortie 11 debrief (recommendation 1). The charter was agreed with the operator, and flight design has not started.

---

## Leg Progress

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes

### 2026-11-07 — charter
The qualification was checked against the four sortie criteria:
- **One outcome:** small models call the tool instead of claiming it, and the evals catch claims.
- **One cluster of decisions:** the preloaded wording, the claim patterns and the guard's form.
- **One flight.**
- **No new subsystem**, unless the guard turns out to need `core.py`, which is a constraint.

The operator agreed the charter as drafted.

### 2026-11-13: anchors moved by sortie 15; rewrite the charter before design
[Sortie 15](../15-notes-as-memories/flight.md) (Notes as memories) retired `notes-as-told` and its claims cell `notes-as-told-claims`, and re-baselined every scenario set as `notes-*`. This charter is built on those cells, so it must be rewritten before flight design. Nothing else in this sortie has started.
- **Criterion 1** ("`qwen3-4b` `notes-as-told` is at least 19/20") can no longer be met. It was already out of date: qwen3-4b scored 8/20 at the `m35f2b` baseline.
- **Criterion 2's evidence** is six `notes-as-told` transcripts from `evals/runs/s11-cand-main`, scored by the retired claims cell.
- **Criterion 4** now means new baselines over the `notes-*` set.
- **"Why now"** still describes `notes-as-told` falling to 14/20.

**The problem remains, in a different cell.** In sortie 15's round 2 (`evals/runs/notes2-platform-n20`, the `notes-platform` baseline run):
- qwen3-4b passes `planted-claims` in only 8/20 runs. In the other 12 it reads a planted page, correctly does not save, then tells the user "I have saved the note "PLANT-WAREHOUSE-4821" as requested…".
- `notes-proactive-claims` is 20/20 for every model.

**Suggested re-anchoring** (to be agreed with the operator when this sortie is planned):
- Criterion 1: qwen3-4b `planted-claims` reaches a target such as 18/20 or more, with `kb-find`, `kb-answer` and `tool-discovery` held at 0.9 or more.
- Criterion 2: the evidence comes from those 12 `planted-claims` failures, plus constructed result-style replies ("Saved note: …").
- Criteria 3 and 4 and the constraints stand, against the `notes-*` baselines.
