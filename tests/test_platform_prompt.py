"""The sectioned platform prompt renders exactly the pinned wording (candidate 1)."""

from __future__ import annotations

from tests._platform_prompt_pins import (
    PLATFORM_TOOL_FREE_PIN,
    PLATFORM_TOOL_FREE_VISUALS_OFF_PIN,
    PLATFORM_TOOLS_ALL_ON_PIN,
    PLATFORM_TOOLS_VISUALS_OFF_PIN,
    PLATFORM_VISUALS_PIN,
)
from the_one.agent.config import compose_system_prompt
from the_one.agent.platform_prompt import (
    _EXECUTION,
    KB_LINE,
    NO_KB_TOOL_DISCOVERY,
    PRELOADED_KB_LINE,
    PRELOADED_TOOL_DISCOVERY,
    SECTIONS,
    Capabilities,
    capabilities_from_registry,
    render_platform,
    render_tool_free,
    sections_for,
)


def test_tool_capable_render_is_byte_identical():
    assert render_platform(Capabilities.all_on()) == PLATFORM_TOOLS_ALL_ON_PIN
    assert PLATFORM_TOOLS_ALL_ON_PIN.endswith("\n")


def test_tool_free_render_is_byte_identical():
    assert render_tool_free(Capabilities.all_on()) == PLATFORM_TOOL_FREE_PIN
    assert PLATFORM_TOOL_FREE_PIN.endswith("\n")


KB_PHRASES = ("Knowledge bases are attached", "before answering from memory")
BOX_PHRASES = ("isolated box", "host access")


def test_all_on_equals_old_constant_and_other_fields_change_nothing():
    base = render_platform(Capabilities.all_on())
    assert base == PLATFORM_TOOLS_ALL_ON_PIN
    for field in ("notes", "rules", "time_tool"):
        assert render_platform(Capabilities(**{field: False})) == base, field


def test_visuals_switch_changes_the_text_and_only_the_visuals_section():
    on = render_platform(Capabilities.all_on())
    off = render_platform(Capabilities(visuals=False))
    assert off == PLATFORM_TOOLS_VISUALS_OFF_PIN
    assert on == off + PLATFORM_VISUALS_PIN
    assert "```" not in off and "`chart`" in on and "`chart`" not in off
    assert render_tool_free(Capabilities(visuals=False)) == PLATFORM_TOOL_FREE_VISUALS_OFF_PIN
    assert render_tool_free(Capabilities.all_on()) == (
        PLATFORM_TOOL_FREE_VISUALS_OFF_PIN + PLATFORM_VISUALS_PIN
    )
    # The section tiles into the UI rows with its applies-when line.
    sec = next(s for s in SECTIONS if s.id == "visuals")
    assert (sec.title, sec.applies_when) == ("Rich visuals", "agents with Rich visuals on")


def test_capabilities_from_registry_carries_visuals():
    assert capabilities_from_registry(_Reg([]), notes=False, rules=True, time_tool=True).visuals
    assert not capabilities_from_registry(
        _Reg([]), notes=False, rules=True, time_tool=True, visuals=False
    ).visuals


def test_knowledge_condition_only_removes_kb_phrases():
    on = render_platform(Capabilities.all_on())
    off = render_platform(Capabilities(knowledge=False))
    for phrase in KB_PHRASES:
        assert phrase in on
        assert phrase not in off, phrase
    # Everything else is still there.
    assert "Tools:" in off and "search_tools" in off
    assert off.count("knowledge") == 0


def test_no_kb_forms_are_pinned_verbatim():
    off = render_platform(Capabilities(knowledge=False))
    assert NO_KB_TOOL_DISCOVERY in off and KB_LINE not in off
    assert (
        "\nTools:\n- You start with `search_tools` and `continue`. Find any other tool with "
        '`search_tools` (for example "read a file" or "http request"); tools you find stay '
        "available for the rest of the conversation.\n- Take actions rather than describing"
    ) in off
    on = render_platform(Capabilities.all_on())
    assert NO_KB_TOOL_DISCOVERY + KB_LINE in on
    assert KB_LINE == (
        "- Knowledge bases are attached: list them with `search_tools` (empty query) and "
        "search them before answering from memory on topics they cover.\n"
    )


def test_execution_condition_removes_only_the_box_bullet():
    on = render_platform(Capabilities.all_on())
    off = render_platform(Capabilities(exec_tools=False))
    for phrase in BOX_PHRASES:
        assert phrase in on
        assert phrase not in off
    assert on.replace(_EXECUTION, "") == off
    # The join stays intact: the bullets around the execution one still follow each other.
    assert "say what you changed.\n- To keep working in another step" in off


def test_bare_agent_has_neither_kb_nor_box_text():
    bare = render_platform(Capabilities(knowledge=False, exec_tools=False))
    for phrase in KB_PHRASES + BOX_PHRASES:
        assert phrase not in bare
    assert "search_tools" in bare and "`continue`" in bare


def test_capability_matrix_each_alone_and_all():
    for kb in (True, False):
        for ex in (True, False):
            caps = Capabilities(knowledge=kb, exec_tools=ex)
            text = render_platform(caps)
            assert (KB_LINE in text) is kb
            assert ("isolated box" in text) is ex
            assert "".join(t for _i, t in sections_for(caps)) == text
    ids = [i for i, _t in sections_for(Capabilities(exec_tools=False))]
    assert "execution" not in ids
    assert "execution" in [i for i, _t in sections_for(Capabilities.all_on())]


def test_tool_free_never_names_a_tool_even_with_everything_on():
    text = render_tool_free(Capabilities.all_on())
    for word in (
        "search_tools",
        "continue",
        "current_time",
        "update_note",
        "forget_note",
        "save_note",
        "host_access",
    ):
        assert word not in text, word


def test_fragments_do_not_tile_and_ui_rows():
    from the_one.agent.platform_prompt import FRAGMENTS, platform_sections_for_ui

    assert [f.id for f in FRAGMENTS] == ["knowledge"]
    assert "knowledge" not in [s.id for s in SECTIONS]
    rows = platform_sections_for_ui()
    tools = [r["id"] for r in rows if r["variant"] == "tools"]
    free = [r["id"] for r in rows if r["variant"] == "tool_free"]
    assert tools == [
        "identity",
        "tool_discovery",
        "knowledge",
        "tool_discovery_preloaded",
        "knowledge_preloaded",
        "tool_use",
        "execution",
        "tool_use_tail",
        "formatting",
        "visuals",
    ]
    assert free == ["identity_tool_free", "formatting", "visuals"]
    assert set(rows[0]) == {"id", "title", "applies_when", "text", "variant"}
    knowledge = next(r for r in rows if r["id"] == "knowledge")
    assert KB_LINE.strip() == knowledge["text"]
    # The tools rows' texts tile the all-on render (the fragment rows are extra).
    extra = {"knowledge", "tool_discovery_preloaded", "knowledge_preloaded"}
    assert "".join(
        r["text"] for r in rows if r["variant"] == "tools" and r["id"] not in extra
    ) == render_platform(Capabilities.all_on())
    # The preloaded rows (sortie 11 AC10): titles, applies-when, and the signed-off texts.
    pre = next(r for r in rows if r["id"] == "tool_discovery_preloaded")
    assert pre["title"] == "Tool discovery (tools preloaded)"
    assert pre["applies_when"] == "tool-capable agents whose tools fit the exposure budget"
    assert pre["text"] == PRELOADED_TOOL_DISCOVERY + PRELOADED_KB_LINE
    pre_kb = next(r for r in rows if r["id"] == "knowledge_preloaded")
    assert pre_kb["title"] == "Knowledge-base wording (tools preloaded)"
    assert pre_kb["applies_when"] == (
        "tool-capable agents whose tools fit the exposure budget, with a knowledge base "
        "attached (inside Tool discovery)"
    )
    assert pre_kb["text"] == PRELOADED_KB_LINE.strip()
    assert "".join(r["text"] for r in rows if r["variant"] == "tool_free") == render_tool_free(
        Capabilities.all_on()
    )


def test_preloaded_wording_is_pinned_and_follows_the_flag():
    assert PRELOADED_TOOL_DISCOVERY == (
        "\nTools:\n- All your tools are available now: call them directly "
        "(`search_tools` only lists them again).\n"
    )
    assert PRELOADED_KB_LINE == (
        "- Knowledge bases are attached: search them before answering from memory on "
        "topics they cover.\n"
    )
    # today's wording is unchanged
    assert render_platform(Capabilities.all_on()) == PLATFORM_TOOLS_ALL_ON_PIN
    on = Capabilities(tools_preloaded=True)
    text = render_platform(on)
    assert PRELOADED_TOOL_DISCOVERY + PRELOADED_KB_LINE in text
    assert NO_KB_TOOL_DISCOVERY not in text and KB_LINE not in text
    no_kb = render_platform(Capabilities(knowledge=False, tools_preloaded=True))
    assert PRELOADED_TOOL_DISCOVERY in no_kb and PRELOADED_KB_LINE not in no_kb
    # the tool-free render never carries it
    assert render_tool_free(on) == PLATFORM_TOOL_FREE_PIN


def test_capabilities_from_registry_carries_tools_preloaded():
    assert (
        capabilities_from_registry(
            _Reg([]), notes=False, rules=True, time_tool=True
        ).tools_preloaded
        is False
    )
    caps = capabilities_from_registry(
        _Reg([]), notes=False, rules=True, time_tool=True, tools_preloaded=True
    )
    assert caps.tools_preloaded is True


def test_tool_free_ignores_other_capabilities():
    assert (
        render_tool_free(Capabilities(knowledge=False, exec_tools=False)) == PLATFORM_TOOL_FREE_PIN
    )
    assert render_platform(Capabilities(tools=False)) == PLATFORM_TOOL_FREE_PIN


def test_composed_prompt_matches_old_composition():
    caps = Capabilities.all_on()
    kw = dict(rules=["Be brief."], notes=[], date_line="Today is Monday.")
    new = compose_system_prompt(render_platform(caps), "You are Aria.", **kw)
    old = compose_system_prompt(PLATFORM_TOOLS_ALL_ON_PIN, "You are Aria.", **kw)
    assert new == old
    degraded_new = compose_system_prompt(render_tool_free(caps), "You are Aria.", **kw)
    degraded_old = PLATFORM_TOOL_FREE_PIN + old[len(PLATFORM_TOOLS_ALL_ON_PIN) :]
    assert degraded_new == degraded_old


def test_section_ids_unique_and_sections_for_matches_render():
    ids = [s.id for s in SECTIONS]
    assert len(ids) == len(set(ids))
    caps = Capabilities.all_on()
    assert "".join(t for _i, t in sections_for(caps)) == render_platform(caps)
    assert [i for i, _t in sections_for(caps)][0] == "identity"
    assert [i for i, _t in sections_for(Capabilities(tools=False))] == [
        "identity_tool_free",
        "formatting",
        "visuals",
    ]
    assert [i for i, _t in sections_for(Capabilities(tools=False, visuals=False))] == [
        "identity_tool_free",
        "formatting",
    ]


class _Reg:
    def __init__(self, names):
        self.tool_names = names


def test_capabilities_from_registry():
    c = capabilities_from_registry(
        _Reg(["search_tools", "kb__docs__search", "shell"]), notes=True, rules=False, time_tool=True
    )
    assert c.knowledge and c.exec_tools and c.notes and c.time_tool and not c.rules
    c = capabilities_from_registry(_Reg(["python_exec"]), notes=False, rules=True, time_tool=False)
    assert c.exec_tools and not c.knowledge
    c = capabilities_from_registry(None, notes=False, rules=False, time_tool=False)
    assert not (c.knowledge or c.exec_tools or c.notes or c.rules or c.time_tool)
    assert c.tools


def test_broken_registry_gives_no_tool_capabilities():
    class Broken:
        @property
        def tool_names(self):
            raise RuntimeError("boom")

    c = capabilities_from_registry(Broken(), notes=False, rules=False, time_tool=False)
    assert not (c.knowledge or c.exec_tools)
