"""Unit tests for the degraded-path direct-tool-protocol renderer.

M16 F03 L08 (#105): ``build_degraded_tool_prompt`` is a pure renderer that
turns a list of ``Tool.to_schema()`` dicts into the system-prompt addendum
injected for non-tool-capable models (e.g. gemma3:4b). These tests pin the
format block, the worked example, the keyword/double-quote rules, the catalog
rendering, and the virtual-tool exclusions — and the empty-catalog edge.

Pure/hermetic: no provider, no network, no agent.
"""

from __future__ import annotations

from the_one.agent.degraded_tools import build_degraded_tool_prompt


def _shell_schema() -> dict:
    return {
        "name": "shell",
        "description": "Execute a shell command in an isolated box.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run."},
            },
            "required": ["command"],
        },
    }


def test_format_block_and_rules_present() -> None:
    out = build_degraded_tool_prompt([_shell_schema()])
    # The ```tool_code format spec is pinned.
    assert "```tool_code" in out
    assert "do not have native tool-calling" in out
    # Keyword-arg + double-quote rules are stated.
    assert "KEYWORD arguments" in out
    assert "DOUBLE-QUOTED" in out
    # One-tool-per-message rule.
    assert "ONE tool per message" in out
    # "emit only the fenced block" instruction.
    assert "ONLY the fenced block" in out


def test_worked_example_present() -> None:
    out = build_degraded_tool_prompt([_shell_schema()])
    # The single pinned worked example.
    assert 'shell(command="echo hello")' in out


def test_tool_gating_clause_present() -> None:
    # CP5 fix: ordinary knowledge questions must be answered directly, not
    # routed through a tool. The gating clause pins that instruction.
    out = build_degraded_tool_prompt([_shell_schema()])
    assert "Only use a tool when the task genuinely requires an external action" in out
    # It tells the model to answer ordinary questions directly and NOT call a tool.
    assert "answer directly in natural language and do NOT call any tool" in out


def test_post_tool_stop_clause_present() -> None:
    # CP4 fix: after a tool result the model must write a final answer rather
    # than re-emitting the same tool call to max_iterations.
    out = build_degraded_tool_prompt([_shell_schema()])
    assert "do NOT call the same tool again for the same" in out
    assert "write a final, natural-language answer to the user that" in out


def test_contrast_example_present() -> None:
    # A compact one-shot contrast: an ordinary question -> direct answer (no
    # tool); an action request -> a ```tool_code call.
    out = build_degraded_tool_prompt([_shell_schema()])
    assert "What is a haiku?" in out
    # The ordinary-question side answers directly (no fenced block for it).
    assert "A haiku is a three-line Japanese poem" in out
    # The action side uses a tool_code call.
    assert 'shell(command="ls -1 | wc -l")' in out


def test_catalog_lists_shell_with_command_param() -> None:
    out = build_degraded_tool_prompt([_shell_schema()])
    assert "Available tools:" in out
    # The catalog entry names the tool and its parameter.
    assert "shell(command)" in out
    # The description is carried through.
    assert "Execute a shell command" in out


def test_catalog_excludes_search_tools_and_continue() -> None:
    # The caller (core.py) is responsible for filtering, but verify the
    # renderer faithfully renders ONLY what it is given — i.e. a catalog built
    # WITHOUT search_tools/continue contains neither name as a catalog entry.
    catalog = [
        _shell_schema(),
        {
            "name": "read_file",
            "description": "Read a file from disk.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    ]
    out = build_degraded_tool_prompt(catalog)
    # search_tools / continue are not in the supplied catalog → not listed.
    assert "search_tools(" not in out
    assert "- continue" not in out
    assert "read_file(path)" in out


def test_required_params_ordered_before_optional() -> None:
    schema = {
        "name": "fetch",
        "description": "Fetch a URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "timeout": {"type": "integer"},
                "url": {"type": "string"},
            },
            "required": ["url"],
        },
    }
    out = build_degraded_tool_prompt([schema])
    # Required (`url`) is listed ahead of optional (`timeout`) even though it is
    # declared second in properties.
    assert "fetch(url, timeout)" in out


def test_empty_catalog_edge() -> None:
    out = build_degraded_tool_prompt([])
    # Still carries the format spec + example (so a model could in principle be
    # told no tools are available without losing the protocol framing).
    assert "```tool_code" in out
    assert "Available tools:" in out
    # States plainly there are no tools rather than emitting an empty list.
    assert "none available" in out


def test_tool_with_no_params_renders_bare_signature() -> None:
    schema = {
        "name": "ping",
        "description": "Health check.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    out = build_degraded_tool_prompt([schema])
    assert "ping(): Health check." in out


def test_deterministic() -> None:
    catalog = [_shell_schema()]
    assert build_degraded_tool_prompt(catalog) == build_degraded_tool_prompt(catalog)
