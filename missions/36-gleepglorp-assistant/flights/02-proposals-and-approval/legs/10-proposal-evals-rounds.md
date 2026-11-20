# Leg: proposal-evals-rounds

**Status**: ready
**Flight**: [Proposals and approval](../flight.md)

## Objective
Tune GleepGlorp's shipped prompt for proposals under the adopted eval method,
then ship it.
- The rounds run in order: fairness pass, same-prompt control, parallel
  screen, shortening, and one n=20 confirmation.
- The confirmation is recorded as `evals/baselines/m36f2-gleepglorp.json`.
- The winning prompt ships in `the_one/gleepglorp/prompt.py`, with a
  proposals topic in the app guide.
- Every round that spends quota is approved by the operator first.

## Context
- **Design:** flight DD11 (the prompt and guide) and DD13 (the method, the
  set, the baseline, qwen3-4b measured only).
- **Leg 9 set the sequence and the tools:**
  - the method in `evals/README.md`;
  - the approve and dismiss turns;
  - the proposal checks;
  - the extended scenario set (10 existing, 8 new, `no-change-claim`
    rewritten).
- **Candidates are prompt files**, `evals/gleepglorp/prompts/<name>.toml`, run
  with `make eval ARGS="run … --prompt-file …"` (`evals/README.md` "Candidate
  prompts and `--prompt-file`"). Spent candidates move to `history/`, as
  squawk 0390 did.
- **Runs:** a run is sequential, so parallel screening means separate
  invocations, each with its own `--run-dir` (as in Flight 1 Leg 9 Part B: six
  candidates, Haiku n=5, 300 runs in about 15 minutes).
- **This leg's shape** follows Flight 1's methodology observation 1 (an
  operator-gated, quota-spending leg). The leg is one artifact with explicit
  gates. Each gate is a recorded operator answer in the flight log, and each
  prompt text is committed before its round runs.
- **Prompt constraints:** the token cap is 450 tool-capable. The prompt must
  keep every Flight 1 safety behaviour, and it must:
  - drop the line that says it cannot change anything;
  - propose one step at a time;
  - say a change is proposed, not done;
  - read `fields` (and `fields_only`) before proposing;
  - never propose a delete or a secret;
  - send a secret or sign-in to its page.
- **Also prompt text:** the tool descriptions of `propose_change` and
  `read_app_config` count as prompt text. Changing them lands under this
  leg's runs.

## Gates and rounds
Each round, in order. The Flight Director shows the operator the run count,
the quota estimate and the reading rule, and waits for an answer before
starting.

0. **Apparatus re-verify.** No quota. Check:
   - the plan token at `~/.config/the-one-evals/plan-token` (exists; never
     read or printed);
   - Ollama with `qwen3-4b`;
   - `pip install -e ".[evals]"`;
   - a host quiet enough (load about 2 or less).
1. **Fairness pass (gate 1).**
   - One attempt per new or rewritten scenario on Haiku (9 runs) with the
     current D-min prompt and with the first candidate (18 runs).
   - Every transcript is reviewed against each check.
   - Unfair checks are fixed. A fix to a frozen scoring module needs another
     operator-approved re-pin, recorded.
2. **Control (gate 2).**
   - The new set on D-min, Haiku n=5 (18 scenarios × 5 = 90 runs).
   - The proposal scenarios are expected to fail: D-min says it cannot change
     anything.
   - This is the screen's control.
3. **Screen (gate 3).**
   - Three or four candidates, Haiku n=5, in parallel invocations (about
     270-360 runs).
   - Read only totals and safety cells, with the control alongside.
   - A candidate with any safety failure is out.
4. **Shortening (gate 4)**, only if the winner is at the ceiling.
   - Leave-one-out over the winner's sections, Haiku n=5 (about 90 runs per
     cut).
   - Keep a cut only if no worse.
5. **Confirmation (gate 5).**
   - The final prompt at n=20 on Haiku (360 runs) and qwen3-4b (360 local
     runs, no plan quota).
   - Then `baseline m36f2-gleepglorp <run-dirs>` and `derive-bars`, with the
     harness's default bars and size ratio 1.0, as in Flight 1.
   - `m36-gleepglorp.json` becomes history. The README and the CLAUDE.md
     Convention are updated.

**Rough plan quota: about 850-1300 Haiku runs in all.** Each round's exact
figure is shown at its gate.

## Acceptance Criteria
1. **Gate answers.** Every gate's operator answer is recorded in the flight
   log before its run, with the run ids and directories after it.
2. **Fairness first.** The fairness pass's findings and any check fixes are
   recorded before the control runs.
3. **Haiku meets its bars on the new baseline.**
   - Zero safety failures at n=20 on Haiku.
   - Haiku at or above the harness's default bars on every improve cell, or
     any cell below its bar is named with the operator's acceptance.
4. **qwen3-4b is measured and reported, safety included, and never gates.**
5. **The shipped prompt:**
   - `the_one/gleepglorp/prompt.py` holds the confirmed text;
   - the tool-capable prompt is 450 tokens or fewer;
   - `tests/test_gleepglorp_prompt.py` is green;
   - every link passes `check_route`;
   - Settings › Prompts shows it.
6. **Other agents unchanged.** The other agents' prompt and token cost are
   unchanged. `measure-prompt` on `evals/measure` matches
   `DEFAULT_MEASURE_PROMPT_FINGERPRINT`, so `tests/test_evals_fingerprint.py`
   is green.
7. **The app guide** gains a `proposals` topic: what the card shows, Approve,
   Dismiss, "Check this", and stale. `tests/test_gleepglorp_guide.py` is
   green.
8. **Recorded and tidied.**
   - The new baseline and its measure are committed.
   - Spent candidates are moved to `history/`.
   - The flight log has the round-by-round numbers.

## Verification Steps
- `make eval ARGS="compare --baseline evals/baselines/m36f2-gleepglorp.json --same-prompt …"`
  reproduces the bars on a re-run, if the operator wants a check.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_prompt.py tests/test_gleepglorp_guide.py tests/test_evals_*.py -x --timeout 60`;
  then `THE_ONE_TEST_NETNS=1 make test-unit`.

## Implementation Guidance
- **Who does what:**
  - A Developer writes the candidates and runs each approved round.
  - Each candidate file is reviewed (Reviewer, Sonnet) and committed before
    its round, as in Flight 1 Leg 9 Part B.
- **What the Flight Director brings to each gate:** a short table of cells
  and safety, plus the next round's plan.
- **Round runs:**
  - Every round runs in the background, with completion notifications, never
    timers.
  - Parallel screening means separate `make eval` invocations, each with its
    own `--run-dir`.

## Edge Cases
- **A safety failure in the confirmation** returns to the screen with the
  operator's direction, and is recorded.
- **A plan-token rate limit or error:** resume with `--resume`; never start a
  duplicate run.
- **Haiku's `propose_change` validity below its bar** (DD5's fallback):
  propose three tools to the operator as a deviation. Do not change it
  silently.

## Files Affected
- `the_one/gleepglorp/prompt.py`.
- `evals/gleepglorp/prompts/*.toml` (candidates, later moved to history).
- `evals/baselines/m36f2-gleepglorp.json`, `evals/README.md`, `CLAUDE.md`
  (the Convention).
- `the_one/gleepglorp/guide/proposals.md` (new) and the guide topic index.
- Possibly the descriptions in `the_one/gleepglorp/proposals/tool.py` and
  `read_tool.py`.

## Citation Audit
- `evals/README.md` "Candidate prompts and `--prompt-file`" (~L232-251): the
  candidate path and run commands — verified.
- `evals/gleepglorp/prompts/`: `dmin.toml`, `v1.toml`, `history/` — verified.
- Flight 1 flight log, Part B (~L310-356): six candidates screened at n=5 (300
  runs, about 15 minutes); prep reviewed before quota — verified.
