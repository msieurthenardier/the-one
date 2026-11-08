# Squawk 0340: `evals/README.md` should say to check fingerprint equality before planning `--same-prompt`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: —

## Report
Sortie 14 planned `compare --same-prompt` against `s11-platform` on the assumption that the current prompt matched the baseline's. It did not, because a later flight's wording had landed since the baseline was recorded. The eval workflow docs should say: before planning a `--same-prompt` compare, run `measure-prompt` and check that its prompt fingerprint equals the baseline's `fingerprints.prompt`.

## Evidence
- `evals/README.md:62` (the `compare` row) and `:231` (the `--same-prompt` refusal) describe the flag but not this pre-check.
- Sortie 14 flight log, Deviations; debrief recommendation 4 and Methodology Observation 1.

## Corrective Action
*(written at completion)*

## Verification
`grep -n "fingerprint" evals/README.md` shows the pre-check beside the `compare` / `--same-prompt` guidance. `.venv/bin/python -m pytest tests/ -q -x --timeout 60 -k "evals or docs"` passes.
