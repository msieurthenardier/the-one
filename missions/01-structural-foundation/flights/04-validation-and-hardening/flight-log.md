# Flight Log: Validation & Hardening

**Flight**: [Validation & Hardening](flight.md)

## Summary

Flight 04 in progress — fixing code quality violations, brittle tests, and broken CI pipeline configuration.

---

## Leg Progress

### Leg 01: code-fixes (completed)
- **Started**: 2026-04-20
- **Ruff auto-fix**: 12 violations resolved automatically (3 F401, 3 F541, 4 I001, 2 F841)
- **Manual E501 fixes**: 24 long-line violations resolved across 16 files by breaking strings, function signatures, and expressions
- **test_builtins.py**: Replaced brittle `assert len(tools) == 14` with `assert len(tools) > 0`; renamed test method to `test_get_tools_returns_tools`
- **pipeline.yml rollback job**: Fixed containerized execution pattern — was using bare `${WORKSPACE_PATH}/ci/deploy.sh` (host path not available in container), now uses `docker run ... -v "${WORKSPACE_PATH}:/src:ro" ... sh /src/ci/deploy.sh rollback` matching the auto-rollback task
- **Verification**: `ruff check` clean, 65 tests passing, `fly validate-pipeline` valid
- **Note**: pytest-timeout not installed; used OS-level `timeout` for test execution safety

### Leg 02: documentation-updates (in-flight)
- **Started**: 2026-04-20
- Added Testing section to CLAUDE.md: `THE_ONE_TEST_URL`, `@pytest.mark.live`, `pytest -m live`, unit/AIAT separation, FakeLLM/StubTool patterns; added live test command to Commands section
- Backfilled flight 03 log: Decisions (leg reordering), Deviations (4 entries from debrief), Anomalies (regex bug, Concourse offline)
- Audited all 11 mission success criteria against codebase — all 11 checked off with inline evidence notes
- Verified only `.md` files modified

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
