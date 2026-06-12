# Leg: os-conventional-data-dir

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

Resolve the app's data/secrets directory to an OS-conventional per-user location via
`platformdirs`, and migrate an existing `~/.the-one` into place by a one-shot rename —
guarded so it can never fire under a test/explicit override.

## Context

- **Flight DDs** — "OS-conventional paths via `platformdirs`" and "`~/.the-one`
  migration = move (rename)", with the **critical guard**: migration fires only when
  `data_dir` is the default platformdirs-resolved path, never under an explicit
  `THE_ONE_DATA_DIR`/test override.
- **Design-review HIGH/MED (resolved into this leg)** — every test sets
  `THE_ONE_DATA_DIR` to a fresh `mkdtemp` (`tests/conftest.py:53-56`); an unconditional
  move would rename the developer's real `~/.the-one` into a throwaway temp dir.
  Pydantic v2 `model_fields_set` is the clean "was `data_dir` explicitly supplied?"
  signal (env- and init-populated fields appear in it).
- Independent of Leg 1; does not touch `SandboxError`.
- Current state: `the_one/config.py:22` hardcodes `data_dir: Path = Path.home() / ".the-one"`;
  `agents_dir`/`db_path` nest under it; `ensure_dirs()` (line 32) just `mkdir`s it. Its
  real call sites are **`the_one/agent/factory.py:237`** (`AgentFactory.create()`) and
  **`the_one/db/connection.py:16`** (`get_connection()`) — so a startup DB op can also
  trigger the migration attempt. Migration must therefore be **fast and non-fatal**
  (never raise out of `ensure_dirs()`). All other read-sites (`encryption.py`,
  `tools/execution.py` box-scratch, connectors) funnel through `settings.data_dir`, so
  they need no change.
- **`model_fields_set` works with the literal default too** (design-review confirmed
  empirically: env/init-sourced ⇒ `{'data_dir'}` in the set; default fallback ⇒ absent).
  A `default_factory` is **not** required to make the guard meaningful — it's kept only
  as a style choice to avoid evaluating `platformdirs` at class-definition time.
- **`tempdirs.user_config_dir` convention split (flagged, out of scope)** —
  `the_one/platform/tempdirs.py` has a separate, unused-in-production `user_config_dir()`
  that hardcodes POSIX `~/.{app}`; its test (`test_platform_tempdirs.py:33`) asserts
  `~/.the-one`. This leg does **not** change `tempdirs` behavior (no production
  consumer), but leaving it creates a latent two-convention split. Resolution: add a
  clarifying comment that `config.py` (via `platformdirs`) is the canonical resolver;
  defer any `tempdirs` consolidation to a later docs/maintenance pass. No test breaks
  (the tempdirs test still exercises tempdirs' own unchanged behavior).

## Inputs

- `the_one/config.py` with the hardcoded `data_dir` default and `ensure_dirs()`.
- `tests/conftest.py:53-56` setting `THE_ONE_DATA_DIR` to a temp dir for every run.
- `pyproject.toml` without a `platformdirs` dependency.

## Outputs

- `platformdirs` added to runtime dependencies in `pyproject.toml`.
- `data_dir` default resolved per-OS via `platformdirs.user_data_dir("the-one", appauthor=False)`
  (Linux `~/.local/share/the-one`, macOS `~/Library/Application Support/the-one`,
  Windows `%APPDATA%\the-one`), implemented as a `default_factory` so `model_fields_set`
  reflects whether the value was explicitly supplied.
- A guarded one-shot migration that renames a legacy `~/.the-one` into the resolved
  default location, run before the directory is created.
- `tools/filesystem.py:48` doc example updated off the hardcoded `~/.the-one/secrets`.
- Tests covering resolution, migration, idempotency, and the never-migrate-on-override
  guard.

## Acceptance Criteria

- [x] `platformdirs` is a declared runtime dependency in `pyproject.toml`.
- [x] With no `THE_ONE_DATA_DIR` set, `settings.data_dir` resolves to
      `platformdirs.user_data_dir("the-one", appauthor=False)` for the host OS.
- [x] An explicit `THE_ONE_DATA_DIR` (or an explicit `Settings(data_dir=...)`) still
      wins and is reflected in `Settings().model_fields_set`.
- [x] When `data_dir` is the default-resolved path, the legacy `~/.the-one` exists, and
      the target does **not** exist, `ensure_dirs()` renames the legacy directory into
      the target (one-shot **move**), preserving contents (DB + secrets).
- [x] Migration **never** fires when `data_dir` was explicitly supplied (env or init) —
      asserted by a test that sets an explicit override with a real legacy dir present
      and confirms no move.
- [x] Migration is idempotent under repeated `ensure_dirs()` calls (no error, no second
      move once the target exists).
- [x] Migration runs **before** the `mkdir` that would otherwise create an empty target
      and block the rename.
- [x] `tools/filesystem.py:48` no longer hardcodes `~/.the-one/...` as the example path.
- [x] Full suite passes; `ruff check`/`ruff format` clean.

## Verification Steps

- `docker exec the-one python -c "import platformdirs, the_one.config as c; print(c.Settings().data_dir)"` with `THE_ONE_DATA_DIR` unset → prints the platformdirs path.
- New unit tests (run via `docker exec the-one pytest -x --timeout 30 tests/test_config_data_dir.py` or wherever placed):
  - default resolution (monkeypatch the platformdirs resolver to a temp dir AND
    `monkeypatch.delenv("THE_ONE_DATA_DIR", raising=False)`, then assert
    `"data_dir" not in Settings().model_fields_set` and the path matches the patched
    resolver);
  - migration moves a populated legacy dir to the (patched) default target and the
    contents arrive;
  - explicit override (`Settings(data_dir=tmp)` or env) with a populated legacy present
    → legacy untouched, no move;
  - idempotency: two `ensure_dirs()` calls, single move, no error.
- `docker exec the-one pytest -x --timeout 30` full suite at leg-end; `ruff` clean.

## Implementation Guidance

1. **Add the dependency** — add `platformdirs` to `pyproject.toml` `[project] dependencies`.

2. **Resolve the default** — in `the_one/config.py`, set the default to
   `Field(default_factory=_default_data_dir)` where `_default_data_dir()` returns
   `Path(platformdirs.user_data_dir("the-one", appauthor=False))`. (The factory form is
   a style choice to avoid evaluating `platformdirs` at class-definition time; the
   `model_fields_set` guard works identically with a literal default — do not rely on
   the factory for the guard's correctness.)

3. **Add a guarded migration** — add `migrate_legacy_data_dir()` (or inline in
   `ensure_dirs()` before the `mkdir`) that performs the rename **only when all** hold:
   - `"data_dir" not in self.model_fields_set` (i.e. default-resolved, not overridden);
   - the legacy `Path.home() / ".the-one"` exists and is a directory;
   - `self.data_dir` does **not** already exist;
   - and the legacy path != the resolved target (guards the pathological case where the
     platform default *is* `~/.the-one`).
   Then `legacy.rename(self.data_dir)` (create the parent first if needed), and log an
   INFO line naming both paths. After it, proceed to `mkdir(parents=True, exist_ok=True)`.
   **Error path**: on `EXDEV` (cross-device) fall back to copy-then-remove; on any other
   `OSError` log a WARNING (naming the exception and both paths) and **continue** — a
   migration failure must never raise out of `ensure_dirs()` (it runs at DB-connection
   and agent-creation time).

4. **Order in `ensure_dirs()`** — migration attempt FIRST, then `mkdir`. (mkdir-first
   would create an empty target and permanently block the rename.)

5. **Update the doc example** — `tools/filesystem.py:48`: change the `~/.the-one/secrets`
   example to a neutral/`<data_dir>/secrets`-style reference (no behavior change).

6. **Tests** — add a focused test module. Because `conftest.py` pins `THE_ONE_DATA_DIR`
   for every run, the default-branch and migration tests must `monkeypatch.delenv` it
   and monkeypatch the platformdirs resolver (e.g. patch `_default_data_dir` or
   `platformdirs.user_data_dir`) to a temp dir, then **construct `Settings()` fresh**.
   **PEP 562 cache hazard (critical)**: the module caches its instance in
   `the_one.config._settings`, already warmed to the conftest temp dir;
   `monkeypatch.delenv` does NOT invalidate it. So each default-path/migration test must
   (a) `monkeypatch.setattr("the_one.config._settings", None)` (or a fixture that does),
   and (b) call `ensure_dirs()` on the **freshly-constructed `Settings()` instance**,
   never on the module-level `settings` object. Cover the four cases in Verification Steps.

7. **Add the tempdirs clarifying comment** — in `the_one/platform/tempdirs.py`, add a
   short comment near `user_config_dir` noting that `the_one/config.py` (via
   `platformdirs`) is the canonical app data-dir resolver and this helper is a separate
   legacy path; do not change its behavior. (No code/behavior change — comment only.)

8. **Run `ruff` + full suite**.

## Edge Cases

- **Explicit override with legacy present** — must NOT migrate (the dangerous case the
  guard exists for). Dedicated test.
- **Repeated `ensure_dirs()`** (per `AgentFactory.create()`) — idempotent; once the
  target exists the rename is skipped.
- **Legacy is a symlink / not a dir** — only migrate a real directory; skip otherwise.
- **Parent of target missing** — create parents before rename (or rely on the platform
  data root existing; create defensively).
- **Cross-filesystem rename** — `Path.rename` can fail across mounts (`OSError`); the
  legacy `~/.the-one` and the platform data dir are normally on the same home
  filesystem, but catch and fall back to copy-then-remove if a cross-device error
  occurs (log it). (Acceptable-variation territory; keep simple if same-FS holds.)

## Files Affected

- `pyproject.toml` — add `platformdirs` dependency.
- `the_one/config.py` — `default_factory` resolution + guarded migration + ordering.
- `the_one/tools/filesystem.py` — doc example (line 48).
- `the_one/platform/tempdirs.py` — clarifying comment only (no behavior change).
- `tests/test_config_data_dir.py` (or similar) — **new**: resolution, migration,
  override-guard, idempotency tests (with `_settings` cache reset).

---
