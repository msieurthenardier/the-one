# Leg: pre-merge-lint-gate

**Status**: completed
**Flight**: [Supply-chain & CI gate](../flight.md)

## Objective
Restore a fast pre-merge CI gate — a lint-only (+ pip-audit) GitHub Actions workflow triggered on pull requests — without re-enabling the heavy lanes that were deliberately cost-shifted to local Concourse.

## Context
Maintenance report 2026-07-10 finding **C1** (+ **C4**): GH Actions `lint.yml`/`test.yml` are `workflow_dispatch`-only since `76659fb` (flight/8 "CI cost-shift to local Concourse"); Concourse validates post-merge on `main` (its `repo` resource polls `branch: main`); the only pre-merge gate is a `ci/README.md` note to run `fly execute`. 10 PRs (#143–152) merged with no automated pre-merge verification; no branch protection. The declared `pip-audit` dev-dep is never invoked in any pipeline (C4).

## Inputs
- `.github/workflows/lint.yml` (currently `workflow_dispatch`-only), `test.yml`, `windows-installer.yml`.
- `ci/tasks/lint.yml` (the Concourse lint task — the enforcing gate on main), `ci/README.md`, `ci/the-one.pipeline.yml`.
- Repo Makefile lint targets; `ruff` config in `pyproject.toml`.

## Outputs
- A pre-merge GitHub Actions workflow that runs `ruff check` + `ruff format --check` (and `pip-audit`) on `pull_request`, failing the build on violations. `ci/README.md` updated to reflect the restored fast pre-merge lane.

## Acceptance Criteria
- [x] A GitHub Actions workflow triggers `on: pull_request` (targeting `main`) and runs `ruff check` + `ruff format --check` as fail-on-nonzero steps (mirror the Concourse `ci/tasks/lint.yml` command shape + pinned ruff version). (`pr-lint.yml` `lint` job; `ruff==0.15.15` pinned to match `ci/tasks/lint.yml`.)
- [x] A `pip-audit` step/job runs in the same workflow (C4), auditing the **runtime closure only** and **failing** on findings. **Mechanism** (design-review [MEDIUM]): audit the runtime deps without contaminating the env with pip-audit's own toolchain deps — e.g. `uv export --no-dev --format requirements-txt > req.txt && pip-audit -r req.txt` (or equivalent). This is a **deliberate policy change** from the existing warn-only `make audit` (`Makefile:229-231`, `pip-audit --skip-editable || true`) — call it out as intentional inline + in `ci/README.md`. After Leg 1 closes the seven runtime clusters, this job is green; it only re-reddens when a new runtime CVE appears (the intended signal). (Separate `pip-audit` job; `uv export --no-dev --no-emit-project` — the `--no-emit-project` flag drops the editable `-e .` self-entry that pip-audit's `--require-hashes` install can't resolve. Policy change documented inline + in ci/README.md. Local run: "No known vulnerabilities found".)
- [x] The **heavy lanes stay off GH Actions PR triggers** — do NOT add test/browser/windows to `pull_request`; the deliberate cost-shift to Concourse (post-merge on `main`) is preserved. `test.yml`/`windows-installer.yml` triggers unchanged except as needed. (No changes to `test.yml`/`windows-installer.yml`/`lint.yml`; only the new `pr-lint.yml` added.)
- [x] Actions are pinned consistently with the repo's existing convention (note: C3 flagged floating major tags as a deferred advisory — match existing style, don't regress). (`actions/checkout@v5` + `actions/setup-python@v6`, matching the existing workflows' major-tag style.)
- [x] `ci/README.md` documents the restored pre-merge lint lane and that heavy lanes remain post-merge on Concourse.
- [x] The workflow YAML is valid (parse-check / `actionlint` if available) and the current tree passes it (ruff already clean — 0 violations, 408 files formatted). (Parsed via PyYAML — actionlint unavailable. Local tree: `ruff check` = "All checks passed!", `ruff format --check` = "408 files already formatted", pip-audit runtime closure clean.)

## Verification Steps
- Validate the workflow YAML (actionlint or a parse check).
- Confirm the current working tree passes the exact commands the workflow runs (`ruff check`, `ruff format --check`, `pip-audit`).
- Confirm no heavy lane was added to `pull_request`.

## Implementation Guidance
1. Add a **new** `.github/workflows/pr-lint.yml` (do NOT re-scope `lint.yml` — design-review: `lint.yml:3-5` carries a "manual break-glass fallback only" comment and `ci/README.md`'s parity table frames it that way; re-purposing risks stale framing) with `on: pull_request: branches: [main]`, a Python setup, then `ruff check` + `ruff format --check` + the runtime-only `pip-audit`.
2. Keep it fast — install only what the checks need. Mirror `ci/tasks/lint.yml`'s ruff invocation and pinned version for parity.
3. Decide the pip-audit failure policy (recommend: fail on the runtime-closure set; the `--ignore-vuln` list or a dev/runtime split for the pip toolchain IDs) and document it inline + in `ci/README.md`.
4. Do not touch the Concourse pipeline or re-enable heavy GH lanes on PRs.

## Edge Cases
- If `pip-audit` in CI would flag the pip-toolchain findings, gate them out explicitly (documented) so the job reflects runtime risk, not toolchain noise.
- Ensure the workflow doesn't require secrets (lint/audit need none) so it runs on PRs from any context.

## Files Affected
- `.github/workflows/pr-lint.yml` (new) or `.github/workflows/lint.yml` (re-scoped); `ci/README.md`.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] YAML valid; current tree passes the checks
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] **Final leg** — batch-reviewed (1 blocking finding: pyproject floors incomplete → fixed; re-verified), committed/PR
