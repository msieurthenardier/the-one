"""Tests for the DD-2 config validator on ``Connector.config``.

Mission 23 Flight 2 Leg 1. Replaces the pre-reset 430-line ACL/routing
schema with a compact reserved-key validator.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_one.db.models import Connector


def _connector(config: dict) -> Connector:
    return Connector(id="c1", name="Test", type="stub", config=config)


def test_empty_config_is_valid() -> None:
    conn = _connector({})
    assert conn.config == {}


def test_all_reserved_keys_accepted() -> None:
    config = {
        "default_agent": "bot",
        "channel_map": {"ch-1": "bot"},
        "allowlist": {"peers": ["p1"], "channels": ["ch-1"]},
        "always_listen": ["ch-1"],
    }
    conn = _connector(config)
    assert conn.config == config


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown key"):
        _connector({"routing_rules": []})


def test_default_agent_must_be_string() -> None:
    with pytest.raises(ValidationError, match="default_agent"):
        _connector({"default_agent": 123})


def test_channel_map_must_be_str_to_str() -> None:
    with pytest.raises(ValidationError, match="channel_map"):
        _connector({"channel_map": {"ch-1": 123}})


def test_allowlist_rejects_unknown_axis() -> None:
    with pytest.raises(ValidationError, match="allowlist"):
        _connector({"allowlist": {"roles": ["r1"]}})


def test_allowlist_peers_must_be_list_of_str() -> None:
    with pytest.raises(ValidationError, match="allowlist"):
        _connector({"allowlist": {"peers": [1, 2]}})


def test_allowlist_channels_must_be_list_of_str() -> None:
    with pytest.raises(ValidationError, match="allowlist"):
        _connector({"allowlist": {"channels": "not-a-list"}})


def test_always_listen_must_be_list_of_str() -> None:
    with pytest.raises(ValidationError, match="always_listen"):
        _connector({"always_listen": "ch-1"})
