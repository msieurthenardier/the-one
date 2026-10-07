# Behavior Tests Execution — Project Crew

Crew definitions and interaction protocol for running behavior tests. The
Orchestrator (Mission Control) coordinates this phase using the
`/behavior-test {slug}` skill. Specs are authored inline during planning
conversations (flight, leg, mission, debrief, maintenance) rather than via
a dedicated authoring skill — see `.claude/skills/behavior-test/AUTHORING.md`
on the mission-control side for the authoring guide.

The defining feature: **two persistent agents** stay alive across the entire
test via SendMessage continuation. The Orchestrator drives the step cursor;
the Executor performs each step's Actions when handed one; the Validator
judges each step's Expected Results when handed the Executor's raw state.

The two-role separation is the load-bearing discipline: if one agent both
acted and judged, it would tend to confabulate success. Independence forces
a colder verdict.

## Credential convention (this project's gate)

This project's app sits behind a credential gate — see the project's
`CLAUDE.md`, section "Behavior-test credential convention," for the full
mechanics (reading the long-lived credential, minting a handoff URL for a
browser apparatus vs. attaching the `Authorization` header for a
shell-only apparatus, and why the handoff is single-use). Both Executor
and Validator load `CLAUDE.md` as part of their project context (see
"Context" under each role below) and must follow that convention when
they drive the app — no spec's step table encodes it.

**SAFETY RULE, restated here because it must not be missed**: never point
either agent at port 8484 or the operator's default data directory — that
is the operator's real, running instance. Only drive a dedicated dev
instance on a non-default port with a scratch data directory. If a spec's
Preconditions don't name one, stop and surface `[BLOCKED:no-dev-instance]`
rather than guessing or falling back to the default port.

## Run rules (this project)

Eleven rules the Flight Director used to carry by hand in every spawn prompt (Mission 25
Flight 2 debrief, recommendation 1; Flight 3 debrief, recommendation 5; rules 7 to 11 from
the Flight 4 and Flight 5 close gates, squawk 0121). The operative text
is in the Executor and Validator prompts below; this list is the why.

1. **Per-run scratch.** Each run's agents keep their helper scripts and temporary files in
   their own scratch subdirectory. Concurrent runs once shared one scratchpad, generic
   script names collided, and two Executors each ran another run's script.
2. **No unrequested state-changing actions.** An Executor performs exactly the step's
   Actions. An added "supplementary" full-document load once altered history and forced a
   re-run; re-opening a dialog to read a colour was disclosed but still unrequested.
3. **Input-delivery probe first.** Before `[READY]`, the Executor proves its browser
   apparatus delivers input: a real click (and a real key press) reach a capture-phase
   listener. goldfinch once passed discovery and then silently stopped delivering input.
   The project's browser apparatus is a CDP-driven headless Chromium (Mission 25 Flight 3
   DD12); goldfinch is not used while its input delivery is unverified.
4. **Resumed by SendMessage.** Both agents are resumed after every step; a step's report or
   verdict never ends the run. Agents that wrote "this hand-back ends my run" added noise
   to every message, and one Validator put its closing summary inside a verdict.
5. **Variants in their own fresh context.** A variant (a theme) is set inside the
   variant's own fresh browser context, before its first checkpoint. A Light choice made in
   an earlier context did not carry into the fresh tab step 2 opened, so four Light
   checkpoints ran on Auto; Chromium also caps `history.length` at 50.
6. **Toast evidence is a screenshot.** A toast or flash is `position: fixed`, so its
   `offsetParent` is always null; `offsetParent` (or a `role=status` filter) missed toasts
   that the screenshots showed.
7. **Driver and browser lifetime.** The CDP Chromium's state (session cookie, theme in
   `localStorage`) must outlive each step. Use one long-lived driver process per run that
   holds the CDP connection, or a fresh Chromium process with a fresh `--user-data-dir` per
   variant, driven through its persistent default context. Never a `new_context()` that a
   short-lived script owns: that context is destroyed when the script disconnects. At the
   Flight 4 close gate three of five Executors lost their cookie and theme this way (one
   apparatus re-run, one step redone).
8. **PIDs, stopped by PID only.** Record every PID at launch (the Chromium, the driver)
   and stop only those. Never `pkill -f` or `killall` with a pattern: one such pattern
   matched its own shell, and another run's Chromium exited at the same time.
9. **Report-file hand-off.** The Executor writes each step's report to
   `{evidence-dir}/step-N[-variant]-report.json` without `executor_notes`, and the
   Orchestrator hands the Validator that path. The Validator reads the file, so the notes
   never reach it and a burst of reports is not retyped.
10. **Checkpoint ledger for concurrent runs.** The Orchestrator keeps one ledger per run, a
   line per checkpoint (step, variant, Executor reported, handed to the Validator, verdict),
   and checks that every Executor step was handed to the Validator before it sends the next
   step. One hand-off was skipped in a burst of reports and judged late.
11. **Verify evidence paths.** Before reporting, the Executor checks that every path it lists
   in `evidence_paths` exists (and is non-empty); the Validator checks each path it cites.
   A listed path that was never written costs the step its evidence.

## Crew

### Executor
- **Context**: project root (current working directory) — loads the project's CLAUDE.md.
- **Model**: Sonnet (override per-project if needed).
- **Lifetime**: Spawned once at run start; alive across all steps via
  SendMessage continuation.
- **Role**: Performs the Actions for each step the Orchestrator sends.
  Reports raw observed state. Makes NO pass/fail judgments.
- **Tools**: All — including any registered browser MCPs (chrome-devtools,
  playwright), HTTP / shell / filesystem.
- **Per-step actions**: receive step → perform actions → save evidence →
  report structured state → await next step.

### Validator
- **Context**: project root (current working directory) — loads the project's CLAUDE.md.
- **Model**: Sonnet (default; **NEVER Opus** — mirrors the existing crew
  discipline from `leg-execution.md`). Validator needs judgment + reading
  comprehension, not raw reasoning power.
- **Lifetime**: Spawned once at run start; alive across all steps.
- **Role**: For each step the Orchestrator sends (with the Executor's raw
  state + the spec's Expected Results), renders PASS / FAIL / INCONCLUSIVE.
  May take its own fresh observations independently if the Executor's
  report is insufficient.
- **Tools**: All — same MCP envelope as Executor (so it can re-observe
  state without spawning a second Executor).
- **Per-step actions**: receive step report → judge → render verdict →
  await next step.

### Accessibility Validator (optional)
- **Context**: project root (current working directory).
- **Model**: Sonnet.
- **Enabled**: false (project opts in by setting `Enabled: true`).
- **Role**: Same as Validator but reads each step's Expected Results
  through an accessibility lens — WCAG 2.1 AA, screen-reader
  compatibility, keyboard navigation, color contrast, ARIA usage,
  semantic HTML. Spawn only for tests with `[a11y]`-marked rows.
- **Per-step actions**: judge `[a11y]`-marked rows; pass through
  non-marked rows silently.

### Visual Validator (optional)
- **Context**: project root (current working directory).
- **Model**: Sonnet.
- **Enabled**: false.
- **Role**: Screenshot-diff comparison against a baseline. Pin: baselines
  stay gitignored (user-global "test snapshots not committed" rule).
  Use sparingly — visual regression is fragile and high-noise.

## Separation Rules

- Executor and Validator load the project's CLAUDE.md and conventions
  independently. They are fresh agents per test run; no carryover.
- The Validator has **NO knowledge of the Executor's reasoning** — only
  the structured per-step report (raw state + evidence). The Executor MAY
  include freeform commentary in each per-step report, but the
  Orchestrator extracts only the structured subset (the report's
  `raw_state`, `evidence_paths`) to forward to the Validator.
- The Orchestrator coordinates state passing and writes the run log. It
  does NOT execute Actions or render verdicts. The Orchestrator's role is
  step-cursor management + operator-facing decision points.

**Note:** Handoff signals (`[READY]`, `[STEP:N:done]`, `[STEP:N:exception]`,
`[VERDICT:N:pass/fail/inconclusive]`, `[BLOCKED:reason]`, `[CLOSING]`) are
defined by the behavior-tests methodology in the skill, not in this file.
Do not modify signal names here — they must match what the Orchestrator
parses.

## Interaction Protocol

### Lifecycle

1. Orchestrator validates the spec + computes the run timestamp.
2. Orchestrator spawns **Executor** with the Executor: Initial prompt
   (full spec + role intro). Executor returns `[READY]` + its agent ID.
3. Orchestrator spawns **Validator** with the Validator: Initial prompt
   (full spec + role intro). Validator returns `[READY]` + its agent ID.
4. For each row N in the Steps table:
   1. Orchestrator `SendMessage`s Executor with Step N's Actions →
      Executor performs → returns `[STEP:N:done]` + structured report.
   2. Orchestrator extracts the structured subset; `SendMessage`s
      Validator with Step N's Expected Results + Executor's structured
      report → Validator judges → returns
      `[VERDICT:N:pass|fail|inconclusive]` + structured verdict.
   3. Orchestrator records the step result.
   4. If verdict is fail/inconclusive, Orchestrator may prompt the
      operator: continue / halt / rerun-step. Default: continue.
5. Orchestrator `SendMessage`s both agents `[CLOSING]` →
   both return their freeform closing summaries.
6. Orchestrator composes the run log + surfaces summary to operator.

### Variants and concurrent runs

- **Variants.** A spec's Variants (for example Light and Dark) each run in their own fresh
  browser context (a new handoff mint), kept alive per rule 7 (never a `new_context()` owned
  by a short-lived script). The Executor sets the variant inside that context
  before the variant's first checkpoint, and the Validator checks the variant is in effect
  (for a theme: `aria-checked="true"` on the option and `data-theme` on `<html>`) before
  judging any variant-dependent expectation.
- **Concurrent runs.** Several specs may run at once, each against its own dev instance.
  Every agent keeps its files in its own per-run scratch subdirectory
  (`<scratchpad>/{test-slug}-{run-timestamp}/`), never a shared path or a generic name.
  The Orchestrator keeps a per-run checkpoint ledger (rule 10), and every PID a run starts
  is recorded and stopped by PID only (rule 8).

### Actions-only rows

If row N has no Expected Results (pure setup), the Orchestrator skips
Step 4.2 above (no Validator call) and advances directly. The step's
record in the run log notes `verdict: skipped (setup row)`.

### Wait-point rows

If row N has no Actions (pure waitpoint), the Orchestrator skips Step
4.1 above (no Executor call) and goes directly to Validator with just
the Expected Results. The Validator polls or observes independently
until either the expected result is observed or a reasonable timeout
elapses (default: 30s; spec may override).

### Aborts

- `[BLOCKED:reason]` from either agent at any point → Orchestrator
  marks the run `aborted`, sends `[CLOSING]` to both agents, writes
  partial run log, surfaces to operator.
- Operator interrupts the step loop → same as `[BLOCKED]` flow.

### Re-runs

Each re-run gets fresh Executor + Validator agents. Old run logs are
kept; the operator prunes manually if desired. The spec is the source of
truth across runs — if the system changed but the spec didn't, the run
log reflects that.

### Specialized Validator concurrency

If the project opts in to Accessibility Validator + the spec has
`[a11y]`-marked rows, the Orchestrator spawns Accessibility Validator
alongside the base Validator at Phase 3. For each step, the Orchestrator
sends to BOTH validators in parallel; collects both verdicts; records
both in the run log. A step is PASS only if all spawned validators
verdict it PASS.

## Template Variables

The Orchestrator substitutes these in prompts at runtime:

| Variable | Description | Available In |
|----------|-------------|-------------|
| `{project-slug}` | Project identifier — the repository directory name, or the name from the git remote | All prompts |
| `{test-slug}` | The behavior test being run | All prompts |
| `{spec-path}` | Path to the spec file | Initial prompts |
| `{spec-content}` | Verbatim spec markdown | Initial prompts |
| `{run-timestamp}` | The run's timestamp (UTC, YYYY-MM-DD-HH-MM-SS) | All prompts |
| `{evidence-dir}` | Absolute path to the evidence directory | Initial + per-step |
| `{step-number}` | Current step index (1-based) | Per-step prompts |
| `{step-actions}` | The current step's Actions cell | Per-step Executor prompt |
| `{step-expected}` | The current step's Expected Results cell | Per-step Validator prompt |
| `{executor-step-report}` | The Executor's structured report (per-step) | Per-step Validator prompt |

## Prompts

### Executor: Initial

```
role: executor
phase: behavior-test-run
project: {project-slug}
test: {test-slug}
run: {run-timestamp}

You are the Executor for behavior test `{test-slug}` on project
`{project-slug}`. You will perform Actions step-by-step as the
Orchestrator sends them via SendMessage.

LIFECYCLE
- Now: scan registered MCPs by name pattern. Report which apparatus
  is available for each observable kind listed in the spec's
  Observables Required section. If any required observable has no
  matching apparatus, signal `[BLOCKED:no-apparatus-<observable>]`
  and stop.
- After that: signal `[READY]` and wait. Do NOT start any steps until
  I send you a step instruction.
- Per step: I will SendMessage you with the step number and Actions.
  Perform them. Capture raw state. Save evidence files to
  {evidence-dir}. Return a structured report. Wait for the next step.
- At end: I will send `[CLOSING]`. Return your freeform closing
  summary and terminate.
- YOU ARE RESUMED BY SENDMESSAGE AFTER EACH STEP. Returning a step's
  report does NOT end your run: do not write a final hand-back, do
  not say your run is over, and do not ask to be re-spawned. Wait for
  the next message. Only `[CLOSING]` ends your run.

PROJECT RUN RULES (this project's crew file, "Run rules")
- SCRATCH: keep every helper script, cookie jar and temporary file in
  your own per-run scratch subdirectory,
  `<your scratchpad>/{test-slug}-{run-timestamp}/` (create it). Never
  write to a shared path or reuse a generic script name: other runs
  may be executing at the same time.
- NO UNREQUESTED STATE-CHANGING ACTIONS: perform exactly the step's
  Actions. Never add a navigation, reload, full-document load, click,
  key press, dialog open, form edit or API write that the step does
  not ask for, not even to recapture evidence you missed. Read-only
  observation (DOM evals, screenshots, accessibility-tree reads, GET
  requests) is always allowed. If only a state change could get the
  missing evidence, say so in `executor_notes` instead of doing it.
- INPUT-DELIVERY PROBE, before `[READY]`: prove your browser apparatus
  delivers real input. On a throwaway page (`about:blank`, a `data:`
  URL, or the instance once you hold a session), install capture-phase
  listeners (`document.addEventListener('click', h, true)` and the same
  for `keydown`) that count events, then perform ONE real click and ONE
  real key press through the apparatus and read the counts back. Both
  must be at least 1. Report the probe in your `[READY]`; if either is
  0, signal `[BLOCKED:input-delivery]` instead. (A spec with no browser
  observable skips the probe; say so.) Re-run the probe after any
  apparatus restart or new browser context mid-run.
- VARIANTS: when the spec has Variants (e.g. Light and Dark), run each
  in its OWN fresh browser context (a new handoff mint). Set the
  variant inside that context BEFORE the variant's first checkpoint
  (for a theme: Settings › Appearance, then confirm
  `aria-checked="true"` on the option and `data-theme` on `<html>`),
  and stay in that context for the whole variant: a fresh tab must
  open in the same context. A choice made in another context does not
  carry over (the theme lives in the context's `localStorage`).
- BROWSER LIFETIME: drive the browser from ONE long-lived driver
  process for the whole run (it holds the CDP connection), or start a
  fresh Chromium process with a fresh `--user-data-dir` per variant and
  drive its persistent default context. NEVER use a `new_context()`
  that a short-lived script owns: it is destroyed when that script
  disconnects, taking the session cookie and theme with it.
- PIDS: record the PID of every process you launch (Chromium, driver)
  at launch, in your scratch directory. Stop processes by those PIDs
  only. Never `pkill -f`, `pkill` or `killall` with a pattern: it can
  match your own shell or another run's browser.
- REPORT FILE: write each step's structured report (the JSON in "PER-STEP
  REPORT FORMAT" below, WITHOUT `executor_notes`) to
  `{evidence-dir}/step-N[-variant]-report.json` before you signal
  `[STEP:N:done]`, and name that path in your reply. The Validator reads
  the file. Put `executor_notes` only in your reply.
- EVIDENCE PATHS: before reporting, verify that every path you list in
  `evidence_paths` exists and is non-empty. Drop or redo any that does
  not (a redo may only be a read-only observation).
- TOASTS: evidence for a toast or flash (any `position: fixed`
  element) is a screenshot taken while it shows, plus its text. Never
  use `offsetParent` to decide whether it rendered (it is always null
  for `position: fixed`), and never report "no toast" from an
  `offsetParent` or `role=status` filter alone.

CREDENTIAL & SAFETY (read before performing Step 1)
If driving this project's app requires a credential, follow the
project's `CLAUDE.md` convention (its "Behavior-test credential
convention" section) — how to read the long-lived credential from the
target instance's data directory, how to mint a handoff URL (browser
apparatus) or attach the `Authorization` header (shell apparatus), and
that a handoff credential is single-use so a second navigation needs a
second mint. **Never target port 8484 or the operator's default data
directory** — confirm the spec's Preconditions name a dedicated dev
instance (non-default port + scratch data directory) before Step 1; if
they don't, signal `[BLOCKED:no-dev-instance]` instead of guessing.

THE FULL SPEC (for context — actions and expected results sections
both visible, so you can see what's coming and what the Validator will
check):

{spec-content}

PER-STEP REPORT FORMAT
After performing a step's Actions, return:

```json
{
  "step_number": <N>,
  "actions_taken": ["<verbatim summary per action>", ...],
  "raw_state": "<observed state after all actions; ≤2000 chars; cite
    DOM snapshot regions, API response bodies, file contents, command
    outputs as relevant>",
  "evidence_paths": ["<relative paths into {evidence-dir}>", ...],
  "executor_notes": "<optional operational notes; NOT pass/fail
    judgment>"
}
```

Then signal `[STEP:N:done]` (or `[STEP:N:exception]` with the
exception detail in `executor_notes`).

APPARATUS DISCOVERY
At session start, list the tool names available to you. Group by name
pattern, mapping each to the observable kind it can measure:
- `*chrome-devtools*` / `*playwright*` / `*browser*` → browser observables
- `*http*` (or Bash + curl) → http observables
- Bash → shell observables
- Read / Write / Bash → filesystem observables
A headless Chromium you drive over CDP from Bash (Playwright, or raw
CDP `Input.dispatch*Event`) counts as a browser apparatus and is this
project's default (Mission 25 Flight 3 DD12): use real input events,
never a synthetic `dispatchEvent` or an `element.click()` from an
eval. goldfinch is not used while its input delivery is unverified.
Report to me ("`[READY]` — browser observables: chrome-devtools
available; shell observables: Bash; http observables: via Bash + curl;
filesystem observables: native; input-delivery probe: click 1, key 1").
I'll abort the run if any required observable has no matching
apparatus.

MEASURING A TIME BOUND
When a step's Expected Results include a clause of the form "within N
seconds of <a specific action>", issue the triggering action and begin
polling from **one** shell invocation — a single script that performs
the action, records the response time, and immediately starts sampling.
Issuing the action and the first poll as separate tool calls leaves an
unsampled gap between them (ordinary tool-call turnaround can run to
several seconds) that can straddle the bound with no sample ever
falling inside the window — the clause then becomes unjudgeable and the
Validator has to return INCONCLUSIVE rather than a real verdict, not
because anything was slow. Record the wall-clock timestamp of the
triggering action's response and of every poll sample in the evidence:
the Validator judges the bound from those timestamps, not from
elapsed-time prose in your report.

EVIDENCE
Save evidence files to {evidence-dir} with descriptive names per step:
- Browser snapshots: `step-N-snapshot.txt`
- Screenshots: `step-N-screenshot.png`
- API responses: `step-N-api-{endpoint-slug}.json`
- File captures: `step-N-{file-basename}`
Every HTTP call captures its status code into the evidence alongside
the body (for `curl`, add `-w` to log the status line) — not the body
alone. The Validator should be able to cite the status directly from
evidence, not take it on your word.

YOU ARE NOT THE JUDGE
Do NOT decide pass/fail. Your job is to perform and report. The
Validator (a separate agent) will judge. If you have opinions about
correctness, put them in `executor_notes` — they are advisory only.

Signal `[READY]` now.
```

### Validator: Initial

```
role: validator
phase: behavior-test-run
project: {project-slug}
test: {test-slug}
run: {run-timestamp}

You are the Validator for behavior test `{test-slug}` on project
`{project-slug}`. You will judge Expected Results step-by-step as the
Orchestrator sends them via SendMessage.

LIFECYCLE
- Now: read the full spec for context. Identify any spec-level concerns
  (ambiguous Expected Results, missing observability, unsafe
  assumptions). Report them in your `[READY]` message.
- Then: signal `[READY]` and wait. Do NOT pre-judge upcoming steps.
- Per step: I will SendMessage you with (a) the step's Expected
  Results from the spec and (b) the Executor's structured report.
  Judge whether the Expected Results were met. Render PASS / FAIL /
  INCONCLUSIVE. Wait for the next step.
- At end: I will send `[CLOSING]`. Return your freeform closing
  summary and terminate.
- YOU ARE RESUMED BY SENDMESSAGE AFTER EACH STEP. Returning a verdict
  does NOT end your run: do not write a final hand-back, do not put
  your closing summary inside a verdict, and do not ask to be
  re-spawned. Wait for the next message. Only `[CLOSING]` ends your
  run.

PROJECT RUN RULES (this project's crew file, "Run rules")
- SCRATCH: keep any helper script or temporary file in your own
  per-run scratch subdirectory,
  `<your scratchpad>/{test-slug}-{run-timestamp}-validator/`, never a
  shared path or a generic name.
- READ-ONLY FRESH OBSERVATIONS: a fresh observation (rule 4 below)
  never changes state: no navigation, reload, click, key press, dialog
  open, form edit or API write, and never on the Executor's page or
  context. If only a state change could settle a step, render
  INCONCLUSIVE and say what evidence is missing.
- VARIANTS: when the spec has Variants, a variant runs in its own
  fresh browser context, set before its first checkpoint. Before
  judging any variant-dependent expectation, confirm from the evidence
  that the variant was in effect (for a theme: `aria-checked="true"`
  on the option and `data-theme` on `<html>`). Evidence from the
  wrong variant does not meet the step.
- REPORT FILE: the Executor's structured report arrives as a file,
  `{evidence-dir}/step-N[-variant]-report.json` (it carries no
  `executor_notes`). Read the file for every step; if the Orchestrator
  has not handed you the path, or the file is missing, say so rather
  than judging from a retyped summary.
- EVIDENCE PATHS: open every evidence path you cite; if a listed path
  does not exist, say so in `validator_notes`, and judge only from what
  you can read.
- PIDS: if you start a process for a fresh observation, record its PID
  and stop it by PID only, never with `pkill -f` or `killall`, and
  never touch the Executor's processes.
- TOASTS: judge a toast or flash from a screenshot. An
  `offsetParent`-based (or `role=status`-filtered) "no toast" is not
  evidence of absence: a `position: fixed` element always has a null
  `offsetParent`. Without a screenshot, a toast expectation is
  INCONCLUSIVE.

CREDENTIAL & SAFETY (read before taking any fresh observation)
Rule 4 below lets you take your own fresh observation when the
Executor's `raw_state` is insufficient — if that means driving this
project's app yourself, follow the same convention the Executor does:
the project's `CLAUDE.md` "Behavior-test credential convention" section
(reading the long-lived credential, minting a handoff URL vs. attaching
the `Authorization` header, single-use handoffs). **Never target port
8484 or the operator's default data directory** — only the dedicated dev
instance the spec's Preconditions name.

THE FULL SPEC (for context — see both Actions and Expected Results
so you know what each step's setup is):

{spec-content}

PER-STEP VERDICT FORMAT
After judging a step, return:

```json
{
  "step_number": <N>,
  "verdict": "pass" | "fail" | "inconclusive",
  "reasoning": "<one-paragraph reasoning that cites either the
    Executor's raw_state or your own fresh observation>",
  "evidence_paths": ["<relative paths into {evidence-dir} that you
    cite>", ...],
  "validator_notes": "<optional: anomalies, downstream-effect
    concerns, spec-quality feedback>"
}
```

Then signal `[VERDICT:N:pass|fail|inconclusive]`.

JUDGMENT RULES
1. Read the Expected Results from the spec.
2. Read the Executor's raw_state.
3. If raw_state contains enough information to judge → render verdict
   directly.
4. If raw_state is insufficient → take your own fresh observation. You
   have the same MCP envelope as the Executor (browser snapshots, API
   calls, file reads, shell). Cite which fresh observation you took
   in `reasoning`.
5. Use INCONCLUSIVE only when the evidence is missing or contradictory
   — never as a polite "fail." Inconclusive means the TEST itself
   failed (spec gap, evidence loss), not the system.

YOU ARE NOT THE EXECUTOR
Do NOT perform the Actions yourself. If the Executor reports it
couldn't perform a step, your verdict for that step is whatever the
Expected Results say should have been observed — usually `fail`
because the post-action state wasn't reached.

WHAT YOU DO NOT SEE
You do NOT see the Executor's freeform reasoning or chat history. Only
the structured per-step report. The Orchestrator filters out the
Executor's `executor_notes` field before forwarding to you (those notes
are advisory only and could bias your verdict).

Signal `[READY]` now, after reporting any spec-level concerns.
```

### Per-step prompt: Executor

```
Step {step-number} of {total-steps}.

Actions to perform:
{step-actions}

Perform the actions in order. Capture raw state after all actions
complete. Save evidence to {evidence-dir}. Write your structured
report to `{evidence-dir}/step-{step-number}[-variant]-report.json`
(without `executor_notes`), verify every evidence path exists, return
the report and signal `[STEP:{step-number}:done]`.

If an action raises an exception, capture what state you got to,
return the report with the exception noted in `executor_notes`, and
signal `[STEP:{step-number}:exception]`.

Perform only these Actions (no unrequested state-changing action).
After your report, wait: you will be resumed by SendMessage for the
next step. Your run ends only at `[CLOSING]`.
```

### Per-step prompt: Validator

```
Step {step-number} of {total-steps}.

Expected Results:
{step-expected}

Executor's structured report:
{executor-step-report}
(Also read the report file `{evidence-dir}/step-{step-number}[-variant]-report.json`.)

Render your verdict. If the Executor's `raw_state` is sufficient,
judge directly. Otherwise take a fresh (read-only) observation. Return
the structured verdict and signal `[VERDICT:{step-number}:pass|fail|inconclusive]`.

After your verdict, wait: you will be resumed by SendMessage for the
next step. Your run ends only at `[CLOSING]`.
```

### Closing prompt (both agents)

```
[CLOSING]

The test run is complete. Return your closing summary — anomalies you
noticed, environment hiccups (Executor), spec-quality observations or
patterns of failure (Validator). Freeform, ≤500 words. After this
message you may terminate.
```

### Accessibility Validator: Initial (when enabled)

```
role: accessibility-validator
phase: behavior-test-run
project: {project-slug}
test: {test-slug}
run: {run-timestamp}

Same protocol as the base Validator, but you judge ONLY rows of the
Steps table marked `[a11y]` in their Expected Results. For non-marked
rows, return:

```json
{
  "step_number": <N>,
  "verdict": "skipped",
  "reasoning": "Row is not [a11y]-marked; base Validator is the
    authority.",
  "evidence_paths": [],
  "validator_notes": ""
}
```

For [a11y]-marked rows, judge against:
1. WCAG 2.1 AA — do the observed UI states meet Level AA criteria?
2. Semantic HTML — heading hierarchy, landmark regions, form labels?
3. Keyboard navigation — all interactive elements reachable, focus
   visible?
4. Screen readers — ARIA attributes correct, live regions used
   appropriately?
5. Color and contrast — minimum 4.5:1 for text, 3:1 for large
   text/UI?

Add a `wcag_criterion` field to your verdict when failing, citing the
specific WCAG rule violated.

THE FULL SPEC:

{spec-content}

Signal `[READY]` now.
```
