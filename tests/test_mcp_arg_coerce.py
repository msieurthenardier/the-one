"""Unit tests for the schema-guided argument coercion helper (squawk 0052)."""

import copy

import pytest

from the_one.mcp._arg_coerce import coerce_arguments


def _obj(**props):
    return {"type": "object", "properties": props}


@pytest.mark.parametrize(
    ("typ", "raw", "expected"),
    [
        ("integer", "7", 7),
        ("integer", " -3 ", -3),
        ("number", "42", 42),
        ("number", "2.5", 2.5),
        ("number", "-.5", -0.5),
        ("number", "1e3", 1000.0),
        ("boolean", "true", True),
        ("boolean", "False", False),
        (["integer", "null"], "9", 9),
    ],
)
def test_coerces(typ, raw, expected):
    out = coerce_arguments({"x": raw}, _obj(x={"type": typ}))["x"]
    assert out == expected
    assert type(out) is type(expected)


@pytest.mark.parametrize(
    ("typ", "raw"),
    [
        ("integer", "7.0"),
        ("integer", "1e3"),
        ("integer", "0x10"),
        ("integer", "1_000"),
        ("integer", "+5"),
        ("integer", ""),
        ("integer", "abc"),
        ("integer", "٣"),
        ("number", "nan"),
        ("number", "inf"),
        ("number", "-Infinity"),
        ("number", "1_0.5"),
        ("number", "1e999"),
        ("boolean", "1"),
        ("boolean", "yes"),
    ],
)
def test_rejections_left_as_is(typ, raw):
    assert coerce_arguments({"x": raw}, _obj(x={"type": typ}))["x"] == raw


@pytest.mark.parametrize(
    "prop",
    [
        {"type": ["string", "integer"]},
        {"type": "string"},
        {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        {"oneOf": [{"type": "integer"}]},
        {"allOf": [{"type": "integer"}]},
        {"$ref": "#/defs/n"},
        {"type": "integer", "enum": [1, 2]},
        {"type": "integer", "const": 1},
        {},
    ],
)
def test_ambiguous_schema_untouched(prop):
    assert coerce_arguments({"x": "7"}, _obj(x=prop))["x"] == "7"


def test_non_string_values_untouched():
    args = {"a": 1, "b": 2.5, "c": True, "d": None, "e": [1]}
    schema = _obj(a={"type": "integer"}, b={"type": "number"}, c={"type": "boolean"})
    assert coerce_arguments(args, schema) == args


def test_nested_object_and_array_items():
    schema = _obj(
        o=_obj(n={"type": "integer"}),
        a={"type": "array", "items": {"type": "number"}},
        t={"type": "array", "items": [{"type": "integer"}]},
    )
    args = {"o": {"n": "5", "z": "6"}, "a": ["1", "2.5", "x"], "t": ["3"], "extra": "8"}
    assert coerce_arguments(args, schema) == {
        "o": {"n": 5, "z": "6"},
        "a": [1, 2.5, "x"],
        "t": ["3"],
        "extra": "8",
    }


def test_does_not_mutate_input():
    args = {"o": {"n": "5"}, "a": ["1"]}
    snapshot = copy.deepcopy(args)
    schema = _obj(o=_obj(n={"type": "integer"}), a={"type": "array", "items": {"type": "integer"}})
    out = coerce_arguments(args, schema)
    assert args == snapshot
    assert out == {"o": {"n": 5}, "a": [1]}
