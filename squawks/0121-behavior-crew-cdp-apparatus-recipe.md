# Squawk 0121: The behavior-test crew file has no CDP apparatus recipe or concurrent-run rules

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: 2026-10-06

## Report

The crew file names a CDP-driven headless Chromium with real input as the project's default
browser apparatus, but gives no recipe for driving it across steps. At the Mission 25
Flight 4 close gate:
- **Contexts died between steps.** Three of five Executors created per-variant contexts
  with Playwright `browser.new_context()` over `connect_over_cdp`. Such a context is
  destroyed when the driving script disconnects, so the session cookie and theme were lost.
  - Cost: one apparatus re-run (`chat-roundtrip` step 3), one step redone
    (`shell-navigation-smoke` step 1) and a mid-run advisory to every Executor.
- **A pattern kill killed its own shell.** One Executor's `pkill -f
  "remote-debugging-port=…"` matched its own shell. Another run's Chromium also exited at
  the same time, cause not established. A PID-only rule went out mid-run.
- **Two improvised patterns worked** and belong in the file:
  - the **report-file hand-off**: the Executor writes `step-N[-variant]-report.json` without
    its notes, and the Validator reads the file;
  - a **per-run checkpoint ledger** for concurrent runs. One hand-off was still skipped in
    a burst of reports and judged late.

Source: the Flight 4 debrief, recommendation 2 and methodology observations 4–5.

## Evidence

- `.flightops/agent-crews/behavior-tests-execution.md`:
  - "Run rules (this project)", rule 3: it names the CDP Chromium but not how to keep its
    state across steps;
  - "Variants and concurrent runs": per-run scratch only.
- Run logs `tests/behavior/{chat-roundtrip,start-a-chat,shell-navigation-smoke}/runs/2026-10-06-06-01-26.md`
  (Orchestrator Notes, Executor closing).

## Corrective Action

Added to `.flightops/agent-crews/behavior-tests-execution.md`:
- **Run rules 7 to 11** (the list now reads "Eleven rules"): driver and browser lifetime
  (one long-lived driver per run, or a fresh Chromium process with a fresh
  `--user-data-dir` per variant driven through its persistent default context, never a
  `new_context()` a short-lived script owns); PIDs recorded at launch and stopped by PID
  only (never `pkill -f` or `killall` with a pattern); the report-file hand-off
  (`step-N[-variant]-report.json` without `executor_notes`, read by the Validator); the
  Orchestrator's per-run checkpoint ledger for concurrent runs; and, from Flight 5, verify
  every evidence path exists before reporting.
- **The prompts where each acts:** the Executor Initial prompt gains BROWSER LIFETIME, PIDS,
  REPORT FILE and EVIDENCE PATHS; the Validator Initial prompt gains REPORT FILE, EVIDENCE
  PATHS and PIDS; the per-step Executor and Validator prompts name the report file.
- "Variants and concurrent runs" now points at rules 7, 8 and 10.
Signal names, `## Crew`, `## Interaction Protocol`, `## Prompts` and every fenced prompt are
unchanged.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

- A parse check: the file has `## Crew`, `## Interaction Protocol` and `## Prompts`, and
  each of the six `###` prompt subsections under `## Prompts` holds a fenced block.
- A re-read shows each rule in the rationale list and in the prompt that acts on it.
- The next behavior run's Executors following it without a mid-run advisory is the open
  observation, for the next run.

## Sign-Off

**Reviewer**: Developer agent, Mission 25 Flight 6 leg 3 (the flight-end review confirms)
**Verdict**: confirmed
**Commit**: pending the Flight 6 legs 1-3 commit
