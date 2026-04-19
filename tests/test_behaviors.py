"""Tests for the_one.agent.behaviors module."""

from __future__ import annotations

import re

from the_one.agent.behaviors import (
    CONTINUE_SCHEMA,
    DIRECT_ACTIONS,
    extract_tool_calls,
    match_direct_action,
)

# ---- valid_names helper used across tests ----
VALID = {"tool_a", "tool_b", "tool_c"}


# ===================================================================
# extract_tool_calls
# ===================================================================

class TestExtractToolCalls:
    """Tests for extract_tool_calls()."""

    def test_valid_json_string_argument(self):
        text = 'Here is a call: {"name": "tool_a", "arguments": "hello"}'
        calls = extract_tool_calls(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "tool_a"
        assert calls[0].arguments == {"args": "hello"}

    def test_non_dict_non_string_arguments_skipped(self):
        """Numeric arguments are parsed but filtered (not str or dict)."""
        text = '{"name": "tool_a", "arguments": 42}'
        calls = extract_tool_calls(text, VALID)
        assert calls == []

    def test_multiple_calls(self):
        text = (
            'First: {"name": "tool_a", "arguments": "x"} '
            'Second: {"name": "tool_b", "arguments": "y"}'
        )
        calls = extract_tool_calls(text, VALID)
        assert len(calls) == 2
        assert calls[0].name == "tool_a"
        assert calls[1].name == "tool_b"

    def test_invalid_json_skipped(self):
        text = '{"name": "tool_a", "arguments": {bad json}}'
        calls = extract_tool_calls(text, VALID)
        assert calls == []

    def test_unknown_tool_filtered(self):
        text = '{"name": "unknown_tool", "arguments": "x"}'
        calls = extract_tool_calls(text, VALID)
        assert calls == []

    def test_string_arguments_wrapped_in_dict(self):
        text = '{"name": "tool_a", "arguments": "hello"}'
        calls = extract_tool_calls(text, VALID)
        assert len(calls) == 1
        assert calls[0].arguments == {"args": "hello"}

    def test_dict_arguments_not_matched(self):
        """Regex can't handle dict arguments (inner braces break the match)."""
        text = '{"name": "tool_a", "arguments": {"x": 1}}'
        calls = extract_tool_calls(text, VALID)
        # The regex [^}]+ consumes up to the first }, producing invalid JSON
        assert calls == []

    def test_nested_arguments_not_matched(self):
        """Regex can't handle nested braces — verify it returns empty list."""
        text = '{"name": "tool_a", "arguments": {"outer": {"inner": 1}}}'
        calls = extract_tool_calls(text, VALID)
        assert calls == []

    def test_no_matches_in_plain_text(self):
        text = "Just a regular message with no tool calls."
        calls = extract_tool_calls(text, VALID)
        assert calls == []

    def test_extracted_ids_are_unique(self):
        text = (
            '{"name": "tool_a", "arguments": "x"} '
            '{"name": "tool_b", "arguments": "y"}'
        )
        calls = extract_tool_calls(text, VALID)
        ids = [c.id for c in calls]
        assert len(set(ids)) == len(ids)
        assert all(id_.startswith("extracted-") for id_ in ids)


# ===================================================================
# match_direct_action
# ===================================================================

class TestMatchDirectAction:
    """Tests for match_direct_action()."""

    def test_restart_yourself(self):
        result = match_direct_action("restart yourself")
        assert result is not None
        assert result[0] == "restart"

    def test_reboot_the_agent(self):
        result = match_direct_action("reboot the agent")
        assert result is not None
        assert result[0] == "restart"

    def test_reload_the_container(self):
        result = match_direct_action("reload the container")
        assert result is not None
        assert result[0] == "restart"

    def test_please_prefix(self):
        result = match_direct_action("please restart yourself")
        assert result is not None
        assert result[0] == "restart"

    def test_rollback(self):
        result = match_direct_action("roll back")
        assert result is not None
        assert result[0] == "rollback"

    def test_undo_deploy(self):
        result = match_direct_action("undo deploy")
        assert result is not None
        assert result[0] == "rollback"

    def test_case_insensitivity(self):
        result = match_direct_action("RESTART YOURSELF")
        assert result is not None
        assert result[0] == "restart"

    def test_non_matching_input(self):
        assert match_direct_action("tell me a joke") is None

    def test_whitespace_stripped(self):
        result = match_direct_action("  restart yourself  ")
        assert result is not None
        assert result[0] == "restart"


# ===================================================================
# Structure validation
# ===================================================================

class TestStructureConstants:
    """Validate structure of DIRECT_ACTIONS and CONTINUE_SCHEMA."""

    def test_direct_actions_is_list_of_tuples(self):
        assert isinstance(DIRECT_ACTIONS, list)
        for entry in DIRECT_ACTIONS:
            assert isinstance(entry, tuple)
            assert len(entry) == 3
            pattern, name, kwargs = entry
            assert isinstance(pattern, re.Pattern)
            assert isinstance(name, str)
            assert isinstance(kwargs, dict)

    def test_continue_schema_structure(self):
        assert isinstance(CONTINUE_SCHEMA, dict)
        assert CONTINUE_SCHEMA["name"] == "continue"
        assert "description" in CONTINUE_SCHEMA
        assert "parameters" in CONTINUE_SCHEMA
        params = CONTINUE_SCHEMA["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "reason" in params["properties"]
