# Flight Debrief: Notes

**Date**: 2026-10-10
**Flight**: [Notes](flight.md)
**Status**: completed
**Duration**: 2026-10-10 (planning) - 2026-10-10 (landed; behavior test 11/11)
**Legs Completed**: 3 of 3
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved

Every agent gained an operator-controlled notes surface, off by default:
- **Store and switch:** the v43 store, an operator-owned switch, and REST.
- **Prompt block:** a bounded "notes, not instructions" block beneath the
  rules.
- **Tools:** `save_note`, `update_note` and `forget_note`, registered outside
  the built-in whitelist and seeded into the baseline.
- **Provenance:** origin plus an untrusted-content flag over the whole
  conversation, computed from the bound Agent's messages with a backwards
  anchor and positional attribution (Ollama ids repeat across turns).
- **Limits:** limits and de-duplication.
- **UI:** a Notes section in the tab and a Notes group in the panel.
- **Docs:** the "Agent notes" section of `SECURITY-MODEL.md`.

`core.py` stayed untouched: the pre-declared split risk never materialised.

**Contract:** `test_planted_instruction_never_yields_an_unflagged_note` was
falsified against a broken taint check and a forward anchor.

**Live behavior test:** `agent-notes-round-trip` passed 11/11 on
`gpt-oss:20b`. The model obeyed the planted page, the note was flagged, and a
rule still won.

### Mission Criteria Advanced
- **Ticked at landing:**
  - "keeps notes across conversations";
  - "operator's to see and control";
  - "off by default";
  - "rules outrank notes";
  - "bounded";
  - "injected content cannot plant a note unnoticed";
  - "rules and notes follow it";
  - "UI says when changes apply".
- **Left open for the HAT:** "notes presented as notes", the only criterion
  left open. Flight 3 closed it in narrowed form.

## What Went Well
- **The security spine needed no HAT revision.** The taint rule, the trusted
  set, the fail-closed switch re-check, the update OR, and one-line
  normalisation plus delimiter neutralisation all held. This was the
  high-risk part, and it got two Architect cycles plus a per-leg Developer
  review.
- **Design reviews caught real security defects before any code existed:**
  - repeated Ollama tool-call ids, which a forward anchor would have let
    through as an unflagged planted note;
  - newline injection forging a `[n]` line;
  - `update_note` laundering a flag;
  - the REST `/api/chat` path missing a context set site.
- **An early backend security review ran in parallel with the UI leg,** so the
  UI wait wasn't idle and the backend had a confirmed review before the UI
  landed.
- **Gate:** green and within every lane budget (about 18.2 min) after Flight
  1's over-budget run.

## What Could Be Improved

### Process
- **UX and copy were marked "autonomous judgement call" but shipped as
  final.** The HAT then reworked the panel (read-only, Pending, live
  refresh), the flag (triangle icon), the flag lifecycle (an operator edit
  clears it) and two rounds of prompt wording. Mockups (A-E) settled the panel
  in minutes at the HAT. A mockup review **before** building leg 3 would have
  saved about 500 lines of drawer JS and tests that were rewritten.
- **Model-behaviour expectations went unprobed:**
  - the overnight wording was never tried against a live model before
    landing;
  - the behavior spec's step 8 probe ("Hello!") was too weak to show
    rule-beats-note;
  - proactive saving was never exercised.

### Technical
- **The flag lifecycle was half-designed:** set, OR and display, but no clear
  path, so it could only ratchet. Flight 3 added "operator edit clears it".
- **The panel showed notes as of when it opened,** so saves in the open chat
  were invisible. Flight 3 added live refresh and the server-side `pending`
  field.
- **`rules-notes-tab.js` is about 700 lines.** It is a split candidate,
  related to #207 (the editor shell).
- **`agents` lane at 428 s of 510 s (84%):** the notes tab tests live there.

### Documentation
- `agents.md` covers the taint rule and the tools. The "operator edit clears
  the flag" and `pending` contracts were added in Flight 3.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Notes helpers in `db/_notes.py`, not `the_one/notes/limits.py` | The `agent`-package-to-repositories import cycle, as with Flight 1's `_rules.py` | Yes: name the `db/_*.py` placement pattern in `agents.md` |
| The web set site moved into `_process_and_broadcast` | DD5 missed the REST `/api/chat` path | Yes: one set site per `step` call, not per transport |
| An early backend review in parallel with the UI leg | Use idle time; no file overlap | Yes, when the legs do not share files |
| The Flight Director seeded the HAT's flagged note through the stub peer | The live model did not take the planted bait that time | Yes: seed security-path fixtures, don't rely on model compliance |

## Key Learnings
- **The prompt text is a product surface.** It needs operator review against a
  live model, the way UI copy does. Evals are now tracked in #259.
- **Design a flag's whole lifecycle at once:** setting it, displaying it, and
  clearing it.
- **"Which notes are in this chat's prompt" is a real user question.**
  Showing current notes in a chat whose prompt is older misleads.

## Methodology Observations
- **Two Architect cycles plus per-leg design reviews.**
  - **What happened:** the flight skill's design-review phase and the
    agentic-workflow's leg design review produced about 12 substantive
    corrections across DD5, DD6, DD8, DD9 and DD11 before any code. The
    implementations then landed first time with no blocking review findings
    on the backend.
  - **Note:** this is positive evidence, worth keeping as a reference point.
    *Skill: flight Phase 5b and agentic-workflow 2a. Plugin 1.2.0.*
- **Autonomous judgement calls on operator-visible UX are not held back.**
  - **What happened:** the methodology lets autonomous judgement calls on
    operator-visible UX flow straight into implementation, with review only
    at the HAT. With the operator away, the Flight Director built UX the
    operator then redesigned.
  - **Expected instead:** a "provisional, needs operator mockup review" state
    for UX DDs, gating the UI leg.
  - **Cost:** about 500 lines rewritten in Flight 3, plus a feature leg with
    its own design review. *Skill: flight and agentic-workflow, under
    autonomous operation. Plugin 1.2.0.*

## Recommendations
1. **Gate operator-visible UX decisions on a mockup review before building,**
   even in autonomous runs. A screenshot mockup took minutes at the HAT.
2. **Design trust flags end to end:** set, display and clear, plus which
   surfaces render them.
3. **Probe model behaviour before landing any prompt wording** (#259 tracks
   evals).
4. **Split or rebudget the `agents` lane** before adding more notes and rules
   UI tests.

## Action Items
- [ ] #259: prompt evals across models (operator, future mission or sortie).
- [ ] Name the `db/_*.py` placement convention in `agents.md` (next
      maintenance pass).
- [ ] `agents` lane headroom: split `test_flow_agent_notes.py` and
      `test_flow_agent_rules.py` into a lane, or rebudget (next maintenance
      pass).
