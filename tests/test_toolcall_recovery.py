"""Hermetic unit suite for the text-form tool-call recovery kernel.

M16 F03 L01 (#105): exhaustive, isolated tests for
``the_one.llm._toolcall_recovery.recover_tool_calls`` — no provider, no
network, no markers (runs under default ``make test``). One test per
acceptance criterion of the leg.
"""

from __future__ import annotations

import logging

from the_one.llm._toolcall_recovery import (
    POSITIONAL_ARGS_KEY,
    recover_and_strip,
    recover_tool_calls,
)

# Verbatim captured primary fixture (Flight 1 spike, live gemma3:4b):
# a ```tool fenced block containing a Python-call, returned with
# tool_calls: null.
GEMMA_FIXTURE = "```tool\nget_weather(city='Paris')\n```"


# ---------------------------------------------------------------------------
# Gemma fenced Python-call (primary)
# ---------------------------------------------------------------------------


def test_gemma_fenced_python_call_kwargs():
    assert recover_tool_calls(GEMMA_FIXTURE) == [
        {"name": "get_weather", "arguments": {"city": "Paris"}}
    ]


def test_untagged_fence_single_call():
    content = "```\nget_weather(city='Paris')\n```"
    assert recover_tool_calls(content) == [{"name": "get_weather", "arguments": {"city": "Paris"}}]


def test_python_fence_single_call():
    content = "```python\nget_weather(city='Paris')\n```"
    assert recover_tool_calls(content) == [{"name": "get_weather", "arguments": {"city": "Paris"}}]


def test_tool_code_fence_positional_shell_call():
    # M16 F03 L07 (#105): real gemma3:4b emits a ```tool_code fence with a
    # POSITIONAL shell call. The kernel must recognize the tag and park the
    # positional arg under the sentinel (binding to `command=` is L07's
    # tools-layer job, not the kernel's).
    content = "```tool_code\nshell('echo hi')\n```"
    assert recover_tool_calls(content) == [
        {"name": "shell", "arguments": {POSITIONAL_ARGS_KEY: ["echo hi"]}}
    ]


# ---------------------------------------------------------------------------
# Positional args (carried, never dropped) + coexistence with keyword args
# ---------------------------------------------------------------------------


def test_positional_args_carried_not_dropped(caplog):
    with caplog.at_level(logging.WARNING):
        result = recover_tool_calls("```tool\nget_weather('Paris')\n```")
    assert result == [{"name": "get_weather", "arguments": {POSITIONAL_ARGS_KEY: ["Paris"]}}]
    assert any("positional" in r.message for r in caplog.records)


def test_positional_and_keyword_coexist():
    result = recover_tool_calls("```tool\nget_weather('Paris', units='metric')\n```")
    assert result == [
        {
            "name": "get_weather",
            "arguments": {"units": "metric", POSITIONAL_ARGS_KEY: ["Paris"]},
        }
    ]


def test_non_literal_kwarg_skipped():
    # city=some_var is not a literal → that call is not partially recovered.
    assert recover_tool_calls("```tool\nget_weather(city=some_var)\n```") == []


# ---------------------------------------------------------------------------
# Dotted function name
# ---------------------------------------------------------------------------


def test_dotted_function_name_preserved():
    content = "```tool\ntools.get_weather(city='Paris')\n```"
    assert recover_tool_calls(content) == [
        {"name": "tools.get_weather", "arguments": {"city": "Paris"}}
    ]


# ---------------------------------------------------------------------------
# Hermes <tool_call> tags
# ---------------------------------------------------------------------------


def test_hermes_single_and_multi():
    single = '<tool_call>{"name": "get_weather", "arguments": {"city": "Paris"}}</tool_call>'
    assert recover_tool_calls(single) == [{"name": "get_weather", "arguments": {"city": "Paris"}}]

    multi = (
        '<tool_call>{"name": "get_weather", "arguments": {"city": "Paris"}}</tool_call>'
        '<tool_call>{"name": "get_time", "arguments": {"tz": "UTC"}}</tool_call>'
    )
    assert recover_tool_calls(multi) == [
        {"name": "get_weather", "arguments": {"city": "Paris"}},
        {"name": "get_time", "arguments": {"tz": "UTC"}},
    ]


def test_hermes_nested_object_arguments():
    # The match runs up to the closing tag, NOT the first inner '}'. A nested
    # object in arguments must be preserved intact.
    content = (
        '<tool_call>{"name": "search", "arguments": '
        '{"query": "x", "filters": {"lang": "en", "safe": true}}}</tool_call>'
    )
    assert recover_tool_calls(content) == [
        {
            "name": "search",
            "arguments": {"query": "x", "filters": {"lang": "en", "safe": True}},
        }
    ]


def test_hermes_missing_name_skipped():
    # A tag whose body lacks "name" is skipped (no KeyError); a valid sibling
    # tag still recovers.
    content = (
        '<tool_call>{"arguments": {"city": "Paris"}}</tool_call>'
        '<tool_call>{"name": "get_time", "arguments": {}}</tool_call>'
    )
    assert recover_tool_calls(content) == [{"name": "get_time", "arguments": {}}]


def test_hermes_arguments_missing_defaults_empty():
    content = '<tool_call>{"name": "ping"}</tool_call>'
    assert recover_tool_calls(content) == [{"name": "ping", "arguments": {}}]


# ---------------------------------------------------------------------------
# Bare-JSON object shapes
# ---------------------------------------------------------------------------


def test_bare_json_shapes():
    plain = '{"name": "get_weather", "arguments": {"city": "Paris"}}'
    assert recover_tool_calls(plain) == [{"name": "get_weather", "arguments": {"city": "Paris"}}]

    function_wrapper = (
        '{"type": "function", "function": {"name": "get_weather", "arguments": {"city": "Paris"}}}'
    )
    assert recover_tool_calls(function_wrapper) == [
        {"name": "get_weather", "arguments": {"city": "Paris"}}
    ]

    tool_params = '{"tool": "get_weather", "parameters": {"city": "Paris"}}'
    assert recover_tool_calls(tool_params) == [
        {"name": "get_weather", "arguments": {"city": "Paris"}}
    ]


def test_bare_json_only_whole_content():
    # A tool-call-shaped JSON object embedded in surrounding prose must NOT
    # fire the bare-JSON recognizer (DD2 whole-content gate).
    content = (
        'Here is the call: {"name": "get_weather", "arguments": {"city": "Paris"}} and that is all.'
    )
    assert recover_tool_calls(content) == []


# ---------------------------------------------------------------------------
# Within-format multi-call & cross-format first-recognizer-wins
# ---------------------------------------------------------------------------


def test_multi_call_ordered():
    # Two fenced calls of the same format → ordered 2-element list.
    content = "```tool\nget_weather(city='Paris')\n```\n```tool\nget_time(tz='UTC')\n```"
    assert recover_tool_calls(content) == [
        {"name": "get_weather", "arguments": {"city": "Paris"}},
        {"name": "get_time", "arguments": {"tz": "UTC"}},
    ]


def test_cross_format_first_recognizer_wins():
    # One fenced call + one Hermes tag. Dispatch tries Hermes first, so ONLY
    # the Hermes tag's calls are returned (cross-format is out of scope).
    content = (
        "```tool\nget_weather(city='Paris')\n```\n"
        '<tool_call>{"name": "get_time", "arguments": {"tz": "UTC"}}</tool_call>'
    )
    assert recover_tool_calls(content) == [{"name": "get_time", "arguments": {"tz": "UTC"}}]


# ---------------------------------------------------------------------------
# No false positives
# ---------------------------------------------------------------------------


def test_no_false_positive_on_prose():
    assert recover_tool_calls("The weather in Paris is sunny today.") == []
    assert recover_tool_calls("You can call get_weather to look this up.") == []


def test_no_false_positive_on_plain_code_fence():
    # A fenced code block whose body is NOT a single bare call.
    content = "```python\nx = 1\nprint(x)\n```"
    assert recover_tool_calls(content) == []
    # A fenced block with a single non-call expression.
    assert recover_tool_calls("```python\n42\n```") == []


# ---------------------------------------------------------------------------
# Robustness: malformed input never raises; empty/whitespace
# ---------------------------------------------------------------------------


def test_malformed_never_raises():
    # Unparseable fence body.
    assert recover_tool_calls("```tool\nget_weather(city=\n```") == []
    # Invalid JSON inside a Hermes tag.
    assert recover_tool_calls("<tool_call>{not json}</tool_call>") == []
    # A Call with a non-literal arg.
    assert recover_tool_calls("```tool\nget_weather(city=os.getenv('X'))\n```") == []
    # Bare JSON that is not an object / not tool-call shape.
    assert recover_tool_calls("{not json}") == []
    assert recover_tool_calls('{"unrelated": "shape"}') == []
    assert recover_tool_calls("[1, 2, 3]") == []


def test_empty_and_whitespace():
    assert recover_tool_calls("") == []
    assert recover_tool_calls("   \n\t  ") == []


# ---------------------------------------------------------------------------
# recover_and_strip (Option B, L02): recovery + span stripping in one pass
# ---------------------------------------------------------------------------


def test_recover_and_strip_fence_stripped_whitespace_only_remainder():
    # The fence is the whole content (only whitespace remains) → "".
    stripped, calls = recover_and_strip(GEMMA_FIXTURE)
    assert calls == [{"name": "get_weather", "arguments": {"city": "Paris"}}]
    assert stripped == ""


def test_recover_and_strip_preserves_surrounding_prose():
    content = "Sure, let me check.\n```tool\nget_weather(city='Paris')\n```\nDone."
    stripped, calls = recover_and_strip(content)
    assert calls == [{"name": "get_weather", "arguments": {"city": "Paris"}}]
    assert "```tool" not in stripped
    assert "get_weather(city='Paris')" not in stripped
    assert "Sure, let me check." in stripped
    assert "Done." in stripped


def test_recover_and_strip_bare_json_whole_content_empty():
    content = '{"name": "get_weather", "arguments": {"city": "Paris"}}'
    stripped, calls = recover_and_strip(content)
    assert calls == [{"name": "get_weather", "arguments": {"city": "Paris"}}]
    assert stripped == ""


def test_recover_and_strip_multi_fence_all_stripped_in_order():
    content = (
        "first\n```tool\nget_weather(city='Paris')\n```\n"
        "middle\n```tool\nget_time(zone='UTC')\n```\nlast"
    )
    stripped, calls = recover_and_strip(content)
    assert calls == [
        {"name": "get_weather", "arguments": {"city": "Paris"}},
        {"name": "get_time", "arguments": {"zone": "UTC"}},
    ]
    assert "```tool" not in stripped
    assert "first" in stripped and "middle" in stripped and "last" in stripped


def test_recover_and_strip_hermes_stripped():
    content = (
        'before <tool_call>{"name": "get_weather", "arguments": {"city": "Paris"}}'
        "</tool_call> after"
    )
    stripped, calls = recover_and_strip(content)
    assert calls == [{"name": "get_weather", "arguments": {"city": "Paris"}}]
    assert "<tool_call>" not in stripped
    assert "before" in stripped and "after" in stripped


def test_recover_and_strip_no_recovery_returns_content_unchanged():
    content = "Just some prose with no tool call."
    stripped, calls = recover_and_strip(content)
    assert calls == []
    assert stripped == content


def test_recover_and_strip_empty_and_whitespace_unchanged():
    assert recover_and_strip("") == ("", [])
    assert recover_and_strip("   \n\t  ") == ("   \n\t  ", [])


def test_recover_tool_calls_is_thin_wrapper():
    # The wrapper drops the stripped half but returns the same calls.
    _stripped, calls = recover_and_strip(GEMMA_FIXTURE)
    assert recover_tool_calls(GEMMA_FIXTURE) == calls
