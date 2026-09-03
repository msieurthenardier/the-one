"""Tests for ``FindPlatformDestinationTool`` — DD-5's lookup-tool contract
(query matching, literal-key candidate translation, connector-name
enrichment, zero-match/empty-query messaging) and the connector-level
read-authorization scoping exercised THROUGH the tool. Mission 23 Flight 4
Leg 3.
"""

from __future__ import annotations

import json

import pytest

from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import Connector
from the_one.db.repositories import ConnectorDirectoryRepository, ConnectorRepository
from the_one.encryption import get_encryptor
from the_one.tools.connector_lookup import FindPlatformDestinationTool


@pytest.fixture
async def conn_repo(isolated_db) -> ConnectorRepository:
    conn = await get_connection()
    return ConnectorRepository(conn, get_encryptor(settings.data_dir))


@pytest.fixture
async def dir_repo(isolated_db) -> ConnectorDirectoryRepository:
    conn = await get_connection()
    return ConnectorDirectoryRepository(conn)


def _tool(agent_name: str) -> FindPlatformDestinationTool:
    return FindPlatformDestinationTool(agent_name=agent_name)


class TestToolContract:
    """AC-1: query matching, bounding/ordering, zero-match messaging,
    literal-key candidate translation, connector-name inclusion."""

    async def test_query_matches_display_name_or_username_case_insensitive(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Marisol Vega",
            username=None,
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p2",
            thread_id=None,
            display_name="Bob",
            username="marisolfan",
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p3",
            thread_id=None,
            display_name="Carl",
            username=None,
        )
        result = await _tool("bot-1").execute(query="mariSOL")
        candidates = json.loads(result)
        assert {c["display_name"] for c in candidates} == {"Marisol Vega", "Bob"}

    async def test_username_only_match(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Totally Different Name",
            username="zephyrine99",
        )
        result = await _tool("bot-1").execute(query="zephyrine")
        [candidate] = json.loads(result)
        assert candidate["username"] == "zephyrine99"

    async def test_bounded_to_ten_newest_first(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        for i in range(12):
            await dir_repo.upsert(
                connector_id="c1",
                kind="peer",
                platform_id=f"p{i}",
                thread_id=None,
                display_name=f"Match {i}",
                username=None,
            )
        result = await _tool("bot-1").execute(query="match")
        candidates = json.loads(result)
        assert len(candidates) == 10
        assert {c["peer_id"] for c in candidates} == {f"p{i}" for i in range(2, 12)}

    async def test_zero_match_message_names_the_query(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        result = await _tool("bot-1").execute(query="nobody-like-this")
        assert "nobody-like-this" in result
        # A zero-match message is NOT an error path — a clear informational
        # string naming the query, not an ``[error] ...``-prefixed refusal.
        assert not result.startswith("[error]")
        with pytest.raises(json.JSONDecodeError):
            json.loads(result)

    async def test_peer_candidate_carries_peer_id_never_channel_keys(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        [candidate] = json.loads(result)
        assert candidate["kind"] == "peer"
        assert candidate["peer_id"] == "p1"
        assert "channel_id" not in candidate
        assert "thread_id" not in candidate
        assert "platform_id" not in candidate

    async def test_channel_candidate_carries_channel_id_and_thread_id_never_peer_id(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="channel",
            platform_id="ch1",
            thread_id="th1",
            display_name="Match Channel",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        [candidate] = json.loads(result)
        assert candidate["kind"] == "channel"
        assert candidate["channel_id"] == "ch1"
        assert candidate["thread_id"] == "th1"
        assert "peer_id" not in candidate
        assert "platform_id" not in candidate

    async def test_connector_name_included(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops Bot", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        [candidate] = json.loads(result)
        assert candidate["connector_name"] == "Ops Bot"

    async def test_query_matching_peer_and_channel_returns_both_shapes(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        """Edge case: a query matching both a peer and a channel on the
        same connector returns both candidates with their distinct key
        shapes."""
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match Peer",
            username=None,
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="channel",
            platform_id="ch1",
            thread_id=None,
            display_name="Match Channel",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        candidates = json.loads(result)
        by_kind = {c["kind"]: c for c in candidates}
        assert "peer_id" in by_kind["peer"] and "channel_id" not in by_kind["peer"]
        assert "channel_id" in by_kind["channel"] and "peer_id" not in by_kind["channel"]

    async def test_duplicate_display_name_across_connectors_disambiguated_by_connector_name(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Connector One", type="stub", config={"default_agent": "bot-1"})
        )
        await conn_repo.create(
            Connector(id="c2", name="Connector Two", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        await dir_repo.upsert(
            connector_id="c2",
            kind="peer",
            platform_id="p2",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        candidates = json.loads(result)
        assert {c["connector_name"] for c in candidates} == {"Connector One", "Connector Two"}

    async def test_empty_query_is_a_clear_error_not_a_full_table_dump(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Anyone",
            username=None,
        )
        result = await _tool("bot-1").execute(query="   ")
        assert result.startswith("[error]")

    async def test_missing_query_is_a_clear_error(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        result = await _tool("bot-1").execute()
        assert result.startswith("[error]")

    async def test_serialization_is_one_compact_json_array(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        assert result.startswith("[") and result.endswith("]")
        assert "\n" not in result
        parsed = json.loads(result)
        assert isinstance(parsed, list)


class TestScoping:
    """AC-2: DD-5's connector-level read-authorization scoping, exercised
    THROUGH the tool (not just at the repository layer, which leg 1
    already covers)."""

    async def test_channel_map_only_caller_sees_connectors_other_rows(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(
                id="c1",
                name="Ops",
                type="stub",
                config={"default_agent": "someone-else", "channel_map": {"ch-mapped": "bot-1"}},
            )
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        result = await _tool("bot-1").execute(query="match")
        candidates = json.loads(result)
        assert len(candidates) == 1
        assert candidates[0]["peer_id"] == "p1"

    async def test_unbound_agent_gets_empty_result_not_error(
        self, conn_repo: ConnectorRepository, dir_repo: ConnectorDirectoryRepository
    ) -> None:
        await conn_repo.create(
            Connector(id="c1", name="Ops", type="stub", config={"default_agent": "bot-1"})
        )
        await dir_repo.upsert(
            connector_id="c1",
            kind="peer",
            platform_id="p1",
            thread_id=None,
            display_name="Match",
            username=None,
        )
        result = await _tool("unbound-agent").execute(query="match")
        assert not result.startswith("[error]")
        assert "match" in result.lower()


class TestSchemaAndDescription:
    """AC-3: target-compatibility + connector_id-omission guidance in the
    description; ``required`` is a prefix of declared property order
    (the global ``test_tool_base.py`` invariant already covers every
    built-in via ``_TOOL_CLASSES`` — these tests pin the specific content
    this leg's AC-3 requires)."""

    def test_description_documents_target_compatibility_and_connector_id_omission(self) -> None:
        description = FindPlatformDestinationTool.description
        assert "send_to_platform_channel" in description
        assert "connector_id" in description
        assert "omit" in description.lower()

    def test_required_is_prefix_of_declared_properties(self) -> None:
        properties = list(FindPlatformDestinationTool.parameters["properties"])
        required = FindPlatformDestinationTool.parameters["required"]
        assert properties[: len(required)] == required
