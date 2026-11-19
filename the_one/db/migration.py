"""One-time migration of JSON agent configs to SQLite."""

from __future__ import annotations

import logging

from the_one.agent.store import FilesystemConfigStore
from the_one.config import settings
from the_one.db.repositories import SQLiteAgentStore
from the_one.naming import NameRuleError, check_agent_name, is_reserved_agent_name

logger = logging.getLogger(__name__)


async def migrate_json_to_sqlite(store: SQLiteAgentStore) -> int:
    """Migrate existing JSON agent configs into SQLite.

    Returns the number of configs migrated. Skips agents that already exist
    in the database.
    """
    fs_store = FilesystemConfigStore(settings.agents_dir)
    names = fs_store.list_agents()
    migrated = 0

    for name in names:
        if is_reserved_agent_name(name):
            logger.warning("Skipping legacy agent config %r: a reserved agent name", name)
            continue
        if await store.exists(name):
            logger.debug("Agent '%s' already in database, skipping", name)
            continue
        try:
            config = fs_store.load(name)
            try:
                check_agent_name(config.name)
            except NameRuleError as e:
                logger.warning("Skipping legacy agent config %r: %s", name, e.message)
                continue
            if await store.exists(config.name):
                logger.debug("Agent '%s' already in database, skipping", config.name)
                continue
            await store.save(config)
            migrated += 1
            logger.info("Migrated agent config: %s", name)
        except Exception:
            logger.exception("Failed to migrate agent config: %s", name)

    if migrated:
        logger.info("Migrated %d agent config(s) from JSON to SQLite", migrated)

    return migrated
