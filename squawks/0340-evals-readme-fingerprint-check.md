# Squawk 0340: `evals/README.md` should say to check fingerprint equality before planning `--same-prompt`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: 2026-11-08

## Report
Sortie 14 planned `compare --same-prompt` against `s11-platform` on the assumption that the current prompt matched the baseline's. It did not, because a later flight's wording had landed since the baseline was recorded. The eval workflow docs should say: before planning a `--same-prompt` compare, run `measure-prompt` and check that its prompt fingerprint equals the baseline's `fingerprints.prompt`.

## Evidence
- `evals/README.md:62` (the `compare` row) and `:231` (the `--same-prompt` refusal) describe the flag but not this pre-check.
- Sortie 14 flight log, Deviations; debrief recommendation 4 and Methodology Observation 1.

## Corrective Action
Added the pre-check to `evals/README.md` in two places: a sentence on the `compare` row, and a bullet after the `compare` refusals list (the `--same-prompt` guidance). It says to run `measure-prompt` (last line `prompt fingerprint: <hash>`, or `fingerprints.prompt` in `--json` output), read the baseline's `fingerprints.prompt` with a one-line `python -c`, and, if they differ, compare without `--same-prompt` or re-baseline. Key paths verified against `evals/tokens.py` and `evals/baselines/s11-platform.json`. Docs only.

## Verification
Result: `grep -n "fingerprint" evals/README.md` shows the pre-check at lines 62 and 230-236. `pytest -k "evals or docs"`: 477 passed.

Original check:
`grep -n "fingerprint" evals/README.md` shows the pre-check beside the `compare` / `--same-prompt` guidance. `.venv/bin/python -m pytest tests/ -q -x --timeout 60 -k "evals or docs"` passes.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; no security-sensitive surface), batch review of the 2026-11-08 squawk turnaround, scoped to the diff: `[HANDOFF:confirmed]`, no blocking issues. It re-ran `test_db_codec`, `test_anthropic_prompt_caching`, `test_evals_cache_probe`, `test_evals_freeze` and `test_evals_cli` (217 passed) and ruff check and format (clean). It ran the documented baseline one-liner (it prints `df5f2249…`) and confirmed the `prompt fingerprint:` line in `evals/tokens.py`. Its note: on this head the check fails (`measure-prompt` gives `84f8bf2e…`), which is the drift squawk 0337 (re-baseline) already tracks; the docs are correct.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-08` commit on `squawk/turnaround-2026-11-08`.
