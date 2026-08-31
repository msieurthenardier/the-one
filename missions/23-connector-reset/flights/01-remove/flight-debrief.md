# Flight Debrief: Remove

**Date**: 2026-08-31
**Flight**: [Remove](flight.md)
**Status**: landed
**Duration**: 2026-08-30 – 2026-08-31
**Legs Completed**: 3 of 3 (+ one Flight-Director-ordered post-leg-3 fix pass)

## Outcome Assessment

### Objectives Achieved
The connector subsystem is fully removed: 213 files, +2,251 / −67,382 (`fea6d3e`, merged as `138025e`). The six kept pieces survived intact and are covered by targeted tests rather than assumption — session keying (repository-level resolver tests incl. NULL-thread COALESCE), visibility (`OPERATOR_VISIBILITY` + `tag_post_step_visibility` relocated to `llm/base.py`, all import sites verified), rotation over `connectors.secrets` (real re-encryption asserted), and the continuation window round-trip. `discord.py` and `aiohttp` are out of the resolved closure, verified both in the lock and by `ModuleNotFoundError` in the synced venv. Migration v38 landed idempotent with upgrade/rewind/chained-legacy coverage. The Windows Concourse build succeeded from the flight branch including the frozen-doctor smoke gate; the installer shrank 62→59 MiB. Independent flight-end review: zero issues.

### Mission Criteria Advanced
- Criterion 1 (dependency closure) — met and verified.
- Criterion 8 (single migration retiring approvals/columns/rows) — met.
- Criterion 10 (tests deleted-not-skipped; `discord_hat` marker/target gone) — met in its Flight-1 half; replacement live HATs remain for Flights 3–4.
- Criterion 12 (Windows packaged build + smoke) — met.
- Criterion 9 (size ceilings) — zero baseline established for the running count.

## What Went Well
- **The delete-first, rebuild-later shape held.** The pre-declared split point never fired — and leg 3 confirmed its two feared triggers were already defused (rotation test seeds rows via raw SQL; Chat badge keys on kept columns).
- **DD-7's deletion-travels-with-its-tests rule caught real issues** and kept every checkpoint green as scoped; the deliberately-scoped browser-lane-red window between legs 1 and 2 was the right call — the design predicted *why* lanes would be red rather than discovering it.
- **Frozen-history discipline.** Both interventions in migration history were done carefully: the `_CONNECTOR_TYPES_SQL` derivation frozen to inline literals (f-string escaping handled, not search-replaced), and the v23 re-entry-guard fix scoped strictly to the `if post_v23_target_exists:` branch with the historical `elif` untouched — covered by a chained v23→v38 legacy test.
- **The fix pass that investigated instead of deleting.** Leg 3 flagged the `session_metadata` plumbing as dead; the fix pass proved it live (carrier for `last_usage`, writer `_persist_last_usage`, reader `chat.js`) and left it alone — careful in both directions.
- **Candid logging.** Every deviation, anomaly, and Flight Director decision is in the log; the flight-end reviewer found the flagged items were exactly the right ones to scrutinize.
- **Suite payoff is real**: −1,010 tests (deleted, not skipped — skip count flat at 10), −159 deselected, ~24–27% faster wall time. The three biggest files in the 08-27 duration table were exactly the ones this flight stripped.

## What Could Be Improved

### Process
- **One bug class cost four review cycles.** Deleted module → unnamed surviving consumer (import, kept test, kept feature), discovered by after-the-fact grep: `_connector_types.py`'s two kept importers (review 1), `schema.py:28`/`codec.py:8` dead derivation+import (review 2), `tag_post_step_visibility` (implementation), routing-audit CSS + the leg-3 near-miss (verification). Each was caught, but a single automated reverse-dependency pass (content `grep -rln` of every deleted symbol/module cross-referenced against the inventory, run against the live tree at recon time) would likely have collapsed all four into one finding.
- **Filename-based inventory misses content-only files.** Five connector-only test files without "connector" in their names escaped the recon list and were found by content re-grep during implementation. Content sweep should be recon step zero, not a safety net.
- **Environment prerequisites decay.** Concourse reachability was checked at planning but Docker was down when the gate actually ran, stalling the landing across a day boundary. Gate-adjacent prerequisites need re-verification immediately before the gate, not only at flight start.
- **Spec-text bugs should be fixed at source, not carried as tribal knowledge.** The `uv sync` missing `--extra dev` (strips the test toolchain) was re-flagged in three legs instead of corrected once where it was written.

### Technical
- `tag_post_step_visibility` hardcodes the literal `"send_to_platform_channel"` — dormant until Flight 2 re-attaches the tool; a rename would silently break visibility tagging. Flight 2 must share a constant or pin the name with a test.
- The v23 guard fix near-duplicates segments 2/4 across the `if`/`elif` branches — accepted debt (touching frozen logic further was the greater risk), but each copy should cross-reference the other.
- Two new `RuntimeWarning: coroutine ... never awaited` warnings in `tests/test_factory.py::TestToolFiltering` (MCP tool-filtering, untouched by this flight) — likely pre-existing AsyncMock hygiene; flight logs don't record warnings so provenance is unconfirmed.

### Documentation
- The reviewed-and-accepted "illustrative backend comments" (`app.py:230-234`, `agent/factory.py:129-174`) describe gateway-listener consumers in present tense that don't exist until Flight 2 — revisit once the send tool and factory accessor have real callers again.
- "Directory absent" is the wrong verification language for deletions — an untracked root-owned `__pycache__` kept the directory alive as an importable empty namespace package. Say "no tracked files, zero LOC" instead; directory absence isn't fully under the agent's control. (Since resolved by the operator.)

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `tag_post_step_visibility` relocated alongside `OPERATOR_VISIBILITY` | DD-3 named only the constant; the function was a second surviving consumer of the same kept semantic | Yes — DD enumerations for "kept semantics" should list every surviving consumer, found by content grep |
| v23 re-entry-guard fix (frozen migration logic edited) | v38's asymmetric retirement broke v23's "connectors exists ⇒ post-v23" assumption | No — one-off; the narrow-scope + chained-test approach is the template if it ever recurs |
| `uv sync` re-run with `--extra dev` | Leg spec text omitted the dev extra; toolchain stripped | Yes — verification steps must copy the exact flag string from the CI workflow files, plus `--extra dev` locally |
| discord_hat suite + marker deletion moved leg 2 → leg 1 | Unit-lane collection imports browser/live modules (marker deselect is post-collection) | Yes — collection-order reasoning belongs in every leg split where imports are deleted |
| Concourse gate deferred to post-commit | Pipelines track `main`; flight commits once at flight end | Yes — CI-dependent criteria are post-commit gates by default under the flight-end commit model |
| Post-leg-3 fix pass (routing-audit leftovers) | Leg 2's grep terms lacked `routing-audit`; leg 3's sweep was broader | Yes — the verify leg's sweep vocabulary should be fixed at flight design and used by every leg, not grown per leg |

## Key Learnings
- **A removal flight's recon is an import-graph problem, not a line-citation problem.** Line citations drift and filename inventories miss content; what actually breaks collection is the reverse-dependency set of the deleted symbols. Tool the recon accordingly.
- **Marker-based deselection ≠ ignored at collection** — pytest imports every collected module before deselecting. Any leg that deletes an importable thing must fix all importers in the same leg, whatever lane they belong to.
- **Scope-sweep greps produce false positives on shared generic infrastructure** (the `session_metadata` save), not just false negatives — a hit needs a live-writer/live-reader check before deletion.
- **The stop-and-split ceiling and pre-declared split point shaped behavior without ever firing** — cheap to write, real influence on every DD's trade-off language. Keep both for removal/reset-shaped work.

## Recommendations
1. **Before Flight 2's legs are specced**: run a content-based reverse-dependency sweep as recon step zero and adopt the flight-wide sweep vocabulary up front (the two process fixes that would have prevented four review cycles and the fix pass).
2. **In Flight 2's contract-core leg**: import the send-tool name from one shared constant (or pin it with a test against `tag_post_step_visibility`'s literal) — the one dormant landmine this flight left armed.
3. **Methodology (mission-control side)**: leg templates' dependency-closure verification steps should require copying exact CI flag strings, and deletion criteria should say "no tracked files / zero LOC," not "directory absent."
4. **After Flight 2 lands**: sweep the accepted present-tense comments (`app.py:230-234`, `factory.py:129-174`) — some become true again, others need the new shape.
5. **Housekeeping**: add cross-reference comments to the two copies of the v23 guard segments; investigate the two `TestToolFiltering` AsyncMock warnings.

## Action Items
- [x] Logged as **squawk 0026**: cross-reference comments on the duplicated v23 guard segments (`db/schema.py`) — servicing, routine
- [x] Logged as **squawk 0027**: investigate/fix the two `AsyncMock ... never awaited` RuntimeWarnings in `tests/test_factory.py::TestToolFiltering` — defect, routine
- [ ] Carried into Flight 2's spec (already drafted): shared send-tool name constant; recon content-sweep; comment revisit after landing
- [ ] Mission-control methodology feedback (for the next `/mission-debrief` or skill edit): CI-exact flag strings in verification templates; "zero tracked LOC" deletion language; reverse-dependency recon step for removal flights
