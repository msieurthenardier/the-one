"""Built-in platform-lookup tool — read-only name-to-id resolution over the
passively-populated connector directory.

Mission 23 Flight 4 Leg 3 (DD-5). Registered like every other built-in in
``tools/builtins.py`` — no factory carve-out beyond the DD-6 baseline-
visibility seed (``agent/factory.py``'s pair-seed loop); no auto-attach.

Read-only, and deliberately narrower than the send tool's authorization:
``ConnectorDirectoryRepository.search`` scopes CONNECTOR-LEVEL (agent_name
anywhere in the connector's binding — ``default_agent`` or any
``channel_map`` value). There is no per-target read gate beyond that
(send-time authorization, unchanged, remains the real per-target gate in
``tools/connector_send.py``); an out-of-scope connector's rows are simply
absent from the result — enumeration reveals nothing, no error path.

``FIND_PLATFORM_DESTINATION_TOOL_NAME`` is exported for
``agent/factory.py``'s DD-6 pair-seed loop, mirroring
``SEND_TO_PLATFORM_CHANNEL_TOOL_NAME`` (``tools/connector_send.py``).
"""

from __future__ import annotations

import json
from typing import Any

from the_one.tools.base import Tool

FIND_PLATFORM_DESTINATION_TOOL_NAME = "find_platform_destination"


class FindPlatformDestinationTool(Tool):
    """Look up a platform peer or channel by an observed name."""

    name = FIND_PLATFORM_DESTINATION_TOOL_NAME
    description = (
        "Look up a platform peer or channel by name in the directory of "
        "names the system has passively observed (matches display name "
        "OR username, case-insensitive substring). Returns up to 10 "
        "candidates, newest-observed first. Each candidate's ids paste "
        "directly into send_to_platform_channel's target: a peer "
        "candidate carries connector_id + peer_id; a channel candidate "
        "carries connector_id + channel_id (and thread_id when set). "
        "Omit connector_id unless you already have one from a prior "
        "result of this tool — it is an opaque id, never the platform "
        "type name, and a guessed connector_id yields false zero-matches."
    )
    # `required` must be a prefix of declared property order
    # (`tests/test_tool_base.py`'s declaration-order positional-binding
    # invariant, Flight 3's DD-11 lesson) — `query` is required and leads;
    # the optional `connector_id` follows.
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Name or username fragment to search for.",
            },
            "connector_id": {
                "type": ["string", "null"],
                "description": (
                    "An opaque id returned by a prior result of this tool "
                    "— never the platform type name (e.g. never 'stub', "
                    "'telegram', 'discord'). Omit unless you already have "
                    "such an id."
                ),
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: Any = None, connector_id: Any = None, **_extra: Any) -> str:  # type: ignore[override]
        if not isinstance(query, str) or not query.strip():
            return "[error] [constraint] query must be a non-empty string"
        if connector_id is not None and not isinstance(connector_id, str):
            return "[error] [constraint] connector_id must be a string"

        from the_one.db.connection import get_connection
        from the_one.db.repositories import ConnectorDirectoryRepository

        conn = await get_connection()
        repo = ConnectorDirectoryRepository(conn)
        results = await repo.search(self._agent_name, query, connector_id)

        if not results:
            return f"[no-match] no directory entry matches {query!r}"

        candidates: list[dict[str, Any]] = []
        for entry in results:
            # DD-5 literal-key translation (review HIGH fix): a peer
            # candidate NEVER carries channel keys and vice versa — no
            # generic `platform_id` in the tool's output, ever.
            candidate: dict[str, Any] = {
                "connector_id": entry.connector_id,
                "connector_name": entry.connector_name,
                "kind": entry.kind,
                "display_name": entry.display_name,
                "username": entry.username,
                "last_seen": entry.last_seen,
            }
            if entry.kind == "peer":
                candidate["peer_id"] = entry.platform_id
            else:
                candidate["channel_id"] = entry.platform_id
                candidate["thread_id"] = entry.thread_id
            candidates.append(candidate)
        # One compact JSON array — never prose-with-inline-ids (the same
        # literal-copy risk the flight's HIGH fix targeted).
        return json.dumps(candidates, separators=(",", ":"))
