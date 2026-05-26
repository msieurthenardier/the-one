"""Tests for ``the_one.connectors._inbound`` policy-gate pre-step — M11 F7 L8.

The policy gate is the pivotal F7 behavioral change: between the F7 L5
command-intercept fallthrough (step 11) and the per-session lock +
``agent.step`` block (step 12), the dispatcher consults a five-path
decision tree (Flight DD §1) to decide whether the bot engages with the
inbound. Silent branches terminal-return with an audit entry having
``disposition="policy-silent"``; engaged branches flow through to step
12 unchanged.

The decision tree (first match wins):

1. ``envelope.raw["is_dm"]`` is True → engage (DMs ignore policy gate).
2. ``decision.scope == "override"`` → engage (peer's ``/talk-to``
   bypasses the gate).
3. ``plugin.is_mention(envelope)`` returns True → engage (explicit
   @mention).
4. ``account.config["always_listen"]`` AND
   ``agent.connector_always_listen[account_id]`` both True → run
   inference; engage iff the inference returns ``"yes"``.
5. Otherwise → silent.

Silent-branch invariants (Flight DD §13):

- NO ``async with session_locks[session_row.id]`` acquired.
- NO ``update_last_inbound`` called.
- NO agent built; NO ``agent.step`` called.
- NO auto-relay; NO WS broadcast.
- The audit append at ``session_metadata["routing"]`` is the only side
  effect.

Engaged-branch invariants:

- Audit entry retains ``disposition="stepped"`` (or
  ``"command-intercepted"`` if step 11 won first).
- The policy sub-block is NOT embedded on engaged paths (F9's audit-log
  inspector reads engaged entries' implicit non-silent disposition).
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from tests._connector_dispatch_helpers import (
    StubPluginWithResolver,
    _envelope,
    _make_factory,
    _seed_provider_and_agent,
    _seed_stub_account,
)
from the_one.agent.config import AgentConfig
from the_one.config import settings
from the_one.connectors import _inbound as inbound_mod
from the_one.connectors import _pool as pool_mod
from the_one.connectors._inbound import dispatch_inbound
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import InboundEnvelope
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.models import ConnectorAccount
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorAccountRepository,
    SQLiteAgentStore,
)
from the_one.encryption import get_encryptor
from the_one.llm.base import Role
from the_one.sessions import clear_for_test as _clear_session_registry


# ─── Autouse fixtures ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_locks_registry():
    yield
    await pool_mod._clear_for_test()
    await inbound_mod._clear_for_test()
    _clear_session_registry()
    _registry_clear_for_test()
    restore_to_baseline_for_test()


# ─── Test-only stub variants ─────────────────────────────────────────────


class StubPluginWithMention(StubPlugin):
    """Stub variant that implements the L1 ``is_mention`` hook.

    The production :class:`StubPlugin` deliberately does NOT implement
    ``is_mention`` — the F7 L8 gate hits ``_default_no_mention`` and
    treats stub-driven inbound as silent-by-default. This test-side
    variant ADDS ``is_mention`` so the mention-engaged gate branch can
    be exercised.

    Class-level ``mention_result`` knob lets each test configure the
    hook's return value.
    """

    mention_result: ClassVar[bool] = True

    def is_mention(self, envelope: InboundEnvelope) -> bool:
        return StubPluginWithMention.mention_result

    @classmethod
    def reset_for_test(cls) -> None:
        StubPlugin.reset_for_test()
        cls.mention_result = True


# ─── Helpers ─────────────────────────────────────────────────────────────


async def _routing_entries(session_id: str) -> list[dict[str, Any]]:
    """Fetch the ``routing`` audit list off the session metadata."""
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    session = await chat_repo.get(session_id)
    if session.session_metadata is None:
        return []
    return session.session_metadata.get("routing", [])


async def _first_session_id() -> str:
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    return sessions[0].id


async def _enable_always_listen(
    *,
    account_id: str = "acct-test",
    agent_name: str = "agent-inbound",
) -> None:
    """Set both always-listen toggles to True for the inference path."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    account = await acc_repo.get(account_id)
    account.config["always_listen"] = True
    await acc_repo.update(account)

    agent_store = SQLiteAgentStore(conn)
    cfg = await agent_store.load(agent_name)
    updated = cfg.model_copy(
        update={"connector_always_listen": {account_id: True}}
    )
    await agent_store.save(updated)


# ─────────────────────────────────────────────────────────────────────────
#   Engagement tests
# ─────────────────────────────────────────────────────────────────────────


class TestPolicyGateEngagement:
    """Each branch of the decision tree that engages (steps 1-4 yes)."""

    async def test_policy_gate_engages_on_dm(self, isolated_db) -> None:
        """``envelope.raw["is_dm"] = True`` → engage even without
        mention/always-listen. Default ``_envelope()`` ships ``is_dm=True``;
        we explicitly pin the assertion here so the regression is named
        after the contract."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        envelope = _envelope(is_dm=True)
        await dispatch_inbound("acct-test", envelope, factory=factory)

        session_id = await _first_session_id()
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        session = await chat_repo.get(session_id)
        history = decode_messages(session.messages)
        # Engaged path: USER + ASSISTANT messages persisted.
        user_msgs = [m for m in history if m.role == Role.USER]
        assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
        assert len(user_msgs) == 1
        assert len(assistant_msgs) >= 1
        # Audit entry → disposition="stepped" (not policy-silent).
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "stepped"
        # Engaged path does NOT embed the policy sub-block on the audit
        # entry — per DD §1, the policy sub-block lives only on silent
        # entries.
        assert "policy" not in routing[0]

    async def test_policy_gate_engages_on_override(self, isolated_db) -> None:
        """``session_metadata["routing_override"] = "agent-inbound"``
        produces ``decision.scope == "override"`` → engage even when
        the envelope is a non-DM, non-mention, non-always-listen
        inbound."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        # Warmup: an engaged DM dispatch materializes the session row
        # so we can write the override key to its metadata.
        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=True, text="warmup"), factory=factory
        )
        session_id = await _first_session_id()

        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        await chat_repo.set_session_metadata_key(
            session_id, "routing_override", "agent-inbound"
        )

        # Now dispatch a non-DM envelope; override engages the gate.
        await dispatch_inbound(
            "acct-test",
            _envelope(is_dm=False, text="override-engages"),
            factory=factory,
        )

        routing = await _routing_entries(session_id)
        # Warmup + override → 2 entries; both "stepped".
        assert len(routing) == 2
        assert routing[-1]["disposition"] == "stepped"
        assert routing[-1]["scope"] == "override"

    async def test_policy_gate_engages_on_mention(
        self, isolated_db
    ) -> None:
        """``plugin.is_mention(envelope)`` True → engage. Non-DM, no
        always-listen, no override."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        StubPluginWithMention.reset_for_test()
        StubPluginWithMention.mention_result = True
        register_for_test("stub", StubPluginWithMention)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "stepped"

    async def test_policy_gate_engages_on_inference_yes(
        self, isolated_db, monkeypatch
    ) -> None:
        """Both always-listen toggles True, inference returns True →
        engage. Audit entry stays ``disposition="stepped"`` and does
        NOT carry the policy sub-block (engaged-path semantic)."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        await _enable_always_listen()
        register_for_test("stub", StubPlugin)

        async def _yes(**kwargs: Any) -> bool:
            return True

        monkeypatch.setattr(inbound_mod, "run_engagement_inference", _yes)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "stepped"
        assert "policy" not in routing[0]


# ─────────────────────────────────────────────────────────────────────────
#   Silent-branch tests
# ─────────────────────────────────────────────────────────────────────────


class TestPolicyGateSilent:
    """Each branch of the decision tree that goes silent (step 5)."""

    async def test_policy_gate_silent_when_account_always_listen_off(
        self, isolated_db
    ) -> None:
        """No DM, no mention, no override, account.always_listen=False
        (default) → silent. The session row exists (resolve_session
        runs before the gate); history holds NO USER/ASSISTANT
        messages; routing audit has one ``"policy-silent"`` entry with
        ``policy.outcome="always-listen-off"`` and
        ``policy.account_always_listen=False``."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        session = await chat_repo.get(session_id)
        history = decode_messages(session.messages)
        assert all(m.role not in (Role.USER, Role.ASSISTANT) for m in history)

        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "policy-silent"
        assert routing[0]["policy"]["outcome"] == "always-listen-off"
        assert routing[0]["policy"]["account_always_listen"] is False

    async def test_policy_gate_silent_when_account_on_agent_off(
        self, isolated_db
    ) -> None:
        """``account.always_listen=True`` but the agent's
        ``connector_always_listen[account_id]`` is False (or absent) →
        silent. Audit entry's policy sub-block records the per-toggle
        state."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)
        # Account-level on; agent-level absent (defaults False).
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        account = await acc_repo.get("acct-test")
        account.config["always_listen"] = True
        await acc_repo.update(account)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "policy-silent"
        assert routing[0]["policy"]["outcome"] == "always-listen-off"
        assert routing[0]["policy"]["account_always_listen"] is True
        assert routing[0]["policy"]["agent_always_listen"] is False

    async def test_policy_gate_silent_on_inference_no(
        self, isolated_db, monkeypatch
    ) -> None:
        """Both toggles True, inference returns False → silent;
        audit has ``policy.outcome="inference-no"``."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        await _enable_always_listen()
        register_for_test("stub", StubPlugin)

        async def _no(**kwargs: Any) -> bool:
            return False

        monkeypatch.setattr(inbound_mod, "run_engagement_inference", _no)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "policy-silent"
        assert routing[0]["policy"]["outcome"] == "inference-no"

    async def test_policy_gate_silent_on_inference_exception(
        self, isolated_db, monkeypatch
    ) -> None:
        """L7 contract: ``run_engagement_inference`` returns False on
        every exceptional outcome (provider resolve failure, etc.).
        The L8 gate sees that False as a silent terminal-return — no
        crash propagates from the dispatcher. We simulate L7's safe-
        default by monkeypatching the function to return False (which
        is L7's published contract for exception paths).
        """
        await _seed_provider_and_agent()
        await _seed_stub_account()
        await _enable_always_listen()
        register_for_test("stub", StubPlugin)

        async def _safe_default(**kwargs: Any) -> bool:
            # Mirrors L7's exception-collapse-to-False behaviour.
            return False

        monkeypatch.setattr(
            inbound_mod, "run_engagement_inference", _safe_default
        )

        factory = await _make_factory()
        # Should NOT raise even if L7's internal provider resolution
        # would fail in production; L7 collapses to False which we
        # simulate here.
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "policy-silent"


# ─────────────────────────────────────────────────────────────────────────
#   Silent-branch side-effect invariants (DD §13)
# ─────────────────────────────────────────────────────────────────────────


class TestPolicyGateSilentSideEffects:
    """Silent branches MUST be free of agent-side side effects."""

    async def test_policy_gate_silent_branch_does_not_acquire_session_lock(
        self, isolated_db
    ) -> None:
        """Silent path bypasses the per-session lock → no
        ``update_last_inbound`` call. The session resolver sets
        ``last_inbound_at`` at session-creation time (see
        ``_session.py:196``), so we materialize the session with an
        engaged DM dispatch first, capture the post-dispatch
        ``last_inbound_at``, then verify a subsequent silent dispatch
        does NOT bump it. F6 Deny / NeedsPairing-failure precedent at
        :func:`test_deny_outcome_logs_and_returns` uses the same shape
        of assertion."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        # Engaged dispatch creates the session and bumps
        # ``last_inbound_at`` inside the per-session lock.
        await dispatch_inbound(
            "acct-test",
            _envelope(is_dm=True, text="warmup"),
            factory=factory,
        )

        session_id = await _first_session_id()
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        before = (await chat_repo.get(session_id)).last_inbound_at
        assert before is not None

        # Now a silent dispatch: same session row, non-DM envelope, no
        # always-listen. The gate goes silent before the lock acquires;
        # ``update_last_inbound`` does NOT fire.
        await dispatch_inbound(
            "acct-test",
            _envelope(is_dm=False, text="silent"),
            factory=factory,
        )
        after = (await chat_repo.get(session_id)).last_inbound_at
        assert after == before

    async def test_policy_gate_silent_branch_does_not_call_agent_step(
        self, isolated_db
    ) -> None:
        """Silent path NEVER calls ``factory.create`` → no agent is
        built. Use a recording factory that fails-loudly if invoked."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        class _FailIfCreated:
            def __init__(self) -> None:
                self.called: bool = False

            async def create(self, name: str = "default"):
                self.called = True
                raise AssertionError(
                    "factory.create must NOT be called on the silent "
                    "policy-gate path"
                )

        factory = _FailIfCreated()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory  # type: ignore[arg-type]
        )
        assert factory.called is False

        # Defense in depth: no USER/ASSISTANT messages persisted.
        session_id = await _first_session_id()
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        session = await chat_repo.get(session_id)
        history = decode_messages(session.messages)
        assert all(m.role not in (Role.USER, Role.ASSISTANT) for m in history)

    async def test_policy_gate_silent_branch_appends_routing_audit_with_policy_subblock(
        self, isolated_db
    ) -> None:
        """The ONE side effect on the silent path is the audit append:
        ``disposition="policy-silent"`` with a ``policy`` sub-dict
        whose ``outcome`` is one of the expected strings."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["disposition"] == "policy-silent"
        assert isinstance(entry["policy"], dict)
        assert entry["policy"]["outcome"] in {
            "always-listen-off",
            "inference-no",
        }


# ─────────────────────────────────────────────────────────────────────────
#   Engaged-disposition regression pins
# ─────────────────────────────────────────────────────────────────────────


class TestPolicyGateEngagedRegression:
    """Pin that engaged paths keep their pre-L8 audit shape."""

    async def test_policy_gate_engaged_audit_disposition_stepped(
        self, isolated_db
    ) -> None:
        """A DM inbound (engaged) lands at step 12 → audit entry has
        ``disposition="stepped"``; L8 did not break the L5 engaged-path
        shape."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=True), factory=factory
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "stepped"


# ─────────────────────────────────────────────────────────────────────────
#   Inference-path provider/model fallback wiring
# ─────────────────────────────────────────────────────────────────────────


class TestPolicyGateInferenceFallbacks:
    """The dispatcher passes the routed agent's ``provider_config_id``
    and ``llm_model`` to :func:`run_engagement_inference` as the
    fallback pair when the settings pair is unset."""

    async def test_policy_gate_inference_path_uses_correct_provider_and_model_fallbacks(
        self, isolated_db, monkeypatch
    ) -> None:
        """Both always-listen toggles True, settings inference fields
        unset → :func:`run_engagement_inference` receives the agent's
        ``provider_config_id`` and ``llm_model`` as the fallback pair.
        Verifies the L8 → L7 wiring contract."""
        await _seed_provider_and_agent(
            agent_name="agent-inbound",
            provider_id="mock-provider",
        )
        await _seed_stub_account()
        await _enable_always_listen()
        register_for_test("stub", StubPlugin)

        captured: dict[str, Any] = {}

        async def _capture(**kwargs: Any) -> bool:
            captured.update(kwargs)
            return False  # silent

        monkeypatch.setattr(
            inbound_mod, "run_engagement_inference", _capture
        )

        factory = await _make_factory()
        await dispatch_inbound(
            "acct-test", _envelope(is_dm=False), factory=factory
        )

        assert captured["fallback_provider_config_id"] == "mock-provider"
        assert captured["fallback_llm_model"] == "mock-default"


# ─────────────────────────────────────────────────────────────────────────
#   Command-intercept × policy-gate interaction
# ─────────────────────────────────────────────────────────────────────────


class TestPolicyGateCommandInterceptInteraction:
    """Step 11 (command intercept) runs BEFORE the policy gate. Pins
    the ordering invariant from the leg's cycle-1 review."""

    async def test_policy_gate_audit_has_silent_branch_for_command_no_response_fallthrough(
        self, isolated_db
    ) -> None:
        """``/foo`` parses as a command but no handler returns a
        response → the command-intercept block falls through to the
        gate. With no DM / mention / always-listen, the gate goes
        silent → audit entry has ``disposition="policy-silent"``."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        # ``/foo`` is unknown → ``_parse_command`` returns
        # ``("foo", [])`` and the built-in dispatch returns None.
        # Step 11 falls through; the gate then evaluates on a non-DM
        # envelope and goes silent.
        await dispatch_inbound(
            "acct-test",
            _envelope(is_dm=False, text="/foo"),
            factory=factory,
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "policy-silent"

    async def test_policy_gate_command_intercept_in_dm_does_not_invoke_gate(
        self, isolated_db
    ) -> None:
        """A DM message that's ALSO a slash command hits step 11
        FIRST; the command-intercept block emits the response and
        returns. The gate NEVER evaluates. Audit entry has
        ``disposition="command-intercepted"`` (NOT ``"policy-silent"``,
        NOT ``"stepped"``). Pins DD §1's 'DMs ignore policy gate' against
        the step-11-before-gate ordering reality."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        # ``/help`` is a known built-in command → step 11 intercepts
        # before the gate runs.
        await dispatch_inbound(
            "acct-test",
            _envelope(is_dm=True, text="/help"),
            factory=factory,
        )

        session_id = await _first_session_id()
        routing = await _routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["disposition"] == "command-intercepted"
        # Engaged-and-intercepted audit entries do NOT carry the
        # policy sub-block; the gate never ran.
        assert "policy" not in entry
