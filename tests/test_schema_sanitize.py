"""Tests for ``the_one.llm._schema_sanitize`` — the pure, stdlib-only tool
``input_schema`` sanitizer that normalizes a schema into a single top-level
Anthropic-acceptable ``object`` form (M16 F02 L01).

Class-grouped, plain-``def`` synchronous unit tests modeled on
``tests/test_llm_base.py``. Each acceptance criterion from the leg artifact
maps to a named test below. The sanitizer is pure (no I/O, no async), so no
fixtures beyond inline schema literals are needed.
"""

from __future__ import annotations

import copy

from tests.fixtures.tool_schemas import PRESS_KEY_INPUT_SCHEMA
from the_one.llm._schema_sanitize import (
    UnsanitizableToolSchema,
    sanitize_tool_schema,
)

# The real-world trigger: goldfinch's ``press_key`` tool input_schema (top-level
# ``anyOf`` alongside a top-level ``type``; the #122 trigger). Shared across the
# conformance suite via ``tests/fixtures/tool_schemas.py`` (DD6).

# Merge note the sanitizer appends to ``description`` when a top-level
# combinator was flattened.
MERGE_NOTE = "(Note: alternative input forms were merged; provide the fields that apply.)"


class TestBasicCoercion:
    def test_missing_type_with_properties_gets_object_type(self) -> None:
        result = sanitize_tool_schema({"properties": {"a": {"type": "string"}}})
        assert result["type"] == "object"
        assert result["properties"] == {"a": {"type": "string"}}

    def test_empty_dict_becomes_object(self) -> None:
        assert sanitize_tool_schema({}) == {"type": "object"}

    def test_none_input_becomes_object(self) -> None:
        assert sanitize_tool_schema(None) == {"type": "object"}

    def test_object_type_no_properties_no_combinator_passes_through(self) -> None:
        # Valid as-is; type ensured present, nothing invented.
        assert sanitize_tool_schema({"type": "object"}) == {"type": "object"}


class TestTypeReconciliation:
    def test_type_array_with_object_collapses_to_scalar_string(self) -> None:
        result = sanitize_tool_schema(
            {"type": ["object", "null"], "properties": {"a": {"type": "string"}}}
        )
        # Scalar string "object", NOT ["object"] — array dropped entirely.
        assert result["type"] == "object"
        assert not isinstance(result["type"], list)

    def test_type_array_without_object_raises(self) -> None:
        try:
            sanitize_tool_schema({"type": ["string", "null"]})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")

    def test_scalar_non_object_type_raises(self) -> None:
        try:
            sanitize_tool_schema({"type": "string"})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")


class TestAllOf:
    def test_allof_of_object_fragments_unions_properties_and_required(self) -> None:
        schema = {
            "allOf": [
                {"properties": {"a": {"type": "string"}}, "required": ["a"]},
                {"properties": {"b": {"type": "integer"}}, "required": ["b"]},
            ],
            "required": ["c"],
        }
        result = sanitize_tool_schema(schema)
        assert result["type"] == "object"
        assert "allOf" not in result
        assert set(result["properties"].keys()) == {"a", "b"}
        # allOf required = union across branches + base-level required.
        assert set(result["required"]) == {"a", "b", "c"}

    def test_allof_with_ref_branch_raises(self) -> None:
        try:
            sanitize_tool_schema({"allOf": [{"$ref": "#/$defs/Foo"}]})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")

    def test_allof_with_scalar_type_branch_raises(self) -> None:
        try:
            sanitize_tool_schema({"allOf": [{"type": "string"}]})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")

    def test_allof_with_not_branch_raises(self) -> None:
        try:
            sanitize_tool_schema({"allOf": [{"not": {"type": "string"}}]})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")


class TestAnyOfOneOf:
    def test_anyof_required_is_intersection_unioned_with_base(self) -> None:
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
            "anyOf": [
                {"required": ["a", "shared"]},
                {"required": ["b", "shared"]},
            ],
        }
        result = sanitize_tool_schema(schema)
        assert result["type"] == "object"
        assert "anyOf" not in result
        # intersection of branch requireds = {shared}; base required = {x}.
        assert set(result["required"]) == {"x", "shared"}

    def test_oneof_branch_properties_unioned_up(self) -> None:
        schema = {
            "oneOf": [
                {"properties": {"a": {"type": "string"}}, "required": ["a"]},
                {"properties": {"b": {"type": "integer"}}, "required": ["b"]},
            ],
        }
        result = sanitize_tool_schema(schema)
        assert result["type"] == "object"
        assert "oneOf" not in result
        assert set(result["properties"].keys()) == {"a", "b"}
        # No common required across the two branches → intersection empty.
        assert "required" not in result or result["required"] == []

    def test_anyof_colliding_key_different_schema_becomes_nested_anyof(self) -> None:
        schema = {
            "anyOf": [
                {"properties": {"v": {"type": "string"}}},
                {"properties": {"v": {"type": "integer"}}},
            ],
        }
        result = sanitize_tool_schema(schema)
        assert result["type"] == "object"
        assert "anyOf" not in result  # top-level combinator gone
        v = result["properties"]["v"]
        assert set(v.keys()) == {"anyOf"}  # nested combinator is legal
        assert {"type": "string"} in v["anyOf"]
        assert {"type": "integer"} in v["anyOf"]
        assert len(v["anyOf"]) == 2

    def test_anyof_colliding_key_identical_schema_deduplicates(self) -> None:
        schema = {
            "anyOf": [
                {"properties": {"v": {"type": "string"}}},
                {"properties": {"v": {"type": "string"}}},
            ],
        }
        result = sanitize_tool_schema(schema)
        # Identical collision collapses to the single shared schema.
        assert result["properties"]["v"] == {"type": "string"}

    def test_anyof_with_non_object_branch_raises(self) -> None:
        try:
            sanitize_tool_schema({"anyOf": [{"required": ["a"]}, {"$ref": "#/x"}]})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")


class TestBothCombinatorsSimultaneously:
    def test_anyof_and_oneof_both_processed_note_appended_once(self) -> None:
        schema = {
            "description": "base desc",
            "anyOf": [{"required": ["a"]}, {"required": ["b"]}],
            "oneOf": [{"required": ["c"]}, {"required": ["d"]}],
        }
        result = sanitize_tool_schema(schema)
        assert result["type"] == "object"
        assert "anyOf" not in result
        assert "oneOf" not in result
        # Merge note appended exactly once even with two combinators.
        assert result["description"].count(MERGE_NOTE) == 1
        assert result["description"].startswith("base desc")


class TestRefBoundary:
    def test_bare_top_level_ref_raises(self) -> None:
        try:
            sanitize_tool_schema({"$ref": "#/$defs/Foo"})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")

    def test_top_level_not_raises(self) -> None:
        try:
            sanitize_tool_schema({"not": {"type": "string"}})
        except UnsanitizableToolSchema as exc:
            assert exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")

    def test_ref_alongside_object_shape_proceeds_and_preserves_ref(self) -> None:
        schema = {
            "$ref": "#/$defs/X",
            "type": "object",
            "properties": {"a": {"type": "string"}},
        }
        result = sanitize_tool_schema(schema)
        assert result["type"] == "object"
        # The sibling $ref is preserved untouched (DD3) — only a *bare*
        # top-level $ref raises.
        assert result["$ref"] == "#/$defs/X"
        assert result["properties"] == {"a": {"type": "string"}}


class TestEmptyCombinatorLists:
    def test_empty_allof_list_dropped_no_raise(self) -> None:
        result = sanitize_tool_schema({"allOf": []})
        assert result == {"type": "object"}

    def test_empty_anyof_list_dropped_no_raise(self) -> None:
        result = sanitize_tool_schema({"anyOf": []})
        assert result == {"type": "object"}


class TestPressKeyFixture:
    def test_press_key_real_fixture(self) -> None:
        result = sanitize_tool_schema(PRESS_KEY_INPUT_SCHEMA)
        assert result["type"] == "object"
        assert "anyOf" not in result
        assert set(result["properties"].keys()) == {"wcId", "name", "key", "modifiers"}
        # Properties carried through unchanged.
        assert result["properties"]["wcId"] == PRESS_KEY_INPUT_SCHEMA["properties"]["wcId"]
        assert (
            result["properties"]["modifiers"] == (PRESS_KEY_INPUT_SCHEMA["properties"]["modifiers"])
        )
        # anyOf branches require name OR key → intersection empty; base
        # required ['wcId'] is the only unconditional requirement.
        assert result["required"] == ["wcId"]


class TestNonMutation:
    def test_input_is_identical_and_byte_unchanged_after_call(self) -> None:
        schema = copy.deepcopy(PRESS_KEY_INPUT_SCHEMA)
        snapshot = copy.deepcopy(schema)
        before_id = id(schema)
        result = sanitize_tool_schema(schema)
        # DD2: input object is the same object and byte-equal to its snapshot.
        assert id(schema) == before_id
        assert schema == snapshot
        # The result is a distinct object, not the input.
        assert result is not schema

    def test_non_mutation_on_combinator_merge_path(self) -> None:
        schema = {
            "description": "d",
            "allOf": [
                {"properties": {"a": {"type": "string"}}, "required": ["a"]},
            ],
        }
        snapshot = copy.deepcopy(schema)
        sanitize_tool_schema(schema)
        assert schema == snapshot


class TestPreservation:
    def test_top_level_metadata_survives_unchanged(self) -> None:
        schema = {
            "type": "object",
            "title": "MyTool",
            "description": "does a thing",
            "additionalProperties": False,
            "$defs": {"Foo": {"type": "string"}},
            "definitions": {"Bar": {"type": "integer"}},
            "properties": {"a": {"type": "string"}},
        }
        result = sanitize_tool_schema(schema)
        assert result["title"] == "MyTool"
        # No combinator flattened → description byte-unchanged.
        assert result["description"] == "does a thing"
        assert result["additionalProperties"] is False
        assert result["$defs"] == {"Foo": {"type": "string"}}
        assert result["definitions"] == {"Bar": {"type": "integer"}}

    def test_description_byte_unchanged_when_no_combinator(self) -> None:
        result = sanitize_tool_schema(
            {"type": "object", "description": "untouched", "properties": {}}
        )
        assert result["description"] == "untouched"
        assert MERGE_NOTE not in result["description"]

    def test_merge_note_appended_when_combinator_flattened(self) -> None:
        result = sanitize_tool_schema(
            {"description": "orig", "anyOf": [{"required": ["a"]}, {"required": ["b"]}]}
        )
        assert result["description"] == f"orig {MERGE_NOTE}"

    def test_merge_note_created_when_no_existing_description(self) -> None:
        result = sanitize_tool_schema({"anyOf": [{"required": ["a"]}, {"required": ["b"]}]})
        assert result["description"] == MERGE_NOTE


class TestNestedUntouched:
    def test_nested_ref_and_defs_carried_through_unmodified(self) -> None:
        schema = {
            "type": "object",
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {"street": {"type": "string"}},
                }
            },
            "properties": {
                "home": {"$ref": "#/$defs/Address"},
                "alt": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
        }
        result = sanitize_tool_schema(schema)
        # Only the top level is rewritten (DD3) — nested $ref and nested anyOf
        # are byte-for-byte identical to the input.
        assert result["properties"]["home"] == {"$ref": "#/$defs/Address"}
        assert result["properties"]["alt"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
        assert result["$defs"] == schema["$defs"]


class TestUnsanitizableReason:
    def test_non_dict_input_raises_with_reason(self) -> None:
        try:
            sanitize_tool_schema([1, 2, 3])  # type: ignore[arg-type]
        except UnsanitizableToolSchema as exc:
            assert exc.reason and "list" in exc.reason
        else:
            raise AssertionError("expected UnsanitizableToolSchema")

    def test_every_unsanitizable_case_has_non_empty_reason(self) -> None:
        unsanitizable_inputs = [
            {"type": ["string", "null"]},
            {"type": "string"},
            {"allOf": [{"$ref": "#/x"}]},
            {"allOf": [{"type": "string"}]},
            {"allOf": [{"not": {"type": "string"}}]},
            {"anyOf": [{"required": ["a"]}, {"$ref": "#/x"}]},
            {"$ref": "#/$defs/Foo"},
            {"not": {"type": "string"}},
        ]
        for bad in unsanitizable_inputs:
            try:
                sanitize_tool_schema(bad)
            except UnsanitizableToolSchema as exc:
                assert exc.reason, f"empty reason for {bad!r}"
            else:
                raise AssertionError(f"expected raise for {bad!r}")
