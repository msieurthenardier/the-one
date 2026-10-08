# Squawk 0152: 27 merged branches remain on the remote and locally

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
27 of 34 remote branches are already merged into `main` (flight/01–07, mission/24, release/0.9.0–0.10.3, sortie/01, squawk/0083, two squawk turnarounds), plus 27 merged local branches. It is hard to tell active work from finished work. Found by routine maintenance 2026-10-08 (finding #33).

## Evidence
- `git branch -r --merged main` / `git branch --merged main`

## Corrective Action
*(written at completion)* Expected: delete the merged local and remote branches. Release branches are covered by their `v*` tags (confirm each tag exists first). Remote deletion is outward-facing: the operator confirms the list before it runs.

## Verification
`git branch -r --merged main` lists only `origin/main`; every deleted release branch has a matching tag.

## Sign-Off
*(written at completion)*
