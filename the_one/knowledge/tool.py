"""``KBSearchTool``: the per-agent, per-knowledge-base search tool (Mission
24, Flight 5, Leg 2; DD-4, DD-8).

One instance per attached knowledge base, built by
:class:`the_one.knowledge.tool_provider.KBToolProvider` at agent-build time.
The knowledge base's identity (``kb_id``) is baked into the tool instance —
never an argument the model supplies — because the agent's
:class:`~the_one.tools.base.ToolRegistry` gates on tool *name*, not on
arguments, so an agent can only ever reach the knowledge bases the operator
attached (``AgentConfig.kb_ids``); see ``SECURITY-MODEL.md``'s
"Knowledge-base indexing" bullet.

**Naming is the provider's job, not this tool's** (DD-4): group-collision
detection needs the agent's whole attached set, which only
:class:`KBToolProvider` has, so the provider computes the finished
``kb__{...}__search`` name and hands it to the constructor. See
``tool_provider.py`` for the naming algorithm.

**Instance attributes before ``super().__init__()``** — the
``MCPClientTool`` precedent (``the_one/mcp/_tool.py``): the base
:class:`~the_one.tools.base.Tool` ``__init__`` does not touch
``self.name``/``self.description``/``self.parameters``, so setting them
first is safe, and ``agent_name`` is threaded through to ``super().__init__``
so ``tool._agent_name == name`` holds for every registered tool
(``tests/test_factory.py::TestAgentNamePlumbing``).

**``limit`` range-checking is this tool's own job** (AC-3): ``Agent._execute_tool``
(``the_one/agent/core.py``) calls ``tool.execute(**args)`` directly with no
JSON-Schema validation or coercion against ``self.parameters`` — a raised
exception becomes ``[error] Tool execution failed: {e}``. An out-of-range
``limit`` is therefore rejected with a ``ValueError`` message, never
silently clamped, matching ``KBChunkRepository.search_keyword``'s own
convention for its ``k`` parameter.

**Everything is resolved at call time, not construction time** (DD-4): the
connection, repositories, vector store and embedding backend are all
looked up fresh inside :meth:`execute` — the tool instance is built once
per agent construction and may outlive any one of them.
``get_embedding_backend()`` is resolved under ``asyncio.to_thread`` because
it is synchronous and takes a ``threading.Lock``; calling it directly on
the event loop before warm-up has finished would block the loop for the
model load.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from the_one.knowledge.retrieval import SearchResult, search
from the_one.tools.base import Tool

if TYPE_CHECKING:
    from the_one.db.models import KnowledgeBase

logger = logging.getLogger(__name__)

# DD-4: parameters. `limit` is rejected out of range, not clamped (AC-3) —
# matching `search_keyword`'s own convention for its `k` parameter.
_DEFAULT_LIMIT = 5
_MIN_LIMIT = 1
_MAX_LIMIT = 20

# DD-8: which of the four degrade causes leave keyword-only results. The
# one cause NOT in this set — "keyword index unavailable" — is the
# reverse: semantic-only results. Getting this backwards renders "these
# are keyword results" for a semantic-only response, which DD-8 calls out
# by name as the trap to avoid.
_KEYWORD_ONLY_DEGRADE_CAUSES = frozenset(
    {
        "semantic index rebuilding",
        "semantic index busy",
        "semantic index unavailable",
    }
)


def build_description(kb: "KnowledgeBase") -> str:
    """Build the tool's ``description`` (DD-4/DD-7/DD-8).

    Names the knowledge base and, when set, carries its description
    **verbatim** — after the DD-7 amendment this is the ONLY text
    ``search_tools`` matches a knowledge base on (no ``source_index``
    entry exists), so the knowledge base's own words must appear here
    unaltered for substring matching to find them (``_search_tools.py``'s
    ``_match_score`` is a plain substring test).

    Also instructs terse, keyword-shaped queries rather than sentences —
    not a style preference: FTS5's implicit AND (``search_keyword``)
    drops the keyword side to zero hits for a sentence-shaped query, which
    is exactly the half the mission's exact-term guarantee rests on
    (DD-3).
    """
    text = f"Search the {kb.name!r} knowledge base."
    if kb.description:
        text += f" {kb.description}"
    text += " Use short keyword queries, not full sentences."
    return text


def _render_result(kb_name: str, query: str, result: SearchResult) -> str:
    """Render :class:`SearchResult` as the tool's returned string (DD-8).

    Shape: an optional degrade line (verbatim ``SearchResult.degraded``
    plus a side-correct sentence) ABOVE everything else, then either a
    header line naming the knowledge base/query/hit-count followed by one
    citation line + chunk text per hit, or — no hits — one sentence naming
    the knowledge base and the query (never an empty string).

    **No per-hit text cap and no total cap here** (AC-28): chunk text is
    already bounded by the chunking settings (1,000 chars by default) and
    ``limit`` is bounded at 20, so the worst case is ~20 KB — and the
    agent loop's context-budget governor (``Agent._govern``,
    ``the_one/agent/core.py``) already bounds every tool result with
    ``truncation_direction = "head"``, the right end since hits are
    emitted best-first. Adding a second cap here would fight that
    governor. Note the governor WILL truncate on a small-context model —
    "~20 KB" is a worst-case size, not a delivery guarantee.
    """
    lines: list[str] = []

    if result.degraded:
        if result.degraded in _KEYWORD_ONLY_DEGRADE_CAUSES:
            note = "these are keyword-only results"
        else:
            # "keyword index unavailable" — the one reversed cause:
            # these are semantic-only results.
            note = "these are semantic-only results"
        lines.append(f"[degraded: {result.degraded} — {note}]")

    if not result.hits:
        lines.append(f"No results in knowledge base {kb_name!r} for {query!r}.")
        return "\n".join(lines)

    lines.append(f"{len(result.hits)} result(s) from knowledge base {kb_name!r} for {query!r}:")
    for n, hit in enumerate(result.hits, start=1):
        # AC-25: the chunk's own item_id/path — never a parent_id. `search`
        # already resolved this; the citation line is a straight render.
        lines.append(f"[{n}] {hit.path} #{hit.seq} ({hit.char_start}-{hit.char_end})")
        lines.append(hit.text)
    return "\n".join(lines)


class KBSearchTool(Tool):
    """Per-agent, per-knowledge-base search tool (DD-4)."""

    def __init__(
        self,
        *,
        name: str,
        kb_id: str,
        kb_name: str,
        description: str,
        agent_name: str,
    ) -> None:
        # Instance attrs BEFORE super().__init__() — MCPClientTool
        # precedent (the base __init__ does not touch these three).
        self.name = name
        self.description = description
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": ("Terse, keyword-shaped search terms (not a full sentence)."),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        f"Maximum number of hits to return "
                        f"({_MIN_LIMIT}-{_MAX_LIMIT}, default {_DEFAULT_LIMIT})."
                    ),
                },
            },
            "required": ["query"],
        }
        self.kb_id = kb_id
        self.kb_name = kb_name
        super().__init__(agent_name=agent_name)

    async def execute(self, query: str = "", limit: int = _DEFAULT_LIMIT) -> str:  # type: ignore[override]
        # AC-3: the tool's own job — Agent._execute_tool applies no schema
        # validation. bool is an int subclass; excluded explicitly so
        # `limit=True` isn't silently accepted as 1.
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not (_MIN_LIMIT <= limit <= _MAX_LIMIT)
        ):
            raise ValueError(
                f"limit must be an integer between {_MIN_LIMIT} and {_MAX_LIMIT}, got {limit!r}"
            )

        # DD-4: resolved at call time, never cached on the instance.
        from the_one.db.connection import get_connection
        from the_one.db.repositories import KBChunkRepository, KBItemRepository
        from the_one.embeddings import get_embedding_backend
        from the_one.vectors import get_vector_store

        conn = await get_connection()
        chunk_repo = KBChunkRepository(conn)
        item_repo = KBItemRepository(conn)
        store = await get_vector_store()
        # Synchronous + lock-taking (see module docstring) — must not run
        # directly on the event loop.
        backend = await asyncio.to_thread(get_embedding_backend)

        result = await search(
            self.kb_id,
            query,
            limit=limit,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=backend,
        )
        return _render_result(self.kb_name, query, result)
