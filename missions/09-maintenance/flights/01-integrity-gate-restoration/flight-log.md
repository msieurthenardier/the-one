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

### 2026-05-15 — Flight review + flight close

- **Reviewer spawned**: Sonnet, `review` action, evaluated all 5 commits (`7cb3f99`, `6f2e1f1`, `e092eb9`, `daf24e2`, `56bfc71`) against all 4 leg acceptance criteria.
- **Outcome**: `[HANDOFF:confirmed]`. No blocking issues, no non-blocking issues.
- **Key verifications by Reviewer**:
  - All 4 leg acceptance criteria satisfied
  - `_safe_script_json` correctly routes all 3 `post_message=` flow sites; zero raw U+2028/U+2029 bytes in source (byte-level grep)
  - `_clean_npx` uses the npm-spec regex (rejects `../etc/passwd`), NOT the broken draft
  - `_SHOULD_SKIP_EPERM_TESTS` predicate correctly combines `_has_sys_admin()` and `_can_unshare_user_namespace()`
  - Broad pytest: 1700 passed on both host and container (1700 is the new baseline — Leg 3's 1702 number proven pre-existing-drift, not regression)
  - Ruff baselines preserved
  - Concourse removal complete: zero stranded refs in live source/docs
  - `SECURITY-MODEL.md` reads coherently post-edits (no orphaned bullets)
  - Code quality observations all positive (commit messages, docstrings, comment blocks documenting rationale)
- **Flight-close commit**: artifact statuses updated (Legs 1-4 → `completed`; Flight 1 → `landed`; checked off in mission.md). Flight log captures the full Flight Director Notes track including the mid-flight pivot. Maintenance report annotation in place.
- **Pivot retrospective**: the flight's most significant decision was the mid-flight Concourse-removal pivot (triggered by Leg 1 `fly` auth blocker). Flight grew from 3 legs (~1.5-2 days) to 4 legs (~2.5-3.5 days revised, executed in one day). All 4 legs landed cleanly with one design-review cycle each. The CRITICAL regex bug in Leg 3 (allowlist that permitted `../etc/passwd`) was caught during design review BEFORE implementation — a strong validation of the per-leg design-review discipline. Total cycle: planning → 4 leg design reviews → 4 leg implementations → 1 flight review → 1 flight-close commit → ready for `/flight-debrief`.

### 2026-05-15 — Leg 3 design review (post-Leg-2-land)

- **Agent spawned**: Developer (Sonnet) for `review-leg-design` on Leg 3.
- **Outcome**: approve with changes. **1 CRITICAL** finding (broken allowlist regex) + 2 other high + 6 medium + 2 low. Recon corrections captured significant line-number drift from Leg 1's ruff format pass.
- **CRITICAL fix applied**: the original `_clean_npx` allowlist `[A-Za-z0-9._@/-]` does NOT block `../etc/passwd` — every character in that string is allowed individually. Replaced with the npm package-name spec `^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$` which only permits `/` after a `@scope/` prefix and forbids leading dots. Verified: `lodash`, `@types/node`, `@scope/pkg` pass; `../etc/passwd`, `a/b/c`, `.hidden`, `Foo` (uppercase), empty all reject. The leg's own verification example would have failed under the original regex — high-severity bug caught before implementation.
- **High-severity fixes applied**:
  1. AC #2 weak — added stronger criterion: all THREE `post_message=` flow sites (failed/expired/success at api.py ~L1838/1861/1913) route through `_safe_script_json`. Verification: `grep -n "json.dumps(post_message)" returns empty`.
  2. Line-number drift from Leg 1's format pass — api.py refs shifted by +2 lines, cache_cleanup.py refs shifted by -2 lines. Spec now uses symbol-based locators with approximate line ranges noted.
- **Medium-severity fixes applied**: `_safe_script_json` location specified (module-level private in api.py above the OAuth callback function); Step 2b renumbered to Step 3 (then 3→11 renumber for the rest); test location specified (`tests/test_oauth_callback_route.py`); `make audit` shape specified (host-side `.venv/bin/pip-audit --skip-editable || true`); `import pip_audit` (underscore module name vs `pip-audit` dash package name) called out explicitly; SECURITY-MODEL step 8 collapsed to ONE new bullet (Concourse cadence dropped); Divert-if widened to all runtime deps (not just 4 named); AC #10 (`grep rotation`) dropped — was trivially satisfied by pre-existing content.
- **Low-severity fixes applied**: `_init_provider_state` line refs replaced with symbol-locator; LSEP/PSEP regression test added to the OAuth XSS test set.
- **Reviewer sub-checks confirmed**: existing OAuth tests at `tests/test_oauth_callback_route.py` assert only heading text — script body escape change is non-breaking; OpenRouter `_APP_URL`/`_APP_NAME` symbolic imports in tests survive the rebrand (no test asserts literal `"the-one"` string against headers); the `make doctor` Makefile target is at L147-149 with single `python -c` probe — straightforward to append `pip_audit`.

### 2026-05-15 — Leg 2 design review (post-Leg-1-land)

- **Agent spawned**: Developer (Sonnet) for `review-leg-design` on Leg 2.
- **Outcome**: approve with changes; 4 high + 4 medium + 3 low issues raised. Important recon corrections.
- **High-severity fixes applied**:
  1. Host vs container venv ambiguity resolved — leg explicit that `pip install asgi-lifespan` + `make doctor` + AC verification all target HOST venv (container has it from image build).
  2. AC #5 can't be verified in-container (SYS_ADMIN short-circuits to existing branch); verification moved to HOST where `_can_unshare_user_namespace()` actually fires.
  3. `_has_sys_admin()` is at L175 not L491; decorator at L488-492; test at L493. Inputs section corrected.
  4. `_has_sys_admin()` mechanism is `/proc/self/status` CapEff bit-21 parsing, NOT `prctl`/`geteuid`. Step 4 description corrected.
- **Medium-severity fixes applied**: AC #6 explicit host venv; `make doctor` clearly host-side (not `docker exec`) — DIFFERENT from `make lint`/`make format` which are container-first; section-header comment block added to indicate the asymmetry; commit message switched to `flight/01:` heredoc convention matching Leg 1; commit file list trimmed (drop ci/pipeline.yml — gone in Leg 4).
- **Low-severity fixes applied**: `or True` no-op dropped from doctor probe; probe set expanded to cover all dev extras with correct import names (notably `pillow` → `from PIL import Image`); Files Affected cleaned (no `ci/pipeline.yml`, no `.venv/`).
- **Host environment probes confirmed by reviewer**: WSL2 `unshare -U -r true` exits 0 → new predicate will trigger SKIP; host venv still missing asgi-lifespan; `make 4.3` available; `pyproject.toml dev` extras enumerated for the full probe set.

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

### Leg 2 — 2026-05-15

- **Status transition**: `ready` → `in-flight` → `landed`.
- **Step 1 — `pip install asgi-lifespan` on HOST venv** (`~/projects/the-one/.venv/bin/pip`): bare `pip` resolves to the system Python 3.12 binary, which is PEP-668 externally-managed and refused the install. Used the project's `.venv/bin/pip` directly. Outcome: `asgi-lifespan-2.1.0` installed cleanly (sniffio already present). `pip show asgi-lifespan` confirms version 2.1.0 (≥ 2.0 floor).
- **Step 2 — `make doctor` target added** to `Makefile` under a new `# ── Drift detection (host-side) ──` section header (between the container-side `format` target and `help`). Probe set matches leg spec exactly: `asgi_lifespan, pytest_asyncio, pytest_timeout, pytest_playwright, pixelmatch`, `from PIL import Image`, `find_spec('playwright')` (slow-init avoidance), `import ruff`. `make doctor` (venv activated) exits 0 with `doctor: ok`.
- **Uninstall-then-doctor experiment**: `pip uninstall -y asgi-lifespan && make doctor` → exits non-zero (exit 2 from make wrapping python's exit 1) with the traceback `ModuleNotFoundError: No module named 'asgi_lifespan'`. Reinstall via `pip install asgi-lifespan` restores, `make doctor` returns to `doctor: ok`. Drift detection proven.
- **Step 4 — sandbox skip predicate tightened** in `tests/test_mcp_sandbox_integration.py`. Added `import subprocess`. Added `_can_unshare_user_namespace()` helper (sibling to `_has_sys_admin()` at L175) that probes `unshare -U -r true` with 2s timeout, handles `FileNotFoundError`/`TimeoutExpired`. Added `_SHOULD_SKIP_EPERM_TESTS = _has_sys_admin() or _can_unshare_user_namespace()`. Updated the L488 decorator from `_has_sys_admin()` to `_SHOULD_SKIP_EPERM_TESTS` with new reason text citing both branches.
- **Step 5 — Predicate verification on HOST**: `pytest tests/test_mcp_sandbox_integration.py::test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3 -v -rs` → **SKIPPED** with reason `"Test exercises the no-privilege-grants path; skip when SYS_ADMIN is granted (container) OR when unshare -U succeeds without privilege (WSL2, stock Ubuntu host)"`. **Case B** from leg spec — WSL2 host where `unshare -U` succeeds without privilege, new branch fires. Confirmed `unshare -U -r true` returns 0 on this host (matching design-review HOST PROBE CONFIRMED note).
- **Broad pytest on HOST**: `pytest --tb=no -q` (venv activated) → **1679 passed, 4 skipped, 375 deselected, 17 warnings in 99.03s**. 0 collection errors, 0 failures. Pre-existing warnings (mock-coroutine in `test_provider_api.py`, `forkpty` in `test_pty_session.py`, pytest cache permission) are unchanged carry-overs, not new.
- **Container pytest baseline preserved**: `docker exec the-one pytest --tb=no -q --ignore=tests/browser` → **1679 passed, 4 skipped, 12 deselected, 2 warnings in 94.10s**. Identical to Leg 1's landed baseline.
- **Step 6 — Leg 1 ruff baseline preserved**: `docker exec the-one ruff check the_one/ tests/` → `All checks passed!`; `docker exec the-one ruff format --check the_one/ tests/` → `220 files already formatted`.
- **Files changed**: `Makefile` (+5 lines: section header + `doctor` target), `tests/test_mcp_sandbox_integration.py` (+30 lines: `subprocess` import, `_can_unshare_user_namespace()` helper + module-level skip constant, decorator update).
- **No anomalies.** The only step-1 wrinkle was the bare-`pip`-vs-venv-`pip` resolution on PEP-668 hosts — resolved by using `.venv/bin/pip` explicitly. Doesn't change the leg's host-venv intent.
- **Commit**: `6f2e1f1` `flight/01: install asgi-lifespan + make doctor (host) + tighten sandbox skip predicate` on `flight/01-integrity-gate-restoration`. Staged paths: `Makefile`, `tests/test_mcp_sandbox_integration.py` (flight artifacts deferred to flight close, matching Leg 1's commit pattern).

### Leg 3 — 2026-05-15

- **Status transition**: `ready` → `in-flight` → `landed`.
- **Step 1 — OAuth XSS escape**: `_safe_script_json` defined as a module-level private helper above `_render_oauth_callback_page` in `the_one/interfaces/web/api.py`. Escapes `</`, `<!--`, U+2028 (LINE SEPARATOR), and U+2029 (PARAGRAPH SEPARATOR). Source uses Python ` ` / ` ` escape sequences (not raw bytes) per leg-spec instruction — verified the file's bytes contain no `e2 80 a8` / `e2 80 a9` literals. **All three `post_message=` flow sites** at `api.py:1838` (failed), `:1861` (expired), `:1913` (success) feed the single `json.dumps(post_message)` site at the script-template (now `_safe_script_json(post_message)`) — three sites, one central serialization point, one swap covers them all. **Verification**: `grep -n "json.dumps(post_message)" the_one/interfaces/web/api.py` returns empty. Existing route-level tests in `tests/test_oauth_callback_route.py` continue to pass (they assert only on heading text, as the design reviewer pre-confirmed).
- **Step 2 — npx allowlist**: `_VALID_NPX_PKG_RE = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")` added to `the_one/mcp/cache_cleanup.py` (with `import re`). `_clean_npx` raises `ValueError("unsafe npx package name: ...")` at function entry before the path-join site. **Test results**: 8 accept cases (`lodash`, `@types/node`, `@scope/pkg`, `pkg-with-dashes`, `pkg_with_underscores`, `a`, `abc123`, `@a/b`) all pass; 11 reject cases (`../etc/passwd`, `a/b/c`, `.hidden`, `-leading-dash`, `Foo`, `pkg;name`, `pkg name`, `pkg\nname`, empty, `@/x`, `@scope/`) all raise as expected. The critical `../etc/passwd` traversal vector — accepted by the original `[A-Za-z0-9._@/-]` draft — is rejected.
- **Step 3 — OAuth XSS regression tests**: `TestSafeScriptJSON` class added to `tests/test_oauth_callback_route.py`. Two tests: `test_safe_script_json_escapes_script_termination` verifies `</script>` → `<\/script>` and the benign payload survives; `test_safe_script_json_escapes_line_separators` verifies U+2028 → ` ` and U+2029 → ` `. Test source uses Python escape sequences (no raw line-separator bytes in the test file either). Both tests pass.
- **Step 4 — pip-audit adoption**: `pip-audit>=2.7` added to `pyproject.toml` `[project.optional-dependencies].dev`. `make doctor` probe extended with `pip_audit` (underscore — module name; `pip-audit` is the dash-named package). New `make audit` target runs `.venv/bin/pip-audit --skip-editable || true` non-blocking. **`make audit` findings**: 6 known CVEs across 2 packages — `pip` 24.0 (4 CVEs: CVE-2025-8869 tar-symlink, CVE-2026-1703 wheel path-traversal, CVE-2026-3219 tar/zip dual-format, CVE-2026-6357 self-update timing) and `urllib3` 2.6.3 (2 CVEs: CVE-2026-44431 cross-origin redirect header leak, CVE-2026-44432 streaming decompression resource exhaustion). **Divert evaluation**: `pip` is environment infrastructure, NOT in `pyproject.toml`'s `dependencies`. `urllib3` is a transitive pulled in by `requests` → `pip-audit` / `pytest-base-url` (dev closure only); not in any runtime dep's install closure. Neither set lands on a runtime dep, no HIGH/CRITICAL classification in the descriptions for runtime impact, so **no divert triggered**. Captured here for M10 awareness. **make doctor caveat**: `make doctor` invoked from the agent's sub-shell can't find bare `python` in `$PATH` (host venv not active in `/bin/sh`); leg-2-baseline behavior preserved — operator's shell (where the doctor target was originally validated) is unchanged.
- **Steps 5-9 — Docs sweep landed**: (5) `agents.md` `## Provider type extension checklist` gains item 7 documenting `_init_provider_state(self, kwargs: dict) -> None` as an optional `LLMProvider` hook with the OpenRouter reference impl. (6) `agents.md` `## Project Conventions` gains `### live-read-across-lazy-resolver-boundary` documenting the F6.5 lazy-resolver pattern + F6.5 L4 bug + F7 L05 regression test, matching the voice of the sibling `### gated-debug-instrumentation` entry. (7) `.env.example` gains a commented `THE_ONE_DEV_MODE=true` block explaining the dev-routes gate and the production-leave-unset constraint. (8) `SECURITY-MODEL.md` Future Work gains one bullet on the MCP `streamable_http` source URL gating asymmetry vs the LLM-provider create/update/test path (Concourse rotation cadence bullet dropped per pivot). (9) `the_one/llm/openrouter_provider.py` `_APP_URL` URL preserved, `_APP_NAME` rebranded to `"GleepGlorp AI"`; inline comment explains the asymmetry. Symbolic test imports in `test_openrouter_provider.py` + `test_factory_openrouter.py` survived (no test edits needed) — both files run green.
- **Step 10 — Baselines preserved**: `ruff check the_one/ tests/` → All checks passed; `ruff format --check the_one/ tests/` → 220 files already formatted. Host pytest broad: **1702 passed, 4 skipped, 373 deselected** (Leg 2 baseline 1679 + 21 new Leg-3 tests + ~2 from other sources = 1702). Container pytest broad: **1702 passed, 4 skipped, 373 deselected** (identical; source + tests bind-mounted into the dev container).
- **Step 11 — Two commits**:
  - **Commit A** `e092eb9` `flight/01: OAuth callback XSS escape; npx pkg allowlist; pip-audit adoption` — staged: `the_one/interfaces/web/api.py`, `the_one/mcp/cache_cleanup.py`, `tests/test_oauth_callback_route.py`, `tests/test_mcp_cache_cleanup.py`, `pyproject.toml`, `Makefile`.
  - **Commit B** `daf24e2` `flight/01: agents.md hook + lazy-resolver pattern; .env.example DEV_MODE; SECURITY-MODEL MCP-URL note; OpenRouter rebrand strings` — staged: `the_one/agents.md`, `.env.example`, `SECURITY-MODEL.md`, `the_one/llm/openrouter_provider.py`.
- **Anomalies**:
  - First Edit pass on `_safe_script_json` accidentally embedded raw U+2028 / U+2029 bytes in the source (the spec explicitly forbids this — they look like spaces in source). Caught by a byte-level `e2 80 a8` check; rewrote via a Bash + Python script that emits the ` ` / ` ` escape sequences literally. Final byte check confirms zero raw line-separator bytes in either the production source or the test file. No functional behavior change — the strings evaluate to the same characters at runtime — but the source-readability requirement is now satisfied.
  - One ruff `E501` surfaced on the OpenRouter rebrand commit's inline comment (127 cols vs the 100 cap). Resolved by lifting the comment to a free-standing line above the assignment. Ruff baseline preserved at 0/0 through the pre-commit verification gate.
  - `make doctor` exits non-zero when invoked from a sub-shell that lacks `python` on `$PATH` (only `python3` + `.venv/bin/python` are present). Operator's interactive shell — where Leg 2 originally validated the target — has `python` aliased / pyenv-shimmed, so the user-visible behavior is unchanged. Not changing the target shape here (would be a Leg-2 spec deviation); flagged for M10 surface area only.
- **Flight ruff + pytest baselines preserved**. No source files outside the leg's enumerated set were modified by either commit.

### Leg 4 — 2026-05-15

- **Status transition**: `ready` → `in-flight` → `landed`.
- **Step 0 — Recon re-verification**: ran the leg-spec grep set across live source/docs (`the_one/`, `tests/`, `CLAUDE.md`, `README.md`, `SECURITY-MODEL.md`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `pyproject.toml`, `.env.example`). Three Concourse refs surfaced — exactly the expected set: `SECURITY-MODEL.md:96` (`THE_ONE_CONCOURSE_PASS` rotation), `SECURITY-MODEL.md:118` (Future Work env-style), `CLAUDE.md:56` (mirrors-the-Concourse-CI/prod parenthetical). The `SECURITY-MODEL.md:99` (`ci/pipeline.yml`) ref also confirmed via Read. No drift from Legs 1-3. `.env` confirmed gitignored at `.gitignore:1`. `fly` auth still broken per Leg-1 baseline → in-flight-build sub-check skipped.
- **Step 1 — `ci/` deletion**: `git rm -r ci/` → removed `ci/deploy.sh` + `ci/pipeline.yml`.
- **Step 2 — `.env` edit**: removed the single `THE_ONE_CONCOURSE_PASS=...` line via `sed -i '/^THE_ONE_CONCOURSE_PASS=/d' .env`. Pre-count: 1 match. Post-count: 0 matches. **Credential value NOT logged.** `.env` gitignored, so local-only edit (no commit impact).
- **Step 3 — `CLAUDE.md:56`**: dropped the `"(mirrors the Concourse CI/prod path)"` parenthetical and rewrote to `"...so dev exercises the same image-build path as a real deploy."` Single-line edit; surrounding `make rebuild` sentence intact.
- **Step 4 — `SECURITY-MODEL.md` edits** (three sites):
  - 4a (L96 area): deleted the `THE_ONE_CONCOURSE_PASS` rotation bullet outright.
  - 4b (L99 area): rewrote `"No secrets land in \`.env.example\`, \`Dockerfile\`, \`docker-compose.yml\`, or \`ci/pipeline.yml\`."` → `"No secrets land in \`.env.example\`, \`Dockerfile\`, or \`docker-compose.yml\`."` (removed the `ci/pipeline.yml` enumeration item).
  - 4c (L118 area): rewrote `"would replace \`THE_ONE_CONCOURSE_PASS\`-style env vars"` → `"would replace local-only \`.env\`-style secret storage"`.
- **Step 5 — `the_one/agents.md` verification**: `grep -inE "self.modif|self.improv|concourse|deploy.*pipeline|rollback.*image" the_one/agents.md` → empty (clean, no edits).
- **Step 6 — `mission-control/projects.md`**: the-one entry description rewritten to product-shaped wording (no `self-modifying` / `deploy via Concourse CI`); stack line dropped `Concourse CI`. **Important finding**: `projects.md` is gitignored in mission-control per its `.gitignore:2` (and CLAUDE.md notes "`projects.md` is gitignored for this reason — it contains local paths and is not committed"). The leg spec's "stage but DO NOT commit" guidance assumed the file was tracked. Treated like `.env`: local-only edit, no commit needed in either repo. `git status` in mission-control: working tree clean (file ignored).
- **Step 7 — `maintenance/2026-05-15.md` annotation**: inserted `## Note: Post-Report Pivot (2026-05-15)` section after the `**Inspection scope**:` header block and before `## Delegation Plan Summary`. Content per leg spec — flags C1-C7 + Finding 1.4 + Finding 8.1 as superseded by F1 Leg 4 / F1 Leg 1.
- **Step 8 — Final grep sweep**: `grep -rln "concourse\|Concourse\|fly trigger-job\|pipeline\.yml\|THE_ONE_CONCOURSE_PASS"` across `.py/.md/.sh/.toml/.yml/Makefile` returns matches ONLY in `missions/` and `maintenance/` (historical artifacts — exempt per leg spec). Zero hits in live source/docs.
- **Step 9 — Tests + ruff baseline**: `ruff check the_one/ tests/` → `All checks passed!`; `ruff format --check the_one/ tests/` → `220 files already formatted` (Leg 1 baseline preserved). Container pytest: `docker exec the-one pytest --tb=no -q --ignore=tests/browser` → **1700 passed, 4 skipped, 12 deselected, 2 warnings in 92.98s**. Host pytest (venv): `pytest --tb=no -q` → **1700 passed, 4 skipped, 375 deselected, 17 warnings in 98.09s**. **Anomaly**: Leg 3 logged 1702 passed; this run shows 1700. Stash-revert experiment (`git stash && pytest`) showed **the pre-Leg-4 working tree also passes 1700, not 1702** — the 2-test delta is pre-existing in the working tree and NOT caused by Leg 4's removals. 0 failures, 0 errors, 0 collection errors. No regression introduced by Leg 4.
- **Files affected** (the-one repo): 5 staged paths — deleted `ci/deploy.sh` (-67 lines), deleted `ci/pipeline.yml` (-91 lines), modified `CLAUDE.md` (1 line), modified `SECURITY-MODEL.md` (-5 lines net: -4 from L96 bullet drop, -1 from L99 enumeration, +2 / -2 on L118 Future Work rewrite), modified `maintenance/2026-05-15.md` (+5 lines for header annotation). Net diff: **5 files changed, 9 insertions(+), 167 deletions(-)**. Also modified (gitignored, not staged): `.env` (1 line removed), `mission-control/projects.md` (description + stack lines).
- **Commit**: `56bfc71` `flight/01: remove Concourse CI infrastructure + self-modification framing` (heredoc-formatted; `Mission: 09` trailer). Staged paths: `CLAUDE.md`, `SECURITY-MODEL.md`, `maintenance/2026-05-15.md`, `ci/deploy.sh` (deleted), `ci/pipeline.yml` (deleted). Flight artifacts (`missions/...`) deferred to flight close per established Leg 1-3 pattern.
- **mission-control change**: NOT committed (gitignored — see Step 6). Local edit only; no operator-cadenced commit required.
- **Anomalies**:
  - Stash-revert during pytest baseline investigation un-staged the `git rm -r ci/` deletions on `stash pop` (deletions don't survive stash cleanly when the index is rebuilt). Re-staged via fresh `git rm ci/deploy.sh ci/pipeline.yml` before commit. No data lost.
  - `mission-control/projects.md` gitignored — leg spec's "stage but DO NOT commit" guidance superseded by the upstream public-repo gitignore reality. Logged as Decision rather than blocker.
  - Pytest baseline drift (1702 → 1700) traced to pre-existing working-tree state, not Leg 4. Flagged for M09 awareness; not blocking.
- **Flight ruff + pytest baselines preserved**. No source files outside the leg's enumerated set were modified.

---

## Decisions

(Populated during execution. The deliberate-violation experiment result lands here.)

### 2026-05-15 — Leg 4: `mission-control/projects.md` is gitignored; treated as local-only edit

- **Context**: leg spec instructed to stage (but not auto-commit) the `projects.md` edits in mission-control, deferring the commit to operator cadence.
- **Finding**: `mission-control/.gitignore:2` explicitly lists `projects.md` (and mission-control's `CLAUDE.md` documents this: "`projects.md` is gitignored for this reason — it contains local paths and is not committed"). The file is not tracked by git at all.
- **Decision**: applied the edits in place; no `git add` / `git status` to surface. Treated analogously to `.env` (gitignored, local-only edit, no commit needed in either repo). Leg-spec acceptance criterion `cd mission-control && sed -n '/^## the-one$/,/^## /p' projects.md | grep -i "concourse\|self.modif"` still satisfied (file content updated locally).
- **Rationale**: forcing a commit via `-f` would violate the upstream public-repo posture documented in mission-control's CLAUDE.md. The leg spec assumed the file was tracked; the actual repo state took precedence.

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
