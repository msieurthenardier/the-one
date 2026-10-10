# Flight Debrief: HAT and Alignment

**Date**: 2026-10-10
**Flight**: [HAT and Alignment](flight.md)
**Status**: landed
**Duration**: 2026-10-10 (one live session with the operator)
**Legs Completed**: 3 of 3: `hat-and-alignment` (interactive), plus two legs
added mid-HAT, `drawer-read-only-notes` and `prompts-page-layers`
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
- **Walk:** the operator walked every planned step:
  1. the empty tab;
  2. rules authored;
  3. rules live in web and connector chats;
  4. notes switched on, a note saved, the panel;
  5. an untrusted note;
  6. rule beats note;
  7. pruning in the tab;
  8. notes off keeps notes;
  9. rename and delete;
  10. the judgement calls.
- **Judgement calls:** every autonomous call was settled. Most were
  confirmed; three were reversed or refined (the panel, the flag affordance,
  the prompt wording).
- **Open criterion:** "notes presented as notes" was closed in narrowed form.
  The no-"memory" vocabulary rule now covers operator-facing language only.
- **What the HAT delivered:**
  - a **read-only chat panel**: bulleted lists, no edit or delete controls,
    a warning-triangle flag with an explanatory tooltip, a "Pending · used
    from the next chat" section driven by a server-side comparison with the
    live prompt, and live refresh after notes tool calls;
  - the **same triangle in the tab**;
  - **an operator edit clears a note's untrusted flag** (only when the text
    changes);
  - **reworked notes prompt wording**: proactive and life-oriented, notes
    phrased as told, no secrets, no planted instructions, a plain-language
    "(unverified)" sentence;
  - **Settings › Prompts shows every prompt layer**, rendered by the real
    functions.
- **Follow-up:** prompt evals are tracked as #259.

### Mission Criteria Advanced
- "Notes are presented as notes, not instructions" is closed.
- The operator confirmed every criterion previously ticked from automated
  evidence.

## What Went Well
- **The fix-vs-feature gate worked live.**
  - Two features were routed to designed, reviewed legs. Leg 2's design
    review produced binding amendments before any code: a DOMParser icon,
    render-side `pending`, a guarded live-session read, and a tool-name map.
  - Wording and look-and-feel changes went inline.
  - The walk never stalled; non-dependent steps continued while Developers
    built.
- **Mockups before building:** five panel options (A-E) rendered with real
  app CSS at real width settled a contested design in two exchanges.
- **Drift-proof examples:** the Prompts page examples are rendered by
  `render_rules_block` and `render_notes_block`, and a test asserts they
  appear verbatim in a composed prompt.
- **Shared DOM icon helpers** (`App.iconNode`, `App.noteFlag`) avoid HTML
  sinks across the panel and the tab.

## What Could Be Improved

### Process
- **Stale browser JavaScript caused a false failure.**
  - **What happened:** at step 4b the operator saw the old panel twice. The
    asset `?v=` changes only with the package version, so an edited file is
    cached.
  - **Cost:** two extra sign-ins and a headless verification to prove the
    server was correct.
  - **Fix:** a HAT preflight should curl the served asset or use a private
    window. Squawk 0085 covers the root cause.
- **Restarts invalidate the one-time handoff link and sign the operator
  out.** Six links were minted. Batching Python changes before re-verifying,
  and handing out two links at a time, helped.
- **Live small-model reliability.** `gpt-oss:20b` did not take the planted
  bait (step 5) and did not save proactively (step 4c), so step 5 needed a
  Flight-Director-seeded flagged note. Security-path checks need seeded
  fixtures; model behaviour belongs in evals (#259).
- **Bookkeeping:** decisions were recorded as Leg Progress narrative rather
  than in the log's Decisions section. Future HATs should mirror each operator
  decision into Decisions.

### Technical
- **`pending` couples the API to the rendered prompt format.**
  - `parse_notes_block` must change whenever `render_notes_block` changes.
  - `pending_known: false` is a graceful fallback.
  - A prompt hash or version stamp on the session would be sturdier.
- **Layering smell:** `api.py` lazily imports `_sessions` from `app.py` for
  the live session read. This is the established pattern, but a candidate for
  an injected accessor.
- **Review coverage:** the two wording rounds, the Prompts page and the
  bullets were covered by one final Reviewer pass. That pass was
  independent, but after the fact rather than per change.

### Documentation
- `agents.md`, CLAUDE.md and `SECURITY-MODEL.md` (the flag lifecycle) are
  updated.
- The agent-wording policy is recorded in the mission and here: no "memory"
  vocabulary in the operator UI only.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Two feature legs added mid-HAT | Operator feature requests (panel redesign, Prompts page) | Yes: the fix-vs-feature gate with a quick design review |
| Flagged note seeded through the stub peer | The live model didn't take the planted bait | Yes: seed security fixtures for HATs |
| Behavior specs re-authored after the HAT | The panel contract changed (DD2) | Yes, as the plan specified |
| HAT instance restarted per Python change | No reload in `serve` | Batch Python changes; mint links in pairs |

## Key Learnings
- **Operators judge UX and wording, not mechanics.** Every reversal at the HAT
  was UX or copy, and the security mechanics were confirmed unchanged.
  Autonomous runs should treat UX and copy as provisional and get a mockup
  review before building.
- **Showing a "pending" state beats explaining why.** The Pending section
  answered the operator's "no notes yet?" confusion without any text.

## Methodology Observations
- **Interactive HAT legs absorb mid-session feature work as separate legs.**
  - **What happened:** agentic-workflow 2b's fix-vs-feature gate handled it,
    and the legs were reviewed and gated.
  - **Friction:** the interactive leg stays `in-flight` while other legs open
    and land beside it. The leg list in `flight.md` (written at planning)
    went stale until landing.
  - **Cost:** artifact bookkeeping only. *Skill: agentic-workflow 2b
    (interactive legs). Plugin 1.2.0.*
- **The HAT walk assumed a live small model would exercise agent-behaviour
  paths.**
  - **What happened:** two steps needed a fallback (seeding) or were accepted
    as model limits.
  - **Expected:** the flight skill's HAT guidance might suggest seeding
    fixtures for agent-behaviour steps.
  - **Cost:** about 10 minutes and one improvised seed. *Skill: flight (HAT
    planning). Plugin 1.2.0.*

## Recommendations
1. **Add a HAT preflight step: verify the served asset bytes** (or use a
   private window) before judging any UI change, and/or fix cache-busting
   (squawk 0085).
2. **Seed fixtures for agent-behaviour HAT steps** (an untrusted note, a
   conflicting note) rather than relying on model compliance.
3. **Treat the notes prompt format as a contract:** keep `render` and `parse`
   together, and consider a prompt version stamp for `pending`.
4. **Run #259 (prompt evals) before the next prompt-wording change.**

## Action Items
- [ ] #259: prompt evals (future mission or sortie).
- [ ] Squawk 0085, existing: make the asset cache-busting content-based.
- [ ] Consider injecting a session accessor instead of the lazy `_sessions`
      import (next maintenance pass).
