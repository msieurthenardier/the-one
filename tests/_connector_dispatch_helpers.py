"""Shared test helpers for connector-dispatch e2e tests.

Mission 10 Flight 4 Leg 5 (F3 debrief carry-forward — the THIRD consumer
trigger). Extracts the previously-duplicated helpers from
``tests/test_connectors_inbound.py`` (F3 L4) and
``tests/test_connectors_e2e_session.py`` (F3 L6) into a single module so
the new ``tests/test_connectors_e2e_platform_send.py`` (F4 L5) can reuse
them without copy-paste.

Exports
-------

The ``isolated_db`` pytest fixture lives in ``tests/conftest.py`` (NOT
this module) because pytest only auto-discovers fixtures from conftest.
This module exports only helper FUNCTIONS that consumer test files
import explicitly.

- :func:`_seed_provider_and_agent` — creates a ``mock``-typed LLM provider
  and an agent config seeded against the per-test DB. Accepts
  ``connector_account_ids`` (F4 L1 widening); the F4 L5 v17 migration
  persists this list to the new ``agents.connector_account_ids`` column,
  so the kwarg flows through to the DB without a monkeypatch.
- :func:`_seed_stub_account` — persists a stub-typed
  :class:`ConnectorAccount` via the repository; accepts
  ``session_continuation_seconds`` override (F3 L6 needs this).
- :func:`_make_factory` — builds an :class:`AgentFactory` whose
  ``store`` reads from the per-test DB; ``mcp_provider=None`` disables
  MCP wiring during agent build.
- :func:`_envelope` — builds an :class:`InboundEnvelope` with sensible
  defaults.
- :class:`_ScriptedProvider` — stateful test-only LLM provider that
  returns pre-scripted ``Message`` instances in sequence (one per
  ``complete()`` call). Used by F4 L4 visibility-tagging tests and F4
  L5 e2e tests that drive the agent's tool-loop end-to-end.
- :func:`_make_scripted_factory` — builds an :class:`AgentFactory` wired
  to a :class:`_ScriptedProvider`. After the F4 L5 v17 migration, the
  ``connector_account_ids`` kwarg flows through real persistence — no
  ``_row_to_config`` monkeypatch needed.

Autouse cleanup (``_reset_stub_state``, ``_clear_pool_locks_registry``)
remains per-file. The cleanup fixtures are autouse-scoped to the
consumer module so they fire for every test in that file but do NOT
need to be exported from this helper module — the leg-design decision
documented in the F3 debrief was that exporting an autouse fixture from
a non-conftest module creates ordering surprises.
"""

from __future__ import annotations

from typing import Any

import pytest

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.connectors.base import InboundEnvelope
from the_one.db.connection import get_connection
from the_one.db.models import ConnectorAccount, LLMProviderConfig
from the_one.db.repositories import (
    ConnectorAccountRepository,
    LLMProviderRepository,
    SQLiteAgentStore,
)
from the_one.encryption import get_encryptor
from the_one.llm.base import LLMProvider, Message

# ─── Seed helpers ────────────────────────────────────────────────────────


async def _seed_provider_and_agent(
    *,
    agent_name: str = "agent-inbound",
    provider_id: str = "mock-provider",
    response_content: str = "ok",
    connector_account_ids: list[str] | None = None,
) -> None:
    """Seed an LLM provider + agent config so ``AgentFactory.create()``
    has something to build against. Uses ``type='mock'`` so the LLM
    registry resolves to :class:`the_one.llm.mock.MockProvider`.

    ``connector_account_ids`` opts the agent into the F4 L3 connector
    carve-out (loads ``send_to_platform_channel`` into the baseline-
    visible tool set + injects the connector-aware system-prompt
    directive). F4 L5 v17 migration persists this list; ``factory.create``
    now sees it on every invocation without a monkeypatch.
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)

    provider_repo = LLMProviderRepository(conn, encryptor)
    await provider_repo.create(
        LLMProviderConfig(
            id=provider_id,
            name="Mock Provider",
            type="mock",
            base_url="",
            config={"response": {"content": response_content}},
        )
    )

    agent_store = SQLiteAgentStore(conn)
    await agent_store.save(
        AgentConfig(
            name=agent_name,
            provider_config_id=provider_id,
            llm_model="mock-default",
            connector_account_ids=connector_account_ids or [],
        )
    )


async def _seed_stub_account(
    account_id: str = "acct-test",
    *,
    session_continuation_seconds: int | None = None,
) -> ConnectorAccount:
    """Persist a stub-typed ConnectorAccount via the repository.

    Accepts an optional ``session_continuation_seconds`` override so
    tests can drive the per-account continuation-window code path
    (the column path the F3 admin editor surfaces; distinct from the
    env-var path covered by F3 L3 resolver tests).
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorAccountRepository(conn, encryptor)
    account = ConnectorAccount(
        id=account_id,
        name="Stub Account",
        type="stub",
        config={},
        secrets={},
        session_continuation_seconds=session_continuation_seconds,
    )
    await repo.create(account)
    return account


async def _make_factory() -> AgentFactory:
    """Build an AgentFactory whose ``store`` reads from the per-test DB.

    Disables MCP wiring (``mcp_provider=None``) so the factory doesn't
    spawn MCP processes during the test agent build.
    """
    conn = await get_connection()
    store = SQLiteAgentStore(conn)
    return AgentFactory(store=store, mcp_provider=None)


def _envelope(
    *,
    channel_id: str = "ch-1",
    thread_id: str | None = None,
    peer_id: str = "peer-1",
    account_id: str = "acct-test",
    platform: str = "stub",
    text: str = "hello",
) -> InboundEnvelope:
    return InboundEnvelope(
        platform=platform,
        account_id=account_id,
        channel_id=channel_id,
        thread_id=thread_id,
        peer_id=peer_id,
        peer_name="Alice",
        text=text,
        raw={},
    )


# ─── Scripted provider + factory ─────────────────────────────────────────


class _ScriptedProvider(LLMProvider):
    """Stateful test provider that returns pre-scripted ``Message`` instances in
    sequence, one per ``complete()`` call.

    Unlike :class:`the_one.llm.mock.MockProvider` (stateless — returns
    the same canned response on every call, which would infinite-loop
    when the canned response carries a tool_call), this provider drives
    multi-iteration agent flows where iteration N must differ from
    iteration N+1 (e.g. iter1 emits a tool_call, iter2 emits plain
    text to end the turn).

    Used by F4 L4 visibility-tagging tests AND F4 L5 e2e platform-send
    tests that exercise the agent's tool-loop end-to-end.
    """

    name = "scripted"

    def __init__(
        self,
        responses: list[Message],
        *,
        model: str = "scripted-default",
        base_url: str = "",
        api_key: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._responses = list(responses)
        self._idx = 0
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.config = config or {}

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        if self._idx >= len(self._responses):
            # Default tail: end the turn with a plain-text response so
            # the agent's tool-loop terminates cleanly even if the test
            # script under-provisioned.
            return Message.assistant(content="(end)")
        response = self._responses[self._idx]
        self._idx += 1
        return response


async def _make_scripted_factory(
    responses: list[Message],
    monkeypatch: pytest.MonkeyPatch,
    *,
    extra_tool_providers: list[Any] | None = None,
    connector_account_ids: list[str] | None = None,
) -> AgentFactory:
    """Build an AgentFactory wired to a :class:`_ScriptedProvider`.

    Monkeypatches ``the_one.agent.factory.get_provider`` so the factory's
    LLM resolution returns our scripted provider. ``extra_tool_providers``
    (optional) are appended after ``BuiltinToolProvider`` so the
    platform-send tool + any test-only tools coexist in the agent's
    registry.

    ``connector_account_ids`` (optional): passed through the
    :func:`_seed_provider_and_agent` path's persisted-row state. After
    the F4 L5 v17 migration this list is in the DB column directly;
    the F4 L4 ``_row_to_config`` monkeypatch workaround is REMOVED.
    Callers that need the F4 L3 connector carve-out to fire should
    seed the agent with ``connector_account_ids`` in
    :func:`_seed_provider_and_agent` BEFORE calling this factory.
    """
    conn = await get_connection()
    store = SQLiteAgentStore(conn)

    from the_one.tools.builtins import BuiltinToolProvider

    providers: list[Any] = [BuiltinToolProvider()]
    if extra_tool_providers:
        providers.extend(extra_tool_providers)
    factory = AgentFactory(store=store, mcp_provider=None, tool_providers=providers)

    def _resolver(name: str, **kwargs: Any) -> _ScriptedProvider:
        return _ScriptedProvider(responses=list(responses), **kwargs)

    from the_one.agent import factory as factory_mod

    monkeypatch.setattr(factory_mod, "get_provider", _resolver)
    return factory
