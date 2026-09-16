# Squawk 0065: name two Flight 3 conventions and one leg-authoring rule in `agents.md`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

## Report

Flight 3's debrief (Recommendation 3) names two patterns now used twice in
the tree and one house rule, none yet in `the_one/agents.md`'s Project
Conventions:

1. **`supervised-per-entity-worker`** — the `ConnectorManager` /
   `IndexingManager` shape: a dict of entities → worker task + wake event +
   idle event + stop flag; `start` / `request` / `stop` / `drain` /
   `state`; a module accessor pair; lifespan-wired; cooperative stop with
   cancel fallback (never flush after a cancel); idle set only on the
   normal-completion path (no `finally`); concurrent drain under a stated
   budget below the desktop launcher's 60 s join. Flight 4's watcher is
   the third instance.
2. **`leg-staged-hook-seam`** — a documented module-level no-op
   (`_after_folder_registered`) landed by an early leg and filled by a
   later one, so the early leg never imports the later leg's module.
3. **Rule**: a design decision that relies on a cap or guard enforced in
   a *different* code path carries an acceptance criterion with the
   negative test, never a cross-reference alone (the `/source` cap gap,
   squawk 0063, is the instance).

## Evidence

- `the_one/knowledge/manager.py` module docstring (lock order, stop/drain contract) and `the_one/connectors/manager.py:51-227`
- `the_one/interfaces/web/api.py::_after_folder_registered`
- Flight 3 debrief, Recommendation 3 and "Process — Minor"
- `the_one/agents.md` "Project Conventions" (Flight 2's four conventions were added under squawk 0062 — same section)

## Corrective Action
*(written at completion)*

## Verification
`grep -c "supervised-per-entity-worker\|leg-staged-hook-seam" the_one/agents.md` → ≥ 2; the rule appears in the conventions list; `ruff`-free (docs only).

## Sign-Off
*(written at completion)*
