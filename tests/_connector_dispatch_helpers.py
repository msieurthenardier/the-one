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
  ``connector_ids`` (F4 L1 widening); the F4 L5 v17 migration
  persists this list to the new ``agents.connector_ids`` column,
  so the kwarg flows through to the DB without a monkeypatch.
- :func:`_seed_stub_account` — persists a stub-typed
  :class:`Connector` via the repository; accepts
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
  ``connector_ids`` kwarg flows through real persistence — no
  ``_row_to_config`` monkeypatch needed.

Autouse cleanup (``_reset_stub_state``, ``_clear_pool_locks_registry``)
remains per-file. The cleanup fixtures are autouse-scoped to the
consumer module so they fire for every test in that file but do NOT
need to be exported from this helper module — the leg-design decision
documented in the F3 debrief was that exporting an autouse fixture from
a non-conftest module creates ordering surprises.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import (
    InboundEnvelope,
    Permit,
    ResolveOutcome,
)
from the_one.db.connection import get_connection
from the_one.db.models import Connector, LLMProviderConfig
from the_one.db.repositories import (
    ConnectorRepository,
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
    connector_ids: list[str] | None = None,
) -> None:
    """Seed an LLM provider + agent config so ``AgentFactory.create()``
    has something to build against. Uses ``type='mock'`` so the LLM
    registry resolves to :class:`the_one.llm.mock.MockProvider`.

    ``connector_ids`` opts the agent into the F4 L3 connector
    carve-out (loads ``send_to_platform_channel`` into the baseline-
    visible tool set + injects the connector-aware system-prompt
    directive). F4 L5 v17 migration persists this list; ``factory.create``
    now sees it on every invocation without a monkeypatch.

    M10 F7 L3: the default (when ``connector_ids`` is ``None``)
    is ``["acct-test"]`` — matches :func:`_seed_stub_account`'s default
    ``account_id="acct-test"`` and :func:`_envelope`'s default
    ``account_id="acct-test"``. The default attachment is required for
    F7 L3's transitional dispatcher helper to find the agent via
    :meth:`SQLiteAgentStore.list_by_connector`. Tests that
    need an empty attachment list pass ``connector_ids=[]``
    explicitly.
    """
    if connector_ids is None:
        connector_ids = ["acct-test"]

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
            connector_ids=connector_ids,
        )
    )


async def _seed_stub_account(
    account_id: str = "acct-test",
    *,
    session_continuation_seconds: int | None = None,
    config: dict[str, Any] | None = None,
) -> Connector:
    """Persist a stub-typed Connector via the repository.

    Accepts an optional ``session_continuation_seconds`` override so
    tests can drive the per-account continuation-window code path
    (the column path the F3 admin editor surfaces; distinct from the
    env-var path covered by F3 L3 resolver tests).

    ``config`` override lets tests supply a reserved-key payload
    (pairing, allowlist, routing, always_listen) at seed time without an
    extra round-trip through ``repo.update``. Empty / missing ``config``
    defaults to ``{}``.
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorRepository(conn, encryptor)
    account = Connector(
        id=account_id,
        name="Stub Account",
        type="stub",
        config=config if config is not None else {},
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
    is_dm: bool = True,
    raw: dict[str, Any] | None = None,
) -> InboundEnvelope:
    """Build an InboundEnvelope with sensible defaults.

    M11 F7 L8: ``is_dm`` defaults to ``True`` so existing dispatcher
    tests engage via the F7 policy gate's DM short-circuit (DD §1 step
    1). Tests that exercise channel-routed (non-DM) engagement override
    with ``is_dm=False`` AND seed always-listen toggles or mention raw
    fields to drive the desired gate branch.

    ``raw`` lets a test pass through arbitrary platform-specific fields
    (e.g. ``guild_id``, ``member_roles``, ``discord_message``). When
    omitted, the helper builds ``{"is_dm": is_dm}``; when supplied, the
    helper merges ``is_dm`` into the dict unless the caller's dict
    already carries an explicit ``"is_dm"`` key.
    """
    raw_dict: dict[str, Any] = dict(raw) if raw is not None else {}
    raw_dict.setdefault("is_dm", is_dm)
    return InboundEnvelope(
        platform=platform,
        account_id=account_id,
        channel_id=channel_id,
        thread_id=thread_id,
        peer_id=peer_id,
        peer_name="Alice",
        text=text,
        raw=raw_dict,
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
    connector_ids: list[str] | None = None,
) -> AgentFactory:
    """Build an AgentFactory wired to a :class:`_ScriptedProvider`.

    Monkeypatches ``the_one.agent.factory.get_provider`` so the factory's
    LLM resolution returns our scripted provider. ``extra_tool_providers``
    (optional) are appended after ``BuiltinToolProvider`` so the
    platform-send tool + any test-only tools coexist in the agent's
    registry.

    ``connector_ids`` (optional): passed through the
    :func:`_seed_provider_and_agent` path's persisted-row state. After
    the F4 L5 v17 migration this list is in the DB column directly;
    the F4 L4 ``_row_to_config`` monkeypatch workaround is REMOVED.
    Callers that need the F4 L3 connector carve-out to fire should
    seed the agent with ``connector_ids`` in
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


# ─── M10 F06 L2: stub variant exposing the resolve hook ──────────────────


class StubPluginWithResolver(StubPlugin):
    """Stub variant that implements the F6 ``resolve`` hook.

    The production :class:`StubPlugin` (in ``the_one/connectors/_stub.py``)
    deliberately does NOT implement ``resolve`` — F1-F5 tests assert that
    a plugin without ``resolve`` behaves byte-identically by hitting the
    ``_default_permit`` fallback at the dispatcher's ``getattr`` discovery
    site. This test-side variant ADDS ``resolve`` so the F6 dispatcher
    branches can be exercised.

    Class-level ``resolve_outcome`` knob lets tests configure the outcome
    per case (default :class:`Permit`); ``resolve_calls`` is the class-
    level recording buffer for assertions. ``reset_for_test`` extends
    :meth:`StubPlugin.reset_for_test` to also clear the resolver state.
    """

    resolve_outcome: ClassVar[ResolveOutcome] = Permit()
    resolve_calls: ClassVar[list[tuple[str, str]]] = []

    def resolve(
        self, account: Connector, envelope: InboundEnvelope
    ) -> ResolveOutcome:
        StubPluginWithResolver.resolve_calls.append(
            (account.id, envelope.peer_id)
        )
        return StubPluginWithResolver.resolve_outcome

    @classmethod
    def reset_for_test(cls) -> None:
        StubPlugin.reset_for_test()
        cls.resolve_outcome = Permit()
        cls.resolve_calls = []
