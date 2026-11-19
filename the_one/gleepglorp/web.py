"""Whether GleepGlorp's ``web_search`` can run (M36 F1 L06, DD5).

``search_configured`` is the one decision: the keyless engines (DuckDuckGo, and anything
unrecognised, which the backend factory treats as DuckDuckGo) always work; a keyed engine
needs every required field filled; a tool switched off for the whole app is never available.
The factory build and ``GET /api/gleepglorp``'s
``web_search_available`` both use it, so the Settings hint and the tool never disagree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# The required fields of each keyed engine (``_web_search_config.py``).
_REQUIRED: dict[str, tuple[str, ...]] = {
    "searxng": ("searxng_base_url",),
    "google_pse": ("google_pse_api_key", "google_pse_cse_id"),
    "brave": ("brave_api_key",),
    "tavily": ("tavily_api_key",),
}


def search_configured(config: Mapping[str, Any] | None, *, enabled: bool = True) -> bool:
    """True when ``web_search`` is on app-wide (``enabled``) and its merged config names a
    usable engine."""
    if not enabled:
        return False
    cfg = config or {}
    engine = cfg.get("search_backend") or "duckduckgo"
    for field in _REQUIRED.get(engine, ()):
        value = cfg.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


async def web_search_available(conn) -> bool:
    """``search_configured`` over the stored ``web_search`` tool config."""
    from the_one.config import settings
    from the_one.db.repositories import ToolConfigRepository
    from the_one.encryption import get_encryptor

    repo = ToolConfigRepository(conn, get_encryptor(settings.data_dir))
    for c in await repo.list():
        if c.name == "web_search":
            return search_configured(c.merged_config(), enabled=bool(c.enabled))
    return search_configured(None)
