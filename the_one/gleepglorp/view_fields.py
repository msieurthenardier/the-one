"""The ``fields`` view: what a change proposal may contain (M36 F2 L2, DD1).

Generated from the declared change shape in :mod:`the_one.gleepglorp.kinds`, never
written by hand, so it cannot drift from what ``propose_change`` accepts. It lists the three
proposable kinds, or gives one kind's fields (type, bounds, whether a field is required or
create-only, and how a reference is named). It reads no stored value.
"""

from __future__ import annotations

from typing import Any

from the_one.gleepglorp.view_core import Ctx, _list_or_detail


async def fields_view(ctx: Ctx, name: str | None = None) -> Any:
    from the_one.gleepglorp import kinds

    summaries = {e["name"]: e["summary"] for e in kinds.describe()}
    entries = [(k, k) for k in kinds.KINDS]

    async def summarize(key: str, item_name: str) -> str:
        return summaries[key]

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        return kinds.describe(key)

    return await _list_or_detail("fields", entries, summarize, detail, name)
