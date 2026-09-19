"""Tests for ``the_one/knowledge/tool.py`` and
``the_one/knowledge/tool_provider.py`` (Mission 24, Flight 5, Leg 2).

Covers: ``KBSearchTool``'s shape (instance attrs before ``super().__init__``,
``agent_name`` threading, ``limit`` range-checking, description content,
result rendering incl. all four degrade causes), ``_normalize_kb_name``'s
mirror of the MCP normalizer (incl. the recorded ``__``-collapse flaw),
``compute_tool_names``'s naming algorithm (group-wide collision, the
fixed-length hash discriminator, truncate-and-suffix, the compound case,
order-independence), and ``KBToolProvider.get_tools_for_agent`` (the
empty/no-DB-call fast path, the orphan-``kb_id`` skip, and the happy path).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from the_one.db.models import KnowledgeBase
from the_one.knowledge import tool as tool_mod
from the_one.knowledge import tool_provider as provider_mod
from the_one.knowledge.retrieval import SearchHit, SearchResult
from the_one.knowledge.tool import KBSearchTool, build_description
from the_one.knowledge.tool_provider import (
    KBToolProvider,
    _normalize_kb_name,
    compute_tool_names,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kb(kb_id: str, name: str, description: str = "") -> KnowledgeBase:
    return KnowledgeBase(id=kb_id, name=name, description=description)


def _hit(chunk_id: int = 1, path: str = "notes/a.md", seq: int = 0) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        item_id="item-1",
        path=path,
        seq=seq,
        char_start=0,
        char_end=10,
        text="hello world",
        score=0.5,
    )


# ---------------------------------------------------------------------------
# _normalize_kb_name
# ---------------------------------------------------------------------------


class TestNormalizeKbName:
    def test_ascii_alnum_and_dash_underscore_preserved(self) -> None:
        assert _normalize_kb_name("docs-1_a") == "docs-1_a"

    def test_other_characters_become_underscore(self) -> None:
        assert _normalize_kb_name("My Docs!") == "My_Docs_"

    def test_double_space_collapses_to_double_underscore(self) -> None:
        # AC-21: the recorded latent flaw, same as the MCP path — a slug
        # containing "__" mis-renders _format_result's group label.
        assert _normalize_kb_name("My  Notes") == "My__Notes"

    def test_idempotent_on_already_normalized_name(self) -> None:
        normalized = _normalize_kb_name("already_ok-name")
        assert _normalize_kb_name(normalized) == normalized


# ---------------------------------------------------------------------------
# compute_tool_names
# ---------------------------------------------------------------------------


class TestComputeToolNames:
    def test_single_short_name_still_gets_a_discriminator(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # AC-1/DD-17: the discriminator is now unconditional — even a
        # solo, short, non-colliding name is discriminated, so its
        # derived name never equals the undiscriminated form.
        # AC-3/L2-D1: applying the discriminator unconditionally does
        # NOT make the WARNING logs unconditional — an ordinary short,
        # non-colliding name still logs neither "too long" nor "collide".
        kb = _kb("kb1", "Docs")
        with caplog.at_level(logging.WARNING):
            names = compute_tool_names([kb], agent_name="agent")
        name = names["kb1"]
        assert name.startswith("kb__Docs_")
        assert name.endswith("__search")
        assert name != "kb__Docs__search"
        disc = name[len("kb__Docs_") : -len("__search")]
        assert len(disc) == 8
        assert all(c in "0123456789abcdef" for c in disc)
        assert caplog.records == []

    def test_two_distinct_short_names_each_get_their_own_discriminator(self) -> None:
        # AC-1/DD-17: two distinct, non-colliding short names are each
        # independently discriminated — not left bare just because
        # neither collides with the other.
        kbs = [_kb("kb1", "Docs"), _kb("kb2", "Runbooks")]
        names = compute_tool_names(kbs, agent_name="agent")
        assert names["kb1"].startswith("kb__Docs_")
        assert names["kb1"].endswith("__search")
        assert names["kb1"] != "kb__Docs__search"
        assert names["kb2"].startswith("kb__Runbooks_")
        assert names["kb2"].endswith("__search")
        assert names["kb2"] != "kb__Runbooks__search"
        assert names["kb1"] != names["kb2"]

    def test_derived_name_is_invariant_to_set_composition(self) -> None:
        # AC-2, DD-17's whole point: a knowledge base's derived name is
        # a pure function of (kb.name, kb.id) alone — computing it for
        # [A], then [A, B] where B shares A's name, then [A, C] where C
        # does not, must yield the identical name for A every time.
        kb_a = _kb("kb-a", "Docs")
        kb_b_same_name = _kb("kb-b", "Docs")
        kb_c_different_name = _kb("kb-c", "Runbooks")

        alone = compute_tool_names([kb_a], agent_name="agent")
        with_same_name_sibling = compute_tool_names([kb_a, kb_b_same_name], agent_name="agent")
        with_different_sibling = compute_tool_names([kb_a, kb_c_different_name], agent_name="agent")

        assert alone["kb-a"] == with_same_name_sibling["kb-a"] == with_different_sibling["kb-a"]

    def test_colliding_names_both_get_discriminator(self, caplog: pytest.LogCaptureFixture) -> None:
        kbs = [_kb("kb-docs-1", "Docs"), _kb("kb-docs-2", "Docs")]
        with caplog.at_level(logging.WARNING):
            names = compute_tool_names(kbs, agent_name="agent")
        assert names["kb-docs-1"] != names["kb-docs-2"]
        for name in names.values():
            assert name.startswith("kb__Docs_")
            assert name.endswith("__search")
            assert len(name) <= 64
        assert any("collide" in r.message for r in caplog.records)

    def test_collision_discriminator_is_not_a_kb_id_prefix(self) -> None:
        # AC-7/AC-9: never `_{kb_id[:6]}` — assert the actual kb_id
        # characters (beyond the shared "kb-docs-" prefix) do not appear
        # literally in the discriminator segment.
        kbs = [_kb("kb-docs-1", "Docs"), _kb("kb-docs-2", "Docs")]
        names = compute_tool_names(kbs, agent_name="agent")
        for name in names.values():
            # Discriminator segment is the part between "kb__Docs_" and "__search".
            disc = name[len("kb__Docs_") : -len("__search")]
            assert disc not in ("1", "2")
            assert len(disc) == 8  # AC-9's first fixed length

    def test_collision_group_names_stable_under_reorder(self) -> None:
        kbs = [_kb("kb-docs-1", "Docs"), _kb("kb-docs-2", "Docs")]
        forward = compute_tool_names(kbs, agent_name="agent")
        backward = compute_tool_names(list(reversed(kbs)), agent_name="agent")
        assert forward == backward

    def test_over_length_name_truncates_and_suffixes(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        long_name = "A" * 60  # kb__ + 60 chars + __search = 72 > 64
        kb = _kb("kb1", long_name)
        with caplog.at_level(logging.WARNING):
            names = compute_tool_names([kb], agent_name="agent")
        name = names["kb1"]
        assert len(name) <= 64
        assert name.startswith("kb__")
        assert name.endswith("__search")
        # Never dropped — AC-8.
        assert name != ""
        assert any("too long" in r.message for r in caplog.records)

    def test_over_length_solo_name_still_gets_a_discriminator(self) -> None:
        # AC-8: even a SOLE over-length name is truncated AND suffixed —
        # never truncated alone, since truncation-only risks a silent
        # collision the assertion pass is what actually prevents.
        long_name = "B" * 60
        kb = _kb("kb1", long_name)
        names = compute_tool_names([kb], agent_name="agent")
        name = names["kb1"]
        body = name[len("kb__") : -len("__search")]
        # body is "<truncated-slug>_<8-hex-discriminator>"
        disc = body.rsplit("_", 1)[-1]
        assert len(disc) == 8
        assert all(c in "0123456789abcdef" for c in disc)

    def test_compound_case_truncation_and_shared_id_prefix(self) -> None:
        # AC-10b: two names each long enough to need AC-8 truncation, AND
        # kb_ids sharing a 6+ character prefix. Both unique, both <= 64,
        # stable under reorder.
        name_a = "Engineering Runbooks And Internal Documentation Archive One"
        name_b = "Engineering Runbooks And Internal Documentation Archive Two"
        kbs = [_kb("shared-prefix-aaa", name_a), _kb("shared-prefix-bbb", name_b)]
        forward = compute_tool_names(kbs, agent_name="agent")
        backward = compute_tool_names(list(reversed(kbs)), agent_name="agent")
        assert forward == backward
        assert forward["shared-prefix-aaa"] != forward["shared-prefix-bbb"]
        for name in forward.values():
            assert len(name) <= 64

    def test_widening_when_discriminator_still_collides(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # AC-9: force an artificial 8-hex collision so the algorithm must
        # widen to 12. Real sha256 collisions at 8 hex are not
        # constructible by hand, so the discriminator function itself is
        # monkeypatched to collide at length 8 and diverge at length 12+.
        def _fake_discriminator(kb_id: str, hash_len: int) -> str:
            if hash_len == 8:
                return "deadbeef"
            return f"{kb_id:0<{hash_len}}"[:hash_len]

        monkeypatch.setattr(provider_mod, "_discriminator", _fake_discriminator)
        kbs = [_kb("kb-docs-1", "Docs"), _kb("kb-docs-2", "Docs")]
        with caplog.at_level(logging.WARNING):
            names = compute_tool_names(kbs, agent_name="agent")
        assert names["kb-docs-1"] != names["kb-docs-2"]
        assert any("still" in r.message and "widening" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# KBToolProvider.get_tools_for_agent
# ---------------------------------------------------------------------------


class _AgentConfigStub:
    """Minimal stand-in with only the attribute the provider reads."""

    def __init__(self, kb_ids: list[str]) -> None:
        self.kb_ids = kb_ids


class TestKBToolProvider:
    async def test_empty_kb_ids_returns_empty_with_no_db_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _raising_get_connection():
            raise AssertionError("get_connection must not be called for empty kb_ids")

        monkeypatch.setattr("the_one.db.connection.get_connection", _raising_get_connection)
        provider = KBToolProvider()
        tools = await provider.get_tools_for_agent(_AgentConfigStub(kb_ids=[]), agent_name="a")
        assert tools == []

    async def test_orphan_kb_id_skipped_rest_kept(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        real_kb = _kb("kb-real", "Docs")

        class _StubRepo:
            def __init__(self, conn) -> None:
                pass

            async def get(self, kb_id: str) -> KnowledgeBase:
                if kb_id == "kb-missing":
                    raise KeyError(f"Knowledge base not found: {kb_id}")
                return real_kb

        monkeypatch.setattr(
            "the_one.db.connection.get_connection", AsyncMock(return_value=object())
        )
        monkeypatch.setattr("the_one.db.repositories.KnowledgeBaseRepository", _StubRepo)

        provider = KBToolProvider()
        with caplog.at_level(logging.WARNING):
            tools = await provider.get_tools_for_agent(
                _AgentConfigStub(kb_ids=["kb-missing", "kb-real"]), agent_name="agent-x"
            )
        assert len(tools) == 1
        assert tools[0].kb_id == "kb-real"
        assert any("kb-missing" in r.message and "agent-x" in r.message for r in caplog.records)

    async def test_all_orphaned_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _StubRepo:
            def __init__(self, conn) -> None:
                pass

            async def get(self, kb_id: str) -> KnowledgeBase:
                raise KeyError(f"Knowledge base not found: {kb_id}")

        monkeypatch.setattr(
            "the_one.db.connection.get_connection", AsyncMock(return_value=object())
        )
        monkeypatch.setattr("the_one.db.repositories.KnowledgeBaseRepository", _StubRepo)

        provider = KBToolProvider()
        tools = await provider.get_tools_for_agent(
            _AgentConfigStub(kb_ids=["kb-a", "kb-b"]), agent_name="agent-x"
        )
        assert tools == []

    async def test_happy_path_builds_tool_per_kb(self, monkeypatch: pytest.MonkeyPatch) -> None:
        kbs = {
            "kb1": _kb("kb1", "Docs", "internal engineering docs"),
            "kb2": _kb("kb2", "Runbooks"),
        }

        class _StubRepo:
            def __init__(self, conn) -> None:
                pass

            async def get(self, kb_id: str) -> KnowledgeBase:
                return kbs[kb_id]

        monkeypatch.setattr(
            "the_one.db.connection.get_connection", AsyncMock(return_value=object())
        )
        monkeypatch.setattr("the_one.db.repositories.KnowledgeBaseRepository", _StubRepo)

        provider = KBToolProvider()
        tools = await provider.get_tools_for_agent(
            _AgentConfigStub(kb_ids=["kb1", "kb2"]), agent_name="agent-y"
        )
        assert {t.kb_id for t in tools} == {"kb1", "kb2"}
        # DD-17: names are now unconditionally discriminated — assert
        # shape, not a literal hash (a hardcoded discriminated literal
        # would rot the same way an undiscriminated one did).
        names = {t.name for t in tools}
        assert len(names) == 2
        assert names.isdisjoint({"kb__Docs__search", "kb__Runbooks__search"})
        for name in names:
            assert name.startswith(("kb__Docs_", "kb__Runbooks_"))
            assert name.endswith("__search")
        for t in tools:
            assert isinstance(t, KBSearchTool)
            assert t._agent_name == "agent-y"


# ---------------------------------------------------------------------------
# build_description
# ---------------------------------------------------------------------------


class TestBuildDescription:
    def test_names_kb_and_instructs_terse_queries(self) -> None:
        kb = _kb("kb1", "Runbooks")
        desc = build_description(kb)
        assert "Runbooks" in desc
        assert "keyword" in desc.lower()

    def test_carries_kb_description_when_set(self) -> None:
        kb = _kb("kb1", "Runbooks", "internal engineering runbooks and postmortems")
        desc = build_description(kb)
        assert "internal engineering runbooks and postmortems" in desc


# ---------------------------------------------------------------------------
# KBSearchTool
# ---------------------------------------------------------------------------


class TestKBSearchTool:
    def test_name_is_used_verbatim_not_recomputed(self) -> None:
        # AC-2: the tool receives its finished name; it does not compute it.
        tool = KBSearchTool(
            name="kb__Weird Name__search",
            kb_id="kb1",
            kb_name="Weird Name",
            description="d",
            agent_name="a",
        )
        assert tool.name == "kb__Weird Name__search"

    def test_agent_name_threaded_to_base(self) -> None:
        tool = KBSearchTool(
            name="kb__docs__search",
            kb_id="kb1",
            kb_name="Docs",
            description="d",
            agent_name="agent-z",
        )
        assert tool._agent_name == "agent-z"

    def test_parameters_schema_has_query_and_limit(self) -> None:
        tool = KBSearchTool(
            name="kb__docs__search", kb_id="kb1", kb_name="Docs", description="d", agent_name="a"
        )
        props = tool.parameters["properties"]
        assert "query" in props
        assert "limit" in props
        assert tool.parameters["required"] == ["query"]

    async def test_limit_below_range_raises(self) -> None:
        tool = KBSearchTool(
            name="kb__docs__search", kb_id="kb1", kb_name="Docs", description="d", agent_name="a"
        )
        with pytest.raises(ValueError, match="limit"):
            await tool.execute(query="x", limit=0)

    async def test_limit_above_range_raises(self) -> None:
        tool = KBSearchTool(
            name="kb__docs__search", kb_id="kb1", kb_name="Docs", description="d", agent_name="a"
        )
        with pytest.raises(ValueError, match="limit"):
            await tool.execute(query="x", limit=21)

    async def test_limit_wrong_type_raises(self) -> None:
        tool = KBSearchTool(
            name="kb__docs__search", kb_id="kb1", kb_name="Docs", description="d", agent_name="a"
        )
        with pytest.raises(ValueError, match="limit"):
            await tool.execute(query="x", limit="5")  # type: ignore[arg-type]

    async def test_limit_bool_rejected(self) -> None:
        # bool is an int subclass — must not be silently accepted as 0/1.
        tool = KBSearchTool(
            name="kb__docs__search", kb_id="kb1", kb_name="Docs", description="d", agent_name="a"
        )
        with pytest.raises(ValueError, match="limit"):
            await tool.execute(query="x", limit=True)  # type: ignore[arg-type]

    async def test_execute_resolves_dependencies_at_call_time_and_calls_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        marker_conn = object()
        marker_store = object()
        marker_backend = object()
        marker_chunk_repo = object()
        marker_item_repo = object()

        captured: dict = {}

        async def _fake_search(kb_id, query, *, limit, chunk_repo, item_repo, store, backend):
            captured.update(
                kb_id=kb_id,
                query=query,
                limit=limit,
                chunk_repo=chunk_repo,
                item_repo=item_repo,
                store=store,
                backend=backend,
            )
            return SearchResult(hits=[_hit()], degraded=None)

        monkeypatch.setattr(
            "the_one.db.connection.get_connection", AsyncMock(return_value=marker_conn)
        )

        def _fake_chunk_repo(conn: object) -> object:
            assert conn is marker_conn
            return marker_chunk_repo

        def _fake_item_repo(conn: object) -> object:
            assert conn is marker_conn
            return marker_item_repo

        monkeypatch.setattr("the_one.db.repositories.KBChunkRepository", _fake_chunk_repo)
        monkeypatch.setattr("the_one.db.repositories.KBItemRepository", _fake_item_repo)
        monkeypatch.setattr(
            "the_one.vectors.get_vector_store", AsyncMock(return_value=marker_store)
        )
        monkeypatch.setattr("the_one.embeddings.get_embedding_backend", lambda: marker_backend)
        monkeypatch.setattr(tool_mod, "search", _fake_search)

        tool = KBSearchTool(
            name="kb__docs__search",
            kb_id="kb-target",
            kb_name="Docs",
            description="d",
            agent_name="a",
        )
        result = await tool.execute(query="rare term", limit=3)

        assert captured["kb_id"] == "kb-target"
        assert captured["query"] == "rare term"
        assert captured["limit"] == 3
        assert captured["chunk_repo"] is marker_chunk_repo
        assert captured["item_repo"] is marker_item_repo
        assert captured["store"] is marker_store
        assert captured["backend"] is marker_backend
        assert "1 result(s)" in result
        assert "hello world" in result


# ---------------------------------------------------------------------------
# _render_result (DD-8)
# ---------------------------------------------------------------------------


class TestRenderResult:
    def test_header_names_kb_query_and_hit_count(self) -> None:
        result = SearchResult(hits=[_hit(), _hit(chunk_id=2)], degraded=None)
        rendered = tool_mod._render_result("Docs", "rare term", result)
        assert "2 result(s)" in rendered
        assert "Docs" in rendered
        assert "rare term" in rendered

    def test_citation_line_shape(self) -> None:
        hit = _hit(path="notes/a.md", seq=3)
        result = SearchResult(hits=[hit], degraded=None)
        rendered = tool_mod._render_result("Docs", "q", result)
        assert "[1] notes/a.md #3 (0-10)" in rendered
        assert "hello world" in rendered

    def test_no_hits_is_one_sentence_never_empty(self) -> None:
        result = SearchResult(hits=[], degraded=None)
        rendered = tool_mod._render_result("Docs", "nonexistent term", result)
        assert rendered.strip() != ""
        assert "Docs" in rendered
        assert "nonexistent term" in rendered

    @pytest.mark.parametrize(
        "degraded",
        [
            "semantic index rebuilding",
            "semantic index busy",
            "semantic index unavailable",
        ],
    )
    def test_degraded_semantic_side_says_keyword_results(self, degraded: str) -> None:
        result = SearchResult(hits=[_hit()], degraded=degraded)
        rendered = tool_mod._render_result("Docs", "q", result)
        assert degraded in rendered
        assert "keyword-only" in rendered
        assert "semantic-only" not in rendered

    def test_degraded_keyword_side_says_semantic_results(self) -> None:
        result = SearchResult(hits=[_hit()], degraded="keyword index unavailable")
        rendered = tool_mod._render_result("Docs", "q", result)
        assert "keyword index unavailable" in rendered
        assert "semantic-only" in rendered
        assert "keyword-only" not in rendered

    def test_degraded_line_appears_above_hits(self) -> None:
        result = SearchResult(hits=[_hit()], degraded="semantic index busy")
        rendered = tool_mod._render_result("Docs", "q", result)
        degraded_pos = rendered.index("semantic index busy")
        header_pos = rendered.index("result(s)")
        assert degraded_pos < header_pos
