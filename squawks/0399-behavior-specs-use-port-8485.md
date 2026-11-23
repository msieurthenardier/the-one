# Squawk 0399: Nine behavior-test specs start their dev instance on port 8485

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

## Report
`CLAUDE.md` says never to use port 8485, the Flight Director's preview instance, and since the
2026-11-21 turnaround its behavior-test recipe uses 8486. Nine specs in `tests/behavior/` still
hard-code `THE_ONE_PORT=8485` or `http://127.0.0.1:8485`. An Executor that follows one of them
collides with a running preview instance. Move each to 8486 or higher, or to an operator-provided
port. Found by the 2026-11-21 turnaround's Reviewer.

## Evidence
- `grep -rln 'THE_ONE_PORT=8485\|127.0.0.1:8485' tests/behavior/*.md` lists 9 files, among them
  `directory-lookup-send.md`, `kb-folder-index-round-trip.md`, `kb-folder-watch-round-trip.md`,
  `workbench-navigation.md` and `shell-navigation-smoke.md`.
- `CLAUDE.md` "Safety rules" (never 8484 or 8485) and "Behavior-test credential convention".

## Corrective Action
Sixteen specs in `tests/behavior/*.md` named 8485 as their instance. Nine of them match the
report's grep; the other seven wrote `localhost:8485`, `:8485` or "attached to 8485". Each now says the
instance runs on `{PORT}`, "a dedicated non-default port, 8486 or higher, assigned per run; never
8484 or 8485", and its start, probe, WebSocket and credential commands use `{PORT}`
(`THE_ONE_PORT={PORT}`, `http://127.0.0.1:{PORT}/api/live`, `ws://127.0.0.1:{PORT}/ws`). Prose
that forbids 8485 stays. `runs/` logs were not touched.

## Verification
`grep -rln 'THE_ONE_PORT=8485\|127.0.0.1:8485' tests/behavior/*.md` returns nothing (2026-11-22).
The remaining `8485` mentions in the specs are prohibitions (never 8484 or 8485) or history.
