# Leg: code-fixes

**Status**: completed
**Flight**: [Validation & Hardening](../flight.md)

## Objective

Fix all 36 ruff violations (24 E501, 3 F401, 3 F541, 4 I001, 2 F841), replace the hardcoded tool count assertion in test_builtins.py, and fix the broken rollback job in pipeline.yml to use the containerized execution pattern.

## Context

- Flight 03 debrief identified 36 ruff violations and a broken rollback job as action items
- The rollback job at pipeline.yml:197-216 uses `${WORKSPACE_PATH}/ci/deploy.sh rollback` as a bare command inside a docker:cli container — that host path doesn't exist in the container
- The auto-rollback task at pipeline.yml:185-195 already uses the correct containerized pattern with `docker run ... -v "${WORKSPACE_PATH}:/src:ro" ... sh /src/ci/deploy.sh rollback`
- The test_builtins.py assertion `assert len(tools) == 14` is brittle — the test's purpose is to verify builtins load, not enforce an exact count

## Inputs

- All source files listed in Files Affected below
- `ruff check the_one/ tests/` output showing 36 violations
- Current pipeline.yml with both working (auto-rollback) and broken (rollback) patterns

## Outputs

- All 36 ruff violations resolved
- `tests/test_builtins.py` assertion changed to `assert len(tools) > 0`
- `ci/pipeline.yml` rollback job fixed to use containerized execution

## Acceptance Criteria

- [x] `ruff check the_one/ tests/` returns zero violations
- [x] `python3 -m pytest tests/ --tb=short -q` passes (all unit tests)
- [x] `fly validate-pipeline -c ci/pipeline.yml` succeeds
- [x] Rollback job in pipeline.yml uses `docker run ... -v "${WORKSPACE_PATH}:/src:ro" ... sh /src/ci/deploy.sh rollback` pattern matching auto-rollback

## Verification Steps

- Run `ruff check the_one/ tests/` — expect clean output
- Run `python3 -m pytest tests/ --tb=short -q` — expect all tests pass
- Run `fly validate-pipeline -c ci/pipeline.yml` — expect valid
- Visually confirm rollback job at ~line 197 uses containerized docker run pattern

## Implementation Guidance

1. **Auto-fix 10 violations with ruff**
   - Run `ruff check --fix the_one/ tests/` to fix: 3 F401 (unused imports), 3 F541 (f-string without placeholders), 4 I001 (unsorted imports) = 10 auto-fixable
   - Then run `ruff check --unsafe-fixes --fix the_one/ tests/` for the 2 F841 violations

2. **Fix 24 E501 violations manually** — break long lines in:
   - `the_one/interfaces/cli.py:61` — break f-string across lines
   - `the_one/interfaces/web/app.py:73,134,216,266,274,313` — break function signatures and expressions (6 violations)
   - `the_one/llm/ollama_provider.py:81` — break return statement
   - `the_one/tools/filesystem.py:22` — break description string
   - `the_one/tools/git.py:21,29,44` — break description strings (3 violations)
   - `the_one/tools/mission_control.py:22,35,46,57` — break description strings (4 violations)
   - `the_one/tools/python_exec.py:16` — break description string
   - `the_one/tools/self_deploy.py:79` — break return expression
   - `the_one/tools/shell.py:11` — break description string
   - `the_one/tools/test_runner.py:22,26,43,64` — break description strings and f-strings (4 violations)
   - `the_one/tools/web.py:58` — break dict literal

3. **Fix test_builtins.py**
   - Change `assert len(tools) == 14` to `assert len(tools) > 0` at line 15

4. **Fix rollback job in pipeline.yml**
   - Replace lines 197-216 rollback job's run section to use the containerized pattern:
     ```
     docker run --rm \
       -v "${WORKSPACE_PATH}:/src:ro" \
       -v /var/run/docker.sock:/var/run/docker.sock \
       -e WORKSPACE_PATH="${WORKSPACE_PATH}" \
       -e CONCOURSE_PASS="${CONCOURSE_PASS}" \
       docker:cli \
       sh /src/ci/deploy.sh rollback
     echo "Rolled back to previous image"
     ```

## Edge Cases

- **E501 in f-strings**: Some long lines are inside f-strings with complex expressions — use parenthesized continuation or break the expression into a variable
- **F841 unused variable `syntax_cmd`**: The variable is assigned but the actual subprocess uses an inline string — just remove the assignment
- **F841 unused variable `message`**: `kwargs.get("message", "self-deploy")` return value is unused — replace with just dropping the line or using `_` if the kwargs access has side effects (it doesn't for dict.get)

## Files Affected

- `the_one/interfaces/cli.py` — Fix 1 E501
- `the_one/interfaces/web/app.py` — Fix 6 E501 (lines 73, 134, 216, 266, 274, 313)
- `the_one/llm/anthropic_provider.py` — Remove unused `json` import (F401)
- `the_one/llm/base.py` — Remove unused `json` import (F401)
- `the_one/llm/ollama_provider.py` — Fix 1 E501
- `the_one/main.py` — Fix 3 F541
- `the_one/tools/filesystem.py` — Fix 1 E501
- `the_one/tools/git.py` — Fix I001, 3 E501
- `the_one/tools/mission_control.py` — Fix F401 (unused asyncio), 4 E501
- `the_one/tools/python_exec.py` — Fix 1 E501
- `the_one/tools/restart.py` — Fix I001
- `the_one/tools/rollback.py` — Fix I001
- `the_one/tools/self_deploy.py` — Fix I001, F841, 1 E501
- `the_one/tools/shell.py` — Fix 1 E501
- `the_one/tools/test_runner.py` — Fix I001, F841, 4 E501
- `the_one/tools/web.py` — Fix 1 E501
- `tests/test_builtins.py` — Change hardcoded tool count assertion
- `ci/pipeline.yml` — Fix rollback job containerized execution

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
