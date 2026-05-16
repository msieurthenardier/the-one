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

### 2026-05-15 — Leg 4 design review

- **Agent spawned**: Developer (Sonnet) for `review-leg-design` on Leg 4.
- **Outcome**: approve with changes; 2 high + 4 medium + 4 low issues raised. Recon corrections caught one missed `SECURITY-MODEL.md` Concourse ref.
- **High-severity fixes applied**:
  1. SECURITY-MODEL.md line 99 `"or \`ci/pipeline.yml\`."` was missed by recon — added as step 4b. Recon section in leg also corrected from "FOUR" to "FIVE" Concourse refs.
  2. AC #5 grep pattern tightened — drop the "historical exempt" parenthetical since the grep's `-bounded` file list already excludes `missions/`.
- **Medium-severity fixes applied**: added new step 0 (re-verify recon at impl time + confirm `.env` gitignored + check no in-flight Concourse builds); step 10's `git add -A` → enumerated paths; commit-message format switched from `-m "...\n\n..."` to heredoc.
- **Low-severity fixes applied**: AC #6 grep widened to `sed`-extracted section (no `-A N` magic number); step 6 explicit "ONLY the `## the-one` entry" warning; maintenance-report annotation heading renamed `Post-Write Pivot` → `Post-Report Pivot (2026-05-15)`.
- **Skipped 2nd review cycle**: changes were corrective. The 1 missed recon item was the only substantive find; the rest were tightening.
- **Recon corrections captured**: Python codebase has ZERO coupling to Concourse (no `ci/` imports, no `THE_ONE_CONCOURSE_PASS` env reads anywhere in `the_one/` or `tests/`). `git rm -r ci/` is empirically safe. `the_one/agents.md` is also clean of self-modification + Concourse refs (confirmed via grep, 1678 lines).

### 2026-05-15 — Mid-flight pivot: Concourse + self-improvement removal

**Trigger**: Leg 1 implementation blocked at Step 0 because `fly -t local` auth was broken (token validation failure). When surfaced to operator, the response questioned the Concourse infrastructure's reason-for-being. Original intent: Concourse as a TOOL the agent uses. Actual drift: Concourse as a maybe-CI-someday pipeline. Operator decision: **remove Concourse + self-improvement framing from the project**.

**Implications**:
- Leg 1's deliberate-violation experiment is moot (no pipeline to test). Lint+format cleanup remains valuable as zero-baseline restoration independent of CI substrate.
- Maintenance report's Category 8 CI/CD findings (C1-C7) shift from "fix" to "remove" — landed in new Leg 4, not Leg 3.
- Leg 1 narrowed: lint+format only. Slug retained for branch-history continuity but the "gate audit" half is annotated as scope-dropped.
- Leg 2 narrowed: `make doctor` stays as a local-bench target; CI inline `python -c` probe dropped.
- Leg 3 narrowed: `pip-audit` adoption becomes `make audit` local target (no CI step); SECURITY-MODEL Concourse rotation cadence note dropped.
- **New Leg 4 added**: `04-remove-concourse-and-self-modification`. Deletes `ci/`, removes `THE_ONE_CONCOURSE_PASS`, audits Dockerfile/docker-compose, revises narrative docs (README, agents.md, CLAUDE.md, SECURITY-MODEL.md), updates mission-control `projects.md` description. Historical M01-M08 artifacts left intact.
- Flight title shifts from "Integrity Gate Restoration" to "Code Hygiene + Concourse Removal." Slug retained.
- Mission outcome paragraph + flight contributing-criteria + leg specs all annotated with the pivot. Original framing preserved as commentary; new framing is the live spec.

**What's NOT removed**: the agent's runtime ability to `Write` / `Edit` / run shell commands stays (those are general tools, not a "self-modification feature"). What goes is the *narrative* + the CI/CD substrate that supported the deploy-and-rollback flow.

**Repo + module names**: still `the-one` (repo) and `the_one` (Python module). Rename decision deferred to M10.

**Authentication blocker resolution**: no longer applicable. The Concourse auth issue is itself evidence FOR the removal (rotation hygiene gap C7 was real; password drift between `.env` and server is the symptom).

### 2026-05-15 — Leg 1 design review (post-flight-start)

- **Agent spawned**: Developer (Sonnet) for `review-leg-design` on Leg 1.
- **Outcome**: approve with changes; 3 high-severity + 4 medium + 2 low issues raised.
- **High-severity fixes applied**:
  1. `fly -t local` may not be authenticated; added explicit step 0 verification + login prompt
  2. Bind-mount probe added to step 0 — confirm pipeline's `WORKSPACE_PATH` resolves to operator's working tree via a unique-marker file before Option A is valid
  3. Acceptance criterion #6 rephrased to clearly allow E402 fix at `interfaces/web/api.py:660` (the prior "format-driven whitespace" framing implicitly disallowed it)
- **Medium-severity fixes applied**: Context now lists all 4 production lint hits not just 2; ruff fix counts framed as "currently ~X" not fixed; Edge Cases section added `set -e`-equivalent regression detection + "gate appears to reject downstream" diagnostic.
- **Low-severity fixes applied**: `set_pipeline` command spelled out; manual-verification step prefixed `(manual)`; belt-and-suspenders `wc -l` check added.
- **Skipped 2nd review cycle**: changes were corrective (no new design). Per skill: "Skip if only minor/cosmetic fixes were applied" — these fixes were closer to clarification than substantive redesign.
- **Open design questions answered inline** in the leg spec: (1) bind-mount probe failure → PAUSE and surface, no auto-fallback; (2) E402 `noqa` authorized if load-bearing with inline comment; (3) experiment success = "fail at ruff step specifically," not downstream.

### 2026-05-15 — Flight start

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-side, not default fallback). Crew extracted: Developer (Sonnet, used for design review + implementation + fix-review-issues + commit), Reviewer (Sonnet, no Opus per skill), Accessibility Reviewer (Sonnet, not needed for this flight — no UI changes).
- **Branch**: `flight/01-integrity-gate-restoration` created off `main` (note: collision-free with M08's merged `flight/01-brand-foundation` because slug differs).
- **Mission state transition**: `09-maintenance` mission status `planning` → `active`. Flight 1 status `ready` → `in-flight`.
- **Initial commit**: planning scaffold (maintenance/2026-05-15.md, missions/09-maintenance/*) committed at flight start. Subsequent commits will be leg work; final commit will check off legs + flight in artifacts and bring statuses to `completed`.
- **Reconnaissance Report at top of this log** was authored during flight design — every cited scope item is `confirmed-live` on current `main`. No retirements, no scope changes.
- **Execution model per skill**: per-leg design review by spawned Developer, then per-leg implementation by spawned Developer, then ONE flight-level Reviewer pass on all uncommitted changes, then ONE final commit checking off all legs + the flight. Tests run with `docker exec the-one pytest -x --timeout 30` per crew prompt — not `docker compose exec` which can wedge on TTY.

---

## Leg Progress

### Leg 1 — 2026-05-15

- **Status transition**: `ready` → `in-flight` (step 1 of leg procedure).
- **Step 0 progress**:
  - Confirmed current lint baseline matches scaffold-time snapshot: 69 errors total (32 E501, 13 I001, 10 F401, 7 E402, 3 F841, 2 N802, 2 N806). Production-side hits confirmed at the four scaffold-identified sites: `agent/core.py:98 E501`, `interfaces/web/api.py:660 E402`, `mcp/_tool_provider.py:38 I001`, `mcp/client.py:263 E501`.
  - **`fly -t local status` failed** (exit 1, "please login again. token validation failed with error: not authorized"). Cannot proceed to pipeline-freshness check, bind-mount probe, or deliberate-violation experiment without authenticated `fly`.
- **`[BLOCKED:fly-auth]` signaled to Flight Director.** Operator action required: interactive `fly -t local login`. Per leg spec (Implementation Guidance step 0) and the leg's stop-and-surface conditions, I PAUSED rather than improvising. Cleanup work (steps 2–3) is deferred because the leg ordering is "experiment FIRST so a failure case can expand leg scope before cleanup; cleanup work is wasted if the gate doesn't actually enforce."
- **Working tree state at pause**: leg status set to `in-flight`; flight-log updated with Reconnaissance Report (pre-existing) and this Leg Progress entry; no source-tree changes; no commits beyond the planning scaffold; no `.ci-bind-mount-probe.tmp` file created yet.

### Leg 1 — 2026-05-15 (post-pivot resume)

- **Scope on resume**: lint+format restoration ONLY (deliberate-violation experiment dropped per the Concourse-removal pivot above). Slug retained for branch-history continuity.
- **Lint baseline**: 69 errors before → 0 after.
  - `ruff check --fix .` fixed 27 (auto-fixable I001/F401; transient count rose to 73 as import-sort reshuffled blocks revealed adjacent issues, then settled at 46 remaining).
  - `ruff check --fix --unsafe-fixes .` fixed 3 (F841 unused-variable assignments in `test_oauth_test_connection_endpoint.py`; reviewed diff — left one orphan `api_mod.__dict__.get(...)` no-op call from the unsafe-fix). Safe.
  - Hand-fixed 43 remaining: 32 E501 (mostly long `pytest.mark.skip(reason=...)` strings wrapped via adjacent-string-literal pattern, plus a few helper-call line wraps; one `# noqa: E501` for a 102-char comment in `test_flow_admin_tools_grid.py`), 7 E402 (4+2 in `tests/browser/test_flow_studio_tools_overrides.py` and `tests/browser/test_studio_mcps_tab.py` resolved by moving import blocks above the `pytestmark = pytest.mark.skip(...)` line; 1 production at `interfaces/web/api.py:660` resolved via `# noqa: E402` with inline reason pointing to the existing comment block above), 2 N802 (`# noqa: N802` for env-var-name-embedded test function names in `test_openrouter_wire_level.py`), 2 N806 (renamed `INITIAL`/`RESOLVED` → `initial`/`resolved` plus 4 downstream usages in `test_process_and_broadcast_live_read.py`).
- **E402 disposition** at `interfaces/web/api.py:660`: kept import in place; added `# noqa: E402` with inline reason. The 10-line comment block at lines 651-659 already explains the deliberate placement (forward-reference avoidance). Moving the import to the top would create a forward reference to `_MASKED_API_KEY_SENTINEL` and fail at module import.
- **Format baseline**: 81 files would-reformat before → 0 after. `ruff format the_one/ tests/` rewrote 78 files (close to recon's 81; the small drift is because some of the hand-fix wrapping already normalized 3 files into format-clean shape). `ruff check` re-verified 0 after format pass.
- **Collection check**: `docker exec the-one pytest --collect-only -q` reports `1683/2058 tests collected (375 deselected) in 1.29s`. **Zero collection errors** — the 6 asgi-lifespan errors anticipated in the leg context did not materialize on the post-Concourse-pivot working tree (likely because `pip install asgi-lifespan` already happened during another path, or the addopts-default deselection covers them; Leg 2 will still verify with its dedicated probe).
- **Broad pytest at leg end**: `docker exec the-one pytest --timeout 30 -q --ignore=tests/browser` → **1679 passed, 4 skipped, 12 deselected, 0 failures, 0 errors** in 94s. The pre-existing `test_sandbox_eperm_on_unshare` failure mentioned in the leg context also did not surface — `test_mcp_sandbox_integration.py` reports `.....sss.....` (5 pass, 3 skip, 5 pass). **No NEW failures introduced beyond pre-existing baseline (baseline is now effectively 0).**
- **Production-code changes** (acceptance criterion: no logic change):
  - `the_one/agent/core.py:98` — line wrap (E501)
  - `the_one/interfaces/web/api.py:660` — `# noqa: E402` + import paren-wrap
  - `the_one/mcp/_tool_provider.py:38` — import reorder (I001)
  - `the_one/mcp/client.py:263` — split docstring first line (E501)
  - 9 MCP files reformatted by `ruff format` — whitespace/wrapping only, no logic change
  - Smoke-tested all four production-touched modules via `docker exec the-one pytest -x --timeout 30 <file>` — all passing.
- **No anomalies.** All steps proceeded cleanly. The 4 production-side lint hits matched the recon's locations exactly (no drift).
- **Commit**: pending below — single `flight/01: restore ruff lint+format zero baseline` commit on `flight/01-integrity-gate-restoration`.
- **Status transition**: `in-flight` → `landed` (completion held until flight close).

---

## Decisions

(Populated during execution. The deliberate-violation experiment result lands here.)

---

## Deviations

(Populated during execution.)

---

## Anomalies

### 2026-05-15 — `fly -t local` not authenticated at Leg 1 step 0

- **Observation**: `fly -t local status` exits 1 with "please login again. token validation failed with error: not authorized".
- **Impact**: blocks the deliberate-violation experiment (the actual Leg 1 deliverable per Architect framing). Lint/format cleanup is deliberately deferred until after the experiment confirms the gate enforces — otherwise the cleanup is wasted work if the gate is silently broken.
- **Resolution path**: operator runs `fly -t local login` interactively, then leg execution resumes at step 0's pipeline-freshness check + bind-mount probe.
- **Foreseen by leg design**: yes — leg spec explicitly anticipated this in the "may not be authenticated" note. The recovery is a one-shot operator action, not a leg-scope expansion.

---

## Session Notes

(Populated during execution.)
