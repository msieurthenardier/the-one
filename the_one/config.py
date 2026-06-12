from __future__ import annotations

import errno
import logging
import shutil
from pathlib import Path

import platformdirs
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _default_data_dir() -> Path:
    """Return the OS-conventional per-user data directory for the-one.

    Linux:   ~/.local/share/the-one
    macOS:   ~/Library/Application Support/the-one
    Windows: %APPDATA%\\the-one
    """
    return Path(platformdirs.user_data_dir("the-one", appauthor=False))


class Settings(BaseSettings):
    model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

    # Web
    host: str = "127.0.0.1"
    port: int = 8484

    # Logging
    log_level: str = "INFO"

    # Dev mode (gates the mock provider type)
    dev_mode: bool = False

    # Paths — resolved via platformdirs to the OS-conventional per-user data dir.
    # Use default_factory so platformdirs is not evaluated at class-definition time
    # and so that model_fields_set correctly reflects whether data_dir was explicitly
    # supplied (env-sourced or init-kwargs) vs left to the factory default.
    data_dir: Path = Field(default_factory=_default_data_dir)

    @property
    def agents_dir(self) -> Path:
        return self.data_dir / "agents"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "the-one.db"

    def ensure_dirs(self) -> None:
        """Create the data directory (and any parents), migrating a legacy
        ``~/.the-one`` directory into the new OS-conventional location when
        all of the following hold:

        1. ``data_dir`` is the default-resolved path (not an explicit env/init
           override — checked via ``model_fields_set``).
        2. The legacy ``~/.the-one`` directory exists and is a real directory
           (not a symlink or other non-dir).
        3. The resolved target does not already exist.
        4. The legacy path and the resolved target differ (guards the edge case
           where the platform default *is* ``~/.the-one``).

        Migration is attempted BEFORE the mkdir so that an empty target cannot
        block the rename.  Migration errors are non-fatal: cross-device moves
        fall back to copy-then-remove; all other OSErrors are logged at WARNING
        and skipped — ``ensure_dirs()`` must never raise (it runs at DB-connection
        and agent-creation time).
        """
        self._maybe_migrate_legacy()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _maybe_migrate_legacy(self) -> None:
        """Attempt to rename the legacy ~/.the-one into self.data_dir.

        Guards ensure the migration only fires under default resolution, never
        under an explicit override.  See ensure_dirs() for the full guard list.
        """
        # Guard 1: data_dir must be the default-resolved path, not explicitly set.
        if "data_dir" in self.model_fields_set:
            return

        legacy = Path.home() / ".the-one"

        # Guard 2: legacy must exist and be a real directory (not a symlink).
        if not legacy.is_dir() or legacy.is_symlink():
            return

        target = self.data_dir

        # Guard 3: target must not already exist.
        if target.exists():
            return

        # Guard 4: paths must differ.
        if legacy == target:
            return

        # Attempt the migration.
        logger.info("Migrating legacy data directory %s → %s", legacy, target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(target)
            logger.info("Migration complete: %s → %s", legacy, target)
        except OSError as exc:
            # Cross-device rename (EXDEV) — fall back to copy-then-remove.
            if exc.errno == errno.EXDEV:
                logger.info(
                    "Cross-device move detected; falling back to copy-then-remove: %s → %s",
                    legacy,
                    target,
                )
                try:
                    shutil.copytree(str(legacy), str(target))
                    shutil.rmtree(str(legacy))
                    logger.info("Copy-then-remove migration complete: %s → %s", legacy, target)
                except OSError as copy_exc:
                    logger.warning(
                        "Migration copy-then-remove failed (%s); skipping. "
                        "Legacy dir left at %s, target %s.",
                        copy_exc,
                        legacy,
                        target,
                    )
            else:
                logger.warning(
                    "Migration failed (%s); skipping. Legacy dir left at %s, target %s.",
                    exc,
                    legacy,
                    target,
                )


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
