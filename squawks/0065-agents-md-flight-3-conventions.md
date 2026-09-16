# Squawk 0065: name two Flight 3 conventions and one leg-authoring rule in `agents.md`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-16

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

Added three new entries under `the_one/agents.md`'s "## Project Conventions"
→ "### Project-wide", in the house style of the existing entries (matching
the shape/length of Flight 2's four squawk-0062 entries), inserted
immediately after `store-owned-until-decided` and before
`### Mission-specific (M16)`:

1. **`supervised-per-entity-worker`** — the dict-of-entities +
   task/wake/idle/stop-flag shape, `start`/`request`/`stop`/`drain`/`state`,
   the `set_manager`/`get_manager` accessor pair, lifespan wiring with its
   own `try`/`except` and a deliberately-placed `drain`, cooperative stop +
   cancel fallback that never flushes after a cancel, idle set only on the
   `try`/`except`/`else` normal-completion path (never `finally`), and
   concurrent `drain()` under a budget stated to stay below the desktop
   launcher's 60s `thread.join`. Cites `ConnectorManager` and
   `IndexingManager` (the latter modelled explicitly on the former per its
   module docstring) and names Flight 4's watcher as the expected third
   instance.
2. **`leg-staged-hook-seam`** — the early-leg no-op / later-leg-fills-it
   shape, citing `_after_folder_registered` (Flight 3 Leg 1 landed the
   no-op, Leg 3 filled it).
3. **`remote-cap-needs-a-negative-test`** — the rule that a cap/guard
   enforced in a different code path needs its own negative-test
   acceptance criterion, not a cross-reference alone. Citing squawk 0063
   (`/source`'s claimed-but-unenforced `MAX_FILE_BYTES` cap).

Also added a one-line cross-reference from the Knowledge indexing block's
`IndexingManager` paragraph ("modelled on `ConnectorManager`") to the new
`supervised-per-entity-worker` convention by name, since that paragraph
did not previously name it. Left squawk 0063's edit to the same block (the
`/source` cap-enforcement sentence) and squawk 0064's changes untouched —
only inserted new text, no existing lines in that block were altered
beyond the one cross-reference insertion.

No other files touched. Docs only — no code, no tests, no ruff-relevant
surface.

## Verification

`grep -c "supervised-per-entity-worker\|leg-staged-hook-seam\|remote-cap-needs-a-negative-test" the_one/agents.md` → **4** (three convention headers/citations plus the one cross-reference mention of `supervised-per-entity-worker` in the Knowledge indexing block). All three names appear in the Project Conventions list; the rule (`remote-cap-needs-a-negative-test`) is present. Docs-only change — no ruff-relevant files touched, nothing to lint.

## Sign-Off
**Reviewer**: Sonnet (batch review, squawk turnaround 2026-09-16; Sonnet tier — 0063 touches the route reading operator-registered paths)
**Verdict**: confirmed
**Commit**: `16222c4`
