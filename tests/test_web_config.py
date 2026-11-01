"""Tests for ``the_one.tools._web_config.WebConfig`` (F5 L1).

Covers:

* Default values for the seven fields.
* ``Field(ge=, le=)`` bounds enforcement on each numeric field.
* The ``_default_le_max`` cross-field validator (F4 D1 / F5 D10).
* ``frozen=True`` posture — mutation raises ``pydantic.ValidationError``.
* List-typed defaults are *lists* (not tuples) per the F4 D3 lesson.
* Resolver narrowing semantics for each Narrow/NarrowSuperset field.
* ``redirect_cap`` markerless rejection at the resolver level (F5 D9).
* Mission invariant lock: no ``disable_ssrf*`` field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_one.tools._web_config import WebConfig
from the_one.tools.resolver import resolve

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestWebConfigDefaults:
    def test_field_count_is_eight(self) -> None:
        # 7 F5 fields + `default_user_agent` (post-debrief addition).
        # M16 F08 L01 (HIGH-1): the M16 F07 web text LLM-context cap field was
        # RETIRED — the central context-budget governor in `Agent._execute_tool`
        # now bounds every tool result. That drops the count 9 → 8 (the exact
        # F07 0.2.6 failure mode, now tracked).
        assert len(WebConfig.model_fields) == 8

    def test_default_values(self) -> None:
        from the_one.tools._web_config import _DEFAULT_USER_AGENT

        c = WebConfig()
        assert c.timeout_seconds_default == 30
        assert c.timeout_seconds_max == 120
        assert c.response_size_cap_bytes == 1_048_576
        assert c.redirect_cap == 5
        assert c.host_allowlist == []
        assert c.host_denylist == []
        assert c.extra_allowed_hosts == []
        assert c.default_user_agent == _DEFAULT_USER_AGENT

    def test_list_defaults_are_lists_not_tuples(self) -> None:
        """Resolver's ``_check_narrow_superset`` requires ``isinstance(tool_val, list)``;
        F4 D3 lesson on ``command_denylist`` applies here too."""
        c = WebConfig()
        assert isinstance(c.host_allowlist, list)
        assert isinstance(c.host_denylist, list)
        assert isinstance(c.extra_allowed_hosts, list)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


class TestWebConfigBounds:
    def test_timeout_default_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(timeout_seconds_default=0)

    def test_timeout_default_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(timeout_seconds_default=3601)

    def test_timeout_max_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(timeout_seconds_max=0)

    def test_timeout_max_above_ceiling_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(timeout_seconds_max=3601)

    def test_response_size_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(response_size_cap_bytes=1023)

    def test_response_size_above_ceiling_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(response_size_cap_bytes=104_857_601)

    def test_redirect_cap_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(redirect_cap=-1)

    def test_redirect_cap_zero_allowed(self) -> None:
        """0 is a valid value: disables redirects entirely."""
        c = WebConfig(redirect_cap=0)
        assert c.redirect_cap == 0

    def test_redirect_cap_above_ceiling_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WebConfig(redirect_cap=21)

    def test_redirect_cap_at_ceiling_allowed(self) -> None:
        c = WebConfig(redirect_cap=20)
        assert c.redirect_cap == 20


# ---------------------------------------------------------------------------
# Cross-field validator (default <= max)
# ---------------------------------------------------------------------------


class TestDefaultLeMaxValidator:
    def test_default_greater_than_max_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            WebConfig(timeout_seconds_default=200, timeout_seconds_max=100)
        assert "must be <=" in str(exc.value)

    def test_default_equal_to_max_allowed(self) -> None:
        c = WebConfig(timeout_seconds_default=60, timeout_seconds_max=60)
        assert c.timeout_seconds_default == 60
        assert c.timeout_seconds_max == 60

    def test_default_less_than_max_allowed(self) -> None:
        c = WebConfig(timeout_seconds_default=15, timeout_seconds_max=60)
        assert c.timeout_seconds_default == 15
        assert c.timeout_seconds_max == 60


# ---------------------------------------------------------------------------
# frozen=True posture
# ---------------------------------------------------------------------------


class TestWebConfigFrozen:
    def test_attribute_assignment_raises(self) -> None:
        c = WebConfig()
        with pytest.raises(ValidationError):
            c.timeout_seconds_default = 999  # type: ignore[misc]

    def test_list_field_attribute_assignment_raises(self) -> None:
        c = WebConfig()
        with pytest.raises(ValidationError):
            c.host_allowlist = ["x.com"]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Resolver narrowing semantics
# ---------------------------------------------------------------------------


class TestWebConfigNarrowing:
    def test_narrow_int_default_narrows(self) -> None:
        cfg = resolve(
            WebConfig,
            {"timeout_seconds_default": 30, "timeout_seconds_max": 120},
            {"timeout_seconds_default": 10},
        )
        assert cfg.timeout_seconds_default == 10

    def test_narrow_int_widening_raises(self) -> None:
        with pytest.raises(ValueError, match="widens"):
            resolve(
                WebConfig,
                {"timeout_seconds_default": 30, "timeout_seconds_max": 120},
                {"timeout_seconds_max": 600},
            )

    def test_narrow_response_size_narrows(self) -> None:
        cfg = resolve(
            WebConfig,
            {"response_size_cap_bytes": 1_048_576},
            {"response_size_cap_bytes": 102_400},
        )
        assert cfg.response_size_cap_bytes == 102_400

    def test_narrow_host_allowlist_subset_passes(self) -> None:
        cfg = resolve(
            WebConfig,
            {"host_allowlist": ["a.com", "b.com", "c.com"]},
            {"host_allowlist": ["a.com"]},
        )
        assert cfg.host_allowlist == ["a.com"]

    def test_narrow_host_allowlist_widening_raises(self) -> None:
        with pytest.raises(ValueError, match="widens"):
            resolve(
                WebConfig,
                {"host_allowlist": ["a.com"]},
                {"host_allowlist": ["a.com", "b.com"]},
            )

    def test_narrow_extra_allowed_hosts_subset_passes(self) -> None:
        cfg = resolve(
            WebConfig,
            {"extra_allowed_hosts": ["localhost:11434", "127.0.0.1:8080"]},
            {"extra_allowed_hosts": ["localhost:11434"]},
        )
        assert cfg.extra_allowed_hosts == ["localhost:11434"]

    def test_narrow_extra_allowed_hosts_widening_raises(self) -> None:
        with pytest.raises(ValueError, match="widens"):
            resolve(
                WebConfig,
                {"extra_allowed_hosts": ["localhost:11434"]},
                {"extra_allowed_hosts": ["localhost:11434", "rogue.host:9999"]},
            )

    def test_narrow_superset_host_denylist_superset_passes(self) -> None:
        cfg = resolve(
            WebConfig,
            {"host_denylist": ["evil.com"]},
            {"host_denylist": ["evil.com", "evil2.com"]},
        )
        assert cfg.host_denylist == ["evil.com", "evil2.com"]

    def test_narrow_superset_host_denylist_dropping_operator_entry_is_unioned_back(self) -> None:
        cfg = resolve(
            WebConfig,
            {"host_denylist": ["evil.com", "evil2.com"]},
            {"host_denylist": ["evil.com"]},
        )
        assert cfg.host_denylist == ["evil.com", "evil2.com"]


# ---------------------------------------------------------------------------
# Field-only redirect_cap — markerless rejection at resolver level
# ---------------------------------------------------------------------------


class TestRedirectCapMarkerlessRejection:
    def test_redirect_cap_agent_override_raises_at_resolver(self) -> None:
        """F5 Decision 9: ``redirect_cap`` is operator-only. Agent override
        on this key MUST raise ``ValueError`` from the resolver. Pin at the
        resolver level (NOT at AgentFactory.create — that's L2's concern).
        """
        with pytest.raises(ValueError) as exc:
            resolve(WebConfig, {}, {"redirect_cap": 0})
        assert "no Narrow/Substitute marker" in str(exc.value)

    def test_redirect_cap_tool_level_only_passes(self) -> None:
        """Operator-only override (no agent override) is fine."""
        cfg = resolve(WebConfig, {"redirect_cap": 3}, None)
        assert cfg.redirect_cap == 3

    def test_redirect_cap_no_agent_override_uses_tool_value(self) -> None:
        cfg = resolve(WebConfig, {"redirect_cap": 7}, {})
        assert cfg.redirect_cap == 7


# ---------------------------------------------------------------------------
# Mission invariant lock — no full-disable toggle
# ---------------------------------------------------------------------------


class TestNoSSRFDisableField:
    """Mission constraint: SSRF protection is on by default and there is NO
    way to fully disable it. The ONLY opt-out is ``extra_allowed_hosts``.
    Lock-test at the schema level so a future PR cannot silently introduce
    a disable toggle.
    """

    def test_no_disable_ssrf_field(self) -> None:
        assert "disable_ssrf" not in WebConfig.model_fields
        assert "ssrf_disabled" not in WebConfig.model_fields
        assert "disable_ssrf_protection" not in WebConfig.model_fields


class TestDefaultUserAgent:
    """Post-F5-debrief addition: `default_user_agent` is a `Substitute`-marked
    field on `WebConfig` so operators can set the baseline UA and agents can
    fully replace it (no narrowing semantic — UA strings aren't ordered)."""

    def test_default_value_is_the_one_ua(self) -> None:
        from the_one.tools._web_config import _DEFAULT_USER_AGENT

        c = WebConfig()
        assert c.default_user_agent == _DEFAULT_USER_AGENT

    def test_substitute_marker_allows_agent_replacement(self) -> None:
        from the_one.tools.resolver import resolve

        operator_cfg = {"default_user_agent": "the-one/0.2"}
        agent_override = {"default_user_agent": "Mozilla/5.0 ResearchAgent/1.0"}
        merged = resolve(WebConfig, operator_cfg, agent_override)
        assert merged.default_user_agent == "Mozilla/5.0 ResearchAgent/1.0"

    def test_no_narrowing_constraint_on_substitute(self) -> None:
        """`Substitute` semantic — agent's value just replaces operator's;
        no ordering is checked. A string `"Z"` overrides an operator-set
        `"A"` without raising."""
        from the_one.tools.resolver import resolve

        # Both directions work: operator long, agent short, and vice versa.
        for op_val, agent_val in [
            ("the-one/0.2", "ShortUA/1"),
            ("ShortUA/1", "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0"),
        ]:
            merged = resolve(
                WebConfig,
                {"default_user_agent": op_val},
                {"default_user_agent": agent_val},
            )
            assert merged.default_user_agent == agent_val


# ---------------------------------------------------------------------------
# WebSearchConfig — field-count + secret-marker guard (M16 F08 L02)
# ---------------------------------------------------------------------------


class TestWebSearchConfig:
    """M16 F08 L02 — ``WebSearchConfig`` is the per-tool Config for
    ``web_search`` (split off the shared ``WebConfig``). Mirrors
    ``TestWebConfigDefaults.test_field_count_is_eight`` so a future PR cannot
    silently add/drop a field, and pins that every secret field carries the
    ``secret:true`` marker (the leg-3 encrypted-split + tools-admin form key
    off this marker)."""

    def test_field_count_is_six(self) -> None:
        from the_one.tools._web_search_config import WebSearchConfig

        # search_backend + searxng_base_url + google_pse_api_key +
        # google_pse_cse_id + brave_api_key + tavily_api_key.
        assert len(WebSearchConfig.model_fields) == 6

    def test_default_backend_is_duckduckgo(self) -> None:
        from the_one.tools._web_search_config import WebSearchConfig

        assert WebSearchConfig().search_backend == "duckduckgo"

    def test_backend_dropdown_marker(self) -> None:
        from the_one.tools._web_search_config import WebSearchConfig

        extra = WebSearchConfig.model_fields["search_backend"].json_schema_extra
        assert extra["ui_hint"] == "dropdown"
        choice_values = {c["value"] for c in extra["ui_choices"]}
        assert choice_values == {"duckduckgo", "searxng", "google_pse", "brave", "tavily"}

    def test_secret_fields_carry_secret_marker(self) -> None:
        from the_one.tools._web_search_config import (
            WEB_SEARCH_SECRET_FIELDS,
            WebSearchConfig,
        )

        # The declared secret set is exactly the three keyed-engine API keys.
        assert WEB_SEARCH_SECRET_FIELDS == (
            "google_pse_api_key",
            "brave_api_key",
            "tavily_api_key",
        )
        for name in WEB_SEARCH_SECRET_FIELDS:
            extra = WebSearchConfig.model_fields[name].json_schema_extra
            assert extra is not None, name
            assert extra.get("secret") is True, name
            assert extra.get("ui_hint") == "password", name

    def test_non_secret_fields_lack_secret_marker(self) -> None:
        """``searxng_base_url`` and ``google_pse_cse_id`` are NOT secrets —
        they must not carry the ``secret:true`` marker (so leg 3 does not
        encrypt them)."""
        from the_one.tools._web_search_config import WebSearchConfig

        for name in ("searxng_base_url", "google_pse_cse_id"):
            extra = WebSearchConfig.model_fields[name].json_schema_extra or {}
            assert extra.get("secret") is not True, name

    def test_frozen(self) -> None:
        from the_one.tools._web_search_config import WebSearchConfig

        c = WebSearchConfig()
        with pytest.raises(ValidationError):
            c.search_backend = "tavily"  # type: ignore[misc]

    def test_secret_field_operator_only_at_resolver(self) -> None:
        """Secret fields carry NO resolver marker, so an agent override raises
        ``ValueError`` (operator-only — agents cannot set search secrets),
        mirroring ``WebConfig.redirect_cap``."""
        from the_one.tools._web_search_config import WebSearchConfig

        with pytest.raises(ValueError) as exc:
            resolve(WebSearchConfig, {}, {"tavily_api_key": "agent-set"})
        assert "no Narrow/Substitute marker" in str(exc.value)
