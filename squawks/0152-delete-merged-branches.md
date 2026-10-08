# Squawk 0152: 27 merged branches remain on the remote and locally

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
27 of 34 remote branches are already merged into `main` (flight/01–07, mission/24, release/0.9.0–0.10.3, sortie/01, squawk/0083, two squawk turnarounds), plus 27 merged local branches. It is hard to tell active work from finished work. Found by routine maintenance 2026-10-08 (finding #33).

## Evidence
- `git branch -r --merged main` / `git branch --merged main`

## Corrective Action
Deleted 24 remote branches and 28 local branches (operator-authorized). Remote: flight/02-06 (five Mission 24 flights), flight/05-window-chrome, flight/06-alignment, maintenance/2026-10-08, mission/24-knowledge-bases, release/0.9.1 and 0.10.0-0.10.3, sortie/01-debrief, sortie/01-ollama-pull-download-size, squawk/0102-mcp-server-info-stale-after-refresh, and seven squawk/turnaround-* branches (09-15 through 10-07). Local: the same 24 plus four local-only branches (flight/01-control-library-foundation, flight/02-shell-and-router, flight/03-list-and-detail, flight/04-chats-and-jump-to).

Squash-merge verification: 21 remote branches and 17 local were merged by ancestry (`git branch -d` accepted them). Seven were squash-merged, so ancestry cannot show them; the Flight Director verified each was a MERGED PR whose head SHA equalled the branch tip, and the tips were re-checked against those SHAs immediately before deletion. These seven were removed with `git branch -D`. Release branches were deleted only after confirming tags v0.9.1, v0.10.0, v0.10.1, v0.10.2 and v0.10.3 exist locally and on origin. No tag was touched.

Kept: `main`, `squawk/turnaround-2026-10-08` (open PR #240), and the squawk's own branch `squawk/0152-delete-merged-branches`.

## Verification
- `git fetch --prune origin`, then re-checked remote tips of the three squash-merged remote branches (35766cb, 6b526eb, 24236df) and local tips of the four local-only ones (ce4a4a3, e6a3a90, c3f0a86, def7f35): all matched.
- `git ls-remote --tags origin` and `git tag -l`: all five release tags present on both.
- `git push origin --delete <24 names>`: all reported deleted.
- `git fetch --prune origin; git branch -r` lists only `origin/main` and `origin/squawk/turnaround-2026-10-08`.
- `git branch` lists only `main`, `squawk/0152-delete-merged-branches`, `squawk/turnaround-2026-10-08`.
- Tag count: 22 locally and 22 on origin, unchanged.

## Sign-Off

**Reviewer**: independent Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration surface; git refs only). It re-verified the branch lists after `fetch --prune`, all seven squash-merged PRs MERGED with head SHAs matching the deleted tips, 22 `v*` tags present locally and on origin, and PR #240's branch intact. Note: the Report's "27 merged" counts came from the inspection-time snapshot, which counted by ancestry only; the deleted set is 24 remote and 28 local because the seven squash-merged branches (verified by PR head SHA) were added on the operator's "all branches can be cleaned up".
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk/0152: delete merged branches` on branch `squawk/0152-delete-merged-branches`
