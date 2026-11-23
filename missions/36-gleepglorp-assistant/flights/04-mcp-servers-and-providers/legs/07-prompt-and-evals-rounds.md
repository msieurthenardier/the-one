# Leg: 07-prompt-and-evals-rounds

**Status**: completed with a recorded disposition. AC5 is not met: the baseline was not recorded. The operator paused the evals
on 2026-11-22 after two n=20 runs found 4 and 9 Haiku safety failures. See the flight log.
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Choose and ship GleepGlorp's prompt for MCP servers and providers, and record the n=20 baseline
`evals/baselines/m36f4-gleepglorp.json` on the new scenario set. The method is "The eval method
(M36 F2)", with every quota round approved by the operator first.

## Context

- **Flight DD12 and DD13.** Legs 6a and 6b (Batch C, `21ea0705`) prepared everything offline:
  - **The set:** 32 scenarios. The cells changed with the `fill-after-fetch` split, so
    `m36f3-gleepglorp.json` cannot be compared, and this leg records a same-set re-baseline.
  - **Candidates:**
    - `p5a`: the three DD12 lines reworded;
    - `p5b`: `p5a` plus the "quote a refused value" rule;
    - `p5c`: an alternative no-copy wording.

    The shipped `p4c` is the control.
  - **The tool-description growth:** +24 tokens, within DD12's 120-token target.
- **This is a procedure leg** with no code of its own, like Flight 3 Leg 8. The one code change,
  the ship at gate 4, goes through a Developer, a Reviewer and a commit.
- **FD tiering: no design review.** Every quota round goes through the operator, and every code
  change through review.
- **The stop-on-safety rule.** Any **safety** cell failure on Haiku stops the round. Before
  anything is recorded, the FD reads the transcript and decides whether it is a real failure or
  a check false positive, and reports to the operator. qwen3-4b is measured only: its numbers,
  safety included, are reported and never block.

## Gates

- **Gate 0. Apparatus** (no quota). Done 2026-11-21:
  - the plan token file is present (not read);
  - Ollama has `qwen3:4b-instruct-2507-q4_K_M`;
  - the dry runs (lower bounds, one call per user turn):
    - fairness: 9 calls per prompt;
    - screen at n=5: 160 runs and at least 175 calls per prompt;
    - n=20 confirmation: at least 1400 calls (700 Haiku, 700 local qwen3-4b).

  Actual calls run about 3 to 5 times the lower bound with tool calls.
- **Gate 1. Fairness pass** (quota). Haiku n=1 on the nine new scenarios, on `p4c` and `p5a`
  (18 runs, at least 18 calls). The FD reads every transcript against each check. A check that
  fails for a correct reply, or passes a wrong one, is fixed offline before gate 2, through a
  Developer, a review and a commit. A fix to a frozen file is re-pinned by the FD under the
  2026-11-20 ruling.
- **Gate 2. Screen** (quota). Haiku n=5 on all 32 scenarios, for `p4c` (control) and `p5a`,
  `p5b`, `p5c`, in parallel run directories `evals/runs/m36f4-screen-<prompt>`. The FD reads
  totals and safety cells only, and reports a table to the operator with a recommendation.
- **Gate 3. Shortening** (optional; quota only if the operator wants it). It drops one section
  at a time from the chosen candidate, keeping a cut only if the result is no worse.
- **Gate 4. Ship** (code, no quota). A Developer makes the operator-chosen candidate the shipped
  prompt:
  - the constants in `the_one/gleepglorp/prompt.py`;
  - the `p4c`-style byte-for-byte pin test for the new file;
  - the platform prompt pins (`tests/_platform_prompt_pins.py`, if GleepGlorp's are there).

  Then a Reviewer and a commit.
- **Gate 5. Confirm and baseline** (quota). Haiku and qwen3-4b n=20 on all 32 scenarios with the
  shipped prompt. Then `baseline m36f4-gleepglorp <run-dirs>`, with bars from `derive-bars`.
  - Haiku must meet the pass bar with **zero safety failures**.
  - The baseline file and the flight-log record of every cell are committed.

## Acceptance Criteria

- [ ] **AC1.** The operator approved each quota gate before it ran, and the approvals are in the
  flight log.
- [ ] **AC2.** The fairness pass was read against every new check. Any check fix landed through
  a review and a commit before gate 2.
- [ ] **AC3.** The screen table (totals and safety cells per prompt) is in the flight log, with
  the operator's choice.
- [ ] **AC4.** The chosen prompt is shipped (gate 4), reviewed and committed. Its measured size is
  at most 550 tokens per variant, and its pins are updated.
- [ ] **AC5.** `evals/baselines/m36f4-gleepglorp.json` is recorded from the n=20 runs, Haiku has
  zero safety failures, and every cell's numbers are written into the flight log.
- [ ] **AC6.** The `SECURITY-MODEL.md` and `evals/README.md` text naming the shipped prompt and
  baseline is current.

## Citation Audit

- `evals/README.md` "The eval method (M36 F2)"; the `run` options `--scenarios-dir`,
  `--measure-dir`, `--prompt-file`, `--n`, `--models` and `--dry-run` — verified (README
  Commands table).
- The dry-run counts above — measured 2026-11-21 at `21ea0705`.
