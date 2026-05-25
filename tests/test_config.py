"""Tests for the_one.agent.config module."""

from __future__ import annotations

import pytest

from the_one.agent.config import BASE_PROMPT, AgentConfig

# ===================================================================
# AgentConfig construction
# ===================================================================


class TestAgentConfigConstruction:
    """Test AgentConfig model construction and defaults."""

    def test_minimal_construction(self):
        cfg = AgentConfig(name="test-agent")
        assert cfg.name == "test-agent"
        assert cfg.description == ""
        assert cfg.provider_config_id is None
        assert cfg.llm_model == ""
        assert cfg.system_prompt == ""
        assert cfg.enabled_tools is None
        assert cfg.disabled_tools == []
        assert cfg.max_iterations == 20

    def test_all_fields(self):
        cfg = AgentConfig(
            name="custom",
            description="A custom agent",
            provider_config_id="prov-123",
            llm_model="gpt-4",
            system_prompt="You are helpful.",
            enabled_tools=["tool_a"],
            disabled_tools=["tool_b"],
            max_iterations=5,
        )
        assert cfg.name == "custom"
        assert cfg.description == "A custom agent"
        assert cfg.provider_config_id == "prov-123"
        assert cfg.llm_model == "gpt-4"
        assert cfg.system_prompt == "You are helpful."
        assert cfg.enabled_tools == ["tool_a"]
        assert cfg.disabled_tools == ["tool_b"]
        assert cfg.max_iterations == 5

    def test_extra_fields_ignored(self):
        """Old JSON configs with llm_provider/llm_base_url should not raise."""
        cfg = AgentConfig(
            name="legacy",
            llm_provider="ollama",
            llm_base_url="http://localhost:11434/v1",
        )
        assert cfg.name == "legacy"
        assert cfg.provider_config_id is None
        assert not hasattr(cfg, "llm_provider")
        assert not hasattr(cfg, "llm_base_url")

    def test_connector_account_ids_defaults_to_empty_list(self):
        """M10 F4: ``connector_account_ids`` mirrors ``mcp_source_ids`` —
        empty list is the no-attached state, not None."""
        cfg = AgentConfig(name="t")
        assert cfg.connector_account_ids == []

    def test_connector_account_ids_round_trip(self):
        """Non-empty ``connector_account_ids`` survives model_dump →
        model_validate."""
        cfg = AgentConfig(name="t", connector_account_ids=["acc-a", "acc-b"])
        dumped = cfg.model_dump()
        assert dumped["connector_account_ids"] == ["acc-a", "acc-b"]
        revived = AgentConfig.model_validate(dumped)
        assert revived.connector_account_ids == ["acc-a", "acc-b"]

    def test_pre_f4_row_deserializes_with_empty_connector_account_ids(self):
        """Back-compat: pre-F4 stored agent rows have no
        ``connector_account_ids`` key; field defaults to []."""
        cfg = AgentConfig.model_validate({"name": "t"})
        assert cfg.connector_account_ids == []


# ===================================================================
# tool_overrides field
# ===================================================================


class TestToolOverridesField:
    """Tests for AgentConfig.tool_overrides — Decision 1 + Decision 6 Q&A."""

    def test_default_is_none(self):
        """Locked-down NULL: no overrides set means None, not {}."""
        cfg = AgentConfig(name="t")
        assert cfg.tool_overrides is None

    def test_explicit_dict_roundtrips_through_model_dump_then_validate(self):
        """An explicit overrides dict survives model_dump → model_validate."""
        cfg = AgentConfig(
            name="t",
            tool_overrides={"shell": {"timeout": 30}, "read_file": {"max_bytes": 1000}},
        )
        dumped = cfg.model_dump()
        assert dumped["tool_overrides"] == {
            "shell": {"timeout": 30},
            "read_file": {"max_bytes": 1000},
        }
        revived = AgentConfig.model_validate(dumped)
        assert revived.tool_overrides == cfg.tool_overrides

    def test_extra_ignore_survives_stale_direct_actions_payload(self):
        """Regression check from F1: model_config['extra'] == 'ignore' so a
        stale `direct_actions: true` payload is silently dropped, NOT a
        ValidationError. Locked-down by F1; pinned here so the new field
        addition doesn't accidentally flip extra='allow'."""
        assert AgentConfig.model_config["extra"] == "ignore"
        cfg = AgentConfig.model_validate(
            {"name": "stale", "direct_actions": True, "tool_overrides": None}
        )
        assert cfg.name == "stale"
        assert not hasattr(cfg, "direct_actions")
        assert cfg.tool_overrides is None

    def test_outer_non_dict_raises_validation_error(self):
        """A list or string at the top level fails Pydantic validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentConfig.model_validate({"name": "t", "tool_overrides": [1, 2, 3]})

    def test_inner_non_dict_raises_validation_error(self):
        """An inner string/list fails validation thanks to dict[str, Any]
        inner type — bare `dict` would silently accept this case."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentConfig.model_validate({"name": "t", "tool_overrides": {"shell": "not-a-dict"}})

        with pytest.raises(ValidationError):
            AgentConfig.model_validate({"name": "t", "tool_overrides": {"shell": [1, 2, 3]}})


# ===================================================================
# is_tool_enabled
# ===================================================================


class TestIsToolEnabled:
    """Test is_tool_enabled() logic paths."""

    def test_no_filters_allows_all(self):
        cfg = AgentConfig(name="t")
        assert cfg.is_tool_enabled("anything") is True

    def test_whitelist_only_allows_listed(self):
        cfg = AgentConfig(name="t", enabled_tools=["alpha", "beta"])
        assert cfg.is_tool_enabled("alpha") is True
        assert cfg.is_tool_enabled("gamma") is False

    def test_blacklist_only_blocks_listed(self):
        cfg = AgentConfig(name="t", disabled_tools=["alpha"])
        assert cfg.is_tool_enabled("alpha") is False
        assert cfg.is_tool_enabled("beta") is True

    def test_both_disabled_takes_precedence(self):
        cfg = AgentConfig(name="t", enabled_tools=["alpha", "beta"], disabled_tools=["alpha"])
        assert cfg.is_tool_enabled("alpha") is False
        assert cfg.is_tool_enabled("beta") is True

    def test_empty_whitelist_blocks_all(self):
        cfg = AgentConfig(name="t", enabled_tools=[])
        assert cfg.is_tool_enabled("anything") is False

    def test_empty_blacklist_blocks_none(self):
        cfg = AgentConfig(name="t", disabled_tools=[])
        assert cfg.is_tool_enabled("anything") is True


# ===================================================================
# get_system_prompt
# ===================================================================


class TestGetSystemPrompt:
    """Test get_system_prompt() fallback behavior."""

    def test_empty_returns_default(self):
        cfg = AgentConfig(name="t")
        assert cfg.get_system_prompt() == BASE_PROMPT

    def test_custom_prompt_appended(self):
        cfg = AgentConfig(name="t", system_prompt="Custom prompt.")
        assert cfg.get_system_prompt() == BASE_PROMPT + "\n\n---\n\nCustom prompt."


# ===================================================================
# BASE_PROMPT validation
# ===================================================================


class TestBasePrompt:
    """Validate BASE_PROMPT is usable."""

    def test_is_non_empty_string(self):
        assert isinstance(BASE_PROMPT, str)
        assert len(BASE_PROMPT) > 0


# ===================================================================
# compose_system_prompt
# ===================================================================


class TestComposeSystemPrompt:
    """Test the F4 (M10) connector-aware system-prompt composition."""

    def test_non_connector_no_persona_returns_base_only(self):
        """Byte-identical to pre-F4 get_system_prompt with empty persona."""
        from the_one.agent.config import compose_system_prompt
        out = compose_system_prompt(BASE_PROMPT, "")
        assert out == BASE_PROMPT

    def test_non_connector_with_persona_returns_base_separator_persona(self):
        """Byte-identical to pre-F4 get_system_prompt with persona."""
        from the_one.agent.config import compose_system_prompt
        out = compose_system_prompt(BASE_PROMPT, "Custom.")
        assert out == BASE_PROMPT + "\n\n---\n\nCustom."

    # ── M11 F7 L9: single-directive surface ───────────────────────
    #
    # The pre-F7 surface had TWO directives (auto-relay ON / OFF)
    # dispatched on the ``auto_relay`` kwarg. F7 made auto-relay an
    # invariant of engaged turns (the L8 policy gate silences
    # everything else upstream), so the OFF directive became dead
    # code and was deleted at L9 along with the ``auto_relay`` kwarg
    # itself. The surviving directive is unconditionally appended
    # when ``connector_attached=True``. ``send_tool_enabled`` stays
    # in the signature as a no-op (callers still compute it for the
    # F10 carve-out that pre-loads the send tool's schema).

    def test_connector_attached_includes_auto_relay_directive(self):
        """``connector_attached=True`` unconditionally lands the
        auto-relay directive — telling the agent its plaintext IS the
        platform reply by default, no permission-asking required.
        Post-L9: there is no longer an OFF state to select; the
        directive is invariant when connector_attached is True."""
        from the_one.agent.config import (
            _CONNECTOR_AUTO_RELAY_DIRECTIVE,
            compose_system_prompt,
        )
        out = compose_system_prompt(
            BASE_PROMPT,
            "",
            connector_attached=True,
            send_tool_enabled=True,
        )
        assert BASE_PROMPT in out
        assert _CONNECTOR_AUTO_RELAY_DIRECTIVE in out

    def test_connector_attached_tool_disabled_includes_on_directive(self):
        """``send_tool_enabled=False`` does NOT change directive
        selection — the directive is unconditional when
        ``connector_attached=True``. The directive references
        ``send_to_platform_channel`` regardless of tool enablement;
        when disabled, the LLM cannot call it regardless of the
        prompt. This test pins the kwarg's no-op status."""
        from the_one.agent.config import (
            _CONNECTOR_AUTO_RELAY_DIRECTIVE,
            compose_system_prompt,
        )
        out = compose_system_prompt(
            BASE_PROMPT,
            "",
            connector_attached=True,
            send_tool_enabled=False,
        )
        assert _CONNECTOR_AUTO_RELAY_DIRECTIVE in out

    def test_connector_attached_with_persona_persona_after_directive(self):
        """Persona appears AFTER the directive, separated by '---'."""
        from the_one.agent.config import (
            _CONNECTOR_AUTO_RELAY_DIRECTIVE,
            compose_system_prompt,
        )
        out = compose_system_prompt(
            BASE_PROMPT,
            "Custom persona.",
            connector_attached=True,
            send_tool_enabled=True,
        )
        # Shape: base + \n\n + directive + \n\n---\n\n + persona.
        assert out.index(BASE_PROMPT) < out.index(
            _CONNECTOR_AUTO_RELAY_DIRECTIVE
        )
        assert out.index(_CONNECTOR_AUTO_RELAY_DIRECTIVE) < out.index("---")
        assert out.endswith("Custom persona.")

    def test_directive_forward_references_l10_history_tools(self):
        """Pins the L9 design: the directive forward-references L10's
        history-fetch tools with "if available" hedging so the prompt
        stays truthful pre-L10 (tools not registered → "tool not
        available" on call) and post-L10 (tools registered → calls
        succeed)."""
        from the_one.agent.config import _CONNECTOR_AUTO_RELAY_DIRECTIVE
        assert "fetch_channel_history" in _CONNECTOR_AUTO_RELAY_DIRECTIVE
        assert "fetch_thread_history" in _CONNECTOR_AUTO_RELAY_DIRECTIVE
        assert "fetch_dm_history" in _CONNECTOR_AUTO_RELAY_DIRECTIVE
        assert "list_visible_channels" in _CONNECTOR_AUTO_RELAY_DIRECTIVE
        assert "if available" in _CONNECTOR_AUTO_RELAY_DIRECTIVE

    # ── M11 F5 L6 HAT round-8: operator_directive removed ─────────
    # The M11 F2 L3 ``operator_directive`` kwarg and the per-account
    # ``system_prompt_directive`` collection were REMOVED. The
    # corresponding append-mode test cluster (three tests) was
    # deleted alongside; legacy callers that still pass the kwarg
    # would now raise ``TypeError`` (no longer in the composer's
    # signature). Nothing in production code passes it.
