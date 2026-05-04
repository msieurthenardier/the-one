# Leg: 01-tests-green-and-lint-gate

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Bring the test suite to green on host and container, add lint enforcement to CI, and exclude tracked `workspace/` from ruff so it does not block the lint gate.

## Context

Maintenance report findings 2.1, 2.2, 4.1, 4.2 (see `maintenance/2026-05-04.md`).

- **2.1**: `tests/test_token_definitions.py::test_every_var_reference_is_defined` red since commit `18a0cd8` (M04 F6) — `--font-size-h3` referenced in `the_one/interfaces/web/static/css/components.css:284` but undefined in `tokens.css`. F1 mission-debrief.md flagged this for routine maintenance.
- **2.2**: `tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist` red on host runs (NEW finding from this maintenance pass). The test assumes container CWD `/app`; on host run from project root (under `~`), the user's `~`-defaulted allowlist accepts it, flipping the assertion. Real test bug, not env quirk.
- **4.1**: 30 ruff lint errors + 75 files would reformat. CI does NOT run `ruff check` or `ruff format --check`; only `pytest`. Silent drift accumulates.
- **4.2**: `workspace/test_agent.py` is tracked but trips ruff `F401`/`F821`/`W292`. `workspace/` is in `pytest.norecursedirs` but NOT in `[tool.ruff].exclude`.

## Inputs

- `the_one/interfaces/web/static/css/tokens.css` (existing; defines design tokens)
- `the_one/interfaces/web/static/css/components.css` (existing; references `--font-size-h3` at line 284)
- `tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist` (existing; environment-coupled)
- `pyproject.toml` `[tool.ruff]` section (existing)
- `ci/pipeline.yml` (existing; has only `pytest` invocations)
- 30 ruff lint errors across `the_one/` and `tests/`
- 75 files that would be reformatted by `ruff format`

## Outputs

- `tokens.css` defines `--font-size-h3` (or `components.css:284` switched to an existing token)
- `tests/test_execution_tools.py` reparametrized cwd test passes regardless of host CWD
- `pyproject.toml` `[tool.ruff].exclude` includes `workspace`
- `ci/pipeline.yml` runs `ruff check` + `ruff format --check` before `pytest`
- All 30 existing lint errors resolved (via `ruff check --fix` + manual fixes)
- 75 files reformatted (`ruff format`)
- `pytest -q --ignore=tests/browser` green on both container and host

## Acceptance Criteria

- [x] `pytest tests/test_token_definitions.py::test_every_var_reference_is_defined` passes
- [x] `pytest tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist` passes regardless of host CWD (the reparametrized test uses `tmp_path` + an explicit out-of-allowlist policy, so it should be CWD-independent by construction; triple-CWD verification at `/tmp`, `~`, and project root is defense-in-depth confirmation)
- [x] `ruff check the_one/ tests/` returns 0 errors (workspace excluded)
- [x] `ruff format --check the_one/ tests/` passes (no diff)
- [x] `ci/pipeline.yml` includes a `ruff check` step AND a `ruff format --check` step that run before the existing `pytest` step in the same task
- [x] Full test suite `pytest -q --ignore=tests/browser` returns 0 failures on host
- [x] Browser test suite `pytest -m browser tests/browser/` continues to pass (no regression from ruff format diff)

## Verification Steps

- `cd /home/cprch/projects/the-one && pytest tests/test_token_definitions.py -v` — passes
- `cd /tmp && pytest /home/cprch/projects/the-one/tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist` — passes from `/tmp`
- `cd /home/cprch/projects/the-one && pytest tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist` — passes from project root
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/` — returns 0
- `cd /home/cprch/projects/the-one && ruff format --check the_one/ tests/` — passes
- `cd /home/cprch/projects/the-one && grep -A 3 "ruff" ci/pipeline.yml` — shows lint step
- `cd /home/cprch/projects/the-one && pytest -q --ignore=tests/browser 2>&1 | tail -10` — 0 failures
- `cd /home/cprch/projects/the-one && make test-browser 2>&1 | tail -10` — 0 failures (regression check)

## Implementation Guidance

1. **Add `--font-size-h3` token to `tokens.css`**
   - Identify the existing font-size token scale (likely `--font-size-h1`, `--font-size-h2`, `--font-size-h4`, etc.). Define `--font-size-h3` as the appropriate intermediate value.
   - Verify `the_one/interfaces/web/static/css/components.css:284` reference resolves.
   - Run `pytest tests/test_token_definitions.py -v` to confirm.

2. **Reparametrize the cwd test**
   - Open `tests/test_execution_tools.py::TestShellTool::test_relative_cwd_refused_when_outside_allowlist`.
   - Replace the implicit "current CWD" assumption with an explicit out-of-allowlist tmpdir: use `tmp_path` fixture, `monkeypatch.chdir(tmp_path)`, AND ensure the agent's `FilesystemConfig.path_allowlist` does NOT include `tmp_path` (configure explicitly to e.g. `["/nonexistent"]` or `["/etc"]`).
   - Verify the test passes from any host CWD.

3. **Exclude `workspace/` from ruff**
   - Open `pyproject.toml`. Locate or create `[tool.ruff]` section.
   - Use `extend-exclude = ["workspace"]` (NOT `exclude = [...]`) so ruff's built-in defaults (`.git`, `.venv`, `node_modules`, etc.) are preserved.
   - Note: `ruff check the_one/ tests/` and `ruff format the_one/ tests/` (the explicit-path invocations used in steps 4 and 5) already scope away from `workspace/` by path, so this exclude is primarily for any future bare `ruff check` invocations and for keeping ruff's tooling output clean.

4. **Apply existing format diff and fix lint errors**
   - Run `ruff check --fix the_one/ tests/` for auto-fixable errors (handles `I001` import sorting, `F401` unused imports, and similar).
   - Run `ruff format the_one/ tests/` to apply the format diff (~75 files).
   - Manually fix any remaining ruff errors that `--fix` can't handle (`E501` line-too-long, `F841` unused vars, `N806`, plus any other non-auto-fixable codes surfaced after `--fix`).
   - For `db/schema.py:261`: the `REMOVED` set is FUNCTION-LOCAL inside `_migrate_v6_to_v7` (verified — inside an `async with` block in a method body, not module-level). Rename to lowercase `removed` per `N806` "variable in function should be lowercase". Update all references in the function body. Do NOT promote to module-level constant — that would misrepresent its scope.
   - Run `pytest -q --ignore=tests/browser` to verify no test broke from the format diff.

5. **Add lint to CI**
   - Open `ci/pipeline.yml`. Locate the test step (currently a single `sh -c "cp -r /src /work && cd /work && pip install --no-cache-dir '.[dev]' -q && python -m pytest tests/ ... && python -m pytest -m browser tests/browser/ ..."` invocation inside `docker run`).
   - **Insert two ruff invocations into the SAME `sh -c` chain**, between `pip install` and `python -m pytest tests/`:
     ```
     ... && pip install --no-cache-dir '.[dev]' -q && ruff check the_one/ tests/ && ruff format --check the_one/ tests/ && python -m pytest tests/ ...
     ```
   - `ruff` is already in `[project.optional-dependencies].dev` (`ruff>=0.6`), so `pip install '.[dev]'` makes it available. No new dependency needed.
   - Both ruff invocations must succeed (chained with `&&`) before pytest runs.
   - Verify via `fly -t the-one trigger-job -j the-one/deploy` (or a local pipeline run) that the test step runs ruff before pytest.

## Edge Cases

- **`ruff format` may touch the `workspace/` file already in tracked state**: ensure `workspace/` is excluded BEFORE running `ruff format`, otherwise the format pass touches files we want to leave alone.
- **`--font-size-h3` choice may not match the design intent**: pick a value that matches the visual hierarchy already established by `--font-size-h2` and `--font-size-h4`. If unclear, look at usage at `components.css:284` and pick the size that matches existing rendering.
- **Reparametrized cwd test may need `monkeypatch` of `Path.cwd` rather than `os.chdir`** depending on how the tool reads CWD. Verify by running with `pytest -v` and checking the assertion's failure message.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — add `--font-size-h3` definition
- `tests/test_execution_tools.py` — reparametrize cwd test
- `pyproject.toml` — add `extend-exclude = ["workspace"]` to `[tool.ruff]`
- `ci/pipeline.yml` — insert `ruff check` + `ruff format --check` into the existing `sh -c` chain (between `pip install` and `python -m pytest tests/`)
- ~75 files reformatted by `ruff format` (one-shot apply)
- `the_one/db/schema.py:261` — rename function-local `REMOVED` → `removed` per `N806`
- Up to ~25 files with manual `E501`/`F841` fixes (and any other non-auto-fixable codes after `--fix`)
- M05/M06 pre-flight artifacts already in working tree (will be included in the leg commit per post-completion checklist):
  - `missions/05-built-in-tool-system/mission.md` (modified)
  - `missions/05-built-in-tool-system/mission-debrief.md` (new)
  - `missions/06-maintenance/` (new — mission, flight, flight-log, 7 legs)
  - `maintenance/2026-05-04.md` (new — first maintenance report)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (host + container)
- [ ] Browser tests passing (regression check after format diff)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
