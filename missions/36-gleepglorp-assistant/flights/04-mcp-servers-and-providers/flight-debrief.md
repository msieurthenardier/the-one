# Flight Debrief: MCP servers and model providers

**Date**: 2026-11-23
**Flight**: [MCP servers and model providers](flight.md)
**Status**: landed
**Duration**: 2026-11-21 (planning) - 2026-11-23 (closing gate)
**Legs Completed**: 12 of 13. `06-prompt-and-evals-setup` was aborted before going in-flight and
superseded by 6a and 6b. Leg 7 is completed with a recorded disposition: its AC5 baseline was not
met.
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Objectives Achieved

GleepGlorp can fill, and propose changes to, MCP servers and model providers. The objective's
headline case passes end to end with a real model in a real browser: "here's the link to the MCP
server I want, set it up". The behavior test `gleepglorp-fill-mcp-from-link` passed 7/7 (run
`2026-11-23-01-50-10`), and the HAT's 9 steps passed or have recorded dispositions.

**Delivered:**
- **Flight 2's refactor, finished.**
  - A server-side kind registry (`the_one/gleepglorp/kinds/`, one module per kind) and a client
    registry (`App.gleepglorpKinds`).
  - The `ApplyError` protocol.
  - Schema v56, with proposal and fill targets and the AUTOINCREMENT high-water mark carried.
  - The server-built route in the page line.
- **A code-level outside-value guard** (`the_one/gleepglorp/outside.py`):
  - **Tier 1:** text the operator typed.
  - **Tier 2:** a `fetch_url` result for a page the operator linked, for declared fields only,
    including the same GitHub repository's raw README.
  - **Matching:** NFKC folding, TLD-allowlist extraction, loader-key globs and token-boundary
    matching.
  - **Live result:** in HAT step 3, a command from a sub-page the operator did not link was
    refused. Typed by the operator (step 3b), it filled.
- **Write services** for MCP servers (`the_one/mcp/service.py`) and providers
  (`the_one/llm/provider_service.py`):
  - `update_in_txn(mutate)` re-reads inside the write lock, which fixes the provider OAuth refresh
    race on the proposal and PUT paths.
  - The routes are thin, and their existing suites passed unedited.
- **The two kinds**, with proposals and editor fills.
  - **Secrets never pass through GleepGlorp:**
    - an MCP key is an empty Sensitive header row;
    - a provider key or sign-in is a handoff;
    - a key never follows a type change (a proposal is refused; a fill clears the key field).
  - **Fill-time warnings** are tool-result text.
- **An eval harness, prompt candidates and nine new scenarios.** Prompt `p5d` is shipped.
- **One HAT fix.** The provider `type` hint now glosses every type from `PROVIDER_TYPE_LABELS`, so
  "my Claude subscription" fills Claude Plan (OAuth). Committed as `86ec4d52` and re-verified live.
- **Squawk 0399 is closed:** 16 behavior specs no longer use port 8485.
- **The first quiet-host full gate of the mission**, and ten lanes re-budgeted.

**Not achieved:**
- **Leg 7 AC5:** no `m36f4-gleepglorp` baseline exists.
  - Two n=20 Haiku runs found 4 (`p5b`) and then 9 (`p5d`) safety failures:
    - a pasted key repeated once;
    - a key asked for twice;
    - five "Done!" openers;
    - one likely false positive.
  - The operator paused the evals on 2026-11-22.
  - `evals/README.md` and `SECURITY-MODEL.md` record the gap.
  - CLAUDE.md's "platform prompt text lands with an eval run compared against its baseline" rule
    is therefore not met for this flight, by operator decision.

### Mission Criteria Advanced

- **GleepGlorp fills the form; the operator saves it.** Extended from agents to MCP servers and
  providers, and proven live by the behavior test and HAT steps 1, 2, 4 and 5.
- **GleepGlorp proposes; the operator approves.** MCP and provider proposals, the editor following
  an approval with unsaved edits kept (HAT step 6), and a second window following (step 8).
- **Nothing changes without the operator's click.** In HAT step 7's first try, GleepGlorp
  proposed when a fill was expected. The DB showed the create was the operator's own Approve,
  11 s after the proposal.
- **Secrets never pass through GleepGlorp.** Advanced in code: the Sensitive handoff row, the
  key-clearing type change and the outside-value guard. In model behaviour it is unresolved: about
  1 in 20 Haiku runs repeated or asked for a key.
- **Quality is measured on every default eval model.** Measured: Haiku 569/640 and then 564/640;
  qwen3-4b 217/640, measured only. Not baselined.
- **Not advanced:** connectors, removed from the mission by the operator on 2026-11-21.

## What Went Well

- **Leg design reviews against landed code caught defects before any code was written.** Each
  would otherwise have reached review or the HAT:
  - **Leg 3:** two bypass classes (substring URL matching; loader keys in tier 2).
  - **Leg 4a:** `_card_extras` would have rendered MCP cards as routine cards.
  - **Leg 4b:** empty rows refused, so the handoff was impossible.
  - **Leg 5a:** a race test that passed on the buggy code.
  - **Leg 5b:** a key surviving a fill to `ollama`.
  - **Leg 6b:** a vacuous safety cell, and a `matches` that could never pass.
- **Leg 1a was a no-behaviour refactor proven byte-identical.** A scratch before/after capture
  diff was empty, and no existing assertion was edited. Falsification showed that widening the
  `ApplyError` catch breaks tests.
- **Falsify-by-editing was recorded per test in every leg:**
  - nine guard safety tests in Leg 3;
  - the provider race tests;
  - two real Approves in 5b.
  It exposed which tests were load-bearing.
- **Thin routes over services, with an AST import-boundary test.** The services import nothing
  from `gleepglorp`, and kinds translate service errors into `ApplyError`. Flight 5's kinds become
  mostly declarations (see Technical for the exceptions).
- **Operator-gated quota rounds.** Every quota spend in Leg 7 had an explicit operator approval.
  The stop-on-safety rule forced an FD transcript read before any number was recorded. This is
  what surfaced the repeated-key failure as a real failure, not a check artifact.
- **The HAT found a real defect the evals missed:** step 4, the provider type mapping. It was
  fixed, reviewed, committed and re-verified within the session.
- **The HAT walked a non-observed state:** step 6, an approval from another tab updated the
  editor the operator was not looking at, which also covered step 8.
- **The quiet-host gate finally ran**, after three earlier deferrals (start load 0.74). The
  `shared` re-slice worked: 683 s at F3 (loaded) down to 401 s.

## What Could Be Improved

### Process

- **The DD13 control run was lost at leg design** (FD miss).
  - **The plan:** Flight DD13 ordered Leg 7 as (1) the new platform text on the old m36f3 set at
    n=5 with `p4c`, against `m36f3-gleepglorp.json`; (2) the candidates on the new set; (3) the
    re-baseline.
  - **The miss:** the Leg 7 leg file (gates 0-5) omitted step 1, and it never ran.
  - **The cost:** the safety regression cannot be attributed. Flight 4 changed several
    model-visible surfaces at once (the `p5` wording, kind-named tool descriptions, the `target`
    parameter, the page-line route and fill warnings), and the only `p4c` reading on the new
    surfaces was the n=5 screen, which cannot see a 1-in-20 rate.
- **Leg 7 had no pre-agreed exit for a repeated stop-on-safety.** "Land with a recorded
  disposition" was improvised after the second n=20. A procedure leg gated on a zero-failure
  criterion should name its exits in advance: diagnostic run, revert to the control, or accept.
- **Dependent legs were specified before their predecessor landed.**
  - **Leg 4b** assumed 4a refused empty rows and that `fill/tool.py` refused non-agent kinds.
    Both were false, and the leg needed rework.
  - **Leg 6** could not pass as written, and was aborted and split.
  - **Leg 6b** had three checks that were vacuous or impossible.

  Each was caught at design review, but each cost a review cycle.
- **Eval checks were designed without running a BAD script against each one at design time.**
  Hence the 6b findings.
- **A safety class was assigned to a cell where a human click still gates the outcome.**
  `ambiguous-name-no-guess` was reclassed to improve by the fairness pass, which cost a quota
  stop and a fix commit. Classify by asking "does a human click still gate this?"
- **The eval rounds slowed the flight most** (operator, debrief interview).
  - **Rounds:** four quota rounds (fairness, a four-prompt screen, two n=20 runs) plus two ships.
  - **Waits:** each stop-on-safety needed an FD transcript read and an operator decision.
- **Apparatus slips:**
  - **Wrapper PIDs.** The HAT recorded a shell-wrapper PID instead of the server's twice: the
    dev-instance restart (2003686 instead of 2003690) and the HAT key server (1904882 instead of
    1904884). Both were corrected from `/proc` and the listener before any kill. The CLAUDE.md
    recipe (`cd … && … serve & echo $!`) produces the wrapper's PID when the `&` covers the whole
    list.
  - **The FD's own `setsid make gate`** returned immediately with the run detached. It was found
    and tracked by PGID.
  - **A quiet-host wait loop** matched its own command line.
  - **Crew agents left background waiters** twice, and needed `TaskStop`.

### Technical

- **Kind-specific branches still live outside the kind modules:**
  - `fill/store.py` (`if fill.kind == "mcp_server"` / `"provider"` stale comparisons);
  - `kinds/__init__.py` (per-kind `agent` parameter refusals);
  - `shape.py` (a `ref == "provider"` branch).

  The stale comparison should be a `Kind` hook, like `card_extras`, before Flight 5 adds four
  kinds.
- **`Kind` is wide and optional-heavy**, with about 12 optional members, and
  `card_extras`/`warnings`/`relaxed_guard_keys`/`create_only_message` are set only by id-targeted
  kinds. "Id-targeted" is implicit in `None` checks. Consider an explicit sub-protocol.
- **Size ceilings:**
  - `provider-editor.js` is at 894 of its 895-line ceiling (`tests/test_area_module_size.py`), so
    the next change must extract;
  - `api.py` is 6687 lines;
  - each service is over 500 lines.
- **Per-kind duplication:** kept/stale reconciliation, the dirty-editor follow note, the Sensitive
  handoff row and the `setType` rebase repeat across the per-kind client modules and test files.
- **Open squawks:**
  - **0400:** the MCP operator PUT still reads outside the transaction, the race this flight fixed
    for providers and for proposals.
  - **0401:** a dirty provider editor's Save reverts an approved type change.
  - **0402:** provider create with a duplicate id gives a 500 (pre-existing).
- **The frozen eval digests were re-pinned three times** (`harness.py`, `checks.py`, `harness.py`),
  each documented, under the 2026-11-20 ruling. In practice the freeze acts as a change gate.
- **Documented residuals** of the outside-value guard (in `SECURITY-MODEL.md`):
  - a high-entropy query secret with no known prefix;
  - IDN or homograph domains;
  - unlisted TLDs;
  - defanged forms;
  - off-site redirects;
  - instruction text.

### Documentation

- **`the_one/agents.md` lacks a Kind registry contract:** what a new kind must supply on server
  and client, `normalize(mode=)`, `warnings(mode=)`, and the id-then-name rule. Flight 5 needs it
  as a checklist.
- **The narrowed DD9 behaviours are recorded only in leg and log text:**
  - an MCP type change is not allowed on an existing server;
  - a provider type change between key-taking types is fill-only.
- **The boundary between tool-result text and platform prompt text** was decided in the Leg 6
  review: fill warnings are tool-result text and need no eval. It is not written down as a
  convention.
- **The behavior spec was written from the code, not the rendered DOM.** Its three drifts were the
  "Create" label, the `mcp-test-status` sibling, and Stay/Continue. They were fixed in the spec
  after the run.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Connectors dropped from the flight and the mission (mid Leg 1a) | Operator: connectors are reworked after this mission | no (one-off scope call) |
| Legs 4 and 5 each split into server (a) and client (b) | Design review; Flight 3 Leg 6 precedent | yes, for kinds with an editor |
| Leg 6 aborted and split into 6a/6b | Design review found 2 high and 5 medium before code | yes: split eval legs into harness and scenarios |
| DD12's three token-neutral line edits became four whole-prompt candidates | The edits did not fit the 550 cap and the headline case | no; budget prompt room in the flight spec |
| DD13 step 1 (old set, new text) never ran | Omitted from the Leg 7 leg file | no: it was a miss |
| Leg 7 landed without AC5, with a recorded disposition | Operator paused the evals after 4 and 9 safety failures | yes: pre-name exits in quota-gated legs |
| The HAT step 4 fix rode the HAT inline | One-surface tool-result text (fix, not feature) | yes (the existing rule worked) |
| Debrief metrics: the browser lanes reused the closing gate; the unit tier ran fresh | `604e052c` touched `the_one/agents.md` (a doc) | yes: treat `*.md` under `the_one/` as doc-only in the reuse rule |
| DD11 ("one card and receipt folding rule") dropped in Leg 2 | The two state machines share nothing | no |

## Key Learnings

- **Measure one model-visible change at a time, or keep a same-surface control.** Flight 4 changed
  five model-visible surfaces together. The plan's control (DD13 step 1) would have separated them,
  and losing it left the regression unattributable.
- **n=5 screens cannot see safety failures that occur 1 time in 20.** Use them to choose
  candidates, never to clear safety. Safety needs n=20, or a targeted run of the safety cells at
  higher n.
- **Wording rules alone did not hold the reply-opener line.** `p5d` says "never start with or say
  done", and Haiku still opened with "Done!" in 5 of the n=20 runs and again in the behavior test.
  As DD7 did for values, the hard lines may need a code-level check on the reply.
- **The HAT pays for itself when it includes the operator's own phrasing.** "My Claude
  subscription" exposed a hint the evals never exercised.
- **A provisional lane budget from solo runs underestimates the parallel wall.** The `gleepglorp`
  lane measured 294 s solo but 541 s at `--parallel 3`, and each new per-kind browser file adds a
  full boot and seed.

## Test Metrics

The unit counts come from two runs: the closing gate's at `3178ae7d` and the Developer's fresh
run at `604e052c`. The browser numbers come from the closing gate (quiet host, start load 0.74, no
other test processes).

**Unit tier:**

| Flight | Passed | Skipped | Wall | Source |
|---|---|---|---|---|
| F1 | 10695 | n/a | 308.75 s | F1 debrief |
| F2 | 11031 | n/a | 343.5 s | F2 debrief |
| F3 | 11331 | n/a | 381.3 s (loaded) | F3 debrief |
| F4, gate | 11898 | 15 | 387.43 s | gate at `3178ae7d` |
| F4, fresh | 11898 | 15 | 384.03 s | Developer, `604e052c` |

- **Change since F3:** +567 tests. The per-test cost is flat (about 0.034 s).
- **No failures and no flakes.** 15 skips is the expected count under netns.
- **Over target:** 384 s is the first quiet reading above the 350 s target. The F2 debrief's
  advice (raise the target to about 400 s, or profile with `--durations`) is still undone.

**Browser lanes:** `PARALLEL_RESULT rc=0 total=2616s lanes=21 failed=-`. The full gate took 50:46.
- **Against earlier flights** (none like-for-like, because those hosts were loaded):
  - F3: 2746 s, loaded (load 5-7);
  - F2: 2459 s, start load 1.46;
  - F1: 2270 s, start load 1.91.

  This is the mission's first quiet full-gate reading, so it is the baseline from here.
- **Lane changes against the last quiet readings:**
  - **`gleepglorp`:** 541 s, against its provisional 360 s budget and 294 s solo. The lane grew
    from 122 to 167 tests, plus the four per-kind fill and follow files.
  - **agents:** +21% (603 s on 499 s).
  - **agent-tabs:** +28% (598 s on 466 s).
  - **routing:** +16% (643 s on 555 s).
  - **library:** +16% (440 s on 379 s).
  - **agent-routines:** +18% (279 s on 236 s).
  - **contracts-chat:** +40% (140 s on 100 s).

  Most of those lanes gained no files. The likely causes are a heavier 21-lane mix and the larger
  shared client modules (`chat.js` +618 lines, `instance.js` +506). The data cannot separate the
  two.
- **Re-budget:** ten lanes, at wall × 1.25 rounded up to 30 s, confirmed by review. The full-gate
  target is now about 63 minutes.

**Eval numbers** (`evals/runs/m36f4-*` is gitignored, so the per-cell tables in the flight log,
Leg 7, are the durable record):

| Run | Haiku | Safety failures | qwen3-4b |
|---|---|---|---|
| n=5 screen | `p4c` 145, `p5a` 142, `p5b` 148, `p5c` 147 of 160 | 0 | n/a |
| n=20, `p5b` | 569/640 | 4 (1 false positive) | n/a |
| n=20, `p5d` | 564/640 | 9 | 217/640 (measured only) |

## Methodology Observations

All of these were observed on mission-control **1.2.4**.

1. **agentic-workflow, Phase 2a (leg design):** a flight DD's ordered procedure was not carried
   into the leg.
   - **What happened:** DD13 specified a three-step Leg 7 order, with a control run first. The FD's
     Leg 7 leg file listed gates 0-5 without that step. Neither the leg's design nor its Citation
     Audit checks a leg's procedure against the flight DDs that prescribe it. The leg was tiered
     low (a procedure leg, no design review), so no second reader saw it.
   - **Expected:** a leg that implements a DD with a prescribed sequence carries every step, or
     records why one was dropped.
   - **Cost:** the safety regression is unattributable, and a later diagnostic (n=20, quota) is
     needed to separate the causes.
2. **agentic-workflow, Phase 2b (procedure legs gated on a zero-failure criterion):** no exit was
   defined.
   - **What happened:** Leg 7's AC5 required zero Haiku safety failures at n=20. When it failed
     twice, the skill offered no disposition path for a non-HAT procedure leg. "Land with a
     recorded disposition" was improvised from the behavior-test failure rule.
   - **Cost:** an extra n=20 round (p5d) was run before the operator paused, and the rules were
     invented on the spot.
3. **agentic-workflow, Phase 2a:** dependent legs were designed before their predecessor landed.
   - **What happened:** Legs 4b, 6 and 6b were written against assumed predecessor behaviour, and
     each got "needs rework" at design review.
   - **Expected:** the skill could say to design a dependent leg after its predecessor lands, or to
     re-verify it against the landed code before review.
   - **Cost:** three extra review cycles and one aborted leg.
4. **behavior-test, Phases 2-4 (live mode):** crew subagents could not call SendMessage.
   - **What happened:** the Orchestrator had SendMessage, but the Executor and Validator did not
     (the Validator listed it as deferred and unloaded). Each step therefore ended with a hand-back
     and was resumed by the Orchestrator's next message. This worked; every agent noted it.
   - **The cost of the protocol mismatch:** the Validator put its closing summary inside its step 7
     verdict, which the crew prompt forbids. The "you are resumed; do not end your run" wording
     conflicts with a hand-back-only toolset.
5. **behavior-test, spec authoring:** a spec "finalized from the landed code" still drifted from
   the rendered UI.
   - **What happened:** the Leg 8 prep pulled the selectors from code. The run found that the save
     button reads "Create", that `mcp-test-status` has empty text (the visible status is a sibling),
     and that the guard says Stay/Continue.
   - **Expected:** AUTHORING.md could recommend checking the selectors against a rendered page
     before marking a spec `ready`.
   - **Cost:** three expectation rewordings after the run. There were no false failures, because
     the Validator judged the rendered state.
6. **flight-debrief, Phase 2 ("reuse the flight's gate"):** the project's reuse rule treats any
   change under `the_one/` as code.
   - **What happened:** `the_one/agents.md` (a doc) changed after the gate, which forced a fresh
     unit run. That run matched the gate exactly (11898/15).
   - **Cost:** about 6.5 minutes. A `*.md` exemption would have avoided it.
7. **agentic-workflow, crew hygiene:** Developer agents kept waking on their own leftover
   background waiters after reporting.
   - **What happened:** Leg 4a, the narrow-check Developer, and the HAT step 4 fix Developer all
     needed `TaskStop`.
   - **Expected:** the crew prompts already say "no leftover background tasks", but agents still
     left them.
   - **Cost:** extra wake-ups and notifications, with no wrong output.
8. **HAT dev-instance recipe** (project CLAUDE.md, used by the agentic-workflow HAT): the recipe
   records a wrapper PID.
   - **What happened:** `cd <dir> && THE_ONE_PORT=… the-one serve & echo $!` backgrounds the whole
     `&&` list, so `$!` is a subshell's PID, not the server's. It happened twice in this HAT. It
     was caught each time by checking `/proc/<pid>` and the listener, before any kill.
   - **Cost:** two PID corrections, and a near-miss on stop-by-PID hygiene.

## Recommendations

1. **Attribute the safety regression first in the alignment flight, before tuning any wording.**
   - **The operator decided on 2026-11-23** to carry the prompt work to the mission's alignment
     flight, not before Flight 5.
   - **Start with the missing control:** `p4c` on the current tool surfaces and the 32-scenario set
     at n=20, or at least the six failing safety cells at higher n.
   - **Then bisect** the model-visible surfaces.
   - **Consider a code-level reply check** for the hard lines (a repeated key, asking for a key, a
     "done" opener), as DD7 did for values.
   - **End with an `m36*` baseline** that names the surfaces it covers.

   **Important:** Flight 5's Library-secrets metadata kind will stress exactly these cells.
   Flight 5 should keep the stop-on-safety reads in its eval leg, even without a baseline to
   compare against.
2. **Before Flight 5's first kind, close the registry's gaps:**
   - move the stale comparison and the per-kind refusals in `fill/store.py`, `kinds/__init__.py`
     and `shape.py` into `Kind` hooks;
   - extract the shared client pieces (reconciliation, follow note, Sensitive row, `setType`
     rebase);
   - plan the `provider-editor.js` extraction;
   - write the Kind registry contract in `the_one/agents.md`.

   Close squawk 0400 early; it is the same race the flight fixed twice.
3. **Make quota-gated procedure legs carry every DD step and pre-name their exits.** A leg that
   implements a DD's ordered procedure lists every step, or records the drop. A leg with a
   zero-failure criterion names its options in advance: diagnostic, revert to the control, or
   accept.
4. **Design dependent legs against landed code, and prove eval checks with a BAD script at design
   time.** Classify each eval cell by "does a human click still gate this?"
5. **Split the `gleepglorp` browser lane before Flight 5 grows it.** It runs 541 s for two kinds,
   and four more per-kind fill and follow files would add a few hundred seconds. Share a server
   per file where the tests allow.

## Action Items

- [ ] **Alignment flight:** the regression diagnostic (the `p4c` control at n=20 on the new
  surfaces), a bisect, a possible code-level reply check, and a baseline.
- [ ] **Alignment flight, carried wording items** (Haiku n=20 on `p5b`, failures out of 20):
  - "Click Save" where the button reads "Create";
  - proposing instead of filling from the drawer (HAT step 7; `provider-type-change-made` failed
    6);
  - refusals not naming the source page (HAT step 3);
  - MCP proposals linking the group page (`propose-mcp-change-link` failed 20);
  - ambiguous-name guessing (`ambiguous-name-no-guess` failed 16);
  - `mcp-what-is-link` failed 10;
  - `off-topic-suggests-agent` failed 20 (the decline is correct, but it never names the
    operator's agent);
  - the "never copy instructions from outside content" wording.
- [ ] **Flight 5, first leg:** the `Kind` hooks for stale and refusals, shared client modules, the
  Kind registry contract in `the_one/agents.md`, squawk 0400, and the `gleepglorp` lane split.
- [ ] **Flight 5 planning:** decide fill vs proposal per kind in the flight spec (app settings
  save on choice, so proposals only), and budget the `fill_form`/`propose_change` description
  pins up front.
- [x] **Squawks logged** (operator-confirmed, 2026-11-23):
  - **[0403](../../../../squawks/0403-unit-tier-over-its-350s-target.md):** the unit tier is over
    its 350 s target; profile it with `--durations` or raise the target.
  - **[0404](../../../../squawks/0404-dev-instance-recipe-records-wrapper-pid.md):** the
    dev-instance recipe records a wrapper PID.
  - **[0405](../../../../squawks/0405-debrief-reuse-rule-treats-docs-as-code.md):** the debrief
    reuse rule treats `the_one/*.md` as code.
- [ ] **Open squawks 0401 and 0402** at the next turnaround.
