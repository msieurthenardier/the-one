# Leg: flight-verification

**Status**: completed
**Flight**: [Shell and Shared Components](../flight.md)

## Objective

Flight-wide verification: full suites, dual-theme visual pass over the vocabulary + shell + gallery (focus via CDP), sink/registry ledger, pixel-snapshot regen. (FD runs the behavior gate afterward.)

## Scope

- `make test-unit`; `TEST_TIMEOUT=3600 make test-browser` full suite once. Flake disposition PRE-SPECIFIED (F2 debrief rec): a failure that passes in isolation AND on one clean full rerun of ITS MODULE counts as a flake (log it); only run the FULL suite twice if >2 modules flake.
- Visual pass both themes on 8485: gallery all sections; topbar/wordmark; one entity grid in EMPTY + populated state (unified CTA); a modal open; tabs selected state (no chamfer); badges strip; focus states via CDP page (button, field, tab, CTA).
- Ledger: per-file sink counts vs 95 baseline; registry row count delta (4 pruned − any added); guard-entry deltas confirmed executed (banner string, clip-path allowance, KNOWN_DEAD_SELECTORS).
- Pixel snapshots regenerated locally (never committed — verify untracked).

## Acceptance Criteria

- [x] Unit green; full browser suite 0 failures per the flake disposition; guard slice green
- [x] Visual pass evidence recorded per enumerated coverage; no alien-console remnants visible anywhere (SC1 spot-check)
- [x] Ledger in flight log; `git status` clean of snapshots
- [x] ruff clean

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md (behavior gate noted FD-pending)
