"""Tests for the canonical A4 request-param resolvers (M16 F11 L01).

Pure unit tests, mirroring the ``resolve_extended_thinking`` /
``_coerce_bool`` block in ``tests/test_anthropic_provider.py:509-569``: a
``_coerce_*`` block (pass-through, string encodings, junk→None, bool
handling) and a ``resolve_*`` block (config-wins, config-wins-over-env,
env-fallback, default-when-unset, env-junk→default) for each of the three
resolvers. No live calls, no provider construction.
"""

from __future__ import annotations

from the_one.llm._request_params import (
    _coerce_effort,
    _coerce_response_format,
    _coerce_stop,
    resolve_reasoning_effort,
    resolve_response_format,
    resolve_stop,
)

# --------------------------------------------------------------------------
# _coerce_effort
# --------------------------------------------------------------------------


def test_coerce_effort_strings_stripped_and_lowered():
    assert _coerce_effort("high") == "high"
    assert _coerce_effort("HIGH") == "high"
    assert _coerce_effort("  Medium  ") == "medium"


def test_coerce_effort_empty_string_none():
    assert _coerce_effort("") is None
    assert _coerce_effort("   ") is None


def test_coerce_effort_bool_rejected():
    assert _coerce_effort(True) is None
    assert _coerce_effort(False) is None


def test_coerce_effort_unrecognized_and_other_types_none():
    assert _coerce_effort(None) is None
    assert _coerce_effort(5) is None
    assert _coerce_effort(1.5) is None
    assert _coerce_effort([]) is None
    assert _coerce_effort({}) is None


# --------------------------------------------------------------------------
# _coerce_response_format
# --------------------------------------------------------------------------


def test_coerce_response_format_json_string_aliases():
    assert _coerce_response_format("json") == {"type": "json_object"}
    assert _coerce_response_format("JSON_OBJECT") == {"type": "json_object"}
    assert _coerce_response_format(" json_object ") == {"type": "json_object"}


def test_coerce_response_format_dict_passthrough_json_object():
    value = {"type": "json_object"}
    assert _coerce_response_format(value) == value


def test_coerce_response_format_dict_passthrough_json_schema():
    value = {"type": "json_schema", "schema": {"type": "object", "properties": {}}}
    assert _coerce_response_format(value) == value


def test_coerce_response_format_dict_wrong_shape_none():
    assert _coerce_response_format({"type": "json_schema"}) is None  # missing schema
    assert _coerce_response_format({"foo": "bar"}) is None
    assert _coerce_response_format({}) is None


def test_coerce_response_format_json_string_right_shape():
    # env-style JSON-encoded string decoding to a valid canonical dict.
    assert _coerce_response_format('{"type": "json_object"}') == {"type": "json_object"}
    schema = {"type": "json_schema", "schema": {"type": "object"}}
    schema_json = '{"type": "json_schema", "schema": {"type": "object"}}'
    assert _coerce_response_format(schema_json) == schema


def test_coerce_response_format_json_string_wrong_shape_none():
    # valid JSON, wrong shape (a list, not an object) -> None.
    assert _coerce_response_format("[1,2]") is None


def test_coerce_response_format_malformed_json_none():
    assert _coerce_response_format("{not json") is None
    assert _coerce_response_format("not json at all") is None


def test_coerce_response_format_empty_string_none():
    assert _coerce_response_format("") is None
    assert _coerce_response_format("   ") is None


def test_coerce_response_format_unrecognized_and_other_types_none():
    assert _coerce_response_format(None) is None
    assert _coerce_response_format(True) is None
    assert _coerce_response_format(5) is None
    assert _coerce_response_format([]) is None


# --------------------------------------------------------------------------
# _coerce_stop
# --------------------------------------------------------------------------


def test_coerce_stop_bare_string_becomes_one_element_list():
    assert _coerce_stop("STOP") == ["STOP"]
    assert _coerce_stop("</s>") == ["</s>"]


def test_coerce_stop_list_passthrough():
    assert _coerce_stop(["a", "b"]) == ["a", "b"]
    assert _coerce_stop(("a", "b")) == ["a", "b"]


def test_coerce_stop_list_drops_non_str_and_empty_entries():
    assert _coerce_stop(["a", "", "b", 5, None, True]) == ["a", "b"]


def test_coerce_stop_list_all_entries_dropped_none():
    assert _coerce_stop(["", 5, None, True]) is None
    assert _coerce_stop([]) is None


def test_coerce_stop_json_array_string_right_shape():
    # env-style JSON-encoded array decoding to a valid canonical list.
    assert _coerce_stop('["</s>","STOP"]') == ["</s>", "STOP"]


def test_coerce_stop_json_object_string_wrong_shape_none():
    # valid JSON, wrong shape (an object, not an array) -> None.
    assert _coerce_stop('{"a": 1}') is None


def test_coerce_stop_dict_wrong_shape_none():
    assert _coerce_stop({"a": 1}) is None


def test_coerce_stop_empty_string_none():
    assert _coerce_stop("") is None
    assert _coerce_stop("   ") is None


def test_coerce_stop_unrecognized_and_other_types_none():
    assert _coerce_stop(None) is None
    assert _coerce_stop(True) is None
    assert _coerce_stop(5) is None


# --------------------------------------------------------------------------
# resolve_reasoning_effort
# --------------------------------------------------------------------------


def test_resolve_reasoning_effort_config_wins(monkeypatch):
    monkeypatch.delenv("THE_ONE_REASONING_EFFORT", raising=False)
    assert resolve_reasoning_effort("high") == "high"


def test_resolve_reasoning_effort_config_wins_over_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_REASONING_EFFORT", "low")
    assert resolve_reasoning_effort("high") == "high"


def test_resolve_reasoning_effort_falls_through_to_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_REASONING_EFFORT", "medium")
    assert resolve_reasoning_effort(None) == "medium"


def test_resolve_reasoning_effort_default_none_when_unset(monkeypatch):
    monkeypatch.delenv("THE_ONE_REASONING_EFFORT", raising=False)
    assert resolve_reasoning_effort(None) is None


def test_resolve_reasoning_effort_env_junk_falls_to_default(monkeypatch):
    monkeypatch.setenv("THE_ONE_REASONING_EFFORT", "")
    assert resolve_reasoning_effort(None) is None


# --------------------------------------------------------------------------
# resolve_response_format
# --------------------------------------------------------------------------


def test_resolve_response_format_config_wins(monkeypatch):
    monkeypatch.delenv("THE_ONE_RESPONSE_FORMAT", raising=False)
    value = {"type": "json_object"}
    assert resolve_response_format(value) == value


def test_resolve_response_format_config_wins_over_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_RESPONSE_FORMAT", '{"type": "json_schema", "schema": {}}')
    value = {"type": "json_object"}
    assert resolve_response_format(value) == value


def test_resolve_response_format_falls_through_to_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_RESPONSE_FORMAT", "json")
    assert resolve_response_format(None) == {"type": "json_object"}


def test_resolve_response_format_default_none_when_unset(monkeypatch):
    monkeypatch.delenv("THE_ONE_RESPONSE_FORMAT", raising=False)
    assert resolve_response_format(None) is None


def test_resolve_response_format_env_junk_falls_to_default(monkeypatch):
    monkeypatch.setenv("THE_ONE_RESPONSE_FORMAT", "not json")
    assert resolve_response_format(None) is None


def test_resolve_response_format_env_valid_json_wrong_shape_none(monkeypatch):
    # Locks the recursive-recoerce behavior: valid JSON, wrong shape (a list).
    monkeypatch.setenv("THE_ONE_RESPONSE_FORMAT", "[1,2]")
    assert resolve_response_format(None) is None


def test_resolve_response_format_env_valid_json_right_shape(monkeypatch):
    # Locks the new JSON-decode-from-env path (no in-repo precedent).
    monkeypatch.setenv("THE_ONE_RESPONSE_FORMAT", '{"type": "json_object"}')
    assert resolve_response_format(None) == {"type": "json_object"}


# --------------------------------------------------------------------------
# resolve_stop
# --------------------------------------------------------------------------


def test_resolve_stop_config_wins(monkeypatch):
    monkeypatch.delenv("THE_ONE_STOP", raising=False)
    assert resolve_stop(["a", "b"]) == ["a", "b"]


def test_resolve_stop_config_wins_over_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_STOP", '["x","y"]')
    assert resolve_stop(["a", "b"]) == ["a", "b"]


def test_resolve_stop_falls_through_to_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_STOP", "STOP")
    assert resolve_stop(None) == ["STOP"]


def test_resolve_stop_default_none_when_unset(monkeypatch):
    monkeypatch.delenv("THE_ONE_STOP", raising=False)
    assert resolve_stop(None) is None


def test_resolve_stop_env_junk_falls_to_default(monkeypatch):
    monkeypatch.setenv("THE_ONE_STOP", "")
    assert resolve_stop(None) is None


def test_resolve_stop_env_valid_json_wrong_shape_none(monkeypatch):
    # Locks the recursive-recoerce behavior: valid JSON, wrong shape (a dict).
    monkeypatch.setenv("THE_ONE_STOP", '{"a":1}')
    assert resolve_stop(None) is None


def test_resolve_stop_env_valid_json_right_shape(monkeypatch):
    # Locks the new JSON-decode-from-env path (no in-repo precedent).
    monkeypatch.setenv("THE_ONE_STOP", '["</s>","STOP"]')
    assert resolve_stop(None) == ["</s>", "STOP"]
