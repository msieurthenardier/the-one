# Leg: settings-lazy-refactor

**Status**: completed
**Flight**: [Chat Polish](../flight.md)

## Objective

Refactor `the_one/config.py` to instantiate `Settings()` lazily via PEP 562 `__getattr__`, and retire the F5 L01.5 conftest singleton-mutation workaround that exists only to compensate for eager instantiation at module-import time.

## Context

- **Design Decision (flight.md)**: "Settings lazy construction: module-level lazy property, NOT a get_settings() function." Use PEP 562 `__getattr__` so `from the_one.config import settings` call sites continue to work unchanged. Symbol identity is preserved (multi-reference call sites stay valid). Test code is zero-touch — the test infrastructure keeps `from the_one.config import settings`.
- **Recon (flight-log.md row #1)**: `the_one/config.py:33` still eager-instantiates `settings = Settings()`. `tests/conftest.py:54-70` contains the L01.5 singleton-mutation workaround (the block beginning with `# F5 L01.5: the env-var override above is insufficient...` and ending with `settings.data_dir = Path(_test_data_dir)`).
- **Why this matters**: F5 L01.5 bisection found that `tests/conftest.py:14 from the_one.platform.sandbox import SandboxProfile` transitively imports `the_one.config`, so the `Settings()` singleton is constructed BEFORE `pytest_configure` can set `THE_ONE_DATA_DIR`. The current workaround mutates the cached singleton's `data_dir` after the env var is set. With lazy construction, no instance exists at conftest import time — the first attribute access happens later (after `pytest_configure` has run), so the env var is read correctly with no mutation needed.
- **Verification anchor (flight.md "Verification" §1)**: `grep -n "settings\.data_dir = Path" tests/conftest.py` must return empty.

## Inputs

Files that exist before this leg runs:
- `the_one/config.py` — defines `Settings(BaseSettings)` and eagerly creates `settings = Settings()` at module scope
- `tests/conftest.py` — contains the L01.5 singleton-mutation block (lines 57-70 in current code)
- All call sites importing `from the_one.config import settings` (verified at design time: `the_one/main.py:7`, `the_one/llm/openrouter_api.py:105`, `the_one/db/migration.py:8`, `the_one/db/connection.py:7`, `the_one/agent/factory.py:11`, `the_one/mcp/_pool.py:48`, `the_one/mcp/_tool_provider.py:44`, `the_one/mcp/oauth/provider_factory.py:50`, `the_one/interfaces/cli.py:13`, `the_one/interfaces/web/api.py:22`, `the_one/interfaces/web/app.py:37`, plus test-side: `tests/test_auto_load.py:119`, `tests/test_lifespan.py:73`, `tests/test_oauth_provider_factory.py:85`, `tests/test_openrouter_api.py:412,427`)
- Broad pytest baseline: exits code 0 in ~91s (1622 passed, 4 skipped, 370 deselected) per F5 L01.5 verified state

State that must be true:
- F5 has merged to main (commit `8d80545`); the L01.5 workaround is the current production state
- Container `the-one` running; `make rebuild` available

## Outputs

Files modified:
- `the_one/config.py` — exports `settings` via PEP 562 `__getattr__` with internal caching; eager `settings = Settings()` line removed
- `tests/conftest.py` — the L01.5 singleton-mutation block (lines roughly 57-70 — the comment block starting with `# F5 L01.5:` through `settings.data_dir = Path(_test_data_dir)`) is removed. The `setdefault("THE_ONE_DATA_DIR", ...)` line at the start of that section stays.

State after:
- `from the_one.config import settings` continues to return a `Settings` instance with consistent identity across imports
- The `Settings` constructor is NOT called until the first `settings.*` attribute access
- `tests/conftest.py` no longer mutates the singleton; `THE_ONE_DATA_DIR` env-var setting alone suffices to isolate the test SQLite DB
- Broad pytest exits code 0 (no change in pass/skip count from current baseline)

## Acceptance Criteria

- [ ] `the_one/config.py` defines `__getattr__(name: str)` that lazily instantiates and caches a single `Settings()` instance when `name == "settings"`, raising `AttributeError` for any other name (so unrelated `from the_one.config import X` still fails cleanly)
- [ ] The module-level `settings = Settings()` line is removed from `the_one/config.py`
- [ ] Subsequent accesses to `settings` (across modules and within a single module) return the SAME object (`is` comparison true) — caching works
- [ ] `from the_one.config import settings` succeeds from each existing import site without modification
- [ ] `tests/conftest.py` no longer contains the line `settings.data_dir = Path(_test_data_dir)` or the surrounding `# F5 L01.5:` workaround comment block — `grep -n "settings\.data_dir = Path" tests/conftest.py` returns empty
- [ ] `tests/conftest.py`'s `pytest_configure` retains `os.environ.setdefault("THE_ONE_DATA_DIR", tempfile.mkdtemp(...))` (the env-var seed line) and the `THE_ONE_TEST_MODE` setdefault — only the singleton-mutation block is removed
- [ ] The autouse session-scoped `_close_db_singleton_at_session_end` fixture stays exactly as-is (unrelated to lazy `Settings()` — it solves the aiosqlite `daemon=False` thread issue)
- [ ] Broad pytest (`docker exec the-one pytest -x --timeout 30`) exits code 0; pass/skip counts match the F5 baseline (1622 passed, 4 skipped, 370 deselected — minor variance acceptable but no NEW failures)
- [ ] Browser suite preserved at 315 passing / 35 skipped (F5 baseline; no new skips)

## Verification Steps

- **Lazy construction check**: open a Python REPL inside the container, run `import the_one.config as c; assert c._settings is None; _ = c.settings.host; assert c._settings is not None`. (PEP 562 `__getattr__`-only names are NOT in `dir(c)`, so the check must probe the cache slot directly. `hasattr(c, "settings")` would also work but triggers construction as a side effect.)
- **Symbol identity check**: run `from the_one.config import settings as s1; from the_one.config import settings as s2; assert s1 is s2` — caching guarantees single instance.
- **`Settings` class still importable directly**: run `from the_one.config import Settings; assert Settings.__name__ == "Settings"`. The `Settings` class is defined at module scope (NOT routed through `__getattr__`); confirm normal attribute lookup still finds it without invoking the lazy path.
- **Env-var honored from conftest**: run `docker exec the-one pytest tests/test_auto_load.py -x --timeout 30 -v` — the test uses `from the_one.config import settings` at line 119; settings.data_dir should reflect the env-var-derived path, not `~/.the-one`.
- **L01.5 workaround removed**: `grep -n "settings\.data_dir = Path" tests/conftest.py` returns empty. `grep -n "F5 L01.5" tests/conftest.py` returns empty (the comment block referencing the workaround is also gone).
- **Broad pytest exits 0**: `docker exec the-one pytest -x --timeout 30` exits with code 0; capture wall time (expect ~90s ±10s).
- **Browser suite preserved**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` exits with the same 315/35 split as F5 baseline.

## Implementation Guidance

1. **Edit `the_one/config.py`** to use PEP 562 lazy construction:

   ```python
   from __future__ import annotations

   from pathlib import Path

   from pydantic_settings import BaseSettings


   class Settings(BaseSettings):
       model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

       # Web
       host: str = "127.0.0.1"
       port: int = 8484

       # Dev mode (gates the mock provider type)
       dev_mode: bool = False

       # Paths
       data_dir: Path = Path.home() / ".the-one"

       @property
       def agents_dir(self) -> Path:
           return self.data_dir / "agents"

       @property
       def db_path(self) -> Path:
           return self.data_dir / "the-one.db"

       def ensure_dirs(self) -> None:
           self.data_dir.mkdir(parents=True, exist_ok=True)


   _settings: Settings | None = None


   def __getattr__(name: str) -> Settings:
       """PEP 562 lazy accessor: instantiate Settings() on first access to
       `settings`, then cache. Defers env-var read until after any
       conftest-level environment mutation has run.
       """
       if name == "settings":
           global _settings
           if _settings is None:
               _settings = Settings()
           return _settings
       raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
   ```

   - The `_settings: Settings | None = None` cache slot lives at module scope alongside `__getattr__`.
   - The `AttributeError` branch is mandatory — without it, any `from the_one.config import X` for `X != "settings"` would silently return `None` instead of raising, masking typos. The error message format matches Python's default missing-attribute message.

2. **Edit `tests/conftest.py`** to remove the L01.5 workaround:

   - Keep the docstring on `pytest_configure` (the `THE_ONE_TEST_MODE` rationale and the cross-reference to `tests/browser/conftest.py`).
   - Keep `os.environ.setdefault("THE_ONE_TEST_MODE", "1")`.
   - Keep the `_test_data_dir = os.environ.setdefault("THE_ONE_DATA_DIR", tempfile.mkdtemp(prefix="the-one-pytest-"))` block including its leading comment block (the M08 F5 L01 explanation of WAL contention — that rationale is still accurate and informative).
   - **Remove** the section starting with `# F5 L01.5: the env-var override above is insufficient...` through `settings.data_dir = Path(_test_data_dir)`. The function-scoped `from pathlib import Path` and `from the_one.config import settings` imports inside the removed block vanish with it; no separate cleanup needed (the top-of-file `from pathlib import Path` at line 8 stays — it's used by `_PROJECT_ROOT`).
   - Update the trailing comment in the kept section if it claims dependence on the next-block mutation. The L01 lead-in comment ("A session-persistent tmp dir...matches the live-container pattern.") stands.

3. **Run broad pytest twice** to validate:

   ```bash
   docker exec the-one pytest -x --timeout 30
   ```

   First run validates the lazy refactor doesn't break anything. Note wall time. Re-run to confirm no flakiness — settings cache should persist across the test session, not across pytest invocations.

4. **Run browser suite** to confirm no regression on the live-container path:

   ```bash
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

   Browser tests are uvicorn-subprocess-based — they should not be affected by the lazy refactor (uvicorn's process inherits the env vars at spawn time). Verifying anyway because the lazy path touches every importer of `settings`.

5. **Update flight log**:
   - Append a "Leg Progress > settings-lazy-refactor" entry summarizing what was done and any wall-time data.
   - If no anomalies surface, no Decisions/Deviations/Anomalies entries needed.

6. **Do NOT commit yet** — the agentic-workflow defers all commits until after L05 (review-and-commit batch over all autonomous legs).

## Edge Cases

- **Pydantic v2 / pydantic-settings behavior**: `BaseSettings()` reads `os.environ` AND the `.env` file at instantiation time. Lazy construction defers this read until first attribute access. The conftest's `os.environ.setdefault("THE_ONE_DATA_DIR", ...)` runs in `pytest_configure`, which fires before any test module's body runs (and before any `settings.*` attribute access). This ordering is what F5 L01.5 verified empirically — re-confirm during this leg by checking that broad pytest still uses the tmp data dir (not `/root/.the-one`).
- **Module-level imports that immediately use `settings`**: `the_one/interfaces/web/app.py:131` calls `build_default_allowlist(settings.host, settings.port)` at module-import time. Under the lazy refactor, this access constructs `Settings()` on first import of `web.app`. This is SAFE for the env-var-isolation goal because: (a) pytest's `pytest_configure` runs BEFORE any test module is collected, so `THE_ONE_DATA_DIR` is set before `web.app` is imported by any test; (b) container `make rebuild` startup imports `web.app` via uvicorn, by which point the live environment is already established. Verify during implementation by checking that `tests/test_ws_responsiveness.py`, `tests/test_agent_context.py`, `tests/test_session_lifecycle.py`, and `tests/test_mcp_pool.py` (the test modules known to import `web.app` at collection time) still observe the env-var-derived `data_dir`. NO other module-import-time `settings.*` access exists in the codebase — verify with `grep -B2 "settings\." the_one/**/*.py | grep -v "^def\|^async def\|^    "`-style scan during implementation.
- **REPL / interactive use**: `from the_one.config import settings` in an interactive Python session creates the instance on first attribute access, exactly as in production. No special handling needed.
- **`AttributeError` semantics**: PEP 562 `__getattr__` is called only for attributes not found via normal lookup. The `Settings` class symbol stays accessible directly because it's still defined at module scope.
- **`tests/conftest.py` import cleanup**: the `from pathlib import Path` and `from the_one.config import settings` lines at the bottom of the L01.5 block (lines 68-69 in the current file) are FUNCTION-SCOPED inside `pytest_configure` — they vanish together with the block, no separate cleanup needed. The top-of-file `from pathlib import Path` (line 8) is used by `_PROJECT_ROOT` (line 17) and several MCP fixtures; it STAYS.

## Files Affected

- `the_one/config.py` — replace eager `settings = Settings()` with `__getattr__` + module-level cache slot
- `tests/conftest.py` — remove the L01.5 singleton-mutation block (lines ~57-70 in current file) and clean up the now-orphaned `Path` / `settings` imports inside `pytest_configure` if any

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0; browser suite 315/35 preserved)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`; the final-status flip happens at the post-L05 commit batch
- [ ] Do NOT check off this leg in flight.md yet — that happens during the commit batch
- [ ] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

8 citations verified against current code at leg design time:
- `the_one/config.py:33 — "settings = Settings()"` — OK
- `tests/conftest.py:14 — "from the_one.platform.sandbox import SandboxProfile"` — OK
- `tests/conftest.py:54-70` (L01.5 workaround block) — OK; precise line range is 57-70 in current file (lead env-var seed at lines 53-56 STAYS; the L01.5 block to remove starts at the comment line 57 and ends at line 70's `settings.data_dir = Path(...)`)
- `the_one/main.py:7` — OK
- `the_one/db/connection.py:7` — OK
- `the_one/interfaces/web/app.py:37` — OK
- `tests/test_auto_load.py:119` — OK
- `the_one/mcp/_pool.py:48` — OK (recon row #1's reference to L01.5 workaround at `_pool.py:210` for `_entry_worker` is historical context, not a cite needing audit)
