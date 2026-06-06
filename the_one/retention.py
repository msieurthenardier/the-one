"""Daily chat-history purge — pure sweep service + due-check (M13 F03).

This module holds the *pure DB logic* for the daily automatic purge:
enumerate agents, compute a per-agent age cutoff, delete each agent's
sessions older than its cutoff, and advance the global ``last_purge_at``
timestamp. It deliberately does NOT import ``app.py`` (which pulls in
FastAPI + the in-memory ``_sessions`` registry) so the sweep stays
unit-testable in isolation. The app-layer wrapper in ``app.py`` calls
:func:`run_purge_sweep` and performs the ``_sessions`` eviction (DD4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

# NOTE: the repository imports are deferred into the functions below (not
# module-level) to keep this module cold-importable. ``the_one.db.repositories``
# participates in a pre-existing import cycle (repositories → agent.config →
# agent → mcp → _pool → repositories) that only resolves when ``the_one.agent``
# is imported first; importing the repos at this module's top would make
# ``from the_one.retention import …`` (and app.py's ``import the_one.retention``,
# placed before its agent import) trigger that cycle and crash at startup.

LAST_PURGE_KEY = "last_purge_at"
PURGE_DUE_AFTER = timedelta(hours=24)


def is_purge_due(last_purge_at: str | None, now: datetime) -> bool:
    """Due if never purged, or ≥24h since the last purge."""
    if last_purge_at is None:
        return True
    return now - datetime.fromisoformat(last_purge_at) >= PURGE_DUE_AFTER


async def get_last_purge_at(conn: aiosqlite.Connection) -> str | None:
    """Read the global last_purge_at (or None if never set). Kept HERE
    (not in app.py) so app.py needs no AppMetadataRepository import —
    app.py's repo import block does not include it (see Inputs)."""
    from the_one.db.repositories import AppMetadataRepository

    return await AppMetadataRepository(conn).get(LAST_PURGE_KEY)


async def run_purge_sweep(conn: aiosqlite.Connection) -> dict:
    """Per-agent age-based purge over all agents. Pure DB logic — does
    NOT touch app-layer _sessions (the app wrapper does). Returns
    {deleted, ids, last_purge_at}."""
    from the_one.db.repositories import (
        AppMetadataRepository,
        ChatSessionRepository,
        SQLiteAgentStore,
    )

    agent_store = SQLiteAgentStore(conn)
    chat_repo = ChatSessionRepository(conn)
    meta = AppMetadataRepository(conn)
    now = datetime.now(timezone.utc)
    all_ids: list[str] = []
    for name, days in await agent_store.list_retention_windows():
        cutoff = (now - timedelta(days=days)).isoformat()
        all_ids.extend(await chat_repo.delete_older_than(name, cutoff))
    last_purge_at = now.isoformat()
    await meta.set(LAST_PURGE_KEY, last_purge_at)
    return {"deleted": len(all_ids), "ids": all_ids, "last_purge_at": last_purge_at}
