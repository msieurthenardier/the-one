"""``read_app_config``: GleepGlorp's one read-only tool (M36 F1 L05, DD5 as amended).

Reads the app's configuration and status through the whitelist views in
:mod:`the_one.gleepglorp.views` and nothing else. It never writes, never fetches over the
network, and never returns a secret, a chat, a file or a log. It stays untrusted in the
taint rule (the fail-closed default in ``the_one/agent/taint.py``): a configuration
field can carry operator- or server-written text.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from the_one.gleepglorp import views
from the_one.tools.base import Tool

logger = logging.getLogger(__name__)

READ_APP_CONFIG_TOOL_NAME = "read_app_config"


class ReadAppConfigTool(Tool):
    """Read one part of the app's configuration, read-only."""

    name = READ_APP_CONFIG_TOOL_NAME
    summary = "Reads the app's configuration and status, never a secret."
    description = (
        "Read how this app is set up, read-only. kind is one of: overview (counts, names, "
        "your own state), agents, mcp_servers, providers, knowledge_bases, connectors, "
        "routines (needs name: an agent), secrets (names and key names only), "
        "built_in_tools, settings. Give name to get one item's detail; leave it out to list "
        "every item. Secret values are never shown."
    )
    parameters = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(views.KINDS)},
            "name": {
                "type": ["string", "null"],
                "description": "Item name for its detail; omit to list. routines needs an agent.",
            },
        },
        "required": ["kind"],
    }

    async def execute(self, kind: Any = None, name: Any = None, **_extra: Any) -> str:  # type: ignore[override]
        if not isinstance(kind, str) or kind not in views.KINDS:
            return f"Unknown kind {str(kind)[:60]!r}. Valid kinds: {', '.join(views.KINDS)}"
        if name is not None and not isinstance(name, str):
            return "name must be a string"

        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.encryption import get_encryptor

        try:
            conn = await get_connection()
            data = await views.read(conn, get_encryptor(settings.data_dir), kind, name)
        except views.PlainMessage as msg:
            return str(msg)
        except Exception:  # noqa: BLE001 - the tool never raises into the loop
            logger.warning("read_app_config(%s) failed", kind, exc_info=True)
            return f"Could not read {kind} right now."
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
