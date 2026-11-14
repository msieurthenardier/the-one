# Flight: Code Hygiene + Concourse Removal

**Status**: completed
**Mission**: [Maintenance (Post-M08)](../../mission.md)

> **Original framing**: "Integrity Gate Restoration" — restore the M06 lint+format zero-baseline AND prove the Concourse pipeline gate enforces via a deliberate-violation experiment. **Pivot 2026-05-15** (mid-flight, after Leg 1 implementation blocked on Concourse auth): operator decision to remove Concourse + self-improvement framing from the project entirely. The deliberate-violation experiment is moot. Several "fix the CI" items become "remove the CI" items. A new Leg 4 is added for the removal. The cleanup work (lint+format, asgi-lifespan, sandbox skip predicate, OAuth XSS, _clean_npx allowlist, agents.md docs, .env.example, OpenRouter rebrand strings) is still valuable and proceeds in Legs 1-3 with narrowed scope.

## Contributing to Criteria

- [x] `ruff check the_one/ tests/` returns 0 errors on `main`
- [x] `ruff format --check the_one/ tests/` returns "all files already formatted"
- [x] ~~CI lint+format gate proven to reject violations via deliberate-violation experiment~~ DROPPED — Concourse removed in Leg 4
- [x] `asgi-lifespan` installed in dev venv AND `make doctor` drift-detection target added (local-bench only — CI step dropped)
- [x] `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` skip predicate tightened
- [x] OAuth callback `postMessage` JSON escaped against `</script>` injection (all three flow sites)
- [x] `_clean_npx` package-name allowlist (npm-spec regex — rejects `../etc/passwd`)
- [x] `pip-audit` added to dev extras + `make audit` local target (CI step dropped)
- [x] `agents.md ## Provider type extension checklist` includes `_init_provider_state` entry
- [x] `agents.md ## Project Conventions` codifies "live-read across lazy-resolver boundary"
- [x] `.env.example` documents `THE_ONE_DEV_MODE` (survived the Leg 4 removal — operator-facing dev gate is independent of Concourse infrastructure)
- [x] `SECURITY-MODEL.md` Future Work names MCP `streamable-http` URL gating asymmetry
- [x] ~~`SECURITY-MODEL.md` documents Concourse team-password rotation cadence~~ DROPPED — Concourse removed in Leg 4
- [x] OpenRouter `_APP_URL` / `_APP_NAME` updated to GleepGlorp AI identity (`_APP_NAME = "GleepGlorp AI"`; `_APP_URL` retained as GitHub URL per repo-name-unchanged constraint)
- [x] Concourse infrastructure removed: `ci/` directory deleted; `THE_ONE_CONCOURSE_PASS` removed from `.env` (gitignored, local-only); `.env.example` already had no Concourse ref; `Dockerfile` and `docker-compose.yml` verified clean (no Concourse refs to clean)
- [x] Self-modification framing removed from `CLAUDE.md` (L56) and `SECURITY-MODEL.md` (3 sites). `README.md`, `agents.md`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `.env.example` all verified clean during recon — no edits needed. `projects.md` description in mission-control is gitignored (operator's local clone — verified at mission-control's .gitignore); staged-locally
- [x] Historical mission artifacts (M01-M08) left intact — they're the record of decisions made at the time, not the live framing

---

## Pre-Flight

### Objective

Restore the CI integrity gate posture M06 codified that M07/M08 silently eroded. Three legs: (1) lint/format restoration + pipeline audit + deliberate-violation experiment to prove the gate works going forward; (2) fix the two test-infrastructure issues that surfaced during the inspection (`asgi-lifespan` install gap, sandbox skip-predicate over-narrow); (3) ship a tight bundle of security one-liners + documentation carry-forwards.

### Open Questions

- [x] Should the deliberate-violation experiment land in flight log, report appendix, or both? → see Design Decisions
- [x] Drift-detection mechanism: `make doctor`, CI assertion, pre-commit, or combination? → see Design Decisions
- [x] OpenRouter rebrand strings here vs separate flight? → see Design Decisions

### Design Decisions

**Deliberate-violation experiment lives in the flight log**: Leg 1 creates a throwaway branch with a single `E501` violation introduced; pushes; `fly trigger-job`; documents the resulting Concourse build URL + exit code in `flight-log.md` under Decisions. If the gate rejects, log the success. If the gate passes the violation through, this becomes the leg's primary deliverable: investigate root cause before doing the cleanup work.
- Rationale: the flight log is the durable execution record; a separate appendix in the maintenance report would duplicate without adding clarity.
- Trade-off: future audits of the gate's history will need to grep across flight logs rather than reading a single report; acceptable for a single-developer project.

**Drift-detection mechanism: `make doctor` target**: Leg 2 adds `make doctor` that imports each declared dev extra (`asgi_lifespan`, `pytest_asyncio`, etc.) inside a `python -c` and fails with a clear `ModuleNotFoundError` message naming the missing extra. CI runs `make doctor` as the first step in the test task (before `ruff`).
- Rationale: `make doctor` is also useful interactively when a developer's venv is out of sync; CI invocation makes it a gate.
- Trade-off: pre-commit hook would catch drift earlier, but the dev-loop here is `make rebuild`-driven (container-based) so pre-commit is awkward; `make doctor` covers both bench and CI cases.

**OpenRouter rebrand strings bundled here, in Leg 3**: They live in `openrouter_provider.py:38-39`, are one-line changes, and Leg 3 is already the "small fixes + doc carry-forward" leg. Adding them does not change the leg's character.
- Rationale: avoid a separate trivial flight; the M08 mission-debrief flagged this as "low priority" but it's the kind of item that rots if not bundled opportunistically.
- Trade-off: none — pure inclusion.

### Prerequisites

- [ ] `main` clean (verified at scaffold: working tree clean, `main` in sync with `origin/main`)
- [ ] Maintenance report at `maintenance/2026-05-15.md` exists and is committed (or at least merged in the same PR as this flight) so success criteria backlinks resolve
- [ ] Operator has Concourse `local` target authenticated (`fly -t local status` returns OK) for the deliberate-violation experiment
- [ ] `asgi-lifespan` is in `pyproject.toml` dev extra (verified — declared but uninstalled in current venv)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites identified
- [x] Validation approach defined (per-leg verification steps; each finding has explicit acceptance criteria from the maintenance report)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Three sequential legs. Each leg lands as a separate commit so a per-leg `git revert` is a clean rollback if the deliberate-violation experiment surfaces a CI issue that takes time to diagnose.

**Leg 1 (Lint/format + gate audit)** is the highest-uncertainty leg. Run the experiment first, then do the cleanup. If the experiment fails (gate didn't reject), the leg's scope expands to include CI repair before continuing. If the experiment succeeds (gate rejects), the cleanup proceeds: `ruff check --fix .` for autofixable items, then hand-fix the ~46 unfixable ones, then `ruff format the_one/ tests/`. Verify zero baseline on both commands. Commit.

**Leg 2 (Test-infrastructure)**: `pip install asgi-lifespan` in the active venv; add `make doctor` target (Makefile addition) that imports each dev extra; add `make doctor` invocation as the first sub-step of CI's test task in `ci/pipeline.yml`. Tighten the `_has_sys_admin` skip predicate in `test_mcp_sandbox_integration.py` to also skip when `unshare -U` succeeds at module import (probe-actual-namespace-creation). Run broad pytest locally; verify exit code 0 (no errors at collection, no `test_sandbox_eperm_on_unshare` failures). Commit.

**Leg 3 (Security + docs sweep)**: small, mechanical, mostly one-liner edits. OAuth callback escape (one line in `api.py`); `_clean_npx` allowlist (one helper function + one call-site swap); `pip-audit` addition (pyproject.toml + pipeline.yml); three `agents.md` doc additions; `.env.example` line; `SECURITY-MODEL.md` two additions; OpenRouter rebrand strings. Verify nothing broke (run `make doctor` + ruff + broad pytest). Commit.

### Checkpoints

- [ ] Deliberate-violation experiment complete; CI gate behavior documented in `flight-log.md`
- [ ] Leg 1: ruff baseline restored to 0 errors, 0 would-reformat
- [ ] Leg 2: `make doctor` target works; broad pytest exits 0
- [ ] Leg 3: all small fixes land; broad pytest still exits 0; no regression in ruff baseline

### Adaptation Criteria

**Divert if**:
- Deliberate-violation experiment surfaces that CI never ran against M07/M08 PRs at all (i.e., the Concourse `set_pipeline` for `the-one` is unhealthy / not triggering). This becomes its own investigation; flight scope grows beyond ruff cleanup.
- `make doctor` reveals additional missing dev extras beyond `asgi-lifespan`. Investigate the venv-drift root cause (e.g., `pip install -e .[dev]` not idempotent across reinstalls).
- The OAuth callback escape fix breaks the M07 OAuth happy-path test. Roll back the change immediately; re-design with a different escape strategy (`<script type="application/json">` parser-split shape).

**Acceptable variations**:
- The 69-lint / 81-format counts may have drifted between report-time and execution-time (small commits during the same day). Acceptable as long as the post-fix baseline lands at 0.
- The `make doctor` target's exact set of imports can include or exclude packages at the executor's judgment (e.g., `playwright` may be too slow to import; could shell-out to `python -c "import playwright" 2>&1` quickly instead).

### Legs

- [x] `01-lint-format-restoration-and-gate-audit` — Restore ruff lint+format zero baselines (gate-audit dropped — Concourse removed in Leg 4; slug retained for branch-history continuity). Landed `7cb3f99`.
- [x] `02-test-infrastructure-fixes` — Install `asgi-lifespan`, add `make doctor` drift detection (local-bench only — CI step dropped), tighten sandbox skip-predicate. Landed `6f2e1f1`.
- [x] `03-security-and-docs-sweep` — OAuth callback XSS escape, `_clean_npx` allowlist, `pip-audit` + `make audit` (local-only), `agents.md` + `SECURITY-MODEL.md` + `.env.example` doc carry-forwards, OpenRouter rebrand strings. Landed `e092eb9` (security/CI) + `daf24e2` (docs).
- [x] `04-remove-concourse-and-self-modification` — Delete `ci/` directory; remove `THE_ONE_CONCOURSE_PASS` from env files; audit Dockerfile/docker-compose for CI-only references; revise narrative docs (README, agents.md, CLAUDE.md, SECURITY-MODEL.md) to drop self-modification + Concourse framing; update mission-control `projects.md` description. Landed `56bfc71`.

---

## Post-Flight

### Completion Checklist

- [ ] All three legs completed
- [ ] All success criteria contributing to this flight (listed at top) checked off
- [ ] `ruff check the_one/ tests/` returns 0; `ruff format --check the_one/ tests/` returns "all files already formatted"
- [ ] Broad pytest exits 0 (with the sandbox skip-predicate fix landed, this should be a clean exit, not just `-x`-terminated)
- [ ] Deliberate-violation experiment result documented in `flight-log.md`
- [ ] CI run on the merge confirms the gate rejected (or passed cleanly, after fixes) — record the build URL in `flight-log.md`
- [ ] All Action Required findings from this flight's scope (in maintenance report) checked off
- [ ] Flight debrief run (per M08 lesson: do NOT skip the debrief at flight close)
- [ ] Mission flight checkbox checked

### Verification

- `cd ~/projects/the-one && ruff check the_one/ tests/` → exit 0, "All checks passed!"
- `cd ~/projects/the-one && ruff format --check the_one/ tests/` → exit 0, "X files already formatted"
- `cd ~/projects/the-one && make doctor` → exit 0, all dev extras importable
- `cd ~/projects/the-one && pytest -q --tb=no` → exit 0, 1683+ collected, 0 errors at collection
- `cd ~/projects/the-one && grep -n "_init_provider_state\|live-read\|lazy-resolver" the_one/agents.md` → matches in `## Provider type extension checklist` and `## Project Conventions`
- `cd ~/projects/the-one && grep -n "THE_ONE_DEV_MODE" .env.example` → match
- `cd ~/projects/the-one && grep -n "MCP.*streamable-http\|streamable_http.*URL gating\|asymmetric" SECURITY-MODEL.md` → match
- `cd ~/projects/the-one && grep -n "GleepGlorp" the_one/llm/openrouter_provider.py` → match (no longer literal `"the-one"` in `_APP_*`)
- `cd ~/projects/the-one && pip-audit --skip-editable` → runs, reports findings (non-blocking)
- Manually triggered Concourse build for the merge passes lint+format gates
