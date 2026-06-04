"""Routing-schema validator tests for F7 L2's extension of
``Connector._validate_config_reserved_keys`` to recognize the
third reserved top-level config key ``"routing"``.

Pins the shape contract:
- valid round-trip
- ``routing = None`` accepted
- exact-keys enforcement (no extra; no missing)
- per-rule shape (scope, match, agent — all required, all type-checked)
- scope in {channel, thread, dm, peer} (case-sensitive)
- match is a non-empty ``list[str]`` of non-empty strings
- default in {None, non-empty str}

The routing engine in F7 L4 consumes the validated shape; F7 L5
dispatcher composes with the engine; F7 L7 Studio editor authors
through the API write path. The validator at the model layer is the
single point of contract enforcement.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_one.db.models import Connector


def _account(config: dict | None = None) -> Connector:
    """Minimal ``Connector`` fixture builder.

    Constructs a stub-shaped account with the given ``config``; all
    other fields (``name``/``type``/``secrets``) default sensibly. The
    Pydantic model fills timestamps via ``Field(default_factory=now_iso)``.
    """
    return Connector(
        id="acc-1",
        name="test",
        type="stub",
        config=config if config is not None else {},
        secrets={},
    )


class TestRoutingSchema:
    """Shape-contract tests for ``config["routing"]``."""

    # ── Top-level shape: presence / absence / round-trip ───────────

    def test_valid_full_round_trip(self) -> None:
        """Full valid shape round-trips byte-equal through the validator."""
        routing = {
            "rules": [
                {"scope": "channel", "match": ["C1"], "agent": "alice"},
            ],
            "default": "bob",
        }
        acc = _account(config={"routing": routing})
        assert acc.config["routing"] == routing

    def test_valid_multi_value_match_round_trip(self) -> None:
        """A rule with multiple match values round-trips byte-equal."""
        routing = {
            "rules": [
                {
                    "scope": "peer",
                    "match": ["P1", "P2", "P3"],
                    "agent": "bob",
                },
            ],
            "default": None,
        }
        acc = _account(config={"routing": routing})
        assert acc.config["routing"] == routing

    def test_routing_none_accepted(self) -> None:
        """``routing = None`` is treated as absent — no error."""
        acc = _account(config={"routing": None})
        assert acc.config["routing"] is None

    def test_routing_absent_accepted(self) -> None:
        """No ``routing`` key at all — config is schema-loose on absence."""
        acc = _account(config={})
        assert "routing" not in acc.config

    def test_routing_empty_dict_rejected(self) -> None:
        """``routing = {}`` rejected — missing required keys."""
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": {}})
        assert "missing required keys" in str(exc.value)
        # The sorted output is alphabetical: ['default', 'rules']
        assert "default" in str(exc.value)
        assert "rules" in str(exc.value)

    def test_routing_missing_default_rejected(self) -> None:
        """``routing = {"rules": []}`` rejected — missing ``default``."""
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": {"rules": []}})
        assert "missing required keys" in str(exc.value)
        assert "default" in str(exc.value)

    def test_routing_empty_rules_with_null_default_accepted(self) -> None:
        """``{"rules": [], "default": None}`` is the valid empty form."""
        acc = _account(config={"routing": {"rules": [], "default": None}})
        assert acc.config["routing"] == {"rules": [], "default": None}

    def test_routing_extra_top_level_key_rejected(self) -> None:
        """Extra top-level keys in ``routing`` are rejected."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [],
                        "default": None,
                        "extra": "x",
                    }
                }
            )
        assert "unexpected keys" in str(exc.value)
        assert "extra" in str(exc.value)

    def test_routing_not_a_dict_rejected(self) -> None:
        """``routing`` must be a dict."""
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": "not-a-dict"})
        assert "must be a dict" in str(exc.value)

    def test_routing_rules_not_a_list_rejected(self) -> None:
        """``routing["rules"]`` must be a list."""
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": {"rules": "nope", "default": None}})
        assert "must be a list" in str(exc.value)

    # ── Per-rule shape ────────────────────────────────────────────

    def test_rule_not_a_dict_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": {"rules": ["not-a-dict"], "default": None}})
        assert "must be a dict" in str(exc.value)

    def test_rule_missing_scope_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"match": ["C1"], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "missing required keys" in str(exc.value)
        assert "scope" in str(exc.value)

    def test_rule_missing_match_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "missing required keys" in str(exc.value)
        assert "match" in str(exc.value)

    def test_rule_missing_agent_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": ["C1"]}],
                        "default": None,
                    }
                }
            )
        assert "missing required keys" in str(exc.value)
        assert "agent" in str(exc.value)

    def test_rule_extra_key_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [
                            {
                                "scope": "channel",
                                "match": ["C1"],
                                "agent": "a",
                                "extra": "x",
                            }
                        ],
                        "default": None,
                    }
                }
            )
        assert "unexpected keys" in str(exc.value)
        assert "extra" in str(exc.value)

    # ── Scope ─────────────────────────────────────────────────────

    @pytest.mark.parametrize("scope", ["channel", "thread", "dm", "peer"])
    def test_rule_valid_scope_accepted(self, scope: str) -> None:
        acc = _account(
            config={
                "routing": {
                    "rules": [{"scope": scope, "match": ["M1"], "agent": "a"}],
                    "default": None,
                }
            }
        )
        assert acc.config["routing"]["rules"][0]["scope"] == scope

    def test_rule_scope_case_sensitive(self) -> None:
        """`Channel` (capitalized) is not in the enum — rejected."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "Channel", "match": ["C1"], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "must be one of" in str(exc.value)

    def test_rule_scope_not_in_enum_rejected(self) -> None:
        """`group` is not a valid scope."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "group", "match": ["C1"], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "must be one of" in str(exc.value)

    def test_rule_scope_not_a_string_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": 42, "match": ["C1"], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "must be one of" in str(exc.value)

    # ── Match ─────────────────────────────────────────────────────

    def test_legacy_match_str_coerced_to_singleton_list_on_read(self) -> None:
        """Pre-HAT2 ``match: str`` form is coerced in-place to ``[str]``.

        HAT iteration 3: the validator accepts the legacy single-value
        string form on the READ path and normalizes it to the new
        multi-value list form in the validated dict. Subsequent writes
        round-trip the coerced shape — each row converges to the new
        form on next save. Writes still require ``match: list[str]``;
        only the read path coerces.
        """
        acc = _account(
            config={
                "routing": {
                    "rules": [{"scope": "channel", "match": "C1", "agent": "alpha"}],
                    "default": None,
                }
            }
        )
        assert acc.config["routing"]["rules"][0]["match"] == ["C1"]

    def test_legacy_match_empty_string_still_rejects(self) -> None:
        """``match: ""`` coerces to ``[""]`` and then fails per-element check.

        The legacy-shape coercion only normalizes the container; the
        per-element non-empty-string contract still applies. An empty
        string is not a valid match value under either shape.
        """
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": "", "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "non-empty string" in str(exc.value)

    def test_rule_match_empty_list_rejected(self) -> None:
        """An empty list is rejected — at least one value required."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": [], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "non-empty list" in str(exc.value)

    def test_rule_match_not_a_list_rejected(self) -> None:
        """``match`` must be a list (not int, dict, etc.)."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": 42, "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "non-empty list" in str(exc.value)

    def test_rule_match_element_empty_string_rejected(self) -> None:
        """Empty string in the match list is rejected."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": ["C1", ""], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "non-empty string" in str(exc.value)

    def test_rule_match_element_not_a_string_rejected(self) -> None:
        """Non-string element in the match list is rejected."""
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": ["C1", 42], "agent": "a"}],
                        "default": None,
                    }
                }
            )
        assert "non-empty string" in str(exc.value)

    # ── Agent ─────────────────────────────────────────────────────

    def test_rule_agent_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": ["C1"], "agent": ""}],
                        "default": None,
                    }
                }
            )
        assert "non-empty string" in str(exc.value)

    def test_rule_agent_not_a_string_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(
                config={
                    "routing": {
                        "rules": [{"scope": "channel", "match": ["C1"], "agent": 42}],
                        "default": None,
                    }
                }
            )
        assert "non-empty string" in str(exc.value)

    # ── Default ───────────────────────────────────────────────────

    def test_default_none_accepted(self) -> None:
        acc = _account(config={"routing": {"rules": [], "default": None}})
        assert acc.config["routing"]["default"] is None

    def test_default_non_empty_string_accepted(self) -> None:
        acc = _account(config={"routing": {"rules": [], "default": "alice"}})
        assert acc.config["routing"]["default"] == "alice"

    def test_default_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": {"rules": [], "default": ""}})
        assert "non-empty string" in str(exc.value)

    def test_default_wrong_type_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _account(config={"routing": {"rules": [], "default": 42}})
        assert "non-empty string" in str(exc.value)
