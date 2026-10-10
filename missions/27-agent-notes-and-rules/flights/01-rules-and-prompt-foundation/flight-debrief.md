# Flight Debrief: Rules and the Prompt Foundation

**Date**: 2026-10-10
**Flight**: [Rules and the Prompt Foundation](flight.md)
**Status**: completed
**Duration**: 2026-10-09 (planning) - 2026-10-09 (landed; behavior test 9/9)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved

- **Rules:** operator-authored, ordered and switchable per agent. Stored in
  v42 `agent_rules` and served over REST. They reach every newly built agent's
  prompt after the persona, through one composer (`compose_system_prompt`)
  and one async loader (`build_system_prompt`) shared by the factory and the
  `next_turn` settle path.
- **UI:** a new **Rules and notes** tab (Rules section), and read-only rules
  in the chat panel.
- **Both pre-existing bugs fixed at the root:**
  - **Rename with revision history failed:** `agent_revisions` was rebuilt
    with `ON UPDATE CASCADE`, pinned by a test that fails on the v41 shape.
  - **A `next_turn` revision dropped the base prompt:** it now recomposes
    through the shared loader, falling back to base plus persona so the turn
    always completes.
- **Behavior test:** `agent-rules-round-trip` passed 9/9 live on
  `gpt-oss:20b`, in the app and through the connector.

### Mission Criteria Advanced
- **Ticked:** "Rules shape new conversations".
- **Partly advanced:**
  - "the agent cannot touch rules" (no rules tool);
  - "rules and notes follow it" (rules and revision history);
  - "UI says when changes apply" (rules half).
- **Closed:** both mission Known Issues.

## What Went Well
- **One composer plus one loader:** removing the second composition
  (`get_system_prompt`) and the pending path's raw-persona write closed the
  drift class, and Flight 2 filled the `notes` slot with no signature change.
- **The cascading-foreign-key recipe:**
  - the v37 ceremony, corrected so the self-reference names the final table
    (safe under `legacy_alter_table`);
  - a `foreign_key_list` idempotency guard;
  - tested on a fresh replay, a populated v41, both self-reference shapes, a
    re-run, rename and delete;
  - reused unchanged by v43.
- **Design reviews caught real defects before code:**
  - the test DB handle (`isolated_db`);
  - `write_transaction` is not re-entrant;
  - the AC20 harness realism;
  - the v42 self-reference;
  - 0-based dense positions.
- **Accessibility review cycles caught real defects:** an unannounced delete
  arm, focus lost on failure, the over-limit state shown only by colour, and a
  chatty live region.
- **Observability design for the behavior test:** a fresh-conversation
  sentinel plus the persisted system message gave an unconfounded 9/9.

## What Could Be Improved

### Process
- **Tab-order consequences were under-searched.** The leg named
  `test_flow_agent_tabs.py` and `test_flow_agents_scale.py`, but missed
  `test_flow_dirty_confirm.py` (`shared` lane), which failed the first gate.
  A leg that reorders tabs should require a repo-wide grep.
- **Leg 2 was tiered low-risk** and still took three review cycles, the third
  a Haiku re-review that found a real focus blocker. UI legs with
  focus/announcement behaviour are not "low-risk" in review cost.
- **A placement planned without an import-direction check:**
  `the_one/agent/rules.py` was impossible (agent -> core -> mcp ->
  repositories), so the rules module landed in `db/_rules.py`.

### Technical
- **The gate went over budget:** 1107 s browser plus 171 s unit, about 21.3
  min, against Mission 26's 20-minute target.
  - `routing` ran 625 s (budget 600), `settings` 590 (540) and `agents` 591
    (510).
  - `routing` and `settings` were untouched, so about 80% of this is host
    contention (netns plus REQUIRE_WEBKIT, a load average of about 20) and
    about 20% is real growth (12 new agents-lane tests).
  - Flight 2's gate returned to about 18.2 min, with every lane in budget.
- **New load-sensitive flakes in `shared`:** one different test per run,
  each passing 3/3 in isolation. The `revertMs: 50` lapse test
  (`test_confirm_contract.py`) is the clearest candidate.
- **Debt:**
  - the drawer's rules fetch bypasses `App.store`, consistent with the
    self-configuration fetch;
  - the `activeElement` origin inference was fixed in Flight 2;
  - the documented limitation that a self-revision can bring rules into an
    open conversation early.

### Documentation
- Flight 3 re-documented the panel (read-only, bulleted, no Edit rules link).
  Flight 1's drawer text in `agents.md` was superseded and has been updated.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Rules constants in `db/_rules.py` | Import cycle from `repositories.py` into the agent package | Yes: name the `db/_*.py` convention |
| `test_flow_dirty_confirm.py` fixed at the gate | The tab-order contract change was not grepped | Yes: a grep requirement for tab-order changes |
| Gate started detached (`setsid`) | The tool's background timeout (10 min) is shorter than the gate | Yes: record in the crew file |
| Flight 1's debrief deferred until after the HAT | Operator away; the debrief benefits from operator input | Case by case |

## Key Learnings
- Fix prompt-composition bugs at the composition seam, not at the call site.
- For any agent-keyed table: `ON UPDATE CASCADE`, plus the PRAGMA-guarded
  rebuild when an existing table needs it.
- A parallel gate on a loaded WSL host produces one-off flakes. Re-run them in
  isolation before calling a regression.

## Methodology Observations
- **Low-risk UI tiering doesn't predict review cost.**
  - **What happened:** agentic-workflow's risk-tiering marked a UI leg
    low-risk, skipping the per-leg design review.
  - **Expected:** that the flight-end review would be light.
  - **Actual:** three review cycles (Sonnet, an Accessibility pass and Haiku),
    with a blocking defect found in cycle 3.
  - **Cost:** two extra fix and review rounds, about 25 minutes.
  - *Skill: agentic-workflow 2a risk tier. Plugin 1.2.0.*
- **The Bash tool's background-task timeout can't contain the full gate.**
  - **What happened:** the first gate was started with a 600 s timeout and
    had to be killed by its process group, then restarted with `setsid`
    detachment.
  - **Cost:** a few minutes.
  - *Skill: agentic-workflow Phase 2d, environment interaction. Plugin
    1.2.0.*

## Recommendations
1. **Require a repo-wide grep in any leg that changes tab order, tab count or
   a shared UI contract,** and list every hit in the leg.
2. **Name the `db/_*.py` placement convention in `agents.md`** (constants that
   repositories need live under `db/`).
3. **Harden or quarantine the `revertMs: 50` lapse test,** and keep a short
   load-flaky list.
4. **Run timed gates on a quiet host,** or record host load next to the
   timings, so budget overruns can be attributed.

## Action Items
- [ ] Squawk **0166**: harden `test_confirm_contract.py::test_lapse_is_visually_distinct_and_clears_on_next_interaction`
      (`revertMs: 50` race under load).
- [ ] Squawk **0167**: CLAUDE.md's expected unit skip count is stale (11, not 10).
- [ ] `agents.md`: the `db/_*.py` convention, and the tab-order grep rule
      (next maintenance pass).
