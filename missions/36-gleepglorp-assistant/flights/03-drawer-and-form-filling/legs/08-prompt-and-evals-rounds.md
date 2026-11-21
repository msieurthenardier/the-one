# Leg: prompt-and-evals-rounds

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective

Choose GleepGlorp's prompt for pages and fills, under the adopted eval method
(`evals/README.md` "The eval method (M36 F2)", DD10), and ship it:
- run the operator-gated rounds;
- ship the winning candidate in `the_one/gleepglorp/prompt.py`;
- record `evals/baselines/m36f3-gleepglorp.json` at n=20 on Haiku and
  qwen3-4b on this flight's final scenario set (23 scenarios).

This is a procedure leg, like Flight 2's Leg 10.
- **Gates:** every round that spends quota sits behind an operator gate.
- **Who runs what:** the Flight Director runs the eval commands and reads
  the transcripts. Developers make any code, scenario or prompt edit, each
  reviewed and committed before the next quota round.
- **Fairness fixes:** a scenario or check fix found by the fairness pass is
  made, tested offline and committed before the screen, never during it.

## Inputs
- Leg 7 (`33c21bca`): candidates `p4` and `p4b`, the checks, and the five new
  scenarios (23 in the set). The cap is 550 tokens.
- The shipped prompt is `p3` (`evals/gleepglorp/prompts/p3.toml` reproduces
  it byte for byte).
- Carried from Leg 7's review: in `fill-after-fetch`'s `no_secret_in_fill`
  pattern, the term `(?i:shell commands)` could also match a legitimate
  prompt line. The fairness pass reads for that.

## Gates
0. **Apparatus, no quota.**
   - The plan token file is present (its contents are never read).
   - Ollama has the `qwen3-4b` entry from `evals/models.toml`.
   - `tiktoken` imports.
   - `run --dry-run` over the set for the planned run counts.
   - `uptime` and `ps`.
1. **Fairness pass.**
   - **Runs:** Haiku, n=1, the 5 new scenarios, on `p3` (control), `p4` and
     `p4b`, in parallel. That is about 15 conversations; `page-what-is` has
     two.
   - **Reading:** every transcript against each check: is each pass and fail
     deserved?
   - **Fixes:** go through a Developer, a review and a commit. Then a re-run
     of the touched scenarios only (gate 1b), approved again.
2. **Control and screen.**
   - **Runs:** Haiku, n=5, all 23 scenarios, on `p3`, `p4` and `p4b`, in
     parallel. That is 115 runs per prompt, 345 in all.
   - **Comparison:** a scratch baseline of `p3` under `--baselines-dir` in
     the session scratchpad (never `evals/baselines/`), then `compare` of
     each candidate.
   - **Reading:** totals and every safety cell. Zero safety failures is
     required of the winner.
3. **Shorten at the ceiling** (optional, operator's call). Drop one section
   phrase at a time from the winner. Each cut is a Haiku n=5 on the touched
   scenarios, kept only if no worse.
4. **Ship.** A Developer sets the shipped section constants to the winner,
   updates the `p3` byte-for-byte test to the new candidate (renamed), and
   updates `CLAUDE.md`, `the_one/agents.md` and the guide if needed. Then a
   review and a commit. The cap test passes at 550.
5. **Confirmation.**
   - **Runs:** Haiku and qwen3-4b, n=20, all 23 scenarios, on the shipped
     prompt. That is 460 runs per model.
   - **Record:** `evals/baselines/m36f3-gleepglorp.json`, with
     `derive-bars --size-ratio 1.0` and the harness default bars.
   - **Reporting:** the tool-description token cost (`fill_form`,
     `get_app_guide`) is reported with it.
   - **Rules:** qwen3-4b is measured only. Haiku must meet its bars with
     zero safety failures.
   - **Commit:** the baseline and the docs (`CLAUDE.md` "Prompt evals"
     names the new baseline) are committed.

## Acceptance Criteria
- **AC1.** Each quota gate has its operator approval recorded in the flight
  log before it runs. The record names the run directories, the prompt and
  scenario fingerprints, the wall time and `safety_fail`.
- **AC2.** The fairness pass leaves every new scenario's checks judged fair,
  with any fix committed before gate 2.
- **AC3.** The shipped prompt is the winner, at 550 tokens or fewer in all
  three variants, and `tests/test_gleepglorp_prompt.py` passes.
- **AC4.** `m36f3-gleepglorp.json` is committed. The Haiku cells meet their
  bars, and Haiku has zero safety failures. qwen3-4b's numbers are reported.
- **AC5.** No run touches port 8484 or 8485 or the default data directory
  (the harness guards this). The plan token is never printed. No run
  directory is committed.

## Safety
- Never read, print or log `~/.config/the-one-evals/plan-token`.
- Run directories stay under `evals/runs/` (gitignored). Scratch baselines go
  in the session scratchpad.
- A rate limit stops the round. It resumes only with `--resume` and a fresh
  approval if the plan changes.
