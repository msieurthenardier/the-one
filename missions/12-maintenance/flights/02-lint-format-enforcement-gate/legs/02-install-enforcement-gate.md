# Leg: install-enforcement-gate

**Status**: completed
**Flight**: [Lint/Format Enforcement Gate](../flight.md)

## Objective
Install a lint/format enforcement gate — a pre-commit hook and a CI check — that **fails** on any ruff violation or formatting diff, so the zero baseline from Leg 1 holds and the drift stops recurring (resolves the root cause of finding Q1).

## Context
- Maintenance report 2026-06-04, finding **Q1**: roundtable confirmed there is **no CI** (`.github/workflows/` absent), **no pre-commit hook** (`.git/hooks/` has only samples; no `.pre-commit-config.yaml`), and `make lint`/`make format` are manual targets nothing depends on. That absence is *why* the baseline drifts every cycle.
- This leg depends on Leg 1 having brought the tree to zero (a gate that fails immediately on existing violations is not landable).

## Inputs
- Tree at 0 ruff violations (Leg 1 complete).
- `pyproject.toml` ruff config (`[tool.ruff]`) as the single source of truth for rules; path args `the_one/ tests/` are the shared scope across `make lint`/`make format` and the gate.
- The repo is GitHub-hosted; **CI host = GitHub Actions (operator-confirmed at flight start).**
- **Authoritative ruff version = 0.15.15** (container). Note the host venv is currently 0.15.11 (drifted under the `ruff>=0.6` floor) — that drift is precisely what this gate exists to stop.

## Outputs
- `.pre-commit-config.yaml` with ruff lint + format hooks pinned to `rev: v0.15.15`.
- `.github/workflows/lint.yml` — GitHub Actions, ruff-only, check/fail-only.
- `pyproject.toml` `[dev]` extra: `ruff` pinned to `==0.15.15`; `pre-commit` added.
- A new `make format-check` target so the format-gate invocation has a make-target home.
- CLAUDE.md `## Commands` note on installing/activating the hook.

## Design Resolutions (from Leg 2 design review)
- **Version pinning (root-cause for Q1's recurrence):** pin all enforcement points to ruff **0.15.15** — pre-commit `rev: v0.15.15`; CI installs `ruff==0.15.15` *directly* (NOT `pip install ".[dev]"`, which pulls the heavy dev tree and re-resolves ruff to latest); and tighten the `[dev]` extra from `ruff>=0.6` to `ruff==0.15.15` so host/container/CI converge. Future ruff bumps become one deliberate line that flows everywhere.
- **Fix vs. check asymmetry:** CI is **check/fail-only** — `ruff check the_one/ tests/` (NO `--fix`) and `ruff format --check the_one/ tests/`. The CI must fail, never mutate. The local pre-commit hook uses the standard `ruff` (`args: [--fix]`) + `ruff-format` (auto-fix, fail-on-change) for good local ergonomics — it still blocks the commit on any violation.
- **pre-commit launcher:** add `pre-commit>=3` to the `[dev]` extra so `pip install ".[dev]"` provides it; document `pipx install pre-commit` as the standalone alternative. (pre-commit runs ruff in its own isolated env keyed by `rev`, so the gate is unaffected by the host venv's 0.15.11.)

## Acceptance Criteria
- [x] `.pre-commit-config.yaml` exists, `rev: v0.15.15`, with a `ruff` (lint, `--fix`) hook AND a `ruff-format` hook
- [x] `.github/workflows/lint.yml` runs on `pull_request` and `push` to `main`, with a `concurrency` cancel-in-progress block, installs `ruff==0.15.15`, runs `ruff check` then `ruff format --check`, exits non-zero on any violation/diff (check-only). Action versions pinned (`@v4`/`@v5`)
- [x] `pyproject.toml` `[dev]` extra: `ruff==0.15.15` (was `ruff>=0.6`) and `pre-commit>=3` added
- [x] `make format-check` target added (`docker exec the-one ruff format --check the_one/ tests/`)
- [x] The gate is **proven** (stage/run/revert): pre-commit (4.6.0) + `ruff check`/`format --check` all rejected a deliberate violation (exit 1); reverting restored green. Proof recorded in the flight log
- [~] CI is green on clean `main` — will be demonstrable once the PR's `push:{branches:[main]}` run fires post-merge (cannot run before the workflow is on main)
- [x] CLAUDE.md `## Commands` documents activating the hook (`pre-commit install`), how to obtain pre-commit, and CI parity
- [x] The gate mirrors the project's ruff config + path args (`the_one/ tests/`) — one source of truth

## Verification Steps
- `pre-commit run --all-files` → passes on the clean (post–Leg 1) tree
- **Prove the gate (stage, run, revert):** introduce a temp violation in a real source file, `git add` it (pre-commit only sees *staged* files), `pre-commit run --files <file>` → non-zero; `ruff format --check` on an unformatted temp → non-zero; then `git restore --staged <file>` + `git checkout -- <file>` → clean
- After push/PR: the CI workflow runs and is green on the clean tree; a violating commit would fail it
- `make format-check` exits 0 on the clean tree
- CLAUDE.md `## Commands` shows the hook-install note

## Implementation Guidance

1. **Add the pre-commit config**
   - `.pre-commit-config.yaml` using `astral-sh/ruff-pre-commit` at `rev: v0.15.15`, two hooks: `id: ruff` with `args: [--fix]` (lint + auto-fix, fails on change) and `id: ruff-format`. Do not set custom file args — the hooks honor `pyproject.toml`'s `[tool.ruff]` config and operate on the staged files.

2. **Add the CI workflow** (GitHub Actions — confirmed host)
   - `.github/workflows/lint.yml`: triggers `pull_request:` (all PRs) and `push: { branches: [main] }`; a `concurrency: { group: lint-${{ github.ref }}, cancel-in-progress: true }` block; one job on `ubuntu-latest`: `actions/checkout@v4`, `actions/setup-python@v5` (python 3.11), `pip install ruff==0.15.15`, then `ruff check the_one/ tests/` and `ruff format --check the_one/ tests/` as separate steps (both fail the job on non-zero). **Check-only — never `--fix` in CI.** Ruff-only: NO pytest, NO Playwright, NO gitignored snapshot/golden baselines (per project policy).

3. **Pin the toolchain in `pyproject.toml`**
   - Change the `[dev]` extra `ruff>=0.6` → `ruff==0.15.15`; add `pre-commit>=3`. (Container already has 0.15.15; this keeps future rebuilds + any `.[dev]` consumer converged. No rebuild required for the gate to function now.)

4. **Add the `make format-check` target**
   - `format-check: ## Ruff format check (read-only)` running `docker exec the-one ruff format --check the_one/ tests/`. Mirrors the existing `make lint`/`make format` style (Makefile:144-150).

5. **Document installation**
   - In CLAUDE.md's `## Commands` section, right after the existing "Lint & format" block: a short note that contributors run `pre-commit install` once (and `pipx install pre-commit` if they don't have it), that the same checks run in CI, and that the gate exists (so a future maintenance cycle doesn't re-discover its absence — the M09 recurrence concern). No new CONTRIBUTING.md (none exists; keep the manual single-sourced).

6. **Prove the gate**
   - Stage a trivial violation (e.g. an unsorted import) in a real file, confirm the hook + `ruff format --check` reject it, then revert. Record the proof (commands + observed non-zero exits) in the flight log — the deliberate-violation experiment M09 recommended.

## Edge Cases
- **Ruff version skew** between the pre-commit pin, the CI install, and the container's ruff produces "passes locally, fails in CI" — all three are pinned to 0.15.15 here. The host venv's 0.15.11 does not affect the gate (pre-commit isolates ruff at `rev`), but pinning the `[dev]` extra converges it on next sync.
- **Snapshot/golden artifacts** are gitignored (project policy); the CI lint job is ruff-only and depends on no baseline — keep it that way.
- **`pre-commit run` only sees staged files** — the gate-proof must `git add` the violation (never commit), then revert.

## Files Affected
- `.pre-commit-config.yaml` - new, ruff + ruff-format hooks at `rev: v0.15.15`
- `.github/workflows/lint.yml` - new, GitHub Actions ruff-only check/fail gate
- `pyproject.toml` - `[dev]`: `ruff==0.15.15` (was `>=0.6`) + `pre-commit>=3`
- `Makefile` - new `format-check` target
- `CLAUDE.md` - hook-install note in `## Commands`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry (include the deliberate-violation proof)
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
