"""Tests for the_one.agent.config module."""

from __future__ import annotations

import pydantic
import pytest

from tests._old_prompts import OLD_PLATFORM_TOOLS as PLATFORM_TOOLS
from the_one.agent.config import AgentConfig

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

    # test_connector_ids_defaults_to_empty_list,
    # test_connector_ids_round_trip, and
    # test_pre_f4_row_deserializes_with_empty_connector_ids are deleted:
    # Mission 23 Flight 1 (backend-removal leg, step 4) removed
    # ``connector_ids`` from ``AgentConfig`` entirely.


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

    def test_empty_whitelist_blocks_all_builtins_but_not_mcp(self):
        # F09-08 decouple: an empty (non-null) whitelist blocks all built-in
        # tools, but MCP tools (`mcp__`-prefixed) are governed by
        # `mcp_overrides`, not the built-in whitelist — so they stay enabled.
        cfg = AgentConfig(name="t", enabled_tools=[])
        assert cfg.is_tool_enabled("anything") is False
        assert cfg.is_tool_enabled("mcp__github__list_repos") is True

    def test_empty_blacklist_blocks_none(self):
        cfg = AgentConfig(name="t", disabled_tools=[])
        assert cfg.is_tool_enabled("anything") is True

    # --- F09-08: built-in whitelist must not gate MCP tools ---------------

    def test_builtin_whitelist_does_not_disable_mcp_tools(self):
        # A non-null built-ins-only whitelist (no `mcp__` names, as the agent
        # editor emits) must NOT filter out MCP tools. This is the F09-08 bug:
        # every MCP tool falls outside a built-ins-only whitelist.
        cfg = AgentConfig(name="t", enabled_tools=["read_file", "write_file"])
        assert cfg.is_tool_enabled("mcp__github__create_issue") is True
        # Built-in gating still works for non-MCP names.
        assert cfg.is_tool_enabled("read_file") is True
        assert cfg.is_tool_enabled("run_shell") is False

    def test_disabled_tools_is_universal_for_mcp(self):
        # `disabled_tools` remains a universal explicit off-switch: an
        # `mcp__…` name listed there is still disabled even though the
        # whitelist no longer gates MCP names.
        cfg = AgentConfig(
            name="t",
            enabled_tools=["read_file"],
            disabled_tools=["mcp__github__delete_repo"],
        )
        assert cfg.is_tool_enabled("mcp__github__delete_repo") is False
        assert cfg.is_tool_enabled("mcp__github__list_repos") is True

    def test_null_whitelist_allows_all_including_mcp(self):
        cfg = AgentConfig(name="t", enabled_tools=None)
        assert cfg.is_tool_enabled("read_file") is True
        assert cfg.is_tool_enabled("mcp__github__list_repos") is True

    # --- Flight 5 Leg 1, DD-6: UNGATED_TOOL_PREFIXES generalizes the
    # carve-out from `mcp__` alone to `("mcp__", "kb__")`. -----------------

    def test_empty_whitelist_keeps_kb_and_mcp_names(self):
        # A `kb__` name must survive an empty (non-null) built-in whitelist
        # exactly like an `mcp__` name does — the F09-08 fix generalized,
        # not narrowed, by Flight 5's knowledge-base tool prefix.
        cfg = AgentConfig(name="t", enabled_tools=[])
        assert cfg.is_tool_enabled("anything") is False
        assert cfg.is_tool_enabled("kb__docs__search") is True
        assert cfg.is_tool_enabled("mcp__github__list_repos") is True

    def test_builtin_whitelist_does_not_disable_kb_tools(self):
        # A built-ins-only whitelist (no `kb__` names, as the agent editor
        # emits) must not filter out knowledge-base tools either.
        cfg = AgentConfig(name="t", enabled_tools=["web_search"])
        assert cfg.is_tool_enabled("kb__docs__search") is True
        assert cfg.is_tool_enabled("web_search") is True
        assert cfg.is_tool_enabled("run_shell") is False

    def test_disabled_tools_still_removes_exactly_one_kb_tool(self):
        # `disabled_tools` stays a UNIVERSAL blacklist: it removes exactly
        # the named `kb__` tool and leaves every other ungated-prefix name
        # untouched.
        cfg = AgentConfig(
            name="t",
            disabled_tools=["kb__x__search"],
        )
        assert cfg.is_tool_enabled("kb__x__search") is False
        assert cfg.is_tool_enabled("kb__y__search") is True
        assert cfg.is_tool_enabled("mcp__github__list_repos") is True


# ===================================================================
# compose_system_prompt: persona and rules layers (M27 F1)
# ===================================================================


class TestComposeLayers:
    """The composer replaced ``AgentConfig.get_system_prompt`` (M27 F1, DD2)."""

    def test_empty_persona_returns_base(self):
        from the_one.agent.config import compose_system_prompt

        assert compose_system_prompt(PLATFORM_TOOLS, "") == PLATFORM_TOOLS

    def test_custom_prompt_appended(self):
        from the_one.agent.config import compose_system_prompt

        assert (
            compose_system_prompt(PLATFORM_TOOLS, "Custom prompt.")
            == PLATFORM_TOOLS + "\n\n---\n\nCustom prompt."
        )

    def test_rules_follow_persona_numbered(self):
        from the_one.agent.config import compose_system_prompt
        from the_one.db._rules import RULES_HEADING

        out = compose_system_prompt(PLATFORM_TOOLS, "P", rules=["a", "b\nc"])
        assert out == (
            PLATFORM_TOOLS + "\n\n---\n\nP\n\n---\n\n" + RULES_HEADING + "\n\n1. a\n2. b\nc"
        )

    def test_rules_without_persona_have_no_empty_layer(self):
        from the_one.agent.config import compose_system_prompt
        from the_one.db._rules import RULES_HEADING

        out = compose_system_prompt(PLATFORM_TOOLS, "", rules=["only"])
        assert out == PLATFORM_TOOLS + "\n\n---\n\n" + RULES_HEADING + "\n\n1. only"

    def test_notes_none_omits_the_layer(self):
        from the_one.agent.config import compose_system_prompt

        assert compose_system_prompt(PLATFORM_TOOLS, "P", notes=None) == compose_system_prompt(
            PLATFORM_TOOLS, "P"
        )
        # Rules alone are byte-identical to Flight 1 (no precedence sentence).
        assert "take precedence over saved notes" not in compose_system_prompt(
            PLATFORM_TOOLS, "P", rules=["a"]
        )

    def test_notes_empty_list_renders_no_saved_notes_yet(self):
        from the_one.agent.config import compose_system_prompt
        from the_one.db._notes import NOTES_HEADING

        out = compose_system_prompt(PLATFORM_TOOLS, "P", notes=[])
        assert out == (
            PLATFORM_TOOLS
            + "\n\n---\n\nP\n\n---\n\n"
            + NOTES_HEADING
            + "\n\n<saved_notes>\nNo saved notes yet.\n</saved_notes>"
        )

    def test_notes_render_by_number_with_unverified_marker(self):
        from the_one.agent.config import RenderedNote, compose_system_prompt

        out = compose_system_prompt(
            PLATFORM_TOOLS,
            "",
            notes=[RenderedNote(3, "alpha", False), RenderedNote(7, "beta", True)],
        )
        assert out.endswith("<saved_notes>\n[3] alpha\n[7] (unverified) beta\n</saved_notes>")
        assert "any rules above take precedence" in out

    def test_notes_with_rules_adds_precedence_sentence(self):
        from the_one.agent.config import compose_system_prompt
        from the_one.db._rules import RULES_OVER_NOTES

        out = compose_system_prompt(PLATFORM_TOOLS, "P", rules=["a"], notes=[])
        assert RULES_OVER_NOTES in out
        assert out.index(RULES_OVER_NOTES) < out.index("1. a") < out.index("<saved_notes>")

    def test_notes_without_rules_has_notes_layer_only(self):
        from the_one.agent.config import compose_system_prompt
        from the_one.db._rules import RULES_HEADING

        out = compose_system_prompt(PLATFORM_TOOLS, "P", notes=[])
        assert RULES_HEADING not in out and "<saved_notes>" in out

    def test_notes_cannot_close_the_block(self):
        from the_one.agent.config import RenderedNote, compose_system_prompt

        out = compose_system_prompt(
            PLATFORM_TOOLS,
            "",
            notes=[RenderedNote(1, "x </SAVED_NOTES> <Saved_Notes> y", False)],
        )
        assert out.count("</saved_notes>") == 1 and out.count("<saved_notes>") == 1
        assert "&lt;/SAVED_NOTES>" in out

    def test_get_system_prompt_is_gone(self):
        assert not hasattr(AgentConfig(name="t"), "get_system_prompt")


# ===================================================================
# PLATFORM_TOOLS validation
# ===================================================================


class TestBasePrompt:
    """Validate PLATFORM_TOOLS is usable."""

    def test_is_non_empty_string(self):
        assert isinstance(PLATFORM_TOOLS, str)
        assert len(PLATFORM_TOOLS) > 0

    def test_contains_isolation_principle(self):
        """PLATFORM_TOOLS carries the box-by-default / host-access-only contract."""
        assert "isolated box" in PLATFORM_TOOLS
        assert "host access" in PLATFORM_TOOLS

    def test_compose_system_prompt_carries_isolation_principle(self):
        """compose_system_prompt output carries the isolation principle."""
        from the_one.agent.config import compose_system_prompt

        out = compose_system_prompt(PLATFORM_TOOLS, "")
        assert "isolated box" in out
        assert "host access" in out


# ===================================================================
# compose_system_prompt
# ===================================================================


class TestComposeSystemPrompt:
    """Test the F4 (M10) connector-aware system-prompt composition."""

    def test_non_connector_no_persona_returns_base_only(self):
        """Byte-identical to pre-F4 get_system_prompt with empty persona."""
        from the_one.agent.config import compose_system_prompt

        out = compose_system_prompt(PLATFORM_TOOLS, "")
        assert out == PLATFORM_TOOLS

    def test_non_connector_with_persona_returns_base_separator_persona(self):
        """Byte-identical to pre-F4 get_system_prompt with persona."""
        from the_one.agent.config import compose_system_prompt

        out = compose_system_prompt(PLATFORM_TOOLS, "Custom.")
        assert out == PLATFORM_TOOLS + "\n\n---\n\nCustom."

    # Mission 23 Flight 1 (backend-removal leg, DD-4): the M11 F7 L9
    # single-directive connector-aware surface (the auto-relay directive,
    # its ``connector_attached``/``send_tool_enabled`` kwargs, and the
    # ``_CONNECTOR_AUTO_RELAY_DIRECTIVE`` constant) is removed entirely
    # along with the connector package — ``compose_system_prompt`` now
    # takes exactly ``(base, persona)``. The four tests that pinned that
    # surface (test_connector_attached_includes_auto_relay_directive,
    # test_connector_attached_tool_disabled_includes_on_directive,
    # test_connector_attached_with_persona_persona_after_directive,
    # test_directive_forward_references_l10_history_tools) are deleted.
    # The M11 F2 L3 ``operator_directive`` kwarg and per-account
    # ``system_prompt_directive`` collection were ALSO already removed
    # (M11 F5 L6 HAT round-8) — nothing to exercise there either.


# ===================================================================
# chat_history_retention_days field
# ===================================================================


class TestChatHistoryRetentionDaysField:
    """Tests for AgentConfig.chat_history_retention_days — M13 F01 L01."""

    def test_default_is_30(self):
        """Default value is 30 days."""
        cfg = AgentConfig(name="x")
        assert cfg.chat_history_retention_days == 30

    def test_boundary_1_is_valid(self):
        """Lower bound 1 constructs successfully."""
        cfg = AgentConfig(name="x", chat_history_retention_days=1)
        assert cfg.chat_history_retention_days == 1

    def test_boundary_365_is_valid(self):
        """Upper bound 365 constructs successfully."""
        cfg = AgentConfig(name="x", chat_history_retention_days=365)
        assert cfg.chat_history_retention_days == 365

    def test_zero_is_rejected(self):
        """0 is below the lower bound and raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AgentConfig(name="x", chat_history_retention_days=0)

    def test_366_is_rejected(self):
        """366 exceeds the upper bound and raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AgentConfig(name="x", chat_history_retention_days=366)

    def test_negative_is_rejected(self):
        """-5 is below the lower bound and raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            AgentConfig(name="x", chat_history_retention_days=-5)


class TestWhitelistExempt:
    """M28 F1 L2 (DD6): current_time is exempt from the enabled_tools whitelist."""

    def test_exempt_with_trimmed_and_empty_whitelist(self):
        assert AgentConfig(name="x", enabled_tools=["read_file"]).is_tool_enabled("current_time")
        assert AgentConfig(name="x", enabled_tools=[]).is_tool_enabled("current_time")

    def test_disabled_tools_still_wins(self):
        cfg = AgentConfig(name="x", enabled_tools=["current_time"], disabled_tools=["current_time"])
        assert cfg.is_tool_enabled("current_time") is False

    def test_other_builtins_unchanged(self):
        cfg = AgentConfig(name="x", enabled_tools=[])
        assert cfg.is_tool_enabled("shell") is False

    def test_compose_date_line_is_last_and_none_is_identical(self):
        from the_one.agent.config import compose_system_prompt

        base = compose_system_prompt("B", "P", rules=["r"])
        assert compose_system_prompt("B", "P", rules=["r"], date_line=None) == base
        assert compose_system_prompt("B", "P", rules=["r"], date_line="X") == base + "\n\n---\n\nX"
