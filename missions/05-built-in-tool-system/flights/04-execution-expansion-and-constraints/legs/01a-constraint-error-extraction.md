# Leg: 01a-constraint-error-extraction

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Move `ConstraintError` from `the_one/tools/filesystem.py` to `the_one/tools/base.py` (next to the `Tool` ABC), with a backward-compatible re-export alias preserved in `filesystem.py` so existing imports continue to work.

## Context

- F4 Decision 8: `ConstraintError` belongs next to the `Tool` ABC because the two-clause `try/except` envelope IS the tool authorship contract. F3 placed it in `filesystem.py` only because filesystem was the first category to need it; F4 introduces an `execution.py` module that needs the same exception type.
- Single-concern, mechanical move. Architect flagged L1 bundling as a smell — splitting L1a (~30 LoC mechanical) from L1b (architectural plumbing) gives each its own review surface.
- Preconditions: `the_one/tools/base.py` ships the `Tool` ABC + `ToolRegistry` (F2). `the_one/tools/filesystem.py` ships `ConstraintError` at line 14 (F3 L2).
- Downstream legs (L2 onwards) import `ConstraintError` from `the_one/tools/base` for the new execution module.

## Inputs

- `the_one/tools/base.py` — exists, defines `Tool` ABC + `ToolRegistry`.
- `the_one/tools/filesystem.py` — defines `ConstraintError` at line 14, used internally and exported.
- `tests/test_filesystem_helpers.py:12` — DOES import `from the_one.tools.filesystem import ConstraintError, ...`. The re-export alias is **load-bearing** for this F3 test (not merely precautionary). This leg deliberately leaves the test on the re-export path — migrating test imports is out of scope for the mechanical-move leg.

## Outputs

- `the_one/tools/base.py` — adds `ConstraintError` class definition (verbatim docstring from filesystem.py).
- `the_one/tools/filesystem.py` — removes the class definition; adds `from the_one.tools.base import ConstraintError` near the top (re-export alias).
- F3 test suite passes unchanged.

## Acceptance Criteria

- [x] `class ConstraintError` is defined in `the_one/tools/base.py` (single source of truth).
- [x] `the_one/tools/filesystem.py` no longer defines `ConstraintError` — it imports it from `the_one.tools.base` (re-export preserved for backward compatibility).
- [x] Existing `from the_one.tools.filesystem import ConstraintError` style imports continue to resolve (re-export validated).
- [x] `rg -n 'class ConstraintError' the_one/` returns exactly **1** match — the one in `base.py`.
- [x] `rg -n 'from the_one.tools.base import.*ConstraintError' the_one/` returns at least 1 match (consolidated import line `from the_one.tools.base import ConstraintError, Tool` in `filesystem.py` satisfies this).
- [x] `ruff check the_one/tools/filesystem.py` returns clean — proves the re-export's `# noqa: F401` is correctly placed (project enables ruff's F-rules per `pyproject.toml`).
- [x] All filesystem tools (`ReadFileTool`, `WriteFileTool`, `ListDirTool`, `EditFileTool`, `DeleteFileTool`, `MoveFileTool`, `MkdirTool`, `GlobTool`, `GrepTool`) and helpers (`_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `_check_read_size`) still raise `ConstraintError` — their behavior is unchanged.
- [x] F3 test suite green: `make test-unit` passes (modulo pre-existing CSS-token red).
- [x] No new test file is required for this leg — the existing F3 suite proves the re-export works.

## Verification Steps

```bash
# Single source of truth
docker exec the-one rg -n 'class ConstraintError' the_one/
# expected: the_one/tools/base.py:N: class ConstraintError(Exception):

# Re-export alias intact
docker exec the-one rg -n 'from the_one.tools.base import.*ConstraintError' the_one/tools/filesystem.py
# expected: at least 1 match

# Backward-compat import smoke
docker exec the-one python -c "
from the_one.tools.filesystem import ConstraintError as A
from the_one.tools.base import ConstraintError as B
assert A is B, 'identity mismatch — re-export is broken'
print('OK')
"

# Lint clean (proves # noqa: F401 placement is correct)
docker exec the-one ruff check the_one/tools/filesystem.py

# F3 filesystem test suite (the actual file names)
docker exec the-one pytest tests/test_filesystem_helpers.py tests/test_filesystem_tools.py -q
```

## Implementation Guidance

1. **Add `ConstraintError` to `the_one/tools/base.py`**
   - Insert directly after the imports, before the `Tool` ABC class definition (so the docstring contract that mentions `try/except ConstraintError` reads top-to-bottom).
   - Copy the full docstring from `filesystem.py` verbatim. Update only the leading reference: change `"raised by filesystem tools and the \`_filesystem_check\` family"` to `"raised by tools and category-helper checks"` (more general now that execution + future categories share it).
   - The docstring's `[error] [constraint] {msg}` format note stays — it's still the wire format.

2. **Strip the definition from `the_one/tools/filesystem.py`**
   - Remove the `class ConstraintError(Exception): ...` block (currently at line 14).
   - Add `from the_one.tools.base import ConstraintError  # noqa: F401  (re-export for backward-compat)` near the top, alongside the other `from the_one.tools.base import Tool` line. The `noqa: F401` is necessary because ruff would flag it as an unused import — the re-export IS the use.
   - Keep the existing `from the_one.tools.base import Tool` import; consolidate to a single line: `from the_one.tools.base import ConstraintError, Tool`.

3. **Verify all internal raises still resolve**
   - Filesystem helpers raise `ConstraintError` directly by name — they now resolve via the re-export. No code change required at raise sites.

4. **Run the F3 filesystem test suite**
   - `docker exec the-one pytest tests/test_filesystem_helpers.py tests/test_filesystem_tools.py -q` should pass identically. `test_filesystem_helpers.py:12` imports `ConstraintError` from `the_one.tools.filesystem` — the re-export keeps this working.

5. **Lint check**
   - `docker exec the-one ruff check the_one/tools/filesystem.py` — ensures the `# noqa: F401` is placed correctly so ruff doesn't flag the re-export.

## Edge Cases

- **Test code importing from filesystem**: `tests/test_filesystem_helpers.py:12` imports `ConstraintError` from `the_one.tools.filesystem` today. The re-export keeps it working. No test migration in this leg — that's deferred to a future cleanup pass (or organically as test files are touched).

- **Pre-implementation working tree**: the orchestrator has uncommitted edits to `flight.md` (status `ready` → `in-flight`) and `flight-log.md` (Flight Director Notes), plus an untracked `legs/` directory holding leg artifacts. These are in-flight planning artifacts on the flight branch — implementation should proceed on top of them, not against `main`.
- **External callers (none today)**: the re-export documents the migration path. Future external code should prefer `from the_one.tools.base import ConstraintError`; the re-export buys time.
- **Linter (ruff)**: the re-export needs `# noqa: F401` to silence unused-import warning. Without `noqa`, CI/local lint would fail.
- **Identity check**: the verification step `assert A is B` confirms there's only ONE class — not two distinct exceptions sharing a name. This catches the failure mode where someone copy-pastes the class instead of importing it.

## Files Affected

- `the_one/tools/base.py` — add `ConstraintError` class definition.
- `the_one/tools/filesystem.py` — remove class definition; add `ConstraintError` to existing `from the_one.tools.base import` line with `# noqa: F401`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] F3 test suite passing
- [x] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit yet)
