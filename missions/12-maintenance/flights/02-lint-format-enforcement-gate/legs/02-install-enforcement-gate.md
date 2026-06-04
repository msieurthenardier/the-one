# Leg: install-enforcement-gate

**Status**: ready
**Flight**: [Lint/Format Enforcement Gate](../flight.md)

## Objective
Install a lint/format enforcement gate — a pre-commit hook and a CI check — that **fails** on any ruff violation or formatting diff, so the zero baseline from Leg 1 holds and the drift stops recurring (resolves the root cause of finding Q1).

## Context
- Maintenance report 2026-06-04, finding **Q1**: roundtable confirmed there is **no CI** (`.github/workflows/` absent), **no pre-commit hook** (`.git/hooks/` has only samples; no `.pre-commit-config.yaml`), and `make lint`/`make format` are manual targets nothing depends on. That absence is *why* the baseline drifts every cycle.
- This leg depends on Leg 1 having brought the tree to zero (a gate that fails immediately on existing violations is not landable).

## Inputs
- Tree at 0 ruff violations (Leg 1 complete).
- `pyproject.toml` ruff config as the single source of truth for rules.
- The repo is GitHub-hosted (`git@github.com:.../the-one.git`).

## Outputs
- `.pre-commit-config.yaml` with ruff lint + format hooks.
- A CI workflow (e.g. `.github/workflows/lint.yml`) running `ruff check` + `ruff format --check`, failing non-zero on violations.

## Acceptance Criteria
- [ ] `.pre-commit-config.yaml` exists with a ruff `check` hook and a ruff `format` (or `format --check`) hook pinned to a ruff version consistent with the project's
- [ ] A CI workflow runs on push/PR, executes `ruff check the_one/ tests/` and `ruff format --check the_one/ tests/`, and exits non-zero on any violation or formatting diff
- [ ] The gate is **proven**: a deliberately-introduced violation (tested locally, not committed) makes the pre-commit hook and `ruff format --check` fail; reverting restores green
- [ ] CI is green on clean `main`
- [ ] The gate uses the same ruff invocation/config as `make lint`/`make format` (one source of truth)

## Verification Steps
- `pre-commit run --all-files` (or the framework's equivalent) → passes on clean tree
- Introduce a temp lint violation → `pre-commit run` / `ruff check` exits non-zero; revert → passes
- Push a branch / open a PR → CI workflow runs and is green; a violating commit would fail it
- Confirm CONTRIBUTING/CLAUDE.md (or the Makefile help) tells contributors to install the hook (`pre-commit install`)

## Implementation Guidance

1. **Add the pre-commit config**
   - `.pre-commit-config.yaml` using the official `astral-sh/ruff-pre-commit` hooks: one for `ruff` (lint, optionally `--fix`) and one for `ruff-format`. Pin the rev to a ruff version matching the project's installed ruff.

2. **Add the CI workflow** (confirm host at flight start per the flight prerequisite)
   - GitHub Actions: `.github/workflows/lint.yml` on `push`/`pull_request` — checkout, set up Python 3.11, install ruff (or `pip install -e ".[dev]"`), run `ruff check the_one/ tests/` then `ruff format --check the_one/ tests/`. Both must fail the job on non-zero exit.
   - If the operator declines GitHub Actions, fall back to enforcing via the pre-commit hook + documenting it as a required local step, and note the gap in the flight log.

3. **Document installation**
   - Add a one-line note (CLAUDE.md "Commands" or a CONTRIBUTING section) that contributors run `pre-commit install` once. Mention the gate exists so future maintenance cycles don't re-discover its absence.

4. **Prove the gate**
   - Temporarily add a trivial violation (e.g. an unsorted import), confirm the hook and `ruff format --check` reject it, then revert. Record the proof in the flight log — this is the step M09 explicitly recommended ("prove the gate via deliberate-violation experiment").

## Edge Cases
- **Ruff version skew** between the pre-commit pin, the CI install, and the container's ruff can produce "passes locally, fails in CI" — pin all three to the same version.
- **Snapshot/golden artifacts** are gitignored (per project policy); ensure the CI lint job does not depend on any gitignored baseline.

## Files Affected
- `.pre-commit-config.yaml` - new, ruff hooks
- `.github/workflows/lint.yml` - new, CI lint+format check (host pending confirmation)
- `CLAUDE.md` or `CONTRIBUTING.md` - one-line install note

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry (include the deliberate-violation proof)
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
