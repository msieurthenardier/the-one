"""Per-agent knowledge-base tool provider (Mission 24, Flight 5, Leg 2; DD-5).

Reads :attr:`the_one.agent.config.AgentConfig.kb_ids` at agent-build time and
produces one :class:`~the_one.knowledge.tool.KBSearchTool` per attached
knowledge base. Sibling shape to
:class:`the_one.mcp._tool_provider.MCPToolProvider` — **not** a
:class:`the_one.tools.provider.ToolProvider` Protocol implementer, for the
same reason that class's docstring already gives: that Protocol is
synchronous and per-tool-name keyed, while this is async and per-entity
(per-knowledge-base) keyed.

Empty ``config.kb_ids`` returns ``[]`` immediately, with **no database
call** — verified by a test that injects a repository stub raising on any
call. A ``kb_id`` that no longer exists (deleted between attachment and
agent build) is logged at WARNING naming the agent and the id, then
skipped — the rest of the attached set still builds (the MCP orphan-source
precedent).

**Naming (DD-4)**: :func:`_normalize_kb_name` mirrors
``the_one/mcp/_tool.py::_normalize_source_name`` exactly (every character
outside ``[a-zA-Z0-9_-]`` becomes ``_``) — re-implemented here, not
imported, for knowledge-package independence (the MCP boundary is already
crossed once, at ``factory.py::_build_source_index``, so this duplication
is a package-hygiene preference, not the avoidance of a crossing that
otherwise doesn't exist).

**The collision discriminator is ALWAYS a fixed-length hash** — the first
8 hex characters of ``sha256(kb_id)``, stepping to 12 then 16 only if a
group still collides at that length — **never a prefix of ``kb_id``**.
``KnowledgeBase._validate_id`` allows up to 64 characters, the same as the
LLM tool-name ceiling, so "widen by taking more of ``kb_id``" can grow
unboundedly and overflow the very budget truncation already reserves
against; a fixed length is known BEFORE truncation and can be reserved
exactly (see :func:`_compute_tool_names`).

**Naming is computed for the agent's WHOLE attached set at once**
(:func:`_compute_tool_names`), because group-wide collision detection
needs that set — this is why naming lives in the provider and not in
:class:`~the_one.knowledge.tool.KBSearchTool` itself. The result is
independent of ``config.kb_ids``'s order: every input to the algorithm
(slug-collision grouping, the hash discriminator) is keyed by ``kb_id``
or by slug VALUE, never by list position, so a reorder never re-targets a
name-keyed ``disabled_tools`` entry at a different knowledge base.
"""

from __future__ import annotations

import hashlib
import logging
import re

from the_one.agent.config import AgentConfig
from the_one.db.models import KnowledgeBase
from the_one.knowledge.tool import KBSearchTool, build_description
from the_one.tools.base import Tool

logger = logging.getLogger(__name__)

# LLM-side tool-name ceiling (OpenAI and Anthropic both cap tool names at
# 64 characters) — mirrors `the_one/mcp/_tool.py::_TOOL_NAME_MAX_LEN`.
_TOOL_NAME_MAX_LEN = 64

_NAME_PREFIX = "kb__"
_NAME_SUFFIX = "__search"
_FIXED_OVERHEAD = len(_NAME_PREFIX) + len(_NAME_SUFFIX)

# AC-9: the discriminator's fixed lengths, tried in order. 8 hex chars
# first; only widened to 12 then 16 if a group still collides at the
# current length (astronomically unlikely for a real sha256 digest, but
# handled rather than assumed away — AC-9's "uniqueness is asserted, not
# assumed").
_HASH_LENGTHS: tuple[int, ...] = (8, 12, 16)


def _normalize_kb_name(name: str) -> str:
    """Normalize a knowledge-base name for use in a tool-name slug.

    Mirrors ``the_one/mcp/_tool.py::_normalize_source_name`` exactly:
    every character outside ``[a-zA-Z0-9_-]`` becomes ``_``. Idempotent on
    an already-normalized name.

    **A slug can itself contain ``__``** (e.g. ``"My  Notes"`` (two
    spaces) -> ``"My__Notes"``), which mis-renders
    ``_search_tools.py::_format_result``'s ``split("__", 2)[1]`` group
    label to ``"My"`` — the same latent flaw the MCP path already has.
    Recorded, not fixed (DD-4); pinned by a test.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _discriminator(kb_id: str, hash_len: int) -> str:
    return hashlib.sha256(kb_id.encode("utf-8")).hexdigest()[:hash_len]


def _build_name(slug: str, hash_len: int | None, kb_id: str) -> str:
    """Build one final tool name.

    ``hash_len is None`` -> no discriminator, the slug used verbatim
    (only reachable when the slug is both short enough and non-colliding).
    Otherwise the discriminator's budget is reserved BEFORE the slug is
    truncated (AC-10): ``reserve len(discriminator) + 1`` (the ``_``
    separator), truncate the slug to what remains, append the
    discriminator once.
    """
    if hash_len is None:
        return f"{_NAME_PREFIX}{slug}{_NAME_SUFFIX}"
    disc = _discriminator(kb_id, hash_len)
    reserved = len(disc) + 1  # +1 for the "_" separator before the hash
    max_slug_len = max(_TOOL_NAME_MAX_LEN - _FIXED_OVERHEAD - reserved, 0)
    truncated = slug[:max_slug_len]
    return f"{_NAME_PREFIX}{truncated}_{disc}{_NAME_SUFFIX}"


def _compute_tool_names(kbs: list[KnowledgeBase], *, agent_name: str) -> dict[str, str]:
    """Return ``{kb_id: tool_name}`` for every entry in ``kbs`` (DD-4).

    Rules, composed exactly once per knowledge base (AC-10, never two
    suffixes):

    1. **Group-wide collision** (AC-7): if a slug has more than one
       claimant among ``kbs``, EVERY member of that group gets the
       discriminator — not just the second and subsequent. Grouped by
       slug VALUE (a dict keyed on the raw, un-truncated slug), never by
       ``kbs`` list position, so the result is independent of input
       order.
    2. **Over-length** (AC-8): a slug whose un-discriminated name would
       exceed 64 characters always gets a discriminator too, truncated to
       fit — never dropped.
    3. **The discriminator is the AC-9 fixed-length hash**, budgeted
       before truncation (AC-10), applied at most once per name.
    4. **Uniqueness is asserted, not assumed** (AC-9): after the first
       pass, any names that still collide have their hash length widened
       (8 -> 12 -> 16) until they're unique or the lengths are exhausted.
    """
    slugs = {kb.id: _normalize_kb_name(kb.name) for kb in kbs}
    slug_members: dict[str, list[str]] = {}
    for kb_id, slug in slugs.items():
        slug_members.setdefault(slug, []).append(kb_id)

    hash_len_by_id: dict[str, int | None] = {}
    for kb in kbs:
        slug = slugs[kb.id]
        raw_name = f"{_NAME_PREFIX}{slug}{_NAME_SUFFIX}"
        over_length = len(raw_name) > _TOOL_NAME_MAX_LEN
        colliding = len(slug_members[slug]) > 1
        if over_length or colliding:
            hash_len_by_id[kb.id] = _HASH_LENGTHS[0]
            if over_length:
                logger.warning(
                    "agent %r: knowledge base %r's name is too long for a "
                    "tool name; truncating and appending a discriminator",
                    agent_name,
                    kb.name,
                )
            if colliding:
                logger.warning(
                    "agent %r: knowledge bases %s collide on tool-name "
                    "slug %r; appending a discriminator to all of them",
                    agent_name,
                    sorted(slug_members[slug]),
                    slug,
                )
        else:
            hash_len_by_id[kb.id] = None

    # AC-9: assert uniqueness across the whole set; widen the hash length
    # for any group that still collides, up to _HASH_LENGTHS' ceiling.
    for _ in range(len(_HASH_LENGTHS)):
        names = {kb.id: _build_name(slugs[kb.id], hash_len_by_id[kb.id], kb.id) for kb in kbs}
        by_name: dict[str, list[str]] = {}
        for kb_id, name in names.items():
            by_name.setdefault(name, []).append(kb_id)
        collided_ids = [kb_id for ids in by_name.values() if len(ids) > 1 for kb_id in ids]
        if not collided_ids:
            return names
        for kb_id in collided_ids:
            current = hash_len_by_id[kb_id] or _HASH_LENGTHS[0]
            idx = _HASH_LENGTHS.index(current)
            if idx + 1 < len(_HASH_LENGTHS):
                hash_len_by_id[kb_id] = _HASH_LENGTHS[idx + 1]
                logger.warning(
                    "agent %r: knowledge base %r's tool name still "
                    "collides at a %d-character discriminator; widening",
                    agent_name,
                    kb_id,
                    current,
                )

    # Exhausted widening — astronomically unlikely for real sha256
    # digests. Best-effort: return the last computed set rather than
    # raising, so the rest of the attachment still builds.
    return {kb.id: _build_name(slugs[kb.id], hash_len_by_id[kb.id], kb.id) for kb in kbs}


class KBToolProvider:
    """Per-agent knowledge-base tool builder (DD-5).

    Not a :class:`the_one.tools.provider.ToolProvider` Protocol
    implementer — see the module docstring.
    """

    async def get_tools_for_agent(
        self,
        config: AgentConfig,
        *,
        agent_name: str,
    ) -> list[Tool]:
        """Return the :class:`~the_one.knowledge.tool.KBSearchTool`
        instances to register into ``agent_name``'s
        :class:`~the_one.tools.base.ToolRegistry`.

        Empty ``config.kb_ids`` -> ``[]``, no database call (AC-12). A
        ``kb_id`` that no longer exists -> WARNING naming the agent and
        the id, skip it, keep the rest (AC-13).
        """
        if not config.kb_ids:
            return []

        from the_one.db.connection import get_connection
        from the_one.db.repositories import KnowledgeBaseRepository

        conn = await get_connection()
        repo = KnowledgeBaseRepository(conn)

        kbs: list[KnowledgeBase] = []
        for kb_id in config.kb_ids:
            try:
                kbs.append(await repo.get(kb_id))
            except KeyError:
                logger.warning(
                    "agent %r references deleted knowledge base %r; skipping",
                    agent_name,
                    kb_id,
                )
        if not kbs:
            return []

        names = _compute_tool_names(kbs, agent_name=agent_name)

        return [
            KBSearchTool(
                name=names[kb.id],
                kb_id=kb.id,
                kb_name=kb.name,
                description=build_description(kb),
                agent_name=agent_name,
            )
            for kb in kbs
        ]
