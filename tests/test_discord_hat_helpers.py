"""Hermetic unit tests for the pure helper functions in the Discord HAT driver.

These tests exercise ``latest_routing_entry``, ``inbound_peer_names``, and
``routing_len`` from ``tests.live.discord_hat.driver`` against fixture dicts
shaped like the real session-detail / inbound-message payloads. No Discord
connection, no credentials, no network — safe to run in the default suite.

Import path uses the established ``from tests.…`` absolute form (the same
mechanism used by ``tests/test_connectors_commands.py:44``); this works
because ``pyproject.toml`` sets ``--import-mode=importlib`` and
``pythonpath=["tests"]``.

NOT marked ``discord_hat`` or ``live`` — runs in the default backend suite.
"""

from __future__ import annotations

from tests.live.discord_hat.driver import (
    inbound_peer_names,
    latest_routing_entry,
    routing_len,
)

# ── fixture shapes ──────────────────────────────────────────────────────────
# Shaped exactly like real session-detail dicts returned by
# GET /api/chat/sessions/{id}: top-level "messages" list + "session_metadata"
# dict with a "routing" list. Shapes verified against F15 scenario assertions
# (see F15 flight log L3–L6 live-run evidence).


def _detail_with_routing(*entries: dict) -> dict:
    """Build a session-detail dict with the given routing entries."""
    return {"session_metadata": {"routing": list(entries)}}


def _detail_with_messages(*messages: dict) -> dict:
    """Build a session-detail dict with the given messages."""
    return {"messages": list(messages)}


def _detail_with_both(messages: list[dict], routing: list[dict]) -> dict:
    """Build a session-detail dict with messages and routing."""
    return {"messages": messages, "session_metadata": {"routing": routing}}


def _stepped_entry(agent: str = "Connector Agent 1") -> dict:
    """A minimal stepped routing entry (real shape from F15 L4 live run)."""
    return {
        "ts": "2026-06-02T12:00:00.000000",
        "agent": agent,
        "rule_index": None,
        "scope": "default",
        "match": [],
        "reason": "default",
        "disposition": "stepped",
    }


def _policy_silent_entry() -> dict:
    """A minimal policy-silent routing entry (real shape from F15 L3 live run)."""
    return {
        "ts": "2026-06-02T12:00:01.000000",
        "agent": None,
        "rule_index": None,
        "scope": None,
        "match": [],
        "reason": "always-listen-off",
        "disposition": "policy-silent",
        "policy": {"outcome": "always-listen-off"},
    }


def _user_message(peer_name: str, content: str = "hello") -> dict:
    """An inbound (role=user) message with a peer_name (F6 attribution shape)."""
    return {
        "role": "user",
        "content": content,
        "peer_name": peer_name,
    }


def _assistant_message(content: str = "hello back") -> dict:
    """An outbound (role=assistant) message — peer_name absent/ignored."""
    return {
        "role": "assistant",
        "content": content,
    }


# ── latest_routing_entry ────────────────────────────────────────────────────


class TestLatestRoutingEntry:
    def test_returns_last_entry_when_multiple(self) -> None:
        e1 = _stepped_entry("Connector Agent 1")
        e2 = _policy_silent_entry()
        detail = _detail_with_routing(e1, e2)
        result = latest_routing_entry(detail)
        assert result is e2

    def test_returns_single_entry(self) -> None:
        e = _stepped_entry()
        detail = _detail_with_routing(e)
        result = latest_routing_entry(detail)
        assert result is e

    def test_returns_none_on_empty_routing(self) -> None:
        detail = _detail_with_routing()
        result = latest_routing_entry(detail)
        assert result is None

    def test_returns_none_on_missing_session_metadata(self) -> None:
        result = latest_routing_entry({"messages": []})
        assert result is None

    def test_returns_none_on_empty_dict(self) -> None:
        result = latest_routing_entry({})
        assert result is None

    def test_returns_none_when_routing_is_null(self) -> None:
        # routing key present but null (e.g. before any dispatch)
        result = latest_routing_entry({"session_metadata": {"routing": None}})
        assert result is None

    def test_preserves_entry_fields(self) -> None:
        e = _stepped_entry("Connector Agent 2")
        detail = _detail_with_routing(e)
        result = latest_routing_entry(detail)
        assert result is not None
        assert result["disposition"] == "stepped"
        assert result["agent"] == "Connector Agent 2"

    def test_policy_silent_entry_has_policy_key(self) -> None:
        e = _policy_silent_entry()
        detail = _detail_with_routing(e)
        result = latest_routing_entry(detail)
        assert result is not None
        assert result["disposition"] == "policy-silent"
        assert result.get("policy", {}).get("outcome") == "always-listen-off"


# ── inbound_peer_names ──────────────────────────────────────────────────────


class TestInboundPeerNames:
    def test_extracts_peer_names_from_user_messages(self) -> None:
        detail = _detail_with_messages(
            _user_message("HAT Test Bot 1"),
            _user_message("HAT Test Bot 2"),
        )
        result = inbound_peer_names(detail)
        assert result == ["HAT Test Bot 1", "HAT Test Bot 2"]

    def test_excludes_assistant_messages(self) -> None:
        # The F6 peer attribution is only on user-role messages; assistant
        # messages carry no peer_name (and inbound_peer_names must filter role).
        detail = _detail_with_messages(
            _user_message("HAT Test Bot 1"),
            _assistant_message("I can help with that"),
        )
        result = inbound_peer_names(detail)
        assert result == ["HAT Test Bot 1"]

    def test_excludes_messages_without_peer_name(self) -> None:
        detail = _detail_with_messages(
            {"role": "user", "content": "no name here"},
        )
        result = inbound_peer_names(detail)
        assert result == []

    def test_returns_empty_on_empty_messages(self) -> None:
        result = inbound_peer_names({"messages": []})
        assert result == []

    def test_returns_empty_on_missing_messages_key(self) -> None:
        result = inbound_peer_names({})
        assert result == []

    def test_returns_empty_on_null_messages(self) -> None:
        result = inbound_peer_names({"messages": None})
        assert result == []

    def test_preserves_order(self) -> None:
        # F15 L4 multi-user: 3 bots post in order; peer_names accumulate in
        # message order, which is posting order under the per-session lock.
        names = ["HAT Test Bot 1", "HAT Test Bot 2", "HAT Test Bot 3"]
        detail = _detail_with_messages(*[_user_message(n) for n in names])
        result = inbound_peer_names(detail)
        assert result == names

    def test_mixed_roles_only_returns_user_names(self) -> None:
        detail = _detail_with_messages(
            _user_message("Bot A"),
            _assistant_message("reply 1"),
            _user_message("Bot B"),
            _assistant_message("reply 2"),
        )
        result = inbound_peer_names(detail)
        assert result == ["Bot A", "Bot B"]


# ── routing_len ─────────────────────────────────────────────────────────────


class TestRoutingLen:
    """Tests for the ``routing_len`` helper — the before/after count logic
    that ``post_and_wait_new_routing`` keys on to detect a NEW routing entry.
    The real production logic is extracted here, so these tests cover the
    actual code path rather than a re-inlined copy.
    """

    def test_returns_zero_on_empty_routing(self) -> None:
        detail = _detail_with_routing()
        assert routing_len(detail) == 0

    def test_returns_count_with_entries(self) -> None:
        detail = _detail_with_routing(
            _stepped_entry(),
            _policy_silent_entry(),
            _stepped_entry("Connector Agent 2"),
        )
        assert routing_len(detail) == 3

    def test_returns_zero_on_missing_session_metadata(self) -> None:
        assert routing_len({"messages": []}) == 0

    def test_returns_zero_on_empty_dict(self) -> None:
        assert routing_len({}) == 0

    def test_returns_zero_when_routing_is_null(self) -> None:
        assert routing_len({"session_metadata": {"routing": None}}) == 0

    def test_before_after_pattern(self) -> None:
        """Simulates the before/after pattern in post_and_wait_new_routing."""
        before_detail = _detail_with_routing(_stepped_entry())
        before = routing_len(before_detail)

        # Simulate a new entry landing after posting.
        after_detail = _detail_with_routing(
            _stepped_entry(),
            _stepped_entry("Connector Agent 2"),
        )
        after = routing_len(after_detail)

        assert before == 1
        assert after == 2
        assert after > before  # the "new entry landed" predicate

    def test_single_entry(self) -> None:
        detail = _detail_with_routing(_stepped_entry())
        assert routing_len(detail) == 1
