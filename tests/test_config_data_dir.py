"""Tests for the OS-conventional data-dir resolution and legacy migration.

PEP 562 cache hazard — the module-level ``_settings`` object is already
warm (pinned to the conftest temp dir) when these tests run.  Every test
that exercises the default-resolution branch or the migration must:

  1. ``monkeypatch.delenv("THE_ONE_DATA_DIR", raising=False)`` — remove the
     conftest-injected override so a freshly-constructed Settings() falls back
     to the factory default.
  2. ``monkeypatch.setattr("the_one.config._settings", None)`` — invalidate
     the cached singleton (though we never use ``settings``; belt-and-suspenders).
  3. Monkeypatch ``platformdirs.user_data_dir`` (via ``the_one.config``) to return
     a temp path, so the test is hermetic and never touches the real user data directory.
  4. Construct ``Settings()`` FRESH and call ``ensure_dirs()`` on THAT instance.
     Never call ``ensure_dirs()`` on the module-level ``settings`` object.

Patching strategy: we patch ``platformdirs.user_data_dir`` as imported in the
config module (``the_one.config.platformdirs.user_data_dir``).  The
``_default_data_dir`` factory calls ``platformdirs.user_data_dir(...)`` via the
module-level ``platformdirs`` reference, so patching ``platformdirs.user_data_dir``
directly reaches the factory call site regardless of the pydantic Field object's
captured function reference.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fresh_settings(**kwargs):
    """Import and construct a fresh Settings() with optional init kwargs."""
    from the_one.config import Settings

    return Settings(**kwargs)


def _patch_platformdirs(monkeypatch, target_path: Path) -> None:
    """Patch platformdirs.user_data_dir inside the config module to return target_path."""
    monkeypatch.setattr(
        "the_one.config.platformdirs.user_data_dir",
        lambda *args, **kwargs: str(target_path),
    )


def _patch_path_home(monkeypatch, fake_home: Path) -> None:
    """Patch Path.home() inside the config module to return fake_home."""
    monkeypatch.setattr("the_one.config.Path", _make_patched_path_class(fake_home))


def _make_patched_path_class(fake_home: Path):
    """Return a drop-in for ``Path`` that overrides ``Path.home()``."""

    class _PathProxy:
        """Thin proxy around Path — overrides .home() only."""

        @staticmethod
        def home() -> Path:
            return fake_home

        def __new__(cls, *args, **kwargs):  # type: ignore[misc]
            return Path(*args, **kwargs)

    # Copy class-level attributes so isinstance/type checks in Path code still work
    # (we only need __new__ and home() for our usage in the config module).
    return _PathProxy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _cache_reset(monkeypatch):
    """Reset the PEP 562 _settings cache so fresh Settings() is constructed."""
    monkeypatch.setattr("the_one.config._settings", None)


@pytest.fixture()
def unset_data_dir_env(monkeypatch, _cache_reset):
    """Remove THE_ONE_DATA_DIR so Settings() falls through to the factory."""
    monkeypatch.delenv("THE_ONE_DATA_DIR", raising=False)


@pytest.fixture()
def patched_default(tmp_path, unset_data_dir_env, monkeypatch):
    """Patch platformdirs.user_data_dir to return a sub-path of tmp_path.

    Returns the patched target path (does NOT create it — tests do so as needed).
    """
    target = tmp_path / "platform-data-dir"
    _patch_platformdirs(monkeypatch, target)
    return target


# ---------------------------------------------------------------------------
# Test 1 — Default resolution
# ---------------------------------------------------------------------------


def test_default_resolution_matches_patched_factory(patched_default):
    """Settings() with no override resolves data_dir to the factory's value,
    and 'data_dir' is NOT in model_fields_set (it was factory-supplied).
    """
    target = patched_default
    s = _make_fresh_settings()
    assert s.data_dir == target
    assert "data_dir" not in s.model_fields_set


# ---------------------------------------------------------------------------
# Test 2 — Migration moves populated legacy dir into the target
# ---------------------------------------------------------------------------


def test_migration_moves_legacy_dir(tmp_path, patched_default, monkeypatch):
    """When data_dir is default-resolved, legacy exists, and target does not,
    ensure_dirs() renames legacy into target and the contents arrive.
    """
    target = patched_default  # does NOT exist yet

    home = tmp_path / "home"
    home.mkdir()
    legacy = home / ".the-one"
    legacy.mkdir()
    (legacy / "the-one.db").write_text("sentinel-db-content")

    _patch_path_home(monkeypatch, home)

    s = _make_fresh_settings()
    assert "data_dir" not in s.model_fields_set  # sanity

    s.ensure_dirs()

    # Target now exists and contains the sentinel file.
    assert target.is_dir()
    assert (target / "the-one.db").read_text() == "sentinel-db-content"

    # Legacy is gone.
    assert not legacy.exists()


# ---------------------------------------------------------------------------
# Test 3a — Explicit init override: legacy is untouched, no migration
# ---------------------------------------------------------------------------


def test_explicit_override_does_not_migrate(tmp_path, monkeypatch, _cache_reset):
    """When data_dir is explicitly supplied via init kwarg, migration never fires,
    even when a real legacy directory is present.
    """
    monkeypatch.delenv("THE_ONE_DATA_DIR", raising=False)

    explicit_target = tmp_path / "explicit-data-dir"
    explicit_target.mkdir()

    home = tmp_path / "home"
    home.mkdir()
    legacy = home / ".the-one"
    legacy.mkdir()
    (legacy / "the-one.db").write_text("legacy-content")

    _patch_path_home(monkeypatch, home)

    # Explicit init override: data_dir in model_fields_set → guard blocks migration.
    s = _make_fresh_settings(data_dir=explicit_target)
    assert "data_dir" in s.model_fields_set

    s.ensure_dirs()

    # Legacy untouched.
    assert legacy.is_dir()
    assert (legacy / "the-one.db").read_text() == "legacy-content"
    # Explicit target intact.
    assert explicit_target.is_dir()


# ---------------------------------------------------------------------------
# Test 3b — Explicit env override: legacy is untouched, no migration
# ---------------------------------------------------------------------------


def test_explicit_env_override_does_not_migrate(tmp_path, monkeypatch, _cache_reset):
    """When THE_ONE_DATA_DIR env var is set, migration never fires."""
    explicit_target = tmp_path / "env-data-dir"
    explicit_target.mkdir()

    monkeypatch.setenv("THE_ONE_DATA_DIR", str(explicit_target))

    home = tmp_path / "home"
    home.mkdir()
    legacy = home / ".the-one"
    legacy.mkdir()
    (legacy / "the-one.db").write_text("legacy-content")

    _patch_path_home(monkeypatch, home)

    s = _make_fresh_settings()
    assert "data_dir" in s.model_fields_set

    s.ensure_dirs()

    assert legacy.is_dir()
    assert (legacy / "the-one.db").read_text() == "legacy-content"


# ---------------------------------------------------------------------------
# Test 4 — Idempotency: two ensure_dirs() calls, single move, no error
# ---------------------------------------------------------------------------


def test_ensure_dirs_idempotent(tmp_path, patched_default, monkeypatch):
    """Two consecutive ensure_dirs() calls produce no error and no second move.

    After the first call the target exists, so the rename guard (target must
    not exist) correctly blocks any second attempt.
    """
    target = patched_default

    home = tmp_path / "home"
    home.mkdir()
    legacy = home / ".the-one"
    legacy.mkdir()
    (legacy / "the-one.db").write_text("sentinel-db-content")

    _patch_path_home(monkeypatch, home)

    s = _make_fresh_settings()

    # First call — migration fires, target created.
    s.ensure_dirs()
    assert target.is_dir()
    assert not legacy.exists()

    # Second call — migration guard skips (target exists), no error.
    s.ensure_dirs()
    assert target.is_dir()
    assert (target / "the-one.db").read_text() == "sentinel-db-content"


# ---------------------------------------------------------------------------
# Test 5 — Guard: target already exists → no migration
# ---------------------------------------------------------------------------


def test_no_migration_when_target_exists(tmp_path, patched_default, monkeypatch):
    """When the target already exists, migration is skipped (idempotency guard)."""
    target = patched_default
    target.mkdir(parents=True)

    home = tmp_path / "home"
    home.mkdir()
    legacy = home / ".the-one"
    legacy.mkdir()
    (legacy / "the-one.db").write_text("legacy-content")

    _patch_path_home(monkeypatch, home)

    s = _make_fresh_settings()
    s.ensure_dirs()

    # Legacy must remain untouched.
    assert legacy.is_dir()
    assert (legacy / "the-one.db").read_text() == "legacy-content"


# ---------------------------------------------------------------------------
# Test 6 — Guard: paths are equal → no migration
# ---------------------------------------------------------------------------


def test_no_migration_when_paths_equal(tmp_path, monkeypatch, _cache_reset):
    """When the platform default equals ~/.the-one (edge-case guard), skip."""
    home = tmp_path / "home"
    home.mkdir()
    legacy = home / ".the-one"
    legacy.mkdir()
    (legacy / "the-one.db").write_text("content")

    monkeypatch.delenv("THE_ONE_DATA_DIR", raising=False)
    # Make _default_data_dir return the SAME path as the legacy dir.
    _patch_platformdirs(monkeypatch, legacy)
    _patch_path_home(monkeypatch, home)

    s = _make_fresh_settings()
    assert s.data_dir == legacy

    s.ensure_dirs()

    # No rename should have happened — legacy still there under original name.
    assert legacy.is_dir()
    assert (legacy / "the-one.db").read_text() == "content"
