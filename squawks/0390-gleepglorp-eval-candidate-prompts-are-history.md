# Squawk 0390: Mark GleepGlorp's eval candidate prompts as history

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-19

## Report
Leg 9 Part B left 13 prompt files in `evals/gleepglorp/prompts/`. Only `v1` (the original) and `dmin` (shipped) still mean anything. The rest are spent candidates: `a`-`e` from the screening and `d`, `d0`-`d5` from the ablation. A reader cannot tell which is live.

Move the spent candidates under a `history/` folder, or mark them as history in `evals/README.md`, the way old baselines are. Keep `v1` and `dmin` where they are. Update the tests that load them by path (`tests/test_evals_*`) so they still pass.

## Evidence
- `ls evals/gleepglorp/prompts/`: `a b c d d0 d1 d2 d3 d4 d5 dmin e v1` (`.toml`).
- The flight log's Leg 9 Part B entries name the ones screened, ablated and shipped.

## Corrective Action
`git mv`'d the eleven spent candidates (`a`-`e`, `d`, `d0`-`d5`) to `evals/gleepglorp/prompts/history/`; `v1.toml` and `dmin.toml` stay. `evals/README.md` and `the_one/agents.md` say so. `tests/test_evals_gleepglorp_fixes.py` now resolves candidate paths through a `candidate_path()` helper (live: `v1`, `dmin`; others under `history/`). No frozen module or baseline touched.

## Verification
`.venv/bin/python -m pytest tests/ -q -x -k evals`: 764 passed. `ruff check` and `ruff format --check` clean on the touched test file.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0386-0390
**Verdict**: confirmed (no stale references outside the historical flight log)
**Commit**: `squawk: turnaround 2026-11-19` on flight/01-gleepglorp-exists-and-answers (PR #380)
