# Squawk 0390: Mark GleepGlorp's eval candidate prompts as history

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

## Report
Leg 9 Part B left 13 prompt files in `evals/gleepglorp/prompts/`. Only `v1` (the original) and `dmin` (shipped) still mean anything. The rest are spent candidates: `a`-`e` from the screening and `d`, `d0`-`d5` from the ablation. A reader cannot tell which is live.

Move the spent candidates under a `history/` folder, or mark them as history in `evals/README.md`, the way old baselines are. Keep `v1` and `dmin` where they are. Update the tests that load them by path (`tests/test_evals_*`) so they still pass.

## Evidence
- `ls evals/gleepglorp/prompts/`: `a b c d d0 d1 d2 d3 d4 d5 dmin e v1` (`.toml`).
- The flight log's Leg 9 Part B entries name the ones screened, ablated and shipped.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
