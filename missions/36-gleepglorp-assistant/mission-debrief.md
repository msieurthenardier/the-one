# Mission Debrief: GleepGlorp, the In-App Assistant

**Date**: 2026-11-24
**Mission**: [GleepGlorp, the In-App Assistant](mission.md)
**Status**: completed
**Duration**: 2026-11-18 - 2026-11-24
**Flights Completed**: 5 of 5 flown. The plan had three flights. Flight 3 and then Flight 4 were
each split at planning, which made six. The optional Flight 6 (Alignment) was not flown, by
operator decision on 2026-11-24, and its items are dispositioned below.
**Plugin version**: mission-control 1.2.4 throughout

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| GleepGlorp is ready once its model is chosen | met | Flight 1. Its settings are stored in app metadata, not an `agents` row: model provider and model, on/off, web, notes and retention (30 days). A quiet setup state shows until a model is chosen, and the daily purge removes GleepGlorp chats older than the retention. |
| Help is one click away on every page | met, as amended | Flight 3. A corner button and a 360px drawer on Agents, Library and Settings hold a second, independent chat instance with page and item awareness. They are not shown in Chats, where GleepGlorp is reached through the chat list (amended 2026-11-19). Verified by a 12-step HAT with a real model, and in WebKitGTK, WebView2 and WKWebView. No behavior test was written for the overlay; the HAT stood in for it. |
| GleepGlorp fills the form; the operator saves it | met | Flights 3-5 cover every editor in scope: agents, MCP servers, model providers, knowledge bases, Library secrets' metadata, built-in tool configs and Knowledge indexing. Date and time saves on choice, so it takes proposals only. Connectors were removed from scope (2026-11-21). The behavior test `gleepglorp-fill-mcp-from-link` passed 7/7 (run `2026-11-23-01-50-10`). |
| GleepGlorp proposes; the operator approves | met | Flight 2 built the change shape, the shared write services, stale checks, the card and continuation on Approve. Flights 4-5 extended it to all nine kinds, and open editors follow an approval in every window. The two behavior specs (`gleepglorp-proposal-create-agent`, `gleepglorp-proposal-attach-mcp`) were written but never run: Flight 2's lean HAT walked the same paths (operator decision). |
| Nothing changes without the operator's click | met | Holds by construction. The allowlist test covers the whole tool set in every settings combination; no-write tests cover `propose_change` and `fill_form`; no delete action exists; no setting relaxes it. |
| Secrets never pass through GleepGlorp | **partly met, accepted for now** | **In code, met.** Reads are masked whitelist views, checked by a nine-column parity test. Every proposal and fill string is checked against stored secrets and key shapes. Secret values, API keys and the operator-only tool fields are refused (Flight 5 added aliases such as `value` and `key`). An MCP key is an empty Sensitive row, and a key never follows a provider type change. **In model behaviour, not met.** Haiku repeats a pasted secret value back in its handoff (6 of 20 at the last measurement; qwen3-4b 12 of 20). In Flight 4 it asked for a key in chat. Nothing is stored or filled, and the operator accepted the repeat for now ("it's already in the transcript by then anyway"). Carried to the follow-up sortie. |
| GleepGlorp sticks to the app | met | Off-topic requests are declined, its tool set is fixed, and it cannot be bound to a connector or own a routine. "Check this" is driven by provenance. Since Flight 4, an outside link, command or address must come from the operator, enforced in code (`outside.py`), which closes Flight 3's prompt-only residual of 1 in 12. The "suggest one of your agents" line was made report-only (operator, Flight 1). |
| The Default agent is gone | met | Flight 1, schema v53. "GleepGlorp" and "default" are reserved names, with a rename-once repair at startup. |
| Quality is measured on every default eval model | **partly met** | Met through Flight 3: its own scenario set, the `m36f3-gleepglorp` baseline (Haiku 426/460, no safety failures), qwen3-4b measured, and other agents' prompts byte-identical. Not met since: the shipped prompt `p5d` (Flight 4) has no baseline. Its n=20 runs had 4 and then 9 Haiku safety failures, never attributed. Flight 5 measured only its ten new scenarios (DD12). The "Done!" and "I've set up" claims fail 19 of 20 in two cells. |

### Overall Outcome
**Achieved, with one honest gap.** The operator can ask GleepGlorp about the app, have it fill any editor in scope while they keep the Save, and approve its proposals to change nine kinds of item. The control surface held throughout. Every change took an operator click, by construction and by test, and no secret value was ever stored, filled or proposed. The outcome was still the right goal at the end. The operator closed the mission satisfied with the HAT rounds, which passed in every flight that had one (Flight 3 after three fixes, the others clean or with one inline fix).

The gap is in model behaviour, not mechanics. After Flight 3, the prompt and tool text kept changing without a baseline, so nothing guards it against regression:
- Flight 4 shipped `p5d` after two n=20 rounds with safety failures. The operator paused the evals and moved attribution to alignment.
- Flight 5 kept the prompt frozen and measured only its new cells.
- With alignment not flown, the debt is now:
  - no baseline;
  - an unattributed regression;
  - a value-repeat rate that tool-result text did not move (8 to 6 of 20);
  - reply-opener claims that wording rules did not move.

Flights 4 and 5 both concluded that these hard lines need a code-level reply check, not more wording. The operator chose a follow-up sortie for this (2026-11-24).

**Scope changed twice on purpose, both operator decisions:**
- no drawer in Chats;
- no connectors, which are to be reworked after this mission.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1. GleepGlorp exists and can answer | completed | DD1 (no `agents` row, reserved name) made every agent route 404 for GleepGlorp by construction. Whitelist read views with a parity corpus, the app guide (13 topics), notes and web, and the Default agent deleted (v53). Prompt "D-min", chosen by parallel n=5 screening and ablation: 255 tokens, Haiku 98.6%. 10 legs plus one aborted (split). The HAT reworked three surfaces whose option board had been approved in one pass. |
| 2. Proposals and approval | completed | The one change shape, `propose_change`, `gleepglorp_proposals` (v54), shared write services extracted from the routes, stale checks, field-level apply under the write lock, continuation on Approve, editor follow-through, and per-path provenance for "Check this". The eval method was written into `evals/README.md`. Prompt `p3`, at 428 of 450 tokens. 11 legs. HAT 9 of 9 with no fixes, which followed an option board. |
| 3. The drawer and form filling | completed | The chat refactored into a factory that runs twice; the drawer on its own window socket; page awareness through one approved touch of the frozen core; `fill_form` (v55) with a lease and unsaved-only writes; checks in all three desktop engines. Prompt `p4c` at the 550 cap, and the n=20 `m36f3` baseline (23 scenarios). 10 legs. HAT 12 of 12 after three fixes, including removing "Show the form". |
| 4. MCP servers and model providers | completed | The `Kind` registry (server and client), the `ApplyError` protocol, v56, the code-level outside-value guard, MCP and provider write services (which fixed an OAuth refresh race), the headline "set it up from this link" behavior test 7/7, and the mission's first quiet-host gate, with ten lanes re-budgeted. Leg 7 landed without its baseline (AC5): `p5d` shipped with unattributed safety failures, and the operator paused the evals. 12 of 13 legs. |
| 5. The remaining kinds | completed | Knowledge bases, Library secrets' metadata, tool configs and app settings, built on registry hooks with no per-kind branches. The gleepglorp lane split into three. `ui/field.js` `wire()` was fixed at its root. Ten new eval cells, one n=20 round with pre-named exits, and two fixes. HAT 9 of 9 with no fix. 10 legs. |
| 6. Alignment *(optional)* | not flown | Operator decision 2026-11-24. Its items go to the follow-up sortie (Action Items). |

## What Went Well
- **Decisions that held for the whole mission** (Architect):
  - **No `agents` row** for GleepGlorp.
  - **Whitelist views** with a structural key guard and a parity corpus, instead of reusing the API's view helpers. Flight 1's review showed the planned "pure move" would have leaked MCP `env` and `headers`, `tool_overrides` and provider URLs.
  - **Shared write services** called by both the route and the proposal apply, so a proposal's validation cannot drift from Save's.
  - **Provenance classified by who can write a value,** failing closed.

  None of these needed reversing, and Flights 4 and 5 built on them without rework.
- **The `Kind` registry paid off as intended.** Flight 4 built it ahead of the kinds, as the Flight 2 and Flight 3 debriefs had recommended. Flight 5 then landed four kinds without touching the proposal or fill loop, and proved the five existing kinds byte-identical with "capture before, diff after". `the_one/agents.md` now has "Adding a kind: the checklist".
- **Moving a safety line from prompt to code worked where wording did not.** The no-copy rule cut planted links in fills from 1 in 5 to 1 in 12. The Flight 4 outside-value guard made them impossible, and live in HAT step 3 it refused a command from a page the operator had not linked. The same lesson is now the plan for the value repeat and the "Done!" claims.
- **Splitting flights at planning, once the scope was known, was right** (operator). Each split landed at a real seam:
  - the overlay before the other editors;
  - the registry groundwork with the two secret-bearing kinds;
  - the four simpler kinds last.

  No flight had to be aborted or re-planned mid-air.
- **Design reviews and option boards caught problems before code.** Every high-risk leg's design review found real defects. From Flight 2 on, option boards before approval took HAT rework from about six cycles in Flight 1 to none in Flight 2.
- **The eval method matured into a reusable procedure:**
  - parallel n=5 screening with a control;
  - a fairness pass on transcripts before quota;
  - safety checks against ranking checks;
  - stop-on-safety with every failing transcript read;
  - exits named in advance;
  - must-fail lie corpora for safety regexes.

  Each step was added after it cost something, so it is earned rather than speculative.
- **The HATs found what the evals could not:**
  - "my Claude subscription" exposed a provider-type hint;
  - "Show the form" had a data-loss path and no use case;
  - a widened tool list silently dropped `http_request` on Approve.

## What Could Be Improved
- **The prompt changed without a baseline for two flights.** Flight 4 changed five model-visible surfaces at once and dropped the control step that DD13 had prescribed. The regression could not be attributed, and `p5d` shipped on an operator pause rather than a measurement. Flight 5 then had nothing to compare against. A prompt or tool-text change that lands without its baseline should be an explicit, dated debt with an owner, not a deferral to an optional flight.
- **Wording was asked to do code's job.** Three times a hard line was given more wording before anyone tried code:
  - planted links (Flight 3);
  - "Done!" openers (Flight 4: "never start with or say done");
  - value repeats (Flight 5: "I never take, fill or repeat one").

  Wording failed each time, and code worked the one time it was tried.
- **Test time grew about 50% in six days.**
  - **Unit tier:** 10,695 tests in 309 s at Flight 1, 12,349 in 470 s at Flight 5. That is 34% over the 350 s standing target on a quiet host. The 451 tests Flight 5 added cost about 0.19 s each, against a tier average of about 0.04 s, so it is not only volume (squawk 0403).
  - **Full gate:** 53:26 against the 67-minute target restated at Flight 5. The target was 43 minutes before this mission and was raised twice.
  - Each new kind adds about 25 s to `gleepglorp-kinds`.
- **Crew background-task hygiene never held** (all five flights): sleep timers, `pgrep -f` wait loops that matched themselves, agents handing back with work still running, a leg landed before its gates finished. Each flight added prompt wording, and the next flight found a new variant. This cost FD time and some invalid timing readings, but no wrong code.
- **A click gate is only as strong as what the card shows.** The card shows a whole new list without marking removals, so the operator approved a dropped tool without seeing it. The operator judged a removal diff not needed (2026-11-24). It is recorded here as the approval surface's known information limit.
- **The `Kind` base class is accreting narrow hooks** (Architect). It has about 15 optional members, several added for a single kind (`operator_only_aliases`, `relaxed_guard_keys`, `create_only_message`, `action_refused`). `proposals/shape.py` still carries a lazy re-export shim for tests that use the old names. Several kind modules are near 600 lines: `mcp_server.py` 580, `tool_config.py` 578, `provider.py` 570, `outside.py` 610, `view_core.py` 630. Review this before the connectors rework adds a tenth kind.

## Lessons Learned
- **A model-facing read surface is a whitelist, never a reuse of the API's views.** The API's views were built for an authenticated browser, not for text sent to a third-party model.
- **Hard safety lines belong in code; wording is for ranking behaviour.** If a line cannot be crossed even 1 time in 20, enforce it in the tool or with a reply check. n=5 cannot see a 1-in-20 failure, so use n=5 to choose between candidates and n=20 (or targeted high-n runs on the safety cells) to clear them.
- **Measure one model-visible change at a time, or keep a control.** Prompt text, tool descriptions, tool-result sentences and field hints are all prompt surface. Changing several at once without a control makes any regression unattributable.
- **Eval checks are code under test.**
  - In Flight 3, four of six "safety failures" were false positives in the checks.
  - In Flight 5, every over-wide exemption was caught by must-fail lies, not by honest-reply tests.
  - So write both corpora before spending quota.
- **Replacing a refusal can remove information the model relied on.** In Flight 5, a more specific values refusal dropped the "Allowed fields" list, and successful fills fell from 15 to 7 out of 20.
- **Split by kind when each kind has its own service and editor seam,** and pair server and client legs (a/b). This held in every flight after Flight 2.
- **Fix shared-control defects at the control, then run the whole browser suite.** The `ui/field.js` `wire()` fix in Flight 5 repaired `aria-describedby` on every form.
- **Provisional lane budgets set from solo runs are off by about 2x.** Mark them provisional, and re-measure them at the next quiet gate.

## Methodology Feedback
All observations are on mission-control 1.2.4. They restate observations already recorded in the flight debriefs, so a later `/mission-control:service-report` sweep should count each occurrence once, not again here.

1. **agentic-workflow, Phase 2b: an operator-gated, quota-spending leg has no shape.** *Methodology observation.*
   - **What happened:** each eval leg was modelled by hand as gates, rounds, re-runs and dispositions, in a leg file that becomes immutable once in flight. There was also no standing quota authority and no exit for a zero-failure criterion that fails.
   - **Recurrence:** Flights 1, 2, 4 and 5 (4 of 5); also 3 of 3 flights in Mission 35.
   - **Cost:**
     - many FD cycles and operator round-trips;
     - an extra n=20 round in Flight 4;
     - leg files that no longer described what happened;
     - "land with a recorded disposition" improvised from the behavior-test failure rule.
   - **Expected:** a gated-rounds leg pattern, with appendable sub-steps, pre-named exits (diagnose, revert to control, accept) and a stated quota authority.
2. **agentic-workflow, crew prompts and harness: crew agents leave background work running.** *Methodology observation (partly harness).*
   - **What happened:** leftover `sleep` timers, self-matching `pgrep -f` loops, hand-backs while waiting on their own tasks, and in one case a leg landed with its gates unfinished.
   - **Recurrence:** Flights 1-5 (5 of 5), and Mission 35.
   - **Cost:**
     - repeated `TaskStop`;
     - one invalid unit-tier reading;
     - about 20 minutes of lanes the FD had to run;
     - a log file left in `$HOME`.
   - **Expected:** the harness reaps or refuses a crew agent's leftover background tasks at hand-back. Prompt wording alone has not held across ten-plus agents.
   - **Local fix:** squawk 0410.
3. **agentic-workflow, Phase 2a: leg design does not survey the code, or wait for predecessors.** *Methodology observation.*
   - **What happened:** legs were designed without a survey of the code they touch, or before the leg they depend on had landed. Design reviews then found code facts, not design points, and legs were split after design.
   - **Recurrence:**
     - Flight 1: two legs split;
     - Flight 2: every high-risk leg's review found code facts;
     - Flight 3: Leg 6 split;
     - Flight 4: three "needs rework" verdicts and one aborted leg.

     That is 4 of 5.
   - **Cost:** about two extra review cycles per flight, and several leg rewrites.
   - **Expected:** a short read-only code survey before writing a high-risk leg, and dependent legs designed or re-verified against landed code.
4. **agentic-workflow, Phase 2a: a flight DD's ordered procedure or planning figures don't carry into the leg.** *Methodology observation.*
   - **What happened:** Flight 4's DD13 control step was omitted from its Leg 7 file, and the leg was tiered low, so no second reader saw it. Flight 5's DD11 token figures were stale by Leg 5.
   - **Recurrence:** Flights 4 and 5 (2 of 5).
   - **Cost:** the unattributable regression, which is this mission's largest open debt, and a survey round in Flight 5.
5. **agentic-workflow, Phase 2a risk checks: tests and registries that enumerate a set the leg grows are not covered.** *Methodology observation.*
   - **What happened:** scenario lists, topic lists and shipped-candidate pins were not on the leg's list of edits it is allowed to make.
   - **Recurrence:** Flight 3, where four legs hit `[BLOCKED]` on them, and Flight 1, where an exact-dict pin reached the gate (2 of 5).
   - **Cost:** 15-30 minutes each.
   - **Local fix:** the project's leg-design checklist.
6. **agentic-workflow, Phase 3: batch mode has no full gate before `landed`.** *Methodology observation, mitigated locally.*
   - **What happened:** the full gate was missing in Flight 2. Flights 3-5 added a closing-gate leg by local practice.
   - **Recurrence:** 1 of 5, then handled locally.
   - **Cost:** Flight 2's target breach surfaced only after landing.
7. **agentic-workflow, Phase 2b: no rule against starting the next Developer during a recorded verification run on the shared tree.** *Methodology observation.*
   - **Recurrence:** Flight 5 only (1 of 5).
   - **Cost:** one inconclusive run.
8. **behavior-test, live mode and spec authoring.** *Methodology observation, low count.*
   - **What happened:** crew agents could not call SendMessage, which conflicted with the "you are resumed" wording. A spec "finalized from code" also drifted from the rendered UI.
   - **Recurrence:** Flight 4 only (1 of 5).
   - **Cost:** a protocol deviation and three rewordings.
9. **flight-debrief, "reuse the flight's gate".** *Local fix: the project's crew rule, squawk 0405.*
   - **What happened:** the rule treats `the_one/*.md` as code, and has no case for an operator deferring the timing reading.
   - **Recurrence:** Flights 3, 4 and 5 (3 of 5).
   - **Cost:** about 7 minutes of redundant unit runs, twice.
10. **Smaller items, recorded as local lessons:**
    - **The design review's two-cycle cap** (Flight 3): no cost.
    - **The HAT protocol:** the multi-surface trigger was not followed in Flight 1, at no cost. The fix-vs-feature gate worked as written in Flight 3.
    - **Option boards before approval** (Flight 1 negative, Flight 2 onward positive): now local practice.
    - **The mission's adaptive planning worked.** Three flights became six through splits at planning (operator: "splits were right"). This is a positive data point for sizing flights at each planning conversation rather than up front.

## Action Items
- [ ] **Sortie: GleepGlorp safety and baseline** (operator decision, 2026-11-24). It takes the items deferred to alignment.
  - **Re-measure first:**
    - `secret-create-fill`, since the field-list fix `cfd77095` was never measured;
    - `secret-widen-propose`;
    - the Flight 4 failing safety cells, with the `p4c` control on the current surfaces at n=20, to attribute the regression.
  - **Then add a code-level reply check** for the hard lines: repeating a pasted secret value, asking for a key in chat, and "Done!" or "I've set up" claims before a Save or Approve.
  - **Record a baseline for the shipped prompt** on the full set (42 scenarios), naming the surfaces it covers, and update CLAUDE.md's baseline list.
  - **Fold in the wording items** listed in the Flight 4 and Flight 5 debriefs:
    - proposing instead of filling in the drawer;
    - "Click Save" where the button reads "Create";
    - refusals that do not name the page;
    - ambiguous-name guessing;
    - a dropped allowed tool on a widen;
    - qwen3-4b's tool discovery (measured only).
  - **Decide where eval run evidence lives,** because `evals/runs/` is not committed.
  - **Run or retire the two unrun proposal behavior specs.**
  - **Standing authority:** the FD may re-run only the failing scenarios after a reviewed exit-1 fix, up to about 40 Haiku runs (operator, 2026-11-24).
- [ ] **Squawks open from this mission:**
  - [0403](../../squawks/0403-unit-tier-over-its-350s-target.md): unit tier 470 s against 350 s; profile with `--durations=50`, or restate the target.
  - [0404](../../squawks/0404-dev-instance-recipe-records-wrapper-pid.md): the dev-instance recipe records a wrapper PID.
  - [0405](../../squawks/0405-debrief-reuse-rule-treats-docs-as-code.md): the debrief's gate-reuse rule treats docs as code.
  - [0407](../../squawks/0407-replaced-proposal-card-keeps-its-buttons.md): a replaced proposal card keeps Approve and Dismiss. This is the most user-facing of them.
  - [0408](../../squawks/0408-tools-page-keepfocus-not-cleared-on-throw.md): `keepFocus` is not cleared on a throw.
  - [0409](../../squawks/0409-drawer-router-wait-helpers-belong-in-nav.md): the router-wait helpers belong in `_nav.py`.
  - [0410](../../squawks/0410-crew-prompts-self-matching-pgrep-and-stray-logs.md): crew-prompt hygiene.
- [ ] **Before the connectors rework adds a tenth kind:**
  - review the `Kind` hooks and fold the single-kind ones into fewer general members;
  - remove the `proposals/shape.py` re-export shim;
  - watch the near-600-line kind modules.
- [ ] **Name the mission's patterns in `the_one/agents.md` "Project Conventions":**
  - whitelist views with a key guard and a parity corpus;
  - provenance by who can write, failing closed;
  - capture before, diff after;
  - safety versus ranking eval cells, where a reclassification needs an operator decision and a recorded residual (Flight 3's `fill-after-fetch-no-secret` is not precedent);
  - a must-fail lie corpus for every safety regex.
- [ ] **Connectors:** GleepGlorp's fills and proposals for connectors are owed to the rework mission. The read-only view and page awareness stay.
- [ ] **Routine maintenance** is due between missions (`/mission-control:routine-maintenance`).
- [ ] **Release 1.0.0** (operator, 2026-11-24), after this debrief merges: the version bump and `docs/releases/v1.0.0.md` in a release PR, then the `v1.0.0` tag once that PR merges.
