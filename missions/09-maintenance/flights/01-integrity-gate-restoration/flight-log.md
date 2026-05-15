# Flight Log: Integrity Gate Restoration

**Flight**: [Integrity Gate Restoration](flight.md)

## Reconnaissance Report

**Date**: 2026-05-15 (during flight design)
**Source artifact**: [Maintenance Report 2026-05-15](../../../../maintenance/2026-05-15.md)
**Method**: Each Flight 1 scope item was verified against current code on `main` before legs were finalized. This pass is a delta-check on top of the spot-check the Architect performed during mission design — most items were re-confirmed; line numbers updated where they had drifted.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Ruff lint baseline: 69 errors | confirmed-live | `ruff check the_one/ tests/` → "Found 69 errors. [*] 23 fixable" | Proceed with Leg 1 cleanup; small day-of drift acceptable |
| Ruff format baseline: 81 files would reformat | confirmed-live | `ruff format --check the_one/ tests/` → "81 files would be reformatted, 139 files already formatted" | Proceed with Leg 1 |
| `asgi-lifespan` declared but uninstalled | confirmed-live | `pip show asgi-lifespan` → "Package(s) not found"; `tests/conftest.py:238` imports it | Proceed with Leg 2 `pip install` |
| `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` exists with `_has_sys_admin()` predicate | confirmed-live | `tests/test_mcp_sandbox_integration.py:177` (`_has_sys_admin`) + `:488` (skip predicate) + `:491` (test) | Proceed with Leg 2 predicate-tightening |
| OAuth callback `post_message_script` flows `json.dumps(post_message)` into `<script>` body | confirmed-live | `the_one/interfaces/web/api.py:1681-1683` (script literal) + `:1836, 1859, 1911` (three `post_message=` flow sites) | Proceed with Leg 3 Option A escape; verify all three flow sites are routed through `_safe_script_json` not just one |
| `_clean_npx(pkg)` is `async def` and takes `pkg` as bare string | confirmed-live | `the_one/mcp/cache_cleanup.py:215` `async def _clean_npx(pkg: str) -> None:` | Proceed with Leg 3 allowlist; verification needs `asyncio.run` wrapper (already corrected in leg spec) |
| `pip-audit` not installed and not in pyproject/pipeline | confirmed-live | `grep -c pip-audit pyproject.toml ci/pipeline.yml` → 0 in both | Proceed with Leg 3 adoption |
| `agents.md ## Provider type extension checklist` heading | confirmed-live | `the_one/agents.md:1485` (line preserved since M05) | Proceed with Leg 3 doc add; locate by heading not line number |
| `agents.md ## Project Conventions` heading | confirmed-live (line drifted) | `the_one/agents.md:171` (NOT L219 as initial scaffold claimed; Architect spot-check during mission planning fixed this) | Proceed with Leg 3 doc add; locate by heading |
| `.env.example` lacks `THE_ONE_DEV_MODE` | confirmed-live | `grep -c THE_ONE_DEV_MODE .env.example` → 0 | Proceed with Leg 3 one-line add |
| `SECURITY-MODEL.md` "Future Work (NOT in scope today)" section | confirmed-live | `SECURITY-MODEL.md:116` heading present | Proceed with Leg 3 two additions under this heading |
| OpenRouter `_APP_URL` / `_APP_NAME` still pre-rebrand strings | confirmed-live | `the_one/llm/openrouter_provider.py:38-39` literal `"https://github.com/msieurthenardier/the-one"` + `"the-one"` | Proceed with Leg 3 rebrand update; preserve GitHub URL (repo name unchanged per M08 constraint) |
| CI pipeline gate command shape (`&&`-chained ruff check + format + pytest) | confirmed-live | `ci/pipeline.yml:24` — single-line `sh -c "cp -r /src /work && cd /work && pip install --no-cache-dir '.[dev]' -q && ruff check the_one/ tests/ && ruff format --check the_one/ tests/ && python -m pytest tests/ --tb=short -q && python -m pytest -m browser tests/browser/ --tb=short -q"` | Two-pytest-invocation shape: deliberate-violation experiment should fire at the FIRST ruff step (fail-fast) |
| `Makefile` has no `doctor` target | confirmed-live | `grep -c "^doctor:\|^.PHONY:.*doctor" Makefile` → 0 | Proceed with Leg 2 new target; no naming collision |

**Net disposition**: 14 of 14 items classified `confirmed-live`. No retirements, no scope changes. Architect's mission-design spot-check pre-empted the items that would have been `already-satisfied` / `drifted` (e.g., agents.md `## Project Conventions` line number was L171 not L219; tools-grid shape; section-nav.js path).

**Observations beyond the scope**:
- The CI pipeline runs pytest in TWO invocations (broad + browser-marked). The first invocation has no marker, so under the addopts default it deselects `browser`, `pixel`, `live`, and `requires_bwrap`. The `asgi-lifespan` collection errors will manifest in the first invocation. Once Leg 2 lands the `python -c` doctor probe, the failure path is "doctor exits non-zero before pytest is even reached" — clean diagnostic.
- The deliberate-violation experiment in Leg 1 should pick a violation that surfaces at the ruff step (line-too-long is easiest). The pipeline's fail-fast under `&&` means the violation never reaches pytest.

---

## Summary

(Populated during execution.)

---

## Flight Director Notes

### 2026-05-15 — Flight start

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-side, not default fallback). Crew extracted: Developer (Sonnet, used for design review + implementation + fix-review-issues + commit), Reviewer (Sonnet, no Opus per skill), Accessibility Reviewer (Sonnet, not needed for this flight — no UI changes).
- **Branch**: `flight/01-integrity-gate-restoration` created off `main` (note: collision-free with M08's merged `flight/01-brand-foundation` because slug differs).
- **Mission state transition**: `09-maintenance` mission status `planning` → `active`. Flight 1 status `ready` → `in-flight`.
- **Initial commit**: planning scaffold (maintenance/2026-05-15.md, missions/09-maintenance/*) committed at flight start. Subsequent commits will be leg work; final commit will check off legs + flight in artifacts and bring statuses to `completed`.
- **Reconnaissance Report at top of this log** was authored during flight design — every cited scope item is `confirmed-live` on current `main`. No retirements, no scope changes.
- **Execution model per skill**: per-leg design review by spawned Developer, then per-leg implementation by spawned Developer, then ONE flight-level Reviewer pass on all uncommitted changes, then ONE final commit checking off all legs + the flight. Tests run with `docker exec the-one pytest -x --timeout 30` per crew prompt — not `docker compose exec` which can wedge on TTY.

---

## Leg Progress

(Populated during execution.)

---

## Decisions

(Populated during execution. The deliberate-violation experiment result lands here.)

---

## Deviations

(Populated during execution.)

---

## Anomalies

(Populated during execution.)

---

## Session Notes

(Populated during execution.)
