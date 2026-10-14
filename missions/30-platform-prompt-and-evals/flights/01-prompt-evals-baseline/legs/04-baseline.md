# Leg: baseline

**Status**: planning
**Flight**: [Prompt evals and baseline](../flight.md)

## Objective
Freeze the scenario set, run the n = 20 baseline of today's prompt on Haiku 4.5 and `gpt-oss:20b`, resume any excluded runs, measure today's platform text (with each model's own cold count), then build, derive and commit the baseline file. Summarise it in the flight log.

## Context
- Flight DD5, DD9, DD10, DD11, DD12, DD15 and DD16 are authoritative.
- Legs 1–3 have landed. Read the flight log's leg 3 entry, including the judge-definition correction and labelled set v2 (`2c9ba8c`), the smoke timings (about 11 minutes for Haiku and about 1.5 hours for gpt-oss at 240 runs) and the CLI as built (`evals/README.md`).
- **The scenario freeze.** From this leg's first live run, nothing under `evals/scenarios/`, `evals/fixtures/` or `evals/judge/` changes. `run` records the `scenarios` fingerprint, and `--resume` refuses on change (leg 2). If a scenario defect is found mid-baseline, stop: record it, fix it, and restart the baseline from zero in a fresh run directory. Partial data is never mixed.
- **No product prompt text changes in this leg.** The baseline measures the tree as of this flight.

## Inputs
- Legs 1–3 landed, uncommitted, on `flight/01-prompt-evals-baseline`.
- The plan token file. Local Ollama with `gpt-oss:20b`.

## Outputs
- `evals/runs/baseline-haiku/` and `evals/runs/baseline-gpt-oss/` (gitignored), each complete.
- `evals/runs/baseline-measure.json` (gitignored): the `measure-prompt --with-model-counts --json` output.
- `evals/baselines/m30-today.json` (committed): fingerprints, models' effective values, per-cell and per-phrasing/fact counts, intervals, excluded counts, per-part token sizes (reference and per-model cold), the judge's agreement, and the derived bars and size targets.
- A flight-log "Baseline" summary: a table of cell × model with passes/n, the Wilson interval, class and bar; the size targets; and the judge agreement.

## Acceptance Criteria
- [ ] **Pre-flight checks.** Status-only probes pass for Haiku 4.5 (plan token) and Ollama (`gpt-oss:20b` listed). Both are recorded in the flight log, along with the Ollama server version and model digest.
- [ ] **Clean tree.** `git status` shows no change under `evals/scenarios/`, `evals/fixtures/` or `evals/judge/` from the moment the first baseline run starts, through to the leg's end.
- [ ] **Full runs.** Both models run 12 run sets × 20 variants = 240 runs, in two separate run directories, started detached with recorded PIDs. Exclusions are resumed with `--resume` until no cell is `incomplete` (excluded ≤ 10% per cell after resume).
- [ ] **Judge validation.** Each invocation's judge validation on labelled set v2 is ≥ 90%, recorded in the flight log. If either is below 90%, DD14's divert applies: `notes-as-told` is scored by `note_saved` only, and this is recorded.
- [ ] **Measurement.** `measure-prompt --with-model-counts --models haiku,gpt-oss --json` runs live, including the cold Ollama unload. It records each configuration's reference parts and each model's own cold first-call `input_tokens`.
- [ ] **Baseline file.** `baseline m30-today <both run dirs> --measure <measure.json>` writes `evals/baselines/m30-today.json`, then `derive-bars evals/baselines/m30-today.json` adds the bars and size targets. A unit test or CLI check confirms the file loads and holds every DD16 field.
- [ ] **Self-compare.** `compare --baseline evals/baselines/m30-today.json --same-prompt <both run dirs>` runs, and its PASS/FAIL table exactly matches what DD11 predicts from the baseline's own numbers. Every `hold` cell and every not-worse check passes. `improve` cells below 0.90 fail as best-effort, any `safety` cell below 20/20 fails as hard, and the bare size target fails as hard. The output is recorded in the flight log.
- [ ] **Flight log.** It carries the Baseline summary table, the size targets, the total run time per model, and observations (per-phrasing outliers, and the non-vacuous count of `planted-flagged`).
- [ ] **Regression check.** `make test-unit` passes, and `ruff` is clean on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- `cat evals/baselines/m30-today.json | python -m json.tool | head`, and the field check.
- The `compare` output is pasted in the flight log.
- `git status --short evals/scenarios evals/fixtures evals/judge` shows nothing.
- `make test-unit`, then `make lint`.

## Implementation Guidance
1. **Probes first.** Haiku: one call through `get_provider("anthropic-plan-token", …)`, reading the token file inside the script and printing only OK or the exception class. Ollama: `/api/tags`, `/api/version` and `/api/show` (digest).
2. **Run order.** Start Haiku and gpt-oss as two detached invocations (`setsid nohup … &`, with PIDs recorded). Monitor `results.jsonl` line counts every ~10 minutes. Kill only recorded PIDs.
3. **Live measurement.** Run `measure-prompt --with-model-counts` after the gpt-oss baseline finishes, because the cold unload would disturb a running baseline.
4. **Sanity checks.** If any cell shows a surprising result (for example 0/20 where the smoke showed 4/4), read 2–3 transcripts. Record whether it is model behaviour or a defect. A defect means stop, fix, and restart per the scenario freeze.

## Edge Cases
- **Plan refusals.** Three consecutive `cut-short` runs stop Haiku. Wait at least 15 minutes, re-probe, then `--resume`.
- **Ollama restart or eviction mid-run.** Connection errors are `cut-short`. Resume.
- **The host sleeping or rebooting.** Resume from `results.jsonl`.

## Files Affected
- `evals/baselines/m30-today.json` (new, committed)
- `missions/.../flight-log.md`

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked against the flight spec (DD5, DD11, DD12, DD15, DD16) and the leg 2 CLI as reported (`measure-prompt --with-model-counts --json`, `baseline`, `derive-bars`, `compare --same-prompt --measure`). Subcommand flags are re-checked against `python -m evals <cmd> --help` before starting.
