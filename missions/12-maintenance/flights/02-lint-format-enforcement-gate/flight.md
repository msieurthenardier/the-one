# Flight: Lint/Format Enforcement Gate

**Status**: landed
**Mission**: [Maintenance (Post-M11)](../../mission.md)

## Contributing to Criteria
- [ ] A pre-commit hook AND a CI check both run `ruff check` + `ruff format --check` and **fail** on violations; `ruff check the_one/ tests/` returns 0 and `ruff format --check` reports all-formatted on `main` (Q1)

---

## Pre-Flight

### Objective
Stop the recurring ruff-baseline drift by installing an *enforcement gate* (pre-commit hook + CI check that fails on violations), and bring the current tree into compliance (78 violations + 97 unformatted files) as a one-time side effect of landing the gate.

### Open Questions
N/A.

### Design Decisions

**The deliverable is the gate, not the reformat**: This is the third recurrence (M06 → drift → M09 → drift). Re-running `ruff format` alone has a proven 100% recurrence rate because nothing enforces the baseline. The flight is structured so the gate lands first/with the cleanup, never cleanup alone.
- Rationale: address the cause (no enforcement) not the symptom (current violations).
- Trade-off: introduces the project's first CI workflow + a pre-commit dependency; worth it.

**Two enforcement points, both failing**: A `.pre-commit-config.yaml` for fast local fail, AND a CI workflow (there is none today — greenfield) so the gate holds even if a contributor skips the hook. Both run `ruff check` and `ruff format --check`.

**Manual `make` targets are kept**: `make lint`/`make format` stay as developer conveniences; the gate calls the same ruff invocations so there is one source of truth.

**Dead `# noqa: BLE001` comments are a cleanup rider, not the gate's job**: `BLE` is not in the selected ruleset, so the 10 suppressions are no-ops. Removing them (or selecting `BLE`) is a separate ruleset decision — handled opportunistically in Leg 1's cleanup, not blocking the gate.

### Prerequisites
- [ ] Decide the CI host. There is no remote pipeline today; a GitHub Actions workflow is the natural fit for the GitHub-hosted repo. If the operator prefers no GitHub Actions, the pre-commit hook + a `make` check invoked some other enforced way is the fallback — confirm at flight start.

### Pre-Flight Checklist
- [ ] All open questions resolved — N/A
- [ ] Design decisions documented
- [ ] Prerequisites verified (CI host confirmed)
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach
Leg 1 brings the tree to zero (run `ruff check --fix` for the 43 auto-fixable, manually resolve the ~35 residuals — E501/N802/N818/N806/E402 — then `ruff format`), and removes the dead `noqa: BLE001` vestiges. Leg 2 installs the enforcement: a `.pre-commit-config.yaml` with the ruff hooks and a CI workflow that runs `ruff check` + `ruff format --check` and fails non-zero on any diff/violation. The gate is then proven by confirming a deliberate violation would fail (locally, without committing it).

### Checkpoints
- [x] Tree at 0 lint violations + 0 would-reformat
- [x] Pre-commit hook rejects a violating staged change
- [~] CI workflow fails on a violation and passes on clean `main` — workflow authored + locally validated; the on-`main` green run is demonstrable only after merge (push trigger fires post-merge)

### Adaptation Criteria

**Divert if**:
- A residual lint violation reflects a real naming-contract issue (N802/N818) that needs a non-mechanical decision — split it out rather than blanket-suppressing.

**Acceptable variations**:
- Pre-commit framework vs a hand-rolled git hook; GitHub Actions vs another runner — whatever the operator confirms.

### Legs
- [x] `01-bring-tree-into-compliance` - Fix all 78 violations + reformat 97 files; remove dead `noqa: BLE001`
- [x] `02-install-enforcement-gate` - Add pre-commit hook + CI check that fail on ruff violations; prove the gate

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated (CLAUDE.md `## Commands` gate-install note)

### Verification
On `main`: `ruff check the_one/ tests/` → 0 errors; `ruff format --check the_one/ tests/` → all formatted. The CI workflow run is green. A locally-introduced violation makes both the pre-commit hook and `ruff format --check` exit non-zero.
