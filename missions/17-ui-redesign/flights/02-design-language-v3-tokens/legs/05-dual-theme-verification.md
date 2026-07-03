# Leg: dual-theme-verification (Leg 4)

**Status**: completed
**Flight**: [Design Language v3 — Tokens and Type](../flight.md)

## Objective

Verify the whole flight: full test suites green, per-file sink counts recorded, and a structured goldfinch visual pass over both themes × three areas (including tabs and focus-visible states) with committed-log evidence notes — followed by the Flight Director's `shell-navigation-smoke` re-run on the dev instance.

## Context

- Flight DDs: checkpoints Leg 4; "Guard churn is bookkeeping" (record per-file sink counts); the deferred tab L-bracket and outline-only focus must be SEEN and consciously accepted, not discovered in Flight 3.
- Split of duties: the Developer performs suites + visual pass + flight-log records; the FD runs the behavior test directly afterward (per agentic-workflow, behavior tests are not delegated to the Developer).

## Inputs

- Legs 1–3 landed (uncommitted); dev instance on 8485

## Outputs

- Flight-log verification entry: suite results (unit + FULL browser suite with `TEST_TIMEOUT=3600`), per-file dynamic-sink counts vs the 95-site baseline (expect unchanged; justify any diff), and the visual-pass record
- Visual-pass evidence (printToPDF fallback per doctrine), covering per theme: chat (transcript + composer), studio (agents grid + one editor surface), system (general + providers), the design gallery, the TAB component (selected state — the deferred L-bracket seen and logged), and a `:focus-visible` state on a button + a form field (outline-only form seen and logged)
- Any visual defects found → fixed if within quiet-system rules and trivially safe, else logged to the flight log with a Flight-3 assignment

## Acceptance Criteria

- [x] `make test-unit` green; `TEST_TIMEOUT=3600 make test-browser` FULL suite green (0 failures; note runtime)
- [x] Contrast/token/guard suites green (already in unit tier — confirm)
- [x] Per-file sink counts recorded; total ≤ 95 with diffs justified
- [x] Visual pass completed for BOTH themes with the enumerated coverage; tab L-bracket + focus treatment explicitly noted as seen/accepted-for-F3
- [x] Pixel snapshots regenerated locally (`pytest -m pixel --snapshot-update`) per the flight-boundary strategy — NOT committed (gitignored; verify)
- [x] `ruff` clean

## Verification Steps

- The suites; the visual pass; `git status` shows no snapshot files staged; flight-log entry complete

## Implementation Guidance

1. Run unit first (fast), then the full browser suite once.
2. Visual pass: one tab, systematic order (dark all areas → light all areas), record per-surface one-line verdicts in the flight log; capture evidence files to a scratch dir (NOT the repo).
3. Sink counts: rerun the Leg-1 helper's classifier or grep equivalent; tabulate.
4. Do not fix non-trivial visual issues in this leg — log and assign.

## Edge Cases

- **Browser suite failures from CSS-dependent assertions**: expected near-zero — design review swept the suite: assertions are DOM/attribute/text-based; no glow/glass/bezel/backdrop pins. Known cosmetic residue to fix in passing: stale "glass tile" docstring at `tests/browser/test_studio_mcps_tab.py:4`. If something else fails: test pinned a retired treatment → fix the test (log it); app broke → fix within quiet-system rules.
- **Pixel snapshot regen churn**: expected wholesale; baselines are local-only.

## Files Affected

- `missions/17-ui-redesign/flights/02-design-language-v3-tokens/flight-log.md` (records)
- Possibly small test fixes (logged)

---

## Citation Audit

No code citations beyond flight/leg artifacts of this same flight (same-day, no drift risk).

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg (`dual-theme-verification`) in flight.md
