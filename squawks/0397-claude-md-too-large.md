# Squawk 0397: CLAUDE.md is too large; pare it back to pointers

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

## Report
The operator reported on 2026-11-21 that `CLAUDE.md` is flagged as too large to load comfortably. It
has grown with a detailed paragraph per mission feature: the GleepGlorp legs, the widgets, the
desktop shells, the lane tables. That detail duplicates `the_one/agents.md`, `SECURITY-MODEL.md` and
`evals/README.md`.

Pare it back to the always-needed operational manual: commands, safety rules (ports, data dir,
credentials), test entry points and the quiet-host rule. Replace each feature paragraph with a
one-line pointer to its `the_one/agents.md` section. Move the per-lane budget prose to
`scripts/run-tests.sh` (already the source of truth) or `the_one/agents.md`.

Keep every rule that prevents harm:
- never port 8484 or 8485;
- never the default data dir;
- the plan token;
- browser tests only through `run-tests.sh`;
- the shell-write rule.

Doc-only: no code changes.

## Evidence
- `CLAUDE.md`: 666 lines, 182,468 bytes (2026-11-21).
- `the_one/agents.md` already holds the deep reference for most feature paragraphs. `CLAUDE.md` says
  of it: "Don't duplicate that material here".

## Corrective Action
*(written at completion)*

## Verification
- `CLAUDE.md` is substantially smaller (target: under about 40 KB).
- Every removed paragraph's detail exists in its target doc.
- Every pointer resolves to an existing heading (grep).
- Every safety rule listed above is still present.
- Tests that read `CLAUDE.md` still pass (grep `tests/` for `CLAUDE.md`).
