"""One-time startup cleanup of copied tool-override values (sortie 07, DD13).

Before sortie 07 the agent editor's Built-in tools tab pre-filled every field with
the app-wide value and the Save walk stored every non-empty field, so opening a
panel and saving copied inherited values into the agent. They act as pins, which
is not what the operator meant. This pass runs **once ever** (recorded under the
``tool_override_cleanup_v1`` key in ``app_metadata``) and, for each agent and each
tool entry:

* drops a field whose value equals the effective app-wide value (the stored row
  merged over the schema defaults; scalars by JSON-canonical equality, lists as
  sets of strings);
* strips app-wide entries from the denied lists (no change in effect, DD3);
* drops dead keys (a non-boolean field with no marker never applied);
* drops tool entries left empty.

Agents are saved through ``SQLiteAgentStore`` so encrypted fields round-trip. The
pass never raises: a failure before the agent loop starts writes no marker (nothing
was changed, so the next start retries); once the loop has started the marker is
written in a ``finally``, even when individual agents failed (they are logged by
name and keep their values, which are valid and just act as pins). A copy of an
app-wide value the operator has since changed no longer matches, so it stays.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from the_one.db.models import now_iso
from the_one.tools.resolver import NarrowSuperset, baseline_value, field_marker

logger = logging.getLogger(__name__)

MARKER_KEY = "tool_override_cleanup_v1"


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        if all(isinstance(x, str) for x in a) and all(isinstance(x, str) for x in b):
            return set(a) == set(b)
    return _canon(a) == _canon(b)


def _is_dead(schema: type, key: str) -> bool:
    info = schema.model_fields[key]
    if info.annotation is bool:
        return False
    try:
        field_marker(schema, key)
    except ValueError:
        return True
    return False


def clean_entry(schema: type, merged_row: dict, entry: dict) -> dict:
    """The tool entry without copied, redundant or dead keys (a new dict)."""
    out: dict = {}
    for key, value in entry.items():
        if key not in schema.model_fields:
            out[key] = value  # not ours to judge: carried, as the tab carries it
            continue
        if _is_dead(schema, key):
            continue
        tool_val = baseline_value(schema, key, merged_row)
        if _same(value, tool_val):
            continue
        if (
            isinstance(value, list)
            and isinstance(tool_val, list)
            and field_marker(schema, key) is NarrowSuperset
        ):
            value = [v for v in value if v not in tool_val]
            if not value:
                continue
        out[key] = value
    return out


def clean_overrides(
    overrides: dict[str, Any], rows: dict[str, Any], tool_classes: dict[str, type]
) -> dict[str, Any]:
    """The cleaned ``tool_overrides`` map; entries that are not dicts, or name a
    tool this build does not know, are carried untouched."""
    result: dict[str, Any] = {}
    for tool, entry in overrides.items():
        tool_cls = tool_classes.get(tool)
        if tool_cls is None or not isinstance(entry, dict):
            result[tool] = entry
            continue
        schema = tool_cls.Config
        if not schema.model_fields:
            result[tool] = entry
            continue
        row = rows.get(tool)
        merged = row.merged_config() if row is not None else {}
        cleaned = clean_entry(schema, merged, entry)
        if cleaned or not entry:
            result[tool] = cleaned
    return result


async def cleanup_copied_overrides(conn, agent_store, tool_repo, meta_repo) -> None:
    """Run the cleanup if it has never run. Never raises."""
    try:
        if await meta_repo.get(MARKER_KEY) is not None:
            return
        from the_one.tools.builtins import _TOOL_CLASSES

        names = await agent_store.list_agents()
        rows = {c.name: c for c in await tool_repo.list()}
    except Exception:
        logger.warning("tool override cleanup could not start; will retry", exc_info=True)
        return
    changed = 0
    try:
        for name in names:
            try:
                cfg = await agent_store.load(name)
                if not cfg.tool_overrides:
                    continue
                cleaned = clean_overrides(cfg.tool_overrides, rows, _TOOL_CLASSES)
                if cleaned == cfg.tool_overrides:
                    continue
                await agent_store.save(cfg.model_copy(update={"tool_overrides": cleaned or None}))
                changed += 1
            except Exception:
                logger.warning(
                    "tool override cleanup failed for agent %r; its values are kept",
                    name,
                    exc_info=True,
                )
    except Exception:
        logger.warning("tool override cleanup stopped partway", exc_info=True)
    finally:
        try:
            await meta_repo.set(MARKER_KEY, now_iso())
        except Exception:
            logger.warning("tool override cleanup could not record its marker", exc_info=True)
    if changed:
        logger.info("tool override cleanup: cleaned %d agent(s)", changed)
