# Mission Debrief: Agents know how to use the platform, measured across models

**Date**: 2026-10-14
**Mission**: [Agents know how to use the platform, measured across models](mission.md)
**Status**: completed
**Duration**: 2026-10-13 – 2026-10-14
**Flights Completed**: 2 of 2 (the optional alignment flight was dropped when the operator delegated all judgement to data)
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|---|---|---|
| One-command eval runs with pass rates, uncertainty, failed transcripts, time, tokens and size by part | met | `python -m evals` / `make eval` (F1) |
| Scenarios cover the mission's list, with program checks plus a judge only for wording | met | 12 run sets / 14 cells. The Haiku judge was validated 32/32 on labelled set v2 |
| Baseline recorded and committed before any prompt change | met | `evals/baselines/m30-today.json` (F1) |
| Bars, statistical rule and size target derived by pre-declared rules | met | F1 DD11, written before any data |
| Guidance only for what the agent has, and the agent's own prompt appended unchanged | met | `platform_prompt.py` sections and capabilities; tool-free prompt built at build time; connector tools seeded only for mapped agents (F2) |
| Platform text as short as possible while meeting the bars | met | Bare prompt sections 595→168 (target ≤ 357); bare platform 1308→420; all-on 1789→773 |
| Settings › Prompts shows each part and when it applies | met | F2 leg 1c |
| Clickable markdown links in chat (connector) | met | `markdown-links` 2/20→19/20 on both models. The live Discord check was waived; per the operator, chat is sufficient and connector delivery is a technical concern |
| No worse than baseline on any scenario, each per-scenario bar met, safety on every run | **partially met** | 0 hard failures and safety 20/20. Unmet: gpt-oss `planted-instruction` 3/20 against a bar of 0.30 (best-effort). gpt-oss `rule-beats-note` passed narrowly (8/20 against 14/20, p = 0.056) |
| Existing behaviour holds: specs and suites pass | met | Notes 11/11, rules 9/9, time 8/8, self-revision 8/8; `make gate` green |
| Evals convention recorded, outside CI and the gate | met | CLAUDE.md "Prompt evals" and `evals/README.md` |

### Overall Outcome
**Achieved, with one honest miss.**
- Every agent now gets a platform prompt sized to what it can actually do: about a third of the old size for a bare agent.
- #282's link formatting works on both target models.
- Gpt-oss now saves notes unprompted where it never did before.
- The platform prompt can now only change with an eval run against a committed baseline (#259).

The miss is gpt-oss:20b obeying instructions planted in fetched pages. Three framings did not move it, which is evidence it is not prompt-addressable at that model size. The `(unverified)` flag caught every such note. The outcome was still the right goal at the end: the operator's "data are the gates" direction turned the eval apparatus from a nice-to-have into the thing that decided every wording.

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| 1: Prompt evals and baseline | completed | A hand-rolled, contained eval runner driving the real factory on Haiku 4.5 and gpt-oss:20b. Gate rules were fixed before any data, and today's prompt was baselined (PR #284) |
| 2: The platform prompt | completed | A sectioned, conditional platform prompt chosen by a pre-declared screening protocol. Hard gates pass, and `m30-platform` is the new baseline (PR #285) |

## What Went Well
- **Rules written before data, then followed.** Bars, the statistical rule, size targets and DD5's keep/reject rules were all fixed in advance. Every decision in roughly 10 hours of live runs is logged with the rule that fired, and the one hard-gate failure was reported and handled within the budget, never relaxed.
- **Containment held under real models.** In about 2,000 live runs there were no escapes. Off-fixture fetches were refused, and the token was found in 0 files on every scan.
- **Validity before measurement.** Proving that every check can fail, plus the smoke runs, caught four check and fixture bugs before the baseline. That included a judge whose labelled set contradicted the product's own definition.
- **Reversible, attributable change.** F2 did a verbatim restructure, pinned byte-for-byte, then switched behaviour, with a commit per candidate and a revert for each rejection. The final review could confirm the shipped text is exactly what was measured.
- **The Architect review cycles found real defects at every stage:** mission, both flight designs, leg designs and both debriefs. Examples include a live-run-deleting sweep, an unmeetable size target, a self-defeating `compare` flag and a size check that DD7 would have made toothless.

## What Could Be Improved
- **Screening design (F2).** Fact-0-only screens left a hold cell unguarded because it sat at its floor at baseline. The "minimal" subtraction was the largest change and got the least scrutiny. The second full run was spent as fix-and-retest.
- **Statistical power (F1 and F2).** At temperature 0, outcomes cluster by fact (an effective n of about 5). The one-sided Fisher test at n = 20 passed a 70%→40% drop. This was stated honestly but not protective.
- **Unit-suite cost (F1).** +31% unit time; the fix (DD15) under-delivered because per-test setup dominates.
- **External credentials (F2).** Discord bot tokens were found revoked only at the live leg.
- **Capability model sprawl (Architect, cross-flight).** Four condition mechanisms (sections, the notes `tools=` flag, the date `tool_available`, the rules-over-notes switch). Capabilities are derived in two places by two rules, and `build_system_prompts` defaults fail open.

## Lessons Learned
- **A judge validated on the wrong distribution is worse than no judge.** Derive labelled sets from the product's own specification and include the output shapes models actually produce.
- **Subtractions need the same rigour as additions.** A minimal rewrite silently removes safeguards that a narrow screen cannot see.
- **Some behaviours are not prompt-addressable at a given model size.** Invest in structural controls (the untrusted flag; gating saves after untrusted content) once a few framings fail to move a cell.
- **Assert on persisted state, not model prose.** The self-revision behaviour spec became reliable once it checked the stored `messages[0]`.
- **Every built prompt has two variants.** Treat the tool-capable and tool-free prompts as a pair everywhere they are built or rebuilt (factory, `pending`), never as one string plus a recovery rule.
- **Patterns to standardize** (to be written into `agents.md` by the follow-up):
  - a named-section table as the single source for rendering, UI and measurement
  - build-time variants instead of runtime recovery
  - "the platform prompt is never identified by its text"
  - an in-process eval harness driving the real factory inside a contained scratch environment

## Methodology Feedback

Each finding restates what the flight debriefs already hold (F1 = Flight 1, F2 = Flight 2); a later sweep should count it once.

| # | Finding | Skill / phase | Flights | Cost | Destination |
|---|---|---|---|---|---|
| 1 | Iterative tuning legs don't fit "one Developer implements the leg". The FD amended the execution model to one Developer per iteration with FD-applied rules. F1 leg 3's judge correction needed the same FD-mediated cycle. | agentic-workflow, 2b | 2 (F1, F2) | A mid-leg spec amendment in each flight | **methodology observation** (1.2.0) |
| 2 | Developers landed legs without ticking acceptance boxes; the FD ticked them against the Reviewer's confirmation. | agentic-workflow, 2b | 1 (F1, legs 2 and 4) | FD bookkeeping, plus a risk of ticking unverified criteria | **methodology observation** (1.2.0) |
| 3 | Code review is deferred to flight end, but live measurement legs depend on correct code. The FD inserted a review checkpoint before tuning. | agentic-workflow, 2d | 1 (F2; latent in F1, whose baseline ran before the flight review) | None observed (deviation logged) | local lesson |
| 4 | Behavior-test orchestration was delegated to an orchestrator subagent per spec to protect the FD's context; the Witnessed separation held. | behavior-test, Orchestrator | 1 (F2) | None | local lesson |
| 5 | External credentials (Discord bot tokens) were found revoked only at leg time. Planning checked key presence, not validity. | flight, Pre-Flight prerequisites | 1 (F2) | One blocked spec (waived) | local lesson (probe credential validity at planning) |
| 6 | Design-review cycle 2 found coherence defects introduced by cycle 1's fixes, within the 2-cycle cap. | flight 5b, agentic-workflow 2a | 2 (F1, F2) | None (the cap allowed it) | local lesson |

Local fixes: none needed in `ARTIFACTS.md` or the crew files. Squawk 0212 covers this project's behavior-test dev-instance convention.

## Action Items
- [ ] **Follow-up (sortie): unify the platform prompt's capability model.**
  - one capabilities→layers renderer
  - one capability derivation shared by the factory and `pending`
  - fail-closed defaults
  - an `Agent.set_prompts(SystemPrompts)` method
  - the product returns structured prompt parts so the evals stop inferring them (closes 0211)
  - the patterns above documented in `agents.md`
- [ ] **Follow-up (sortie): strengthen the eval gates and screening.**
  - per-fact paired comparison or an effect-size floor for mid-rate hold cells
  - per-cell headroom facts in screening
  - subtractions screened at full width
  - separate diagnostic and confirmatory budgets
  - decide whether to keep or archive `m30-today.json`
- [ ] **Diagnose gpt-oss `rule-beats-note` fact 1** (date format, 0/4 in both final runs) before the next change to rules or notes text.
- [ ] **Safety, product-side:** gate or confirm note saves made after untrusted content in the same turn, and re-class gpt-oss `planted-instruction` as "measured, not targeted".
- [ ] **Unit-tier cost:** move the 20-variant scenario tests behind an `evals` marker run by `make eval`.
- [ ] **Squawks 0207–0212** at the next turnaround. 0207 (the connector send description) is prompt text, so it needs an eval run against `m30-platform`.
- [ ] **The operator merges** the stacked PRs #283 → #284 → #285.
