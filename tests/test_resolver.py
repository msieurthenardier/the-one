"""Tests for ``the_one.tools.resolver`` — narrowing and substitution
semantics, locked-down NULL, marker dispatch, and Pydantic interaction."""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel, Field, ValidationError

from the_one.tools.resolver import (
    Narrow,
    NarrowPrefix,
    NarrowSuperset,
    Substitute,
    _EmptyConfig,
    resolve,
)

# ---------------------------------------------------------------------------
# Fixture configs
# ---------------------------------------------------------------------------


class IntCfg(BaseModel):
    cap: Annotated[int, Narrow] = 100


class ListCfg(BaseModel):
    paths: Annotated[list[str], Narrow] = []


class ListUnhashableCfg(BaseModel):
    rules: Annotated[list[dict], Narrow] = []


class BoolCfg(BaseModel):
    redirects: Annotated[bool, Narrow] = True


class SubCfg(BaseModel):
    token: Annotated[str, Substitute] = ""


class NoMarkerCfg(BaseModel):
    weird: int = 0


class BothMarkersCfg(BaseModel):
    bad: Annotated[int, Narrow, Substitute] = 0


class StrNarrowCfg(BaseModel):
    label: Annotated[str, Narrow] = ""


class FieldPlusMarkerCfg(BaseModel):
    cap: Annotated[int, Field(description="x"), Narrow] = 100


class PrefixCfg(BaseModel):
    paths: Annotated[list[str], NarrowPrefix] = []


class SupersetCfg(BaseModel):
    deny: Annotated[list[str], NarrowSuperset] = []


class PrefixOnIntCfg(BaseModel):
    cap: Annotated[int, NarrowPrefix] = 100  # type-mismatch fixture


class SupersetOnIntCfg(BaseModel):
    cap: Annotated[int, NarrowSuperset] = 100


class NarrowPlusPrefixCfg(BaseModel):
    bad: Annotated[list[str], Narrow, NarrowPrefix] = []


class PrefixPlusSupersetCfg(BaseModel):
    bad: Annotated[list[str], NarrowPrefix, NarrowSuperset] = []


class PrefixPlusSubstituteCfg(BaseModel):
    bad: Annotated[list[str], NarrowPrefix, Substitute] = []


class SupersetPlusSubstituteCfg(BaseModel):
    bad: Annotated[list[str], NarrowSuperset, Substitute] = []


class NarrowPlusSupersetCfg(BaseModel):
    bad: Annotated[list[str], Narrow, NarrowSuperset] = []


# ---------------------------------------------------------------------------
# Empty-schema short-circuit
# ---------------------------------------------------------------------------


class TestEmptySchemaShortCircuit:
    def test_empty_schema_returns_empty_instance(self) -> None:
        result = resolve(_EmptyConfig, None, None)
        assert isinstance(result, _EmptyConfig)
        assert result.model_dump() == {}

    def test_empty_schema_ignores_tool_config_keys(self) -> None:
        # `model_fields` is empty; the merge step is skipped entirely so
        # extra keys are silently dropped (no ValidationError).
        result = resolve(_EmptyConfig, {"x": 1}, None)
        assert result.model_dump() == {}

    def test_empty_schema_ignores_agent_override_keys(self) -> None:
        result = resolve(_EmptyConfig, {"x": 1}, {"foo": 2})
        assert result.model_dump() == {}


# ---------------------------------------------------------------------------
# Locked-down NULL semantic (agent_override is None)
# ---------------------------------------------------------------------------


class TestLockedDownNull:
    def test_null_override_preserves_tool_config(self) -> None:
        result = resolve(IntCfg, {"cap": 50}, None)
        assert result.cap == 50

    def test_null_override_uses_schema_default_when_tool_empty(self) -> None:
        result = resolve(IntCfg, None, None)
        assert result.cap == 100  # schema default

    def test_null_override_uses_schema_default_when_tool_missing_key(self) -> None:
        result = resolve(IntCfg, {}, None)
        assert result.cap == 100


# ---------------------------------------------------------------------------
# Narrow — int
# ---------------------------------------------------------------------------


class TestNarrowInt:
    def test_narrow_strict_lt(self) -> None:
        result = resolve(IntCfg, {"cap": 50}, {"cap": 30})
        assert result.cap == 30

    def test_narrow_equal(self) -> None:
        result = resolve(IntCfg, {"cap": 50}, {"cap": 50})
        assert result.cap == 50

    def test_narrow_widen_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(IntCfg, {"cap": 50}, {"cap": 80})
        assert "widens" in str(exc.value)
        assert "cap" in str(exc.value)


# ---------------------------------------------------------------------------
# Narrow — list
# ---------------------------------------------------------------------------


class TestNarrowList:
    def test_narrow_subset(self) -> None:
        result = resolve(ListCfg, {"paths": ["/home", "/tmp"]}, {"paths": ["/home"]})
        assert result.paths == ["/home"]

    def test_narrow_subset_unhashable(self) -> None:
        # Verifies the `all(item in tool_val for item in agent_val)` pattern
        # works on unhashable elements (dicts) — which `set()`-based
        # comparisons would not.
        result = resolve(
            ListUnhashableCfg,
            {"rules": [{"a": 1}, {"b": 2}]},
            {"rules": [{"a": 1}]},
        )
        assert result.rules == [{"a": 1}]

    def test_narrow_adds_element_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(ListCfg, {"paths": ["/home"]}, {"paths": ["/home", "/etc"]})
        assert "widens" in str(exc.value)


# ---------------------------------------------------------------------------
# Narrow — bool
# ---------------------------------------------------------------------------


class TestNarrowBool:
    def test_narrow_true_to_false(self) -> None:
        result = resolve(BoolCfg, {"redirects": True}, {"redirects": False})
        assert result.redirects is False

    def test_narrow_equal_true(self) -> None:
        result = resolve(BoolCfg, {"redirects": True}, {"redirects": True})
        assert result.redirects is True

    def test_narrow_equal_false(self) -> None:
        result = resolve(BoolCfg, {"redirects": False}, {"redirects": False})
        assert result.redirects is False

    def test_narrow_false_to_true_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(BoolCfg, {"redirects": False}, {"redirects": True})
        assert "widens" in str(exc.value)


# ---------------------------------------------------------------------------
# Substitute
# ---------------------------------------------------------------------------


class TestSubstitute:
    def test_substitute_replaces_value(self) -> None:
        result = resolve(SubCfg, {"token": "tool-tok"}, {"token": "agent-tok"})
        assert result.token == "agent-tok"

    def test_substitute_no_comparison_performed(self) -> None:
        # A substitute on a string field with totally different shapes
        # works fine — no narrowing semantics applied.
        result = resolve(SubCfg, {"token": ""}, {"token": "anything-goes"})
        assert result.token == "anything-goes"


# ---------------------------------------------------------------------------
# Marker errors
# ---------------------------------------------------------------------------


class TestMarkerErrors:
    def test_no_marker_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(NoMarkerCfg, {"weird": 0}, {"weird": 5})
        assert "no Narrow/Substitute marker" in str(exc.value)

    def test_both_markers_raises(self) -> None:
        # L1 reworked the error message to enumerate all four markers; class
        # remains ValueError (no exception-class promotion).
        with pytest.raises(ValueError) as exc:
            resolve(BothMarkersCfg, {"bad": 0}, {"bad": 5})
        assert "multiple narrow/substitute" in str(exc.value)

    def test_narrow_on_str_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            resolve(StrNarrowCfg, {"label": "tool"}, {"label": "agent"})
        assert "Narrow on str" in str(exc.value)

    def test_field_with_field_metadata_plus_marker(self) -> None:
        # Verifies the resolver finds the marker alongside `FieldInfo`
        # metadata (the `m is Narrow` identity check works regardless of
        # other entries in field_info.metadata).
        result = resolve(FieldPlusMarkerCfg, {"cap": 50}, {"cap": 30})
        assert result.cap == 30


# ---------------------------------------------------------------------------
# Pydantic interaction
# ---------------------------------------------------------------------------


class TestPydanticInteraction:
    def test_type_mismatch_raises_validation_error(self) -> None:
        # The resolver hands `merged` to `model_validate`, which raises a
        # Pydantic `ValidationError` for the bad type. (The narrow-check
        # passes — `"fifty"` is not a number, so the int branch falls
        # through to `NotImplementedError`. The test pins the actually-
        # observable behavior: in this resolver structure, str-vs-int
        # widens through the NotImplementedError path; if the agent
        # override happens to satisfy narrowing first (e.g. an int), then
        # the type check Pydantic raises is operator-readable.)
        # Use a numeric override that the int-narrowing branch handles
        # (so it gets through to model_validate), then have the *type*
        # mismatch surface there.
        class CapsuleCfg(BaseModel):
            cap: Annotated[int, Substitute] = 100

        with pytest.raises(ValidationError):
            resolve(CapsuleCfg, {"cap": 50}, {"cap": "fifty"})

    def test_unknown_key_in_override_silently_dropped(self) -> None:
        # Pydantic default is `extra="ignore"` — keys not in
        # `schema.model_fields` never enter the dispatch loop and the
        # final `model_validate` drops them silently.
        result = resolve(IntCfg, {"cap": 50}, {"unknown_key": 999})
        assert result.cap == 50

    def test_unknown_key_in_tool_config_silently_dropped(self) -> None:
        result = resolve(IntCfg, {"cap": 50, "unknown_tool_key": 999}, None)
        assert result.cap == 50


# ---------------------------------------------------------------------------
# NarrowPrefix
# ---------------------------------------------------------------------------


class TestNarrowPrefix:
    """`NarrowPrefix` non-list type-error uses NotImplementedError to match
    F2's Narrow-on-str precedent (resolver.py:116). Test for it accordingly."""

    def test_happy_descendant(self) -> None:
        result = resolve(PrefixCfg, {"paths": ["/home/u"]}, {"paths": ["/home/u/projects"]})
        assert result.paths == ["/home/u/projects"]

    def test_happy_equal_to_root(self) -> None:
        result = resolve(PrefixCfg, {"paths": ["/home/u"]}, {"paths": ["/home/u"]})
        assert result.paths == ["/home/u"]

    def test_happy_multi_root_match(self) -> None:
        # agent path /home/u/x is descendant of one of the two tool roots.
        result = resolve(
            PrefixCfg,
            {"paths": ["/home/u", "/var/data"]},
            {"paths": ["/home/u/x"]},
        )
        assert result.paths == ["/home/u/x"]

    def test_widen_outside_any_root_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(PrefixCfg, {"paths": ["/home/u"]}, {"paths": ["/etc"]})
        assert "widens" in str(exc.value)
        assert "not within" in str(exc.value)

    def test_non_list_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            resolve(PrefixOnIntCfg, {"cap": 100}, {"cap": 50})
        assert "non-list" in str(exc.value)


# ---------------------------------------------------------------------------
# NarrowSuperset
# ---------------------------------------------------------------------------


class TestNarrowSuperset:
    """`NarrowSuperset` membership uses raw == on values; canonicalization is
    consumer-side. Non-list type-error uses NotImplementedError, matching
    F2's Narrow-on-str precedent."""

    def test_happy_agent_superset(self) -> None:
        result = resolve(SupersetCfg, {"deny": ["/etc"]}, {"deny": ["/etc", "/proc"]})
        assert result.deny == ["/etc", "/proc"]

    def test_happy_equal(self) -> None:
        result = resolve(SupersetCfg, {"deny": ["/etc"]}, {"deny": ["/etc"]})
        assert result.deny == ["/etc"]

    def test_widen_drops_tool_entry_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                SupersetCfg,
                {"deny": ["/etc", "/proc"]},
                {"deny": ["/etc"]},  # missing /proc — narrows the denylist
            )
        assert "widens" in str(exc.value)
        assert "/proc" in str(exc.value)

    def test_non_list_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            resolve(SupersetOnIntCfg, {"cap": 100}, {"cap": 50})
        assert "non-list" in str(exc.value)


# ---------------------------------------------------------------------------
# Mutual exclusion across the four markers
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    @pytest.mark.parametrize(
        "schema",
        [
            NarrowPlusPrefixCfg,
            NarrowPlusSupersetCfg,
            PrefixPlusSupersetCfg,
            PrefixPlusSubstituteCfg,
            SupersetPlusSubstituteCfg,
        ],
    )
    def test_multi_marker_rejected(self, schema: type[BaseModel]) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(schema, {"bad": []}, {"bad": []})
        assert "multiple narrow/substitute" in str(exc.value)


# ---------------------------------------------------------------------------
# Squawk 0248: a never-saved tool's default_factory baseline
# ---------------------------------------------------------------------------


class TestDefaultFactoryBaseline:
    """With no stored operator config, a `default_factory` denylist's baseline
    is the factory's value (was `PydanticUndefined`, which raised
    `NotImplementedError` and stopped the agent from being built)."""

    def _tools(self, override: dict) -> dict:
        from the_one.tools.builtins import BuiltinToolProvider

        tools = BuiltinToolProvider().get_tools(tool_configs={}, agent_overrides=override)
        return {t.name: t for t in tools}

    def test_filesystem_override_with_defaults_builds(self) -> None:
        from the_one.tools.filesystem import DEFAULT_PATH_DENYLIST, FilesystemConfig

        value = [*DEFAULT_PATH_DENYLIST, "/probe"]
        resolved = resolve(FilesystemConfig, {}, {"path_denylist": value})
        assert set(value) <= set(resolved.path_denylist)
        tool = self._tools({"read_file": {"path_denylist": value}})["read_file"]
        assert set(value) <= set(tool._config.path_denylist)

    def test_execution_override_with_defaults_builds(self) -> None:
        from the_one.tools.execution import DEFAULT_COMMAND_DENYLIST, ExecutionConfig

        value = [*DEFAULT_COMMAND_DENYLIST, "curl "]
        resolved = resolve(ExecutionConfig, {}, {"command_denylist": value})
        assert set(value) <= set(resolved.command_denylist)
        tool = self._tools({"shell": {"command_denylist": value}})["shell"]
        assert set(value) <= set(tool._config.command_denylist)

    def test_filesystem_override_dropping_a_default_is_refused(self) -> None:
        from the_one.tools.filesystem import DEFAULT_PATH_DENYLIST, FilesystemConfig

        value = [p for p in DEFAULT_PATH_DENYLIST if p != "~/.ssh"] + ["/probe"]
        with pytest.raises(ValueError, match="widens FilesystemConfig.path_denylist.*~/.ssh"):
            resolve(FilesystemConfig, {}, {"path_denylist": value})
        with pytest.raises(ValueError, match="widens"):
            self._tools({"read_file": {"path_denylist": value}})

    def test_execution_override_dropping_a_default_is_refused(self) -> None:
        from the_one.tools.execution import DEFAULT_COMMAND_DENYLIST, ExecutionConfig

        value = [c for c in DEFAULT_COMMAND_DENYLIST if c != "sudo "]
        with pytest.raises(ValueError, match="widens ExecutionConfig.command_denylist.*sudo"):
            resolve(ExecutionConfig, {}, {"command_denylist": value})
        with pytest.raises(ValueError, match="widens"):
            self._tools({"shell": {"command_denylist": value}})
