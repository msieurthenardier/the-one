# Squawk 0024: `.flightops/` is gitignored — methodology config doesn't travel with the repo

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

## Report

`.flightops/` holds the project's Flight Control configuration — `ARTIFACTS.md` (artifact
conventions every skill reads), `FLIGHT_OPERATIONS.md`, `README.md`, and seven
`agent-crews/*.md` crew definitions — yet it is listed in `.gitignore`, so none of it is
versioned. Squawk 0023's crew-file change could only be applied locally. The ignore was
added in the initial mission-control-integration commit alongside `.memory/` (which *is*
private) and appears to be an over-broad grouping rather than a decision. Operator
decision 2026-08-28: track it. Remove the line, add the directory, leave `.memory/` ignored.

## Evidence

- `.gitignore:21` — `.flightops/` (introduced in `67ffd87`, same hunk as `.memory/`)
- `find .flightops -type f` → 10 markdown files, 124K; scanned clean for operator paths/usernames
- `squawks/0023-crew-reviewer-model-security-reviews.md` Sign-Off — "applied on disk … `.flightops/` is gitignored"
- Sibling projects (mission-control, air-traffic-control) do not ignore `.flightops/`

## Corrective Action

- Removed the `.flightops/` line from `.gitignore` (was line 21, grouped with `.memory/` in
  the original mission-control-integration commit); `.memory/` remains ignored.
- Scanned `.flightops/` for operator-identifying content before staging: `grep -rn -E
  '/home/|/Users/|C:\\Users' .flightops` returned no matches, and the heads of
  `.flightops/README.md` and `.flightops/FLIGHT_OPERATIONS.md` contain no machine-specific
  paths. Clear to stage.
- `git add .flightops .gitignore` — staged the ten previously-untracked markdown files
  (`ARTIFACTS.md`, `FLIGHT_OPERATIONS.md`, `README.md`, seven `agent-crews/*.md`) plus the
  `.gitignore` edit. Not committed.
- Checked whether any repo doc claims `.flightops/` is local/ignored: `grep -rn "flightops"
  README.md CLAUDE.md docs/` only matched `CLAUDE.md`'s description of the AI-agent reading
  order (`.flightops/README.md`, `.flightops/FLIGHT_OPERATIONS.md`, etc.) — no claim that the
  directory is local-only or gitignored. No doc correction needed.

## Verification

- `git check-ignore -v .flightops/ARTIFACTS.md` — no output, exit 1 (file is no longer ignored).
- `git status --short` — shows `A  .flightops/ARTIFACTS.md`, `A  .flightops/FLIGHT_OPERATIONS.md`,
  `A  .flightops/README.md`, and `A  .flightops/agent-crews/{behavior-tests-execution,
  flight-debrief,flight-design,leg-execution,mission-debrief,mission-design,
  routine-maintenance}.md` (ten files), plus `M  .gitignore`.
- `git diff --cached --stat | tail -1` — `11 files changed, 2638 insertions(+), 1 deletion(-)`.
- Leak scan (re-run after staging): `grep -rn -E '/home/|/Users/|C:\\Users' .flightops` —
  empty output, exit 1.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped; Haiku — non-security diff, first application of the squawk 0023 rule)
**Verdict**: confirmed
**Commit**: `767e87d` on `squawk/turnaround-2026-08-28` — PR #180
