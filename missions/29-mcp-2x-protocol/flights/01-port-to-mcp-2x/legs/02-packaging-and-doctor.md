# Leg: packaging-and-doctor

**Status**: completed
**Flight**: [Port to the mcp 2.x SDK at parity](../flight.md)

## Objective
Make the Windows packaged build carry everything `mcp` 2.3.0 needs, and give `the-one doctor` a twelfth gate, `mcp sdk`, which proves that in a frozen build (flight DD11).

## Context
- **Origin:** this leg was split out of `sdk-port` at leg design (see the flight log). It runs after `sdk-port` has landed, in the same worktree and uncommitted tree. The Flight Director reviews and commits the whole flight at once.
- **Why the package list grows:** with `mcp` 2.3.0, the SDK path also needs `mcp_types`, `httpx2`, `httpcore2`, `truststore` and `opentelemetry`.
  - `packaging/windows/the-one.spec` collects only `mcp` submodules (~75), filtering out `mcp.cli`.
  - 2.3.0's `mcp/server/fastmcp.py` is a stub that raises on import, so the submodule walk must filter it as well.
  - `httpx2/__version__.py` and `httpcore2/__init__.py` call `importlib.metadata.version()` at import time, so they need `copy_metadata`.
  - The spec's comment still says "pinned 1.27.0".
- **How the doctor reports:** `the_one/diagnostics.py::run_doctor` prints a fixed `gates` list (~1032-1044), currently eleven gates ending with `time zones`, and its docstring says "eleven".
  - Both Windows lanes grep the gate lines by name: `ci/tasks/windows-installer-build.yml` (the needle list ~117) and the break-glass `.github/workflows/windows-installer.yml` (`grep -q "…: OK" doctor.out` lines ~129-135).
  - `tests/test_doctor.py::test_gates_list_has_eleven_names_ending_with_time_zones` (~867) pins the exact list.
  - `CLAUDE.md`'s Knowledge-bases paragraph names the ninth to eleventh gates.
- **Gate placement:** the new gate runs unconditionally on every host, like `time zones`. It is appended last.
- **This leg cannot run the Windows lanes.** Running them is the `hat` leg's job; here, check that the spec and workflow files are well-formed.

## Inputs
- `sdk-port` landed: `mcp==2.3.0` is installed in the worktree `.venv`, and `the_one.self_configuration.surface` imports on 2.x.

## Outputs
- `packaging/windows/the-one.spec`, `the_one/diagnostics.py`, `tests/test_doctor.py`, `ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml`, `CLAUDE.md` and `the_one/agents.md` (wherever it lists doctor gates) are updated.
- The flight log has a `packaging-and-doctor` entry.

## Acceptance Criteria
- [x] AC1: `packaging/windows/the-one.spec`:
  - collects submodules of `mcp_types`, `httpx2`, `httpcore2`, `truststore` and `opentelemetry` (each with `on_error="warn"`, as `mcp` has) and adds them to the hidden imports;
  - filters `mcp.server.fastmcp` out of the `mcp` walk alongside `mcp.cli`;
  - adds `copy_metadata("httpx2")` and `copy_metadata("httpcore2")` to the datas;
  - replaces the stale "pinned 1.27.0" comment, and the comment explains each addition the way the file's existing comments do.
- [x] AC2: `run_doctor` has a twelfth gate named `mcp sdk`, appended after `time zones`, and implemented as a `_probe_…` function returning `ProbeResult` like its siblings. It:
  - imports `mcp`, `mcp.types.version` and `the_one.self_configuration.surface`;
  - builds a `truststore` SSL context;
  - passes with a detail naming the `mcp` version and the handshake revision (e.g. `mcp 2.3.0, handshake 2025-11-25`);
  - fails with the exception text, ASCII-safe like its siblings, when an import or the context fails.

  It runs unconditionally on every host. The `run_doctor` docstring says "twelve" and describes the gate.
- [x] AC3: `tests/test_doctor.py`:
  - The gate-list test is renamed for twelve gates ending with `mcp sdk` and asserts the new order. Log the rename as a changed expectation.
  - A new test covers the gate's failure path: monkeypatch the import seam so an import raises, and assert the result is not OK and its detail carries the reason.
- [x] AC4: `ci/tasks/windows-installer-build.yml`'s needle list and `.github/workflows/windows-installer.yml`'s `grep -q` checks both include `mcp sdk: OK`, and the comment above each names the gate's purpose.
- [x] AC5: `CLAUDE.md` names the twelfth gate where it lists the doctor gates. `the_one/agents.md` does the same wherever it enumerates them.
- [x] AC6: `.venv/bin/the-one doctor`, run with a scratch `THE_ONE_DATA_DIR`, prints `  mcp sdk: OK — …` and exits 0 on this host.
- [x] AC7: these all pass:
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_doctor.py -x --timeout 60`;
  - the whole unit suite (`make test-unit`, plain mode), with the same totals as at the end of `sdk-port` plus this leg's new tests;
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`.
- [x] AC8: the spec file still parses as Python (`python -c "import ast; ast.parse(open('packaging/windows/the-one.spec').read())"`), and both YAML files still parse.

## Verification Steps
- AC1, AC4, AC5: read the diffs.
- AC6: `THE_ONE_DATA_DIR=$(mktemp -d) .venv/bin/the-one doctor; echo rc=$?`.
- AC7, AC8: the commands above, with exit codes recorded in the flight log.

## Implementation Guidance
1. Add `_probe_mcp_sdk()` in `the_one/diagnostics.py`, following `_probe_time_zones()`. Use an import seam that tests can monkeypatch, as `_import_watchfiles` does. Wire it into `gates`, and update the docstring.
2. Update `tests/test_doctor.py` (the renamed list test, plus the failure-path test).
3. Update the packaging spec.
4. Update both workflow needle lists and the comments above them.
5. Update the docs, then run the AC6 to AC8 checks.

## Edge Cases
- **The doctor launches probe children.** Run it against a scratch data directory, never the operator's default data dir, and never on ports 8484 or 8485.
- **The surface module has import-time side effects** (it creates the `MCPServer` instance). The probe must only import it, never call its app factory or start a session manager.
- **`truststore` on Linux** builds its context from the system store; a missing CA bundle would fail the gate. Report a failure on this host as a finding; do not weaken the gate.

## Files Affected
- `the_one/diagnostics.py`
- `tests/test_doctor.py`
- `packaging/windows/the-one.spec`
- `ci/tasks/windows-installer-build.yml`
- `.github/workflows/windows-installer.yml`
- `CLAUDE.md`, `the_one/agents.md`
- The flight log

## Citation Audit
Checked at leg design against the flight branch:
- `the_one/diagnostics.py::run_doctor`: the docstring says "eleven" (~945-960), and the `gates` list ends with `time_zone_probe` (~1032-1044).
- `tests/test_doctor.py::test_gates_list_has_eleven_names_ending_with_time_zones` (~867).
- `ci/tasks/windows-installer-build.yml`: the needle list `@("usearch: OK", …, "time zones: OK")` (~117).
- `.github/workflows/windows-installer.yml`: the `grep -q "time zones: OK" doctor.out` checks (~129-135).
- `packaging/windows/the-one.spec`: `mcp_hidden = collect_submodules("mcp", filter=…mcp.cli…, on_error="warn")` (~75-79), and the "pinned 1.27.0" comment (~66).

**Risk tier: low.** The change is additive and follows the established `_probe_*` and needle-list pattern. It touches no security-sensitive or shared runtime surface, so there is no per-leg design review; the flight-end Reviewer covers it.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
