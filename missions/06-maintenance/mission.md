# Mission: Maintenance — Pre-Mission-06 Quick Wins

**Status**: active

## Outcome

Resolve codebase health issues identified in maintenance report [2026-05-04](../../maintenance/2026-05-04.md). Land 14 Action Required findings as 7 bundled, atomic legs in a single focused flight. Each bundle is low-risk, ≤4 file touches, no schema/migration churn, no architectural change. Net effect: green test suite on `main`, lint enforced in CI, three high-impact a11y gaps closed, CI hardened with pinned tags + `.dockerignore` + correct `auto-rollback` verification, cheap web-side hardening (Origin allowlist + non-https provider warning), Concourse credentials rotated, and the project's no-auth threat model documented explicitly.

## Context

Mission 05 (Built-In Tool System) just completed. `/routine-maintenance` ran the project's first-ever maintenance inspection and produced [maintenance/2026-05-04.md](../../maintenance/2026-05-04.md): 0 Critical, 14 Action Required, 28 Advisory, 7 Pass. All Critical-claimed findings (CICD-C1 manual-trigger pipeline, INSP-C1 Concourse passwords in git history) were correctly downgraded by the Architect — the project is a single-user local dev tool with documented "operator-trusted setup, NOT malicious actor" threat model (F3 Decision 10), and the repo is private on GitHub with localhost-only Concourse.

The 14 Action Required findings split cleanly into 7 bundles, each addressable as a single atomic leg. All Advisory findings are deferred to either: (a) the M05 mission-debrief backlog (already triaged), (b) the maintenance report's "Known Debt Carried Forward" section for architectural items too large for a quick-win pass, or (c) opportunistic follow-up flights (dependency refresh, observability, mypy bring-up). Documentation backlog from M05 is similarly deferred.

This is the project's first dedicated maintenance mission. The 7-bundle structure is intentionally conservative — each leg should land cleanly without dependency on the others, allowing partial completion if priorities shift mid-flight.

## Success Criteria

- [x] Test suite green on `main` for both container and host runs (`tests/test_token_definitions.py::test_every_var_reference_is_defined` passes; `tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist` passes regardless of CWD)
- [x] CI pipeline runs `ruff check` and `ruff format --check` against `the_one/` and `tests/`; `workspace/` excluded from ruff
- [x] One-shot `ruff format` + `ruff check --fix` applied; existing 30 lint errors resolved
- [x] Chat surface meets WCAG 2.1 AA for keyboard + screen reader baseline: chat message log has live region, chat input has accessible name, info-icon tooltips are reachable via keyboard and screen reader
- [x] All four Concourse pipeline images pinned (digest or specific tag); `mcr.microsoft.com/playwright/python:v1.58.0-jammy` retained, `docker:cli` and `curlimages/curl:latest` replaced; `Playwright` pinned in `pyproject.toml` to match CI image
- [x] `.dockerignore` exists at repo root excluding `.env*`, `.git/`, `workspace/`, `__pycache__/`, `*.egg-info/`, `missions/`, `docs/`, `.memory/`, `.pytest_cache/`
- [x] `auto-rollback` re-runs health-check after rollback and fails loudly on healthcheck timeout; "no rollback image exists" handled explicitly on first deploy
- [x] Health-check loop fails loudly with explicit "app never came up after 60s" message when 12/12 attempts fail (instead of falling through to a connection-refused error from selftest)
- [x] Origin-allowlist middleware rejects state-mutating requests from disallowed origins; default `http://127.0.0.1:*` + configurable
- [x] LLM provider configurations with non-`https://` `base_url` for non-localhost hosts are warned (or refused) at save time
- [x] Local Concourse + Concourse-admin passwords rotated; `.env` updated; old passwords invalidated in local Concourse
- [x] `SECURITY-MODEL.md` (or section in `agents.md`) documents the no-auth posture, single-user local-only deployment context, and dev-mode `0.0.0.0` bind expectation; stale `agents.md:3` and `:263-264` lines updated; M04 F5 heading-hierarchy a11y refinement absorbed if cheap

## Stakeholders

- **Primary user**: solo developer/operator who interacts with the agent daily; owns the local dev environment

## Constraints

- **No architectural change** — every leg must be ≤4 file touches; no schema migrations; no new abstractions
- **No new dependencies** — Bundle E's Origin-allowlist is a small middleware function in `the_one/interfaces/web/`, not a new package
- **No git history rewrite** — Bundle F rotates passwords and updates `.env` but explicitly does NOT use `git filter-repo` / BFG (private repo, single-dev, low ROI/high risk)
- **Preserve M01-M05 functionality** — every leg ends with `pytest` green and `playwright` browser tests green
- **Linux/WSL only** — no cross-platform validation required for this maintenance pass

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`)
- Docker and docker-compose (existing dev loop via `make rebuild`)
- Playwright Python binding for browser tests (M04 baseline)
- ruff for linting and formatting
- Local Concourse instance for credential rotation (Bundle F)

## Open Questions

N/A — all design decisions are absorbed in the per-leg Acceptance Criteria.

## Known Issues

N/A — issues are tracked in maintenance/2026-05-04.md and `missions/05-built-in-tool-system/mission-debrief.md`.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses.

- [x] Flight 1: **Pre-Mission-06 Quick Wins** — 7 atomic legs covering all 14 Action Required findings from maintenance/2026-05-04.md
- [x] Flight 2: **Debrief Follow-ups** — 5 legs absorbing the action items surfaced in Flight 01's debrief (doc patches, edge-case tests, Origin-allowlist hardening, host-env dependency clarity, cross-project admin-pass rotation)
- [ ] Flight 3 *(optional, separable)*: **Dependency Refresh** — one-shot bulk update of 16 outdated deps + verify tests green
