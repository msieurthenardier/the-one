# Leg: git-and-asset-hygiene

**Status**: ready
**Flight**: [Cleanup Grab-Bag](../flight.md)

## Objective
Delete the 3 stale merged remote branches (G1) and re-export the oversized brand PNGs (G2).

## Context
Maintenance report 2026-06-04, Category 7 findings:
- **G1**: 3 merged remote branches not deleted — `origin/docs/acl-recon-reason-string-convention`, `origin/flight/16-pairing-peers-dm-only`, `origin/flight/17-daily-driver-gate` (the flight/16 and flight/17 debriefs are already committed/completed).
- **G2**: 2 brand PNGs >1MB — `the_one/interfaces/web/static/brand/gleepglorp_med.png` (1.78MB) and `gleepglorp_small.png` (1.71MB). "small" is nearly as large as "med", strongly suggesting `gleepglorp_small.png` was not actually downscaled (an asset-pipeline/export bug). Oversized PNGs bloat clone size.

## Inputs
- The remote with the 3 merged branches.
- `the_one/interfaces/web/static/brand/gleepglorp_med.png`, `gleepglorp_small.png`, and any HTML/CSS referencing them.

## Outputs
- The 3 stale branches deleted on the remote.
- Re-exported (meaningfully smaller) brand PNGs at the correct dimensions.

## Acceptance Criteria
- [ ] `origin/docs/acl-recon-reason-string-convention`, `origin/flight/16-pairing-peers-dm-only`, `origin/flight/17-daily-driver-gate` are deleted from the remote
- [ ] No local tracking branches dangle for the deleted remotes
- [ ] `gleepglorp_small.png` is re-exported at its intended (smaller) dimensions and file size, materially below `gleepglorp_med.png`
- [ ] `gleepglorp_med.png` is re-compressed if it can shrink without visible quality loss
- [ ] The brand images still render correctly wherever they're referenced (no broken `src`)

## Verification Steps
- `git ls-remote --heads origin` → the 3 branches absent
- `git branch -a --merged main` → the 3 no longer listed
- `du -k the_one/interfaces/web/static/brand/*.png` → `gleepglorp_small.png` meaningfully smaller than before and than `_med`
- Manual: load the app surfaces that show the brand images, confirm they render crisply
- `make verify-serving` (or a manual curl) if the brand assets are on a checked path

## Implementation Guidance

1. **G1 — delete the merged branches** (confirm each is truly merged into `main` first)
   - `git push origin --delete docs/acl-recon-reason-string-convention flight/16-pairing-peers-dm-only flight/17-daily-driver-gate`
   - `git fetch --prune` to drop local tracking refs.
   - This is a remote-mutating operation — confirm with the operator before pushing the deletions if there's any doubt the branches are fully merged.

2. **G2 — re-export the PNGs**
   - Determine the intended display dimensions for `_small` vs `_med` (check the CSS/HTML `width`/`height` or usage context). Re-export `gleepglorp_small.png` at the smaller dimension so it's actually downscaled.
   - Run both through a lossless/optimized PNG compressor (e.g. `oxipng`/`pngquant` if available) without visible quality loss.
   - Confirm references still resolve and render.

## Edge Cases
- **A branch isn't actually merged** — if `--merged main` was stale, do not delete; re-confirm. The report listed these as merged, but verify at execution time.
- **Brand asset is referenced by exact filename** — keep the filenames the same so no `src` updates are needed; only the file contents change.
- **Snapshot/pixel tests** — brand-image changes could shift visual snapshots; those baselines are gitignored/local-only, so regenerate locally if a `-m pixel` run is done (no committed baseline to update).

## Files Affected
- Remote refs (3 branches deleted) - no local file change for G1 beyond pruning
- `the_one/interfaces/web/static/brand/gleepglorp_small.png` - re-exported smaller
- `the_one/interfaces/web/static/brand/gleepglorp_med.png` - re-compressed (if beneficial)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
