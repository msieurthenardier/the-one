"""Tests for F6 L1 operator-disable enforcement at the AgentFactory boundary.

L1 widens `AgentFactory.create()` to read `ToolConfigRepository.list()`
(full models with the L0 `enabled` flag) and project two derived
structures: `tool_configs_by_name: dict[str, dict]` for the resolver
path AND `disabled_names: set[str]` for the registry-build filter.

Disabled tools are filtered out of the registry independently of the
per-agent `enabled_tools` / `disabled_tools` whitelist.

The introspection path (`BuiltinToolProvider.get_tools()` with no args)
is NOT modified — `GET /api/tools` continues to list all tools regardless
of disable state. Enforcement is factory-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import KnowledgeBase, LLMProviderConfig
from the_one.db.repositories import KnowledgeBaseRepository, ToolConfigRepository
from the_one.db.schema import ensure_schema
from the_one.tools.base import Tool


class InMemoryStore:
    """Minimal async store backed by a dict."""

    def __init__(self) -> None:
        self._data: dict[str, AgentConfig] = {}

    async def list_agents(self) -> list[str]:
        return sorted(self._data.keys())

    async def load(self, name: str) -> AgentConfig:
        if name not in self._data:
            raise KeyError(f"Agent config not found: {name}")
        return self._data[name]

    async def save(self, config: AgentConfig) -> None:
        self._data[config.name] = config

    async def exists(self, name: str) -> bool:
        return name in self._data


class StubProvider:
    """Returns a fixed set of tools mirroring builtin tool names."""

    @property
    def name(self) -> str:
        return "stub"

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
        agent_name: str | None = None,
    ) -> list[Tool]:
        from conftest import StubTool

        return [
            StubTool("web_search", agent_name=agent_name),
            StubTool("fetch_url", agent_name=agent_name),
            StubTool("shell", agent_name=agent_name),
        ]


class StubProviderWithKbTool(StubProvider):
    """Same fixed built-in set, plus one `kb__`-prefixed name — stands in
    for a registered knowledge-base tool (Flight 5 Leg 2 builds the real
    `KBToolProvider`; this factory-composition test only needs a name with
    the right prefix reaching `is_tool_enabled`'s gate)."""

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
        agent_name: str | None = None,
    ) -> list[Tool]:
        from conftest import StubTool

        return [
            *super().get_tools(tool_configs, agent_overrides, agent_name),
            StubTool("kb__docs__search", agent_name=agent_name),
        ]


def _fake_get_provider(name: str, **kwargs: Any) -> Any:
    from conftest import FakeLLM

    return FakeLLM(responses=[])


def _make_provider_config() -> LLMProviderConfig:
    return LLMProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="ollama",
        base_url="http://localhost:11434/v1",
    )


@pytest.fixture
async def db_conn(tmp_path):
    """Open a fresh isolated SQLite DB with the v9 schema applied."""
    conn = await aiosqlite.connect(str(tmp_path / "test.db"))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    yield conn
    await conn.close()


@pytest.fixture
def tool_encryptor(tmp_path):
    """Real Fernet-backed Encryptor for the tool-config repo (M16 F08 L03).

    Shared by both the seed-side `ToolConfigRepository(db_conn, ...)`
    constructions and the patched `get_encryptor` the factory consumes,
    so encrypt-on-write / decrypt-on-read round-trips under one key.
    """
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    return Encryptor(Fernet.generate_key(), key_path=tmp_path / "tool_config.key")


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def _patch_block(conn, mock_provider_repo, real_tool_repo: ToolConfigRepository):
    """Patch the factory's DB/provider/encryptor wiring; route the real
    `ToolConfigRepository(conn)` construction to the supplied repo so we
    exercise the actual `list()` call against the in-memory DB."""
    return patch.multiple(
        "the_one.agent.factory",
        get_provider=_fake_get_provider,
        settings=MagicMock(
            agents_dir=Path("/tmp/test-agents"),
            data_dir=Path("/tmp/test-data"),
            ensure_dirs=lambda: None,
        ),
    )


async def _build_factory(
    conn,
    store: InMemoryStore,
    cfg: AgentConfig,
    provider: StubProvider,
    encryptor=None,
):
    await store.save(cfg)
    mock_provider_repo = AsyncMock()
    mock_provider_repo.get = AsyncMock(return_value=_make_provider_config())

    with (
        patch("the_one.agent.factory.get_provider", _fake_get_provider),
        patch("the_one.agent.factory.settings") as mock_settings,
        patch(
            "the_one.db.connection.get_connection",
            new_callable=AsyncMock,
            return_value=conn,
        ),
        patch("the_one.encryption.get_encryptor", return_value=encryptor or AsyncMock()),
        patch(
            "the_one.db.repositories.LLMProviderRepository",
            return_value=mock_provider_repo,
        ),
    ):
        mock_settings.agents_dir = Path("/tmp/test-agents")
        mock_settings.data_dir = Path("/tmp/test-data")
        mock_settings.ensure_dirs = lambda: None

        factory = AgentFactory(store=store, tool_providers=[provider])
        agent = await factory.create(cfg.name)
    return agent


class TestDisableEnforcement:
    async def test_disabled_tool_excluded_from_registry(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """Operator disables `web_search`; factory registry omits it."""
        repo = ToolConfigRepository(db_conn, tool_encryptor)
        await repo.upsert("web_search", {}, enabled=False)

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        names = agent.tools.tool_names
        assert "web_search" not in names
        assert "fetch_url" in names
        assert "shell" in names

    async def test_disabled_tool_independent_of_per_agent_whitelist(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """Operator disable wins even if the agent's `enabled_tools`
        whitelist names the tool."""
        repo = ToolConfigRepository(db_conn, tool_encryptor)
        await repo.upsert("web_search", {}, enabled=False)

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            enabled_tools=["web_search", "fetch_url"],
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        assert "web_search" not in agent.tools.tool_names
        assert "fetch_url" in agent.tools.tool_names

    async def test_re_enabling_restores_tool_to_registry(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """Disable, then re-enable; the registry contains the tool again."""
        repo = ToolConfigRepository(db_conn, tool_encryptor)
        await repo.upsert("web_search", {}, enabled=False)
        await repo.upsert("web_search", {}, enabled=True)

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        assert "web_search" in agent.tools.tool_names

    async def test_per_agent_disable_independent_of_operator_disable(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """Operator-enabled, agent-disabled (via `disabled_tools`); the
        tool is still absent. Confirms the two filters are independent."""
        # No DB row → operator default (enabled=True).
        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            disabled_tools=["web_search"],
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        assert "web_search" not in agent.tools.tool_names
        assert "fetch_url" in agent.tools.tool_names

    async def test_factory_feeds_real_secret_to_search_backend(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """KEYSTONE (M16 F08 L03): a saved `web_search` config with a real
        encrypted `brave_api_key` reaches `build_search_backend` THROUGH THE
        FACTORY path with the REAL key — not masked, not missing.

        Exercises `AgentFactory.create()` → `repo.list()` →
        `merged_config()` → `BuiltinToolProvider.get_tools` → `resolve` →
        `build_search_backend`. NOT a direct `list_all()` call (that method
        has no production consumer)."""
        from the_one.tools._search_backends import SearchBackend
        from the_one.tools.builtins import BuiltinToolProvider

        repo = ToolConfigRepository(db_conn, tool_encryptor)
        await repo.upsert(
            "web_search",
            {"search_backend": "brave"},
            secrets={"brave_api_key": "BRAVE-REAL-FACTORY-KEY"},
        )

        cfg = AgentConfig(
            name="agent-search",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        agent = await _build_factory(db_conn, store, cfg, BuiltinToolProvider(), tool_encryptor)

        # Pull the real WebSearchTool out of the built registry and read the
        # backend the factory injected.
        web_search = agent.tools.get("web_search")
        backend = web_search._cross_configs[SearchBackend]
        # BraveSearchBackend stores the key on `_api_key` (stripped).
        assert getattr(backend, "_api_key", None) == "BRAVE-REAL-FACTORY-KEY", (
            "factory must feed the REAL decrypted brave_api_key to "
            f"build_search_backend; got backend={backend!r}"
        )

    async def test_narrowed_builtin_whitelist_keeps_kb_tool(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """Flight 5 Leg 1, DD-6: a built-ins-only `enabled_tools` whitelist
        (no `kb__` name in it, as the agent editor emits) must not strip a
        registered knowledge-base tool at the factory composition level —
        the regression `UNGATED_TOOL_PREFIXES` exists to prevent."""
        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            enabled_tools=["web_search"],
        )
        agent = await _build_factory(db_conn, store, cfg, StubProviderWithKbTool(), tool_encryptor)
        names = agent.tools.tool_names
        assert "kb__docs__search" in names
        assert "web_search" in names
        assert "fetch_url" not in names

    async def test_factory_does_not_call_list_all(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """Light regression net: the L1 projection switches the factory's
        repo call from `list_all()` to `list()`. Spy on the repository
        and verify `list_all` is never invoked on the factory path."""
        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        await store.save(cfg)
        mock_provider_repo = AsyncMock()
        mock_provider_repo.get = AsyncMock(return_value=_make_provider_config())

        # Build a wrapper repo that delegates to the real one but tracks
        # whether `list_all` was called.
        real_repo = ToolConfigRepository(db_conn, tool_encryptor)
        list_all_calls = 0
        list_calls = 0

        original_list_all = real_repo.list_all
        original_list = real_repo.list

        async def tracked_list_all() -> dict[str, dict]:
            nonlocal list_all_calls
            list_all_calls += 1
            return await original_list_all()

        async def tracked_list():
            nonlocal list_calls
            list_calls += 1
            return await original_list()

        real_repo.list_all = tracked_list_all  # type: ignore[assignment]
        real_repo.list = tracked_list  # type: ignore[assignment]

        with (
            patch("the_one.agent.factory.get_provider", _fake_get_provider),
            patch("the_one.agent.factory.settings") as mock_settings,
            patch(
                "the_one.db.connection.get_connection",
                new_callable=AsyncMock,
                return_value=db_conn,
            ),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch(
                "the_one.db.repositories.LLMProviderRepository",
                return_value=mock_provider_repo,
            ),
            patch(
                "the_one.db.repositories.ToolConfigRepository",
                return_value=real_repo,
            ),
        ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None

            factory = AgentFactory(store=store, tool_providers=[StubProvider()])
            await factory.create(cfg.name)

        assert list_all_calls == 0, "factory must not call repo.list_all() in L1+"
        assert list_calls == 1, "factory must call repo.list() exactly once"


class TestKbToolStaleDisableReconcile:
    """M24 F07 L01, DD-13 (AC-11–AC-17): the detach -> rename -> reattach
    hole. Uses the REAL ``KBToolProvider`` (the default when
    ``AgentFactory`` is built with no ``kb_provider`` kwarg) against
    ``db_conn`` — a real SQLite connection with the real schema, patched
    in as the factory's ``the_one.db.connection.get_connection`` result
    exactly as ``_build_factory`` already does for every other test in
    this module. ``StubProviderWithKbTool`` (used elsewhere in this file)
    is deliberately NOT used here: its docstring says it "stands in" for
    a real provider and it returns a FIXED tool name, so it cannot
    reproduce a rename and cannot falsify the reconcile (leg
    Implementation Guidance step 9)."""

    async def test_disabled_kb_tool_survives_detach_rename_reattach(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        kb_repo = KnowledgeBaseRepository(db_conn)
        await kb_repo.create(KnowledgeBase(id="kb1", name="Original Name"))

        # 1. Attached, undisabled: build once to learn the CURRENT derived
        # tool name.
        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            kb_ids=["kb1"],
        )
        agent_v1 = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        names_v1 = [n for n in agent_v1.tools.tool_names if n.startswith("kb__")]
        assert len(names_v1) == 1
        tool_name_v1 = names_v1[0]

        # 2. Operator disables it by its current name. Sanity: it's gone.
        cfg = cfg.model_copy(update={"disabled_tools": [tool_name_v1]})
        agent_disabled = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        assert tool_name_v1 not in agent_disabled.tools.tool_names

        # 3. Detach. kb_rename.py's write-side rewrite only reaches
        # CURRENTLY ATTACHED agents (SQLiteAgentStore.list_by_kb), so a
        # rename that happens now is invisible to it — this is precisely
        # the case the read-side reconcile exists for.
        cfg = cfg.model_copy(update={"kb_ids": []})
        await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)

        # 4. Rename the knowledge base while detached.
        renamed = await kb_repo.get("kb1")
        renamed.name = "Renamed Knowledge Base"
        await kb_repo.update(renamed)

        # Compute what the tool's name WOULD be post-rename, independent
        # of the factory/registry — the reconciled tool is expected to be
        # excluded from the registry entirely, so its name cannot be read
        # back off `agent.tools.tool_names` (that's the whole point).
        from the_one.knowledge.tool_provider import compute_tool_names

        tool_name_v2 = compute_tool_names([renamed], agent_name="agent-a")["kb1"]

        # The rename actually changed the derived name (same kb_id, same
        # discriminator, different slug) — otherwise this test would prove
        # nothing.
        assert tool_name_v2 != tool_name_v1

        # 5. Reattach. `disabled_tools` still carries the STALE v1 name —
        # nothing rewrote it, since the agent was detached at rename time.
        cfg = cfg.model_copy(update={"kb_ids": ["kb1"]})
        agent_v2 = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)

        # AC-16: the operator's disable survives even though the literal
        # disabled_tools entry (tool_name_v1) does not match the tool's
        # current name (tool_name_v2) — the reconciled tool is excluded
        # from the registry altogether (no kb__ tool at all, since it's
        # the agent's only attached knowledge base).
        names_v2 = [n for n in agent_v2.tools.tool_names if n.startswith("kb__")]
        assert names_v2 == []
        assert tool_name_v2 not in agent_v2.tools.tool_names

        # AC-15: the reconcile never wrote back to the stored config.
        stored = await store.load("agent-a")
        assert stored.disabled_tools == [tool_name_v1]

    async def test_reconcile_does_not_disable_a_different_kb(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """AC-14: a disabled_tools entry carrying a discriminator for a
        DIFFERENT kb_id must not disable this tool."""
        kb_repo = KnowledgeBaseRepository(db_conn)
        await kb_repo.create(KnowledgeBase(id="kb-other", name="Other"))
        await kb_repo.create(KnowledgeBase(id="kb-target", name="Target"))

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            kb_ids=["kb-other"],
        )
        agent_other = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        [other_name] = [n for n in agent_other.tools.tool_names if n.startswith("kb__")]

        # Attach ONLY kb-target, but disabled_tools still names kb-other's
        # (unrelated) tool.
        cfg = cfg.model_copy(update={"kb_ids": ["kb-target"], "disabled_tools": [other_name]})
        agent_target = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        [target_name] = [n for n in agent_target.tools.tool_names if n.startswith("kb__")]
        assert target_name in agent_target.tools.tool_names

    async def test_reconcile_ignores_entries_that_are_not_kb_tool_names(
        self, db_conn, store: InMemoryStore, tool_encryptor
    ) -> None:
        """A `disabled_tools` entry with no `kb__…__search` shape must not
        false-positive against an attached kb tool's discriminator."""
        kb_repo = KnowledgeBaseRepository(db_conn)
        await kb_repo.create(KnowledgeBase(id="kb1", name="Docs"))

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            kb_ids=["kb1"],
            disabled_tools=["shell", "web_search"],
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider(), tool_encryptor)
        assert any(n.startswith("kb__") for n in agent.tools.tool_names)


class TestKbToolIsDisabledHelper:
    """Pure-function coverage of ``_kb_tool_is_disabled`` (DD-13) — AC-11
    through AC-15 — independent of the full factory/DB machinery the
    end-to-end reconcile tests above exercise."""

    def test_current_name_entry_still_disables(self) -> None:
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _discriminator

        name = f"kb__docs_{_discriminator('kb1', 8)}__search"
        tool = SimpleNamespace(name=name, kb_id="kb1")
        assert _kb_tool_is_disabled(tool, [name]) is True

    def test_stale_slug_with_matching_discriminator_still_disables(self) -> None:
        """AC-11: a stale entry whose slug does not match the tool's
        CURRENT name still disables it, as long as the discriminator
        derives from this tool's kb_id."""
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _discriminator

        disc = _discriminator("kb1", 8)
        stale_entry = f"kb__Old_Name_{disc}__search"
        tool = SimpleNamespace(name=f"kb__New_Name_{disc}__search", kb_id="kb1")
        assert _kb_tool_is_disabled(tool, [stale_entry]) is True

    def test_different_kb_id_discriminator_does_not_disable(self) -> None:
        """AC-14: an entry carrying a discriminator for a DIFFERENT kb_id
        must not disable this tool."""
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _discriminator

        other_disc = _discriminator("kb-other", 8)
        entry = f"kb__Whatever_{other_disc}__search"
        target_disc = _discriminator("kb-target", 8)
        tool = SimpleNamespace(name=f"kb__Target_{target_disc}__search", kb_id="kb-target")
        assert _kb_tool_is_disabled(tool, [entry]) is False

    def test_widened_discriminator_lengths_are_all_tried(self) -> None:
        """AC-12: the match is attempted for every L in _HASH_LENGTHS
        (8, 12, 16), not a fixed width."""
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _HASH_LENGTHS, _discriminator

        for hash_len in _HASH_LENGTHS:
            disc = _discriminator("kb1", hash_len)
            entry = f"kb__Whatever_Slug_{disc}__search"
            tool = SimpleNamespace(name="kb__current__search", kb_id="kb1")
            assert _kb_tool_is_disabled(tool, [entry]) is True, f"failed at hash_len={hash_len}"

    def test_slug_containing_underscores_does_not_break_matching(self) -> None:
        """AC-13: the match never splits on slug position — a slug
        containing "_" and "__" must still reconcile correctly."""
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _discriminator

        disc = _discriminator("kb1", 8)
        slug = "My__Weird_Notes"
        stale_entry = f"kb__{slug}_{disc}__search"
        tool = SimpleNamespace(name=f"kb__Renamed__Again_{disc}__search", kb_id="kb1")
        assert _kb_tool_is_disabled(tool, [stale_entry]) is True

    def test_non_kb_shaped_entry_never_matches(self) -> None:
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _discriminator

        name = f"kb__docs_{_discriminator('kb1', 8)}__search"
        tool = SimpleNamespace(name=name, kb_id="kb1")
        assert _kb_tool_is_disabled(tool, ["shell", "web_search"]) is False

    def test_disabled_tools_list_is_not_mutated(self) -> None:
        """AC-15: the helper never writes to the ``disabled_tools`` list
        it is given."""
        from types import SimpleNamespace

        from the_one.agent.factory import _kb_tool_is_disabled
        from the_one.knowledge.tool_provider import _discriminator

        disc = _discriminator("kb1", 8)
        stale_entry = f"kb__Old_{disc}__search"
        disabled = [stale_entry]
        original = list(disabled)
        tool = SimpleNamespace(name=f"kb__New_{disc}__search", kb_id="kb1")

        _kb_tool_is_disabled(tool, disabled)

        assert disabled == original
