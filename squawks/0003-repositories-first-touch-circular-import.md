# Squawk 0003: `the_one.db.repositories` fails as a first-touch import in a fresh process

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-25
**Completed**: 2026-08-29

## Report

Importing `the_one.db.repositories` (or `the_one.interfaces.web.api`, which pulls
it in) as the very first `the_one`-touching import in a fresh Python process
raises a circular-import error: `repositories.py`'s
`from the_one.agent.config import AgentConfig` transitively re-enters
`the_one.mcp._pool`'s `from the_one.db.repositories import MCPSourceRepository`
before that class has finished defining.

Does **not** manifest in `make test-unit` or any real entrypoint (`the-one serve`,
CLI, tests) because other modules are imported first and warm the cycle. Surfaced
only by a bare `.venv/bin/python -c "import the_one.interfaces.web.api"`.

Discovered during Mission 21 Flight 1 (Leg 1 design review) as flight-log
Anomaly A10; deferred to a squawk at flight end per the out-of-scope-defect rule.

## Evidence

- `.venv/bin/python -c "import the_one.interfaces.web.api"` on a clean checkout →
  `ImportError` (partially-initialized module) from the
  `agent.config` → `mcp._pool` → `db.repositories` re-entry.
- `the_one/db/repositories.py`: top-level `from the_one.agent.config import AgentConfig`.
- `the_one/mcp/_pool.py`: `from the_one.db.repositories import MCPSourceRepository`.

## Corrective Action

**Cycle map** (traced by reading each module's imports, first-touch on
`the_one.db.repositories`):

1. `the_one/db/repositories.py:12` — module-top `from the_one.agent.config
   import AgentConfig`. Importing the `agent.config` submodule first runs
   the `the_one.agent` package's `__init__.py`.
2. `the_one/agent/__init__.py:2` — `from the_one.agent.core import Agent`.
3. `the_one/agent/core.py:21` — `from the_one.mcp.errors import
   MCPAuthRequired`. Importing the `mcp.errors` submodule first runs the
   `the_one.mcp` package's `__init__.py`.
4. `the_one/mcp/__init__.py:40` — `from the_one.mcp._pool import (...)`.
5. `the_one/mcp/_pool.py:51` — `from the_one.db.repositories import
   MCPSourceRepository` — re-enters `the_one.db.repositories`, which is
   still mid-execution at line 12 (class bodies below it, including
   `MCPSourceRepository`, haven't run yet) → `ImportError: cannot import
   name 'MCPSourceRepository' from partially initialized module`.

Chain: `db.repositories` → `agent.config` → `agent` (pkg `__init__`) →
`agent.core` → `mcp.errors` → `mcp` (pkg `__init__`) → `mcp._pool` →
`db.repositories` (re-entry, partial).

**Fix** (smallest edge cut, one file — `the_one/db/repositories.py`):
`AgentConfig` is used in this module only in type annotations (already
deferred by the existing `from __future__ import annotations`) and in one
runtime construction, `_row_to_config`'s `return AgentConfig(...)`. Moved
the module-top import under `if TYPE_CHECKING:` and added a local `from
the_one.agent.config import AgentConfig` inside `_row_to_config`, with a
comment at both sites naming the cycle. This breaks the
`repositories` → `agent.config` edge at import time (it still exists at
call time, once, well after both modules have finished defining), which is
sufficient — `mcp._pool` → `repositories` was left untouched, per the
squawk's own candidate-fix preference to avoid restructuring `_pool.py`.

## Verification

- Bare first-touch import now succeeds:
  `.venv/bin/python -c "import the_one.interfaces.web.api; import
  the_one.db.repositories; print('ok')"` → `ok`.
- Each of the following also imports cleanly as the sole/first
  `the_one`-touching import in its own fresh process:
  `the_one.db.repositories`, `the_one.mcp._pool`, `the_one.agent.config`,
  `the_one.interfaces.web.app` — all print `OK`.
- Added `test_first_touch_import_succeeds` (parametrized over the four
  modules above) to `tests/test_imports.py`, which already held the
  project's subprocess-isolated import-graph regression tests (used that
  file instead of a new `tests/test_import_graph.py`, to keep one home for
  this test category). Confirmed red→green: stashed just
  `the_one/db/repositories.py` (`git stash push -- the_one/db/repositories.py`),
  ran `tests/test_imports.py` — `test_first_touch_import_succeeds[the_one.db.repositories]`
  failed with the exact `ImportError` above (`assert 1 == 0`, 1 failed / 2
  passed — the two pre-existing tests in the file were unaffected); popped
  the stash to restore the fix, reran — all green.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_imports.py
  tests/test_db_repositories.py tests/test_mcp_pool.py -x --timeout 120` →
  **279 passed, 2 deselected** in ~76s.
- `.venv/bin/ruff check .` → All checks passed. `.venv/bin/ruff format
  --check .` → 455 files already formatted.
- Scope check: one source file touched (`the_one/db/repositories.py`),
  `mcp/_pool.py` untouched, no targeted test failures — within squawk
  scope.

## Sign-Off

*(written at completion)*

## Disposition

**Deferred**: cosmetic/latent — no production path or test hits it, and Mission 21
Flight 1's own additions (`the_one.config`, `the_one.encryption`, both leaf
modules) neither touch nor worsen it. Revisit when a genuinely first-touch import
of `db.repositories` becomes necessary (e.g. a new standalone script or a
packaging entrypoint that imports it before the web/CLI modules), or during a
maintenance cycle addressing import-graph hygiene. Candidate fix: make the
`AgentConfig` import in `repositories.py` function-local, or break the
`mcp._pool` → `db.repositories` edge.

Taken up 2026-08-29 (maintenance cycle trigger).
