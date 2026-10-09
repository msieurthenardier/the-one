"""Tests for ``the_one/knowledge/kb_rename.py`` (Mission 24, Flight 6, Leg 2).

Covers :func:`rename_kb_tool_references`'s agent-rewrite mechanics
(L2-D7 step 3) directly, against a real ``SQLiteAgentStore`` — the seam
``SQLiteAgentStore.list_by_kb`` exists to provide.
"""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.repositories import SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.knowledge.kb_rename import rename_kb_tool_references


@pytest.fixture
async def conn(tmp_path):

    db_path = tmp_path / "test.db"
    connection = await connect_template_db(db_path)
    yield connection
    await connection.close()


@pytest.fixture
def agent_store(conn, tmp_path):
    key = Fernet.generate_key()
    encryptor = Encryptor(key, key_path=tmp_path / "agent_store.key")
    return SQLiteAgentStore(conn, encryptor)


class TestRenameKbToolReferences:
    async def test_rewrites_matching_entry_across_attached_agents(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        await agent_store.save(
            AgentConfig(
                name="a1",
                kb_ids=["kb1"],
                disabled_tools=["kb__Docs_old__search", "shell"],
            )
        )
        await agent_store.save(
            AgentConfig(
                name="a2",
                kb_ids=["kb1"],
                disabled_tools=["kb__Docs_old__search"],
            )
        )
        failed = await rename_kb_tool_references(
            agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
        )
        assert failed == []
        a1 = await agent_store.load("a1")
        assert a1.disabled_tools == ["kb__Docs_new__search", "shell"]
        a2 = await agent_store.load("a2")
        assert a2.disabled_tools == ["kb__Docs_new__search"]

    async def test_agent_with_no_matching_entry_is_not_resaved(
        self, agent_store: SQLiteAgentStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await agent_store.save(
            AgentConfig(name="untouched", kb_ids=["kb1"], disabled_tools=["shell"])
        )

        save_calls: list[str] = []
        real_save = agent_store.save

        async def _tracked_save(cfg):
            save_calls.append(cfg.name)
            await real_save(cfg)

        monkeypatch.setattr(agent_store, "save", _tracked_save)

        failed = await rename_kb_tool_references(
            agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
        )
        assert failed == []
        # AC-8: no matching entry -> not re-saved at all, not just
        # "saved with the same value".
        assert save_calls == []
        loaded_after = await agent_store.load("untouched")
        assert loaded_after.disabled_tools == ["shell"]

    async def test_agent_with_empty_or_null_disabled_tools_not_resaved_or_errored(
        self, agent_store: SQLiteAgentStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await agent_store.save(AgentConfig(name="empty-dt", kb_ids=["kb1"], disabled_tools=[]))

        save_calls: list[str] = []
        real_save = agent_store.save

        async def _tracked_save(cfg):
            save_calls.append(cfg.name)
            await real_save(cfg)

        monkeypatch.setattr(agent_store, "save", _tracked_save)

        failed = await rename_kb_tool_references(
            agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
        )
        assert failed == []
        assert save_calls == []
        assert (await agent_store.load("empty-dt")).disabled_tools == []

    async def test_duplicate_matching_entries_are_deduplicated(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        await agent_store.save(
            AgentConfig(
                name="dupe",
                kb_ids=["kb1"],
                disabled_tools=["kb__Docs_old__search", "kb__Docs_old__search", "shell"],
            )
        )
        failed = await rename_kb_tool_references(
            agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
        )
        assert failed == []
        loaded = await agent_store.load("dupe")
        assert loaded.disabled_tools == ["kb__Docs_new__search", "shell"]

    async def test_unattached_agent_is_never_considered(
        self, agent_store: SQLiteAgentStore
    ) -> None:
        # Attached to a DIFFERENT kb, but happens to carry the same
        # disabled_tools literal — list_by_kb must exclude it.
        await agent_store.save(
            AgentConfig(
                name="other-kb-agent",
                kb_ids=["kb-other"],
                disabled_tools=["kb__Docs_old__search"],
            )
        )
        failed = await rename_kb_tool_references(
            agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
        )
        assert failed == []
        loaded = await agent_store.load("other-kb-agent")
        assert loaded.disabled_tools == ["kb__Docs_old__search"]

    async def test_one_agent_failure_does_not_block_the_rest(
        self,
        agent_store: SQLiteAgentStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # AC-12: a plain for-loop would let one agent's save() failure
        # propagate and abort the rest. Force the FIRST agent's save to
        # raise; the second must still be rewritten, and the failure
        # returned + logged rather than raised.
        await agent_store.save(
            AgentConfig(name="a-fails", kb_ids=["kb1"], disabled_tools=["kb__Docs_old__search"])
        )
        await agent_store.save(
            AgentConfig(name="b-ok", kb_ids=["kb1"], disabled_tools=["kb__Docs_old__search"])
        )

        real_save = agent_store.save

        async def _flaky_save(cfg):
            if cfg.name == "a-fails":
                raise RuntimeError("boom")
            await real_save(cfg)

        monkeypatch.setattr(agent_store, "save", _flaky_save)

        with caplog.at_level(logging.WARNING):
            failed = await rename_kb_tool_references(
                agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
            )
        assert failed == ["a-fails"]
        assert any("a-fails" in r.message for r in caplog.records)

        # b-ok still got rewritten despite a-fails' failure.
        monkeypatch.setattr(agent_store, "save", real_save)
        loaded_b = await agent_store.load("b-ok")
        assert loaded_b.disabled_tools == ["kb__Docs_new__search"]

    async def test_no_attached_agents_returns_empty(self, agent_store: SQLiteAgentStore) -> None:
        failed = await rename_kb_tool_references(
            agent_store, "kb-nobody", "kb__X_old__search", "kb__X_new__search"
        )
        assert failed == []

    async def test_enumeration_failure_does_not_raise_and_warns(
        self,
        agent_store: SQLiteAgentStore,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Phase 2d review fix: `store.list_by_kb` runs before the per-agent
        # try/except (AC-12) even starts, so a failure there used to
        # propagate unhandled past this function — after the knowledge-base
        # row had already been renamed by the caller. It must instead log
        # a WARNING and return without raising, same as a per-agent
        # failure does.
        await agent_store.save(
            AgentConfig(
                name="a1",
                kb_ids=["kb1"],
                disabled_tools=["kb__Docs_old__search"],
            )
        )

        async def _flaky_list_by_kb(kb_id):
            raise RuntimeError("boom")

        monkeypatch.setattr(agent_store, "list_by_kb", _flaky_list_by_kb)

        with caplog.at_level(logging.WARNING):
            failed = await rename_kb_tool_references(
                agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
            )
        assert failed == []
        assert any("kb1" in r.message and "enumerate" in r.message for r in caplog.records)

        # The caller is unaffected: nothing else raised, and the agent's
        # disabled_tools entry is untouched since it was never examined
        # (load() is unpatched, so this reads the real stored value).
        loaded = await agent_store.load("a1")
        assert loaded.disabled_tools == ["kb__Docs_old__search"]

    async def test_enabled_tools_is_never_touched(self, agent_store: SQLiteAgentStore) -> None:
        # AC-9: a `kb__` name placed in enabled_tools is inert and must
        # survive a rename untouched.
        await agent_store.save(
            AgentConfig(
                name="enabled-agent",
                kb_ids=["kb1"],
                disabled_tools=["kb__Docs_old__search"],
                enabled_tools=["kb__Docs_old__search", "shell"],
            )
        )
        failed = await rename_kb_tool_references(
            agent_store, "kb1", "kb__Docs_old__search", "kb__Docs_new__search"
        )
        assert failed == []
        loaded = await agent_store.load("enabled-agent")
        assert loaded.enabled_tools == ["kb__Docs_old__search", "shell"]
        assert loaded.disabled_tools == ["kb__Docs_new__search"]
