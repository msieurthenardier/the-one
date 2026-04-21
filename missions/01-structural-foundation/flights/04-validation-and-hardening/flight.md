# Flight: Validation & Hardening

**Status**: in-flight
**Mission**: [Structural Foundation](../../mission.md)

## Contributing to Criteria

- [ ] Each architectural concern lives in a clearly bounded module with explicit public interfaces
- [ ] New functionality can be added by creating files in designated locations without modifying core agent code
- [ ] The tool system supports registry-based management with runtime enable/disable per agent
- [ ] The plugin architecture supports both built-in tools and future MCP client integrations through a unified `ToolProvider` protocol
- [ ] The architecture supports multiple agent definitions, each with their own prompt, tool set, LLM provider, and configuration
- [ ] An `agents.md` file provides development-facing self-awareness context
- [ ] The extension model is documented with clear patterns for adding tools, providers, and future extension types
- [ ] Core modules have unit tests that run in isolation; integration tests validate the agent step cycle end-to-end
- [ ] The Concourse pipeline runs the full test suite as a hard gate before deployment
- [ ] The codebase has minimal external dependencies
- [ ] A developer can understand where to add a new capability by reading the project structure and extension documentation alone

---

## Pre-Flight

### Objective

Close out Mission 01 by resolving all outstanding technical debt from prior flights, fixing lint violations, documenting test conventions, verifying the full system end-to-end (deploy, rollback), and checking off mission success criteria. Autopilot remains paused — self-improvement workflows are a future mission concern. This is a cleanup-and-verification flight, not a feature flight.

### Open Questions

_(none — scope is well-defined from flight 03 debrief action items and mission checklist)_

### Design Decisions

**Backfill flight 03 log inline**: Populate the empty Decisions, Deviations, and Anomalies sections of the flight 03 log using information already captured in the flight 03 debrief. This is documentation catch-up, not new analysis.
- Rationale: The debrief already has the content; the log just wasn't maintained during execution.
- Trade-off: None.

**Fix all ruff violations**: 36 total violations across `the_one/`: 16 E501 (line too long), 2 F401 (unused imports), 3 F541 (f-string without placeholders), 4 I001 (unsorted imports), 2 F841 (unused variables). 10 are auto-fixable via `ruff check --fix`. The remaining E501 violations need manual line breaks. F841 (unused variables in `self_deploy.py` and `test_runner.py`) require manual judgment.
- Rationale: Clean lint is a mission success criterion prerequisite. Most fixes are mechanical.
- Trade-off: None.

**Replace hardcoded tool count with `> 0` assertion**: Change `assert len(tools) == 14` to `assert len(tools) > 0` in `test_builtins.py`. The test's purpose is to verify builtins load, not to enforce an exact count.
- Rationale: Exact count is brittle. The test already checks protocol compliance and attribute presence on all tools — the count assertion adds no value beyond "something loaded."
- Trade-off: Won't catch accidental tool removal, but individual tool tests would be the right place for that.

**Fix rollback job to use containerized execution**: The rollback job runs `${WORKSPACE_PATH}/ci/deploy.sh rollback` as a bare command inside a `docker:cli` container — that host path doesn't exist in the container. This is a bug, not just an inconsistency. Change to the same `docker run ... -v "${WORKSPACE_PATH}:/src:ro" ... sh /src/ci/deploy.sh rollback` pattern used by deploy and auto-rollback.
- Rationale: Bug fix. The current rollback job only works if the Concourse worker happens to share the host filesystem.
- Trade-off: None.

**Check off mission criteria by auditing each one**: Walk through all 11 success criteria, verify each against the actual codebase, and check off those that are met. Any that are genuinely unmet should be noted as known issues.
- Rationale: The criteria are functionally met but never formally checked off.
- Trade-off: None.

### Prerequisites

- [x] Flight 03 merged to main
- [x] Deploy pipeline functional (build #15 passed)
- [x] Ollama running with qwen2.5:7b

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

This flight is a series of small, independent fixes followed by a verification sweep. No architectural changes — just polish, documentation, and validation. The work naturally splits into: code fixes (lint, tests, pipeline), documentation updates (CLAUDE.md, flight log, mission criteria), and verification (deploy, rollback, autopilot).

### Checkpoints

- [ ] All ruff violations fixed (`ruff check the_one/ tests/` clean)
- [ ] All tests pass (`pytest tests/ --tb=short -q`)
- [ ] Pipeline.yml consistent (all deploy.sh calls use containerized pattern)
- [ ] CLAUDE.md documents test conventions
- [ ] Mission success criteria audited and checked off

### Adaptation Criteria

**Divert if**:
- End-to-end verification reveals a regression that requires code changes beyond simple fixes

**Acceptable variations**:
- Mission criteria audit may reveal criteria that need rewording rather than checking off
- Additional small fixes discovered during verification can be folded in

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `code-fixes` — Fix all 36 ruff violations (E501, F401, F541, I001, F841), replace hardcoded tool count in test_builtins.py, fix rollback job in pipeline.yml
- [x] `documentation-updates` — Add test conventions to CLAUDE.md, backfill flight 03 log sections, audit and check off mission success criteria
- [ ] `verify-and-deploy` — Deploy to verify all changes, run AIAT tests against live agent, trigger rollback job to verify it works

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] `ruff check the_one/ tests/` clean
- [ ] `pytest tests/ --tb=short -q` passes
- [ ] Deploy succeeds with selftest passing
- [ ] Rollback job works
- [ ] All mission success criteria checked off or noted as known issues

### Verification

The flight is verified when:
- The full deploy pipeline passes (test → build → deploy → selftest)
- The rollback job executes successfully
- All mission success criteria are formally addressed
- `ruff check` and `pytest` are both clean
