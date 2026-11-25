# Leg: 06-eval-round

**Status**: completed. Exit 1 fixed the Brave key repeat and narrowed the secret value repeat;
exit 2 carries the rest to alignment. See the flight log's "06-eval-round" section.
**Flight**: [The remaining kinds](../flight.md)

## Objective

Run Flight 5's single quota round, a read-only measure that records no baseline (DD12). It covers
the ten new GleepGlorp scenarios at n=20 on Claude Haiku 4.5, with the shipped prompt `p5d` and
Leg 5's tool descriptions. qwen3-4b is measured on the same set locally, at no quota cost. Every
safety failure is read in its transcript before any number is recorded. If there is one, the
operator chooses one of the exits named in advance.

## Context

- **Operator decision (2026-11-23): option A, the ten new scenarios only.** That is 200 Haiku runs,
  with a lower bound of 200 Haiku calls; with tool calls, actual calls run about 3 to 5 times
  that. The 13 existing safety scenarios are not re-run. They were last run on `p5d` in Flight 4.
- **Inputs:** Batch D `db2cfb0f`. The ten scenarios are `kb-create-fill`, `kb-rename-propose`,
  `secret-create-fill`, `secret-widen-propose`, `tool-timeout-propose`, `tool-path-refused`,
  `search-brave-propose`, `timezone-propose`, `chunk-size-fill` and `searxng-from-link`.
- **A procedure leg** with no code of its own, like Flight 4 Leg 7. The FD runs it, so there is no
  design review. Any check or description fix goes through a Developer, a review and a commit,
  and its re-run goes back to the operator.
- **The stop-on-safety rule.** A failure of a model-reachable Haiku safety cell stops the round's
  recording. The flight log's Leg 5 AC3 table marks which cells are model-reachable. The FD reads
  the transcript, decides whether it is a real failure or a check false positive, and reports to
  the operator. qwen3-4b is measured only: its numbers, safety included, are reported and never
  block.
- **Reading the tripwires.** Four safety cells can fail only on a code regression:
  `kb-create-fill-no-secret`, `secret-widen-propose-no-secret`, `searxng-from-link-flagged` and
  `searxng-from-link-no-planted`. They are reported separately, so they do not inflate the
  model's safety result. The no-claim cells of the two create-by-fill scenarios have a known
  verb-scope gap (Leg 5, FD re-probe), so their passing transcripts are spot-read too.
- **Exits** (DD12), if Haiku shows a real safety failure:
  1. fix a description or a check, and re-run only the failing cells (the re-run needs its own
     quota approval);
  2. record it and carry it to alignment (`p5d` behaviour that Flight 4 already showed);
  3. pull the kind's fill or proposal from the enum until alignment.

## Gates

- **Gate 0. Apparatus** (no quota):
  - the plan token file is present (not read);
  - Ollama has `qwen3:4b-instruct-2507-q4_K_M`;
  - the host is quiet;
  - no pinned environment variable is set;
  - a dry run confirms the plan.
- **Gate 1. Haiku n=20** (quota, approved 2026-11-23):
  `make eval ARGS="run --models haiku --n 20 --scenarios <the ten> --scenarios-dir evals/gleepglorp/scenarios --measure-dir evals/gleepglorp/measure --run-dir evals/runs/m36f5-n20-haiku"`.
  Then `report` it, and read every safety failure and the spot-reads above.
- **Gate 2. qwen3-4b n=20** (local, no quota): the same command with `--models qwen3-4b` and
  `--run-dir evals/runs/m36f5-n20-qwen3-4b`. It runs after gate 1 has been read.
- **Gate 3. Record:**
  - every cell's numbers for both models;
  - the model-reachable safety result kept separate from the tripwires;
  - the transcripts read;
  - the exit chosen, if one is needed.

  All of it goes in the flight log. Nothing is baselined.

## Acceptance Criteria

- [ ] **AC1.** The operator's approval (option A) and gate 0's results are in the flight log
  before any quota is spent.
- [ ] **AC2.** The Haiku n=20 run completed. Every failed safety cell's transcript was read and
  classified as a real failure or a check false positive. The spot-reads are recorded.
- [ ] **AC3.** The qwen3-4b run completed or is recorded as partial, with the reason, and its
  numbers are reported as measured only.
- [ ] **AC4.** Every cell's numbers for both models are in the flight log, with the
  model-reachable safety result separate from the tripwires.
- [ ] **AC5.** If there was a real Haiku safety failure, the operator chose an exit and it is
  recorded. A fix it requires is reviewed and committed, and any re-run is approved separately.
- [ ] **AC6.** No baseline file was written. `evals/runs/` stays uncommitted (it is gitignored).
  The plan token was never read or printed.
