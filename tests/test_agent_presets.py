"""Tests the agent preset registry."""

from __future__ import annotations


def test_presets_module_exports_three_presets():
    from the_one.agent._presets import PRESETS
    assert len(PRESETS) == 3
    names = {p["name"] for p in PRESETS}
    assert names == {"research", "shell-buddy", "web-crawler"}


def test_presets_each_have_required_keys():
    from the_one.agent._presets import PRESETS
    for p in PRESETS:
        assert "name" in p
        assert "description" in p
        assert "tools_enabled" in p
        assert isinstance(p["tools_enabled"], list)
        assert "system_prompt" in p
        assert "default_model_family" in p  # 'opus' | 'sonnet' | 'haiku'


def test_research_preset_is_read_only():
    from the_one.agent._presets import PRESETS
    research = next(p for p in PRESETS if p["name"] == "research")
    forbidden = {"write_file", "delete_file", "edit_file", "move_file"}
    assert not (set(research["tools_enabled"]) & forbidden), (
        "research preset must not include write tools"
    )


def test_shell_buddy_preset_is_minimal():
    from the_one.agent._presets import PRESETS
    sb = next(p for p in PRESETS if p["name"] == "shell-buddy")
    assert "shell" in sb["tools_enabled"]
    assert "web_search" not in sb["tools_enabled"]
    assert sb["default_model_family"] == "haiku"
