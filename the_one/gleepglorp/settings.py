"""GleepGlorp's stored settings (M36 F1 L03).

One JSON value under the ``gleepglorp`` key in ``app_metadata``, read on every call
(no cache), the way the time-zone setting is. A stored value that does not parse
loads as the defaults.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

SETTING_KEY = "gleepglorp"

GleepGlorpState = Literal["off", "needs_model", "provider_missing", "ready"]


class GleepGlorpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = True
    provider_config_id: str | None = None
    model: str | None = None
    web_access: bool = True
    memory: bool = True
    retention_days: int = Field(30, ge=1, le=365)


async def load_settings(conn) -> GleepGlorpSettings:
    """Load the stored settings. Never raises; a bad stored value is the defaults."""
    from the_one.db.repositories import AppMetadataRepository

    try:
        raw = await AppMetadataRepository(conn).get(SETTING_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("Could not read the GleepGlorp setting; using the defaults", exc_info=True)
        return GleepGlorpSettings()
    if raw is None:
        return GleepGlorpSettings()
    try:
        return GleepGlorpSettings.model_validate_json(raw)
    except Exception:  # noqa: BLE001 - a bad stored value falls back to the defaults
        logger.warning("Stored GleepGlorp setting is invalid; using the defaults")
        return GleepGlorpSettings()


async def save_settings(conn, settings: GleepGlorpSettings) -> None:
    from the_one.db.repositories import AppMetadataRepository

    await AppMetadataRepository(conn).set(SETTING_KEY, settings.model_dump_json())


async def provider_exists(conn, provider_id: str) -> bool:
    async with conn.execute("SELECT 1 FROM llm_providers WHERE id = ?", (provider_id,)) as cur:
        return await cur.fetchone() is not None


async def state(conn, settings: GleepGlorpSettings) -> GleepGlorpState:
    if not settings.enabled:
        return "off"
    if not settings.provider_config_id or not settings.model:
        return "needs_model"
    if not await provider_exists(conn, settings.provider_config_id):
        return "provider_missing"
    return "ready"


async def response(conn, settings: GleepGlorpSettings | None = None) -> dict[str, Any]:
    """The GET/PUT body: the settings plus the derived state and whether web search can run."""
    from the_one.gleepglorp.web import web_search_available

    s = settings if settings is not None else await load_settings(conn)
    return {
        **s.model_dump(),
        "state": await state(conn, s),
        "web_search_available": await web_search_available(conn),
    }
