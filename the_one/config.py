from __future__ import annotations

import errno
import logging
import shutil
from pathlib import Path

import platformdirs
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _default_data_dir() -> Path:
    """Return the OS-conventional per-user data directory for the-one.

    Linux:   ~/.local/share/the-one
    macOS:   ~/Library/Application Support/the-one
    Windows: %LOCALAPPDATA%\\the-one
    """
    return Path(platformdirs.user_data_dir("the-one", appauthor=False))


def _resolve_env_file() -> str:
    """Choose the ``env_file`` pydantic-settings reads at class-definition time.

    M15 F5 L1 (DD8) — frozen ``.env`` anchoring. A frozen, double-clicked app
    has an unpredictable CWD, so a bare relative ``.env`` would silently never
    be found. When frozen, anchor ``.env`` to the per-user data directory (the
    same ``platformdirs`` location ``_default_data_dir`` uses) so it is found
    regardless of CWD. When NOT frozen, keep the relative ``.env`` (today's
    dev/source behavior, byte-for-byte).

    This MUST be computed at *import* time (here) rather than referencing
    ``_default_data_dir`` as an instance method: pydantic-settings resolves
    ``env_file`` from ``model_config`` when the ``Settings`` *class* is defined,
    before any instance exists. ``THE_ONE_*`` environment variables keep working
    regardless of which file (if any) is found — they take precedence over the
    ``.env`` file in pydantic-settings' source ordering.
    """
    # Avoid an import cycle: read the frozen flag directly (the platform layer
    # imports nothing from config, so importing it here is one-directional).
    from the_one.platform.env import is_frozen

    if is_frozen():
        return str(_default_data_dir() / ".env")
    return ".env"


class Settings(BaseSettings):
    model_config = {"env_prefix": "THE_ONE_", "env_file": _resolve_env_file(), "extra": "ignore"}

    # Web
    host: str = "127.0.0.1"
    port: int = 8484

    # Logging
    log_level: str = "INFO"

    # Dev mode (gates the mock provider type)
    dev_mode: bool = False

    # Chat telemetry overlay — context-fullness warn/critical thresholds (percent
    # of the model's context window). Plumbed to the frontend via /api/config and
    # read by telemetry-overlay.js to color the bar (warn → orange, crit → red)
    # and emit a non-color a11y signal. Env-overridable
    # (THE_ONE_CONTEXT_WARN_PCT / _CRIT_PCT); invalid combinations clamp back to
    # the 70/90 defaults (see the validator below). M16 F08 L05.
    context_warn_pct: int = 70
    context_crit_pct: int = 90

    # Paths — resolved via platformdirs to the OS-conventional per-user data dir.
    # Use default_factory so platformdirs is not evaluated at class-definition time
    # and so that model_fields_set correctly reflects whether data_dir was explicitly
    # supplied (env-sourced or init-kwargs) vs left to the factory default.
    data_dir: Path = Field(default_factory=_default_data_dir)

    @model_validator(mode="after")
    def _clamp_context_thresholds(self) -> Settings:
        """Guard the context-fullness thresholds: require
        ``0 < warn < crit <= 100``. An invalid combination (warn≥crit, out of
        range, etc.) CLAMPS both back to the 70/90 defaults and logs a warning —
        it must NOT raise, because this validator runs at ``Settings()``
        construction during boot and a raised error would crash startup. This is
        the single source of truth for threshold sanity; ``/api/config`` can then
        emit the values unconditionally.
        """
        if not (0 < self.context_warn_pct < self.context_crit_pct <= 100):
            logger.warning(
                "Invalid context-fullness thresholds (warn=%s, crit=%s); "
                "expected 0 < warn < crit <= 100. Resetting to defaults 70/90.",
                self.context_warn_pct,
                self.context_crit_pct,
            )
            self.context_warn_pct = 70
            self.context_crit_pct = 90
        return self

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
