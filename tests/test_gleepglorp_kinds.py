"""The GleepGlorp kinds registry (M36 F4 L1a, DD2): the explicit registry, its derived views,
and the lazy re-export that keeps ``proposals.shape``'s old names working."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from the_one.gleepglorp import kinds
from the_one.gleepglorp.proposals import shape

ROOT = Path(__file__).resolve().parent.parent / "the_one"

# Every name production code or tests reached through ``shape`` before the registry, minus the
# names that stay there as real attributes (ShapeError, ACTIONS, _ECHO_MAX, routine_service).
MOVED = [
    "normalize",
    "describe",
    "SPECS",
    "KINDS",
    "KIND_SUMMARIES",
    "OPERATOR_ONLY_FIELDS",
    "AGENT_FIELDS",
    "RULE_FIELDS",
    "ROUTINE_FIELDS",
    "SCHEDULE_EXAMPLE",
    "_agent_base",
    "spec_for",
    "comparable_value",
]
STAYING = ["ShapeError", "ACTIONS", "_ECHO_MAX", "routine_service", "FieldSpec", "Normalized"]


def test_the_registry_is_exactly_the_seven_kinds_in_order() -> None:
    assert isinstance(kinds.REGISTRY, tuple)
    assert [k.name for k in kinds.REGISTRY] == [
        "agent",
        "rule",
        "routine",
        "mcp_server",
        "provider",
        "knowledge_base",
        "secret",
    ]
    assert kinds.KINDS == (
        "agent",
        "rule",
        "routine",
        "mcp_server",
        "provider",
        "knowledge_base",
        "secret",
    )
    assert set(kinds.SPECS) == set(kinds.KIND_SUMMARIES) == set(kinds.KINDS)


def test_get_returns_the_kind_and_refuses_an_unknown_name() -> None:
    assert kinds.get("rule") is kinds.rule.KIND
    with pytest.raises(KeyError):
        kinds.get("nope")
    with pytest.raises(KeyError):
        kinds.describe("nope")


def test_operator_only_fields_appear_in_no_kinds_fields() -> None:
    stored = {f.stored for k in kinds.REGISTRY for f in k.fields}
    named = {f.name for k in kinds.REGISTRY for f in k.fields}
    for kind in kinds.REGISTRY:
        for field in kind.operator_only:
            assert field not in stored and field not in named, (kind.name, field)
    union = tuple(f for k in kinds.REGISTRY for f in k.operator_only)
    assert kinds.OPERATOR_ONLY_FIELDS == union
    assert kinds.OPERATOR_ONLY_FIELDS == (
        "secret_ids",
        "tool_overrides",
        "mcp_overrides",
        "self_revision_requires_approval",
        "routines_self_config_enabled",
        "routines_require_approval",
        "cwd",
        "sandbox",
        "secrets",
        # the provider's two (Leg 5a): a key or token is never GleepGlorp's to set
        "api_key",
        "secrets",
        # the knowledge base's three (M36 F5 L3a): folders, files and indexing are the operator's
        "folders",
        "items",
        "path",
        # the secret's three: a value, a key name and an agent's grant are never GleepGlorp's
        "values",
        "keys",
        "secret_ids",
    )


def test_the_fillable_kinds() -> None:
    assert kinds.FILLABLE == ("agent", "mcp_server", "provider", "knowledge_base", "secret")


@pytest.mark.parametrize("name", MOVED)
def test_shape_reexports_every_moved_name_lazily(name) -> None:
    assert name not in shape.__dict__  # never a real attribute: the lazy export stays live
    assert getattr(shape, name) is not None


@pytest.mark.parametrize("name", STAYING)
def test_shape_keeps_its_primitives(name) -> None:
    assert name in shape.__dict__


def test_the_reexport_points_at_the_registry_objects() -> None:
    assert shape.SPECS is kinds.SPECS
    assert shape.normalize is kinds.normalize
    assert shape.AGENT_FIELDS is kinds.agent.AGENT_FIELDS
    assert shape._agent_base is kinds.agent.agent_base


def test_an_unknown_shape_attribute_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError):
        shape.no_such_name  # noqa: B018
    from the_one.gleepglorp.proposals.shape import ShapeError  # a real name still imports

    assert issubclass(ShapeError, ValueError)


def test_shape_imports_nothing_from_kinds_at_module_level() -> None:
    tree = ast.parse((ROOT / "gleepglorp/proposals/shape.py").read_text())
    for node in tree.body:  # module level only: the lazy export imports inside a function
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n.startswith("the_one.gleepglorp.kinds") for n in names), names


def test_the_kinds_package_has_every_module_the_leg_lists() -> None:
    present = {p.name for p in (ROOT / "gleepglorp/kinds").glob("*.py")}
    assert {"__init__.py", "base.py", "errors.py", "deps.py", "agent.py", "rule.py"} <= present
    assert "routine.py" in present
