# Squawk 0121: The behavior-test crew file has no CDP apparatus recipe or concurrent-run rules

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: —

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

*(written at completion)*

Add to the crew file's run rules, and to the Executor and Validator prompts where they act:
- **Driver or browser lifetime:**
  - one long-lived driver process per run holding the CDP connection, or a fresh Chromium
    process with a fresh `--user-data-dir` per variant, driving its persistent default
    context;
  - never a `new_context()` that a short-lived script owns.
- **PIDs:** record them at launch and stop only those (never `pkill -f` or `killall` with
  a pattern).
- **The report-file hand-off** above.
- **For concurrent runs:** an Orchestrator ledger, one line per checkpoint, and a check
  that every Executor step was handed to the Validator before the next step is sent.

Keep the file's required sections, signal names and fenced prompts intact.

## Verification

- The file still has `## Crew`, `## Interaction Protocol` and `## Prompts`, with every
  prompt in a fenced block.
- A re-read shows each rule in both the rationale list and the prompt that acts on it.
- The next behavior run's Executors follow it without a mid-run advisory.

## Sign-Off

*(written at completion)*
