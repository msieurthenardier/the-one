"""Type-level surface tests for F7 L1's CommandHandler Protocol and
CommandResponse dataclass plus the text-prefix command parser in
``_commands.py``.

Leg 1 of M10 F07 lands the surfaces but no consumer; leg 5 will wire
``_parse_command`` into the inbound dispatcher and leg 6 will ship the
six v1 command handlers. These tests pin:

- the parser's happy paths and negatives (case-sensitivity, single-slash
  rule, lowercase-letter-leading rule, whitespace handling, no-args
  default)
- ``CommandResponse`` is frozen + slotted + equal + hashable
- ``CommandHandler`` is runtime_checkable and accepts a sample handler
- the ``StubPlugin`` does NOT implement ``handle_command`` (regression-net
  preservation; F1–F6 dispatcher tests exercise the fall-through path)

Inline minimal fixtures (mirrors ``test_connectors_resolver.py``).
"""

from __future__ import annotations

import dataclasses

import aiosqlite
import pytest

from the_one.agent.config import AgentConfig
from the_one.connectors import CommandHandler, CommandResponse
from the_one.connectors._commands import (
    _dispatch_builtin_command,
    _handle_agents,
    _handle_help,
    _handle_new,
    _handle_reset,
    _handle_talk_to,
    _handle_whoami,
    _parse_command,
    _permitted_agents,
)
from the_one.connectors.base import InboundEnvelope
from the_one.db.models import ChatSession, Connector
from the_one.db.repositories import ChatSessionRepository
from the_one.db.schema import ensure_schema


class TestParseCommand:
    """Parser happy paths and negatives.

    Mirrors ``_validate_pairing_prefix``'s shape: pure function,
    byte-equality comparisons, case-sensitive, no regex. Returns
    ``(command_name, args)`` on success or ``None`` on any mismatch.
    """

    def test_parse_bare_agents(self) -> None:
        assert _parse_command("/agents") == ("agents", [])

    def test_parse_bare_whoami(self) -> None:
        assert _parse_command("/whoami") == ("whoami", [])

    def test_parse_bare_help(self) -> None:
        assert _parse_command("/help") == ("help", [])

    def test_parse_bare_new(self) -> None:
        assert _parse_command("/new") == ("new", [])

    def test_parse_bare_reset(self) -> None:
        assert _parse_command("/reset") == ("reset", [])

    def test_parse_talk_to_with_single_arg(self) -> None:
        assert _parse_command("/talk-to alice") == ("talk-to", ["alice"])

    def test_parse_talk_to_with_multiple_args(self) -> None:
        assert _parse_command("/talk-to alice extra") == (
            "talk-to",
            ["alice", "extra"],
        )

    def test_parse_collapses_internal_whitespace_runs(self) -> None:
        """``str.split()`` with no arg collapses runs of whitespace."""
        assert _parse_command("/talk-to   alice   bob") == (
            "talk-to",
            ["alice", "bob"],
        )

    def test_parse_trailing_whitespace_yields_no_args(self) -> None:
        """``str.split()`` ignores trailing whitespace."""
        assert _parse_command("/talk-to   ") == ("talk-to", [])

    def test_parse_empty_string_is_none(self) -> None:
        assert _parse_command("") is None

    def test_parse_plain_text_is_none(self) -> None:
        assert _parse_command("hello") is None

    def test_parse_lone_slash_is_none(self) -> None:
        """``/`` with no command word."""
        assert _parse_command("/") is None

    def test_parse_double_slash_is_none(self) -> None:
        """Single-leading-slash rule: ``//`` is rejected at the head check."""
        assert _parse_command("//double") is None

    def test_parse_leading_whitespace_is_none(self) -> None:
        """Commands must be at column 0 — matches ``_validate_pairing_prefix``'s
        ``startswith`` discipline."""
        assert _parse_command(" /agents") is None

    def test_parse_capitalized_command_is_none(self) -> None:
        """Case-sensitive; lowercase only — matches ``_validate_pairing_prefix``
        precedent (``PAIR`` keyword is case-sensitive byte-equality)."""
        assert _parse_command("/Agents") is None

    def test_parse_hyphen_leading_is_none(self) -> None:
        """Name head must be a lowercase letter, not a hyphen."""
        assert _parse_command("/-foo") is None

    def test_parse_digit_leading_is_none(self) -> None:
        """Name head must be a lowercase letter, not a digit."""
        assert _parse_command("/9foo") is None

    def test_parse_underscore_in_name_is_none(self) -> None:
        """``_`` is not in ``[a-z0-9-]``."""
        assert _parse_command("/foo_bar") is None


class TestCommandResponse:
    """``CommandResponse`` is frozen + slotted + equal + hashable."""

    def test_constructs_with_text(self) -> None:
        response = CommandResponse(text="hi")
        assert response.text == "hi"

    def test_equality(self) -> None:
        assert CommandResponse(text="hi") == CommandResponse(text="hi")
        assert CommandResponse(text="hi") != CommandResponse(text="bye")

    def test_hashable(self) -> None:
        # frozen+slots → hashable; calling hash() must not raise.
        assert hash(CommandResponse(text="hi")) == hash(CommandResponse(text="hi"))

    def test_mutation_raises_frozen_instance_error(self) -> None:
        response = CommandResponse(text="hi")
        with pytest.raises(dataclasses.FrozenInstanceError):
            response.text = "mutated"  # type: ignore[misc]

    def test_module_is_canonical_base(self) -> None:
        """Pins canonical-import identity. Mirrors the same-named
        assertion in ``test_connectors_resolver.py`` for
        ``_default_permit``."""
        assert CommandResponse.__module__ == "the_one.connectors.base"


class TestCommandHandlerProtocol:
    """``CommandHandler`` is ``runtime_checkable`` and structurally satisfiable."""

    def test_sample_handler_satisfies(self) -> None:
        """Inline minimal class with the right async signature passes."""

        class _SampleHandler:
            async def handle_command(
                self,
                envelope: object,
                command_name: str,
                args: list[str],
            ) -> CommandResponse | None:
                return CommandResponse(text=f"{command_name}!")

        assert isinstance(_SampleHandler(), CommandHandler)

    def test_class_without_handle_command_does_not_satisfy(self) -> None:
        """``@runtime_checkable`` confirms method-name presence at
        ``isinstance`` time."""

        class _NotAHandler:
            pass

        assert not isinstance(_NotAHandler(), CommandHandler)

    def test_stub_plugin_does_not_implement_handle_command(self) -> None:
        """Regression-net preservation: the stub MUST stay at its
        4-method shape. F1–F6 dispatcher tests drive inbound through the
        stub and rely on the fall-through path (handler-absent →
        dispatcher's built-in text-prefix parser handles the command).
        """
        from the_one.connectors._stub import StubPlugin

        plugin = StubPlugin()
        assert not hasattr(plugin, "handle_command")
        assert not isinstance(plugin, CommandHandler)

    def test_sync_handle_command_also_satisfies_runtime_check(self) -> None:
        """``@runtime_checkable`` Protocols verify method NAMES only —
        they do NOT verify signature, async-ness, or return type.

        L5's dispatcher MUST treat the return as awaitable per the
        Protocol's declared shape, not per the runtime-check guarantee.
        A plugin that violates the declared async signature breaks the
        runtime contract; the runtime check does not catch it. This is
        a stdlib limitation, accepted and documented here.
        """

        class _SyncSampleHandler:
            # NOTE: synchronous on purpose — pins that runtime_checkable
            # does not verify async-ness.
            def handle_command(  # type: ignore[override]
                self,
                envelope: object,
                command_name: str,
                args: list[str],
            ) -> CommandResponse | None:
                return None

        assert isinstance(_SyncSampleHandler(), CommandHandler)

    def test_module_is_canonical_base(self) -> None:
        """Pins canonical-import identity. Mirrors the same-named
        assertion in ``test_connectors_resolver.py`` for
        ``_default_permit``."""
        assert CommandHandler.__module__ == "the_one.connectors.base"


# ─────────────────────────────────────────────────────────────────
# M10 F7 L6: command-handler tests
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def conn(tmp_path):
    """Fresh DB connection with schema applied. Mirrors
    ``tests/test_connectors_session.py``'s ``conn`` fixture."""
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


def _envelope(
    *,
    peer_id: str = "peer-1",
    channel_id: str = "ch-1",
    account_id: str = "acct-test",
    text: str = "/help",
) -> InboundEnvelope:
    return InboundEnvelope(
        platform="stub",
        account_id=account_id,
        channel_id=channel_id,
        thread_id=None,
        peer_id=peer_id,
        peer_name="Alice",
        text=text,
        raw={},
    )


def _account(
    *,
    account_id: str = "acct-test",
    allowlist: dict | None = None,
) -> Connector:
    config: dict = {}
    if allowlist is not None:
        config["allowlist"] = allowlist
    return Connector(
        id=account_id,
        name="Test Account",
        type="stub",
        config=config,
    )


def _agent(
    name: str,
    *,
    connector_acls: dict[str, dict[str, list[str] | None]] | None = None,
) -> AgentConfig:
    return AgentConfig(
        name=name,
        connector_ids=["acct-test"],
        connector_acls=connector_acls,
    )


def _build_context(
    *,
    envelope: InboundEnvelope | None = None,
    account: Connector | None = None,
    eligible: list[AgentConfig] | None = None,
    routed_agent_name: str = "alpha",
    chat_repo: ChatSessionRepository | None = None,
    session_id: str = "session-1",
    args: list[str] | None = None,
) -> dict:
    ctx: dict = {
        "account": account if account is not None else _account(),
        "envelope": envelope if envelope is not None else _envelope(),
        "eligible_attached_agents": eligible if eligible is not None else [],
        "routed_agent_name": routed_agent_name,
        "session_id": session_id,
        "chat_repo": chat_repo,
    }
    if args is not None:
        ctx["args"] = args
    return ctx


async def _seed_chat_session(
    chat_repo: ChatSessionRepository,
    *,
    session_id: str = "session-1",
) -> None:
    """Seed a minimal chat_sessions row for ``set_session_metadata_key``
    targets — the primitive raises ``KeyError`` if the row doesn't exist."""
    await chat_repo.create(
        ChatSession(
            id=session_id,
            agent_name="alpha",
            title="test",
            messages="[]",
            platform="stub",
            connector_id="acct-test",
            channel_id="ch-1",
            thread_id=None,
            peer_id="peer-1",
        )
    )


class TestPermittedAgents:
    """Pin :func:`_permitted_agents` ACL filtering — input ordering
    preserved, ACL-denied agents removed."""

    def test_returns_alphabetical_when_no_acls(self) -> None:
        """No ACLs on the account or agents → every eligible agent
        appears in the result."""
        ctx = _build_context(
            eligible=[_agent("alpha"), _agent("bravo")],
        )
        assert _permitted_agents(ctx) == ["alpha", "bravo"]

    def test_account_allowlist_denies_peer(self) -> None:
        """Account allowlist with peers=[allowed-peer] denies peer-1."""
        account = _account(
            allowlist={"peers": ["allowed-peer"], "channels": []},
        )
        ctx = _build_context(
            account=account,
            eligible=[_agent("alpha"), _agent("bravo")],
        )
        assert _permitted_agents(ctx) == []

    def test_per_agent_acl_filters_one_agent(self) -> None:
        """``bravo`` has explicit empty peers list → denied; ``alpha``
        with no ACL inherits account-default permit."""
        eligible = [
            _agent("alpha"),
            _agent(
                "bravo",
                connector_acls={"acct-test": {"peers": [], "channels": None}},
            ),
        ]
        ctx = _build_context(eligible=eligible)
        assert _permitted_agents(ctx) == ["alpha"]


class TestHandleAgents:
    """Pin ``/agents`` handler's text and ACL filtering."""

    async def test_lists_permitted_agents(self) -> None:
        ctx = _build_context(
            eligible=[_agent("alpha"), _agent("bravo")],
            args=[],
        )
        response = await _handle_agents(ctx)
        assert response.text == (
            "Agents available to you on this account:\n- alpha\n- bravo"
        )

    async def test_empty_when_no_eligible(self) -> None:
        """No eligible agents → the byte-identical no-eligible string
        from L5's ``_inbound.py:394``."""
        ctx = _build_context(eligible=[], args=[])
        response = await _handle_agents(ctx)
        assert response.text == "No agents available for this conversation."

    async def test_acl_denied_agents_filtered(self) -> None:
        """``bravo`` denied via empty per-agent peers list → only
        ``alpha`` listed."""
        eligible = [
            _agent("alpha"),
            _agent(
                "bravo",
                connector_acls={"acct-test": {"peers": [], "channels": None}},
            ),
        ]
        ctx = _build_context(eligible=eligible, args=[])
        response = await _handle_agents(ctx)
        assert response.text == (
            "Agents available to you on this account:\n- alpha"
        )

    async def test_returns_no_eligible_when_all_denied(self) -> None:
        """All eligible attached agents are ACL-denied → the
        no-eligible string."""
        eligible = [
            _agent(
                "alpha",
                connector_acls={"acct-test": {"peers": [], "channels": None}},
            ),
            _agent(
                "bravo",
                connector_acls={"acct-test": {"peers": [], "channels": None}},
            ),
        ]
        ctx = _build_context(eligible=eligible, args=[])
        response = await _handle_agents(ctx)
        assert response.text == "No agents available for this conversation."


class TestHandleTalkTo:
    """Pin ``/talk-to`` handler's args parsing, ACL check, and
    ``routing_override`` side-effect."""

    async def test_empty_args_returns_usage(self, chat_repo) -> None:
        await _seed_chat_session(chat_repo)
        ctx = _build_context(
            eligible=[_agent("alpha")],
            chat_repo=chat_repo,
            args=[],
        )
        response = await _handle_talk_to(ctx)
        assert response.text == "Usage: /talk-to <agent-slug>"
        # No write to the session row.
        session = await chat_repo.get("session-1")
        assert session.session_metadata is None

    async def test_whitespace_only_returns_usage(self, chat_repo) -> None:
        """Parser-collapsed equivalent of ``/talk-to    `` — args is
        the empty list. Pins the L1 parser's trailing-whitespace
        contract."""
        await _seed_chat_session(chat_repo)
        ctx = _build_context(
            eligible=[_agent("alpha")],
            chat_repo=chat_repo,
            args=[],
        )
        response = await _handle_talk_to(ctx)
        assert response.text == "Usage: /talk-to <agent-slug>"

    async def test_unknown_slug_returns_peer_error(self, chat_repo) -> None:
        await _seed_chat_session(chat_repo)
        ctx = _build_context(
            eligible=[_agent("alpha")],
            chat_repo=chat_repo,
            args=["nonexistent"],
        )
        response = await _handle_talk_to(ctx)
        assert response.text == (
            "No such agent or you don't have permission: nonexistent"
        )
        # No write to the session row.
        session = await chat_repo.get("session-1")
        assert session.session_metadata is None

    async def test_acl_denied_slug_same_error_path(self, chat_repo) -> None:
        """ACL-denied agent's slug behaves the same as unknown — the
        handler does not distinguish "doesn't exist" from "denied" in
        the peer-facing text (avoids leaking ACL state)."""
        await _seed_chat_session(chat_repo)
        eligible = [
            _agent(
                "bravo",
                connector_acls={"acct-test": {"peers": [], "channels": None}},
            ),
        ]
        ctx = _build_context(
            eligible=eligible,
            chat_repo=chat_repo,
            args=["bravo"],
        )
        response = await _handle_talk_to(ctx)
        assert response.text == (
            "No such agent or you don't have permission: bravo"
        )
        # No override write.
        session = await chat_repo.get("session-1")
        assert session.session_metadata is None

    async def test_valid_slug_writes_routing_override(self, chat_repo) -> None:
        """Valid slug ⇒ ``set_session_metadata_key`` writes the
        override; the confirmation text echoes the slug."""
        await _seed_chat_session(chat_repo)
        ctx = _build_context(
            eligible=[_agent("alpha"), _agent("bravo")],
            chat_repo=chat_repo,
            args=["bravo"],
        )
        response = await _handle_talk_to(ctx)
        assert response.text == "Now routing your messages to bravo."

        session = await chat_repo.get("session-1")
        assert session.session_metadata == {"routing_override": "bravo"}

    async def test_multiple_args_only_first_consumed(self, chat_repo) -> None:
        """``/talk-to alice extra`` → handler reads ``args[0]`` only."""
        await _seed_chat_session(chat_repo)
        ctx = _build_context(
            eligible=[_agent("alice")],
            chat_repo=chat_repo,
            args=["alice", "extra"],
        )
        response = await _handle_talk_to(ctx)
        assert response.text == "Now routing your messages to alice."
        session = await chat_repo.get("session-1")
        assert session.session_metadata == {"routing_override": "alice"}

    async def test_second_talk_to_overwrites_first(self, chat_repo) -> None:
        """Pins ``set_session_metadata_key``'s last-writer-wins
        primitive contract: a second ``/talk-to`` overwrites the
        first's ``routing_override`` value."""
        await _seed_chat_session(chat_repo)
        eligible = [_agent("alice"), _agent("bob")]
        ctx_a = _build_context(
            eligible=eligible,
            chat_repo=chat_repo,
            args=["alice"],
        )
        await _handle_talk_to(ctx_a)
        ctx_b = _build_context(
            eligible=eligible,
            chat_repo=chat_repo,
            args=["bob"],
        )
        await _handle_talk_to(ctx_b)

        session = await chat_repo.get("session-1")
        assert session.session_metadata == {"routing_override": "bob"}


class TestHandleWhoami:
    """Pin ``/whoami`` returns the routed agent name from context."""

    async def test_returns_routed_agent_name(self) -> None:
        ctx = _build_context(routed_agent_name="alpha")
        response = await _handle_whoami(ctx)
        assert response.text == "Currently responding: alpha."

    async def test_returns_routed_agent_name_alt(self) -> None:
        ctx = _build_context(routed_agent_name="bravo")
        response = await _handle_whoami(ctx)
        assert response.text == "Currently responding: bravo."


class TestHandleNew:
    """Pin ``/new`` writes ``ended_at`` and returns the confirmation."""

    async def test_writes_ended_at_and_returns_confirmation(self, chat_repo) -> None:
        await _seed_chat_session(chat_repo)
        ctx = _build_context(chat_repo=chat_repo)
        response = await _handle_new(ctx)
        assert response.text == (
            "Started a new conversation. Your next message will begin a "
            "fresh session."
        )
        session = await chat_repo.get("session-1")
        assert session.session_metadata is not None
        assert "ended_at" in session.session_metadata
        # ISO timestamp shape: round-trip via datetime.fromisoformat.
        from datetime import datetime
        datetime.fromisoformat(session.session_metadata["ended_at"])


class TestHandleReset:
    """Pin ``/reset`` is an alias for ``/new`` — same response, same
    side-effect."""

    async def test_reset_aliases_new(self, chat_repo) -> None:
        await _seed_chat_session(chat_repo, session_id="reset-session")
        ctx = _build_context(chat_repo=chat_repo, session_id="reset-session")
        response = await _handle_reset(ctx)
        assert response.text == (
            "Started a new conversation. Your next message will begin a "
            "fresh session."
        )
        session = await chat_repo.get("reset-session")
        assert session.session_metadata is not None
        assert "ended_at" in session.session_metadata

    async def test_reset_response_matches_new_response(self, chat_repo) -> None:
        """Calling ``_handle_new`` and ``_handle_reset`` on the same
        context-shaped state produces equal ``CommandResponse`` values."""
        await _seed_chat_session(chat_repo, session_id="new-session")
        await _seed_chat_session(chat_repo, session_id="reset-session")
        ctx_new = _build_context(chat_repo=chat_repo, session_id="new-session")
        ctx_reset = _build_context(chat_repo=chat_repo, session_id="reset-session")

        response_new = await _handle_new(ctx_new)
        response_reset = await _handle_reset(ctx_reset)

        assert response_new == response_reset


class TestHandleHelp:
    """Pin ``/help`` permission-filtering: ``/agents`` and ``/talk-to``
    listed only when the peer has ≥1 ACL-permitted attached agent."""

    async def test_help_with_permitted_agents_lists_all_six(self) -> None:
        ctx = _build_context(eligible=[_agent("alpha")])
        response = await _handle_help(ctx)
        text = response.text
        assert text.startswith("Available commands:")
        # All six commands listed.
        assert "/agents" in text
        assert "/talk-to" in text
        assert "/whoami" in text
        assert "/new" in text
        assert "/reset" in text
        assert "/help" in text

    async def test_help_with_zero_permitted_agents_hides_agent_dependent(
        self,
    ) -> None:
        """ACL denies every attached agent → ``/agents`` and ``/talk-to``
        are absent from the response."""
        eligible = [
            _agent(
                "alpha",
                connector_acls={"acct-test": {"peers": [], "channels": None}},
            ),
        ]
        ctx = _build_context(eligible=eligible)
        response = await _handle_help(ctx)
        text = response.text
        assert text.startswith("Available commands:")
        assert "/agents" not in text
        assert "/talk-to" not in text
        # Always-listed commands stay.
        assert "/whoami" in text
        assert "/new" in text
        assert "/reset" in text
        assert "/help" in text

    async def test_help_with_no_eligible_attached_agents(self) -> None:
        """Same shape as zero-permitted: no attached agents at all
        also hides the agent-dependent commands."""
        ctx = _build_context(eligible=[])
        response = await _handle_help(ctx)
        text = response.text
        assert "/agents" not in text
        assert "/talk-to" not in text
        assert "/whoami" in text
        assert "/help" in text


class TestDispatchBuiltinCommand:
    """Pin :func:`_dispatch_builtin_command` integration: known
    commands route to their handler; unknown commands return
    ``None`` (fall-through)."""

    async def test_agents_dispatches_to_handler(self) -> None:
        ctx = _build_context(eligible=[_agent("alpha")])
        response = await _dispatch_builtin_command("agents", [], ctx)
        assert response is not None
        assert response.text == (
            "Agents available to you on this account:\n- alpha"
        )

    async def test_unknown_command_returns_none(self) -> None:
        """Fall-through is preserved for unrecognized command names —
        the L5 dispatcher treats ``None`` as ``"don't intercept; run
        agent.step"``."""
        ctx = _build_context(eligible=[_agent("alpha")])
        result = await _dispatch_builtin_command("nonsense", [], ctx)
        assert result is None

    async def test_help_dispatches_to_handler(self) -> None:
        ctx = _build_context(eligible=[_agent("alpha")])
        response = await _dispatch_builtin_command("help", [], ctx)
        assert response is not None
        assert response.text.startswith("Available commands:")

    async def test_args_packed_into_context(self, chat_repo) -> None:
        """Dispatcher packs ``args`` into the context dict under the
        ``"args"`` key before invoking the handler — this is the
        single L6 contract on how arguments reach the handlers."""
        await _seed_chat_session(chat_repo)
        ctx = _build_context(
            eligible=[_agent("alice")],
            chat_repo=chat_repo,
        )
        # ``args`` is NOT set on the context before dispatch.
        assert "args" not in ctx
        response = await _dispatch_builtin_command("talk-to", ["alice"], ctx)
        assert response is not None
        assert response.text == "Now routing your messages to alice."
        # After dispatch, the handler observed args via context.
        assert ctx["args"] == ["alice"]
