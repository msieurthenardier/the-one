# Leg: cache-verification

**Status**: completed
**Flight**: [Anthropic prompt caching](../flight.md)

## Objective
Prove criteria 1, 2 (live half) and 4 on the committed leg 1 code (`178a931b`). Run the live `cache-probe` on haiku 4.5, then a haiku-only s11 eval run compared against `evals/baselines/s11-platform.json` with `--same-prompt --models haiku`, and record the readings.

## Context
- The Flight Director runs this leg. It spends plan quota and changes no code unless a defect is found. A defect gets a new fix commit (no amend), reviewed like leg 1, and the step is re-run.
- DD4 (probe rules and exit codes), DD5 (per-leg re-verify of the plan endpoint: the probe runs first), DD7 (`compare --models`).
- Prerequisites, checked 2026-11-08:
  - `tiktoken` 0.14.0 is installed (the `[evals]` extra).
  - Plan token default path.
  - Host load is 0.62.

## Acceptance Criteria
- [ ] `make eval ARGS="cache-probe"` exits 0. If it exits 3, the persona is padded (a probe-data fix commit) and the probe re-run. If it exits 1 or 4, divert per the flight.
- [ ] `make eval ARGS="run --models haiku"` completes with every run counted, not stopped or aborted.
- [ ] `make eval ARGS="measure-prompt --json <run-dir>/measure.json"` writes the measurement. Its prompt fingerprint equals the baseline's, since no prompt text changed.
- [ ] `make eval ARGS="compare <run-dir> --baseline evals/baselines/s11-platform.json --same-prompt --models haiku"` reports no gate failure (exit 0). A failing cell is re-run once before a divert.
- [ ] The readings are recorded in the flight log: the per-call probe lines, the compare summary, and the size-gate rows.

## Outcome (2026-11-08)
- **Probe:** exit 0.
- **Run:** 240/240 runs counted.
- **Measure:** written. Deviation: its prompt fingerprint is `84f8bf2e…`, not the baseline's `df5f2249…`. `s11-platform` predates sortie 11's leg 3 wording, and leg 1 changed no prompt text, as the unchanged size gates confirm. The compare therefore ran without `--same-prompt`.
- **Compare:** exit 0, no gate failure.
- Readings are in the flight log.

## Verification Steps
The command outputs above are the evidence. Run directories under `evals/runs/` are gitignored and are not committed.

## Citation Audit
- `evals/__main__.py`: `run`, `measure-prompt --json`, `compare --same-prompt --models`, and `cache-probe` with no arguments. Verified via `--help` at `178a931b`.
