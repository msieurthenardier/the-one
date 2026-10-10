# Mission Debrief: Agent Notes and Rules

**Date**: 2026-10-10
**Mission**: [Agent Notes and Rules](mission.md)
**Status**: completed
**Duration**: 2026-10-09 to 2026-10-10
**Flights Completed**: 3 of 3
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|---|---|---|
| Rules shape new conversations | **Met** | `agent-rules-round-trip` passed 9/9 twice: after Flight 1, then re-run after the HAT's panel re-author. Sentinel replies came back in web and connector chats. The disabled rule was absent. The operator watched it live at the HAT. |
| The agent keeps notes across conversations | **Met** | `agent-notes-round-trip` passed 11/11 twice, after Flight 2 and after the HAT. `save_note` showed in the tool stream, and a fresh chat recalled the note. |
| Notes are the operator's to see and control | **Met, with the panel redesigned at the HAT** | **The tab** lists each note with its time, origin chat and peer. It edits, deletes and clears all through a confirm dialog. **The chat panel** is now **read-only** by operator decision, overriding #230's "remove from the panel" wording. It shows bullets, the flag, and a Pending section, and it refreshes live. |
| Off by default, and off loses nothing | **Met** | v43 defaults the switch to off. Live step 10: with notes off there is no notes block and there are no notes tools, and the rows are kept. Writes from an already-built agent are refused when they run. |
| Rules outrank notes; the agent cannot touch rules | **Met** | No rules tool exists. The rule is placed first with an explicit precedence sentence, and a planted "pirate speak" note lost to a rule in both live runs. |
| Notes are bounded | **Met** | Limits: 400 characters per note, 4,000 in total and 5 writes per turn. Duplicates are de-duplicated, and a refused write reaches the agent as an error with corrective text. Covered by the unit tier. |
| Notes are presented as notes, not instructions | **Met in narrowed form** | The structure was met in Flight 2. At the HAT the operator accepted a short acknowledgement after a save. The operator also narrowed the no-"memory" vocabulary rule to **operator-facing** language. The prompt wording was reworked twice with the operator. |
| Injected content cannot plant a note unnoticed | **Met** | The contract test covers 8 untrusted tools × 3 timings, plus repeated and bare tool-call ids. It was falsified against a broken taint check and a forward anchor. **Live:** the model obeyed the planted page in both runs, and both times the note was flagged `fetch_url` and the rule still won. |
| An agent's rules and notes follow it | **Met** | v42 and v43 cascade on rename and delete. This also fixed the pre-existing rename failure for agents with revision history. Upgrades from populated v41 and v42 databases are tested. |
| The UI says when changes apply | **Met** | The tab states when a change applies. The panel's Pending section ("used from the next chat") shows it directly rather than explaining it. |

### Overall Outcome

The mission delivered its outcome: an agent now carries operator rules and its own saved notes into every new conversation, in the app and in connector channels. The operator can always see what was saved, where it came from, and whether untrusted content was in play. Both pre-existing bugs the mission found were fixed at the root:
- renaming an agent that has revision history;
- a `next_turn` self-revision dropping the base prompt.

The goal was still right at the end. What changed at the HAT was the **presentation**, not the mechanics:
- a read-only panel;
- a warning-triangle flag with a tooltip;
- a Pending section;
- an operator edit clearing the flag;
- the prompt wording;
- every prompt layer shown on Settings › Prompts.

The security spine (taint attribution, the trusted set, OR-on-update, one-line normalisation, the fail-closed switch) went through the HAT unchanged.

**The weak spot is model behaviour, which this mission could not settle:**
- `gpt-oss:20b` did not save proactively;
- it obeyed planted instructions (the flag held);
- with notes off, it sometimes hunts the filesystem.

Evals across models are tracked as #259.

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| [01 Rules and the prompt foundation](flights/01-rules-and-prompt-foundation/flight.md) | completed | **Rules:** v42 rules, plus `agent_revisions` rebuilt with a cascade. **Prompt composition:** one composer and one async loader shared by the factory and `next_turn`. **UI:** the Rules and notes tab (Rules section) and rules in the chat panel. **Behavior test:** 9/9. The gate ran over budget, about 80% of it host contention. ([debrief](flights/01-rules-and-prompt-foundation/flight-debrief.md)) |
| [02 Notes](flights/02-notes/flight.md) | completed | **Store and tools:** the v43 store, the switch, and three bound tools outside the whitelist. **Provenance:** across the whole conversation, with a backwards anchor. **Limits:** limits and de-duplication. **UI:** the Notes section and the panel group. **Security:** a `SECURITY-MODEL.md` section. **Behavior test:** 11/11. The pre-declared split point never fired, and `core.py` was untouched. ([debrief](flights/02-notes/flight-debrief.md)) |
| [03 HAT and alignment](flights/03-hat-and-alignment/flight.md) | completed | **The walk:** one live walk with the operator. **Gate:** two feature legs went through it (a read-only panel with Pending and live refresh; the Prompts page showing every layer). **Inline:** two rounds of wording changes. **Judgement calls:** every call was settled. **Specs:** both behavior specs were re-authored and re-run green. ([debrief](flights/03-hat-and-alignment/flight-debrief.md)) |

**Squawks logged during the mission:**
- 0166: the `revertMs: 50` lapse test is flaky under load.
- 0167: CLAUDE.md's unit skip count is stale.
- 0168: the jump-to New chat test is flaky under load.
- 0169: a `#chats/~new/{agent}` hash navigation auto-joins the latest chat. Found by the notes re-run's Executor.

**Follow-up issue:** #259, prompt evals across models.

## What Went Well

- **One composer, one loader.** Collapsing two prompt compositions into `compose_system_prompt` plus `build_system_prompt` fixed one bug and closed a class of drift. Flight 2 then added notes with no signature change, and the HAT's Prompts page renders its examples through the same functions, pinned by a test.
- **Design reviews paid for themselves on the security work.** Before any code existed, two Architect cycles plus per-leg reviews caught four gaps:
  - repeated Ollama tool-call ids, which a forward anchor would have let through as an unflagged planted note;
  - newline injection forging a `[n]` line;
  - `update_note` laundering a flag;
  - a missing taint set site on the REST path.

  The backend then landed with no blocking review findings.
- **The cascading foreign-key recipe** (rebuild guarded by PRAGMA, a correct self-reference, tests on fresh and populated databases) was written once in v42 and reused unchanged in v43.
- **The fix-vs-feature gate worked live.** Mid-HAT requests became reviewed legs while the walk continued. Mockups (A-E) rendered with real CSS settled the panel in two exchanges.
- **Falsify-then-revert contract tests.** The planted-note contract was shown to fail against a broken implementation before it was trusted.

## What Could Be Improved

- **Autonomous UX shipped as if final.** The overnight run made operator-visible UX and copy calls (the panel, the flag affordance, the prompt wording) and built them in full. The HAT reworked all three, rewriting about 500 lines of panel JS and tests. A screenshot mockup at planning would have cost minutes.
- **Prompt wording was never tried against a live model before landing.** Proactive saving, rule-beats-note strength and the post-save acknowledgement were first seen at the behavior test or the HAT.
- **Gate timing and stability:**
  - Flight 1's gate ran over its 20-minute target. That was mostly host contention, but the `agents` lane now sits at about 84-90% of its budget.
  - Load-sensitive one-off flakes appeared in `shared` (squawks 0166 and 0168).
- **HAT friction:**
  - Stale cached JavaScript made the operator see the old panel twice. Asset `?v=` is the package version (squawk 0085).
  - Each Python restart signed the operator out, and six handoff links were minted.
- **Debt carried forward:**
  - `pending` couples the API to the rendered notes block (`parse_notes_block` must track `render_notes_block`).
  - `api.py`'s lazy `_sessions` import.
  - `rules-notes-tab.js` is about 700 lines (related to #207).
  - The drawer's rules and notes fetches bypass `App.store`.

## Lessons Learned

- **The prompt text is a product surface.** Review it with the operator against a live model, the way UI copy is reviewed, and measure it with evals (#259) before the next change.
- **Design a trust flag's whole lifecycle at once:** set, display, clear, and every surface that renders it. Flight 2 shipped a flag that could only ratchet.
- **"Which notes are in this chat's prompt" is a real user question.** Showing current state in a chat whose prompt is older misleads. A Pending state answered it without explanation.
- **Seed fixtures for security-path checks.** A small live model's compliance varies run to run, so HAT steps that need a planted or conflicting note should seed it rather than hope for it.
- **Place shared constants where the import graph allows.** Constants that repositories need live in `db/_*.py` (`_rules.py`, `_notes.py`). The planned `the_one/agent/rules.py` would have created an import cycle.
- **Set taint once per `step` call, not once per transport.** The REST path was nearly missed because set sites were planned per transport.

## Methodology Feedback

| # | Finding | Flights | Destination |
|---|---|---|---|
| 1 | **Autonomous UX judgement calls flow straight to implementation.** | F2 (raised), F3 (paid) | Methodology observation |
| 2 | **Low-risk tiering of UI legs does not predict review cost.** | F1 | Methodology observation |
| 3 | **HAT planning assumes a live model will exercise agent-behaviour paths.** | F3 | Methodology observation |
| 4 | **The interactive HAT leg's leg list goes stale** when feature legs are added mid-session. | F3 | Local lesson |
| 5 | **The Bash tool's background timeout can't contain the full gate.** | F1, F2, F3 | Local fix |
| 6 | **The HAT preflight should verify the served asset bytes.** | F3 | Local fix |
| 7 | **Two Architect cycles plus per-leg reviews on the security work** (positive evidence). | F2 | Reference point |

These restate the flight debriefs' observations; a sweep should count each once.

### 1. Autonomous UX judgement calls flow straight to implementation
- **What happened:** UX decisions made while the operator was away were marked *(autonomous judgement call)* and built in full. The HAT then reversed them.
- **Expected:** a "provisional, needs a mockup review" state that gates the UI leg.
- **Cost:** about 500 lines rewritten, plus one feature leg with its own design review.
- **Skill:** flight, and agentic-workflow under autonomous operation. Plugin 1.2.0.
- **Recurrence:** raised in F2, paid in F3.

### 2. Low-risk tiering of UI legs does not predict review cost
- **What happened:** a UI leg with focus and announcement behaviour was tiered low-risk. Review then needed three cycles, and the third found a blocker.
- **Cost:** two extra fix and review rounds, about 25 minutes.
- **Skill:** agentic-workflow 2a. Plugin 1.2.0.
- **Recurrence:** F1. F2's UI leg was tiered high and did not recur.

### 3. HAT planning assumes a live model will exercise agent-behaviour paths
- **What happened:** two walk steps needed a seeded fixture, or were accepted as model limits.
- **Cost:** about 10 minutes and one improvised seed.
- **Skill:** flight (HAT planning). Plugin 1.2.0.
- **Recurrence:** F3. F2's behavior test had the same exposure but happened to pass.

### 4. The interactive HAT leg's leg list goes stale (local lesson)
- **What happened:** feature legs were added mid-session, and the leg list in `flight.md` was out of date until landing.
- **Cost:** bookkeeping only, so this stays a local lesson.
- **Skill:** agentic-workflow 2b. Plugin 1.2.0.

### 5. The background timeout can't contain the full gate (local fix)
- **What happened:** the full gate runs longer than the Bash tool's background timeout.
- **Fix:** detach the gate with `setsid nohup`, and record this in the project's crew files and CLAUDE.md.

### 6. The HAT preflight should verify the served asset bytes (local fix)
- **What happened:** stale cached JavaScript caused a false HAT failure.
- **Fix:** add a check of the served asset bytes, or use a private window, to the project's HAT guidance. Squawk 0085 covers the root cause.

### 7. Two Architect cycles plus per-leg reviews (reference point)
- **What happened:** about 12 substantive corrections came before any code, and the backend landed first time.
- **Note:** this is positive evidence for the review depth on high-risk security work. It is recorded as a reference point, not a defect.
