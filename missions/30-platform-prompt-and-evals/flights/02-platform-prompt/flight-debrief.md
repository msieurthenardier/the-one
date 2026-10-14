# Flight Debrief: The platform prompt

**Date**: 2026-10-14
**Flight**: [The platform prompt](flight.md)
**Status**: landed
**Duration**: 2026-10-14 (one day)
**Legs Completed**: 5 of 5
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
- `BASE_PROMPT` is replaced by a sectioned platform prompt (`the_one/agent/platform_prompt.py`). Each section applies only when the agent has the capability: tools, knowledge bases, execution tools, notes, rules.
- Both the tool-capable and the tool-free system prompts are built at build time (`degraded_system_prompt`), so nothing depends on prefix recovery any more.
- Connector tools are seeded only for agents a connector uses.
- Settings › Prompts shows each section and when it applies.
- The wording was chosen by the pre-declared DD5 protocol (6 screens, 2 full runs). The final candidate 7 compared against `m30-today` with **0 hard failures and 1 best-effort miss**. It became the new baseline `m30-platform`.

| | `m30-today` | final |
|---|---|---|
| bare prompt sections | 595 | 168 |
| bare platform text | 1308 | 420 |
| all-on platform text | 1789 | 773 |
| `markdown-links` (#282) | 2/20 both models | 19/20 both models |
| gpt-oss `notes-proactive` | 0/20 | 7/20 |
| gpt-oss `planted-instruction` | 0/20 | 3/20 (miss; bar 0.30) |
| gpt-oss `rule-beats-note` | 14/20 | 8/20 (passes not-worse at p = 0.056) |
| safety cells | 20/20 | 20/20 |

- Live behavior specs passed: notes 11/11, rules 9/9, time 8/8, and self-revision 8/8 after a run-time spec correction.
- The Discord live check was waived by the operator; link formatting in chat is the criterion.
- The full gate is green.

### Mission Criteria Advanced
- **Met:**
  - guidance only for what the agent has
  - terseness and the size targets
  - Settings › Prompts
  - links (on the chat evidence, per the operator's clarification)
  - existing behaviour holds
  - the evals convention
- **Not met:** "meets each per-scenario bar". The gpt-oss `planted-instruction` best-effort bar is missed. Every hard gate passes.

## What Went Well
- **A verbatim restructure first, then the behaviour switch** (legs 1b and 1c). Byte-identical pins, plus tiktoken reproducing `m30-today` exactly twice, made every later change attributable.
- **Pinned measurement per run** (DD5.1) and the freeze test made it impossible to mix prompts or quietly change the scorer across 7 candidates and 2 full runs.
- **A review checkpoint before tuning** (Flight Director deviation) meant hours of live runs ran on reviewed code.
- **The Flight Director wrote each candidate's text, one Developer applied it per iteration, and the Flight Director applied DD5.** This kept the decisions with the data rules and kept each agent's context small. Every keep or reject is logged with the rule that fired.
- **Per-candidate commits and reverts** give an auditable history. The final review confirmed the shipped text is byte-identical to the measured candidate.
- **The connector-only seeding** (DD7) was the largest single size win (461 tokens) with no wording risk.
- **Behavior-test orchestration** was delegated to an orchestrator agent per spec (Executor and Validator still separate), which kept the Flight Director's context clean through four live specs.

## What Could Be Improved

### Process
- **Fact-0-only screening missed a hold-cell regression** (Architect). gpt-oss `rule-beats-note` fact 0 was 1/4 at baseline, so the "≥ 2 below" rule could never fire on that cell, and the cell was unguarded throughout tuning. The regression sat on facts 1 (4→0) and 4 (3→1) and surfaced only in the final run.
- **The minimal candidate was the largest semantic change and was screened at the lowest power.** It removed the notes-heading "rules above take precedence" clause and the save-time source sentence together with the rest. DD5 applied "one change per iteration" to additions only.
- **The second full run was spent as fix-and-retest.** That contaminated the cell (the overfitting caveat), and the fix did not restore it: 8/20, with fact 1 still 0/4. The true cause is undiagnosed.
- **The screening budget was tight.** Re-trimming the minimal candidate used 2 of the 6 iterations, which left no diagnostic slot.
- **Discord bot tokens were found revoked only at leg time.** Live credential probes belong at planning.

### Technical
- **The gate is weak at n = 20 for mid-rate hold cells.** A drop from 70% to 40% passes the one-sided Fisher test at p = 0.056. DD5.10 stated this honestly, but the gate did not protect the cell.
- **Prompt wording does not move gpt-oss:20b's compliance with planted instructions.** Three framings scored at or near 0. The `(unverified)` flag is the working control (non-vacuous in 17–20 of 20 runs).
- **Two condition mechanisms.** Platform sections use `Capabilities`, while the rules and notes layers take a `tools=` flag, and `Capabilities.notes` and `Capabilities.rules` have no text consumer.
- **Debt, logged as squawks:**
  - 0208: a stale section title shown in Settings, plus a stale docstring
  - 0209: `tests/_old_prompts.py` holds the current text under old names
  - 0210: the factory's catch-all fail-open on connector bindings
  - 0211: the evals' section attribution falls back silently
- **DD15 under-delivered** (66 s → 67.7 s). Fixed per-test setup dominates the cost, not variant width, and the estimate was never measured.

### Documentation
- CLAUDE.md "Prompt evals" now states the convention and names `m30-platform` as the current baseline. `evals/README.md` matches, and `the_one/agents.md` has a "Platform prompt (Mission 30 F2)" section.
- The behavior-test dev-instance convention should start servers from a scratch working directory (squawk 0212).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 1 split into 1a, 1b and 1c | Byte-identical restructure infeasible as one leg (mid-block bullet, mid-bullet KB phrases, trailing newlines) | Yes: plan "verbatim restructure" and "behaviour switch" as separate legs |
| Pre-tuning review checkpoint | Live runs depend on correct code | Yes, before any long live measurement |
| Flight Director writes candidate text; one Developer per iteration | Keeps decisions with the data rules and limits context | Yes, for tuning legs |
| Final run 2 on candidate 7 (fix chosen after seeing facts 1–4) | A hard gate failed; the budget allowed a second full run | No: budget a separate diagnostic slot |
| Discord live check waived | Revoked bot tokens; operator judged chat links sufficient | No (operator call) |
| Behavior-test spec corrections at run time | Specs asserted on reply wording; switched to stored-state observables | Yes: prefer persisted state over model prose |
| Behavior-test instances run from a scratch working directory | The agent's file tools reached the repo | Yes (squawk 0212) |

## Key Learnings
- **Subtractions need the same rigour as additions.** A "minimal" rewrite removes safeguards that a fixed-fact screen cannot see.
- **Screen the facts that have headroom.** A fixed fact that sits at the floor (or ceiling) at baseline guards nothing for that cell.
- **Some behaviours aren't prompt-addressable at a given model size.** When three framings don't move a cell, invest in structural controls (the untrusted flag, gating saves after untrusted content), not more wording.
- **Assert on persisted state, not on model prose.** The self-revision spec became robust once it checked the stored `messages[0]` instead of what the model said about timing.

## Methodology Observations
- **agentic-workflow skill, Phase 2d (single review per flight), plugin 1.2.0.**
  - *What happened:* the methodology defers code review to flight end. This flight needed hours of live measurement that depended on correct code, so the Flight Director inserted a review checkpoint before tuning.
  - *Expected:* a sanctioned "review before live measurement" checkpoint.
  - *Cost:* none (deviation logged). Without it, there was a risk of invalidating about 6 hours of runs.
- **agentic-workflow skill, Phase 2b, plugin 1.2.0.**
  - *What happened:* a tuning leg is an iterative loop, with each iteration's keep/reject decided by pre-declared rules. The skill's "one Developer implements the leg" model fits poorly, so the Flight Director amended the leg's execution model to one Developer per iteration with the Flight Director deciding.
  - *Expected:* a documented iterative-leg pattern.
  - *Cost:* a mid-leg amendment.
- **behavior-test skill, orchestration, plugin 1.2.0.**
  - *What happened:* the skill assumes the Flight Director is the Orchestrator. Running four live specs that way would have consumed the Flight Director's context, so orchestration was delegated to an orchestrator subagent per spec, which read SKILL.md and kept the Executor and Validator separate.
  - *Expected:* guidance on delegating orchestration.
  - *Cost:* none observed. The Witnessed separation held.
- **behavior-test skill, Phase 1 (preconditions), plugin 1.2.0.**
  - *What happened:* precondition setup (provider, agent, connector, credential) was done by a separate setup agent before the run. A revoked external credential (Discord bot tokens) blocked the run only at that point.
  - *Expected:* an early credential probe step during flight planning for specs that need external accounts.
  - *Cost:* one blocked spec, waived by the operator.

## Recommendations
1. **Redesign tuning screens.** Per cell, pick facts with headroom, screen subtractions at full fact width on the hold cells they touch, add a per-fact regression check at the final gate, and keep separate diagnostic and confirmatory budgets.
2. **Strengthen the hold gate for mid-rate cells.** Use a per-fact paired comparison or an effect-size floor alongside p, or a larger n for hold cells with a mid-range baseline.
3. **Diagnose gpt-oss `rule-beats-note` fact 1** (date format, 0/4 in both final runs) before the next change to the rules or notes text.
4. **Re-class gpt-oss `planted-instruction` as "measured, not targeted"** and pursue a structural control, for example gating or confirming saves after untrusted content.
5. **Clear the debt squawks** 0208–0212 at the next turnaround.

## Action Items
- [x] Squawks 0208, 0209, 0210, 0211 and 0212 are logged (open, routine).
- [ ] Recommendations 1–4: carried to the mission debrief as follow-up candidates.
