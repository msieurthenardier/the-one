"""Tests for the_one.agent.behaviors module."""

from __future__ import annotations

import re

from the_one.agent.behaviors import (
    CONTINUE_SCHEMA,
    DIRECT_ACTIONS,
    match_direct_action,
)

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
